"""Registry timestamps: an outside RFC 3161 service dates the state of the registry.

AMR prepares the request and checks the response; it never contacts the service. The
service is simulated here (pyHanko's dummy time-stamper, with its own test authority):
no network call in these tests.
"""

import asyncio
import base64
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from asn1crypto import algos, tsp
from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko.sign.timestamps.dummy_client import DummyTimeStamper
from pyhanko_certvalidator.registry import SimpleCertificateStore

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.registry_timestamp import ANCHOR_V1_COLUMNS, anchor_sha256, canonical
from amr.server import TOOL_PROFILES
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.log_action import log_action
from amr.tools.registry_timestamp import (
    prepare_registry_timestamp,
    record_registry_timestamp,
    timestamp_hash_data,
)

BASE = {
    "principal_id": "org:clinic",
    "agent_id": "agent:scribe",
    "scope": "Write consultation notes",
    "legal_basis_regulation": "Delegation of authority",
    "legal_basis_article": "Section 2",
    "duration_hours": 24.0,
}


def _cert(name, key, issuer=None, issuer_key=None, ca=False, tsa=False):
    now = datetime.now(UTC)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer.subject if issuer else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=30))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if tsa:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True
        ).add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, False, False),
            critical=True,
        )
    else:
        builder = builder.add_extension(
            x509.KeyUsage(True, False, False, False, False, True, True, False, False),
            critical=True,
        )
    return builder.sign(issuer_key or key, hashes.SHA256())


def _asn1(cert) -> asn1_x509.Certificate:
    return asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))


class Authority:
    """A test certificate authority and the time-stamping service it certifies."""

    def __init__(self, name: str) -> None:
        root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.root = _cert(f"{name} Root", root_key, ca=True)
        tsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.tsa_cert = _cert(f"{name} TSA", tsa_key, self.root, root_key, tsa=True)
        self.tsa_key = asn1_keys.PrivateKeyInfo.load(
            tsa_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    def pem(self, path: Path) -> Path:
        path.write_bytes(self.root.public_bytes(serialization.Encoding.PEM))
        return path

    def respond(self, request_der: bytes, at: datetime | None = None) -> bytes:
        stamper = DummyTimeStamper(
            tsa_cert=_asn1(self.tsa_cert),
            tsa_key=self.tsa_key,
            certs_to_embed=SimpleCertificateStore.from_certs([_asn1(self.root)]),
            fixed_dt=at,
        )
        response = asyncio.run(
            stamper.async_request_tsa_response(tsp.TimeStampReq.load(request_der))
        )
        return response.dump()


TRUSTED = Authority("Trusted Test")
OTHER = Authority("Other Test")


@pytest.fixture
def trusted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = TRUSTED.pem(tmp_path / "tsa_roots.pem")
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", path)
    return path


async def _registry() -> dict:
    mandate = json.loads(await create_mandate(**BASE))
    assert "mandate_id" in mandate, mandate
    action = json.loads(
        await log_action(mandate["mandate_id"], BASE["agent_id"], "note.write", "{}")
    )
    assert "chain_hash" in action or "action_id" in action, action
    return mandate


async def _prepare() -> dict:
    prepared = json.loads(await prepare_registry_timestamp())
    assert "anchor" in prepared, prepared
    return prepared


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def _stamp(authority: Authority = TRUSTED, at: datetime | None = None) -> dict:
    prepared = await _prepare()
    request = base64.b64decode(prepared["timestamp_request"])
    response = await asyncio.to_thread(authority.respond, request, at)
    prepared["response"] = response
    return prepared


async def _record(prepared: dict, response: bytes | None = None) -> dict:
    return json.loads(
        await record_registry_timestamp(
            json.dumps(prepared["anchor"]), _b64(response or prepared["response"])
        )
    )


# --- the request ------------------------------------------------------------------


async def test_the_request_dates_the_sha256_of_the_anchor_with_its_nonce() -> None:
    await _registry()
    prepared = await _prepare()
    request = tsp.TimeStampReq.load(base64.b64decode(prepared["timestamp_request"]))
    imprint = request["message_imprint"]
    assert imprint["hash_algorithm"]["algorithm"].native == "sha256"
    assert (
        imprint["hashed_message"].native == hashlib.sha256(canonical(prepared["anchor"])).digest()
    )
    assert request["nonce"].native == prepared["anchor"]["nonce"]
    assert request["cert_req"].native is True
    assert prepared["anchor_sha256"] == anchor_sha256(prepared["anchor"])
    assert prepared["content_type"] == "application/timestamp-query"


async def test_the_anchor_covers_every_append_only_table_and_counts_rows() -> None:
    await _registry()
    anchor = (await _prepare())["anchor"]
    assert set(anchor["tables"]) == set(ANCHOR_V1_COLUMNS)
    assert anchor["tables"]["mandates"]["rows"] == 1
    assert anchor["tables"]["action_logs"]["rows"] == 1
    assert anchor["tables"]["issued_tokens"]["rows"] == 0


async def test_each_request_has_a_fresh_nonce() -> None:
    await _registry()
    first, second = await _prepare(), await _prepare()
    assert first["anchor"]["nonce"] != second["anchor"]["nonce"]


async def test_the_anchor_follows_the_specification(temp_db: Path) -> None:
    """Recompute a table digest the way docs/registry-timestamp-spec.md says."""
    await _registry()
    anchor = (await _prepare())["anchor"]
    conn = sqlite3.connect(str(temp_db))
    columns = ", ".join(ANCHOR_V1_COLUMNS["mandates"])
    rows = conn.execute(f"SELECT rowid, {columns} FROM mandates ORDER BY rowid").fetchall()  # noqa: S608
    conn.close()
    digest = hashlib.sha256()
    for row in rows:
        line = json.dumps(list(row), separators=(",", ":"))
        digest.update(hashlib.sha256(line.encode()).digest())
    assert anchor["tables"]["mandates"]["sha256"] == digest.hexdigest()


async def test_prepare_never_creates_a_registry(temp_db: Path) -> None:
    body = json.loads(await prepare_registry_timestamp())
    assert body["code"] == "registry_unavailable"
    assert not temp_db.exists()


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")
async def test_openssl_reads_the_request(tmp_path: Path) -> None:
    await _registry()
    prepared = await _prepare()
    req = tmp_path / "req.tsq"
    req.write_bytes(base64.b64decode(prepared["timestamp_request"]))
    text = subprocess.run(  # noqa: S603
        ["openssl", "ts", "-query", "-in", str(req), "-text"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "sha256" in text.lower()
    [nonce] = re.findall(r"Nonce: 0x([0-9A-Fa-f]+)", text)
    assert int(nonce, 16) == prepared["anchor"]["nonce"]
    parsed = subprocess.run(  # noqa: S603
        ["openssl", "asn1parse", "-inform", "DER", "-in", str(req)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    digest = hashlib.sha256(canonical(prepared["anchor"])).hexdigest().upper()
    assert f"[HEX DUMP]:{digest}" in parsed


# --- recording --------------------------------------------------------------------


async def test_a_trusted_response_is_recorded(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp()
    body = await _record(prepared)
    assert body["status"] == "recorded", body
    assert body["anchor_sha256"] == prepared["anchor_sha256"]
    assert "Trusted Test TSA" in body["tsa"]
    assert body["rows_anchored"]["mandates"] == 1
    assert len(body["chain_hash"]) == 64


async def test_without_trust_roots_nothing_is_accepted() -> None:
    await _registry()
    prepared = await _stamp()
    body = await _record(prepared)
    assert body["code"] == "timestamp_trust_roots_missing"


async def test_unreadable_trust_roots_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "roots.pem"
    bad.write_text("not a certificate")
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", bad)
    await _registry()
    body = await _record(await _stamp())
    assert body["code"] == "timestamp_trust_roots_missing"


async def test_a_response_from_another_service_is_refused(trusted: Path) -> None:
    await _registry()
    body = await _record(await _stamp(OTHER))
    assert body["code"] == "timestamp_signer_not_trusted"


async def test_a_response_for_another_digest_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp()
    other = await _stamp()  # another anchor (another nonce): another digest
    body = await _record(prepared, other["response"])
    assert body["code"] == "timestamp_imprint_mismatch"


async def test_an_edited_anchor_is_refused(trusted: Path) -> None:
    """Claiming fewer rows than were dated changes the anchor, so its digest."""
    await _registry()
    prepared = await _stamp()
    prepared["anchor"]["tables"]["action_logs"]["rows"] = 0
    body = await _record(prepared)
    assert body["code"] == "timestamp_imprint_mismatch"


async def test_a_response_with_another_nonce_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _prepare()
    request = tsp.TimeStampReq(
        {
            "version": "v1",
            "message_imprint": tsp.MessageImprint(
                {
                    "hash_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}),
                    "hashed_message": hashlib.sha256(canonical(prepared["anchor"])).digest(),
                }
            ),
            "nonce": prepared["anchor"]["nonce"] + 1,
            "cert_req": True,
        }
    ).dump()
    response = await asyncio.to_thread(TRUSTED.respond, request, None)
    body = await _record(prepared, response)
    assert body["code"] == "timestamp_nonce_mismatch"


async def test_a_response_without_nonce_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _prepare()
    request = tsp.TimeStampReq.load(base64.b64decode(prepared["timestamp_request"]))
    bare = tsp.TimeStampReq(
        {"version": "v1", "message_imprint": request["message_imprint"], "cert_req": True}
    ).dump()
    response = await asyncio.to_thread(TRUSTED.respond, bare, None)
    body = await _record(prepared, response)
    assert body["code"] == "timestamp_nonce_mismatch"


async def test_a_response_dated_before_the_anchor_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp(at=datetime.now(UTC) - timedelta(hours=1))
    body = await _record(prepared)
    assert body["code"] == "timestamp_before_anchor"


async def test_a_response_within_the_clock_skew_is_accepted(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp(at=datetime.now(UTC) - timedelta(seconds=60))
    body = await _record(prepared)
    assert body["status"] == "recorded", body


async def test_a_forged_signature_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp()
    response = tsp.TimeStampResp.load(prepared["response"])
    signer = response["time_stamp_token"]["content"]["signer_infos"][0]
    signature = bytearray(signer["signature"].native)
    signature[10] ^= 0xFF
    signer["signature"] = bytes(signature)
    body = await _record(prepared, response.dump(force=True))
    assert body["code"] == "timestamp_signature_invalid"


async def test_a_refused_request_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _prepare()
    rejection = bytes.fromhex("3005300302010" + "2")  # status rejection, no token
    body = await _record(prepared, rejection)
    assert body["code"] == "timestamp_not_granted"


@pytest.mark.parametrize("garbage", [b"not der at all", b"\x30\x03\x02\x01\x00"])
async def test_garbage_is_malformed(trusted: Path, garbage: bytes) -> None:
    await _registry()
    prepared = await _prepare()
    body = await _record(prepared, garbage)
    assert body["code"] == "timestamp_malformed"


async def test_non_base64_is_malformed(trusted: Path) -> None:
    await _registry()
    prepared = await _prepare()
    body = json.loads(
        await record_registry_timestamp(json.dumps(prepared["anchor"]), "not base64 !!")
    )
    assert body["code"] == "timestamp_malformed"


@pytest.mark.parametrize(
    "anchor",
    [
        "[]",
        "{}",
        "not json",
        json.dumps({"anchor_version": 2, "computed_at": "x", "nonce": 1, "tables": {}}),
    ],
)
async def test_an_anchor_amr_did_not_prepare_is_refused(trusted: Path, anchor: str) -> None:
    await _registry()
    prepared = await _stamp()
    body = json.loads(await record_registry_timestamp(anchor, _b64(prepared["response"])))
    assert body["code"] == "anchor_invalid"


async def test_an_anchor_missing_a_table_is_refused(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp()
    del prepared["anchor"]["tables"]["action_receipts"]
    body = await _record(prepared)
    assert body["code"] == "anchor_invalid"


async def test_input_too_long_is_invalid(trusted: Path) -> None:
    body = json.loads(await record_registry_timestamp("x" * 20001, "AAAA"))
    assert body["code"] == "invalid_input"
    assert body["field"] == "anchor_json"


async def test_a_registry_changed_before_recording_is_refused(trusted: Path, temp_db: Path) -> None:
    await _registry()
    prepared = await _stamp()
    conn = sqlite3.connect(str(temp_db))
    conn.execute("UPDATE action_logs SET evidence = 'rewritten'")
    conn.commit()
    conn.close()
    body = await _record(prepared)
    assert body["code"] == "anchor_mismatch"


async def test_rows_added_after_the_anchor_do_not_stop_recording(trusted: Path) -> None:
    mandate = await _registry()
    prepared = await _stamp()
    await log_action(mandate["mandate_id"], BASE["agent_id"], "note.write", "{}")
    body = await _record(prepared)
    assert body["status"] == "recorded", body


async def test_one_timestamp_per_anchor(trusted: Path) -> None:
    await _registry()
    prepared = await _stamp()
    assert (await _record(prepared))["status"] == "recorded"
    again = await _record(prepared)
    assert again["code"] == "timestamp_already_recorded"


async def test_timestamps_are_chained(trusted: Path, temp_db: Path) -> None:
    await _registry()
    first = await _record(await _stamp())
    second = await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM registry_timestamps ORDER BY rowid")]
    conn.close()
    assert rows[0]["chain_hash"] == first["chain_hash"]
    assert rows[0]["chain_hash"] == compute_hash(timestamp_hash_data(rows[0]), "")
    assert rows[1]["chain_hash"] == second["chain_hash"]
    assert rows[1]["chain_hash"] == compute_hash(
        timestamp_hash_data(rows[1]), rows[0]["chain_hash"]
    )


# --- in the proof -----------------------------------------------------------------


async def test_the_proof_shows_the_timestamp_covering_the_mandate(trusted: Path) -> None:
    mandate = await _registry()
    prepared = await _stamp()
    await _record(prepared)
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    [stamp] = proof["registry_timestamps"]
    assert stamp["anchor_sha256"] == prepared["anchor_sha256"]
    assert stamp["actions_covered"] == 1
    assert stamp["anchor_intact"] is True
    assert stamp["response_matches"] is True
    assert stamp["signature_valid"] is True
    assert base64.b64decode(stamp["timestamp_response"]) == prepared["response"]
    assert anchor_sha256(stamp["anchor"]) == prepared["anchor_sha256"]
    assert proof["chain_integrity"]["timestamps_intact"] is True


async def test_a_mandate_created_after_the_anchor_is_not_covered(trusted: Path) -> None:
    await _registry()
    await _record(await _stamp())
    later = json.loads(await create_mandate(**{**BASE, "agent_id": "agent:later"}))
    proof = json.loads(await get_proof(later["mandate_id"]))
    assert proof["registry_timestamps"] == []
    assert proof["chain_integrity"]["timestamps_intact"] is None


async def test_actions_logged_after_the_anchor_are_not_counted(trusted: Path) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    await log_action(mandate["mandate_id"], BASE["agent_id"], "note.write", "{}")
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"][0]["actions_covered"] == 1
    assert proof["chain_integrity"]["timestamps_intact"] is True


async def test_a_journal_changed_after_the_timestamp_is_detected(
    trusted: Path, temp_db: Path
) -> None:
    """Even when the hacker recomputes the action's chain hash so the chain still verifies."""
    mandate = await _registry()
    await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM action_logs").fetchone())
    mandate_hash = conn.execute(
        "SELECT chain_hash FROM mandates WHERE id = ?", (mandate["mandate_id"],)
    ).fetchone()[0]
    row["evidence"] = '{"rewritten": true}'
    data = {k: v for k, v in row.items() if k != "chain_hash"}
    new_hash = compute_hash(data, mandate_hash)
    conn.execute(
        "UPDATE action_logs SET evidence = ?, chain_hash = ? WHERE id = ?",
        (row["evidence"], new_hash, row["id"]),
    )
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"][0]["anchor_intact"] is False
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_a_deleted_row_is_detected(trusted: Path, temp_db: Path) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.execute("DELETE FROM action_logs")
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_a_changed_row_of_another_table_is_detected(trusted: Path, temp_db: Path) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.execute("UPDATE mandates SET scope = 'Write and send consultation notes'")
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_without_roots_the_proof_says_the_signature_is_not_checked(
    trusted: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", None)
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"][0]["signature_valid"] is None
    assert proof["chain_integrity"]["timestamps_intact"] is True


async def test_roots_that_no_longer_trust_the_service_show_in_the_proof(
    trusted: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", OTHER.pem(tmp_path / "o.pem"))
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"][0]["signature_valid"] is False
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_an_edited_timestamp_record_breaks_the_chain(trusted: Path, temp_db: Path) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.execute("UPDATE registry_timestamps SET gen_time = '2020-01-01T00:00:00+00:00'")
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_an_edited_stored_anchor_breaks_the_chain(trusted: Path, temp_db: Path) -> None:
    """Lowering the anchored rows in the stored anchor would hide later edits: refused."""
    mandate = await _registry()
    await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    stored = json.loads(conn.execute("SELECT anchor_json FROM registry_timestamps").fetchone()[0])
    stored["tables"]["mandates"]["last_rowid"] = 5
    conn.execute(
        "UPDATE registry_timestamps SET anchor_json = ?",
        (canonical(stored).decode(),),
    )
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_the_stored_anchor_is_sealed_even_without_trust_roots(
    trusted: Path, temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without roots the signature is not re-checked: the seal alone shows the edit."""
    mandate = await _registry()
    await _record(await _stamp())
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", None)
    conn = sqlite3.connect(str(temp_db))
    stored = json.loads(conn.execute("SELECT anchor_json FROM registry_timestamps").fetchone()[0])
    stored["tables"]["mandates"]["last_rowid"] = 5
    conn.execute(
        "UPDATE registry_timestamps SET anchor_json = ?",
        (canonical(stored).decode(),),
    )
    conn.commit()
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["chain_integrity"]["timestamps_intact"] is False


def _rechain(conn: sqlite3.Connection) -> None:
    """What an operator who edits the timestamp table would do: recompute every hash."""
    conn.row_factory = sqlite3.Row
    previous = ""
    for row in [dict(r) for r in conn.execute("SELECT * FROM registry_timestamps ORDER BY rowid")]:
        new = compute_hash(timestamp_hash_data(row), previous)
        conn.execute(
            "UPDATE registry_timestamps SET chain_hash = ? WHERE anchor_sha256 = ?",
            (new, row["anchor_sha256"]),
        )
        previous = new
    conn.commit()


async def test_an_edited_date_with_a_recomputed_chain_is_detected(
    trusted: Path, temp_db: Path
) -> None:
    """The date and the service shown come from the signed response, not the columns."""
    mandate = await _registry()
    recorded = await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.execute("UPDATE registry_timestamps SET gen_time = '2020-01-01T00:00:00+00:00', tsa = 'X'")
    _rechain(conn)
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    [stamp] = proof["registry_timestamps"]
    assert stamp["gen_time"] == recorded["gen_time"]
    assert stamp["tsa"] == recorded["tsa"]
    assert stamp["response_matches"] is False
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_a_rebuilt_anchor_is_detected_without_trust_roots(
    trusted: Path, temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edit a mandate, rebuild the stored anchor, its key and the chain: the stored
    response still dates the original anchor, and that is checked without roots."""
    mandate = await _registry()
    await _record(await _stamp())
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", None)
    conn = sqlite3.connect(str(temp_db))
    conn.execute("UPDATE mandates SET scope = 'Write and send consultation notes'")
    conn.commit()
    conn.close()
    import aiosqlite

    from amr.registry_timestamp import compute_anchor

    async with aiosqlite.connect(str(temp_db)) as db:
        db.row_factory = aiosqlite.Row
        fresh = await compute_anchor(db, datetime.now(UTC))
    conn = sqlite3.connect(str(temp_db))
    old = json.loads(conn.execute("SELECT anchor_json FROM registry_timestamps").fetchone()[0])
    old["tables"] = fresh["tables"]
    conn.execute(
        "UPDATE registry_timestamps SET anchor_json = ?, anchor_sha256 = ?",
        (canonical(old).decode(), anchor_sha256(old)),
    )
    _rechain(conn)
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    [stamp] = proof["registry_timestamps"]
    assert stamp["anchor_intact"] is True  # the rebuilt anchor matches the edited rows
    assert stamp["response_matches"] is False  # but the service never dated it
    assert stamp["signature_valid"] is None
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_a_stored_key_that_does_not_name_its_anchor_is_detected(
    trusted: Path, temp_db: Path
) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    conn = sqlite3.connect(str(temp_db))
    conn.execute("UPDATE registry_timestamps SET anchor_sha256 = ?", ("f" * 64,))
    _rechain(conn)
    conn.close()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"][0]["response_matches"] is True
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_unreadable_roots_at_proof_time_are_not_a_pass(
    trusted: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mandate = await _registry()
    await _record(await _stamp())
    broken = tmp_path / "broken.pem"
    broken.write_text("not a certificate")
    monkeypatch.setattr(settings, "timestamp_trust_roots_path", broken)
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"][0]["signature_valid"] is False
    assert proof["chain_integrity"]["timestamps_intact"] is False


async def test_the_anchor_escapes_accents_as_the_specification_says(temp_db: Path) -> None:
    await create_mandate(**{**BASE, "scope": "Rédiger les notes du médecin"})
    anchor = (await _prepare())["anchor"]
    conn = sqlite3.connect(str(temp_db))
    columns = ", ".join(ANCHOR_V1_COLUMNS["mandates"])
    rows = conn.execute(f"SELECT rowid, {columns} FROM mandates ORDER BY rowid").fetchall()  # noqa: S608
    conn.close()
    digest = hashlib.sha256()
    for row in rows:
        line = json.dumps(list(row), separators=(",", ":"), ensure_ascii=True)
        assert "\\u00e9" in line
        digest.update(hashlib.sha256(line.encode("ascii")).digest())
    assert anchor["tables"]["mandates"]["sha256"] == digest.hexdigest()


async def test_a_mandate_without_timestamp_is_unchanged() -> None:
    mandate = await _registry()
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["registry_timestamps"] == []
    assert proof["chain_integrity"]["timestamps_intact"] is None
    assert proof["chain_integrity"]["actions_chain_valid"] is True


# --- who may call it --------------------------------------------------------------


def test_only_the_principal_profile_has_the_timestamp_tools() -> None:
    for name in ("prepare_registry_timestamp", "record_registry_timestamp"):
        assert name in TOOL_PROFILES["principal"]
        assert name not in TOOL_PROFILES["agent"]
        assert name not in TOOL_PROFILES["receiver"]


def test_the_module_makes_no_network_call() -> None:
    root = Path(__file__).resolve().parent.parent / "src" / "amr"
    for path in (root / "registry_timestamp.py", root / "tools" / "registry_timestamp.py"):
        source = path.read_text(encoding="utf-8")
        for marker in ("urllib", "http.client", "requests", "aiohttp", "socket", "HTTPTimeStamper"):
            assert marker not in source, (path.name, marker)


def test_the_documentation_says_what_a_timestamp_does_not_show() -> None:
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    spec = (root / "docs" / "registry-timestamp-spec.md").read_text(encoding="utf-8")
    section = readme.split("### `prepare_registry_timestamp`")[1].split("\n---")[0]
    for text in (section, spec):
        assert "what it does not show" in text.lower()
        assert "AMR makes no network call" in text or "AMR never contacts" in text
        for word in ("opposable", "compliant", "conforme", "legally binding"):
            assert word not in text.lower(), word
        assert "does not say whether a service is qualified" in " ".join(text.split())
