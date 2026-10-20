from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from news_agent.cli import DEFAULTS, run, scan_once
from news_agent.core import GateClosed, KST, Store
from news_agent.naver import PublishNotSubmitted, PublishUncertain
from news_agent.youtube import SourceError, Video


class OnceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.current = datetime(2026, 10, 20, 12, tzinfo=KST)
        self.config = {**DEFAULTS, 'min_publish_interval_seconds': 0, 'channels': DEFAULTS['channels'][:1]}
        self.source = Mock()
        self.source.fetch_today.return_value = [
            Video(f'video{number:06d}', 'UC'+'a'*22, 'SBS 뉴스', f'서로 다른 주요 사건 {number}',
                  f'https://www.youtube.com/shorts/video{number:06d}', self.current)
            for number in range(1, 5)
        ]
        self.publisher = Mock()
        self.publisher.publish.side_effect = self.publish_ok

    def tearDown(self):
        self.temp.cleanup()

    def publish_ok(self, **kwargs):
        kwargs['before_submit']()
        return 'https://blog.naver.com/wdetector/123456789'

    def execute(self):
        with patch('news_agent.cli.now_kst', return_value=self.current), \
                patch('news_agent.cli.make_publisher', return_value=self.publisher), \
                patch('news_agent.youtube.YouTubeSource', return_value=self.source):
            return run(self.config, self.root, once=True)

    def snapshot(self):
        return Store(self.root/'agent.sqlite3').snapshot(self.current)

    def test_once_publishes_only_one_and_exits(self):
        self.assertEqual(self.execute(), 0)
        self.publisher.publish.assert_called_once()
        self.publisher.close.assert_called_once()
        self.assertEqual(self.snapshot()['counts'], {'pending': 3, 'published': 1})
        kwargs = self.publisher.publish.call_args.kwargs
        self.assertEqual((kwargs['blog_id'], kwargs['category'], kwargs['topic']),
                         ('wdetector', '이슈', '사회·정치'))

    def test_repeated_once_cannot_bypass_daily_limit(self):
        for _ in range(3):
            self.assertEqual(self.execute(), 0)
        self.assertEqual(self.execute(), 3)
        self.assertEqual(self.publisher.publish.call_count, 3)
        self.assertEqual(self.snapshot()['counts']['published'], 3)

    def test_no_candidates_never_opens_publisher(self):
        self.source.fetch_today.return_value = []
        self.assertEqual(self.execute(), 3)
        self.publisher.publish.assert_not_called()
        self.publisher.ensure_login.assert_not_called()

    def test_unavailable_sources_are_not_reported_as_success(self):
        self.source.fetch_today.side_effect = SourceError('네트워크 연결 확인 필요')
        self.assertEqual(self.execute(), 3)
        self.publisher.publish.assert_not_called()
        self.assertEqual(self.snapshot()['sources']['publisher']['state'], 'source_error')

    def test_uncertain_post_exits_and_blocks_next_once(self):
        def uncertain(**kwargs):
            kwargs['before_submit']()
            raise PublishUncertain('발행 결과 확인 필요')
        self.publisher.publish.side_effect = uncertain
        self.assertEqual(self.execute(), 2)
        self.assertEqual(len(self.snapshot()['needs_reconciliation']), 1)
        self.assertEqual(self.execute(), 3)
        self.publisher.publish.assert_called_once()

    def test_presubmit_auth_failure_exits_without_quota_reservation(self):
        self.publisher.publish.side_effect = PublishNotSubmitted('로그인 확인 필요')
        self.assertEqual(self.execute(), 2)
        self.assertEqual(self.snapshot()['counts'], {'failed': 1, 'pending': 3})
        self.assertFalse(self.snapshot()['needs_reconciliation'])
        with Store(self.root/'agent.sqlite3').connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_gate_recheck_exits_without_retrying(self):
        self.publisher.publish.side_effect = GateClosed('날짜 전환')
        self.assertEqual(self.execute(), 3)
        self.publisher.publish.assert_called_once()
        self.assertEqual(self.snapshot()['counts'], {'pending': 4})

    def test_partial_source_error_keeps_other_channels(self):
        config = {**self.config, 'channels': DEFAULTS['channels'][:2]}
        failed = Mock()
        failed.fetch_today.side_effect = SourceError('네트워크 연결 확인 필요')
        def source_for(**kwargs):
            return failed if kwargs['name'] == 'MBC 뉴스' else self.source
        store = Store(self.root/'agent.sqlite3')
        with patch('news_agent.cli.now_kst', return_value=self.current), \
                patch('news_agent.youtube.YouTubeSource', side_effect=source_for):
            self.assertEqual(scan_once(config, store), 1)
        self.assertEqual(store.snapshot(self.current)['counts'], {'pending': 4})


if __name__ == '__main__':
    unittest.main()
