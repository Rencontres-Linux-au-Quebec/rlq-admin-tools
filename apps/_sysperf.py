#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _sysperf.py — performance counters of the machine read from /proc and /sys, WITHOUT any external command (shared module, apps/):
# processor (busy, iowait, steal), pressure stall information (PSI: cpu, io, memory — host or container cgroup), disks (% utilization, wait per
# operation, operations and bytes per second), memory, network, ZFS ARC. Used by app-log-live.py (latency of the requests: is it the disk?) and
# host-perf-audit.py (Proxmox host: what limits the performance).
#
# VERSION HISTORY (summary — see doc/_sysperf.changelog.txt for the full detail):
#   1.2.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.1.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.0.20261016.114848 — First version: snapshot() and rates() over /proc/stat, /proc/pressure, cgroup v2, /proc/diskstats, /proc/meminfo,
#                         /proc/net/dev, ZFS arcstats.
"""Two snapshots and their difference: a sample costs a few small file reads (well under a millisecond of processor).

    a = snapshot(); time.sleep(30); b = snapshot(); r = rates(a, b)

r = {"dt", "cpu": {"busy", "user", "system", "iowait", "steal"} (% of all the processors), "psi": {"cpu"|"io"|"memory": {"some", "full"}} (% of the time
some / all tasks were stalled, from the kernel's cumulative counters: exact over the interval), "disks": {dev: {"util", "r_s", "w_s", "rkb_s", "wkb_s",
"r_await", "w_await", "queue"}}, "net": {iface: {"rx_kb_s", "tx_kb_s", "errors", "drops"}}, "arc": {"hit", "size", "c_max"} or None, "mem": meminfo kB}.

Unreadable sources are simply absent (container without /proc/pressure, no ZFS…). NGINX_TOOLS_PROC_ROOT prefixes every path (tests: fake /proc and /sys)."""
import os
import re
import time

__version__ = "1.2.20261019.150215"

ROOT = os.environ.get("NGINX_TOOLS_PROC_ROOT", "")
SKIP_DEVICES = ("loop", "ram", "zram", "sr", "fd", "nbd")
CPU_FIELDS = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")


def _p(path):
    return ROOT + path


def _read(path):
    try:
        with open(_p(path), encoding="ascii", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def cpu_times():
    """{field: ticks} of the first line of /proc/stat and "n" (number of processors); None if unreadable."""
    text = _read("/proc/stat")
    if not text:
        return None
    first = text.split("\n", 1)[0].split()
    if not first or first[0] != "cpu":
        return None
    values = [int(x) for x in first[1:9]] + [0] * (8 - len(first[1:9]))
    res = dict(zip(CPU_FIELDS, values))
    res["n"] = len(re.findall(r"^cpu\d+ ", text, re.M)) or 1
    return res


def cgroup_root():
    """Directory of the cgroup v2 of this machine or container (/sys/fs/cgroup when cgroup.controllers exists), else None. In a Proxmox LXC container,
    it is the CONTAINER's own cgroup: its io.pressure measures the waits of the container only (lxcfs does not virtualize /proc/pressure)."""
    return "/sys/fs/cgroup" if os.path.exists(_p("/sys/fs/cgroup/cgroup.controllers")) else None


def psi(kind, base=None):
    """Pressure stall information of `kind` (cpu, io, memory): {"some": {"avg10", "avg60", "avg300", "total"}, "full": {…}}; None if absent.
    base=None: the whole machine (/proc/pressure); otherwise a cgroup directory (its KIND.pressure)."""
    text = _read(f"{base}/{kind}.pressure" if base else f"/proc/pressure/{kind}")
    if not text:
        return None
    res = {}
    for line in text.splitlines():
        m = re.match(r"(some|full) avg10=([\d.]+) avg60=([\d.]+) avg300=([\d.]+) total=(\d+)", line)
        if m:
            res[m.group(1)] = {"avg10": float(m.group(2)), "avg60": float(m.group(3)), "avg300": float(m.group(4)), "total": int(m.group(5))}
    return res or None


def is_whole_disk(name):
    """True for a whole disk (/sys/block/NAME exists), not a partition; loops, RAM disks, CD-ROM and network block devices excluded."""
    return not name.startswith(SKIP_DEVICES) and os.path.isdir(_p(f"/sys/block/{name}"))


def rotational(name):
    """True: spinning hard disk (SATA/SAS HDD); False: SSD / NVMe; None: unknown (virtual device, ZFS volume zdN, device-mapper)."""
    text = _read(f"/sys/block/{name}/queue/rotational")
    if text is None or name.startswith(("zd", "dm-", "md")):
        return None
    return text.strip() == "1"


def disk_model(name):
    text = _read(f"/sys/block/{name}/device/model")
    return " ".join(text.split()) if text else ""


def diskstats():
    """{device: {"reads", "rd_sectors", "rd_ms", "writes", "wr_sectors", "wr_ms", "in_flight", "io_ms", "weighted_ms"}} of the WHOLE disks of /proc/diskstats."""
    text = _read("/proc/diskstats")
    res = {}
    for line in (text or "").splitlines():
        c = line.split()
        if len(c) < 14 or not is_whole_disk(c[2]):
            continue
        try:
            v = [int(x) for x in c[3:14]]
        except ValueError:
            continue
        res[c[2]] = {"reads": v[0], "rd_sectors": v[2], "rd_ms": v[3], "writes": v[4], "wr_sectors": v[6], "wr_ms": v[7], "in_flight": v[8],
                     "io_ms": v[9], "weighted_ms": v[10]}
    return res


def meminfo():
    res = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        k, _, rest = line.partition(":")
        try:
            res[k.strip()] = int(rest.split()[0])
        except (ValueError, IndexError):
            continue
    return res


def net_dev():
    """{interface: (rx_bytes, tx_bytes, rx_errs + tx_errs, rx_drop + tx_drop)} of /proc/net/dev (lo excluded)."""
    res = {}
    for line in (_read("/proc/net/dev") or "").splitlines()[2:]:
        name, _, rest = line.partition(":")
        c = rest.split()
        if len(c) >= 16 and name.strip() != "lo":
            try:
                res[name.strip()] = (int(c[0]), int(c[8]), int(c[2]) + int(c[10]), int(c[3]) + int(c[11]))
            except ValueError:
                continue
    return res


def arcstats():
    """ZFS ARC counters (/proc/spl/kstat/zfs/arcstats): {"hits", "misses", "size", "c_max", "c_min", "l2_hits", "l2_misses", "memory_throttle_count"…}; None without ZFS."""
    text = _read("/proc/spl/kstat/zfs/arcstats")
    if not text:
        return None
    res = {}
    for line in text.splitlines():
        c = line.split()
        if len(c) == 3 and c[2].isdigit():
            res[c[0]] = int(c[2])
    return res or None


def loadavg():
    text = _read("/proc/loadavg")
    try:
        return float(text.split()[0]) if text else None
    except (ValueError, IndexError):
        return None


def snapshot(cgroup=True, net=True, arc=True):
    """Every counter at this instant. cgroup=True: the PSI of the cgroup v2 (container) when it exists, otherwise those of /proc/pressure."""
    base = cgroup_root() if cgroup else None
    pressures = {}
    for kind in ("cpu", "io", "memory"):
        v = psi(kind, base) if base else None
        if v is None:
            v = psi(kind)
        if v is not None:
            pressures[kind] = v
    return {"t": time.monotonic(), "wall": time.time(), "cpu": cpu_times(), "psi": pressures, "psi_source": base or "/proc/pressure",
            "disks": diskstats(), "net": net_dev() if net else {}, "arc": arcstats() if arc else None, "mem": meminfo(), "load": loadavg()}


def rates(a, b):
    """Difference of two snapshots (b after a): percentages and rates over the interval (see the module docstring)."""
    dt = max(b["t"] - a["t"], 1e-6)
    res = {"dt": dt, "wall": b["wall"], "cpu": None, "psi": {}, "disks": {}, "net": {}, "arc": None, "mem": b.get("mem") or {}, "load": b.get("load")}
    ca, cb = a.get("cpu"), b.get("cpu")
    total = sum(cb[f] - ca[f] for f in CPU_FIELDS) if ca and cb else 0
    if total > 0:                                   # no tick elapsed (counters frozen): no processor measure rather than a false 100 %
        d = {f: 100.0 * (cb[f] - ca[f]) / total for f in CPU_FIELDS}
        res["cpu"] = {"busy": 100.0 - d["idle"] - d["iowait"], "user": d["user"] + d["nice"], "system": d["system"] + d["irq"] + d["softirq"],
                      "iowait": d["iowait"], "steal": d["steal"], "n": cb["n"]}
    for kind, vb in b.get("psi", {}).items():
        va = a.get("psi", {}).get(kind)
        if not va:
            continue
        res["psi"][kind] = {k: max(0.0, min(100.0, (vb[k]["total"] - va[k]["total"]) / 1e6 / dt * 100.0)) for k in ("some", "full") if k in vb and k in va}
    for dev, vb in b.get("disks", {}).items():
        va = a.get("disks", {}).get(dev)
        if not va:
            continue
        r, w = vb["reads"] - va["reads"], vb["writes"] - va["writes"]
        res["disks"][dev] = {"util": max(0.0, min(100.0, (vb["io_ms"] - va["io_ms"]) / (dt * 10.0))), "r_s": r / dt, "w_s": w / dt,
                             "rkb_s": (vb["rd_sectors"] - va["rd_sectors"]) / 2.0 / dt, "wkb_s": (vb["wr_sectors"] - va["wr_sectors"]) / 2.0 / dt,
                             "r_await": (vb["rd_ms"] - va["rd_ms"]) / r if r > 0 else None, "w_await": (vb["wr_ms"] - va["wr_ms"]) / w if w > 0 else None,
                             "queue": (vb["weighted_ms"] - va["weighted_ms"]) / (dt * 1000.0)}
    for iface, vb in b.get("net", {}).items():
        va = a.get("net", {}).get(iface)
        if va:
            res["net"][iface] = {"rx_kb_s": (vb[0] - va[0]) / 1024.0 / dt, "tx_kb_s": (vb[1] - va[1]) / 1024.0 / dt, "errors": vb[2] - va[2], "drops": vb[3] - va[3]}
    aa, ab = a.get("arc"), b.get("arc")
    if aa and ab:
        hits, misses = ab.get("hits", 0) - aa.get("hits", 0), ab.get("misses", 0) - aa.get("misses", 0)
        res["arc"] = {"hit": 100.0 * hits / (hits + misses) if hits + misses else None, "size": ab.get("size", 0), "c_max": ab.get("c_max", 0),
                      "c_min": ab.get("c_min", 0), "throttle": ab.get("memory_throttle_count", 0) - aa.get("memory_throttle_count", 0),
                      "l2_hit": (100.0 * (ab.get("l2_hits", 0) - aa.get("l2_hits", 0)) / max(1, (ab.get("l2_hits", 0) - aa.get("l2_hits", 0)) + (ab.get("l2_misses", 0) - aa.get("l2_misses", 0))))
                      if "l2_hits" in ab and (ab.get("l2_hits", 0) + ab.get("l2_misses", 0)) > (aa.get("l2_hits", 0) + aa.get("l2_misses", 0)) else None}
    return res


def busiest_disk(r):
    """(device, % utilization) of the most used disk of a rates() result, or (None, 0.0)."""
    if not r.get("disks"):
        return None, 0.0
    dev = max(r["disks"], key=lambda d: r["disks"][d]["util"])
    return dev, r["disks"][dev]["util"]


def main(argv):
    """python3 apps/_sysperf.py [SECONDS]: one sample over SECONDS (default 5), printed as key=value lines; --version."""
    if "--version" in argv:
        print(__version__)
        return 0
    secs = float(argv[0]) if argv and argv[0].replace(".", "", 1).isdigit() else 5.0
    a = snapshot()
    time.sleep(secs)
    r = rates(a, snapshot())
    if r["cpu"]:
        print("cpu " + " ".join(f"{k}={v:.1f}" for k, v in r["cpu"].items() if k != "n"))
    for kind, v in r["psi"].items():
        print(f"psi.{kind} " + " ".join(f"{k}={x:.1f}" for k, x in v.items()))
    for dev, v in sorted(r["disks"].items()):
        print(f"disk.{dev} " + " ".join(f"{k}={x:.1f}" for k, x in v.items() if x is not None))
    if r["arc"]:
        print("arc " + " ".join(f"{k}={x}" for k, x in r["arc"].items()))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
