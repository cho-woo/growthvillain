"""Public delivery evidence, with reported end dates separate from absence detection.

Durations include start and end calendar dates (Korea time). Only a complete,
normal exact-ID lookup with an explicit missing-ad message detects absence.
HTTP errors or omission from keyword results never prove an end.
"""
from datetime import date, datetime, timedelta, timezone
import re
from keyword_evidence import merge_query_fields

KST = timezone(timedelta(hours=9))
LIFECYCLE_FIELDS = ('deliveryStatus', 'endedAt', 'endedDetectedAt', 'durationDays',
                    'durationLabel', 'durationBasis', 'durationCountMethod', 'statusCheckedAt')


def iso_date(value):
    value = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    match = re.fullmatch(r'(\d{4})[.년]\s*(\d{1,2})[.월]\s*(\d{1,2})[.일]?', value)
    try:
        return date(*map(int, match.groups())).isoformat() if match else ''
    except ValueError:
        return ''


def _today():
    return datetime.now(KST).date()


def _observation_date(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=KST)
        day = stamp.astimezone(KST).date()
        return day if day <= _today() else None
    except (TypeError, ValueError):
        return None


def parse_delivery(text):
    # Only the ad-library header before the creative body is evidence. Do not
    # interpret promotional text mentioning an "active" ingredient as status.
    header = re.split(r'플랫폼|Platforms|이 광고의 여러 버전|See ad details|광고 상세 정보', text, maxsplit=1, flags=re.I)[0][:1400]
    status_header = re.split(r'(?:라이브러리 ID|Library ID)\s*:', header, maxsplit=1, flags=re.I)[0]
    status = 'unknown'
    if re.search(r'(?:^|\n)\s*(?:비활성|게재 종료|Inactive)\b', status_header, re.I):
        status = 'ended'
    elif re.search(r'(?:^|\n)\s*(?:활성|Active)\b', status_header, re.I):
        status = 'active'
    start, end = '', ''
    kr = r'(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)'
    en = r'([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})'
    started = re.search(kr + r'\s*에\s*게재\s*시작', header)
    if not started:
        started = re.search(r'Started running on\s+' + en, header, re.I)
    if started:
        start = iso_date(started[1])
    ended = re.search(kr + r'\s*에\s*(?:게재\s*)?종료', header)
    if not ended:
        ended = re.search(r'(?:Stopped running|Ended) on\s+' + en, header, re.I)
    if ended:
        end = iso_date(ended[1])
        status = 'ended'
    if status == 'ended':
        ranged = re.search(kr + r'\s*(?:~|–|—|-)\s*' + kr, header)
        if not ranged:
            ranged = re.search(en + r'\s*(?:~|–|—|-)\s*' + en, header)
        if ranged:
            start, end = iso_date(ranged[1]), iso_date(ranged[2])
    if end and ((start and end < start) or end > _today().isoformat()):
        end = ''
    return {'delivery_status': status, 'start_date': start, 'end_date': end}


def delivery_fields(status='unknown', start='', end='', checked_at='', *, ended_detected_at=''):
    """Return public fields without treating an observation as a reported end."""
    status = status if status in ('active', 'ended', 'unknown') else 'unknown'
    start, end = iso_date(start), iso_date(end)
    detected_day = _observation_date(ended_detected_at) if ended_detected_at else None
    if status != 'ended':
        end, ended_detected_at, detected_day = '', '', None
    elif end and ((start and end < start) or end > _today().isoformat()):
        end = ''
    if not detected_day:
        ended_detected_at = ''
    basis = 'reported' if end else 'detected' if detected_day else None
    effective_end = date.fromisoformat(end) if end else detected_day
    start_day = date.fromisoformat(start) if start else None
    duration = ((effective_end - start_day).days + 1
                if effective_end and start_day and effective_end >= start_day else None)
    if status == 'ended':
        label = f'{duration}일 게재 후 종료' if duration is not None else '종료 · 기간 미확인'
        if basis == 'detected':
            label += ' · 감지일 기준'
    else:
        label = '게재 중' if status == 'active' else '게재 상태 미확인'
    return {'deliveryStatus': status, 'endedAt': end or None,
            'endedDetectedAt': ended_detected_at or None, 'durationDays': duration,
            'durationLabel': label, 'durationBasis': basis,
            'durationCountMethod': 'inclusive-calendar-days', 'statusCheckedAt': checked_at or None}


def absence_fields(existing, checked_at):
    """Apply only confirmed exact-ID ``not_found``; repeated absence keeps its date.

    A source-reported end date takes precedence. The detection interval may
    include days after the actual end, hence the explicit estimate label.
    """
    if _observation_date(checked_at) is None:
        raise ValueError('종료 감지에는 유효한 확인 시각이 필요합니다.')
    was_ended = existing.get('deliveryStatus') == 'ended'
    reported = existing.get('endedAt') if was_ended else ''
    detected = existing.get('endedDetectedAt') if was_ended else ''
    return delivery_fields('ended', existing.get('startedAt'), reported, checked_at,
                           ended_detected_at=detected or checked_at)


def merge_status_observation(previous, observation):
    """Merge a checker result; network failures preserve lifecycle evidence."""
    result = dict(previous)
    outcome, checked_at = observation.get('outcome'), observation.get('checkedAt')
    if outcome not in ('confirmed', 'not_found', 'unavailable', 'blocked'):
        return result
    result.update(statusCheckAttemptAt=checked_at, statusCheckOutcome=outcome)
    if outcome == 'not_found':
        result.update(absence_fields(previous, checked_at))
    elif outcome == 'confirmed':
        status = observation.get('delivery_status')
        if status == 'unknown' and previous.get('durationBasis') == 'detected' and not previous.get('endedAt'):
            # The exact saved ID exists again, but its current status label is
            # unavailable. Withdraw the absence inference without claiming active.
            result.update(delivery_fields('unknown', previous.get('startedAt'), checked_at=checked_at))
            return result
        if status not in ('active', 'ended'):
            return result
        start = iso_date(observation.get('start_date')) or previous.get('startedAt', '')
        end = iso_date(observation.get('end_date'))
        detected = ''
        if status == 'ended' and previous.get('deliveryStatus') == 'ended':
            end = end or previous.get('endedAt')
            detected = previous.get('endedDetectedAt')
        result['startedAt'] = start
        result.update(delivery_fields(status, start, end, checked_at, ended_detected_at=detected))
    return result


def merge_observation(previous, current):
    result = dict(current)
    result.update(merge_query_fields(previous, current))
    result['firstSeenAt'] = previous.get('firstSeenAt') or previous.get('collectedAt') or current.get('collectedAt')
    result['lastSeenAt'] = current.get('collectedAt')
    if not iso_date(result.get('startedAt')):
        result['startedAt'] = previous.get('startedAt', '')
    old_status, status = previous.get('deliveryStatus'), current.get('deliveryStatus', 'unknown')
    if status == 'unknown' and old_status in ('active', 'ended'):
        if old_status == 'ended' and previous.get('durationBasis') == 'detected' and not previous.get('endedAt'):
            # It was actually found again; absence is no longer evidence that
            # it remains ended. Do not claim active without the source label.
            result.update(delivery_fields('unknown', result.get('startedAt'), checked_at=current.get('statusCheckedAt')))
        else:
            for key in LIFECYCLE_FIELDS:
                result[key] = previous.get(key)
    elif status == 'ended' and old_status == 'ended' and not current.get('endedAt'):
        result.update(delivery_fields('ended', result.get('startedAt'), previous.get('endedAt'),
                                     current.get('statusCheckedAt'), ended_detected_at=previous.get('endedDetectedAt')))
    return result
