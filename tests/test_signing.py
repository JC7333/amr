"""Tests for AMR Ed25519 signing key management."""

import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.crypto.signing import (
    ensure_signing_key_exists,
    generate_signing_key,
    get_key_id,
    load_public_key,
    load_signing_key,
)


@pytest.fixture()
def key_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide isolated key paths for each test."""
    priv = tmp_path / "test_signing_key.pem"
    pub = tmp_path / "test_signing_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    return priv, pub


def test_generate_creates_both_files(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    assert priv.exists(), "Private key file should exist after generation"
    assert pub.exists(), "Public key file should exist after generation"


def test_generate_refuses_overwrite(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    with pytest.raises(FileExistsError):
        generate_signing_key(priv, pub)


def test_ensure_creates_if_missing(key_paths):
    priv, pub = key_paths
    assert not priv.exists()
    ensure_signing_key_exists()
    assert priv.exists()
    assert pub.exists()


def test_ensure_idempotent(key_paths):
    priv, pub = key_paths
    ensure_signing_key_exists()
    mtime = priv.stat().st_mtime
    ensure_signing_key_exists()
    assert priv.stat().st_mtime == mtime, "ensure_signing_key_exists should not overwrite existing key"


def test_load_returns_ed25519_private(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    key = load_signing_key()
    assert isinstance(key, ed25519.Ed25519PrivateKey)


def test_load_public_returns_ed25519_public(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    key = load_public_key()
    assert isinstance(key, ed25519.Ed25519PublicKey)


def test_sign_and_verify_roundtrip(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    private_key = load_signing_key()
    public_key = load_public_key()
    message = b"test message for signing"
    signature = private_key.sign(message)
    # verify() raises InvalidSignature if wrong; no exception means success
    public_key.verify(signature, message)


def test_get_key_id_is_stable(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    ids = [get_key_id() for _ in range(10)]
    assert len(set(ids)) == 1, "get_key_id should return the same value on repeated calls"


def test_get_key_id_is_16_chars(key_paths):
    priv, pub = key_paths
    generate_signing_key(priv, pub)
    assert len(get_key_id()) == 16


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file permissions not applicable on Windows")
def test_posix_permissions_0600(key_paths):
    import stat

    priv, pub = key_paths
    generate_signing_key(priv, pub)
    priv_mode = stat.S_IMODE(priv.stat().st_mode)
    assert priv_mode == 0o600, f"Expected 0o600, got {oct(priv_mode)}"
