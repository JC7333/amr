"""AMR tool: prepare_mandate_pdf - the mandate as a PDF the principal signs itself."""

import base64
import hashlib
import json
from typing import Any

from amr.crypto.principal import PrincipalSignatureError
from amr.mandate_pdf import ATTACHMENT_NAME, build_mandate_pdf
from amr.tools.principal_keys import prepare_mandate_signature


async def prepare_mandate_pdf(
    principal_id: str,
    agent_id: str,
    scope: str,
    legal_basis_regulation: str,
    legal_basis_article: str,
    duration_hours: float,
    legal_basis_jurisdiction: str = "EU",
    parent_mandate_id: str | None = None,
    metadata: dict[str, str] | None = None,
    allowed_actions: list[str] | None = None,
    forbidden_actions: list[str] | None = None,
    delegation_allowed: bool = False,
    max_amount: str | None = None,
    currency: str = "EUR",
    amount_actions: list[str] | None = None,
    signed_at: str | None = None,
    period_max_amount: str | None = None,
    period_days: int | None = None,
    risk_classes: list[dict[str, Any]] | None = None,
    max_delegation_depth: int | None = None,
) -> str:
    """Return the mandate as a PDF for the principal to sign with its own signature tool.

    Takes the same arguments as create_mandate (and prepare_mandate_signature). Nothing
    is written. The PDF shows the mandate and carries, as the attached file
    amr-mandate.json, the exact bytes prepare_mandate_signature returns for the same
    arguments and signed_at; the SHA-256 of these bytes is printed on every page.
    The same arguments and signed_at always give the same PDF.

    The registry does not sign this PDF: the principal signs it with its own tool (for
    example a PAdES signature), keeps the signed file and can record it, after
    create_mandate, with attach_signed_mandate_pdf. An agent cannot sign in the principal's
    place. create_mandate accepts signed_at only within
    AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS (default 900 s) of its clock: generate,
    sign and register within that window, or generate a new PDF. The PDF matches a
    mandate the principal signed only if it was created with the same arguments and
    signed_at; it matches a mandate created without that signature if its content
    describes it (attach_signed_mandate_pdf).

    Args:
        signed_at: ISO 8601 timestamp with timezone to place in the content.
                   Default: now (UTC). Pass the same value to create_mandate.
        (all other arguments: see create_mandate)

    Returns:
        JSON string with keys: pdf_base64 (standard base64 of the PDF), filename,
        pdf_sha256, attachment_name ("amr-mandate.json"), payload_sha256 (the value
        printed in the PDF), payload, payload_b64url, signed_at.
        On error: the same error as prepare_mandate_signature, or
        {"error": "...", "code": "mandate_pdf_too_large"} (content over 256 KiB or
        more than 200 pages).
    """
    prepared = json.loads(
        await prepare_mandate_signature(
            principal_id=principal_id,
            agent_id=agent_id,
            scope=scope,
            legal_basis_regulation=legal_basis_regulation,
            legal_basis_article=legal_basis_article,
            duration_hours=duration_hours,
            legal_basis_jurisdiction=legal_basis_jurisdiction,
            parent_mandate_id=parent_mandate_id,
            metadata=metadata,
            allowed_actions=allowed_actions,
            forbidden_actions=forbidden_actions,
            delegation_allowed=delegation_allowed,
            max_amount=max_amount,
            currency=currency,
            amount_actions=amount_actions,
            signed_at=signed_at,
            period_max_amount=period_max_amount,
            period_days=period_days,
            risk_classes=risk_classes,
            max_delegation_depth=max_delegation_depth,
        )
    )
    if "error" in prepared:
        return json.dumps(prepared)
    payload = prepared["payload"].encode("utf-8")
    try:
        pdf = build_mandate_pdf(payload)
    except PrincipalSignatureError as exc:
        return json.dumps({"error": f"{exc.code}: {exc.message}", "code": exc.code})
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    result: dict[str, Any] = {
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "filename": f"amr-mandate-{payload_sha256[:12]}.pdf",
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "attachment_name": ATTACHMENT_NAME,
        "payload_sha256": payload_sha256,
        "payload": prepared["payload"],
        "payload_b64url": prepared["payload_b64url"],
        "signed_at": prepared["signed_at"],
    }
    return json.dumps(result)
