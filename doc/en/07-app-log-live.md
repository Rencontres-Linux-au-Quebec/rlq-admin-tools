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
* Switches while running (1.170), current value shown in the `?` menu, saved by `W`: `J` --log-merge (nginx line and Odoo line together, with `x` --log-nginx), `B` --status-header, `C` --truncate (shortened or whole lines), `O` --utc, `Q` --slow (threshold of the slow requests, asked), `Z` --status-every (asked), `K` --no-ban-prompt, `y` --no-sitemap, `u` --hide-user-agent. The options that decide what is read (--since, --grep, --app, --log-dir...) are set at startup only; the menu names them.
* `z` (1.163) analysis of the problems raised, with probable causes and recommended solutions: see the section « Analysis of the problems raised » below.
* `S`/`I` latest survey / event registrations (30 days), `E` error detail, `D` site diagnostic (why the maintenance page appears), `G` members of each `RLQ*` group, `b` ban the recommended addresses (1.155: only those that `nginx-log-audit.sh --investigate` recommends too: each address is first checked by that program, the one that bans; the others are listed with its verdict).
* `--hide-addons` (key `q`): hides the INFO lines of the Odoo modules (`odoo.addons.*`: crons, websocket, fetchmail...), and those of `odoo.models.unlink` (records deleted) and `odoo.modules.registry` (cache invalidations). Never hidden: errors (WARNING, ERROR, CRITICAL, traces), e-mails being sent (`mail_mail`, `ir_mail_server`, "successfully sent") and generated files (`ir_actions_report`, PDF...). Pressing `q` again shows how many lines were hidden.

## Analysis of the problems raised (z key, 1.163)

Press **z** in the live stream: the program analyzes what the dashboard counted since its start and prints, for each problem, the evidence, the probable cause and what to do. You no longer need to copy the logs to have them explained.

1. **Details read in the logs**, only for the problems raised: the Odoo traceback that follows each ERROR / CRITICAL message (the Odoo logfile, otherwise the systemd journal a few seconds around its time: exception, module of the last frame) and, for the URLs that answer 4xx, the status codes, the referers (the page that holds the dead link) and the User-Agents of the nginx access logs.
2. **Rules** (apps/_advisor.py): 5xx errors (Odoo did not answer, or an exception in a module), 404 on pages of sitemap.xml (real page gone, truncated link, or false alarm of a language code alone that the site does not offer), repeated 404 outside the sitemap (unpublished product, dead internal link), `sitemap.xml` refused or missing, known Odoo messages (`.map` source maps, "called ignoring args", expired live chat guest, "Exception during request handling" explained by its traceback), concurrent update failures, failed e-mails (SMTP codes 452, 503, 550), slow requests (SQL, Python or cold cache), addresses to ban (key `b`: the white list and the score of nginx-log-audit.sh decide, CDN relays are never proposed), account forms, latency measured on too few requests.
3. **Continuous improvement**: each analysis is kept in `advisor-history.json` (state folder of the program: `APP_LOG_LIVE_STATE_DIR`, otherwise `/var/lib/app-log-live`, otherwise `~/.cache/app-log-live`; mode 600; 200 analyses and 90 days at most). Each problem is tagged **[new]**, **[recurring: N analyses in a row]**, **[back]** or **[no new occurrence since the last analysis]**; the problems that disappeared are listed as **resolved**, and the problems seen most often come first in "to fix first".

Severity: ✖ problem, ⚠ to look at, ℹ information. Nothing is modified on the server: the logs are only read, and the only file written is the history.

1.164: in the comparison with sitemap.xml (health, `--log-chk-sitemap`), a first segment of two letters is removed as a language prefix only when it is a code of ISO 639-1 (`/fr`, `/es`, `/fr_CA`...). Before, `/ev` (a truncated `/event`) was compared as the home page and counted as a 404 "in sitemap.xml".

### Over several weeks: --advise (1.165)

```
sudo app-log-live.py --advise          # the last 14 days
sudo app-log-live.py --advise 30       # the last 30 days
sudo app-log-live.py --advise --since 2026-10-01 --until 2026-10-31
```

The same analysis as the z key, without the live stream: the logs of the window are read without being shown (this can take a few minutes for several weeks), then the analysis is printed. The rotated nginx access logs of the window (`.1`, `.2.gz`...) are read for the referers. Each run is kept in `advisor-history-advise.json` (separate from the history of the z key, whose windows are not comparable), so that two runs a week apart say what is new, recurring or resolved. With `--summary`, the session summary follows. 1.166: the window is read about 15 times faster (20,000 lines in 8 s instead of more than 2 minutes on the test machine) and with the lowest priority (nice 19, idle disk class), so the analysis never slows Odoo down: the lines are counted without being formatted or translated, and the names (DNS, RDAP, country) are looked up at the end only for the addresses the analysis shows. Without sudo, the systemd journal and `/var/lib/app-log-live` may not be readable.

1.168: while the window is read, the error output shows the progress: the share of the window already read, the date reached, the lines read per second and the time left (one line rewritten in place on a terminal, one line every 30 s otherwise), then each step of the analysis (names of the addresses, Odoo tracebacks, nginx logs, service journal, database, answer of the site, rules) with the time since the start.

### Details checked and corrections (1.167)

For each problem, the analysis now checks the facts itself instead of only pointing to a tool (read-only):

* **Slow requests**: the workers and limits of `odoo.conf` (`workers`, `max_cron_threads`, `limit_time_cpu`, `limit_time_real`, `limit_memory_*`), the processors and memory of the machine (those of the container), compared with the Odoo deployment guide ((2 x CPU) + 1 workers at most, about 325 MB each); the busiest hours; the requests that came in the 10 minutes after a start of Odoo (cold cache).
* **Odoo unreachable from nginx**: the lines of the nginx error log are no longer counted as Odoo errors nor as failed e-mails; they are grouped and compared with the starts and stops of the service (its journal) and its state now.
* **Odoo exceptions**: the exception of every occurrence (not only the last one), the module of the last frame; known causes (VAPID key of the push notifications, access rights, deleted records, memory, timeouts...).
* **5xx errors**: grouped by page, with the traceback logged at the same second and the addresses; a vulnerability scanner (quotes, brackets, « zqzz ») is recognized.
* **Failed e-mails**: the database decides (state of the mail queue, causes, outgoing servers): a count of the journal that the database does not confirm is shown as information.
* **404**: the answer of the site now, the event or product of the number in the address (published, archived, deleted), the web page and a similar one, a redirect already defined; the referers of the site itself (with or without www) are recognized.
* **Account forms**: forms really sent (POST) or only shown (GET), sign-up free or on invitation, portal accounts created in the window.

With **`--apply`** (with `--advise`, on a terminal), the corrections are offered one by one after the analysis, one question each: ban the addresses through `nginx-log-audit.sh --ban` (it investigates each address, checks the white list and its score, and asks its own confirmation), open `odoo-mail-retry.py` for the failed e-mails (it lists them and asks before resending), warm Odoo up with `odoo-warmup.py` after a restart. Nothing is done without a « yes », and `odoo.conf` is never modified.

## Dashboard: what 1.169 changes

* With `--log-merge`, the line of nginx and the line of Odoo of one request make one line; the Odoo times (SQL queries, SQL time, Python time) of that line are now counted: before, the slow requests, the latency and the most SQL queries of the dashboard only saw the Odoo lines that had not found their nginx partner (67 requests measured for 2,603 seen).
* The slow requests of the 10 minutes after the start of Odoo (cold cache) are shown but not counted in the health; the probes of this server (`app-health-check.py`) are named as such: they measured the slowness, they did not cause it. The state of the server "right now" is used to explain slow requests only if they are less than 5 minutes old.
* "Odoo unreachable from nginx" counts interruptions (errors less than 5 minutes apart): one short interruption (a restart) is "to look at", several or one longer than 15 minutes are a "problem", with the start of Odoo.
* "Automatic monitoring (web-monitor.py): last run N h ago" when the last run is more than 48 hours old: its timer is stopped or failing.
* Counts without plural markers: "requests: 4 · addresses: 1".

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

* **Status bar** (reverse video), after every N displayed lines (`--status-every N`, 100 by default; 0 = never): SQL injection attempts, 4xx and 5xx answers, banned addresses seen, slow requests (duration >= `--slow`) and the slowest one. The counters are cumulative since the last detailed report: **Ctrl-T** or **g** reset them. Colour: white = nothing to see; green = a little (4xx, a few slow requests); yellow = to look at (SQL injection, 5xx, banned address, many slow requests); red = investigate now (repeated injections, many 5xx or slow requests). 1.125: each figure has its own colour (green, yellow or red) according to its criticality, for example 5xx: 0 green, 1 to 4 yellow, 5 and more red. The bar is also shown once after the history, at startup (not with `--status-every 0`). 1.154: the line of column labels (HOUR, PROG, LVL, CC IP-BLOCK, HTTP, STA...) is shown again right after each status bar, aligned on the last request line; "CC IP-BLOCK" sits over the country code and the name (or the address), with or without `--min`.
* **f** (refresh): the last lines of the buffer are displayed again with the current options (addresses, DNS, names, highlight, `--only`...). They are not counted again and not written again to the daily journal.
* **P** (print): the last lines of the buffer (`--buffer N`, 200 by default; 0 = none) are written to a file, colors kept (`less -R file`). The program asks for the number of lines and the file name. The file is created with mode 600: it holds addresses and names.
* **Y**: latency report (formerly the P key).

## nginx logs in the same stream (1.116)

The access and error logs of the site (`ACCESS_LOGS` and `ERROR_LOGS` of the application profile, in `/var/log/nginx`) are read
with the application log. Their lines get the same prefix and the same columns as the Odoo lines (local date and time, host, program
`http`, level, country and address, name). They are hidden by default on an Odoo server.

- `--log-nginx` (or `LOG_NGINX=yes` in the configuration file) shows them from the start.
- `--log-merge` (1.123): the nginx line and the Odoo line of the SAME request (same URL and status, within 5 seconds) are shown as ONE line, with the SQL queries and the times of Odoo. Since 1.153, a 304 of nginx (it answered the browser's conditional request itself) merges with a 200 of Odoo, and a 499 of nginx (the client left before the answer) with any status of Odoo; the merged line keeps the status of nginx, the one the browser got. It needs `--log-nginx`; an nginx line still waiting for its Odoo line after 8 seconds is shown alone. Configuration key: `LOG_MERGE`.
- `--status-header` (1.123, 1.125): the time stays at the start of each line; the date (without the time) and the host name are shown at the start of the status bar (date and host of the last line). Configuration key: `STATUS_HEADER`.
- `--config-merge` (1.125): rewrites the configuration file read (the one given with `-c FILE`, otherwise the last one read) from the NEW default configuration (example of the current language), keeping the values set in the old file. The old file is first copied to `FILE.bak-YYYYMMDD-HHMMSS` (local time). The keys unknown to the program are listed and left out. The program then exits.
- Display (1.123): the level is written in 4 characters (`ERR`, `WARN`, `CRIT`, `DBUG`, `INFO`), the protocol as `H1.1`, and a shortened line is marked with `…`. 1.124: the status bar gives the 4xx and 5xx answers by code (403, 404, 500...).
- The key `x` shows or hides them on the fly, from the next line on (the menu `?` says whether they are shown). Hidden lines are not
  counted and not looked up. Lines read while they were hidden are not shown later.

```
app-log-live.py --log-nginx                      # live: Odoo and nginx together
app-log-live.py --log-nginx --no-follow -S '-1h' # the last hour of both, then stop
app-log-live.py --log-nginx -g ' 404 '           # the 404 answers of nginx and of Odoo
```

- The start message names the nginx files read, and whether they are shown.
- `-S`, `-U` and `-g` apply to the nginx lines too (the application lines are already filtered by journalctl).
- A nginx log that is silent does not hold back the Odoo lines: it is waited for `APP_LOG_MERGE_WAIT` seconds (2 by default),
  then it is not waited for again until it speaks.
- The merge is done by `apps/_logs_merge.py`, which can also be run alone (`--help`, `--version`).
- BigBlueButton: its nginx lines were already shown and stay so.

## Options
* **1.114 - status bar details**: the bar also names the three addresses with the most problem lines (`top IP`), only when addresses are displayed (`--show-ip`, or the **H** key); otherwise it says they are hidden. The first time the bar turns red, one beep and one red **ALERT** line are shown; the alert is given again only after **Ctrl-T** or **g**.
* **1.114 - configuration file**: `BUFFER=` (`--buffer`) and `STATUS_EVERY=` (`--status-every`) can be set in `/etc/default/app-log-live.conf` or `~/.app-log-live.conf`. The command line keeps priority.

* **1.156 - system column**: the User-Agent gives `AND`, `IOS`, `WIN`, `LIN` or `MAC`; without a system, the program that makes the request: `CUR` (curl), `PYT` (Python), `WGT` (wget), `GOL` (Go), `JAV` (Java), `PHP`, `NOD` (Node.js), `RUB` (Ruby), `PER` (Perl); `OTH` for any other User-Agent.

* **1.157 - account forms**: a request to `/web/reset_password` or `/web/signup` (with or without a language prefix) is shown in **red reverse video** only from the 4th request of the same address (1.174; one to three requests keep the normal style of the login pages). The summary (Ctrl-G, Ctrl-T, Ctrl-C) adds the line "Account forms": number of requests per address (first five) and per page. A robot that follows the links of the login page reads them without submitting anything; this mark shows an address that asks for them in bursts.

* **1.158 - errors only**: `--errors-only` (`ERRORS_ONLY`) or the `X` key (toggle) shows only the errors and the suspicious requests: HTTP code 400 and above, suspicious request, Odoo WARNING / ERROR / CRITICAL, traces, failed logins. Normal transactions (2xx, 3xx, INFO) are hidden. At startup (at least 3000 lines of history read) and each time `X` switches it on, the **last 100 errors** are shown first. The summary counts only what is displayed.

* **1.159 - robots**: the system column shows `BOT` (magenta) for a robot that gives its name in its User-Agent (Googlebot, Amazonbot, SemrushBot, NVIDIABOT, facebookexternalhit...), checked before the system; the programs `CUR`, `PYT`, `WGT`, `GOL`, `JAV`, `PHP`, `NOD`, `RUB`, `PER` are shown in **bold yellow** (script tool). A **403 produced by a refused robot** (list of `bot_blocker.conf`, `[BOT]`) is not critical: the URL is shown in yellow, without reverse video; a request for a sensitive file keeps its reverse video.

* **1.160 - startup and backslash**: the startup lines (nginx logs, Odoo service, sign-in history, modules PostgreSQL warning, colour legends, banned addresses, screen, daily log) are in the `?` key and no longer on screen; the line "Startup information: press ?" is removed. A request with a backslash (`register%5C` in nginx, `register\\` in Odoo) is seen as the same request and merges into one line.

* **1.161 - themes**: `--theme N` (0 to 4) or `THEME` in the configuration: every color is replaced by the nearest one that reads on the chosen background (see `00-overview.md`).

{{HELP}}

* **1.162 - Enter key and logged-in users**: while waiting for new lines, **Enter** prints the status bar with the date and time of the action (no legend, counters not reset). The bar counts SSH sessions like the reports (sshd processes and `who` together: it stayed at 0 when `who` gave no origin address) and adds "logged in (who) N (accounts)".
