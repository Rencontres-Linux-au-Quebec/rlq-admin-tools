# odoo-update-module.sh - controlled module update

Updates Odoo modules (`rlq_*` by default) the safe way: optionally unpacks a module archive, **stops the service**, runs `odoo -u ... --stop-after-init --no-http --workers=0 --max-cron-threads=0` as the service's account under a maximum duration, **restarts** the service, waits until it listens, then warms the cache (`odoo-warmup.py`).

```bash
odoo-update-module.sh --dry-run                       # service, database, modules, commands - nothing stopped
odoo-update-module.sh --backup                        # odoo-backup.sh first; a failed backup aborts, nothing is stopped
odoo-update-module.sh --zip ~/Downloads --addons-dir /opt/odoo/addons
odoo-update-module.sh --module 'rlq_*' --module website_x --timeout 3600
```

## Auto-detection

Service: `erplibre*` or `odoo*` systemd unit (override `--service`). Database: the `-d` of the service command, else Odoo's `db_name`. Account: `User=` of the unit. Command: `odoo_bin.sh` of the service folder, else `odoo-bin`. An Odoo started by hand makes the program stop unless `--force` (it is then ignored, not stopped).

## Quiet site, copy of the modules, rollback

* **A quiet site first**: before stopping Odoo, the program checks the activity: active visitors (nginx, last 5 minutes), HTTP writes (POST, PUT, PATCH, DELETE except known reads), PostgreSQL sessions and locks, writes in the activity tables. As soon as there is activity, it waits (checking every 30 s) for at most `--wait-quiet` minutes (60; `0` = a single check). At the end of the wait the update is **cancelled**, nothing is stopped; `--force-busy` (`FORCE_BUSY=yes`) runs it anyway. `--check-activity` shows the state without changing anything. Without root, PostgreSQL is queried through « sudo -n -u postgres ».
* **Copy of the modules**: the module folders are saved as a `.tar.gz` in `MODULES_BACKUP_DIR` (`/var/backups/odoo-update-module`, the last 10 kept) *before* anything changes.
* **Check after the start**: the ERROR / CRITICAL lines of Odoo's log since the restart (systemd journal and Odoo's `logfile`), after the warm-up.
* **Rollback**: after a failed update, a failed start or errors in the log - and when this run replaced the code with `--zip` - the previous module folders are put back, updated again and Odoo restarted. On a terminal it asks first (Enter = yes); unattended (cron, systemd) it is automatic; `--no-rollback` (`ROLLBACK=non`) forbids it. The site never stays stopped.
* **Ctrl+C** is answered at once, even during a 30-minute update; "yes" stops the update and restarts the service if it was running.

## What to check after

Update logs are kept `LOG_KEEP_DAYS` days. A successful `-u` followed by a clean warm-up is the real signal for modules with XML/view changes; read the printed log path if anything fails.

## Configuration keys

`ADDONS_DIR`, `BACKUP`, `BUSY_VISITORS` (3), `VISITOR_WINDOW` (5), `WAIT_CONNECTED` (60), `WAIT_CONNECTED_LOW` (3), `WAIT_ANONYMOUS` (30), `WAIT_ANONYMOUS_LOW` (2), `LOW_REQUESTS` (10), `COMMAND`, `DATABASE`, `LANGUAGE`, `MODULES`, `MODULES_BACKUP_DIR`, `ODOO_CONF`, `ODOO_DIR`, `ROLLBACK`, `RUN_USER`, `SERVICE`, `ZIP`, `WARMUP`, `TIMEOUT` (1800 s), `WAIT` (90 s), `WAIT_QUIET` (vide : délais selon le profil), `FORCE_BUSY` (no).

## Options
{{HELP}}
