# Qui doit être root ? — droits requis par chaque programme

Règle : un programme qui **modifie** le système (pare-feu, services, fichiers de `/etc`, bases de données) ou qui **ne peut rien lire d'utile** sans root le **refuse dès le début**
(avant tout travail, hors `--help`, `--version` et `--changelog`). Un programme de **lecture** fonctionne sans root mais affiche une ligne « Droits limités (pas root) : … »
qui dit ce qui sera incomplet (désactivable : `NGINX_TOOLS_AVIS_ROOT=0`).

La lecture de PostgreSQL passe par le compte `postgres` (`runuser`) : tout ce qui touche aux bases d'Odoo (modules, comptes, inscriptions, courriels) exige root.

| Programme | Utilisateur ordinaire | Root requis |
|---|---|---|
| `zip-versions.py` | **Oui, entièrement** (lit des archives .zip) | Jamais |
| `odoo-warmup.py` | **Oui** (requêtes HTTP vers le site) | Seulement pour écrire ou supprimer dans `/etc/default/odoo-warmup-pages` (sinon, fichier personnel) |
| `app-health-check.py` | **Oui, en partie** (contrôles HTTP, certificats, services, disque) | `nginx -t`, PostgreSQL, fail2ban, journaux protégés ; `--create-config` dans `/etc/default` (sinon `~/.app-health-check.conf`) |
| `app-log-check.py` | **Oui, en partie** (lecture des journaux accessibles) — avis « Droits limités » | PostgreSQL (modules, utilisateurs), fail2ban, journaux illisibles |
| `app-log-live.py` | **Oui, en partie** (flux des journaux lisibles) — avis « Droits limités » | Modules et inscriptions (PostgreSQL), fail2ban, pare-feu, `nginx -T`, bannir (touche b) |
| `web-monitor.py` | **Oui pour lire** : `--summary`, `--list-users`, `--status`, `--dry-run`, `--unban-check` (résultats incomplets, avis « Droits limités ») | **Refusé dès le début** pour : passage normal, `--apply`, `--ban-recommended`, `--install-timer`, `--uninstall-timer` |
| `nginx-log-audit.sh` | **Oui pour lire** (statistiques, `--stats`, `--fail2ban` si les journaux sont lisibles) | `--ban`, `--unban`, `--export-bans`, `--import-bans` (pare-feu) |
| `nginx-hardening.sh` | **Oui** : `--check` (défaut, ne modifie rien) | `--update` : refusé dès le début, avant même le verrou |
| `odoo-update-module.sh` | **Oui** : `--dry-run` (simulation) | Mise à jour réelle (arrêt/démarrage du service, compte d'Odoo) |
| `odoo-backup.sh` | **Oui** : `--dry-run` ; ou si l'on est déjà le compte PostgreSQL | Sauvegarde sous le compte PostgreSQL, `--install-timer`, `--uninstall-timer` |
| `sync-crowdsec-blocklist.sh` | **Oui** : `--dry-run` | Synchronisation, `--status`, `--blocked`, `--install-cron`, `--uninstall`, `--ufw-hook` |
| `odoo-chat-post.py` | **Oui, entièrement** (API externe d'Odoo avec une clé API ; aucune lecture de PostgreSQL) | Jamais ; seulement pour lire `/etc/default/odoo-chat-post.conf` (clé API, droits 600) : sinon `~/.odoo-chat-post.conf` |
| `odoo-mail-retry.py` | **Non** | **Toujours** (tout passe par PostgreSQL) : refusé dès le début |

Durée de conservation des journaux propres aux programmes (`app-log-live.py`, `web-monitor.py`, `odoo-update-module.sh`) : clé `LOG_KEEP_DAYS` de
`/etc/default/app-default.conf` (180 jours par défaut ; 0 = jamais effacés).
