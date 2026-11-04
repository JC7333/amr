"""did:web: prove that a principal's key is published by the domain it names.

A principal whose identifier is ``did:web:<domain>`` (W3C did:web method) publishes its
keys at ``https://<domain>/.well-known/did.json``. register_principal_key accepts the key
of such a principal only if that document lists it, so the first caller can no longer
register a key in the name of an organisation it does not control.

Network: this is the second opt-in exception to "no network calls" (the first is
report_issue). It is off unless the operator sets AMR_DID_WEB_RESOLVE=1 in the server's
process environment (never read from a .env file: an agent that can write files in its
working directory cannot switch the network on). When it is on, one HTTPS GET is made per
registration, to the domain named by the principal: HTTPS only, certificate checked, no
redirect followed, short timeout, bounded size, and only to public addresses (the
connection is pinned to the address that was checked, so a DNS answer cannot switch to a
private one in between).

What it proves: the domain served this key at registration time. It is not a qualified
electronic signature and it does not say who, inside the organisation, holds the key.
"""

import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from amr.crypto.principal import b64url_decode

RESOLVE_ENV = "AMR_DID_WEB_RESOLVE"
DID_WEB_PREFIX = "did:web:"
REQUEST_TIMEOUT_SECONDS = 5
MAX_DOCUMENT_BYTES = 64 * 1024
MAX_DID_LENGTH = 200

# Multicodec prefix of an Ed25519 public key in publicKeyMultibase (0xed, varint).
_ED25519_MULTICODEC = b"\xed\x01"
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]{1,100}$")
_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})


class DidWebError(Exception):
    """A did:web problem, with a stable machine-readable code."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.extra = extra


@dataclass(frozen=True)
class DidWebTarget:
    """A parsed did:web identifier: canonical form, host and document path."""

    did: str
    host: str
    path: str

    @property
    def url(self) -> str:
        return f"https://{self.host}{self.path}"


@dataclass(frozen=True)
class DidWebDocument:
    """The DID document as read: exact bytes, their SHA-256 and the parsed JSON."""

    did: str
    url: str
    raw: bytes
    sha256: str
    document: dict[str, Any]


def is_did_web(principal_id: str) -> bool:
    """True if the identifier claims the did:web method (prefix compared loosely).

    Case and surrounding spaces are ignored here on purpose: "DID:Web:example.org" must
    not escape the domain check by looking different; parse() then demands the
    canonical form.
    """
    return principal_id.strip().lower().startswith(DID_WEB_PREFIX)


def resolution_enabled() -> bool:
    """True only if the operator set AMR_DID_WEB_RESOLVE in the process environment."""
    return os.environ.get(RESOLVE_ENV, "").strip().lower() in _ENABLED_VALUES


def _ascii_host(raw_host: str) -> str:
    if "%3a" in raw_host.lower() or ":" in raw_host:
        raise DidWebError("did_web_invalid", "ports are not supported in did:web identifiers")
    host = raw_host.strip().rstrip(".")
    if not host:
        raise DidWebError("did_web_invalid", "the did:web identifier names no domain")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise DidWebError("did_web_invalid", "an IP address is not a domain name")
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise DidWebError("did_web_invalid", "the domain is not a valid name") from exc
    labels = ascii_host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        raise DidWebError("did_web_invalid", "the domain is not a valid public name")
    if labels[-1].isdigit():
        raise DidWebError("did_web_invalid", "the domain is not a valid public name")
    return ascii_host


def parse(principal_id: str) -> DidWebTarget:
    """Parse a did:web identifier into its canonical form and document location.

    did:web:example.org            -> https://example.org/.well-known/did.json
    did:web:example.org:units:hr   -> https://example.org/units/hr/did.json
    A domain with accents is converted to its ASCII (punycode) form; the canonical
    identifier uses that form. Raises DidWebError(did_web_invalid) otherwise.
    """
    if not isinstance(principal_id, str) or len(principal_id) > MAX_DID_LENGTH:
        raise DidWebError("did_web_invalid", "the did:web identifier is too long")
    text = principal_id.strip()
    if not text.lower().startswith(DID_WEB_PREFIX):
        raise DidWebError("did_web_invalid", "the identifier does not start with did:web:")
    parts = text[len(DID_WEB_PREFIX):].split(":")
    host = _ascii_host(unquote(parts[0]))
    segments = []
    for part in parts[1:]:
        segment = unquote(part)
        if not _PATH_SEGMENT.match(segment) or segment in {".", ".."}:
            raise DidWebError("did_web_invalid", "a path segment of the identifier is invalid")
        segments.append(segment)
    path = "/" + "/".join(segments) + "/did.json" if segments else "/.well-known/did.json"
    canonical = DID_WEB_PREFIX + ":".join([host, *segments])
    return DidWebTarget(did=canonical, host=host, path=path)


def _public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _resolve(host: str) -> list[str]:
    """Addresses of the host (IPv4 and IPv6). Separate so tests can replace it."""
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS to a checked address, with the certificate checked against the host name."""

    def __init__(self, host: str, address: str, timeout: float) -> None:
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _get(host: str, address: str, path: str) -> tuple[int, str | None, bytes]:
    """GET https://host/path through the checked address; never follows a redirect.

    Blocking: run in a thread. Returns (status, Location header, body up to the limit
    plus one byte, so an oversized body is detected).
    """
    connection = _PinnedHTTPSConnection(host, address, REQUEST_TIMEOUT_SECONDS)
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/did+json, application/json", "User-Agent": "amr"},
        )
        response = connection.getresponse()
        body = response.read(MAX_DOCUMENT_BYTES + 1)
        return response.status, response.getheader("Location"), body
    finally:
        connection.close()


def fetch(target: DidWebTarget) -> DidWebDocument:
    """Read the DID document of a parsed did:web identifier. Blocking: run in a thread.

    Raises DidWebError with code did_web_unreachable, did_web_address_refused,
    did_web_https_required, did_web_redirect or did_web_document_invalid.
    """
    try:
        addresses = _resolve(target.host)
    except (OSError, UnicodeError) as exc:
        raise DidWebError(
            "did_web_unreachable", f"{target.host} could not be resolved ({type(exc).__name__})"
        ) from exc
    if not addresses:
        raise DidWebError("did_web_unreachable", f"{target.host} has no address")
    if not all(_public_address(address) for address in addresses):
        raise DidWebError(
            "did_web_address_refused",
            f"{target.host} resolves to a private, local or reserved address",
        )
    try:
        status, location, body = _get(target.host, addresses[0], target.path)
    except ssl.SSLError as exc:
        raise DidWebError(
            "did_web_https_required",
            f"{target.host} did not complete a valid HTTPS connection ({type(exc).__name__})",
        ) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise DidWebError(
            "did_web_unreachable", f"{target.url} could not be read ({type(exc).__name__})"
        ) from exc
    if 300 <= status < 400:
        raise DidWebError(
            "did_web_redirect",
            "the DID document must be served at its own address; redirects are not followed",
            location=location,
        )
    if status != 200:
        raise DidWebError("did_web_unreachable", f"{target.url} answered HTTP {status}")
    if len(body) > MAX_DOCUMENT_BYTES:
        raise DidWebError("did_web_document_invalid", "the DID document is too large")
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DidWebError("did_web_document_invalid", "the DID document is not JSON") from exc
    if not isinstance(document, dict):
        raise DidWebError("did_web_document_invalid", "the DID document is not a JSON object")
    if document.get("id") != target.did:
        raise DidWebError(
            "did_web_document_invalid", "the DID document id does not match the identifier"
        )
    return DidWebDocument(
        did=target.did,
        url=target.url,
        raw=body,
        sha256=hashlib.sha256(body).hexdigest(),
        document=document,
    )


def _base58_decode(text: str) -> bytes:
    number = 0
    for char in text:
        index = _BASE58_ALPHABET.find(char)
        if index < 0:
            raise ValueError("not base58btc")
        number = number * 58 + index
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeros = len(text) - len(text.lstrip("1"))
    return b"\x00" * leading_zeros + body


def _method_key(method: Any) -> bytes | None:
    """The raw Ed25519 key of a verification method, or None if it carries none."""
    if not isinstance(method, dict):
        return None
    jwk = method.get("publicKeyJwk")
    if isinstance(jwk, dict):
        if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519" or "d" in jwk:
            return None
        try:
            return b64url_decode(jwk.get("x"), 32, "public_key")
        except Exception:
            return None
    multibase = method.get("publicKeyMultibase")
    if isinstance(multibase, str) and multibase.startswith("z") and len(multibase) < 100:
        try:
            decoded = _base58_decode(multibase[1:])
        except ValueError:
            return None
        if len(decoded) == 34 and decoded.startswith(_ED25519_MULTICODEC):
            return decoded[2:]
    return None


def key_published(document: dict[str, Any], public_key_raw: bytes) -> bool:
    """True if a verificationMethod of the document carries this Ed25519 public key.

    Accepted forms: publicKeyJwk {"kty": "OKP", "crv": "Ed25519", "x": <base64url>} and
    publicKeyMultibase "z" + base58btc(0xed 0x01 + key). Embedded methods only.
    """
    methods = document.get("verificationMethod")
    if not isinstance(methods, list):
        return False
    return any(_method_key(method) == public_key_raw for method in methods)
