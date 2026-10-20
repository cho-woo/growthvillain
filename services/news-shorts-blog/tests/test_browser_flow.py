"""Opt-in real Chromium integration against intercepted HTML; no external posts."""
import html
import os
from pathlib import Path
import tempfile
import unittest

from news_agent.core import Store, article_for, now_kst
from news_agent.naver import NaverPublisher, PublishNotSubmitted
from news_agent.youtube import Video


@unittest.skipUnless(os.environ.get('NEWS_AGENT_TEST_BROWSER'), 'Set NEWS_AGENT_TEST_BROWSER to a Chromium executable')
class BrowserFlowTests(unittest.TestCase):
    def test_editor_to_confirmed_receipt_and_durable_quota(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
            store = Store(Path(tmp)/'agent.sqlite3')
            current = now_kst().replace(hour=12, minute=0)
            video = Video('abcdefghijk', 'UC'+'a'*22, 'SBS 뉴스', '국회 긴급회의 개최',
                          'https://www.youtube.com/shorts/abcdefghijk', current)
            store.observe([video], current)
            article = article_for(store.candidate(current))
            browser = playwright.chromium.launch(executable_path=os.environ['NEWS_AGENT_TEST_BROWSER'], headless=True)
            page = browser.new_page()
            seen_submission = []
            post_url = 'https://blog.naver.com/wdetector/123456789'

            def intercept(route):
                if '/PostWriteForm.naver' in route.request.url:
                    markup = '''<!doctype html><html lang="ko"><body>
                    <div class="se-documentTitle"><div contenteditable="true"></div></div>
                    <div class="se-component se-text"><div contenteditable="true"></div></div>
                    <button class="publish_btn_test" onclick="document.querySelector('#settings').hidden=false">발행</button>
                    <div id="settings" hidden>
                      <button class="category_select_test" onclick="document.querySelector('#categories').hidden=false">미분류</button>
                      <div id="categories" hidden><button role="option" onclick="document.querySelector('.category_select_test').innerText='이슈';document.querySelector('#categories').hidden=true">이슈</button></div>
                      <button class="topic_select_test" onclick="document.querySelector('#topics').hidden=false">주제 선택</button>
                      <div id="topics" hidden><button role="option" onclick="document.querySelector('.topic_select_test').innerText='사회·정치';document.querySelector('#topics').hidden=true">사회·정치</button></div>
                      <input type="radio" id="public" name="visibility"><label for="public">공개</label>
                      <button class="confirm_btn_test" onclick="window.location.href=''' + "'" + post_url + "'" + '''">발행</button>
                    </div></body></html>'''
                elif route.request.url == post_url:
                    with store.connect() as db:
                        state = db.execute('SELECT state FROM attempts WHERE video_id=?', (video.video_id,)).fetchone()[0]
                    seen_submission.append(state)
                    markup = '<html><body><h1>'+html.escape(article['title'])+'</h1><p>'+html.escape(article['body'])+'</p></body></html>'
                else:
                    route.abort()
                    return
                route.fulfill(status=200, content_type='text/html; charset=utf-8', body=markup)

            page.route('**/*', intercept)
            publisher = NaverPublisher(Path(tmp)/'profile')
            publisher._page = page
            def reserve():
                self.assertEqual(page.locator('.category_select_test').inner_text(), '이슈')
                self.assertEqual(page.locator('.topic_select_test').inner_text(), '사회·정치')
                self.assertTrue(page.get_by_role('radio', name='공개', exact=True).is_checked())
                store.before_submit(video.video_id, current)
            result = publisher.publish(article, 'wdetector', category='이슈', topic='사회·정치', before_submit=reserve)
            self.assertEqual(result, post_url)
            self.assertEqual(seen_submission, ['submitting'])
            store.complete(video.video_id, result, 'wdetector', current)
            self.assertEqual(store.snapshot(current)['counts'], {'published': 1})
            self.assertIsNone(store.candidate(current))
            browser.close()


if __name__ == '__main__':
    unittest.main()
