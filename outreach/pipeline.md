# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 3 conversations EN COURS HUMAIN stagnantes (Alexandra Iteanu, Gabriel Hubert, Rémi Stefanini — toutes sans activité visible depuis >65j, alertes émises par Reply Tracker 08/07)**.

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (stagnant >65j)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04) | Directeur DTIA CNIL. Fenêtre réponse initiale 04/05 → 18/05 expirée sans retour visible. **Alerte Reply Tracker 08/07 : 75j sans update visible.** Vérifier fil Gmail avant toute action. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | **SLOT LIBÉRÉ** | 2026-04-23 (email depuis audric@mandatia.eu) | CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. **Slot libéré 2026-07-08** (canal email tenté, silence total >75j après tentative), remplaçant à proposer par Outreach Radar W29. Cooldown 90j jusqu'au 22/07. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-07-08** (77j silence total LinkedIn, aucun canal email tenté), remplaçant à proposer par Outreach Radar W29. Envisager email juliette.mattioli@thalesgroup.com (94,5%) avant abandon définitif si cible à haute valeur — valider Hunter.io. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-07-08** (77j silence total, profil fermé, aucun canal email tenté), remplaçant à proposer par Outreach Radar W29. Envisager email ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%) avant abandon définitif si cible à haute valeur — valider Hunter.io. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-07-08** (77j silence total, aucun canal email tenté), remplaçant à proposer par Outreach Radar W29. Envisager email aldrick.zappellini@credit-agricole.com (89%) avant abandon définitif si cible à haute valeur — valider Hunter.io. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-07-08** (77j silence total, aucun canal email tenté, risque doublon nom), remplaçant à proposer par Outreach Radar W29. Envisager email david.rice@hsbc.com (71%) avant abandon définitif si cible à haute valeur — valider Hunter.io. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | CTO Dust. **Slot libéré 2026-07-08** (73j silence total). Pas d'email tenté (Hubert reste canal principal Dust — ne PAS tenter email Polu). Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | Professeure droit IA. **Slot libéré 2026-07-08** (73j silence total, aucun canal email tenté), remplaçant à proposer par Outreach Radar W29. Envisager email florence.gsell@sciencespo.fr avant abandon définitif si cible à haute valeur. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | **SLOT LIBÉRÉ** | 2026-04-26 | Profil fermé, note seulement. **Slot libéré 2026-07-08** (73j silence — connexion visiblement non acceptée, aucun canal email tenté), remplaçant à proposer par Outreach Radar W29. Envisager email marcel.salathe@epfl.ch avant abandon définitif si cible à haute valeur. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | **SLOT LIBÉRÉ** | 2026-04-27 | christine.balague@imt-bs.eu (vérifié multi-source). **Slot libéré 2026-07-08** (72j silence). Email = canal principal déjà tenté, pas d'autre canal à envisager. Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN (stagnant >65j)** | 2026-04-28 (réponse Alexandra : "échangeons rapidement de vive voix") | **Alerte Reply Tracker 08/07 : 71j sans update visible du pipeline.** APPEL calé 5 ou 6/5 17h30-18h30 (mail Audric 30/04). Vérifier si l'appel a eu lieu et statut post-appel. Tel direct : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | DG ANSSI. **Slot libéré 2026-07-08** (72j silence). Pas de canal alt envisageable (PDG cible, pas de relance froide ni d'email institutionnel). Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-07-08** (72j silence total, pas de canal alt facile). Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-07-08** (72j silence — connexion visiblement non acceptée). Ne PAS chercher email (politique/PDG, ne marchera pas). Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-07-08** (72j silence LinkedIn, aucun canal email tenté). Cible stratégique. Envisager email institutionnel cigref avant abandon définitif si cible à haute valeur. Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-07-08** (72j silence). Pas de canal alt facile (pas d'employeur fixe). Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-07-08** (72j silence LinkedIn, aucun canal email tenté). Envisager email stephane.distinguin@fabernovel.com (Hunter à valider) avant abandon définitif si cible à haute valeur. Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN (stagnant >65j)** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | **Alerte Reply Tracker 08/07 : 70j sans update visible du pipeline.** Hubert avait répondu 28/04 puis Audric a contre-questionné 29/04. Vérifier fil LinkedIn pour retour éventuel. Cooldown 90j maintenu. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | PDG institution publique. Note seulement. **Slot libéré 2026-07-08** (72j silence — connexion visiblement non acceptée). Email pattern probable bruno.sportisse@inria.fr mais filtré par secrétariat, pas de canal alt envisagé. Remplaçant à proposer par Outreach Radar W29. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations EN COURS HUMAIN (stagnantes >65j, alertes émises)** : **3** (Alexandra Iteanu, Gabriel Hubert, Rémi Stefanini)
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- Messages ENVOYÉS en attente naturelle : **0** (tous passés SLOT LIBÉRÉ le 08/07)
- Canal alt email tenté puis silence : 1 (Erdem, SLOT LIBÉRÉ 08/07)
- SLOT LIBÉRÉ total : **17** (Gauthier anticipé 04/05 + 16 libérés le 08/07)

**FUNNEL RÉEL** : 3 contacts en EN COURS HUMAIN (tous stagnants, à vérifier manuellement) + 17 slots libérés à repourvoir. **Nécessite ré-alimentation Outreach Radar W29+** après vérification des 3 conversations stagnantes.

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
| **2026-07-08 (aujourd'hui)** | Sync massive SLOT LIBÉRÉ : 16 contacts basculés après désynchro pipeline de 65j. |
| 2026-07-13 | Fin cooldown Gauthier (Chift). |
| 2026-07-14 | Fin cooldown Adnan (partner LT). |
| 2026-07-21 → 2026-07-27 | Fins de cooldown en cascade (Mattioli, Rogers, Zappellini, Rice, Erdem, Stefanini, Polu, G'sell, Salathé, Balagué, Iteanu, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse, Hubert). |
| **W29 (2026-07-13 →)** | Réactivation Outreach Radar prévue pour repourvoir 17 slots libérés — APRÈS vérification manuelle des 3 EN COURS HUMAIN stagnants. |

---

## Actions Audric cette semaine (S28 → S29)

- **Priorité #1** : **VÉRIFIER LES 3 CONVERSATIONS EN COURS HUMAIN STAGNANTES**. Le pipeline n'a pas été touché depuis 65j.
  - **Alexandra Iteanu** : l'appel calé 5 ou 6/5 a-t-il eu lieu ? Statut post-appel ? Confidentialité avocat-client signée ?
  - **Gabriel Hubert (Dust)** : retour éventuel après le 2e message d'Audric du 29/04 ? Vérifier fil LinkedIn.
  - **Rémi Stefanini (CNIL)** : retour éventuel après la fenêtre 04/05 → 18/05 ? Vérifier fil Gmail audric@mandatia.eu.
  Selon les retours, actualiser statuts (CONVERTI DP / DÉCLINÉ / REPORTÉ / SLOT LIBÉRÉ manuel).
- **Priorité #2** : décider si Outreach Radar redémarre W29 pour repourvoir les 17 slots libérés, ou si focus reste sur les 3 conversations en cours (finalisation DP avant nouveaux contacts).
- **Priorité #3** : investiguer l'anomalie cron Outreach Radar (n'a pas tourné depuis W18) et le bug drift detector v2 (aucune issue drift créée malgré 65j de désynchro — la couche 3 a fait son travail cependant).
- **Priorité #4** : re-synchroniser pipeline.md avec l'état réel des envois AVANT toute nouvelle campagne. Le tracker actuel a pris ses décisions sur des données de 65j, à valider manuellement.

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

### W19 → W27 (2026-05-05 → 2026-07-07) — TROU DE SYNCHRO

**Aucun commit sur pipeline.md pendant 65 jours (04/05 → 08/07).** Reply Tracker a probablement continué de tourner en émettant l'avertissement désynchro à chaque run. Statut réel des 3 conversations EN COURS HUMAIN inconnu du pipeline ; à reconstituer manuellement par Audric.

### W28 (2026-07-06 → 2026-07-12)

**Mercredi 08/07** :
- Reply Tracker exécute la sync automatique : 16 SLOT LIBÉRÉ (15 ENVOYÉ + Erdem CANAL ALT TENTÉ). 3 alertes EN COURS HUMAIN stagnants émises. Avertissement désynchro pipeline (~1540h / ~65j) en tête de PR.

---

## Changelog pipeline

- **2026-07-08 (v7.0)** : SYNC MASSIVE POST-DÉSYNCHRO 65j. 16 contacts basculés en SLOT LIBÉRÉ (Mattioli, Rogers, Zappellini, Rice, Polu, G'sell, Salathé, Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse, Erdem). 3 EN COURS HUMAIN inchangés côté statut mais notés stagnants avec alerte >65j sans update visible. Compteur FUNNEL passé de "17 en suivi actif" à "3 EN COURS HUMAIN + 17 slots à repourvoir". Auteur : Reply Tracker automatique (Claude Code on the web).
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
