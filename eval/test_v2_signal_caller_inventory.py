import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "mcp" / "src",
    REPO_ROOT / "eval",
)
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


def _call_names(path: Path, names: set[str]) -> tuple[str, ...]:
    tree = ast.parse(path.read_text())
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in names
    }
    return tuple(sorted(calls))


def _runtime_files() -> list[Path]:
    files = []
    for root in RUNTIME_ROOTS:
        files.extend(root.rglob("*.py"))
    return sorted(
        path
        for path in files
        if not path.name.startswith(("._", ".___"))
        if not path.name.startswith("test_")
        and path != REPO_ROOT / "src/mighty_mouse/v2/telemetry.py"
    )


def _caller_inventory(
    names: set[str], *, tests: bool
) -> dict[str, tuple[str, ...]]:
    paths = []
    for root in RUNTIME_ROOTS:
        paths.extend(root.rglob("*.py"))
    return {
        str(path.relative_to(REPO_ROOT)): calls
        for path in sorted(paths)
        if not path.name.startswith(("._", ".___"))
        if path.name.startswith("test_") == tests
        if path != REPO_ROOT / "src/mighty_mouse/v2/telemetry.py"
        and (calls := _call_names(path, names))
    }


def test_supported_signal_callers_use_canonical_telemetry() -> None:
    assert _caller_inventory(
        {"SignalTelemetry"}, tests=False
    ) == CANONICAL_CALLERS


def test_compatibility_facade_constructors_remain_test_only() -> None:
    assert _caller_inventory(
        {"SignalAggregator", "TelemetryAggregator"}, tests=True
    ) == COMPATIBILITY_TEST_CALLERS


def test_runtime_inventory_excludes_compatibility_implementation() -> None:
    assert all(
        not _call_names(path, {"SignalAggregator", "TelemetryAggregator"})
        for path in _runtime_files()
    )
