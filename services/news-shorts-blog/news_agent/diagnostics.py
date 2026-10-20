"""Local setup diagnostics; never log credentials or visit external websites."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .errors import AgentAlreadyRunning, ConfigurationError
from . import __version__


def browser_path(channel):
    if channel == 'chromium':
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                path = Path(playwright.chromium.executable_path)
                return path if path.is_file() else None
        except Exception:
            return None
    if os.name == 'nt':
        relative = ('Google/Chrome/Application/chrome.exe' if channel == 'chrome'
                    else 'Microsoft/Edge/Application/msedge.exe')
        for variable in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
            if os.environ.get(variable):
                path = Path(os.environ[variable])/relative
                if path.is_file():
                    return path
        return None
    executable = shutil.which('google-chrome' if channel == 'chrome' else 'microsoft-edge')
    return Path(executable) if executable else None


def diagnose(path):
    from .cli import instance_lock, read_config
    from .naver import read_credentials

    path = Path(path)
    failed = False
    print('로컬 진단 · 계정 값 출력 없음 · 로그인/게시 없음')
    print(f'뉴스 에이전트 버전: {__version__}')
    print(f'Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
    print(f'설정 파일 위치: {path}')
    print(f'실행 프로그램 위치: {Path(__file__).resolve().parent.parent}')
    if sys.version_info < (3, 11):
        print('[PYTHON_VERSION] Python 3.11 이상을 설치한 뒤 Setup.cmd를 실행하세요.')
        failed = True

    try:
        config = read_config(path)
        print('[CONFIG_OK] 설정 파일과 필드 형식이 정상입니다.')
    except ConfigurationError as error:
        print(f'[{error.code}] {error}')
        config = None
        failed = True

    for module in ('playwright', 'requests', 'yt_dlp'):
        try:
            present = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            present = False
        if present:
            print(f'[MODULE_OK] {module}')
        else:
            print(f'[MODULE_MISSING] {module}: Setup.cmd를 다시 실행하세요.')
            failed = True

    if path.parent.is_dir():
        try:
            with tempfile.TemporaryFile(dir=path.parent) as handle:
                handle.write(b'check')
                handle.flush()
            print('[DATA_WRITE_OK] 개인 데이터 폴더에 쓸 수 있습니다.')
        except OSError:
            print('[DATA_ACCESS] 개인 데이터 폴더에 쓸 수 없습니다. 접근 권한과 저장 공간을 확인하세요.')
            failed = True
        try:
            with instance_lock(path.parent/'agent.lock'):
                print('[LOCK_OK] 다른 에이전트 실행이 감지되지 않았습니다.')
        except AgentAlreadyRunning:
            print('[ALREADY_RUNNING] 기존 Start.cmd·Login.cmd·Post-Once.cmd 실행을 종료한 뒤 다시 시도하세요.')
            failed = True
        except OSError:
            print('[LOCK_ACCESS] 실행 잠금 파일에 접근할 수 없습니다. 폴더 권한을 확인하세요.')
            failed = True
    else:
        print('[DATA_MISSING] 개인 설정 폴더가 없습니다. Setup.cmd를 실행하세요.')
        failed = True

    if config is not None:
        if browser_path(config['browser_channel']):
            print('[BROWSER_OK] 설정한 브라우저 실행 파일이 있습니다. 실제 실행 성공은 Login.cmd에서 확인합니다.')
        else:
            print('[BROWSER_MISSING] 설정한 브라우저를 찾지 못했습니다. Chrome 설치 또는 Install.ps1 -BrowserChannel chromium을 실행하세요.')
            failed = True
        credentials = config.get('credentials_file')
        if credentials:
            try:
                read_credentials(Path(credentials))
                print('[CREDENTIALS_OK] 로컬 계정 파일을 읽을 수 있고 형식이 정상입니다. 실제 로그인 여부는 아직 확인하지 않았습니다.')
            except (ValueError, OSError):
                print('[CREDENTIALS_MANUAL] 로컬 계정 파일을 읽거나 해석하지 못했습니다. Login.cmd에서 직접 로그인할 수 있습니다.')
        else:
            print('[CREDENTIALS_MANUAL] 브라우저에서 직접 로그인하도록 설정되어 있습니다.')

    print('진단 종료 · 문제가 표시되면 해당 [코드]와 설명을 알려주세요.')
    return 2 if failed else 0
