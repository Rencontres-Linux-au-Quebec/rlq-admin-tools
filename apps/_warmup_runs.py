# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Runs of odoo-warmup.py: when each warm-up started and ended, so that app-log-live.py can say which local requests are the warm-up.

The Odoo log (werkzeug) has no User-Agent: a request of the warm-up is only « 127.0.0.1 GET /web/login ». odoo-warmup.py writes one line
per run « START END PID » (seconds since the epoch; END = 0 while it runs) in the first writable file of RUNS_FILES; app-log-live.py reads
every one of them. The last RUNS_KEEP runs are kept. No message here is shown to a user."""
import os
import time

__version__ = "1.0.20261118.205214"

RUNS_KEEP = 20
MARGIN = 2.0                      # seconds around a run: a request logged just before the start or just after the end


def runs_files():
    """Candidate files, first one first: ODOO_WARMUP_RUNS (tests), /var/lib/odoo-warmup/runs (root), ~/.cache/odoo-warmup/runs."""
    files = [os.environ.get("ODOO_WARMUP_RUNS", ""), "/var/lib/odoo-warmup/runs", os.path.expanduser("~/.cache/odoo-warmup/runs")]
    return [f for f in files if f]


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    runs = []
    for line in lines:
        parts = line.split()
        try:
            runs.append((float(parts[0]), float(parts[1]), int(parts[2])))
        except (IndexError, ValueError):
            continue
    return runs


def _write(path, runs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        f.writelines(f"{s:.2f} {e:.2f} {p}\n" for s, e, p in runs[-RUNS_KEEP:])
    os.replace(temporary, path)


def record_start(now=None):
    """A run starts: returns (file, start) for record_end, or None when no file can be written (never an error for the warm-up)."""
    start = time.time() if now is None else now
    for path in runs_files():
        try:
            _write(path, _read(path) + [(start, 0.0, os.getpid())])
            return path, start
        except OSError:
            continue
    return None


def record_end(token, now=None):
    """The run of `token` (record_start) ends: its END is written."""
    if not token:
        return
    path, start = token
    end = time.time() if now is None else now
    try:
        _write(path, [(s, end if (abs(s - start) < 0.01 and e == 0 and p == os.getpid()) else e, p) for s, e, p in _read(path)])
    except OSError:
        pass


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def runs(now=None):
    """[(start, end)] of every file, sorted. A run without END: end = now when its process is alive; dropped otherwise (killed)."""
    now = time.time() if now is None else now
    found = []
    for path in runs_files():
        for s, e, p in _read(path):
            if e == 0:
                if not _alive(p):
                    continue
                e = now
            found.append((s - MARGIN, e + MARGIN))
    return sorted(set(found))


class Runs:
    """Cached reader for a log stream: the files are read again at most every `every` seconds."""
    def __init__(self, every=2.0):
        self.every, self.read_at, self.cache = every, 0.0, []

    def windows(self, now=None):
        now = time.time() if now is None else now
        if now - self.read_at >= self.every:
            self.cache, self.read_at = runs(now), now
        return self.cache

    def during(self, instant, now=None):
        """The (start, end) window of the run during which `instant` falls, or None."""
        if instant is None:
            return None
        for window in self.windows(now):
            if window[0] <= instant <= window[1]:
                return window
        return None
