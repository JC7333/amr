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

    def get(self, host: str, address: str, path: str) -> tuple[int, str | None, bytes]:
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
    }
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
