"""The mandate as a PDF the principal signs with its own signature tool.

The PDF shows the mandate in readable form and carries the exact bytes of the mandate
(the canonical JSON returned by prepare_mandate_signature) as an attached file named
``amr-mandate.json``. Its SHA-256 is printed in clear on every page, so a reader can
compare the printed value with the attached file without trusting the rendering.

The PDF is built with the standard library only and is deterministic: the same
payload always gives the same bytes. The registry never signs it; the principal signs
it (for example a PAdES signature made with the tool it uses for its contracts).
Checking such a signature is not done here.
"""

import hashlib
import json
import textwrap
from typing import Any

from amr.crypto.principal import MANDATE_CONTEXT, PrincipalSignatureError

ATTACHMENT_NAME = "amr-mandate.json"

_PAGE_WIDTH = 595  # A4, points
_PAGE_HEIGHT = 842
_MARGIN = 50
_BODY_SIZE = 9  # Courier: every glyph is 0.6 em wide
_LINE_HEIGHT = 11
_HEADING_SIZE = 12
_HEADING_HEIGHT = 18
_CHARS_PER_LINE = 90  # 90 * 0.6 * 9 pt = 486 pt, inside the 495 pt between margins
_FOOTER_Y = 30
_MAX_PAGES = 200


def _display(text: str) -> str:
    """Text as the PDF shows it: Windows-1252 glyphs only, control characters as '?'."""
    shown = []
    for char in text:
        if char < " " or char == "\x7f":
            shown.append("?")
            continue
        try:
            char.encode("cp1252")
        except UnicodeEncodeError:
            shown.append("?")
        else:
            shown.append(char)
    return "".join(shown)


def _literal(text: str) -> bytes:
    """A PDF literal string, encoded in Windows-1252 (WinAnsiEncoding)."""
    raw = _display(text).encode("cp1252")
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + raw + b")"


def _wrap(line: str) -> list[str]:
    """Wrap one line to the page width, keeping its indentation; never drops a character."""
    shown = _display(line)
    indent = len(shown) - len(shown.lstrip(" "))
    indent = min(indent, _CHARS_PER_LINE // 2)
    body = shown[indent:]
    if not body:
        return [""]
    width = _CHARS_PER_LINE - indent
    pieces = [body[i : i + width] for i in range(0, len(body), width)]
    return [" " * indent + piece for piece in pieces]


def _wrap_words(text: str) -> list[str]:
    """Wrap prose on word boundaries; long words are cut, nothing is dropped."""
    shown = _display(text)
    lines = textwrap.wrap(
        shown,
        width=_CHARS_PER_LINE,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    )
    return lines or [""]


def _parse_payload(payload: bytes) -> dict[str, Any]:
    try:
        content = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PrincipalSignatureError("mandate_payload_invalid", "payload is not JSON") from exc
    if not isinstance(content, dict) or content.get("context") != MANDATE_CONTEXT:
        raise PrincipalSignatureError(
            "mandate_payload_invalid", f"payload is not an {MANDATE_CONTEXT} mandate"
        )
    return content


def _summary(content: dict[str, Any]) -> list[tuple[str, str]]:
    basis = content.get("legal_basis") or {}
    basis_text = ", ".join(
        str(basis.get(key)) for key in ("regulation", "article") if basis.get(key)
    )
    if basis.get("jurisdiction"):
        basis_text += f" ({basis['jurisdiction']})"
    rows = [
        ("Principal", str(content.get("principal_id"))),
        ("Agent", str(content.get("agent_id"))),
        ("Scope", str(content.get("scope"))),
        ("Legal basis", basis_text),
        ("Duration", f"{content.get('duration_hours')} hours from creation in the registry"),
        ("Parent mandate", str(content.get("parent_mandate_id") or "none (root mandate)")),
        ("Signed at (in the content)", str(content.get("signed_at"))),
    ]
    return rows


def _lines(payload: bytes, content: dict[str, Any], digest: str) -> list[tuple[str, str]]:
    """(style, text) lines of the document; style is "h" (heading) or "b" (body)."""
    out: list[tuple[str, str]] = [("h", "Mandate for an AI agent, to be signed by the principal")]
    out.append(("b", ""))
    for label, value in _summary(content):
        out.extend(("b", line) for line in _wrap_words(f"{label}: {value}"))
    out.append(("b", ""))
    out.append(("h", "Exact content of the mandate"))
    out.extend(
        ("b", line)
        for line in _wrap_words(
            f"This is the attached file {ATTACHMENT_NAME} (canonical JSON, UTF-8), shown "
            "indented. The attached file is authoritative: characters that this page "
            "cannot show are printed as '?'."
        )
    )
    out.append(("b", ""))
    pretty = json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False)
    for raw_line in pretty.splitlines():
        out.extend(("b", line) for line in _wrap(raw_line))
    out.append(("b", ""))
    out.append(("h", f"SHA-256 of {ATTACHMENT_NAME}"))
    out.append(("b", digest))
    out.append(("b", f"Size: {len(payload)} bytes"))
    out.append(("b", ""))
    out.extend(
        ("b", line)
        for line in _wrap_words(
            "Signing this PDF with your own signature tool signs the attached content. "
            "This document does not create the mandate: the registry creates it with "
            "create_mandate, from arguments that give exactly this content."
        )
    )
    return out


def _paginate(lines: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    pages: list[list[tuple[str, str]]] = [[]]
    used = 0
    room = _PAGE_HEIGHT - 2 * _MARGIN
    for style, text in lines:
        height = _HEADING_HEIGHT if style == "h" else _LINE_HEIGHT
        if used + height > room and pages[-1]:
            pages.append([])
            used = 0
        pages[-1].append((style, text))
        used += height
    if len(pages) > _MAX_PAGES:
        raise PrincipalSignatureError(
            "mandate_payload_invalid", f"the mandate needs more than {_MAX_PAGES} pages"
        )
    return pages


def _page_stream(page: list[tuple[str, str]], footer: str) -> bytes:
    parts: list[bytes] = []
    y = _PAGE_HEIGHT - _MARGIN
    for style, text in page:
        if style == "h":
            y -= _HEADING_HEIGHT
            font, size = b"/F2", _HEADING_SIZE
        else:
            y -= _LINE_HEIGHT
            font, size = b"/F1", _BODY_SIZE
        if text:
            parts.append(
                b"BT "
                + font
                + b" %d Tf 1 0 0 1 %d %d Tm " % (size, _MARGIN, y)
                + _literal(text)
                + b" Tj ET"
            )
    parts.append(
        b"BT /F1 7 Tf 1 0 0 1 %d %d Tm " % (_MARGIN, _FOOTER_Y) + _literal(footer) + b" Tj ET"
    )
    return b"\n".join(parts) + b"\n"


def _stream_object(dictionary: bytes, data: bytes) -> bytes:
    return (
        b"<< "
        + dictionary
        + b" /Length %d >>\nstream\n" % len(data)
        + data
        + b"\nendstream"
    )


def build_mandate_pdf(payload: bytes) -> bytes:
    """Return the PDF of a mandate payload (bytes from prepare_mandate_signature).

    Raises PrincipalSignatureError("mandate_payload_invalid") if the payload is not an
    amr.mandate.v1 canonical JSON document.
    """
    content = _parse_payload(payload)
    digest = hashlib.sha256(payload).hexdigest()
    pages = _paginate(_lines(payload, content, digest))

    # Fixed numbering: 1 catalog, 2 page tree, 3-4 fonts, 5 file specification,
    # 6 attached file, 7 document information, then one page and one content per page.
    first_page = 8
    page_ids = [first_page + 2 * i for i in range(len(pages))]
    objects: dict[int, bytes] = {}
    name = _literal(ATTACHMENT_NAME)
    objects[1] = (
        b"<< /Type /Catalog /Pages 2 0 R /Lang (en)"
        b" /Names << /EmbeddedFiles << /Names [" + name + b" 5 0 R] >> >>"
        b" /AF [5 0 R] /PageMode /UseAttachments >>"
    )
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objects[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(pages)
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    objects[4] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold"
        b" /Encoding /WinAnsiEncoding >>"
    )
    objects[5] = (
        b"<< /Type /Filespec /F " + name + b" /UF " + name
        + b" /Desc (Exact content of the mandate, canonical JSON) /AFRelationship /Source"
        b" /EF << /F 6 0 R /UF 6 0 R >> >>"
    )
    objects[6] = _stream_object(
        b"/Type /EmbeddedFile /Subtype /application#2Fjson /Params << /Size %d >>"
        % len(payload),
        payload,
    )
    objects[7] = b"<< /Title (AMR mandate to be signed by the principal) /Creator (AMR) >>"
    for index, (page, pid) in enumerate(zip(pages, page_ids, strict=True), start=1):
        footer = f"{ATTACHMENT_NAME} SHA-256 {digest} - page {index}/{len(pages)}"
        objects[pid] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d]" % (_PAGE_WIDTH, _PAGE_HEIGHT)
            + b" /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >>"
            + b" /Contents %d 0 R >>" % (pid + 1)
        )
        objects[pid + 1] = _stream_object(b"", _page_stream(page, footer))

    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    size = max(objects) + 1
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets[number]
    file_id = digest[:32].encode("ascii")
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R /ID [<" % size
        + file_id
        + b"> <"
        + file_id
        + b">] >>\nstartxref\n%d\n%%%%EOF\n" % xref_at
    )
    return bytes(out)
