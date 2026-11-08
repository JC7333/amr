"""Tests for attach_signed_mandate_pdf: the principal's PAdES signature of a mandate PDF."""

import base64
import io
import json
import socket
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers

from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.pades import _QcStatements, _QcTypes, load_trust_roots
from amr.server import mcp
from amr.tools.attach_signed_mandate_pdf import attach_signed_mandate_pdf
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.prepare_mandate_pdf import prepare_mandate_pdf
from amr.tools.principal_keys import register_principal_key

BASE = {
    "principal_id": "org:clinic",
    "agent_id": "agent:scheduler",
    "scope": "Book and cancel patient appointments (no clinical data)",
    "legal_basis_regulation": "Code civil",
    "legal_basis_article": "Art. 1984",
    "duration_hours": 24.0,
    "allowed_actions": ["calendar.book", "calendar.cancel"],
}
QUALIFIED = ("0.4.0.1862.1.1", "0.4.0.1862.1.4")


# --- a test certificate authority ------------------------------------------------------------


def _name(**attrs: str) -> x509.Name:
    oids = {
        "cn": NameOID.COMMON_NAME,
        "given": NameOID.GIVEN_NAME,
        "surname": NameOID.SURNAME,
        "serial": NameOID.SERIAL_NUMBER,
        "org": NameOID.ORGANIZATION_NAME,
        "org_id": NameOID.ORGANIZATION_IDENTIFIER,
        "country": NameOID.COUNTRY_NAME,
    }
    return x509.Name([x509.NameAttribute(oids[k], v) for k, v in attrs.items()])


def _qc_extension(statements: tuple[str, ...], qc_type: str | None) -> x509.UnrecognizedExtension:
    items = [{"statement_id": oid} for oid in statements]
    if qc_type is not None:
        items.append({"statement_id": "0.4.0.1862.1.6", "statement_info": _QcTypes([qc_type])})
    return x509.UnrecognizedExtension(
        x509.ObjectIdentifier("1.3.6.1.5.5.7.1.3"), _QcStatements(items).dump()
    )


class Authority:
    def __init__(self, name: str = "Test Qualified CA") -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.name = _name(cn=name, org="Test Trust Services", country="FR")
        now = datetime.now(UTC)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(self.name)
            .issuer_name(self.name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=10))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, True, True, False, False),
                critical=True,
            )
            .sign(self.key, hashes.SHA256())
        )

    def pem(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.PEM)

    def issue(
        self,
        subject: x509.Name | None = None,
        qc: tuple[str, ...] = QUALIFIED,
        qc_type: str | None = "0.4.0.1862.1.6.1",
        days: tuple[int, int] = (-1, 365),
        urls: bool = False,
    ) -> "Signer":
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        builder = (
            x509.CertificateBuilder()
            .subject_name(
                subject
                or _name(
                    cn="Jeanne Martin",
                    given="Jeanne",
                    surname="Martin",
                    serial="PNOFR-123456",
                    org="Clinique Test",
                    org_id="NTRFR-123456789",
                    country="FR",
                )
            )
            .issuer_name(self.name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now + timedelta(days=days[0]))
            .not_valid_after(now + timedelta(days=days[1]))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(True, True, False, False, False, False, False, False, False),
                critical=True,
            )
        )
        if qc:
            builder = builder.add_extension(_qc_extension(qc, qc_type), critical=False)
        if urls:
            # A real certificate names where to fetch its issuer and revocation data:
            # the registry must not follow these addresses.
            builder = builder.add_extension(
                x509.AuthorityInformationAccess(
                    [
                        x509.AccessDescription(
                            x509.oid.AuthorityInformationAccessOID.OCSP,
                            x509.UniformResourceIdentifier("http://ocsp.example.invalid"),
                        ),
                        x509.AccessDescription(
                            x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                            x509.UniformResourceIdentifier("http://ca.example.invalid/ca.crt"),
                        ),
                    ]
                ),
                critical=False,
            ).add_extension(
                x509.CRLDistributionPoints(
                    [
                        x509.DistributionPoint(
                            [x509.UniformResourceIdentifier("http://crl.example.invalid/c.crl")],
                            None,
                            None,
                            None,
                        )
                    ]
                ),
                critical=False,
            ).add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False
            )
        return Signer(key, builder.sign(self.key, hashes.SHA256()))


class Signer:
    def __init__(self, key: ec.EllipticCurvePrivateKey, cert: x509.Certificate) -> None:
        der_key = key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        self.cert = cert
        self.pyhanko = signers.SimpleSigner(
            signing_cert=asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
            signing_key=asn1_keys.PrivateKeyInfo.load(der_key),
            cert_registry=None,
        )

    async def seal(self, pdf: bytes, field: str = "Signature1", digest: str = "sha256") -> bytes:
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf))
        meta = signers.PdfSignatureMetadata(
            field_name=field, subfilter=fields.SigSeedSubFilter.PADES, md_algorithm=digest
        )
        return (await signers.async_sign_pdf(writer, meta, signer=self.pyhanko)).getvalue()


@pytest.fixture(scope="module")
def authority() -> Authority:
    return Authority()


@pytest.fixture(scope="module")
def signer(authority: Authority) -> Signer:
    return authority.issue()


@pytest.fixture
def roots(authority: Authority, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "roots.pem"
    path.write_bytes(authority.pem())
    monkeypatch.setattr("amr.config.settings.pdf_trust_roots_path", path)
    return path


# --- mandates and their PDFs ------------------------------------------------------------------


async def _pdf(**overrides) -> bytes:
    result = json.loads(await prepare_mandate_pdf(**{**BASE, **overrides}))
    assert "error" not in result, result
    return base64.b64decode(result["pdf_base64"])


async def _signed_mandate(principal_id: str = BASE["principal_id"]) -> tuple[str, bytes]:
    """A mandate the principal signed with its Ed25519 key, and its PDF."""
    key = ed25519.Ed25519PrivateKey.generate()
    public = b64url_encode(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
    )
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, public)))
    assert json.loads(await register_principal_key(principal_id, public, proof))["status"]
    now = datetime.now(UTC).isoformat()
    prepared = json.loads(
        await prepare_mandate_pdf(**{**BASE, "principal_id": principal_id, "signed_at": now})
    )
    created = json.loads(
        await create_mandate(
            **{**BASE, "principal_id": principal_id, "signed_at": now},
            principal_signature=b64url_encode(key.sign(prepared["payload"].encode())),
        )
    )
    assert "error" not in created, created
    return created["mandate_id"], base64.b64decode(prepared["pdf_base64"])


async def _plain_mandate(**overrides) -> tuple[str, bytes]:
    """A mandate registered without a principal signature, and a PDF of it."""
    created = json.loads(await create_mandate(**{**BASE, **overrides}))
    assert "error" not in created, created
    return created["mandate_id"], await _pdf(**overrides)


async def _attach(mandate_id: str, pdf: bytes) -> dict:
    return json.loads(await attach_signed_mandate_pdf(mandate_id, base64.b64encode(pdf).decode()))


def _sql(db: Path, query: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        return conn.execute(query, params).fetchall()


# --- accepted ---------------------------------------------------------------------------------


async def test_signed_pdf_of_a_signed_mandate_is_recorded(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = await signer.seal(pdf)
    result = await _attach(mandate_id, signed)
    assert result["status"] == "attached", result
    assert result["mandate_id"] == mandate_id
    assert result["revocation_checked"] is False
    assert result["trust_roots_sha256"] == load_trust_roots(roots).sha256
    (who,) = result["signers"]
    assert who["field_name"] == "Signature1"
    subject = who["certificate"]["subject"]
    assert subject["surname"] == "Martin"
    assert subject["given_name"] == "Jeanne"
    assert subject["organization_identifier"] == "NTRFR-123456789"
    assert who["certificate"]["issuer"]["common_name"] == "Test Qualified CA"
    assert who["certificate"]["declared_level"] == "qualified_on_qscd"
    assert who["certificate"]["qc_statements"]["qc_types"] == ["esign"]
    assert who["signer_reported_time"] is not None

    proof = json.loads(await get_proof(mandate_id))
    assert proof["chain_integrity"]["pdf_signatures_intact"] is True
    (record,) = proof["pdf_signatures"]
    assert record["signed_pdf_sha256"] == result["signed_pdf_sha256"]
    assert record["signers"] == result["signers"]
    assert record["chain_hash"] == result["chain_hash"]
    assert [e["event_type"] for e in proof["events"]].count("pdf_signature_attached") == 1


async def test_mandate_without_principal_key_matches_on_its_content(
    roots: Path, signer: Signer
) -> None:
    mandate_id, pdf = await _plain_mandate()
    result = await _attach(mandate_id, await signer.seal(pdf))
    assert result["status"] == "attached", result
    proof = json.loads(await get_proof(mandate_id))
    assert proof["chain_integrity"]["pdf_signatures_intact"] is True


async def test_two_signers_are_both_recorded(roots: Path, authority: Authority) -> None:
    mandate_id, pdf = await _signed_mandate()
    first = authority.issue()
    second = authority.issue(subject=_name(cn="Paul Durand", surname="Durand"), qc=())
    signed = await second.seal(await first.seal(pdf, "Director"), "Secretary")
    result = await _attach(mandate_id, signed)
    assert result["status"] == "attached", result
    assert [s["field_name"] for s in result["signers"]] == ["Director", "Secretary"]
    assert [s["certificate"]["declared_level"] for s in result["signers"]] == [
        "qualified_on_qscd",
        "not_qualified",
    ]


@pytest.mark.parametrize(
    ("qc", "qc_type", "level"),
    [
        (QUALIFIED, "0.4.0.1862.1.6.2", "qualified_on_qscd"),
        (("0.4.0.1862.1.1",), None, "qualified"),
        (("0.4.0.1862.1.4",), None, "not_qualified"),
        ((), None, "not_qualified"),
    ],
)
async def test_declared_level_reads_the_qc_statements(
    roots: Path, authority: Authority, qc: tuple, qc_type: str | None, level: str
) -> None:
    mandate_id, pdf = await _signed_mandate()
    result = await _attach(mandate_id, await authority.issue(qc=qc, qc_type=qc_type).seal(pdf))
    certificate = result["signers"][0]["certificate"]
    assert certificate["declared_level"] == level
    assert certificate["qc_statements"]["qc_compliance"] is ("0.4.0.1862.1.1" in qc)
    assert certificate["qc_statements"]["qc_sscd"] is ("0.4.0.1862.1.4" in qc)
    if qc_type == "0.4.0.1862.1.6.2":
        assert certificate["qc_statements"]["qc_types"] == ["eseal"]


async def test_no_network_call_even_when_the_certificate_names_urls(
    roots: Path, authority: Authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = await authority.issue(urls=True).seal(pdf)
    calls: list = []

    def refuse(*args, **kwargs):
        calls.append(args)
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    result = await _attach(mandate_id, signed)
    assert result["status"] == "attached", result
    assert calls == []


# --- refused ----------------------------------------------------------------------------------


async def test_without_trust_roots_nothing_is_accepted(signer: Signer, temp_db: Path) -> None:
    mandate_id, pdf = await _signed_mandate()
    result = await _attach(mandate_id, await signer.seal(pdf))
    assert result["code"] == "pdf_trust_roots_missing"
    assert _sql(temp_db, "SELECT COUNT(*) FROM mandate_pdf_signatures") == [(0,)]


async def test_unreadable_trust_roots_are_refused(
    signer: Signer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "roots.pem"
    path.write_text("not a certificate")
    monkeypatch.setattr("amr.config.settings.pdf_trust_roots_path", path)
    mandate_id, pdf = await _signed_mandate()
    assert (await _attach(mandate_id, await signer.seal(pdf)))["code"] == "pdf_trust_roots_missing"


async def test_signer_of_another_authority_is_not_trusted(roots: Path) -> None:
    mandate_id, pdf = await _signed_mandate()
    stranger = Authority("Unknown CA").issue()
    result = await _attach(mandate_id, await stranger.seal(pdf))
    assert result["code"] == "signer_not_trusted"


async def test_expired_certificate_is_not_trusted(roots: Path, authority: Authority) -> None:
    mandate_id, pdf = await _signed_mandate()
    expired = authority.issue(days=(-30, -1))
    assert (await _attach(mandate_id, await expired.seal(pdf)))["code"] == "signer_not_trusted"


async def test_one_untrusted_signer_refuses_the_file(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = await Authority("Unknown CA").issue().seal(await signer.seal(pdf, "A"), "B")
    assert (await _attach(mandate_id, signed))["code"] == "signer_not_trusted"


async def test_sha1_signature_is_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = await signer.seal(pdf, digest="sha1")
    assert (await _attach(mandate_id, signed))["code"] == "signature_invalid"


async def test_more_than_ten_signatures_are_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    for number in range(11):
        pdf = await signer.seal(pdf, f"S{number}")
    assert (await _attach(mandate_id, pdf))["code"] == "pdf_too_large"


async def test_unsigned_pdf_is_refused(roots: Path) -> None:
    mandate_id, pdf = await _signed_mandate()
    assert (await _attach(mandate_id, pdf))["code"] == "pdf_not_signed"


def _replace_page_text(pdf: bytes, text: bytes) -> bytes:
    """An incremental update that replaces the text of the first page."""
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf))
    page = writer.root["/Pages"]["/Kids"][0].get_object()
    stream = generic.StreamObject(stream_data=b"BT /F1 20 Tf 50 700 Td (" + text + b") Tj ET")
    page["/Contents"] = writer.add_object(stream)
    writer.update_container(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


async def test_page_changed_before_signing_is_refused(roots: Path, signer: Signer) -> None:
    # The signature itself is valid: it covers a mandate PDF whose page was replaced
    # before signing, so the principal signed a text that is not the mandate.
    mandate_id, pdf = await _signed_mandate()
    signed = await signer.seal(_replace_page_text(pdf, b"Any action allowed"))
    assert (await _attach(mandate_id, signed))["code"] == "pdf_modified"


async def test_page_changed_after_signing_is_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = _replace_page_text(await signer.seal(pdf), b"Any action allowed")
    assert (await _attach(mandate_id, signed))["code"] == "pdf_modified"


def _add_annotation(pdf: bytes) -> bytes:
    """An incremental update that lays a text box over the first page."""
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf))
    page = writer.root["/Pages"]["/Kids"][0].get_object()
    note = generic.DictionaryObject(
        {
            generic.NameObject("/Type"): generic.NameObject("/Annot"),
            generic.NameObject("/Subtype"): generic.NameObject("/FreeText"),
            generic.NameObject("/Rect"): generic.ArrayObject(
                [generic.NumberObject(n) for n in (50, 600, 500, 700)]
            ),
            generic.NameObject("/Contents"): generic.TextStringObject("Any action allowed"),
            generic.NameObject("/DA"): generic.TextStringObject("/Helv 20 Tf 0 g"),
        }
    )
    page["/Annots"] = generic.ArrayObject([writer.add_object(note)])
    writer.update_container(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


async def test_annotation_added_after_signing_is_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    result = await _attach(mandate_id, _add_annotation(await signer.seal(pdf)))
    assert result["code"] == "pdf_modified"


async def test_review_level_above_form_filling_is_refused(
    roots: Path, signer: Signer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pyhanko.sign.diff_analysis import DiffResult, ModificationLevel

    import amr.pades

    monkeypatch.setattr(
        amr.pades.DEFAULT_DIFF_POLICY,
        "review_file",
        lambda *a, **k: DiffResult(ModificationLevel.ANNOTATIONS, set()),
    )
    mandate_id, pdf = await _signed_mandate()
    result = await _attach(mandate_id, await signer.seal(pdf))
    assert result["code"] == "pdf_modified"
    assert "beyond signing" in result["error"]


async def test_signature_that_does_not_cover_the_document_is_refused(
    roots: Path, signer: Signer, monkeypatch: pytest.MonkeyPatch
) -> None:
    import copy

    from pyhanko.sign.validation.status import SignatureCoverageLevel

    import amr.pades

    real = amr.pades.async_validate_pdf_signature

    async def partial(*args, **kwargs):
        status = await real(*args, **kwargs)
        changed = copy.copy(status)
        object.__setattr__(changed, "coverage", SignatureCoverageLevel.CONTIGUOUS_BLOCK_FROM_START)
        return changed

    monkeypatch.setattr(amr.pades, "async_validate_pdf_signature", partial)
    mandate_id, pdf = await _signed_mandate()
    result = await _attach(mandate_id, await signer.seal(pdf))
    assert result["code"] == "pdf_modified"
    assert "does not cover" in result["error"]


async def test_concurrent_attachments_keep_the_chain_intact(
    roots: Path, authority: Authority, temp_db: Path
) -> None:
    import asyncio

    mandate_id, pdf = await _signed_mandate()
    files = [await authority.issue().seal(pdf) for _ in range(6)]
    results = await asyncio.gather(*(_attach(mandate_id, f) for f in files))
    assert all(r.get("status") == "attached" for r in results), results
    proof = json.loads(await get_proof(mandate_id))
    assert len(proof["pdf_signatures"]) == 6
    assert proof["chain_integrity"]["pdf_signatures_intact"] is True


def _shadow_document(pdf: bytes, text: bytes) -> bytes:
    """The mandate PDF followed by a whole second document (no /Prev) showing other text."""
    import re

    objects = {
        int(m.group(1)): m.group(2)
        for m in re.finditer(rb"(\d+) 0 obj\n(.*?)\nendobj\n", pdf, re.S)
    }
    data = b"BT /F2 20 Tf 1 0 0 1 50 700 Tm (" + text + b") Tj ET\n"
    objects[9] = b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"
    out = bytearray(pdf)
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    size = max(objects) + 1
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets[number]
    file_id = re.search(rb"/ID \[<([0-9a-f]+)>", pdf).group(1)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R /ID [<%s> <%s>] >>\n" % (
        size,
        file_id,
        file_id,
    )
    out += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


async def test_second_document_appended_after_the_mandate_is_refused(
    roots: Path, signer: Signer
) -> None:
    # The reader would take the appended document for the first revision: the signer
    # signs its text, not the mandate, although the file starts with the mandate PDF.
    mandate_id, pdf = await _signed_mandate()
    signed = await signer.seal(_shadow_document(pdf, b"Agent may only READ the calendar."))
    result = await _attach(mandate_id, signed)
    assert result["code"] == "pdf_modified"
    assert "first revision" in result["error"]


async def test_field_prepared_before_signing_is_refused(roots: Path, signer: Signer) -> None:
    from pyhanko.sign.fields import SigFieldSpec, append_signature_field

    mandate_id, pdf = await _signed_mandate()
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf))
    append_signature_field(writer, SigFieldSpec("Signature1", box=(0, 0, 595, 842)))
    out = io.BytesIO()
    writer.write(out)
    result = await _attach(mandate_id, await signer.seal(out.getvalue()))
    assert result["code"] == "pdf_modified"
    assert "first update" in result["error"]


async def test_document_timestamp_is_refused(roots: Path, authority: Authority) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from pyhanko.sign import timestamps

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(cn="Test TSA"))
        .issuer_name(authority.name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=100))
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True
        )
        .sign(authority.key, hashes.SHA256())
    )
    stamper = timestamps.DummyTimeStamper(
        tsa_cert=asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
        tsa_key=asn1_keys.PrivateKeyInfo.load(
            key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        ),
    )
    mandate_id, pdf = await _signed_mandate()
    signed = await authority.issue().seal(pdf)
    writer = IncrementalPdfFileWriter(io.BytesIO(signed))
    stamped = await signers.PdfTimeStamper(stamper).async_timestamp_pdf(writer, "sha256")
    result = await _attach(mandate_id, stamped.getvalue())
    assert result["code"] == "document_timestamp_unsupported"


async def test_signed_content_cannot_serve_a_second_identical_mandate(
    roots: Path, signer: Signer
) -> None:
    first_id, pdf = await _plain_mandate()
    signed = await signer.seal(pdf)
    assert (await _attach(first_id, signed))["status"] == "attached"
    second_id, _ = await _plain_mandate()
    result = await _attach(second_id, signed)
    assert result["code"] == "pdf_used_by_another_mandate"
    proof = json.loads(await get_proof(second_id))
    assert proof["pdf_signatures"] == []


async def test_unsigned_mandate_needs_a_pdf_prepared_for_its_registration(
    roots: Path, signer: Signer
) -> None:
    mandate_id, _ = await _plain_mandate()
    old = await _pdf(signed_at=(datetime.now(UTC) - timedelta(hours=2)).isoformat())
    result = await _attach(mandate_id, await signer.seal(old))
    assert result["code"] == "pdf_not_this_mandate"


async def test_damaged_signature_is_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = bytearray(await signer.seal(pdf))
    at = signed.index(b"/Contents <") + len(b"/Contents <") + 200
    signed[at] = ord("0") if signed[at] != ord("0") else ord("1")
    result = await _attach(mandate_id, bytes(signed))
    assert result["code"] == "signature_invalid"


async def test_signed_bytes_changed_are_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = bytearray(await signer.seal(pdf))
    at = signed.index(b"Signature1")
    signed[at] = ord("X")
    result = await _attach(mandate_id, bytes(signed))
    assert result["code"] in {"signature_invalid", "pdf_modified", "pdf_unreadable"}
    assert "status" not in result


async def test_rewritten_file_is_refused(roots: Path, signer: Signer) -> None:
    mandate_id, pdf = await _signed_mandate()
    rewritten = pdf.replace(
        b"/Title (AMR mandate to be signed by the principal)",
        b"/Title (AMR mandate to be signed by the principaL)",
    )
    assert rewritten != pdf
    result = await _attach(mandate_id, await signer.seal(rewritten))
    assert result["code"] == "pdf_not_a_mandate"


async def test_attachment_removed_after_the_mandate_is_refused(
    roots: Path, signer: Signer
) -> None:
    writer = IncrementalPdfFileWriter(io.BytesIO(await _pdf()))
    del writer.root["/Names"]
    writer.update_root()
    out = io.BytesIO()
    writer.write(out)
    mandate_id, _ = await _signed_mandate()
    assert (await _attach(mandate_id, await signer.seal(out.getvalue())))["code"] == "pdf_modified"


def _blank_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [] /SigFlags 3 >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
    ]
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 4\n0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


async def test_any_other_pdf_is_not_a_mandate(roots: Path, signer: Signer) -> None:
    mandate_id, _ = await _signed_mandate()
    signed = await signer.seal(_blank_pdf())
    assert (await _attach(mandate_id, signed))["code"] == "pdf_not_a_mandate"


async def test_garbage_is_unreadable(roots: Path) -> None:
    mandate_id, _ = await _signed_mandate()
    assert (await _attach(mandate_id, b"not a pdf at all"))["code"] == "pdf_unreadable"


async def test_pdf_of_another_mandate_is_refused(roots: Path, signer: Signer) -> None:
    mandate_id, _ = await _signed_mandate()
    _, other_pdf = await _signed_mandate("org:other")
    result = await _attach(mandate_id, await signer.seal(other_pdf))
    assert result["code"] == "pdf_not_this_mandate"


async def test_signed_mandate_needs_the_very_bytes_it_signed(roots: Path, signer: Signer) -> None:
    # Same mandate content, another signed_at: not the payload the principal signed.
    mandate_id, _ = await _signed_mandate()
    pdf = await _pdf(signed_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat())
    assert (await _attach(mandate_id, await signer.seal(pdf)))["code"] == "pdf_not_this_mandate"


@pytest.mark.parametrize(
    "change",
    [
        {"scope": "Another scope"},
        {"agent_id": "agent:other"},
        {"duration_hours": 48.0},
        {"allowed_actions": ["calendar.book"]},
        {"legal_basis_article": "Art. 1985"},
    ],
)
async def test_unsigned_mandate_content_must_match(
    roots: Path, signer: Signer, change: dict
) -> None:
    mandate_id, _ = await _plain_mandate()
    pdf = await _pdf(**change)
    assert (await _attach(mandate_id, await signer.seal(pdf)))["code"] == "pdf_not_this_mandate"


async def test_unknown_mandate_is_refused(roots: Path, signer: Signer) -> None:
    _, pdf = await _signed_mandate()
    result = await _attach("00000000-0000-4000-8000-000000000000", await signer.seal(pdf))
    assert result["code"] == "mandate_not_found"


async def test_same_file_twice_is_refused(roots: Path, signer: Signer, temp_db: Path) -> None:
    mandate_id, pdf = await _signed_mandate()
    signed = await signer.seal(pdf)
    assert (await _attach(mandate_id, signed))["status"] == "attached"
    assert (await _attach(mandate_id, signed))["code"] == "pdf_already_attached"
    assert _sql(temp_db, "SELECT COUNT(*) FROM mandate_pdf_signatures") == [(1,)]
    events = _sql(
        temp_db,
        "SELECT COUNT(*) FROM mandate_events WHERE event_type = 'pdf_signature_attached'",
    )
    assert events == [(1,)]


@pytest.mark.parametrize(
    ("mandate_id", "data"),
    [
        ("not-a-uuid", base64.b64encode(b"%PDF-").decode()),
        ("00000000-0000-4000-8000-000000000000", "!!!not base64!!!"),
        ("00000000-0000-4000-8000-000000000000", ""),
    ],
)
async def test_invalid_input(roots: Path, mandate_id: str, data: str) -> None:
    result = json.loads(await attach_signed_mandate_pdf(mandate_id, data))
    assert result["code"] == "invalid_input"


async def test_oversized_input_is_refused_before_decoding(roots: Path) -> None:
    result = json.loads(
        await attach_signed_mandate_pdf("00000000-0000-4000-8000-000000000000", "A" * 12_000_000)
    )
    assert result["code"] == "invalid_input"


# --- the record in the Proof Pack -------------------------------------------------------------


async def test_record_chains_to_the_previous_one(roots: Path, signer: Signer) -> None:
    first_id, first_pdf = await _signed_mandate()
    second_id, second_pdf = await _signed_mandate("org:second")
    await _attach(first_id, await signer.seal(first_pdf))
    await _attach(second_id, await signer.seal(second_pdf))
    for mandate_id in (first_id, second_id):
        proof = json.loads(await get_proof(mandate_id))
        assert proof["chain_integrity"]["pdf_signatures_intact"] is True


@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE mandate_pdf_signatures SET signers_json = '[]'",
        "UPDATE mandate_pdf_signatures SET checked_at = '2020-01-01T00:00:00+00:00'",
        "UPDATE mandate_pdf_signatures SET signed_pdf = X'00'",
        "UPDATE mandate_pdf_signatures SET trust_roots_sha256 = 'x'",
        "DELETE FROM mandate_pdf_signatures",
        "DELETE FROM mandate_events WHERE event_type = 'pdf_signature_attached'",
    ],
)
async def test_tampered_record_shows_in_the_proof(
    roots: Path, signer: Signer, temp_db: Path, tamper: str
) -> None:
    mandate_id, pdf = await _signed_mandate()
    await _attach(mandate_id, await signer.seal(pdf))
    _sql(temp_db, tamper)
    proof = json.loads(await get_proof(mandate_id))
    assert proof["chain_integrity"]["pdf_signatures_intact"] is False


async def test_record_of_a_deleted_earlier_row_breaks_the_next(
    roots: Path, signer: Signer, temp_db: Path
) -> None:
    first_id, first_pdf = await _signed_mandate()
    second_id, second_pdf = await _signed_mandate("org:second")
    await _attach(first_id, await signer.seal(first_pdf))
    await _attach(second_id, await signer.seal(second_pdf))
    _sql(temp_db, "DELETE FROM mandate_pdf_signatures WHERE mandate_id = ?", (first_id,))
    proof = json.loads(await get_proof(second_id))
    assert proof["chain_integrity"]["pdf_signatures_intact"] is False


async def test_proof_without_signed_pdf_says_null() -> None:
    mandate_id, _ = await _plain_mandate()
    proof = json.loads(await get_proof(mandate_id))
    assert proof["pdf_signatures"] == []
    assert proof["chain_integrity"]["pdf_signatures_intact"] is None


async def test_existing_mandate_hash_is_unchanged_by_attaching(
    roots: Path, signer: Signer, temp_db: Path
) -> None:
    mandate_id, pdf = await _signed_mandate()
    before = _sql(temp_db, "SELECT chain_hash FROM mandates WHERE id = ?", (mandate_id,))
    await _attach(mandate_id, await signer.seal(pdf))
    after = _sql(temp_db, "SELECT chain_hash FROM mandates WHERE id = ?", (mandate_id,))
    assert before == after
    proof = json.loads(await get_proof(mandate_id))
    assert proof["chain_integrity"]["principal_signature_valid"] is True


async def test_migration_adds_the_table_to_an_existing_database(temp_db: Path) -> None:
    mandate_id, _ = await _plain_mandate()
    _sql(temp_db, "DROP TABLE mandate_pdf_signatures")
    _sql(temp_db, "DELETE FROM schema_version WHERE version = 10")
    proof = json.loads(await get_proof(mandate_id))
    assert proof["chain_integrity"]["pdf_signatures_intact"] is None
    assert (10,) in _sql(temp_db, "SELECT version FROM schema_version")


# --- the mandate PDF and the tool -------------------------------------------------------------


async def test_mandate_pdf_has_an_empty_append_only_form() -> None:
    pdf = await _pdf()
    assert b"/AcroForm << /Fields [] /SigFlags 3 >>" in pdf


async def test_tool_is_registered() -> None:
    tools = await mcp.list_tools()
    names = [tool.name for tool in tools]
    assert "attach_signed_mandate_pdf" in names
