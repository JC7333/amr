# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 3 conversations EN COURS HUMAIN héritées (Alexandra Iteanu, Gabriel Hubert/Dust, Rémi Stefanini/CNIL — état réel inconnu, pipeline stale depuis 2026-05-04) + 1 partner LT (Adnan Khan/Centurian)**.

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (fenêtre réponse ouverte)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; retour effectif 04/05) | Directeur DTIA CNIL. Fenêtre réponse initiale 04/05 → 18/05. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. **[2026-06-18 ALERTE TRACKER]** Aucune MAJ pipeline depuis 04/05 (55j). Fenêtre théorique dépassée d'un mois — soit Stefanini a répondu hors Claude Code (statut à mettre à jour), soit silence prolongé (envisager REPORTÉ ou SLOT LIBÉRÉ manuel). À synchroniser avant tout. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | SLOT LIBÉRÉ | 2026-04-23 (email depuis audric@mandatia.eu) | **[2026-06-18 SLOT LIBÉRÉ]** silence total 56j depuis email >35j. Canal alt email épuisé. Remplaçant à proposer par Outreach Radar W26. — CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | SLOT LIBÉRÉ | 2026-04-22 | **[2026-06-18 SLOT LIBÉRÉ]** silence 57j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email avant abandon définitif si cible haute valeur (email probable juliette.mattioli@thalesgroup.com — 94,5%, valider Hunter). — Cible CAC40 défense souveraine. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | SLOT LIBÉRÉ | 2026-04-22 | **[2026-06-18 SLOT LIBÉRÉ]** silence 57j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email avant abandon définitif si cible haute valeur (ian.rogers@ledger.com — 72,9% ou @ledger.fr — 51,2%, valider Hunter). — Profil fermé. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | SLOT LIBÉRÉ | 2026-04-22 | **[2026-06-18 SLOT LIBÉRÉ]** silence 57j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email avant abandon définitif si cible haute valeur (aldrick.zappellini@credit-agricole.com — 89%, valider Hunter). |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | SLOT LIBÉRÉ | 2026-04-22 | **[2026-06-18 SLOT LIBÉRÉ]** silence 57j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email avant abandon définitif si cible haute valeur (david.rice@hsbc.com — 71%, risque doublon nom, valider Hunter). |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-26 | **[2026-06-18 SLOT LIBÉRÉ]** silence 53j >35j. Remplaçant à proposer par Outreach Radar W26. Pas de canal alt email (Hubert canal principal Dust). — CTO Dust. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-26 | **[2026-06-18 SLOT LIBÉRÉ]** silence 53j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email académique probable florence.gsell@sciencespo.fr avant abandon si cible haute valeur. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | SLOT LIBÉRÉ | 2026-04-26 | **[2026-06-18 SLOT LIBÉRÉ]** silence 53j >35j. Remplaçant à proposer par Outreach Radar W26. Connexion LinkedIn probablement jamais acceptée. Email académique marcel.salathe@epfl.ch — envisager avant abandon si cible haute valeur. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Canal email principal déjà épuisé (christine.balague@imt-bs.eu). |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN** | 2026-04-28 (réponse Alexandra : "le point que vous soulevez de la responsabilité et du mandat est fondamental, échangeons rapidement de vive voix") | Réponse de l'associée d'Olivier Iteanu (le mail initial avait été envoyé "À l'attention de Maître Iteanu" → transmis à Alexandra). **APPEL CADRÉ** : créneaux proposés 5 ou 6/5 17h30-18h30 (mail Audric 30/04). Tel direct fourni : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. **[2026-06-18 ALERTE TRACKER]** Aucune MAJ pipeline depuis 04/05 (51j). L'appel 5-6/5 a-t-il eu lieu ? Compte-rendu ? Suite donnée (DP signé, en réflexion, déclinée) ? À synchroniser **en priorité absolue** avant tout autre action. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Pas de canal alt envisagé (DG ANSSI). |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Pas de canal alt prévu. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Connexion probablement jamais acceptée. NE PAS chercher email (politique/PDG). |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email institutionnel Cigref avant abandon (cible haute valeur — 150 DSI grandes entreprises FR). |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Pas de canal alt facile (pas d'employeur fixe). |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Envisager email avant abandon (stephane.distinguin@fabernovel.com à valider Hunter). |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | Hubert a répondu 28/04 sur 1er message d'Audric : "ça dépend des tâches/de l'impact". Audric a contre-questionné 29/04 sur où il voit le seuil entre clients juristes vs métier. En attente retour Hubert au moment de la dernière synchro. Cooldown 90j maintenu. **[2026-06-18 ALERTE TRACKER]** Aucune MAJ pipeline depuis 04/05 (50j). Hubert a-t-il répondu ? Conversation morte ou DP en réflexion ? À synchroniser avant tout. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | SLOT LIBÉRÉ | 2026-04-27 | **[2026-06-18 SLOT LIBÉRÉ]** silence 52j >35j. Remplaçant à proposer par Outreach Radar W26. Pas de canal alt envisagé (PDG institution publique, secrétariat filtre). |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations EN COURS HUMAIN (héritées, état réel inconnu)** : **3** (Alexandra Iteanu, Gabriel Hubert, Rémi Stefanini) — **pipeline non synchronisé depuis 04/05/2026 (~6 semaines), MAJ manuelle requise**
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- Messages ENVOYÉS sans retour : **0** (tous transférés SLOT LIBÉRÉ le 18/06)
- Canal alt email tenté : 1 (Erdem) → silence → SLOT LIBÉRÉ 18/06
- SLOT LIBÉRÉ anticipé : 1 (Gauthier Henroz / Chift)
- **SLOT LIBÉRÉ par silence >35j (Reply Tracker 18/06)** : 16

**FUNNEL RÉEL** : **3 contacts en suivi actif** (les 3 EN COURS HUMAIN — Iteanu, Hubert, Stefanini, sous réserve de synchro) sur 22 contactés. 19 contacts hors funnel (1 SORTI partner LT + 1 SKIP + 17 SLOT LIBÉRÉ). **PRIORITÉ ABSOLUE** : Audric doit synchroniser le statut réel des 3 conversations actives avant tout nouveau Outreach Radar W26.

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

## Dates clés (historiques — toutes dépassées au 18/06/2026)

| Date | Événement |
|---|---|
| 2026-05-04 | Retour effectif Stefanini. Surveillance passive Gmail. |
| 2026-05-05 ou 06 17h30-18h30 | **APPEL ALEXANDRA ITEANU** (créneau ferme — issue inconnue dans le pipeline). |
| 2026-05-04 → 2026-05-18 | Fenêtre normale réponse Stefanini (dépassée d'un mois). |
| 2026-05-06 | Mattioli, Rogers, Zappellini, Rice fenêtre canal alt (non utilisée). |
| 2026-05-10 | Polu, G'sell, Salathé fenêtre canal alt (non utilisée). |
| 2026-05-11 | Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse fenêtre canal alt (non utilisée). |
| 2026-05-18 | Erdem 35j silence — SLOT LIBÉRÉ acté 18/06. |
| 2026-05-27 | Mattioli, Rogers, Zappellini, Rice 35j — SLOT LIBÉRÉ acté 18/06. |
| 2026-05-31 | Polu, G'sell, Salathé 35j — SLOT LIBÉRÉ acté 18/06. |
| 2026-06-01 | 9 contacts du 27/04 35j — SLOT LIBÉRÉ acté 18/06. |

---

## Actions Audric cette semaine (S25)

- **Priorité #1** : SYNCHRONISER pipeline.md avec l'état réel des 3 conversations EN COURS HUMAIN (Iteanu, Hubert, Stefanini). Ces statuts datent du 04/05 et le funnel a probablement bougé. Sans synchro, le tracker tournera dans le vide.
- **Priorité #2** : valider que les 16 SLOT LIBÉRÉ de ce run sont cohérents (mergeable tel quel). Si une cible a en fait répondu hors Claude Code, corriger.
- **Priorité #3** : relancer Outreach Radar W26 — le funnel actif est descendu à 3 (EN COURS HUMAIN) ; capacité de nouveaux envois enfin libérée. Cibler 3-5 nouveaux contacts haute valeur.
- **Priorité #4** : investiguer l'anomalie cron Outreach Radar (n'a pas tourné depuis W18 ?) et le drift detector (n'a apparemment pas créé d'issue malgré ~6 semaines de désynchro). Deux couches de protection silencieuses pendant 6 semaines = à corriger.

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
- Sync pipeline.md v6.0 (PR #27).
- Stefanini retour effectif de congés (fenêtre réponse ouverte).

### W19-W24 (2026-05-05 → 2026-06-14) — TROU DE SYNCHRONISATION

**6 semaines sans MAJ pipeline.md.** Dernière synchro confirmée 04/05/2026 (v6.0). Les 3 conversations EN COURS HUMAIN (Iteanu — appel calé 5-6/5, Hubert — question seuil en attente, Stefanini — fenêtre réponse 04→18/05) ont **probablement** évolué hors Claude Code mais aucune trace dans le pipeline. Reply Tracker a tourné chaque matin sans pouvoir actionner les transitions manuelles. **À reconstituer manuellement par Audric.**

### W25 (2026-06-15 → 2026-06-21)

**Mercredi 18/06** — Reply Tracker (Claude Opus 4.7) :
- **16 SLOT LIBÉRÉ automatiques** sur silences >35j cumulés depuis l'absence de synchro : Mattioli, Rogers, Zappellini, Rice (57j), Polu, G'sell, Salathé (53j), Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse (52j), Erdem (56j canal alt épuisé).
- Compteur funnel actif : 17 → 3 (sous réserve synchro réelle des EN COURS HUMAIN).
- **3 alertes EN COURS HUMAIN stagnance** : Stefanini 55j, Iteanu 51j, Hubert 50j sans MAJ visible.
- 0 PROPOSÉ en attente. 0 canal alt 14-20j à signaler (toutes fenêtres dépassées de plusieurs semaines).
- **Avertissement désynchro >48h** en tête de PR (couche 3 anti-dérive) — ~1072h d'écart depuis dernier commit pipeline.

---

## Changelog pipeline

- **2026-06-18 (v6.1)** : Reply Tracker — 16 SLOT LIBÉRÉ automatiques sur silences >35j accumulés pendant ~6 semaines de désynchro. Compteur funnel actif passe de 17 à 3 (sous réserve synchro réelle des EN COURS HUMAIN). Pipeline reste stale côté Iteanu/Hubert/Stefanini — Audric doit synchroniser manuellement avant toute action en aval ou Outreach Radar W26. Auteur : Reply Tracker (Claude Opus 4.7).
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
