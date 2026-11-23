"""The hospital scribe example runs end to end, and its documentation matches it."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "scribe_consultation.py"
DOC_EN = ROOT / "docs" / "scribe-example.md"
DOC_FR = ROOT / "docs" / "scribe-example.fr.md"

# One line per checked step: a step that silently stopped being checked fails the test.
EXPECTED_STEPS = (
    "ok: an agent cannot grant itself a root mandate",
    "ok: the principal's key is registered",
    "ok: the signed mandate is registered",
    "ok: the committee decision is recorded with the mandate",
    "ok: authorization granted: consultation.transcribe",
    "ok: authorization granted: note.draft",
    "ok: authorization refused: prescription.create (forbidden:prescription.*)",
    "ok: authorization refused: coding.propose (forbidden:coding.*)",
    "ok: authorization refused: patient_record.export (forbidden:patient_record.export)",
    "ok: authorization refused: patient_record.read (not_allowed:patient_record.read)",
    "ok: authorization granted: note.file, validator and text hash sealed",
    "ok: note.file is in its risk class: 30-second token, registry re-check required",
    "ok: the record system re-checks the registry and accepts the validated note",
    "ok: a note changed after validation is refused (action_mismatch)",
    "ok: the scribe's declaration is logged",
    "ok: the signed withdrawal is registered",
    "ok: no new authorization after the withdrawal",
    "ok: an authorization issued before the withdrawal is refused",
    "ok: the chains and both signatures verify",
    "OK: every step behaved as documented.",
)


@pytest.fixture(scope="module")
def run() -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [sys.executable, str(EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_scribe_example_exits_zero(run: subprocess.CompletedProcess) -> None:
    assert run.returncode == 0, run.stdout + run.stderr


def test_scribe_example_checks_every_step_in_order(run: subprocess.CompletedProcess) -> None:
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    checked = [line for line in lines if line.startswith(("ok: ", "OK: ", "FAILED: "))]
    assert checked == list(EXPECTED_STEPS), run.stdout


def test_scribe_example_prints_the_registry_answers(run: subprocess.CompletedProcess) -> None:
    for tool in (
        "create_mandate (refusal)",
        "register_principal_key",
        "issue_action_token",
        "check_action_token",
        "revoke_mandate",
        "get_proof",
    ):
        assert f": {tool}" in run.stdout, tool


def test_scribe_example_uses_three_profiles() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    for profile in ('"principal"', '"agent"', '"receiver"'):
        assert f"server(stack, env, {profile})" in source, profile


@pytest.mark.parametrize("doc", [DOC_EN, DOC_FR])
def test_scribe_docs_link_the_example_and_state_the_limits(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    assert "examples/scribe_consultation.py" in text
    assert "tests/test_scribe_example.py" in text
    assert ("does not authenticate" in text) or ("n'authentifie pas" in text)
    for word in (
        "opposable",
        "legal mandate",
        "mandat légal",
    ):  # the article number: test_mandate_vocabulary
        assert word not in text, word


def test_readme_points_to_both_scribe_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    linked = set(
        re.findall(
            r"\[`(docs/scribe[\w.-]*)`\]\(https://github\.com/JC7333/amr/blob/main/(docs/scribe[\w.-]*)\)",
            readme,
        )
    )
    assert linked == {
        ("docs/scribe-example.md", "docs/scribe-example.md"),
        ("docs/scribe-example.fr.md", "docs/scribe-example.fr.md"),
    }
    for _, path in linked:
        assert (ROOT / path).is_file(), path


def _example_mandate() -> dict:
    spec = importlib.util.spec_from_file_location("scribe_consultation", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MANDATE


@pytest.mark.parametrize(
    "family",
    ["prescription", "diagnosis", "coding", "patient_record", "letter.send", "patient_message"],
)
def test_example_mandate_never_lists_a_forbidden_act_as_allowed(family: str) -> None:
    # The example must not permit what it shows refused, even if forbidden would still win.
    mandate = _example_mandate()
    assert not any(a.startswith(family) for a in mandate["allowed_actions"]), family
    assert any(f.startswith(family) for f in mandate["forbidden_actions"]), family
