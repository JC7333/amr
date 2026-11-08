"""Legal figures and status lines of the README stay true (checked against the adopted texts).

Regulation (EU) 2024/1689, Art. 99(4): non-compliance with Art. 26 (deployers) is fined up to
EUR 15 000 000 or 3 % of worldwide annual turnover. EUR 30M / 6 % comes from the 2021 proposal.
Regulation (EU) 2026/1744 moved the high-risk obligations to 2 December 2027 (Annex III) and
2 August 2028 (Annex I).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
DOCS = {
    name: (ROOT / name).read_text(encoding="utf-8")
    for name in ("README.md", "AGENTS.md", "llms.txt")
}
if (ROOT / "CLAUDE.md").is_file():
    DOCS["CLAUDE.md"] = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# Fine figures of the 2021 proposal (EUR 30M / 6 %, EUR 20M / 4 %), in any common spelling.
WRONG_FINES = [
    re.compile(r"(€|EUR)\s?(20|30)\s?(M\b|million|mio|000[ ,.]?000)", re.IGNORECASE),
    re.compile(r"\b(4|6)\s?%\s+(of\s+)?(the\s+)?(global|worldwide|annual|turnover)", re.IGNORECASE),
]
ARTICLE_26 = re.compile(r"Art(icle|\.)?\s?26", re.IGNORECASE)


@pytest.mark.parametrize("name", sorted(DOCS))
def test_no_fine_figure_from_the_2021_proposal(name: str) -> None:
    text = DOCS[name].replace("Never write €30M or 6%", "")
    for pattern in WRONG_FINES:
        assert not pattern.search(text), pattern.search(text).group(0)


@pytest.mark.parametrize(
    "wrong", ["€30M", "EUR 30 million", "€20 million or 4% of worldwide", "6 % of global turnover"]
)
def test_fine_patterns_catch_the_usual_spellings(wrong: str) -> None:
    assert any(pattern.search(wrong) for pattern in WRONG_FINES)


def test_readme_gives_the_adopted_fine_with_its_article() -> None:
    assert README.count("€15 million or 3% of worldwide annual turnover") == 2
    assert README.count("Art. 99(6)") == 2
    assert "Art. 99(4)" in README


@pytest.mark.parametrize("name", sorted(DOCS))
def test_no_august_2026_date_next_to_article_26(name: str) -> None:
    text = DOCS[name]
    for match in re.finditer(r"August 2026", text):
        around = text[max(0, match.start() - 200) : match.end() + 200]
        assert not ARTICLE_26.search(around), around


def test_readme_gives_the_dates_of_regulation_2026_1744() -> None:
    assert "2 December 2027" in README
    assert "2 August 2028" in README
    assert "https://eur-lex.europa.eu/eli/reg/2026/1744/oj" in README


@pytest.mark.parametrize("stale", ["four tools", "in design", "v0.1** *(current)*"])
def test_readme_has_no_stale_status_line(stale: str) -> None:
    assert stale not in README.lower()


def test_readme_lists_no_per_file_test_count() -> None:
    assert not re.search(r"test_\w+\.py\s+#\s*\d+ tests", README)


def test_readme_presents_enforcement_as_shipped() -> None:
    assert "The roadmap leads to **structural enforcement**" not in README
    assert "| ✅ Live |" in README


def test_readme_says_amr_alone_does_not_make_a_system_compliant() -> None:
    assert "does not by itself make a system compliant" in README

def test_readme_does_not_sell_the_open_source_enforcement() -> None:
    # issue_action_token and check_action_token ship in the free Apache-2.0 package
    # (sentence removed at the owner's request, 2026-11-08).
    assert "enforcement layer is the commercial product" not in README.lower()
