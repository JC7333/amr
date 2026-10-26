"""The agent-facing documentation and the quickstart example match the real server."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = (ROOT / "src" / "amr" / "server.py").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
LLMS = (ROOT / "llms.txt").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")

REGISTERED_TOOLS = set(re.findall(r"^mcp\.tool\(\)\((\w+)\)", SERVER, flags=re.MULTILINE))
INSTALL = 'uvx --from git+https://github.com/JC7333/amr --with "mcp<2" amr'


def test_registered_tools_are_found() -> None:
    # Guards the regex above: an empty set would make the next two tests vacuous.
    assert {"create_mandate", "verify_mandate", "revoke_mandate"} <= REGISTERED_TOOLS


def test_agents_md_lists_every_tool_and_only_real_ones() -> None:
    listed = set(re.findall(r"^\| `(\w+)` \|", AGENTS, flags=re.MULTILINE))
    assert listed == REGISTERED_TOOLS


def test_readme_quickstart_names_only_real_tools() -> None:
    start = README.index("## Quickstart for agents")
    section = README[start : README.index("## Why AMR?")]
    numbered = re.findall(r"^\d\. `(\w+)", section, flags=re.MULTILINE)
    assert numbered
    assert set(numbered) <= REGISTERED_TOOLS


@pytest.mark.parametrize("text", [AGENTS, LLMS, README])
def test_install_command_pins_mcp_v1(text: str) -> None:
    assert INSTALL in text


def test_readme_says_amr_is_not_on_pypi() -> None:
    assert "`uvx amr` would install a different project" in README


def test_llms_txt_links_to_existing_files() -> None:
    paths = re.findall(r"github\.com/JC7333/amr/blob/main/([\w./-]+)\)", LLMS)
    assert paths
    for path in paths:
        assert (ROOT / path).is_file(), path


def test_documents_make_no_compliance_promise() -> None:
    for text in (AGENTS, LLMS):
        assert "does not make anyone compliant" in text


def test_quickstart_example_runs_end_to_end() -> None:
    result = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [sys.executable, str(ROOT / "examples" / "quickstart_agent.py")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: every step behaved as documented." in result.stdout
