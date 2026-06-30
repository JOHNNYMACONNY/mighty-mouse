"""Versioned Mighty Mouse protocol delivery."""

from __future__ import annotations

from importlib import resources

PROTOCOL_VERSION = "v9.1"
COMPLEXITIES = ("low", "medium", "high")


def get_protocol(complexity: str = "medium", version: str = PROTOCOL_VERSION) -> str:
    normalized = complexity.lower().strip()
    if normalized not in COMPLEXITIES:
        raise ValueError(f"complexity must be one of: {', '.join(COMPLEXITIES)}")
    protocol_file = resources.files(__package__).joinpath(version, f"{normalized}.md")
    if not protocol_file.is_file():
        raise ValueError(f"Unknown protocol version: {version}")
    return protocol_file.read_text(encoding="utf-8")


__all__ = ["COMPLEXITIES", "PROTOCOL_VERSION", "get_protocol"]
