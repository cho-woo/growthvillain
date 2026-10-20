"""Windows foreground agent; collection continues during manual authentication."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import threading

from .core import GateClosed, Store, article_for, now_kst, stamp

DEFAULTS = {
    "blog_id": "wdetector", "category": "이슈", "topic": "사회·정치",
    "credentials_file": r"C:\Users\LG\Desktop\그로스빌런\pw.txt",
    "browser_channel": "chrome", "poll_seconds": 60,
    "min_publish_interval_seconds": 300, "daily_limit": 3,
    "channels": [
        {"name": "SBS 뉴스", "handle": "@SBSnews8"},
        {"name": "MBC 뉴스", "handle": "@MBCNEWS11"},
        {"name": "YTN", "handle": "@ytnnews24"},
    ],
}


def default_root():
    base = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home()/".local/share"
    return base/"GrowthvillainNewsAgent"


def read_config(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("설정은 JSON 객체여야 합니다.")
    config = {**DEFAULTS, **value}
    if not isinstance(config["blog_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,60}", config["blog_id"]):
        raise ValueError("config.json에 대상 blog_id를 입력하세요. 비밀번호는 넣지 마세요.")
    for key, low, high in (("poll_seconds", 30, 3600), ("daily_limit", 1, 3),
                           ("min_publish_interval_seconds", 0, 86400)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError(f"{key}: {low}~{high} 범위의 정수가 필요합니다.")
    if config["browser_channel"] not in ("chrome", "msedge", "chromium"):
        raise ValueError("browser_channel은 chrome, msedge, chromium 중 하나입니다.")
    if config["category"] is not None and (not isinstance(config["category"], str) or not config["category"].strip()):
        raise ValueError("category는 카테고리 이름 또는 null이어야 합니다.")
    if config["topic"] is not None and (not isinstance(config["topic"], str) or not config["topic"].strip()):
        raise ValueError("topic은 주제 분류 이름 또는 null이어야 합니다.")
    if config["credentials_file"] is not None and not isinstance(config["credentials_file"], str):
        raise ValueError("credentials_file은 파일 경로 또는 null이어야 합니다.")
    channels = config["channels"]
    if not isinstance(channels, list) or not 1 <= len(channels) <= 10:
        raise ValueError("channels는 채널 1~10개여야 합니다.")
    handles = set()
    names = set()
    from .youtube import YouTubeSource
    for channel in channels:
        if (not isinstance(channel, dict) or not isinstance(channel.get("name"), str) or
                not re.fullmatch(r"@[A-Za-z0-9_.-]+", str(channel.get("handle", "")))):
            raise ValueError("채널 이름과 공식 @handle을 확인하세요.")
        if channel["handle"].lower() in handles:
            raise ValueError("중복 채널이 있습니다.")
        if channel["name"] in names:
            raise ValueError("채널 표시 이름은 서로 달라야 합니다.")
        YouTubeSource(handle=channel["handle"], name=channel["name"], channel_id=channel.get("channel_id"))
        handles.add(channel["handle"].lower())
        names.add(channel["name"])
    return config


@contextmanager
def instance_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("에이전트 또는 로그인 창이 이미 실행 중입니다.") from error
        yield
    finally:
        handle.close()


def polling_loop(channel, config, store, stop):
    from .youtube import SourceError, YouTubeSource
    source = YouTubeSource(handle=channel["handle"], name=channel["name"], channel_id=channel.get("channel_id"))
    failures = 0
    while not stop.is_set():
        current = now_kst()
        try:
            videos = source.fetch_today(current)
            added = store.observe(videos, now_kst())
            failures = 0
            store.set_status(channel["name"], {"state": "watching", "checked_at": stamp(current),
                                              "new_candidates": added})
            if added:
                print(f"[{channel['name']}] 당일 쇼츠 {added}개 감지", flush=True)
        except Exception as error:
            failures += 1
            # SourceError is intentionally sanitized by the discovery module.
            message = str(error) if isinstance(error, SourceError) else "채널 확인 실패; 네트워크·의존성 확인 필요"
            store.set_status(channel["name"], {"state": "source_error", "checked_at": stamp(current),
                                              "message": message[:240]})
            if failures == 1:
                print(f"[{channel['name']}] 수집 연결 확인 필요. status 명령에서 확인하세요.", flush=True)
        delay = min(config["poll_seconds"] * 2 ** min(failures, 4), 900)
        stop.wait(delay)


def make_publisher(config, root):
    from .naver import NaverPublisher
    credentials = Path(config["credentials_file"]) if config.get("credentials_file") else None
    return NaverPublisher(profile_dir=root/"browser-profile", credentials_file=credentials,
                          browser_channel=config["browser_channel"])


def scan_once(config, store):
    """Refresh each channel once without starting a permanent polling loop."""
    from .youtube import SourceError, YouTubeSource

    def check(channel):
        current = now_kst()
        try:
            source = YouTubeSource(handle=channel["handle"], name=channel["name"],
                                   channel_id=channel.get("channel_id"))
            added = store.observe(source.fetch_today(current), now_kst())
            store.set_status(channel["name"], {"state": "checked", "checked_at": stamp(current),
                                              "new_candidates": added})
            print(f"[{channel['name']}] 확인 완료 · 새 당일 쇼츠 {added}개", flush=True)
            return True
        except Exception as error:
            message = str(error) if isinstance(error, SourceError) else "채널 확인 실패; 네트워크·의존성 확인 필요"
            store.set_status(channel["name"], {"state": "source_error", "checked_at": stamp(current),
                                              "message": message[:240]})
            print(f"[{channel['name']}] 확인 실패 · status에서 원인을 확인하세요.", flush=True)
            return False

    with ThreadPoolExecutor(max_workers=min(3, len(config["channels"]))) as pool:
        return sum(pool.map(check, config["channels"]))


def run(config, root, *, login_only=False, once=False):
    from .naver import PublishNotSubmitted, PublishUncertain
    store = Store(root/"agent.sqlite3")
    stop = threading.Event()
    with instance_lock(root/"agent.lock"):
        store.recover()
        publisher = make_publisher(config, root)
        threads = []

        def on_wait(reason):
            if reason == "ready":
                store.set_status("publisher", {"state": "preparing", "at": stamp(now_kst())})
                return
            store.set_status("publisher", {"state": "needs_auth", "at": stamp(now_kst()),
                                           "message": "브라우저에서 로그인·캡챠·추가 인증을 직접 완료하세요."})
            print("브라우저에서 로그인·인증을 완료하세요. 확인되면 자동으로 이어집니다.", flush=True)

        try:
            if login_only:
                publisher.ensure_login(config["blog_id"], on_wait=on_wait)
                store.set_status("publisher", {"state": "login_ready", "at": stamp(now_kst())})
                print("네이버 편집기 접근을 확인했습니다. 로그인 세션을 보관했습니다.")
                return 0
            if once:
                print("1회 게시 시작 · 당일 쇼츠 확인 후 최대 1개 · 기존 일일 한도 적용", flush=True)
                if scan_once(config, store) == 0:
                    store.set_status("publisher", {"state": "source_error", "at": stamp(now_kst()),
                                                   "message": "채널을 확인할 수 없어 게시하지 않았습니다."})
                    print("채널 확인에 실패해 게시하지 않았습니다.", flush=True)
                    return 3
            else:
                for channel in config["channels"]:
                    thread = threading.Thread(target=polling_loop, args=(channel, config, store, stop), daemon=True)
                    thread.start()
                    threads.append(thread)
                print("뉴스 감시 시작 · KST 하루 최대 3개 · 종료: Ctrl+C", flush=True)
            while not stop.is_set():
                video = store.candidate(now_kst(), config["daily_limit"], config["min_publish_interval_seconds"])
                if not video:
                    if once:
                        store.set_status("publisher", {"state": "no_eligible_post", "at": stamp(now_kst()),
                                                       "message": "당일 후보·중복·발행 한도·간격·미확인 결과를 확인하세요."})
                        print("지금 게시 가능한 영상이 없습니다. 후보·일일 한도·간격·미확인 결과를 status에서 확인하세요.", flush=True)
                        return 3
                    stop.wait(2)
                    continue
                article = article_for(video)
                drafts = root/"drafts"
                drafts.mkdir(exist_ok=True)
                (drafts/f"{video['video_id']}.json").write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    store.set_status("publisher", {"state": "preparing", "video_id": video["video_id"], "at": stamp(now_kst())})
                    url = publisher.publish(
                        article=article, blog_id=config["blog_id"], category=config["category"], topic=config["topic"],
                        before_submit=lambda: store.before_submit(video["video_id"], now_kst(),
                            config["daily_limit"], config["min_publish_interval_seconds"]),
                        on_wait=on_wait)
                    store.complete(video["video_id"], url, config["blog_id"], now_kst())
                    store.set_status("publisher", {"state": "published", "url": url, "at": stamp(now_kst())})
                    print(f"게시 확인: {url}", flush=True)
                    if once:
                        return 0
                except GateClosed:
                    store.set_status("publisher", {"state": "waiting", "message": "당일 여부·발행 한도·간격 확인 대기"})
                    if once:
                        print("발행 직전 조건을 확인해 게시를 보류했습니다.", flush=True)
                        return 3
                    stop.wait(5)
                except Exception as error:
                    # Any exception after durable submission is uncertain, including confirmation/storage failures.
                    store.uncertain(video["video_id"])
                    message = str(error) if isinstance(error, (PublishNotSubmitted, PublishUncertain)) else "편집기·로그인 또는 게시 기록 확인 실패"
                    store.fail(video["video_id"], message)
                    state = "uncertain" if store.snapshot(now_kst())["needs_reconciliation"] else "needs_attention"
                    store.set_status("publisher", {"state": state, "video_id": video["video_id"], "at": stamp(now_kst()), "message": message})
                    print("발행을 보류했습니다. status 명령과 브라우저를 확인하세요.", flush=True)
                    if once:
                        return 2
                    # Pause publishing after a browser failure. Discovery keeps running.
                    # Restart deliberately after fixing selectors/login; never churn through queued items.
                    while not stop.wait(2):
                        pass
        finally:
            stop.set()
            publisher.close()
            for thread in threads:
                thread.join(timeout=1)
    return 0


def main(argv=None):
    from .naver import PublishNotSubmitted, PublishUncertain
    parser = argparse.ArgumentParser(description="당일 뉴스 쇼츠 → 네이버 블로그 (한국 시간 하루 최대 3개)")
    parser.add_argument("--config", type=Path, default=default_root()/"config.json")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="개인 설정 생성; 자동 발행하지 않음")
    init.add_argument("--blog-id")
    init.add_argument("--category")
    init.add_argument("--topic")
    init.add_argument("--browser-channel", choices=("chrome", "msedge", "chromium"))
    commands.add_parser("login", help="로그인과 수동 인증만 수행")
    commands.add_parser("run", help="감시 및 자동 발행 시작")
    commands.add_parser("once", help="채널 확인 후 최대 1개 게시하고 종료; 기존 일일 한도 적용")
    commands.add_parser("status", help="현재 상태와 게시 내역 확인")
    reconcile = commands.add_parser("reconcile", help="실제 블로그를 확인한 뒤 불확실한 결과 정리")
    reconcile.add_argument("video_id")
    outcome = reconcile.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--url")
    outcome.add_argument("--not-published", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = args.config.expanduser().resolve()
        if args.command == "init":
            if path.exists():
                print("기존 설정을 보존했습니다. 변경은 config.json에서 하세요.")
                return 0
            config = json.loads(json.dumps(DEFAULTS))
            config["blog_id"] = args.blog_id or DEFAULTS["blog_id"]
            config["category"] = args.category if args.category is not None else DEFAULTS["category"]
            config["topic"] = args.topic if args.topic is not None else DEFAULTS["topic"]
            config["browser_channel"] = args.browser_channel or "chrome"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2)
            print(f"설정 생성: {path}")
            if not config["blog_id"]:
                print("실행 전 config.json의 blog_id와 category를 지정하세요.")
            return 0
        config = read_config(path)
        root = path.parent
        if args.command in ("run", "login", "once"):
            return run(config, root, login_only=args.command == "login", once=args.command == "once")
        store = Store(root/"agent.sqlite3")
        if args.command == "status":
            print(json.dumps(store.snapshot(now_kst()), ensure_ascii=False, indent=2))
        elif args.url:
            # This command is explicit user attestation, not an automated HTTP verification.
            store.complete(args.video_id, args.url, config["blog_id"], now_kst())
            print("사용자가 확인한 게시 주소를 기록했습니다. 재발행하지 않습니다.")
        else:
            store.reconcile_absent(args.video_id)
            print("미게시 확인을 기록했습니다. 이 영상은 자동 재발행하지 않습니다.")
        return 0
    except KeyboardInterrupt:
        print("에이전트를 종료했습니다. 다음 실행 때 미확인 게시 결과를 점검합니다.")
        return 130
    except (PublishNotSubmitted, PublishUncertain) as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, json.JSONDecodeError):
        print("설정·실행을 확인하세요: config.json의 블로그 ID/경로, 실행 중인 에이전트, 브라우저 설치 상태를 확인하세요.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
