"""Explicit, offline, data-only Improvement Bundle export."""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
from pathlib import Path

_FORBIDDEN = {"source", "code", "transcript", "prompt", "secret", "pin", "promotion", "authority", "control_state", "executable"}


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def export_bundle(destination: str | Path, manifest: dict, signing_key: bytes) -> Path:
    """Write a deterministic manifest and detached signature; never transmits data."""
    required = {"schema_version", "model_identities", "execution_profiles", "capabilities", "provenance", "policies"}
    if not required.issubset(manifest) or any(key in _FORBIDDEN for key in manifest):
        raise ValueError("Bundle manifest is incomplete or contains prohibited authority/content")
    for value in manifest.values():
        if isinstance(value, str) and any(term in value.lower() for term in _FORBIDDEN):
            raise ValueError("Bundle manifest contains prohibited content")
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    payload = _canonical(manifest)
    (destination / "manifest.json").write_bytes(payload)
    (destination / "manifest.sig").write_text(hmac.new(signing_key, payload, sha256).hexdigest())
    return destination


def verify_bundle(directory: str | Path, signing_key: bytes) -> dict:
    directory = Path(directory); payload = (directory / "manifest.json").read_bytes()
    signature = (directory / "manifest.sig").read_text().strip()
    if not hmac.compare_digest(signature, hmac.new(signing_key, payload, sha256).hexdigest()):
        raise ValueError("Bundle signature is invalid")
    return json.loads(payload)


def import_bundle(directory: str | Path, quarantine_dir: str | Path, signing_key: bytes, *, model_identity: str, execution_profile: str, capabilities: set[str]) -> Path:
    """Verify then copy a Bundle as inert external provenance; never touches v2 state."""
    manifest = verify_bundle(directory, signing_key)
    if manifest.get("schema_version") != 1:
        raise ValueError("Bundle schema is unsupported")
    if model_identity not in manifest["model_identities"] or execution_profile not in manifest["execution_profiles"]:
        raise ValueError("Bundle is incompatible with this local identity/profile")
    if not set(manifest["capabilities"]).issubset(capabilities):
        raise ValueError("Bundle requires unavailable capabilities")
    quarantine_dir = Path(quarantine_dir); quarantine_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256(_canonical(manifest)).hexdigest()
    target = quarantine_dir / f"bundle-{digest}.json"
    if target.exists():
        raise ValueError("Bundle replay already exists in quarantine")
    target.write_bytes(_canonical({"external_provenance": digest, "manifest": manifest}))
    return target
