#!/usr/bin/env python3
"""
weekly_pulse.py â€” Routine 5 AMR (v4.1 â€” fix encoding UTF-8 + max_tokens).

Tourne tous les dimanches Ã  9h Paris.
Compile l'Ã©tat de la semaine + gÃ©nÃ¨re revue ET veille AMR via web_search
ET envoie le pulse par mail Ã  audric9@gmail.com.

Sortie : 
- artifact GitHub (backup, accessible depuis Actions)
- mail HTML Ã  audric9@gmail.com
- summary GitHub Actions (pour debug)

v4.1 fixes (par rapport Ã  v4) :
- Encoding UTF-8 explicite sur Subject/From (fini les "Ã°Å¸Å¸Â¢" mojibake)
- max_tokens 4500 â†’ 8000 (fini les pulses tronquÃ©s mi-phrase)
- Le reste inchangÃ© : cross-checking + envoi mail + alert level

v4 nouveautÃ©s :
- Cross-checking obligatoire : 2 sources MINIMUM par fait, sinon marquage "âš ï¸ Ã€ VÃ‰RIFIER"
- Envoi mail HTML + text fallback via SMTP Gmail
- Sujet mail prÃ©fixÃ© par niveau d'alerte le plus haut dÃ©tectÃ©
- Pulse persistant : artifact + mail (double sÃ©curitÃ©)
- TolÃ©rance erreur mail : pulse gÃ©nÃ©rÃ© mÃªme si SMTP KO

CoÃ»t marginal : ~0.13â‚¬/run = 7â‚¬/an. InchangÃ© v3.
"""

import os
import sys
import json
import time
import smtplib
import datetime as dt
from pathlib import Path
from typing import Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr

import anthropic
import requests


# â”€â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

REPO_OWNER = "JC7333"
REPO_NAME = "amr"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OUTPUT_DIR = Path("weekly-pulse")

GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Mail config
GMAIL_USER = os.environ.get("GMAIL_USER", "audric9@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
MAIL_TO = "audric9@gmail.com"
MAIL_FROM_NAME = "Pulse AMR"

if not ANTHROPIC_KEY:
    print("FATAL: ANTHROPIC_API_KEY missing", file=sys.stderr)
    sys.exit(1)


# â”€â”€â”€ Utilitaires â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def log(level: str, msg: str) -> None:
    ts = dt.datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] {level:5} {msg}", file=sys.stderr)


def retry_http(fn, *args, retries: int = 3, **kwargs) -> Any:
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
    if not GH_TOKEN:
        log("WARN", "GH_TOKEN absent, skip commits")
        return []
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"

    def _call():
        r = requests.get(
            url, params={"since": since, "sha": "main"},
            headers={"Authorization": f"Bearer {GH_TOKEN}"}, timeout=20,
        )
        r.raise_for_status()
        return r.json()

    data = retry_http(_call)
    if data is None:
        return []
    return [
        {"sha": c["sha"][:7], "msg": c["commit"]["message"].split("\n")[0],
         "date": c["commit"]["author"]["date"]}
        for c in data
    ]


def get_recent_prs(days: int = 7) -> list[dict]:
    if not GH_TOKEN:
        return []
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls"

    def _call():
        r = requests.get(
            url,
            params={"state": "all", "per_page": 30, "sort": "updated", "direction": "desc"},
            headers={"Authorization": f"Bearer {GH_TOKEN}"}, timeout=20,
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
                    "number": pr["number"], "title": pr["title"],
                    "state": pr["state"], "merged": pr.get("merged_at") is not None,
                    "updated": pr["updated_at"],
                })
        except (KeyError, ValueError) as e:
            log("WARN", f"Skip malformed PR: {e}")
    return out


def get_pipeline_md() -> str:
    p = Path("outreach/pipeline.md")
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")[:5000]
    except Exception as e:
        log("WARN", f"Cannot read pipeline.md: {e}")
    return "(pipeline.md absent ou illisible)"


def get_decisions_md() -> str:
    p = Path("decisions.md")
    try:
        if p.exists():
            return p.read_text(encoding="utf-8")[:3000]
    except Exception as e:
        log("WARN", f"Cannot read decisions.md: {e}")
    return "(decisions.md absent)"


def days_to_bank_window() -> int:
    deadline = dt.date(2026, 11, 30)
    return (deadline - dt.date.today()).days


# â”€â”€â”€ Prompt Claude (v4 avec cross-checking) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
RÃˆGLE FONDAMENTALE â€” CROSS-CHECKING DES SOURCES
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

Chaque fait que tu rapportes DOIT Ãªtre :
- Soit confirmÃ© par MINIMUM 2 sources indÃ©pendantes â†’ tu cites les deux
- Soit marquÃ© "âš ï¸ Ã€ VÃ‰RIFIER" en gras avec la source unique mentionnÃ©e
- JAMAIS d'affirmation sans source

Pour les actualitÃ©s rÃ©glementaires (AI Act, Digital Omnibus, eIDAS),
PRIVILÃ‰GIER les sources primaires : Parlement europÃ©en, Conseil EU,
Commission, EUR-Lex, communiquÃ©s officiels. Les articles dÃ©rivÃ©s
(Euractiv, Politico, Sifted) sont OK comme 2e confirmation, jamais
comme seule source.

Pour les levÃ©es de fonds et acquisitions, vÃ©rifier sur Crunchbase OU
TechCrunch OU site officiel de l'entreprise.

Si une info paraÃ®t surprenante (date qui contredit ce que je connais,
chiffre exceptionnel), TRIPLE-CHECK avec 3 sources avant de l'affirmer.
Si impossible â†’ marquer "âš ï¸ Ã€ VÃ‰RIFIER - source unique X, contradiction
possible avec [info connue]".

INTERDIT : inventer des dates prÃ©cises, des montants exacts, des noms de
personnes ou de sociÃ©tÃ©s non confirmÃ©s par recherche.

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
RECHERCHES OBLIGATOIRES (utilise web_search)
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

AVANT de gÃ©nÃ©rer la section "ðŸ”­ Veille AMR", tu DOIS effectuer ces
recherches :
1. "ArkForge AI compliance" + variantes (derniÃ¨re semaine)
2. "OpenBox AI agent runtime" OR "Mastra AI agent governance"
3. "Vanta OneTrust Drata AI agent compliance" (concurrence indirecte)
4. "EU AI Act Digital Omnibus 2026" + "Annex III deadline"
5. "AI agent compliance startup funding 2026" (levÃ©es/acquisitions)
6. "MCP Model Context Protocol authorization mandate"
7. Recherche libre selon ce qui semble pertinent

Si une recherche ramÃ¨ne un fait majeur (deadline modifiÃ©e, concurrent
qui pivote, grosse levÃ©e), AJOUTER une recherche de confirmation
ciblÃ©e sur cette info prÃ©cise.

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
STRUCTURE DE SORTIE (markdown strict, <3 min lecture)
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# Weekly Pulse â€” {date}

**Niveau d'alerte global : [ðŸš¨ / ðŸ”´ / ðŸŸ¡ / ðŸŸ¢]**
(Le niveau le plus haut atteint dans le pulse. Sert au tri rapide.)

## ðŸ“Š Semaine Ã©coulÃ©e
Pour chaque projet actif avec activitÃ© : 1-2 lignes factuelles, chiffrÃ©es.
Si pas d'activitÃ©, NE PAS le mentionner.

## ðŸŽ¯ Ã‰tat des fronts
Pour chacun des 5 fronts (AMR, KORVEX, Ã‰tuve, immo, fenÃªtre bancaire) :
- ðŸ”´ BLOQUANTE (J+7) : [action]
- ðŸŸ¡ CRITIQUE (J+14) : [action]
- ðŸŸ¢ UTILE (J+30) : [action]
Si rien sur un front, Ã©crire "RAS".

## ðŸ”­ Veille AMR cette semaine
**Concurrents**
- [Concurrent] : [ce qui a bougÃ©] [sources : url1, url2] â†’ impact AMR : [phrase courte]
**RÃ©glementaire**
- [Ã‰tape AI Act / Digital Omnibus] [sources : url1, url2] â†’ impact AMR : [...]
**MarchÃ©**
- [LevÃ©e/acquisition] [sources : url1, url2] â†’ impact AMR : [...]
**Signaux faibles Ã  surveiller**
- [Ã€ garder Ã  l'Å“il] [source : url] (1 source suffit pour signaux faibles)

Pour chaque item, **EXPLICITER LES SOURCES** entre crochets.
Si une info est marquÃ©e "âš ï¸ Ã€ VÃ‰RIFIER", expliquer pourquoi.

## âš¡ Check signaux de bascule AMR
Ã‰tat courant des 6 signaux :
- ðŸŸ¡ Inbounds qualifiÃ©s (>3/mois) : [N actuel / 3]
- ðŸŸ¡ 1er Tier 1 signÃ© : [oui/non]
- ðŸ”´ 1er Tier 2 enterprise : [oui/non]
- ðŸ”´ ARR 100k confirmÃ© : [oui/non]
- ðŸš¨ Offre rachat >2Mâ‚¬ : [oui/non]
- ðŸš¨ LevÃ©e preempt : [oui/non]
Si UN signal franchi â†’ "**âš ï¸ REVUE STRATÃ‰GIQUE DÃ‰CLENCHÃ‰E**".

## ðŸ“… Plan semaine prochaine
Calendrier crÃ©neaux soir/WE. Audric consulte en journÃ©e.
Allocation cible AMR ~9-11h/sem : lun/mer/ven soir 21-23h + sam matin
9-12h + dim flex.

## â° FenÃªtre bancaire
J-{days} avant 30/11/2026. Ã‰tape la plus en retard. Action si urgente.

## ðŸŽ¯ Actions de mise Ã  jour suggÃ©rÃ©es
Si la veille a remontÃ© des infos qui impactent ton messaging, ton site,
tes skills :
- [mandatia.eu] : [description du changement suggÃ©rÃ©] (prioritÃ© : ðŸ”´/ðŸŸ¡/ðŸŸ¢)
- [skill amr-core] : [description] (prioritÃ© : ...)
- [skill amr-outreach] : [description] (prioritÃ© : ...)
- [LinkedIn] : [suggestion Ã  valider manuellement] (prioritÃ© : ...)

Si rien Ã  suggÃ©rer, Ã©crire "Aucune mise Ã  jour nÃ©cessaire cette semaine."

## â“ Sanity check
UNE seule question d'arbitrage stratÃ©gique (ou rien si rien d'urgent).

â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

INTERDITS : prÃ©ambules, fÃ©licitations, blabla, listes dÃ©coratives,
re-stratÃ©gie globale, reproches moraux. Style oral, asymÃ©trique, dense.
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
2. CROSS-CHECK chaque fait avec MINIMUM 2 sources, sinon marque "âš ï¸ Ã€ VÃ‰RIFIER".
3. DÃ©termine le niveau d'alerte global (le plus haut dÃ©tectÃ©).
4. GÃ©nÃ¨re la pulse complÃ¨te au format demandÃ©.
5. Sortie markdown brute, pas de prÃ©ambule."""


def call_claude_with_retry(client, system, user_prompt, retries: int = 3) -> str | None:
    last_exc = None
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8000,
                system=system,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 12,  # +4 vs v3 pour permettre les triple-checks
                }],
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


# â”€â”€â”€ Email â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def detect_alert_level(pulse_md: str) -> str:
    """DÃ©tecte le niveau d'alerte le plus haut dans le pulse."""
    if "ðŸš¨" in pulse_md or "REVUE STRATÃ‰GIQUE DÃ‰CLENCHÃ‰E" in pulse_md:
        return "ðŸš¨"
    if "ðŸ”´" in pulse_md:
        return "ðŸ”´"
    if "ðŸŸ¡" in pulse_md:
        return "ðŸŸ¡"
    return "ðŸŸ¢"


def markdown_to_html(md: str) -> str:
    """Conversion markdownâ†’HTML minimaliste, propre pour mail."""
    html_lines = []
    in_list = False
    for line in md.split("\n"):
        line = line.rstrip()
        # Headers
        if line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<h1 style="color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:8px;">{line[2:]}</h1>')
        elif line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<h2 style="color:#2d3748;margin-top:24px;">{line[3:]}</h2>')
        elif line.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<h3 style="color:#4a5568;">{line[4:]}</h3>')
        # Bold
        elif line.startswith("**") and line.endswith("**"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<p><strong>{line[2:-2]}</strong></p>')
        # Lists
        elif line.startswith("- "):
            if not in_list:
                html_lines.append('<ul style="line-height:1.6;">')
                in_list = True
            # Inline bold within list items
            content = line[2:]
            while "**" in content:
                content = content.replace("**", "<strong>", 1)
                content = content.replace("**", "</strong>", 1)
            html_lines.append(f"<li>{content}</li>")
        # Empty line
        elif line == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
        # Paragraph
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            # Inline bold
            content = line
            while "**" in content:
                content = content.replace("**", "<strong>", 1)
                content = content.replace("**", "</strong>", 1)
            html_lines.append(f"<p>{content}</p>")
    if in_list:
        html_lines.append("</ul>")

    body = "\n".join(html_lines)
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Pulse AMR</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
             max-width:700px;margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.5;">
{body}
<hr style="margin-top:32px;border:none;border-top:1px solid #ddd;">
<p style="color:#888;font-size:12px;">Pulse AMR gÃ©nÃ©rÃ© automatiquement â€” routine GitHub Actions weekly-pulse.<br>
Source : github.com/JC7333/amr/actions</p>
</body></html>"""


def send_mail(pulse_md: str, alert_level: str) -> bool:
    """Envoie le pulse par mail. Retourne True si succÃ¨s."""
    if not GMAIL_APP_PASSWORD:
        log("WARN", "GMAIL_APP_PASSWORD absent â€” skip mail")
        return False

    today = dt.date.today().strftime("%d/%m/%Y")
    subject = f"{alert_level} Pulse AMR â€” {today}"

    msg = MIMEMultipart("alternative")
    # Encodage UTF-8 explicite pour subject et From (sinon Gmail affiche mojibake)
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(MAIL_FROM_NAME, "utf-8")), GMAIL_USER))
    msg["To"] = MAIL_TO

    text_part = MIMEText(pulse_md, "plain", "utf-8")
    html_part = MIMEText(markdown_to_html(pulse_md), "html", "utf-8")
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        log("INFO", f"Mail envoyÃ© Ã  {MAIL_TO} (subject: {subject})")
        return True
    except Exception as e:
        log("ERROR", f"Mail failed: {e}")
        return False


# â”€â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main() -> int:
    log("INFO", "Starting weekly-pulse v4 (cross-checking + mail)")

    log("INFO", "Collecting dataâ€¦")
    commits = get_recent_commits()
    prs = get_recent_prs()
    pipeline = get_pipeline_md()
    decisions = get_decisions_md()
    j_bank = days_to_bank_window()
    log("INFO", f"Collected: {len(commits)} commits, {len(prs)} PRs, J-{j_bank} bank")

    log("INFO", "Calling Claude with web_search + cross-checkâ€¦")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    pulse_md = call_claude_with_retry(
        client, SYSTEM_PROMPT,
        build_user_prompt(commits, prs, pipeline, decisions, j_bank)
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
        alert_level = "ðŸš¨"
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / f"{dt.date.today().isoformat()}-FALLBACK.md"
        out.write_text(pulse_md, encoding="utf-8")
        send_mail(pulse_md, alert_level)
        return 1

    # DÃ©tection niveau d'alerte pour subject mail
    alert_level = detect_alert_level(pulse_md)
    log("INFO", f"Detected alert level: {alert_level}")

    # Ã‰criture artifact (backup)
    log("INFO", "Writing artifactâ€¦")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"{dt.date.today().isoformat()}.md"
    out.write_text(pulse_md, encoding="utf-8")
    log("INFO", f"Written {out} ({len(pulse_md)} chars)")

    # Envoi mail
    log("INFO", "Sending mailâ€¦")
    mail_ok = send_mail(pulse_md, alert_level)
    if not mail_ok:
        log("WARN", "Mail KO mais pulse gÃ©nÃ©rÃ© (artifact disponible)")

    log("INFO", "Done.")
    return 0  # Toujours 0 si le pulse est gÃ©nÃ©rÃ©, mÃªme si mail KO


if __name__ == "__main__":
    sys.exit(main())
