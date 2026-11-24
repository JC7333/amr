"""The receiver's receipt: what the system that received an action declares it did.

The registry knows it authorized an action (the token) and what the agent declared
(log_action). record_action_receipt adds the receiver's own line; get_proof then shows,
for each action, the three lines and which one is missing.
"""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.signing import generate_signing_key, get_key_id, load_signing_key
from amr.db.engine import init_db
from amr.server import TOOL_PROFILES
from amr.tools import record_action_receipt as receipt_module
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import log_action
from amr.tools.record_action_receipt import receipt_hash_data, record_action_receipt
from amr.tools.revoke_mandate import revoke_mandate

PRINCIPAL = "org:hospital"
AGENT = "agent:scribe"
AUDIENCE = "receiver://patient-record"
NOTE_SHA = hashlib.sha256(b"Consultation note, validated").hexdigest()

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Write consultation notes into the patient record",
    "legal_basis_regulation": "Delegation of authority",
    "legal_basis_article": "Section 2",
    "duration_hours": 24.0,
    "allowed_actions": ["note.*"],
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _mandate(**overrides: object) -> str:
    result = json.loads(await create_mandate(**{**BASE, **overrides}))
    assert result.get("status") == "created", result
    return result["mandate_id"]


async def _token(mandate_id: str, action_type: str = "note.write") -> str:
    result = json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=AGENT,
            action=f"{action_type} {uuid4()}",
            audience=AUDIENCE,
            action_type=action_type,
        )
    )
    assert "token" in result, result
    return result["token"]


async def _receipt(token: str, audience: str = AUDIENCE, **kw: object) -> dict:
    params: dict = {"outcome": "executed", **kw}
    return json.loads(await record_action_receipt(token, audience, **params))


async def _proof(mandate_id: str) -> dict:
    proof = json.loads(await get_proof(mandate_id))
    assert "error" not in proof, proof
    return proof


def _registry_pem() -> bytes:
    return load_signing_key().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def _forge(claims: dict, key_pem: bytes | None = None, kid: str | None = None) -> str:
    return jwt.encode(
        claims,
        key_pem if key_pem is not None else _registry_pem(),
        algorithm="EdDSA",
        headers={"kid": kid if kid is not None else get_key_id(), "typ": "JWT"},
    )


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list:
    with sqlite3.connect(db_path) as db:
        rows = db.execute(statement, params).fetchall()
        db.commit()
    return rows


# --- recording ---------------------------------------------------------------------------


async def test_executed_receipt_is_recorded_with_what_was_received(temp_db: Path) -> None:
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    result = await _receipt(token, received_content_sha256=NOTE_SHA)
    assert result["status"] == "recorded"
    assert result["outcome"] == "executed"
    assert result["jti"] == _claims(token)["jti"]
    assert result["mandate_id"] == mandate_id
    assert result["agent_id"] == AGENT
    assert result["received_content_sha256"] == NOTE_SHA
    assert "refusal_reason" not in result
    assert result["agent_declaration_action_id"] is None
    rows = _sql(temp_db, "SELECT outcome, refusal_reason, audience FROM action_receipts")
    assert rows == [("executed", "", AUDIENCE)]


async def test_refused_receipt_keeps_its_reason() -> None:
    token = await _token(await _mandate())
    result = await _receipt(token, outcome="refused", refusal_reason="note does not match")
    assert result["outcome"] == "refused"
    assert result["refusal_reason"] == "note does not match"


async def test_receipt_names_the_action_the_agent_logged_with_the_token() -> None:
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    logged = json.loads(await log_action(mandate_id, "Wrote the note", action_token=token))
    assert logged["status"] == "logged", logged
    result = await _receipt(token)
    assert result["agent_declaration_action_id"] == logged["action_id"]


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"outcome": "refused"}, None),
        ({"outcome": "refused", "refusal_reason": "   "}, None),
        ({"outcome": "executed", "refusal_reason": "why not"}, None),
        ({"outcome": "done"}, "outcome"),
        ({"received_content_sha256": "ABC"}, "received_content_sha256"),
        ({"received_content_sha256": "0" * 63}, "received_content_sha256"),
        ({"outcome": "refused", "refusal_reason": "x" * 501}, "refusal_reason"),
    ],
)
async def test_bad_input_is_refused_and_records_nothing(
    temp_db: Path, kw: dict, field: str | None
) -> None:
    token = await _token(await _mandate())
    result = await _receipt(token, **kw)
    assert result["code"] == "invalid_input", result
    if field is not None:
        assert result["field"] == field
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_receipts") == [(0,)]


async def test_a_second_receipt_for_the_same_token_is_refused(temp_db: Path) -> None:
    token = await _token(await _mandate())
    assert (await _receipt(token))["status"] == "recorded"
    again = await _receipt(token, outcome="refused", refusal_reason="changed my mind")
    assert again["code"] == "receipt_already_recorded"
    assert _sql(temp_db, "SELECT outcome FROM action_receipts") == [("executed",)]


async def test_receipt_for_another_audience_is_refused(temp_db: Path) -> None:
    token = await _token(await _mandate())
    result = await _receipt(token, audience="receiver://someone-else")
    assert result["code"] == "wrong_audience"
    assert result["field"] == "audience"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_receipts") == [(0,)]


async def test_receipt_for_a_token_the_registry_never_issued_is_refused(temp_db: Path) -> None:
    mandate_id = await _mandate()
    real = _claims(await _token(mandate_id))
    forged = _forge({**real, "jti": str(uuid4())})
    result = await _receipt(forged)
    assert result["code"] == "unknown_token"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_receipts") == [(0,)]


async def test_receipt_for_a_token_that_does_not_match_its_record_is_refused() -> None:
    mandate_id = await _mandate()
    real = _claims(await _token(mandate_id))
    for change in ({"amr_action_hash": "1" * 64}, {"sub": "agent:other"}):
        result = await _receipt(_forge({**real, **change}))
        assert result["code"] == "token_record_mismatch", change


async def test_receipt_for_a_token_signed_by_another_key_is_refused() -> None:
    mandate_id = await _mandate()
    real = _claims(await _token(mandate_id))
    other = ed25519.Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    assert (await _receipt(_forge(real, key_pem=other)))["code"] == "bad_signature"
    assert (await _receipt(_forge(real, kid="other-key")))["code"] == "key_mismatch"


async def test_receipt_for_a_token_not_yet_valid_is_refused() -> None:
    mandate_id = await _mandate()
    real = _claims(await _token(mandate_id))
    later = int(datetime.now(UTC).timestamp()) + 3600
    result = await _receipt(_forge({**real, "nbf": later}))
    assert result["code"] == "token_not_yet_valid"


async def test_receipt_after_expiry_is_accepted_within_seven_days() -> None:
    mandate_id = await _mandate()
    real = _claims(await _token(mandate_id))
    past = int(datetime.now(UTC).timestamp()) - 3 * 86400
    # Same jti and record fields: only exp (and iat/nbf) moved into the past.
    result = await _receipt(_forge({**real, "iat": past - 60, "nbf": past - 60, "exp": past}))
    assert result["status"] == "recorded", result


async def test_receipt_more_than_seven_days_after_expiry_is_refused(temp_db: Path) -> None:
    mandate_id = await _mandate()
    real = _claims(await _token(mandate_id))
    past = int(datetime.now(UTC).timestamp()) - 8 * 86400
    result = await _receipt(_forge({**real, "iat": past - 60, "nbf": past - 60, "exp": past}))
    assert result["code"] == "receipt_too_late"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_receipts") == [(0,)]


def test_late_window_is_seven_days() -> None:
    assert timedelta(days=7) == receipt_module.RECEIPT_LATE_WINDOW


async def test_receipt_after_the_mandate_was_withdrawn_is_accepted() -> None:
    """Decided: a refusal because of the withdrawal is exactly what to record."""
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    revoked = json.loads(await revoke_mandate(mandate_id, "Agent replaced"))
    assert revoked.get("status") == "revoked", revoked
    result = await _receipt(token, outcome="refused", refusal_reason="mandate withdrawn")
    assert result["status"] == "recorded", result
    proof = await _proof(mandate_id)
    assert proof["mandate"]["status"] == "revoked"
    assert proof["action_trail"][0]["receiver_receipt"]["refusal_reason"] == "mandate withdrawn"


async def test_no_registry_database_is_never_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    missing = tmp_path / "elsewhere" / "none.db"
    monkeypatch.setattr("amr.config.settings.db_path", missing)
    result = await _receipt(token)
    assert result["code"] == "registry_unavailable"
    assert not missing.exists()


async def test_receipts_are_chained_across_the_registry(temp_db: Path) -> None:
    first_mandate = await _mandate()
    second_mandate = await _mandate(agent_id=AGENT, scope="Another ward")
    one = await _receipt(await _token(first_mandate))
    two = await _receipt(await _token(second_mandate))
    rows = _sql(
        temp_db,
        "SELECT jti, mandate_id, agent_id, action_hash, audience, outcome, refusal_reason, "
        "received_content_sha256, recorded_at, chain_hash FROM action_receipts ORDER BY rowid",
    )
    keys = (
        "jti", "mandate_id", "agent_id", "action_hash", "audience", "outcome",
        "refusal_reason", "received_content_sha256", "recorded_at", "chain_hash",
    )
    first, second = (dict(zip(keys, row, strict=True)) for row in rows)
    mandate_hashes = dict(_sql(temp_db, "SELECT id, chain_hash FROM mandates"))
    assert first["chain_hash"] == compute_hash(
        receipt_hash_data(first, mandate_hashes[first_mandate]), ""
    )
    assert second["chain_hash"] == compute_hash(
        receipt_hash_data(second, mandate_hashes[second_mandate]), first["chain_hash"]
    )
    assert (one["chain_hash"], two["chain_hash"]) == (first["chain_hash"], second["chain_hash"])


# --- the three lines in the proof --------------------------------------------------------


async def test_proof_shows_three_lines_and_which_one_is_missing() -> None:
    mandate_id = await _mandate()
    complete = await _token(mandate_id)
    logged = json.loads(await log_action(mandate_id, "Wrote the note", action_token=complete))
    await _receipt(complete, received_content_sha256=NOTE_SHA)
    unanswered = await _token(mandate_id, "note.read")
    untokened = json.loads(await log_action(mandate_id, "Read the agenda"))

    proof = await _proof(mandate_id)
    trail = proof["action_trail"]
    assert [entry["missing"] for entry in trail] == [
        [],
        ["agent_declaration", "receiver_receipt"],
        ["authorization", "receiver_receipt"],
    ]
    first, second, third = trail
    assert first["jti"] == _claims(complete)["jti"]
    assert first["authorization"]["audience"] == AUDIENCE
    assert first["authorization"]["action_hash"] == _claims(complete)["amr_action_hash"]
    assert first["agent_declaration"]["action_id"] == logged["action_id"]
    assert first["receiver_receipt"]["outcome"] == "executed"
    assert first["receiver_receipt"]["received_content_sha256"] == NOTE_SHA
    assert first["receiver_receipt"]["refusal_reason"] is None
    assert second["jti"] == _claims(unanswered)["jti"]
    assert third["jti"] is None
    assert third["agent_declaration"]["action_id"] == untokened["action_id"]
    assert proof["chain_integrity"]["receipts_intact"] is True
    assert proof["chain_integrity"]["actions_with_receipt"] == 1


async def test_receipt_without_the_agents_declaration_shows_it_missing() -> None:
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    await _receipt(token, outcome="refused", refusal_reason="no validated note")
    entry = (await _proof(mandate_id))["action_trail"][0]
    assert entry["missing"] == ["agent_declaration"]
    assert entry["receiver_receipt"]["outcome"] == "refused"


async def test_mandate_without_receipts_keeps_its_proof_and_hashes() -> None:
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    await log_action(mandate_id, "Wrote the note", action_token=token)
    await log_action(mandate_id, "Plain entry")
    proof = await _proof(mandate_id)
    assert proof["chain_integrity"]["receipts_intact"] is None
    assert proof["chain_integrity"]["actions_with_receipt"] == 0
    assert proof["chain_integrity"]["actions_chain_valid"] is True
    assert all(entry["receiver_receipt"] is None for entry in proof["action_trail"])


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        ("UPDATE action_receipts SET outcome = ?", ("refused",)),
        ("UPDATE action_receipts SET received_content_sha256 = ?", ("1" * 64,)),
        ("UPDATE action_receipts SET recorded_at = ?", ("2026-01-01T00:00:00+00:00",)),
        ("UPDATE action_receipts SET chain_hash = ?", ("2" * 64,)),
    ],
)
async def test_an_edited_receipt_is_detected(temp_db: Path, statement: str, params: tuple) -> None:
    mandate_id = await _mandate()
    await _receipt(await _token(mandate_id), received_content_sha256=NOTE_SHA)
    _sql(temp_db, statement, params)
    assert (await _proof(mandate_id))["chain_integrity"]["receipts_intact"] is False


async def test_a_receipt_rewritten_for_another_action_is_detected(temp_db: Path) -> None:
    """The row recomputes, but it no longer matches the token the registry issued."""
    mandate_id = await _mandate()
    await _receipt(await _token(mandate_id))
    rows = _sql(
        temp_db,
        "SELECT jti, mandate_id, agent_id, action_hash, audience, outcome, refusal_reason, "
        "received_content_sha256, recorded_at FROM action_receipts",
    )
    keys = (
        "jti", "mandate_id", "agent_id", "action_hash", "audience", "outcome",
        "refusal_reason", "received_content_sha256", "recorded_at",
    )
    receipt = dict(zip(keys, rows[0], strict=True))
    receipt["action_hash"] = "3" * 64
    mandate_hash = _sql(temp_db, "SELECT chain_hash FROM mandates")[0][0]
    rehashed = compute_hash(receipt_hash_data(receipt, mandate_hash), "")
    _sql(
        temp_db,
        "UPDATE action_receipts SET action_hash = ?, chain_hash = ?",
        ("3" * 64, rehashed),
    )
    assert (await _proof(mandate_id))["chain_integrity"]["receipts_intact"] is False


async def test_a_deleted_earlier_receipt_breaks_the_next_one(temp_db: Path) -> None:
    mandate_id = await _mandate()
    first = await _receipt(await _token(mandate_id))
    await _receipt(await _token(mandate_id, "note.read"))
    _sql(temp_db, "DELETE FROM action_receipts WHERE jti = ?", (first["jti"],))
    assert (await _proof(mandate_id))["chain_integrity"]["receipts_intact"] is False


# --- insurer dossier, schema, profiles ---------------------------------------------------


async def test_insurer_dossier_carries_the_three_lines() -> None:
    mandate_id = await _mandate()
    token = await _token(mandate_id)
    await log_action(mandate_id, "Wrote the note", action_token=token)
    await _receipt(token)
    dossier = json.loads(await export_insurer_dossier(mandate_id))["dossier"]
    assert [entry["missing"] for entry in dossier["action_trail"]] == [[]]
    assert dossier["integrity"]["receipts_intact"] is True
    assert any("receipt" in limit for limit in dossier["limits"])


async def test_insurer_dossier_keeps_only_the_period() -> None:
    mandate_id = await _mandate()
    await _receipt(await _token(mandate_id))
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    dossier = json.loads(
        await export_insurer_dossier(mandate_id, period_start=later)
    )
    # The period starts after now, so period_end defaults to now: refused as invalid.
    assert dossier.get("code") == "invalid_input"
    earlier = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    before = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    dossier = json.loads(
        await export_insurer_dossier(mandate_id, period_start=earlier, period_end=before)
    )["dossier"]
    assert dossier["action_trail"] == []


async def test_schema_version_13_is_recorded(temp_db: Path) -> None:
    await init_db(temp_db)
    versions = {row[0] for row in _sql(temp_db, "SELECT version FROM schema_version")}
    assert 13 in versions


def test_only_the_receiver_profile_records_receipts() -> None:
    holders = {name for name, tools in TOOL_PROFILES.items() if "record_action_receipt" in tools}
    assert holders == {"full", "receiver"}


async def test_receipt_for_a_token_of_another_issuer_is_refused() -> None:
    real = _claims(await _token(await _mandate()))
    assert real["iss"] == settings.token_issuer
    result = await _receipt(_forge({**real, "iss": "https://other-registry.example"}))
    assert result["code"] == "wrong_issuer"
