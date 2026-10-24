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
# web-monitor.py — AUTOMATIC monitoring: runs the project's tools without interaction (app-health-check.py,
# app-log-check.py, nginx-log-audit.sh, sync-crowdsec-blocklist.sh --status), decides whether something
# REQUIRES ACTION, and sends an e-mail ONLY in that case — a single grouped alert, never one per tool.
#
# What triggers an alert (and nothing else, so that every e-mail deserves to be read):
#   - app-health-check.py --target local: at least one [FAIL] (site, HSTS, blocking, robots.txt, Google...);
#   - app-log-check.py: entries "to review" (protocol attacks, Python traces, errors) — known harmless
#     noise (section [4]) never alerts;
#   - nginx-log-audit.sh --fail2ban --no-prompt: 5xx errors, Odoo upstream down, recommended ban
#     (section [10]) or repeat offender to ban permanently. NOT the attacks already blocked (405, 444,
#     traversal) nor the "access forbidden" entries of the error log: usual noise, which also includes the
#     tests of app-health-check.py itself (they would trigger an alert on every run);
#   - sync-crowdsec-blocklist.sh --status: community list out of date.
#
# Two design precautions:
#   - SEPARATE state directories for nginx-log-audit.sh and app-log-check.py (variables NGINX_LOG_AUDIT_STATE_DIR and
#     APP_LOG_CHECK_STATE_DIR): these tools remember where they stopped in the logs; if the automaton
#     shared that memory, your manual runs would always display "nothing new".
#   - No e-mail bursts: an alert IDENTICAL to the previous one is only sent again after 24 h; a
#     DIFFERENT alert is sent right away.
#
# E-mail: SMTP_* and NOTIFY_EMAIL_TO settings of the app-health-check.py configuration (same file, same
# sending function). Without SMTP configured: alert in the system journal (journalctl -t web-monitor) and in
# the complete report /var/log/web-monitor/, always written (30 days kept).
#
#
# Usage:
#   web-monitor.py                      runs the tools, alerts if necessary (default, = --run)
#   web-monitor.py --dry-run            same, without sending e-mail or touching the read positions
#   web-monitor.py --install-timer [--interval-hours N]   systemd timer (default: every hour)
#   web-monitor.py --uninstall-timer    removes the timer
#   web-monitor.py --status             timer state, last run, last alert
#   web-monitor.py --list-users         logins to Odoo (or BBB participants), in alphabetical order
#                  [--details]          ... with the traffic of each account (pages, errors, modules)
#                  [--table]            ... as a numbered table (N, UID, IP, name, logins, minutes, systems, browsers, pages; columns of 3 to 30 characters)
#                  [--sort KEY] [--reverse]   sort: name, login, uid, ip, first, last, logins, minutes, type, os, pages, written, received, sent (French synonyms accepted)
#   --lang en|fr   display language (default: WEB_MONITOR_LANG, LC_ALL, LC_MESSAGES, LANG; no variable: fr); catalog lang/web-monitor.fr.po
#   web-monitor.py --unban-check        reassess the manual bans (nginx-log-audit.sh --unban-check)
#   web-monitor.py --ban-recommended    ban the IPs recommended by the last run (--yes: without question)
#   web-monitor.py --apply [--yes]      summary, then the program makes the recommended fixes (--yes: without question)
#   web-monitor.py --summary [--days N]  figures summary: today, D-1, D-2, 7 days, 30 days (or N days) (traffic, blocks and
#                                             attacks, errors), highlights, log coverage; root
#   -v/--verbose  displays each command run ;  --version ;  --changelog

import argparse
import collections
import concurrent.futures
import contextlib
import bisect
import datetime
import glob
import gzip
import hashlib
import importlib.util
import ipaddress
import json
import os
# PATH completed: under cron, /usr/sbin and /sbin are missing (systemctl, iptables, fail2ban-client, nginx). Added at the end.
if not os.environ.get("NGINX_TOOLS_TESTS"):         # during tests: never the real commands of /usr/sbin
    os.environ["PATH"] = os.environ.get("PATH", "/usr/bin:/bin") + "".join(
        f":{d}" for d in ("/usr/local/sbin", "/usr/sbin", "/sbin") if d not in os.environ.get("PATH", "").split(":"))
import re
try:                    # line editing in prompts (backspace ^H or ^?, arrows): without readline, input() displays "^H"
    import readline  # noqa: F401
except ImportError:
    pass
import shlex
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse

__version__ = "2.78.20261023.210301"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
# Changelog in the doc/ subdirectory; fallback on the old location as long as the installation is not reorganized.
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
STATE_DIR = os.environ.get("WEB_MONITOR_STATE_DIR", "/var/lib/web-monitor")
LOG_DIR = os.environ.get("WEB_MONITOR_LOG_DIR", "/var/log/web-monitor")
SYSTEMD_DIR = os.environ.get("WEB_MONITOR_SYSTEMD_DIR", "/etc/systemd/system")
UNIT = "web-monitor"
LOG_RETENTION_DAYS = 180      # default; LOG_KEEP_DAYS of /etc/default/app-default.conf (variable NGINX_TOOLS_LOG_KEEP_DAYS) overrides it; 0 = never deleted
REALERT_AFTER_S = 24 * 3600
TOOL_TIMEOUT_S = 900
ODOO_SERVICE_CANDIDATES = ["erplibre.service", "erplibre_erplibre.service"]
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
VERBOSE = False


# --- Langue d'affichage : --lang en|fr, puis WEB_MONITOR_LANG, LC_ALL, LC_MESSAGES, LANG (apps/_i18n.py + catalogue lang/web-monitor.en.po) ----------
SYSTEM_CONFIG = "/etc/default/web-monitor.conf"     # then the personal file .web-monitor.conf in the home directory (apps/_config.py), then the command line
PERSONAL_CONFIG = ".web-monitor.conf"
# Configuration file options: KEY -> (command-line option, type). LANGUAGE: en, fr, or auto (follow LC_ALL / LANG).
SCHEMA_CONFIG = {"APP": ("app", str), "DAYS": ("days", int), "DETAILS": ("details", bool), "INTERVAL_HOURS": ("interval_hours", int), "NO_PAGER": ("no_pager", bool),
                 "NO_PROMPT": ("no_prompt", bool), "REVERSE": ("reverse", bool), "SORT": ("sort", None), "TABLE": ("table", bool), "VERBOSE": ("verbose", bool),
                 "REPEAT_HEADER": ("repeat_header", bool), "STATS": ("stats", bool), "TABLE_FIELDS": ("table_fields", lambda v: table_fields(v)),    # 2.67
                 "CSV": ("csv", str), "GROUP": ("group", str), "INTERNET": ("internet", bool)}                                                             # 2.69


def _explicit_config(argv):
    """-c FILE / --config FILE / --config=FILE from the command line (read before argparse: the language depends on it), or None."""
    for i, a in enumerate(argv):
        if a.startswith("--config="):
            return a.split("=", 1)[1]
        if a in ("-c", "--config") and i + 1 < len(argv):
            return argv[i + 1]
    return None


EXPLICIT_CONFIG = _explicit_config(sys.argv[1:])


def foreground_child():
    """Context of a child program that owns the terminal: Ctrl-C and its confirmation belong to it (apps/_i18n.py foreground_child); nothing without the module."""
    try:
        module = _load_module("_i18n")
    except Exception:  # noqa: BLE001 - module missing or broken: Ctrl-C keeps its usual behavior
        module = None
    return module.foreground_child() if module is not None and hasattr(module, "foreground_child") else contextlib.nullcontext()


def _load_module(display_name):
    spec = importlib.util.spec_from_file_location(display_name, os.path.join(SCRIPT_DIR, "apps", display_name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_i18n():
    """(language, translator, available languages, configuration, configuration files read). Module or catalog missing: French, no error."""
    cfg, files = {}, []
    try:
        _cfg_mod = _load_module("_config")
        cfg, files = _cfg_mod.lire(SCRIPT_NAME, EXPLICIT_CONFIG)
    except Exception:
        pass
    try:
        module = _load_module("_i18n")
        avail = module.langues_disponibles(SCRIPT_DIR, SCRIPT_NAME)
        chosen, origin = module.langue_et_origine(variable_programme="WEB_MONITOR_LANG", disponibles=avail, configuration=cfg.get("LANGUAGE", "")) \
            if hasattr(module, "langue_et_origine") else (module.langue(variable_programme="WEB_MONITOR_LANG", disponibles=avail, configuration=cfg.get("LANGUAGE", "")), "")
        globals()["LANGUAGE_ORIGIN"] = origin             # 2.67: which setting decided the language (shown in « Options: --lang xx (origin) »)
        return chosen, module.traducteur(chosen, SCRIPT_DIR, SCRIPT_NAME, ("_bbb", "_connexions", "_email_check", "_listes", "_odoo_db", "_profile", "nginx-log-audit", "sync-crowdsec-blocklist", "app-log-check")), avail, cfg, files
    except Exception:
        return "en", (lambda text_value: text_value), ["en"], cfg, files


LANGUAGE_ORIGIN = ""
LANGUAGE, TR, AVAILABLE_LANGUAGES, CONFIG, CONFIG_FILES = _load_i18n()
LITERAL_START, LITERAL_END, LITERAL_SLOT = "\ue001", "\ue002", "\ue003"     # 2.71: private-use characters, never in a real text
LITERAL_RE = re.compile(LITERAL_START + "(.*?)" + LITERAL_END, re.S)


def literal(text_value):
    """2.71: text displayed AS IS in every language — option values, field and sort keys (« browsers », « sent »): the translator replaced them by
    French words (« navigateurs », « envoyé(s) ») that the program then refused. Only for texts that are displayed through TR (print, argparse)."""
    return LITERAL_START + str(text_value) + LITERAL_END


def _keeping_literals(translate):
    """The translator, with the literal() parts set aside during the translation, then put back unchanged and without their markers."""
    def tr(text_value):
        if not isinstance(text_value, str) or LITERAL_START not in text_value:
            return translate(text_value)
        kept = LITERAL_RE.findall(text_value)
        res = translate(LITERAL_RE.sub(LITERAL_SLOT, text_value))
        if not isinstance(res, str) or res.count(LITERAL_SLOT) != len(kept):
            return text_value.replace(LITERAL_START, "").replace(LITERAL_END, "")
        it = iter(kept)
        return re.sub(LITERAL_SLOT, lambda _m: next(it), res)
    return tr


TR = _keeping_literals(TR)
try:
    _load_module("_i18n").installer_confirmation_ctrl_c(TR)       # Ctrl+C asks for confirmation (interactive terminal only)
except Exception:
    pass
try:                                                      # --anonymize: the program is relaunched behind the output filter (apps/_anonymiser.py + apps/_traduire.py); CLOSED failure
    _load_module("_anonymiser").relancer_si_demande(sys.argv[1:], CONFIG)
except Exception:
    if any(a.startswith("--anon") and "--anonymize".startswith(a) for a in sys.argv[1:]):
        raise SystemExit("ERROR: anonymization requested but apps/_anonymiser.py is unreadable: nothing is displayed.")
_system_print, _system_input = print, input


def print(*a, **k):            # noqa: A001 — all displayed text goes through the translator (no effect in French)
    _system_print(*(TR(x) if isinstance(x, str) else x for x in a), **k)


def input(prompt_text=""):          # noqa: A001
    return _system_input(TR(prompt_text))


def migrate_path(old, new):
    """Renaming of the programs in 2.0: renames the old file or directory if it exists and the new one does NOT
    exist yet (never overwrites); silent if nothing to do or if the rights are missing."""
    if os.path.exists(old) and not os.path.exists(new):
        try:
            os.makedirs(os.path.dirname(new) or ".", exist_ok=True)
            os.rename(old, new)
            print(f"Migration (programs renamed, version 2.0): {old} → {new}", file=sys.stderr)
        except OSError:
            pass


def migrate_installation():
    """Renaming 2.0 (surveillance-odoo.py -> web-monitor.py): state, reports, state directories of the tools, and systemd
    timer (the old one is removed, the new one installed with the SAME interval and the new program path)."""
    if not os.environ.get("WEB_MONITOR_STATE_DIR"):
        migrate_path("/var/lib/surveillance-odoo", STATE_DIR)
    for old, new in (("chk-nginx-logs", "nginx-log-audit"), ("chk-odoo-logs", "app-log-check")):
        migrate_path(os.path.join(STATE_DIR, old), os.path.join(STATE_DIR, new))
    if not os.environ.get("WEB_MONITOR_LOG_DIR"):
        migrate_path("/var/log/surveillance-odoo", LOG_DIR)
    migrate_path(os.path.join(STATE_DIR, "derniere-alerte.json"), os.path.join(STATE_DIR, "last-alert.json"))   # 2.2
    migrate_path(os.path.join(STATE_DIR, "dernier-passage"), os.path.join(STATE_DIR, "last-run"))               # 2.2
    old_timer = os.path.join(SYSTEMD_DIR, "surveillance-odoo.timer")
    if os.path.exists(old_timer) and not os.path.exists(os.path.join(SYSTEMD_DIR, f"{UNIT}.timer")) and os.geteuid() == 0:
        m = re.search(r"OnCalendar=\*-\*-\* (?:00/(\d+)|\*):05:00", open(old_timer).read())
        hour_values = int(m.group(1)) if m and m.group(1) else 1
        run(["systemctl", "disable", "--now", "surveillance-odoo.timer"], timeout=60)
        for ext in ("timer", "service"):
            try:
                os.remove(os.path.join(SYSTEMD_DIR, f"surveillance-odoo.{ext}"))
            except FileNotFoundError:
                pass
        eprint(f"Migration: timer surveillance-odoo removed, replaced by {UNIT} (every {hour_values} hour(s)).")
        install_timer(hour_values)


def eprint(*a):
    print(*a, file=sys.stderr)


def verbose_args():
    """--verbose of web-monitor.py, passed to ALL the programs of the suite that it launches (each then displays its
    own external commands): ["--verbose"] or []."""
    return ["--verbose"] if VERBOSE else []


def run(cmd, env_extra=None, timeout=TOOL_TIMEOUT_S):
    """Runs a command, returns (code, text output without colors). Never raises: a failing tool is
    information for the report, not a reason to stop the monitoring."""
    if VERBOSE:
        eprint("+ " + shlex.join(cmd))
    env = dict(os.environ, NGINX_TOOLS_LANG="fr", **(env_extra or {}))          # analyzed output: always in French, translated afterwards when displayed
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        if VERBOSE and r.stderr:                         # the commands that a called program displays with --verbose
            sys.stderr.write(r.stderr if r.stderr.endswith("\n") else r.stderr + "\n")
        return r.returncode, ANSI_RE.sub("", (r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return 124, f"(timed out: {timeout} s)"
    except OSError as e:
        return 127, f"(cannot start: {e})"


def section(text, start_marker, end_marker_re=r"^--- \[|^=====|^RÉSUMÉ"):
    """Lines between a line starting with start_marker and the beginning of the next section."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith(start_marker):
            inside = True
            continue
        if inside and re.match(end_marker_re, line.strip()):
            break
        if inside:
            out.append(line)
    return [l for l in out if l.strip()]


PROFILE = {}           # application profile chosen (apps/<name>.conf), loaded in main()
NO_PAGER = False      # --no-pager: never offer to open the report in less
NO_PROMPT = False     # --no-prompt: never ask the ban question at the end of a run
SAVE_RECO = False    # --save-recommended: with --dry-run, still writes recommended-bans.json (b key of app-log-live.py)
RECOMMENDED = []     # (IP, reason) recommended for banning by the current run (analyze_nginx_logs)
ACTIONS = []          # (label, equivalent command, function): fixes the program can make itself (summary)
APPLY = False     # --apply: make the fixes proposed by the summary
YES = False           # --yes: without question (with --apply or --ban-recommended)


def load_profile(force):
    """Profile apps/<name>.conf: detected, or forced by --app (or APP_PROFILE). Without an apps/ folder: Odoo by default."""
    folder = os.path.join(SCRIPT_DIR, "apps")
    if not os.path.isfile(os.path.join(folder, "_profile.py")):
        return {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "ACCESS_LOGS": "*-access.log", "CATCHALL_LOG": "odoo-catchall-444.log",
                "APP_LOG_KIND": "journal", "SERVICES": " ".join(ODOO_SERVICE_CANDIDATES),
                "APP_DETECTION": "default (apps/ folder missing next to the program)"}
    sys.path.insert(0, folder)
    import _profile
    return _profile.charger_profil_app(folder, force)


def detect_odoo_service():
    for svc in ODOO_SERVICE_CANDIDATES:
        code, out = run(["systemctl", "list-unit-files", svc, "--no-legend"], timeout=20)
        if code == 0 and any(l.split()[:1] == [svc] for l in out.splitlines()):
            ns = run(["systemctl", "show", "-p", "LogNamespace", "--value", svc], timeout=20)[1].strip()
            return svc, ns
    return None, ""


# ------------------------------------------------------------------------------------------------------------------
# Analysis of each tool: returns a list of alerts (title, excerpt lines, keys) — empty list = nothing to
# report. The KEYS identify each element (a failing check, a proposed IP, a type of Python trace)
# without the counters or hours that change on every run: they are what decides "new problem".
# ------------------------------------------------------------------------------------------------------------------
def analyze_sanity(code, out):
    fails = [l.strip() for l in out.splitlines() if l.strip().startswith("[FAIL]")]
    if code != 0 and fails:
        return [("app-health-check.py: failing check(s)", fails,
                 ["sanity:" + f.replace("[FAIL]", "").split(" — ")[0].strip() for f in fails])]
    if code not in (0, 1):
        return [("app-health-check.py: the tool itself failed", out.strip().splitlines()[-8:], ["sanity:outil"])]
    return []


def analyze_odoo_logs(code, out):
    # "N entries to review" (Odoo journal) or "N errors to review" (file journal, e.g. BBB)
    m = re.search(r"RÉSUMÉ : (\d+) (?:entrée|erreur)\(s\) à examiner.*", out)
    if m and int(m.group(1)) > 0:
        lines = [m.group(0)]
        for marker in ("--- [1]", "--- [2]", "--- [3]"):
            body = section(out, marker)
            header = next((l for l in out.splitlines() if l.startswith(marker)), marker)
            if body and body[0].strip() != "RIEN":
                lines.append(header)
                lines += ["  " + l.strip()[:200] for l in body[:10]]
        keys = []
        for marker in ("--- [1]", "--- [2]", "--- [3]"):
            for l in section(out, marker):
                mm = re.match(r"\s*\[\d+x\]\s*(.+)", l)
                if mm:
                    keys.append("odoo:" + re.sub(r"\d+", "N", mm.group(1))[:120])
        return [(f"app-log-check.py: item(s) to examine in the journal of {PROFILE.get('APP_LABEL', 'Odoo')}",
                 lines, keys or ["odoo:entrees"])]
    if code not in (0, 1) and "RÉSUMÉ" not in out:
        return [("app-log-check.py: the tool itself failed", out.strip().splitlines()[-8:], ["odoo:outil"])]
    return []


UPSTREAM_RE = re.compile(r"upstream|connect\(\) failed|no live upstreams|upstream timed out|Connection refused", re.I)


def analyze_nginx_logs(code, out):
    alerts = []
    s6 = section(out, "--- [6]")
    if s6 and s6[0].strip() != "RIEN":
        alerts.append(("nginx-log-audit.sh: server errors 5xx", [l.strip()[:200] for l in s6[:12]], ["nginx:5xx"]))
    s7 = [l for l in section(out, "--- [7]") if UPSTREAM_RE.search(l)]
    if s7:
        alerts.append(("nginx-log-audit.sh: Odoo unreachable from nginx (upstream errors)", [l.strip()[:200] for l in s7[:12]], ["nginx:upstream"]))
    # Section [10] walked INVESTIGATION BY INVESTIGATION: an IP is kept only if ITS OWN investigation concludes "ban
    # recommended" (before 2.5, all the IPs of the section were as soon as a single one was recommended — including
    # the robots "to watch" or "probably harmless").
    blocks, current = [], None
    for l in section(out, "--- [10]"):
        if l.strip().startswith("▶"):
            current = [l.strip()]
            blocks.append(current)
        elif current is not None:
            current.append(l.strip())
    proposals, ips = [], []
    for block in blocks:
        if not any("bannissement recommandé" in l for l in block):
            continue
        ip = re.sub(r"^▶\s*(\S+).*", r"\1", block[0])
        score = next((re.search(r"Score \d+/7", l).group(0) for l in block if re.search(r"Score \d+/7", l)), "")
        hostile = next((re.search(r"Signes d'hostilité : (\d+)", l).group(1) for l in block if "Signes d'hostilité" in l), "?")
        ips.append(ip)
        proposals += [block[0], f"    → {score} : ban recommended ({hostile} sign(s) of hostility)"]
        RECOMMENDED.append((ip, TR(f"investigation: {score}, {hostile} sign(s) of hostility".replace(" : ,", " :"))))
    if ips:
        alerts.append(("nginx-log-audit.sh: ban recommended (investigation, section [10])", proposals[:12],
                       ["nginx:ban:" + ip for ip in ips]))
    repeat_offender = []
    grab = False
    for l in out.splitlines():
        if "Bannissement PERMANENT recommandé" in l:
            grab = True
            repeat_offender.append(l.strip())
            continue
        if grab:
            if l.startswith("Rappel :") or l.startswith("=====") or "LISTE COMMUNAUTAIRE" in l:
                break
            if l.strip().startswith("▶") or "Pour bannir" in l:
                repeat_offender.append(l.strip())
    if repeat_offender:
        ips = [re.sub(r"^▶\s*(\S+).*", r"\1", l) for l in repeat_offender if l.startswith("▶")]
        for l in repeat_offender:
            m = re.match(r"^▶\s*(\S+)\s*—\s*(.+)$", l)
            if m and m.group(1) not in [r[0] for r in RECOMMENDED]:
                RECOMMENDED.append((m.group(1), TR(f"repeat offender: {m.group(2)} — repeated temporary bans")))
        alerts.append(("nginx-log-audit.sh: repeat offender(s) to ban permanently", repeat_offender[:14],
                       ["nginx:recidive:" + ip for ip in ips] or ["nginx:recidive"]))
    if code != 0 and "RÉSUMÉ" not in out:
        alerts.append(("nginx-log-audit.sh: the tool itself failed", out.strip().splitlines()[-8:], ["nginx:outil"]))
    return alerts


BACKUP_STATE = os.environ.get("ODOO_BACKUP_STATE_DIR", "/var/lib/odoo-backup")
REINSTALL = {"web-monitor": "web-monitor.py --install-timer", "odoo-backup": "odoo-backup.sh --install-timer",
               "sync-crowdsec-blocklist": "sync-crowdsec-blocklist.sh --install-cron"}


def backup_threshold_hours():
    """Maximum tolerated age of the last backup, written by odoo-backup.sh according to the configured hours (maximum gap between
    two backups + 2 h); 26 h (one backup per day) as long as it does not exist."""
    try:
        return max(1, int(open(os.path.join(BACKUP_STATE, "max-age-hours")).read().strip()))
    except (OSError, ValueError):
        return 26


def timers_missing_files():
    """[(tool, kind, file)]: systemd units (web-monitor, odoo-backup) and cron entries (sync-crowdsec-blocklist) of our tools whose
    command runs a SCRIPT that does not exist (moved, deleted) or reads a configuration (--config, -c) that does not exist.
    Before odoo-backup.sh 1.5, a missing --config was ignored: the backup ran with the default values, without
    REMOTE, without any message — this is what this check reveals on an already installed timer."""
    commands = []
    for tool_name in (UNIT, "odoo-backup"):
        try:
            for text_line in open(os.path.join(SYSTEMD_DIR, f"{tool_name}.service"), encoding="utf-8", errors="replace"):
                if text_line.startswith("ExecStart="):
                    commands.append((tool_name, text_line.split("=", 1)[1].strip().lstrip("-@+!:")))
        except OSError:
            pass
    try:
        for text_line in open(os.environ.get("SYNC_CROWDSEC_CRON_FILE", "/etc/cron.d/sync-crowdsec-blocklist"), encoding="utf-8", errors="replace"):
            t = text_line.strip()
            if not t or t.startswith("#") or "=" in t.split()[0]:
                continue
            fields = t.split(None, 6)                         # m h day month weekday user command
            if len(fields) >= 7:
                commands.append(("sync-crowdsec-blocklist", fields[6]))
    except OSError:
        pass
    problems = []
    for tool_name, command in commands:
        try:
            words = shlex.split(command)
        except ValueError:
            continue
        script = next((m for m in words if os.path.isabs(m) and re.search(r"\.(sh|py)$", m)), None)
        if script and not os.path.exists(script):
            problems.append((tool_name, "script", script))
        for i, m in enumerate(words):
            value = m.split("=", 1)[1] if m.startswith("--config=") else (words[i + 1] if m in ("--config", "-c") and i + 1 < len(words) else None)
            if value and not os.path.exists(value):
                problems.append((tool_name, "config", value))
    return problems


def analyze_timers():
    """Alert: a timer of our tools references a file (script or configuration) that does not exist."""
    alert_items = []
    for tool_name, kind, path in timers_missing_files():
        what = "reads a configuration file" if kind == "config" else "runs a script"
        alert_items.append((f"{tool_name} : the timer {what} which does not exist ({path})",
                        [f"the automatic task fails, or runs without its settings (default values) — fix it: "
                         f"{REINSTALL[tool_name]} (without --config: the program finds its own file in /etc/default)"],
                        [f"timer:{tool_name}:{kind}:{path}"]))
    return alert_items


def analyze_backup(code, out):
    """Odoo backup (odoo-backup.sh --status): alert if it has already worked (last-success) and is
    too old or failing. Never configured: no alert on every run, but a HIGH recommendation."""
    if not os.path.exists(os.path.join(BACKUP_STATE, "last-success")):
        return []
    text_lines = [re.sub(r"\x1b\[[0-9;]*m", "", l).strip() for l in out.splitlines() if "[FAIL]" in l or "dernier échec" in l]
    if code != 0 or any("[FAIL]" in l for l in text_lines):
        return [("odoo-backup.sh: Odoo backup too old or failing", text_lines[:6] or [out.strip()[:200]], ["sauvegarde:echec"])]
    return []


def analyze_crowdsec(code, out):
    alerts = []
    # Consecutive failures of the synchronization (sync-crowdsec-blocklist.sh 1.10): reported from the first monitoring run,
    # instead of being discovered in /var/log/sync-crowdsec-blocklist.log.
    text_lines = out.splitlines()
    for i, l in enumerate(text_lines):
        if l.strip().startswith("ÉCHEC EN COURS"):
            alerts.append(("sync-crowdsec-blocklist.sh: synchronization failing",
                           [x.strip() for x in text_lines[i:i + 3]], ["crowdsec:echec"]))
            break
    stale = [l.strip() for l in text_lines if "inchangée depuis" in l or l.strip().startswith("ATTENTION")]
    if stale:
        alerts.append(("sync-crowdsec-blocklist.sh: community list outdated", stale[:6], ["crowdsec:perimee"]))
    return alerts


# ------------------------------------------------------------------------------------------------------------------
def human_key(k):
    """Readable label of an alert key, for the "NEW" line of the e-mail."""
    labels = {"nginx:ban:": "ban recommended for ", "nginx:recidive:": "repeat offender to ban: ",
              "sanity:": "check failing: ", "odoo:": "Odoo journal: ", "nginx:5xx": "5xx errors",
              "nginx:upstream": "Odoo unreachable from nginx", "crowdsec:perimee": "CrowdSec list outdated"}
    for prefix, label in labels.items():
        if k.startswith(prefix):
            return label + k[len(prefix):]
    return k.split(":", 1)[-1]


def load_sanity_module():
    path = os.path.join(SCRIPT_DIR, "app-health-check.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("sanity_check_odoo", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def journal(lines, priority="user.notice"):
    """Writes lines to the system journal (journalctl -t web-monitor), one entry per line: logger reads
    its standard input line by line. Limited to 120 lines (the complete report stays in LOG_DIR)."""
    if not shutil.which("logger"):
        return
    if VERBOSE:
        eprint(f"+ logger -t {SCRIPT_NAME} -p {priority} ({len(lines)} line(s))")
    try:
        subprocess.run(["logger", "-t", SCRIPT_NAME, "-p", priority], input=TR("\n".join(lines[:120]) + "\n"),
                       text=True, timeout=10, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        pass


def notify(subject, body, dry_run):
    """E-mail through the app-health-check.py configuration; the COMPLETE CONTENT of the alert also goes to the
    system journal (the only channel when SMTP is not configured: a mere title was useless there)."""
    if dry_run:
        return "not sent (--dry-run)"
    journal([subject] + [l for l in body.splitlines() if l.strip()], "user.warning")
    mod = load_sanity_module()
    if mod is None:
        return "not sent: app-health-check.py not found next to this script (system journal only)"
    try:
        cfg = mod.load_config(mod.resolve_config_paths(None))
    except Exception as e:
        return f"not sent: app-health-check.py configuration unreadable ({e}) — system journal only"
    if not cfg.get("SMTP_HOST") or not cfg.get("NOTIFY_EMAIL_TO"):
        return ("not sent: SMTP_HOST / NOTIFY_EMAIL_TO missing from the app-health-check.py configuration (system journal only: journalctl -t web-monitor)")
    try:
        mod.send_email(cfg, TR(subject), TR(body))
        return f"sent to {cfg['NOTIFY_EMAIL_TO']}"
    except Exception as e:
        return f"FAILED to send ({e}) — system journal only"


def journal_days():
    """Days of retention of the reports of this program: LOG_KEEP_DAYS of the common configuration file, otherwise LOG_RETENTION_DAYS; 0 = never."""
    try:
        return max(0, int(os.environ.get("NGINX_TOOLS_LOG_KEEP_DAYS", "").strip()))
    except ValueError:
        return LOG_RETENTION_DAYS


def purge_old_logs():
    if not journal_days():
        return
    limit = time.time() - journal_days() * 86400
    try:
        for name in os.listdir(LOG_DIR):
            p = os.path.join(LOG_DIR, name)
            if name.endswith(".log") and os.path.getmtime(p) < limit:
                os.remove(p)
    except OSError:
        pass


def do_run(dry_run):
    host = socket.gethostname()
    now = datetime.datetime.now().astimezone()
    work_state = tempfile.mkdtemp(prefix="web-monitor-") if dry_run else STATE_DIR
    os.makedirs(work_state, exist_ok=True)
    report, alerts = [], []
    report.append(f"web-monitor.py v{__version__} — {host} — {now:%Y-%m-%d %H:%M:%S %Z}")
    if dry_run:
        report.append("(--dry-run: log reading positions NOT modified, no e-mail)")

    def tool(name):
        p = os.path.join(SCRIPT_DIR, name)
        return p if os.path.isfile(p) else None

    runs = []
    sc = tool("app-health-check.py")
    if sc:
        runs.append(("app-health-check.py --target local", [sys.executable, sc, "--target", "local", "--app", PROFILE["APP_NAME"]] + verbose_args(),
                     None, analyze_sanity))
    ol = tool("app-log-check.py")
    if ol:
        svc, ns = detect_odoo_service() if PROFILE.get("APP_LOG_KIND") == "journal" else (None, "")
        cmd = ([sys.executable, ol, "--app", PROFILE["APP_NAME"]] + (["--service", svc] if svc else [])
               + (["--namespace", ns] if ns else []) + verbose_args())
        runs.append(("app-log-check.py", cmd, {"APP_LOG_CHECK_STATE_DIR": os.path.join(work_state, "app-log-check")}, analyze_odoo_logs))
    nl = tool("nginx-log-audit.sh")
    if nl:
        runs.append(("nginx-log-audit.sh --fail2ban --no-prompt", ["bash", nl, "--fail2ban", "--no-prompt", "--app", PROFILE["APP_NAME"]] + verbose_args(),
                     {"NGINX_LOG_AUDIT_STATE_DIR": os.path.join(work_state, "nginx-log-audit")}, analyze_nginx_logs))
    cs = tool("sync-crowdsec-blocklist.sh")
    if cs:
        runs.append(("sync-crowdsec-blocklist.sh --status", ["bash", cs, "--status"] + verbose_args(), None, analyze_crowdsec))
    ob = os.path.join(SCRIPT_DIR, "odoo-backup.sh")
    if PROFILE.get("APP_NAME") == "odoo" and os.path.isfile(ob):
        runs.append(("odoo-backup.sh --status", ["bash", ob, "--status"] + verbose_args(), None, analyze_backup))

    for label, cmd, env, analyzer in runs:
        t0 = time.time()
        code, out = run(cmd, env)
        found = analyzer(code, out)
        alerts += found
        report.append("")
        report.append("=" * 100)
        report.append(f" {label} — code {code}, {time.time() - t0:.0f} s — "
                      + (f"{len(found)} alert(s)" if found else "nothing to report"))
        report.append("=" * 100)
        report.append(out.rstrip())
    timers_found = analyze_timers()
    if timers_found:
        alerts += timers_found
        report += ["", "=" * 100, f" timers of our tools — {len(timers_found)} alert(s)", "=" * 100]
        report += [f"{heading}\n  {text_lines[0]}" for heading, text_lines, _ in timers_found]
    missing = [n for n in ("app-health-check.py", "app-log-check.py", "nginx-log-audit.sh", "sync-crowdsec-blocklist.sh") if not tool(n)]
    if missing:
        report.insert(1, f"Tools missing from {SCRIPT_DIR} (ignored): {', '.join(missing)}")

    # --- Decision et envoi (anti-rafale : alerte identique renvoyee apres 24 h seulement) ---
    alert_file = os.path.join(STATE_DIR, "last-alert.json")
    if not dry_run or SAVE_RECO:
        remember_recommendations(now)
    status = "nothing to report"
    if alerts:
        body_lines = [f"Monitoring {host} — {now:%Y-%m-%d %H:%M %Z} — {len(alerts)} item(s) to examine:", ""]
        for title, lines, _ in alerts:
            body_lines.append(f"■ {title}")
            body_lines += [f"    {l}" for l in lines]
            body_lines.append("")
        if RECOMMENDED:
            body_lines += [f"To ban the {len(RECOMMENDED)} recommended IP(s) in one command (root, with confirmation):",
                           "    web-monitor.py --ban-recommended", ""]
        subject = f"[web-monitor] {host} : {len(alerts)} item(s) to examine"
        # Comparison on the TITLES (the details — hours, counters — change on every run). New e-mail
        # only if a NEW problem appears, or 24 h after the previous one: a problem that disappears (resolved)
        # does not justify writing again for the others, already reported.
        titles = [t for t, _, _ in alerts]
        keys = sorted({k for _, _, ks in alerts for k in ks})
        digest = hashlib.sha256("\n".join(keys).encode()).hexdigest()
        previous = {}
        try:
            previous = json.load(open(alert_file))
        except (OSError, ValueError):
            pass
        new_keys = [k for k in keys if k not in previous.get("keys", [])]
        if not new_keys and time.time() - previous.get("time", 0) < REALERT_AFTER_S:
            status = (f"{len(alerts)} alert(s), all already reported on {previous.get('when', '?')} — no new "
                      "e-mail before 24 h (unless a new problem)")
        else:
            log_path_hint = os.path.join(LOG_DIR, f"{now:%Y-%m-%d_%H%M%S}.log")
            if previous.get("keys") and new_keys:
                body_lines.insert(1, f"NEW since the e-mail of {previous.get('when', '?')} : "
                                     + "; ".join(human_key(k) for k in new_keys))
            body_lines.append(f"Full report on the server: {log_path_hint}")
            status = f"{len(alerts)} alert(s) — e-mail {notify(subject, chr(10).join(body_lines), dry_run)}"
            if not dry_run:
                os.makedirs(STATE_DIR, exist_ok=True)
                json.dump({"digest": digest, "time": time.time(), "when": f"{now:%Y-%m-%d %H:%M}",
                           "titles": titles, "keys": keys}, open(alert_file, "w"), ensure_ascii=False)
        report.insert(1, "")
        report.insert(2, "ALERTES : " + "; ".join(t for t, _, _ in alerts))
    report.insert(1, f"Result: {status}")

    text = "\n".join(report) + "\n"
    if not dry_run:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{now:%Y-%m-%d_%H%M%S}.log")
        n = 2
        while os.path.exists(path):                      # two runs in the same second: overwrite nothing
            path = os.path.join(LOG_DIR, f"{now:%Y-%m-%d_%H%M%S}-{n}.log"); n += 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(TR(text))
        os.chmod(path, 0o640)
        with open(os.path.join(STATE_DIR, "last-run"), "w") as f:
            f.write(f"{now:%Y-%m-%d %H:%M:%S %Z} — {status}\n")
        purge_old_logs()
        # Status line on EVERY run: "journalctl -t web-monitor" also shows the history of the runs
        # (nothing to report, alerts already reported…), not only the alerts sent.
        journal([f"Pass {now:%Y-%m-%d %H:%M} — {status}"])
        print(f"{host} — {now:%Y-%m-%d %H:%M %Z}")
        print(f"Result: {status}")
        if alerts:
            print()
            print(f"Items to examine ({len(alerts)}) :")
            for title, lines, _ in alerts:
                print(f"  ■ {title}")
                for l in lines[:6]:
                    print(f"      {l[:160]}")
                if len(lines) > 6:
                    print(f"      (… {len(lines) - 6} more line(s) in the full report)")
            print()
        print(f"Full report: {path}")
        offer_ban()
        offer_less(path)
    else:
        print(text)
        shutil.rmtree(work_state, ignore_errors=True)
    return 1 if alerts else 0


# ------------------------------------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------------------------------------
# --summary: figures summary (today, 7 days, 30 days) of traffic, blocks and attacks, and errors,
# followed by the highlights of the last 30 days and the exact COVERAGE of each log (oldest date,
# rotation policy, change to make to keep 3 months). Sources: nginx logs of the site and of the
# catch-all sensor (rotations and .gz included), fail2ban.log, Odoo systemd journal, states of sync-crowdsec-blocklist.sh and
# nginx-log-audit.sh.
# ------------------------------------------------------------------------------------------------------------------
NGINX_DIR = os.environ.get("WEB_MONITOR_NGINX_DIR", "/var/log/nginx")
FAIL2BAN_LOG = os.environ.get("WEB_MONITOR_FAIL2BAN_LOG", "/var/log/fail2ban.log")
LOGROTATE_DIR = os.environ.get("WEB_MONITOR_LOGROTATE_DIR", "/etc/logrotate.d")
CROWDSEC_STATE = os.environ.get("SYNC_CROWDSEC_STATE_DIR", "/var/lib/sync-crowdsec-blocklist")
CHK_STATE = os.environ.get("NGINX_LOG_AUDIT_STATE_DIR", os.path.expanduser("~/.local/state/nginx-log-audit"))
TARGET_RETENTION_DAYS = 92
# Magenta for malicious elements and alerts (terminal only; never in a file or a pipe).
BAD, END_BAD = ("\x1b[1;35m", "\x1b[0m") if sys.stdout.isatty() else ("", "")


def colors_on():
    """ANSI codes allowed: the output is a terminal at display time (never in a captured report or one sent by e-mail), without NO_COLOR nor TERM=dumb."""
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def color_code(code, text_value):
    """Colored text ONLY if the output is a terminal at display time (never in a captured report
    or one sent by e-mail, nor with NO_COLOR). code: 32 green, 33 yellow, 31 red, 1 bold, 35 magenta."""
    if not colors_on():
        return str(text_value)
    return f"\x1b[1;{code}m{text_value}\x1b[0m" if code != "1" else f"\x1b[1m{text_value}\x1b[0m"
# Group 8: requested domain name (nginx combined_host format: host="…" at the end of the line; absent from old lines).
TIME_RE = re.compile(r'\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}):\d{2} ([+-]\d{4})\]')     # minute and time zone of an access line (--list-users --table)
ACCESS_RE = re.compile(r'^(\S+) \S+ \S+ \[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3})(?: (\S+) "[^"]*" "([^"]*)")?(?: host="([^"]*)")?(?: rl=(\d+))?')
# 2.66: « rl=$request_length » (size of the request, headers included) at the end of the combined_host format (nginx-odoo-config 1.11): MB sent by each account.
CATCHALL_RE = re.compile(r'^(\S+) - \[(\d{2}/\w{3}/\d{4}):[^\]]*\](?: "\S+ (\S+))?')
FAIL2BAN_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) .*\[([^\]]+)\] Ban (\S+)")
ASSET_RE = re.compile(r"^/web/(assets|image|static|content|binary)/|/static/|/websocket|/longpolling|"
                      r"\.(js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|map)(\?|$)")
SENSITIVE_BASE = (r"\.env|\.git/|phpmyadmin|\.aws/|\.ssh/|\.(bak|old|sql|swp)(\?|$)|"
                 r"/config\.(php|json|yml)|/server-status|/_ignition|/debug/default")
SENSITIVE_WP = r"/wp-|wp-login|xmlrpc\.php|/wp(/|\?|$)|/wordpress(/|\?|$)"      # sensitive on an Odoo site ONLY (normal pages under WordPress: apps/_profile.py cms())
SENSITIVE_CMS_BBB = r"/administrator(/|$)|/joomla|/drupal|/sites/default|/typo3|/magento|/prestashop|/bitrix|/umbraco|/ghost/|/user/login|/node/[0-9]+|/components/com_|/index\.php|\.(asp|aspx|jsp|cgi|php)(\?|$)|/admin/login|/wp-json|/typo3conf"
SENSITIVE_RE = re.compile(SENSITIVE_BASE + "|" + SENSITIVE_WP)


def set_cms():
    """WordPress site (variable NGINX_TOOLS_CMS, /etc/default/nginx-tools-cms.conf or detected wp-config.php): its URLs are no longer "sensitive"."""
    global SENSITIVE_RE
    folder = os.path.join(SCRIPT_DIR, "apps")
    if not os.path.isfile(os.path.join(folder, "_profile.py")):
        return
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import _profile
    if PROFILE.get("APP_NAME") == "bbb":                 # BigBlueButton hosts no CMS: anything related to one is sensitive
        SENSITIVE_RE = re.compile(SENSITIVE_BASE + "|" + SENSITIVE_WP + "|" + SENSITIVE_CMS_BBB)
    elif _profile.cms() == "wordpress":
        SENSITIVE_RE = re.compile(SENSITIVE_BASE)
# Codes produced by nginx ITSELF (the request does not reach the application): invalid request, refusal (allow
# list, robot filter), forbidden method, body too large, rate limiting, closing without a response.
LINE_MAX = 65536          # guard: beyond it, the line is truncated BEFORE any regular expression (bounded CPU)


def truncate(text_lines):
    """Log lines truncated to LINE_MAX characters: an abnormally long line (attack, huge trace) cannot
    blow up the computation time of the regular expressions."""
    for text_line in text_lines:
        yield text_line[:LINE_MAX]


NGINX_404_SIZE = 2048    # below: nginx 404 page; above: application 404 page
# Redirect produced by nginx ITSELF ("return 301" of a block that only redirects, e.g. rencontres-linux.quebec →
# www): page of 162 to 169 bytes ("301 Moved Permanently", with or without version number); the Odoo redirect
# (Werkzeug, "Redirecting..." + target URL) always exceeds 200 bytes. A malicious URL redirected by nginx did not
# reach the application: counted as rejected (before 2.37, false "not filtered by nginx").
NGINX_3XX_SIZE = 200
NGINX_REJECT_CODES = {"400", "403", "405", "413", "429", "444"}
# Malicious URLs by their SHAPE, whatever the response code (2.6): sensitive files (SENSITIVE_RE), directory
# traversal, PHP or CGI scripts (Odoo serves none), SQL or script injection, and attempts to use the
# server as a proxy (absolute URL, or "host:port" of a CONNECT request). A 403 or 444 does NOT make a URL
# malicious: it refuses a CLIENT (blocked robot, unknown domain) on a page that is sometimes entirely legitimate.
OTHER_BAD_RE = re.compile(r"\.\./|%2e%2e|\.php(\?|$)|/cgi-bin/|union(\s|%20|\+)+select|<script|%3cscript|^https?://|"
                           r"^[a-z0-9.-]+\.[a-z]{2,}:\d+$", re.I)
OUTIL_RE = re.compile(r"(curl|wget|python-requests|python-httpx|python-urllib|aiohttp|go-http-client|okhttp|libwww-perl|"
                      r"java|scrapy|headlesschrome|zgrab|masscan|nmap|poc-suite|nuclei|sqlmap|nikto)", re.I)
SERVER_TESTS = ("app-health-check/", "sanity-check-odoo/")     # User-Agents of our own tests (deliberately blocked)


def malicious(url):
    return bool(SENSITIVE_RE.search(url) or OTHER_BAD_RE.search(url))


def client_family(ua):
    """Readable family of a blocked client: robot by its name, tool, browser by system, empty User-Agent."""
    if not ua or ua == "-":
        return "(empty User-Agent)"
    r = ROBOT_RE.search(ua)
    if r:
        return r.group(0)
    o = OUTIL_RE.search(ua)
    if o:
        return o.group(1).lower()
    if ua.startswith("Mozilla/"):
        for pattern, display_name in (("Windows", "Windows"), ("iPhone", "iOS"), ("iPad", "iOS"), ("Android", "Android"),
                           ("Macintosh", "macOS"), ("Linux", "Linux")):
            if pattern in ua:
                return f"browser ({display_name})"
        return "browser (other)"
    return ua.split("/")[0][:30]


def server_addresses():
    """Addresses of this server (loopback, hostname -I, public IP remembered by nginx-log-audit.sh)."""
    ips = {"127.0.0.1", "::1"}
    ips.update(run(["hostname", "-I"], timeout=10)[1].split())
    try:                                     # (the old name is migrated by nginx-log-audit.sh)
        ips.update(open(os.path.join(CHK_STATE, "public-ip")).read().split())
    except OSError:
        pass
    return ips


_LISTS = [None]


class EmptyLists(object):
    """Fallback if apps/_listes.py is missing: no list (the program never stops). Same interface as apps/_listes.py (French names, until that component is migrated)."""
    blanche, lieux, problemes, ancien, fichiers = [], [], [], False, {}
    def blanche_de(self, ip): return None
    def lieu(self, ip): return None
    def etiquette(self, ip): return ""
    def protegee(self, ip): return False
    def reseaux_ne_pas_bannir(self): return []
    def resume(self): return "Lists: component apps/_listes.py missing"


def lists():
    """Whitelist and places (/etc/default/nginx-tools-*.conf, apps/_listes.py), read once; the "Lists: …" line goes to the error output."""
    if _LISTS[0] is None:
        path = os.path.join(SCRIPT_DIR, "apps", "_listes.py")
        try:
            spec = importlib.util.spec_from_file_location("_listes", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _LISTS[0] = module.charger(os.path.join(SCRIPT_DIR, "apps"))
        except (OSError, AttributeError, ImportError):
            _LISTS[0] = EmptyLists()
        print(_LISTS[0].resume(), file=sys.stderr)
        for problem in _LISTS[0].problemes:
            print(f"  WARNING {problem}", file=sys.stderr)
    return _LISTS[0]


def network_text(network):
    """Single address ("203.0.113.10") or range ("203.0.113.0/28") as written in the lists."""
    return str(network.network_address) if network.prefixlen == network.max_prefixlen else str(network)


def team():
    """{address or range: label} of the addresses never to ban: whitelist (/etc/default/nginx-tools-white-list.conf) and places [protected]."""
    res = {}
    for e in lists().blanche:
        res[network_text(e.reseau)] = e.libelle or "team"
    for e in lists().lieux:
        if e.protegee:
            res.setdefault(network_text(e.reseau), e.libelle or "protected location")
    return res


def whitelist_captions():
    """{address: label}: team list, completed by the comments of the nginx "allow" rules."""
    res = {}
    for m in re.finditer(r"^\s*allow\s+([0-9a-fA-F:./]+)\s*;[ \t]*#[ \t]*(.+)$", run(["nginx", "-T"], timeout=30)[1], re.M):
        res.setdefault(m.group(1), m.group(2).strip())
    res.update(team())
    return res


def nginx_whitelist():
    code, out = run(["nginx", "-T"], timeout=30)
    return set(re.findall(r"^\s*allow\s+([0-9a-fA-F:./]+)\s*;", out, re.M)) if code == 0 else set()


def in_whitelist(ip):
    """IP of the nginx whitelist: exact address, or within a range (e.g. mobile phone with a dynamic address)."""
    if ip in WHITELIST:
        return True
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for e in WHITELIST:
        if "/" in e:
            try:
                if address in ipaddress.ip_network(e, strict=False):
                    return True
            except ValueError:
                pass
    return False


ROBOT_RE = re.compile(r"[A-Za-z0-9_.-]*(?:bot|crawler|spider|Bot|Crawler|Spider)[A-Za-z0-9_.-]*")
_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _open_log(path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.endswith(".gz") \
        else open(path, encoding="utf-8", errors="replace")


def _rotations(database):
    """Active file and all its rotations (.1, .2.gz…)."""
    return sorted(glob.glob(database) + glob.glob(database + ".*"))


def duration(n):
    """"1 day", "N days"."""
    return f"{n} day" if n == 1 else f"{n} days"


DAYS_GIVEN = False   # --days given explicitly (--list-users: otherwise the whole history)
DAYS = 30        # --days N: length of the long period of the summary and of --list-users (default: 30 days)


class Periods:
    """Windows: today (0), week (1: 7 days, or N if --days N < 7) and long period (2: DAYS days),
    today included — indices used everywhere —, then D-1 (3, yesterday) and D-2 (4, the day before yesterday), whole days.
    Display: self.order (columns that make no sense for a short period removed)."""
    N = 5

    def __init__(self, today, day_count=None):
        day_count = day_count or DAYS
        week = min(7, day_count)
        self.today = today
        one_day = datetime.timedelta(days=1)
        self.starts = (today, today - datetime.timedelta(days=week - 1), today - datetime.timedelta(days=day_count - 1),
                       today - one_day, today - 2 * one_day)
        self.ends = (today, today, today, today - one_day, today - 2 * one_day)
        self.names = ("Today", duration(week), duration(day_count), "J-1", "J-2")
        self.order = tuple(i for i in (0, 3, 4, 1, 2) if not (i == 3 and day_count < 2) and not (i == 4 and day_count < 3)
                           and not (i == 1 and day_count <= 7))

    def indices(self, d):
        return [i for i, (start, end) in enumerate(zip(self.starts, self.ends)) if d is not None and start <= d <= end]


class Tally:
    """Counters per period: numbers (add) and sets of distinct elements (add_distinct)."""
    def __init__(self):
        self.n, self.sets = {}, {}

    def add(self, key_value, idx, k=1):
        for i in idx:
            self.n[(key_value, i)] = self.n.get((key_value, i), 0) + k

    def add_distinct(self, key_value, idx, val):
        for i in idx:
            self.sets.setdefault((key_value, i), set()).add(val)

    def get(self, key_value, i):
        return len(self.sets[(key_value, i)]) if (key_value, i) in self.sets else self.n.get((key_value, i), 0)


class Source:
    """Coverage of a log: oldest date seen, number of files read."""
    def __init__(self, caption):
        self.libelle, self.oldest, self.files, self.byte_count = caption, None, 0, 0

    def count_item(self, path):
        self.files += 1
        try:
            self.byte_count += os.path.getsize(path)
        except OSError:
            pass

    def seen(self, d):
        if d is not None and (self.oldest is None or d < self.oldest):
            self.oldest = d


def logrotate_policy(display_name):
    """(frequency, number kept, days covered, path) of the first block of /etc/logrotate.d/<name>, or None."""
    path = os.path.join(LOGROTATE_DIR, display_name)
    try:
        text_value = open(path, encoding="utf-8").read()
    except OSError:
        return None
    freq = next((f for f in ("daily", "weekly", "monthly") if re.search(rf"^\s*{f}\b", text_value, re.M)), "weekly")
    m = re.search(r"^\s*rotate\s+(\d+)", text_value, re.M)
    n = int(m.group(1)) if m else 4
    day_count = n * {"daily": 1, "weekly": 7, "monthly": 30}[freq]
    return freq, n, day_count, path


def _systemd_journal_size(ns):
    """Space used by the systemd journal (namespace of the application if it exists, otherwise the whole journal)."""
    code, out = run(["journalctl"] + (["--namespace", ns] if ns else []) + ["--disk-usage"], timeout=30)
    m = re.search(r"take up ([\d.]+)\s*([KMGT]?)", out)
    if not m:
        return None
    return int(float(m.group(1)) * 1024 ** " KMGT".index(m.group(2) or " "))


def log_space(sources, svc, ns, today_date):
    """Disk space used by the logs, daily rate and projection at 3, 6 and 12 months, compared to the free space
    of the /var/log partition. Compressed rotations included: the projection follows the current mix."""
    print()
    print("LOG DISK SPACE")
    total, per_day = 0, 0.0
    for key_value, src in sources.items():
        byte_count = src.byte_count
        detail = ""
        if key_value == "odoo" and PROFILE.get("APP_LOG_KIND") == "journal":
            byte_count = _systemd_journal_size(ns) or 0
            detail = f" (journal {'« ' + ns + ' »' if ns else 'full systemd, all services'})"
        if not byte_count:
            continue
        day_count = max(1, (today_date - src.oldest).days + 1) if src.oldest else 1
        total += byte_count
        per_day += byte_count / day_count
        print(f"  {src.libelle:<30} {_bytes(byte_count):>10}  ≈ {_bytes(byte_count / day_count)}/day on {day_count} day(s){detail}")
    if not total:
        print("  no measurable log")
        return
    print(f"  {'Total':<30} {_bytes(total):>10}  ≈ {_bytes(per_day)}/day")
    try:
        disk = shutil.disk_usage("/var/log")
        free_amount = f" — /var/log partition: {_bytes(disk.free)} free of {_bytes(disk.total)}"
    except OSError:
        disk, free_amount = None, ""
    proj = {month: per_day * month * 30.5 for month in (3, 6, 12)}
    print("  Projection at a constant rate: " + " · ".join(f"{m} months ≈ {_bytes(v)}" for m, v in proj.items()) + free_amount)
    if disk and proj[12] > disk.free * 0.8:
        print(f"  {BAD}⚠ 12 months would exceed 80 % of the free space in /var/log.{END_BAD}")
    print("  Retention period: nginx-hardening.sh --update --log-retention-months N (3 by default).")


ODOO_CONF_CANDIDATES = ("/opt/odoo/erplibre/config.conf", "/home/utilisateur/git/erplibre/config.conf", "/etc/odoo/odoo.conf")
ODOO_DEFAULTS = {"workers": 0, "max_cron_threads": 2, "limit_memory_soft": 2048 << 20, "limit_memory_hard": 2560 << 20,
                "limit_time_cpu": 60, "limit_time_real": 120}


ODOO_OPTIONS = ("workers", "max_cron_threads", "limit_memory_soft", "limit_memory_hard", "limit_time_cpu", "limit_time_real")


def _line_options(args):
    """Odoo options of a command line — forms "--opt=val" AND "--opt val" (e.g. --limit-time-real 1200)."""
    res, config = {}, None
    for i, a in enumerate(args):
        display_name, _, val = a.partition("=")
        if not val and i + 1 < len(args) and not args[i + 1].startswith("-"):
            val = args[i + 1]
        if display_name in ("-c", "--config"):
            config = val or config
        elif display_name.startswith("--") and display_name[2:].replace("-", "_") in ODOO_OPTIONS and re.fullmatch(r"\d+", val or ""):
            res[display_name[2:].replace("-", "_")] = int(val)
    return res, config


def _odoo_processes(svc):
    """Command lines of the main process of the service and of its descendants (PROC_DIR: tests)."""
    proc = os.environ.get("PROC_DIR", "/proc")
    pid = run(["systemctl", "show", "-p", "MainPID", "--value", svc], timeout=20)[1].strip()
    if not pid.isdigit() or pid == "0":
        return []
    parents = {}
    for p in os.listdir(proc) if os.path.isdir(proc) else []:
        if p.isdigit():
            try:
                parents[p] = open(os.path.join(proc, p, "stat")).read().rsplit(")", 1)[1].split()[1]
            except (OSError, IndexError):
                pass
    family, to_see = [], [pid]
    while to_see:
        current = to_see.pop()
        family.append(current)
        to_see += [p for p, pp in parents.items() if pp == current and p not in family]
    text_lines = []
    for p in family:
        try:
            args = open(os.path.join(proc, p, "cmdline"), "rb").read().split(b"\0")
            text_lines.append([x.decode("utf-8", "replace") for x in args if x])
        except OSError:
            pass
    return text_lines


def _script_options(path, depth=0):
    """Options passed by a startup script (e.g. ERPLibre's run.sh), following a called script (odoo_bin.sh)."""
    res, config = {}, None
    try:
        text_value = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return res, config
    for text_line in text_value.splitlines():
        text_line = text_line.split("#", 1)[0] if not text_line.lstrip().startswith("#!") else ""
        if "--limit-" in text_line or "--workers" in text_line or "--max-cron-threads" in text_line or " -c " in text_line:
            try:
                o, c = _line_options(shlex.split(text_line))
            except ValueError:
                continue
            res.update(o)
            config = c or config
    return res, config


def odoo_config(svc):
    """(path, values, origin) of the Odoo configuration, in priority order: options of the RUNNING PROCESS (the
    values really applied), otherwise of the startup script (ExecStart, e.g. run.sh which calls odoo_bin.sh with
    --limit-…), then configuration file, then Odoo defaults. The command line overrides the file."""
    import configparser
    argv = run(["systemctl", "show", "-p", "ExecStart", svc], timeout=20)[1]
    m = re.search(r"argv\[\]=([^;]*)", argv)
    exec_args = shlex.split(m.group(1)) if m else []
    exec_opt, path = _line_options(exec_args)
    script_opt = {}
    for a in exec_args:
        if a.endswith(".sh") and os.path.isfile(a):
            o, c = _script_options(a)
            script_opt.update(o)
            path = path or c
    proc_opt = {}
    for args in _odoo_processes(svc):
        o, c = _line_options(args)
        if o or c:
            proc_opt.update(o)
            path = path or c
    if path and not os.path.isabs(path):                       # "-c ./config.conf": relative to the script folder
        database = next((os.path.dirname(a) for a in exec_args if a.endswith(".sh")), "")
        path = os.path.normpath(os.path.join(database, path)) if database else path
    path = path if path and os.path.isfile(path) else next((c for c in ODOO_CONF_CANDIDATES if os.path.isfile(c)), None)
    values, origin = dict(ODOO_DEFAULTS), {}
    if path:
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read(path, encoding="utf-8")
            for key_value in ODOO_DEFAULTS:
                if cp.has_option("options", key_value):
                    values[key_value] = int(float(cp.get("options", key_value)))
                    origin[key_value] = "file"
        except (configparser.Error, ValueError):
            pass
    for source, opts in (("startup script", script_opt), ("command line", exec_opt), ("running processes", proc_opt)):
        for key_value, val in opts.items():
            values[key_value] = val
            origin[key_value] = source
    return path, values, origin


def workers_advice(svc, c, mem_odoo, mem_pg):
    """Odoo worker configuration, worst-case memory, signs of saturation (30 days) and advice."""
    path, v, origin = odoo_config(svc)
    cores = os.cpu_count() or 1
    ram = _meminfo().get("MemTotal", 0)
    w, cron = v["workers"], v["max_cron_threads"]
    print()
    print(f"  Odoo (workers) — {path or 'configuration not found: Odoo default values'}")
    sources = {}
    for key_value, src in origin.items():
        if src != "file":
            sources.setdefault(src, []).append(key_value)
    for src, key_list in sources.items():                              # the command line overrides the file
        print(f"    (priority, {src} : {', '.join(key_list)})")
    print(f"    workers={w}, max_cron_threads={cron}, limit_memory_soft={_bytes(v['limit_memory_soft'])}, "
          f"limit_memory_hard={_bytes(v['limit_memory_hard'])}, limit_time_cpu={v['limit_time_cpu']} s, "
          f"limit_time_real={v['limit_time_real']} s")
    rec, cpu_kill, elapsed = (c.get(k, 2) for k in ("workers_memoire", "workers_cpu", "workers_temps"))
    print(f"    Signs of saturation ({DAYS} days): {rec} recycling(s) for memory · {cpu_kill} stop(s) for CPU time"
          f" · {elapsed} stop(s) for real time · {c.get('erreurs5xx', 2)} 5xx error(s)")
    notice = []
    if w == 0:
        processes = 1
        suggested = min(2 * cores + 1, max(2, int((ram * 0.7 - (mem_pg or 0)) // (400 << 20)))) if ram else 2 * cores + 1
        notice.append(f"multithread mode (workers=0): a single process serves the whole site. In production, Odoo recommends "
                    f"multiprocess mode: try workers={suggested} (≈ 400 MB per worker; Odoo's formula: "
                    f"2 × cores + 1 = {2 * cores + 1}), with proxy_mode = True behind nginx.")
    else:
        processes = w + cron + 2                       # + main process and gevent process (websocket)
        per_proc = (mem_odoo or 0) / processes
        worst = (w + cron) * v["limit_memory_hard"]
        unlimited = v["limit_memory_hard"] == 0
        print(f"    Measured memory: {_bytes(mem_odoo) if mem_odoo else 'n/d'} for ≈ {processes} processes"
              + (f" (≈ {_bytes(per_proc)} each)" if mem_odoo else "")
              + (" ; worst case: UNLIMITED (limit_memory_hard=0)" if unlimited else
                 f" ; worst case (limit_memory_hard × {w + cron} workers and crons): {_bytes(worst)} for {_bytes(ram)} of RAM"))
        if unlimited:
            notice.append("limit_memory_hard=0: NO memory limit — a single runaway worker (report, import, loop) can use all of the server's RAM and get random processes killed (OOM), PostgreSQL included. Apply the value suggested by nginx-hardening.sh --check (step 6), in run.sh if it passes --limit-memory-hard on the command line.")
        elif ram and worst > ram * 0.9:
            safe_limit = int(ram * 0.8 // (w + cron))
            notice.append(f"worst-case memory exceeds the RAM: if several workers grew together, the kernel would kill "
                        f"processes (OOM). Lower limit_memory_hard to {_bytes(safe_limit)} (and limit_memory_soft to ≈ 80% "
                        f"of that value) — see also nginx-hardening.sh, step 6.")
        if elapsed or cpu_kill:
            notice.append("requests exceed limit_time_real / limit_time_cpu: find which ones in the journal (reports, exports, heavy imports) before raising these limits.")
        if rec > 30:
            notice.append(TR("workers often recycled for memory ({rec} in {days} days): raise limit_memory_soft by about 25% if the RAM allows it.").format(rec=rec, days=DAYS))
        if w > 2 * cores + 1:
            notice.append(TR("more workers ({w}) than Odoo's formula (2 × {cores} cores + 1 = {formula}): no gain, the processes compete for the CPU.").format(
                w=w, cores=cores, formula=2 * cores + 1))
    if not notice:
        notice.append("no sign of saturation: the current limits do not hinder Odoo. Low RAM usage does not call for raising the limits — they cost nothing until they are reached. Add workers only if slowness or 502/504 errors appear at peak hours (e.g. during an event).")
    for a in notice:
        print(f"    → {a}")


# ------------------------------------------------------------------------------------------------------------------
# Diagnoses and fixes made BY THE PROGRAM (2.36): a recommendation no longer points to a command to type.
# The checks without side effects (nginx -T, investigation of an IP, trial of a URL through nginx, robots.txt) are made
# during the summary and their result is written in the recommendation; the fixes that modify the server
# (nginx reload, ban, nginx-hardening.sh --update, timer, fail2ban) are offered at the end of the summary,
# with confirmation (--apply --yes: without question).
# ------------------------------------------------------------------------------------------------------------------
_NGINX_T = {}
NGINX_TIME_RE = re.compile(r"\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})\]")


def nginx_hour(text_line):
    """Instant (epoch) of an nginx log line, or None."""
    m = NGINX_TIME_RE.search(text_line)
    if not m or m.group(2) not in _MONTHS:
        return None
    try:
        offset = (1 if m.group(7) == "+" else -1) * datetime.timedelta(hours=int(m.group(8)), minutes=int(m.group(9)))
        return datetime.datetime(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)),
                                 int(m.group(6)), tzinfo=datetime.timezone(offset)).timestamp()
    except ValueError:
        return None


def hm(t):
    return time.strftime("%H:%M", time.localtime(t))


def nginx_T():
    """Output of "nginx -T" (complete configuration), read only once per summary."""
    if "t" not in _NGINX_T:
        _NGINX_T["t"] = run(["nginx", "-T"], timeout=30)[1]
    return _NGINX_T["t"]


def deny_rules(text_value):
    """Deny directives of the configuration (return 403, deny, User-Agent test), "file:line « directive »"."""
    file_path, n, found_items, in_format = "?", 0, [], False
    for text_line in text_value.splitlines():
        m = re.match(r"# configuration file (.+?):\s*$", text_line)
        if m:
            file_path, n, in_format = m.group(1), 0, False
            continue
        n += 1
        directive = text_line.split("#", 1)[0].strip()
        if re.match(r"log_format\b", directive):             # log format ("$http_user_agent" in quotes, over several lines): not a deny rule
            in_format = True
        if in_format:
            in_format = not directive.endswith(";")
            continue
        if directive and re.search(r"return\s+403|\bdeny\s|\$http_user_agent", directive):
            found_items.append(f"{file_path}:{n} « {directive[:90]} »")
    return found_items


def priority_locations(text_value, path):
    """"location = X" or "location ^~ X" blocks that catch this path BEFORE the regex locations (security rules)."""
    file_path, n, found_items = "?", 0, []
    for text_line in text_value.splitlines():
        m = re.match(r"# configuration file (.+?):\s*$", text_line)
        if m:
            file_path, n = m.group(1), 0
            continue
        n += 1
        m = re.match(r"\s*location\s+(=|\^~)\s+(\S+)\s*\{?", text_line)
        if m and ((m.group(1) == "=" and path == m.group(2)) or (m.group(1) == "^~" and path.startswith(m.group(2)))):
            found_items.append(f"{file_path}:{n} « location {m.group(1)} {m.group(2)} »")
    return found_items


def regex_locations(text_value, path):
    """"location ~ / ~* EXPRESSION" rules of nginx -T whose expression matches this path (evaluated here, same PCRE
    syntax for our rules): "file:line « location ~* … »". Empty = NO rule of the configuration targets this path."""
    file_path, n, found_items = "?", 0, []
    for text_line in text_value.splitlines():
        m = re.match(r"# configuration file (.+?):\s*$", text_line)
        if m:
            file_path, n = m.group(1), 0
            continue
        n += 1
        m = re.match(r"""\s*location\s+(~\*?)\s+("[^"]*"|'[^']*'|[^\s{]+)\s*\{?""", text_line)
        if not m:
            continue
        expression = m.group(2).strip("\"'")
        try:
            if re.search(expression, path, re.I if m.group(1) == "~*" else 0):
                found_items.append(f"{file_path}:{n} « location {m.group(1)} {expression[:60]} »")
        except re.error:
            continue
    return found_items


def leak_cause(text_value, pass_through):
    """Why nginx lets these paths through, according to its active configuration (nginx -T): (text, missing_rule?).
    Three cases: a priority location (= or ^~) catches them; a rule matches but is not applied; NO rule
    targets them (the server block is correct, the rule is what is missing)."""
    captured = sorted({loc for x in pass_through for loc in priority_locations(text_value, x[0])})
    if captured:
        return " — caught before the rules by: " + " ; ".join(captured[:4]), False
    if not text_value.strip():
        return " — nginx configuration unreadable (nginx -T): cause undetermined", False
    no_rule = [x[0] for x in pass_through if not regex_locations(text_value, x[0])]
    if no_rule:
        return (" — NO rule in nginx -T targets " + ", ".join(no_rule[:4])
                + (" …" if len(no_rule) > 4 else "") + " : the server block is correct, a rule is MISSING (e.g. wp-admin / wp-login in a « return 404 » rule of snippets/securite-commune.conf, shipped in nginx-odoo-config)"), True
    examples = sorted({loc for x in pass_through for loc in regex_locations(text_value, x[0])})
    return (" — rules target them (" + " ; ".join(examples[:3]) + ") but nginx still responds: the server block serving this name does not include them, or another location comes first"), False


def nginx_loaded_since():
    """Instant (epoch) of the last load of the nginx configuration: start of the current workers (a reload
    replaces them; those "is shutting down" are ignored). None if it cannot be determined."""
    proc = os.environ.get("WEB_MONITOR_PROC_DIR", "/proc")
    try:
        with open(os.path.join(proc, "stat")) as f:
            btime = next(int(l.split()[1]) for l in f if l.startswith("btime"))
        tck = os.sysconf("SC_CLK_TCK")
        pids = [x for x in os.listdir(proc) if x.isdigit()]
    except (OSError, StopIteration, ValueError):
        return None
    starts = []
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            if cmd != "nginx: worker process":
                continue
            with open(os.path.join(proc, pid, "stat")) as f:
                start = int(f.read().rsplit(")", 1)[1].split()[19])
        except (OSError, ValueError, IndexError):
            continue
        starts.append(btime + start / tck)
    return min(starts) if starts else None


def read_page(path, host_value=None):
    """GET through nginx on this server (127.0.0.1:443, Host header of the site, User-Agent of our tests: excluded from
    the figures). (status, body); status 444 if nginx closes the connection without a response; None if impossible."""
    mod = load_sanity_module()
    if not mod or not hasattr(mod, "Http"):
        return None
    if not host_value:
        try:
            host_value = mod.load_config(mod.resolve_config_paths(None)).get("ODOO_PUBLIC_HOST")
        except Exception:
            host_value = None
    try:
        status_code, _, body_text = mod.Http("127.0.0.1", 443, host_value or socket.getfqdn(), False, timeout=8).request("GET", path)
        return status_code, body_text if isinstance(body_text, bytes) else str(body_text).encode()
    except Exception as e:
        if type(e).__name__ in ("RemoteDisconnected", "BadStatusLine"):     # 444: connection closed without a response
            return 444, b""
        return None


def probe(targets):
    """Tries each (path, name) through nginx: [(path, status, bytes, refused by nginx: True/False/None)]."""
    res = []
    for path, host_value in targets:
        r = read_page(path, host_value)
        if r is None:
            res.append((path, None, 0, None))
        else:
            res.append((path, r[0], len(r[1]), r[0] in (400, 403, 404, 444) and len(r[1]) < NGINX_404_SIZE))
    if res and all(x[3] is None for x in res):
        return None
    return res


def probe_text(results):
    return ", ".join(f"{c} → {s if s is not None else 'no response'}" + (f" ({o} o)" if s not in (None, 444) else "")
                     for c, s, o, _ in results)


def investigate_ip(ip):
    """Investigation by nginx-log-audit.sh --investigate (without question): (conclusion, ban recommended?)."""
    nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
    if not os.path.isfile(nla):
        return None, False
    app = ["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []
    _, out = run(["bash", nla, "--investigate", ip, "--no-prompt"] + app + verbose_args(), timeout=300)
    verdict = next((l.strip()[1:].strip() for l in out.splitlines() if l.strip().startswith("→ Score")), "")
    return (verdict or None), "bannissement recommandé" in verdict


def add_action(caption, command, func):
    """Fix that the program will make itself at the end of the summary (only once per command)."""
    for i, (lib, cmd, f) in enumerate(ACTIONS):
        if cmd == command:                            # same command: a single launch, labels merged
            if caption.lower() not in lib.lower():
                ACTIONS[i] = (f"{lib} ; {caption[:1].lower()}{caption[1:]}", cmd, f)
            return
    ACTIONS.append((caption, command, func))


def run_tool(display_name, *arguments):
    """Runs a tool of the suite, output displayed as is; return code."""
    path = os.path.join(SCRIPT_DIR, display_name)
    if not os.path.isfile(path):
        print(f"{display_name} not found next to this program.")
        return 1
    app = ["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []
    interpreted = [sys.executable] if display_name.endswith(".py") else ["bash"]
    with foreground_child():                       # 2.66: the program owns the terminal: Ctrl-C (and its confirmation) are its own
        return subprocess.run(interpreted + [path] + list(arguments) + app + verbose_args()).returncode


def reload_nginx():
    code, out = run(["nginx", "-t"], timeout=30)
    if code != 0:
        print(f"{BAD}nginx -t rejects the configuration: nginx NOT reloaded.{END_BAD}\n" + out.strip())
        return 1
    code, out = run(["systemctl", "reload", "nginx"], timeout=60)
    print("nginx reloaded (nginx -t succeeded)." if code == 0 else f"{BAD}nginx reload failed:{END_BAD} {out.strip()}")
    return code


def start_fail2ban():
    code, out = run(["systemctl", "enable", "--now", "fail2ban"], timeout=60)
    print("fail2ban enabled and started." if code == 0 else f"{BAD}fail2ban start failed:{END_BAD} {out.strip()}")
    return code


def leak_diagnosis_bbb(rules, day, today_date):
    """BigBlueButton, rules installed, malicious requests passed today: (forced priority or None,
    explanation). Checks in order: nginx reloaded since the installation? file included (nginx -T)? requests
    after the entry into force? does nginx still let them through (real test)?"""
    installed = os.path.getmtime(rules)
    load_time = nginx_loaded_since()
    text_value = nginx_T()
    if load_time is not None and installed > load_time + 1:
        add_action("Reload nginx to apply the BigBlueButton security rules",
                       "nginx -t && systemctl reload nginx", reload_nginx)
        return None, (f"checked by the program: rules installed at {hm(installed)}, but nginx has not been reloaded since "
                      f"(configuration loaded at {hm(load_time)}) — they do not apply yet; reload offered "
                      "at the end of the summary")
    if text_value.strip() and f"# configuration file {rules}:" not in text_value:
        return None, (f"checked by the program: {rules} is missing from nginx -T — the BigBlueButton configuration does not include "
                      "/etc/bigbluebutton/nginx/*.nginx, so the rules do not apply (BBB server block to examine; its files are never modified by our tools)")
    start = max(installed, load_time or 0)
    after = [x for x in day if x[0] is not None and x[0] >= start]
    if day and not after:
        trial = probe([("/.env", None), ("/.git/config", None)])
        confirmed = ""
        if trial and all(x[3] for x in trial):
            confirmed = f", and nginx now refuses {probe_text(trial)}"
        elif trial and any(x[3] is False for x in trial):
            return None, TR("the {count} from today predate the rules taking effect ({time}), BUT nginx still lets through {probes} (program test)").format(
                count=fmt(today_date), time=hm(start), probes=probe_text([x for x in trial if x[3] is False]))
        return 3, TR("checked by the program: all {count} from today predate the rules taking effect ({time}); none since{confirmed}. "
                     "Nothing to do: the counter will drop back to zero within 7 days").format(count=fmt(today_date), time=hm(start), confirmed=confirmed)
    account = {}
    for _, url, host_value in after or day:
        account[(url, host_value)] = account.get((url, host_value), 0) + 1
    tops = [k for k, _ in sorted(account.items(), key=lambda x: -x[1])[:5]] or [("/.env", ""), ("/.git/config", "")]
    since = f"{fmt(len(after))} since the rules took effect ({hm(start)})" if after else f"{fmt(today_date)} today"
    trial = probe([(u, h or None) for u, h in tops])
    if trial is None:
        return None, (f"{since} : " + ", ".join(u for u, _ in tops) + " — test through nginx impossible (app-health-check.py missing next to this program)")
    pass_through = [x for x in trial if x[3] is False]
    if pass_through:
        cause_text, _ = leak_cause(text_value, pass_through)
        return None, (f"checked by the program: {since}, and nginx still lets through {probe_text(pass_through)}{cause_text}")
    return None, (f"{since} ({', '.join(u for u, _ in tops)}), but nginx refuses them when the program tries them "
                  f"({probe_text(trial)}): passed through another path (requested name: "
                  + (", ".join(sorted({h for _, h in tops if h})) or "unknown") + "); to watch")


def leak_diagnosis_odoo(day, today_date, last_one, per_name):
    """Odoo (or any application with securite-commune.conf): real test through nginx instead of pointing to
    app-health-check.py. (forced priority or None, explanation)."""
    if today_date == 0:
        trial = probe([(c, None) for c in ("/.env", "/en_CA/.env", "/.git/config")])
        if trial and all(x[3] for x in trial):
            return 3, (f"none today (last on {last_one}); checked by the program: nginx now refuses "
                       f"{probe_text(trial)} (minimal nginx response). Nothing to do: the counter will drop back to zero within 7 days")
        if trial:
            pass_through0 = [x for x in trial if x[3] is False]
            cause_text, _ = leak_cause(nginx_T(), pass_through0)
            return None, (f"none today (last on {last_one}), but nginx still lets through "
                          f"{probe_text(pass_through0)} (program test)" + cause_text)
        return None, (f"none today (last on {last_one}): probably predate the current nginx rules "
                      "(test through nginx impossible: app-health-check.py missing)")
    account = {}
    for _, url, host_value in day:
        account[(url, host_value)] = account.get((url, host_value), 0) + 1
    tops = [k for k, _ in sorted(account.items(), key=lambda x: -x[1])[:5]] or [(c, "") for c in ("/.env", "/.git/config")]
    trial = probe([(u, h or None) for u, h in tops])
    if trial is None:
        return None, (f"{fmt(today_date)} still today — test through nginx impossible (app-health-check.py missing)."
                      + per_name)
    pass_through = [x for x in trial if x[3] is False]
    if not pass_through:
        return None, (f"{fmt(today_date)} still today, but nginx now refuses these URLs when the program "
                      f"tries ({probe_text(trial)}): predate the current configuration or went through another name."
                      + per_name)
    cause_text, _ = leak_cause(nginx_T(), pass_through)
    return None, (f"{fmt(today_date)} still today; checked by the program: nginx still lets through "
                  f"{probe_text(pass_through)}" + cause_text + "." + per_name)


def investigate_403(ip, n, facts):
    """Investigation made by the program on an address that accumulates 403 refusals; recommended → ban proposed."""
    if (facts.get("bannies") or {}).get(ip) == "banni":
        return f"{ip} already banned, nothing to do"
    if in_whitelist(ip) or ip in SERVER:
        return f"{ip} : team or this server's address, never banned"
    verdict, recommended_flag = investigate_ip(ip)
    if verdict is None:
        return f"{ip} : investigation impossible (nginx-log-audit.sh missing or inconclusive)"
    if recommended_flag and ip not in [r[0] for r in RECOMMENDED]:
        RECOMMENDED.append((ip, TR(f"{fmt(n)} browser 403 refusals in {DAYS} days; investigation: {verdict}")))
    return f"{ip} : {verdict}" + (" — ban offered at the end of the summary" if recommended_flag else "")


def other_addresses(ips, facts):
    """Among these refused addresses, those that ALSO got normal pages (real visitors refused at times)."""
    if "ips_2xx" not in facts or not ips:
        return ""
    ok = sum(1 for i in ips if i in facts["ips_2xx"])
    return (f"checked by the program: {fmt(ok)} also got normal pages (real visitors refused at times, "
            f"to examine) and {fmt(len(ips) - ok)} received only refusals (probably robots). ")


def deny_rules_text():
    """Deny rules of the nginx configuration, collected by the program (no more "nginx -T | grep" to type)."""
    text_value = nginx_T()
    if not text_value.strip():
        return "nginx configuration unreadable (nginx -T): deny rules not collected."
    rules = deny_rules(text_value)
    if not rules:
        return "No « return 403 », « deny » rule or User-Agent test in nginx -T: the refusal comes from the application."
    return ("Deny rules found in nginx -T: " + " ; ".join(rules[:5])
            + (f" … (+{len(rules) - 5})" if len(rules) > 5 else "") + ".")


def robots_state():
    """robots.txt of the server read by the program: "Disallow: /" present?"""
    r = read_page("/robots.txt")
    if r is None:
        return "robots.txt not checked (app-health-check.py missing next to this program)"
    status_code, body_text = r
    text_value = body_text.decode("utf-8", "replace")
    if status_code == 200 and re.search(r"(?im)^\s*Disallow:\s*/\s*$", text_value):
        return "robots.txt checked by the program: « Disallow: / » present — nothing to do, the robot will space out its visits"
    return (f"robots.txt checked by the program: status {status_code}, « Disallow: / » ABSENT"
            + (f" (content: {' | '.join(l.strip() for l in text_value.splitlines() if l.strip())[:120]})" if text_value.strip() else "")
            + " — put « User-agent: * » then « Disallow: / » in it so that it stops coming back")


def app_log_check_summary():
    """Application-side causes of the 5xx errors: app-log-check.py launched by the program, its SUMMARY line."""
    path = os.path.join(SCRIPT_DIR, "app-log-check.py")
    if not os.path.isfile(path):
        return "app-log-check.py missing next to this program: application-side causes not collected"
    svc, ns = detect_odoo_service() if PROFILE.get("APP_LOG_KIND") == "journal" else (None, "")
    cmd = [sys.executable, path] + (["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []) \
        + (["--service", svc] if svc else []) + (["--namespace", ns] if ns else []) + verbose_args()
    with tempfile.TemporaryDirectory() as state:          # separate read position: manual runs stay intact
        _, out = run(cmd, env_extra={"APP_LOG_CHECK_STATE_DIR": state}, timeout=300)
    summary = next((l.strip() for l in out.splitlines() if "RÉSUMÉ" in l), "")
    entries = [l.strip() for l in out.splitlines() if re.match(r"\s*\[\d+x\]", l)][:3]
    return ("app-log-check.py run by the program: " + (summary or "no summary")
            + (" — " + " | ".join(entries) if entries else ""))


def backup_state():
    """State of the backups read by the program (odoo-backup.sh --status), instead of pointing to the command."""
    path = os.path.join(SCRIPT_DIR, "odoo-backup.sh")
    if not os.path.isfile(path):
        return "odoo-backup.sh missing next to this program"
    code, out = run(["bash", path, "--status"] + verbose_args(), timeout=60)
    useful = [l.strip() for l in out.splitlines() if re.search(r"ÉCHEC|échec|erreur|timer|dernière|⚠", l, re.I)][:4]
    return "odoo-backup.sh --status run by the program: " + (" | ".join(useful) or out.strip()[-300:] or f"code {code}")


# --- IPs banned WRONGLY (2.59): a valid banned IP is a visitor, a team member or a user who can no longer get in -------------------
def current_bans(manual):
    """{ip: [sources]} of the currently banned IPs: manual bans (nginx-log-audit.sh journal), fail2ban jails (fail2ban-client status JAIL)."""
    res = {ip: ["manuel"] for ip in manual}
    code, output = run(["fail2ban-client", "status"], timeout=20)
    if code == 0:
        jails = [j.strip() for j in re.sub(r".*Jail list:", "", output, flags=re.S).split(",") if j.strip()]
        for jail in jails:
            code_j, j_output = run(["fail2ban-client", "status", jail], timeout=20)
            m = re.search(r"Banned IP list:\s*(.*)", j_output) if code_j == 0 else None
            for ip in (m.group(1).split() if m else []):
                res.setdefault(ip, []).append("fail2ban:" + jail)
    return res


def valid_reason(ip, facts):
    """(certainty, reason) if this IP looks valid, otherwise None: whitelist and known user = "certain"; human visitor (CSS/JS loaded, at least 2 pages
    viewed, no malicious URL requested) = "probable"."""
    bad = ip in facts.get("ips_mal", ())
    if in_whitelist(ip):
        return ("certain", "allowlist (team)" + (" — also requested malicious URLs" if bad else ""))
    if ip in facts.get("ips_connues", ()):
        return ("certain", "known user (successful Odoo login)" + (" — also requested malicious URLs" if bad else ""))
    pages = (facts.get("pages_ip") or {}).get(ip, 0)
    if ip in facts.get("ips_humaines", ()) and pages >= 2 and not bad:
        return ("probable", f"probable human visitor: {pages} page(s) viewed, CSS/JS loaded, no malicious URL")
    return None


def ips_to_unban(facts, manual):
    """Sorted list [(ip, certainty, reason, [ban sources])] of the banned IPs that look valid, including in the CrowdSec community list."""
    banned = current_bans(manual)
    candidates = {ip for ip in set(banned) | set(facts.get("ips_connues", ())) | set(facts.get("ips_humaines", ())) if valid_reason(ip, facts)}
    for ip in candidates:
        for display_name in ("crowdsec-blocklist-v4", "crowdsec-blocklist-v6"):
            if (":" in ip) != display_name.endswith("v6"):
                continue
            if shutil.which("ipset") and run(["ipset", "test", display_name, ip], timeout=10)[0] == 0:
                banned.setdefault(ip, []).append("crowdsec")
    res = []
    for ip in sorted(candidates):
        if ip in banned:
            certainty, reason = valid_reason(ip, facts)
            res.append((ip, certainty, reason, banned[ip]))
    return sorted(res, key=lambda x: (x[1] != "certain", x[0]))


def unban_command(ip, source):
    """Command (displayed, and executed by unban) that lifts a ban."""
    if source.startswith("fail2ban:"):
        return ["fail2ban-client", "set", source.split(":", 1)[1], "unbanip", ip]
    if source == "crowdsec":
        return ["ipset", "del", "crowdsec-blocklist-v6" if ":" in ip else "crowdsec-blocklist-v4", ip]
    return ["bash", os.path.join(SCRIPT_DIR, "nginx-log-audit.sh"), "--unban", ip] + (["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else [])


def unban(items):
    """Lifts every ban of the list ips_to_unban; returns the number of successful commands."""
    n = 0
    for ip, _certainty, _reason, sources in items:
        for source in sources:
            code, output = run(unban_command(ip, source), timeout=60)
            n += code == 0
            print(f"  {ip} ({source}) : {'unbanned' if code == 0 else BAD + 'NOT lifted' + END_BAD + ' — ' + output.strip()[-120:]}")
    print("A ban from the CrowdSec community list comes back at the next synchronization: for a valid visitor, add the address to /etc/default/nginx-tools-white-list.conf.")
    return n


def show_unbans(to_unban):
    """Summary section: banned IPs that look valid, with the reason and the command that lifts the ban."""
    print()
    print("BANNED IPs THAT LOOK VALID (to unban)")
    if not to_unban:
        print("  none: every banned IP is unknown to the allowlist, to known users and to human visitors")
        return
    for ip, certainty, reason, sources in to_unban:
        print(f"  {BAD if certainty == 'certain' else ''}{ip:<18}{END_BAD if certainty == 'certain' else ''} {certainty:<9} {reason}")
        print(f"      banned by {', '.join(sources)} — lift with: " + " ; ".join(shlex.join(unban_command(ip, x)) for x in sources))


def show_logins(svc):
    """Connections to Odoo against their limits (apps/_connexions.py: chat / websocket, HTTP, PostgreSQL, nginx): a line of figures; returns the findings (level, finding, parameter)."""
    conf_path = PROFILE.get("ODOO_CONF")
    modules = {}
    for display_name in ("_connexions", "_odoo_conf"):
        path = os.path.join(SCRIPT_DIR, "apps", display_name + ".py")
        if not os.path.isfile(path):
            return []
        spec = importlib.util.spec_from_file_location(display_name, path)
        modules[display_name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modules[display_name])
    if PROFILE.get("APP_NAME") == "bbb" or not conf_path:
        return []
    try:
        measures = modules["_connexions"].mesurer(modules["_odoo_conf"].lire(conf_path), lambda key_value: modules["_odoo_conf"].valeur(conf_path, key_value))
        findings = modules["_connexions"].diagnostiquer(measures, service=svc or "odoo.service")
    except Exception:  # noqa: BLE001 - a measurement that is impossible does not stop the summary
        return []
    text_line = modules["_connexions"].resume(measures)
    if text_line:
        print(f"  Connections  : {text_line}")
    return findings


def offer_fixes():
    """End of the summary: make the proposed fixes (bans, reload, tools). Root required; one question
    per fix in a terminal; --apply --yes: all without question; otherwise (report, no terminal), the command."""
    if not (ACTIONS or RECOMMENDED):
        return 0
    if os.geteuid() != 0:
        print("\nFixes not made: root required (sudo web-monitor.py --apply).")
        if not NO_PROMPT and sys.stdin.isatty() and sys.stdout.isatty() and shutil.which("sudo"):       # 2.59: offer to rerun with sudo (one question per fix)
            try:
                rep = input("Relaunch now with sudo to make these fixes (one question per fix)? [y/N]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return 0
            if rep in ("o", "oui", "y", "yes"):
                arguments = [a for a in sys.argv if a != "--apply"] + ["--apply"]
                os.execvp("sudo", ["sudo", sys.executable] + arguments)
        return 0
    if APPLY and YES:
        if RECOMMENDED:
            ban(RECOMMENDED, choose=False)
        for lib, cmd, func in ACTIONS:
            print(f"\n{'=' * 70}\n{lib} ({cmd})")
            func()
        return 0
    if NO_PROMPT or not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("\nFor the program to make these fixes: web-monitor.py --apply (one question per fix) or web-monitor.py --apply --yes (no questions).")
        return 0
    if RECOMMENDED:
        ask_ban(RECOMMENDED)
    for lib, cmd, func in ACTIONS:
        try:
            rep = input(f"\n{lib} ({cmd}) — do it now? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nRemaining fixes not made.")
            return 0
        if rep in ("o", "oui", "y", "yes"):
            func()
        else:
            print("Not done.")
    return 0


def candidate_package(display_name):
    """Candidate version of a package according to "apt-cache policy"; None if apt is absent or does not know the package."""
    code, output = run(["apt-cache", "policy", display_name], timeout=30)
    m = re.search(r"Candidate:\s*(\S+)", output) if code == 0 else None
    return m.group(1) if m and m.group(1) != "(none)" else None


def install_geoip():
    code, output = run(["apt-get", "install", "-y", "geoip-bin", "geoip-database"], timeout=900)
    print("geoip-bin and geoip-database installed: the country of IP addresses is read locally." if code == 0
          else f"{BAD}geoip-bin installation failed (code {code}) :{END_BAD} {output.strip()[-300:]}")
    return code


def recommendations(c, facts, policies):
    """Recommendations ranked by importance, deduced from the summary figures (period: 7 days).
    Each entry: (priority 1 high / 2 medium / 3 low, finding, why, how)."""
    R = []
    _NGINX_T.clear()                                   # configuration reread on every summary
    ACTIONS.clear()
    app = PROFILE.get("APP_LABEL", "l'application")
    bbb = PROFILE.get("APP_NAME") == "bbb"
    g = lambda k: c.get(k, 1)
    passed_on, suspicious = g("transmises"), g("transmises_suspectes")
    part = 100 * suspicious / passed_on if passed_on else 0
    if suspicious > 100:
        examples = ", ".join(u for u, _ in sorted(facts["non_filtrees"].items(), key=lambda x: -x[1])[:3])
        today_date = c.get("transmises_suspectes", 0)
        last_one = facts.get("non_filtrees_derniere", "?")
        hosts = facts.get("non_filtrees_hotes") or {}
        per_name = (" Names concerned: " + ", ".join(f"{h} ({fmt(n)})" for h, n in sorted(hosts.items(), key=lambda x: -x[1])[:3])
                   + " — this is the server block of that name that needs fixing.") if hosts else ""
        bbb_rules = os.path.join(os.environ.get("NGINX_HARDENING_BBB_NGINX_DIR", "/etc/bigbluebutton/nginx"),
                                  "zz-nginx-hardening-security.nginx")
        day = facts.get("non_filtrees_jour") or []
        forced_prio = None
        if bbb and not os.path.isfile(bbb_rules):
            add_action("Install the BigBlueButton security rules and the nginx-blocked-probes jail",
                           "nginx-hardening.sh --update", lambda: run_tool("nginx-hardening.sh", "--update"))
            comment = ("fix offered at the end of the summary — nginx-hardening.sh --update: it installs " + bbb_rules
                       + " (our own file, included by BigBlueButton in its server block, never overwritten by its updates; BBB files untouched) and the nginx-blocked-probes jail")
        elif bbb and today_date == 0:
            comment = None                             # rules in place, none today: earlier requests
        elif bbb:
            forced_prio, comment = leak_diagnosis_bbb(bbb_rules, day, today_date)
        else:
            forced_prio, comment = leak_diagnosis_odoo(day, today_date, last_one, per_name)
        if comment is not None:
            R.append((forced_prio or (1 if part > 5 else 2), f"{fmt(suspicious)} malicious requests ({examples}…) reached {app} in 7 days "
                      f"({part:.0f} % of the forwarded traffic)",
                      f"nginx should refuse them itself: each one needlessly ties up {app} and tells the attacker what exists",
                      comment))
    for level, finding, advice in facts.get("connexions") or []:
        R.append((1 if level == "crit" else 2, f"connection limit close: {finding}", "beyond the limit, new connections (Odoo chat, pages, database) are refused", f"setting to change: {advice}"))
    to_unban = facts.get("a_debannir") or []
    if to_unban:
        certain_ones = [x for x in to_unban if x[1] == "certain"]
        add_action(f"Unban {len(to_unban)} valid IP(s)", "debannir", lambda: unban(to_unban))
        R.append((1 if certain_ones else 2, f"{len(to_unban)} banned IP(s) look valid ({len(certain_ones)} certain: team or known user): {', '.join(x[0] for x in to_unban[:5])}",
                  "a person who can no longer reach the site is a costlier false positive than one more robot",
                  "lifting offered at the end of the summary (commands in the « Banned IPs that look valid » section)"))
    # LOADED jails (fail2ban-client status), not only those that already banned: a new jail counts.
    code_f2b, f2b_output = run(["fail2ban-client", "status"], timeout=20)
    loaded = [j.strip() for j in re.sub(r".*Jail list:", "", f2b_output, flags=re.S).split(",")] if code_f2b == 0 else []
    if code_f2b != 0 and (facts["jails"] or g("fichiers_sensibles") > 50):
        add_action("Enable and start fail2ban", "systemctl enable --now fail2ban", start_fail2ban)
        R.append((1, "fail2ban does not respond (stopped?): no jail is active",
                  "without fail2ban, no scanner or password attempt is banned",
                  "start offered at the end of the summary (systemctl enable --now fail2ban)"))
    jails_web = [j for j in set(facts["jails"]) | set(loaded) if j.startswith("nginx")]
    if code_f2b == 0 and not jails_web and g("fichiers_sensibles") > 50:
        add_action("Install the nginx-blocked-probes jail (and the security rules)", "nginx-hardening.sh --update",
                       lambda: run_tool("nginx-hardening.sh", "--update"))
        R.append((1, f"no fail2ban jail bans web scanners ({fmt(g('fichiers_sensibles'))} requests for sensitive files in 7 days)",
                  "a scanner can try hundreds of URLs without ever being blocked",
                  "fix offered at the end of the summary — nginx-hardening.sh --update: it installs the nginx-blocked-probes jail" + (
                      " and the rules /etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx (BBB files untouched)"
                      if bbb else " (with the rules of securite-commune.conf from nginx-odoo-config.zip)")))
    ok, detail = _certificate_via_health()
    if ok is False:
        cause_text = "certbot missing: check renewal according to the tool in use"
        if shutil.which("certbot"):
            code_cb, cb_output = run(["certbot", "renew", "--dry-run"], timeout=180)
            error_list = [l.strip() for l in cb_output.splitlines() if re.search(r"error|fail|échec|problem", l, re.I)]
            cause_text = ("renewal test succeeded (certbot renew --dry-run, run by the program): the next automatic renewal should go through; check that the certbot timer is active"
                     if code_cb == 0 else "renewal test failed (certbot renew --dry-run, run by the program): "
                     + (" | ".join(error_list[-3:]) or cb_output.strip()[-300:]) + " — fix the cause (DNS, port 80, firewall)")
        R.append((1, f"TLS certificate: {detail}", "when it expires, all browsers refuse the site", cause_text))
    for point in sorted({"/", "/var/log", "/opt"}):
        if os.path.isdir(point):
            disk = shutil.disk_usage(point)
            if disk.total and disk.free / disk.total < 0.15:
                R.append((1, f"disk {point} almost full ({100 * disk.free / disk.total:.0f} % free)",
                          "a full partition stops the database and the logs", "free up space or enlarge the disk"))
    robots = facts["robots"]
    engines = {k: v for k, v in robots.items() if re.search(r"Googlebot|bingbot|Applebot|DuckDuckBot", k, re.I)}
    if engines and sum(engines.values()) > 100:
        display_name, n = max(engines.items(), key=lambda x: x[1])
        pages_m = facts.get("refus_robots_chemins", {}).get(display_name, {})
        requested = ("Pages requested: " + ", ".join(f"{u} ({fmt(c)})" for u, c in sorted(pages_m.items(), key=lambda x: -x[1])[:3])
                     + ". ") if pages_m else ""
        if bbb:
            # A meetings server (room links /rooms/…/join) has no reason to be indexed: the refusal is intended.
            R.append((3, f"{display_name} is trying to index this BigBlueButton server: {fmt(n)} 403 refusals in {DAYS} days",
                      "a meeting server has no reason to be indexed (room links): the refusal is intended; the only cost is that the robot keeps coming back",
                      f"nothing urgent. {requested}" + robots_state()))
        else:
            R.append((2, f"{display_name} receives 403 refusals ({fmt(n)} en {DAYS} days)",
                      "a search engine refused with a 403 retries endlessly and may drop the site from its results",
                      f"{requested}if these pages should not be indexed, say so in robots.txt (Disallow) rather than with a 403; "
                      "otherwise find the rule that blocks it (nginx-log-audit.sh --stats --details)"))
    browser = sum(v for k, v in robots.items() if k.startswith("browser"))
    if browser > 200 and browser > 0.25 * sum(robots.values()):
        ordinary = facts.get("refus_navigateurs", {})
        n_ordinary, n_scan = sum(ordinary.values()), facts.get("refus_nav_scanners", 0)
        refused_ips = facts.get("refus_nav_ip", {})
        chunks = []
        if n_ordinary:
            paths = ", ".join(f"{u} ({fmt(n)})" for u, n in sorted(ordinary.items(), key=lambda x: -x[1])[:4])
            chunks.append(f"{fmt(n_ordinary)} target ordinary pages ({paths})")
        if n_scan:
            chunks.append(f"{fmt(n_scan)} target scanner URLs (.env, .php…): normal refusal")
        comment = " ; ".join(chunks) + ". " if chunks else ""
        if refused_ips and n_ordinary:
            tops = sorted(refused_ips.items(), key=lambda x: (-x[1], x[0]))[:3]
            count, (top_ip, top_n) = len(refused_ips), tops[0]
            if count < 20:
                comment += (f"Concentrated on {fmt(count)} address(es) (most active: "
                            + ", ".join(f"{i} ({fmt(n)})" for i, n in tops) + "): probably robots. Program investigation: " + " ; ".join(investigate_403(i, n, facts) for i, n in tops) + ". ")
            elif top_n < 0.3 * n_ordinary:
                comment += (f"Spread over {fmt(count)} different addresses: probably a RULE that refuses real "
                            f"visitors. {other_addresses(list(refused_ips), facts)}{deny_rules_text()} ")
            else:
                # Many addresses, but ONE dominates: probable robot for that share, the rest is to be reviewed.
                others = [i for i in refused_ips if i != top_ip]
                comment += (f"Spread over {fmt(count)} addresses, but a single one ({top_ip}) accounts for {100 * top_n / n_ordinary:.0f} % "
                            f"({fmt(top_n)}): probably a robot. Program investigation: {investigate_403(top_ip, top_n, facts)}. "
                            + TR("The {count} other addresses share the rest: {others}").format(count=fmt(count - 1), others=other_addresses(others, facts))
                            + f"{deny_rules_text()} ")
            small_ones = facts.get("refus_nav_petits", 0)
            if small_ones >= 0.8 * n_ordinary:
                comment += "Very short responses: typical of a refusal by nginx itself. "
            elif small_ones <= 0.2 * n_ordinary:
                comment += "Long responses: more likely the application than nginx. "
        R.append((2, f"{fmt(browser)} 403 refusals target ordinary browsers ({DAYS} days)",
                  "these are often disguised robots, but they may be real visitors being refused",
                  comment.strip()))
    if passed_on and g("erreurs5xx") > max(20, 0.01 * passed_on):
        R.append((2, f"{fmt(g('erreurs5xx'))} server errors (5xx) in 7 days", "visitors received an error page",
                  app_log_check_summary()))
    if g("connexions") > 50:
        if "odoo-auth" in loaded:
            R.append((3, f"{fmt(g('connexions'))} login failures in 7 days", "possible password-guessing attack",
                      f"checked by the program: the odoo-auth jail is active ({len(facts['jails'].get('odoo-auth', ()))} IP "
                      f"banned by it over the period); nothing to do"))
        else:
            add_action("Install the odoo-auth jail", "nginx-hardening.sh --update",
                           lambda: run_tool("nginx-hardening.sh", "--update"))
            R.append((2, f"{fmt(g('connexions'))} login failures in 7 days", "possible password-guessing attack",
                      "checked by the program: the odoo-auth jail is not loaded"
                      + (" (fail2ban does not respond)" if code_f2b != 0 else "")
                      + " ; installation offered at the end of the summary (nginx-hardening.sh --update)"))
    if not PROFILE.get("CATCHALL_LOG") and not bbb:           # BBB: HAProxy receives port 443 (see nginx-hardening.sh)
        R.append((2, "no catch-all sensor (requests by raw IP address or unknown domain)",
                  "these requests, almost always sweeps, reach the site instead of being refused with 444",
                  "default server block that answers 444 and logs separately"))
    if not os.path.exists(os.path.join(SYSTEMD_DIR, f"{UNIT}.timer")):
        add_action("Install automatic monitoring (every hour)", "web-monitor.py --install-timer",
                       lambda: install_timer(1))
        R.append((2, "automatic monitoring not installed", "problems are only seen when you run the check",
                  "installation offered at the end of the summary (web-monitor.py --install-timer: every hour)"))
    mod = load_sanity_module()
    try:
        cfg = mod.load_config(mod.resolve_config_paths(None)) if mod else {}
    except Exception:
        cfg = {}
    if not (cfg.get("SMTP_HOST") and cfg.get("NOTIFY_EMAIL_TO")):
        R.append((2, "e-mail alerts not configured", "alerts stay in the system journal, where nobody sees them",
                  "follow doc/email-setup.md (SMTP relay, DNS records), then app-health-check.py --check-email-dns and --test-email"))
    short_ones = [f"{display_name} ({pol[2]} days)" for display_name, pol in (("nginx", policies.get("site")), ("fail2ban", policies.get("fail2ban")))
               if pol and pol[2] < TARGET_RETENTION_DAYS]
    if short_ones:
        add_action("Keep 3 months of logs (rotation)", "nginx-hardening.sh --update",
                       lambda: run_tool("nginx-hardening.sh", "--update"))
        R.append((3, "logs kept for less than 3 months: " + ", ".join(short_ones),
                  "impossible to trace an attack or a trend beyond that", "fix offered at the end of the summary — nginx-hardening.sh --update (step 11; --log-retention-months N for another duration)"))
    if PROFILE.get("APP_NAME") == "odoo":
        success = os.path.join(BACKUP_STATE, "last-success")
        if not os.path.exists(success):
            R.append((1, "no automatic Odoo backup (database and filestore)",
                      "a disk failure, a handling mistake or ransomware would lose all the data",
                      "run odoo-backup.sh (creates /etc/default/odoo-backup.conf: set REMOTE there, the off-server copy), then odoo-backup.sh --test-restore and odoo-backup.sh --install-timer"))
        elif time.time() - os.path.getmtime(success) > backup_threshold_hours() * 3600:
            threshold = backup_threshold_hours()
            R.append((1, f"last successful Odoo backup was {int((time.time() - os.path.getmtime(success)) // 3600)} h (threshold: {threshold} h)",
                      "beyond that delay, a failure would lose the work done since the last backup", backup_state()))
    if PROFILE.get("APP_LOG_KIND") == "journal":
        svc_odoo = detect_odoo_service()[0]
        if svc_odoo and odoo_config(svc_odoo)[1].get("limit_memory_hard") == 0:
            R.append((1, "Odoo without a memory limit (limit_memory_hard=0)",
                      "a runaway worker can exhaust the RAM and get PostgreSQL or Odoo killed by the kernel",
                      "apply the value from nginx-hardening.sh --check (step 6) — in run.sh if it passes it on the command line"))
    hsts = re.findall(r"Strict-Transport-Security\"?\s+\"?max-age=(\d+)", nginx_T())
    if hsts and min(int(x) for x in hsts) < 86400:
        R.append((3, f"HSTS max-age={min(int(x) for x in hsts)} s only",
                  "too short to really protect visitors against a downgrade to HTTP",
                  "move to max-age=31536000 once the configuration is judged stable"))
    if not shutil.which("geoiplookup") and candidate_package("geoip-bin"):
        add_action("Install geoip-bin (country of IP addresses read locally, without Internet)", "apt-get install -y geoip-bin geoip-database",
                       install_geoip)
        R.append((2, "geoip-bin missing (recommended, not optional)",
                  "without it, app-log-live.py looks up the country of EVERY address on the Internet (rdap.org): slow, and dependent on an outside service",
                  "installation offered at the end of the summary (apt-get install -y geoip-bin geoip-database); nginx-hardening.sh --update installs it too"))
    for prio, finding, comment in facts.get("bbb_problemes") or []:           # BigBlueButton section (apps/_bbb.py)
        if "nginx-hardening.sh --update" in comment:
            add_action("Check and reapply the BigBlueButton hardening (then record its state)",
                           "nginx-hardening.sh --update", lambda: run_tool("nginx-hardening.sh", "--update"))
            comment = comment.replace("nginx-hardening.sh --update", "nginx-hardening.sh --update, offered at the end of the summary", 1)
        R.append((prio, f"BigBlueButton: {finding}",
                  "our rules must stay in place and compatible with BBB after each of its updates", comment))
    print()
    print("RECOMMENDATIONS (in order of importance, based on these figures)")
    if not R:
        print("  None: nothing important to improve based on these figures.")
        return
    caption = {1: f"{BAD}HIGH{END_BAD}", 2: "MEDIUM", 3: "LOW"}
    for i, (prio, finding, why, comment) in enumerate(sorted(R, key=lambda r: r[0]), 1):
        print(f"  {i}. [{caption[prio]}] {finding}")
        print(f"     Why      : {why}")
        print(f"     How      : {comment}")
    if ACTIONS or RECOMMENDED:
        print()
        print("FIXES THE PROGRAM CAN MAKE ITSELF (offered below, with confirmation):")
        for i, (lib, cmd, _) in enumerate(ACTIONS):
            print(f"  {chr(97 + i)}) {lib} ({cmd})")
        for ip, reason in RECOMMENDED:
            print(f"  ▶ ban {ip} — {reason}")


def _certificate_via_health():
    """(False, detail) if a TLS certificate is failing according to app-health-check.py, otherwise (None, "")."""
    mod = load_sanity_module()
    if not mod or not hasattr(mod, "check_certificat_tls"):
        return None, ""
    try:
        cfg = mod.load_config(mod.resolve_config_paths(None))
        for label, ok, detail in mod.check_tls_certificate(cfg, "local"):
            if ok is False:
                return False, f"{label.split('—')[-1].strip()} — {detail}"
    except Exception:
        pass
    return None, ""


BASE_MODULES = {"res": "base", "ir": "base", "base": "base"}


# Form submissions that write into Odoo (registration, account creation, password reset, website form, message, survey): a flood of them is spam.
FORM_POST_RE = re.compile(r"^/(?:[a-z]{2}_[A-Z]{2}/)?(?:event/[^/]+/registration/|web/signup|web/reset_password|website/form/|mail/message/post|"
                          r"mail/chatter_post|survey/submit/|website/contactus|shop/address)")
BURST_WINDOW_S = 10               # suspicious burst: BURST_PAGES distinct pages or more within this window (same rule as nginx-log-audit.sh)
BURST_PAGES = 15


def accumulate_ip(stats, ip, method, url, code, d, idx, ua="", second=None):
    """Statistics of an IP address: requests and pages viewed per period, errors per code, activity per day,
    Odoo modules (prefix of the model of the /web/dataset/call_kw|call_button/<model>/… calls), most viewed pages.
    2.65 (suspicious activity of logged-in users): form submissions, malicious URLs, scripting tools, distinct User-Agents, and the largest
    burst of pages (number of pages within BURST_WINDOW_S seconds; `second` = epoch second of the request, None if unknown)."""
    v = stats.setdefault(ip, {"req": [0] * Periods.N, "pages": [0] * Periods.N, "err": {}, "days": {}, "modules": {}, "urls": {},
                              "posts": {}, "bad": 0, "tools": 0, "uas": set(), "burst": 0, "burst_when": "", "_win": []})
    page = method == "GET" and code[0] == "2" and not ASSET_RE.search(url)
    for i in idx:
        v["req"][i] += 1
        if page:
            v["pages"][i] += 1
    if page:
        path = url.split("?")[0][:60]
        v["urls"][path] = v["urls"].get(path, 0) + 1
        if second is not None:
            win = v["_win"]
            if win and second < win[-1]:          # a rotation read out of order: new window
                win.clear()
            win.append(second)
            while win and second - win[0] >= BURST_WINDOW_S:
                win.pop(0)
            if len(win) > v["burst"]:
                v["burst"] = len(win)
                v["burst_when"] = datetime.datetime.fromtimestamp(second).strftime("%Y-%m-%d %H:%M:%S")
    if code >= "400":
        v["err"][code] = v["err"].get(code, 0) + 1
    day = f"{d:%Y-%m-%d}"
    v["days"][day] = v["days"].get(day, 0) + 1
    m = re.match(r"/web/dataset/call_(?:kw|button)/([a-z0-9_]+)\.", url)
    if m:
        module = BASE_MODULES.get(m.group(1), m.group(1))
        v["modules"][module] = v["modules"].get(module, 0) + 1
    if method == "POST" and FORM_POST_RE.match(url):
        kind = re.sub(r"^/(?:[a-z]{2}_[A-Z]{2}/)?", "/", url.split("?")[0])
        kind = "/event/…/registration" if kind.startswith("/event/") else "/".join(kind.split("/")[:3])
        v["posts"][kind] = v["posts"].get(kind, 0) + 1
    if malicious(url):
        v["bad"] += 1
    if ua and OUTIL_RE.search(ua):
        v["tools"] += 1
    if ua and len(v["uas"]) < 20:
        v["uas"].add(ua[:160])


def request_second(text_line):
    """Epoch second of an nginx access line (None if unreadable); cached per (date, zone) by datetime itself — called only for followed addresses."""
    m = NGINX_TIME_RE.search(text_line)
    if not m:
        return None
    try:
        dd, mon, yy, hh, mi, ss, sign, zh, zm = m.groups()
        tz = datetime.timezone((1 if sign == "+" else -1) * datetime.timedelta(hours=int(zh), minutes=int(zm)))
        return int(datetime.datetime(int(yy), _MONTHS[mon], int(dd), int(hh), int(mi), int(ss), tzinfo=tz).timestamp())
    except (KeyError, ValueError):
        return None


def aggregate_ips(stats, ips, i=2):
    """Cumulation of the statistics of several IP addresses (those of an account), period i (2: 30 days / all)."""
    a = {"req": 0, "pages": 0, "err": {}, "days": {}, "modules": {}, "urls": {}, "posts": {}, "bad": 0, "tools": 0, "uas": set(), "burst": 0, "burst_when": ""}
    for ip in ips:
        v = stats.get(ip)
        if not v:
            continue
        a["req"] += v["req"][i]
        a["pages"] += v["pages"][i]
        for key_value in ("err", "days", "modules", "urls", "posts"):
            for k, n in v.get(key_value, {}).items():
                a[key_value][k] = a[key_value].get(k, 0) + n
        a["bad"] += v.get("bad", 0)
        a["tools"] += v.get("tools", 0)
        a["uas"] |= v.get("uas", set())
        if v.get("burst", 0) > a["burst"]:
            a["burst"], a["burst_when"] = v["burst"], v.get("burst_when", "")
    return a


def detail_lines(a, day_count=1):
    """Detail lines of an account, one labeled piece of information per line (no indentation: the caller adds it).
    Errors: red if there are 5xx, yellow otherwise (429, 4xx); 5xx codes in red, 429 in yellow. day_count: 1 = "Busiest day"
    (summary); more (--list-users --details: 5) = "Busiest days", from the most to the least active (requests per day)."""
    if not a["req"]:
        return ["Traffic         : no request from these addresses in the nginx logs kept"]
    top = lambda d, n: ", ".join(f"{k} ({fmt(v)})" for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0]))[:n])
    n_err = sum(a["err"].values())
    codes = ", ".join(color_code("31" if k.startswith("5") else "33" if k == "429" else "0", f"{k} : {fmt(v)}")
                      for k, v in sorted(a["err"].items(), key=lambda x: -x[1])[:3])
    error_list = color_code("31" if any(k.startswith("5") for k in a["err"]) else "33", f"{fmt(n_err)} error(s)") if n_err else "0 errors"
    day, n_day = max(a["days"].items(), key=lambda x: (x[1], x[0]))
    text_lines = [f"Traffic         : {fmt(a['pages'])} pages viewed · {fmt(a['req'])} requests · {error_list}" + (f" ({codes})" if n_err else "")]
    if day_count <= 1:
        text_lines.append(f"Busiest day     : {day} ({fmt(n_day)} requests)")
    else:
        most_active = sorted(a["days"].items(), key=lambda x: (-x[1], x[0]))[:day_count]
        text_lines.append("Busiest days: " + ", ".join(f"{j} ({fmt(n)} req.)" for j, n in most_active))
    if a["modules"]:
        text_lines.append(f"Odoo modules    : {top(a['modules'], 6)}")
    if a["urls"]:
        text_lines.append(f"Top pages       : {top(a['urls'], 4)}")
    return text_lines


def logged_in_ips(since):
    """IP addresses of the successful logins to Odoo since the given date (systemd journal), read BEFORE the nginx journal
    to detail only these addresses. None: no journal (BigBlueButton) — all addresses are followed."""
    if PROFILE.get("APP_LOG_KIND") != "journal":
        return None
    svc, ns = detect_odoo_service()
    if not svc:
        return set()
    code, out = run(["journalctl", "-u", svc, "-o", "short-iso", "--no-pager", "-q"] + (["--since", since] if since else [])
                    + ["--grep", "Login successful for"] + (["--namespace", ns] if ns else []), timeout=300)
    if not since:
        LOGIN_HISTORY_CACHE["out"] = out             # whole history: reused by login_history() (first login of each account)
    banned_accounts = registered_odoo_users()["banned"]
    return {ip for login, ip in re.findall(r"Login successful for db:\S+ login:(\S+) from (\S+)", out) if login not in banned_accounts}


def logged_in_shares(c, facts):
    """Requests and pages viewed of the IP addresses of logged-in users (Odoo: successful logins; BBB: participants)."""
    ips = facts.get("ips_connues") or {i for v in facts.get("comptes", {}).values() for i in v["ips"]}
    for ip in ips:
        v = facts.get("stats_ip", {}).get(ip)
        if v:
            team = in_whitelist(ip)
            for i in range(Periods.N):
                c.n[("req_connectes", i)] = c.n.get(("req_connectes", i), 0) + v["req"][i]
                c.n[("pages_connectes", i)] = c.n.get(("pages_connectes", i), 0) + v["pages"][i]
                if not team:
                    c.n[("req_connus_hors_equipe", i)] = c.n.get(("req_connus_hors_equipe", i), 0) + v["req"][i]


def note_account(accounts, display_name, ip, idx, when, database=None):
    v = accounts.setdefault(display_name, {"n": [0] * Periods.N, "ips": {}, "last": "", "bases": set()})
    if database:
        v["bases"].add(database)
    for i in idx:
        v["n"][i] += 1
    v["ips"][ip] = v["ips"].get(ip, 0) + 1
    v["last"] = max(v["last"], when)


def show_whitelist(c, facts):
    """Use of the site by each address of the whitelist (team): requests per period and share of the site
    traffic, pages viewed, last activity; total of the list."""
    stats = facts.get("stats_ip", {})
    captions = whitelist_captions()
    addresses = sorted({a for a in WHITELIST | set(captions) if a not in ("127.0.0.1", "::1")},
                      key=lambda a: (captions.get(a, "~"), a))
    if not addresses:
        return
    print()
    print(f"WHITELIST USAGE (team) — requests, and share of the traffic of {PROFILE.get('APP_LABEL', 'l’application')}")
    total = [0, 0, 0]
    cumulative = lambda ip: [sum(v["req"][i] for a, v in stats.items() if a == ip or ("/" in ip and _within(a, ip))) for i in range(3)]
    wl_lines = []
    for a in addresses:
        req = cumulative(a)
        pages = sum(v["pages"][2] for x, v in stats.items() if x == a or ("/" in a and _within(x, a)))
        day_count = [j for x, v in stats.items() if x == a or ("/" in a and _within(x, a)) for j in v["days"]]
        for i in range(3):
            total[i] += req[i]
        wl_lines.append((a, captions.get(a, "")[:44], req, pages, max(day_count) if day_count else "no activity"))
    wid = max([len(fmt(v)) for _, _, req, _, _ in wl_lines for v in req] + [len(fmt(v)) for v in total] + [1])      # right-aligned digits, "(12 %)" in its column
    col = wid + 9
    cell = lambda v, i: f"{fmt(v):>{wid}}" + (f" ({100 * v / c.get('requetes', i):.0f} %)" if c.get("requetes", i) else "").ljust(8)
    cols = [0, 1, 2] if DAYS > 7 else [0, 2]               # period of 7 days or less: the "7 days" column would be identical to that of the period (removed)
    names = {0: TR("Today"), 1: TR("7 days"), 2: TR(f"{DAYS} days")}
    print(f"  {'Address':<17} {'Label':<44} " + " ".join(f"{names[i]:>{col}}" for i in cols) + f" {TR(f'Pages {DAYS} j'):>10}  Last")
    for a, lib, req, pages, last in wl_lines:
        print(f"  {a:<17} {lib:<44} " + " ".join(f"{cell(req[i], i):>{col}}" for i in cols) + f" {fmt(pages):>10}  {last}")
    print(f"  {'Whole whitelist':<62} " + " ".join(f"{cell(total[i], i):>{col}}" for i in cols))
    print("  (whitelist: /etc/default/nginx-tools-white-list.conf, completed by the locations [protected] and nginx « allow » rules; our own tests excluded)")


def _within(ip, range_value):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(range_value, strict=False)
    except ValueError:
        return False


def shared_mark(accounts):
    """{address: number of accounts, or PLACE NAME}: addresses used by several accounts (office, mobile, NAT) or located in a
    [shared] place (university…) — for these, the place replaces the number of accounts."""
    n = {}
    for v in accounts.values():
        for ip in v["ips"]:
            n[ip] = n.get(ip, 0) + 1
    res = {ip: k for ip, k in n.items() if k > 1}
    for ip in n:
        place = lists().lieu(ip)
        if place and place.partagee:
            res[ip] = place.libelle
    return res


def shared_text(value):
    """"4 accounts" (number) or the name of the place (address of a shared place)."""
    return f"{value} accounts" if isinstance(value, int) else str(value)


def show_accounts(facts, banned):
    """Logged-in accounts (Odoo: journal, successful logins) or participants (BigBlueButton: participation links):
    a blank line and the name before each account, then one piece of information per line; key figures in color (terminal)."""
    bbb = PROFILE.get("APP_NAME") == "bbb"
    accounts = facts.get("comptes") or {}
    print()
    print("BIGBLUEBUTTON PARTICIPANTS (join links, nginx log)" if bbb else
          f"CONNECTIONS TO {PROFILE.get('APP_LABEL', 'ODOO').upper()} (successful logins, log)")
    if not accounts:
        print("  none in the logs kept")
        return
    sorted_items = sorted(accounts.items(), key=lambda x: (-x[1]["n"][2], x[0]))
    shared = shared_mark(accounts)
    for display_name, v in sorted_items[:20]:
        ips = sorted(v["ips"], key=lambda i: -v["ips"][i])
        shown = ", ".join(color_code("35", f"{i} (banned)") if i in banned else f"{i} (shared: {shared_text(shared[i])})" if i in shared else i
                        for i in ips)                    # ALL the addresses (never "(+N)")
        print()
        print(f"  {color_code('1', display_name)}")
        today_d = color_code("32", v["n"][0]) if v["n"][0] else "0"
        week = f"7 j {v['n'][1]} · " if DAYS > 7 else ""              # --days N ≤ 7: no distinct "week" column
        print(f"    Logins          : today {today_d} · {week}{DAYS} j {v['n'][2]} — last {v['last']}")
        print(f"    IP addresses    : {shown}")
        if "stats_ip" in facts:
            for text_line in detail_lines(aggregate_ips(facts["stats_ip"], v["ips"])):
                print(f"    {text_line}")
    if len(sorted_items) > 20:
        print()
        print(f"  (+{len(sorted_items) - 20} other(s) — full list: web-monitor.py --list-users)")
    print()
    if "stats_ip" in facts:
        print(f"  (traffic of the account's IP addresses over {DAYS} days — a shared address counts for each account)")
    banned_ips = sorted({i for v in accounts.values() for i in v["ips"] if i in banned})
    if banned_ips:
        print(f"  {BAD}⚠ {len(banned_ips)} banned address(es) of logged-in users: {', '.join(banned_ips)} — bans to lift:{END_BAD}")
        print(f"  {BAD}  nginx-log-audit.sh --unban-check (or --unban IP){END_BAD}")


def read_odoo_users(accounts):
    """{database: {login: {uid, name, type}} or None} of the databases where the accounts logged in (apps/_odoo_db.py: read-only
    in PostgreSQL, root required)."""
    path = os.path.join(SCRIPT_DIR, "apps", "_odoo_db.py")
    if not os.path.isfile(path):
        return {}
    spec = importlib.util.spec_from_file_location("_odoo_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.VERBOSE = VERBOSE                              # --verbose: the psql command is displayed
    return {database: module.utilisateurs(database) for database in sorted({b for v in accounts.values() for b in v["bases"]})}


def read_profiles(accounts):
    """2.67: {database: {login: profile} or None}: e-mail, phone, country, city, groups, tags, event registrations, surveys completed of each account
    (apps/_odoo_db.py user_profiles, read-only in PostgreSQL, root required)."""
    path = os.path.join(SCRIPT_DIR, "apps", "_odoo_db.py")
    if not os.path.isfile(path):
        return {}
    spec = importlib.util.spec_from_file_location("_odoo_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.VERBOSE = VERBOSE
    if not hasattr(module, "user_profiles"):
        return {}
    return {database: module.user_profiles(database) for database in sorted({b for v in accounts.values() for b in v["bases"]})}


def uid_lines(login, databases, utilisateurs):
    """Odoo UID of the account (one per database where it logged in); the reason if the database is unreadable."""
    if not databases:
        return []
    res = []
    for database in sorted(databases):
        table = utilisateurs.get(database)
        info = (table or {}).get(login)
        if info:
            res.append(f"Odoo UID        : {color_code('36', info['uid'])} — {info['nom'] or login} ({info['type']}), database {database}")
        elif table is None:
            res.append(f"Odoo UID        : unreadable (database {database} : PostgreSQL unreachable, or root required)")
        else:
            res.append(f"Odoo UID        : not found (database {database} : account deleted or renamed since)")
    return res


# --- --list-users: sort (--sort), table (--table), estimated login duration ------------------------------------------------------
COLUMN_WIDTH = 30                  # --table: MAXIMUM width of a column (longer text truncated with "…")
MIN_COLUMN_WIDTH = 5               # --table: minimum width; in between, the column adjusts to its longest content
JOURNAL_ISO_RE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:[.,]\d+)?(?:(Z)|([+-])(\d\d):?(\d\d))?")


def journal_minute(text_line):
    """Minute (epoch // 60) of a "journalctl -o short-iso" line: time zone "-0400", "-04:00" or "Z" (depending on the systemd version), decimal seconds
    tolerated; without a time zone: local time. None if the line has no readable timestamp."""
    m = JOURNAL_ISO_RE.match(text_line)
    if not m:
        return None
    a, mo, j, h, mi, se = (int(x) for x in m.group(1, 2, 3, 4, 5, 6))
    try:
        if m.group(7) or m.group(8):
            offset = 0 if m.group(7) else (1 if m.group(8) == "+" else -1) * (int(m.group(9)) * 60 + int(m.group(10)))
            tz = datetime.timezone(datetime.timedelta(minutes=offset))
            return int(datetime.datetime(a, mo, j, h, mi, se, tzinfo=tz).timestamp() // 60)
        return int(datetime.datetime(a, mo, j, h, mi, se).timestamp() // 60)
    except (ValueError, OverflowError):
        return None
def os_name(ua):
    """Operating system according to the User-Agent (family only: Windows 10 and 11 present the same "Windows NT 10.0"); "" if unknown (robots, tools).
    Known limit: a recent iPad (iPadOS 13+) presents itself as a Mac."""
    for pattern, name in ((r"Windows Phone", "Windows Phone"), (r"Windows", "Windows"), (r"Android", "Android"), (r"iPhone|iPad|iPod|CPU OS|iOS", "iOS"),
                          (r"CrOS", "ChromeOS"), (r"Macintosh|Mac OS X", "macOS"), (r"Linux|X11|Ubuntu|Fedora|Debian", "Linux")):
        if re.search(pattern, ua or ""):
            return name
    return ""


def browser_name(ua):
    """Browser according to the User-Agent (Edge, Opera, Firefox, Chrome, Safari, Samsung Internet); "" if unknown (robots, tools)."""
    ua = ua or ""
    for pattern, name in ((r"Edg(?:e|A|iOS)?/", "Edge"), (r"OPR/|Opera", "Opera"), (r"SamsungBrowser/", "Samsung Internet"), (r"Firefox/|FxiOS/", "Firefox"),
                          (r"Chrome/|CriOS/|Chromium/", "Chrome"), (r"Version/[\d.]+.*Safari/", "Safari")):
        if re.search(pattern, ua):
            return name
    return ""


def top_names(counter, limit=3):
    """"Windows, Android (+1)": the names of a counter from the most to the least frequent, `limit` at most; "-" if empty."""
    names = [n for n, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]
    return "-" if not names else ", ".join(names[:limit]) + (f" (+{len(names) - limit})" if len(names) > limit else "")


SESSION_PAUSE = 30                    # minutes without a request from the address after which a login is considered ended
# Canonical key -> (label, default direction: 1 ascending, -1 descending, synonyms accepted)
USER_SORTS = {
    "created": ("account creation", -1, ("cree", "créé", "creation", "création", "new", "nouveau")),
    "first": ("first login", 1, ("premiere", "première", "oldest")),
    "ip": ("IP address", 1, ("adresse",)),
    "last": ("last login", -1, ("latest", "derniere", "dernière", "recent", "récent")),
    "login": ("identifiant", 1, ("identifiant", "id", "compte")),
    "logins": ("number of logins", -1, ("connexions", "connexion", "count", "n")),
    "minutes": ("login minutes", -1, ("duree", "durée", "duration", "time")),
    "name": ("nom", 1, ("nom",)),
    "os": ("operating system", 1, ("system", "systeme", "système")),
    "pages": ("pages viewed", -1, ("vues", "views", "lues", "read")),
    "received": ("MB received", -1, ("recus", "download")),
    "sent": ("MB sent", -1, ("envoyes", "upload")),
    "written": ("pages written", -1, ("ecrites", "writes", "post")),
    "type": ("account type", 1, ("kind",)),
    "uid": ("UID", 1, ()),
    "vpn": ("VPN, Tor, relay, hosting", -1, ("proxy", "hebergeur", "hébergeur", "tor")),
    "events": ("event registrations", -1, ("evenements", "inscriptions", "registrations")),
    "surveys": ("surveys completed", -1, ("sondages",)),
    "seen": ("last seen on the site", -1, ("ipseen", "ip-seen", "vue", "vu")),
}
SORT_FIELD = {"name": "name", "login": "login", "uid": "uid", "ip": "ip", "first": "first", "last": "last", "logins": "logins", "minutes": "minutes",
              "type": "type", "os": "systems", "pages": "read", "written": "written", "received": "received", "sent": "sent", "events": "events",
              "surveys": "surveys", "seen": "ipseen", "created": "created", "vpn": "vpn"}           # 2.69: --sort KEY -> column whose title is colored


def plain_text(text):
    """Lower case without accents (« Bénévole » -> « benevole »): names compared as people type them (--group, --sort)."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(text).strip().lower()) if not unicodedata.combining(c))


def sort_key(value):
    """--sort: accepts the canonical key or a synonym (name, latest, first, duration…), case-insensitive; otherwise an error that lists the keys."""
    v = plain_text(value or "")                         # 2.66: accents ignored (« reçus » = « recus », « écrites » = « ecrites »)
    for key_value, (_, _, synonyms) in USER_SORTS.items():
        if v == key_value or v in {plain_text(x) for x in synonyms}:
            return key_value
    raise argparse.ArgumentTypeError(f"unknown sort key « {value} » (values: {literal(', '.join(sorted(USER_SORTS)))} ; synonyms: name, latest, first, logins, duration…)")


def char_width(ch):
    """Columns taken by a character on a terminal: 2 for the wide East Asian characters (Chinese, Japanese, Korean, full-width forms, most emoji),
    0 for combining marks and zero-width characters, 1 otherwise."""
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(text_value):
    """Width of a text on a terminal (2.65: « 张三李四 » takes 8 columns, not 4 — the --table columns were shifted by Chinese names)."""
    text_value = ANSI_RE.sub("", str(text_value))
    return sum(char_width(c) for c in text_value) if not text_value.isascii() else len(text_value)


def truncate_column(text_value, width=COLUMN_WIDTH):
    """Single-line text, padded with spaces to `width` COLUMNS of the terminal, or truncated with "…" if wider (wide characters count 2)."""
    text_value = " ".join(str(text_value).split())
    if display_width(text_value) <= width:
        return text_value + " " * (width - display_width(text_value))
    out, used = "", 0
    for ch in text_value:
        w = char_width(ch)
        if used + w > width - 1:
            break
        out, used = out + ch, used + w
    return out + "…" + " " * (width - 1 - used)


# --table / --csv (2.67): fields of the table, in the default order — key (--table-fields), French header, English header, alignment, maximum width.
# The headers are written in both languages here (a column title is not a sentence to translate by fragments: « Type », « Name » would change elsewhere).
TABLE_FIELDS = (
    ("num", "N°", "#", "r", 5), ("uid", "UID", "UID", "r", 6), ("ip", "IP", "IP", "l", 20), ("ipseen", "IP vue", "IP seen", "l", 27), ("name", "Nom", "Name", "l", 21), ("login", "Identifiant", "Login", "l", 23),
    ("ipcountry", "Pays IP", "IP ctry", "l", 8), ("vpn", "VPN", "VPN", "l", 14),
    ("created", "Compte créé", "Account created", "l", 10), ("first", "Première connexion", "First login", "l", 16), ("last", "Dernière connexion", "Last login", "l", 16), ("logins", "Connexions", "Logins", "r", 6),
    ("minutes", "Minutes", "Minutes", "r", 7), ("type", "Type", "Type", "l", 8), ("events", "Événements", "Events", "r", 5), ("surveys", "Sondages", "Surveys", "r", 5),
    ("phone", "Téléphone", "Phone", "l", 17), ("country", "Pays", "Country", "l", 4), ("city", "Ville", "City", "l", 15), ("groups", "Groupes", "Groups", "l", 30),
    ("tags", "Étiquettes", "Tags", "l", 30), ("systems", "Systèmes", "Systems", "l", 24), ("browsers", "Navigateurs", "Browsers", "l", 24),
    ("read", "Pages lues", "Pages read", "r", 7), ("written", "Pages écrites", "Pages written", "r", 7), ("received", "Mo reçus", "MB received", "r", 7),
    ("sent", "Mo envoyés", "MB sent", "r", 7), ("email", "Courriel", "E-mail", "l", 30))
FIELD_KEYS = [f[0] for f in TABLE_FIELDS]
DEFAULT_TABLE_FIELDS = [k for k in FIELD_KEYS if k not in ("email", "tags")]     # the login is already the e-mail of most accounts; 2.69: tags often repeat the groups
PROFILE_FIELDS = {"events", "surveys", "phone", "country", "city", "groups", "tags", "email", "created"}      # read in PostgreSQL (apps/_odoo_db.py user_profiles)
# 2.71: French names of the fields, accepted for the English keys (until 2.70 the French help displayed « navigateurs », « envoyé(s) »… instead of the keys)
FIELD_ALIASES = {"navigateurs": "browsers", "systemes": "systems", "envoye(s)": "sent", "envoyes": "sent", "recus": "received", "lues": "read",
                 "ecrites": "written", "pays": "country", "ville": "city", "groupes": "groups", "etiquettes": "tags", "telephone": "phone",
                 "evenements": "events", "sondages": "surveys", "courriel": "email", "nom": "name", "identifiant": "login", "connexions": "logins",
                 "premiere": "first", "derniere": "last", "cree": "created", "ip-vue": "ipseen", "pays-ip": "ipcountry"}
MIN_HEADER_WIDTH = 4                  # a column is never narrower: its title stays readable (« Conn », « Mint »)


def table_fields(value):
    """--table-fields name,login,logins…: the fields to show, in the order given (« all » = every field, e-mail included); otherwise an error that lists them."""
    keys = [k.strip().lower().replace("ip-seen", "ipseen").replace("ip-country", "ipcountry") for k in (value or "").split(",") if k.strip()]
    keys = [FIELD_ALIASES.get(plain_text(k), k) for k in keys]                     # 2.71: the French names once shown by the help (« navigateurs »)
    if keys == ["all"]:
        return list(FIELD_KEYS)
    wrong = [k for k in keys if k not in FIELD_KEYS]
    if wrong or not keys:
        raise argparse.ArgumentTypeError(f"unknown field(s) « {literal(', '.join(wrong) or value)} » (fields: {literal(', '.join(FIELD_KEYS))}, or all)")
    return list(dict.fromkeys(keys))


def compact_names(counter, limit=3):
    """« Linux,Windows,Android,+1 »: the names of a counter from the most to the least frequent, `limit` at most, no space (narrow columns); « - » if empty."""
    names = [n for n, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]
    return "-" if not names else ",".join(names[:limit]) + (f",+{len(names) - limit}" if len(names) > limit else "")


def cut_to(text_value, width):
    """Text cut to `width` terminal columns WITHOUT « … » (column titles: « Connexions » -> « Conn »)."""
    out, used = "", 0
    for ch in text_value:
        if used + char_width(ch) > width:
            break
        out, used = out + ch, used + char_width(ch)
    return out


def compact_table(fields, rows, styles=None, repeat_header=False, sorted_field=None):
    """2.67: table without spaces around the cells (« |Conn| »): each column as wide as its longest value (at least MIN_HEADER_WIDTH, at most the field's
    maximum, longer values cut with « … »); the title is cut to that width, on TWO lines when it has two words or more (« Première » / « connexion »);
    numbers aligned on the right. `rows`: lists of texts (one per field); `styles`: same shape, color code of each cell or None (applied AFTER the
    padding: colors never shift the columns). repeat_header: the titles again under the last line. sorted_field (2.69): its title in cyan.
    2.70: every UNDERLINE_EVERY-th line underlined."""
    spec = {f[0]: f for f in TABLE_FIELDS}
    titles = [spec[k][1] if LANGUAGE != "en" else spec[k][2] for k in fields]
    widths = []
    for i, k in enumerate(fields):
        data = max([display_width(str(r[i])) for r in rows] or [0])
        widths.append(max(MIN_HEADER_WIDTH, min(spec[k][4], data)))
    def header_lines():
        split = [t.split(" ", 1) if " " in t else [t, ""] for t in titles]
        def title(part, w, k):
            t = cut_to(part, w) + " " * (w - display_width(cut_to(part, w)))
            return color_code("36", t) if k == sorted_field and sorted_field else color_code("1", t)      # 2.69: the sorted column stands out
        lines = ["|" + "|".join(title(part[n], w, k) for part, w, k in zip(split, widths, fields)) + "|" for n in (0, 1)]
        return lines if any(part[1] for part in split) else lines[:1]
    sep = "|" + "|".join("-" * w for w in widths) + "|"
    out = [sep] + header_lines() + [sep]
    for r_i, r in enumerate(rows):
        cells = []
        for i, (k, w) in enumerate(zip(fields, widths)):
            text_value = " ".join(str(r[i]).split())
            if display_width(text_value) > w:
                text_value = cut_to(text_value, w - 1) + "…"
            pad = " " * (w - display_width(text_value))
            cell = pad + text_value if spec[k][3] == "r" else text_value + pad
            style = styles[r_i][i] if styles else None
            cells.append(color_code(style, cell) if style else cell)
        line = "|" + "|".join(cells) + "|"
        out.append(underline(line) if UNDERLINE_EVERY and (r_i + 1) % UNDERLINE_EVERY == 0 and r_i + 1 < len(rows) else line)
    out.append(sep)
    if repeat_header:
        out += header_lines() + [sep]
    return out


UNDERLINE_EVERY = 5                   # 2.70: --table: every 5th line underlined (easier to follow a line across a wide table); 0 = never


def underline(line):
    """2.70: the whole line underlined, colored cells included (each « ESC[…m » of a cell keeps the underline: « 0 » would remove it); unchanged without colors."""
    if not colors_on():
        return line
    return "\x1b[4m" + ANSI_RE.sub(lambda m: m.group(0)[:-1] + ";4m", line) + "\x1b[0m"


def level_styles(values):
    """Colors of a numeric column (2.67): the top 10 % of the non-zero values in bold yellow, the next 15 % in yellow, 0 in grey (codes for color_code,
    which always adds bold: « 0;… » removes it)."""
    nonzero = sorted(v for v in values if v)
    if not nonzero:
        return lambda v: "0;90"
    def at(q):
        return nonzero[min(len(nonzero) - 1, int(q * len(nonzero)))]
    p90, p75 = at(0.9), at(0.75)
    def style(v):
        if not v:
            return "0;90"
        if len(nonzero) >= 4 and v >= p90:
            return "33"
        if len(nonzero) >= 4 and v >= p75:
            return "0;33"
        return None
    return style


WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
NOT_A_WRITE_RE = re.compile(r"^/(?:websocket|longpolling|bus/|im_livechat/init|web/webclient/|web/action/load|web/dataset/call_kw/[^?]*/(?:web_)?(?:search_read|read|search_count|name_search|onchange|read_group|web_read_group|fields_get|get_views))")


def megabytes(n):
    """Bytes -> « 12.3 » (MB, one decimal; « <0.1 » for a few kilobytes, « 0 » for nothing)."""
    if not n:
        return "0"
    mb = n / 1_000_000
    return "<0.1" if mb < 0.05 else f"{mb:.1f}"


def tally_agent(agents, key_value, ua, is_page, is_write=False, sent=0, received=None):
    """--list-users --table: counts the operating system and the browser of a request (User-Agent `ua`), the pages read, the pages written (2.66: POST / PUT /
    PATCH / DELETE that change something: forms, records — not the reads of the Odoo web client nor the chat), the bytes the account RECEIVED (body sent by
    nginx) and SENT (size of its request: « rl= » of the log, None if the log does not have it), per `key_value` (address or participant).
    Our own tests (SERVER_TESTS) and the User-Agents without a known system or browser (robots, tools) count for nothing."""
    v = agents.setdefault(key_value, {"os": {}, "nav": {}, "pages": 0, "written": 0, "received": 0, "sent": None})
    if is_page:
        v["pages"] += 1
    if is_write:
        v["written"] += 1
    v["received"] += sent or 0
    if received is not None:
        v["sent"] = (v["sent"] or 0) + received
    if not ua or any(t in ua for t in SERVER_TESTS):
        return
    for kind, name in (("os", os_name(ua)), ("nav", browser_name(ua))):
        if name:
            v[kind][name] = v[kind].get(name, 0) + 1


def login_minutes(logins, activity):
    """Estimated login minutes of an account: for each login (minute, address), the session lasts as long as the address makes a request at least every
    SESSION_PAUSE minutes; overlapping sessions are merged; a login without activity counts 1 minute. `activity`: {address: sorted minutes}."""
    intervals = []
    for start, ip in logins:
        active_ones, end = activity.get(ip, []), start
        for a in active_ones[bisect.bisect_left(active_ones, start):]:
            if a - end > SESSION_PAUSE:
                break
            end = max(end, a)
        intervals.append((start, end))
    total, current = 0, None
    for d, f in sorted(intervals):
        if current and d <= current[1] + 1:
            current[1] = max(current[1], f)
        else:
            if current:
                total += current[1] - current[0] + 1
            current = [d, f]
    return total + (current[1] - current[0] + 1 if current else 0)


def csv_number(value, decimals=0):
    """A number for a spreadsheet: decimal comma in French (Excel in French reads « 12,5 »), point in English; empty if unknown."""
    if value is None:
        return ""
    text_value = f"{value:.{decimals}f}" if decimals else str(value)
    return text_value.replace(".", ",") if LANGUAGE != "en" else text_value


def seen_text(minute, short=True):
    """Minute (epoch // 60) of the last request of an address -> « 10-17 14:05 » (short) or « 2026-10-17 14:05 »."""
    return time.strftime("%m-%d %H:%M" if short else "%Y-%m-%d %H:%M", time.localtime(minute * 60))


# --- 2.70: country and owner of the address block (RDAP, otherwise whois: apps/_reseau.py, permanent cache apps/_cache_ip.py), VPN detection ---------
IP_LOOKUPS_PER_ACCOUNT = 5            # addresses of an account looked up: its most used ones (logins) and the latest seen
IP_LOOKUP_TIMEOUT_S = 8
IP_LOOKUP_THREADS = 8
# Owner of the block (RDAP organisation and network name) -> (kind, short name; empty: the owner's first word). The first match wins.
# Kinds: VPN, Tor, Relay (iCloud Private Relay, Cloudflare WARP: the user's real address is hidden too), Hosting (data center: the exit of most VPNs
# and proxies — a person does not browse from a data center, a VPN does).
VPN_OWNERS = (
    (r"nordvpn|tefincom", "VPN", "NordVPN"), (r"surfshark", "VPN", "Surfshark"), (r"expressvpn|express vpn", "VPN", "ExpressVPN"),
    (r"proton ?(ag|vpn|technologies)", "VPN", "Proton"), (r"mullvad|31173 services", "VPN", "Mullvad"), (r"private internet access", "VPN", "PIA"),
    (r"cyberghost", "VPN", "CyberGhost"), (r"ipvanish", "VPN", "IPVanish"), (r"windscribe", "VPN", "Windscribe"), (r"hide\.?me\b|eventure", "VPN", "hide.me"),
    (r"purevpn|gz systems", "VPN", "PureVPN"), (r"torguard|vpnetworks", "VPN", "TorGuard"), (r"vyprvpn|golden frog", "VPN", "VyprVPN"),
    (r"hotspot shield|\bpango\b", "VPN", "HotspotShield"), (r"tunnelbear", "VPN", "TunnelBear"), (r"astrill", "VPN", "Astrill"), (r"airvpn", "VPN", "AirVPN"),
    (r"\bivpn\b|privatus", "VPN", "IVPN"), (r"perfect privacy", "VPN", "PerfectPrivacy"), (r"\bovpn\b", "VPN", "OVPN"), (r"privado", "VPN", "Privado"),
    (r"strongvpn", "VPN", "StrongVPN"), (r"vpn", "VPN", ""),
    (r"torservers|tor[-_ ]?exit|emerald onion|applied privacy|calyx institute|tor project", "Tor", ""),
    (r"private[-_ ]?relay", "Relay", "iCloud"), (r"cloudflare", "Relay", "Cloudflare"), (r"fastly", "Relay", "Fastly"),
    (r"m247", "Hosting", "M247"), (r"datacamp|cdn77", "Hosting", "DataCamp"), (r"packethub", "Hosting", "PacketHub"), (r"clouvider", "Hosting", "Clouvider"),
    (r"zenlayer", "Hosting", "Zenlayer"), (r"leaseweb", "Hosting", "Leaseweb"), (r"\bovh", "Hosting", "OVH"), (r"hetzner", "Hosting", "Hetzner"),
    (r"digitalocean|digital ocean", "Hosting", "DigitalOcean"), (r"amazon|\baws\b", "Hosting", "Amazon"), (r"google (llc|cloud)|google-cloud|googlecloud", "Hosting", "Google"),
    (r"microsoft|azure", "Hosting", "Microsoft"), (r"linode|akamai", "Hosting", "Akamai"), (r"vultr|choopa|constant company", "Hosting", "Vultr"),
    (r"contabo", "Hosting", "Contabo"), (r"scaleway|online s\.?a\.?s", "Hosting", "Scaleway"), (r"hostinger", "Hosting", "Hostinger"), (r"psychz", "Hosting", "Psychz"),
    (r"xtom", "Hosting", "xTom"), (r"tzulo", "Hosting", "Tzulo"), (r"performive", "Hosting", "Performive"), (r"gsl networks", "Hosting", "GSL"),
    (r"datapacket", "Hosting", "DataPacket"), (r"quadranet", "Hosting", "QuadraNet"), (r"colocrossing", "Hosting", "ColoCrossing"), (r"worldstream", "Hosting", "WorldStream"),
    (r"frantech|buyvm|ponynet", "Hosting", "BuyVM"), (r"g-?core", "Hosting", "G-Core"), (r"stark industries", "Hosting", "Stark"), (r"\baeza\b", "Hosting", "Aeza"),
    (r"alibaba|aliyun", "Hosting", "Alibaba"), (r"tencent", "Hosting", "Tencent"), (r"oracle", "Hosting", "Oracle"), (r"ionos|1&1", "Hosting", "IONOS"),
    (r"netcup", "Hosting", "netcup"), (r"hivelocity", "Hosting", "Hivelocity"),
    (r"hosting|hoster|data ?cent(er|re)|datacent|\bvps\b|colocation|server", "Hosting", ""))
VPN_OWNERS_RE = [(re.compile(pattern), kind, name) for pattern, kind, name in VPN_OWNERS]
VPN_PRIORITY = {"VPN": 4, "Tor": 4, "Relay": 2, "Hosting": 1}


def public_address(ip):
    """True for an address of the Internet (not private, loopback, link-local, documentation…): only those have an owner in RDAP / whois."""
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def ip_owners(ips):
    """{address: owner of its block (apps/_reseau.py fournisseur: organisation, reseau, plage, pays…) or None if unknown}. Public addresses only. Each address
    is asked ONCE on the Internet (rdap.org, otherwise the whois command; only the address is sent), then served by the permanent cache of the addresses
    (apps/_cache_ip.py, 90 days; a failure is never remembered). NGINX_TOOLS_INTERNET=off: the cache only."""
    res = {ip: None for ip in ips}
    public = sorted(ip for ip in res if public_address(ip))
    if not public:
        return res
    try:
        net = _load_module("_reseau")
    except Exception:  # noqa: BLE001 - component missing or broken: country and VPN unknown, the table is still shown
        eprint("Owner of the address blocks: component apps/_reseau.py missing or unreadable — IP country and VPN unknown")
        return res
    net.VERBOSE = VERBOSE
    cache = net.ouvrir_cache("auto")
    todo = []
    for ip in public:
        known = cache.rdap(ip) if cache is not None else None
        if known:
            res[ip] = known
        else:
            todo.append(ip)
    if not todo:
        return res
    if os.environ.get("NGINX_TOOLS_INTERNET", "").lower() in ("off", "0", "no", "non"):
        eprint(f"Owner of the address blocks: {len(todo)} address(es) not in the cache, not looked up (NGINX_TOOLS_INTERNET=off) — « ? » in the table")
        return res
    show = sys.stderr.isatty() or VERBOSE                 # a long step says what it does (never in a pipe nor a timer)
    start = time.time()
    if show:
        eprint(f"Owner of the address blocks (RDAP, otherwise whois): {len(todo)} address(es) to look up on the Internet, {len(public) - len(todo)} in the cache …")
    with concurrent.futures.ThreadPoolExecutor(IP_LOOKUP_THREADS) as pool:
        for ip, r in zip(todo, pool.map(lambda i: net.fournisseur(i, IP_LOOKUP_TIMEOUT_S, cache=cache), todo)):
            res[ip] = r
    if show:
        unknown = sum(1 for ip in todo if res[ip] is None)
        eprint(f"  … done in {time.time() - start:.0f} s" + (f" ({unknown} unknown: rdap.org unreachable and no whois command?)" if unknown else ""))
    return res


def owner_name(owner):
    """Short name of a block owner: first word of the organisation (otherwise of the network name), 12 characters at most."""
    text_value = (owner.get("organisation") or owner.get("reseau") or "?").replace(",", " ").split()
    return (text_value[0] if text_value else "?")[:12]


def vpn_kind(owner):
    """(kind, short name) of the owner of an address block — VPN, Tor, Relay, Hosting (see VPN_OWNERS) — or None: an access provider (home, mobile),
    a company, a school… A guess from the NAME of the owner, not a proof: a VPN on a network of unknown name is not seen."""
    if not owner:
        return None
    text_value = " ".join(owner.get(k) or "" for k in ("organisation", "reseau")).lower()
    for pattern, kind, name in VPN_OWNERS_RE:
        if pattern.search(text_value):
            return kind, name or owner_name(owner)
    return None


def account_lookups(v, seen):
    """Addresses of an account to look up (2.70): its IP_LOOKUPS_PER_ACCOUNT most used ones (logins), the main one first, then the latest seen."""
    ips = sorted(v["ips"], key=lambda i: (-v["ips"][i], i))[:IP_LOOKUPS_PER_ACCOUNT]
    if seen and seen[0][1] not in ips:
        ips.append(seen[0][1])
    return ips


def users_table(order, accounts, infos, fields, bbb, compute_minutes, banned, sort_caption, invert, table_rows, csv_path, repeat_header, show_stats,
                rl_lines, logs_read, sorted_field=None):
    """2.67: --table (compact table, colors), --csv FILE (every field, every value, « ; » separator for Excel), --stats (members per group, systems,
    browsers, countries, e-mail domains, internal / portal, top 10 of the most active accounts)."""
    today = datetime.date.today().isoformat()

    def main_one(v):
        return max(v["ips"], key=lambda i: (v["ips"][i], i))

    def mb_value(n):
        return None if n is None else n / 1_000_000

    rows, styles, records = [], [], []
    number_columns = {k: [] for k in ("logins", "minutes", "read", "written", "received", "sent", "events", "surveys")}
    for ordinal, name in enumerate(order, 1):
        v, f = accounts[name], infos[name]
        p = f.get("profile") or {}
        others = len(v["ips"]) - 1
        record = {"num": ordinal, "uid": f["uid"] or "", "ip": main_one(v), "ips": v["ips"], "name": f["nom"], "login": name, "first": v["premiere"],
                  "last": v["derniere"], "logins": v["n"], "minutes": f["minutes"], "type": TR(f["type"]) if f["type"] else "", "events": p.get("events"),
                  "surveys": p.get("surveys"), "phone": p.get("phone", ""), "country": p.get("country", ""), "country_name": p.get("country_name", ""),
                  "city": p.get("city", ""), "groups": p.get("groups", []), "tags": p.get("tags", []), "os": f["os"], "nav": f["nav"],
                  "read": None if bbb else f["pages"], "written": None if bbb else f["written"], "received": None if bbb else f["received"],
                  "sent": None if bbb else f["sent"], "email": p.get("email", ""), "seen": f.get("seen", []), "created": p.get("created"),
                  "owners": f.get("owners", []), "ipcountry": f.get("countries", []), "vpn": f.get("vpn")}
        records.append(record)
        for k in number_columns:
            number_columns[k].append(record[k] or 0)
        shown = {"num": ordinal, "uid": f["uid"] or "-", "ip": record["ip"] + (f" +{others}" if others else ""), "name": f["nom"], "login": name,
                 "first": v["premiere"], "last": v["derniere"], "logins": v["n"], "minutes": "-" if f["minutes"] is None else f["minutes"],
                 "type": (record["type"] or "-").split("/")[0], "events": "-" if record["events"] is None else record["events"],
                 "surveys": "-" if record["surveys"] is None else record["surveys"], "phone": record["phone"] or "-", "country": record["country"] or "-",
                 "city": record["city"] or "-", "groups": ",".join(record["groups"]) or "-", "tags": ",".join(record["tags"]) or "-",
                 "systems": compact_names(f["os"]), "browsers": compact_names(f["nav"]), "read": "-" if bbb else f["pages"], "written": "-" if bbb else f["written"],
                 "received": "-" if bbb else megabytes(f["received"]), "sent": "-" if bbb else ("?" if f["sent"] is None else megabytes(f["sent"])),
                 "email": record["email"] or "-",
                 "created": time.strftime("%Y-%m-%d", time.localtime(record["created"])) if record["created"] else "-",
                 "ipcountry": ",".join(record["ipcountry"]) or ("?" if any(public_address(ip) for ip, _ in record["owners"]) else "-"),
                 "vpn": f"{TR(record['vpn'][0])} {record['vpn'][1]}" if record["vpn"] else "-",
                 "ipseen": (f"{record['seen'][0][1]} {seen_text(record['seen'][0][0])}" + (f" +{len(record['seen']) - 1}" if len(record["seen"]) > 1 else ""))
                           if record["seen"] else "-"}
        rows.append([shown[k] for k in fields])
    level = {k: level_styles(vals) for k, vals in number_columns.items()}
    for record in records:
        style = {"logins": level["logins"](record["logins"]), "minutes": level["minutes"](record["minutes"] or 0),
                 "read": level["read"](record["read"] or 0), "written": level["written"](record["written"] or 0),
                 "received": level["received"](record["received"] or 0), "sent": None if record["sent"] is None else level["sent"](record["sent"]),
                 "events": level["events"](record["events"] or 0), "surveys": level["surveys"](record["surveys"] or 0),
                 "last": "32" if record["last"].startswith(today) else None,                   # logged in today (bold green)
                 "first": "36" if record["first"].startswith(today) else None,                 # new account today (bold cyan)
                 "ip": "35" if record["ip"] in banned else None,
                 "ipseen": "32" if record["seen"] and seen_text(record["seen"][0][0], False).startswith(today) else None,      # seen today on the site
                 "type": "36" if record["type"] and record["type"] != TR("interne") else None,
                 "created": "36" if record["created"] and time.time() - record["created"] < NEW_ACCOUNT_DAYS * 86400 else None,     # 2.70: new account
                 "ipcountry": "0;33" if record["country"] and record["ipcountry"] and record["ipcountry"][0] != record["country"].upper() else None,
                 "vpn": None if not record["vpn"] else "33" if VPN_PRIORITY[record["vpn"][0]] >= 4 else "0;33"}
        styles.append([style.get(k) for k in fields])
    if table_rows:
        print(f"Sort: {sort_caption}{' (reversed order)' if invert else ''}. Fields: {literal(','.join(fields))} (--table-fields to choose; all: every field).")
        print()
        for l in compact_table(fields, rows, styles, repeat_header, sorted_field):
            print(l)
        print()
        total_minutes = sum(r["minutes"] or 0 for r in records)
        print(f"  Total: {len(records)} {'participant(s)' if bbb else 'account(s)'}, {sum(r['logins'] for r in records)} login(s)"
              + (f", {total_minutes} login minute(s) (≈ {total_minutes / 60:.1f} h)" if compute_minutes else ""))
        print("  (colors: last login today in green, account created today in cyan, the busiest accounts in yellow — bold: top 10 %; 0 in grey)")
        if "created" in fields:
            print(f"  (account created: date of creation of the Odoo account; cyan: less than {NEW_ACCOUNT_DAYS} days)")
        if "ipcountry" in fields:
            print("  (IP country: country of the owner of the address block according to RDAP / whois — the registry, not a geolocation; main address first;")
            print("   yellow: differs from the country of the Odoo contact; ?: owner unknown)")
        if "vpn" in fields:
            print("  (VPN: the owner of the block of one of the account's addresses is a known VPN, Tor, a relay (iCloud Private Relay, Cloudflare WARP)")
            print("   or a hosting company (data center: the exit of most VPNs and proxies) — a guess from the owner's name, not a proof:")
            print("   a VPN on a network of unknown name is not seen, a company or a school may go out through a data center)")
        if "ipseen" in fields:
            print("  (IP seen: the account's address with the latest request in the nginx logs, even without a new login to Odoo; green: today; +N: its other addresses seen)")
        if compute_minutes:
            print(f"  (estimated minutes: a login lasts as long as its IP address makes a request at least every {SESSION_PAUSE} minutes according to the nginx logs;")
            print("   overlapping logins count once; an address shared by several people inflates the estimate)")
            print("  (systems, browsers and pages viewed: User-Agent and pages of the account's IP addresses in the nginx logs; Windows 10 and 11 look the same;")
            print("   robots and tools are not counted; an address shared by several people mixes their systems)")
            print("  (pages written: forms and records sent (POST, PUT, DELETE), not the reads of the Odoo web client nor the chat;")
            print("   MB received: what nginx sent to the account; MB sent: size of its requests — « ? » if the nginx log has no « rl= » field (nginx-odoo-config 1.11))")
        if logs_read and not rl_lines and not bbb and "sent" in fields:
            print(f"  {BAD}MB sent: « ? » because NO line of the nginx logs read has the « rl= » field: deploy nginx-odoo-config 1.11 (log_format combined_host with "
                  f"rl=$request_length), then nginx -t and systemctl reload nginx — only the requests logged after that count{END_BAD}")
        banned_t = sorted({i for r in records for i in r["ips"] if i in banned})
        if banned_t:
            print(f"  {BAD}⚠ banned address(es) of logged-in users: {', '.join(banned_t)} — nginx-log-audit.sh --unban-check{END_BAD}")
    if csv_path:
        code = write_users_csv(csv_path, records, fields)
        if code:
            return code
    if show_stats:
        print_user_stats(records, bbb)
    return 0


CSV_FIELDS = (("num", "N°", "#"), ("uid", "UID", "UID"), ("login", "Identifiant", "Login"), ("name", "Nom", "Name"), ("email", "Courriel", "E-mail"),
              ("type", "Type", "Type"), ("ip", "Adresse IP principale", "Main IP address"), ("ips", "Adresses IP (connexions)", "IP addresses (logins)"),
              ("ipseen", "Adresses IP vues (dernière requête)", "IP addresses seen (last request)"),
              ("ipcountry", "Pays des adresses IP (RDAP/whois)", "Country of the IP addresses (RDAP/whois)"), ("vpn", "VPN, Tor, relais, hébergeur", "VPN, Tor, relay, hosting"),
              ("created", "Compte créé", "Account created"), ("first", "Première connexion", "First login"), ("last", "Dernière connexion", "Last login"),
              ("logins", "Connexions", "Logins"),
              ("minutes", "Minutes", "Minutes"), ("events", "Événements", "Events"), ("surveys", "Sondages", "Surveys"), ("phone", "Téléphone", "Phone"),
              ("country", "Pays", "Country"), ("country_name", "Nom du pays", "Country name"), ("city", "Ville", "City"), ("groups", "Groupes", "Groups"),
              ("tags", "Étiquettes", "Tags"), ("systems", "Systèmes (requêtes)", "Systems (requests)"), ("browsers", "Navigateurs (requêtes)", "Browsers (requests)"),
              ("read", "Pages lues", "Pages read"), ("written", "Pages écrites", "Pages written"), ("received", "Mo reçus", "MB received"), ("sent", "Mo envoyés", "MB sent"))
CSV_OF_FIELD = {"ip": ("ip", "ips"), "country": ("country", "country_name"), "systems": ("systems",), "browsers": ("browsers",)}


def write_users_csv(path, records, fields):
    """2.67: --csv FILE (« - »: standard output): EVERY value, never cut — all the IP addresses with their number of logins (« , » between the values of a cell), all the groups and tags, the
    systems and browsers with their number of requests, MB with 3 decimals; « ; » separator, UTF-8 with BOM, decimal comma in French: Excel opens it
    as it is. Columns: those of --table-fields when given (each with its full detail), otherwise all."""
    import csv
    keys = [c[0] for c in CSV_FIELDS]
    if fields and fields != DEFAULT_TABLE_FIELDS:
        wanted = [x for k in fields for x in CSV_OF_FIELD.get(k, (k,))]
        keys = [k for k in wanted if k in keys]
    titles = {c[0]: (c[2] if LANGUAGE == "en" else c[1]) for c in CSV_FIELDS}

    def counts(counter):
        return ", ".join(f"{n} ({c})" for n, c in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))

    def value(r, k):
        if k == "ips":
            return ", ".join(f"{ip} ({n})" for ip, n in sorted(r["ips"].items(), key=lambda kv: (-kv[1], kv[0])))
        if k == "ipseen":
            return ", ".join(f"{ip} ({seen_text(m, False)})" for m, ip in r["seen"])
        if k in ("groups", "tags"):
            return ", ".join(r[k])
        if k == "created":
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created"])) if r["created"] else ""
        if k == "ipcountry":
            return ", ".join(f"{ip} ({(o.get('pays') or '?').upper()} {o.get('organisation') or o.get('reseau') or ''})".replace(" )", ")") if o else f"{ip} (?)"
                             for ip, o in r["owners"] if public_address(ip))
        if k == "vpn":
            return ", ".join(f"{ip} ({TR(kv[0])} {kv[1]})" for ip, o in r["owners"] for kv in [vpn_kind(o)] if kv)
        if k == "systems":
            return counts(r["os"])
        if k == "browsers":
            return counts(r["nav"])
        if k in ("received", "sent"):
            return csv_number(mb_or_none(r[k]), 3)
        if k in ("logins", "minutes", "events", "surveys", "read", "written", "num"):
            return csv_number(r[k])
        return r[k] if r[k] is not None else ""
    try:
        f = sys.stdout if path == "-" else open(path, "w", encoding="utf-8-sig", newline="")
    except OSError as e:
        eprint(f"ERROR: CSV file not writable: {path} ({e})")
        return 1
    try:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        w.writerow([titles[k] for k in keys])
        for r in records:
            w.writerow([value(r, k) for k in keys])
    finally:
        if f is not sys.stdout:
            f.close()
    if path != "-":
        print(f"CSV written: {os.path.abspath(path)} — {len(records)} line(s), {len(keys)} column(s), separator « ; » (Excel: open it directly)")
    return 0


def mb_or_none(n):
    return None if n is None else n / 1_000_000


def print_user_stats(records, bbb):
    """2.67: --stats: members per group, operating systems, browsers, countries, e-mail domains, internal / portal accounts, then the top 10 of the most
    active accounts by logins, minutes, pages read, pages written, MB received, events and surveys. Percentages of the accounts listed."""
    n = len(records)
    if not n:
        return

    def section(title, counter, limit=15, unit="account(s)"):
        print(f"  {color_code('1', title)}" + ("" if counter else " : -"))
        width = max([display_width(str(k)) for k in counter] or [0])
        for k, c in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[:limit]:
            print(f"    {str(k)}{' ' * (width - display_width(str(k)))}  {c:>5} {unit} ({100 * c / n:.0f} %)")
        if len(counter) > limit:
            print(f"    … (+{len(counter) - limit})")
    print()
    print(color_code("1;36", f"──── Statistics of the {n} {'participant(s)' if bbb else 'account(s)'} listed ────"))
    if not bbb:
        section("Members per group", collections.Counter(g for r in records for g in r["groups"]))
        section("Members per tag", collections.Counter(t for r in records for t in r["tags"]))
        section("Internal / portal", collections.Counter(r["type"] or "?" for r in records))
        section("Countries (Odoo contact)", collections.Counter(r["country"] or "?" for r in records))
    if any(r["owners"] for r in records):                                   # 2.70: owners of the address blocks looked up
        section("Countries (main IP address, RDAP/whois)", collections.Counter((r["ipcountry"] or ["?"])[0] for r in records))
        section("VPN, Tor, relay, hosting", collections.Counter(f"{TR(r['vpn'][0])} {r['vpn'][1]}" for r in records if r["vpn"]))
    section("E-mail domains", collections.Counter(((r["email"] or r["login"]).rpartition("@")[2].lower() or "?") for r in records))
    section("Operating systems", collections.Counter(s for r in records for s in r["os"]))
    section("Browsers", collections.Counter(b for r in records for b in r["nav"]))
    print(f"  {color_code('1', 'Top 10 of the most active accounts')}")
    metrics = (("logins", TR("number of logins"), str), ("minutes", TR("login minutes"), str), ("read", TR("pages read"), str), ("written", TR("pages written"), str),
               ("received", TR("MB received"), megabytes), ("events", TR("event registrations"), str), ("surveys", TR("surveys completed"), str))
    width = max(display_width(t) for _, t, _ in metrics)                # titles translated BEFORE padding: aligned in every language
    for key_value, title, fmt in metrics:
        top = sorted((r for r in records if r.get(key_value)), key=lambda r: (-r[key_value], r["login"]))[:10]
        if top:
            print(f"    {title}{' ' * (width - display_width(title))}  " + " · ".join(f"{r['name'] or r['login']} {color_code('36', fmt(r[key_value]))}" for r in top))


def list_users(details=False, table_rows=False, sort_order="name", invert=False, fields=None, group=None, csv_path=None, repeat_header=False, show_stats=False):
    """--list-users: all the logins of the available history, in alphabetical order (--details: traffic of
    each account — pages, errors, modules, busiest day — taken from the nginx logs, slower to compute). Odoo: successful
    logins from the systemd journal ("Login successful … login:ACCOUNT from IP"); BigBlueButton: participation links
    (/bigbluebutton/api/join?fullName=…) in the nginx logs and their rotations."""
    accounts, bbb = {}, PROFILE.get("APP_NAME") == "bbb"
    def note(display_name, ip, when, database=None, minute=None):
        v = accounts.setdefault(display_name, {"n": 0, "ips": {}, "premiere": when, "derniere": when, "bases": set(), "connexions": []})
        if database:
            v["bases"].add(database)
        if minute is not None:
            v["connexions"].append((minute, ip))
        v["n"] += 1
        v["ips"][ip] = v["ips"].get(ip, 0) + 1
        v["premiere"], v["derniere"] = min(v["premiere"], when), max(v["derniere"], when)
    if not bbb:
        svc, ns = detect_odoo_service()
        if not svc:
            eprint("ERROR: application service not found (systemd journal).")
            return 2
        since = ["--since", f"{datetime.date.today() - datetime.timedelta(days=DAYS - 1)}"] if DAYS_GIVEN else []
        code, out = run(["journalctl", "-u", svc, "-o", "short-iso", "--no-pager", "-q", "--grep", "Login successful for"]
                        + since + (["--namespace", ns] if ns else []), timeout=600)
        for text_line in truncate(out.splitlines()):
            m = re.search(r"Login successful for db:(\S+) login:(\S+) from (\S+)", text_line)
            if m:
                minute = journal_minute(text_line)
                note(m.group(2), m.group(3), text_line[:16].replace("T", " "), m.group(1), minute)
        source = (f"systemd journal of {svc}, {DAYS} last days" if DAYS_GIVEN else
                  f"systemd journal of {svc} (since {first_journal_date(svc, ns) or '?'})")
    # Traffic statistics: all the nginx logs of the site and their rotations (whole history kept).
    want_agents = table_rows or csv_path or show_stats or sort_order in ("os", "pages", "written", "received", "sent")                           # systems, browsers, pages viewed (User-Agent of the nginx logs)
    compute_minutes = (want_agents or sort_order == "minutes") and not bbb              # login minutes: activity of the addresses in the nginx logs
    stats, tracked_ips = {}, ({i for v in accounts.values() for i in v["ips"]} if (details or compute_minutes) else set())
    activity, cached_minutes, nginx_logs_read = {}, {}, []
    rl_lines = [0]                        # 2.67: lines with « rl= » (size of the request): without any, « MB sent » cannot be known
    ip_agents = {}                        # --table: {address: {"os": {name: n}, "nav": {name: n}, "pages": n}} (User-Agent and pages of the accounts' addresses)
    bbb_agents = {}                       # BigBlueButton: {participant: same dict}, from the User-Agent of the join link
    if bbb or tracked_ips:                    # nginx logs: participants (BBB), traffic of the accounts (--details, --table)
        databases = sorted({b for pattern in PROFILE.get("ACCESS_LOGS", "*-access.log").split() for b in glob.glob(os.path.join(NGINX_DIR, pattern))})
        nginx_logs_read = []
        for database in databases:
            for path in _rotations(database):
                try:
                    f = gzip.open(path, "rt", errors="replace") if path.endswith(".gz") else open(path, errors="replace")
                except OSError:
                    continue
                nginx_logs_read.append(path)
                with f:
                    for text_line in truncate(f):
                        m = ACCESS_RE.match(text_line)
                        if not m:
                            continue
                        day = datetime.datetime.strptime(m.group(2), "%d/%b/%Y").date()
                        if DAYS_GIVEN and (datetime.date.today() - day).days >= DAYS:
                            continue
                        if bbb and m.group(4).startswith("/bigbluebutton/api/join?") and m.group(5)[0] in "23":
                            q = urllib.parse.parse_qs(m.group(4).split("?", 1)[1])
                            participant = (q.get("fullName") or ["(no name)"])[0][:40]
                            note(participant, m.group(1), f"{day:%Y-%m-%d}")
                            if want_agents:
                                tally_agent(bbb_agents, participant, m.group(7), False)
                        if m.group(9):
                            rl_lines[0] += 1
                        if compute_minutes and m.group(1) in tracked_ips:
                            tally_agent(ip_agents, m.group(1), m.group(7), m.group(3) == "GET" and m.group(5)[0] == "2" and not ASSET_RE.search(m.group(4)),
                                        m.group(3) in WRITE_METHODS and m.group(5)[0] in "23" and not NOT_A_WRITE_RE.match(m.group(4)),
                                        int(m.group(6)) if (m.group(6) or "").isdigit() else 0, int(m.group(9)) if m.group(9) else None)
                            h = TIME_RE.search(text_line)
                            if h:
                                key_h = h.group(1) + " " + h.group(2)
                                mn = cached_minutes.get(key_h)
                                if mn is None:
                                    try:
                                        mn = cached_minutes[key_h] = int(datetime.datetime.strptime(key_h, "%d/%b/%Y:%H:%M %z").timestamp() // 60)
                                    except ValueError:
                                        mn = -1
                                if mn >= 0:
                                    activity.setdefault(m.group(1), set()).add(mn)
                        if details and (bbb or m.group(1) in tracked_ips):
                            accumulate_ip(stats, m.group(1), m.group(3), m.group(4), m.group(5), day, [2])
    if bbb:
        source = "join links from the nginx logs and their rotations"
    logs_read = nginx_logs_read if (bbb or tracked_ips) else []
    banned = set()
    try:
        for l in open(os.path.join(CHK_STATE, "bans.tsv"), encoding="utf-8"):
            cols = l.rstrip("\n").split("\t")              # 2.68: NOT « fields » (that name holds the --table-fields columns: KeyError on a date)
            if len(cols) >= 3 and cols[1] in ("banni", "leve"):    # 2.73: other events (« justifie »: justification added later) change nothing
                (banned.add if cols[1] == "banni" else banned.discard)(cols[2])
    except OSError:
        pass
    print(f"{'BigBlueButton participants' if bbb else 'Connections to ' + PROFILE.get('APP_LABEL', 'Odoo')} — {source}")
    print(f"{len(accounts)} {'participant(s)' if bbb else 'account(s)'}, "
          + ("in alphabetical order" if sort_order == "name" and not invert else f"sorted by {USER_SORTS[sort_order][0]}{' (reversed order)' if invert else ''}"))
    if logs_read:
        print(f"nginx access logs read ({len(logs_read)} file(s), rotations included): {', '.join(logs_read[:4])}"
              + (f" … (+{len(logs_read) - 4})" if len(logs_read) > 4 else ""))
    elif compute_minutes or details:
        print(f"nginx access logs: no file read in {NGINX_DIR} ({PROFILE.get('ACCESS_LOGS', '*-access.log')}) — login minutes = 1 per login at minimum")
    print()
    if not accounts:
        print("  no login in the available history")
        return 0
    shared = shared_mark(accounts)
    needs_uid = (details or table_rows or csv_path or group or show_stats or sort_order in ("uid", "type", "events", "surveys", "created")) and not bbb
    odoo_users = read_odoo_users(accounts) if needs_uid else {}
    profiles = read_profiles(accounts) if needs_uid and (table_rows or csv_path or group or show_stats or sort_order in ("events", "surveys", "created")) else {}
    active_ones = {ip: sorted(m) for ip, m in activity.items()}
    infos = {}
    for display_name, v in accounts.items():
        sheets = [(odoo_users.get(b) or {}).get(display_name) for b in sorted(v["bases"])]
        sheets = [f for f in sheets if f]
        infos[display_name] = {"uid": " / ".join(str(f["uid"]) for f in sheets), "uid_n": min([int(f["uid"]) for f in sheets if str(f["uid"]).isdigit()] or [10 ** 12]),
                      "type": " / ".join(sorted({f["type"] for f in sheets})), "nom": next((f["nom"] for f in sheets if f["nom"]), display_name),
                      "minutes": login_minutes(v["connexions"], active_ones) if compute_minutes else None}
        sources_ua = [bbb_agents.get(display_name)] if bbb else [ip_agents.get(ip) for ip in v["ips"]]          # addresses of the account (BBB: the participant)
        infos[display_name].update({"os": {}, "nav": {}, "pages": 0, "written": 0, "received": 0, "sent": None})
        sheet = next(((profiles.get(b) or {}).get(display_name) for b in sorted(v["bases"]) if (profiles.get(b) or {}).get(display_name)), None)
        infos[display_name]["profile"] = sheet or {}
        # 2.69: addresses of the account SEEN in the nginx logs (any request, even without a new login to Odoo), most recent first: [(minute, address)]
        infos[display_name]["seen"] = sorted(((max(activity[ip]), ip) for ip in v["ips"] if activity.get(ip)), reverse=True)
        for a in (x for x in sources_ua if x):
            infos[display_name]["pages"] += a["pages"]
            infos[display_name]["written"] += a.get("written", 0)
            infos[display_name]["received"] += a.get("received", 0)
            if a.get("sent") is not None:
                infos[display_name]["sent"] = (infos[display_name]["sent"] or 0) + a["sent"]
            for kind in ("os", "nav"):
                for name, n in a[kind].items():
                    infos[display_name][kind][name] = infos[display_name][kind].get(name, 0) + n

    # 2.70: country and VPN from the owner of the address blocks (RDAP / whois), only when a column, the CSV or the sort needs them
    wanted = set(fields or DEFAULT_TABLE_FIELDS)
    csv_keys = set(FIELD_KEYS) if not fields or fields == DEFAULT_TABLE_FIELDS else wanted
    if (table_rows and wanted & {"ipcountry", "vpn"}) or (csv_path and csv_keys & {"ipcountry", "vpn"}) or sort_order == "vpn":
        lookups = {n: account_lookups(v, infos[n]["seen"]) for n, v in accounts.items()}
        owners = ip_owners({ip for ips in lookups.values() for ip in ips})
        for n, ips in lookups.items():
            f = infos[n]
            f["owners"] = [(ip, owners.get(ip)) for ip in ips]
            f["countries"] = list(dict.fromkeys((o.get("pays") or "").upper() for _, o in f["owners"] if o and o.get("pays")))
            kinds = [k for k in (vpn_kind(o) for _, o in f["owners"]) if k]
            f["vpn"] = max(kinds, key=lambda k: VPN_PRIORITY[k[0]]) if kinds else None

    def key_ip(ip):
        try:
            return (0, ipaddress.ip_address(ip).version, int(ipaddress.ip_address(ip)))
        except ValueError:
            return (1, 0, ip)

    def main_one(v):
        return max(v["ips"], key=lambda i: (v["ips"][i], i))
    key_list = {"logins": lambda n: accounts[n]["n"], "last": lambda n: accounts[n]["derniere"], "login": lambda n: n.casefold(),
            "ip": lambda n: key_ip(main_one(accounts[n])), "minutes": lambda n: infos[n]["minutes"] or 0, "name": lambda n: (infos[n]["nom"] if table_rows else n).casefold(),
            "first": lambda n: accounts[n]["premiere"], "type": lambda n: infos[n]["type"], "uid": lambda n: infos[n]["uid_n"],
            "os": lambda n: top_names(infos[n]["os"], 1).casefold(), "pages": lambda n: infos[n]["pages"], "written": lambda n: infos[n]["written"],
            "received": lambda n: infos[n]["received"], "sent": lambda n: infos[n]["sent"] or 0,
            "events": lambda n: infos[n]["profile"].get("events", 0), "surveys": lambda n: infos[n]["profile"].get("surveys", 0),
            "seen": lambda n: infos[n]["seen"][0][0] if infos[n]["seen"] else 0, "created": lambda n: infos[n]["profile"].get("created") or 0,
            "vpn": lambda n: VPN_PRIORITY[infos[n]["vpn"][0]] if infos[n].get("vpn") else 0}
    if group:                                         # 2.67: --group NAME: only the members of that Odoo group (exact name, otherwise part of the name; accents ignored)
        wanted = plain_text(group)
        names = {g for f in infos.values() for g in f["profile"].get("all_groups", [])} | {g for p in profiles.values() for f in (p or {}).values() for g in f.get("all_groups", [])}
        chosen = {g for g in names if plain_text(g) == wanted} or {g for g in names if wanted in plain_text(g)}
        if not chosen:
            print(f"No Odoo group named « {group} »" + (f" (groups: {', '.join(sorted(n for n in names if n.upper().startswith('RLQ'))[:20]) or ', '.join(sorted(names)[:20])})" if names
                                                         else " (PostgreSQL unreadable: root required?)"))
            return 1
        accounts = {n: v for n, v in accounts.items() if chosen & set(infos[n]["profile"].get("all_groups", []))}
        members = {login for p in profiles.values() for login, f in (p or {}).items() if chosen & set(f.get("all_groups", []))}
        absent = sorted(members - set(accounts))
        print(f"Group {', '.join(sorted(chosen))} — {len(accounts)} member(s) with a login in the history"
              + (f", {len(absent)} member(s) without any login: {', '.join(absent[:10])}{' …' if len(absent) > 10 else ''}" if absent else ""))
        print()
        if not accounts:
            return 0
    sort_caption, direction, _ = USER_SORTS[sort_order]
    order = sorted(accounts, key=lambda n: (n.casefold(), n))                       # stable base: alphabetical, then the requested key
    order.sort(key=key_list[sort_order], reverse=(direction < 0) != bool(invert))
    if table_rows or csv_path or show_stats:
        return users_table(order, accounts, infos, fields or DEFAULT_TABLE_FIELDS, bbb, compute_minutes, banned, sort_caption, invert,
                           table_rows, csv_path, repeat_header, show_stats, rl_lines[0], bool(logs_read), SORT_FIELD.get(sort_order))
    for display_name in order:
        v = accounts[display_name]
        ips = ", ".join(color_code("35", f"{i} (banned)") if i in banned else f"{i} (shared: {shared_text(shared[i])})" if i in shared else i
                        for i in sorted(v["ips"], key=lambda i: -v["ips"][i]))
        print()
        print(f"  {color_code('1', display_name)}")
        print(f"    Logins          : {color_code('32', v['n'])} (first {v['premiere']}, last {v['derniere']})")
        print(f"    IP addresses    : {ips}")
        if details and not bbb:
            for text_line in uid_lines(display_name, v["bases"], odoo_users):
                print(f"    {text_line}")
        if details:
            for text_line in detail_lines(aggregate_ips(stats, v["ips"]), day_count=5):
                print(f"    {text_line}")
    print()
    if details:
        print("  (details: traffic of the account's IP addresses in all the nginx logs kept — an address shared")
        print("   by several accounts counts in full for each)")
    else:
        print("  (traffic of each account — pages, errors, modules, busiest day: web-monitor.py --list-users --details)")
    banned_ips = sorted({i for v in accounts.values() for i in v["ips"] if i in banned})
    if banned_ips:
        print()
        print(f"  {BAD}⚠ banned address(es) of logged-in users: {', '.join(banned_ips)} — nginx-log-audit.sh --unban-check{END_BAD}")
    return 0


# --- 2.65: suspicious activity of LOGGED-IN users (an account is not a proof of good faith), investigation, ban and watch of an Odoo account ---------
ACCESS_DENIED_RE = re.compile(r"Access Denied by (ACLs|record rules) for operation: \w+.*?uid: (\d+), model: ([\w.]+)")
PASSWORD_RESET_RE = re.compile(r"Password reset attempt for <([^>]*)>")
LOGIN_FAILED_RE = re.compile(r"Login failed for db:\S+ login:(\S+) from")
LOGIN_HISTORY_CACHE = {}
# Weight of each sign in the suspicion score; 2-3 = to watch, SUSPECT_LEVEL or more = suspicious. Each sign alone has an innocent explanation
# (a burst = several tabs opened at once; a new account = a new member): only their SUM deserves attention, and an investigation before any ban.
SUSPICION_WEIGHTS = {"malicious": 3, "burst": 2, "tool": 2, "denied": 2, "posts": 2, "farm": 2, "banned_ip": 2, "disposable": 2,
                     "failures": 1, "resets": 1, "many_ips": 1, "errors": 1, "new": 1, "email": 1}
WATCH_LEVEL, SUSPECT_LEVEL = 2, 4
NEW_ACCOUNT_DAYS = 7
DENIED_MIN, POSTS_PER_DAY_MIN, FAILURES_MIN, RESETS_MIN, MANY_IPS_MIN, FARM_ACCOUNTS_MIN = 3, 20, 5, 3, 6, 3


def registered_odoo_users():
    """{"banned": {login: event}, "watched": {login: event}} of the register apps/_odoo_users.py; empty if the component is missing."""
    try:
        return _load_module("_odoo_users").state()
    except Exception:
        return {"banned": {}, "watched": {}}


def email_module():
    try:
        return _load_module("_email_check")
    except Exception:
        return None


def odoo_db_module():
    path = os.path.join(SCRIPT_DIR, "apps", "_odoo_db.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("_odoo_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.VERBOSE = VERBOSE
    return module


def login_history():
    """{login: {"bases": set, "ips": {ip: n}, "first": "YYYY-MM-DD HH:MM", "last": …, "n": logins}} over the WHOLE systemd journal (Odoo); {} elsewhere.
    Reuses the output already read by logged_in_ips(None) during the same run."""
    out = LOGIN_HISTORY_CACHE.get("out")
    if out is None:
        if PROFILE.get("APP_LOG_KIND") != "journal":
            return {}
        svc, ns = detect_odoo_service()
        if not svc:
            return {}
        _, out = run(["journalctl", "-u", svc, "-o", "short-iso", "--no-pager", "-q", "--grep", "Login successful for"] + (["--namespace", ns] if ns else []),
                     timeout=300)
        LOGIN_HISTORY_CACHE["out"] = out
    res = {}
    for line in out.splitlines():
        m = re.search(r"Login successful for db:(\S+) login:(\S+) from (\S+)", line)
        if not m:
            continue
        when = line[:16].replace("T", " ")
        v = res.setdefault(m.group(2), {"bases": set(), "ips": {}, "first": when, "last": when, "n": 0})
        v["bases"].add(m.group(1))
        v["ips"][m.group(3)] = v["ips"].get(m.group(3), 0) + 1
        v["first"], v["last"], v["n"] = min(v["first"], when), max(v["last"], when), v["n"] + 1
    return res


def suspicion(login, acc, facts, user, history, shared, banned_ips):
    """(score, [reasons]) of a logged-in account over the period of the summary. `acc`: entry of facts["comptes"]; `user`: {uid, nom, type} or None;
    `history`: entry of login_history(); `shared`: {ip: number of accounts | place}; `banned_ips`: banned addresses. Reasons in English (translated at display)."""
    a = aggregate_ips(facts.get("stats_ip", {}), acc["ips"])
    reasons, score = [], 0

    def add(key, text):
        nonlocal score
        score += SUSPICION_WEIGHTS[key]
        reasons.append(f"+{SUSPICION_WEIGHTS[key]} {text}")
    if a["bad"]:
        add("malicious", f"malicious URLs requested: {a['bad']} (sensitive files, injections, PHP…)")
    if a["burst"] >= BURST_PAGES:
        add("burst", f"burst: {a['burst']} pages in {BURST_WINDOW_S} s ({a['burst_when']}) — a person reads one page at a time")
    if a["tools"]:
        add("tool", f"scripting tool in the User-Agent: {a['tools']} request(s) (curl, python-requests…)")
    uid = str((user or {}).get("uid", ""))
    denied = facts.get("odoo_denied", {}).get(uid, {}) if uid else {}
    if sum(denied.values()) >= DENIED_MIN:
        add("denied", f"Odoo access refused: {sum(denied.values())} time(s) ({', '.join(f'{k} ×{n}' for k, n in sorted(denied.items(), key=lambda x: -x[1])[:3])}) — tries to read what it may not")
    days_active = max(1, len(a["days"]))
    n_posts = sum(a["posts"].values())
    if n_posts >= POSTS_PER_DAY_MIN * days_active or n_posts >= POSTS_PER_DAY_MIN * 3:
        add("posts", f"forms submitted: {n_posts} ({', '.join(f'{k} ×{n}' for k, n in sorted(a['posts'].items(), key=lambda x: -x[1])[:3])})")
    failures = facts.get("login_failures", {}).get(login, 0)
    if failures >= FAILURES_MIN:
        add("failures", f"failed logins with this login: {failures}")
    resets = facts.get("password_resets", {}).get(login, 0)
    if resets >= RESETS_MIN:
        add("resets", f"password reset requests: {resets}")
    if len(acc["ips"]) >= MANY_IPS_MIN:
        add("many_ips", f"{len(acc['ips'])} different IP addresses")
    if (user or {}).get("type") != "interne":
        farm = [ip for ip in acc["ips"] if isinstance(shared.get(ip), int) and shared[ip] >= FARM_ACCOUNTS_MIN and not in_whitelist(ip)]
        if farm:
            add("farm", f"address shared with {max(shared[ip] for ip in farm) - 1} other account(s): {', '.join(farm[:3])} (several accounts from one place)")
    on_banned = [ip for ip in acc["ips"] if ip in banned_ips]
    if on_banned:
        add("banned_ip", f"uses banned address(es): {', '.join(on_banned[:3])}")
    if a["req"] >= 50 and sum(n for k, n in a["err"].items() if k.startswith("4")) * 100 >= 30 * a["req"]:
        add("errors", f"{sum(n for k, n in a['err'].items() if k.startswith('4'))} client errors (4xx) out of {a['req']} requests")
    first = (history or {}).get("first", "")
    if first and first[:10] >= (datetime.date.today() - datetime.timedelta(days=NEW_ACCOUNT_DAYS - 1)).isoformat():
        add("new", f"new account: first login {first}")
    em = email_module()
    if em and "@" in login:
        chk = em.check(login)
        if chk["disposable"]:
            add("disposable", f"disposable e-mail address ({chk['domain']})")
        elif chk["reason"]:
            add("email", f"login e-mail address: {chk['reason']}")
    return score, reasons


def suspects_list(facts, banned_ips):
    """[(score, login, acc, user, history, reasons)] of the accounts to show: score >= WATCH_LEVEL, or watched; banned accounts excluded
    (already handled). Internal accounts are scored too (never trust an account blindly) but are never offered for a ban."""
    accounts = facts.get("comptes") or {}
    if not accounts or PROFILE.get("APP_NAME") == "bbb":
        return []
    reg = registered_odoo_users()
    history = login_history()
    for login, v in accounts.items():               # databases from the whole history (the summary may not have seen the login line)
        v.setdefault("bases", set()).update((history.get(login) or {}).get("bases", set()))
    users = {}
    for database, table in (read_odoo_users(accounts) or {}).items():
        for login, info in (table or {}).items():
            users.setdefault(login, info)
    shared = shared_mark(accounts)
    res = []
    for login, acc in accounts.items():
        if login in reg["banned"]:
            continue
        score, reasons = suspicion(login, acc, facts, users.get(login), history.get(login), shared, banned_ips)
        if score >= WATCH_LEVEL or login in reg["watched"]:
            res.append((score, login, acc, users.get(login), history.get(login), reasons))
    return sorted(res, key=lambda x: (-x[0], x[1]))


def level_text(score):
    return "SUSPICIOUS" if score >= SUSPECT_LEVEL else "to watch" if score >= WATCH_LEVEL else "low"


def show_suspects(facts, banned_ips):
    """Summary section: logged-in accounts whose activity deserves a look (score), and the watched accounts; offers the investigation."""
    if PROFILE.get("APP_NAME") == "bbb" or PROFILE.get("APP_LOG_KIND") != "journal":
        return []
    suspects = suspects_list(facts, banned_ips)
    reg = registered_odoo_users()
    print()
    print(f"SUSPICIOUS ACTIVITY OF LOGGED-IN USERS — an account is not a proof of good faith ({duration(DAYS)})")
    if not suspects:
        print("  none: no logged-in account shows signs of misuse (burst, tools, refused accesses, forms in bulk, malicious URLs…)")
    for score, login, acc, user, hist, reasons in suspects[:15]:
        style = "31" if score >= SUSPECT_LEVEL else "33" if score >= WATCH_LEVEL else "0"
        who = f"{(user or {}).get('nom') or login}" + (f" (UID {user['uid']}, {TR(user['type'])})" if user else "")
        marks = (" [watched]" if login in reg["watched"] else "")
        print()
        print(f"  {color_code(style, '▶ ' + login)} — {who} — score {score} — {color_code(style, level_text(score))}{marks}")
        first = (hist or {}).get("first", "?")
        print(f"      first login {first} · {(hist or {}).get('n', sum(acc['n']))} login(s) · IP: {', '.join(sorted(acc['ips'], key=lambda i: -acc['ips'][i])[:4])}"
              + (f" (+{len(acc['ips']) - 4})" if len(acc["ips"]) > 4 else ""))
        for r in reasons:
            print(f"      {r}")
        if not reasons:
            print("      no sign over the period (account watched: its activity is listed here at every summary)")
    if len(suspects) > 15:
        print(f"\n  (+{len(suspects) - 15} other(s): web-monitor.py --suspect-users)")
    print()
    print(f"  (score = sum of the signs; {WATCH_LEVEL}-{SUSPECT_LEVEL - 1}: to watch, {SUSPECT_LEVEL} and more: suspicious. Each sign alone can be innocent: investigate before banning.)")
    if suspects:
        print("  Investigation of an account (all its addresses, e-mail, Internet), then ban or watch: web-monitor.py --suspect-users")
        add_action(f"Investigate the {len(suspects)} account(s) to watch or suspicious (all their addresses, their e-mail; ban or watch each one)",
                   "web-monitor.py --suspect-users", lambda: suspect_menu(suspects, yes=YES))
    return suspects


def suspect_users(yes=False, internet=None):
    """--suspect-users: the suspicious accounts of the period (same computation as the summary), then the menu: investigate, ban, watch."""
    if PROFILE.get("APP_LOG_KIND") != "journal" or PROFILE.get("APP_NAME") == "bbb":
        print("Odoo accounts only: nothing to examine on this server.")
        return 0
    periods = Periods(datetime.date.today())
    _c, _sources, facts, banned, _svc, _ns, _unreadable = collect_summary(periods)
    suspects = show_suspects(facts, banned)
    ACTIONS.clear()
    if not suspects:
        return 0
    return suspect_menu(suspects, yes=yes, internet=internet)


def suspect_menu(suspects, yes=False, internet=None):
    """Numbered list; [N] investigates account N (then offers ban / watch), [a] investigates them all, Enter quits. Without a terminal or with --yes:
    every account investigated, nothing banned (a ban is never decided without a person)."""
    if yes or NO_PROMPT or not (sys.stdin.isatty() and sys.stdout.isatty()):
        for _score, login, *_ in suspects:
            investigate_user(login, ask=False, internet=bool(internet))
        print("\nNo account banned without a question: web-monitor.py --ban-odoo-user LOGIN (investigation, then confirmation).")
        return 0
    while True:
        print()
        for i, (score, login, *_rest) in enumerate(suspects, 1):
            print(f"  [{i}] {login} — score {score} ({level_text(score)})")
        try:
            rep = input("Investigate which account? [number]  [a] all  [Enter] quit: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if not rep:
            return 0
        chosen = list(range(len(suspects))) if rep in ("a", "all", "t", "tous") else [int(rep) - 1] if rep.isdigit() and 1 <= int(rep) <= len(suspects) else []
        if not chosen:
            print("Unknown choice.")
            continue
        for i in chosen:
            investigate_user(suspects[i][1], ask=True, internet=internet)


def account_activity(login, ips, uid=None):
    """Activity of an account over the WHOLE history kept, for the investigation: requests of its addresses in the nginx logs (and their
    rotations) and its signs in the Odoo journal (refused accesses of its UID, password resets, failed logins). Returns (stats, facts) in the
    shape used by suspicion()."""
    stats, wanted = {}, set(ips)
    if wanted:
        databases = sorted({b for pattern in PROFILE.get("ACCESS_LOGS", "*-access.log").split() for b in glob.glob(os.path.join(NGINX_DIR, pattern))})
        for database in databases:
            for path in _rotations(database):
                try:
                    f = _open_log(path)
                except OSError:
                    continue
                with f:
                    for text_line in truncate(f):
                        if text_line.split(" ", 1)[0] not in wanted:
                            continue
                        m = ACCESS_RE.match(text_line)
                        if not m:
                            continue
                        try:
                            d = datetime.datetime.strptime(m.group(2), "%d/%b/%Y").date()
                        except ValueError:
                            continue
                        accumulate_ip(stats, m.group(1), m.group(3), m.group(4), m.group(5), d, [2], m.group(7) or "", request_second(text_line))
    facts = {"stats_ip": stats}
    svc, ns = detect_odoo_service() if PROFILE.get("APP_LOG_KIND") == "journal" else (None, "")
    if svc:
        _, out = run(["journalctl", "-u", svc, "-o", "short-iso", "--no-pager", "-q", "--grep", "Access Denied by|Password reset attempt|Login failed for"]
                     + (["--namespace", ns] if ns else []), timeout=300)
        for text_line in out.splitlines():
            ma = ACCESS_DENIED_RE.search(text_line)
            if ma and uid is not None and ma.group(2) == str(uid):
                facts.setdefault("odoo_denied", {}).setdefault(ma.group(2), {}).setdefault(ma.group(3), 0)
                facts["odoo_denied"][ma.group(2)][ma.group(3)] += 1
            mp = PASSWORD_RESET_RE.search(text_line)
            if mp and mp.group(1) == login:
                facts.setdefault("password_resets", {})[login] = facts.get("password_resets", {}).get(login, 0) + 1
            mf = LOGIN_FAILED_RE.search(text_line)
            if mf and mf.group(1) == login:
                facts.setdefault("login_failures", {})[login] = facts.get("login_failures", {}).get(login, 0) + 1
    return stats, facts


def _ts(epoch):
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M") if epoch else "-"


def investigate_user(login, ask=True, internet=None, offer_actions=True):
    """Investigation of an Odoo account BEFORE any decision: the account in Odoo (creation, logins, registrations, messages), ALL its IP addresses
    (nginx-log-audit.sh --investigate each), the other accounts on these addresses, its e-mail address (syntax, typo, disposable, mail server) and,
    with consent, the Internet (StopForumSpam, Gravatar, web search). Ends with a verdict and, on a terminal, the offer to ban or watch.
    Returns {"login", "db", "uid", "type", "ips", "points", "verdict", "internal", "active"} (None: account unknown)."""
    print()
    print("=" * 78)
    print(f" INVESTIGATION OF THE ODOO ACCOUNT {login}")
    print("=" * 78)
    history = login_history().get(login)
    ips = sorted((history or {}).get("ips", {}), key=lambda i: -history["ips"][i]) if history else []
    bases = sorted((history or {}).get("bases", set()))
    db = odoo_db_module()
    detail, database = None, None
    for b in bases or []:
        detail = db.user_detail(b, login) if db else None
        if detail:
            database = b
            break
    if not bases and db:                                   # never logged in according to the journal: look in every Odoo database
        for b in db.bases_odoo() or []:
            detail = db.user_detail(b, login)
            if detail:
                database = b
                break
    points, notes = 0, []

    def sign(n, text):
        nonlocal points
        points += n
        notes.append((n, text))
    print()
    print("[1] The account in Odoo")
    if detail is None:
        print("  PostgreSQL unreadable (root required, or database unreachable): account details unknown.")
    elif not detail:
        print(f"  no account with the login « {login} » in {', '.join(bases) or 'the Odoo databases'}.")
        if not history:
            return None
    else:
        kind = "portal/public" if detail["share"] else "internal"
        print(f"  {detail['name']} — UID {detail['uid']}, {TR(kind)}, database {database}, {'account active' if detail['active'] else color_code('35', 'ARCHIVED (cannot log in)')}")
        print(f"  created {_ts(detail['created'])}" + (f" through {detail['oauth']} (OAuth)" if detail["oauth"] else "")
              + f" · {detail['logins']} login(s) recorded by Odoo, last {_ts(detail['last_login'])}")
        if detail["email"] and detail["email"].lower() != login.lower():
            print(f"  contact e-mail: {detail['email']} (different from the login)")
        regs = detail["registrations"]
        print(f"  event registrations: {detail['registration_count']}" + (" — " + "; ".join(f"{_ts(t)[:10]} {ev} ({st})" for t, ev, st in regs[:4]) if regs else ""))
        if detail["messages_30d"] is not None:
            print(f"  messages posted (30 days): {detail['messages_30d']}" + ("  ⚠ many" if detail["messages_30d"] >= 20 else ""))
            if detail["messages_30d"] >= 20:
                sign(2, f"{detail['messages_30d']} messages posted in 30 days")
        if detail["survey_answers"] is not None:
            print(f"  survey answers: {detail['survey_answers']}")
        if time.time() - detail["created"] < NEW_ACCOUNT_DAYS * 86400 and not history:      # counted in [2b] (« new account ») when it logged in
            sign(1, f"account created less than {NEW_ACCOUNT_DAYS} days ago")
        if not detail["share"]:
            print(color_code("33", "  INTERNAL account (employee, volunteer with back-office access): never banned by this program — archive it in Odoo itself if needed."))
    print()
    print(f"[2] Its IP addresses ({len(ips)} in the whole journal)")
    others = {}
    hist_all = login_history()
    for ip in ips:
        others[ip] = sorted(l for l, v in hist_all.items() if l != login and ip in v["ips"])
    for i, ip in enumerate(ips[:10], 1):
        if VERBOSE or sys.stderr.isatty():
            eprint(f"  … {i}/{min(len(ips), 10)} : nginx-log-audit.sh --investigate {ip}")
        verdict, recommended = investigate_ip(ip)
        extra = f" — also used by: {', '.join(others[ip][:4])}" + (f" (+{len(others[ip]) - 4})" if len(others[ip]) > 4 else "") if others[ip] else ""
        place = lists().lieu(ip)
        tag = " (whitelist)" if in_whitelist(ip) else f" ({place.libelle})" if place else ""
        print(f"  {ip}{tag} — {history['ips'][ip]} login(s){extra}")
        if verdict:
            print(f"      {verdict}")
        if recommended:
            sign(2, f"{ip}: ban recommended by the investigation of the address")
        if len(others[ip]) >= FARM_ACCOUNTS_MIN - 1 and not in_whitelist(ip) and not (place and place.partagee):
            sign(2, f"{ip}: {len(others[ip]) + 1} accounts on the same address")
    if len(ips) > 10:
        print(f"  (+{len(ips) - 10} other address(es) not investigated)")
    print()
    print("[2b] Its activity on the site (nginx logs and Odoo journal, whole history kept)")
    stats, act_facts = account_activity(login, ips, (detail or {}).get("uid"))
    for text_line in detail_lines(aggregate_ips(stats, ips), day_count=5):
        print(f"  {text_line}")
    banned_now = set()
    user_row = {"uid": (detail or {}).get("uid", ""), "type": "interne" if detail and not detail["share"] else "portail/public"} if detail else None
    a_score, a_reasons = suspicion(login, {"ips": {ip: 1 for ip in ips}, "n": [0] * Periods.N}, act_facts, user_row,
                                   dict(history or {}, first=(history or {}).get("first", "")), {}, banned_now)
    for r in a_reasons:
        print(f"  {r}")
        n_points = int(r.split(" ", 1)[0].lstrip("+"))
        sign(n_points, r.split(" ", 1)[1])
    if not a_reasons:
        print("  no sign of misuse in its requests")
    print()
    print("[3] Its e-mail address")
    email = login if "@" in login else (detail or {}).get("email", "")
    em = email_module()
    if not email or not em:
        print("  no e-mail address to check" if not email else "  component apps/_email_check.py missing")
    else:
        chk = em.check(email)
        mx = em.mx_status(chk["domain"]) if chk["domain"] else "none"
        print(f"  {email} — syntax {'valid' if chk['valid'] else color_code('31', 'INVALID')}" + (f" ({chk['reason']})" if chk["reason"] else "")
              + (f" — suggested correction: {chk['suggestion']}" if chk["suggestion"] else ""))
        print(f"  mail server of {chk['domain'] or '?'} — " + {"mx": "yes (MX record)", "a-only": "no MX record, address only (mail possible)",
                                                             "none": color_code("31", "NONE — this domain receives no mail"), "unknown": "unknown (DNS tool missing or no Internet)"}[mx])
        if chk["disposable"] and "@" not in login:                    # login = e-mail: already counted in [2b]
            sign(2, f"disposable e-mail address ({chk['domain']})")
        if mx == "none":
            sign(2, f"the domain {chk['domain']} receives no mail")
        print()
        print("[4] Internet (the e-mail address and the IP addresses are sent to StopForumSpam, Gravatar and DuckDuckGo)")
        if internet is None:
            if ask and sys.stdin.isatty() and sys.stdout.isatty():
                try:
                    internet = input("  Search the Internet for this e-mail and these addresses? [Y/n]: ").strip().lower() in ("", "o", "oui", "y", "yes")
                except (KeyboardInterrupt, EOFError):
                    internet = False
            else:
                internet = False
        if not internet:
            print("  not searched (--internet to allow it without a question)")
        elif not em.internet_allowed():
            print("  disabled on this server (NGINX_TOOLS_INTERNET=off)")
        else:
            look = em.internet_lookups(email, ips[:15])
            sfs = look.get("stopforumspam")
            if sfs is None:
                print("  StopForumSpam: unreachable")
            else:
                e = sfs.get("email") or {}
                print("  StopForumSpam, e-mail: " + (color_code("31", f"REPORTED {e['frequency']} time(s), last {e['lastseen']}, confidence {e['confidence']:.0f} %")
                                                    if e.get("appears") else "never reported"))
                if e.get("appears"):
                    sign(3, f"e-mail reported {e['frequency']} time(s) to StopForumSpam")
                for ip, x in sfs.get("ip", {}).items():
                    if x.get("appears"):
                        print(f"  StopForumSpam, {ip} — " + color_code("31", f"REPORTED {x['frequency']} time(s), last {x['lastseen']}, confidence {x['confidence']:.0f} %"))
                        if x.get("confidence", 0) >= 25:
                            sign(2, f"{ip} reported to StopForumSpam")
                if not any(x.get("appears") for x in sfs.get("ip", {}).values()):
                    print("  StopForumSpam, IP addresses: never reported")
            g = look.get("gravatar")
            print("  Gravatar: " + ("profile picture found (address used elsewhere, often for years)" if g else "none" if g is False else "unreachable"))
            w = look.get("web")
            if w is None:
                print(f"  Web search: not available (search engine refused or unreachable) — to open in a browser: {em.search_url(email)}")
            else:
                print(f"  Web search of « {email} » — {w['count']} result(s)" + (" (an address never published anywhere: common for a recent or private address)" if not w["count"] else ""))
                for title, url in w["results"]:
                    print(f"      - {title} — {url}")
                print(f"      (all the results: {w['url']})")
    # --- verdict ---
    print()
    print("[5] Verdict")
    for n, text in notes:
        print(f"  +{n} {text}")
    verdict = "ban justified" if points >= 5 else "to watch" if points >= 2 else "no sign of misuse"
    style = "31" if points >= 5 else "33" if points >= 2 else "32"
    print(f"  → {color_code(style, f'score {points} — {verdict}')}" + ("" if points else " (the account behaves like a normal user)"))
    internal = bool(detail) and not detail["share"]
    res = {"login": login, "db": database, "uid": (detail or {}).get("uid"), "type": "internal" if internal else "portal", "ips": ips, "points": points,
           "verdict": verdict, "internal": internal, "active": (detail or {}).get("active", True), "others": others}
    if offer_actions and ask and sys.stdin.isatty() and sys.stdout.isatty() and not NO_PROMPT:
        reg = registered_odoo_users()
        pieces = ["[w] watch" if login not in reg["watched"] else "[u] stop watching"] + ([] if internal else ["[b] ban"]) + ["[Enter] nothing: "]
        try:
            rep = input(f"\n{login} — " + "  ".join(TR(p) for p in pieces)).strip().lower()
        except (KeyboardInterrupt, EOFError):
            rep = ""
        if rep in ("w", "s", "surveiller", "watch") and login not in reg["watched"]:
            watch_user(login, True, res)
        elif rep in ("u", "unwatch") and login in reg["watched"]:
            watch_user(login, False, res)
        elif rep in ("b", "ban", "bannir") and not internal:
            ban_user(login, yes=False, investigation=res)
    return res


def watch_user(login, on, investigation=None):
    """--watch-odoo-user / --unwatch-odoo-user: records the account in the register (always listed in the summary, marked in app-log-live.py)."""
    reg = registered_odoo_users()
    if on and login in reg["watched"]:
        print(f"{login} is already watched (since {reg['watched'][login]['date'][:16]}).")
        return 0
    if not on and login not in reg["watched"]:
        print(f"{login} is not watched.")
        return 0
    hist = login_history().get(login) or {}
    inv = investigation or {}
    path = _load_module("_odoo_users").record("watched" if on else "unwatched", inv.get("db") or ",".join(sorted(hist.get("bases", ()))), inv.get("uid") or "",
                                              login, sorted(hist.get("ips", {})), "web-monitor.py")
    if not path:
        print(f"{BAD}Register not writable (root required): nothing recorded.{END_BAD}")
        return 2
    print(f"{login} — {'watched — listed in every summary (section SUSPICIOUS ACTIVITY) and marked in app-log-live.py' if on else 'no longer watched'}.")
    return 0


def ban_user(login, yes=False, investigation=None, addresses=True):
    """--ban-odoo-user: investigation first (always), then, after confirmation: the Odoo account ARCHIVED (it can no longer log in, its sessions end, its
    login stays taken: no new account with the same e-mail), its IP addresses banned by nginx-log-audit.sh (only those used by NO other account and
    neither whitelisted nor in a place), and the event recorded (register apps/_odoo_users.py) — undone by --unban-odoo-user."""
    if not _load_module("_config").est_root():
        eprint("ERROR: root required (sudo) to ban an account.")
        return 2
    reg = registered_odoo_users()
    if login in reg["banned"]:
        print(f"{login} is already banned (since {reg['banned'][login]['date'][:16]}): web-monitor.py --unban-odoo-user {login} to lift it.")
        return 0
    inv = investigation or investigate_user(login, ask=not yes, internet=False if yes else None, offer_actions=False)
    if not inv:
        print(f"{BAD}Account {login} unknown: nothing banned.{END_BAD}")
        return 1
    if inv["internal"]:
        print(f"{BAD}REFUSED: {login} is an INTERNAL account (back-office access): archive it in Odoo itself (Settings > Users) after checking with the team.{END_BAD}")
        return 1
    if not inv["db"] or not inv["uid"]:
        print(f"{BAD}Odoo account unreadable (PostgreSQL, root): nothing banned.{END_BAD}")
        return 1
    to_ban, kept = [], []
    for ip in inv["ips"]:
        place = lists().lieu(ip)
        if in_whitelist(ip) or (place and (place.partagee or place.protegee)):
            kept.append((ip, "whitelist or place"))
        elif inv["others"].get(ip):
            kept.append((ip, f"also used by {', '.join(inv['others'][ip][:3])}"))
        else:
            to_ban.append(ip)
    print()
    print(f"BAN OF THE ODOO ACCOUNT {login} (UID {inv['uid']}, database {inv['db']}) — investigation verdict: {inv['verdict']}")
    print("  1. account ARCHIVED in Odoo: no more login, open sessions ended, the e-mail cannot be used for a new account")
    if addresses and to_ban:
        print(f"  2. IP address(es) banned at the firewall: {', '.join(to_ban)}")
        print("     (a home address can be reassigned to someone else later: lift with --unban-odoo-user after a few weeks)")
    for ip, why in kept:
        print(f"     not banned: {ip} ({why})")
    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            eprint("ERROR: no terminal to confirm — add --yes to ban without a question.")
            return 2
        try:
            rep = input("Ban? [y] account and addresses  [a] account only  [N] nothing: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            rep = ""
        if rep in ("a", "account", "compte"):
            addresses = False
        elif rep not in ("o", "oui", "y", "yes"):
            print("Nothing banned.")
            return 0
    db = odoo_db_module()
    changed = db.set_user_active(inv["db"], inv["uid"], False) if db else None
    if changed is None:
        print(f"{BAD}Odoo account NOT archived (PostgreSQL write failed): nothing else done.{END_BAD}")
        return 1
    print(f"  Odoo account: {'archived' if changed else 'already archived (or protected): unchanged'}")
    banned_ips = []
    if addresses:
        nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
        app = ["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []
        for ip in to_ban:
            why = f"web-monitor.py --ban-odoo-user: Odoo account {login} banned (score {inv['points']}: {inv['verdict']})"   # 2.73: kept in the ban journal
            r = subprocess.run(["bash", nla, "--ban", ip, "--yes", "--reason", why] + app + verbose_args(), capture_output=True, text=True, env=dict(os.environ, NGINX_TOOLS_LANG="fr"))
            print(f"  {ip} — {'banned' if r.returncode == 0 else BAD + 'NOT banned' + END_BAD}")
            if r.returncode == 0:
                banned_ips.append(ip)
    path = _load_module("_odoo_users").record("banned", inv["db"], inv["uid"], login, banned_ips, f"score {inv['points']}: {inv['verdict']}")
    print(f"  Recorded in {path}." if path else f"  {BAD}Register not writable: the ban is not recorded (--unban-odoo-user will not know the addresses).{END_BAD}")
    print(f"Undo: web-monitor.py --unban-odoo-user {login}")
    return 0


def unban_user(login, yes=False):
    """--unban-odoo-user: the account restored in Odoo and the addresses banned WITH it unbanned (register apps/_odoo_users.py)."""
    if not _load_module("_config").est_root():
        eprint("ERROR: root required (sudo) to lift a ban.")
        return 2
    event = registered_odoo_users()["banned"].get(login)
    if not event:
        print(f"{login} is not banned by this program (register apps/_odoo_users.py): nothing to lift.")
        return 0
    print(f"Ban of {login} on {event['date'][:16]} (database {event['db']}, UID {event['uid']}, addresses: {', '.join(event['ips']) or 'none'}).")
    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            eprint("ERROR: no terminal to confirm — add --yes to lift without a question.")
            return 2
        try:
            if input("Restore the account and unban its addresses? [y/N]: ").strip().lower() not in ("o", "oui", "y", "yes"):
                print("Nothing changed.")
                return 0
        except (KeyboardInterrupt, EOFError):
            return 0
    db = odoo_db_module()
    changed = db.set_user_active(event["db"], event["uid"], True) if db else None
    print("  Odoo account: " + ("restored" if changed else "already active: unchanged" if changed is False else BAD + "NOT restored (PostgreSQL write failed)" + END_BAD))
    nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
    app = ["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []
    for ip in event["ips"]:
        r = subprocess.run(["bash", nla, "--unban", ip, "--yes", "--reason", f"web-monitor.py --unban-odoo-user: Odoo account {login} restored"] + app + verbose_args(),
                           capture_output=True, text=True, env=dict(os.environ, NGINX_TOOLS_LANG="fr"))
        print(f"  {ip} — {'unbanned' if r.returncode == 0 else BAD + 'NOT unbanned' + END_BAD}")
    _load_module("_odoo_users").record("unbanned", event["db"], event["uid"], login, event["ips"], "web-monitor.py --unban-odoo-user")
    return 0 if changed is not None else 1


def first_journal_date(svc, ns):
    """Date of the oldest entry of the service's systemd journal (first line only)."""
    cmd = ["journalctl", "-u", svc, "-o", "short-iso", "--no-pager"] + (["--namespace", ns] if ns else [])
    if VERBOSE:
        eprint("+ " + shlex.join(cmd) + "   (first line only)")
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for text_line in truncate(p.stdout):
            try:
                d = datetime.date.fromisoformat(text_line[:10])
            except ValueError:
                continue
            p.kill()
            return d
        p.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


SERVER = set()        # addresses of this server (collect_summary)
WHITELIST = set()        # addresses of the nginx whitelist (team)


def device_family(ua):
    """Computer, phone or tablet according to the User-Agent. Known limit: a recent iPad (iPadOS 13+) presents
    itself as a Mac and therefore counts as a computer."""
    if re.search(r"iPad|Tablet|Kindle|Silk|PlayBook", ua) or ("Android" in ua and "Mobile" not in ua):
        return "tablette"
    if re.search(r"Mobile|iPhone|iPod|Android|Windows Phone|Opera Mini|BlackBerry", ua):
        return "cellulaire"
    return "ordinateur"


def collect_summary(periods):
    SERVER.clear()
    SERVER.update(server_addresses())
    WHITELIST.clear()
    WHITELIST.update(nginx_whitelist())
    WHITELIST.update(team())                  # whitelist and protected places (also valid without nginx configuration: BBB)
    # Addresses of logged-in users (Odoo), read first: detailed statistics of these addresses only.
    # Whole journal history (not only 30 days): an IP that logged in ONCE remains "known".
    account_ips = logged_in_ips(None)
    ip_stats = {}
    with_assets, pages_per_period = set(), [{} for _ in range(Periods.N)]
    c = Tally()
    app_name = PROFILE.get("APP_LABEL", "Odoo")
    app_caption = (TR("Journal of {vowel_name}").format(vowel_name=app_name) if app_name[:1].upper() in "AEIOUYH" else TR("Journal of {name}").format(name=app_name)) \
        + (" (systemd)" if PROFILE.get("APP_LOG_KIND") == "journal" else "")
    sources = {k: Source(v) for k, v in (("site", "Site logs (nginx)"), ("catchall", "Catch-all sensor (nginx)"),
                                          ("fail2ban", "fail2ban.log"), ("odoo", app_caption))}
    if not PROFILE.get("CATCHALL_LOG"):
        del sources["catchall"]
    unreadable = []
    facts = {"ip": {}, "malveillantes": {}, "non_filtrees": {}, "non_filtrees_hotes": {}, "hotes": {}, "valides": {}, "robots": {},
             "days": {}, "jails": {}, "comptes": {}, "refus_navigateurs": {}, "refus_nav_ip": {}, "refus_robots_chemins": {},
             "non_filtrees_jour": [], "ips_2xx": set(), "hotes_periodes": {}}
    cache = {}
    start30 = periods.starts[2]

    def nginx_day(txt):                       # "27/Sep/2026" -> date, converted only once (cache)
        if txt not in cache:
            try:
                cache[txt] = datetime.date(int(txt[7:11]), _MONTHS[txt[3:6]], int(txt[0:2]))
            except (KeyError, ValueError):
                cache[txt] = None
        return cache[txt]

    def read_it(path):
        try:
            return _open_log(path)
        except OSError:
            unreadable.append(path)
            return None

    def plus_one(mapping, key_value):
        mapping[key_value] = mapping.get(key_value, 0) + 1

    # --- site logs (one *-access.log file per vhost; default access.log excluded) ---
    databases = sorted({b for pattern in PROFILE.get("ACCESS_LOGS", "*-access.log").split() for b in glob.glob(os.path.join(NGINX_DIR, pattern))})
    for database in databases:
        for path in _rotations(database):
            f = read_it(path)
            if f is None:
                continue
            sources["site"].count_item(path)
            with f:
                for text_line in truncate(f):
                    m = ACCESS_RE.match(text_line)
                    if not m:
                        continue
                    d = nginx_day(m.group(2)); sources["site"].seen(d)
                    idx = periods.indices(d)
                    if not idx:
                        continue
                    ip, method, url, code, ua = m.group(1), m.group(3), m.group(4), m.group(5), m.group(7) or ""
                    size = int(m.group(6)) if m.group(6) and m.group(6).isdigit() else 0
                    host_value = m.group(8)
                    # Requests from OUR programs (loopback, addresses of this server, app-health-check User-Agent):
                    # deliberate tests, excluded from all figures (visits, rejections, errors, access to sensitive files) and counted separately.
                    if ip in SERVER or any(t in ua for t in SERVER_TESTS):
                        c.add("nos_programmes", idx)
                        continue
                    c.add("requetes", idx)
                    if account_ips is None or ip in account_ips or in_whitelist(ip):
                        accumulate_ip(ip_stats, ip, method, url, code, d, idx, ua, request_second(text_line) if ip in (account_ips or ()) else None)
                    c.add_distinct("visiteurs", idx, ip)
                    sensitive = bool(SENSITIVE_RE.search(url))
                    bad = malicious(url)
                    if bad:
                        facts.setdefault("ips_mal", set()).add(ip)
                    # nginx itself answers 404 to malicious URLs (location ~ /\., .php, ../…) to reveal nothing:
                    # small page (a few hundred bytes), whereas the Odoo 404 page weighs tens of KB.
                    rejected = (code in NGINX_REJECT_CODES or (code == "404" and bad and size < NGINX_404_SIZE)
                               or (code[0] == "3" and bad and size <= NGINX_3XX_SIZE))
                    our_tests = False                  # (excluded above: kept for the readability of the conditions)
                    if rejected:
                        c.add("rejetees", idx)
                    else:
                        c.add("transmises", idx)
                        if bad:
                            c.add("transmises_suspectes", idx)
                            if not our_tests:
                                plus_one(facts["non_filtrees"], url.split("?")[0][:60])
                                if host_value:
                                    plus_one(facts["non_filtrees_hotes"], host_value)
                                facts["non_filtrees_derniere"] = max(facts.get("non_filtrees_derniere", ""), f"{d:%Y-%m-%d}")
                                if 0 in idx and len(facts["non_filtrees_jour"]) < 5000:      # today: exact hour
                                    facts["non_filtrees_jour"].append((nginx_hour(text_line), url.split("?")[0][:200], host_value or ""))
                    if code[0] == "2":                   # got at least one normal response (possible real visitor)
                        facts["ips_2xx"].add(ip)
                    if method == "GET" and code[0] == "2" and not ASSET_RE.search(url):
                        c.add("pages", idx)
                        plus_one(facts.setdefault("pages_ip", {}), ip)
                        if not bad:
                            plus_one(facts["valides"], url.split("?")[0][:60])
                    if code == "403":
                        c.add("bloques403", idx)
                        if not our_tests:
                            family = client_family(ua)
                            plus_one(facts["robots"], family)
                            if not bad:                          # pages requested by this family (at most 300 paths)
                                family_paths = facts["refus_robots_chemins"].setdefault(family, {})
                                short_path = url.split("?")[0][:60]
                                if short_path in family_paths or len(family_paths) < 300:
                                    plus_one(family_paths, short_path)
                            if family.startswith("browser"):
                                if bad:                          # scanner URL (.env, .php…): normal refusal
                                    facts["refus_nav_scanners"] = facts.get("refus_nav_scanners", 0) + 1
                                else:                            # ordinary page: rule too strict or disguised robot?
                                    plus_one(facts["refus_navigateurs"], url.split("?")[0][:60])
                                    plus_one(facts["refus_nav_ip"], ip)
                                    if size <= 600:            # small page: typical of a refusal by nginx itself
                                        facts["refus_nav_petits"] = facts.get("refus_nav_petits", 0) + 1
                    elif code == "429":
                        c.add("limites429", idx)
                    elif code[0] == "5":
                        c.add("erreurs5xx", idx)
                    if sensitive:
                        c.add("fichiers_sensibles", idx)
                    if bad and not our_tests:
                        plus_one(facts["malveillantes"], url.split("?")[0][:60])
                    # Devices: visitor = IP + browser; "probable human" if it also loaded the CSS/JS (robots
                    # and scrapers read the HTML without loading them); robots, tools, team (whitelist), this server excluded.
                    if method == "GET" and not our_tests and not in_whitelist(ip) and ua and ua != "-" \
                            and not ROBOT_RE.search(ua) and not OUTIL_RE.search(ua):
                        key_value = ip + "|" + ua
                        if code[0] in "23" and ASSET_RE.search(url):
                            with_assets.add(key_value)
                        elif code[0] == "2" and not bad and not ASSET_RE.search(url):
                            for i in idx:
                                pages_per_period[i][key_value] = device_family(ua)
                    # BigBlueButton participants: participation link (/bigbluebutton/api/join?fullName=…), opened
                    # by the participant's browser — their IP and the name they entered.
                    if url.startswith("/bigbluebutton/api/join?") and code[0] in "23":
                        q = urllib.parse.parse_qs(url.split("?", 1)[1])
                        note_account(facts["comptes"], (q.get("fullName") or ["(no name)"])[0][:40], ip, idx, f"{d:%Y-%m-%d}")
                    if host_value:
                        plus_one(facts["hotes"], host_value)
                    row_hote = facts["hotes_periodes"].setdefault(host_value or "", [0] * Periods.N)   # "" = line without Host (older format)
                    for i in idx:
                        row_hote[i] += 1
                    plus_one(facts["ip"], ip)
                    plus_one(facts["days"], d)
    # --- capteur catch-all ---
    # Refusals by the security rules (securite-commune.conf), logged separately in blocked-probes.log (combined_host).
    for path in _rotations(os.path.join(NGINX_DIR, "blocked-probes.log")):
        if not os.path.exists(path):
            continue
        sources.setdefault("refus", Source("Rule refusals (nginx)")).count_item(path)
        try:
            f = gzip.open(path, "rt", errors="replace") if path.endswith(".gz") else open(path, errors="replace")
        except OSError:
            continue
        with f:
            for text_line in truncate(f):
                mr = ACCESS_RE.match(text_line)
                if not mr or mr.group(1) in SERVER:
                    continue
                d = nginx_day(mr.group(2)); sources["refus"].seen(d)
                idx = periods.indices(d)
                c.add("refus_regles", idx)
                if idx and malicious(mr.group(4)):       # 2.59: by the SHAPE of the URL (a robot refused on /robots.txt is not a malicious URL)
                    plus_one(facts["malveillantes"], mr.group(4).split("?")[0][:60])

    for path in (_rotations(os.path.join(NGINX_DIR, PROFILE["CATCHALL_LOG"])) if PROFILE.get("CATCHALL_LOG") else []):
        f = read_it(path)
        if f is None:
            continue
        sources["catchall"].count_item(path)
        with f:
            for text_line in truncate(f):
                m = CATCHALL_RE.match(text_line)
                if m:
                    d = nginx_day(m.group(2)); sources["catchall"].seen(d)
                    idx = periods.indices(d)
                    if m.group(1) in SERVER:              # our own sensor tests
                        c.add("nos_programmes", idx)
                        continue
                    c.add("catchall", idx)
                    if idx and m.group(3) and malicious(m.group(3)):
                        plus_one(facts["malveillantes"], m.group(3).split("?")[0][:60])
    # --- fail2ban: "2026-09-27 03:04:47,123 fail2ban.actions [..]: NOTICE [jail] Ban 1.2.3.4" ---
    for path in _rotations(FAIL2BAN_LOG):
        f = read_it(path)
        if f is None:
            continue
        sources["fail2ban"].count_item(path)
        with f:
            for text_line in truncate(f):
                try:
                    d0 = datetime.date.fromisoformat(text_line[:10])
                except ValueError:
                    continue
                sources["fail2ban"].seen(d0)
                m = FAIL2BAN_RE.match(text_line)
                if m:
                    idx = periods.indices(d0)
                    c.add_distinct("fail2ban", idx, m.group(5))
                    if idx and d0 >= start30:
                        facts["jails"].setdefault(m.group(4), set()).add(m.group(5))
    # --- bannissements manuels (nginx-log-audit.sh 1.34+) et IP CrowdSec actives ---
    banned = {}
    def new_or_old(folder, new, old):      # files of the other tools: English name, otherwise the old one (not yet migrated)
        n, a = os.path.join(folder, new), os.path.join(folder, old)
        return n if os.path.exists(n) or not os.path.exists(a) else a
    for path, key_value, date_col, filter_text in ((new_or_old(CHK_STATE, "bans.tsv", "bannissements.tsv"), "manuels", 0, "banni"),
                                          (new_or_old(CROWDSEC_STATE, "blocked-ips.tsv", "ip-bloquees.tsv"), "crowdsec", 4, None)):
        if not os.path.exists(path):
            continue
        f = read_it(path)
        if f is None:
            continue
        with f:
            for text_line in truncate(f):
                fields = text_line.rstrip("\n").split("\t")
                if len(fields) <= date_col:
                    continue
                if key_value == "manuels" and len(fields) >= 3 and fields[1] in ("banni", "leve"):
                    banned[fields[2]] = fields[1]                   # last known event: banned / lifted (2.73: « justifie » ignored)
                if filter_text and filter_text not in fields:
                    continue
                try:
                    d = datetime.date.fromisoformat(fields[date_col][:10])
                except ValueError:
                    continue
                c.add_distinct(key_value, periods.indices(d), fields[2] if key_value == "manuels" else fields[0])
    # --- Odoo journal: login failures and errors (filtered at the source: --grep) ---
    svc, ns = detect_odoo_service() if PROFILE.get("APP_LOG_KIND") == "journal" else (None, "")
    if PROFILE.get("APP_LOG_KIND") == "file":
        # Application journal in files (e.g. BBB: /var/log/bigbluebutton/bbb-web.log): error lines per day.
        svc = PROFILE.get("APP_LABEL")
        for database in PROFILE.get("APP_LOG_FILES", "").split():
            for path in _rotations(database):
                f = read_it(path)
                if f is None:
                    continue
                sources["odoo"].count_item(path)
                with f:
                    for text_line in truncate(f):
                        try:
                            d = datetime.date.fromisoformat(text_line[:10])
                        except ValueError:
                            continue
                        sources["odoo"].seen(d)
                        if " ERROR " in text_line or " FATAL " in text_line:
                            c.add("erreurs_odoo", periods.indices(d))
    elif svc:
        sources["odoo"].oldest = first_journal_date(svc, ns)
        base_cmd = ["journalctl", "-u", svc, "-o", "short-iso", "--no-pager",
                    "--since", start30.isoformat()] + (["--namespace", ns] if ns else [])
        code, out = run(base_cmd + ["--grep", "Login failed for|Login successful for| ERROR | CRITICAL |memory limit|CPU time limit|timeout after|"
                                    "Access Denied by|Password reset attempt"], timeout=300)
        if code != 0 and "pattern matching" in out:          # journalctl compiled without --grep: filtering here
            code, out = run(base_cmd, timeout=600)
        for text_line in truncate(out.splitlines()):
            try:
                d = datetime.date.fromisoformat(text_line[:10])
            except ValueError:
                continue
            idx = periods.indices(d)
            # Worker saturation (multiprocess mode): recycled for memory (limit_memory_soft, normal if
            # rare), killed for CPU time (limit_time_cpu) or real time (limit_time_real: "timeout after").
            if "virtual memory limit" in text_line:
                c.add("workers_memoire", idx)
            elif "CPU time limit" in text_line:
                c.add("workers_cpu", idx)
            elif re.search(r"Worker\w* \(\d+\) timeout after", text_line):
                c.add("workers_temps", idx)
            ml = re.search(r"Login successful for db:(\S+) login:(\S+) from (\S+)", text_line)
            if ml:
                note_account(facts["comptes"], ml.group(2), ml.group(3), idx, text_line[:16].replace("T", " "), ml.group(1))
                continue
            if idx and 2 in idx:                       # suspicious activity of logged-in users (period of the summary)
                ma = ACCESS_DENIED_RE.search(text_line)
                if ma:
                    facts.setdefault("odoo_denied", {}).setdefault(ma.group(2), {}).setdefault(ma.group(3), 0)
                    facts["odoo_denied"][ma.group(2)][ma.group(3)] += 1
                    continue
                mp = PASSWORD_RESET_RE.search(text_line)
                if mp:
                    plus_one(facts.setdefault("password_resets", {}), mp.group(1))
                    continue
                mf = LOGIN_FAILED_RE.search(text_line)
                if mf:
                    plus_one(facts.setdefault("login_failures", {}), mf.group(1))
            if "Login failed for" in text_line:
                c.add("connexions", idx)
            elif " ERROR " in text_line or " CRITICAL " in text_line:
                c.add("erreurs_odoo", idx)
    facts["stats_ip"] = ip_stats
    facts["ips_humaines"] = {key_value.split("|", 1)[0] for key_value in with_assets}      # IPs whose browser loaded the CSS/JS (probable human)
    facts["ips_connues"] = account_ips if account_ips is not None else {i for v in facts["comptes"].values() for i in v["ips"]}
    logged_in_shares(c, facts)
    # Devices of probable human visitors (pages viewed AND CSS/JS loaded), per period.
    for i, pages in enumerate(pages_per_period):
        for key_value, family in pages.items():
            if key_value in with_assets:
                c.n[("app_" + family, i)] = c.n.get(("app_" + family, i), 0) + 1
                c.n[("app_total", i)] = c.n.get(("app_total", i), 0) + 1
    return c, sources, facts, {ip for ip, ev in banned.items() if ev == "banni"}, svc, ns, unreadable


# ------------------------------------------------------------------------------------------------------------------
# Resources: what REMAINS in the VM or container (memory, load, disk) and the consumption of each service
# (nginx + services of the profile), measured by systemd (cgroups). In a Proxmox LXC container, /proc/meminfo and the
# load reflect the LIMITS of the container (lxcfs). CPU: two measurements one second apart (CURRENT
# load, not an average since startup). Unavailable values (accounting disabled): "n/a".
# ------------------------------------------------------------------------------------------------------------------
MEMINFO = os.environ.get("WEB_MONITOR_MEMINFO", "/proc/meminfo")


def _bytes(n):
    for unit, size in (("Go", 1 << 30), ("Mo", 1 << 20), ("Ko", 1 << 10)):
        if n >= size:
            return f"{n / size:.1f} {unit}".replace(".", ",")
    return f"{int(n)} o"


def _meminfo():
    values = {}
    try:
        for text_line in open(MEMINFO, encoding="utf-8"):
            key_value, _, remaining = text_line.partition(":")
            values[key_value] = int(remaining.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return values


def _existing_services():
    units = ["nginx.service"]
    for u in PROFILE.get("SERVICES", "").split():
        if "*" in u:                         # e.g. postgresql@*.service: the real instances (postgresql@16-main…)
            out = run(["systemctl", "list-units", "--all", "--no-legend", "--plain", u], timeout=20)[1]
            units += [l.split()[0] for l in out.splitlines() if l.split()]
        elif u != "nginx.service":
            units.append(u)
    code, out = run(["systemctl", "show", "-p", "Id,LoadState"] + units, timeout=30)
    present = set()
    for block in out.split("\n\n"):
        fields = dict(l.split("=", 1) for l in block.splitlines() if "=" in l)
        if fields.get("LoadState") == "loaded":
            present.add(fields.get("Id"))
    return [u for u in units if u in present]


def _measure(units):
    code, out = run(["systemctl", "show", "-p", "Id,ActiveState,CPUUsageNSec,MemoryCurrent,MemoryMax,IOReadBytes,IOWriteBytes"]
                    + units, timeout=30)
    res = {}
    for block in out.split("\n\n"):
        fields = dict(l.split("=", 1) for l in block.splitlines() if "=" in l)
        if fields.get("Id"):
            res[fields["Id"]] = fields
    return res


def _number(v):
    try:
        n = int(v)
        return None if n >= (1 << 63) - 1 or n < 0 else n     # "[not set]" or "infinity": unavailable
    except (TypeError, ValueError):
        return None


def show_resources(c=None, svc=None):
    print()
    virt = run(["systemd-detect-virt"], timeout=10)[1].strip() or "unknown"
    print(f"RESOURCES (virtualization: {virt})")
    alert_items = []
    m = _meminfo()
    if m.get("MemTotal"):
        total, avail = m["MemTotal"], m.get("MemAvailable", 0)
        free_pct = 100 * avail // total
        text_line = f"  Memory       : {_bytes(avail)} available out of {_bytes(total)} ({free_pct} % free)"
        if m.get("SwapTotal"):
            text_line += f" — swap: {_bytes(m['SwapTotal'] - m.get('SwapFree', 0))} used out of {_bytes(m['SwapTotal'])}"
        print(text_line)
        if free_pct < 10:
            alert_items.append(f"low available memory ({free_pct} %)")
    try:
        c1, c5, c15 = os.getloadavg()
        cores = len(os.sched_getaffinity(0))
        pct = int(100 * c1 / cores)
        print(f"  Load         : {c1:.2f} · {c5:.2f} · {c15:.2f} (1/5/15 min) for {cores} core(s) — {pct} % of capacity".replace(".", ","))
        if c5 >= cores:
            alert_items.append(f"5-min load ({c5:.2f}) higher than the number of cores ({cores})")
    except (OSError, AttributeError):
        pass
    seen_items = set()
    for path in ("/", "/var/log", "/var/lib/postgresql", "/opt"):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_dev in seen_items:
            continue
        seen_items.add(st.st_dev)
        disk = shutil.disk_usage(path)
        free_pct = 100 * disk.free // disk.total if disk.total else 0
        print(f"  Disk {path:<13}: {_bytes(disk.free)} free of {_bytes(disk.total)} ({free_pct} %)")
        if free_pct < 15:
            alert_items.append(f"disk {path} almost full ({free_pct} % free)")
    memories = {}
    units = _existing_services()
    if units:
        before = _measure(units)
        time.sleep(1)
        after = _measure(units)
        text_lines = []
        for u in units:
            a, b = before.get(u, {}), after.get(u, {})
            state = b.get("ActiveState", "?")
            cpu1, cpu2 = _number(a.get("CPUUsageNSec")), _number(b.get("CPUUsageNSec"))
            cpu = f"{(cpu2 - cpu1) / 1e7:.1f} %".replace(".", ",") if cpu1 is not None and cpu2 is not None else "n/d"
            mem, maximum = _number(b.get("MemoryCurrent")), _number(b.get("MemoryMax"))
            cutoff = "no limit" if maximum is None else f"{_bytes(maximum)} ({100 * mem // maximum if mem else 0} %)"
            if mem and maximum and mem * 10 >= maximum * 9:
                alert_items.append(f"{u} close to its memory limit ({100 * mem // maximum} %)")
            was_read, written = _number(b.get("IOReadBytes")), _number(b.get("IOWriteBytes"))
            io = f"{_bytes(was_read)} / {_bytes(written)}" if was_read is not None and written is not None else "n/d"
            display_name = (u[:-8] if u.endswith(".service") else u) + ("" if state == "active" else f" ({state})")   # Python 3.8: no removesuffix
            text_lines.append((display_name, cpu, _bytes(mem) if mem is not None else "n/d", cutoff, io))
            memories[u] = mem
            if state not in ("active", "reloading"):
                alert_items.append(f"{u} is not active ({state})")
        with_io = any(l[4] != "n/d" for l in text_lines)
        print(f"  {'Service':<30} {'CPU':>11} {'memory':>10}  {'limit':<22}" + ("  read / written (since startup)" if with_io else ""))
        for display_name, cpu, mem, cutoff, io in text_lines:
            print(f"    {display_name:<28} {cpu:>11} {mem:>10}  {cutoff:<22}" + (f"  {io}" if with_io else ""))
        if not with_io:
            print("  (reads/writes not measured: I/O accounting disabled for these services, common in LXC)")
    for a in alert_items:
        print(f"  {BAD}⚠ {a}{END_BAD}")
    # Odoo workers: configuration, worst-case memory, signs of saturation and advice (Odoo in systemd journal).
    if c is not None and svc and PROFILE.get("APP_LOG_KIND") == "journal":
        workers_advice(svc, c, memories.get(svc), sum(v or 0 for u, v in memories.items() if u.startswith("postgresql")))


def blocked_packets():
    """Packets blocked at the firewall BEFORE nginx, by origin — iptables counters CUMULATED since the rules were loaded
    (not split by period). None if iptables is absent or inaccessible (root required)."""
    code, out = run(["iptables", "-L", "INPUT", "-v", "-x", "-n"], timeout=30)
    if code != 0 or "Chain INPUT" not in out:
        return None
    res = {"CrowdSec": 0, "fail2ban": 0, "manual bans": 0}
    f2b_strings = set()
    for text_line in out.splitlines()[2:]:
        c = text_line.split()
        if len(c) < 9 or not c[0].isdigit():
            continue
        packages, target_value, source = int(c[0]), c[2], c[7]
        if "crowdsec-blocklist" in text_line:
            res["CrowdSec"] += packages
        elif target_value.startswith("f2b-"):
            f2b_strings.add(target_value)
        elif target_value in ("DROP", "REJECT") and source not in ("0.0.0.0/0", "::/0") and len(c) == 9:
            res["manual bans"] += packages             # "-s IP -j DROP" without any other criterion (--ban)
    for string_value in sorted(f2b_strings) + ["ufw-user-input"]:
        code, out = run(["iptables", "-L", string_value, "-v", "-x", "-n"], timeout=30)
        for text_line in out.splitlines()[2:] if code == 0 else []:
            c = text_line.split()
            if len(c) >= 9 and c[0].isdigit() and c[2] in ("DROP", "REJECT"):
                res["fail2ban" if string_value.startswith("f2b-") else "manual bans"] += int(c[0])
    return res


def fmt(n):
    return str(n)                                           # numbers without thousands separator ("3403", never "3 403")


def top(mapping, n=5):
    return sorted(mapping.items(), key=lambda kv: (-kv[1], str(kv[0])))[:n]


RECO_FILE = "recommended-bans.json"
RECO_DURATION_S = 48 * 3600     # a recommendation that is not renewed is forgotten after 48 h (like the reading by app-log-live.py)


def remember_recommendations(now, merge=True):
    """IPs recommended for banning by this run (empty list otherwise): picked up by --ban-recommended, which the
    e-mail or the journal mention when the run happens without a terminal (timer)."""
    path = os.path.join(STATE_DIR, RECO_FILE)
    now_dt = time.time()
    ips = [{"ip": ip, "raison": r, "vu": now_dt} for ip, r in RECOMMENDED]
    # A run only reads the NEW lines of the logs: an address recommended by a previous run does not necessarily appear there any more. It therefore stays recommended
    # (with its reason) until it is banned or 48 h after its last recommendation — otherwise a rerun (b key of app-log-live.py) would erase valid recommendations.
    try:
        if not merge:                                  # list processed by --ban-recommended: emptied for good
            raise ValueError
        with open(path) as f:
            old = json.load(f)
        seen_items = {x["ip"] for x in ips}
        for x in old.get("ips", []):
            since = float(x.get("vu", old.get("time", 0)))
            if isinstance(x, dict) and isinstance(x.get("ip"), str) and x["ip"] not in seen_items and now_dt - since < RECO_DURATION_S:
                ips.append({"ip": x["ip"], "raison": str(x.get("raison", "")), "vu": since})
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        temp = f"{path}.{os.getpid()}.tmp"          # written aside then renamed in one go: a reader (app-log-live.py) or a second run never sees a half-written file
        with open(temp, "w") as f:
            json.dump({"when": f"{now:%Y-%m-%d %H:%M}", "time": now_dt, "ips": ips}, f)
        os.replace(temp, path)
    except OSError:
        pass


def ban(items, choose):
    """Bans the IPs of the list with nginx-log-audit.sh. choose=True: one by one, with the investigation and the
    confirmation of --ban (full reasoning). Otherwise: all, without a new question (--ban --yes)."""
    nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
    if not os.path.isfile(nla):
        print("nginx-log-audit.sh not found next to this program: banning impossible.")
        return 1
    app = ["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []
    n_ok = 0
    for ip, reason in items:
        why = ["--reason", f"web-monitor.py: {reason}"]          # 2.73: the reason is kept in the ban journal (date, time, justification)
        if choose:
            print(f"\n{'=' * 70}\n{ip} — {reason}")
            with foreground_child():
                code = subprocess.run(["bash", nla, "--ban", ip] + why + app + verbose_args()).returncode
        else:                                      # 2.66: own session: Ctrl-C asks web-monitor's question and never kills a ban halfway
            r = subprocess.run(["bash", nla, "--ban", ip, "--yes"] + why + app + verbose_args(), capture_output=True, text=True, env=dict(os.environ, NGINX_TOOLS_LANG="fr"),
                               start_new_session=True)
            if VERBOSE and r.stderr:
                sys.stderr.write(r.stderr)
            code = r.returncode
            detail = next((l.strip() for l in r.stdout.splitlines() + r.stderr.splitlines()
                           if re.search(r"Règle|Déjà|REFUSÉ|ÉCHEC", l)), "")
            print(f"  {ip} : {'banni' if code == 0 else BAD + 'NOT banned' + END_BAD}{' — ' + detail if detail else ''}")
        n_ok += code == 0
    print(f"\n{n_ok}/{len(items)} IP(s) banned (reversible: nginx-log-audit.sh --unban IP).")
    return 0


def ask_ban(items, yes=False):
    """A single question for all the IPs: [o] all, [c] one by one (detailed investigation), [N] nothing."""
    print(f"\n{len(items)} IP(s) recommended for banning:")
    for ip, reason in items:
        print(f"  {BAD}▶ {ip}{END_BAD} — {reason}")
    if yes:
        return ban(items, choose=False)
    try:
        rep = input("\nBan now? [y] all  [c] choose one by one (detailed investigation)  [N] none: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        rep = ""
    if rep in ("o", "oui", "y", "yes"):
        return ban(items, choose=False)
    if rep in ("c", "choisir", "choose"):
        return ban(items, choose=True)
    print("No IP banned. Later: web-monitor.py --ban-recommended")
    return 0


def offer_ban():
    """End of a manually launched run (terminal, root): offer to ban the recommended IPs, with no other step."""
    if not RECOMMENDED or NO_PROMPT or os.geteuid() != 0 or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    ask_ban(RECOMMENDED)


def ban_recommended(yes):
    """--ban-recommended: ban the IPs recommended by the LAST run (e.g. the timer's, without a terminal)."""
    if os.geteuid() != 0:
        eprint("ERROR: root required (sudo) to ban.")
        return 2
    try:
        d = json.load(open(os.path.join(STATE_DIR, RECO_FILE)))
    except (OSError, ValueError):
        print("No recommendation recorded: run a pass first (web-monitor.py).")
        return 0
    items = [(x["ip"], x.get("raison", "")) for x in d.get("ips", [])]
    age = time.time() - d.get("time", time.time())
    print(f"Recommendations of the pass of {d.get('when')} ({_age(age)}).")
    if age > 24 * 3600:
        print(f"{BAD}⚠ more than 24 h old: run a pass again (web-monitor.py) to get an up-to-date list.{END_BAD}")
    if not items:
        print("No IP recommended for banning.")
        return 0
    if not yes and not (sys.stdin.isatty() and sys.stdout.isatty()):
        eprint("ERROR: no terminal to confirm — add --yes to ban without questions.")
        return 2
    code = ask_ban(items, yes=yes)
    if yes:
        remember_recommendations(datetime.datetime.now().astimezone(), merge=False)      # list processed: emptied
    return code


def offer_less(path):
    """End of a manually launched run (terminal): offer to open the complete report in less. Never in the
    timer (no terminal) nor with --no-pager. Enter: opens; Ctrl-C or Ctrl-D: ends without opening."""
    if NO_PAGER or not (sys.stdin.isatty() and sys.stdout.isatty()) or not shutil.which("less"):
        return
    try:
        input("\nPress Enter to open the full report in less (q to quit), or Ctrl-C to finish: ")
    except (KeyboardInterrupt, EOFError):
        print()
        return
    # Ctrl-C in less is meant for less: the signal also goes to this program (same process group) and raised
    # KeyboardInterrupt in it (traceback). A neutral handler while less runs; less itself keeps the default behavior
    # (a Python handler is reset at exec, unlike SIG_IGN).
    old = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        subprocess.run(["less", "-R", path])
    finally:
        signal.signal(signal.SIGINT, old)


def show_bbb_state():
    """BigBlueButton: versions, BBB configuration and ours, compatibility with our rules, changes since the
    last nginx-hardening.sh --update (apps/_bbb.py). Problems returned for the recommendations."""
    if PROFILE.get("APP_NAME") != "bbb":
        return []
    path = os.path.join(SCRIPT_DIR, "apps", "_bbb.py")
    if not os.path.isfile(path):
        return []
    try:
        spec = importlib.util.spec_from_file_location("_bbb", path)
        bbb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bbb)
        bbb.VERBOSE = VERBOSE                             # --verbose passed to the component (its commands are displayed)
        text_lines, problems = bbb.resume("summary")
    except Exception as e:                                      # never stop the summary for this section
        print(f"BIGBLUEBUTTON: state not collected ({type(e).__name__} : {e})")
        print()
        return []
    print("BIGBLUEBUTTON — VERSIONS, CONFIGURATION AND COMPATIBILITY WITH OUR RULES")
    for text_line in text_lines:
        tag_match = re.match(r"\[(OK|ATTN|FAIL)\] ", text_line)
        if tag_match:
            color = {"OK": "\x1b[1;32m", "ATTN": "\x1b[1;33m", "FAIL": "\x1b[1;31m"}[tag_match.group(1)]
            tag = f"[{tag_match.group(1)}]"
            print("  " + (f"{color}{tag}\x1b[0m" if sys.stdout.isatty() else tag) + " " + text_line[len(tag) + 1:])
        else:
            print(text_line)
    print()
    return problems


def show_summary():
    now = datetime.datetime.now().astimezone()
    periods = Periods(now.date())
    c, sources, facts, banned, svc, ns, unreadable = collect_summary(periods)
    site = sources["site"].oldest
    partial = [site is not None and site > start for start in periods.starts]
    header_labels = [periods.names[i] + ("*" if partial[i] else "") for i in periods.order]
    app = PROFILE.get("APP_LABEL", "Odoo")
    text_lines = [
        ("FUNNEL: WHO ARRIVES, WHO IS STOPPED, WHO REACHES THE APPLICATION", None),
        ("Arrived at nginx (site + catch-all sensor)", "arrivees"),
        ("Rejected by nginx (codes of its rules*)", "rejetees_total"),
        (f"Forwarded to {app}", "transmises"),
        ("  of which malicious URLs not filtered by nginx", "transmises_suspectes"),
        ("TRAFFIC", None),
        ("Requests on the site", "requetes"),
        ("  of which from known users' IPs", "req_connectes"),
        ("    of which outside the team (whitelist)", "req_connus_hors_equipe"),
        ("Distinct visitors (IP addresses)", "visiteurs"),
        ("Page views (excluding images, CSS, JS)", "pages"),
        ("  of which by known users", "pages_connectes"),
        ("Requests from our programs (excluded above)", "nos_programmes"),
        ("VISITORS' DEVICES (probable humans)", None),
        ("Computer", "app_ordinateur"),
        ("Cell phone", "app_cellulaire"),
        ("Tablet", "app_tablette"),
        ("BLOCKS AND ATTACKS", None),
        ("403 refusals (robots, tools, restricted access)", "bloques403"),
        ("Attempts on the catch-all sensor (444)", "catchall"),
        ("Security rule refusals (dedicated log)", "refus_regles"),
        ("Throttled requests (rate limiting, 429)", "limites429"),
        ("Access to sensitive files (.env, .git…)", "fichiers_sensibles"),
        ("IPs banned by fail2ban (distinct)", "fail2ban"),
        ("Manual bans", "manuels"),
        ("Active CrowdSec list IPs (blocked)", "crowdsec"),
        (PROFILE.get("APP_LABEL", "Odoo").upper(), None),
    ] + ([("Login failures", "connexions")] if PROFILE.get("APP_LOG_KIND") == "journal" else []) + [
        (f"Errors {PROFILE.get('APP_LABEL', 'Odoo')} (ERROR/CRITICAL)", "erreurs_odoo"),
        ("Server errors (5xx)", "erreurs5xx"),
    ]
    width = 52
    col = 14
    # Funnel: arrivals = site + sensor; rejected = codes produced by nginx + the whole sensor (444).
    for i in range(Periods.N):
        c.n[("arrivees", i)] = c.get("requetes", i) + c.get("catchall", i)
        c.n[("rejetees_total", i)] = c.get("rejetees", i) + c.get("catchall", i)
    base_pct = {"req_connectes": "requetes", "req_connus_hors_equipe": "requetes", "pages_connectes": "pages", "rejetees_total": "arrivees", "transmises": "arrivees", "transmises_suspectes": "transmises",
                "app_ordinateur": "app_total", "app_cellulaire": "app_total", "app_tablette": "app_total"}
    print(f"Summary — {socket.gethostname()} — {PROFILE.get('APP_LABEL', 'Odoo')} ({PROFILE.get('APP_DETECTION', '')}) — "
          f"{now:%Y-%m-%d %H:%M %Z} — web-monitor.py v{__version__}")
    print()
    entry_list = [TR(e) for e in header_labels]          # labels translated BEFORE computing the widths (FR and EN do not have the same length)
    number_width = max([len(fmt(c.get(key_value, i))) for _, key_value in text_lines if key_value for i in periods.order] + [max(len(e) for e in entry_list) - 7, 1])     # right-aligned digits; "(12 %)" comes after; wide enough for the label
    col = number_width + 9
    print(" " * (width + 1) + "".join(e.ljust(col) for e in entry_list))       # each label starts above its digits (2.59)
    for caption, key_value in text_lines:
        if key_value is None:
            print(caption)
            continue
        cells = []
        for i in periods.order:
            v = c.get(key_value, i)
            number = f"{fmt(v):>{number_width}}"
            pct = f" ({100 * v // c.get(base_pct[key_value], i)} %)" if key_value in base_pct and c.get(base_pct[key_value], i) else ""
            txt = number + f"{pct:<8}"
            if key_value == "transmises_suspectes" and v:
                txt = BAD + number + END_BAD + f"{pct:<8}"
                cells.append(" " * (col - len(number) - 8) + txt)
                continue
            cells.append(f"{txt:>{col}}")
        print(f"  {TR(caption):<{width - 2}}" + "".join(cells))                  # label translated BEFORE padding: columns aligned in all languages
        if key_value == "transmises_suspectes":
            print("  * 400, 403, 405, 413, 429, 444, and the 404s and redirects (3xx) from nginx itself on malicious URLs")
            print("    (.env, .php, ../…): small response page; the application's are much heavier.")
            print()
        if key_value == "req_connus_hors_equipe":
            print("  (known users: IP addresses used for at least one successful login, over the whole history")
            print("   of the journal — even without an open session today)")
        if key_value == "app_tablette":
            print("  Visitor = IP address + browser that loaded the CSS/JS of a page (robots read the HTML without")
            print("  loading them); robots, tools, team (whitelist) and this server excluded. A recent iPad presents")
            print("  itself as a Mac: it counts as a computer.")

    pf = blocked_packets()
    print()
    if pf is None:
        print("  Firewall: counters inaccessible (root required) — packets blocked before nginx not counted.")
    else:
        print(f"  Firewall: {fmt(sum(pf.values()))} packets blocked BEFORE nginx since the rules were loaded ("
              + ", ".join(f"{k} : {fmt(v)}" for k, v in pf.items()) + ")")
        print("             cumulative iptables counters, in packets (not requests): not split by period.")

    # --- requests per DNS name (Host), per period: the same columns as the funnel above ---
    host_rows = facts.get("hotes_periodes", {})
    if host_rows:
        ranked = sorted((h for h in host_rows if h), key=lambda h: (-host_rows[h][2], -host_rows[h][0], h))
        shown, others = ranked[:15], ranked[15:]
        print()
        print("REQUESTS BY DNS NAME (Host), SITE LOGS (this server's own tests excluded)")
        print(" " * (width + 1) + "".join(e.ljust(col) for e in entry_list))

        def host_line(label, values):
            label = label if len(label) <= width - 3 else label[:width - 4] + "…"
            cells = ""
            for i in periods.order:                                   # same cells as the funnel: the number, then the 8 columns of the « (12 %) » these rows do not have
                cells += (f"{fmt(values[i]):>{number_width}}" + " " * 8).rjust(col)
            print(f"  {label:<{width - 2}}" + cells)

        for h in shown:
            host_line(h, host_rows[h])
        if others:
            host_line(TR("{n} other name(s)").format(n=len(others)), [sum(host_rows[h][i] for h in others) for i in range(Periods.N)])
        if "" in host_rows:
            host_line(TR("(no Host field: older log lines)"), host_rows[""])

    # --- faits marquants (30 jours) ---
    print()
    print(f"HIGHLIGHTS ({duration(DAYS)})")
    if facts["days"]:
        day, n = top(facts["days"], 1)[0]
        print(f"  Busiest day              : {day:%Y-%m-%d} ({fmt(n)} requests)")
    if facts["ip"]:
        mark = lambda ip: ", banned" if ip in banned else ", this server" if ip in SERVER else ", whitelist" if in_whitelist(ip) else ""
        print("  Most active IPs          : " + ", ".join(f"{ip} ({fmt(n)}{mark(ip)})" for ip, n in top(facts["ip"])))
    print("  Malicious URLs           : " + (", ".join(f"{BAD}{u}{END_BAD} ({fmt(n)})" for u, n in top(facts["malveillantes"])) or "none")
          + "   (by their shape: sensitive files, traversal, injections, PHP, proxy)")
    print("  Not filtered by nginx    : " + (", ".join(f"{BAD}{u}{END_BAD} ({fmt(n)})" for u, n in top(facts["non_filtrees"]))
                                         or "none") + f"   ({PROFILE.get('APP_LABEL', 'application')} answered, often 404)")
    if facts.get("hotes"):
        print("  Names requested (Host)   : " + ", ".join(f"{h} ({fmt(n)})" for h, n in top(facts["hotes"])))
    if facts.get("non_filtrees_hotes"):
        print("    … of the unfiltered    : " + ", ".join(f"{BAD}{h}{END_BAD} ({fmt(n)})" for h, n in top(facts["non_filtrees_hotes"]))
              + "   (server block that let them through)")
    print("  Most viewed valid pages  : " + (", ".join(f"{u} ({fmt(n)})" for u, n in top(facts["valides"])) or "none"))
    print("  Clients blocked (403)    : " + (", ".join(f"{r} ({fmt(n)})" for r, n in top(facts["robots"])) or "no client")
          + "   (excluding this server's tests)")
    jails = {j: len(ips) for j, ips in facts["jails"].items()}
    print("  fail2ban, IPs per jail   : " + (", ".join(f"{j} ({n})" for j, n in top(jails, 8)) or "none"))

    # --- couverture exacte de chaque journal ---
    print()
    show_whitelist(c, facts)
    show_accounts(facts, banned)
    show_suspects(facts, banned)
    print()
    print("LOG COVERAGE (oldest date available)")
    policies = {"site": logrotate_policy("nginx"), "catchall": logrotate_policy("nginx"), "fail2ban": logrotate_policy("fail2ban")}
    for key_value, src in sources.items():
        date_text = f"{src.oldest:%Y-%m-%d}" if src.oldest else "—"
        info = f"{src.files} file(s)" if src.files else ""
        pol = policies.get(key_value)
        if pol:
            freq = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}[pol[0]]
            info += f"{' — ' if info else ''}rotation {freq}, {pol[1]} kept ≈ {pol[2]} days"
        elif key_value == "odoo" and not svc:
            info = f"service {PROFILE.get('APP_LABEL', 'Odoo')} not detected"
        print(f"  {src.libelle:<30} {date_text:<11} {info}")
    if any(partial):
        print(f"* Partial period: the site logs only go back to {site:%Y-%m-%d} (rotation).")
    log_space(sources, svc, ns, now.date())

    # --- conserver 3 mois : modification exacte a faire ---
    advices = []
    for display_name, key_value in (("nginx", "site"), ("fail2ban", "fail2ban")):
        pol = policies.get(key_value)
        if pol and pol[2] < TARGET_RETENTION_DAYS:
            per = {"daily": 1, "weekly": 7, "monthly": 30}[pol[0]]
            target_value = -(-TARGET_RETENTION_DAYS // per)
            advices.append(f"  {display_name} : in {pol[3]}, replace « rotate {pol[1]} » with « rotate {target_value} »")
    if advices:
        print()
        print("KEEP 3 MONTHS (instead of the current rotation):")
        print("\n".join(advices))
        if PROFILE.get("APP_LOG_KIND") != "journal":
            pass      # journal in files: rotation managed by the application itself
        elif ns:      # isolated journal (LogNamespace): its own configuration file and its own service
            print(f"  Odoo journal (namespace « {ns} ») : in /etc/systemd/journald@{ns}.conf, section « [Journal] »,")
            print(f"    « MaxRetentionSec=3month » and « SystemMaxUse=2G », then systemctl restart systemd-journald@{ns}")
        else:
            print("  Odoo journal: file /etc/systemd/journald.conf.d/retention.conf containing « [Journal] » then")
            print("    « MaxRetentionSec=3month » and « SystemMaxUse=2G », then systemctl restart systemd-journald")
        print("  (little space needed: the rotations are compressed)")

    print()
    if unreadable:
        print(f"{len(set(unreadable))} unreadable file(s) (run again as root): " + ", ".join(sorted(set(unreadable))[:4])
              + (" …" if len(set(unreadable)) > 4 else ""))
    if not sources["site"].files:
        print(f"No log read in {NGINX_DIR} — is this really the nginx + Odoo server?")
    show_resources(c, svc)
    facts["connexions"] = show_logins(svc)
    print()
    facts["bbb_problemes"] = show_bbb_state()
    facts["bannies"] = banned
    facts["a_debannir"] = ips_to_unban(facts, banned)
    show_unbans(facts["a_debannir"])
    recommendations(c, facts, {"site": logrotate_policy("nginx"), "fail2ban": logrotate_policy("fail2ban")})
    print("Detail of an indicator: nginx-log-audit.sh --stats (traffic), --fail2ban (bans), app-log-check.py (application).")
    return offer_fixes()


def install_timer(hours):
    service = f"""# Generated by web-monitor.py --install-timer — do not edit by hand.\n[Unit]\nDescription=Automatic nginx + Odoo monitoring (alert only if an action is needed)\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=oneshot\nExecStart={sys.executable} {os.path.realpath(__file__)}\nNice=10\nIOSchedulingClass=idle\nTimeoutStartSec=30min\n# Exit code 1 = "alert raised" (not a service failure): do not mark the unit as failed because of it.\nSuccessExitStatus=1\n"""
    calendar = "*-*-* *:05:00" if hours == 1 else f"*-*-* 00/{hours}:05:00"
    timer = f"""# Generated by web-monitor.py --install-timer — do not edit by hand.\n[Unit]\nDescription=Runs web-monitor every {hours} hour(s)\n\n[Timer]\nOnCalendar={calendar}\n# Catches up a missed run (server off at the scheduled time).\nPersistent=true\nRandomizedDelaySec=120\n\n[Install]\nWantedBy=timers.target\n"""
    os.makedirs(SYSTEMD_DIR, exist_ok=True)
    with open(os.path.join(SYSTEMD_DIR, f"{UNIT}.service"), "w") as f:
        f.write(service)
    with open(os.path.join(SYSTEMD_DIR, f"{UNIT}.timer"), "w") as f:
        f.write(timer)
    for cmd in (["systemctl", "daemon-reload"], ["systemctl", "enable", "--now", f"{UNIT}.timer"]):
        code, out = run(cmd, timeout=60)
        if code != 0:
            print(f"ERROR: {' '.join(cmd)} failed: {out.strip()}", file=sys.stderr)
            return 1
    print(f"Timer installed and active: {SYSTEMD_DIR}/{UNIT}.timer (every {hours} hour(s), at minute 5).")
    print(f"Next run: systemctl list-timers {UNIT}.timer; journal: journalctl -u {UNIT}.service")
    print("Remember to set SMTP_HOST and NOTIFY_EMAIL_TO in the app-health-check.py configuration to receive alerts by e-mail.")
    return 0


def uninstall_timer():
    run(["systemctl", "disable", "--now", f"{UNIT}.timer"], timeout=60)
    for ext in ("timer", "service"):
        try:
            os.remove(os.path.join(SYSTEMD_DIR, f"{UNIT}.{ext}"))
        except FileNotFoundError:
            pass
    run(["systemctl", "daemon-reload"], timeout=60)
    print("Timer removed. Reports and state kept in", LOG_DIR, "et", STATE_DIR)
    return 0


def _age(seconds):
    seconds = int(seconds)
    for unit, size in (("day(s)", 86400), ("h", 3600), ("min", 60)):
        if seconds >= size:
            return f"{seconds // size} {unit} ago" if LANGUAGE == "en" else f"il y a {seconds // size} {unit}"
    return "just now"


def show_status():
    """Review of the monitoring: timer (installed, active, interval, next and last run), last run
    (age, delay), last alert (elements, next possible e-mail), e-mail (configured or not), reports."""
    now = time.time()
    print(socket.gethostname())
    try:
        p = load_profile(None)
        app = f"{p['APP_LABEL']} ({p['APP_DETECTION']})"
    except Exception as e:                  # machine without application: --status is still useful
        app = f"not detected ({e})"
    print(f"Application: {app}")

    print()
    print("TIMER (automatic monitoring)")
    timer_file = os.path.join(SYSTEMD_DIR, f"{UNIT}.timer")
    interval_h = None
    if not os.path.exists(timer_file):
        print(f"  {BAD}NOT INSTALLED: monitoring does not run automatically{END_BAD} (only when you run it).")
        if os.path.exists(os.path.join(SYSTEMD_DIR, "surveillance-odoo.timer")):
            print("  Old surveillance-odoo timer present: run web-monitor.py (as root) to migrate it automatically.")
        print("  To install it (root): web-monitor.py --install-timer          (every hour; --interval-hours N)")
    else:
        m = re.search(r"OnCalendar=\*-\*-\* (?:00/(\d+)|\*):05:00", open(timer_file).read())
        interval_h = int(m.group(1)) if m and m.group(1) else 1
        active = run(["systemctl", "is-active", f"{UNIT}.timer"], timeout=20)[1].strip() or "unknown"
        enabled_at_boot = run(["systemctl", "is-enabled", f"{UNIT}.timer"], timeout=20)[1].strip() or "unknown"
        fields = dict(l.split("=", 1) for l in run(["systemctl", "show", f"{UNIT}.timer", "-p",
                      "NextElapseUSecRealtime,LastTriggerUSec"], timeout=20)[1].splitlines() if "=" in l)
        svc = dict(l.split("=", 1) for l in run(["systemctl", "show", f"{UNIT}.service", "-p",
                   "ExecMainStatus,Result"], timeout=20)[1].splitlines() if "=" in l)
        state = f"{active}, {'enabled at boot' if enabled_at_boot == 'enabled' else 'NOT enabled at boot'}"
        print(f"  State             : {state if active == 'active' else BAD + state + END_BAD}")
        print(f"  Interval          : every {interval_h} hour(s) (at the 5th minute)")
        print(f"  Next run          : {fields.get('NextElapseUSecRealtime') or 'none (timer stopped)'}")
        print(f"  Last start        : {fields.get('LastTriggerUSec') or 'never'}")
        code_sortie = svc.get("ExecMainStatus", "")
        if code_sortie:
            direction = {"0": "healthy", "1": "alert(s)", "2": "tool ERROR"}.get(code_sortie, "unexpected")
            print(f"  Last result       : code {code_sortie} ({direction})")
        if active != "active" or enabled_at_boot != "enabled":
            print("  To (re)enable it: systemctl enable --now web-monitor.timer")

    print()
    print("LAST PASS")
    path = os.path.join(STATE_DIR, "last-run")
    try:
        text_value = open(path).read().strip()
        age = now - os.path.getmtime(path)
        print(f"  {text_value}")
        print(f"  ({_age(age)})")
        if interval_h and age > 2 * interval_h * 3600 + 600:
            print(f"  {BAD}⚠ late: no pass for more than two intervals — is the timer running?{END_BAD}")
        if re.search(r"sanity-check-odoo|surveillance-odoo|chk-nginx-logs|chk-odoo-logs", text_value):
            print("  (message written by a version older than the program renaming)")
    except OSError:
        print("  no pass recorded")

    print()
    print("LAST ALERT SENT")
    try:
        d = json.loads(open(os.path.join(STATE_DIR, "last-alert.json")).read())
        print(f"  {d.get('when')} ({_age(now - d.get('time', now))})")
        for t in d.get("titles", []):
            print(f"    ■ {t}")
        next_run = d.get("time", now) + REALERT_AFTER_S
        if next_run > now:
            print(f"  Same situation: no new e-mail before {datetime.datetime.fromtimestamp(next_run):%Y-%m-%d %H:%M} "
                  "(unless a new problem).")
    except (OSError, ValueError):
        print("  none")

    for heading, text_lines, _ in analyze_timers():
        print()
        print(f"  {BAD}⚠ {heading}{END_BAD}")
        print(f"    {text_lines[0]}")
    print()
    print("E-MAIL")
    mod = load_sanity_module()
    cfg = {}
    if mod is not None:
        try:
            cfg = mod.load_config(mod.resolve_config_paths(None))
        except Exception:
            pass
    if cfg.get("SMTP_HOST") and cfg.get("NOTIFY_EMAIL_TO"):
        print(f"  Configured: alerts sent to {cfg['NOTIFY_EMAIL_TO']} (server {cfg['SMTP_HOST']}).")
    else:
        print(f"  {BAD}NOT configured: alerts only go to the system journal{END_BAD} (journalctl -t web-monitor).")
        print(f"  To enable it: set SMTP_HOST and NOTIFY_EMAIL_TO in {'/etc/default/app-health-check.conf'}")
        print("  (see doc/en/app-health-check.conf.example for the other SMTP keys).")

    print()
    print("REPORTS")
    try:
        reports = sorted(f for f in os.listdir(LOG_DIR) if f.endswith(".log"))
    except OSError:
        reports = []
    if reports:
        print(f"  {len(reports)} report(s) in {LOG_DIR} ({journal_days() or 'all'} days kept); latest: {os.path.join(LOG_DIR, reports[-1])}")
    else:
        print(f"  no report in {LOG_DIR}")
    print("  System journal: journalctl -t web-monitor -n 50")
    return 0


_LOCK = None


def take_lock():
    """A single MODIFYING run at a time (timer, manual launch): immediate abort (code 75) if another
    is running. Folder: NGINX_TOOLS_LOCK_DIR (tests), otherwise /run/lock, otherwise the temporary folder."""
    global _LOCK
    if os.environ.get("VERROU_TENU_web_monitor"):
        return
    import fcntl
    d = os.environ.get("NGINX_TOOLS_LOCK_DIR", "/run/lock")
    if not (os.path.isdir(d) and os.access(d, os.W_OK)):
        d = tempfile.gettempdir()
    path = os.path.join(d, "web-monitor.lock")
    f = open(path, "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        eprint(f"ERROR: another run of web-monitor.py is in progress (lock {path}) — aborting.")
        sys.exit(75)
    _LOCK = f
    os.environ["VERROU_TENU_web_monitor"] = "1"


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
    # SIGPIPE has its default behavior (like cat or grep): if the reader closes early ("| head"), the
    # process stops silently. Python ignores it otherwise, and a BrokenPipeError can occur until the final
    # flush of the buffers ("Exception ignored on flushing sys.stdout"), out of reach of any try/except.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        text = changelog_section(CHANGELOG_FILE, "web-monitor.py")
    except OSError:
        print(f"Changelog not found: {CHANGELOG_FILE}", file=sys.stderr)
        return 1
    if sys.stdout.isatty():
        text = re.sub(r"(\d+\.\d+\.\d{8}\.\d{6})", "\x1b[1;36m\\1\x1b[0m", text)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        # Reader closed early (e.g. "| head"): silent output, no Python traceback.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


class SortedHelp(argparse.HelpFormatter):
    """Help options in ALPHABETICAL ORDER (long name, without the dashes: "-h, --help" is filed under "help"),
    in the list as in the "usage" line."""
    @staticmethod
    def _key(action):
        names = action.option_strings or [action.dest]
        return names[-1].lstrip("-").lower()

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions if groups else sorted(actions, key=self._key), groups, prefix)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._key))


class LocalizedArgumentParser(argparse.ArgumentParser):
    """argparse in the display language (LANGUAGE): help texts and error messages of the program translated by TR; in French, also the most frequent argparse
    messages and the help section titles (same approach as app-health-check.py)."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", SortedHelp)             # options in alphabetical order
        if kwargs.get("description"):
            kwargs["description"] = TR(kwargs["description"])
        super().__init__(*args, **kwargs)
        if "--anonymize" not in self._option_string_actions:
            self.add_argument("--anonymize", action="store_true", help="Anonymizes what is displayed (IP addresses, emails, identifiers, tokens) with stable pseudonyms; key ANONYMIZE")

    def add_argument(self, *args, **kwargs):
        if isinstance(kwargs.get("help"), str):
            kwargs["help"] = TR(kwargs["help"])
        return super().add_argument(*args, **kwargs)

    def error(self, message):
        # 2.71: option names never translated (« --sort » became « --tri »). 2.74: a message translated WHOLE by the catalogue (its msgid includes the option:
        # « --days expects a number of days … ») keeps that translation when every option name is still there; otherwise the options are set aside
        options = re.findall(r"(?<![\w-])--[a-z][\w-]*", message)
        whole = TR(message)
        message = whole if whole != message and all(re.search(rf"(?<![\w-]){re.escape(o)}(?![\w-])", whole) for o in options) else \
            TR(re.sub(r"(?<![\w-])--[a-z][\w-]*", lambda m: literal(m.group(0)), message))
        if LANGUAGE == "fr":
            message = re.sub(r"^unrecognized arguments: (.+)$", r"argument(s) non reconnu(s) : \1", message)
            message = re.sub(r"^argument (\S+): invalid int value: (.+)$", r"argument \1 : entier invalide : \2", message)
            message = message.replace("expected one argument", "une valeur est attendue")
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog} : erreur : {message}\n" if LANGUAGE == "fr" else f"{self.prog}: error: {message}\n")

    def format_usage(self):
        return super().format_usage().replace("usage: ", "usage : ", 1) if LANGUAGE == "fr" else super().format_usage()

    def format_help(self):
        text_value = super().format_help()
        if LANGUAGE != "fr":
            return text_value
        return (text_value.replace("usage: ", "usage : ", 1).replace("\noptions:\n", "\noptions :\n")
                .replace("show this help message and exit", "affiche cette aide et quitte")
                .replace("show program's version number and exit", "affiche la version et quitte"))


def launch_with_report(func):
    """--report-err: copies the output and prints at the end of the run an error report to copy-paste (apps/_rapport.py).
    Without the option (or with --help, --version, --changelog): normal run."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        folder = os.path.dirname(os.path.abspath(__file__))
        try:
            spec = importlib.util.spec_from_file_location("_rapport", os.path.join(folder, "apps", "_rapport.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"--report-err unavailable ({e}) — normal run.", file=sys.stderr)
            return func()
        return module.lancer(func, os.path.basename(__file__), __version__, folder)
    return func()


def show_configuration(defaults, problems):
    """Two start lines: WHICH configuration file(s) were read, and the important options that result (as well as the display language)."""
    if "--changelog" in sys.argv:          # --changelog shows only the journal
        return
    try:
        print(_load_module("_config").ligne_configuration(CONFIG_FILES, EXPLICIT_CONFIG, SCRIPT_NAME))
    except Exception:
        return
    options = [f"--lang {LANGUAGE}" + (f" ({LANGUAGE_ORIGIN})" if LANGUAGE_ORIGIN else "")] + [f"--{o.replace('_', '-')} {'yes' if v is True else 'no' if v is False else literal(','.join(v) if isinstance(v, list) else v)}" for o, v in sorted(defaults.items())]
    print("  Options: " + " · ".join(options) + " (command line takes precedence)")
    for p in problems:
        eprint(f"  WARNING: configuration value ignored: {p}")


def execute():
    """Protected main(): Ctrl-C (anywhere, even at a question) ends cleanly, without a traceback (code 130)."""
    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl-C).", file=sys.stderr)
        return 130

def main():
    global VERBOSE
    parser = LocalizedArgumentParser(
        description="Automatic nginx + Odoo monitoring: runs the project's tools, alerts only if action is needed.")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/web-monitor.conf, then the personal file .web-monitor.conf; UPPERCASE options: APP, DAYS, DETAILS, INTERVAL_HOURS, LANGUAGE, NO_PAGER, NO_PROMPT, REVERSE, SORT, TABLE)")
    parser.add_argument("--run", action="store_true", help="Run the monitoring (default behavior)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the tools and show the decision, without e-mail or changing the log reading positions")
    parser.add_argument("--install-timer", action="store_true", help="Install and enable the systemd timer")
    parser.add_argument("--interval-hours", type=int, default=1, metavar="N",
                        help="With --install-timer: interval in hours, 1 to 24 (default: 1)")
    parser.add_argument("--uninstall-timer", action="store_true", help="Remove the systemd timer")
    parser.add_argument("--status", action="store_true", help="Timer state, last pass, last alert")
    parser.add_argument("--lang", choices=AVAILABLE_LANGUAGES, metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--list-users", action="store_true",
                        help="List all Odoo logins (or BigBlueButton participants) in alphabetical order")
    parser.add_argument("--days", type=int, metavar="N",
                        help="With --summary or --list-users: limit to the last N days (1 to 366; summary: 30 by default)")
    parser.add_argument("--details", action="store_true",
                        help="With --list-users: add each account's traffic (slower to compute)")
    parser.add_argument("--table", action="store_true",
                        help="With --list-users: compact numbered table, one column per field (--table-fields), each as narrow as its content (titles cut, on two lines), colors for today's logins and the busiest accounts")
    parser.add_argument("--table-fields", type=table_fields, metavar="FIELDS",
                        help="With --table or --csv: the fields to show, in that order, separated by commas (all: every field) — " + literal(",".join(FIELD_KEYS)) + " (implies --list-users --table)")
    parser.add_argument("--csv", metavar="FILE",
                        help="With --list-users: also write every value, never cut, in a CSV file (« ; » separator, decimal comma in French: Excel opens it directly; - = standard output)")
    parser.add_argument("--group", metavar="NAME",
                        help="With --list-users: only the members of this Odoo group (exact name, otherwise part of the name; accents and case ignored)")
    parser.add_argument("--repeat-header", action="store_true",
                        help="With --table: the column titles also at the bottom of the table")
    parser.add_argument("--stats", action="store_true",
                        help="With --list-users: statistics at the end — members per group and tag, internal / portal, countries, e-mail domains, systems, browsers, top 10 of the most active accounts (logins, minutes, pages read and written, MB, events, surveys)")
    parser.add_argument("--save-recommended", action="store_true",
                        help="With --dry-run: still saves the recommended IPs (used by the b key of app-log-live.py)")
    parser.add_argument("--sort", type=sort_key, default="name", metavar="KEY",
                        help="With --list-users: sort order — name (default), login, uid, ip, created, first, last, logins, minutes, type, os, pages, written, received, sent, events, surveys, seen, vpn; name, login, ip, uid, first, os: ascending; the others: descending")
    parser.add_argument("--reverse", action="store_true", help="With --sort: reverse the sort order")
    parser.add_argument("--suspect-users", action="store_true",
                        help="Logged-in Odoo accounts whose activity is suspicious (score: bursts, tools, refused accesses, forms in bulk, malicious URLs, disposable e-mail…) and watched accounts, then investigation of each one (all its IP addresses, e-mail, Internet) with the offer to ban or watch it")
    parser.add_argument("--investigate-user", metavar="LOGIN",
                        help="Investigation of ONE Odoo account (all its IP addresses, other accounts on them, e-mail, Internet with consent), then the offer to ban or watch it")
    parser.add_argument("--ban-odoo-user", metavar="LOGIN",
                        help="Ban an Odoo account after its investigation: account archived (no more login, sessions ended), IP addresses used by no other account banned at the firewall; with confirmation (--yes: without)")
    parser.add_argument("--unban-odoo-user", metavar="LOGIN",
                        help="Lift the ban of an Odoo account: account restored and the IP addresses banned with it unbanned")
    parser.add_argument("--watch-odoo-user", metavar="LOGIN",
                        help="Watch an Odoo account: always listed in the summary (SUSPICIOUS ACTIVITY section) and marked in app-log-live.py")
    parser.add_argument("--unwatch-odoo-user", metavar="LOGIN", help="Stop watching an Odoo account")
    parser.add_argument("--internet", action="store_true",
                        help="With --suspect-users, --investigate-user, --ban-odoo-user: search the e-mail and the IP addresses on the Internet (StopForumSpam, Gravatar, DuckDuckGo) without asking — they are sent to these services")
    parser.add_argument("--unban-check", action="store_true",
                        help="Re-evaluate manual bans (runs nginx-log-audit.sh --unban-check)")
    parser.add_argument("--ban-recommended", action="store_true",
                        help="Ban the IPs recommended by the last pass (e.g. the timer's), with confirmation")
    parser.add_argument("--yes", action="store_true", help="With --apply, --ban-recommended, --ban-odoo-user, --unban-odoo-user: without questions (--suspect-users: every account investigated, none banned)")
    parser.add_argument("--apply", action="store_true",
                        help="Summary, then the program makes the recommended fixes itself (bans, nginx reload, nginx-hardening.sh --update, timer…): one question per fix, --yes without questions")
    parser.add_argument("--no-prompt", action="store_true",
                        help="Do not offer to ban the recommended IPs at the end of a pass")
    parser.add_argument("--report-err", action="store_true",
                        help="At the end, show an error report to copy and paste (program, version, server, failures, warnings); without ban questions or pager")
    parser.add_argument("--no-pager", action="store_true",
                        help="Do not offer to open the full report in less at the end of a pass")
    parser.add_argument("--app", metavar="NAME",
                        help="Application behind nginx (profile apps/NAME.conf: odoo, bbb…) — detected automatically by default")
    parser.add_argument("--summary", action="store_true",
                        help="Numbered summary (today, D-1, D-2, 7 days, 30 days or --days N): traffic, blocks and attacks, errors, highlights, log coverage")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each command run")
    parser.add_argument("--version", action="version", version=f"web-monitor.py version {__version__}")
    parser.add_argument("--changelog", action="store_true", help="Show the changelog")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version displays it itself)
        print(f"web-monitor.py v{__version__}")
    try:                                      # configuration file: default values of the options (the command line overrides them)
        defaults, problems = _load_module("_config").defauts_options(
            CONFIG, {k: (o, sort_key if t is None else t) for k, (o, t) in SCHEMA_CONFIG.items()})
        parser.set_defaults(**defaults)
    except Exception as e:
        defaults, problems = {}, [f"apps/_config.py unreadable ({e})"]
    args = parser.parse_args()
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    show_configuration(defaults, problems)
    VERBOSE = args.verbose
    global DAYS, DAYS_GIVEN
    if args.days is not None:
        if not 1 <= args.days <= 366:
            parser.error("--days expects a number of days between 1 and 366")
        DAYS, DAYS_GIVEN = args.days, True
    # --changelog, --status and the timer do not need the application: they work everywhere (e.g. a
    # workstation without Odoo or BBB, where the profile cannot be detected). The profile is only loaded for --summary and the run.
    if args.changelog:
        return show_changelog()
    given = {a.split("=", 1)[0] for a in sys.argv[1:] if a.startswith("--")}
    listing = given & {"--table-fields", "--group", "--csv", "--stats", "--repeat-header"}
    if listing:                                         # 2.67: these options only make sense with --list-users — 2.69: ON THE COMMAND LINE only: the same
        args.list_users = True                          # keys in a configuration file (TABLE_FIELDS, STATS…) are settings of --list-users, never a reason to list
        args.table = args.table or listing != {"--csv"}  # (the timer, run without option, keeps monitoring); --csv alone: the file only
    set_cms()
    if not args.dry_run:
        migrate_installation()
    global PROFILE, NO_PAGER, NO_PROMPT, APPLY, YES, SAVE_RECO
    SAVE_RECO = args.save_recommended and args.dry_run
    APPLY, YES = args.apply, args.yes
    if args.apply:                                      # --apply: the fixes of the summary
        args.summary = True
    NO_PAGER = args.no_pager or args.report_err          # --report-err: never a pager nor a question (report to copy-paste)
    NO_PROMPT = args.no_prompt or args.report_err
    # Root: required AT THE START for anything that modifies (run, bans, timer, fixes); the read modes only warn about what will be incomplete.
    user_reading = args.suspect_users or args.investigate_user              # read-only (the ban / watch offered at the end checks root itself)
    user_writing = args.ban_odoo_user or args.unban_odoo_user or args.watch_odoo_user or args.unwatch_odoo_user
    modifying = args.install_timer or args.uninstall_timer or args.apply or args.ban_recommended or user_writing or not (
        args.dry_run or args.summary or args.list_users or args.unban_check or args.status or user_reading)
    if modifying and not _load_module("_config").est_root():
        eprint("ERROR: root required (sudo) to change anything (run, bans, timer, fixes) — only --dry-run, --list-users, --status, --summary and --unban-check work without privileges.")
        return 2
    notice = _load_module("_config").avis_non_root("web-monitor.py", "fail2ban logs, PostgreSQL (accounts, e-mails), firewall and nginx -T incomplete or unreadable")
    if notice:
        eprint(notice)
    if args.status:
        return show_status()
    if args.summary or not (args.install_timer or args.uninstall_timer):
        try:
            PROFILE = load_profile(args.app)
        except Exception as e:            # ProfilError (message in French)
            eprint(f"ERROR: {e}")
            return 2
        set_cms()                                      # the profile is known: BigBlueButton → any CMS is sensitive
    if args.summary:
        return show_summary()
    internet = True if args.internet else None
    if args.suspect_users:
        return suspect_users(args.yes, internet)
    if args.investigate_user:
        return 0 if investigate_user(args.investigate_user, ask=not args.yes, internet=internet if internet else (False if args.yes else None)) else 1
    if args.watch_odoo_user or args.unwatch_odoo_user:
        return watch_user(args.watch_odoo_user or args.unwatch_odoo_user, bool(args.watch_odoo_user))
    if args.ban_odoo_user:
        take_lock()
        inv = investigate_user(args.ban_odoo_user, ask=not args.yes, internet=internet if internet else (False if args.yes else None), offer_actions=False)
        return ban_user(args.ban_odoo_user, args.yes, inv) if inv else 1
    if args.unban_odoo_user:
        take_lock()
        return unban_user(args.unban_odoo_user, args.yes)
    if not (args.dry_run or args.list_users or args.unban_check):   # run, bans, timer: modifying
        take_lock()
    if args.ban_recommended:
        return ban_recommended(args.yes)
    if args.list_users:
        return list_users(args.details, args.table, args.sort, args.reverse, args.table_fields, args.group, args.csv, args.repeat_header, args.stats)
    if args.unban_check:
        nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
        app = ["--app", PROFILE["APP_NAME"]] if PROFILE.get("APP_NAME") else []
        with foreground_child():
            return subprocess.run(["bash", nla, "--unban-check"] + app + verbose_args()).returncode
    if (args.install_timer or args.uninstall_timer or not args.dry_run) and os.geteuid() != 0:
        print("ERROR: root required (sudo) — only --dry-run and --status work without privileges.", file=sys.stderr)
        return 2
    if args.install_timer:
        if not 1 <= args.interval_hours <= 24:
            parser.error("--interval-hours expects a value between 1 and 24")
        return install_timer(args.interval_hours)
    if args.uninstall_timer:
        return uninstall_timer()
    return do_run(args.dry_run)


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(execute))
    except BrokenPipeError:
        # Reader closed early (e.g. "| head"): silent output, no Python traceback.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
