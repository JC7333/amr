"""AMR test configuration and shared fixtures."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated temporary SQLite database for each test.

    Sets AMR_DB_PATH to a unique path under pytest's tmp_path so that
    every test starts with a clean, empty database. The monkeypatch
    fixture automatically restores the original value after each test.

    Args:
        tmp_path: pytest built-in fixture providing a temporary directory.
        monkeypatch: pytest built-in fixture for patching env and attributes.

    Returns:
        Path to the temporary SQLite database file.
    """
    db_path = tmp_path / "test_amr.db"
    monkeypatch.setenv("AMR_DB_PATH", str(db_path))
    monkeypatch.setattr("amr.config.settings.db_path", db_path)
    return db_path
