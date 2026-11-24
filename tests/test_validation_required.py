"""Human validation required by the mandate (validation_actions).

The principal lists action types that need a human validation. For them, the action
metadata must carry the declared validator (validated_by) and the SHA-256 of the content
validated (validated_content_sha256); otherwise no token. Both values are sealed into the
token, returned by check_action_token and shown by get_proof. A sub-mandate cannot lift
the requirement. Mandates without it behave, hash and sign exactly as before.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import ValidationError

from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.db.engine import init_db
from amr.mandate_pdf import _summary
from amr.models.perimeter import Perimeter, validation_detail
from amr.templates import AGENT_SANTE_RGPD
from amr.tool_errors import report_refusals
from amr.tools.check_action_token import check_action_token
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import log_action
from amr.tools.prepare_mandate_pdf import prepare_mandate_pdf
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.verify_mandate import verify_mandate
from tests._helpers import insert_mandate_directly

PRINCIPAL = "org:clinic"
AGENT = "agent:scribe"
HELPER = "agent:helper"
AUDIENCE = "runtime://records"
NOTE = "Consultation note, validated text"
NOTE_SHA = hashlib.sha256(NOTE.encode("utf-8")).hexdigest()
VALIDATED = {"validated_by": "user:dr-a", "validated_content_sha256": NOTE_SHA}

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Draft and file consultation notes",
    "legal_basis_regulation": "Committee decision",
    "legal_basis_article": "Item 3",
    "duration_hours": 24.0,
    "allowed_actions": ["note.*", "record.read"],
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


async def _child(parent_id: str, **overrides: object) -> str:
    params: dict = {
        "principal_id": AGENT,
        "agent_id": HELPER,
        "scope": "File notes",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 12.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["note.send"],
        **overrides,
    }
    result = json.loads(await create_mandate(**params))
    assert result.get("status") == "created", result
    return result["mandate_id"]


async def _issue(
    mandate_id: str,
    action_type: str = "note.send",
    metadata: dict[str, str] | None = None,
    agent_id: str = AGENT,
) -> dict:
    return json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=agent_id,
            action=f"{action_type} {uuid4()}",
            audience=AUDIENCE,
            action_metadata_json=json.dumps(metadata or {}),
            action_type=action_type,
        )
    )


def _claims(issued: dict) -> dict:
    return jwt.decode(issued["token"], options={"verify_signature": False})


def _sql(db_path: Path, query: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


# --- the perimeter model ---------------------------------------------------------------


def test_a_perimeter_without_the_field_keeps_its_exact_form() -> None:
    perimeter = Perimeter(allowed_actions=("note.*",), forbidden_actions=("note.delete",))
    assert perimeter.to_json() == (
        '{"allowed_actions":["note.*"],"amount_actions":[],"currency":"EUR",'
        '"delegation_allowed":false,"forbidden_actions":["note.delete"],"max_amount":null}'
    )
    assert "validation_actions" not in perimeter.canonical()


def test_the_field_is_sorted_deduplicated_and_sealed() -> None:
    perimeter = Perimeter(
        allowed_actions=("note.*",), validation_actions=("note.send", "note.amend", "note.send")
    )
    assert perimeter.canonical()["validation_actions"] == ["note.amend", "note.send"]
    plain = Perimeter(allowed_actions=("note.*",))
    assert perimeter.digest() != plain.digest()
    assert Perimeter.from_json(perimeter.to_json()) == perimeter


@pytest.mark.parametrize("bad", ["Note.Send", "note..send", "", "note.send!", "*.send"])
def test_an_invalid_pattern_is_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("note.*",), validation_actions=(bad,))


def test_validation_detail_names_what_is_missing() -> None:
    assert validation_detail({}) == (
        "validation_required:validated_by,validated_content_sha256"
    )
    assert validation_detail({"validated_by": "user:x"}) == (
        "validation_required:validated_content_sha256"
    )
    assert validation_detail({"validated_content_sha256": NOTE_SHA}) == (
        "validation_required:validated_by"
    )
    assert validation_detail(VALIDATED) is None


@pytest.mark.parametrize(
    ("metadata", "field"),
    [
        ({"validated_by": "", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "   ", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "user:a\nuser:b", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "user:a\x85b", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "user:a\u2028b", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "user:dr-a\u202e", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "\u200b", "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "x" * 201, "validated_content_sha256": NOTE_SHA}, "validated_by"),
        ({"validated_by": "user:a", "validated_content_sha256": NOTE_SHA.upper()},
         "validated_content_sha256"),
        ({"validated_by": "user:a", "validated_content_sha256": NOTE_SHA[:63]},
         "validated_content_sha256"),
        ({"validated_by": "user:a", "validated_content_sha256": NOTE_SHA + "0"},
         "validated_content_sha256"),
    ],
)
def test_validation_detail_refuses_bad_values(metadata: dict, field: str) -> None:
    assert validation_detail(metadata) == f"validation_invalid:{field}"


def test_a_validator_of_200_characters_is_accepted() -> None:
    assert validation_detail({**VALIDATED, "validated_by": "x" * 200}) is None
    assert validation_detail({**VALIDATED, "validated_by": "Dr Hélène Café"}) is None


def test_check_action_reaches_sub_types_and_only_them() -> None:
    perimeter = Perimeter(
        allowed_actions=("note.*", "record.read"), validation_actions=("note.send",)
    )
    assert perimeter.check_action("note.send", {}) == (
        "validation_required:validated_by,validated_content_sha256"
    )
    assert perimeter.check_action("note.send.urgent", {}) is not None
    assert perimeter.check_action("note.sendx", {}) is None
    assert perimeter.check_action("note.draft", {}) is None
    assert perimeter.check_action("note.send", VALIDATED) is None


def test_forbidden_and_amount_rules_still_apply() -> None:
    perimeter = Perimeter(
        allowed_actions=("note.*",),
        forbidden_actions=("note.delete",),
        validation_actions=("note.*",),
        max_amount="10",  # type: ignore[arg-type]
        amount_actions=("note.bill",),
    )
    assert perimeter.check_action("note.delete", VALIDATED) == "forbidden:note.delete"
    assert perimeter.check_action("record.read", VALIDATED) == "not_allowed:record.read"
    assert perimeter.check_action("note.bill", VALIDATED) == "amount_required"
    over = {**VALIDATED, "amount": "11", "currency": "EUR"}
    assert perimeter.check_action("note.bill", over) == "amount_above_limit:10 EUR"


def test_a_sub_mandate_inherits_the_requirement_and_can_add_one() -> None:
    parent = Perimeter(
        allowed_actions=("note.*",), delegation_allowed=True, validation_actions=("note.send",)
    )
    child = Perimeter(allowed_actions=("note.*",)).narrowed_by(parent)
    assert child.validation_actions == ("note.send",)
    added = Perimeter(allowed_actions=("note.*",), validation_actions=("note.amend",)).narrowed_by(
        parent
    )
    assert added.validation_actions == ("note.amend", "note.send")


# --- creation, signature, display ------------------------------------------------------


async def test_the_mandate_stores_and_returns_the_requirement() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    verified = json.loads(await verify_mandate(AGENT, "file a note", mandate_id=mandate_id))
    assert verified["perimeter"]["validation_actions"] == ["note.send"]


async def test_a_mandate_without_the_requirement_has_no_key() -> None:
    mandate_id = await _mandate()
    verified = json.loads(await verify_mandate(AGENT, "file a note", mandate_id=mandate_id))
    assert "validation_actions" not in verified["perimeter"]


async def test_the_requirement_alone_asks_for_allowed_actions() -> None:
    params = {k: v for k, v in BASE.items() if k != "allowed_actions"}
    result = json.loads(await create_mandate(**params, validation_actions=["note.send"]))
    assert result.get("code") == "perimeter_invalid", result


async def test_the_requirement_is_stored_and_shown_in_the_proof(temp_db: Path) -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    stored = _sql(temp_db, "SELECT perimeter_json FROM mandates WHERE id = ?", (mandate_id,))
    assert '"validation_actions":["note.send"]' in stored[0][0]
    pack = json.loads(await get_proof(mandate_id))
    assert pack["mandate"]["perimeter"]["validation_actions"] == ["note.send"]
    assert pack["chain_integrity"]["actions_chain_valid"] is True


async def test_the_principal_signature_covers_the_requirement() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    pub = b64url_encode(raw)
    proof = b64url_encode(key.sign(key_registration_payload(PRINCIPAL, pub)))
    assert "key_id" in json.loads(await register_principal_key(PRINCIPAL, pub, proof))

    args = {**BASE, "validation_actions": ["note.send"]}
    prepared = json.loads(await prepare_mandate_signature(**args))
    assert '"validation_actions"' in prepared["payload"]
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))

    lifted = {k: v for k, v in args.items() if k != "validation_actions"}
    refused = json.loads(await create_mandate(
        **lifted, principal_signature=signature, signed_at=prepared["signed_at"]
    ))
    assert refused.get("code") == "principal_signature_invalid", refused

    created = json.loads(await create_mandate(
        **args, principal_signature=signature, signed_at=prepared["signed_at"]
    ))
    assert created.get("status") == "created", created
    pack = json.loads(await get_proof(created["mandate_id"]))
    assert pack["chain_integrity"]["principal_signature_valid"] is True


async def test_a_payload_without_the_requirement_is_unchanged() -> None:
    prepared = json.loads(
        await prepare_mandate_signature(**BASE, signed_at="2026-11-24T10:00:00+00:00")
    )
    assert "validation_actions" not in prepared["payload"]


async def test_the_pdf_shows_the_requirement() -> None:
    prepared = json.loads(
        await prepare_mandate_pdf(**BASE, validation_actions=["note.send"])
    )
    content = json.loads(prepared["payload"])
    rows = dict(_summary(content))
    assert rows["Human validation required for"].startswith("note.send")
    plain = dict(_summary(json.loads(json.loads(await prepare_mandate_pdf(**BASE))["payload"])))
    assert "Human validation required for" not in plain


async def test_the_insurer_dossier_shows_the_requirement_only_when_set() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    page = json.loads(await export_insurer_dossier(mandate_id, format="html"))["html"]
    assert "Human validation required for" in page
    assert "not authenticated by the registry" in page
    plain = await _mandate(agent_id="agent:other")
    page = json.loads(await export_insurer_dossier(plain, format="html"))["html"]
    assert "Human validation required for" not in page


def test_a_template_passes_its_requirement_to_create_mandate() -> None:
    assert "validation_actions" not in AGENT_SANTE_RGPD.create_mandate_kwargs()
    required = AGENT_SANTE_RGPD.perimeter.model_copy(
        update={"validation_actions": ("letter.draft",)}
    )
    template = AGENT_SANTE_RGPD.model_copy(update={"perimeter": required})
    assert template.create_mandate_kwargs()["validation_actions"] == ["letter.draft"]


# --- issuance --------------------------------------------------------------------------


async def test_no_token_without_the_validation() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    denied = await _issue(mandate_id)
    assert denied["denied"] is True
    assert denied["reason"] == "action_out_of_scope"
    assert denied["detail"] == "validation_required:validated_by,validated_content_sha256"
    assert denied["refused_by"] == mandate_id


async def test_the_refusal_reaches_an_mcp_client_as_an_error() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    result = await report_refusals(issue_action_token)(
        mandate_id=mandate_id,
        agent_id=AGENT,
        action="send the note",
        audience=AUDIENCE,
        action_type="note.send",
    )
    assert getattr(result, "isError", getattr(result, "is_error", None)) is True
    body = json.loads(result.content[0].text)
    assert body["code"] == "action_out_of_scope"
    assert "validation_required" in body["message"]


async def test_no_token_with_a_malformed_hash() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    denied = await _issue(
        mandate_id, metadata={**VALIDATED, "validated_content_sha256": "not-a-hash"}
    )
    assert denied["detail"] == "validation_invalid:validated_content_sha256"


async def test_a_validated_action_gets_a_token_with_both_values_sealed(temp_db: Path) -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    issued = await _issue(mandate_id, metadata=VALIDATED)
    assert "token" in issued, issued
    claims = _claims(issued)
    assert claims["amr_validation_required"] is True
    assert claims["amr_validated_by"] == "user:dr-a"
    assert claims["amr_validated_content_sha256"] == NOTE_SHA
    rows = _sql(
        temp_db,
        "SELECT jti, mandate_id, action_type, validated_by, validated_content_sha256 "
        "FROM token_validations",
    )
    assert rows == [(issued["jti"], mandate_id, "note.send", "user:dr-a", NOTE_SHA)]


async def test_an_action_outside_the_requirement_is_unchanged(temp_db: Path) -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    issued = await _issue(mandate_id, action_type="note.draft", metadata=VALIDATED)
    claims = _claims(issued)
    assert not any(key.startswith("amr_validat") for key in claims)
    assert _sql(temp_db, "SELECT COUNT(*) FROM token_validations") == [(0,)]


async def test_a_mandate_without_the_requirement_issues_unchanged_tokens(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _issue(mandate_id)
    assert "token" in issued, issued
    assert not any(key.startswith("amr_validat") for key in _claims(issued))
    assert _sql(temp_db, "SELECT COUNT(*) FROM token_validations") == [(0,)]


async def test_a_sub_mandate_cannot_lift_the_requirement() -> None:
    root = await _mandate(delegation_allowed=True, validation_actions=["note.send"])
    child = await _child(root)
    verified = json.loads(await verify_mandate(HELPER, "file a note", mandate_id=child))
    assert verified["perimeter"]["validation_actions"] == ["note.send"]
    denied = await _issue(child, agent_id=HELPER)
    assert denied["detail"].startswith("validation_required")
    assert denied["refused_by"] == child
    issued = await _issue(child, agent_id=HELPER, metadata=VALIDATED)
    assert _claims(issued)["amr_validated_by"] == "user:dr-a"


async def test_the_issuer_applies_a_parent_requirement_missing_from_the_stored_child(
    temp_db: Path,
) -> None:
    # Defence in depth: a sub-mandate stored without the parent's requirement (by hand,
    # or before inheritance) is still bound by it at issuance.
    root = await _mandate(delegation_allowed=True, validation_actions=["note.send"])
    child_id = str(uuid4())
    await insert_mandate_directly(
        temp_db,
        child_id,
        principal_id=AGENT,
        agent_id=HELPER,
        perimeter_json=Perimeter(allowed_actions=("note.send",)).to_json(),
        parent_mandate_id=root,
        hours_until_expiry=6.0,
    )
    denied = await _issue(child_id, agent_id=HELPER)
    assert denied["detail"].startswith("validation_required")
    assert denied["refused_by"] == root
    issued = await _issue(child_id, agent_id=HELPER, metadata=VALIDATED)
    assert _claims(issued)["amr_validation_required"] is True
    rows = _sql(temp_db, "SELECT mandate_id FROM token_validations")
    assert rows == [(child_id,)]


async def test_another_content_is_another_action() -> None:
    # The two values are part of the action hash: a token for one validated text does not
    # cover another one.
    mandate_id = await _mandate(validation_actions=["note.send"])
    first = await _issue(mandate_id, metadata=VALIDATED)
    other = hashlib.sha256(b"another text").hexdigest()
    second = await _issue(mandate_id, metadata={**VALIDATED, "validated_content_sha256": other})
    assert _claims(first)["amr_action_hash"] != _claims(second)["amr_action_hash"]


# --- the receiver and the proof --------------------------------------------------------


async def test_check_action_token_returns_both_values() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    issued = await _issue(mandate_id, metadata=VALIDATED)
    checked = json.loads(await check_action_token(issued["token"], AUDIENCE))
    assert checked["valid"] is True, checked
    assert checked["validation_required"] is True
    assert checked["validated_by"] == "user:dr-a"
    assert checked["validated_content_sha256"] == NOTE_SHA


async def test_check_action_token_is_unchanged_without_a_requirement() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    issued = await _issue(mandate_id, action_type="note.draft")
    checked = json.loads(await check_action_token(issued["token"], AUDIENCE))
    assert checked["valid"] is True, checked
    assert not any(key.startswith("validat") for key in checked)


async def test_get_proof_shows_the_validation_and_the_logged_action() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    issued = await _issue(mandate_id, metadata=VALIDATED)
    unused = await _issue(
        mandate_id,
        metadata={**VALIDATED, "validated_content_sha256": hashlib.sha256(b"x").hexdigest()},
    )
    logged = json.loads(
        await log_action(
            mandate_id=mandate_id,
            action="Filed the validated note",
            evidence="records:note-1",
            result="Filed",
            action_token=issued["token"],
        )
    )
    assert logged.get("status") == "logged", logged
    pack = json.loads(await get_proof(mandate_id))
    by_jti = {row["jti"]: row for row in pack["validated_actions"]}
    assert by_jti[issued["jti"]] == {
        "jti": issued["jti"],
        "action_type": "note.send",
        "validated_by": "user:dr-a",
        "validated_content_sha256": NOTE_SHA,
        "issued_at": by_jti[issued["jti"]]["issued_at"],
        "action_id": logged["action_id"],
    }
    assert by_jti[unused["jti"]]["action_id"] is None
    assert pack["chain_integrity"]["actions_chain_valid"] is True


async def test_get_proof_has_no_key_without_a_validation() -> None:
    mandate_id = await _mandate(validation_actions=["note.send"])
    await _issue(mandate_id, action_type="note.draft")
    pack = json.loads(await get_proof(mandate_id))
    assert "validated_actions" not in pack


# --- schema ----------------------------------------------------------------------------


async def test_an_existing_database_gains_the_table_and_keeps_its_rows(
    temp_db: Path,
) -> None:
    # A database from before v12: same schema without token_validations nor version 12.
    mandate_id = await _mandate()
    issued = await _issue(mandate_id, action_type="note.draft")
    conn = sqlite3.connect(temp_db)
    conn.execute("DROP TABLE token_validations")
    conn.execute("DELETE FROM schema_version WHERE version = 12")
    conn.commit()
    conn.close()
    before = _sql(temp_db, "SELECT id, chain_hash, perimeter_json FROM mandates")
    tokens = _sql(temp_db, "SELECT jti, action_hash FROM issued_tokens")
    await init_db(temp_db)
    assert (12,) in _sql(temp_db, "SELECT version FROM schema_version")
    assert _sql(temp_db, "SELECT COUNT(*) FROM token_validations") == [(0,)]
    assert _sql(temp_db, "SELECT id, chain_hash, perimeter_json FROM mandates") == before
    assert _sql(temp_db, "SELECT jti, action_hash FROM issued_tokens") == tokens
    assert tokens[0][0] == issued["jti"]
    pack = json.loads(await get_proof(mandate_id))
    assert "validated_actions" not in pack


async def test_schema_v12_is_recorded_and_idempotent(temp_db: Path) -> None:
    await init_db(temp_db)
    await init_db(temp_db)
    assert (12,) in _sql(temp_db, "SELECT version FROM schema_version")
    columns = [row[1] for row in _sql(temp_db, "PRAGMA table_info(token_validations)")]
    assert columns == [
        "jti",
        "mandate_id",
        "action_type",
        "validated_by",
        "validated_content_sha256",
        "issued_at",
    ]
