# AMR Outreach Pipeline — Design Partners

Objectif: 5 Design Partners signés. Statut actuel: **0/5 signés. Pipeline stale 61 jours (dernier resync 15/07). État réel à reconfirmer par Audric — cf. bloc de resync W38 ci-dessous avant tout nouveau geste.**

---

## ⚠️ RESYNC W38 EN ATTENTE (radar 2026-09-14)

**Le pipeline actif ci-dessous reflète l'état au 15/07/2026. Nous sommes le 14/09/2026, soit +61 jours. Aucun événement d'envoi/réponse n'a été committé au repo entre les deux dates.** Le Reply Tracker a tourné toute la période (voir branches `claude/reply-tracker-2026-*`) mais n'a pas ré-écrit ce fichier.

Avant tout nouveau geste, Audric doit reconfirmer :

| Ligne | Question posée | Conséquence pipeline si silence côté cible |
|---|---|---|
| Gesnouin (envoyé 15/07) | Réponse arrivée ? Sinon, silence à 61 jours — la note pipeline autorise le temps long institutionnel (2-3 mois), donc **pas SLOT LIBÉRÉ automatique**, mais on approche du plafond raisonnable. | Marquer `EN COURS HUMAIN` si réponse ; sinon garder `ENVOYÉ (silence institutionnel)` jusqu'à 90j. |
| Iteanu (draft reprise prêt) | L'email reprise a-t-il été envoyé ? Si oui, quand ? Si non, la fenêtre de « fraîcheur » de l'appel de mai s'est refermée. | Si non envoyé, la reprise n'a plus la légitimité orale : requalifier `SORTI FUNNEL` ou reformuler entièrement. |
| Hubert (Dust) | Nouvelle activité de son côté ? | Reste `EN COURS HUMAIN (dormant, optionnel)` par défaut. Pas d'action forcée. |
| Boutemadja / Klaimee (planifié 20/07) | Envoyé ? Réponse ? | Si envoyé + silence : +56j > 35j = **SLOT LIBÉRÉ**. Si jamais envoyé : requalifier — le trigger « marché assurance mûri » a lui-même vieilli. |
| Hadj / Doctolib (planifié 16-17/07) | Envoyé LinkedIn ? Canal alt email `contact.dataprivacy@doctolib.com` tenté au 31/07 ? Réponse ? | Silence complet + tentative canal alt épuisée = **SLOT LIBÉRÉ**. La controverse Doctolib × IA de juillet a par ailleurs suffisamment évolué pour requalifier tout nouveau contact autour d'un trigger différent (opt-out effectif depuis 01/08, communication publique du groupe). |
| MACSF (courrier sociétaire planifié semaine 20/07) | Courrier envoyé ? Réponse ? | Courrier papier tolère 8 semaines. Passé 60j sans retour, canal alt = ligne sociétariat MACSF (courrier de relance = OK dans une relation contractuelle sociétaire, ce n'est PAS du cold outreach, exception règle fondatrice). |
| Stefanini (REPORTÉ) | Signal entrant CNIL DTIA sur agents IA depuis 15/07 ? | Pas d'action tant que pas de consultation publique CNIL agents. |

**Radar W38 ne propose PAS de traiter ces lignes lui-même** — le pipeline reste single-source-of-truth d'Audric. Les 2 nouvelles cibles ci-dessous (Caillat AXA, Ouhdi avocat) sont livrées en drafts sans effet sur les lignes existantes.

---

Fondateur: Audric Bugnard (Aix-les-Bains, FR). Produit: mandatia.eu.

**Email pro actif** : audric@mandatia.eu (Zimbra Starter OVH, SPF + DKIM + DMARC configurés, mail-tester.com score 10/10 le 23/04).

**Recentrage funnel (décision 04/07/2026, decision log)** : voie C-RAMPE, angles SANTÉ + ASSURANCE. Cibles prioritaires : avocats / DPO santé / assureurs / institutions santé numérique. Les ExCom CAC40 généralistes et académiques sortent de la cible court terme (taux de réponse avril : 2/21 — les réponses viennent du juridique, des fondateurs de plateformes et, tardivement, des institutions).

---

## RÈGLE FONDATRICE — pas de relance froide

**On ne relance JAMAIS un contact qui n'a pas répondu à un premier message.**
Insister sur contact froid = spam = tue la cible + entache réputation mandatia.

**Exception unique** : conversation orale ou RDV déjà démarrés puis tus.

**Conséquence opérationnelle** :
- Silence LinkedIn à 14j : canal email alternatif possible UNE fois (pas relance, autre porte)
- Silence total à 35j : `SLOT LIBÉRÉ`, abandon
- Cooldown 90j écoulé + contexte objectivement nouveau : nouveau premier contact possible, à condition d'apporter une valeur nouvelle (jamais un "je reviens vers vous")

---

## RÈGLE SYNCHRO PIPELINE (ajoutée 27/04/2026, violée 04/05→15/07 — post-mortem en changelog)

**Le pipeline.md doit être synchronisé avec l'état réel des envois sous 24h.**
Toute désynchro >48h fait dériver le Reply Tracker (alertes basées sur données stale).

---

## Légende statut

- `ENVOYÉ` — message envoyé, date dans colonne Dernier échange
- `PROPOSÉ` — draft prêt, envoi planifié, pas encore parti
- `CANAL ALT TENTÉ` — 2e canal tenté après silence LinkedIn 14j (une seule fois)
- `SLOT LIBÉRÉ` — silence total >35j, abandon
- `EN COURS HUMAIN` — réponse reçue, Audric gère à la main
- `REPORTÉ` — cible valide, timing pas optimal
- `SORTI FUNNEL` — reclassé hors cible DP avec note explicative

---

## Pipeline actif (cibles vivantes uniquement)

| Date contact | Prénom Nom | Entreprise | Secteur | Canal | Statut | Dernier échange | Notes |
|---|---|---|---|---|---|---|---|
| 2026-07-15 | **Philippe Gesnouin** | Inria | Directeur programme Santé numérique, co-pilote PEPR Santé numérique (France 2030), cofondateur Health Data Hub | Email audric@mandatia.eu, cc Bruno Sportisse | **ENVOYÉ (warm intro)** | 2026-07-15 (email envoyé, version ultra-courte validée) | Intro via réponse Sportisse. Angle SANTÉ pur (mandat des agents dans les parcours de soin). Pas de relance si silence — Sportisse en cc, toute insistance se verrait. Cible réputation/réseau institutionnel, pas DP commercial. |
| 2026-04-27 | **Bruno Sportisse** | Inria | PDG | LinkedIn note connexion | **EN COURS HUMAIN — REDIRECTION** | Réponse constatée 2026-07-15 (oriente vers Gesnouin, demande cc) | Réponse ~2,5 mois après l'envoi. Preuve que la purge mécanique 35j peut se tromper sur les institutions publiques (temps long). Rien à faire de plus : le cc sur l'email Gesnouin clôt la boucle. |
| 2026-04-27 | **Alexandra Iteanu** | Iteanu Avocats | Avocate numérique/IA, Sorbonne, AFCDP | Email | **EN COURS HUMAIN (dormant)** | Appel tenu début mai (qualifié) | **Exception relance orale active** (règle fondatrice). Draft reprise prêt (outreach/drafts/, 04/07) : proposition de texte de référence mandat/responsabilité co-signé — c'est ça qui convertit en DP. Condition avant envoi : Audric reconfirme le contenu exact de l'appel de mai. |
| 2026-04-27 | Gabriel Hubert | Dust.tt | CEO | LinkedIn | **EN COURS HUMAIN (dormant, optionnel)** | 2026-04-29 (2e message Audric, question seuil juristes/métier, sans retour) | Dialogue ouvert donc réponse possible sans violer la règle. Optionnel, ne pas forcer. Draft prêt (04/07). |
| 2026-04-13 | Ines Boutemadja | Klaimee (YC) | Assurance d'agents IA | LinkedIn (13/04, silence) | **PROPOSÉ — nouveau contact post-cooldown** | 2026-04-13 | Cooldown 90j fini le 12/07. Nouveau premier contact autorisé UNIQUEMENT avec valeur nouvelle (le marché assurance a mûri : exigence de preuve de mandat comme condition de police). Canal : email après validation Hunter ≥80 ou source publique. Draft prêt (04/07). Envoi recalé : **lundi 20/07**. |
| 2026-06-29 (radar W27) | Laurence Hadj | Doctolib | DPO Groupe | LinkedIn (profil à vérifier visuellement) | **PROPOSÉ** | — | Draft v2 prêt (04/07, corrigé voix). Envoi initialement planifié 06/07, non exécuté. **Recalé : 16-17/07.** Canal alt si silence 14j : contact.dataprivacy@doctolib.com, "À l'attention de Laurence Hadj, DPO Groupe", depuis audric@mandatia.eu. |
| — | MACSF | MACSF | Assureur RCP médicale (Audric sociétaire) | Courrier papier sociétaire | **PROPOSÉ** | — | Courrier de médecin sociétaire à son assureur = pas du cold outreach. Question : un assuré qui utilise un agent IA en consultation est-il couvert, et à quelles conditions de mandat ? Draft prêt (04/07). **Recalé : semaine du 20/07.** |
| 2026-04-22 | Rémi Stefanini | CNIL (DTIA) | Régulateur | LinkedIn → email | **REPORTÉ** | 2026-04-24 (autoreply) | Veille passive. Aucune action. Réactivation uniquement sur signal entrant ou consultation publique CNIL agents. |
| 2026-04-15 | Adnan Khan | Centurian.ai (ex-Equinix) | Runtime gouvernance agents | LinkedIn | **SORTI FUNNEL** | 2026-04-27 | Partner intégration LT (Centurian = futur consommateur du registre). Pas de relance froide. |
| 2026-09-14 (radar W38) | Matthieu Caillat | AXA | Group CTO & AI Officer + CEO AXA Group Operations (effectif 01/09/2026) | LinkedIn à vérifier / email `prenom.nom@axa.com` PROBABLE | **PROPOSÉ** | — | Trigger prise poste 01/09 (13j). Angle ASSURANCE. Cible C-level ExCom → accessibilité faible (historique avril 2026 : 2/21). Draft prêt : `outreach/drafts/2026-09-14_caillat.md`. Envoyer un canal à la fois, LinkedIn en priorité si Audric confirme bouton Message. |
| 2026-09-14 (radar W38) | Brahim Ouhdi | OUHDI LAW FIRM (Paris 17) | Avocat au Barreau de Paris, droit du numérique / affaires, publications AI Act × relation-client cross-border FR/MA | LinkedIn probable direct / formulaire cabinet | **PROPOSÉ** | — | Trigger article Village de la Justice du 26/08/2026 (19j) sur AI Act + opt-in téléphonique. Angle JURIDIQUE, pas DP classique — proposition ciblée de relecture co-signée avec Iteanu du texte de référence mandat. Draft prêt : `outreach/drafts/2026-09-14_ouhdi.md`. |

---

## Slots libérés (silence total >35j, purge appliquée 04/07, confirmée 15/07)

Erdem Yağan (Remedi), Juliette Mattioli (Thales), Ian Rogers (Ledger), Aldrick Zappellini (Crédit Agricole), David Rice (HSBC), Stanislas Polu (Dust), Florence G'sell (Sciences Po), Marcel Salathé (EPFL), Christine Balagué (IMT-BS), Vincent Strubel (ANSSI), Anne Bouverot (AI Action Summit), Cédric O, Henri d'Agrain (Cigref), Tariq Krim, Stéphane Distinguin (Fabernovel) — **15 contacts**.

Bruno Sportisse, initialement dans cette purge, en est SORTI le 15/07 (réponse reçue) : leçon — les institutions publiques répondent à 2-3 mois, la règle 35j est calibrée pour le privé.

Aucune re-sollicitation prévue : le funnel reste recentré santé/assurance/juridique.

---

## Compteur Design Partners

- Signés : **0 / 5**
- Fil frais : **1 à confirmer** (Gesnouin, envoyé 15/07 — 61j silence, temps long institutionnel encore tolérable jusqu'à ~90j)
- Fils dormants : 2 (Iteanu — statut reprise à reconfirmer par Audric ; Hubert — optionnel)
- Envois planifiés au 15/07 : 3 (Hadj, Klaimee, MACSF) — **statut réel à reconfirmer par Audric** (cf. bloc resync W38 en haut)
- Veille passive : 1 (Stefanini)
- Nouveaux drafts W38 (2026-09-14) : 2 (Caillat AXA, Ouhdi avocat) — PROPOSÉ, aucun envoi encore
- Règle capacité : **3 fils chauds simultanés max**. Un envoi à la fois. Après resync, si 3 slots planifiés juillet sont libérés, on redémarre proprement.

---

## Dates clés

| Date | Événement |
|---|---|
| **2026-07-15** | Email Gesnouin envoyé (cc Sportisse). Resync pipeline v7.1. |
| **2026-07-16 ou 17** | Envoi LinkedIn Hadj (vérifier bouton Message avant). |
| **2026-07-20 (lundi)** | Envoi email Boutemadja/Klaimee (adresse validée Hunter ≥80 d'abord). |
| **Semaine du 20/07** | Courrier MACSF sociétaire. |
| **Dès reconfirmation appel** | Email reprise Iteanu (pas de date artificielle — 20 min au calme pour reconfirmer le contenu de l'appel de mai, puis envoi). |
| **2026-07-31** | Si silence Hadj 14j → canal alt contact.dataprivacy@doctolib.com. |
| **2026-08-31** | Jalon : template agent-sante-rgpd shippé + brouillon texte de référence mandat/responsabilité. |
| **2026-09-30** | Bilan 90j : objectif 1 DP signé + 1 signal payant template. |

Gesnouin : pas de fenêtre canal alt (le cc Sportisse interdit toute insistance). Silence = silence.

---

## Changelog pipeline

- **2026-09-14 (v7.2, radar W38)** : ajout bloc de resync W38 en tête de fichier (pipeline stale +61j). Aucune modification unilatérale des lignes existantes — Audric reste single-source-of-truth sur l'état réel des envois de juillet. Ajout de 2 lignes PROPOSÉ (Caillat AXA prise de poste 01/09, Ouhdi avocat article 26/08). Compteur DP mis à jour pour refléter l'incertitude sur les envois juillet. Drafts dans `outreach/drafts/2026-09-14_*.md`. Radar W38 explicitement livre 2 cibles (pas 5) — auto-critique : trigger events fiables <30j quasi-inexistants côté FR compliance/AI en cette semaine, préférer 2 solides à 5 spéculatifs (règle explicite du prompt radar).
- **2026-07-15 (v7.1)** : RESYNC RÉEL (session Claude). ★ Réponse Bruno Sportisse (redirection vers Philippe Gesnouin, resp. programme Santé numérique Inria, cc demandé) — Sportisse requalifié EN COURS HUMAIN, sorti de la purge. Nouvelle ligne Gesnouin, email envoyé 15/07 depuis Zimbra (version ultra-courte, cc Sportisse). Confirmation Audric : AUCUN des 4 envois planifiés le 04/07 (Hadj 06/07, Iteanu, Klaimee 13/07, MACSF) n'a été exécuté — replanification resserrée à un envoi à la fois. Purge v7.0 confirmée à 15 slots (16 moins Sportisse). Tableau restructuré : pipeline actif séparé des slots libérés.
- **2026-07-04 (v7.0, jamais poussée — intégrée ici)** : resync post-dérive 60j. Purge 16 SLOT LIBÉRÉ. Stefanini → REPORTÉ. Ajout ligne manquante Boutemadja/Klaimee (contactée 13/04, jamais tracée). Iteanu : appel qualifié tenu début mai, exception relance orale activée. Ajout Hadj (Radar W27). Recentrage funnel santé/assurance (décision C-RAMPE + angles, decision log). 5 drafts dans outreach/drafts/. Post-mortem dérive : le .bat de push n'a pas été lancé pendant 11 jours — d'où cette v7.1 qui fusionne.
- **2026-05-04 (v6.0)** : synchro post-S18 (Adnan sorti, Iteanu/Hubert EN COURS HUMAIN, funnel 21→17).
- Historique antérieur : git log du fichier.
