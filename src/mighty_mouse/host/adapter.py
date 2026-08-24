"""HostAdapter deep module encapsulating environment detection, contract binding, and PolicyEngine interaction for host integration."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
from typing import Any, Sequence

from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    Mode,
    ModelIdentity,
    Pin,
    PolicySelection,
    Preview,
    PromotionNotice,
    Scope,
    Signal,
    StoredRecord,
    TaskCategory,
    resolve_execution_profile,
)
from mighty_mouse.protocols import get_protocol


SUPPORTED_RUNTIME_KINDS = frozenset({"cline", "claude-code", "codex", "cursor", "antigravity", "hermes", "windsurf"})
MCP_TOOL_CONTRACT_VERSION = 6
MCP_ADAPTER_CONFIG_SCHEMA_VERSION = 2
ADAPTER_CONFIG_FILENAME = "mcp-adapter.json"


@dataclass(frozen=True)
class AdapterRuntimeContext:
    state_dir: Path
    repository: str
    model_class: str
    model_identity: ModelIdentity
    execution_profile: ExecutionProfile
    model_source: str = "host"
    ollama_model: str | None = None


class HostAdapter:
    """Deep adapter isolating host environment detection, tool contract hashing, and PolicyEngine interaction."""

    def __init__(self, engine: PolicyEngine | None = None) -> None:
        self.engine = engine

    def _policy_engine(self) -> PolicyEngine:
        if self.engine is None:
            raise RuntimeError("HostAdapter policy controls require a configured PolicyEngine")
        return self.engine

    def select_policy(self, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> PolicySelection:
        return self._policy_engine().select_policy(scope, model_identity, execution_profile)

    def record_signal(self, signal: Signal) -> str | None:
        return self._policy_engine().record_signal(signal)

    def get_status(self, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> dict[str, Any]:
        return self._policy_engine().get_status(scope, model_identity, execution_profile)

    def pin(self, value: Pin, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> StoredRecord:
        return self._policy_engine().pin(value, model_identity, execution_profile)

    def preview(self, value: Preview, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> PolicySelection:
        return self._policy_engine().preview(value, model_identity, execution_profile)

    def rollback(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
        reason: str,
        security_breach: bool = False,
    ) -> PromotionNotice:
        return self._policy_engine().rollback(scope, model_identity, execution_profile, reason, security_breach)

    def solve(
        self,
        workspace: str,
        p_cfg_path: str,
        task_input: str,
        *,
        state_dir: str | None = None,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
        feedback_str: str | None = None,
        explicit_skills: str | None = None,
        temperature: float | None = None,
        stage: str = "unified",
        plan_file: str | None = None,
    ) -> None:
        """Execute coding task using authoritatively resolved host
        runtime context.
        """
        ctx = self.resolve_adapter_context(
            workspace=workspace,
            state_dir=state_dir,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        try:
            from mighty_mouse.orchestrator.mighty_mouse_agent import (
                _solve_with_runtime_context,
            )
        except ImportError:
            from mighty_mouse_agent import (  # type: ignore[no-redef]
                _solve_with_runtime_context,
            )
        return _solve_with_runtime_context(
            p_cfg_path,
            task_input,
            runtime_context=ctx,
            feedback_str=feedback_str,
            workspace=workspace,
            explicit_skills=explicit_skills,
            temperature=temperature,
            stage=stage,
            plan_file=plan_file,
        )

    def solve_swarm(
        self,
        workspace: str,
        task_input: str,
        *,
        verification_workspace: str,
        state_dir: str | None = None,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
        concurrency: int = 1,
        test_command: str | Sequence[str] | None = None,
        lint_command: str | Sequence[str] | None = None,
        build_command: str | Sequence[str] | None = None,
        allowed_paths: list[str] | None = None,
        task_config: dict[str, Any] | None = None,
        timeout_sec: int = 120,
    ) -> dict[str, Any]:
        """Execute coding task using Multi-Agent Swarm bound to canonical
        host provenance and isolated verification.
        """
        ws_path = Path(workspace)
        if not ws_path.is_dir():
            raise ValueError(
                f"Workspace must be an existing directory: {workspace}"
            )
        iso_ws_path = Path(verification_workspace)
        if not iso_ws_path.is_dir():
            raise ValueError(
                "Verification workspace must be an existing directory: "
                f"{verification_workspace}"
            )
        ws_real = os.path.realpath(os.path.abspath(workspace))
        iso_real = os.path.realpath(os.path.abspath(verification_workspace))
        try:
            common = os.path.commonpath([ws_real, iso_real])
        except ValueError:
            common = None

        if common in (ws_real, iso_real):
            raise ValueError(
                "Verification workspace cannot overlap with application "
                "workspace"
            )
        if concurrency not in (1, 2):
            raise ValueError(
                f"Swarm concurrency must be 1 or 2, got {concurrency}"
            )

        try:
            task_data = json.loads(task_input)
            if not isinstance(task_data, dict):
                raise ValueError("task_input must be a valid JSON object")
        except json.JSONDecodeError as exc:
            raise ValueError("task_input is invalid JSON") from exc

        allowed_delete_paths: tuple[str, ...] = ()
        if "deletable_files" in task_data:
            raw_deletables = task_data["deletable_files"]
            if not isinstance(raw_deletables, list):
                raise ValueError(
                    "task_input deletable_files must be a list of relative "
                    f"path strings, got {type(raw_deletables).__name__}"
                )
            validated_paths: list[str] = []
            for item in raw_deletables:
                if not isinstance(item, str):
                    raise ValueError(
                        "task_input deletable_files entry must be a string, "
                        f"got {type(item).__name__}"
                    )
                trimmed = item.strip()
                if not trimmed:
                    raise ValueError(
                        "task_input deletable_files entry cannot be empty"
                    )
                if trimmed.startswith("/") or Path(trimmed).is_absolute():
                    raise ValueError(
                        "task_input deletable_files entry cannot be "
                        f"absolute: {item}"
                    )
                if ".." in Path(trimmed).parts:
                    raise ValueError(
                        "task_input deletable_files entry cannot contain "
                        f"parent traversal '..': {item}"
                    )
                validated_paths.append(trimmed)
            allowed_delete_paths = tuple(validated_paths)

        ctx = self.resolve_adapter_context(
            workspace=workspace,
            state_dir=state_dir,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )

        if ctx.model_source != "ollama" or not ctx.ollama_model:
            raise ValueError(
                "Swarm execution requires an Ollama-backed model identity, "
                f"got model_source='{ctx.model_source}'"
            )

        try:
            from mighty_mouse.orchestrator.response_application import (
                ResponseApplicationPolicy,
                apply_response,
            )
            from mighty_mouse.orchestrator.swarm import (
                SwarmOrchestrator,
                create_isolated_verification_adapter,
            )
        except ImportError:
            from response_application import (  # type: ignore[no-redef]
                ResponseApplicationPolicy,
                apply_response,
            )
            from swarm import (  # type: ignore[no-redef]
                SwarmOrchestrator,
                create_isolated_verification_adapter,
            )

        real_policy = ResponseApplicationPolicy(
            workspace_root=workspace,
            allowed_delete_paths=allowed_delete_paths,
        )

        iso_verifier = create_isolated_verification_adapter(
            isolated_workspace=verification_workspace,
            test_command=test_command,
            lint_command=lint_command,
            build_command=build_command,
            allowed_paths=allowed_paths,
            task_config=task_config,
            timeout_sec=timeout_sec,
        )

        orchestrator = SwarmOrchestrator(
            model_name=ctx.ollama_model,
            concurrency=concurrency,
        )

        pipeline_result = orchestrator.execute_swarm_pipeline(
            task_data=task_data,
            application_policy=real_policy,
            verification_adapter=iso_verifier,
            application_adapter=apply_response,
        )

        host_provenance = {
            "repository": ctx.repository,
            "model_class": ctx.model_class,
            "model_digest": str(ctx.model_identity.artifact_digest),
            "execution_profile_id": str(ctx.execution_profile.profile_id),
            "model_source": ctx.model_source,
            "ollama_model": ctx.ollama_model,
            "contract_version": contract_version,
        }

        return {
            "host_provenance": host_provenance,
            "pipeline_result": pipeline_result,
        }

    @staticmethod
    def get_tool_contract(
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> dict[str, str]:
        """Construct a versioned tool contract dictionary mapping tool names to signatures."""
        contract = {"contract_version": str(contract_version)}
        for name, func in tool_signatures.items():
            contract[name] = str(inspect.signature(func)) if callable(func) else str(func)
        return contract

    @staticmethod
    def resolve_ollama_model_digest(model: str) -> str:
        """Resolve a model digest from the local Ollama manifest library."""
        name, separator, tag = model.rpartition(":")
        if not separator:
            name, tag = model, "latest"
        if not name or not tag or any(part in {"", ".", ".."} for part in name.split("/")):
            raise ValueError("Ollama model must be a model name with an optional tag")
        manifest_path = Path.home() / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / name / tag
        if not manifest_path.is_file():
            raise ValueError(f"Ollama manifest is unavailable for {model}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ollama manifest is invalid for {model}") from exc
        digest = next((layer.get("digest") for layer in manifest.get("layers", []) if layer.get("mediaType") == "application/vnd.ollama.image.model"), None)
        if not isinstance(digest, str):
            raise ValueError(f"Ollama model-layer digest is unavailable for {model}")
        return digest

    @staticmethod
    def build_execution_profile(
        *,
        runtime_kind: str,
        runtime_version: str,
        effective_context_limit: int,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> tuple[ExecutionProfile, str, str]:
        """Build a canonical ExecutionProfile along with tool contract and prompt digests."""
        if runtime_kind not in SUPPORTED_RUNTIME_KINDS or not runtime_version or runtime_version == "unknown":
            raise ValueError("Workspace setup requires a supported runtime kind and exact runtime version")
        tool_contract = HostAdapter.get_tool_contract(tool_signatures, contract_version=contract_version)
        tool_contract_digest = "sha256:" + sha256(
            json.dumps(tool_contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        prompt_template_digest = "sha256:" + sha256(
            "\n".join(get_protocol(complexity) for complexity in ("low", "medium", "high")).encode()
        ).hexdigest()
        profile = resolve_execution_profile(
            runtime_kind=runtime_kind,
            runtime_version=runtime_version,
            effective_context_limit=effective_context_limit,
            tool_contract_digest=tool_contract_digest,
            prompt_template_digest=prompt_template_digest,
            sampling_settings={},
            resource_limits={},
            capabilities=frozenset({"mcp", *tool_contract}),
        )
        return profile, tool_contract_digest, prompt_template_digest

    @staticmethod
    def build_adapter_config(
        *,
        repository: str,
        model_digest: str,
        model_class: str,
        effective_context_limit: int,
        runtime_kind: str,
        runtime_version: str,
        ollama_model: str | None,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> dict[str, Any]:
        """Build and validate an adapter identity configuration document."""
        profile, tool_contract_digest, prompt_template_digest = HostAdapter.build_execution_profile(
            runtime_kind=runtime_kind,
            runtime_version=runtime_version,
            effective_context_limit=effective_context_limit,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        config = {
            "schema_version": MCP_ADAPTER_CONFIG_SCHEMA_VERSION,
            "repository": repository,
            "model_digest": model_digest,
            "model_class": model_class,
            "model_source": "ollama" if ollama_model else "host",
            "ollama_model": ollama_model,
            "execution_profile_id": profile.profile_id,
            "runtime_kind": runtime_kind,
            "runtime_version": runtime_version,
            "effective_context_limit": effective_context_limit,
            "tool_contract_digest": tool_contract_digest,
            "prompt_template_digest": prompt_template_digest,
        }
        HostAdapter.validate_adapter_config(
            config,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        return config

    @staticmethod
    def validate_adapter_config(
        config: dict[str, Any],
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> Scope:
        """Validate adapter identity config and return the resolved Scope."""
        required = {
            "schema_version", "repository", "model_digest", "model_class", "execution_profile_id",
            "model_source", "ollama_model", "runtime_kind", "runtime_version", "effective_context_limit", "tool_contract_digest",
            "prompt_template_digest",
        }
        if set(config) != required:
            raise ValueError("MCP adapter identity configuration is stale or invalid; run setup_workspace")
        if config["schema_version"] != MCP_ADAPTER_CONFIG_SCHEMA_VERSION:
            raise ValueError("MCP adapter identity configuration is stale; run setup_workspace")
        if config["model_source"] not in {"ollama", "host"}:
            raise ValueError("MCP adapter identity configuration is stale or invalid; run setup_workspace")
        if config["model_source"] == "ollama":
            ollama_model = config["ollama_model"]
            if not isinstance(ollama_model, str) or HostAdapter.resolve_ollama_model_digest(ollama_model) != config["model_digest"]:
                raise ValueError("MCP adapter model identity changed; run setup_workspace")
        elif config["ollama_model"] is not None:
            raise ValueError("MCP adapter identity configuration is stale or invalid; run setup_workspace")
        profile, tool_contract_digest, prompt_template_digest = HostAdapter.build_execution_profile(
            runtime_kind=str(config["runtime_kind"]),
            runtime_version=str(config["runtime_version"]),
            effective_context_limit=int(config["effective_context_limit"]),
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        if (
            config["execution_profile_id"] != profile.profile_id
            or config["tool_contract_digest"] != tool_contract_digest
            or config["prompt_template_digest"] != prompt_template_digest
        ):
            raise ValueError("MCP adapter identity configuration is stale; run setup_workspace")
        scope = Scope(Mode.CODING, str(config["repository"]), TaskCategory.UNKNOWN, str(config["model_class"]))
        Signal(
            signal_id="signal-000", scope=scope, model_digest=str(config["model_digest"]),
            execution_profile_id=str(config["execution_profile_id"]), outcome="passed", duration_ms=0,
            retry_count=0, verifier_category="none", verifier_result="not_run",
        )
        return scope

    @staticmethod
    def resolve_adapter_context(
        workspace: str,
        state_dir: str | None = None,
        *,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> AdapterRuntimeContext:
        """Resolve workspace state directory, model identity, and execution profile context."""
        resolved_state_dir = Path(state_dir) if state_dir else Path(workspace) / ".mighty-mouse"
        path = resolved_state_dir / ADAPTER_CONFIG_FILENAME
        if not path.is_file():
            raise ValueError(f"MCP adapter identity is not configured: {path}; run setup_workspace")
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("MCP adapter identity configuration is invalid JSON") from exc
        HostAdapter.validate_adapter_config(
            config,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        profile, _, _ = HostAdapter.build_execution_profile(
            runtime_kind=str(config["runtime_kind"]),
            runtime_version=str(config["runtime_version"]),
            effective_context_limit=int(config["effective_context_limit"]),
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        model_identity = ModelIdentity(
            artifact_digest=str(config["model_digest"]),
        )
        return AdapterRuntimeContext(
            state_dir=resolved_state_dir,
            repository=str(config["repository"]),
            model_class=str(config["model_class"]),
            model_identity=model_identity,
            execution_profile=profile,
            model_source=str(config.get("model_source", "host")),
            ollama_model=config.get("ollama_model"),
        )

    @staticmethod
    def resolve_adapter_scope(
        workspace: str,
        state_dir: str | None,
        task_category: str,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> tuple[Path, Scope, str, str]:
        """Resolve workspace state directory, Scope, model digest, and execution profile ID."""
        ctx = HostAdapter.resolve_adapter_context(
            workspace,
            state_dir,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        scope = Scope(Mode.CODING, ctx.repository, TaskCategory(task_category), ctx.model_class)
        return ctx.state_dir, scope, str(ctx.model_identity.artifact_digest), str(ctx.execution_profile.profile_id)
