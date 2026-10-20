"""Offline verifier for mandate attestations (for the third party that receives one).

Usage:
    python -m amr.verify_attestation ATTESTATION --public-key registry.pub
        [--audience ME] [--issuer amr://registry] [--leeway 30]

ATTESTATION is the compact JWS itself, a file that contains it, or "-" for stdin.
The public key is the PEM from get_registry_public_key. No network call, no database.
Prints the result as JSON; exit code 0 if valid, 1 if not, 2 on a usage error.
"""

import argparse
import json
import sys
from pathlib import Path

from amr.attestation import verify_attestation


def _read_attestation(value: str) -> str:
    if value == "-":
        return sys.stdin.read().strip()
    try:
        return Path(value).read_text(encoding="utf-8").strip()
    except OSError:  # not a readable file: the attestation itself
        return value.strip()


def main(argv: list[str] | None = None) -> int:
    """Verify one attestation and print the result; return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m amr.verify_attestation",
        description="Verify an AMR mandate attestation offline.",
    )
    parser.add_argument("attestation", help="compact JWS, a file containing it, or -")
    parser.add_argument("--public-key", required=True, help="registry public key (PEM file)")
    parser.add_argument("--audience", default=None, help="who you are, if it is addressed")
    parser.add_argument("--issuer", default=None, help="registry issuer you expect")
    parser.add_argument("--leeway", type=int, default=0, help="clock skew tolerated (s)")
    args = parser.parse_args(argv)

    try:
        public_key_pem = Path(args.public_key).read_bytes()
    except OSError as exc:
        print(json.dumps({"valid": False, "reason": "public_key_unreadable",
                          "detail": str(exc)}))
        return 2
    result = verify_attestation(
        _read_attestation(args.attestation),
        public_key_pem,
        audience=args.audience,
        issuer=args.issuer,
        leeway=args.leeway,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
