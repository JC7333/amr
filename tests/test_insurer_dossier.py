"""Tests for export_insurer_dossier: content, signature, offline verification, print view."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from pydantic import ValidationError

from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.models.dossier import InsurerDossierRequest
from amr.proof.insurer_dossier import (
    DOSSIER_TYPE,
    DossierVerificationError,
    canonical_bytes,
    dossier_digest,
    verify_dossier,
)
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import log_action
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key

PRINCIPAL = "org:clinic"
AGENT = "agent:scheduler"

ROOT = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Book and move patient appointments",
    "legal_basis_regulation": "Service contract",
    "legal_basis_article": "Clause 4",
    "duration_hours": 48.0,
    "allowed_actions": ["appointment.*", "agent.create"],
    "forbidden_actions": ["appointment.delete"],
    "delegation_allowed": True,
    "max_amount": "250",
    "amount_actions": ["appointment.pay"],
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "registry_key.pem"
    pub = tmp_path / "registry_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


def _registry_pem() -> str:
    from amr.config import settings

    return settings.public_key_path.read_text(encoding="utf-8")


async def _create(**kwargs: object) -> str:
    result = json.loads(await create_mandate(**kwargs))
    assert "mandate_id" in result, result
    return result["mandate_id"]


async def _root(**overrides: object) -> str:
    return await _create(**{**ROOT, **overrides})


async def _sub(parent_id: str, parent_agent: str, agent: str, **overrides: object) -> str:
    params: dict = {
        "principal_id": parent_agent,
        "agent_id": agent,
        "scope": "Move appointments only",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 24.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["appointment.move"],
    }
    params.update(overrides)
    return await _create(**params)


async def _export(mandate_id: str, **kwargs: object) -> dict:
    return json.loads(await export_insurer_dossier(mandate_id, **kwargs))


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
    return rows


# --- Content ----------------------------------------------------------------------


async def test_dossier_states_the_mandate_and_its_perimeter() -> None:
    mandate_id = await _root()
    result = await _export(mandate_id)
    dossier = result["dossier"]

    assert dossier["dossier_version"] == "1.0"
    assert dossier["mandate"]["id"] == mandate_id
    assert dossier["mandate"]["principal_id"] == PRINCIPAL
    assert dossier["mandate"]["agent_id"] == AGENT
    perimeter = dossier["mandate"]["perimeter"]
    assert perimeter["allowed_actions"] == ["agent.create", "appointment.*"]
    assert perimeter["forbidden_actions"] == ["appointment.delete"]
    assert perimeter["delegation_allowed"] is True
    assert perimeter["max_amount"] == "250"
    assert perimeter["amount_actions"] == ["appointment.pay"]
    assert dossier["status"] == {
        "stored_status": "active",
        "in_force": True,
        "not_in_force_reason": None,
    }
    assert dossier["limits"]
    assert dossier["sub_mandates"] == []
    assert dossier["sub_mandates_truncated"] is False


async def test_default_period_runs_from_creation_to_generation() -> None:
    mandate_id = await _root()
    dossier = (await _export(mandate_id))["dossier"]
    assert (
        dossier["period"]["start"]
        == datetime.fromisoformat(dossier["mandate"]["created_at"]).isoformat()
    )
    assert dossier["period"]["end"] == dossier["generated_at"]


async def test_revoked_mandate_is_not_in_force_and_cuts_its_sub_mandates(temp_db: Path) -> None:
    root = await _root()
    child = await _sub(root, AGENT, "agent:helper")
    _sql(temp_db, "UPDATE mandates SET status = 'revoked' WHERE id = ?", (root,))

    dossier = (await _export(root))["dossier"]

    assert dossier["status"]["in_force"] is False
    assert dossier["status"]["not_in_force_reason"] == "mandate_revoked"
    (sub,) = dossier["sub_mandates"]
    assert sub["id"] == child
    assert sub["status"]["stored_status"] == "active"
    assert sub["status"]["in_force"] is False
    assert sub["status"]["not_in_force_reason"] == "parent_mandate_not_in_force"


async def test_expired_mandate_is_not_in_force(temp_db: Path) -> None:
    root = await _root()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    _sql(temp_db, "UPDATE mandates SET expires_at = ? WHERE id = ?", (past, root))

    dossier = (await _export(root))["dossier"]

    assert dossier["status"]["in_force"] is False
    assert dossier["status"]["not_in_force_reason"] == "mandate_expired"


async def test_dossier_of_a_sub_mandate_reports_the_broken_chain_above(temp_db: Path) -> None:
    root = await _root()
    child = await _sub(root, AGENT, "agent:helper")
    _sql(temp_db, "UPDATE mandates SET status = 'revoked' WHERE id = ?", (root,))

    dossier = (await _export(child))["dossier"]

    assert dossier["status"]["stored_status"] == "active"
    assert dossier["status"]["in_force"] is False
    assert dossier["status"]["not_in_force_reason"] == "parent_mandate_revoked"


async def test_sub_mandate_tree_is_listed_with_depth() -> None:
    root = await _root()
    child = await _sub(
        root,
        AGENT,
        "agent:helper",
        allowed_actions=["appointment.move", "agent.create"],
        delegation_allowed=True,
    )
    grandchild = await _sub(child, "agent:helper", "agent:grand", duration_hours=12.0)
    sibling = await _sub(root, AGENT, "agent:other")

    dossier = (await _export(root))["dossier"]
    by_id = {s["id"]: s for s in dossier["sub_mandates"]}

    assert set(by_id) == {child, grandchild, sibling}
    assert by_id[child]["depth"] == 1
    assert by_id[sibling]["depth"] == 1
    assert by_id[grandchild]["depth"] == 2
    assert by_id[grandchild]["parent_mandate_id"] == child
    assert by_id[grandchild]["perimeter"]["allowed_actions"] == ["appointment.move"]
    assert all(s["status"]["in_force"] for s in dossier["sub_mandates"])


async def test_revoked_child_cuts_only_its_own_branch(temp_db: Path) -> None:
    root = await _root()
    child = await _sub(
        root,
        AGENT,
        "agent:helper",
        allowed_actions=["appointment.move", "agent.create"],
        delegation_allowed=True,
    )
    grandchild = await _sub(child, "agent:helper", "agent:grand", duration_hours=12.0)
    sibling = await _sub(root, AGENT, "agent:other")
    _sql(temp_db, "UPDATE mandates SET status = 'revoked' WHERE id = ?", (child,))

    by_id = {s["id"]: s for s in (await _export(root))["dossier"]["sub_mandates"]}

    assert by_id[child]["status"]["not_in_force_reason"] == "mandate_revoked"
    assert by_id[grandchild]["status"]["not_in_force_reason"] == "parent_mandate_not_in_force"
    assert by_id[sibling]["status"]["in_force"] is True


async def test_sub_mandate_list_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("amr.tools.export_insurer_dossier.MAX_SUB_MANDATES", 2)
    root = await _root()
    for n in range(3):
        await _sub(root, AGENT, f"agent:helper-{n}")

    dossier = (await _export(root))["dossier"]

    assert len(dossier["sub_mandates"]) == 2
    assert dossier["sub_mandates_truncated"] is True


async def test_sub_mandate_tree_is_bounded_in_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("amr.tools.export_insurer_dossier.MAX_DELEGATION_DEPTH", 1)
    root = await _root()
    child = await _sub(
        root,
        AGENT,
        "agent:helper",
        allowed_actions=["appointment.move", "agent.create"],
        delegation_allowed=True,
    )
    await _sub(child, "agent:helper", "agent:grand", duration_hours=12.0)

    dossier = (await _export(root))["dossier"]

    assert [s["id"] for s in dossier["sub_mandates"]] == [child]
    assert dossier["sub_mandates_truncated"] is True


async def test_actions_are_filtered_by_period(temp_db: Path) -> None:
    root = await _root()
    for label in ("first", "second", "third"):
        assert json.loads(await log_action(mandate_id=root, action=label))["status"] == "logged"
    stamps = [
        row[0]
        for row in _sql(
            temp_db,
            "SELECT timestamp FROM action_logs WHERE mandate_id = ? ORDER BY timestamp",
            (root,),
        )
    ]

    dossier = (await _export(root, period_start=stamps[1], period_end=stamps[1]))["dossier"]

    assert [a["action"] for a in dossier["actions"]] == ["second"]
    assert dossier["integrity"]["total_actions"] == 3
    assert dossier["integrity"]["actions_chain_valid"] is True


async def test_sub_mandate_actions_are_counted_in_period() -> None:
    root = await _root()
    child = await _sub(root, AGENT, "agent:helper")
    await log_action(mandate_id=child, action="moved")
    await log_action(mandate_id=child, action="moved again")

    (sub,) = (await _export(root))["dossier"]["sub_mandates"]
    assert sub["actions_in_period"] == 2
    assert sub["integrity"]["total_actions"] == 2

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    later = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    (sub,) = (await _export(root, period_start=future, period_end=later))["dossier"]["sub_mandates"]
    assert sub["actions_in_period"] == 0


async def test_chain_head_is_the_last_action_hash() -> None:
    root = await _root()
    dossier = (await _export(root))["dossier"]
    assert dossier["integrity"]["chain_head"] == dossier["mandate"]["chain_hash"]

    await log_action(mandate_id=root, action="booked")
    logged = json.loads(await log_action(mandate_id=root, action="moved"))
    dossier = (await _export(root))["dossier"]
    assert dossier["integrity"]["chain_head"] == logged["chain_hash"]


async def test_tampered_action_log_shows_in_the_dossier(temp_db: Path) -> None:
    root = await _root()
    await log_action(mandate_id=root, action="booked", evidence="ticket:1")
    _sql(temp_db, "UPDATE action_logs SET evidence = 'ticket:2' WHERE mandate_id = ?", (root,))

    dossier = (await _export(root))["dossier"]

    assert dossier["integrity"]["actions_chain_valid"] is False


async def test_tokens_of_the_tree_are_listed_with_period() -> None:
    root = await _root()
    child = await _sub(root, AGENT, "agent:helper")
    issued_root = json.loads(
        await issue_action_token(
            root, AGENT, "Book slot 9:00", "calendar", action_type="appointment.book"
        )
    )
    issued_child = json.loads(
        await issue_action_token(
            child, "agent:helper", "Move slot", "calendar", action_type="appointment.move"
        )
    )
    assert "token" in issued_root and "token" in issued_child

    tokens = (await _export(root))["dossier"]["tokens"]
    assert {t["jti"] for t in tokens} == {issued_root["jti"], issued_child["jti"]}
    assert {t["mandate_id"] for t in tokens} == {root, child}

    past_start = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    past_end = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    tokens = (await _export(root, period_start=past_start, period_end=past_end))["dossier"][
        "tokens"
    ]
    assert tokens == []


async def test_status_events_in_period_are_listed(temp_db: Path) -> None:
    root = await _root()
    child = await _sub(root, AGENT, "agent:helper")
    now = datetime.now(UTC)
    old = (now - timedelta(days=10)).isoformat()
    _sql(
        temp_db,
        "INSERT INTO mandate_events (mandate_id, event_type, timestamp, reason) "
        "VALUES (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)",
        (
            root, "suspended", now.isoformat(), "incident review",
            child, "revoked", now.isoformat(), "operator stop",
            root, "note", old, "outside the period",
        ),
    )  # fmt: skip

    events = (await _export(root))["dossier"]["events"]

    assert {(e["mandate_id"], e["event_type"]) for e in events} == {
        (root, "suspended"),
        (child, "revoked"),
    }


async def test_principal_signature_is_reported(temp_db: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    public = b64url_encode(raw)
    proof = b64url_encode(key.sign(key_registration_payload(PRINCIPAL, public)))
    registered = json.loads(await register_principal_key(PRINCIPAL, public, proof))
    prepared = json.loads(await prepare_mandate_signature(**ROOT))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    signed = await _root(principal_signature=signature, signed_at=prepared["signed_at"])
    unsigned = await _root(principal_id="org:other")

    integrity = (await _export(signed))["dossier"]["integrity"]
    assert integrity["principal_signature_valid"] is True
    assert integrity["principal_key_id"] == registered["key_id"]

    integrity = (await _export(unsigned))["dossier"]["integrity"]
    assert integrity["principal_signature_valid"] is None
    assert integrity["principal_key_id"] is None

    _sql(temp_db, "UPDATE mandates SET scope = 'Anything' WHERE id = ?", (signed,))
    integrity = (await _export(signed))["dossier"]["integrity"]
    assert integrity["principal_signature_valid"] is False


async def test_export_writes_nothing(temp_db: Path) -> None:
    root = await _root()
    await _sub(root, AGENT, "agent:helper")
    await log_action(mandate_id=root, action="booked")
    tables = ("mandates", "action_logs", "mandate_events", "issued_tokens", "principal_keys")

    def snapshot() -> dict[str, list[tuple]]:
        return {t: _sql(temp_db, f"SELECT * FROM {t} ORDER BY 1") for t in tables}  # noqa: S608

    before = snapshot()
    await _export(root, format="html")
    assert snapshot() == before


# --- Signature --------------------------------------------------------------------


async def test_signed_dossier_verifies_with_the_registry_key() -> None:
    root = await _root()
    await log_action(mandate_id=root, action="booked")
    result = await _export(root)

    verified = verify_dossier(result["signature"]["jws"], _registry_pem())

    assert verified == result["dossier"]
    assert result["dossier_sha256"] == dossier_digest(result["dossier"])
    assert result["signature"]["algorithm"] == "EdDSA"
    assert result["signature"]["public_key_pem"] == _registry_pem()
    header = jwt.get_unverified_header(result["signature"]["jws"])
    assert header == {"alg": "EdDSA", "kid": result["signature"]["key_id"], "typ": DOSSIER_TYPE}


async def test_dossier_does_not_verify_with_another_key(tmp_path: Path) -> None:
    root = await _root()
    jws = (await _export(root))["signature"]["jws"]
    other_priv, other_pub = tmp_path / "other.pem", tmp_path / "other.pub"
    generate_signing_key(other_priv, other_pub)

    with pytest.raises(DossierVerificationError):
        verify_dossier(jws, other_pub.read_text(encoding="utf-8"))


async def test_tampered_dossier_does_not_verify() -> None:
    root = await _root()
    jws = (await _export(root))["signature"]["jws"]
    header, payload, signature = jws.split(".")
    dossier = json.loads(jwt.utils.base64url_decode(payload))
    dossier["status"]["in_force"] = not dossier["status"]["in_force"]
    forged_payload = jwt.utils.base64url_encode(canonical_bytes(dossier)).decode()

    with pytest.raises(DossierVerificationError):
        verify_dossier(f"{header}.{forged_payload}.{signature}", _registry_pem())


async def test_unsigned_and_hmac_dossiers_are_refused() -> None:
    root = await _root()
    dossier = (await _export(root))["dossier"]
    payload = canonical_bytes(dossier)
    pem = _registry_pem()
    unsigned = jwt.api_jws.PyJWS().encode(
        payload, None, algorithm="none", headers={"typ": DOSSIER_TYPE}
    )
    with pytest.raises(DossierVerificationError):
        verify_dossier(unsigned, pem)

    # Algorithm confusion: the public key used as an HMAC secret.
    jws_hmac = jwt.api_jws.PyJWS()
    jws_hmac._algorithms["HS256"].prepare_key = lambda key: key  # type: ignore[method-assign]
    forged = jws_hmac.encode(
        payload, pem.encode(), algorithm="HS256", headers={"typ": DOSSIER_TYPE}
    )
    with pytest.raises(DossierVerificationError):
        verify_dossier(forged, pem)


def test_registry_jws_of_another_type_is_refused() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    other = jwt.api_jws.PyJWS().encode(
        canonical_bytes({"a": 1}), key, algorithm="EdDSA", headers={"typ": "JWT"}
    )
    with pytest.raises(DossierVerificationError, match="not an AMR insurer dossier"):
        verify_dossier(other, pem)


def test_non_canonical_payload_is_refused() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    loose = jwt.api_jws.PyJWS().encode(
        b'{"b": 1, "a": 2}', key, algorithm="EdDSA", headers={"typ": DOSSIER_TYPE}
    )
    with pytest.raises(DossierVerificationError, match="canonical"):
        verify_dossier(loose, pem)


def test_bad_public_key_is_refused() -> None:
    with pytest.raises(DossierVerificationError):
        verify_dossier("a.b.c", "not a key")


# --- Print view -------------------------------------------------------------------


async def test_html_view_is_self_contained_and_escaped() -> None:
    root = await _root(scope="<script>alert(1)</script> & co")
    await log_action(mandate_id=root, action="<img src=x onerror=alert(2)>")
    result = await _export(root, format="html")
    page = result["html"]

    assert page.startswith("<!doctype html>")
    assert "<script>" not in page
    assert "<img" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co" in page
    assert "http://" not in page and "https://" not in page
    assert result["dossier_sha256"] in page
    assert result["signature"]["key_id"] in page
    assert "appointment.delete" in page
    assert "250 EUR" in page


async def test_json_format_has_no_html() -> None:
    root = await _root()
    assert "html" not in await _export(root)


# --- Input validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"period_start": "not a date"},
        {"period_end": "2026-13-01"},
        {"period_start": "2026-10-02T00:00:00Z", "period_end": "2026-10-01T00:00:00Z"},
        {"format": "pdf"},
    ],
)
async def test_invalid_input_is_refused(kwargs: dict) -> None:
    root = await _root()
    result = await _export(root, **kwargs)
    assert result["error"].startswith("Invalid input")


async def test_period_start_after_default_end_is_refused() -> None:
    root = await _root()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    result = await _export(root, period_start=future)
    assert result["error"].startswith("Invalid input")


async def test_unknown_or_malformed_mandate_is_refused() -> None:
    assert "error" in await _export(str(uuid.uuid4()))
    assert "error" in await _export("not-a-uuid")


async def test_naive_period_reads_as_utc(temp_db: Path) -> None:
    root = await _root()
    await log_action(mandate_id=root, action="booked")
    (stamp,) = _sql(temp_db, "SELECT timestamp FROM action_logs WHERE mandate_id = ?", (root,))[0]
    naive = datetime.fromisoformat(stamp).astimezone(UTC).replace(tzinfo=None).isoformat()

    dossier = (await _export(root, period_start=naive, period_end=naive))["dossier"]

    assert [a["action"] for a in dossier["actions"]] == ["booked"]
    assert dossier["period"]["start"].endswith("+00:00")


def test_canonical_form_sorts_keys_without_whitespace() -> None:
    assert canonical_bytes({"b": 1, "a": {"d": 2, "c": "é"}}) == (
        '{"a":{"c":"é","d":2},"b":1}'.encode()
    )


def test_non_ed25519_public_key_is_refused() -> None:
    pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    with pytest.raises(DossierVerificationError, match="not Ed25519"):
        verify_dossier("a.b.c", pem)


def test_request_model_refuses_reversed_period_and_unknown_fields() -> None:
    mandate_id = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        InsurerDossierRequest(
            mandate_id=mandate_id,
            period_start="2026-10-02T00:00:00Z",
            period_end="2026-10-01T00:00:00Z",
        )
    with pytest.raises(ValidationError):
        InsurerDossierRequest(mandate_id=mandate_id, period="october")


@pytest.mark.parametrize("bound", ["2026-10-31", "1700000000", 1, "2026-10-31 12:00"])
async def test_period_bound_without_time_is_refused(bound: object) -> None:
    root = await _root()
    result = await _export(root, period_end=bound)
    assert result["error"].startswith("Invalid input")


async def test_export_never_creates_a_signing_key(tmp_path: Path, monkeypatch) -> None:
    root = await _root()
    missing_priv, missing_pub = tmp_path / "none.pem", tmp_path / "none.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", missing_priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", missing_pub)

    result = await _export(root)

    assert "signing key" in result["error"]
    assert not missing_priv.exists() and not missing_pub.exists()


async def test_sub_mandate_actions_are_not_listed_as_the_mandates_own() -> None:
    root = await _root()
    child = await _sub(root, AGENT, "agent:helper")
    await log_action(mandate_id=root, action="booked")
    await log_action(mandate_id=child, action="moved")

    dossier = (await _export(root))["dossier"]

    assert [a["action"] for a in dossier["actions"]] == ["booked"]
    assert {a["mandate_id"] for a in dossier["actions"]} == {root}


async def test_bidi_controls_are_neutralised_in_the_print_view() -> None:
    root = await _root(scope="pay \u202erof 01 EUR")
    page = (await _export(root, format="html"))["html"]
    assert "\u202e" not in page
    assert "pay \ufffdrof 01 EUR" in page
