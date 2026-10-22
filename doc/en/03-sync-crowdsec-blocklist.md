# sync-crowdsec-blocklist.sh - CrowdSec community blocklist at the firewall

Downloads the CrowdSec community list and loads it into **two ipsets** (`crowdsec-blocklist-v4`, `-v6`) dropped by the firewall (iptables rules or a `ufw` hook). It does not need the CrowdSec agent.

* **Atomic loading** with `ipset swap`: the set is never empty or partial; nginx is not reloaded.
* **Protection against a truncated list**: `--min-ips` refuses a list smaller than expected; the previous set stays in place.
* **Trusted addresses are never blocked** (white list, `[protected]` places).
* Run from cron (`--install-cron --cron-hours N`) and survive `ufw reload` with `--ufw-hook`.

```bash
sync-crowdsec-blocklist.sh --dry-run          # download and analyse, change nothing
sync-crowdsec-blocklist.sh                    # synchronise now
sync-crowdsec-blocklist.sh --install-cron --cron-hours 6 --ufw-hook
sync-crowdsec-blocklist.sh --status           # last sync, current failure, size, protected IPs
sync-crowdsec-blocklist.sh --blocked --top 20 # addresses actually dropped (firewall counters)
sync-crowdsec-blocklist.sh --uninstall        # remove cron, rules and ipsets
```

`app-log-live.py` marks addresses present in these sets as `[banned: CrowdSec]` (a `nomatch` entry is an exception).

## Options
{{HELP}}
