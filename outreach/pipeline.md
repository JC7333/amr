# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 3 conversations actives à vérifier (Alexandra Iteanu — appel devait être 5 ou 6/5, depuis silence ; Gabriel Hubert/Dust — en attente retour ; Rémi Stefanini/CNIL — fenêtre théorique close 18/05). 16 slots libérés ce jour.**

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

**ALERTE 2026-06-04** : désynchro mesurée à 730h (30 jours). Le pipeline n'a pas
été touché depuis le 04/05 v6.0. Toutes les transitions de cette PR sont
mécaniques. Audric doit re-synchroniser avec l'état réel avant d'agir.

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
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (fenêtre réponse théoriquement close)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04 ; retour effectif 04/05) | Directeur DTIA CNIL. Fenêtre réponse réaliste : 04/05 → 18/05. **2026-06-04 : 41j silence, fenêtre close depuis 17j. Vérifier fil mail audric@mandatia.eu et statuer (DÉCLINÉ silencieux ou attente longue).** Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | **SLOT LIBÉRÉ** | 2026-04-23 (email depuis audric@mandatia.eu) | CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. **Slot libéré 2026-06-04** : 42j silence post-email, 51j post-LinkedIn (les 2 canaux tentés, échéance prévue 18/05 dépassée). Remplaçant à proposer par Outreach Radar W24. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | **SLOT LIBÉRÉ anticipé** | 2026-04-14 | **Décision 04/05** : canal email Chift prévu 28/04 jamais activé (anti-dilution face à 2 conversations chaudes Iteanu + Hubert). 20j silence LinkedIn ce jour. Slot libéré explicitement plutôt que de tenter un 2e canal en retard sur prospect tiède. Cooldown 90j maintenu jusqu'au 13/07. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-04** (43j silence LinkedIn, fenêtre canal alt 06/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Email probable juliette.mattioli@thalesgroup.com (94,5%) — envisager email avant abandon définitif si cible jugée haute valeur (CAC40 souveraine). |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | **SLOT LIBÉRÉ** | 2026-04-22 | Profil fermé. **Slot libéré 2026-06-04** (43j silence, fenêtre canal alt 06/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Email probable ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%) — envisager email avant abandon si cible haute valeur. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-04** (43j silence, fenêtre canal alt 06/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Email probable aldrick.zappellini@credit-agricole.com (89%) — envisager email avant abandon si cible haute valeur (banque CAC40). |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | **SLOT LIBÉRÉ** | 2026-04-22 | **Slot libéré 2026-06-04** (43j silence, fenêtre canal alt 06/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Email probable david.rice@hsbc.com (71%, risque doublon nom) — envisager email avant abandon si cible haute valeur. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | CTO Dust. **Slot libéré 2026-06-04** (39j silence). Remplaçant à proposer par Outreach Radar W24. **NE PAS tenter email** (Hubert = canal principal Dust, déjà en EN COURS HUMAIN). |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-26 | Professeure droit IA. **Slot libéré 2026-06-04** (39j silence, fenêtre canal alt 10/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Email probable florence.gsell@sciencespo.fr — envisager avant abandon si cible haute valeur (académique gouvernance). |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | **SLOT LIBÉRÉ** | 2026-04-26 | Profil fermé, note seulement. **Slot libéré 2026-06-04** (39j silence, connexion vraisemblablement pas acceptée). Remplaçant à proposer par Outreach Radar W24. Email marcel.salathe@epfl.ch — envisager avant abandon si cible haute valeur. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | **SLOT LIBÉRÉ** | 2026-04-27 | christine.balague@imt-bs.eu (vérifié multi-source). **Slot libéré 2026-06-04** (38j silence sur le canal principal email). Remplaçant à proposer par Outreach Radar W24. Pas de canal alt prévu — email était déjà le canal principal. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate à la Cour — Numérique / Cybersécurité / Data / IA — Chargée d'enseignement Master 2 Droit des données Sorbonne — AFCDP | Email cabinet → Email perso | **EN COURS HUMAIN** | 2026-04-28 (réponse Alexandra : "le point que vous soulevez de la responsabilité et du mandat est fondamental, échangeons rapidement de vive voix") | Réponse de l'associée d'Olivier Iteanu (le mail initial avait été envoyé "À l'attention de Maître Iteanu" → transmis à Alexandra). Appel proposé 5 ou 6/5 17h30-18h30 (mail Audric 30/04). **2026-06-04 : 37j sans mise à jour du pipeline. L'appel a-t-il eu lieu ? Vérifier Gmail + agenda. Si appel tenu, mettre à jour le résultat ; sinon relancer cadrage.** Tel direct : 06.43.90.40.24. Confidentialité avocat-client envisagée pour DP. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | DG ANSSI. **Slot libéré 2026-06-04** (38j silence). Remplaçant à proposer par Outreach Radar W24. Pas de relance froide ni d'email institutionnel envisagé (PDG cible) — abandon définitif. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | **Slot libéré 2026-06-04** (38j silence). Remplaçant à proposer par Outreach Radar W24. Pas de canal alt prévu — abandon définitif. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | Profil fermé probable, note seulement. **Slot libéré 2026-06-04** (38j silence, connexion vraisemblablement pas acceptée). Remplaçant à proposer par Outreach Radar W24. NE PAS chercher email (politique/PDG, ne marchera pas) — abandon définitif. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. Cible stratégique. **Slot libéré 2026-06-04** (38j silence, fenêtre canal alt 11/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Envisager email institutionnel cigref avant abandon définitif (haute valeur stratégique). |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-06-04** (38j silence). Remplaçant à proposer par Outreach Radar W24. Pas de canal alt facile (pas d'employeur fixe) — abandon définitif. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | **SLOT LIBÉRÉ** | 2026-04-27 | Profil ouvert. **Slot libéré 2026-06-04** (38j silence, fenêtre canal alt 11/05 jamais activée). Remplaçant à proposer par Outreach Radar W24. Email probable stephane.distinguin@fabernovel.com — envisager avant abandon si cible jugée haute valeur (à valider Hunter). |
| 2026-04-27 | **Gabriel Hubert** | Dust.tt | CEO Dust | LinkedIn message direct → échanges LinkedIn | **EN COURS HUMAIN** | 2026-04-29 (Audric 2e message : question seuil clients juristes vs métier) | Hubert a répondu 28/04 sur 1er message d'Audric : "ça dépend des tâches/de l'impact". Audric a contre-questionné 29/04 sur où il voit le seuil entre clients juristes vs métier dans l'usage agent. **2026-06-04 : 36j sans mise à jour du pipeline. Vérifier fil LinkedIn — Hubert a-t-il répondu ? Si oui, mettre à jour. Si pas de retour à 36j sur conversation tiède chaude, considérer la conversation comme abandonnée naturellement (pas de relance, on respecte le silence).** Cooldown 90j maintenu. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | **SLOT LIBÉRÉ** | 2026-04-27 | PDG institution publique. Note seulement. **Slot libéré 2026-06-04** (38j silence, connexion vraisemblablement pas acceptée). Remplaçant à proposer par Outreach Radar W24. Email pattern probable bruno.sportisse@inria.fr mais filtré par secrétariat — pas de canal alt envisagé, abandon définitif. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- **Conversations actives à vérifier** : 3 (Alexandra Iteanu — appel théorique 5 ou 6/5 sans mise à jour depuis 37j ; Gabriel Hubert — 36j sans mise à jour ; Rémi Stefanini — 41j silence depuis email institutionnel, fenêtre close depuis 17j)
- **Reclassement partner LT** : 1 (Adnan Khan / Centurian)
- Messages ENVOYÉS sans retour : **0** (tous passés en SLOT LIBÉRÉ à 35j)
- SLOT LIBÉRÉ ce jour : **16** (Erdem, Mattioli, Rogers, Zappellini, Rice, Polu, G'sell, Salathé, Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse)
- SLOT LIBÉRÉ anticipé antérieur : 1 (Gauthier Henroz / Chift)

**FUNNEL RÉEL au 2026-06-04** : 3 contacts en suivi actif EN COURS HUMAIN (Iteanu, Hubert, Stefanini — tous 3 stagnants, état réel à vérifier hors Claude). 16 slots à repourvoir par Outreach Radar W24. STOP nouveaux contacts levé : capacité pleine pour repeupler le funnel — Outreach Radar W24 prioritaire.

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
| **2026-06-04 (aujourd'hui)** | Reply Tracker post-désynchro 30j. 16 SLOT LIBÉRÉ appliqués mécaniquement. Audric doit re-synchroniser avant action. |
| 2026-06-04 → 2026-06-08 | Vérification statut réel Iteanu, Hubert, Stefanini (appel tenu ? réponses reçues hors Claude ?). |
| 2026-06-09 (W24) | Outreach Radar W24 : proposer 16 nouveaux contacts pour repourvoir le funnel. |

---

## Actions Audric cette semaine (S23)

- **Priorité #1** : SYNCHRONISER pipeline.md avec l'état réel des échanges (Gmail audric@mandatia.eu, LinkedIn, agenda). 30 jours sans mise à jour du pipeline = 100% des alertes de cette PR sont basées sur des données stale. Faire le tour des 3 EN COURS HUMAIN + vérifier qu'aucune réponse n'a été ratée parmi les 16 SLOT LIBÉRÉ.
- **Priorité #2** : statuer sur Iteanu Alexandra (l'appel calé 5 ou 6/5 a-t-il eu lieu ? résultat ?). C'était la conversation la plus chaude.
- **Priorité #3** : statuer sur Hubert Gabriel (réponse reçue depuis 29/04 ?) et Stefanini (réponse depuis 04/05 ?).
- **Priorité #4** : déclencher Outreach Radar W24 une fois le pipeline ré-aligné — 16 slots à repourvoir.

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

### W19 → W23 (2026-05-04 → 2026-06-04) — TROU DE SYNCHRO

**Aucune mise à jour du pipeline pendant 30 jours.** Le Reply Tracker du 2026-06-04
applique mécaniquement les transitions à 35j sur les données du 04/05. État réel
à reconstituer hors Claude (Gmail audric@mandatia.eu + LinkedIn + agenda).

### W23 (2026-06-01 → 2026-06-07)

**Jeudi 4/06** :
- Reply Tracker v6.1 (cette PR) : 16 SLOT LIBÉRÉ + 3 alertes EN COURS HUMAIN.
- Désynchro mesurée : 730h (30 jours).

---

## Changelog pipeline

- **2026-06-04 (v6.1)** : Reply Tracker post-désynchro 30j. **16 SLOT LIBÉRÉ** appliqués mécaniquement à 35j+ silence : Erdem (CANAL ALT TENTÉ → SLOT LIBÉRÉ, 42j post-email), Mattioli, Rogers, Zappellini, Rice (43j), Polu, G'sell, Salathé (39j), Balagué, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Sportisse (38j). 3 alertes EN COURS HUMAIN stagnant (Stefanini 41j, Iteanu 37j, Hubert 36j) — pipeline NON modifié sur ces 3, action humaine requise. Funnel actif passé de 17 à 3 contacts (tous EN COURS HUMAIN à vérifier). Auteur : Claude Reply Tracker (automatique).
- **2026-05-04 (v6.0)** : SYNCHRO POST-S18. Adnan SORTI FUNNEL (Centurian.ai, reclassé partner LT). Iteanu : nom corrigé en Alexandra Iteanu (associée, pas Olivier), passage EN COURS HUMAIN, appel calé 5 ou 6/5. Hubert : passage EN COURS HUMAIN (échanges en cours). Gauthier : SLOT LIBÉRÉ anticipé (canal email jamais activé, anti-dilution). Compteur funnel actif passé de 21 à 17 contacts en suivi. Auteur : Audric via session Claude Opus du 4/05 matin.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 intégrés. Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn.
- **2026-04-21 → 22** : création initiale via PR #2.
