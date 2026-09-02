#!/usr/bin/env python3
"""Thin repository-owned PreToolUse entrypoint for Antigravity.

Delegates composition directly to canonical MCP-side
run_antigravity_composite_pre_tool_use with Delivery Guard check_tool_call
as the authoritative pre-action gate.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure current script dir, .agents/scripts, src, and mcp/src are in sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = (
    _SCRIPT_DIR.parent.parent
    if _SCRIPT_DIR.name == "scripts" and _SCRIPT_DIR.parent.name == ".agents"
    else _SCRIPT_DIR.parent
)

for _p in [
    str(_SCRIPT_DIR),
    str(_REPO_ROOT / ".agents" / "scripts"),
    str(_REPO_ROOT / "scripts"),
    str(_REPO_ROOT / "src"),
    str(_REPO_ROOT / "mcp" / "src"),
]:
    if _p not in sys.path and Path(_p).exists():
        sys.path.insert(0, _p)

try:
    from delivery_guard import (  # type: ignore # noqa: E402
        check_tool_call as _guard_checker,
    )
except Exception:
    _guard_checker = None


def main() -> None:
    try:
        raw_input = sys.stdin.read()
    except Exception:
        raw_input = ""

    try:
        from mighty_mouse_mcp.antigravity_hooks import (  # noqa: E402
            run_antigravity_composite_pre_tool_use,
        )

        result = run_antigravity_composite_pre_tool_use(
            raw_input,
            guard_checker=_guard_checker,
        )
    except Exception:
        result = {
            "decision": "deny",
            "reason": "Composite PreToolUse runtime failure",
        }

    sys.stdout.write(json.dumps(result, sort_keys=True) + chr(10))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
