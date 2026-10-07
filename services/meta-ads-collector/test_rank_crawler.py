import copy
from datetime import date, timedelta, datetime
import unittest
from urllib.parse import urlencode

from naver_rank_crawler import KST, RankCollectionError, parse_collection_date, parse_rows


class RankCrawlerValidationTests(unittest.TestCase):
    def rows(self, start=1):
        return [
            {"rank": str(rank), "text": f"{rank}검색어{rank}\n  ",
             "href": "/shoppingInsight/sKeyword.naver?" + urlencode({"keyword": f"검색어{rank}", "cid": "50000002"})}
            for rank in range(start, start + 20)
        ]

    def test_accepts_consecutive_page_with_visible_matching_keywords(self):
        entries = parse_rows(self.rows(21), "50000002", 21)
        self.assertEqual(entries[0], {"rank": 21, "keyword": "검색어21"})
        self.assertEqual(entries[-1]["rank"], 40)

    def test_rejects_stale_page(self):
        with self.assertRaises(RankCollectionError):
            parse_rows(self.rows(), "50000002", 21)

    def test_rejects_incomplete_page(self):
        with self.assertRaises(RankCollectionError):
            parse_rows(self.rows()[:-1], "50000002", 1)

    def test_rejects_mismatched_category(self):
        with self.assertRaises(RankCollectionError):
            parse_rows(self.rows(), "50000006", 1)

    def test_rejects_unexpected_link_and_keyword_mismatch(self):
        rows = self.rows()
        for changed in (
            {"href": "https://example.com/shoppingInsight/sKeyword.naver?keyword=검색어1&cid=50000002"},
            {"href": "/shoppingInsight/sCategory.naver?keyword=검색어1&cid=50000002"},
            {"href": "/shoppingInsight/sKeyword.naver?keyword=다른검색어&cid=50000002"},
            {"text": "1다른검색어"},
        ):
            with self.subTest(changed=changed):
                edited = copy.deepcopy(rows)
                edited[0].update(changed)
                with self.assertRaises(RankCollectionError):
                    parse_rows(edited, "50000002", 1)

    def test_date_has_full_prior_comparison_window(self):
        self.assertEqual(parse_collection_date("2017-08-08"), date(2017, 8, 8))
        with self.assertRaises(ValueError):
            parse_collection_date("2017-08-07")

    def test_future_and_ambiguous_dates_rejected(self):
        today = datetime.now(KST).date()
        for value in (today.isoformat(), "20261004", "2026-02-30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_collection_date(value)
        self.assertEqual(parse_collection_date(None), today - timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
