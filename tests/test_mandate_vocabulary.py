"""The repository speaks of the person who authorizes, not of a mandate given to the agent.

A mandate here is the written authorization a person or a body gives for its agent. It binds
the one who gives it, not the agent, which is not a person. The shipped texts therefore never
call it a "legal mandate" and never give a civil-code article on agency as an example legal
basis: the example is the act that gives the signer the power to authorize (delegation of
authority, body decision, contract clause).

The ``legal_basis`` field keeps its name and its free-text format: a mandate recorded with any
legal basis, an old example included, is created and hashed exactly as before.
"""

import json
import re
from pathlib import Path

import aiosqlite

from amr.crypto.chain import compute_hash
from amr.server import mcp
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof

ROOT = Path(__file__).resolve().parent.parent

# Texts shipped with the code. CLAUDE.md and pyproject.toml are protected files, changed on
# their own reviewed branch; they are not checked here.
SHIPPED = sorted(
    [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "llms.txt", ROOT / "server.json"]
    + list((ROOT / "docs").rglob("*.md"))
    + list((ROOT / "src").rglob("*.py"))
)
LEGAL_MANDATE = re.compile(r"legal\s+mandates?", re.IGNORECASE)
CIVIL_CODE_AGENCY = re.compile(r"\b1984\b")
DEFINITION = "the written authorization a person or a body gives for its agent"
TAGLINE = "Records who authorized an AI agent to do what, until when"


def _text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_shipped_texts_exist() -> None:
    assert len(SHIPPED) > 10
    for path in SHIPPED:
        assert path.is_file(), path


def test_no_shipped_text_says_legal_mandate() -> None:
    found = [str(p.relative_to(ROOT)) for p in SHIPPED if LEGAL_MANDATE.search(_text(p))]
    assert found == []


def test_no_shipped_text_cites_article_1984() -> None:
    found = [str(p.relative_to(ROOT)) for p in SHIPPED if CIVIL_CODE_AGENCY.search(_text(p))]
    assert found == []


def test_tests_do_not_use_article_1984_as_example() -> None:
    here = Path(__file__).name
    found = [
        p.name for p in (ROOT / "tests").glob("*.py")
        if p.name != here and CIVIL_CODE_AGENCY.search(p.read_text(encoding="utf-8"))
    ]
    assert found == []


def test_readme_tagline_is_the_registry_description() -> None:
    readme = _text(ROOT / "README.md")
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["description"].startswith(TAGLINE)
    assert f"> **{TAGLINE}.**" in readme


def test_readme_defines_the_word_mandate_once() -> None:
    readme = _text(ROOT / "README.md")
    assert readme.count(DEFINITION) == 1
    assert "it binds the one who gives it, not the agent, which is not a person" in readme


async def test_create_mandate_tool_description_uses_the_definition() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    description = " ".join((tools["create_mandate"].description or "").split())
    assert not LEGAL_MANDATE.search(description)
    assert "the written authorization a principal (a person or a body) gives" in description
    assert "delegation of authority" in description


async def test_any_legal_basis_text_is_still_accepted_and_hashed_as_before(temp_db: Path) -> None:
    result = json.loads(await create_mandate(
        principal_id="org:clinic", agent_id="agent:billing", scope="Handle supplier invoices",
        legal_basis_regulation="Mandat de gestion", legal_basis_article="Art. 1984 Code civil",
        duration_hours=24,
    ))
    assert result["status"] == "created"
    async with aiosqlite.connect(str(temp_db)) as db:
        db.row_factory = aiosqlite.Row
        row = await (
            await db.execute("SELECT * FROM mandates WHERE id = ?", (result["mandate_id"],))
        ).fetchone()
    legal = json.loads(row["legal_basis_json"])
    assert legal == {
        "regulation": "Mandat de gestion", "article": "Art. 1984 Code civil", "jurisdiction": "EU",
    }
    data = {
        "id": row["id"],
        "principal_id": "org:clinic",
        "agent_id": "agent:billing",
        "scope": "Handle supplier invoices",
        "legal_basis_regulation": "Mandat de gestion",
        "legal_basis_article": "Art. 1984 Code civil",
        "legal_basis_jurisdiction": "EU",
        "duration_hours": 24,
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "parent_mandate_id": None,
    }
    assert compute_hash(data, "") == row["chain_hash"] == result["chain_hash"]
    proof = json.loads(await get_proof(result["mandate_id"]))
    assert proof["mandate"]["legal_basis"]["article"] == "Art. 1984 Code civil"


def test_pinned_mandate_hash_is_unchanged() -> None:
    # A mandate written before this change, with the old example legal basis: same hash.
    data = {
        "id": "00000000-0000-4000-8000-000000000001",
        "principal_id": "org:clinic",
        "agent_id": "agent:billing",
        "scope": "Handle supplier invoices",
        "legal_basis_regulation": "Mandat de gestion",
        "legal_basis_article": "Art. 1984 Code civil",
        "legal_basis_jurisdiction": "EU",
        "duration_hours": 24,
        "created_at": "2026-11-01T00:00:00+00:00",
        "expires_at": "2026-11-02T00:00:00+00:00",
        "parent_mandate_id": None,
    }
    assert compute_hash(data, "") == PINNED


PINNED = "7407dbf865035bbbc46544369a9f77a35491219a8c2f6a747fa034670c2d1656"
