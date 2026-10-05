import asyncio
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, AsyncMock

import catalog
import crawler
from server import Store, Controller, Server, competitor_input


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.runtime_probe = patch.object(Controller, 'check_runtime', return_value=False)
        self.runtime_probe.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.web = self.root / 'web'
        self.web.mkdir()
        (self.web / 'index.html').write_text('portfolio', encoding='utf-8')
        self.store = Store(self.root / 'private', self.web)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
        self.runtime_probe.stop()

    def sample(self, path='media/123456/image.jpg'):
        run = self.root / 'run'
        (run / 'media/123456').mkdir(parents=True, exist_ok=True)
        (run / 'media/123456/image.jpg').write_bytes(b'public-image-fixture')
        row = {'library_id': '123456', 'advertiser': 'Public brand', 'ad_text': '<script>ordinary ad text</script>',
               '_saved_images': [path], '_saved_videos': [], '_saved_posters': [], '_keyword': 'cream',
               '_collected_at': '2026-05-14T13:00:00', 'start_date': 'May 12, 2026',
               'landing_url': 'https://example.com/product?product_no=41&access_token=NEVER_EXPORT&fbclid=TRACKING',
               'employee_notes': 'NEVER_EXPORT', 'aws_access_key_id': 'NEVER_EXPORT'}
        source = run / 'cards.jsonl'
        source.write_text(json.dumps(row), encoding='utf-8')
        return source

    def test_import_deduplicates_and_exports_only_public_fields(self):
        source = self.sample()
        self.assertEqual(self.store.import_file(source), 1)
        self.assertEqual(self.store.import_file(source), 0)
        payload = (self.web / 'tools/meta-ads/data/catalog.json').read_text(encoding='utf-8')
        self.assertNotIn('NEVER_EXPORT', payload)
        self.assertNotIn('TRACKING', payload)
        data = json.loads(payload)
        self.assertEqual(len(data['cards']), 1)
        self.assertEqual(data['cards'][0]['startedAt'], '2026-05-12')
        self.assertTrue((self.web / data['cards'][0]['media'][0]['url'].lstrip('/')).is_file())

    def test_import_rejects_traversal_and_no_partial_db_commit(self):
        (self.root / 'secret.jpg').write_bytes(b'private')
        source = self.sample('../secret.jpg')
        with self.assertRaises(ValueError):
            self.store.import_file(source)
        self.assertEqual(self.store.cards(), [])
        self.assertFalse((self.web / 'tools/meta-ads/data/catalog.json').exists())

    def test_private_state_cannot_be_in_web_root(self):
        with self.assertRaises(ValueError):
            Store(self.web / 'private', self.web)

    def test_second_process_cannot_reset_active_jobs(self):
        competitor = self.store.save_competitor({'name': 'Brand', 'keyword': 'cream'})
        self.store.enqueue(competitor['id'], 1)
        with self.assertRaises(ValueError):
            Store(self.root / 'private', self.web)
        self.assertEqual(self.store.jobs()[0]['status'], 'queued')

    def test_input_rejects_urls_and_unbounded_jobs(self):
        for value in ['https://example.com', '../example.com', 'example.com;ls', 'localhost']:
            with self.assertRaises(ValueError):
                competitor_input({'name': 'Brand', 'keyword': 'cream', 'domain': value})
        competitor = self.store.save_competitor({'name': 'Brand', 'keyword': 'cream'})
        for limit in (0, 101, True, '20'):
            with self.assertRaises(ValueError):
                self.store.enqueue(competitor['id'], limit)
        self.store.enqueue(competitor['id'], 1)
        with self.assertRaises(ValueError):
            self.store.enqueue(competitor['id'], 1)

    def test_failed_crawler_is_not_success_and_preserves_archive(self):
        self.store.import_file(self.sample())
        competitor = self.store.save_competitor({'name': 'Brand', 'keyword': 'cream'})
        self.store.enqueue(competitor['id'], 1)
        controller = Controller(self.store)
        class FailedProcess:
            returncode = 1
            def poll(self): return 1
        with patch('server.subprocess.Popen', return_value=FailedProcess()):
            controller.execute(self.store.rows('SELECT * FROM jobs')[0])
        self.assertEqual(self.store.jobs()[0]['status'], 'failed')
        self.assertEqual(len(self.store.cards()), 1)

    def test_canceled_queued_job_never_launches(self):
        competitor = self.store.save_competitor({'name': 'Brand', 'keyword': 'cream'})
        job = self.store.enqueue(competitor['id'], 1)
        controller = Controller(self.store)
        row = self.store.rows('SELECT * FROM jobs')[0]
        controller.cancel(job['id'])
        with patch('server.subprocess.Popen') as process:
            controller.execute(row)
            process.assert_not_called()
        self.assertEqual(self.store.jobs()[0]['status'], 'canceled')

    def test_meta_access_restriction_has_explicit_message_and_utf8_logs(self):
        self.store.import_file(self.sample())
        competitor = self.store.save_competitor({'name': 'Brand', 'keyword': 'cream'})
        self.store.enqueue(competitor['id'], 1)
        controller = Controller(self.store)
        class BlockedProcess:
            returncode = 20
            def poll(self): return 20
        with patch('server.subprocess.Popen', return_value=BlockedProcess()) as process:
            controller.execute(self.store.rows('SELECT * FROM jobs')[0])
        self.assertEqual(process.call_args.kwargs['env']['PYTHONIOENCODING'], 'utf-8')
        self.assertEqual(self.store.jobs()[0]['status'], 'failed')
        self.assertIn('Meta가 수집 요청을 차단했습니다(접근 제한)', self.store.jobs()[0]['message'])
        self.assertEqual(len(self.store.cards()), 1)

    def test_crawler_media_does_not_fetch_private_or_untrusted_hosts(self):
        for url in ('http://fbcdn.net/a.jpg', 'https://127.0.0.1/a', 'https://fbcdn.net.attacker.com/a',
                    'https://user:secret@fbcdn.net/a', 'https://fbcdn.net:444/a'):
            self.assertFalse(crawler.allowed_media_url(url))
        self.assertTrue(crawler.allowed_media_url('https://scontent.xx.fbcdn.net/a.jpg'))

    def test_blocked_and_empty_runs_fail_explicitly(self):
        class BlockedPage:
            url = 'https://www.facebook.com/checkpoint/'
        with self.assertRaises(crawler.CollectionBlocked):
            asyncio.run(crawler.check_access(BlockedPage()))
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
        with patch.object(crawler, 'async_playwright', return_value=Playwright()), \
             patch.object(crawler, 'setup_search', new=AsyncMock()), \
             patch.object(crawler, 'check_access', new=AsyncMock()), \
             patch.object(crawler, 'scroll_until_enough', new=AsyncMock()), \
             patch.object(crawler, 'get_visible_cards', new=AsyncMock(return_value=[])):
            with self.assertRaisesRegex(RuntimeError, 'No usable ads'):
                asyncio.run(crawler.run('cream', 1, '', self.root / 'empty', total_target=1, auto=True, headless=True))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        CollectorTests.setUp(self)
        self.controller = Controller(self.store)
        self.server = Server(0, self.controller)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        CollectorTests.tearDown(self)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        h = {'Content-Type': 'application/json'}
        h.update(headers or {})
        connection.request(method, path, None if body is None else json.dumps(body), h)
        response = connection.getresponse()
        result = (response.status, response.read())
        connection.close()
        return result

    def test_cross_site_and_dns_rebinding_are_rejected(self):
        for headers in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('GET', '/api/meta-ads/bootstrap', headers=headers)[0], 403)
        status, response = self.request('GET', '/api/meta-ads/bootstrap')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(response)['token'])

    def test_mutations_require_both_origin_and_session_token(self):
        body = {'name': 'Brand', 'keyword': 'cream'}
        for headers in ({}, {'Origin': self.origin}, {'X-Meta-Ads-Token': self.controller.token},
                        {'Origin': 'https://evil.example', 'X-Meta-Ads-Token': self.controller.token}):
            self.assertEqual(self.request('POST', '/api/meta-ads/competitors', body, headers)[0], 403)
        headers = {'Origin': self.origin, 'X-Meta-Ads-Token': self.controller.token}
        self.assertEqual(self.request('POST', '/api/meta-ads/competitors', body, headers)[0], 201)

    def test_static_routes_reject_private_files_and_support_media_range(self):
        (self.web / 'services').mkdir()
        (self.web / 'services/secret.json').write_text('{"secret":true}')
        (self.web / 'services/secret.html').write_text('private')
        (self.web / 'catalog.mjs').write_text('export const ready = true;')
        (self.web / 'video.mp4').write_bytes(b'0123456789')
        for path in ('/../private/collector.sqlite3', '/services/secret.json', '/services/secret.html', '/SERVICES/secret.html', '/.git/config', '/%2e%2e/private/collector.sqlite3'):
            self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('GET', '/catalog.mjs')[0], 200)
        self.assertEqual(self.request('GET', '/video.mp4', headers={'Range': 'bytes=2-5'}), (206, b'2345'))
        self.assertEqual(self.request('GET', '/video.mp4', headers={'Range': 'bytes=30-40'})[0], 416)


if __name__ == '__main__':
    unittest.main(verbosity=2)
