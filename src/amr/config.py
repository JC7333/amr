"""AMR configuration - loads from environment variables or .env file."""

from pathlib import Path

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

    model_config = {"env_prefix": "AMR_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
