#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026  Services-Linux Conseils Inc <Martial@Bigras.ca> <Martial.Bigras@Services-Conseils-Linux.com>
# License: GNU Affero General Public License, version 3 or later — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# host-perf-audit.py — WHAT LIMITS THE PERFORMANCE of a hypervisor (Proxmox VE) or of any Linux server: processor, memory, disks, network, ZFS,
# measured over a chosen duration (a minute to several hours), then a verdict per resource, the answer to « are SSD disks justified? » and the
# settings to change (ZFS, ARC, swappiness…). Run it ON THE PROXMOX HOST: inside a container, the real disks are not visible.
#   * Light by design: one sample every INTERVAL seconds reads a few small files of /proc and /sys (apps/_sysperf.py, no external command); the
#     program lowers its own priority (nice 10, idle I/O class) and reports what it cost. The few commands (zpool, zfs, pveversion, smartctl) run ONCE.
#   * Per guest (LXC containers and VMs): processor, memory, disk throughput and disk waiting time, from their cgroup (cgroup v2), named from
#     /etc/pve (hostname / name).
#   * Ctrl-C during the measurement: the report is still produced with the samples already taken.
#   * --apply: the SAFE and reversible settings (ZFS atime and compression of a dataset, ARC maximum, vm.swappiness) are offered one by one with
#     confirmation; the others (hardware, VM disk options) are explained, never changed.
# Configuration (common rule): /etc/default/host-perf-audit.conf THEN ~/.host-perf-audit.cfg (the last one wins; keys CSV, DURATION, INTERVAL, LANGUAGE,
# NO_GUESTS, TOP, VERBOSE); -c/--config: that file ALONE; the command line takes priority.
#
# VERSION HISTORY (summary — see doc/host-perf-audit.changelog.txt for the full detail):
#   1.2.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.1.20261016.151148 — Number of logical cores read from /proc/stat (the one measured), not from the machine running the program.
#   1.0.20261016.114848 — First version: CPU, memory, disks, PSI, network, ZFS (pools, ARC, latency, datasets), guests; verdict, SSD question, --apply.
#
# Usage:
#   host-perf-audit.py                         one minute of measurement (sample every 5 s), then the report
#   host-perf-audit.py --duration 4h           four hours (sample every 60 s): the daily peaks are included
#   host-perf-audit.py --duration 30m --csv /root/perf.csv   samples also written to a CSV file (spreadsheet)
#   host-perf-audit.py --apply                 report, then the safe settings offered one by one
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

__version__ = "1.2.20261016.173838"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "doc", f"{SCRIPT_NAME}.changelog.txt")
PVE_DIR = os.environ.get("HOST_PERF_AUDIT_PVE_DIR", "/etc/pve")
SYSCTL_FILE = os.environ.get("HOST_PERF_AUDIT_SYSCTL_FILE", "/etc/sysctl.d/90-host-perf-audit.conf")
MODPROBE_FILE = os.environ.get("HOST_PERF_AUDIT_MODPROBE_FILE", "/etc/modprobe.d/zfs-arc-host-perf-audit.conf")
CMD_TIMEOUT = 20
VERBOSE = False

# Thresholds (documented in the report): above them the resource is « limiting ».
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
    print, input = I18N.print, I18N.input          # noqa: A001 — every displayed text goes through the translator
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
SCHEMA_CONFIG = {"CSV": ("csv", str), "DURATION": ("duration", str), "INTERVAL": ("interval", float), "NO_GUESTS": ("no_guests", bool), "TOP": ("top", int),
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
    # Average waits since import, in nanoseconds (-p): total_wait r/w, disk_wait r/w, syncq_wait r/w, asyncq_wait r/w…
    code, out = run(["zpool", "iostat", "-l", "-H", "-p"])
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) >= 15 and c[0] in pools:
            def ms(x):
                return int(x) / 1e6 if x.isdigit() else None
            pools[c[0]]["latency"] = {"total_r": ms(c[7]), "total_w": ms(c[8]), "disk_r": ms(c[9]), "disk_w": ms(c[10]), "syncq_w": ms(c[12]), "asyncq_w": ms(c[14])}
    datasets = {}
    code, out = run(["zfs", "get", "-H", "-p", "-o", "name,property,value", "-t", "filesystem,volume",
                     "compression,atime,relatime,recordsize,volblocksize,sync,primarycache,logbias,compressratio,used"])
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) == 3:
            datasets.setdefault(c[0], {})[c[1]] = c[2]
    return {"pools": pools, "datasets": datasets}


# ---------------------------------------------------------------------------------------------------------------- sampling
def sample_loop(duration, interval, guests, csv_path):
    """Samples every `interval` seconds during `duration` seconds (Ctrl-C: stop, keep what was taken). Returns the list of rates() results, each with
    "guests": {vmid: {cpu, mem, io_r, io_w, io_some}}."""
    samples, t_end = [], time.monotonic() + duration
    prev = SYSPERF.snapshot()
    prev_g = {vmid: cgroup_counters(path) for vmid, (_k, path) in guests.items()}
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
                prev_g[vmid] = c
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
        eprint(f"\nMeasurement interrupted (Ctrl-C) after {len(samples)} sample(s): report on what was measured.")
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
    out.append(f"PROCESSOR — {facts['cpu_model'] or '?'}, {facts['cores']} logical core(s), governor {facts['governor'] or '?'}")
    out.append(f"  busy: average {avg(busy) or 0:.0f} %, 95 % of the time under {pct(busy, 95) or 0:.0f} %, peak {max(busy or [0]):.0f} % · iowait {avg(iow) or 0:.1f} % · steal {avg(steal) or 0:.1f} %"
               f" · load {avg(load) or 0:.1f} (peak {max([x for x in load if x is not None] or [0]):.1f}) for {facts['cores']} core(s)")
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
        arc_line = f"  ZFS ARC: {size / 2 ** 30:.1f} GiB used, maximum {cmax / 2 ** 30:.1f} GiB ({100 * cmax / max(total * 1024, 1):.0f} % of the RAM) · hit ratio {avg(hits) or 0:.1f} % (95 % of the samples above {pct(hits, 5) or 0:.0f} %)"
        out.append(arc_line)
        throttle = sum(x.get("throttle", 0) for x in arcs)
        if throttle:
            out.append(f"  {tag('warn')} ARC memory throttle: {throttle} time(s) — the ARC had to give memory back under pressure")
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
    out.append("DISKS — % of the time busy (utilization), operations and throughput per second, wait per operation (ms)")
    h = [T(x) for x in ("disk", "type", "util avg", "p95", "max", "read/s", "write/s", "MB/s r", "MB/s w", "wait r", "wait w", "model")]
    out.append(f"  {h[0]:<10} {h[1]:<5} {h[2]:>8} {h[3]:>5} {h[4]:>5}  {h[5]:>7} {h[6]:>7}  {h[7]:>6} {h[8]:>6}  {h[9]:>7} {h[10]:>7}  {h[11]}")
    worst = []
    for dev in devices:
        vals = [s["disks"][dev] for s in samples if dev in s["disks"]]
        util = [v["util"] for v in vals]
        rw = [v["r_await"] for v in vals if v["r_await"] is not None and v["r_s"] >= 0.5]
        ww = [v["w_await"] for v in vals if v["w_await"] is not None and v["w_s"] >= 0.5]
        info = facts["disks"].get(dev, {"kind": "zvol" if dev.startswith("zd") else "?", "model": "", "scheduler": ""})
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


def analyze_zfs(zfs, facts, worst, io_avg, fd, out):
    if not zfs:
        return
    out.append("ZFS")
    for name, p in zfs["pools"].items():
        kinds = sorted({facts["disks"].get(d, {}).get("kind", "?") for d in facts["disks"]})
        extra = [x for x in ("special", "log", "cache") if p[x]]
        out.append(f"  pool {name} — {p['size'] / 1e12:.2f} TB, used {p['cap']} %, fragmentation {p['frag']} %, {p['health']}, ashift {p['ashift'] or '?'}, vdevs "
                   f"{', '.join(sorted(set(p['vdevs']))) or 'single disk(s)'}" + (f", devices: {', '.join(extra)}" if extra else ", no special / log / cache device"))
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
    tuned = 0
    for name, props in sorted(zfs["datasets"].items()):
        if props.get("compression") in ("off",) and tuned < 6:
            tuned += 1
            fd.suggest(2, f"dataset {name}: compression off — lz4 (or zstd) is almost free in processor and reduces the disk reads and writes (new data only)",
                       lambda n=name: run_set(["zfs", "set", "compression=lz4", n]), f"zfs set compression=lz4 {name}")
        if props.get("atime") == "on" and props.get("relatime") != "on" and tuned < 6:
            tuned += 1
            fd.suggest(2, f"dataset {name}: atime=on without relatime — every read writes the access time; atime=off removes these writes",
                       lambda n=name: run_set(["zfs", "set", "atime=off", n]), f"zfs set atime=off {name}")
        if props.get("sync") == "disabled":
            fd.suggest(1, f"dataset {name}: sync=disabled — fast but an outage can lose the last seconds of committed transactions (PostgreSQL!): « standard » unless deliberate")
    hdd_pool = any(facts["disks"][d]["kind"] == "HDD" for d in facts["disks"])
    if hdd_pool and not any(p["special"] for p in zfs["pools"].values()) and (io_avg or 0) >= IO_PSI_WARN:
        fd.suggest(2, "HDD pool without « special » device: two small mirrored SSD as special vdev hold the metadata and the small blocks (zfs set special_small_blocks=16K): "
                      "most of the random reads of PostgreSQL then hit SSD — an intermediate step before replacing all the disks")
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
        io = [(v["io_r"] or 0) + (v["io_w"] or 0) for v in vals]
        some = [v["io_some"] for v in vals]
        mem = vals[-1]["mem"] or 0
        kind, name, _conf = names.get(vmid, ("?", "", ""))
        rows.append((avg(io) or 0, vmid, kind, name, avg(cpu) or 0, max([x for x in cpu if x is not None] or [0]), mem, vals[-1]["mem_max"], avg(some), max([x for x in some if x is not None] or [0])))
    out.append(f"GUESTS — the {min(top, len(rows))} busiest on the disks (cgroup of each running container / VM)")
    h = [T(x) for x in ("id", "type", "name", "CPU avg", "peak", "memory", "disk MB/s", "disk wait")]
    out.append(f"  {h[0]:>5} {h[1]:<4} {h[2]:<22} {h[3]:>8} {h[4]:>6}  {h[5]:>10}  {h[6]:>9}  {h[7]:>9} {h[4]:>6}")
    for io, vmid, kind, name, cpu, cpu_max, mem, mem_max, some, some_max in sorted(rows, reverse=True)[:top]:
        out.append(f"  {vmid:>5} {kind:<4} {name[:22]:<22} {cpu:>7.0f}% {cpu_max:>5.0f}%  {mem / 2 ** 30:>6.1f} GiB  {io / 1048576:>9.2f}  "
                   + (f"{some:>8.1f}% {some_max:>5.0f}%" if some is not None else f"{'-':>9} {'-':>6}"))
    out.append("  (CPU: 100 % = one full core; disk wait: % of the time the guest's tasks waited for the disk — the latency felt INSIDE it)")
    return rows


def guest_config_advice(names, fd):
    """Advice from the VM / container configurations of /etc/pve (never changed by the program: a VM restart is needed)."""
    for vmid, (kind, name, conf) in sorted(names.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        if kind != "vm":
            continue
        for m in re.finditer(r"^(scsi|virtio|sata|ide)\d+:\s*(.+)$", conf, re.M):
            bus, opts = m.group(1), m.group(2)
            if "media=cdrom" in opts:
                continue
            if bus in ("sata", "ide"):
                fd.suggest(2, f"VM {vmid} ({name}): disk on the {bus.upper()} bus (emulated, slow) — VirtIO SCSI single with iothread=1 (driver needed in the guest)")
            if bus == "scsi" and "iothread=1" not in opts:
                fd.suggest(3, f"VM {vmid} ({name}): SCSI disk without iothread=1 (with the « VirtIO SCSI single » controller, each disk gets its own I/O thread)")
            cache = re.search(r"cache=(\w+)", opts)
            if cache and cache.group(1) in ("writeback", "unsafe"):
                fd.suggest(3, f"VM {vmid} ({name}): disk cache « {cache.group(1)} » on ZFS — double cache with the ARC; « none » is the usual choice")
        if re.search(r"^cpu:\s*kvm64", conf, re.M):
            fd.suggest(3, f"VM {vmid} ({name}): CPU type kvm64 hides the instructions of the real processor — « host » (or x86-64-v2-AES) is faster when migration is not needed")


def ssd_answer(fd, worst, io_avg, io_full, facts, guests_rows, out):
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
    if busiest and busiest[0][8]:
        out.append(f"  Guest that waited most for the disk: {busiest[0][1]} {busiest[0][3]} ({busiest[0][8]:.1f} % of its time).")


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
def report(samples, facts, zfs, smart, names, guests_rows_cb, args, cost):
    fd, out = Findings(), []
    if not samples:
        print("No sample taken: nothing to analyze (interrupted too early).")
        return fd
    dur = samples[-1]["wall"] - samples[0]["wall"] + samples[0]["dt"]
    first = datetime.datetime.fromtimestamp(samples[0]["wall"] - samples[0]["dt"])
    print()
    print(f"PERFORMANCE OF {facts['host']} — {facts['pve'] or 'Linux ' + facts['kernel']} — {len(samples)} sample(s) from {first:%Y-%m-%d %H:%M} over {human_duration(dur)}")
    print(f"  (waiting times from {samples[-1].get('psi_source', '/proc/pressure')}; this program used {cost:.2f} s of processor in all)")
    print()
    analyze_cpu(samples, facts, fd, out)
    out.append("")
    analyze_memory(samples, facts, zfs, fd, out)
    out.append("")
    worst, io_avg, io_full = analyze_disks(samples, facts, smart, fd, out)
    out.append("")
    analyze_zfs(zfs, facts, worst, io_avg, fd, out)
    if zfs:
        out.append("")
    analyze_network(samples, out)
    out.append("")
    rows = guests_rows_cb(samples, out) if not args.no_guests else []
    if rows:
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
    ssd_answer(fd, worst, io_avg, io_full, facts, rows, tail)
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
def show_changelog():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        text = open(CHANGELOG_FILE, encoding="utf-8").read()
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


def main():
    global VERBOSE
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="What limits the performance of a Proxmox host (or any Linux server): processor, memory, disks, network, ZFS, guests — measured "
                    "over a chosen duration, with a verdict, the answer to « are SSD disks justified? » and the settings to change.")
    parser.add_argument("--apply", action="store_true", help="After the report, apply the SAFE settings one by one with confirmation (ZFS compression / atime of a dataset, ARC maximum, vm.swappiness); --yes: without questions")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/host-perf-audit.conf, then the personal file .host-perf-audit.cfg; UPPERCASE options: CSV, DURATION, INTERVAL, LANGUAGE, NO_GUESTS, TOP, VERBOSE)")
    parser.add_argument("--csv", default=None, metavar="FILE", help="Also write every sample to this CSV file (one line per interval: CPU, waits, memory, ARC, each disk)")
    parser.add_argument("--duration", default="60", metavar="TIME", help="Length of the measurement: 90 (seconds), 10m, 4h, 1h30m… (default: 60 seconds)")
    parser.add_argument("--interval", type=float, default=None, metavar="SECONDS",
                        help="Seconds between two samples (default: 5 up to 2 minutes of measurement, 15 up to 30 minutes, 60 beyond)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["en"], metavar="LANG", help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--no-guests", action="store_true", help="Do not measure each container / VM (cgroups)")
    parser.add_argument("--report-err", action="store_true", help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--top", type=int, default=8, metavar="N", help="Number of guests shown, the busiest on the disks first (default: 8)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each command run")
    parser.add_argument("--version", action="version", version=f"host-perf-audit.py version {__version__}")
    parser.add_argument("--yes", action="store_true", help="With --apply: without questions")
    if "--version" not in sys.argv[1:]:
        print(f"host-perf-audit.py v{__version__}")
    defaults, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defaults, problems)
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
    print(f"Measuring for {human_duration(duration)}, one sample every {interval:g} s ({len(facts['disks'])} disk(s), {len(guests)} running guest(s)"
          + (f", ZFS pool(s): {', '.join(zfs['pools'])}" if zfs else "") + ") — Ctrl-C stops early and still gives the report.")
    samples = sample_loop(duration, interval, guests, args.csv)
    t1 = os.times()
    cost = (t1.user + t1.system + t1.children_user + t1.children_system) - (t0.user + t0.system + t0.children_user + t0.children_system)
    fd = report(samples, facts, zfs, smart, names, lambda s, out: analyze_guests(s, names, args.top, out), args, cost)
    if args.csv and samples:
        print(f"\nSamples written to {args.csv}.")
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
