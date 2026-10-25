"""Tests for mandate attestations: a third party verifies a mandate offline.

The question: can the receiver of an agent (a seller, a hospital, an insurer) check,
alone and without calling the registry, that the agent's mandate exists, who granted
it, what it allows, until when, and that it was not cut?
"""

import base64
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.attestation import ATTESTATION_TYP, registry_key_id, verify_attestation
from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key, load_signing_key
from amr.db.engine import init_db
from amr.models.perimeter import Perimeter
from amr.tools.create_mandate import create_mandate
from amr.tools.issue_action_token import issue_action_token
from amr.tools.issue_mandate_attestation import (
    get_registry_public_key,
    issue_mandate_attestation,
)
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.verify_attestation import main as cli_main
from tests._helpers import insert_mandate_directly

PRINCIPAL = "org:clinic"
AGENT = "agent:assistant"

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Order medical supplies for the practice",
    "legal_basis_regulation": "Code civil",
    "legal_basis_article": "Art. 1984",
    "duration_hours": 24.0,
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolated registry key per test."""
    priv = tmp_path / "registry_key.pem"
    pub = tmp_path / "registry_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _public_key_pem() -> str:
    return json.loads(await get_registry_public_key())["public_key_pem"]


async def _mandate(**overrides: object) -> dict:
    result = json.loads(await create_mandate(**{**BASE, **overrides}))
    assert "mandate_id" in result, result
    return result


async def _attest(mandate_id: str, agent_id: str = AGENT, **kwargs: object) -> dict:
    return json.loads(await issue_mandate_attestation(mandate_id, agent_id, **kwargs))


async def _verify(attestation: str, **kwargs: object) -> dict:
    return verify_attestation(attestation, await _public_key_pem(), **kwargs)


def _claims(attestation: str) -> dict:
    return jwt.decode(attestation, options={"verify_signature": False})


def _resign(claims: dict, typ: str = ATTESTATION_TYP) -> str:
    """Sign arbitrary claims with the registry key (a buggy or compromised issuer)."""
    key = load_signing_key()
    kid = registry_key_id(key.public_key())
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": kid, "typ": typ})


def _sql(db_path: Path, statement: str, params: tuple) -> None:
    """Tamper with the database on purpose, as an attacker with file access would."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(statement, params)
    conn.commit()
    conn.close()


# --- Issuance --------------------------------------------------------------------------


async def test_attestation_is_verified_offline_with_the_public_key_only() -> None:
    m = await _mandate(allowed_actions=["supplies.order"], forbidden_actions=["rx.*"])
    issued = await _attest(m["mandate_id"])
    assert set(issued) == {"attestation", "jti", "issued_at", "expires_at", "key_id", "issuer"}

    result = await _verify(issued["attestation"])
    assert result["valid"] is True, result
    summary = result["attestation"]
    assert summary["mandate_id"] == m["mandate_id"]
    assert summary["principal_id"] == PRINCIPAL
    assert summary["agent_id"] == AGENT
    assert summary["scope"] == BASE["scope"]
    assert summary["legal_basis"]["article"] == "Art. 1984"
    assert summary["perimeter"]["allowed_actions"] == ["supplies.order"]
    assert summary["perimeter"]["forbidden_actions"] == ["rx.*"]
    assert summary["mandate_expires_at"] == m["expires_at"]
    assert summary["delegated"] is False
    assert summary["delegation_chain"] == []
    assert summary["principal_signed"] is False
    assert summary["jti"] == issued["jti"]


async def test_attestation_header_and_claims() -> None:
    m = await _mandate(allowed_actions=["supplies.order"])
    issued = await _attest(m["mandate_id"])
    header = jwt.get_unverified_header(issued["attestation"])
    assert header == {"alg": "EdDSA", "typ": ATTESTATION_TYP, "kid": issued["key_id"]}
    claims = _claims(issued["attestation"])
    assert claims["iss"] == "amr://localhost"
    assert claims["sub"] == AGENT
    assert claims["nbf"] == claims["iat"]
    assert claims["amr_attestation"] == "mandate.v1"
    assert "aud" not in claims
    assert claims["amr_mandate"]["status"] == "active"
    assert claims["amr_mandate"]["chain_hash"] == m["chain_hash"]
    assert claims["amr_mandate"]["perimeter_digest"] == Perimeter.model_validate(
        m["perimeter"]
    ).digest()
    assert "metadata" not in claims["amr_mandate"]


async def test_free_text_mandate_is_attested_without_perimeter() -> None:
    m = await _mandate()
    issued = await _attest(m["mandate_id"])
    claims = _claims(issued["attestation"])
    assert claims["amr_mandate"]["perimeter"] is None
    assert claims["amr_mandate"]["perimeter_digest"] is None
    assert (await _verify(issued["attestation"]))["valid"] is True


async def test_lifetime_defaults_to_the_configured_maximum(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.attestation_lifetime_seconds", 600)
    m = await _mandate()
    claims = _claims((await _attest(m["mandate_id"]))["attestation"])
    assert claims["exp"] - claims["iat"] == 600


async def test_lifetime_can_shorten_but_never_extend(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.attestation_lifetime_seconds", 600)
    m = await _mandate()
    short = _claims((await _attest(m["mandate_id"], lifetime_seconds=60))["attestation"])
    assert short["exp"] - short["iat"] == 60
    long = _claims((await _attest(m["mandate_id"], lifetime_seconds=99999))["attestation"])
    assert long["exp"] - long["iat"] == 600


async def test_attestation_never_outlives_the_mandate(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.attestation_lifetime_seconds", 86400)
    m = await _mandate(duration_hours=0.1)  # six minutes
    issued = await _attest(m["mandate_id"])
    claims = _claims(issued["attestation"])
    assert claims["exp"] <= datetime.fromisoformat(m["expires_at"]).timestamp()
    assert claims["exp"] - claims["iat"] <= 360
    assert (await _verify(issued["attestation"]))["valid"] is True


async def test_attestation_never_outlives_a_parent(temp_db: Path, monkeypatch) -> None:
    """Even a sub-mandate stored with a later expiry than its parent is capped."""
    monkeypatch.setattr("amr.config.settings.attestation_lifetime_seconds", 86400)
    parent_id, child_id = str(uuid4()), str(uuid4())
    await insert_mandate_directly(
        temp_db, parent_id, agent_id="agent:lead", hours_until_expiry=0.1
    )
    await insert_mandate_directly(
        temp_db, child_id, principal_id="agent:lead", agent_id=AGENT,
        parent_mandate_id=parent_id, hours_until_expiry=10,
    )
    issued = await _attest(child_id)
    claims = _claims(issued["attestation"])
    assert claims["exp"] - claims["iat"] <= 360
    assert (await _verify(issued["attestation"]))["valid"] is True


async def test_issuance_is_recorded(temp_db: Path) -> None:
    m = await _mandate()
    issued = await _attest(m["mandate_id"], audience="seller:acme")
    conn = sqlite3.connect(str(temp_db))
    row = conn.execute(
        "SELECT mandate_id, agent_id, audience, expires_at, key_id, claims_digest "
        "FROM issued_attestations WHERE jti = ?",
        (issued["jti"],),
    ).fetchone()
    conn.close()
    assert row[:5] == (m["mandate_id"], AGENT, "seller:acme", issued["expires_at"],
                       issued["key_id"])
    assert len(row[5]) == 64


async def test_each_attestation_has_its_own_jti() -> None:
    m = await _mandate()
    first = await _attest(m["mandate_id"])
    second = await _attest(m["mandate_id"])
    assert first["jti"] != second["jti"]


# --- Refusals ----------------------------------------------------------------------


async def test_unknown_mandate_is_refused() -> None:
    result = await _attest(str(uuid4()))
    assert result["denied"] is True
    assert result["reason"] == "mandate_not_found"


async def test_another_agent_cannot_get_the_attestation() -> None:
    m = await _mandate()
    result = await _attest(m["mandate_id"], agent_id="agent:intruder")
    assert result["reason"] == "agent_mismatch"


@pytest.mark.parametrize("status", ["revoked", "expired"])
async def test_cut_mandate_is_refused(temp_db: Path, status: str) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id=AGENT, status=status)
    result = await _attest(mandate_id)
    assert result["reason"] == f"mandate_status_{status}"


async def test_expired_mandate_is_refused(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id=AGENT, hours_until_expiry=-1)
    assert (await _attest(mandate_id))["reason"] == "mandate_expired"


async def test_mandate_expiring_within_the_second_is_refused(temp_db: Path, monkeypatch) -> None:
    """An attestation that would expire in the second it is issued is not issued."""
    frozen = datetime(2030, 1, 1, 12, 0, 0, 100000, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return frozen

    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id=AGENT)
    _sql(temp_db, "UPDATE mandates SET expires_at = ? WHERE id = ?",
         ((frozen + timedelta(milliseconds=400)).isoformat(), mandate_id))
    monkeypatch.setattr("amr.tools.issue_mandate_attestation.datetime", FrozenDatetime)
    assert (await _attest(mandate_id))["reason"] == "mandate_expired"


async def test_revoked_parent_cuts_the_attestation(temp_db: Path) -> None:
    parent_id, child_id = str(uuid4()), str(uuid4())
    await insert_mandate_directly(temp_db, parent_id, agent_id="agent:lead", status="revoked")
    await insert_mandate_directly(
        temp_db, child_id, agent_id=AGENT, parent_mandate_id=parent_id
    )
    result = await _attest(child_id)
    assert result["reason"] == "parent_mandate_revoked"
    assert result["refused_by"] == parent_id


async def test_expired_parent_cuts_the_attestation(temp_db: Path) -> None:
    parent_id, child_id = str(uuid4()), str(uuid4())
    await insert_mandate_directly(
        temp_db, parent_id, agent_id="agent:lead", hours_until_expiry=-1
    )
    await insert_mandate_directly(
        temp_db, child_id, agent_id=AGENT, parent_mandate_id=parent_id
    )
    assert (await _attest(child_id))["reason"] == "parent_mandate_expired"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mandate_id": "not-a-uuid"},
        {"agent_id": ""},
        {"audience": ""},
        {"lifetime_seconds": 0},
        {"lifetime_seconds": -5},
    ],
)
async def test_invalid_input_is_refused(kwargs: dict) -> None:
    m = await _mandate()
    args = {"mandate_id": m["mandate_id"], "agent_id": AGENT, **kwargs}
    result = json.loads(await issue_mandate_attestation(**args))
    assert result["denied"] is True
    assert result["reason"].startswith("invalid_input")


async def test_refusal_writes_nothing(temp_db: Path) -> None:
    m = await _mandate()
    await _attest(m["mandate_id"], agent_id="agent:intruder")
    conn = sqlite3.connect(str(temp_db))
    count = conn.execute("SELECT COUNT(*) FROM issued_attestations").fetchone()[0]
    conn.close()
    assert count == 0


# --- Delegation chain ---------------------------------------------------------------


async def test_sub_mandate_attestation_carries_the_whole_chain() -> None:
    root = await _mandate(
        agent_id="agent:lead", duration_hours=48,
        allowed_actions=["supplies.*"], delegation_allowed=True,
    )
    middle = await _mandate(
        principal_id="agent:lead", agent_id="agent:buyer",
        parent_mandate_id=root["mandate_id"], duration_hours=36,
        allowed_actions=["supplies.*"], delegation_allowed=True,
    )
    leaf = await _mandate(
        principal_id="agent:buyer", agent_id=AGENT, parent_mandate_id=middle["mandate_id"],
        allowed_actions=["supplies.order"],
    )
    issued = await _attest(leaf["mandate_id"])
    claims = _claims(issued["attestation"])
    assert [link["id"] for link in claims["amr_chain"]] == [
        middle["mandate_id"], root["mandate_id"]
    ]
    assert claims["amr_chain"][1]["principal_id"] == PRINCIPAL
    result = await _verify(issued["attestation"])
    assert result["valid"] is True, result
    assert result["attestation"]["delegated"] is True
    assert [link["mandate_id"] for link in result["attestation"]["delegation_chain"]] == [
        middle["mandate_id"], root["mandate_id"]
    ]
    assert result["attestation"]["delegation_chain"][1]["principal_id"] == PRINCIPAL


# --- Principal signatures -------------------------------------------------------------


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
    assert "key_id" in result, result


async def _signed_mandate(key: ed25519.Ed25519PrivateKey, **overrides: object) -> dict:
    args = {**BASE, **overrides}
    prepared = json.loads(await prepare_mandate_signature(**args))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return await _mandate(
        **overrides, principal_signature=signature, signed_at=prepared["signed_at"]
    )


async def test_signed_mandate_attestation_lets_the_receiver_check_the_principal() -> None:
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key, allowed_actions=["supplies.order"])
    issued = await _attest(m["mandate_id"], include_principal_payload=True)
    block = _claims(issued["attestation"])["amr_mandate"]["principal_signature"]
    assert block["public_key"] == _pub(key)
    # The receiver can re-check the principal's own signature without the registry.
    raw = base64.urlsafe_b64decode(block["signature"] + "=" * (-len(block["signature"]) % 4))
    key.public_key().verify(raw, block["payload"].encode("utf-8"))
    result = await _verify(issued["attestation"])
    assert result["valid"] is True, result
    assert result["attestation"]["principal_signed"] is True
    assert result["attestation"]["principal_key_id"] == block["key_id"]
    assert result["attestation"]["principal_signature_rechecked"] is True


async def test_signed_payload_and_metadata_are_not_disclosed_by_default() -> None:
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key, metadata={"client_ref": "C-0042"})
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    assert "C-0042" not in json.dumps(_claims(attestation))
    block = _claims(attestation)["amr_mandate"]["principal_signature"]
    assert set(block) == {"key_id", "public_key", "signed_at", "algorithm"}
    result = await _verify(attestation)
    assert result["valid"] is True, result
    assert result["attestation"]["principal_signed"] is True
    assert result["attestation"]["principal_signature_rechecked"] is False


async def test_signed_payload_discloses_metadata_only_on_request() -> None:
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key, metadata={"client_ref": "C-0042"})
    attestation = (await _attest(m["mandate_id"], include_principal_payload=True))[
        "attestation"
    ]
    payload = _claims(attestation)["amr_mandate"]["principal_signature"]["payload"]
    assert json.loads(payload)["metadata"] == {"client_ref": "C-0042"}


async def test_tampered_signed_mandate_is_not_attested(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key, allowed_actions=["supplies.order"])
    _sql(temp_db, "UPDATE mandates SET scope = ? WHERE id = ?", ("Anything", m["mandate_id"]))
    result = await _attest(m["mandate_id"])
    assert result["reason"] == "principal_signature_invalid"
    assert "refused_by" not in result


async def test_stripped_signature_is_not_attested(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key)
    _sql(
        temp_db,
        "UPDATE mandates SET principal_signature = NULL, principal_signed_at = NULL, "
        "principal_key_id = NULL, principal_signed_payload = NULL WHERE id = ?",
        (m["mandate_id"],),
    )
    assert (await _attest(m["mandate_id"]))["reason"] == "principal_signature_invalid"


async def test_tampered_parent_signature_cuts_the_sub_mandate(temp_db: Path) -> None:
    key = _new_key()
    await _register(key)
    parent = await _signed_mandate(
        key, agent_id="agent:lead", duration_hours=48,
        allowed_actions=["supplies.*"], delegation_allowed=True,
    )
    child = await _mandate(
        principal_id="agent:lead", agent_id=AGENT, parent_mandate_id=parent["mandate_id"],
        allowed_actions=["supplies.order"],
    )
    _sql(temp_db, "UPDATE mandates SET scope = ? WHERE id = ?",
         ("Anything", parent["mandate_id"]))
    result = await _attest(child["mandate_id"])
    assert result["reason"] == "principal_signature_invalid"
    assert result["refused_by"] == parent["mandate_id"]


async def test_unsigned_mandate_of_principal_without_key_is_attested() -> None:
    m = await _mandate()
    issued = await _attest(m["mandate_id"])
    assert _claims(issued["attestation"])["amr_mandate"]["principal_signature"] is None
    assert (await _verify(issued["attestation"]))["attestation"]["principal_signed"] is False


# --- Receiver side: what the verifier refuses --------------------------------------------


async def test_audience_must_be_named_by_the_receiver() -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"], audience="seller:acme"))["attestation"]
    assert _claims(attestation)["aud"] == "seller:acme"
    assert (await _verify(attestation, audience="seller:acme"))["valid"] is True
    assert (await _verify(attestation))["reason"] == "wrong_audience"
    assert (await _verify(attestation, audience="seller:other"))["reason"] == "wrong_audience"


async def test_receiver_expecting_an_audience_refuses_an_unaddressed_attestation() -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    assert (await _verify(attestation, audience="seller:acme"))["reason"] == "wrong_audience"


async def test_issuer_is_checked_when_given() -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    assert (await _verify(attestation, issuer="amr://localhost"))["valid"] is True
    assert (await _verify(attestation, issuer="amr://other"))["reason"] == "wrong_issuer"


async def test_expired_attestation_is_refused() -> None:
    m = await _mandate()
    issued = await _attest(m["mandate_id"], lifetime_seconds=60)
    exp = _claims(issued["attestation"])["exp"]
    assert (await _verify(issued["attestation"], now=exp - 1))["valid"] is True
    assert (await _verify(issued["attestation"], now=exp))["reason"] == "expired"
    assert (await _verify(issued["attestation"], now=exp + 5, leeway=10))["valid"] is True


async def test_attestation_is_not_valid_before_issuance() -> None:
    m = await _mandate()
    issued = await _attest(m["mandate_id"])
    nbf = _claims(issued["attestation"])["nbf"]
    assert (await _verify(issued["attestation"], now=nbf - 1))["reason"] == "not_yet_valid"


async def test_another_registry_key_is_refused(tmp_path: Path) -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    other_priv, other_pub = tmp_path / "other.pem", tmp_path / "other.pub"
    generate_signing_key(other_priv, other_pub)
    result = verify_attestation(attestation, other_pub.read_bytes())
    assert result["reason"] == "key_mismatch"


async def test_forged_signature_is_refused(tmp_path: Path) -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    claims = _claims(attestation)
    claims["amr_mandate"]["scope"] = "Anything at all"
    # Same kid, signed with another key: the signature check must catch it.
    forger = _new_key()
    header = jwt.get_unverified_header(attestation)
    forged = jwt.encode(claims, forger, algorithm="EdDSA", headers=header)
    assert (await _verify(forged))["reason"] == "bad_signature"


async def test_modified_payload_is_refused() -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    head, _, sig = attestation.split(".")
    claims = _claims(attestation)
    claims["amr_mandate"]["scope"] = "Anything at all"
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    assert (await _verify(f"{head}.{body}.{sig}"))["reason"] == "bad_signature"


async def test_action_token_is_not_an_attestation() -> None:
    m = await _mandate()
    token = json.loads(await issue_action_token(
        mandate_id=m["mandate_id"], agent_id=AGENT, action="order", audience="seller:acme"
    ))["token"]
    assert (await _verify(token, audience="seller:acme"))["reason"] == "not_an_attestation"


async def test_attestation_is_not_an_action_token() -> None:
    """A JWT library alone accepts it: action-token consumers must check typ and
    amr_action_hash (docs/token-issuance-spec.md), which an attestation lacks."""
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"], audience="seller:acme"))["attestation"]
    claims = jwt.decode(attestation, await _public_key_pem(), algorithms=["EdDSA"],
                        audience="seller:acme")
    assert "amr_action_hash" not in claims
    assert jwt.get_unverified_header(attestation)["typ"] == ATTESTATION_TYP


async def test_algorithm_none_is_refused() -> None:
    m = await _mandate()
    claims = _claims((await _attest(m["mandate_id"]))["attestation"])
    unsigned = jwt.encode(claims, None, algorithm="none",
                          headers={"typ": ATTESTATION_TYP})
    assert (await _verify(unsigned))["reason"] == "wrong_algorithm"


async def test_garbage_is_refused() -> None:
    assert (await _verify("not.a.jws"))["reason"] == "malformed"
    assert (await _verify(""))["reason"] == "malformed"


async def test_rsa_or_garbage_public_key_is_refused() -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    assert verify_attestation(attestation, b"nope")["reason"] == "public_key_invalid"
    from cryptography.hazmat.primitives.asymmetric import rsa

    rsa_pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key(
    ).public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert verify_attestation(attestation, rsa_pem)["reason"] == "public_key_invalid"


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda c: c.update(amr_attestation="mandate.v0"), "not_an_attestation"),
        (lambda c: c.pop("amr_attestation"), "not_an_attestation"),
        (lambda c: c.pop("jti"), "claims_invalid"),
        (lambda c: c.update(exp=str(c["exp"])), "claims_invalid"),
        (lambda c: c.update(sub="agent:other"), "claims_invalid"),
        (lambda c: c["amr_mandate"].update(status="revoked"), "claims_invalid"),
        (lambda c: c["amr_mandate"].pop("scope"), "claims_invalid"),
        (lambda c: c["amr_mandate"].update(perimeter_digest="0" * 64), "claims_invalid"),
        (lambda c: c["amr_mandate"].update(perimeter={"allowed_actions": ["*"]}),
         "claims_invalid"),
        (lambda c: c["amr_mandate"].update(expires_at="2000-01-01T00:00:00+00:00"),
         "claims_invalid"),
        (lambda c: c["amr_mandate"].update(parent_mandate_id=str(uuid4())), "claims_invalid"),
        (lambda c: c.update(amr_chain="none"), "claims_invalid"),
        (lambda c: c.update(amr_mandate="none"), "claims_invalid"),
    ],
)
async def test_inconsistent_content_is_refused_even_if_signed(mutate, reason) -> None:
    """The verifier checks the content, not only the signature of the registry."""
    m = await _mandate(allowed_actions=["supplies.order"])
    claims = _claims((await _attest(m["mandate_id"]))["attestation"])
    mutate(claims)
    result = await _verify(_resign(claims))
    assert result["valid"] is False
    assert result["reason"] == reason


async def test_wrong_typ_is_refused_even_if_signed() -> None:
    m = await _mandate()
    claims = _claims((await _attest(m["mandate_id"]))["attestation"])
    assert (await _verify(_resign(claims, typ="JWT")))["reason"] == "not_an_attestation"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda chain: chain.pop(),  # root missing
        lambda chain: chain.reverse(),  # out of order
        lambda chain: chain[0].update(status="revoked"),  # a cut parent
        lambda chain: chain[1].update(expires_at="2000-01-01T00:00:00+00:00"),
        lambda chain: chain[0].pop("principal_id"),
        lambda chain: chain[1].update(parent_mandate_id=str(uuid4())),  # no root
        lambda chain: chain[0].update(id=str(uuid4())),  # a parent that is not ours
        lambda chain: chain[0].update(agent_id="agent:other"),  # not the delegator
        lambda chain: chain[0].update(principal_id="org:other"),  # root's agent differs
    ],
)
async def test_inconsistent_chain_is_refused_even_if_signed(mutate) -> None:
    root = await _mandate(
        agent_id="agent:lead", duration_hours=48,
        allowed_actions=["supplies.*"], delegation_allowed=True,
    )
    middle = await _mandate(
        principal_id="agent:lead", agent_id="agent:buyer",
        parent_mandate_id=root["mandate_id"], duration_hours=36,
        allowed_actions=["supplies.*"], delegation_allowed=True,
    )
    leaf = await _mandate(
        principal_id="agent:buyer", agent_id=AGENT, parent_mandate_id=middle["mandate_id"],
        allowed_actions=["supplies.order"],
    )
    claims = _claims((await _attest(leaf["mandate_id"]))["attestation"])
    mutate(claims["amr_chain"])
    assert (await _verify(_resign(claims)))["reason"] == "claims_invalid"


async def test_registry_vouched_signature_still_checks_its_key_id() -> None:
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key)
    claims = _claims((await _attest(m["mandate_id"]))["attestation"])
    claims["amr_mandate"]["principal_signature"]["public_key"] = _pub(_new_key())
    assert (await _verify(_resign(claims)))["reason"] == "principal_signature_invalid"


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda b, m: b.update(signature=b64url_encode(b"\x00" * 64)),
         "principal_signature_invalid"),
        (lambda b, m: b.update(public_key=_pub(_new_key())), "principal_signature_invalid"),
        (lambda b, m: b.update(key_id="0" * 16), "principal_signature_invalid"),
        (lambda b, m: m.update(scope="Anything at all"), "principal_signature_invalid"),
        (lambda b, m: m.update(principal_id="org:other"), "principal_signature_invalid"),
        (lambda b, m: m.update(perimeter=Perimeter(allowed_actions=("*",)).canonical(),
                               perimeter_digest=Perimeter(allowed_actions=("*",)).digest()),
         "principal_signature_invalid"),
        (lambda b, m: b.update(signed_at="2020-01-01T00:00:00+00:00"),
         "principal_signature_invalid"),
        (lambda b, m: b.update(payload="not json"), "principal_signature_invalid"),
        (lambda b, m: b.pop("payload"), "claims_invalid"),
        (lambda b, m: m.update(expires_at="2099-01-01T00:00:00+00:00"),
         "principal_signature_invalid"),
        (lambda b, m: m.update(created_at="2000-01-01T00:00:00+00:00"),
         "principal_signature_invalid"),
        (lambda b, m: b.update(key_proof_signature=b64url_encode(b"\x01" * 64)),
         "principal_signature_invalid"),
        (lambda b, m: b.update(key_proof_signature="!"), "principal_signature_invalid"),
    ],
)
async def test_principal_signature_is_rechecked_by_the_receiver(mutate, reason) -> None:
    """Even a registry-signed attestation cannot claim a principal signature it lacks."""
    key = _new_key()
    await _register(key)
    m = await _signed_mandate(key, allowed_actions=["supplies.order"])
    claims = _claims(
        (await _attest(m["mandate_id"], include_principal_payload=True))["attestation"]
    )
    mutate(claims["amr_mandate"]["principal_signature"], claims["amr_mandate"])
    result = await _verify(_resign(claims))
    assert result["valid"] is False
    assert result["reason"] == reason


# --- Public key and offline command ------------------------------------------------------


async def test_registry_public_key_export() -> None:
    exported = json.loads(await get_registry_public_key())
    assert exported["algorithm"] == "EdDSA"
    assert exported["issuer"] == "amr://localhost"
    key = serialization.load_pem_public_key(exported["public_key_pem"].encode())
    assert registry_key_id(key) == exported["key_id"]
    jwk = exported["public_key_jwk"]
    assert (jwk["kty"], jwk["crv"], jwk["kid"]) == ("OKP", "Ed25519", exported["key_id"])
    raw = base64.urlsafe_b64decode(jwk["x"] + "=" * (-len(jwk["x"]) % 4))
    assert ed25519.Ed25519PublicKey.from_public_bytes(raw).public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode() == exported["public_key_pem"]
    assert "PRIVATE" not in json.dumps(exported)


async def test_offline_command(tmp_path: Path, capsys) -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"], audience="seller:acme"))["attestation"]
    pub = tmp_path / "registry.pub"
    pub.write_text(await _public_key_pem())
    token_file = tmp_path / "attestation.jws"
    token_file.write_text(attestation + "\n")

    assert cli_main([str(token_file), "--public-key", str(pub), "--audience", "seller:acme"]) == 0
    capsys.readouterr()
    json_key = tmp_path / "registry.json"
    json_key.write_text(await get_registry_public_key())
    assert cli_main([attestation, "--public-key", str(json_key), "--audience", "seller:acme"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is True
    assert out["attestation"]["mandate_id"] == m["mandate_id"]

    assert cli_main([attestation, "--public-key", str(pub)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "wrong_audience"

    assert cli_main([attestation, "--public-key", str(tmp_path / "missing.pub")]) == 2


# --- Compatibility -----------------------------------------------------------------------


async def test_existing_mandates_and_hashes_are_unchanged(temp_db: Path) -> None:
    """Attesting reads the mandate; it writes only to issued_attestations."""
    m = await _mandate(allowed_actions=["supplies.order"])
    conn = sqlite3.connect(str(temp_db))
    before = conn.execute("SELECT * FROM mandates").fetchall()
    conn.close()
    await _attest(m["mandate_id"])
    conn = sqlite3.connect(str(temp_db))
    after = conn.execute("SELECT * FROM mandates").fetchall()
    versions = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
    conn.close()
    assert before == after
    assert {2, 3, 4, 5} <= versions


async def test_database_without_the_attestation_table_gains_it(temp_db: Path) -> None:
    await init_db(temp_db)
    _sql(temp_db, "DROP TABLE issued_attestations", ())
    _sql(temp_db, "DELETE FROM schema_version WHERE version = ?", (5,))
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id=AGENT)
    issued = await _attest(mandate_id)
    assert "attestation" in issued, issued
    assert (await _verify(issued["attestation"]))["valid"] is True


async def test_verification_needs_no_database(temp_db: Path) -> None:
    m = await _mandate()
    attestation = (await _attest(m["mandate_id"]))["attestation"]
    pem = await _public_key_pem()
    temp_db.unlink()
    result = verify_attestation(attestation, pem, now=time.time())
    assert result["valid"] is True
    assert not temp_db.exists()
