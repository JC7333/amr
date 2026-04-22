"""AMR - Agent Mandate Registry MCP Server.

Run with: uv run amr
"""

from mcp.server.fastmcp import FastMCP

from amr.config import settings
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import log_action
from amr.tools.verify_mandate import verify_mandate

mcp = FastMCP(settings.server_name)

# Register tools - FastMCP generates schemas from type hints + docstrings
mcp.tool()(create_mandate)
mcp.tool()(verify_mandate)
mcp.tool()(log_action)
mcp.tool()(get_proof)
mcp.tool()(issue_action_token)


def main() -> None:
    """Entry point for the AMR MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
