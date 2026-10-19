# Qui doit être root, et ce que la suite touche

Règle : un programme qui **modifie** le système (pare-feu, services, fichiers de `/etc`, bases de données) ou qui **ne peut rien lire d'utile** sans root le **refuse dès le début** (avant tout travail ; `--help`, `--version`, `--changelog` exceptés). Un programme de lecture fonctionne sans root mais affiche « Droits limités (pas root) : … » en disant ce qui sera incomplet.

PostgreSQL est lu par le compte `postgres` (`runuser`) : tout ce qui touche aux bases d'Odoo (modules, comptes, inscriptions, courriels) exige root.

| Programme | Utilisateur ordinaire | Root requis |
|---|---|---|
| `zip-versions.py` | entièrement | jamais |
| `odoo-warmup.py` | oui (HTTP) | seulement pour écrire `/etc/default/odoo-warmup-pages.conf` (sinon fichier personnel) |
| `odoo-chat-post.py` | entièrement (API externe + clé) | jamais ; seulement pour lire `/etc/default/odoo-chat-post.conf` (clé d'API, droits 600) |
| `app-health-check.py` | en partie | `nginx -t`, PostgreSQL, fail2ban, journaux protégés ; `--create-config` dans `/etc/default` |
| `app-log-check.py`, `app-log-live.py` | en partie | PostgreSQL (modules, utilisateurs), fail2ban, pare-feu, `nginx -T`, bannissements |
| `web-monitor.py` | lecture : `--summary`, `--list-users`, `--status`, `--dry-run`, `--unban-check` | refusé dès le début pour les passages, minuteries, `--apply`, bannissements |
| `nginx-log-audit.sh` | lecture | `--ban`, `--unban`, `--export-bans`, `--import-bans` |
| `nginx-hardening.sh` | `--check` | `--update` (refusé avant le verrou) |
| `odoo-update-module.sh` | `--dry-run` | mise à jour réelle |
| `odoo-backup.sh` | `--dry-run`, ou déjà le compte PostgreSQL | sauvegarde, minuteries |
| `sync-crowdsec-blocklist.sh` | `--dry-run` | synchronisation, état, cron, désinstallation, crochet ufw |
| `odoo-mail-retry.py` | non | toujours |

## Propriétés de sécurité

* Les fichiers de configuration sont analysés, jamais exécutés ; les clés inconnues sont ignorées.
* Les mots de passe ne sont jamais passés en option ni affichés (`--report-err` masque les secrets).
* Les fichiers contenant des secrets sont créés en mode 600 et les versions précédentes sont sauvegardées.
* Les lectures PostgreSQL utilisent une transaction en lecture seule (`default_transaction_read_only=on`) ; la seule écriture (renvoi de courriels) est protégée et consignée.
* `--anonymize` (voir *Vue d'ensemble*) rend n'importe quelle sortie partageable.
* **Ctrl+C demande toujours confirmation avant d'arrêter**, dans tous les programmes, et répond tout de suite même pendant une commande longue (`timeout --foreground`, `run_interruptible`) ; quand un programme en lance un autre, seul celui de devant pose la question.
* Le cache des IP contient des données personnelles : mode 600, purgé après 180 jours.
