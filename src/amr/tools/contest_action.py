"""AMR tools: contest_action, prepare_contest_signature and list_action_contests.

An agent may already have acted when its principal finds the act was not wanted (beyond
the mandate, beyond what was meant, or simply disputed). Revoking the mandate stops what
comes next; it does not record that one past act is disputed. contest_action records it:
a dated row in action_contests (append-only, chained with SHA-256, one per logged
action) plus an "action_contested" mandate event. The row carries a response deadline,
respond_by, chosen by the operator (response_days): AMR computes no legal deadline and
asserts none. list_action_contests is the reminder: it returns the contests of a mandate
or of a contesting principal with the days left before respond_by.

A contest changes nothing else: the action log, the mandate and its hash stay as they
are, tokens keep their rules, and the mandate stays in force until revoke_mandate.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import aiosqlite
from pydantic import BaseModel, Field, ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.principal import (
    PrincipalSignatureError,
    b64url_encode,
    canonical_json,
    parse_public_key,
    parse_signature,
    parse_signed_at,
    verify,
)
from amr.db.engine import get_db, get_principal_key, init_db
from amr.delegation import MAX_DELEGATION_DEPTH

CONTEST_CONTEXT = "amr.action_contest.v1"
CONTEST_EVENT = "action_contested"
MAX_RESPONSE_DAYS = 365
MAX_LISTED_CONTESTS = 500


def _error(code: str, message: str) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code})


def _aware(moment: str) -> datetime:
    parsed = datetime.fromisoformat(moment)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class ContestRequest(BaseModel):
    """Validated input of contest_action and prepare_contest_signature."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    action_id: UUID
    reason: str = Field(..., min_length=1, max_length=500)
    response_days: int = Field(..., ge=1, le=MAX_RESPONSE_DAYS, strict=True)
    contested_by: str | None = Field(default=None, min_length=1, max_length=256)


class ContestListRequest(BaseModel):
    """Validated input of list_action_contests."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID | None = None
    contested_by: str | None = Field(default=None, min_length=1, max_length=256)
    due_within_days: int | None = Field(default=None, ge=0, le=MAX_RESPONSE_DAYS, strict=True)


def contest_payload(
    *,
    mandate_id: str,
    action_id: str,
    contested_by: str,
    reason: str,
    response_days: int,
    signed_at: str,
) -> bytes:
    """The exact bytes a principal signs to contest one logged action."""
    return canonical_json(
        {
            "context": CONTEST_CONTEXT,
            "mandate_id": mandate_id,
            "action_id": action_id,
            "contested_by": contested_by,
            "reason": reason,
            "response_days": response_days,
            "signed_at": signed_at,
        }
    )


def contest_signature_valid(contest: dict[str, Any], public_key: str | None) -> bool:
    """Re-check a stored contest signature against the contesting principal's key.

    The signed payload must name this mandate, this action, this principal, this
    reason, this response delay and this signed_at. Any damaged field reads as invalid.
    """
    try:
        if public_key is None:
            return False
        signature_raw = parse_signature(contest["principal_signature"])
        payload_text = contest["principal_signed_payload"]
        if not verify(parse_public_key(public_key), payload_text.encode("utf-8"), signature_raw):
            return False
        expected = contest_payload(
            mandate_id=contest["mandate_id"],
            action_id=contest["action_id"],
            contested_by=contest["contested_by"],
            reason=contest["reason"],
            response_days=contest["response_days"],
            signed_at=contest["principal_signed_at"],
        )
        return payload_text.encode("utf-8") == expected
    except (ValueError, TypeError, KeyError, AttributeError, PrincipalSignatureError):
        return False


async def _chain_principals(db: aiosqlite.Connection, mandate_id: str) -> list[str]:
    """Principals allowed to contest an act under this mandate.

    The mandate's own principal first, then the principal of every mandate above it,
    whatever their status: an organization can dispute what an agent did under a
    sub-mandate it delegated, even after cutting the branch.
    """
    principals: list[str] = []
    current: str | None = mandate_id
    steps = 0
    while current is not None and steps <= MAX_DELEGATION_DEPTH:
        cursor = await db.execute(
            "SELECT principal_id, parent_mandate_id FROM mandates WHERE id = ?", (current,)
        )
        row = await cursor.fetchone()
        if row is None:
            break
        if row["principal_id"] not in principals:
            principals.append(row["principal_id"])
        current = row["parent_mandate_id"]
        steps += 1
    return principals


async def _resolve(
    db: aiosqlite.Connection, req: ContestRequest
) -> tuple[aiosqlite.Row, aiosqlite.Row, str] | str:
    """Read the mandate and the action, and settle who contests. Error JSON on failure."""
    mandate_id = str(req.mandate_id)
    cursor = await db.execute(
        "SELECT id, principal_id, parent_mandate_id, chain_hash FROM mandates WHERE id = ?",
        (mandate_id,),
    )
    mandate = await cursor.fetchone()
    if mandate is None:
        return _error("mandate_not_found", f"no mandate '{mandate_id}'")
    cursor = await db.execute(
        "SELECT id, mandate_id, timestamp, chain_hash FROM action_logs WHERE id = ?",
        (str(req.action_id),),
    )
    action = await cursor.fetchone()
    if action is None or action["mandate_id"] != mandate_id:
        return _error(
            "action_not_found", f"no logged action '{req.action_id}' under this mandate"
        )
    contested_by = req.contested_by if req.contested_by is not None else mandate["principal_id"]
    if contested_by not in await _chain_principals(db, mandate_id):
        return _error(
            "contester_not_in_chain",
            "only the mandate's principal or the principal of a mandate above it "
            "can contest an action logged under it",
        )
    return mandate, action, contested_by


async def _check_contest_signature(
    db: aiosqlite.Connection,
    req: ContestRequest,
    contested_by: str,
    principal_signature: str | None,
    signed_at: str | None,
    now: datetime,
) -> dict[str, str] | None:
    """Same policy as create_mandate and revoke_mandate, for the contesting principal.

    A principal with a registered key must sign; AMR_REQUIRE_PRINCIPAL_SIGNATURE makes
    every contest signed. Returns the verified signature record, or None if unsigned.
    Raises PrincipalSignatureError with a stable code.
    """
    key_row = await get_principal_key(db, contested_by)
    if principal_signature is None and signed_at is None:
        if key_row is not None:
            raise PrincipalSignatureError(
                "principal_signature_required",
                "this principal has a registered key: the contest must carry its signature",
            )
        if settings.require_principal_signature:
            raise PrincipalSignatureError(
                "principal_signature_required",
                "this registry requires every contest to be signed by the principal",
            )
        return None
    if principal_signature is None or signed_at is None:
        raise PrincipalSignatureError(
            "principal_signature_incomplete",
            "principal_signature and signed_at must be given together",
        )
    signature_raw = parse_signature(principal_signature)
    signed_moment = parse_signed_at(signed_at)
    if key_row is None:
        raise PrincipalSignatureError(
            "principal_key_not_registered",
            "no public key is registered for this principal (register_principal_key)",
        )
    max_age = timedelta(seconds=settings.principal_signature_max_age_seconds)
    if abs(now - signed_moment) > max_age:
        raise PrincipalSignatureError(
            "principal_signature_stale",
            f"signed_at must be within {settings.principal_signature_max_age_seconds} "
            "seconds of the registry clock",
        )
    payload = contest_payload(
        mandate_id=str(req.mandate_id),
        action_id=str(req.action_id),
        contested_by=contested_by,
        reason=req.reason,
        response_days=req.response_days,
        signed_at=signed_at,
    )
    if not verify(parse_public_key(key_row["public_key"]), payload, signature_raw):
        raise PrincipalSignatureError(
            "principal_signature_invalid",
            "the signature does not match this contest and the principal's registered key",
        )
    return {
        "signature": b64url_encode(signature_raw),
        "signed_at": signed_at,
        "key_id": key_row["key_id"],
        "payload": payload.decode("utf-8"),
    }


async def get_last_contest_hash(db: aiosqlite.Connection) -> str:
    """Return the chain_hash of the last recorded contest, or "" if none."""
    cursor = await db.execute(
        "SELECT chain_hash FROM action_contests ORDER BY rowid DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    return row["chain_hash"] if row is not None else ""


def contest_hash_data(contest: dict[str, Any], mandate_chain_hash: str) -> dict[str, Any]:
    """The fields sealed in a contest's chain_hash, from its stored row."""
    data: dict[str, Any] = {
        "mandate_id": contest["mandate_id"],
        "mandate_chain_hash": mandate_chain_hash,
        "action_id": contest["action_id"],
        "action_chain_hash": contest["action_chain_hash"],
        "contested_by": contest["contested_by"],
        "reason": contest["reason"],
        "response_days": contest["response_days"],
        "contested_at": contest["contested_at"],
        "respond_by": contest["respond_by"],
    }
    if contest["principal_signature"] is not None:
        data["principal_signature"] = {
            "signature": contest["principal_signature"],
            "signed_at": contest["principal_signed_at"],
            "key_id": contest["principal_key_id"],
        }
    return data


def contest_hash_valid(
    contest: dict[str, Any], mandate_chain_hash: str, previous_hash: str
) -> bool:
    """Recompute a contest's chain_hash from its row and the previous contest's hash."""
    try:
        expected = compute_hash(contest_hash_data(contest, mandate_chain_hash), previous_hash)
    except (TypeError, ValueError, KeyError):
        return False
    return expected == contest["chain_hash"]


def deadline_view(respond_by: str, now: datetime) -> dict[str, Any]:
    """Days left before respond_by (negative once passed), and whether it has passed."""
    deadline = _aware(respond_by)
    remaining = deadline - now
    return {
        "respond_by": respond_by,
        "days_left": remaining.days if remaining >= timedelta(0) else -((-remaining).days),
        "deadline_passed": deadline <= now,
    }


def contest_record(row: Any, now: datetime) -> dict[str, Any]:
    """The public form of one action_contests row, with its deadline view."""
    contest = dict(row)
    return {
        "mandate_id": contest["mandate_id"],
        "action_id": contest["action_id"],
        "action_chain_hash": contest["action_chain_hash"],
        "contested_by": contest["contested_by"],
        "reason": contest["reason"],
        "response_days": contest["response_days"],
        "contested_at": contest["contested_at"],
        "reminder": deadline_view(contest["respond_by"], now),
        "principal_signature": (
            {
                "signature": contest["principal_signature"],
                "signed_at": contest["principal_signed_at"],
                "key_id": contest["principal_key_id"],
                "payload": contest["principal_signed_payload"],
                "algorithm": "Ed25519",
            }
            if contest["principal_signature"] is not None
            else None
        ),
        "chain_hash": contest["chain_hash"],
    }


# Fixed statements, no interpolation (CLAUDE.md rule 1).
_SELECT_CONTESTS = (
    "SELECT mandate_id, action_id, action_chain_hash, contested_by, reason, "
    "response_days, contested_at, respond_by, principal_signature, "
    "principal_signed_at, principal_key_id, principal_signed_payload, chain_hash "
    "FROM action_contests "
)
_LIST_ORDER = " AND respond_by <= ? ORDER BY respond_by ASC, rowid ASC LIMIT ?"
_LIST_QUERIES = {
    "both": _SELECT_CONTESTS + "WHERE mandate_id = ? AND contested_by = ?" + _LIST_ORDER,
    "mandate": _SELECT_CONTESTS + "WHERE mandate_id = ?" + _LIST_ORDER,
    "contester": _SELECT_CONTESTS + "WHERE contested_by = ?" + _LIST_ORDER,
}
_INSERT_CONTEST = (
    "INSERT INTO action_contests (mandate_id, action_id, action_chain_hash, "
    "contested_by, reason, response_days, contested_at, respond_by, "
    "principal_signature, principal_signed_at, principal_key_id, "
    "principal_signed_payload, chain_hash) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


async def mandate_contests(
    db: aiosqlite.Connection, mandate_id: str
) -> list[tuple[aiosqlite.Row, str]]:
    """Every contest recorded under one mandate, oldest first, each with the chain_hash
    of the contest recorded just before it in the whole registry ("" for the first)."""
    cursor = await db.execute(
        "SELECT rowid AS position, mandate_id, action_id, action_chain_hash, "
        "contested_by, reason, response_days, contested_at, respond_by, "
        "principal_signature, principal_signed_at, principal_key_id, "
        "principal_signed_payload, chain_hash FROM action_contests "
        "WHERE mandate_id = ? ORDER BY rowid ASC",
        (mandate_id,),
    )
    found: list[tuple[aiosqlite.Row, str]] = []
    for row in await cursor.fetchall():
        previous = await db.execute(
            "SELECT chain_hash FROM action_contests WHERE rowid < ? "
            "ORDER BY rowid DESC LIMIT 1",
            (row["position"],),
        )
        before = await previous.fetchone()
        found.append((row, before["chain_hash"] if before is not None else ""))
    return found


async def prepare_contest_signature(
    mandate_id: str,
    action_id: str,
    reason: str,
    response_days: int,
    contested_by: str | None = None,
    signed_at: str | None = None,
) -> str:
    """Return the exact bytes a principal must sign to contest a logged action.

    Nothing is written. The principal signs payload (UTF-8 bytes; payload_b64url is
    the same bytes) with its Ed25519 key, then calls contest_action with the same
    arguments plus principal_signature and this signed_at.

    Args:
        mandate_id: UUID of the mandate the action was logged under.
        action_id: action_id returned by log_action.
        reason: Why the act is contested, as it will be recorded (1 to 500 characters).
        response_days: Days until respond_by (1 to 365), chosen by the operator.
        contested_by: The contesting principal. Default: the mandate's principal.
        signed_at: ISO 8601 timestamp with timezone. Default: now (UTC).

    Returns:
        JSON string with keys: payload (str), payload_b64url, signed_at, contested_by.
        On error: {"error": "...", "code": "..."}.
    """
    db = None
    try:
        try:
            req = ContestRequest(
                mandate_id=mandate_id,  # type: ignore[arg-type]
                action_id=action_id,  # type: ignore[arg-type]
                reason=reason,
                response_days=response_days,
                contested_by=contested_by,
            )
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"])
        moment = signed_at if signed_at is not None else datetime.now(UTC).isoformat()
        parse_signed_at(moment)
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        resolved = await _resolve(db, req)
        if isinstance(resolved, str):
            return resolved
        _, action, who = resolved
        cursor = await db.execute(
            "SELECT 1 FROM action_contests WHERE action_id = ?", (action["id"],)
        )
        if await cursor.fetchone() is not None:
            return _error("action_already_contested", "this action is already contested")
        payload = contest_payload(
            mandate_id=str(req.mandate_id),
            action_id=str(req.action_id),
            contested_by=who,
            reason=req.reason,
            response_days=req.response_days,
            signed_at=moment,
        )
        return json.dumps(
            {
                "payload": payload.decode("utf-8"),
                "payload_b64url": b64url_encode(payload),
                "signed_at": moment,
                "contested_by": who,
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()


async def contest_action(
    mandate_id: str,
    action_id: str,
    reason: str,
    response_days: int,
    contested_by: str | None = None,
    principal_signature: str | None = None,
    signed_at: str | None = None,
) -> str:
    """Record that a principal contests an action an agent already performed.

    Use it when an act logged with log_action was not wanted: the registry keeps a
    dated, chained record that the act was disputed, and when, so silence is not the
    only trace. One contest per action; it cannot be withdrawn or edited.

    The contesting principal is the mandate's principal (default) or the principal of
    any mandate above it in the delegation chain. If that principal has a registered
    key, the contest must carry its signature: build the bytes with
    prepare_contest_signature, sign them, pass principal_signature and signed_at. With
    AMR_REQUIRE_PRINCIPAL_SIGNATURE, every contest must be signed.

    response_days sets respond_by = contested_at + response_days. It is the operator's
    own deadline (for example the delay its counsel gives before keeping or using what
    was ordered could be read as ratifying it): AMR computes no legal deadline and
    asserts none. list_action_contests reminds it.

    A contest does not undo the action, does not revoke the mandate (call
    revoke_mandate for that) and changes no hash already recorded.

    Args:
        mandate_id: UUID of the mandate the action was logged under.
        action_id: action_id returned by log_action.
        reason: Why the act is contested (1 to 500 characters).
                Example: "order placed above the agreed quantity"
        response_days: Days until respond_by, 1 to 365. Example: 14
        contested_by: The contesting principal. Default: the mandate's principal.
        principal_signature: Base64url Ed25519 signature of the contest payload.
        signed_at: The signed_at placed in the payload (ISO 8601 with timezone).

    Returns:
        JSON string with keys: status ("contested"), mandate_id, action_id,
        action_chain_hash, contested_by, reason, response_days, contested_at,
        reminder ({respond_by, days_left, deadline_passed}), principal_signature
        ({key_id, signed_at} or null), chain_hash.
        On error: {"error": "...", "code": "..."} with code invalid_input,
        mandate_not_found, action_not_found, contester_not_in_chain,
        action_already_contested or a principal signature code.
    """
    db = None
    try:
        try:
            req = ContestRequest(
                mandate_id=mandate_id,  # type: ignore[arg-type]
                action_id=action_id,  # type: ignore[arg-type]
                reason=reason,
                response_days=response_days,
                contested_by=contested_by,
            )
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"])
        now = datetime.now(UTC)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        # One write transaction from these reads to the inserts below, so two
        # concurrent contests cannot chain to the same previous contest hash.
        await db.execute("BEGIN IMMEDIATE")
        resolved = await _resolve(db, req)
        if isinstance(resolved, str):
            return resolved
        mandate, action, who = resolved
        cursor = await db.execute(
            "SELECT 1 FROM action_contests WHERE action_id = ?", (action["id"],)
        )
        if await cursor.fetchone() is not None:
            return _error("action_already_contested", "this action is already contested")

        signature = await _check_contest_signature(
            db, req, who, principal_signature, signed_at, now
        )

        contested_at = now.isoformat()
        respond_by = (now + timedelta(days=req.response_days)).isoformat()
        hash_data = contest_hash_data(
            {
                "mandate_id": mandate["id"],
                "action_id": action["id"],
                "action_chain_hash": action["chain_hash"],
                "contested_by": who,
                "reason": req.reason,
                "response_days": req.response_days,
                "contested_at": contested_at,
                "respond_by": respond_by,
                "principal_signature": signature["signature"] if signature else None,
                "principal_signed_at": signature["signed_at"] if signature else None,
                "principal_key_id": signature["key_id"] if signature else None,
            },
            mandate["chain_hash"],
        )
        chain_hash = compute_hash(hash_data, await get_last_contest_hash(db))

        await db.execute(
            _INSERT_CONTEST,
            (
                mandate["id"],
                action["id"],
                action["chain_hash"],
                who,
                req.reason,
                req.response_days,
                contested_at,
                respond_by,
                signature["signature"] if signature else None,
                signature["signed_at"] if signature else None,
                signature["key_id"] if signature else None,
                signature["payload"] if signature else None,
                chain_hash,
            ),
        )
        await db.execute(
            """
            INSERT INTO mandate_events (mandate_id, event_type, timestamp, reason)
            VALUES (?, ?, ?, ?)
            """,
            (mandate["id"], CONTEST_EVENT, contested_at, f"action {action['id']}: {req.reason}"),
        )
        await db.commit()

        return json.dumps(
            {
                "status": "contested",
                "mandate_id": mandate["id"],
                "action_id": action["id"],
                "action_chain_hash": action["chain_hash"],
                "contested_by": who,
                "reason": req.reason,
                "response_days": req.response_days,
                "contested_at": contested_at,
                "reminder": deadline_view(respond_by, now),
                "principal_signature": (
                    {"key_id": signature["key_id"], "signed_at": signature["signed_at"]}
                    if signature
                    else None
                ),
                "chain_hash": chain_hash,
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError as exc:
        if "action_contests.action_id" in str(exc):
            return _error("action_already_contested", "this action is already contested")
        if "principal_signature" in str(exc):
            # Defensive only: the payload names the action, so a replayed signature
            # meets action_already_contested first.
            return _error(
                "principal_signature_replayed", "this signature already recorded a contest"
            )
        return json.dumps({"error": str(exc)})

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()


async def list_action_contests(
    mandate_id: str | None = None,
    contested_by: str | None = None,
    due_within_days: int | None = None,
) -> str:
    """List contested actions with the days left before their respond_by (the reminder).

    Read-only. Give mandate_id, contested_by, or both. Call it on a schedule (for
    example each morning) to see which contests reach their response deadline soon.
    The deadline is the operator's own (response_days of contest_action), not a legal
    deadline computed by AMR.

    Args:
        mandate_id: Only the contests under this mandate.
        contested_by: Only the contests recorded by this principal.
        due_within_days: Only the contests whose respond_by is at most this many days
                         away, including those already passed (0 to 365).

    Returns:
        JSON string with keys: generated_at, count, truncated (true if more than 500
        matched; the 500 nearest deadlines are returned) and contests (list, nearest
        respond_by first, each with mandate_id, action_id, action_chain_hash,
        contested_by, reason, response_days, contested_at, reminder {respond_by,
        days_left, deadline_passed}, principal_signature, chain_hash).
        On error: {"error": "...", "code": "invalid_input"}.
    """
    db = None
    try:
        try:
            req = ContestListRequest(
                mandate_id=mandate_id,  # type: ignore[arg-type]
                contested_by=contested_by,
                due_within_days=due_within_days,
            )
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"])
        if req.mandate_id is None and req.contested_by is None:
            return _error("invalid_input", "give mandate_id, contested_by, or both")
        now = datetime.now(UTC)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        # respond_by is stored as a UTC ISO string written by contest_action, so the
        # string order is the time order. No horizon: the far end of the range.
        horizon = (
            (now + timedelta(days=req.due_within_days)).isoformat()
            if req.due_within_days is not None
            else "9999"
        )
        tail = (horizon, MAX_LISTED_CONTESTS + 1)
        if req.mandate_id is not None and req.contested_by is not None:
            cursor = await db.execute(
                _LIST_QUERIES["both"], (str(req.mandate_id), req.contested_by, *tail)
            )
        elif req.mandate_id is not None:
            cursor = await db.execute(_LIST_QUERIES["mandate"], (str(req.mandate_id), *tail))
        else:
            cursor = await db.execute(_LIST_QUERIES["contester"], (req.contested_by, *tail))
        rows = list(await cursor.fetchall())
        truncated = len(rows) > MAX_LISTED_CONTESTS
        contests = [contest_record(row, now) for row in rows[:MAX_LISTED_CONTESTS]]
        return json.dumps(
            {
                "generated_at": now.isoformat(),
                "count": len(contests),
                "truncated": truncated,
                "contests": contests,
            }
        )

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
