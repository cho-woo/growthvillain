"""Queue, privacy and schedule contracts; generated rank fixtures are test-only."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from server import Store, Controller
from storage_config import StorageUnavailable
from trend_service import TrendService, KST, SOURCE_URL


def snapshots(category='50000023', names=('검증브랜드',), days_ago=1):
    current_day = datetime.now(KST).date() - timedelta(days=days_ago)
    prior_day = current_day - timedelta(days=7)
    old = [f'일반검색어{i:03d}' for i in range(1, 101)]
    for offset, name in enumerate(names):
        old[70 + offset] = name
    current = list(names) + [word for word in old if word not in names]
    def wrap(words, day):
        return {'category': category, 'date': day.isoformat(), 'sourceUrl': SOURCE_URL,
                'entries': [{'rank': rank, 'keyword': word} for rank, word in enumerate(words, 1)]}
    return wrap(current, current_day), wrap(old, prior_day)


class TrendServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.web = self.base / 'web'
        self.web.mkdir()
        self.store = Store(self.base / 'private', self.web)
        self.service = TrendService(self.store)

    def tearDown(self):
        self.service.stop()
        self.store.close()
        self.temp.cleanup()

    def seed(self, category='50000023', names=('검증브랜드',), days_ago=1):
        current, previous = snapshots(category, names, days_ago)
        self.service.record_snapshots(current, previous, category)
        return current, previous

    def confirm(self, name='검증브랜드'):
        return self.service.save_brand({'name': name, 'aliases': [name], 'domain': 'example.com'})

    def candidate(self):
        return next(c for c in self.service.candidates() if c['keyword'] == '검증브랜드')

    def test_generic_keyword_collects_without_brand_confirmation_and_is_idempotent(self):
        self.seed()
        candidate = self.candidate()
        self.assertFalse(candidate['needsReview'])
        self.assertIsNotNone(candidate['dispatchKey'])
        with self.assertRaises(ValueError):
            self.service.collect('unconfirmed-brand')
        first = self.service.collect(candidate['dispatchKey'])
        second = self.service.collect(candidate['dispatchKey'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.store.jobs()), 1)
        self.assertEqual(first['domain'], '')
        self.assertEqual(first['keyword'], '검증브랜드')
        self.assertEqual(first['limit'], 20)

    def test_full_queue_does_not_consume_dispatch_key(self):
        self.seed()
        self.confirm()
        for number in range(20):
            comp = self.store.save_competitor({'name': f'대기{number}', 'keyword': f'검색{number}'})
            self.store.enqueue(comp['id'], 1)
        with self.assertRaises(ValueError):
            self.service.collect(self.candidate()['dispatchKey'])
        self.assertEqual(self.store.rows('SELECT * FROM trend_dispatches'), [])
        self.assertEqual(len(self.store.jobs()), 20)

    def test_job_and_dispatch_roll_back_together(self):
        self.seed()
        self.confirm()
        self.store.write("CREATE TRIGGER fail_dispatch BEFORE INSERT ON trend_dispatches BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaises(Exception):
            self.service.collect(self.candidate()['dispatchKey'])
        self.assertEqual(self.store.jobs(), [])
        self.assertEqual(self.store.rows('SELECT * FROM trend_dispatches'), [])

    def test_failed_and_canceled_jobs_retry_but_done_job_does_not(self):
        self.seed()
        self.confirm()
        key = self.candidate()['dispatchKey']
        first = self.service.collect(key)
        self.store.write("UPDATE jobs SET status='failed' WHERE id=?", (first['id'],))
        self.assertEqual(self.candidate()['state'], 'failed')
        second = self.service.collect(key)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_dispatches')), 1)
        self.store.write("UPDATE jobs SET status='canceled' WHERE id=?", (second['id'],))
        self.assertEqual(self.candidate()['state'], 'failed')
        third = self.service.collect(key)
        self.store.write("UPDATE jobs SET status='done' WHERE id=?", (third['id'],))
        self.assertEqual(self.candidate()['state'], 'done')
        self.assertEqual(self.service.collect(key)['id'], third['id'])
        self.assertEqual(len(self.store.jobs()), 3)

    def test_brand_cooldown_is_shared_across_categories(self):
        self.seed()
        self.confirm()
        self.service.collect(self.candidate()['dispatchKey'])
        self.store.write("UPDATE jobs SET status='done'")
        self.seed(category='50000006')
        self.service.save_settings({'category': '50000006'})
        self.assertEqual(self.candidate()['state'], 'cooldown')
        with self.assertRaises(ValueError):
            self.service.collect(self.candidate()['dispatchKey'])
        self.assertEqual(len(self.store.jobs()), 1)

    def test_auto_is_opt_in_one_at_a_time_and_total_is_five_keywords_per_day(self):
        names = tuple(f'브랜드{i}' for i in range(8))
        self.seed(names=names)
        self.assertEqual(self.service.dispatch_ready(), 0)
        self.service.save_settings({'autoEnabled': True})
        start = datetime.now(KST).replace(hour=12, minute=0, second=0).timestamp()
        for number in range(5):
            with patch('trend_service.time.time', return_value=start + number*900):
                self.assertEqual(self.service.dispatch_ready(), 1)
                self.assertEqual(self.service.dispatch_ready(), 0)
                self.store.write("UPDATE jobs SET status='done'")
                self.assertEqual(self.service.dispatch_ready(), 0)
        with patch('trend_service.time.time', return_value=start+5000):
            self.assertEqual(self.service.dispatch_ready(), 0)
        self.assertEqual(len(self.store.jobs()), 5)
        self.assertEqual({j['keyword'] for j in self.store.jobs()}, set(names[:5]))
        self.assertEqual(self.service.collection_policy()['dailyRemaining'], 0)
        other_instance = TrendService(self.store)
        self.assertTrue(other_instance.auto_enabled)
        other_instance.stop()

    def test_partial_source_does_not_replace_good_snapshot(self):
        current, previous = self.seed()
        current['entries'] = current['entries'][:99]
        with self.assertRaises(ValueError):
            self.service.record_snapshots(current, previous, '50000023')
        self.assertEqual(self.candidate()['currentRank'], 1)
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_snapshots')), 2)

    def test_stale_source_is_visible_but_cannot_dispatch(self):
        self.seed(days_ago=15)
        self.confirm()
        self.assertEqual(self.candidate()['state'], 'stale')
        with self.assertRaises(ValueError):
            self.service.collect(self.candidate()['dispatchKey'])
        self.service.save_settings({'category': '50000006'})
        self.assertEqual(self.service.candidates(), [])

    def test_ignore_generic_and_confirmed_alias_conflict(self):
        self.seed()
        self.service.ignore('검증브랜드')
        self.assertEqual(self.service.candidates(), [])
        self.confirm()
        self.assertEqual(len(self.service.candidates()), 1)
        with self.assertRaises(ValueError):
            self.service.save_brand({'name': '다른브랜드', 'aliases': ['검증브랜드']})
        self.service.save_brand({'name': '검증브랜드', 'aliases': ['다른표기']})
        self.assertEqual(self.service.brands()[0]['domain'], 'example.com')
        self.assertIn('다른표기', self.service.brands()[0]['aliases'])

    def test_brand_normalization_collision_does_not_corrupt_configuration(self):
        self.service.save_brand({'name': '달바'})
        with self.assertRaises(ValueError):
            self.service.save_brand({'name': '별도브랜드', 'aliases': ['달 바']})
        with self.assertRaises(ValueError):
            self.service.save_brand({'name': '숨은\u200b문자'})
        self.assertEqual(len(self.service.brands()), 1)
        self.assertEqual(len(self.store.competitors()), 1)
        self.assertEqual(self.service.status()['candidates'], [])
        self.service.ignore('달 바')
        self.assertEqual(self.store.rows('SELECT * FROM trend_ignored')[0]['keyword'], '달바')

    def test_book_category_and_partial_setting_update(self):
        self.service.save_settings({'category': '50005542', 'minimumRise': 12})
        self.service.save_settings({'autoEnabled': True})
        self.assertEqual(self.service.settings()['category'], '50005542')
        self.assertEqual(self.service.settings()['minimumRise'], 12)
        self.assertTrue(self.service.auto_enabled)

    def test_health_food_default_and_supported_food_categories(self):
        self.assertEqual(self.service.settings()['category'], '50000023')
        for category in ('50000006', '50000023', '50001899', '50001090', '50001092', '50017220', '50018919', '50000024'):
            self.service.save_settings({'category': category})
            self.assertEqual(self.service.settings()['category'], category)

    def test_only_public_trend_fields_are_exported_and_drive_failure_does_not_queue(self):
        self.seed()
        self.confirm()
        public_path = self.web / 'tools/meta-ads/data/trends.json'
        public = json.loads(public_path.read_text(encoding='utf-8'))
        self.assertEqual(len(public['history']), 1)
        self.assertEqual(public['history'][0]['brandName'], '검증브랜드')
        self.assertNotIn('dispatchKey', public['candidates'][0])
        self.assertNotIn('domain', public['brands'][0])
        self.assertNotIn('competitorId', public['brands'][0])
        self.assertNotIn(str(self.store.root), public_path.read_text(encoding='utf-8'))
        key = self.candidate()['dispatchKey']
        with patch('trend_service.assert_storage_available', side_effect=StorageUnavailable('drive unavailable')):
            with self.assertRaises(StorageUnavailable):
                self.service.collect(key)
        self.assertEqual(self.store.jobs(), [])
        self.assertEqual(json.loads(public_path.read_text(encoding='utf-8')), public)

    def test_failed_scan_keeps_last_good_rank_and_reports_error(self):
        self.seed()
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        with patch('trend_service.subprocess.Popen', return_value=process):
            self.service._scan(self.service.settings())
        self.assertIsNotNone(self.service.status()['error'])
        self.assertEqual(self.candidate()['currentRank'], 1)
        self.assertFalse(self.service.scanning)
        self.assertEqual(self.store.jobs(), [])
        self.assertTrue(any((self.store.root / 'trends').rglob('scan.log')))
        public = json.loads((self.web / 'tools/meta-ads/data/trends.json').read_text(encoding='utf-8'))
        self.assertEqual(public['history'][0]['currentRank'], 1)
        self.assertIsNotNone(public['lastError'])
        self.assertIsNotNone(public['lastSuccessAt'])

    def test_history_keeps_first_observation_and_multiple_dated_comparisons(self):
        with patch('trend_service.now', return_value='2026-10-07T00:00:00+00:00'):
            current, previous = self.seed(days_ago=2)
        with patch('trend_service.now', return_value='2026-10-07T01:00:00+00:00'):
            self.service.record_snapshots(current, previous, '50000023')
        event = self.service.history()[0]
        self.assertEqual(event['observedAt'], '2026-10-07T00:00:00+00:00')
        self.assertEqual(event['lastObservedAt'], '2026-10-07T01:00:00+00:00')
        self.assertEqual(event['periodDays'], 7)
        self.assertEqual((event['previousRank'], event['currentRank']), (71, 1))
        self.seed(days_ago=1)
        self.assertEqual(len(self.service.history()), 2)
        other = TrendService(self.store)
        self.assertEqual(len(other.history()), 2)
        other.stop()

    def test_new_top_entry_never_invents_previous_rank_in_history_or_export(self):
        current, previous = snapshots()
        current['entries'][0]['keyword'] = '새로진입한검색어'
        self.service.record_snapshots(current, previous, '50000023')
        item = self.service.history()[0]
        self.assertTrue(item['isNew'])
        self.assertIsNone(item['previousRank'])
        self.assertIsNone(item['rankRise'])
        self.assertEqual(item['rankWindow'], 100)
        self.assertEqual(item['periodDays'], 7)

    def test_explicit_auto_choice_and_next_run_survive_restart_and_off(self):
        self.service.save_settings({'autoEnabled': True})
        self.service.next_attempt = 1800000000
        self.service.last_attempt_at = '2026-10-07T01:00:00+00:00'
        self.service._persist_runtime()
        self.service.stop()
        resumed = TrendService(self.store)
        self.assertTrue(resumed.auto_enabled)
        self.assertEqual(resumed.next_attempt, 1800000000)
        self.assertEqual(resumed.status()['intervalSeconds'], 3600)
        self.assertEqual(resumed.status()['sourceCadence'], 'daily')
        self.assertIsNotNone(resumed.status()['nextRunAt'])
        resumed.save_settings({'autoEnabled': False})
        self.assertIsNone(resumed.status()['nextRunAt'])
        again = TrendService(self.store)
        self.assertFalse(again.auto_enabled)
        resumed.stop()
        again.stop()

    def test_hourly_tick_reuses_finalized_daily_source_and_keeps_observed_time(self):
        self.seed()
        observed = self.service.history()[0]['observedAt']
        self.service.save_settings({'autoEnabled': True})
        with patch.object(self.service, 'scan') as scan:
            self.service.tick()
            scan.assert_not_called()
        self.assertGreater(self.service.next_attempt, 0)
        self.assertEqual(self.service.history()[0]['observedAt'], observed)
        self.assertEqual(self.service.status()['comparisonDays'], 7)

    def test_regular_scheduler_skips_trend_only_competitors(self):
        self.confirm()
        manual = self.store.save_competitor({'name': '일반 대상', 'keyword': '일반 대상'})
        with patch.object(Controller, 'check_runtime', return_value=True):
            controller = Controller(self.store)
        controller.auto_enabled = True
        def finish_iteration(_):
            controller.stop_event.set()
            return True
        with patch.object(self.store, 'enqueue', wraps=self.store.enqueue) as enqueue, \
             patch.object(controller, 'execute'), patch.object(controller.stop_event, 'wait', side_effect=finish_iteration):
            controller.run()
            enqueue.assert_called_once_with(manual['id'], 20)
        controller.stop()
        comp = self.store.competitors()[0]
        self.store.save_competitor({'name': comp['name'], 'keyword': comp['keyword']}, comp['id'])
        self.assertTrue(self.store.competitors()[0]['trendOnly'])


if __name__ == '__main__':
    unittest.main()
