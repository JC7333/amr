# Example: a hospital scribe under mandate

[Version française](scribe-example.fr.md)

[`examples/scribe_consultation.py`](../examples/scribe_consultation.py) plays, on your
machine, what happens when a hospital lets an AI scribe help in consultations. The
hospital, its committee, the doctor, the scribe and the patient record are all made up.

```bash
git clone https://github.com/JC7333/amr.git && cd amr && uv sync
uv run python examples/scribe_consultation.py   # prints every answer, ends with "OK"
```

Three AMR servers share one throw-away registry. Each sees only the tools of its role:

- the **principal**, the person the committee designated, who signs and withdraws;
- the **scribe**, the agent;
- the **record system**, which receives the note and files it.

## What the run shows

1. **The scribe cannot authorize itself.** It asks for its own mandate and is refused
   (`root_mandate_needs_principal`): an agent can only act under a mandate someone gave it.
2. **The principal signs the mandate.** It registers its key once, then signs a mandate
   that records the committee decision (body, title, date, reference, who it designates).
   The scribe may transcribe, draft the note, draft the letter, and file the note. It may
   never prescribe, diagnose, code, export or delete a record, send a letter, write to a
   patient, or create another agent. Filing a note is in a risk class: its authorization
   lasts 30 seconds and the record system must re-check it with the registry.
3. **Before each act, the scribe asks for an authorization.** Granted for transcribing
   and drafting. Refused for a prescription, a coding proposal and an export (forbidden),
   and for reading the record (not in the mandate).
4. **Filing the note a doctor validated.** The scribe asks for an authorization whose
   details carry who validated the note and the SHA-256 of the validated text. The
   record system does not take these details from the scribe: it rebuilds them from what
   it knows itself, the doctor logged in to its session and the text it received, and
   asks the registry: accepted. If the text it received has one word changed, the
   fingerprint no longer matches: refused (`action_mismatch`). In the script, the logged-in
   doctor and the received text are written by hand; in real life they come from the
   record system itself. The scribe then declares the filing in
   the log, with the authorization it used.
5. **The principal withdraws the mandate**, with its signature. The scribe gets no new
   authorization, and the record system refuses an authorization issued before the
   withdrawal (`mandate_status_revoked`).
6. **The proof.** `get_proof` returns the mandate, the committee decision, the
   scribe's declaration and the withdrawal, and checks that the action chain, the
   principal's signature of the mandate and its signature of the withdrawal verify.

The test suite runs the example (`tests/test_scribe_example.py`).

## What the example does not show

- It is not a real scribe and not a real patient record: no consultation is transcribed,
  no record is touched, no medical data is used.
- The registry writes down the validator the scribe declares. It does not authenticate
  that doctor. The record system is the one that compares the validator and the text
  with what it knows (who is logged in, which text it receives).
- The log holds what the scribe declares it did. It is a declaration, not a proof that
  the act took place.
- AMR does not make a hospital compliant with any text, and this is not legal advice.
