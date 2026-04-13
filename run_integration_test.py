"""AMR Integration Test - validates all 4 MCP tools end-to-end."""
import asyncio
import json
import os
from pathlib import Path

# Set DB path BEFORE importing tools (settings is a module-level singleton)
os.environ["AMR_DB_PATH"] = str(Path("test_integration.db"))
Path("test_integration.db").unlink(missing_ok=True)

from amr.tools.create_mandate import create_mandate  # noqa: E402
from amr.tools.get_proof import get_proof  # noqa: E402
from amr.tools.log_action import log_action  # noqa: E402
from amr.tools.verify_mandate import verify_mandate  # noqa: E402


async def test() -> None:
    """Run the full integration test against all 4 AMR tools."""
    # 1. Create mandate
    r = json.loads(
        await create_mandate(
            principal_id="user:audric",
            agent_id="agent:korvex",
            scope="Compare financial products",
            legal_basis_regulation="Contract",
            legal_basis_article="Mandat conseil 2026-042",
            duration_hours=720,
        )
    )
    if "error" in r:
        raise RuntimeError(f"create_mandate failed: {r['error']}")
    print(f"1. Mandate created: {r['mandate_id'][:8]}")

    # 2. Verify mandate
    r2 = json.loads(
        await verify_mandate(agent_id="agent:korvex", action="send reco")
    )
    if "error" in r2:
        raise RuntimeError(f"verify_mandate failed: {r2['error']}")
    print(f"2. Verified: {r2['authorized']}")

    # 3. Log action
    r3 = json.loads(
        await log_action(
            mandate_id=r["mandate_id"],
            action="Sent reco Product X",
            evidence="email:msg_123",
            result="Delivered",
        )
    )
    if "error" in r3:
        raise RuntimeError(f"log_action failed: {r3['error']}")
    print(f"3. Action logged: {r3['action_id'][:8]}")

    # 4. Get proof
    r4 = json.loads(await get_proof(mandate_id=r["mandate_id"]))
    if "error" in r4:
        raise RuntimeError(f"get_proof failed: {r4['error']}")
    print(f"4. Proof Pack: {r4['chain_integrity']}")

    # Cleanup
    Path("test_integration.db").unlink(missing_ok=True)
    Path("test_integration.db-wal").unlink(missing_ok=True)
    Path("test_integration.db-shm").unlink(missing_ok=True)
    print()
    print("ALL 4 TOOLS WORKING")


asyncio.run(test())
