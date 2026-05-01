# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés, 2 conversations en cours (Adnan Khan + Rémi Stefanini CNIL), 18 messages en attente + 1 canal alt tenté (Erdem)**.

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

---

## Pipeline

| Date contact | Prénom Nom | Entreprise | Secteur | Canal utilisé | Statut | Dernier échange | Notes |
|---|---|---|---|---|---|---|---|
| 2026-04-15 | Adnan Khan | Equinix | Infra / Datacenter | LinkedIn | EN COURS HUMAIN | 2026-04-27 (Audric continuité post-pivot) | Candidat #1 Design Partner. Pivot enforcement mergé 23/04. Continuité post-pivot envoyée 27/04. Attente nouvelle réponse. |
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn 22/04 → Email institutionnel 24/04 | **EN COURS HUMAIN (attente retour congés)** | 2026-04-24 (email envoyé, autoreply reçu : absent jusqu'au 30/04) | Directeur DTIA CNIL. Autoreply : retour 04/05. Backups Toubiana / Della-Valle nommés mais NE PAS contacter. Fenêtre réponse réaliste : 04/05 → 18/05. Confidentialité absolue. |
| 2026-04-14 | Erdem Yağan | Remedi Finance | Fintech healthcare BNPL (UK/TR) | LinkedIn (EN) puis email 23/04 | CANAL ALT TENTÉ | 2026-04-23 (email depuis audric@mandatia.eu) | CEO Remedi = BNPL cliniques + e-KYC + credit scoring = AI Act Annex III pt 5. Email public vérifié erdem@remedifinance.com. Si silence total 18/05 : SLOT LIBÉRÉ. |
| 2026-04-14 | Gauthier Henroz | Chift | API finance pour agents IA (Belgique) | LinkedIn direct (FR) | ENVOYÉ | 2026-04-14 | 13j silence aujourd'hui. Canal email Chift à activer **demain 28/04** (gauthier.henroz@chift.eu, 61,8% Hunter à valider). Si silence total 18/05 : SLOT LIBÉRÉ. |
| 2026-04-22 | Juliette Mattioli | Thales | Défense / tech souveraine (CAC40) | LinkedIn direct | ENVOYÉ | 2026-04-22 | Attente 14j. Email probable si silence 06/05 : juliette.mattioli@thalesgroup.com (94,5%). Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-22 | Ian Rogers | Ledger | Fintech sécurité hardware | LinkedIn note connexion 193c | ENVOYÉ | 2026-04-22 | Profil fermé. Attente 14j. Email probable : ian.rogers@ledger.com (72,9%) ou @ledger.fr (51,2%). Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-22 | Aldrick Zappellini | Groupe Crédit Agricole | Banque mutualiste | LinkedIn InMail | ENVOYÉ | 2026-04-22 | Attente 14j. Email probable si silence 06/05 : aldrick.zappellini@credit-agricole.com (89%). Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-22 | David Rice | HSBC | Banque universelle (UK) | LinkedIn InMail | ENVOYÉ | 2026-04-22 | Attente 14j. Email probable : david.rice@hsbc.com (71%). Risque doublon nom. Valider Hunter. SLOT LIBÉRÉ 27/05. |
| 2026-04-26 | Stanislas Polu | Dust.tt | Plateforme agents B2B (FR) | LinkedIn message direct | ENVOYÉ | 2026-04-26 | CTO Dust. Attente 14j. Si silence 10/05 : canal email possible (probable stanislas@dust.tt). SLOT LIBÉRÉ 31/05. |
| 2026-04-26 | Florence G'sell | Sciences Po | Académique gouvernance IA | LinkedIn message direct | ENVOYÉ | 2026-04-26 | Professeure droit IA. Attente 14j. Email probable florence.gsell@sciencespo.fr. SLOT LIBÉRÉ 31/05. |
| 2026-04-26 | Marcel Salathé | EPFL | Académique IA Suisse | LinkedIn note connexion 200c | ENVOYÉ | 2026-04-26 | Profil fermé, note seulement. Attente acceptation connexion. Si pas accepté à J+14 : tenter email marcel.salathe@epfl.ch. SLOT LIBÉRÉ 31/05. |
| 2026-04-27 | Christine Balagué | IMT-BS | Académique chaire Good in Tech | Email institutionnel | ENVOYÉ | 2026-04-27 | christine.balague@imt-bs.eu (vérifié multi-source). Attente 14j. Si silence 11/05 : pas de relance. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Olivier Iteanu | Iteanu Avocats | Avocat IT / numérique | Email cabinet | ENVOYÉ | 2026-04-27 | contact@iteanu.law (vérifié site officiel). Sujet précisé "À l'attention de Maître Iteanu" pour transmission directe. Attente 14j. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Vincent Strubel | ANSSI | Régulateur cybersécurité | LinkedIn message direct | ENVOYÉ | 2026-04-27 | DG ANSSI. Profil ouvert au moment de l'envoi (vérifié bouton Message). Attente 14j. Pas de relance froide ni d'email institutionnel envisagé (PDG cible). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Anne Bouverot | AI Action Summit France | Gouvernance IA | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert au moment de l'envoi. Attente 14j. Pas de canal alt prévu. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Cédric O | Ex-Sec d'État Numérique / board Mistral | Souveraineté IA / politique | LinkedIn note connexion | ENVOYÉ | 2026-04-27 | Profil fermé probable, note seulement. Attente acceptation. Si pas accepté à J+14 : NE PAS chercher email (politique/PDG, ne marchera pas). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Henri d'Agrain | Cigref | Délégué général Cigref (DSI 150 grandes entreprises FR) | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. Cible stratégique : Cigref = premier prescripteur IA chez DSI grands comptes FR. Si silence 11/05 : tenter email institutionnel cigref. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Tariq Krim | Indépendant souveraineté num. | Influenceur / commentateur | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. Attente 14j. Si silence 11/05 : pas de canal alt facile (pas d'employeur fixe). SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Stéphane Distinguin | Fabernovel / French Tech | Conseil + écosystème AI Action Summit | LinkedIn message direct | ENVOYÉ | 2026-04-27 | Profil ouvert. Attente 14j. Si silence 11/05 : email probable stephane.distinguin@fabernovel.com à valider Hunter. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Gabriel Hubert | Dust.tt | CEO Dust (cofondateur de Polu) | LinkedIn message direct | ENVOYÉ | 2026-04-27 | **Note** : Polu (CTO) déjà contacté 26/04. Envoi Hubert le lendemain = signal "envoi en masse Dust" possible. Risque que Hubert et Polu se concertent et trouvent l'approche peu sincère. À surveiller dans les réponses. SLOT LIBÉRÉ 01/06. |
| 2026-04-27 | Bruno Sportisse | Inria | PDG Inria (3000 personnes) | LinkedIn note connexion | ENVOYÉ | 2026-04-27 | PDG institution publique. Note seulement. Email pattern probable bruno.sportisse@inria.fr mais filtré par secrétariat. Pas de canal alt envisagé. SLOT LIBÉRÉ 01/06. |
| 2026-04-21 (proposé W17) | Pierre Houlès | Kering | Luxe (CAC40) | — | SKIP | — | Trigger 35j hors fenêtre. Audric a arbitré NON. |

---

## Compteur Design Partners

- Signés: **0 / 5**
- Conversations en cours : **2** (Adnan Khan + Rémi Stefanini CNIL)
- Messages ENVOYÉS en attente : **18**
- Canal alt email tenté : 1 (Erdem)

**ALERTE FUNNEL** : 21 contacts actifs = dépassement plafond viable (15). Capacité de cadrage simultané risquée si plus de 5 réponses positives arrivent la semaine du 5/05. Aucun nouveau contact ne doit être ajouté avant **18/05** ou avant que des slots se libèrent par silence à J+35.

---

## Contacts déjà sollicités (cooldown 90j)

- Equinix (Adnan, 2026-04-15) — cooldown 2026-07-14
- CNIL (Stefanini, 2026-04-22 LinkedIn + 2026-04-24 email) — cooldown 2026-07-23
- Remedi Finance (Erdem, 2026-04-14 LinkedIn + 2026-04-23 email) — cooldown 2026-07-22
- Chift (Gauthier, 2026-04-14) — cooldown 2026-07-13
- Thales (Mattioli, 2026-04-22) — cooldown 2026-07-21
- Ledger (Rogers, 2026-04-22) — cooldown 2026-07-21
- Crédit Agricole (Zappellini, 2026-04-22) — cooldown 2026-07-21
- HSBC (Rice, 2026-04-22) — cooldown 2026-07-21
- Dust.tt (Polu 26/04 + Hubert 27/04) — cooldown 2026-07-25 et 2026-07-26
- Sciences Po (G'sell, 2026-04-26) — cooldown 2026-07-25
- EPFL (Salathé, 2026-04-26) — cooldown 2026-07-25
- IMT-BS (Balagué, 2026-04-27) — cooldown 2026-07-26
- Iteanu Avocats (Iteanu, 2026-04-27) — cooldown 2026-07-26
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
| 2026-04-28 (demain) | Gauthier Henroz atteint 14j silence LinkedIn → canal email Chift possible (gauthier.henroz@chift.eu à valider Hunter) |
| 2026-05-04 | Retour effectif Stefanini (lundi après congés) |
| 2026-05-06 | Mattioli, Rogers, Zappellini, Rice atteignent 14j silence → canal email possible |
| 2026-05-04 → 2026-05-18 | Fenêtre normale réponse Stefanini (2 semaines post-retour) |
| 2026-05-10 | Polu, G'sell, Salathé atteignent 14j silence → canal email possible (Salathé : tenter email seulement si connexion non acceptée) |
| 2026-05-11 | Balagué, Iteanu, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Hubert, Sportisse atteignent 14j silence → canal email possible UNIQUEMENT pour ceux dont le canal alt est faisable et pertinent (pas Sportisse, pas Cédric, pas Strubel) |
| 2026-05-18 | Erdem + Gauthier atteignent 35j silence → SLOT LIBÉRÉ si pas de réponse |
| 2026-05-27 | Mattioli, Rogers, Zappellini, Rice atteignent 35j silence → SLOT LIBÉRÉ |
| 2026-05-31 | Polu, G'sell, Salathé atteignent 35j → SLOT LIBÉRÉ |
| 2026-06-01 | 10 contacts du 27/04 atteignent 35j → SLOT LIBÉRÉ massif (vague de remplacement à anticiper) |

---

## Actions Audric cette semaine

- **Priorité #1** : surveiller Gmail audric@mandatia.eu et LinkedIn pour réponses — Adnan post-pivot, Stefanini (4-5/05), Erdem, et tous les nouveaux.
- **Priorité #2** : envoi email Chift à Gauthier Henroz **demain 28/04** si silence LinkedIn confirmé.
- **Priorité #3** : **NE PAS envoyer de nouveau message d'outreach avant 18/05** (capacité de cadrage saturée).

---

## Journal hebdomadaire

### W17 (2026-04-20 → 2026-04-26)

**Outreach Radar lundi 21/04** : 1 cible DP fraîche (Mattioli) + 1 borderline skippée (Houlès) + 1 régulateur stratégique (Stefanini).

**Complément Outreach Radar mercredi 22/04** : 3 cibles supplémentaires fintech/banque (Rogers, Zappellini, Rice).

**Ajouts rétroactifs 23/04** : Erdem Yağan (Remedi Finance, CEO) + Gauthier Henroz (Chift, CEO) — tous deux envoyés 14/04 hors pipeline initial.

**Canal email activé 23/04** : Erdem Yağan via audric@mandatia.eu.

**RÉPONSE INSTITUTIONNELLE 24/04** : Rémi Stefanini (CNIL DTIA) répond sur LinkedIn à 08:39, demande de bascule sur email. Email envoyé 24/04, autoreply reçu (retour 04/05).

**Wave 1 dimanche 26/04** : ajout 3 cibles (Polu/Dust, G'sell/SciencesPo, Salathé/EPFL) hors radar habituel, à l'initiative d'Audric.

**Volume W17 effectif** : 11 cibles contactées (8 LinkedIn + 1 canal alt email Erdem + 1 canal officiel CNIL Stefanini + 1 réponse positive Stefanini).

### W18 (2026-04-27 → 2026-05-03)

**Lundi 27/04 — vague massive d'outreach** : 11 envois dans la journée, hors cadre Outreach Radar. Audric a explicitement validé "qui ne tente rien n'a rien" malgré recommandation Claude d'étalement (2 envois ce soir + 4 le 5/05). Décision actée et tracée.

- Wave 2 (matin) : Balagué/IMT-BS (email), Iteanu/cabinet (email), Strubel/ANSSI (LinkedIn), Bouverot/AISummit (LinkedIn).
- Wave 3 (soir) : Cédric O (note), d'Agrain/Cigref, Krim, Distinguin/Fabernovel, Hubert/Dust, Sportisse/Inria (note).

**Volume W18 jour 1** : 11 ENVOYÉ + 1 EN COURS HUMAIN relancé (Adnan continuité post-pivot).

**Outreach Radar W18** : **N'A PAS TOURNÉ ce matin** (anomalie cron à investiguer dans repo amr).

**Reply Tracker W18** : tourné chaque matin (PR #15 du 27/04). Mais alertes basées sur pipeline.md gelé au 24/04 → désynchro corrigée par mise à jour v5.0.

**Tracker run 2026-05-01** : 0 slot libéré, 1 canal alt signalé (Chift/Henroz, silence LinkedIn 17j), 1 alerte EN COURS HUMAIN (Adnan Khan, 4j sans MAJ post-pivot). Stefanini exclu (autoreply documenté retour 04/05). Aucun changement de statut appliqué. Désynchro pipeline >48h détectée (dernier commit 27/04 20:37 UTC).

---

## Changelog pipeline

- **2026-05-01 (Tracker run quotidien)** : note de run — 0 slot libéré, 1 canal alt signalé (Chift/Henroz silence LinkedIn 17j), 1 alerte EN COURS HUMAIN (Adnan 4j sans MAJ post-pivot). Pas de changement de statut appliqué. Avertissement désynchro pipeline (>48h sans commit) émis.
- **2026-04-27 soir (v5.0)** : SYNCHRO MAJEURE. +13 contacts envoyés depuis le 26/04 (Polu, G'sell, Salathé, Balagué, Iteanu, Strubel, Bouverot, Cédric O, d'Agrain, Krim, Distinguin, Hubert, Sportisse) intégrés. Adnan passé à dernier échange = 27/04 (continuité post-pivot envoyée). Funnel passe de 8 à 21 contacts actifs. Ajout règle synchro pipeline + workflow drift detector. Auteur : Audric via session Claude Opus du 27/04 19h45.
- **2026-04-24 soir (v4.1)** : autoreply Stefanini reçu (congés jusqu'au 30/04, retour 04/05). Backups Toubiana/Della-Valle notés mais NE PAS solliciter.
- **2026-04-24 matin (v4)** : réponse Stefanini LinkedIn 08:39 → bascule email institutionnel.
- **2026-04-23 21h (v3)** : identification Erdem = Remedi Finance + Gauthier = Chift. Email pro audric@mandatia.eu activé.
- **2026-04-23 14h (v2)** : application règle fondatrice "pas de relance froide".
- **2026-04-23 13h30** : sync post-capture LinkedIn. Passage ENVOYÉ des 5 contacts W17.
- **2026-04-21 → 22** : création initiale via PR #2 `claude/outreach-W17`, 6 drafts rédigés.
