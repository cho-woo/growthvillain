"""No network/Git commands: deterministic overlap tests for archive dispatch."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from archive_publisher import ArchivePublisher


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


if __name__ == '__main__':
    unittest.main()
