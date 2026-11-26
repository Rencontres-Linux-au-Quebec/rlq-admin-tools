# sqli-investigate.py - SQL injection investigation (read-only)

Reads the nginx access logs (current files, rotations and `.gz`), the fail2ban log and, with `--odoo-log`, the Odoo log.
Every request whose **decoded** URL contains a SQL injection attempt is classified by family: `union` (UNION SELECT), `error`
(EXTRACTVALUE, UPDATEXML, CONCAT(0x7e...)), `order-by` (ORDER BY n), `boolean` (' AND 1=1, ') AND ('...), `time` (SLEEP, BENCHMARK), `schema`
(information_schema, LOAD_FILE, INTO OUTFILE).

```bash
sqli-investigate.py                              # investigation with the default paths
sqli-investigate.py --odoo-log /path/odoo.log    # adds the Odoo errors within 60 s of each attempt
sqli-investigate.py --jail nginx-sqli --top 10   # jail to examine, ten addresses in the summary
sqli-investigate.py --report-err                 # paste-ready report in case of a problem
```

## What is written

Only in `--output` (folder mode 700, files mode 600), by default `~/audit/sqli-investigate/YYYYMMDD-HHMMSS`:

* `sqli-requests.tsv`: every attempt (time, address, method, HTTP code, size, family, referer, user agent, decoded URL, file read).
* `sqli-summary.txt`: most active addresses, answers, user agents, bans and the answers received after each ban.
* `sqli-bans.txt`: jail events and the state reported by `fail2ban-client status`.

## What the program does not do

* It never bans, unbans, restarts anything or changes a configuration.
* A 200 answer does **not** prove there was no injection: only the SQL queries executed in PostgreSQL can prove it.
* The `boolean` family is a heuristic: review `sqli-requests.tsv` before concluding.

## Configuration

`/etc/default/sqli-investigate.conf` then `~/.sqli-investigate.conf` (the last one read wins; the command line has priority). Example: `doc/en/sqli-investigate.conf.example`.
Keys: `ACCESS_LOG`, `FAIL2BAN_LOG`, `JAIL`, `LANGUAGE`, `NO_LOOKUP`, `ODOO_LOG`, `OUTPUT`, `TOP`.

## Why not collect-all-advise.sh

`collect-all-advise.sh` anonymises by default, reads only the details of 4xx codes, does not re-read the fail2ban jail and does not see the
SQL requests themselves. This program answers the investigation questions: who tried what, when, with which answer, and what happened
after the ban.
