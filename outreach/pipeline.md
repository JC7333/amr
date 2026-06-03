# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 3 conversations actives mais toutes stagnantes ≥35j (Alexandra Iteanu — appel calé 5 ou 6/5 puis silence ; Gabriel Hubert/Dust — silence post 2e message 29/04 ; Rémi Stefanini/CNIL — fenêtre réponse théorique fermée 18/05 sans retour)**.

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (fenêtre réponse fermée)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; retour effectif 04/05 attendu) | Directeur DTIA CNIL. Fenêtre réponse théorique 04/05 → 18/05 désormais close depuis 16j. **Tracker 03/06 : alerte EN COURS HUMAIN stagnant 40j.** Surveillance passive maintenue. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | **SLOT LIBÉRÉ** | 2026-04-23 (email depuis audric@mandatia.eu) | CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. **Slot libéré 2026-06-03** (silence total >35j post-canal alt, bascule 18/05 explicitement prévue dans pipeline v6.0 atteinte). Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-03** (42j silence total, auto-bascule >35j). Canal email jamais activé — envisager juliette.mattioli@thalesgroup.com (94,5%) via validation Hunter AVANT abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | **SLOT LIBÉRÉ** | 2026-04-22 | Profil fermé. **Slot libéré 2026-06-03** (42j silence total, auto-bascule >35j). Canal email jamais activé — envisager ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%) via Hunter avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-03** (42j silence total, auto-bascule >35j). Canal email jamais activé — envisager aldrick.zappellini@credit-agricole.com (89%) via Hunter avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-03** (42j silence total, auto-bascule >35j). Canal email jamais activé — risque doublon nom, validation Hunter requise sur david.rice@hsbc.com (71%) avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | CTO Dust. **Slot libéré 2026-06-03** (38j silence total, auto-bascule >35j). Pas de canal alt tenté (Hubert = canal Dust principal, équipe Dust déjà au courant via Hubert). Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | Professeure droit IA. **Slot libéré 2026-06-03** (38j silence total, auto-bascule >35j). Canal email jamais activé — envisager florence.gsell@sciencespo.fr via validation Hunter avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | **SLOT LIBÉRÉ** | 2026-04-26 | Profil fermé, note seulement. **Slot libéré 2026-06-03** (38j silence, connexion non acceptée). Canal email jamais activé — envisager marcel.salathe@epfl.ch via validation Hunter avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | **SLOT LIBÉRÉ** | 2026-04-27 | christine.balague@imt-bs.eu (vérifié multi-source). **Slot libéré 2026-06-03** (37j silence total, auto-bascule >35j). Email = canal principal déjà utilisé, pas de canal alt prévu. Abandon définitif. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN** | 2026-04-28 (réponse Alexandra : "le point que vous soulevez de la responsabilité et du mandat est fondamental, échangeons rapidement de vive voix") | Réponse de l'associée d'Olivier Iteanu (le mail initial avait été envoyé "À l'attention de Maître Iteanu" → transmis à Alexandra). **APPEL CADRÉ** : créneaux proposés 5 ou 6/5 17h30-18h30 (mail Audric 30/04). Tel direct fourni : 06.43.90.40.24. **Tracker 03/06 : alerte EN COURS HUMAIN stagnant 36j sans suite documentée post appel 5/6 mai.** Vérifier fil de discussion + statut appel + suivi à faire. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | DG ANSSI. **Slot libéré 2026-06-03** (37j silence total, auto-bascule >35j). Pas de relance froide ni d'email institutionnel envisagé (PDG cible). Abandon définitif. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-03** (37j silence total, auto-bascule >35j). Pas de canal alt prévu. Abandon définitif. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | Profil fermé probable, note seulement. **Slot libéré 2026-06-03** (37j silence, connexion non acceptée). Pas de canal alt (politique/PDG, ne marchera pas). Abandon définitif. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. Cible stratégique. **Slot libéré 2026-06-03** (37j silence total, auto-bascule >35j). Canal email jamais activé — envisager email institutionnel cigref via Hunter avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-06-03** (37j silence total, auto-bascule >35j). Pas de canal alt facile (pas d'employeur fixe). Abandon définitif. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | Hubert a répondu 28/04 sur 1er message d'Audric : "ça dépend des tâches/de l'impact". Audric a contre-questionné 29/04 sur où il voit le seuil entre clients juristes vs métier dans l'usage agent. **Tracker 03/06 : alerte EN COURS HUMAIN stagnant 35j sans retour Hubert sur le 2e message.** Vérifier fil de discussion LinkedIn. Cooldown 90j maintenu. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-06-03** (37j silence total, auto-bascule >35j). Canal email jamais activé — envisager stephane.distinguin@fabernovel.com via Hunter avant abandon définitif si cible haute valeur. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | PDG institution publique. Note seulement. **Slot libéré 2026-06-03** (37j silence, connexion non acceptée). Email pattern probable bruno.sportisse@inria.fr mais filtré par secrétariat. Pas de canal alt envisagé. Abandon définitif. Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations actives** : **3 mais toutes stagnantes ≥35j** (Alexandra Iteanu — appel 5 ou 6/5 puis silence 36j ; Gabriel Hubert — silence 35j post 2e message ; Rémi Stefanini — fenêtre fermée 18/05 sans retour, silence 40j)
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- Messages ENVOYÉS sans retour : **0** (tous basculés SLOT LIBÉRÉ au 03/06)
- Canal alt email tenté : 1 (Erdem) → silence → SLOT LIBÉRÉ
- SLOT LIBÉRÉ total : **17** (Gauthier 04/05 anticipé + Erdem 03/06 post-canal-alt + 15 contacts massifs 03/06)

**FUNNEL RÉEL** : 3 contacts en conversation active mais TOUTES stagnantes ≥35j. Aucun contact frais en file. **Outreach Radar W18-W23 N'A PAS TOURNÉ** (anomalie persistante signalée depuis W18) → reprise critique W24 nécessaire pour reconstituer un pipeline. Capacité d'envoi entièrement libérée. La priorité opérationnelle bascule de "cadrage conversations chaudes" vers "audit conversations stagnantes + relance Outreach Radar".

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
| 2026-05-04 | Retour effectif Stefanini. Surveillance passive Gmail. |
| 2026-05-05 ou 06 17h30-18h30 | APPEL ALEXANDRA ITEANU (créneau proposé par Audric 30/04). |
| 2026-05-04 ou 05 soir | Préparation appel Iteanu : récit fondateur + 3 questions à envoyer 24h avant + lignes rouges. |
| 2026-05-06 | Mattioli, Rogers, Zappellini, Rice atteignent 14j silence → fenêtre canal alt ouverte |
| 2026-05-04 → 2026-05-18 | Fenêtre normale réponse Stefanini |
| 2026-05-10 | Polu, G'sell, Salathé atteignent 14j silence → fenêtre canal alt |
| 2026-05-11 | Balagué, Iteanu, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse atteignent 14j silence |
| 2026-05-18 | Erdem atteint 35j silence → SLOT LIBÉRÉ |
| 2026-05-27 | Mattioli, Rogers, Zappellini, Rice atteignent 35j silence → SLOT LIBÉRÉ |
| 2026-05-31 | Polu, G'sell, Salathé atteignent 35j → SLOT LIBÉRÉ |
| 2026-06-01 | 9 contacts du 27/04 atteignent 35j → SLOT LIBÉRÉ massif |
| **2026-06-03 (aujourd'hui)** | **Tracker exécute la bascule SLOT LIBÉRÉ automatique massive (16 contacts).** |

---

## Actions Audric cette semaine (S22-W23)

> Section S19 conservée pour archive (priorités obsolètes). Voir priorités à jour ci-dessous.

**Priorités à jour 2026-06-03** :

- **Priorité #1** : auditer les 3 conversations EN COURS HUMAIN stagnantes (Iteanu 36j post appel 5/6 mai non documenté ; Hubert 35j post 2e message ; Stefanini 40j post fenêtre fermée 18/05). Décider pour chacune : relance cadrée (exception conversation orale démarrée puis tue, cf. Iteanu si appel a eu lieu) OU passage manuel SLOT LIBÉRÉ/REPORTÉ/DÉCLINÉ. **À traiter avant tout nouvel outreach.**
- **Priorité #2** : redémarrer Outreach Radar W24 (n'a pas tourné depuis W18). Capacité d'envoi entièrement libérée par la bascule massive de SLOT LIBÉRÉ.
- **Priorité #3** : pour les SLOT LIBÉRÉ haute valeur où canal email n'a jamais été activé (Mattioli/Thales, Rogers/Ledger, Zappellini/CA, Rice/HSBC, G'sell/SciencesPo, Salathé/EPFL, d'Agrain/Cigref, Distinguin/Fabernovel), décider canal email UNE fois via Hunter validation OU abandon définitif (8 décisions binaires). Pas de relance froide LinkedIn.
- **Priorité #4** : sync pipeline.md immédiate après chaque décision (règle synchro <24h ; désynchro 30j détectée aujourd'hui, à ne pas reproduire).

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

### W19-W23 (2026-05-04 → 2026-06-03)

**Anomalie majeure : pipeline.md non synchronisé depuis 04/05** (30j de désynchro détectée par Tracker 03/06). Aucun signal d'activité outreach visible côté git. Trois scénarios non distinguables sans audit Audric :
1. Audric a continué hors pipeline (envois LinkedIn / suivis EN COURS HUMAIN non consignés).
2. Audric a stoppé l'outreach (focus produit/code AMR).
3. Mélange : conversations chaudes traitées hors pipeline, pas de nouveaux envois.

**Outreach Radar W19-W23** : N'A PAS TOURNÉ. Anomalie persistante depuis W18.

**Reply Tracker W19-W23** : statut inconnu côté commits (aucune PR sur main entre 04/05 et 03/06). Bascule rétroactive massive opérée par le Tracker du 03/06.

### W23 (2026-06-01 → 2026-06-07)

**Mercredi 03/06** :
- Tracker bascule 16 contacts SLOT LIBÉRÉ automatique (15 ENVOYÉ >35j + Erdem CANAL ALT TENTÉ >35j post-bascule 18/05).
- 3 alertes EN COURS HUMAIN stagnant (Iteanu 36j, Hubert 35j, Stefanini 40j) générées.
- Funnel actif passe de 17 à 3 contacts (tous stagnants).
- Avertissement désynchro pipeline 30j attaché à la PR (couche 3 anti-dérive).

---

## Changelog pipeline

- **2026-06-03 (v7.0)** : SLOT LIBÉRÉ AUTOMATIQUE MASSIF par Reply Tracker. 15 contacts ENVOYÉ ayant dépassé 35j de silence (Mattioli, Rogers, Zappellini, Rice, Polu, G'sell, Salathé, Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse) + Erdem (CANAL ALT TENTÉ >35j post-bascule 18/05) passent SLOT LIBÉRÉ. Funnel actif passe de 17 à 3 (tous EN COURS HUMAIN, tous stagnants ≥35j). 3 alertes EN COURS HUMAIN générées (Stefanini 40j, Iteanu 36j, Hubert 35j). Avertissement désynchro 30j attaché : pipeline non touché depuis le 04/05 (v6.0), bascule rétroactive opérée. Action #1 : audit conversations actives + redémarrage Outreach Radar W24. Auteur : Reply Tracker automatique.
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
