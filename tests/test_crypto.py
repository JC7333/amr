"""Tests for the AMR cryptographic chain module (sync, no DB required)."""

from amr.crypto.chain import compute_hash, verify_chain

# ---------------------------------------------------------------------------
# compute_hash tests
# ---------------------------------------------------------------------------


def test_compute_hash_deterministic():
    """The same data and previous_hash must always produce the same hash."""
    data = {"id": "abc", "action": "send recommendation"}
    previous = "0" * 64

    h1 = compute_hash(data, previous)
    h2 = compute_hash(data, previous)

    assert h1 == h2


def test_compute_hash_different_data():
    """Different data with the same previous_hash must produce different hashes."""
    previous = ""
    h1 = compute_hash({"id": "1", "value": "alpha"}, previous)
    h2 = compute_hash({"id": "1", "value": "beta"}, previous)

    assert h1 != h2


def test_compute_hash_different_previous():
    """The same data with a different previous_hash must produce a different hash."""
    data = {"id": "1", "value": "same"}
    h1 = compute_hash(data, "previous_a")
    h2 = compute_hash(data, "previous_b")

    assert h1 != h2


def test_compute_hash_length():
    """compute_hash must return a 64-character hexadecimal string (SHA-256)."""
    result = compute_hash({"id": "test"}, "")

    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# verify_chain tests
# ---------------------------------------------------------------------------


def _build_chain(*labels: str, initial_hash: str = "") -> list[dict]:
    """Build a valid chain of entries from a sequence of label strings."""
    entries = []
    previous = initial_hash
    for label in labels:
        data = {"id": label, "value": f"data-{label}"}
        stored = compute_hash(data, previous)
        entries.append({**data, "chain_hash": stored})
        previous = stored
    return entries


def test_verify_chain_valid():
    """A correctly built chain of three entries must pass verification."""
    chain = _build_chain("e1", "e2", "e3")

    assert verify_chain(chain) is True


def test_verify_chain_tampered():
    """A chain where an entry's data has been altered must fail verification."""
    chain = _build_chain("e1", "e2", "e3")

    # Tamper with the first entry's payload (hash stored is now wrong)
    chain[0] = {**chain[0], "value": "tampered-value"}

    assert verify_chain(chain) is False


def test_verify_chain_empty():
    """An empty chain must be considered valid (vacuous truth)."""
    assert verify_chain([]) is True
