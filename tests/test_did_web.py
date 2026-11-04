"""Tests for did:web principals: the key must be published by the domain it names.

No test reaches the network: amr.did_web._resolve (DNS) and amr.did_web._get (the
pinned HTTPS GET) are replaced by fakes that record their calls.
"""

import hashlib
import json
import sqlite3
import ssl
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr import did_web
from amr.attestation import verify_attestation
from amr.crypto.chain import compute_hash
from amr.crypto.principal import (
    KEY_REGISTRATION_CONTEXT,
    b64url_encode,
    key_id,
    key_registration_payload,
)
from amr.crypto.signing import generate_signing_key
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_mandate_attestation import (
    get_registry_public_key,
    issue_mandate_attestation,
)
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key

DID = "did:web:hospital.example"
AGENT = "agent:scheduler"
PUBLIC_IP = "93.184.216.34"

BASE = {
    "agent_id": AGENT,
    "scope": "Book appointments",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "registry_key.pem"
    pub = tmp_path / "registry_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


class FakeNet:
    """Records DNS lookups and GETs; answers with what the test set."""

    def __init__(self) -> None:
        self.addresses: list[str] = [PUBLIC_IP]
        self.resolve_error: Exception | None = None
        self.status = 200
        self.location: str | None = None
        self.body = b""
        self.get_error: Exception | None = None
        self.resolved: list[str] = []
        self.gets: list[tuple[str, str, str]] = []

    def resolve(self, host: str) -> list[str]:
        self.resolved.append(host)
        if self.resolve_error is not None:
            raise self.resolve_error
        return list(self.addresses)

    def get(
        self, host: str, address: str, path: str, deadline: float | None = None
    ) -> tuple[int, str | None, bytes]:
        self.gets.append((host, address, path))
        if self.get_error is not None:
            raise self.get_error
        return self.status, self.location, self.body


@pytest.fixture
def net(monkeypatch: pytest.MonkeyPatch) -> FakeNet:
    fake = FakeNet()
    monkeypatch.setattr(did_web, "_resolve", fake.resolve)
    monkeypatch.setattr(did_web, "_get", fake.get)
    monkeypatch.setenv(did_web.RESOLVE_ENV, "1")
    return fake


def _new_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def _raw(key: ed25519.Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    return b64url_encode(_raw(key))


def _base58(raw: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = alphabet[rem] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def _jwk_method(key: ed25519.Ed25519PrivateKey, did: str = DID) -> dict:
    return {
        "id": f"{did}#key-1",
        "type": "JsonWebKey2020",
        "controller": did,
        "publicKeyJwk": {"kty": "OKP", "crv": "Ed25519", "x": _pub(key)},
    }


def _document(*methods: dict, did: str = DID) -> bytes:
    return json.dumps({"id": did, "verificationMethod": list(methods)}).encode("utf-8")


async def _register(key: ed25519.Ed25519PrivateKey, principal_id: str = DID) -> dict:
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, _pub(key))))
    return json.loads(await register_principal_key(principal_id, _pub(key), proof))


async def _signed_mandate(key: ed25519.Ed25519PrivateKey, principal_id: str = DID) -> str:
    args = {**BASE, "principal_id": principal_id}
    prepared = json.loads(await prepare_mandate_signature(**args))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    result = json.loads(
        await create_mandate(
            **args, principal_signature=signature, signed_at=prepared["signed_at"]
        )
    )
    assert "mandate_id" in result, result
    return result["mandate_id"]


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(statement, params).fetchall()
    conn.commit()
    conn.close()
    return rows


# --- Parsing the identifier ----------------------------------------------------------


def test_parse_domain_only() -> None:
    target = did_web.parse("did:web:example.org")
    assert target.did == "did:web:example.org"
    assert target.url == "https://example.org/.well-known/did.json"


def test_parse_with_path() -> None:
    target = did_web.parse("did:web:example.org:units:hr")
    assert target.url == "https://example.org/units/hr/did.json"
    assert target.did == "did:web:example.org:units:hr"


def test_parse_accented_domain_gives_punycode() -> None:
    target = did_web.parse("did:web:hôpital.example")
    assert target.host == "xn--hpital-ixa.example"
    assert target.did == "did:web:xn--hpital-ixa.example"


def test_parse_uppercase_domain_is_lowercased() -> None:
    assert did_web.parse("did:web:Hospital.Example").did == "did:web:hospital.example"


@pytest.mark.parametrize(
    "principal_id",
    [
        "did:web:example.org%3A8443",
        "did:web:127.0.0.1",
        "did:web:localhost",
        "did:web:",
        "did:web:example.org:..",
        "did:web:example.org:a%2Fb",
        "did:web:-bad-.example",
        "did:web:example.123",
        "did:web:" + "a" * 200 + ".org",
    ],
)
def test_parse_refuses_invalid_identifiers(principal_id: str) -> None:
    with pytest.raises(did_web.DidWebError) as exc:
        did_web.parse(principal_id)
    assert exc.value.code == "did_web_invalid"


@pytest.mark.parametrize(
    "principal_id", ["did:web:example.org", "DID:WEB:example.org", " did:web:example.org"]
)
def test_did_web_prefix_detected_whatever_the_case(principal_id: str) -> None:
    assert did_web.is_did_web(principal_id)


def test_ordinary_identifier_is_not_did_web() -> None:
    assert not did_web.is_did_web("user:audric")
    assert not did_web.is_did_web("did:key:z6Mk")


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "192.168.1.1",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104 - an address under test, nothing binds to it
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_private_and_local_addresses_are_not_public(address: str) -> None:
    assert not did_web._public_address(address)


def test_public_address_is_public() -> None:
    assert did_web._public_address(PUBLIC_IP)
    assert did_web._public_address("2606:4700:4700::1111")


# --- Opt-in ------------------------------------------------------------------------


async def test_without_opt_in_did_web_key_is_refused_and_no_network(
    net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(did_web.RESOLVE_ENV)
    key = _new_key()
    net.body = _document(_jwk_method(key))
    result = await _register(key)
    assert result["code"] == "did_web_resolution_disabled"
    assert net.resolved == [] and net.gets == []


async def test_opt_in_in_dotenv_file_does_not_switch_network_on(
    net: FakeNet, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(did_web.RESOLVE_ENV)
    (tmp_path / ".env").write_text(f"{did_web.RESOLVE_ENV}=1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    key = _new_key()
    net.body = _document(_jwk_method(key))
    result = await _register(key)
    assert result["code"] == "did_web_resolution_disabled"
    assert net.gets == []


@pytest.mark.parametrize("value", ["0", "", "false", "no"])
async def test_opt_in_needs_a_true_value(
    net: FakeNet, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(did_web.RESOLVE_ENV, value)
    result = await _register(_new_key())
    assert result["code"] == "did_web_resolution_disabled"


async def test_lookalike_prefix_cannot_skip_the_domain_check(
    net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(did_web.RESOLVE_ENV)
    result = await _register(_new_key(), "DID:web:hospital.example")
    assert result["code"] == "did_web_resolution_disabled"
    monkeypatch.setenv(did_web.RESOLVE_ENV, "1")
    result = await _register(_new_key(), "DID:web:hospital.example")
    assert result["code"] == "did_web_not_canonical"
    assert result["canonical_principal_id"] == DID
    assert net.gets == []


# --- Registration --------------------------------------------------------------------


async def test_published_jwk_key_is_registered_with_its_proof(net: FakeNet) -> None:
    key = _new_key()
    net.body = _document(_jwk_method(key))
    result = await _register(key)
    assert result["status"] == "registered", result
    assert result["domain_proof"] == {
        "did_document_url": "https://hospital.example/.well-known/did.json",
        "did_document_sha256": hashlib.sha256(net.body).hexdigest(),
        "verified_at": result["registered_at"],
    }
    # One DNS lookup, one GET pinned to the address that was checked.
    assert net.resolved == ["hospital.example"]
    assert net.gets == [("hospital.example", PUBLIC_IP, "/.well-known/did.json")]


async def test_published_multibase_key_is_registered(net: FakeNet) -> None:
    key = _new_key()
    method = {
        "id": f"{DID}#key-1",
        "type": "Multikey",
        "controller": DID,
        "publicKeyMultibase": "z" + _base58(b"\xed\x01" + _raw(key)),
    }
    net.body = _document(method)
    result = await _register(key)
    assert result["status"] == "registered", result


async def test_path_did_reads_document_under_its_path(net: FakeNet) -> None:
    did = "did:web:hospital.example:units:cardiology"
    key = _new_key()
    net.body = _document(_jwk_method(key, did), did=did)
    result = await _register(key, did)
    assert result["status"] == "registered", result
    assert net.gets[0][2] == "/units/cardiology/did.json"


async def test_key_not_in_document_is_refused_and_nothing_stored(
    net: FakeNet, temp_db: Path
) -> None:
    key, other = _new_key(), _new_key()
    net.body = _document(_jwk_method(other))
    result = await _register(key)
    assert result["code"] == "did_web_key_not_published"
    assert _sql(temp_db, "SELECT COUNT(*) FROM principal_keys") == [(0,)]
    assert _sql(temp_db, "SELECT COUNT(*) FROM principal_key_domain_proofs") == [(0,)]
    # The domain's real key can still be registered afterwards.
    net.body = _document(_jwk_method(other))
    assert (await _register(other))["status"] == "registered"


async def test_document_without_verification_methods_is_refused(net: FakeNet) -> None:
    net.body = json.dumps({"id": DID}).encode()
    assert (await _register(_new_key()))["code"] == "did_web_key_not_published"


async def test_wrong_curve_or_private_jwk_is_not_a_published_key(net: FakeNet) -> None:
    key = _new_key()
    wrong_curve = _jwk_method(key)
    wrong_curve["publicKeyJwk"] = {**wrong_curve["publicKeyJwk"], "crv": "X25519"}
    private = _jwk_method(key)
    private["publicKeyJwk"] = {**private["publicKeyJwk"], "d": _pub(_new_key())}
    net.body = _document(wrong_curve, private)
    assert (await _register(key))["code"] == "did_web_key_not_published"


async def test_multibase_without_ed25519_prefix_is_not_a_published_key(net: FakeNet) -> None:
    key = _new_key()
    method = {"id": f"{DID}#k", "publicKeyMultibase": "z" + _base58(b"\x12\x00" + _raw(key))}
    net.body = _document(method)
    assert (await _register(key))["code"] == "did_web_key_not_published"


async def test_non_canonical_identifier_is_refused_with_the_canonical_form(
    net: FakeNet,
) -> None:
    result = await _register(_new_key(), "did:web:hôpital.example")
    assert result["code"] == "did_web_not_canonical"
    assert result["canonical_principal_id"] == "did:web:xn--hpital-ixa.example"
    assert net.gets == []


async def test_punycode_domain_is_fetched_in_ascii(net: FakeNet) -> None:
    did = "did:web:xn--hpital-ixa.example"
    key = _new_key()
    net.body = _document(_jwk_method(key, did), did=did)
    result = await _register(key, did)
    assert result["status"] == "registered", result
    assert net.gets[0][0] == "xn--hpital-ixa.example"


async def test_invalid_identifier_is_refused(net: FakeNet) -> None:
    assert (await _register(_new_key(), "did:web:localhost"))["code"] == "did_web_invalid"
    assert net.resolved == []


async def test_unresolvable_domain_is_unreachable(net: FakeNet) -> None:
    net.resolve_error = OSError("Name or service not known")
    assert (await _register(_new_key()))["code"] == "did_web_unreachable"
    assert net.gets == []


async def test_connection_failure_is_unreachable(net: FakeNet) -> None:
    net.get_error = ConnectionRefusedError()
    assert (await _register(_new_key()))["code"] == "did_web_unreachable"


async def test_http_error_status_is_unreachable(net: FakeNet) -> None:
    net.status = 404
    result = await _register(_new_key())
    assert result["code"] == "did_web_unreachable"
    assert "404" in result["error"]


@pytest.mark.parametrize("addresses", [["10.0.0.5"], [PUBLIC_IP, "127.0.0.1"], ["::1"]])
async def test_private_address_is_refused_before_any_connection(
    net: FakeNet, addresses: list[str]
) -> None:
    net.addresses = addresses
    assert (await _register(_new_key()))["code"] == "did_web_address_refused"
    assert net.gets == []


async def test_tls_failure_means_https_required(net: FakeNet) -> None:
    net.get_error = ssl.SSLCertVerificationError("certificate verify failed")
    assert (await _register(_new_key()))["code"] == "did_web_https_required"


@pytest.mark.parametrize("status", [301, 302, 307, 308])
async def test_redirect_is_refused(net: FakeNet, status: int) -> None:
    key = _new_key()
    net.status = status
    net.location = "https://attacker.example/.well-known/did.json"
    net.body = _document(_jwk_method(key))
    result = await _register(key)
    assert result["code"] == "did_web_redirect"
    assert result["location"] == "https://attacker.example/.well-known/did.json"
    assert len(net.gets) == 1


async def test_document_id_must_match_the_identifier(net: FakeNet) -> None:
    key = _new_key()
    net.body = _document(_jwk_method(key), did="did:web:attacker.example")
    assert (await _register(key))["code"] == "did_web_document_invalid"


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b"\xff\xfe"])
async def test_document_that_is_not_a_json_object_is_refused(net: FakeNet, body: bytes) -> None:
    net.body = body
    assert (await _register(_new_key()))["code"] == "did_web_document_invalid"


async def test_oversized_document_is_refused(net: FakeNet) -> None:
    key = _new_key()
    doc = json.loads(_document(_jwk_method(key)))
    doc["padding"] = "x" * did_web.MAX_DOCUMENT_BYTES
    net.body = json.dumps(doc).encode()
    assert (await _register(key))["code"] == "did_web_document_invalid"


async def test_second_registration_refused_without_network(net: FakeNet) -> None:
    key = _new_key()
    net.body = _document(_jwk_method(key))
    assert (await _register(key))["status"] == "registered"
    net.resolved.clear()
    net.gets.clear()
    result = await _register(key)
    assert result["code"] == "principal_key_already_registered"
    assert net.resolved == [] and net.gets == []


async def test_bad_proof_of_possession_refused_before_network(net: FakeNet) -> None:
    key = _new_key()
    proof = b64url_encode(_new_key().sign(key_registration_payload(DID, _pub(key))))
    result = json.loads(await register_principal_key(DID, _pub(key), proof))
    assert result["code"] == "principal_key_proof_invalid"
    assert net.gets == []


# --- Chain: sealed for did:web, unchanged for everyone else --------------------------


async def test_domain_proof_is_sealed_in_the_key_chain_hash(net: FakeNet) -> None:
    key = _new_key()
    net.body = _document(_jwk_method(key))
    result = await _register(key)
    proof = b64url_encode(key.sign(key_registration_payload(DID, _pub(key))))
    record = {
        "context": KEY_REGISTRATION_CONTEXT,
        "principal_id": DID,
        "public_key": _pub(key),
        "key_id": key_id(_raw(key)),
        "proof_signature": proof,
        "registered_at": result["registered_at"],
        "domain_proof": result["domain_proof"],
    }
    assert result["chain_hash"] == compute_hash(record, "")
    del record["domain_proof"]
    assert result["chain_hash"] != compute_hash(record, "")


async def test_ordinary_principal_unchanged_and_no_network(net: FakeNet) -> None:
    key = _new_key()
    result = await _register(key, "user:audric")
    assert result["status"] == "registered"
    assert result["domain_proof"] is None
    assert net.resolved == [] and net.gets == []
    proof = b64url_encode(key.sign(key_registration_payload("user:audric", _pub(key))))
    record = {
        "context": KEY_REGISTRATION_CONTEXT,
        "principal_id": "user:audric",
        "public_key": _pub(key),
        "key_id": key_id(_raw(key)),
        "proof_signature": proof,
        "registered_at": result["registered_at"],
    }
    # Same hash as before this feature: no domain_proof field for ordinary principals.
    assert result["chain_hash"] == compute_hash(record, "")


# --- Proof Pack, attestation, insurer dossier ----------------------------------------


async def _did_mandate(net: FakeNet) -> tuple[str, bytes]:
    key = _new_key()
    net.body = _document(_jwk_method(key))
    assert (await _register(key))["status"] == "registered"
    return await _signed_mandate(key), net.body


async def test_proof_pack_shows_and_rechecks_the_domain_proof(net: FakeNet) -> None:
    mandate_id, body = await _did_mandate(net)
    proof = json.loads(await get_proof(mandate_id))
    domain = proof["mandate"]["principal_signature"]["key_domain_proof"]
    assert domain["did_document_url"] == "https://hospital.example/.well-known/did.json"
    assert domain["did_document_sha256"] == hashlib.sha256(body).hexdigest()
    assert domain["document"] == body.decode("utf-8")
    assert domain["rechecked"] is True
    assert proof["chain_integrity"]["principal_signature_valid"] is True


async def test_tampered_stored_document_fails_the_recheck(net: FakeNet, temp_db: Path) -> None:
    mandate_id, body = await _did_mandate(net)
    other = _document(_jwk_method(_new_key())).decode("utf-8")
    _sql(temp_db, "UPDATE principal_key_domain_proofs SET document = ?", (other,))
    proof = json.loads(await get_proof(mandate_id))
    assert proof["mandate"]["principal_signature"]["key_domain_proof"]["rechecked"] is False


async def test_stored_document_changed_without_its_hash_fails_the_recheck(
    net: FakeNet, temp_db: Path
) -> None:
    # Same id, same key, only the bytes differ: the SHA-256 alone must catch it.
    mandate_id, body = await _did_mandate(net)
    changed = json.dumps(json.loads(body), indent=2)
    _sql(temp_db, "UPDATE principal_key_domain_proofs SET document = ?", (changed,))
    proof = json.loads(await get_proof(mandate_id))
    assert proof["mandate"]["principal_signature"]["key_domain_proof"]["rechecked"] is False


async def test_insurer_dossier_reports_a_failed_recheck(net: FakeNet, temp_db: Path) -> None:
    mandate_id, body = await _did_mandate(net)
    changed = json.dumps(json.loads(body), indent=2)
    _sql(temp_db, "UPDATE principal_key_domain_proofs SET document = ?", (changed,))
    result = json.loads(await export_insurer_dossier(mandate_id))
    domains = _find(result.get("dossier", result), "principal_key_domain")
    assert domains and domains[0]["rechecked"] is False


async def test_stored_document_without_the_key_fails_the_recheck(
    net: FakeNet, temp_db: Path
) -> None:
    mandate_id, _ = await _did_mandate(net)
    other = _document(_jwk_method(_new_key()))
    _sql(
        temp_db,
        "UPDATE principal_key_domain_proofs SET document = ?, document_sha256 = ?",
        (other.decode("utf-8"), hashlib.sha256(other).hexdigest()),
    )
    proof = json.loads(await get_proof(mandate_id))
    assert proof["mandate"]["principal_signature"]["key_domain_proof"]["rechecked"] is False


async def test_stored_document_for_another_principal_fails_the_recheck(
    net: FakeNet, temp_db: Path
) -> None:
    mandate_id, _ = await _did_mandate(net)
    proof_row = _sql(temp_db, "SELECT document FROM principal_key_domain_proofs")[0][0]
    doc = json.loads(proof_row)
    doc["id"] = "did:web:attacker.example"
    other = json.dumps(doc).encode()
    _sql(
        temp_db,
        "UPDATE principal_key_domain_proofs SET document = ?, document_sha256 = ?",
        (other.decode("utf-8"), hashlib.sha256(other).hexdigest()),
    )
    proof = json.loads(await get_proof(mandate_id))
    assert proof["mandate"]["principal_signature"]["key_domain_proof"]["rechecked"] is False


async def test_ordinary_signed_mandate_has_no_domain_proof(net: FakeNet) -> None:
    key = _new_key()
    await _register(key, "user:audric")
    mandate_id = await _signed_mandate(key, "user:audric")
    proof = json.loads(await get_proof(mandate_id))
    assert proof["mandate"]["principal_signature"]["key_domain_proof"] is None


@pytest.mark.parametrize("include_payload", [False, True])
async def test_attestation_carries_the_domain_proof_without_the_document(
    net: FakeNet, include_payload: bool
) -> None:
    mandate_id, body = await _did_mandate(net)
    issued = json.loads(
        await issue_mandate_attestation(
            mandate_id, AGENT, include_principal_payload=include_payload
        )
    )
    assert "attestation" in issued, issued
    pem = json.loads(await get_registry_public_key())["public_key_pem"]
    result = verify_attestation(issued["attestation"], pem)
    assert result["valid"] is True, result
    summary = result["attestation"]
    assert summary["principal_key_domain"] == {
        "did_document_url": "https://hospital.example/.well-known/did.json",
        "did_document_sha256": hashlib.sha256(body).hexdigest(),
        "verified_at": summary["principal_key_domain"]["verified_at"],
        "rechecked": True,
    }
    assert summary["principal_did_web_unverified"] is False
    assert summary["principal_signature_rechecked"] is include_payload
    assert body.decode("utf-8") not in issued["attestation"]


async def test_attestation_of_ordinary_mandate_has_no_domain(net: FakeNet) -> None:
    key = _new_key()
    await _register(key, "user:audric")
    mandate_id = await _signed_mandate(key, "user:audric")
    issued = json.loads(await issue_mandate_attestation(mandate_id, AGENT))
    pem = json.loads(await get_registry_public_key())["public_key_pem"]
    summary = verify_attestation(issued["attestation"], pem)["attestation"]
    assert summary["principal_key_domain"] is None


def _find(obj: object, name: str) -> list:
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == name:
                found.append(value)
            found.extend(_find(value, name))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find(item, name))
    return found


async def test_insurer_dossier_carries_the_domain_proof(net: FakeNet) -> None:
    mandate_id, body = await _did_mandate(net)
    result = json.loads(await export_insurer_dossier(mandate_id))
    domains = _find(result.get("dossier", result), "principal_key_domain")
    assert domains, result
    assert domains[0]["did_document_sha256"] == hashlib.sha256(body).hexdigest()
    assert domains[0]["rechecked"] is True
    assert "document" not in domains[0]


async def test_migration_adds_the_table_to_an_existing_database(temp_db: Path) -> None:
    from amr.db.engine import init_db

    await init_db(temp_db)
    _sql(temp_db, "DROP TABLE principal_key_domain_proofs")
    _sql(temp_db, "DELETE FROM schema_version WHERE version = 9")
    await init_db(temp_db)
    assert _sql(temp_db, "SELECT COUNT(*) FROM principal_key_domain_proofs") == [(0,)]
    assert _sql(temp_db, "SELECT MAX(version) FROM schema_version") == [(9,)]


# --- Review fixes: forged proofs, look-alikes, addresses, real TLS --------------------


async def test_forged_proof_row_with_matching_hash_fails_the_recheck(
    net: FakeNet, temp_db: Path
) -> None:
    # Document and its hash replaced together, URL and time changed: the key's
    # chain_hash no longer matches the record rebuilt with this proof.
    mandate_id, _ = await _did_mandate(net)
    forged = json.loads(_sql(temp_db, "SELECT document FROM principal_key_domain_proofs")[0][0])
    forged["service"] = []
    raw = json.dumps(forged).encode()
    _sql(
        temp_db,
        "UPDATE principal_key_domain_proofs SET document = ?, document_sha256 = ?",
        (raw.decode(), hashlib.sha256(raw).hexdigest()),
    )
    proof = json.loads(await get_proof(mandate_id))
    block = proof["mandate"]["principal_signature"]
    assert block["key_domain_proof"]["rechecked"] is False
    assert block["did_web_unverified"] is True


@pytest.mark.parametrize(
    ("column", "value"),
    [("document_url", "https://evil.example/x"), ("verified_at", "1999-01-01T00:00:00+00:00")],
)
async def test_proof_row_with_other_url_or_time_fails_the_recheck(
    net: FakeNet, temp_db: Path, column: str, value: str
) -> None:
    mandate_id, _ = await _did_mandate(net)
    _sql(temp_db, f"UPDATE principal_key_domain_proofs SET {column} = ?", (value,))  # noqa: S608
    proof = json.loads(await get_proof(mandate_id))
    assert proof["mandate"]["principal_signature"]["key_domain_proof"]["rechecked"] is False


async def test_proof_row_added_to_an_unchecked_key_fails_the_recheck(
    net: FakeNet, temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A did:web key registered without any domain check (as before this version),
    # then a proof row slipped in afterwards: the key's hash does not seal it.
    key = _new_key()
    net.body = _document(_jwk_method(key))
    assert (await _register(key))["status"] == "registered"
    record = _sql(temp_db, "SELECT * FROM principal_key_domain_proofs")
    # Rebuild the key row as a legacy one: chain_hash without domain_proof.
    proof = b64url_encode(key.sign(key_registration_payload(DID, _pub(key))))
    registered_at = _sql(temp_db, "SELECT registered_at FROM principal_keys")[0][0]
    legacy = {
        "context": KEY_REGISTRATION_CONTEXT,
        "principal_id": DID,
        "public_key": _pub(key),
        "key_id": key_id(_raw(key)),
        "proof_signature": proof,
        "registered_at": registered_at,
    }
    _sql(temp_db, "UPDATE principal_keys SET chain_hash = ?", (compute_hash(legacy, ""),))
    assert record
    mandate_id = await _signed_mandate(key)
    block = json.loads(await get_proof(mandate_id))["mandate"]["principal_signature"]
    assert block["key_domain_proof"]["rechecked"] is False
    assert block["did_web_unverified"] is True


async def test_legacy_did_web_key_without_proof_is_flagged_unverified(
    net: FakeNet, temp_db: Path
) -> None:
    key = _new_key()
    net.body = _document(_jwk_method(key))
    await _register(key)
    _sql(temp_db, "DELETE FROM principal_key_domain_proofs")
    mandate_id = await _signed_mandate(key)
    block = json.loads(await get_proof(mandate_id))["mandate"]["principal_signature"]
    assert block["key_domain_proof"] is None
    assert block["did_web_unverified"] is True
    issued = json.loads(await issue_mandate_attestation(mandate_id, AGENT))
    pem = json.loads(await get_registry_public_key())["public_key_pem"]
    summary = verify_attestation(issued["attestation"], pem)["attestation"]
    assert summary["principal_did_web_unverified"] is True
    dossier = json.loads(await export_insurer_dossier(mandate_id))
    assert _find(dossier, "principal_did_web_unverified")[0] is True


async def test_ordinary_signed_mandate_is_not_flagged(net: FakeNet) -> None:
    key = _new_key()
    await _register(key, "user:audric")
    mandate_id = await _signed_mandate(key, "user:audric")
    block = json.loads(await get_proof(mandate_id))["mandate"]["principal_signature"]
    assert block["did_web_unverified"] is False


@pytest.mark.parametrize(
    "principal_id",
    [
        "did:w\u0435b:hospital.example",  # Cyrillic e
        "d\u0456d:web:hospital.example",  # Cyrillic i
        "did:\u200bweb:hospital.example",  # zero-width space
        "did\uff1aweb\uff1ahospital.example",  # full-width colons
        "\uff44id:web:hospital.example",  # full-width d
    ],
)
async def test_lookalike_did_web_identifiers_are_refused(
    net: FakeNet, monkeypatch: pytest.MonkeyPatch, principal_id: str
) -> None:
    monkeypatch.delenv(did_web.RESOLVE_ENV)
    result = await _register(_new_key(), principal_id)
    assert result["code"] == "principal_id_lookalike", result
    assert net.gets == []


@pytest.mark.parametrize("principal_id", ["user:audric", "urn:example:hr", "agent:caf\u00e9"])
async def test_ordinary_identifiers_still_register(net: FakeNet, principal_id: str) -> None:
    assert (await _register(_new_key(), principal_id))["status"] == "registered"


@pytest.mark.parametrize(
    "address", ["64:ff9b::7f00:1", "64:ff9b::a00:1", "::7f00:1", "192.88.99.1", "2002:7f00:1::1"]
)
def test_addresses_embedding_another_address_are_refused(address: str) -> None:
    assert not did_web._public_address(address)


def test_idna_divergent_domain_is_refused() -> None:
    with pytest.raises(did_web.DidWebError) as exc:
        did_web.parse("did:web:stra\u00dfe.example")
    assert exc.value.code == "did_web_invalid"


async def test_deeply_nested_document_is_invalid(net: FakeNet) -> None:
    net.body = b"[" * 50000 + b"]" * 50000
    net.body = net.body[: did_web.MAX_DOCUMENT_BYTES]
    assert (await _register(_new_key()))["code"] == "did_web_document_invalid"


async def test_next_checked_address_is_tried_when_one_fails(net: FakeNet) -> None:
    key = _new_key()
    net.addresses = ["2606:4700:4700::1111", PUBLIC_IP]
    net.body = _document(_jwk_method(key))
    calls = []

    def flaky(host: str, address: str, path: str, deadline: float | None = None):
        calls.append(address)
        if address != PUBLIC_IP:
            raise OSError("network unreachable")
        return 200, None, net.body

    did_web._get = flaky  # restored by the net fixture's monkeypatch
    assert (await _register(key))["status"] == "registered"
    assert calls == ["2606:4700:4700::1111", PUBLIC_IP]


async def test_migration_keeps_existing_key_hashes(temp_db: Path, net: FakeNet) -> None:
    from amr.db.engine import init_db

    key = _new_key()
    result = await _register(key, "user:audric")
    _sql(temp_db, "DROP TABLE principal_key_domain_proofs")
    _sql(temp_db, "DELETE FROM schema_version WHERE version = 9")
    await init_db(temp_db)
    assert _sql(temp_db, "SELECT chain_hash FROM principal_keys") == [(result["chain_hash"],)]
    assert _sql(temp_db, "SELECT MAX(version) FROM schema_version") == [(9,)]


# --- Real TLS on a local server (the network code itself, not a fake) ---------------


def _local_ca_and_cert(tmp_path: Path) -> tuple[Path, Path, Path]:
    import datetime as dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = dt.datetime.now(dt.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AMR test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hospital.example")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("hospital.example")]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    ca_path, cert_path, key_path = tmp_path / "ca.pem", tmp_path / "c.pem", tmp_path / "k.pem"
    ca_path.write_bytes(ca.public_bytes(pem))
    cert_path.write_bytes(cert.public_bytes(pem))
    key_path.write_bytes(
        key.private_bytes(
            pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    return ca_path, cert_path, key_path


@pytest.fixture
def tls_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A local HTTPS server for hospital.example; did_web trusts its CA and port only."""
    import http.server
    import threading
    import time as _time

    ca_path, cert_path, key_path = _local_ca_and_cert(tmp_path)
    routes: dict[str, tuple[int, dict[str, str], bytes, float]] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            status, headers, body, pause = routes.get(self.path, (404, {}, b"", 0.0))
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if pause:
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    _time.sleep(pause)
            else:
                self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def trusting_context() -> ssl.SSLContext:
        ctx = ssl.create_default_context(cafile=str(ca_path))
        return ctx

    monkeypatch.setattr(did_web, "_PORT", server.server_address[1])
    monkeypatch.setattr(did_web, "_ssl_context", trusting_context)
    yield routes
    server.shutdown()
    server.server_close()


def test_real_get_reads_the_document_through_the_pinned_address(tls_server) -> None:
    tls_server["/.well-known/did.json"] = (200, {}, b'{"id": "x"}', 0.0)
    # "hospital.example" does not resolve: only the pinned address can reach the server.
    status, _, body = did_web._get("hospital.example", "127.0.0.1", "/.well-known/did.json")
    assert (status, body) == (200, b'{"id": "x"}')


def test_real_get_checks_the_certificate_against_the_host_name(tls_server) -> None:
    tls_server["/.well-known/did.json"] = (200, {}, b"{}", 0.0)
    with pytest.raises(ssl.SSLCertVerificationError):
        did_web._get("attacker.example", "127.0.0.1", "/.well-known/did.json")


def test_real_get_does_not_follow_a_redirect(tls_server) -> None:
    tls_server["/.well-known/did.json"] = (
        302, {"Location": "https://hospital.example/other.json"}, b"", 0.0
    )
    tls_server["/other.json"] = (200, {}, b"{}", 0.0)
    status, location, _ = did_web._get("hospital.example", "127.0.0.1", "/.well-known/did.json")
    assert (status, location) == (302, "https://hospital.example/other.json")


def test_real_get_stops_reading_past_the_size_limit(tls_server) -> None:
    tls_server["/.well-known/did.json"] = (200, {}, b"x" * (did_web.MAX_DOCUMENT_BYTES * 3), 0.0)
    _, _, body = did_web._get("hospital.example", "127.0.0.1", "/.well-known/did.json")
    assert len(body) == did_web.MAX_DOCUMENT_BYTES + 1


def test_real_get_enforces_an_overall_deadline(tls_server) -> None:
    import time as _time

    # One byte every 0.2 s: each read is fast, the whole body is not.
    tls_server["/.well-known/did.json"] = (200, {}, b"x" * 100, 0.2)
    with pytest.raises(TimeoutError):
        did_web._get(
            "hospital.example", "127.0.0.1", "/.well-known/did.json", _time.monotonic() + 1
        )


async def test_real_registration_end_to_end(
    tls_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(did_web.RESOLVE_ENV, "1")
    monkeypatch.setattr(did_web, "_resolve", lambda host: ["127.0.0.1"])
    # The local server is on a loopback address, refused in production: allow it here.
    monkeypatch.setattr(did_web, "_public_address", lambda address: True)
    key = _new_key()
    tls_server["/.well-known/did.json"] = (200, {}, _document(_jwk_method(key)), 0.0)
    result = await _register(key)
    assert result["status"] == "registered", result
    other = _new_key()
    tls_server["/.well-known/did.json"] = (
        200, {}, _document(_jwk_method(key), did="did:web:other.example"), 0.0
    )
    result = await _register(other, "did:web:other.example")
    assert result["code"] == "did_web_https_required"  # certificate is for hospital.example


@pytest.mark.parametrize(
    ("column", "value"),
    [("document_url", "https://evil.example/x"), ("verified_at", "1999-01-01T00:00:00+00:00")],
)
async def test_resealed_forged_url_or_time_still_fails_the_recheck(
    net: FakeNet, temp_db: Path, column: str, value: str
) -> None:
    # An attacker with file access rewrites the proof row AND the key's chain_hash so
    # they agree: the URL must still be the identifier's, the time the registration's.
    key = _new_key()
    net.body = _document(_jwk_method(key))
    result = await _register(key)
    _sql(temp_db, f"UPDATE principal_key_domain_proofs SET {column} = ?", (value,))  # noqa: S608
    url, sha, verified_at = _sql(
        temp_db,
        "SELECT document_url, document_sha256, verified_at FROM principal_key_domain_proofs",
    )[0]
    record = {
        "context": KEY_REGISTRATION_CONTEXT,
        "principal_id": DID,
        "public_key": _pub(key),
        "key_id": key_id(_raw(key)),
        "proof_signature": b64url_encode(key.sign(key_registration_payload(DID, _pub(key)))),
        "registered_at": result["registered_at"],
        "domain_proof": {
            "did_document_url": url,
            "did_document_sha256": sha,
            "verified_at": verified_at,
        },
    }
    _sql(temp_db, "UPDATE principal_keys SET chain_hash = ?", (compute_hash(record, ""),))
    mandate_id = await _signed_mandate(key)
    block = json.loads(await get_proof(mandate_id))["mandate"]["principal_signature"]
    assert block["key_domain_proof"]["rechecked"] is False
    # The attestation carries the failed recheck instead of vouching for the proof.
    issued = json.loads(await issue_mandate_attestation(mandate_id, AGENT))
    pem = json.loads(await get_registry_public_key())["public_key_pem"]
    summary = verify_attestation(issued["attestation"], pem)["attestation"]
    assert summary["principal_key_domain"]["rechecked"] is False
    assert summary["principal_did_web_unverified"] is True
