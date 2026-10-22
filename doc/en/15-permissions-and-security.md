# Who must be root, and what the suite touches

Rule: a program that **modifies** the system (firewall, services, `/etc` files, databases) or that can read nothing useful without root **refuses at the very start** (before any work; `--help`, `--version`, `--changelog` excepted). A reader program works without root but prints "Limited rights (not root): ..." naming what will be incomplete.

PostgreSQL is read through the `postgres` account (`runuser`): anything involving Odoo databases (modules, accounts, registrations, e-mails) requires root.

| Program | Ordinary user | Root required |
|---|---|---|
| `zip-versions.py` | fully | never |
| `odoo-warmup.py` | yes (HTTP) | only to write `/etc/default/odoo-warmup-pages.conf` (else a personal file) |
| `odoo-chat-post.py` | fully (external API + key) | never; only to read `/etc/default/odoo-chat-post.conf` (API key, mode 600) |
| `app-health-check.py` | partly | `nginx -t`, PostgreSQL, fail2ban, protected logs; `--create-config` in `/etc/default` |
| `app-log-check.py`, `app-log-live.py` | partly | PostgreSQL (modules, users), fail2ban, firewall, `nginx -T`, bans |
| `web-monitor.py` | reading: `--summary`, `--list-users`, `--status`, `--dry-run`, `--unban-check` | refused at start for passes, timers, `--apply`, bans |
| `nginx-log-audit.sh` | reading | `--ban`, `--unban`, `--export-bans`, `--import-bans` |
| `nginx-hardening.sh` | `--check` | `--update` (refused before the lock) |
| `odoo-update-module.sh` | `--dry-run` | real update |
| `odoo-backup.sh` | `--dry-run`, or already the PostgreSQL account | backup, timers |
| `sync-crowdsec-blocklist.sh` | `--dry-run` | sync, status, cron, uninstall, ufw hook |
| `odoo-mail-retry.py` | no | always |

## Security properties

* Configuration files are parsed, never executed; unknown keys are ignored.
* Passwords are never passed as options and never printed (`--report-err` masks secrets).
* Files containing secrets are created with mode 600 and previous versions are backed up.
* PostgreSQL reads use a read-only transaction (`default_transaction_read_only=on`); the one write (mail resend) is guarded and logged.
* `--anonymize` (see *Overview*) makes any output safe to share.
* **Ctrl+C always asks before stopping**, in every program, and is answered at once even during a long command (`timeout --foreground`, `run_interruptible`); when one program runs another, only the one in front asks.
* The IP cache holds personal data: mode 600, purged after 180 days.
