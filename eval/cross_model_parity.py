"""Milestone 13 — Cross-Model Frontier Parity v1: Harness Contract."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import yaml

import jsonschema

from eval.runner_lock import LOCK_FILE_PATH, SingleInstanceLock
from mighty_mouse.host.adapter import HostAdapter, MCP_TOOL_CONTRACT_VERSION

M13_SCHEMA_VERSION = "1.0.0"
M13_EXPERIMENT_ID = "m13-cross-model-pilot-01"
M13_EXPERIMENT_BASE_SHA = "e396d1960208673679d7aac8d2f9e6f5d10f2545"
M13_PLAN_DESIGN = "m13-cross-model-pilot-v1"
M13_ORDER_SEED = "m13-cross-model-pilot-v1"
M13_EFFECTIVE_CONTEXT_LIMIT = 32768
M13_ALLOWED_ARMS = ("control_once", "mm_single")
M13_CANONICAL_CONFIG_SHA256 = (
    "f846fec3c052c76ab6f944c889baf7e8ed217beffaaa47ed8c5851fb82cba8f3"
)

DEFAULT_CONFIG_PATH = Path("configs/mighty_mouse_v1.yaml")
DEFAULT_CONTRACT_PATH = Path("eval/cross_model_parity_contract.json")

M13_HARNESS_ALLOWED_PATHS = frozenset(
    {
        "eval/cross_model_parity.py",
        "eval/cross_model_parity_contract.json",
        "eval/test_cross_model_parity.py",
    }
)


@dataclass(frozen=True)
class CrossModelCandidate:
    candidate_id: str
    model_tag: str
    model_family: str
    model_class: str
    model_digest: str
    quantization: str
    parameter_scale: str
    packaged_context: int
    effective_context: int


@dataclass(frozen=True)
class CrossModelAnchorTask:
    tier: str
    task_id: str
    task_file: str
    sha256: str
    expected_files: Tuple[str, ...]


@dataclass(frozen=True)
class CrossModelPlanUnit:
    order_index: int
    trial_id: str
    candidate_id: str
    model_tag: str
    model_family: str
    model_class: str
    model_digest: str
    quantization: str
    packaged_context: int
    effective_context: int
    tier: str
    task_id: str
    task_file: str
    task_sha256: str
    arm: str
    replicate: int
    experiment_base_sha: str
    harness_sha: str
    sort_hash: str
    projected_config_sha256: Optional[str]


LLAMA_DIGEST = (
    "sha256:667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29"
)
QWEN_DIGEST = (
    "sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730"
)

FROZEN_CANDIDATES: Dict[str, CrossModelCandidate] = {
    "llama31_8b_q4km": CrossModelCandidate(
        candidate_id="llama31_8b_q4km",
        model_tag="llama3.1:8b-instruct-q4_K_M",
        model_family="llama",
        model_class="llama3.1-8b-local",
        model_digest=LLAMA_DIGEST,
        quantization="Q4_K_M",
        parameter_scale="8.0B",
        packaged_context=131072,
        effective_context=32768,
    ),
    "qwen25_7b_q4km": CrossModelCandidate(
        candidate_id="qwen25_7b_q4km",
        model_tag="qwen2.5:7b-instruct-q4_K_M",
        model_family="qwen2",
        model_class="qwen2.5-7b-local",
        model_digest=QWEN_DIGEST,
        quantization="Q4_K_M",
        parameter_scale="7.6B",
        packaged_context=32768,
        effective_context=32768,
    ),
}

TASK_003_SHA = (
    "d5ac92cf635fb9bb18340df6dc831d6b78fd0ccfaf046e4a79bfcd3657f49976"
)
TASK_047_SHA = (
    "9e40f53e472658c6689f759b30f20b85b1f9cdcb6d27367115e99e0619b54b47"
)
TASK_1415_SHA = (
    "750bec2e8f6f1888fea1dc502d19a123f312f540dbbcfe93dbd5bac39a0db486"
)

FROZEN_ANCHOR_TASKS: Dict[str, CrossModelAnchorTask] = {
    "task_003": CrossModelAnchorTask(
        tier="tier_1",
        task_id="task_003",
        task_file="tasks/benchmark/task_003_legacy_link_circuitbreaker.json",
        sha256=TASK_003_SHA,
        expected_files=("legacy_link.py",),
    ),
    "task_047": CrossModelAnchorTask(
        tier="tier_5",
        task_id="task_047",
        task_file="tasks/benchmark/task_047_stream_stack_enricher.json",
        sha256=TASK_047_SHA,
        expected_files=("stream_stack.py",),
    ),
    "task_1415": CrossModelAnchorTask(
        tier="tier_7",
        task_id="task_1415",
        task_file="tasks/benchmark/task_1415_file_proxy_retry.json",
        sha256=TASK_1415_SHA,
        expected_files=("file_proxy.py",),
    ),
}


FROZEN_CANDIDATES_JSON: Dict[str, Any] = json.loads(
    json.dumps({k: asdict(v) for k, v in FROZEN_CANDIDATES.items()})
)
FROZEN_ANCHOR_TASKS_JSON: Dict[str, Any] = json.loads(
    json.dumps({k: asdict(v) for k, v in FROZEN_ANCHOR_TASKS.items()})
)


def load_contract_schema(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> Dict[str, Any]:
    with open(contract_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_payload_against_schema(
    payload: Dict[str, Any],
    definition_name: str,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> None:
    schema = load_contract_schema(contract_path)
    target_schema = {
        "$schema": schema.get(
            "$schema", "http://json-schema.org/draft-07/schema#"
        ),
        "definitions": schema.get("definitions", {}),
        **schema["definitions"][definition_name],
    }
    jsonschema.validate(instance=payload, schema=target_schema)


def load_canonical_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_candidate_config(
    model_tag: str, config_path: Path = DEFAULT_CONFIG_PATH
) -> Tuple[Dict[str, Any], str]:
    canon = load_canonical_config(config_path)

    if canon.get("provider") != "ollama":
        raise ValueError(
            f"Expected canonical provider 'ollama', found "
            f"'{canon.get('provider')}'"
        )
    if canon.get("temperature") != 0.2:
        raise ValueError(
            "Canonical configuration parameter tampered: temperature != 0.2"
        )
    if canon.get("max_tokens") != 4000:
        raise ValueError(
            "Canonical configuration parameter tampered: max_tokens != 4000"
        )

    projected = dict(canon)
    projected["model"] = model_tag

    diff_keys = [k for k in projected if projected[k] != canon.get(k)]
    if diff_keys != ["model"]:
        raise ValueError(
            f"Projected configuration modified unauthorized keys: {diff_keys}"
        )

    serialized = yaml.dump(projected, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return projected, digest


def compute_sort_hash(
    base_sha: str,
    order_seed: str,
    candidate_id: str,
    task_id: str,
    arm: str,
    replicate: int,
) -> str:
    seed_str = (
        f"{base_sha}{order_seed}{candidate_id}{task_id}{arm}{replicate}"
    )
    return hashlib.sha256(seed_str.encode("utf-8")).hexdigest()


def get_current_git_sha() -> str:
    out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
    return out.strip()


def check_git_clean_except_prototype() -> None:
    out = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    for line in lines:
        parts = line.split(None, 1)
        if len(parts) == 2:
            status, path = parts
            is_proto = (
                status == "??"
                and path == "eval/prototype_apple_dashboard.html"
            )
            if is_proto:
                continue
            is_harness = (
                status == "??"
                and path in M13_HARNESS_ALLOWED_PATHS
            )
            if is_harness:
                continue
            raise ValueError(f"Working tree is not clean: '{line}'")
        raise ValueError(f"Working tree is not clean: '{line}'")


def verify_base_to_harness_delta(base_sha: str, harness_sha: str) -> None:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base_sha}..{harness_sha}"],
        text=True,
    )
    changed_files = [line.strip() for line in out.splitlines() if line.strip()]
    disallowed = [
        f for f in changed_files if f not in M13_HARNESS_ALLOWED_PATHS
    ]
    if disallowed:
        raise ValueError(
            f"Unauthorized file changes detected between base and harness: "
            f"{disallowed}"
        )


def materialize_execution_plan(
    harness_sha: Optional[str] = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Dict[str, Any]:
    if harness_sha is None:
        harness_sha = get_current_git_sha()

    canonical_config_bytes = config_path.read_bytes()
    canonical_config_sha256 = hashlib.sha256(
        canonical_config_bytes
    ).hexdigest()
    if canonical_config_sha256 != M13_CANONICAL_CONFIG_SHA256:
        raise ValueError(
            f"Canonical config SHA256 mismatch: expected "
            f"{M13_CANONICAL_CONFIG_SHA256}, found {canonical_config_sha256}"
        )

    projected_shas: Dict[str, str] = {}
    for cand_id, cand in FROZEN_CANDIDATES.items():
        _, proj_sha = project_candidate_config(cand.model_tag, config_path)
        projected_shas[cand_id] = proj_sha

    raw_units: List[Dict[str, Any]] = []

    for cand_id, cand in FROZEN_CANDIDATES.items():
        for task_id, task in FROZEN_ANCHOR_TASKS.items():
            for arm in M13_ALLOWED_ARMS:
                replicate = 1
                sort_hash = compute_sort_hash(
                    M13_EXPERIMENT_BASE_SHA,
                    M13_ORDER_SEED,
                    cand_id,
                    task_id,
                    arm,
                    replicate,
                )
                trial_id = (
                    f"m13_{cand_id}_{task.tier}_{task_id}_{arm}_rep{replicate}"
                )
                proj_config_sha = (
                    projected_shas[cand_id] if arm == "mm_single" else None
                )

                unit = {
                    "trial_id": trial_id,
                    "candidate_id": cand.candidate_id,
                    "model_tag": cand.model_tag,
                    "model_family": cand.model_family,
                    "model_class": cand.model_class,
                    "model_digest": cand.model_digest,
                    "quantization": cand.quantization,
                    "packaged_context": cand.packaged_context,
                    "effective_context": cand.effective_context,
                    "tier": task.tier,
                    "task_id": task.task_id,
                    "task_file": task.task_file,
                    "task_sha256": task.sha256,
                    "arm": arm,
                    "replicate": replicate,
                    "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
                    "harness_sha": harness_sha,
                    "sort_hash": sort_hash,
                    "projected_config_sha256": proj_config_sha,
                }
                raw_units.append(unit)

    sorted_units = sorted(raw_units, key=lambda u: u["sort_hash"])

    final_units: List[Dict[str, Any]] = []
    for idx, u in enumerate(sorted_units):
        u_with_idx = {"order_index": idx, **u}
        final_units.append(u_with_idx)

    plan = {
        "schema_version": M13_SCHEMA_VERSION,
        "experiment_id": M13_EXPERIMENT_ID,
        "plan_design": M13_PLAN_DESIGN,
        "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
        "order_seed": M13_ORDER_SEED,
        "effective_context_limit": M13_EFFECTIVE_CONTEXT_LIMIT,
        "canonical_config_path": str(config_path),
        "canonical_config_sha256": canonical_config_sha256,
        "candidates": copy.deepcopy(FROZEN_CANDIDATES_JSON),
        "anchor_tasks": copy.deepcopy(FROZEN_ANCHOR_TASKS_JSON),
        "arms": list(M13_ALLOWED_ARMS),
        "replicates": 1,
        "trial_count": len(final_units),
        "trial_units": final_units,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return plan


def validate_execution_plan(
    plan: Dict[str, Any],
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    current_head: Optional[str] = None,
) -> Dict[str, Any]:
    if current_head is None:
        current_head = get_current_git_sha()

    errors: List[str] = []

    try:
        validate_payload_against_schema(
            plan, "execution_plan", contract_path
        )
    except Exception as e:
        errors.append(f"Schema validation error: {e}")

    if plan.get("schema_version") != M13_SCHEMA_VERSION:
        errors.append(
            f"schema_version mismatch: expected {M13_SCHEMA_VERSION}, "
            f"found {plan.get('schema_version')}"
        )

    if plan.get("experiment_id") != M13_EXPERIMENT_ID:
        errors.append(
            f"experiment_id mismatch: expected {M13_EXPERIMENT_ID}, "
            f"found {plan.get('experiment_id')}"
        )

    if plan.get("plan_design") != M13_PLAN_DESIGN:
        errors.append(
            f"plan_design mismatch: expected {M13_PLAN_DESIGN}, "
            f"found {plan.get('plan_design')}"
        )

    if plan.get("order_seed") != M13_ORDER_SEED:
        errors.append(
            f"order_seed mismatch: expected {M13_ORDER_SEED}, "
            f"found {plan.get('order_seed')}"
        )

    if (
        plan.get("effective_context_limit")
        != M13_EFFECTIVE_CONTEXT_LIMIT
    ):
        errors.append(
            f"effective_context_limit mismatch: expected "
            f"{M13_EFFECTIVE_CONTEXT_LIMIT}, found "
            f"{plan.get('effective_context_limit')}"
        )

    if plan.get("canonical_config_path") != str(DEFAULT_CONFIG_PATH):
        errors.append(
            f"canonical_config_path mismatch: expected "
            f"{DEFAULT_CONFIG_PATH}, found {plan.get('canonical_config_path')}"
        )

    if plan.get("canonical_config_sha256") != M13_CANONICAL_CONFIG_SHA256:
        errors.append(
            f"canonical_config_sha256 mismatch: expected "
            f"{M13_CANONICAL_CONFIG_SHA256}, "
            f"found {plan.get('canonical_config_sha256')}"
        )

    cfg_path_str = plan.get("canonical_config_path", "")
    cfg_path = Path(cfg_path_str) if cfg_path_str else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        errors.append(f"canonical_config_path missing: {cfg_path}")
    else:
        disk_sha = hashlib.sha256(cfg_path.read_bytes()).hexdigest()
        if disk_sha != M13_CANONICAL_CONFIG_SHA256:
            errors.append(
                f"canonical config disk sha mismatch: expected "
                f"{M13_CANONICAL_CONFIG_SHA256}, disk has {disk_sha}"
            )

    if plan.get("candidates") != FROZEN_CANDIDATES_JSON:
        errors.append("Top-level candidates do not match frozen definitions")

    if plan.get("anchor_tasks") != FROZEN_ANCHOR_TASKS_JSON:
        errors.append(
            "Top-level anchor_tasks do not match frozen definitions"
        )

    if plan.get("arms") != list(M13_ALLOWED_ARMS):
        errors.append(
            f"arms mismatch: expected {list(M13_ALLOWED_ARMS)}, "
            f"found {plan.get('arms')}"
        )

    if plan.get("replicates") != 1:
        errors.append(
            f"replicates mismatch: expected 1, "
            f"found {plan.get('replicates')}"
        )

    if plan.get("experiment_base_sha") != M13_EXPERIMENT_BASE_SHA:
        errors.append(
            f"experiment_base_sha mismatch: expected "
            f"{M13_EXPERIMENT_BASE_SHA}, found "
            f"{plan.get('experiment_base_sha')}"
        )

    harness_sha = plan.get("harness_sha", "")
    if harness_sha != current_head:
        errors.append(
            f"harness_sha mismatch: plan has {harness_sha}, "
            f"current HEAD is {current_head}"
        )
    try:
        verify_base_to_harness_delta(
            M13_EXPERIMENT_BASE_SHA, harness_sha
        )
    except Exception as e:
        errors.append(f"Base to harness delta error: {e}")

    units = plan.get("trial_units", [])
    if len(units) != 12 or plan.get("trial_count") != 12:
        errors.append(
            f"trial_count must be exactly 12, found {len(units)}"
        )

    seen_order_indices = set()
    seen_trial_ids = set()
    seen_tuples = set()
    sort_hashes = []

    projected_shas: Dict[str, Optional[str]] = {}
    if cfg_path.exists():
        for cid, cand in FROZEN_CANDIDATES.items():
            try:
                _, psha = project_candidate_config(cand.model_tag, cfg_path)
                projected_shas[cid] = psha
            except Exception as e:
                projected_shas[cid] = None
                errors.append(f"Config projection failed for {cid}: {e}")

    for idx, u in enumerate(units):
        ord_idx = u.get("order_index")
        if ord_idx != idx:
            errors.append(
                f"Unit {idx} has non-contiguous order_index: {ord_idx}"
            )
        seen_order_indices.add(ord_idx)

        tid = u.get("trial_id")
        if tid in seen_trial_ids:
            errors.append(f"Duplicate trial_id: {tid}")
        seen_trial_ids.add(tid)

        cand_id = u.get("candidate_id")
        task_id = u.get("task_id")
        arm = u.get("arm")
        rep = u.get("replicate")

        tup = (cand_id, task_id, arm, rep)
        if tup in seen_tuples:
            errors.append(f"Duplicate trial execution tuple: {tup}")
        seen_tuples.add(tup)

        if arm not in M13_ALLOWED_ARMS:
            errors.append(f"Disallowed arm in unit {idx}: {arm}")

        if cand_id not in FROZEN_CANDIDATES:
            errors.append(f"Unknown candidate_id: {cand_id}")
        else:
            fc = FROZEN_CANDIDATES[cand_id]
            if u.get("model_tag") != fc.model_tag:
                errors.append(f"model_tag mismatch for {cand_id}")
            if u.get("model_family") != fc.model_family:
                errors.append(f"model_family mismatch for {cand_id}")
            if u.get("model_class") != fc.model_class:
                errors.append(f"model_class mismatch for {cand_id}")
            if u.get("model_digest") != fc.model_digest:
                errors.append(f"model_digest mismatch for {cand_id}")
            if u.get("quantization") != fc.quantization:
                errors.append(f"quantization mismatch for {cand_id}")
            if u.get("packaged_context") != fc.packaged_context:
                errors.append(
                    f"packaged_context mismatch for {cand_id}: "
                    f"{u.get('packaged_context')} != {fc.packaged_context}"
                )
            if u.get("effective_context") != fc.effective_context:
                errors.append(
                    f"effective_context mismatch for {cand_id}: "
                    f"{u.get('effective_context')} != {fc.effective_context}"
                )

        if task_id not in FROZEN_ANCHOR_TASKS:
            errors.append(f"Unknown task_id: {task_id}")
        else:
            ft = FROZEN_ANCHOR_TASKS[task_id]
            if u.get("tier") != ft.tier:
                errors.append(
                    f"tier mismatch for {task_id}: {u.get('tier')} "
                    f"!= {ft.tier}"
                )
            if u.get("task_file") != ft.task_file:
                errors.append(
                    f"task_file mismatch for {task_id}: "
                    f"{u.get('task_file')} != {ft.task_file}"
                )
            if u.get("task_sha256") != ft.sha256:
                errors.append(f"task_sha256 mismatch for {task_id}")

        if u.get("experiment_base_sha") != M13_EXPERIMENT_BASE_SHA:
            errors.append(
                f"experiment_base_sha mismatch in unit {idx}: "
                f"{u.get('experiment_base_sha')} != "
                f"{M13_EXPERIMENT_BASE_SHA}"
            )

        if u.get("harness_sha") != harness_sha:
            errors.append(
                f"harness_sha mismatch in unit {idx}: "
                f"{u.get('harness_sha')} != {harness_sha}"
            )

        if cand_id in FROZEN_CANDIDATES and task_id in FROZEN_ANCHOR_TASKS:
            exp_tid = (
                f"m13_{cand_id}_{FROZEN_ANCHOR_TASKS[task_id].tier}_"
                f"{task_id}_{arm}_rep{rep}"
            )
            if tid != exp_tid:
                errors.append(
                    f"trial_id mismatch in unit {idx}: expected {exp_tid}, "
                    f"found {tid}"
                )

        if arm == "mm_single":
            exp_sha = projected_shas.get(cand_id)
            if exp_sha is None or u.get("projected_config_sha256") != exp_sha:
                errors.append(
                    f"projected_config_sha256 mismatch in unit {idx}: "
                    f"expected {exp_sha}, "
                    f"found {u.get('projected_config_sha256')}"
                )
        else:
            if u.get("projected_config_sha256") is not None:
                errors.append(
                    f"control_once unit {idx} must have null "
                    f"projected_config_sha256"
                )

        expected_sh = compute_sort_hash(
            M13_EXPERIMENT_BASE_SHA,
            M13_ORDER_SEED,
            cand_id,
            task_id,
            arm,
            rep,
        )
        if u.get("sort_hash") != expected_sh:
            errors.append(f"Sort hash mismatch in unit {idx}")
        sort_hashes.append(u.get("sort_hash", ""))

    if sort_hashes != sorted(sort_hashes):
        errors.append(
            "Trial units are not ordered according to "
            "deterministic sort_hash"
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def run_preflight(
    config_path: Path = DEFAULT_CONFIG_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    lock_path: Path = LOCK_FILE_PATH,
) -> Dict[str, Any]:
    with SingleInstanceLock(lock_path):
        blocking_reasons: List[str] = []

        harness_sha = get_current_git_sha()
        try:
            check_git_clean_except_prototype()
        except Exception as e:
            blocking_reasons.append(f"Git clean check failed: {e}")

        try:
            verify_base_to_harness_delta(M13_EXPERIMENT_BASE_SHA, harness_sha)
        except Exception as e:
            blocking_reasons.append(f"Base to harness delta failed: {e}")

        ollama_ver = "unknown"
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/version")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ollama_ver = data.get("version", "unknown")
        except Exception as e:
            blocking_reasons.append(
                f"Failed to inspect Ollama API version: {e}"
            )

        cand_val: Dict[str, Any] = {}
        for cid, cand in FROZEN_CANDIDATES.items():
            try:
                d1 = HostAdapter.resolve_ollama_model_digest(cand.model_tag)
                d2 = HostAdapter.resolve_ollama_model_digest(cand.model_tag)
                if d1 != d2:
                    blocking_reasons.append(
                        f"Unstable digest resolution for {cand.model_tag}"
                    )
                if d1 != cand.model_digest:
                    blocking_reasons.append(
                        f"Model digest mismatch for {cand.model_tag}: "
                        f"resolved {d1} != expected {cand.model_digest}"
                    )
                cand_val[cid] = {
                    "installed": True,
                    "resolved_digest": d1,
                    "matches_frozen": d1 == cand.model_digest,
                }
            except Exception as e:
                blocking_reasons.append(
                    f"Failed to validate candidate {cand.model_tag}: {e}"
                )
                cand_val[cid] = {"installed": False, "error": str(e)}

        task_val: Dict[str, Any] = {}
        for tid, task in FROZEN_ANCHOR_TASKS.items():
            tp = Path(task.task_file)
            if not tp.exists():
                blocking_reasons.append(
                    f"Anchor task file missing: {task.task_file}"
                )
                task_val[tid] = {"exists": False}
            else:
                actual_sha = hashlib.sha256(tp.read_bytes()).hexdigest()
                matches = actual_sha == task.sha256
                if not matches:
                    blocking_reasons.append(
                        f"Anchor task hash mismatch: {task.task_file}"
                    )
                task_val[tid] = {
                    "exists": True,
                    "sha256": actual_sha,
                    "matches": matches,
                }

        config_val: Dict[str, Any] = {}
        cfg_ok = False
        try:
            canon_bytes = config_path.read_bytes()
            canon_sha = hashlib.sha256(canon_bytes).hexdigest()
            config_val["canonical_sha256"] = canon_sha

            for cid, cand in FROZEN_CANDIDATES.items():
                _, proj_sha = project_candidate_config(
                    cand.model_tag, config_path
                )
                config_val[cid] = {"projected_sha256": proj_sha}
            cfg_ok = True
        except Exception as e:
            blocking_reasons.append(f"Config projection failure: {e}")

        mcp_ver: Optional[str] = f"v{MCP_TOOL_CONTRACT_VERSION}"
        if MCP_TOOL_CONTRACT_VERSION != 6:
            blocking_reasons.append(
                f"MCP contract version mismatch: expected v6, found {mcp_ver}"
            )

        mcp_count: Optional[int] = None
        try:
            from mighty_mouse_mcp.server import _get_mcp_tool_signatures
            sigs = _get_mcp_tool_signatures()
            mcp_count = len(sigs)
            if mcp_count != 15:
                blocking_reasons.append(
                    f"MCP tool count mismatch: expected 15, found {mcp_count}"
                )
        except Exception as e:
            blocking_reasons.append(
                f"Failed to inspect MCP tool signatures: {e}"
            )

        plan_report: Dict[str, Any]
        if not cfg_ok:
            plan_err = (
                "Plan materialization skipped due to config projection "
                "failure"
            )
            plan_report = {"valid": False, "errors": [plan_err]}
        else:
            try:
                plan = materialize_execution_plan(
                    harness_sha=harness_sha, config_path=config_path
                )
                plan_report = validate_execution_plan(
                    plan, contract_path=contract_path, current_head=harness_sha
                )
                if not plan_report["valid"]:
                    blocking_reasons.extend(plan_report["errors"])
            except Exception as e:
                plan_err = f"Failed to materialize or validate plan: {e}"
                blocking_reasons.append(plan_err)
                plan_report = {"valid": False, "errors": [plan_err]}

        report = {
            "status": "PASSED" if not blocking_reasons else "FAILED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_base_sha": M13_EXPERIMENT_BASE_SHA,
            "git_harness_sha": harness_sha,
            "ollama_version": ollama_ver,
            "candidate_validation": cand_val,
            "anchor_task_validation": task_val,
            "config_projection_validation": config_val,
            "mcp_tools_count": mcp_count,
            "mcp_contract_version": mcp_ver,
            "execution_plan_validation": plan_report,
            "generation_calls": 0,
            "blocking_reasons": blocking_reasons,
        }

        validate_payload_against_schema(
            report, "preflight_report", contract_path
        )
        return report
