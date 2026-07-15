"""Fail-closed optional host hook for confirming Signal recording."""

from __future__ import annotations

import argparse
import json

from mighty_mouse_mcp.server import run_recording_audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exit nonzero unless Mighty Mouse recorded a Signal after a host task began."
    )
    parser.add_argument("workspace", help="Workspace whose .mighty-mouse state should be checked")
    parser.add_argument("--receipt-hash", required=True, help="Receipt hash returned by verify_and_record")
    parser.add_argument("--after", required=True, help="ISO-8601 UTC task start time")
    args = parser.parse_args()
    result = run_recording_audit(args.workspace, args.receipt_hash, args.after)
    print(json.dumps(result, sort_keys=True))
    if not result["recorded"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
