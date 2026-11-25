"""AMR tools: prepare_registry_timestamp and record_registry_timestamp.

Have an outside time-stamping service (RFC 3161) date the state of the registry, so that
anyone can check later that the registry held these rows, unchanged, at that date. AMR
prepares the request and checks the response; the operator sends the request to the
service of their choice. AMR makes no network call. See docs/registry-timestamp-spec.md.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.db.engine import get_db, init_db
from amr.models.timestamp import RecordTimestampRequest
from amr.registry_timestamp import (
    TimestampError,
    anchor_intact,
    anchor_sha256,
    canonical,
    check_anchor_shape,
    check_timestamp_response,
    compute_anchor,
    decode_response,
    load_timestamp_trust_roots,
    timestamp_request,
)
from amr.tool_errors import validation_field

_INSERT_TIMESTAMP = """
INSERT INTO registry_timestamps (
    anchor_sha256, anchor_json, response_der, gen_time, tsa, serial_number, policy,
    trust_roots_sha256, recorded_at, chain_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_TIMESTAMPS = (
    "SELECT anchor_sha256, anchor_json, response_der, gen_time, tsa, serial_number, "
    "policy, trust_roots_sha256, recorded_at, chain_hash "
    "FROM registry_timestamps ORDER BY rowid ASC"
)


def _error(code: str, message: str, field: str | None = None) -> str:
    return json.dumps({"error": message, "code": code, "field": field})


def timestamp_hash_data(row: dict[str, Any]) -> dict[str, Any]:
    """The fields sealed in a registry timestamp's chain_hash, from its stored row."""
    return {
        "anchor_sha256": row["anchor_sha256"],
        "response_sha256": hashlib.sha256(bytes(row["response_der"])).hexdigest(),
        "gen_time": row["gen_time"],
        "tsa": row["tsa"],
        "serial_number": row["serial_number"],
        "policy": row["policy"],
        "trust_roots_sha256": row["trust_roots_sha256"],
        "recorded_at": row["recorded_at"],
    }


async def registry_timestamps(db: aiosqlite.Connection) -> tuple[list[dict[str, Any]], bool]:
    """Every recorded timestamp, oldest first, and whether their chain recomputes.

    A row whose anchor no longer hashes to its anchor_sha256 breaks the chain too."""
    cursor = await db.execute(_SELECT_TIMESTAMPS)
    rows = [dict(row) for row in await cursor.fetchall()]
    previous = ""
    intact = True
    for row in rows:
        try:
            anchor = json.loads(row["anchor_json"])
            sealed = anchor_sha256(anchor) == row["anchor_sha256"]
            expected = compute_hash(timestamp_hash_data(row), previous)
        except (TypeError, ValueError, KeyError):
            sealed, expected = False, ""
        if not sealed or expected != row["chain_hash"]:
            intact = False
        previous = row["chain_hash"]
    return rows, intact


async def mandate_timestamps(
    db: aiosqlite.Connection, mandate_id: str
) -> tuple[list[dict[str, Any]], bool | None]:
    """The timestamps that cover a mandate (its row was anchored), each re-checked.

    Returns (records, timestamps_intact). timestamps_intact is None when no timestamp
    covers the mandate and the registry's timestamp chain is whole; False when a
    covering anchor no longer matches the registry, a stored response does not date
    its stored anchor or disagrees with its stored columns, a signature no longer
    verifies against the operator's roots (or the roots file cannot be read), a stored
    anchor is malformed, or the timestamp chain is broken; True otherwise. Date,
    service and serial number shown are read from the signed response.
    """
    rows, chain_ok = await registry_timestamps(db)
    cursor = await db.execute("SELECT rowid AS r FROM mandates WHERE id = ?", (mandate_id,))
    found = await cursor.fetchone()
    roots_unreadable = False
    try:
        roots = load_timestamp_trust_roots(settings.timestamp_trust_roots_path)
    except TimestampError:
        roots, roots_unreadable = None, True
    records: list[dict[str, Any]] = []
    intact: bool | None = None if chain_ok else False
    for row in rows:
        try:
            anchor = check_anchor_shape(json.loads(row["anchor_json"]))
        except (TimestampError, TypeError, ValueError):
            intact = False
            continue
        if found is None or found["r"] > anchor["tables"]["mandates"]["last_rowid"]:
            continue
        cursor = await db.execute(
            "SELECT COUNT(*) AS n FROM action_logs WHERE mandate_id = ? AND rowid <= ?",
            (mandate_id, anchor["tables"]["action_logs"]["last_rowid"]),
        )
        actions_covered = int((await cursor.fetchone())["n"])
        still = await anchor_intact(db, anchor)
        # Read again from the signed response, never from the editable columns: the
        # response must date this stored anchor (imprint, nonce, date), whether or not
        # trust roots are set, and say what the columns say.
        der = bytes(row["response_der"])
        try:
            signed = await check_timestamp_response(der, anchor, None)
        except TimestampError:
            signed = None
        response_matches = signed is not None and all(
            signed[key] == row[key] for key in ("gen_time", "tsa", "serial_number", "policy")
        )
        signature_valid: bool | None = False if roots_unreadable else None
        if roots is not None:
            try:
                await check_timestamp_response(der, anchor, roots)
                signature_valid = True
            except TimestampError:
                signature_valid = False
        records.append(
            {
                "anchor_sha256": row["anchor_sha256"],
                "gen_time": signed["gen_time"] if signed else None,
                "tsa": signed["tsa"] if signed else None,
                "serial_number": signed["serial_number"] if signed else None,
                "recorded_at": row["recorded_at"],
                "actions_covered": actions_covered,
                "anchor_intact": still,
                "response_matches": response_matches,
                "signature_valid": signature_valid,
                "timestamp_response": base64.b64encode(bytes(row["response_der"])).decode(),
                "anchor": anchor,
            }
        )
        if not still or not response_matches or signature_valid is False:
            intact = False
        elif intact is None:
            intact = True
    return records, intact


async def prepare_registry_timestamp() -> str:
    """Prepare a request for an outside time-stamping service to date the registry.

    For the operator of the registry (profile principal). Computes an anchor of the
    registry as it is now: for each append-only table (mandates, action log, tokens,
    revocations, contests, receipts, keys and the others), how many rows it holds and a
    SHA-256 over them. Returns the anchor and an RFC 3161 time-stamp request whose
    message imprint is the anchor's SHA-256. Nothing is recorded and nothing is sent:
    send the request yourself to the time-stamping service you chose (HTTP POST,
    Content-Type application/timestamp-query), then give its response and this anchor
    to record_registry_timestamp. Only a digest leaves the registry, never its content.

    Returns:
        JSON string: {anchor (give it back unchanged), anchor_sha256, timestamp_request
        (base64 DER TimeStampReq), content_type, rows_anchored}. Refused:
        {error, code, field}; code is registry_unavailable or internal_error.
    """
    db = None
    try:
        # Never create a registry here: dating an empty file proves nothing.
        if not settings.db_path.resolve().is_file():
            return _error("registry_unavailable", "no registry database at the configured path")
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        await db.execute("BEGIN")  # one consistent read of every table
        anchor = await compute_anchor(db, datetime.now(UTC))
        await db.rollback()
        return json.dumps(
            {
                "anchor": anchor,
                "anchor_sha256": anchor_sha256(anchor),
                "timestamp_request": base64.b64encode(timestamp_request(anchor)).decode(),
                "content_type": "application/timestamp-query",
                "rows_anchored": {
                    table: entry["rows"] for table, entry in anchor["tables"].items()
                },
            }
        )
    except Exception as exc:
        return _error("internal_error", f"cannot prepare the timestamp: {type(exc).__name__}")
    finally:
        if db is not None:
            await db.close()


async def record_registry_timestamp(anchor_json: str, timestamp_response: str) -> str:
    """Record an outside time-stamping service's response dating the registry.

    For the operator of the registry (profile principal), after
    prepare_registry_timestamp and sending its request to the service. The response
    must be a granted RFC 3161 TimeStampResp for this anchor (same SHA-256 imprint,
    same nonce), signed by a service whose certificate chains to a trust root of
    AMR_TIMESTAMP_TRUST_ROOTS_PATH at the date it gives; and the registry must still
    hold exactly the rows anchored. Kept append-only and chained (SHA-256);
    get_proof then shows, for a mandate, the timestamps that cover it, re-checked.

    What a timestamp shows: the registry held these rows, unchanged, at the service's
    date; a row changed afterwards is detected. What it does not show: that what the
    rows say is true. AMR does not check revocation of the service's certificate.

    Args:
        anchor_json: The anchor returned by prepare_registry_timestamp, as JSON.
        timestamp_response: The service's response (DER TimeStampResp), base64.

    Returns:
        JSON string. Recorded: {status: "recorded", anchor_sha256, gen_time, tsa,
        serial_number, rows_anchored, recorded_at, chain_hash}. Refused:
        {error, code, field}; code is invalid_input, anchor_invalid,
        timestamp_trust_roots_missing, timestamp_malformed, timestamp_not_granted,
        timestamp_imprint_mismatch, timestamp_nonce_mismatch, timestamp_before_anchor,
        timestamp_signature_invalid, timestamp_signer_not_trusted, registry_unavailable,
        anchor_mismatch, timestamp_already_recorded or internal_error.
    """
    db = None
    try:
        try:
            req = RecordTimestampRequest(
                anchor_json=anchor_json, timestamp_response=timestamp_response
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            return _error("invalid_input", f"Invalid input: {first['msg']}", validation_field(exc))
        try:
            anchor = check_anchor_shape(json.loads(req.anchor_json))
        except ValueError:
            return _error("anchor_invalid", "anchor_json is not JSON", "anchor_json")
        roots = load_timestamp_trust_roots(settings.timestamp_trust_roots_path)
        if roots is None:
            return _error(
                "timestamp_trust_roots_missing",
                "set AMR_TIMESTAMP_TRUST_ROOTS_PATH to a PEM file of the certificate "
                "authorities of the time-stamping services you trust",
            )
        response_der = decode_response(req.timestamp_response)
        checked = await check_timestamp_response(response_der, anchor, roots)

        if not settings.db_path.resolve().is_file():
            return _error("registry_unavailable", "no registry database at the configured path")
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        # One write transaction from the checks to the insert: the rows anchored cannot
        # change, and two records cannot chain to the same previous hash.
        await db.execute("BEGIN IMMEDIATE")
        if not await anchor_intact(db, anchor):
            return _error(
                "anchor_mismatch",
                "the registry does not hold the rows this anchor describes",
                "anchor_json",
            )
        digest = anchor_sha256(anchor)
        cursor = await db.execute(
            "SELECT 1 FROM registry_timestamps WHERE anchor_sha256 = ?", (digest,)
        )
        if await cursor.fetchone() is not None:
            return _error(
                "timestamp_already_recorded",
                "a timestamp for this anchor is already recorded",
                "anchor_json",
            )
        cursor = await db.execute(
            "SELECT chain_hash FROM registry_timestamps ORDER BY rowid DESC LIMIT 1"
        )
        last = await cursor.fetchone()
        row = {
            "anchor_sha256": digest,
            "response_der": response_der,
            "gen_time": checked["gen_time"],
            "tsa": checked["tsa"],
            "serial_number": checked["serial_number"],
            "policy": checked["policy"],
            "trust_roots_sha256": roots.sha256,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        chain_hash = compute_hash(timestamp_hash_data(row), last["chain_hash"] if last else "")
        await db.execute(
            _INSERT_TIMESTAMP,
            (
                digest,
                canonical(anchor).decode("utf-8"),
                response_der,
                row["gen_time"],
                row["tsa"],
                row["serial_number"],
                row["policy"],
                row["trust_roots_sha256"],
                row["recorded_at"],
                chain_hash,
            ),
        )
        await db.commit()
        return json.dumps(
            {
                "status": "recorded",
                "anchor_sha256": digest,
                "gen_time": row["gen_time"],
                "tsa": row["tsa"],
                "serial_number": row["serial_number"],
                "rows_anchored": {
                    table: entry["rows"] for table, entry in anchor["tables"].items()
                },
                "recorded_at": row["recorded_at"],
                "chain_hash": chain_hash,
            }
        )
    except TimestampError as exc:
        return _error(exc.code, exc.message, exc.field)
    except Exception as exc:
        return _error("internal_error", f"cannot record the timestamp: {type(exc).__name__}")
    finally:
        if db is not None:
            if db.in_transaction:
                await db.rollback()
            await db.close()
