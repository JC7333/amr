"""Tests for principal signatures: key registration, signed mandates, Proof Pack."""

import base64
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.crypto.chain import compute_hash
from amr.crypto.principal import b64url_encode, key_id, key_registration_payload
from amr.db.engine import init_db
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "user:audric"
AGENT = "agent:atelier"

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Open pull requests on the AMR repository",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
}


def _new_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


async def _register(key: ed25519.Ed25519PrivateKey, principal_id: str = PRINCIPAL) -> dict:
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, _pub(key))))
    return json.loads(await register_principal_key(principal_id, _pub(key), proof))


async def _sign(key: ed25519.Ed25519PrivateKey, signed_at: str | None = None, **kwargs) -> dict:
    """Prepare the payload for kwargs and return create_mandate kwargs with the signature."""
    args = {**BASE, **kwargs}
    prepared = json.loads(await prepare_mandate_signature(**args, signed_at=signed_at))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return {**args, "principal_signature": signature, "signed_at": prepared["signed_at"]}


async def _create(**kwargs) -> dict:
    return json.loads(await create_mandate(**kwargs))


# ---------------------------------------------------------------------------
# Key registration
# ---------------------------------------------------------------------------


async def test_register_key_returns_key_id():
    key = _new_key()
    result = await _register(key)
    assert result["status"] == "registered"
    assert len(result["key_id"]) == 16
    assert len(result["chain_hash"]) == 64


async def test_register_key_twice_is_refused():
    await _register(_new_key())
    result = await _register(_new_key())
    assert result["code"] == "principal_key_already_registered"


async def test_register_key_with_proof_from_another_key_is_refused():
    key, other = _new_key(), _new_key()
    proof = b64url_encode(other.sign(key_registration_payload(PRINCIPAL, _pub(key))))
    result = json.loads(await register_principal_key(PRINCIPAL, _pub(key), proof))
    assert result["code"] == "principal_key_proof_invalid"


async def test_register_key_with_proof_for_another_principal_is_refused():
    key = _new_key()
    proof = b64url_encode(key.sign(key_registration_payload("user:someone-else", _pub(key))))
    result = json.loads(await register_principal_key(PRINCIPAL, _pub(key), proof))
    assert result["code"] == "principal_key_proof_invalid"


@pytest.mark.parametrize("bad_key", ["", "not base64!", b64url_encode(b"short"), "A" * 300])
async def test_register_malformed_key_is_refused(bad_key):
    result = json.loads(await register_principal_key(PRINCIPAL, bad_key, "A" * 86))
    assert result["code"] == "public_key_invalid"


async def test_register_key_accepts_padded_base64url():
    key = _new_key()
    padded = _pub(key) + "="
    proof = b64url_encode(key.sign(key_registration_payload(PRINCIPAL, _pub(key))))
    result = json.loads(await register_principal_key(PRINCIPAL, padded, proof))
    assert result["status"] == "registered"


async def test_register_key_rejects_empty_principal():
    key = _new_key()
    proof = b64url_encode(key.sign(key_registration_payload("", _pub(key))))
    result = json.loads(await register_principal_key("", _pub(key), proof))
    assert result["code"] == "principal_id_invalid"


# ---------------------------------------------------------------------------
# Signed mandates
# ---------------------------------------------------------------------------


async def test_signed_mandate_is_created():
    key = _new_key()
    registered = await _register(key)
    result = await _create(**await _sign(key))
    assert result["status"] == "created"
    assert result["principal_signature"]["key_id"] == registered["key_id"]


async def test_unsigned_mandate_for_registered_principal_is_refused():
    await _register(_new_key())
    result = await _create(**BASE)
    assert result["code"] == "principal_signature_required"


async def test_signature_by_another_key_is_refused():
    key = _new_key()
    await _register(key)
    result = await _create(**await _sign(_new_key()))
    assert result["code"] == "principal_signature_invalid"


@pytest.mark.parametrize(
    "change",
    [
        {"agent_id": "agent:intruder"},
        {"scope": "Merge pull requests"},
        {"duration_hours": 8760.0},
        {"legal_basis_article": "Clause 2"},
        {"legal_basis_jurisdiction": "FR"},
        {"metadata": {"client_ref": "X"}},
        {"allowed_actions": ["code.*"]},
    ],
)
async def test_signature_does_not_cover_a_changed_argument(change):
    key = _new_key()
    await _register(key)
    signed = await _sign(key, allowed_actions=["code.pull_request.open"])
    result = await _create(**{**signed, **change})
    assert result["code"] == "principal_signature_invalid"


async def test_signature_without_registered_key_is_refused():
    result = await _create(**await _sign(_new_key()))
    assert result["code"] == "principal_key_not_registered"


@pytest.mark.parametrize("drop", ["principal_signature", "signed_at"])
async def test_signature_and_signed_at_go_together(drop):
    key = _new_key()
    await _register(key)
    signed = await _sign(key)
    signed[drop] = None
    result = await _create(**signed)
    assert result["code"] == "principal_signature_incomplete"


@pytest.mark.parametrize("offset_minutes", [-16, 16])
async def test_signature_outside_time_window_is_refused(offset_minutes):
    key = _new_key()
    await _register(key)
    moment = (datetime.now(UTC) + timedelta(minutes=offset_minutes)).isoformat()
    result = await _create(**await _sign(key, signed_at=moment))
    assert result["code"] == "principal_signature_stale"


async def test_signature_inside_time_window_is_accepted():
    key = _new_key()
    await _register(key)
    moment = (datetime.now(UTC) - timedelta(minutes=14)).isoformat()
    result = await _create(**await _sign(key, signed_at=moment))
    assert result["status"] == "created"


async def test_signed_at_without_timezone_is_refused():
    key = _new_key()
    await _register(key)
    signed = await _sign(key)
    signed["signed_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
    result = await _create(**signed)
    assert result["code"] == "signed_at_invalid"


async def test_malformed_signature_is_refused():
    key = _new_key()
    await _register(key)
    signed = await _sign(key)
    signed["principal_signature"] = "abc"
    result = await _create(**signed)
    assert result["code"] == "principal_signature_invalid"


async def test_replayed_signature_is_refused():
    key = _new_key()
    await _register(key)
    signed = await _sign(key)
    assert (await _create(**signed))["status"] == "created"
    result = await _create(**signed)
    assert result["code"] == "principal_signature_replayed"


async def test_replay_with_padded_signature_is_refused():
    key = _new_key()
    await _register(key)
    signed = await _sign(key)
    assert (await _create(**signed))["status"] == "created"
    result = await _create(**{**signed, "principal_signature": signed["principal_signature"] + "="})
    assert result["code"] == "principal_signature_replayed"


async def test_require_principal_signature_refuses_unsigned(monkeypatch):
    monkeypatch.setattr("amr.config.settings.require_principal_signature", True)
    result = await _create(**BASE)
    assert result["code"] == "principal_signature_required"


async def test_require_principal_signature_accepts_signed(monkeypatch):
    monkeypatch.setattr("amr.config.settings.require_principal_signature", True)
    key = _new_key()
    await _register(key)
    result = await _create(**await _sign(key))
    assert result["status"] == "created"


async def test_unregistered_principal_without_signature_works_as_before():
    result = await _create(**BASE)
    assert result["status"] == "created"
    assert result["principal_signature"] is None


async def test_mandates_created_before_key_registration_stay_valid():
    before = await _create(**BASE)
    await _register(_new_key())
    verdict = json.loads(await verify_mandate(AGENT, "open a pull request"))
    assert verdict["authorized"] is True
    assert verdict["mandate_id"] == before["mandate_id"]


# ---------------------------------------------------------------------------
# Hash chain compatibility
# ---------------------------------------------------------------------------


def _row(db_path: Path, mandate_id: str) -> sqlite3.Row:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
    finally:
        conn.close()


def _legacy_hash_data(row: sqlite3.Row) -> dict:
    legal = json.loads(row["legal_basis_json"])
    return {
        "id": row["id"],
        "principal_id": row["principal_id"],
        "agent_id": row["agent_id"],
        "scope": row["scope"],
        "legal_basis_regulation": legal["regulation"],
        "legal_basis_article": legal["article"],
        "legal_basis_jurisdiction": legal["jurisdiction"],
        "duration_hours": BASE["duration_hours"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "parent_mandate_id": row["parent_mandate_id"],
    }


async def test_unsigned_mandate_hash_is_unchanged(temp_db):
    result = await _create(**BASE)
    row = _row(temp_db, result["mandate_id"])
    assert result["chain_hash"] == compute_hash(_legacy_hash_data(row), "")
    assert row["principal_signature"] is None


async def test_signed_mandate_hash_seals_the_signature(temp_db):
    key = _new_key()
    registered = await _register(key)
    signed = await _sign(key)
    result = await _create(**signed)
    row = _row(temp_db, result["mandate_id"])
    data = _legacy_hash_data(row)
    data["principal_signature"] = {
        "signature": signed["principal_signature"],
        "signed_at": signed["signed_at"],
        "key_id": registered["key_id"],
    }
    assert result["chain_hash"] == compute_hash(data, "")


async def test_principal_keys_are_chained(temp_db):
    first = await _register(_new_key(), "user:one")
    second = await _register(_new_key(), "user:two")
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM principal_keys ORDER BY rowid").fetchall()
    conn.close()
    previous = ""
    for row, result in zip(rows, (first, second), strict=True):
        record = {
            "context": "amr.principal_key.v1",
            "principal_id": row["principal_id"],
            "public_key": row["public_key"],
            "key_id": row["key_id"],
            "proof_signature": row["proof_signature"],
            "registered_at": row["registered_at"],
        }
        assert row["chain_hash"] == compute_hash(record, previous) == result["chain_hash"]
        previous = row["chain_hash"]


# ---------------------------------------------------------------------------
# Proof Pack
# ---------------------------------------------------------------------------


async def test_proof_pack_keeps_and_verifies_the_signature():
    key = _new_key()
    await _register(key)
    signed = await _sign(key, allowed_actions=["code.pull_request.open"])
    created = await _create(**signed)
    proof = json.loads(await get_proof(created["mandate_id"]))
    signature = proof["mandate"]["principal_signature"]
    assert signature["signature"] == signed["principal_signature"]
    assert signature["public_key"] == _pub(key)
    assert signature["algorithm"] == "Ed25519"
    assert proof["chain_integrity"]["principal_signature_valid"] is True
    # Anyone can re-check it with the payload and public key alone.
    key.public_key().verify(_b64(signature["signature"]), signature["payload"].encode("utf-8"))


def _b64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


async def test_proof_pack_of_unsigned_mandate():
    created = await _create(**BASE)
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["mandate"]["principal_signature"] is None
    assert proof["chain_integrity"]["principal_signature_valid"] is None


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("scope", "Merge anything"),
        ("agent_id", "agent:intruder"),
        ("perimeter_json", json.dumps({"allowed_actions": ["*"]})),
        ("principal_signed_at", "2026-01-01T00:00:00+00:00"),
        ("expires_at", "2099-01-01T00:00:00+00:00"),
    ],
)
async def test_proof_pack_detects_a_tampered_mandate(temp_db, column, value):
    key = _new_key()
    await _register(key)
    created = await _create(**await _sign(key, allowed_actions=["code.pull_request.open"]))
    conn = sqlite3.connect(str(temp_db))
    # Tampering on purpose, as an attacker with file access would.
    conn.execute(
        {
            "scope": "UPDATE mandates SET scope = ? WHERE id = ?",
            "agent_id": "UPDATE mandates SET agent_id = ? WHERE id = ?",
            "perimeter_json": "UPDATE mandates SET perimeter_json = ? WHERE id = ?",
            "principal_signed_at": "UPDATE mandates SET principal_signed_at = ? WHERE id = ?",
            "expires_at": "UPDATE mandates SET expires_at = ? WHERE id = ?",
        }[column],
        (value, created["mandate_id"]),
    )
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is False


async def test_proof_pack_detects_a_swapped_key(temp_db):
    key = _new_key()
    await _register(key)
    created = await _create(**await _sign(key))
    conn = sqlite3.connect(str(temp_db))
    conn.execute(
        "UPDATE principal_keys SET public_key = ? WHERE principal_id = ?",
        (_pub(_new_key()), PRINCIPAL),
    )
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is False


def _sql(db_path: Path, statement: str, params: tuple) -> None:
    """Tamper with the database on purpose, as an attacker with file access would."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(statement, params)
    conn.commit()
    conn.close()


async def test_proof_pack_detects_a_stripped_signature(temp_db):
    key = _new_key()
    await _register(key)
    created = await _create(**await _sign(key))
    _sql(
        temp_db,
        "UPDATE mandates SET principal_signature = NULL, principal_signed_at = NULL, "
        "principal_key_id = NULL, principal_signed_payload = NULL WHERE id = ?",
        (created["mandate_id"],),
    )
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["mandate"]["principal_signature"] is None
    assert proof["chain_integrity"]["principal_signature_valid"] is False


async def test_proof_pack_of_mandate_created_before_key_registration():
    created = await _create(**BASE)
    await _register(_new_key())
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is None


async def test_proof_pack_detects_a_replaced_key_without_its_proof(temp_db):
    """A key swapped in the database fails its stored proof of possession.

    (An attacker who also rewrites the proof is not detected: see spec, Known limits.)
    """
    key = _new_key()
    await _register(key)
    signed = await _sign(key)
    created = await _create(**signed)
    forged = _new_key()
    forged_raw = forged.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    forged_key_id = key_id(forged_raw)
    row = _row(temp_db, created["mandate_id"])
    forged_signature = b64url_encode(forged.sign(row["principal_signed_payload"].encode("utf-8")))
    _sql(
        temp_db,
        "UPDATE principal_keys SET public_key = ?, key_id = ? WHERE principal_id = ?",
        (_pub(forged), forged_key_id, PRINCIPAL),
    )
    _sql(
        temp_db,
        "UPDATE mandates SET principal_signature = ?, principal_key_id = ? WHERE id = ?",
        (forged_signature, forged_key_id, created["mandate_id"]),
    )
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is False


async def test_proof_pack_survives_a_damaged_payload(temp_db):
    key = _new_key()
    await _register(key)
    created = await _create(**await _sign(key))
    _sql(
        temp_db,
        "UPDATE mandates SET principal_signed_payload = NULL WHERE id = ?",
        (created["mandate_id"],),
    )
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert "error" not in proof
    assert proof["chain_integrity"]["principal_signature_valid"] is False


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


async def _signed_sub_mandate() -> dict:
    root = await _create(**BASE, allowed_actions=["code.*"], delegation_allowed=True)
    agent_key = _new_key()
    await _register(agent_key, AGENT)
    sub = {
        **BASE,
        "principal_id": AGENT,
        "agent_id": "agent:helper",
        "parent_mandate_id": root["mandate_id"],
        "allowed_actions": ["code.test.run"],
        "duration_hours": 12.0,
    }
    assert (await _create(**sub))["code"] == "principal_signature_required"
    prepared = json.loads(await prepare_mandate_signature(**sub))
    signature = b64url_encode(agent_key.sign(prepared["payload"].encode("utf-8")))
    created = await _create(**sub, principal_signature=signature, signed_at=prepared["signed_at"])
    assert created["status"] == "created"
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is True
    return created


async def test_sub_mandate_from_an_agent_with_a_key_must_be_signed():
    assert (await _signed_sub_mandate())["status"] == "created"


async def test_proof_pack_detects_a_widened_sub_mandate_perimeter(temp_db):
    created = await _signed_sub_mandate()
    widened = json.dumps(
        {
            "allowed_actions": ["*"],
            "forbidden_actions": [],
            "delegation_allowed": False,
            "max_amount": None,
            "currency": "EUR",
            "amount_actions": [],
        }
    )
    _sql(
        temp_db,
        "UPDATE mandates SET perimeter_json = ? WHERE id = ?",
        (widened, created["mandate_id"]),
    )
    proof = json.loads(await get_proof(created["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is False


# ---------------------------------------------------------------------------
# prepare_mandate_signature and migration
# ---------------------------------------------------------------------------


async def test_prepare_returns_canonical_payload():
    moment = "2026-10-18T20:30:00+00:00"
    prepared = json.loads(await prepare_mandate_signature(**BASE, signed_at=moment))
    payload = json.loads(prepared["payload"])
    assert payload["context"] == "amr.mandate.v1"
    assert payload["signed_at"] == moment
    assert payload["perimeter"] is None
    assert prepared["payload"] == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert _b64(prepared["payload_b64url"]) == prepared["payload"].encode("utf-8")


async def test_prepare_defaults_signed_at_to_now():
    prepared = json.loads(await prepare_mandate_signature(**BASE))
    moment = datetime.fromisoformat(prepared["signed_at"])
    assert abs(datetime.now(UTC) - moment) < timedelta(seconds=10)


async def test_prepare_rejects_invalid_input():
    prepared = json.loads(await prepare_mandate_signature(**{**BASE, "duration_hours": 0}))
    assert "error" in prepared


_V3_MANDATES = """
CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
INSERT INTO schema_version VALUES (2), (3);
CREATE TABLE mandates (
    id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, agent_id TEXT NOT NULL,
    scope TEXT NOT NULL, legal_basis_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, parent_mandate_id TEXT REFERENCES mandates(id),
    metadata_json TEXT NOT NULL DEFAULT '{}', chain_hash TEXT NOT NULL,
    perimeter_json TEXT
);
INSERT INTO mandates VALUES ('m1', 'p', 'a', 's', '{}', 'active',
    '2026-01-01T00:00:00+00:00', '2027-01-01T00:00:00+00:00', NULL, '{}', 'h', NULL);
"""


async def test_v3_database_is_migrated_without_touching_rows(temp_db):
    conn = sqlite3.connect(str(temp_db))
    conn.executescript(_V3_MANDATES)
    conn.close()
    before = _row(temp_db, "m1")
    await init_db(temp_db)
    await init_db(temp_db)  # idempotent
    after = _row(temp_db, "m1")
    assert list(after)[: len(before)] == list(before)
    assert after["principal_signature"] is None
    conn = sqlite3.connect(str(temp_db))
    versions = {v for (v,) in conn.execute("SELECT version FROM schema_version")}
    tables = {t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert 4 in versions
    assert "principal_keys" in tables
