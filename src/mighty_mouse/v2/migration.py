"""Fail-closed, dry-run-first migration receipts for immutable v1 artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path


@dataclass(frozen=True)
class MigrationReport:
    source_digest: str
    proposed: tuple[str, ...]
    skipped: tuple[str, ...]
    applied: bool


class V1Migrator:
    """Imports only explicitly recognized v1 records and never rewrites source."""

    receipt_name = "v2-migration-receipts.json"

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)

    def migrate(self, source: str | Path, *, apply: bool = False) -> MigrationReport:
        source = Path(source)
        raw = source.read_bytes()
        digest = "sha256:" + sha256(raw).hexdigest()
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("v1 migration requires valid JSON input") from error
        records = document.get("records") if isinstance(document, dict) else None
        if not isinstance(records, list):
            raise ValueError("v1 migration requires a records array")
        proposed, skipped = [], []
        for item in records:
            if not isinstance(item, dict) or item.get("kind") not in {"benchmark_result", "verification_result"} or not isinstance(item.get("id"), str):
                skipped.append(str(item.get("id", "unknown")) if isinstance(item, dict) else "unknown")
            else:
                proposed.append(item["id"])
        report = MigrationReport(digest, tuple(proposed), tuple(skipped), apply)
        if not apply:
            return report
        self.state_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = self.state_dir / self.receipt_name
        receipts = json.loads(receipt_path.read_text()) if receipt_path.exists() else []
        if not any(entry["source_digest"] == digest for entry in receipts):
            receipts.append({"source_digest": digest, "proposed": proposed, "skipped": skipped})
            receipt_path.write_text(json.dumps(receipts, sort_keys=True, separators=(",", ":")))
        if source.read_bytes() != raw:
            raise RuntimeError("v1 source changed during migration; no v2 state was derived")
        return report
