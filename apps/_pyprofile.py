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
"""p = find_pyspy() or install_pyspy(run); code, err = record(p, pid, seconds, raw_path, run_live); s = summarize(raw_path)"""
import os
import re
import shutil
import subprocess
from collections import Counter

__version__ = "1.0.20261118.143832"

# py-spy « raw » (collapsed stacks): « frame;frame;...;frame COUNT », frame = « function (file.py:line) »; with --subprocesses the first frame
# can be « process PID:"command" »
RAW_RE = re.compile(r"^(.*) (\d+)$")
FRAME_RE = re.compile(r"^(.*?) \((.*?)(?::(\d+))?\)$")
PYSPY_PATHS = ("py-spy", "/usr/bin/py-spy", "/usr/local/bin/py-spy", "/root/.local/bin/py-spy")
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


def parse_frame(frame):
    """(function, file, line) of a frame of py-spy."""
    m = FRAME_RE.match(frame.strip())
    if not m:
        return frame.strip(), "", ""
    return m.group(1), m.group(2), m.group(3) or ""


def short_file(path):
    """The end of a path that names the module: …/odoo/http.py, …/addons/website/models/ir_http.py."""
    for marker in ("/odoo/addons/", "/addons/", "/odoo/", "/site-packages/", "/lib/python"):
        i = path.rfind(marker)
        if i >= 0:
            return path[i + 1:]
    return os.path.basename(path)


def summarize(raw_path, top=12, common=0.9):
    """{"samples", "processes", "leaf": [(share, function, file)], "held": [(share, function, file)]} of a collapsed file of py-spy.
    leaf: where the processor time is spent (last frame of each sample); held: functions present in the stacks (inclusive time), the frames
    present in at least `common` of the samples left out (the loop of the server, the start of the request: always there, they say nothing)."""
    samples, leaf, held, processes = 0, Counter(), Counter(), set()
    try:
        with open(raw_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = RAW_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                stack, n = m.group(1), int(m.group(2))
                frames = [x for x in stack.split(";") if x]
                if frames and frames[0].startswith("process "):
                    processes.add(frames[0].split(":", 1)[0])
                    frames = frames[1:]
                frames = [x for x in frames if not x.startswith("thread ")]
                if not frames:
                    continue
                samples += n
                fn, path, _ln = parse_frame(frames[-1])
                leaf[(fn, short_file(path))] += n
                for key in {(parse_frame(x)[0], short_file(parse_frame(x)[1])) for x in frames}:
                    held[key] += n
    except OSError:
        return {"samples": 0, "processes": 0, "leaf": [], "held": []}
    if not samples:
        return {"samples": 0, "processes": len(processes), "leaf": [], "held": []}
    held_list = [(v / samples, fn, path) for (fn, path), v in held.items() if v / samples < common]
    return {"samples": samples, "processes": len(processes),
            "leaf": [(v / samples, fn, path) for (fn, path), v in leaf.most_common(top)],
            "held": sorted(held_list, reverse=True)[:top]}
