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
# sqli-investigate.py - READ-ONLY investigation of the SQL injection attempts in the nginx access logs.
#   * Reads the access logs (current and rotated files, .gz included), the fail2ban log (bans of one jail) and, with --odoo-log,
#     the Odoo log. Finds every request whose DECODED URL matches an attack family: union (UNION SELECT), error (EXTRACTVALUE,
#     UPDATEXML, CONCAT(0x7e...), elt), order-by (ORDER BY n), boolean (' AND 1=1, ') AND ('...), time (SLEEP, BENCHMARK), schema
#     (information_schema, LOAD_FILE, INTO OUTFILE).
#   * Writes, only in --output (mode 600, folder 700): sqli-requests.tsv (every attempt), sqli-summary.txt (addresses, families,
#     answers, user agents, Odoo errors near the attempts) and sqli-bans.txt (bans of the jail, the state given by fail2ban-client,
#     and the answers the banned addresses still got after each ban).
#   * Never bans, unbans, restarts a service or changes a configuration. A 2xx answer is NOT a proof of absence of injection:
#     only the PostgreSQL side (queries) can show that.
# Configuration (common rule): /etc/default/sqli-investigate.conf THEN ~/.sqli-investigate.conf (the last one wins; keys ACCESS_LOG,
# FAIL2BAN_LOG, JAIL, NO_LOOKUP, ODOO_LOG, OUTPUT, TOP, LANGUAGE); -c/--config: that file ALONE; the command line takes priority.
#
#
# Usage:
#   sqli-investigate.py                              investigation with the default paths (needs read access to /var/log)
#   sqli-investigate.py --odoo-log FILE              also counts the Odoo errors within 60 s of each attempt
#   sqli-investigate.py --jail nginx-sqli --top 10   jail to examine, ten addresses in the summary
#   sqli-investigate.py --no-lookup                  no reverse DNS lookup of the addresses
#   sqli-investigate.py --output DIR                 folder of the results (default: /var/lib/sqli-investigate/YYYYMMDD-HHMMSS)
#   --access-log GLOB, --fail2ban-log GLOB, --lang en|fr, --verbose, --report-err, --version, --changelog, --config-merge

import argparse
import collections
import datetime as dt
import glob
import gzip
import importlib.util
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import urllib.parse

__version__ = "0.3.20261127.090500"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
SYSTEM_CONF = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), SCRIPT_NAME + ".conf")      # variable: tests only
USER_CONF = "~/." + SCRIPT_NAME + ".conf"
DEFAULT_ACCESS_LOG = "/var/log/nginx/*-access.log*"
DEFAULT_FAIL2BAN_LOG = "/var/log/fail2ban.log*"
DEFAULT_JAIL = "nginx-sqli"
DEFAULT_TOP = 20
ODOO_WINDOW_S = 60
VERBOSE = False


def _start():
    """Common context (apps/_i18n.py: language, translated print / input, parser); module absent: source language (English)."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "SQLI_INVESTIGATE_LANG", ("_config", "_rapport"))
    except Exception:
        return None


I18N = _start()
LANGUAGE = I18N.langue if I18N else "en"
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 - every displayed text goes through the translator


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


def load_module(name):
    """Component of apps/ (None if absent)."""
    path = os.path.join(SCRIPT_DIR, "apps", name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Attack families, searched in the DECODED URL (%20 and + become spaces, %27 becomes a quote).
FAMILIES = [
    ("union", re.compile(r"union(?:\s|/\*.*?\*/)+(?:all(?:\s)+)?select", re.I | re.S)),
    ("error", re.compile(r"\b(?:extractvalue|updatexml)\s*\(|\bconcat\s*\(\s*0x|\belt\s*\(\s*\d+\s*=", re.I)),
    ("order-by", re.compile(r"order\s+by\s+\d+", re.I)),
    ("boolean", re.compile(r"['\")]\s*(?:and|or)\s|\b(?:and|or)\s+\(?\s*\d+\s*=\s*\d+|\b(?:and|or)\s*\(\s*'[^']*'\s*=", re.I)),
    ("time", re.compile(r"\b(?:sleep|benchmark|pg_sleep)\s*\(", re.I)),
    ("schema", re.compile(r"information_schema|load_file\s*\(|into\s+(?:out|dump)file", re.I)),
]

# Combined nginx format: ip - user [time] "method url protocol" status bytes ["referer" "user agent"]
ACCESS_RE = re.compile(r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>[A-Z]+) (?P<url>\S*)[^"]*" '
                       r'(?P<status>\d{3}) (?P<size>\S+)(?: "(?P<ref>[^"]*)" "(?P<ua>[^"]*)")?')
NGINX_TIME = "%d/%b/%Y:%H:%M:%S %z"
F2B_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.]\d+\s.*?\[([^\]]+)\]\s+(Ban|Unban)\s+(\S+)")
LOCAL_TIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})")
ODOO_ERROR_RE = re.compile(r"\b(?:ERROR|CRITICAL)\b|Traceback \(most recent call last\)|psycopg2|syntax error at or near", re.I)
TRUE_WORDS = ("1", "true", "yes", "oui", "on", "vrai")


def yes_no(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in TRUE_WORDS


def read_config(explicite=None):
    """(values, files read): /etc/default/sqli-investigate.conf then ~/.sqli-investigate.conf (the last one wins); explicit (-c/--config):
    that file ALONE, which must exist (FileNotFoundError otherwise). Keys: ACCESS_LOG, FAIL2BAN_LOG, JAIL, NO_LOOKUP, ODOO_LOG, OUTPUT, TOP, LANGUAGE."""
    values, files_read = {}, []
    if explicite and not os.path.isfile(explicite):
        raise FileNotFoundError(f"configuration file not found: {explicite}")
    if not explicite:                                          # first start: the default file is created (every option in a comment)
        try:
            load_module("_config").creer_par_defaut(SCRIPT_NAME)
        except Exception:
            pass
    for path in ([explicite] if explicite else [SYSTEM_CONF, os.path.expanduser(USER_CONF)]):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        files_read.append(path)
        for line in lines:
            line = line.split("#", 1)[0].strip()
            m = re.fullmatch(r"([A-Z_]+)\s*=\s*[\"']?(.*?)[\"']?", line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            if key == "TOP" and value.isdigit():
                values["TOP"] = int(value)
            elif key in ("ACCESS_LOG", "FAIL2BAN_LOG", "JAIL", "ODOO_LOG", "OUTPUT", "LANGUAGE") and value:
                values[key] = value
            elif key == "NO_LOOKUP":
                values["NO_LOOKUP"] = yes_no(value)
    return values, files_read


def shell_safe(text):
    return re.sub(r"[\x00-\x1f\x7f]", " ", text)


def expand(pattern):
    return sorted(f for f in glob.glob(pattern) if os.path.isfile(f))


def open_log(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def parse_nginx_time(text):
    try:
        return dt.datetime.strptime(text, NGINX_TIME)
    except ValueError:
        return None


def parse_local_time(text):
    """Fail2ban and Odoo times: naive, in the local time of the server."""
    m = LOCAL_TIME_RE.match(text)
    if not m:
        return None
    return dt.datetime(*[int(x) for x in m.groups()]).astimezone()


def fmt(when):
    return when.strftime("%Y-%m-%d %H:%M:%S") if when else "?"


def read_bans(pattern, jail, warnings):
    events = []
    files = expand(pattern)
    if not files:
        warnings.append(f"no fail2ban log: {pattern}")
    for path in files:
        try:
            with open_log(path) as fh:
                for line in fh:
                    m = F2B_RE.match(line)
                    if m and m.group(2) == jail:
                        when = parse_local_time(m.group(1))
                        if when:
                            events.append((when, m.group(3), m.group(4)))
        except OSError as err:
            warnings.append(f"{path}: {err.strerror}")
    events.sort(key=lambda e: e[0])
    return events


def scan_access(pattern, watched, warnings):
    """One pass over the access logs: the attempts (families found), and the answers given to the watched (banned) addresses."""
    attempts, answers = [], collections.defaultdict(list)
    files = expand(pattern)
    if not files:
        warnings.append(f"no nginx access log: {pattern}")
    for path in files:
        try:
            fh = open_log(path)
        except OSError as err:
            warnings.append(f"{path}: {err.strerror}")
            continue
        with fh:
            for line in fh:
                m = ACCESS_RE.match(line)
                if not m:
                    continue
                when = parse_nginx_time(m.group("ts"))
                if when is None:
                    continue
                ip, status = m.group("ip"), int(m.group("status"))
                if ip in watched:
                    answers[ip].append((when, status))
                text = urllib.parse.unquote_plus(m.group("url"))
                families = [name for name, rx in FAMILIES if rx.search(text)]
                if families:
                    attempts.append({"time": when, "ip": ip, "method": m.group("method"), "status": status, "size": m.group("size"),
                                     "families": families, "referer": m.group("ref") or "-", "agent": m.group("ua") or "-",
                                     "url": text[:600], "file": os.path.basename(path)})
    attempts.sort(key=lambda a: a["time"])
    return attempts, answers


def read_odoo_errors(path, warnings):
    errors = []
    try:
        with open_log(path) as fh:
            for line in fh:
                if ODOO_ERROR_RE.search(line):
                    when = parse_local_time(line)
                    if when:
                        errors.append(when)
    except OSError as err:
        warnings.append(f"{path}: {err.strerror}")
    return errors


def reverse_name(ip, cache):
    if ip not in cache:
        try:
            cache[ip] = socket.gethostbyaddr(ip)[0]
        except (OSError, UnicodeError):
            cache[ip] = ""
    return cache[ip]


def fail2ban_state(jail, warnings):
    if shutil.which("fail2ban-client") is None:
        warnings.append("fail2ban-client not found: the jail state was not read")
        return ""
    try:
        done = subprocess.run(["fail2ban-client", "status", jail], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as err:
        warnings.append(f"fail2ban-client: {err}")
        return ""
    return (done.stdout or done.stderr or "").strip()


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def ban_windows(events):
    """Effective ban periods from the (time, action, address) events: (start, address, end) where end is the matching Unban, or None
    while the address is still banned. A repeated Ban while already banned does not start a new period."""
    open_bans, windows = {}, []
    for when, act, ip in sorted(events, key=lambda e: e[0]):
        if act == "Ban" and ip not in open_bans:
            open_bans[ip] = when
        elif act == "Unban" and ip in open_bans:
            windows.append((open_bans.pop(ip), ip, when))
    windows += [(start, ip, None) for ip, start in open_bans.items()]
    return sorted(windows, key=lambda w: w[0])


def build_summary(attempts, answers, windows, banned_now, names, odoo_errors, top, color):
    """Summary lines. color: function (code, text) -> text (identity when the output is not a terminal)."""
    lines = []
    if not attempts:
        lines.append("No SQL injection attempt found in the logs read.")
    else:
        lines.append(color("1;33", "Investigation summary (%s)" % SCRIPT_NAME))
        lines.append("Attempts: %d, from %s to %s" % (len(attempts), fmt(attempts[0]["time"]), fmt(attempts[-1]["time"])))
        fams = collections.Counter(f for a in attempts for f in a["families"])
        lines.append("Families: " + ", ".join("%s %d" % (k, v) for k, v in fams.most_common()))
        codes = collections.Counter(a["status"] for a in attempts)
        lines.append("Answers (HTTP code): " + ", ".join("%d ×%d" % (k, v) for k, v in sorted(codes.items())))
        ok = sum(1 for a in attempts if 200 <= a["status"] < 300)
        lines.append("Attempts answered with 2xx: %d (a 200 answer does not prove the absence of injection: see the SQL requests)" % ok)
        if odoo_errors is not None:
            near = sum(1 for a in attempts if any(abs((e - a["time"]).total_seconds()) <= ODOO_WINDOW_S for e in odoo_errors))
            lines.append("Attempts with an Odoo error within ±%d s: %d" % (ODOO_WINDOW_S, near))
        lines.append("")
        lines.append(color("1;33", "Most active addresses (top %d)" % top))
        per_ip = collections.defaultdict(list)
        for a in attempts:
            per_ip[a["ip"]].append(a)
        for ip, items in sorted(per_ip.items(), key=lambda kv: -len(kv[1]))[:top]:
            agents = collections.Counter(a["agent"] for a in items)
            families = sorted({f for a in items for f in a["families"]})
            tag = " [banned now]" if banned_now.get(ip) else ""
            lines.append("  %s%s %s" % (color("1;36", ip), tag, names.get(ip, "")))
            lines.append("    %d attempts, from %s to %s · families: %s"
                         % (len(items), fmt(items[0]["time"]), fmt(items[-1]["time"]), ", ".join(families)))
            lines.append("    answers: " + ", ".join("%d ×%d" % (k, v) for k, v in sorted(collections.Counter(a["status"] for a in items).items())))
            lines.append("    agents: " + " | ".join("%s ×%d" % (k[:70], v) for k, v in agents.most_common(3)))
    lines.append("")
    lines.append(color("1;33", "Jail bans (or none)"))
    if not windows:
        lines.append("  No ban read in the fail2ban log.")
    for start, ip, end in windows:
        during = [s for ts, s in answers.get(ip, []) if ts >= start and (end is None or ts < end)]
        ok_during = sum(1 for s in during if 200 <= s < 300)
        lines.append("  %s banned at %s: %d request(s) during the ban, %d with 2xx; ban ended: %s"
                     % (ip, fmt(start), len(during), ok_during, fmt(end) if end else "still active"))
    return lines


def show_changelog():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        with open(CHANGELOG_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        eprint(f"Changelog not found: {CHANGELOG_FILE}")
        return 1
    section, inside = [], False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == SCRIPT_NAME + ".py"
            if inside:
                section.append(line)
        elif inside:
            section.append(line)
    text = "\n".join(section) + "\n" if section else f"No entry for {SCRIPT_NAME}.py in {CHANGELOG_FILE}\n"
    if sys.stdout.isatty():
        text = re.sub(r"(\d+\.\d+\.\d{8}\.\d{6})", "\x1b[1;36m\\1\x1b[0m", text)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


class SortedHelp(argparse.HelpFormatter):
    """Help options in ALPHABETICAL ORDER (long name, without the dashes)."""
    @staticmethod
    def _key(action):
        names = action.option_strings or [action.dest]
        return names[-1].lstrip("-").lower()

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions if groups else sorted(actions, key=self._key), groups, prefix)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._key))


class LocalizedArgumentParser(argparse.ArgumentParser):
    """Fallback parser (apps/_i18n.py missing): options in alphabetical order."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", SortedHelp)
        super().__init__(*args, **kwargs)


def main():
    global VERBOSE
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="READ-ONLY investigation of the SQL injection attempts in the nginx access logs: every attempt, its answer, the fail2ban "
                    "bans and the answers the banned addresses got afterwards.")
    parser.add_argument("--access-log", default=None, metavar="GLOB",
                        help=f"nginx access logs, glob (rotated files and .gz included; default: {DEFAULT_ACCESS_LOG})")
    parser.add_argument("--changelog", action="store_true", help="Display the changelog of this program")
    parser.add_argument("-c", "--config", default=None, metavar="FILE",
                        help=f"This configuration file ONLY (default: {SYSTEM_CONF}, then {USER_CONF})")
    parser.add_argument("--config-merge", action="store_true",
                        help="Rewrite the configuration file from the NEW default configuration, keeping the values already set; the old file "
                             "is first copied to FILE.bak-YYYYMMDD-HHMMSS (with -c: that file only). Then exit")
    parser.add_argument("--fail2ban-log", default=None, metavar="GLOB",
                        help=f"fail2ban log, glob (default: {DEFAULT_FAIL2BAN_LOG})")
    parser.add_argument("--jail", default=None, metavar="NAME",
                        help=f"fail2ban jail to examine (default: {DEFAULT_JAIL})")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["en"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--no-lookup", action="store_true", help="No reverse DNS lookup of the addresses (no names in the summary)")
    parser.add_argument("--odoo-log", default=None, metavar="FILE",
                        help="Odoo log: counts the Odoo errors within 60 s of each attempt")
    parser.add_argument("--output", default=None, metavar="DIR",
                        help="Results folder, created in mode 700 (default: /var/lib/sqli-investigate/YYYYMMDD-HHMMSS)")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--top", type=int, default=None, metavar="N",
                        help=f"Number of addresses detailed in the summary (default: {DEFAULT_TOP})")
    parser.add_argument("-v", "--verbose", action="store_true", help="Display each step and each external command run")
    parser.add_argument("--version", action="version", version=f"{SCRIPT_NAME}.py version {__version__}")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version prints it itself)
        print(f"{SCRIPT_NAME}.py v{__version__}")
    args = parser.parse_args()
    VERBOSE = args.verbose

    if args.config_merge:                     # apps/_config.py fusionner, same rule for every program
        sys.exit(load_module("_config").fusionner_cli(SCRIPT_NAME, args.config, LANGUAGE))
    if args.changelog:
        return show_changelog()
    try:
        config, files_read = read_config(args.config)
    except FileNotFoundError as err:
        eprint(f"ERROR: {err}")
        return 2

    access = args.access_log or config.get("ACCESS_LOG") or DEFAULT_ACCESS_LOG
    f2b = args.fail2ban_log or config.get("FAIL2BAN_LOG") or DEFAULT_FAIL2BAN_LOG
    jail = args.jail or config.get("JAIL") or DEFAULT_JAIL
    odoo_log = args.odoo_log or config.get("ODOO_LOG")
    top = args.top if args.top is not None else config.get("TOP", DEFAULT_TOP)
    no_lookup = args.no_lookup or config.get("NO_LOOKUP", False)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or config.get("OUTPUT") or os.path.join("/var/lib", SCRIPT_NAME, stamp)
    if top < 1:
        eprint("ERROR: --top must be a positive number.")
        return 2

    if args.config:
        read_files = f"{files_read[0]} (requested by -c/--config: no other file read)" if files_read else "none (default values)"
    else:
        read_files = ", then ".join(files_read) + (" (the last one wins)" if len(files_read) > 1 else "") if files_read else "none (default values)"
    print(f"Configuration read: {read_files}")
    print(f"  Options: access logs {access} · jail {jail} · output {output} · {top} addresses"
          + (" · no DNS lookup" if no_lookup else "") + (f" · Odoo log {odoo_log}" if odoo_log else ""))

    warnings = []
    bans_events = read_bans(f2b, jail, warnings)
    banned_now = {}
    for when, act, ip in bans_events:
        banned_now[ip] = act == "Ban"
    attempts, answers = scan_access(access, {ip for _, act, ip in bans_events}, warnings)
    odoo_errors = read_odoo_errors(odoo_log, warnings) if odoo_log else None

    names = {}
    if not no_lookup:
        cache = {}
        for ip, _ in collections.Counter(a["ip"] for a in attempts).most_common(top):
            names[ip] = "(" + (reverse_name(ip, cache) or "no name") + ")"

    windows = ban_windows(bans_events)
    os.makedirs(output, mode=0o700, exist_ok=True)
    os.chmod(output, 0o700)
    tsv = ["time\tip\tmethod\tstatus\tbytes\tfamilies\treferer\tuser_agent\tdecoded_url\tfile"]
    for a in attempts:
        tsv.append("\t".join([fmt(a["time"]), a["ip"], a["method"], str(a["status"]), a["size"], ",".join(a["families"]),
                              shell_safe(a["referer"]), shell_safe(a["agent"]), shell_safe(a["url"]), a["file"]]))
    write_private(os.path.join(output, "sqli-requests.tsv"), "\n".join(tsv) + "\n")
    summary = build_summary(attempts, answers, windows, banned_now, names, odoo_errors, top, lambda code, text: text)
    write_private(os.path.join(output, "sqli-summary.txt"), "\n".join(summary) + "\n")
    state = fail2ban_state(jail, warnings)
    bans_text = ["Current state of the jail %s (fail2ban-client status):" % jail, state or "(unavailable)", "",
                 "Events read: %d" % len(bans_events)]
    bans_text += ["%s %s %s" % (fmt(when), act, ip) for when, act, ip in bans_events]
    write_private(os.path.join(output, "sqli-bans.txt"), "\n".join(bans_text) + "\n")

    color = (lambda code, text: "\x1b[%sm%s\x1b[0m" % (code, text)) if sys.stdout.isatty() and not os.environ.get("NO_COLOR") else (lambda c, t: t)
    print("\n".join(build_summary(attempts, answers, windows, banned_now, names, odoo_errors, top, color)))
    print("")
    print(f"Results written to: {output}")
    print("  sqli-requests.tsv (every attempt), sqli-summary.txt (summary), sqli-bans.txt (bans and state of the jail)")
    for w in warnings:
        eprint(f"WARNING: {w}")
    if VERBOSE:
        eprint(f"  [verbose] {len(attempts)} attempts, {len(bans_events)} fail2ban events, {len(answers)} addresses tracked")
    return 0


def protected_main():
    try:
        return main()
    except KeyboardInterrupt:
        eprint("\nInterrupted (Ctrl-C).")
        return 130


def launch_with_report(function):
    """--report-err: paste-ready error report at the end of the run (apps/_rapport.py, if next to this file)."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        module = load_module("_rapport")
        if module is None:
            eprint("--report-err unavailable (apps/_rapport.py missing): normal run.")
            return function()
        return module.lancer(function, os.path.basename(__file__), __version__, SCRIPT_DIR)
    return function()


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(protected_main))
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
