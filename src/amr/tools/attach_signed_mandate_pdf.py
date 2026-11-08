"""AMR tool: attach_signed_mandate_pdf - record a PAdES signature of the mandate PDF."""

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.principal import PrincipalSignatureError, parse_signed_at
from amr.db.engine import get_db, init_db
from amr.pades import (
    MAX_SIGNED_PDF_BYTES,
    PadesError,
    check_signed_mandate_pdf,
    load_trust_roots,
)
from amr.tools.get_proof import (
    PDF_SIGNATURE_EVENT,
    payload_matches_mandate,
    pdf_signature_hash_data,
)

# Base64 of MAX_SIGNED_PDF_BYTES, rounded up, before any decoding work.
_MAX_BASE64_CHARS = 4 * ((MAX_SIGNED_PDF_BYTES + 2) // 3)


class AttachSignedPdfRequest(BaseModel):
    """Input of attach_signed_mandate_pdf."""

    model_config = ConfigDict(extra="forbid")

    mandate_id: UUID
    signed_pdf_base64: str = Field(min_length=4, max_length=_MAX_BASE64_CHARS)


def _error(code: str, message: str) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code})


async def _parent_perimeter(db: aiosqlite.Connection, parent_id: str | None) -> str | None:
    if parent_id is None:
        return None
    cursor = await db.execute("SELECT perimeter_json FROM mandates WHERE id = ?", (parent_id,))
    row = await cursor.fetchone()
    return row["perimeter_json"] if row is not None else None


async def _describes(db: aiosqlite.Connection, mandate: Any, payload_text: str) -> bool:
    """True if the payload attached to the PDF is the content of this mandate."""
    if mandate["principal_signed_payload"] is not None:
        # A mandate the principal signed: the PDF must carry the very bytes it signed.
        return payload_text == mandate["principal_signed_payload"]
    view = {
        "principal_id": mandate["principal_id"],
        "agent_id": mandate["agent_id"],
        "scope": mandate["scope"],
        "legal_basis": json.loads(mandate["legal_basis_json"]),
        "parent_mandate_id": mandate["parent_mandate_id"],
        "metadata": json.loads(mandate["metadata_json"]),
        "perimeter": (
            json.loads(mandate["perimeter_json"]) if mandate["perimeter_json"] else None
        ),
        "created_at": mandate["created_at"],
        "expires_at": mandate["expires_at"],
    }
    parent_perimeter_json = await _parent_perimeter(db, mandate["parent_mandate_id"])
    try:
        if not payload_matches_mandate(view, payload_text, None, parent_perimeter_json):
            return False
        # The PDF was prepared for this registration: its signed_at is within the
        # signature window of the moment the mandate was created, so a PDF signed for
        # one mandate does not fit an identical mandate created later.
        signed_at = parse_signed_at(json.loads(payload_text)["signed_at"])
        created_at = datetime.fromisoformat(mandate["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        window = timedelta(seconds=settings.principal_signature_max_age_seconds)
        return abs(created_at - signed_at) <= window
    except (ValueError, TypeError, KeyError, AttributeError, PrincipalSignatureError):
        return False


async def attach_signed_mandate_pdf(mandate_id: str, signed_pdf_base64: str) -> str:
    """Check a PAdES signature of the mandate PDF and record who the certificate names.

    The principal signs the PDF of prepare_mandate_pdf with its own tool (for example
    with a qualified certificate) and anyone passes the signed file here, after
    create_mandate. The registry checks, offline: the file starts with the exact
    mandate PDF and its attached content is this mandate (for a mandate the principal
    signed with its Ed25519 key, the very bytes it signed; otherwise the same content,
    prepared within AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS of the mandate's creation,
    and not already recorded for another mandate); everything appended only
    adds signatures; every signature verifies, covers the document and its certificate
    chains to a trust root of AMR_PDF_TRUST_ROOTS_PATH at the time of the check. It
    records the signed file, the signers and the SHA-256 of the trust roots used,
    chained with SHA-256 and shown by get_proof.

    What it does not check: the EU trusted lists (the operator chooses the trust roots),
    certificate revocation (no OCSP or CRL, no network call), that the signer is the
    principal or may act for it (compare signers[].certificate.subject yourself). The
    declared_level is what the certificate declares under these roots.

    Args:
        mandate_id: UUID of the registered mandate.
        signed_pdf_base64: The signed PDF, standard base64 (at most 8 MiB once decoded).

    Returns:
        JSON string with keys: status ("attached"), mandate_id, payload_sha256,
        pdf_sha256 (the unsigned mandate PDF), signed_pdf_sha256, signers (list of
        {field_name, certificate {subject, issuer, certificate_sha256, serial,
        not_valid_before, not_valid_after, qc_statements, declared_level},
        signer_reported_time, modification_level_after}), trust_roots_sha256,
        checked_at, revocation_checked (false), chain_hash.
        On error: {"error": "...", "code": "..."} with code invalid_input,
        pdf_trust_roots_missing, pdf_too_large, pdf_unreadable, pdf_not_a_mandate,
        pdf_not_signed, pdf_modified, signature_invalid, signer_not_trusted,
        document_timestamp_unsupported, mandate_not_found, pdf_not_this_mandate,
        pdf_used_by_another_mandate or pdf_already_attached.
    """
    db = None
    try:
        try:
            req = AttachSignedPdfRequest(
                mandate_id=mandate_id,  # type: ignore[arg-type]
                signed_pdf_base64=signed_pdf_base64,
            )
            signed_pdf = base64.b64decode(req.signed_pdf_base64, validate=True)
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"])
        except (binascii.Error, ValueError):
            return _error("invalid_input", "signed_pdf_base64 is not standard base64")
        canonical_id = str(req.mandate_id)

        roots = load_trust_roots(settings.pdf_trust_roots_path)
        checked = await check_signed_mandate_pdf(signed_pdf, roots)
        payload: bytes = checked["payload"]
        try:
            payload_text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return _error("pdf_not_a_mandate", "the attached content is not UTF-8")

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        cursor = await db.execute(
            """
            SELECT id, principal_id, agent_id, scope, legal_basis_json, created_at,
                   expires_at, parent_mandate_id, metadata_json, chain_hash,
                   perimeter_json, principal_signed_payload
            FROM mandates WHERE id = ?
            """,
            (canonical_id,),
        )
        mandate = await cursor.fetchone()
        if mandate is None:
            return _error("mandate_not_found", f"no mandate '{canonical_id}'")
        if not await _describes(db, mandate, payload_text):
            return _error(
                "pdf_not_this_mandate", "the signed PDF describes another mandate"
            )

        checked_at = datetime.now(UTC).isoformat()
        row: dict[str, Any] = {
            "mandate_id": canonical_id,
            "mandate_chain_hash": mandate["chain_hash"],
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "pdf_sha256": checked["pdf_sha256"],
            "signed_pdf_sha256": hashlib.sha256(signed_pdf).hexdigest(),
            "signers_json": json.dumps(checked["signers"], sort_keys=True),
            "trust_roots_sha256": roots.sha256,
            "checked_at": checked_at,
        }
        # One writer at a time: two attachments must not chain to the same previous hash.
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT chain_hash FROM mandate_pdf_signatures ORDER BY rowid DESC LIMIT 1"
        )
        previous = await cursor.fetchone()
        cursor = await db.execute(
            "SELECT 1 FROM mandate_pdf_signatures WHERE payload_sha256 = ? AND mandate_id != ? "
            "LIMIT 1",
            (row["payload_sha256"], canonical_id),
        )
        if await cursor.fetchone() is not None:
            await db.rollback()
            return _error(
                "pdf_used_by_another_mandate",
                "this mandate content was already signed for another mandate",
            )
        chain_hash = compute_hash(
            pdf_signature_hash_data(row), previous["chain_hash"] if previous else ""
        )
        await db.execute(
            """
            INSERT INTO mandate_pdf_signatures
              (mandate_id, mandate_chain_hash, payload_sha256, pdf_sha256,
               signed_pdf_sha256, signed_pdf, signers_json, trust_roots_sha256,
               checked_at, chain_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["mandate_id"],
                row["mandate_chain_hash"],
                row["payload_sha256"],
                row["pdf_sha256"],
                row["signed_pdf_sha256"],
                signed_pdf,
                row["signers_json"],
                row["trust_roots_sha256"],
                row["checked_at"],
                chain_hash,
            ),
        )
        await db.execute(
            """
            INSERT INTO mandate_events (mandate_id, event_type, timestamp, reason)
            VALUES (?, ?, ?, ?)
            """,
            (
                canonical_id,
                PDF_SIGNATURE_EVENT,
                checked_at,
                f"signed PDF {row['signed_pdf_sha256']}",
            ),
        )
        await db.commit()

        return json.dumps(
            {
                "status": "attached",
                "mandate_id": canonical_id,
                "payload_sha256": row["payload_sha256"],
                "pdf_sha256": row["pdf_sha256"],
                "signed_pdf_sha256": row["signed_pdf_sha256"],
                "signers": checked["signers"],
                "trust_roots_sha256": roots.sha256,
                "checked_at": checked_at,
                "revocation_checked": False,
                "chain_hash": chain_hash,
            }
        )

    except PadesError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError as exc:
        if "mandate_pdf_signatures" in str(exc):
            return _error("pdf_already_attached", "this signed PDF is already recorded")
        return json.dumps({"error": str(exc)})

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
