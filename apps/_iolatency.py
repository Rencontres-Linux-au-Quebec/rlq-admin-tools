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
# _iolatency.py - WHO waits for the disks, and on WHICH files (shared module, apps/), for host-perf-audit.py --io-latency:
#   * per process (and per guest: LXC container or VM, from /proc/PID/cgroup): the time spent waiting for block I/O, from the kernel's delay
#     accounting (/proc/PID/task/TID/stat, field 42); kernel.task_delayacct is switched on for the measurement and restored after it;
#   * per file: every ZFS read, write, open or fsync slower than a threshold, with the process and the file name (zfsslower of bcc, when installed);
#   * per pool: the ZFS waits of each interval of the measurement (zpool iostat -y -l -H -p), not the averages since the import of the pool.
"""t = Tracer(threshold_ms=20, interval=5); t.start(); ...; t.stop(); r = t.results()

r = {"delayacct": "on" | "enabled" | "unavailable", "procs": [{"guest", "pid", "comm", "wait_s"}...] (largest first),
     "slow": {"tool": path or None, "count", "files": [{"guest", "comm", "op", "file", "count", "total_ms", "max_ms"}...], "error"},
     "pools": {pool: {"intervals", "read_ms": [...], "write_ms": [...], "disk_read_ms": [...], "syncq_read_ms": [...]}}}
NGINX_TOOLS_PROC_ROOT prefixes the paths of /proc (tests)."""
import glob
import os
import re
import shutil
import subprocess
import threading

__version__ = "1.0.20261118.064500"

ROOT = os.environ.get("NGINX_TOOLS_PROC_ROOT", "")
DELAYACCT = "/proc/sys/kernel/task_delayacct"
SLOWER_TOOLS = ("zfsslower-bpfcc", "/usr/share/bcc/tools/zfsslower", "/usr/sbin/zfsslower-bpfcc", "zfsslower")
# bcc zfsslower:  TIME     COMM           PID    T BYTES   OFF_KB   LAT(ms) FILENAME
SLOW_RE = re.compile(r"^\d\d:\d\d:\d\d\s+(\S.{0,15}?)\s+(\d+)\s+([RWOS])\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(.*)$")
OPS = {"R": "read", "W": "write", "O": "open", "S": "fsync"}
CGROUP_LXC_RE = re.compile(r"/lxc(?:\.payload)?[./](\d+)(?:/|$)")
CGROUP_VM_RE = re.compile(r"/qemu\.slice/(\d+)\.scope")


def _p(path):
    return ROOT + path


def _read(path):
    try:
        with open(_p(path), encoding="ascii", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def guest_of(pid):
    """« lxc 105 », « vm 430 » or « host » from /proc/PID/cgroup (cgroup v2); None when the process is gone."""
    text = _read(f"/proc/{pid}/cgroup")
    if text is None:
        return None
    m = CGROUP_LXC_RE.search(text)
    if m:
        return "lxc " + m.group(1)
    m = CGROUP_VM_RE.search(text)
    if m:
        return "vm " + m.group(1)
    return "host"


def blkio_ticks():
    """{pid: (comm, ticks)}: the block I/O delay of every thread, summed per process (field 42 of /proc/PID/task/TID/stat)."""
    res = {}
    for stat in glob.glob(_p("/proc/[0-9]*/task/[0-9]*/stat")):
        try:
            with open(stat, encoding="ascii", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        lp, rp = text.find("("), text.rfind(")")
        if lp < 0 or rp < 0:
            continue
        fields = text[rp + 2:].split()
        if len(fields) < 40:
            continue
        try:
            ticks = int(fields[39])          # field 42 (delayacct_blkio_ticks): the list starts at field 3
        except ValueError:
            continue
        pid = stat[len(_p("/proc/")):].split("/", 1)[0]
        comm, total = res.get(pid, (None, 0))
        if comm is None or stat.endswith(f"/task/{pid}/stat"):
            comm = text[lp + 1:rp]
        res[pid] = (comm, total + ticks)
    return res


def pool_line(line):
    """One line of « zpool iostat -y -l -H -p POOL... »: (pool, {read, write, disk_read, syncq_read} in ms, read ops) or None.
    Columns: name alloc free rops wops rbytes wbytes total_r total_w disk_r disk_w syncq_r syncq_w asyncq_r asyncq_w scrub trim [rebuild]."""
    w = line.split("\t") if "\t" in line else line.split()
    if len(w) < 15:
        return None

    def ms(v):
        try:
            return int(v) / 1e6
        except ValueError:
            return None
    try:
        rops = float(w[3])
    except ValueError:
        return None
    return w[0], {"read": ms(w[7]), "write": ms(w[8]), "disk_read": ms(w[9]), "syncq_read": ms(w[11])}, rops


class Tracer:
    def __init__(self, threshold_ms=20.0, interval=5.0, pools=(), runner=None, which=shutil.which):
        self.threshold = threshold_ms
        self.interval = max(1, int(round(interval)))
        self.pools = list(pools)
        self.which = which
        self.popen = runner or subprocess.Popen
        self.state = "unavailable"
        self.restore = None
        self.before = {}
        self.after = {}
        self.ticks_per_s = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        self.slow_tool = None
        self.slow_proc = None
        self.slow_error = ""
        self.slow = {}               # (guest, comm, op, file) -> [count, total, max]
        self.slow_count = 0
        self.pool_proc = None
        self.pool_data = {}
        self.threads = []
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ delay accounting
    def _delayacct_on(self):
        value = (_read(DELAYACCT) or "").strip()
        if value == "1":
            return "on"
        if value != "0":
            return "unavailable"
        try:
            with open(_p(DELAYACCT), "w", encoding="ascii") as f:
                f.write("1\n")
        except OSError:
            return "unavailable"
        self.restore = "0"
        return "enabled"

    def _delayacct_restore(self):
        if self.restore is not None:
            try:
                with open(_p(DELAYACCT), "w", encoding="ascii") as f:
                    f.write(self.restore + "\n")
            except OSError:
                pass
            self.restore = None

    # ------------------------------------------------------------------ zfsslower
    def find_slow_tool(self):
        for name in SLOWER_TOOLS:
            path = self.which(name) if not name.startswith("/") else (name if os.path.isfile(name) and os.access(name, os.X_OK) else None)
            if path:
                return path
        return None

    def _read_slow(self, stream):
        cache = {}
        for line in stream:
            m = SLOW_RE.match(line.rstrip("\n"))
            if not m:
                if "error" in line.lower() or "cannot" in line.lower() or "failed" in line.lower():
                    self.slow_error = (self.slow_error or line.strip())[:300]
                continue
            comm, pid, op, _bytes, _off, lat, name = m.groups()
            guest = cache.get(pid)
            if guest is None:
                guest = cache[pid] = guest_of(pid) or "?"
            lat = float(lat)
            key = (guest, comm.strip(), OPS.get(op, op), name.strip() or "?")
            with self.lock:
                e = self.slow.setdefault(key, [0, 0.0, 0.0])
                e[0] += 1
                e[1] += lat
                e[2] = max(e[2], lat)
                self.slow_count += 1

    # ------------------------------------------------------------------ zpool iostat
    def _read_pools(self, stream):
        for line in stream:
            parsed = pool_line(line.rstrip("\n"))
            if not parsed:
                continue
            pool, waits, rops = parsed
            with self.lock:
                d = self.pool_data.setdefault(pool, {"intervals": 0, "read_ms": [], "write_ms": [], "disk_read_ms": [], "syncq_read_ms": []})
                d["intervals"] += 1
                if rops > 0 and waits["read"] is not None:
                    d["read_ms"].append(waits["read"])
                    if waits["disk_read"] is not None:
                        d["disk_read_ms"].append(waits["disk_read"])
                    if waits["syncq_read"] is not None:
                        d["syncq_read_ms"].append(waits["syncq_read"])
                if waits["write"] is not None:
                    d["write_ms"].append(waits["write"])

    def _spawn(self, cmd, reader):
        try:
            proc = self.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                              universal_newlines=True, errors="replace", bufsize=1)
        except (OSError, ValueError) as e:
            return None, str(e)
        th = threading.Thread(target=reader, args=(proc.stdout,), daemon=True)
        th.start()
        self.threads.append(th)
        return proc, ""

    def start(self):
        self.state = self._delayacct_on()
        self.before = blkio_ticks() if self.state != "unavailable" else {}
        self.slow_tool = self.find_slow_tool()
        if self.slow_tool:
            self.slow_proc, self.slow_error = self._spawn([self.slow_tool, str(int(self.threshold) if self.threshold >= 1 else 1)], self._read_slow)
        if self.pools and self.which("zpool"):
            self.pool_proc, _err = self._spawn(["zpool", "iostat", "-y", "-l", "-H", "-p"] + self.pools + [str(self.interval)], self._read_pools)

    def stop(self):
        for proc in (self.slow_proc, self.pool_proc):
            if proc is None:
                continue
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        for th in self.threads:
            th.join(timeout=5)
        if self.state != "unavailable":
            self.after = blkio_ticks()
        self._delayacct_restore()

    def results(self, top=12):
        procs = []
        for pid, (comm, ticks) in self.after.items():
            prev = self.before.get(pid)
            if prev is None or prev[0] != comm:
                continue                     # started during the measurement (or pid reused): its delay began before switching on is unknown
            delta = (ticks - prev[1]) / float(self.ticks_per_s or 100)
            if delta > 0:
                procs.append({"guest": guest_of(pid) or "?", "pid": pid, "comm": comm, "wait_s": delta})
        procs.sort(key=lambda p: -p["wait_s"])
        with self.lock:
            files = [{"guest": g, "comm": c, "op": o, "file": f, "count": v[0], "total_ms": v[1], "max_ms": v[2]}
                     for (g, c, o, f), v in self.slow.items()]
            pools = {k: dict(v) for k, v in self.pool_data.items()}
            count = self.slow_count
        files.sort(key=lambda f: -f["total_ms"])
        return {"delayacct": self.state, "procs": procs[:top], "procs_all": len(procs),
                "slow": {"tool": self.slow_tool, "count": count, "files": files[:top], "error": self.slow_error, "threshold": self.threshold},
                "pools": pools}
