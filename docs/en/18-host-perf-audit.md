# host-perf-audit.py — what limits the performance of a Proxmox host

Run it **on the Proxmox host** (inside a container the real disks are not visible). It measures over a chosen duration — a minute to a whole day — then gives a verdict per resource, the answer to “are SSD disks justified?”, and the settings to change.

```bash
host-perf-audit.py                                  # one minute, one sample every 5 s
host-perf-audit.py --duration 4h                    # the busy hours: one sample every 60 s
host-perf-audit.py --duration 24h --csv /root/perf.csv   # a whole day, every sample in a spreadsheet file
host-perf-audit.py --apply                          # report, then the safe settings one by one
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
