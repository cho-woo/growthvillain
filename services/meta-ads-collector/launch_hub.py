"""Start the user's local automation hub; safe to invoke again at Windows logon."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

from automation_bridge import file_lock, hub_root, read_json, write_json

SERVICE = Path(__file__).resolve().parent


def server_ready():
    try:
        with urlopen('http://127.0.0.1:4177/api/meta-ads/status', timeout=2) as response:
            return json.load(response).get('mode') == 'local'
    except Exception:
        return False


def main():
    root = hub_root()
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root/'launcher.lock') as locked:
        if not locked:
            return
        local = Path(os.environ['LOCALAPPDATA'])
        runtime = local/'JoWooHyung/MetaAds/runtime/Scripts/python.exe'
        widget_python = local/'Programs/Python/Python312/pythonw.exe'
        if not server_ready():
            # The service reads the configured D: path and refuses a fallback.
            with (root/'server.log').open('a', encoding='utf-8') as log:
                subprocess.Popen([str(runtime), '-X','utf8',str(SERVICE/'server.py'),
                                  '--web-root',str(SERVICE.parent.parent),'--port','4177'],
                                 cwd=SERVICE, stdout=log, stderr=log,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        # The widget has its own singleton lock. Scheduled health checks do not
        # keep reopening a widget that the user deliberately closed.
        if '--widget' in sys.argv:
            with (root/'widget.log').open('a', encoding='utf-8') as log:
                subprocess.Popen([str(widget_python),str(SERVICE/'desktop_status.py')], cwd=SERVICE,
                                 stdout=log, stderr=log)


if __name__ == '__main__':
    main()
