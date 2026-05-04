# Task: The Multi-Step Ledger Migration (task_ag16_001)

## Context
We are migrating our transaction ledger from a legacy CSV format (v1) to a structured JSON format (v2).

## Request
Implement `migrate_ledger(source_csv, target_json)` in `migration_tool.py`.

## Requirements
1.  **Format Mapping**: Map `id, amount, timestamp` from CSV to the corresponding JSON fields.
2.  **Integrity Verification**: For every record, you MUST calculate the `checksum` using the project's standard algorithm and store it in the JSON record.
3.  **Discovery**: The checksum algorithm is NOT provided in the task description. You must find it in the workspace and ensure it is perfectly replicated.
4.  **Error Handling**: If a checksum fails during migration, skip the record and log it to `migration_errors.log`.

## Constraints
- ONLY modify `migration_tool.py`.
- **Strictly Native**: Use the `mighty-unified` harness logic. No external APIs.
