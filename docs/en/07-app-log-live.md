# app-log-live.py — real-time Odoo log and dashboard

Follows the Odoo journal (`journalctl -f`) and rewrites each line for humans: **who** (the Odoo user behind an address, from PostgreSQL, cached), **where** (country), whether the address is the team, a named place, the server itself (`127.0.0.1` = this program), or **banned** (`[banned: fail2ban|CrowdSec]`). Suspicious requests are shown in reverse video; slow requests (`--slow`, 5 s) and errors can beep (`--chime`).

```bash
app-log-live.py                     # follow, with the recent history
app-log-live.py --level 5 --health 30      # dashboard level 5; health alert every 30 min if something is wrong
app-log-live.py --accentuate-group "Team"  # contacts of an Odoo tag in white bold on blue
app-log-live.py --modules-startup          # table of installed custom modules at start-up
app-log-live.py --summary --no-follow      # print the summary and leave
```

## Keys (press `?` for the menu)

* `Ctrl-G` dashboard (health, resources, address cache, languages, top 10 URLs, Odoo errors); `1`–`9` choose its level; `Ctrl-T` only what changed since the last display; `Ctrl-C` stop and print the session summary (which includes the number of members of each `RLQ*` group).
* Switches changed on the fly: `a` accentuate group, `c` chime, `d`/`t` name column width, `e` exclude IPs, `H` health period, `i` hide IP, `l` highlight words, `m` minimal, `M` installed modules table with sorting, `L` latest modules, `n` only not-found, `o` only lines containing a text, `r` copy-paste error report, `s` suspicious only, `T` periodic report, `v` verbose, `w` watch URLs, `C` save the changed settings to the configuration file.
* `S`/`I` latest survey / event registrations (30 days), `E` error detail, `D` site diagnostic (why the maintenance page appears), `G` members of each `RLQ*` group, `b` ban the recommended addresses.

## Latency: is it the disk?

Every 30 seconds a light sampler reads the kernel counters (no command): processor, waiting time (PSI) for the disk / processor / memory — the *container's own* cgroup when running in an LXC container —, and the disks' % busy and wait per operation. Each Odoo request (SQL time + Python time of its journal line) is filed in the bin of its hour, “disk busy” or “disk calm”. Press **P** (or Ctrl-G at level 6 and more) after a few hours: the verdict says whether the disks slow the requests (SSD justified), only at times (startups, backups), or not at all (SATA enough), with the per-hour table at level 8. Inside a container the disk counters can be partial: run `host-perf-audit.py` on the Proxmox host for the real disks.

## Design rules worth knowing

* A slow lookup never holds back a fast one: fast path (this server, a known person, the team) makes no outside call; DNS, owner and country run in separate threads. Names of people depend only on PostgreSQL (read-only, cached).
* Odoo logs no session end: “connected” means active within `--idle` minutes.
* The event time comes from the log line, never from the machine time zone.
* Daily colored logs go to `/var/log/app-log-live/` (root) or `~/.local/state/app-log-live/` (mode 600, 30 days; `--log-dir`, `--log-keep-days`, `--no-log-file`).
* By default on a terminal, a log line wider than `$COLUMNS - 10` columns (`--truncate N`: N columns) is shortened to “start ... last two words”, so the end of a long URL (and a `[banned: …]` label) stays visible; `--no-truncate` shows whole lines. Menus and reports are never cut; the daily log keeps the whole lines.
* One log line out of 5 is underlined, to follow a line across a wide screen (`--no-underline`: none).
* By default on a terminal, IP addresses and e-mails are shown as stable pseudonyms (`IP-4f2a9c`, `usager-9c1e03@anonyme.invalid`); `--no-anonymize` shows the real values. Names of people stay; the daily log keeps everything. A pipe or another program reading the output always gets the real, whole lines.
* A sent e-mail is shown as “E-mail #N sent to NAME — « subject »”, even when Odoo deleted it right after sending (auto_delete).
* “Who is connected now” gives each SSH account with its number of sessions (`ana ×2, root ×1`, sftp included); the RLQ* groups are shown on 4, 2 or 1 column(s) depending on the terminal width.
* Key **I**: registrations grouped by event, then by ticket, with **the survey of each ticket** (counts: confirmed, unfinished, without survey); an answer to another survey (last year's, a test, another ticket) is pointed out, never counted.
* A sent e-mail shows its recipient and subject: “E-mail #7573 sent to Ana Tremblay (a***n@…) — « subject » — registration …”.
* **Ctrl+C** during a program started from the menu (nginx-log-audit.sh, web-monitor.py…): one question only, at once.

## Options
{{HELP}}
