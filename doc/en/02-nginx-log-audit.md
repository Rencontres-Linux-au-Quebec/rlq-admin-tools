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

`--investigate IP` starts with the **Bans** section: current state (firewall rule, fail2ban jails with start and end, CrowdSec list) and chronological history (journal of manual bans and `fail2ban.log` with its rotations), then, for each jail involved, its reason and what the address did (refused pages from `blocked-probes.log`, requests to the catch-all sensor...). An address blocked only by fail2ban or by the CrowdSec list does not appear in `--unban-check`, which handles manual bans only.

The **rented server** clue is checked when the reverse DNS names a hosting provider (AWS, OVH, Hetzner...); with `--investigate`, it is also checked when the **owner of the address block** (RDAP) is one, even if the reverse DNS does not show it (example: Vultr behind an unrelated name). The list of **Odoo accounts active** during the requests is searched only when the address asked for a page that needs a session (login, back office, customer account, chat): Odoo does not record the IP address of sessions, and for a robot that only reads public pages this time coincidence would designate members wrongly. Logins found in the Odoo journal for the address itself are always shown.

Refusals produced by our nginx rules are logged to `blocked-probes.log`, not to the site logs; investigations and evidence read it too ("Requests REFUSED by nginx"), otherwise a banned address would look as if it had made no request.

## Reviewing manual bans every day (`--unban-check`)

`--unban-check` (run as root) re-evaluates each manual ban with the current rules and proposes lifting the unjustified ones. Its verdicts:

- **justified**: at least one strong sign (sensitive files, errors in bulk, fake search engine, catch-all sensor) or repeated refusals in `blocked-probes.log`: keep it;
- **to check**: a single burst of pages and no strong sign: a browser or a monitoring tool can do that. Nothing is lifted by this verdict; read the requests and decide;
- **inconsistent**: the address changed during the investigation: no verdict, run `--investigate` again;
- **without trace**: no request left in the logs: the ban history (fail2ban jails, ban log) is shown.

After the list, the section **AUTRES POINTS A RE-VERIFIER** runs read-only checks and prints the command for each: team addresses among the bans, fail2ban jails, addresses refused by nginx that also received normal pages (possible false positive), logs used by the checks, and the commands to run by hand for each address to check. Its sections 1 to 5 can be copied as they are for a review.

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
