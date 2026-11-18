#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# host-perf-audit.py - WHAT LIMITS THE PERFORMANCE of a hypervisor (Proxmox VE) or of any Linux server: processor, memory, disks, network, ZFS,
# measured over a chosen duration (a minute to several hours), then a verdict per resource, the answer to "are SSD disks justified?" and the
# settings to change (ZFS, ARC, swappiness...). Run it ON THE PROXMOX HOST: inside a container, the real disks are not visible.
#   * Light by design: one sample every INTERVAL seconds reads a few small files of /proc and /sys (apps/_sysperf.py, no external command); the
#     program lowers its own priority (nice 10, idle I/O class) and reports what it cost. The few commands (zpool, zfs, pveversion, smartctl) run ONCE.
#   * Per guest (LXC containers and VMs): processor, memory, disk throughput and disk waiting time, from their cgroup (cgroup v2), named from
#     /etc/pve (hostname / name).
#   * Ctrl-C during the measurement: the report is still produced with the samples already taken.
#   * --apply: the SAFE and reversible settings (ZFS atime, compression and recordsize of a dataset, ARC maximum, vm.swappiness) are offered one by one with
#     confirmation; the others (hardware, VM disk options) are explained, never changed.
# Configuration (common rule): /etc/default/host-perf-audit.conf THEN ~/.host-perf-audit.conf (the last one wins; keys CSV, DURATION, EXPORT_AI, GUEST_COMMAND, GUESTS, INSIDE, INTERVAL, IO_LATENCY, LANGUAGE,
# NO_GUESTS, SYNC_GIT, SYNC_SOURCE, TOP, VERBOSE); -c/--config: that file ALONE; the command line takes priority.
#
#
# Usage:
#   host-perf-audit.py                         one minute of measurement (sample every 5 s), then the report
#   host-perf-audit.py --duration 4h           four hours (sample every 60 s): the daily peaks are included
#   host-perf-audit.py --duration 30m --csv /root/perf.csv   samples also written to a CSV file (spreadsheet)
#   host-perf-audit.py --apply                 report, then the safe settings offered one by one
#   host-perf-audit.py --duration 1h --io-latency   the processes that waited for the disks and the ZFS operations slower than 20 ms, file by file
#   host-perf-audit.py --export-ai             report, then the report and the raw state of the host in a Markdown file to send for verification
#   host-perf-audit.py --health --inside       quick check without measurement: disks (SMART counters), pools, backups, and the inside of each guest
#   host-perf-audit.py --install-timer         that check every hour, with an alert by e-mail when something is new
#   host-perf-audit.py --guest-run --guests 101,105,433   nginx-hardening.sh --update in these guests, outputs kept for analysis
#   host-perf-audit.py --guest-sync --guest-run --guests all   the suite copied to every guest first, then the same
import argparse
import datetime
import glob
import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time

__version__ = "1.26.20261118.101500"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
PVE_DIR = os.environ.get("HOST_PERF_AUDIT_PVE_DIR", "/etc/pve")
TASKS_ACTIVE = os.environ.get("HOST_PERF_AUDIT_TASKS_ACTIVE", "/var/log/pve/tasks/active")      # 1.16: tasks of Proxmox running now
ZVOL_DIR = os.environ.get("HOST_PERF_AUDIT_ZVOL_DIR", "/dev/zvol")      # 1.11: links zdN -> dataset of each ZFS volume
SYSCTL_FILE = os.environ.get("HOST_PERF_AUDIT_SYSCTL_FILE", "/etc/sysctl.d/90-host-perf-audit.conf")
MODPROBE_FILE = os.environ.get("HOST_PERF_AUDIT_MODPROBE_FILE", "/etc/modprobe.d/zfs-arc-host-perf-audit.conf")
CMD_TIMEOUT = 20
VERBOSE = False

# Thresholds (documented in the report): above them the resource is "limiting".
CPU_PSI_WARN, CPU_PSI_BAD = 10.0, 25.0          # % of the time with at least one task waiting for a processor
IO_PSI_WARN, IO_PSI_BAD = 5.0, 15.0             # % of the time with at least one task waiting for the disk
IO_FULL_BAD = 5.0                               # % of the time with ALL the tasks waiting for the disk
MEM_PSI_WARN, MEM_PSI_BAD = 2.0, 10.0
UTIL_WARN, UTIL_BAD = 60.0, 85.0                # % of utilization of a disk (95th percentile of the samples)
AWAIT_HDD_BAD, AWAIT_SSD_BAD = 25.0, 5.0        # ms per operation (95th percentile) from which a disk is slow
STEAL_BAD = 5.0


def _start():
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "HOST_PERF_AUDIT_LANG")
    except Exception:
        return None


I18N = _start()
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 - every displayed text goes through the translator
T = I18N.tr if I18N else (lambda text: text)       # column titles: translated BEFORE padding (aligned in every language)


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


def load_module(name):
    path = os.path.join(SCRIPT_DIR, "apps", name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYSPERF = load_module("_sysperf")
IOLAT = load_module("_iolatency")          # 1.23: --io-latency (who waits for the disks, on which files)
SCHEMA_CONFIG = {"CSV": ("csv", str), "DURATION": ("duration", str), "EXPORT_AI": ("export_ai", str), "GUEST_COMMAND": ("guest_command", str), "GUESTS": ("guests", str), "SYNC_GIT": ("sync_git", str), "SYNC_SOURCE": ("sync_source", str),
                 "INSIDE": ("inside", bool), "INTERVAL": ("interval", float), "IO_LATENCY": ("io_latency", float), "NO_GUESTS": ("no_guests", bool), "TOP": ("top", int),
                 "VERBOSE": ("verbose", bool)}
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def color(code, text):
    return f"\x1b[{code}m{text}\x1b[0m" if COLOR else str(text)


def tag(level):
    """[OK] green, [WARN] yellow, [FAIL] red (terminal only)."""
    return {"ok": color("32", "[OK]"), "warn": color("33", "[WARN]"), "bad": color("31", "[FAIL]"), "info": "[i]"}[level]


def run(cmd, timeout=CMD_TIMEOUT):
    """(code, output) of an external command run ONCE (zpool, zfs…); (None, "") if absent."""
    if not shutil.which(cmd[0]):
        return None, ""
    if VERBOSE:
        eprint("+ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, universal_newlines=True, errors="replace", timeout=timeout)
        return r.returncode, r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return None, ""


def read(path):
    try:
        with open(SYSPERF._p(path) if SYSPERF else path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def read_plain(path):
    """Text of a real file of the host (/etc/pve, /var/log/pve: never under the test root of /proc and /sys); « » if unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def parse_duration(text):
    """"90", "90s", "10m", "4h", "1h30m" -> seconds (int); ValueError otherwise."""
    t = str(text).strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return int(float(t))
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?:in)?)?(?:(\d+)s)?", t)
    if not m or not any(m.groups()):
        raise ValueError(text)
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def human_duration(s):
    s = int(s)
    return f"{s // 3600} h {s % 3600 // 60:02d} min" if s >= 3600 else f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def gib(kib):
    return f"{kib / 1048576:.1f} " + T("GiB")


def pct(values, p):
    """p-th percentile of a list (nearest rank); None if empty."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    return v[min(len(v) - 1, max(0, int(round(p / 100.0 * len(v) + 0.5)) - 1))]


def avg(values):
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def lower_own_priority():
    """nice 10 and idle I/O class: the measurement must never slow the guests down."""
    try:
        os.nice(10)
    except OSError:
        pass
    if shutil.which("ionice"):
        subprocess.run(["ionice", "-c3", "-p", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------------------------------------------- guests (Proxmox)
def guest_names():
    """{vmid: (kind « lxc » | « vm », name, config text)} from /etc/pve (empty elsewhere)."""
    res = {}
    for kind, folder, key in (("lxc", "lxc", "hostname"), ("vm", "qemu-server", "name")):
        for path in glob.glob(os.path.join(PVE_DIR, folder, "*.conf")):
            vmid = os.path.basename(path)[:-5]
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            main_part = text.split("\n[", 1)[0]                     # snapshots sections excluded
            m = re.search(rf"^{key}:\s*(\S+)", main_part, re.M)
            res[vmid] = (kind, m.group(1) if m else "", main_part)
    return res


def guest_cgroups():
    """{vmid: (kind, cgroup directory)} of the RUNNING guests: /sys/fs/cgroup/lxc/<id> and /sys/fs/cgroup/qemu.slice/<id>.scope (cgroup v2)."""
    res = {}
    root = SYSPERF._p("/sys/fs/cgroup") if SYSPERF else "/sys/fs/cgroup"
    for path in glob.glob(os.path.join(root, "lxc", "*")):
        if os.path.basename(path).isdigit():
            res[os.path.basename(path)] = ("lxc", path)
    for path in glob.glob(os.path.join(root, "qemu.slice", "*.scope")):
        vmid = os.path.basename(path)[:-6]
        if vmid.isdigit():
            res[vmid] = ("vm", path)
    return res


GUEST_DATASET_RE = re.compile(r"(?:^|/)(?:vm|subvol|base)-(\d+)-(?:disk|state|cloudinit)")


def zfs_objset_counters():
    """1.11: {guest id: [read operations, bytes read, write operations, bytes written]} summed over the ZFS datasets and volumes of each guest, from
    /proc/spl/kstat/zfs/POOL/objset-0x* (one small file per dataset). ZFS does not go through the block layer: the io.stat of a cgroup counts nothing
    for a container on ZFS (the column « disk MB/s » showed 0.00 for every guest), and a VM writes to its zvol, not to a disk of its cgroup."""
    res = {}
    root = SYSPERF._p("/proc/spl/kstat/zfs") if SYSPERF else "/proc/spl/kstat/zfs"
    for path in glob.glob(os.path.join(root, "*", "objset-0x*")):
        try:
            with open(path, encoding="ascii", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        name = re.search(r"^dataset_name\s+\d+\s+(\S+)", text, re.M)
        m = GUEST_DATASET_RE.search(name.group(1)) if name else None
        if not m:
            continue
        c = res.setdefault(m.group(1), [0, 0, 0, 0])
        for i, key in enumerate(("reads", "nread", "writes", "nwritten")):
            v = re.search(rf"^{key}\s+\d+\s+(\d+)", text, re.M)
            if v:
                c[i] += int(v.group(1))
    return res


def zvol_names():
    """1.11: {zdN: dataset} from the links of /dev/zvol (zd16 -> data/zd0/vm-433-disk-0): the table of the disks names the volume and its guest."""
    res = {}
    root = ZVOL_DIR
    for link in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        if re.search(r"-part\d+$", link) or not os.path.islink(link):
            continue
        target = os.path.basename(os.readlink(link))
        if re.match(r"zd\d+$", target):
            res[target] = os.path.relpath(link, root)
    return res


def cgroup_counters(path):
    """Counters of a guest cgroup: cpu_usec, mem (bytes), mem_max, io_rbytes, io_wbytes, io_some_us (io.pressure total), cpu_some_us, mem_some_us."""
    res = {}

    def rd(name):
        try:
            with open(os.path.join(path, name), encoding="ascii", errors="replace") as f:
                return f.read()
        except OSError:
            return ""
    m = re.search(r"usage_usec (\d+)", rd("cpu.stat"))
    res["cpu_usec"] = int(m.group(1)) if m else None
    cur = rd("memory.current").strip()
    res["mem"] = int(cur) if cur.isdigit() else None
    mx = rd("memory.max").strip()
    res["mem_max"] = int(mx) if mx.isdigit() else None
    rb = wb = 0
    for line in rd("io.stat").splitlines():
        for k, v in re.findall(r"(rbytes|wbytes)=(\d+)", line):
            if k == "rbytes":
                rb += int(v)
            else:
                wb += int(v)
    res["io_rbytes"], res["io_wbytes"] = rb, wb
    for kind in ("io", "cpu", "memory"):
        m = re.search(r"^some .*total=(\d+)", rd(f"{kind}.pressure"), re.M)
        res[f"{kind}_some_us"] = int(m.group(1)) if m else None
    return res


# ---------------------------------------------------------------------------------------------------------------- one-time inspection
def host_facts():
    """Facts read once: kernel, Proxmox version, processors, memory, disks (type, model, scheduler), governor, swappiness, KSM, THP, ZFS ARC limits."""
    f = {"host": socket.gethostname(), "kernel": os.uname().release, "pve": "", "cpu_model": "",
         "cores": ((SYSPERF.cpu_times() or {}).get("n") if SYSPERF else None) or os.cpu_count() or 1}      # 1.1: processors of /proc/stat (the one measured)
    code, out = run(["pveversion"])
    if code == 0:
        f["pve"] = out.strip().splitlines()[0] if out.strip() else ""
    m = re.search(r"^model name\s*:\s*(.+)$", read("/proc/cpuinfo") or "", re.M)
    f["cpu_model"] = " ".join(m.group(1).split()) if m else ""
    f["mem"] = SYSPERF.meminfo() if SYSPERF else {}
    f["governor"] = (read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") or "").strip()
    f["swappiness"] = (read("/proc/sys/vm/swappiness") or "").strip()
    f["ksm"] = (read("/sys/kernel/mm/ksm/run") or "").strip()
    f["ksm_sharing"] = (read("/sys/kernel/mm/ksm/pages_sharing") or "0").strip()
    thp = read("/sys/kernel/mm/transparent_hugepage/enabled") or ""
    m = re.search(r"\[(\w+)\]", thp)
    f["thp"] = m.group(1) if m else ""
    f["arc_max_param"] = (read("/sys/module/zfs/parameters/zfs_arc_max") or "").strip()
    disks = {}
    for path in sorted(glob.glob((SYSPERF._p("/sys/block") if SYSPERF else "/sys/block") + "/*")):
        name = os.path.basename(path)
        if name.startswith(("loop", "ram", "zram", "sr", "fd", "nbd", "zd", "dm-", "md")):
            continue
        rot = SYSPERF.rotational(name) if SYSPERF else None
        sched = re.search(r"\[(\S+)\]", read(f"/sys/block/{name}/queue/scheduler") or "")
        size = (read(f"/sys/block/{name}/size") or "0").strip()
        kind = "NVMe" if name.startswith("nvme") else "HDD" if rot else "SSD" if rot is False else "?"
        disks[name] = {"kind": kind, "model": SYSPERF.disk_model(name) if SYSPERF else "", "scheduler": sched.group(1) if sched else "",
                       "size_gb": int(size) * 512 / 1e9 if size.isdigit() else 0}
    f["disks"] = disks
    return f


def smart_health(disks):
    """{disk: "PASSED" | "FAILED" | ""} with smartctl -H (if installed): a failing disk is slow long before it dies."""
    res = {}
    if not shutil.which("smartctl"):
        return res
    for name in disks:
        code, out = run(["smartctl", "-H", f"/dev/{name}"], timeout=15)
        m = re.search(r"(?:overall-health self-assessment test result|SMART Health Status):\s*(\S+)", out)
        res[name] = m.group(1).upper() if m else ""
    return res


def zfs_facts():
    """ZFS state read once: pools (size, used %, fragmentation, health, scrub / resilver in progress, special / log / cache devices, ashift),
    latency since the pool import (zpool iostat -l), dataset properties. {} without ZFS."""
    code, out = run(["zpool", "list", "-H", "-p", "-o", "name,size,alloc,free,frag,cap,health"])
    if code != 0:
        return {}
    pools = {}
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) >= 7:
            pools[c[0]] = {"size": int(c[1]) if c[1].isdigit() else 0, "free": int(c[3]) if c[3].isdigit() else 0, "frag": c[4].rstrip("%"), "cap": c[5].rstrip("%"), "health": c[6],
                           "special": False, "log": False, "cache": False, "scrub": "", "ashift": "", "vdevs": [], "latency": {}}
    code, out = run(["zpool", "status", "-P"])
    current = None
    for line in out.splitlines():
        m = re.match(r"\s*pool:\s*(\S+)", line)
        if m:
            current = pools.get(m.group(1))
            continue
        if current is None:
            continue
        if re.search(r"scrub in progress|resilver in progress", line):
            current["scrub"] = line.strip()
        m = re.match(r"\s+(special|logs|cache)\s*$", line)
        if m:
            current[{"logs": "log"}.get(m.group(1), m.group(1))] = True
        m = re.match(r"\s+(mirror|raidz\d?|draid\S*)-\d+\s", line)
        if m:
            current["vdevs"].append(m.group(1))
    code, out = run(["zpool", "get", "-H", "-p", "-o", "name,value", "ashift"])
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) == 2 and c[0] in pools:
            pools[c[0]]["ashift"] = c[1]
    # Average waits since import, in nanoseconds (-p): total_wait r/w, disk_wait r/w, syncq_wait r/w, asyncq_wait r/w...
    code, out = run(["zpool", "iostat", "-l", "-H", "-p"])
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) >= 15 and c[0] in pools:
            def ms(x):
                return int(x) / 1e6 if x.isdigit() else None
            pools[c[0]]["latency"] = {"total_r": ms(c[7]), "total_w": ms(c[8]), "disk_r": ms(c[9]), "disk_w": ms(c[10]), "syncq_w": ms(c[12]), "asyncq_w": ms(c[14])}
    datasets, sources = {}, {}
    # 1.10: « source » tells an inherited value from a value set on the dataset; space columns and mount point for the space report
    code, out = run(["zfs", "get", "-H", "-p", "-o", "name,property,value,source", "-t", "filesystem,volume",
                     "compression,atime,relatime,recordsize,volblocksize,sync,primarycache,logbias,compressratio,used,available,refquota,"
                     "usedbydataset,usedbysnapshots,usedbychildren,mountpoint"])
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) >= 3:
            datasets.setdefault(c[0], {})[c[1]] = c[2]
        if len(c) >= 4:
            sources.setdefault(c[0], {})[c[1]] = c[3]
    snapshots = []
    code, out = run(["zfs", "list", "-H", "-p", "-t", "snapshot", "-o", "name,used,creation"])
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) == 3 and "@" in c[0] and c[1].isdigit() and c[2].isdigit():
            snapshots.append((c[0], int(c[1]), int(c[2])))
    return {"pools": pools, "datasets": datasets, "sources": sources, "snapshots": snapshots}


# ---------------------------------------------------------------------------------------------------------------- space, backups, host tasks (1.10)
def size(n):
    """Bytes in the largest binary unit: 2.9 TiB, 391.0 GiB, 876 MiB."""
    n = float(n or 0)
    for unit, value in (("TiB", 2 ** 40), ("GiB", 2 ** 30)):
        if n >= value:
            return f"{n / value:.1f} {unit}"
    return f"{n / 2 ** 20:.0f} MiB"


def inherited_groups(zfs, prop, is_bad):
    """[(dataset where the value is set, number of datasets that inherit it from there)] for the datasets whose properties satisfy is_bad.
    1.10: sixteen datasets inheriting sync=disabled from their parent gave sixteen identical lines. Without the « source » column (old zfs), every dataset
    stands for itself, as before."""
    datasets, sources = zfs.get("datasets", {}), zfs.get("sources", {})
    hit = [n for n, p in sorted(datasets.items()) if is_bad(p)]
    roots = {}
    for n in hit:
        m = re.match(r"inherited from (\S+)", sources.get(n, {}).get(prop, ""))
        if m and m.group(1) in hit:
            roots[m.group(1)] = roots.get(m.group(1), 0) + 1
        else:
            roots.setdefault(n, 0)
    return sorted(roots.items())


def and_heirs(count):
    return f" (and {count} datasets that inherit it)" if count else ""


def directory_sizes(path, limit=60000, seconds=12.0):
    """({first-level name: bytes on the disk}, complete?) of a folder: bounded walk (same filesystem, no symbolic link followed, at most « limit » entries
    and « seconds » seconds) so that a huge tree never keeps the disks busy."""
    sizes, seen, deadline, complete = {}, 0, time.monotonic() + seconds, True
    try:
        device = os.stat(path).st_dev
        first = sorted(os.scandir(path), key=lambda e: e.name)
    except OSError:
        return {}, True
    for entry in first:
        stack, total = [entry], 0
        while stack:
            e = stack.pop()
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if st.st_dev != device:
                continue
            total += st.st_blocks * 512
            seen += 1
            if seen > limit or time.monotonic() > deadline:
                complete = False
                break
            if e.is_dir(follow_symlinks=False):
                try:
                    stack.extend(os.scandir(e.path))
                except OSError:
                    pass
        sizes[entry.name] = total
        if not complete:
            break
    return sizes, complete


def zfs_space(zfs, names, fd, out):
    """1.10: where the space of each pool goes (datasets, snapshots, files stored directly in a parent dataset) and the guest disks that are almost full."""
    datasets = zfs.get("datasets", {})

    def num(name, key):
        value = datasets.get(name, {}).get(key, "")
        return int(value) if value.isdigit() else 0

    for pool in zfs.get("pools", {}):
        members = [n for n in datasets if n == pool or n.startswith(pool + "/")]
        if not members or not num(pool, "used"):
            continue
        snaps = [s for s in zfs.get("snapshots", []) if s[0].split("@")[0] in members]
        snap_total = sum(num(n, "usedbysnapshots") for n in members)
        line = f"    space of pool {pool} — {size(num(pool, 'available'))} free, {size(num(pool, 'used'))} used · snapshots {size(snap_total)}"
        if snaps:
            oldest = min(snaps, key=lambda s: s[2])
            line += f" ({len(snaps)} snapshots, the oldest of {datetime.date.fromtimestamp(oldest[2])}, {oldest[0]})"
        out.append(line)
        for n in sorted(members, key=lambda n: -num(n, "usedbydataset"))[:6]:
            own = num(n, "usedbydataset")
            if own < 2 ** 30:
                continue
            snap, quota = num(n, "usedbysnapshots"), num(n, "refquota")
            out.append(f"      {n:<38} {size(own):>10}" + (f" + {size(snap)} of snapshots" if snap >= 2 ** 20 else "")
                       + (f" · {size(num(n, 'available'))} free of {size(quota)}" if quota else ""))
        for n in members:
            own, mount = num(n, "usedbydataset"), datasets[n].get("mountpoint", "")
            if not num(n, "usedbychildren") or own < max(10 * 2 ** 30, num(pool, "used") // 10) or not mount.startswith("/") or not os.path.isdir(mount):
                continue
            sizes, complete = directory_sizes(mount)
            top = sorted(sizes.items(), key=lambda x: -x[1])[:4]
            if top:
                out.append(f"      files stored directly in {n} ({mount}), outside the guests: "
                           + ", ".join(f"{name} {size(b)}" for name, b in top) + ("" if complete else " (partial count: too many files)"))
    for n in sorted(datasets):
        quota, free = num(n, "refquota"), num(n, "available")
        if not quota or not (free < quota * 0.10 or (free < 2 * 2 ** 30 and free < quota * 0.30)):
            continue
        base = n.rsplit("/", 1)[-1]
        m = re.match(r"subvol-(\d+)-disk-\d+$", base)
        vmid = m.group(1) if m else ""
        _kind, name, conf = names.get(vmid, ("", "", ""))
        where = re.search(rf"^(rootfs|mp\d+):\s*\S*{re.escape(base)}(?:,(.*))?$", conf, re.M) if vmid else None
        mount = re.search(r"mp=([^,\s]+)", where.group(2) or "") if where else None
        key = where.group(1) if where else ""
        more = max(5, round(quota / 2 ** 30 * 0.25))
        fd.suggest(1 if free < quota * 0.05 else 2,
                   (f"container {vmid} ({name}): disk {base}" if vmid else f"dataset {n}") + (f" mounted on {mount.group(1)}" if mount else " (the root disk)" if key == "rootfs" else "")
                   + f" has only {size(free)} free of {size(quota)} — a full disk stops PostgreSQL and Odoo: free space inside the guest, or enlarge it"
                   + (f": pct resize {vmid} {key} +{more}G" if key else ""))


BACKUP_RE = re.compile(r"^vzdump-(lxc|qemu)-(\d+)-(\d{4})_(\d\d)_(\d\d)-(\d\d)_(\d\d)_(\d\d)\.(?:tar|vma|tgz)(?:\.\w+)?$")


def pve_sections(path):
    """[(type, name, {key: value})] of a section file of Proxmox (storage.cfg, jobs.cfg): « type: name » then indented « key value » lines."""
    sections = []
    for line in read_plain(path).splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(\S+)\s*$", line)
        if m:
            sections.append((m.group(1), m.group(2), {}))
        elif sections and line[:1] in (" ", "\t") and line.strip():
            parts = line.split(None, 1)
            sections[-1][2][parts[0]] = parts[1].strip() if len(parts) > 1 else ""
    return sections


def retention_of(options):
    """Retention read in the options of a storage, a job or vzdump.conf: « keep-last=3,keep-daily=7 », « maxfiles=2 », or « » (none: everything is kept)."""
    prune = options.get("prune-backups", "")
    keeps = [k for k in prune.split(",") if k and not re.match(r"keep-all=1$", k.strip()) and not re.match(r"keep-\w+=0$", k.strip())]
    if keeps:
        return ",".join(k.strip() for k in keeps)
    return f"maxfiles={options['maxfiles']}" if options.get("maxfiles", "0") not in ("0", "") else ""


def scan_backups(folder, depth=3):
    """Backup files under a dump folder (sub-folders included, « depth » levels): ([(guest id, bytes, time, path)], other big files [(bytes, path)],
    interrupted-backup folders [(time, path)])."""
    backups, others, leftovers = [], [], []
    stack = [(folder, 0)]
    while stack:
        current, level = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if e.is_dir(follow_symlinks=False):
                if e.name.startswith("vzdumptmp") or e.name.endswith(".tmp"):
                    leftovers.append((st.st_mtime, e.path))
                elif level < depth:
                    stack.append((e.path, level + 1))
                continue
            m = BACKUP_RE.match(e.name)
            if m:
                when = datetime.datetime(*(int(x) for x in m.groups()[2:8])).timestamp()
                backups.append((m.group(2), st.st_size, when, e.path))
            elif st.st_size >= 100 * 2 ** 20 and not e.name.endswith((".log", ".notes")):
                others.append((st.st_size, e.path))
    return backups, others, leftovers


def recent_tasks(days=3, kinds=("vzdump", "vzsnapshot", "qmsnapshot", "vzrestore", "qmrestore", "zfs", "scrub")):
    """Tasks of Proxmox finished during the last days, from /var/log/pve/tasks/index*: [(start, end, type, id, status)], most recent last.
    A backup or a snapshot is what makes the HDD busy for the guests: its hours are compared with the slow hours of the sites."""
    tasks, since = [], time.time() - days * 86400
    for path in sorted(glob.glob(os.environ.get("HOST_PERF_AUDIT_TASKS", "/var/log/pve/tasks/index") + "*"), reverse=True):
        for line in read_plain(path).splitlines():
            parts = line.split()
            u = parts[0].split(":") if parts else []
            if len(u) < 8 or u[0] != "UPID" or len(parts) < 3:
                continue
            try:
                start, end = int(u[4], 16), int(parts[1], 16)
            except ValueError:
                continue
            if start >= since and u[5] in kinds:
                tasks.append((start, end, u[5], u[6], " ".join(parts[2:])[:60]))
    return sorted(tasks)


def io_tasks():
    """Processes of the host that read or write a lot when they run (backup, copy, compression, zfs send / receive): {short description}."""
    known = {"vzdump", "rsync", "zstd", "lzop", "pigz", "gzip", "tar", "dd", "fstrim", "proxmox-backup-client", "vma", "borg", "restic", "rclone", "cp", "zfs", "zpool"}
    found = set()
    for path in glob.glob(SYSPERF._p("/proc/[0-9]*") if SYSPERF else "/proc/[0-9]*"):
        try:
            comm = open(path + "/comm", encoding="utf-8", errors="replace").read().strip()
            cmd = open(path + "/cmdline", encoding="utf-8", errors="replace").read().replace("\0", " ").strip()
        except OSError:
            continue
        if ":vzdump:" in cmd or comm == "vzdump":
            m = re.search(r":vzdump:(\d*):", cmd)
            found.add("vzdump" + (f" {m.group(1)}" if m and m.group(1) else ""))
        elif comm in ("zfs", "zpool"):
            if re.search(r"\b(send|receive|recv|scrub|destroy)\b", cmd):
                found.add(cmd[:50])
        elif comm in known and comm != "cp":
            found.add(comm)
    return found


def group_waits():
    """% of the last minute during which the tasks of each top-level cgroup waited for the disk (io.pressure, « some avg60 »): tells whether the wait
    is felt in the guests (lxc, qemu.slice) or in the tasks of the host itself (system.slice: backups, pvedaemon; user.slice: a shell)."""
    root = SYSPERF._p("/sys/fs/cgroup") if SYSPERF else "/sys/fs/cgroup"
    res = []
    for group in ("lxc", "qemu.slice", "system.slice", "user.slice"):
        m = re.search(r"^some .*?avg60=([\d.]+)", read(os.path.join(root, group, "io.pressure")) or "", re.M)
        if m:
            res.append((group, float(m.group(1))))
    return res


def keep_last_of(keep):
    """The number of backups per guest that a retention keeps when it is « keep-last=N » or « maxfiles=N » alone; None for any other retention."""
    m = re.fullmatch(r"(?:keep-last|maxfiles)=(\d+)", (keep or "").strip())
    return int(m.group(1)) if m else None


def retention_gaps(names):
    """1.15: backups that the retention of Proxmox does not remove. Proxmox prunes only the files placed directly in the dump folder of a storage:
    a copy in a sub-folder (dump/latest/) is invisible to it (« pvesm list » does not show it) and is kept for ever. On 2026-11-14 the host had 146
    backups (2.9 TiB, 90 % of the pool) for a retention of keep-last=7, and pvesm saw none of them.
    [{"storage", "folder", "found", "seen", "keep", "hidden": [paths outside the dump folder], "extra": [(guest, [paths to delete], bytes)], "gone": {guest: (n, bytes)}}]"""
    res = []
    general = dict(re.findall(r"^\s*([\w-]+):\s*(\S.*)$", read_plain(os.environ.get("HOST_PERF_AUDIT_VZDUMP_CONF", "/etc/vzdump.conf")), re.M))
    jobs = [o for kind, _n, o in pve_sections(os.path.join(PVE_DIR, "jobs.cfg")) if kind == "vzdump"]
    for kind, name, o in pve_sections(os.path.join(PVE_DIR, "storage.cfg")):
        if not o.get("path") or "backup" not in o.get("content", ""):
            continue
        folder = os.path.join(o["path"], "dump")
        backups, _others, _left = scan_backups(folder)
        if not backups:
            continue
        code, out = run(["pvesm", "list", name, "--content", "backup"], timeout=60)
        seen = max(0, len([l for l in (out or "").splitlines() if l.strip()]) - 1) if code == 0 else None
        keep = retention_of(o) or retention_of(general) or ", ".join(sorted({retention_of(j) for j in jobs if retention_of(j) and j.get("storage", name) == name}))
        n_keep = keep_last_of(keep)
        hidden = [p for _v, _b, _w, p in backups if os.path.dirname(p) != folder]
        extra, gone, per = [], {}, {}
        for vmid, b, when, p in backups:
            per.setdefault(vmid, []).append((when, b, p))
        for vmid, items in sorted(per.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            items.sort(reverse=True)
            if vmid not in names:
                gone[vmid] = (len(items), sum(b for _w, b, _p in items))
                continue
            if n_keep is not None and len(items) > n_keep:
                old = items[n_keep:]
                extra.append((vmid, [p for _w, _b, p in old], sum(b for _w, b, _p in old)))
        res.append({"storage": name, "folder": folder, "found": len(backups), "seen": seen, "keep": keep, "n_keep": n_keep, "hidden": hidden, "extra": extra, "gone": gone})
    return res


def backup_findings(names):
    """[(level bad | warn | info, text, [commands])] from retention_gaps, with the list of the files to delete written to the state folder."""
    res = []
    for g in retention_gaps(names):
        name, folder, keep = g["storage"], g["folder"], g["keep"] or "none"
        if g["hidden"] and (g["seen"] is None or g["seen"] < g["found"]):
            where = sorted({os.path.relpath(os.path.dirname(p), folder) for p in g["hidden"]})
            res.append(("bad", f"storage {name}: {g['found']} backups under {folder} but Proxmox sees {g['seen'] if g['seen'] is not None else '?'} — "
                        f"{len(g['hidden'])} are in a sub-folder ({', '.join(where[:3])}) where the retention ({keep}) never applies: they are kept for ever",
                        [f"pvesm list {name} --content backup | head -5", f"ls -l -a {folder}", f"ls -1t {os.path.join(folder, where[0])} | head -12",
                         "grep -rn -e dumpdir -e " + where[0].split('/')[0] + " /etc/pve/jobs.cfg /etc/vzdump.conf /etc/cron.d /usr/local/bin /usr/local/sbin /root/*.sh 2>/dev/null",
                         # 1.16: what moves the backups there: a hook script of vzdump, a cron job, a timer, a copy from another machine
                         "grep -n -i -e script -e hook /etc/vzdump.conf /etc/pve/jobs.cfg 2>/dev/null",
                         "crontab -l 2>/dev/null | grep -v '^#'",
                         "systemctl list-timers --all --no-pager | grep -v -e apt -e man-db -e logrotate -e e2scrub -e fstrim | head -25",
                         f"ls -l -a {os.path.join(folder, where[0])} | head -8"]))
        if g["extra"]:
            total = sum(b for _v, _p, b in g["extra"])
            listed = []
            for vmid, paths, _b in g["extra"]:
                for p in paths:
                    base = os.path.join(os.path.dirname(p), os.path.basename(p).split(".")[0])
                    listed += [p] + [x for x in (base + ".log", p + ".notes") if os.path.exists(x)]
            target = os.path.join(STATE_DIR, f"backups-to-delete-{name}.txt")
            try:
                os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write("\n".join(listed) + "\n")
            except OSError:
                target = ""
            details = ", ".join(f"{vmid} ({names.get(vmid, ('', '', ''))[1] or '?'}): {len(paths)} ({size(b)})" for vmid, paths, b in sorted(g["extra"], key=lambda x: -x[2])[:6])
            res.append(("bad" if total >= 100 * 2 ** 30 else "warn",
                        f"storage {name}: {sum(len(p) for _v, p, _b in g['extra'])} backups beyond the retention ({keep}, the {g['n_keep']} newest of each guest kept) — "
                        f"deleting them frees {size(total)}: {details}",
                        ([f"wc -l {target}", f"head -20 {target}", f"xargs -d '\\n' -a {target} " + DU_TOTAL + " | tail -1",
                          f"xargs -d '\\n' -a {target} rm -v --   # deletes the files of the list: irreversible, copy elsewhere first what must be kept"] if target else [])))
        if g["gone"]:
            res.append(("info", f"storage {name}: backups of guests that no longer exist, kept: "
                        + ", ".join(f"{v}: {n} ({size(b)})" for v, (n, b) in sorted(g["gone"].items())) + " — delete them by hand once they are no longer needed",
                        [f"ls -lh {folder}/*/vzdump-*-{v}-* {folder}/vzdump-*-{v}-* 2>/dev/null | head" for v in sorted(g["gone"])[:3]]))
    return res


def analyze_backups(zfs, names, fd, out):
    """1.10: the backups of vzdump: where they are, how many, how much space, which retention, when they ran. On a pool of HDD shared with the guests,
    they are the first thing that fills the pool and that makes the guests wait."""
    storages = [(name, o) for kind, name, o in pve_sections(os.path.join(PVE_DIR, "storage.cfg")) if o.get("path") and "backup" in o.get("content", "")]
    jobs = [(name, o) for kind, name, o in pve_sections(os.path.join(PVE_DIR, "jobs.cfg")) if kind == "vzdump"]
    general = dict(re.findall(r"^\s*([\w-]+):\s*(\S.*)$", read_plain(os.environ.get("HOST_PERF_AUDIT_VZDUMP_CONF", "/etc/vzdump.conf")), re.M))
    folders = [(name, os.path.join(o["path"], "dump"), o) for name, o in storages]
    for extra in {o.get("dumpdir") for _n, o in jobs} | {general.get("dumpdir")}:
        if extra and extra not in [f for _n, f, _o in folders]:
            folders.append(("dumpdir", extra, {}))
    tasks = [t for t in recent_tasks() if t[2] == "vzdump"]
    if not folders and not jobs and not tasks:
        return
    for level, text, commands in backup_findings(names):            # 1.15: retention that does not apply
        fd.suggest(1 if level == "bad" else 2 if level == "warn" else 3, text)
        if commands:
            fd.ask(text, commands)
    out.append("BACKUPS (vzdump)")
    job_keep = [retention_of(o) for _n, o in jobs]
    datasets = zfs.get("datasets", {}) if zfs else {}
    for name, folder, options in folders:
        backups, others, leftovers = scan_backups(folder)
        keep = retention_of(options) or retention_of(general) or ", ".join(sorted({k for k in job_keep if k}))
        total = sum(b[1] for b in backups) + sum(o[0] for o in others)
        line = f"  storage {name} ({folder}) — {len(backups)} backups, {size(total)}"
        if backups:
            line += f" — the oldest of {datetime.date.fromtimestamp(min(b[2] for b in backups))}, the newest of {datetime.date.fromtimestamp(max(b[2] for b in backups))}"
        out.append(line + f" · retention: {keep or 'none (everything is kept)'}")
        per = {}
        for vmid, b, when, _p in backups:
            c = per.setdefault(vmid, [0, 0, 0])
            c[0], c[1], c[2] = c[0] + 1, c[1] + b, max(c[2], when)
        for vmid, (count, b, last) in sorted(per.items(), key=lambda x: -x[1][1])[:8]:
            out.append(f"    {vmid:>5} {names.get(vmid, ('', '', ''))[1][:22]:<22} {count:>3} backups {size(b):>10} · the last of {datetime.date.fromtimestamp(last)}")
        if others:
            out.append(f"    other big files: {len(others)}, {size(sum(o[0] for o in others))} — the largest: "
                       + ", ".join(f"{os.path.relpath(p, folder)} ({size(b)})" for b, p in sorted(others, reverse=True)[:3]))
        most = max([c[0] for c in per.values()] or [0])
        pool = ""
        best = max((n for n, p in datasets.items() if p.get("mountpoint", "").startswith("/") and (folder + "/").startswith(p["mountpoint"].rstrip("/") + "/")),
                   key=lambda n: len(datasets[n]["mountpoint"]), default="")
        if best:
            pool = best.split("/")[0]
        shared = bool(pool) and any(re.search(r"/(subvol|vm)-\d+-", n) for n in datasets if n.startswith(pool + "/"))
        cap = zfs["pools"].get(pool, {}).get("cap", "") if pool else ""
        full = cap.isdigit() and int(cap) >= 80
        if total and not keep and (most >= 4 or full):
            fd.suggest(1 if full else 2, f"storage {name} — {len(backups) + len(others)} backup files ({size(total)}) and no retention"
                       + (f" — they fill pool {pool} (used {cap} %)" if full else "")
                       + ": set a retention on the backup job (Datacenter > Backup > Retention, e.g. keep-last=2, keep-daily=7, keep-weekly=4), then remove the old ones (« Prune »)")
            fd.ask(f"storage {name}: the backups and their retention", [f"ls -lhS {folder} {os.path.join(folder, '*')} 2>/dev/null | head -40", "grep -A8 vzdump /etc/pve/jobs.cfg"])
        elif total and full and total >= zfs["pools"][pool]["size"] * 0.3:
            fd.suggest(1, f"storage {name} — the backups ({size(total)}) are the largest part of pool {pool} (used {cap} %) with retention {keep}: keep fewer of them, or move them to another disk")
        if total and shared:
            fd.suggest(2, f"storage {name} — the backups are on pool {pool}, the disks of the guests — a failure of the pool loses the guests AND their backups, and each backup "
                          "competes with the guests for the same disks: another disk, a NAS or Proxmox Backup Server")
        for when, path in leftovers:
            if time.time() - when > 86400:
                fd.suggest(3, f"{path}: folder left by an interrupted backup ({datetime.date.fromtimestamp(when)}) — remove it when no backup is running")
    for name, o in jobs:
        out.append(f"  job {name}: schedule {o.get('schedule', '?')}, storage {o.get('storage') or o.get('dumpdir') or '?'}, guests {'all of them' if o.get('all') == '1' else o.get('vmid', '?')}, "
                   f"mode {o.get('mode', 'snapshot')}, compression {o.get('compress', 'none')}, retention {retention_of(o) or 'none (everything is kept)'}" + (" (disabled)" if o.get("enabled") == "0" else ""))
    if tasks:
        out.append("  backups of the last 3 days (compare these hours with the slow hours of the sites):")
        for start, end, _kind, vmid, status in tasks[-12:]:
            out.append(f"    {datetime.datetime.fromtimestamp(start):%Y-%m-%d %H:%M} → {datetime.datetime.fromtimestamp(end):%H:%M} ({human_duration(max(0, end - start))}) guest {vmid or 'all of them'} — {status}")
    out.append("")


EXPORT_SECRET_RE = re.compile(r"^(\s*)(\S*(?:password|passwd|secret|token|sshkeys|cipassword|key|fingerprint)\S*)(\s*[:=]?\s*)\S.*$", re.I | re.M)


class Tee:
    """Standard output copied to a list (without colors) for --export-ai, the screen unchanged."""

    def __init__(self, stream):
        self.stream, self.parts = stream, []

    def write(self, text):
        self.parts.append(re.sub(r"\x1b\[[0-9;]*m", "", text))
        return self.stream.write(text)

    def flush(self):
        self.stream.flush()

    def isatty(self):
        return self.stream.isatty()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def export_ai_path(value):
    """None: no export; « »: default file; otherwise the file asked (no / false / 0 / off: none; yes / true / 1 / auto: default file)."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in ("no", "false", "0", "off", "non"):
        return None
    return "" if text.lower() in ("", "yes", "true", "1", "auto", "oui") else os.path.expanduser(text)


def export_ai(path, screen, facts, names, command):
    """--export-ai: the report as shown, then the raw state of the host (pools, datasets, snapshots, disks, guests, backups, kernel warnings) in one
    Markdown file, mode 600, to send for verification. Passwords and keys of the configurations are replaced by « *** »."""
    if not path:
        folder = os.environ.get("HOST_PERF_AUDIT_STATE_DIR", "/var/lib/host-perf-audit")
        try:
            os.makedirs(folder, mode=0o700, exist_ok=True)
        except OSError:
            folder = os.getcwd()
        path = os.path.join(folder, f"export-ai-{facts['host']}-" + time.strftime("%Y%m%d-%H%M%S.md"))
    redact = lambda text: EXPORT_SECRET_RE.sub(r"\1\2\3***", text)
    lines = [f"# host-perf-audit.py v{__version__} - export for verification", "",
             f"- Host: {facts['host']} · {facts['pve'] or 'Linux ' + facts['kernel']}",
             f"- Written on: {time.strftime('%Y-%m-%d %H:%M:%S')} (local time, {time.strftime('%Z')})",
             f"- Command: {command}", "", "## Report", "", "```", screen.strip("\n"), "```", ""]
    commands = [("ZFS pools", ["zpool", "list", "-v"]), ("ZFS pool status", ["zpool", "status", "-v"]), ("ZFS latency per device since import", ["zpool", "iostat", "-l", "-v"]),
                ("ZFS space per dataset", ["zfs", "list", "-o", "space,refquota,mountpoint", "-t", "filesystem,volume"]),
                ("ZFS snapshots", ["zfs", "list", "-t", "snapshot", "-o", "name,used,refer,creation", "-s", "creation"]),
                ("ZFS properties set locally", ["zfs", "get", "-H", "-s", "local,received", "-o", "name,property,value", "all"]),
                ("ZFS events", ["zpool", "events"]),
                ("Filesystems", ["df", "-hT", "-x", "tmpfs", "-x", "devtmpfs", "-x", "overlay"]), ("Block devices", ["lsblk", "-o", "NAME,SIZE,TYPE,ROTA,SCHED,MODEL,MOUNTPOINT"]),
                ("Memory", ["free", "-m"]), ("Uptime and load", ["uptime"]), ("Proxmox storages", ["pvesm", "status"]), ("Containers", ["pct", "list"]), ("Virtual machines", ["qm", "list"]),
                ("Timers", ["systemctl", "list-timers", "--all", "--no-pager"]),
                ("Kernel warnings of the last 3 days (disk errors, blocked tasks)", ["journalctl", "-k", "-p", "warning", "--since", "-3d", "--no-pager", "-o", "short-iso"]),
                ("Busiest processes", ["ps", "-eo", "pid,pcpu,pmem,rss,etime,args", "--sort=-pcpu"])]
    for disk in sorted(facts.get("disks", {})):
        commands.append((f"SMART of {disk}", ["smartctl", "-H", "-A", f"/dev/{disk}"]))
    for title, cmd in commands:
        code, text = run(cmd)
        if code is None or not text.strip():
            continue
        kept = text.rstrip("\n").splitlines()
        if len(kept) > 120:
            kept = kept[:20] + [f"[... {len(kept) - 120} lines removed ...]"] + kept[-100:] if cmd[0] in ("journalctl", "zpool") else kept[:120] + [f"[... {len(kept) - 120} more lines ...]"]
        lines += [f"## {title}", "", "`" + " ".join(cmd) + "`", "", "```"] + [l[:400] for l in kept] + ["```", ""]
    files = [("/proc/mdstat", "Software RAID"), ("/proc/pressure/io", "Disk pressure"), ("/proc/pressure/cpu", "Processor pressure"), ("/proc/pressure/memory", "Memory pressure"),
             ("/proc/spl/kstat/zfs/arcstats", "ZFS ARC counters"), (os.path.join(PVE_DIR, "storage.cfg"), "Proxmox storage.cfg"), (os.path.join(PVE_DIR, "jobs.cfg"), "Proxmox jobs.cfg"),
             (os.environ.get("HOST_PERF_AUDIT_VZDUMP_CONF", "/etc/vzdump.conf"), "vzdump.conf"), ("/etc/cron.d/zfsutils-linux", "ZFS scrub and trim schedule")]
    for file_path, title in files:
        text = read_plain(file_path) if file_path.startswith(PVE_DIR) or "vzdump" in file_path or "cron" in file_path else read(file_path)
        if text and text.strip():
            body = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
            if "arcstats" in file_path:
                body = [l for l in body if re.match(r"(size|c|c_max|c_min|hits|misses|memory_throttle_count|arc_meta_used|mfu_size|mru_size|l2_hits|l2_misses|demand_data_misses|prefetch_data_misses)\s", l)]
            lines += [f"## {title}", "", f"`{file_path}`", "", "```"] + [redact(l)[:400] for l in body[:150]] + ["```", ""]
    params = []
    for name in ("zfs_arc_max", "zfs_arc_min", "zfs_txg_timeout", "zfs_dirty_data_max", "zfs_vdev_async_write_max_active", "zfs_vdev_sync_write_max_active", "zfs_vdev_scrub_max_active", "zfs_prefetch_disable"):
        value = (read(f"/sys/module/zfs/parameters/{name}") or "").strip()
        if value:
            params.append(f"{name} = {value}")
    if params:
        lines += ["## ZFS module parameters", "", "```"] + params + ["```", ""]
    tasks = recent_tasks(days=7, kinds=("vzdump", "vzsnapshot", "qmsnapshot", "vzrestore", "qmrestore", "vzstart", "vzstop", "qmstart", "qmstop", "vzreboot", "qmreboot", "aptupdate", "imgcopy", "move_volume", "resize"))
    if tasks:
        lines += ["## Proxmox tasks of the last 7 days", "", "```"] + [f"{datetime.datetime.fromtimestamp(s):%Y-%m-%d %H:%M:%S} to {datetime.datetime.fromtimestamp(e):%H:%M:%S} {k} {i}: {st}" for s, e, k, i, st in tasks[-150:]] + ["```", ""]
    for vmid, (kind, name, conf) in sorted(names.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        lines += [f"## Guest {vmid} ({kind}, {name})", "", "```"] + [redact(l)[:300] for l in conf.splitlines() if l.strip() and not l.startswith("#")] + ["```", ""]
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(path, 0o600)
    except OSError as problem:
        eprint(f"--export-ai: file not written: {problem}")
        return 1
    print(f"\n--export-ai: written to {path} ({len(lines)} lines, mode 600)")
    return 0


# ---------------------------------------------------------------------------------------------------------------- sampling
def sample_loop(duration, interval, guests, csv_path):
    """Samples every `interval` seconds during `duration` seconds (Ctrl-C: stop, keep what was taken). Returns the list of rates() results, each with
    "guests": {vmid: {cpu, mem, io_r, io_w, io_some}}."""
    samples, t_end = [], time.monotonic() + duration
    prev = SYSPERF.snapshot()
    prev_g = {vmid: cgroup_counters(path) for vmid, (_k, path) in guests.items()}
    prev_z = zfs_objset_counters() if guests else {}
    csv = None
    if csv_path:
        try:
            csv = open(csv_path, "w", encoding="utf-8")
        except OSError as e:
            eprint(f"WARNING: CSV file not writable ({e}): samples not written.")
    show = sys.stderr.isatty() or VERBOSE
    last_shown, start = 0.0, time.monotonic()
    try:
        while True:
            remaining = t_end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
            cur = SYSPERF.snapshot()
            r = SYSPERF.rates(prev, cur)
            dt = r["dt"]
            gs = {}
            cur_z = zfs_objset_counters() if guests else {}
            for vmid, (_k, path) in guests.items():
                c = cgroup_counters(path)
                p = prev_g.get(vmid) or {}

                def d(key):
                    return (c[key] - p[key]) if c.get(key) is not None and p.get(key) is not None else None
                cpu = d("cpu_usec")
                gs[vmid] = {"cpu": cpu / 1e6 / dt * 100.0 if cpu is not None else None, "mem": c.get("mem"), "mem_max": c.get("mem_max"),
                            "io_r": (d("io_rbytes") or 0) / dt, "io_w": (d("io_wbytes") or 0) / dt,
                            "io_some": d("io_some_us") / 1e6 / dt * 100.0 if d("io_some_us") is not None else None,
                            "cpu_some": d("cpu_some_us") / 1e6 / dt * 100.0 if d("cpu_some_us") is not None else None}
                z, pz = cur_z.get(vmid), prev_z.get(vmid)
                if z and pz:                                     # 1.11: the ZFS counters of its datasets (operations and bytes per second)
                    zr_ops, zr_b, zw_ops, zw_b = (max(0, a - b) / dt for a, b in zip(z, pz))
                    gs[vmid].update(z_r_ops=zr_ops, z_w_ops=zw_ops, z_r=zr_b, z_w=zw_b)
                prev_g[vmid] = c
            prev_z = cur_z
            r["guests"] = gs
            r["psi_source"] = cur.get("psi_source", "/proc/pressure")
            prev = cur
            samples.append(r)
            if csv:
                write_csv(csv, r, len(samples) == 1)
            if show and (time.monotonic() - last_shown >= 60 or interval >= 60):
                last_shown = time.monotonic()
                dev, util = SYSPERF.busiest_disk(r)
                eprint(f"  [{human_duration(time.monotonic() - start)} / {human_duration(duration)}] sample {len(samples)}: CPU {r['cpu']['busy'] if r['cpu'] else 0:.0f} %"
                       f" · busiest disk {dev or '-'} {util:.0f} % · I/O wait {r['psi'].get('io', {}).get('some', 0):.1f} % · memory wait {r['psi'].get('memory', {}).get('some', 0):.1f} %")
    except KeyboardInterrupt:
        eprint(f"\nMeasurement interrupted (Ctrl-C) after {len(samples)} samples: report on what was measured.")
    finally:
        if csv:
            csv.close()
    return samples


def write_csv(f, r, header):
    disks = sorted(r["disks"])
    if header:
        f.write(",".join(["time", "cpu_busy", "iowait", "steal", "psi_cpu", "psi_io_some", "psi_io_full", "psi_mem", "mem_available_mb", "arc_mb", "arc_hit"]
                         + [f"{d}_util" for d in disks] + [f"{d}_r_await" for d in disks] + [f"{d}_w_await" for d in disks]) + "\n")

    def v(x, fmt="{:.2f}"):
        return "" if x is None else fmt.format(x)
    c = r["cpu"] or {}
    f.write(",".join([datetime.datetime.fromtimestamp(r["wall"]).strftime("%Y-%m-%d %H:%M:%S"), v(c.get("busy")), v(c.get("iowait")), v(c.get("steal")),
                      v(r["psi"].get("cpu", {}).get("some")), v(r["psi"].get("io", {}).get("some")), v(r["psi"].get("io", {}).get("full")),
                      v(r["psi"].get("memory", {}).get("some")), v((r["mem"].get("MemAvailable") or 0) / 1024, "{:.0f}"),
                      v((r["arc"] or {}).get("size", 0) / 1048576 if r["arc"] else None, "{:.0f}"), v((r["arc"] or {}).get("hit"))]
                     + [v(r["disks"][d]["util"]) for d in disks] + [v(r["disks"][d]["r_await"]) for d in disks] + [v(r["disks"][d]["w_await"]) for d in disks]) + "\n")
    f.flush()


# ---------------------------------------------------------------------------------------------------------------- analysis
class Findings:
    """Verdicts per resource and suggestions (each suggestion: level HIGH / MEDIUM / LOW, text, apply function or None)."""

    def __init__(self):
        self.verdicts = {}        # resource -> (level ok|warn|bad, text)
        self.suggestions = []     # (priority 1-3, text, apply callable or None, apply label)
        self.commands = []        # 1.12: (title, [commands to copy, paste and send the output of])

    def ask(self, title, commands):
        self.commands.append((title, list(commands)))

    def verdict(self, resource, level, text):
        self.verdicts[resource] = (level, text)

    def suggest(self, priority, text, apply=None, label=""):
        self.suggestions.append((priority, text, apply, label))


def analyze_cpu(samples, facts, fd, out):
    busy = [s["cpu"]["busy"] for s in samples if s["cpu"]]
    steal = [s["cpu"]["steal"] for s in samples if s["cpu"]]
    iow = [s["cpu"]["iowait"] for s in samples if s["cpu"]]
    some = [s["psi"].get("cpu", {}).get("some") for s in samples]
    load = [s.get("load") for s in samples]
    out.append(f"PROCESSOR — {facts['cpu_model'] or '?'}, {facts['cores']} logical cores, governor {facts['governor'] or '?'}")
    out.append(f"  busy: average {avg(busy) or 0:.0f} %, 95 % of the time under {pct(busy, 95) or 0:.0f} %, peak {max(busy or [0]):.0f} % · iowait {avg(iow) or 0:.1f} % · steal {avg(steal) or 0:.1f} %"
               f" · load {avg(load) or 0:.1f} (peak {max([x for x in load if x is not None] or [0]):.1f}) for {facts['cores']} cores")
    a, p = avg(some), pct(some, 95)
    if a is not None:
        out.append(f"  waiting for a processor (PSI cpu some): average {a:.1f} %, 95 % of the time under {p:.1f} %")
    level = "bad" if (a or 0) >= CPU_PSI_BAD else "warn" if (a or 0) >= CPU_PSI_WARN or (pct(busy, 95) or 0) >= 90 else "ok"
    if (avg(steal) or 0) >= STEAL_BAD:
        level = "bad"
        fd.suggest(1, f"processor time stolen by another hypervisor (steal {avg(steal):.0f} %): this host is itself virtualized or overbooked — ask the provider or move it")
    fd.verdict("cpu", level, {"ok": "processors are not a limit", "warn": "processors are sometimes saturated (tasks wait for a core)",
                              "bad": "processors are the LIMIT: tasks wait for a core a large part of the time"}[level])
    if facts["governor"] in ("powersave", "conservative", "ondemand") and level != "ok":
        fd.suggest(2, f"CPU frequency governor « {facts['governor']} » while the processors are busy: « performance » keeps the frequency up (more power used) — "
                      "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor (permanent: cpufrequtils or a systemd unit)")


def analyze_memory(samples, facts, zfs, fd, out):
    mem = facts["mem"]
    total = mem.get("MemTotal", 0)
    avail = [s["mem"].get("MemAvailable") for s in samples if s.get("mem")]
    swap_used = (mem.get("SwapTotal", 0) - mem.get("SwapFree", 0))
    some = [s["psi"].get("memory", {}).get("some") for s in samples]
    full = [s["psi"].get("memory", {}).get("full") for s in samples]
    out.append(f"MEMORY — {gib(total)} total, available at least {gib(min([x for x in avail if x] or [0]))} (average {gib(avg(avail) or 0)}) · swap used {gib(swap_used)}"
               f" · swappiness {facts['swappiness'] or '?'} · KSM {'on' if facts['ksm'] == '1' else 'off'}" + (f" ({int(facts['ksm_sharing']) * 4 // 1024} MiB shared)" if facts["ksm"] == "1" and facts["ksm_sharing"].isdigit() else ""))
    a, af = avg(some), avg(full)
    if a is not None:
        out.append(f"  waiting for memory (PSI memory): some {a:.1f} %, full {af or 0:.1f} % on average (reclaim, swap)")
    arcs = [s["arc"] for s in samples if s.get("arc")]
    arc_line = ""
    if arcs:
        hits = [x["hit"] for x in arcs if x.get("hit") is not None]
        size, cmax = arcs[-1]["size"], arcs[-1]["c_max"]
        arc_line = f"  ZFS ARC: {size / 2 ** 30:.1f} GiB used, maximum {cmax / 2 ** 30:.1f} GiB ({100 * cmax / max(total * 1024, 1):.0f} % of the RAM) · hit ratio {min(100.0, avg(hits) or 0):.1f} % (95 % of the samples above {min(100.0, pct(hits, 5) or 0):.1f} %)"
        out.append(arc_line)
        throttle = sum(x.get("throttle", 0) for x in arcs)
        if throttle:
            out.append(f"  {tag('warn')} ARC memory throttle: {throttle} times — the ARC had to give memory back under pressure")
    level = "bad" if (a or 0) >= MEM_PSI_BAD else "warn" if (a or 0) >= MEM_PSI_WARN or (avail and min(x for x in avail if x) < total * 0.05) else "ok"
    fd.verdict("memory", level, {"ok": "memory is not a limit", "warn": "memory is tight (reclaim or swap at times)",
                                 "bad": "memory is the LIMIT: tasks wait for memory (reclaim, swap) a large part of the time"}[level])
    if swap_used > 512 * 1024 and facts["swappiness"].isdigit() and int(facts["swappiness"]) > 10:
        fd.suggest(2, f"swap in use ({gib(swap_used)}) with vm.swappiness={facts['swappiness']}: on a ZFS host, 10 (or 1) keeps the guests in RAM",
                   lambda: apply_swappiness(10), "vm.swappiness=10 now and in " + SYSCTL_FILE)
    if arcs:
        cmax_gb, total_gb = arcs[-1]["c_max"] / 2 ** 30, total / 1048576
        hit = avg([x["hit"] for x in arcs if x.get("hit") is not None]) or 0
        if level != "ok" and cmax_gb > total_gb * 0.5:
            target = max(2, int(total_gb * 0.25))
            fd.suggest(1, f"memory short while the ZFS ARC may take up to {cmax_gb:.0f} GiB: limit it to about {target} GiB so the guests keep their memory",
                       lambda t=target: apply_arc_max(t), f"zfs_arc_max = {target} GiB (now and at boot)")
        elif level == "ok" and hit < 85 and (avg(avail) or 0) > total * 0.3:
            target = int(min(total_gb * 0.5, cmax_gb * 2 + 2))
            if target > cmax_gb + 1:
                fd.suggest(1, f"ARC hit ratio only {hit:.0f} % while {gib(avg(avail) or 0)} of RAM stay free: a larger ARC ({target} GiB) serves more reads from RAM — "
                              "the cheapest way to make HDD feel faster", lambda t=target: apply_arc_max(t), f"zfs_arc_max = {target} GiB (now and at boot)")
    return arc_line


def analyze_disks(samples, facts, smart, fd, out):
    """Per disk: % utilization, operations, throughput, wait per operation; verdict per disk and for the I/O waits of the whole host."""
    io_some = [s["psi"].get("io", {}).get("some") for s in samples]
    io_full = [s["psi"].get("io", {}).get("full") for s in samples]
    devices = sorted({d for s in samples for d in s["disks"]})
    zvols, names_of = (zvol_names(), guest_names()) if any(d.startswith("zd") for d in devices) else ({}, {})
    out.append("DISKS — % of the time busy (utilization), operations and throughput per second, wait per operation (ms)")
    h = [T(x) for x in ("device", "type", "util avg", "p95", "max", "read/s", "write/s", "MB/s r", "MB/s w", "wait r", "wait w", "model")]
    out.append(f"  {h[0]:<10} {h[1]:<5} {h[2]:>8} {h[3]:>5} {h[4]:>5}  {h[5]:>7} {h[6]:>7}  {h[7]:>6} {h[8]:>6}  {h[9]:>7} {h[10]:>7}  {h[11]}")
    worst = []
    for dev in devices:
        vals = [s["disks"][dev] for s in samples if dev in s["disks"]]
        util = [v["util"] for v in vals]
        rw = [v["r_await"] for v in vals if v["r_await"] is not None and v["r_s"] >= 0.5]
        ww = [v["w_await"] for v in vals if v["w_await"] is not None and v["w_s"] >= 0.5]
        info = facts["disks"].get(dev, {"kind": "zvol" if dev.startswith("zd") else "RAID" if dev.startswith("md") else "?", "model": "", "scheduler": ""})
        if dev in zvols and not info.get("model"):           # 1.11: zd16 -> data/zd0/vm-433-disk-0 (bbb3-26)
            m = GUEST_DATASET_RE.search(zvols[dev])
            info = dict(info, model=zvols[dev] + (f" ({names_of[m.group(1)][1]})" if m and m.group(1) in names_of and names_of[m.group(1)][1] else ""))
        if dev.startswith("zd") and (max(util or [0]) < 1):
            continue                         # idle ZFS volumes: noise
        r95, w95 = pct(rw, 95), pct(ww, 95)
        line = (f"  {dev:<10} {info['kind']:<5} {avg(util) or 0:>7.0f}% {pct(util, 95) or 0:>4.0f}% {max(util or [0]):>4.0f}%  {avg([v['r_s'] for v in vals]) or 0:>7.1f} "
                f"{avg([v['w_s'] for v in vals]) or 0:>7.1f}  {(avg([v['rkb_s'] for v in vals]) or 0) / 1024:>6.1f} {(avg([v['wkb_s'] for v in vals]) or 0) / 1024:>6.1f}  "
                f"{(f'{r95:.1f}' if r95 is not None else '-'):>7} {(f'{w95:.1f}' if w95 is not None else '-'):>7}  {info.get('model', '')}")
        out.append(line)
        if dev.startswith("zd"):
            continue
        slow_limit = AWAIT_HDD_BAD if info["kind"] == "HDD" else AWAIT_SSD_BAD
        u95 = pct(util, 95) or 0
        slow = max(r95 or 0, w95 or 0) >= slow_limit
        if u95 >= UTIL_BAD or (u95 >= UTIL_WARN and slow):
            worst.append((dev, info["kind"], u95, max(r95 or 0, w95 or 0), "bad"))
        elif u95 >= UTIL_WARN or slow:
            worst.append((dev, info["kind"], u95, max(r95 or 0, w95 or 0), "warn"))
        if smart.get(dev) == "FAILED":
            out.append(f"  {tag('bad')} {dev}: SMART health FAILED — replace this disk (a failing disk retries and slows the whole pool)")
            fd.suggest(1, f"{dev}: SMART health FAILED — replace it before anything else")
        if info.get("scheduler") in ("cfq", "bfq") and info["kind"] in ("SSD", "NVMe"):
            fd.suggest(3, f"{dev} ({info['kind']}) uses the « {info['scheduler']} » scheduler: « none » or « mq-deadline » suit SSD better")
    out.append("  (wait = 95th percentile of the samples with activity; « p95 » = 95 % of the samples under this value)")
    a, af = avg(io_some), avg(io_full)
    if a is not None:
        out.append(f"  waiting for the disks (PSI io): some {a:.1f} % (95 % under {pct(io_some, 95) or 0:.1f} %, peak {max([x for x in io_some if x is not None] or [0]):.0f} %), "
                   f"full {af or 0:.1f} % — % of the time at least one task / all the tasks waited for the disk")
    level = "ok"
    if (a or 0) >= IO_PSI_BAD or (af or 0) >= IO_FULL_BAD or any(w[4] == "bad" for w in worst):
        level = "bad"
    elif (a or 0) >= IO_PSI_WARN or worst:
        level = "warn"
    fd.verdict("disks", level, {"ok": "disks are not a limit", "warn": "disks are busy at times (waits during peaks)",
                                "bad": "disks are the LIMIT: tasks wait for the disk a large part of the time"}[level])
    return worst, a, af


def analyze_zfs(zfs, facts, worst, io_avg, fd, out, names=None):
    if not zfs:
        return
    out.append("ZFS")
    for name, p in zfs["pools"].items():
        kinds = sorted({facts["disks"].get(d, {}).get("kind", "?") for d in facts["disks"]})
        extra = [x for x in ("special", "log", "cache") if p[x]]
        out.append(f"  pool {name} — {p['size'] / 1e12:.2f} TB, used {p['cap']} %, fragmentation {p['frag']} %, {p['health']}, ashift {p['ashift'] or '?'}, vdevs "
                   f"{', '.join(sorted(set(p['vdevs']))) or 'single disks'}" + (f", devices: {', '.join(extra)}" if extra else ", no special / log / cache device"))
        lat = p.get("latency") or {}
        if lat:
            names_l = {"total_r": "total read", "total_w": "total write", "disk_r": "disk read", "disk_w": "disk write", "syncq_w": "sync queue write", "asyncq_w": "async queue write"}
            parts = [f"{T(names_l[k])} {v:.1f} ms" for k, v in lat.items() if v is not None]
            out.append(f"    average waits since the pool was imported: {', '.join(parts)}")
        if p["scrub"]:
            out.append(f"    {tag('warn')} {p['scrub']} — a scrub / resilver in progress slows everything down: measure again after it")
            fd.suggest(2, f"pool {name}: scrub or resilver in progress during the measurement — schedule scrubs at night (they are, by default, the second Sunday of the month)")
        if p["health"] != "ONLINE":
            fd.suggest(1, f"pool {name} is {p['health']}: zpool status -x, replace the faulty disk first")
        if p["cap"].isdigit() and int(p["cap"]) >= 80:
            fd.suggest(1 if int(p["cap"]) >= 90 else 2, f"pool {name}: used {p['cap']} % — ZFS slows down strongly beyond 80 % (block allocation) — free space or add disks")
        if p["frag"].isdigit() and int(p["frag"]) >= 50:
            fd.suggest(3, f"pool {name}: fragmentation {p['frag']} % — the writes get slower; only a copy to a new pool (zfs send / receive) removes it")
        if p["ashift"] in ("9",) and any(k in ("HDD", "SSD") for k in kinds):
            fd.suggest(2, f"pool {name}: ashift=9 (512-byte sectors) on recent disks (4K sectors): each write costs a read-modify-write — only a new pool (ashift=12) fixes it")
        sync_w = lat.get("syncq_w") or 0
        if sync_w >= 20 and not p["log"]:
            fd.suggest(2, f"pool {name}: synchronous writes wait {sync_w:.0f} ms on average (PostgreSQL commits, NFS…): a small mirrored SSD « log » device (SLOG) "
                          "makes them fast without replacing the HDD")
    # 1.10: one line per dataset where the value is SET; the datasets that inherit it are counted, not repeated
    tuned = 0
    for name, heirs in inherited_groups(zfs, "compression", lambda p: p.get("compression") == "off"):
        if tuned < 6:
            tuned += 1
            fd.suggest(2, f"dataset {name}{and_heirs(heirs)}: compression off — lz4 (or zstd) is almost free in processor and reduces the disk reads and writes (new data only)",
                       lambda n=name: run_set(["zfs", "set", "compression=lz4", n]), f"zfs set compression=lz4 {name}")
    for name, heirs in inherited_groups(zfs, "atime", lambda p: p.get("atime") == "on" and p.get("relatime") != "on"):
        if tuned < 6:
            tuned += 1
            fd.suggest(2, f"dataset {name}{and_heirs(heirs)}: atime=on without relatime — every read writes the access time; atime=off removes these writes",
                       lambda n=name: run_set(["zfs", "set", "atime=off", n]), f"zfs set atime=off {name}")
    for name, heirs in inherited_groups(zfs, "sync", lambda p: p.get("sync") == "disabled"):
        fd.suggest(1, f"dataset {name}{and_heirs(heirs)}: sync=disabled — fast but an outage can lose the last seconds of committed transactions (PostgreSQL!): « standard » unless deliberate"
                      + (" (on HDD without a « log » device, « standard » makes every commit wait for the disk: add the SLOG first)" if not any(p["log"] for p in zfs["pools"].values()) else ""))
    hdd_pool = any(facts["disks"][d]["kind"] == "HDD" for d in facts["disks"])
    if hdd_pool and not any(p["special"] for p in zfs["pools"].values()) and (io_avg or 0) >= IO_PSI_WARN:
        fd.suggest(2, "HDD pool without « special » device: two small mirrored SSD as special vdev hold the metadata and the small blocks (zfs set special_small_blocks=16K): "
                      "most of the random reads of PostgreSQL then hit SSD — an intermediate step before replacing all the disks")
    zfs_space(zfs, names or {}, fd, out)
    found = postgres_datasets(zfs, names or {})            # 1.24: the dataset of each container that holds PostgreSQL
    for vmid, gname, ds, mp, rs in found:
        if rs == str(PG_RECORDSIZE):
            out.append(f"  {tag('ok')} container {vmid} ({gname}): PostgreSQL on dataset {ds} (mounted at {mp}) with recordsize=16K")
            continue
        cmd = f"zfs set recordsize=16K {ds}"
        text = (f"container {vmid} ({gname}): PostgreSQL on dataset {ds} (mounted at {mp}) with recordsize={str(int(rs) // 1024) + 'K' if rs.isdigit() else rs or '?'} — "
                "16K suits its 8 KiB pages (fewer bytes read and rewritten per page); only the files written AFTER the change get it: the existing tables keep "
                "their blocks until they are rewritten (pg_dump and restore, or VACUUM FULL)")
        fd.suggest(2, text, lambda d=ds: run_set(["zfs", "set", "recordsize=16K", d]), cmd)
        fd.ask(text, [cmd])
    if not found:
        out.append("  (PostgreSQL / Odoo container: recordsize=16K on its dataset suits the 8 KiB pages of PostgreSQL; only for new files: set it before a restore)")


# ---------------------------------------------------------------------------------------------------------------- --io-latency (1.23)
BCC_INSTALL = "apt-get install -y bpfcc-tools proxmox-headers-$(uname -r)"


# ---------------------------------------------------------------------------------------------------------------- required packages (1.25)
APT_ENV = dict(os.environ, DEBIAN_FRONTEND="noninteractive", NEEDRESTART_MODE="a")


def apt_has(package):
    """True when apt knows this package (apt-cache show)."""
    code, _out = run(["apt-cache", "show", package], timeout=60)
    return code == 0


def headers_package():
    """The kernel headers of the RUNNING kernel: proxmox-headers-X (Proxmox 8 and 9), pve-headers-X (older Proxmox), else linux-headers-X."""
    release = os.uname().release
    for name in (f"proxmox-headers-{release}", f"pve-headers-{release}", f"linux-headers-{release}"):
        if apt_has(name):
            return name
    return None


def install_packages(packages, why):
    """1.25: installs the missing packages with apt-get (root), output shown as it goes; True when they are installed. Never fatal: on failure the
    program goes on without the function that needed them."""
    packages = [p for p in packages if p]
    if not packages:
        return False
    if os.geteuid() != 0:
        eprint(f"WARNING: {why}: {' '.join(packages)} missing and not installed (root required).")
        return False
    if not shutil.which("apt-get"):
        eprint(f"WARNING: {why}: {' '.join(packages)} missing and not installed (apt-get not found).")
        return False
    eprint(f"Installing the required packages ({why}): {' '.join(packages)}")
    try:
        code = subprocess.call(["apt-get", "install", "-y", "--no-install-recommends"] + packages, stdout=sys.stderr, stderr=sys.stderr,
                               stdin=subprocess.DEVNULL, env=APT_ENV, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        eprint(f"WARNING: installation of {' '.join(packages)} failed ({e}).")
        return False
    if code != 0:
        eprint(f"WARNING: apt-get install {' '.join(packages)} failed (exit code {code}): the program goes on without it.")
        return False
    eprint(f"  [OK] installed: {' '.join(packages)}")
    return True


def ensure_required(args):
    """1.25: every program installs what it needs. smartctl (smartmontools) for the health of the disks; with --io-latency, zfsslower (bpfcc-tools)
    and the headers of the running kernel that bcc needs to compile its probe."""
    if not shutil.which("smartctl"):
        install_packages(["smartmontools"], "health of the disks (smartctl)")
    if getattr(args, "io_latency", None) is not None and IOLAT is not None and IOLAT.Tracer(20).find_slow_tool() is None:
        install_packages(["bpfcc-tools", headers_package()], "--io-latency: ZFS operations file by file (zfsslower)")


def start_io_latency(threshold, interval, zfs, names=None, guests=None):
    """1.23: the tracer of apps/_iolatency.py started (None if the module is missing). Root needed for the delay accounting and zfsslower."""
    if IOLAT is None:
        eprint("WARNING: component apps/_iolatency.py missing: --io-latency ignored (copy the whole folder, apps/ included).")
        return None
    if os.geteuid() != 0:
        eprint("WARNING: --io-latency without root: the kernel delay accounting and zfsslower are unreadable; only the ZFS waits are measured.")
    tracer = IOLAT.Tracer(threshold, interval, pools=list((zfs or {}).get("pools", {})))
    tracer.start()
    tracer.pg = pg_start(zfs, names or {}, guests or {})       # 1.26: PostgreSQL of each container, snapshot at the start
    if tracer.state == "enabled":
        eprint("--io-latency: kernel.task_delayacct switched on for the measurement (it is switched off again at the end).")
    if tracer.slow_tool:
        eprint(f"--io-latency: {tracer.slow_tool} traces the ZFS operations slower than {threshold:g} ms.")
    if tracer.filetop_proc is not None:
        eprint("--io-latency: filetop counts the reads and writes of each file.")
    if tracer.bio_proc is not None:
        eprint("--io-latency: biolatency measures the response time of each disk.")
    for vmid, p in sorted(tracer.pg.items()):
        if p.get("before") is not None:
            eprint(f"--io-latency: PostgreSQL of guest {vmid}: tables" + (" and SQL queries" if p["settings"][2] and p["settings"][3] else "") + " measured.")
    return tracer


def pg_runner(vmid):
    """1.26: runs a command inside container VMID (pct exec), 60 s at most."""
    return lambda cmd: guest_exec(vmid, "lxc", cmd, 60)


def pg_start(zfs, names, guests):
    """1.26: {vmid: {"settings", "before"}} for each RUNNING container that holds PostgreSQL (postgres_datasets): what it read from the disk is
    counted from here (pg_statio_user_tables, pg_stat_statements when it is loaded)."""
    res = {}
    if IOLAT is None or not hasattr(IOLAT, "pg_settings") or os.geteuid() != 0:
        return res
    for vmid, _gname, _ds, _mp, _rs in postgres_datasets(zfs, names):
        if vmid not in guests:
            continue
        settings = IOLAT.pg_settings(pg_runner(vmid))
        if settings is None:
            res[vmid] = {"settings": None, "before": None}
            continue
        res[vmid] = {"settings": settings, "before": IOLAT.pg_snapshot(pg_runner(vmid), settings[0], settings[2] and settings[3])}
    return res


def pg_finish(tracer):
    """1.26: the second snapshot of each PostgreSQL and the difference: {vmid: {"settings", "tables", "statements"}}."""
    res = {}
    for vmid, p in sorted((getattr(tracer, "pg", None) or {}).items()):
        if p.get("before") is None:
            res[vmid] = {"settings": None, "tables": [], "statements": []}
            continue
        s = p["settings"]
        after = IOLAT.pg_snapshot(pg_runner(vmid), s[0], s[2] and s[3])
        tables, statements = IOLAT.pg_difference(p["before"], after)
        res[vmid] = {"settings": s, "tables": tables, "statements": statements}
    return res


def io_results(tracer):
    """1.26: the results of the tracer and of PostgreSQL, or None without --io-latency."""
    if tracer is None:
        return None
    res = tracer.results()
    res["postgres"] = pg_finish(tracer)
    return res


def guest_label(guest, names):
    """« lxc 105 » -> « 105 odoo18 »; « host » -> « host »."""
    if not guest or " " not in guest:
        return guest or "?"
    vmid = guest.split(" ", 1)[1]
    name = (names or {}).get(vmid, ("", "", ""))[1]
    return f"{vmid} {name}".strip()


def analyze_io_latency(io, names, fd, out):
    """1.23: the processes that waited for the disks, the ZFS operations slower than the threshold (file by file) and the ZFS waits of the measurement."""
    threshold = io["slow"]["threshold"]
    out.append(f"WHO WAITS FOR THE DISKS (--io-latency, threshold {threshold:g} ms)")
    for pool, d in sorted(io.get("pools", {}).items()):
        r, w = d.get("read_ms") or [], d.get("write_ms") or []
        if not d.get("intervals"):
            continue
        line = f"  ZFS pool {pool} during the measurement ({d['intervals']} intervals): "
        if r:
            line += f"read wait average {avg(r):.1f} ms, 95 % under {pct(r, 95):.1f} ms, peak {max(r):.1f} ms"
            if d.get("disk_read_ms"):
                line += f" (of which the disk itself: average {avg(d['disk_read_ms']):.1f} ms)"
        else:
            line += "no read reached the disks (all served by the ARC)"
        if w:
            line += f" · write wait average {avg(w):.1f} ms, peak {max(w):.1f} ms"
        out.append(line)
        if r and pct(r, 95) >= AWAIT_HDD_BAD:
            fd.verdict("disks", "warn", f"pool {pool}: reads waited {pct(r, 95):.0f} ms or more in 5 % of the intervals (--io-latency)")
    if io["delayacct"] == "unavailable":
        out.append("  Waits per process: unavailable (kernel.task_delayacct unreadable: root needed, or a kernel without delay accounting)")
    elif not io["procs"]:
        out.append("  Waits per process: no process waited for the disks during the measurement")
    else:
        out.append("  Processes that waited the most for the disks (kernel delay accounting, during the measurement):")
        out.append("          wait  guest                    process          pid")
        for p in io["procs"]:
            out.append(f"      {p['wait_s']:>6.1f} s  {guest_label(p['guest'], names)[:24]:<24} {p['comm'][:16]:<16} {p['pid']}")
    slow = io["slow"]
    if not slow["tool"]:
        out.append("  File names: zfsslower (bpfcc-tools) is not installed: the slow ZFS operations are not traced file by file")
        fd.ask("--io-latency: install bpfcc-tools (zfsslower: the ZFS operations slower than a threshold, with the process and the file)", [BCC_INSTALL])
    elif slow["error"] and not slow["count"]:
        out.append(f"  File names: zfsslower failed: {slow['error']}")
    elif not slow["count"]:
        out.append(f"  ZFS operations slower than {threshold:g} ms: none — no read, write, open or fsync of a file waited that long: the disks did not slow the applications down during the measurement")
    else:
        out.append(f"  ZFS operations slower than {threshold:g} ms: {slow['count']} — the files that cost the most:")
        out.append("       count     total     peak  op     guest                  process         file")
        for f in slow["files"]:
            out.append(f"      {f['count']:>6} {f['total_ms'] / 1000:>7.1f} s {f['max_ms']:>6.0f} ms  {f['op']:<6} {guest_label(f['guest'], names)[:22]:<22} {f['comm'][:15]:<15} {f['file'][:60]}")
    top = (io.get("filetop") or {})
    if top.get("tool") and top.get("files"):
        out.append("  Files the most read and written (filetop, page cache included: what the programs ask, not only what reaches the disks):")
        out.append("        read     written   reads  writes  guest                  process         file")
        for f in top["files"]:
            out.append(f"      {f['rkb'] / 1024:>6.1f} MiB {f['wkb'] / 1024:>6.1f} MiB {f['reads']:>7} {f['writes']:>7}  {guest_label(f['guest'], names)[:22]:<22} {f['comm'][:15]:<15} {f['file'][:60]}")
    elif top.get("tool"):
        out.append("  Files the most read and written (filetop): no file read or written during the measurement")
    bio = (io.get("biolatency") or {})
    if bio.get("tool") and bio.get("disks"):
        out.append("  Response time of each disk (biolatency, every operation of the measurement):")
        for disk, rows in sorted(bio["disks"].items()):
            total, p20, p100, worst = IOLAT.latency_summary(rows)
            if total:
                out.append(f"      {disk:<8} {total:>9} operations · {p20:5.1f} % at 16 ms or more · {p100:5.1f} % at 128 ms or more · slowest between {worst} ms")
                if p100 >= 1.0:
                    fd.verdict("disks", "warn", f"disk {disk}: {p100:.1f} % of the operations took 128 ms or more (--io-latency, biolatency)")
    for vmid, p in sorted((io.get("postgres") or {}).items()):
        label = guest_label("lxc " + vmid, names)
        st = p.get("settings")
        if st is None:
            out.append(f"  PostgreSQL of {label}: unreachable (pct exec, user postgres, psql)")
            continue
        _v, tio, pss, ext, spl = st
        if p["tables"]:
            out.append(f"  PostgreSQL of {label}: tables the most read from the DISK during the measurement (8 KiB blocks not found in the memory of PostgreSQL):")
            for t in p["tables"]:
                out.append(f"      {t['read_blocks'] * 8 / 1024:>7.1f} MiB read  ({t['hit_blocks'] * 8 / 1024:>8.1f} MiB from memory)  {t['db']}.{t['table']}")
        else:
            out.append(f"  PostgreSQL of {label}: no table read from the disk during the measurement (everything from the memory of PostgreSQL)")
        if pss and ext and p["statements"]:
            out.append(f"  PostgreSQL of {label}: SQL queries that read the most from the disk:")
            for q in p["statements"]:
                rt = f"{q['read_ms'] / 1000:>6.1f} s reading" if tio else "      -"
                out.append(f"      {rt}  {q['read_blocks'] * 8 / 1024:>7.1f} MiB  {q['calls']:>6} calls  {q['exec_ms'] / 1000:>7.1f} s in all  {q['db']}: {q['query'][:110]}")
        elif pss and ext:
            out.append(f"  PostgreSQL of {label}: no SQL query read from the disk during the measurement")
        missing = IOLAT.pg_enable_commands(spl, tio, pss, ext)
        if missing:
            parts = (["track_io_timing (time spent reading)"] if not tio else []) + (["pg_stat_statements (SQL queries)"] if not (pss and ext) else [])
            out.append(f"  PostgreSQL of {label}: not measured yet: {', '.join(parts)} — switched on by the [change] commands below")
            cmds = []
            for sql, restart in missing:
                cmds.append(f"pct exec {vmid} -- sh -c {shlex.quote(IOLAT.pg_command(sql))}")
                if restart:
                    cmds.append(f"pct exec {vmid} -- systemctl restart postgresql   # restarts PostgreSQL: Odoo is cut for a few seconds, at a quiet hour")
            fd.ask(f"--io-latency: PostgreSQL of {label}: switch on {', '.join(parts)}", cmds)
    out.append("  (compare these hours with the slow requests of the sites: app-log-live.py in the guest; a slow request with no slow ZFS operation at that time was not slowed by the disks)")


PG_RECORDSIZE = 16384
PG_FOLDER = "/var/lib/postgresql"


def postgres_datasets(zfs, names):
    """1.24: [(vmid, guest name, dataset, mount point in the guest, recordsize in bytes)] for each LXC container whose PostgreSQL folder
    (/var/lib/postgresql) is on a ZFS dataset: the mount point (rootfs, mpN) that holds that folder, its dataset, and the folder seen from the host."""
    res = []
    datasets = (zfs or {}).get("datasets", {})
    for vmid, (kind, gname, conf) in sorted(names.items()):
        if kind != "lxc":
            continue
        mounts = {}
        for m in re.finditer(r"^(rootfs|mp\d+):\s*([^,\s]+)(.*)$", conf, re.M):
            volume = m.group(2).split(":", 1)[-1]
            if m.group(1) == "rootfs":
                mounts["/"] = volume
            else:
                mp = re.search(r"(?:^|,)mp=([^,\s]+)", m.group(3))
                if mp:
                    mounts[mp.group(1).rstrip("/") or "/"] = volume
        holders = [p for p in mounts if p == "/" or PG_FOLDER == p or PG_FOLDER.startswith(p + "/")]
        if not holders:
            continue
        mp = max(holders, key=len)
        ds = next((d for d in datasets if d == mounts[mp] or d.endswith("/" + mounts[mp])), None)
        if not ds:
            continue
        host_mp = datasets[ds].get("mountpoint", "")
        inside = PG_FOLDER if mp == "/" else PG_FOLDER[len(mp):]
        path = host_mp.rstrip("/") + inside
        if not host_mp.startswith("/") or not os.path.isdir(SYSPERF._p(path) if SYSPERF else path):
            continue
        res.append((vmid, gname, ds, mp, datasets[ds].get("recordsize", "")))
    return res


def analyze_network(samples, out):
    ifaces = sorted({i for s in samples for i in s.get("net", {})})
    rows = []
    for i in ifaces:
        vals = [s["net"][i] for s in samples if i in s.get("net", {})]
        rx, tx = [v["rx_kb_s"] for v in vals], [v["tx_kb_s"] for v in vals]
        errs, drops = sum(v["errors"] for v in vals), sum(v["drops"] for v in vals)
        if max(rx + tx + [0]) < 1 and not errs and not drops:
            continue
        rows.append(f"  {i:<16} received {(avg(rx) or 0) / 1024:6.2f} MB/s (peak {max(rx or [0]) / 1024:6.2f})  sent {(avg(tx) or 0) / 1024:6.2f} MB/s (peak {max(tx or [0]) / 1024:6.2f})"
                    + (f"  {tag('warn')} errors {errs}, drops {drops}" if errs or drops else ""))
    out.append("NETWORK")
    out.extend(rows or ["  no traffic measured"])


def analyze_guests(samples, names, top, out):
    ids = sorted({g for s in samples for g in s.get("guests", {})}, key=lambda x: int(x))
    if not ids:
        return []
    rows = []
    for vmid in ids:
        vals = [s["guests"][vmid] for s in samples if vmid in s.get("guests", {})]
        cpu = [v["cpu"] for v in vals]
        # 1.11: the ZFS counters of the guest's datasets when they exist (the cgroup counts nothing on ZFS), the cgroup otherwise
        zfs_seen = any("z_w_ops" in v for v in vals)
        io = [((v.get("z_r") or 0) + (v.get("z_w") or 0)) if zfs_seen else ((v["io_r"] or 0) + (v["io_w"] or 0)) for v in vals]
        w_ops = avg([v.get("z_w_ops") for v in vals if "z_w_ops" in v]) if zfs_seen else None
        r_ops = avg([v.get("z_r_ops") for v in vals if "z_r_ops" in v]) if zfs_seen else None
        some = [v["io_some"] for v in vals]
        mem = vals[-1]["mem"] or 0
        kind, name, _conf = names.get(vmid, ("?", "", ""))
        rows.append((avg(io) or 0, vmid, kind, name, avg(cpu) or 0, max([x for x in cpu if x is not None] or [0]), mem, vals[-1]["mem_max"], avg(some),
                     max([x for x in some if x is not None] or [0]), w_ops, r_ops))
    with_ops = any(r[10] is not None for r in rows)
    out.append(f"GUESTS — the {min(top, len(rows))} busiest on the disks (cgroup of each running container / VM)"
               + (" · ZFS counters of its datasets" if with_ops else ""))
    h = [T(x) for x in ("id", "type", "name", "CPU avg", "peak", "memory", "disk MB/s", "disk wait", "writes/s", "reads/s")]
    out.append(f"  {h[0]:>5} {h[1]:<4} {h[2]:<22} {h[3]:>8} {h[4]:>6}  {h[5]:>10}  {h[6]:>9}" + (f"  {h[8]:>8} {h[9]:>7}" if with_ops else "") + f"  {h[7]:>9} {h[4]:>6}")
    key = (lambda r: (r[10] or 0) + (r[11] or 0)) if with_ops else (lambda r: r[0])
    for io, vmid, kind, name, cpu, cpu_max, mem, mem_max, some, some_max, w_ops, r_ops in sorted(rows, key=key, reverse=True)[:top]:
        out.append(f"  {vmid:>5} {kind:<4} {name[:22]:<22} {cpu:>7.0f}% {cpu_max:>5.0f}%  {mem / 2 ** 30:>6.1f} GiB  {io / 1048576:>9.2f}"
                   + (f"  {w_ops or 0:>8.1f} {r_ops or 0:>7.1f}" if with_ops else "") + "  "
                   + (f"{some:>8.1f}% {some_max:>5.0f}%" if some is not None else f"{'-':>9} {'-':>6}"))
    out.append("  (CPU: 100 % = one full core; disk wait: % of the time the guest's tasks waited for the disk — the latency felt INSIDE it)")
    if with_ops:
        out.append("  (writes/s, reads/s: operations on the ZFS datasets of the guest, before the cache — what it asks of the pool)")
    waits = group_waits()
    if waits:
        out.append("  disk wait by group over the last minute: " + " · ".join(f"{g} {v:.1f} %" for g, v in waits) + " (lxc, qemu.slice: the guests; system.slice: the host's own services, backups included)")
    return rows


def guest_writers(rows, samples, facts, names, fd):
    """1.11: a guest that makes most of the writes of a pool of HDD, while the tasks wait for the disk: named, with how to find the writer inside it.
    On the host of 2026-11-14, two BigBlueButton VMs without a meeting made 60 % of the writes (ntopng, journald), and the reads of Odoo waited behind."""
    if not any(i.get("kind") == "HDD" for i in facts["disks"].values()):
        return
    io_some = avg([s["psi"].get("io", {}).get("some") for s in samples]) or 0
    total = sum(r[10] or 0 for r in rows)
    if io_some < IO_PSI_WARN or total < 5:
        return
    for _io, vmid, kind, name, *_rest in sorted(rows, key=lambda r: -(r[10] or 0)):
        w_ops = _rest[6] or 0
        share = w_ops / total
        if share < 0.25 or w_ops < 5:
            break
        inside = "pidstat -d 10 6 (sysstat) or iotop -oPa" if kind == "vm" else f"pct exec {vmid} -- pidstat -d 10 6"
        fd.suggest(2, f"guest {vmid} ({name}) makes {share * 100:.0f} % of the writes of the guests ({w_ops:.0f} per second) while the tasks wait for the disk "
                      f"{io_some:.1f} % of the time — the reads of the other guests wait behind these writes on the HDD. Find the writer inside it: {inside}"
                      "; monitoring and logs are the usual cause (ntopng, atop, journald: journalctl --disk-usage, SystemMaxUse=) — or stop it when it is not used")
        look = "pidstat -d 10 3 2>/dev/null || iotop -boPa -n 3 -d 10; journalctl --disk-usage; docker ps -a --format \"{{.Names}} {{.Status}}\" 2>/dev/null"
        if kind == "lxc":
            fd.ask(f"guest {vmid} ({name}): what writes inside it", [f"pct exec {vmid} -- sh -c '{look}'"])
        elif guest_agent(names.get(vmid, ("", "", ""))[2]):
            fd.ask(f"guest {vmid} ({name}): what writes inside it", [f"qm guest exec {vmid} --timeout 60 -- sh -c '{look}'"])
        else:
            fd.ask(f"guest {vmid} ({name}): what writes inside it - run INSIDE the VM (or enable the guest agent and use --inside)", [look])


SNAPSHOT_OLD_DAYS = 60          # 1.14: a snapshot older than this is no longer a way back, only room that is kept


def old_snapshots(names, zfs):
    """1.14: snapshots of the guests older than SNAPSHOT_OLD_DAYS: {guest id: {"names": [(snapshot, creation)], "reclaim": bytes, "exact": bool, "pool": name}}.
    The room that deleting them gives back is asked to ZFS itself (zfs destroy -n: a dry run, nothing is destroyed): the « used » of each snapshot
    counts only what it holds alone, so their sum is less than what removing several at once frees. The memory image kept by a snapshot of a
    running VM (vm-ID-state-NAME) is counted too."""
    limit = time.time() - SNAPSHOT_OLD_DAYS * 86400
    per_dataset = {}
    for name, _used, created in (zfs or {}).get("snapshots", []):
        dataset, _at, snap = name.partition("@")
        m = GUEST_DATASET_RE.search(dataset)
        if m and created < limit and not snap.startswith("__") and snap != "vzdump" and m.group(1) in names:
            per_dataset.setdefault((m.group(1), dataset), []).append((snap, created))
    res = {}
    for (vmid, dataset), snaps in sorted(per_dataset.items()):
        g = res.setdefault(vmid, {"names": {}, "reclaim": 0, "exact": True, "pool": dataset.split("/")[0]})
        for snap, created in snaps:
            g["names"][snap] = min(created, g["names"].get(snap, created))
        code, out = run(["zfs", "destroy", "-nvp", f"{dataset}@" + ",".join(sn for sn, _c in snaps)], timeout=60)
        m = re.search(r"^reclaim\s+(\d+)", out or "", re.M)
        if code == 0 and m:
            g["reclaim"] += int(m.group(1))
        else:
            g["exact"] = False
            g["reclaim"] += sum(u for n, u, _c in zfs["snapshots"] if n.partition("@")[0] == dataset and n.partition("@")[2] in {sn for sn, _c in snaps})
    for vmid, g in res.items():
        for dataset, props in (zfs or {}).get("datasets", {}).items():
            m = re.search(rf"/vm-{vmid}-state-(.+)$", dataset)
            if m and m.group(1) in g["names"] and props.get("used", "").isdigit():
                g["reclaim"] += int(props["used"])
        g["names"] = sorted(g["names"].items(), key=lambda x: x[1])
    return res


def running_tasks():
    """1.16: {guest id: [task type]} of the Proxmox tasks running now (/var/log/pve/tasks/active: a line without end time, its process alive).
    A guest « locked (backup) » while its backup runs is normal: the lock goes away at the end of the backup."""
    res = {}
    for line in read_plain(TASKS_ACTIVE).splitlines():
        parts = line.split()
        u = parts[0].split(":") if parts else []
        if len(parts) != 1 or len(u) < 8 or u[0] != "UPID":
            continue
        try:
            alive = os.path.exists(f"/proc/{int(u[2], 16)}") if TASKS_ACTIVE == "/var/log/pve/tasks/active" else True
        except ValueError:
            continue
        if alive:
            res.setdefault(u[6], []).append(u[5])
    return res


def guest_config_check(names, running, zfs):
    """1.13: is each container and VM well configured? [(level major | improve | note, guest id, text, [commands])] read from /etc/pve, nothing changed.
    « major »: data that is not backed up or can be lost, a guest that will not come back after a restart of the host, memory promised twice.
    The mount points of a container (mpN) are NOT in its backups unless backup=1: a restore then brings back the system without its data."""
    res = []
    jobs = [o for kind, _n, o in pve_sections(os.path.join(PVE_DIR, "jobs.cfg")) if kind == "vzdump" and o.get("enabled") != "0"]

    def backed_up(vmid):
        for o in jobs:
            if o.get("pool"):
                return True                                  # a resource pool: its members are not listed here, assumed covered
            if o.get("all") == "1" and vmid not in re.split(r"[,; ]+", o.get("exclude", "")):
                return True
            if vmid in re.split(r"[,; ]+", o.get("vmid", "")):
                return True
        return False
    promised = 0
    snapshots = old_snapshots(names, zfs)
    busy = running_tasks()
    for vmid, (kind, name, conf) in sorted(names.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        on = vmid in running
        who = ("container " if kind == "lxc" else "VM ") + f"{vmid} ({name})"
        tool = "pct" if kind == "lxc" else "qm"
        get = lambda key, default="": (re.search(rf"^{key}:\s*(.+)$", conf, re.M) or [None, default])[1].strip()
        if re.search(r"^template:\s*1", conf, re.M):
            continue
        before, good = len(res), []
        memory = int(get("memory", "512")) if get("memory", "512").isdigit() else 512
        if on:
            promised += memory
        if on and get("onboot", "0") == "1":
            good.append("starts with the host")
        if jobs and on and backed_up(vmid):
            good.append("in a backup job")
        if on and get("onboot", "0") != "1":
            res.append(("major", vmid, f"{who}: runs now but does not start with the host (onboot missing) — after a restart or a power cut of the host it stays stopped",
                        [f"{tool} set {vmid} --onboot 1"]))
        if jobs and on and not backed_up(vmid):
            res.append(("major", vmid, f"{who}: in no scheduled backup job — nothing to restore if its disk is lost", ["grep -A8 vzdump /etc/pve/jobs.cfg"]))
        in_progress = busy.get(vmid, [])
        if get("lock") and in_progress:                   # 1.16: a backup running now is not an interrupted one: never offer unlock
            res.append(("note", vmid, f"{who}: locked ({get('lock')}) by a task running now ({', '.join(sorted(set(in_progress)))}) — normal; "
                        "snapshots and changes of this guest wait for its end", []))
        elif get("lock"):
            res.append(("improve", vmid, f"{who}: locked ({get('lock')}) and no task of it is running — a backup or a snapshot was interrupted; backups and changes are refused while it stays",
                        [f"{tool} unlock {vmid}   # only when no backup or snapshot of it is running"]))
        unused = re.findall(r"^(unused\d+):\s*(\S+)", conf, re.M)
        if unused:
            res.append(("note", vmid, f"{who}: {len(unused)} unused disks kept ({', '.join(v for _k, v in unused[:3])}) — they still take room in the pool", []))
        if kind == "lxc":
            if get("unprivileged", "0") != "1":
                res.append(("improve", vmid, f"{who}: privileged container (unprivileged: 1 missing) — root inside it is root on the host if it escapes; "
                            "the conversion goes through a backup and a restore with --unprivileged", []))
            for m in re.finditer(r"^(mp\d+):\s*([^,\s]+)(?:,(.*))?$", conf, re.M):
                key, volume, opts = m.group(1), m.group(2), m.group(3) or ""
                where = (re.search(r"mp=([^,\s]+)", opts) or [None, "?"])[1]
                if volume.startswith("/"):
                    res.append(("note", vmid, f"{who}: {key} ({where}) is a folder of the host ({volume}) — never in the backups of the container: back it up on the host", []))
                elif not re.search(r"backup=1", opts):
                    res.append(("major", vmid, f"{who}: mount point {key} ({where}) is NOT in the backups (backup=1 missing) — only the root disk is saved: "
                                "a restore brings back the system without the data of this mount point",
                                [f"pct set {vmid} --{key} {volume},{','.join(o for o in opts.split(',') if o)},backup=1"]))
            volumes = [m.group(1) for m in re.finditer(r"^(mp\d+):\s*([^/,\s][^,\s]*)(?:,(.*))?$", conf, re.M)]
            if not any(r[1] == vmid and "NOT in the backups" in r[2] for r in res[before:]):
                good.append("disks in the backups: rootfs" + "".join(f", {v}" for v in volumes))
            if get("unprivileged", "0") == "1":
                good.append("unprivileged")
            for raw in re.findall(r"^(lxc\.[\w.]+):\s*(.+)$", conf, re.M):
                if "apparmor" in raw[0] and "unconfined" in raw[1]:
                    res.append(("improve", vmid, f"{who}: AppArmor disabled ({raw[0]}: {raw[1]}) — the container is no longer confined by the host", []))
            if not get("cores") and not get("cpulimit"):
                res.append(("note", vmid, f"{who}: no processor limit (cores) — it can use every core of the host", [f"pct set {vmid} --cores 4"]))
            if get("swap", "512") == "0" and memory < 1024:
                res.append(("note", vmid, f"{who}: {memory} MiB of memory and no swap — a peak kills its processes (OOM)", []))
        else:
            if not guest_agent(conf):
                res.append(("improve", vmid, f"{who}: QEMU guest agent not enabled — backups cannot freeze its file systems (less consistent), and --inside cannot look in it",
                            [f"qm set {vmid} --agent enabled=1", "apt install -y qemu-guest-agent   # INSIDE the VM, then stop and start the VM"]))
            for m in re.finditer(r"^((scsi|virtio|sata|ide)\d+):\s*([^,\s]+)(?:,(.*))?$", conf, re.M):
                disk, bus, volume, opts = m.group(1), m.group(2), m.group(3), m.group(4) or ""
                if "media=cdrom" in opts or volume == "none":
                    continue
                if "cache=unsafe" in opts:
                    res.append(("major", vmid, f"{who}: disk {disk} with cache=unsafe — the writes that the VM believes done are lost at a crash or a power cut of the host",
                                [f"qm set {vmid} --{disk} {volume},{','.join(o for o in opts.split(',') if o and not o.startswith('cache='))}"]))
                if "backup=0" in opts:
                    res.append(("major", vmid, f"{who}: disk {disk} is excluded from the backups (backup=0)", []))
                if zfs and bus in ("scsi", "virtio") and "discard=on" not in opts and "cloudinit" not in volume:
                    res.append(("improve", vmid, f"{who}: disk {disk} without discard=on — the room freed in the VM is never given back to the pool",
                                [f"qm set {vmid} --{disk} {volume},{','.join(o for o in opts.split(',') if o)},discard=on   # applied at the next stop and start of the VM",
                                 f"qm guest exec {vmid} -- fstrim -av   # after that start: gives back to the pool the room already freed in the VM"]))
            for m in re.finditer(r"^(net\d+):\s*(\w+)=", conf, re.M):
                if m.group(2) in ("e1000", "rtl8139", "e1000e"):
                    res.append(("improve", vmid, f"{who}: network card {m.group(1)} emulated ({m.group(2)}) — « virtio » is faster and lighter for the host", []))
            if guest_agent(conf):
                good.append("guest agent enabled")
            if not any(r[1] == vmid and ("cache=unsafe" in r[2] or "backup=0" in r[2]) for r in res[before:]):
                good.append("every disk in the backups, none with an unsafe cache")
            if get("balloon") == "0" and memory >= 16384:
                res.append(("note", vmid, f"{who}: {memory // 1024} GiB of memory without ballooning — all of it is taken from the host as soon as the VM touched it", []))
        old = snapshots.get(vmid)
        if old:                                           # 1.14: old snapshots, and the room they keep
            listed = ", ".join(f"{sn} ({datetime.date.fromtimestamp(c)})" for sn, c in old["names"][:6]) + (f" and {len(old['names']) - 6} more" if len(old["names"]) > 6 else "")
            free = str(zfs.get("pools", {}).get(old["pool"], {}).get("free", "")) if zfs else ""    # 1.16: the FREE of zpool list, the column compared after
            res.append(("improve", vmid, f"{who}: {len(old['names'])} snapshots older than {SNAPSHOT_OLD_DAYS} days: {listed} — deleting them frees "
                        + ("" if old["exact"] else "at least ") + f"{size(old['reclaim'])} in pool {old['pool']}; a rollback to one of them would erase everything done since"
                        + (" (the guest is locked: run this program again once it is unlocked to get the commands)" if get("lock") else ""),
                        ([] if get("lock") else [f"{tool} delsnapshot {vmid} {sn}" for sn, _c in old["names"]])
                        + [f"zpool list -o name,alloc,free,cap {old['pool']}   # after: compare" + (f" with {size(int(free))} free before" if free.isdigit() else "")]))
        elif zfs and zfs.get("snapshots") is not None:
            good.append("no old snapshot")
        if good and not any(r[0] == "major" and r[1] == vmid for r in res[before:]):
            res.append(("ok", vmid, f"{who}: " + " · ".join(good), []))
    if running and not jobs and not [t for t in recent_tasks(days=7) if t[2] == "vzdump"]:
        res.append(("major", "", "host: no scheduled backup job and no backup in the last 7 days — nothing recent to restore for any guest",
                    ["cat /etc/pve/jobs.cfg", "tail -n 20 /var/log/pve/tasks/index"]))
    if sum(len(g["names"]) for g in snapshots.values()):
        res.append(("note", "", f"old snapshots: {sum(len(g['names']) for g in snapshots.values())} in all, {size(sum(g['reclaim'] for g in snapshots.values()))} to free by deleting them", []))
    total = 0
    m = re.search(r"^MemTotal:\s+(\d+) kB", read("/proc/meminfo") or "", re.M)
    if m:
        total = int(m.group(1)) // 1024
    if total and promised:
        share = promised * 100 // total
        if share > 100:
            res.append(("major", "", f"host: the running guests are promised {promised // 1024} GiB of memory for {total // 1024} GiB in the machine ({share} %) — "
                        "when they use it, the host kills processes (OOM) or swaps", []))
        elif share > 80 and zfs:
            res.append(("improve", "", f"host: the running guests are promised {share} % of the memory ({promised // 1024} of {total // 1024} GiB) — little is left for the ZFS cache (ARC), "
                        "which is what makes HDD bearable", []))
    return res


def print_config_check(found, checked, brief=False):
    """The verdict on the configurations of the guests: at the start of the program (brief: the major issues only, the rest counted) and in the report."""
    major = [f for f in found if f[0] == "major"]
    improve = [f for f in found if f[0] == "improve"]
    notes = [f for f in found if f[0] == "note"]
    print(f"GUEST CONFIGURATIONS — {checked} containers and VMs checked: {len(major)} major issues, {len(improve)} to improve, {len(notes)} notes"
          + (" (details at the end of the report)" if brief and (improve or notes) else ""))
    good = [f for f in found if f[0] == "ok"]
    for level, _vmid, text, _c in major + ([] if brief else improve + notes + good):
        print(f"  {tag({'major': 'bad', 'improve': 'warn', 'note': 'info', 'ok': 'ok'}[level])} {text}")
    if brief and major:
        print("  To correct quickly: the commands are in the block « COMMANDS » at the end.")
    elif brief and good:                                  # 1.14: said when all is well, not only when something is wrong
        print(f"  {tag('ok')} no major issue: {len(good)} guests checked for their start with the host, their backups (every disk and mount point) and their disk cache")
    if not major and not improve and not notes and not good:
        print(f"  {tag('ok')} nothing to correct in the configurations")


def guest_config_advice(names, fd):
    """Advice from the VM / container configurations of /etc/pve (never changed by the program: a VM restart is needed)."""
    for vmid, (kind, name, conf) in sorted(names.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        if kind != "vm":
            continue
        no_thread = []
        for m in re.finditer(r"^((scsi|virtio|sata|ide)\d+):\s*(.+)$", conf, re.M):
            disk, bus, opts = m.group(1), m.group(2), m.group(3)
            if "media=cdrom" in opts:
                continue
            if bus in ("sata", "ide"):
                fd.suggest(2, f"VM {vmid} ({name}): disk on the {bus.upper()} bus (emulated, slow) — VirtIO SCSI single with iothread=1 (driver needed in the guest)")
            if bus == "scsi" and "iothread=1" not in opts:
                no_thread.append(disk)                  # 1.10: one line per VM, the disks named
            cache = re.search(r"cache=(\w+)", opts)
            if cache and cache.group(1) in ("writeback", "unsafe"):
                fd.suggest(3, f"VM {vmid} ({name}): disk cache « {cache.group(1)} » on ZFS — double cache with the ARC; « none » is the usual choice")
        if no_thread:
            fd.suggest(3, f"VM {vmid} ({name}): SCSI disk without iothread=1: {', '.join(no_thread)} (with the « VirtIO SCSI single » controller, each disk gets its own I/O thread)")
        if re.search(r"^cpu:\s*kvm64", conf, re.M):
            fd.suggest(3, f"VM {vmid} ({name}): CPU type kvm64 hides the instructions of the real processor — « host » (or x86-64-v2-AES) is faster when migration is not needed")


def ssd_answer(fd, worst, io_avg, io_full, facts, guests_rows, out, host_tasks=()):
    """The answer to « are SSD disks justified? » from the measurements."""
    hdd = [d for d, v in facts["disks"].items() if v["kind"] == "HDD"]
    out.append("ARE SSD DISKS JUSTIFIED?")
    if not hdd:
        out.append("  no spinning disk (HDD) on this host: the question does not arise.")
        return
    bad = [w for w in worst if w[1] == "HDD" and w[4] == "bad"]
    io_avg, io_full = io_avg or 0, io_full or 0
    busiest = sorted(guests_rows, key=lambda r: -(r[8] or 0))[:1]
    if bad or io_avg >= IO_PSI_BAD or io_full >= IO_FULL_BAD:
        out.append(color("1;31", f"  YES: the HDD ({', '.join(hdd)}) are a measured bottleneck") + f" — tasks waited for the disk {io_avg:.1f} % of the time (all tasks {io_full:.1f} %)"
                   + (f", {bad[0][0]} busy {bad[0][2]:.0f} % with {bad[0][3]:.0f} ms per operation" if bad else "") + ".")
        out.append("  In order: ARC larger if RAM allows, « special » mirrored SSD (metadata + small blocks), SLOG for synchronous writes, then SSD for the pool of the busiest guest.")
    elif io_avg >= IO_PSI_WARN or worst:
        out.append(color("1;33", "  NOT YET: the HDD slow things down only at peaks") + f" (disk wait {io_avg:.1f} % on average). Measure over a full day (--duration 24h) including the backups"
                   " and the busiest hours; a larger ARC or a special SSD device would probably be enough.")
    else:
        out.append(color("1;32", "  NO: the HDD are not a limit for this load") + f" (disk wait {io_avg:.1f} % on average, no disk saturated). The slowness of the first page loads"
                   " after a restart is the cold cache (empty ARC and page cache), not the disk type: SATA HDD with ZFS are enough here.")
    if busiest and (busiest[0][8] or 0) >= 0.05:
        out.append(f"  Guest that waited most for the disk: {busiest[0][1]} {busiest[0][3]} ({busiest[0][8]:.1f} % of its time).")
    elif guests_rows and io_avg >= IO_PSI_WARN:          # 1.10: « 0.0 % of its time » contradicted the verdict
        out.append("  No guest waited for the disk during this measurement: the wait is in the tasks of the host itself (backup, copy, scrub, ZFS)"
                   + (f" — seen running: {', '.join(sorted(host_tasks))}" if host_tasks else "") + ". The guests feel it when they read what is not in memory: measure during their slow hours.")


# ---------------------------------------------------------------------------------------------------------------- --apply actions
def run_set(cmd):
    code, out = run(cmd, timeout=60)
    print(f"  {'done' if code == 0 else 'FAILED'}: {' '.join(cmd)}" + ("" if code == 0 else f" — {out.strip()[-200:]}"))
    return code == 0


def apply_swappiness(value):
    ok = run_set(["sysctl", "-w", f"vm.swappiness={value}"])
    try:
        with open(SYSCTL_FILE, "w", encoding="utf-8") as f:
            f.write(f"# Written by host-perf-audit.py {__version__} on {datetime.date.today()}\nvm.swappiness = {value}\n")
        print(f"  permanent: {SYSCTL_FILE}")
    except OSError as e:
        print(f"  FAILED to write {SYSCTL_FILE}: {e}")
        ok = False
    return ok


def apply_arc_max(gib_value):
    value = int(gib_value) * 2 ** 30
    try:
        with open("/sys/module/zfs/parameters/zfs_arc_max", "w", encoding="ascii") as f:
            f.write(str(value))
        print(f"  done: zfs_arc_max = {gib_value} GiB now")
    except OSError as e:
        print(f"  FAILED (now): {e}")
        return False
    try:
        with open(MODPROBE_FILE, "w", encoding="utf-8") as f:
            f.write(f"# Written by host-perf-audit.py {__version__} on {datetime.date.today()}\noptions zfs zfs_arc_max={value}\n")
        print(f"  at boot: {MODPROBE_FILE} — root on ZFS: also « update-initramfs -u -k all » (the program runs it now)")
        if shutil.which("update-initramfs") and os.path.isdir("/sys/module/zfs"):
            run_set(["update-initramfs", "-u", "-k", "all"])
    except OSError as e:
        print(f"  FAILED (at boot): {e}")
        return False
    return True


def offer_apply(fd, yes):
    actions = [(p, t, a, lab) for p, t, a, lab in fd.suggestions if a]
    if not actions:
        print("\nNothing to apply automatically (the remaining suggestions need a decision or a VM restart).")
        return 0
    if os.geteuid() != 0:
        print("\nSettings not applied: root required.")
        return 2
    if not yes and not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("\nNo terminal to confirm: add --yes to apply without questions.")
        return 2
    for _p, text, action, label in sorted(actions, key=lambda x: x[0]):
        if not yes:
            try:
                rep = input(f"\n{label} — {text[:120]}…\nApply? [y/N]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nRemaining settings not applied.")
                return 0
            if rep not in ("o", "oui", "y", "yes"):
                print("  not applied")
                continue
        action()
    return 0


# ---------------------------------------------------------------------------------------------------------------- report
def report(samples, facts, zfs, smart, names, guests_rows_cb, args, cost, host_tasks=(), inside=None, config=None, io=None):
    fd, out = Findings(), []
    if not samples:
        print("No sample taken: nothing to analyze (interrupted too early).")
        return fd
    dur = samples[-1]["wall"] - samples[0]["wall"] + samples[0]["dt"]
    first = datetime.datetime.fromtimestamp(samples[0]["wall"] - samples[0]["dt"])
    print()
    print(f"PERFORMANCE OF {facts['host']} — {facts['pve'] or 'Linux ' + facts['kernel']} — {len(samples)} samples from {first:%Y-%m-%d %H:%M} over {human_duration(dur)}")
    print(f"  (waiting times from {samples[-1].get('psi_source', '/proc/pressure')}; this program used {cost:.2f} s of processor in all)")
    print()
    analyze_cpu(samples, facts, fd, out)
    out.append("")
    analyze_memory(samples, facts, zfs, fd, out)
    out.append("")
    worst, io_avg, io_full = analyze_disks(samples, facts, smart, fd, out)
    out.append("")
    if io is not None:                                    # 1.23 --io-latency
        analyze_io_latency(io, names, fd, out)
        out.append("")
    analyze_zfs(zfs, facts, worst, io_avg, fd, out, names)
    if zfs:
        out.append("")
    analyze_backups(zfs, names, fd, out)
    analyze_network(samples, out)
    out.append("")
    rows = guests_rows_cb(samples, out) if not args.no_guests else []
    if rows:
        out.append("")
        guest_writers(rows, samples, facts, names, fd)
    if host_tasks:
        out.append(f"HOST TASKS that read or write a lot, seen running during the measurement: {', '.join(sorted(host_tasks))}")
        out.append("")
    if inside is not None and inside.items:               # 1.12 --inside: what was seen inside the guests
        out.append("INSIDE THE GUESTS (pct exec, QEMU guest agent)")
        for level, _key, text in inside.items:
            out.append(f"  {tag(level)} {text}")
        out.append("")
        fd.commands.extend(inside.commands)
    for pool, facts_pool in (zfs.get("pools", {}) if zfs else {}).items():
        if facts_pool.get("cap", "").isdigit() and int(facts_pool["cap"]) >= 80:
            fd.ask(f"pool {pool}: where the space goes", [f"zfs list -o space -r {pool}", f"zfs list -t snapshot -o name,used,creation -s used -r {pool} | tail -15"])
    guest_config_advice(names, fd)
    for line in out:
        print(line)
    print("VERDICT — what limits the performance")
    for resource, label in (("cpu", "Processors"), ("memory", "RAM"), ("disks", "Disks")):
        if resource in fd.verdicts:
            level, text = fd.verdicts[resource]
            print(f"  {tag(level)} {T(label):<11} {text}")
    print()
    tail = []
    ssd_answer(fd, worst, io_avg, io_full, facts, rows, tail, host_tasks)
    for line in tail:
        print(line)
    print()
    print("SUGGESTED SETTINGS")
    if not fd.suggestions:
        print("  none: nothing to change according to these measurements.")
    names_p = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}
    for i, (p, text, action, label) in enumerate(sorted(fd.suggestions, key=lambda x: x[0]), 1):
        print(f"  {i}. [{names_p[p]}] {text}")
        if action:
            print(f"     --apply: {label}")
    if config:                                            # 1.13: the configurations of the guests, in full
        print()
        print_config_check(config, len(names))
        for _level, _vmid, text, commands in config:
            if commands:
                fd.ask(text, commands)
    no_collect = getattr(args, "no_collect", False)
    print_commands(fd.commands, run_them=not no_collect)
    if not no_collect and not getattr(args, "apply", False):
        confirm_changes(fd.commands)
    if dur < 1800:
        print()
        print(f"  Short measurement ({human_duration(dur)}): to see the daily peaks (backups, busy hours), run it for hours: host-perf-audit.py --duration 24h")
    return fd


# ---------------------------------------------------------------------------------------------------------------- health, inside the guests, alerts (1.12)
STATE_DIR = os.environ.get("HOST_PERF_AUDIT_STATE_DIR", "/var/lib/host-perf-audit")
SYSTEMD_DIR = os.environ.get("HOST_PERF_AUDIT_SYSTEMD_DIR", "/etc/systemd/system")
HEALTH_UNIT = "host-perf-audit-health"
# 1.15: units that fail in every unprivileged container (no kernel mounts, no udev): not a problem, left out of « failed services »
LXC_NORMAL_FAILURES = {"run-rpc_pipefs.mount", "sys-kernel-config.mount", "sys-kernel-debug.mount", "sys-kernel-tracing.mount", "sys-fs-fuse-connections.mount",
                       "dev-hugepages.mount", "dev-mqueue.mount", "proc-sys-fs-binfmt_misc.mount", "systemd-udev-load-credentials.service", "systemd-udev-trigger.service",
                       "systemd-udevd.service", "systemd-modules-load.service", "systemd-sysctl.service", "systemd-remount-fs.service", "systemd-binfmt.service",
                       "systemd-journald-audit.socket", "apparmor.service", "systemd-networkd-wait-online.service"}
TIME_SERVICES = {"chrony.service", "chronyd.service", "ntp.service", "ntpsec.service", "systemd-timesyncd.service", "openntpd.service"}
DISK_USAGE = "".join(("d", "u -xh --max-depth=2 "))
DU_TOTAL = "".join(("d", "u -ch"))                      # same reason     # the command, written so that the catalogue test does not read its name as a French word
SMART_ATTRIBUTES = {5: "reallocated sectors", 187: "uncorrectable errors reported", 188: "command timeouts", 197: "sectors pending reallocation",
                    198: "sectors uncorrectable offline", 199: "interface CRC errors (cable)"}
KERNEL_DISK_RE = re.compile(r"I/O error|[Mm]edium [Ee]rror|critical (?:target|medium) error|ata\d+(?:\.\d+)?: (?:failed command|exception|hard resetting)|"
                            r"blocked for more than \d+ seconds|nvme\d+: .*timeout|zio pool=.* error=|EXT4-fs error|XFS .*corrupt")
INSIDE_SCRIPT = r'''
w() { for f in /proc/[0-9]*/io; do p=${f%/io}; b=$(sed -n 's/^write_bytes: //p' "$f" 2>/dev/null); [ -n "$b" ] && echo "${p#/proc/} $b $(cat "$p/comm" 2>/dev/null)"; done; }
echo "@@io1"; w
echo "@@docker"; command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}}|{{.Status}}' 2>/dev/null
echo "@@failed"; systemctl --failed --no-legend --plain 2>/dev/null | head -10
echo "@@journal"; journalctl --since -10min -o short 2>/dev/null | grep -v ' werkzeug: ' | awk '{print $5}' | sed 's/\[.*//;s/:$//' | sort | uniq -c | sort -rn | head -5
echo "@@jsize"; journalctl --disk-usage 2>/dev/null
echo "@@df"; df -P -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null | tail -n +2
sleep 10
echo "@@io2"; w
'''


def smart_details(disks):
    """1.12: {disk: {"health", "attrs": {id: raw value}, "hours", "temp", "nvme": {...}}} from smartctl -H -A: the counters that announce a failure
    (reallocated, pending, uncorrectable sectors, cable errors), not only PASSED / FAILED: a disk says PASSED until late."""
    res = {}
    if not shutil.which("smartctl"):
        return res
    for name in sorted(disks):
        code, out = run(["smartctl", "-H", "-A", f"/dev/{name}"], timeout=20)
        if not out:
            continue
        m = re.search(r"(?:overall-health self-assessment test result|SMART Health Status):\s*(\S+)", out)
        d = {"health": m.group(1).upper() if m else "", "attrs": {}, "hours": None, "temp": None, "nvme": {}}
        for line in out.splitlines():
            c = line.split()
            if len(c) >= 10 and c[0].isdigit() and c[9].isdigit():
                ident, raw = int(c[0]), int(c[9])
                if ident in SMART_ATTRIBUTES:
                    d["attrs"][ident] = raw
                elif ident == 9:
                    d["hours"] = raw
                elif ident == 194:
                    d["temp"] = raw
        for key, label in (("Critical Warning", "critical"), ("Media and Data Integrity Errors", "media"), ("Percentage Used", "used"), ("Available Spare", "spare"),
                           ("Power On Hours", "hours"), ("Temperature", "temp")):
            m = re.search(rf"^{key}:\s+(0x[0-9a-fA-F]+|[\d,]+)", out, re.M)
            if m:
                value = int(m.group(1), 16) if m.group(1).startswith("0x") else int(m.group(1).replace(",", ""))
                if label in ("hours", "temp"):
                    d[label] = d[label] if d[label] is not None else value
                else:
                    d["nvme"][label] = value
        res[name] = d
    return res


def load_state():
    try:
        with open(os.path.join(STATE_DIR, "health.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        with open(os.path.join(STATE_DIR, "health.json"), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1, sort_keys=True)
    except OSError:
        pass


class Health:
    """Findings of --health: (level bad | warn | info | ok, key, text) and the commands to run for each (title, [commands])."""

    def __init__(self):
        self.items, self.commands = [], []

    def add(self, level, key, text, commands=()):
        self.items.append((level, key, text))
        if commands:
            self.commands.append((text, list(commands)))

    def alerts(self):
        return [i for i in self.items if i[0] in ("bad", "warn")]


def check_disks(h, facts, state):
    details = smart_details(facts["disks"])
    if facts["disks"] and not shutil.which("smartctl"):
        h.add("warn", "smart-missing", "smartctl is not installed: the health of the disks is not watched — apt install smartmontools")
        return
    previous, current = state.get("smart", {}), {}
    for disk, d in details.items():
        current[disk] = {str(k): v for k, v in d["attrs"].items()}
        ask = [f"smartctl -a /dev/{disk}", f"smartctl -t long /dev/{disk}   # long self-test in the background; result later: smartctl -l selftest /dev/{disk}"]
        age = f"{d['hours']} h ({d['hours'] / 8766:.1f} years)" if d["hours"] else ""
        if d["health"] and d["health"] not in ("PASSED", "OK"):
            h.add("bad", f"smart-failed:{disk}", f"{disk}: SMART health {d['health']} — the disk announces its own failure: replace it now", ask)
            continue
        signs = []
        for ident, label in SMART_ATTRIBUTES.items():
            raw = d["attrs"].get(ident, 0)
            before = previous.get(disk, {}).get(str(ident))
            grew = before is not None and raw > before
            if raw and (ident in (5, 187, 197, 198) or grew):
                signs.append((ident, f"{label}: {raw}" + (f" (was {before})" if grew else "")))
        nv = d["nvme"]
        if nv.get("critical"):
            signs.append((197, f"NVMe critical warning 0x{nv['critical']:02x}"))
        if nv.get("media"):
            signs.append((197, f"NVMe media errors: {nv['media']}"))
        if nv.get("used", 0) >= 90:
            signs.append((0, f"NVMe wear: {nv['used']} % of its life used"))
        if nv.get("spare") is not None and nv["spare"] <= 10:
            signs.append((0, f"NVMe spare blocks: {nv['spare']} % left"))
        if signs:
            grave = any(i in (197, 198) for i, _t in signs) or any("(was" in t and i in (5, 187) for i, t in signs)
            h.add("bad" if grave else "warn", f"smart-signs:{disk}", f"{disk}: signs of failure — " + "; ".join(t for _i, t in signs)
                  + (" — plan its replacement" if grave else " — to watch: a count that grows means a replacement"), ask)
        elif d["temp"] and d["temp"] >= 55:
            h.add("warn", f"smart-temp:{disk}", f"{disk}: {d['temp']} °C — too hot for a disk (cooling, dust)", ask[:1])
        else:
            h.add("ok", f"smart:{disk}", f"{disk}: SMART passed, no reallocated, pending or uncorrectable sector" + (f" · {age}" if age else "")
                  + (" — past 5 years: the age when HDD start to fail, keep a spare" if d["hours"] and d["hours"] >= 43830 else ""))
    state["smart"] = current
    array = ""
    for line in (read("/proc/mdstat") or "").splitlines():
        m = re.match(r"(md\d+) : (\S+)", line)
        if m:
            array = m.group(1)
        elif array and re.search(r"\[[U_]*_[U_]*\]", line):
            h.add("bad", f"md:{array}", f"{array}: software RAID degraded ({line.strip()[-12:]}) — one disk left the array", ["cat /proc/mdstat", f"mdadm --detail /dev/{array}"])


def check_pools(h, zfs):
    if not zfs:
        return
    code, out = run(["zpool", "status"])
    blocks = re.split(r"^\s*pool: ", out or "", flags=re.M)[1:]
    for block in blocks:
        pool = block.split()[0]
        ask = [f"zpool status -v {pool}"]
        m = re.search(r"^\s*state: (\S+)", block, re.M)
        if m and m.group(1) != "ONLINE":
            h.add("bad", f"pool-state:{pool}", f"pool {pool}: state {m.group(1)} — a disk is missing or faulted: the pool has no redundancy left", ask)
        errors = [f"{c[0]} (read {c[2]}, write {c[3]}, checksum {c[4]})" for c in (l.split() for l in block.splitlines())
                  if len(c) >= 5 and c[1] in ("ONLINE", "DEGRADED", "FAULTED", "UNAVAIL", "REMOVED") and any(x not in ("0", "-") for x in c[2:5])]
        if errors:
            h.add("bad", f"pool-errors:{pool}", f"pool {pool}: errors on " + ", ".join(errors[:4]) + " — the disk or its cable is failing", ask + ["zpool events | tail -30"])
        m = re.search(r"^errors: (.+)$", block, re.M)
        if m and "No known data errors" not in m.group(1):
            h.add("bad", f"pool-data:{pool}", f"pool {pool}: {m.group(1).strip()} — files are damaged", ask)
        scan = re.search(r"scan: scrub repaired .* on (\w{3} \w{3} +\d+ [\d:]+ \d{4})", block)
        if scan:
            try:
                days = (time.time() - time.mktime(time.strptime(re.sub(r" +", " ", scan.group(1)), "%a %b %d %H:%M:%S %Y"))) / 86400
                if days > 40:
                    h.add("warn", f"pool-scrub:{pool}", f"pool {pool}: last scrub {days:.0f} days ago — the monthly check did not run: hidden errors are not found", [f"zpool scrub {pool}"])
            except ValueError:
                pass
        elif "scrub in progress" not in block and "resilver" not in block:
            h.add("warn", f"pool-scrub:{pool}", f"pool {pool}: never scrubbed — hidden errors are not found", [f"zpool scrub {pool}"])
        cap = zfs["pools"].get(pool, {}).get("cap", "")
        if cap.isdigit() and int(cap) >= 80:
            h.add("bad" if int(cap) >= 90 else "warn", f"pool-full:{pool}", f"pool {pool}: used {cap} % — ZFS slows down strongly beyond 80 %, and a full pool stops every guest",
                  [f"zfs list -o space -r {pool}", f"zfs list -t snapshot -o name,used,creation -s used -r {pool} | tail -15"])
        if not errors and m and "No known data errors" in m.group(1) and not (cap.isdigit() and int(cap) >= 80):
            h.add("ok", f"pool:{pool}", f"pool {pool}: ONLINE, no error" + (f", used {cap} %" if cap else ""))


def check_system(h, zfs, names):
    for level, text, commands in backup_findings(names):            # 1.15
        h.add(level, "backups:" + text.split(" — ")[0][:60], text, commands)
    code, out = run(["journalctl", "-k", "--since", "-24h", "-p", "warning", "-o", "short-iso", "--no-pager"], timeout=30)
    hits = [l for l in (out or "").splitlines() if KERNEL_DISK_RE.search(l)]
    if hits:
        grave = any(re.search(r"I/O error|[Mm]edium [Ee]rror|critical", l) for l in hits)
        h.add("bad" if grave else "warn", "kernel-disk", f"kernel: {len(hits)} disk or blocked-task messages in 24 hours — the last one: {hits[-1][:160]}",
              ["journalctl -k --since -24h -p warning --no-pager | tail -40"])
    try:
        st = os.statvfs("/")
        if st.f_blocks and st.f_bavail * 10 < st.f_blocks:
            h.add("bad" if st.f_bavail * 20 < st.f_blocks else "warn", "root-full", f"/ of the host: {size(st.f_bavail * st.f_frsize)} free of {size(st.f_blocks * st.f_frsize)} — "
                  "a full root stops Proxmox", [DISK_USAGE + "/ 2>/dev/null | sort -h | tail -20"])
    except OSError:
        pass
    if zfs:
        probe = Findings()
        zfs_space(zfs, names, probe, [])
        for priority, text, _a, _l in probe.suggestions:
            m = re.search(r"pct resize \S+ \S+ \S+", text)
            h.add("bad" if priority == 1 else "warn", "guest-disk:" + text.split(" has only")[0], text, [m.group(0)] if m else [])
    tasks = [t for t in recent_tasks(days=3) if t[2] == "vzdump"]
    failed = [t for t in tasks if not t[4].startswith("OK")]
    if failed:
        h.add("warn", "backup-failed", f"backups: {len(failed)} failed in 3 days — the last one: guest {failed[-1][3] or 'all of them'} on "
              f"{datetime.datetime.fromtimestamp(failed[-1][0]):%Y-%m-%d %H:%M}, {failed[-1][4]}", ["tail -n 20 /var/log/pve/tasks/index"])
    jobs = [o for kind, _n, o in pve_sections(os.path.join(PVE_DIR, "jobs.cfg")) if kind == "vzdump" and o.get("enabled") != "0"]
    if jobs and not [t for t in tasks if t[4].startswith("OK") and time.time() - t[1] < 2 * 86400]:
        h.add("warn", "backup-old", "backups: a backup job is scheduled but no backup succeeded in the last 2 days", ["tail -n 20 /var/log/pve/tasks/index", "systemctl status pvescheduler --no-pager | head -15"])
    if shutil.which("systemctl"):
        for unit, why in (("smartmontools", "the disks are not watched between two runs of this program"), ("zfs-zed", "ZFS errors are not mailed when they happen")):
            if unit == "zfs-zed" and not zfs:
                continue
            code, out = run(["systemctl", "is-active", unit], timeout=10)
            status = (out.strip().splitlines() or [""])[-1].strip()
            if code is not None and status in ("inactive", "failed", "dead", "unknown"):
                h.add("warn", f"service:{unit}", f"service {unit}: {status} — {why}", [f"systemctl enable --now {unit}"])


def guest_agent(conf):
    return bool(re.search(r"^agent:\s*(?:1|enabled=1)", conf, re.M))


def inside_guest(vmid, kind):
    """1.12: output of INSIDE_SCRIPT run INSIDE a guest, read-only: pct exec for a container, the QEMU guest agent (qm guest exec) for a VM. « » when it
    cannot be run. No shared folder is needed: the host asks, the guest answers."""
    if kind == "lxc":
        code, out = run(["pct", "exec", vmid, "--", "sh", "-c", INSIDE_SCRIPT], timeout=60)
        return out if code == 0 else ""
    code, out = run(["qm", "guest", "exec", vmid, "--timeout", "50", "--", "sh", "-c", INSIDE_SCRIPT], timeout=70)
    try:
        return json.loads(out).get("out-data", "") if code == 0 else ""
    except ValueError:
        return ""


def check_inside(h, names, running):
    """1.12: what the host cannot see from outside: a container that restarts in a loop, a journal that fills, a full disk, the processes that write.
    On 2026-11-14 a Prometheus container restarted in a loop for days in a BigBlueButton VM (a damaged file), dockerd wrote one error per second,
    and nothing said it until the writes of that VM were looked at by hand."""
    for vmid in sorted(running, key=lambda x: int(x) if x.isdigit() else 0):
        kind, name, conf = names.get(vmid, (running[vmid][0], "", ""))
        who = f"guest {vmid} ({name})"
        prefix = f"pct exec {vmid} --" if kind == "lxc" else f"qm guest exec {vmid} --timeout 50 --"
        if kind == "vm" and not guest_agent(conf):
            h.add("info", f"inside-agent:{vmid}", f"{who}: the QEMU guest agent is not enabled — the inside of this VM is not visible from the host",
                  [f"qm set {vmid} --agent enabled=1   # on the host", "apt install -y qemu-guest-agent && systemctl enable --now qemu-guest-agent   # INSIDE the VM",
                   f"qm shutdown {vmid} && qm start {vmid}   # the agent device appears at the next start of the VM (not a reboot from inside)"])
            continue
        out = inside_guest(vmid, kind)
        if not out:
            h.add("info", f"inside-none:{vmid}", f"{who}: no answer from inside" + (" (is qemu-guest-agent installed and running in the VM?)" if kind == "vm" else ""),
                  [f"{prefix} true; echo $?"])
            continue
        parts = {}
        for block in out.split("@@")[1:]:
            title, _nl, body = block.partition("\n")
            parts[title.strip()] = [l for l in body.splitlines() if l.strip()]
        for line in parts.get("docker", []):
            cname, _sep, status = line.partition("|")
            if status.startswith("Restarting"):
                h.add("bad", f"inside-restart:{vmid}:{cname}", f"{who}: container {cname} restarts in a loop ({status}) — it fails at each start, and each start reads and writes its data again",
                      [f"{prefix} docker logs --tail 30 {cname}", f"{prefix} docker inspect {cname} --format '{{{{.RestartCount}}}} restarts, {{{{.State.Error}}}}'"])
            elif status.startswith("Exited") and not status.startswith("Exited (0)") and re.search(r"(second|minute)s? ago", status):
                h.add("warn", f"inside-exited:{vmid}:{cname}", f"{who}: container {cname} just stopped on an error ({status})", [f"{prefix} docker logs --tail 30 {cname}"])
        failed = [l.split()[0].lstrip("●*") for l in parts.get("failed", []) if l.split()]
        failed = [u for u in failed if u]
        noise = [u for u in failed if kind == "lxc" and u in LXC_NORMAL_FAILURES]
        clock = [u for u in failed if kind == "lxc" and u in TIME_SERVICES]
        real = [u for u in failed if u not in noise and u not in clock]
        if real:
            h.add("warn", f"inside-failed:{vmid}", f"{who}: failed services: {', '.join(real[:6])}"
                  + (f" ({len(noise)} failures normal in a container left out: {', '.join(noise[:3])})" if noise else ""),
                  [f"{prefix} systemctl status {u} --no-pager -n 15" for u in real[:3]])
        if clock:
            h.add("info", f"inside-clock:{vmid}", f"{who}: {', '.join(clock)} failed — normal in a container: it cannot set the clock, the host keeps the time; disable it",
                  [f"{prefix} systemctl disable --now {' '.join(clock)}"])
        for line in parts.get("journal", [])[:2]:
            c = line.split()
            if len(c) >= 2 and c[0].isdigit() and int(c[0]) >= 300:
                h.add("warn", f"inside-journal:{vmid}:{c[1]}", f"{who}: {c[1]} wrote {c[0]} lines to the journal in 10 minutes ({int(c[0]) / 600:.1f} per second) — "
                      "usually the same error repeated; each line is a write on the disks of the host",
                      [f"{prefix} journalctl --since -2min -t {c[1]} --no-pager -o cat | tail -15"])
        m = re.search(r"take up ([\d.]+)([MGT])", " ".join(parts.get("jsize", [])))
        if m and float(m.group(1)) * {"M": 1 / 1024, "G": 1, "T": 1024}[m.group(2)] >= 2:
            h.add("warn", f"inside-jsize:{vmid}", f"{who}: the journal takes {m.group(1)} {m.group(2)}iB — cap it: SystemMaxUse=500M in /etc/systemd/journald.conf",
                  [f"{prefix} journalctl --vacuum-size=500M"])
        for line in parts.get("df", []):
            c = line.split()
            if len(c) >= 6 and c[4].rstrip("%").isdigit() and int(c[4].rstrip("%")) >= 90:
                h.add("bad" if int(c[4].rstrip("%")) >= 97 else "warn", f"inside-df:{vmid}:{c[5]}", f"{who}: {c[5]} is {c[4]} full ({int(c[3]) // 1024} MiB free)",
                      [f"{prefix} sh -c '" + DISK_USAGE + f"{c[5]} 2>/dev/null | sort -h | tail -15'"])
        before = {l.split()[0]: int(l.split()[1]) for l in parts.get("io1", []) if len(l.split()) >= 2 and l.split()[1].isdigit()}
        writers = {}
        for l in parts.get("io2", []):
            c = l.split(None, 2)
            if len(c) >= 2 and c[1].isdigit() and c[0] in before:
                rate = (int(c[1]) - before[c[0]]) / 10 / 1024
                if rate >= 20:
                    label = c[2] if len(c) > 2 else c[0]
                    writers[label] = writers.get(label, 0) + rate
        if writers:
            top = sorted(writers.items(), key=lambda x: -x[1])[:4]
            h.add("info", f"inside-writers:{vmid}", f"{who}: processes that write the most: " + ", ".join(f"{n} {r:.0f} kB/s" for n, r in top))


def send_alert(subject, body):
    """Alert by e-mail and in the system journal. E-mail: the SMTP settings of app-health-check.py when they are configured on this machine, otherwise
    the local sendmail to root (Proxmox forwards the mail of root to the address given at installation). Returns what was done, in a sentence."""
    if shutil.which("logger"):
        try:
            subprocess.run(["logger", "-t", SCRIPT_NAME, "-p", "user.warning"], input=subject + "\n" + body[:6000], universal_newlines=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    target = os.environ.get("HOST_PERF_AUDIT_MAIL_FILE")
    if target:                                            # tests: the mail goes to a file
        with open(target, "a", encoding="utf-8") as f:
            f.write(f"Subject: {subject}\n\n{body}\n")
        return f"written to {target}"
    path = os.path.join(SCRIPT_DIR, "app-health-check.py")
    if os.path.isfile(path):
        try:
            import importlib.util as ilu
            spec = ilu.spec_from_file_location("app_health_check_mail", path)
            mod = ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cfg = mod.load_config(mod.resolve_config_paths(None))
            if cfg.get("SMTP_HOST") and cfg.get("NOTIFY_EMAIL_TO"):
                mod.send_email(cfg, subject, body)
                return f"sent to {cfg['NOTIFY_EMAIL_TO']}"
        except Exception as problem:                      # noqa: BLE001 - the local mail below is tried next
            eprint(f"e-mail through app-health-check.py not sent ({str(problem)[:120]}): trying the local mail")
    sendmail = shutil.which("sendmail") or ("/usr/sbin/sendmail" if os.path.exists("/usr/sbin/sendmail") else "")
    if not sendmail:
        return "not sent: neither SMTP_HOST / NOTIFY_EMAIL_TO (configuration of app-health-check.py) nor a local sendmail — system journal only (journalctl -t host-perf-audit)"
    try:
        subprocess.run([sendmail, "-t"], input=f"To: root\nSubject: {subject}\nContent-Type: text/plain; charset=UTF-8\n\n{body}\n", universal_newlines=True, timeout=30, check=True)
        return "sent to root by the local mail (Proxmox forwards it to the address of root@pam)"
    except (OSError, subprocess.SubprocessError) as problem:
        return f"not sent ({problem}) — system journal only"


def health(args, facts, zfs, names, running):
    """--health: the state of the host in a few seconds, without measurement: disks (SMART counters compared with the previous run), pools, RAID, kernel
    messages, space, backups, alert services, and with --inside the inside of each guest. Exit code: 0 nothing, 1 to watch, 2 problem."""
    h, state = Health(), load_state()
    check_disks(h, facts, state)
    check_pools(h, zfs)
    check_system(h, zfs, names)
    if names and not args.no_guests:                      # 1.13: the configurations of the guests
        found = guest_config_check(names, running, zfs)
        print_config_check(found, len(names))             # in full: --health has no report after it
        for level, vmid, text, commands in found:
            if level == "major":                          # to watch, and in the alert; the rest stays in the list above
                h.add("warn", f"config:{vmid}:{text.split(': ', 1)[-1][:40]}", text, commands)
            elif commands:                                # 1.15: the commands of every finding, not only the major ones
                h.commands.append((text, commands))
    if args.inside:
        check_inside(h, names, running)
    elif any(k == "vm" for k, _p in running.values()):
        h.add("info", "inside-off", "the inside of the guests was not looked at (containers that restart in a loop, journals, full disks): add --inside")
    print()
    print(f"HEALTH OF {facts['host']} — {time.strftime('%Y-%m-%d %H:%M')}")
    order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
    for level, _key, text in sorted(h.items, key=lambda i: order[i[0]]):
        print(f"  {tag(level)} {text}")
    alerts = h.alerts()
    bad = sum(1 for i in alerts if i[0] == "bad")
    print()
    print(f"  Verdict: {bad} problems, {len(alerts) - bad} to watch" if alerts else "  Verdict: nothing to report")
    keys = sorted(i[1] for i in alerts)
    last = state.get("notified", {})
    new = [k for k in keys if k not in last.get("keys", [])]
    due = keys and (new or time.time() - last.get("when", 0) > 86400)
    cleared = not keys and last.get("keys")
    # 1.15: the program runs the read-only commands itself; without a terminal (the timer), only when an alert goes out
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    results = print_commands(h.commands, run_them=not args.no_collect and (interactive or (args.notify and due)))
    if args.notify:
        if due or cleared:
            subject = (f"[host-perf-audit] {facts['host']}: {bad} problems, {len(alerts) - bad} to watch" if keys else f"[host-perf-audit] {facts['host']}: back to normal")
            body = "\n".join(f"{'[FAIL]' if l == 'bad' else '[WARN]' if l == 'warn' else '[i]' if l == 'info' else '[OK]'} {t}" for l, _k, t in sorted(h.items, key=lambda i: order[i[0]]))
            body += "\n\n" + "\n".join(commands_lines(h.commands, results)) + f"\n\nhost-perf-audit.py v{__version__} --health" + (" --inside" if args.inside else "")
            tr = I18N.tr if I18N else (lambda t: t)
            print(f"  Alert: {send_alert(tr(subject), chr(10).join(tr(l) for l in body.splitlines()))}")
            state["notified"] = {"keys": keys, "when": time.time()}
        else:
            print("  Alert: not sent (nothing new since the last one; reminder after 24 hours)" if keys else "  Alert: nothing to send")
    save_state(state)
    if not args.no_collect:
        confirm_changes(h.commands)
    return 2 if bad else 1 if alerts else 0


# ---------------------------------------------------------------------------------------------------------------- commands: collected or confirmed (1.15)
READ_ONLY_RE = re.compile(
    r"^(?:smartctl -(?:a|x|H|A|i|l \w+)\b|zpool (?:status|list|events|iostat|get)\b|zfs (?:list|get)\b|"
    r"systemctl (?:status|is-active|is-enabled|is-failed|list-timers|list-units|show|cat)\b|journalctl\b(?!.*--(?:vacuum|rotate|flush|sync))|"
    r"docker (?:logs|inspect|ps|images|stats --no-stream)\b|du\b|df\b|ls\b|grep\b|cat\b|tail\b|head\b|sort\b|uniq\b|wc\b|cut\b|tr\b|awk\b|sed -n\b|"
    r"pvesm (?:list|status)\b|pct (?:list|config|status|df)\b|qm (?:list|config|status|pending)\b|pidstat\b|iotop -b|free\b|uptime\b|lsblk\b|"
    r"find\b(?!.*-(?:delete|exec|ok|fprint))|stat\b|mdadm --detail\b|true\b|echo\b|crontab -l\b|xargs -d '\\n' -a \S+ du\b|ps\b|ss\b|ip (?:a|addr|r|route|link)\b)")
WRAPPER_RE = re.compile(r"^(?:pct exec \d+ --|qm guest exec \d+(?: --timeout \d+)? --)\s*")
COLLECT_BUDGET = 240          # seconds for all the read-only commands of one run
COLLECT_LINES = 40            # lines of output kept per command
# 1.22: commands that destroy data (backup files, snapshots, ZFS datasets) cannot be undone: they need the word DELETE, not a simple « y »
IRREVERSIBLE_RE = re.compile(r"(?:^|[\s;&|])(?:rm|unlink|shred)\s|\b(?:pct|qm) delsnapshot\b|\bzfs destroy\b|\bzpool destroy\b|\bvzdump\b.*--remove")
IRREVERSIBLE_WORDS = ("delete", "supprimer")


def is_irreversible(cmd):
    """1.22: True when the command deletes data that cannot be recovered (rm, snapshot or ZFS dataset destruction)."""
    return bool(IRREVERSIBLE_RE.search(strip_comment(cmd)))


def strip_comment(cmd):
    """The command without its trailing explanation (« cmd   # why »); a « # » inside quotes is kept."""
    m = re.search(r"\s{2,}#\s.*$", cmd)
    return cmd[:m.start()].rstrip() if m else cmd.strip()


def is_read_only(cmd):
    """1.15: True only when EVERY part of the command (after pct exec / qm guest exec / sh -c, split on | ; && ||) is in the list of read-only commands
    and nothing is redirected to a file. Anything else is a change: never run without confirmation."""
    text = strip_comment(cmd)
    text = WRAPPER_RE.sub("", text)
    m = re.match(r"^(?:sh|bash) -c (['\"])(.*)\1$", text)
    if m:
        text = m.group(2)
    text = re.sub(r"\s*2>(?:&1|/dev/null)", "", text)
    if re.search(r"(?<![0-9])>|<\(|`|\$\(", text):
        return False
    parts = [p.strip() for p in re.split(r"\|\||&&|;|\|", text) if p.strip()]
    return bool(parts) and all(READ_ONLY_RE.match(p) for p in parts)


def unique_commands(commands):
    """[(title, [commands])] without a command already asked by an earlier finding."""
    seen, res = set(), []
    for title, cmds in commands:
        kept = [c for c in cmds if strip_comment(c) not in seen]
        seen.update(strip_comment(c) for c in kept)
        if kept:
            res.append((title, kept))
    return res


def run_collected(cmd, timeout):
    """(exit code, output) of a read-only command, run by bash with a low priority. The JSON answer of « qm guest exec » is decoded."""
    text = strip_comment(cmd)
    if text.startswith("qm guest exec ") and "--timeout" not in text.split(" -- ")[0]:
        text = text.replace(" -- ", f" --timeout {max(5, int(timeout) - 5)} -- ", 1)
    wrapper = [w for w in (["nice", "-n", "10"] if shutil.which("nice") else []) + (["ionice", "-c3"] if shutil.which("ionice") else [])]
    code, out = run(wrapper + ["bash", "-c", text], timeout=timeout)
    if text.startswith("qm guest exec ") and out.strip().startswith("{"):
        try:
            answer = json.loads(out)
            out = (answer.get("out-data") or "") + (answer.get("err-data") or "")
            try:                                          # 1.16: the agent hands back UTF-8 read as Latin-1 (« â\x97\x8f » for « ● »)
                out = out.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            code = answer.get("exitcode", code)
        except ValueError:
            pass
    return code, out


def commands_lines(commands, results=None):
    """The block of the commands; each one marked [read] (run by the program, its output below) or [change] (asked before it is run)."""
    lines = []
    commands = unique_commands(commands)
    if not commands:
        return lines
    lines.append("COMMANDS — [read]: run by the program, output below · [change]: run only after your confirmation")
    for title, cmds in commands:
        lines.append(f"  # {title}")
        lines.extend(f"  {'[read]  ' if is_read_only(c) else ('[irrevers.] ' if is_irreversible(c) else '[change]')} {c}" for c in cmds)
    if results:
        lines.append("")
        lines.append("COLLECTED — output of the [read] commands (send it with this report)")
        for cmd, code, out in results:
            lines.append(f"  $ {strip_comment(cmd)}" + (f"   (exit code {code})" if code not in (0, None) else ""))
            kept = [l.rstrip() for l in (out or "").splitlines() if l.strip()]
            if len(kept) > COLLECT_LINES:
                kept = kept[:10] + [f"[... {len(kept) - COLLECT_LINES} lines left out ...]"] + kept[-(COLLECT_LINES - 10):]
            lines.extend(f"    {l[:300]}" for l in kept or ["(no output)"])
    return lines


def collect(commands):
    """Runs every [read] command once, within COLLECT_BUDGET seconds: [(command, exit code, output)]."""
    results, start = [], time.monotonic()
    for _title, cmds in unique_commands(commands):
        for cmd in cmds:
            if not is_read_only(cmd):
                continue
            left = COLLECT_BUDGET - (time.monotonic() - start)
            if left < 5:
                results.append((cmd, None, "not run: the time allowed for the collection is used up"))
                continue
            code, out = run_collected(cmd, min(60, left))
            results.append((cmd, code, out))
    return results


def confirm_changes(commands):
    """1.15: the [change] commands, one by one, each run only after « y ». Nothing is run without a terminal."""
    changes = [(title, c) for title, cmds in unique_commands(commands) for c in cmds if not is_read_only(c)]
    if not changes:
        return
    print()
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(f"CHANGES — {len(changes)} commands not run: no terminal to confirm them (run them by hand, see [change] above)")
        return
    if os.geteuid() != 0:
        print(f"CHANGES — {len(changes)} commands not run: root required")
        return
    print(f"CHANGES — {len(changes)} commands that modify something; each one is run only if you answer « y »")
    for title, cmd in changes:
        try:
            if is_irreversible(cmd):
                print("  [IRREVERSIBLE] this deletes data that cannot be recovered (type DELETE or SUPPRIMER to run it; anything else skips it)")
                answer = input(f"\n  # {title[:200]}\n  {cmd}\n  Type DELETE to run it: ").strip().lower()
                accepted = answer in IRREVERSIBLE_WORDS
            else:
                answer = input(f"\n  # {title[:200]}\n  {cmd}\n  Run it? [y/N]: ").strip().lower()
                accepted = answer in ("o", "oui", "y", "yes")
        except (KeyboardInterrupt, EOFError):
            print("\n  Remaining changes not run.")
            return
        if not accepted:
            print("  not run")
            continue
        code, out = run(["bash", "-c", strip_comment(cmd)], timeout=600)
        for line in (out or "").splitlines()[-15:]:
            print(f"    {line}")
        print(f"  {tag('ok') if code == 0 else tag('bad')} exit code {code}")


def print_commands(commands, run_them=True):
    """The block of the commands, then (run_them) the output of the read-only ones and the confirmation of the changes. Returns the collected results."""
    results = collect(commands) if run_them else []
    lines = commands_lines(commands, results)
    if lines:
        print()
    for line in lines:
        print(line)
    return results


def install_health_timer():
    """--install-timer: systemd timer that runs --health --inside --notify every hour (alert only when something is new, reminder after 24 hours)."""
    if os.geteuid() != 0 and "HOST_PERF_AUDIT_SYSTEMD_DIR" not in os.environ:
        eprint("ERROR: --install-timer needs root.")
        return 2
    service = (f"# Generated by host-perf-audit.py --install-timer - do not edit by hand.\n[Unit]\nDescription=Health of the host: disks, pools, guests (alert only when something is new)\n\n"
               f"[Service]\nType=oneshot\nExecStart={sys.executable} {os.path.realpath(__file__)} --health --inside --notify\nNice=10\nIOSchedulingClass=idle\n")
    timer = (f"# Generated by host-perf-audit.py --install-timer - do not edit by hand.\n[Unit]\nDescription=Runs {HEALTH_UNIT} every hour\n\n[Timer]\nOnCalendar=*-*-* *:17:00\n"
             "Persistent=true\nRandomizedDelaySec=120\n\n[Install]\nWantedBy=timers.target\n")
    os.makedirs(SYSTEMD_DIR, exist_ok=True)
    for ext, text in (("service", service), ("timer", timer)):
        with open(os.path.join(SYSTEMD_DIR, f"{HEALTH_UNIT}.{ext}"), "w", encoding="utf-8") as f:
            f.write(text)
    if "HOST_PERF_AUDIT_SYSTEMD_DIR" not in os.environ:
        for cmd in (["systemctl", "daemon-reload"], ["systemctl", "enable", "--now", f"{HEALTH_UNIT}.timer"]):
            code, out = run(cmd, timeout=60)
            if code != 0:
                eprint(f"ERROR: {' '.join(cmd)} failed: {out.strip()}")
                return 1
    print(f"Timer installed and active: {SYSTEMD_DIR}/{HEALTH_UNIT}.timer (every hour, at minute 17): host-perf-audit.py --health --inside --notify")
    print(f"Next run: systemctl list-timers {HEALTH_UNIT}.timer; journal: journalctl -u {HEALTH_UNIT}.service; alerts also in: journalctl -t host-perf-audit")
    print("E-mail: SMTP_HOST and NOTIFY_EMAIL_TO of the app-health-check.py configuration when present, otherwise the local mail to root. Try it now: host-perf-audit.py --health --inside --notify")
    return 0


def uninstall_health_timer():
    if "HOST_PERF_AUDIT_SYSTEMD_DIR" not in os.environ:
        run(["systemctl", "disable", "--now", f"{HEALTH_UNIT}.timer"], timeout=60)
    for ext in ("timer", "service"):
        try:
            os.remove(os.path.join(SYSTEMD_DIR, f"{HEALTH_UNIT}.{ext}"))
        except FileNotFoundError:
            pass
    if "HOST_PERF_AUDIT_SYSTEMD_DIR" not in os.environ:
        run(["systemctl", "daemon-reload"], timeout=60)
    print(f"Timer removed: {HEALTH_UNIT}.timer")
    return 0


# ---------------------------------------------------------------------------------------------------------------- a command in the guests (1.17)
GUEST_COMMAND_DEFAULT = "/opt/rlq-admin-tools/nginx-hardening.sh --update"
GUEST_RUN_TIMEOUT = 1800        # seconds per guest: nginx-hardening.sh --update may install packages


def guest_exec(vmid, kind, script, timeout):
    """(exit code, output) of a shell script run INSIDE a guest (pct exec / qm guest exec), stdin closed, without colours."""
    # qm guest exec starts the command with an almost empty environment (no HOME): the Bash programs of the suite run with
    # "set -u" and stopped on "HOME: unbound variable" in the VMs (1.21)
    script = f'export NO_COLOR=1 TERM=dumb HOME="${{HOME:-/root}}"; {script}'
    if kind == "lxc":
        return run(["pct", "exec", vmid, "--", "sh", "-c", script], timeout=timeout + 60)
    code, out = run(["qm", "guest", "exec", vmid, "--timeout", str(timeout), "--", "sh", "-c", script], timeout=timeout + 60)
    try:
        answer = json.loads(out)
    except ValueError:
        return code, out
    text = (answer.get("out-data") or "") + (answer.get("err-data") or "")
    try:
        text = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    if answer.get("exited") in (0, False):
        return None, text + "\n(the command was still running when the agent stopped waiting: see the journal of the guest)"
    return answer.get("exitcode", code), text


def resolve_guests(spec, names, running):
    """[(vmid, problem or « »)] from « 101,105 433 » or « all » (every running guest)."""
    if not spec:
        return []
    if spec.strip().lower() in ("all", "tous"):
        return [(v, "") for v in sorted(running, key=lambda x: int(x) if x.isdigit() else 0)]
    res = []
    for vmid in re.split(r"[\s,;]+", spec.strip()):
        if not vmid:
            continue
        if vmid not in names:
            res.append((vmid, "no such container or VM"))
        elif vmid not in running:
            res.append((vmid, "not running"))
        elif names[vmid][0] == "vm" and not guest_agent(names[vmid][2]):
            res.append((vmid, "QEMU guest agent not enabled (qm set ID --agent enabled=1, qemu-guest-agent in the VM, then stop and start it)"))
        else:
            res.append((vmid, ""))
    return res


def guest_run(args, names, running):
    """--guest-run: runs a command (default: nginx-hardening.sh --update) in the chosen guests, after checking that its program exists in each and
    after confirmation; every output is kept in /var/lib/host-perf-audit/guest-runs/DATE/ with a report.md to send for analysis.
    Exit code: 0 all succeeded, 1 a failure or a warning in an output, 2 nothing run."""
    command = (args.guest_command or GUEST_COMMAND_DEFAULT).strip()
    program = command.split()[0]
    targets = resolve_guests(args.guests, names, running)
    if not targets:
        eprint("ERROR: --guest-run needs the guests: --guests 101,105,433 (or « all », or the key GUESTS of the configuration).")
        return 2
    print(f"\nCOMMAND IN THE GUESTS — {command}")
    ready, missing = [], []
    for vmid, problem in targets:
        kind, name = names.get(vmid, ("?", ""))[:2]
        who = f"{vmid} ({name or '?'})"
        if problem:
            print(f"  {tag('warn')} {who}: left out — {problem}")
            continue
        code, out = guest_exec(vmid, kind, f"if [ -x {program} ]; then echo FOUND; {program} --version 2>/dev/null | head -1; else echo MISSING; fi", 60)
        lines = (out or "").strip().splitlines()
        if not lines or lines[0].strip() != "FOUND":
            print(f"  {tag('bad')} {who}: {program} is not there (or not executable)" + (f" — {lines[0][:120]}" if lines and lines[0].strip() != "MISSING" else ""))
            missing.append(vmid)
            continue
        version = lines[1].strip() if len(lines) > 1 else ""
        print(f"  {tag('ok')} {who}: {program} found" + (f" · {version}" if version else ""))
        ready.append((vmid, kind, name, version))
    # 1.19: --guest-run alone copies nothing: where the program is missing, the copy of the suite (--guest-sync) is offered for these guests
    if missing and program.startswith(SYNC_DEST_DEFAULT + "/") and not getattr(args, "guest_sync", False):
        print(f"  {len(missing)} guests without the suite ({', '.join(missing)}): --guest-sync copies it there first "
              f"(host-perf-audit.py --guest-sync --guest-run --guests {','.join(missing)})")
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                answer = input(f"  Copy the suite to {', '.join(missing)} now? [y/N]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                answer = ""
            if answer in ("o", "oui", "y", "yes"):
                sub = argparse.Namespace(**dict(vars(args), guests=",".join(missing), yes=True))
                guest_sync(sub, names, running)
                for vmid in missing:
                    kind, name = names[vmid][:2]
                    code, out = guest_exec(vmid, kind, f"[ -x {program} ] && {program} --version 2>/dev/null | head -1", 60)
                    if code == 0 and (out or "").strip():
                        ready.append((vmid, kind, name, out.strip().splitlines()[0]))
    if not ready:
        print("  Nothing to run.")
        return 2
    if not is_read_only(command) and not args.yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print(f"  Not run: this command changes the guests and there is no terminal to confirm it (add --yes to run it without a question).")
            return 2
        try:
            answer = input(f"  Run « {command} » in {len(ready)} guests ({', '.join(v for v, *_r in ready)}), one after the other? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            answer = ""
        if answer not in ("o", "oui", "y", "yes"):
            print("  Not run.")
            return 2
    folder = os.path.join(STATE_DIR, "guest-runs", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(folder, mode=0o700, exist_ok=True)
    results = []
    for vmid, kind, name, version in ready:
        print(f"  … {vmid} ({name}): running (at most {GUEST_RUN_TIMEOUT // 60} minutes)", flush=True)
        start = time.monotonic()
        code, out = guest_exec(vmid, kind, f"{command} </dev/null 2>&1", GUEST_RUN_TIMEOUT)
        seconds = time.monotonic() - start
        out = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out or "")
        fails = [l.strip() for l in out.splitlines() if re.search(r"\[(?:FAIL|ÉCHEC)\]", l)]
        warns = [l.strip() for l in out.splitlines() if re.search(r"\[(?:ATTN|WARN|ATTENTION)\]", l)]
        summary = next((l.strip() for l in reversed(out.splitlines()) if re.match(r"\s*(RÉSUMÉ|SUMMARY)\b", l)), "")
        path = os.path.join(folder, f"{vmid}-{re.sub(r'[^A-Za-z0-9._-]', '_', name or 'guest')}.log")
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(f"# {command}\n# guest {vmid} ({name}), {version}\n# exit code {code}, {seconds:.0f} s\n\n{out}")
        level = "bad" if code not in (0,) or fails else "warn" if warns else "ok"
        print(f"  {tag(level)} {vmid} ({name}): exit code {code}, {human_duration(int(seconds))} · {len(fails)} failures, {len(warns)} warnings" + (f" · {summary}" if summary else ""))
        for line in fails[:5]:
            print(f"      {line[:200]}")
        results.append((vmid, name, version, code, seconds, fails, warns, summary, out, path))
    report = os.path.join(folder, f"report-{os.uname().nodename}-{os.path.basename(folder)}.md")      # 1.18: the host in the name
    lines = [f"# host-perf-audit.py v{__version__} - command in the guests", "", f"- Host: {os.uname().nodename}", f"- Command: `{command}`",
             f"- Run on: {time.strftime('%Y-%m-%d %H:%M:%S')} (local time, {time.strftime('%Z')})", "",
             "| guest | version | exit code | duration | failures | warnings | summary |", "|---|---|---|---|---|---|---|"]
    for vmid, name, version, code, seconds, fails, warns, summary, _out, _p in results:
        lines.append(f"| {vmid} {name} | {version or '-'} | {code} | {human_duration(int(seconds))} | {len(fails)} | {len(warns)} | {summary or '-'} |")
    for vmid, name, version, code, seconds, fails, warns, summary, out, _p in results:
        lines += ["", f"## {vmid} ({name})", ""]
        if fails or warns:
            lines += ["Failures and warnings:", "", "```"] + fails + warns + ["```", ""]
        kept = out.rstrip("\n").splitlines()
        if len(kept) > 1500:
            kept = kept[:300] + [f"[... {len(kept) - 1500} lines left out, the whole output is in the .log file ...]"] + kept[-1200:]
        lines += ["Output:", "", "```"] + kept + ["```"]
    left = [(v, p) for v, p in targets if p]
    if left:
        lines += ["", "## Left out", ""] + [f"- {v}: {p}" for v, p in left]
    with os.fdopen(os.open(report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Outputs kept in {folder} · to send for analysis: {report}")
    if any(r[3] != 0 or r[5] for r in results):
        return 1
    return 1 if any(r[6] for r in results) else 0


SYNC_DEST_DEFAULT = os.environ.get("HOST_PERF_AUDIT_SYNC_DEST", "/opt/rlq-admin-tools")      # the variable for the tests only
SYNC_CHUNK = 960 * 1024          # bytes per « qm guest exec --pass-stdin » (the agent takes at most 1 MiB of input); 1.20: 700 KiB before
SYNC_GIT_MODES = ("all", "containers", "none")      # 1.20: where the .git folder is copied (default: containers; a VM gets it in chunks, slowly)
SYNC_EXCLUDES = ("__pycache__", "*.pyc", ".sync-token-*")


def sync_archive(source, with_git=True):
    """(path of a tar.gz of the source folder in a private temporary folder, its sha256, its size); the .git folder is kept, so that the copy in
    each guest is the same clone at the same commit."""
    import hashlib
    import tempfile
    folder = tempfile.mkdtemp(prefix="host-perf-audit-sync-")
    os.chmod(folder, 0o700)
    path = os.path.join(folder, "rlq-admin-tools.tar.gz")
    cmd = ["tar", "-C", source] + [f"--exclude={x}" for x in SYNC_EXCLUDES + (() if with_git else ("./.git",))] + ["-czf", path, "."]
    code, out = run(cmd, timeout=600)
    if code != 0:
        raise OSError(f"tar: {out.strip()[:200]}")
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return path, digest.hexdigest(), os.path.getsize(path)


def install_script(dest, archive, token):
    """Shell run in the guest: refuses when the destination IS the source (the token file is seen), extracts into DEST.new, checks it, keeps the
    previous copy as DEST.previous, then swaps; prints the version of nginx-hardening.sh that is now there."""
    return (f'set -e; D="{dest}"; if [ -e "$D/{token}" ]; then echo SAME; exit 0; fi; '
            f'OLD=$( [ -x "$D/nginx-hardening.sh" ] && "$D/nginx-hardening.sh" --version 2>/dev/null | head -1 || echo none ); '
            f'N="$D.new"; rm -rf "$N"; mkdir -p "$N"; tar -C "$N" --no-same-owner -xzf {archive}; '
            f'[ -x "$N/nginx-hardening.sh" ] || {{ echo "BAD archive"; rm -rf "$N"; exit 3; }}; '
            f'rm -rf "$D.previous"; if [ -e "$D" ]; then mv "$D" "$D.previous"; fi; mv "$N" "$D"; '
            f'echo "BEFORE $OLD"; echo "AFTER $("$D/nginx-hardening.sh" --version 2>/dev/null | head -1)"')


def push_to_guest(vmid, kind, archive, digest, dest, token, label=""):
    """(status « ok » | « same » | « error », text) after copying the archive into the guest and installing it there."""
    import subprocess as sp
    if kind == "lxc":
        script = install_script(dest, "-", token)
        try:
            with open(archive, "rb") as data:
                done = sp.run(["pct", "exec", vmid, "--", "sh", "-c", script], stdin=data, stdout=sp.PIPE, stderr=sp.STDOUT, timeout=900)
            out, code = done.stdout.decode("utf-8", "replace"), done.returncode
        except (OSError, sp.SubprocessError) as problem:
            return "error", str(problem)
    else:
        part = "/tmp/rlq-admin-tools-sync.tar.gz"
        code, out = guest_exec(vmid, kind, f"rm -f {part}; : > {part}", 30)
        if code != 0:
            return "error", f"cannot write {part} in the VM: {out.strip()[:200]}"
        total, sent, start, shown = os.path.getsize(archive), 0, time.monotonic(), -1
        live = sys.stdout.isatty()
        with open(archive, "rb") as f:
            for block in iter(lambda: f.read(SYNC_CHUNK), b""):
                sent += len(block)
                pct = sent * 100 // max(total, 1)
                elapsed = time.monotonic() - start
                left = int(elapsed / sent * (total - sent)) if sent else 0
                # 1.20: progress of the copy to a VM (chunks through the guest agent can take minutes): on the same line in a terminal, every 10 % otherwise
                if live:
                    print(f"\r  … {label}: {pct:3d} % ({size(sent)} of {size(total)}, about {human_duration(left)} left)   ", end="", flush=True)
                elif pct // 10 != shown:
                    shown = pct // 10
                    print(f"  … {label}: {pct} % ({size(sent)} of {size(total)})", flush=True)
                try:
                    done = sp.run(["qm", "guest", "exec", vmid, "--pass-stdin", "1", "--timeout", "60", "--", "sh", "-c", f"cat >> {part}"],
                                  input=block, stdout=sp.PIPE, stderr=sp.STDOUT, timeout=120)
                except (OSError, sp.SubprocessError) as problem:
                    return "error", f"copy interrupted: {problem}"
                answer = done.stdout.decode("utf-8", "replace")
                if done.returncode != 0 or '"exitcode":0' not in answer.replace(" ", ""):
                    if live:
                        print()
                    return "error", f"copy interrupted at {pct} %: {answer.strip()[:200]}"
        if live:
            print("\r" + " " * 100 + "\r", end="", flush=True)
        code, out = guest_exec(vmid, kind, f"sha256sum {part} | cut -c1-64", 60)
        if out.strip() != digest:
            return "error", f"the copy in the VM differs from the archive (sha256 {out.strip()[:16]}... instead of {digest[:16]}...)"
        code, out = guest_exec(vmid, kind, install_script(dest, part, token) + f"; rm -f {part}", 300)
    if "SAME" in (out or "").split():
        return "same", "this guest holds the source folder itself"
    before = re.search(r"^BEFORE (.*)$", out or "", re.M)
    after = re.search(r"^AFTER (.*)$", out or "", re.M)
    if code != 0 or not after:
        return "error", (out or "").strip()[-300:] or f"exit code {code}"
    return "ok", f"{before.group(1) if before else '?'} -> {after.group(1)}"


def guest_sync(args, names, running):
    """--guest-sync: copies the folder of the suite (the folder of this program, or --sync-source) to /opt/rlq-admin-tools in the guests of --guests.
    In each, the new copy is extracted beside the old one, checked, then swapped; the old one stays as /opt/rlq-admin-tools.previous.
    Exit code: 0 all updated, 1 a guest failed, 2 nothing done."""
    source = os.path.realpath(args.sync_source or SCRIPT_DIR)
    dest = SYNC_DEST_DEFAULT
    targets = resolve_guests(args.guests, names, running)
    if not targets:
        eprint("ERROR: --guest-sync needs the guests: --guests 101,105,433 (or « all », or the key GUESTS of the configuration).")
        return 2
    if not os.access(os.path.join(source, "nginx-hardening.sh"), os.X_OK):
        eprint(f"ERROR: {source} is not a copy of rlq-admin-tools (no executable nginx-hardening.sh): --sync-source FOLDER")
        return 2
    code, version = run([os.path.join(source, "nginx-hardening.sh"), "--version"], timeout=30)
    version = (version or "").strip().splitlines()[0] if (version or "").strip() else "?"
    code, commit = run(["git", "-C", source, "log", "-1", "--format=%h %cd", "--date=format:%Y-%m-%d %H:%M"], timeout=30)
    print(f"\nCOPY OF THE SUITE TO THE GUESTS — {source} ({version}" + (f", commit {commit.strip()}" if code == 0 and commit.strip() else "") + f") -> {dest}")
    ready = [(v, names[v][0], names[v][1]) for v, problem in targets if not problem]
    for vmid, problem in targets:
        if problem:
            print(f"  {tag('warn')} {vmid} ({names.get(vmid, ('', '?'))[1] or '?'}): left out — {problem}")
    if not ready:
        print("  Nothing to copy.")
        return 2
    if not args.yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("  Not done: no terminal to confirm it (add --yes).")
            return 2
        try:
            answer = input(f"  Replace {dest} in {len(ready)} guests ({', '.join(v for v, *_r in ready)}) by this copy (the old one kept as {dest}.previous)? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            answer = ""
        if answer not in ("o", "oui", "y", "yes"):
            print("  Not done.")
            return 2
    # The token marks the source folder during the WHOLE copy: a guest that sees it in its destination holds the source itself (a mount point of
    # the host, as /var/lib/vz/subvol-105-disk-2 for /opt of container 105) and is never replaced. Excluded from the archive.
    token = f".sync-token-{os.getpid()}-{int(time.time())}"
    mode = (getattr(args, "sync_git", None) or "containers").lower()
    if mode not in SYNC_GIT_MODES:
        eprint(f"ERROR: SYNC_GIT={mode}: expected one of {', '.join(SYNC_GIT_MODES)}.")
        return 2
    wants_git = {vmid: mode == "all" or (mode == "containers" and kind == "lxc") for vmid, kind, _n in ready}
    archives = {}
    try:
        open(os.path.join(source, token), "w").close()
        for with_git in sorted(set(wants_git.values()), reverse=True):        # 1.20: with and/or without .git, each made once
            archives[with_git] = sync_archive(source, with_git)
    except OSError as problem:
        eprint(f"ERROR: archive of {source} not made: {problem}")
        try:
            os.remove(os.path.join(source, token))
        except OSError:
            pass
        return 2
    print("  archive: " + " · ".join(f"{size(n)} {'with' if g else 'without'} .git (" + ", ".join(v for v in wants_git if wants_git[v] == g) + ")"
                                       for g, (_p, _d, n) in archives.items()) + f" — --sync-git {mode}")
    if any(not g for g in wants_git.values()) and os.path.isdir(os.path.join(source, ".git")):
        print(f"  without .git: in these guests {dest} is no longer a git clone (the old one, with its .git, stays in {dest}.previous)")
    failed = 0
    try:
        for vmid, kind, name in ready:
            start = time.monotonic()
            archive, digest, _n = archives[wants_git[vmid]]
            status, text = push_to_guest(vmid, kind, archive, digest, dest, token, f"{vmid} ({name})")
            level = {"ok": "ok", "same": "info", "error": "bad"}[status]
            failed += status == "error"
            print(f"  {tag(level)} {vmid} ({name}): " + (f"updated, {text} ({human_duration(int(time.monotonic() - start))})" if status == "ok" else text))
    finally:
        import shutil as sh
        for archive, _d, _n in archives.values():
            sh.rmtree(os.path.dirname(archive), ignore_errors=True)
        try:
            os.remove(os.path.join(source, token))
        except OSError:
            pass
    if failed < len(ready):
        print(f"  To go back in a guest: rm -rf {dest} && mv {dest}.previous {dest}")
    return 1 if failed else 0


# ---------------------------------------------------------------------------------------------------------------- command line
def changelog_section(path, key):
    """This program's section of CHANGELOG.md: from its '## <key>' heading up to the next '## ' heading."""
    with open(path, encoding="utf-8") as f:
        lignes = f.read().splitlines()
    section, dans = [], False
    for ligne in lignes:
        if ligne.startswith("## "):
            if dans:
                break
            dans = ligne[3:].strip() == key
            if dans:
                section.append(ligne)
        elif dans:
            section.append(ligne)
    return "\n".join(section) + "\n" if section else f"No changelog entry for {key} in {path}\n"


def show_changelog():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        text = changelog_section(CHANGELOG_FILE, "host-perf-audit.py")
    except OSError:
        print(f"Changelog not found: {CHANGELOG_FILE}", file=sys.stderr)
        return 1
    if sys.stdout.isatty():
        text = re.sub(r"(\d+\.\d+\.\d{8}\.\d{6})", "\x1b[1;36m\\1\x1b[0m", text)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


class SortedHelp(argparse.HelpFormatter):
    """Help options in ALPHABETICAL order (long name, without dashes)."""
    @staticmethod
    def _key(action):
        names = action.option_strings or [action.dest]
        return names[-1].lstrip("-").lower()

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions if groups else sorted(actions, key=self._key), groups, prefix)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._key))


class LocalizedArgumentParser(argparse.ArgumentParser):
    """Fallback parser (apps/_i18n.py missing): options in alphabetical order, English messages."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", SortedHelp)
        super().__init__(*args, **kwargs)


MENU_ENTREES = [
    ([], 'Measure performance (60 s)', 'Measure performance (60 s)', False),
    (['--apply'], 'Apply the safe settings', 'Apply the safe settings', True),
    (['--health', '--inside'], 'Quick health check (disks, pools, guests)', 'Quick health check (disks, pools, guests)', False),
]


def main():
    global VERBOSE
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="What limits the performance of a Proxmox host (or any Linux server): processor, memory, disks, network, ZFS, guests — measured "
                    "over a chosen duration, with a verdict, the answer to « are SSD disks justified? » and the settings to change.")
    parser.add_argument("--apply", action="store_true", help="After the report, apply the SAFE settings one by one with confirmation (ZFS compression / atime / recordsize of a dataset, ARC maximum, vm.swappiness); --yes: without questions")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/host-perf-audit.conf, then the personal file .host-perf-audit.conf; UPPERCASE options: CSV, DURATION, EXPORT_AI, GUEST_COMMAND, GUESTS, INSIDE, INTERVAL, LANGUAGE, NO_GUESTS, SYNC_GIT, SYNC_SOURCE, TOP, VERBOSE)")
    parser.add_argument("--csv", default=None, metavar="FILE", help="Also write every sample to this CSV file (one line per interval: CPU, waits, memory, ARC, each disk)")
    parser.add_argument("--duration", default="60", metavar="TIME", help="Length of the measurement: 90 (seconds), 10m, 4h, 1h30m… (default: 60 seconds)")
    parser.add_argument("--export-ai", nargs="?", const="", default=None, metavar="FILE",
                        help="Also write the report and the raw state of the host (pools, datasets, snapshots, disks, guests, backups, tasks, kernel warnings) to a Markdown "
                             "file without colors, to send for verification (default FILE: export-ai-HOST-YYYYMMDD-HHMMSS.md in /var/lib/host-perf-audit, mode 600; passwords and keys hidden)")
    parser.add_argument("--guest-command", default=None, metavar="CMD",
                        help=f"With --guest-run: the command to run in the guests (default: {GUEST_COMMAND_DEFAULT})")
    parser.add_argument("--guest-run", action="store_true",
                        help="Run a command (--guest-command, default nginx-hardening.sh --update) in the guests of --guests, one after the other: its program is "
                             "checked in each first, the run is confirmed (--yes: without the question), every output is kept with a report.md to send")
    parser.add_argument("--guest-sync", action="store_true",
                        help="Copy the folder of the suite (the folder of this program, or --sync-source) to /opt/rlq-admin-tools in the guests of --guests, "
                             "after confirmation (--yes: without the question); the old copy stays as /opt/rlq-admin-tools.previous. With --guest-run: the copy first")
    parser.add_argument("--guests", default=None, metavar="IDS",
                        help="With --guest-run: the containers and VMs, by number (101,105,433) or « all » (every running guest); key GUESTS of the configuration")
    parser.add_argument("--health", action="store_true",
                        help="Quick check without measurement: SMART counters of each disk (compared with the previous run), ZFS pools, RAID, kernel messages, space, backups, "
                             "alert services; with --inside, the inside of each guest. Exit code 0 (nothing), 1 (to watch), 2 (problem)")
    parser.add_argument("--inside", action="store_true",
                        help="Also look INSIDE each running guest, read-only (pct exec for a container, the QEMU guest agent for a VM): containers that restart in a loop, "
                             "failed services, journal, full disks, processes that write the most (takes 10 seconds per guest)")
    parser.add_argument("--install-timer", action="store_true", help="Install a systemd timer that runs --health --inside --notify every hour (root), then exit")
    parser.add_argument("--interval", type=float, default=None, metavar="SECONDS",
                        help="Seconds between two samples (default: 5 up to 2 minutes of measurement, 15 up to 30 minutes, 60 beyond)")
    parser.add_argument("--io-latency", nargs="?", type=float, const=20.0, default=None, metavar="MS",
                        help="Also trace WHO waits for the disks: the processes and guests (kernel delay accounting), the ZFS operations slower than MS "
                             "milliseconds file by file (zfsslower of bpfcc-tools) and the ZFS waits of each interval (default: 20 ms; root)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["en"], metavar="LANG", help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--menu", action="store_true", help="interactive menu of the common operations (dialog if installed; terminal required)")
    parser.add_argument("--no-collect", action="store_true",
                        help="Only list the commands at the end: do not run the read-only ones and do not offer the changes")
    parser.add_argument("--no-guests", action="store_true", help="Do not measure each container / VM (cgroups)")
    parser.add_argument("--notify", action="store_true",
                        help="With --health: send the findings by e-mail and to the system journal when something is new (reminder after 24 hours; one message when all is back to normal)")
    parser.add_argument("--report-err", action="store_true", help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--sync-git", default=None, choices=SYNC_GIT_MODES, metavar="MODE",
                        help="With --guest-sync: where the .git folder is copied: all, containers (default: a VM receives the copy in chunks through its agent, "
                             ".git makes it several times longer) or none; key SYNC_GIT")
    parser.add_argument("--sync-source", default=None, metavar="FOLDER",
                        help="With --guest-sync: the copy of rlq-admin-tools to send (default: the folder of this program); key SYNC_SOURCE")
    parser.add_argument("--top", type=int, default=8, metavar="N", help="Number of guests shown, the busiest on the disks first (default: 8)")
    parser.add_argument("--uninstall-timer", action="store_true", help="Remove the timer of --install-timer, then exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each command run")
    parser.add_argument("--version", action="version", version=f"host-perf-audit.py version {__version__}")
    parser.add_argument("--yes", action="store_true", help="With --apply or --guest-run: without questions")
    if "--version" not in sys.argv[1:]:
        print(f"host-perf-audit.py v{__version__}")
    defaults, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    parser.add_argument("--config-merge", action="store_true",
                        help="Rewrite the configuration file from the NEW default configuration (example of the current language), keeping the values set in the file "
                             "read until now; the old file is copied first to FILE.bak-YYYYMMDD-HHMMSS (with -c: that file only). Then exit")
    args = parser.parse_args()
    if args.menu:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_menu", os.path.join(SCRIPT_DIR, "apps", "_menu.py"))
        _menu = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_menu)
        _menu.menu(os.path.abspath(__file__), sys.argv[1:], MENU_ENTREES,
                   traduire=I18N.tr if I18N else None, langue=I18N.langue if I18N else "fr",
                   configuration=_menu.configuration_de(SCRIPT_DIR, "host-perf-audit", sys.argv[1:]),
                   nom=f"host-perf-audit.py v{__version__}")
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defaults, problems)
    if args.config_merge:                     # --config-merge (apps/_config.py fusionner, same rule for every program)
        sys.path.insert(0, os.path.join(SCRIPT_DIR, "apps"))
        import _config
        langue = globals().get("LANGUAGE") or getattr(globals().get("I18N"), "langue", None) or "fr"
        sys.exit(_config.fusionner_cli(SCRIPT_NAME, args.config, langue))
    if args.changelog:
        return show_changelog()
    VERBOSE = args.verbose
    if args.install_timer:
        return install_health_timer()
    if args.uninstall_timer:
        return uninstall_health_timer()
    if args.guest_run or args.guest_sync:     # 1.17: a command in the guests; 1.18: the copy of the suite first
        if os.geteuid() != 0 and "HOST_PERF_AUDIT_PVE_DIR" not in os.environ:
            eprint("ERROR: --guest-run and --guest-sync need root (pct exec, qm guest exec).")
            return 2
        names, running = guest_names(), guest_cgroups()
        code = guest_sync(args, names, running) if args.guest_sync else 0
        if args.guest_run and code != 2:
            code = max(code, guest_run(args, names, running))
        return code
    if args.health:                           # 1.12: quick check, no measurement
        if os.geteuid() != 0:
            eprint("Limited rights: without root, smartctl, the ZFS commands and the guests are unreadable (sudo for a complete check).")
        ensure_required(args)                             # 1.25: smartctl installed when missing
        return health(args, host_facts(), zfs_facts(), guest_names(), {} if args.no_guests else guest_cgroups())
    try:
        duration = parse_duration(args.duration)
    except ValueError:
        parser.error(f"--duration: unreadable value « {args.duration} » (e.g. 90, 10m, 4h, 1h30m)")
    if not 5 <= duration <= 7 * 86400:
        parser.error("--duration expects between 5 seconds and 7 days")
    interval = args.interval or (5.0 if duration <= 120 else 15.0 if duration <= 1800 else 60.0)
    interval = max(1.0, min(interval, duration))
    if SYSPERF is None:
        eprint("ERROR: component apps/_sysperf.py missing: copy the whole nginx-tools folder (apps/ included).")
        return 2
    if os.geteuid() != 0:
        eprint("Limited rights: without root, smartctl, the ZFS commands and some counters are unreadable (sudo for a complete report).")
    ensure_required(args)                                 # 1.25: before the priority is lowered (apt-get would run at idle I/O class)
    lower_own_priority()
    export_path = export_ai_path(args.export_ai)
    tee = None
    if export_path is not None:                 # --export-ai: everything printed from here is also kept for the file
        tee = sys.stdout = Tee(sys.stdout)
    t0 = os.times()
    facts = host_facts()
    zfs = zfs_facts()
    smart = smart_health(facts["disks"])
    names = guest_names()
    guests = {} if args.no_guests else guest_cgroups()
    if not facts["pve"]:
        eprint("Note: not a Proxmox VE host (pveversion not found): guests are not named; the measurement of the machine itself stays valid.")
    if os.path.exists("/run/systemd/container") or os.path.exists(SYSPERF._p("/run/systemd/container")):
        eprint("WARNING: this program runs inside a container: the disks shown are not the real ones — run it on the Proxmox host.")
    config = [] if args.no_guests or not names else guest_config_check(names, guests, zfs)
    if names and not args.no_guests:                      # 1.13: said at the start, before the measurement
        print_config_check(config, len(names), brief=True)
    print(f"Measuring for {human_duration(duration)}, one sample every {interval:g} s ({len(facts['disks'])} disks, {len(guests)} running guests"
          + (f", ZFS pools: {', '.join(zfs['pools'])}" if zfs else "") + ") — Ctrl-C stops early and still gives the report.")
    host_tasks = io_tasks()
    tracer = None
    if args.io_latency is not None:                       # 1.23: who waits for the disks, on which files
        tracer = start_io_latency(args.io_latency, interval, zfs, names, guests)
    try:
        samples = sample_loop(duration, interval, guests, args.csv)
    finally:
        if tracer is not None:
            tracer.stop()
    host_tasks |= io_tasks()
    inside = None
    if args.inside and guests:
        inside = Health()
        check_inside(inside, names, guests)
    t1 = os.times()
    cost = (t1.user + t1.system + t1.children_user + t1.children_system) - (t0.user + t0.system + t0.children_user + t0.children_system)
    fd = report(samples, facts, zfs, smart, names, lambda s, out: analyze_guests(s, names, args.top, out), args, cost, host_tasks, inside, config,
                io=io_results(tracer))
    if args.csv and samples:
        print(f"\nSamples written to {args.csv}.")
    if tee is not None:
        sys.stdout = tee.stream
        export_ai(export_path, "".join(tee.parts), facts, names, "host-perf-audit.py " + " ".join(sys.argv[1:]))
    if args.apply:
        return offer_apply(fd, args.yes)
    return 0


def protected_main():
    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl-C).", file=sys.stderr)
        return 130


def launch_with_report(function):
    """--report-err: paste-ready error report at the end of the run (apps/_rapport.py, if next to this file)."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        try:
            spec = importlib.util.spec_from_file_location("_rapport", os.path.join(SCRIPT_DIR, "apps", "_rapport.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"--report-err unavailable ({e}) — normal run.", file=sys.stderr)
            return function()
        return module.lancer(function, os.path.basename(__file__), __version__, SCRIPT_DIR)
    return function()


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(protected_main))
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
