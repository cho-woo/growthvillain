import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import Store, Controller
from catalog import public_card
from archive_publisher import ArchivePublisher


class LiveControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.web = self.root / 'web'
        self.web.mkdir()
        self.store = Store(self.root/'data', self.web)
        self.runtime = patch.object(Controller, 'check_runtime', return_value=False)
        self.runtime.start()

    def tearDown(self):
        self.runtime.stop()
        self.store.close()
        self.tmp.cleanup()

    def test_persistent_switch_cancels_waiting_jobs_without_false_success(self):
        brand = self.store.save_competitor({'name':'브랜드','keyword':'브랜드','intervalHours':6})
        c = Controller(self.store)
        c.set_auto(True)
        self.assertTrue(Controller(self.store).auto_enabled)
        self.assertIsNotNone(c.status()['nextRunAt'])
        job = self.store.enqueue(brand['id'], 1)
        c.set_auto(False)
        self.assertFalse(Controller(self.store).auto_enabled)
        self.assertEqual(self.store.jobs()[0]['status'], 'canceled')
        self.assertIsNone(c.status()['lastSuccessAt'])
        self.assertIsNone(c.status()['nextRunAt'])

    def test_public_cards_explicitly_allow_fields(self):
        result = public_card({'id':'123456','media':[], 'employee_notes':'SECRET',
                              'localPath':'PRIVATE', 'deliveryStatus':'ended', 'startedAt':'2026-01-01',
                              'endedAt':'2026-01-03'})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(result['durationLabel'], '3일 게재 후 종료')

    def test_archive_fingerprint_does_not_loop_on_its_own_success(self):
        p = self.web / 'tools/meta-ads/data'
        p.mkdir(parents=True)
        status = {'automations':[{'id':'meta-ads','enabled':True}], 'updatedAt':'old',
                  'publication':{'enabled':True,'lastSuccessAt':None,'error':None}}
        (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
        publisher = ArchivePublisher(self.store)
        with patch('archive_publisher.time.time', return_value=3601):
            before = publisher.fingerprint()
            status.update(updatedAt='new', publication={'enabled':True,'lastSuccessAt':'first','error':None})
            (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
            first_success = publisher.fingerprint()
            self.assertNotEqual(before, first_success)
            status.update(updatedAt='newer', publication={'enabled':True,'lastSuccessAt':'second',
                                                         'lastAttemptAt':'now','state':'publishing','error':None})
            (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
            self.assertEqual(first_success, publisher.fingerprint())
            status['publication']['error'] = '게시 실패'
            (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
            failed = publisher.fingerprint()
            self.assertNotEqual(first_success, failed)
            status['publication']['error'] = None
            (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
            self.assertEqual(first_success, publisher.fingerprint())
            status['publication']['enabled'] = False
            (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
            self.assertNotEqual(first_success, publisher.fingerprint())
            status['publication']['enabled'] = True
            status['automations'][0]['enabled'] = False
            (p/'automation.json').write_text(json.dumps(status), encoding='utf-8')
            self.assertNotEqual(first_success, publisher.fingerprint())

    def test_trend_collection_obeys_meta_switch(self):
        c = Controller(self.store)
        c.trends.auto_enabled = True
        with patch.object(c.trends, 'candidates') as candidates:
            self.assertEqual(c.trends.dispatch_ready(), 0)
            candidates.assert_not_called()


if __name__ == '__main__':
    unittest.main()
