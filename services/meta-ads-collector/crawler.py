"""
Meta Ads Library Crawler
========================
메타 광고 라이브러리에서 키워드 검색 후 광고 레퍼런스 카드를 수집합니다.

기능:
- 키워드 입력 → "모든 광고" 선택 → 검색
- 카드별 텍스트, 이미지, 동영상, 랜딩 URL 수집
- 동일 랜딩 도메인 광고만 필터링 (옵션)
- 10개씩 끊어서 진행, 사용자가 계속 여부 결정
- 미디어 파일은 output/<run_id>/media/ 폴더에 다운로드

사용:
    # 대화형
    python meta_ads_crawler.py

    # 비대화형 (--keyword 가 주어지면 input() 스킵하고 자동 진행)
    python meta_ads_crawler.py --keyword "마스크팩" --batch 20 --total 60 --headless
    python meta_ads_crawler.py --keyword "메디큐브" --domain themedicube --total 40

필요:
    pip install playwright requests
    playwright install chromium
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, urlencode


import requests

# Playwright는 실제 크롤링 시점에만 import (--help 가벼움 + 워커 환경에서 미설치여도 일단 import 가능)
try:
    from playwright.async_api import (  # type: ignore
        async_playwright,
        Page,
        ElementHandle,
        TimeoutError as PlaywrightTimeoutError,
    )
except ImportError:  # pragma: no cover
    async_playwright = None  # type: ignore[assignment]
    Page = ElementHandle = object  # type: ignore[assignment,misc]
    class PlaywrightTimeoutError(Exception):  # type: ignore[no-redef]
        pass


# ---------- 설정 ----------
BASE_URL = "https://www.facebook.com/ads/library/"
DEFAULT_BATCH_SIZE = 10
HEADLESS = False  # 처음엔 False로 두고 동작 확인 후 True 로 바꿔도 됨
NAV_TIMEOUT_MS = 60_000
SCROLL_WAIT_MS = 1500
CARD_WAIT_MS = 8000


# ---------- 유틸 ----------
def safe_filename(s: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^\w\-_. ]", "_", s)
    s = s.strip().replace(" ", "_")
    return s[:maxlen] or "untitled"


def extract_real_url(fb_redirect_url: str) -> str:
    """l.facebook.com/l.php?u=<encoded> 형태에서 실제 URL 추출."""
    if not fb_redirect_url:
        return ""
    try:
        parsed = urlparse(fb_redirect_url)
        if "facebook.com" in parsed.netloc and parsed.path.endswith("/l.php"):
            q = parse_qs(parsed.query)
            if "u" in q and q["u"]:
                return unquote(q["u"][0])
        return fb_redirect_url
    except Exception:
        return fb_redirect_url


def get_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        # www. 떼고 비교
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


class CollectionBlocked(RuntimeError):
    pass


def allowed_media_url(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        return parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443) and any(host == domain or host.endswith('.' + domain) for domain in ('fbcdn.net', 'facebook.com', 'fbsbx.com'))
    except ValueError:
        return False


def download_media(url, dest_path, headers=None):
    # Public Meta CDN media only. Never follow redirects to arbitrary hosts.
    if not allowed_media_url(url):
        return False
    try:
        for _ in range(4):
            with requests.get(url, stream=True, timeout=(15, 45), allow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = response.headers.get('Location', '')
                    if not allowed_media_url(url):
                        return False
                    continue
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').split(';')[0]
                if not (content_type.startswith('image/') or content_type.startswith('video/')):
                    return False
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with dest_path.open('wb') as output:
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 100 * 1024 * 1024:
                            raise ValueError('Media exceeds 100MB')
                        output.write(chunk)
                return size > 0
    except Exception:
        if dest_path.exists():
            dest_path.unlink()
        print('[!] A media download failed; no remote URL is published.')
    return False


async def check_access(page):
    url = page.url.lower()
    if any(part in url for part in ('/login', '/checkpoint', '/captcha', '/challenge')):
        raise CollectionBlocked('Meta login or verification is required. Collection stopped.')
    for selector in ('input[type="password"]', 'iframe[src*="captcha"]', '[data-testid="captcha"]'):
        for element in await page.query_selector_all(selector):
            if await element.is_visible():
                raise CollectionBlocked('Meta login or verification is required. Collection stopped.')
    body = (await page.inner_text('body')).lower()
    for marker in ('you’re temporarily blocked', "you're temporarily blocked", '일시적으로 차단', 'too many requests', 'confirm you are human', '로봇이 아님을', 'security check required'):
        if marker in body:
            raise CollectionBlocked('Meta blocked this request. Collection stopped; no bypass is attempted.')


async def setup_search(page, keyword, diagnostic_path=None):
    url = BASE_URL + '?' + urlencode({'active_status': 'all', 'ad_type': 'all', 'country': 'KR', 'is_targeted_country': 'false', 'media_type': 'all', 'q': keyword, 'search_type': 'keyword_unordered'})
    response = await page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
    initial_status = response.status if response else None
    diagnostic = {'initialStatus': initial_status, 'outcome': 'waiting', 'adCount': 0}
    # The document's initial HTTP status can be 403 while the public SPA still
    # loads real ad results. Judge the rendered outcome; never retry or bypass a gate.
    try:
        if initial_status == 429:
            raise CollectionBlocked('Meta rate limit reached. Collection stopped.')
        try:
            await page.wait_for_function(r"""() => {
                const text = document.body?.innerText || '';
                return /(?:라이브러리 ID|Library ID)[:\s]+\d{5,40}/i.test(text) ||
                    /결과\s*0개|검색 결과가 없습니다|광고를 찾을 수 없습니다|no ads found|no results found/i.test(text) ||
                    /temporarily blocked|일시적으로 차단|too many requests|confirm you are human|로봇이 아님을|security check required/i.test(text) ||
                    /\/(login|checkpoint|captcha|challenge)(\/|\?|$)/i.test(location.href) ||
                    [...document.querySelectorAll('input[type="password"],iframe[src*="captcha"]')].some(el => el.getClientRects().length);
            }""", timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        await check_access(page)
        text = await page.inner_text('body')
        ad_ids = set(re.findall(r'(?:라이브러리 ID|Library ID)[:\s]+(\d{5,40})', text, re.I))
        if ad_ids:
            diagnostic.update(outcome='ready', adCount=len(ad_ids))
            print(f'[*] Public ad results ready: {len(ad_ids)} (initial HTTP {initial_status})', flush=True)
            return
        if re.search(r'결과\s*0개|검색 결과가 없습니다|광고를 찾을 수 없습니다|no ads found|no results found', text, re.I):
            diagnostic['outcome'] = 'empty'
            raise RuntimeError('No ads found for this search.')
        if initial_status in (401, 403):
            raise CollectionBlocked(f'HTTP {initial_status}; no public ad results appeared before timeout.')
        diagnostic['outcome'] = 'timeout'
        raise RuntimeError('Ad results did not finish loading before timeout.')
    except CollectionBlocked:
        diagnostic['outcome'] = 'blocked'
        raise
    finally:
        if diagnostic_path:
            # Only status/counts, never account data, page HTML, cookies or headers.
            Path(diagnostic_path).write_text(json.dumps(diagnostic, indent=2), encoding='utf-8')


async def extract_card_data(card: ElementHandle, page: Page) -> dict:
    """카드 하나에서 텍스트/이미지/동영상/랜딩URL 추출."""
    data = {
        "library_id": "",
        "advertiser": "",
        "advertiser_url": "",
        "start_date": "",
        "platforms_raw": "",
        "ad_text": "",
        "cta_headline": "",   # "[품절임박] 이 링크에서만..." 류
        "cta_label": "",      # "Shop Now"
        "landing_url_raw": "",
        "landing_url": "",
        "landing_domain": "",
        "image_urls": [],
        "video_urls": [],
        "video_poster_urls": [],
        # 카드 안 모든 페이지명 (advertiser 외 인플루언서·공식브랜드 동시 표시 대응)
        "secondary_pages": [],
        # "X 페이지는 Y와 함께합니다" 파트너십 메타데이터에서 잡힌 Y
        "partner_with": "",
    }

    # 라이브러리 ID
    try:
        txt = await card.inner_text()
    except Exception:
        txt = ""

    m = re.search(r"라이브러리 ID[:\s]+(\d+)", txt)
    if not m:
        m = re.search(r"Library ID[:\s]+(\d+)", txt)
    if m:
        data["library_id"] = m.group(1)

    from ad_lifecycle import parse_delivery
    data.update(parse_delivery(txt))

    # 게재 시작일 - 한국어 우선 ("2025. 7. 14.에 게재 시작함"),
    # 그 다음 영문 ("Started running on Jul 14, 2025") 폴백.
    # ※ 기존 패턴은 너무 관대해서 library_id 끝자리("…100121")를 잘못 잡았으므로
    #   날짜 직전이 라인 시작이거나 "."/공백 같은 경계여야 매칭.
    m = re.search(
        r"(?:^|[^\d])(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*에\s*게재\s*시작",
        txt,
    )
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        data["start_date"] = f"{y}-{mo}-{d}"
    else:
        m = re.search(
            r"Started running on\s+([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", txt
        )
        if m:
            data["start_date"] = m.group(1).strip()

    m = re.search(r"플랫폼\s*([^\n]+)", txt)
    if m:
        data["platforms_raw"] = m.group(1).strip()

    # 카드 안의 모든 페이지 링크 텍스트 (메인 advertiser 포함, 중복 제거)
    # 메디큐브가 메인이 아니어도 secondary로 노출되는 경우를 잡기 위함.
    try:
        all_anchors = await card.query_selector_all('a[href*="facebook.com/"][target="_blank"]')
        seen_pages: set = set()
        for a in all_anchors:
            try:
                href = await a.get_attribute("href") or ""
            except Exception:
                continue
            # 외부 리다이렉트 / 광고 라이브러리 자체 링크는 제외
            if "/l.php" in href or "ads/library" in href:
                continue
            try:
                text = (await a.inner_text() or "").strip()
            except Exception:
                continue
            # 너무 길거나 줄바꿈 포함은 페이지명이 아닐 가능성
            if not text or len(text) > 80 or "\n" in text:
                continue
            if not data["advertiser"]:
                data["advertiser"] = text
                data["advertiser_url"] = href
            key = text.lower()
            if key in seen_pages:
                continue
            seen_pages.add(key)
            data["secondary_pages"].append(text)
    except Exception:
        pass

    # 파트너십 텍스트: "이유정 페이지는 메디큐브와 함께합니다" / "…과 함께합니다"
    try:
        m = re.search(
            r"([^\n]{1,40}?)\s*페이지는\s+([^\n]{1,40}?)(?:와|과)\s*함께(?:합니다)?",
            txt,
        )
        if m:
            partner = m.group(2).strip().rstrip(".").rstrip()
            if partner:
                data["partner_with"] = partner
    except Exception:
        pass

    # 광고 본문 텍스트 (광고주명 아래 white-space:pre-wrap 영역)
    try:
        body = await card.query_selector('div[style*="white-space: pre-wrap"]')
        if body:
            data["ad_text"] = (await body.inner_text()).strip()
    except Exception:
        pass

    # 이미지들 (광고주 프로필 썸네일 제외 - 60x60 짜리)
    try:
        imgs = await card.query_selector_all("img")
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if not src:
                continue
            # 프로필 썸네일(_s60x60_tt6 등) 스킵
            if "s60x60" in src or "p60x60" in src:
                continue
            if src not in data["image_urls"]:
                data["image_urls"].append(src)
    except Exception:
        pass

    # 비디오
    try:
        videos = await card.query_selector_all("video")
        for v in videos:
            candidates = [await v.get_attribute("src") or ""]
            candidates.append(await v.evaluate("video => video.currentSrc || ''"))
            for source in await v.query_selector_all("source[src]"):
                candidates.append(await source.get_attribute("src") or "")
            src = next((url for url in candidates if allowed_media_url(url)), "")
            poster = await v.get_attribute("poster") or ""
            if src and src not in data["video_urls"]:
                data["video_urls"].append(src)
            if poster and poster not in data["video_poster_urls"]:
                data["video_poster_urls"].append(poster)
    except Exception:
        pass

    # 랜딩 페이지 링크 + CTA
    try:
        # 카드 맨 아래쪽 외부링크 (l.facebook.com/l.php 로 리다이렉트)
        landing_anchors = await card.query_selector_all('a[href*="l.facebook.com/l.php"], a[href*="l.php?u="]')
        # 광고주 페이지 링크는 facebook.com/<id>/ 이므로 제외됨
        if landing_anchors:
            # Partnership headers can link to an influencer's Instagram profile.
            # The final external link is the product CTA below the ad creative.
            a = landing_anchors[-1]
            href = await a.get_attribute("href") or ""
            data["landing_url_raw"] = href
            data["landing_url"] = extract_real_url(href)
            data["landing_domain"] = get_domain(data["landing_url"])

            # 그 안에서 헤드라인/CTA 라벨 추출
            try:
                inner = await a.inner_text()
                lines = [ln.strip() for ln in inner.split("\n") if ln.strip()]
                if lines:
                    # 보통 [할인문구] 가 헤드라인, 마지막 짧은 게 CTA 라벨
                    data["cta_headline"] = lines[0]
                    if len(lines) > 1:
                        data["cta_label"] = lines[-1]
            except Exception:
                pass
    except Exception:
        pass

    return data


async def get_visible_cards(page: Page):
    """광고 카드 노드 리스트. 라이브러리 ID 텍스트 기준으로 카드 컨테이너를 찾음."""
    # 라이브러리 ID 텍스트가 들어있는 가장 가까운 카드 컨테이너 탐색
    # 카드는 보통 width 가 일정한 div.xh8yej3 계층에 있음.
    cards = await page.evaluate(r"""
        () => {
            const out = [];
            const seen = new Set();
            const all = document.querySelectorAll('div');
            for (const el of all) {
                const t = el.innerText || '';
                if (!t.includes('라이브러리 ID') && !t.includes('Library ID')) continue;
                // 광고 카드는 보통 텍스트가 너무 짧지도 너무 길지도 않음
                if (t.length < 30 || t.length > 5000) continue;
                // 카드 컨테이너: 가장 가까운 큰 박스
                let node = el;
                let depth = 0;
                while (node && depth < 8) {
                    if (node.offsetWidth > 280 && node.offsetWidth < 700 &&
                        node.offsetHeight > 200) break;
                    node = node.parentElement;
                    depth++;
                }
                // Exhausting the ancestor walk is not a matching card. Never
                // let a page wrapper consume this ID before its actual DIV.
                if (!node || node.tagName !== 'DIV' ||
                    !(node.offsetWidth > 280 && node.offsetWidth < 700 && node.offsetHeight > 200)) continue;
                const ids = [...new Set((node.innerText || '').match(/(?:라이브러리 ID|Library ID)[:\s]+\d+/g) || [])]
                    .map(text => text.match(/\d+$/)[0]);
                if (new Set(ids).size !== 1) continue;
                // 중복 제거 - 같은 카드 안에 ID 텍스트가 여러개 잡힐 수 있어서
                const key = ids[0];
                if (seen.has(key)) continue;
                seen.add(key);
                // 식별용 data 속성 부여
                if (!node.dataset.crawlId) {
                    node.dataset.crawlId = 'card_' + Math.random().toString(36).slice(2, 10);
                }
                out.push(node.dataset.crawlId);
            }
            return out;
        }
    """)
    handles = []
    for cid in cards:
        h = await page.query_selector(f'div[data-crawl-id="{cid}"]')
        if h:
            handles.append(h)
    return handles


async def scroll_until_enough(page: Page, target_count: int, already_seen_ids: set, max_scrolls: int = None):
    """무한 스크롤. 새로운 카드가 target_count 만큼 모일 때까지 스크롤."""
    # 배치 크기에 비례해서 스크롤 한도 조정 (10개당 약 8회 스크롤, 최소 40 최대 200)
    if max_scrolls is None:
        max_scrolls = max(40, min(200, target_count * 8))
    last_h = 0
    same_h_count = 0
    for i in range(max_scrolls):
        await check_access(page)
        cards = await get_visible_cards(page)
        new_ids = set()
        for c in cards:
            # 임시로 library_id 만 빠르게 추출해서 중복 체크
            try:
                txt = await c.inner_text()
            except Exception:
                continue
            m = re.search(r"라이브러리 ID[:\s]+(\d+)", txt) or re.search(r"Library ID[:\s]+(\d+)", txt)
            if m and m.group(1) not in already_seen_ids:
                new_ids.add(m.group(1))
        if len(new_ids) >= target_count:
            return
        # 스크롤
        await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5);")
        await asyncio.sleep(SCROLL_WAIT_MS / 1000)
        h = await page.evaluate("document.body.scrollHeight")
        if h == last_h:
            same_h_count += 1
            if same_h_count >= 3:
                print("  [*] 더 이상 새 결과가 로드되지 않습니다.")
                return
        else:
            same_h_count = 0
            last_h = h


def prompt_continue() -> bool:
    print("\n" + "=" * 60)
    ans = input("계속 다음 10개를 가져올까요? [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def prompt_filter_domain(domains_seen: dict) -> str:
    """수집된 카드들의 랜딩 도메인 중 어느 도메인으로 필터링할지 물음."""
    print("\n[*] 수집된 랜딩 도메인:")
    items = sorted(domains_seen.items(), key=lambda x: -x[1])
    for i, (d, n) in enumerate(items, 1):
        print(f"  {i}. {d}  ({n}건)")
    print("  0. 필터링 안 함 (전체 저장)")
    ans = input("필터링할 도메인 번호 입력 [기본 0]: ").strip()
    if not ans or ans == "0":
        return ""
    try:
        idx = int(ans) - 1
        return items[idx][0]
    except Exception:
        return ""


# ---------- 메인 ----------
async def run(
    keyword: str,
    batch_size: int,
    target_domain: str,
    run_dir: Path,
    *,
    total_target: int | None = None,
    auto: bool = False,
    headless: bool | None = None,
    browser_channel: str = 'chromium',
):
    """크롤링 본체.

    total_target: 채워지면 그 개수 도달 시 자동 종료. None이면 대화형 prompt_continue.
    auto: True면 첫 배치 후 도메인 필터 질문도 스킵.
    headless: 전역 HEADLESS 대신 명시적 지정.
    """
    media_dir = run_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    cards_jsonl = run_dir / "cards.jsonl"

    is_headless = HEADLESS if headless is None else headless

    if async_playwright is None:
        raise RuntimeError("Playwright is not installed. Run setup first.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel=browser_channel, headless=is_headless, args=['--lang=ko-KR'])
        context = await browser.new_context(locale="ko-KR", viewport={"width": 1440, "height": 960})
        page = await context.new_page()
        page.set_default_timeout(NAV_TIMEOUT_MS)

        await setup_search(page, keyword, run_dir / 'access-diagnostic.json')

        seen_ids: set = set()
        domains_seen: dict = {}
        total_saved = 0
        batch_num = 0

        while True:
            await check_access(page)
            batch_num += 1
            print(f"\n========== 배치 #{batch_num} ==========")

            # 카드 충분히 로드될 때까지 스크롤
            await scroll_until_enough(page, batch_size, seen_ids)
            cards = await get_visible_cards(page)
            print(f"[*] 화면에 잡힌 카드: {len(cards)}개 (누적 처리: {len(seen_ids)}개)")

            collected_this_batch = 0
            examined_this_batch = 0
            for card in cards:
                if collected_this_batch >= batch_size or (total_target is not None and total_saved >= total_target):
                    break

                try:
                    data = await extract_card_data(card, page)
                except Exception as e:
                    print(f"  [!] 카드 추출 실패: {e}")
                    continue

                lib_id = data["library_id"]
                if not re.fullmatch(r"\d{5,40}", lib_id) or lib_id in seen_ids:
                    continue
                seen_ids.add(lib_id)
                examined_this_batch += 1

                # 도메인 필터 (부분 일치: 'themedicube' 입력하면 'themedicube.co.kr', 'shop.themedicube.com' 모두 매칭)
                dom = data["landing_domain"]
                if dom:
                    domains_seen[dom] = domains_seen.get(dom, 0) + 1
                if target_domain and not (dom == target_domain or dom.endswith("." + target_domain)):
                    continue

                # 미디어 다운로드
                card_media_dir = media_dir / lib_id
                saved_images, saved_videos, saved_posters = [], [], []

                for idx, img_url in enumerate(data["image_urls"], 1):
                    ext = ".jpg"
                    if ".png" in img_url.lower():
                        ext = ".png"
                    elif ".webp" in img_url.lower():
                        ext = ".webp"
                    dest = card_media_dir / f"image_{idx}{ext}"
                    if download_media(img_url, dest):
                        saved_images.append(str(dest.relative_to(run_dir)))

                for idx, v_url in enumerate(data["video_urls"], 1):
                    dest = card_media_dir / f"video_{idx}.mp4"
                    if download_media(v_url, dest):
                        saved_videos.append(str(dest.relative_to(run_dir)))

                for idx, pst in enumerate(data["video_poster_urls"], 1):
                    dest = card_media_dir / f"poster_{idx}.jpg"
                    if download_media(pst, dest):
                        saved_posters.append(str(dest.relative_to(run_dir)))

                if not saved_images and not saved_videos:
                    if not saved_posters:
                        continue
                    # A saved poster is still a usable preview, but never claim
                    # that the video itself was downloaded successfully.
                    saved_images = list(saved_posters)
                    saved_posters = []
                    print("  [*] 영상 파일을 받지 못해 포스터 이미지만 저장합니다.")
                data["_saved_images"] = saved_images
                data["_saved_videos"] = saved_videos
                data["_saved_posters"] = saved_posters
                data["_keyword"] = keyword
                data["_collected_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

                with open(cards_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

                total_saved += 1
                collected_this_batch += 1
                print(
                    f"  [{total_saved:>3}] ID={lib_id} | {data['advertiser'][:20]} | "
                    f"도메인={dom or '-'} | 이미지 {len(saved_images)} 동영상 {len(saved_videos)}"
                )

            print(f"\n[*] 배치 #{batch_num} 완료: 이번에 {collected_this_batch}건 저장 / 총 {total_saved}건")

            # 목표 도달 시 자동 종료
            if total_target is not None and total_saved >= total_target:
                print(f"[*] 목표 {total_target}건 도달, 자동 종료")
                break

            # Filtered or unavailable media must not hide later search results.
            if examined_this_batch == 0:
                print("[*] 추가 스크롤 후에도 새로운 광고 ID가 없어 자동 종료")
                break

            # Fixed pacing limits request volume; no evasion or identity spoofing.
            await asyncio.sleep(4)

            # 도메인 필터링이 아직 없으면 첫 배치 후 물어볼 수도 있음 (auto면 스킵)
            if not auto and not target_domain and batch_num == 1 and domains_seen:
                ans = input("\n수집된 도메인 중 특정 도메인만 필터링할까요? [y/N]: ").strip().lower()
                if ans in ("y", "yes"):
                    target_domain = prompt_filter_domain(domains_seen)
                    if target_domain:
                        print(f"[*] 이후 배치부터 도메인='{target_domain}' 만 저장합니다.")

            # 비대화형: total_target까지 계속 / 대화형: prompt
            if total_target is not None or auto:
                continue
            if not prompt_continue():
                break

        await check_access(page)
        await browser.close()
        if total_saved == 0:
            raise RuntimeError("No usable ads collected. There may be no results, a login gate, or the page layout changed.")

        print(f"\n[완료] 총 {total_saved}건 저장")
        print(f"  - 메타데이터: {cards_jsonl}")
        print(f"  - 미디어 폴더: {media_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Meta Ads Library Crawler")
    parser.add_argument("--keyword", help="검색 키워드 (지정 시 비대화형 모드)")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"한 배치당 수집 개수 (기본 {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--domain", default="",
                        help="랜딩 도메인 필터 (부분 일치). 빈 값이면 필터 없음")
    parser.add_argument("--total", type=int, default=None,
                        help="총 수집 목표 개수 (도달 시 자동 종료). 비대화형 필수.")
    parser.add_argument("--run-id", default=None,
                        help="출력 폴더명 (기본: <timestamp>_<keyword>)")
    parser.add_argument("--output-dir", default="output", help="결과 루트 디렉토리")
    parser.add_argument("--headless", action="store_true", help="브라우저 헤드리스 모드")
    parser.add_argument("--browser-channel", choices=['chromium', 'chrome', 'msedge'], default='chromium',
                        help="실제 브라우저 엔진 (기본 chromium, 새 헤드리스 모드 지원)")
    return parser.parse_args()


def main():
    args = parse_args()

    # 비대화형: --keyword 가 주어졌을 때
    non_interactive = bool(args.keyword)

    print("=" * 60)
    print("Meta Ads Library Crawler" + (" (비대화형)" if non_interactive else ""))
    print("=" * 60)

    if non_interactive:
        keyword = args.keyword.strip()
        batch_size = max(args.batch, 1)
        dom_in = (args.domain or "").strip().lower()
    else:
        keyword = input("검색 키워드를 입력하세요: ").strip()
        if not keyword:
            print("키워드가 비어있습니다. 종료.")
            sys.exit(1)
        bs_in = input(f"배치 크기 [기본 {DEFAULT_BATCH_SIZE}]: ").strip()
        try:
            batch_size = int(bs_in) if bs_in else DEFAULT_BATCH_SIZE
        except ValueError:
            batch_size = DEFAULT_BATCH_SIZE
        dom_in = input(
            "랜딩 도메인 필터 (부분 일치 가능. 예: 'themedicube' 또는 'obge.co.kr'). 비우면 첫 배치 후 선택: "
        ).strip().lower()

    if not 1 <= len(keyword) <= 100:
        raise ValueError("Keyword length must be 1-100")
    if args.total is None or not 1 <= args.total <= 100:
        raise ValueError("Specify --total between 1 and 100")
    if args.run_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.run_id):
        raise ValueError("Invalid run ID")
    if dom_in.startswith("www."):
        dom_in = dom_in[4:]

    run_id = args.run_id or (
        datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + safe_filename(keyword, 30)
    )
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] 출력 디렉터리: {run_dir.resolve()}")
    if non_interactive:
        print(f"[*] 키워드='{keyword}' 배치={batch_size} 목표={args.total or '무제한'} "
              f"도메인='{dom_in or '(없음)'}' 헤드리스={args.headless}")

    asyncio.run(
        run(
            keyword,
            batch_size,
            dom_in,
            run_dir,
            total_target=args.total,
            auto=non_interactive,
            headless=args.headless if non_interactive else None,
            browser_channel=args.browser_channel,
        )
    )

    # 비대화형 모드에서 워커가 결과 파싱할 수 있게 마지막 줄로 run_dir 출력
    if non_interactive:
        print(f"RUN_DIR={run_dir}")


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        main()
    except CollectionBlocked:
        # A stable exit status lets the local UI distinguish an access restriction
        # from installation, no-results or page-layout errors. Never bypass it.
        print('COLLECTION_BLOCKED: Meta access restriction. Collection stopped.', file=sys.stderr)
        sys.exit(20)
