# odoo-update-module.sh - mise à jour contrôlée de modules

Met à jour des modules Odoo (`rlq_*` par défaut) de façon sûre : décompresse au besoin une archive de modules, **arrête le service**, exécute `odoo -u ... --stop-after-init --no-http --workers=0 --max-cron-threads=0` sous le compte du service avec une durée maximale, **redémarre** le service, attend qu'il écoute, puis préchauffe le cache (`odoo-warmup.py`).

```bash
odoo-update-module.sh --dry-run                       # service, base, modules, commandes - rien n'est arrêté
odoo-update-module.sh --backup                        # d'abord odoo-backup.sh ; une sauvegarde en échec annule tout, rien n'est arrêté
odoo-update-module.sh --zip ~/Téléchargements --addons-dir /opt/odoo/addons
odoo-update-module.sh --module 'rlq_*' --module website_x --timeout 3600
```

## Détection automatique

Service : unité systemd `erplibre*` ou `odoo*` (`--service` pour forcer). Base : le `-d` de la commande du service, sinon le `db_name` d'Odoo. Compte : `User=` de l'unité. Commande : `odoo_bin.sh` du dossier du service, sinon `odoo-bin`. Un Odoo lancé à la main arrête le programme sauf avec `--force` (il est alors ignoré, pas arrêté).

## Site calme, copie des modules, retour arrière

* **D'abord un site calme** : avant d'arrêter Odoo, le programme vérifie l'activité : visiteurs actifs (nginx, 5 dernières minutes), écritures HTTP (POST, PUT, PATCH, DELETE hors lectures connues), sessions et verrous PostgreSQL, écritures dans les tables d'activité. Dès qu'une activité existe, il attend (contrôle toutes les 30 s) au plus `--wait-quiet` minutes (60 ; `0` = un seul contrôle). Au bout du délai, la mise à jour est **annulée** sans rien arrêter ; `--force-busy` (`FORCE_BUSY=oui`) la fait quand même. `--check-activity` affiche l'état sans rien changer. Sans `sudo` ni root, PostgreSQL reste interrogé par « sudo -n -u postgres ».
* **Copie des modules** : les dossiers des modules sont copiés en `.tar.gz` dans `MODULES_BACKUP_DIR` (`/var/backups/odoo-update-module`, les 10 dernières gardées) *avant* tout changement.
* **Contrôle après le démarrage** : les lignes ERROR / CRITICAL du journal d'Odoo depuis le redémarrage (journal systemd et `logfile` d'Odoo), après le préchauffage.
* **Retour arrière** : après une mise à jour en échec, un démarrage raté ou des erreurs dans le journal - et si ce lancement a remplacé le code avec `--zip` - , les dossiers d'avant sont remis, mis à jour de nouveau et Odoo redémarré. Sur un terminal, une question d'abord (Entrée = oui) ; sans personne (cron, systemd), automatique ; `--no-rollback` (`ROLLBACK=non`) l'interdit. Le site ne reste jamais arrêté.
* **Ctrl+C** répond tout de suite, même pendant une mise à jour de 30 minutes ; « oui » arrête la mise à jour et redémarre le service s'il tournait.

## À vérifier ensuite

Les journaux de mise à jour sont gardés `LOG_KEEP_DAYS` jours. Un `-u` réussi suivi d'un préchauffage propre est le vrai signal pour les modules qui modifient des vues XML ; en cas d'échec, lire le chemin du journal affiché.

## Clés de configuration

`ADDONS_DIR`, `BACKUP`, `BUSY_VISITORS` (3), `VISITOR_WINDOW` (5), `WAIT_CONNECTED` (60), `WAIT_CONNECTED_LOW` (3), `WAIT_ANONYMOUS` (30), `WAIT_ANONYMOUS_LOW` (2), `LOW_REQUESTS` (10), `COMMAND`, `DATABASE`, `LANGUAGE`, `MODULES`, `MODULES_BACKUP_DIR`, `ODOO_CONF`, `ODOO_DIR`, `ROLLBACK`, `RUN_USER`, `SERVICE`, `ZIP`, `WARMUP`, `TIMEOUT` (1800 s), `WAIT` (90 s), `WAIT_QUIET` (vide : délais selon le profil), `FORCE_BUSY` (non).

## Options
{{HELP}}
