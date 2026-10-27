"""Tests for report_issue: an agent reports a problem with AMR without a person.

No test reaches the network: the module's opener is replaced by a fake that records
each request, and tests that expect no call check that it recorded none.
"""

import ast
import http.client
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from amr.config import Settings, settings
from amr.tools import report_issue as report_issue_module
from amr.tools.report_issue import MAX_PREFILLED_URL_LENGTH, report_issue

ROOT = Path(__file__).resolve().parent.parent
TITLE = "issue_action_token refuses an allowed action"
DESCRIPTION = "Sent action_type report.read under allowed_actions report.*; got denied."


class FakeUrlopen:
    """Stands in for the module's opener (its open method) and records each request."""

    def __init__(self, answer: Any = None, error: BaseException | None = None) -> None:
        self.answer = answer
        self.error = error
        self.requests: list[Any] = []
        self.timeouts: list[Any] = []

    def open(self, request: Any, timeout: Any = None) -> io.BytesIO:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return io.BytesIO(json.dumps(self.answer).encode("utf-8"))


@pytest.fixture
def fake_urlopen(monkeypatch: pytest.MonkeyPatch) -> FakeUrlopen:
    fake = FakeUrlopen(answer={"number": 42, "html_url": "https://github.com/JC7333/amr/issues/42"})
    monkeypatch.setattr(report_issue_module, "_OPENER", fake)
    return fake


@pytest.fixture
def with_token(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "github_pat_test_only_0123456789"  # noqa: S105 - fake value for tests
    monkeypatch.setenv("AMR_ISSUE_TOKEN", token)
    return token


@pytest.fixture(autouse=True)
def no_token_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMR_ISSUE_TOKEN", raising=False)
    monkeypatch.setattr(settings, "issue_repository", "JC7333/amr")


def _query(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


# --- Without a token: no network call, a pre-filled link -------------------------


async def test_without_token_makes_no_network_call(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["status"] == "not_sent"
    assert fake_urlopen.requests == []


async def test_without_token_returns_prefilled_link(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0", context="Cursor, macOS"))
    url = result["new_issue_url"]
    assert url.startswith("https://github.com/JC7333/amr/issues/new?")
    query = _query(url)
    assert query["title"] == [TITLE]
    body = query["body"][0]
    assert DESCRIPTION in body
    assert "AMR version: 0.1.0" in body
    assert "Context: Cursor, macOS" in body
    assert result["issues_url"] == "https://github.com/JC7333/amr/issues"


async def test_empty_token_counts_as_no_token(
    monkeypatch: pytest.MonkeyPatch, fake_urlopen: FakeUrlopen
) -> None:
    for blank in ("", "   "):
        monkeypatch.setenv("AMR_ISSUE_TOKEN", blank)
        result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
        assert result["status"] == "not_sent"
    assert fake_urlopen.requests == []


async def test_token_in_dotenv_file_does_not_switch_network_on(
    fake_urlopen: FakeUrlopen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("AMR_ISSUE_TOKEN=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert not hasattr(Settings(), "issue_token")
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["status"] == "not_sent"
    assert fake_urlopen.requests == []


async def test_long_description_link_keeps_only_the_title(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue(TITLE, "\u00e9 " * 2000, "0.1.0"))
    url = result["new_issue_url"]
    assert len(url) <= MAX_PREFILLED_URL_LENGTH
    assert _query(url) == {"title": [TITLE]}


async def test_short_description_link_keeps_the_body(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue(TITLE, "y" * 1000, "0.1.0"))
    assert "body" in _query(result["new_issue_url"])


# --- With a token: one HTTPS request to the GitHub REST API ------------------------


async def test_with_token_creates_the_issue(fake_urlopen: FakeUrlopen, with_token: str) -> None:
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result == {
        "status": "created",
        "issue_number": 42,
        "issue_url": "https://github.com/JC7333/amr/issues/42",
    }
    assert len(fake_urlopen.requests) == 1


async def test_request_targets_the_configured_repository(
    fake_urlopen: FakeUrlopen, with_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "issue_repository", "someone/fork")
    await report_issue(TITLE, DESCRIPTION, "0.1.0")
    request = fake_urlopen.requests[0]
    assert request.full_url == "https://api.github.com/repos/someone/fork/issues"
    assert request.get_method() == "POST"


async def test_request_carries_token_and_api_headers(
    fake_urlopen: FakeUrlopen, with_token: str
) -> None:
    await report_issue(TITLE, DESCRIPTION, "0.1.0")
    request = fake_urlopen.requests[0]
    assert request.get_header("Authorization") == f"Bearer {with_token}"
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("X-github-api-version") == "2022-11-28"
    assert fake_urlopen.timeouts[0] == report_issue_module.REQUEST_TIMEOUT_SECONDS


async def test_request_body_is_exactly_what_the_caller_wrote(
    fake_urlopen: FakeUrlopen, with_token: str
) -> None:
    await report_issue(TITLE, DESCRIPTION, "0.1.0", context="Claude Code")
    payload = json.loads(fake_urlopen.requests[0].data.decode("utf-8"))
    assert set(payload) == {"title", "body"}
    assert payload["title"] == TITLE
    assert payload["body"] == (
        f"{DESCRIPTION}\n\n---\nAMR version: 0.1.0\nContext: Claude Code\n"
        "Reported by an agent through the AMR report_issue tool."
    )


async def test_result_never_contains_the_token(fake_urlopen: FakeUrlopen, with_token: str) -> None:
    ok = await report_issue(TITLE, DESCRIPTION, "0.1.0")
    fake_urlopen.error = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    failed = await report_issue(TITLE, DESCRIPTION, "0.1.0")
    fake_urlopen.error = ValueError(f"Invalid header value b'Bearer {with_token}'")
    value_error = await report_issue(TITLE, DESCRIPTION, "0.1.0")
    for result in (ok, failed, value_error):
        assert with_token not in result


async def test_invalid_token_through_real_request_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A newline in the token makes http.client refuse the header with a message that
    # quotes it; the opener must fail before any connection and the token stay hidden.
    token = "leak\nme-0123456789"  # noqa: S105 - fake value for tests
    monkeypatch.setenv("AMR_ISSUE_TOKEN", token)

    def no_connect(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a connection was attempted")

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", no_connect)
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"
    assert "leak" not in json.dumps(result)


def test_redirects_are_refused() -> None:
    # urllib would resend the Authorization header to the redirect target.
    handler = report_issue_module._NoRedirect()
    request = urllib.request.Request("https://api.github.com/repos/a/b/issues")
    assert handler.redirect_request(request, None, 302, "Found", {}, "http://evil/") is None
    handlers = report_issue_module._OPENER.handlers
    assert any(isinstance(h, report_issue_module._NoRedirect) for h in handlers)
    assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in handlers)


async def test_redirect_answer_is_not_created(fake_urlopen: FakeUrlopen, with_token: str) -> None:
    fake_urlopen.error = urllib.error.HTTPError("u", 302, "Found", {}, None)
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"


async def test_broken_http_answer_returns_fallback_link(
    fake_urlopen: FakeUrlopen, with_token: str
) -> None:
    fake_urlopen.error = http.client.IncompleteRead(b"")
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"
    assert "new_issue_url" in result


async def test_mentions_do_not_notify_anyone(fake_urlopen: FakeUrlopen, with_token: str) -> None:
    await report_issue(TITLE, "Ping @octocat about #12 please", "0.1.0", context="@team")
    body = json.loads(fake_urlopen.requests[0].data.decode("utf-8"))["body"]
    assert "@" not in body
    assert "#12" not in body
    assert "&#64;octocat" in body
    assert "&#35;12" in body
    assert "&&" not in body


async def test_http_error_returns_fallback_link(fake_urlopen: FakeUrlopen, with_token: str) -> None:
    fake_urlopen.error = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"
    assert "HTTP 403" in result["error"]
    assert result["new_issue_url"].startswith("https://github.com/JC7333/amr/issues/new?")


async def test_unreachable_github_returns_fallback_link(
    fake_urlopen: FakeUrlopen, with_token: str
) -> None:
    fake_urlopen.error = urllib.error.URLError("no route")
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"
    assert "new_issue_url" in result


async def test_timeout_returns_fallback_link(fake_urlopen: FakeUrlopen, with_token: str) -> None:
    fake_urlopen.error = TimeoutError()
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"


@pytest.mark.parametrize(
    "answer",
    [
        {"message": "Validation Failed"},
        {"number": "42", "html_url": "https://github.com/JC7333/amr/issues/42"},
        {"number": 42},
        ["not", "an", "object"],
    ],
)
async def test_unexpected_answer_is_not_reported_as_created(
    fake_urlopen: FakeUrlopen, with_token: str, answer: Any
) -> None:
    fake_urlopen.answer = answer
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0"))
    assert result["code"] == "issue_not_created"


# --- Validation and secrets: refused before any network call ---------------------


@pytest.mark.parametrize(
    ("title", "description", "version", "context"),
    [
        ("bug", DESCRIPTION, "0.1.0", None),
        ("t" * 121, DESCRIPTION, "0.1.0", None),
        (TITLE, "too short", "0.1.0", None),
        ("      ", DESCRIPTION, "0.1.0", None),
        (TITLE, " " * 20, "0.1.0", None),
        (TITLE, "d" * 4001, "0.1.0", None),
        (TITLE, DESCRIPTION, "", None),
        (TITLE, DESCRIPTION, "v" * 41, None),
        (TITLE, DESCRIPTION, "0.1.0", "c" * 1001),
    ],
)
async def test_invalid_input_is_refused(
    fake_urlopen: FakeUrlopen,
    with_token: str,
    title: str,
    description: str,
    version: str,
    context: str | None,
) -> None:
    result = json.loads(await report_issue(title, description, version, context))
    assert result["code"] == "issue_report_invalid"
    assert fake_urlopen.requests == []


def test_model_refuses_unknown_fields() -> None:
    # Nothing beyond the four documented fields can ride along (no mandate data).
    with pytest.raises(ValidationError):
        report_issue_module.IssueReport(
            title=TITLE, description=DESCRIPTION, version="0.1.0", mandate_id="m-1"
        )


async def test_bounds_are_inclusive(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue("t" * 120, "d" * 4000, "v" * 40, "c" * 1000))
    assert result["status"] == "not_sent"
    result = json.loads(await report_issue("t" * 5, "d" * 10, "v", None))
    assert result["status"] == "not_sent"


SECRETS = [
    "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEI",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "token eyJhbGciOiJFZERTQSJ9.eyJpc3MiOiJhbXIifQ.c2lnbmF0dXJlX3ZhbHVl here",
    "split eyJhbGciOiJFZERTQSJ9.eyJpc3Mi\nOiJhbXIifQ.c2lnbmF0dXJl X3ZhbHVl",
    "invisible eyJ\u200bhbGciOiJFZERTQSJ9.eyJpc3MiOiJhbXIifQ.c2lnbmF0dXJlX3ZhbHVl",
    "detached eyJhbGciOiJFZERTQSJ9..c2lnbmF0dXJlX3ZhbHVl",
    "-----BEGIN PRIVATE KEY",
    "MC4CAQAwBQYDK2VwBCIEIGx1dHJlcyBkb25uZWVzIGljaQ",
    "ghp_0123456789abcdefghijABCDEFGHIJ",
    "github_pat_11ABCDEFG0123456789_abcdefghij",
]


@pytest.mark.parametrize("secret", SECRETS)
async def test_secret_in_description_is_refused_as_secret(
    fake_urlopen: FakeUrlopen, with_token: str, secret: str
) -> None:
    result = json.loads(await report_issue(TITLE, f"{DESCRIPTION} {secret}", "0.1.0"))
    assert result["code"] == "issue_contains_secret"
    assert fake_urlopen.requests == []


async def test_secret_in_context_is_refused_as_secret(
    fake_urlopen: FakeUrlopen, with_token: str
) -> None:
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "0.1.0", SECRETS[2]))
    assert result["code"] == "issue_contains_secret"


async def test_secret_in_version_is_refused_as_secret(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue(TITLE, DESCRIPTION, "-----BEGIN EC KEY-----"))
    assert result["code"] == "issue_contains_secret"


async def test_secret_in_title_is_refused_as_secret(fake_urlopen: FakeUrlopen) -> None:
    result = json.loads(await report_issue("key -----BEGIN PRIVATE KEY-----", DESCRIPTION, "1"))
    assert result["code"] == "issue_contains_secret"


async def test_ordinary_dotted_text_is_not_taken_for_a_token(fake_urlopen: FakeUrlopen) -> None:
    text = "Called amr.tools.report_issue.report_issue with report.read.v1 in config.json."
    result = json.loads(await report_issue(TITLE, text, "0.1.0"))
    assert result["status"] == "not_sent"


def test_tool_cannot_read_the_registry() -> None:
    # Nothing from the registry can be attached: the module imports no database code.
    tree = ast.parse((ROOT / "src" / "amr" / "tools" / "report_issue.py").read_text("utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name and (name.startswith("amr.db") or name == "aiosqlite") for name in imported)


# --- Configuration ------------------------------------------------------------------


def test_token_is_not_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMR_ISSUE_TOKEN", "from-env")
    loaded = Settings(_env_file=None)
    assert "from-env" not in repr(loaded)
    assert "issue_token" not in Settings.model_fields


@pytest.mark.parametrize(
    "repository",
    ["JC7333", "a/b/c", "https://evil.example/x", "a b/c", "../x", "a/..", "./b", "../.."],
)
def test_settings_refuse_odd_repository(monkeypatch: pytest.MonkeyPatch, repository: str) -> None:
    monkeypatch.setenv("AMR_ISSUE_REPOSITORY", repository)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_server_registers_report_issue() -> None:
    server = (ROOT / "src" / "amr" / "server.py").read_text(encoding="utf-8")
    assert "mcp.tool()(report_issue)" in server


NETWORK_MODULES = (
    "urllib",
    "http",
    "socket",
    "ssl",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "smtplib",
    "ftplib",
)
NETWORK_CALLS = {"open_connection", "create_connection", "open_unix_connection", "urlopen"}


def _network_uses(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            if node.module == "urllib":
                names = [f"urllib.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Attribute) and node.attr in NETWORK_CALLS:
            found.append(node.attr)
            continue
        else:
            continue
        for name in names:
            if name == "urllib.parse":
                continue  # pure string handling, no network
            if name.split(".")[0] in NETWORK_MODULES:
                found.append(name)
    return found


@pytest.mark.parametrize(
    "source",
    [
        "import urllib\nurllib.request.urlopen('x')",
        "from urllib import request",
        "from http import client",
        "import ssl",
        "import asyncio\nasyncio.open_connection('h', 1)",
        "import socket",
    ],
)
def test_network_detector_sees_indirect_uses(source: str) -> None:
    assert _network_uses(source)


def test_network_detector_allows_urllib_parse() -> None:
    assert _network_uses("import urllib.parse\nfrom urllib.parse import quote") == []


def test_report_issue_is_the_only_module_that_reaches_the_network() -> None:
    # CLAUDE.md rule 5: report_issue is the single, opt-in exception.
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "src" / "amr").rglob("*.py"))
        if _network_uses(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [str(Path("src/amr/tools/report_issue.py"))]
