# migration_tool.py
import csv
import json
import os
import sys

# Discovery: Use the project's standard checksum algorithm from v1/utils.py
# We add the v1 path to sys.path to import it cleanly.
sys.path.append(os.path.join(os.path.dirname(__file__), 'ledger', 'v1'))
from utils import calculate_checksum

def migrate_ledger(source_csv, target_json):
    results = []
    error_log = "migration_errors.log"
    
    with open(source_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # 1. Format Mapping & Validation
                record_id = row['id']
                amount = float(row['amount'])
                timestamp = row['timestamp']
                
                # 2. Integrity Verification (Discovery Replicated)
                checksum = calculate_checksum(record_id, amount)
                
                results.append({
                    "id": record_id,
                    "amount": amount,
                    "timestamp": timestamp,
                    "checksum": checksum
                })
            except (ValueError, TypeError) as e:
                # 4. Error Handling
                with open(error_log, 'a') as log:
                    log.write(f"Failed to migrate record {row.get('id')}: {e}\n")
                continue
                
    # 3. Output
    with open(target_json, 'w') as f:
        json.dump(results, f, indent=4)
