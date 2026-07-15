# AMR Outreach Pipeline — Design Partners

> ⚠️ **AVERTISSEMENT DÉSYNCHRO PIPELINE MAJEURE (2026-07-15)** ⚠️
>
> `outreach/pipeline.md` n'a pas été mis à jour depuis **~1710 heures (~72 jours)**
> (dernier commit : 2026-05-04 19:04 UTC, par JC7333).
>
> Le tracker automatique de ce jour a appliqué **16 transitions
> ENVOYÉ / CANAL ALT TENTÉ → SLOT LIBÉRÉ** parce que la règle mécanique
> (>35j silence total = slot libéré) le mandate. **CES TRANSITIONS SONT
> PROBABLEMENT FAUSSES** — Audric a très certainement eu des réponses,
> conversations, ou pris des décisions durant ces 72 jours qui ne figurent
> pas ici (appel Iteanu du 5-6/05, échanges Hubert, retour Stefanini,
> éventuels DP signés, etc.).
>
> **NE PAS MERGER cette PR aveuglément.** Étapes prioritaires :
> 1. Re-synchroniser `pipeline.md` avec l'état réel (Gmail
>    audric@mandatia.eu, LinkedIn, historique conversations).
> 2. Re-déclencher le Reply Tracker sur la version à jour.
>
> Cette PR sert principalement de **signal d'alarme désynchro majeure**,
> pas de nouvelle source de vérité. Le compteur "conversations actives"
> ci-dessous n'a pas été touché volontairement pour préserver la mémoire
> pré-désynchro.

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 4 conversations actives (Alexandra Iteanu — appel calé 5 ou 6/5 ; Gabriel Hubert/Dust — échange en cours ; Rémi Stefanini/CNIL — fenêtre réponse ouverte ; Adnan Khan/Equinix — reclassé partner LT)** *(état pré-désynchro, à re-vérifier)*.

Fondateur: Audric Bugnard (Aix-les-Bains, FR). Produit: mandatia.eu.

**Email pro actif** : audric@mandatia.eu (Zimbra Starter OVH, SPF + DKIM + DMARC configurés, mail-tester.com score 10/10 le 23/04).

---

## RÈGLE FONDATRICE — pas de relance froide

**On ne relance JAMAIS un contact qui n'a pas répondu à un premier message.**
Insister sur contact froid = spam = tue la cible + entache réputation mandatia.

**Exception unique** : conversation orale ou RDV déjà démarrés puis tus.

**Conséquence opérationnelle** :
- Silence LinkedIn à 14j : canal email alternatif possible UNE fois (pas relance, autre porte)
- Silence total à 35j : `SLOT LIBÉRÉ`, Outreach Radar propose un autre contact

---

## RÈGLE SYNCHRO PIPELINE (ajoutée 27/04/2026)

**Le pipeline.md doit être synchronisé avec l'état réel des envois sous 24h.**
Toute désynchro >48h fait dériver le Reply Tracker (alertes basées sur données stale).

**Mécanisme** :
- Quand Audric confirme un envoi via Claude.ai, Claude met à jour mémoire + pipeline.md dans la même réponse.
- Workflow GitHub Action `pipeline-drift-detector` ouvre automatiquement une issue `⚠️ Pipeline drift` si plus de 2 PR Reply Tracker s'accumulent en attente.
- L'issue se ferme dès que la dérive est résolue.

**⚠️ Cette règle a été VIOLÉE massivement entre le 04/05 et le 15/07 (72 jours de désynchro). Le tracker du 15/07 a produit une PR d'alarme.**

---

## Légende statut

- `ENVOYÉ` — message envoyé, date dans colonne Dernier échange
- `PROPOSÉ W{xx}` — Outreach Radar a proposé, Audric n'a pas encore envoyé
- `CANAL ALT TENTÉ` — 2e canal tenté après silence LinkedIn 14j (une seule fois)
- `SLOT LIBÉRÉ` — silence total >35j, remplaçant à proposer
- `EN COURS HUMAIN` — réponse reçue, Audric gère à la main
- `DÉCLINÉ` — réponse négative claire
- `CONVERTI DP` — accord Design Partner signé
- `REPORTÉ` — cible valide, timing pas optimal
- `SKIP` — écartée
- `SORTI FUNNEL` — contact reclassé hors cible DP (concurrent, pivot, etc.) avec note explicative

---

## Pipeline

| Date contact | Prénom Nom | Entreprise | Secteur | Canal utilisé | Statut | Dernier échange | Notes |
|---|---|---|---|---|---|---|---|
| 2026-04-15 | Adnan Khan | Equinix → Centurian.ai | Infra / Datacenter → Plateforme runtime gouvernance agents | LinkedIn | **SORTI FUNNEL** | 2026-04-27 (Audric continuité post-pivot, pas de retour) | **Reclassé partner LT le 04/05/2026.** Adnan a quitté Equinix et a lancé Centurian.ai (post LinkedIn ~13/04) : plateforme de découverte/gouvernance/observabilité d'agents en entreprise (compliance EU AI Act 02/08/2026). Couche **runtime + reporting**, différente de la couche **autorisation prospective** d'AMR. Pas concurrent direct mais plus DP candidat. Potentiel partner intégration LT (Centurian = futur consommateur du registre AMR). Pas de relance froide. |
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (⚠️ 82j stagnant)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; retour effectif 04/05) | ⚠️ Aucun mouvement visible depuis 82 jours. Statut EN COURS HUMAIN NON TOUCHÉ par le tracker (seul Audric arbitre). Vérifier Gmail audric@mandatia.eu si une réponse est arrivée entretemps. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-23 (email depuis audric@mandatia.eu) | Slot libéré automatiquement par tracker : silence total ~83j depuis le 23/04. ⚠️ **Désynchro pipeline 72j — vérifier réponse Gmail avant proposition remplaçant.** Cooldown 90j jusqu'au 22/07. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | Décision 04/05 : canal email Chift prévu 28/04 jamais activé (anti-dilution). Cooldown 90j jusqu'au 13/07 — **cooldown expiré aujourd'hui**, cible réutilisable si pertinent. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-22 | Slot libéré auto : silence total ~84j. ⚠️ Désynchro pipeline 72j — vérifier réalité avant proposition remplaçant. Note historique : email probable juliette.mattioli@thalesgroup.com (94,5%). |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-22 | Slot libéré auto : silence total ~84j. ⚠️ Désynchro pipeline 72j — vérifier acceptation LinkedIn / réponse avant proposition remplaçant. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-22 | Slot libéré auto : silence total ~84j. ⚠️ Désynchro pipeline 72j — vérifier réalité avant proposition remplaçant. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-22 | Slot libéré auto : silence total ~84j. ⚠️ Désynchro pipeline 72j — vérifier réalité avant proposition remplaçant. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-26 | Slot libéré auto : silence total ~80j. Cooldown Dust géré via Hubert (voir ligne dédiée). ⚠️ Désynchro pipeline 72j. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-26 | Slot libéré auto : silence total ~80j. ⚠️ Désynchro pipeline 72j — vérifier avant proposition remplaçant. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-26 | Slot libéré auto : silence total ~80j. ⚠️ Désynchro pipeline 72j — vérifier acceptation connexion / email éventuel. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Pas de canal alt envisagé (email = canal principal). ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN (⚠️ 78j stagnant)** | 2026-04-28 (réponse Alexandra : "échangeons rapidement de vive voix") | ⚠️ APPEL prévu 5 ou 6/05 — **résultat inconnu, aucun update pipeline depuis**. Statut EN COURS HUMAIN NON TOUCHÉ (seul Audric arbitre). Vérifier Gmail + historique appel. Tel direct fourni : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Pas de relance froide envisagée (PDG cible). ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Pas de canal alt prévu. ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Note historique : ne PAS chercher email (politique/PDG). ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Cible stratégique — vérifier si canal email institutionnel Cigref a été tenté dans l'intervalle. ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Pas de canal alt facile. ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Note historique : email probable stephane.distinguin@fabernovel.com (à valider Hunter si réactivation). ⚠️ Désynchro pipeline 72j. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN (⚠️ 77j stagnant)** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | ⚠️ Aucun update depuis 77 jours. Statut EN COURS HUMAIN NON TOUCHÉ (seul Audric arbitre). Vérifier LinkedIn — Hubert a-t-il répondu à la question seuil ? |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | **SLOT LIBÉRÉ (auto 2026-07-15)** | 2026-04-27 | Slot libéré auto : silence total ~79j. Pas de canal alt envisagé. ⚠️ Désynchro pipeline 72j. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5** *(à vérifier vu la désynchro 72j)*
- **Conversations actives déclarées pré-désynchro** : 3 (Alexandra Iteanu — appel 5 ou 6/5 ; Gabriel Hubert — échanges en cours ; Rémi Stefanini — fenêtre réponse ouverte). **État réel inconnu.**
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- **SLOT LIBÉRÉ** : 17 total (16 auto par tracker 2026-07-15 + 1 anticipé Gauthier)
- Messages ENVOYÉ en attente : **0** (tous libérés auto)
- SKIP / SORTI FUNNEL : 2 (Houlès, Adnan)

**FUNNEL RÉEL POST-TRACKER** : 3 lignes EN COURS HUMAIN (Iteanu, Hubert, Stefanini) — **toutes stagnantes >77j sans update pipeline**. 17 slots libérés. **La priorité #1 est la re-synchronisation manuelle**, pas la relance d'outreach.

---

## Contacts déjà sollicités (cooldown 90j)

- Equinix → Centurian.ai (Adnan, 2026-04-15) — cooldown 2026-07-14 **(expiré)** (mais reclassé partner LT)
- CNIL (Stefanini, 2026-04-22 LinkedIn + 2026-04-24 email) — cooldown 2026-07-23
- Remedi Finance (Erdem, 2026-04-14 LinkedIn + 2026-04-23 email) — cooldown 2026-07-22
- Chift (Gauthier, 2026-04-14) — cooldown 2026-07-13 **(expiré)**
- Thales (Mattioli, 2026-04-22) — cooldown 2026-07-21
- Ledger (Rogers, 2026-04-22) — cooldown 2026-07-21
- Crédit Agricole (Zappellini, 2026-04-22) — cooldown 2026-07-21
- HSBC (Rice, 2026-04-22) — cooldown 2026-07-21
- Dust.tt (Polu 26/04 + Hubert 27/04 — Hubert répond) — cooldown 2026-07-25 et 2026-07-26
- Sciences Po (G'sell, 2026-04-26) — cooldown 2026-07-25
- EPFL (Salathé, 2026-04-26) — cooldown 2026-07-25
- IMT-BS (Balagué, 2026-04-27) — cooldown 2026-07-26
- Iteanu Avocats (Alexandra Iteanu répond, 2026-04-28) — cooldown 2026-07-27
- ANSSI (Strubel, 2026-04-27) — cooldown 2026-07-26
- AI Action Summit (Bouverot, 2026-04-27) — cooldown 2026-07-26
- Cédric O (perso, 2026-04-27) — cooldown 2026-07-26
- Cigref (d'Agrain, 2026-04-27) — cooldown 2026-07-26
- Tariq Krim (perso, 2026-04-27) — cooldown 2026-07-26
- Fabernovel (Distinguin, 2026-04-27) — cooldown 2026-07-26
- Inria (Sportisse, 2026-04-27) — cooldown 2026-07-26

(Kering NON cooldownée — Houlès SKIP)

---

## Contacts CNIL backup (ne pas solliciter sans invitation explicite de Stefanini)

- **Vincent Toubiana** (vtoubiana@cnil.fr) — backup Stefanini jusqu'au 24/04/2026
- **Florent Della-Valle** (fdella-valle@cnil.fr) — backup Stefanini 25/04-30/04/2026

Ces noms sont connus via l'autoreply institutionnel de Stefanini. **NE JAMAIS les contacter de propre initiative.**

---

## Dates clés

| Date | Événement |
|---|---|
| **2026-07-15 (aujourd'hui)** | ⚠️ Tracker automatique : 16 slots libérés auto. Désynchro pipeline 72j détectée. **Priorité re-sync manuelle.** |
| 2026-05-04 → 2026-07-15 | **TROU NOIR pipeline** — aucune trace de mise à jour. Vérifier Gmail + LinkedIn + notes Claude session pour reconstituer. |
| 2026-05-05 ou 06 | Appel Iteanu prévu — **résultat inconnu, à re-documenter**. |
| 2026-05-04 | Retour effectif Stefanini annoncé — **résultat inconnu**. |

---

## Actions Audric prochainement

- **Priorité #1** : **RE-SYNCHRONISER pipeline.md** avec l'état réel des 72 derniers jours. Sources à consulter : Gmail audric@mandatia.eu, LinkedIn, historique conversations Claude. Sans cette étape, toutes les décisions outreach en aval sont aveugles.
- **Priorité #2** : Ne PAS merger cette PR aveuglément. Elle est un signal d'alarme, pas une source de vérité. Soit close la PR après resync, soit merge après avoir validé chaque SLOT LIBÉRÉ auto.
- **Priorité #3** : Une fois pipeline resynchronisé, re-déclencher Reply Tracker et Outreach Radar pour repartir sur base saine.
- **Priorité #4** : Investiguer pourquoi ni le drift detector ni les routines de tracker n'ont visiblement produit d'alerte visible sur ces 72 jours (ou si oui, pourquoi Audric ne les a pas vues).

---

## Journal hebdomadaire

### W17 (2026-04-20 → 2026-04-26)

**Outreach Radar lundi 21/04** : 1 cible DP fraîche (Mattioli) + 1 borderline skippée (Houlès) + 1 régulateur stratégique (Stefanini).

**Complément Outreach Radar mercredi 22/04** : 3 cibles supplémentaires fintech/banque (Rogers, Zappellini, Rice).

**Ajouts rétroactifs 23/04** : Erdem Yağan (Remedi Finance, CEO) + Gauthier Henroz (Chift, CEO) — tous deux envoyés 14/04 hors pipeline initial.

**Canal email activé 23/04** : Erdem Yağan via audric@mandatia.eu.

**RÉPONSE INSTITUTIONNELLE 24/04** : Rémi Stefanini (CNIL DTIA) répond sur LinkedIn à 08:39, demande de bascule sur email. Email envoyé 24/04, autoreply reçu (retour 04/05).

**Wave 1 dimanche 26/04** : ajout 3 cibles (Polu/Dust, G'sell/SciencesPo, Salathé/EPFL) hors radar habituel, à l'initiative d'Audric.

**Volume W17 effectif** : 11 cibles contactées.

### W18 (2026-04-27 → 2026-05-03)

**Lundi 27/04 — vague massive d'outreach** : 11 envois dans la journée. Wave 2 (Balagué, Iteanu cabinet, Strubel, Bouverot) + Wave 3 (Cédric O, d'Agrain, Krim, Distinguin, Hubert, Sportisse).

**Mardi 28/04** :
- ★ **RÉPONSE Alexandra Iteanu** (associée du cabinet Iteanu, avocate IA/Sorbonne) : "le point que vous soulevez est fondamental, échangeons de vive voix". Reclassée EN COURS HUMAIN.
- ★ **RÉPONSE Gabriel Hubert** (CEO Dust) : "ça dépend des tâches/de l'impact". Reclassé EN COURS HUMAIN.
- Canal email Chift Gauthier prévu : **non activé** (anti-dilution).

**Mercredi 29/04** :
- Audric envoie 2e message à Hubert : question seuil clients juristes vs métier.

**Jeudi 30/04** :
- Audric envoie mail à Alexandra Iteanu avec créneaux 5 ou 6/5 17h30-18h30 + tel direct.

**Lundi 4/05** :
- Audric découvre post LinkedIn Adnan Khan (~13/04) annonçant Centurian.ai → Adnan reclassé SORTI FUNNEL / partner LT.
- Sync pipeline.md v6.0.
- Stefanini retour effectif de congés (fenêtre réponse ouverte).

### W19-W28 (2026-05-05 → 2026-07-14) — TROU NOIR PIPELINE

⚠️ **Aucune trace de mise à jour de pipeline.md pendant 72 jours**. À reconstituer manuellement : appel Iteanu 5/6-05, échanges Hubert post-2e message, retour Stefanini, éventuels DP signés, nouveaux outreach effectués hors pipeline, etc.

### W29 (2026-07-13 → 2026-07-19)

**Mardi 15/07** :
- Reply Tracker exécuté sur pipeline stale 72j. Désynchro pipeline détectée en pré-vérification. 16 slots libérés automatiquement par règle mécanique >35j silence. 3 EN COURS HUMAIN stagnants massifs signalés (Iteanu, Hubert, Stefanini). Notification push envoyée à Audric.

---

## Changelog pipeline

- **2026-07-15 (v6.1)** : ⚠️ PR d'ALARME DÉSYNCHRO générée par Reply Tracker automatique. 72 jours sans mise à jour de pipeline.md. 16 transitions ENVOYÉ/CANAL ALT TENTÉ → SLOT LIBÉRÉ appliquées mécaniquement (Erdem, Mattioli, Rogers, Zappellini, Rice, Polu, G'sell, Salathé, Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse). Statuts EN COURS HUMAIN d'Iteanu, Hubert, Stefanini préservés (non touchés). Cette version est un signal d'alarme, pas une source de vérité — à valider avant merge après re-synchronisation manuelle.
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
