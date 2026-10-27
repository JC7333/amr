"""Token lifetime is bounded: never above the default, never past the mandate chain."""

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest

from amr.config import settings
from amr.crypto.signing import generate_signing_key
from amr.tools.create_mandate import create_mandate
from amr.tools.issue_action_token import issue_action_token

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _root(duration_hours: float = 24.0) -> dict:
    result = json.loads(await create_mandate(
        principal_id=PRINCIPAL,
        agent_id=AGENT,
        scope="Handle supplier invoices",
        legal_basis_regulation="Mandate contract",
        legal_basis_article="Clause 1",
        duration_hours=duration_hours,
        allowed_actions=["invoice.*"],
        delegation_allowed=True,
    ))
    assert result.get("status") == "created", result
    return result


async def _child(parent_id: str, delegation_allowed: bool = False) -> dict:
    result = json.loads(await create_mandate(
        principal_id=AGENT,
        agent_id=HELPER,
        scope="Read invoices only",
        legal_basis_regulation="Service contract",
        legal_basis_article="Clause 4",
        duration_hours=12.0,
        parent_mandate_id=parent_id,
        allowed_actions=["invoice.read"],
        delegation_allowed=delegation_allowed,
    ))
    assert result.get("status") == "created", result
    return result


async def _token(mandate_id: str, agent_id: str = AGENT, **overrides: object) -> dict:
    params: dict = {
        "mandate_id": mandate_id,
        "agent_id": agent_id,
        "action": f"read invoice {uuid4()}",
        "audience": "runtime://erp",
        "action_type": "invoice.read",
    }
    params.update(overrides)
    return json.loads(await issue_action_token(**params))


def _set_expiry(db_path: Path, mandate_id: str, moment: datetime) -> None:
    # Test-only: move a mandate's expiry, to stand for a short-lived mandate.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE mandates SET expires_at = ? WHERE id = ?",
            (moment.isoformat(), mandate_id),
        )


def _expires(token: dict) -> datetime:
    return datetime.fromisoformat(token["expires_at"])


def _exp_claim(token: dict) -> int:
    claims = jwt.decode(token["token"], options={"verify_signature": False})
    return claims["exp"]


async def test_default_lifetime_is_unchanged() -> None:
    root = await _root()
    before = datetime.now(UTC)
    token = await _token(root["mandate_id"])
    lifetime = (_expires(token) - before).total_seconds()
    assert settings.token_lifetime_seconds - 5 <= lifetime <= settings.token_lifetime_seconds + 5


async def test_override_cannot_lengthen_a_token() -> None:
    root = await _root()
    before = datetime.now(UTC)
    token = await _token(root["mandate_id"], lifetime_override_seconds=86400)
    lifetime = (_expires(token) - before).total_seconds()
    assert lifetime <= settings.token_lifetime_seconds + 5
    assert _exp_claim(token) <= int(
        (before + timedelta(seconds=settings.token_lifetime_seconds + 5)).timestamp()
    )


async def test_override_can_shorten_a_token() -> None:
    root = await _root()
    before = datetime.now(UTC)
    token = await _token(root["mandate_id"], lifetime_override_seconds=30)
    lifetime = (_expires(token) - before).total_seconds()
    assert 25 <= lifetime <= 35


async def test_token_never_outlives_its_mandate(temp_db: Path) -> None:
    root = await _root()
    ends = datetime.now(UTC) + timedelta(seconds=40)
    _set_expiry(temp_db, root["mandate_id"], ends)
    token = await _token(root["mandate_id"])
    assert "token" in token, token
    assert _expires(token) == ends
    assert _exp_claim(token) <= int(ends.timestamp())


async def test_token_never_outlives_a_parent_mandate(temp_db: Path) -> None:
    root = await _root()
    child = await _child(root["mandate_id"])
    ends = datetime.now(UTC) + timedelta(seconds=45)
    _set_expiry(temp_db, root["mandate_id"], ends)
    token = await _token(child["mandate_id"], HELPER)
    assert "token" in token, token
    assert _expires(token) == ends
    assert _exp_claim(token) <= int(ends.timestamp())


async def test_token_never_outlives_a_grandparent_mandate(temp_db: Path) -> None:
    root = await _root()
    child = await _child(root["mandate_id"], delegation_allowed=True)
    grandchild = json.loads(await create_mandate(
        principal_id=HELPER,
        agent_id="agent:reader",
        scope="Read one invoice",
        legal_basis_regulation="Service contract",
        legal_basis_article="Clause 5",
        duration_hours=1.0,
        parent_mandate_id=child["mandate_id"],
        allowed_actions=["invoice.read"],
    ))
    assert grandchild.get("status") == "created", grandchild
    ends = datetime.now(UTC) + timedelta(seconds=50)
    _set_expiry(temp_db, root["mandate_id"], ends)
    token = await _token(grandchild["mandate_id"], "agent:reader")
    assert "token" in token, token
    assert _expires(token) == ends


async def test_long_override_is_still_bounded_by_the_chain(temp_db: Path) -> None:
    root = await _root()
    child = await _child(root["mandate_id"])
    ends = datetime.now(UTC) + timedelta(seconds=20)
    _set_expiry(temp_db, root["mandate_id"], ends)
    token = await _token(child["mandate_id"], HELPER, lifetime_override_seconds=86400)
    assert _expires(token) == ends


async def test_a_nearer_chain_end_wins_over_the_default(temp_db: Path) -> None:
    root = await _root()
    child = await _child(root["mandate_id"])
    far = datetime.now(UTC) + timedelta(hours=2)
    near = datetime.now(UTC) + timedelta(seconds=60)
    _set_expiry(temp_db, root["mandate_id"], far)
    _set_expiry(temp_db, child["mandate_id"], near)
    token = await _token(child["mandate_id"], HELPER)
    assert _expires(token) == near


async def test_a_stored_expiry_without_timezone_is_read_as_utc(temp_db: Path) -> None:
    root = await _root()
    ends = datetime.now(UTC) + timedelta(seconds=40)
    _set_expiry(temp_db, root["mandate_id"], ends.replace(tzinfo=None))
    token = await _token(root["mandate_id"])
    assert "token" in token, token
    assert _expires(token) == ends


async def test_no_token_when_the_chain_ends_within_the_second(temp_db: Path) -> None:
    root = await _root()
    child = await _child(root["mandate_id"])
    # The root must end later in the same whole second as the request: start at the
    # top of a second, so that a fixed +300 ms can never cross into the next one.
    now = datetime.now(UTC)
    if now.microsecond > 100_000:
        time.sleep(1 - now.microsecond / 1_000_000)
    second = datetime.now(UTC).replace(microsecond=0)
    _set_expiry(temp_db, root["mandate_id"], second + timedelta(milliseconds=900))
    denied = await _token(child["mandate_id"], HELPER)
    assert denied.get("denied") is True, denied
    assert denied["reason"] == "mandate_expired"
    assert denied["refused_by"] == root["mandate_id"]
