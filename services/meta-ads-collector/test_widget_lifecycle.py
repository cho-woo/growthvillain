import queue
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from desktop_status import opacity_percent, WidgetPreferences, StatusWindow


class WidgetLifecycleTests(unittest.TestCase):
    def window(self, registered=True):
        window = StatusWindow.__new__(StatusWindow)
        window.root = Mock()
        window.tk = SimpleNamespace(TclError=RuntimeError)
        window.client = Mock()
        window.closed = False
        window.tray_hidden = False
        window.tray = Mock()
        window.tray.registered = registered
        window.tray.ensure_registered.return_value = registered
        window.tray_events = queue.Queue()
        window.next_tray_retry = 0
        window.notice = Mock()
        window.pool = Mock()
        window.opacity_save_job = None
        window.tick_job = 'poll-job'
        window.tray_job = 'tray-job'
        window.opacity = 75
        window.opacity_label = Mock()
        window.preferences = Mock()
        return window

    def test_opacity_is_clamped_and_invalid_values_use_readable_default(self):
        for value in (None, True, 'bad', float('nan'), float('inf')):
            self.assertEqual(opacity_percent(value), 100)
        self.assertEqual(opacity_percent(10), 30)
        self.assertEqual(opacity_percent(130), 100)
        self.assertEqual(opacity_percent('65.0'), 65)

    def test_preferences_are_only_local_opacity_and_survive_reload(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'private/widget-preferences.json'
            prefs = WidgetPreferences(path)
            self.assertEqual(prefs.opacity(), 100)
            prefs.save_opacity(57)
            self.assertEqual(WidgetPreferences(path).opacity(), 57)
            self.assertEqual(set(__import__('json').loads(path.read_text())), {'opacity'})
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(prefs.opacity(), 100)

    def test_x_hides_window_without_stopping_polling_or_automations(self):
        window = self.window()
        window.hide_to_tray()
        window.root.withdraw.assert_called_once()
        self.assertTrue(window.tray_hidden)
        self.assertFalse(window.closed)
        window.pool.shutdown.assert_not_called()
        window.client.switch.assert_not_called()

    def test_failed_tray_keeps_window_reachable_from_taskbar(self):
        window = self.window(False)
        window.hide_to_tray()
        window.root.withdraw.assert_not_called()
        window.root.iconify.assert_called_once()
        self.assertFalse(window.tray_hidden)

    def test_tray_restore_and_explorer_failure_use_tk_thread_queue(self):
        window = self.window()
        window.tray_hidden = True
        window.tray_events.put('unavailable')
        window.process_tray_events()
        window.root.deiconify.assert_called_once()
        self.assertFalse(window.tray_hidden)
        window.tray_events.put('open')
        window.process_tray_events()
        self.assertEqual(window.root.deiconify.call_count, 2)

    def test_exit_cleans_timers_tray_pool_once_without_control_request(self):
        window = self.window()
        window.opacity_save_job = 'opacity-job'
        window.tray_events.put('exit')
        window.process_tray_events()
        self.assertTrue(window.closed)
        window.root.after_cancel.assert_any_call('opacity-job')
        window.root.after_cancel.assert_any_call('poll-job')
        window.root.after_cancel.assert_any_call('tray-job')
        window.preferences.save_opacity.assert_called_once_with(75)
        window.tray.close.assert_called_once()
        window.root.destroy.assert_called_once()
        window.client.switch.assert_not_called()
        window.close()
        window.root.destroy.assert_called_once()

    def test_opacity_updates_alpha_then_debounces_disk_write(self):
        window = self.window()
        window.opacity_save_job = 'previous-save'
        window.change_opacity('45')
        window.root.attributes.assert_called_once_with('-alpha', .45)
        window.root.after_cancel.assert_called_once_with('previous-save')
        window.root.after.assert_called_once_with(300, window.persist_opacity)
        window.preferences.save_opacity.assert_not_called()
        window.persist_opacity()
        window.preferences.save_opacity.assert_called_once_with(45)


if __name__ == '__main__':
    unittest.main()
