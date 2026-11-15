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
#   * --apply: the SAFE and reversible settings (ZFS atime and compression of a dataset, ARC maximum, vm.swappiness) are offered one by one with
#     confirmation; the others (hardware, VM disk options) are explained, never changed.
# Configuration (common rule): /etc/default/host-perf-audit.conf THEN ~/.host-perf-audit.conf (the last one wins; keys CSV, DURATION, EXPORT_AI, INTERVAL, LANGUAGE,
# NO_GUESTS, TOP, VERBOSE); -c/--config: that file ALONE; the command line takes priority.
#
#
# Usage:
#   host-perf-audit.py                         one minute of measurement (sample every 5 s), then the report
#   host-perf-audit.py --duration 4h           four hours (sample every 60 s): the daily peaks are included
#   host-perf-audit.py --duration 30m --csv /root/perf.csv   samples also written to a CSV file (spreadsheet)
#   host-perf-audit.py --apply                 report, then the safe settings offered one by one
#   host-perf-audit.py --export-ai             report, then the report and the raw state of the host in a Markdown file to send for verification
import argparse
import datetime
import glob
import importlib.util
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

__version__ = "1.11.20261114.192640"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
PVE_DIR = os.environ.get("HOST_PERF_AUDIT_PVE_DIR", "/etc/pve")
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
SCHEMA_CONFIG = {"CSV": ("csv", str), "DURATION": ("duration", str), "EXPORT_AI": ("export_ai", str), "INTERVAL": ("interval", float), "NO_GUESTS": ("no_guests", bool), "TOP": ("top", int),
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
            pools[c[0]] = {"size": int(c[1]) if c[1].isdigit() else 0, "frag": c[4].rstrip("%"), "cap": c[5].rstrip("%"), "health": c[6],
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
    out.append("  (PostgreSQL / Odoo container: recordsize=16K on its dataset suits the 8 KiB pages of PostgreSQL; only for new files: set it before a restore)")


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
def report(samples, facts, zfs, smart, names, guests_rows_cb, args, cost, host_tasks=()):
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
    if dur < 1800:
        print()
        print(f"  Short measurement ({human_duration(dur)}): to see the daily peaks (backups, busy hours), run it for hours: host-perf-audit.py --duration 24h")
    return fd


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
]


def main():
    global VERBOSE
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="What limits the performance of a Proxmox host (or any Linux server): processor, memory, disks, network, ZFS, guests — measured "
                    "over a chosen duration, with a verdict, the answer to « are SSD disks justified? » and the settings to change.")
    parser.add_argument("--apply", action="store_true", help="After the report, apply the SAFE settings one by one with confirmation (ZFS compression / atime of a dataset, ARC maximum, vm.swappiness); --yes: without questions")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/host-perf-audit.conf, then the personal file .host-perf-audit.conf; UPPERCASE options: CSV, DURATION, EXPORT_AI, INTERVAL, LANGUAGE, NO_GUESTS, TOP, VERBOSE)")
    parser.add_argument("--csv", default=None, metavar="FILE", help="Also write every sample to this CSV file (one line per interval: CPU, waits, memory, ARC, each disk)")
    parser.add_argument("--duration", default="60", metavar="TIME", help="Length of the measurement: 90 (seconds), 10m, 4h, 1h30m… (default: 60 seconds)")
    parser.add_argument("--export-ai", nargs="?", const="", default=None, metavar="FILE",
                        help="Also write the report and the raw state of the host (pools, datasets, snapshots, disks, guests, backups, tasks, kernel warnings) to a Markdown "
                             "file without colors, to send for verification (default FILE: export-ai-HOST-YYYYMMDD-HHMMSS.md in /var/lib/host-perf-audit, mode 600; passwords and keys hidden)")
    parser.add_argument("--interval", type=float, default=None, metavar="SECONDS",
                        help="Seconds between two samples (default: 5 up to 2 minutes of measurement, 15 up to 30 minutes, 60 beyond)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["en"], metavar="LANG", help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--menu", action="store_true", help="interactive menu of the common operations (dialog if installed; terminal required)")
    parser.add_argument("--no-guests", action="store_true", help="Do not measure each container / VM (cgroups)")
    parser.add_argument("--report-err", action="store_true", help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--top", type=int, default=8, metavar="N", help="Number of guests shown, the busiest on the disks first (default: 8)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each command run")
    parser.add_argument("--version", action="version", version=f"host-perf-audit.py version {__version__}")
    parser.add_argument("--yes", action="store_true", help="With --apply: without questions")
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
    print(f"Measuring for {human_duration(duration)}, one sample every {interval:g} s ({len(facts['disks'])} disks, {len(guests)} running guests"
          + (f", ZFS pools: {', '.join(zfs['pools'])}" if zfs else "") + ") — Ctrl-C stops early and still gives the report.")
    host_tasks = io_tasks()
    samples = sample_loop(duration, interval, guests, args.csv)
    host_tasks |= io_tasks()
    t1 = os.times()
    cost = (t1.user + t1.system + t1.children_user + t1.children_system) - (t0.user + t0.system + t0.children_user + t0.children_system)
    fd = report(samples, facts, zfs, smart, names, lambda s, out: analyze_guests(s, names, args.top, out), args, cost, host_tasks)
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
