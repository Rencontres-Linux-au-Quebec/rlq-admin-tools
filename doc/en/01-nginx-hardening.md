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
| 4 | Odoo listening interface and nginx upstreams: the upstream port must be Odoo's; checks the websocket (live chat) upstream, `proxy_http_version`, `proxy_read_timeout`; upstreams of another Odoo version are neither checked nor changed |
| 5 | firewall: Odoo's HTTP/gevent ports blocked from outside |
| 6 | memory-limit suggestion (`--workers` x available RAM) |
| 7 | Odoo systemd unit and `run.sh` audit |
| 8 | `odoo.conf` audit (`list_db`, `admin_passwd`, proxy mode, limits...) |
| 9 | fail2ban jails: catch-all sensor, `odoo-auth` (login failures read from Odoo's journal), `nginx-blocked-probes` (5 nginx refusals in 10 minutes -> 24 h ban) |
| 10 | HSTS actually sent by each HTTPS name (read from `nginx -T`) |
| 11 | log retention (`--log-retention-months`, 1-24, default 3) |
| 12 | address lists -> nginx snippets (`team-ips-geo.conf`, `team-ips-allow.conf`, `shared-ips-geo.conf`); nginx is reloaded when the snippets are newer than the loaded configuration |
| 13 | alert e-mail: relay, MX, SPF, DMARC, DKIM |
| 14 | `geoip-bin` / `geoip-database` for local country lookup |
| 15 | `app-log-live.py --chime` in byobu/tmux |

## Notes for administrators

* **State file.** `/etc/default/nginx-hardening.conf` is a *state* file written by the program (asked answers, generated markers) - do not hand-edit.
* **Never `return` at server level** in redirect-only blocks: put the redirect in `location /` and include `snippets/securite-commune.conf`, otherwise the redirect precedes the deny rules.
* **Client addresses** come from `$remote_addr`, never `X-Forwarded-For`. Site logs use the `combined_host` format; nginx refusals go to `/var/log/nginx/blocked-probes.log` so that fail2ban's `nginx-blocked-probes` jail can read them.
* **BigBlueButton.** Security rules go into one file of ours (`/etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx`); no BBB-managed file is edited. HAProxy terminates TLS there, so HSTS uses `http-after-response`. There is deliberately no catch-all sensor on BBB. See `doc/bbb-upgrade.md` to upgrade BBB without losing the hardening (`--update` before and after).
* **Privileges.** `--check` works as a normal user with an incomplete picture; `--update` is refused immediately without root, before taking the lock.

## Options
{{HELP}}
