"""Tests for issued_tokens DB helpers."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite
import pytest

from amr.db.engine import (
    get_db,
    get_issued_token,
    init_db,
    is_token_replay,
    record_issued_token,
)


def _future_iso(seconds: int = 300) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def _past_iso(seconds: int = 300) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_token_row(
    mandate_id: str,
    action_hash: str = "deadbeef",
    jti: str | None = None,
    expires_at: str | None = None,
) -> dict[str, str]:
    return {
        "jti": jti or str(uuid4()),
        "mandate_id": mandate_id,
        "agent_id": "test-agent",
        "action_hash": action_hash,
        "scope_digest": "scopehash",
        "audience": "runtime://test",
        "issued_at": _now_iso(),
        "expires_at": expires_at or _future_iso(),
        "key_id": "abcd1234ef567890",
    }


async def _insert_mandate(db: aiosqlite.Connection, mandate_id: str) -> None:
    """Insert a minimal mandate row to satisfy FK constraint."""
    now = datetime.now(UTC).isoformat()
    expires = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    await db.execute(
        """
        INSERT INTO mandates (
            id, principal_id, agent_id, scope, legal_basis_json,
            status, created_at, expires_at, metadata_json, chain_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mandate_id,
            "principal",
            "test-agent",
            "test scope",
            "{}",
            "active",
            now,
            expires,
            "{}",
            "0" * 64,
        ),
    )
    await db.commit()


async def test_record_inserts_row(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await get_db(temp_db)
    try:
        mandate_id = str(uuid4())
        await _insert_mandate(db, mandate_id)
        row = _make_token_row(mandate_id)
        await record_issued_token(db, row)
        await db.commit()
        result = await get_issued_token(db, row["jti"])
    finally:
        await db.close()
    assert result is not None
    assert result["jti"] == row["jti"]
    assert result["mandate_id"] == mandate_id


async def test_replay_detected_on_same_pair(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await get_db(temp_db)
    try:
        mandate_id = str(uuid4())
        await _insert_mandate(db, mandate_id)
        row = _make_token_row(mandate_id, action_hash="action_abc")
        await record_issued_token(db, row)
        await db.commit()
        result = await is_token_replay(db, mandate_id, "action_abc", _now_iso())
    finally:
        await db.close()
    assert result is True


async def test_replay_not_detected_after_expiration(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await get_db(temp_db)
    try:
        mandate_id = str(uuid4())
        await _insert_mandate(db, mandate_id)
        # expires_at already in the past
        row = _make_token_row(mandate_id, action_hash="action_expired", expires_at=_past_iso())
        await record_issued_token(db, row)
        await db.commit()
        result = await is_token_replay(db, mandate_id, "action_expired", _now_iso())
    finally:
        await db.close()
    assert result is False


async def test_replay_not_detected_different_action(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await get_db(temp_db)
    try:
        mandate_id = str(uuid4())
        await _insert_mandate(db, mandate_id)
        row = _make_token_row(mandate_id, action_hash="action_A")
        await record_issued_token(db, row)
        await db.commit()
        result = await is_token_replay(db, mandate_id, "action_B", _now_iso())
    finally:
        await db.close()
    assert result is False


async def test_replay_not_detected_different_mandate(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await get_db(temp_db)
    try:
        mandate_id_1 = str(uuid4())
        mandate_id_2 = str(uuid4())
        await _insert_mandate(db, mandate_id_1)
        await _insert_mandate(db, mandate_id_2)
        row = _make_token_row(mandate_id_1, action_hash="shared_action")
        await record_issued_token(db, row)
        await db.commit()
        result = await is_token_replay(db, mandate_id_2, "shared_action", _now_iso())
    finally:
        await db.close()
    assert result is False


async def test_get_issued_token_returns_none_for_unknown_jti(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await get_db(temp_db)
    try:
        result = await get_issued_token(db, "nonexistent-jti")
    finally:
        await db.close()
    assert result is None


async def test_commit_required_for_persistence(temp_db: Path) -> None:
    """record_issued_token without commit → not visible in a new connection."""
    await init_db(temp_db)
    jti = str(uuid4())
    mandate_id = str(uuid4())

    # Insert mandate in a separate committed connection first
    db = await get_db(temp_db)
    try:
        await _insert_mandate(db, mandate_id)
    finally:
        await db.close()

    # Insert token but do NOT commit
    db2 = await get_db(temp_db)
    try:
        row = _make_token_row(mandate_id, jti=jti)
        await record_issued_token(db2, row)
        # Intentionally no await db2.commit()
    finally:
        await db2.close()

    # Open a new connection and verify the token is not visible
    db3 = await get_db(temp_db)
    try:
        result = await get_issued_token(db3, jti)
    finally:
        await db3.close()
    assert result is None
