"""Bounded tool-using runtime for the local-model capability study.

The runtime deliberately keeps model access separate from workspace tools so
every study condition can receive the same tools and budget. It is
experimental and must not be presented as evidence until a prospective study
protocol is frozen and completed.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

@dataclass(frozen=True)
class AgentBudget:
    max_turns: int = 20
    max_tool_calls: int = 40
    max_wall_seconds: int = 900
    max_output_tokens_per_turn: int = 4_000
    context_tokens: int = 32_768

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")


class ChatClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        timeout_seconds: float,
        output_tokens: int,
        context_tokens: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...


class OllamaChatClient:
    """Small `/api/chat` client with deterministic study settings."""

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        *,
        temperature: float = 0.1,
        seed: int = 7,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.seed = seed

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        timeout_seconds: float,
        output_tokens: int,
        context_tokens: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "seed": self.seed,
                "num_predict": output_tokens,
                "num_ctx": context_tokens,
            },
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=max(1, timeout_seconds)) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama returned HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Unable to reach Ollama at {self.host}: {error}") from error

        message = result.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama response did not contain a chat message")
        metrics = {
            "model": result.get("model", self.model),
            "prompt_tokens": int(result.get("prompt_eval_count") or 0),
            "completion_tokens": int(result.get("eval_count") or 0),
            "wall_seconds": time.monotonic() - started,
            "load_duration_ns": int(result.get("load_duration") or 0),
            "prompt_eval_duration_ns": int(result.get("prompt_eval_duration") or 0),
            "eval_duration_ns": int(result.get("eval_duration") or 0),
        }
        return message, metrics


def _tool_definition(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_DEFINITIONS = [
    _tool_definition(
        "list_files",
        "List files beneath a workspace-relative directory.",
        {"path": {"type": "string", "description": "Relative directory; use '.' for the workspace root."}},
        ["path"],
    ),
    _tool_definition(
        "read_file",
        "Read a bounded UTF-8 slice of a workspace file.",
        {
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20000},
        },
        ["path"],
    ),
    _tool_definition(
        "search_text",
        "Search workspace text files for a literal string.",
        {"query": {"type": "string"}, "path": {"type": "string"}},
        ["query"],
    ),
    _tool_definition(
        "write_file",
        "Create or replace one allowed workspace file with complete UTF-8 content.",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _tool_definition(
        "run_check",
        "Run one allowlisted project check by its identifier.",
        {"check_id": {"type": "string"}},
        ["check_id"],
    ),
    _tool_definition(
        "finish",
        "Stop work and summarize the result. This does not override acceptance checks.",
        {"summary": {"type": "string"}},
        ["summary"],
    ),
]


LOCAL_STUDY_PROTOCOL = """Mighty Mouse local-agent protocol:
1. Inspect the relevant repository files before editing.
2. Identify the narrowest root cause and keep changes inside the declared write scope.
3. Do not alter tests or check configuration unless those paths are explicitly writable.
4. Implement the smallest complete fix, then run the relevant allowlisted checks by their exact identifiers.
5. If a check fails, use its real output to make a bounded correction and rerun it while budget remains.
6. Never claim success from reasoning alone. Call finish only after checks pass, or state the unresolved blocker accurately.
"""


def build_tool_definitions(allowed_paths: list[str], checks: dict[str, list[str]]) -> list[dict[str, Any]]:
    definitions = deepcopy(TOOL_DEFINITIONS)
    for definition in definitions:
        function = definition["function"]
        if function["name"] == "write_file":
            function["description"] += f" Writable paths: {', '.join(allowed_paths)}."
        elif function["name"] == "run_check":
            function["parameters"]["properties"]["check_id"]["enum"] = sorted(checks)
            function["description"] += f" Available check identifiers: {', '.join(sorted(checks))}."
    return definitions


class WorkspaceTools:
    def __init__(
        self,
        workspace: Path,
        *,
        allowed_paths: list[str],
        checks: dict[str, list[str]],
        command_timeout_seconds: int,
        max_file_bytes: int = 100_000,
    ) -> None:
        self.workspace = workspace.resolve()
        self.allowed_paths = tuple(self._normalize_allowed(path) for path in allowed_paths)
        self.checks = checks
        self.command_timeout_seconds = command_timeout_seconds
        self.max_file_bytes = max_file_bytes

    @staticmethod
    def _normalize_allowed(path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Invalid allowed path: {path}")
        normalized = candidate.as_posix()
        if normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized or normalized == ".":
            raise ValueError(f"Invalid allowed path: {path}")
        return normalized.rstrip("/")

    def _resolve(self, path: str, *, must_exist: bool = False) -> tuple[str, Path]:
        if not isinstance(path, str) or not path.strip() or Path(path).is_absolute():
            raise ValueError("Tool paths must be non-empty and workspace-relative")
        candidate = (self.workspace / path).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise ValueError(f"Path escapes workspace: {path}")
        relative = candidate.relative_to(self.workspace).as_posix()
        if must_exist and not candidate.exists():
            raise FileNotFoundError(relative)
        return relative, candidate

    def _write_allowed(self, relative: str) -> bool:
        return any(relative == allowed or relative.startswith(f"{allowed}/") for allowed in self.allowed_paths)

    def list_files(self, path: str = ".") -> dict[str, Any]:
        _, target = self._resolve(path, must_exist=True)
        if not target.is_dir():
            raise NotADirectoryError(path)
        files = []
        for item in sorted(target.rglob("*")):
            if not item.is_file() or ".git" in item.parts:
                continue
            resolved = item.resolve()
            if resolved != self.workspace and self.workspace not in resolved.parents:
                continue
            files.append(item.relative_to(self.workspace).as_posix())
            if len(files) >= 500:
                return {"files": files, "truncated": True}
        return {"files": files, "truncated": False}

    def read_file(self, path: str, offset: int = 0, limit: int = 20_000) -> dict[str, Any]:
        relative, target = self._resolve(path, must_exist=True)
        if not target.is_file():
            raise IsADirectoryError(relative)
        offset = max(0, int(offset))
        limit = min(20_000, max(1, int(limit)))
        content = target.read_text(encoding="utf-8", errors="replace")
        return {
            "path": relative,
            "content": content[offset : offset + limit],
            "offset": offset,
            "truncated": offset + limit < len(content),
            "total_characters": len(content),
        }

    def search_text(self, query: str, path: str = ".") -> dict[str, Any]:
        if not isinstance(query, str) or not query:
            raise ValueError("Search query must be non-empty")
        _, target = self._resolve(path, must_exist=True)
        candidates = [target] if target.is_file() else sorted(target.rglob("*"))
        matches = []
        for candidate in candidates:
            if not candidate.is_file() or ".git" in candidate.parts or candidate.stat().st_size > self.max_file_bytes:
                continue
            resolved = candidate.resolve()
            if resolved != self.workspace and self.workspace not in resolved.parents:
                continue
            for line_number, line in enumerate(candidate.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if query in line:
                    matches.append({
                        "path": candidate.relative_to(self.workspace).as_posix(),
                        "line": line_number,
                        "text": line[:500],
                    })
                    if len(matches) >= 100:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        relative, target = self._resolve(path)
        if not self._write_allowed(relative):
            raise PermissionError(f"Write outside allowed paths: {relative}")
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_file_bytes:
            raise ValueError(f"File exceeds {self.max_file_bytes} bytes: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return {"path": relative, "bytes_written": len(encoded)}

    def run_check(self, check_id: str) -> dict[str, Any]:
        argv = self.checks.get(check_id)
        if not argv or not all(isinstance(part, str) and part for part in argv):
            raise ValueError(f"Unknown check_id: {check_id}")
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
                check=False,
            )
            return {
                "check_id": check_id,
                "passed": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-12_000:],
                "stderr": completed.stderr[-12_000:],
                "duration_seconds": time.monotonic() - started,
            }
        except subprocess.TimeoutExpired as error:
            return {
                "check_id": check_id,
                "passed": False,
                "timed_out": True,
                "stdout": (error.stdout or "")[-12_000:] if isinstance(error.stdout, str) else "",
                "stderr": (error.stderr or "")[-12_000:] if isinstance(error.stderr, str) else "",
                "duration_seconds": time.monotonic() - started,
            }

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "list_files":
            return self.list_files(**arguments)
        if name == "read_file":
            return self.read_file(**arguments)
        if name == "search_text":
            return self.search_text(**arguments)
        if name == "write_file":
            return self.write_file(**arguments)
        if name == "run_check":
            return self.run_check(**arguments)
        if name == "finish":
            return {"finished": True, "summary": str(arguments.get("summary", ""))}
        raise ValueError(f"Unknown tool: {name}")


def _normalize_relative_prefix(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Invalid workspace-relative prefix: {path}")
    normalized = candidate.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized == ".":
        raise ValueError(f"Invalid workspace-relative prefix: {path}")
    return normalized.rstrip("/")


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def _hash_workspace(workspace: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        resolved = path.resolve()
        if resolved != workspace and workspace not in resolved.parents:
            continue
        hashes[path.relative_to(workspace).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _condition_system_prompt(
    condition: str,
    complexity: str,
    allowed_paths: list[str],
    check_ids: list[str],
) -> str:
    shared = (
        "You are operating in a disposable repository workspace. Use the provided tools to inspect the actual files, "
        "make only task-relevant changes, run project checks, and finish with a concise factual summary. "
        "Never invent tool results or access paths outside the workspace.\n"
        f"Writable paths: {', '.join(allowed_paths)}.\n"
        f"Available check identifiers: {', '.join(check_ids)}."
    )
    if condition == "gemma_mighty_mouse":
        return f"{shared}\n\nComplexity: {complexity}.\n\n{LOCAL_STUDY_PROTOCOL}"
    if condition in {"gemma_raw", "reference_raw"}:
        return shared
    raise ValueError(f"Unsupported condition: {condition}")


def _normalize_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function") or {}
    name = function.get("name")
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(name, str) or not isinstance(arguments, dict):
        raise ValueError("Malformed tool call")
    return name, arguments


def run_agent_condition(
    client: ChatClient,
    workspace: Path,
    task: dict[str, Any],
    *,
    condition: str,
    budget: AgentBudget,
) -> dict[str, Any]:
    """Run one study condition and return a complete machine-readable record."""

    required = {"id", "description", "complexity", "allowed_paths", "checks"}
    missing = sorted(required - task.keys())
    if missing:
        raise ValueError(f"Task is missing required fields: {', '.join(missing)}")
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError(f"Workspace is not a directory: {workspace}")

    tools = WorkspaceTools(
        workspace,
        allowed_paths=list(task["allowed_paths"]),
        checks=dict(task["checks"]),
        command_timeout_seconds=min(int(task.get("check_timeout_seconds", 120)), budget.max_wall_seconds),
    )
    before = _hash_workspace(workspace)
    ignored_paths = tuple(_normalize_relative_prefix(path) for path in task.get("ignored_paths", []))
    started = time.monotonic()
    tool_definitions = build_tool_definitions(list(task["allowed_paths"]), dict(task["checks"]))
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": _condition_system_prompt(
                condition,
                str(task["complexity"]),
                list(task["allowed_paths"]),
                sorted(task["checks"]),
            ),
        },
        {"role": "user", "content": str(task["description"])},
    ]
    events = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "model_seconds": 0.0}
    finish_summary = ""
    stop_reason = "turn_budget_exhausted"
    turn = 0
    tool_calls = 0

    while turn < budget.max_turns:
        elapsed = time.monotonic() - started
        if elapsed >= budget.max_wall_seconds:
            stop_reason = "wall_time_exhausted"
            break
        turn += 1
        message, metrics = client.chat(
            messages,
            tool_definitions,
            timeout_seconds=budget.max_wall_seconds - elapsed,
            output_tokens=budget.max_output_tokens_per_turn,
            context_tokens=budget.context_tokens,
        )
        messages.append(message)
        usage["prompt_tokens"] += int(metrics.get("prompt_tokens") or 0)
        usage["completion_tokens"] += int(metrics.get("completion_tokens") or 0)
        usage["model_seconds"] += float(metrics.get("wall_seconds") or 0)
        calls = message.get("tool_calls") or []
        events.append({"type": "model_turn", "turn": turn, "message": message, "metrics": metrics})
        if not calls:
            messages.append({
                "role": "user",
                "content": "Use the available tools to continue, or call finish when the task is complete.",
            })
            continue

        finished = False
        for call in calls:
            if tool_calls >= budget.max_tool_calls:
                stop_reason = "tool_budget_exhausted"
                finished = True
                break
            tool_calls += 1
            arguments: dict[str, Any] = {}
            try:
                name, arguments = _normalize_tool_call(call)
                result = tools.execute(name, arguments)
                ok = True
            except Exception as error:  # Tool errors are evidence and feedback, not runner crashes.
                name = (call.get("function") or {}).get("name", "unknown")
                result = {"error": type(error).__name__, "message": str(error)}
                ok = False
            events.append({
                "type": "tool_call",
                "turn": turn,
                "tool": name,
                "arguments": arguments,
                "ok": ok,
                "result": result,
            })
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, sort_keys=True)})
            if name == "finish" and ok:
                finish_summary = str(result.get("summary", ""))
                stop_reason = "model_finished"
                finished = True
                break
        if finished:
            break

    acceptance = {check_id: tools.run_check(check_id) for check_id in task["checks"]}
    after = _hash_workspace(workspace)
    all_changed_paths = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    generated_paths = sorted(path for path in all_changed_paths if _matches_prefix(path, ignored_paths))
    changed_paths = sorted(path for path in all_changed_paths if not _matches_prefix(path, ignored_paths))
    disallowed_changes = sorted(path for path in changed_paths if not tools._write_allowed(path))
    passed = bool(acceptance) and all(result.get("passed") for result in acceptance.values()) and not disallowed_changes
    return {
        "schema_version": 1,
        "task_id": task["id"],
        "condition": condition,
        "model": client.model,
        "budget": asdict(budget),
        "passed": passed,
        "stop_reason": stop_reason,
        "finish_summary": finish_summary,
        "turns": turn,
        "tool_calls": tool_calls,
        "duration_seconds": time.monotonic() - started,
        "usage": {
            **usage,
            "total_tokens": usage["prompt_tokens"] + usage["completion_tokens"],
        },
        "changed_paths": changed_paths,
        "ignored_generated_paths": generated_paths,
        "disallowed_changes": disallowed_changes,
        "acceptance": acceptance,
        "events": events,
    }
