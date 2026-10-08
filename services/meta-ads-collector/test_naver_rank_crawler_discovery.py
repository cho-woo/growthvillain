import asyncio
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

from naver_rank_crawler import (CATEGORY_PATHS, RankCollectionError, RankDataUnavailable, latest_public_date,
                                parse_response_rows, rank_request_matches, wait_for_matching_dom, read_current_snapshot)


def request(**changes):
    values = {"url": "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver",
              "method": "POST", "resource_type": "xhr",
              "post_data_json": {"cid": "50000023", "timeUnit": "date", "startDate": "2026-10-06", "endDate": "2026-10-06", "page": "1", "count": "20"}}
    values.update(changes)
    return SimpleNamespace(**values)


class DiscoveryValidationTests(unittest.TestCase):
    def test_latest_visible_date_excludes_later_date_selector(self):
        self.assertEqual(date(2026, 10, 6), latest_public_date("2026.10.05.(월) 2026.10.06.(화) 2026 10 07", today=date(2026, 10, 8)))

    def test_unavailable_future_and_stale_home_dates_fail(self):
        for text in ("날짜 없음", "2026.10.08.(목)", "2026.10.09.(금)", "2026.10.04.(일)"):
            with self.subTest(text=text), self.assertRaises(RankCollectionError):
                latest_public_date(text, today=date(2026, 10, 8))

    def test_selected_paths(self):
        self.assertEqual(("50000006", "50000023"), CATEGORY_PATHS["50000023"])
        self.assertEqual(("50000006", "50000024"), CATEGORY_PATHS["50000024"])

    def test_response_must_match_observed_exact_date_category_and_page(self):
        self.assertTrue(rank_request_matches(request(), "50000023", date(2026, 10, 6), 1))
        for key, value in (("cid", "50000000"), ("startDate", "2026-09-07"), ("endDate", "2026-10-07"),
                           ("page", "2"), ("timeUnit", "month"), ("count", "100"), ("gender", "f")):
            params = request().post_data_json | {key: value}
            with self.subTest(key=key): self.assertFalse(rank_request_matches(request(post_data_json=params), "50000023", date(2026, 10, 6), 1))
        self.assertFalse(rank_request_matches(request(url="https://example.com/shoppingInsight/getCategoryKeywordRank.naver"), "50000023", date(2026, 10, 6), 1))

    def test_empty_or_partial_response_is_not_a_snapshot(self):
        for rows in ([], [{"rank": 1, "keyword": "오메가3"}], None):
            with self.subTest(rows=rows), self.assertRaises(RankCollectionError): parse_response_rows({"ranks": rows}, 1)

    def test_response_rows_require_exact_contiguous_page(self):
        rows = [{"rank": i, "keyword": f"영양검색어{i}", "linkId": "ignored"} for i in range(1, 21)]
        self.assertEqual({"rank": 1, "keyword": "영양검색어1"}, parse_response_rows({"ranks": rows}, 1)[0])
        with self.assertRaises(RankCollectionError): parse_response_rows({"ranks": rows}, 21)
        rows[0]["rank"] = True
        with self.assertRaises(RankCollectionError): parse_response_rows({"ranks": rows}, 1)

    def test_later_empty_page_is_incomplete_not_an_unavailable_day(self):
        with self.assertRaises(RankDataUnavailable):
            parse_response_rows({"ranks": []}, 1)
        for first_rank in (21, 41, 61, 81):
            with self.subTest(first_rank=first_rank), self.assertRaises(RankCollectionError) as result:
                parse_response_rows({"ranks": []}, first_rank)
            self.assertNotIsInstance(result.exception, RankDataUnavailable)


class DomFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_yesterday_data_takes_precedence_over_lagging_home(self):
        read = AsyncMock(return_value={"date": "2026-10-07"})
        with patch("naver_rank_crawler.discover_latest_date", AsyncMock()) as discover:
            day, snapshot, method = await read_current_snapshot(None, read, None, {}, today=date(2026, 10, 8))
        self.assertEqual(date(2026, 10, 7), day)
        self.assertEqual("public-ui-latest", method)
        discover.assert_not_called()
        self.assertEqual(1, read.await_count)

    async def test_only_empty_successful_response_allows_one_observed_date_fallback(self):
        read = AsyncMock(side_effect=[RankDataUnavailable("empty"), {"date": "2026-10-06"}])
        with patch("naver_rank_crawler.discover_latest_date", AsyncMock(return_value=date(2026, 10, 6))), \
             patch("naver_rank_crawler.asyncio.sleep", AsyncMock()):
            day, snapshot, method = await read_current_snapshot(None, read, None, {}, today=date(2026, 10, 8))
        self.assertEqual(date(2026, 10, 6), day)
        self.assertEqual("public-home", method)
        self.assertEqual(2, read.await_count)

    async def test_explicit_date_and_network_failure_never_fallback(self):
        for day, failure in ((date(2026, 10, 7), RankDataUnavailable("empty")),
                             (None, RankCollectionError("HTTP 403")), (None, TimeoutError())):
            read = AsyncMock(side_effect=failure)
            with self.subTest(day=day, failure=type(failure).__name__), \
                 patch("naver_rank_crawler.discover_latest_date", AsyncMock()) as discover:
                with self.assertRaises(type(failure)):
                    await read_current_snapshot(None, read, day, {}, today=date(2026, 10, 8))
                discover.assert_not_called()
                self.assertEqual(1, read.await_count)

    async def test_stale_first_page_with_new_category_links_waits_for_actual_response_keywords(self):
        from playwright.async_api import async_playwright
        def links(prefix):
            return "".join('<a class="link_text" href="/shoppingInsight/sKeyword.naver?' +
                           urlencode({"cid": "50000023", "keyword": f"{prefix}{i}"}) + '"><span class="rank_top1000_num">' +
                           str(i) + '</span>' + f"{prefix}{i}" + '</a>' for i in range(1, 21))
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content('<base href="https://datalab.naver.com/"><div class="rank_top1000_list">' + links("패션") + '</div>')
                rows = [{"rank": i, "keyword": f"영양{i}"} for i in range(1, 21)]
                task = asyncio.create_task(wait_for_matching_dom(page, rows, "50000023"))
                await asyncio.sleep(0.15)
                self.assertFalse(task.done(), "stale rank numbers and new cid links must not pass")
                await page.locator('.rank_top1000_list').evaluate('(element, markup) => element.innerHTML = markup', links("영양"))
                await asyncio.wait_for(task, timeout=3)
            finally:
                await browser.close()


if __name__ == "__main__": unittest.main()
