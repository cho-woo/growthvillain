"""Bounded exact-ID public checks; explicit normal no-result differs from failure."""
import argparse
import asyncio
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit

from ad_lifecycle import parse_delivery
from catalog import atomic_json, now
from crawler import async_playwright, check_access, CollectionBlocked, get_visible_cards

MISSING_AD = re.compile(
    r'^(?:이\s*광고(?:는|를)\s*(?:더\s*이상\s*)?(?:이용할|사용할|찾을)\s*수\s*없습니다'
    r'|(?:해당\s*)?광고를\s*찾을\s*수\s*없습니다|검색\s*결과가\s*없습니다|결과\s*0개'
    r'|This ad (?:is no longer available|is not available|isn[’\']t available)'
    r'|Ad not found|No ads found|No results found)[.!。]?$', re.I)
ERROR_NOTICE = re.compile(
    r'temporarily|too many requests|something went wrong|try again|security check|confirm you are human'
    r'|log in to|login required|일시적|차단|문제가 발생|다시 시도|로그인(?:이 필요|하여|해야)|로봇이 아님', re.I)
LIBRARY_ID = re.compile(r'(?:라이브러리 ID|Library ID)[:\s]+(\d{5,40})', re.I)


def not_found_evidence(ad_id, *, url, http_status, text, ready_state='complete', busy=False):
    """True only for a complete exact-ID response with an intentional empty UI.

    A generic missing endpoint (404), generic unavailable-content screen,
    another ad card, redirected search or active spinner cannot end an ad.
    """
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        exact_page = (parsed.scheme == 'https' and parsed.netloc in ('www.facebook.com', 'facebook.com')
                      and parsed.path.rstrip('/') == '/ads/library'
                      and query.get('id') == [ad_id] and not query.get('q'))
    except (TypeError, ValueError):
        return False
    if not exact_page or http_status != 200 or ready_state != 'complete' or busy:
        return False
    if not text or LIBRARY_ID.search(text) or ERROR_NOTICE.search(text):
        return False
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    has_shell = any(re.fullmatch(r'(?:Meta\s*)?Ad Library|광고 라이브러리', line, re.I) for line in lines)
    return has_shell and any(MISSING_AD.fullmatch(line) for line in lines)


async def inspect_ad(page, ad_id):
    item = {'id': ad_id, 'checkedAt': now(), 'outcome': 'unavailable'}
    network_failures = []

    def public_request(request):
        try:
            host = urlsplit(request.url).hostname or ''
            return request.resource_type in ('xhr', 'fetch') and (host == 'facebook.com' or host.endswith('.facebook.com'))
        except (AttributeError, ValueError):
            return False

    def observe_response(response):
        if public_request(response.request) and response.status >= 400:
            network_failures.append(response.status)

    def observe_failure(request):
        if public_request(request):
            network_failures.append(0)

    page.on('response', observe_response)
    page.on('requestfailed', observe_failure)
    try:
        response = await page.goto('https://www.facebook.com/ads/library/?id=' + ad_id,
                                   wait_until='domcontentloaded', timeout=30000)
        initial_status = response.status if response else None
        if initial_status == 429:
            raise CollectionBlocked('rate limited')
        if initial_status is None or initial_status >= 500 or initial_status == 404:
            return item
        try:
            await page.wait_for_function(r"""() => {
                const text = document.body?.innerText || '';
                return /(?:라이브러리 ID|Library ID)[:\s]+\d{5,40}/i.test(text) ||
                    /광고를 찾을 수 없습니다|검색 결과가 없습니다|결과\s*0개|no ads found|no results found|ad not found|this ad (?:is no longer available|is not available|isn.t available)/i.test(text) ||
                    /temporarily blocked|일시적으로 차단|too many requests|confirm you are human|security check/i.test(text);
            }""", timeout=12000)
        except Exception:
            pass
        await check_access(page)
        for card in await get_visible_cards(page):
            text = await card.inner_text()
            if set(LIBRARY_ID.findall(text)) == {ad_id}:
                evidence = parse_delivery(text)
                # Exact ID existence is confirmed even if its delivery label
                # is absent; the merger can withdraw an earlier absence estimate.
                item.update(evidence, outcome='confirmed')
                return item
        # A finished document alone does not prove the public SPA's request
        # completed. Failed XHR/fetch must never become an empty-result inference.
        await page.wait_for_load_state('networkidle', timeout=3000)
        if network_failures:
            if any(status in (401, 403, 429) for status in network_failures):
                item['outcome'] = 'blocked'
            return item
        text = await page.inner_text('body')
        state = await page.evaluate("""() => ({readyState: document.readyState,
            busy: [...document.querySelectorAll('[aria-busy="true"],[role="progressbar"]')]
                .some(el => el.getClientRects().length > 0)})""")
        if not_found_evidence(ad_id, url=page.url, http_status=initial_status, text=text,
                              ready_state=state['readyState'], busy=state['busy']):
            # Ensure the no-result screen remains after the initial render.
            await asyncio.sleep(.5)
            stable_text = await page.inner_text('body')
            stable = await page.evaluate("""() => ({readyState: document.readyState,
                busy: [...document.querySelectorAll('[aria-busy="true"],[role="progressbar"]')]
                    .some(el => el.getClientRects().length > 0)})""")
            if not network_failures and not_found_evidence(ad_id, url=page.url, http_status=initial_status, text=stable_text,
                                  ready_state=stable['readyState'], busy=stable['busy']):
                item.update(outcome='not_found', evidence='exact_id_explicit_no_result')
        elif initial_status in (401, 403):
            item['outcome'] = 'blocked'
    except CollectionBlocked:
        item['outcome'] = 'blocked'
    except Exception:
        item['outcome'] = 'unavailable'
    finally:
        page.remove_listener('response', observe_response)
        page.remove_listener('requestfailed', observe_failure)
        item['checkedAt'] = now()
    return item


async def check(ids, destination):
    observations = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--lang=ko-KR'])
        try:
            context = await browser.new_context(locale='ko-KR')
            page = await context.new_page()
            deadline = time.monotonic() + 180
            for ad_id in ids:
                if time.monotonic() >= deadline:
                    break
                try:
                    item = await asyncio.wait_for(inspect_ad(page, ad_id), timeout=min(45, deadline-time.monotonic()))
                except asyncio.TimeoutError:
                    item = {'id': ad_id, 'checkedAt': now(), 'outcome': 'unavailable'}
                observations.append(item)
                if item['outcome'] == 'blocked':
                    break
                await asyncio.sleep(2)
        finally:
            await browser.close()
    atomic_json(destination, {'checkedAt': now(), 'observations': observations})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ids = args.ids.split(',')
    if not 1 <= len(ids) <= 10 or any(not re.fullmatch(r'\d{5,40}', i) for i in ids):
        parser.error('1–10 valid ad IDs required')
    asyncio.run(check(ids, args.output))


if __name__ == '__main__':
    main()
