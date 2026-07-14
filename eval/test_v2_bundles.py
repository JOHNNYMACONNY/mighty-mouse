import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mighty_mouse.v2.bundles import export_bundle, import_bundle, verify_bundle


def _manifest():
    return {"schema_version":"v2","model_identities":["sha256:model"],"execution_profiles":["local"],"capabilities":["tools"],"provenance":{"digest":"sha256:p"},"policies":[{"digest":"sha256:policy"}]}


def test_bundle_requires_receiver_local_keyring_and_quarantines_import(tmp_path):
    private = Ed25519PrivateKey.generate(); public = private.public_key()
    bundle = export_bundle(tmp_path / "export", _manifest(), private, key_id="publisher-1")
    assert verify_bundle(bundle, {"publisher-1": public}) == _manifest()
    destination = import_bundle(bundle, tmp_path / "quarantine", {"publisher-1": public}, model_identity="sha256:model", execution_profile="local", capabilities={"tools"})
    assert (destination / "QUARANTINED").exists()


def test_bundle_rejects_unknown_keys_and_tampered_signatures(tmp_path):
    private = Ed25519PrivateKey.generate()
    bundle = export_bundle(tmp_path / "export", _manifest(), private, key_id="publisher-1")
    with pytest.raises(ValueError, match="not trusted"):
        verify_bundle(bundle, {})
    (bundle / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="signature"):
        verify_bundle(bundle, {"publisher-1": private.public_key()})
