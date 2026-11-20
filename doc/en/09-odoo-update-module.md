# odoo-update-module.sh - controlled module update

Updates Odoo modules (`rlq_*` by default) the safe way: optionally unpacks a module archive, **stops the service**, runs `odoo -u ... --stop-after-init --no-http --workers=0 --max-cron-threads=0` as the service's account under a maximum duration, **restarts** the service, waits until it listens, then warms the cache (`odoo-warmup.py`).

```bash
odoo-update-module.sh --dry-run                       # service, database, modules, commands - nothing stopped
odoo-update-module.sh --backup                        # odoo-backup.sh first; a failed backup aborts, nothing is stopped
odoo-update-module.sh --zip ~/Downloads --addons-dir /opt/odoo/addons
odoo-update-module.sh --zip rlq_module_a.zip --zip rlq_module_b.zip    # several archives: extracted one after the other; a module may be in one archive only
odoo-update-module.sh --module 'rlq_*' --module website_x --timeout 3600
```

## Auto-detection

Service: `erplibre*` or `odoo*` systemd unit (override `--service`). Database: the `-d` of the service command, else Odoo's `db_name`. Account: `User=` of the unit. Command: `odoo_bin.sh` of the service folder, else `odoo-bin`. An Odoo started by hand makes the program stop unless `--force` (it is then ignored, not stopped).

## Quiet site, copy of the modules, rollback

* **A quiet site first**: before stopping Odoo, the program checks the activity: active visitors (nginx, last 5 minutes; 1.29: only the users **logged in to Odoo** who do something else than the bus polls of a tab left open, and the addresses that make a real write, count; visitors not logged in who only read no longer count; database unreadable: every address counts), HTTP writes (POST, PUT, PATCH, DELETE except known reads, including the bus polls `/bus/...` and `/websocket`; 1.26: live chat, presence and visitor tracking are **light** writes which, like visitors, do not cancel the update at the end of the wait; `LIGHT_WRITES` adds more; 1.29: the sign-in `/web/login`, `/website_mail/is_follower`, the probes `/xmlrpc/2/db` and `/xmlrpc/2/common` and the read methods of `call_kw` (`has_access`, `name_search`, `search_count`...) are **reads**, ignored and counted in a note when the site is busy; `READ_REQUESTS` adds more; `/html_editor/bus_broadcast` is a light write), PostgreSQL sessions and locks, writes in the activity tables. As soon as there is activity, it waits (checking every 30 s) for at most `--wait-quiet` minutes (60; `0` = a single check). At the end of the wait the update is **cancelled**, nothing is stopped; `--force-busy` (`FORCE_BUSY=yes`) runs it anyway. `--check-activity` shows the state without changing anything. 1.27: when the site is busy, the program says **who it waits for**: each active address (with its country), the Odoo user of that address (Odoo device log, `res_device_log`) or "visitor not logged in", the number of requests and writes, then the users logged in to Odoo from another address (8 lines at most; `--anonymize` replaces them with pseudonyms). Without root, PostgreSQL is queried through « sudo -n -u postgres ».

* **1.39: connected users are never cut**: any user logged in to Odoo and active in the last `VISITOR_WINDOW` minutes, and any chat or presence write (`LIGHT_WRITES_WAIT=yes`), delays the update. If the site is still busy at the end of the wait, the update is **cancelled** and nothing is stopped. Anonymous visitors who only read do not delay it.
* **1.32: restart sooner without risk**: a write of the Odoo administration (`call_kw`: `web_save`, `action_...`) over for more than `WRITE_GRACE` seconds (60) no longer blocks: the form keeps its values in the browser and the write is over when nginx logs it. A **form being edited** (an `onchange` after the last save of the same address) blocks. `WRITE_GRACE=0`: behaviour before. Writes of the public site (`/survey/submit`...) keep the 5-minute window. Light writes (chat, presence) are only a note (`LIGHT_WRITES_WAIT=yes` to wait as before). `/web/action/load_breadcrumbs`, `/event/init_barcode_interface` and `ir.config_parameter/get_*` are reads; `mail.push.device` is a light write. An address that uses the administration (`/web/dataset/`, `/web/action/`, `/odoo`) is a "logged-in user (account not identified)", not a visitor. A check identical to the previous one takes one line ("unchanged since the previous check").
* **Copy of the modules**: the module folders are saved as a `.tar.gz` in `MODULES_BACKUP_DIR` (`/var/backups/odoo-update-module`, the last 10 kept) *before* anything changes.
* **Check after the start**: the ERROR / CRITICAL lines of Odoo's log since the restart (systemd journal and Odoo's `logfile`), after the warm-up.
* **Rollback**: after a failed update, a failed start or errors in the log - and when this run replaced the code with `--zip` - the previous module folders are put back, updated again and Odoo restarted. On a terminal it asks first (Enter = yes); unattended (cron, systemd) it is automatic; `--no-rollback` (`ROLLBACK=non`) forbids it. The site never stays stopped.
* **Ctrl+C** is answered at once, even during a 30-minute update; "yes" stops the update and restarts the service if it was running.

## What to check after

Update logs are kept `LOG_KEEP_DAYS` days. A successful `-u` followed by a clean warm-up is the real signal for modules with XML/view changes; read the printed log path if anything fails.

## Configuration keys

`ADDONS_DIR`, `BACKUP`, `BUSY_VISITORS` (3), `VISITOR_WINDOW` (5), `WAIT_CONNECTED` (60), `WAIT_CONNECTED_LOW` (3), `WAIT_ANONYMOUS` (30), `WAIT_ANONYMOUS_LOW` (2), `LOW_REQUESTS` (10), `CONNECTED_WINDOW` (15), `COMMAND`, `DATABASE`, `LANGUAGE`, `MODULES`, `MODULES_BACKUP_DIR`, `ODOO_CONF`, `ODOO_DIR`, `ROLLBACK`, `RUN_USER`, `SERVICE`, `ZIP`, `WARMUP`, `TIMEOUT` (1800 s), `WAIT` (90 s), `WAIT_QUIET` (vide : délais selon le profil), `FORCE_BUSY` (no).

## Options
{{HELP}}
