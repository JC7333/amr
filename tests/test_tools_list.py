"""python -m amr.tools_list prints the tools/list response a client receives.

Directories that read the code see no tool (AMR registers them in a loop); they take the
tools/list response pasted by hand. That response must be the one a real client gets, for
the chosen profile, in camelCase JSON as the MCP specification writes it.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from amr import tools_list as tools_list_module
from amr.server import TOOL_PROFILES, TOOLS, tools_for
from amr.tools_list import main, tool_as_json, tools_list

ROOT = Path(__file__).resolve().parent.parent
RELEASE = (ROOT / "docs" / "release.md").read_text(encoding="utf-8")


def _names(listing: dict) -> list[str]:
    return [tool["name"] for tool in listing["tools"]]


@pytest.mark.parametrize("profile", sorted(TOOL_PROFILES))
def test_lists_the_profile_tools_in_server_order(profile: str) -> None:
    assert _names(tools_list(profile)) == [tool.__name__ for tool in tools_for(profile)]


def test_full_profile_lists_every_tool() -> None:
    assert _names(tools_list("full")) == [tool.__name__ for tool in TOOLS]


def test_receiver_profile_hides_the_principal_tools() -> None:
    names = set(_names(tools_list("receiver")))
    assert names == set(TOOL_PROFILES["receiver"])
    assert "create_mandate" not in names and "revoke_mandate" not in names


def test_each_tool_has_description_and_camel_case_input_schema() -> None:
    for tool in tools_list("full")["tools"]:
        assert tool["description"].strip(), tool["name"]
        assert tool["inputSchema"]["type"] == "object", tool["name"]
        assert "input_schema" not in tool, tool["name"]


def test_keys_are_written_as_the_mcp_specification_names_them() -> None:
    """SDK 2 names the fields input_schema and meta in Python; the wire names are camelCase."""
    from amr.server import mcp

    tool_type = type(asyncio.run(mcp.list_tools())[0])
    tool = tool_type.model_validate(
        {"name": "probe", "inputSchema": {"type": "object"}, "_meta": {"k": 1}}
    )
    assert tool_as_json(tool) == {
        "name": "probe",
        "inputSchema": {"type": "object"},
        "_meta": {"k": 1},
    }


def test_no_null_fields_are_printed() -> None:
    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key != "default":  # a JSON Schema default may legitimately be null
                    assert item is not None, key
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for tool in tools_list("full")["tools"]:
        walk({k: v for k, v in tool.items() if k != "inputSchema"})


def test_main_prints_json_for_the_requested_profile(capsys) -> None:
    assert main(["--profile", "agent"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert _names(printed) == [tool.__name__ for tool in tools_for("agent")]


def test_main_defaults_to_the_configured_profile(capsys, monkeypatch) -> None:
    monkeypatch.setattr(tools_list_module.settings, "tool_profile", "receiver")
    assert main([]) == 0
    assert set(_names(json.loads(capsys.readouterr().out))) == set(TOOL_PROFILES["receiver"])


def test_main_refuses_an_unknown_profile(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--profile", "admin"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize("profile", sorted(TOOL_PROFILES))
def test_output_matches_what_a_real_client_receives(tmp_path, profile: str) -> None:
    """Start the real server over stdio and compare its tools/list with the printed one."""
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

    async def session() -> list[dict]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = (await client.list_tools()).tools
            return [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in tools]

    received = asyncio.run(asyncio.wait_for(session(), timeout=60))
    assert tools_list(profile)["tools"] == received


def test_the_command_runs_as_a_module_and_writes_nothing(tmp_path) -> None:
    import subprocess

    env = {k: v for k, v in os.environ.items() if not k.startswith("AMR_")}
    out = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [sys.executable, "-m", "amr.tools_list", "--profile", "receiver"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        cwd=tmp_path,
        env=env,
    ).stdout
    assert set(_names(json.loads(out))) == set(TOOL_PROFILES["receiver"])
    assert list(tmp_path.iterdir()) == []  # no database, no key, no file of any kind


def test_release_guide_gives_the_command() -> None:
    assert "python -m amr.tools_list" in RELEASE
    assert "uvx --from mandatia python -m amr.tools_list" in RELEASE
    assert "0.1.2 on PyPI does not have it" in RELEASE
