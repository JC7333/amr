#!/usr/bin/env python3
"""
weekly_pulse.py â€” Routine 5 AMR (v3 avec veille auto).

Tourne tous les dimanches Ã  19h Paris.
Compile l'Ã©tat de la semaine + gÃ©nÃ¨re une revue ET une veille AMR via
web_search natif Anthropic.

Sortie : weekly-pulse/YYYY-MM-DD.md uploadÃ© en artifact GitHub.

v3 nouveautÃ©s :
- web_search activÃ© cÃ´tÃ© Anthropic API (server-side, gÃ©rÃ© par Claude)
- Veille auto sur concurrents, rÃ©glementaire, marchÃ© AI compliance
- Section "ðŸ”­ Veille AMR cette semaine" ajoutÃ©e au pulse
- max_tokens augmentÃ© Ã  4000 (vs 2000 v2)

CoÃ»t marginal : ~0,1â‚¬/sem (web_search + tokens). 5â‚¬/an total.
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


# â”€â”€â”€ Collecte des donnÃ©es â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    return "(decisions.md absent)"


def days_to_bank_window() -> int:
    """Jours restants avant le 30/11/2026 (fenÃªtre crÃ©dit commercial)."""
    deadline = dt.date(2026, 11, 30)
    return (deadline - dt.date.today()).days


# â”€â”€â”€ Prompt Claude (v3 avec veille) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SYSTEM_PROMPT = """Tu gÃ©nÃ¨res la revue hebdomadaire d'Audric, mÃ©decin
thermaliste Ã  Aix-les-Bains, solo fondateur multi-projets.

Audric construit AMR (mandatia.eu) = registre de mandats pour agents IA
basÃ© sur Art.1984 Code civil + eIDAS 2.0 + EU AI Act. ModÃ¨le freemium :
Tier 0 OSS, Tier 1 350â‚¬/mois (token issuer mandate-gated), Tier 2
enterprise 20-80k/an, Tier 3 templates sectoriels 2-5kâ‚¬/pack.

STRATÃ‰GIE OPTIONALITÃ‰ : Audric continue la mÃ©decine (rente), dÃ©veloppe
AMR intensivement, basculera vers AMR plein temps SI signaux d'attraction
forte se dÃ©clenchent. Signaux Ã  surveiller :
- ðŸŸ¡ >3 inbounds qualifiÃ©s/mois sans outreach actif
- ðŸŸ¡ 1er client Tier 1 signÃ© (350â‚¬/mois ARR)
- ðŸ”´ 1er contrat Tier 2 enterprise 20-80kâ‚¬/an
- ðŸ”´ ARR rÃ©current 100kâ‚¬ confirmÃ©
- ðŸš¨ Offre rachat >2Mâ‚¬
- ðŸš¨ LevÃ©e preempt VC tier 1 sans dÃ©marche

Tu DOIS utiliser web_search pour faire de la veille concurrentielle et
rÃ©glementaire AMR. Recherches ciblÃ©es obligatoires AVANT de gÃ©nÃ©rer
la section "ðŸ”­ Veille AMR cette semaine" :
1. "ArkForge AI compliance" (derniÃ¨re semaine)
2. "OpenBox AI agent runtime" OR "RAMS blockchain mandate"
3. "Vanta OneTrust Drata AI agent" (concurrence indirecte)
4. "EU AI Act Digital Omnibus" (rÃ©glementaire derniÃ¨re semaine)
5. "AI agent compliance startup funding" (levÃ©es/acquisitions)
6. "MCP Model Context Protocol mandate authorization" (signaux Ã©cosystÃ¨me)
7. Une recherche libre selon ce qui semble pertinent cette semaine

Format STRICT, dense, lecture <3 minutes, en franÃ§ais.

Structure de sortie (markdown) :

# Weekly Pulse â€” {date}

## ðŸ“Š Semaine Ã©coulÃ©e
Pour chaque projet actif avec activitÃ© : 1-2 lignes factuelles, chiffrÃ©es.
Si pas d'activitÃ© sur un projet, NE PAS le mentionner.

## ðŸŽ¯ Ã‰tat des fronts
Pour chacun des 5 fronts (AMR, KORVEX, Ã‰tuve, immo, fenÃªtre bancaire) :
- ðŸ”´ BLOQUANTE (J+7) : [action] (ne mettre que si vraiment bloquante)
- ðŸŸ¡ CRITIQUE (J+14) : [action]
- ðŸŸ¢ UTILE (J+30) : [action]
Si rien ne bloque sur un front, Ã©crire "RAS" et passer.

## ðŸ”­ Veille AMR cette semaine
**Concurrents**
- [Concurrent] : [ce qui a bougÃ©] â†’ impact AMR : [phrase courte dÃ©cisionnelle]
**RÃ©glementaire**
- [Ã‰tape AI Act / Digital Omnibus] â†’ impact AMR : [...]
**MarchÃ©**
- [LevÃ©e/acquisition/lancement notable] â†’ impact AMR : [...]
**Signaux faibles Ã  surveiller**
- [Ã€ garder Ã  l'Å“il sans agir maintenant]

Si une recherche ne ramÃ¨ne rien de nouveau, Ã©crire "RAS cette semaine"
pour cette sous-section. Ne pas inventer.

## âš¡ Check signaux de bascule AMR
Ã‰tat courant des 6 signaux :
- ðŸŸ¡ Inbounds qualifiÃ©s (>3/mois) : [N actuel / 3]
- ðŸŸ¡ 1er Tier 1 signÃ© : [oui/non]
- ðŸ”´ 1er Tier 2 enterprise : [oui/non]
- ðŸ”´ ARR 100k confirmÃ© : [oui/non]
- ðŸš¨ Offre rachat >2Mâ‚¬ : [oui/non]
- ðŸš¨ LevÃ©e preempt : [oui/non]
Si UN signal franchi â†’ Ã©crire en gras "âš ï¸ REVUE STRATÃ‰GIQUE DÃ‰CLENCHÃ‰E".

## ðŸ“… Plan semaine prochaine
Calendrier crÃ©neaux soir/WE. Audric consulte en journÃ©e.
Allocation cible AMR ~9-11h/sem : lun/mer/ven soir 21-23h + sam matin 9-12h + dim flex.

## â° FenÃªtre bancaire
J-{days} avant 30/11/2026. Ã‰tape la plus en retard. Action cette semaine si urgente.

## â“ Sanity check
UNE seule question d'arbitrage Ã  la fin (ou rien si rien d'urgent).

INTERDITS : prÃ©ambules, fÃ©licitations, blabla, listes dÃ©coratives,
re-stratÃ©gie globale, reproches moraux. Style oral, asymÃ©trique.
JAMAIS inventer de fait. Si web_search ne ramÃ¨ne rien, dire "RAS"."""


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

INSTRUCTIONS :
1. Effectue les 6-7 recherches web obligatoires pour la section Veille.
2. GÃ©nÃ¨re ensuite la pulse complÃ¨te au format demandÃ©.
3. Sortie markdown brute, pas de prÃ©ambule."""


def call_claude_with_retry(client, system, user_prompt, retries: int = 3) -> str | None:
    """Appel Claude avec web_search + retry sur erreurs API."""
    last_exc = None
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4000,
                system=system,
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 8,  # Limite hard pour Ã©viter dÃ©rapage coÃ»t
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
            # Server-side tool : Claude gÃ¨re lui-mÃªme les itÃ©rations.
            # On extrait uniquement les blocks de type "text" du rÃ©sultat final.
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
    log("INFO", "Starting weekly-pulse v3")

    log("INFO", "Collecting dataâ€¦")
    commits = get_recent_commits()
    prs = get_recent_prs()
    pipeline = get_pipeline_md()
    decisions = get_decisions_md()
    j_bank = days_to_bank_window()
    log("INFO", f"Collected: {len(commits)} commits, {len(prs)} PRs, J-{j_bank} bank")

    log("INFO", "Calling Claude with web_searchâ€¦")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    pulse_md = call_claude_with_retry(
        client, SYSTEM_PROMPT, build_user_prompt(commits, prs, pipeline, decisions, j_bank)
    )

    if pulse_md is None:
        log("ERROR", "Claude API totally down â€” writing fallback")
        pulse_md = f"""# Weekly Pulse â€” {dt.date.today().isoformat()} (FALLBACK)

**âš ï¸ Claude API indisponible. DonnÃ©es brutes ci-dessous.**

## Commits 7j
{json.dumps(commits, indent=2, ensure_ascii=False)}

## PRs 7j
{json.dumps(prs, indent=2, ensure_ascii=False)}

## FenÃªtre bancaire
J-{j_bank} avant 30/11/2026.

## Pipeline (extrait)
{pipeline[:1500]}
"""
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / f"{dt.date.today().isoformat()}-FALLBACK.md"
        out.write_text(pulse_md, encoding="utf-8")
        return 1

    log("INFO", "Writing outputâ€¦")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"{dt.date.today().isoformat()}.md"
    out.write_text(pulse_md, encoding="utf-8")
    log("INFO", f"Written {out} ({len(pulse_md)} chars)")
    log("INFO", "Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
