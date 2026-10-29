"""Registry check at execution: the receiver re-checks a token when it acts."""

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
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.signing import generate_signing_key, get_key_id, load_signing_key
from amr.db.engine import init_db
from amr.models.perimeter import Perimeter, PerimeterError, RiskClass
from amr.server import mcp
from amr.tools import check_action_token as check_module
from amr.tools.check_action_token import check_action_token
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.issue_action_token import _canonical_action_hash, issue_action_token
from amr.tools.issue_mandate_attestation import issue_mandate_attestation
from amr.tools.revoke_mandate import revoke_mandate
from tests._helpers import insert_mandate_directly

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"
AUDIENCE = "runtime://erp"

CHECKED = {
    "name": "irreversible",
    "actions": ["invoice.pay"],
    "max_token_seconds": 30,
    "registry_check": True,
}
UNCHECKED = {"name": "irreversible", "actions": ["invoice.pay"], "max_token_seconds": 30}

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Handle supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _root(**overrides: object) -> dict:
    params: dict = {**BASE, "allowed_actions": ["invoice.*"], **overrides}
    result = json.loads(await create_mandate(**params))
    assert result.get("status") == "created", result
    return result


async def _child(parent_id: str, **overrides: object) -> dict:
    params: dict = {
        "principal_id": AGENT,
        "agent_id": HELPER,
        "scope": "Pay and read invoices",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 12.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["invoice.read", "invoice.pay"],
    }
    params.update(overrides)
    result = json.loads(await create_mandate(**params))
    assert result.get("status") == "created", result
    return result


async def _token(mandate_id: str, action_type: str, agent_id: str = AGENT, **kw: object) -> dict:
    params: dict = {
        "mandate_id": mandate_id,
        "agent_id": agent_id,
        "action": f"{action_type} {uuid4()}",
        "audience": AUDIENCE,
        "action_type": action_type,
    }
    params.update(kw)
    result = json.loads(await issue_action_token(**params))
    assert "token" in result, result
    return result


def _claims(token: dict | str) -> dict:
    raw = token["token"] if isinstance(token, dict) else token
    return jwt.decode(raw, options={"verify_signature": False})


async def _check(token: dict | str, audience: str = AUDIENCE, **kw: object) -> dict:
    raw = token["token"] if isinstance(token, dict) else token
    return json.loads(await check_action_token(raw, audience, **kw))


def _registry_pem() -> bytes:
    return load_signing_key().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _forge(claims: dict, key_pem: bytes | None = None, kid: str | None = None) -> str:
    """A token signed with the registry key (or another one), with the claims given."""
    return jwt.encode(
        claims,
        key_pem if key_pem is not None else _registry_pem(),
        algorithm="EdDSA",
        headers={"kid": kid if kid is not None else get_key_id(), "typ": "JWT"},
    )


def _fresh_claims(**overrides: object) -> dict:
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": settings.token_issuer,
        "sub": AGENT,
        "aud": AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        "jti": str(uuid4()),
        "amr_mandate_id": str(uuid4()),
        "amr_action_hash": "0" * 64,
        "amr_scope_digest": "0" * 64,
    }
    claims.update(overrides)
    return claims


def _db_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        ]
        return {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]  # noqa: S608
            for table in tables
        }
    finally:
        conn.close()


# --- Model --------------------------------------------------------------------------


def test_class_without_flag_keeps_its_canonical_form() -> None:
    perimeter = Perimeter(
        allowed_actions=("invoice.*",),
        risk_classes=(RiskClass(**UNCHECKED),),
    )
    # Digest and JSON of this perimeter on main before registry_check existed (frozen).
    assert perimeter.digest() == (
        "70c451ec3a51a95c06f39de31224dd2861ad49950771f4a6ad20b9a7feba7acc"
    )
    assert perimeter.to_json() == (
        '{"allowed_actions":["invoice.*"],"amount_actions":[],"currency":"EUR",'
        '"delegation_allowed":false,"forbidden_actions":[],"max_amount":null,'
        '"risk_classes":[{"actions":["invoice.pay"],"max_token_seconds":30,'
        '"name":"irreversible"}]}'
    )


def test_class_with_flag_is_sealed_in_the_canonical_form() -> None:
    flagged = Perimeter(allowed_actions=("invoice.*",), risk_classes=(RiskClass(**CHECKED),))
    plain = Perimeter(allowed_actions=("invoice.*",), risk_classes=(RiskClass(**UNCHECKED),))
    assert flagged.canonical()["risk_classes"][0]["registry_check"] is True
    assert "registry_check" not in plain.canonical()["risk_classes"][0]
    assert flagged.digest() != plain.digest()
    assert Perimeter.from_json(flagged.to_json()) == flagged


def test_explicit_false_flag_is_the_same_class_as_no_flag() -> None:
    explicit = RiskClass(**{**UNCHECKED, "registry_check": False})
    assert explicit.canonical() == RiskClass(**UNCHECKED).canonical()


@pytest.mark.parametrize("value", ["yes", 1, "true", None])
def test_flag_must_be_a_strict_boolean(value: object) -> None:
    with pytest.raises(ValidationError):
        RiskClass(**{**UNCHECKED, "registry_check": value})


def test_requires_registry_check_reaches_sub_types_only_of_flagged_classes() -> None:
    perimeter = Perimeter(
        allowed_actions=("invoice.*",),
        risk_classes=(
            RiskClass(**CHECKED),
            RiskClass(name="reads", actions=("invoice.read",), max_token_seconds=60),
        ),
    )
    assert perimeter.requires_registry_check("invoice.pay")
    assert perimeter.requires_registry_check("invoice.pay.partial")
    assert not perimeter.requires_registry_check("invoice.read")
    assert not perimeter.requires_registry_check("invoice.payroll")


def test_sub_mandate_inherits_the_flag_and_cannot_drop_it() -> None:
    parent = Perimeter(
        allowed_actions=("invoice.*",),
        delegation_allowed=True,
        risk_classes=(RiskClass(**CHECKED),),
    )
    same_name_without_flag = Perimeter(
        allowed_actions=("invoice.pay",),
        risk_classes=(RiskClass(**{**UNCHECKED, "max_token_seconds": 10}),),
    )
    narrowed = same_name_without_flag.narrowed_by(parent)
    (merged,) = narrowed.risk_classes
    assert merged.registry_check is True
    assert merged.max_token_seconds == 10
    inherited = Perimeter(allowed_actions=("invoice.pay",)).narrowed_by(parent)
    assert inherited.risk_classes[0].registry_check is True


def test_sub_mandate_can_add_the_flag_to_a_parent_class() -> None:
    parent = Perimeter(
        allowed_actions=("invoice.*",),
        delegation_allowed=True,
        risk_classes=(RiskClass(**UNCHECKED),),
    )
    child = Perimeter(allowed_actions=("invoice.pay",), risk_classes=(RiskClass(**CHECKED),))
    (merged,) = child.narrowed_by(parent).risk_classes
    assert merged.registry_check is True


def test_sub_mandate_cannot_lengthen_a_flagged_class() -> None:
    parent = Perimeter(
        allowed_actions=("invoice.*",),
        delegation_allowed=True,
        risk_classes=(RiskClass(**CHECKED),),
    )
    child = Perimeter(
        allowed_actions=("invoice.pay",),
        risk_classes=(RiskClass(**{**CHECKED, "max_token_seconds": 60}),),
    )
    with pytest.raises(PerimeterError):
        child.narrowed_by(parent)


# --- Issuer -------------------------------------------------------------------------


async def test_token_carries_the_claim_only_for_flagged_actions() -> None:
    root = await _root(risk_classes=[CHECKED])
    paid = _claims(await _token(root["mandate_id"], "invoice.pay"))
    read = _claims(await _token(root["mandate_id"], "invoice.read"))
    assert paid["amr_registry_check"] is True
    assert "amr_registry_check" not in read


async def test_class_without_flag_issues_the_same_claims_as_before() -> None:
    root = await _root(risk_classes=[UNCHECKED])
    claims = _claims(await _token(root["mandate_id"], "invoice.pay"))
    assert set(claims) == {
        "iss", "sub", "aud", "iat", "nbf", "exp", "jti", "amr_mandate_id",
        "amr_action_hash", "amr_scope_digest", "amr_action_type",
        "amr_perimeter_digest", "amr_risk_classes",
    }


async def test_mandate_without_perimeter_never_flags() -> None:
    result = json.loads(await create_mandate(**BASE))
    claims = _claims(await _token(result["mandate_id"], "invoice.pay"))
    assert "amr_registry_check" not in claims


async def test_flag_in_a_parent_perimeter_reaches_tokens_of_the_branch(
    temp_db: Path,
) -> None:
    root = await _root(risk_classes=[CHECKED], delegation_allowed=True)
    # A sub-mandate whose stored perimeter lacks the class (written directly): the
    # issuer still reads every perimeter of the chain.
    child_id = str(uuid4())
    await insert_mandate_directly(
        temp_db,
        child_id,
        principal_id=AGENT,
        agent_id=HELPER,
        hours_until_expiry=2.0,
        perimeter_json=Perimeter(allowed_actions=("invoice.pay",)).to_json(),
        parent_mandate_id=root["mandate_id"],
    )
    claims = _claims(await _token(child_id, "invoice.pay", agent_id=HELPER))
    assert claims["amr_registry_check"] is True
    assert claims["exp"] - claims["iat"] <= 30


async def test_created_sub_mandate_shows_the_inherited_flag() -> None:
    root = await _root(risk_classes=[CHECKED], delegation_allowed=True)
    child = await _child(root["mandate_id"])
    conn = sqlite3.connect(settings.db_path)
    try:
        stored = conn.execute(
            "SELECT perimeter_json FROM mandates WHERE id = ?", (child["mandate_id"],)
        ).fetchone()[0]
    finally:
        conn.close()
    assert json.loads(stored)["risk_classes"][0]["registry_check"] is True


# --- check_action_token: accepted ---------------------------------------------------


async def test_valid_token_is_accepted() -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    result = await _check(token)
    assert result["valid"] is True, result
    assert result["reason"] == "ok"
    assert result["jti"] == token["jti"]
    assert result["mandate_id"] == root["mandate_id"]
    assert result["agent_id"] == AGENT
    assert result["action_type"] == "invoice.pay"
    assert result["registry_check_required"] is True
    assert datetime.fromisoformat(result["expires_at"]) == datetime.fromtimestamp(
        _claims(token)["exp"], UTC
    )
    assert datetime.fromisoformat(result["checked_at"]).tzinfo is not None


async def test_unflagged_token_can_be_checked_too() -> None:
    result_mandate = json.loads(await create_mandate(**BASE))
    token = await _token(result_mandate["mandate_id"], "invoice.pay")
    result = await _check(token)
    assert result["valid"] is True, result
    assert result["registry_check_required"] is False


def _db_files(db_path: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in db_path.parent.glob(db_path.name + "*")
    }


async def test_check_writes_nothing(temp_db: Path) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    before = _db_counts(temp_db)
    files_before = _db_files(temp_db)
    assert (await _check(token))["valid"] is True
    assert (await _check(token, audience="runtime://other"))["valid"] is False
    revoked_token = _forge(_fresh_claims())
    assert (await _check(revoked_token))["valid"] is False
    assert _db_counts(temp_db) == before
    assert _db_files(temp_db) == files_before


async def test_missing_database_is_never_created(temp_db: Path) -> None:
    assert not temp_db.exists()
    result = await _check(_forge(_fresh_claims()))
    assert result["reason"] == "registry_unavailable"
    assert not temp_db.exists()


async def test_database_is_opened_read_only(temp_db: Path) -> None:
    await init_db(temp_db)
    db = await check_module._open_read_only()
    assert db is not None
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            await db.execute("CREATE TABLE intruder (a TEXT)")
    finally:
        await db.close()


async def test_internal_error_has_a_fixed_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")

    async def broken(*_args: object) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(check_module, "get_issued_token", broken)
    result = await _check(token)
    assert result["valid"] is False
    assert result["reason"] == "internal_error"
    assert result["detail"] == "disk on fire"


async def test_same_token_can_be_checked_twice() -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    assert (await _check(token))["valid"] is True
    assert (await _check(token))["valid"] is True


# --- check_action_token: the mandate moved after issuance ---------------------------


async def test_revocation_after_issuance_is_seen() -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    revoked = json.loads(await revoke_mandate(root["mandate_id"], "agent overspent"))
    assert revoked["status"] == "revoked", revoked
    result = await _check(token)
    assert result["valid"] is False
    assert result["reason"] == "mandate_status_revoked"
    assert result["mandate_id"] == root["mandate_id"]


async def test_parent_revocation_after_issuance_is_seen() -> None:
    root = await _root(risk_classes=[CHECKED], delegation_allowed=True)
    child = await _child(root["mandate_id"])
    token = await _token(child["mandate_id"], "invoice.pay", agent_id=HELPER)
    assert (await _check(token))["valid"] is True
    await revoke_mandate(root["mandate_id"], "principal withdrew")
    result = await _check(token)
    assert result["valid"] is False
    # The child carries no revocation row of its own: the cut comes from the parent.
    assert result["reason"] == "parent_mandate_revoked"
    assert result["refused_by"] == root["mandate_id"]


async def test_status_change_is_seen(temp_db: Path) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE mandates SET status = 'suspended' WHERE id = ?", (root["mandate_id"],))
    conn.commit()
    conn.close()
    result = await _check(token)
    assert result["valid"] is False
    assert result["reason"] == "mandate_status_suspended"


async def test_parent_status_change_is_seen(temp_db: Path) -> None:
    root = await _root(risk_classes=[CHECKED], delegation_allowed=True)
    child = await _child(root["mandate_id"])
    token = await _token(child["mandate_id"], "invoice.pay", agent_id=HELPER)
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE mandates SET status = 'suspended' WHERE id = ?", (root["mandate_id"],))
    conn.commit()
    conn.close()
    result = await _check(token)
    assert result["reason"] == "parent_mandate_suspended"
    assert result["refused_by"] == root["mandate_id"]


async def test_expired_mandate_is_seen(temp_db: Path) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    past = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE mandates SET expires_at = ? WHERE id = ?", (past, root["mandate_id"]))
    conn.commit()
    conn.close()
    assert (await _check(token))["reason"] == "mandate_expired"


async def test_expired_parent_is_seen(temp_db: Path) -> None:
    root = await _root(risk_classes=[CHECKED], delegation_allowed=True)
    child = await _child(root["mandate_id"])
    token = await _token(child["mandate_id"], "invoice.pay", agent_id=HELPER)
    past = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE mandates SET expires_at = ? WHERE id = ?", (past, root["mandate_id"]))
    conn.commit()
    conn.close()
    result = await _check(token)
    assert result["reason"] == "parent_mandate_expired"
    assert result["refused_by"] == root["mandate_id"]


async def test_agent_change_is_seen(temp_db: Path) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    conn = sqlite3.connect(temp_db)
    conn.execute("UPDATE mandates SET agent_id = 'agent:other' WHERE id = ?", (root["mandate_id"],))
    conn.commit()
    conn.close()
    assert (await _check(token))["reason"] == "agent_mismatch"


async def test_missing_mandate_is_seen(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id=AGENT)
    token = await _token(mandate_id, "invoice.pay")
    conn = sqlite3.connect(temp_db)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM mandates WHERE id = ?", (mandate_id,))
    conn.commit()
    conn.close()
    assert (await _check(token))["reason"] == "mandate_not_found"


# --- check_action_token: the token itself -------------------------------------------


async def test_wrong_audience_is_refused() -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    result = await _check(token, audience="runtime://other")
    assert result["valid"] is False
    assert result["reason"] == "wrong_audience"


async def test_tampered_signature_is_refused() -> None:
    root = await _root(risk_classes=[CHECKED])
    raw = (await _token(root["mandate_id"], "invoice.pay"))["token"]
    head, body, sig = raw.split(".")
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert (await _check(f"{head}.{body}.{flipped}"))["reason"] == "bad_signature"


async def test_tampered_claims_are_refused() -> None:
    root = await _root(risk_classes=[CHECKED])
    raw = (await _token(root["mandate_id"], "invoice.pay"))["token"]
    head, _body, sig = raw.split(".")
    claims = _claims(raw)
    claims["exp"] += 3600
    body = jwt.utils.base64url_encode(json.dumps(claims).encode()).decode()
    assert (await _check(f"{head}.{body}.{sig}"))["reason"] == "bad_signature"


async def test_token_of_another_registry_is_refused(tmp_path: Path) -> None:
    other = ed25519.Ed25519PrivateKey.generate()
    other_pem = other.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    raw_pub = other.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    other_kid = hashlib.sha256(raw_pub).hexdigest()[:16]
    assert (await _check(_forge(_fresh_claims(), other_pem, other_kid)))["reason"] == (
        "key_mismatch"
    )
    # Same claims, another key, but this registry's kid in the header.
    assert (await _check(_forge(_fresh_claims(), other_pem)))["reason"] == "bad_signature"


async def test_registry_without_key_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token = _forge(_fresh_claims())
    monkeypatch.setattr("amr.config.settings.public_key_path", tmp_path / "absent.pub")
    assert (await _check(token))["reason"] == "key_mismatch"


async def test_other_algorithms_are_refused() -> None:
    unsigned = jwt.encode(_fresh_claims(), key=None, algorithm="none")
    assert (await _check(unsigned))["reason"] == "wrong_algorithm"
    hmac = jwt.encode(_fresh_claims(), "a" * 32, algorithm="HS256", headers={"kid": get_key_id()})
    assert (await _check(hmac))["reason"] == "wrong_algorithm"


async def test_malformed_token_is_refused() -> None:
    assert (await _check("not-a-token"))["reason"] == "malformed"


async def test_expired_token_is_refused() -> None:
    now = int(datetime.now(UTC).timestamp())
    token = _forge(_fresh_claims(iat=now - 120, nbf=now - 120, exp=now - 60))
    assert (await _check(token))["reason"] == "token_expired"


async def test_token_not_yet_valid_is_refused() -> None:
    now = int(datetime.now(UTC).timestamp())
    token = _forge(_fresh_claims(nbf=now + 120, exp=now + 300))
    assert (await _check(token))["reason"] == "token_not_yet_valid"


async def test_wrong_issuer_is_refused() -> None:
    token = _forge(_fresh_claims(iss="amr://someone-else"))
    assert (await _check(token))["reason"] == "wrong_issuer"


@pytest.mark.parametrize("claim", ["jti", "amr_mandate_id", "amr_action_hash", "sub", "iat"])
async def test_missing_claim_is_refused(claim: str) -> None:
    claims = _fresh_claims()
    del claims[claim]
    assert (await _check(_forge(claims)))["reason"] == "missing_claim"


async def test_token_the_registry_never_issued_is_refused(temp_db: Path) -> None:
    await init_db(temp_db)
    # Signed with the registry key, but no issued_tokens row: e.g. a leaked key.
    result = await _check(_forge(_fresh_claims()))
    assert result["valid"] is False
    assert result["reason"] == "unknown_token"


@pytest.mark.parametrize(
    "field,value",
    [
        ("amr_mandate_id", str(uuid4())),
        ("amr_action_hash", "1" * 64),
        ("aud", "runtime://other"),
        ("sub", "agent:other"),
    ],
)
async def test_token_that_differs_from_its_record_is_refused(field: str, value: str) -> None:
    root = await _root(risk_classes=[CHECKED])
    real = _claims(await _token(root["mandate_id"], "invoice.pay"))
    forged = {**real, field: value}
    audience = value if field == "aud" else AUDIENCE
    assert (await _check(_forge(forged), audience=audience))["reason"] == (
        "token_record_mismatch"
    )


async def test_attestation_is_not_an_action_token() -> None:
    root = await _root(risk_classes=[CHECKED])
    attestation = json.loads(
        await issue_mandate_attestation(root["mandate_id"], AGENT, audience=AUDIENCE)
    )
    result = await _check(attestation["attestation"])
    assert result["valid"] is False
    # It has no amr_action_hash: refused before any database read.
    assert result["reason"] == "missing_claim"


# --- check_action_token: what the receiver adds -------------------------------------


async def test_expected_action_hash_must_match() -> None:
    root = await _root(risk_classes=[CHECKED])
    action = f"pay invoice {uuid4()}"
    token = await _token(root["mandate_id"], "invoice.pay", action=action)
    good = _canonical_action_hash(action, AUDIENCE, {}, "invoice.pay")
    other = _canonical_action_hash("pay another invoice", AUDIENCE, {}, "invoice.pay")
    assert (await _check(token, expected_action_hash=good))["valid"] is True
    result = await _check(token, expected_action_hash=other)
    assert result["valid"] is False
    assert result["reason"] == "action_mismatch"


class _Later(datetime):
    """datetime whose now() is 20 seconds ahead (the receiver checks later)."""

    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return datetime.now(tz) + timedelta(seconds=20)  # type: ignore[arg-type]


async def test_receiver_can_only_tighten_the_age(monkeypatch: pytest.MonkeyPatch) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    monkeypatch.setattr(check_module, "datetime", _Later)
    assert (await _check(token, max_token_age_seconds=10))["reason"] == "token_too_old"
    assert (await _check(token, max_token_age_seconds=25))["valid"] is True
    assert (await _check(token, max_token_age_seconds=86400))["valid"] is True


async def test_large_age_never_extends_exp() -> None:
    now = int(datetime.now(UTC).timestamp())
    token = _forge(_fresh_claims(iat=now - 120, nbf=now - 120, exp=now - 60))
    assert (await _check(token, max_token_age_seconds=86400))["reason"] == "token_expired"


@pytest.mark.parametrize(
    "kw",
    [
        {"max_token_age_seconds": 0},
        {"max_token_age_seconds": 86401},
        {"max_token_age_seconds": True},
        {"max_token_age_seconds": "10"},
        {"expected_action_hash": "A" * 64},
        {"expected_action_hash": "0" * 63},
    ],
)
async def test_invalid_input_is_refused(kw: dict) -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    assert (await _check(token, **kw))["reason"] == "invalid_input"


async def test_empty_audience_is_invalid_input() -> None:
    root = await _root(risk_classes=[CHECKED])
    token = await _token(root["mandate_id"], "invoice.pay")
    assert (await _check(token, audience=""))["reason"] == "invalid_input"


async def test_insurer_dossier_shows_the_flag() -> None:
    flagged = await _root(risk_classes=[CHECKED])
    plain = await _root(risk_classes=[UNCHECKED])
    page = json.loads(await export_insurer_dossier(flagged["mandate_id"], format="html"))["html"]
    assert "registry re-checked at execution" in page
    page = json.loads(await export_insurer_dossier(plain["mandate_id"], format="html"))["html"]
    assert "registry re-checked at execution" not in page


async def test_tool_is_registered() -> None:
    names = {tool.name for tool in await mcp.list_tools()}
    assert "check_action_token" in names
