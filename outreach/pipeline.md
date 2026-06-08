# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés. État réel conversations chaudes du 04/05 à confirmer par Audric (cf. ⚠️ DÉSYNCHRO ci-dessous).**

Fondateur: Audric Bugnard (Aix-les-Bains, FR). Produit: mandatia.eu.

**Email pro actif** : audric@mandatia.eu (Zimbra Starter OVH, SPF + DKIM + DMARC configurés, mail-tester.com score 10/10 le 23/04).

---

## ⚠️ DÉSYNCHRO MAJEURE détectée le 2026-06-08 (W24)

Dernière mise à jour pipeline : **2026-05-04**. Aujourd'hui : **2026-06-08** (35 jours d'écart).

L'Outreach Radar n'a pas tourné W19-W23 (anomalie cron déjà notée v6.0, jamais résolue). Toutes les dates clés planifiées dans la v6.0 sont déjà passées sans confirmation Audric :

| Date planifiée v6.0 | Événement attendu | Statut au 08/06/2026 |
|---|---|---|
| 2026-05-05 ou 06 | Appel Alexandra Iteanu | **STATUT INCONNU — Audric à confirmer** (eu lieu ? converti DP ? décliné ?) |
| 2026-05-04 → 18/05 | Fenêtre réponse Stefanini (CNIL) | **EXPIRÉE — Audric à confirmer** (réponse reçue ? silence ? slot libéré ?) |
| 2026-05-06 → 27/05 | Mattioli/Rogers/Zappellini/Rice fenêtre canal alt puis SLOT LIBÉRÉ | **EXPIRÉE — SLOT LIBÉRÉ planifié, action canal alt à confirmer** |
| 2026-05-18 | Erdem 35j silence → SLOT LIBÉRÉ | **EXPIRÉE — SLOT LIBÉRÉ planifié** |
| 2026-05-27 → 01/06 | Vague massive SLOT LIBÉRÉ (12 contacts du 22-27/04) | **EXPIRÉE — SLOT LIBÉRÉ planifié** |
| 2026-05-29 → 06 | Retour Hubert sur question seuil ? | **STATUT INCONNU — Audric à confirmer** |

**Action requise Audric (cette semaine S24)** :
1. Vérifier Gmail audric@mandatia.eu : retours Iteanu / Hubert / Stefanini / autres.
2. Mettre à jour les statuts des contacts ENVOYÉ ci-dessous (CONVERTI DP / DÉCLINÉ / EN COURS HUMAIN / SLOT LIBÉRÉ confirmé).
3. Confirmer ou infirmer le compteur DP réel.

**Conséquence pour le radar** : par défaut, tous les contacts ENVOYÉ entre 14/04 et 27/04 sont marqués `SLOT LIBÉRÉ (planifié, à confirmer)` ci-dessous. Cooldown 90j inchangé sur l'employeur.

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

**⚠️ Le détecteur de drift n'a pas alerté sur la désynchro W19-W23. Bug à investiguer en parallèle.**

---

## Légende statut

- `ENVOYÉ` — message envoyé, date dans colonne Dernier échange
- `PROPOSÉ W{xx}` — Outreach Radar a proposé, Audric n'a pas encore envoyé
- `CANAL ALT TENTÉ` — 2e canal tenté après silence LinkedIn 14j (une seule fois)
- `SLOT LIBÉRÉ` — silence total >35j, remplaçant à proposer
- `SLOT LIBÉRÉ (planifié, à confirmer)` — date 35j atteinte théoriquement mais désynchro = statut réel non vérifié
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
| 2026-04-15 | Adnan Khan | Equinix → Centurian.ai | Infra / Datacenter → Plateforme runtime gouvernance agents | LinkedIn | **SORTI FUNNEL** | 2026-04-27 | Reclassé partner LT le 04/05/2026. Pas DP. Pas de relance froide. |
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email 24/04 | **STATUT INCONNU (fenêtre réponse expirée 18/05)** | 2026-04-24 (dernier connu) | Fenêtre 04/05 → 18/05 expirée sans confirmation Audric. Soit réponse reçue (à confirmer), soit silence (SLOT LIBÉRÉ planifié 28/05). Confidentialité absolue. Pas de relance froide. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL | LinkedIn + email 23/04 | **SLOT LIBÉRÉ (planifié 18/05, à confirmer)** | 2026-04-23 | Cooldown 90j maintenu jusqu'au 22/07. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA | LinkedIn (FR) | **SLOT LIBÉRÉ** | 2026-04-14 | Décision 04/05 anti-dilution. Cooldown 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ (planifié 27/05, à confirmer)** | 2026-04-22 | Canal alt fenêtre 06/05 → action inconnue. Cooldown 21/07. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion | **SLOT LIBÉRÉ (planifié 27/05, à confirmer)** | 2026-04-22 | Profil fermé. Cooldown 21/07. |
| 2026-04-22 | Aldrick Zappellini | Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ (planifié 27/05, à confirmer)** | 2026-04-22 | Cooldown 21/07. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ (planifié 27/05, à confirmer)** | 2026-04-22 | Cooldown 21/07. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 31/05, à confirmer)** | 2026-04-26 | Hubert canal principal Dust, pas Polu. Cooldown 25/07. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 31/05, à confirmer)** | 2026-04-26 | Cooldown 25/07. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion | **SLOT LIBÉRÉ (planifié 31/05, à confirmer)** | 2026-04-26 | Profil fermé. Cooldown 25/07. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / IA — Sorbonne | Email + appel | **STATUT INCONNU — appel calé 05 ou 06/05, résultat non confirmé Audric** | 2026-04-30 (dernier mail Audric connu) | **CRITIQUE** : appel le plus important du pipeline, résultat inconnu. Audric à confirmer EN COURS HUMAIN / CONVERTI DP / DÉCLINÉ. Cooldown 27/07. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | Cédric O | Ex-Sec d'État / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème | LinkedIn message direct | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct | **STATUT INCONNU — dernière interaction Audric 29/04** | 2026-04-29 (Audric question seuil) | Conversation chaude au 04/05. Si retour Hubert reçu entre 04/05 et 08/06 = EN COURS HUMAIN. Si silence = vraisemblablement perdu. Audric à confirmer. Cooldown 26/07. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria | LinkedIn note connexion | **SLOT LIBÉRÉ (planifié 01/06, à confirmer)** | 2026-04-27 | Cooldown 26/07. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Audric a arbitré NON. |
| **2026-06-08 (PROPOSÉ W24)** | **Arno Amabile** | **Ministère Justice (Observatoire IA)** | **Secteur public / justice** | **LinkedIn direct (à confirmer Audric) ou note 200c** | **PROPOSÉ W24** | — | **Score 87. Trigger 01/06 nomination Observatoire IA Justice. Cible #1 prioritaire de la semaine — trigger ultra-frais, fenêtre attention courte.** |
| **2026-06-08 (PROPOSÉ W24)** | **Kaoutar Sghiouer** | **Sanofi** | **Pharma CAC40** | **LinkedIn (probable InMail) + email PROBABLE** | **PROPOSÉ W24** | — | **Score 87. Trigger Fortune 27/05 + Snowflake Summit 1-4/06 + VivaTech 17-20/06. Verbatim "traceability/guardrails/accountability" aligné AMR.** |
| **2026-06-08 (PROPOSÉ W24)** | **Eric Robert** | **EDF** | **Énergie / institution stratégique** | **LinkedIn direct + email PROBABLE** | **PROPOSÉ W24** | — | **Score 82. Trigger AION 21/05 + workshop 2025 "gouvernance IA agentique" en contexte. Risque homonyme email à valider.** |
| **2026-06-08 (PROPOSÉ W24)** | **Evelyne Llauro-Barrès** | **MAIF** | **Assurance / mutuelle** | **LinkedIn direct + email PROBABLE** | **PROPOSÉ W24** | — | **Score 78. Trigger 07/05 (32j, juste hors fenêtre stricte — disclaimer transparent). Accord IA MAIF unanime syndicats, Commission CSE outillage = besoin AMR.** |

---

## Compteur Design Partners

- Signés: **0 / 5** (sous réserve confirmation Audric sur conversations 04/05)
- **Conversations chaudes du 04/05 — statut inconnu W24** : Iteanu, Hubert, Stefanini (Audric à confirmer)
- Messages ENVOYÉS sans retour confirmé (devenus SLOT LIBÉRÉ planifié) : **14**
- Canal alt email tenté : 1 (Erdem) → SLOT LIBÉRÉ planifié 18/05
- SLOT LIBÉRÉ anticipé (avant 35j) : 1 (Gauthier Henroz)
- **Nouvelles cibles PROPOSÉES W24** : 4 (Amabile, Sghiouer, Robert, Llauro-Barrès)

**FUNNEL au 08/06/2026 (sous réserve confirmation Audric)** :
- 3 contacts en suivi actif théorique (Iteanu, Hubert, Stefanini)
- 14 contacts SLOT LIBÉRÉ planifié (Erdem + 13 autres)
- 4 nouvelles cibles PROPOSÉES W24
- 1 SORTI FUNNEL (Adnan), 1 SLOT LIBÉRÉ anticipé (Gauthier), 1 SKIP (Houlès)

---

## Contacts déjà sollicités (cooldown 90j)

Cooldown inchangé, calculé sur date premier contact + 90j. Tous les contacts ci-dessous = employeur EXCLU de la recherche de nouvelles cibles.

- Equinix → Centurian.ai (Adnan, 14/04) — cooldown jusqu'au 13/07
- CNIL (Stefanini, 22/04) — cooldown 21/07
- Remedi Finance (Erdem, 14/04) — cooldown 13/07
- Chift (Gauthier, 14/04) — cooldown 13/07
- Thales (Mattioli, 22/04) — cooldown 21/07
- Ledger (Rogers, 22/04) — cooldown 21/07
- Crédit Agricole (Zappellini, 22/04) — cooldown 21/07
- HSBC (Rice, 22/04) — cooldown 21/07
- Dust.tt (Polu 26/04 + Hubert 27/04) — cooldown 25/07 et 26/07
- Sciences Po (G'sell, 26/04) — cooldown 25/07
- EPFL (Salathé, 26/04) — cooldown 25/07
- IMT-BS (Balagué, 27/04) — cooldown 26/07
- Iteanu Avocats (Alexandra, 28/04) — cooldown 27/07
- ANSSI (Strubel, 27/04) — cooldown 26/07
- AI Action Summit (Bouverot, 27/04) — cooldown 26/07
- Cédric O (perso, 27/04) — cooldown 26/07
- Cigref (d'Agrain, 27/04) — cooldown 26/07
- Tariq Krim (perso, 27/04) — cooldown 26/07
- Fabernovel (Distinguin, 27/04) — cooldown 26/07
- Inria (Sportisse, 27/04) — cooldown 26/07
- **Nouveaux W24** :
  - Ministère Justice / Current AI (Amabile, prévu 08/06) — cooldown 06/09
  - Sanofi (Sghiouer, prévu 08/06) — cooldown 06/09
  - EDF (Robert, prévu 08/06) — cooldown 06/09
  - MAIF (Llauro-Barrès, prévu 08/06) — cooldown 06/09

---

## Contacts CNIL backup (ne pas solliciter sans invitation explicite de Stefanini)

- **Vincent Toubiana** (vtoubiana@cnil.fr)
- **Florent Della-Valle** (fdella-valle@cnil.fr)

Connus via l'autoreply institutionnel de Stefanini. **NE JAMAIS contacter de propre initiative.**

---

## Dates clés W24 et au-delà

| Date | Événement |
|---|---|
| **2026-06-08 (aujourd'hui, lundi)** | Outreach Radar W24 — 4 nouvelles cibles proposées. Audric à statuer sur conversations 04/05 (Iteanu, Hubert, Stefanini). |
| **2026-06-08 → 14** | Envoi cibles W24 par Audric (priorité #1 Amabile, trigger 7j seulement). |
| **2026-06-17 → 20** | **VivaTech 2026** Paris — Kaoutar Sghiouer (Sanofi) intervient sur "AI & Productivity". Opportunité contact au salon si Audric s'y rend. |
| **2026-07-13** | Cooldown 90j Adnan/Gauthier/Erdem expire — leurs employeurs redeviennent sourçables. |
| **2026-07-13** | J+35 cibles W24 — silence total = SLOT LIBÉRÉ pour Amabile/Sghiouer/Robert/Llauro-Barrès. |
| **2026-08-02** | **Date légale AI Act Annex III** (report probable 02/12/2027 via Digital Omnibus). Si maintenue, fenêtre attention compliance officers maximale fin juin / début juillet. |

---

## Actions Audric cette semaine (S24)

- **Priorité #1** : **synchroniser pipeline avec réel**. Vérifier Gmail audric@mandatia.eu + LinkedIn pour réponses tardives Iteanu / Hubert / Stefanini / autres. Mettre à jour les statuts dans pipeline.md ci-dessus.
- **Priorité #2** : envoyer le message Arno Amabile (Observatoire IA Justice) dès aujourd'hui ou demain — trigger 7j, fenêtre d'attention courte avant que les sollicitations affluent. **Voir `outreach/drafts/2026-06-08_amabile.md`.**
- **Priorité #3** : envoyer Kaoutar Sghiouer (Sanofi) avant VivaTech (17/06) — l'angle "agents IA Sanofi + traceability" est encore chaud, et VivaTech va saturer l'inbox des SVP. **Voir `outreach/drafts/2026-06-08_sghiouer.md`.**
- **Priorité #4** : envoyer Eric Robert (EDF) en milieu de semaine. **Voir `outreach/drafts/2026-06-08_robert.md`.**
- **Priorité #5** : Llauro-Barrès (MAIF) en fin de semaine, trigger borderline (32j) mais sujet brûlant. **Voir `outreach/drafts/2026-06-08_llauro-barres.md`.**
- **Investigation parallèle** : pourquoi le drift detector n'a pas alerté sur 35 jours de désynchro ? Et pourquoi l'Outreach Radar n'a pas tourné W19-W23 ? Bug à fixer pour ne pas reproduire.

---

## Journal hebdomadaire

### W17-W18 (2026-04-20 → 2026-05-03) — cf. v6.0 du pipeline pour le détail

22 contacts touchés sur 2 semaines. 2 réponses positives chaudes (Iteanu, Hubert). 1 réponse institutionnelle CNIL (Stefanini autoreply). 1 reclassement partner LT (Adnan/Centurian).

### W19 → W23 (2026-05-04 → 2026-06-07) — TROU MÉMOIRE

**Outreach Radar n'a pas tourné W19, W20, W21, W22, W23.** Anomalie cron persistante, jamais résolue depuis le 04/05. Aucune mise à jour pipeline pendant 5 semaines.

**Conséquence** : statut réel inconnu pour 17 conversations actives. Vraisemblances par défaut :
- 14 contacts ENVOYÉS sans retour : passage théorique en SLOT LIBÉRÉ entre 18/05 et 01/06.
- 3 conversations chaudes (Iteanu, Hubert, Stefanini) : soit converties, soit refroidies, soit perdues. **Aucun signal pipeline.**

À investiguer cette semaine : (1) état boîte mail Audric, (2) pourquoi l'Outreach Radar ne tourne plus, (3) pourquoi le drift detector n'a pas crié.

### W24 (2026-06-08 → 2026-06-14)

**Lundi 8/06** : Outreach Radar W24 relancé manuellement. 4 nouvelles cibles proposées avec trigger event vérifié :
- Arno Amabile (Observatoire IA Justice) — trigger 01/06
- Kaoutar Sghiouer (Sanofi) — trigger Fortune 27/05 + VivaTech 17-20/06
- Eric Robert (EDF) — trigger consortium AION 21/05
- Evelyne Llauro-Barrès (MAIF) — trigger accord IA 07/05 (32j, borderline transparent)

Diversification respectée : 4 secteurs (public/justice, pharma, énergie, mutuelle). Sonia Cissé (Linklaters) et Xavier Vamparys (CNP) écartés (triggers fragiles ou poste partiellement aligné).

---

## Changelog pipeline

- **2026-06-08 (v7.0)** : **SYNCHRO POST-TROU W19-W23**. Désynchro majeure documentée (5 semaines sans Radar). 14 contacts ENVOYÉS marqués SLOT LIBÉRÉ planifié, à confirmer Audric. 3 conversations chaudes (Iteanu, Hubert, Stefanini) marquées STATUT INCONNU. +4 nouvelles cibles W24 (Amabile, Sghiouer, Robert, Llauro-Barrès). Légende enrichie ("SLOT LIBÉRÉ planifié, à confirmer"). Action #1 = synchronisation pipeline avec boîte mail Audric. Auteur : Outreach Radar W24 relancé manuellement.
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL. Iteanu corrigé en Alexandra. Hubert EN COURS HUMAIN. Gauthier SLOT LIBÉRÉ anticipé. Compteur funnel actif 17 contacts. Auteur : Audric session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : +13 contacts. Funnel 8 → 21. Ajout règle synchro + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem (Remedi) + Gauthier (Chift). Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
