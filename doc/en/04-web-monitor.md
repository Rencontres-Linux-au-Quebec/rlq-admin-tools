# web-monitor.py - orchestrator, summaries and one-question fixes

Runs the suite's tools on a schedule, **alerts only when action is needed**, and gives a numbered summary of traffic and security. It is the program to start with on a new server and the one to put on a timer.

```bash
web-monitor.py --install-timer --interval-hours 1   # systemd timer, one pass per hour
web-monitor.py --status                             # timer state, last pass, last alert
web-monitor.py --summary --days 7                   # traffic, blocks and attacks, errors, requests per DNS name, highlights, log coverage
web-monitor.py --apply                              # make the recommended fixes, one question per fix
web-monitor.py --apply --yes                        # same, without questions
web-monitor.py --list-users --table --sort last --reverse   # Odoo logins (or BBB participants) with traffic
web-monitor.py --unban-check                        # re-evaluate manual bans
```

## What a pass does

1. Runs `nginx-log-audit.sh`, `app-health-check.py`, `app-log-check.py` and checks bans, timers and mail.
2. Decides whether something needs attention; if yes, e-mails the alert (relay configured by `nginx-hardening.sh`, step 0d) and records the recommended IPs.
3. At a terminal, offers to ban the recommended addresses (`--no-prompt` to skip) and to open the full report in `less` (`--no-pager`).

`--dry-run` shows the decision without sending e-mail or moving log positions; with `--save-recommended` it still saves the recommended IPs (used by the `b` key of `app-log-live.py`).

## Recommendations are verified

A recommendation states the **real cause**: the program itself evaluates the `location ~` blocks of `nginx -T` for each path that crosses nginx ("rule missing" differs from "server block not including the snippet"). Fixes available through `--apply` include bans, nginx reload, `nginx-hardening.sh --update`, and timer repair. A timer pointing to a configuration file that does not exist is reported.

## Logged-in users are not trusted blindly

The summary has a section **SUSPICIOUS ACTIVITY OF LOGGED-IN USERS**: every account that logged in gets a score made of signs that each have an innocent explanation - only their sum deserves attention.

| Sign | Points |
|---|---|
| malicious URLs requested (sensitive files, injections, PHP...) | 3 |
| burst of pages (15 or more distinct pages within 10 s), scripting tool User-Agent, Odoo access refused for its UID, forms submitted in bulk, address shared by several portal accounts, banned address, disposable e-mail | 2 each |
| failed logins, password resets, 6+ addresses, many 4xx errors, new account (first login in the last 7 days), misspelled e-mail domain | 1 each |

2-3 = *to watch*, 4 and more = *suspicious*. Watched accounts are always listed.

```bash
web-monitor.py --suspect-users                      # the accounts of the section, then: investigate [N] / [a] all
web-monitor.py --investigate-user user@example.org  # one account: Odoo record, ALL its IP addresses, activity, e-mail, Internet
web-monitor.py --watch-odoo-user user@example.org   # always listed, marked [watched] in app-log-live.py
web-monitor.py --ban-odoo-user user@example.org     # investigation, then confirmation
web-monitor.py --unban-odoo-user user@example.org   # account restored, addresses unbanned
```

**Investigation.** The account in Odoo (creation, OAuth provider, logins, registrations, messages, surveys), every IP address it used (each investigated by `nginx-log-audit.sh --investigate`, with the other accounts seen on it), its activity over the whole history kept, its e-mail address (syntax, typo, disposable domain, mail server of the domain) and - only after a yes, or `--internet` - the Internet: StopForumSpam (spam reports of the e-mail and the addresses), Gravatar, a web search of the exact address. These lookups send the address to third parties; `NGINX_TOOLS_INTERNET=off` disables them.

**Ban.** The Odoo account is **archived** (no more login, open sessions end, the e-mail cannot be reused for a new account) and the addresses used by *no other account* are banned at the firewall (`nginx-log-audit.sh --ban`). Internal accounts, the administrator and the public user are never archived - in the program and in the SQL itself. Everything is recorded in `/var/lib/nginx-tools/odoo-users.tsv` (`apps/_odoo_users.py`), which `--unban-odoo-user` uses to undo it and which tells `nginx-log-audit.sh` that the addresses of a banned account are no longer "a legitimate user".

## Notes

* A redirect (3xx, small page) from nginx to a malicious URL is a **rejection** for the monitor.
* `--list-users` on Odoo reads PostgreSQL (root); "Odoo does not record the end of a session", so *connected* means "logged in, not logged out, active within the last minutes".

* `--list-users --table` also shows, per account, the **pages read**, the **pages written** (forms and records sent - not the reads of the Odoo web client), the **MB received** (what nginx sent) and the **MB sent** (size of its requests; needs `rl=$request_length` at the end of the `combined_host` log format, nginx-odoo-config 1.11 - `?` otherwise). `--sort written|received|sent`.
* `--list-users --table` is a **compact** table: no space around the cells, each column as narrow as its content (titles cut, at least 4 characters, on two lines when they have two words). Fields: `num,uid,ip,ipseen,ipcountry,vpn,name,login,created,first,last,logins,minutes,type,events,surveys,phone,country,city,groups,tags,systems,browsers,read,written,received,sent,email` - choose them and their order with `--table-fields` (`all` = every field; by default all but `tags` and `email`). **IP seen**: the account's address with the latest request in the nginx logs, even without a new login (`--sort seen`). **IP country**: country of the owner of each address block according to RDAP / whois (the registry, not a geolocation; yellow when it differs from the Odoo contact's country). **VPN**: the block owner is a known VPN, Tor, a relay (iCloud Private Relay, Cloudflare WARP) or a hosting company (data center) - a guess from the owner's name, not a proof (`--sort vpn`); each address is looked up once on the Internet (rdap.org, otherwise whois), then served by the address cache for 90 days (`NGINX_TOOLS_INTERNET=off`: cache only). **Account created**: creation date of the Odoo account, cyan under 7 days (`--sort created`). Every 5th line is underlined. The title of the sorted column is in cyan. Every setting has a key in the configuration file (`TABLE_FIELDS`, `SORT`, `STATS`, `GROUP`, `CSV`...); actions (`--apply`, `--ban-*`, `--list-users`) stay on the command line. Events = registrations not cancelled, surveys = surveys completed; groups = those created in Odoo or by an `rlq_*` module. In a terminal: last login today in green, account created today in cyan, the busiest accounts in yellow.
* `--group NAME` (members of an Odoo group, accents ignored), `--csv FILE` (every value, never cut; `;` separator, decimal comma in French: Excel opens it directly), `--repeat-header` (titles also at the bottom), `--stats` (members per group and tag, internal / portal, countries, e-mail domains, systems, browsers, top 10 of the most active accounts).

## Options
{{HELP}}
