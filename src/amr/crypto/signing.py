"""AMR signing key management for Ed25519 token issuance."""

import hashlib
import os
import stat
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.config import settings


def generate_signing_key(
    private_key_path: Path | None = None,
    public_key_path: Path | None = None,
) -> None:
    """Generate a new Ed25519 keypair and write it to disk.

    Raises FileExistsError if a key already exists at private_key_path.
    Sets file permissions to 0600 on POSIX systems. No-op on Windows.
    """
    priv_path = private_key_path if private_key_path is not None else settings.signing_key_path
    pub_path = public_key_path if public_key_path is not None else settings.public_key_path

    if priv_path.exists():
        raise FileExistsError(f"Signing key already exists at {priv_path}")

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path.write_bytes(private_pem)
    pub_path.write_bytes(public_pem)

    # Set permissions to 0600 on POSIX (no-op on Windows)
    if sys.platform != "win32":
        os.chmod(priv_path, stat.S_IRUSR | stat.S_IWUSR)
        os.chmod(pub_path, stat.S_IRUSR | stat.S_IWUSR)


def ensure_signing_key_exists() -> None:
    """Ensure a signing key exists at settings.signing_key_path.

    If missing, generates a new keypair. Safe to call on every tool invocation.
    """
    if not settings.signing_key_path.exists():
        generate_signing_key()


def load_signing_key() -> ed25519.Ed25519PrivateKey:
    """Load the Ed25519 private key from settings.signing_key_path."""
    pem_bytes = settings.signing_key_path.read_bytes()
    return serialization.load_pem_private_key(pem_bytes, password=None)  # type: ignore[return-value]


def load_public_key() -> ed25519.Ed25519PublicKey:
    """Load the Ed25519 public key from settings.public_key_path."""
    pem_bytes = settings.public_key_path.read_bytes()
    return serialization.load_pem_public_key(pem_bytes)  # type: ignore[return-value]


def get_key_id() -> str:
    """Return a stable key identifier (first 16 hex chars of SHA-256 of public key bytes)."""
    public_key = load_public_key()
    raw_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw_bytes).hexdigest()[:16]
