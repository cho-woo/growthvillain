"""Exact query provenance, bounded keyword queue and dated observation evidence."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from catalog import public_card
from keyword_evidence import ad_evidence, evidence_index, merge_query_fields
from naver_trends import compare_snapshots, dispatch_key
from server import Store
from test_trend_service import snapshots
from trend_service import TrendService, KST
from backfill_keyword_links import backfill


class QueryEvidenceTests(unittest.TestCase):
    def test_multiquery_provenance_keeps_first_and_last_collection_dates(self):
        old = {'keyword': '인삼', 'collectedAt': '2026-10-01T00:00:00Z'}
        new = {'keyword': '면역 영양제', 'collectedAt': '2026-10-03T00:00:00Z'}
        merged = {**new, **merge_query_fields(old, new)}
        again = {'keyword': '면역영양제', 'collectedAt': '2026-10-06T00:00:00Z'}
        history = merge_query_fields(merged, again)
        self.assertEqual(set(history['matchedKeywords']), {'인삼', '면역 영양제'})
        linked = next(row for row in history['queryEvidence'] if row['query'] == '면역 영양제')
        self.assertEqual(linked['firstCollectedAt'], '2026-10-03T00:00:00+00:00')
        self.assertEqual(linked['lastCollectedAt'], '2026-10-06T00:00:00+00:00')

    def test_timing_is_observational_and_copy_mentions_are_not_query_links(self):
        cards = [{'id':str(123450+i), 'keyword':'인삼', 'collectedAt':'2026-10-07T00:00:00Z',
                  'advertiser':'공개 광고주', 'text':'비타민 카피에 등장', 'startedAt':start}
                 for i,start in enumerate(('2026-09-29','2026-09-30','2026-10-06','2026-10-07',''))]
        item = {'keyword':'인삼','previousDate':'2026-09-29','date':'2026-10-06'}
        evidence = ad_evidence(item,evidence_index(cards))
        self.assertEqual(evidence['adCount'],5)
        self.assertFalse(evidence['causationEstablished'])
        timing = {ad['id']:ad['startTiming'] for ad in evidence['ads']}
        self.assertEqual([timing[str(123450+i)] for i in range(5)],
                         ['before-window','during-window','during-window','after-window','unknown'])
        self.assertEqual(ad_evidence({**item,'keyword':'비타민'},evidence_index(cards))['adCount'],0)
        self.assertEqual(evidence['advertisers'],[{'name':'공개 광고주','adCount':5}])

    def test_public_provenance_whitelists_nested_fields(self):
        card={'id':'123456','keyword':'인삼','collectedAt':'2026-10-07T00:00:00Z','media':[],
              'queryEvidence':[{'query':'비타민','firstCollectedAt':'2026-10-01T00:00:00Z',
                                'lastCollectedAt':'2026-10-02T00:00:00Z','token':'SECRET','path':'PRIVATE'}]}
        public=public_card(card)
        self.assertEqual(set(public['matchedKeywords']),{'인삼','비타민'})
        self.assertNotIn('SECRET',json.dumps(public))
        self.assertNotIn('PRIVATE',json.dumps(public))

    def test_same_brand_different_keywords_stay_independently_collectable(self):
        current,previous=snapshots(names=('검증브랜드크림','검증브랜드토너'))
        items=compare_snapshots(current,previous,brands=[{'id':'a','name':'검증브랜드'}],keyword_mode=True)
        self.assertEqual(len(items),2)
        self.assertEqual(len({item['dispatchKey'] for item in items}),2)
        self.assertTrue(all(not item['needsReview'] for item in items))


class KeywordQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.store=Store(self.base/'private',self.base/'web')
        self.service=TrendService(self.store)

    def tearDown(self):
        self.service.stop()
        self.store.close()
        self.temp.cleanup()

    def seed(self,names,days_ago=1):
        current,previous=snapshots(names=names,days_ago=days_ago)
        self.service.record_snapshots(current,previous,current['category'])
        return current

    def test_meta_off_blocks_automatic_but_keeps_keyword_candidates(self):
        self.seed(('인삼','마그네슘'))
        self.service.save_settings({'autoEnabled':True})
        self.service.can_collect=lambda:False
        self.assertEqual(self.service.dispatch_ready(),0)
        self.assertEqual(len(self.service.candidates()),2)
        self.assertFalse(self.service.collection_policy()['enabled'])
        self.assertIsNone(self.service.collection_policy()['nextDispatchAt'])
        with self.assertRaisesRegex(ValueError,'OFF'):
            self.service.collect(self.service.candidates()[0]['dispatchKey'],automatic=True)
        self.assertEqual(self.store.jobs(),[])

    def test_old_uncollected_keywords_do_not_starve_behind_new_top_keywords(self):
        self.seed(('이전미수집',),days_ago=4)
        self.seed(('오늘급상승',))
        self.service.save_settings({'autoEnabled':True})
        pending=self.service.collection_candidates()
        self.assertEqual([item['keyword'] for item in pending],['이전미수집','오늘급상승'])
        self.assertEqual(pending[0]['state'],'backlog')
        self.assertEqual(pending[0]['collectionReason'],'historical-backlog')
        self.assertEqual(self.service.dispatch_ready(),1)
        self.assertEqual(self.store.jobs()[0]['keyword'],'이전미수집')
        self.assertEqual(self.store.jobs()[0]['domain'],'')

    def test_never_collected_beats_already_collected_and_oldest_collection_wins(self):
        self.seed(('이미수집최상위','미수집','오래된수집'))
        for number,(keyword,stamp) in enumerate((('이미수집최상위','2026-10-06T00:00:00Z'),('오래된수집','2026-10-01T00:00:00Z'))):
            card={'id':str(123456+number),'keyword':keyword,'collectedAt':stamp,'media':[]}
            self.store.write('INSERT INTO ads(id,payload) VALUES(?,?)',(card['id'],json.dumps(card)))
        self.assertEqual([c['keyword'] for c in self.service.collection_candidates()],
                         ['미수집','오래된수집','이미수집최상위'])

    def test_legacy_brand_dispatch_migrates_query_and_counts_daily_budget(self):
        current=self.seed(('센트룸',))
        brand=self.service.save_brand({'name':'센트룸'})
        key=dispatch_key(current['category'],current['date'],brand['id'])
        stamp=datetime.now(KST).replace(hour=0,minute=1,second=0).timestamp()
        self.store.write("INSERT INTO jobs(id,competitor_id,name,keyword,domain,max_ads,status,requested_at) VALUES(?,?,?,?,?,?,?,?)",
                         ('legacy-job',brand['competitorId'],'센트룸','센트룸','',20,'done',current['date']))
        self.store.write('INSERT INTO trend_dispatches(dispatch_key,brand_id,job_id,queued_at,automatic) VALUES(?,?,?,?,?)',
                         (key,brand['id'],'legacy-job',stamp,1))
        restarted=TrendService(self.store)
        try:
            candidate=restarted.candidates()[0]
            self.assertEqual(candidate['dispatchKey'],key)
            self.assertEqual(candidate['state'],'done')
            self.assertEqual(restarted.collect(key)['id'],'legacy-job')
            self.assertEqual(restarted.collection_policy()['dailyUsed'],1)
            self.assertEqual(restarted.collection_policy()['dailyRemaining'],287)
            self.assertEqual(self.store.rows('SELECT keyword FROM trend_dispatches')[0]['keyword'],'센트룸')
        finally:
            restarted.stop()

    def test_import_same_ad_with_two_queries_preserves_both_links_and_public_evidence(self):
        self.seed(('인삼','마그네슘'))
        self.store.on_import=self.service.export
        run=self.base/'run'
        run.mkdir()
        (run/'public.jpg').write_bytes(b'public fixture')
        for query in ('인삼','마그네슘'):
            record={'library_id':'123456789','advertiser':'광고주','start_date':'2026-10-01',
                    '_saved_images':['public.jpg'],'_keyword':query,'_collected_at':'2026-10-07T00:00:00Z'}
            (run/'cards.jsonl').write_text(json.dumps(record),encoding='utf-8')
            self.store.import_file(run/'cards.jsonl')
        self.assertEqual(len(self.store.cards()),1)
        self.assertEqual(set(self.store.cards()[0]['matchedKeywords']),{'인삼','마그네슘'})
        public=json.loads((self.base/'web/tools/meta-ads/data/trends.json').read_text(encoding='utf-8'))
        for item in public['candidates']:
            self.assertEqual(item['adEvidence']['adIds'],['123456789'])
            self.assertEqual(item['adEvidence']['adCount'],1)
            self.assertNotIn('dispatchKey',item)

    def test_offline_backfill_restores_old_query_without_copying_raw_private_fields(self):
        card={'id':'123456789','advertiser':'광고주','keyword':'최근검색어',
              'collectedAt':'2026-10-07T00:00:00Z','media':[]}
        self.store.write('INSERT INTO ads(id,payload) VALUES(?,?)',(card['id'],json.dumps(card)))
        run=self.store.root/'runs/old-public-run'
        run.mkdir(parents=True)
        row={'library_id':card['id'],'_keyword':'이전검색어','_collected_at':'2026-10-01T00:00:00Z',
             'cookies':'NEVER_COPY','_saved_images':['../../../private.jpg']}
        (run/'cards.jsonl').write_text(json.dumps(row),encoding='utf-8')
        self.assertEqual(backfill(self.store)['linkedAds'],1)
        recovered=self.store.cards()[0]
        self.assertEqual(set(recovered['matchedKeywords']),{'최근검색어','이전검색어'})
        self.assertNotIn('NEVER_COPY',json.dumps(recovered))
        self.assertNotIn('private.jpg',json.dumps(recovered))
        self.assertEqual(recovered['keyword'],'최근검색어')
        self.assertEqual(backfill(self.store)['linkedAds'],0)


if __name__=='__main__':
    unittest.main()
