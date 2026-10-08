import json
from pathlib import Path
import tempfile
import unittest

from completed_cards import read_completed_jsonl


class CompletedCardsTests(unittest.TestCase):
    def test_only_lf_committed_rows_survive_interrupted_utf8_tail_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cards.jsonl'
            payload = b'{"library_id":"123456"}\n' + '{"name":"광고'.encode('utf-8')[:-1]
            path.write_bytes(payload)
            result = read_completed_jsonl(path)
            self.assertEqual(result['rows'], [{'library_id': '123456'}])
            self.assertGreater(result['ignoredTrailingBytes'], 0)
            self.assertEqual(path.read_bytes(), payload)

    def test_valid_json_without_newline_is_not_committed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cards.jsonl'
            path.write_bytes(b'{"library_id":"123456"}')
            self.assertEqual(read_completed_jsonl(path)['rows'], [])

    def test_invalid_complete_row_is_rejected_without_skipping(self):
        for bad_row in (b'{bad}\n', b'[]\n', b'\xff\n'):
            with self.subTest(bad_row=bad_row), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'cards.jsonl'
                path.write_bytes(b'{"library_id":"123456"}\n' + bad_row)
                with self.assertRaises(ValueError):
                    read_completed_jsonl(path)

    def test_bounds_and_bom_crlf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cards.jsonl'
            path.write_bytes(b'\xef\xbb\xbf{}\r\n\r\n{}\n')
            self.assertEqual(read_completed_jsonl(path)['rows'], [{}, {}])
            with self.assertRaises(ValueError):
                read_completed_jsonl(path, max_rows=1)
            with self.assertRaises(ValueError):
                read_completed_jsonl(path, max_bytes=3)


if __name__ == '__main__':
    unittest.main()
