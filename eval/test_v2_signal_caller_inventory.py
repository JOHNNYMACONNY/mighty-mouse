import ast
import json
from pathlib import Path
from unittest.mock import Mock

from mighty_mouse.v2.foundation import Mode, Scope, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle
from perpetual_loop import AutoresearchLoop


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "mcp" / "src",
)
EVAL_ROOT = REPO_ROOT / "eval"
TELEMETRY_IMPLEMENTATION = REPO_ROOT / "src/mighty_mouse/v2/telemetry.py"

CANONICAL_CALLERS = {
    "eval/perpetual_loop.py": ("SignalTelemetry",),
    "mcp/src/mighty_mouse_mcp/server.py": ("SignalTelemetry",),
    "src/mighty_mouse/commands/signals_cmd.py": ("SignalTelemetry",),
    "src/mighty_mouse/v2/engine.py": ("SignalTelemetry",),
}
COMPATIBILITY_TEST_CALLERS = {
    "eval/test_v2_signal_telemetry_canonical.py": ("SignalAggregator",),
    "eval/test_v2_telemetry.py": ("TelemetryAggregator",),
}
POLICY_COMPATIBILITY_SEAM = {
    "src/mighty_mouse/v2/policy.py": (
        "PolicyLifecycle.__init__.telemetry_aggregator",
        "PolicyLifecycle.determine_state.telemetry_aggregator.compute_pass_rate",
        "PolicyLifecycle.resolve_policy.telemetry_aggregator.compute_pass_rate",
        "policy.TYPE_CHECKING.TelemetryAggregator",
        "resolve_effective_policy.telemetry_aggregator",
    ),
}
CYCLE_SIGNAL_INTERFACE = {
    "eval/autoresearch_cycle.py": (
        "AutoresearchCycle.run.operations.record_signal",
        "AutoresearchCycleOperations.record_signal",
    ),
}
LIFECYCLE_OWNER_METHODS = (
    "compute_pass_rate",
    "get_signal_summary",
    "history",
)
LIFECYCLE_HISTORY_CONSUMERS = {
    "src/mighty_mouse/commands/signals_cmd.py": ("SignalLifecycle.history",),
    "src/mighty_mouse/v2/research.py": ("SignalLifecycle.history",),
    "src/mighty_mouse/v2/status.py": ("SignalLifecycle.history",),
}

_CANONICAL_QUALIFIED_NAMES = {
    "mighty_mouse.v2.SignalTelemetry",
    "mighty_mouse.v2.telemetry.SignalTelemetry",
}
_COMPATIBILITY_QUALIFIED_NAMES = {
    "mighty_mouse.v2.SignalAggregator",
    "mighty_mouse.v2.TelemetryAggregator",
    "mighty_mouse.v2.telemetry.SignalAggregator",
    "mighty_mouse.v2.telemetry.TelemetryAggregator",
}


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


def _file_module(path: Path) -> tuple[str, ...]:
    relative = path.relative_to(REPO_ROOT)
    if relative.parts[0] == "src":
        parts = relative.parts[1:]
    elif relative.parts[:2] == ("mcp", "src"):
        parts = relative.parts[2:]
    else:
        return ()
    package_parts = parts[:-1]
    if parts[-1] == "__init__.py":
        package_parts = parts[:-1]
    return tuple(Path(*package_parts).parts)


def _import_module(node: ast.ImportFrom, path: Path) -> str:
    if node.level == 0:
        return node.module or ""
    package = list(_file_module(path))
    package = package[: len(package) - (node.level - 1)]
    if node.module:
        package.extend(node.module.split("."))
    return ".".join(package)


def _bindings(tree: ast.AST, path: Path) -> tuple[dict[str, str], dict[str, str]]:
    symbols: dict[str, str] = {}
    modules: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = _import_module(node, path)
            if module not in {"mighty_mouse.v2", "mighty_mouse.v2.telemetry"}:
                continue
            for alias in node.names:
                if alias.name != "*":
                    symbols[alias.asname or alias.name] = f"{module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    modules[alias.asname] = alias.name
                else:
                    modules[alias.name.split(".")[0]] = alias.name.split(".")[0]

    def resolve(node: ast.AST) -> str | None:
        dotted = _dotted_name(node)
        if dotted is None:
            return None
        if isinstance(node, ast.Name):
            return symbols.get(node.id)
        root, _, suffix = dotted.partition(".")
        module = modules.get(root)
        if module is None:
            return None
        return f"{module}.{suffix}" if suffix else module

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            targets: list[ast.AST] = []
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            if value is None:
                continue
            qualified = resolve(value)
            if qualified is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and symbols.get(target.id) != qualified:
                    symbols[target.id] = qualified
                    changed = True

    return symbols, modules


def _call_names(path: Path, names: set[str]) -> tuple[str, ...]:
    tree = ast.parse(path.read_text())
    symbols, modules = _bindings(tree, path)

    def resolve(node: ast.AST) -> str | None:
        dotted = _dotted_name(node)
        if dotted is None:
            return None
        if isinstance(node, ast.Name):
            return symbols.get(node.id)
        root, _, suffix = dotted.partition(".")
        module = modules.get(root)
        return f"{module}.{suffix}" if module and suffix else module

    qualified_to_name = {
        **{qualified: "SignalTelemetry" for qualified in _CANONICAL_QUALIFIED_NAMES},
        **{
            qualified: name
            for qualified in _COMPATIBILITY_QUALIFIED_NAMES
            for name in ("SignalAggregator", "TelemetryAggregator")
            if qualified.endswith(f".{name}")
        },
    }
    calls = {
        qualified_to_name[qualified]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (qualified := resolve(node.func)) in qualified_to_name
        and qualified_to_name[qualified] in names
    }
    return tuple(sorted(calls))


def _python_files() -> list[Path]:
    files = [
        path
        for root in RUNTIME_ROOTS
        for path in root.rglob("*.py")
    ]
    # Keep eval inventory bounded to supported top-level harness modules and
    # tests. pyproject excludes eval/local_model_pilot from pytest collection.
    files.extend(EVAL_ROOT.glob("*.py"))
    return sorted(
        {
            path
            for path in files
            if not path.name.startswith(("._", ".___"))
        }
    )


def _runtime_files() -> list[Path]:
    return [
        path
        for path in _python_files()
        if not path.name.startswith("test_")
        and path != TELEMETRY_IMPLEMENTATION
    ]


def _caller_inventory(
    names: set[str], *, tests: bool
) -> dict[str, tuple[str, ...]]:
    return {
        str(path.relative_to(REPO_ROOT)): calls
        for path in _python_files()
        if path.name.startswith("test_") == tests
        if path != TELEMETRY_IMPLEMENTATION
        and (calls := _call_names(path, names))
    }


def _class_method_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        method.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == class_name
        for method in node.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _policy_seam_inventory() -> dict[str, tuple[str, ...]]:
    path = REPO_ROOT / "src/mighty_mouse/v2/policy.py"
    tree = ast.parse(path.read_text())
    entries: set[str] = set()
    policy_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PolicyLifecycle"
    )
    for method in policy_class.body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if method.name == "__init__":
            if any(arg.arg == "telemetry_aggregator" for arg in method.args.args):
                entries.add("PolicyLifecycle.__init__.telemetry_aggregator")
        if method.name in {"determine_state", "resolve_policy"}:
            if any(
                isinstance(node, ast.Call)
                and _dotted_name(node.func)
                == "self.telemetry_aggregator.compute_pass_rate"
                for node in ast.walk(method)
            ):
                entries.add(
                    f"PolicyLifecycle.{method.name}.telemetry_aggregator.compute_pass_rate"
                )
    resolver = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "resolve_effective_policy"
    )
    if any(arg.arg == "telemetry_aggregator" for arg in resolver.args.args):
        entries.add("resolve_effective_policy.telemetry_aggregator")
    if any(
        isinstance(node, ast.ImportFrom)
        and _import_module(node, path) == "mighty_mouse.v2.telemetry"
        and any(alias.name == "TelemetryAggregator" for alias in node.names)
        for node in ast.walk(tree)
    ):
        entries.add("policy.TYPE_CHECKING.TelemetryAggregator")
    return {"src/mighty_mouse/v2/policy.py": tuple(sorted(entries))}


def _cycle_signal_inventory() -> dict[str, tuple[str, ...]]:
    path = REPO_ROOT / "eval/autoresearch_cycle.py"
    tree = ast.parse(path.read_text())
    entries: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name == "AutoresearchCycleOperations":
            if "record_signal" in {
                method.name
                for method in node.body
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
            }:
                entries.add("AutoresearchCycleOperations.record_signal")
        if node.name == "AutoresearchCycle":
            run_method = next(
                method
                for method in node.body
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                and method.name == "run"
            )
            if any(
                isinstance(call, ast.Call)
                and _dotted_name(call.func) == "self.operations.record_signal"
                for call in ast.walk(run_method)
            ):
                entries.add("AutoresearchCycle.run.operations.record_signal")
    return {"eval/autoresearch_cycle.py": tuple(sorted(entries))}


def _direct_history_consumers() -> dict[str, tuple[str, ...]]:
    consumers: dict[str, tuple[str, ...]] = {}
    for path in _runtime_files():
        tree = ast.parse(path.read_text())
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "history"
            for node in ast.walk(tree)
        ):
            consumers[str(path.relative_to(REPO_ROOT))] = ("SignalLifecycle.history",)
    return consumers


def _inventory_scope() -> Scope:
    return Scope(
        mode=Mode.AGENTIC,
        repository="JOHNNYMACONNY/mighty-mouse",
        task_category=TaskCategory.MAINTENANCE,
        model_class="local-small",
    )


def test_supported_signal_callers_use_canonical_telemetry() -> None:
    assert _caller_inventory({"SignalTelemetry"}, tests=False) == CANONICAL_CALLERS


def test_compatibility_facade_constructors_remain_test_only() -> None:
    assert _caller_inventory(
        {"SignalAggregator", "TelemetryAggregator"}, tests=True
    ) == COMPATIBILITY_TEST_CALLERS


def test_runtime_inventory_excludes_compatibility_implementation() -> None:
    assert all(
        not _call_names(path, {"SignalAggregator", "TelemetryAggregator"})
        for path in _runtime_files()
    )


def test_inventory_resolves_aliases_and_module_provenance(tmp_path: Path) -> None:
    path = tmp_path / "caller.py"
    path.write_text(
        "\n".join(
            (
                "from mighty_mouse.v2.telemetry import SignalTelemetry as CanonicalSignal",
                "import mighty_mouse.v2.telemetry as telemetry_module",
                "from unrelated_module import SignalTelemetry",
                "CanonicalSignal()",
                "telemetry_module.SignalTelemetry()",
                "SignalTelemetry()",
            )
        )
    )

    assert _call_names(path, {"SignalTelemetry"}) == ("SignalTelemetry",)


def test_policy_compatibility_seam_is_explicitly_inventoried() -> None:
    assert _policy_seam_inventory() == POLICY_COMPATIBILITY_SEAM


def test_autoresearch_cycle_signal_interface_is_inventoried() -> None:
    assert _cycle_signal_inventory() == CYCLE_SIGNAL_INTERFACE


def test_signal_lifecycle_owns_history_projection_without_direct_consumers() -> None:
    lifecycle_path = REPO_ROOT / "src/mighty_mouse/v2/signals.py"
    assert set(LIFECYCLE_OWNER_METHODS).issubset(
        _class_method_names(lifecycle_path, "SignalLifecycle")
    )
    assert _direct_history_consumers() == LIFECYCLE_HISTORY_CONSUMERS


def test_evaluator_metrics_and_v2_signal_receipts_stay_separate(tmp_path: Path) -> None:
    metric_path = tmp_path / "metric_telemetry.json"
    state_dir = tmp_path / "v2-state"
    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(metric_path),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(state_dir),
    )

    loop.record_signal(
        scope=_inventory_scope(), outcome="passed", signal_counter=1
    )
    assert not metric_path.exists()

    receipt_path = next(state_dir.joinpath(SignalLifecycle.receipt_directory).glob("*.json"))
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    assert set(receipt) == {"schema_version", "recorded_at", "signal", "receipt_hash"}
    assert receipt["schema_version"] == SignalLifecycle.schema_version

    loop.update_telemetry(
        "tier-1",
        {
            "success_rate": "1/1",
            "first_pass_rate": "1/1",
            "avg_latency_sec": 0.5,
            "total_tokens": 10,
        },
        "config-hash",
    )
    metric_entry = json.loads(metric_path.read_text())[-1]
    assert set(metric_entry) == {
        "timestamp",
        "tier",
        "config_hash",
        "success_rate",
        "first_pass_rate",
        "avg_latency",
        "total_tokens",
    }
    assert metric_entry["tier"] == "tier-1"
    assert not {"schema_version", "receipt_hash", "signal"} & set(metric_entry)
    assert receipt_path.read_bytes() == receipt_bytes
