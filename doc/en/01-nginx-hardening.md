# nginx-hardening.sh - server audit and installation

Audits (default) or installs/repairs (`--update`) the server's baseline in numbered steps. Nothing is changed without `--update`; every file it modifies is backed up first. Runs for the Odoo profile and the BigBlueButton profile (`--app odoo|bbb`, auto-detected otherwise; the audit says "not applicable" where a step does not fit the application).

```bash
./nginx-hardening.sh --check --app odoo          # read-only audit
./nginx-hardening.sh --update                    # apply (root; asks a few questions the first time)
./nginx-hardening.sh --update --rename-to new.example.org   # DNS name change + new Let's Encrypt certificate
```

## Steps

| Step | Subject |
|---|---|
| 0 | required programs (`ss`, `curl`, `logrotate`, `fail2ban`, `iptables-persistent`) |
| 0a | nginx before the changes (`nginx -t`, service) |
| 0b | time zone (`--timezone`) |
| 0c | nginx cache directories (`proxy_cache_path`) |
| 0d | e-mail of the programs: `msmtp`, SMTP relay asked once, password asked separately and never an option (`--mail-*`) |
| 0e | DNS name change in nginx and Let's Encrypt (`--rename-from/--rename-to`) |
| 1 | ACME directory `/var/www/letsencrypt` |
| 2 | catch-all log (sensor for requests to unknown host names) |
| 3 | maintenance page |
| 4 | Odoo listening interface and nginx upstreams: the upstream port must be Odoo's; checks the websocket (live chat) upstream, `proxy_http_version`, `proxy_read_timeout`; upstreams of another Odoo version are neither checked nor changed; 2.89: on an Odoo server, `--update` sets the `worker_connections` of nginx to 2048 (`WORKER_CONNECTIONS`, `events` block of nginx.conf: each websocket of the chat takes 2 connections) and adds `worker_rlimit_nofile` when missing; copy first, `nginx -t`, reload without cutting anyone |
| 5 | firewall: Odoo's HTTP/gevent ports blocked from outside |
| 6 | memory-limit suggestion: the available RAM (at least 15 % kept for PostgreSQL and the system, 10 % margin) shared by the workers, the cron threads (`max_cron_threads`, `--cron-threads`) and the gevent process (2.82). 2.85: Odoo compares its limits with the **virtual** memory; the suggested limit is the RAM share plus the virtual memory without RAM measured on the workers (about 400 MB), and `limit_memory_soft` never goes below 1024 MB nor below 1.5 × a worker at rest (fewer workers are suggested instead). A current limit under a worker at rest is a failure: the workers are recycled as soon as they start, in a loop. 2.86: check of the limits of the gevent process of the live chat (`limit_memory_soft_gevent` 2147483648, `limit_memory_hard_gevent` 2684354560 recommended: without them it takes the limit of the workers and restarts when many people chat, which cuts every discussion); when the RAM is short, the memory to add to keep the workers at 1536 MB (hard limit), and a warning when less than 15 % of the memory is available. Same calculation as the memory risk of app-log-live.py |
| 7 | Odoo systemd unit and `run.sh` audit |
| 8 | `odoo.conf` audit (`list_db`, `admin_passwd`, proxy mode, limits...); 2.87: the file read the way Odoo reads it (`apps/_odoo_conf_check.py`): a comment after a value (`limit_memory_soft_gevent = 2147483648 # 2048 MB`) stays IN the value and Odoo no longer starts; also key given twice, value of the wrong type, keys unknown to Odoo and parsing by the Odoo of the server. Check alone: `python3 apps/_odoo_conf_check.py /opt/odoo/erplibre/config.conf` |
| 9 | fail2ban jails: catch-all sensor, `odoo-auth` (login failures read from Odoo's journal), `nginx-blocked-probes` (5 nginx refusals in 10 minutes -> 24 h ban) |
| 10 | HSTS actually sent by each HTTPS name (read from `nginx -T`) |
| 11 | log retention (`--log-retention-months`, 1-24, default 3); persistent systemd journal (`JOURNAL_PERSISTENT`, 2.83): the reasons why Odoo stopped survive a reboot |
| 12 | address lists -> nginx snippets (`team-ips-geo.conf`, `team-ips-allow.conf`, `shared-ips-geo.conf`); nginx is reloaded when the snippets are newer than the loaded configuration |
| 13 | alert e-mail: relay, MX, SPF, DMARC, DKIM |
| 14 | `geoip-bin` / `geoip-database` for local country lookup |
| 15 | `app-log-live.py --chime` in byobu/tmux |
| 16 | calls of Odoo to its own public name (User-Agent python-requests) |
| 17 | PostgreSQL (2.83, `PG_LOGGING`, `PG_SLOW_MS`): queries longer than 2 s, lock waits, autovacuum and temporary files written to the PostgreSQL log (file `conf.d/90-nginx-hardening-logging.conf`, reloaded without restart; the text of the slow queries is in it); `shared_buffers` left at 128 MB is reported |

## Notes for administrators

* **State file.** `/etc/default/nginx-hardening.conf` is a *state* file written by the program (asked answers, generated markers) - do not hand-edit.
* **Never `return` at server level** in redirect-only blocks: put the redirect in `location /` and include `snippets/securite-commune.conf`, otherwise the redirect precedes the deny rules.
* **Client addresses** come from `$remote_addr`, never `X-Forwarded-For`. Site logs use the `combined_host` format; nginx refusals go to `/var/log/nginx/blocked-probes.log` so that fail2ban's `nginx-blocked-probes` jail can read them.
* **BigBlueButton.** Security rules go into one file of ours (`/etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx`); no BBB-managed file is edited. HAProxy terminates TLS there, so HSTS uses `http-after-response`. There is deliberately no catch-all sensor on BBB. See `doc/bbb-upgrade.md` to upgrade BBB without losing the hardening (`--update` before and after).
* **Privileges.** `--check` works as a normal user with an incomplete picture; `--update` is refused immediately without root, before taking the lock.

## Options
{{HELP}}
