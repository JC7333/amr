#!/usr/bin/env python3
"""
weekly_pulse.py â€” Routine 5 AMR (v2 robuste).

Tourne tous les dimanches Ã  19h Paris.
Compile l'Ã©tat de la semaine Ã©coulÃ©e sur le repo amr et appelle Claude pour
produire une revue hebdo structurÃ©e.

Sortie : weekly-pulse/YYYY-MM-DD.md uploadÃ© en artifact GitHub.

Robustesse v2 :
- Retry exponentiel sur appels HTTP/API (3 tentatives, backoff 1s/2s/4s).
- Logging structurÃ© (stderr) pour debug.
- Fallback : si une source de donnÃ©es Ã©choue, on continue avec les autres.
- Code de sortie 1 uniquement si Claude API totalement KO (sinon 0 mÃªme partiel).
"""

import os
import sys
import json
import time
import datetime as dt
from pathlib import Path
from typing import Any

import anthropic
import requests


# â”€â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

REPO_OWNER = "JC7333"
REPO_NAME = "amr"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OUTPUT_DIR = Path("weekly-pulse")
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

if not ANTHROPIC_KEY:
    print("FATAL: ANTHROPIC_API_KEY missing", file=sys.stderr)
    sys.exit(1)


# â”€â”€â”€ Utilitaires â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def log(level: str, msg: str) -> None:
    """Logging structurÃ© sur stderr (visible dans GitHub Actions logs)."""
    ts = dt.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] {level:5} {msg}", file=sys.stderr)


def retry_http(fn, *args, retries: int = 3, **kwargs) -> Any:
    """Retry exponentiel sur erreurs HTTP/rÃ©seau. Retourne None si tout Ã©choue."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except (requests.RequestException, requests.Timeout) as e:
            last_exc = e
            wait = 2 ** attempt
            log("WARN", f"HTTP retry {attempt + 1}/{retries} after {wait}s: {e}")
            time.sleep(wait)
    log("ERROR", f"HTTP failed after {retries} retries: {last_exc}")
    return None


# â”€â”€â”€ Collecte des donnÃ©es (chaque source fallback si KO) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_recent_commits(days: int = 7) -> list[dict]:
    """Liste les commits des N derniers jours sur main."""
    if not GH_TOKEN:
        log("WARN", "GH_TOKEN absent, skip commits")
        return []
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"

    def _call():
        r = requests.get(
            url,
            params={"since": since, "sha": "main"},
            headers={"Authorization": f"Bearer {GH_TOKEN}"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    data = retry_http(_call)
    if data is None:
        return []
    return [
        {
            "sha": c["sha"][:7],
            "msg": c["commit"]["message"].split("\n")[0],
            "date": c["commit"]["author"]["date"],
        }
        for c in data
    ]


def get_recent_prs(days: int = 7) -> list[dict]:
    """PRs crÃ©Ã©es ou mergÃ©es dans les N derniers jours."""
    if not GH_TOKEN:
        return []
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls"

    def _call():
        r = requests.get(
            url,
            params={"state": "all", "per_page": 30, "sort": "updated", "direction": "desc"},
            headers={"Authorization": f"Bearer {GH_TOKEN}"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    data = retry_http(_call)
    if data is None:
        return []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    out = []
    for pr in data:
        try:
            updated = dt.datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
            if updated.replace(tzinfo=None) >= cutoff:
                out.append({
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "merged": pr.get("merged_at") is not None,
                    "updated": pr["updated_at"],
                })
        except (KeyError, ValueError) as e:
            log("WARN", f"Skip malformed PR: {e}")
    return out


def get_pipeline_md() -> str:
    """Lit outreach/pipeline.md s'il existe."""
    p = Path("outreach/pipeline.md")
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")[:5000]
    except Exception as e:
        log("WARN", f"Cannot read pipeline.md: {e}")
    return "(pipeline.md absent ou illisible)"


def get_decisions_md() -> str:
    """Lit decisions.md s'il existe (skill decision-log)."""
    p = Path("decisions.md")
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")[:3000]
    except Exception as e:
        log("WARN", f"Cannot read decisions.md: {e}")
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
re-stratÃ©gie globale, reproches moraux. Style oral, asymÃ©trique."""


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


def call_claude_with_retry(client, system, user_prompt, retries: int = 3) -> str | None:
    """Appel Claude avec retry sur erreurs API. None si tout Ã©choue."""
    last_exc = None
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        except (anthropic.APIError, anthropic.APIConnectionError) as e:
            last_exc = e
            wait = 2 ** attempt
            log("WARN", f"Claude retry {attempt + 1}/{retries} after {wait}s: {e}")
            time.sleep(wait)
        except Exception as e:
            log("ERROR", f"Claude unexpected error: {e}")
            return None
    log("ERROR", f"Claude failed after {retries} retries: {last_exc}")
    return None


# â”€â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main() -> int:
    log("INFO", "Starting weekly-pulse")

    log("INFO", "Collecting dataâ€¦")
    commits = get_recent_commits()
    prs = get_recent_prs()
    pipeline = get_pipeline_md()
    decisions = get_decisions_md()
    j_bank = days_to_bank_window()
    log("INFO", f"Collected: {len(commits)} commits, {len(prs)} PRs, J-{j_bank} bank")

    log("INFO", "Calling Claudeâ€¦")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    pulse_md = call_claude_with_retry(
        client, SYSTEM_PROMPT, build_user_prompt(commits, prs, pipeline, decisions, j_bank)
    )

    if pulse_md is None:
        log("ERROR", "Claude API totally down â€” writing fallback")
        pulse_md = f"""# Weekly Pulse â€” {dt.date.today().isoformat()} (FALLBACK)

**âš ï¸ Claude API indisponible. DonnÃ©es brutes ci-dessous, Ã  interprÃ©ter manuellement.**

## Commits 7j
{json.dumps(commits, indent=2, ensure_ascii=False)}

## PRs 7j
{json.dumps(prs, indent=2, ensure_ascii=False)}

## FenÃªtre bancaire
J-{j_bank} avant 30/11/2026.

## Pipeline (extrait)
{pipeline[:1500]}
"""
        # On Ã©crit quand mÃªme un fichier pour que l'artifact ne soit pas vide
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / f"{dt.date.today().isoformat()}-FALLBACK.md"
        out.write_text(pulse_md, encoding="utf-8")
        return 1  # Exit 1 pour signaler l'Ã©chec partiel

    log("INFO", "Writing outputâ€¦")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"{dt.date.today().isoformat()}.md"
    out.write_text(pulse_md, encoding="utf-8")
    log("INFO", f"Written {out} ({len(pulse_md)} chars)")
    log("INFO", "Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
