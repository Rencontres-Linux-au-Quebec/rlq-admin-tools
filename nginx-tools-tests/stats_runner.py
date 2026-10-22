#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Test runner of run-all.sh with statistics (run-all.sh 1.188).

  stats_runner.py --run STATS.json MODULE…   like « python3 -m unittest -v MODULE… » (same output, read by run-all.sh), and writes for each
                                             test: module, program, kind, duration, result; plus the resources of the pass (CPU, memory, I/O)
  stats_runner.py [--total SECONDS] --report STATS.json…
                                             the statistics table (one file per awk pass), in the display language (NGINX_TOOLS_I18N_LANGUE)

Kind of a test, measured while it runs (never declared by hand):
  unit         calls functions of the programs in this process, launches nothing;
  functional   launches a program (subprocess) and checks its output, files and exit code;
  interactive  drives a program in a real pseudo-terminal (pty: questions, Ctrl-C, keys);
  conformity   static checks of files (conventions, nginx configuration…): module with NATURE_TESTS = "conformité".
"""
import json
import os
import pty
import resource
import subprocess
import sys
import time
import unicodedata
import unittest

__version__ = "1.0.20261020.112434"
HERE = os.path.dirname(os.path.abspath(__file__))
PROG_DIR = os.environ.get("TEST_SCRIPTS_DIR") or os.path.dirname(HERE)
KINDS = ("unit", "functional", "interactive", "conformity")
TEXTS = {
    "fr": {"title": "Statistiques des tests", "duration": "Durée", "whole": "Durée totale de run-all.sh", "of_tests": "dont tests", "passes": "passe(s) awk", "cpu": "CPU", "user": "utilisateur", "system": "système",
           "memory": "Mémoire max. d'un processus", "io": "Disque", "read": "lu", "written": "écrit", "processes": "Programmes lancés",
           "tests": "tests", "program": "Programme", "unit": "unitaires", "functional": "fonctionnels", "interactive": "interactifs", "conformity": "conformité",
           "skipped": "désactivés", "failed": "échecs", "total": "TOTAL", "slowest": "Les plus lents", "kinds": "Nature",
           "legend": "unitaires = fonctions appelées sans lancer de programme · fonctionnels = programme lancé, sortie vérifiée · "
                     "interactifs = vrai pseudo-terminal (questions, Ctrl-C) · conformité = fichiers vérifiés sans exécution",
           "transversal": "(transversal)", "none": "aucune statistique (passe interrompue ?)"},
    "en": {"title": "Test statistics", "duration": "Duration", "whole": "Total duration of run-all.sh", "of_tests": "of which tests", "passes": "awk pass(es)", "cpu": "CPU", "user": "user", "system": "system",
           "memory": "Max. memory of one process", "io": "Disk", "read": "read", "written": "written", "processes": "Programs launched",
           "tests": "tests", "program": "Program", "unit": "unit", "functional": "functional", "interactive": "interactive", "conformity": "conformity",
           "skipped": "skipped", "failed": "failed", "total": "TOTAL", "slowest": "Slowest", "kinds": "Kind",
           "legend": "unit = functions called without launching a program · functional = program launched, output checked · "
                     "interactive = real pseudo-terminal (questions, Ctrl-C) · conformity = files checked without running anything",
           "transversal": "(cross-cutting)", "none": "no statistics (interrupted pass?)"},
}


def width(text):
    """Columns taken on a terminal: accents count 1, a wide East Asian character 2, a combining mark 0."""
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def pad(text, n, right=False):
    """`text` padded to `n` COLUMNS (not characters: « Durée » and « Duration » line up the same way)."""
    space = " " * max(0, n - width(text))
    return space + text if right else text + space


def program_of(module):
    """Program tested by a module: PROGRAMME = "…" in the module, otherwise derived from its name (test_app_log_live -> app-log-live.py,
    test_cache_ip -> apps/_cache_ip.py), otherwise cross-cutting."""
    name = module[5:] if module.startswith("test_") else module
    for candidate in (name.replace("_", "-") + ".py", name.replace("_", "-") + ".sh", os.path.join("apps", "_" + name + ".py"), os.path.join("apps", "_" + name + ".sh")):
        if os.path.isfile(os.path.join(PROG_DIR, candidate)):
            return candidate
    return None


class Probe:
    """Counts, during ONE test, the programs it launches (subprocess) and the pseudo-terminals it opens (pty.fork, os.forkpty)."""
    def __init__(self):
        self.spawned = self.ptys = self.total = 0
        original_init, original_fork, original_forkpty = subprocess.Popen.__init__, pty.fork, os.forkpty
        probe = self

        def popen_init(self_, *a, **k):
            probe.spawned += 1
            probe.total += 1
            return original_init(self_, *a, **k)

        def fork():
            probe.ptys += 1
            probe.total += 1
            return original_fork()

        def forkpty():
            probe.ptys += 1
            probe.total += 1
            return original_forkpty()
        self._originals = (original_init, original_fork, original_forkpty)
        subprocess.Popen.__init__, pty.fork, os.forkpty = popen_init, fork, forkpty

    def uninstall(self):
        subprocess.Popen.__init__, pty.fork, os.forkpty = self._originals

    def reset(self):
        self.spawned = self.ptys = 0


class StatsResult(unittest.TextTestResult):
    probe = None
    records = []

    def startTest(self, test):
        self._t0 = time.monotonic()
        self.probe.reset()
        self._outcome = "ok"
        super().startTest(test)

    def _set(self, outcome):
        self._outcome = outcome

    def addFailure(self, test, err):
        self._set("failed")
        super().addFailure(test, err)

    def addError(self, test, err):
        self._set("failed")
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._set("skipped")
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:                                       # a failed subTest() makes its test failed (unittest counts it on its own)
            self._set("failed")
        super().addSubTest(test, subtest, err)

    def addExpectedFailure(self, test, err):
        self._set("ok")
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._set("failed")
        super().addUnexpectedSuccess(test)

    def stopTest(self, test):
        super().stopTest(test)
        module = type(test).__module__
        nature = getattr(sys.modules.get(module), "NATURE_TESTS", "")
        if self.probe.ptys:
            kind = "interactive"
        elif self.probe.spawned:
            kind = "functional"
        elif nature == "conformité":
            kind = "conformity"
        else:
            kind = "unit"
        explicit = getattr(sys.modules.get(module), "PROGRAMME", None)
        self.records.append({"id": test.id(), "module": module, "program": explicit or program_of(module), "kind": kind,
                             "seconds": round(time.monotonic() - self._t0, 3), "result": self._outcome})


def run(stats_path, modules):
    probe = Probe()
    StatsResult.probe = probe
    t0, io0 = time.monotonic(), _io()
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2, resultclass=StatsResult).run(suite)
    self_ru, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    io1 = _io()
    data = {"version": __version__, "awk": os.path.basename(os.environ.get("TEST_AWK", "awk")), "seconds": round(time.monotonic() - t0, 2),
            "cpu_user": round(self_ru.ru_utime + children.ru_utime, 2), "cpu_system": round(self_ru.ru_stime + children.ru_stime, 2),
            "max_rss_kb": max(self_ru.ru_maxrss, children.ru_maxrss), "processes": probe.total,
            "read_bytes": io1[0] - io0[0], "write_bytes": io1[1] - io0[1], "tests": StatsResult.records}
    try:
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"stats_runner.py: {e}", file=sys.stderr)
    return 0 if result.wasSuccessful() else 1


def _io():
    """(bytes read, bytes written) on disk by this process and its finished children (/proc/self/io; children: rusage blocks × 512)."""
    try:
        with open("/proc/self/io", encoding="ascii") as f:
            values = dict(line.split(": ") for line in f.read().splitlines())
        own = (int(values.get("read_bytes", 0)), int(values.get("write_bytes", 0)))
    except (OSError, ValueError):
        own = (0, 0)
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own[0] + ru.ru_inblock * 512, own[1] + ru.ru_oublock * 512


def size(n):
    for unit in ("o", "Kio", "Mio", "Gio"):
        if n < 1024 or unit == "Gio":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def duration(s):
    m, s = divmod(int(round(s)), 60)
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min {s:02d} s" if h else f"{m} min {s:02d} s" if m else f"{s} s"


def report(paths, lang=None, color=None, whole=None):
    lang = lang or ("en" if os.environ.get("NGINX_TOOLS_I18N_LANGUE", "fr").startswith("en") else "fr")
    t = TEXTS[lang]
    color = sys.stdout.isatty() if color is None else color
    bold = (lambda s: f"\x1b[1m{s}\x1b[0m") if color else (lambda s: s)
    cyan = (lambda s: f"\x1b[36m{s}\x1b[0m") if color else (lambda s: s)
    passes = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                passes.append(json.load(f))
        except (OSError, ValueError):
            continue
    print()
    print(cyan(f"=== {t['title']} ==="))
    if not passes:
        print("  " + t["none"])
        return 0
    total_s = sum(p["seconds"] for p in passes)
    rows = ([(t["whole"], duration(whole))] if whole else []) + [
            (t["of_tests"] if whole else t["duration"], f"{duration(total_s)} — {len(passes)} {t['passes']} (" + ", ".join(f"{p['awk']} {duration(p['seconds'])}" for p in passes) + ")"),
            (t["cpu"], f"{sum(p['cpu_user'] for p in passes):.1f} s {t['user']}, {sum(p['cpu_system'] for p in passes):.1f} s {t['system']}"),
            (t["memory"], size(max(p["max_rss_kb"] for p in passes) * 1024)),
            (t["io"], f"{size(sum(p['read_bytes'] for p in passes))} {t['read']}, {size(sum(p['write_bytes'] for p in passes))} {t['written']}"),
            (t["processes"], str(sum(p["processes"] for p in passes)))]
    label_w = max(width(r[0]) for r in rows)
    for label, value in rows:
        print(f"  {pad(label, label_w)} : {value}")
    first = passes[0]["tests"]                                   # the table: first pass (the others run the same tests with another awk)
    per = {}
    for r in first:
        key = r["program"] or t["transversal"]
        row = per.setdefault(key, {"tests": 0, "seconds": 0.0, "skipped": 0, "failed": 0, **{k: 0 for k in KINDS}})
        row["tests"] += 1
        row["seconds"] += r["seconds"]
        row[r["kind"]] += 1
        if r["result"] in ("skipped", "failed"):
            row[r["result"]] += 1
    cols = [t["program"], t["tests"]] + [t[k] for k in KINDS] + [t["skipped"], t["failed"], t["duration"]]
    body = [[name, str(v["tests"])] + [str(v[k]) for k in KINDS] + [str(v["skipped"]), str(v["failed"]), duration(v["seconds"])]
            for name, v in sorted(per.items(), key=lambda x: (x[0].startswith("("), x[0].lower()))]
    totals = [t["total"], str(len(first))] + [str(sum(v[k] for v in per.values())) for k in KINDS] + \
             [str(sum(v["skipped"] for v in per.values())), str(sum(v["failed"] for v in per.values())), duration(sum(v["seconds"] for v in per.values()))]
    widths = [max(width(row[i]) for row in [cols] + body + [totals]) for i in range(len(cols))]

    def line(cells, style=lambda s: s):
        return "  " + "  ".join(style(pad(c, widths[i], right=i > 0)) for i, c in enumerate(cells))
    print()
    print(line(cols, bold))
    for row in body:
        print(line(row))
    print(line(totals, bold))
    print("  " + t["legend"])
    slow = sorted(first, key=lambda r: -r["seconds"])[:5]
    if slow:
        print(f"  {t['slowest']} : " + " · ".join(f"{r['id'].split('.', 1)[-1]} ({r['seconds']:.1f} s)" for r in slow))
    return 0


def main(argv):
    if argv[1:2] == ["--version"]:
        print(f"stats_runner.py version {__version__}")
        return 0
    if len(argv) >= 4 and argv[1] == "--run":
        return run(argv[2], [a for a in argv[3:] if not a.startswith("-")])          # « -v » of the former command line: the output is always verbose
    whole = None
    if len(argv) >= 3 and argv[1] == "--total":
        try:
            whole = float(argv[2])
        except ValueError:
            pass
        argv = argv[:1] + argv[3:]
    if len(argv) >= 3 and argv[1] == "--report":
        return report(argv[2:], whole=whole)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
