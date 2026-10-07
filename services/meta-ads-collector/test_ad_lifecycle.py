"""Lifecycle evidence fixtures; public failure is never an ad end."""
import asyncio
from datetime import date
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ad_lifecycle import (absence_fields, delivery_fields, iso_date, merge_observation,
                          merge_status_observation, parse_delivery)
from check_ad_status import inspect_ad, not_found_evidence


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.today = patch('ad_lifecycle._today', return_value=date(2026, 10, 7))
        self.today.start()
        self.addCleanup(self.today.stop)

    def test_public_start_date_formats_and_invalid_dates(self):
        for value in ('2024-02-29', 'Feb 29, 2024', 'February 29, 2024', '29 Feb 2024',
                      '2024. 2. 29.', '2024년 2월 29일'):
            with self.subTest(value=value):
                self.assertEqual(iso_date(value), '2024-02-29')
        for value in ('2025-02-29', '2026. 13. 1.', None, 'not a date'):
            self.assertEqual(iso_date(value), '')

    def test_reported_duration_counts_both_calendar_dates(self):
        value = delivery_fields('ended', '2024-01-01', '2024-06-30')
        self.assertEqual(value['durationDays'], 182)
        self.assertEqual(value['durationLabel'], '182일 게재 후 종료')
        self.assertEqual(value['durationBasis'], 'reported')
        self.assertEqual(value['durationCountMethod'], 'inclusive-calendar-days')
        self.assertEqual(delivery_fields('ended', '2024-02-29', '2024-02-29')['durationDays'], 1)
        self.assertEqual(delivery_fields('ended', '2024-02-28', '2024-03-01')['durationDays'], 3)

    def test_explicit_end_is_retained_without_start_but_invalid_range_has_no_duration(self):
        value = delivery_fields('ended', '', '2024-06-30')
        self.assertEqual(value['endedAt'], '2024-06-30')
        self.assertIsNone(value['durationDays'])
        for start, end in (('2024-07-01', '2024-06-30'), ('2024-01-01', '2026-10-08')):
            value = delivery_fields('ended', start, end)
            self.assertIsNone(value['endedAt'])
            self.assertIsNone(value['durationDays'])

    def test_absence_date_is_first_observation_kst_not_reported_end(self):
        existing = {'startedAt': '2024-01-01', **delivery_fields('active')}
        fields = absence_fields(existing, '2024-06-29T15:00:00Z')
        self.assertEqual(fields['durationDays'], 182)
        self.assertIsNone(fields['endedAt'])
        self.assertEqual(fields['endedDetectedAt'], '2024-06-29T15:00:00Z')
        self.assertEqual(fields['durationBasis'], 'detected')
        self.assertEqual(fields['durationLabel'], '182일 게재 후 종료 · 감지일 기준')
        repeated = absence_fields({**existing, **fields}, '2024-07-01T00:00:00Z')
        self.assertEqual(repeated['endedDetectedAt'], fields['endedDetectedAt'])
        self.assertEqual(repeated['durationDays'], 182)
        self.assertEqual(repeated['statusCheckedAt'], '2024-07-01T00:00:00Z')

    def test_invalid_or_future_absence_timestamp_is_rejected(self):
        for stamp in ('bad', None, '2030-01-01T00:00:00Z'):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                absence_fields({'startedAt': '2024-01-01'}, stamp)

    def test_reported_end_wins_over_later_absence_and_unknown_duration_stays_unknown(self):
        old = {'startedAt': '2024-01-01', **delivery_fields('ended', '2024-01-01', '2024-06-30')}
        value = absence_fields(old, '2024-07-10T01:00:00Z')
        self.assertEqual(value['endedAt'], '2024-06-30')
        self.assertEqual(value['durationDays'], 182)
        self.assertEqual(value['durationBasis'], 'reported')
        self.assertNotIn('감지일 기준', value['durationLabel'])
        missing_start = absence_fields({}, '2024-07-01T00:00:00Z')
        self.assertIsNone(missing_start['durationDays'])
        self.assertIn('기간 미확인', missing_start['durationLabel'])

    def test_failures_leave_lifecycle_unchanged(self):
        old = {'id': '123456', 'startedAt': '2024-01-01', **delivery_fields('active', checked_at='2024-06-01T00:00:00Z')}
        for outcome in ('unavailable', 'blocked'):
            updated = merge_status_observation(old, {'outcome': outcome, 'checkedAt': '2024-07-01T00:00:00Z'})
            self.assertEqual(updated['deliveryStatus'], 'active')
            self.assertEqual(updated['statusCheckedAt'], old['statusCheckedAt'])
            self.assertIsNone(updated['endedDetectedAt'])
        self.assertEqual(merge_status_observation(old, {'outcome': 'missing'}), old)

    def test_reactivated_ad_clears_detected_end_and_later_report_overrides_estimate(self):
        old = {'startedAt': '2024-01-01'}
        old.update(absence_fields(old, '2024-07-01T00:00:00Z'))
        active = merge_status_observation(old, {'outcome': 'confirmed', 'delivery_status': 'active', 'checkedAt': '2024-07-02T00:00:00Z'})
        self.assertEqual(active['deliveryStatus'], 'active')
        self.assertIsNone(active['endedDetectedAt'])
        self.assertIsNone(active['durationDays'])
        unknown = merge_status_observation(old, {'outcome': 'confirmed', 'delivery_status': 'unknown', 'checkedAt': '2024-07-02T00:00:00Z'})
        self.assertEqual(unknown['deliveryStatus'], 'unknown')
        self.assertIsNone(unknown['endedDetectedAt'])
        reported = merge_status_observation(old, {'outcome': 'confirmed', 'delivery_status': 'ended',
                                                  'end_date': '2024-06-30', 'checkedAt': '2024-07-02T00:00:00Z'})
        self.assertEqual(reported['durationBasis'], 'reported')
        self.assertEqual(reported['durationDays'], 182)

    def test_found_unknown_card_clears_only_inferred_end(self):
        old = {'startedAt': '2024-01-01'}
        old.update(absence_fields(old, '2024-07-01T00:00:00Z'))
        current = {'collectedAt': '2024-07-02T00:00:00Z', **delivery_fields('unknown')}
        value = merge_observation(old, current)
        self.assertEqual(value['deliveryStatus'], 'unknown')
        self.assertIsNone(value['endedDetectedAt'])
        reported = {**old, **delivery_fields('ended', '2024-01-01', '2024-06-30')}
        self.assertEqual(merge_observation(reported, current)['endedAt'], '2024-06-30')

    def test_creative_body_is_not_delivery_status_or_date(self):
        value = parse_delivery('활성\n라이브러리 ID: 123456\n2024. 1. 1.에 게재 시작함\n플랫폼\n광고 문구\n2024. 6. 30.에 종료')
        self.assertEqual(value, {'delivery_status': 'active', 'start_date': '2024-01-01', 'end_date': ''})
        value = parse_delivery('Inactive\nLibrary ID: 123456\nJan 1, 2024 – Jun 30, 2024\nPlatforms\nText')
        self.assertEqual(value, {'delivery_status': 'ended', 'start_date': '2024-01-01', 'end_date': '2024-06-30'})


class AbsenceEvidenceTests(unittest.TestCase):
    def evidence(self, **kwargs):
        fields = {'url': 'https://www.facebook.com/ads/library/?id=123456', 'http_status': 200,
                  'text': '광고 라이브러리\n광고를 찾을 수 없습니다.', 'ready_state': 'complete', 'busy': False}
        fields.update(kwargs)
        return not_found_evidence('123456', **fields)

    def test_explicit_exact_id_normal_page_confirms_absence(self):
        self.assertTrue(self.evidence())
        self.assertTrue(self.evidence(text='Meta Ad Library\nThis ad is no longer available.'))
        self.assertTrue(self.evidence(text='Ad Library\nNo results found'))

    def test_http_failure_missing_endpoint_and_unfinished_page_never_confirm_absence(self):
        for status in (None, 401, 403, 404, 429, 500, 503):
            self.assertFalse(self.evidence(http_status=status))
        self.assertFalse(self.evidence(ready_state='interactive'))
        self.assertFalse(self.evidence(busy=True))

    def test_redirected_search_another_id_and_duplicate_ids_never_confirm_absence(self):
        for url in ('https://www.facebook.com/ads/library/?q=brand',
                    'https://www.facebook.com/ads/library/?id=123456&q=brand',
                    'https://www.facebook.com/ads/library/?id=999999',
                    'https://www.facebook.com/ads/library/?id=123456&id=123456',
                    'https://www.facebook.com/login/?id=123456',
                    'https://facebook.com.attacker.test/ads/library/?id=123456'):
            with self.subTest(url=url):
                self.assertFalse(self.evidence(url=url))

    def test_blank_generic_error_login_and_other_card_never_confirm_absence(self):
        for text in ('', 'No ads found', 'Ad Library\nThis content is not available right now',
                     'Ad Library\nNo ads found\nSomething went wrong. Try again.',
                     'Ad Library\nNo ads found\nLog in to continue',
                     '광고 라이브러리\n광고를 찾을 수 없습니다.\n일시적으로 차단되었습니다',
                     'Ad Library\nNo ads found\nLibrary ID: 999999'):
            with self.subTest(text=text):
                self.assertFalse(self.evidence(text=text))


class CheckerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def page(self, text='Ad Library\nNo ads found', status=200):
        page = Mock()
        page.url = 'https://www.facebook.com/ads/library/?id=123456'
        page.goto = AsyncMock(return_value=Mock(status=status))
        page.wait_for_function = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.inner_text = AsyncMock(return_value=text)
        page.evaluate = AsyncMock(return_value={'readyState': 'complete', 'busy': False})
        return page

    async def inspect(self, page, cards=()):
        with patch('check_ad_status.check_access', new=AsyncMock()), \
             patch('check_ad_status.get_visible_cards', new=AsyncMock(return_value=cards)), \
             patch('check_ad_status.asyncio.sleep', new=AsyncMock()):
            return await inspect_ad(page, '123456')

    async def test_stable_explicit_no_results_is_not_found(self):
        value = await self.inspect(self.page())
        self.assertEqual(value['outcome'], 'not_found')
        self.assertEqual(value['evidence'], 'exact_id_explicit_no_result')

    async def test_no_result_that_disappears_during_render_remains_unavailable(self):
        page = self.page()
        page.inner_text.side_effect = ['Ad Library\nNo ads found', 'Ad Library\nLoading']
        self.assertEqual((await self.inspect(page))['outcome'], 'unavailable')

    async def test_404_and_429_never_read_page_as_missing_ad(self):
        for status, outcome in ((404, 'unavailable'), (429, 'blocked')):
            page = self.page(status=status)
            self.assertEqual((await self.inspect(page))['outcome'], outcome)
            page.inner_text.assert_not_awaited()

    async def test_200_document_with_failed_public_xhr_does_not_end_ad(self):
        for status, outcome in ((503, 'unavailable'), (403, 'blocked')):
            page = self.page()
            handlers = {}
            page.on.side_effect = lambda name, callback: handlers.update({name: callback})
            async def network_idle(*args, **kwargs):
                request = Mock(resource_type='fetch', url='https://www.facebook.com/api/graphql/')
                handlers['response'](Mock(request=request, status=status))
            page.wait_for_load_state.side_effect = network_idle
            self.assertEqual((await self.inspect(page))['outcome'], outcome)

    async def test_unfinished_network_does_not_end_ad(self):
        page = self.page()
        page.wait_for_load_state.side_effect = TimeoutError('network still loading')
        self.assertEqual((await self.inspect(page))['outcome'], 'unavailable')

    async def test_exact_active_card_wins_and_mismatched_card_is_not_absence(self):
        card = Mock(inner_text=AsyncMock(return_value='Active\nLibrary ID: 123456\nStarted running on Jan 1, 2024\nPlatforms'))
        value = await self.inspect(self.page(status=403), [card])
        self.assertEqual(value['outcome'], 'confirmed')
        self.assertEqual(value['delivery_status'], 'active')
        unknown = Mock(inner_text=AsyncMock(return_value='Library ID: 123456\nPlatforms'))
        value = await self.inspect(self.page(), [unknown])
        self.assertEqual(value['outcome'], 'confirmed')
        self.assertEqual(value['delivery_status'], 'unknown')
        wrong = Mock(inner_text=AsyncMock(return_value='Active\nLibrary ID: 999999'))
        value = await self.inspect(self.page(text='Ad Library\nNo ads found\nLibrary ID: 999999'), [wrong])
        self.assertEqual(value['outcome'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
