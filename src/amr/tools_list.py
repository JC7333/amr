"""Print the MCP tools/list response of this server, for directories that cannot run it.

Some MCP directories read the tools from the source code and only see decorated
functions; AMR registers its tools in a loop (see server.py), so they show none. They
accept the tools/list response pasted by hand instead. This prints the tools of that
response, as a client receives them, for one profile, from the installed package:

    uv run python -m amr.tools_list                 # profile from AMR_TOOL_PROFILE
    uv run python -m amr.tools_list --profile full  # every tool
    uvx --from mandatia python -m amr.tools_list    # from PyPI, versions after 0.1.2

Nothing is started, written or sent: the tools are registered on a server object that is
never run, listed, and printed as JSON.
"""

import argparse
import asyncio
import json
import sys

from amr.config import settings
from amr.server import TOOL_PROFILES, FastMCP, tools_for


def tool_as_json(tool) -> dict:
    """One tool as the MCP specification writes it: camelCase keys, no null fields."""
    return tool.model_dump(mode="json", by_alias=True, exclude_none=True)


def tools_list(profile: str) -> dict:
    """The tools/list result a client receives from a server started with this profile."""
    server = FastMCP(settings.server_name)
    for tool in tools_for(profile):
        server.tool()(tool)
    tools = asyncio.run(server.list_tools())
    return {"tools": [tool_as_json(tool) for tool in tools]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m amr.tools_list",
        description="Print the MCP tools/list response of this server as JSON.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(TOOL_PROFILES),
        default=settings.tool_profile,
        help="tool profile to list (default: AMR_TOOL_PROFILE or .env, else full)",
    )
    args = parser.parse_args(argv)
    sys.stdout.write(json.dumps(tools_list(args.profile), indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
