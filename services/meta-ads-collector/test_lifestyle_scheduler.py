import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from automation_bridge import KST, read_json, write_json
from automation_manager import AutomationManager
from desktop_status import EXPECTED, row_view
from lifestyle_scheduler import (DailyScheduler, attempted_today, next_daily,
                                 pending_article, publication_time, receipts,
                                 successful_publication_at, target_ready)


class Beat:
    def __init__(self):
        self.updates = []

    def update(self, **fields):
        self.updates.append(fields)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/'Lifestyle_Blog_Agent'
        self.hub = Path(self.temporary.name)/'hub'
        self.current = datetime(2026, 10, 8, 22, 0, tzinfo=KST)
        self.config = {'naver_blog_id': 'ehfvnd2007', 'naver_category_no': 15,
                       'naver_category_name': '일상', 'naver_topic': '일상·생각',
                       'naver_session_file': 'state/naver_blog_session-ehfvnd2007.json'}
        write_json(self.root/'config.json', self.config)
        write_json(self.root/self.config['naver_session_file'], {'test': 'existence-only'})
        write_json(self.root/'state/naver-login-status.json', {'blogId': 'ehfvnd2007', 'state': 'ready'})
        write_json(self.hub/'control.json', {'lifestyle-blog': True, 'food-blog': True})
        self.beat = Beat()
        self.calls = []
        self.scheduler = DailyScheduler(self.root, self.hub, self.beat,
                                        clock=lambda: self.current, runner=self.runner)

    def runner(self, script, *args):
        self.calls.append(script)
        if script == 'lifestyle_agent.py':
            self.draft()
        elif script == 'publish_lifestyle.py':
            self.receipt('published')
        return 0

    def draft(self, **overrides):
        article = {'publicationId': 'test-today', 'status': 'draft', 'reviewStatus': 'verified',
                   'generatedAt': self.current.isoformat(),
                   'validation': {'sourcesVerified': True, 'claimsChecked': True}}
        article.update(overrides)
        path = self.root/'drafts/today/article.json'
        write_json(path, article)
        return path

    def receipt(self, status='published', **overrides):
        value = {'publicationId': 'test-today', 'blogId': 'ehfvnd2007', 'categoryNo': 15,
                 'status': status, 'at': self.current.isoformat()}
        value.update(overrides)
        write_json(self.root/'state/publications/ehfvnd2007-15-test-today.json', value)
        return value

    def due(self):
        self.current = self.current.replace(hour=23, minute=10, second=1)

    def test_startup_before_and_after_slot_does_not_backfill(self):
        self.assertEqual(next_daily(self.current), self.current.replace(hour=23, minute=10))
        late = self.current.replace(hour=23, minute=12)
        self.assertEqual(next_daily(late), (late+timedelta(days=1)).replace(minute=10))
        self.current = late
        scheduler = DailyScheduler(self.root, self.hub, self.beat,
                                   clock=lambda: self.current, runner=self.runner)
        scheduler.tick()
        self.assertEqual(self.calls, [])
        self.assertTrue(self.beat.updates[-1]['nextRunAt'].startswith('2026-10-09T23:10'))

    def test_collection_then_one_publication_at_due_slot(self):
        self.scheduler.tick()
        self.assertEqual(self.calls, [])
        self.due()
        self.scheduler.tick()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py', 'publish_lifestyle.py'])
        self.assertEqual(read_json(self.scheduler.state_path)['publicationAttemptDate'], '2026-10-08')
        self.assertEqual(self.beat.updates[-1]['state'], 'waiting')

    def test_manual_published_running_and_unknown_all_consume_today(self):
        for status in ('published', 'running', 'unknown'):
            with self.subTest(status=status):
                record = self.receipt(status)
                self.assertTrue(attempted_today({}, [record], self.current))
        self.receipt('published')
        self.due()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertIn('오늘 발행 완료', self.beat.updates[-1]['message'])

    def test_unknown_manual_receipt_is_not_reported_as_success(self):
        self.receipt('unknown')
        self.due()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertEqual(self.beat.updates[-1]['state'], 'blocked')
        self.assertIsNone(self.beat.updates[-1]['lastSuccessAt'])

    def test_previous_day_and_other_target_receipt_do_not_consume_today(self):
        record = self.receipt(at=(self.current-timedelta(days=1)).isoformat())
        self.assertFalse(attempted_today({}, [record], self.current))
        self.receipt(blogId='other-blog')
        self.assertEqual(receipts(self.root), [])

    def test_kst_date_used_for_utc_manual_receipts(self):
        record = self.receipt(at='2026-10-07T16:00:00+00:00')
        self.assertTrue(attempted_today({}, [record], self.current))

    def test_auto_failure_is_not_retried_that_day(self):
        def runner(script, *args):
            self.calls.append(script)
            if script == 'lifestyle_agent.py':
                self.draft()
                return 0
            return 1
        self.scheduler.runner = runner
        self.due()
        self.scheduler.tick()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py', 'publish_lifestyle.py'])
        self.assertEqual(self.beat.updates[-1]['state'], 'blocked')

    def test_collection_failure_never_publishes_old_draft_or_retries(self):
        self.draft()
        self.scheduler.runner = lambda script, *args: self.calls.append(script) or 1
        self.due()
        self.scheduler.tick()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertEqual(self.beat.updates[-1]['state'], 'error')

    def test_unreviewed_previous_day_future_and_used_drafts_excluded(self):
        for override in ({'reviewStatus': 'needs_review'},
                         {'validation': {'sourcesVerified': True, 'claimsChecked': False}},
                         {'generatedAt': (self.current-timedelta(days=1)).isoformat()},
                         {'generatedAt': (self.current+timedelta(minutes=1)).isoformat()},
                         {'publicationId': '../escape'}, {'status': 'reference_only'}):
            with self.subTest(override=override):
                self.draft(**override)
                self.assertIsNone(pending_article(self.root, self.current))
        path = self.draft()
        self.assertEqual(pending_article(self.root, self.current), path)
        self.receipt('unknown')
        self.assertIsNone(pending_article(self.root, self.current))

    def test_partial_receipt_blocks_same_article(self):
        self.draft()
        write_json(self.root/'state/publications/ehfvnd2007-15-test-today.json', {})
        self.assertIsNone(pending_article(self.root, self.current))

    def test_missing_reviewed_article_waits_without_publication(self):
        self.scheduler.runner = lambda script, *args: self.calls.append(script) or 0
        self.due()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertIn('새 초안 0개', self.beat.updates[-1]['message'])

    def test_target_status_category_session_and_auth_hold_are_all_required(self):
        self.assertTrue(target_ready(self.root, self.config)[0])
        for key, value in (('naver_category_no', True), ('naver_category_no', 6),
                           ('naver_blog_id', 'other'), ('naver_topic', '뷰티'),
                           ('naver_session_file', '../session.json')):
            with self.subTest(key=key, value=value):
                self.assertFalse(target_ready(self.root, dict(self.config, **{key: value}))[0])
        write_json(self.root/'state/publication-auth-required.json', {})
        self.assertFalse(target_ready(self.root, self.config)[0])

    def test_login_gate_allows_collection_but_never_publication(self):
        write_json(self.root/'state/naver-login-status.json', {'blogId': 'ehfvnd2007', 'state': 'verification_limited'})
        self.due()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertEqual(self.beat.updates[-1]['state'], 'blocked')
        self.assertEqual(self.beat.updates[-1]['message'],
                         '보호조치 인증 횟수 초과 · 발행 보류 · 수집 일정 유지')

    def test_explicit_auth_hold_preserves_verification_limit_message(self):
        write_json(self.root/'state/publication-auth-required.json',
                   {'blogId': 'ehfvnd2007', 'state': 'verification_limited'})
        self.attention()
        self.scheduler.tick()
        self.assertEqual(self.beat.updates[-1]['state'], 'blocked')
        self.assertEqual(self.beat.updates[-1]['message'],
                         '보호조치 인증 횟수 초과 · 발행 보류 · 수집 일정 유지')
        self.assertEqual(self.beat.updates[-1]['nextRunAt'], '2026-10-08T23:10:00+09:00')

    def test_different_blog_verification_limit_is_not_attributed_to_this_blog(self):
        write_json(self.root/'state/naver-login-status.json',
                   {'blogId': 'other-blog', 'state': 'verification_limited'})
        self.assertNotIn('인증 횟수 초과', target_ready(self.root, self.config)[1])

    def test_off_during_collection_does_not_start_a_post(self):
        def runner(script, *args):
            self.calls.append(script)
            self.draft()
            write_json(self.hub/'control.json', {'lifestyle-blog': False})
            return 0
        self.scheduler.runner = runner
        self.due()
        self.scheduler.tick()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertEqual(self.beat.updates[-1]['state'], 'paused')

    def test_off_skips_missed_slot_and_reenable_does_not_catch_up(self):
        write_json(self.hub/'control.json', {'lifestyle-blog': False})
        self.due()
        self.scheduler.tick()
        write_json(self.hub/'control.json', {'lifestyle-blog': True})
        self.scheduler.tick()
        self.assertEqual(self.calls, [])

    def test_sleep_across_midnight_skips_previous_day_slot(self):
        self.current += timedelta(days=1)
        self.scheduler.tick()
        self.assertEqual(self.calls, [])

    def test_food_slots_and_beauty_actual_finish_both_enforce_gap(self):
        at = self.current.replace(hour=23, minute=10)
        self.assertEqual(publication_time(at, {'jobs': [{'time': '2026-10-08T21:00:00+09:00'}]}),
                         datetime(2026,10,9,0,0,tzinfo=KST))
        self.assertEqual(publication_time(at, {}, {'automationId': 'beauty-blog',
                                                  'finishedAt': '2026-10-08T21:15:00+09:00'}),
                         datetime(2026,10,9,0,15,tzinfo=KST))
        self.assertEqual(publication_time(at, {}, {'automationId': 'lifestyle-blog',
                                                  'finishedAt': '2026-10-08T21:15:00+09:00'}), at)

    def test_gap_crossing_midnight_defers_instead_of_late_publication(self):
        write_json(self.hub/'publication-ledger.json', {'automationId': 'beauty-blog',
                                                       'finishedAt': '2026-10-08T21:15:00+09:00'})
        self.due()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertIn('간격 부족', self.beat.updates[-1]['message'])

    def test_within_day_gap_waits_then_publishes_once(self):
        write_json(self.hub/'publication-ledger.json', {'automationId': 'food-blog',
                                                       'finishedAt': '2026-10-08T20:30:00+09:00'})
        self.due()
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py'])
        self.assertTrue(self.beat.updates[-1]['nextRunAt'].startswith('2026-10-08T23:30'))
        self.current = self.current.replace(minute=30)
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py', 'publish_lifestyle.py'])

    def test_success_comes_from_confirmed_receipt_only(self):
        self.assertIsNone(successful_publication_at([self.receipt('unknown')]))
        self.assertEqual(successful_publication_at([self.receipt('published')]), self.current.isoformat(timespec='seconds'))

    def test_attempt_without_receipt_after_interruption_never_claims_success(self):
        write_json(self.scheduler.state_path, {'publicationAttemptDate': '2026-10-08'})
        self.scheduler.tick()
        self.assertEqual(self.beat.updates[-1]['state'], 'blocked')
        self.assertIn('확인 필요', self.beat.updates[-1]['message'])
        self.assertIsNone(self.beat.updates[-1]['lastSuccessAt'])

    def test_old_failed_attempt_does_not_hide_today_confirmed_manual_receipt(self):
        write_json(self.scheduler.state_path, {'publicationAttemptDate': '2026-10-07',
                                               'lastPublicationOk': False})
        self.receipt('published')
        self.scheduler.tick()
        self.assertEqual(self.beat.updates[-1]['state'], 'waiting')
        self.assertIn('오늘 발행 완료', self.beat.updates[-1]['message'])

    def attention(self, **overrides):
        value = {'needsAttention': True, 'statusLabel': 'AI 작성 연결 확인 필요'}
        value.update(overrides)
        write_json(self.root/'state/generation.json', value)

    def test_generation_attention_is_visible_without_hiding_next_schedule(self):
        self.attention()
        self.scheduler.tick()
        status = self.beat.updates[-1]
        self.assertEqual(status['state'], 'error')
        self.assertEqual(status['message'], 'AI 작성 연결 확인 필요')
        self.assertEqual(status['nextRunAt'], '2026-10-08T23:10:00+09:00')

    def test_manual_success_stays_visible_despite_generation_and_collection_error(self):
        self.attention()
        self.receipt('published')
        write_json(self.scheduler.state_path, {'lastCollectionOk': False})
        self.scheduler.tick()
        status = self.beat.updates[-1]
        self.assertEqual(status['state'], 'error')
        self.assertEqual(status['message'], '오늘 발행 완료 · AI 작성 연결 확인 필요')
        self.assertEqual(status['lastSuccessAt'], self.current.isoformat(timespec='seconds'))
        self.assertEqual(status['nextRunAt'], '2026-10-08T23:10:00+09:00')

    def test_login_hold_takes_priority_over_generation_attention(self):
        self.attention()
        write_json(self.root/'state/naver-login-status.json', {'blogId': 'ehfvnd2007', 'state': 'needs_login'})
        self.scheduler.tick()
        self.assertEqual(self.beat.updates[-1]['state'], 'blocked')
        self.assertIn('로그인 확인 필요', self.beat.updates[-1]['message'])
        self.assertNotIn('AI 작성', self.beat.updates[-1]['message'])

    def test_attention_does_not_disable_next_day_collection(self):
        self.attention()
        self.current = self.current.replace(hour=23, minute=15)
        self.scheduler = DailyScheduler(self.root, self.hub, self.beat,
                                        clock=lambda: self.current, runner=self.runner)
        self.current = (self.current+timedelta(days=1)).replace(minute=10, second=1)
        self.scheduler.tick()
        self.assertEqual(self.calls, ['lifestyle_agent.py', 'publish_lifestyle.py'])

    def test_unexpected_generation_label_never_leaks_provider_response(self):
        self.attention(statusLabel='private provider response')
        self.scheduler.tick()
        self.assertEqual(self.beat.updates[-1]['message'], 'AI 작성 확인 필요')

    def test_resolved_generation_attention_restores_normal_waiting_status(self):
        self.attention(needsAttention=False)
        self.scheduler.tick()
        self.assertEqual(self.beat.updates[-1]['state'], 'waiting')


class HubRegistrationTests(unittest.TestCase):
    def test_six_rows_and_live_lifestyle_schedule_display(self):
        self.assertEqual(len(EXPECTED), 6)
        self.assertIn(('lifestyle-blog', '일상 블로그'), EXPECTED)
        view = row_view({'id': 'lifestyle-blog', 'enabled': True, 'state': 'waiting',
                         'controllable': True, 'nextRunAt': '2026-10-08T23:10:00+09:00'},
                        True, datetime(2026,10,8,22,tzinfo=KST).timestamp())
        self.assertIn('매일 23:10', view['detail'])
        self.assertIn('1시간 10분 후', view['detail'])
        self.assertFalse(view['disabled'])

    def test_manager_lifestyle_switch_preserves_other_flags(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root/'control.json', {'food-blog': False, 'beauty-blog': True})
            manager = AutomationManager(root=root, lifestyle_root=root/'lifestyle')
            with patch.object(manager, 'tick') as tick:
                manager.set_enabled('lifestyle-blog', True)
                manager.set_enabled('lifestyle-blog', False)
                tick.assert_called_once()
            self.assertEqual(read_json(root/'control.json'),
                             {'food-blog': False, 'beauty-blog': True, 'lifestyle-blog': False})
            self.assertEqual(manager.projects['lifestyle-blog'][1], 'lifestyle_scheduler.py')
            rows = manager.status()['automations']
            row = next(value for value in rows if value['id'] == 'lifestyle-blog')
            self.assertTrue(row['controllable'])
            self.assertEqual(row['state'], 'paused')


if __name__ == '__main__':
    unittest.main()
