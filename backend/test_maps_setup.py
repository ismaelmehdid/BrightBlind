import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import setup_maps as setup

class MapsSetupTests(unittest.TestCase):
    def test_no_billing_stops_before_enabling_or_creating(self):
        replies = [[{'account': setup.ACCOUNT}], [{'projectId': 'event-test', 'name': setup.PROJECT_NAME}], {'billingEnabled': False}]
        with patch.object(setup, 'gcloud', side_effect=replies) as cli, patch('sys.argv', ['setup_maps.py']):
            with self.assertRaisesRegex(RuntimeError, 'no active billing'): setup.main()
            self.assertEqual(cli.call_count, 3)

    def test_wrong_account_stops_before_project_access(self):
        with patch.object(setup, 'gcloud', return_value=[{'account': 'someone-else@example.test'}]) as cli, patch('sys.argv', ['setup_maps.py']):
            with self.assertRaisesRegex(RuntimeError, 'Sign in'): setup.main()
            self.assertEqual(cli.call_count, 1)

    def test_private_save_preserves_other_provider_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'.env'
            path.write_text('GEMINI_API_KEY=example-existing\nGOOGLE_MAPS_API_KEY=old\n')
            setup.save_key(path, 'test-new-key', 'event-test')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn('GEMINI_API_KEY=example-existing', path.read_text())
            self.assertEqual(path.read_text().count('GOOGLE_MAPS_API_KEY='), 1)
            self.assertFalse(path.with_name('.env.maps-tmp').exists())

if __name__ == '__main__': unittest.main()
