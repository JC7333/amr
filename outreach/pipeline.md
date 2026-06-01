# AMR Outreach Pipeline — Design Partners

> **⚠️ DRIFT 4 SEMAINES — sync requise avant tout nouvel envoi**
> Dernier update v6.0 : 04/05/2026. Aujourd'hui : **01/06/2026 (S22)**. Outreach Radar n'a pas tourné W19/W20/W21 (anomalie cron déjà notée 04/05). État réel des 3 conversations chaudes (Iteanu 5-6/05, Hubert, Stefanini) inconnu depuis 28 jours. **Toutes les dates « SLOT LIBÉRÉ » listées dans la section « Dates clés » sont théoriquement atteintes mais à confirmer manuellement par Audric avant arbitrage.** Voir section « Questions de synchro Audric W22 » en bas.

Objectif: 5 Design Partners signés. Statut **figé au 04/05/2026** : 0/5 signés, 3 conversations chaudes (Iteanu appel 5-6/05 ; Hubert/Dust ; Stefanini/CNIL fenêtre ouverte) + 1 reclassement partner LT (Adnan Khan/Centurian). **État réel au 01/06 = à confirmer.**

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (fenêtre réponse ouverte)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; **retour effectif 04/05 = aujourd'hui**) | Directeur DTIA CNIL. Fenêtre réponse réaliste : 04/05 → 18/05. Surveillance passive. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | CANAL ALT TENTÉ | 2026-04-23 (email depuis audric@mandatia.eu) | CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. Si silence total 18/05 : SLOT LIBÉRÉ. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | ENVOYÉ | 2026-04-22 | Atteint 12j silence aujourd'hui. Fenêtre canal alt s'ouvre 06/05 (14j). Email probable juliette.mattioli@thalesgroup.com (94,5%). Valider Hunter avant tout envoi. SLOT LIBÉRÉ 27/05 si silence total. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | ENVOYÉ | 2026-04-22 | Profil fermé. 12j silence. Fenêtre canal alt 06/05. Email probable ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%). Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | ENVOYÉ | 2026-04-22 | 12j silence. Fenêtre canal alt 06/05. Email probable aldrick.zappellini@credit-agricole.com (89%). Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | ENVOYÉ | 2026-04-22 | 12j silence. Fenêtre canal alt 06/05. Email probable david.rice@hsbc.com (71%). Risque doublon nom. Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | ENVOYÉ | 2026-04-26 | CTO Dust. 8j silence. **Note** : Hubert (CEO Dust) a répondu, donc équipe Dust a vu AMR — Polu probablement au courant. Si silence 10/05 : ne PAS tenter email Polu (Hubert canal principal Dust). SLOT LIBÉRÉ 31/05. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | ENVOYÉ | 2026-04-26 | Professeure droit IA. 8j silence. Fenêtre canal alt 10/05. Email probable florence.gsell@sciencespo.fr. SLOT LIBÉRÉ 31/05. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | ENVOYÉ | 2026-04-26 | Profil fermé, note seulement. Attente acceptation connexion. Si pas accepté à J+14 (10/05) : tenter email marcel.salathe@epfl.ch. SLOT LIBÉRÉ 31/05. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | ENVOYÉ | 2026-04-27 | christine.balague@imt-bs.eu (vérifié multi-source). 7j silence. Pas de canal alt prévu (email = canal principal). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN** | 2026-04-28 (réponse Alexandra : "le point que vous soulevez de la responsabilité et du mandat est fondamental, échangeons rapidement de vive voix") | Réponse de l'associée d'Olivier Iteanu (le mail initial avait été envoyé "À l'attention de Maître Iteanu" → transmis à Alexandra). **APPEL CADRÉ** : créneaux proposés 5 ou 6/5 17h30-18h30 (mail Audric 30/04). En attente confirmation date ferme. **3 questions précises à envoyer 24h avant l'appel** (préparation Claude session 4/5 soir). Tel direct fourni : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | ENVOYÉ | 2026-04-27 | DG ANSSI. 7j silence. Pas de relance froide ni d'email institutionnel envisagé (PDG cible). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | ENVOYÉ | 2026-04-27 | 7j silence. Pas de canal alt prévu. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | ENVOYÉ | 2026-04-27 | Profil fermé probable, note seulement. Attente acceptation. Si pas accepté à J+14 : NE PAS chercher email (politique/PDG, ne marchera pas). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. Cible stratégique. Si silence 11/05 : tenter email institutionnel cigref. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. 7j silence. Pas de canal alt facile (pas d'employeur fixe). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. 7j silence. Si silence 11/05 : email probable stephane.distinguin@fabernovel.com à valider Hunter. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | Hubert a répondu 28/04 sur 1er message d'Audric : "ça dépend des tâches/de l'impact". Audric a contre-questionné 29/04 sur où il voit le seuil entre clients juristes vs métier dans l'usage agent. **En attente retour Hubert.** Cooldown 90j maintenu. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | ENVOYÉ | 2026-04-27 | PDG institution publique. Note seulement. Email pattern probable bruno.sportisse@inria.fr mais filtré par secrétariat. Pas de canal alt envisagé. SLOT LIBÉRÉ 01/06. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |
| 2026-06-01 (proposé W22) | Yann Lechelle | Probabl (spin-off Inria, scikit-learn) | Écosystème IA open source FR | — | **PROPOSÉ W22** | — | CEO Probabl, board Hub France IA. Trigger : tribune Maddyness 12/05/2026 « Tribune Debunk #2 » — pitch quasi-identique à AMR (imputabilité, AI Act, « ce nom est celui que la justice interrogera »). LinkedIn https://www.linkedin.com/in/ylechelle/ à vérifier visuellement (direct vs InMail). Email non CONFIRMÉ. Voir draft `2026-06-01_lechelle.md`. **Cible « partenaire écosystème », pas deployer AI Act classique — arbitrage Audric requis.** |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations actives** : **3 chaudes** (Alexandra Iteanu — appel 5 ou 6/5 ; Gabriel Hubert — échanges en cours ; Rémi Stefanini — fenêtre réponse ouverte)
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- Messages ENVOYÉS sans retour : 14 (en attente naturelle, pas de relance froide)
- Canal alt email tenté : 1 (Erdem) → silence
- SLOT LIBÉRÉ anticipé : 1 (Gauthier Henroz / Chift)

**FUNNEL RÉEL** : 17 contacts en suivi actif (21 envoyés - Adnan SORTI - Gauthier libéré - Houlès SKIP). 3 conversations chaudes dont 1 RDV calé. **STOP nouveaux contacts jusqu'au 18/05** (priorité = cadrer correctement Iteanu + Hubert + Stefanini si elle répond).

---

## Contacts déjà sollicités (cooldown 90j)

- Equinix → Centurian.ai (Adnan, 2026-04-15) — cooldown 2026-07-14 (mais reclassé partner LT)
- CNIL (Stefanini, 2026-04-22 LinkedIn + 2026-04-24 email) — cooldown 2026-07-23
- Remedi Finance (Erdem, 2026-04-14 LinkedIn + 2026-04-23 email) — cooldown 2026-07-22
- Chift (Gauthier, 2026-04-14) — cooldown 2026-07-13
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
| **2026-05-04 (aujourd'hui)** | Retour effectif Stefanini. Surveillance passive Gmail. |
| **2026-05-05 ou 06 17h30-18h30** | **APPEL ALEXANDRA ITEANU** (créneau ferme à confirmer par mail Audric 30/04). |
| **2026-05-04 ou 05 soir** | Préparation appel Iteanu : récit fondateur + 3 questions à envoyer 24h avant + lignes rouges. |
| 2026-05-06 | Mattioli, Rogers, Zappellini, Rice atteignent 14j silence → fenêtre canal alt ouverte |
| 2026-05-04 → 2026-05-18 | Fenêtre normale réponse Stefanini |
| 2026-05-10 | Polu, G'sell, Salathé atteignent 14j silence → fenêtre canal alt (Salathé : tenter email seulement si connexion non acceptée ; Polu : NE PAS tenter, Hubert est le canal Dust) |
| 2026-05-11 | Balagué, Iteanu, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse atteignent 14j silence → canal alt UNIQUEMENT pour cibles pertinentes (pas Sportisse, pas Cédric, pas Strubel, pas Iteanu — déjà en cours humain) |
| 2026-05-18 | Erdem atteint 35j silence → SLOT LIBÉRÉ si pas de réponse |
| 2026-05-27 | Mattioli, Rogers, Zappellini, Rice atteignent 35j silence → SLOT LIBÉRÉ |
| 2026-05-31 | Polu, G'sell, Salathé atteignent 35j → SLOT LIBÉRÉ |
| 2026-06-01 | 9 contacts du 27/04 atteignent 35j → SLOT LIBÉRÉ massif |

---

## Actions Audric cette semaine (S19)

- **Priorité #1** : préparer l'appel Alexandra Iteanu (récit fondateur + 3 questions précises à envoyer 24h avant + lignes rouges en cas de questions techniques juridiques pointues). Session de prépa Claude le **04/05 ou 05/05 soir**.
- **Priorité #2** : surveiller Gmail audric@mandatia.eu et LinkedIn — Stefanini fenêtre ouverte aujourd'hui, Hubert en attente retour, premières réponses possibles d'autres contacts.
- **Priorité #3** : si retour Hubert sur la question seuil juristes/métier, répondre dans la même journée (conversation chaude).
- **Priorité #4** : NE PAS envoyer de nouveau message d'outreach. Capacité de cadrage saturée. Plafond strict jusqu'au 18/05.

---

## Actions Audric cette semaine (S22 — Radar W22 du 01/06/2026)

**Contexte** : 28 jours de gap depuis dernier sync. Le Radar W22 livre **une seule cible nouvelle** (Lechelle) au lieu de 5 — décision assumée : sans pipeline à jour ni accès LinkedIn direct pour vérifier les triggers individuels, livrer 5 cibles serait inventer. Mieux : 1 cible solide + sync rigoureuse.

- **Priorité #1 — SYNCHRO** : avant tout nouvel envoi, répondre aux 5 questions de la section « Questions de synchro Audric W22 » ci-dessous. Sans ça, l'arbitrage SLOT LIBÉRÉ est aveugle.
- **Priorité #2 — Lechelle (si arbitré OUI par Audric)** : vérifier visuellement le bouton « Message » sur https://www.linkedin.com/in/ylechelle/ puis envoyer la version longue (750c) du draft `2026-06-01_lechelle.md`. Si pas de bouton Message → note InMail 180c. Pas d'email cette semaine (non confirmé).
- **Priorité #3 — Arbitrage Lechelle DP strict vs partenaire écosystème** : il n'est pas deployer AI Act classique. Avant d'envoyer, Audric décide si la cible vise un slot DP (5 places) ou un slot partenaire écosystème séparé (comme Adnan Khan / Centurian reclassé partner LT).
- **Priorité #4 — Réflexion sur les SLOTS LIBÉRÉS atteints** : 14 contacts envoyés du 22/04 au 27/04 ont théoriquement atteint 35j. Selon réponses Audric, soit (a) certains ont répondu entre-temps et restent en suivi humain, soit (b) silence confirmé → SLOT LIBÉRÉ effectif → relance Outreach Radar W23 sur fondations propres.
- **Priorité #5 — Anomalie cron Outreach Radar** : le radar n'a pas tourné depuis W18. À investiguer dès que capacité dispo (non bloquant cette semaine).

---

## Questions de synchro Audric W22 (à répondre avant tout nouvel envoi)

Sans ces réponses, le radar W23 sera lui aussi à l'aveugle. Préférable de poser explicitement plutôt que d'extrapoler.

1. **Iteanu — appel 5 ou 6/05** : a-t-il eu lieu ? Si oui, contenu et suite (DP signé, en réflexion, déclinée) ?
2. **Hubert/Dust** : retour reçu sur la question seuil clients juristes vs métier (29/04) ? Conversation toujours active ?
3. **Stefanini/CNIL** : réponse reçue dans la fenêtre 04/05 → 18/05 ? Si silence, statut actuel ?
4. **Contacts 22/04 → 27/04 (vague de 14 cibles)** : combien ont répondu ? Liste précise des répondants vs silencieux confirmés (impact direct sur quels SLOTS sont libérés au 01/06).
5. **Erdem/Remedi Finance** : a-t-il répondu au mail du 23/04 ? SLOT LIBÉRÉ devait être effectif au 18/05 si silence.

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

### W22 (2026-06-01 → 2026-06-07) — radar relancé après 4 semaines d'anomalie cron

**Lundi 01/06** :
- Radar W22 livré avec **1 cible nouvelle** (Yann Lechelle / Probabl) au lieu de 5. Décision assumée : sans pipeline à jour ni vérification LinkedIn directe individuelle possible, livrer 5 cibles aurait violé la contrainte « 0 invention de contact ». Voir draft `2026-06-01_lechelle.md`.
- **Alerte drift** placée en tête du pipeline.md : sync requise (5 questions Audric ci-dessus).
- **Aucune relance proposée** : règle fondatrice respectée (pas de relance froide).
- **Aucun SLOT LIBÉRÉ marqué automatiquement** : besoin de confirmation Audric pour les 14 contacts du 22/04 → 27/04 qui ont théoriquement atteint 35j (certains ont peut-être répondu sur Gmail entre 04/05 et 01/06, info non remontée dans pipeline).
- Trigger event identifié pour Lechelle : tribune Maddyness 12/05/2026, sujet identique à AMR (imputabilité agents IA, AI Act).

**Triggers macro vérifiés et utilisables comme accroche W23+** (si Audric veut continuer dans cette veine) :
- 07/05/2026 : accord politique Conseil/Parlement Digital Omnibus → report AI Act Annex III au 02/12/2027 (Annex I au 02/08/2028)
- 19/05/2026 : Commission EU publie draft guidelines classification high-risk AI + consultation publique ouverte jusqu'au 23/06/2026

**Cibles candidates écartées cette semaine (motif documenté)** :
- Thibaut Mercier (Drouot Avocats, tribune Bpifrance Big Media mai 2026 sur AI Act/Omnibus) : redondant avec Iteanu Avocats en cours humain. Reportée si Iteanu décline.
- Yacine Touati (CTO « SpotOn », tribune Maddyness 26/05) : entreprise « SpotOn » ambigüe (US vs FR), pas vérifiable comme EU AI Act target. SKIP.
- Naaia (plateforme SaaS gouvernance IA FR) : concurrent direct (gouvernance/conformité), pas DP. SKIP cooldown nature.
- Alberto Tepox (Hub France IA, chef projet livre blanc « Agents experts IA ») : trigger principal = présentation 27/04/2026 = J-35, **hors fenêtre <30j**. Reportable si activité plus fraîche détectée.

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
- Sync pipeline.md v6.0 (cette PR).
- Stefanini retour effectif de congés (fenêtre réponse ouverte).

**Reply Tracker W18-S19** : a tourné chaque matin (PR #20 du 29/04 → #26 du 04/05). Couche 3 anti-dérive (avertissement désynchro >48h) opérationnelle depuis le 30/04 — visible en tête de chaque PR.

**Outreach Radar W18** : N'A PAS TOURNÉ. Anomalie cron persistante. À investiguer S20 si capacité dispo (non bloquant : aucun nouveau contact souhaité avant 18/05).

**Drift detector v2** : déployé 29/04. Aucune issue créée à ce jour malgré 6 PR Reply Tracker open ; bug de robustesse à investiguer mais non bloquant (la couche 3 prompt Reply Tracker fait le job en parallèle).

---

## Changelog pipeline

- **2026-06-01 (v6.1 — radar W22)** : ALERTE drift 4 semaines en tête de fichier. +1 cible proposée (Lechelle / Probabl) avec trigger Maddyness 12/05/2026. Section « Questions de synchro Audric W22 » ajoutée — sync requise avant nouvel envoi ou avant arbitrage SLOT LIBÉRÉ massif. Aucun SLOT LIBÉRÉ marqué automatiquement (Audric doit confirmer silence vs réponse pour les 14 contacts du 22-27/04). Auteur : Outreach Radar W22 (session 01/06 matin).
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.