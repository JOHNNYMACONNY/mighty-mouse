"""Explicit offline, data-only Improvement Bundle export and quarantine."""
from __future__ import annotations

import base64
import json
import unicodedata
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

_FORBIDDEN = {"source", "code", "transcript", "prompt", "secret", "pin", "promotion", "authority", "control_state", "executable"}
_REQUIRED = {"schema_version", "model_identities", "execution_profiles", "capabilities", "provenance", "policies"}

def _normalise(value):
    if isinstance(value, str): return unicodedata.normalize("NFC", value)
    if isinstance(value, list): return [_normalise(item) for item in value]
    if isinstance(value, dict): return {str(key): _normalise(item) for key, item in value.items()}
    return value

def _canonical_manifest(value: dict) -> bytes:
    """The signed JCS-style manifest bytes; never sign a re-serialized import."""
    return json.dumps(_normalise(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def _validate(manifest: dict) -> None:
    if not _REQUIRED.issubset(manifest) or any(key in _FORBIDDEN for key in manifest):
        raise ValueError("Bundle manifest is incomplete or contains prohibited authority/content")
    if any(term in json.dumps(manifest).lower() for term in _FORBIDDEN):
        raise ValueError("Bundle manifest contains prohibited content")

def export_bundle(destination: str | Path, manifest: dict, signing_key: Ed25519PrivateKey, *, key_id: str) -> Path:
    """Write a canonical manifest and a detached Ed25519 signature with its signer id."""
    if not key_id: raise ValueError("bundle export requires a signing key id")
    _validate(manifest)
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    payload = _canonical_manifest(manifest)
    signature = signing_key.sign(payload)
    (destination / "manifest.json").write_bytes(payload)
    (destination / "manifest.sig").write_text(json.dumps({"algorithm":"Ed25519", "key_id":key_id, "signature":base64.b64encode(signature).decode()}, sort_keys=True, separators=(",", ":")))
    return destination

def verify_bundle(directory: str | Path, keyring: dict[str, Ed25519PublicKey]) -> dict:
    directory = Path(directory); payload = (directory / "manifest.json").read_bytes()
    envelope = json.loads((directory / "manifest.sig").read_text())
    if envelope.get("algorithm") != "Ed25519" or not isinstance(envelope.get("key_id"), str): raise ValueError("invalid bundle signature envelope")
    key = keyring.get(envelope["key_id"])
    if key is None: raise ValueError("bundle signing key is not trusted locally")
    try: key.verify(base64.b64decode(envelope["signature"], validate=True), payload)
    except (InvalidSignature, ValueError, TypeError) as exc: raise ValueError("bundle signature is invalid") from exc
    manifest = json.loads(payload)
    if payload != _canonical_manifest(manifest): raise ValueError("bundle manifest is not canonical")
    _validate(manifest)
    return manifest

def import_bundle(directory: str | Path, quarantine_dir: str | Path, keyring: dict[str, Ed25519PublicKey], *, model_identity: str, execution_profile: str, capabilities: set[str]) -> Path:
    """Verify then copy as untrusted data; import is never an activation path."""
    manifest = verify_bundle(directory, keyring)
    if model_identity not in manifest["model_identities"] or execution_profile not in manifest["execution_profiles"] or not set(manifest["capabilities"]).issubset(capabilities):
        raise ValueError("bundle is incompatible with this local execution")
    destination = Path(quarantine_dir) / Path(directory).name; destination.mkdir(parents=True, exist_ok=False)
    for name in ("manifest.json", "manifest.sig"): (destination / name).write_bytes((Path(directory) / name).read_bytes())
    (destination / "QUARANTINED").write_text("untrusted data-only candidate; local evaluation required\n")
    return destination

def public_key_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
