import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from news_agent.naver import (
    NaverPublisher, PublishNotSubmitted, PublishUncertain,
    confirmed_post_url, editor_matches, parse_credentials, read_credentials,
)


ARTICLE = {"title": "뉴스 출처 안내", "body": "원문: https://www.youtube.com/shorts/Abcdef_1234", "video_id": "Abcdef_1234"}


class CredentialTests(unittest.TestCase):
    def test_common_notepad_formats(self):
        for text in [
            '\ufeff아이디: sample\n비밀번호: demo-only',
            '네이버 아이디 = sample\n네이버 비밀번호 = demo-only',
            '# 계정 정보\nsample\ndemo-only\n',
            json.dumps({"naver_id": "sample", "naver_password": "demo-only"}),
        ]:
            with self.subTest(format=text[:12]):
                self.assertEqual(parse_credentials(text), ("sample", "demo-only"))

    def test_password_may_contain_separators(self):
        self.assertEqual(parse_credentials('id: sample\npw: a:b=c'), ("sample", "a:b=c"))

    def test_invalid_credentials_do_not_appear_in_error(self):
        for text in ['private-value', '{"id":"private-value"}', 'id: one\nusername: two\npw: private-value']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as caught:
                    parse_credentials(text)
                self.assertNotIn('private-value', str(caught.exception))

    def test_extensionless_fallback_and_utf16_notepad(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "pw").write_text('아이디: sample\n비밀번호: demo-only', encoding='utf-16')
            self.assertEqual(read_credentials(folder / "pw.txt"), ("sample", "demo-only"))


class TargetTests(unittest.TestCase):
    def test_editor_requires_exact_target_https_host(self):
        self.assertTrue(editor_matches('https://blog.naver.com/PostWriteForm.naver?blogId=sample', 'sample'))
        self.assertTrue(editor_matches('https://blog.naver.com/sample/postwrite', 'sample'))
        for url in ['http://blog.naver.com/PostWriteForm.naver?blogId=sample',
                    'https://blog.naver.com.evil.test/PostWriteForm.naver?blogId=sample',
                    'https://blog.naver.com/PostWriteForm.naver?blogId=someone',
                    'https://blog.naver.com/PostWriteForm.naver?blogId=sample&blogId=someone',
                    'https://blog.naver.com/sample']:
            self.assertFalse(editor_matches(url, 'sample'))

    def test_receipt_requires_actual_post_and_exact_blog(self):
        expected = 'https://blog.naver.com/sample/223456789012'
        self.assertEqual(confirmed_post_url(expected, 'sample'), expected)
        self.assertEqual(confirmed_post_url('https://m.blog.naver.com/PostView.naver?blogId=sample&logNo=223456789012', 'sample'), expected)
        for url in ['https://blog.naver.com/sample', 'https://blog.naver.com/other/223456789012',
                    'https://blog.naver.com/sample/postwrite', 'https://evil.test/sample/223456789012']:
            self.assertIsNone(confirmed_post_url(url, 'sample'))


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.publisher = NaverPublisher(Path('/unused'))
        self.button = Mock()
        self.publisher._prepare = Mock(return_value=(Mock(), self.button))
        self.publisher._confirm = Mock(return_value='https://blog.naver.com/sample/223456789012')

    def test_durable_quota_callback_precedes_exactly_one_click(self):
        order = []
        self.button.click.side_effect = lambda: order.append('click')
        self.publisher.publish(ARTICLE, 'sample', before_submit=lambda: order.append('ledger'))
        self.assertEqual(order, ['ledger', 'click'])
        self.button.click.assert_called_once()

    def test_failed_quota_callback_prevents_click(self):
        def denied():
            raise RuntimeError('daily quota consumed')
        with self.assertRaisesRegex(RuntimeError, 'daily quota consumed'):
            self.publisher.publish(ARTICLE, 'sample', before_submit=denied)
        self.button.click.assert_not_called()

    def test_editor_failure_does_not_consume_quota(self):
        self.publisher._prepare.side_effect = RuntimeError('sensitive browser internals')
        ledger = Mock()
        with self.assertRaises(PublishNotSubmitted) as caught:
            self.publisher.publish(ARTICLE, 'sample', before_submit=ledger)
        ledger.assert_not_called()
        self.button.click.assert_not_called()
        self.assertNotIn('sensitive', str(caught.exception))

    def test_click_exception_is_uncertain_and_never_retried(self):
        self.button.click.side_effect = RuntimeError('network closed during click')
        with self.assertRaises(PublishUncertain):
            self.publisher.publish(ARTICLE, 'sample')
        self.button.click.assert_called_once()

    def test_confirmation_exception_is_uncertain(self):
        self.publisher._confirm.side_effect = RuntimeError('navigation timeout')
        with self.assertRaises(PublishUncertain):
            self.publisher.publish(ARTICLE, 'sample')
        self.button.click.assert_called_once()

    def test_missing_evidence_never_opens_browser(self):
        with self.assertRaises(PublishNotSubmitted):
            self.publisher.publish(dict(ARTICLE, body='출처 없음'), 'sample')
        self.publisher._prepare.assert_not_called()


class AuthenticationTests(unittest.TestCase):
    def test_autofill_only_runs_once_on_naver_https_login(self):
        publisher = NaverPublisher(Path('/unused'), Path('/not-read'))
        page = Mock(url='https://nid.naver.com/nidlogin.login')
        controls = [Mock(), Mock(), Mock()]
        with patch('news_agent.naver.read_credentials', return_value=('sample', 'demo-only')) as read:
            with patch('news_agent.naver._find_visible', side_effect=controls):
                publisher._autofill_once(page)
                publisher._autofill_once(page)
        read.assert_called_once()
        controls[2].click.assert_called_once()

    def test_no_credentials_sent_to_other_origin(self):
        publisher = NaverPublisher(Path('/unused'), Path('/not-read'))
        with patch('news_agent.naver.read_credentials') as read:
            publisher._autofill_once(Mock(url='https://nid.naver.com.evil.test/login'))
            publisher._autofill_once(Mock(url='http://nid.naver.com/login'))
        read.assert_not_called()


class ConfirmationTests(unittest.TestCase):
    def page_with_post(self, text, links=()):
        page = Mock()
        frame = Mock(url='https://blog.naver.com/sample/223456789012')
        page.frames = [frame]
        body = Mock()
        body.inner_text.return_value = text
        anchors = Mock()
        anchors.count.return_value = len(links)
        anchors.nth.side_effect = lambda i: Mock(**{'get_attribute.return_value': links[i]})
        frame.locator.side_effect = lambda selector: body if selector == 'body' else anchors
        return page

    def test_actual_post_title_and_source_are_required(self):
        publisher = NaverPublisher(Path('/unused'))
        page = self.page_with_post(ARTICLE['title'] + '\n' + ARTICLE['body'])
        self.assertEqual(publisher._confirm(page, ARTICLE, 'sample'), 'https://blog.naver.com/sample/223456789012')

    def test_linkified_source_can_be_verified(self):
        publisher = NaverPublisher(Path('/unused'))
        page = self.page_with_post(ARTICLE['title'], ['https://www.youtube.com/shorts/' + ARTICLE['video_id']])
        self.assertEqual(publisher._confirm(page, ARTICLE, 'sample'), 'https://blog.naver.com/sample/223456789012')

    def test_post_url_with_wrong_content_is_never_a_success(self):
        publisher = NaverPublisher(Path('/unused'))
        page = self.page_with_post('Another article unrelated to this source')
        with patch('news_agent.naver.time.monotonic', side_effect=[0, 1, 46]), \
                patch.object(publisher, '_authentication_challenge', return_value=False):
            with self.assertRaises(PublishUncertain):
                publisher._confirm(page, ARTICLE, 'sample')

    def test_post_click_manual_challenge_resumes_confirmation_without_second_click(self):
        publisher = NaverPublisher(Path('/unused'), manual_timeout_seconds=60)
        page = self.page_with_post(ARTICLE['title'] + '\n' + ARTICLE['body'])
        result_frames = page.frames
        page.frames = []
        clock = [0]
        def wait(_):
            clock[0] += 0.5
            if clock[0] >= 1.5:
                page.frames = result_frames
        page.wait_for_timeout.side_effect = wait
        events = []
        with patch('news_agent.naver.time.monotonic', side_effect=lambda: clock[0]), \
                patch.object(publisher, '_authentication_challenge', side_effect=[True, True, False]), \
                patch.object(publisher, '_autofill_once') as autofill:
            url = publisher._confirm(page, ARTICLE, 'sample', events.append)
        self.assertEqual(url, 'https://blog.naver.com/sample/223456789012')
        self.assertEqual(events, ['needs_auth', 'ready'])
        autofill.assert_not_called()

    def test_post_click_manual_challenge_timeout_remains_uncertain(self):
        publisher = NaverPublisher(Path('/unused'), manual_timeout_seconds=2)
        page = Mock(frames=[])
        clock = [0]
        def wait(_):
            clock[0] += 0.5
        page.wait_for_timeout.side_effect = wait
        events = []
        with patch('news_agent.naver.time.monotonic', side_effect=lambda: clock[0]), \
                patch.object(publisher, '_authentication_challenge', return_value=True):
            with self.assertRaises(PublishUncertain):
                publisher._confirm(page, ARTICLE, 'sample', events.append)
        self.assertEqual(events, ['needs_auth'])
        self.assertEqual(clock[0], 2)


class VisibilityTests(unittest.TestCase):
    def test_exact_public_radio_is_checked_and_read_back(self):
        publisher = NaverPublisher(Path('/unused'))
        editor = Mock()
        radios = editor.get_by_role.return_value
        radios.count.return_value = 1
        radio = radios.nth.return_value
        radio.is_checked.side_effect = [False, True]
        radio.is_visible.return_value = True
        publisher._ensure_public(editor)
        radio.check.assert_called_once()
        editor.get_by_role.assert_called_once_with('radio', name='공개', exact=True, include_hidden=True)

    def test_unknown_public_visibility_fails_before_submit(self):
        publisher = NaverPublisher(Path('/unused'))
        editor = Mock()
        editor.get_by_role.return_value.count.return_value = 0
        with self.assertRaises(PublishNotSubmitted):
            publisher._ensure_public(editor)


class TopicTests(unittest.TestCase):
    def collection(self, *labels):
        items = [Mock(**{'inner_text.return_value': label, 'is_visible.return_value': True}) for label in labels]
        collection = Mock()
        collection.count.return_value = len(items)
        collection.nth.side_effect = lambda index: items[index]
        return collection, items

    def test_unknown_topic_control_fails_closed(self):
        publisher = NaverPublisher(Path('/unused'))
        with patch('news_agent.naver._wait_visible', return_value=None):
            with self.assertRaises(PublishNotSubmitted):
                publisher._select_topic(Mock(), '사회·정치')

    def test_exact_topic_selected_allowing_only_spacing_and_middle_dot(self):
        publisher = NaverPublisher(Path('/unused'))
        editor = Mock()
        control = Mock()
        control.inner_text.side_effect = ['주제 선택', '사회 정치']
        options, items = self.collection('사회·정치 의견', '경제·비즈니스', '사회정치')
        editor.get_by_role.return_value = options
        with patch('news_agent.naver._wait_visible', return_value=control):
            publisher._select_topic(editor, '사회·정치')
        items[0].click.assert_not_called()
        items[1].click.assert_not_called()
        items[2].click.assert_called_once()

    def test_existing_equivalent_topic_is_verified_without_click(self):
        publisher = NaverPublisher(Path('/unused'))
        editor = Mock()
        control = Mock(**{'inner_text.return_value': '사회정치'})
        with patch('news_agent.naver._wait_visible', return_value=control):
            publisher._select_topic(editor, '사회·정치')
        control.click.assert_not_called()

    def test_wrong_selected_topic_is_not_accepted(self):
        publisher = NaverPublisher(Path('/unused'))
        editor = Mock()
        control = Mock()
        control.inner_text.side_effect = ['주제 선택', '경제·비즈니스']
        options, _ = self.collection('사회·정치')
        editor.get_by_role.return_value = options
        with patch('news_agent.naver._wait_visible', return_value=control):
            with self.assertRaises(PublishNotSubmitted):
                publisher._select_topic(editor, '사회·정치')

    def test_similar_topic_labels_do_not_match(self):
        publisher = NaverPublisher(Path('/unused'))
        editor = Mock()
        control = Mock(**{'inner_text.return_value': '주제 선택'})
        options, items = self.collection('사회/정치', '사회·정치 의견')
        editor.get_by_role.return_value = options
        editor.locator.return_value = self.collection()[0]
        with patch('news_agent.naver._wait_visible', return_value=control):
            with self.assertRaises(PublishNotSubmitted):
                publisher._select_topic(editor, '사회·정치')
        for item in items:
            item.click.assert_not_called()

    def test_topic_failure_never_reaches_durable_quota_callback(self):
        publisher = NaverPublisher(Path('/unused'))
        publisher._prepare = Mock(side_effect=PublishNotSubmitted('주제 분류 확인 필요'))
        ledger = Mock()
        with self.assertRaises(PublishNotSubmitted):
            publisher.publish(ARTICLE, 'wdetector', category='이슈', before_submit=ledger, topic='사회·정치')
        self.assertEqual(publisher._prepare.call_args.args[-1], '사회·정치')
        ledger.assert_not_called()


if __name__ == '__main__':
    unittest.main()
