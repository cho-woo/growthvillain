import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import crawler


class Response:
    def __init__(self, status):
        self.status = status


class LoadingPage:
    """Initial document can be replaced before the public results render."""
    def __init__(self, status=403, text='라이브러리 ID: 123456789', url=None, timeout=False):
        self.initial_status = status
        self.result_text = text
        self.url = url or crawler.BASE_URL
        self.timeout = timeout
        self.ready = False

    async def goto(self, url, **kwargs):
        self.request_url = url
        return Response(self.initial_status)

    async def wait_for_function(self, predicate, **kwargs):
        self.ready = True
        if self.timeout:
            raise crawler.PlaywrightTimeoutError('fixture timeout')

    async def query_selector_all(self, selector):
        if not self.ready:
            raise RuntimeError('Initial document is navigating')
        return []

    async def inner_text(self, selector):
        if not self.ready:
            raise RuntimeError('Initial document is navigating')
        return self.result_text


class SearchReadinessTests(unittest.TestCase):
    def run_search(self, page):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = Path(tmp) / 'access.json'
            try:
                asyncio.run(crawler.setup_search(page, '메디큐브 & 패드', diagnostic))
            finally:
                self.diagnostic = json.loads(diagnostic.read_text(encoding='utf-8'))

    def test_initial_403_does_not_discard_later_public_ads(self):
        page = LoadingPage()
        self.run_search(page)
        self.assertTrue(page.ready)
        self.assertEqual(self.diagnostic, {'initialStatus': 403, 'outcome': 'ready', 'adCount': 1})
        self.assertIn('%26', page.request_url)

    def test_403_without_results_remains_failure(self):
        with self.assertRaises(crawler.CollectionBlocked):
            self.run_search(LoadingPage(text='', timeout=True))
        self.assertEqual(self.diagnostic['outcome'], 'blocked')

    def test_rendered_checkpoint_stops_even_if_ads_are_present(self):
        with self.assertRaises(crawler.CollectionBlocked):
            self.run_search(LoadingPage(url='https://www.facebook.com/checkpoint/'))
        self.assertEqual(self.diagnostic['outcome'], 'blocked')

    def test_rendered_block_notice_is_not_treated_as_success(self):
        with self.assertRaises(crawler.CollectionBlocked):
            self.run_search(LoadingPage(text="You're temporarily blocked"))

    def test_429_stops_without_waiting_or_retrying(self):
        page = LoadingPage(status=429)
        with self.assertRaises(crawler.CollectionBlocked):
            self.run_search(page)
        self.assertFalse(page.ready)

    def test_real_empty_results_are_not_a_block(self):
        with self.assertRaisesRegex(RuntimeError, 'No ads found'):
            self.run_search(LoadingPage(text='광고 라이브러리 결과 0개'))
        self.assertEqual(self.diagnostic['outcome'], 'empty')


if __name__ == '__main__':
    unittest.main(verbosity=2)
