# host-perf-audit.py - what limits the performance of a Proxmox host

Run it **on the Proxmox host** (inside a container the real disks are not visible). It measures over a chosen duration - a minute to a whole day - then gives a verdict per resource, the answer to "are SSD disks justified?", and the settings to change.

```bash
host-perf-audit.py                                  # one minute, one sample every 5 s
host-perf-audit.py --duration 4h                    # the busy hours: one sample every 60 s
host-perf-audit.py --duration 24h --csv /root/perf.csv   # a whole day, every sample in a spreadsheet file
host-perf-audit.py --apply                          # report, then the safe settings one by one
host-perf-audit.py --export-ai                      # report, then the report and the raw state of the host in a Markdown file to send for verification
```

## What is measured

* **Processor**: % busy, iowait, steal (time taken by another hypervisor), load, and the waiting time for a core (PSI *cpu*).
* **Memory**: available memory, swap, waiting time for memory (PSI *memory*: reclaim, swap), ZFS ARC size, maximum and hit ratio.
* **Disks**: per disk (HDD, SSD or NVMe, model): % of the time busy, operations and MB per second, wait per read and per write (95th percentile), and the waiting time of the whole host for the disks (PSI *io*: *some* = at least one task waited, *full* = all of them did). SMART health when `smartctl` is installed.
* **ZFS**: per pool, used %, fragmentation, health, scrub / resilver in progress, special / log / cache devices, `ashift`, the average waits since the pool was imported (synchronous writes included); dataset properties (compression, atime, sync, recordsize).
* **Network**: received / sent per interface, errors and drops.
* **Guests**: for each running container and VM (cgroup v2, named from `/etc/pve`): processor, memory, disk throughput and the waiting time for the disk *inside* the guest.

The program is light by design: a sample reads a few small files of `/proc` and `/sys` (no command), the program lowers its own priority (nice 10, idle I/O class), the few commands (`zpool`, `zfs`, `pveversion`, `smartctl`) run once, and the report prints the processor time the run cost. **Ctrl-C** during the measurement stops it and still gives the report on the samples already taken.

## Are SSD disks justified?

* **Yes** when the HDD are a measured bottleneck: tasks wait for the disk a large part of the time, or a disk is busy more than 85 % of the time (95th percentile) with slow operations. The report lists the cheaper steps first: a bigger ARC if RAM allows, a mirrored SSD *special* device (metadata and small blocks), an SSD *log* device (SLOG) for synchronous writes such as PostgreSQL commits, then SSD for the pool of the busiest guest.
* **Not yet** when the disks slow things down only at peaks: measure over a whole day including the backups.
* **No** when the disks are not a limit: the slowness of the first page loads after a restart is the cold cache, not the disk type.

## Settings

Each suggestion has a priority (HIGH / MEDIUM / LOW). With `--apply`, the **safe and reversible** ones are offered one by one (`--yes` without questions): ZFS `compression=lz4` and `atime=off` of a dataset, `zfs_arc_max` (now, in `/etc/modprobe.d/` and the initramfs), `vm.swappiness` (now and in `/etc/sysctl.d/`). Hardware advice and VM disk options (bus, `iothread`, cache, CPU type) are explained, never changed: they need a decision and a VM restart.

## Options
{{HELP}}

## Space, backups and export (1.10)

* **Space of the pools**: free space, snapshots, largest datasets, and what is stored directly in a parent dataset (for example `/var/lib/vz/dump`).
* **Container disk almost full**: named with its mount point and the `pct resize` command.
* **Backups (vzdump)**: number, size, retention, scheduled jobs and the hours of the backups of the last 3 days, to compare with the slow hours of the sites.
* **`--export-ai`**: writes the report and the raw state of the host to `/var/lib/host-perf-audit/export-ai-HOST-DATE.md` (mode 600, passwords hidden). Key `EXPORT_AI` in the configuration.

## Health, inside of the guests and alerts (1.12)

```bash
host-perf-audit.py --health --inside            # a check of a few seconds, without measurement
host-perf-audit.py --install-timer              # the same every hour, with an e-mail alert when something is new
```

* **`--health`**: SMART counters of each disk compared with the previous run (reallocated, pending, uncorrectable sectors), state and errors of the ZFS pools, RAID, kernel messages, space, backups. Exit code 0, 1 (to watch) or 2 (problem).
* **`--inside`**: looks inside each guest, read-only: `pct exec` for a container, the QEMU guest agent for a VM (`qm set ID --agent enabled=1`, `qemu-guest-agent` in the VM, then stop and start the VM). Docker containers that restart in a loop, failed services, a journal that overflows, full disks, the processes that write the most. No shared folder is needed.
* **`--notify`**: system journal and e-mail (SMTP settings of `app-health-check.py`, otherwise local mail to root), only when something is new, reminder after 24 hours.
* **Commands to run**: every report ends with the commands to copy, paste, and whose output is to be sent.

## Configuration of the containers and VMs (1.13)

At startup, the program checks the configuration of each guest (`/etc/pve`, read-only) and announces the **major issues**: a container mount point missing from the backups (`backup=1`), a disk with `cache=unsafe`, a guest without `onboot`, a guest in no backup job, more memory promised than the machine has. The whole list (to improve, notes) is at the end of the report, with the `pct set` / `qm set` commands to copy.

Since 1.14, each guest in order gets its `[OK]` line with what was verified, and the snapshots older than 60 days are listed with the room that deleting them frees (computed by `zfs destroy -n`, nothing destroyed) and the `pct delsnapshot` / `qm delsnapshot` commands.

## Commands run by the program (1.15)

At the end of the report and of `--health`, each command is marked **`[read]`** (the program runs it and shows its output in the section "COLLECTED") or **`[change]`** (it modifies something: the program offers it one by one and runs it only after "y", as root, in a terminal). `--no-collect` only lists the commands. Backups placed in a sub-folder that Proxmox does not see (its retention never applies there) are reported, with the list of the files to delete beyond `keep-last` and the room freed.

## Command in the guests (1.17)

```bash
host-perf-audit.py --guest-run --guests 101,104,105,433
```

Runs `/opt/rlq-admin-tools/nginx-hardening.sh --update` (or `--guest-command`) in each guest, one after the other, after checking that the program exists there and after a confirmation (`--yes`: without the question). The outputs are kept in `/var/lib/host-perf-audit/guest-runs/DATE/`, with a `report.md` to send for analysis. Keys `GUESTS` and `GUEST_COMMAND` in the configuration.
