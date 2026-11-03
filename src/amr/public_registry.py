"""Public registry: a read-only verification point anyone can query without an account.

Two halves, kept apart on purpose:

* ``export`` runs next to the registry. It reads the SQLite database read-only and
  writes a **signed snapshot** (compact JWS, EdDSA, registry key): for each mandate,
  only what a third party needs to decide whether to trust an agent (agent, principal
  reference, perimeter, dates, recorded status, revocation date, hashes). No scope
  text, no legal basis, no metadata, no revocation reason, and the principal identifier
  is replaced by its SHA-256 (``principal_ref``).
* ``make_app`` is a WSGI application (standard library only) that serves that
  snapshot. It never sees the database, writes nothing, keeps no log and never reads
  the client's address. It answers in JSON for machines and in HTML for people, and
  states how long each verification took.

The snapshot is verified when the application starts: a snapshot that is not signed
by the pinned registry key is refused, so a hosting provider cannot alter it.
A snapshot is a photograph: a revocation made after ``generated_at`` is not shown
until the next export. Every answer says when the snapshot was taken.

See docs/public-registry-spec.md.
"""

import argparse
import asyncio
import hashlib
import html
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs
from uuid import UUID

import aiosqlite
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, Field, ValidationError

from amr.attestation import registry_key_id, verify_attestation
from amr.config import settings
from amr.crypto.signing import ensure_signing_key_exists, load_signing_key
from amr.delegation import MAX_DELEGATION_DEPTH
from amr.models.perimeter import Perimeter

EXPORT_TYP = "amr-public-registry+jwt"
EXPORT_FORMAT = "amr-public-registry.v1"
# EdDSA is the only algorithm accepted, when signing and when loading a snapshot.
ALGORITHM = "EdDSA"
# Longest query string accepted (an attestation is a few kilobytes).
MAX_QUERY_LENGTH = 16_384

_UUID_PATH = re.compile(r"^/mandates/([^/]+)$")


class PublicRegistryError(Exception):
    """A snapshot or a key could not be used. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class PublicMandate(BaseModel):
    """One mandate as published: only fields a third party needs, no free text."""

    model_config = {"extra": "forbid", "frozen": True}

    id: str
    agent_id: str
    principal_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    principal_signed: bool
    principal_key_id: str | None
    perimeter: dict[str, Any] | None
    perimeter_digest: str | None
    created_at: str
    expires_at: str
    parent_mandate_id: str | None
    recorded_status: str
    revoked_at: str | None
    chain_hash: str


class PublicSnapshot(BaseModel):
    """The signed content of an export."""

    model_config = {"extra": "forbid", "frozen": True}

    format: Literal["amr-public-registry.v1"]
    issuer: str
    key_id: str
    generated_at: str
    mandates: list[PublicMandate]


# ---------------------------------------------------------------------------
# Export (registry side)
# ---------------------------------------------------------------------------


def principal_ref(principal_id: str) -> str:
    """Published reference of a principal: SHA-256 of its identifier.

    Whoever knows the identifier can recompute it and compare; whoever does not, does
    not read it. It is a pseudonym, not an anonymisation: a short or guessable
    identifier can be found by trying candidates.
    """
    return "sha256:" + hashlib.sha256(principal_id.encode("utf-8")).hexdigest()


def _perimeter_digest(perimeter: dict[str, Any] | None) -> str | None:
    if perimeter is None:
        return None
    return Perimeter.model_validate(perimeter).digest()


async def _read_mandates(db_path: Path) -> list[PublicMandate]:
    path = db_path.resolve()
    if not path.is_file():
        raise PublicRegistryError("database_not_found", str(db_path))
    db = await aiosqlite.connect(f"{path.as_uri()}?mode=ro", uri=True)
    db.row_factory = aiosqlite.Row
    try:
        cursor = await db.execute(
            """
            SELECT m.id, m.principal_id, m.agent_id, m.status, m.created_at,
                   m.expires_at, m.parent_mandate_id, m.chain_hash, m.perimeter_json,
                   m.principal_signature, m.principal_key_id, r.revoked_at
            FROM mandates AS m
            LEFT JOIN mandate_revocations AS r ON r.mandate_id = m.id
            ORDER BY m.created_at, m.id
            """
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()
    mandates = []
    for row in rows:
        perimeter = json.loads(row["perimeter_json"]) if row["perimeter_json"] else None
        signed = row["principal_signature"] is not None
        mandates.append(
            PublicMandate(
                id=row["id"],
                agent_id=row["agent_id"],
                principal_ref=principal_ref(row["principal_id"]),
                principal_signed=signed,
                principal_key_id=row["principal_key_id"] if signed else None,
                perimeter=perimeter,
                perimeter_digest=_perimeter_digest(perimeter),
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                parent_mandate_id=row["parent_mandate_id"],
                recorded_status=row["status"],
                revoked_at=row["revoked_at"],
                chain_hash=row["chain_hash"],
            )
        )
    return mandates


async def build_export(
    db_path: Path | None = None,
    private_key: ed25519.Ed25519PrivateKey | None = None,
    issuer: str | None = None,
    now: datetime | None = None,
) -> str:
    """Read the registry read-only and return the signed snapshot (compact JWS).

    Defaults: the configured database, registry key and issuer.
    """
    if private_key is None:
        ensure_signing_key_exists()
        private_key = load_signing_key()
    key_id = registry_key_id(private_key.public_key())
    moment = now or datetime.now(UTC)
    snapshot = PublicSnapshot(
        format=EXPORT_FORMAT,
        issuer=issuer or settings.token_issuer,
        key_id=key_id,
        generated_at=moment.isoformat(),
        mandates=await _read_mandates(db_path or settings.db_path),
    )
    claims = {"iss": snapshot.issuer, "iat": int(moment.timestamp()),
              "amr_public_registry": snapshot.model_dump()}
    return jwt.encode(
        claims, private_key, algorithm=ALGORITHM,
        headers={"typ": EXPORT_TYP, "kid": key_id},
    )


def write_export(out: Path, **kwargs: Any) -> str:
    """Write the signed snapshot to ``out`` atomically; return the JWS."""
    token = asyncio.run(build_export(**kwargs))
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(token, encoding="ascii")
    os.replace(tmp, out)
    return token


# ---------------------------------------------------------------------------
# Loading a snapshot (verification side)
# ---------------------------------------------------------------------------


def load_public_key_file(path: Path) -> ed25519.Ed25519PublicKey:
    """Read the registry public key: PEM, or the JSON returned by get_registry_public_key."""
    content = path.read_bytes()
    if content.lstrip().startswith(b"{"):
        try:
            content = json.loads(content)["public_key_pem"].encode("ascii")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise PublicRegistryError("public_key_invalid", "no public_key_pem") from exc
    return parse_public_key(content)


def parse_public_key(pem: bytes | str) -> ed25519.Ed25519PublicKey:
    data = pem.encode("ascii") if isinstance(pem, str) else pem
    try:
        key = serialization.load_pem_public_key(data)
    except ValueError as exc:
        raise PublicRegistryError("public_key_invalid", "not a PEM public key") from exc
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise PublicRegistryError("public_key_invalid", "the registry key must be Ed25519")
    return key


def load_snapshot(
    token: str, public_key: ed25519.Ed25519PublicKey, issuer: str | None = None
) -> PublicSnapshot:
    """Verify a signed snapshot with the pinned registry key and return its content."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise PublicRegistryError("malformed", "not a compact JWS") from exc
    if header.get("alg") != ALGORITHM:
        raise PublicRegistryError("wrong_algorithm", "only EdDSA is accepted")
    if header.get("typ") != EXPORT_TYP:
        raise PublicRegistryError("not_a_registry_export", f"typ must be {EXPORT_TYP}")
    key_id = registry_key_id(public_key)
    if header.get("kid") != key_id:
        raise PublicRegistryError("key_mismatch", "signed with another registry key")
    try:
        claims = jwt.decode(
            token, public_key, algorithms=[ALGORITHM],
            options={"verify_iat": False, "verify_aud": False, "verify_iss": False},
        )
    except jwt.InvalidSignatureError as exc:
        raise PublicRegistryError("bad_signature", "signature does not verify") from exc
    except jwt.InvalidTokenError as exc:
        raise PublicRegistryError("malformed", str(exc)) from exc
    try:
        snapshot = PublicSnapshot.model_validate(claims.get("amr_public_registry"))
    except ValidationError as exc:
        raise PublicRegistryError("snapshot_invalid", "content does not match v1") from exc
    if snapshot.key_id != key_id or claims.get("iss") != snapshot.issuer:
        raise PublicRegistryError("snapshot_invalid", "header and content disagree")
    if issuer is not None and snapshot.issuer != issuer:
        raise PublicRegistryError("wrong_issuer", "exported by another registry")
    ids = [mandate.id for mandate in snapshot.mandates]
    if len(ids) != len(set(ids)):
        raise PublicRegistryError("snapshot_invalid", "a mandate appears twice")
    return snapshot


# ---------------------------------------------------------------------------
# Status, evaluated at request time from the snapshot
# ---------------------------------------------------------------------------


def _expired(expires_at: str, now: float) -> bool:
    moment = datetime.fromisoformat(expires_at)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp() <= now


def evaluate(
    index: dict[str, PublicMandate], mandate_id: str, now: float
) -> dict[str, Any]:
    """Status of a mandate now, from the snapshot: the mandate itself, then its chain.

    ``active`` only if the mandate is recorded active, not revoked, not expired, and
    every mandate above it is too (a sub-mandate is only as valid as its parents).
    """
    mandate = index.get(mandate_id)
    if mandate is None:
        return {"status": "unknown"}
    result: dict[str, Any] = {"status": "active", "reason": None, "refused_by": None}
    if mandate.revoked_at is not None:
        result.update(status="revoked", reason="mandate_revoked", refused_by=mandate.id)
    elif mandate.recorded_status != "active":
        result.update(status="inactive", reason=f"mandate_{mandate.recorded_status}",
                      refused_by=mandate.id)
    elif _expired(mandate.expires_at, now):
        result.update(status="expired", reason="mandate_expired", refused_by=mandate.id)
    chain: list[dict[str, Any]] = []
    parent_id = mandate.parent_mandate_id
    while parent_id:
        if len(chain) >= MAX_DELEGATION_DEPTH:
            reason, refused_by = "delegation_chain_too_deep", None
        else:
            parent = index.get(parent_id)
            if parent is None:
                reason, refused_by = "parent_mandate_not_found", parent_id
            elif parent.revoked_at is not None:
                reason, refused_by = "parent_mandate_revoked", parent.id
            elif parent.recorded_status != "active":
                reason, refused_by = f"parent_mandate_{parent.recorded_status}", parent.id
            elif _expired(parent.expires_at, now):
                reason, refused_by = "parent_mandate_expired", parent.id
            else:
                chain.append({"mandate_id": parent.id, "agent_id": parent.agent_id,
                              "principal_ref": parent.principal_ref,
                              "expires_at": parent.expires_at})
                parent_id = parent.parent_mandate_id
                continue
        if result["status"] == "active":
            result.update(status="cut_by_parent", reason=reason, refused_by=refused_by)
        break
    result["delegation_chain"] = chain
    return result


# ---------------------------------------------------------------------------
# WSGI application (read-only)
# ---------------------------------------------------------------------------

_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

_STATUS_TEXT = {
    200: "200 OK", 400: "400 Bad Request", 404: "404 Not Found",
    405: "405 Method Not Allowed", 414: "414 URI Too Long",
}

_STYLE = (
    "body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:0 auto;"
    "padding:1rem;color:#1b1f24;background:#fff}h1{font-size:1.4rem}"
    "code,textarea,input{font:14px ui-monospace,monospace}"
    "textarea,input[type=text]{width:100%;box-sizing:border-box}"
    "dl{display:grid;grid-template-columns:max-content 1fr;gap:.25rem 1rem}"
    "dd{margin:0;overflow-wrap:anywhere}.s{font-weight:700}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}}"
)


def _wants_html(environ: dict[str, Any], query: dict[str, list[str]]) -> bool:
    fmt = query.get("format", [""])[0]
    if fmt in ("html", "json"):
        return fmt == "html"
    accept = environ.get("HTTP_ACCEPT", "")
    return "text/html" in accept and "application/json" not in accept


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body>{body}</body></html>"
    )


def _dl(items: Iterable[tuple[str, Any]]) -> str:
    rows = []
    for label, value in items:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        rows.append(f"<dt>{html.escape(label)}</dt><dd><code>{html.escape(text)}</code></dd>")
    return "<dl>" + "".join(rows) + "</dl>"


def make_app(
    export_token: str,
    public_key: ed25519.Ed25519PublicKey,
    *,
    issuer: str | None = None,
    clock: Callable[[], float] = time.time,
) -> Callable[..., list[bytes]]:
    """Build the read-only WSGI application for one signed snapshot.

    The snapshot is verified here, once: an altered or foreign snapshot raises
    PublicRegistryError and nothing is served.
    """
    snapshot = load_snapshot(export_token, public_key, issuer)
    index = {mandate.id: mandate for mandate in snapshot.mandates}
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    generated = datetime.fromisoformat(snapshot.generated_at).timestamp()

    def registry_block(now: float) -> dict[str, Any]:
        return {
            "issuer": snapshot.issuer,
            "key_id": snapshot.key_id,
            "snapshot_generated_at": snapshot.generated_at,
            "snapshot_age_seconds": max(0, int(now - generated)),
            "notice": "Snapshot of the registry: a revocation made after "
                      "snapshot_generated_at is not shown here.",
        }

    def mandate_view(mandate_id: str, now: float) -> tuple[int, dict[str, Any]]:
        try:
            canonical = str(UUID(mandate_id))
        except ValueError:
            return 400, {"status": "invalid_id"}
        verdict = evaluate(index, canonical, now)
        if verdict["status"] == "unknown":
            return 404, {"status": "unknown", "mandate_id": canonical}
        return 200, {**verdict, "mandate": index[canonical].model_dump()}

    def attestation_view(query: dict[str, list[str]], now: float) -> tuple[int, dict[str, Any]]:
        token = query.get("attestation", [""])[0].strip()
        if not token:
            return 400, {"valid": False, "reason": "attestation_missing"}
        audience = query.get("audience", [""])[0].strip() or None
        result = verify_attestation(token, public_pem, audience=audience,
                                    issuer=snapshot.issuer, now=now)
        if not result["valid"]:
            return 200, result
        summary = result["attestation"]
        ids = [summary["mandate_id"]] + [
            link["mandate_id"] for link in summary["delegation_chain"]
        ]
        for mandate_id in ids:
            mandate = index.get(mandate_id)
            if mandate is not None and mandate.revoked_at is not None:
                return 200, {"valid": False, "reason": "revoked_in_registry",
                             "refused_by": mandate_id, "revoked_at": mandate.revoked_at}
        known = summary["mandate_id"] in index
        return 200, {**result, "in_snapshot": known}

    def render_html(path: str, status: int, payload: dict[str, Any]) -> str:
        verification = payload.get("verification_ms")
        registry = payload.get("registry", {})
        footer = (
            f"<p>Verified in {html.escape(str(verification))} ms. Snapshot taken "
            f"{html.escape(str(registry.get('snapshot_generated_at')))}; a later "
            "revocation is not shown. Registry key "
            f"<code>{html.escape(str(registry.get('key_id')))}</code>.</p>"
            "<p><a href=\"/\">New verification</a></p>"
        )
        if path.startswith("/mandates/"):
            if status != 200:
                return _page("Mandate", "<h1>Mandate</h1><p class=\"s\">"
                             f"{html.escape(payload['status'])}</p>" + footer)
            mandate = payload["mandate"]
            items = [("status", payload["status"]), ("reason", payload["reason"] or "")]
            items += [(key, value) for key, value in mandate.items()]
            items.append(("delegation_chain", payload["delegation_chain"]))
            return _page("Mandate", "<h1>Mandate</h1><p class=\"s\">"
                         f"{html.escape(payload['status'])}</p>" + _dl(items) + footer)
        title = "valid" if payload.get("valid") else "not valid"
        items = [(key, value) for key, value in payload.items()
                 if key not in ("registry", "verification_ms")]
        return _page("Attestation", f"<h1>Attestation</h1><p class=\"s\">{title}</p>"
                     + _dl(items) + footer)

    def home() -> str:
        return _page("Verify an agent mandate", (
            "<h1>Verify an agent mandate</h1>"
            "<p>Read-only. No account. Nothing you type is stored.</p>"
            "<form method=\"get\" action=\"/mandates/\" id=\"m\">"
            "<label for=\"id\">Mandate identifier</label>"
            "<input type=\"text\" id=\"id\" name=\"id\" required>"
            "<input type=\"hidden\" name=\"format\" value=\"html\">"
            "<button>Check the mandate</button></form>"
            "<form method=\"get\" action=\"/attestation\">"
            "<label for=\"a\">Attestation (compact JWS)</label>"
            "<textarea id=\"a\" name=\"attestation\" rows=\"5\" required></textarea>"
            "<label for=\"aud\">Your audience, if it is addressed to you</label>"
            "<input type=\"text\" id=\"aud\" name=\"audience\">"
            "<input type=\"hidden\" name=\"format\" value=\"html\">"
            "<button>Check the attestation</button></form>"
            f"<p>Registry key <code>{html.escape(snapshot.key_id)}</code> "
            "(<a href=\"/key\">public key</a>). Snapshot taken "
            f"{html.escape(snapshot.generated_at)}.</p>"
        ))

    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        started = time.perf_counter()
        now = clock()
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        raw_query = environ.get("QUERY_STRING", "")
        headers = [
            ("X-Content-Type-Options", "nosniff"),
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Security-Policy", _CSP),
        ]
        if method not in ("GET", "HEAD"):
            status, payload, as_html = 405, {"error": "read_only"}, False
            headers.append(("Allow", "GET, HEAD"))
        elif len(raw_query) > MAX_QUERY_LENGTH:
            status, payload, as_html = 414, {"error": "query_too_long"}, False
        else:
            query = parse_qs(raw_query, max_num_fields=8)
            as_html = _wants_html(environ, query)
            if path == "/mandates/" and "id" in query:
                path = "/mandates/" + query["id"][0].strip()
            match = _UUID_PATH.match(path)
            if path == "/" and as_html:
                body = home().encode("utf-8")
                headers.append(("Content-Type", "text/html; charset=utf-8"))
                start_response(_STATUS_TEXT[200], headers)
                return [b"" if method == "HEAD" else body]
            if path == "/":
                status, payload = 200, {"endpoints": ["/mandates/<id>", "/attestation",
                                                      "/key"]}
            elif match:
                status, payload = mandate_view(match.group(1), now)
            elif path == "/attestation":
                status, payload = attestation_view(query, now)
            elif path == "/key":
                status, payload = 200, {"issuer": snapshot.issuer,
                                        "key_id": snapshot.key_id,
                                        "algorithm": ALGORITHM,
                                        "public_key_pem": public_pem}
            else:
                status, payload = 404, {"error": "not_found"}
        payload["checked_at"] = datetime.fromtimestamp(now, UTC).isoformat()
        payload["registry"] = registry_block(now)
        payload["verification_ms"] = round((time.perf_counter() - started) * 1000, 3)
        if as_html and path != "/" and status in (200, 400, 404):
            body = render_html(path, status, payload).encode("utf-8")
            headers.append(("Content-Type", "text/html; charset=utf-8"))
        else:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            headers.append(("Content-Type", "application/json; charset=utf-8"))
            headers.append(("Access-Control-Allow-Origin", "*"))
        start_response(_STATUS_TEXT[status], headers)
        return [b"" if method == "HEAD" else body]

    return app


def app_from_settings() -> Callable[..., list[bytes]]:
    """The application for a host: snapshot at AMR_PUBLIC_EXPORT_PATH, key at
    AMR_PUBLIC_KEY_PATH (the registry public key, pinned by the operator)."""
    token = Path(settings.public_export_path).read_text(encoding="ascii").strip()
    return make_app(token, load_public_key_file(Path(settings.public_key_path)))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _serve(app: Callable[..., list[bytes]], host: str, port: int) -> None:
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    class QuietHandler(WSGIRequestHandler):
        """No access log: the client's address is never written anywhere."""

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    with make_server(host, port, app, handler_class=QuietHandler) as server:
        print(f"Serving the public registry on http://{host}:{port}/", file=sys.stderr)
        server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amr.public_registry",
        description="Export a signed public snapshot of the registry, or serve one.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write the signed snapshot")
    export.add_argument("--out", type=Path, default=None,
                        help="output file (default: AMR_PUBLIC_EXPORT_PATH)")
    export.add_argument("--db", type=Path, default=None, help="database (default: AMR_DB_PATH)")
    serve = sub.add_parser("serve", help="serve a snapshot, read-only (local test)")
    serve.add_argument("--export", type=Path, default=None,
                       help="snapshot file (default: AMR_PUBLIC_EXPORT_PATH)")
    serve.add_argument("--public-key", type=Path, default=None,
                       help="registry public key, PEM or JSON (default: AMR_PUBLIC_KEY_PATH)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    try:
        if args.command == "export":
            out = args.out or Path(settings.public_export_path)
            write_export(out, db_path=args.db)
            print(json.dumps({"written": str(out)}))
            return 0
        token = Path(args.export or settings.public_export_path).read_text(
            encoding="ascii").strip()
        key = load_public_key_file(Path(args.public_key or settings.public_key_path))
        _serve(make_app(token, key), args.host, args.port)
        return 0
    except PublicRegistryError as exc:
        print(json.dumps({"error": exc.code, "detail": exc.detail}))
        return 1
    except OSError as exc:
        print(json.dumps({"error": "file_unreadable", "detail": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
