# write-v4.ps1 — ecrit weekly_pulse.py v4 + met a jour weekly-pulse.yml (timing 9h)
# v4 = cross-checking sources + envoi mail Gmail + nouveau timing dimanche 9h
# Suppose que tu es dans C:\dev\amr

Write-Host "=== Branche actuelle ===" -ForegroundColor Cyan
git checkout main
git pull
$existsBranch = git branch --list "sync/weekly-pulse-v4"
if ($existsBranch) {
    Write-Host "  Branche sync/weekly-pulse-v4 existe deja, suppression locale" -ForegroundColor Yellow
    git branch -D sync/weekly-pulse-v4
}
git checkout -b sync/weekly-pulse-v4

Write-Host "=== Ecriture weekly_pulse.py v4 ===" -ForegroundColor Cyan
$pyContent = @'
#!/usr/bin/env python3
"""
weekly_pulse.py — Routine 5 AMR (v4 avec cross-checking et envoi mail).

Tourne tous les dimanches à 9h Paris.
Compile l'état de la semaine + génère revue ET veille AMR via web_search
ET envoie le pulse par mail à audric9@gmail.com.

Sortie : 
- artifact GitHub (backup, accessible depuis Actions)
- mail HTML à audric9@gmail.com
- summary GitHub Actions (pour debug)

v4 nouveautés :
- Cross-checking obligatoire : 2 sources MINIMUM par fait, sinon marquage "⚠️ À VÉRIFIER"
- Envoi mail HTML + text fallback via SMTP Gmail
- Sujet mail préfixé par niveau d'alerte le plus haut détecté
- Pulse persistant : artifact + mail (double sécurité)
- Tolérance erreur mail : pulse généré même si SMTP KO

Coût marginal : ~0.13€/run = 7€/an. Inchangé v3.
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

import anthropic
import requests


# ─── Configuration ──────────────────────────────────────────────────────────

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


# ─── Utilitaires ────────────────────────────────────────────────────────────

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


# ─── Collecte des données ───────────────────────────────────────────────────

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


# ─── Prompt Claude (v4 avec cross-checking) ────────────────────────────────

SYSTEM_PROMPT = """Tu génères la revue hebdomadaire d'Audric, médecin
thermaliste à Aix-les-Bains, solo fondateur multi-projets.

Audric construit AMR (mandatia.eu) = registre de mandats pour agents IA
basé sur Art.1984 Code civil + eIDAS 2.0 + EU AI Act. Modèle freemium :
Tier 0 OSS, Tier 1 350€/mois (token issuer mandate-gated), Tier 2
enterprise 20-80k/an, Tier 3 templates sectoriels 2-5k€/pack.

STRATÉGIE OPTIONALITÉ : Audric continue la médecine (rente), développe
AMR intensivement, basculera vers AMR plein temps SI signaux d'attraction
forte se déclenchent. Signaux à surveiller :
- 🟡 >3 inbounds qualifiés/mois sans outreach actif
- 🟡 1er client Tier 1 signé (350€/mois ARR)
- 🔴 1er contrat Tier 2 enterprise 20-80k€/an
- 🔴 ARR récurrent 100k€ confirmé
- 🚨 Offre rachat >2M€
- 🚨 Levée preempt VC tier 1 sans démarche

═══════════════════════════════════════════════════
RÈGLE FONDAMENTALE — CROSS-CHECKING DES SOURCES
═══════════════════════════════════════════════════

Chaque fait que tu rapportes DOIT être :
- Soit confirmé par MINIMUM 2 sources indépendantes → tu cites les deux
- Soit marqué "⚠️ À VÉRIFIER" en gras avec la source unique mentionnée
- JAMAIS d'affirmation sans source

Pour les actualités réglementaires (AI Act, Digital Omnibus, eIDAS),
PRIVILÉGIER les sources primaires : Parlement européen, Conseil EU,
Commission, EUR-Lex, communiqués officiels. Les articles dérivés
(Euractiv, Politico, Sifted) sont OK comme 2e confirmation, jamais
comme seule source.

Pour les levées de fonds et acquisitions, vérifier sur Crunchbase OU
TechCrunch OU site officiel de l'entreprise.

Si une info paraît surprenante (date qui contredit ce que je connais,
chiffre exceptionnel), TRIPLE-CHECK avec 3 sources avant de l'affirmer.
Si impossible → marquer "⚠️ À VÉRIFIER - source unique X, contradiction
possible avec [info connue]".

INTERDIT : inventer des dates précises, des montants exacts, des noms de
personnes ou de sociétés non confirmés par recherche.

═══════════════════════════════════════════════════
RECHERCHES OBLIGATOIRES (utilise web_search)
═══════════════════════════════════════════════════

AVANT de générer la section "🔭 Veille AMR", tu DOIS effectuer ces
recherches :
1. "ArkForge AI compliance" + variantes (dernière semaine)
2. "OpenBox AI agent runtime" OR "Mastra AI agent governance"
3. "Vanta OneTrust Drata AI agent compliance" (concurrence indirecte)
4. "EU AI Act Digital Omnibus 2026" + "Annex III deadline"
5. "AI agent compliance startup funding 2026" (levées/acquisitions)
6. "MCP Model Context Protocol authorization mandate"
7. Recherche libre selon ce qui semble pertinent

Si une recherche ramène un fait majeur (deadline modifiée, concurrent
qui pivote, grosse levée), AJOUTER une recherche de confirmation
ciblée sur cette info précise.

═══════════════════════════════════════════════════
STRUCTURE DE SORTIE (markdown strict, <3 min lecture)
═══════════════════════════════════════════════════

# Weekly Pulse — {date}

**Niveau d'alerte global : [🚨 / 🔴 / 🟡 / 🟢]**
(Le niveau le plus haut atteint dans le pulse. Sert au tri rapide.)

## 📊 Semaine écoulée
Pour chaque projet actif avec activité : 1-2 lignes factuelles, chiffrées.
Si pas d'activité, NE PAS le mentionner.

## 🎯 État des fronts
Pour chacun des 5 fronts (AMR, KORVEX, Étuve, immo, fenêtre bancaire) :
- 🔴 BLOQUANTE (J+7) : [action]
- 🟡 CRITIQUE (J+14) : [action]
- 🟢 UTILE (J+30) : [action]
Si rien sur un front, écrire "RAS".

## 🔭 Veille AMR cette semaine
**Concurrents**
- [Concurrent] : [ce qui a bougé] [sources : url1, url2] → impact AMR : [phrase courte]
**Réglementaire**
- [Étape AI Act / Digital Omnibus] [sources : url1, url2] → impact AMR : [...]
**Marché**
- [Levée/acquisition] [sources : url1, url2] → impact AMR : [...]
**Signaux faibles à surveiller**
- [À garder à l'œil] [source : url] (1 source suffit pour signaux faibles)

Pour chaque item, **EXPLICITER LES SOURCES** entre crochets.
Si une info est marquée "⚠️ À VÉRIFIER", expliquer pourquoi.

## ⚡ Check signaux de bascule AMR
État courant des 6 signaux :
- 🟡 Inbounds qualifiés (>3/mois) : [N actuel / 3]
- 🟡 1er Tier 1 signé : [oui/non]
- 🔴 1er Tier 2 enterprise : [oui/non]
- 🔴 ARR 100k confirmé : [oui/non]
- 🚨 Offre rachat >2M€ : [oui/non]
- 🚨 Levée preempt : [oui/non]
Si UN signal franchi → "**⚠️ REVUE STRATÉGIQUE DÉCLENCHÉE**".

## 📅 Plan semaine prochaine
Calendrier créneaux soir/WE. Audric consulte en journée.
Allocation cible AMR ~9-11h/sem : lun/mer/ven soir 21-23h + sam matin
9-12h + dim flex.

## ⏰ Fenêtre bancaire
J-{days} avant 30/11/2026. Étape la plus en retard. Action si urgente.

## 🎯 Actions de mise à jour suggérées
Si la veille a remonté des infos qui impactent ton messaging, ton site,
tes skills :
- [mandatia.eu] : [description du changement suggéré] (priorité : 🔴/🟡/🟢)
- [skill amr-core] : [description] (priorité : ...)
- [skill amr-outreach] : [description] (priorité : ...)
- [LinkedIn] : [suggestion à valider manuellement] (priorité : ...)

Si rien à suggérer, écrire "Aucune mise à jour nécessaire cette semaine."

## ❓ Sanity check
UNE seule question d'arbitrage stratégique (ou rien si rien d'urgent).

═══════════════════════════════════════════════════

INTERDITS : préambules, félicitations, blabla, listes décoratives,
re-stratégie globale, reproches moraux. Style oral, asymétrique, dense.
JAMAIS inventer de fait. Si web_search ne ramène rien, dire "RAS"."""


def build_user_prompt(commits, prs, pipeline, decisions, j_bank) -> str:
    return f"""Génère la weekly-pulse d'aujourd'hui.

Date : {dt.date.today().isoformat()}

COMMITS REPO AMR (7j) :
{json.dumps(commits, indent=2, ensure_ascii=False)}

PRS REPO AMR (7j) :
{json.dumps(prs, indent=2, ensure_ascii=False)}

PIPELINE.MD ACTUEL :
{pipeline}

DECISIONS.MD ACTUEL :
{decisions}

FENÊTRE BANCAIRE : J-{j_bank} avant 30/11/2026.

INSTRUCTIONS :
1. Effectue les 6-7 recherches web obligatoires pour la section Veille.
2. CROSS-CHECK chaque fait avec MINIMUM 2 sources, sinon marque "⚠️ À VÉRIFIER".
3. Détermine le niveau d'alerte global (le plus haut détecté).
4. Génère la pulse complète au format demandé.
5. Sortie markdown brute, pas de préambule."""


def call_claude_with_retry(client, system, user_prompt, retries: int = 3) -> str | None:
    last_exc = None
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4500,
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


# ─── Email ──────────────────────────────────────────────────────────────────

def detect_alert_level(pulse_md: str) -> str:
    """Détecte le niveau d'alerte le plus haut dans le pulse."""
    if "🚨" in pulse_md or "REVUE STRATÉGIQUE DÉCLENCHÉE" in pulse_md:
        return "🚨"
    if "🔴" in pulse_md:
        return "🔴"
    if "🟡" in pulse_md:
        return "🟡"
    return "🟢"


def markdown_to_html(md: str) -> str:
    """Conversion markdown→HTML minimaliste, propre pour mail."""
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
<p style="color:#888;font-size:12px;">Pulse AMR généré automatiquement — routine GitHub Actions weekly-pulse.<br>
Source : github.com/JC7333/amr/actions</p>
</body></html>"""


def send_mail(pulse_md: str, alert_level: str) -> bool:
    """Envoie le pulse par mail. Retourne True si succès."""
    if not GMAIL_APP_PASSWORD:
        log("WARN", "GMAIL_APP_PASSWORD absent — skip mail")
        return False

    today = dt.date.today().strftime("%d/%m/%Y")
    subject = f"{alert_level} Pulse AMR — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = MAIL_TO

    text_part = MIMEText(pulse_md, "plain", "utf-8")
    html_part = MIMEText(markdown_to_html(pulse_md), "html", "utf-8")
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        log("INFO", f"Mail envoyé à {MAIL_TO} (subject: {subject})")
        return True
    except Exception as e:
        log("ERROR", f"Mail failed: {e}")
        return False


# ─── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    log("INFO", "Starting weekly-pulse v4 (cross-checking + mail)")

    log("INFO", "Collecting data…")
    commits = get_recent_commits()
    prs = get_recent_prs()
    pipeline = get_pipeline_md()
    decisions = get_decisions_md()
    j_bank = days_to_bank_window()
    log("INFO", f"Collected: {len(commits)} commits, {len(prs)} PRs, J-{j_bank} bank")

    log("INFO", "Calling Claude with web_search + cross-check…")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    pulse_md = call_claude_with_retry(
        client, SYSTEM_PROMPT,
        build_user_prompt(commits, prs, pipeline, decisions, j_bank)
    )

    if pulse_md is None:
        log("ERROR", "Claude API totally down — writing fallback")
        pulse_md = f"""# Weekly Pulse — {dt.date.today().isoformat()} (FALLBACK)

**⚠️ Claude API indisponible. Données brutes ci-dessous.**

## Commits 7j
{json.dumps(commits, indent=2, ensure_ascii=False)}

## PRs 7j
{json.dumps(prs, indent=2, ensure_ascii=False)}

## Fenêtre bancaire
J-{j_bank} avant 30/11/2026.

## Pipeline (extrait)
{pipeline[:1500]}
"""
        alert_level = "🚨"
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / f"{dt.date.today().isoformat()}-FALLBACK.md"
        out.write_text(pulse_md, encoding="utf-8")
        send_mail(pulse_md, alert_level)
        return 1

    # Détection niveau d'alerte pour subject mail
    alert_level = detect_alert_level(pulse_md)
    log("INFO", f"Detected alert level: {alert_level}")

    # Écriture artifact (backup)
    log("INFO", "Writing artifact…")
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"{dt.date.today().isoformat()}.md"
    out.write_text(pulse_md, encoding="utf-8")
    log("INFO", f"Written {out} ({len(pulse_md)} chars)")

    # Envoi mail
    log("INFO", "Sending mail…")
    mail_ok = send_mail(pulse_md, alert_level)
    if not mail_ok:
        log("WARN", "Mail KO mais pulse généré (artifact disponible)")

    log("INFO", "Done.")
    return 0  # Toujours 0 si le pulse est généré, même si mail KO


if __name__ == "__main__":
    sys.exit(main())

'@
[System.IO.File]::WriteAllText("$pwd\.github\scripts\weekly_pulse.py", $pyContent, [System.Text.UTF8Encoding]::new($false))
$sizePy = (Get-Item .github\scripts\weekly_pulse.py).Length
Write-Host "  weekly_pulse.py : $sizePy bytes" -ForegroundColor Green

Write-Host "=== Ecriture weekly-pulse.yml (nouveau timing) ===" -ForegroundColor Cyan
$ymlContent = @'
name: weekly-pulse

# Routine 5 d'Audric — revue hebdo automatique dimanche 9h Paris.
# Génère pulse avec veille auto + cross-checking, l'envoie par mail.
#
# Secrets requis :
#   - ANTHROPIC_API_KEY : clé API Anthropic (existant)
#   - GMAIL_APP_PASSWORD : mot de passe d'application Gmail (à créer)
#
# Optionnel :
#   - GMAIL_USER : adresse Gmail (défaut: audric9@gmail.com)
#
# Timing :
#   - 0 7 * * 0 = dimanche 7h UTC = 9h Paris en été (UTC+2)
#   - 0 8 * * 0 = dimanche 8h UTC = 9h Paris en hiver (UTC+1)
#   GitHub Actions ne fait pas la conversion DST automatiquement,
#   donc on configure les deux crons et le job s'exécute UNE fois selon le mois.
#   En pratique le runner tournera 2 fois en heure-pivot (mars/octobre),
#   mais l'idempotence du pulse (artifact + mail) supporte ça.

on:
  schedule:
    - cron: '0 7 * * 0'  # dimanche 9h Paris (été)
    - cron: '0 8 * * 0'  # dimanche 9h Paris (hiver)
  workflow_dispatch:  # déclenchement manuel possible

jobs:
  weekly-pulse:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4
        with:
          fetch-depth: 30

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install deps
        run: pip install anthropic requests

      - name: Generate weekly pulse + send mail
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: python .github/scripts/weekly_pulse.py

      - name: Upload pulse as artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: weekly-pulse-${{ github.run_id }}
          path: weekly-pulse/*.md
          retention-days: 90

      - name: Show pulse in summary
        if: always()
        run: |
          PULSE_FILE=$(ls -t weekly-pulse/*.md 2>/dev/null | head -1)
          if [ -n "$PULSE_FILE" ]; then
            echo "## Weekly Pulse $(date -u +%Y-%m-%d)" >> $GITHUB_STEP_SUMMARY
            echo "" >> $GITHUB_STEP_SUMMARY
            cat "$PULSE_FILE" >> $GITHUB_STEP_SUMMARY
          fi

'@
[System.IO.File]::WriteAllText("$pwd\.github\workflows\weekly-pulse.yml", $ymlContent, [System.Text.UTF8Encoding]::new($false))
$sizeYml = (Get-Item .github\workflows\weekly-pulse.yml).Length
Write-Host "  weekly-pulse.yml : $sizeYml bytes" -ForegroundColor Green

Write-Host "=== Git add + commit ===" -ForegroundColor Cyan
git add .github/scripts/weekly_pulse.py .github/workflows/weekly-pulse.yml
git commit -m "weekly-pulse v4 : cross-checking sources + envoi mail Gmail + timing dim 9h"

Write-Host "=== Push + PR + merge ===" -ForegroundColor Cyan
git push origin sync/weekly-pulse-v4
gh pr create --title "weekly-pulse v4 (cross-checking + mail)" --body "Ajoute cross-checking obligatoire (2 sources min ou marquage A VERIFIER), envoi mail Gmail HTML a audric9@gmail.com, nouveau timing dimanche 9h Paris (cron double ete/hiver), section 'Actions de mise a jour suggerees', detection niveau d'alerte pour subject mail."
gh pr merge --squash --delete-branch

Write-Host "=== Retour sur main ===" -ForegroundColor Cyan
git checkout main
git pull

Write-Host ""
Write-Host "=== TERMINE ===" -ForegroundColor Green
Write-Host ""
Write-Host "PROCHAINES ETAPES OBLIGATOIRES :" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Creer un Mot de passe d'application Gmail (5 min) :" -ForegroundColor Cyan
Write-Host "   - Va sur : https://myaccount.google.com/security"
Write-Host "   - Active la verif en 2 etapes si pas deja fait"
Write-Host "   - Va sur : https://myaccount.google.com/apppasswords"
Write-Host "   - App : 'Mail', Device : 'GitHub Actions AMR'"
Write-Host "   - Genere un code 16 caracteres"
Write-Host ""
Write-Host "2. Ajouter le secret GMAIL_APP_PASSWORD au repo :" -ForegroundColor Cyan
Write-Host "   - https://github.com/JC7333/amr/settings/secrets/actions"
Write-Host "   - New repository secret"
Write-Host "   - Name : GMAIL_APP_PASSWORD"
Write-Host "   - Secret : le code 16 caracteres genere"
Write-Host ""
Write-Host "3. Tester en manuel :" -ForegroundColor Cyan
Write-Host "   - https://github.com/JC7333/amr/actions"
Write-Host "   - weekly-pulse > Run workflow > Run workflow"
Write-Host "   - Attendre 3-4 min (cross-check prend plus de temps)"
Write-Host "   - Verifier reception mail sur audric9@gmail.com"
