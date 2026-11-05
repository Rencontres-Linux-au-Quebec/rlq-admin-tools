# system-hardening.sh - security updates, audit and file integrity of the system

Hardening of the operating system itself, wherever it runs: a **Proxmox VE 9 host** (Debian 13), a **virtual machine** (Ubuntu 20.04 and later, Debian 12 and later) or an **LXC container** (Debian 12 and later). Like `nginx-hardening.sh`, it **only checks** by default; `--update` applies.

```bash
system-hardening.sh                  # check only, changes nothing
sudo system-hardening.sh --update    # apply (packages, configuration, rules, AIDE baseline, daily timer)
sudo system-hardening.sh --baseline-update   # after wanted changes (updates, new Odoo modules): new AIDE baseline
system-hardening.sh --notify         # the daily summary, now
sudo system-hardening.sh --rollback  # remove the files written by --update (packages stay)
```

## What it sets up

1. **unattended-upgrades**: the security updates of the distribution are applied every day (Debian Security, Ubuntu security and ESM). The lists of `50unattended-upgrades` are cleared first, so nothing else is upgraded by itself. **No automatic reboot** by default (`AUTOMATIC_REBOOT=no`): the reboot stops Odoo and the BigBlueButton meetings; the program says when a reboot is pending (`/var/run/reboot-required`, or a newer kernel installed than the one running). On a Proxmox host, only the Debian security updates are applied: the Proxmox packages are updated by hand (`apt full-upgrade`).
2. **auditd** (not in an LXC container, see below): rules tagged `rlq-*` - `rlq-sudo` (sudoers), `rlq-sudo-exec` (each `sudo` run by a real user), `rlq-ssh-keys` (`.ssh` of root and of each user), `rlq-sshd`, `rlq-cron`, `rlq-identity` (passwd, shadow, group), `rlq-pam`, `rlq-preload` (`/etc/ld.so.preload`), `rlq-systemd` (units), `rlq-apt` (package sources). Rather than all of `/etc` (thousands of harmless changes), the sensitive parts are watched; AIDE covers the integrity of the whole `/etc`. To read the events: `ausearch -k rlq-ssh-keys -i`.
3. **AIDE**: file integrity. The folders that change all the time are excluded (logs, caches, PostgreSQL, Docker, BigBlueButton recordings, Odoo filestore and the `data_dir` of each Odoo configuration found, Proxmox storage and `/etc/pve`); `AIDE_EXCLUDE` adds others. The baseline is created once (5 to 30 minutes), then checked every day by the distribution (`dailyaidecheck.timer` or `/etc/cron.daily/aide`).
4. **Daily summary by e-mail**: `system-hardening-notify.timer` runs `--notify` every day (`NOTIFY_TIME`, 07:30 by default). The mail goes through the mail settings of the suite (`/etc/default/nginx-tools-mail.conf`, set up by `nginx-hardening.sh --update --mail-setup`): no local mail server is needed. A mail is sent only when something needs attention (security updates installed, reboot pending, AIDE differences, sensitive audit events), or every day with `NOTIFY_ALWAYS=yes`.

## LXC containers and the Proxmox host

The kernel audit cannot run in an unprivileged LXC container: the kernel belongs to the host. In a container, the program sets up unattended-upgrades, AIDE and the daily summary, and says that the audit is done on the host. On the **Proxmox host**, `--update` also writes watches for the sensitive files of each **running** container (seen in `/var/lib/lxc/ID/rootfs`): sudoers, `.ssh`, cron, passwd, shadow, sshd. After a container is restarted, run `--update` again on the host so that the watches follow its new mount (`AUDIT_WATCH_CONTAINERS=no` to leave the containers out).

## Files written

Only files of its own, removed by `--rollback`: `/etc/apt/apt.conf.d/52rlq-unattended-upgrades`, `/etc/audit/rules.d/60-rlq-hardening.rules`, `/etc/aide/aide.conf.d/99_rlq_exclusions`, `/etc/systemd/system/system-hardening-notify.service` and `.timer`. No file of the distribution is modified. The packages (`unattended-upgrades`, `auditd`, `aide`) and the AIDE database stay after `--rollback`.

## Options
{{HELP}}
