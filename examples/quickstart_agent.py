"""Quickstart for agents: the whole AMR flow over MCP stdio, in one run.

Starts the AMR server as a child process (a throw-away database), then:
create a mandate, verify it, log an action, issue a signed attestation, check it
offline, revoke the mandate, verify again, and print the proof.

    uv run python examples/quickstart_agent.py

Exit code 0 only if every step behaved as documented. Nothing leaves the machine.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TIMEOUT = 60  # seconds, per step
SERVER_CODE = "from amr.server import main; main()"


async def call(session: ClientSession, tool: str, **arguments) -> dict:
    """Call one AMR tool and return its JSON result."""
    result = await asyncio.wait_for(session.call_tool(tool, arguments), TIMEOUT)
    text = result.content[0].text
    print(f"\n== {tool}\n{text[:600]}{'...' if len(text) > 600 else ''}")
    return json.loads(text)


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAILED: {message}")
        sys.exit(1)


async def run(workdir: Path) -> None:
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("AMR_")},
        "AMR_DB_PATH": str(workdir / "quickstart.db"),
        "AMR_SIGNING_KEY_PATH": str(workdir / "key.pem"),
        "AMR_PUBLIC_KEY_PATH": str(workdir / "key.pub"),
    }
    params = StdioServerParameters(command=sys.executable, args=["-c", SERVER_CODE], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await asyncio.wait_for(session.initialize(), TIMEOUT)

        mandate = await call(
            session,
            "create_mandate",
            principal_id="org:example-clinic",
            agent_id="agent:scheduler-1",
            scope="Book and move appointments in the clinic calendar",
            legal_basis_regulation="Service agreement",
            legal_basis_article="Clause 4",
            duration_hours=24,
            allowed_actions=["appointment.book", "appointment.move"],
            forbidden_actions=["prescription.*"],
        )
        check(mandate.get("status") == "created", "create_mandate did not create")
        mandate_id = mandate["mandate_id"]

        # verify_mandate only looks for an active mandate of this agent; the perimeter is
        # enforced by issue_action_token, not here.
        verified = await call(
            session, "verify_mandate", agent_id="agent:scheduler-1", action="appointment.book"
        )
        check(verified.get("authorized") is True, "verify_mandate should authorize")

        logged = await call(
            session,
            "log_action",
            mandate_id=mandate_id,
            action="appointment.book",
            evidence="calendar:event-1",
            result="booked",
        )
        check(logged.get("status") == "logged", "log_action did not log")

        key = await call(session, "get_registry_public_key")
        attestation = await call(
            session,
            "issue_mandate_attestation",
            mandate_id=mandate_id,
            agent_id="agent:scheduler-1",
            audience="receiver:example",
        )
        check("attestation" in attestation, "no attestation issued")
        (workdir / "attestation.jws").write_text(attestation["attestation"], encoding="utf-8")
        (workdir / "registry.pub").write_text(key["public_key_pem"], encoding="utf-8")

        offline = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "amr.verify_attestation",
            str(workdir / "attestation.jws"),
            "--public-key",
            str(workdir / "registry.pub"),
            "--audience",
            "receiver:example",
            stdout=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(offline.communicate(), TIMEOUT)
        print(f"\n== offline check (no registry call)\n{out.decode()[:300]}")
        check(
            offline.returncode == 0 and json.loads(out)["valid"] is True,
            "offline check should accept the attestation",
        )

        revoked = await call(
            session, "revoke_mandate", mandate_id=mandate_id, reason="quickstart: stop button"
        )
        check(revoked.get("status") == "revoked", "revoke_mandate did not revoke")

        after = await call(
            session, "verify_mandate", agent_id="agent:scheduler-1", action="appointment.book"
        )
        check(after.get("authorized") is False, "a revoked mandate must not verify")

        proof = await call(session, "get_proof", mandate_id=mandate_id)
        check("error" not in proof, "get_proof returned an error")
    print("\nOK: every step behaved as documented.")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run(Path(tmp)))


if __name__ == "__main__":
    main()
