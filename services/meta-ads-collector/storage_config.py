"""Resolve personal storage without silently falling back from an external drive."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


class StorageUnavailable(OSError):
    pass


def assert_storage_available(data_dir):
    path = Path(data_dir)
    if not path.is_dir():
        raise StorageUnavailable(
            f'광고 저장 폴더에 접근할 수 없습니다: {path}\n'
            '외장 드라이브의 연결과 드라이브 문자를 확인하세요. 다른 경로에 저장하지 않습니다.'
        )


def resolve_data_dir(explicit=None, *, environ=None, settings_file=None):
    """CLI > environment > local settings > first-run local default; never create files."""
    env = os.environ if environ is None else environ
    local_root = Path(env.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'JoWooHyung/MetaAds'
    config = Path(settings_file) if settings_file is not None else local_root / 'settings.json'
    require_existing = False
    if explicit is not None:
        value = explicit
    elif 'CRAWLER_DATA_DIR' in env:
        value = env['CRAWLER_DATA_DIR']
    elif config.exists():
        try:
            data = json.loads(config.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f'저장 경로 설정 파일을 읽을 수 없습니다: {config}. 설정을 확인하세요.') from error
        if not isinstance(data, dict) or 'dataDir' not in data:
            raise ValueError(f'저장 경로 설정 파일에 dataDir 항목이 필요합니다: {config}')
        value = data['dataDir']
        # A configured archive already exists; its disappearance is an error,
        # not an invitation to create an empty archive or return to drive C.
        require_existing = True
    else:
        value = str(local_root)
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError('광고 저장 경로는 비어 있지 않은 절대 경로여야 합니다.')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('광고 저장 경로는 드라이브 문자를 포함한 절대 경로여야 합니다.')
    if not Path(path.anchor).is_dir():
        raise StorageUnavailable('광고 저장 드라이브에 접근할 수 없습니다. 외장 드라이브를 연결하세요.')
    path = path.resolve()
    if path.exists() and not path.is_dir():
        raise ValueError('광고 저장 경로가 폴더가 아닙니다.')
    if require_existing:
        assert_storage_available(path)
    return path


def main():
    parser = argparse.ArgumentParser(description='개인 광고 수집기의 저장 경로 확인')
    parser.add_argument('--data-dir')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        path = resolve_data_dir(args.data_dir)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'dataDir': str(path)}, ensure_ascii=True) if args.json else path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
