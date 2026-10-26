"""AMR configuration - loads from environment variables or .env file."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings. Override via env vars prefixed AMR_."""

    db_path: Path = Path("amr_mandates.db")
    hash_algorithm: str = "sha256"
    log_level: str = "INFO"
    server_name: str = "Agent Mandate Registry"
    server_version: str = "0.1.0"

    # Token issuance
    signing_key_path: Path = Path("amr_signing_key.pem")
    public_key_path: Path = Path("amr_signing_key.pub")
    token_issuer: str = "amr://localhost"  # noqa: S105 — not a password, it's an issuer URI
    token_lifetime_seconds: int = 300

    # Principal signatures on mandates (see docs/principal-signature-spec.md).
    # A principal that registered a key must always sign. When True, every mandate
    # must be signed, so a principal without a registered key cannot grant one.
    require_principal_signature: bool = False
    # How old (or how far in the future) a principal's signed_at may be.
    principal_signature_max_age_seconds: int = 900

    # Mandate attestations shown by an agent to a third party (see
    # docs/mandate-attestation-spec.md). Longest lifetime an attestation may have:
    # a revocation reaches a receiver that checks offline only when it expires.
    attestation_lifetime_seconds: int = Field(default=900, gt=0)

    # report_issue (see docs/report-issue-spec.md). Without a token the tool makes no
    # network call and returns a pre-filled link. With one, it creates the issue on
    # issue_repository through the GitHub REST API: give it the narrowest scope
    # (fine-grained token, Issues: write, on that repository only).
    issue_token: SecretStr | None = None
    issue_repository: str = Field(
        default="JC7333/amr", pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
    )

    model_config = {"env_prefix": "AMR_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
