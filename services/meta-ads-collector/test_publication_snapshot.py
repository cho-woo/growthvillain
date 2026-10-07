import unittest
from server import publication_snapshot


class PublicationSnapshotTests(unittest.TestCase):
    def test_static_snapshot_preserves_previous_completed_transfer(self):
        status = {'state': 'publishing', 'lastSuccessAt': '2026-10-07T03:00:00Z',
                  'enabled': True, 'diagnostic': {'private': 'not public'}}
        result = publication_snapshot(status)
        self.assertEqual(result['state'], 'synced')
        self.assertEqual(result['lastSuccessAt'], status['lastSuccessAt'])
        self.assertNotIn('diagnostic', result)
        self.assertEqual(status['state'], 'publishing')

    def test_first_transfer_is_pending_until_success_exists(self):
        result = publication_snapshot({'state': 'publishing', 'lastSuccessAt': None})
        self.assertEqual(result['state'], 'pending')
        self.assertIsNone(result['lastSuccessAt'])

    def test_failure_is_not_hidden(self):
        result = publication_snapshot({'state': 'error', 'error': 'transfer failed'})
        self.assertEqual(result['state'], 'error')
        self.assertEqual(result['error'], 'transfer failed')


if __name__ == '__main__':
    unittest.main()
