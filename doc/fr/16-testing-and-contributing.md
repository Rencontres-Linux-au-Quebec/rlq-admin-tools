# Tests, traduction et contribution

## La suite de tests

`nginx-tools-tests/run-all.sh` valide toute la suite : présence des fichiers, syntaxe (`bash -n`, `py_compile`), **ShellCheck**, **ruff**, tests unitaires/intégration sous chaque awk (mawk, gawk, busybox si présent) **limités à l'environnement du serveur** (modules étiquetés `commun` + `odoo` ou `bbb` ; `--all-environments` les exécute tous, `--list` montre sans exécuter), configuration nginx déployée comparée à la copie de référence (Odoo), puis contrôles en lecture seule du vrai serveur (hors verdict). Un test en échec est relancé seul : échec confirmé (bloquant) ou `[INSTABLE]`.

```bash
nginx-tools-tests/run-all.sh                   # tout, pour ce serveur
python3 -m unittest test_i18n test_anonymiser  # exécution ciblée depuis le dossier des tests
```

Règles que la suite impose : chaque option longue figure dans `doc/NOM.conf.example` ; les options sont en ordre alphabétique ; chaque `test_*.py` déclare `ENVIRONNEMENT = "commun" | "odoo" | "bbb"` ; la première ligne de sortie est `NOM vVERSION` ; aucune syntaxe Python plus récente que 3.8 ; aucun répertoire temporaire oublié ; **aucun vrai fichier de configuration n'est modifié** (des sentinelles surveillent `/etc/default` et `~`) ; les tests redirigent tous les chemins système vers un dossier temporaire et simulent `ufw`, `iptables`, `nginx`, `systemctl`.

Ne jamais lancer une ancienne suite de tests contre de nouveaux programmes (ni l'inverse) : déployer les deux archives ensemble.

## Pièges qui ont déjà coûté un cycle

* `systemctl is-active` affiche l'état *et* renvoie un code non nul : ne pas écrire `$(... || echo inconnu)`.
* La version de développement de ShellCheck est plus récente que celle de Debian et ne signale pas `A && B || C` (SC2015) : un test cherche lui-même ce motif. Jamais d'apostrophe dans `${x:+...}` entre guillemets.
* Un test qui charge un programme dans le processus de test lit le vrai `os.environ` et `/proc` ; corriger les dépendances à la machine au niveau du processus (`helpers.py`).
* Les adresses de documentation (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`) sont « privées » pour `ipaddress` de Python : utiliser d'autres adresses publiques dans les tests.
* Couper par octets (`cut -c`) coupe un caractère accentué en deux : couper avec Python.
* Les invites Python chargent `readline` ; les invites bash utilisent `read -e`.

## Traduction

Les programmes affichent en anglais ou en français. Le mécanisme est une *post-traduction de la sortie* : `apps/_i18n.py` (Python) et `apps/_i18n.sh` + `apps/_traduire.py` (bash) remplacent des fragments connus par le texte de `lang/NOM.XX.po` (format PO standard ; voir `lang/README.md`). Les catalogues partagés `_config` et `_i18n` sont toujours chargés. `test_i18n` examine chaque littéral de chaîne et échoue si un message n'a pas d'entrée au catalogue. Les programmes déjà migrés vers un code en anglais (`zip-versions.py` d'abord, les autres suivent par étapes) déclarent `"Source-Language: en\n"` dans `lang/NOM.fr.po` : les `msgid` sont alors les textes anglais du code et les `msgstr` la traduction française. Pour ajouter une langue : copier un fichier `.po`, traduire les lignes `msgstr`, lancer les tests.

## Signaler un problème

Lancer le programme fautif avec `--report-err` (ajouter `--anonymize` avant de publier) et joindre le rapport.
