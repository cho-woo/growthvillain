import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import crawler
from completed_cards import read_completed_jsonl


class Card:
    def __init__(self, identifier):
        self.identifier = identifier

    async def get_attribute(self, name):
        return self.identifier


def fake_playwright():
    class Page:
        def set_default_timeout(self, value): pass
    class Context:
        async def new_page(self): return Page()
    class Browser:
        async def new_context(self, **kwargs): return Context()
        async def close(self): pass
    class Chromium:
        async def launch(self, **kwargs): return Browser()
    class Playwright:
        chromium = Chromium()
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    return Playwright()


class CrawlerBudgetTests(unittest.TestCase):
    def run_fixture(self, run_dir, batches, *, target=100, download=None, clock=None, storage=None):
        async def extract(card, page):
            return {'library_id': card.identifier, 'advertiser': 'Brand', 'landing_domain': '',
                    'image_urls': ['https://scontent.xx.fbcdn.net/ad.jpg'],
                    'video_urls': [], 'video_poster_urls': []}
        with ExitStack() as stack:
            stack.enter_context(patch.object(crawler, 'async_playwright', return_value=fake_playwright()))
            for name in ('setup_search', 'check_access', 'scroll_until_enough'):
                stack.enter_context(patch.object(crawler, name, new=AsyncMock()))
            stack.enter_context(patch.object(crawler, 'get_visible_cards', new=AsyncMock(side_effect=batches)))
            extraction = stack.enter_context(patch.object(crawler, 'extract_card_data', new=AsyncMock(side_effect=extract)))
            stack.enter_context(patch.object(crawler, 'download_media', side_effect=download or self.save_media))
            stack.enter_context(patch.object(crawler.asyncio, 'sleep', new=AsyncMock()))
            stack.enter_context(patch.object(crawler.shutil, 'disk_usage', side_effect=storage or (lambda path: SimpleNamespace(free=10 * 1024 ** 3))))
            if clock:
                # Replace this module's time handle, not asyncio's global clock.
                stack.enter_context(patch.object(crawler, 'time', SimpleNamespace(monotonic=clock)))
            asyncio.run(crawler.run('cream', 1, '', run_dir, total_target=target, auto=True, headless=True, runtime_budget_seconds=30))
            return extraction.await_count

    @staticmethod
    def save_media(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'complete-image')
        return True

    def test_soft_budget_preserves_completed_first_card(self):
        now = [0]
        def download(url, path):
            result = self.save_media(url, path)
            now[0] = 31
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = self.run_fixture(root, [[Card('123456')]], download=download, clock=lambda: now[0])
            result = read_completed_jsonl(root / 'cards.jsonl')
            completion = json.loads((root / 'completion.json').read_text())
            self.assertEqual(calls, 1)
            self.assertEqual(len(result['rows']), 1)
            self.assertEqual(completion['reason'], 'time_budget')
            self.assertFalse(completion['complete'])
            self.assertEqual(completion['savedCount'], 1)

    def test_storage_floor_stops_after_completed_card(self):
        free = [10 * 1024 ** 3]
        def download(url, path):
            result = self.save_media(url, path)
            free[0] = 5 * 1024 ** 3
            return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_fixture(root, [[Card('123456')]], download=download,
                             storage=lambda path: SimpleNamespace(free=free[0]))
            completion = json.loads((root / 'completion.json').read_text())
            self.assertEqual(completion['reason'], 'storage_low')
            self.assertEqual(len(read_completed_jsonl(root / 'cards.jsonl')['rows']), 1)

    def test_seen_card_skips_expensive_extractor_across_batches(self):
        first, second = Card('123456'), Card('234567')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = self.run_fixture(root, [[first], [first, second]], target=2)
            self.assertEqual(calls, 2)
            self.assertEqual(json.loads((root / 'completion.json').read_text())['reason'], 'target_reached')

    def test_budget_during_multifile_card_does_not_commit_partial_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {'image_urls': ['https://scontent.xx.fbcdn.net/1.jpg', 'https://scontent.xx.fbcdn.net/2.jpg'],
                   'video_urls': [], 'video_poster_urls': []}
            with patch.object(crawler, 'runtime_stop_reason', side_effect=[None, 'storage_low']), \
                 patch.object(crawler, 'download_media', side_effect=self.save_media) as download:
                saved, reason = crawler.download_card_media(row, root / 'media', root, 1, 1)
            self.assertEqual(reason, 'storage_low')
            self.assertEqual(len(saved['images']), 1)
            self.assertEqual(download.call_count, 1)
            self.assertFalse((root / 'cards.jsonl').exists())

    def test_scroll_budget_prevents_further_page_activity(self):
        page = SimpleNamespace(evaluate=AsyncMock())
        with patch.object(crawler, 'time', SimpleNamespace(monotonic=lambda: 10)), \
             patch.object(crawler, 'check_access', new=AsyncMock()) as access:
            asyncio.run(crawler.scroll_until_enough(page, 100, set(), deadline=10))
            access.assert_not_awaited()
            page.evaluate.assert_not_awaited()

    def test_download_commits_only_finished_file(self):
        class Response:
            status_code = 200
            headers = {'Content-Type': 'image/jpeg'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def raise_for_status(self): pass
            def iter_content(self, size):
                yield b'first'
                if self.fail:
                    raise RuntimeError('interrupted')
                yield b'second'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ad.jpg'
            response = Response()
            for fail in (True, False):
                response.fail = fail
                with patch.object(crawler.requests, 'get', return_value=response):
                    self.assertEqual(crawler.download_media('https://scontent.xx.fbcdn.net/ad.jpg', path), not fail)
                self.assertEqual(path.exists(), not fail)
                self.assertFalse(path.with_name('ad.jpg.part').exists())
            self.assertEqual(path.read_bytes(), b'firstsecond')

    def test_hardkill_orphan_is_never_referenced_by_committed_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / 'media'
            media.mkdir()
            (media / 'first.jpg').write_bytes(b'complete')
            (media / 'second.jpg.part').write_bytes(b'incomplete')
            crawler.append_completed_card(root / 'cards.jsonl', {'library_id': '123456', '_saved_images': ['media/first.jpg']})
            result = read_completed_jsonl(root / 'cards.jsonl')
            self.assertEqual(result['rows'][0]['_saved_images'], ['media/first.jpg'])
            self.assertTrue((media / 'second.jpg.part').exists())


if __name__ == '__main__':
    unittest.main()
