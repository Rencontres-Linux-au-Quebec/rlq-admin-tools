# Suite de tests — outils nginx + Odoo (Rencontres Linux Québec)

Une seule commande, à lancer **avant chaque déploiement**, depuis le répertoire des programmes :

```bash
sudo nginx-tools-tests/run-all.sh          # -v pour le détail de chaque test
```

Verdict possible : **TOUT PASSE**, **N ÉCHEC(S) — ne pas déployer**, ou « tout ce qui a été exécuté réussit — mais
N point(s) NON vérifié(s) » (outil absent, tests exigeant root). Code de sortie 0 seulement sans échec.

## Ce qui est vérifié

1. **Syntaxe** de tous les programmes (`bash -n`, `python3 -m py_compile`).
2. **ShellCheck** sur tous les scripts Bash : 0 signalement attendu (les exceptions voulues sont documentées par des
   directives `# shellcheck disable=…` dans le code, avec leur raison).
3. **ruff** sur le Python (défauts réels : noms indéfinis, imports et variables inutilisés…), s'il est installé.
4. **La suite de tests**, une fois **par awk disponible** (mawk, gawk, BusyBox) : gawk et mawk n'interprètent pas les
   programmes awk de la même façon.
5. **Configuration déployée** (`/etc/nginx`, `/etc/fail2ban`) comparée à `nginx-tools-tests/nginx-odoo/` : les fichiers différents
   sont signalés `[ATTN]`, pour information (une différence peut être voulue).

| Module | Couvre |
|---|---|
| `test_conventions.py` | versionnage et changelog de TOUS les programmes : format et date de la version, `--version`, résumé d'en-tête, changelog (plus récent en premier), couleurs, `--changelog \| head` |
| `test_nginx_log_audit.py` | SIGPIPE (IP à 770 requêtes), champs vides, motifs awk, IP protégées, moteurs vérifiés, NAT, récidivistes (.gz), ufw inactif, sauvegarde sans chaînes fail2ban, Ctrl-C et réponse lente dans un vrai terminal |
| `test_sync_crowdsec.py` | IP protégées (`nomatch`, plages), course `grep -q` au redémarrage (10 essais), liste trop petite, liste périmée, ufw, crochet ufw retiré à l'identique |
| `test_nginx_hardening.py` | HSTS empirique à travers les `include`, jail `odoo-auth` généré/chargé/différent, namespace de journal, message `list_db` |
| `test_app_log_check.py` | bruit connu, regroupement avec raison PostgreSQL, détection exacte du service |
| `test_app_health_check.py` | règle stricte `-dev.`/`.dev.`, cohérence `EXPECT_RESTRICTED_ACCESS`, robots.txt, Google OAuth derrière la redirection de langue, `--create-config` |
| `test_multi_app.py` | profils d'application (détection identique en Bash et Python, `--app`, `APP_PROFILE`, profil vide refusé), migration des anciens chemins sans écrasement, chaque programme en mode BigBlueButton, bloc Ressources |
| `test_odoo_mail_retry.py` | `odoo-mail-retry.py` : liste des courriels non envoyés (titres, masquage, causes), menu de renvoi (vrais pseudo-terminaux), `--resend --yes`, avertissements, écriture gardée |
| `test_odoo_warmup.py` | `odoo-warmup.py` : préchauffage du cache d'Odoo contre un FAUX serveur Odoo (pages publiques, assets, connexion par clé d'API, get_views, échecs, démarrage automatique systemd) |
| `test_cache_ip.py` | `apps/_cache_ip.py` : cache permanent des adresses (durées de validité, échecs jamais mémorisés, purge, fichier abîmé, fils et processus en parallèle) et son usage par `_reseau.py` |
| `test_listes.py` | `apps/_listes.py` et `_listes.sh` : liste blanche et lieux hors des archives (syntaxe, options, plage la plus précise, repli transitoire), lecteur bash identique au lecteur Python |
| `test_app_log_live.py` | `app-log-live.py` : heure ISO sans doublons, adresses IP remplacées (personne, équipe, DNS, ISP) suivies de l'adresse, `--min`, couleurs (HTTP, erreurs, connexions), présence (connecté, inactif, déconnecté), flux jamais bloqué, IPv6, BigBlueButton, `--verbose` |
| `test_bbb.py` | état de BigBlueButton (`apps/_bbb.py`) : versions, configuration de BBB et la nôtre, compatibilité (règles chargées, API, client HTML5, HSTS, `bbb-conf --check`), mise à jour simulée entre deux passages, sections AVANT / APRÈS de `nginx-hardening.sh`, section du sommaire |
| `test_config_nginx.py` | configuration de `nginx-tools-tests/nginx-odoo/` sans nginx : syntaxe (accolades, `;`), `include` existants, une seule `location = /robots.txt`, en-têtes HSTS valides, filtre à robots, limite de connexion, règle `/web/database/*`, filtres fail2ban sur des lignes réelles, et le vrai `fail2ban-regex` s'il est installé |
| `test_zip_versions.py` | versions lues dans les archives sans extraction (les nôtres et celles d'autres programmes : manifeste, CHANGELOG, package.json…), cohérence des archives de tests, archive la plus récente par type, archive corrompue, comparaison avec l'installation et la configuration |
| `test_web_monitor.py` | bruit ignoré, un seul courriel, anti-rafale élément par élément, états séparés, `--dry-run` |

Chaque test porte, dans sa description, la version où le bug a été corrigé : c'est un test de **non-régression**.

## Outils recommandés (plus il y en a, plus la couverture est complète)

```bash
apt install shellcheck gawk mawk busybox    # indispensables : sans gawk, le bug « awk -v » est invisible
pipx install ruff                           # ou exécutable statique déposé dans nginx-tools-tests/tools/
```

**Fournis dans `nginx-tools-tests/tools/`** (pris en priorité sur le PATH, aucune installation nécessaire) : `gawk` 5.3.2 (statique,
licence GPL-3.0) et `ruff` 0.16.9 (statique, licence MIT). D'autres exécutables statiques peuvent y être déposés (ex.
`shellcheck`). Les programmes, et leur dossier `apps/` (profils d'application), doivent se trouver dans le répertoire parent de `nginx-tools-tests/`. La configuration nginx de référence est
livrée AVEC l'archive de la suite, dans `nginx-tools-tests/nginx-odoo/` (copie identique de `nginx-odoo-config.zip`, vérifiée par un test).

**Dépôt Git (public)** : la configuration nginx est PRIVÉE et n'est jamais dans le dépôt (`.gitignore`) ; les exécutables de `tools/` y sont (versions, licences, sources et empreintes : `tools/LISEZMOI.md`). Les tests la
cherchent dans `$NGINX_ODOO_DIR`, puis `nginx-tools-tests/nginx-odoo/`, puis `nginx-odoo/` à côté des programmes ; absente, les tests qui en ont besoin
sont désactivés (« configuration absente »), jamais en échec :

```bash
NGINX_ODOO_DIR=~/rlq-nginx-config/nginx-odoo nginx-tools-tests/run-all.sh
```

## Données des tests : fictives

Aucune donnée personnelle (nom, courriel, adresse IP d'une personne) dans la suite : noms inventés, domaines `exemple.org` / `example.com`, adresses de
documentation (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`, RFC 5737) — **privées pour Python**, donc jamais recherchées par les programmes — et, quand un test
exige une adresse PUBLIQUE, des blocs du DoD américain (`11.x`, `21.x`…) qui ne sont attribués à aucun particulier. `donnees_exemples.py` regroupe des
exemples en français (accents, traits d'union, apostrophes), en anglais, avec un accent COMBINANT (forme NFD : 2 caractères, 1 colonne) et en chinois
(1 caractère, 2 colonnes) : ce sont les cas qui décalent les colonnes. `test_alignement.py` (et des tests de `test_app_log_live.py`, `test_odoo_users.py`)
vérifient que les colonnes restent alignées **en français et en anglais**.

## Statistiques (fin de `run-all.sh`)

Durée totale et par passe awk, CPU (utilisateur, système), mémoire maximale d'un processus, disque lu / écrit, nombre de programmes lancés, puis un tableau
par programme testé : nombre de tests **unitaires** (fonctions appelées sans lancer de programme), **fonctionnels** (programme lancé, sortie vérifiée),
**interactifs** (vrai pseudo-terminal : questions, Ctrl-C) et de **conformité** (fichiers vérifiés sans rien exécuter), désactivés, en échec, et leur durée ;
enfin les 5 tests les plus lents. La nature est MESURÉE pendant chaque test (`stats_runner.py`), jamais déclarée à la main ; un module de vérifications
statiques porte `NATURE_TESTS = "conformité"`, un module dont le nom ne désigne pas un programme peut porter `PROGRAMME = "…"`.

Les répertoires temporaires des tests (`/tmp/test-rlq-*`) sont supprimés à la fin de chaque test ; `run-all.sh`
supprime en plus ceux qui resteraient après un passage interrompu (message `[NETTOYÉ]`).

## Ajouter un test

Chaque bug corrigé devrait devenir un test. Dans le module du programme concerné :

```python
def test_description_courte(self):
    """1.xx : ce qui se passait avant la correction."""
    self.mock("outil", "script bash du faux outil")        # faux outil placé en tête du PATH
    rc, out, err = self.run_cmd(["bash", self.prog, "--option"])
    self.assertIn("texte attendu", out)
```

`self.run_pty(cmd, [(b"texte attendu", b"touches", délai)])` lance le programme dans un vrai pseudo-terminal
(questions interactives, Ctrl-C = `b"\x03"`). Vérifier qu'un nouveau test **échoue** quand on réintroduit le bug
(vérification par mutation) : un test qui passe toujours ne protège de rien.

## Environnements

Chaque module `test_*.py` porte une ligne `ENVIRONNEMENT = "commun"`, `"odoo"` ou `"bbb"` (un test de `test_conventions.py` l'exige).
`run-all.sh` détecte le serveur (profil `apps/*.conf`) ou prend `--app NOM`, et n'exécute que les modules communs et ceux de cet environnement :

- `./run-all.sh --list` : environnement détecté et modules retenus, sans rien exécuter ;
- `./run-all.sh --app bbb` ou `--app odoo` : forcer l'environnement ;
- `./run-all.sh --all-environments` : tous les modules (poste de développement, ou avant une livraison).
