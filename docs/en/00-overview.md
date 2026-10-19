# Overview and concepts

*nginx-tools* is a suite of command-line programs to install, audit, monitor and maintain an **nginx + Odoo** server (and, with the same engine, a **BigBlueButton** server). It is written for system administrators who know Linux (systemd, nginx, PostgreSQL, firewalls) and Odoo (Community 18, ERPLibre-style installs).

## The programs

| Program | Language | What it does | Needs root |
|---|---|---|---|
| `nginx-hardening.sh` | bash | 16-step audit/installation of the server: nginx, firewall, Odoo limits, fail2ban, HSTS, log retention, e-mail relay | `--update` only |
| `nginx-log-audit.sh` | bash | nginx log report: robots, refusals, attacks, IP investigation, bans | for bans |
| `sync-crowdsec-blocklist.sh` | bash | imports the CrowdSec community blocklist into two firewall ipsets | yes |
| `web-monitor.py` | python | orchestrator: hourly pass, alerts, summaries, one-question-per-fix `--apply` | for fixes |
| `app-health-check.py` | python | health check of nginx + the application (probes, TLS, sensitive files, e-mail DNS) | partly |
| `app-log-check.py` | python | analysis of Odoo's systemd journal (protocol attacks, tracebacks, noise) | partly |
| `app-log-live.py` | python | real-time Odoo log with visitor names, country, bans and a dashboard | partly |
| `odoo-backup.sh` | bash | native-format Odoo backup/restore with retention, remote copy and systemd timer | yes |
| `odoo-update-module.sh` | bash | updates Odoo modules (`rlq_*` by default) with the service stopped, then restarts and warms up | yes |
| `odoo-warmup.py` | python | warms Odoo's caches after a restart | no |
| `odoo-mail-retry.py` | python | lists and resends Odoo e-mails in *exception* state | yes |
| `odoo-chat-post.py` | python | creates Discuss alert channels/threads, a restricted bot account, and posts alerts | no |
| `odoo-docs.py` | python | publishes this documentation into Odoo (OCA `document_page` wiki or website pages) | no |
| `zip-versions.py` | python | reports versions inside release archives, compares with the installation | no |
| `host-perf-audit.py` | python | on a Proxmox host (or any Linux server): what limits the performance — CPU, memory, disks, ZFS, network, guests — and whether SSD disks are justified | for a full report |

Shared components live in `apps/` (profile detection, report generator, i18n, anonymizer, RDAP/whois, IP cache, mail…). They are internal: do not run them directly except `apps/_anonymiser.py` (a filter).

## Requirements

* Debian/Ubuntu-like system with systemd. BigBlueButton 2.7 on Ubuntu 20.04 means **Python 3.8** — the code avoids newer syntax.
* `python3`, `bash`, `gawk` or `mawk`; recommended: `geoip-bin` + `geoip-database` (local country lookup), `fail2ban`, `ufw` or `iptables`/`ipset`, `curl`.
* PostgreSQL access is read-only through `runuser -u postgres -- psql` (this is why anything touching Odoo's database needs root).

## Installation

```bash
cd /root/scripts
unzip -o nginx-tools.<VERSION>.zip && cp -r nginx-tools/* . && rm -rf nginx-tools
./nginx-hardening.sh --check          # audit, changes nothing
./nginx-hardening.sh --update         # install/repair what is missing (backs up modified files)
unzip -o nginx-tools-tests.<VERSION>.zip && nginx-tools-tests/run-all.sh
```

Always deploy the program archive and the test archive **together** (same MAJOR.MINOR). `zip-versions.py` checks that names and contents agree.

## Conventions shared by every program

**First line.** Every run prints `NAME vVERSION` first (even `--help`). Data-producing or streaming programs print it on standard error.

**Versions.** `MAJOR.MINOR.YYYYMMDD.HHMMSS` (local time). `--version` prints it; `--changelog` shows `doc/NAME.changelog.txt`, newest first, with version numbers colored on a terminal only.

**Configuration layering.** `/etc/default/NAME.conf` is read first, then `~/.NAME.cfg` if it exists (the last one wins), then the command line (highest priority). `-c/--config FILE` reads that file **alone** and it must exist. Files are *parsed, never executed*; only known keys are kept. At start-up each program prints which files it read, with their modification date and a one-line summary of the important options. A default file is created on first run from `doc/NAME.conf.example`. Shared keys (`ANONYMIZE`, `LOG_KEEP_DAYS`, language…) live in `/etc/default/app-default.conf`.

**Language.** Programs speak English and French (other languages: add `lang/NAME.XX.po`, see *Translation*). Priority: `--lang` > `NGINX_TOOLS_LANG` > the program's variable (`WEB_MONITOR_LANG`…) > `LANGUAGE=` in the file > the environment as gettext: GNU `LANGUAGE` (`fr_CA:fr:en`, ignored under the `C` locale), then `LC_ALL`, `LC_MESSAGES`, `LANG` — the first defined wins, so a forgotten `LC_ALL` hides `LANG`. The *Options* line at start-up says which setting decided: `--lang en (LC_ALL=C.UTF-8 ; LANG=fr_CA.UTF-8 ignored)`.

**Alphabetical options.** Help lists options alphabetically; a test enforces it.

**`--report-err`.** Prints at the end a paste-ready report: program, version, command, host, system, duration, exit code, versions of the whole suite, failures, warnings, recommendations. Secrets are masked; colors and prompts are disabled. This is the preferred way to report a problem.

**Read-only by default.** Programs that change the system say so, ask for confirmation, and back up files they modify. `--yes` removes questions where it makes sense.

**`--verbose`** is forwarded to every program a program launches, so every external command is visible.

**Progress.** Long programs print one line per step with elapsed time on standard error, only on a terminal or with `--verbose` (never in pipes or cron).

**Privilege notice.** A reader program run without root prints “Limited rights (not root): …” stating what will be incomplete (silence with `NGINX_TOOLS_AVIS_ROOT=0`). See *Who must be root*.

## Anonymized output (`--anonymize`)

Every program accepts `--anonymize` (or `ANONYMIZE=1`, `NGINX_TOOLS_ANONYMIZE=1`). IP addresses become `IP-4f2a9c`, e-mails `usager-9c1e03@anonyme.invalid`, logins/user names `ID-3b7d11`, tokens/passwords/cookies `***`. Pseudonyms are **stable** (HMAC-SHA256 with a per-machine secret salt stored in `/etc/default/nginx-tools-anon.salt` or `~/.nginx-tools-anon.salt`, mode 600), so the same visitor keeps the same pseudonym from one report to the next, which makes shared excerpts safe to post. Loopback, masks and version numbers are left alone. The filter *fails closed*: if it is requested but missing, the program stops instead of printing clear data. `apps/_anonymiser.py --pseudonyme VALUE` tells you which pseudonym a known value maps to. Limit: only the recognized patterns are masked (a person's name written in free text is not).

## Lists of trusted addresses

Addresses specific to an installation live **outside the code**, in `/etc/default`:

* `nginx-tools-white-list.conf` — trusted addresses: never banned, allowed to development/lab sites.
* `nginx-tools-ip-location.conf` — named places (`# University [shared] [protected]`), no access granted.

`nginx-hardening.sh --update` generates the nginx snippets from these files (`team-ips-geo.conf`, `team-ips-allow.conf`); never edit those by hand.

## Data kept by the suite

* `/var/lib/nginx-tools/ip-cache.sqlite` (mode 600): DNS name (30 days), block owner and country (90 days); failed lookups are never cached; addresses unseen for 180 days are purged (an IP address is personal data). `--no-cache`, `NGINX_TOOLS_IP_CACHE=off|path`.
* Program logs (`app-log-live`, `web-monitor`, `odoo-update-module`) are kept `LOG_KEEP_DAYS` days (180 by default, 0 = forever).
