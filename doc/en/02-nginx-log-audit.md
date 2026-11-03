# nginx-log-audit.sh - nginx log report, investigations, bans

Reads the nginx access logs (the site log of `dev`, `lab` or `prod`; default: the detected profile) and produces a numbered report: robots, refusals, attacks, sensitive-file probes, bursts, parallel requests, rotated identities, followed by a proposal to ban offenders. It keeps a reading position, so each run analyses **what is new** (`--init` re-reads the active file, `--init-all` the whole history with rotations).

```bash
nginx-log-audit.sh prod                    # report, then offer bans
nginx-log-audit.sh prod --last 24 --no-prompt
nginx-log-audit.sh --investigate 203.0.113.7   # whole-history investigation + RDAP owner of the block
nginx-log-audit.sh --evidence 203.0.113.7      # evidence for/against a ban, read-only
sudo nginx-log-audit.sh --ban 203.0.113.7      # evidence shown, justification and confirmation asked (--yes to skip)
sudo nginx-log-audit.sh --ban 203.0.113.7 --yes --reason ".env scanner"   # justification given in advance
sudo nginx-log-audit.sh --ban-history          # journal of manual bans: date, time, justification, origin
nginx-log-audit.sh --export-bans > bans.txt ; nginx-log-audit.sh --import-bans bans.txt
nginx-log-audit.sh --stats --details       # traffic statistics: codes, IPs, user agents, devices
```

## How a ban is decided

Clues are counted per address: sensitive-path probing, page bursts (`--page-burst`: distinct pages in 10 s), parallel dynamic requests in the same second (`--parallel-threshold`, section 11), many robot identities from one address (`--ua-rotation-threshold`). A ban is *suggested* from `--ban-threshold` clues (default 3). Addresses in the white list or in places marked `[protected]` are never proposed. Manual bans are re-evaluated by `--unban-check` (lifting is suggested if no longer justified). When more than 5 IPs are to be lifted, a summary of those IPs is printed after the final tally.

## When and why an address was banned

Every `--ban` and `--unban` records in `~/.local/state/nginx-log-audit/bans.tsv` the date, the time, the **justification** and the origin (account and program: command line, `web-monitor.py`, `app-log-live.py`, report question...). The justification is asked at the keyboard (editable proposal: the evidence); `--reason TEXT` gives it in advance; with `--yes` and no `--reason`, it is recorded as "automatic". To justify an older ban after the fact: `--ban IP --reason "..."` (the ban date does not change).

`--unban IP` lifts **every** ban of the address, with no other command to run: the manual firewall rule, each fail2ban jail that holds it (found by the program) and the CrowdSec list (the address is removed from the ipset and added to `/etc/default/sync-crowdsec-blocklist.allow`, otherwise the next synchronisation would block it again). It first shows what it found, asks for a confirmation and a justification, then records one lift in the journal with the sources lifted. A jail can ban it again if it does the same again. `--unban-check` and `--unban-expired`, which judge the manual ban, lift that one only.

`--investigate IP` starts with the **Bans** section: current state (firewall rule, fail2ban jails with start and end, CrowdSec list) and chronological history (journal of manual bans and `fail2ban.log` with its rotations), then, for each jail involved, its reason and what the address did (refused pages from `blocked-probes.log`, requests to the catch-all sensor...). An address blocked only by fail2ban or by the CrowdSec list does not appear in `--unban-check`, which handles manual bans only.

The **rented server** clue is checked when the reverse DNS names a hosting provider (AWS, OVH, Hetzner...); with `--investigate`, it is also checked when the **owner of the address block** (RDAP) is one, even if the reverse DNS does not show it (example: Vultr behind an unrelated name). The list of **Odoo accounts active** during the requests is searched only when the address asked for a page that needs a session (login, back office, customer account, chat): Odoo does not record the IP address of sessions, and for a robot that only reads public pages this time coincidence would designate members wrongly. Logins found in the Odoo journal for the address itself are always shown.

Refusals produced by our nginx rules are logged to `blocked-probes.log`, not to the site logs; investigations and evidence read it too ("Requests REFUSED by nginx"), otherwise a banned address would look as if it had made no request.

`--unban-low-score` (2.85) runs `--investigate` on EVERY banned address (sub-process: the same code, the same logs including `blocked-probes.log`, the same RDAP, the same verdict engine): the score and the verdict in the table are those of `--investigate`, word for word. An address is lifted only if the verdict is "LEVER LE BANNISSEMENT" (otherwise it stays banned, even with `--yes`). `--unban-check` follows the same logic: it no longer has a verdict of its own (before, it gave 0/7 and "lift" where `--investigate` gave 3/7 and "BANNIR"). An SQL injection in the logs keeps a ban in all three commands. The line `RÉSUMÉ|ip|verdict|reason|bans|score` now carries the score as 6th field. Since 2.87, addresses whose verdict is "BANNIR" (for instance banned only temporarily by fail2ban) get a question "Bannir durablement ... [o/n]" (never automatic: with `--yes` or without a terminal only the `--ban IP` command is printed). The lift and ban questions require o or n (no default answer, Ctrl-C = no). Since 2.88, the logs (fail2ban, catch-all sensor, nginx refusals, site) and the Odoo logins are read ONCE for all the addresses, then the investigations run in parallel (4 at most; variable `NGINX_TOOLS_JOBS=N` to change it). The verdict does not change. Since 2.89, the full result of `--investigate` for the address is shown right above each question (lift or ban). Since 2.90, the suspicious URLs that may have caused the ban (nginx refusals, sensitive site pages, catch-all sensor) are listed under the result, to confirm the verdict. Since 2.91, two clues add to the score: the systematic sweep (at least 30 query variants of one page, for example every combination of the `/event` tags, or 100 distinct URLs repeated under several language prefixes) and the incomplete browser User-Agent (AppleWebKit without "KHTML, like Gecko"). A sweep is never proposed for a lift. The investigation also says whether an Odoo account logged in FROM the address (Odoo journal); the list of accounts active at the same time is shown only when it has 5 accounts or fewer.

Since 2.84, the analysis reports, as information only (no hostility point), 10 or more requests to `/web/reset_password` or `/web/signup`: the logs do not tell a form shown from a form sent, and a robot that follows the links of the login page reads them without submitting anything.

An address blocked **only** by the CrowdSec community list gets the verdict "LAISSER À CROWDSEC" (2.82), with no lift command: the list comes from other servers, and the absence of a local trace does not clear it. `--unban` also removes the CrowdSec list (permanent exception in `sync-crowdsec-blocklist.allow`); the lift recommendation for a manual ban warns about it when CrowdSec blocks too.

## Verdict and recommendation of `--investigate`

`--investigate` ends with **ANALYSIS AND RECOMMENDATION**: it re-reads the investigation as a person would and gives one verdict, its reasons and the command to run.

| Verdict | When |
|---|---|
| DO NOT BAN / LIFT THE BAN | protected address (white list, protected place), verified search engine, logged-in Odoo account, CDN node |
| BAN / KEEP THE BAN | strong sign (sensitive files, mass errors, fake engine, catch-all sensor) or score at the threshold with a sign of hostility; the duration by origin is given |
| LEAVE IT TO FAIL2BAN | strong sign, but score under the threshold: a firewall ban would need an exception |
| REFUSE THE ROBOT BY ITS NAME | no sign of hostility, but the robot gives its name in its User-Agent ("CareerScout/1.0", "webzio (+https://...)") and `bot_blocker.conf` does not refuse it: refusing it by name follows the robot when it changes address |
| LIFT THE BAN | banned address with no sign of hostility: fail2ban catches a new burst on its own |
| NO ACTION | nothing to report |

Notes are added: name already refused in `bot_blocker.conf`, probable nature of the requests (job offers, RSS feeds, forms), **type of address** (VPN, Tor exit, relay, hosting provider, from the block owner and the official list of Tor exits, cached one day), access provider address, current fail2ban and CrowdSec bans. The country is not a criterion: it is the server's, not the person's. When the RDAP organisation says nothing ("Admin"), the network name is shown instead.

Several addresses at once: `nginx-log-audit.sh --investigate 203.0.113.7 198.51.100.4` (or `203.0.113.7,198.51.100.4`). Each address is investigated in turn, then a **summary** gives the verdict of each and the commands to run (`--ban`, `--unban`), which check again and ask for confirmation.

## Reviewing manual bans every day (`--unban-check`)

`--unban-check` (run as root) re-evaluates each manual ban with the current rules and proposes lifting the unjustified ones. Its verdicts:

- **justified**: at least one strong sign (sensitive files, errors in bulk, fake search engine, catch-all sensor) or repeated refusals in `blocked-probes.log`: keep it;
- **to check**: a single burst of pages and no strong sign: a browser or a monitoring tool can do that. Nothing is lifted by this verdict; read the requests and decide;
- **inconsistent**: the address changed during the investigation: no verdict, run `--investigate` again;
- **without trace**: no request left in the logs: the ban history (fail2ban jails, ban log) is shown.

After the list, the section **AUTRES POINTS A RE-VERIFIER** runs read-only checks and prints the command for each: team addresses among the bans, fail2ban jails, addresses refused by nginx that also received normal pages (possible false positive), logs used by the checks, and the commands to run by hand for each address to check. Its sections 1 to 5 can be copied as they are for a review.

Section **6** (2.80): the program itself runs `--investigate` for each address of section 5 (20 at most, variable `UNBAN_CHECK_INVESTIGATIONS`) and shows only its block **ANALYSIS AND RECOMMENDATION** (verdict, reasons, command), then a summary and the `--ban` or `--unban` commands to run. The full report of an address: the command of section 5.

To run it every morning, as root:

```
0 7 * * * root /root/scripts/nginx-log-audit.sh prod --unban-check --no-prompt
```

## Duration of bans (expiry)

A firewall ban is no longer permanent: an address changes hands over time (a cloud instance goes to another customer, a subscriber line to another subscriber). Its duration depends on the **origin** of the address, decided when banning:

| Origin | Recognized by | Key (option) | Default |
|---|---|---|---|
| hosting provider, cloud | reverse DNS (AWS, OVH, Vultr...) or owner of the block (RDAP) | `BAN_DAYS_HOSTING` (`--ban-days-hosting`) | 365 days |
| access provider | reverse DNS of a subscriber line (dsl, cable, pool, dyn..., or the address written in the name) | `BAN_DAYS_ISP` (`--ban-days-isp`) | 90 days |
| unknown | neither | `BAN_DAYS_OTHER` (`--ban-days-other`) | 365 days |

`0` = no expiry. `--ban IP --ban-days N` sets the duration of that ban only, whatever the origin. The expiry date and the origin are written in `bans.tsv` (columns 6 and 7) and shown by `--investigate` and `--ban-history`.

`--unban-expired` (root) shows each manual ban with its date, its expiry date and the decision, then asks once (`--yes`: no question) and lifts those whose expiry date has passed, through `--unban` (journal and persistent rules updated). A ban recorded before version 2.73 gets an expiry date computed from its ban date, written once in the journal. A rule absent from the journal (set by hand) has no known date: it stays in place; `--ban IP --reason TEXT` sets its expiry from today.

`--ban` and `--unban-expired` write `/etc/cron.d/nginx-log-audit-expiry`, which runs `--unban-expired --yes` every day at 4:23 (log: `/var/log/nginx-log-audit-expiry.log`).

## Options
{{HELP}}

`--theme N` (2.86) chooses a color theme (0 = terminal colors, 1 dark background, 2 light background, 3 and 4: high contrast); `THEME` in the configuration; see `00-overview.md`.
