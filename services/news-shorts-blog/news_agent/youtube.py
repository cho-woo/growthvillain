"""Conditional YouTube RSS discovery with explicit channel Shorts membership.

RSS identifies publication time but does not identify Shorts. A video is emitted
only after the configured channel's Shorts tab independently lists its ID.
No video download, browser session, account, or CAPTCHA bypass is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

KST = timezone(timedelta(hours=9))
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
HANDLE = re.compile(r"@[A-Za-z0-9_.-]{3,50}\Z")
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class SourceError(RuntimeError):
    """A source could not be checked; this is different from no new videos."""


@dataclass(frozen=True)
class Video:
    video_id: str
    channel_id: str
    channel_name: str
    title: str
    url: str
    published_at: datetime
    description: str = ""


class _QuietLogger:
    # Extractor messages can include opaque query strings. Report safe errors at
    # our boundary instead of forwarding third-party messages to the console.
    def debug(self, *_args, **_kwargs):
        pass

    info = warning = error = debug


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def parse_feed(content: bytes, channel_id: str, channel_name: str) -> list[Video]:
    """Parse only entries whose feed and item identify the expected channel."""
    if len(content) > 2_000_000 or b"<!DOCTYPE" in content.upper():
        raise SourceError("YouTube RSS 응답 형식이 올바르지 않습니다.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise SourceError("YouTube RSS를 읽을 수 없습니다.") from None
    if root.tag != f"{{{NS['atom']}}}feed":
        raise SourceError("YouTube RSS 피드가 아닙니다.")
    if root.findtext("yt:channelId", namespaces=NS) != channel_id:
        raise SourceError("YouTube RSS의 채널 ID가 설정과 일치하지 않습니다.")
    videos: list[Video] = []
    seen: set[str] = set()
    for entry in root.findall("atom:entry", NS):
        if entry.findtext("yt:channelId", namespaces=NS) != channel_id:
            raise SourceError("YouTube RSS 항목의 채널 ID가 일치하지 않습니다.")
        identity = entry.findtext("yt:videoId", default="", namespaces=NS)
        title = entry.findtext("atom:title", default="", namespaces=NS).strip()
        published = _parse_timestamp(entry.findtext("atom:published", default="", namespaces=NS))
        if not VIDEO_ID.fullmatch(identity) or not title or published is None or identity in seen:
            continue
        seen.add(identity)
        description = entry.findtext("media:group/media:description", default="", namespaces=NS)
        videos.append(Video(identity, channel_id, channel_name, title,
                            f"https://www.youtube.com/shorts/{identity}", published,
                            description.strip()))
    return videos


class YouTubeSource:
    """One configured channel. Call from a scheduler at least 60s apart.

    Feed responses are retained across HTTP 304, including when a prior Shorts
    tab check failed. A Shorts tab delay is retried after 60 seconds. State is
    per instance; durable publication deduplication belongs in the agent store.
    """

    def __init__(self, handle: str, name: str, channel_id: str | None = None):
        if not HANDLE.fullmatch(handle):
            raise ValueError("YouTube handle must be an @handle, without a URL.")
        if channel_id is not None and not CHANNEL_ID.fullmatch(channel_id):
            raise ValueError("Invalid YouTube channel ID.")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A channel display name is required.")
        self.handle = handle
        self.name = name.strip()
        self.channel_id = channel_id
        self.etag: str | None = None
        self.modified: str | None = None
        self._feed: list[Video] = []
        self._has_feed = False
        self._short_ids: set[str] = set()
        self._checked_candidates: set[str] = set()
        self._shorts_checked_at: datetime | None = None
        self._day = None

    def _extract_shorts(self) -> dict:
        try:
            import yt_dlp
        except ImportError:
            raise SourceError("yt-dlp가 설치되지 않았습니다. 설치 스크립트를 실행하세요.") from None
        options = {
            "quiet": True,
            "no_warnings": True,
            "logger": _QuietLogger(),
            "extract_flat": "in_playlist",
            "skip_download": True,
            "playlistend": 60,
            "socket_timeout": 15,
            "retries": 1,
            "extractor_retries": 1,
            "ignoreerrors": False,
            "lazy_playlist": False,
        }
        try:
            with yt_dlp.YoutubeDL(options) as extractor:
                result = extractor.extract_info(f"https://www.youtube.com/{self.handle}/shorts", download=False)
        except Exception:
            raise SourceError("YouTube Shorts 목록 확인 실패 · 네트워크나 YouTube 접근 상태를 확인하세요.") from None
        if not isinstance(result, dict):
            raise SourceError("YouTube Shorts 목록 응답이 없습니다.")
        return result

    def _load_shorts(self, now: datetime) -> None:
        result = self._extract_shorts()
        try:
            tab_url = urlsplit(result.get("webpage_url", ""))
            actual_shorts_tab = (tab_url.scheme == "https" and
                                 tab_url.hostname in {"www.youtube.com", "youtube.com", "m.youtube.com"} and
                                 tab_url.path.rstrip("/").endswith("/shorts"))
        except (ValueError, TypeError):
            actual_shorts_tab = False
        if not actual_shorts_tab:
            raise SourceError("YouTube Shorts 전용 탭을 확인할 수 없습니다.")
        identity = result.get("channel_id")
        if not isinstance(identity, str) or not CHANNEL_ID.fullmatch(identity):
            raise SourceError("YouTube Shorts 채널 ID를 확인할 수 없습니다.")
        if self.channel_id is not None and identity != self.channel_id:
            raise SourceError("설정한 채널과 YouTube Shorts 채널 ID가 다릅니다.")
        entries = result.get("entries")
        if not isinstance(entries, list):
            raise SourceError("YouTube Shorts 목록 형식이 올바르지 않습니다.")
        found: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            owner = entry.get("channel_id")
            if owner is not None and owner != identity:
                raise SourceError("다른 채널의 Shorts가 발견되어 확인을 중단했습니다.")
            video_id = entry.get("id")
            if isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id):
                found.add(video_id)
        self.channel_id = identity
        self._short_ids.update(found)
        self._shorts_checked_at = now

    @staticmethod
    def _http_get(url: str, headers: dict):
        try:
            import requests
            return requests.get(url, headers=headers, timeout=(8, 20), allow_redirects=False)
        except ImportError:
            raise SourceError("requests가 설치되지 않았습니다. 설치 스크립트를 실행하세요.") from None
        except Exception:
            raise SourceError("YouTube RSS 요청 실패 · 네트워크를 확인하세요.") from None

    def _refresh_feed(self) -> None:
        headers = {"User-Agent": "NewsShortsBlog/1.0 (+YouTube RSS reader)"}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.modified:
            headers["If-Modified-Since"] = self.modified
        response = self._http_get(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={self.channel_id}", headers)
        try:
            if response.status_code == 304:
                if not self._has_feed:
                    raise SourceError("캐시가 없는 YouTube RSS 304 응답입니다.")
                return
            if response.status_code != 200:
                code = int(response.status_code)
                raise SourceError(f"YouTube RSS 확인 실패 (HTTP {code}).")
            parsed = parse_feed(response.content, self.channel_id, self.name)
            # Only cache successful, validated responses. A transient error must
            # not advance the cache and permanently lose a candidate video.
            self._feed = parsed
            self._has_feed = True
            self.etag = response.headers.get("ETag")
            self.modified = response.headers.get("Last-Modified")
        finally:
            response.close()

    def fetch_today(self, now: datetime) -> list[Video]:
        if now.tzinfo is None:
            raise ValueError("An aware datetime is required.")
        today = now.astimezone(KST).date()
        if today != self._day:
            self._short_ids.clear()
            self._checked_candidates.clear()
            self._shorts_checked_at = None
            self._day = today
        resolved_now = False
        if self.channel_id is None:
            self._load_shorts(now)
            resolved_now = True
        self._refresh_feed()
        candidates = [video for video in self._feed
                      if video.published_at <= now and video.published_at.astimezone(KST).date() == today]
        candidate_ids = {video.video_id for video in candidates}
        unknown = candidate_ids - self._short_ids
        refresh = (bool(unknown) and
                   (not unknown.issubset(self._checked_candidates) or self._shorts_checked_at is None or
                    (now - self._shorts_checked_at).total_seconds() >= 60))
        if refresh and not resolved_now:
            self._load_shorts(now)
        # Failures before here leave candidate checks pending for the next poll,
        # even if YouTube answers the next conditional RSS request with 304.
        self._checked_candidates.update(candidate_ids)
        return sorted((video for video in candidates if video.video_id in self._short_ids),
                      key=lambda video: (video.published_at, video.video_id), reverse=True)
