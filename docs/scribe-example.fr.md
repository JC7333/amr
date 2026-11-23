# Exemple : un scribe hospitalier sous mandat

[English version](scribe-example.md)

[`examples/scribe_consultation.py`](../examples/scribe_consultation.py) rejoue, sur votre
machine, ce qui se passe quand un hôpital laisse un scribe IA aider en consultation.
L'hôpital, sa commission, le médecin, le scribe et le dossier patient sont inventés.

```bash
git clone https://github.com/JC7333/amr.git && cd amr && uv sync
uv run python examples/scribe_consultation.py   # affiche chaque réponse, finit par « OK »
```

Trois serveurs AMR partagent un registre jetable. Chacun ne voit que les outils de son rôle :

- le **mandant**, la personne désignée par la commission, qui signe et qui retire ;
- le **scribe**, l'agent ;
- le **dossier patient**, qui reçoit la note et la classe.

## Ce que l'essai montre

1. **Le scribe ne peut pas s'autoriser lui-même.** Il demande son propre mandat et
   reçoit un refus (`root_mandate_needs_principal`) : un agent n'agit que sous un mandat
   qu'une personne lui a donné.
2. **Le mandant signe le mandat.** Il enregistre sa clé une fois, puis signe un mandat
   qui garde la décision de la commission (organe, intitulé, date, référence, personne
   désignée). Le scribe peut transcrire, rédiger la note, rédiger le courrier et classer
   la note. Il ne peut jamais prescrire, poser un diagnostic, coder, exporter ou effacer
   un dossier, envoyer un courrier, écrire à un patient ni créer un autre agent. Classer
   une note est dans une classe de risque : son autorisation dure 30 secondes et le
   dossier patient doit la revérifier auprès du registre.
3. **Avant chaque acte, le scribe demande une autorisation.** Accordée pour transcrire
   et rédiger. Refusée pour une ordonnance, une proposition de codage et un export
   (interdits), et pour lire le dossier (absent du mandat).
4. **Classer la note validée par un médecin.** Le scribe demande une autorisation dont
   le détail porte qui a validé la note et l'empreinte SHA-256 du texte validé. Le
   dossier patient ne reprend pas ce détail au scribe : il le refait avec ce qu'il sait
   lui-même, le médecin connecté à sa session et le texte qu'il a reçu, puis interroge le
   registre : accepté. Si le texte reçu a un mot changé, l'empreinte ne correspond plus :
   refusé (`action_mismatch`). Dans le script, le médecin connecté et le texte reçu sont
   écrits à la main ; en vrai, ils viennent du dossier patient lui-même. Le scribe déclare ensuite le classement
   dans le journal, avec l'autorisation utilisée.
5. **Le mandant retire le mandat**, avec sa signature. Le scribe n'obtient plus aucune
   autorisation, et le dossier patient refuse une autorisation délivrée avant le retrait
   (`mandate_status_revoked`).
6. **La preuve.** `get_proof` rend le mandat, la décision de la commission, la
   déclaration du scribe et le retrait, et vérifie la chaîne des inscriptions, la
   signature du mandat et celle du retrait par le mandant.

La suite de tests exécute l'exemple (`tests/test_scribe_example.py`).

## Ce que l'essai ne montre pas

- Ce n'est ni un vrai scribe ni un vrai dossier patient : aucune consultation n'est
  transcrite, aucun dossier n'est touché, aucune donnée médicale n'est utilisée.
- Le registre note le validateur que le scribe déclare. Il n'authentifie pas ce médecin.
  C'est le dossier patient qui compare le validateur et le texte à ce qu'il sait (qui est
  connecté, quel texte il reçoit).
- Le journal garde ce que le scribe déclare avoir fait. C'est une déclaration, pas la
  preuve que l'acte a eu lieu.
- AMR ne rend un hôpital conforme à aucun texte, et rien ici n'est un conseil juridique.
