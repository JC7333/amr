"""Refusals reported to MCP clients as errors, in one shape.

Each AMR tool answers with a JSON string. Until now a refusal (unknown or revoked mandate,
action outside the perimeter, invalid input) came back as an ordinary result, so an agent
that only looked at the MCP error flag saw a success. Each tool also had its own shape:
"error" alone, "error" with "code", or "denied" with "reason".

The server now wraps every tool it registers (see server.register_tools). When the JSON
answer is a refusal, the client receives it with isError set, and the JSON gains three keys,
the same for every tool:

    code     a stable machine word (mandate_not_found, action_out_of_scope, invalid_input,
             internal_error, ...): the tool's own "code", else its "reason", else
             internal_error;
    message  one readable sentence; a raw Pydantic validation text becomes
             "<field>: <what is wrong>";
    field    the input field at fault, when AMR knows it, else null.

Every key the tool already returned stays as it was. A key the tool already set is never
overwritten. A successful answer is passed through untouched.

What counts as a refusal: a top-level "error" key, "denied": true, or, for
check_action_token only, "valid": false with reason invalid_input or internal_error (the
call itself could not be answered), or verify_mandate "authorized": false for a
malformed mandate_id (bad input). The other negative answers of the checking tools,
verify_mandate "authorized": false and check_action_token "valid": false with any other
reason, are answers to the question asked, not errors: they stay ordinary results.

The tool functions themselves are unchanged: Python code that calls them directly gets
the same string as before. Only what an MCP client receives changes.
"""

import functools
import importlib.metadata
import json
import re
from typing import Any

# check_action_token answers "valid": false for a bad token (an answer); these reasons
# mean the check could not be made at all.
CHECK_FAILED_REASONS = frozenset({"invalid_input", "internal_error", "registry_unavailable"})

# verify_mandate answers a malformed mandate_id with "authorized": false and this reason:
# bad input, not an answer to the question asked.
VERIFY_BAD_ID_PREFIX = "Invalid mandate_id format"

_PYDANTIC_HEADER = re.compile(r"(\d+) validation errors? for \S+")
_TYPE_SUFFIX = re.compile(r"\s*\[type=.*\]\s*$")
_CODE_PREFIX = re.compile(r"^([a-z][a-z0-9_]*):\s*")


def validation_field(exc: Any) -> str | None:
    """The input field of the first error of a Pydantic ValidationError, if it has one."""
    errors = exc.errors()
    location = errors[0].get("loc", ()) if errors else ()
    return ".".join(str(part) for part in location) or None


def is_refusal(body: Any) -> bool:
    """Whether a tool's decoded JSON answer is a refusal (see module docstring)."""
    if not isinstance(body, dict):
        return False
    if "error" in body:
        return True
    if body.get("denied") is True:
        return True
    reason = body.get("reason")
    if body.get("authorized") is False and isinstance(reason, str):
        return reason.startswith(VERIFY_BAD_ID_PREFIX)
    return body.get("valid") is False and body.get("reason") in CHECK_FAILED_REASONS


def _code_of(body: dict[str, Any]) -> str:
    if body.get("authorized") is False:  # verify_mandate's malformed mandate_id
        return "invalid_input"
    for key in ("code", "reason"):
        value = body.get(key)
        if isinstance(value, str) and value:
            prefix = _CODE_PREFIX.match(value)
            return prefix.group(1) if prefix else value.split(":", 1)[0].strip()
    return "internal_error"


def _pydantic_first_error(text: str) -> tuple[str | None, str] | None:
    """(field, readable message) of the first error in a Pydantic validation text."""
    header = _PYDANTIC_HEADER.search(text)
    if header is None:
        return None
    count = int(header.group(1))
    lines = [line for line in text[header.end() :].splitlines() if line.strip()]
    if not lines:
        return None
    field: str | None = None
    if not lines[0].startswith(" ") and len(lines) > 1:
        field = lines[0].strip()
        detail = lines[1]
    else:
        detail = lines[0]  # an error on the whole input has no field line
    detail = _TYPE_SUFFIX.sub("", detail.strip())
    detail = detail.removeprefix("Value error, ").removeprefix("Assertion failed, ")
    message = f"{field}: {detail}" if field else detail
    if count > 1:
        message += f" (and {count - 1} more)"
    return field, message


def common_shape(body: dict[str, Any]) -> dict[str, Any]:
    """code, message and field of a refusal."""
    code = _code_of(body)
    raw = body.get("error")
    from_error = isinstance(raw, str) and bool(raw)
    if not from_error:
        reason = body.get("reason")
        detail = body.get("detail")
        raw = f"{reason}: {detail}" if detail else str(reason or code)
    field = body.get("field") if isinstance(body.get("field"), str) else None
    parsed = _pydantic_first_error(raw)
    if parsed is not None:
        parsed_field, message = parsed
        field = field or parsed_field
        if code == "internal_error":  # an uncaught validation error is still bad input
            code = "invalid_input"
    else:
        message = raw
        # "reason: detail" built above keeps its reason; a reason that is itself
        # "code: text" loses the code, which is already in code.
        prefix = _CODE_PREFIX.match(message) if from_error or not body.get("detail") else None
        if prefix and prefix.group(1) == code and message[prefix.end() :]:
            message = message[prefix.end() :]
        elif message == code:  # a bare reason word: say it as words
            message = code.replace("_", " ").capitalize()
        message = message.removeprefix("Invalid input: ").removeprefix("Value error, ")
        if code == "invalid_input" and field and not message.startswith(field):
            message = f"{field}: {message}"
    if field is None and (
        code == "mandate_not_found" or str(body.get("reason", "")).startswith(VERIFY_BAD_ID_PREFIX)
    ):
        field = "mandate_id"
    return {"code": code, "message": message, "field": field}


def with_common_shape(text: str) -> tuple[str, bool]:
    """The tool's answer with the common shape added, and whether it is a refusal."""
    try:
        body = json.loads(text)
    except (TypeError, ValueError):
        return text, False
    if not is_refusal(body):
        return text, False
    for key, value in common_shape(body).items():
        body.setdefault(key, value)
    return json.dumps(body, default=str), True


def _sdk_passes_results_through() -> bool:
    """mcp 1.19 and later (and 2.x) send a CallToolResult a tool returns as it is."""
    try:
        major, minor = (int(part) for part in importlib.metadata.version("mcp").split(".")[:2])
    except (importlib.metadata.PackageNotFoundError, ValueError):
        return False
    return (major, minor) >= (1, 19)


PASSES_RESULTS_THROUGH = _sdk_passes_results_through()


class ToolRefusal(Exception):  # noqa: N818 - named for what the client sees
    """Raised for a refusal on an SDK that cannot take a CallToolResult from a tool:
    the SDK then reports it as an error, with the JSON as its text."""


def error_result(text: str) -> Any:
    """An MCP tool result flagged isError, carrying the JSON as text and as the
    structured {"result": ...} the tool's output schema declares."""
    from mcp.types import CallToolResult

    return CallToolResult.model_validate(
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {"result": text},
            "isError": True,
        }
    )


def report_refusals(tool):
    """Wrap an async tool so that a refusal reaches the MCP client as an error.

    The wrapper keeps the tool's name, docstring and signature, so the SDK builds the same
    input and output schemas.
    """

    @functools.wraps(tool)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        text = await tool(*args, **kwargs)
        shaped, refused = with_common_shape(text)
        if not refused:
            return text
        if PASSES_RESULTS_THROUGH:
            return error_result(shaped)
        raise ToolRefusal(shaped)

    return wrapper
