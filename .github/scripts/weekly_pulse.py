#!/usr/bin/env python3
"""
weekly_pulse.py â€” Routine 5 AMR.

Tourne tous les dimanches Ã  19h Paris.
Compile l'Ã©tat de la semaine Ã©coulÃ©e sur le repo amr (+ accÃ¨s lecture
optionnel Ã  d'autres sources via API GitHub) et appelle Claude pour
produire une revue hebdo structurÃ©e.

Sortie : weekly-pulse/YYYY-MM-DD.md commitÃ© par le workflow GitHub Action.
"""

import os
import json
import subprocess
import datetime as dt
from pathlib import Path

import anthropic
import requests


# â”€â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

REPO_OWNER = "JC7333"
REPO_NAME = "amr"
ANTHROPIC_MODEL = "claude-sonnet-4-6"  # actuel (plus Ã©conomique que Opus pour ce job)
OUTPUT_DIR = Path("weekly-pulse")
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]


# â”€â”€â”€ Collecte des donnÃ©es â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_recent_commits(days: int = 7) -> list[dict]:
    """Liste les commits des N derniers jours sur main."""
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"
    r = requests.get(
        url,
        params={"since": since, "sha": "main"},
        headers={"Authorization": f"Bearer {GH_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    return [
        {
            "sha": c["sha"][:7],
            "msg": c["commit"]["message"].split("\n")[0],
            "date": c["commit"]["author"]["date"],
        }
        for c in r.json()
    ]


def get_recent_prs(days: int = 7) -> list[dict]:
    """PRs crÃ©Ã©es ou mergÃ©es dans les N derniers jours."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls"
    r = requests.get(
        url,
        params={"state": "all", "per_page": 30, "sort": "updated", "direction": "desc"},
        headers={"Authorization": f"Bearer {GH_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    out = []
    for pr in r.json():
        updated = dt.datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        if updated.replace(tzinfo=None) >= cutoff:
            out.append(
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "merged": pr.get("merged_at") is not None,
                    "updated": pr["updated_at"],
                }
            )
    return out


def get_pipeline_md() -> str:
    """Lit outreach/pipeline.md s'il existe."""
    p = Path("outreach/pipeline.md")
    if p.exists():
        return p.read_text(encoding="utf-8")[:5000]
    return "(pipeline.md absent du repo â€” Ã  vÃ©rifier)"


def get_decisions_md() -> str:
    """Lit decisions.md s'il existe (skill decision-log)."""
    p = Path("decisions.md")
    if p.exists():
        return p.read_text(encoding="utf-8")[:3000]
    return "(decisions.md absent â€” skill decision-log non encore utilisÃ©)"


def days_to_bank_window() -> int:
    """Jours restants avant le 30/11/2026 (fenÃªtre crÃ©dit commercial)."""
    deadline = dt.date(2026, 11, 30)
    return (deadline - dt.date.today()).days


# â”€â”€â”€ Prompt Claude â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SYSTEM_PROMPT = """Tu gÃ©nÃ¨res la revue hebdomadaire d'Audric, mÃ©decin
thermaliste Ã  Aix-les-Bains, solo fondateur multi-projets.

Format STRICT, dense, lecture 90 secondes max, en franÃ§ais.

Structure de sortie (markdown) :

# Weekly Pulse â€” {date}

## ðŸ“Š Semaine Ã©coulÃ©e
Pour chaque projet actif avec activitÃ© : 1-2 lignes factuelles, chiffrÃ©es.

## ðŸŽ¯ Ã‰tat des fronts
Pour chacun des 5 fronts (AMR, KORVEX, Ã‰tuve, immo, fenÃªtre bancaire) :
- ðŸ”´ BLOQUANTE (J+7) : [action]
- ðŸŸ¡ CRITIQUE (J+14) : [action]
- ðŸŸ¢ UTILE (J+30) : [action]

## ðŸ“… Plan semaine prochaine
Calendrier crÃ©neaux soir/WE. Audric consulte en journÃ©e.

## â° FenÃªtre bancaire
J-{days} avant 30/11/2026. Ã‰tapes manquantes cochÃ©es. Action cette semaine.

## â“ Sanity check
UNE seule question d'arbitrage Ã  la fin.

INTERDITS : prÃ©ambules, fÃ©licitations, blabla, listes dÃ©coratives,
re-stratÃ©gie globale, reproches moraux.
Style oral, asymÃ©trique. Pas de bullet point dÃ©coratif vide."""


def build_user_prompt(commits, prs, pipeline, decisions, j_bank) -> str:
    return f"""GÃ©nÃ¨re la weekly-pulse d'aujourd'hui.

Date : {dt.date.today().isoformat()}

COMMITS REPO AMR (7j) :
{json.dumps(commits, indent=2, ensure_ascii=False)}

PRS REPO AMR (7j) :
{json.dumps(prs, indent=2, ensure_ascii=False)}

PIPELINE.MD ACTUEL :
{pipeline}

DECISIONS.MD ACTUEL :
{decisions}

FENÃŠTRE BANCAIRE : J-{j_bank} avant 30/11/2026.

GÃ©nÃ¨re la revue maintenant. Sortie markdown brute, pas de prÃ©ambule."""


# â”€â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main() -> None:
    print("â†’ Collecting dataâ€¦")
    commits = get_recent_commits()
    prs = get_recent_prs()
    pipeline = get_pipeline_md()
    decisions = get_decisions_md()
    j_bank = days_to_bank_window()
    print(f"  {len(commits)} commits, {len(prs)} PRs, J-{j_bank} bank window")

    print("â†’ Calling Claudeâ€¦")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(commits, prs, pipeline, decisions, j_bank),
            }
        ],
    )
    pulse_md = "".join(b.text for b in resp.content if b.type == "text")

    print("â†’ Writing outputâ€¦")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"{dt.date.today().isoformat()}.md"
    out.write_text(pulse_md, encoding="utf-8")
    print(f"  Written {out}")

    print("â†’ Done.")


if __name__ == "__main__":
    main()
