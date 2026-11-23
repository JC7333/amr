"""Refusals reach MCP clients as errors, in one shape (code, message, field).

Unit tests of amr.tool_errors, the wrapper the server puts around every tool, and an
end-to-end check over stdio with the installed MCP SDK (version 1 in the main CI job,
version 2 in "Tests (MCP SDK v2)").
"""

import asyncio
import inspect
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel, Field, ValidationError

from amr import tool_errors
from amr.crypto.signing import generate_signing_key
from amr.server import TOOLS, register_tools, tools_for
from amr.tool_errors import (
    ToolRefusal,
    common_shape,
    is_refusal,
    report_refusals,
    validation_field,
    with_common_shape,
)
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import log_action
from amr.tools.revoke_mandate import revoke_mandate
from amr.tools.verify_mandate import verify_mandate

ROOT = {
    "principal_id": "org:clinic",
    "agent_id": "agent:billing",
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


class _Probe(BaseModel):
    name: str = Field(min_length=3)
    size: int


def _validation_error() -> ValidationError:
    try:
        _Probe(name="x", size="big")
    except ValidationError as exc:
        return exc
    raise AssertionError("no validation error")


# --- what counts as a refusal -------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"error": "anything"},
        {"error": "x", "code": "mandate_not_found"},
        {"denied": True, "reason": "action_out_of_scope"},
        {"valid": False, "reason": "invalid_input"},
        {"valid": False, "reason": "internal_error"},
    ],
)
def test_refusals_are_recognised(body: dict) -> None:
    assert is_refusal(body)


@pytest.mark.parametrize(
    "body",
    [
        {"status": "created", "mandate_id": "m"},
        {"authorized": False, "reason": "No active mandate found"},
        {"valid": False, "reason": "token_expired"},
        {"valid": False, "reason": "bad_signature"},
        {"valid": True, "reason": "ok"},
        {"denied": False},
        {"status": "not_sent", "message": "open new_issue_url"},
        ["error"],
        "error",
    ],
)
def test_answers_are_not_refusals(body: object) -> None:
    assert not is_refusal(body)


# --- the common shape ---------------------------------------------------------------------


def test_code_comes_from_the_tool_code_first() -> None:
    shape = common_shape(
        {"error": "delegation_not_allowed: parent forbids it", "code": "delegation_not_allowed"}
    )
    assert shape == {
        "code": "delegation_not_allowed",
        "message": "parent forbids it",
        "field": None,
    }


def test_code_comes_from_the_reason_without_its_detail() -> None:
    shape = common_shape(
        {"denied": True, "reason": "invalid_input: action_metadata_json must decode to a dict"}
    )
    assert shape["code"] == "invalid_input"
    shape = common_shape(
        {"denied": True, "reason": "action_out_of_scope", "detail": "forbidden:agent.create"}
    )
    assert shape == {
        "code": "action_out_of_scope",
        "message": "action_out_of_scope: forbidden:agent.create",
        "field": None,
    }


def test_an_error_without_code_or_reason_is_internal() -> None:
    assert common_shape({"error": "database is locked"}) == {
        "code": "internal_error",
        "message": "database is locked",
        "field": None,
    }


def test_a_raw_pydantic_text_becomes_a_field_and_a_sentence() -> None:
    raw = str(_validation_error())
    shape = common_shape({"error": raw})
    assert shape["code"] == "invalid_input"
    assert shape["field"] == "name"
    assert shape["message"] == "name: String should have at least 3 characters (and 1 more)"
    assert "type=" not in shape["message"] and "pydantic.dev" not in shape["message"]
    assert "input_value" not in shape["message"]


def test_a_pydantic_text_behind_a_code_keeps_the_code() -> None:
    raw = f"perimeter_invalid: {_validation_error()}"
    shape = common_shape({"error": raw, "code": "perimeter_invalid"})
    assert shape["code"] == "perimeter_invalid"
    assert shape["field"] == "name"


def test_a_whole_input_error_has_no_field() -> None:
    class _Pair(BaseModel):
        low: int
        high: int

        def model_post_init(self, _context: object) -> None:
            if self.low > self.high:
                raise ValueError("low is above high")

    try:
        _Pair(low=2, high=1)
    except ValidationError as exc:
        raw = str(exc)
    shape = common_shape({"error": raw})
    assert shape["field"] is None
    assert shape["message"] == "low is above high"


def test_validation_field_names_the_first_field() -> None:
    assert validation_field(_validation_error()) == "name"


def test_invalid_input_message_names_its_field() -> None:
    shape = common_shape(
        {"error": "invalid_input: too short", "code": "invalid_input", "field": "reason"}
    )
    assert shape == {"code": "invalid_input", "message": "reason: too short", "field": "reason"}


def test_the_tool_keys_are_kept_and_never_overwritten() -> None:
    original = {"error": "x: y", "code": "x", "message": "mine", "field": "f", "refused_by": "m1"}
    shaped, refused = with_common_shape(json.dumps(original))
    assert refused
    assert json.loads(shaped) == original


def test_a_success_is_returned_byte_for_byte() -> None:
    text = json.dumps({"status": "created", "mandate_id": "m", "chain_hash": "ab"})
    assert with_common_shape(text) == (text, False)
    assert with_common_shape("not json") == ("not json", False)


# --- the wrapper --------------------------------------------------------------------------


def _is_error(result: object) -> bool | None:
    return getattr(result, "isError", getattr(result, "is_error", None))


def _text(result: object) -> str:
    return result.content[0].text


def _structured(result: object) -> object:
    return getattr(result, "structuredContent", getattr(result, "structured_content", None))


async def test_a_refusal_becomes_an_mcp_error_with_the_common_shape() -> None:
    result = await report_refusals(get_proof)(str(uuid4()))
    assert _is_error(result) is True
    body = json.loads(_text(result))
    assert body["code"] == "mandate_not_found"
    assert body["field"] == "mandate_id"
    assert "not found" in body["message"]
    assert body["error"].startswith("Mandate '")  # the old key is still there
    assert _structured(result) == {"result": _text(result)}


async def test_a_success_goes_through_unchanged() -> None:
    created = await report_refusals(create_mandate)(**ROOT)
    assert isinstance(created, str)
    assert json.loads(created)["status"] == "created"


async def test_an_old_sdk_gets_an_exception_carrying_the_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tool_errors, "PASSES_RESULTS_THROUGH", False)
    with pytest.raises(ToolRefusal) as caught:
        await report_refusals(get_proof)("not-a-uuid")
    body = json.loads(str(caught.value))
    assert body["code"] == "invalid_input"
    assert body["field"] == "mandate_id"


def test_the_sdk_version_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    for version, expected in [
        ("1.18.3", False),
        ("1.19.0", True),
        ("1.27.0", True),
        ("2.3.0", True),
        ("0.9", False),
    ]:
        monkeypatch.setattr(tool_errors.importlib.metadata, "version", lambda _name, v=version: v)
        assert tool_errors._sdk_passes_results_through() is expected


def test_wrapping_keeps_name_doc_and_signature() -> None:
    for tool in TOOLS:
        wrapped = report_refusals(tool)
        assert wrapped.__name__ == tool.__name__
        assert wrapped.__doc__ == tool.__doc__
        assert inspect.signature(wrapped) == inspect.signature(tool)
        assert inspect.iscoroutinefunction(wrapped)


class _Recorder:
    def __init__(self) -> None:
        self.registered: list = []

    def tool(self, annotations=None):
        def register(fn):
            self.registered.append(fn)
            return fn

        return register


@pytest.mark.parametrize("profile", ["full", "principal", "agent", "receiver"])
def test_every_registered_tool_is_wrapped(profile: str) -> None:
    server = _Recorder()
    register_tools(server, profile)
    assert [fn.__wrapped__ for fn in server.registered] == list(tools_for(profile))


def test_the_sdk_builds_the_same_schemas_for_wrapped_tools() -> None:
    from amr.server import make_server

    plain, wrapped = make_server(), make_server()
    for tool in TOOLS:
        plain.tool()(tool)
    register_tools(wrapped, "full")

    def schemas(server) -> dict:
        out = {}
        for t in asyncio.run(server.list_tools()):
            data = t.model_dump(by_alias=True, exclude={"annotations"})
            out[t.name] = (
                data.get("inputSchema"),
                data.get("outputSchema"),
                data.get("description"),
            )
        return out

    assert schemas(wrapped) == schemas(plain)


# --- real refusals of the tools, through the wrapper ---------------------------------------


async def _created() -> str:
    body = json.loads(await create_mandate(**ROOT))
    assert body["status"] == "created", body
    return body["mandate_id"]


async def test_log_action_refusals_get_their_own_codes() -> None:
    wrapped = report_refusals(log_action)
    bad = json.loads(_text(await wrapped(mandate_id="nope", action="x")))
    assert (bad["code"], bad["field"]) == ("invalid_input", "mandate_id")
    missing = json.loads(_text(await wrapped(mandate_id=str(uuid4()), action="x")))
    assert (missing["code"], missing["field"]) == ("mandate_not_found", "mandate_id")
    mandate_id = await _created()
    revoked = json.loads(await revoke_mandate(mandate_id=mandate_id, reason="ended"))
    assert revoked.get("status") == "revoked", revoked
    result = await wrapped(mandate_id=mandate_id, action="x")
    assert _is_error(result) is True
    assert json.loads(_text(result))["code"] == "mandate_status_revoked"


async def test_log_action_on_an_expired_mandate(temp_db: Path) -> None:
    from tests._helpers import insert_mandate_directly

    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, hours_until_expiry=-1)
    body = json.loads(_text(await report_refusals(log_action)(mandate_id=mandate_id, action="x")))
    assert body["code"] == "mandate_expired"
    other = str(uuid4())
    await insert_mandate_directly(temp_db, other, status="suspended")
    body = json.loads(_text(await report_refusals(log_action)(mandate_id=other, action="x")))
    assert body["code"] == "mandate_status_suspended"


async def test_issue_action_token_refusal_is_an_error() -> None:
    mandate_id = await _created()
    result = await report_refusals(issue_action_token)(
        mandate_id=mandate_id,
        agent_id="agent:billing",
        action="create an agent",
        audience="runtime://erp",
        action_type="agent.create",
    )
    assert _is_error(result) is True
    body = json.loads(_text(result))
    assert body["denied"] is True and body["reason"] == "action_out_of_scope"
    assert body["code"] == "action_out_of_scope"


async def test_verify_mandate_no_is_an_answer_not_an_error() -> None:
    answer = await report_refusals(verify_mandate)(agent_id="agent:nobody", action="read")
    assert isinstance(answer, str)
    assert json.loads(answer)["authorized"] is False


async def test_check_action_token_bad_token_is_an_answer_bad_input_is_an_error() -> None:
    from amr.tools.check_action_token import check_action_token

    wrapped = report_refusals(check_action_token)
    answer = await wrapped(token="not.a.token", audience="runtime://erp")
    assert isinstance(answer, str)
    assert json.loads(answer)["valid"] is False
    failed = await wrapped(token="", audience="")
    assert _is_error(failed) is True
    assert json.loads(_text(failed))["code"] == "invalid_input"


async def test_create_mandate_bad_input_names_the_field() -> None:
    result = await report_refusals(create_mandate)(**{**ROOT, "duration_hours": -5})
    assert _is_error(result) is True
    body = json.loads(_text(result))
    assert body["code"] == "invalid_input"
    assert body["field"] == "duration_hours"
    assert body["message"].startswith("duration_hours: ")


async def test_revoke_mandate_bad_input_names_the_field() -> None:
    mandate_id = await _created()
    body = json.loads(
        _text(await report_refusals(revoke_mandate)(mandate_id=mandate_id, reason=""))
    )
    assert body["code"] == "invalid_input"
    assert body["field"] == "reason"


async def test_export_insurer_dossier_codes() -> None:
    wrapped = report_refusals(export_insurer_dossier)
    missing = json.loads(_text(await wrapped(mandate_id=str(uuid4()))))
    assert (missing["code"], missing["field"]) == ("mandate_not_found", "mandate_id")
    bad = json.loads(_text(await wrapped(mandate_id="nope")))
    assert (bad["code"], bad["field"]) == ("invalid_input", "mandate_id")
    mandate_id = await _created()
    order = json.loads(
        _text(
            await wrapped(
                mandate_id=mandate_id,
                period_start="2026-02-01T00:00:00+00:00",
                period_end="2026-01-01T00:00:00+00:00",
            )
        )
    )
    # Checked on the whole input by the request model: no single field to blame.
    assert (order["code"], order["field"]) == ("invalid_input", None)
    assert order["message"] == "period_start must not be after period_end"
    # Only period_end, before the mandate was created: the period starts at creation.
    early = json.loads(
        _text(await wrapped(mandate_id=mandate_id, period_end="2020-01-01T00:00:00+00:00"))
    )
    assert (early["code"], early["field"]) == ("invalid_input", "period_end")


async def test_export_insurer_dossier_without_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mandate_id = await _created()
    monkeypatch.setattr("amr.config.settings.signing_key_path", tmp_path / "absent.pem")
    body = json.loads(_text(await report_refusals(export_insurer_dossier)(mandate_id=mandate_id)))
    assert body["code"] == "registry_key_missing"


async def test_direct_python_calls_are_unchanged() -> None:
    """Only the MCP layer adds message: a direct call still returns the tool's own JSON."""
    body = json.loads(await get_proof(str(uuid4())))
    assert "message" not in body
    assert body["error"].endswith("not found")


# --- end to end, over stdio, with the installed SDK ----------------------------------------


def test_stdio_client_sees_refusals_as_errors(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(
        os.environ,
        AMR_DB_PATH=str(tmp_path / "amr.db"),
        AMR_SIGNING_KEY_PATH=str(tmp_path / "key.pem"),
        AMR_PUBLIC_KEY_PATH=str(tmp_path / "key.pub"),
    )
    params = StdioServerParameters(command=sys.executable, args=["-m", "amr.server"], env=env)

    async def session() -> dict:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            out = {}
            out["created"] = await client.call_tool("create_mandate", ROOT)
            mandate_id = json.loads(out["created"].content[0].text)["mandate_id"]
            out["unknown"] = await client.call_tool("get_proof", {"mandate_id": str(uuid4())})
            out["no"] = await client.call_tool(
                "verify_mandate", {"agent_id": "agent:x", "action": "read"}
            )
            out["denied"] = await client.call_tool(
                "issue_action_token",
                {
                    "mandate_id": mandate_id,
                    "agent_id": "agent:billing",
                    "action": "create an agent",
                    "audience": "runtime://erp",
                    "action_type": "agent.create",
                },
            )
            out["invalid"] = await client.call_tool(
                "create_mandate", {**ROOT, "duration_hours": -5}
            )
            return out

    out = asyncio.run(asyncio.wait_for(session(), timeout=60))
    assert not _is_error(out["created"])
    assert not _is_error(out["no"])
    assert json.loads(out["no"].content[0].text)["authorized"] is False
    for name, code, field in [
        ("unknown", "mandate_not_found", "mandate_id"),
        ("denied", "action_out_of_scope", None),
        ("invalid", "invalid_input", "duration_hours"),
    ]:
        result = out[name]
        assert _is_error(result) is True, name
        body = json.loads(result.content[0].text)
        assert (body["code"], body["field"]) == (code, field), name
        assert body["message"], name
