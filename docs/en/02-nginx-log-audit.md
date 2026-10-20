# nginx-log-audit.sh — nginx log report, investigations, bans

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

Clues are counted per address: sensitive-path probing, page bursts (`--page-burst`: distinct pages in 10 s), parallel dynamic requests in the same second (`--parallel-threshold`, section 11), many robot identities from one address (`--ua-rotation-threshold`). A ban is *suggested* from `--ban-threshold` clues (default 3). Addresses in the white list or in places marked `[protected]` are never proposed. Manual bans are re-evaluated by `--unban-check` (lifting is suggested if no longer justified).

## When and why an address was banned

Every `--ban` and `--unban` records in `~/.local/state/nginx-log-audit/bans.tsv` the date, the time, the **justification** and the origin (account and program: command line, `web-monitor.py`, `app-log-live.py`, report question…). The justification is asked at the keyboard (editable proposal: the evidence); `--reason TEXT` gives it in advance; with `--yes` and no `--reason`, it is recorded as "automatic". To justify an older ban after the fact: `--ban IP --reason "…"` (the ban date does not change).

`--investigate IP` starts with the **Bans** section: current state (firewall rule, fail2ban jails with start and end, CrowdSec list) and chronological history (journal of manual bans and `fail2ban.log` with its rotations), then, for each jail involved, its reason and what the address did (refused pages from `blocked-probes.log`, requests to the catch-all sensor…). An address blocked only by fail2ban or by the CrowdSec list does not appear in `--unban-check`, which handles manual bans only.

Refusals produced by our nginx rules are logged to `blocked-probes.log`, not to the site logs; investigations and evidence read it too (“Requests REFUSED by nginx”), otherwise a banned address would look as if it had made no request.

## Options
{{HELP}}
