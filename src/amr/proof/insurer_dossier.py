"""Insurer dossier: canonical form, registry signature, offline verification, print view.

The dossier is a JSON document built from the registry (see
amr.tools.export_insurer_dossier). It is signed as a JWS Compact Serialization
(RFC 7515) whose payload is the canonical JSON bytes of the dossier, with the
registry's Ed25519 key (EdDSA, hardcoded on both sides). The HTML view is a
rendering of the signed dossier for printing; only the JWS is signed.
"""

import hashlib
import html
import json
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

DOSSIER_VERSION = "1.0"
DOSSIER_TYPE = "amr-insurer-dossier+json"
_ALGORITHM = "EdDSA"


class DossierVerificationError(ValueError):
    """The signed dossier does not verify against the given registry key."""


def canonical_bytes(dossier: dict[str, Any]) -> bytes:
    """Canonical JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(dossier, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def dossier_digest(dossier: dict[str, Any]) -> str:
    """SHA-256 (hex) of the canonical dossier, printed on the paper view."""
    return hashlib.sha256(canonical_bytes(dossier)).hexdigest()


def sign_dossier(
    dossier: dict[str, Any], private_key: ed25519.Ed25519PrivateKey, key_id: str
) -> str:
    """Return the JWS (compact) of the canonical dossier, signed with EdDSA."""
    return jwt.api_jws.PyJWS().encode(
        canonical_bytes(dossier),
        private_key,
        algorithm=_ALGORITHM,
        headers={"kid": key_id, "typ": DOSSIER_TYPE},
    )


def verify_dossier(dossier_jws: str, public_key_pem: str) -> dict[str, Any]:
    """Verify a signed dossier offline and return it.

    The registry public key must be obtained out of band (not from the dossier
    itself): a dossier that carries its own key proves nothing about who signed it.
    Raises DossierVerificationError on any failure.
    """
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise DossierVerificationError(f"invalid public key: {exc}") from exc
    if not isinstance(public_key, ed25519.Ed25519PublicKey):
        raise DossierVerificationError("public key is not Ed25519")
    try:
        decoded = jwt.api_jws.PyJWS().decode_complete(
            dossier_jws, public_key, algorithms=[_ALGORITHM]
        )
    except jwt.exceptions.PyJWTError as exc:
        raise DossierVerificationError(f"signature invalid: {exc}") from exc
    if decoded["header"].get("typ") != DOSSIER_TYPE:
        raise DossierVerificationError("not an AMR insurer dossier")
    try:
        dossier = json.loads(decoded["payload"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DossierVerificationError("payload is not JSON") from exc
    if not isinstance(dossier, dict) or canonical_bytes(dossier) != decoded["payload"]:
        raise DossierVerificationError("payload is not a canonical dossier")
    return dossier


# --- Print view ---------------------------------------------------------------

_CSS = """
body{font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#111;
max-width:960px;margin:24px auto;padding:0 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px;
border-bottom:1px solid #999;padding-bottom:4px}
table{border-collapse:collapse;width:100%;margin:6px 0}
th,td{border:1px solid #bbb;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f0f0f0;width:30%}.mono{font-family:ui-monospace,monospace;
font-size:12px;word-break:break-all}.ok{color:#05602d}.bad{color:#a00000;font-weight:600}
.muted{color:#555}@media print{body{margin:0;max-width:none}h2{break-after:avoid}
tr{break-inside:avoid}}
"""


# Bidirectional controls can make printed text read in a misleading order.
_BIDI_CONTROLS = dict.fromkeys(
    [0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)], "\ufffd"
)


def _text(value: Any) -> str:
    return html.escape(str(value).translate(_BIDI_CONTROLS))


def _e(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list | tuple):
        return ", ".join(_text(item) for item in value) or "—"
    return _text(value)


def _check(value: bool | None, none_text: str) -> str:
    if value is None:
        return f'<span class="muted">{html.escape(none_text)}</span>'
    if value:
        return '<span class="ok">valid</span>'
    return '<span class="bad">INVALID</span>'


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(f"<tr><th>{html.escape(k)}</th><td>{v}</td></tr>" for k, v in pairs)


def _perimeter_rows(perimeter: dict[str, Any] | None) -> list[tuple[str, str]]:
    if perimeter is None:
        return [("Structured perimeter", "none (free-text scope only, not enforced)")]
    return [
        ("Allowed action types", _e(perimeter.get("allowed_actions"))),
        ("Forbidden action types", _e(perimeter.get("forbidden_actions"))),
        ("May delegate (sub-mandates)", _e(perimeter.get("delegation_allowed"))),
        (
            "Amount limit per action",
            (
                f"{_e(perimeter.get('max_amount'))} {_e(perimeter.get('currency'))}"
                if perimeter.get("max_amount") is not None
                else "none"
            ),
        ),
        ("Actions bound by the amount limit", _e(perimeter.get("amount_actions"))),
        (
            "Cumulative amount limit",
            (
                f"{_e(perimeter.get('period_max_amount'))} {_e(perimeter.get('currency'))} "
                f"per {_e(perimeter.get('period_days'))} days (rolling, whole branch)"
                if perimeter.get("period_max_amount") is not None
                else "none"
            ),
        ),
    ]


def _table(headers: list[str], body: list[list[str]], empty: str) -> str:
    if not body:
        return f'<p class="muted">{html.escape(empty)}</p>'
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in body)
    return f"<table><tr>{head}</tr>{rows}</table>"


def render_html(dossier: dict[str, Any], digest: str, key_id: str) -> str:
    """Printable, self-contained HTML view of a dossier (no external resources)."""
    m = dossier["mandate"]
    period = dossier["period"]
    status = dossier["status"]
    integrity = dossier["integrity"]
    legal = m.get("legal_basis") or {}

    mandate_rows = [
        ("Mandate id", f'<span class="mono">{_e(m["id"])}</span>'),
        ("Principal (grants the mandate)", _e(m["principal_id"])),
        ("Agent (acts under it)", _e(m["agent_id"])),
        ("Scope (as written)", _e(m["scope"])),
        (
            "Legal basis (as declared by the principal)",
            _e(" · ".join(str(v) for v in legal.values()) if legal else None),
        ),
        ("Created", _e(m["created_at"])),
        ("Expires", _e(m["expires_at"])),
        ("Parent mandate", _e(m["parent_mandate_id"])),
    ]
    status_rows = [
        ("Stored status", _e(status["stored_status"])),
        ("In force at generation time", _e(status["in_force"])),
        ("Reason if not in force", _e(status["not_in_force_reason"])),
    ]
    integrity_rows = [
        ("Action log chain (whole mandate)", _check(integrity["actions_chain_valid"], "")),
        (
            "Principal signature",
            _check(integrity["principal_signature_valid"], "not signed by the principal"),
        ),
        ("Principal key id", _e(integrity["principal_key_id"])),
        ("Last action chain hash", f'<span class="mono">{_e(integrity["chain_head"])}</span>'),
        ("Actions recorded (whole mandate)", _e(integrity["total_actions"])),
    ]
    sub_rows = [
        [
            f'<span class="mono">{_e(s["id"])}</span>',
            _e(s["depth"]),
            _e(s["agent_id"]),
            _e((s["perimeter"] or {}).get("allowed_actions")),
            _e(s["status"]["in_force"]),
            _e(s["status"]["not_in_force_reason"]),
            _check(s["integrity"]["actions_chain_valid"], ""),
            _e(s["actions_in_period"]),
        ]
        for s in dossier["sub_mandates"]
    ]
    event_rows = [
        [_e(ev["timestamp"]), _e(ev["mandate_id"]), _e(ev["event_type"]), _e(ev["reason"])]
        for ev in dossier["events"]
    ]
    action_rows = [
        [
            _e(a["timestamp"]),
            _e(a["agent_id"]),
            _e(a["action"]),
            _e(a["result"]),
            f'<span class="mono">{_e(a["chain_hash"][:16])}…</span>',
        ]
        for a in dossier["actions"]
    ]
    token_rows = [
        [
            _e(t["issued_at"]),
            _e(t["audience"]),
            f'<span class="mono">{_e(t["action_hash"][:16])}…</span>',
            _e(t["expires_at"]),
        ]
        for t in dossier["tokens"]
    ]
    limits = "".join(f"<li>{html.escape(item)}</li>" for item in dossier["limits"])
    truncated = (
        '<p class="bad">Sub-mandate list truncated: the events and tokens of the '
        "omitted sub-mandates are not included either.</p>"
        if dossier.get("sub_mandates_truncated")
        else ""
    )

    subs_table = _table(
        ["Id", "Depth", "Agent", "Allowed", "In force", "Reason", "Chain", "Actions in period"],
        sub_rows,
        "No sub-mandate.",
    )
    events_table = _table(
        ["When", "Mandate", "Event", "Reason"], event_rows, "No status event in the period."
    )
    actions_table = _table(
        ["When", "Agent", "Action", "Result", "Chain hash"],
        action_rows,
        "No action logged in the period.",
    )
    tokens_table = _table(
        ["Issued", "Audience", "Action hash", "Expires"],
        token_rows,
        "No token issued in the period.",
    )
    verification_rows = _rows(
        [
            ("SHA-256 of the canonical dossier", f'<span class="mono">{_e(digest)}</span>'),
            ("Registry signing key id", f'<span class="mono">{_e(key_id)}</span>'),
            ("Signature", "JWS (RFC 7515), EdDSA / Ed25519, over the canonical dossier JSON"),
        ]
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AMR insurer dossier {_e(m["id"])}</title><style>{_CSS}</style></head>
<body>
<h1>Insurer dossier: mandate of an AI agent</h1>
<p class="muted">Agent Mandate Registry · dossier version {_e(dossier["dossier_version"])} ·
generated {_e(dossier["generated_at"])} · period {_e(period["start"])} to {_e(period["end"])}</p>
<h2>1. The mandate</h2><table>{_rows(mandate_rows)}</table>
<h2>2. Perimeter (enforced when a token is requested)</h2>
<table>{_rows(_perimeter_rows(m["perimeter"]))}</table>
<h2>3. Status and stop</h2><table>{_rows(status_rows)}</table>
<h2>4. Integrity</h2><table>{_rows(integrity_rows)}</table>
<h2>5. Sub-mandates ({len(dossier["sub_mandates"])})</h2>{truncated}
{subs_table}
<h2>6. Status events in the period ({len(dossier["events"])})</h2>
{events_table}
<h2>7. Actions logged in the period ({len(dossier["actions"])})</h2>
{actions_table}
<h2>8. Action tokens issued in the period ({len(dossier["tokens"])})</h2>
{tokens_table}
<h2>9. Limits of this dossier</h2><ul>{limits}</ul>
<h2>10. Verification</h2><table>{verification_rows}</table>
<p class="muted">This page renders the signed JSON dossier. Only the JSON signature is
proof: verify it with the registry public key obtained out of band.</p>
</body></html>
"""
