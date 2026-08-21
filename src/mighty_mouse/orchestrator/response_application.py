"""Response application boundary for parsed model output.

This module owns the response-application request seam while the existing
``ResponseParser`` remains the compatibility implementation.  Agent
Execution must receive only a fully bound callable adapter built from this
boundary; parser policy stays outside Agent Execution.
"""

from __future__ import annotations

import os
import posixpath
import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseApplicationPolicy:
    """Application policy preserved from the legacy parser contract."""

    workspace_root: str
    allowed_delete_paths: tuple[str, ...] = ()
    max_file_bytes: int = 100_000
    system_mode: bool = False
    strict_code_hygiene: bool = False


@dataclass(frozen=True)
class ResponseApplicationRequest:
    """One raw response plus its composition-root-bound application policy."""

    raw_response: str
    policy: ResponseApplicationPolicy


def _resolve_target_path(path: str, workspace_root: str) -> tuple[str, str]:
    if not path:
        raise ValueError("Missing target path")

    path = path.strip()
    if os.path.isabs(path):
        raise ValueError(f"Absolute paths are not allowed: {path}")
    if ".." in path.split(os.sep):
        raise ValueError(f"Parent traversal is not allowed: {path}")

    workspace_root = os.path.abspath(workspace_root or os.getcwd())
    target_path = os.path.abspath(os.path.join(workspace_root, path))
    if target_path != workspace_root and not target_path.startswith(
        workspace_root + os.sep
    ):
        raise ValueError(f"Resolved path escapes workspace: {path}")

    canonical_workspace_root = os.path.realpath(workspace_root)
    canonical_target_path = os.path.realpath(target_path)
    if (
        canonical_target_path != canonical_workspace_root
        and not canonical_target_path.startswith(
            canonical_workspace_root + os.sep
        )
    ):
        raise ValueError(f"Resolved path escapes workspace: {path}")

    return path, target_path


@dataclass(frozen=True)
class PlannedOperation:
    """A single validated filesystem operation from a model response."""

    kind: str  # "write" | "delete"
    path: str
    target_path: str
    content: str = ""


@dataclass(frozen=True)
class ResponsePlan:
    """Immutable plan of operations derived from a raw response."""

    raw_response: str
    operations: tuple[PlannedOperation, ...]

    @property
    def output_paths(self) -> tuple[str, ...]:
        return tuple(
            op.path
            for op in self.operations
            if op.path.lower() != "checklist.md"
        )

    def canonical_representation(self) -> str:
        """Deterministic canonical representation of planned operations."""
        lines: list[str] = []
        for op in self.operations:
            lines.append(f"OP:{op.kind}:{op.path}")
            if op.kind == "write":
                size = len(op.content.encode("utf-8"))
                lines.append(f"CONTENT_BYTES:{size}")
                lines.append(op.content)
        return "\n".join(lines)


def plan_response(request: ResponseApplicationRequest) -> ResponsePlan:
    """Pure, non-mutating planning and validation of model responses.

    Performs full parsing, syntax validation, path resolution, deletion checks,
    size limits, and hygiene checks without writing or deleting any files.
    """
    raw_text = request.raw_response
    policy = request.policy
    workspace_root = os.path.abspath(policy.workspace_root or os.getcwd())
    allowed_delete_paths = {
        path.strip()
        for path in (policy.allowed_delete_paths or [])
        if path and path.strip()
    }

    operations: list[PlannedOperation] = []

    checklist_match = re.search(
        r"# Mighty Mouse Checklist.*?(?=```|$)",
        raw_text,
        re.DOTALL | re.IGNORECASE,
    )
    if checklist_match:
        checklist_content = checklist_match.group(0).strip() + "\n"
        path, checklist_path = _resolve_target_path(
            "CHECKLIST.md",
            workspace_root,
        )
        operations.append(
            PlannedOperation(
                kind="write",
                path=path,
                target_path=checklist_path,
                content=checklist_content,
            )
        )

    file_blocks = re.finditer(
        r"```(?P<lang>\w+)?"
        r"(?:\s*:\s*(?P<path>[^\n\s]+))?.*?\n"
        r"(?P<content>.*?)"
        r"(?:\n\s*```|\s*```)",
        raw_text,
        re.DOTALL,
    )

    for block in file_blocks:
        path = block.group("path")
        content = block.group("content")
        start_pos = block.start()

        # Fallback: pre-fence sniffing for legacy response formats.
        if not path:
            preceding_text = raw_text[:start_pos].strip().split("\n")[-3:]
            candidates = []
            for line in preceding_text:
                match = re.search(
                    r"(?:File|Target):\s*([^\n\s]+)", line, re.IGNORECASE
                )
                if match:
                    candidates.append(match.group(1))

            if len(set(candidates)) == 1:
                path = candidates[0]
            elif len(set(candidates)) > 1:
                raise ValueError(
                    "Ambiguous file targets found in pre-fence hint: "
                    f"{candidates}"
                )

        # Fallback: first-line comment sniffing for the legacy format.
        if not path:
            lines = content.split("\n")
            for line in lines:
                if not line.strip():
                    continue
                first_line = line.strip()
                if first_line.startswith("#") or first_line.startswith("//"):
                    potential = first_line.lstrip("#/ ").strip()
                    if "." in potential and len(potential.split()) == 1:
                        path = potential
                break

        if not path:
            continue

        is_delete = (block.group("lang") == "delete")
        if path.startswith("delete:"):
            is_delete = True
            path = path[7:].strip()

        path, target_path = _resolve_target_path(path, workspace_root)

        if path.lower() == "checklist.md":
            continue

        # Harness protection: block .mighty/ unless system mode allows it.
        if not policy.system_mode:
            norm_path = posixpath.normpath(path.replace("\\", "/"))
            if norm_path == ".mighty" or norm_path.startswith(".mighty/"):
                print(
                    f"[parser] REJECTED system path: {path}",
                    file=sys.stderr,
                )
                continue

        if len(content.encode("utf-8")) > policy.max_file_bytes:
            raise ValueError(f"Refusing oversized file block for {path}")

        if is_delete:
            if path not in allowed_delete_paths:
                raise ValueError(f"Deletion not permitted for path: {path}")
            operations.append(
                PlannedOperation(
                    kind="delete",
                    path=path,
                    target_path=target_path,
                )
            )
            continue

        if policy.strict_code_hygiene:
            leakage_patterns = [
                r"</thought>",
                r"</act>",
                r"</mighty>",
                r"</context_audit>",
                r"</adversarial_red_team>",
                r"</adversarial_plan>",
                r"</verify>",
                r"</xml>",
            ]
            for pattern in leakage_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    raise ValueError(
                        f"XML leakage detected in {path}: "
                        f"Found hallucinated tag {pattern}"
                    )

        operations.append(
            PlannedOperation(
                kind="write",
                path=path,
                target_path=target_path,
                content=content,
            )
        )

    return ResponsePlan(raw_response=raw_text, operations=tuple(operations))


def _apply_response_text(
    raw_text: str, policy: ResponseApplicationPolicy
) -> list[str]:
    """Own response parse, validation, authorization, and application order.

    ResponseParser delegates here as a public compatibility shim.
    """
    print(
        f"[parser] Processing response (Length: {len(raw_text)})",
        file=sys.stderr,
    )
    workspace_root = os.path.abspath(policy.workspace_root or os.getcwd())
    allowed_delete_paths = {
        path.strip()
        for path in (policy.allowed_delete_paths or [])
        if path and path.strip()
    }

    checklist_match = re.search(
        r"# Mighty Mouse Checklist.*?(?=```|$)",
        raw_text,
        re.DOTALL | re.IGNORECASE,
    )
    if checklist_match:
        checklist_content = checklist_match.group(0).strip()
        _, checklist_path = _resolve_target_path(
            "CHECKLIST.md",
            workspace_root,
        )
        with open(checklist_path, "w") as checklist_file:
            checklist_file.write(checklist_content)
            checklist_file.write("\n")
        print("[parser] Wrote CHECKLIST.md", file=sys.stderr)

    file_blocks = re.finditer(
        r"```(?P<lang>\w+)?"
        r"(?:\s*:\s*(?P<path>[^\n\s]+))?.*?\n"
        r"(?P<content>.*?)"
        r"(?:\n\s*```|\s*```)",
        raw_text,
        re.DOTALL,
    )

    extracted_files = []
    for block in file_blocks:
        path = block.group("path")
        content = block.group("content")
        start_pos = block.start()

        # Fallback: pre-fence sniffing for legacy response formats.
        if not path:
            preceding_text = raw_text[:start_pos].strip().split("\n")[-3:]
            candidates = []
            for line in preceding_text:
                match = re.search(
                    r"(?:File|Target):\s*([^\n\s]+)", line, re.IGNORECASE
                )
                if match:
                    candidates.append(match.group(1))

            if len(set(candidates)) == 1:
                path = candidates[0]
            elif len(set(candidates)) > 1:
                raise ValueError(
                    "Ambiguous file targets found in pre-fence hint: "
                    f"{candidates}"
                )

        # Fallback: first-line comment sniffing for the legacy format.
        if not path:
            lines = content.split("\n")
            for line in lines:
                if not line.strip():
                    continue
                first_line = line.strip()
                if first_line.startswith("#") or first_line.startswith("//"):
                    potential = first_line.lstrip("#/ ").strip()
                    if "." in potential and len(potential.split()) == 1:
                        path = potential
                break

        if not path:
            continue

        is_delete = (block.group("lang") == "delete")
        if path.startswith("delete:"):
            is_delete = True
            path = path[7:].strip()

        path, target_path = _resolve_target_path(path, workspace_root)

        if path.lower() == "checklist.md":
            continue

        # Harness protection: block .mighty/ unless system mode allows it.
        if not policy.system_mode:
            norm_path = posixpath.normpath(path.replace("\\", "/"))
            if norm_path == ".mighty" or norm_path.startswith(".mighty/"):
                print(
                    f"[parser] REJECTED system path: {path}",
                    file=sys.stderr,
                )
                continue

        if len(content.encode("utf-8")) > policy.max_file_bytes:
            raise ValueError(f"Refusing oversized file block for {path}")

        if is_delete:
            if path not in allowed_delete_paths:
                raise ValueError(f"Deletion not permitted for path: {path}")
            if os.path.exists(target_path):
                os.remove(target_path)
                print(f"[parser] PURGED file: {path}", file=sys.stderr)
            extracted_files.append(path)
            continue

        if policy.strict_code_hygiene:
            leakage_patterns = [
                r"</thought>",
                r"</act>",
                r"</mighty>",
                r"</context_audit>",
                r"</adversarial_red_team>",
                r"</adversarial_plan>",
                r"</verify>",
                r"</xml>",
            ]
            for pattern in leakage_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    raise ValueError(
                        f"XML leakage detected in {path}: "
                        f"Found hallucinated tag {pattern}"
                    )

        print(
            f"[parser] Target: {path} (Resolved: {target_path})",
            file=sys.stderr,
        )
        target_directory = os.path.dirname(target_path)
        os.makedirs(target_directory or ".", exist_ok=True)
        with open(target_path, "w") as output_file:
            output_file.write(content)
        print(
            f"[parser] Wrote {len(content)} bytes to {path}",
            file=sys.stderr,
        )
        extracted_files.append(path)

    if not extracted_files:
        print("[parser] !!!!!!!!! WARNING !!!!!!!!!", file=sys.stderr)
        print(
            "[parser] No code blocks with file paths identified in response.",
            file=sys.stderr,
        )
        print(
            f"[parser] Response length: {len(raw_text)} chars.",
            file=sys.stderr,
        )
        print("[parser] !!!!!!!!!!!!!!!!!!!!!!!!!!!", file=sys.stderr)

    return extracted_files


def apply_response(request: ResponseApplicationRequest) -> list[str]:
    """Apply one response while preserving legacy parser behavior."""
    return _apply_response_text(
        request.raw_response,
        request.policy,
    )
