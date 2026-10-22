# odoo-backup.sh — sauvegarde et restauration au format natif d'Odoo

Sauvegarde chaque base configurée (ou détectée) au format de la page *Gérer les bases de données* d'Odoo : dump texte `pg_dump --no-owner` + `manifest.json` + `filestore/`, empaquetés en `.zip` (importable par la page d'Odoo) ou `.tar.xz`.

```bash
odoo-backup.sh --dry-run                   # ce qui serait fait
odoo-backup.sh                             # sauvegarder toutes les bases
odoo-backup.sh --db mabase --dest /mnt/sauvegarde
odoo-backup.sh --status                    # sauvegardes présentes, âge de la dernière, minuterie, copie distante
odoo-backup.sh --test-restore              # restaure la dernière sauvegarde dans une base temporaire, vérifie, supprime
odoo-backup.sh --restore /var/backups/odoo/mabase_2026-10-14.zip --db mabase_copie
odoo-backup.sh --install-timer --times "09:00 16:00 23:00"
```

## Comportement et garanties

* **La restauration n'écrase jamais** : une base ou un filestore existant est un refus. Restaurer sous un nouveau nom, puis basculer.
* **Rétention** : `KEEP_RECENT_DAYS` garde *toutes* les sauvegardes des N derniers jours (sinon plusieurs sauvegardes par jour seraient effacées), puis `KEEP_DAILY`, `KEEP_WEEKLY`, `KEEP_MONTHLY` gardent la dernière de chaque jour, semaine ISO et mois.
* **Copie distante** : `REMOTE=utilisateur@hôte:/chemin` copie avec `rsync` ; `--status` dit s'il existe une copie hors du serveur (une sauvegarde qui reste sur le serveur n'est pas une sauvegarde).
* **Seuil d'alerte** du contrôle de la minuterie : plus grand écart observé + 2 heures.
* Le dossier de sauvegarde est en mode 700. `pg_dump` s'exécute sous `PG_USER` (défaut `postgres`).
* Sans liste de bases configurée, les bases sont : le `db_name` d'Odoo, sinon toutes.

## Clés de configuration (`/etc/default/odoo-backup.conf`)

`DEST`, `FORMAT`, `DATABASES`, `ODOO_CONF`, `LANGUAGE`, `FILESTORE_DIR`, `PG_USER`, `KEEP_RECENT_DAYS`, `KEEP_DAILY`, `KEEP_WEEKLY`, `KEEP_MONTHLY`, `REMOTE`, `TIMER_TIME` (un ou plusieurs `HH:MM`). Le fichier est créé au premier lancement et lu sans être exécuté.

## Options
{{HELP}}
