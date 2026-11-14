"""Every tool carries MCP annotations that tell the truth about what it does.

MCP clients read readOnlyHint, destructiveHint, idempotentHint and openWorldHint
(specification 2025-06-18 onwards) to decide which calls need the user's approval. A
read-only tool that writes would be approved silently; a write tool with no annotation
looks like a read in some directories. The class of each tool is frozen here, checked in
the tools/list response a client receives, and read-only tools are run against a real
registry to prove they change nothing.
"""

import ast
import asyncio
import hashlib
import inspect
import json
import re
import sqlite3
import textwrap
from pathlib import Path

import pytest

from amr.server import TOOL_ANNOTATIONS, TOOLS, FastMCP, mcp, register_tools
from amr.tools.check_action_token import check_action_token
from amr.tools.contest_action import list_action_contests, prepare_contest_signature
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.issue_mandate_attestation import get_registry_public_key
from amr.tools.log_action import log_action
from amr.tools.prepare_mandate_pdf import prepare_mandate_pdf
from amr.tools.principal_keys import prepare_mandate_signature
from amr.tools.revoke_mandate import prepare_revocation_signature
from amr.tools.verify_mandate import verify_mandate
from amr.tools_list import tools_list

# (readOnlyHint, destructiveHint, idempotentHint, openWorldHint); None = not sent, the
# specification gives those two no meaning on a read-only tool.
READ = (True, None, None, False)
APPEND = (False, False, False, False)
EXPECTED: dict[str, tuple] = {
    "create_mandate": APPEND,
    "verify_mandate": READ,
    "log_action": APPEND,
    "get_proof": READ,
    "issue_action_token": APPEND,
    "check_action_token": READ,
    "register_principal_key": (False, False, False, True),
    "prepare_mandate_signature": READ,
    "prepare_mandate_pdf": READ,
    "attach_signed_mandate_pdf": APPEND,
    "issue_mandate_attestation": APPEND,
    "get_registry_public_key": (False, False, True, False),
    "export_insurer_dossier": READ,
    "revoke_mandate": (False, True, False, False),
    "prepare_revocation_signature": READ,
    "contest_action": APPEND,
    "prepare_contest_signature": READ,
    "list_action_contests": READ,
    "report_issue": (False, False, False, True),
}
WIRE_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

BASE = {
    "principal_id": "dr-example",
    "agent_id": "agent-example",
    "scope": "Order medical supplies for the practice",
    "legal_basis_regulation": "Delegation of authority",
    "legal_basis_article": "Section 2",
    "duration_hours": 24.0,
}


def _wire(annotations: dict | None) -> tuple:
    assert annotations is not None
    return tuple(annotations.get(key) for key in WIRE_KEYS)


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Registry key paths in the test directory, the key itself not created yet."""
    priv = tmp_path / "registry_key.pem"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", tmp_path / "registry_key.pub")
    return priv


def test_every_tool_has_exactly_one_annotation() -> None:
    assert set(TOOL_ANNOTATIONS) == {tool.__name__ for tool in TOOLS}
    assert set(EXPECTED) == {tool.__name__ for tool in TOOLS}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_tools_list_sends_the_frozen_class(name: str) -> None:
    listed = {tool["name"]: tool for tool in tools_list("full")["tools"]}
    assert _wire(listed[name].get("annotations")) == EXPECTED[name]


def test_the_running_server_registers_the_annotations() -> None:
    for tool in asyncio.run(mcp.list_tools()):
        sent = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert _wire(sent.get("annotations")) == EXPECTED[tool.name], tool.name


@pytest.mark.parametrize("profile", ["principal", "agent", "receiver"])
def test_profiles_keep_the_annotations(profile: str) -> None:
    server = FastMCP("probe")
    register_tools(server, profile)
    for tool in asyncio.run(server.list_tools()):
        sent = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert _wire(sent.get("annotations")) == EXPECTED[tool.name], (profile, tool.name)


def test_only_revocation_is_destructive_and_only_opt_in_network_is_open_world() -> None:
    destructive = {
        n for n, a in TOOL_ANNOTATIONS.items() if a.model_dump(by_alias=True)["destructiveHint"]
    }
    open_world = {
        n for n, a in TOOL_ANNOTATIONS.items() if a.model_dump(by_alias=True)["openWorldHint"]
    }
    assert destructive == {"revoke_mandate"}
    assert open_world == {"register_principal_key", "report_issue"}


# What writes the registry or the disk, or reaches the network, in a tool's own body.
WRITE_MARKERS = (
    "commit(",
    "INSERT INTO",
    "ensure_signing_key_exists(",
    "to_thread(fetch",
    "http.client",
    "urlopen",
)


def _code_without_docstring(tool) -> str:
    body = ast.parse(textwrap.dedent(inspect.getsource(tool))).body[0]
    if ast.get_docstring(body) is not None:
        body.body = body.body[1:]
    return ast.unparse(body)


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.__name__)
def test_a_tool_whose_code_writes_or_reaches_out_is_not_read_only(tool) -> None:
    source = _code_without_docstring(tool)
    if any(marker in source for marker in WRITE_MARKERS):
        assert EXPECTED[tool.__name__][0] is False, tool.__name__


def _snapshot(db_path: Path, key_path: Path) -> tuple:
    """Every row of every table, hashed, and whether the registry key exists."""
    digest = hashlib.sha256()
    conn = sqlite3.connect(str(db_path))
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    ]
    for table in tables:
        # Table names come from sqlite_master, not from input.
        rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()  # noqa: S608
        digest.update(f"{table}:{len(rows)}:{rows!r}".encode())
    conn.close()
    return digest.hexdigest(), len(tables), key_path.exists()


async def _registry_with_one_action() -> dict:
    mandate = json.loads(await create_mandate(**BASE, allowed_actions=["supplies.order"]))
    assert "mandate_id" in mandate, mandate
    logged = json.loads(
        await log_action(mandate["mandate_id"], BASE["agent_id"], "supplies.order", "{}")
    )
    return {"mandate": mandate, "action": logged}


async def test_read_only_tools_change_nothing(temp_db: Path, isolated_signing_keys: Path) -> None:
    state = await _registry_with_one_action()
    mandate_id = state["mandate"]["mandate_id"]
    action_id = str(state["action"].get("action_id", state["action"].get("id", "1")))
    before = _snapshot(temp_db, isolated_signing_keys)
    assert before[1] > 0 and before[2] is False

    calls = {
        "verify_mandate": verify_mandate(BASE["agent_id"], "supplies.order"),
        "get_proof": get_proof(mandate_id),
        "check_action_token": check_action_token("not-a-token", "receiver.example"),
        "prepare_mandate_signature": prepare_mandate_signature(**BASE),
        "prepare_mandate_pdf": prepare_mandate_pdf(**BASE),
        "export_insurer_dossier": export_insurer_dossier(mandate_id),
        "prepare_revocation_signature": prepare_revocation_signature(mandate_id, "test"),
        "prepare_contest_signature": prepare_contest_signature(mandate_id, action_id, "test", 7),
        "list_action_contests": list_action_contests(mandate_id=mandate_id),
    }
    assert set(calls) == {name for name, hints in EXPECTED.items() if hints == READ}
    for name, call in calls.items():
        await call
        assert _snapshot(temp_db, isolated_signing_keys) == before, name


async def test_read_only_tools_change_nothing_once_the_key_and_a_token_exist(
    temp_db: Path, isolated_signing_keys: Path
) -> None:
    """The same, on the paths that sign or verify: a real token, a signed dossier."""
    state = await _registry_with_one_action()
    mandate_id = state["mandate"]["mandate_id"]
    issued = json.loads(
        await issue_action_token(
            mandate_id,
            BASE["agent_id"],
            "order gloves",
            "supplier.example",
            action_type="supplies.order",
        )
    )
    assert "token" in issued, issued
    before = _snapshot(temp_db, isolated_signing_keys)
    assert before[2] is True

    checked = json.loads(await check_action_token(issued["token"], "supplier.example"))
    assert checked["valid"] is True, checked
    dossier = json.loads(await export_insurer_dossier(mandate_id))
    assert "error" not in dossier, dossier
    proof = json.loads(await get_proof(mandate_id))
    assert "error" not in proof, proof
    assert _snapshot(temp_db, isolated_signing_keys) == before


async def test_get_registry_public_key_creates_the_key_once(isolated_signing_keys: Path) -> None:
    assert not isolated_signing_keys.exists()
    first = await get_registry_public_key()
    assert isolated_signing_keys.exists()
    content = isolated_signing_keys.read_bytes()
    assert await get_registry_public_key() == first
    assert isolated_signing_keys.read_bytes() == content


async def test_append_tools_do_add_to_the_registry(
    temp_db: Path, isolated_signing_keys: Path
) -> None:
    await _registry_with_one_action()
    before = _snapshot(temp_db, isolated_signing_keys)
    await _registry_with_one_action()
    assert _snapshot(temp_db, isolated_signing_keys) != before


def _readme_classes() -> dict[str, set[str]]:
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    table = readme.split("| Class | Tools |", 1)[1].split("\n\n", 1)[0]
    names = {tool.__name__ for tool in TOOLS}
    classes = {}
    for line in table.splitlines()[2:]:
        label, tools = line.strip("|").split("|", 1)
        classes[label.split("(")[0].strip()] = set(re.findall(r"`(\w+)`", tools)) & names
    return classes


def test_readme_table_matches_the_annotations() -> None:
    classes = _readme_classes()
    by_hints: dict[tuple, set[str]] = {}
    for name, hints in EXPECTED.items():
        by_hints.setdefault(hints, set()).add(name)
    assert classes["read-only"] == by_hints[READ]
    assert classes["appends to the registry"] == by_hints[APPEND]
    assert classes["appends, may reach the network"] == by_hints[(False, False, False, True)]
    assert classes["destructive"] == by_hints[(False, True, False, False)]
    assert classes["idempotent write"] == by_hints[(False, False, True, False)]
    assert set().union(*classes.values()) == set(EXPECTED)
