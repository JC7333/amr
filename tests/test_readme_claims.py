"""Legal figures and status lines of the README stay true (checked against the adopted texts).

Regulation (EU) 2024/1689, Art. 99(4): non-compliance with Art. 26 (deployers) is fined up to
EUR 15 000 000 or 3 % of worldwide annual turnover. EUR 30M / 6 % comes from the 2021 proposal.
Regulation (EU) 2026/1744 moved the high-risk obligations to 2 December 2027 (Annex III) and
2 August 2028 (Annex I).
"""

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


@pytest.mark.parametrize("name", sorted(DOCS))
def test_no_fine_figure_from_the_2021_proposal(name: str) -> None:
    text = DOCS[name].replace("Never write €30M or 6%", "")
    for wrong in ("€30M", "30M", "6% global", "6% of global", "30 000 000", "30,000,000"):
        assert wrong not in text, wrong


def test_readme_gives_the_adopted_fine_with_its_article() -> None:
    assert README.count("€15 million or 3% of worldwide annual turnover") == 2
    assert "Art. 99(4)" in README


@pytest.mark.parametrize("name", sorted(DOCS))
def test_no_august_2026_date_for_article_26(name: str) -> None:
    assert "August 2026" not in DOCS[name]
    assert "effective August" not in DOCS[name]


def test_readme_gives_the_dates_of_regulation_2026_1744() -> None:
    assert "2 December 2027" in README
    assert "2 August 2028" in README
    assert "https://eur-lex.europa.eu/eli/reg/2026/1744/oj" in README


@pytest.mark.parametrize(
    "stale", ["four tools", "In design", "v0.1** *(current)*", "test_crypto.py           # 7 tests"]
)
def test_readme_has_no_stale_status_line(stale: str) -> None:
    assert stale not in README


def test_readme_says_amr_alone_does_not_make_a_system_compliant() -> None:
    assert "does not by itself make a system compliant" in README
