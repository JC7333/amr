# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 4 conversations actives (Alexandra Iteanu — appel calé 5 ou 6/5 ; Gabriel Hubert/Dust — échange en cours ; Rémi Stefanini/CNIL — fenêtre réponse ouverte ; Adnan Khan/Equinix — reclassé partner LT)**.

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (fenêtre réponse ouverte)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; **retour effectif 04/05**) | Directeur DTIA CNIL. Fenêtre réponse réaliste : 04/05 → 18/05. **⚠️ Reply Tracker 28/05 : fenêtre fermée depuis 10j, aucune MAJ visible (dernier échange 24/04 = 34j). Vérifier fil Gmail/LinkedIn.** Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | **SLOT LIBÉRÉ** | 2026-04-23 (email depuis audric@mandatia.eu) | **Slot libéré 2026-05-28**, remplaçant à proposer par Outreach Radar W23. Silence total sur 2 canaux (LinkedIn 14/04 + email 23/04), seuil 18/05 noté dépassé. CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. Cooldown 90j jusqu'au 22/07 maintenu. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-05-28**, remplaçant à proposer par Outreach Radar W23. 36j silence LinkedIn, canal email jamais activé. **Envisager email avant abandon définitif si cible à haute valeur** : juliette.mattioli@thalesgroup.com (94,5%), valider Hunter avant envoi. Cooldown 90j jusqu'au 21/07. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-05-28**, remplaçant à proposer par Outreach Radar W23. Profil fermé, 36j silence LinkedIn, canal email jamais activé. **Envisager email avant abandon définitif si cible à haute valeur** : ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%), valider Hunter. Cooldown 90j jusqu'au 21/07. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-05-28**, remplaçant à proposer par Outreach Radar W23. 36j silence LinkedIn, canal email jamais activé. **Envisager email avant abandon définitif si cible à haute valeur** : aldrick.zappellini@credit-agricole.com (89%), valider Hunter. Cooldown 90j jusqu'au 21/07. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-05-28**, remplaçant à proposer par Outreach Radar W23. 36j silence LinkedIn, canal email jamais activé. **Envisager email avant abandon définitif si cible à haute valeur** : david.rice@hsbc.com (71%, risque doublon nom), valider Hunter. Cooldown 90j jusqu'au 21/07. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | ENVOYÉ | 2026-04-26 | CTO Dust. 32j silence. **Note** : Hubert (CEO Dust) a répondu, donc équipe Dust a vu AMR — Polu probablement au courant. NE PAS tenter email Polu (Hubert canal principal Dust). SLOT LIBÉRÉ 31/05. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | ENVOYÉ | 2026-04-26 | Professeure droit IA. 32j silence. Fenêtre canal alt dépassée. Email probable florence.gsell@sciencespo.fr. SLOT LIBÉRÉ 31/05. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | ENVOYÉ | 2026-04-26 | Profil fermé, note seulement. Attente acceptation connexion. Si pas accepté : tenter email marcel.salathe@epfl.ch. SLOT LIBÉRÉ 31/05. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | ENVOYÉ | 2026-04-27 | christine.balague@imt-bs.eu (vérifié multi-source). 31j silence. Pas de canal alt prévu (email = canal principal). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN** | 2026-04-28 (réponse Alexandra : "le point que vous soulevez de la responsabilité et du mandat est fondamental, échangeons rapidement de vive voix") | Réponse de l'associée d'Olivier Iteanu (le mail initial avait été envoyé "À l'attention de Maître Iteanu" → transmis à Alexandra). **APPEL CADRÉ** : créneaux proposés 5 ou 6/5 17h30-18h30 (mail Audric 30/04). **⚠️ Reply Tracker 28/05 : aucune MAJ visible depuis 28/04 (30j). L'appel a-t-il eu lieu ? Vérifier issue de l'appel et fil mail.** Tel direct fourni : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | ENVOYÉ | 2026-04-27 | DG ANSSI. 31j silence. Pas de relance froide ni d'email institutionnel envisagé (PDG cible). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | ENVOYÉ | 2026-04-27 | 31j silence. Pas de canal alt prévu. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | ENVOYÉ | 2026-04-27 | Profil fermé probable, note seulement. Attente acceptation. NE PAS chercher email (politique/PDG, ne marchera pas). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. Cible stratégique. 31j silence. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. 31j silence. Pas de canal alt facile (pas d'employeur fixe). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. 31j silence. Email probable stephane.distinguin@fabernovel.com à valider Hunter. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | Hubert a répondu 28/04 sur 1er message d'Audric : "ça dépend des tâches/de l'impact". Audric a contre-questionné 29/04 sur où il voit le seuil entre clients juristes vs métier dans l'usage agent. **⚠️ Reply Tracker 28/05 : aucune MAJ visible depuis 29/04 (29j). Conversation chaude au point mort, vérifier fil LinkedIn.** Cooldown 90j maintenu. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | ENVOYÉ | 2026-04-27 | PDG institution publique. Note seulement. Email pattern probable bruno.sportisse@inria.fr mais filtré par secrétariat. Pas de canal alt envisagé. SLOT LIBÉRÉ 01/06. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations actives (EN COURS HUMAIN)** : **3** (Alexandra Iteanu, Gabriel Hubert, Rémi Stefanini) — ⚠️ toutes ≥29j sans MAJ visible au 28/05, voir alertes Reply Tracker
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- Messages ENVOYÉS sans retour : 11 (en attente naturelle, pas de relance froide)
- SLOT LIBÉRÉ : 6 (Gauthier Henroz/Chift ; Erdem Yağan/Remedi ; Juliette Mattioli/Thales ; Ian Rogers/Ledger ; Aldrick Zappellini/Crédit Agricole ; David Rice/HSBC)

**FUNNEL RÉEL** : 14 contacts en suivi actif (11 ENVOYÉ en attente + 3 EN COURS HUMAIN). 5 slots libérés au 28/05 (Erdem + 4 banque/défense du 22/04). Recompte aligné sur les statuts réels du tableau (l'ancien total 17 comptait encore Erdem + les 4 du 22/04). ⚠️ Plafond "STOP nouveaux contacts jusqu'au 18/05" expiré, MAIS pipeline désynchronisé depuis le 04/05 (562h) : synchroniser l'état réel des envois avant toute décision d'outreach.

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
| 2026-05-05 ou 06 17h30-18h30 | **APPEL ALEXANDRA ITEANU** (créneau ferme à confirmer par mail Audric 30/04). ⚠️ Issue inconnue au 28/05 — à vérifier. |
| 2026-05-04 → 2026-05-18 | Fenêtre normale réponse Stefanini (fermée, sans retour visible). |
| 2026-05-18 | Erdem atteint 35j silence → SLOT LIBÉRÉ (réalisé 28/05). |
| 2026-05-27 | Mattioli, Rogers, Zappellini, Rice atteignent 35j silence → SLOT LIBÉRÉ (réalisé 28/05). |
| 2026-05-31 | Polu, G'sell, Salathé atteignent 35j → SLOT LIBÉRÉ. |
| 2026-06-01 | 8 contacts du 27/04 (Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse) atteignent 35j → SLOT LIBÉRÉ massif. |

---

## Actions Audric cette semaine (S22)

- **Priorité #1** : **SYNCHRONISER pipeline.md avec l'état réel des envois** (désynchro 562h depuis le 04/05). Toutes les alertes ci-dessous peuvent être stale.
- **Priorité #2** : triager les 3 conversations EN COURS HUMAIN au point mort — confirmer l'issue de l'appel Iteanu (5-6/5), l'état du fil Hubert et la fenêtre Stefanini (fermée 18/05). Ces 3 "chaudes" sont silencieuses depuis 29-34j.
- **Priorité #3** : 5 slots libérés ce jour → Outreach Radar W23 proposera des remplaçants. Pour Mattioli/Rogers/Zappellini/Rice (haute valeur, email jamais tenté), arbitrer email unique avant abandon définitif.
- **Priorité #4** : pas de relance froide. Plafond 18/05 expiré mais ne rien envoyer avant resynchro.

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
- Sync pipeline.md v6.0 (cette PR).
- Stefanini retour effectif de congés (fenêtre réponse ouverte).

**Reply Tracker W18-S19** : a tourné chaque matin (PR #20 du 29/04 → #26 du 04/05). Couche 3 anti-dérive (avertissement désynchro >48h) opérationnelle depuis le 30/04 — visible en tête de chaque PR.

**Outreach Radar W18** : N'A PAS TOURNÉ. Anomalie cron persistante. À investiguer S20 si capacité dispo (non bloquant : aucun nouveau contact souhaité avant 18/05).

**Drift detector v2** : déployé 29/04. Aucune issue créée à ce jour malgré 6 PR Reply Tracker open ; bug de robustesse à investiguer mais non bloquant (la couche 3 prompt Reply Tracker fait le job en parallèle).

### W19→W22 (2026-05-04 → 2026-05-28)

**⚠️ DÉSYNCHRO PIPELINE** : aucune mise à jour de pipeline.md entre le 04/05 et le 28/05 (562h). Reply Tracker non synchronisé sur l'état réel des envois pendant ~23j.

**Reply Tracker 28/05 (v6.1)** : reprise. Application automatique de 5 SLOT LIBÉRÉ atteignant 35j+ (Erdem, Mattioli, Rogers, Zappellini, Rice). 3 alertes EN COURS HUMAIN stagnantes (Iteanu, Hubert, Stefanini). Aucun nouvel envoi visible côté pipeline depuis le 04/05 — à resynchroniser d'urgence.

---

## Changelog pipeline

- **2026-05-28 (v6.1)** : Reply Tracker auto-run après 562h de désynchro. 5 SLOT LIBÉRÉ à 35j+ : Erdem Yağan (silence 2 canaux, seuil 18/05 dépassé), Juliette Mattioli, Ian Rogers, Aldrick Zappellini, David Rice (36j silence LinkedIn, canal email jamais activé → note "envisager email avant abandon"). 3 alertes EN COURS HUMAIN stagnantes (Iteanu 30j, Hubert 29j, Stefanini 34j). Compteur funnel actif recompté 17→14. ⚠️ Alertes possiblement basées sur données stale (pipeline non synchronisé depuis le 04/05). Auteur : Reply Tracker (Claude Code).
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
