"""AMR tool: report_issue.

Lets an agent report a problem with AMR itself, without a person in the loop.

By default it makes no network call: it returns a pre-filled "new issue" link on the
AMR repository that the agent (or its user) opens. Only when the operator has set
AMR_ISSUE_TOKEN in the server's process environment does it create the issue itself,
with one HTTPS request to the GitHub REST API (redirects refused). This is the single
tool of AMR allowed to reach the network, and only then. The token is read from the
process environment only, never from a .env file: an agent that can write files in its
working directory cannot switch the network on.

Nothing from the registry is ever attached: the issue holds exactly the title,
description, version and context the caller wrote. Text that contains a PEM block, a
JWS-shaped token (the form of AMR tokens and attestations), a GitHub token or a bare
Ed25519 private key is refused. This is a safety net for those shapes only: it does not
detect other secrets or personal data.
"""

import asyncio
import http.client
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from amr.config import settings

GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"
REQUEST_TIMEOUT_SECONDS = 10
# Pre-filled links longer than this are cut down to the title: browsers and GitHub
# refuse very long URLs.
MAX_PREFILLED_URL_LENGTH = 8000
MAX_RESPONSE_BYTES = 1_000_000
TOKEN_ENV = "AMR_ISSUE_TOKEN"  # noqa: S105 - name of the variable, not a secret

# Matched after whitespace and invisible characters are removed (see _compact).
_SECRET_PATTERNS = (
    # PEM block header: private key, certificate.
    re.compile(r"-----BEGIN"),
    # Compact JWS (AMR tokens, attestations), detached payload included.
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]{8,}"),
    # GitHub tokens, the kind of secret this tool brings in.
    re.compile(r"(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    # Bare PKCS#8 Ed25519 private key body (what follows the PEM header).
    re.compile(r"MC4CAQAwBQYDK2Vw"),
)
_INVISIBLE = re.compile(r"[\s\u200b-\u200f\u2060\ufeff]+")


def _error(code: str, message: str, **extra: Any) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code, **extra})


class IssueReport(BaseModel):
    """Validated input of report_issue."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    title: str = Field(..., min_length=5, max_length=120)
    description: str = Field(..., min_length=10, max_length=4000)
    version: str = Field(..., min_length=1, max_length=40)
    context: str | None = Field(default=None, max_length=1000)


def _contains_secret(report: IssueReport) -> bool:
    texts = (report.title, report.description, report.version, report.context or "")
    compact = [_INVISIBLE.sub("", text) for text in texts]
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS for text in compact)


def _no_mentions(text: str) -> str:
    """Stop @user and #123 from notifying anyone under the operator's identity."""
    return text.replace("#", "&#35;").replace("@", "&#64;")


def _issue_body(report: IssueReport) -> str:
    lines = [
        _no_mentions(report.description),
        "",
        "---",
        f"AMR version: {_no_mentions(report.version)}",
    ]
    if report.context:
        lines.append(f"Context: {_no_mentions(report.context)}")
    lines.append("Reported by an agent through the AMR report_issue tool.")
    return "\n".join(lines)


def _prefilled_url(repository: str, title: str, body: str) -> str:
    base = f"{GITHUB_WEB}/{repository}/issues/new"
    url = f"{base}?{urllib.parse.urlencode({'title': title, 'body': body})}"
    if len(url) > MAX_PREFILLED_URL_LENGTH:
        url = f"{base}?{urllib.parse.urlencode({'title': title})}"
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: urllib would otherwise resend the Authorization header."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post_issue(repository: str, token: str, title: str, body: str) -> dict[str, Any]:
    """Create the issue through the GitHub REST API. Blocking: run in a thread."""
    request = urllib.request.Request(  # noqa: S310 - fixed https:// base, never user input
        f"{GITHUB_API}/repos/{repository}/issues",
        data=json.dumps({"title": title, "body": body}).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"amr/{settings.server_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))


async def report_issue(
    title: str,
    description: str,
    version: str,
    context: str | None = None,
) -> str:
    """Report a problem with AMR itself (a bug, a confusing error, a missing feature).

    Write only what you observed: the tool name, what you sent, what came back. Never
    paste real mandate contents, personal data, keys or tokens: nothing from the
    registry is attached; PEM blocks, JWS-shaped tokens, GitHub tokens and bare Ed25519
    private keys are refused, other secrets are not detected.

    Without AMR_ISSUE_TOKEN in the server's environment, no network call is made: the result
    holds new_issue_url, a pre-filled link to open. With it, the issue is created on
    the AMR repository and its link is returned.

    Args:
        title: Short summary, 5 to 120 characters.
               Example: "issue_action_token refuses an allowed action"
        description: What happened and what you expected, 10 to 4000 characters.
        version: AMR version you run. Example: "0.1.0"
        context: Optional, up to 1000 characters: MCP client, OS, Python version.

    Returns:
        JSON string with key status:
        "not_sent" (no token): new_issue_url, issues_url, message;
        "created": issue_number, issue_url.
        On error: {"error": "...", "code": "..."} with code issue_report_invalid,
        issue_contains_secret or issue_not_created (then new_issue_url as a fallback).
    """
    try:
        report = IssueReport(title=title, description=description, version=version, context=context)
    except ValidationError as exc:
        return _error("issue_report_invalid", str(exc))
    if _contains_secret(report):
        return _error(
            "issue_contains_secret",
            "the text looks like a private key or a signed token; remove it",
        )

    repository = settings.issue_repository
    title_clean = report.title
    body = _issue_body(report)
    fallback_url = _prefilled_url(repository, title_clean, body)
    token = os.environ.get(TOKEN_ENV, "").strip()

    if not token:
        return json.dumps(
            {
                "status": "not_sent",
                "new_issue_url": fallback_url,
                "issues_url": f"{GITHUB_WEB}/{repository}/issues",
                "message": (
                    "No issue token is configured, so AMR made no network call. "
                    "Open new_issue_url to file the issue."
                ),
            }
        )

    try:
        created = await asyncio.to_thread(_post_issue, repository, token, title_clean, body)
    except urllib.error.HTTPError as exc:
        return _error(
            "issue_not_created",
            f"GitHub answered HTTP {exc.code}",
            new_issue_url=fallback_url,
        )
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        TimeoutError,
        OSError,
        ValueError,
    ) as exc:
        return _error(
            "issue_not_created",
            f"GitHub could not be reached ({type(exc).__name__})",
            new_issue_url=fallback_url,
        )
    number = created.get("number") if isinstance(created, dict) else None
    url = created.get("html_url") if isinstance(created, dict) else None
    if not isinstance(number, int) or not isinstance(url, str):
        return _error(
            "issue_not_created",
            "unexpected answer from GitHub",
            new_issue_url=fallback_url,
        )
    return json.dumps({"status": "created", "issue_number": number, "issue_url": url})
