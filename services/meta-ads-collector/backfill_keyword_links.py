"""Recover recorded query associations from saved public runs without re-crawling.

Run only while the local collector is stopped. Store's process lock prevents
opening the archive concurrently. Only existing ad IDs and public query/date
metadata are updated; this never imports unrelated JSON fields or media files.
"""
import argparse
import json
from pathlib import Path
import re

from keyword_evidence import merge_query_fields


def backfill(store):
    root = (store.root / 'runs').resolve()
    cards = {card['id']: card for card in store.cards()}
    updated, inspected, ignored = set(), 0, 0
    if root.is_dir():
        for path in root.glob('*/cards.jsonl'):
            resolved = path.resolve()
            if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.stat().st_size > 20*1024*1024:
                ignored += 1
                continue
            inspected += 1
            try:
                lines = resolved.read_text(encoding='utf-8-sig').splitlines()
            except (OSError, UnicodeError):
                ignored += 1
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError('invalid row')
                    ad_id = row.get('library_id')
                    if not isinstance(ad_id, str) or not re.fullmatch(r'\d{5,40}', ad_id) or ad_id not in cards:
                        continue
                    current = cards[ad_id]
                    public = {'keyword': row.get('_keyword'), 'collectedAt': row.get('_collected_at')}
                    fields = merge_query_fields(current, public)
                    if any(current.get(key) != value for key, value in fields.items()):
                        current.update(fields)
                        updated.add(ad_id)
                except (ValueError, TypeError, KeyError):
                    ignored += 1
    if updated:
        with store.lock:
            try:
                for ad_id in updated:
                    store.db.execute('UPDATE ads SET payload=? WHERE id=?',
                                     (json.dumps(cards[ad_id], ensure_ascii=False), ad_id))
                store.db.commit()
            except Exception:
                store.db.rollback()
                raise
    return {'inspectedFiles': inspected, 'linkedAds': len(updated), 'ignoredRowsOrFiles': ignored}


def main():
    parser = argparse.ArgumentParser(description='수집기 종료 후 저장된 공개 광고의 검색어 연결 복구')
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--web-root', type=Path, required=True)
    args = parser.parse_args()
    from server import Store
    from trend_service import TrendService
    store = Store(args.data_dir, args.web_root)
    try:
        result = backfill(store)
        store.export()
        TrendService(store).export()
        print(json.dumps(result, ensure_ascii=False))
    finally:
        store.close()


if __name__ == '__main__':
    main()
