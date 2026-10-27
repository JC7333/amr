"""AMR database engine - async SQLite with WAL mode and append-only tables."""

from datetime import UTC, datetime, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path

import aiosqlite

from amr.config import settings

# --- SQL Schema (append-only design: no UPDATE or DELETE on mandates/action_logs) ---

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA secure_delete=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS mandates (
    id                TEXT PRIMARY KEY,
    principal_id      TEXT NOT NULL,
    agent_id          TEXT NOT NULL,
    scope             TEXT NOT NULL,
    legal_basis_json  TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active',
    created_at        TEXT NOT NULL,
    expires_at        TEXT NOT NULL,
    parent_mandate_id TEXT REFERENCES mandates(id),
    metadata_json     TEXT NOT NULL DEFAULT '{}',
    chain_hash        TEXT NOT NULL,
    perimeter_json    TEXT,
    principal_signature      TEXT,
    principal_signed_at      TEXT,
    principal_key_id         TEXT,
    principal_signed_payload TEXT
);

CREATE TABLE IF NOT EXISTS action_logs (
    id          TEXT PRIMARY KEY,
    mandate_id  TEXT NOT NULL REFERENCES mandates(id),
    agent_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    evidence    TEXT NOT NULL DEFAULT '',
    result      TEXT NOT NULL DEFAULT '',
    timestamp   TEXT NOT NULL,
    chain_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mandate_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mandate_id  TEXT NOT NULL REFERENCES mandates(id),
    event_type  TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT ''
);

-- One row per revoked mandate (append-only; the PRIMARY KEY makes a revocation final).
-- Effective status = 'revoked' when a row exists here, whatever mandates.status says.
CREATE TABLE IF NOT EXISTS mandate_revocations (
    mandate_id               TEXT PRIMARY KEY REFERENCES mandates(id),
    principal_id             TEXT NOT NULL,
    reason                   TEXT NOT NULL,
    revoked_at               TEXT NOT NULL,
    principal_signature      TEXT UNIQUE,
    principal_signed_at      TEXT,
    principal_key_id         TEXT,
    principal_signed_payload TEXT,
    chain_hash               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issued_tokens (
    jti              TEXT PRIMARY KEY,
    mandate_id       TEXT NOT NULL REFERENCES mandates(id),
    agent_id         TEXT NOT NULL,
    action_hash      TEXT NOT NULL,
    scope_digest     TEXT NOT NULL,
    audience         TEXT NOT NULL,
    issued_at        TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    key_id           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS principal_keys (
    principal_id     TEXT PRIMARY KEY,
    public_key       TEXT NOT NULL,
    key_id           TEXT NOT NULL,
    proof_signature  TEXT NOT NULL,
    registered_at    TEXT NOT NULL,
    chain_hash       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issued_attestations (
    jti              TEXT PRIMARY KEY,
    mandate_id       TEXT NOT NULL REFERENCES mandates(id),
    agent_id         TEXT NOT NULL,
    audience         TEXT,
    issued_at        TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    key_id           TEXT NOT NULL,
    claims_digest    TEXT NOT NULL
);

-- One row per (issued token, mandate of its delegation chain) for tokens whose action
-- declares an amount (append-only). The cumulative ceiling of a mandate sums the rows
-- of its own id, so spending by any sub-mandate below it counts too.
CREATE TABLE IF NOT EXISTS token_amounts (
    jti              TEXT NOT NULL REFERENCES issued_tokens(jti),
    mandate_id       TEXT NOT NULL REFERENCES mandates(id),
    amount           TEXT NOT NULL,
    currency         TEXT NOT NULL,
    issued_at        TEXT NOT NULL,
    PRIMARY KEY (jti, mandate_id)
);

CREATE INDEX IF NOT EXISTS idx_token_amounts_mandate
    ON token_amounts(mandate_id, currency, issued_at);
CREATE INDEX IF NOT EXISTS idx_issued_attestations_mandate ON issued_attestations(mandate_id);
CREATE INDEX IF NOT EXISTS idx_issued_tokens_mandate  ON issued_tokens(mandate_id);
CREATE INDEX IF NOT EXISTS idx_issued_tokens_expires  ON issued_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_issued_tokens_action   ON issued_tokens(mandate_id, action_hash);

CREATE INDEX IF NOT EXISTS idx_mandates_agent_id     ON mandates(agent_id);
CREATE INDEX IF NOT EXISTS idx_mandates_principal_id ON mandates(principal_id);
CREATE INDEX IF NOT EXISTS idx_mandates_status       ON mandates(status);
CREATE INDEX IF NOT EXISTS idx_action_logs_mandate   ON action_logs(mandate_id);
CREATE INDEX IF NOT EXISTS idx_action_logs_agent     ON action_logs(agent_id);
"""


_PRINCIPAL_SIGNATURE_COLUMNS = (
    "principal_signature",
    "principal_signed_at",
    "principal_key_id",
    "principal_signed_payload",
)
# Fixed statements (no interpolation): one per column added by schema v4.
_ADD_COLUMN_SQL = {
    "principal_signature": "ALTER TABLE mandates ADD COLUMN principal_signature TEXT",
    "principal_signed_at": "ALTER TABLE mandates ADD COLUMN principal_signed_at TEXT",
    "principal_key_id": "ALTER TABLE mandates ADD COLUMN principal_key_id TEXT",
    "principal_signed_payload": (
        "ALTER TABLE mandates ADD COLUMN principal_signed_payload TEXT"
    ),
}


def _resolve_db_path(db_path: Path | str | None) -> Path:
    """Resolve the database path, falling back to settings if not provided."""
    if db_path is None:
        return settings.db_path
    return Path(db_path)


async def get_db(db_path: Path | str | None = None) -> aiosqlite.Connection:
    """Open and configure an async SQLite connection.

    Enables WAL mode, foreign keys, busy timeout, and secure_delete.
    Caller is responsible for closing the connection.

    Args:
        db_path: Path to the SQLite database file. Defaults to settings.db_path.

    Returns:
        A configured aiosqlite.Connection with row_factory set to aiosqlite.Row.
    """
    path = _resolve_db_path(db_path)
    db = await aiosqlite.connect(str(path))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA secure_delete=ON")
    return db


async def init_db(db_path: Path | str | None = None) -> None:
    """Initialize the database schema (idempotent - safe to call multiple times).

    Creates all tables and indexes if they do not already exist.
    Records the schema versions applied (2: issued tokens, 3: mandate perimeter,
    4: principal signatures, 5: issued attestations, 6: mandate revocations,
    7: token amounts for cumulative ceilings).

    Args:
        db_path: Path to the SQLite database file. Defaults to settings.db_path.
    """
    path = _resolve_db_path(db_path)
    async with aiosqlite.connect(str(path)) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(_SCHEMA_SQL)
        # Schema v2: adds issued_tokens table for structural hard-stop enforcement.
        # Existing v1 DBs are upgraded transparently (CREATE IF NOT EXISTS is idempotent).
        await db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (2,),
        )
        # Schema v3: structured mandate perimeter (allowed / forbidden action types,
        # delegation flag, amount limit). Older databases gain a nullable column;
        # existing rows are not modified (append-only invariant preserved).
        cursor = await db.execute("PRAGMA table_info(mandates)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "perimeter_json" not in columns:
            try:
                await db.execute("ALTER TABLE mandates ADD COLUMN perimeter_json TEXT")
            except aiosqlite.OperationalError as exc:
                # Another process added it between our check and our ALTER.
                if "duplicate column" not in str(exc):
                    raise
        await db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (3,),
        )
        # Schema v4: principal signatures. Older databases gain nullable columns
        # (existing mandates stay unsigned and unchanged); principal_keys is created
        # by the script above. A signature can register only one mandate (replay).
        cursor = await db.execute("PRAGMA table_info(mandates)")
        columns = {row["name"] for row in await cursor.fetchall()}
        for column in _PRINCIPAL_SIGNATURE_COLUMNS:
            if column not in columns:
                try:
                    await db.execute(_ADD_COLUMN_SQL[column])
                except aiosqlite.OperationalError as exc:
                    if "duplicate column" not in str(exc):
                        raise
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_mandates_principal_signature "
            "ON mandates(principal_signature) WHERE principal_signature IS NOT NULL"
        )
        await db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (4,),
        )
        # Schema v5: issued_attestations (append-only audit of the attestations shown
        # to third parties), created by the script above. Nothing else changes.
        await db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (5,),
        )
        # Schema v6: mandate_revocations, created by the script above (v5:
        # issued_attestations, just before). Existing mandates are not modified.
        await db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (6,),
        )
        # Schema v7: token_amounts, created by the script above, for cumulative amount
        # ceilings. Tokens issued before v7 carry no amount row. Nothing else changes.
        await db.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (7,),
        )
        await db.commit()


async def get_last_mandate_hash(db: aiosqlite.Connection) -> str:
    """Return the chain_hash of the most recently inserted mandate.

    This is used to link the next mandate into the hash chain.

    Args:
        db: An open aiosqlite connection.

    Returns:
        The chain_hash string of the last mandate, or "" if no mandates exist.
    """
    cursor = await db.execute(
        "SELECT chain_hash FROM mandates ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    if row is None:
        return ""
    return row["chain_hash"]


async def get_principal_key(
    db: aiosqlite.Connection, principal_id: str
) -> aiosqlite.Row | None:
    """Return the registered key row of a principal, or None if it has none."""
    cursor = await db.execute(
        "SELECT principal_id, public_key, key_id, proof_signature, registered_at, chain_hash "
        "FROM principal_keys WHERE principal_id = ?",
        (principal_id,),
    )
    return await cursor.fetchone()


async def get_last_principal_key_hash(db: aiosqlite.Connection) -> str:
    """Return the chain_hash of the last registered principal key, or "" if none."""
    cursor = await db.execute(
        "SELECT chain_hash FROM principal_keys ORDER BY rowid DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    if row is None:
        return ""
    return row["chain_hash"]


async def get_revocation(
    db: aiosqlite.Connection, mandate_id: str
) -> aiosqlite.Row | None:
    """Return the revocation row of a mandate, or None if it was never revoked."""
    cursor = await db.execute(
        "SELECT mandate_id, principal_id, reason, revoked_at, principal_signature, "
        "principal_signed_at, principal_key_id, principal_signed_payload, chain_hash "
        "FROM mandate_revocations WHERE mandate_id = ?",
        (mandate_id,),
    )
    return await cursor.fetchone()


async def get_last_revocation_hash(db: aiosqlite.Connection) -> str:
    """Return the chain_hash of the last recorded revocation, or "" if none."""
    cursor = await db.execute(
        "SELECT chain_hash FROM mandate_revocations ORDER BY rowid DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    if row is None:
        return ""
    return row["chain_hash"]


async def get_last_action_hash(db: aiosqlite.Connection, mandate_id: str) -> str:
    """Return the chain_hash of the last action logged for a given mandate.

    If no actions exist yet, returns the mandate's own chain_hash to anchor the chain.

    Args:
        db: An open aiosqlite connection.
        mandate_id: The UUID string of the mandate.

    Returns:
        The chain_hash of the last action, or the mandate's chain_hash if none exist.
    """
    cursor = await db.execute(
        "SELECT chain_hash FROM action_logs WHERE mandate_id = ? ORDER BY timestamp DESC LIMIT 1",
        (mandate_id,),
    )
    row = await cursor.fetchone()
    if row is not None:
        return row["chain_hash"]

    # Fall back to the mandate's own hash as the genesis for its action chain
    cursor2 = await db.execute(
        "SELECT chain_hash FROM mandates WHERE id = ?",
        (mandate_id,),
    )
    row2 = await cursor2.fetchone()
    if row2 is None:
        return ""
    return row2["chain_hash"]


async def record_issued_token(
    db: aiosqlite.Connection, token_row: dict[str, str]
) -> None:
    """Insert a newly issued token into issued_tokens. Does NOT commit.

    The caller is responsible for committing the transaction.
    Expected keys in token_row: jti, mandate_id, agent_id, action_hash,
    scope_digest, audience, issued_at, expires_at, key_id.
    """
    await db.execute(
        """
        INSERT INTO issued_tokens (
            jti, mandate_id, agent_id, action_hash, scope_digest,
            audience, issued_at, expires_at, key_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_row["jti"],
            token_row["mandate_id"],
            token_row["agent_id"],
            token_row["action_hash"],
            token_row["scope_digest"],
            token_row["audience"],
            token_row["issued_at"],
            token_row["expires_at"],
            token_row["key_id"],
        ),
    )


async def record_issued_attestation(
    db: aiosqlite.Connection, row: dict[str, str | None]
) -> None:
    """Insert an issued mandate attestation into issued_attestations. Does NOT commit.

    Expected keys: jti, mandate_id, agent_id, audience (or None), issued_at,
    expires_at, key_id, claims_digest.
    """
    await db.execute(
        """
        INSERT INTO issued_attestations (
            jti, mandate_id, agent_id, audience, issued_at, expires_at,
            key_id, claims_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["jti"],
            row["mandate_id"],
            row["agent_id"],
            row["audience"],
            row["issued_at"],
            row["expires_at"],
            row["key_id"],
            row["claims_digest"],
        ),
    )


async def is_token_replay(
    db: aiosqlite.Connection,
    mandate_id: str,
    action_hash: str,
    now_iso: str,
) -> bool:
    """Return True if an active (non-expired) token already exists
    for the given (mandate_id, action_hash) pair.
    """
    cursor = await db.execute(
        """
        SELECT 1 FROM issued_tokens
        WHERE mandate_id = ?
          AND action_hash = ?
          AND expires_at > ?
        LIMIT 1
        """,
        (mandate_id, action_hash, now_iso),
    )
    row = await cursor.fetchone()
    return row is not None


async def record_token_amount(
    db: aiosqlite.Connection,
    jti: str,
    mandate_ids: list[str],
    amount: str,
    currency: str,
    issued_at: str,
) -> None:
    """Record the amount of an issued token against each mandate of its chain. No commit."""
    for mandate_id in mandate_ids:
        await db.execute(
            "INSERT INTO token_amounts (jti, mandate_id, amount, currency, issued_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (jti, mandate_id, amount, currency, issued_at),
        )


async def get_period_spend(
    db: aiosqlite.Connection, mandate_id: str, currency: str, since: datetime
) -> Decimal:
    """Total amount of the tokens issued under a mandate (or below it) after ``since``.

    The SQL filter only narrows the rows (issued_at is a UTC ISO string, compared with a
    one-second margin); the exact window is applied on the parsed timestamps. The sum is
    exact: amounts have at most 18 + 18 digits, far below the 80-digit context.
    """
    cursor = await db.execute(
        "SELECT amount, issued_at FROM token_amounts "
        "WHERE mandate_id = ? AND currency = ? AND issued_at > ?",
        (mandate_id, currency, (since - timedelta(seconds=1)).isoformat()),
    )
    with localcontext(Context(prec=80)):
        total = Decimal(0)
        for row in await cursor.fetchall():
            issued_at = datetime.fromisoformat(row["issued_at"])
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=UTC)
            if issued_at > since:
                total += Decimal(row["amount"])
    return total


async def get_issued_token(
    db: aiosqlite.Connection, jti: str
) -> dict[str, str] | None:
    """Return the full row of an issued token by its jti, or None if absent."""
    cursor = await db.execute(
        "SELECT * FROM issued_tokens WHERE jti = ?",
        (jti,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)
