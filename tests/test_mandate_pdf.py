"""Tests for prepare_mandate_pdf: the mandate as a PDF the principal signs itself."""

import base64
import hashlib
import json
import re
import shutil
import subprocess  # noqa: S404 - only to run poppler on a file the test wrote
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.crypto.principal import PrincipalSignatureError, b64url_encode, key_registration_payload
from amr.mandate_pdf import ATTACHMENT_NAME, build_mandate_pdf
from amr.server import mcp
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.prepare_mandate_pdf import prepare_mandate_pdf
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key

ROOT = Path(__file__).resolve().parent.parent
SIGNED_AT = "2026-11-06T21:00:00+00:00"
BASE = {
    "principal_id": "org:clinic",
    "agent_id": "agent:scheduler",
    "scope": "Book and cancel patient appointments (no clinical data) \\ backslash",
    "legal_basis_regulation": "Delegation of authority",
    "legal_basis_article": "Section 2",
    "duration_hours": 24.0,
    "allowed_actions": ["calendar.book", "calendar.cancel"],
    "signed_at": SIGNED_AT,
}


# --- a minimal reader of the PDFs this module writes ---------------------------------------


def _xref(pdf: bytes) -> dict[int, int]:
    start = int(re.search(rb"startxref\n(\d+)\n%%EOF\n$", pdf).group(1))
    assert pdf[start : start + 5] == b"xref\n"
    header = re.match(rb"xref\n0 (\d+)\n", pdf[start:])
    count = int(header.group(1))
    entries = pdf[start + header.end() : start + header.end() + 20 * count]
    offsets = {}
    for number in range(count):
        entry = entries[20 * number : 20 * number + 20]
        assert len(entry) == 20 and entry.endswith(b" \n"), entry
        if number == 0:
            assert entry == b"0000000000 65535 f \n"
            continue
        assert entry[10:18] == b" 00000 n", entry
        offsets[number] = int(entry[:10])
    return offsets


def _object(pdf: bytes, number: int) -> bytes:
    at = _xref(pdf)[number]
    head = b"%d 0 obj\n" % number
    assert pdf[at : at + len(head)] == head
    end = pdf.index(b"\nendobj\n", at)
    return pdf[at + len(head) : end]


def _stream(pdf: bytes, number: int) -> bytes:
    body = _object(pdf, number)
    length = int(re.search(rb"/Length (\d+) >>\nstream\n", body).group(1))
    start = body.index(b"stream\n") + len(b"stream\n")
    data = body[start : start + length]
    assert body[start + length :] == b"\nendstream"
    return data


def _attached(pdf: bytes) -> bytes:
    catalog = _object(pdf, 1)
    names = re.search(rb"/EmbeddedFiles << /Names \[\((.*?)\) (\d+) 0 R\]", catalog)
    assert names.group(1) == ATTACHMENT_NAME.encode()
    spec = _object(pdf, int(names.group(2)))
    stream_number = int(re.search(rb"/EF << /F (\d+) 0 R", spec).group(1))
    return _stream(pdf, stream_number)


def _page_contents(pdf: bytes) -> list[bytes]:
    tree = _object(pdf, 2)
    kids = [int(n) for n in re.findall(rb"(\d+) 0 R", tree)]
    assert int(re.search(rb"/Count (\d+)", tree).group(1)) == len(kids)
    contents = []
    for kid in kids:
        page = _object(pdf, kid)
        assert b"/Type /Page " in page
        contents.append(_stream(pdf, int(re.search(rb"/Contents (\d+) 0 R", page).group(1))))
    return contents


def _shown_text(content: bytes) -> list[str]:
    """Literal strings of a content stream, unescaped, in order."""
    out = []
    for raw in re.findall(rb"\(((?:\\.|[^\\()])*)\) Tj", content):
        out.append(re.sub(rb"\\(.)", rb"\1", raw).decode("cp1252"))
    return out


async def _pdf(**overrides) -> tuple[dict, bytes]:
    result = json.loads(await prepare_mandate_pdf(**{**BASE, **overrides}))
    assert "error" not in result, result
    return result, base64.b64decode(result["pdf_base64"], validate=True)


# --- the attached content is the signed payload ---------------------------------------------


async def test_attached_file_is_exactly_the_payload_to_sign() -> None:
    result, pdf = await _pdf()
    prepared = json.loads(await prepare_mandate_signature(**BASE))
    payload = prepared["payload"].encode("utf-8")
    assert _attached(pdf) == payload
    assert result["payload"] == prepared["payload"]
    assert result["payload_b64url"] == prepared["payload_b64url"]
    assert result["signed_at"] == SIGNED_AT
    assert result["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert result["attachment_name"] == "amr-mandate.json"
    assert result["filename"] == f"amr-mandate-{result['payload_sha256'][:12]}.pdf"
    assert b"/Params << /Size %d >>" % len(payload) in pdf


async def test_attached_file_keeps_every_character_the_page_cannot_show() -> None:
    scope = "Rendez-vous à l'hôpital, 漢字, emoji \U0001f600, tab\tend"
    result, pdf = await _pdf(scope=scope)
    attached = json.loads(_attached(pdf).decode("utf-8"))
    assert attached["scope"] == scope
    shown = "\n".join(t for c in _page_contents(pdf) for t in _shown_text(c))
    assert "Rendez-vous à l'hôpital, ??, emoji ?, tab?end" in shown


async def test_principal_can_sign_the_attached_file_and_create_the_mandate() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    public = b64url_encode(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
    )
    proof = b64url_encode(key.sign(key_registration_payload(BASE["principal_id"], public)))
    registered = json.loads(await register_principal_key(BASE["principal_id"], public, proof))
    assert registered["status"] == "registered"
    now = datetime.now(UTC).isoformat()
    _, pdf = await _pdf(signed_at=now)
    signature = b64url_encode(key.sign(_attached(pdf)))
    created = json.loads(
        await create_mandate(**{**BASE, "signed_at": now}, principal_signature=signature)
    )
    assert "error" not in created, created
    proof_pack = json.loads(await get_proof(created["mandate_id"]))
    assert proof_pack["chain_integrity"]["principal_signature_valid"] is True


# --- the printed fingerprint ------------------------------------------------------------


async def test_sha256_is_printed_in_the_body_and_on_every_page() -> None:
    result, pdf = await _pdf(metadata={f"note{i}": "Long note " * 60 for i in range(16)})
    pages = _page_contents(pdf)
    assert len(pages) >= 3
    digest = result["payload_sha256"]
    for index, content in enumerate(pages, start=1):
        footer = _shown_text(content)[-1]
        assert footer == f"amr-mandate.json SHA-256 {digest} - page {index}/{len(pages)}"
    body = [t for c in pages for t in _shown_text(c)[:-1]]
    assert body.count(digest) == 1
    assert "SHA-256 of amr-mandate.json" in body


async def test_page_text_shows_the_whole_scope_without_dropping_characters() -> None:
    scope = "x" * 250 + " (parenthesis) and \\ backslash " + "word " * 300
    _, pdf = await _pdf(scope=scope)
    pages = _page_contents(pdf)
    body = "".join(t.strip() for c in pages for t in _shown_text(c)[:-1])
    assert scope.replace(" ", "") in body.replace(" ", "")


async def test_summary_keeps_every_word_of_the_scope_in_order() -> None:
    scope = "  ".join(f"w{i}" for i in range(300)) + "\tend (x) \\ y"
    _, pdf = await _pdf(scope=scope)
    lines = [t for t in _shown_text(_page_contents(pdf)[0])]
    start = next(i for i, t in enumerate(lines) if t.startswith("Scope: "))
    row = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.startswith("    "):
            break
        row.append(line)
    shown = " ".join(" ".join(row).split())
    assert shown == "Scope: " + " ".join(scope.replace("\t", "?").split())


LABELS = (
    "Principal:", "Agent:", "Scope:", "Legal basis:", "Duration:", "Parent mandate:",
    "Signed at (in the content):", "Allowed actions:", "Forbidden actions:",
    "Ceiling per action:", "Ceiling per period:", "Delegation allowed:", "Risk classes:",
    "Perimeter:",
)


@pytest.mark.parametrize("pad", [0, 1, 7, 33, 90])
async def test_scope_text_cannot_add_a_summary_row(pad: int) -> None:
    fake = "Legal basis: none, read-only (EU)"
    scope = "Read the calendar only." + " " * pad + (" " * 90).join(
        [fake, "Duration: 1 hours", "Delegation allowed: no", "Ceiling per action: 1 EUR"]
    )
    _, pdf = await _pdf(scope=scope, max_amount="5000", amount_actions=["calendar.book"])
    lines = _shown_text(_page_contents(pdf)[0])
    head = lines[: lines.index("Exact content of the mandate")]
    starts = [t.split(":")[0] + ":" for t in head if t and not t.startswith(" ")]
    assert [s for s in starts if s in LABELS] == [s for s in LABELS if s in starts]
    for label in LABELS:
        assert sum(1 for t in head if t.startswith(label)) <= 1, label
    assert "Ceiling per action: 5000 EUR (actions: calendar.book)" in head


async def test_summary_shows_the_perimeter_limits() -> None:
    _, pdf = await _pdf(
        forbidden_actions=["calendar.delete"],
        delegation_allowed=True,
        max_delegation_depth=2,
        max_amount="150",
        amount_actions=["calendar.book"],
        period_max_amount="900",
        period_days=30,
    )
    shown = _shown_text(_page_contents(pdf)[0])
    assert "Allowed actions: calendar.book, calendar.cancel" in shown
    assert "Forbidden actions: calendar.delete" in shown
    assert "Ceiling per action: 150 EUR (actions: calendar.book)" in shown
    assert "Ceiling per period: 900 EUR over 30 days" in shown
    assert "Delegation allowed: yes, at most 2 level(s) below" in shown


async def test_summary_says_when_there_is_no_perimeter() -> None:
    args = {k: v for k, v in BASE.items() if k != "allowed_actions"}
    result = json.loads(await prepare_mandate_pdf(**args))
    pdf = base64.b64decode(result["pdf_base64"])
    shown = _shown_text(_page_contents(pdf)[0])
    assert "Perimeter: none (free-text scope only)" in shown
    assert "Delegation allowed: no" not in shown


async def test_summary_collapses_runs_of_whitespace() -> None:
    _, pdf = await _pdf(scope="Read     the\n\ncalendar   only")
    assert "Scope: Read the??calendar only" in _shown_text(_page_contents(pdf)[0])


async def test_file_identifier_comes_from_the_payload_fingerprint() -> None:
    result, pdf = await _pdf()
    file_id = result["payload_sha256"][:32]
    assert f"/ID [<{file_id}> <{file_id}>]".encode() in pdf


async def test_too_large_content_is_refused_before_layout() -> None:
    result = json.loads(await prepare_mandate_pdf(**BASE, metadata={"big": "a" * 300_000}))
    assert result["code"] == "mandate_pdf_too_large"


async def test_summary_names_principal_agent_and_legal_basis() -> None:
    _, pdf = await _pdf()
    shown = [t for c in _page_contents(pdf) for t in _shown_text(c)]
    assert "Principal: org:clinic" in shown
    assert "Agent: agent:scheduler" in shown
    assert "Legal basis: Delegation of authority, Section 2 (EU)" in shown
    assert "Parent mandate: none (root mandate)" in shown
    assert f"Signed at (in the content): {SIGNED_AT}" in shown


async def test_lines_fit_the_page_width() -> None:
    _, pdf = await _pdf(scope="y" * 1000, metadata={"k": "v" * 400, "w": "word " * 300})
    for content in _page_contents(pdf):
        for text in _shown_text(content)[:-1]:
            assert len(text) <= 90, text


# --- determinism and structure ------------------------------------------------------------


async def test_same_arguments_give_the_same_pdf_and_others_do_not() -> None:
    _, one = await _pdf()
    _, two = await _pdf()
    _, other = await _pdf(scope="Another scope")
    assert one == two
    assert one != other


async def test_xref_points_at_every_object() -> None:
    _, pdf = await _pdf(metadata={"long": "z " * 3000})
    offsets = _xref(pdf)
    assert pdf.startswith(b"%PDF-1.7\n")
    for number in offsets:
        _object(pdf, number)
    assert re.search(rb"/Size (\d+)", pdf[pdf.rindex(b"trailer") :]).group(1) == (
        b"%d" % (len(offsets) + 1)
    )


def test_build_rejects_a_payload_that_is_not_a_mandate() -> None:
    for payload in (b"not json", b"[1]", b'{"context":"amr.principal_key.v1"}', b"\xff"):
        with pytest.raises(PrincipalSignatureError) as excinfo:
            build_mandate_pdf(payload)
        assert excinfo.value.code == "mandate_payload_invalid"


# --- errors and side effects ------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"signed_at": "2026-11-06T21:00:00"},
        {"allowed_actions": []},
        {"duration_hours": -1.0},
        {"max_amount": "abc"},
    ],
)
async def test_errors_are_those_of_prepare_mandate_signature(overrides: dict) -> None:
    expected = json.loads(await prepare_mandate_signature(**{**BASE, **overrides}))
    assert "error" in expected
    got = json.loads(await prepare_mandate_pdf(**{**BASE, **overrides}))
    assert got == expected


async def test_default_signed_at_is_now_and_returned(temp_db: Path) -> None:
    args = {k: v for k, v in BASE.items() if k != "signed_at"}
    result = json.loads(await prepare_mandate_pdf(**args))
    assert result["signed_at"].endswith("+00:00")
    assert json.loads(result["payload"])["signed_at"] == result["signed_at"]


async def test_nothing_is_written(temp_db: Path) -> None:
    await _pdf()
    assert not temp_db.exists()


async def test_tool_is_registered() -> None:
    names = {tool.name for tool in await mcp.list_tools()}
    assert "prepare_mandate_pdf" in names


@pytest.mark.parametrize("name", ["README.md", "AGENTS.md", "docs/principal-signature-spec.md"])
def test_docs_describe_the_tool(name: str) -> None:
    assert "prepare_mandate_pdf" in (ROOT / name).read_text(encoding="utf-8")


# --- an independent reader (poppler), when installed --------------------------------------


def _poppler(tool: str, *args: str) -> str:
    path = shutil.which(tool)
    assert path is not None
    return subprocess.run(  # noqa: S603 - fixed poppler binary, arguments from the test
        [path, *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("pdfinfo", "pdfdetach", "pdftotext")),
    reason="poppler-utils not installed",
)
async def test_poppler_reads_the_pdf_and_extracts_the_same_file(tmp_path: Path) -> None:
    result, pdf = await _pdf(metadata={"long": "Poppler check " * 400})
    path = tmp_path / "mandate.pdf"
    path.write_bytes(pdf)
    out = tmp_path / "attached.json"
    assert "PDF version:     1.7" in _poppler("pdfinfo", str(path))
    assert "1: amr-mandate.json" in _poppler("pdfdetach", "-list", str(path))
    _poppler("pdfdetach", "-save", "1", "-o", str(out), str(path))
    assert hashlib.sha256(out.read_bytes()).hexdigest() == result["payload_sha256"]
    assert result["payload_sha256"] in _poppler("pdftotext", str(path), "-")
