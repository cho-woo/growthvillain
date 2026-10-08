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
HOME_URL = "https://datalab.naver.com/"
# This path is a filter for responses triggered by the public UI. It is never
# called directly by this collector.
RANK_RESPONSE_PATH = "/shoppingInsight/getCategoryKeywordRank.naver"
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


class RankDataUnavailable(RankCollectionError):
    """A matching successful public response explicitly returned no ranks."""


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


def latest_public_date(text: str, *, today: date) -> date:
    days = []
    for value in re.findall(r"\b(\d{4}\.\d{2}\.\d{2})\.\([월화수목금토일]\)", text):
        try:
            days.append(date.fromisoformat(value.replace(".", "-")))
        except ValueError:
            continue
    if not days:
        raise RankCollectionError("공개 홈에서 일간 순위 날짜를 확인하지 못했습니다.")
    latest = max(days)
    if not 1 <= (today - latest).days <= 3:
        raise RankCollectionError("최신 공개 순위 날짜가 오늘 이전 3일 범위를 벗어났습니다.")
    return latest


async def discover_latest_date(context, diagnostic: dict) -> date:
    page = await context.new_page()
    try:
        diagnostic.update(stage="date-discovery", step="public-home-navigation")
        response = await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
        if response is None or response.status >= 400:
            raise RankCollectionError("네이버 공개 홈에 접근할 수 없습니다.")
        await page.wait_for_function("""() => /\\d{4}\\.\\d{2}\\.\\d{2}\\.\\([월화수목금토일]\\)/.test(document.body.innerText)""", timeout=15000)
        day = latest_public_date(await page.locator("body").inner_text(), today=datetime.now(KST).date())
        diagnostic["date"] = day.isoformat()
        diagnostic["dateSelection"] = "public-home"
        return day
    finally:
        await page.close()


def rank_request_matches(request, category: str, day: date, page_number: int) -> bool:
    try:
        url = urlsplit(request.url)
        if (url.scheme != "https" or url.hostname != "datalab.naver.com" or url.path != RANK_RESPONSE_PATH
                or request.method != "POST" or request.resource_type not in {"xhr", "fetch"}):
            return False
        params = request.post_data_json
        expected = {"cid": category, "timeUnit": "date", "startDate": day.isoformat(),
                    "endDate": day.isoformat(), "page": str(page_number), "count": "20"}
        return isinstance(params, dict) and set(params) == set(expected) and all(str(params[key]) == value for key, value in expected.items())
    except (ValueError, TypeError, AttributeError):
        return False


def parse_response_rows(payload, first_rank: int) -> list[dict]:
    """Read only public ranks from the observed UI response, never its tokens."""
    rows = payload.get("ranks") if isinstance(payload, dict) else None
    if rows == [] and first_rank == 1:
        raise RankDataUnavailable("요청 날짜의 공개 순위 목록이 아직 비어 있습니다.")
    if not isinstance(rows, list) or len(rows) != 20:
        raise RankCollectionError("요청 날짜의 공개 순위 응답 20개를 확인하지 못했습니다.")
    clean = []
    for expected, row in enumerate(rows, start=first_rank):
        if not isinstance(row, dict) or isinstance(row.get("rank"), bool):
            raise RankCollectionError("공개 순위 응답 구조가 변경되었습니다.")
        try:
            rank = int(row.get("rank"))
        except (ValueError, TypeError):
            raise RankCollectionError("공개 순위 응답 구조가 변경되었습니다.") from None
        keyword = row.get("keyword")
        if rank != expected or not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 200:
            raise RankCollectionError("공개 순위 응답의 순서나 검색어가 올바르지 않습니다.")
        clean.append({"rank": rank, "keyword": keyword.strip()})
    return clean


async def observed_rank_action(page, action, category: str, day: date, page_number: int, diagnostic: dict):
    # Observe the actual normal-button response instead of assuming that a new
    # heading/cid means an old first-page keyword list has finished rendering.
    async with page.expect_response(lambda response: rank_request_matches(response.request, category, day, page_number), timeout=25000) as pending:
        await action()
    response = await pending.value
    if response.status != 200:
        raise RankCollectionError(f"네이버 공개 순위 요청이 실패했습니다 (HTTP {response.status}).")
    diagnostic["lastRankRequest"] = {"cid": category, "startDate": day.isoformat(), "endDate": day.isoformat(), "page": page_number, "count": 20}
    try:
        payload = await response.json()
    except Exception:
        raise RankCollectionError("공개 순위 응답을 확인하지 못했습니다.") from None
    metadata = {key: value for key in ("date", "datetime", "range", "statusCode", "returnCode")
                if isinstance(payload, dict) and ((value := payload.get(key)) is None or isinstance(value, (str, int, float, bool)))}
    diagnostic["lastRankResponseMetadata"] = metadata
    return parse_response_rows(payload, (page_number - 1) * 20 + 1)


async def wait_for_matching_dom(page, rows: list[dict], category: str):
    await page.wait_for_function("""expected => {
        const anchors = [...document.querySelectorAll('.rank_top1000_list a.link_text')];
        if (anchors.length !== expected.rows.length) return false;
        return anchors.every((el, index) => {
            const row = expected.rows[index];
            const rank = Number(el.querySelector('.rank_top1000_num')?.textContent.trim());
            let url;
            try { url = new URL(el.getAttribute('href'), document.baseURI); }
            catch { return false; }
            return rank === row.rank && url.searchParams.get('keyword') === row.keyword
                && url.searchParams.get('cid') === expected.category
                && el.textContent.trim().slice(String(rank).length).trim() === row.keyword;
        });
    }""", arg={"rows": rows, "category": category}, timeout=15000)


async def read_current_snapshot(context, read_day, day: date | None, diagnostic: dict, *, today: date | None = None):
    if day is not None:
        return day, await read_day(day, "current-snapshot"), "explicit"
    yesterday = (today or datetime.now(KST).date()) - timedelta(days=1)
    diagnostic["date"] = yesterday.isoformat()
    try:
        return yesterday, await read_day(yesterday, "current-snapshot"), "public-ui-latest"
    except RankDataUnavailable:
        # Only an exact matching HTTP-200 empty rank response permits one
        # bounded fallback. Authentication, 403/429, timeout and changed schema
        # stop the run; none of those is treated as permission to try again.
        diagnostic["unavailableDate"] = yesterday.isoformat()
        observed_day = await discover_latest_date(context, diagnostic)
        if observed_day >= yesterday:
            raise RankDataUnavailable("공개 홈의 최신 날짜도 요청 날짜와 같아 재시도하지 않습니다.")
        await asyncio.sleep(DATE_INTERVAL_SECONDS)
        current = await read_day(observed_day, "current-snapshot")
        return observed_day, current, "public-home"


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
    diagnostic["step"] = "submit-query"
    response_rows = await observed_rank_action(page, form.locator(".btn_submit").click, category, day, 1, diagnostic)
    await heading.filter(has_text=expected_range).wait_for(timeout=25000)
    if CATEGORIES[category] not in (await heading.inner_text()):
        raise RankCollectionError("조회 결과의 분야가 선택한 분야와 다릅니다.")


    entries = []
    for page_index in range(5):
        diagnostic["step"] = f"read-rank-page-{page_index + 1}"
        expected_rank = page_index * 20 + 1
        await wait_for_matching_dom(page, response_rows, category)
        if expected_range not in " ".join((await heading.inner_text()).split()):
            raise RankCollectionError("페이지를 넘기는 동안 조회 날짜가 바뀌었습니다.")
        raw = await page.locator(".rank_top1000_list a.link_text").evaluate_all("""nodes => nodes.map(el => ({
            rank: el.querySelector('.rank_top1000_num')?.textContent.trim(),
            href: el.getAttribute('href'), text: el.textContent.trim()
        }))""")
        parsed = parse_rows(raw, category, expected_rank)
        if parsed != response_rows:
            raise RankCollectionError("공개 응답과 화면의 순위 목록이 다릅니다. 이전 목록을 저장하지 않습니다.")
        entries.extend(parsed)
        diagnostic["rankResponseConfirmed"] = True
        if page_index < 4:
            await asyncio.sleep(PAGE_INTERVAL_SECONDS)
            response_rows = await observed_rank_action(page, page.locator(".rank_top1000 .btn_page_next").click, category, day, page_index + 2, diagnostic)
    result = {"category": category, "date": day.isoformat(), "sourceUrl": SOURCE_URL, "entries": entries}
    validate_snapshot(result, expected_count=SNAPSHOT_SIZE)
    return result

async def collect_pair(category: str, day: date | None, diagnostic: dict | None = None) -> dict:
    from playwright.async_api import async_playwright
    diagnostic = diagnostic if diagnostic is not None else {}
    diagnostic.update({"stage": "browser-launch", "category": category, "date": day.isoformat() if day else None})
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

            day, current, date_selection = await read_current_snapshot(context, read_day, day, diagnostic)
            diagnostic["step"] = "date-request-interval"
            await asyncio.sleep(DATE_INTERVAL_SECONDS)
            previous = await read_day(day - timedelta(days=7), "previous-snapshot")
            diagnostic["stage"] = "complete"
            return {"current": current, "previous": previous, "dateSelection": date_selection,
                    "observedAt": datetime.now(KST).isoformat(timespec="seconds")}
        finally:
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 쇼핑인사이트 공개 인기검색어 일별 순위 비교 자료 수집")
    parser.add_argument("--category", choices=sorted(CATEGORIES), default="50000023")
    parser.add_argument("--date", help="조회일 YYYY-MM-DD. 생략하면 어제를 확인하고 빈 순위일 때만 공개 홈의 최신 표시일 사용")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    diagnostic = {"stage": "input-validation"}
    try:
        day = parse_collection_date(args.date) if args.date else None
        payload = asyncio.run(asyncio.wait_for(collect_pair(args.category, day, diagnostic), timeout=180))
        diagnostic["stage"] = "save-output"
        output = args.output.expanduser().absolute()
        if not output.parent.is_dir():
            raise ValueError("저장 폴더가 없습니다. 외장 드라이브 연결을 확인해 주세요.")
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, output)
        print(json.dumps({"ok": True, "category": args.category, "date": payload['current']['date'], "count": SNAPSHOT_SIZE,
                          "dateSelection": payload["dateSelection"]}, ensure_ascii=False))
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
