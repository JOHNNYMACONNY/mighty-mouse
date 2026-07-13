"""Bounded, fail-closed local controller for v2 Background Research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from mighty_mouse.v2.foundation import (
    Candidate,
    Champion,
    EvidenceBundle,
    ExecutionProfile,
    Experiment,
    ExperimentDecision,
    ExperimentOutcome,
    Generation,
    ImmutableStateStore,
    ModelIdentity,
    Policy,
    Scope,
    validate_protected_task_categories,
)
from mighty_mouse.v2.signals import SignalLifecycle


_ALLOWED_MUTATION_PATHS = frozenset({"policy", "routing", "tool-order", "retry-budget", "checklist", "task-category"})
_THERMAL_STATES = frozenset({"normal", "warm", "critical"})


@dataclass(frozen=True)
class ResearchLimits:
    candidate_cap: int
    max_tool_calls: int
    max_duration_ms: int
    max_cost_units: int
    max_calls_per_minute: int
    max_concurrency: int = 1

    def __post_init__(self) -> None:
        if any(value < 1 for value in (self.candidate_cap, self.max_tool_calls, self.max_duration_ms, self.max_cost_units, self.max_calls_per_minute, self.max_concurrency)):
            raise ValueError("Background Research limits must be positive")
        if self.max_concurrency != 1:
            raise ValueError("v2 Background Research permits one Generation at a time")


class BackgroundResearch:
    """Owns durable controls and manifests; all results remain in the v2 state store."""

    control_filename = "v2-background-research-controls.jsonl"
    manifest_directory = "v2-background-research-manifests"
    schema_version = 1

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.controls_path = self.state_dir / self.control_filename
        self.manifest_dir = self.state_dir / self.manifest_directory
        self.store = ImmutableStateStore(self.state_dir)

    def start(
        self,
        *,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
        protocol_version: str,
        limits: ResearchLimits,
        seed_schedule: tuple[int, ...],
        task_order: tuple[str, ...],
        mutation_paths: tuple[str, ...],
        protected_task_categories: tuple[tuple[str, tuple[str, ...]], ...] = (),
    ) -> dict[str, Any]:
        if self._runnable_generation_id() is not None:
            raise ValueError("a Background Research Generation is running or resumable; stop it before starting another")
        self._validate_start_inputs(model_identity, execution_profile, protocol_version, seed_schedule, task_order, mutation_paths)
        protected_task_categories = protected_task_categories or (("all-development-tasks", task_order),)
        validate_protected_task_categories(protected_task_categories, task_order)
        champion, candidate = self._base_champion(scope, model_identity, execution_profile)
        generation_id = f"generation-{uuid4().hex}"
        manifest = {
            "schema_version": self.schema_version,
            "generation_id": generation_id,
            "base_champion_id": champion.champion_id,
            "base_candidate_id": candidate.candidate_id,
            "scope": {"mode": scope.mode.value, "repository": scope.repository, "task_category": scope.task_category.value, "model_class": scope.model_class},
            "model_digest": model_identity.artifact_digest,
            "execution_profile_id": execution_profile.profile_id,
            "compatible_execution_profile_ids": sorted(candidate.compatible_execution_profiles),
            "signal_aggregate_digest": self._signal_aggregate_digest(scope),
            "protocol_version": protocol_version,
            "limits": {"candidate_cap": limits.candidate_cap, "max_tool_calls": limits.max_tool_calls, "max_duration_ms": limits.max_duration_ms, "max_cost_units": limits.max_cost_units, "max_calls_per_minute": limits.max_calls_per_minute, "max_concurrency": limits.max_concurrency},
            "seed_schedule": list(seed_schedule),
            "task_order": list(task_order),
            "condition_order": ["baseline", "candidate"],
            "protected_task_categories": [[category, list(task_ids)] for category, task_ids in protected_task_categories],
            "mutation_paths": list(mutation_paths),
            "recorded_at": self._timestamp(),
        }
        manifest["manifest_digest"] = self._digest(manifest)
        self._write_immutable(self.manifest_dir / f"{generation_id}.json", manifest)
        self._append_control("started", generation_id, manifest["manifest_digest"])
        return self.status(generation_id)

    def stop(self) -> dict[str, Any]:
        generation_id = self._runnable_generation_id()
        if generation_id is None:
            raise ValueError("no Background Research Generation is running")
        manifest = self._manifest(generation_id)
        self._append_control("stopped", generation_id, manifest["manifest_digest"])
        return self.status(generation_id)

    def run(self, *, thermal_state: str, requested_tool_calls: int = 1, requested_duration_ms: int = 1, requested_cost_units: int = 1) -> dict[str, Any]:
        generation_id = self._runnable_generation_id()
        if generation_id is None:
            raise ValueError("Background Research is stopped; explicitly start it before running")
        manifest = self._manifest(generation_id)
        denial = self._resource_denial(manifest, thermal_state, requested_tool_calls, requested_duration_ms, requested_cost_units)
        if denial:
            self._append_control("budget_blocked", generation_id, manifest["manifest_digest"], reason=denial)
            raise ValueError(denial)
        self._append_control("usage", generation_id, manifest["manifest_digest"], usage={"tool_calls": requested_tool_calls, "duration_ms": requested_duration_ms, "cost_units": requested_cost_units})
        candidate = Candidate(
            candidate_id=f"candidate-{generation_id.rsplit('-', 1)[-1]}-001",
            policy=Policy(policy_id=f"policy-{generation_id.rsplit('-', 1)[-1]}-001", mode=self._scope(manifest).mode, version="generated-1"),
            scope=self._scope(manifest),
            model_digest=manifest["model_digest"],
            required_capabilities=frozenset(),
            compatible_execution_profiles=frozenset(manifest["compatible_execution_profile_ids"]),
        )
        experiment_id = f"experiment-{generation_id.rsplit('-', 1)[-1]}-001"
        evidence = EvidenceBundle(
            evidence_bundle_id=f"evidence-{generation_id.rsplit('-', 1)[-1]}-001",
            experiment_id=experiment_id,
            model_digest=manifest["model_digest"],
            execution_profile_id=manifest["execution_profile_id"],
            bundle_digest=manifest["manifest_digest"],
        )
        experiment = Experiment(
            experiment_id=experiment_id, generation_id=generation_id, baseline_candidate_id=manifest["base_candidate_id"],
            model_digest=manifest["model_digest"], execution_profile_id=manifest["execution_profile_id"],
            candidate_ids=(candidate.candidate_id,), evidence_bundle_ids=(evidence.evidence_bundle_id,),
            evidence_bundle_digests=(evidence.bundle_digest,), evaluation_outcomes=(), gate_results=(("mutation_surface", True), ("resource_limits", True), ("frozen_tasks", True)),
            protocol_version=manifest["protocol_version"], outcome=ExperimentOutcome.COMPLETED,
            decision=ExperimentDecision.NO_CHANGE, holdout_nominee_id=None,
        )
        generation = Generation(
            generation_id=generation_id, base_champion_id=manifest["base_champion_id"], scope=self._scope(manifest),
            model_digest=manifest["model_digest"], execution_profile_id=manifest["execution_profile_id"],
            compatible_execution_profile_ids=tuple(manifest["compatible_execution_profile_ids"]), signal_ids=(),
            signal_aggregate_digest=manifest["signal_aggregate_digest"], experiment_ids=(experiment_id,), candidate_ids=(candidate.candidate_id,),
            protocol_version=manifest["protocol_version"], mutation_budget=manifest["limits"]["candidate_cap"],
            seed_schedule=tuple(manifest["seed_schedule"]), task_order=tuple(manifest["task_order"]), condition_order=tuple(manifest["condition_order"]),
            protected_task_categories=tuple((category, tuple(task_ids)) for category, task_ids in manifest.get("protected_task_categories", ())),
            protocol_manifest_digest=manifest["manifest_digest"],
        )
        self.store.append_candidate(candidate)
        self.store.append(evidence)
        self.store.append(experiment)
        self.store.append(generation)
        self._append_control("completed", generation_id, manifest["manifest_digest"])
        return self.status(generation_id)

    def status(self, generation_id: str | None = None) -> dict[str, Any]:
        generation_id = generation_id or self._latest_generation_id()
        if generation_id is None:
            return {"schema_version": self.schema_version, "interface": "background_research", "state": "stopped", "generation_id": None}
        manifest = self._manifest(generation_id)
        controls = [control for control in self._controls() if control["generation_id"] == generation_id]
        action = next(control["action"] for control in reversed(controls) if control["action"] != "usage")
        state = {"started": "running", "stopped": "stopped", "budget_blocked": "budget-blocked", "completed": "completed"}[action]
        return {"schema_version": self.schema_version, "interface": "background_research", "state": state, "generation_id": generation_id, "manifest_digest": manifest["manifest_digest"], "base_champion_id": manifest["base_champion_id"], "candidate_cap": manifest["limits"]["candidate_cap"], "last_reason": controls[-1].get("reason")}

    def _base_champion(self, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> tuple[Champion, Candidate]:
        candidates = {record.value.candidate_id: record.value for record in self.store.records() if isinstance(record.value, Candidate)}
        for record in reversed(self.store.records()):
            champion = record.value
            if not isinstance(champion, Champion) or champion.scope != scope:
                continue
            if champion.model_digest != model_identity.artifact_digest or champion.execution_profile_id != execution_profile.profile_id:
                continue
            candidate = candidates.get(champion.candidate_id)
            if candidate and execution_profile.profile_id in candidate.compatible_execution_profiles and candidate.required_capabilities.issubset(execution_profile.capabilities):
                return champion, candidate
        raise ValueError("Background Research requires an exact compatible base Champion")

    def _validate_start_inputs(self, model_identity: ModelIdentity, execution_profile: ExecutionProfile, protocol_version: str, seed_schedule: tuple[int, ...], task_order: tuple[str, ...], mutation_paths: tuple[str, ...]) -> None:
        if not model_identity.is_complete or not execution_profile.is_complete:
            raise ValueError("Background Research requires complete Model Identity and Execution Profile")
        if not protocol_version or not seed_schedule or not task_order:
            raise ValueError("Background Research requires a frozen protocol version, seeds, and task order")
        if not mutation_paths or not set(mutation_paths).issubset(_ALLOWED_MUTATION_PATHS):
            raise ValueError("mutation surface is invalid; runtime code, evaluators, gates, holdouts, and unrelated state are denied")

    def _resource_denial(self, manifest: dict[str, Any], thermal_state: str, tool_calls: int, duration_ms: int, cost_units: int) -> str | None:
        if thermal_state not in _THERMAL_STATES:
            return "thermal state is invalid"
        if thermal_state == "critical":
            return "resource denial: thermal limit is critical"
        limits = manifest["limits"]
        usage = self._usage(manifest["generation_id"])
        for name, value, key, used_key in (("tool-call", tool_calls, "max_tool_calls", "tool_calls"), ("duration", duration_ms, "max_duration_ms", "duration_ms"), ("cost", cost_units, "max_cost_units", "cost_units")):
            if value < 0 or usage[used_key] + value > limits[key]:
                return f"resource denial: {name} limit exceeded"
        if tool_calls > limits["max_calls_per_minute"]:
            return "resource denial: rate limit exceeded"
        return None

    def _active_generation_id(self) -> str | None:
        latest = self._latest_generation_id()
        return latest if latest and self.status(latest)["state"] == "running" else None

    def _runnable_generation_id(self) -> str | None:
        latest = self._latest_generation_id()
        return latest if latest and self.status(latest)["state"] in {"running", "budget-blocked"} else None

    def _latest_generation_id(self) -> str | None:
        controls = self._controls()
        return controls[-1]["generation_id"] if controls else None

    def _controls(self) -> list[dict[str, Any]]:
        if not self.controls_path.exists():
            return []
        return [json.loads(line) for line in self.controls_path.read_text(encoding="utf-8").splitlines()]

    def _usage(self, generation_id: str) -> dict[str, int]:
        totals = {"tool_calls": 0, "duration_ms": 0, "cost_units": 0}
        for control in self._controls():
            if control["generation_id"] == generation_id and control["action"] == "usage":
                for key in totals:
                    totals[key] += control["usage"][key]
        return totals

    def _append_control(self, action: str, generation_id: str, manifest_digest: str, *, reason: str | None = None, usage: dict[str, int] | None = None) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": self.schema_version, "recorded_at": self._timestamp(), "action": action, "generation_id": generation_id, "manifest_digest": manifest_digest, "reason": reason, "usage": usage}
        with self.controls_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def _manifest(self, generation_id: str) -> dict[str, Any]:
        path = self.manifest_dir / f"{generation_id}.json"
        if not path.exists():
            raise ValueError("Background Research manifest is missing")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("manifest_digest") != self._digest(manifest, "manifest_digest"):
            raise ValueError("Background Research manifest integrity check failed")
        return manifest

    @staticmethod
    def _scope(manifest: dict[str, Any]) -> Scope:
        from mighty_mouse.v2.foundation import Mode, TaskCategory
        value = manifest["scope"]
        return Scope(Mode(value["mode"]), value["repository"], TaskCategory(value["task_category"]), value["model_class"])

    def _signal_aggregate_digest(self, scope: Scope) -> str:
        history = SignalLifecycle(self.state_dir).history(scope=scope)
        return "sha256:" + sha256(json.dumps(history, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _digest(document: dict[str, Any], excluded: str | None = None) -> str:
        payload = {key: value for key, value in document.items() if key != excluded}
        return "sha256:" + sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _write_immutable(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError("Background Research manifests are immutable")
        with path.open("x", encoding="utf-8") as file:
            file.write(json.dumps(document, sort_keys=True, separators=(",", ":")))
            file.flush()
            os.fsync(file.fileno())
