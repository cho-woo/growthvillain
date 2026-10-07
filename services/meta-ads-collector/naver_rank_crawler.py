"""Read dated keyword ranks through Naver's public Shopping Insight page.

This browser collector uses the public category/date controls and pagination.
It does not call an undocumented endpoint or infer a brand from a product term.
Only two complete, validated daily snapshots are written to the output file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from naver_trends import validate_snapshot

SOURCE_URL = "https://datalab.naver.com/shoppingInsight/sCategory.naver"
CATEGORIES = {
    "50000000": "패션의류", "50000001": "패션잡화", "50000002": "화장품/미용",
    "50000003": "디지털/가전", "50000004": "가구/인테리어", "50000005": "출산/육아",
    "50000006": "식품", "50000007": "스포츠/레저", "50000008": "생활/건강",
    "50000009": "여가/생활편의", "50000010": "면세점", "50005542": "도서",
    "50000023": "건강식품", "50001899": "건강환/정", "50001090": "비타민제",
    "50001092": "영양제", "50017220": "효소", "50018919": "건강분말",
    "50000024": "다이어트식품",
}
CATEGORY_PATHS = {key: (key,) for key in CATEGORIES}
CATEGORY_PATHS.update({
    "50000023": ("50000006", "50000023"),
    "50000024": ("50000006", "50000024"),
    **{key: ("50000006", "50000023", key)
       for key in ("50001899", "50001090", "50001092", "50017220", "50018919")},
})
KST = timezone(timedelta(hours=9))
SNAPSHOT_SIZE = 100
PAGE_INTERVAL_SECONDS = 2
DATE_INTERVAL_SECONDS = 10


class RankCollectionError(RuntimeError):
    """The public page did not provide a complete verifiable snapshot."""


def parse_collection_date(value: str | None) -> date:
    yesterday = datetime.now(KST).date() - timedelta(days=1)
    try:
        if value is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Invalid ISO date format")
        day = date.fromisoformat(value) if value else yesterday
    except (ValueError, TypeError) as exc:
        raise ValueError("조회 날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc
    if day > yesterday or day < date(2017, 8, 8):
        raise ValueError("조회 날짜는 2017-08-08부터 어제까지 선택할 수 있습니다.")
    return day


def parse_rows(raw_rows: list[dict], category: str, first_rank: int) -> list[dict]:
    """Reject duplicate/stale pages, unexpected links, and mismatched categories."""
    if len(raw_rows) != 20:
        raise RankCollectionError("인기검색어 목록 일부가 누락되었습니다. 결과를 저장하지 않습니다.")
    entries = []
    for expected, row in enumerate(raw_rows, start=first_rank):
        try:
            rank = int(row["rank"])
            parsed = urlsplit(urljoin(SOURCE_URL, row["href"]))
            query = parse_qs(parsed.query)
            keyword = query["keyword"][0].strip()
            linked_category = query["cid"][0]
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise RankCollectionError("인기검색어 링크 구조가 변경되었습니다.") from exc
        if (rank != expected or linked_category != category or not keyword
                or parsed.scheme != "https" or parsed.netloc != "datalab.naver.com"
                or parsed.path != "/shoppingInsight/sKeyword.naver"):
            raise RankCollectionError("날짜·분야에 맞는 연속 순위를 확인하지 못했습니다.")
        visible_keyword = re.sub(r"^\s*" + str(rank) + r"\s*", "", row.get("text", ""), count=1).strip()
        if visible_keyword != keyword:
            raise RankCollectionError("인기검색어 링크와 화면의 검색어가 다릅니다.")
        entries.append({"rank": rank, "keyword": keyword})
    return entries


async def select_value(select, value: str) -> None:
    button = select.locator(".select_btn")
    if (await button.inner_text()).strip() == value:
        return
    await button.click()
    option = select.locator("a.option").filter(has_text=re.compile(r"^\s*" + re.escape(value) + r"\s*$"))
    if await option.count() != 1:
        raise RankCollectionError(f"네이버 조회 조건에서 {value} 값을 선택할 수 없습니다.")
    await option.click()
    if (await button.inner_text()).strip() != value:
        raise RankCollectionError("조회 조건을 적용하지 못했습니다.")


async def snapshot(page, category: str, day: date, diagnostic: dict | None = None) -> dict:
    diagnostic = diagnostic if diagnostic is not None else {}
    diagnostic["step"] = "category-and-date-controls"
    form = page.locator(".step_form").first
    for level, category_id in enumerate(CATEGORY_PATHS[category]):
        category_select = form.locator(".set_period.category .select").nth(level)
        if (await category_select.locator(".select_btn").inner_text()).strip() == CATEGORIES[category_id]:
            continue
        await category_select.locator(".select_btn").click()
        await category_select.locator(f'a[data-cid="{category_id}"]').click()
    await form.locator("label.period.input").click()
    date_selects = form.locator(".set_period_target .select")
    if await date_selects.count() != 6:
        raise RankCollectionError("네이버 날짜 선택 화면 구조가 변경되었습니다.")
    # Day 1 is valid in every month and avoids a 29/30/31 rollover.
    await select_value(date_selects.nth(2), "01")
    for offset in (0, 3):
        for index, value in enumerate((str(day.year), f"{day.month:02d}", f"{day.day:02d}")):
            await select_value(date_selects.nth(offset + index), value)

    expected_date = day.strftime("%Y.%m.%d.")
    expected_range = f"{expected_date} ~ {expected_date}"
    heading = page.locator(".insite_title").filter(has_text="인기검색어")
    # Observe only status codes from requests triggered by the normal submit.
    # No response bodies or undocumented endpoints are accessed.
    requests, failures = set(), []
    def observe_request(request):
        if request.resource_type in {"xhr", "fetch"} and urlsplit(request.url).hostname == "datalab.naver.com":
            requests.add(request)
    def observe_failure(request):
        if request in requests:
            failures.append("request-failed")
    def observe_response(result):
        if result.request in requests and result.status >= 400:
            failures.append(f"HTTP {result.status}")
    page.on("request", observe_request)
    page.on("requestfailed", observe_failure)
    page.on("response", observe_response)
    diagnostic["step"] = "submit-query"
    await form.locator(".btn_submit").click()
    await heading.filter(has_text=expected_range).wait_for(timeout=25000)
    await page.wait_for_load_state("networkidle", timeout=25000)
    if failures or not requests:
        raise RankCollectionError("네이버 조회 요청의 완료를 확인하지 못했습니다. 이전 목록을 재사용하지 않습니다.")
    page.remove_listener("request", observe_request)
    page.remove_listener("requestfailed", observe_failure)
    page.remove_listener("response", observe_response)
    if CATEGORIES[category] not in (await heading.inner_text()):
        raise RankCollectionError("조회 결과의 분야가 선택한 분야와 다릅니다.")


    entries = []
    for page_index in range(5):
        diagnostic["step"] = f"read-rank-page-{page_index + 1}"
        expected_rank = page_index * 20 + 1
        await page.wait_for_function("""expected => {
            const el = document.querySelector('.rank_top1000_list .rank_top1000_num');
            return el && Number(el.textContent.trim()) === expected;
        }""", arg=expected_rank, timeout=15000)
        if expected_range not in " ".join((await heading.inner_text()).split()):
            raise RankCollectionError("페이지를 넘기는 동안 조회 날짜가 바뀌었습니다.")
        raw = await page.locator(".rank_top1000_list a.link_text").evaluate_all("""nodes => nodes.map(el => ({
            rank: el.querySelector('.rank_top1000_num')?.textContent.trim(),
            href: el.getAttribute('href'), text: el.textContent.trim()
        }))""")
        entries.extend(parse_rows(raw, category, expected_rank))
        if page_index < 4:
            await asyncio.sleep(PAGE_INTERVAL_SECONDS)
            await page.locator(".rank_top1000 .btn_page_next").click()
    result = {"category": category, "date": day.isoformat(), "sourceUrl": SOURCE_URL, "entries": entries}
    validate_snapshot(result, expected_count=SNAPSHOT_SIZE)
    return result

async def collect_pair(category: str, day: date, diagnostic: dict | None = None) -> dict:
    from playwright.async_api import async_playwright
    diagnostic = diagnostic if diagnostic is not None else {}
    diagnostic.update({"stage": "browser-launch", "category": category, "date": day.isoformat()})
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chromium", headless=True, args=["--lang=ko-KR"])
        try:
            context = await browser.new_context(locale="ko-KR", viewport={"width": 1440, "height": 1000})

            async def read_day(target_day, stage):
                # Separate documents prevent stale pagination; one context keeps
                # the ordinary public browser session for both date queries.
                page = await context.new_page()
                page.set_default_timeout(15000)
                diagnostic["stage"] = stage
                diagnostic["step"] = "public-page-navigation"
                diagnostic.pop("initialStatus", None)
                def observe_navigation(response):
                    if (response.request.is_navigation_request()
                            and urlsplit(response.url).hostname == "datalab.naver.com"):
                        diagnostic["initialStatus"] = response.status
                page.on("response", observe_navigation)
                try:
                    response = await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=45000)
                    if response:
                        diagnostic["initialStatus"] = response.status
                        if response.status >= 400:
                            raise RankCollectionError(f"네이버 공개 페이지가 응답하지 않습니다 (HTTP {response.status}).")
                    await page.locator(".rank_top1000_list a.link_text").first.wait_for(timeout=25000)
                    await page.wait_for_load_state("networkidle", timeout=20000)
                    return await snapshot(page, category, target_day, diagnostic)
                finally:
                    await page.close()

            current = await read_day(day, "current-snapshot")
            diagnostic["step"] = "date-request-interval"
            await asyncio.sleep(DATE_INTERVAL_SECONDS)
            previous = await read_day(day - timedelta(days=7), "previous-snapshot")
            diagnostic["stage"] = "complete"
            return {"current": current, "previous": previous}
        finally:
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 쇼핑인사이트 공개 인기검색어 일별 순위 비교 자료 수집")
    parser.add_argument("--category", choices=sorted(CATEGORIES), default="50000023")
    parser.add_argument("--date", help="조회일 YYYY-MM-DD. 기본값: 한국 시간 어제")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    diagnostic = {"stage": "input-validation"}
    try:
        day = parse_collection_date(args.date)
        payload = asyncio.run(asyncio.wait_for(collect_pair(args.category, day, diagnostic), timeout=180))
        diagnostic["stage"] = "save-output"
        output = args.output.expanduser().absolute()
        if not output.parent.is_dir():
            raise ValueError("저장 폴더가 없습니다. 외장 드라이브 연결을 확인해 주세요.")
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, output)
        print(json.dumps({"ok": True, "category": args.category, "date": day.isoformat(), "count": SNAPSHOT_SIZE}, ensure_ascii=False))
        return 0
    except Exception as exc:
        if isinstance(exc, (RankCollectionError, ValueError)):
            message = str(exc)
        elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            message = "네이버 순위 조회 제한 시간을 초과했습니다. 결과를 저장하지 않았습니다."
        else:
            message = f"네이버 공개 화면을 수집하지 못했습니다 ({type(exc).__name__}). 결과를 저장하지 않았습니다."
        diagnostic["errorType"] = type(exc).__name__
        operation = re.match(r"([A-Za-z_.]+):", str(exc))
        if operation:
            diagnostic["operation"] = operation.group(1)
        network_error = re.search(r"net::[A-Z_]+", str(exc))
        if network_error:
            diagnostic["networkError"] = network_error.group(0)
        print(json.dumps({"ok": False, "message": message, "diagnostic": diagnostic}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
