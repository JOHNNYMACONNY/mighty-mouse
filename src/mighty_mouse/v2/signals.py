"""Privacy-safe collection, retention, and history for routine v2 Signals."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory, _to_json_value


class SignalLifecycle:
    """Public collection/history boundary; receipt files are immutable once written."""

    receipt_directory = "v2-signal-receipts"
    aggregate_directory = "v2-signal-aggregates"
    control_filename = "v2-signal-controls.jsonl"
    schema_version = 1
    detailed_retention_days = 30

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.receipt_dir = self.state_dir / self.receipt_directory
        self.aggregate_dir = self.state_dir / self.aggregate_directory
        self.control_path = self.state_dir / self.control_filename

    def collect(self, signal: Signal, *, now: datetime | None = None) -> str | None:
        """Persist one validated Signal receipt unless collection is paused."""
        if self.collection_paused:
            return None
        self.compact(now=now)
        document = {"schema_version": self.schema_version, "recorded_at": self._timestamp(now), "signal": _to_json_value(signal)}
        document["receipt_hash"] = self._hash(document)
        self._write_immutable(self.receipt_dir / f"{document['receipt_hash']}.json", document)
        return document["receipt_hash"]

    def pause(self) -> None:
        self._append_control("paused")

    def resume(self) -> None:
        self._append_control("resumed")

    @property
    def collection_paused(self) -> bool:
        return any(control["action"] == "paused" for control in self._documents(self.control_path)) and not any(
            control["action"] == "resumed" for control in self._documents(self.control_path)[
                self._last_pause_index() + 1:
            ]
        )

    def compact(self, *, now: datetime | None = None) -> int:
        """Replace expired detailed receipt files with immutable durable aggregates."""
        cutoff = self._now(now) - timedelta(days=self.detailed_retention_days)
        expired = [receipt for receipt in self._receipts() if datetime.fromisoformat(receipt["recorded_at"]) <= cutoff]
        for aggregate in self._aggregate(expired):
            document = {"schema_version": self.schema_version, "aggregate": aggregate}
            document["aggregate_hash"] = self._hash(document)
            self._write_immutable(self.aggregate_dir / f"{document['aggregate_hash']}.json", document)
        for receipt in expired:
            (self.receipt_dir / f"{receipt['receipt_hash']}.json").unlink()
        return len(expired)

    def purge(self, *, scope: Scope | None = None) -> int:
        """Remove only eligible Signal files; unrelated immutable v2 state is untouched."""
        receipts = self._receipts()
        aggregates = self._aggregates()
        eligible_receipts = [receipt for receipt in receipts if scope is None or self._scope(receipt["signal"]) == scope]
        eligible_aggregates = [aggregate for aggregate in aggregates if scope is None or self._aggregate_matches_scope(aggregate, scope)]
        for receipt in eligible_receipts:
            (self.receipt_dir / f"{receipt['receipt_hash']}.json").unlink()
        for aggregate in eligible_aggregates:
            (self.aggregate_dir / f"{aggregate['aggregate_hash']}.json").unlink()
        self._append_control("purged")
        return len(eligible_receipts) + sum(aggregate["aggregate"]["count"] for aggregate in eligible_aggregates)

    def history(
        self,
        *,
        scope: Scope | None = None,
        model_digest: str | None = None,
        execution_profile_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return safe aggregate facts only, never individual Signal fields or identifiers."""
        receipts = [
            receipt for receipt in self._receipts()
            if (scope is None or self._scope(receipt["signal"]) == scope)
            and (model_digest is None or receipt["signal"]["model_digest"] == model_digest)
            and (execution_profile_id is None or receipt["signal"]["execution_profile_id"] == execution_profile_id)
        ]
        aggregates = [
            aggregate["aggregate"] for aggregate in self._aggregates()
            if (scope is None or self._aggregate_matches_scope(aggregate, scope))
            and (model_digest is None or aggregate["aggregate"].get("model_digest") == model_digest)
            and (execution_profile_id is None or aggregate["aggregate"].get("execution_profile_id") == execution_profile_id)
        ]
        return {"collection_paused": self.collection_paused, "receipt_count": len(receipts), "aggregates": self._combine_aggregates([*aggregates, *self._aggregate(receipts)])}

    def _receipts(self) -> list[dict[str, Any]]:
        receipts = self._documents(self.receipt_dir)
        for receipt in receipts:
            if receipt.get("schema_version") != self.schema_version or receipt.get("receipt_hash") != self._hash(receipt, "receipt_hash"):
                raise ValueError("invalid Signal receipt")
            self._signal(receipt["signal"])
        return receipts

    def _aggregates(self) -> list[dict[str, Any]]:
        aggregates = self._documents(self.aggregate_dir)
        for document in aggregates:
            if document.get("schema_version") != self.schema_version or document.get("aggregate_hash") != self._hash(document, "aggregate_hash"):
                raise ValueError("invalid Signal aggregate")
        return aggregates

    def _aggregate(self, receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
        for receipt in receipts:
            signal = self._signal(receipt["signal"])
            dimensions = self._dimensions(signal)
            bucket = buckets.setdefault(dimensions, dict(zip(self._dimension_names(), dimensions)) | {"count": 0, "total_duration_ms": 0, "total_retry_count": 0})
            bucket["count"] += 1
            bucket["total_duration_ms"] += signal.duration_ms
            bucket["total_retry_count"] += signal.retry_count
        return list(buckets.values())

    def _combine_aggregates(self, aggregates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
        for aggregate in aggregates:
            dimensions = tuple(aggregate[name] for name in self._dimension_names())
            bucket = buckets.setdefault(dimensions, {name: aggregate[name] for name in self._dimension_names()} | {"count": 0, "total_duration_ms": 0, "total_retry_count": 0})
            for metric in ("count", "total_duration_ms", "total_retry_count"):
                bucket[metric] += aggregate[metric]
        return [buckets[key] for key in sorted(buckets, key=str)]

    @staticmethod
    def _dimension_names() -> tuple[str, ...]:
        return ("repository", "mode", "task_category", "model_class", "model_digest", "execution_profile_id", "outcome", "verifier_category", "verifier_result", "rating")

    @staticmethod
    def _dimensions(signal: Signal) -> tuple[Any, ...]:
        return (signal.scope.repository, signal.scope.mode.value, signal.scope.task_category.value, signal.scope.model_class, signal.model_digest, signal.execution_profile_id, signal.outcome, signal.verifier_category, signal.verifier_result, signal.rating)

    @staticmethod
    def _scope(value: dict[str, Any]) -> Scope:
        return Scope(Mode(value["scope"]["mode"]), value["scope"]["repository"], TaskCategory(value["scope"]["task_category"]), value["scope"]["model_class"])

    @classmethod
    def _signal(cls, value: dict[str, Any]) -> Signal:
        return Signal(value["signal_id"], cls._scope(value), value["model_digest"], value["execution_profile_id"], value["outcome"], value["duration_ms"], value["retry_count"], value["verifier_category"], value.get("verifier_result", "not_run"), tuple(tuple(item) for item in value.get("environment_metadata", ())), value.get("rating"))

    @staticmethod
    def _aggregate_matches_scope(document: dict[str, Any], scope: Scope) -> bool:
        aggregate = document["aggregate"] if "aggregate" in document else document
        return (aggregate["repository"], aggregate["mode"], aggregate["task_category"], aggregate["model_class"]) == (scope.repository, scope.mode.value, scope.task_category.value, scope.model_class)

    def _last_pause_index(self) -> int:
        controls = self._documents(self.control_path)
        return max((index for index, control in enumerate(controls) if control["action"] == "paused"), default=-1)

    def _append_control(self, action: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.control_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"schema_version": self.schema_version, "recorded_at": self._timestamp(None), "action": action}, sort_keys=True, separators=(",", ":")) + "\n")

    @staticmethod
    def _documents(path: Path) -> list[dict[str, Any]]:
        if path.is_dir():
            return [json.loads(item.read_text(encoding="utf-8")) for item in sorted(path.glob("*.json"))]
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def _hash(document: dict[str, Any], excluded_key: str | None = None) -> str:
        excluded_key = excluded_key or ("receipt_hash" if "receipt_hash" in document else "aggregate_hash")
        payload = {key: value for key, value in document.items() if key != excluded_key}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        return value.astimezone(timezone.utc) if value else datetime.now(timezone.utc)

    @classmethod
    def _timestamp(cls, value: datetime | None) -> str:
        return cls._now(value).isoformat()

    @staticmethod
    def _write_immutable(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("Signal records are append-only")
        with path.open("x", encoding="utf-8") as file:
            file.write(json.dumps(document, sort_keys=True, separators=(",", ":")))
            file.flush()
            os.fsync(file.fileno())
