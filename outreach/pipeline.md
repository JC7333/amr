# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 3 conversations EN COURS HUMAIN stagnantes >50j selon dernier état pipeline (Alexandra Iteanu, Gabriel Hubert, Rémi Stefanini), 16 slots libérés le 2026-06-20 (silence >35j) — ⚠️ pipeline désynchro 46j, à vérifier avant action**.

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (stagnance >50j ⚠️)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; retour effectif annoncé 04/05) | Directeur DTIA CNIL. Fenêtre réponse initiale 04/05 → 18/05 désormais largement dépassée. **57j sans MAJ pipeline visible.** Vérifier Gmail audric@mandatia.eu pour réponse éventuelle ou statuer REPORTÉ/SKIP si silence définitif. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | **SLOT LIBÉRÉ** | 2026-04-23 (email depuis audric@mandatia.eu) | CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. **Slot libéré 2026-06-20** : silence total 58j depuis email (LinkedIn + email tous deux tentés). Remplaçant à proposer par Outreach Radar W26. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-20** : silence LinkedIn 59j. Cible CAC40 haute valeur — envisager email juliette.mattioli@thalesgroup.com (94,5% confiance, validation Hunter requise) avant abandon définitif. Sinon remplaçant Outreach Radar W26. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-20** : silence LinkedIn 59j, profil fermé. Email à valider Hunter avant tentative finale : ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%). Sinon remplaçant Outreach Radar W26. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-20** : silence LinkedIn 59j. Email probable aldrick.zappellini@credit-agricole.com (89%, valider Hunter). Envisager email avant abandon si cible haute valeur. Sinon remplaçant Outreach Radar W26. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-20** : silence LinkedIn 59j. Email probable david.rice@hsbc.com (71%, risque doublon nom, valider Hunter). Envisager email avant abandon si cible haute valeur. Sinon remplaçant Outreach Radar W26. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | **Slot libéré 2026-06-20** : silence LinkedIn 55j. CTO Dust. **NE PAS tenter email** (Hubert canal principal Dust). Si Hubert se relance, Polu redeviendra accessible par ricochet. Remplaçant Outreach Radar W26. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | **Slot libéré 2026-06-20** : silence LinkedIn 55j. Email probable florence.gsell@sciencespo.fr — envisager UNE tentative email avant abandon définitif si cible toujours pertinente. Sinon remplaçant Outreach Radar W26. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | **SLOT LIBÉRÉ** | 2026-04-26 | **Slot libéré 2026-06-20** : silence 55j, connexion LinkedIn probablement non acceptée. Email marcel.salathe@epfl.ch — envisager UNE tentative avant abandon définitif. Sinon remplaçant Outreach Radar W26. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence email 54j. Email = canal principal déjà tenté (christine.balague@imt-bs.eu vérifié multi-source). Pas de canal alt restant. Remplaçant Outreach Radar W26. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN (stagnance >50j ⚠️)** | 2026-04-28 (réponse Alexandra : "le point que vous soulevez de la responsabilité et du mandat est fondamental, échangeons rapidement de vive voix") | Réponse de l'associée d'Olivier Iteanu (le mail initial avait été envoyé "À l'attention de Maître Iteanu" → transmis à Alexandra). **APPEL CADRÉ** prévu 5 ou 6/5 17h30-18h30 (mail Audric 30/04). **53j sans MAJ pipeline visible.** Vérifier issue de l'appel et statuer (CONVERTI DP / REPORTÉ / SUITE / DÉCLINÉ). Tel direct fourni : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence LinkedIn 54j. DG ANSSI. Pas de canal alt (PDG cible, pas de relance froide ni d'email institutionnel envisagé). Remplaçant Outreach Radar W26. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence LinkedIn 54j. Pas de canal alt prévu. Remplaçant Outreach Radar W26. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence 54j, connexion probablement non acceptée. NE PAS chercher email (politique/PDG, ne marchera pas). Remplaçant Outreach Radar W26. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence LinkedIn 54j. **Cible stratégique** — envisager UNE tentative email institutionnel cigref (validation Hunter requise) avant abandon définitif. Sinon remplaçant Outreach Radar W26. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence LinkedIn 54j. Pas de canal alt facile (pas d'employeur fixe). Remplaçant Outreach Radar W26. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence LinkedIn 54j. Email probable stephane.distinguin@fabernovel.com — envisager UNE tentative (validation Hunter) avant abandon. Sinon remplaçant Outreach Radar W26. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN (stagnance >50j ⚠️)** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | Hubert a répondu 28/04 sur 1er message d'Audric : "ça dépend des tâches/de l'impact". Audric a contre-questionné 29/04 sur seuil clients juristes vs métier. **52j sans MAJ pipeline visible.** Vérifier fil LinkedIn pour réponse Hubert et statuer. Si silence confirmé : conversation morte, ne PAS insister. Cooldown 90j maintenu. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-20** : silence 54j, PDG institution publique, note seulement. Email bruno.sportisse@inria.fr filtré secrétariat. Pas de canal alt envisagé. Remplaçant Outreach Radar W26. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations EN COURS HUMAIN stagnantes** : **3** (Alexandra Iteanu, Gabriel Hubert, Rémi Stefanini — toutes >50j sans MAJ visible, à statuer)
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- **Slots libérés 2026-06-20** : 16 (Erdem + Mattioli + Rogers + Zappellini + Rice + Polu + G'sell + Salathé + Balagué + Strubel + Bouverot + Cédric O + d'Agrain + Krim + Distinguin + Sportisse)
- SLOT LIBÉRÉ anticipé antérieur : 1 (Gauthier Henroz / Chift)
- SKIP / SORTI FUNNEL : 2 (Houlès, Adnan)

**FUNNEL RÉEL APRÈS PURGE 2026-06-20** : 3 contacts en EN COURS HUMAIN (à statuer urgemment), 0 ENVOYÉ actif, 0 PROPOSÉ. **Capacité Outreach Radar W26 totalement disponible** — proposer jusqu'à 16 remplaçants si Audric le souhaite, sous réserve de confirmation préalable de l'état réel des 3 conversations stagnantes.

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
| **2026-06-20 (aujourd'hui)** | Purge massive SLOT LIBÉRÉ (16 contacts). 3 EN COURS HUMAIN à statuer urgemment. |
| 2026-07-13 → 2026-07-27 | Sortie progressive des cooldowns 90j (premier : Chift le 13/07). |

---

## Actions Audric cette semaine (S25)

- **Priorité #1** : **statuer les 3 EN COURS HUMAIN stagnants** (Iteanu, Hubert, Stefanini). Vérifier Gmail audric@mandatia.eu + fil LinkedIn Hubert + suite appel Iteanu prévu 5 ou 6/5. Mettre à jour pipeline avec verdict (CONVERTI DP / REPORTÉ / DÉCLINÉ / SUITE).
- **Priorité #2** : décider du sort des 4 cibles haute valeur où une UNE tentative email est encore acceptable AVANT abandon (Mattioli/Thales, Zappellini/CA, Rice/HSBC, d'Agrain/Cigref). Si oui : valider emails sur Hunter.io, envoyer via audric@mandatia.eu, mettre à jour pipeline en CANAL ALT TENTÉ.
- **Priorité #3** : déclencher Outreach Radar W26 pour proposer remplaçants (jusqu'à 16 slots disponibles).
- **Priorité #4** : investiguer anomalie cron Outreach Radar (n'a pas tourné depuis W17) et bug pipeline-drift-detector v2 (n'a rien remonté malgré 46j de désynchro).

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

### W19 → W25 (2026-05-05 → 2026-06-20)

**PIPELINE NON SYNCHRONISÉ pendant 46 jours.** Aucune mise à jour de pipeline.md depuis le 04/05. L'état réel des envois et conversations entre le 05/05 et le 20/06 est inconnu du tracker.

**Reply Tracker 2026-06-20** : déclenche purge automatique des 16 contacts ENVOYÉ/CANAL ALT TENTÉ dépassant 35j de silence selon dernières dates connues, et lève 3 alertes EN COURS HUMAIN stagnantes >50j. Avertissement désynchro 46j émis en tête de PR.

---

## Changelog pipeline

- **2026-06-20 (v7.0)** : PURGE AUTOMATIQUE Reply Tracker après 46j de désynchro. 15 ENVOYÉ + 1 CANAL ALT TENTÉ (Erdem) → SLOT LIBÉRÉ (silence >35j). 3 EN COURS HUMAIN (Iteanu, Hubert, Stefanini) annotés stagnants >50j sans MAJ visible, à statuer par Audric. Funnel actif réduit à 3 conversations à clarifier + 16 slots remplaçables. Auteur : Reply Tracker automatique (Claude).
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
