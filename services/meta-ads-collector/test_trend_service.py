"""Queue, privacy and schedule contracts; generated rank fixtures are test-only."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from server import Store, Controller
from storage_config import StorageUnavailable
from trend_service import TrendService, KST, SOURCE_URL, validate_recent_source_date


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

    @patch('trend_service.DAILY_QUERY_LIMIT', 5)
    def test_auto_is_opt_in_one_at_a_time_and_respects_configured_daily_cap(self):
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

    def test_health_and_diet_dual_default_and_supported_food_categories(self):
        self.assertEqual(self.service.settings()['category'], '50000023')
        self.assertEqual(self.service.settings()['categories'], ['50000023', '50000024'])
        for category in ('50000006', '50000023', '50001899', '50001090', '50001092', '50017220', '50018919', '50000024'):
            self.service.save_settings({'category': category})
            self.assertEqual(self.service.settings()['category'], category)

    def test_active_category_filters_history_before_limit_and_preserves_raw_records(self):
        self.service.save_settings({'category': '50001092'})
        self.seed(category='50001092', names=('마그네슘',), days_ago=2)
        self.seed(category='50000023', names=('인삼',), days_ago=1)
        history = self.service.history(limit=1)
        self.assertEqual([item['keyword'] for item in history], ['마그네슘'])
        public = self.service.export()
        self.assertEqual({item['category'] for item in public['history']}, {'50001092'})
        self.assertEqual({item['category'] for item in public['candidates']}, {'50001092'})
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_events')), 2)
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_snapshots')), 4)
        self.service.save_settings({'category': '50000023'})
        self.assertEqual([item['keyword'] for item in self.service.history()], ['인삼'])
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_events')), 2)

    def test_no_active_snapshot_never_exports_other_category_rank_history(self):
        self.service.save_settings({'category': '50001092'})
        self.seed(category='50000023', names=('인삼',))
        public = self.service.export()
        self.assertEqual(public['settings']['category'], '50001092')
        self.assertEqual(public['history'], [])
        self.assertEqual(public['candidates'], [])
        self.assertIsNone(public['sourceDate'])

    def test_prior_category_manual_key_cannot_return_or_retry_its_existing_job(self):
        self.service.save_settings({'category': '50000023'})
        self.seed(category='50000023')
        old_key = self.candidate()['dispatchKey']
        old_job = self.service.collect(old_key)
        self.store.write("UPDATE jobs SET status='done' WHERE id=?", (old_job['id'],))
        self.seed(category='50001092', names=('영양제대상',))
        self.service.save_settings({'category': '50001092'})
        with self.assertRaisesRegex(ValueError, '현재 선택된 카테고리'):
            self.service.collect(old_key)
        self.store.write("UPDATE jobs SET status='failed' WHERE id=?", (old_job['id'],))
        with self.assertRaisesRegex(ValueError, '현재 선택된 카테고리'):
            self.service.collect(old_key)
        self.assertEqual(len(self.store.jobs()), 1)
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_dispatches')), 1)

    def test_automatic_dispatch_uses_only_active_category_even_when_older_other_history_exists(self):
        self.service.save_settings({'category': '50001092'})
        self.seed(category='50000023', names=('다른분야과거',), days_ago=5)
        self.seed(category='50001092', names=('영양제급상승',))
        self.service.save_settings({'autoEnabled': True})
        self.assertEqual(self.service.dispatch_ready(), 1)
        self.assertEqual([job['keyword'] for job in self.store.jobs()], ['영양제급상승'])

    def test_new_default_does_not_overwrite_an_explicit_existing_category(self):
        self.service.save_settings({'category': '50000023'})
        resumed = TrendService(self.store)
        try:
            self.assertEqual(resumed.settings()['category'], '50000023')
        finally:
            resumed.stop()

    def test_recent_source_date_must_be_a_strict_completed_kst_calendar_day(self):
        current = datetime(2026, 10, 8, 0, 30, tzinfo=KST)
        for value in ('2026-10-07', '2026-10-06', '2026-10-05'):
            self.assertEqual(validate_recent_source_date(value, current).isoformat(), value)
        for value in ('2026-10-08', '2026-10-09', '2026-10-04', '20261007',
                      '2026-10-07T00:00:00', '2026-02-30', None, 20261007):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_recent_source_date(value, current)

    def fake_successful_scan(self, days_ago):
        self.service.save_settings({'category': '50000023'})
        current, previous = snapshots(days_ago=days_ago)
        def launch(command, **options):
            self.assertNotIn('--date', command)
            self.assertEqual(command[command.index('--category')+1], '50000023')
            output = Path(command[command.index('--output')+1])
            output.write_text(json.dumps({'current': current, 'previous': previous}), encoding='utf-8')
            process = Mock()
            process.poll.return_value = 0
            process.returncode = 0
            return process
        with patch('trend_service.subprocess.Popen', side_effect=launch):
            self.service._scan(self.service.settings())
        return current, previous

    def test_scan_uses_observed_public_date_when_source_is_two_days_behind(self):
        current, _ = self.fake_successful_scan(2)
        self.assertIsNone(self.service.status()['error'])
        self.assertEqual(self.service.status()['sourceDate'], current['date'])
        self.assertEqual(self.service.history()[0]['sourceAgeDays'], 2)
        self.assertEqual(self.service.history()[0]['periodDays'], 7)

    def test_scan_rejects_today_future_and_over_three_days_without_replacing_good_snapshot(self):
        good, _ = self.seed()
        for days_ago in (0, -1, 4):
            with self.subTest(days_ago=days_ago):
                self.fake_successful_scan(days_ago)
                self.assertEqual(self.service.status()['sourceDate'], good['date'])
                self.assertIsNotNone(self.service.status()['error'])

    def test_two_day_old_cached_source_is_rechecked_on_next_hour(self):
        self.seed(days_ago=2)
        self.service.save_settings({'autoEnabled': True})
        with patch.object(self.service, 'scan') as scan, patch.object(self.service, 'dispatch_ready'):
            self.service.tick()
            scan.assert_called_once()

    def test_legacy_single_settings_read_compatibility_and_partial_updates(self):
        legacy = {'category': '50000006', 'minimumRise': 13, 'newTop': 10}
        self.store.write('UPDATE trend_settings SET payload=? WHERE id=1', (json.dumps(legacy),))
        self.assertEqual(self.service.settings()['categories'], ['50000006'])
        self.assertEqual(json.loads(self.store.rows('SELECT payload FROM trend_settings')[0]['payload']), legacy)
        self.service.save_settings({'autoEnabled': True})
        self.assertEqual(self.service.settings()['categories'], ['50000006'])
        self.assertEqual(self.service.settings()['minimumRise'], 13)

    def test_dual_setting_validation_preserves_previous_selection(self):
        expected = self.service.settings()
        for categories in ([], ['50000023', '50000023'], ['50000023', '50000024', '50001092'],
                           '50000023', ['missing'], [None]):
            with self.subTest(categories=categories), self.assertRaises(ValueError):
                self.service.save_settings({'categories': categories})
            self.assertEqual(self.service.settings(), expected)
        with self.assertRaises(ValueError):
            self.service.save_settings({'category': '50001092', 'categories': ['50000023', '50000024']})
        self.service.save_settings({'categories': ['50000024', '50000023'], 'newTop': 15})
        self.assertEqual(self.service.settings()['category'], '50000024')
        self.service.save_settings({'autoEnabled': True})
        self.assertEqual(self.service.settings()['categories'], ['50000024', '50000023'])

    def test_dual_candidates_and_history_preserve_category_and_hide_outside_records(self):
        self.seed(category='50000023', names=('건강급상승',), days_ago=2)
        self.seed(category='50000024', names=('다이어트급상승',), days_ago=1)
        self.seed(category='50001092', names=('다른분야급상승',), days_ago=1)
        public = self.service.export()
        for field in ('candidates', 'history'):
            actual = {(item['category'], item['keyword']) for item in public[field]}
            self.assertEqual(actual, {('50000023', '건강급상승'), ('50000024', '다이어트급상승')})
        self.assertEqual(len(self.store.rows('SELECT * FROM trend_events')), 3)
        for candidate in self.service.candidates():
            self.service.collect(candidate['dispatchKey'])
        self.assertEqual({job['keyword'] for job in self.store.jobs()}, {'건강급상승', '다이어트급상승'})

    def test_same_keyword_in_both_categories_keeps_rank_evidence_but_global_query_cooldown(self):
        self.seed(category='50000023', names=('마그네슘',))
        self.seed(category='50000024', names=('마그네슘',))
        candidates = self.service.candidates()
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len(self.service.history()), 2)
        self.assertEqual(len(self.service.collection_candidates()), 1)
        self.service.collect(candidates[0]['dispatchKey'])
        self.store.write("UPDATE jobs SET status='done'")
        with self.assertRaisesRegex(ValueError, '24시간'):
            self.service.collect(candidates[1]['dispatchKey'])
        self.assertEqual(len(self.store.jobs()), 1)

    def test_last_success_uses_selected_category_checks_not_global_last_import(self):
        with patch('trend_service.now', return_value='2026-10-08T00:10:00+00:00'):
            self.seed(category='50000023', names=('건강급상승',))
        with patch('trend_service.now', return_value='2026-10-08T00:20:00+00:00'):
            self.seed(category='50000024', names=('다이어트급상승',))
        with patch('trend_service.now', return_value='2026-10-08T00:30:00+00:00'):
            self.seed(category='50001092', names=('다른분야',))
        status = self.service.status()
        self.assertEqual(status['lastSuccessAt'], '2026-10-08T00:20:00+00:00')
        summaries = {row['category']: row for row in status['sourceSummaries']}
        self.assertEqual(summaries['50000023']['categoryName'], '건강식품')
        self.assertEqual(summaries['50000024']['categoryName'], '다이어트식품')
        self.assertEqual(summaries['50000023']['lastChecked'], '2026-10-08T00:10:00+00:00')
        self.service.save_settings({'category': '50000006'})
        self.assertIsNone(self.service.status()['lastSuccessAt'])

    def test_full_dual_category_backlog_exceeds_ui_limit_and_oldest_can_dispatch(self):
        # Generated observations only: each day/category has 100 distinct rises.
        self.seed()
        template = self.store.rows('SELECT payload FROM trend_events')[0]['payload']
        today = datetime.now(KST).date()
        records = []
        for category in ('50000023', '50000024', '50001092'):
            for age in range(1, 16):
                day = (today - timedelta(days=age)).isoformat()
                previous = (today - timedelta(days=age+7)).isoformat()
                for number in range(100):
                    key = f'{category}-{age:02d}-{number:03d}'
                    payload = dict(json.loads(template), category=category, date=day,
                                   currentDate=day, previousDate=previous, keyword=key)
                    records.append((key, category, day, day+'T00:00:00+00:00',
                                    day+'T00:00:00+00:00', json.dumps(payload)))
        self.store.db.executemany('INSERT INTO trend_events VALUES(?,?,?,?,?,?)', records)
        self.store.db.commit()
        self.assertEqual(len(self.service.history()), 2000)
        backlog = self.service.collection_candidates()
        # 2,800 generated in-range events plus the seed's current candidate.
        self.assertEqual(len(backlog), 2801)
        self.assertEqual({item['category'] for item in backlog}, {'50000023', '50000024'})
        self.assertEqual(backlog[0]['sourceAgeDays'], 14)
        self.assertNotIn(backlog[0]['dispatchKey'], {item['dispatchKey'] for item in self.service.history()})
        self.service.save_settings({'autoEnabled': True})
        self.assertEqual(self.service.dispatch_ready(), 1)
        self.assertEqual(self.store.jobs()[0]['keyword'], backlog[0]['keyword'])

    def test_history_orders_by_source_date_and_backlog_sql_excludes_expired_rows(self):
        # Deliberately observe the oldest source last: observed_at must not decide
        # source-date order, and SQLite CURRENT_DATE must not replace the column.
        for index, age in enumerate((1, 3, 15)):
            with patch('trend_service.now', return_value=f'2026-10-08T00:0{index}:00+00:00'):
                self.seed(names=(f'순위{age}',), days_ago=age)
        self.assertEqual([item['sourceAgeDays'] for item in self.service.history()], [1, 3, 15])
        self.assertEqual([item['sourceAgeDays'] for item in self.service._backlog_history()], [1, 3])

    def run_dual_scan(self, outcomes):
        calls = []
        def launch(command, **options):
            self.assertNotIn('--date', command)
            category = command[command.index('--category')+1]
            calls.append(category)
            process = Mock()
            days_ago = outcomes.get(category)
            if days_ago is None:
                process.poll.return_value = 1
                process.returncode = 1
                return process
            current, previous = snapshots(category, names=(f'분야{category}',), days_ago=days_ago)
            output = Path(command[command.index('--output')+1])
            output.write_text(json.dumps({'current': current, 'previous': previous}), encoding='utf-8')
            process.poll.return_value = 0
            process.returncode = 0
            return process
        with patch('trend_service.subprocess.Popen', side_effect=launch):
            self.service._scan(self.service.settings())
        return calls

    def test_dual_scan_runs_in_order_and_keeps_each_observed_public_date(self):
        self.assertEqual(self.run_dual_scan({'50000023': 2, '50000024': 1}), ['50000023', '50000024'])
        public = self.service.export()
        summaries = {row['category']: row for row in public['sourceSummaries']}
        self.assertEqual(summaries['50000023']['sourceDate'], snapshots(days_ago=2)[0]['date'])
        self.assertEqual(summaries['50000024']['sourceDate'], snapshots(days_ago=1)[0]['date'])
        self.assertTrue(all(row['error'] is None for row in summaries.values()))
        self.assertIsNone(public['error'])

    def test_one_category_failure_does_not_prevent_other_success_and_survives_restart(self):
        for failed in ('50000023', '50000024'):
            with self.subTest(failed=failed):
                succeeded = '50000024' if failed == '50000023' else '50000023'
                good, _ = self.seed(category=failed, names=('보존할기록',), days_ago=3)
                self.run_dual_scan({failed: None, succeeded: 2})
                summaries = {row['category']: row for row in self.service.status()['sourceSummaries']}
                self.assertEqual(summaries[failed]['sourceDate'], good['date'])
                self.assertIsNotNone(summaries[failed]['error'])
                self.assertIsNone(summaries[succeeded]['error'])
                self.assertEqual(summaries[succeeded]['sourceDate'], snapshots(days_ago=2)[0]['date'])
                other = TrendService(self.store)
                try:
                    errors = {row['category']: row['error'] for row in other.status()['sourceSummaries']}
                    self.assertIsNotNone(errors[failed])
                    self.assertIsNone(errors[succeeded])
                finally:
                    other.stop()

    def test_category_recovery_clears_only_its_error_and_other_scope_hides_old_errors(self):
        self.run_dual_scan({})
        self.assertEqual(len(self.service.status()['lastError']['categories']), 2)
        self.run_dual_scan({'50000023': 2})
        self.assertEqual(self.service.status()['lastError']['categories'], ['50000024'])
        self.service.save_settings({'category': '50001092'})
        self.assertIsNone(self.service.status()['error'])
        self.assertEqual(self.service.status()['sourceSummaries'][0]['category'], '50001092')
        self.service.save_settings({'categories': ['50000023', '50000024']})
        self.assertEqual(self.service.status()['lastError']['categories'], ['50000024'])
        self.run_dual_scan({'50000023': 2, '50000024': 2})
        self.assertIsNone(self.service.status()['lastError'])

    def test_invalid_one_category_source_date_does_not_replace_it_or_block_other_category(self):
        good, _ = self.seed(category='50000023', days_ago=2)
        self.run_dual_scan({'50000023': 0, '50000024': 1})
        summaries = {row['category']: row for row in self.service.status()['sourceSummaries']}
        self.assertEqual(summaries['50000023']['sourceDate'], good['date'])
        self.assertIsNotNone(summaries['50000023']['error'])
        self.assertIsNone(summaries['50000024']['error'])

    def test_hourly_cache_requires_both_categories_to_be_finalized(self):
        self.seed(category='50000023')
        self.service.save_settings({'autoEnabled': True})
        with patch.object(self.service, 'scan') as scan, patch.object(self.service, 'dispatch_ready'):
            self.service.tick()
            scan.assert_called_once()
        self.seed(category='50000024')
        with patch.object(self.service, 'scan') as scan, patch.object(self.service, 'dispatch_ready'):
            self.service.tick()
            scan.assert_not_called()

    def test_older_observed_date_cannot_regress_snapshot_or_refresh_last_success(self):
        with patch('trend_service.now', return_value='2026-10-08T00:10:00+00:00'):
            current, previous = self.seed(category='50000023', names=('최신기록',))
        self.run_dual_scan({'50000023': 2, '50000024': 1})
        source = self.service.status()['sourceSummaries'][0]
        self.assertEqual(source['sourceDate'], current['date'])
        self.assertEqual(source['previousSourceDate'], previous['date'])
        self.assertEqual(source['lastChecked'], '2026-10-08T00:10:00+00:00')
        self.assertIn('이전 날짜', source['error'])

    def test_same_date_scan_can_correct_rows_and_advance_confirmation_time(self):
        with patch('trend_service.now', return_value='2026-10-08T00:10:00+00:00'):
            old, _ = self.seed(category='50000023', names=('교정전키워드',))
        with patch('trend_service.now', return_value='2026-10-08T00:20:00+00:00'):
            self.run_dual_scan({'50000023': 1, '50000024': 1})
        source = self.service.status()['sourceSummaries'][0]
        self.assertEqual(source['sourceDate'], old['date'])
        self.assertEqual(source['lastChecked'], '2026-10-08T00:20:00+00:00')
        actual = [item['keyword'] for item in self.service.candidates() if item['category'] == '50000023']
        self.assertEqual(actual, ['분야50000023'])

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
        self.service.save_settings({'category': '50000023'})
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
            enqueue.assert_called_once_with(manual['id'], 100)
        controller.stop()
        comp = self.store.competitors()[0]
        self.store.save_competitor({'name': comp['name'], 'keyword': comp['keyword']}, comp['id'])
        self.assertTrue(self.store.competitors()[0]['trendOnly'])


if __name__ == '__main__':
    unittest.main()
