"""Large verified single-ad catalogs retain all assets and path validation."""
import json
from pathlib import Path
import tempfile
import unittest

from catalog import MAX_MEDIA_ITEMS_PER_KIND, normalize_row
from server import Store
from crawler import async_playwright, get_visible_cards


class LargeCarouselTests(unittest.TestCase):
    def test_353_images_import_and_export_and_remain_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            run=base/'run'
            (run/'media').mkdir(parents=True)
            names=[]
            for number in range(353):
                name=f'media/{number}.jpg'
                (run/name).write_bytes(b'public test image '+str(number).encode())
                names.append(name)
            row={'library_id':'123456789','advertiser':'Test','_saved_images':names,
                 '_collected_at':'2026-10-07T00:00:00Z','_private_cookie':'DO_NOT_EXPORT'}
            path=run/'cards.jsonl'
            path.write_text(json.dumps(row),encoding='utf-8')
            store=Store(base/'private',base/'web')
            try:
                self.assertEqual(store.import_file(path),1)
                public=json.loads((base/'web/tools/meta-ads/data/catalog.json').read_text(encoding='utf-8'))
                self.assertEqual(len(public['cards'][0]['media']),353)
                self.assertNotIn('DO_NOT_EXPORT',json.dumps(public))
                for media in public['cards'][0]['media']:
                    self.assertTrue((base/'web'/media['url'].lstrip('/')).is_file())
                self.assertEqual(store.import_file(path),0)
                # Larger lists retain the same containment and missing-file checks.
                (base/'outside.jpg').write_bytes(b'outside')
                for unsafe in ('../outside.jpg','media/missing.jpg','media/config.json'):
                    with self.subTest(path=unsafe), self.assertRaises(ValueError):
                        normalize_row({**row,'_saved_images':names+[unsafe]},run,base/'assets')
            finally:
                store.close()

    def test_1001_media_entries_fail_before_file_copy_without_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            row={'library_id':'123456789','_saved_images':['image.jpg']*(MAX_MEDIA_ITEMS_PER_KIND+1)}
            with self.assertRaisesRegex(ValueError,'1001.*1000'):
                normalize_row(row,base,base/'assets')
            self.assertFalse((base/'assets').exists())


@unittest.skipUnless(async_playwright is not None,'Playwright runtime is not installed')
class CardBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_wide_wrapper_does_not_capture_a_single_ad_id(self):
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True)
            try:
                page=await browser.new_page(viewport={'width':1440,'height':1000})
                # More than eight oversized ancestors previously exhausted the
                # search while leaving an unmatched page wrapper as a candidate.
                wrappers='<div style="width:1200px;height:900px">'*12
                card='<div id="real-card" style="width:350px;height:300px">Active<br>Library ID: 123456789<br>Platforms<br>Public creative</div>'
                await page.set_content(wrappers+card+'</div>'*12)
                cards=await get_visible_cards(page)
                self.assertEqual(len(cards),1)
                self.assertEqual(await cards[0].get_attribute('id'),'real-card')
                self.assertEqual(await page.locator('[data-crawl-id]').count(),1)
            finally:
                await browser.close()


if __name__=='__main__':
    unittest.main()
