"""Only public ad fields and explicitly referenced media leave the private store."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from ad_lifecycle import delivery_fields

MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4'}
MAX_MEDIA_BYTES = 100 * 1024 * 1024
# Verified single-ad product catalogs can contain hundreds of creative images.
MAX_MEDIA_ITEMS_PER_KIND = 1000


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def inside(base, path):
    base, path = Path(base).resolve(), Path(path).resolve()
    if path == base or not path.is_relative_to(base):
        raise ValueError('허용된 폴더 밖의 경로입니다.')
    return path


def public_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return ''
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            return ''
        host = url.hostname.encode('idna').decode('ascii')
        if host in ('localhost', '127.0.0.1', '::1'):
            return ''
        # Keep product identifiers, remove ad tracking and credential-like parameters.
        blocked = ('utm_', 'fbclid', 'gclid', 'access_token', 'token', 'signature', 'key', 'secret')
        query = urlencode([(k, v) for k, v in parse_qsl(url.query) if not any(x in k.lower() for x in blocked)])
        return urlunsplit((url.scheme, url.netloc, url.path, query, ''))
    except (ValueError, UnicodeError):
        return ''


def clean_text(value, maximum=12000):
    return str(value or '').replace('\x00', '')[:maximum].strip()


def date_value(value):
    value = clean_text(value, 80)
    for fmt in ('%Y-%m-%d', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return ''


def normalize_row(row, run_dir, asset_dir):
    if not isinstance(row, dict):
        raise ValueError('광고 레코드는 객체여야 합니다.')
    ad_id = clean_text(row.get('library_id'), 80)
    if not re.fullmatch(r'\d{5,40}', ad_id):
        raise ValueError('올바르지 않은 광고 ID입니다.')
    run_dir, asset_dir = Path(run_dir).resolve(), Path(asset_dir).resolve()

    def copy_media(relative):
        if not isinstance(relative, str) or '\x00' in relative:
            raise ValueError('올바르지 않은 소재 경로입니다.')
        source = inside(run_dir, run_dir / relative.replace('\\', '/'))
        if source.suffix.lower() not in MEDIA_EXTENSIONS or not source.is_file():
            raise ValueError('소재 파일이 없거나 지원되지 않는 형식입니다.')
        if source.stat().st_size > MAX_MEDIA_BYTES:
            raise ValueError('소재 파일이 100MB를 초과합니다.')
        # Hash filenames avoid collision and never copy arbitrary source names.
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
        relative_out = Path(ad_id) / (digest + source.suffix.lower())
        destination = inside(asset_dir, asset_dir / relative_out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
        return relative_out.as_posix()

    def paths(key):
        values = row.get(key, [])
        if not isinstance(values, list):
            raise ValueError('소재 목록이 올바르지 않습니다.')
        if len(values) > MAX_MEDIA_ITEMS_PER_KIND:
            raise ValueError(f'광고 {ad_id}의 {key} 소재가 {len(values)}개입니다. 허용 한도는 {MAX_MEDIA_ITEMS_PER_KIND}개입니다.')
        return [copy_media(item) for item in values]

    images, videos, posters = paths('_saved_images'), paths('_saved_videos'), paths('_saved_posters')
    media = [{'type': 'image', 'path': item} for item in images]
    media += [{'type': 'video', 'path': item, 'posterPath': posters[i] if i < len(posters) else ''}
              for i, item in enumerate(videos)]
    if not media:
        raise ValueError('저장된 이미지 또는 영상이 없는 광고입니다.')
    landing = public_url(row.get('landing_url', ''))
    return {
        'id': ad_id, 'advertiser': clean_text(row.get('advertiser'), 180),
        'text': clean_text(row.get('ad_text')), 'headline': clean_text(row.get('cta_headline'), 500),
        'landingUrl': landing, 'domain': (urlsplit(landing).hostname or '').removeprefix('www.'),
        'libraryUrl': 'https://www.facebook.com/ads/library/?id=' + ad_id,
        'startedAt': date_value(row.get('start_date')),
        'collectedAt': clean_text(row.get('_collected_at'), 80),
        'keyword': clean_text(row.get('_keyword'), 100),
        'platforms': clean_text(row.get('platforms_raw'), 150), 'media': media,
        **delivery_fields(row.get('delivery_status'), row.get('start_date'), row.get('end_date'),
                          clean_text(row.get('_collected_at'), 80)),
    }


def public_card(card):
    allowed = ('id','advertiser','text','headline','landingUrl','domain','libraryUrl','startedAt',
               'collectedAt','keyword','platforms','firstSeenAt','lastSeenAt','statusCheckAttemptAt',
               'statusCheckOutcome')
    result = {key: card[key] for key in allowed if key in card}
    result.update(delivery_fields(card.get('deliveryStatus'), card.get('startedAt'), card.get('endedAt'), card.get('statusCheckedAt'), ended_detected_at=card.get('endedDetectedAt')))
    result['media'] = []
    for media in card['media']:
        item = {'type': media['type'], 'url': '/tools/meta-ads/media/' + media['path']}
        if media.get('posterPath'):
            item['poster'] = '/tools/meta-ads/media/' + media['posterPath']
        result['media'].append(item)
    return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def export_catalog(cards, asset_dir, web_root):
    web_root, asset_dir = Path(web_root).resolve(), Path(asset_dir).resolve()
    target = inside(web_root, web_root / 'tools/meta-ads')
    for card in cards:
        for media in card['media']:
            for key in ('path', 'posterPath'):
                if media.get(key):
                    source = inside(asset_dir, asset_dir / media[key])
                    destination = inside(target, target / 'media' / media[key])
                    if not source.is_file():
                        raise ValueError('내보낼 소재 파일이 없습니다.')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if not destination.exists():
                        shutil.copyfile(source, destination)
    result = {'version': 1, 'updatedAt': now(), 'mode': 'archive',
              'cards': [public_card(card) for card in cards]}
    atomic_json(target / 'data/catalog.json', result)
    return result
