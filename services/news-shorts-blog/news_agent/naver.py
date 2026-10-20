"""Headed, local Naver publication with a human authentication checkpoint.

Credentials and the browser profile remain on the operator's computer. This
module neither solves authentication challenges nor retries a submission whose
result is unknown. Site DOM changes deliberately fail before submission.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import parse_qs, quote, urlsplit


DEFAULT_CREDENTIALS_FILE = Path(r"C:\Users\LG\Desktop\그로스빌런\pw.txt")


class PublishNotSubmitted(RuntimeError):
    """The final publish button has not been pressed."""


class PublishUncertain(RuntimeError):
    """Submission may have happened; inspect the blog before any retry."""


def _label(value: str) -> str:
    return re.sub(r"[\s_\-]", "", value).lower()


_ID_KEYS = {"id", "userid", "username", "naverid", "아이디", "네이버아이디", "계정", "네이버계정"}
_PW_KEYS = {"pw", "password", "passwd", "naverpw", "naverpassword", "비밀번호", "네이버비밀번호", "암호"}


def parse_credentials(text: str) -> tuple[str, str]:
    """Parse common Notepad layouts without including input in any error."""
    text = text.lstrip("\ufeff").strip()
    values: dict[str, str] = {}
    if text.startswith("{"):
        try:
            raw = json.loads(text)
        except (ValueError, TypeError):
            raise ValueError("계정 파일 JSON 형식을 확인하세요.") from None
        if not isinstance(raw, dict):
            raise ValueError("계정 파일에는 아이디와 비밀번호가 필요합니다.")
        values = {_label(str(key)): value for key, value in raw.items() if isinstance(value, str)}
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        for line in lines:
            match = re.match(r"^([^:=：]+)\s*[:=：]\s*(.*)$", line)
            if match:
                key = _label(match[1])
                if key in _ID_KEYS | _PW_KEYS:
                    values[key] = match[2].strip()
        if not values and len(lines) == 2:
            values = {"id": lines[0], "pw": lines[1]}
    user_ids = [value.strip() for key, value in values.items() if key in _ID_KEYS]
    passwords = [value for key, value in values.items() if key in _PW_KEYS]
    if len(user_ids) != 1 or len(passwords) != 1 or not user_ids[0] or not passwords[0]:
        raise ValueError("계정 파일에 아이디와 비밀번호를 각각 한 번 지정하세요.")
    if any(c in user_ids[0] + passwords[0] for c in "\r\n\x00"):
        raise ValueError("계정 파일 값의 형식을 확인하세요.")
    return user_ids[0], passwords[0]


def read_credentials(path: Path) -> tuple[str, str]:
    """Read only the explicitly configured local file, with Notepad encodings."""
    target = Path(path)
    if not target.exists() and target.name.lower() == "pw.txt":
        target = target.with_name("pw")
    try:
        raw = target.read_bytes()
    except OSError:
        raise ValueError("로컬 계정 파일을 읽을 수 없습니다. 브라우저에서 직접 로그인할 수 있습니다.") from None
    if len(raw) > 16_384:
        raise ValueError("계정 파일이 너무 큽니다. 아이디와 비밀번호만 지정하세요.")
    encodings = ["utf-16"] if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "cp949"]
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return parse_credentials(text)
    raise ValueError("계정 파일 인코딩을 UTF-8로 저장하세요.")


def validate_blog_id(blog_id: str) -> str:
    if not isinstance(blog_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,60}", blog_id):
        raise ValueError("올바른 네이버 블로그 ID가 필요합니다.")
    return blog_id


def editor_matches(url: str, blog_id: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "blog.naver.com":
        return False
    query = parse_qs(parsed.query)
    if parsed.path.lower() == "/postwriteform.naver":
        return query.get("blogId") == [blog_id]
    return parsed.path.rstrip("/") == f"/{blog_id}/postwrite"


def confirmed_post_url(url: str, blog_id: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"blog.naver.com", "m.blog.naver.com"}:
        return None
    match = re.fullmatch(r"/([^/]+)/([0-9]{5,})/?", parsed.path)
    if match and match[1] == blog_id:
        return f"https://blog.naver.com/{blog_id}/{match[2]}"
    query = parse_qs(parsed.query)
    if parsed.path.lower() == "/postview.naver" and query.get("blogId") == [blog_id]:
        numbers = query.get("logNo", [])
        if len(numbers) == 1 and re.fullmatch(r"[0-9]{5,}", numbers[0]):
            return f"https://blog.naver.com/{blog_id}/{numbers[0]}"
    return None


def _one_visible(locator):
    matches = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    return matches[0] if len(matches) == 1 else None


def _find_visible(scope, selectors):
    for selector in selectors:
        result = _one_visible(scope.locator(selector))
        if result is not None:
            return result
    return None


def _wait_visible(scope, selectors, timeout_seconds=5):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = _find_visible(scope, selectors)
        if result is not None:
            return result
        time.sleep(0.1)
    return None


def _editor_text(locator):
    text = locator.inner_text()
    placeholders = locator.locator(".se-placeholder")
    for index in range(placeholders.count()):
        placeholder = placeholders.nth(index).inner_text()
        if placeholder:
            text = text.replace(placeholder, "", 1)
    return text.strip()


def _normalized(text):
    return " ".join(text.split())


def _topic_label(text):
    return re.sub(r"\s|·", "", text)


def _topic_option(locator, topic):
    matches = []
    for index in range(locator.count()):
        item = locator.nth(index)
        if item.is_visible() and _topic_label(item.inner_text()) == _topic_label(topic):
            matches.append(item)
    return matches[0] if len(matches) == 1 else None


class NaverPublisher:
    def __init__(self, profile_dir: Path, credentials_file: Path | None = None,
                 browser_channel: str = "chrome", manual_timeout_seconds: int = 1800):
        self.profile_dir = Path(profile_dir)
        self.credentials_file = Path(credentials_file) if credentials_file else None
        self.browser_channel = browser_channel
        self.manual_timeout_seconds = manual_timeout_seconds
        self._playwright = None
        self._context = None
        self._page = None
        self._login_attempted = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        finally:
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            self._context = self._playwright = self._page = None
            self._login_attempted = False

    def _open(self):
        if self._page is not None and not self._page.is_closed():
            return self._page
        from playwright.sync_api import sync_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            options = {"headless": False, "locale": "ko-KR", "viewport": {"width": 1280, "height": 900}}
            if self.browser_channel != "chromium":
                options["channel"] = self.browser_channel
            self._context = self._playwright.chromium.launch_persistent_context(str(self.profile_dir), **options)
            self._context.set_default_timeout(10_000)
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            return self._page
        except Exception:
            self.close()
            raise PublishNotSubmitted("Chrome 창을 열 수 없습니다. 브라우저 설치와 프로필 사용 상태를 확인하세요.") from None

    def _editor(self, page, blog_id):
        for frame in page.frames:
            if editor_matches(frame.url, blog_id):
                title = _find_visible(frame, [
                    ".se-documentTitle [contenteditable='true']",
                    ".se-title-text [contenteditable='true']",
                    ".se-documentTitle .se-text-paragraph",
                ])
                if title is not None:
                    return frame
        return None

    def _autofill_once(self, page):
        if self._login_attempted or not self.credentials_file:
            return
        parsed = urlsplit(page.url)
        if parsed.scheme != "https" or parsed.hostname != "nid.naver.com":
            return
        self._login_attempted = True
        try:
            user_id, password = read_credentials(self.credentials_file)
        except ValueError:
            return  # Manual login remains possible; never expose file contents.
        username_input = _find_visible(page, ["input#id"])
        password_input = _find_visible(page, ["input#pw"])
        login = _find_visible(page, ["button[id='log.login']", "button.btn_login"])
        if username_input is None or password_input is None or login is None:
            return
        username_input.fill(user_id)
        password_input.fill(password)
        login.click()

    def ensure_login(self, blog_id: str, on_wait: Callable[[str], None] = lambda _: None):
        """Open the target editor; a human completes every login challenge."""
        validate_blog_id(blog_id)
        try:
            page = self._open()
            page.goto(f"https://blog.naver.com/PostWriteForm.naver?blogId={quote(blog_id)}",
                      wait_until="domcontentloaded")
            deadline = time.monotonic() + self.manual_timeout_seconds
            notified = False
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise PublishNotSubmitted("로그인 창이 닫혔습니다. 다시 실행하세요.")
                editor = self._editor(page, blog_id)
                if editor is not None:
                    on_wait("ready")
                    return page, editor
                self._autofill_once(page)
                if not notified:
                    on_wait("needs_auth")
                    notified = True
                # Human solves CAPTCHA/2FA in the visible browser. No retries,
                # challenge interaction, stealth settings, or session scraping.
                page.wait_for_timeout(1000)
            raise PublishNotSubmitted("수동 로그인·인증 대기 시간이 지났습니다. 발행하지 않았습니다.")
        except PublishNotSubmitted:
            raise
        except Exception:
            raise PublishNotSubmitted("로그인 또는 편집기를 확인하지 못했습니다. 열린 브라우저를 확인하세요.") from None

    def _select_category(self, editor, category):
        if not category:
            return
        control = _wait_visible(editor, ["button[class*='category_toggle']", "button[class*='category_select']"])
        if control is None:
            raise PublishNotSubmitted("카테고리 선택 메뉴를 확인할 수 없어 발행을 보류했습니다.")
        if control.inner_text().strip() == category:
            return
        control.click()
        options = editor.get_by_role("option", name=category, exact=True)
        option = _one_visible(options)
        if option is None:
            option = _one_visible(editor.locator("label").filter(has_text=re.compile(r"^\s*" + re.escape(category) + r"\s*$")))
        if option is None:
            raise PublishNotSubmitted("설정한 카테고리를 정확히 선택하지 못했습니다.")
        option.click()
        if control.inner_text().strip() != category:
            raise PublishNotSubmitted("발행 카테고리를 확인하지 못했습니다.")

    def _ensure_public(self, editor):
        radios = editor.get_by_role("radio", name="공개", exact=True, include_hidden=True)
        if radios.count() != 1:
            raise PublishNotSubmitted("공개 발행 설정을 정확히 확인할 수 없어 발행을 보류했습니다.")
        radio = radios.nth(0)
        if not radio.is_checked():
            if radio.is_visible():
                radio.check()
            else:
                identity = radio.get_attribute("id") or ""
                if not re.fullmatch(r"[A-Za-z0-9_-]+", identity):
                    raise PublishNotSubmitted("공개 설정의 연결된 입력 영역을 확인하지 못했습니다.")
                label = _one_visible(editor.locator(f'label[for="{identity}"]'))
                if label is None or label.inner_text().strip() != "공개":
                    raise PublishNotSubmitted("공개 설정의 연결된 선택 항목을 확인하지 못했습니다.")
                label.click()
        if not radio.is_checked():
            raise PublishNotSubmitted("공개 발행 설정을 적용하지 못했습니다.")

    def _select_topic(self, editor, topic):
        if topic is None:
            return
        if not isinstance(topic, str) or not _topic_label(topic):
            raise PublishNotSubmitted("발행 주제 분류를 올바르게 지정하세요.")
        control = _wait_visible(editor, [
            "button[class*='subject_toggle']", "button[class*='subject_select']",
            "button[class*='topic_toggle']", "button[class*='topic_select']",
        ])
        if control is None:
            raise PublishNotSubmitted("주제 분류 선택 메뉴를 확인할 수 없어 발행을 보류했습니다.")
        if _topic_label(control.inner_text()) == _topic_label(topic):
            return
        control.click()
        option = _topic_option(editor.get_by_role("option"), topic)
        if option is None:
            option = _topic_option(editor.locator("label"), topic)
        if option is None:
            raise PublishNotSubmitted("설정한 주제 분류를 정확히 선택하지 못했습니다.")
        option.click()
        if _topic_label(control.inner_text()) != _topic_label(topic):
            raise PublishNotSubmitted("발행 주제 분류를 확인하지 못했습니다.")

    def _prepare(self, article, blog_id, category, on_wait, topic=None):
        page, editor = self.ensure_login(blog_id, on_wait)
        title = _find_visible(editor, [
            ".se-documentTitle [contenteditable='true']",
            ".se-title-text [contenteditable='true']",
            ".se-documentTitle .se-text-paragraph",
        ])
        body = _find_visible(editor, [
            ".se-component.se-text [contenteditable='true']",
            ".se-component.se-text .se-text-paragraph",
        ])
        if title is None or body is None:
            raise PublishNotSubmitted("편집기 입력 영역이 변경되었거나 초안이 열려 있습니다. 발행을 보류했습니다.")
        if _editor_text(title) or _editor_text(body):
            raise PublishNotSubmitted("기존 초안이 있어 자동으로 덮어쓰지 않았습니다. 빈 글쓰기 화면에서 재개하세요.")
        title.click()
        page.keyboard.insert_text(article["title"])
        body.click()
        page.keyboard.insert_text(article["body"])
        # Read back what the actual editor accepted before opening publication.
        accepted = _normalized(editor.locator("body").inner_text())
        if (_normalized(article["title"]) != _normalized(_editor_text(title))
                or _normalized(article["body"]) not in accepted):
            raise PublishNotSubmitted("입력한 제목·본문 전체를 편집기에서 확인하지 못했습니다.")
        open_publish = _find_visible(editor, ["button[class*='publish_btn']"])
        if open_publish is None or open_publish.inner_text().strip() != "발행":
            raise PublishNotSubmitted("발행 설정 버튼을 확인할 수 없습니다.")
        open_publish.click()
        final_button = _wait_visible(editor, ["button[class*='confirm_btn']"])
        if (final_button is None or not final_button.is_enabled()
                or final_button.inner_text().strip() != "발행"):
            raise PublishNotSubmitted("최종 발행 버튼을 확인할 수 없어 발행을 보류했습니다.")
        self._select_category(editor, category)
        self._select_topic(editor, topic)
        self._ensure_public(editor)
        if not editor_matches(editor.url, blog_id):
            raise PublishNotSubmitted("발행 대상 블로그를 확인하지 못했습니다.")
        return page, final_button

    def _authentication_challenge(self, page):
        pages = [page]
        if self._context is not None:
            pages.extend(candidate for candidate in self._context.pages if candidate is not page and not candidate.is_closed())
        for frame in (frame for candidate in pages for frame in candidate.frames):
            parsed = urlsplit(frame.url)
            if parsed.scheme == "https" and parsed.hostname == "nid.naver.com":
                return True
            if parsed.hostname not in {"blog.naver.com", "m.blog.naver.com"}:
                continue
            if _find_visible(frame, [
                "input[name='captcha']", "input#captcha", "input#captcha_value",
                "input[autocomplete='one-time-code']", "iframe[src*='captcha']",
                "[role='dialog'][aria-label*='인증']", "[role='dialog'][aria-label*='보호']",
            ]) is not None:
                return True
            for phrase in ("자동입력 방지문자를 입력", "자동입력방지 문자", "추가 인증이 필요",
                           "본인 인증이 필요", "본인인증이 필요", "보안 확인이 필요"):
                if _one_visible(frame.get_by_text(phrase, exact=False)) is not None:
                    return True
        return False

    def _confirm(self, page, article, blog_id, on_wait: Callable[[str], None] = lambda _: None):
        deadline = time.monotonic() + 45
        challenge_deadline = None
        awaiting_human = False
        challenge_active = False
        while time.monotonic() < deadline:
            for frame in page.frames:
                url = confirmed_post_url(frame.url, blog_id)
                if url:
                    # Confirm rendered post content, not a notification or URL
                    # pointing to a different/older post.
                    text = frame.locator("body").inner_text()
                    anchors = frame.locator("a[href*='youtube.com']")
                    links = [anchors.nth(i).get_attribute("href") or "" for i in range(anchors.count())]
                    source_present = article["video_id"] in text or any(article["video_id"] in link for link in links)
                    if article["title"] in text and source_present:
                        if awaiting_human:
                            on_wait("ready")
                        return url
            challenge = self._authentication_challenge(page)
            if challenge:
                if not awaiting_human:
                    on_wait("needs_auth")
                    awaiting_human = True
                    challenge_deadline = time.monotonic() + self.manual_timeout_seconds
                deadline = challenge_deadline
                challenge_active = True
            elif challenge_active:
                # After manual resolution, allow normal navigation to settle.
                # Keep a fixed ceiling; a reappearing challenge cannot renew it.
                deadline = min(challenge_deadline, time.monotonic() + 45)
                challenge_active = False
            page.wait_for_timeout(500)
        raise PublishUncertain("발행 결과를 확인하지 못했습니다. 블로그를 직접 확인한 뒤 상태를 처리하세요.")

    def publish(self, article: dict, blog_id: str, category: str | None = None,
                before_submit: Callable[[], None] = lambda: None,
                on_wait: Callable[[str], None] = lambda _: None,
                topic: str | None = None) -> str:
        validate_blog_id(blog_id)
        if (not isinstance(article, dict) or not all(isinstance(article.get(key), str) and article[key].strip()
                                                    for key in ("title", "body", "video_id"))
                or not re.fullmatch(r"[A-Za-z0-9_-]{11}", article["video_id"])
                or not any(source in article["body"] for source in (
                    f"https://www.youtube.com/shorts/{article['video_id']}",
                    f"https://www.youtube.com/watch?v={article['video_id']}"))):
            raise PublishNotSubmitted("제목·본문·유튜브 출처가 있는 게시물이 필요합니다.")
        try:
            page, button = self._prepare(article, blog_id, category, on_wait, topic)
        except PublishNotSubmitted:
            raise
        except Exception:
            raise PublishNotSubmitted("편집기 준비 중 오류가 발생했습니다. 최종 발행을 누르지 않았습니다.") from None
        # The durable daily quota/receipt belongs to the caller. Its failure
        # must prevent the click and propagate unchanged.
        before_submit()
        try:
            button.click()
            return self._confirm(page, article, blog_id, on_wait)
        except PublishUncertain:
            raise
        except Exception:
            raise PublishUncertain("발행 요청 후 결과가 불명확합니다. 자동 재발행하지 마세요.") from None
