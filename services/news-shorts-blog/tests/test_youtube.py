from datetime import datetime, timedelta, timezone
import sys
import types
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape

from news_agent.youtube import KST, SourceError, YouTubeSource, parse_feed

CHANNEL = "UC" + "a" * 22
OTHER = "UC" + "b" * 22
VIDEO = "abcdefghijk"
SECOND = "lmnopqrstuv"
NOW = datetime(2026, 10, 20, 12, tzinfo=KST)


def feed(items=None, channel=CHANNEL):
    if items is None:
        items = [(VIDEO, "속보: 오늘 뉴스", "2026-10-20T02:00:00Z", channel)]
    entries = "".join(
        f"<entry><yt:videoId>{video}</yt:videoId><yt:channelId>{owner}</yt:channelId>"
        f"<title>{escape(title)}</title><published>{at}</published>"
        "<media:group><media:description>공식 영상 설명</media:description></media:group></entry>"
        for video, title, at, owner in items)
    return (f'<feed xmlns="http://www.w3.org/2005/Atom" '
            'xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
            'xmlns:media="http://search.yahoo.com/mrss/">'
            f"<yt:channelId>{channel}</yt:channelId>{entries}</feed>").encode()


def response(content=None, code=200, headers=None):
    result = Mock(status_code=code, content=feed() if content is None else content,
                  headers=headers or {})
    return result


def shorts(*identities, channel=CHANNEL):
    return {"channel_id": channel,
            "webpage_url": f"https://www.youtube.com/channel/{channel}/shorts",
            "entries": [{"id": value, "channel_id": channel} for value in identities]}


class FeedTests(unittest.TestCase):
    def test_parses_only_verified_feed_fields_and_builds_canonical_url(self):
        video = parse_feed(feed(), CHANNEL, "뉴스")[0]
        self.assertEqual(video.video_id, VIDEO)
        self.assertEqual(video.url, f"https://www.youtube.com/shorts/{VIDEO}")
        self.assertEqual(video.description, "공식 영상 설명")
        self.assertEqual(video.published_at, datetime(2026, 10, 20, 2, tzinfo=timezone.utc))

    def test_rejects_wrong_feed_and_entry_channel(self):
        for content in [feed(channel=OTHER), feed([(VIDEO, "제목", "2026-10-20T02:00:00Z", OTHER)])]:
            with self.subTest(content=content), self.assertRaises(SourceError):
                parse_feed(content, CHANNEL, "뉴스")

    def test_malformed_entries_do_not_become_candidates(self):
        items = [(VIDEO, "제목", "not-a-time", CHANNEL),
                 (SECOND, "제목", "2026-10-20T02:00:00", CHANNEL),
                 ("../bad", "제목", "2026-10-20T02:00:00Z", CHANNEL)]
        self.assertEqual(parse_feed(feed(items), CHANNEL, "뉴스"), [])

    def test_refuses_non_feed_and_dtd(self):
        for content in [b"<html>blocked</html>", b"broken XML", b"<!DOCTYPE x><feed/>"]:
            with self.subTest(content=content), self.assertRaises(SourceError):
                parse_feed(content, CHANNEL, "뉴스")


class DiscoveryTests(unittest.TestCase):
    def source(self, channel=CHANNEL):
        source = YouTubeSource("@SBSnews8", "SBS", channel)
        source._http_get = Mock(return_value=response())
        source._extract_shorts = Mock(return_value=shorts(VIDEO))
        return source

    def test_resolves_channel_from_actual_shorts_tab_without_guessed_id(self):
        source = self.source(None)
        self.assertEqual(source.fetch_today(NOW)[0].video_id, VIDEO)
        self.assertEqual(source.channel_id, CHANNEL)
        source._extract_shorts.assert_called_once()
        self.assertIn("channel_id=" + CHANNEL, source._http_get.call_args.args[0])

    def test_only_shorts_membership_not_duration_or_title_is_sufficient(self):
        source = self.source()
        source._http_get.return_value = response(feed([(VIDEO, "#shorts 짧은 속보", "2026-10-20T02:00:00Z", CHANNEL)]))
        source._extract_shorts.return_value = shorts(SECOND)
        self.assertEqual(source.fetch_today(NOW), [])

    def test_conditional_feed_304_retains_verified_candidates(self):
        source = self.source()
        source._http_get.side_effect = [response(headers={"ETag": '"version1"', "Last-Modified": "time"}), response(code=304)]
        first = source.fetch_today(NOW)
        self.assertEqual(source.fetch_today(NOW + timedelta(seconds=60)), first)
        self.assertEqual(source._extract_shorts.call_count, 1)
        headers = source._http_get.call_args.args[1]
        self.assertEqual(headers["If-None-Match"], '"version1"')
        self.assertEqual(headers["If-Modified-Since"], "time")

    def test_shorts_failure_retries_even_when_next_feed_is_unchanged(self):
        source = self.source()
        source._http_get.side_effect = [response(headers={"ETag": "one"}), response(code=304)]
        source._extract_shorts.side_effect = [SourceError("blocked"), shorts(VIDEO)]
        with self.assertRaises(SourceError):
            source.fetch_today(NOW)
        self.assertEqual(source.fetch_today(NOW + timedelta(seconds=60))[0].video_id, VIDEO)
        self.assertEqual(source._extract_shorts.call_count, 2)

    def test_shorts_tab_lag_is_rechecked_after_sixty_seconds(self):
        source = self.source()
        source._http_get.side_effect = [response(), response(code=304), response(code=304)]
        source._extract_shorts.side_effect = [shorts(), shorts(VIDEO)]
        self.assertEqual(source.fetch_today(NOW), [])
        self.assertEqual(source.fetch_today(NOW + timedelta(seconds=30)), [])
        self.assertEqual(source.fetch_today(NOW + timedelta(seconds=60))[0].video_id, VIDEO)
        self.assertEqual(source._extract_shorts.call_count, 2)

    def test_future_and_previous_kst_day_are_excluded(self):
        source = self.source()
        source._http_get.return_value = response(feed([
            (VIDEO, "어제", "2026-10-19T14:59:59Z", CHANNEL),
            (SECOND, "오늘", "2026-10-19T15:00:00Z", CHANNEL),
            ("zzzzzzzzzzz", "미래", "2026-10-20T04:00:00Z", CHANNEL),
        ]))
        source._extract_shorts.return_value = shorts(VIDEO, SECOND, "zzzzzzzzzzz")
        self.assertEqual([v.video_id for v in source.fetch_today(NOW)], [SECOND])

    def test_no_today_candidates_does_not_fetch_shorts(self):
        source = self.source()
        source._http_get.return_value = response(feed([]))
        self.assertEqual(source.fetch_today(NOW), [])
        source._extract_shorts.assert_not_called()

    def test_midnight_resets_membership_and_drops_yesterday_on_304(self):
        source = self.source()
        source._http_get.side_effect = [response(), response(code=304)]
        self.assertEqual(len(source.fetch_today(NOW)), 1)
        self.assertEqual(source.fetch_today(NOW + timedelta(days=1)), [])
        self.assertEqual(source._short_ids, set())

    def test_wrong_channel_and_non_shorts_tab_fail_closed(self):
        for extracted in [shorts(VIDEO, channel=OTHER),
                          dict(shorts(VIDEO), webpage_url="https://www.youtube.com/@SBSnews8/videos"),
                          dict(shorts(VIDEO), webpage_url="https://evil.example/shorts")]:
            with self.subTest(extracted=extracted):
                source = self.source()
                source._extract_shorts.return_value = extracted
                with self.assertRaises(SourceError):
                    source.fetch_today(NOW)

    def test_error_response_is_not_cached_as_no_news(self):
        source = self.source()
        failed = response(code=429)
        source._http_get.side_effect = [failed, response()]
        with self.assertRaisesRegex(SourceError, "429"):
            source.fetch_today(NOW)
        failed.close.assert_called_once()
        self.assertEqual(source.fetch_today(NOW + timedelta(seconds=60))[0].video_id, VIDEO)

    def test_rejects_naive_now_and_invalid_source(self):
        with self.assertRaises(ValueError):
            self.source().fetch_today(datetime(2026, 10, 20))
        for handle in ["https://www.youtube.com/@SBSnews8", "@SBSnews8/shorts", "@x"]:
            with self.assertRaises(ValueError):
                YouTubeSource(handle, "News")

    def test_extractor_has_bounded_network_retries_and_no_download(self):
        fake_extractor = Mock()
        fake_extractor.__enter__ = Mock(return_value=fake_extractor)
        fake_extractor.__exit__ = Mock(return_value=False)
        fake_extractor.extract_info.return_value = shorts(VIDEO)
        constructor = Mock(return_value=fake_extractor)
        with patch.dict(sys.modules, {"yt_dlp": types.SimpleNamespace(YoutubeDL=constructor)}):
            source = YouTubeSource("@SBSnews8", "SBS", CHANNEL)
            self.assertEqual(source._extract_shorts()["channel_id"], CHANNEL)
        options = constructor.call_args.args[0]
        self.assertTrue(options["skip_download"])
        self.assertEqual(options["socket_timeout"], 15)
        self.assertEqual(options["playlistend"], 60)
        self.assertFalse(fake_extractor.extract_info.call_args.kwargs["download"])


if __name__ == "__main__":
    unittest.main()
