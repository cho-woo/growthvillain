from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from news_agent.cli import DEFAULTS, instance_lock, main, read_config
from news_agent.core import GateClosed, KST, Store, article_for, similar_title, valid_post_url
from news_agent.youtube import Video


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root/'agent.sqlite3')
        self.now = datetime(2026, 10, 20, 10, tzinfo=KST)

    def tearDown(self):
        self.temp.cleanup()

    def add(self, number, title=None, at=None):
        identity = f'video{number:06d}'
        video = Video(identity, 'UC'+'a'*22, 'SBS 뉴스', title or f'서로 다른 주요 사건 {number}',
                      f'https://www.youtube.com/shorts/{identity}', at or self.now)
        self.store.observe([video], self.now)
        return identity

    def test_successful_posts_stop_at_three(self):
        for number in range(4):
            identity = self.add(number)
            if number < 3:
                self.store.before_submit(identity, self.now, min_interval=0)
                self.store.complete(identity, f'https://blog.naver.com/testblog/{10000+number}', 'testblog', self.now)
            else:
                with self.assertRaises(GateClosed):
                    self.store.before_submit(identity, self.now, min_interval=0)
        self.assertIsNone(self.store.candidate(self.now, min_interval=0))
        self.assertEqual(self.store.snapshot(self.now)['counts']['published'], 3)

    def test_atomic_reservation_prevents_concurrent_submit(self):
        ids = [self.add(i) for i in range(2)]
        def reserve(identity):
            try:
                Store(self.store.path).before_submit(identity, self.now, min_interval=0)
                return True
            except GateClosed:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(reserve, ids)), 1)

    def test_crash_receipt_blocks_even_next_day(self):
        identity = self.add(1)
        self.store.before_submit(identity, self.now, min_interval=0)
        restored = Store(self.store.path)
        restored.recover()
        self.assertEqual(restored.snapshot(self.now)['needs_reconciliation'][0]['video_id'], identity)
        self.now += timedelta(days=1)
        next_id = self.add(2)
        with self.assertRaises(GateClosed):
            restored.before_submit(next_id, self.now, min_interval=0)
        restored.reconcile_absent(identity)
        restored.before_submit(next_id, self.now, min_interval=0)

    def test_uncertain_confirmation_accepts_only_target_blog(self):
        identity = self.add(1)
        self.store.before_submit(identity, self.now, min_interval=0)
        self.store.uncertain(identity)
        with self.assertRaises(ValueError):
            self.store.complete(identity, 'https://blog.naver.com/other/12345', 'testblog', self.now)
        self.store.complete(identity, 'https://blog.naver.com/testblog/12345', 'testblog', self.now)
        self.assertEqual(self.store.snapshot(self.now)['counts'], {'published': 1})

    def test_retry_after_confirmation_cannot_duplicate(self):
        identity = self.add(1)
        self.store.before_submit(identity, self.now, min_interval=0)
        self.store.complete(identity, 'https://blog.naver.com/testblog/12345', 'testblog', self.now)
        self.add(1)
        with self.assertRaises(GateClosed):
            self.store.before_submit(identity, self.now, min_interval=0)

    def test_midnight_after_human_auth_rejects_yesterday(self):
        identity = self.add(1)
        tomorrow = (self.now+timedelta(days=1)).replace(hour=0, minute=1)
        with self.assertRaises(GateClosed):
            self.store.before_submit(identity, tomorrow, min_interval=0)
        self.assertEqual(self.store.snapshot(self.now)['counts'], {'pending': 1})

    def test_midnight_guard_and_interval(self):
        identity = self.add(1)
        with self.assertRaises(GateClosed):
            self.store.before_submit(identity, self.now.replace(hour=23, minute=59), min_interval=0)
        self.store.before_submit(identity, self.now)
        self.store.complete(identity, 'https://blog.naver.com/testblog/12345', 'testblog', self.now)
        second = self.add(2)
        with self.assertRaises(GateClosed):
            self.store.before_submit(second, self.now+timedelta(seconds=299))
        self.store.before_submit(second, self.now+timedelta(seconds=300))

    def test_postclick_auth_crossing_midnight_counts_toward_both_days(self):
        self.now = self.now.replace(hour=23, minute=58)
        identity = self.add(1)
        self.store.before_submit(identity, self.now, min_interval=0)
        self.now += timedelta(minutes=12)
        self.store.complete(identity, 'https://blog.naver.com/testblog/12345', 'testblog', self.now)
        for number in (2, 3):
            next_id = self.add(number)
            self.store.before_submit(next_id, self.now, min_interval=0)
            self.store.complete(next_id, f'https://blog.naver.com/testblog/{12345+number}', 'testblog', self.now)
        fourth = self.add(4)
        with self.assertRaises(GateClosed):
            self.store.before_submit(fourth, self.now, min_interval=0)

    def test_future_and_previous_day_are_not_queued(self):
        self.add(1, at=self.now+timedelta(seconds=1))
        self.add(2, at=self.now-timedelta(days=1))
        self.assertEqual(self.store.snapshot(self.now)['counts'], {})

    def test_kst_not_utc_day(self):
        self.now = datetime(2026, 10, 20, 0, 10, tzinfo=KST)
        self.add(1, at=datetime(2026, 10, 19, 15, 5, tzinfo=timezone.utc))
        self.assertEqual(self.store.snapshot(self.now)['counts'], {'pending': 1})

    def test_similar_news_cross_channel_queued_once(self):
        title = '[속보] 서울 지하철 운행 중단으로 출근길 시민 불편'
        self.add(1, title=title)
        self.add(2, title='서울 지하철 운행 중단으로 출근길 시민 불편 #SBS #shorts')
        self.assertEqual(self.store.snapshot(self.now)['counts'], {'duplicate': 1, 'pending': 1})

    def test_presubmit_failure_does_not_consume_quota(self):
        identity = self.add(1)
        self.store.uncertain(identity)
        self.store.fail(identity, '로그인 필요')
        next_id = self.add(2)
        self.store.before_submit(next_id, self.now, min_interval=0)

    def test_manual_no_post_does_not_requeue_video(self):
        identity = self.add(1)
        self.store.before_submit(identity, self.now, min_interval=0)
        self.store.uncertain(identity)
        self.store.reconcile_absent(identity)
        self.assertIsNone(self.store.candidate(self.now, min_interval=0))

    def test_article_is_source_bound_not_invented_summary(self):
        identity = self.add(1, title='국회 긴급회의 개최')
        article = article_for(self.store.candidate(self.now))
        self.assertIn('국회 긴급회의 개최', article['body'])
        self.assertIn(f'https://www.youtube.com/shorts/{identity}', article['body'])
        self.assertIn('전사한 요약', article['body'])
        self.assertNotIn('의결', article['body'])


class ConfigurationTests(unittest.TestCase):
    def test_user_target_defaults_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            self.assertEqual(main(['--config', str(path), 'init']), 0)
            config = read_config(path)
            self.assertEqual(config['blog_id'], 'wdetector')
            self.assertEqual(config['category'], '이슈')
            self.assertEqual(config['topic'], '사회·정치')

    def test_init_preserves_existing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            self.assertEqual(main(['--config', str(path), 'init', '--blog-id', 'myblog']), 0)
            first = path.read_bytes()
            self.assertEqual(main(['--config', str(path), 'init', '--blog-id', 'changed']), 0)
            self.assertEqual(path.read_bytes(), first)
            self.assertEqual(read_config(path)['blog_id'], 'myblog')

    def test_invalid_daily_cap_and_polls_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            for key, value in [('daily_limit', 4), ('daily_limit', True), ('poll_seconds', 1), ('blog_id', '')]:
                config = {**DEFAULTS, 'blog_id': 'myblog', key: value}
                path.write_text(json.dumps(config), encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_config(path)

    def test_bad_channels_fail_before_threads_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.json'
            for channel in ({'name': 'SBS', 'handle': '@x'}, {'name': ' ', 'handle': '@SBSnews8'},
                            {'name': 'SBS', 'handle': '@SBSnews8', 'channel_id': 'wrong'}):
                path.write_text(json.dumps({**DEFAULTS, 'blog_id': 'myblog', 'channels': [channel]}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_config(path)

    def test_process_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'lock'
            with instance_lock(path):
                with self.assertRaises(ValueError):
                    with instance_lock(path):
                        pass
            with instance_lock(path):
                pass

    def test_post_url_rejects_other_domains_and_credentials(self):
        for url in ('https://blog.naver.com.evil.test/myblog/12345',
                    'https://user:password@blog.naver.com/myblog/12345',
                    'https://blog.naver.com/other/12345', 'http://blog.naver.com/myblog/12345'):
            self.assertFalse(valid_post_url(url, 'myblog'))
        self.assertTrue(valid_post_url('https://blog.naver.com/PostView.naver?blogId=myblog&logNo=12345', 'myblog'))

    def test_distinct_headlines_not_duplicate(self):
        self.assertFalse(similar_title('정부 추경 예산안 발표', '서울 대설 주의보 해제'))


if __name__ == '__main__':
    unittest.main()
