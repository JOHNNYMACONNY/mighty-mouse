"""HostAdapter deep module encapsulating environment detection, contract binding, and PolicyEngine interaction for host integration."""

from __future__ import annotations

from hashlib import sha256
import inspect
import json
from pathlib import Path
from typing import Any

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
MCP_TOOL_CONTRACT_VERSION = 1
MCP_ADAPTER_CONFIG_SCHEMA_VERSION = 2
ADAPTER_CONFIG_FILENAME = "mcp-adapter.json"


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
    def resolve_adapter_scope(
        workspace: str,
        state_dir: str | None,
        task_category: str,
        tool_signatures: dict[str, Any],
        contract_version: int = MCP_TOOL_CONTRACT_VERSION,
    ) -> tuple[Path, Scope, str, str]:
        """Resolve workspace state directory, Scope, model digest, and execution profile ID."""
        resolved_state_dir = Path(state_dir) if state_dir else Path(workspace) / ".mighty-mouse"
        path = resolved_state_dir / ADAPTER_CONFIG_FILENAME
        if not path.is_file():
            raise ValueError(f"MCP adapter identity is not configured: {path}; run setup_workspace")
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Cline adapter identity configuration is invalid JSON") from exc
        base_scope = HostAdapter.validate_adapter_config(
            config,
            tool_signatures=tool_signatures,
            contract_version=contract_version,
        )
        scope = Scope(Mode.CODING, base_scope.repository, TaskCategory(task_category), base_scope.model_class)
        return resolved_state_dir, scope, str(config["model_digest"]), str(config["execution_profile_id"])
