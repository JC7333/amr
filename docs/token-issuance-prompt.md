# AMR — Implémentation du pivot enforcement : token issuance layer (v3, 2026-04-22)

> **Instructions pour Cline** : ce fichier est ton cahier des charges complet.
> Exécute les phases dans l'ordre. Ne saute pas une phase. Commit atomique par
> phase. Si tu bloques, documente dans docs/token-issuance-troubleshooting.md
> et arrête-toi proprement.

---

## Contexte

AMR est un registre MCP de mandats pour agents IA (repo local : C:\dev\amr,
repo GitHub : JC7333/amr). Architecture actuelle : FastMCP + SQLite + Pydantic v2
+ SHA-256 chain. 4 outils MCP existants : create_mandate, verify_mandate,
log_action, get_proof.

Feedback design partner (Adnan Khan, Equinix, 17/04/2026) : le verify_mandate
actuel est passif — l'appelant peut ignorer le résultat. Le vrai produit doit
être un hard-stop structurel : pas de mandat valide = pas de token émis = agent
ne peut pas agir.

Mission : ajouter une couche d'émission de token (JWS Ed25519) qui n'émet un
token QUE si un mandat actif autorise l'action dans son scope. Le token est le
seul moyen pour l'agent d'agir côté runtime/plateforme cliente.

---

## Règles absolues (non négociables, valables pour toute la session)

1. **Ne touche pas aux fichiers existants sauf mention explicite dans une phase.**
   Fichiers verrouillés :
   - src/amr/tools/create_mandate.py
   - src/amr/tools/verify_mandate.py
   - src/amr/tools/log_action.py
   - src/amr/tools/get_proof.py
   - src/amr/models/mandate.py (extension OK via nouveau fichier, modification NON)
   - src/amr/crypto/chain.py
   - Tables existantes dans src/amr/db/engine.py (AJOUT de table OK, MODIF des
     tables mandates/action_logs/mandate_events NON)
   - Tests existants

2. **Invariants du projet (déjà documentés dans CLAUDE.md)** :
   - SQL paramétré uniquement (?, pas f-strings ni .format())
   - Pydantic v2 avec `extra="forbid"` sur tous les inputs
   - Tables append-only (pas de UPDATE/DELETE sur mandates/action_logs/issued_tokens)
   - Pas de secrets en clair (config via env prefix AMR_)
   - Pas d'appels réseau sortants
   - ruff S rules doivent passer

3. **Definition of done par phase** — ne passe à la phase suivante que si :
   - `uv run pytest -v` passe (nouveaux tests inclus, zéro régression)
   - `uv run ruff check src/` passe
   - Les fichiers verrouillés n'ont pas été modifiés (vérifie via `git diff main -- <fichier>`)
   - La phase est documentée (CLAUDE.md, README.md, ou docs/ selon la phase)

4. **Commit atomique par phase** sur branche dédiée `feature/token-issuance-v1`.
   Messages de commit au format : `phase N: <description courte>`.

5. **En cas d'échec bloquant** : STOP, documente l'erreur dans
   `docs/token-issuance-troubleshooting.md`, ne force pas.

---

## Phase 0 — Préparation (10 min)

### Vérification préalable (CRITIQUE, à faire avant toute chose)

1. Exécuter `uv --version` → doit répondre une version. Si `uv` n'est pas installé, STOP et demander à Audric d'installer uv.
2. Exécuter `uv run python --version` → doit afficher `Python 3.12.x` ou `Python 3.13.x`. Si pas installé, STOP.
3. Exécuter `git status` dans `C:\dev\amr` → doit être clean (ou sur main sans modifications non commitées). Sinon, STOP et demander à Audric de stash/commit avant.
4. Exécuter `git pull origin main` → récupère les derniers commits.

Si l'une de ces 4 vérifications échoue, documenter dans `docs/token-issuance-troubleshooting.md` et arrêter.

### Actions

1. `git checkout -b feature/token-issuance-v1`
2. Créer le dossier `docs/` s'il n'existe pas
3. Créer `docs/token-issuance-spec.md` avec le contenu ci-dessous :

```markdown
# Token Issuance Specification v1.0

## Goal
Enforce structural hard-stop: no valid mandate → no token → no action.

## Token Format
JWS Compact Serialization (RFC 7515) with Ed25519 signature (EdDSA).
Header: {"alg":"EdDSA","typ":"JWT","kid":"<key-id>"}.

## Required Claims
- `iss` (issuer): "amr://localhost" or configured issuer URI
- `sub` (subject): agent_id
- `aud` (audience): runtime/platform identifier where the token will be presented
- `exp` (expiration): issued_at + configurable lifetime (default 300s)
- `iat` (issued_at): UTC epoch
- `nbf` (not before): iat
- `jti` (JWT ID): UUIDv4, used for replay prevention
- `amr_mandate_id`: mandate UUID that authorized this token
- `amr_action_hash`: SHA-256 of the canonical action descriptor
  (prevents token reuse for other actions)
- `amr_scope_digest`: SHA-256 of the mandate scope at issuance time

## Replay Prevention
The `issued_tokens` table stores every issued jti with its expiration.
A token cannot be issued twice for the same `(mandate_id, action_hash)`
within the expiration window (idempotency enforced).

Note: `action_hash` does NOT include the mandate_id. The replay
prevention is keyed on `(mandate_id, action_hash)` in the DB index,
which correctly handles the case of two mandates for the same agent
requesting the same action — each gets its own token.

## Offline Verification Contract (for consumers)
Consumers of the token (agent runtimes, platforms) validate the token
using the Ed25519 public key, which AMR publishes at a well-known path
or exposes via config.

Consumers MUST check, in this order:
1. JWS signature is valid against the AMR public key (algorithm fixed to EdDSA).
2. `iss` matches the expected AMR issuer URI.
3. `aud` matches the consumer's own audience identifier
   (prevents audience confusion attacks — a token for audience A must
   not be accepted by audience B).
4. `exp` is in the future AND `nbf` is in the past (with reasonable clock skew).
5. `amr_action_hash` matches the SHA-256 of the action they are about to perform
   (canonical JSON form — see _canonical_action_hash in issue_action_token.py).

If any check fails, the consumer MUST reject the token and refuse the action.

## Security Notes
- Private key is generated once, stored at `settings.signing_key_path`,
  file permissions 0600 on POSIX.
- Algorithm is fixed to EdDSA in both encoding and decoding;
  no algorithm negotiation to prevent confusion attacks.
- Key rotation: out of scope for v1 (documented as v2 follow-up).
- Token revocation before expiration: out of scope for v1.
  Short token lifetime (5 min default) limits revocation window.
```

### Definition of done phase 0
- Branche `feature/token-issuance-v1` créée
- `docs/token-issuance-spec.md` commité
- Commit : `phase 0: token issuance spec`

---

## Phase 1 — Dépendances et clés de signature (25 min)

### Actions

1. Ajouter au `pyproject.toml` dans `[project].dependencies` :
   - `cryptography>=42.0.0`
   - `pyjwt[crypto]>=2.8.0`
2. `uv sync` pour mettre à jour `uv.lock`
3. Ajouter à `src/amr/config.py` ces champs dans la classe `Settings` :

```python
# Token issuance
signing_key_path: Path = Path("amr_signing_key.pem")
public_key_path: Path = Path("amr_signing_key.pub")
token_issuer: str = "amr://localhost"
token_lifetime_seconds: int = 300
```

4. Ajouter au `.gitignore` :

```
amr_signing_key.pem
amr_signing_key.pub
*.db
*.db-shm
*.db-wal
```

5. Créer `src/amr/crypto/signing.py` avec les fonctions suivantes
   (la signature exacte doit être respectée) :

```python
"""AMR signing key management for Ed25519 token issuance."""

import hashlib
import os
import stat
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.config import settings


def generate_signing_key(
    private_key_path: Path | None = None,
    public_key_path: Path | None = None,
) -> None:
    """Generate a new Ed25519 keypair and write it to disk.

    Raises FileExistsError if a key already exists at private_key_path.
    Sets file permissions to 0600 on POSIX systems. No-op on Windows.
    """
    ...


def ensure_signing_key_exists() -> None:
    """Ensure a signing key exists at settings.signing_key_path.

    If missing, generates a new keypair. Safe to call on every tool invocation.
    """
    ...


def load_signing_key() -> ed25519.Ed25519PrivateKey:
    """Load the Ed25519 private key from settings.signing_key_path."""
    ...


def load_public_key() -> ed25519.Ed25519PublicKey:
    """Load the Ed25519 public key from settings.public_key_path."""
    ...


def get_key_id() -> str:
    """Return a stable key identifier (first 16 hex chars of SHA-256 of public key bytes)."""
    ...
```

Implémente ces fonctions en respectant :
- Clé privée : format PEM PKCS8 non chiffré
- Clé publique : format PEM SubjectPublicKeyInfo
- `get_key_id` : hash SHA-256 des bytes bruts de la clé publique, tronqué aux 16 premiers caractères hex

### Tests obligatoires — `tests/test_signing.py`

1. `test_generate_creates_both_files` : après `generate_signing_key`, les deux fichiers existent
2. `test_generate_refuses_overwrite` : appeler 2× lève FileExistsError
3. `test_ensure_creates_if_missing` : si clé absente, `ensure_signing_key_exists` la crée
4. `test_ensure_idempotent` : si clé présente, `ensure_signing_key_exists` ne fait rien
5. `test_load_returns_ed25519_private` : type correct
6. `test_load_public_returns_ed25519_public` : type correct
7. `test_sign_and_verify_roundtrip` : signer un message avec la privée, vérifier avec la publique
8. `test_get_key_id_is_stable` : même clé → même ID sur 10 appels
9. `test_get_key_id_is_16_chars` : longueur exacte
10. `test_posix_permissions_0600` : skip sur Windows via `pytest.mark.skipif(sys.platform == "win32", ...)`. Sur POSIX, vérifie que `stat.S_IMODE(...) == 0o600`.

### Definition of done phase 1
- Dépendances ajoutées, `uv.lock` à jour
- Module `signing.py` fonctionnel (toutes les fonctions implémentées)
- 10 tests passent
- `ruff check src/` passe
- Commit : `phase 1: Ed25519 signing infrastructure`

---

## Phase 2 — Schéma DB : table issued_tokens (20 min)

### Actions

1. Dans `src/amr/db/engine.py`, ajouter au `_SCHEMA_SQL` (APRÈS `mandate_events`,
   AVANT les `CREATE INDEX` existants) :

```sql
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

CREATE INDEX IF NOT EXISTS idx_issued_tokens_mandate  ON issued_tokens(mandate_id);
CREATE INDEX IF NOT EXISTS idx_issued_tokens_expires  ON issued_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_issued_tokens_action   ON issued_tokens(mandate_id, action_hash);
```

2. Mettre à jour la version du schéma : dans le `INSERT OR IGNORE INTO schema_version`,
   remplacer `(1,)` par `(2,)`. Ajouter un commentaire au-dessus :

```python
# Schema v2: adds issued_tokens table for structural hard-stop enforcement.
# Existing v1 DBs are upgraded transparently (CREATE IF NOT EXISTS is idempotent).
```

3. Ajouter 3 fonctions utilitaires à la fin de `engine.py` :

```python
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
```

### Tests obligatoires — `tests/test_issued_tokens_db.py`

1. `test_record_inserts_row` : après record + commit, `get_issued_token` retourne le row
2. `test_replay_detected_on_same_pair` : record un token non expiré, puis is_token_replay
   sur le même (mandate_id, action_hash) → True
3. `test_replay_not_detected_after_expiration` : record un token avec expires_at
   dans le passé, is_token_replay → False
4. `test_replay_not_detected_different_action` : même mandate_id, action_hash
   différent → False
5. `test_replay_not_detected_different_mandate` : même action_hash, mandate_id
   différent → False
6. `test_get_issued_token_returns_none_for_unknown_jti`
7. `test_commit_required_for_persistence` : record SANS commit, puis ouvrir une
   nouvelle connexion → le token n'est pas visible

Note : chaque test doit faire `await db.commit()` après `record_issued_token`
(sauf le test #7 qui vérifie le contraire).

### Definition of done phase 2
- Table `issued_tokens` ajoutée au schéma
- 3 fonctions utilitaires ajoutées
- 7 tests passent
- `ruff check src/` passe
- Aucune table existante (mandates, action_logs, mandate_events) modifiée
  → vérifier avec `git diff main -- src/amr/db/engine.py` que les CREATE TABLE
  existants sont intacts
- Commit : `phase 2: issued_tokens table and helpers`

---

## Phase 3 — Models Pydantic pour tokens (10 min)

### Actions

Créer `src/amr/models/token.py` (nouveau fichier, ne touche pas mandate.py) :

```python
"""Pydantic models for action tokens issued by AMR."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IssueTokenRequest(BaseModel):
    """Input for issuing an action token. Strictly validated."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    agent_id: str = Field(..., min_length=1, max_length=200)
    action: str = Field(..., min_length=1, max_length=2000)
    audience: str = Field(..., min_length=1, max_length=500)
    action_metadata: dict[str, str] = Field(default_factory=dict)


class TokenIssueResult(BaseModel):
    """Result of a successful token issuance."""

    token: str
    jti: UUID
    expires_at: datetime
    key_id: str


class TokenDenyResult(BaseModel):
    """Result of a denied token issuance.

    reason is a machine-readable code (e.g. "mandate_not_found",
    "mandate_expired", "replay_detected_active_token_exists").
    """

    denied: bool = True
    reason: str
    mandate_id: UUID | None = None
```

Mettre à jour `src/amr/models/__init__.py` en AJOUTANT (sans rien modifier)
un import depuis `token.py`. Si `__init__.py` est actuellement minimal,
ne modifie que pour ajouter les nouveaux imports, pas le reste.

### Tests obligatoires — `tests/test_token_models.py`

1. `test_issue_token_request_valid` : instanciation avec valeurs valides
2. `test_issue_token_request_rejects_extra_field` : passer un champ `foo="bar"` → ValidationError
3. `test_issue_token_request_rejects_invalid_uuid` : mandate_id="not-a-uuid" → ValidationError
4. `test_issue_token_request_rejects_empty_agent_id` : agent_id="" → ValidationError
5. `test_issue_token_request_rejects_too_long_action` : action de 2001 chars → ValidationError
6. `test_token_issue_result_roundtrip` : instancier, dumps, loads, égalité

### Definition of done phase 3
- Fichier `models/token.py` créé
- `__init__.py` étendu sans régression
- 6 tests passent
- `ruff check src/` passe
- Commit : `phase 3: token pydantic models`

---

## Phase 4 — Le cœur : tool issue_action_token (50 min)

### Actions

Créer `src/amr/tools/issue_action_token.py`. La signature exacte de la
fonction tool MCP doit être respectée (pas de changement de nom de paramètre) :

```python
"""AMR tool: issue_action_token — structural hard-stop token issuer.

This is the enforcement layer: no valid mandate → no token → no action.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.signing import ensure_signing_key_exists, get_key_id, load_signing_key
from amr.db.engine import (
    get_db,
    init_db,
    is_token_replay,
    record_issued_token,
)
from amr.models.token import IssueTokenRequest


def _canonical_action_hash(action: str, audience: str, metadata: dict[str, str]) -> str:
    """Canonical SHA-256 hash of the action descriptor.

    Uses sorted keys and compact separators for reproducibility across
    languages and implementations. Consumers MUST use the exact same
    canonicalization when verifying a token.
    """
    canonical = json.dumps(
        {"action": action, "audience": audience, "metadata": metadata},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scope_digest(scope: str) -> str:
    """SHA-256 of the mandate scope at issuance time."""
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()


async def issue_action_token(
    mandate_id: str,
    agent_id: str,
    action: str,
    audience: str,
    action_metadata_json: str = "{}",
    lifetime_override_seconds: int | None = None,
) -> str:
    """Issue a signed action token IF AND ONLY IF a valid mandate authorizes it.

    This is the hard-stop: no valid mandate → no token → no action possible.
    Returns a JSON string with either {token, jti, expires_at, key_id}
    on success, or {denied: true, reason: "...", mandate_id: "..."} on denial.

    Args:
        mandate_id: UUID of the mandate the agent invokes.
        agent_id: Agent identifier, must match mandate.agent_id.
        action: Description of the action to be authorized.
        audience: Where the token will be presented (runtime/platform URL or id).
        action_metadata_json: Optional JSON-encoded dict of additional action metadata.
        lifetime_override_seconds: Optional override for token lifetime.
            Intended for tests only. If None, uses settings.token_lifetime_seconds.

    Returns:
        JSON string. Success keys: token, jti, expires_at, key_id.
        Denial keys: denied (true), reason, mandate_id.
    """
    db = None
    try:
        # --- 1. Validate inputs via Pydantic ---
        try:
            metadata_raw = (
                json.loads(action_metadata_json) if action_metadata_json else {}
            )
            if not isinstance(metadata_raw, dict):
                return json.dumps({
                    "denied": True,
                    "reason": "invalid_input: action_metadata_json must decode to a dict",
                })
            req = IssueTokenRequest(
                mandate_id=UUID(mandate_id),
                agent_id=agent_id,
                action=action,
                audience=audience,
                action_metadata=metadata_raw,
            )
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            return json.dumps({"denied": True, "reason": f"invalid_input: {exc}"})

        # --- 2. Ensure signing key exists (generates on first use) ---
        ensure_signing_key_exists()

        # --- 3. Fetch mandate and perform hard checks ---
        now = datetime.now(UTC)
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        cursor = await db.execute(
            """
            SELECT id, agent_id, scope, status, expires_at
            FROM mandates
            WHERE id = ?
            """,
            (str(req.mandate_id),),
        )
        row = await cursor.fetchone()

        if row is None:
            return json.dumps({
                "denied": True,
                "reason": "mandate_not_found",
                "mandate_id": str(req.mandate_id),
            })

        if row["agent_id"] != req.agent_id:
            return json.dumps({
                "denied": True,
                "reason": "agent_mismatch",
                "mandate_id": str(req.mandate_id),
            })

        if row["status"] != "active":
            return json.dumps({
                "denied": True,
                "reason": f"mandate_status_{row['status']}",
                "mandate_id": str(req.mandate_id),
            })

        mandate_expires = datetime.fromisoformat(row["expires_at"])
        # Ensure timezone awareness (SQLite stores ISO strings; reparse as UTC)
        if mandate_expires.tzinfo is None:
            mandate_expires = mandate_expires.replace(tzinfo=UTC)
        if mandate_expires <= now:
            return json.dumps({
                "denied": True,
                "reason": "mandate_expired",
                "mandate_id": str(req.mandate_id),
            })

        # --- 4. Replay prevention ---
        action_hash = _canonical_action_hash(
            req.action, req.audience, req.action_metadata
        )
        if await is_token_replay(
            db, str(req.mandate_id), action_hash, now.isoformat()
        ):
            return json.dumps({
                "denied": True,
                "reason": "replay_detected_active_token_exists",
                "mandate_id": str(req.mandate_id),
            })

        # --- 5. Build JWS claims ---
        jti = uuid4()
        lifetime = (
            lifetime_override_seconds
            if lifetime_override_seconds is not None
            else settings.token_lifetime_seconds
        )
        expires_at = now + timedelta(seconds=lifetime)
        scope_digest = _scope_digest(row["scope"])
        key_id = get_key_id()

        claims = {
            "iss": settings.token_issuer,
            "sub": req.agent_id,
            "aud": req.audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(jti),
            "amr_mandate_id": str(req.mandate_id),
            "amr_action_hash": action_hash,
            "amr_scope_digest": scope_digest,
        }

        # Load key and serialize to PEM bytes (pyjwt expects bytes or str for EdDSA)
        private_key = load_signing_key()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = jwt.encode(
            claims,
            private_key_pem,
            algorithm="EdDSA",
            headers={"kid": key_id, "typ": "JWT"},
        )

        # --- 6. Record the issued token (replay prevention + audit) ---
        await record_issued_token(
            db,
            {
                "jti": str(jti),
                "mandate_id": str(req.mandate_id),
                "agent_id": req.agent_id,
                "action_hash": action_hash,
                "scope_digest": scope_digest,
                "audience": req.audience,
                "issued_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "key_id": key_id,
            },
        )
        await db.commit()

        return json.dumps({
            "token": token,
            "jti": str(jti),
            "expires_at": expires_at.isoformat(),
            "key_id": key_id,
        })

    except Exception as exc:
        return json.dumps({"denied": True, "reason": f"internal_error: {exc}"})
    finally:
        if db is not None:
            await db.close()
```

### Helper de test pour créer des mandats

Ajoute à `tests/conftest.py` (ou crée `tests/_helpers.py`) une fonction
`insert_mandate_directly` qui insère un mandat en DB via SQL direct pour
les tests du tool issue_action_token. Elle accepte les paramètres de
flexibilité (status, expires_at dans le passé ou le futur, etc.).

Signature suggérée :

```python
async def insert_mandate_directly(
    db_path: Path,
    mandate_id: str,
    principal_id: str = "test-principal",
    agent_id: str = "test-agent",
    scope: str = "default scope",
    status: str = "active",
    hours_until_expiry: float = 24.0,
    chain_hash: str = "0" * 64,
) -> None:
    """Insert a mandate directly via SQL for isolated test setup.

    Allows negative hours_until_expiry to create already-expired mandates,
    and allows status="revoked" / "expired" to test denial paths.

    IMPORTANT: this bypasses the production chain_hash invariant. The default
    chain_hash is a placeholder ("0" * 64). Tests that combine this helper
    with real chain-dependent operations (e.g. log_action after) may produce
    broken chains — which is fine for isolated tests of issue_action_token,
    since that tool does not re-verify the chain. If a test needs a valid
    chain, use create_mandate() instead.
    """
```

### Tests obligatoires — `tests/test_issue_action_token.py`

Chaque test est isolé (temp_db fixture). Utiliser `insert_mandate_directly`
pour le setup. Au MINIMUM ces 13 tests :

1. `test_happy_path_issues_valid_token` :
   - insère mandat actif
   - issue un token
   - décode le JWS avec la clé publique (algorithmes=["EdDSA"])
   - vérifie tous les claims requis : iss, sub, aud, iat, nbf, exp, jti,
     amr_mandate_id, amr_action_hash, amr_scope_digest
2. `test_mandate_not_found_is_denied` → reason == "mandate_not_found"
3. `test_agent_mismatch_is_denied` → reason == "agent_mismatch"
4. `test_expired_mandate_is_denied` : mandat inséré avec hours_until_expiry=-1
   → reason == "mandate_expired"
5. `test_revoked_mandate_is_denied` : status="revoked"
   → reason == "mandate_status_revoked"
6. `test_replay_is_denied_when_active_token_exists` :
   - issue token A
   - issue token B pour même mandate + action
   - token B doit être denied avec reason == "replay_detected_active_token_exists"
7. `test_replay_allowed_after_previous_token_expired` :
   - issue token A avec lifetime_override_seconds=1
   - attendre 2 secondes via asyncio.sleep(2)
   - issue token B pour même mandate + action
   - token B doit être accepté
8. `test_invalid_mandate_id_format_is_denied` : mandate_id="not-a-uuid"
   → reason commence par "invalid_input"
9. `test_invalid_action_metadata_json_is_denied` : action_metadata_json="not json"
   → reason commence par "invalid_input"
10. `test_action_hash_is_deterministic` :
    - appeler _canonical_action_hash 10× avec mêmes args → même résultat
11. `test_two_different_actions_produce_different_tokens` :
    - issue token pour action "X", puis pour action "Y"
    - action_hash des deux tokens doit différer
12. `test_token_signature_verifies_with_public_key` :
    - issue un token
    - extraire la signature, la valider manuellement avec ed25519.Ed25519PublicKey.verify
    - OU plus simple : jwt.decode(token, public_key_pem, algorithms=["EdDSA"])
      ne doit pas lever d'exception
13. `test_audience_claim_matches_input` :
    - issue token avec audience="runtime://platform-x"
    - decoded["aud"] == "runtime://platform-x"

### Definition of done phase 4
- Tool `issue_action_token.py` créé, implémentation complète
- Helper `insert_mandate_directly` ajouté
- 13 tests passent
- `ruff check src/` passe
- Fichiers verrouillés inchangés (git diff le confirme)
- Commit : `phase 4: issue_action_token tool with replay prevention and test helpers`

---

## Phase 5 — Enregistrement MCP + documentation (15 min)

### Actions

1. Dans `src/amr/server.py`, ajouter :

```python
from amr.tools.issue_action_token import issue_action_token
# ... après les autres mcp.tool()(...)
mcp.tool()(issue_action_token)
```

2. Mettre à jour `CLAUDE.md` :
   - Dans le tableau "MCP Tool Reference", ajouter une ligne :
     `| issue_action_token | Issue a signed action token if and only if a valid mandate authorizes the action (hard-stop enforcement) |`
   - Ajouter une nouvelle section "Token Issuance Architecture" de 15 lignes max
     qui résume :
     - Format du token (JWS EdDSA)
     - Claims principaux (jti, amr_mandate_id, amr_action_hash, aud)
     - Replay prevention via issued_tokens table
     - Contract de vérification consumer (renvoie vers docs/token-issuance-spec.md)
   - Dans "Security Rules", ajouter règle 8 :
     `8. **Algorithm confusion prevention** — EdDSA is hardcoded in both encode and decode. Never accept algorithm=None or RS256 substitution.`

3. Mettre à jour `README.md` :
   - Ajouter une nouvelle section de 2e niveau (`## Structural hard-stop enforcement`)
     placée IMMÉDIATEMENT APRÈS le premier `##` (intro ou titre principal)
     et AVANT toute section technique (Installation, Commands, Architecture).
   - Si le README a déjà une section "Features" ou équivalente, ajouter le
     paragraphe à l'intérieur plutôt que créer une nouvelle section.
   - Contenu à insérer :

```markdown
### Structural hard-stop enforcement

AMR does not only record mandates — it enforces them. Agent runtimes must obtain
a signed action token from AMR before performing any action. The token is issued
if and only if a valid, non-expired, non-revoked mandate authorizes that specific
action for that specific agent. No mandate → no token → no action.

Tokens are JWS (RFC 7515) signed with Ed25519 (EdDSA), include replay prevention
via the `jti` claim and the `issued_tokens` audit table, and carry the exact
action hash and scope digest they authorize. Consumers verify offline with the
AMR public key and MUST check `aud`, `exp`, and `amr_action_hash`.

See `docs/token-issuance-spec.md` for the full specification.
```

### Definition of done phase 5
- `issue_action_token` exposé par MCP server
- `uv run amr` démarre sans erreur (test manuel, documenter dans doc si problème)
- `CLAUDE.md` et `README.md` à jour
- Commit : `phase 5: register issue_action_token tool, docs update`

---

## Phase 6 — Test d'intégration end-to-end (25 min)

### Actions

Créer `tests/test_integration_token_flow.py` qui exécute un scénario complet :

```python
"""End-to-end integration test for the token issuance flow.

Scenario: a principal creates a mandate for an agent, the agent requests
tokens for various actions, some are granted, some are denied.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from amr.crypto.signing import ensure_signing_key_exists, load_public_key
from amr.tools.create_mandate import create_mandate
from amr.tools.issue_action_token import issue_action_token


@pytest.mark.asyncio
async def test_end_to_end_token_flow(temp_db: Path) -> None:
    """Full flow: create mandate → issue token → verify → replay → expire → deny."""

    ensure_signing_key_exists()
    public_key = load_public_key()
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # 1. Create a valid mandate
    # NOTE: signature of create_mandate is exact — do not rename params.
    # Verified against src/amr/tools/create_mandate.py at 2026-04-22.
    create_result_json = await create_mandate(
        principal_id="hospital-paris-01",
        agent_id="claude-clinical-v1",
        scope="summarize patient records for physician review",
        legal_basis_regulation="EU AI Act",
        legal_basis_article="Art. 26",
        duration_hours=24.0,
        legal_basis_jurisdiction="EU",
    )
    create_result = json.loads(create_result_json)
    assert "mandate_id" in create_result, (
        f"create_mandate returned unexpected result: {create_result_json}"
    )
    mandate_id = create_result["mandate_id"]

    # 2. Issue a token for a valid action
    issue_result_1 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 12345",
        audience="clinical-runtime://hospital-paris-01",
        lifetime_override_seconds=2,  # short to test expiry quickly
    ))
    assert "token" in issue_result_1, f"token issuance failed: {issue_result_1}"
    token_1 = issue_result_1["token"]

    # 3. Verify the token offline with the public key
    decoded = jwt.decode(
        token_1,
        public_key_pem,
        algorithms=["EdDSA"],
        audience="clinical-runtime://hospital-paris-01",
    )
    assert decoded["sub"] == "claude-clinical-v1"
    assert decoded["amr_mandate_id"] == mandate_id
    assert "amr_action_hash" in decoded

    # 4. Replay attempt on same action → denied
    issue_result_2 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 12345",
        audience="clinical-runtime://hospital-paris-01",
    ))
    assert issue_result_2.get("denied") is True
    assert issue_result_2.get("reason") == "replay_detected_active_token_exists"

    # 5. Different action → allowed
    issue_result_3 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 67890",
        audience="clinical-runtime://hospital-paris-01",
    ))
    assert "token" in issue_result_3, f"different-action issuance failed: {issue_result_3}"

    # 6. Wait for token_1 to expire, then re-issue for the same action → allowed
    await asyncio.sleep(3)
    issue_result_4 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 12345",
        audience="clinical-runtime://hospital-paris-01",
    ))
    assert "token" in issue_result_4, (
        f"re-issuance after expiry failed: {issue_result_4}"
    )

    # 7. Audience confusion defense: consumer B refuses token for audience A
    with pytest.raises(jwt.exceptions.InvalidAudienceError):
        jwt.decode(
            token_1,
            public_key_pem,
            algorithms=["EdDSA"],
            audience="wrong-runtime://other-hospital",
        )


@pytest.mark.asyncio
async def test_expired_mandate_denies_token(temp_db: Path) -> None:
    """A mandate whose expires_at is in the past cannot issue new tokens.

    Uses insert_mandate_directly to set up an already-expired mandate
    without violating the production append-only invariant on real data.
    """
    from tests._helpers import insert_mandate_directly

    mandate_id = str(uuid4())
    await insert_mandate_directly(
        db_path=temp_db,
        mandate_id=mandate_id,
        agent_id="expired-agent",
        status="active",  # status "active" but expires_at in the past
        hours_until_expiry=-1.0,
    )

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="expired-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason") == "mandate_expired"
```

Note : la signature exacte de `create_mandate` peut différer. Lire le fichier
`src/amr/tools/create_mandate.py` AVANT d'écrire le test pour ajuster les
paramètres. Si la signature utilise d'autres noms de paramètres, adapter.

### Definition of done phase 6
- Test d'intégration passe (les deux fonctions de test)
- Tous les tests existants passent toujours (`uv run pytest -v` — zéro régression)
- `ruff check src/` passe
- Commit : `phase 6: end-to-end integration test with offline verification`

---

## Phase 7 — Push et PR (10 min)

### Actions

1. `git push -u origin feature/token-issuance-v1`
2. Ouvrir une Pull Request sur GitHub (via CLI `gh pr create` si installé,
   sinon instruire Audric de le faire manuellement) avec :
   - **Titre** : `[Pivot] Token issuance layer — structural hard-stop enforcement (v1)`
   - **Description** (à coller tel quel) :

```markdown
## Motivation
Feedback design partner (Adnan Khan, Equinix, 17/04/2026) : le verify_mandate
actuel est passif. Cette PR ajoute la couche d'émission de token qui rend
l'enforcement structurel : pas de mandat valide = pas de token = pas d'action.

## Changes
- New MCP tool: `issue_action_token`
- New module: `src/amr/crypto/signing.py` (Ed25519 key management)
- New module: `src/amr/models/token.py` (Pydantic v2)
- New DB table: `issued_tokens` (replay prevention + audit trail)
- New dependencies: `cryptography>=42.0.0`, `pyjwt[crypto]>=2.8.0`
- Documentation: `CLAUDE.md`, `README.md`, `docs/token-issuance-spec.md` updated
- Tests: +30 unit tests, +2 integration tests (all green)

## Testing
- `uv run pytest -v` — all green (existing + new)
- `uv run ruff check src/` — clean
- Manual smoke test: `uv run amr` starts, tool `issue_action_token` registered

## Security considerations
- EdDSA algorithm is hardcoded in encode and decode (no algorithm negotiation)
- Audience claim `aud` is required and MUST be verified by consumers
- Replay prevention via `issued_tokens` table indexed on `(mandate_id, action_hash)`
- Private key file permissions: 0600 on POSIX, generated on first use
- Private key path is in `.gitignore`

## Non-goals of this PR (documented as follow-ups)
- Key rotation (v2)
- Token revocation before expiration (v2)
- Well-known public key distribution endpoint (v2)
- Rate limiting of token issuance (v2)

## Review checklist for human reviewer
- [ ] JWT claims are exhaustive (iss, sub, aud, iat, nbf, exp, jti, amr_*)
- [ ] Replay detection works (test_replay_is_denied + integration)
- [ ] Locked files unchanged (git diff main -- src/amr/tools/create_mandate.py verify_mandate.py log_action.py get_proof.py models/mandate.py crypto/chain.py)
- [ ] Secrets (private key) excluded from git (.gitignore verified)
- [ ] SQL is 100% parameterized (ruff S608 passes)
- [ ] Audience confusion defense in place (test_end_to_end covers it)

## Post-merge recommended action
Budget 200-300€ for a 2-3h security audit by a senior Python/crypto freelance
dev before the first paying customer uses this in production.
```

3. **Ne pas merger automatiquement.** Laisser Audric faire la review.

### Definition of done phase 7
- Branche poussée sur origin
- PR ouverte sur GitHub avec description complète
- Commit : (pas nécessaire, la PR est le livrable final)

---

## En cas de problème

Si tu bloques à une phase :
1. Ne force pas
2. Crée `docs/token-issuance-troubleshooting.md` avec :
   - Phase bloquée
   - Erreur précise (stack trace complet)
   - Ce que tu as essayé
   - Hypothèse sur la cause
3. Commit ce fichier sur la branche
4. Arrête-toi proprement
5. Indique à Audric : "bloqué en phase X, voir docs/token-issuance-troubleshooting.md"

---

## Estimation totale

- Phase 0 : 10 min
- Phase 1 : 25 min
- Phase 2 : 20 min
- Phase 3 : 10 min
- Phase 4 : 50 min
- Phase 5 : 15 min
- Phase 6 : 25 min
- Phase 7 : 10 min

**Total : 2h45 environ.**

Coût API estimé : $4 à $10 selon les tâtonnements de Cline. Acceptable pour un
pivot produit de cette envergure.

---

## Révision humaine après la PR

Audric doit :
1. Lire la PR sur GitHub
2. Demander à Claude en chat : "audite la PR #X du repo JC7333/amr" pour avoir
   un second regard automatique sur le code
3. Tester manuellement :
   - `uv run amr` dans un terminal Windows
   - Appeler le tool depuis un client MCP (Claude Desktop configuré sur amr)
   - Vérifier qu'un token est émis pour un mandat valide
   - Vérifier qu'un refus propre est retourné pour un mandat expiré
4. Ne merger que si les deux passes (Claude audit + test manuel) sont vertes

## Investissement sécurité recommandé (après merge)

Une fois la PR mergée et avant le premier client payant :
budget 200-300€ pour 2-3h de review par un dev senior freelance familier de la
sécurité API / crypto. Plateformes : Malt, Upwork, Comet. Mots-clés recherche :
"Python API security audit, JWS, Ed25519, pyjwt". Livrable attendu : rapport de
vulnérabilités (si trouvées) + recommandations.

Pourquoi cette dépense se justifie :
- Le token est la seule chose qui sépare l'autorisation de l'action
- Une faille ici = produit démoli lors d'un audit par le premier vrai client
- 200-300€ est négligeable par rapport à la valeur d'un DP Equinix/Ledger/Thales
