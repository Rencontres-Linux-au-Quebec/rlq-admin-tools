# app-log-live.py - real-time Odoo log and dashboard

Follows the Odoo journal (`journalctl -f`) and rewrites each line for humans: **who** (the Odoo user behind an address, from PostgreSQL, cached), **where** (country), whether the address is the team, a named place, the server itself (`127.0.0.1` = this program), or **banned** (`[banned: fail2ban|CrowdSec]`). Suspicious requests are shown in reverse video; slow requests (`--slow`, 5 s) and errors can beep (`--chime`).

```bash
app-log-live.py                     # follow, with the recent history
app-log-live.py --level 5 --health 30      # dashboard level 5; health alert every 30 min if something is wrong
app-log-live.py --accentuate-group "Team"  # contacts of an Odoo tag in white bold on blue
app-log-live.py --modules-startup          # table of installed custom modules at start-up
app-log-live.py --summary --no-follow      # print the summary and leave
```

## Keys (press `?` for the menu)

* `Ctrl-G` dashboard (health, resources, address cache, languages, top 10 URLs, Odoo errors); `1`-`9` choose its level; `Ctrl-T` only what changed since the last display (the summary counts the requests per name of the DNS column, without the unidentified addresses); `Ctrl-C` stop and print the session summary (which includes the number of members of each `RLQ*` group).
* Switches changed on the fly: `a` accentuate group, `c` chime, `d`/`t` name column width, `e` exclude IPs, `H` health period, `i` hide IP, `q` hide the Odoo module lines (`--hide-addons`), `l` highlight words, `m` minimal, `M` installed modules table with sorting, `L` latest modules, `n` only not-found, `o` only lines containing a text, `r` copy-paste error report, `s` suspicious only, `T` periodic report, `v` verbose, `w` watch URLs, `C` save the changed settings to the configuration file.
* `S`/`I` latest survey / event registrations (30 days), `E` error detail, `D` site diagnostic (why the maintenance page appears), `G` members of each `RLQ*` group, `b` ban the recommended addresses.
* `--hide-addons` (key `q`): hides the INFO lines of the Odoo modules (`odoo.addons.*`: crons, websocket, fetchmail...). Never hidden: errors (WARNING, ERROR, CRITICAL, traces), e-mails being sent (`mail_mail`, `ir_mail_server`, "successfully sent") and generated files (`ir_actions_report`, PDF...). Pressing `q` again shows how many lines were hidden.

## Recording a test (R key)

To analyze a test of the site (an abandoned survey, a registration, a talk proposal...) without the noise:

1. Press **R** in the live stream: a label is asked (for example `survey-abandoned`, Enter = none).
2. Make the test. While recording, **REC** is shown in red at column `$COLUMNS - 4` of each line.
3. Press **R** again: the recording stops and the `.tar.xz` archive is created in the background. Its path is shown on the line « Archive to send for analysis ».

While recording, **N** marks the steps of the test: N asks for a description and starts a step, N again ends it (for example « registration », then « survey abandoned »). The steps (start, end, duration, description) are listed in `steps.txt` of the archive and in `records.log`. A step still open when the recording stops is closed at that moment.

The archive holds: `README.txt` (local and UTC times, missing sources), `records.log` (the lines of the test, without robots, static files, websockets or local probes), `stream-all.log` (every line, with its category), `raw/` (complete extracts of nginx, Odoo, fail2ban and the systemd journal over the window), `network/` (connections of the web and Odoo ports), `db/` (PostgreSQL activity, `ir_cron` locks, snapshots of the survey, registration, e-mail and page tables), `context/` (service and Odoo settings without secrets, modules).

IP addresses, e-mails, known names and tokens are replaced by stable pseudonyms before they are written. The database is only read, in read-only transactions.

**Recording requirements (1.100)**: the `psql` client (package `postgresql-client`) and access to the Odoo database are mandatory; without them the recording is refused with a message (the PostgreSQL samples show the writes and the locks). The program can run without root: PostgreSQL is then queried through `sudo -n -u postgres`, and the advanced commands (fail2ban-client, ipset, journalctl) through `sudo -n`. These sudo rules must be allowed without password for the account running the program. The archive also records the system context (root or not, operating system, tool versions).

Without a keyboard: `--record-test-log MIN` records MIN minutes from start-up, writes the archive, then exits. `--record-max MIN` (key `RECORD_MAX`, 60 by default and at most; 0 is refused) stops a recording by itself. `--steps-line` (key F) shows all the steps of the recording on one white line, updated at each step (screen only).

## Latency: is it the disk?

Every 30 seconds a light sampler reads the kernel counters (no command): processor, waiting time (PSI) for the disk / processor / memory - the *container's own* cgroup when running in an LXC container - , and the disks' % busy and wait per operation. Each Odoo request (SQL time + Python time of its journal line) is filed in the bin of its hour, "disk busy" or "disk calm". Press **Y** (or Ctrl-G at level 6 and more) after a few hours: the verdict says whether the disks slow the requests (SSD justified), only at times (startups, backups), or not at all (SATA enough), with the per-hour table at level 8. Inside a container the disk counters can be partial: run `host-perf-audit.py` on the Proxmox host for the real disks.

## Design rules worth knowing

* A slow lookup never holds back a fast one: fast path (this server, a known person, the team) makes no outside call; DNS, owner and country run in separate threads. Names of people depend only on PostgreSQL (read-only, cached).
* Odoo logs no session end: "connected" means active within `--idle` minutes.
* The event time comes from the log line, never from the machine time zone.
* Daily colored logs go to `/var/log/app-log-live/` (root) or `~/.local/state/app-log-live/` (mode 600, 30 days; `--log-dir`, `--log-keep-days`, `--no-log-file`).
* By default on a terminal, a log line wider than `$COLUMNS - 10` columns (`--truncate N`: N columns) is shortened to "start ... last two words", so the end of a long URL (and a `[banned: ...]` label) stays visible; `--no-truncate` shows whole lines. Menus and reports are never cut; the daily log keeps the whole lines.
* One log line out of 10 is underlined, to follow a line across a wide screen (`--underline N`, `UNDERLINE=N`; `--no-underline`: none). The `U` menu key asks for N; `C` saves the value into the configuration file, like the other settings.
* `--min` is on by default: no database name, no « werkzeug », no fetchmail lines except errors (`--no-min` or `MIN=no`: everything).
* Configuration values are written in English only: `yes` / `no` (French `oui` / `non` are still read, with a warning asking to replace them).
* By default on a terminal, IP addresses and e-mails are shown as stable pseudonyms (`IP-4f2a9c`, `usager-9c1e03@anonyme.invalid`); `--no-anonymize` shows the real values. Names of people stay; the daily log keeps everything. A pipe or another program reading the output always gets the real, whole lines.
* A sent e-mail is shown as "E-mail #N sent to NAME - « subject »", even when Odoo deleted it right after sending (auto_delete).
* "Who is connected now" gives each SSH account with its number of sessions (`ana x2, root x1`, sftp included); the RLQ* groups are shown on 4, 2 or 1 column(s) depending on the terminal width.
* Key **I**: registrations grouped by event, then by ticket, with **the survey of each ticket** (counts: confirmed, unfinished, without survey); an answer to another survey (last year's, a test, another ticket) is pointed out, never counted.
* A sent e-mail shows its recipient and subject: "E-mail #7573 sent to Ana Tremblay (a***n@...) - « subject » - registration ...".
* **Ctrl+C** during a program started from the menu (nginx-log-audit.sh, web-monitor.py...): one question only, at once.

## Time window, journalctl options and country filters (1.112)

* `-S` / `--since TIME` and `-U` / `--until TIME`: `YYYY-MM-DD [HH:MM[:SS]] [Z or +HH:MM]`, `HH:MM[:SS]` (today), `today`, `yesterday`, `now`, `@EPOCH`, or relative (`-2h`, `'-30 min'`, `'0.5 day'`, `'3 days ago'`). Local time, or UTC with `--utc`. A date alone covers the whole day (`--until` stops at the start of the next day). With the live stream, `--until` stops the program at that time.
* `--utc`: the times of the lines and the times given without a time zone are in UTC.
* `-n` / `--lines N`: alias of `--lines`, as in journalctl. `--no-hostname`: without the host name.
* `-g` / `--grep REGEX`: only the lines whose message matches. Case-insensitive unless REGEX has an uppercase letter (as journalctl).
* `--country CC,CC`: only the lines whose first address (the client) is in these countries. `--exclude-country CC,CC`: hides them. Two-letter codes, repeatable. An address of unknown country is hidden by `--country` and kept by `--exclude-country`.
* `--days` accepts fractions: `--days 0.1` = 2.4 hours of sign-in history.
* `-f` and `--no-pager` are accepted for journalctl compatibility (no effect).

Examples:

```bash
app-log-live.py -S '-2h' --utc -n 500          # last two hours, in UTC
app-log-live.py -S yesterday -U today -g error  # yesterday only, lines containing "error"
app-log-live.py --exclude-country US,CN         # hide the addresses of these countries
app-log-live.py --days 0.1 --no-follow          # sign-ins of the last 2.4 hours
```

## Status bar, refresh and print (1.113)

* **Status bar** (reverse video), after every N displayed lines (`--status-every N`, 100 by default; 0 = never): SQL injection attempts, 4xx and 5xx answers, banned addresses seen, slow requests (duration >= `--slow`) and the slowest one. The counters are cumulative since the last detailed report: **Ctrl-T** or **g** reset them. Colour: white = nothing to see; green = a little (4xx, a few slow requests); yellow = to look at (SQL injection, 5xx, banned address, many slow requests); red = investigate now (repeated injections, many 5xx or slow requests).
* **f** (refresh): the last lines of the buffer are displayed again with the current options (addresses, DNS, names, highlight, `--only`...). They are not counted again and not written again to the daily journal.
* **P** (print): the last lines of the buffer (`--buffer N`, 200 by default; 0 = none) are written to a file, colors kept (`less -R file`). The program asks for the number of lines and the file name. The file is created with mode 600: it holds addresses and names.
* **Y**: latency report (formerly the P key).

## Options
* **1.114 - status bar details**: the bar also names the three addresses with the most problem lines (`top IP`), only when addresses are displayed (`--show-ip`, or the **H** key); otherwise it says they are hidden. The first time the bar turns red, one beep and one red **ALERT** line are shown; the alert is given again only after **Ctrl-T** or **g**.
* **1.114 - configuration file**: `BUFFER=` (`--buffer`) and `STATUS_EVERY=` (`--status-every`) can be set in `/etc/default/app-log-live.conf` or `~/.app-log-live.conf`. The command line keeps priority.

{{HELP}}
