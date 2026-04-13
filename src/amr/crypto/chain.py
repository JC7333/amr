"""AMR cryptographic chain module - SHA-256 hash chaining (git-style, not blockchain)."""

import hashlib
import json
from typing import Any


def compute_hash(data: dict[str, Any], previous_hash: str = "") -> str:
    """Compute a SHA-256 hash linking data to a previous hash in the chain.

    Each entry is linked to the previous one via its hash, making the chain
    tamper-evident: modifying any entry invalidates all subsequent hashes.

    Args:
        data: The data dict to hash (will be JSON-serialized with sorted keys).
        previous_hash: The hash of the previous entry in the chain (or "" for genesis).

    Returns:
        A 64-character lowercase hex SHA-256 digest.
    """
    payload = {"previous_hash": previous_hash, "data": data}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def verify_chain(
    entries: list[dict[str, Any]],
    hash_field: str = "chain_hash",
    initial_hash: str = "",
) -> bool:
    """Verify the integrity of a chain of hashed entries.

    Recomputes the hash for each entry (excluding the stored chain_hash field)
    and compares it with the stored value. Returns False if any entry has been
    tampered with. An empty chain is considered valid (vacuous truth).

    Args:
        entries: List of dicts, each containing a hash_field with the stored hash.
        hash_field: The name of the field containing the stored chain hash.
        initial_hash: The hash to use as the genesis previous_hash (default "").
                      For action chains, pass the mandate's chain_hash.

    Returns:
        True if the chain is intact, False if any entry fails verification.
    """
    if not entries:
        return True

    previous_hash = initial_hash
    for entry in entries:
        stored_hash = entry.get(hash_field, "")
        # Rebuild the data without the chain_hash field
        data_without_hash = {k: v for k, v in entry.items() if k != hash_field}
        expected_hash = compute_hash(data_without_hash, previous_hash)
        if expected_hash != stored_hash:
            return False
        previous_hash = stored_hash

    return True
