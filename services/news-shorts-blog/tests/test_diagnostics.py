from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from news_agent.cli import DEFAULTS, instance_lock, main, read_config
from news_agent.diagnostics import diagnose
from news_agent.errors import ConfigurationError


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root/'config.json'

    def tearDown(self):
        self.temp.cleanup()

    def config(self, **changes):
        self.path.write_text(json.dumps({**DEFAULTS, **changes}), encoding='utf-8')

    def invoke(self, command='login'):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = main(['--config', str(self.path), command])
        return code, output.getvalue()

    def test_login_missing_config_explains_setup_without_opening_browser(self):
        with patch('news_agent.cli.make_publisher') as publisher:
            code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('[CONFIG_MISSING]', output)
        self.assertIn('Setup.cmd', output)
        self.assertIn(str(self.path), output)
        publisher.assert_not_called()

    def test_invalid_json_reports_location_without_secret_contents(self):
        self.path.write_text('{"password":"DO_NOT_PRINT_TEST_SECRET",\n bad}', encoding='utf-8')
        code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('[CONFIG_JSON]', output)
        self.assertIn('2행', output)
        self.assertNotIn('DO_NOT_PRINT_TEST_SECRET', output)

    def test_bad_blog_id_reports_field_not_value(self):
        self.config(blog_id='DO_NOT_PRINT_TEST_SECRET!')
        code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('[CONFIG_VALUE]', output)
        self.assertIn('blog_id', output)
        self.assertNotIn('DO_NOT_PRINT_TEST_SECRET', output)

    def test_unreadable_config_and_encoding_are_distinct(self):
        self.config()
        with patch.object(Path, 'read_text', side_effect=PermissionError('DO_NOT_PRINT_TEST_SECRET')):
            with self.assertRaises(ConfigurationError) as raised:
                read_config(self.path)
        self.assertEqual(raised.exception.code, 'CONFIG_ACCESS')
        self.assertNotIn('DO_NOT_PRINT_TEST_SECRET', str(raised.exception))
        self.path.write_bytes(b'\xff\xfeinvalid')
        code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('[CONFIG_ENCODING]', output)

    def test_login_duplicate_process_error_is_explicit(self):
        self.config()
        with instance_lock(self.root/'agent.lock'), patch('news_agent.cli.make_publisher') as publisher:
            code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn('[ALREADY_RUNNING]', output)
        self.assertIn('Start.cmd', output)
        publisher.assert_not_called()

    def test_diagnose_checks_format_without_printing_credentials_or_logging_in(self):
        credentials = self.root/'pw.txt'
        credentials.write_text('id: TEST_PRIVATE_USER\npw: TEST_PRIVATE_PASSWORD', encoding='utf-8')
        self.config(credentials_file=str(credentials))
        before = self.path.read_bytes()
        with patch('news_agent.diagnostics.browser_path', return_value=Path('/fake/browser')), \
                patch('news_agent.diagnostics.importlib.util.find_spec', return_value=object()), \
                patch('news_agent.naver.NaverPublisher') as publisher:
            code, output = self.invoke('diagnose')
        self.assertEqual(code, 0)
        self.assertIn('[CREDENTIALS_OK]', output)
        self.assertIn('[CONFIG_OK]', output)
        self.assertIn('[LOCK_OK]', output)
        self.assertNotIn('TEST_PRIVATE_USER', output)
        self.assertNotIn('TEST_PRIVATE_PASSWORD', output)
        self.assertEqual(self.path.read_bytes(), before)
        publisher.assert_not_called()

    def test_diagnose_reports_missing_browser_and_dependencies(self):
        self.config(credentials_file=None)
        with patch('news_agent.diagnostics.browser_path', return_value=None), \
                patch('news_agent.diagnostics.importlib.util.find_spec', return_value=None):
            code, output = self.invoke('diagnose')
        self.assertEqual(code, 2)
        self.assertIn('[MODULE_MISSING]', output)
        self.assertIn('[BROWSER_MISSING]', output)

    def test_diagnose_detects_existing_lock_without_releasing_it(self):
        self.config(credentials_file=None)
        with instance_lock(self.root/'agent.lock'), \
                patch('news_agent.diagnostics.browser_path', return_value=Path('/fake/browser')), \
                patch('news_agent.diagnostics.importlib.util.find_spec', return_value=object()):
            code, output = self.invoke('diagnose')
            with self.assertRaises(ValueError):
                with instance_lock(self.root/'agent.lock'):
                    pass
        self.assertEqual(code, 2)
        self.assertIn('[ALREADY_RUNNING]', output)

    def test_diagnose_missing_config_is_reported_without_creating_it(self):
        with patch('news_agent.diagnostics.importlib.util.find_spec', return_value=object()):
            code, output = self.invoke('diagnose')
        self.assertEqual(code, 2)
        self.assertIn('[CONFIG_MISSING]', output)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
