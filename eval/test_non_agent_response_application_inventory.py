import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "mcp" / "src",
)
EVAL_ROOT = REPO_ROOT / "eval"
RESPONSE_PARSER_IMPLEMENTATION = (
    REPO_ROOT / "src/mighty_mouse/orchestrator/response_parser.py"
)

SUPPORTED_NON_AGENT_CALLERS = {
    "eval/autoresearch_harness.py": ("apply_response",),
    "eval/run_bare_baseline.py": ("apply_response",),
    # Deprecated evaluator remains executable and stays on canonical path
    # until its retirement receives a separate disposition.
    "eval/run_decomposed.py": ("apply_response",),
    "eval/run_decomposed_v2.py": ("apply_response",),
    "src/mighty_mouse/orchestrator/swarm.py": ("apply_response",),
}
AGENT_CALLERS = {
    "src/mighty_mouse/orchestrator/mighty_mouse_agent.py": ("apply_response",),
}


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


def _python_files() -> list[Path]:
    files = [
        path
        for root in RUNTIME_ROOTS
        for path in root.rglob("*.py")
    ]
    files.extend(EVAL_ROOT.glob("*.py"))
    return sorted(
        {
            path
            for path in files
            if not path.name.startswith(("._", ".___"))
            and not path.name.startswith("test_")
        }
    )


def _call_names(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text())
    return tuple(
        sorted(
            {
                name
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and (name := _dotted_name(node.func)) is not None
            }
        )
    )


def _caller_inventory(name: str) -> dict[str, tuple[str, ...]]:
    return {
        str(path.relative_to(REPO_ROOT)): (name,)
        for path in _python_files()
        if path != RESPONSE_PARSER_IMPLEMENTATION
        if name in _call_names(path)
    }


def test_supported_non_agent_callers_use_response_application_boundary() -> None:
    assert _caller_inventory("apply_response") == {
        **SUPPORTED_NON_AGENT_CALLERS,
        **AGENT_CALLERS,
    }


def test_supported_non_agent_callers_have_explicit_inventory() -> None:
    assert {
        path: calls
        for path, calls in _caller_inventory("apply_response").items()
        if path not in AGENT_CALLERS
    } == SUPPORTED_NON_AGENT_CALLERS


def test_no_supported_runtime_caller_uses_response_parser_directly() -> None:
    direct_parser_callers = {
        str(path.relative_to(REPO_ROOT)): calls
        for path in _python_files()
        if path != RESPONSE_PARSER_IMPLEMENTATION
        if (calls := tuple(
            name
            for name in _call_names(path)
            if name == "ResponseParser.parse_and_write"
        ))
    }

    assert direct_parser_callers == {}
