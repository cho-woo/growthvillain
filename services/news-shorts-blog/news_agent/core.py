"""Persistent publication limits, duplicate detection, and source-bound articles."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import parse_qs, urlsplit

KST = timezone(timedelta(hours=9))


def now_kst():
    return datetime.now(KST)


def stamp(value):
    if value.tzinfo is None:
        raise ValueError("시간대가 있는 시각이 필요합니다.")
    return value.astimezone(KST).isoformat()


def normalized_title(title):
    title = unicodedata.normalize("NFKC", title).lower()
    title = re.sub(r"\[[^]]*\]|#[\w가-힣]+", " ", title)
    title = re.sub(r"\b(sbs|mbc|ytn|news|shorts)\b|속보|뉴스", " ", title)
    return re.sub(r"[^\w가-힣]", "", title)


def similar_title(left, right):
    a, b = normalized_title(left), normalized_title(right)
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 12 and
            SequenceMatcher(None, a, b).ratio() >= .82))


def article_for(video):
    """Do not invent a transcript or facts unavailable from the source metadata."""
    title = " ".join(video["title"].split())
    source = " ".join(video["channel_name"].split())
    published = datetime.fromisoformat(video["published_at"]).astimezone(KST)
    url = f"https://www.youtube.com/shorts/{video['video_id']}"
    return {
        "video_id": video["video_id"],
        "title": f"[{source}] {title}"[:150],
        "body": (
            f"오늘의 뉴스 쇼츠 | {source}\n\n"
            f"{source}가 {published:%Y년 %m월 %d일 %H:%M} (한국 시간)에 공개한 "
            f"뉴스 쇼츠입니다.\n\n"
            f"보도 제목\n{title}\n\n"
            "원본 확인\n"
            "사건의 경위와 인터뷰, 현장 영상은 아래 방송사 원본에서 확인할 수 있습니다. "
            "속보의 내용은 후속 보도에서 수정되거나 추가될 수 있으므로 "
            "방송사의 최신 안내를 함께 확인해 주세요.\n\n"
            f"출처: {source} 공식 유튜브 채널\n{url}\n\n"
            "이 글은 방송사 공개 제목·게시 시각과 원본 링크로 자동 작성한 안내입니다. "
            "영상 전체를 시청·전사한 요약이나 독립적으로 확인한 취재 기사는 아닙니다."
        ),
    }


def valid_post_url(url, blog_id):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"blog.naver.com", "m.blog.naver.com"}:
            return False
        if parsed.username or parsed.password:
            return False
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == blog_id and parts[1].isdigit():
            return True
        query = parse_qs(parsed.query)
        return (parsed.path == "/PostView.naver" and query.get("blogId") == [blog_id]
                and bool(re.fullmatch(r"\d+", query.get("logNo", [""])[0])))
    except (ValueError, TypeError):
        return False


class GateClosed(RuntimeError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS videos (
                  video_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL,
                  channel_name TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
                  published_at TEXT NOT NULL, day TEXT NOT NULL,
                  discovered_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                  note TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS attempts (
                  video_id TEXT PRIMARY KEY REFERENCES videos(video_id), day TEXT NOT NULL,
                  submitted_at TEXT NOT NULL, state TEXT NOT NULL,
                  post_url TEXT, confirmed_at TEXT);
                CREATE TABLE IF NOT EXISTS status (
                  name TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def observe(self, videos, current):
        day = current.astimezone(KST).date().isoformat()
        added = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            titles = [r[0] for r in db.execute("SELECT title FROM videos WHERE day=? AND state!='duplicate'", (day,))]
            for video in videos:
                if (video.published_at.tzinfo is None or video.published_at > current or
                        video.published_at.astimezone(KST).date().isoformat() != day):
                    continue
                if db.execute("SELECT 1 FROM videos WHERE video_id=?", (video.video_id,)).fetchone():
                    continue
                duplicate = any(similar_title(video.title, prior) for prior in titles)
                db.execute("INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    video.video_id, video.channel_id, video.channel_name, video.title,
                    video.url, stamp(video.published_at), day, stamp(current),
                    "duplicate" if duplicate else "pending", "유사 제목" if duplicate else ""))
                if not duplicate:
                    titles.append(video.title)
                    added += 1
        return added

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE attempts SET state='uncertain' WHERE state='submitting'")
            db.execute("UPDATE videos SET state='uncertain', note='이전 실행의 게시 결과 확인 필요' "
                       "WHERE state='submitting'")

    def set_status(self, name, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO status VALUES(?,?)", (name, json.dumps(value, ensure_ascii=False)))

    def candidate(self, current, daily_limit=3, min_interval=300):
        with self.connect() as db:
            try:
                self._gate(db, current, daily_limit, min_interval)
            except GateClosed:
                return None
            row = db.execute("SELECT * FROM videos WHERE day=? AND state='pending' "
                             "ORDER BY published_at DESC LIMIT 1",
                             (current.astimezone(KST).date().isoformat(),)).fetchone()
            return dict(row) if row else None

    def _gate(self, db, current, daily_limit, min_interval):
        current = current.astimezone(KST)
        if not 1 <= daily_limit <= 3 or min_interval < 0:
            raise ValueError("일일 발행 한도는 1~3개여야 합니다.")
        if current.hour == 23 and current.minute == 59:
            raise GateClosed("날짜 전환 직전에는 발행하지 않습니다.")
        if db.execute("SELECT 1 FROM attempts WHERE state IN ('uncertain','submitting')").fetchone():
            raise GateClosed("확인되지 않은 게시 결과가 있습니다.")
        # A human may finish a post-click challenge after midnight. Count that
        # attempt on both the submission and confirmation days conservatively.
        count = db.execute("SELECT count(*) FROM attempts WHERE state!='not_published' "
                           "AND (day=? OR substr(confirmed_at,1,10)=?)",
                           (current.date().isoformat(), current.date().isoformat())).fetchone()[0]
        if count >= daily_limit:
            raise GateClosed("오늘의 발행 한도에 도달했습니다.")
        latest = db.execute("SELECT coalesce(confirmed_at,submitted_at) AS last_at FROM attempts "
                            "WHERE state!='not_published' ORDER BY last_at DESC LIMIT 1").fetchone()
        if latest and (current - datetime.fromisoformat(latest[0])).total_seconds() < min_interval:
            raise GateClosed("다음 발행 간격을 기다립니다.")

    def before_submit(self, video_id, current, daily_limit=3, min_interval=300):
        """Durable reservation immediately before the irreversible browser click."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._gate(db, current, daily_limit, min_interval)
            row = db.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
            day = current.astimezone(KST).date().isoformat()
            if not row or row["state"] != "pending" or row["day"] != day:
                raise GateClosed("당일의 미게시 영상만 발행할 수 있습니다.")
            db.execute("INSERT INTO attempts VALUES(?,?,?,'submitting',NULL,NULL)", (video_id, day, stamp(current)))
            db.execute("UPDATE videos SET state='submitting' WHERE video_id=?", (video_id,))

    def complete(self, video_id, post_url, blog_id, current):
        if not valid_post_url(post_url, blog_id):
            raise ValueError("대상 블로그의 실제 게시 주소가 필요합니다.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE attempts SET state='published', post_url=?, confirmed_at=? "
                                 "WHERE video_id=? AND state IN ('submitting','uncertain')",
                                 (post_url, stamp(current), video_id)).rowcount
            if changed != 1:
                raise ValueError("확인할 발행 시도가 없습니다.")
            db.execute("UPDATE videos SET state='published', note='' WHERE video_id=?", (video_id,))

    def uncertain(self, video_id):
        with self.connect() as db:
            db.execute("UPDATE attempts SET state='uncertain' WHERE video_id=? AND state='submitting'", (video_id,))
            db.execute("UPDATE videos SET state='uncertain', note='블로그에서 실제 게시 여부 확인 필요' "
                       "WHERE video_id=? AND state='submitting'", (video_id,))

    def fail(self, video_id, message):
        with self.connect() as db:
            db.execute("UPDATE videos SET state='failed',note=? WHERE video_id=? AND state='pending'",
                       (message, video_id))

    def reconcile_absent(self, video_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE attempts SET state='not_published' WHERE video_id=? AND state='uncertain'",
                                 (video_id,)).rowcount
            if changed != 1:
                raise ValueError("결과 확인 대기 중인 영상이 아닙니다.")
            # Never automatically re-submit a manually resolved item.
            db.execute("UPDATE videos SET state='failed',note='사용자가 미게시 확인; 재발행하지 않음' WHERE video_id=?",
                       (video_id,))

    def snapshot(self, current):
        with self.connect() as db:
            return {
                "day_kst": current.astimezone(KST).date().isoformat(),
                "counts": dict(db.execute("SELECT state,count(*) FROM videos WHERE day=? GROUP BY state",
                               (current.astimezone(KST).date().isoformat(),)).fetchall()),
                "sources": {row["name"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM status")},
                "needs_reconciliation": [dict(row) for row in db.execute(
                    "SELECT video_id,day,submitted_at FROM attempts WHERE state='uncertain'")],
                "recent_posts": [dict(row) for row in db.execute(
                    "SELECT video_id,post_url,confirmed_at FROM attempts WHERE state='published' "
                    "ORDER BY confirmed_at DESC LIMIT 10")],
            }
