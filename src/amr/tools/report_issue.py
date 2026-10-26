"""AMR tool: report_issue.

Lets an agent report a problem with AMR itself, without a person in the loop.

By default it makes no network call: it returns a pre-filled "new issue" link on the
AMR repository that the agent (or its user) opens. Only when the operator has set
AMR_ISSUE_TOKEN does it create the issue itself, with one HTTPS request to the GitHub
REST API. This is the single tool of AMR allowed to reach the network, and only then.

Nothing from the registry is ever attached: the issue holds exactly the title,
description, version and context the caller wrote. Text that looks like a private key
or a signed token is refused, so a secret cannot leave by mistake.
"""

import asyncio
import json
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

# A PEM block (private key, certificate) or a compact JWS (AMR tokens, attestations).
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]+-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
)


def _error(code: str, message: str, **extra: Any) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code, **extra})


class IssueReport(BaseModel):
    """Validated input of report_issue."""

    model_config = {"extra": "forbid"}

    title: str = Field(..., min_length=5, max_length=120)
    description: str = Field(..., min_length=10, max_length=4000)
    version: str = Field(..., min_length=1, max_length=40)
    context: str | None = Field(default=None, max_length=1000)


def _contains_secret(report: IssueReport) -> bool:
    texts = (report.title, report.description, report.version, report.context or "")
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS for text in texts)


def _issue_body(report: IssueReport) -> str:
    lines = [report.description.strip(), "", "---", f"AMR version: {report.version}"]
    if report.context:
        lines.append(f"Context: {report.context.strip()}")
    lines.append("Reported by an agent through the AMR report_issue tool.")
    return "\n".join(lines)


def _prefilled_url(repository: str, title: str, body: str) -> str:
    base = f"{GITHUB_WEB}/{repository}/issues/new"
    url = f"{base}?{urllib.parse.urlencode({'title': title, 'body': body})}"
    if len(url) > MAX_PREFILLED_URL_LENGTH:
        url = f"{base}?{urllib.parse.urlencode({'title': title})}"
    return url


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
    with urllib.request.urlopen(  # noqa: S310 - same fixed https:// request as above
        request, timeout=REQUEST_TIMEOUT_SECONDS
    ) as response:
        return json.loads(response.read().decode("utf-8"))


async def report_issue(
    title: str,
    description: str,
    version: str,
    context: str | None = None,
) -> str:
    """Report a problem with AMR itself (a bug, a confusing error, a missing feature).

    Write only what you observed: the tool name, what you sent, what came back. Never
    paste real mandate contents, personal data, keys or tokens: nothing from the
    registry is attached, and text that looks like a private key or a signed token is
    refused.

    Without AMR_ISSUE_TOKEN set by the operator, no network call is made: the result
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
        report = IssueReport(
            title=title, description=description, version=version, context=context
        )
    except ValidationError as exc:
        return _error("issue_report_invalid", str(exc))
    if _contains_secret(report):
        return _error(
            "issue_contains_secret",
            "the text looks like a private key or a signed token; remove it",
        )

    repository = settings.issue_repository
    title_clean = report.title.strip()
    body = _issue_body(report)
    fallback_url = _prefilled_url(repository, title_clean, body)
    token = settings.issue_token.get_secret_value() if settings.issue_token else ""

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
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
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
