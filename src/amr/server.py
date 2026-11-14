"""AMR - Agent Mandate Registry MCP Server.

Run with: uv run amr

AMR_TOOL_PROFILE chooses which tools this server exposes (default "full", every tool):
"principal" for the person or body that grants and revokes mandates, "agent" for the
agent that acts under one, "receiver" for a third party that checks the agent's tokens.
An agent should never be given the principal's tools: an agent that can create, sign or
revoke its own root mandate authorizes itself, and the mandate proves nothing.
"""

try:  # mcp 2.x renamed FastMCP to MCPServer (and kept the decorator and run API used here)
    from mcp.server.mcpserver import MCPServer as FastMCP
except ModuleNotFoundError as exc:  # mcp 1.x has no mcp.server.mcpserver
    if exc.name not in ("mcp", "mcp.server", "mcp.server.mcpserver"):
        raise  # a dependency of mcp 2.x is missing: show that error, not a misleading one
    from mcp.server.fastmcp import FastMCP

try:  # mcp 1.7 added tool annotations; pyproject still allows mcp from 1.2
    from mcp.types import ToolAnnotations
except ImportError:  # older SDK: it cannot send annotations, so tools register without
    ToolAnnotations = None

from amr.config import settings
from amr.tools.attach_signed_mandate_pdf import attach_signed_mandate_pdf
from amr.tools.check_action_token import check_action_token
from amr.tools.contest_action import (
    contest_action,
    list_action_contests,
    prepare_contest_signature,
)
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.issue_mandate_attestation import (
    get_registry_public_key,
    issue_mandate_attestation,
)
from amr.tools.log_action import log_action
from amr.tools.prepare_mandate_pdf import prepare_mandate_pdf
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.report_issue import report_issue
from amr.tools.revoke_mandate import prepare_revocation_signature, revoke_mandate
from amr.tools.verify_mandate import verify_mandate

# Every tool of the server, in the order a client lists them.
TOOLS = (
    create_mandate,
    verify_mandate,
    log_action,
    get_proof,
    issue_action_token,
    check_action_token,
    register_principal_key,
    prepare_mandate_signature,
    prepare_mandate_pdf,
    attach_signed_mandate_pdf,
    issue_mandate_attestation,
    get_registry_public_key,
    export_insurer_dossier,
    revoke_mandate,
    prepare_revocation_signature,
    contest_action,
    prepare_contest_signature,
    list_action_contests,
    report_issue,
)

# Who may call what. "agent" keeps create_mandate for sub-mandates only (see
# create_mandate): an agent may delegate inside its own mandate, never grant itself a root.
TOOL_PROFILES: dict[str, frozenset[str]] = {
    "full": frozenset(tool.__name__ for tool in TOOLS),
    "principal": frozenset(
        {
            "create_mandate",
            "verify_mandate",
            "get_proof",
            "register_principal_key",
            "prepare_mandate_signature",
            "prepare_mandate_pdf",
            "attach_signed_mandate_pdf",
            "issue_mandate_attestation",
            "get_registry_public_key",
            "export_insurer_dossier",
            "revoke_mandate",
            "prepare_revocation_signature",
            "contest_action",
            "prepare_contest_signature",
            "list_action_contests",
            "report_issue",
        }
    ),
    "agent": frozenset(
        {
            "create_mandate",
            "verify_mandate",
            "issue_action_token",
            "log_action",
            "issue_mandate_attestation",
            "get_registry_public_key",
            "report_issue",
        }
    ),
    "receiver": frozenset({"check_action_token", "get_registry_public_key", "report_issue"}),
}


# MCP tool annotations (specification 2025-03-26 onwards, mcp SDK 1.7 onwards), read by
# clients to decide which calls to approve. They are hints, not a security boundary: AMR
# enforces its own rules whatever a client does with them.
#   read-only:   records nothing (no mandate, action, token, contest or key) and sends
#                nothing; like every tool, it may create the empty database on first use.
#   destructive: ends something for good (a revoked mandate is never reactivated).
#   idempotent:  calling again with the same arguments adds nothing more.
#   open world:  may reach the network (only when the operator opts in, see README).
# A tool that writes the registry, creates the signing key or may reach the network is
# never read-only.
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
_APPENDS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

_TOOL_HINTS: dict[str, dict[str, bool]] = {
    "create_mandate": _APPENDS,
    "verify_mandate": _READ_ONLY,
    "log_action": _APPENDS,
    "get_proof": _READ_ONLY,
    "issue_action_token": _APPENDS,
    "check_action_token": _READ_ONLY,
    # did:web principals: the domain is fetched when AMR_DID_WEB_RESOLVE=1.
    "register_principal_key": {**_APPENDS, "openWorldHint": True},
    "prepare_mandate_signature": _READ_ONLY,
    "prepare_mandate_pdf": _READ_ONLY,
    "attach_signed_mandate_pdf": _APPENDS,
    "issue_mandate_attestation": _APPENDS,
    # Creates the registry signing key on the very first call, then only reads it.
    "get_registry_public_key": {**_APPENDS, "idempotentHint": True},
    "export_insurer_dossier": _READ_ONLY,
    "revoke_mandate": {**_APPENDS, "destructiveHint": True},
    "prepare_revocation_signature": _READ_ONLY,
    "contest_action": _APPENDS,
    "prepare_contest_signature": _READ_ONLY,
    "list_action_contests": _READ_ONLY,
    # Files a GitHub issue when the operator sets AMR_ISSUE_TOKEN.
    "report_issue": {**_APPENDS, "openWorldHint": True},
}

TOOL_ANNOTATIONS: dict = (
    {name: ToolAnnotations.model_validate(hints) for name, hints in _TOOL_HINTS.items()}
    if ToolAnnotations is not None
    else {}
)


def tools_for(profile: str) -> tuple:
    """The tools a server started with this profile exposes, in TOOLS order."""
    allowed = TOOL_PROFILES[profile]
    return tuple(tool for tool in TOOLS if tool.__name__ in allowed)


def register_tools(server, profile: str) -> None:
    """Register the tools of this profile on a server, each with its MCP annotations."""
    for tool in tools_for(profile):
        if ToolAnnotations is None:
            server.tool()(tool)
        else:
            server.tool(annotations=TOOL_ANNOTATIONS[tool.__name__])(tool)


mcp = FastMCP(settings.server_name)

# Register tools - FastMCP generates schemas from type hints + docstrings
register_tools(mcp, settings.tool_profile)


def main() -> None:
    """Entry point for the AMR MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
