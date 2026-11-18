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
# _pyprofile.py - WHERE the Python time of an application goes (shared module, apps/), for app-log-live.py --profile: py-spy samples the
# main process of the service AND its children (the prefork workers of Odoo) without stopping them (--nonblocking), for a while, then the
# samples are summed per function: where the processor time is spent (last frame) and which functions of the application hold the time
# (every frame, the frames common to almost all the samples left out: the loop of the server). py-spy is installed when missing.
# 1.1: every profile of every program in ONE place, /var/lib/python-profile/profile-HOST-PROGRAM-YYYYMMDD-HHMMSS.txt (summary) and .raw.txt
# (samples of py-spy), like the other programs of the repository (/var/lib/PROGRAM, name of the server in the file name); the summary leaves
# out the frames of the server and of the frameworks, sums the time per module of the application and names the known causes.
"""raw, text = profile_paths("odoo-warmup"); cmd = record_command(pyspy, pid, s, raw); s = summarize(raw); lines = report_lines(s, tr); save(lines, text)"""
import glob
import os
import re
import shutil
import subprocess
import time
from collections import Counter

__version__ = "1.1.20261118.172706"

# py-spy « raw » (collapsed stacks): « frame;frame;...;frame COUNT », frame = « function (file.py:line) »; with --subprocesses the first frame
# can be « process PID:"command" »
RAW_RE = re.compile(r"^(.*) (\d+)$")
FRAME_RE = re.compile(r"^(.*?) \((.*?)(?::(\d+))?\)$")
PYSPY_PATHS = ("py-spy", "/usr/bin/py-spy", "/usr/local/bin/py-spy", "/root/.local/bin/py-spy")
PROFILE_DIRS = (os.environ.get("PYPROFILE_DIR"), "/var/lib/python-profile", os.path.join(os.path.expanduser("~"), ".cache", "python-profile"))
PROFILE_KEEP = 20                                       # profiles kept per program (summary and samples)
# Frames that say nothing about the application: loop of the prefork server, sockets, WSGI, dispatch of Odoo, decorators, caches
INFRA_FILES = ("threading.py", "socketserver.py", "http/server.py", "werkzeug/serving.py", "odoo/service/server.py", "odoo/service/model.py",
               "odoo/http.py", "odoo/tools/facade.py", "decorator.py", "odoo/tools/profiler.py", "odoo/tools/cache.py", "odoo/tools/func.py",
               "odoo-bin", "odoo/cli/", "gevent/hub.py", "selectors.py")
IDLE_FUNCTIONS = ("PreforkServer.sleep", "Worker.sleep", "Hub.run", "select", "poll", "accept")
# Known causes: (function of the stack, minimum share, text). The share is that of the active samples holding the function.
CAUSES = (("IrQWeb._compile", 0.15, "QWeb templates compiled: the first time a page is shown in EACH worker, Odoo compiles its templates (a cache per process): a warm-up of every worker (odoo-warmup.py) or fewer restarts and replaced workers"),
          ("Cursor.execute", 0.25, "waiting for PostgreSQL: SQL queries (host-perf-audit.py --io-latency shows the queries and the tables read from the disk)"),
          ("Application.statics", 0.05, "list of the static folders of every module: first static file of a worker (odoo-warmup.py asks them to every worker)"),
          ("_get_contextual_pricelist", 0.05, "prices of the event tickets (website_sale pricelists) computed for each page"),
          ("Users._has_group", 0.10, "rights of the user checked again and again in the templates (has_group)"))
APT_ENV = dict(os.environ, DEBIAN_FRONTEND="noninteractive", NEEDRESTART_MODE="a")


def find_pyspy(which=shutil.which):
    for name in PYSPY_PATHS:
        path = which(name) if not name.startswith("/") else (name if os.path.isfile(name) and os.access(name, os.X_OK) else None)
        if path:
            return path
    return None


def default_run(cmd, timeout=1800):
    """(exit code, output) of a command; its output is also shown as it goes (installation)."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, universal_newlines=True,
                           errors="replace", timeout=timeout, env=APT_ENV)
        return p.returncode, p.stdout or ""
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def install_pyspy(run=default_run, which=shutil.which, say=print):
    """Installs py-spy: the Debian package when apt knows it, else pip (python3-pip installed first). Returns its path, or None."""
    if os.geteuid() != 0:
        say("py-spy missing and not installed (root required).")
        return None
    if which("apt-get"):
        code, _out = run(["apt-cache", "show", "py-spy"], 60)
        if code == 0:
            say("Installing py-spy (apt-get install py-spy)...")
            if run(["apt-get", "install", "-y", "--no-install-recommends", "py-spy"])[0] == 0 and find_pyspy(which):
                return find_pyspy(which)
        if not which("pip3") and run(["python3", "-m", "pip", "--version"], 60)[0] != 0:
            say("Installing pip (apt-get install python3-pip)...")
            run(["apt-get", "install", "-y", "--no-install-recommends", "python3-pip"])
    say("Installing py-spy (pip install py-spy)...")
    code, out = run(["python3", "-m", "pip", "install", "--break-system-packages", "py-spy"])
    if code != 0:
        code, out = run(["python3", "-m", "pip", "install", "py-spy"])
    path = find_pyspy(which)
    if not path:
        say(f"py-spy could not be installed: {out.strip().splitlines()[-1] if out.strip() else code}")
    return path


def record_command(pyspy, pid, seconds, raw_path, rate=50):
    """py-spy record of the process PID and of its children, without stopping them, in collapsed stacks (« raw »)."""
    return [pyspy, "record", "--pid", str(pid), "--subprocesses", "--nonblocking", "--rate", str(rate), "--duration", str(int(seconds)),
            "--format", "raw", "--output", raw_path]


def profile_paths(program, host=None, when=None):
    """(samples, summary) paths of a new profile of `program`: the first writable folder of PROFILE_DIRS (created if needed)."""
    host = host or os.uname().nodename.split(".")[0]
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    for folder in PROFILE_DIRS:
        if not folder:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            continue
        if os.access(folder, os.W_OK):
            base = os.path.join(folder, f"profile-{host}-{program}-{stamp}")
            return base + ".raw.txt", base + ".txt"
    base = os.path.join("/tmp", f"profile-{host}-{program}-{stamp}")
    return base + ".raw.txt", base + ".txt"


def save(lines, text_path, program, keep=PROFILE_KEEP):
    """Writes the summary; keeps the `keep` latest profiles of `program` in its folder (summaries and samples). Returns True when written."""
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        return False
    folder = os.path.dirname(text_path)
    for suffix in (".raw.txt", ".txt"):
        olds = sorted(x for x in glob.glob(os.path.join(folder, f"profile-*-{program}-*{suffix}")) if suffix == ".raw.txt" or not x.endswith(".raw.txt"))
        for old in olds[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass
    return True


def parse_frame(frame):
    """(function, file, line) of a frame of py-spy."""
    m = FRAME_RE.match(frame.strip())
    if not m:
        return frame.strip(), "", ""
    return m.group(1), m.group(2), m.group(3) or ""


def short_file(path):
    """The end of a path that names the module: …/odoo/http.py, …/addons/website/models/ir_http.py."""
    if not path.startswith("/"):                          # py-spy already gives the path from the package (werkzeug/serving.py)
        return path
    for marker in ("/odoo/addons/", "/addons/", "/odoo/", "/site-packages/", "/lib/python"):
        i = path.rfind(marker)
        if i >= 0:
            return path[i + 1:]
    return os.path.basename(path)


def is_infra(path):
    return any(marker in path for marker in INFRA_FILES) or path.startswith("<frozen")


def module_of(fn, path):
    """Module of the application a frame belongs to: addon of Odoo (website, base...), the ORM, compiled QWeb templates, or a Python library."""
    if path.startswith("<") and path[1:-1].isdigit():
        return "QWeb templates (rendering)"
    if path.startswith("odoo/addons/"):
        return path.split("/")[2]
    if path.startswith("addons/"):
        return path.split("/")[1]
    if path in ("odoo/models.py", "odoo/fields.py", "odoo/api.py"):
        return "odoo (ORM)"
    if path.startswith("odoo/"):
        return "odoo (" + path.split("/")[-1] + ")"
    parts = path.split("/")
    return parts[0] if len(parts) > 1 and "." not in parts[0] else (parts[-1].rsplit(".", 1)[0] or "?")


def summarize(raw_path, top=12, common=0.9):
    """Summary of a collapsed file of py-spy (samples of the busy threads only: py-spy leaves out the idle ones):
    {"samples", "idle", "processes", "leaf": [(share, function, file)], "held": [(share, function, file)], "modules": [(share, module)],
     "causes": [(share, text)]}. leaf: last frame of each sample (where the processor time goes); held: the functions of the application in the
    stacks (inclusive time; frames of the server and of the frameworks, and frames present in `common` of the samples, left out); modules:
    inclusive time per module of the application; causes: known causes over their threshold. Shares are of the busy samples."""
    samples, idle, leaf, held, modules, processes = 0, 0, Counter(), Counter(), Counter(), set()
    empty = {"samples": 0, "idle": 0, "processes": 0, "leaf": [], "held": [], "modules": [], "causes": []}
    try:
        with open(raw_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = RAW_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                stack, n = m.group(1), int(m.group(2))
                frames = [x for x in stack.split(";") if x]
                owner = None
                while frames and frames[0].startswith("process "):        # --subprocesses: run.sh;odoo_bin.sh;odoo-bin;worker: the last is the owner
                    owner = frames.pop(0).split(":", 1)[0]
                if owner:
                    processes.add(owner)
                frames = [x for x in frames if not x.startswith("thread ")]
                if not frames:
                    continue
                parsed = [(fn, short_file(path)) for fn, path, _ln in map(parse_frame, frames)]
                if any(fn.endswith(name) for fn, _p in parsed[-1:] for name in IDLE_FUNCTIONS):
                    idle += n
                    continue
                samples += n
                leaf[parsed[-1]] += n
                for key in set(parsed):
                    held[key] += n
                for name in {module_of(fn, path) for fn, path in parsed if not is_infra(path)}:
                    modules[name] += n
    except OSError:
        return empty
    if not samples:
        return dict(empty, idle=idle, processes=len(processes))
    held_list = [(v / samples, fn, path) for (fn, path), v in held.items() if v / samples < common and not is_infra(path)]
    causes = []
    for function, threshold, text in CAUSES:
        share = max((v for (fn, _p), v in held.items() if fn.endswith(function)), default=0) / samples
        if share >= threshold:
            causes.append((share, text))
    return {"samples": samples, "idle": idle, "processes": len(processes),
            "leaf": [(v / samples, fn, path) for (fn, path), v in leaf.most_common(top)],
            "held": sorted(held_list, reverse=True)[:top],
            "modules": [(v / samples, name) for name, v in modules.most_common(8)],
            "causes": sorted(causes, reverse=True)}


def report_lines(summary, tr=lambda t: t):
    """Text of the summary, translated by `tr` (catalogue lang/_pyprofile.LANG.po)."""
    lines = [tr("Python profile: {samples} busy samples in {processes} processes ({idle} idle samples left out); each sample is 1/50 s of a busy worker").format(
        samples=summary["samples"], processes=summary["processes"] or 1, idle=summary.get("idle", 0))]
    if summary["samples"] < 100:
        lines.append(tr("  Few samples: Odoo was almost idle during the profile; profile while the site is slow, or longer"))
    if summary.get("causes"):
        lines.append(tr("  What takes the time:"))
        lines += [f"    {share * 100:5.1f} %  " + tr(text) for share, text in summary["causes"]]
    if summary.get("modules"):
        lines.append(tr("  Time per module of the application (with what it calls):"))
        lines += [f"    {share * 100:5.1f} %  {tr(name) if name.startswith(('QWeb', 'odoo (')) else name}" for share, name in summary["modules"]]
    lines.append(tr("  Where the processor time goes (last function of each sample):"))
    lines += [f"    {share * 100:5.1f} %  {fn}  ({path})" for share, fn, path in summary["leaf"]]
    lines.append(tr("  Functions of the application that hold the time (with what they call):"))
    lines += [f"    {share * 100:5.1f} %  {fn}  ({path})" for share, fn, path in summary["held"]]
    return lines
