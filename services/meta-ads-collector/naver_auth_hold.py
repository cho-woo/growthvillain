"""Local authentication holds; never connect to Naver or retry verification."""
import json


def publication_auth_hold(root, blog_id=None):
    """Return a hold state; ``ready`` only removes this local hold, not publish gates.

    An absent file preserves older installations. Once login setup has written
    a status, only an explicit ready state for that target releases its hold.
    """
    try:
        status = json.loads((root/'state/naver-login-status.json').read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError):
        return 'needs_login'
    if not isinstance(status, dict):
        return 'needs_login'
    if blog_id and status.get('blogId') != blog_id:
        return 'needs_login'
    state = status.get('state')
    if state == 'ready':
        return None
    return state if isinstance(state, str) and state else 'needs_login'


def auth_hold_message(state):
    if state == 'verification_limited':
        return '보호조치 인증 횟수 초과 · 발행 보류'
    return '로그인 확인 대기 · 발행 보류'
