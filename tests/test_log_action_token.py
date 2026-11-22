"""log_action under an action token: the logged action is tied to a token the registry issued."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.config import Settings, settings
from amr.crypto.chain import compute_hash
from amr.crypto.signing import generate_signing_key, get_key_id, load_signing_key
from amr.server import mcp
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import MAX_TOKEN_LENGTH, log_action
from amr.tools.revoke_mandate import revoke_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"
AUDIENCE = "runtime://erp"
OLD_ACTION_FIELDS = {
    "id",
    "mandate_id",
    "agent_id",
    "action",
    "evidence",
    "result",
    "timestamp",
    "chain_hash",
}

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Handle supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
    "allowed_actions": ["invoice.*"],
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


async def _token(mandate_id: str, action_type: str = "invoice.pay", agent_id: str = AGENT) -> dict:
    result = json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=agent_id,
            action=f"{action_type} {uuid4()}",
            audience=AUDIENCE,
            action_type=action_type,
        )
    )
    assert "token" in result, result
    return result


async def _log(mandate_id: str, token: str | None = None, action: str = "Paid invoice") -> dict:
    return json.loads(
        await log_action(
            mandate_id=mandate_id,
            action=action,
            evidence="erp:invoice-42",
            result="Paid",
            action_token=token,
        )
    )


async def _proof(mandate_id: str) -> dict:
    return json.loads(await get_proof(mandate_id))


def _sql(db_path: Path, query: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _registry_pem() -> bytes:
    return load_signing_key().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _resign(token: str, key_pem: bytes | None = None, **overrides: object) -> str:
    """The same claims (with overrides), signed with the registry key or another one."""
    claims = jwt.decode(token, options={"verify_signature": False})
    claims.update(overrides)
    return jwt.encode(
        claims,
        key_pem if key_pem is not None else _registry_pem(),
        algorithm="EdDSA",
        headers={"kid": get_key_id(), "typ": "JWT"},
    )


# --- Without a token: nothing changes --------------------------------------------------


async def test_default_setting_is_off() -> None:
    assert Settings().require_action_token_for_log is False


async def test_setting_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMR_REQUIRE_ACTION_TOKEN_FOR_LOG", "true")
    assert Settings().require_action_token_for_log is True


async def test_action_without_token_keeps_its_fields_and_hash(temp_db: Path) -> None:
    mandate_id = await _mandate()
    logged = await _log(mandate_id)
    assert logged["status"] == "logged"
    assert "token_jti" not in logged

    proof = await _proof(mandate_id)
    entry = proof["actions"][0]
    # Exactly the fields an action had before tokens could cover it.
    assert set(entry) == OLD_ACTION_FIELDS
    # The hash is the one the previous log_action wrote: its seven fields, read from
    # the stored row (not from get_proof), chained to the mandate hash.
    row = _sql(
        temp_db,
        "SELECT id, mandate_id, agent_id, action, evidence, result, timestamp, chain_hash "
        "FROM action_logs",
    )[0]
    old_data = dict(
        zip(
            ("id", "mandate_id", "agent_id", "action", "evidence", "result", "timestamp"),
            row[:7],
            strict=True,
        )
    )
    assert compute_hash(old_data, proof["mandate"]["chain_hash"]) == row[7]
    assert row[7] == logged["chain_hash"]
    assert proof["chain_integrity"]["actions_chain_valid"] is True
    assert proof["chain_integrity"]["actions_with_token"] == 0


# --- With a valid token ------------------------------------------------------------------


async def test_valid_token_is_sealed_into_the_entry() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    logged = await _log(mandate_id, issued["token"])
    assert logged["status"] == "logged", logged
    assert logged["token_jti"] == issued["jti"]

    proof = await _proof(mandate_id)
    entry = proof["actions"][0]
    claims = jwt.decode(issued["token"], options={"verify_signature": False})
    assert entry["action_token_jti"] == issued["jti"]
    assert entry["action_token_action_hash"] == claims["amr_action_hash"]
    data = {key: value for key, value in entry.items() if key != "chain_hash"}
    assert compute_hash(data, proof["mandate"]["chain_hash"]) == entry["chain_hash"]
    assert entry["chain_hash"] == logged["chain_hash"]
    assert proof["chain_integrity"]["actions_chain_valid"] is True
    assert proof["chain_integrity"]["actions_with_token"] == 1


async def test_mixed_chain_stays_valid() -> None:
    mandate_id = await _mandate()
    await _log(mandate_id, action="Read invoice")
    issued = await _token(mandate_id)
    await _log(mandate_id, issued["token"])
    await _log(mandate_id, action="Filed receipt")
    proof = await _proof(mandate_id)
    assert proof["chain_integrity"]["actions_chain_valid"] is True
    assert proof["chain_integrity"]["total_actions"] == 3
    assert proof["chain_integrity"]["actions_with_token"] == 1
    assert ["action_token_jti" in a for a in proof["actions"]] == [False, True, False]


async def test_required_setting_logs_a_covered_action(monkeypatch: pytest.MonkeyPatch) -> None:
    mandate_id = await _mandate()
    monkeypatch.setattr(settings, "require_action_token_for_log", True)
    issued = await _token(mandate_id)
    logged = await _log(mandate_id, issued["token"])
    assert logged["status"] == "logged", logged


async def test_sub_mandate_token_covers_its_own_action() -> None:
    root = await _mandate(delegation_allowed=True)
    child = json.loads(
        await create_mandate(
            principal_id=AGENT,
            agent_id=HELPER,
            scope="Pay invoices",
            legal_basis_regulation="Service contract",
            legal_basis_article="Clause 4",
            duration_hours=12.0,
            parent_mandate_id=root,
            allowed_actions=["invoice.pay"],
        )
    )
    assert child.get("status") == "created", child
    issued = await _token(child["mandate_id"], agent_id=HELPER)
    assert (await _log(child["mandate_id"], issued["token"]))["status"] == "logged"
    # The child's token does not cover an action logged under the root.
    issued2 = await _token(child["mandate_id"], agent_id=HELPER)
    refused = await _log(root, issued2["token"])
    assert refused["reason"] == "token_mandate_mismatch"


# --- Refusals ----------------------------------------------------------------------------


async def test_required_setting_refuses_an_action_without_token(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mandate_id = await _mandate()
    monkeypatch.setattr(settings, "require_action_token_for_log", True)
    refused = await _log(mandate_id)
    assert refused["reason"] == "action_token_required"
    assert "error" in refused
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(0,)]


async def test_token_covers_one_action_only(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    assert (await _log(mandate_id, issued["token"]))["status"] == "logged"
    again = await _log(mandate_id, issued["token"], action="Paid it twice")
    assert again["reason"] == "token_already_used"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(1,)]


async def test_token_of_another_mandate_is_refused(temp_db: Path) -> None:
    first = await _mandate()
    second = await _mandate(scope="Handle customer invoices")
    issued = await _token(first)
    refused = await _log(second, issued["token"])
    assert refused["reason"] == "token_mandate_mismatch"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(0,)]


@pytest.mark.parametrize("garbage", ["", "not-a-token", "a.b.c"])
async def test_malformed_token_is_refused(temp_db: Path, garbage: str) -> None:
    mandate_id = await _mandate()
    refused = await _log(mandate_id, garbage)
    assert refused["reason"] == "malformed"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(0,)]


async def test_oversized_token_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    # A real token padded past the limit is refused by length, before any decoding.
    refused = await _log(mandate_id, issued["token"] + "A" * MAX_TOKEN_LENGTH)
    assert refused["reason"] == "malformed"
    assert "token too long" in refused["error"]


async def test_expired_token_is_refused(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    past = int(datetime.now(UTC).timestamp()) - 60
    refused = await _log(mandate_id, _resign(issued["token"], exp=past))
    assert refused["reason"] == "token_expired"
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(0,)]


async def test_token_not_yet_valid_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    future = int(datetime.now(UTC).timestamp()) + 120
    refused = await _log(mandate_id, _resign(issued["token"], nbf=future))
    assert refused["reason"] == "token_not_yet_valid"


async def test_concurrent_calls_with_one_token_log_one_action(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    results = await asyncio.gather(
        *(_log(mandate_id, issued["token"], action=f"Paid {i}") for i in range(6))
    )
    assert [r.get("status") for r in results].count("logged") == 1
    refused = [r for r in results if r.get("status") != "logged"]
    assert {r.get("reason") for r in refused} == {"token_already_used"}
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(1,)]
    assert (await _proof(mandate_id))["chain_integrity"]["actions_chain_valid"] is True


async def test_database_from_before_v11_is_upgraded(temp_db: Path) -> None:
    mandate_id = await _mandate()
    old = await _log(mandate_id)
    # A registry as the previous version left it: no action_log_tokens, no version 11.
    _sql(temp_db, "DROP TABLE action_log_tokens")
    _sql(temp_db, "DELETE FROM schema_version WHERE version = 11")
    issued = await _token(mandate_id)
    assert (await _log(mandate_id, issued["token"]))["status"] == "logged"
    assert (11,) in _sql(temp_db, "SELECT version FROM schema_version")
    proof = await _proof(mandate_id)
    assert proof["actions"][0]["chain_hash"] == old["chain_hash"]
    assert proof["chain_integrity"]["actions_chain_valid"] is True
    assert proof["chain_integrity"]["actions_with_token"] == 1


async def test_token_signed_with_another_key_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    other = ed25519.Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    refused = await _log(mandate_id, _resign(issued["token"], key_pem=other))
    assert refused["reason"] == "bad_signature"


async def test_unsigned_token_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    claims = jwt.decode(issued["token"], options={"verify_signature": False})
    unsigned = jwt.encode(claims, key=None, algorithm="none")
    refused = await _log(mandate_id, unsigned)
    assert refused["reason"] == "wrong_algorithm"


async def test_token_the_registry_never_issued_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    refused = await _log(mandate_id, _resign(issued["token"], jti=str(uuid4())))
    assert refused["reason"] == "unknown_token"


async def test_token_with_altered_claims_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    refused = await _log(mandate_id, _resign(issued["token"], amr_action_hash="1" * 64))
    assert refused["reason"] == "token_record_mismatch"
    refused = await _log(mandate_id, _resign(issued["token"], aud="runtime://other"))
    assert refused["reason"] == "token_record_mismatch"


async def test_token_with_another_issuer_is_refused() -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    refused = await _log(mandate_id, _resign(issued["token"], iss="amr://elsewhere"))
    assert refused["reason"] == "wrong_issuer"


async def test_token_record_of_another_agent_is_refused(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    # A record and token naming another agent than the mandate's (forged in the database).
    _sql(temp_db, "UPDATE issued_tokens SET agent_id = ? WHERE jti = ?", (HELPER, issued["jti"]))
    refused = await _log(mandate_id, _resign(issued["token"], sub=HELPER))
    assert refused["reason"] == "agent_mismatch"


async def test_revoked_mandate_refuses_even_with_a_valid_token(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    revoked = json.loads(await revoke_mandate(mandate_id=mandate_id, reason="Stopped"))
    assert revoked.get("status") == "revoked", revoked
    refused = await _log(mandate_id, issued["token"])
    assert "error" in refused
    assert _sql(temp_db, "SELECT COUNT(*) FROM action_logs") == [(0,)]


# --- Tampering ---------------------------------------------------------------------------


async def test_deleting_the_token_link_breaks_the_chain(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    await _log(mandate_id, issued["token"])
    _sql(temp_db, "DELETE FROM action_log_tokens")
    proof = await _proof(mandate_id)
    assert proof["chain_integrity"]["actions_chain_valid"] is False


async def test_adding_a_token_link_breaks_the_chain(temp_db: Path) -> None:
    mandate_id = await _mandate()
    logged = await _log(mandate_id)
    issued = await _token(mandate_id)
    _sql(
        temp_db,
        "INSERT INTO action_log_tokens (action_id, jti, mandate_id, action_hash) "
        "VALUES (?, ?, ?, ?)",
        (logged["action_id"], issued["jti"], mandate_id, "0" * 64),
    )
    proof = await _proof(mandate_id)
    assert proof["chain_integrity"]["actions_chain_valid"] is False


async def test_database_refuses_a_second_link_for_one_token(temp_db: Path) -> None:
    mandate_id = await _mandate()
    issued = await _token(mandate_id)
    await _log(mandate_id, issued["token"])
    other = await _log(mandate_id)
    with pytest.raises(sqlite3.IntegrityError):
        _sql(
            temp_db,
            "INSERT INTO action_log_tokens (action_id, jti, mandate_id, action_hash) "
            "VALUES (?, ?, ?, ?)",
            (other["action_id"], issued["jti"], mandate_id, "0" * 64),
        )


async def test_schema_records_version_11(temp_db: Path) -> None:
    await _mandate()
    assert (11,) in _sql(temp_db, "SELECT version FROM schema_version")


# --- MCP schema ----------------------------------------------------------------------------


async def test_mcp_schema_exposes_an_optional_action_token() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    tool = tools["log_action"]
    # MCP SDK 1 names it inputSchema, SDK 2 input_schema.
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    assert "action_token" in schema["properties"]
    assert "action_token" not in schema.get("required", [])
