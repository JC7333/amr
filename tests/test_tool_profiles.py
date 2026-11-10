"""AMR_TOOL_PROFILE: a server exposes the principal's tools, the agent's, the receiver's, or all.

An agent that can create, sign or revoke its own root mandate authorizes itself, and the
mandate proves nothing. The agent profile therefore never exposes the principal's tools,
and create_mandate refuses a root mandate there (sub-mandates stay possible).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from amr.config import Settings
from amr.crypto.signing import generate_signing_key
from amr.server import TOOL_PROFILES, TOOLS, tools_for
from amr.tools.create_mandate import create_mandate

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
ALL = {tool.__name__ for tool in TOOLS}

# What only the principal may do: grant, sign, revoke, contest.
PRINCIPAL_ONLY = {
    "register_principal_key",
    "prepare_mandate_signature",
    "prepare_mandate_pdf",
    "attach_signed_mandate_pdf",
    "revoke_mandate",
    "prepare_revocation_signature",
    "contest_action",
    "prepare_contest_signature",
}
# What only the acting agent does: ask for a token, log its act.
AGENT_ONLY = {"issue_action_token", "log_action"}

BASE = {
    "scope": "Pay supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
}


def _names(profile: str) -> set[str]:
    return {tool.__name__ for tool in tools_for(profile)}


def test_every_profile_names_only_real_tools() -> None:
    for profile, names in TOOL_PROFILES.items():
        assert names <= ALL, (profile, names - ALL)


def test_full_profile_is_every_tool() -> None:
    assert _names("full") == ALL
    assert len(ALL) == 19


def test_agent_profile_cannot_grant_sign_or_revoke() -> None:
    agent = _names("agent")
    assert not agent & PRINCIPAL_ONLY
    assert agent >= AGENT_ONLY
    assert "check_action_token" not in agent


def test_principal_profile_does_not_act_for_the_agent() -> None:
    principal = _names("principal")
    assert principal >= PRINCIPAL_ONLY
    assert not principal & AGENT_ONLY
    assert "create_mandate" in principal


def test_receiver_profile_only_checks() -> None:
    assert _names("receiver") == {"check_action_token", "get_registry_public_key", "report_issue"}


def test_every_tool_belongs_to_a_restricted_profile() -> None:
    restricted = _names("principal") | _names("agent") | _names("receiver")
    assert restricted == ALL


def test_profiles_keep_the_server_order() -> None:
    order = [tool.__name__ for tool in TOOLS]
    for profile in TOOL_PROFILES:
        names = [tool.__name__ for tool in tools_for(profile)]
        assert names == [n for n in order if n in names]


def test_default_profile_is_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMR_TOOL_PROFILE", raising=False)
    assert Settings(_env_file=None).tool_profile == "full"


@pytest.mark.parametrize("profile", ["full", "principal", "agent", "receiver"])
def test_profile_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    monkeypatch.setenv("AMR_TOOL_PROFILE", profile)
    assert Settings(_env_file=None).tool_profile == profile


@pytest.mark.parametrize("profile", ["admin", "Agent", "", "all"])
def test_unknown_profile_is_refused(monkeypatch: pytest.MonkeyPatch, profile: str) -> None:
    monkeypatch.setenv("AMR_TOOL_PROFILE", profile)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --- create_mandate in the agent profile ------------------------------------------------


@pytest.fixture
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv, pub = tmp_path / "key.pem", tmp_path / "key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _create(**kwargs: object) -> dict:
    return json.loads(await create_mandate(**BASE, **kwargs))


async def test_agent_profile_refuses_a_root_mandate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("amr.config.settings.tool_profile", "agent")
    result = await _create(
        principal_id="org:clinic", agent_id="agent:assistant", duration_hours=24.0,
        allowed_actions=["invoice.pay"],
    )
    assert result.get("code") == "root_mandate_needs_principal", result
    assert "mandate_id" not in result


async def test_agent_profile_keeps_sub_mandates(monkeypatch: pytest.MonkeyPatch, keys) -> None:
    root = await _create(
        principal_id="org:clinic", agent_id="agent:assistant", duration_hours=24.0,
        allowed_actions=["invoice.*"], delegation_allowed=True,
    )
    assert "mandate_id" in root, root
    monkeypatch.setattr("amr.config.settings.tool_profile", "agent")
    child = await _create(
        principal_id="agent:assistant", agent_id="agent:sub", duration_hours=12.0,
        allowed_actions=["invoice.read"], parent_mandate_id=root["mandate_id"],
    )
    assert "mandate_id" in child, child


@pytest.mark.parametrize("profile", ["full", "principal"])
async def test_other_profiles_create_root_mandates(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    monkeypatch.setattr("amr.config.settings.tool_profile", profile)
    result = await _create(
        principal_id="org:clinic", agent_id="agent:assistant", duration_hours=24.0,
        allowed_actions=["invoice.pay"],
    )
    assert "mandate_id" in result, result


# --- the real server over stdio -------------------------------------------------------------


@pytest.mark.parametrize("profile", ["agent", "receiver"])
def test_stdio_server_lists_only_the_profile_tools(tmp_path: Path, profile: str) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(
        os.environ,
        AMR_DB_PATH=str(tmp_path / "amr.db"),
        AMR_SIGNING_KEY_PATH=str(tmp_path / "key.pem"),
        AMR_PUBLIC_KEY_PATH=str(tmp_path / "key.pub"),
        AMR_TOOL_PROFILE=profile,
    )
    params = StdioServerParameters(command=sys.executable, args=["-m", "amr.server"], env=env)

    async def session() -> set[str]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            return {t.name for t in (await client.list_tools()).tools}

    names = asyncio.run(asyncio.wait_for(session(), timeout=60))
    assert names == _names(profile)


# --- documentation ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [README, AGENTS], ids=["README", "AGENTS"])
def test_docs_explain_the_profiles(text: str) -> None:
    assert "AMR_TOOL_PROFILE" in text
    for profile in ("principal", "agent", "receiver"):
        assert f"`{profile}`" in text
