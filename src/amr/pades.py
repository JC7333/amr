"""Check a PAdES signature the principal made on the mandate PDF (prepare_mandate_pdf).

The principal signs the PDF of prepare_mandate_pdf with its own tool, which appends
its signature to the file (an incremental update). This module checks, offline:

1. the signed file starts with the exact bytes of the mandate PDF, rebuilt here from
   the mandate content attached to it (amr-mandate.json): the signature is on this
   mandate and on nothing else;
2. every revision added after the mandate PDF only adds signatures (and validation
   data): no page, text or attachment was changed before or after signing;
3. every signature is intact, cryptographically valid, covers its whole revision,
   and its certificate chains to one of the operator's trust roots
   (AMR_PDF_TRUST_ROOTS_PATH, a PEM file), at the time of the check.

It reports what the signer's certificate declares (names, organisation identifier,
qualified-certificate statements of ETSI EN 319 412-5); it does not read the EU
trusted lists itself, makes no network call and does not check revocation (no OCSP,
no CRL download): whether a root is a qualified trust service is the operator's
choice of trust roots.
"""

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from asn1crypto import core
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.diff_analysis import DEFAULT_DIFF_POLICY, ModificationLevel
from pyhanko.sign.diff_analysis.policy_api import SuspiciousModification
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko.sign.validation.status import SignatureCoverageLevel
from pyhanko_certvalidator import ValidationContext

from amr.crypto.principal import PrincipalSignatureError
from amr.mandate_pdf import ATTACHMENT_NAME, build_mandate_pdf

MAX_SIGNED_PDF_BYTES = 8 * 1024 * 1024
MAX_SIGNATURES = 10
_WEAK_DIGESTS = frozenset({"md2", "md5", "sha1"})  # also refused by pyHanko's chain checks

_QC_STATEMENTS_OID = "1.3.6.1.5.5.7.1.3"  # RFC 3739
_QC_COMPLIANCE = "0.4.0.1862.1.1"  # ETSI EN 319 412-5: EU qualified certificate
_QC_SSCD = "0.4.0.1862.1.4"  # private key in a qualified signature creation device
_QC_TYPE = "0.4.0.1862.1.6"
_QC_TYPES = {
    "0.4.0.1862.1.6.1": "esign",
    "0.4.0.1862.1.6.2": "eseal",
    "0.4.0.1862.1.6.3": "web",
}

# pyHanko logs every failed path building with a traceback; the result says it already.
logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)


class PadesError(Exception):
    """A signed mandate PDF refused, with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TrustRoots:
    """The operator's trust roots and the SHA-256 that names this exact set."""

    certificates: tuple[asn1_x509.Certificate, ...]
    sha256: str


class _QcStatement(core.Sequence):
    _fields = [
        ("statement_id", core.ObjectIdentifier),
        ("statement_info", core.Any, {"optional": True}),
    ]


class _QcStatements(core.SequenceOf):
    _child_spec = _QcStatement


class _QcTypes(core.SequenceOf):
    _child_spec = core.ObjectIdentifier


def load_trust_roots(path: Path | None) -> TrustRoots:
    """Read the operator's trust roots (PEM certificates) from path.

    Raises PadesError("pdf_trust_roots_missing") if no path is set, the file cannot be
    read or holds no certificate.
    """
    if path is None:
        raise PadesError(
            "pdf_trust_roots_missing",
            "set AMR_PDF_TRUST_ROOTS_PATH to a PEM file of the certificate authorities "
            "the registry trusts for signed mandate PDFs",
        )
    try:
        certificates = x509.load_pem_x509_certificates(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise PadesError(
            "pdf_trust_roots_missing", f"cannot read trust roots from {path}: {exc}"
        ) from exc
    der = [cert.public_bytes(serialization.Encoding.DER) for cert in certificates]
    fingerprints = sorted({hashlib.sha256(item).hexdigest() for item in der})
    return TrustRoots(
        certificates=tuple(asn1_x509.Certificate.load(item) for item in der),
        sha256=hashlib.sha256("\n".join(fingerprints).encode("ascii")).hexdigest(),
    )


def _qc_statements(cert: asn1_x509.Certificate) -> dict[str, Any]:
    """The qualified-certificate statements a certificate declares (not checked here)."""
    found: dict[str, Any] = {"qc_compliance": False, "qc_sscd": False, "qc_types": []}
    for extension in cert["tbs_certificate"]["extensions"]:
        if extension["extn_id"].dotted != _QC_STATEMENTS_OID:
            continue
        try:
            statements = _QcStatements.load(extension["extn_value"].contents)
            for statement in statements:
                oid = statement["statement_id"].dotted
                if oid == _QC_COMPLIANCE:
                    found["qc_compliance"] = True
                elif oid == _QC_SSCD:
                    found["qc_sscd"] = True
                elif oid == _QC_TYPE and statement["statement_info"].contents:
                    types = _QcTypes.load(statement["statement_info"].dump())
                    found["qc_types"] = sorted(
                        _QC_TYPES.get(item.dotted, item.dotted) for item in types
                    )
        except (ValueError, TypeError):
            found = {"qc_compliance": False, "qc_sscd": False, "qc_types": []}
            found["qc_statements_unreadable"] = True
    return found


def _name(name: asn1_x509.Name) -> dict[str, str]:
    fields = (
        "common_name",
        "given_name",
        "surname",
        "serial_number",
        "organization_name",
        "organization_identifier",
        "country_name",
    )
    native = name.native
    return {field: str(native[field]) for field in fields if field in native}


def describe_certificate(cert: asn1_x509.Certificate) -> dict[str, Any]:
    """Who the certificate names, who issued it, and what it declares."""
    qc = _qc_statements(cert)
    if qc["qc_compliance"] and qc["qc_sscd"]:
        declared = "qualified_on_qscd"
    elif qc["qc_compliance"]:
        declared = "qualified"
    else:
        declared = "not_qualified"
    return {
        "subject": _name(cert.subject),
        "issuer": _name(cert.issuer),
        "certificate_sha256": cert.sha256.hex(),
        "serial": format(cert.serial_number, "x"),
        "not_valid_before": cert["tbs_certificate"]["validity"]["not_before"].native.isoformat(),
        "not_valid_after": cert["tbs_certificate"]["validity"]["not_after"].native.isoformat(),
        "qc_statements": qc,
        "declared_level": declared,
    }


def _mandate_payload(reader: PdfFileReader) -> bytes:
    """The amr-mandate.json attached to the first revision of the signed file."""
    try:
        root = reader.get_historical_resolver(0).root
        names = root["/Names"]["/EmbeddedFiles"]["/Names"]
        if len(names) != 2 or str(names[0]) != ATTACHMENT_NAME:
            raise PadesError("pdf_not_a_mandate", "the first revision has no amr-mandate.json")
        return names[1]["/EF"]["/F"].data
    except PadesError:
        raise
    except Exception as exc:
        raise PadesError(
            "pdf_not_a_mandate", "the first revision is not a mandate PDF of AMR"
        ) from exc


async def check_signed_mandate_pdf(signed_pdf: bytes, roots: TrustRoots) -> dict[str, Any]:
    """Check a signed mandate PDF; return the mandate payload and its signers.

    Returns {"payload": bytes, "pdf_sha256": unsigned PDF SHA-256, "signers": [...]},
    each signer with its certificate description, field name, signing time as the
    signer reports it (not a trusted time) and the modification level after it.
    Raises PadesError with code pdf_too_large, pdf_unreadable, pdf_not_a_mandate,
    pdf_not_signed, pdf_modified, document_timestamp_unsupported, signature_invalid or
    signer_not_trusted.
    """
    if len(signed_pdf) > MAX_SIGNED_PDF_BYTES:
        raise PadesError("pdf_too_large", f"signed PDF over {MAX_SIGNED_PDF_BYTES} bytes")
    try:
        reader = PdfFileReader(io.BytesIO(signed_pdf), strict=True)
        revisions = reader.xrefs.total_revisions
        signatures = list(reader.embedded_signatures)
    except Exception as exc:
        raise PadesError("pdf_unreadable", "the file is not a readable PDF") from exc

    payload = _mandate_payload(reader)
    try:
        original = build_mandate_pdf(payload)
    except PrincipalSignatureError as exc:
        raise PadesError("pdf_not_a_mandate", exc.message) from exc
    if not signed_pdf.startswith(original):
        # Rebuilt from its own attachment, the mandate PDF must be the start of the file:
        # a tool that rewrote the file instead of appending to it is refused too.
        raise PadesError(
            "pdf_not_a_mandate",
            "the file does not start with the exact mandate PDF of prepare_mandate_pdf "
            "(was it rewritten instead of signed in an incremental update?)",
        )
    # The reader builds revisions by following /Prev back from the end of the file: a
    # whole second document appended after the mandate PDF, with no /Prev, would become
    # "revision 0" and the mandate bytes dead bytes. Revision 0 must be the mandate PDF.
    mandate_xref = int(re.search(rb"startxref\n(\d+)\n%%EOF\n$", original).group(1))
    try:
        first_xref = reader.xrefs.get_startxref_for_revision(0)
    except Exception as exc:
        raise PadesError("pdf_unreadable", "the revisions of the file cannot be read") from exc
    if first_xref != mandate_xref:
        raise PadesError(
            "pdf_modified", "the first revision of the file is not the mandate PDF"
        )
    if not signatures or revisions < 2:
        raise PadesError("pdf_not_signed", "the PDF carries no signature")
    if any(signature.sig_object_type != "/Sig" for signature in signatures):
        raise PadesError(
            "document_timestamp_unsupported",
            "document timestamps (PAdES-B-LTA) are not checked in this version",
        )
    if min(signature.signed_revision for signature in signatures) != 1:
        # Nothing unsigned between the mandate PDF and the first signature (for example
        # a signature field prepared in advance with its own appearance).
        raise PadesError(
            "pdf_modified", "the first signature is not the first update of the mandate PDF"
        )
    if len(signatures) > MAX_SIGNATURES:
        raise PadesError("pdf_too_large", f"more than {MAX_SIGNATURES} signatures")

    # Everything appended to the mandate PDF, revision by revision, may only add
    # signature fields (and validation data): a page or the attachment changed before
    # the first signature would be signed without being the mandate.
    try:
        review = DEFAULT_DIFF_POLICY.review_file(reader, 0)
    except Exception as exc:
        raise PadesError("pdf_modified", "the revisions after the mandate cannot be read") from exc
    if isinstance(review, SuspiciousModification):
        raise PadesError("pdf_modified", f"the mandate PDF was modified: {review}")
    if review.modification_level > ModificationLevel.FORM_FILLING:
        raise PadesError("pdf_modified", "the mandate PDF was modified beyond signing")
    field_names = {signature.field_name for signature in signatures}
    if not set(review.changed_form_fields) <= field_names:
        raise PadesError("pdf_modified", "a form field other than a signature was filled")

    context = ValidationContext(
        trust_roots=list(roots.certificates),
        allow_fetching=False,
        revocation_mode="soft-fail",
    )
    signers = []
    for signature in signatures:
        try:
            status = await async_validate_pdf_signature(signature, context)
        except Exception as exc:
            raise PadesError("signature_invalid", "a signature cannot be checked") from exc
        if not (status.intact and status.valid) or status.md_algorithm in _WEAK_DIGESTS:
            raise PadesError(
                "signature_invalid",
                f"signature {signature.field_name} does not verify or uses a weak digest",
            )
        covered = status.coverage == SignatureCoverageLevel.ENTIRE_FILE or (
            status.coverage == SignatureCoverageLevel.ENTIRE_REVISION
            and status.modification_level is not None
            and status.modification_level <= ModificationLevel.FORM_FILLING
        )
        if not covered or status.docmdp_ok is False:
            raise PadesError(
                "pdf_modified", f"signature {signature.field_name} does not cover the document"
            )
        if not status.trusted:
            raise PadesError(
                "signer_not_trusted",
                f"the certificate of signature {signature.field_name} does not chain to "
                "a trust root of AMR_PDF_TRUST_ROOTS_PATH (or is expired)",
            )
        reported = status.signer_reported_dt
        signers.append(
            {
                "field_name": signature.field_name,
                "certificate": describe_certificate(status.signing_cert),
                "signer_reported_time": reported.isoformat() if reported else None,
                "modification_level_after": (
                    status.modification_level.name.lower()
                    if status.modification_level is not None
                    else None
                ),
            }
        )
    return {
        "payload": payload,
        "pdf_sha256": hashlib.sha256(original).hexdigest(),
        "signers": signers,
    }
