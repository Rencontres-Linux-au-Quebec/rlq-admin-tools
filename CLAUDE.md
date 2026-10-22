# Consignes pour Claude - rlq-admin-tools

## Pull requests

Les créer et donner le lien, ne jamais les fusionner ni les approuver ; l'utilisateur les valide lui-même.

## Tests : le moins de jetons possible - Pour lancer ou vérifier les tests, déléguer à l'agent **`testeur`** (`.claude/agents/testeur.md` : Claude Haiku 5.5, effort low). Il lance
  `nginx-tools-tests/run-all.sh` (ou seulement les modules nommés) et ne rapporte que le verdict, les échecs et les statistiques. Ne jamais relire la
  sortie complète de run-all.sh dans la conversation principale.
- Corriger un échec : dans la conversation principale ; un échec simple et bien localisé peut être confié à Claude Sonnet 5.5, effort medium.
- Une seule exécution de run-all.sh à la fois sur une machine (chaque passage supprime les dossiers temporaires `test-rlq-*` créés pendant qu'il tourne).
- L'utilisateur peut aussi lancer run-all.sh lui-même et ne coller que les lignes `[ÉCHEC]` et `FAIL`.

## Conventions

Celles de `doc/CONTEXTE.md` (section 3) : version MAJEUR.MINEUR.AAAAMMJJ.HHMMSS (heure locale), CHANGELOG.md indique le plus récent en premier, `--version`, `--changelog`, options triées, configuration `/etc/default/<programme>.conf` puis `~/.<programme>.conf`, archives `nom.MAJEUR.MINEUR.zip`.

## Dépôt public : aucune donnée personnelle

Jamais de vrai nom, courriel, nom d'utilisateur ou adresse IP d'une personne dans le dépôt (code, tests, changelogs, docs). Exemples : noms inventés,
`exemple.org`, adresses de documentation (RFC 5737) ou blocs `11.x` quand une adresse publique est nécessaire (voir `nginx-tools-tests/README.md`).
La configuration nginx (privée) et les termes personnels de `test_docs` restent hors du dépôt.
