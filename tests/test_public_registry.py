"""Tests for the public registry: a third party verifies a mandate online, without an
account, from a signed snapshot that never exposes a person's name.

The questions: does an unknown identifier answer "unknown" without leaking anything?
Does a revoked mandate answer "revoked" with its date? Is a forged attestation or an
altered snapshot refused? Is any write possible? Does a name reach the export?
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr import public_registry as pr
from amr.crypto.signing import generate_signing_key, load_public_key, load_signing_key
from amr.tools.create_mandate import create_mandate
from amr.tools.issue_mandate_attestation import (
    get_registry_public_key,
    issue_mandate_attestation,
)
from amr.tools.revoke_mandate import revoke_mandate
from tests._helpers import insert_mandate_directly

PERSON = "Jeanne Exemple-Dupont"
SCOPE = "Order supplies for Jeanne Exemple-Dupont's practice"


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "registry_key.pem"
    pub = tmp_path / "registry_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    monkeypatch.setattr("amr.config.settings.public_export_path", tmp_path / "export.jws")
    generate_signing_key(priv, pub)


async def _mandate(principal: str = PERSON, agent: str = "agent:buyer", **kw: Any) -> str:
    result = json.loads(await create_mandate(
        principal_id=principal, agent_id=agent, scope=SCOPE,
        legal_basis_regulation="Delegation of authority", legal_basis_article="Section 2",
        duration_hours=kw.pop("duration_hours", 24.0),
        metadata={"contact": PERSON}, **kw,
    ))
    assert "error" not in result, result
    return result["mandate_id"]


async def _app(clock: Any = time.time) -> Any:
    return pr.make_app(await pr.build_export(), load_public_key(), clock=clock)


def _call(app: Any, path: str, query: str = "", method: str = "GET",
          accept: str = "") -> tuple[str, dict[str, str], bytes]:
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "HTTP_ACCEPT": accept, "REMOTE_ADDR": "203.0.113.77",
               "wsgi.input": BytesIO(b"")}
    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body


def _json(app: Any, path: str, query: str = "") -> tuple[str, dict[str, Any]]:
    status, headers, body = _call(app, path, query)
    assert headers["Content-Type"].startswith("application/json")
    return status, json.loads(body)


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


# --- export: content and privacy ------------------------------------------------


async def test_export_never_contains_a_name_scope_metadata_or_reason() -> None:
    mandate_id = await _mandate()
    await revoke_mandate(mandate_id, f"{PERSON} left the practice")
    token = await pr.build_export()
    text = json.dumps(_claims(token), ensure_ascii=False)
    assert mandate_id in text
    for secret in (PERSON, "Exemple", "Delegation of authority", "Section 2", "left the practice",
                   "contact"):
        assert secret not in text, secret
    entry = _claims(token)["amr_public_registry"]["mandates"][0]
    assert entry["principal_ref"] == pr.principal_ref(PERSON)
    assert entry["principal_ref"].startswith("sha256:")
    assert set(entry) == set(pr.PublicMandate.model_fields)


async def test_export_is_signed_eddsa_with_registry_key_and_typed() -> None:
    await _mandate()
    header = jwt.get_unverified_header(await pr.build_export())
    assert header["alg"] == "EdDSA"
    assert header["typ"] == pr.EXPORT_TYP
    from amr.attestation import registry_key_id

    assert header["kid"] == registry_key_id(load_public_key())


async def test_export_reads_database_without_changing_it(temp_db: Path) -> None:
    await _mandate()
    before = temp_db.read_bytes()
    await pr.build_export()
    assert temp_db.read_bytes() == before


async def test_export_opens_the_database_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    await _mandate()
    import aiosqlite

    opened: list[str] = []
    real_connect = aiosqlite.connect

    def spy(database: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(database))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(pr.aiosqlite, "connect", spy)
    await pr.build_export()
    assert opened and all(uri.endswith("?mode=ro") for uri in opened)


async def test_export_of_missing_database_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "nothing.db"
    with pytest.raises(pr.PublicRegistryError) as err:
        await pr.build_export(db_path=missing)
    assert err.value.code == "database_not_found"
    assert not missing.exists()


async def test_export_keeps_mandate_hash_unchanged() -> None:
    mandate_id = await _mandate()
    entry = _claims(await pr.build_export())["amr_public_registry"]["mandates"][0]
    import aiosqlite

    from amr.config import settings

    async with aiosqlite.connect(settings.db_path) as db:
        row = await (await db.execute(
            "SELECT chain_hash FROM mandates WHERE id = ?", (mandate_id,))).fetchone()
    assert entry["chain_hash"] == row[0]


async def test_write_export_and_cli_export(tmp_path: Path) -> None:
    await _mandate()
    out = tmp_path / "snap.jws"
    assert await asyncio.to_thread(pr.main, ["export", "--out", str(out)]) == 0
    snapshot = pr.load_snapshot(out.read_text(encoding="ascii"), load_public_key())
    assert len(snapshot.mandates) == 1
    assert not (tmp_path / "snap.jws.tmp").exists()


# --- loading: forged or foreign snapshots are refused ---------------------------


async def test_altered_snapshot_is_refused() -> None:
    await _mandate()
    header, payload, signature = (await pr.build_export()).split(".")
    claims = _claims(f"{header}.{payload}.{signature}")
    claims["amr_public_registry"]["mandates"][0]["revoked_at"] = None
    claims["amr_public_registry"]["mandates"][0]["agent_id"] = "agent:other"
    forged_payload = jwt.utils.base64url_encode(
        json.dumps(claims, separators=(",", ":")).encode()).decode()
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(f"{header}.{forged_payload}.{signature}", load_public_key())
    assert err.value.code == "bad_signature"


async def test_snapshot_signed_by_another_key_is_refused() -> None:
    await _mandate()
    other = ed25519.Ed25519PrivateKey.generate()
    token = await pr.build_export(private_key=other)
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(token, load_public_key())
    assert err.value.code == "key_mismatch"


async def test_snapshot_with_other_algorithm_or_type_is_refused() -> None:
    await _mandate()
    claims = _claims(await pr.build_export())
    kid = jwt.get_unverified_header(await pr.build_export())["kid"]
    hs = jwt.encode(claims, "s" * 32, algorithm="HS256",
                    headers={"typ": pr.EXPORT_TYP, "kid": kid})
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(hs, load_public_key())
    assert err.value.code == "wrong_algorithm"
    none = jwt.encode(claims, None, algorithm="none", headers={"typ": pr.EXPORT_TYP})
    with pytest.raises(pr.PublicRegistryError):
        pr.make_app(none, load_public_key())
    wrong_typ = jwt.encode(claims, load_signing_key(), algorithm="EdDSA",
                           headers={"typ": "amr-attestation+jwt", "kid": kid})
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(wrong_typ, load_public_key())
    assert err.value.code == "not_a_registry_export"


async def test_snapshot_with_extra_field_or_duplicate_is_refused() -> None:
    await _mandate()
    claims = _claims(await pr.build_export())
    kid = jwt.get_unverified_header(await pr.build_export())["kid"]
    extra = json.loads(json.dumps(claims))
    extra["amr_public_registry"]["mandates"][0]["scope"] = SCOPE
    token = jwt.encode(extra, load_signing_key(), algorithm="EdDSA",
                       headers={"typ": pr.EXPORT_TYP, "kid": kid})
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(token, load_public_key())
    assert err.value.code == "snapshot_invalid"
    dup = json.loads(json.dumps(claims))
    dup["amr_public_registry"]["mandates"] *= 2
    token = jwt.encode(dup, load_signing_key(), algorithm="EdDSA",
                       headers={"typ": pr.EXPORT_TYP, "kid": kid})
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(token, load_public_key())
    assert err.value.code == "snapshot_invalid"


async def test_wrong_issuer_is_refused_when_pinned() -> None:
    await _mandate()
    with pytest.raises(pr.PublicRegistryError) as err:
        pr.make_app(await pr.build_export(), load_public_key(), issuer="amr://elsewhere")
    assert err.value.code == "wrong_issuer"


def test_public_key_file_pem_and_json(tmp_path: Path) -> None:
    pem = load_public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    (tmp_path / "k.pem").write_bytes(pem)
    (tmp_path / "k.json").write_text(json.dumps({"public_key_pem": pem.decode()}))
    (tmp_path / "bad.json").write_text("{}")
    assert isinstance(pr.load_public_key_file(tmp_path / "k.pem"), ed25519.Ed25519PublicKey)
    assert isinstance(pr.load_public_key_file(tmp_path / "k.json"), ed25519.Ed25519PublicKey)
    with pytest.raises(pr.PublicRegistryError):
        pr.load_public_key_file(tmp_path / "bad.json")


# --- answers ---------------------------------------------------------------------


async def test_active_mandate_answers_active_with_timing() -> None:
    mandate_id = await _mandate()
    status, body = _json(await _app(), f"/mandates/{mandate_id}")
    assert status.startswith("200")
    assert body["status"] == "active"
    assert body["mandate"]["id"] == mandate_id
    assert isinstance(body["verification_ms"], float)
    assert body["registry"]["snapshot_generated_at"]
    assert "revocation made after" in body["registry"]["notice"]


async def test_unknown_identifier_answers_unknown_without_leak() -> None:
    known = await _mandate()
    unknown = str(uuid4())
    status, headers, raw = _call(await _app(), f"/mandates/{unknown}")
    assert status.startswith("404")
    body = json.loads(raw)
    assert body["status"] == "unknown"
    assert known not in raw.decode()
    assert "agent:buyer" not in raw.decode()


async def test_invalid_identifier_is_rejected() -> None:
    await _mandate()
    status, body = _json(await _app(), "/mandates/not-a-uuid")
    assert status.startswith("400")
    assert body["status"] == "invalid_id"


async def test_revoked_mandate_answers_revoked_with_date() -> None:
    mandate_id = await _mandate()
    await revoke_mandate(mandate_id, "ended")
    status, body = _json(await _app(), f"/mandates/{mandate_id}")
    assert status.startswith("200")
    assert body["status"] == "revoked"
    assert body["mandate"]["revoked_at"]
    datetime.fromisoformat(body["mandate"]["revoked_at"])


async def test_sub_mandate_under_revoked_parent_is_cut() -> None:
    parent, child = str(uuid4()), str(uuid4())
    from amr.config import settings

    await insert_mandate_directly(settings.db_path, parent, agent_id="agent:a")
    await insert_mandate_directly(settings.db_path, child, principal_id="agent:a",
                                  agent_id="agent:b", parent_mandate_id=parent)
    await revoke_mandate(parent, "ended")
    _, body = _json(await _app(), f"/mandates/{child}")
    assert body["status"] == "cut_by_parent"
    assert body["reason"] == "parent_mandate_revoked"
    assert body["refused_by"] == parent


async def test_sub_mandate_chain_is_listed_when_active() -> None:
    parent, child = str(uuid4()), str(uuid4())
    from amr.config import settings

    await insert_mandate_directly(settings.db_path, parent, agent_id="agent:a")
    await insert_mandate_directly(settings.db_path, child, principal_id="agent:a",
                                  agent_id="agent:b", parent_mandate_id=parent)
    _, body = _json(await _app(), f"/mandates/{child}")
    assert body["status"] == "active"
    assert [link["mandate_id"] for link in body["delegation_chain"]] == [parent]


async def test_inactive_and_missing_parent() -> None:
    from amr.config import settings

    suspended, orphan = str(uuid4()), str(uuid4())
    await insert_mandate_directly(settings.db_path, suspended, status="suspended")
    await insert_mandate_directly(settings.db_path, orphan, parent_mandate_id=str(uuid4()))
    app = await _app()
    _, body = _json(app, f"/mandates/{suspended}")
    assert (body["status"], body["reason"]) == ("inactive", "mandate_suspended")
    _, body = _json(app, f"/mandates/{orphan}")
    assert (body["status"], body["reason"]) == ("cut_by_parent", "parent_mandate_not_found")


async def test_expiry_is_evaluated_at_request_time() -> None:
    mandate_id = await _mandate(duration_hours=1.0)
    later = time.time() + 2 * 3600
    _, body = _json(await _app(clock=lambda: later), f"/mandates/{mandate_id}")
    assert body["status"] == "expired"
    assert body["registry"]["snapshot_age_seconds"] >= 7000


async def test_parent_expiry_cuts_child_at_request_time() -> None:
    from amr.config import settings

    parent, child = str(uuid4()), str(uuid4())
    await insert_mandate_directly(settings.db_path, parent, agent_id="agent:a",
                                  hours_until_expiry=1.0)
    await insert_mandate_directly(settings.db_path, child, principal_id="agent:a",
                                  agent_id="agent:b", parent_mandate_id=parent,
                                  hours_until_expiry=5.0)
    later = time.time() + 2 * 3600
    _, body = _json(await _app(clock=lambda: later), f"/mandates/{child}")
    assert (body["status"], body["reason"]) == ("cut_by_parent", "parent_mandate_expired")


def test_chain_too_deep_is_cut() -> None:
    index: dict[str, pr.PublicMandate] = {}
    far = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    previous = None
    for depth in range(pr.MAX_DELEGATION_DEPTH + 2):
        mandate_id = f"m{depth}"
        index[mandate_id] = pr.PublicMandate(
            id=mandate_id, agent_id="a", principal_ref=pr.principal_ref("p"),
            principal_signed=False, principal_key_id=None, perimeter=None,
            perimeter_digest=None, created_at=far, expires_at=far,
            parent_mandate_id=previous, recorded_status="active", revoked_at=None,
            chain_hash="0" * 64)
        previous = mandate_id
    verdict = pr.evaluate(index, previous, time.time())
    assert verdict["reason"] == "delegation_chain_too_deep"


# --- read-only ----------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_no_write_method_is_accepted(method: str, temp_db: Path) -> None:
    mandate_id = await _mandate()
    app = await _app()
    before = temp_db.read_bytes()
    status, headers, body = _call(app, f"/mandates/{mandate_id}", method=method)
    assert status.startswith("405")
    assert headers["Allow"] == "GET, HEAD"
    assert temp_db.read_bytes() == before
    _, after = _json(app, f"/mandates/{mandate_id}")
    assert after["status"] == "active"


async def test_head_returns_no_body() -> None:
    mandate_id = await _mandate()
    status, _, body = _call(await _app(), f"/mandates/{mandate_id}", method="HEAD")
    assert status.startswith("200")
    assert body == b""


async def test_security_headers_and_client_address_never_echoed() -> None:
    mandate_id = await _mandate()
    for path, accept in ((f"/mandates/{mandate_id}", ""), ("/", "text/html"),
                         (f"/mandates/{mandate_id}", "text/html")):
        _, headers, body = _call(await _app(), path, accept=accept)
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Cache-Control"] == "no-store"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert b"203.0.113.77" not in body


async def test_query_too_long_is_refused() -> None:
    await _mandate()
    status, _, _ = _call(await _app(), "/attestation", "attestation=" + "a" * 20_000)
    assert status.startswith("414")


def test_local_server_writes_no_access_log(capsys: pytest.CaptureFixture[str]) -> None:
    import socket
    import threading
    import urllib.request
    import wsgiref.simple_server as ws

    def tiny(environ: dict[str, Any], start_response: Any) -> list[bytes]:
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    servers: list[Any] = []
    real_make_server = ws.make_server

    def recording_make_server(*args: Any, **kwargs: Any) -> Any:
        server = real_make_server(*args, **kwargs)
        servers.append(server)
        return server

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    ws.make_server = recording_make_server
    thread = threading.Thread(target=pr._serve, args=(tiny, "127.0.0.1", port), daemon=True)
    body = None
    try:
        thread.start()
        for _ in range(100):
            try:
                body = urllib.request.urlopen(  # noqa: S310 - local test server
                    f"http://127.0.0.1:{port}/probe", timeout=1).read()
                break
            except OSError:
                time.sleep(0.05)
    finally:
        ws.make_server = real_make_server
        for server in servers:
            server.shutdown()
        thread.join(timeout=5)
    assert body == b"ok"
    err = capsys.readouterr().err
    assert "/probe" not in err
    assert "127.0.0.1 - -" not in err


# --- HTML for people -----------------------------------------------------------------


async def test_html_answer_escapes_values_and_shows_timing() -> None:
    mandate_id = await _mandate(agent="<script>alert(1)</script>")
    status, headers, body = _call(await _app(), f"/mandates/{mandate_id}", "format=html")
    assert status.startswith("200")
    assert headers["Content-Type"].startswith("text/html")
    text = body.decode()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
    assert "Verified in" in text and " ms" in text


async def test_form_lookup_by_query_id() -> None:
    mandate_id = await _mandate()
    status, _, body = _call(await _app(), "/mandates/", f"id={mandate_id}&format=html")
    assert status.startswith("200")
    assert "active" in body.decode()


async def test_home_page_and_key() -> None:
    await _mandate()
    app = await _app()
    status, headers, body = _call(app, "/", accept="text/html")
    assert headers["Content-Type"].startswith("text/html")
    assert b"Verify an agent mandate" in body
    _, key = _json(app, "/key")
    expected = json.loads(await get_registry_public_key())
    assert key["key_id"] == expected["key_id"]
    assert key["public_key_pem"] == expected["public_key_pem"]
    _, index = _json(app, "/")
    assert "/attestation" in index["endpoints"]


# --- attestations pasted into the page -------------------------------------------------


async def _attestation(mandate_id: str, audience: str | None = None) -> str:
    result = json.loads(await issue_mandate_attestation(mandate_id, "agent:buyer",
                                                        audience=audience))
    return result["attestation"]


async def test_valid_attestation_is_accepted() -> None:
    mandate_id = await _mandate()
    token = await _attestation(mandate_id)
    _, body = _json(await _app(), "/attestation", f"attestation={token}")
    assert body["valid"] is True
    assert body["in_snapshot"] is True
    assert body["attestation"]["mandate_id"] == mandate_id


async def test_forged_attestation_is_refused() -> None:
    mandate_id = await _mandate()
    token = await _attestation(mandate_id)
    header, payload, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    _, body = _json(await _app(), "/attestation", f"attestation={header}.{payload}.{flipped}")
    assert body["valid"] is False
    assert body["reason"] == "bad_signature"


async def test_attestation_of_mandate_revoked_since_is_refused() -> None:
    mandate_id = await _mandate()
    token = await _attestation(mandate_id)
    await revoke_mandate(mandate_id, "ended")
    _, body = _json(await _app(), "/attestation", f"attestation={token}")
    assert body["valid"] is False
    assert body["reason"] == "revoked_in_registry"
    assert body["refused_by"] == mandate_id


async def test_attestation_under_parent_revoked_since_is_refused() -> None:
    parent = await _mandate(principal="org:clinic", agent="agent:lead",
                            allowed_actions=["order.*"], delegation_allowed=True)
    child = json.loads(await create_mandate(
        principal_id="agent:lead", agent_id="agent:buyer", scope="sub",
        legal_basis_regulation="Delegation of authority", legal_basis_article="Section 2",
        duration_hours=1.0, parent_mandate_id=parent, allowed_actions=["order.small"],
    ))
    assert "error" not in child, child
    token = await _attestation(child["mandate_id"])
    await revoke_mandate(parent, "ended")
    _, body = _json(await _app(), "/attestation", f"attestation={token}")
    assert (body["valid"], body["reason"], body["refused_by"]) == (
        False, "revoked_in_registry", parent)


async def test_addressed_attestation_needs_its_audience() -> None:
    mandate_id = await _mandate()
    token = await _attestation(mandate_id, audience="seller:acme")
    app = await _app()
    _, body = _json(app, "/attestation", f"attestation={token}")
    assert (body["valid"], body["reason"]) == (False, "wrong_audience")
    _, body = _json(app, "/attestation", f"attestation={token}&audience=seller:acme")
    assert body["valid"] is True


async def test_missing_attestation_is_a_bad_request() -> None:
    await _mandate()
    status, body = _json(await _app(), "/attestation")
    assert status.startswith("400")
    assert body["reason"] == "attestation_missing"


async def test_app_from_settings(tmp_path: Path) -> None:
    mandate_id = await _mandate()
    from amr.config import settings

    await asyncio.to_thread(pr.write_export, Path(settings.public_export_path))
    _, body = _json(pr.app_from_settings(), f"/mandates/{mandate_id}")
    assert body["status"] == "active"


# --- after the independent review ----------------------------------------------------


async def test_raw_snapshot_is_served_for_receivers_who_verify_themselves() -> None:
    await _mandate()
    token = await pr.build_export()
    app = pr.make_app(token, load_public_key())
    status, headers, body = _call(app, "/snapshot")
    assert status.startswith("200")
    assert headers["Content-Type"].startswith("application/jose")
    assert body.decode() == token
    assert pr.load_snapshot(body.decode(), load_public_key()).mandates


async def test_old_snapshot_is_refused_when_a_maximum_age_is_set() -> None:
    mandate_id = await _mandate()
    old = await pr.build_export(now=datetime.now(UTC) - timedelta(hours=2))
    await revoke_mandate(mandate_id, "ended")
    token = await _attestation_after_revocation_is_impossible(mandate_id)
    app = pr.make_app(old, load_public_key(), max_snapshot_age_seconds=3600)
    status, body = _json(app, f"/mandates/{mandate_id}")
    assert status.startswith("503")
    assert body["status"] == "snapshot_too_old"
    status, body = _json(app, "/attestation", f"attestation={token}")
    assert (body["valid"], body["reason"]) == (False, "snapshot_too_old")
    status, _, page = _call(app, f"/mandates/{mandate_id}", "format=html")
    assert status.startswith("503") and b"snapshot_too_old" in page
    fresh = pr.make_app(await pr.build_export(), load_public_key(),
                        max_snapshot_age_seconds=3600)
    _, body = _json(fresh, f"/mandates/{mandate_id}")
    assert body["status"] == "revoked"


async def _attestation_after_revocation_is_impossible(mandate_id: str) -> str:
    result = json.loads(await issue_mandate_attestation(mandate_id, "agent:buyer"))
    assert result.get("denied") is True
    return "x.y.z"


async def test_typed_value_with_slash_or_unknown_path_renders_not_found() -> None:
    await _mandate()
    app = await _app()
    for path, query in (("/mandates/", "id=a/b&format=html"),
                        ("/mandates/x/y", "format=html"), ("/anything", "format=html")):
        status, headers, body = _call(app, path, query)
        assert status.startswith("404"), path
        assert headers["Content-Type"].startswith("text/html")
        assert b"Not found" in body
        assert b"Attestation" not in body


async def test_too_many_query_fields_is_a_bad_request() -> None:
    await _mandate()
    query = "&".join(f"f{i}=1" for i in range(20))
    status, body = _json(await _app(), "/attestation", query)
    assert status.startswith("400")
    assert body["error"] == "bad_query"


async def test_export_never_creates_a_registry_key(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    await _mandate()
    missing = tmp_path / "nokey" / "registry.pem"
    from amr.config import settings

    pub_path = Path(settings.public_key_path)
    pub_before = pub_path.read_bytes()
    monkeypatch.setattr("amr.config.settings.signing_key_path", missing)
    with pytest.raises(pr.PublicRegistryError) as err:
        await pr.build_export()
    assert err.value.code == "signing_key_not_found"
    assert not missing.exists()
    assert pub_path.read_bytes() == pub_before


async def test_outdated_database_gives_a_clear_error(tmp_path: Path) -> None:
    import sqlite3

    old = tmp_path / "old.db"
    with sqlite3.connect(old) as db:
        db.execute("CREATE TABLE mandates (id TEXT PRIMARY KEY, principal_id TEXT)")
    with pytest.raises(pr.PublicRegistryError) as err:
        await pr.build_export(db_path=old)
    assert err.value.code == "schema_outdated"


async def test_app_from_settings_applies_the_maximum_age(
        monkeypatch: pytest.MonkeyPatch) -> None:
    mandate_id = await _mandate()
    from amr.config import settings

    path = Path(settings.public_export_path)
    old = await pr.build_export(now=datetime.now(UTC) - timedelta(hours=2))
    path.write_text(old, encoding="ascii")
    monkeypatch.setattr("amr.config.settings.public_snapshot_max_age_seconds", 3600)
    status, body = _json(pr.app_from_settings(), f"/mandates/{mandate_id}")
    assert (status[:3], body["status"]) == ("503", "snapshot_too_old")
