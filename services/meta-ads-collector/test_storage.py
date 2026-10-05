"""Storage selection, unplug safety and archive relocation tests (no network)."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from storage_config import resolve_data_dir, StorageUnavailable
from server import Store, Controller


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = {'LOCALAPPDATA': str(self.root / 'local')}
        self.local = self.root / 'local/JoWooHyung/MetaAds'
        self.local.mkdir(parents=True)
        self.config = self.local / 'settings.json'
        self.external = self.root / 'external/광고 저장'
        self.external.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def configure(self, path):
        # Windows PowerShell commonly writes a UTF-8 BOM.
        self.config.write_text(json.dumps({'dataDir': str(path)}, ensure_ascii=False), encoding='utf-8-sig')

    def test_selection_precedence_and_first_run_creation_policy(self):
        self.assertEqual(resolve_data_dir(environ=self.env), self.local)
        self.configure(self.external)
        self.assertEqual(resolve_data_dir(environ=self.env), self.external)
        override = self.root / 'new-explicit-archive'
        environment = dict(self.env, CRAWLER_DATA_DIR=str(self.root / 'environment-archive'))
        self.assertEqual(resolve_data_dir(environ=environment), self.root / 'environment-archive')
        self.assertEqual(resolve_data_dir(str(override), environ=environment), override)
        self.assertFalse(override.exists(), 'Selection must not create a directory.')

    def test_malformed_settings_and_relative_paths_do_not_fall_back(self):
        for contents in ('{invalid', '[]', '{}', '{"dataDir": "relative/path"}', '{"dataDir": null}'):
            with self.subTest(contents=contents):
                self.config.write_text(contents, encoding='utf-8')
                with self.assertRaises(ValueError):
                    resolve_data_dir(environ=self.env)
        with self.assertRaises(ValueError):
            resolve_data_dir('relative/path', environ=self.env)
        with self.assertRaises(ValueError):
            resolve_data_dir(environ=dict(self.env, CRAWLER_DATA_DIR='relative/path'))

    def test_missing_configured_directory_and_unavailable_drive_are_errors(self):
        missing = self.external / 'missing'
        self.configure(missing)
        with self.assertRaises(StorageUnavailable):
            resolve_data_dir(environ=self.env)
        self.assertFalse(missing.exists())
        self.configure(self.external)
        original = Path.is_dir
        anchor = Path(self.external.anchor)
        with patch.object(Path, 'is_dir', lambda p: False if p == anchor else original(p)):
            with self.assertRaises(StorageUnavailable):
                resolve_data_dir(str(self.external), environ=self.env)
        self.assertFalse((self.local / 'collector.sqlite3').exists())

    def test_unplug_stops_writes_and_worker_without_starting_crawler(self):
        web = self.root / 'web'
        web.mkdir()
        store = Store(self.external, web)
        try:
            with patch.object(Controller, 'check_runtime', return_value=False):
                controller = Controller(store)
            original = Path.is_dir
            with patch.object(Path, 'is_dir', lambda p: False if p == store.root else original(p)):
                with self.assertRaises(StorageUnavailable):
                    store.write('DELETE FROM ads')
                with patch('server.subprocess.Popen') as process:
                    with self.assertRaises(StorageUnavailable):
                        controller.execute({'id': 'do-not-start'})
                    process.assert_not_called()
                status = controller.status()
                self.assertFalse(status['storageAvailable'])
                self.assertEqual(status['storagePath'], str(self.external))
            self.assertEqual(store.cards(), [])
            self.assertFalse((self.local / 'collector.sqlite3').exists())
        finally:
            store.close()

    def test_copying_archive_preserves_relative_media_and_public_urls(self):
        web = self.root / 'web'
        web.mkdir()
        original = self.root / 'old-archive'
        store = Store(original, web)
        run = original / 'runs/one'
        run.mkdir(parents=True)
        (run / 'image.jpg').write_bytes(b'storage migration media fixture')
        source = run / 'cards.jsonl'
        source.write_text(json.dumps({'library_id': '123456789', 'advertiser': 'Public brand',
                                     '_saved_images': ['image.jpg']}), encoding='utf-8')
        store.import_file(source)
        store.close()
        shutil.copytree(original, self.external, dirs_exist_ok=True)
        moved = Store(self.external, web)
        try:
            self.assertEqual(len(moved.cards()), 1)
            asset = moved.cards()[0]['media'][0]['path']
            self.assertTrue((self.external / 'media' / asset).is_file())
            self.assertFalse(Path(asset).is_absolute())
            public = moved.export()
            self.assertEqual(public['cards'][0]['media'][0]['url'], '/tools/meta-ads/media/' + asset)
            self.assertNotIn(str(self.external), json.dumps(public))
        finally:
            moved.close()


if __name__ == '__main__':
    unittest.main()
