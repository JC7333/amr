"""Tests for revoke_mandate: the principal's stop button, append-only and chained.

Answers a question asked on 23/10/2026: what triggers a revocation, and how fast does
it take effect? The principal triggers it (signed when it has a key), it takes effect
for every new check at once, and tokens already issued live until their exp.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.crypto.chain import compute_hash
from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.db.engine import init_db
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.issue_mandate_attestation import issue_mandate_attestation
from amr.tools.log_action import log_action
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.revoke_mandate import prepare_revocation_signature, revoke_mandate
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"

ROOT = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Handle supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
    "allowed_actions": ["invoice.*"],
    "delegation_allowed": True,
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _create(**overrides: object) -> dict:
    result = json.loads(await create_mandate(**{**ROOT, **overrides}))
    assert result.get("status") == "created", result
    return result


async def _sub(parent_id: str, **overrides: object) -> dict:
    params: dict = {
        "principal_id": AGENT,
        "agent_id": HELPER,
        "scope": "Read invoices only",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 12.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["invoice.read"],
    }
    params.update(overrides)
    return json.loads(await create_mandate(**params))


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


async def _revoke(mandate_id: str, reason: str = "agent exceeded its order limit", **kw) -> dict:
    return json.loads(await revoke_mandate(mandate_id, reason, **kw))


async def _proof(mandate_id: str) -> dict:
    return json.loads(await get_proof(mandate_id))


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
    return rows


def _new_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


async def _register(key: ed25519.Ed25519PrivateKey, principal_id: str = PRINCIPAL) -> None:
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, _pub(key))))
    result = json.loads(await register_principal_key(principal_id, _pub(key), proof))
    assert result["status"] == "registered", result


async def _signed_root(key: ed25519.Ed25519PrivateKey) -> dict:
    prepared = json.loads(await prepare_mandate_signature(**ROOT))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return await _create(principal_signature=signature, signed_at=prepared["signed_at"])


async def _signed_revocation(
    key: ed25519.Ed25519PrivateKey, mandate_id: str, reason: str, signed_at: str | None = None
) -> dict:
    prepared = json.loads(await prepare_revocation_signature(mandate_id, reason, signed_at))
    return {
        "principal_signature": b64url_encode(key.sign(prepared["payload"].encode("utf-8"))),
        "signed_at": prepared["signed_at"],
    }


# --- Effect -------------------------------------------------------------------------


async def test_revocation_returns_the_record() -> None:
    root = await _create()
    result = await _revoke(root["mandate_id"])
    assert result["status"] == "revoked"
    assert result["mandate_id"] == root["mandate_id"]
    assert result["principal_id"] == PRINCIPAL
    assert result["reason"] == "agent exceeded its order limit"
    assert result["principal_signature"] is None
    assert len(result["chain_hash"]) == 64
    assert datetime.fromisoformat(result["revoked_at"]) <= datetime.now(UTC)


async def test_revoked_mandate_gets_no_token() -> None:
    root = await _create()
    assert "token" in await _token(root["mandate_id"])
    await _revoke(root["mandate_id"])
    denied = await _token(root["mandate_id"])
    assert denied["denied"] is True
    assert denied["reason"] == "mandate_status_revoked"


async def test_revoked_mandate_is_not_returned_by_verify() -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    result = json.loads(await verify_mandate(AGENT, "pay"))
    assert result["authorized"] is False
    assert result["mandate_id"] is None


async def test_verify_falls_back_to_an_older_unrevoked_mandate() -> None:
    older = await _create()
    newer = await _create()
    await _revoke(newer["mandate_id"])
    result = json.loads(await verify_mandate(AGENT, "pay"))
    assert result["authorized"] is True
    assert result["mandate_id"] == older["mandate_id"]


async def test_revoking_the_parent_cuts_existing_sub_mandates() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    assert "token" in await _token(child["mandate_id"], HELPER)
    await _revoke(root["mandate_id"])
    denied = await _token(child["mandate_id"], HELPER)
    assert denied["reason"] == "parent_mandate_revoked"
    assert denied["refused_by"] == root["mandate_id"]
    verdict = json.loads(await verify_mandate(HELPER, "read"))
    assert verdict["authorized"] is False
    assert verdict["reason"] == "Delegation chain broken: parent_mandate_revoked"


async def test_revoking_a_grandparent_cuts_the_whole_branch() -> None:
    root = await _create()
    middle = await _sub(root["mandate_id"], allowed_actions=["invoice.*"],
                        delegation_allowed=True)
    leaf = await _sub(middle["mandate_id"], principal_id=HELPER, agent_id="agent:leaf",
                      duration_hours=6.0)
    assert leaf["status"] == "created", leaf
    await _revoke(root["mandate_id"])
    denied = await _token(leaf["mandate_id"], "agent:leaf")
    assert denied["reason"] == "parent_mandate_revoked"
    assert denied["refused_by"] == root["mandate_id"]


async def test_no_sub_mandate_under_a_revoked_parent() -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    child = await _sub(root["mandate_id"])
    assert child["code"] == "parent_mandate_revoked"


async def test_revoking_a_sub_mandate_leaves_the_parent_working() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    result = await _revoke(child["mandate_id"])
    assert result["principal_id"] == AGENT
    assert (await _token(child["mandate_id"], HELPER))["reason"] == "mandate_status_revoked"
    assert "token" in await _token(root["mandate_id"])


async def test_revocation_is_final() -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    again = await _revoke(root["mandate_id"], reason="second try")
    assert again["code"] == "mandate_already_revoked"


async def test_revocation_accepts_an_uppercase_id(temp_db: Path) -> None:
    root = await _create()
    result = await _revoke(root["mandate_id"].upper())
    assert result["mandate_id"] == root["mandate_id"]
    assert (await _token(root["mandate_id"]))["reason"] == "mandate_status_revoked"


async def test_expired_mandate_can_still_be_revoked(temp_db: Path) -> None:
    root = await _create()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    _sql(temp_db, "UPDATE mandates SET expires_at = ? WHERE id = ?", (past, root["mandate_id"]))
    assert (await _revoke(root["mandate_id"]))["status"] == "revoked"


# --- Input --------------------------------------------------------------------------


async def test_unknown_mandate_is_refused() -> None:
    result = await _revoke(str(uuid4()))
    assert result["code"] == "mandate_not_found"


@pytest.mark.parametrize(
    ("mandate_id", "reason"),
    [("not-a-uuid", "stop"), (None, "stop"), ("ok", ""), ("ok", "x" * 501)],
)
async def test_invalid_input_is_refused(mandate_id: str | None, reason: str) -> None:
    if mandate_id == "ok":
        mandate_id = (await _create())["mandate_id"]
    result = json.loads(await revoke_mandate(mandate_id, reason))  # type: ignore[arg-type]
    assert result["code"] == "invalid_input"


async def test_failed_revocation_writes_nothing(temp_db: Path) -> None:
    root = await _create()
    await revoke_mandate(root["mandate_id"], "")
    await _revoke(str(uuid4()))
    assert _sql(temp_db, "SELECT COUNT(*) FROM mandate_revocations") == [(0,)]
    assert _sql(temp_db, "SELECT COUNT(*) FROM mandate_events") == [(0,)]


# --- Append-only record and chain ---------------------------------------------------


async def test_mandate_row_is_never_updated(temp_db: Path) -> None:
    root = await _create()
    before = _sql(temp_db, "SELECT * FROM mandates")
    await _revoke(root["mandate_id"])
    assert _sql(temp_db, "SELECT * FROM mandates") == before


async def test_revocation_writes_one_record_and_one_event(temp_db: Path) -> None:
    root = await _create()
    result = await _revoke(root["mandate_id"])
    rows = _sql(temp_db, "SELECT mandate_id, reason, revoked_at FROM mandate_revocations")
    assert rows == [(root["mandate_id"], result["reason"], result["revoked_at"])]
    events = _sql(temp_db, "SELECT mandate_id, event_type, timestamp, reason FROM mandate_events")
    assert events == [(root["mandate_id"], "revoked", result["revoked_at"], result["reason"])]


async def test_revocations_are_chained() -> None:
    first = await _create()
    second = await _create()
    one = await _revoke(first["mandate_id"])
    two = await _revoke(second["mandate_id"], reason="contract ended")
    expected_one = compute_hash(
        {
            "mandate_id": first["mandate_id"],
            "mandate_chain_hash": first["chain_hash"],
            "principal_id": PRINCIPAL,
            "reason": one["reason"],
            "revoked_at": one["revoked_at"],
        },
        "",
    )
    assert one["chain_hash"] == expected_one
    expected_two = compute_hash(
        {
            "mandate_id": second["mandate_id"],
            "mandate_chain_hash": second["chain_hash"],
            "principal_id": PRINCIPAL,
            "reason": "contract ended",
            "revoked_at": two["revoked_at"],
        },
        one["chain_hash"],
    )
    assert two["chain_hash"] == expected_two


async def test_mandate_hash_and_action_chain_are_unchanged_by_revocation() -> None:
    root = await _create()
    await log_action(mandate_id=root["mandate_id"], action="read invoice 1")
    before = await _proof(root["mandate_id"])
    await _revoke(root["mandate_id"])
    after = await _proof(root["mandate_id"])
    assert after["mandate"]["chain_hash"] == root["chain_hash"]
    assert after["actions"] == before["actions"]
    assert after["chain_integrity"]["actions_chain_valid"] is True


async def test_older_database_gains_the_table(temp_db: Path) -> None:
    root = await _create()
    _sql(temp_db, "DROP TABLE mandate_revocations")
    _sql(temp_db, "DELETE FROM schema_version WHERE version = 6")
    await init_db(temp_db)
    assert _sql(temp_db, "SELECT version FROM schema_version WHERE version = 6") == [(6,)]
    assert "token" in await _token(root["mandate_id"])
    assert (await _revoke(root["mandate_id"]))["status"] == "revoked"


# --- Outstanding tokens: the honest answer to "how fast" ----------------------------


async def test_outstanding_tokens_are_reported() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    first = await _token(root["mandate_id"])
    second = await _token(child["mandate_id"], HELPER, lifetime_override_seconds=600)
    result = await _revoke(root["mandate_id"])
    outstanding = result["outstanding_tokens"]
    assert outstanding["still_valid"] == 2
    assert outstanding["last_expires_at"] == max(first["expires_at"], second["expires_at"])


async def test_expired_tokens_are_not_outstanding() -> None:
    root = await _create()
    expired = await _token(root["mandate_id"], lifetime_override_seconds=-1)
    assert "token" in expired, expired
    result = await _revoke(root["mandate_id"])
    assert result["outstanding_tokens"] == {"still_valid": 0, "last_expires_at": None}


# --- Proof Pack and insurer dossier -------------------------------------------------


async def test_proof_reports_the_revocation() -> None:
    root = await _create()
    result = await _revoke(root["mandate_id"])
    proof = await _proof(root["mandate_id"])
    assert proof["mandate"]["status"] == "revoked"
    revocation = proof["mandate"]["revocation"]
    assert revocation["revoked_at"] == result["revoked_at"]
    assert revocation["reason"] == result["reason"]
    assert revocation["chain_hash"] == result["chain_hash"]
    assert revocation["principal_signature"] is None
    assert proof["chain_integrity"]["revocation_signature_valid"] is None
    assert [e["event_type"] for e in proof["events"]] == ["revoked"]


async def test_proof_of_an_unrevoked_mandate_is_unchanged_in_meaning() -> None:
    root = await _create()
    proof = await _proof(root["mandate_id"])
    assert proof["mandate"]["status"] == "active"
    assert proof["mandate"]["revocation"] is None
    assert proof["chain_integrity"]["revocation_signature_valid"] is None


async def test_insurer_dossier_reports_the_revocation_and_the_cut_branch() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    await _revoke(root["mandate_id"])
    dossier = json.loads(await export_insurer_dossier(root["mandate_id"]))["dossier"]
    assert dossier["status"]["in_force"] is False
    assert dossier["status"]["not_in_force_reason"] == "mandate_revoked"
    assert dossier["sub_mandates"][0]["id"] == child["mandate_id"]
    assert dossier["sub_mandates"][0]["status"]["in_force"] is False
    assert [e["event_type"] for e in dossier["events"]] == ["revoked"]


# --- Principal signature ------------------------------------------------------------


async def test_principal_with_a_key_must_sign() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    result = await _revoke(root["mandate_id"])
    assert result["code"] == "principal_signature_required"
    assert "token" in await _token(root["mandate_id"])


async def test_signed_revocation_is_accepted_and_proven() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    reason = "agent exceeded its order limit"
    signed = await _signed_revocation(key, root["mandate_id"], reason)
    result = await _revoke(root["mandate_id"], reason, **signed)
    assert result["status"] == "revoked", result
    assert result["principal_signature"]["signed_at"] == signed["signed_at"]
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is True
    stored = proof["mandate"]["revocation"]["principal_signature"]
    assert stored["signature"] == signed["principal_signature"]
    payload = json.loads(stored["payload"])
    assert payload == {
        "context": "amr.revocation.v1",
        "mandate_id": root["mandate_id"],
        "principal_id": PRINCIPAL,
        "reason": reason,
        "signed_at": signed["signed_at"],
    }


async def test_signature_by_another_key_is_refused() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(_new_key(), root["mandate_id"], "stop")
    result = await _revoke(root["mandate_id"], "stop", **signed)
    assert result["code"] == "principal_signature_invalid"


async def test_signature_does_not_carry_over_to_another_reason() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "contract ended")
    result = await _revoke(root["mandate_id"], "agent misbehaved", **signed)
    assert result["code"] == "principal_signature_invalid"


async def test_signature_does_not_carry_over_to_another_mandate() -> None:
    key = _new_key()
    await _register(key)
    first = await _signed_root(key)
    second = await _signed_root(key)
    signed = await _signed_revocation(key, first["mandate_id"], "stop")
    result = await _revoke(second["mandate_id"], "stop", **signed)
    assert result["code"] == "principal_signature_invalid"


async def test_stale_signature_is_refused() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    signed = await _signed_revocation(key, root["mandate_id"], "stop", signed_at=old)
    result = await _revoke(root["mandate_id"], "stop", **signed)
    assert result["code"] == "principal_signature_stale"


async def test_signature_without_signed_at_is_refused() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "stop")
    result = await _revoke(
        root["mandate_id"], "stop", principal_signature=signed["principal_signature"]
    )
    assert result["code"] == "principal_signature_incomplete"


async def test_signature_for_a_principal_without_key_is_refused() -> None:
    root = await _create()
    signed = await _signed_revocation(_new_key(), root["mandate_id"], "stop")
    result = await _revoke(root["mandate_id"], "stop", **signed)
    assert result["code"] == "principal_key_not_registered"


async def test_registry_requiring_signatures_refuses_unsigned_revocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = await _create()
    monkeypatch.setattr("amr.config.settings.require_principal_signature", True)
    result = await _revoke(root["mandate_id"])
    assert result["code"] == "principal_signature_required"


async def test_tampered_revocation_reason_shows_in_the_proof(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "stop")
    await _revoke(root["mandate_id"], "stop", **signed)
    _sql(temp_db, "UPDATE mandate_revocations SET reason = 'other' WHERE mandate_id = ?",
         (root["mandate_id"],))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is False


async def test_stripped_revocation_signature_shows_in_the_proof(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "stop")
    await _revoke(root["mandate_id"], "stop", **signed)
    _sql(temp_db, "UPDATE mandate_revocations SET principal_signature = NULL WHERE mandate_id = ?",
         (root["mandate_id"],))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is False


async def test_unsigned_revocation_before_key_registration_stays_unproven() -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    await _register(_new_key())
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is None


# --- prepare_revocation_signature ---------------------------------------------------


async def test_prepare_returns_the_exact_payload() -> None:
    root = await _create()
    signed_at = "2026-10-23T20:30:00+00:00"
    prepared = json.loads(await prepare_revocation_signature(root["mandate_id"], "stop",
                                                             signed_at))
    assert prepared["signed_at"] == signed_at
    assert prepared["principal_id"] == PRINCIPAL
    assert prepared["payload"] == (
        '{"context":"amr.revocation.v1","mandate_id":"' + root["mandate_id"]
        + '","principal_id":"org:clinic","reason":"stop","signed_at":"' + signed_at + '"}'
    )


async def test_prepare_refuses_unknown_mandate_and_bad_time() -> None:
    missing = json.loads(await prepare_revocation_signature(str(uuid4()), "stop"))
    assert missing["code"] == "mandate_not_found"
    root = await _create()
    naive = json.loads(await prepare_revocation_signature(root["mandate_id"], "stop",
                                                          "2026-10-23T20:30:00"))
    assert naive["code"] == "signed_at_invalid"


async def test_prepare_writes_nothing(temp_db: Path) -> None:
    root = await _create()
    await prepare_revocation_signature(root["mandate_id"], "stop")
    assert _sql(temp_db, "SELECT COUNT(*) FROM mandate_revocations") == [(0,)]
    assert "token" in await _token(root["mandate_id"])


async def test_second_revocation_by_a_key_holder_says_already_revoked() -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "stop")
    await _revoke(root["mandate_id"], "stop", **signed)
    again = await _revoke(root["mandate_id"], "stop")
    assert again["code"] == "mandate_already_revoked"


async def test_database_refuses_a_second_revocation_row(temp_db: Path) -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    with pytest.raises(sqlite3.IntegrityError):
        _sql(
            temp_db,
            "INSERT INTO mandate_revocations (mandate_id, principal_id, reason, revoked_at, "
            "chain_hash) VALUES (?, ?, ?, ?, ?)",
            (root["mandate_id"], PRINCIPAL, "again", datetime.now(UTC).isoformat(), "0" * 64),
        )


async def test_tampered_revocation_key_id_shows_in_the_proof(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "stop")
    await _revoke(root["mandate_id"], "stop", **signed)
    _sql(temp_db, "UPDATE mandate_revocations SET principal_key_id = 'x' WHERE mandate_id = ?",
         (root["mandate_id"],))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is False


async def test_no_action_is_logged_under_a_revoked_mandate(temp_db: Path) -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    result = json.loads(await log_action(mandate_id=root["mandate_id"], action="paid 10k"))
    assert "revoked" in result["error"]
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(0,)]


async def test_dossier_keeps_the_true_stored_status_and_reports_the_revocation_check() -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    dossier = json.loads(await export_insurer_dossier(root["mandate_id"]))["dossier"]
    assert dossier["status"]["stored_status"] == "active"
    assert dossier["mandate"]["status"] == "revoked"
    assert "revocation_signature_valid" in dossier["integrity"]
    assert dossier["integrity"]["revocation_signature_valid"] is None


async def test_deleted_revocation_record_shows_in_the_proof(temp_db: Path) -> None:
    root = await _create()
    await _revoke(root["mandate_id"])
    _sql(temp_db, "DELETE FROM mandate_revocations")
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is False


async def test_tampered_principal_key_voids_the_revocation_check(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    root = await _signed_root(key)
    signed = await _signed_revocation(key, root["mandate_id"], "stop")
    await _revoke(root["mandate_id"], "stop", **signed)
    _sql(temp_db, "UPDATE principal_keys SET proof_signature = ? WHERE principal_id = ?",
         (b64url_encode(b"\x00" * 64), PRINCIPAL))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["revocation_signature_valid"] is False


async def test_no_attestation_for_a_revoked_mandate(temp_db: Path) -> None:
    root = await _create()
    granted = json.loads(await issue_mandate_attestation(root["mandate_id"], AGENT))
    assert "attestation" in granted, granted
    await _revoke(root["mandate_id"])
    denied = json.loads(await issue_mandate_attestation(root["mandate_id"], AGENT))
    assert denied["denied"] is True
    assert denied["reason"] == "mandate_status_revoked"
    assert "attestation" not in denied
    count = "SELECT COUNT(*) FROM issued_attestations"
    assert _sql(temp_db, count) == [(1,)]


async def test_no_attestation_under_a_revoked_parent() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    granted = json.loads(await issue_mandate_attestation(child["mandate_id"], HELPER))
    assert "attestation" in granted, granted
    await _revoke(root["mandate_id"])
    denied = json.loads(await issue_mandate_attestation(child["mandate_id"], HELPER))
    assert denied["denied"] is True
    assert denied["reason"] == "parent_mandate_revoked"
    assert denied["refused_by"] == root["mandate_id"]
