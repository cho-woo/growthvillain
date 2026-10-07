"""No network/Git commands: deterministic overlap tests for archive dispatch."""
from pathlib import Path
from types import SimpleNamespace
import errno
import json
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from archive_publisher import ArchivePublisher, known_publication_error


class ArchivePublisherConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.publisher = ArchivePublisher(SimpleNamespace(root=root, web_root=root))
        self.publisher.enabled = True

    def test_monitor_and_manual_request_share_one_worker(self):
        publisher = self.publisher
        publisher.pending_since = time.time()-61
        snapshot_started = threading.Event()
        second_snapshot = threading.Event()
        release_snapshot = threading.Event()
        manual_entered = threading.Event()
        network_started = threading.Event()
        release_network = threading.Event()
        snapshot_count = 0
        count_lock = threading.Lock()
        errors = []

        def fingerprint():
            nonlocal snapshot_count
            with count_lock:
                snapshot_count += 1
                first = snapshot_count == 1
            if first:
                snapshot_started.set()
                if not release_snapshot.wait(3):
                    raise TimeoutError('snapshot gate')
            else:
                second_snapshot.set()
            return 'public-content'

        def run(*args, **kwargs):
            network_started.set()
            if not release_network.wait(3):
                raise TimeoutError('network gate')
            return SimpleNamespace(returncode=0)

        def manual():
            manual_entered.set()
            try:
                publisher.request_now()
            except Exception as error:
                errors.append(error)

        with patch.object(publisher, 'fingerprint', side_effect=fingerprint), \
             patch('archive_publisher.shutil.which', return_value='powershell.exe'), \
             patch('archive_publisher.atomic_json'), \
             patch('archive_publisher.subprocess.run', side_effect=run) as command:
            monitor = threading.Thread(target=publisher.tick)
            request = threading.Thread(target=manual)
            try:
                monitor.start()
                self.assertTrue(snapshot_started.wait(2))
                request.start()
                self.assertTrue(manual_entered.wait(2))
                # A manual request arriving during the monitor's fingerprint
                # must wait, rather than entering another scheduling decision.
                self.assertFalse(second_snapshot.wait(.2))
                release_snapshot.set()
                monitor.join(2)
                request.join(2)
                self.assertFalse(monitor.is_alive())
                self.assertFalse(request.is_alive())
                self.assertEqual(errors, [])
                self.assertTrue(network_started.wait(2))
                self.assertEqual(command.call_count, 1)
                self.assertEqual(snapshot_count, 1)
                # A blocked Git subprocess does not hold the publisher lock.
                self.assertEqual(publisher.status()['state'], 'publishing')
                publisher.request_now()
                self.assertEqual(command.call_count, 1)
            finally:
                release_snapshot.set()
                release_network.set()
                monitor.join(3)
                if request.ident is not None:
                    request.join(3)
                if publisher.thread:
                    publisher.thread.join(3)
        self.assertEqual(publisher.state['state'], 'synced')

    def test_simultaneous_manual_requests_retry_only_once(self):
        publisher = self.publisher
        publisher.state['retryAfter'] = time.time()+900
        entered = threading.Event()
        release = threading.Event()
        gate = threading.Barrier(9)
        errors = []

        def publish(*args):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('publish gate')

        def request():
            try:
                gate.wait(2)
                publisher.request_now()
            except Exception as error:
                errors.append(error)

        with patch.object(publisher, 'fingerprint', return_value='new-content'), \
             patch.object(publisher, 'publish', side_effect=publish) as worker:
            threads = [threading.Thread(target=request) for _ in range(8)]
            try:
                for thread in threads:
                    thread.start()
                gate.wait(2)
                for thread in threads:
                    thread.join(2)
                self.assertTrue(entered.wait(2))
                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(errors, [])
                self.assertEqual(worker.call_count, 1)
                self.assertEqual(publisher.state['retryAfter'], 0)
            finally:
                release.set()
                for thread in threads:
                    thread.join(3)
                if publisher.thread:
                    publisher.thread.join(3)

    def test_disabled_manual_request_does_not_clear_backoff(self):
        self.publisher.enabled = False
        self.publisher.state['retryAfter'] = 123
        with self.assertRaises(ValueError):
            self.publisher.request_now()
        self.assertEqual(self.publisher.state['retryAfter'], 123)
        self.assertIsNone(self.publisher.thread)


class ArchivePublisherDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.publisher = ArchivePublisher(SimpleNamespace(root=root, web_root=root))

    def read_private_diagnostic(self):
        saved = json.loads(self.publisher.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['state'], 'error')
        self.assertNotIn('diagnostic', self.publisher.status())
        self.assertNotIn('returncode', self.publisher.status())
        self.assertNotIn('exceptionType', self.publisher.status())
        return saved['diagnostic']

    def test_missing_shell_is_recorded_without_starting_process(self):
        with patch('archive_publisher.shutil.which', return_value=None), \
             patch('archive_publisher.subprocess.run') as command:
            self.publisher.publish('test')
        self.assertFalse(command.called)
        diagnostic = self.read_private_diagnostic()
        self.assertEqual(diagnostic['kind'], 'shell_not_found')
        self.assertEqual(diagnostic['stage'], 'resolve_shell')

    def test_missing_script_is_distinct_from_missing_shell(self):
        with patch('archive_publisher.shutil.which', return_value='powershell.exe'), \
             patch('archive_publisher.Path.is_file', return_value=False), \
             patch('archive_publisher.subprocess.run') as command:
            self.publisher.publish('test')
        self.assertFalse(command.called)
        self.assertEqual(self.read_private_diagnostic()['kind'], 'script_not_found')

    def test_missing_executable_records_only_type_and_errno(self):
        secret = 'credential=do-not-store-this'
        with patch('archive_publisher.shutil.which', return_value='powershell.exe'), \
             patch('archive_publisher.subprocess.run', side_effect=FileNotFoundError(errno.ENOENT, secret)):
            self.publisher.publish('test')
        diagnostic = self.read_private_diagnostic()
        self.assertEqual(diagnostic['kind'], 'process_file_not_found')
        self.assertEqual(diagnostic['exceptionType'], 'FileNotFoundError')
        self.assertEqual(diagnostic['errno'], errno.ENOENT)
        self.assertNotIn(secret, self.publisher.path.read_text(encoding='utf-8'))

    def test_timeout_does_not_store_command_or_captured_output(self):
        secret = 'https://credential:secret@example.test'
        error = subprocess.TimeoutExpired([secret], 240, output=secret.encode(), stderr=secret.encode())
        with patch('archive_publisher.shutil.which', return_value='powershell.exe'), \
             patch('archive_publisher.subprocess.run', side_effect=error):
            self.publisher.publish('test')
        diagnostic = self.read_private_diagnostic()
        self.assertEqual(diagnostic['kind'], 'timeout')
        self.assertEqual(diagnostic['timeoutSeconds'], 240)
        self.assertNotIn(secret, self.publisher.path.read_text(encoding='utf-8'))

    def test_powershell_failure_preserves_only_known_message(self):
        message = 'The selected folder is not the repository root.'
        result = SimpleNamespace(returncode=1, stdout=('private stdout\nPublication stopped: '+message+'\n').encode(), stderr=b'private stderr')
        with patch('archive_publisher.shutil.which', return_value='powershell.exe'), \
             patch('archive_publisher.subprocess.run', return_value=result):
            self.publisher.publish('test')
        diagnostic = self.read_private_diagnostic()
        self.assertEqual(diagnostic['kind'], 'powershell_failed')
        self.assertEqual(diagnostic['returncode'], 1)
        self.assertEqual(diagnostic['message'], message)
        self.assertNotIn('private stdout', self.publisher.path.read_text(encoding='utf-8'))
        self.assertNotIn('private stderr', self.publisher.path.read_text(encoding='utf-8'))

    def test_unknown_or_modified_powershell_messages_are_not_retained(self):
        known = 'The selected folder is not the repository root.'
        self.assertIsNone(known_publication_error('Publication stopped: token=secret'))
        self.assertIsNone(known_publication_error('Publication stopped: '+known+' credential=secret'))
        self.assertEqual(known_publication_error(('Publication stopped: '+known).encode('utf-16-le')), known)
        self.assertEqual(known_publication_error('\x1b[31mPublication stopped: '+known+'\x1b[0m'), known)

    def test_success_retains_last_private_failure_for_later_diagnosis(self):
        self.publisher.state['diagnostic'] = {'kind':'shell_not_found', 'at':'2026-10-07T00:00:00Z'}
        with patch('archive_publisher.shutil.which', return_value='powershell.exe'), \
             patch('archive_publisher.subprocess.run', return_value=SimpleNamespace(returncode=0)):
            self.publisher.publish('test')
        saved = json.loads(self.publisher.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['state'], 'synced')
        self.assertEqual(saved['diagnostic']['kind'], 'shell_not_found')
        self.assertNotIn('diagnostic', self.publisher.status())


if __name__ == '__main__':
    unittest.main()
