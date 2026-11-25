"""Registry timestamps (RFC 3161): have an outside time-stamping service date the registry.

A registry its operator keeps is evidence its operator could rewrite. A time-stamping
authority (TSA) chosen by the operator can date a digest of the registry: anyone can
then check that the registry was in that exact state at that date, and that nothing
written up to then was changed afterwards.

What is dated is an anchor: for each append-only table, how many rows it held and a
SHA-256 over those rows (every column listed below, rowid order). The anchor's own
SHA-256 is the message imprint sent to the TSA. No content leaves the registry, only
that digest.

AMR never calls the TSA. prepare_registry_timestamp returns the request (DER, base64);
the operator sends it to the service of their choice with their own tools, then gives
the response to record_registry_timestamp, which checks it against the operator's trust
roots (AMR_TIMESTAMP_TRUST_ROOTS_PATH) and keeps it. No address is built in.

What a timestamp shows: the registry held these rows, in this state, at the service's
date. What it does not show: that what the rows say is true.

Standard library and the libraries AMR already uses for signed PDFs (asn1crypto,
pyhanko); no network call.
"""

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from asn1crypto import algos, cms, core, tsp
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from pyhanko.sign.validation.generic_cms import validate_tst_signed_data
from pyhanko_certvalidator import ValidationContext

# pyhanko_certvalidator logs every path it fails to build; a refusal says it already.
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)

ANCHOR_VERSION = 1

# A response whose date is earlier than the anchor by more than this is refused: the
# service cannot have dated a registry state before it was computed (clock skew allowed).
CLOCK_SKEW_SECONDS = 300

# Statuses of a TimeStampResp that carry a token (RFC 3161, section 2.4.2).
_GRANTED = {"granted", "granted_with_mods"}

# Version 1 of the anchor: each table and the exact columns it covers. Written out, not
# built, so every query below is a constant string. A later schema that adds a column
# keeps these lists: an anchor of version 1 is re-checked on the columns it covered.
ANCHOR_V1_COLUMNS: dict[str, tuple[str, ...]] = {
    "mandates": (
        "id",
        "principal_id",
        "agent_id",
        "scope",
        "legal_basis_json",
        "status",
        "created_at",
        "expires_at",
        "parent_mandate_id",
        "metadata_json",
        "chain_hash",
        "perimeter_json",
        "principal_signature",
        "principal_signed_at",
        "principal_key_id",
        "principal_signed_payload",
    ),
    "action_logs": (
        "id",
        "mandate_id",
        "agent_id",
        "action",
        "evidence",
        "result",
        "timestamp",
        "chain_hash",
    ),
    "mandate_events": (
        "id",
        "mandate_id",
        "event_type",
        "timestamp",
        "reason",
    ),
    "mandate_revocations": (
        "mandate_id",
        "principal_id",
        "reason",
        "revoked_at",
        "principal_signature",
        "principal_signed_at",
        "principal_key_id",
        "principal_signed_payload",
        "chain_hash",
    ),
    "issued_tokens": (
        "jti",
        "mandate_id",
        "agent_id",
        "action_hash",
        "scope_digest",
        "audience",
        "issued_at",
        "expires_at",
        "key_id",
    ),
    "principal_keys": (
        "principal_id",
        "public_key",
        "key_id",
        "proof_signature",
        "registered_at",
        "chain_hash",
    ),
    "issued_attestations": (
        "jti",
        "mandate_id",
        "agent_id",
        "audience",
        "issued_at",
        "expires_at",
        "key_id",
        "claims_digest",
    ),
    "token_amounts": (
        "jti",
        "mandate_id",
        "amount",
        "currency",
        "issued_at",
    ),
    "action_contests": (
        "action_id",
        "mandate_id",
        "action_chain_hash",
        "contested_by",
        "reason",
        "response_days",
        "contested_at",
        "respond_by",
        "principal_signature",
        "principal_signed_at",
        "principal_key_id",
        "principal_signed_payload",
        "chain_hash",
    ),
    "principal_key_domain_proofs": (
        "principal_id",
        "key_id",
        "document_url",
        "document_sha256",
        "document",
        "verified_at",
    ),
    "mandate_pdf_signatures": (
        "mandate_id",
        "mandate_chain_hash",
        "payload_sha256",
        "pdf_sha256",
        "signed_pdf_sha256",
        "signed_pdf",
        "signers_json",
        "trust_roots_sha256",
        "checked_at",
        "chain_hash",
    ),
    "action_log_tokens": (
        "action_id",
        "jti",
        "mandate_id",
        "action_hash",
    ),
    "token_validations": (
        "jti",
        "mandate_id",
        "action_type",
        "validated_by",
        "validated_content_sha256",
        "issued_at",
    ),
    "action_receipts": (
        "jti",
        "mandate_id",
        "agent_id",
        "action_hash",
        "audience",
        "outcome",
        "refusal_reason",
        "received_content_sha256",
        "recorded_at",
        "chain_hash",
    ),
}

# rowid, then the columns above, for the rows up to a given rowid, oldest first.
_ANCHOR_V1_SQL: dict[str, str] = {
    "mandates": (
        "SELECT rowid, id, principal_id, agent_id, scope, legal_basis_json, status, "
        "created_at, expires_at, parent_mandate_id, metadata_json, chain_hash, "
        "perimeter_json, principal_signature, principal_signed_at, principal_key_id, "
        "principal_signed_payload FROM mandates WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "action_logs": (
        "SELECT rowid, id, mandate_id, agent_id, action, evidence, result, timestamp, "
        "chain_hash FROM action_logs WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "mandate_events": (
        "SELECT rowid, id, mandate_id, event_type, timestamp, reason FROM "
        "mandate_events WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "mandate_revocations": (
        "SELECT rowid, mandate_id, principal_id, reason, revoked_at, "
        "principal_signature, principal_signed_at, principal_key_id, "
        "principal_signed_payload, chain_hash FROM mandate_revocations WHERE rowid <= ? "
        "ORDER BY rowid ASC"
    ),
    "issued_tokens": (
        "SELECT rowid, jti, mandate_id, agent_id, action_hash, scope_digest, audience, "
        "issued_at, expires_at, key_id FROM issued_tokens WHERE rowid <= ? ORDER BY "
        "rowid ASC"
    ),
    "principal_keys": (
        "SELECT rowid, principal_id, public_key, key_id, proof_signature, "
        "registered_at, chain_hash FROM principal_keys WHERE rowid <= ? ORDER BY rowid "
        "ASC"
    ),
    "issued_attestations": (
        "SELECT rowid, jti, mandate_id, agent_id, audience, issued_at, expires_at, "
        "key_id, claims_digest FROM issued_attestations WHERE rowid <= ? ORDER BY rowid "
        "ASC"
    ),
    "token_amounts": (
        "SELECT rowid, jti, mandate_id, amount, currency, issued_at FROM token_amounts "
        "WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "action_contests": (
        "SELECT rowid, action_id, mandate_id, action_chain_hash, contested_by, reason, "
        "response_days, contested_at, respond_by, principal_signature, "
        "principal_signed_at, principal_key_id, principal_signed_payload, chain_hash "
        "FROM action_contests WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "principal_key_domain_proofs": (
        "SELECT rowid, principal_id, key_id, document_url, document_sha256, document, "
        "verified_at FROM principal_key_domain_proofs WHERE rowid <= ? ORDER BY rowid "
        "ASC"
    ),
    "mandate_pdf_signatures": (
        "SELECT rowid, mandate_id, mandate_chain_hash, payload_sha256, pdf_sha256, "
        "signed_pdf_sha256, signed_pdf, signers_json, trust_roots_sha256, checked_at, "
        "chain_hash FROM mandate_pdf_signatures WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "action_log_tokens": (
        "SELECT rowid, action_id, jti, mandate_id, action_hash FROM action_log_tokens "
        "WHERE rowid <= ? ORDER BY rowid ASC"
    ),
    "token_validations": (
        "SELECT rowid, jti, mandate_id, action_type, validated_by, "
        "validated_content_sha256, issued_at FROM token_validations WHERE rowid <= ? "
        "ORDER BY rowid ASC"
    ),
    "action_receipts": (
        "SELECT rowid, jti, mandate_id, agent_id, action_hash, audience, outcome, "
        "refusal_reason, received_content_sha256, recorded_at, chain_hash FROM "
        "action_receipts WHERE rowid <= ? ORDER BY rowid ASC"
    ),
}

_LAST_ROWID_SQL: dict[str, str] = {
    "mandates": "SELECT COALESCE(MAX(rowid), 0) AS last FROM mandates",
    "action_logs": "SELECT COALESCE(MAX(rowid), 0) AS last FROM action_logs",
    "mandate_events": "SELECT COALESCE(MAX(rowid), 0) AS last FROM mandate_events",
    "mandate_revocations": "SELECT COALESCE(MAX(rowid), 0) AS last FROM mandate_revocations",
    "issued_tokens": "SELECT COALESCE(MAX(rowid), 0) AS last FROM issued_tokens",
    "principal_keys": "SELECT COALESCE(MAX(rowid), 0) AS last FROM principal_keys",
    "issued_attestations": "SELECT COALESCE(MAX(rowid), 0) AS last FROM issued_attestations",
    "token_amounts": "SELECT COALESCE(MAX(rowid), 0) AS last FROM token_amounts",
    "action_contests": "SELECT COALESCE(MAX(rowid), 0) AS last FROM action_contests",
    "principal_key_domain_proofs": (
        "SELECT COALESCE(MAX(rowid), 0) AS last FROM principal_key_domain_proofs"
    ),
    "mandate_pdf_signatures": "SELECT COALESCE(MAX(rowid), 0) AS last FROM mandate_pdf_signatures",
    "action_log_tokens": "SELECT COALESCE(MAX(rowid), 0) AS last FROM action_log_tokens",
    "token_validations": "SELECT COALESCE(MAX(rowid), 0) AS last FROM token_validations",
    "action_receipts": "SELECT COALESCE(MAX(rowid), 0) AS last FROM action_receipts",
}


class _TimeStampResp(core.Sequence):
    """RFC 3161 TimeStampResp, with the token optional as the RFC says (asn1crypto's
    own class requires it, so it cannot read a rejection)."""

    _fields = [
        ("status", tsp.PKIStatusInfo),
        ("time_stamp_token", cms.ContentInfo, {"optional": True}),
    ]


class TimestampError(Exception):
    """A registry timestamp refused, with a stable code."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


@dataclass(frozen=True)
class TimestampTrustRoots:
    """The operator's trust roots for time-stamping services, and the SHA-256 naming them."""

    certificates: tuple[asn1_x509.Certificate, ...]
    sha256: str


def load_timestamp_trust_roots(path: Path | None) -> TimestampTrustRoots | None:
    """Read the operator's trust roots (PEM certificates), or None if no path is set.

    Raises TimestampError("timestamp_trust_roots_missing") if the file cannot be read or
    holds no certificate.
    """
    if path is None:
        return None
    try:
        certificates = x509.load_pem_x509_certificates(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise TimestampError(
            "timestamp_trust_roots_missing",
            f"cannot read the time-stamping trust roots from {path}: {exc}",
        ) from exc
    der = [cert.public_bytes(serialization.Encoding.DER) for cert in certificates]
    fingerprints = sorted({hashlib.sha256(item).hexdigest() for item in der})
    return TimestampTrustRoots(
        certificates=tuple(asn1_x509.Certificate.load(item) for item in der),
        sha256=hashlib.sha256("\n".join(fingerprints).encode("ascii")).hexdigest(),
    )


def canonical(anchor: dict[str, Any]) -> bytes:
    """The bytes whose SHA-256 is the message imprint: sorted keys, no spaces."""
    return json.dumps(anchor, sort_keys=True, separators=(",", ":")).encode("utf-8")


def anchor_sha256(anchor: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(anchor)).hexdigest()


def _cell(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return {"hex": bytes(value).hex()}
    return value


async def _table_digest(db: aiosqlite.Connection, table: str, last_rowid: int) -> tuple[int, str]:
    """(rows, sha256) over the rows of a table up to last_rowid, in rowid order."""
    cursor = await db.execute(_ANCHOR_V1_SQL[table], (last_rowid,))
    digest = hashlib.sha256()
    rows = 0
    for row in await cursor.fetchall():
        line = json.dumps(
            [_cell(value) for value in tuple(row)], separators=(",", ":"), ensure_ascii=True
        )
        digest.update(hashlib.sha256(line.encode("utf-8")).digest())
        rows += 1
    return rows, digest.hexdigest()


async def compute_anchor(db: aiosqlite.Connection, now: datetime) -> dict[str, Any]:
    """The anchor of the registry as it is now, with a fresh nonce."""
    tables: dict[str, Any] = {}
    for table in ANCHOR_V1_COLUMNS:
        cursor = await db.execute(_LAST_ROWID_SQL[table])
        last_rowid = int((await cursor.fetchone())["last"])
        rows, digest = await _table_digest(db, table, last_rowid)
        tables[table] = {"last_rowid": last_rowid, "rows": rows, "sha256": digest}
    return {
        "anchor_version": ANCHOR_VERSION,
        "computed_at": now.isoformat(),
        # Sealed in the imprint and echoed by the service: a response to another
        # request cannot be attached to this anchor.
        "nonce": secrets.randbits(63),
        "tables": tables,
    }


def check_anchor_shape(anchor: Any) -> dict[str, Any]:
    """Validate an anchor given back by a client; raise TimestampError if malformed."""
    if not isinstance(anchor, dict) or set(anchor) != {
        "anchor_version",
        "computed_at",
        "nonce",
        "tables",
    }:
        raise TimestampError("anchor_invalid", "the anchor is not one AMR prepared", "anchor")
    if anchor["anchor_version"] != ANCHOR_VERSION or type(anchor["anchor_version"]) is not int:
        raise TimestampError("anchor_invalid", "unknown anchor version", "anchor")
    nonce = anchor["nonce"]
    if type(nonce) is not int or not 0 <= nonce < 2**63:
        raise TimestampError("anchor_invalid", "the anchor nonce is invalid", "anchor")
    try:
        computed_at = datetime.fromisoformat(anchor["computed_at"])
    except (TypeError, ValueError) as exc:
        raise TimestampError("anchor_invalid", "computed_at is not a date", "anchor") from exc
    if computed_at.tzinfo is None:
        raise TimestampError("anchor_invalid", "computed_at has no time zone", "anchor")
    tables = anchor["tables"]
    if not isinstance(tables, dict) or set(tables) != set(ANCHOR_V1_COLUMNS):
        raise TimestampError("anchor_invalid", "the anchor does not list every table", "anchor")
    for entry in tables.values():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"last_rowid", "rows", "sha256"}
            or type(entry["last_rowid"]) is not int
            or type(entry["rows"]) is not int
            or not 0 <= entry["rows"] <= entry["last_rowid"] < 2**63
            or not isinstance(entry["sha256"], str)
            or len(entry["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in entry["sha256"])
        ):
            raise TimestampError("anchor_invalid", "a table entry is malformed", "anchor")
    return anchor


async def anchor_intact(db: aiosqlite.Connection, anchor: dict[str, Any]) -> bool:
    """Whether the registry still holds, up to each anchored rowid, exactly what was
    anchored. False shows a row changed, deleted or inserted below an anchored rowid."""
    for table, entry in anchor["tables"].items():
        rows, digest = await _table_digest(db, table, entry["last_rowid"])
        if rows != entry["rows"] or digest != entry["sha256"]:
            return False
    return True


def timestamp_request(anchor: dict[str, Any]) -> bytes:
    """The RFC 3161 TimeStampReq (DER) for this anchor: SHA-256 imprint, its nonce,
    and the service's certificate requested in the response."""
    return tsp.TimeStampReq(
        {
            "version": "v1",
            "message_imprint": tsp.MessageImprint(
                {
                    "hash_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}),
                    "hashed_message": hashlib.sha256(canonical(anchor)).digest(),
                }
            ),
            "nonce": anchor["nonce"],
            "cert_req": True,
        }
    ).dump()


def _signer_certificate(signed_data: cms.SignedData) -> asn1_x509.Certificate | None:
    infos = signed_data["signer_infos"]
    if len(infos) != 1:
        return None
    sid = infos[0]["sid"]
    for choice in signed_data["certificates"] or []:
        if choice.name != "certificate":
            continue
        cert = choice.chosen
        if sid.name == "issuer_and_serial_number":
            if (
                cert.issuer == sid.chosen["issuer"]
                and cert.serial_number == sid.chosen["serial_number"].native
            ):
                return cert
        elif cert.key_identifier == sid.chosen.native:
            return cert
    return None


def _token_parts(response_der: bytes) -> tuple[cms.SignedData, tsp.TSTInfo]:
    try:
        response = _TimeStampResp.load(response_der, strict=True)
        status = response["status"]["status"].native
    except (ValueError, TypeError, KeyError) as exc:
        raise TimestampError(
            "timestamp_malformed", "not an RFC 3161 TimeStampResp", "timestamp_response"
        ) from exc
    if status not in _GRANTED:
        raise TimestampError(
            "timestamp_not_granted",
            f"the time-stamping service did not grant the request (status {status})",
            "timestamp_response",
        )
    try:
        token = response["time_stamp_token"]
        if not isinstance(token, cms.ContentInfo):  # absent (core.Void)
            raise ValueError("no token")
        if token["content_type"].native != "signed_data":
            raise ValueError("not signed data")
        signed_data = token["content"]
        tst_info = signed_data["encap_content_info"]["content"].parsed
        if not isinstance(tst_info, tsp.TSTInfo):
            raise ValueError("no TSTInfo")
        _ = tst_info.native  # parse every field now, so a malformed one fails here
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise TimestampError(
            "timestamp_malformed",
            "the response carries no valid time-stamp token",
            "timestamp_response",
        ) from exc
    return signed_data, tst_info


async def check_timestamp_response(
    response_der: bytes, anchor: dict[str, Any], roots: TimestampTrustRoots | None
) -> dict[str, Any]:
    """Check a TimeStampResp against an anchor and the operator's trust roots.

    Everything is read from the signed token. With roots None, every check except the
    signature and the certificate chain still runs (imprint, nonce, date, one signer
    carried in the response).

    Returns {gen_time, serial_number, policy, tsa} or raises TimestampError with code
    timestamp_malformed, timestamp_not_granted, timestamp_imprint_mismatch,
    timestamp_nonce_mismatch, timestamp_signature_invalid, timestamp_signer_not_trusted
    or timestamp_before_anchor.
    """
    signed_data, tst_info = _token_parts(response_der)
    imprint = tst_info["message_imprint"]
    expected = hashlib.sha256(canonical(anchor)).digest()
    if (
        imprint["hash_algorithm"]["algorithm"].native != "sha256"
        or imprint["hashed_message"].native != expected
    ):
        raise TimestampError(
            "timestamp_imprint_mismatch",
            "the response dates another digest than this anchor's",
            "timestamp_response",
        )
    if tst_info["nonce"].native != anchor["nonce"]:
        raise TimestampError(
            "timestamp_nonce_mismatch",
            "the response does not answer the request prepared for this anchor",
            "timestamp_response",
        )
    gen_time = tst_info["gen_time"].native
    computed_at = datetime.fromisoformat(anchor["computed_at"])
    if (computed_at - gen_time).total_seconds() > CLOCK_SKEW_SECONDS:
        raise TimestampError(
            "timestamp_before_anchor",
            "the service dates the anchor before it was computed",
            "timestamp_response",
        )
    signer = _signer_certificate(signed_data)
    if signer is None:
        raise TimestampError(
            "timestamp_signature_invalid",
            "the response does not carry the service's certificate (one signer expected)",
            "timestamp_response",
        )
    info = {
        "gen_time": gen_time.astimezone(UTC).isoformat(),
        "serial_number": str(tst_info["serial_number"].native),
        "policy": tst_info["policy"].dotted,
        "tsa": signer.subject.human_friendly,
    }
    if roots is None:
        return info
    context = ValidationContext(
        trust_roots=list(roots.certificates),
        allow_fetching=False,
        revocation_mode="soft-fail",
        moment=gen_time,
    )
    try:
        status = await validate_tst_signed_data(signed_data, context, lambda _alg: expected)
    except Exception as exc:
        raise TimestampError(
            "timestamp_signature_invalid",
            "the time-stamp signature cannot be checked",
            "timestamp_response",
        ) from exc
    if not (status.get("intact") and status.get("valid")):
        raise TimestampError(
            "timestamp_signature_invalid",
            "the time-stamp signature does not verify",
            "timestamp_response",
        )
    if status.get("trust_problem_indic") is not None:
        raise TimestampError(
            "timestamp_signer_not_trusted",
            "the service's certificate does not chain to a trust root of "
            "AMR_TIMESTAMP_TRUST_ROOTS_PATH (or was not valid at the date it gives)",
            "timestamp_response",
        )
    return info


def decode_response(value: str) -> bytes:
    """The DER bytes of a base64 TimeStampResp; raise TimestampError if not base64."""
    try:
        return base64.b64decode(value.strip(), validate=True)
    except (ValueError, TypeError) as exc:
        raise TimestampError(
            "timestamp_malformed", "timestamp_response is not base64", "timestamp_response"
        ) from exc
