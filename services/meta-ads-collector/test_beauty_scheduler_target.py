from contextlib import nullcontext
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import beauty_scheduler as scheduler


class BeautyTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'beauty'
        self.root.mkdir()
        self.hub = Path(self.temp.name)/'hub'
        self.hub.mkdir()
        self.food = Path(self.temp.name)/'food'
        self.food.mkdir()
        self.now = datetime(2026, 10, 7, 14, 0, tzinfo=scheduler.KST)
        self.config = {'naver_blog_id': 'vwhdngud', 'naver_category_no': 1,
                       'naver_category_name': '뷰티',
                       'naver_session_file': 'state/naver_blog_session-vwhdngud.json',
                       'restaurant_project': '../food'}
        scheduler.write_json(self.root/'config.json', self.config)
        self.state = {'collectionDate': '2026-10-07', 'lastCollectionOk': True,
                      'lastCollectionAt': '2026-10-07T07:00:00+09:00'}
        self.heartbeat = MagicMock()
        self.heartbeat.start.return_value = self.heartbeat

    def session(self):
        scheduler.write_json(self.root/self.config['naver_session_file'], {'cookies': []})

    def execute(self, *, sleep=None, enabled=True, article=True, permitted=True):
        scheduler.write_json(self.root/'state/scheduler.json', self.state)
        food_before = (self.food/'scheduler_state.json').read_bytes() if (self.food/'scheduler_state.json').exists() else None
        with (patch.object(scheduler, 'ROOT', self.root),
              patch.object(scheduler, 'hub_root', return_value=self.hub),
              patch.object(scheduler, 'Heartbeat', return_value=self.heartbeat),
              patch.object(scheduler, 'enabled', return_value=enabled),
              patch.object(scheduler, 'datetime') as clock,
              patch.object(scheduler, 'stamp', return_value=self.now.isoformat()),
              patch.object(scheduler, 'file_lock', side_effect=lambda *_: nullcontext(True)) as singleton,
              patch.object(scheduler, 'publish_slot', side_effect=lambda *_: nullcontext(permitted)) as slot,
              patch.object(scheduler, 'pending_article', return_value=self.root/'draft.json' if article else None),
              patch.object(scheduler, 'run_child', return_value=0) as child,
              patch.object(scheduler.time, 'sleep', side_effect=sleep or KeyboardInterrupt)):
            clock.now.return_value = self.now
            self.assertEqual(scheduler.main(), 0)
        food_after = (self.food/'scheduler_state.json').read_bytes() if (self.food/'scheduler_state.json').exists() else None
        self.assertEqual(food_before, food_after)
        singleton.assert_called_once_with(self.hub/'beauty-blog-process.lock')
        self.heartbeat.stop.assert_called_once()
        return child, slot, scheduler.read_json(self.root/'state/scheduler.json')

    def final_status(self):
        return self.heartbeat.update.call_args.kwargs

    def test_old_shared_session_does_not_enable_new_target(self):
        scheduler.write_json(self.root/'state/naver_blog_session.json', {'cookies': []})
        self.assertFalse(scheduler.publication_session_ready(self.root, self.config))
        self.session()
        self.assertTrue(scheduler.publication_session_ready(self.root, self.config))

    def test_missing_configured_session_or_blog_stays_blocked(self):
        self.assertFalse(scheduler.publication_session_ready(self.root, {}))
        self.session()
        self.assertFalse(scheduler.publication_session_ready(self.root, {'naver_session_file': self.config['naver_session_file']}))

    def test_legacy_success_is_not_new_target_success(self):
        state = {'lastPublicationOk': True, 'lastPublicationAt': self.now.isoformat(),
                 'lastSuccessAt': self.now.isoformat()}
        for old_target in [None, 'wdetector']:
            if old_target:
                state['lastPublicationBlogId'] = old_target
            self.assertEqual(scheduler.waiting_status(state, self.config, True, None, self.now),
                             ('waiting', '수집 ON · 확인된 발행용 초안 0개'))
            self.assertIsNone(scheduler.current_success_at(state, self.config))

    def test_new_target_success_is_shown(self):
        state = {**self.state, 'lastPublicationOk': True, 'lastPublicationBlogId': 'vwhdngud',
                 'lastPublicationAt': self.now.isoformat()}
        self.assertIn('최근 뷰티 발행 완료', scheduler.waiting_status(state, self.config, True, None, self.now)[1])
        self.assertEqual(scheduler.current_success_at(state, self.config), self.now.isoformat())

    def test_collection_success_remains_valid_after_target_change(self):
        state = {**self.state, 'lastPublicationOk': True, 'lastPublicationBlogId': 'wdetector',
                 'lastPublicationAt': self.now.isoformat()}
        self.assertEqual(scheduler.current_success_at(state, self.config), self.state['lastCollectionAt'])

    def test_legacy_publication_failure_does_not_block_new_target_message(self):
        state = {'lastPublicationOk': False, 'publicationAttemptDate': '2026-10-07',
                 'lastPublicationBlogId': 'wdetector'}
        self.assertEqual(scheduler.waiting_status(state, self.config, True, None, self.now)[0], 'waiting')
        state['lastPublicationBlogId'] = 'vwhdngud'
        self.assertEqual(scheduler.waiting_status(state, self.config, True, None, self.now)[0], 'blocked')

    def test_no_login_leaves_publication_and_food_untouched(self):
        self.state.update(lastPublicationOk=True, lastPublicationAt=self.now.isoformat())
        child, slot, after = self.execute()
        child.assert_not_called()
        slot.assert_not_called()
        self.assertEqual(after, self.state)
        status = self.final_status()
        self.assertEqual(status['state'], 'blocked')
        self.assertEqual(status['message'], 'vwhdngud 로그인 필요 · 수집 ON')
        self.assertEqual(status['nextRunAt'], '2026-10-08T07:00:00+09:00')
        self.assertEqual(status['lastSuccessAt'], self.state['lastCollectionAt'])

    def test_collection_still_runs_without_login(self):
        self.state.pop('collectionDate')
        child, slot, after = self.execute()
        child.assert_called_once_with('beauty_agent.py', 'run')
        slot.assert_not_called()
        self.assertEqual(after['collectionDate'], '2026-10-07')
        self.assertNotIn('publicationAttemptDate', after)
        self.assertEqual(self.final_status()['state'], 'blocked')
        self.assertEqual(self.final_status()['nextRunAt'], '2026-10-08T07:00:00+09:00')

    def test_login_file_appearing_restores_publication_without_restart(self):
        calls = 0
        def next_tick(_):
            nonlocal calls
            calls += 1
            if calls == 1:
                self.session()
                return
            raise KeyboardInterrupt
        child, slot, after = self.execute(sleep=next_tick)
        child.assert_called_once_with('publish_beauty.py', self.root/'draft.json')
        slot.assert_called_once_with('beauty-blog')
        self.assertEqual(after['lastPublicationBlogId'], 'vwhdngud')
        self.assertTrue(after['lastPublicationOk'])
        self.assertEqual(after['publicationAttemptDate'], '2026-10-07')

    def test_existing_daily_attempt_is_preserved_after_target_change(self):
        self.session()
        self.state.update(publicationAttemptDate='2026-10-07', lastPublicationBlogId='wdetector')
        child, slot, after = self.execute()
        child.assert_not_called()
        slot.assert_not_called()
        self.assertEqual(after, self.state)

    def test_disabled_automation_remains_off(self):
        self.session()
        child, slot, after = self.execute(enabled=False)
        child.assert_not_called()
        slot.assert_not_called()
        self.assertEqual(after, self.state)
        self.assertEqual(self.final_status()['state'], 'paused')

    def test_shared_publication_lock_is_still_required(self):
        self.session()
        child, slot, after = self.execute(permitted=False)
        child.assert_not_called()
        slot.assert_called_once_with('beauty-blog')
        self.assertNotIn('publicationAttemptDate', after)

    def test_food_gap_still_defers_publication(self):
        self.session()
        scheduler.write_json(self.food/'scheduler_state.json', {'jobs': [{'time': self.now.isoformat()}]})
        child, slot, after = self.execute()
        child.assert_not_called()
        slot.assert_not_called()
        self.assertEqual(self.final_status()['nextRunAt'], '2026-10-07T17:00:00+09:00')
        self.assertEqual(after, self.state)


if __name__ == '__main__':
    unittest.main()
