import unittest
import json
import os
import sys

# Add path for discovery simulation
sys.path.append(os.path.join(os.path.dirname(__file__), 'ledger', 'v1'))
from utils import calculate_checksum

from migration_tool import migrate_ledger

class TestMigration(unittest.TestCase):
    def test_migration_accuracy(self):
        csv_path = os.path.join(os.path.dirname(__file__), 'ledger', 'v1', 'ledger.csv')
        json_path = os.path.join(os.path.dirname(__file__), 'ledger.json')
        
        migrate_ledger(csv_path, json_path)
        
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        # tx_001 check
        tx1 = next(r for r in data if r['id'] == 'tx_001')
        self.assertEqual(tx1['amount'], 100.50)
        expected_cs = calculate_checksum('tx_001', 100.50)
        self.assertEqual(tx1['checksum'], expected_cs, "Checksum mismatch for tx_001!")
        
        # tx_002 check
        tx2 = next(r for r in data if r['id'] == 'tx_002')
        self.assertEqual(tx2['amount'], 200.0)
        
        # Verify invalid tx_003 was skipped
        ids = [r['id'] for r in data]
        self.assertNotIn('tx_003', ids, "Invalid record tx_003 should have been skipped.")

if __name__ == "__main__":
    unittest.main()
