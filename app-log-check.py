#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# app-log-check.py — analyzes Odoo's systemd journal (journalctl -u <service>) to spot two things that
# nginx-log-audit.sh can NOT see (these events never appear in the nginx logs, only in Odoo's own
# journal): (1) protocol-level attacks against Odoo's gevent/longpolling port (e.g. a TLS client that connects
# directly in plain HTTP, bypassing nginx entirely), and (2) unhandled Python traces (tracebacks), grouped by
# final message to spot a recurring bug at a glance.
#
# VERSION HISTORY (summary — see app-log-check.changelog.txt for full detail):
#   2.22.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   2.21.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   2.20.20261015.215241 — Source code, comments and changelog in English (display stays French/English via lang/app-log-check.fr.po).
#   2.19.20261015.080630 — « Limited rights (not root) » notice at startup.
#   2.18.20261013.084000 — Base64 / very long lines abbreviated in tracebacks.
#   2.17.20261012.213000 — Odoo service deduced from db_user (Odoo configuration).
#   2.16.20261012.103600 — Configuration file created at first start (all options commented out); doc/app-log-check.conf.example template completed.
#   2.15.20261010.215000 — French or English display (--lang); configuration file (LANGUAGE and options) and -c/--config.
#   2.14.20261009.112443 — --errors-only option: only the error detail (traces [2], other errors [3], diagnostics [5]).
#   2.13.20261007.175327 — Diagnostics: « permanent » flag (cause that comes back as long as the setting is not fixed).
#   2.12.20261007.171721 — Summary at the top; section [5]: cause and solution of e-mail errors (SMTP 452, 503, 550…) and e-mail state read from Odoo.
#   2.11.20261007.093208 — Address labels: whitelist then places (apps/_listes.py); « shared address » verdict.
#   2.10.20261002.214327 — --by-hour: per-account analysis, bursts after a login elsewhere, session modules, journal volume; first line of EVERY run (even --help): name and version.
#   2.9.20261002.201545 — --by-hour option: report of problems per hour and per day, pages in error, « Session expired » and its diagnosis.
#   1.0.20260922.083916 — First version.
#   1.1.20260922.085118 — Service auto-detection (--service becomes optional): tries "erplibre.service"
#                          (real name in PROD) then "erplibre_erplibre.service" (real name in DEV/LAB) via
#                          "systemctl list-unit-files", uses the first one found. An explicit --service keeps
#                          absolute priority over auto-detection.
#   1.2.20260922.123120 — Added --namespace NAME: needed to keep working if the Odoo service
#                          is isolated in its own journal namespace (LogNamespace=) to give it a
#                          retention limit independent of the other services. Part of the
#                          remembered (incremental) position, to never mix the positions of two namespaces.
#   1.3.20260924.203547 — New section [4] « known noise, harmless » (source .map files of old asset
#                          bundles, push subscriptions with an old VAPID key): counted apart, with an
#                          explanation, instead of being mixed with the real errors. New -v/--verbose option
#                          (journalctl/systemctl commands). Service detection by EXACT name.
#   1.4.20260925.073513 — Section [3] grouped (account, first/last occurrence, truncated example); for a
#                          failed SQL query, shows the table and the PostgreSQL reason (the « ERROR: » line that follows
#                          the query, hidden until now). New known noise: concurrent update conflict
#                          (automatically replayed by Odoo, recognized only if the reason is in the journal) and
#                          invalid OAuth token.
#   1.5.20260926.132132 — --changelog: pipe interruption (« | head ») without Python trace (BrokenPipeError),
#                          defect found by the new test suite.
#   1.6.20260926.211237 — --changelog: default SIGPIPE (no more message at Python's final flush).
#   1.7.20260926.223504 — Known noise: websocket subscription refused by web_editor (Odoo 18 bug fixed upstream).
#   2.0.20260927.145909 — Renamed (old name: chk-odoo-logs.py); application profiles (--app); analysis of journals
#                          in files (BBB: bbb-web.log), grouped by message, incremental follow-up.
#   2.1.20260927.192332 — IP of protocol attacks in magenta (terminal only).
#   2.2.20260927.202645 — Changelog in the doc/ subfolder (fallback on the old location).
#   2.3.20260928.083340 — Accent: « Fenêtre » in the header.
#   2.4.20260929.144332 — Length guard on journal lines (64 KB) before the regular expressions.
#   2.5.20260929.195459 — Help: options in alphabetical order.
#   2.6.20260930.084200 — Ctrl-C: clean exit (code 130), without call trace.
#   2.8.20261002.064915 — Permission refusals (Access Denied by ACLs, INFO) as known noise, detail per user.
#   2.7.20260930.163902 — --report-err option: error report to copy-paste at the end of the run.
#
# Usage:
#   python3 app-log-check.py [--service NOM] [--init] [--last HEURES] [--errors-only] [--full-trace] [-v|--verbose] [--version]
#   app-log-check.py --by-hour [--days N] [--top N]   report of problems PER HOUR AND PER DAY (pages in error, « Session expired »)
#                            [--changelog]
#
#   --service NAME  : name of the systemd unit to query. Without this option: auto-detection among
#                      "erplibre.service" (PROD) and "erplibre_erplibre.service" (DEV/LAB), via
#                      "systemctl list-unit-files" — the first one that really exists on this machine is
#                      used. To be given explicitly if the name differs from the two above.
#   --namespace NAME: journal namespace to query (e.g. "odoo" if the Odoo service was isolated via
#                      LogNamespace= in a systemd override). Without this option: default namespace, as
#                      before any isolation. Part of the remembered position (incremental): switching from one
#                      namespace to another never mixes the positions of the two.
#   --init          : analyzes the whole history available in the journal (limited by journald's retention,
#                      not by this script). Without this option: only the entries since the last run
#                      (position remembered per service in ~/.local/state/app-log-check/).
#   --last HOURS    : restricts to the last HOURS hours, independently of the remembered position (like
#                      nginx-log-audit.sh) — never touches that position, a normal call then resumes it
#                      exactly where it was.
#   --full-trace    : shows the complete Python trace for EVERY error group (by default, a single
#                      complete example is shown per group — largely enough to identify the cause, and avoids an
#                      unreadable report if the same bug happened 200 times).
#   --version       : displays the version and exits.
#   --changelog     : displays app-log-check.changelog.txt.
#
# Requires access to journalctl for the service concerned (root, or member of the "systemd-journal" group on
# most distributions).
# ========================================================================================================================

import argparse
import bisect
import shlex
import signal
import textwrap
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections import Counter, OrderedDict
from datetime import datetime, timedelta

__version__ = "2.22.20261019.150215"

DEFAULT_SERVICE = "erplibre_erplibre.service"
STATE_DIR = os.environ.get("APP_LOG_CHECK_STATE_DIR") or os.path.expanduser("~/.local/state/app-log-check")

# A "structured" Odoo line always starts with its own timestamp + level — this is what distinguishes a
# NEW log entry from a "raw" continuation line (e.g. a Python traceback line, which does not have this
# prefix). journalctl -o cat already removes its OWN syslog prefix, so this pattern only concerns the
# internal format of Odoo's Python logger.
LINE_MAX = 65536          # journal line length guard (bounds the CPU spent by the regular expressions)
ODOO_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ (INFO|ERROR|WARNING|CRITICAL|DEBUG) ")

# Last line of a typical Python exception: "ExceptionName: message" or "module.ExceptionName: message".
EXCEPTION_LINE_RE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning)):\s*(.*)$")

# Protocol-level attacks/anomalies (gevent refuses the connection before even reaching Odoo itself).
PROTOCOL_ISSUE_RE = re.compile(r"(Invalid HTTP method|Invalid http version|Invalid request)", re.IGNORECASE)
SOURCE_ADDR_RE = re.compile(r"\(from \('([0-9a-fA-F:.]+)',\s*(\d+)\)\)")


VERBOSE = False
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]


def _start():
    """Common context (apps/_i18n.py: language, configuration, translated print / input, parser); module missing: French, no configuration."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "APP_LOG_CHECK_LANG")
    except Exception:
        return None


I18N = _start()
LANGUAGE = I18N.langue if I18N else "fr"
TR = I18N.tr if I18N else (lambda text_value: text_value)
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 — every displayed text goes through the translator (no effect when the display language is the source language)
# Configuration file options (/etc/default/app-log-check.conf, then the personal file .app-log-check.cfg): KEY -> (command-line option, type).
# LANGUAGE: en, fr or auto (follow LC_ALL / LANG).
SCHEMA_CONFIG = {"APP": ("app", str), "DAYS": ("days", int), "ERRORS_ONLY": ("errors_only", bool), "FULL_TRACE": ("full_trace", bool), "NAMESPACE": ("namespace", str),
                 "SERVICE": ("service", str), "TOP": ("top", int), "VERBOSE": ("verbose", bool)}


def vcmd(cmd):
    """Displays the exact external command (argument list) before running it, if --verbose."""
    if VERBOSE:
        eprint("+ " + shlex.join(cmd))


# Magenta for malicious elements (IP of protocol attacks) — terminal only, never in a pipe.
BAD, END_BAD = ("\x1b[1;35m", "\x1b[0m") if sys.stdout.isatty() else ("", "")


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def changelog_path(display_name):
    """Changelog in the doc/ subfolder; fallback on the old location (next to the program) as long as
    the installation has not been reorganized."""
    folder = os.path.dirname(os.path.realpath(__file__))
    new = os.path.join(folder, "doc", display_name)
    old = os.path.join(folder, display_name)
    return new if os.path.isfile(new) or not os.path.isfile(old) else old


def show_changelog():
    # SIGPIPE has its default behavior (like cat or grep): if the reader closes early (« | head »), the
    # process stops silently. Python otherwise ignores it, and a BrokenPipeError can occur up to the final
    # flush of the buffers (« Exception ignored on flushing sys.stdout »), out of reach of any try/except.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    path = changelog_path("app-log-check.changelog.txt")
    if not os.path.isfile(path):
        eprint(f"Changelog not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if sys.stdout.isatty():
        content = re.sub(
            r"^(## [0-9]+\.[0-9]+\.[0-9]{8}\.[0-9]{6}.*)$",
            "\x1b[1;36m\\1\x1b[0m",
            content,
            flags=re.MULTILINE,
        )
    try:
        sys.stdout.write(content)
        sys.stdout.flush()
    except BrokenPipeError:
        # Reader closed early (e.g. « --changelog | head »): silent exit, without Python trace. The
        # descriptor is redirected to /dev/null so that Python's final flush does not fail in turn.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def migrate_path(old, new):
    """Program renaming in 2.0: renames the old file or folder if it exists and the new one does NOT exist
    yet (never overwrites); silent if nothing to do or if rights are missing."""
    if os.path.exists(old) and not os.path.exists(new):
        try:
            os.makedirs(os.path.dirname(new) or ".", exist_ok=True)
            os.rename(old, new)
            print(f"Migration (programs renamed, version 2.0): {old} → {new}", file=sys.stderr)
        except OSError:
            pass


def state_file_path(service, namespace=None):
    if not os.environ.get("APP_LOG_CHECK_STATE_DIR"):
        migrate_path(os.path.expanduser("~/.local/state/chk-odoo-logs"), STATE_DIR)
    os.makedirs(STATE_DIR, exist_ok=True)
    key = f"{namespace}__{service}" if namespace else service
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    return os.path.join(STATE_DIR, f"{safe_name}.last")


def read_last_run(service, namespace=None):
    path = state_file_path(service, namespace)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return None
    return None


def write_last_run(service, when, namespace=None):
    path = state_file_path(service, namespace)
    with open(path, "w", encoding="utf-8") as f:
        f.write(when)


def run_journalctl(service, since=None, namespace=None):
    cmd = ["journalctl", "-u", service, "-o", "cat", "--no-pager"]
    if namespace:
        cmd += ["--namespace", namespace]
    if since:
        cmd += ["--since", since]
    try:
        vcmd(cmd)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        eprint("ERROR: 'journalctl' command not found on this system.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        eprint("ERROR: journalctl took more than 60s to answer — try --last with a shorter window.")
        sys.exit(1)
    if result.returncode != 0:
        eprint(f"WARNING: journalctl returned code {result.returncode}.")
        if result.stderr.strip():
            eprint(result.stderr.strip())
        if "No entries" not in (result.stderr or "") and not result.stdout:
            eprint("(unknown unit, or insufficient rights — root or member of the 'systemd-journal' group required)")
    return result.stdout.splitlines()


def parse_entries(lines):
    """Groups the raw lines into 'entries': an Odoo structured line + every continuation line that follows
    (e.g. a complete Python traceback) up to the next structured line."""
    entries = []
    current = None
    for line in lines:
        line = line[:LINE_MAX]          # guard: abnormally long line truncated before the regular expressions
        if ODOO_LINE_RE.match(line):
            if current is not None:
                entries.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
        # a raw line BEFORE any structured entry (rare, truncated window start) is ignored.
    if current is not None:
        entries.append(current)
    return entries


BLOB_RE = re.compile(r"[A-Za-z0-9+/=_-]{60,}")
DISPLAYED_LINE_MAX = 200


def abbreviate(text_line):
    """Displayed line: long runs without spaces (image or base64 data, tokens) replaced by « [data: N chars] », then cut at 200 characters."""
    text_line = BLOB_RE.sub(lambda m: f"[data: {len(m.group(0))} chars]", text_line)
    return text_line if len(text_line) <= DISPLAYED_LINE_MAX else text_line[:DISPLAYED_LINE_MAX - 1] + "…"


def extract_headline(entry):
    """For an entry containing a traceback: the LAST line that looks like 'ExceptionClass: message' —
    the most specific/outermost exception in a 'during handling of...' chain. Failing that, the
    last non-empty line."""
    candidates = [l.strip() for l in entry[1:] if EXCEPTION_LINE_RE.match(l.strip())]
    if candidates:
        return abbreviate(candidates[-1])
    for l in reversed(entry[1:]):
        if l.strip() and not (BLOB_RE.fullmatch(l.strip())):        # a base64 data line is not a message
            return abbreviate(l.strip())
    return abbreviate(entry[0].strip())


ERROR_PREFIX_RE = re.compile(r"^\S+ \S+ \d+ (?:ERROR|CRITICAL) \S+ ")
SQL_TABLE_RE = re.compile(r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+\"?(\w+)", re.IGNORECASE)


def error_signature(entry):
    """Grouping key of an uncategorized error. Failed SQL query (« odoo.sql_db: bad query »): targeted table
    + PostgreSQL reason, which Odoo writes on an « ERROR: ... » line AFTER the query (continuation line
    — the first line only contains the query, the least useful part). Other messages: text without the date
    or PID, hexadecimal identifiers and numbers neutralized, so that occurrences of the same problem are
    grouped."""
    head = entry[0].strip()
    msg = ERROR_PREFIX_RE.sub("", head)
    if "odoo.sql_db: bad query" in msg:
        reason = next((l.strip() for l in entry[1:] if l.strip().startswith("ERROR:")), "")
        m = SQL_TABLE_RE.search(msg)
        table = m.group(1) if m else "?"
        return (f"odoo.sql_db: failed SQL query on « {table} » — "
                + (reason if reason else "PostgreSQL reason missing from the entry (see --full-trace)"))
    msg = re.sub(r"\b[0-9a-f]{7,}\b", "…", msg)
    msg = re.sub(r"\d+", "N", msg)
    return msg[:200]


# Known and HARMLESS ERROR messages: counted apart (section [4]) rather than mixed with the real problems. Each
# entry: (regular expression searched in the whole entry, short label, explanation + action).
# Permission refusals logged at INFO by Odoo (ir.model.access): operation, user (uid), model; database in the header.
ACL_RE = re.compile(r"\d+ INFO (\S+) odoo\.addons\.base\.models\.ir_model: Access Denied by ACLs for operation: (\w+), "
                    r"uid: (\d+), model: ([\w.]+)")
ACL_LABEL = "Access rights check refused (Access Denied by ACLs, INFO level) — page served normally"


def login_odoo(database, uid):
    """Login of an Odoo user (read-only in PostgreSQL, as postgres); None if
    impossible (psql missing, database unreachable, not root)."""
    if not re.fullmatch(r"[\w-]+", database or "") or not re.fullmatch(r"\d+", str(uid)):
        return None
    try:
        r = subprocess.run(["runuser", "-u", "postgres", "--", "psql", "-d", database, "-tAc",
                            f"SELECT login || ' (' || COALESCE(p.name::text, '') || ', ' || "
                            f"CASE WHEN u.share THEN 'portal/public' ELSE 'internal' END || ')' "
                            f"FROM res_users u JOIN res_partner p ON p.id = u.partner_id WHERE u.id = {int(uid)}"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           universal_newlines=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text_value = r.stdout.strip()
    return text_value if r.returncode == 0 and text_value else None


KNOWN_BENIGN = [
    (re.compile(r"\.map should have been generated through debug assets"),
     "Source map (.map) of an old JavaScript asset bundle",
     "A browser with developer tools open (or a robot) requested the source map of an asset bundle whose version no longer exists (« most likely outdated ») — typically a page loaded before assets were regenerated (module update, restart). Odoo only generates these maps in debug=assets mode and simply answers 404. No action required."),
    (re.compile(r"could not serialize access due to concurrent update|deadlock detected"),
     "Concurrent update conflict (transaction replayed automatically by Odoo)",
     "Two requests handled in parallel by different workers modified the same row at the same time (typical case: website_visitor, when the same visitor — often a robot — loads several pages at once); PostgreSQL fails one of the two transactions, which Odoo replays automatically (« retrying » mechanism of the HTTP service, several attempts). The visitor sees nothing. Recognized ONLY when the PostgreSQL reason appears in the log. Look into it only if it is massive and continuous."),
    (re.compile(r"auth_oauth[\s\S]*Exception: invalid_request"),
     "OAuth (Google) sign-in refused: invalid token",
     "Validation of the OAuth token with the provider returned « invalid_request »: token missing, expired or forged — typically an old sign-in return URL reloaded or bookmarked, or a robot calling /auth_oauth/signin. Isolated: harmless. Repeated for real users: check the OAuth configuration in Odoo (client ID, redirect URL authorized at Google)."),
    (re.compile(r"web_editor/models/ir_websocket\.py[\s\S]*AccessDenied"),
     "Websocket subscription refused by web_editor (known Odoo 18 bug, fixed upstream)",
     "A browser asks to subscribe, through the websocket, to an editor channel (collaboration on a record) the user has no right to — typically a tab left open after a sign-out or a change of rights. Odoo 18 bug: the function raises an error instead of ignoring that channel, so the browser subscribes to NO channel (real-time notifications lost until the page is reloaded). Not an attack. Fixed upstream (« [FIX] web_editor: don't raise when subscribing », task 6545047): update the Odoo 18 sources (ERPLibre) to include it."),
    (ACL_RE,
     ACL_LABEL,
     "Odoo checked whether a user had the right to perform an operation (most often « write », modify) on a model, the answer was no, and Odoo logs this refusal at INFO level. This is not a modification attempted by the visitor nor an attack: most often, the website checks while displaying a page whether the signed-in person can edit it (« Edit » button, editable fields), and the page is served normally — the werkzeug « 200 » line of the same process follows immediately. Harmless. Look into it only if the user SHOULD have this right (rights missing from their group), or if the operation is create/unlink in large numbers from an unknown account. Details per user below."),
    (re.compile(r"InvalidVapidError: Invalid VAPID public key"),
     "Subscription to push notifications with an old VAPID key",
     "A browser retries to subscribe to push notifications with the public VAPID key from before a regeneration; Odoo simply compares this key to the one in the database (mail.push.device) and refuses. The server's keys are valid; the browser will subscribe again with the right key. No action required, unless the message repeats in large numbers from the same user."),
]


def analyze(entries):
    protocol_issues = []  # list of (type, ip, port, entry)
    traceback_groups = OrderedDict()  # headline -> {"count": N, "example": entry, "first": entry0}
    other_errors = OrderedDict()  # signature -> {"count", "first", "last", "example"} (uncategorized ERROR/CRITICAL)
    benign = OrderedDict()  # label -> {"count": N, "explanation": str, "example": entry}

    for entry in entries:
        head = entry[0]
        full_text = "\n".join(entry)

        matched = False
        for rx, label, explanation in KNOWN_BENIGN:
            m_benin = rx.search(full_text)
            if m_benin:
                b = benign.setdefault(label, {"count": 0, "explanation": explanation, "example": entry})
                b["count"] += 1
                if rx is ACL_RE:                     # detail: (database, operation, uid, model) -> count
                    key_value = m_benin.groups()
                    b.setdefault("details", OrderedDict())[key_value] = b.get("details", {}).get(key_value, 0) + 1
                matched = True
                break
        if matched:
            continue

        m = PROTOCOL_ISSUE_RE.search(full_text)
        if m:
            addr = SOURCE_ADDR_RE.search(full_text)
            ip = addr.group(1) if addr else "?"
            port = addr.group(2) if addr else "?"
            protocol_issues.append((m.group(1), ip, port, entry))
            continue

        if "Traceback (most recent call last):" in full_text:
            headline = extract_headline(entry)
            if headline not in traceback_groups:
                traceback_groups[headline] = {"count": 0, "example": entry}
            traceback_groups[headline]["count"] += 1
            continue

        if re.search(r"\b(ERROR|CRITICAL)\b", head):
            sig = error_signature(entry)
            g = other_errors.setdefault(sig, {"count": 0, "first": head[:23], "last": head[:23], "example": entry})
            g["count"] += 1
            g["last"] = head[:23]

    return protocol_issues, traceback_groups, other_errors, benign


# ------------------------------------------------------------------------------------------------------------------
# Diagnostics: probable cause and solution of the errors we know how to explain (summary and section [5])
# ------------------------------------------------------------------------------------------------------------------
MAIL_ID_RE = re.compile(r"failed sending mail \(id: (\d+)\)")
DB_ERROR_RE = re.compile(r"\b(?:ERROR|CRITICAL|WARNING) (\S+) odoo")
MAIL_CONTEXT_RE = re.compile(r"MailDeliveryException|smtplib|ir_mail_server|mail_mail|SMTP", re.I)
SENDER_RE = re.compile(r'"([^"]+)" \(header From\) while using "([^"]+)" as envelope sender')
BATCH_LIMIT = "mail.session.batch.size"

DIAGNOSTICS = [
    {"id": "smtp-sender", "family": "e-mail", "short": "sender refused (550)",
     "pattern": re.compile(r"not allowed to send emails? as|Sender address rejected|Sender verify failed|SMTPSenderRefused: \((?:550|553)|header From.{0,60}envelope sender", re.I),
     "title": "E-mails refused: the « From » address is not the sender authorized by the mail server (550)",
     "why": "The mail server requires the « From » address (From header) to be that of the authorized sender: the SMTP account, or one of its aliases. Odoo sets as « From » the address of the person who triggers the sending (here a personal address), while the envelope sender is the SMTP account address: the server refuses each e-mail, which stays in « Delivery Failed ». « SMTP server 'None' » in the error means no outgoing server is registered in Odoo: it uses the smtp_* settings of odoo.conf.",
     "fix": ["Settings ▸ Technical ▸ Outgoing Mail Servers: register the server (host, port, encryption, login) instead of relying only on odoo.conf, and fill in its « From Filter » with the authorized address (e.g. admin@your-domain) or the domain.",
                  "Settings ▸ Technical ▸ System Parameters: « mail.default.from » = the local part of the authorized address and « mail.catchall.domain » = the domain (depending on the version: Technical ▸ Email ▸ Alias Domains). Odoo then replaces the « From » of unauthorized authors with this address, keeping the person's name.",
                  "Or, at the mail provider: allow this account to send « as » the other addresses of the domain (aliases, send-as identities).",
                  "Then resend the failed e-mails (see « E-mail status » below): they do not leave by themselves."]},
    {"id": "smtp-session", "family": "e-mail", "short": "per-connection message limit (452)",
     "pattern": re.compile(r"SMTPDataError: \(452|Maximum number of messages per session|too many messages (?:in|per) (?:this )?(?:session|connection)", re.I),
     "title": "E-mails not sent: the SMTP server limits the number of messages per connection (452 4.4.5)",
     "why": "Odoo sends queued e-mails in batches, reusing ONE SMTP connection for the whole batch (up to 1000 e-mails per connection by default). The mail server limits the number of messages accepted per connection: beyond it, it answers 452 « Maximum number of messages per session exceeded » and the remaining e-mails of the batch go to « Delivery Failed ». This happens mostly in bursts: several registrations at the same time produce as many confirmation e-mails at once.",
     "fix": [f"Settings ▸ Technical ▸ System Parameters (developer mode): create or edit the key « {BATCH_LIMIT} » with a value LOWER than the mail server's limit "
                  "(try 10; ask the provider for the exact limit). Odoo then opens a new connection every N e-mails.",
                  "Resend the e-mails already failed: Settings ▸ Technical ▸ Emails ▸ Emails, filter « Delivery Failed », then « Retry » on each (depending on the version, on the e-mail form): without this, the registered people will never receive it.",
                  "Also check the provider's sending cap per hour and per day: a burst of registrations may reach it."]},
    {"id": "smtp-503", "family": "e-mail", "short": "« Multiple MAIL » (503)",
     "pattern": re.compile(r"Multiple MAIL commands not allowed|SMTPSenderRefused: \(503", re.I),
     "title": "E-mails not sent: « Multiple MAIL commands not allowed » (503), cascading after another failure",
     "why": "Consequence of the 452 refusal (per-connection message limit), in the same connection: after one message fails (typically the 452), Odoo reuses the SMTP connection for the next e-mails of the batch, but the server considers a transaction is already open and refuses each new MAIL command (503). These failures arrive within the same second as those of the first problem.",
     "fix": [f"Same solution as for the 452 (per-connection message limit): a smaller « {BATCH_LIMIT} ». Without the first failure, the cascade does not happen.",
                  "If these 503s appear WITHOUT a 452 failure before, the problem lies elsewhere: check the outgoing server (a single connection per batch, authentication) and the mail server.",
                  "Then resend the failed e-mails (see « E-mail status » below)."]},
    {"id": "smtp-auth", "family": "e-mail", "short": "authentication refused (535)",
     "pattern": re.compile(r"SMTPAuthenticationError|\(535,|Authentication (?:failed|unsuccessful)|Username and Password not accepted|5\.7\.8", re.I),
     "title": "E-mails not sent: the SMTP server refuses the login or password (535)",
     "why": "Odoo cannot authenticate: password changed or expired, application password required by the provider, or two-factor authentication.",
     "fix": ["Check or renew the login and password in the outgoing server (Technical ▸ Outgoing Mail Servers ▸ « Test Connection »), or smtp_user / smtp_password in odoo.conf (then restart the service).",
                  "At Google, Microsoft and others: use an application password."]},
    {"id": "smtp-relay", "family": "e-mail", "short": "relay refused",
     "pattern": re.compile(r"Relay access denied|relay not permitted|Relaying denied|5\.7\.1[^\n]{0,60}relay", re.I),
     "title": "E-mails not sent: the SMTP server refuses to relay",
     "why": "The connection is not authenticated, or the sender does not belong to a domain this server agrees to relay.",
     "fix": ["Enable authentication (login and password) on the outgoing server; use the right port and the right encryption (587 with STARTTLS, 465 with SSL).",
                  "Use a « From » address of the domain managed by this server (see the sender diagnosis)."]},
    {"id": "smtp-connection", "family": "e-mail", "short": "SMTP server unreachable",
     "pattern": re.compile(r"SMTPServerDisconnected|SMTPConnectError|Connection (?:refused|timed out|reset)|Network is unreachable|Name or service not known", re.I),
     "title": "E-mails not sent: the SMTP server is unreachable",
     "why": "Odoo cannot reach the mail server (wrong address or port, outgoing firewall, server stopped or overloaded, DNS).",
     "fix": ["Check the host, port and encryption (Technical ▸ Outgoing Mail Servers ▸ « Test Connection », or smtp_server / smtp_port / smtp_ssl in odoo.conf).",
                  "Check that this server's firewall lets this port out, and the state of the mail server at the provider."]},
]


# A PERMANENT cause comes back with every send as long as the setting is not fixed (resending the e-mails beforehand is useless); a transient cause goes away on resend.
for _d in DIAGNOSTICS:
    _d["permanent"] = _d["id"] in ("smtp-sender", "smtp-auth", "smtp-relay")


def classify_diagnostic(text_value):
    """The diagnostic that explains this error text (the first one in the list that matches), or None. E-mail diagnostics require an SMTP context."""
    for d in DIAGNOSTICS:
        if d["pattern"].search(text_value) and (d["family"] != "e-mail" or MAIL_CONTEXT_RE.search(text_value)):
            return d
    return None


def diagnose(entries):
    """{id: {diag, n, first, last, ids (e-mails), databases, details}} for the errors (ERROR, CRITICAL, WARNING) we know how to explain."""
    res = OrderedDict()
    for entry in entries:
        head = entry[0]
        if not re.search(r"\b(ERROR|CRITICAL|WARNING)\b", head):
            continue
        text_value = "\n".join(entry)
        d = classify_diagnostic(text_value)
        if d is None:
            continue
        g = res.setdefault(d["id"], {"diag": d, "n": 0, "first": head[:19], "last": head[:19], "ids": [], "databases": Counter(), "details": Counter()})
        g["n"] += 1
        g["last"] = head[:19]
        m = MAIL_ID_RE.search(text_value)
        if m:
            g["ids"].append(int(m.group(1)))
        b = DB_ERROR_RE.search(head)
        if b:
            g["databases"][b.group(1)] += 1
        e = SENDER_RE.search(text_value)
        if e:
            g["details"][f"From: {e.group(1)} ; envelope sender (SMTP account): {e.group(2)}"] += 1
    return res


def summary_line(marker, tag, text_value):
    """One line of the summary: marker ([!] to examine, [ok] nothing, [i] information), fixed-width label, text."""
    return f"  {marker:<4} {tag:<15} {text_value}"


def show_summary(protocol_issues, traceback_groups, other_errors, benign, diag):
    """What matters, in a few lines, BEFORE the detail: problems with their known cause first."""
    print_section("SOMMAIRE")
    mails = [g for g in diag.values() if g["diag"]["family"] == "e-mail"]
    n_trace = sum(g["count"] for g in traceback_groups.values())
    n_other = sum(g["count"] for g in other_errors.values())
    n_benign = sum(b["count"] for b in benign.values())
    if mails:
        total = sum(g["n"] for g in mails)
        ids = {i for g in mails for i in g["ids"]}
        detail = ", ".join(f"{g['n']} × {g['diag']['short']}" for g in sorted(mails, key=lambda g: -g["n"]))
        print(summary_line("[!]", "E-MAIL", f"{total} sending failure(s)" + (f" ({len(ids)} distinct e-mail(s))" if ids else "")
                             + ", " + TR("from {first} to {last}").format(first=min(g['first'] for g in mails), last=max(g['last'] for g in mails)) + f" : {detail}"))
        print(summary_line("", "", "→ people did NOT receive their e-mail (registration, invitation…): cause and solution in [5]"))
    for g in [g for g in diag.values() if g["diag"]["family"] != "e-mail"]:
        print(summary_line("[!]", g["diag"]["family"].upper(), f"{g['n']} occurrence(s) : {g['diag']['short']} → cause and solution in [5]"))
    if n_trace:
        linked_count = sum(g["n"] for g in mails)
        print(summary_line("[!]", "PYTHON TRACES", f"{n_trace} occurrence(s) in {len(traceback_groups)} group(s)" + (f", including {linked_count} related to e-mails" if linked_count else "") + " → [2]"))
    else:
        print(summary_line("[ok]", "PYTHON TRACES", "nothing"))
    print(summary_line("[!]" if protocol_issues else "[ok]", "PROTOCOL", f"{len(protocol_issues)} anomaly(ies) → [1]" if protocol_issues else "nothing"))
    print(summary_line("[!]" if n_other else "[ok]", "OTHER ERRORS", f"{n_other} occurrence(s) → [3]" if n_other else "nothing"))
    if n_benign:
        print(summary_line("[i]", "KNOWN NOISE", f"{n_benign} harmless message(s) → [4]"))


def load_odoo_db():
    """Component apps/_odoo_db.py (read-only PostgreSQL access), or None."""
    path = os.path.join(SCRIPT_DIR, "apps", "_odoo_db.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("_odoo_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.VERBOSE = VERBOSE
    return module


def mail_state(database, day_count=7):
    """« E-mail state in Odoo » lines (read-only: mail.* parameters, outgoing servers, e-mails of the last DAYS days)."""
    text_lines = [f"  E-mail status in Odoo (read-only, database {database or '?'}, {day_count} last days):"]
    db = load_odoo_db()
    if db is None or not database:
        return text_lines + ["    unreadable (component apps/_odoo_db.py missing or unknown database)"]
    servers, params, courriels = db.serveurs_courriel(database), db.parametres(database, "mail."), db.courriels(database, day_count)
    if servers is None and params is None and courriels is None:
        return text_lines + ["    unreadable (PostgreSQL unreachable, or root required)"]
    if servers is not None:
        if not servers:
            text_lines.append("    Outgoing mail servers: NONE registered — Odoo uses the smtp_* settings of odoo.conf (« SMTP server 'None' » in the errors)")
        for srv in servers:
            text_lines.append(f"    Outgoing server: « {srv['nom']} » ({srv['hote']}:{srv['port']}, {srv['chiffrement'] or 'without encryption'})"
                          + (f", From filter « {srv['filtre']} »" if srv["filtre"] else ", WITHOUT From filter") + ("" if srv["actif"] else " — INACTIVE"))
    if params is not None:
        batch = params.get(BATCH_LIMIT)
        text_lines.append(f"    {BATCH_LIMIT} : " + (f"{batch} (if the 452 errors continue, choose a smaller value)" if batch
                                               else "not set — Odoo sends up to 1000 e-mails per SMTP connection"))
        others = [f"{k} = {v}" for k, v in params.items() if k != BATCH_LIMIT]
        if others:
            text_lines.append("    Other mail.* parameters: " + " ; ".join(others[:6]))
    if courriels is not None:
        e = courriels["etats"]
        text_lines.append(f"    E-mails: {e.get('sent', 0)} sent, {e.get('exception', 0)} FAILED TO SEND (to resend), {e.get('outgoing', 0)} queued"
                      + (f", {e['cancel']} cancelled" if e.get("cancel") else ""))
        if courriels["echecs_par_jour"]:
            text_lines.append("    Failures per day: " + ", ".join(f"{j} ({n})" for j, n in courriels["echecs_par_jour"].items()))
        if courriels["sujets"]:
            text_lines.append("    Failed subjects: " + " ; ".join(f"« {subject} » ({n})" for subject, n in courriels["sujets"]))
    return text_lines


def nbsp_quotes(text_value):
    """Non-breaking spaces inside the French quotes: « mail.session.batch.size » no longer breaks at the end of a line."""
    return text_value.replace("« ", "«\u00a0").replace(" »", "\u00a0»")


def show_diagnostics(diag):
    """Section [5]: for each recognized problem, when, why, and the solution; then the e-mail state in Odoo."""
    print_section("[5] Diagnostics: probable cause and solution")
    mail_database = ""
    for g in sorted(diag.values(), key=lambda g: -g["n"]):
        d = g["diag"]
        print()
        print(f"  ▶ {d['title']} — {g['n']} occurrence(s)")
        database = g["databases"].most_common(1)[0][0] if g["databases"] else ""
        if d["family"] == "e-mail" and database:
            mail_database = mail_database or database
        when = TR("from {first} to {last}").format(first=g['first'], last=g['last']) + (f", database {database}" if database else "")
        ids = sorted(set(g["ids"]))
        if ids:
            when += f" ; e-mails (id): {', '.join(map(str, ids[:10]))}" + (f" … (+{len(ids) - 10})" if len(ids) > 10 else "")
        print(textwrap.fill(nbsp_quotes(TR("When: ") + when), width=110, initial_indent="     ", subsequent_indent="            "))
        for detail, n in g["details"].most_common(2):
            print(textwrap.fill(nbsp_quotes(TR(f"Observed: {detail} ({n}×)")), width=110, initial_indent="     ", subsequent_indent="               "))
        print(textwrap.fill(nbsp_quotes(TR("Why: " + d["why"])), width=110, initial_indent="     ", subsequent_indent="               "))
        print("     Solution:")
        for i, step in enumerate(d["fix"], 1):
            print(textwrap.fill(nbsp_quotes(TR(f"{i}. {step}")), width=110, initial_indent="       ", subsequent_indent="          "))
    if any(g["diag"]["family"] == "e-mail" for g in diag.values()):
        print()
        for text_line in mail_state(mail_database):
            print(text_line)


def print_section(title):
    print()
    print(f"--- {title} ---")


# PROD uses "erplibre.service"; DEV and LAB use "erplibre_erplibre.service" — auto-detect rather than
# making the user guess --service at each call. The order does not matter (only one of the two should exist on a
# given machine), but keep the list short: adding --service remains the explicit way for any other name.
CANDIDATE_SERVICES = ["erplibre.service", "erplibre_erplibre.service"]


def _units_from_config():
    """Probable units according to the Odoo configuration found (db_user, file name); empty list otherwise."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "apps"))
        import _odoo_conf
        path = _odoo_conf.trouver()
        return _odoo_conf.unites(path) if path else []
    except Exception:  # library missing or unreadable: default list
        return []


def detect_service():
    """Returns the first unit name of CANDIDATE_SERVICES that really exists on this machine (unit file
    present, whether or not it is active), or None if neither is found."""
    for name in _units_from_config() + CANDIDATE_SERVICES:
        try:
            vcmd(["systemctl", "list-unit-files", name, "--no-legend"])
            result = subprocess.run(
                ["systemctl", "list-unit-files", name, "--no-legend"],
                capture_output=True, text=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        # EXACT comparison of the first field: "erplibre.service" is a substring of "erplibre_erplibre.service".
        if result.returncode == 0 and any(l.split()[:1] == [name] for l in result.stdout.splitlines()):
            return name
    return None


def load_profile(force):
    """Profile apps/<name>.conf (detected, or forced by --app / APP_PROFILE); without apps/ folder: Odoo by default."""
    folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), "apps")
    if not os.path.isfile(os.path.join(folder, "_profile.py")):
        return {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "APP_LOG_KIND": "log",
                "APP_DETECTION": "default (apps/ folder missing next to the program)"}
    sys.path.insert(0, folder)
    import _profile
    return _profile.charger_profil_app(folder, force)


# Normalization of a message for grouping: times, dates, numbers, hexadecimal identifiers and UUIDs removed,
# so that the same error repeated with different values forms ONE single group.
_NORMALIZE = [(re.compile(r"^\S*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.,]?\d*\S*\s*"), ""),
               (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
               (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<hex>"), (re.compile(r"\d+"), "<n>")]


def normalize(text_line):
    for rx, repl in _NORMALIZE:
        text_line = rx.sub(repl, text_line)
    return text_line.strip()[:160]


def analyze_files(profile, args):
    """Application journal in FILES (e.g. BBB: /var/log/bigbluebutton/bbb-web.log): ERROR/FATAL and
    WARN lines grouped by normalized message. Incremental follow-up by position (byte + inode) in the state folder;
    --init: the whole active file; --last HOURS: timestamped lines of the last HOURS hours."""
    fichiers = [f for f in profile.get("APP_LOG_FILES", "").split()]
    print("=" * 100)
    print(f" Log analysis — {profile['APP_LABEL']} ({profile['APP_DETECTION']}) — {', '.join(fichiers) or 'no file'}")
    cutoff = None
    if args.last is not None:
        cutoff = datetime.now() - timedelta(hours=args.last)
        print(f" Window: last {args.last}h (--last) — saved position not modified.")
    elif args.init:
        print(" Window: the whole active file (--init).")
    print("=" * 100)
    grouped = {"error": {}, "warning": {}}
    for path in fichiers:
        if not os.path.isfile(path):
            print(TR("WARNING: {path} not found.").format(path=path))
            continue
        state = os.path.join(STATE_DIR, "file-" + re.sub(r"[^A-Za-z0-9._-]", "_", path) + ".pos")
        st = os.stat(path)
        start = 0
        if not args.init and args.last is None and os.path.isfile(state):
            try:
                ino, pos = open(state).read().split()
                if int(ino) == st.st_ino and int(pos) <= st.st_size:
                    start = int(pos)            # same file, not truncated: resume where we stopped
            except (OSError, ValueError):
                pass
        try:
            f = open(path, "rb")
        except OSError as e:
            print(TR("WARNING: {path} unreadable ({e}) — run again as root.").format(path=path, e=e))
            continue
        with f:
            f.seek(start)
            for raw in f:
                text_line = raw.decode("utf-8", "replace").rstrip("\n")
                if cutoff is not None:
                    try:
                        if datetime.fromisoformat(text_line[:19].replace("T", " ")) < cutoff:
                            continue
                    except ValueError:
                        continue
                level = "error" if re.search(r"\b(ERROR|FATAL|SEVERE)\b", text_line) else \
                         "warning" if re.search(r"\bWARN(ING)?\b", text_line) else None
                if level:
                    g = grouped[level].setdefault(normalize(text_line), [0, text_line, text_line])
                    g[0] += 1
                    g[2] = text_line
            end = f.tell()
        if args.last is None:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(state, "w") as e:
                e.write(f"{st.st_ino} {end}\n")
    for level, heading in (("error", "[1] Errors (ERROR / FATAL)"), ("warning", "[2] Warnings (WARN)")):
        g = grouped[level]
        print_section(f"{heading} — {sum(v[0] for v in g.values())} line(s), {len(g)} distinct")
        if not g:
            print("NOTHING")
            continue
        for _, (n, first_seen, last_seen) in sorted(g.items(), key=lambda kv: -kv[1][0])[:15]:
            print(f"  [{n}x] {first_seen[:170]}")
            if n > 1 and last_seen != first_seen:
                print(f"        last: {last_seen[:160]}")
    n_err = sum(v[0] for v in grouped["error"].values())
    print()
    print("=" * 100)
    print(" SUMMARY: " + (f"{n_err} error(s) to examine (section [1])." if n_err else "nothing suspicious in this window."))
    print("=" * 100)
    return 0



class SortedHelp(argparse.HelpFormatter):
    """Help options in ALPHABETICAL ORDER (long name, without dashes: « -h, --help » sorts under « help »),
    in the list as well as in the « usage » line."""
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


JOURNAL_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})([+-]\d{2}:?\d{2}|Z)? (\S+) ([^\s\[:]+)(?:\[(\d+)\])?: (.*)$")
STRUCTURE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ (DEBUG|INFO|WARNING|ERROR|CRITICAL) (\S+) (\S+): (.*)$")
REQUEST_RE = re.compile(r'^(\S+) - - (?:\[[^\]]*\] )?"[A-Z]+ (\S+) HTTP/[\d.]+" (\d{3})\b')
START_RE = re.compile(r"^Started ")
LOGIN_RE = re.compile(r"Login successful for db:(\S+) login:(\S+) from (\S+)")
SESSION_PATTERNS = ("%session%", "%login%", "%concurrent%", "%single%")      # names of modules that could limit sessions


def epoch_iso(day, h, mi, s, tz):
    try:
        return datetime.strptime(f"{day} {h}:{mi}:{s} {tz or '+0000'}", "%Y-%m-%d %H:%M:%S %z").timestamp()
    except ValueError:
        return 0.0


def normalize_page(url):
    """Page without parameters, identifiers (« 9725-35c703c7 », numbers) and fingerprints replaced: similar pages are grouped."""
    chunks = []
    for m in urllib.parse.unquote(url.split("?", 1)[0]).split("/"):
        if re.fullmatch(r"\d+(?:-[0-9a-f]+)?", m):
            m = "{id}"
        elif re.fullmatch(r"[0-9a-f]{16,}", m):
            m = "{hash}"
        chunks.append(m)
    return ("/".join(chunks) or "/")[:120]


def hourly_signature(level, logger, text_value, text_lines):
    """Grouping key of an error or warning: message without timestamp or level, numbers and long tokens (keys, notification
    tokens, fingerprints) neutralized so that occurrences of the same problem are grouped."""
    if level == "WARNING":
        key_value = re.sub(r"\d+", "N", re.sub(r"\b[0-9a-f]{7,}\b", "…", f"{logger}: {text_value}"))[:200]
    else:
        key_value = error_signature(text_lines)
    return re.sub(r"[A-Za-z0-9_\-:]{24,}", "…", key_value)


class HourlyAnalyzer:
    """Counts, per local (day, hour): errors and warnings (grouped as in the usual report), failed HTTP requests
    (400 and above) per page, and « Session expired » per page (attached to the next request of the same process)."""
    def __init__(self):
        self.per_key = {}                  # (category, key) -> Counter{(day, hour): n}
        self.all_items = Counter()              # (day, hour) -> n, all categories
        self.ips_session = Counter()       # address -> « Session expired » attached to a request from this address
        self.sessions = []                 # instant of each « Session expired »
        self.sessions_by_ip = []              # (instant, address) of each « Session expired » attached to a request
        self.logins = []               # (instant, identifier, address) of each successful login
        self.accounts_by_ip = {}               # address -> identifiers logged in from it
        self.databases_seen = Counter()             # database -> « Session expired » (to read the installed modules)
        self.byte_count = 0
        self.starts_list = []               # instants of the service's « Started … » (restarts)
        self.text_lines = 0
        self.ongoing = None               # entry in progress (structured line + continuations)
        self.waiting = {}                  # pid -> (day, hour, instant) of a « Session expired » waiting for its page

    def count_items(self, category, key_value, day, hour):
        self.per_key.setdefault((category, key_value), Counter())[(day, hour)] += 1
        self.all_items[(day, hour)] += 1

    def text_line(self, raw_line):
        self.text_lines += 1
        self.byte_count += len(raw_line) + 1
        m = JOURNAL_ISO_RE.match(raw_line[:LINE_MAX])
        if not m:
            return
        day, h, mi, secs, tz, _, program_name, pid, message = m.groups()
        if program_name == "systemd" and START_RE.match(message):
            self.starts_list.append(epoch_iso(day, h, mi, secs, tz))
        elif STRUCTURE_RE.match(message):
            self.flush_out()
            self.ongoing = {"day": day, "hour": int(h), "pid": pid, "instant": (day, h, mi, secs, tz), "lines": [message]}
        elif self.ongoing is not None:
            self.ongoing["lines"].append(message)

    def flush_out(self):
        e, self.ongoing = self.ongoing, None
        if e is None:
            return
        level, database, logger, text_value = STRUCTURE_RE.match(e["lines"][0]).groups()
        if logger == "werkzeug":
            r = REQUEST_RE.match(text_value)
            if not r:
                return
            ip, page, code = r.group(1), normalize_page(r.group(2)), int(r.group(3))
            waiting = self.waiting.pop(e["pid"], None)
            if waiting:
                self.count_items("session", page, waiting[0], waiting[1])
                self.ips_session[ip] += 1
                self.sessions.append(waiting[2])
                self.sessions_by_ip.append((waiting[2], ip))
            if code >= 400:
                self.count_items("http", f"{code} {page}", e["day"], e["hour"])
        elif logger == "odoo.http" and text_value.startswith("Session expired"):
            self.give_up(e["pid"])
            self.waiting[e["pid"]] = (e["day"], e["hour"], epoch_iso(*e["instant"]))
            self.databases_seen[database] += 1
        elif logger == "odoo.addons.base.models.res_users" and (c := LOGIN_RE.search(text_value)):
            self.logins.append((epoch_iso(*e["instant"]), c.group(2), c.group(3)))
            self.accounts_by_ip.setdefault(c.group(3), set()).add(c.group(2))
        elif level in ("ERROR", "CRITICAL", "WARNING"):
            complete = "\n".join(e["lines"])
            key_value = next((f"{label} (harmless)" for rx, label, _ in KNOWN_BENIGN if rx.search(complete)), None) or hourly_signature(level, logger, text_value, e["lines"])
            self.count_items("warn" if level == "WARNING" else "error", key_value, e["day"], e["hour"])

    def give_up(self, pid):
        """« Session expired » left without a following request: counted without a page."""
        waiting = self.waiting.pop(pid, None)
        if waiting:
            self.count_items("session", "(unknown page)", waiting[0], waiting[1])
            self.sessions.append(waiting[2])

    def end(self):
        self.flush_out()
        for pid in list(self.waiting):
            self.give_up(pid)


def after_start(instants, starts):
    """Number of instants that occurred within the hour following one of the starts (sorted list)."""
    n = 0
    for t in instants:
        i = bisect.bisect_right(starts, t)
        if i and t - starts[i - 1] <= 3600:
            n += 1
    return n


def thousands(n):
    return f"{n:,}".replace(",", " ")


_LISTES = [None]


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
    """Whitelist and places (/etc/default/nginx-tools-*.conf, apps/_listes.py), read once; the « Lists: … » line goes to the error output."""
    if _LISTES[0] is None:
        path = os.path.join(SCRIPT_DIR, "apps", "_listes.py")
        try:
            spec = importlib.util.spec_from_file_location("_listes", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _LISTES[0] = module.charger(os.path.join(SCRIPT_DIR, "apps"))
        except (OSError, AttributeError, ImportError):
            _LISTES[0] = EmptyLists()
        print(_LISTES[0].resume(), file=sys.stderr)
        for problem in _LISTES[0].problemes:
            print(TR("  WARNING {problem}").format(problem=problem), file=sys.stderr)
    return _LISTES[0]


def ip_label(ip):
    """Short label of the address (whitelist, otherwise place: « Étienne (cell phone…) », « Example University »), or ''."""
    caption = re.sub(r"\s+—\s+[^)]*(?=\))", "", lists().etiquette(ip).strip())
    return re.sub(r"\s+—\s+.*$", "", caption)


team_label = ip_label          # old name


def peaks(counter, n=3):
    """« 19 h (5 600), 20 h (67) »: the busiest hours of a counter {(day, hour): n}."""
    per_hour = Counter()
    for (_, hour), k in counter.items():
        per_hour[hour] += k
    return ", ".join(f"{h:02d} h ({thousands(k)})" for h, k in sorted(per_hour.items(), key=lambda x: (-x[1], x[0]))[:n])


def per_day(counter, n=6):
    per = Counter()
    for (day, _), k in counter.items():
        per[day] += k
    day_count = sorted(per)[-n:]
    return " · ".join(f"{j[5:]} {thousands(per[j])}" for j in day_count) + (" …" if len(per) > n else "")


def hour_ranges(hour_values):
    """[0, 1, 2, 4, 5] -> « 00 h–02 h, 04 h–05 h »."""
    res, start, prev = [], None, None
    for h in list(hour_values) + [None]:
        if start is None:
            start = prev = h
        elif h is not None and h == prev + 1:
            prev = h
        else:
            res.append(f"{start:02d} h" if start == prev else f"{start:02d} h–{prev:02d} h")
            start = prev = h
    return ", ".join(res)


def hours_table(counter, columns=14):
    """Hour (rows) × day (columns) table of problems — only the hours where there are some — with totals and a bar per hour;
    colors in a terminal."""
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    day_count = sorted({j for j, _ in counter})
    displayed = day_count[-columns:]
    maximum = max(counter.values(), default=1)
    totals = [sum(counter.get((j, h), 0) for j in day_count) for h in range(24)]
    max_hours = max(totals) or 1
    text_lines = ["  Hour  |" + "".join(f"{j[5:]:>7}" for j in displayed) + " |   Total"]
    for h in range(24):
        if not totals[h]:
            continue
        cells = ""
        for j in displayed:
            n = counter.get((j, h), 0)
            c = f"{n if n else '.':>7}"
            if color and n:
                c = f"\x1b[{'1;31' if n >= 0.75 * maximum else '33' if n >= 0.25 * maximum else '0'}m{c}\x1b[0m"
            cells += c
        text_lines.append(f"  {h:02d} h  |{cells} |{totals[h]:>8}  " + "█" * max(1, round(20 * totals[h] / max_hours)))
    days_total = [sum(counter.get((j, h), 0) for h in range(24)) for j in displayed]
    text_lines.append("  Total |" + "".join(f"{t:>7}" for t in days_total) + f" |{sum(totals):>8}")
    text_lines.append(f"  Hours without problems: {hour_ranges([h for h in range(24) if not totals[h]]) or 'none'}")
    if len(day_count) > columns:
        text_lines.append(f"  ({columns} last days shown out of {len(day_count)} ; the Total column covers the {len(day_count)} days)")
    return text_lines


def show_hourly_report(a, service, day_count, top):
    print(f"REPORT OF PROBLEMS BY HOUR AND BY DAY — {service} — {day_count} last days — local time of the machine")
    print("=" * 100)
    if not a.all_items:
        print(" No problem in the window (no error, warning, error page or « Session expired »).")
        return
    print(" Count: errors (ERROR, CRITICAL), warnings (WARNING), error pages (HTTP 400 and above), « Session expired ».")
    redundant = 2 * len(a.sessions)                    # each « Session expired » comes with its request line
    print(f" Log: {thousands(a.text_lines)} lines (≈ {a.byte_count / 1e6:.0f} MB) over {day_count} days; « Session expired » and their requests: "
          f"≈ {thousands(redundant)} lines ({100 * redundant / max(a.text_lines, 1):.0f} %).")
    print()
    print("--- [1] All problems, by hour (rows) and by day (columns) ---")
    for text_line in hours_table(a.all_items):
        print(text_line)
    per_hour = Counter()
    per_day_short = Counter()
    for (j, h), k in a.all_items.items():
        per_hour[h] += k
        per_day_short[j] += k
    print(f"\n Busiest hours: {peaks(a.all_items, 5)}")
    print(" Busiest days : " + ", ".join(f"{j} ({thousands(k)})" for j, k in per_day_short.most_common(3)))
    # --- pages
    pages = [(sum(c.values()), cat, key_value, c) for (cat, key_value), c in a.per_key.items() if cat in ("http", "session")]
    print()
    print(f"--- [2] Error pages (HTTP 400 and above, « Session expired »: page requested) — the {top} first ---")
    if not pages:
        print("  no page")
    for total, cat, key_value, c in sorted(pages, key=lambda x: (-x[0], x[2]))[:top]:
        kind_name = "Session expired" if cat == "session" else f"HTTP {key_value.split(' ', 1)[0]}"
        page = key_value if cat == "session" else key_value.split(" ", 1)[1]
        print(f"  {thousands(total):>7}  {kind_name:<15} {page}")
        print(f"           per day: {per_day(c)}   |   peaks: {peaks(c)}")
    # --- messages
    messages = [(sum(c.values()), cat, key_value, c) for (cat, key_value), c in a.per_key.items() if cat in ("error", "warn")]
    print()
    print(f"--- [3] Error and warning messages — the {top} first ones ---")
    if not messages:
        print("  no message")
    for total, cat, key_value, c in sorted(messages, key=lambda x: (-x[0], x[2]))[:top]:
        print(f"  {thousands(total):>7}  {'ERR.' if cat == 'error' else 'WARN.':<7} {key_value[:150]}")
        print(f"           per day: {per_day(c)}   |   peaks: {peaks(c)}")
    # --- diagnosis of « Session expired »
    total_s = len(a.sessions)
    if total_s >= 20:
        session_diagnostics(a, total_s)


def bursts(events, gap=600):
    """[(address, start, end, count)]: series of events (instant, address) from the same address spaced by less than GAP seconds."""
    per_ip = {}
    for t, ip in sorted(events):
        per_ip.setdefault(ip, []).append(t)
    res = []
    for ip, instants in per_ip.items():
        start = prev = instants[0]
        n = 1
        for t in instants[1:]:
            if t - prev > gap:
                res.append((ip, start, prev, n))
                start, n = t, 0
            prev, n = t, n + 1
        res.append((ip, start, prev, n))
    return sorted(res, key=lambda r: r[1])


def bursts_after_login(a, delay=300):
    """(bursts, triggered, examples): a burst is « triggered » if the same account logged in from ANOTHER address within the
    DELAY seconds preceding it (a sign that a login on one workstation invalidates the other's session)."""
    items = bursts(a.sessions_by_ip)
    triggered, examples = 0, []
    for ip, start, _, n in items:
        accounts = a.accounts_by_ip.get(ip, set())
        hit = next(((t, login, ip2) for t, login, ip2 in a.logins if ip2 != ip and login in accounts and 0 <= start - t <= delay), None)
        if hit:
            triggered += 1
            if len(examples) < 3:
                f = lambda x: time.strftime("%m-%d %H:%M", time.localtime(x))
                examples.append(f"{f(start)}  {ip} ({thousands(n)} event(s)) ← {hit[1]} signed in from {hit[2]} (at {time.strftime('%H:%M', time.localtime(hit[0]))})")
    return len(items), triggered, examples


def session_modules(database):
    """Installed modules whose name suggests sessions or login (apps/_odoo_db.py, read-only); None if unreadable."""
    module = load_odoo_db()
    return None if module is None else module.modules_installes(database, SESSION_PATTERNS)


def session_diagnostics(a, total_s):
    print()
    print(f"--- [4] « Session expired »: {thousands(total_s)} times — who, and why ---")
    sess_entry = Counter()
    for (cat, _), c in a.per_key.items():
        if cat == "session":
            sess_entry.update(c)
    print(f"  Peak hours: {peaks(sess_entry)}")
    with_ip = sum(a.ips_session.values()) or 1
    print("  Addresses (clients):")
    for ip, n in a.ips_session.most_common(5):
        lib = team_label(ip)
        accounts_by_ip = ", ".join(sorted(a.accounts_by_ip.get(ip, ())))
        print(f"    {ip:<18} {thousands(n):>7}  ({100 * n / with_ip:.0f} %)" + (f"  {lib}" if lib else "") + (f"  [account: {accounts_by_ip}]" if accounts_by_ip else ""))
    ip_max, n_max = a.ips_session.most_common(1)[0] if a.ips_session else ("?", 0)
    part = n_max / with_ip
    # accounts behind the addresses that make up 95% of the events
    cumulative, main_ones = 0, []
    for ip, n in a.ips_session.most_common():
        main_ones.append(ip)
        cumulative += n
        if cumulative >= 0.95 * with_ip:
            break
    accounts = set().union(*(a.accounts_by_ip.get(ip, set()) for ip in main_ones)) if main_ones else set()
    starts = sorted(a.starts_list)
    after = after_start(a.sessions, starts)
    print(f"  Service restarts in the period: {len(starts)}"
          + (f" ; {100 * after / total_s:.0f} % of the « Session expired » happen within the hour following one of them." if starts else "."))
    bursts_count, triggered, examples = bursts_after_login(a)
    if bursts_count:
        print(f"  Bursts (series less than 10 min apart): {bursts_count} ; {triggered} start less than 5 min after a login of the same "
              "account from another address.")
        for e in examples:
            print(f"    {e}")
    database = a.databases_seen.most_common(1)[0][0] if a.databases_seen else ""
    modules = session_modules(database) if database else None
    if modules is None:
        print("  Installed modules suggesting sessions or sign-in: unreadable (PostgreSQL unreachable, or root required).")
    elif not modules:
        print("  Installed modules whose name suggests a session limit: none (Odoo CE normally allows several simultaneous sessions for the same account).")
    else:
        print("  Installed modules whose name suggests sessions or sign-in: " + ", ".join(modules) + " — to examine: a module may limit sessions per account.")
    correlation = ""
    if bursts_count >= 2 and triggered / bursts_count >= 0.5:
        correlation = (f" {triggered} burst(s) out of {bursts_count} start right after a login of the same account from another address: logging in "
                       "on one workstation seems to INVALIDATE the other's session (a single session per account). Odoo CE does not impose this: see the modules "
                       "above, then the security settings (Preferences ▸ Security ▸ Devices).")
    elif bursts_count >= 2:
        correlation = " The bursts do not follow a sign-in from another address: this is not a single session per account."
    place_max = lists().lieu(ip_max)
    if part >= 0.8 and place_max is not None and place_max.partagee:
        verdict = (f"SHARED ADDRESS ({ip_max} — {place_max.libelle}, {100 * part:.0f} %). Several people are behind this address: it is not "
                   "necessarily a single tab. Look among them for the person(s) whose session became invalid (logout in another "
                   "tab, password changed, database restored) and ask them to reload (Ctrl+F5) or to sign in again." + correlation)
    elif part >= 0.8:
        lib = ip_label(ip_max)
        verdict = (f"A SINGLE CLIENT ({ip_max}{' — ' + lib if lib else ''}, {100 * part:.0f} %). A tab or application left open "
                   "with a session that became invalid (logout in another tab, session expired or deleted, password changed, database "
                   "restored) keeps requesting pages the server refuses. This is NOT a server defect: closing or reloading "
                   "(Ctrl+F5) the Odoo tabs open from this address, or signing in again, stops the flood." + correlation)
    elif len(main_ones) >= 2 and len(accounts) == 1:
        verdict = (f"A SINGLE ACCOUNT ({next(iter(accounts))}) out of {len(main_ones)} addresses ({', '.join(main_ones)}): its different workstations. A tab left "
                   "open on one workstation, with a session that became invalid, keeps requesting pages the server refuses." + correlation)
    elif starts and after / total_s >= 0.5:
        verdict = ("SEVERAL CLIENTS, especially right after a restart: sessions do not survive a restart. Check that the sessions folder (data_dir/sessions) is kept between two starts and is writable by the service user.")
    else:
        verdict = ("SEVERAL CLIENTS, unrelated to a restart: sessions lost on the server side. Check for a database change (restore, dbfilter), a password changed for several accounts, and cookies (www or not, HTTP or HTTPS); compare the peaks above with these events." + correlation)
    print(textwrap.fill(TR(verdict), width=110, initial_indent="  VERDICT: ", subsequent_indent="     "))


def hourly_report(service, namespace, day_count, top):
    """--by-hour: reads the journal of the last DAYS days (without touching the remembered position) and displays the report. Exit code."""
    cmd = ["journalctl", "-u", service, "-o", "short-iso", "--no-pager", "--since", f"-{day_count} days"] + (["--namespace", namespace] if namespace else [])
    vcmd(cmd)
    eprint(f"Reading the log of {service} ({day_count} days): several minutes if the log is large…")
    start, a = time.time(), HourlyAnalyzer()
    with tempfile.TemporaryFile("w+") as stderr_file:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr_file, text=True, errors="replace")
        except OSError:
            eprint("ERROR: 'journalctl' command not found on this system.")
            return 1
        try:
            for raw_line in proc.stdout:
                a.text_line(raw_line.rstrip("\n"))
                if a.text_lines % 500000 == 0:
                    eprint(f"  … {thousands(a.text_lines)} lines read ({time.time() - start:.0f} s)")
        finally:
            proc.stdout.close()
            proc.wait()
        if proc.returncode != 0 and not a.text_lines:
            stderr_file.seek(0)
            eprint(f"ERROR: journalctl returned code {proc.returncode} : {stderr_file.read().strip()[:300]}")
            return 1
    a.end()
    eprint(f"  {thousands(a.text_lines)} lines read in {time.time() - start:.0f} s.")
    show_hourly_report(a, service, day_count, top)
    return 0


def main():
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="Analyzes Odoo's systemd log for protocol attacks and Python tracebacks.",
        add_help=True,
    )
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/app-log-check.conf, then the personal file .app-log-check.cfg; options in UPPERCASE: APP, DAYS, ERRORS_ONLY, FULL_TRACE, LANGUAGE, NAMESPACE, SERVICE, TOP, VERBOSE)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--service", default=None,
                         help=f"Systemd unit to query (default: auto-detection among {', '.join(CANDIDATE_SERVICES)})")
    parser.add_argument("--namespace", default=None,
                         help="Journal namespace to query (e.g. 'odoo' if the service was isolated via LogNamespace=). Without this option: default namespace (behavior from before any isolation).")
    parser.add_argument("--by-hour", action="store_true",
                        help="Report of problems BY HOUR AND BY DAY (errors, error pages, « Session expired » and their peaks) over the last --days days; neither uses nor modifies the saved position")
    parser.add_argument("--days", type=int, default=7, metavar="N", help="With --by-hour: days analyzed (default: 7)")
    parser.add_argument("--top", type=int, default=15, metavar="N", help="With --by-hour: pages and messages shown (default: 15)")
    parser.add_argument("--init", action="store_true", help="Analyze the whole available history of the log")
    parser.add_argument("--last", type=int, metavar="HOURS", help="Restrict to the last HOURS hours")
    parser.add_argument("--errors-only", action="store_true",
                        help="Only the DETAIL of the errors: Python tracebacks [2], other errors [3] and diagnostics [5] (no protocol attacks, no known noise, no summary)")
    parser.add_argument("--full-trace", action="store_true", help="Show the full traceback for each group (not just an example)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show each external command run (journalctl, systemctl)")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--version", action="version", version=f"app-log-check.py version {__version__}")
    parser.add_argument("--changelog", action="store_true", help="Show the changelog")
    parser.add_argument("--app", metavar="NAME",
                        help="Application behind nginx (profile apps/NAME.conf: odoo, bbb…) — detected automatically by default")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version displays it itself)
        print(f"app-log-check.py v{__version__}")
    defauts, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defauts, problems)
    global VERBOSE
    VERBOSE = args.verbose
    if not args.changelog:
        try:
            spec = importlib.util.spec_from_file_location("_config", os.path.join(SCRIPT_DIR, "apps", "_config.py"))
            _cfg_root = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_cfg_root)
            notice = _cfg_root.avis_non_root("app-log-check.py", "PostgreSQL (modules, users), fail2ban and some logs unreadable")
            if notice:
                eprint(notice)
        except (ImportError, OSError, AttributeError):
            pass

    if args.changelog:
        show_changelog()
        return

    try:
        profile = load_profile(args.app)
    except Exception as e:            # ProfileError (message in French)
        eprint(TR("ERROR: {message}").format(message=e))
        sys.exit(2)
    if args.by_hour and not 1 <= args.days <= 3650:
        parser.error("--days must be between 1 and 3650")
    if profile.get("APP_LOG_KIND") == "file":
        if args.by_hour:
            eprint("--by-hour: available for Odoo's journal (systemd). For nginx: nginx-log-audit.sh --stats (traffic per day).")
            sys.exit(2)
        sys.exit(analyze_files(profile, args))

    service = args.service
    if service is None:
        service = detect_service()
        if service is None:
            eprint(f"WARNING: no unit among {', '.join(CANDIDATE_SERVICES)} found by 'systemctl "
                    f"list-unit-files' — using the default '{DEFAULT_SERVICE}'. Specify --service NAME if "
                    f"it is not the right one.")
            service = DEFAULT_SERVICE

    if args.by_hour:
        sys.exit(hourly_report(service, args.namespace, args.days, args.top))

    print("=" * 100)
    print(f" Log analysis — service: {service}" + (" (auto-detected)" if args.service is None else ""))
    if args.namespace:
        print(f" Namespace: {args.namespace}")

    now_marker = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    if args.last is not None:
        since = f"{args.last} hours ago"
        print(f" Window: last {args.last}h (--last) — saved position not modified.")
    elif args.init:
        since = None
        print(" Window: the whole history available in the journal (--init).")
    else:
        last_run = read_last_run(service, args.namespace)
        since = last_run if last_run else None
        if last_run:
            print(f" Window: since the last run ({last_run}).")
        else:
            print(" Window: no previous run found — analyzing the whole available history.")
            print(" (the next calls, without --init/--last, will become incremental from now on)")

    print("=" * 100)

    lines = run_journalctl(service, since=since, namespace=args.namespace)
    entries = parse_entries(lines)

    if args.last is None:
        write_last_run(service, now_marker, args.namespace)

    if not entries:
        print()
        print("No entry found in this window.")
        return

    protocol_issues, traceback_groups, other_errors, benign = analyze(entries)
    diag = diagnose(entries)
    if not args.errors_only:
        show_summary(protocol_issues, traceback_groups, other_errors, benign, diag)

    if not args.errors_only:
        print_section(f"[1] Protocol attacks / anomalies detected ({len(protocol_issues)})")
        if not protocol_issues:
            print("NOTHING")
        else:
            print("These are connections that did NOT EVEN reach nginx properly formed — often a direct connection")
            print("to Odoo's gevent/longpolling port, bypassing nginx. See also nginx-hardening.sh")
            print("to check that this port is indeed blocked from the outside.")
            by_ip = OrderedDict()
            for kind, ip, port, entry in protocol_issues:
                by_ip.setdefault(ip, []).append(kind)
            for ip, kinds in sorted(by_ip.items(), key=lambda kv: -len(kv[1])):
                print(f"  {len(kinds):4d}  {BAD}{ip:20s}{END_BAD}  {', '.join(sorted(set(kinds)))}")

    print_section(f"[2] Python tracebacks — {sum(g['count'] for g in traceback_groups.values())} occurrence(s), {len(traceback_groups)} distinct")
    if not traceback_groups:
        print("NOTHING")
    else:
        print("Grouped by final message (the most specific exception) — a recurring bug appears only once")
        print("here, with its count, rather than drowned in as many identical blocks as occurrences.")
        for headline, info in sorted(traceback_groups.items(), key=lambda kv: -kv[1]["count"]):
            print()
            print(f"  [{info['count']}x] {headline}")
            print(f"      Triggered by: {abbreviate(info['example'][0].strip())}")
            if args.full_trace:
                print("      Full traceback:")
                for l in info["example"][1:]:
                    print(f"        {abbreviate(l)}")
            else:
                print("      (run again with --full-trace for the full traceback of each group)")

    n_other = sum(g["count"] for g in other_errors.values())
    print_section(f"[3] Other uncategorized errors (ERROR/CRITICAL) — {n_other} occurrence(s), "
                  f"{len(other_errors)} distinct")
    if not other_errors:
        print("NOTHING")
    else:
        for sig, g in sorted(other_errors.items(), key=lambda kv: -kv[1]["count"]):
            print(f"  [{g['count']}x] {sig}")
            if g["count"] > 1:
                print(f"      First: {g['first']} — last: {g['last']}")
            example = abbreviate(g["example"][0].strip())
            if args.full_trace:
                print("      Full example:")
                for line in g["example"]:
                    print(f"        {abbreviate(line.rstrip())}")
            else:
                print(f"      Example: {example[:180]}{'…' if len(example) > 180 else ''}")
        if not args.full_trace:
            print("      (run again with --full-trace for the full entry of each group)")

    if not args.errors_only:
        n_benign = sum(b["count"] for b in benign.values())
        print_section(f"[4] Known noise, harmless ({n_benign})")
        if not benign:
            print("NOTHING")
        else:
            for label, info in sorted(benign.items(), key=lambda kv: -kv[1]["count"]):
                print(f"  [{info['count']}x] {label}")
                print(f"      Example: {info['example'][0].strip()}")
                print(textwrap.fill(TR(info["explanation"]), width=110, initial_indent="      ", subsequent_indent="      "))
                for (database, operation, uid, model), n in sorted((info.get("details") or {}).items(), key=lambda kv: -kv[1])[:10]:
                    who = login_odoo(database, uid)
                    print(f"      {n:5d}x  " + TR("{operation} on {model}").format(operation=operation, model=model) + f" — user uid {uid}"
                          + (f" : {who}" if who else f" (form: /web#id={uid}&model=res.users&view_type=form)")
                          + f" — database {database}")

    if diag:
        show_diagnostics(diag)

    print()
    if args.errors_only:
        return
    print("=" * 100)
    n_issues = len(protocol_issues) + sum(g["count"] for g in traceback_groups.values()) + n_other
    if n_issues == 0:
        print("SUMMARY: nothing suspicious in this window." + (f" ({n_benign} message(s) of known noise, see [4].)" if n_benign else ""))
    else:
        print(f"SUMMARY: {n_issues} entry(ies) to examine ({len(protocol_issues)} protocol, "
              f"{sum(g['count'] for g in traceback_groups.values())} Python trace(s), {n_other} other(s))"
              + (f" — plus {n_benign} message(s) of known harmless noise (see [4])." if n_benign else ".")
              + (" Causes and solutions: section [5]." if diag else ""))
    print("=" * 100)


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


def protected_main():
    """main() with Ctrl-C cleanly interrupted (code 130, no call trace)."""
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl-C).", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(launch_with_report(protected_main))
