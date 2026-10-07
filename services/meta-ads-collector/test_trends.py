"""Deterministic fixtures only; invented names are never production seed data."""
import copy
import unittest

from naver_trends import (compare_snapshots, dispatch_key, match_brand,
                          normalize_keyword, validate_brands, validate_snapshot)


SOURCE = 'https://datalab.naver.com/shoppingInsight/sCategory.naver'


def snapshot(day='2026-10-04', count=100, category='50000002'):
    return {'category': category, 'date': day, 'sourceUrl': SOURCE,
            'entries': [{'rank': i, 'keyword': f'검증용 일반검색어 {i:03d}'} for i in range(1, count + 1)]}


def moved(source, old_rank, new_rank):
    result = copy.deepcopy(source)
    keyword = result['entries'].pop(old_rank - 1)['keyword']
    result['entries'].insert(new_rank - 1, {'keyword': keyword})
    for rank, row in enumerate(result['entries'], 1):
        row['rank'] = rank
    return result


class SnapshotTests(unittest.TestCase):
    def test_complete_hundred_ranks_are_canonical_and_not_mutated(self):
        source = snapshot()
        source['entries'].reverse()
        before = copy.deepcopy(source)
        clean = validate_snapshot(source)
        self.assertEqual(clean['entries'][0]['rank'], 1)
        self.assertEqual(clean['entries'][-1]['rank'], 100)
        self.assertEqual(source, before)

    def test_empty_partial_and_missing_middle_are_rejected(self):
        for entries in ([], snapshot()['entries'][:99], snapshot()['entries'][1:] + [{'rank': 101, 'keyword': '추가 항목'}]):
            with self.subTest(count=len(entries)), self.assertRaises(ValueError):
                validate_snapshot({**snapshot(), 'entries': entries})

    def test_duplicate_rank_or_normalized_keyword_are_rejected(self):
        duplicate_rank = snapshot()
        duplicate_rank['entries'][1]['rank'] = 1
        duplicate_keyword = snapshot()
        duplicate_keyword['entries'][1]['keyword'] = '검증용일반검색어001'
        for value in (duplicate_rank, duplicate_keyword):
            with self.assertRaises(ValueError):
                validate_snapshot(value)

    def test_invalid_dates_ranks_sources_and_hidden_characters_fail(self):
        for day in ('2026-02-30', '2026-1-02', '', None):
            with self.subTest(day=day), self.assertRaises(ValueError):
                validate_snapshot({**snapshot(), 'date': day})
        for rank in (0, 501, True, '1'):
            value = snapshot()
            value['entries'][0]['rank'] = rank
            with self.subTest(rank=rank), self.assertRaises(ValueError):
                validate_snapshot(value)
        for source in ('http://datalab.naver.com/', 'https://datalab.naver.com.attacker.test/',
                       'https://user:secret@datalab.naver.com/', 'https://datalab.naver.com:bad/'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_snapshot({**snapshot(), 'sourceUrl': source})
        value = snapshot()
        value['entries'][0]['keyword'] = '눈에\u200b안보임'
        with self.assertRaises(ValueError):
            validate_snapshot(value)

    def test_explicit_top_one_and_top_five_hundred_supported(self):
        self.assertEqual(len(validate_snapshot(snapshot(count=1), expected_count=1)['entries']), 1)
        self.assertEqual(len(validate_snapshot(snapshot(count=500), expected_count=500)['entries']), 500)


class BrandTests(unittest.TestCase):
    BRANDS = [{'id': 'fixture-a', 'name': '검증브랜드', 'aliases': ['Example Brand']},
              {'id': 'fixture-b', 'name': '검증브랜드플러스', 'aliases': ['Example Brand Plus']}]

    def test_longest_leading_alias_and_spacing_case_normalization(self):
        self.assertEqual(match_brand('검증 브랜드 플러스 크림', self.BRANDS)['id'], 'fixture-b')
        self.assertEqual(match_brand('ｅＸＡＭＰＬＥ brandplus 토너', self.BRANDS)['id'], 'fixture-b')
        self.assertEqual(match_brand('EXAMPLEbrand 토너', self.BRANDS)['id'], 'fixture-a')
        self.assertEqual(normalize_keyword(' Ａ b C '), 'abc')

    def test_generic_and_nonleading_mentions_never_guess_a_brand(self):
        self.assertIsNone(match_brand('마스크팩', self.BRANDS))
        self.assertIsNone(match_brand('추천 검증브랜드 크림', self.BRANDS))
        self.assertIsNone(match_brand('검증브랜드 크림', []))

    def test_duplicate_alias_owners_and_duplicate_ids_fail(self):
        for brands in ([{'id': 'a', 'name': '한 브랜드'}, {'id': 'b', 'name': '한브랜드'}],
                       [{'id': 'a', 'name': '첫째'}, {'id': 'a', 'name': '둘째'}]):
            with self.assertRaises(ValueError):
                validate_brands(brands)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.previous = snapshot('2026-09-27')
        self.current = snapshot('2026-10-04')

    def test_exact_threshold_and_top_one(self):
        self.current = moved(self.current, 11, 1)
        result = compare_snapshots(self.current, self.previous)
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]['previousRank'], result[0]['currentRank'], result[0]['rankRise']), (11, 1, 10))
        self.assertEqual(result[0]['periodDays'], 7)
        self.assertEqual(result[0]['currentDate'], '2026-10-04')
        self.assertTrue(result[0]['needsReview'])
        self.assertIsNone(result[0]['brandId'])
        self.assertIsNone(result[0]['dispatchKey'])
        self.assertEqual(compare_snapshots(self.current, self.previous, minimum_rise=11), [])

    def test_unchanged_or_falling_is_not_rising(self):
        self.assertEqual(compare_snapshots(self.current, self.previous), [])
        self.current = moved(self.current, 1, 100)
        self.assertEqual(compare_snapshots(self.current, self.previous), [])

    def test_new_entry_is_labeled_without_fabricated_delta(self):
        self.current['entries'][19]['keyword'] = '검증용 신규상위검색어'
        self.current['entries'][20]['keyword'] = '검증용 신규하위검색어'
        result = compare_snapshots(self.current, self.previous)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['currentRank'], 20)
        self.assertTrue(result[0]['isNew'])
        self.assertIsNone(result[0]['previousRank'])
        self.assertIsNone(result[0]['rankRise'])

    def test_missing_or_partial_baseline_never_claims_new_entries(self):
        for previous in (None, {**self.previous, 'entries': []},
                         {**self.previous, 'entries': self.previous['entries'][:99]}):
            with self.assertRaises(ValueError):
                compare_snapshots(self.current, previous)

    def test_cross_category_same_day_wrong_gap_and_reversed_dates_fail(self):
        for previous in ({**self.previous, 'category': 'different'},
                         {**self.previous, 'date': '2026-10-04'},
                         {**self.previous, 'date': '2026-09-26'},
                         {**self.previous, 'date': '2026-10-11'}):
            with self.assertRaises(ValueError):
                compare_snapshots(self.current, previous)

    def test_changed_spacing_is_not_a_new_keyword(self):
        self.previous['entries'][0]['keyword'] = '검증 BRAND 토너'
        self.current['entries'][0]['keyword'] = '검증brand토너'
        self.assertEqual(compare_snapshots(self.current, self.previous), [])

    def test_confirmed_brand_deduplicates_to_largest_measured_rise(self):
        self.previous['entries'][49]['keyword'] = '검증브랜드 크림'
        self.previous['entries'][79]['keyword'] = 'Example Brand 토너'
        self.current['entries'][4]['keyword'] = '검증브랜드 크림'
        self.current['entries'][9]['keyword'] = 'Example Brand 토너'
        self.current['entries'][0]['keyword'] = '검증브랜드 신규제품'
        brands = [{'id': 'fixture-brand', 'name': '검증브랜드', 'aliases': ['Example Brand']}]
        result = compare_snapshots(self.current, self.previous, brands)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['rankRise'], 70)
        self.assertEqual(result[0]['brandId'], 'fixture-brand')
        self.assertFalse(result[0]['needsReview'])
        self.assertEqual(result[0]['dispatchKey'], dispatch_key('50000002', '2026-10-04', 'fixture-brand'))

    def test_unknown_candidates_remain_separate_for_review(self):
        self.current['entries'][0]['keyword'] = '검증용 미확인 검색어 가'
        self.current['entries'][1]['keyword'] = '검증용 미확인 검색어 나'
        result = compare_snapshots(self.current, self.previous)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row['needsReview'] and row['dispatchKey'] is None for row in result))

    def test_top_one_new_entry_and_configured_comparison_interval(self):
        previous = snapshot('2026-10-03', count=1)
        current = snapshot('2026-10-04', count=1)
        current['entries'][0]['keyword'] = '다른 검증용 검색어'
        result = compare_snapshots(current, previous, expected_count=1, lookback_days=1)
        self.assertTrue(result[0]['isNew'])
        self.assertIsNone(result[0]['rankRise'])
        self.assertEqual(result[0]['periodDays'], 1)

    def test_dispatch_key_is_stable_and_separates_category_date_brand(self):
        key = dispatch_key('50000002', '2026-10-04', 'brand-a')
        self.assertEqual(key, dispatch_key('50000002', '2026-10-04', 'brand-a'))
        self.assertEqual(len(key), 64)
        self.assertNotEqual(key, dispatch_key('50000003', '2026-10-04', 'brand-a'))
        self.assertNotEqual(key, dispatch_key('50000002', '2026-10-05', 'brand-a'))
        self.assertNotEqual(key, dispatch_key('50000002', '2026-10-04', 'brand-b'))


if __name__ == '__main__':
    unittest.main()
