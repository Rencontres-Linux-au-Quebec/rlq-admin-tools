# odoo-backup.sh — backup and restore in Odoo's native format

Backs up every configured (or detected) database in the format of Odoo's own *Manage Databases* page: `pg_dump --no-owner` text dump + `manifest.json` + `filestore/`, packed as `.zip` (importable by the Odoo page) or `.tar.xz`.

```bash
odoo-backup.sh --dry-run                   # what would be done
odoo-backup.sh                             # back up all databases
odoo-backup.sh --db mydb --dest /mnt/backup
odoo-backup.sh --status                    # backups present, age of the latest, timer, remote copy
odoo-backup.sh --test-restore              # restore the latest backup into a temporary database, check it, delete it
odoo-backup.sh --restore /var/backups/odoo/mydb_2026-10-14.zip --db mydb_copy
odoo-backup.sh --install-timer --times "09:00 16:00 23:00"
```

## Behavior and guarantees

* **Restore never overwrites**: an existing database or filestore is a refusal. Restore into a new name, then switch.
* **Retention**: `KEEP_RECENT_DAYS` keeps *all* backups of the last N days (otherwise several backups per day would be erased), then `KEEP_DAILY`, `KEEP_WEEKLY`, `KEEP_MONTHLY` keep the last of each day, ISO week and month.
* **Remote copy**: `REMOTE=user@host:/path` copies with `rsync`; `--status` tells whether a copy exists off the server (a backup that stays on the server is not a backup).
* **Alert threshold** of the timer check: largest observed gap + 2 hours.
* The backup folder is mode 700. `pg_dump` runs as `PG_USER` (default `postgres`).
* Without a configured database list, the databases are: Odoo's `db_name`, otherwise all.

## Configuration keys (`/etc/default/odoo-backup.conf`)

`DEST`, `FORMAT`, `DATABASES`, `ODOO_CONF`, `LANGUAGE`, `FILESTORE_DIR`, `PG_USER`, `KEEP_RECENT_DAYS`, `KEEP_DAILY`, `KEEP_WEEKLY`, `KEEP_MONTHLY`, `REMOTE`, `TIMER_TIME` (one or more `HH:MM`). The file is created on first run, read without being executed.

## Options
{{HELP}}
