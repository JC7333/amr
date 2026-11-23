"""A hospital scribe under mandate: the whole flow over MCP stdio, three servers, one run.

A fictitious hospital lets an AI scribe transcribe consultations and draft notes and
letters. Three AMR servers share one throw-away registry, each with its own tool profile:

    principal  the person a fictitious committee designated, who signs and withdraws
    agent      the scribe
    receiver   the patient record system that files the note

The run plays, and checks, in this order:

  1. the scribe tries to grant itself a mandate: refused (root_mandate_needs_principal);
  2. the principal registers its key and signs a mandate that records the committee
     decision, lists what the scribe may do and what it may never do, and puts note.file
     in a risk class (30-second tokens, re-checked with the registry by the receiver);
  3. authorizations granted for consultation.transcribe and note.draft, refused for
     prescription.create, coding.propose, patient_record.export and patient_record.read;
  4. an authorization to file a note whose metadata carry who validated it and the
     SHA-256 of the validated text: the record system recomputes the action hash from
     the text it receives and accepts it; the same check with one word changed is
     refused (action_mismatch);
  5. the principal withdraws the mandate with its signature: no new authorization, and
     the record system refuses an authorization issued before the withdrawal;
  6. get_proof: the chains verify.

    uv run python examples/scribe_consultation.py

Exit code 0 only if every step behaved as documented. Nothing leaves the machine: no
real hospital, committee, doctor, scribe or patient record is involved.
"""

import asyncio
import base64
import hashlib
import json
import os
import sys
import tempfile
from contextlib import AsyncExitStack
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TIMEOUT = 60  # seconds, per step
SERVER_CODE = "from amr.server import main; main()"

PRINCIPAL = "org:example-hospital/committee-delegate"
SCRIBE = "agent:example-scribe-1"
RECORD_SYSTEM = "receiver:example-patient-record"

# What the committee decided (fictitious). The registry seals it into the mandate.
ORGAN_DECISION = {
    "body": "Digital strategy committee (fictitious hospital)",
    "title": "Trial of an AI scribe in outpatient consultations",
    "decided_on": date.today().isoformat(),
    "reference": "EXAMPLE-2026-01",
    "authorized_personnel": ["Head of the digital department (example)"],
}

MANDATE = {
    "principal_id": PRINCIPAL,
    "agent_id": SCRIBE,
    "scope": "Transcribe outpatient consultations, draft the note and the letter, file "
    "the note once a doctor has validated it",
    "legal_basis_regulation": "Committee decision",
    "legal_basis_article": "Item 1",
    "duration_hours": 24,
    "allowed_actions": ["consultation.transcribe", "note.draft", "letter.draft", "note.file"],
    "forbidden_actions": [
        "prescription.*",
        "diagnosis.*",
        "coding.*",
        "patient_record.export",
        "patient_record.delete",
        "letter.send",
        "patient_message.send",
        "agent.create",
    ],
    "risk_classes": [
        {
            "name": "filed-in-record",
            "actions": ["note.file"],
            "max_token_seconds": 30,
            "registry_check": True,
        }
    ],
}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def action_hash(action: str, audience: str, metadata: dict, action_type: str) -> str:
    """The receiver's own computation of amr_action_hash (token-issuance-spec.md)."""
    descriptor = {
        "action": action,
        "action_type": action_type,
        "audience": audience,
        "metadata": metadata,
    }
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def call(session: ClientSession, who: str, tool: str, **arguments) -> dict:
    """Call one AMR tool, print the registry's answer, return it as a dict.

    A refusal comes back flagged isError, with the same JSON body (code, message, field).
    """
    result = await asyncio.wait_for(session.call_tool(tool, arguments), TIMEOUT)
    text = result.content[0].text
    flag = " (refusal)" if result.isError else ""
    print(f"\n== {who}: {tool}{flag}\n{text[:500]}{'...' if len(text) > 500 else ''}")
    try:
        return json.loads(text)
    except ValueError:
        return {"error": text}


class StepFailedError(Exception):
    """A step did not behave as documented."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise StepFailedError(message)
    print(f"   ok: {message}")


def refusal_code(answer: dict) -> str | None:
    """The machine word of a refusal, whatever the tool."""
    return answer.get("code") or answer.get("reason")


async def server(stack: AsyncExitStack, env: dict, profile: str) -> ClientSession:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", SERVER_CODE],
        env={**env, "AMR_TOOL_PROFILE": profile},
    )
    read, write = await stack.enter_async_context(stdio_client(params))
    session = await stack.enter_async_context(ClientSession(read, write))
    await asyncio.wait_for(session.initialize(), TIMEOUT)
    return session


async def run(workdir: Path) -> None:
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("AMR_")},
        "AMR_DB_PATH": str(workdir / "scribe.db"),
        "AMR_SIGNING_KEY_PATH": str(workdir / "key.pem"),
        "AMR_PUBLIC_KEY_PATH": str(workdir / "key.pub"),
    }
    async with AsyncExitStack() as stack:
        principal = await server(stack, env, "principal")
        scribe = await server(stack, env, "agent")
        record = await server(stack, env, "receiver")

        print("\n### 1. The scribe tries to grant itself a mandate")
        own = await call(scribe, "scribe", "create_mandate", **MANDATE)
        check(
            refusal_code(own) == "root_mandate_needs_principal",
            "an agent cannot grant itself a root mandate",
        )

        print("\n### 2. The principal registers its key and signs the mandate")
        key = Ed25519PrivateKey.generate()
        public_key = b64url(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        proof = json.dumps(
            {
                "context": "amr.principal_key.v1",
                "principal_id": PRINCIPAL,
                "public_key": public_key,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        registered = await call(
            principal,
            "principal",
            "register_principal_key",
            principal_id=PRINCIPAL,
            public_key=public_key,
            proof_signature=b64url(key.sign(proof)),
        )
        check(registered.get("status") == "registered", "the principal's key is registered")

        decision = json.dumps(
            ORGAN_DECISION, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        mandate_args = {**MANDATE, "metadata": {"organ_decision": decision}}
        prepared = await call(principal, "principal", "prepare_mandate_signature", **mandate_args)
        signature = b64url(key.sign(b64url_decode(prepared["payload_b64url"])))
        mandate = await call(
            principal,
            "principal",
            "create_mandate",
            **mandate_args,
            principal_signature=signature,
            signed_at=prepared["signed_at"],
        )
        check(mandate.get("status") == "created", "the signed mandate is registered")
        check(
            (mandate.get("organ_decision") or {}).get("reference") == "EXAMPLE-2026-01",
            "the committee decision is recorded with the mandate",
        )
        mandate_id = mandate["mandate_id"]

        async def ask(action: str, metadata: dict | None = None) -> dict:
            return await call(
                scribe,
                "scribe",
                "issue_action_token",
                mandate_id=mandate_id,
                agent_id=SCRIBE,
                action=action,
                action_type=action,
                audience=RECORD_SYSTEM,
                action_metadata_json=json.dumps(metadata or {}),
            )

        print("\n### 3. What the scribe may do, and what it may not")
        transcribe = await ask("consultation.transcribe")
        check("token" in transcribe, "authorization granted: consultation.transcribe")
        draft = await ask("note.draft")
        check("token" in draft, "authorization granted: note.draft")
        for action, detail in (
            ("prescription.create", "forbidden:prescription.*"),
            ("coding.propose", "forbidden:coding.*"),
            ("patient_record.export", "forbidden:patient_record.export"),
            ("patient_record.read", "not_allowed:patient_record.read"),
        ):
            refused = await ask(action)
            check(
                "token" not in refused
                and refusal_code(refused) == "action_out_of_scope"
                and refused.get("detail") == detail,
                f"authorization refused: {action} ({detail})",
            )

        print("\n### 4. Filing the note a doctor validated")
        note = "Consultation of the day. Example text, no real patient."
        metadata = {
            "validated_by": "doctor:example-1",
            "note_sha256": hashlib.sha256(note.encode("utf-8")).hexdigest(),
        }
        filing = await ask("note.file", metadata)
        check("token" in filing, "authorization granted: note.file, validator and text hash sealed")
        claims = json.loads(b64url_decode(filing["token"].split(".")[1]))  # read, not verified
        check(
            claims.get("amr_registry_check") is True and claims["exp"] - claims["iat"] <= 30,
            "note.file is in its risk class: 30-second token, registry re-check required",
        )

        # The record system computes the hash itself, from the note it actually receives.
        received = {**metadata, "note_sha256": hashlib.sha256(note.encode()).hexdigest()}
        accepted = await call(
            record,
            "record system",
            "check_action_token",
            token=filing["token"],
            audience=RECORD_SYSTEM,
            expected_action_hash=action_hash("note.file", RECORD_SYSTEM, received, "note.file"),
        )
        check(
            accepted.get("valid") is True and accepted.get("registry_check_required") is True,
            "the record system re-checks the registry and accepts the validated note",
        )

        altered = note.replace("Example", "Changed")
        changed = {**metadata, "note_sha256": hashlib.sha256(altered.encode()).hexdigest()}
        mismatch = await call(
            record,
            "record system",
            "check_action_token",
            token=filing["token"],
            audience=RECORD_SYSTEM,
            expected_action_hash=action_hash("note.file", RECORD_SYSTEM, changed, "note.file"),
        )
        check(
            mismatch.get("valid") is False and mismatch.get("reason") == "action_mismatch",
            "a note changed after validation is refused (action_mismatch)",
        )

        logged = await call(
            scribe,
            "scribe",
            "log_action",
            mandate_id=mandate_id,
            action="note.file",
            evidence="note_sha256:" + metadata["note_sha256"],
            result="filed",
            action_token=filing["token"],
        )
        check(logged.get("status") == "logged", "the scribe's declaration is logged")

        print("\n### 5. The principal withdraws the mandate")
        reason = "End of the trial"
        to_sign = await call(
            principal,
            "principal",
            "prepare_revocation_signature",
            mandate_id=mandate_id,
            reason=reason,
        )
        revoked = await call(
            principal,
            "principal",
            "revoke_mandate",
            mandate_id=mandate_id,
            reason=reason,
            principal_signature=b64url(key.sign(b64url_decode(to_sign["payload_b64url"]))),
            signed_at=to_sign["signed_at"],
        )
        check(revoked.get("status") == "revoked", "the signed withdrawal is registered")

        after = await ask("note.draft")
        check("token" not in after, "no new authorization after the withdrawal")
        old = await call(
            record,
            "record system",
            "check_action_token",
            token=transcribe["token"],
            audience=RECORD_SYSTEM,
        )
        check(
            old.get("valid") is False and old.get("reason") == "mandate_status_revoked",
            "an authorization issued before the withdrawal is refused",
        )

        print("\n### 6. The proof")
        proof_pack = await call(principal, "principal", "get_proof", mandate_id=mandate_id)
        integrity = proof_pack.get("chain_integrity", {})
        check(
            integrity.get("actions_chain_valid") is True
            and integrity.get("principal_signature_valid") is True
            and integrity.get("revocation_signature_valid") is True,
            "the chains and both signatures verify",
        )
    print("\nOK: every step behaved as documented.")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            asyncio.run(run(Path(tmp)))
        except* StepFailedError as failed:
            while isinstance(failed, BaseExceptionGroup):
                failed = failed.exceptions[0]
            print(f"FAILED: {failed}")
            sys.exit(1)


if __name__ == "__main__":
    main()
