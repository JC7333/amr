"""Tests for suspend_mandate and resume_mandate: a reversible pause by a designated key.

Answers a question asked by a consultant in agent security (23 and 25/11/2026): cutting
must be easier than granting. The principal designates, in the mandate itself, the keys
that may suspend it at once; only the principal lifts the suspension; revocation stays
final.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr import public_registry as pr
from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.models.perimeter import Perimeter
from amr.tools.check_action_token import check_action_token
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.issue_mandate_attestation import issue_mandate_attestation
from amr.tools.log_action import log_action
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.revoke_mandate import revoke_mandate
from amr.tools.suspend_mandate import (
    prepare_suspension_signature,
    resume_mandate,
    suspend_mandate,
    suspension_record_hash,
)
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"
AUDIENCE = "runtime://erp"


def _new_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


OFFICER = _new_key()
ONCALL = _new_key()

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
    params: dict = {**ROOT, "suspension_keys": [_pub(OFFICER), _pub(ONCALL)]}
    params.update(overrides)
    result = json.loads(await create_mandate(**params))
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


async def _token(mandate_id: str, agent_id: str = AGENT) -> dict:
    return json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=agent_id,
            action=f"read invoice {uuid4()}",
            audience=AUDIENCE,
            action_type="invoice.read",
        )
    )


async def _payload(mandate_id: str, action: str, reason: str, public_key: str = "",
                   signed_at: str | None = None) -> dict:
    result = json.loads(
        await prepare_suspension_signature(mandate_id, action, reason, public_key, signed_at)
    )
    assert "payload" in result, result
    return result


async def _suspend(mandate_id: str, key: ed25519.Ed25519PrivateKey = OFFICER,
                   reason: str = "unusual orders, under review",
                   signed_at: str | None = None) -> dict:
    prepared = await _payload(mandate_id, "suspend", reason, _pub(key), signed_at)
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return json.loads(
        await suspend_mandate(mandate_id, reason, _pub(key), signature, prepared["signed_at"])
    )


async def _resume_signed(mandate_id: str, key: ed25519.Ed25519PrivateKey,
                         reason: str = "review done") -> dict:
    prepared = await _payload(mandate_id, "resume", reason)
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return json.loads(
        await resume_mandate(mandate_id, reason, signature, prepared["signed_at"])
    )


async def _register(key: ed25519.Ed25519PrivateKey, principal_id: str = PRINCIPAL) -> None:
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, _pub(key))))
    result = json.loads(await register_principal_key(principal_id, _pub(key), proof))
    assert result["status"] == "registered", result


async def _proof(mandate_id: str) -> dict:
    return json.loads(await get_proof(mandate_id))


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
    return rows


# --- the mandate designates its suspension keys ------------------------------------


async def test_a_mandate_without_suspension_keys_keeps_its_exact_perimeter() -> None:
    plain = json.loads(await create_mandate(**ROOT))
    assert "suspension_keys" not in plain["perimeter"]
    legacy = Perimeter(allowed_actions=("invoice.*",), delegation_allowed=True)
    assert Perimeter.model_validate(plain["perimeter"]).digest() == legacy.digest()
    assert "suspension_keys" not in legacy.canonical()


async def test_the_keys_are_part_of_the_perimeter_sorted_and_unique() -> None:
    created = await _create(suspension_keys=[_pub(ONCALL), _pub(OFFICER), _pub(ONCALL)])
    assert created["perimeter"]["suspension_keys"] == sorted([_pub(OFFICER), _pub(ONCALL)])


async def test_keys_change_the_perimeter_digest() -> None:
    with_keys = Perimeter(allowed_actions=("invoice.*",), suspension_keys=(_pub(OFFICER),))
    without = Perimeter(allowed_actions=("invoice.*",))
    assert with_keys.digest() != without.digest()


async def test_an_invalid_key_is_refused() -> None:
    result = json.loads(await create_mandate(**ROOT, suspension_keys=["not-a-key"]))
    assert result["code"] == "perimeter_invalid"


async def test_at_most_five_keys() -> None:
    keys = [_pub(_new_key()) for _ in range(6)]
    result = json.loads(await create_mandate(**ROOT, suspension_keys=keys))
    assert result["code"] == "perimeter_invalid"
    assert (await _create(suspension_keys=keys[:5]))["perimeter"]["suspension_keys"]


async def test_keys_need_a_structured_perimeter() -> None:
    params = {k: v for k, v in ROOT.items() if k not in ("allowed_actions", "delegation_allowed")}
    result = json.loads(await create_mandate(**params, suspension_keys=[_pub(OFFICER)]))
    assert result["code"] == "perimeter_invalid"


async def test_the_principal_signature_covers_the_keys() -> None:
    principal_key = _new_key()
    await _register(principal_key)
    params = {**ROOT, "suspension_keys": [_pub(OFFICER)]}
    prepared = json.loads(await prepare_mandate_signature(**params))
    assert _pub(OFFICER) in prepared["payload"]
    signature = b64url_encode(principal_key.sign(prepared["payload"].encode("utf-8")))
    other = {**params, "suspension_keys": [_pub(ONCALL)]}
    refused = json.loads(
        await create_mandate(**other, principal_signature=signature,
                             signed_at=prepared["signed_at"])
    )
    assert refused["code"] == "principal_signature_invalid"
    created = json.loads(
        await create_mandate(**params, principal_signature=signature,
                             signed_at=prepared["signed_at"])
    )
    assert created["status"] == "created", created


async def test_a_sub_mandate_keeps_its_own_keys_only() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"], suspension_keys=[_pub(ONCALL)])
    assert child["perimeter"]["suspension_keys"] == [_pub(ONCALL)]
    plain_child = await _sub(root["mandate_id"])
    assert "suspension_keys" not in plain_child["perimeter"]


# --- suspending ------------------------------------------------------------------


async def test_a_designated_key_suspends_and_everything_stops() -> None:
    root = await _create()
    mid = root["mandate_id"]
    before = await _token(mid)
    assert "token" in before, before

    suspended = await _suspend(mid)
    assert suspended["status"] == "suspended", suspended
    assert suspended["key_id"]

    assert (await _token(mid))["reason"] == "mandate_status_suspended"
    attestation = json.loads(await issue_mandate_attestation(mid, AGENT))
    assert attestation["reason"] == "mandate_status_suspended"
    logged = json.loads(await log_action(mid, AGENT, "invoice.read", "{}"))
    assert logged["code"] == "mandate_status_suspended"
    named = json.loads(await verify_mandate(AGENT, "read", mandate_id=mid))
    assert named["authorized"] is False and named["reason"] == "Mandate suspended"
    anyone = json.loads(await verify_mandate(AGENT, "read"))
    assert anyone["authorized"] is False
    checked = json.loads(await check_action_token(before["token"], AUDIENCE))
    assert checked["valid"] is False and checked["reason"] == "mandate_status_suspended"


async def test_the_other_designated_key_suspends_too() -> None:
    root = await _create()
    assert (await _suspend(root["mandate_id"], ONCALL))["status"] == "suspended"


async def test_verify_without_mandate_id_falls_back_to_another_mandate() -> None:
    older = await _create()
    newer = await _create()
    await _suspend(newer["mandate_id"])
    answer = json.loads(await verify_mandate(AGENT, "read"))
    assert answer["authorized"] is True
    assert answer["mandate_id"] == older["mandate_id"]


async def test_the_whole_branch_below_is_cut() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    child_token = await _token(child["mandate_id"], HELPER)
    assert "token" in child_token, child_token
    await _suspend(root["mandate_id"])

    refused = await _token(child["mandate_id"], HELPER)
    assert refused["reason"] == "parent_mandate_suspended"
    checked = json.loads(await check_action_token(child_token["token"], AUDIENCE))
    assert checked["reason"] == "parent_mandate_suspended"
    new_child = await _sub(root["mandate_id"])
    assert new_child["code"] == "parent_mandate_suspended"
    named = json.loads(await verify_mandate(HELPER, "read", mandate_id=child["mandate_id"]))
    assert named["authorized"] is False and "parent_mandate_suspended" in named["reason"]


async def test_a_key_the_mandate_does_not_designate_cannot_suspend() -> None:
    root = await _create(suspension_keys=[_pub(OFFICER)])
    result = await _suspend(root["mandate_id"], ONCALL)
    assert result["code"] == "suspension_key_not_designated"
    assert "token" in await _token(root["mandate_id"])


async def test_a_mandate_without_keys_cannot_be_suspended() -> None:
    plain = json.loads(await create_mandate(**ROOT))
    result = await _suspend(plain["mandate_id"])
    assert result["code"] == "suspension_not_designated"


async def test_a_bad_signature_is_refused() -> None:
    root = await _create()
    mid = root["mandate_id"]
    prepared = await _payload(mid, "suspend", "first reason", _pub(OFFICER))
    signature = b64url_encode(OFFICER.sign(prepared["payload"].encode("utf-8")))
    other_reason = json.loads(
        await suspend_mandate(mid, "other reason", _pub(OFFICER), signature,
                              prepared["signed_at"])
    )
    assert other_reason["code"] == "suspension_signature_invalid"
    forged = b64url_encode(ONCALL.sign(prepared["payload"].encode("utf-8")))
    wrong_key = json.loads(
        await suspend_mandate(mid, "first reason", _pub(OFFICER), forged,
                              prepared["signed_at"])
    )
    assert wrong_key["code"] == "suspension_signature_invalid"
    assert "token" in await _token(mid)


async def test_a_resume_signature_cannot_suspend() -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _register(OFFICER)
    prepared = await _payload(mid, "resume", "why")
    signature = b64url_encode(OFFICER.sign(prepared["payload"].encode("utf-8")))
    result = json.loads(
        await suspend_mandate(mid, "why", _pub(OFFICER), signature, prepared["signed_at"])
    )
    assert result["code"] == "suspension_signature_invalid"


async def test_a_stale_signature_is_refused() -> None:
    root = await _create()
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    result = await _suspend(root["mandate_id"], signed_at=old)
    assert result["code"] == "principal_signature_stale"


async def test_suspending_twice_is_refused() -> None:
    root = await _create()
    await _suspend(root["mandate_id"])
    again = await _suspend(root["mandate_id"], ONCALL)
    assert again["code"] == "mandate_already_suspended"


async def test_a_signature_cannot_be_replayed() -> None:
    root = await _create()
    mid = root["mandate_id"]
    reason = "under review"
    prepared = await _payload(mid, "suspend", reason, _pub(OFFICER))
    signature = b64url_encode(OFFICER.sign(prepared["payload"].encode("utf-8")))
    first = json.loads(
        await suspend_mandate(mid, reason, _pub(OFFICER), signature, prepared["signed_at"])
    )
    assert first["status"] == "suspended"
    assert (json.loads(await resume_mandate(mid, "done")))["status"] == "resumed"
    replay = json.loads(
        await suspend_mandate(mid, reason, _pub(OFFICER), signature, prepared["signed_at"])
    )
    assert replay["code"] == "suspension_signature_replayed"


async def test_a_revoked_mandate_cannot_be_suspended_or_resumed() -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    assert json.loads(await revoke_mandate(mid, "ended"))["status"] == "revoked"
    assert json.loads(await resume_mandate(mid, "back"))["code"] == "mandate_already_revoked"
    other = await _create()
    assert json.loads(await revoke_mandate(other["mandate_id"], "ended"))["status"] == "revoked"
    assert (await _suspend(other["mandate_id"]))["code"] == "mandate_already_revoked"
    proof = await _proof(mid)
    assert proof["mandate"]["status"] == "revoked"


async def test_unknown_mandate() -> None:
    result = await suspend_mandate(str(uuid4()), "x", _pub(OFFICER), "A" * 86,
                                   datetime.now(UTC).isoformat())
    assert json.loads(result)["code"] == "mandate_not_found"
    assert json.loads(await resume_mandate(str(uuid4()), "x"))["code"] == "mandate_not_found"
    bad = json.loads(await resume_mandate("not-a-uuid", "x"))
    assert bad["code"] == "invalid_input"


# --- resuming ----------------------------------------------------------------------


async def test_the_principal_resumes_and_the_mandate_works_again() -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    resumed = json.loads(await resume_mandate(mid, "review done"))
    assert resumed["status"] == "resumed", resumed
    assert resumed["principal_signature"] is None
    assert "token" in await _token(mid)
    assert json.loads(await verify_mandate(AGENT, "read", mandate_id=mid))["authorized"]


async def test_resume_needs_a_suspension() -> None:
    root = await _create()
    result = json.loads(await resume_mandate(root["mandate_id"], "nothing to lift"))
    assert result["code"] == "mandate_not_suspended"


async def test_a_principal_with_a_key_must_sign_the_resumption() -> None:
    principal_key = _new_key()
    await _register(principal_key)
    params = {**ROOT, "suspension_keys": [_pub(OFFICER)]}
    prepared = json.loads(await prepare_mandate_signature(**params))
    signature = b64url_encode(principal_key.sign(prepared["payload"].encode("utf-8")))
    root = json.loads(
        await create_mandate(**params, principal_signature=signature,
                             signed_at=prepared["signed_at"])
    )
    mid = root["mandate_id"]
    await _suspend(mid)

    unsigned = json.loads(await resume_mandate(mid, "back"))
    assert unsigned["code"] == "principal_signature_required"
    by_holder = await _resume_signed(mid, OFFICER)
    assert by_holder["code"] == "principal_signature_invalid"
    assert (await _token(mid))["reason"] == "mandate_status_suspended"

    resumed = await _resume_signed(mid, principal_key)
    assert resumed["status"] == "resumed", resumed
    assert resumed["principal_signature"]["key_id"]
    proof = await _proof(mid)
    assert proof["mandate"]["status"] == "active"
    assert proof["chain_integrity"]["suspensions_valid"] is True


async def test_require_principal_signature_applies_to_resumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = await _create()
    await _suspend(root["mandate_id"])
    monkeypatch.setattr("amr.config.settings.require_principal_signature", True)
    result = json.loads(await resume_mandate(root["mandate_id"], "back"))
    assert result["code"] == "principal_signature_required"


async def test_half_a_signature_is_refused() -> None:
    root = await _create()
    await _suspend(root["mandate_id"])
    result = json.loads(await resume_mandate(root["mandate_id"], "back", "A" * 86, None))
    assert result["code"] == "principal_signature_incomplete"


async def test_suspend_resume_suspend_again() -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    await resume_mandate(mid, "done")
    assert (await _suspend(mid, ONCALL, reason="second look"))["status"] == "suspended"
    proof = await _proof(mid)
    assert [s["action"] for s in proof["suspensions"]] == ["suspend", "resume", "suspend"]
    assert proof["mandate"]["suspension"]["reason"] == "second look"
    assert proof["chain_integrity"]["suspensions_valid"] is True


# --- what the proof, the dossier and the public registry show ------------------------


async def test_the_proof_shows_the_suspension(temp_db: Path) -> None:
    root = await _create()
    mid = root["mandate_id"]
    never = await _proof(mid)
    assert never["mandate"]["suspension"] is None
    assert never["suspensions"] == []
    assert never["chain_integrity"]["suspensions_valid"] is None

    await _suspend(mid)
    proof = await _proof(mid)
    assert proof["mandate"]["status"] == "suspended"
    assert proof["mandate"]["stored_status"] == "active"
    assert proof["mandate"]["suspension"]["reason"] == "unusual orders, under review"
    (entry,) = proof["suspensions"]
    assert entry["signature"]["public_key"] == _pub(OFFICER)
    assert proof["chain_integrity"]["suspensions_valid"] is True
    assert [e["event_type"] for e in proof["events"]].count("suspended") == 1
    versions = {row[0] for row in _sql(temp_db, "SELECT version FROM schema_version")}
    assert 15 in versions


async def test_a_deleted_suspension_record_shows_in_the_proof(temp_db: Path) -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    _sql(temp_db, "DELETE FROM mandate_suspensions WHERE mandate_id = ?", (mid,))
    proof = await _proof(mid)
    assert proof["chain_integrity"]["suspensions_valid"] is False


async def test_an_altered_suspension_record_shows_in_the_proof(temp_db: Path) -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    _sql(temp_db, "UPDATE mandate_suspensions SET reason = ? WHERE mandate_id = ?",
         ("nothing happened", mid))
    assert (await _proof(mid))["chain_integrity"]["suspensions_valid"] is False


async def test_a_forged_suspension_by_an_undesignated_key_shows_in_the_proof(
    temp_db: Path,
) -> None:
    root = await _create(suspension_keys=[_pub(OFFICER)])
    mid = root["mandate_id"]
    await _suspend(mid)
    _sql(temp_db, "UPDATE mandate_suspensions SET public_key = ? WHERE mandate_id = ?",
         (_pub(ONCALL), mid))
    assert (await _proof(mid))["chain_integrity"]["suspensions_valid"] is False


async def test_an_altered_record_time_breaks_the_recomputed_chain(temp_db: Path) -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    _sql(temp_db, "UPDATE mandate_suspensions SET recorded_at = ? WHERE mandate_id = ?",
         ("2020-01-01T00:00:00+00:00", mid))
    assert (await _proof(mid))["chain_integrity"]["suspensions_valid"] is False


async def test_a_record_rewritten_with_an_undesignated_key_is_invalid(temp_db: Path) -> None:
    root = await _create(suspension_keys=[_pub(OFFICER)])
    mid = root["mandate_id"]
    reason = "unusual orders, under review"
    await _suspend(mid, reason=reason)
    # Rewrite the whole record as if ONCALL (not designated) had signed it, hash included.
    prepared = await _payload(mid, "suspend", reason, _pub(ONCALL))
    signature = b64url_encode(ONCALL.sign(prepared["payload"].encode("utf-8")))
    (row,) = _sql(temp_db, "SELECT mandate_id, action, reason, recorded_at "
                  "FROM mandate_suspensions WHERE mandate_id = ?", (mid,))
    record = {"mandate_id": row[0], "action": row[1], "reason": row[2],
              "recorded_at": row[3], "signature": signature,
              "signed_at": prepared["signed_at"], "key_id": prepared["key_id"]}
    chain_hash = suspension_record_hash(record, root["chain_hash"], "")
    _sql(temp_db, "UPDATE mandate_suspensions SET public_key = ?, key_id = ?, signature = ?, "
         "signed_at = ?, signed_payload = ?, chain_hash = ? WHERE mandate_id = ?",
         (_pub(ONCALL), prepared["key_id"], signature, prepared["signed_at"],
          prepared["payload"], chain_hash, mid))
    assert (await _proof(mid))["chain_integrity"]["suspensions_valid"] is False


async def test_a_deleted_resumption_shows_in_the_proof(temp_db: Path) -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    await resume_mandate(mid, "done")
    _sql(temp_db, "DELETE FROM mandate_suspensions WHERE action = 'resume'")
    proof = await _proof(mid)
    assert proof["mandate"]["status"] == "suspended"
    assert proof["chain_integrity"]["suspensions_valid"] is False


async def test_an_unsigned_resumption_after_the_principal_had_a_key_is_invalid(
    temp_db: Path,
) -> None:
    root = await _create()
    mid = root["mandate_id"]
    await _suspend(mid)
    await resume_mandate(mid, "done")
    principal_key = _new_key()
    await _register(principal_key)
    # Pretend the key existed before the resumption: an unsigned one is then a forgery.
    _sql(temp_db, "UPDATE principal_keys SET registered_at = ? WHERE principal_id = ?",
         ((datetime.now(UTC) - timedelta(days=1)).isoformat(), PRINCIPAL))
    assert (await _proof(mid))["chain_integrity"]["suspensions_valid"] is False


async def test_the_insurer_dossier_shows_it_not_in_force() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    await _suspend(root["mandate_id"])
    dossier = json.loads(await export_insurer_dossier(root["mandate_id"]))["dossier"]
    assert dossier["status"]["in_force"] is False
    assert dossier["status"]["not_in_force_reason"] == "mandate_suspended"
    (sub,) = dossier["sub_mandates"]
    assert sub["id"] == child["mandate_id"]
    assert sub["status"]["in_force"] is False


async def test_the_public_registry_export_shows_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    await _suspend(root["mandate_id"])
    snapshot = jwt.decode(await pr.build_export(), options={"verify_signature": False})
    mandates = {m["id"]: m for m in snapshot["amr_public_registry"]["mandates"]}
    assert mandates[root["mandate_id"]]["recorded_status"] == "suspended"
    index = {m["id"]: pr.PublicMandate.model_validate(m) for m in mandates.values()}
    now = datetime.now(UTC).timestamp()
    assert pr.evaluate(index, root["mandate_id"], now)["reason"] == "mandate_suspended"
    assert (
        pr.evaluate(index, child["mandate_id"], now)["reason"] == "parent_mandate_suspended"
    )
    await resume_mandate(root["mandate_id"], "done")
    snapshot = jwt.decode(await pr.build_export(), options={"verify_signature": False})
    mandates = {m["id"]: m for m in snapshot["amr_public_registry"]["mandates"]}
    assert mandates[root["mandate_id"]]["recorded_status"] == "active"


async def test_prepare_writes_nothing_and_names_the_signer() -> None:
    root = await _create()
    prepared = await _payload(root["mandate_id"], "suspend", "why", _pub(OFFICER))
    body = json.loads(prepared["payload"])
    assert body["context"] == "amr.suspension.v1"
    assert body["action"] == "suspend"
    assert body["principal_id"] == PRINCIPAL
    assert prepared["key_id"] == body["key_id"]
    bad_action = json.loads(
        await prepare_suspension_signature(root["mandate_id"], "pause", "why", _pub(OFFICER))
    )
    assert bad_action["code"] == "invalid_input"
    no_key = json.loads(
        await prepare_suspension_signature(root["mandate_id"], "resume", "why")
    )
    assert no_key["code"] == "principal_key_not_registered"
