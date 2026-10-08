"""Persistent request pacing, capacity reserves and single-worker fairness."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from collection_guard import CollectionGuard, MIN_FREE_BYTES
from server import Store, Controller
from test_trend_service import snapshots


class CollectionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.web = self.base / 'web'
        self.web.mkdir()
        self.store = Store(self.base / 'private', self.web)
        self.runtime = patch.object(Controller, 'check_runtime', return_value=False)
        self.runtime.start()
        self.disk = patch('collection_guard.shutil.disk_usage', return_value=Mock(free=20*1024**3))
        self.disk_mock = self.disk.start()
        self.controller = Controller(self.store)

    def tearDown(self):
        self.runtime.stop()
        self.disk.stop()
        self.store.close()
        self.temp.cleanup()

    def card(self):
        value = {'id': '123456789', 'media': [], 'collectedAt': '2026-10-01T00:00:00+00:00'}
        self.store.write('INSERT INTO ads(id,payload) VALUES(?,?)', (value['id'], json.dumps(value)))
        return value

    def competitor(self):
        return self.store.save_competitor({'name': '공개 검색어', 'keyword': '공개 검색어', 'intervalHours': 1})

    def trend(self):
        current, previous = snapshots(names=('공개 급상승',))
        self.controller.trends.record_snapshots(current, previous, current['category'])
        self.controller.trends.save_settings({'autoEnabled': True})
        return self.controller.trends

    def test_repeated_blocks_wait_one_six_twenty_four_hours_and_persist(self):
        clock = 2000000000
        guard = self.controller.collection_guard
        for delay in (3600, 21600, 86400, 86400):
            with patch('collection_guard.time.time', return_value=clock):
                guard.blocked()
                status = CollectionGuard(self.store).status()
                self.assertEqual(status['state'], 'blocked')
                self.assertEqual(datetime.fromisoformat(status['nextAllowedAt']).timestamp(), clock+delay)
                guard.failed()
                self.assertEqual(guard.status()['blockedUntil'], status['blockedUntil'])
            clock += delay+1
        with patch('collection_guard.time.time', return_value=clock):
            self.assertTrue(guard.allowed())
            guard.succeeded()
            self.assertEqual(CollectionGuard(self.store).status()['blockStreak'], 0)
            guard.blocked()
            self.assertEqual(datetime.fromisoformat(guard.status()['nextAllowedAt']).timestamp(), clock+3600)

    def test_generic_error_wait_is_five_minutes_and_survives_restart(self):
        with patch('collection_guard.time.time', return_value=2000000000):
            self.controller.collection_guard.failed()
            status = CollectionGuard(self.store).status()
            self.assertEqual(status['state'], 'failure')
            self.assertEqual(datetime.fromisoformat(status['nextAllowedAt']).timestamp(), 2000000300)
        with patch('collection_guard.time.time', return_value=2000000301):
            self.assertTrue(CollectionGuard(self.store).allowed())

    def test_status_success_cannot_reset_search_block_escalation(self):
        guard = self.controller.collection_guard
        with patch('collection_guard.time.time', return_value=2000000000):
            guard.blocked()
            guard.succeeded(reset_blocks=False)
            self.assertEqual(guard.status()['state'], 'blocked')
        with patch('collection_guard.time.time', return_value=2000003601):
            guard.succeeded(reset_blocks=False)
            self.assertEqual(guard.status()['blockStreak'],1)
            self.assertEqual(guard.status()['state'],'ready')
            guard.blocked()
            self.assertEqual(datetime.fromisoformat(guard.status()['nextAllowedAt']).timestamp(),2000003601+21600)
        self.assertEqual(CollectionGuard(self.store).status()['blockStreak'],2)

    def test_hourly_status_appointment_is_clamped_to_fifteen_minutes_on_upgrade(self):
        self.store.set_setting('nextStatusCheck',2000003600)
        with patch('server.time.time', return_value=2000000000):
            Controller(self.store)
            self.assertEqual(self.store.setting('nextStatusCheck'),2000000900)
            self.store.set_setting('nextStatusCheck',2000000123)
            Controller(self.store)
            self.assertEqual(self.store.setting('nextStatusCheck'),2000000123)

    def test_either_drive_at_reserve_stops_media_but_not_exact_id_checks(self):
        for free_values in ((MIN_FREE_BYTES, MIN_FREE_BYTES+1), (MIN_FREE_BYTES+1, MIN_FREE_BYTES)):
            self.disk_mock.side_effect = lambda path: Mock(free=free_values[0 if path == self.store.root else 1])
            self.assertEqual(self.controller.collection_guard.status()['state'], 'storage')
            self.assertFalse(self.controller.collection_guard.allowed())
            self.assertTrue(self.controller.collection_guard.allowed(media=False))
        self.disk_mock.side_effect = OSError('drive gone')
        self.assertFalse(self.controller.collection_guard.allowed())

    def test_guard_writers_always_acquire_store_before_guard_lock(self):
        events = []
        original = self.store.lock
        class AuditLock:
            def __init__(self, name, underlying=None): self.name, self.underlying = name, underlying or threading.RLock()
            def __enter__(self):
                self.underlying.acquire()
                events.append(self.name)
                return self
            def __exit__(self, *args): self.underlying.release()
        self.store.lock = AuditLock('store', original)
        self.controller.collection_guard.lock = AuditLock('guard')
        try:
            for operation in ('blocked', 'failed', 'succeeded'):
                events.clear()
                getattr(self.controller.collection_guard, operation)()
                self.assertEqual(events[:2], ['store', 'guard'])
        finally:
            self.store.lock = original

    def test_policy_is_288_queries_five_minutes_100_ads_but_rank_stays_hourly(self):
        trends = self.trend()
        self.controller.set_auto(True)
        policy = trends.collection_policy()
        self.assertEqual((policy['maxDailyQueries'], policy['maxAdsPerQuery'], policy['intervalSeconds']), (288, 100, 300))
        self.assertEqual((policy['maxPending'], policy['keywordCooldownSeconds']), (1, 86400))
        self.assertEqual(trends.status()['intervalSeconds'], 3600)
        self.assertEqual(trends.dispatch_ready(), 1)
        self.assertEqual(self.store.jobs()[0]['limit'], 100)
        self.assertEqual(trends.dispatch_ready(), 0)

    def test_guard_holds_trend_dispatch_without_falsely_switching_meta_off(self):
        trends = self.trend()
        self.controller.set_auto(True)
        self.controller.collection_guard.blocked()
        policy = trends.collection_policy()
        self.assertTrue(policy['metaAutoEnabled'])
        self.assertFalse(policy['enabled'])
        self.assertEqual(policy['collectionGuard']['state'], 'blocked')
        self.assertIsNotNone(policy['nextDispatchAt'])
        self.assertEqual(trends.dispatch_ready(), 0)
        self.assertEqual(self.store.jobs(), [])
        with self.assertRaisesRegex(ValueError, '접근 제한'):
            trends.collect(trends.candidates()[0]['dispatchKey'])

    def test_five_minute_dispatch_boundary_and_failed_key_not_automatically_retried(self):
        trends = self.controller.trends
        current, previous = snapshots(names=('급상승하나','급상승둘'))
        trends.record_snapshots(current, previous, current['category'])
        trends.save_settings({'autoEnabled':True})
        self.controller.auto_enabled = True
        instant = datetime.now(timezone.utc).timestamp()
        with patch('trend_service.time.time', return_value=instant):
            self.assertEqual(trends.dispatch_ready(), 1)
        failed = self.store.jobs()[0]
        self.store.write("UPDATE jobs SET status='failed' WHERE id=?", (failed['id'],))
        with patch('trend_service.time.time', return_value=instant+299):
            self.assertEqual(trends.dispatch_ready(), 0)
        with patch('trend_service.time.time', return_value=instant+300):
            self.assertEqual(trends.dispatch_ready(), 1)
        self.assertEqual(len(self.store.jobs()), 2)
        self.assertNotEqual(self.store.jobs()[0]['keyword'], failed['keyword'])

    def prepared_run(self, code, *, trailing=False, completion=None):
        brand = self.competitor()
        job = self.store.enqueue(brand['id'],100)
        row = self.store.rows('SELECT * FROM jobs WHERE id=?',(job['id'],))[0]
        directory = self.store.root/'runs'/job['id']
        directory.mkdir(parents=True)
        (directory/'image.jpg').write_bytes(b'test public image')
        data = {'library_id':'123456789','advertiser':'공개광고주','_saved_images':['image.jpg'],
                '_saved_videos':[],'_saved_posters':[],'_keyword':job['keyword'],'_collected_at':'2026-10-08T00:00:00+00:00'}
        (directory/'cards.jsonl').write_bytes((json.dumps(data)+'\n').encode()+ (b'{"library_id":' if trailing else b''))
        if completion:
            (directory/'completion.json').write_text(json.dumps({'reason':completion}))
        process = Mock(returncode=code)
        process.poll.return_value = code
        return row, directory, process

    def test_blocked_partial_keeps_complete_rows_and_cooldown(self):
        row, directory, process = self.prepared_run(20,trailing=True)
        with patch('server.subprocess.Popen', return_value=process):
            self.controller.execute(row)
        job = self.store.jobs()[0]
        self.assertEqual((job['status'],job['imported']),('done',1))
        self.assertIn('일부 수집',job['message'])
        self.assertIn('접근 제한',job['message'])
        self.assertEqual(self.controller.collection_guard.status()['state'],'blocked')
        self.assertEqual(len(self.store.cards()),1)
        self.assertTrue((directory/'cards.jsonl').read_bytes().endswith(b'{"library_id":'))

    def test_hard_timeout_imports_completed_rows_with_error_wait(self):
        row, directory, process = self.prepared_run(None,trailing=True)
        with patch('server.subprocess.Popen',return_value=process), patch('server.time.monotonic',side_effect=[0,901]), patch.object(self.controller,'kill_process') as kill, patch.object(self.controller.stop_event,'wait',return_value=False):
            self.controller.execute(row)
        kill.assert_called_once()
        self.assertEqual(self.store.jobs()[0]['status'],'done')
        self.assertIn('일부 수집',self.store.jobs()[0]['message'])
        self.assertIn('시간 제한',self.store.jobs()[0]['message'])
        self.assertEqual(self.controller.collection_guard.status()['state'],'failure')

    def test_soft_budget_completion_is_partial_and_not_an_access_failure(self):
        row, directory, process = self.prepared_run(0,completion='time_budget')
        with patch('collection_guard.time.time',return_value=1000):
            self.controller.collection_guard.blocked()
        with patch('server.subprocess.Popen',return_value=process) as start:
            self.controller.execute(row)
        self.assertEqual(self.store.jobs()[0]['status'],'done')
        self.assertIn('일부 수집',self.store.jobs()[0]['message'])
        self.assertEqual(self.controller.collection_guard.status()['state'],'ready')
        self.assertEqual(self.controller.collection_guard.status()['blockStreak'],1)
        self.assertEqual(start.call_args.args[0][-2:],['--runtime-budget-seconds','840'])

    def test_partial_complete_malformed_row_is_not_silently_skipped(self):
        row, directory, process = self.prepared_run(1)
        with (directory/'cards.jsonl').open('ab') as stream: stream.write(b'{broken json}\n')
        with patch('server.subprocess.Popen',return_value=process):
            self.controller.execute(row)
        self.assertEqual(self.store.jobs()[0]['status'],'failed')
        self.assertEqual(self.store.cards(),[])

    def test_canceled_work_keeps_raw_rows_without_automatic_import(self):
        row, directory, process = self.prepared_run(20)
        def launch(*args,**kwargs):
            self.store.write("UPDATE jobs SET status='canceled' WHERE id=?",(row['id'],))
            return process
        with patch('server.subprocess.Popen',side_effect=launch):
            self.controller.execute(row)
        self.assertEqual(self.store.jobs()[0]['status'],'canceled')
        self.assertEqual(self.store.cards(),[])
        self.assertTrue((directory/'cards.jsonl').exists())
        self.assertEqual(self.controller.collection_guard.status()['state'],'ready')

    def test_import_checks_both_drive_reserves_after_child_finishes(self):
        row, directory, process = self.prepared_run(0)
        def launch(*args,**kwargs):
            self.disk_mock.return_value = Mock(free=MIN_FREE_BYTES)
            return process
        with patch('server.subprocess.Popen',side_effect=launch):
            self.controller.execute(row)
        self.assertEqual(self.store.jobs()[0]['status'],'failed')
        self.assertIn('원본은 보존',self.store.jobs()[0]['message'])
        self.assertEqual(self.store.cards(),[])
        self.assertEqual(self.controller.collection_guard.status()['state'],'storage')

    def test_guard_stops_both_existing_queue_and_new_regular_queue(self):
        brand = self.competitor()
        queued = self.store.enqueue(brand['id'], 100)
        self.controller.auto_enabled = True
        self.controller.collection_guard.blocked()
        self.card()
        with patch.object(self.controller, 'execute') as execute, patch.object(self.controller, 'check_saved_ads') as checks:
            self.controller.run_once()
            execute.assert_not_called()
            checks.assert_not_called()
        self.assertEqual(len(self.store.jobs()), 1)
        self.assertEqual(self.store.jobs()[0]['id'], queued['id'])
        with patch('server.subprocess.Popen') as process:
            self.controller.execute(self.store.rows('SELECT * FROM jobs')[0])
            process.assert_not_called()
        self.assertEqual(self.store.jobs()[0]['status'], 'queued')

    def test_due_status_batch_precedes_queue_then_regular_job_can_run(self):
        self.card()
        self.competitor()
        self.controller.auto_enabled = True
        def checked(): self.store.set_setting('nextStatusCheck', 2000000900)
        with patch('server.time.time', return_value=2000000000), patch.object(self.controller, 'execute') as execute, patch.object(self.controller, 'check_saved_ads', side_effect=checked) as check:
            self.controller.run_once()
            check.assert_called_once()
            execute.assert_not_called()
            self.assertEqual(self.store.jobs()[0]['limit'], 100)
            self.controller.run_once()
            self.assertEqual(check.call_count, 1)
            execute.assert_called_once()

    def test_disk_hold_does_not_prevent_due_status_batch(self):
        self.card()
        self.competitor()
        self.controller.auto_enabled = True
        self.disk_mock.return_value = Mock(free=MIN_FREE_BYTES)
        with patch.object(self.controller, 'check_saved_ads') as check, patch.object(self.controller, 'execute') as execute:
            self.controller.run_once()
            check.assert_called_once()
            execute.assert_not_called()
        self.assertEqual(self.store.jobs(), [])

    def test_status_batch_failure_and_block_are_shared_with_search(self):
        self.card()
        def response(command, **kwargs):
            output = Path(command[command.index('--output')+1])
            output.write_text(json.dumps({'observations': [{'id':'123456789','outcome':'blocked','checkedAt':'2026-10-08T00:00:00+00:00'}]}))
            return Mock(returncode=0)
        with patch('server.subprocess.run', side_effect=response):
            self.controller.check_saved_ads()
        self.assertEqual(self.controller.collection_guard.status()['state'], 'blocked')
        self.assertGreater(self.store.setting('nextStatusCheck'), 0)
        self.assertFalse(self.controller.status_check_running)

    def test_live_row_has_hold_reason_and_fifteen_minute_status_cadence(self):
        self.competitor()
        self.controller.auto_enabled = True
        self.controller.collection_guard.blocked()
        row = self.controller.automation_status()['automations'][0]
        self.assertEqual((row['state'],row['statusCheckIntervalSeconds'],row['statusCheckBatchSize']), ('waiting',900,10))
        self.assertIn('접근 제한', row['message'])
        self.assertTrue(row['enabled'])
        self.assertEqual(row['nextRunAt'], row['collectionGuard']['nextAllowedAt'])


if __name__ == '__main__':
    unittest.main()
