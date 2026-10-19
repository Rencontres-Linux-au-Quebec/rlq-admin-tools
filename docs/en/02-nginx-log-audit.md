# nginx-log-audit.sh — nginx log report, investigations, bans

Reads the nginx access logs (the site log of `dev`, `lab` or `prod`; default: the detected profile) and produces a numbered report: robots, refusals, attacks, sensitive-file probes, bursts, parallel requests, rotated identities, followed by a proposal to ban offenders. It keeps a reading position, so each run analyses **what is new** (`--init` re-reads the active file, `--init-all` the whole history with rotations).

```bash
nginx-log-audit.sh prod                    # report, then offer bans
nginx-log-audit.sh prod --last 24 --no-prompt
nginx-log-audit.sh --investigate 203.0.113.7   # whole-history investigation + RDAP owner of the block
nginx-log-audit.sh --evidence 203.0.113.7      # evidence for/against a ban, read-only
sudo nginx-log-audit.sh --ban 203.0.113.7      # evidence shown, confirmation asked (--yes to skip)
nginx-log-audit.sh --export-bans > bans.txt ; nginx-log-audit.sh --import-bans bans.txt
nginx-log-audit.sh --stats --details       # traffic statistics: codes, IPs, user agents, devices
```

## How a ban is decided

Clues are counted per address: sensitive-path probing, page bursts (`--page-burst`: distinct pages in 10 s), parallel dynamic requests in the same second (`--parallel-threshold`, section 11), many robot identities from one address (`--ua-rotation-threshold`). A ban is *suggested* from `--ban-threshold` clues (default 3). Addresses in the white list or in places marked `[protected]` are never proposed. Manual bans are re-evaluated by `--unban-check` (lifting is suggested if no longer justified).

Refusals produced by our nginx rules are logged to `blocked-probes.log`, not to the site logs; investigations and evidence read it too (“Requests REFUSED by nginx”), otherwise a banned address would look as if it had made no request.

## Options
{{HELP}}
