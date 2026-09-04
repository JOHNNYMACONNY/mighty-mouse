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
M13_EXECUTION_BASE_SHA = "751d5094ccb472ccdaf65fc967405913f0136e09"
M13_PLAN_DESIGN = "m13-cross-model-pilot-v1"
M13_ORDER_SEED = "m13-cross-model-pilot-v1"
M13_EFFECTIVE_CONTEXT_LIMIT = 32768
M13_ALLOWED_ARMS = ("control_once", "mm_single")
M13_CANONICAL_CONFIG_SHA256 = (
    "f846fec3c052c76ab6f944c889baf7e8ed217beffaaa47ed8c5851fb82cba8f3"
)

M13_PHASE_B_EXPERIMENT_ID = "m13-cross-model-phase-b-01"
M13_PHASE_B_PLAN_DESIGN = "m13-cross-model-phase-b-v1"
M13_PHASE_B_ORDER_SEED = "m13-cross-model-phase-b-v1"
M13_PHASE_B_EXECUTION_BASE_SHA = "667fd939bbcc865d166d86a8dbd28c81272c4ecb"
M13_PHASE_B_TRIAL_COUNT = 56

DEFAULT_CONFIG_PATH = Path("configs/mighty_mouse_v1.yaml")
DEFAULT_CONTRACT_PATH = Path("eval/cross_model_parity_contract.json")

M13_HARNESS_ALLOWED_PATHS = frozenset(
    {
        "eval/cross_model_parity.py",
        "eval/cross_model_parity_contract.json",
        "eval/test_cross_model_parity.py",
        "eval/cross_model_parity_execution.py",
        "eval/test_cross_model_parity_execution.py",
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

FROZEN_PHASE_B_TASKS: Dict[str, CrossModelAnchorTask] = {
    "task_003": CrossModelAnchorTask(
        tier="tier_1",
        task_id="task_003",
        task_file="tasks/benchmark/task_003_legacy_link_circuitbreaker.json",
        sha256=(
            "d5ac92cf635fb9bb18340df6dc831d6b78fd0ccfaf046e4a79bfcd3657f49976"
        ),
        expected_files=("legacy_link.py",),
    ),
    "task_001": CrossModelAnchorTask(
        tier="tier_1",
        task_id="task_001",
        task_file="tasks/benchmark/task_001_legacy_registry_ratelimiter.json",
        sha256=(
            "b711f6469a2870ff71d6831a2b9ee7af9659f0fc52ce5e329de90c508e803cc2"
        ),
        expected_files=("legacy_registry.py",),
    ),
    "task_011": CrossModelAnchorTask(
        tier="tier_overnight",
        task_id="task_011",
        task_file=(
            "tasks/benchmark/task_011_realtime_decorator_ratelimiter.json"
        ),
        sha256=(
            "60c7f56233e6f87a69191247bc9cccf31697b90dec188c2bf690b5f133d2ca50"
        ),
        expected_files=("realtime_decorator.py",),
    ),
    "task_012": CrossModelAnchorTask(
        tier="tier_overnight",
        task_id="task_012",
        task_file="tasks/benchmark/task_012_network_facade_retry.json",
        sha256=(
            "330b4888c625a01e8a9457c095fcd9785c7b5adc7a3cc7bd325f09d8db4f9c9c"
        ),
        expected_files=("network_facade.py",),
    ),
    "task_025": CrossModelAnchorTask(
        tier="tier_3",
        task_id="task_025",
        task_file="tasks/benchmark/task_025_async_factory_transformer.json",
        sha256=(
            "1c71e53de1728f655f5fb870ef57094f6b436b22487638c6c9db183c543b7da6"
        ),
        expected_files=("async_factory.py",),
    ),
    "task_016": CrossModelAnchorTask(
        tier="tier_3",
        task_id="task_016",
        task_file="tasks/benchmark/task_016_memory_stack_enricher.json",
        sha256=(
            "5e49f11dd2eb2b1547226c9b5a14277cb9ac9b918a5972e671a9122f9fa8085f"
        ),
        expected_files=("memory_stack.py",),
    ),
    "task_033": CrossModelAnchorTask(
        tier="tier_4",
        task_id="task_033",
        task_file="tasks/benchmark/task_033_cloud_composite_retry.json",
        sha256=(
            "6ddaf8333466ccd336c4936d0f8d8d9787370348fa52bb42b70d9604108d212b"
        ),
        expected_files=("cloud_composite.py",),
    ),
    "task_029": CrossModelAnchorTask(
        tier="tier_4",
        task_id="task_029",
        task_file="tasks/benchmark/task_029_stream_proxy_filter.json",
        sha256=(
            "1bd8fd93dafa2720ba891362f00ebef6b2b565f10b804a49caeb3f3f3053c2ed"
        ),
        expected_files=("stream_proxy.py",),
    ),
    "task_047": CrossModelAnchorTask(
        tier="tier_5",
        task_id="task_047",
        task_file="tasks/benchmark/task_047_stream_stack_enricher.json",
        sha256=(
            "9e40f53e472658c6689f759b30f20b85b1f9cdcb6d27367115e99e0619b54b47"
        ),
        expected_files=("stream_stack.py",),
    ),
    "task_045": CrossModelAnchorTask(
        tier="tier_5",
        task_id="task_045",
        task_file="tasks/benchmark/task_045_file_node_enricher.json",
        sha256=(
            "0ad0407e97e2bcc7ce06b99d9ae5586ea440b274de898f166828909efb75f88d"
        ),
        expected_files=("file_node.py",),
    ),
    "task_1014": CrossModelAnchorTask(
        tier="tier_6",
        task_id="task_1014",
        task_file="tasks/benchmark/task_1014_async_bridge_transformer.json",
        sha256=(
            "52ad25c60bd876aa9c50c22896553fa142646c16dffc721eadc81d179aa22153"
        ),
        expected_files=("async_bridge.py",),
    ),
    "task_1007": CrossModelAnchorTask(
        tier="tier_6",
        task_id="task_1007",
        task_file="tasks/benchmark/task_1007_legacy_cache_transformer.json",
        sha256=(
            "f3d40a60eb9b176f94a92f7974f6b0913a5c8de8e8a7b294efdfe9a40411eb86"
        ),
        expected_files=("legacy_cache.py",),
    ),
    "task_1415": CrossModelAnchorTask(
        tier="tier_7",
        task_id="task_1415",
        task_file="tasks/benchmark/task_1415_file_proxy_retry.json",
        sha256=(
            "750bec2e8f6f1888fea1dc502d19a123f312f540dbbcfe93dbd5bac39a0db486"
        ),
        expected_files=("file_proxy.py",),
    ),
    "task_1407": CrossModelAnchorTask(
        tier="tier_7",
        task_id="task_1407",
        task_file="tasks/benchmark/task_1407_memory_data_validator.json",
        sha256=(
            "da95501872193512a9853ecc37e78587cafbde6352128a0f15dfc302fc7268a7"
        ),
        expected_files=("memory_data.py",),
    ),
}

FROZEN_PHASE_B_TASKS_JSON: Dict[str, Any] = json.loads(
    json.dumps({k: asdict(v) for k, v in FROZEN_PHASE_B_TASKS.items()})
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


def verify_base_to_harness_delta(
    base_sha: str = M13_EXECUTION_BASE_SHA,
    harness_sha: Optional[str] = None,
) -> List[str]:
    if harness_sha is None:
        harness_sha = get_current_git_sha()
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
    return changed_files


def materialize_execution_plan(
    harness_sha: Optional[str] = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    experiment_id: str = M13_EXPERIMENT_ID,
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

    is_phase_b = experiment_id == M13_PHASE_B_EXPERIMENT_ID
    if is_phase_b:
        exp_id = M13_PHASE_B_EXPERIMENT_ID
        plan_design = M13_PHASE_B_PLAN_DESIGN
        order_seed = M13_PHASE_B_ORDER_SEED
        tasks_dict = FROZEN_PHASE_B_TASKS
        tasks_json = FROZEN_PHASE_B_TASKS_JSON
        trial_prefix = "m13_b"
    else:
        exp_id = M13_EXPERIMENT_ID
        plan_design = M13_PLAN_DESIGN
        order_seed = M13_ORDER_SEED
        tasks_dict = FROZEN_ANCHOR_TASKS
        tasks_json = FROZEN_ANCHOR_TASKS_JSON
        trial_prefix = "m13"

    projected_shas: Dict[str, str] = {}
    for cand_id, cand in FROZEN_CANDIDATES.items():
        _, proj_sha = project_candidate_config(cand.model_tag, config_path)
        projected_shas[cand_id] = proj_sha

    raw_units: List[Dict[str, Any]] = []

    for cand_id, cand in FROZEN_CANDIDATES.items():
        for task_id, task in tasks_dict.items():
            for arm in M13_ALLOWED_ARMS:
                replicate = 1
                sort_hash = compute_sort_hash(
                    M13_EXPERIMENT_BASE_SHA,
                    order_seed,
                    cand_id,
                    task_id,
                    arm,
                    replicate,
                )
                trial_id = (
                    f"{trial_prefix}_{cand_id}_{task.tier}_{task_id}_"
                    f"{arm}_rep{replicate}"
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
        "experiment_id": exp_id,
        "plan_design": plan_design,
        "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
        "order_seed": order_seed,
        "effective_context_limit": M13_EFFECTIVE_CONTEXT_LIMIT,
        "canonical_config_path": str(config_path),
        "canonical_config_sha256": canonical_config_sha256,
        "candidates": copy.deepcopy(FROZEN_CANDIDATES_JSON),
        "anchor_tasks": copy.deepcopy(tasks_json),
        "arms": list(M13_ALLOWED_ARMS),
        "replicates": 1,
        "trial_count": len(final_units),
        "trial_units": final_units,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return plan


def materialize_phase_b_plan(
    harness_sha: Optional[str] = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Dict[str, Any]:
    """Materialize deterministic 56-unit Phase B execution plan."""
    return materialize_execution_plan(
        harness_sha=harness_sha,
        config_path=config_path,
        experiment_id=M13_PHASE_B_EXPERIMENT_ID,
    )


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

    exp_id = plan.get("experiment_id")
    is_phase_b = exp_id == M13_PHASE_B_EXPERIMENT_ID
    is_phase_a = exp_id == M13_EXPERIMENT_ID

    if not (is_phase_a or is_phase_b):
        errors.append(
            f"experiment_id mismatch: expected '{M13_EXPERIMENT_ID}' or "
            f"'{M13_PHASE_B_EXPERIMENT_ID}', found '{exp_id}'"
        )

    expected_plan_design = (
        M13_PHASE_B_PLAN_DESIGN if is_phase_b else M13_PLAN_DESIGN
    )
    if plan.get("plan_design") != expected_plan_design:
        errors.append(
            f"plan_design mismatch: expected {expected_plan_design}, "
            f"found {plan.get('plan_design')}"
        )

    expected_order_seed = (
        M13_PHASE_B_ORDER_SEED if is_phase_b else M13_ORDER_SEED
    )
    if plan.get("order_seed") != expected_order_seed:
        errors.append(
            f"order_seed mismatch: expected {expected_order_seed}, "
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

    expected_tasks_json = (
        FROZEN_PHASE_B_TASKS_JSON if is_phase_b else FROZEN_ANCHOR_TASKS_JSON
    )
    if plan.get("anchor_tasks") != expected_tasks_json:
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

    expected_exec_base = (
        M13_PHASE_B_EXECUTION_BASE_SHA
        if is_phase_b
        else M13_EXECUTION_BASE_SHA
    )
    try:
        verify_base_to_harness_delta(
            expected_exec_base, harness_sha
        )
    except Exception as e:
        errors.append(f"Base to harness delta error: {e}")

    expected_count = (
        M13_PHASE_B_TRIAL_COUNT if is_phase_b else 12
    )
    units = plan.get("trial_units", [])
    if (
        len(units) != expected_count
        or plan.get("trial_count") != expected_count
    ):
        errors.append(
            f"trial_count must be exactly {expected_count}, found {len(units)}"
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

    tasks_dict = FROZEN_PHASE_B_TASKS if is_phase_b else FROZEN_ANCHOR_TASKS
    trial_prefix = "m13_b" if is_phase_b else "m13"

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

        if task_id not in tasks_dict:
            errors.append(f"Unknown task_id: {task_id}")
        else:
            ft = tasks_dict[task_id]
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

        if cand_id in FROZEN_CANDIDATES and task_id in tasks_dict:
            exp_tid = (
                f"{trial_prefix}_{cand_id}_{tasks_dict[task_id].tier}_"
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
            expected_order_seed,
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


def summarize_cross_model_results(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute candidate x arm aggregates, paired outcomes, and overhead."""
    by_cand_arm: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_arm: Dict[str, Dict[str, Any]] = {}
    by_cand: Dict[str, Dict[str, Any]] = {}
    paired: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _init_bucket() -> Dict[str, Any]:
        return {
            "executed": 0,
            "passed": 0,
            "analyzable": 0,
            "infrastructure_excluded": 0,
            "generation_calls": 0,
            "total_tokens": 0,
            "wall_time": 0.0,
        }

    for r in records:
        cand_id = r["candidate_id"]
        arm = r["arm"]
        task_id = r["task_id"]
        passed = bool(r.get("passed", False))
        infra = bool(r.get("infrastructure_error", False))
        token_coverage = bool(r.get("token_coverage_complete", True))
        analyzable = (not infra) and token_coverage
        tokens = r.get("total_tokens") or 0
        gens = r.get("generation_call_count", 0)
        wall = r.get("wall_latency_seconds", 0.0)

        pair_key = (cand_id, task_id)
        if pair_key not in paired:
            paired[pair_key] = {}
        paired[pair_key][arm] = {
            "passed": passed,
            "failure_category": r.get("failure_category"),
            "tokens": tokens,
            "generation_calls": gens,
            "wall_latency_seconds": wall,
        }

        for k, d in (
            ((cand_id, arm), by_cand_arm),
            (arm, by_arm),
            (cand_id, by_cand),
        ):
            if k not in d:
                d[k] = _init_bucket()
            b = d[k]
            b["executed"] += 1
            if passed:
                b["passed"] += 1
            if analyzable:
                b["analyzable"] += 1
            if infra:
                b["infrastructure_excluded"] += 1
            b["generation_calls"] += gens
            b["total_tokens"] += tokens
            b["wall_time"] += wall

    return {
        "by_candidate_and_arm": {
            f"{c}_{a}": b for (c, a), b in sorted(by_cand_arm.items())
        },
        "by_arm": {a: b for a, b in sorted(by_arm.items())},
        "by_candidate": {c: b for c, b in sorted(by_cand.items())},
        "paired_task_outcomes": {
            f"{c}_{t}": arms for (c, t), arms in sorted(paired.items())
        },
        "total_records": len(records),
        "total_analyzable": sum(b["analyzable"] for b in by_arm.values()),
        "total_passed": sum(b["passed"] for b in by_arm.values()),
        "total_infrastructure_excluded": sum(
            b["infrastructure_excluded"] for b in by_arm.values()
        ),
        "total_generation_calls": sum(
            b["generation_calls"] for b in by_arm.values()
        ),
        "total_tokens": sum(b["total_tokens"] for b in by_arm.values()),
        "total_wall_time": round(
            sum(b["wall_time"] for b in by_arm.values()), 2
        ),
    }


def run_preflight(
    config_path: Path = DEFAULT_CONFIG_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    lock_path: Path = LOCK_FILE_PATH,
    lock_already_held: bool = False,
) -> Dict[str, Any]:
    if lock_already_held:
        return _run_preflight_body(config_path, contract_path)
    with SingleInstanceLock(lock_path):
        return _run_preflight_body(config_path, contract_path)


def _run_preflight_body(
    config_path: Path,
    contract_path: Path,
) -> Dict[str, Any]:
    blocking_reasons: List[str] = []

    harness_sha = get_current_git_sha()
    try:
        check_git_clean_except_prototype()
    except Exception as e:
        blocking_reasons.append(f"Git clean check failed: {e}")

    changed_paths: List[str] = []
    try:
        res = verify_base_to_harness_delta(
            M13_EXECUTION_BASE_SHA, harness_sha
        )
        if isinstance(res, list):
            changed_paths = res
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
        "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
        "execution_base_sha": M13_EXECUTION_BASE_SHA,
        "harness_sha": harness_sha,
        "execution_base_to_harness_changed_paths": changed_paths,
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
