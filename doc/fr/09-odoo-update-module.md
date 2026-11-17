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

* **D'abord un site calme** : avant d'arrêter Odoo, le programme vérifie l'activité : visiteurs actifs (nginx, 5 dernières minutes ; 1.29 : seuls comptent les utilisateurs **connectés à Odoo** qui font autre chose que les sondages du bus d'un onglet laissé ouvert, et les adresses qui font une vraie écriture ; les visiteurs non connectés qui ne font que lire ne comptent plus ; base illisible : toutes les adresses comptent), écritures HTTP (POST, PUT, PATCH, DELETE hors lectures connues, dont les sondages du bus `/bus/...` et `/websocket` ; 1.26 : la discussion en direct, la présence et le suivi des visiteurs sont des écritures **légères** qui, comme les visiteurs, n'annulent pas la mise à jour à la fin de l'attente ; `LIGHT_WRITES` en ajoute ; 1.29 : la connexion `/web/login`, `/website_mail/is_follower`, les sondes `/xmlrpc/2/db` et `/xmlrpc/2/common` et les méthodes de lecture de `call_kw` (`has_access`, `name_search`, `search_count`...) sont des **lectures**, ignorées et comptées dans une note quand le site est occupé ; `READ_REQUESTS` en ajoute ; `/html_editor/bus_broadcast` est une écriture légère), sessions et verrous PostgreSQL, écritures dans les tables d'activité. Dès qu'une activité existe, il attend (contrôle toutes les 30 s) au plus `--wait-quiet` minutes (60 ; `0` = un seul contrôle). Au bout du délai, la mise à jour est **annulée** sans rien arrêter ; `--force-busy` (`FORCE_BUSY=oui`) la fait quand même. `--check-activity` affiche l'état sans rien changer. 1.27 : quand le site est occupé, le programme dit **qui il attend** : chaque adresse active (avec son pays), l'utilisateur d'Odoo de cette adresse (journal des appareils d'Odoo, `res_device_log`) ou « visiteur non connecté », le nombre de requêtes et d'écritures, puis les utilisateurs connectés à Odoo depuis une autre adresse (8 lignes au plus ; `--anonymize` les remplace par des pseudonymes). Sans `sudo` ni root, PostgreSQL reste interrogé par « sudo -n -u postgres ».
* **1.32 : redémarrer plus tôt sans risque** : une écriture de l'administration d'Odoo (`call_kw` : `web_save`, `action_...`) terminée depuis plus de `WRITE_GRACE` secondes (60) ne bloque plus : le formulaire garde ses valeurs dans le navigateur et l'écriture est finie quand nginx la note. Un **formulaire en cours de modification** (un `onchange` après le dernier enregistrement de la même adresse) bloque. `WRITE_GRACE=0` : comportement d'avant. Les écritures du site public (`/survey/submit`...) gardent la fenêtre de 5 minutes. Les écritures légères (discussion, présence) ne sont plus qu'une note (`LIGHT_WRITES_WAIT=yes` pour attendre comme avant). `/web/action/load_breadcrumbs`, `/event/init_barcode_interface` et `ir.config_parameter/get_*` sont des lectures ; `mail.push.device` est une écriture légère. Une adresse qui utilise l'administration (`/web/dataset/`, `/web/action/`, `/odoo`) est un « utilisateur connecté (compte non identifié) », pas un visiteur. Un contrôle identique au précédent tient sur une ligne (« inchangé depuis le contrôle précédent »).
* **Copie des modules** : les dossiers des modules sont copiés en `.tar.gz` dans `MODULES_BACKUP_DIR` (`/var/backups/odoo-update-module`, les 10 dernières gardées) *avant* tout changement.
* **Contrôle après le démarrage** : les lignes ERROR / CRITICAL du journal d'Odoo depuis le redémarrage (journal systemd et `logfile` d'Odoo), après le préchauffage.
* **Retour arrière** : après une mise à jour en échec, un démarrage raté ou des erreurs dans le journal - et si ce lancement a remplacé le code avec `--zip` - , les dossiers d'avant sont remis, mis à jour de nouveau et Odoo redémarré. Sur un terminal, une question d'abord (Entrée = oui) ; sans personne (cron, systemd), automatique ; `--no-rollback` (`ROLLBACK=non`) l'interdit. Le site ne reste jamais arrêté.
* **Ctrl+C** répond tout de suite, même pendant une mise à jour de 30 minutes ; « oui » arrête la mise à jour et redémarre le service s'il tournait.

## À vérifier ensuite

Les journaux de mise à jour sont gardés `LOG_KEEP_DAYS` jours. Un `-u` réussi suivi d'un préchauffage propre est le vrai signal pour les modules qui modifient des vues XML ; en cas d'échec, lire le chemin du journal affiché.

## Clés de configuration

`ADDONS_DIR`, `BACKUP`, `BUSY_VISITORS` (3), `VISITOR_WINDOW` (5), `WAIT_CONNECTED` (60), `WAIT_CONNECTED_LOW` (3), `WAIT_ANONYMOUS` (30), `WAIT_ANONYMOUS_LOW` (2), `LOW_REQUESTS` (10), `CONNECTED_WINDOW` (15), `COMMAND`, `DATABASE`, `LANGUAGE`, `MODULES`, `MODULES_BACKUP_DIR`, `ODOO_CONF`, `ODOO_DIR`, `ROLLBACK`, `RUN_USER`, `SERVICE`, `ZIP`, `WARMUP`, `TIMEOUT` (1800 s), `WAIT` (90 s), `WAIT_QUIET` (vide : délais selon le profil), `FORCE_BUSY` (non).

## Options
{{HELP}}
