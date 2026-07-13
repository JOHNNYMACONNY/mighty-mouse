"""Isolated paired development evaluation for frozen v2 Generations."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from typing import Callable
from uuid import uuid4

from mighty_mouse.v2.foundation import Candidate, Champion, EvidenceBundle, EvaluationOutcome, EvaluationOutcomeKind, Experiment, ExperimentDecision, ExperimentOutcome, FreshHoldout, Generation, ImmutableStateStore


@dataclass(frozen=True)
class EvaluationRun:
    kind: EvaluationOutcomeKind
    duration_ms: int = 0
    tool_calls: int = 0
    retries: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class ConditionRun:
    task_id: str
    paired_candidate_id: str
    candidate_id: str
    run: EvaluationRun

Runner = Callable[[str, Candidate, Path, int], EvaluationRun | EvaluationOutcomeKind]

@dataclass(frozen=True)
class EvaluationRequest:
    generation_id: str
    base_workspace: Path
    preparation_digest: str
    budget_digest: str
    capability_probe_passed: bool
    sandbox_check_passed: bool
    protected_task_categories: tuple[tuple[str, tuple[str, ...]], ...] = ()

@dataclass(frozen=True)
class EvaluationResult:
    experiment_id: str
    outcome: ExperimentOutcome
    decision: ExperimentDecision
    holdout_nominee_id: str | None


@dataclass(frozen=True)
class FreshHoldoutRequest:
    """Quarantined, precommitted paired evaluation inputs; never used for tuning."""

    experiment_id: str
    candidate_id: str
    base_workspace: Path
    task_ids: tuple[str, ...]
    protocol_digest: str
    environment_digest: str
    corpus_digest: str
    task_digests: tuple[tuple[str, str], ...] = ()
    manifest_digest: str | None = None
    contaminated: bool = False
    exposed: bool = False

    def __post_init__(self) -> None:
        if (not self.task_ids or len(set(self.task_ids)) != len(self.task_ids)
                or not all((self.protocol_digest, self.environment_digest, self.corpus_digest))):
            raise ValueError("fresh holdout requires frozen tasks and versioned protocol inputs")
        if self.contaminated or self.exposed:
            raise ValueError("consumed, contaminated, or exposed holdout tasks are ineligible")
        if self.task_digests and {task for task, _ in self.task_digests} != set(self.task_ids):
            raise ValueError("fresh holdout task IDs and frozen task digests must match")

class DevelopmentEvaluator:
    """Runs frozen development tasks only; no holdout input exists in this API."""
    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.store = ImmutableStateStore(state_dir)

    def evaluate(self, request: EvaluationRequest, runner: Runner) -> EvaluationResult:
        with self._lock():
            generation, champion, baseline, candidates = self._inputs(request.generation_id)
            if self._already_nominated(generation.generation_id):
                raise ValueError("a Generation may nominate at most one holdout contender")
            if not request.base_workspace.is_dir() or not request.preparation_digest or not request.budget_digest:
                raise ValueError("evaluation requires a base workspace and frozen preparation and budget digests")
            gates = (("capability_probe", request.capability_probe_passed), ("sandbox", request.sandbox_check_passed))
            runs: list[ConditionRun] = []
            base_digest = self._tree_digest(request.base_workspace)
            if all(value for _, value in gates):
                try:
                    with TemporaryDirectory(prefix="mighty-mouse-eval-snapshot-") as root:
                        snapshot = Path(root) / "base"; copytree(request.base_workspace, snapshot)
                        if len(generation.condition_order) != 2 or set(generation.condition_order) != {"baseline", "candidate"}:
                            raise ValueError("frozen condition order is invalid")
                        for paired_candidate in candidates:
                            order = tuple(baseline if item == "baseline" else paired_candidate for item in generation.condition_order)
                            for index, task_id in enumerate(generation.task_order):
                                seed = generation.seed_schedule[index % len(generation.seed_schedule)]
                                for candidate in order:
                                    with TemporaryDirectory(prefix="mighty-mouse-eval-") as condition:
                                        workspace = Path(condition) / "worktree"; copytree(snapshot, workspace)
                                        try:
                                            result = runner(task_id, candidate, workspace, seed)
                                            run = result if isinstance(result, EvaluationRun) else EvaluationRun(result)
                                        except Exception:
                                            run = EvaluationRun(EvaluationOutcomeKind.ERROR, reason="runner_exception")
                                    runs.append(ConditionRun(task_id, paired_candidate.candidate_id, candidate.candidate_id, self._normalize_run(run)))
                except OSError:
                    runs = [ConditionRun(task, paired.candidate_id, candidate.candidate_id, EvaluationRun(EvaluationOutcomeKind.ERROR, reason="workspace_error")) for task in generation.task_order for paired in candidates for candidate in (baseline, paired)]
            outcomes = tuple(EvaluationOutcome(item.task_id, item.candidate_id, item.run.kind, item.run.reason) for item in runs)
            base_failed = any(
                item.candidate_id == baseline.candidate_id and item.run.kind is EvaluationOutcomeKind.ERROR
                for item in runs
            )
            invalid = not all(value for _, value in gates) or any(
                item.run.kind is EvaluationOutcomeKind.INVALID for item in runs
            )
            outcome = ExperimentOutcome.INVALID if invalid else ExperimentOutcome.FAILED if base_failed else ExperimentOutcome.COMPLETED
            winner = None if outcome is not ExperimentOutcome.COMPLETED else self._winner(baseline, candidates, runs, request.protected_task_categories)
            experiment_id = f"experiment-{uuid4().hex}"
            digest = self._digest({"generation": generation.generation_id, "base_digest": base_digest, "preparation_digest": request.preparation_digest, "budget_digest": request.budget_digest, "tasks": generation.task_order, "seeds": generation.seed_schedule, "condition_order": generation.condition_order, "gates": gates, "runs": [(item.task_id, item.paired_candidate_id, item.candidate_id, item.run.kind.value, item.run.duration_ms, item.run.tool_calls, item.run.retries, item.run.reason) for item in runs]})
            evidence = EvidenceBundle(f"evidence-{uuid4().hex}", experiment_id, generation.model_digest, generation.execution_profile_id, digest)
            condition_evidence = tuple(EvidenceBundle(f"evidence-{uuid4().hex}", experiment_id, generation.model_digest, generation.execution_profile_id, self._digest({"experiment": experiment_id, "task": item.task_id, "paired": item.paired_candidate_id, "candidate": item.candidate_id, "outcome": item.run.kind.value, "reason": item.run.reason})) for item in runs)
            all_evidence = (evidence, *condition_evidence)
            experiment = Experiment(experiment_id, generation.generation_id, baseline.candidate_id, generation.model_digest, generation.execution_profile_id, tuple(c.candidate_id for c in candidates), tuple(item.evidence_bundle_id for item in all_evidence), tuple(item.bundle_digest for item in all_evidence), outcomes, gates, generation.protocol_version, outcome, ExperimentDecision.NOMINATE if winner else ExperimentDecision.NO_CHANGE, winner.candidate_id if winner else None)
            for bundle in all_evidence: self.store.append(bundle)
            self.store.append(experiment)
            return EvaluationResult(experiment_id, experiment.outcome, experiment.decision, experiment.holdout_nominee_id)

    def _inputs(self, generation_id: str):
        records = self.store.records(); generation = next((r.value for r in reversed(records) if isinstance(r.value, Generation) and r.value.generation_id == generation_id), None)
        candidates = {r.value.candidate_id: r.value for r in records if isinstance(r.value, Candidate)}; champions = {r.value.champion_id: r.value for r in records if isinstance(r.value, Champion)}
        champion = champions.get(generation.base_champion_id) if generation else None; baseline = candidates.get(champion.candidate_id) if champion else None
        selected = tuple(candidates[c] for c in generation.candidate_ids) if generation and all(c in candidates for c in generation.candidate_ids) else ()
        if not generation or not champion or not baseline or not selected: raise ValueError("Generation lacks immutable evaluation inputs")
        if champion.scope != generation.scope or champion.model_digest != generation.model_digest or champion.execution_profile_id != generation.execution_profile_id or baseline.scope != generation.scope or baseline.model_digest != generation.model_digest or generation.execution_profile_id not in baseline.compatible_execution_profiles: raise ValueError("base Champion is incompatible with frozen Generation")
        if any(c.scope != generation.scope or c.model_digest != generation.model_digest or generation.execution_profile_id not in c.compatible_execution_profiles for c in selected): raise ValueError("Candidate is incompatible with frozen Generation")
        return generation, champion, baseline, selected

    def _already_nominated(self, generation_id): return any(isinstance(r.value, Experiment) and r.value.generation_id == generation_id and r.value.holdout_nominee_id for r in self.store.records())
    @staticmethod
    def _winner(baseline, candidates, runs, protected_task_categories=()):
        def score(candidate, paired_candidate_id):
            values = [item.run for item in runs if item.paired_candidate_id == paired_candidate_id and item.candidate_id == candidate.candidate_id]
            return (sum(run.kind is EvaluationOutcomeKind.PASSED for run in values), -sum(run.duration_ms + run.tool_calls for run in values), -sum(run.retries for run in values))
        eligible = [candidate for candidate in candidates if not any(item.run.kind is EvaluationOutcomeKind.ERROR for item in runs if item.candidate_id == candidate.candidate_id)]
        def protects(candidate):
            for _, task_ids in protected_task_categories:
                candidate_passes = sum(item.run.kind is EvaluationOutcomeKind.PASSED for item in runs if item.paired_candidate_id == candidate.candidate_id and item.candidate_id == candidate.candidate_id and item.task_id in task_ids)
                baseline_passes = sum(item.run.kind is EvaluationOutcomeKind.PASSED for item in runs if item.paired_candidate_id == candidate.candidate_id and item.candidate_id == baseline.candidate_id and item.task_id in task_ids)
                if candidate_passes < baseline_passes: return False
            return True
        contenders = [candidate for candidate in eligible if protects(candidate) and score(candidate, candidate.candidate_id) > score(baseline, candidate.candidate_id)]
        if not contenders:
            return None
        best_score = max(score(candidate, candidate.candidate_id) for candidate in contenders)
        finalists = [candidate for candidate in contenders if score(candidate, candidate.candidate_id) == best_score]
        return finalists[0] if len(finalists) == 1 else None

    @staticmethod
    def _normalize_run(run: EvaluationRun) -> EvaluationRun:
        if run.kind is EvaluationOutcomeKind.TIMEOUT:
            return EvaluationRun(EvaluationOutcomeKind.ERROR, run.duration_ms, run.tool_calls, run.retries, run.reason or "timeout")
        return run
    @contextmanager
    def _lock(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / "v2-evaluation.lock").open("a+") as file:
            import fcntl; fcntl.flock(file.fileno(), fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    @staticmethod
    def _digest(value): return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    @classmethod
    def _tree_digest(cls, path):
        digest = sha256()
        for item in sorted(path.rglob("*")):
            if item.is_file(): digest.update(str(item.relative_to(path)).encode()); digest.update(item.read_bytes())
        return "sha256:" + digest.hexdigest()


class FreshHoldoutEvaluator:
    """One-way quarantined gate: its results never feed Generation or Signals."""

    def __init__(self, state_dir: str | Path) -> None:
        self.store = ImmutableStateStore(state_dir)

    def evaluate(self, request: FreshHoldoutRequest, runner: Runner) -> FreshHoldout:
        records = self.store.records()
        experiment = next((r.value for r in reversed(records) if isinstance(r.value, Experiment) and r.value.experiment_id == request.experiment_id), None)
        candidates = {r.value.candidate_id: r.value for r in records if isinstance(r.value, Candidate)}
        if not experiment or experiment.holdout_nominee_id != request.candidate_id:
            raise ValueError("fresh holdout requires one recorded nominated contender")
        candidate, baseline = candidates.get(request.candidate_id), candidates.get(experiment.baseline_candidate_id)
        if not candidate or not baseline or not request.base_workspace.is_dir():
            raise ValueError("fresh holdout requires recorded paired inputs and a base workspace")
        if not request.task_digests or not request.manifest_digest:
            raise ValueError("fresh holdout requires a controller-frozen private manifest")
        task_digests, manifest_digest = request.task_digests, request.manifest_digest
        manifest_path = self._manifest_path(manifest_digest)
        if not manifest_path.is_file() or json.loads(manifest_path.read_text()) != {"corpus": request.corpus_digest, "protocol": request.protocol_digest, "environment": request.environment_digest, "tasks": [list(item) for item in task_digests]}:
            raise ValueError("fresh holdout manifest does not match frozen private corpus")
        if any(isinstance(r.value, FreshHoldout) and (
            r.value.manifest_digest == manifest_digest or set(r.value.task_digests).intersection(task_digests)
        ) for r in records):
            raise ValueError("fresh holdout manifest or task has already been consumed")
        passed = True
        with TemporaryDirectory(prefix="mighty-mouse-holdout-") as root:
            for task_id in request.task_ids:
                for condition in (baseline, candidate):
                    workspace = Path(root) / f"{task_id}-{condition.candidate_id}"
                    copytree(request.base_workspace, workspace)
                    try:
                        run = runner(task_id, condition, workspace, 0)
                        kind = run.kind if isinstance(run, EvaluationRun) else run
                    except Exception:
                        kind = EvaluationOutcomeKind.ERROR
                    if kind is not EvaluationOutcomeKind.PASSED:
                        passed = False
        evidence_id = next((identifier for identifier in experiment.evidence_bundle_ids), None)
        result = FreshHoldout(candidate.candidate_id, candidate.scope, candidate.model_digest, experiment.execution_profile_id, passed,
                              experiment.experiment_id, evidence_id, manifest_digest, request.corpus_digest,
                              request.protocol_digest, task_digests, True, request.contaminated, request.exposed)
        self.store.append(result)
        return result

    @staticmethod
    def _digest(value) -> str:
        return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _manifest_path(self, digest: str) -> Path:
        return self.store.path.parent / "fresh-holdout-manifests" / f"{digest.removeprefix('sha256:')}.json"

    def freeze_manifest(self, *, task_digests: tuple[tuple[str, str], ...], corpus_digest: str, protocol_digest: str, environment_digest: str) -> str:
        if not task_digests or len({task for task, _ in task_digests}) != len(task_digests): raise ValueError("private manifest requires unique frozen task digests")
        payload = {"corpus": corpus_digest, "protocol": protocol_digest, "environment": environment_digest, "tasks": [list(item) for item in task_digests]}
        digest = self._digest(payload); path = self._manifest_path(digest); path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and json.loads(path.read_text()) != payload: raise ValueError("private manifest digest collision")
        path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return digest
