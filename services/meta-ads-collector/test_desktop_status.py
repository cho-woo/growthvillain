import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automation_bridge import (KST, cross_kind_ready, file_lock, publish_slot,
                               read_json, write_json, Heartbeat)
from automation_manager import heartbeat_status, AutomationManager
from beauty_scheduler import publication_time, next_collection, pending_article
from desktop_status import countdown, row_view, LocalClient, interval_label


class DesktopStatusTests(unittest.TestCase):
    def test_disconnect_never_keeps_green_or_allows_toggle(self):
        view = row_view({'enabled': True, 'running': True, 'controllable': True}, False)
        self.assertTrue(view['disabled'])
        self.assertIn('OFF', view['label'])
        self.assertIn('확인 불가', view['detail'])

    def test_running_waiting_and_pausing_are_different(self):
        row = {'enabled': True, 'running': True, 'controllable': True}
        self.assertIn('실행 중', row_view(row, True)['label'])
        self.assertIn('대기', row_view(dict(row, running=False), True)['label'])
        self.assertIn('마무리', row_view(dict(row, enabled=False), True)['label'])
        self.assertIn('일시 정지', row_view(dict(row, enabled=False, running=False), True)['label'])

    def test_countdown_understands_kst_and_missing_dates(self):
        self.assertEqual(countdown('2026-10-07T18:44:10+09:00', datetime(2026,10,7,9,44,0,tzinfo=timezone.utc).timestamp()), '10초 후')
        self.assertEqual(countdown('2026-10-07T18:44:10', datetime(2026,10,7,9,44,0,tzinfo=timezone.utc).timestamp()), '10초 후')
        self.assertEqual(countdown(None), '다음 일정 없음')
        self.assertEqual(interval_label(21600), '6시간')

    def test_localclient_does_not_allow_remote_addresses_or_id_paths(self):
        self.assertEqual(LocalClient().origin, 'http://127.0.0.1:4177')
        with self.assertRaises(ValueError): LocalClient('https://outside.invalid')
        with self.assertRaises(ValueError): LocalClient().switch('../../token', True)

    def test_meta_cadence_visible(self):
        view = row_view({'id':'meta-ads', 'enabled':True, 'intervalSeconds':21600,
                         'statusCheckIntervalSeconds':3600, 'statusCheckBatchSize':10}, True)
        self.assertIn('수집 6시간', view['detail'])
        self.assertIn('10개/1시간', view['detail'])


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.current = datetime(2026,10,7,12,0,tzinfo=KST)

    def test_publication_waits_three_hours_on_both_sides_of_food(self):
        food = {'jobs':[{'time':'2026-10-07T11:50:00', 'done':True}, {'time':'2026-10-07T18:44:00'}]}
        self.assertEqual(publication_time(self.current,food), self.current.replace(hour=14,minute=50))
        self.assertEqual(publication_time(self.current.replace(hour=16),food), self.current.replace(hour=21,minute=44))

    def test_ledger_actual_finish_extends_gap(self):
        actual = {'automationId':'food-blog','finishedAt':'2026-10-07T12:10:00+09:00'}
        self.assertEqual(publication_time(self.current,{},actual),self.current.replace(hour=15,minute=10))
        self.assertFalse(cross_kind_ready('beauty-blog',actual,self.current.replace(hour=13)))
        self.assertTrue(cross_kind_ready('food-blog',actual,self.current.replace(hour=13)))

    def test_daily_schedule_and_initial_collection(self):
        self.assertEqual(next_collection(self.current,None),self.current)
        self.assertEqual(next_collection(self.current,'2026-10-07'),datetime(2026,10,8,7,tzinfo=KST))
        self.assertEqual(next_collection(self.current.replace(hour=6),'2026-10-06'),self.current.replace(hour=7))

    def test_reference_drafts_and_receipts_are_excluded(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            write_json(root/'drafts/ref/article.json', {'status':'reference_only','goodsNo':'A000000000001','generatedAt':self.current.isoformat()})
            self.assertIsNone(pending_article(root))
            path=root/'drafts/approved/article.json'
            write_json(path,{'status':'draft','goodsNo':'A000000000002','generatedAt':self.current.isoformat()})
            self.assertEqual(pending_article(root),path)
            write_json(root/'state/publications/blog-9-A000000000002.json',{'status':'unknown'})
            self.assertIsNone(pending_article(root))

    def test_pause_prevents_new_attempt_and_shared_lock_excludes_other_processes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with publish_slot('food-blog',root) as allowed:
                self.assertFalse(allowed)
            write_json(root/'control.json',{'food-blog':True,'beauty-blog':True})
            with publish_slot('food-blog',root) as allowed:
                self.assertTrue(allowed)
                with publish_slot('beauty-blog',root) as other:
                    self.assertFalse(other)
            self.assertEqual(read_json(root/'publication-ledger.json')['automationId'],'food-blog')

    def test_stale_heartbeat_is_offline_and_disabled_running_finishes(self):
        old={'heartbeatAt':(self.current-timedelta(seconds=40)).isoformat(),'state':'running','running':True}
        self.assertEqual(heartbeat_status('food-blog','Food',old,True,self.current)['state'],'offline')
        old['heartbeatAt']=self.current.isoformat()
        self.assertEqual(heartbeat_status('food-blog','Food',old,False,self.current)['state'],'stopping')

    def test_manager_off_is_cooperative_and_retains_flags(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            manager=AutomationManager(root=root)
            with patch.object(manager,'tick') as tick:
                manager.set_enabled('beauty-blog',True)
                manager.set_enabled('food-blog',False)
                self.assertTrue(read_json(root/'control.json')['beauty-blog'])
                self.assertFalse(read_json(root/'control.json')['food-blog'])
                tick.assert_called_once()
            with self.assertRaises(ValueError): manager.set_enabled('unregistered',True)


if __name__ == '__main__':
    unittest.main()
