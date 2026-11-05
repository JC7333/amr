"""AMR runs with version 1 and version 2 of the MCP Python SDK, without any extra pin.

mcp 2.x renamed ``mcp.server.fastmcp.FastMCP`` to ``mcp.server.mcpserver.MCPServer``. The server
imports the version 2 class when it exists and falls back to the version 1 class otherwise. The
whole suite runs against both versions in CI (job "Tests (MCP SDK v2)").
"""

import asyncio
import importlib.metadata
import importlib.util
import os
import re
import sys
import tomllib
import types
from pathlib import Path

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "src" / "amr" / "server.py"
SERVER = SERVER_PATH.read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
REGISTERED_TOOLS = set(re.findall(r"^mcp\.tool\(\)\((\w+)\)", SERVER, flags=re.MULTILINE))
DOCS = {
    name: (ROOT / name).read_text(encoding="utf-8")
    for name in ("README.md", "AGENTS.md", "llms.txt")
}
CI = ROOT / ".github" / "workflows" / "ci.yml"
INSTALLED_MAJOR = int(importlib.metadata.version("mcp").split(".")[0])


def _mcp_requirement() -> Requirement:
    reqs = [Requirement(d) for d in PYPROJECT["project"]["dependencies"]]
    (mcp,) = [r for r in reqs if r.name == "mcp"]
    return mcp


def _load_server_copy(monkeypatch, modules: dict) -> types.ModuleType:
    """Execute a private copy of amr/server.py with some mcp modules replaced or removed."""
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("amr_server_probe", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeServer:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools: list[str] = []

    def tool(self):
        def register(fn):
            self.tools.append(fn.__name__)
            return fn

        return register


def _fake_module(name: str, attr: str) -> types.ModuleType:
    module = types.ModuleType(name)
    setattr(module, attr, type(attr, (_FakeServer,), {}))
    return module


# --- dependency range ----------------------------------------------------------------------


@pytest.mark.parametrize("version", ["1.2.0", "1.27.0", "2.0.0", "2.3.0", "2.99.0"])
def test_dependency_accepts_mcp_v1_and_v2(version: str) -> None:
    assert version in _mcp_requirement().specifier


@pytest.mark.parametrize("version", ["1.1.0", "3.0.0"])
def test_dependency_refuses_untested_major_versions(version: str) -> None:
    assert version not in _mcp_requirement().specifier


def test_dependency_keeps_the_cli_extra() -> None:
    assert _mcp_requirement().extras == {"cli"}


# --- import selection ----------------------------------------------------------------------


def test_server_uses_the_class_of_the_installed_sdk() -> None:
    from amr.server import mcp

    expected = "MCPServer" if INSTALLED_MAJOR >= 2 else "FastMCP"
    assert type(mcp).__name__ == expected


def test_ci_job_runs_the_expected_sdk_major_version() -> None:
    # CI sets EXPECTED_MCP_MAJOR in each job, so the v2 job cannot silently test version 1.
    expected = os.environ.get("EXPECTED_MCP_MAJOR")
    if expected is None:
        pytest.skip("EXPECTED_MCP_MAJOR is only set in CI")
    assert str(INSTALLED_MAJOR) == expected


def test_v2_class_is_preferred_when_present(monkeypatch) -> None:
    v2 = _fake_module("mcp.server.mcpserver", "MCPServer")
    v1 = _fake_module("mcp.server.fastmcp", "FastMCP")
    probe = _load_server_copy(monkeypatch, {"mcp.server.mcpserver": v2, "mcp.server.fastmcp": v1})
    assert type(probe.mcp) is v2.MCPServer
    assert set(probe.mcp.tools) == REGISTERED_TOOLS


def test_v1_class_is_used_when_v2_module_is_missing(monkeypatch) -> None:
    v1 = _fake_module("mcp.server.fastmcp", "FastMCP")
    # None in sys.modules makes "import mcp.server.mcpserver" raise ModuleNotFoundError,
    # exactly as on mcp 1.x where the module does not exist.
    probe = _load_server_copy(monkeypatch, {"mcp.server.mcpserver": None, "mcp.server.fastmcp": v1})
    assert type(probe.mcp) is v1.FastMCP
    assert set(probe.mcp.tools) == REGISTERED_TOOLS


def test_missing_sdk_is_still_reported(monkeypatch) -> None:
    with pytest.raises(ModuleNotFoundError):
        _load_server_copy(monkeypatch, {"mcp.server.mcpserver": None, "mcp.server.fastmcp": None})


class _BrokenDependencyFinder:
    """Makes "import mcp.server.mcpserver" fail because one of its own dependencies is missing."""

    def find_spec(self, name, path=None, target=None):
        if name == "mcp.server.mcpserver":
            raise ModuleNotFoundError("No module named 'httpx2'", name="httpx2")
        return None


def test_missing_dependency_of_v2_is_not_hidden_by_the_fallback(monkeypatch) -> None:
    v1 = _fake_module("mcp.server.fastmcp", "FastMCP")
    monkeypatch.delitem(sys.modules, "mcp.server.mcpserver", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BrokenDependencyFinder(), *sys.meta_path])
    with pytest.raises(ModuleNotFoundError) as excinfo:
        _load_server_copy(monkeypatch, {"mcp.server.fastmcp": v1})
    assert excinfo.value.name == "httpx2"


def test_server_name_comes_from_settings(monkeypatch) -> None:
    from amr.config import settings

    v2 = _fake_module("mcp.server.mcpserver", "MCPServer")
    probe = _load_server_copy(monkeypatch, {"mcp.server.mcpserver": v2})
    assert probe.mcp.name == settings.server_name


# --- real SDK -----------------------------------------------------------------------------


def test_every_tool_is_listed_with_its_input_schema() -> None:
    from amr.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == REGISTERED_TOOLS
    for tool in tools:
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
        assert schema and schema.get("type") == "object", tool.name


def test_stdio_session_lists_tools_and_answers(tmp_path) -> None:
    """Start the real server over stdio with the installed SDK and talk to it as a client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(
        os.environ,
        AMR_DB_PATH=str(tmp_path / "amr.db"),
        AMR_SIGNING_KEY_PATH=str(tmp_path / "key.pem"),
        AMR_PUBLIC_KEY_PATH=str(tmp_path / "key.pub"),
    )
    params = StdioServerParameters(command=sys.executable, args=["-m", "amr.server"], env=env)

    async def session() -> tuple[str, set[str], str, bool]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            init = await client.initialize()
            info = getattr(init, "serverInfo", None) or init.server_info
            names = {t.name for t in (await client.list_tools()).tools}
            ok = await client.call_tool("verify_mandate", {"agent_id": "agent-x", "action": "read"})
            bad = await client.call_tool("verify_mandate", {"agent_id": "agent-x"})
            is_error = getattr(bad, "isError", getattr(bad, "is_error", None))
            return info.name, names, ok.content[0].text, is_error

    from amr.config import settings

    server_name, names, text, is_error = asyncio.run(asyncio.wait_for(session(), timeout=60))
    assert server_name == settings.server_name
    assert names == REGISTERED_TOOLS
    assert '"authorized": false' in text
    assert "No active mandate found for agent 'agent-x'" in text
    assert is_error is True


# --- documentation and CI ----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DOCS))
def test_docs_no_longer_ask_for_a_version_pin(name: str) -> None:
    assert "mcp<2" not in DOCS[name]
    assert "mcp.server.fastmcp" not in DOCS[name]


@pytest.mark.parametrize("name", sorted(DOCS))
def test_docs_say_both_sdk_versions_work(name: str) -> None:
    assert "version 1 and version 2 of the MCP Python SDK" in DOCS[name]


V2_RUN = (
    "uv run --isolated --no-project --with . --with pytest --with pytest-asyncio"
    ' --with "mcp[cli]>=2,<3" python -m pytest -q'
)


def test_release_runs_the_suite_against_mcp_v2_before_building() -> None:
    publish = ROOT / ".github" / "workflows" / "publish.yml"
    if not publish.is_file():
        pytest.skip("CI files are only in the repository")
    workflow = publish.read_text(encoding="utf-8")
    assert V2_RUN in workflow
    assert workflow.index(V2_RUN) < workflow.index("run: uv build")


def test_ci_runs_the_suite_against_mcp_v2() -> None:
    if not CI.is_file():
        pytest.skip("CI files are only in the repository")
    ci = CI.read_text(encoding="utf-8")
    assert V2_RUN in ci
    assert 'EXPECTED_MCP_MAJOR: "2"' in ci
    assert 'EXPECTED_MCP_MAJOR: "1"' in ci
