# nginx-tools-tests/tools/ — exécutables statiques fournis avec la suite

`run-all.sh` les prend **avant** ceux du PATH : aucune installation nécessaire sur un serveur (Linux x86-64).

| Fichier | Version | Licence | Source | SHA-256 |
|---|---|---|---|---|
| `gawk` | GNU Awk 5.3.2 (statique) | GPL-3.0-or-later | https://ftp.gnu.org/gnu/gawk/gawk-5.3.2.tar.xz | `20e6fd3ea50a69ddb4d574a76a718c244c3b9f3225057e3e6136ab6a96bfb2b9` |
| `ruff` | ruff 0.16.9 (static-pie) | MIT | https://github.com/astral-sh/ruff/releases/tag/0.16.9 | `6d80e1c634c39516bae1b2432a1f2a732eef1cd90597af18b8a3b2951cbab6b8` |

Vérifier : `sha256sum -c` sur les valeurs ci-dessus. Mettre à jour : remplacer l'exécutable, puis cette table (version, empreinte) et le
journal `doc/run-all.changelog.txt`. D'autres exécutables statiques (ex. `shellcheck`) peuvent être déposés ici.
