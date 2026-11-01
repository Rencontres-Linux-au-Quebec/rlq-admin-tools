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
# app-log-live.py - the application journal IN REAL TIME (Odoo: "journalctl --lines 50 -fu erplibre.service"), formatted:
#   * LOCAL date and time in the format 2026-10-02 10:07:18.33 (hundredths): no more duplicate of Odoo's UTC time or of the PID;
#     the date "[02/Oct/2026 14:07:18]" of werkzeug requests is removed (it is already at the start of the line);
#   * each IP address replaced by what is known about it, followed by the address in brackets, in this order:
#       1. the NAME of the person who has already logged in to the site from this address (Odoo journal, "Login successful for
#          db:... login:... from IP"; name read from PostgreSQL read-only, otherwise the login; a login that arrives
#          WHILE displaying is learned immediately);
#       2. the team label (whitelist), or "this server" (loopback, address of the server); on the address of a PLACE: "Person | Place" (several accounts: "Place | Person +1 other account(s)");
#       3. the DNS name (reverse DNS);
#       4. failing that, the OWNER of the address block according to RDAP (rdap.org, otherwise whois): "Name (org)" = registered organization,
#          "NAME (network)" = only the technical name of the network. It is NOT necessarily an internet provider (host, cloud, search
#          engine, company) and all the addresses of that block carry the same name. --no-isp: no outside request;
#   * COMPACT PRESENTATION: "2026-10-07 22:46:02.82 odoo18 odoo INFO CA 11.191.124.32    name ... "GET ... " - no ":" after the program or after the logger, address and country WITHOUT
#     brackets (country BEFORE the address, no comma) in a column of 18 characters, and the "- -" of a request (RFC 1413 identity and HTTP user, always "-" in Odoo) removed (never when there is a real
#     user); addresses quoted INSIDE a message keep "name [CA address]";
#   * ALIGNMENT: the name that replaces the address takes AT LEAST 45 characters (--dns-max N: N without ever truncating, 20 without a value; --dns-max-truncate N: cut at N, "..." at the end,
#     32 without a value); on lines WITHOUT an address (Odoo messages such as odoo.addons.mail.models.mail_mail), the text starts at the column of the GET / POST of requests (never above the number columns); the GET of all
#     the line types (werkzeug, websocket "longpolling", with or without --min) starts at the same column, and the redundant ISO date of a websocket is removed;
#   * NUMBERS AFTER THE HTTP CODE (legend at startup): Odoo "200 - 105 0.046 0.426" = size, SQL queries, SQL time, Python time; websocket "101 494 14.6" = size, duration;
#     colors when high (SQL >= 300 orange, >= 1000 red; size >= 1 MB / 10 MB; durations according to --slow);
#   * TEST RECORDING (1.93): R starts / stops a recording (label asked; "REC" at column $COLUMNS-4 meanwhile; the .tar.xz archive of the window, noise left out,
#     see apps/_record.py) - --record-test-log MIN records without the keyboard, then exits; N (while recording) starts / ends a step with a description (steps.txt);
#   * STEPS LINE (1.99): F key (or --steps-line, STEPS_LINE) shows ALL the steps of the recording on ONE white reverse-video line, at each step (screen only).
#   * STATUS BAR (1.113, --status-every N): reverse-video summary every N lines (SQL injection attempts, 4xx, 5xx, banned addresses, slow requests), reset by Ctrl-T and g;
#     f key: the buffer of the last lines (--buffer N) displayed again with the current options; P key: printed to a file with colors; Y key: latency report.
#   * KEY MENU (? or h): toggles and settings on the fly - a --accentuate-group, A --anonymize, c --chime, e --exclude-ip, T --time-report, U --underline N, d --dns-max, t --dns-max-truncate, H --health, i --hide-ip, l --highlight, m --min, M --modules (table of the installed Odoo modules, sorted by name, date, creation, version, author or state), o --only, r error report (--report-err),
#     s --suspect, v --verbose, V version; S survey registrations, I event registrations, b addresses to ban (nginx-log-audit.sh --ban, like web-monitor.py).
#   * KEYBOARD DASHBOARD (terminal only, --no-keys: disabled): Ctrl-G = health (check mark / warning / cross symbols, with the detail of the problems), efficiency of the program (CPU, memory, input/output,
#     address cache), pages per language (EN, FR, ES), HTTP codes, top 10 URLs, Odoo errors; Ctrl-T = only what changed since the last display; --health MIN:
#     automatic alert with the detail, ONLY if there is a problem;
#   * DAILY JOURNAL: the live stream (not the startup history) is also written WITH its colors to FOLDER/app-log-live-YYYY-MM-DD.log (mode 600, 30 days kept; --log-dir,
#     --log-keep-days, --no-log-file): "less -R file" or "tail -f file";
#   * INVERSE VIDEO: the URL of a SUSPICIOUS request (WordPress, .php, phpMyAdmin, .env, .git, backups, directory traversal, Odoo database manager...) in MAGENTA; the URL of an HTTP 5xx (red) or 4xx (yellow) error, only the URL; the address of a machine of the WHITELIST (white background) or of the PLACES file
#     (gray background), black text (explicit colors: readable on any theme) - with --hide-ip, it is the name that is; the login page keeps its style except on 5xx; a legend is displayed at startup;
#   * [banned: fail2ban] / [banned: CrowdSec] at the end of the line when the address is CURRENTLY banned (fail2ban-client, ipsets crowdsec-blocklist-v4 / -v6 of sync-crowdsec-blocklist.sh,
#     "nomatch" = exception; re-read every 60 s; root required; never for the whitelist or a place; --no-banned: disabled);
#   * SLOW REQUESTS: Odoo duration (SQL + Python) >= --slow seconds (5 by default): both durations in bold orange, bold red at 3 times the threshold, and "<- slow: 12.3 s";
#   * FILTERS: --suspect (only suspicious requests); --not-found (only 404 answers, and the summary lists ALL these pages); --only TEXT (name, address, URL, module... case-insensitive, repeatable: one OR the other); both
#     add up; a Python trace follows the decision of its first line; the summary counts only the displayed lines;
#   * SESSION SUMMARY when stopping with Ctrl-C (and with --summary at the end of a --no-follow): most active addresses, requests by name (the DNS column: identified
#     names only, the addresses without a name are counted apart; Ctrl-T gives the period), suspicious requests (with [banned]), 5xx and 4xx errors,
#     slow requests, banned addresses seen;
#   * PRESENCE: "login" (filled circle), "logout" (cross), "no activity since N min" (empty circle) inserted in the stream, and a summary of who is
#     still logged in after the history (see "Logged in" below);
#   * colors: HTTP codes (200 green, 3xx cyan, 4xx red, 5xx bold red), levels and error words (ERROR and Traceback in red,
#     WARNING in orange), logins to the site (login, /web/login) in white on blue; --min: the minimum of information.
#   * COUNTRY: "Name [CA address]" (local geoiplookup database if it exists, otherwise RDAP - the same call as the internet provider; never
#     for this server, a private network or the team);
#   * 127.0.0.1 and the addresses of this server: never a person; the PROGRAM is named (app-health-check.py for its health probes);
#   * LOGIN: as soon as a person logs in, their lines of the last --recap seconds (120), displayed higher up without a name, are
#     displayed again with their name (without relaunching journalctl); the following lines carry their name immediately;
#   * error WITHOUT SEVERITY (concurrent update conflict: "bad query" + "could not serialize access") in orange, with its reason.
# "Logged in": Odoo does not record the end of a session. A person is "logged in" if they logged in (journal), did not
# request /web/session/logout and had some activity for less than --idle minutes (15 by default) from THEIR address (another
# person behind the same address counts too). The session itself stays valid for up to 7 days without activity.
# The stream is never blocked by a slow lookup: a line waits at most 3 s, then keeps the IP address.
# BigBlueButton (file journals): the nginx and bbb-web journals are followed (tail -F), without names of people or presence.
# NGINX LOGS (1.115, --log-nginx, LOG_NGINX): the access and error logs of the site are merged with the application stream, in time
#   order, with the same date and time prefix (apps/_logs_merge.py); --since, --until and -g apply to them too.
#
#
#   (--no-cache: neither reading nor writing of the permanent address cache, /var/lib/nginx-tools/ip-cache.sqlite)
# Usage:
#   app-log-live.py                          last 50 messages then the live stream (Ctrl-C to stop)
#   app-log-live.py --lines 500              ... with 500 messages of history
#   app-log-live.py --min                    the minimum: without database name or "werkzeug", without fetchmail noise
#   app-log-live.py --hide-ip                without the IP address in brackets after the name
#   app-log-live.py --no-truncate            whole log lines (by default: shortened to $COLUMNS - 10, "start ... last two words")
#   app-log-live.py --no-anonymize           real IP addresses, e-mails and names on screen (by default: stable pseudonyms IP-4f2a9c, membre-4f2a9c; A key on the fly)
#   app-log-live.py --underline 3            one log line out of 3 underlined to the end of the screen line (by default 10; --no-underline: none)
#   app-log-live.py --no-follow              displays the last messages then stops (for a pipe or a file)
#   app-log-live.py --log-nginx             the nginx logs of the site in the same stream, in time order (-S, -U, -g apply to them)
#   app-log-live.py --no-isp --no-history    no outside request, without the login history
#   app-log-live.py -S '-2h' -U now --utc   lines of the last two hours, in UTC (or -S 'yesterday', --since '2026-10-29 08:00')
#   app-log-live.py -g 'erreur|timeout' -n 500   messages matching a regular expression (--grep), 500 lines of history
#   app-log-live.py --exclude-country US,CN   hide the addresses of these countries (--country CA shows only them)
#   app-log-live.py --days 0.1 --no-follow   the last 2.4 hours of sign-ins (fractions of a day are allowed)
#   --days N, --idle MIN, --recap SEC, --no-presence, --service NAME, --namespace NAME, --app NAME, --verbose, --version, --changelog, --report-err

import argparse
import ast
import atexit
import collections
import contextlib
import copy
import datetime
import glob
import importlib.util
import json
import ipaddress
import math
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from urllib.parse import unquote
from collections import Counter, OrderedDict
from concurrent.futures import Future

__version__ = "1.141.20261031.232038"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]


def _start():
    """Shared context (apps/_i18n.py: language, configuration, translated print / input, parser); module missing: French, without configuration."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        globals()["I18N_MODULE"] = module
        # 1.91: --anonymize is applied HERE, piece by piece between the color codes (a colored address or name stays recognized): never relaunched
        # behind the output filter of apps/_traduire.py, which saw "\x1b[...m11.191.124.32" as a word and left colored addresses and names in clear
        os.environ["NGINX_TOOLS_ANON_SELF"] = "1"
        try:
            return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "APP_LOG_LIVE_LANG", ("_bbb", "_listes", "nginx-log-audit", "_connexions", "_limites"))
        finally:
            os.environ.pop("NGINX_TOOLS_ANON_SELF", None)            # the programs launched by this one keep the usual rule
    except Exception:
        return None


I18N_MODULE = None
I18N = _start()


def stop_group(proc):
    """Stops a program started in its own session and everything it launched (SIGTERM to its process group, SIGKILL 3 s later if needed)."""
    for sig_number, wait in ((signal.SIGTERM, 3), (signal.SIGKILL, 2)):
        try:
            os.killpg(proc.pid, sig_number)
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def foreground_child():
    """Context of a child program that owns the terminal (questions, Ctrl+C with its own confirmation): apps/_i18n.py foreground_child(); nothing without it (1.84)."""
    return I18N_MODULE.foreground_child() if I18N_MODULE is not None and hasattr(I18N_MODULE, "foreground_child") else contextlib.nullcontext()
LANGUAGE = I18N.langue if I18N else "fr"
TR = I18N.tr if I18N else (lambda text: text)
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 - all displayed text goes through the translator (no effect in French)
# Configuration file options (/etc/default/app-log-live.conf, then the personal file .app-log-live.conf): KEY -> (command-line option, type).
# LANGUAGE: en, fr or auto (follow LC_ALL / LANG).
def _comma_list(value):
    """"a, b" -> ['a', 'b'] (configuration value with several items)."""
    return [t.strip() for t in value.split(",") if t.strip()]


def _chime_config(value):
    """CHIME: 0, 1 or 2 (empty or "none": no beep)."""
    if value.strip().lower() in ("aucun", "none", "n"):
        return None
    n = int(value)
    if n not in (0, 1, 2):
        raise ValueError("0, 1 or 2 expected")
    return n


def _truncate_config(value):
    """TRUNCATE (1.88): a number of columns (0 = $COLUMNS - 10), yes (= 0) or no (whole lines)."""
    v = value.strip().lower()
    if v in ("no", "non", "n", "false", "off", "none", "aucun"):
        return False
    if v in ("yes", "oui", "y", "o", "true", "on"):
        return 0
    return int(value)


def _underline_config(value):
    """UNDERLINE (1.91): one line out of N underlined — a number (0 = none), yes (= every UNDERLINE_DEFAULT lines) or no."""
    v = value.strip().lower()
    if v in ("no", "non", "n", "false", "off", "none", "aucun"):
        return 0
    if v in ("yes", "oui", "y", "o", "true", "on"):
        return UNDERLINE_DEFAULT
    n = int(value)
    if n < 0:
        raise ValueError("0 or more expected")
    return n


UNDERLINE_RATIO = 0.8                                             # 1.107: underlined lines stop at 80 % of the terminal width (COLUMNS)
UNDERLINE_DEFAULT = 10                                                # --underline without N (and default since 1.98): one log line out of 10 underlined


SCHEMA_CONFIG = {"ACCENTUATE_GROUP": ("accentuate_group", str), "CHIME": ("chime", _chime_config), "DNS_MAX_TRUNCATE": ("dns_max_truncate", int), "EXCLUDE_IP": ("exclude_ip", _comma_list),
                 "ONLY": ("only", _comma_list), "STATUS_HEADER": ("status_header", bool), "STEPS_LINE": ("steps_line", bool), "SUSPECT": ("suspect", bool), "SUMMARY": ("summary", bool), "TIME_REPORT": ("time_report", float), "TRUNCATE": ("truncate", _truncate_config), "WATCH": ("watch", str), "ANONYMIZE": ("anonymize", bool), "UNDERLINE": ("underline", _underline_config),
                 "APP": ("app", str), "CMS": ("cms", str), "CONNECTIONS": ("connections", float), "DAYS": ("days", float),"DISK_MIN": ("disk_min", float), "DNS_MAX": ("dns_max", int), "HEALTH": ("health", float), "HIDE_ADDONS": ("hide_addons", bool), "HIDE_IP": ("hide_ip", bool), "HIGHLIGHT": ("highlight", str), "IDLE": ("idle", float),
                 "LINES": ("lines", int), "LOG_DIR": ("log_dir", str), "LOG_KEEP_DAYS": ("log_keep_days", int), "LOG_MERGE": ("log_merge", bool), "LOG_NGINX": ("log_nginx", bool), "MIN": ("min", bool), "MODULES_CUSTOM": ("modules_custom", bool), "MODULES_SORT": ("modules_sort", str), "MODULES_STARTUP": ("modules_startup", bool), "NAMESPACE": ("namespace", str),
                 "NO_BANNED": ("no_banned", bool), "NOT_FOUND": ("not_found", bool), "NO_BAN_PROMPT": ("no_ban_prompt", bool), "NO_CACHE": ("no_cache", bool), "NO_HISTORY": ("no_history", bool),
                 "NO_ISP": ("no_isp", bool), "NO_KEYS": ("no_keys", bool), "NO_LOG_FILE": ("no_log_file", bool), "NO_PRESENCE": ("no_presence", bool),
                 "LEVEL": ("level", int), "BUFFER": ("buffer", int), "STATUS_EVERY": ("status_every", int), "NO_USER_AGENT": ("no_user_agent", bool), "HIDE_USER_AGENT": ("hide_user_agent", bool), "REQUEST_LENGTH": ("request_length", bool), "RECAP": ("recap", float), "RECORD_MAX": ("record_max", float), "SERVICE": ("service", str), "SLOW": ("slow", float), "VERBOSE": ("verbose", bool)}
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
LINES_DEFAULT = 50
DAYS_DEFAULT = 0                                                      # 0 = the whole journal history
IDLE_DEFAULT = 15.0                                                 # minutes without activity before "no more activity"
REPORT_DEFAULT = 60.0                                                 # --time-report without a value: minutes between two periodic reports
LEVEL_MAX = 9                                                        # dashboard levels: 1 (verdict) to 9 (everything) - keys 1 to 9, --level
# Shared thresholds (apps/_seuils.py, also read by web-monitor.py; its header lists the files that override them).
# Without the module, or if it cannot be read, the built-in value of the constant is kept.
def seuil_commun(cle, defaut):
    chemin = os.path.join(SCRIPT_DIR, "apps", "_seuils.py")
    if not os.path.isfile(chemin):
        return defaut
    try:
        spec = importlib.util.spec_from_file_location("_seuils", chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        valeurs, _lus, avis = module.charger()
    except Exception as erreur:
        print(f"WARNING / AVERTISSEMENT: apps/_seuils.py unreadable / illisible ({erreur}): built-in values used", file=sys.stderr)
        return defaut
    for avertissement in avis:
        print(f"WARNING / AVERTISSEMENT: {avertissement}", file=sys.stderr)
    return valeurs.get(cle, defaut)


CONNECTIONS_THRESHOLD_DEFAULT = seuil_commun("CONNECTIONS_PCT", 80.0)                                          # % of use of a limit (connections, descriptors, PostgreSQL, nginx) from which a WARNING is displayed; --connections
DISK_MIN_DEFAULT = 5.0                                               # free GB below which a WARNING is displayed (journals partition); --disk-min
HEALTH_DEFAULT = 10.0                                                   # minutes between two automatic health checks (alert only if there is a problem)
JOURNAL_DAYS_DEFAULT = 180                                            # days of daily journals kept (they contain addresses and names)
RECAP_DEFAUT = 120.0                                                  # seconds of lines displayed again with the name after a login
WAIT_DELAY = float(os.environ.get("APP_LOG_LIVE_WAIT", "3"))      # seconds that a line waits for its names
NGINX_DIR = os.environ.get("APP_LOG_LIVE_NGINX_DIR", "/var/log/nginx")
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
COLORS_256 = "256color" in os.environ.get("TERM", "") or bool(os.environ.get("COLORTERM"))
ORANGE = "38;5;208" if COLORS_256 else "33"
VERBOSE = False

IPV4_RE = re.compile(r"(?<![\w.])(?<![^/]/)(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\w|\.\d)")
IPV6_RE = re.compile(r"(?<![\w:.])[0-9A-Fa-f:]{2,39}(?![\w:])")
LOGIN_RE = re.compile(r"Login successful for db:(\S+) login:(\S+) from ([0-9A-Fa-f:.]+)")
HISTORY_RE = re.compile(r"^(\S+) .*Login successful for db:(\S+) login:(\S+) from ([0-9A-Fa-f:.]+)")

# Line of "journalctl -o short-iso-precise": 2026-10-02T10:07:18.326421-0400 odoo18 odoo[502389]: message
# 1.112: the host name is optional (journalctl --no-hostname); the line is then "2026-10-02T10:07:18.326421-0400 odoo[502389]: message"
JOURNAL_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})([+-]\d{2}):?(\d{2}|Z)? (?:([^\s\[:]+) )?([^\s\[:]+)(?:\[\d+\])?: (.*)$")
# 1.112 --utc: times of the log lines and of --since / --until in UTC instead of the local time (set by main)
TIME_UTC = False
# Odoo message: 2026-10-02 14:07:18,326 502389 INFO base werkzeug: text
ODOO_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ (DEBUG|INFO|WARNING|ERROR|CRITICAL) (\S+) (\S+): (.*)$")
WERKZEUG_DATE_RE = re.compile(r"^(.*? - - )\[\d{2}/\w{3}/\d{4} \d{2}:\d{2}:\d{2}\] (\".*)$")
# Websocket requests ("longpolling"): the date is in ISO format "[2026-10-08 13:11:22]" in UTC; removed ONLY if it is the same instant as the time of the line
DATE_ISO_RE = re.compile(r"^(.*? - - )\[(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\] (\".*)$")
STATUS_RE = re.compile(r'"(?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s.*"\s(\d{3})\b')
LOGIN_PATH_RE = re.compile(r'(?<=[\s"])(/(?:[a-z]{2}(?:_[A-Z]{2})?/)?web/(?:login|session/(?:authenticate|logout)|reset_password|signup)[^\s"]*)')
LOGOUT_RE = re.compile(r'"(?:GET|POST)\s/(?:[a-z]{2}(?:_[A-Z]{2})?/)?web/session/logout[^"]*"')
LOGIN_OK_RE = re.compile(r"(Login successful) for db:\S+ (login:\S+)")
LOGIN_FAILED_RE = re.compile(r"(Login failed|Login attempt failed|authentication failed)\b(?: for db:\S+ (login:\S+))?", re.I)
ERROR_WORDS_RE = re.compile(r"Traceback \(most recent call last\):|\b[A-Za-z_][\w.]*(?:Error|Exception)\b|\bFATAL\b|\bdeadlock detected\b|"
                            r"\bout of memory\b|\bKilled\b|Connection refused|\btimed out\b|\bWorker [\w(). ]*timeout")
# --min: usual noise lines, discarded EXCEPT if it is an error (level WARNING, ERROR or CRITICAL, or a trace)
MIN_EXCLUDED_RE = re.compile(r"^(?:odoo\.addons\.mail\.models\.fetchmail: |odoo\.addons\.base\.models\.ir_cron: Job 'Mail: Fetchmail Service)")
# 1.99 --steps-line (F key): all the steps of a recording on one white line; --record-max: 60 minutes at most (default and maximum, 0 refused).
# 1.97 --hide-addons: INFO / DEBUG lines of the Odoo modules (logger odoo.addons.*) are hidden EXCEPT e-mails being sent and generated files (PDF reports...);
# errors (WARNING, ERROR, CRITICAL, traces) are never hidden. Searched on "logger: text".
ADDONS_KEEP_RE = re.compile(r"successfully sent|\bmail_mail\b|\bir_mail_server\b|mail delivery|\bsmtp\b|ir_actions_report|wkhtmltopdf|\bpdf\b|\.(?:pdf|xlsx?|docx?|csv|zip)\b"
                            r"|report has been generated|\breport\b.*\bgenerat", re.IGNORECASE)
# Access request (nginx / werkzeug journal): the URL and the HTTP code
REQUEST_RE = re.compile(r'"(?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s(\S+).*"\s(\d{3})\b')
# 3-letter methods (GET, PUT): one more space after them so that their URL aligns with that of POST / HEAD (4 letters)
SHORT_METHOD_RE = re.compile(r'"(?:GET|PUT)( )(?=\S+.*"\s\d{3}\b)')
# SUSPICIOUS requests: neither Odoo nor BigBlueButton (WordPress, PHP, phpMyAdmin...), sensitive files (.env, .git, backups, keys), directory traversal, exposed Odoo
# database manager. Same spirit as SENSITIVE_RE of nginx-log-audit.sh; search on the decoded URL (%2e%2e = ..).
SUSPECT_WP = r"/wp-(?:admin|content|includes|login|json|config|cron)|/wp(?:/|\?|$)|/wordpress(?:/|\?|$)|wlwmanifest|xmlrpc\.php|\.php(?:\b|$)"    # suspicious on an Odoo site ONLY (normal under WordPress)
SUSPECT_BASE = (
    r"/\.(?:env|git|svn|hg|aws|ssh|htaccess|htpasswd|ds_store|npmrc|docker)(?:\b|/|$)|\.env(?:\.\w+)?(?:\?|$)"
    r"|/_ignition|/debug/default|/_profiler|/telescope(?:/|$)|/phpinfo"
    r"|phpmyadmin|/pma/|/myadmin|/adminer|cgi-bin|/vendor/phpunit|/boaform|/hnap1|/actuator|/jenkins|/solr/|/manager/html|/server-(?:status|info)|/owa/|/ecp/|/autodiscover"
    r"|\.(?:bak|old|orig|sql|swp|dump)(?:\?|$)|/config\.(?:json|ya?ml|ini|xml)|/(?:composer|package)\.(?:json|lock)|/id_rsa|/credentials|/secrets?\.(?:json|ya?ml|txt)"
    r"|/etc/(?:passwd|shadow)|/proc/self|\.\./|/win\.ini|/boot\.ini|/web/database/|/xmlrpc(?:/2)?/db\b")
SUSPECT_RE = re.compile(SUSPECT_BASE + "|" + SUSPECT_WP, re.I)
SUSPECT_CMS_BBB = (r"|/administrator(?:/|$)|/joomla|/drupal|/sites/default|/typo3|/magento|/prestashop|/bitrix|/umbraco|/ghost/|/user/login|/node/\d+|/components/com_"
                   r"|/misc/drupal|/index\.php|\.(?:asp|aspx|jsp|cgi)(?:\b|$)|/admin/login|/wp-json|/joomla|/cms(?:/|$)|/typo3conf")
CMS = "odoo"


def regler_cms(cms, bbb_server=False):
    """WordPress site: /wp-admin, /wp-login.php, xmlrpc.php, *.php… are normal pages, no longer suspicious requests; Odoo-only site: they are. BigBlueButton server:
    EVERYTHING that touches a CMS (WordPress, Joomla, Drupal, TYPO3, Magento, *.php, *.asp…) is suspicious, whatever the configured CMS: BigBlueButton hosts none."""
    global SUSPECT_RE, CMS
    CMS = "bbb" if bbb_server else cms
    SUSPECT_RE = re.compile(SUSPECT_BASE + ("" if cms == "wordpress" and not bbb_server else "|" + SUSPECT_WP) + (SUSPECT_CMS_BBB if bbb_server else ""), re.I)


THRESHOLD_404 = seuil_commun("PROBE_404", 5)               # DIFFERENT pages in 404 for the same address: probe sweep, address to ban (like a suspicious request)
NAME_WIDTH = 45            # MINIMUM width (never truncated) of the name that replaces the address, and of the first field (the logger) of lines without an address
DNS_MAX_DEFAULT = 20         # --dns-max without a value: width of the names column (never truncated)
DNS_TRUNCATE_DEFAULT = 32     # --dns-max-truncate without a value: width AND limit of the names column (the rest is cut, "..." at the end)
NAME_TRUNCATE = 45            # limit of the names (default: cut at the width of the column, "..." at the end); 0 = never truncated (--dns-max)
# Numbers after the HTTP code: thresholds above which they change color (orange, then red)
SQL_HIGH, SQL_VERY_HIGH = 300, 1000                       # number of SQL queries of a page
SIZE_HIGH, SIZE_VERY_HIGH = 1_000_000, 10_000_000   # bytes of the response
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m|[\ue001\ue002]")        # color codes and the markers of protected text (see raw)
PROTECTED_RE = re.compile("\ue001(.*?)\ue002", re.S)


def raw(text):
    """Marks text of the journal (data: never translated) inside a line that Output.write sends through the translator."""
    return "\ue001" + text + "\ue002" if text else text


def translate_protected(text):
    """TR(text) without touching the parts marked with raw(): hidden behind tokens during the translation, then put back (markers removed)."""
    kept = []

    def hide(m):
        kept.append(m.group(1))
        return f"\ue003{len(kept) - 1}\ue004"
    hidden = PROTECTED_RE.sub(hide, text) if "\ue001" in text else text
    result = TR(hidden)
    if kept:
        result = re.sub("\ue003(\\d+)\ue004", lambda m: kept[int(m.group(1))], result)
    return result.replace("\ue001", "").replace("\ue002", "")
STYLES = {"nginx": "1;35", "person": "1;32", "team": "1;32", "place": "1;36", "server": "36", "dns": "36", "org": "33", "reseau": "33", "ip": "90", "connection": "1;37;44",
          "failure": "1;" + ORANGE, "error": "1;31", "warning": ORANGE, "debug": "2", "highlight": "30;46",
          # INVERSE VIDEO (7): suspicious request; URL of a 5xx (red) or 4xx (yellow) error. Whitelist address (white background) or places file address (gray background):
          # EXPLICIT background AND text (black), never "7;90" (inverted gray): on a theme where bright black is black, the address became black on black
          "suspect": "7;35", "url_critical": "7;91", "url_warning": "7;93", "blanche": "107;30", "place_ip": ("48;5;245" if COLORS_256 else "47") + ";30",
          "accent": "1;97;48;5;18" if COLORS_256 else "1;97;44",       # contact of the --accentuate-group group: bold white on dark blue
          "banned": "1;91", "slow_request": "1;" + ORANGE, "very_slow_request": "1;31", "title": "1;36", "transfer_low": "32", "transfer_mid": "33", "transfer_slow": "1;31"}
# Duration of an Odoo request (werkzeug): "... 200 - 105 0.046 0.426" = code, size, SQL queries, SQL time, Python time (seconds)
DURATION_RE = re.compile(r'"\s\d{3}\s\S+\s(\d+)\s(\d+\.\d+)\s(\d+\.\d+)\s*$')
# Same line: the size (bytes or "-") and the number of SQL queries, to color them when they are high
# Whole werkzeug request: '"GET /url HTTP/1.1" 200 - 13 0.006 0.066' - the block "HTTP/1.1 200 - 13 0.006 0.066" is displayed BEFORE "GET /url" (aligned columns)
# 1.117: nginx access line (no SQL or time columns): the request, the status and the size, then the referer, agent and host that stay as text
NGINX_REQUEST_RE = re.compile(r'"((?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s.*?) (HTTP/\d(?:\.\d)?)"\s(\d{3})\s(\S+)')
WERKZEUG_RE = re.compile(r'"((?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s.*?) (HTTP/\d(?:\.\d)?)"\s(\d{3})\s(\S+)(?:\s(\d+)\s(\d+\.\d+))?\s(\d+\.\d+)\s*$')
PORT_RE = re.compile(r"\bport=(\d{1,5})\b")          # 1.121: $server_port of an nginx access line (log_format: port=$server_port)
UPSTREAM_PORT_RE = re.compile(r"\bupstream=\S*?:(\d{1,5})\b")      # 1.121: port of the Odoo upstream (log_format: upstream=$upstream_addr)
SQL_SIZE_RE = re.compile(r'"\s\d{3}\s(\S+)\s(\d+)\s\d+\.\d+\s\d+\.\d+\s*$')


# ------------------------------------------------------------------------------------------------------------------
# --log-merge (1.123): the nginx line and the Odoo line of the same request are shown as ONE line
# ------------------------------------------------------------------------------------------------------------------
MERGE_WINDOW = 2.0      # seconds (log time) between the nginx line and the Odoo line of one request (Odoo logs when its answer is ready)
MERGE_HOLD = 3.0        # seconds (wall clock) an nginx line waits for its Odoo line, then it is shown alone (static file, no Odoo...)


def is_nginx_request(L):
    return L.database == "nginx" and L.logger == "request" and L.instant is not None and bool(NGINX_REQUEST_RE.search(L.text or ""))


def is_odoo_request(L):
    """Odoo line of a request WITH its SQL queries and times (the numbers the merged line takes from it)."""
    if L.database == "nginx" or L.instant is None:
        return False
    m = WERKZEUG_RE.search(L.text or "")
    return bool(m and m.group(5))


def request_key(L):
    """(method and URL, status code): the same request in the nginx line and in the Odoo line."""
    m = WERKZEUG_RE.search(L.text or "") or NGINX_REQUEST_RE.search(L.text or "")
    return (m.group(1), m.group(3))


def merge_step(item, held):
    """1.123 --log-merge: `held` = request lines waiting for their partner, as (item, key, log time, wall time): nginx lines wait for their Odoo line,
    and (1.135) Odoo lines wait for their nginx line, because the two sources are read at different speeds (the Odoo line can come first).
    Returns the items to show now, in order (maybe none). A pair becomes ONE line (the nginx line with the SQL queries and the times of Odoo).
    A held line whose partner can no longer come is released alone."""
    L = item[0]
    ready = []
    while held and L.instant is not None and held[0][2] + MERGE_WINDOW < L.instant:
        ready.append(held.popleft()[0])
    if is_odoo_request(L):
        key = request_key(L)
        for index, (held_item, held_key, held_instant, _wall) in enumerate(held):
            if is_nginx_request(held_item[0]) and held_key == key and abs(L.instant - held_instant) <= MERGE_WINDOW:
                del held[index]
                m = WERKZEUG_RE.search(L.text)
                held_item[0].odoo_times = (m.group(5), m.group(6) or "", m.group(7))
                if L.ts_txt:                      # 1.131: the merged line shows the time of the Odoo line (hundredths), nginx has only seconds
                    held_item[0].ts_txt = L.ts_txt
                ready.append(held_item)
                return ready
        held.append((item, key, L.instant, time.time()))      # 1.135: the Odoo line waits for its nginx line
        return ready
    if is_nginx_request(L):
        key = request_key(L)
        for index, (held_item, held_key, held_instant, _wall) in enumerate(held):
            if is_odoo_request(held_item[0]) and held_key == key and abs(L.instant - held_instant) <= MERGE_WINDOW:
                del held[index]                   # 1.135: the Odoo line came first: it is absorbed into this nginx line
                m = WERKZEUG_RE.search(held_item[0].text)
                L.odoo_times = (m.group(5), m.group(6) or "", m.group(7))
                if held_item[0].ts_txt:
                    L.ts_txt = held_item[0].ts_txt
                ready.append(item)
                return ready
        held.append((item, request_key(L), L.instant, time.time()))
        return ready
    ready.append(item)
    return ready


def merge_release(held, now):
    """1.123: the nginx lines held for more than MERGE_HOLD seconds (wall clock) are shown alone, in order."""
    released = []
    while held and held[0][3] + MERGE_HOLD <= now:
        released.append(held.popleft()[0])
    return released


def short_http(protocol):
    """1.123: "HTTP/1.1" is shown "H1.1" (the request columns are narrower)."""
    return "H" + protocol[5:] if protocol.startswith("HTTP/") else protocol


def color_code(code, text):
    return f"\x1b[{code}m{text}\x1b[0m" if COLOR and code else text


NUMBER_RE = re.compile(r"(?<![\w.])\d+(?!\w)(?: %)?")


def percent_text(n, total):
    """« 12 », or « <1 » for a share that is not zero but rounds to 0 (1.83: one 4xx error out of 297 requests showed « 4xx 0 % »)."""
    share = 100 * n / total if total else 0
    return "<1" if 0 < share < 0.5 else f"{share:.0f}"


def numbers(text, style="1;36"):
    """The numbers (and their "%") of a summary line in color; "2xx", "EN" and the words stay as they are."""
    return NUMBER_RE.sub(lambda m: color_code(style, m.group(0)), TR(text))      # 1.83: translated first (a colored "95 %" split the fragment "% under")


MEASURE_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?: ?(?:%|[KMGT]?o\b(?:/s)?))?(?!\w)")


def measured_numbers(text, style="1;36"):
    """The measures of a line ("0.4 %", "39.8 MB", "55.5 KB/s", "0 B", "194", decimals included) in color; the words stay as they are."""
    return MEASURE_RE.sub(lambda m: color_code(style, m.group(0)), TR(text))     # 1.83: translated first (a colored "67.6 KB/s" split "/s, of which disk")


TIMES_RE = re.compile(r"×\d+")


def times(text, style="1;36"):
    """The "×N" (number of times) of a line in color."""
    return TIMES_RE.sub(lambda m: color_code(style, m.group(0)), text)


def none_found(word="none"):
    """"none" (or "no", 0) in green: nothing to report. In French the feminine form (« aucune »), used by every caller."""
    return color_code("32", "aucune" if LANGUAGE == "fr" and word == "none" else word)


def none_fem():
    """"none" for the plain-text lists; « aucune » in French (feminine)."""
    return "aucune" if LANGUAGE == "fr" else "none"


def http_style(code):
    """200 green, 3xx cyan, 429 orange, 4xx (404…) red, 5xx bold red."""
    n = int(code)
    if n >= 500:
        return "1;31"
    if n == 429:
        return ORANGE
    if n >= 400:
        return "31"
    if n >= 300:
        return "36"
    return "32" if n >= 200 else None


def read_exclusions(text):
    """(networks, invalid) of a list "IP1,IP2,10.0.0.0/8" (addresses or networks, IPv4 or IPv6, separated by commas or spaces)."""
    networks, invalid = [], []
    for word in re.split(r"[,\s]+", text or ""):
        if not word:
            continue
        try:
            networks.append(ipaddress.ip_network(word, strict=False))
        except ValueError:
            invalid.append(word)
    return networks, invalid


def excluded_address(ip, networks):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a.version == r.version and a in r for r in networks)


def load_group(odoo_db, name, databases_seen):
    """(members, error, fatal): members = {(database, login)} of the accounts whose contact carries the Odoo contact TAG `name` (res.partner.category);
    error: text if the tag exists in no database (fatal) or if PostgreSQL is unreadable (non-fatal: we continue without accentuation)."""
    if odoo_db is None:
        return None, "available only for Odoo (reading PostgreSQL).", False
    databases_seen = list(databases_seen) or odoo_db.bases_odoo() or []
    if not databases_seen:
        return None, "no readable Odoo database (PostgreSQL unreachable or program not run as root): unable to check the tag.", False
    member_list, exists_, readable, known_list = set(), False, False, []
    for database in databases_seen:
        found = odoo_db.groupe_existe(database, name)
        if found is None:
            continue
        readable = True
        if found:
            exists_ = True
            logins = odoo_db.membres_groupe(database, name)
            member_list.update((database, login) for login in (logins or []))
        else:
            known_list += odoo_db.groupes_contacts(database) or []
    if not readable:
        return None, "contact tag tables unreadable (PostgreSQL unreachable?): unable to check the tag.", False
    if not exists_:
        close_ones = ", ".join(sorted(set(known_list))[:20]) or "none"
        return None, f"the contact tag « {name} » does not exist in any Odoo database. Existing tags: {close_ones}.", True
    return member_list, None, False


def tmux_option(name):
    """Value of a global tmux option (byobu relies on tmux); None if tmux is absent or does not know it."""
    r = lancer(["tmux", "show-options", "-gv", name], 3)
    return r[1].strip() if r[0] == 0 and r[1].strip() else None


def prepare_beep():
    """(mode, hints) of the sound signal. Outside tmux/byobu: the BEL character (\a). In tmux (byobu): tmux sends the BEL to the terminal only if bell-action is not "none" and
    visual-bell is "off"; otherwise, if allow-passthrough is "on" (tmux 3.3+), the BEL is sent DIRECTLY to the terminal, without going through tmux."""
    if not os.environ.get("TMUX"):
        advices = ["in screen: « vbell off » in ~/.screenrc"] if os.environ.get("STY") else []
        return "bel", advices
    passthrough, action, visual = tmux_option("allow-passthrough"), tmux_option("bell-action"), tmux_option("visual-bell")
    if passthrough in ("on", "all"):
        return "passthrough", []
    advices = []
    if action == "none":
        advices.append("bell-action is « none »: tmux/byobu swallows the beep — tmux set -g bell-action any")
    if visual == "on":
        advices.append("visual-bell is « on »: tmux/byobu replaces the beep with a message — tmux set -g visual-bell off")
    if advices or passthrough is None:
        advices.append("so that it is heard even in another window: tmux set -g allow-passthrough on (tmux 3.3+); make it permanent in the byobu or tmux configuration")
    return "bel", advices


def sonner(mode, screen):
    """A beep, ONLY if the output is a terminal; "passthrough" mode: the BEL goes through tmux/byobu to the terminal."""
    if not sys.stdout.isatty():
        return
    screen.write("\x1bPtmux;\a\x1b\\" if mode == "passthrough" else "\a")
    screen.flush()


def is_reportable_error(L, level):
    """--chime: 0 = any error (4xx, 5xx, Odoo ERROR / CRITICAL, traces); 1 = 4xx; 2 = 5xx and 4xx."""
    r = REQUEST_RE.search(L.text or "")
    if r:
        code = int(r.group(2))
        return 400 <= code < 600 if level in (0, 2) else 400 <= code < 500
    return level == 0 and (L.level in ("ERROR", "CRITICAL") or "Traceback (most recent call last)" in (L.text or ""))


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


def vcmd(cmd):
    if VERBOSE:
        eprint("+ " + shlex.join(cmd))


def lancer(cmd, delay=10):
    """Output of a short command (empty string if absent, failing or too long)."""
    vcmd(cmd)
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=delay, universal_newlines=True, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return r.returncode, r.stdout


def privileged(cmd):
    """1.100: a command that needs root (fail2ban-client, ipset, journalctl of a protected log…): run as it is under root, through « sudo -n » otherwise
    (never a password question; without sudo, the command runs as it is and fails as it would)."""
    if os.geteuid() == 0 or shutil.which("sudo") is None:
        return cmd
    return ["sudo", "-n"] + cmd


def lancer_root(cmd, delay=10):
    """lancer() for the advanced commands that need root: see privileged()."""
    return lancer(privileged(cmd), delay)


def load_module(name):
    """Component of apps/ (None if absent): never a stop because of a missing component."""
    path = os.path.join(SCRIPT_DIR, "apps", name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



# ------------------------------------------------------------------------------------------------------------------
# IP addresses of a text
# ------------------------------------------------------------------------------------------------------------------
def new_anonymiser(module):
    """1.91: Anonymiseur of apps/_anonymiser.py for the screen — aligned IP pseudonyms (fixed_width) and the names of people of KNOWN_NAMES (membre-xxxxxx);
    an older module without these parameters still anonymizes the addresses and e-mails."""
    parameters = module.Anonymiseur.__init__.__code__.co_varnames
    kwargs = {"fixed_width": True} if "fixed_width" in parameters else {}
    if "names" in parameters:
        kwargs.update(names=KNOWN_NAMES, names_lock=KNOWN_NAMES_LOCK)
    return module.Anonymiseur(**kwargs)


def find_ips(text_line):
    """[(start, end, ip)] of the IPv4 and IPv6 addresses of the text (IPv6 validated: "03:02:14" is not one)."""
    found_items = [(m.start(), m.end(), m.group()) for m in IPV4_RE.finditer(text_line)]
    for m in IPV6_RE.finditer(text_line):
        text = m.group()
        if ":" not in text or any(d <= m.start() < f for d, f, _ in found_items):
            continue
        try:
            ipaddress.IPv6Address(text)
        except ValueError:
            continue
        found_items.append((m.start(), m.end(), text))
    return sorted(found_items)


# ------------------------------------------------------------------------------------------------------------------
# A journal line, parsed
# ------------------------------------------------------------------------------------------------------------------
DATA_URI_RE = re.compile(r"(data:[\w/+.-]+;base64,)[A-Za-z0-9+/=]{20,}'?")
# Secrets in the lines (Google access token in /auth_oauth/signin?...access_token=..., password, reset token...): their VALUE is never displayed or counted;
# Odoo's own journal is not modified. "token_type=Bearer" is not a secret.
# LINEAR-time expressions: never a nested repetition or a prefix "(word_)*" (on a long line of words_separated_by_underscores, 1.54 took seconds,
# then minutes: the live display stopped). The keyword is searched directly; what precedes it ("access_") does not need to be read: only the value is replaced.
SECRET_WORD = r"(?:token|password|passwd|secret|api_?key)(?:_(?!type\b)[A-Za-z]{1,20}){0,3}"      # BOUNDED suffix: constant work per keyword
SECRET_PARAM_RE = re.compile(r"(" + SECRET_WORD + r")=([^&\s\"'#;<>]+)", re.I)
SECRET_JSON_RE = re.compile(r"(" + SECRET_WORD + r"[\"']\s*:\s*[\"'])([^\"']+)([\"'])", re.I)
SECRET_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.I)
SECRET_HINT_RE = re.compile(r"token|password|passwd|secret|api_?key|bearer", re.I)
SECRET_MASK = "***"


def mask_secrets(text):
    """Replaces with *** the value of access_token=, token=, password=, … (URL or form parameters, JSON / Python dict, "Bearer …")."""
    if not SECRET_HINT_RE.search(text):
        return text
    text = SECRET_PARAM_RE.sub(lambda m: m.group(1) + "=" + SECRET_MASK, text)
    text = SECRET_JSON_RE.sub(lambda m: m.group(1) + SECRET_MASK + m.group(3), text)
    return SECRET_BEARER_RE.sub(lambda m: m.group(1) + SECRET_MASK, text)

MIN_DEFAULT = True                                                    # 1.98: --min by default (MIN key of the configuration file; --no-min: everything)
HIGHLIGHT_DEFAULT = "POST,webclient,discuss,avatar,20-ans,21-ans,portes,ouvertes,-2026-"      # --highlight / HIGHLIGHT: words highlighted in cyan (comma = several)
SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def modify_highlight(database, text):
    """"+word" ADDS a word to the `base` list, "-word" REMOVES it (case-insensitive); several separated by a comma or a space ("+odoo -POST +20-ans").
    Words without a sign in an input that contains + or - are added. Returns the new list, or None if the input has neither "+" nor "-" at the start
    (it is then a complete list that REPLACES the old one). 1.88: a word that starts AND ends with "-" (« -2026- ») is a word, not a removal: « --2026- » removes it."""
    words = [m for m in re.split(r"[,\s]+", text.strip()) if m]

    def removal(m):
        return len(m) > 1 and m[0] == "-" and not (len(m) > 2 and m[-1] == "-" and m[1] != "-")
    if not any((m[0] == "+" and len(m) > 1) or removal(m) for m in words):
        return None
    items = list(database)
    for m in words:
        if removal(m):
            items = [x for x in items if x.lower() != m[1:].lower()]
        else:
            word = m[1:] if m[0] == "+" else m
            if word and word.lower() not in [x.lower() for x in items]:
                items.append(word)
    return items


def config_values(options, verbose, widths=None):
    """{KEY: text} of ALL the settings that can be changed on the fly (menu) that have a key in SCHEMA_CONFIG, as they would be written in app-log-live.conf
    (an empty value = "no setting": option not touched at the next launch). `widths` = (NAME_WIDTH, NAME_TRUNCATE)."""
    yes_no = lambda b: "yes" if b else "no"
    sort_by = options["modules_sort"]
    width, truncated = widths if widths else (None, None)
    res = {"HEALTH": f"{options['health']:g}", "HIDE_ADDONS": yes_no(options.get("hide_addons")), "HIDE_IP": yes_no(not options["keep_ip"]), "HIDE_USER_AGENT": yes_no(options.get("hide_user_agent")), "REQUEST_LENGTH": yes_no(options.get("request_length")), "HIGHLIGHT": ",".join(options["highlight_words"]) or "none",
           "LEVEL": str(options["level"]), "MIN": yes_no(options["minimal"]), "MODULES_CUSTOM": yes_no(sort_by[2]), "MODULES_SORT": ("-" if sort_by[1] else "") + sort_by[0],
           "NOT_FOUND": yes_no(options["not_found"]), "VERBOSE": yes_no(verbose),
           "ACCENTUATE_GROUP": options.get("group") or "", "CHIME": "" if options.get("chime") is None else str(options["chime"]),
           "EXCLUDE_IP": ",".join(str(r) for r in options.get("exclude") or []), "ONLY": ",".join(options.get("only") or []),
           "STEPS_LINE": yes_no(options.get("steps_line")), "UNDERLINE": str(options.get("underline", UNDERLINE_DEFAULT)), "SUSPECT": yes_no(options.get("suspect")), "ANONYMIZE": yes_no(options.get("anonymize")), "TIME_REPORT": f"{options.get('report_min') or 0:g}", "WATCH": ",".join(options.get("watch") or [])}
    if width is not None:
        res["DNS_MAX"] = "" if truncated else str(width)                    # one or the other: column without cut, or cut at N
        res["DNS_MAX_TRUNCATE"] = str(truncated) if truncated else ""
    return res


def config_changes(current_one, start_state):
    """{KEY: text} of only the values that differ from those at startup."""
    return {k: v for k, v in current_one.items() if start_state.get(k) != v}


def system_config_path(program_name=None):
    """/etc/default/app-log-live.conf (NGINX_TOOLS_ETC_DEFAULT: another folder, tests)."""
    return os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), f"{program_name or SCRIPT_NAME}.conf")


def config_merge(explicit=None):
    """1.125 --config-merge: the file read until now (or `explicit`) is rewritten from the NEW default configuration (doc/LANGUAGE/PROGRAM.conf.example),
    keeping the values set (uncommented) in it. Keys unknown to the program are left out and listed. The old file is copied first to
    FILE.bak-YYYYMMDD-HHMMSS (local time). Returns 0, or 1 when the example is missing or the file cannot be written."""
    cfg_lib = load_module("_config")
    if explicit:
        files = [explicit] if os.path.isfile(explicit) else []
        target = explicit
    else:
        files = [c for c, existe in cfg_lib.chemins_regle(SCRIPT_NAME) if existe] if cfg_lib else []
        target = files[-1] if files else cfg_lib.personnel(SCRIPT_NAME) if cfg_lib else os.path.expanduser(f"~/.{SCRIPT_NAME}.conf")
    old = {}
    for c in files:
        old.update(cfg_lib.lire_fichier(c) if cfg_lib else {})
    model = os.path.join(SCRIPT_DIR, "doc", "fr" if LANGUAGE == "fr" else "en", f"{SCRIPT_NAME}.conf.example")
    try:
        with open(model, encoding="utf-8") as f:
            model_lines = f.read().splitlines()
    except OSError:
        eprint(TR("Example configuration not found: {path}").format(path=model))
        return 1
    known = set(SCHEMA_CONFIG) | set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)\s*=", "\n".join(model_lines), re.M))
    kept = {k: v for k, v in old.items() if k in known}
    dropped = sorted(k for k in old if k not in known)
    backup, mode = None, 0o644
    try:
        if os.path.isfile(target):
            mode = os.stat(target).st_mode & 0o777
            backup = f"{target}.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}"
            shutil.copy2(target, backup)
        write_lines(target, apply_values(model_lines, kept), mode)
    except OSError as e:
        eprint(TR("Cannot write {path}: {error}").format(path=target, error=e))
        return 1
    print(TR("Configuration merged into {path}").format(path=target))
    print(TR("  read: {files}").format(files=", ".join(files) if files else TR("none (new file)")))
    print(TR("  new default configuration: {path}").format(path=model))
    print(TR("  backup of the previous file: {path}").format(path=backup or TR("none")))
    print(TR("  values kept: {n}").format(n=len(kept)) + (f" ({', '.join(sorted(kept))})" if kept else ""))
    if dropped:
        print(TR("  unknown keys left out: {keys}").format(keys=", ".join(dropped)))
    return 0


def write_config(path, values):
    """Updates `path`: the active line KEY=… is replaced; otherwise the first commented line #KEY=… is activated; otherwise KEY=… is added at the end. The other lines
    (comments included) are kept as they are. File absent: copy of doc/PROGRAM.conf.example (if it exists). Written through a temporary file then
    replacement; the rights of an existing file are kept (644 for a new one). OSError if impossible. Returns the number of keys written."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        model = os.path.join(SCRIPT_DIR, "doc", "en", f"{SCRIPT_NAME}.conf.example")
        try:
            with open(model, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        mode = 0o644
    write_lines(path, apply_values(lines, values), mode)
    return len(values)


def apply_values(lines, values):
    """1.125: the lines of a configuration file with {KEY: value} applied (see write_config); the lines are not written here."""
    lines = list(lines)
    for key_value, value in values.items():
        text = f'"{value}"' if value != value.strip() or "#" in value else value
        new_one = f"{key_value}={text}"
        active_ones = [i for i, l in enumerate(lines) if re.match(rf"\s*{key_value}\s*=", l)]
        commented = [i for i, l in enumerate(lines) if re.match(rf"\s*#\s*{key_value}\s*=", l)]
        if active_ones:
            lines[active_ones[-1]] = new_one
        elif commented:
            lines[commented[0]] = new_one
        else:
            lines.append(new_one)
    return lines


def write_lines(path, lines, mode=0o644):
    """1.125: writes the lines to `path` through a temporary file, then replacement; rights `mode`. OSError if impossible."""
    temp = f"{path}.tmp{os.getpid()}"
    try:
        with open(temp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(temp, mode)
        os.replace(temp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def read_highlight(text, database=None):
    """"POST, webclient,…" -> list of words. Empty, "none", "no" or "non": no word. "+word -word": modifies the default list (or `base`)."""
    if text is None:
        return [m.strip() for m in HIGHLIGHT_DEFAULT.split(",") if m.strip()]
    modified = modify_highlight([m.strip() for m in HIGHLIGHT_DEFAULT.split(",")] if database is None else database, text)
    if modified is not None:
        return modified
    words = [m.strip() for m in text.split(",") if m.strip()]
    return [] if [m.lower() for m in words] in (["none"], ["aucun"], ["non"]) else words


def highlight_pattern(words):
    """Expression of the words: upper/lower case ignored, EXCEPT a word written ALL IN CAPITALS (POST) which must also be so in the line (otherwise "post" would highlight postgres)."""
    if not words:
        return None
    return re.compile("|".join((f"(?-i:{re.escape(m)})" if len(m) > 1 and m.isupper() else f"(?i:{re.escape(m)})") for m in sorted(set(words), key=len, reverse=True)))


def highlight_text(text, pattern, code=None):
    """Words of the pattern in black on a cyan background. Never touches the color codes of the line: after each word, the current color is restored. Without color (pipe): text unchanged."""
    if pattern is None or not COLOR:
        return text
    code = code or STYLES["highlight"]
    sortie_, pos, active = [], 0, ""
    for m in SGR_RE.finditer(text):
        segment = text[pos:m.start()]
        sortie_.append(pattern.sub(lambda t: f"\x1b[{code}m{t.group(0)}\x1b[0m" + (f"\x1b[{active}m" if active else ""), segment))
        sortie_.append(m.group(0))
        pos = m.end()
        active = "" if m.group(1) in ("", "0") else (active + ";" if active else "") + m.group(1)
    sortie_.append(pattern.sub(lambda t: f"\x1b[{code}m{t.group(0)}\x1b[0m" + (f"\x1b[{active}m" if active else ""), text[pos:]))
    return "".join(sortie_)

BASE64_BLOCK_RE = re.compile(r"[A-Za-z0-9+/=]{60,}'?$")


NGINX_ERROR_TAG_RE = re.compile(r"^\[(\w+)\] ")                              # 1.116: "[error] ..." at the start of an nginx error line
NGINX_LEVELS = {"emerg": "CRITICAL", "alert": "CRITICAL", "crit": "CRITICAL", "error": "ERROR", "warn": "WARNING"}


class Line:
    """Fields of a line: time (local ISO text and instant), machine, program, level, database, logger, and the message TEXT
    (cleaned: without werkzeug's redundant date). Line without a recognized header (BigBlueButton): everything is in "text"."""
    def __init__(self, raw_line):
        raw_line = DATA_URI_RE.sub(r"\1[… base64 omis]", raw_line)                  # image pasted in an e-mail: never thousands of characters on screen
        raw_line = mask_secrets(raw_line)                                          # access token, password...: never displayed
        self.raw_line = raw_line
        self.ts_txt = self.instant = self.host_name = self.program_name = self.level = self.database = self.logger = None
        self.text = raw_line
        self.odoo_times = None                                                     # 1.123 --log-merge: (SQL queries, SQL time, Python time) of the Odoo line of the same request
        self._analyze(raw_line)
        self.nginx_fields()
        block = BASE64_BLOCK_RE.match((self.text or "").strip())
        if block:                                                                   # continuation of a long line cut by the journal: a simple base64 block
            self.text = f"[… {len(self.text.strip())} base64 characters omitted]"

    def _analyze(self, raw_line):
        m = JOURNAL_RE.match(raw_line)
        if not m:
            return
        a, mo, j, h, mi, s, us, offset, minutes, self.host_name, self.program_name, message = m.groups()
        try:
            timezone = datetime.timezone(datetime.timedelta(hours=int(offset), minutes=(-1 if offset[0] == "-" else 1) * int(minutes or 0)))
            dt = datetime.datetime(int(a), int(mo), int(j), int(h), int(mi), int(s), int(us), tzinfo=timezone)
        except ValueError:
            return
        rounded = dt + datetime.timedelta(microseconds=5000)                      # hundredths rounded (326 ms -> .33)
        if TIME_UTC:                                                              # 1.112 --utc: shown in UTC
            rounded = rounded.astimezone(datetime.timezone.utc)
        self.ts_txt = f"{rounded:%Y-%m-%d %H:%M:%S}.{rounded.microsecond // 10000:02d}"
        self.instant = dt.timestamp()
        self.text = message
        o = ODOO_RE.match(message)
        if o:
            self.level, self.database, self.logger, self.text = o.groups()
            if self.logger == "werkzeug":
                w = WERKZEUG_DATE_RE.match(self.text)
                if w:
                    self.text = w.group(1) + w.group(2)
            w = DATE_ISO_RE.match(self.text)                               # websockets ("longpolling" logger or werkzeug): ISO date
            if w and self.same_instant(w, dt):
                self.text = w.group(1) + w.group(8)

    def nginx_fields(self):
        """1.116: a line of an nginx log (program "http", merged by apps/_logs_merge.py) gets the fields of an Odoo line: level INFO,
        database "nginx" and logger "request" (13 characters, like "base werkzeug": the name starts at the same column as in Odoo),
        or, for an error line, the level of its [error] / [warn] tag and logger "error". Without these fields the address would not be in
        the address column (country, address) and the names would not be aligned with the Odoo lines."""
        if self.program_name != "http" or self.level is not None or self.text is None:
            return
        m = NGINX_ERROR_TAG_RE.match(self.text)
        if m:
            self.level, self.database, self.logger = NGINX_LEVELS.get(m.group(1), "INFO"), "nginx", "error"
        else:
            self.level, self.database, self.logger = "INFO", "nginx", "request"

    @staticmethod
    def same_instant(w, dt):
        """True if the date "[YYYY-MM-DD HH:MM:SS]" found in the message (UTC, or local time of the line) is the same instant as the time of the line (within 2 s)."""
        try:
            was_read = [int(x) for x in w.group(2, 3, 4, 5, 6, 7)]
            in_utc = datetime.datetime(*was_read, tzinfo=datetime.timezone.utc)
            as_local = datetime.datetime(*was_read, tzinfo=dt.tzinfo)
        except ValueError:
            return False
        return min(abs((in_utc - dt).total_seconds()), abs((as_local - dt).total_seconds())) <= 2

    def err(self):
        """Error or warning line: never discarded by --min."""
        return self.level in ("WARNING", "ERROR", "CRITICAL") or bool(re.search(r"Traceback|Exception|Error", self.text or ""))

    def discard_in_min(self):
        return (self.level in ("INFO", "DEBUG") and not self.err()
                and bool(MIN_EXCLUDED_RE.match(f"{self.logger}: {self.text}")))

    def discard_addons(self):
        """--hide-addons: INFO / DEBUG line of an Odoo module (logger odoo.addons.*) discarded, EXCEPT errors, e-mails sent and generated files (PDF…)."""
        return (self.level in ("INFO", "DEBUG") and (self.logger or "").startswith("odoo.addons.") and not self.err()
                and not ADDONS_KEEP_RE.search(f"{self.logger}: {self.text}"))


# ------------------------------------------------------------------------------------------------------------------
# What is known about an address
# ------------------------------------------------------------------------------------------------------------------
INFO_RE = re.compile(r"(?P<chemin>/[\w.@+/-]+)|(?P<num>(?<![\w.-])\d+(?:[.,]\d+)?(?: ?(?:%|[KMGT]o\b))?(?!\w))")


def color_info(text):
    """Startup information line ("Lists: …", "Address cache: …"): the label before ":" in bold, file paths in cyan, numbers and their unit in bold cyan."""
    tag, sep, remaining = text.partition(" : ")
    if not sep:
        tag, sep, remaining = "", "", text
    remaining = INFO_RE.sub(lambda m: color_code("36", m.group("chemin")) if m.group("chemin") else color_code("1;36", m.group("num")), remaining)
    return (color_code("1", tag) + sep if tag else "") + remaining


def open_cache():
    """Permanent address cache (apps/_cache_ip.py): an address is looked up only once; purge of the addresses not seen again for 180
    days (privacy); the "Address cache: …" line goes to the error output. None if the component is missing or if the cache is disabled."""
    module = load_module("_cache_ip")
    if module is None:
        eprint("Address cache: component apps/_cache_ip.py missing")
        return None
    cache = module.ouvrir()
    if not cache.actif:
        eprint(TR("Address cache: disabled") if cache.raison == "désactivé" else TR("Address cache: unusable") + cache.raison.partition("inutilisable")[2])
        return None
    purged = cache.purger()
    eprint(color_info(cache.resume() + (f" — {purged} address(es) not seen again for {module.RETENTION_JOURS} days deleted" if purged else "")))
    return cache


def read_lists():
    """Whitelist and places (/etc/default/nginx-tools-*.conf, apps/_listes.py); the "Lists: …" line goes to the error output.
    None if the component is missing (no list: never a stop)."""
    module = load_module("_listes")
    if module is None:
        eprint("Lists: component apps/_listes.py missing")
        return None
    lists = module.charger(os.path.join(SCRIPT_DIR, "apps"))
    eprint(color_info(lists.resume()))
    for problem in lists.problemes:
        eprint(TR("  WARNING {problem}").format(problem=problem))
    return lists


def short_caption(caption):
    """"Étienne (Vidéotron mobile, current address — may change)" -> "Étienne (Vidéotron mobile, current address)":
    the remark after "—" is a comment of the list, not part of the name."""
    caption = caption.strip()
    short = re.sub(r"\s+—\s+[^)]*(?=\))", "", caption)             # remark inside a closed parenthesis
    short = re.sub(r"\s+—\s+.*$", "", short)                          # remaining remark (outside a parenthesis, or an unclosed parenthesis)
    return short.strip() or caption


_CACHE_IO = {"t": 0.0, "v": None}


def io_wait():
    """(disk wait in %, "some" I/O pressure over 10 s in % or None): % of the processors' time spent waiting for the disk during ~0.3 s (iowait field of /proc/stat), and the kernel's
    I/O pressure (/proc/pressure/io, if the kernel offers it). Memorized 30 s (the sample makes us wait 0.3 s). None if /proc/stat is unreadable."""
    if time.time() - _CACHE_IO["t"] < 30:
        return _CACHE_IO["v"]

    def cpu():
        with open("/proc/stat", encoding="ascii") as f:
            field_list = [int(x) for x in f.readline().split()[1:]]
        return sum(field_list), field_list[4]
    try:
        t0, w0 = cpu()
        time.sleep(0.3)
        t1, w1 = cpu()
        iowait = 100.0 * (w1 - w0) / (t1 - t0) if t1 > t0 else 0.0
        psi = None
        try:
            with open("/proc/pressure/io", encoding="ascii") as f:
                m = re.search(r"some .*?avg10=([\d.]+)", f.read())
            psi = float(m.group(1)) if m else None
        except (OSError, ValueError):
            pass
        value = (iowait, psi)
    except (OSError, ValueError, IndexError):
        value = None
    _CACHE_IO.update(t=time.time(), v=value)
    return value


def md_rotational(name):
    """Type of a software RAID array (mdN): True if all its member disks are spinning disks, False if all are SSD, None if unknown or mixed.
    The members come from /sys/block/mdN/slaves (sda3 -> sda, nvme0n1p2 -> nvme0n1); 1.94: an array was typed « ? » before."""
    kinds = set()
    for member in glob.glob(f"/sys/block/{name}/slaves/*"):
        base = re.sub(r"p?\d+$", "", os.path.basename(member))
        try:
            with open(f"/sys/block/{base}/queue/rotational", encoding="ascii") as f:
                kinds.add(f.read().strip() == "1")
        except OSError:
            return None
    return kinds.pop() if len(kinds) == 1 else None


def physical_disks():
    """[(name, rotational)] of the physical disks (/sys/block/*/queue/rotational: 1 = spinning hard disk, 0 = SSD / NVMe) and of the RAID arrays (mdN, type of their
    members, 1.94: they were left out of the « disks » line of the latency report); without virtual disks (loop, ram, zram, dm-, sr, fd, nbd)."""
    res = []
    try:
        names = sorted(os.listdir("/sys/block"))
    except OSError:
        return res
    for name in names:
        if name.startswith(("loop", "ram", "zram", "dm-", "sr", "fd", "nbd")):
            continue
        if name.startswith("md"):
            raid_hdd = md_rotational(name)
            if raid_hdd is not None:
                res.append((name, raid_hdd))
            continue
        try:
            with open(f"/sys/block/{name}/queue/rotational", encoding="ascii") as f:
                res.append((name, f.read().strip() == "1"))
        except OSError:
            continue
    return res


def read_state():
    """State of the server at this instant read from /proc and /sys: {load, cores, swap_mb, mem_gb, io (disk wait %, I/O pressure % or None) or None, disks [(name, rotational)]}; None if /proc is unreadable."""
    try:
        with open("/proc/loadavg", encoding="ascii") as f:
            load = float(f.read().split()[0])
        meminfo = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for text_line in f:
                key_value, _, remaining = text_line.partition(":")
                meminfo[key_value] = int(remaining.split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return {"load": load, "cores": os.cpu_count() or 1, "swap_mb": (meminfo.get("SwapTotal", 0) - meminfo.get("SwapFree", 0)) // 1024,
            "mem_gb": meminfo.get("MemAvailable", 0) / 1048576, "io": io_wait(), "disks": physical_disks()}


def system_state(state=None):
    """"load 1.2 on 4 core(s) · swap used 120 MB · memory available 3.1 GB · disk wait 4 % … · disks: sda hard disk"; empty string if /proc is unreadable. ZFS volumes
    (zd0, zd16…) are grouped: their "SSD" indicator says nothing about the type of the pool's disks."""
    state = state or read_state()
    if not state:
        return ""
    text = TR("load {load:.1f} out of {cores} cores · swap used {swap} MB · memory available {mem:.1f} GB").format(
        load=state["load"], cores=state["cores"], swap=state["swap_mb"], mem=state["mem_gb"])
    io = state["io"]
    if io is not None:
        text += f" · disk wait {io[0]:.0f} %" + (f" (I/O pressure over 10 s: {io[1]:.0f} %)" if io[1] is not None else "")
    zfs = [name for name, _ in state["disks"] if re.fullmatch(r"zd\d+", name)]
    others = [(name, rotatif) for name, rotatif in state["disks"] if name not in zfs]
    chunks = [f"{name} {'hard disk (spinning)' if rotatif else 'SSD'}" for name, rotatif in others]
    if zfs:
        chunks.append(f"{len(zfs)} ZFS volumes (real type: that of the pool disks)")
    if chunks:
        text += " · disks: " + ", ".join(chunks)
    return text


def python_conclusion(state):
    """What the server state says about a time that is almost entirely in Python: the retained causes (load, swap, disk) or, if none, those that remain (cold cache, lock, computation)."""
    causes_list = []
    if state["load"] >= state["cores"]:
        causes_list.append("server saturated (load equal to or above the number of cores)")
    if state["swap_mb"] >= 100:
        causes_list.append("memory full (swap in use)")
    io = state["io"]
    if io is not None and (io[0] >= 10 or (io[1] is not None and io[1] >= 10)):
        causes_list.append("disk too slow (disk wait of 10% or more: attachments, logs, swap and the final transaction write are counted as Python)")
    if causes_list:
        return "probable causes: " + " ; ".join(causes_list)
    return ("load, swap and disk are NOT the cause at this moment; what remains: cold Odoo cache (assets, compiled views: after a restart, a module update or a view change), a lock, or heavy computation in a module (profiling: developer mode, bug icon -> Profiling)")


def cut_words(text, limit):
    """Text cut at `limit` characters, at a word boundary, with « … » at the end; unchanged if it fits (1.94: an Odoo message was cut in the middle of its identifier)."""
    if len(text) <= limit:
        return text
    head = text[:limit - 1]
    if " " in head:
        head = head[:head.rfind(" ")]
    return head.rstrip() + " …"


def clock_of(instant):
    """Local date and time of a journal line, to the second (2026-10-20 23:50:37): the slow requests show it (1.94)."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(instant))


def short_url(url, width=60):
    """URL shortened in the MIDDLE ("/event/journee…/registration"): the end (the requested action) stays readable."""
    if len(url) <= width:
        return url
    start = (width - 1) // 2
    return url[:start] + "…" + url[len(url) - (width - 1 - start):]


def read_agents(agents, patterns, folder, lines=200000):
    """Background thread: follows the nginx access journals (tail -F, history included) and memorizes the first User-Agent of each address. Silent if the journals are unreadable.
    Returns the tail process (to terminate at the end) or None."""
    files_read = []
    for pattern in (patterns or "").split():
        files_read += sorted(glob.glob(os.path.join(folder, pattern)))
    files_read = [f for f in OrderedDict.fromkeys(files_read) if os.path.isfile(f) and os.access(f, os.R_OK)]
    if not files_read:
        return None
    try:
        proc = subprocess.Popen(["tail", "-n", str(lines), "-F"] + files_read, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                universal_newlines=True, errors="replace", start_new_session=True)
    except OSError:
        return None

    def reader():
        for raw_line in proc.stdout:
            m = ACCESS_AGENT_RE.match(raw_line)
            if m and m.group(1) not in agents and len(agents) < AGENTS_MAX:
                agents[m.group(1)] = m.group(2)[:200]
    threading.Thread(target=reader, daemon=True).start()
    return proc


def thread_stacks(names=None):
    """Call stack (text) of the threads of the program, to find what blocks."""
    import traceback
    chunks = []
    for thread in threading.enumerate():
        if names and thread.name not in names and not (thread is threading.main_thread() and "main" in names):
            continue
        box = sys._current_frames().get(thread.ident)
        if box is not None:
            chunks.append(f"--- thread '{thread.name} ' ---\n" + "".join(traceback.format_stack(box)[-12:]))
    return "\n".join(chunks)


WATCHDOG_DELAY = float(os.environ.get("APP_LOG_LIVE_WATCHDOG", "8"))      # seconds without progress before the watchdog alert (0: disabled)


INTERACTIVE = [0]        # > 0: the main thread is deliberately waiting for an answer (question, investigation, ban) - the watchdog keeps quiet


@contextlib.contextmanager
def interaction():
    """Around an action that questions the user or launches an interactive program: the display loop stops on purpose, it is not a failure."""
    INTERACTIVE[0] += 1
    try:
        yield
    finally:
        INTERACTIVE[0] -= 1


def start_watchdog(proc, file, state, received, reader_thread):
    """Live watchdog: if the display no longer follows while lines are waiting, writes ONE alert (on the error output) with the stack of the blocked thread. Two cases:
    lines are ready in the journal pipe but the reader thread does not take them (it is blocked); or lines are read but the display loop does not process them.
    Also: kill -USR1 PID writes the stack of all threads, at any time."""
    import faulthandler
    import select
    if hasattr(signal, "SIGUSR1"):
        with contextlib.suppress(Exception):
            faulthandler.register(signal.SIGUSR1, all_threads=True)

    def keep_watch():
        last_seen = {"received": -1, "read_files": -1, "t": time.time(), "alert": False}
        while proc.poll() is None:
            time.sleep(1.0)
            if not WATCHDOG_DELAY:
                return
            try:
                ready = bool(select.select([proc.stdout], [], [], 0)[0])
            except (OSError, ValueError):
                return
            waiting = file.qsize()
            if INTERACTIVE[0]:                                  # question in progress: the wait is intended
                last_seen.update(t=time.time(), alert=False)
                continue
            progress = received[0] != last_seen["received"] or state["read_files"] != last_seen["read_files"]
            last_seen.update(received=received[0], read_files=state["read_files"])
            if progress or not (ready or waiting):
                last_seen.update(t=time.time(), alert=False)
                continue
            if time.time() - last_seen["t"] >= WATCHDOG_DELAY and not last_seen["alert"]:
                last_seen["alert"] = True
                case = ("the journal has lines ready but the reader thread does not take them" if ready
                       else f"{waiting} lines read are waiting, the display loop does not process them")
                eprint(color_code(ORANGE, TR("⚠ Watchdog ({name} v{version}) : no progress for {delay} s — {case}. Stack of the blocked thread (copy it):").format(name="app-log-live", version=__version__, delay=f"{WATCHDOG_DELAY:g}", case=case)))
                eprint(thread_stacks(("reader",) if ready else ("main",)))
    threading.Thread(target=keep_watch, daemon=True, name="watchdog").start()


def local_address(ip):
    """Loopback address (127.0.0.0/8, ::1)?"""
    try:
        return ipaddress.ip_address(ip.split("%")[0]).is_loopback
    except ValueError:
        return False


# 1.91: names of people (logged-in accounts) and team labels shown by this program -> (prefix, stable key). Given to apps/_anonymiser.py: with --anonymize
# they become "membre-4f2a9c" / "equipe-4f2a9c" on screen (the daily journal keeps them). Logins that are not a person are never registered.
KNOWN_NAMES = {}
KNOWN_NAMES_LOCK = threading.Lock()
NOT_A_PERSON = {"admin", "administrator", "administrateur", "public", "__system__", "odoobot", "demo", "portal", "default"}


def note_name(name, key, prefix="membre"):
    """Registers a name shown on screen (anonymized by --anonymize); ignored when shorter than 3 characters, an e-mail (anonymized on its own) or a technical login."""
    name = (name or "").strip()
    if len(name) < 3 or "@" in name or name.lower() in NOT_A_PERSON:
        return
    with KNOWN_NAMES_LOCK:
        KNOWN_NAMES.setdefault(name, (prefix, key))


def version_with_date():
    """"app-log-live version 1.40.20261013.100000 (2026-10-13 10:00:00)": the local date and time of the modification are in the version number."""
    m = re.match(r"^(\d+\.\d+)\.(\d{4})(\d{2})(\d{2})\.(\d{2})(\d{2})(\d{2})$", __version__)
    when = f" ({m.group(2)}-{m.group(3)}-{m.group(4)} {m.group(5)}:{m.group(6)}:{m.group(7)})" if m else ""
    return f"{SCRIPT_NAME} version {__version__}{when}"


def server_addresses():
    code, output = lancer(["hostname", "-I"], 5)
    return set(output.split()) if code == 0 else set()


# External (public) IP address of this server: the whitelists and other /etc/default files sometimes contain it.
# If it changes (internet provider, router restart), these files are no longer up to date: it is displayed, with the files to fix.
EXTERNAL_IP_SERVICE = "ifconfig.me"


def external_ip():
    """External IP address according to "curl ifconfig.me"; None if unreachable or if the answer is not an address."""
    code, output = lancer(["curl", "-s", "--max-time", "6", EXTERNAL_IP_SERVICE], 10)
    try:
        return str(ipaddress.ip_address(output.strip())) if code == 0 else None
    except ValueError:
        return None


def external_ip_file():
    """File where the last known external address is memorized (from one run to the next); variable APP_LOG_LIVE_STATE_DIR to change it."""
    for folder in (os.environ.get("APP_LOG_LIVE_STATE_DIR"), "/var/lib/app-log-live", os.path.join(os.path.expanduser("~"), ".cache", "app-log-live")):
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
                if os.access(folder, os.W_OK):
                    return os.path.join(folder, "ip-externe.txt")
            except OSError:
                continue
    return None


def files_with_ip(ip, folder=None):
    """Files of /etc/default (variable APP_LOG_LIVE_DEFAULT_DIR for the tests) that contain this address."""
    folder = folder or os.environ.get("APP_LOG_LIVE_DEFAULT_DIR", "/etc/default")
    pattern, found_list = re.compile(r"(?<![\w.:])" + re.escape(ip) + r"(?![\w.:])"), []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return found_list
    for name in names:
        path = os.path.join(folder, name)
        try:
            if os.path.isfile(path) and pattern.search(open(path, encoding="utf-8", errors="replace").read()):
                found_list.append(path)
        except OSError:
            continue
    return found_list


def ip_change_message(old_one, new_one):
    """Warning lines when the external address goes from old to new."""
    lines = [f"WARNING the external IP address of this server has changed: {old_one} → {new_one} (according to curl {EXTERNAL_IP_SERVICE})",
              "  The configuration files in /etc/default that contain the old address must be changed:"]
    files_read = files_with_ip(old_one)
    lines += [f"    {f}" for f in files_read] or ["    (no file in /etc/default contains the old address; also check the DNS, the firewall and the allow lists)"]
    return lines


# Local requests (127.0.0.1 or address of the server): the PROGRAM that makes them, according to the requested page. They are the health probes of
# app-health-check.py (launched by web-monitor.py every hour): GET /, POST /web/webclient/version_info, GET /web/health.
LOCAL_PROGRAMS = [(re.compile(r'"(?:GET|POST) (?:/web/health|/web/webclient/version_info|/)(?:\?\S*)? HTTP'), "app-health-check.py")]


def local_program(text):
    """Name of the program of this server that made this local request; None if not recognized."""
    for pattern, name in LOCAL_PROGRAMS:
        if pattern.search(text):
            return name
    return None


class People:
    """Who logged in from which address (Odoo journal), and the name of that person (PostgreSQL, read-only).
    No method called by the stream blocks: the names come from a cache, refreshed in the background."""
    def __init__(self, odoo_db):
        self.odoo_db = odoo_db
        self.par_ip = {}                    # ip -> OrderedDict{(database, login): date}
        self.databases_seen = {}                     # database -> (read instant, {login: {...}} or None)
        self.in_progress = set()               # databases being refreshed
        self.waits = {}                  # database -> [(Future, accounts)]: awaited names
        self.lock = threading.Lock()

    def ajouter(self, ip, database, login, when):
        with self.lock:
            d = self.par_ip.setdefault(ip, OrderedDict())
            d.pop((database, login), None)
            d[(database, login)] = when        # most recent last

    def accounts(self, ip):
        """Accounts known for this address AT THIS INSTANT (copy), from oldest to most recent."""
        with self.lock:
            return list((self.par_ip.get(ip) or {}).keys())

    @staticmethod
    def short(name):
        """"Josée Desrosiers" -> "JoséeD" (first name and initial of the surname); an e-mail login -> the part before "@"."""
        words = (name or "").split("@")[0].split()
        return words[0] + words[-1][0].upper() if len(words) > 1 else (words[0] if words else "")

    def name_of(self, database, login):
        """Name of the person according to the database cache (otherwise their login); does not take the lock (called with or without it).
        1.91: the name, its short form and the login are registered for --anonymize (same pseudonym « membre-xxxxxx » for the three)."""
        table = self.databases_seen.get(database, (0, None))[1]
        name = ((table or {}).get(login) or {}).get("nom") or login
        key = f"{database}:{login}"
        for shown in {name, self.short(name), login}:
            note_name(shown, key)
        return name

    def tag(self, accounts, name):
        """Name of the account(s) behind an address (_tag), followed by « [watched] » or « [banned account] » when one of them is in the register of
        web-monitor.py (--watch-odoo-user, --ban-odoo-user; apps/_odoo_users.py, reread at most every 60 s)."""
        text = self._tag(accounts, name)
        reg = registered_odoo_users()
        logins = {login for _db, login in accounts}
        if logins & set(reg["banned"]):
            return text + " [banned account]"
        if logins & set(reg["watched"]):
            return text + " [watched]"
        return text

    def _tag(self, accounts, name):
        """A single person: their name. Several accounts behind the same address: ALL summarized, the most recent first — "JoséeD+ÉtienneB+JoséD"
        (first name + initial of the surname; "+etc" beyond 6); several accounts of the same person: their name only.
        An account whose name is not known (login only: "admin", "etienne.berube.ing") is only another login of an already
        named person: it is omitted as soon as at least one account has a name (no "ÉtienneB+Administrator+admin" duplicate); the comparison ignores case."""
        shorts, names, nameless = [], [], []
        for database, login in reversed(accounts):
            true_ = self.name_of(database, login)
            c = self.short(true_)
            if not c:
                continue
            if true_ == login:                                    # the name cannot be found: only the login is available
                if c.lower() not in [x.lower() for x in nameless]:
                    nameless.append(c)
                continue
            if c.lower() not in [x.lower() for x in shorts]:
                shorts.append(c)
                names.append(true_)
        if not shorts:                                           # no known name: the logins, for lack of better
            shorts = names = nameless
        if len(shorts) < 2:
            return name if (name and name in names) or not names else names[0]
        return "+".join(shorts[:6]) + ("+etc" if len(shorts) > 6 else "")

    def load(self, database):
        """Reads the users of the database (separate thread), then releases those waiting for a name."""
        table = self.odoo_db.utilisateurs(database) if self.odoo_db is not None else None
        with self.lock:
            self.databases_seen[database] = (time.time(), table)
            self.in_progress.discard(database)
            waits = self.waits.pop(database, [])
        for future, accounts in waits:
            name = ((table or {}).get(accounts[-1][1]) or {}).get("nom") or accounts[-1][1]
            future.set_result(self.tag(accounts, name))

    def preload(self):
        """Names of the people of the databases seen in the history, BEFORE the live stream (no provisional name at startup)."""
        with self.lock:
            databases_seen = sorted({b for d in self.par_ip.values() for b, _ in d})
        for database in databases_seen:
            self.load(database)

    def expected_name(self, accounts):
        """(name, None) immediately when the name is in the cache (or unreadable for less than a minute: the login); otherwise
        (None, Future) resolved as soon as PostgreSQL has answered (read in a separate thread). The stream waits only for that Future, at
        most WAIT_DELAY seconds: no other thread is held."""
        database, login = accounts[-1]
        with self.lock:
            instant, table = self.databases_seen.get(database, (0, None))
            name = ((table or {}).get(login) or {}).get("nom")
            if name or self.odoo_db is None or (instant and time.time() - instant <= 60):
                return self.tag(accounts, name or login), None
            future = Future()
            self.waits.setdefault(database, []).append((future, accounts))
            lancer = database not in self.in_progress
            if lancer:
                self.in_progress.add(database)
        if lancer:
            threading.Thread(target=self.load, args=(database,), daemon=True).start()
        return None, future


def geoip_country(ip):
    """Country code according to the local database (geoiplookup, geoip-bin package); None if absent or if it does not know the address."""
    code, output = lancer(["geoiplookup", ip], 5)
    m = re.search(r"Country Edition: ([A-Z]{2}),", output) if code == 0 else None
    return m.group(1) if m else None


class Resolver:
    """What is known about an address, WITHOUT ever blocking the stream: FAST path (this server, person already logged in, team: nothing
    external, immediate result) then SLOW paths, each in its own threads so that none delays the others:
    DNS (4 threads), block owner via RDAP (2), country (3). Results kept in memory (one lookup per address)."""
    def __init__(self, people, lists, server, with_isp, network, cache=None):
        self.people, self.lists, self.server, self.with_isp, self.reseau = people, lists, server, with_isp, network
        self.cache = cache                                       # permanent address cache (apps/_cache_ip.py) or None
        self.futures, self.pays, self.rdaps = {}, {}, {}
        self.counters = Counter()                               # efficiency: fast, memory, cache, dns, rdap, memory_country, cache_country, country (dashboard)
        self.lock = threading.Lock()
        self.dns_queue, self.isp_queue, self.country_queue = queue.Queue(), queue.Queue(), queue.Queue()
        for target, file, n in ((self._dns, self.dns_queue, 4), (self._isp, self.isp_queue, 2), (self._country, self.country_queue, 3)):
            for _ in range(n):
                threading.Thread(target=target, args=(file,), daemon=True).start()

    def local(self, ip):
        """Address without country or provider lookup: invalid, local loopback, private. (The team is no longer part of it since 1.11, nor the PUBLIC
        addresses of this server since 1.91: their country is also displayed, in front of the address like the others.)"""
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return True
        return a.is_loopback or a.is_private or a.is_link_local

    def category(self, ip):
        """"whitelist" (address of the whitelist), "place" (places file) or None, according to the files only (no lookup); the
        whitelist wins; never for this server."""
        if self.lists is None:
            return None
        try:
            a = ipaddress.ip_address(ip)
            if a.is_loopback or ip in self.server:
                return None
            if self.lists.blanche_de(ip) is not None:
                return "blanche"
            return "place" if self.lists.lieu(ip) is not None else None
        except ValueError:
            return None

    def fast(self, ip):
        """(kind, text, account) immediately, or (Future, account, place, number of accounts) if the person's name is being read, or None if a slow
        lookup is needed. Order: this server, SHARED place (never a person's name), known person (followed by the place if defined), whitelist, other place."""
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return ("unknown", ip, None)
        if a.is_loopback or ip in self.server:                  # never a person: several programs, sometimes a tunnel
            return ("server", "this server", None)
        place = self.lists.lieu(ip) if self.lists is not None else None
        if place is not None and place.partagee:                   # university, office...: several people, the PLACE is named
            return ("place", short_caption(place.libelle or "shared place"), None)
        accounts = self.people.accounts(ip)
        if accounts:
            name, waiting = self.people.expected_name(accounts)
            place_name = short_caption(place.libelle or "place") if place is not None else None
            if waiting is None:
                return ("person", self.with_place(name, place_name, len(accounts)), accounts[-1])
            return waiting, accounts[-1], place_name, len(accounts)  # name being read: (Future, account, place, number of accounts)
        whitelist = self.lists.blanche_de(ip) if self.lists is not None else None
        if whitelist is not None:
            label = short_caption(whitelist.libelle or "team")
            if whitelist.libelle:
                note_name(label, f"team:{label}", "equipe")               # 1.91: a team label is usually a person's name
            return ("team", label, None)
        if place is not None:
            return ("place", short_caption(place.libelle or "place"), None)
        return None

    @staticmethod
    def with_place(name, place, account_count):
        """Address of a (non-shared) place where a person logged in: "Josée Desrosiers | ETS-Université". If several accounts logged in there, we do not know
        who makes THIS request (the journal does not give the user id): the place comes first, "ETS-Université | JoséeD+ÉtienneB"."""
        if not place:
            return name
        return f"{place} | {name}" if account_count > 1 else f"{name} | {place}"

    def future(self, ip):
        """Future of the label (kind, text, account): already resolved for the fast path."""
        r = self.fast(ip)
        if r is not None:
            self.account("fast")
            f = Future()
            if isinstance(r[0], Future):                              # name of the person being read
                waiting, account, place_name, n = r
                waiting.add_done_callback(lambda a, f=f, account=account, place_name=place_name, n=n:
                                          f.set_result(("person", self.with_place(a.result(), place_name, n), account)))
            else:
                f.set_result(r)
            return f
        with self.lock:
            f = self.futures.get(ip)
            new = f is None
            if new:
                f = self.futures[ip] = Future()
        if not new:
            self.account("memory")                                # already requested during this session
        elif self.from_cache(ip, f):                        # known from the cache: immediate result, without any lookup
            self.account("cache")
        else:
            self.account("dns")
            self.dns_queue.put((ip, f))
        return f

    def account(self, name):
        with self.lock:
            self.counters[name] += 1

    def from_cache(self, ip, future):
        """Resolves the future from the permanent cache if the address is known there (true); false if a lookup is needed. DNS name first, then block
        owner; "no DNS name" recently verified: go straight to RDAP (DNS never redone). The cache stays in use with --no-isp
        (no external request)."""
        c = self.cache
        if c is None:
            return False
        c.toucher(ip)
        name = c.ptr(ip)
        if name:
            future.set_result(("dns", name, None))
            return True
        if name is None:
            return False                                         # never looked up (or expired): DNS to do
        memorized = c.rdap(ip)
        if memorized:
            future.set_result(self.block_name(memorized, ip))
            return True
        if self.with_isp and self.reseau is not None:            # DNS without a name, but RDAP not yet known: straight to the RDAP path
            self.rdap(ip).add_done_callback(lambda rf, ip=ip, future=future: future.set_result(self.block_name(rf.result(), ip)))
        else:
            future.set_result(("unknown", ip, None))
        return True

    def country_future(self, ip):
        """Future of the country code, or None for a local address (no lookup)."""
        if self.local(ip):
            return None
        with self.lock:
            f = self.pays.get(ip)
            new = f is None
            if new:
                f = self.pays[ip] = Future()
        if new:
            memorized = self.cache.pays(ip) if self.cache is not None else None
            if memorized:                                         # country known from the cache: immediate
                self.account("country_cache")
                f.set_result(memorized)
            else:
                self.account("country")
                self.country_queue.put((ip, f))
        else:
            self.account("country_memory")
        return f

    def rdap(self, ip):
        with self.lock:
            f = self.rdaps.get(ip)
            if f is None:
                f = self.rdaps[ip] = Future()
                self.counters["rdap"] += 1
                self.isp_queue.put((ip, f))
        return f

    def _dns(self, file):
        while True:
            ip, future = file.get()
            try:
                code, output = lancer(["getent", "hosts", ip], 5)
                field_list = output.split()
                if self.cache is not None and (code == 2 or (code == 0 and len(field_list) >= 2)):
                    self.cache.ecrire_ptr(ip, field_list[1].rstrip(".") if code == 0 else "")      # found, or "no name" (never a network error)
                if code == 0 and len(field_list) >= 2:
                    future.set_result(("dns", field_list[1].rstrip("."), None))
                elif ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_link_local:
                    future.set_result(("unknown", "private network", None))
                elif self.with_isp and self.reseau is not None:   # owner of the block: separate thread, this thread stays free
                    self.rdap(ip).add_done_callback(
                        lambda rf, ip=ip, future=future: future.set_result(self.block_name(rf.result(), ip)))
                else:
                    future.set_result(("unknown", ip, None))
            except Exception as e:                      # never stop the stream for a lookup
                future.set_result(("unknown", f"{type(e).__name__}", None))

    @staticmethod
    def block_name(r, ip):
        """(kind, name, None) according to the RDAP response: "org" = registered organization, "network" = only the technical name of the network
        (sometimes an identifier like "meta-mnt"), "unknown" without a response. It is not necessarily an internet provider."""
        if not r:
            return ("unknown", ip, None)
        if r["organisation"]:
            return ("org", r["organisation"], None)
        return ("reseau", r["reseau"], None)

    def _isp(self, file):
        while True:
            ip, future = file.get()
            try:
                result = self.reseau.fournisseur(ip, cache=self.cache)
            except Exception:
                result = None
            future.set_result(result)

    def _country(self, file):
        while True:
            ip, future = file.get()
            pays = None
            try:
                pays = geoip_country(ip)
                if pays and self.cache is not None:
                    self.cache.ecrire_pays(ip, pays, "geoip")
                if pays is None and self.with_isp and self.reseau is not None:
                    r = self.rdap(ip).result(timeout=30)    # the same RDAP call as for the owner of the block
                    pays = (r or {}).get("pays") or None
            except Exception:
                pays = None
            future.set_result(pays)


LEVEL_WIDTH = 4             # 1.123: the level is shown in 4 characters (LEVEL_SHORT), right-aligned on this width: the country starts at the same column for every level
LEVEL_SHORT = {"CRITICAL": "CRIT", "DEBUG": "DBUG", "ERROR": "ERR", "WARNING": "WARN"}      # 1.123: INFO stays INFO; the names of the logs are unchanged
SIZE_WIDTH = 4              # 1.121: width of the size column: at most 4 characters ("-" for Odoo; 9999, then 2.9k, 600k, 4.5M)
NUMBERS_BLOCK_WIDTH = 40   # (1.133: 4 characters more for the OS column before the GET; 1.123: the protocol is shown as "H1.1") # "H1.1 200    -    21  0.011  0.054  ": from the start of the numbers block to the "GET / POST" (see aligned_request)
COLUMN_WIDTH = 18        # "CC xxx.xxx.xxx.xxx": country code, space, longest IPv4 address (without brackets or comma)


CATEGORY_STYLE = {"blanche": "blanche", "place": "place_ip"}


RLQ_DOMAIN_SUFFIX = ".rencontres-linux.quebec"                   # 1.127: names of the domain are shown with this tag instead
RLQ_TAG = ".RLQ."
def display_url(url):
    """1.128: the URL decoded for the display (%20 -> space). Kept as it was sent when the decoding gives a control character or a quote
    (%0A, %22...): the line would be broken, and those codes are the very thing to see."""
    if "%" not in url:
        return url
    decoded = unquote(url)
    return url if any(ord(c) < 32 or c in '"\\' for c in decoded) else decoded


URL_IN_TEXT_RE = re.compile(r'(https?://[^/\s"]+)([^\s"]*)')      # 1.133: every URL of the text (referer...): the host stays (.RLQ), the path and the query are decoded
OS_CODES = (("AND", re.compile(r"Android", re.I)), ("IOS", re.compile(r"iPhone|iPad|iPod", re.I)),       # 1.133: 3-letter system of the User-Agent (Android before Linux)
            ("WIN", re.compile(r"Windows", re.I)), ("LIN", re.compile(r"Linux", re.I)), ("MAC", re.compile(r"Macintosh|Mac OS X", re.I)))
NGINX_AGENT_RE = re.compile(r'"[^"]*" "([^"]*)"')                  # 1.133: after the request and the size of an nginx line: the referer, then the User-Agent
OS_BLANK = "   "
OS_COLORS = {"LIN": "32", "AND": "36"}                             # 1.136: LIN in green, AND in cyan
RL_WIDTH = 5                                                       # 1.136: width of the request length column (rl=, nginx)
RL_RE = re.compile(r"\srl=(\d+)")


def os_code(agent):
    """1.133/1.134: AND (Android), IOS (iPhone, iPad, iPod), WIN (Windows), LIN (Linux), MAC (macOS) from the User-Agent; OTH for any other
    User-Agent; three blanks without User-Agent (Odoo lines, "-" of nginx)."""
    if not agent or agent.strip() in ("", "-"):
        return OS_BLANK
    for code, pattern in OS_CODES:
        if pattern.search(agent):
            return code
    return "OTH"


def line_fields(plain):
    """1.139: start of the fields DATE, PROG, LEVEL and ADDRESS/NAME in a rendered line (plain text): {label: column}. A field not found is left out."""
    fields = {}
    date = re.match(r"(?:\d{4}-\d\d-\d\d )?\S+", plain)
    end = date.end() if date else 0
    if date:
        fields["DATE"] = 0
    level = re.search(r"(?<=\s)(DEBUG|INFO|WARNING|WARN|ERROR|ERR|CRITICAL|CRIT|ALERT|EMERG|NOTICE|DEB|INF|WAR|CRI|NOT|DBG)(?=\s)", plain[end:])
    if level:
        level_at = end + level.start(1)
        fields["LEVEL"] = level_at
        program = re.search(r"\S+$", plain[:level_at].rstrip())
        if program and program.start() > end:
            fields["PROG"] = program.start()
        after_level = level_at + len(level.group(1))
        address = re.search(r"\S", plain[after_level:])
        if address:
            fields["ADDRESS/NAME"] = after_level + address.start()
    return fields


def column_header(request_length=False, minimal=False, width=COLUMN_WIDTH, columns=None, start=None, plain=None):
    """1.136-1.139: labels of the request columns above the same columns of a rendered Odoo request line (the line given, or a sample rendered with
    the same options). `start`: column of "H1.1" in that line. The four first labels (DATE, PROG, LEVEL, ADDRESS/NAME) sit on the fields of the same
    line; a label that would overlap another one or the numbers block is left out."""
    sample = Formatting(minimal, width, 0.0, False, request_length=request_length).format_value(Line(      # the offsets of the labels: from a GET sample
        '2026-10-31T09:53:27.790000-0400 odoo18 odoo[1]: 2026-10-31 05:53:27,790 1 INFO base werkzeug: 179.201.24.98 - - '
        '[31/Oct/2026 09:53:27] "GET /web/abc?lang=en_CA HTTP/1.1" 303 - 1 0.000 0.002'), {}, False)
    sample_plain = ANSI_RE.sub("", sample)
    sample_start = sample_plain.index("H1.1")
    get_at = sample_plain.index("GET", sample_start)
    os_at = get_at - 4 - sample_start                       # offsets from the start of the numbers block
    get_at -= sample_start
    if plain is None:
        plain = sample_plain
    if start is None:
        start = sample_start
    labels = [(0, "HTTP"), (5, "STA"), (9, "SIZE"), (14, "SQL"), (19, "SQL s"), (26, "PY s")]
    if request_length:
        labels.append((os_at - 6, "RL"))
    labels += [(os_at, "OS"), (get_at, TR("REQUEST"))]
    row = [" "] * (get_at + len(TR("REQUEST")) + 1)
    for offset, label in labels:
        for i, letter in enumerate(label):
            row[offset + i] = letter
    line = [" "] * (start + len(row))
    fields = line_fields(plain)
    for name in ("DATE", "PROG", "LEVEL", "ADDRESS/NAME"):          # 1.139: on the fields of the line, left to right
        at, word = fields.get(name), TR(name)
        if at is None or at + len(word) >= start - 1 or any(line[at + i] != " " for i in range(len(word))):
            continue
        line[at:at + len(word)] = list(word)
    line[start:] = row
    text = "".join(line).rstrip()
    return text[:columns] if columns else text        # 1.137: never wider than the terminal (the labels beyond it are not shown)


def transfer_style(total):
    """1.141: traffic light of the time (SQL + Python, or the duration of a websocket): white under 1 s, green from 1 s to under 3 s,
    yellow from 3 s to 6 s, red above 6 s (None = no colour)."""
    if total < 1:
        return None
    if total < 3:
        return STYLES["transfer_low"]
    return STYLES["transfer_mid"] if total <= 6 else STYLES["transfer_slow"]


RLQ_TEXT_TAG = ".RLQ"                                              # 1.128: the same domain in the text of the lines (referer, host=...)
RLQ_DOMAIN_RE = re.compile(r"(\.?)(?<![\w-])rencontres-linux\.quebec", re.IGNORECASE)     # 1.134: with or without the dot (www. / host=): ".RLQ" or "RLQ"


def render(kind_name, text, ip, keep_ip, pays=None, category=None, accent=False):
    """(name, parts, raw, category): the colored NAME that replaces the address in the text; the "parts" [country, address (except --hide-ip)] for the
    address column; raw: true if nothing is known about the address (the name is the address itself); category: "whitelist" (whitelist), "place" (places
    file) or None — the address is then displayed in INVERSE VIDEO (white / gray); with --hide-ip (no address displayed) it is the name that is."""
    raw = kind_name == "unknown" and text == ip
    suffix = {"org": " (org)", "reseau": " (network)"}.get(kind_name, "")
    style = STYLES[CATEGORY_STYLE[category]] if (category and not keep_ip) else STYLES.get(kind_name)
    if accent and kind_name == "person":                         # member of the --accentuate-group group: bold white on dark blue
        style = STYLES["accent"]
    shown = text + suffix
    rlq = shown.lower().endswith(RLQ_DOMAIN_SUFFIX)                 # 1.127: ".rencontres-linux.quebec" is shown as ".RLQ." (in colour), to save room
    if rlq:
        shown = shown[:-len(RLQ_DOMAIN_SUFFIX)] + RLQ_TAG
    if NAME_TRUNCATE and len(shown) > NAME_TRUNCATE:               # --dns-max-truncate N: at most N characters, the last one is "..."
        shown = shown[:NAME_TRUNCATE - 1] + "…"
    if raw:
        name = ip
    elif rlq and shown.endswith(RLQ_TAG):
        name = color_code(style, shown[:-len(RLQ_TAG)]) + color_code(STYLES["place"], RLQ_TAG)
    else:
        name = color_code(style, shown)
    return name, ([pays] if pays else []) + ([ip] if keep_ip else []), raw, category


def crochets(parts, ip, category, surrounded=True):
    """"[CA address]" in gray (without the brackets if surrounded is false: address column); the address itself in INVERSE VIDEO white (whitelist) or gray
    (places file) when defined there. Without color: the same text."""
    gray = STYLES["ip"]
    output = color_code(gray, "[") if surrounded else ""
    for i, x in enumerate(parts):
        if i:
            output += color_code(gray, " ")
        output += color_code(STYLES[CATEGORY_STYLE[category]] if (x == ip and category) else gray, x)
    return output + (color_code(gray, "]") if surrounded else "")


# ------------------------------------------------------------------------------------------------------------------
# Formatting of a line
# ------------------------------------------------------------------------------------------------------------------
def suspect_url(url):
    """True if the URL is suspicious (SUSPECT_RE), as is or decoded (%2e%2e = ..)."""
    return bool(SUSPECT_RE.search(url) or SUSPECT_RE.search(unquote(url)))


def suspicious_request(text):
    r = REQUEST_RE.search(text)
    return bool(r and suspect_url(r.group(1)))


def mount_point(path):
    """Mount point (partition) that contains `path`."""
    path = os.path.realpath(path)
    while not os.path.ismount(path) and path != os.path.dirname(path):
        path = os.path.dirname(path)
    return path


def journals_free_space(profile):
    """{mount point: free bytes} of the partitions where the journals are written: Odoo file (logfile), nginx, systemd journal (one entry per partition)."""
    candidates = [os.path.dirname(profile.get("ODOO_LOGFILE") or ""), NGINX_DIR, "/var/log/journal", "/var/log"]
    result = {}
    for path in candidates:
        if path and os.path.isdir(path):
            try:
                result.setdefault(mount_point(path), shutil.disk_usage(path).free)
            except OSError:
                continue
    return result


def request_not_found(text):
    """True for a request whose response is 404 (page not found)."""
    r = REQUEST_RE.search(text)
    return bool(r and r.group(2) == "404")


def request_duration(text):
    """Total duration (seconds: SQL + Python) of an Odoo request, or None."""
    m = DURATION_RE.search(text)
    return float(m.group(2)) + float(m.group(3)) if m else None


DETAIL_RE = re.compile(r'"\s(\d{3})\s(\S+)\s(\d+)\s(\d+\.\d+)\s(\d+\.\d+)\s*$')


def request_detail(text):
    """(size in bytes or None, SQL queries, SQL time, Python time) of an Odoo request, or None."""
    m = DETAIL_RE.search(text)
    if not m:
        return None
    return (int(m.group(2)) if m.group(2).isdigit() else None, int(m.group(3)), float(m.group(4)), float(m.group(5)))


def url_template(url):
    """URL without parameters, numbers replaced by "N" (/event/journee-2026-125/registration -> /event/journee-N-N/registration): groups the same pages."""
    return re.sub(r"\d+", "N", url.split("?", 1)[0])


COLD_RE = re.compile(r"/web/assets/|/web/bundle/|/get_views\b|/web/webclient/(?:load_menus|translations)")      # work that Odoo redoes once after a restart or a module update


def request_cause(sql_n, t_sql, t_py, size, url=""):
    """Probable cause of a slow request: short text; the strongest indication first."""
    total = t_sql + t_py
    if total <= 0:
        return "unknown"
    if t_sql < 0.2 * total and COLD_RE.search(url):
        if "/web/assets/" in url or "/web/bundle/" in url:
            return "assets (JS/CSS) rebuilt: normal once after a restart or a module update"
        return "views or menus recompiled (cold Odoo cache): normal once per screen after a restart or a module update"
    if t_sql >= 0.6 * total:
        return "slow SQL queries (" + (f"{sql_n} queries, " if sql_n >= SQL_HIGH else "") + "index or query to optimise)"
    if sql_n >= SQL_HIGH:
        return f"too many SQL queries ({sql_n}: repeated reading of records)"
    if size is not None and size >= SIZE_HIGH:
        return f"large response ({size // 1_000_000} Mo)"
    if t_sql < 0.2 * total:
        return "Python time (computation, waiting for a lock, or overloaded server)"
    return "mixed (SQL and Python)"


class Formatting:
    """Builds the displayed line: normalized header, then the text with its words in color. All the detection is done on the
    RAW text (never on already colored text); a detection that overlaps a higher-priority one (the IP address first) is ignored."""
    def __init__(self, minimal=False, width=COLUMN_WIDTH, slowest=0.0, status_header=False, hide_user_agent=False, request_length=False):
        self.request_length = request_length                                # 1.136 --request-length: rl= of the nginx lines in its own column before the GET
        self.hide_user_agent = hide_user_agent                              # 1.134 --hide-user-agent: the User-Agent text is not shown (the OS column stays)
        self.status_header = status_header                                  # 1.123 --status-header
        self.minimal = minimal
        self.slowest = slowest                            # threshold (seconds) of slow requests; 0 = no highlighting
        self.width = width                      # width of the address column, after the level
        self.offset = 0                           # width of the "database logger" of THIS line minus that of "database werkzeug": the name is shortened accordingly, so that the GET stays aligned
        self.in_trace = False                       # in a Python trace (lines following "Traceback")
        self.benign_ongoing = False                 # in an error WITHOUT SEVERITY (concurrent update conflict)

    def spans(self, L, renderings, soft=False):
        """[(start, end, rendering)] non-overlapping, by priority: IP addresses, logins, HTTP code, paths, error words."""
        text, retained = L.text, []
        addresses = find_ips(text)
        first_seen = addresses[0][2] if addresses and L.level is not None else None      # this one is in the address COLUMN

        def ajouter(d, f, rendering):
            if all(f <= a or d >= b for a, b, _ in retained):
                retained.append((d, f, rendering))
        for d, f, ip in addresses:
            name, parts, raw, category = renderings.get(ip, (ip, [], True, None))
            if ip == first_seen:
                rendering = name
            else:                                    # other address of the message: "name [CA address]" in the text
                p = [x for x in parts if not (raw and x == ip)]
                rendering = name + (" " + crochets(p, ip, category) if p else "")
            if d == 0:                               # address at the very start (nginx / werkzeug request): the name takes at least NAME_WIDTH characters
                rendering += " " * max(0, NAME_WIDTH - self.offset - display_width(rendering))      # (never truncated: a longer name overflows) to align what follows
                if text[f:f + 5] == " - - ":        # "- -" = RFC 1413 identity and HTTP user: always "-" in Odoo; removed only if both are "-"
                    f += 4
            ajouter(d, f, rendering)
        m = LOGIN_OK_RE.search(text)
        if m:
            ajouter(m.start(1), m.end(1), color_code(STYLES["connection"], m.group(1)))
            ajouter(m.start(2), m.end(2), color_code(STYLES["connection"], m.group(2)))
        for m in LOGIN_FAILED_RE.finditer(text):
            ajouter(m.start(1), m.end(1), color_code(STYLES["failure"], m.group(1)))
            if m.group(2):
                ajouter(m.start(2), m.end(2), color_code(STYLES["failure"], m.group(2)))
        m = SHORT_METHOD_RE.search(text)
        if m:
            ajouter(m.start(1), m.end(1), "  ")
        m = STATUS_RE.search(text)
        if m and http_style(m.group(1)):
            ajouter(m.start(1), m.end(1), color_code(http_style(m.group(1)), m.group(1)))
        # URL in INVERSE VIDEO: SUSPICIOUS request (terminal color); otherwise critical 5xx error (red); the login page keeps its style; then 4xx error
        # (yellow). Only the URL is touched (the HTTP code keeps its color).
        r = REQUEST_RE.search(text)
        shown_url = display_url(r.group(1)) if r else ""                                              # 1.128: the URL as it is really requested (%20 -> space)
        if r:
            code = int(r.group(2))
            if suspect_url(r.group(1)):
                ajouter(r.start(1), r.end(1), color_code(STYLES["suspect"], r.group(1)))              # suspect: the URL as it was sent (%2e%2e stays visible)
            elif code >= 500:
                ajouter(r.start(1), r.end(1), color_code(STYLES["url_critical"], shown_url))
        for m in LOGIN_PATH_RE.finditer(text):
            ajouter(m.start(1), m.end(1), color_code(STYLES["connection"], m.group(1)))
        if r and 400 <= int(r.group(2)) < 500:
            ajouter(r.start(1), r.end(1), color_code(STYLES["url_warning"], shown_url))
        if r and not suspect_url(r.group(1)) and shown_url != r.group(1):      # 1.128: a URL coded in %XX and not coloured above: shown decoded
            ajouter(r.start(1), r.end(1), shown_url)
        for m in URL_IN_TEXT_RE.finditer(text):           # 1.133: every URL of the line (referer...): path and query decoded (%5B -> [, %2C -> ,), the host kept
            shown_part = display_url(m.group(2))
            if m.group(2) and shown_part != m.group(2) and not suspect_url(m.group(2)):
                ajouter(m.start(2), m.end(2), shown_part)
        for m in RLQ_DOMAIN_RE.finditer(text):             # 1.128: the domain is shown as ".RLQ" in the text too (in colour); 1.134: "RLQ" without a dot
            ajouter(m.start(), m.end(), color_code(STYLES["place"], RLQ_TEXT_TAG if m.group(1) else "RLQ"))
        style = STYLES["warning"] if (L.level == "WARNING" or soft) else STYLES["error"]
        for m in ERROR_WORDS_RE.finditer(text):
            ajouter(m.start(), m.end(), color_code(style, m.group()))
        m = SQL_SIZE_RE.search(text)
        if m and self.slowest:                                  # size of the response and number of SQL queries, when they are high (--slow 0: disabled)
            if m.group(1).isdigit():
                byte_count = int(m.group(1))
                if byte_count >= SIZE_HIGH:
                    ajouter(m.start(1), m.end(1), color_code(STYLES["very_slow_request"] if byte_count >= SIZE_VERY_HIGH else STYLES["slow_request"], m.group(1)))
            sql_requests = int(m.group(2))
            if sql_requests >= SQL_HIGH:
                ajouter(m.start(2), m.end(2), color_code(STYLES["very_slow_request"] if sql_requests >= SQL_VERY_HIGH else STYLES["slow_request"], m.group(2)))
        m = DURATION_RE.search(text)
        if m and self.slowest:
            duration_style = self.slowness_style(float(m.group(2)) + float(m.group(3)))
            if duration_style:
                ajouter(m.start(2), m.end(3), color_code(duration_style, m.group(2) + " " + m.group(3)))
        return sorted(retained)

    @staticmethod
    def colored_text(text, retained, start, end):
        """The raw text [start, end) with the detections (start, end, rendering) that fit entirely in it."""
        chunks, position = [], start
        for d, f, rendering in retained:
            if d >= position and f <= end:
                chunks.append(raw(text[position:d]) + rendering)
                position = f
        return "".join(chunks) + raw(text[position:end])

    def aligned_nginx_request(self, text, retained, times=None):
        """1.117: nginx access line: "\"GET /url HTTP/1.1\" 200 15203 \"-\" \"agent\" host=..." becomes "HTTP/1.1 200 15203      \"GET /url\" \"-\" \"agent\" host=...":
        the status and the size are in the same columns as the status and the size of an Odoo request line. nginx gives no SQL or time
        columns: they stay empty, so the Odoo times are not repeated. Other line form: None (display unchanged)."""
        m = NGINX_REQUEST_RE.search(text)
        if not m:
            return None
        ouvrir = m.start()
        http, code, size = m.group(2), m.group(3), m.group(4)

        def token(group, value, width):
            rendering = value
            for d, f, r in retained:
                if (d, f) == (m.start(group), m.end(group)):
                    rendering = r
            return " " * max(0, width - len(value)) + rendering
        agent = NGINX_AGENT_RE.search(text, m.end(4))
        if times:                                                # 1.123 --log-merge: SQL queries and times of the Odoo line of the same request
            sql_s, t_sql_s, t_py_s = times[0].rjust(4), times[1].rjust(6), times[2].rjust(6)
            total = (float(times[1] or 0) + float(times[2])) if times[2] else 0.0      # 1.141: a websocket has no SQL time
            if total:                                            # 1.141: white under 1 s, green 1 to 3 s, yellow 3 to 6 s, red above 6 s
                style = transfer_style(total)
                t_sql_s, t_py_s = color_code(style, t_sql_s), color_code(style, t_py_s)
            numbers = [sql_s, t_sql_s, t_py_s]
        else:
            numbers = [" " * 4, " " * 6, " " * 6]
        if code == "403" and agent and BOT_BLOCKED_UA_RE.search(agent.group(1)):      # 1.134: a robot refused by policy: [BOT] in the transfer-time column
            numbers[2] = color_code(STYLES["debug"], "[BOT]".rjust(6))
        block = " ".join([short_http(http).ljust(4), token(3, code, 3), token(4, size_text(size), SIZE_WIDTH)] + numbers)
        os_name = os_code(agent.group(1) if agent else "")                         # 1.133: OS of the client, 3 characters before the GET
        os_column = color_code(OS_COLORS[os_name], os_name) if os_name in OS_COLORS else os_name      # 1.136: LIN green, AND cyan
        rl = RL_RE.search(text, m.end(4))
        rl_column = (rl.group(1).rjust(RL_WIDTH) if rl else " " * RL_WIDTH) + " " if self.request_length else ""     # 1.136: its own column
        request_data = self.colored_text(text, retained, ouvrir + 1, m.end(1))      # 1.119: no quotes; the request keeps the column of the Odoo request
        before = self.colored_text(text, retained, 0, ouvrir)
        if not ANSI_RE.sub("", before).endswith(" "):
            before += " "
        cuts = []                                                # 1.134: the User-Agent text (with its quotes) is left out; 1.136: so is rl= when it has its column
        if self.hide_user_agent and agent:
            cuts.append((agent.start(1) - 1, agent.end(1) + 1))
        if rl:                                           # 1.136: rl= leaves the end of the line: its column (--request-length) or nothing
            cuts.append((rl.start(0), rl.end(0)))
        pieces, position = [], m.end(4)
        for cut_start, cut_end in sorted(cuts):
            pieces.append(self.colored_text(text, retained, position, cut_start))
            position = cut_end
        pieces.append(self.colored_text(text, retained, position, len(text)))
        tail = re.sub(" {2,}", " ", "".join(pieces)).replace('"', "")
        return before + block + "   " + rl_column + os_column + " " + request_data + tail

    def aligned_request(self, text, retained):
        """Werkzeug line: "… \"GET /url HTTP/1.1\" 200 - 13 0.006 0.066" becomes "… HTTP/1.1 200       - 13 0.006 0.066  \"GET /url\"": the block of numbers, of fixed width,
        goes BEFORE the request (columns aligned from one line to the next). Other line form: None (display unchanged)."""
        m = WERKZEUG_RE.search(text)
        if not m:
            return None
        ouvrir = m.start()
        http, code, size, sql, t_sql, t_py = (m.group(i) or "" for i in range(2, 8))      # websocket: no SQL queries or SQL time (empty columns)

        def token(hint, value, width, right=True, shown=None):
            rendering = shown or value
            for d, f, r in retained:
                if shown is None and (d, f) == (m.start(hint), m.end(hint)):
                    rendering = r
            if hint in (6, 7) and value and t_py:                     # 1.141: traffic light of the time; a websocket duration (no SQL time) too
                style = transfer_style(float(t_sql or 0) + float(t_py))
                if style:
                    rendering = color_code(style, shown or value)      # 1.141: the shown text (a websocket duration: 3 decimals)
            empty = " " * max(0, width - len(shown or value))
            return empty + rendering if right else rendering + empty
        start = [short_http(http).ljust(4), token(3, code, 3), token(4, size_text(size), SIZE_WIDTH)]
        if sql:
            block = " ".join(start + [token(5, sql, 4), token(6, t_sql, 6), token(7, t_py, 6)])
        else:                                                   # websocket: only the duration, right-aligned on the width of the three columns SQL / SQL time / Python time
            block = " ".join(start + [" " * 4, token(7, t_py, 13, shown=f"{float(t_py):.3f}")])      # 3 decimals like the other columns: the decimal points are aligned
        request_data = self.colored_text(text, retained, ouvrir + 1, m.end(1))      # 1.121: no quotes, nothing put in their place
        before = self.colored_text(text, retained, 0, ouvrir)
        if not ANSI_RE.sub("", before).endswith(" "):          # name as wide as its column: never "this serverHTTP/1.1" stuck together, at least one space before HTTP
            before += " "
        rl_blank = " " * (RL_WIDTH + 1) if self.request_length else ""          # 1.136: same column as nginx lines (blank in an Odoo line)
        return before + block + "   " + rl_blank + OS_BLANK + " " + request_data          # 1.133: the same column as nginx lines (blank: no User-Agent in the Odoo line)

    def slowness_style(self, total):
        """Bold orange from the --slow threshold, bold red from 3 times the threshold; None under the threshold (or without a threshold)."""
        if not self.slowest or total < self.slowest:
            return None
        return STYLES["very_slow_request"] if total >= 3 * self.slowest else STYLES["slow_request"]

    def hidden_logger(self, L):
        """In --min, the logger of a REQUEST is not displayed: "werkzeug", and also "longpolling" (websocket, same line format) — otherwise this 11-letter word
        pushes the name to the right and the names are no longer aligned from one line to the next."""
        return self.minimal and (L.logger == "werkzeug" or (L.logger == "request" and L.database == "nginx")
                                 or (L.logger == "longpolling" and bool(WERKZEUG_RE.search(L.text))))

    def format_value(self, L, renderings, benign=False):
        """Final text of the line (without a line break). benign: error WITHOUT SEVERITY (orange instead of red, with its reason)."""
        if L.level is not None:                                         # new structured Odoo entry: the trace is over
            self.in_trace = False
            self.benign_ongoing = benign
            # Logger other than werkzeug ("longpolling" of websockets...): longer "database logger" (or displayed in --min): the name is shortened accordingly, the GET stays aligned
            displayed = ([] if self.minimal else [L.database]) + ([] if self.hidden_logger(L) else [L.logger])
            reference = 0 if self.minimal else len("base werkzeug") + 1
            self.offset = (len(" ".join(displayed)) + 1 if displayed else 0) - reference
        else:
            self.offset = 0
            if "Traceback (most recent call last)" in L.text:           # start of a Python trace (following lines: the trace)
                self.in_trace = True
        if L.level is None and self.in_trace:                           # trace line: all in red
            body = color_code(STYLES["error"], raw(L.text))
        elif L.level is None and self.benign_ongoing:                   # continuation of an error without severity: orange
            body = color_code(STYLES["warning"], raw(L.text))
        else:
            retained = self.spans(L, renderings, benign)
            body = (self.aligned_request(L.text, retained)
                    or (self.aligned_nginx_request(L.text, retained, L.odoo_times) if L.database == "nginx" and L.logger == "request" else None)
                    or self.colored_text(L.text, retained, 0, len(L.text)))
            if benign:
                body += color_code(STYLES["debug"], " (concurrent update conflict: Odoo retries automatically)")
            total = (float(L.odoo_times[1] or 0) + float(L.odoo_times[2] or 0)) if L.odoo_times else request_duration(L.text)     # 1.123: merged line: the Odoo times
            if total is not None and self.slowness_style(total):
                body += color_code(self.slowness_style(total), f" ← slow: {total:.1f} s")
        column = ""
        addresses = find_ips(L.text)
        if L.level is not None:                                         # address column of fixed width, right after the level
            visible, colored = "", ""
            if addresses and addresses[0][2] in renderings and renderings[addresses[0][2]][1]:
                ip0 = addresses[0][2]
                visible = " ".join(renderings[ip0][1])
                colored = crochets(renderings[ip0][1], ip0, renderings[ip0][3], surrounded=False)
                if renderings[ip0][1][0] == ip0:                        # 1.91: no country (loopback, private network, lookup too slow): the address stays
                    visible, colored = "   " + visible, "   " + colored  # under the addresses of the other lines ("CA 11.191.124.32")
            column = colored + " " * max(0, self.width - len(visible))                 # 1.117: the level has a fixed width (LEVEL_WIDTH), nothing to take back here
        header = []
        if L.ts_txt:
            shown_program = color_code(STYLES["nginx"], L.program_name) if (L.database == "nginx" and L.program_name) else L.program_name     # 1.118: nginx lines in colour
            if self.status_header:                              # 1.125 --status-header: the time stays on the line; the date and the host name are in the status bar
                header.append(L.ts_txt.rpartition(" ")[2])
                header.append((shown_program or "") + ("" if L.level else ":"))
            else:
                header.append(L.ts_txt)
                header.append(" ".join(x for x in (L.host_name, shown_program) if x) + ("" if L.level else ":"))          # structured Odoo line: "odoo18 odoo INFO", without ":" (1.112: without host with --no-hostname)
        if L.level:
            short = LEVEL_SHORT.get(L.level, L.level)                                            # 1.123: 4 characters
            level_text = {"ERROR": color_code(STYLES["warning"] if benign else STYLES["error"], short), "CRITICAL": color_code(STYLES["error"], short),
                          "WARNING": color_code(STYLES["warning"], short), "DEBUG": color_code(STYLES["debug"], short)}.get(L.level, short)
            header.append(" " * max(0, LEVEL_WIDTH - len(short)) + level_text)                   # 1.117: right-aligned, same column for INFO, ERROR and CRITICAL
            if column:
                header.append(column)
            field_list = ([] if self.minimal else [L.database]) + ([] if self.hidden_logger(L) else [L.logger])
            shown_fields = ([] if self.minimal else [color_code(STYLES["nginx"], L.database) if L.database == "nginx" else L.database]) + ([] if self.hidden_logger(L) else [L.logger])     # 1.118: "nginx" in colour
            if WERKZEUG_RE.search(L.text) or (L.database == "nginx" and L.logger == "request"):      # 1.116: nginx request = Odoo request
                header.extend(shown_fields)
            else:
                # Odoo message that is NOT a request: its text starts at the column of the "GET / POST" of requests (after the numbers block), never
                # above the number columns. "database logger" is padded up to that column (never truncated: a longer logger overflows).
                target = (0 if self.minimal else len("base werkzeug") + 1) + NAME_WIDTH + NUMBERS_BLOCK_WIDTH + (RL_WIDTH + 1 if self.request_length else 0)
                header.append(" ".join(shown_fields) + " " * max(0, target - 1 - len(" ".join(field_list))))     # padding from the plain text (colours take no column)
        return (" ".join(header) + " " if header else "") + body


# ------------------------------------------------------------------------------------------------------------------
# Presence: who is still logged in?
# ------------------------------------------------------------------------------------------------------------------
def duration(seconds):
    """"45 s" under 2 minutes, "40 min" beyond."""
    seconds = max(0, int(seconds))
    return f"{seconds} s" if seconds < 120 else f"{seconds // 60} min"


class Presence:
    """Tracking of each recognized person: login (journal), logout (/web/session/logout), activity (a request from their
    address). Odoo does not write the end of a session: "logged in" = logged in, not logged out, active for less than --idle minutes."""
    def __init__(self, idle_minutes):
        self.idle_state = idle_minutes * 60
        self.state = OrderedDict()           # account -> dict(name, ip, last_seen, requests, logged_out, idle)

    @staticmethod
    def hour(instant):
        return time.strftime("%H:%M:%S", time.localtime(instant))

    @staticmethod
    def timestamp(when, hour):
        """(date and time "YYYY-MM-DD HH:MM:SS", time "HH:MM:SS"): those of the journal line if given ("time": 8 or 19 characters — same time as the
        commented line, whatever the timezone of the machine), otherwise those of the instant."""
        if hour and len(hour) >= 19:
            return hour[:19], hour[11:19]
        complete = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when))
        return (f"{complete[:10]} {hour}" if hour else complete), (hour or complete[11:])

    def _entry(self, account, name, ip, when):
        e = self.state.setdefault(account, {"nom": name, "ip": ip, "last_seen": when, "hour": self.hour(when), "date": self.timestamp(when, None)[0],
                                          "requetes": 0, "logged_out": False, "idle_state": False})
        e["nom"], e["ip"] = name, ip
        return e

    def login(self, account, name, ip, when, hour=None):
        """"time": HH:MM:SS (or YYYY-MM-DD HH:MM:SS) of the journal line."""
        date, hour = self.timestamp(when, hour)
        e = self._entry(account, name, ip, when)
        e.update(last_seen=when, hour=hour, date=date, logged_out=False, idle_state=False)
        return [("connection", f"● {hour} {name} [{ip}] has just signed in")]

    def activity(self, account, name, ip, when, logout=False, hour=None):
        """Events (kind, text) to display after this line."""
        date, hour = self.timestamp(when, hour)
        e = self._entry(account, name, ip, when)
        events = []
        if logout:
            e.update(last_seen=when, hour=hour, date=date, logged_out=True, idle_state=False)
            return [("logout", f"✕ {hour} {name} [{ip}] signed out (/web/session/logout)")]
        if e["idle_state"] and not e["logged_out"]:
            events.append(("connection", f"● {hour} {name} [{ip}] : back after {duration(when - e['last_seen'])} of inactivity"))
        if when >= e["last_seen"]:
            e["hour"], e["date"] = hour, date
        e.update(last_seen=max(e["last_seen"], when), idle_state=False)
        e["requetes"] += 1
        return events

    def check(self, now_dt):
        """People whose inactivity has just exceeded --idle: "no more activity" events."""
        events = []
        for e in self.state.values():
            if not e["logged_out"] and not e["idle_state"] and now_dt - e["last_seen"] >= self.idle_state:
                e["idle_state"] = True
                events.append(("idle_state", f"○ {self.hour(now_dt)} {e['nom']} [{e['ip']}] : no activity for "
                                              f"{duration(now_dt - e['last_seen'])} (session may still be valid)"))
        return events

    def summary(self, now_dt, message_count):
        """Presence in COLUMNS: state, name, address, date and time of the last activity, then the detail (gap, requests seen)."""
        lines = [f"Presence based on the last {message_count} messages (inactive after {self.idle_state / 60:g} min; most recent activity first):"]
        ranked = []
        for e in self.state.values():
            gap = duration(now_dt - e["last_seen"])
            if e["logged_out"]:
                kind_name, state, detail = "logout", "✕ signed out", "at sign-out (/web/session/logout)"
            elif now_dt - e["last_seen"] >= self.idle_state:
                kind_name, state, detail = "idle_state", "○ inactive", f"since {gap}"
            else:
                kind_name, state, detail = "connection", "● signed in", TR("{gap} ago · {n} requests seen").format(gap=gap, n=e['requetes'])
            e["idle_state"] = kind_name == "idle_state"
            ranked.append((e["last_seen"], (kind_name, state, e["nom"], f"[{e['ip']}]", e.get("date") or e["hour"], detail)))
        ranked = [r for _, r in sorted(ranked, key=lambda x: x[0], reverse=True)]       # most recent last activity first
        if ranked:
            widths = [max(len(r[k]) for r in ranked) for k in (1, 2, 3, 4)]
            headers = ("State", "Name", "Address", "Last activity")
            widths = [max(l, len(t)) for l, t in zip(widths, headers)]
            widths[0] = max(widths[0], 15)                                   # room for the French "logout" label (the translation never changes the column positions)
            lines.append("  " + color_code(STYLES["debug"], "  ".join(t.ljust(l) for t, l in zip(headers, widths)) + "  " + TR("Detail")))
            for kind_name, state, name, address, date, detail in ranked:
                text = "  ".join(c.ljust(l) for c, l in zip((state, name, address, date), widths)) + "  " + detail
                lines.append("  " + color_code({"connection": "1;32", "logout": "1;31", "idle_state": ORANGE}[kind_name], text))
        else:
            lines.append("  no person signed in to the site in these messages")
        return lines

    def event(self, kind_name, text):
        return color_code({"connection": "1;32", "logout": "1;31", "idle_state": ORANGE}[kind_name], text)


# ------------------------------------------------------------------------------------------------------------------
# Site diagnostic (D key, --diagnose): why the MAINTENANCE page is displayed, and what to do. nginx serves it (error_page 502 503 504) when it cannot
# reach Odoo: stopped service, Odoo not listening on the port of its configuration, nginx upstream that points to ANOTHER port, firewall.
# ------------------------------------------------------------------------------------------------------------------
MAINTENANCE_MARK = "Maintenance en cours"           # <title> of the maintenance page of the nginx configuration (maintenance/index.html)


def listening_ports():
    """{port: [processes]} of the listening TCP ports (ss -ltnp); None if ss is absent."""
    code, output = lancer(["ss", "-ltnpH"], 10)
    if code != 0:
        return None
    res = {}
    for text_line in output.splitlines():
        field_list = text_line.split()
        if len(field_list) >= 4 and field_list[3].rpartition(":")[2].isdigit():
            res.setdefault(int(field_list[3].rpartition(":")[2]), []).extend(re.findall(r'\(\("([^"]+)"', text_line))
    return res


def nginx_upstreams(text):
    """[(name, host, port, file, line)] of the "server HOST:PORT;" of the upstream blocks of "nginx -T"; (server names) served by nginx."""
    file_path, n, name, upstreams, names = "?", 0, None, [], []
    for text_line in text.splitlines():
        m = re.match(r"# configuration file (.+?):\s*$", text_line)
        if m:
            file_path, n, name = m.group(1), 0, None
            continue
        n += 1
        d = text_line.split("#", 1)[0].strip()
        m = re.match(r"upstream\s+(\S+)\s*\{", d)
        if m:
            name = m.group(1)
            continue
        if name and d.startswith("}"):
            name = None
        m = re.match(r"server\s+\[?([\w.:-]+?)\]?:(\d+)\b", d)
        if name and m:
            upstreams.append((name, m.group(1), int(m.group(2)), file_path, n))
        m = re.match(r"server_name\s+([^;]+);", d)
        if m:
            for x in m.group(1).split():
                if not re.search(r"[*~_$]", x) and x != "localhost" and x not in names:
                    names.append(x)
    return upstreams, names


def local_request(port, host_name, tls=False, path="/", delay=8):
    """(HTTP code, start of the body) of a request to 127.0.0.1:port with the Host header (and SNI in TLS); (None, error text) if the connection fails."""
    import socket
    import ssl
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=delay)
        if tls:
            context = ssl.create_default_context()
            context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
            s = context.wrap_socket(s, server_hostname=host_name)
        s.settimeout(delay)
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: {host_name}\r\nUser-Agent: app-log-live-diagnose\r\nConnection: close\r\n\r\n".encode())
        payload = b""
        while len(payload) < 20000:
            block = s.recv(4096)
            if not block:
                break
            payload += block
        s.close()
    except socket.timeout:
        return None, "timeout"
    except ConnectionRefusedError:
        return None, "connection refused"
    except (OSError, ssl.SSLError) as e:
        return None, str(e)[:80]
    text = payload.decode("utf-8", "replace")
    m = re.match(r"HTTP/\d(?:\.\d)? (\d{3})", text)
    return (int(m.group(1)) if m else None), text.partition("\r\n\r\n")[2]


def certificate_advice(message, name):
    """What to do according to the certificate check message."""
    if re.search(r"self[- ]signed|self signed", message, re.I):
        return TR("nginx presents a SELF-SIGNED certificate for this name (often the fallback « snakeoil » certificate of a default server block): this name's server block is missing or its ssl_certificate "
                  "is wrong. Check: nginx -T | grep -n -B2 -A12 'server_name {name}' ; then issue the real certificate: certbot --nginx -d {name} (or certbot certonly --webroot -w /var/www/letsencrypt -d {name}) "
                  "and nginx -t && systemctl reload nginx. "
                  "If the DNS name has just CHANGED (e.g. odoo-lab → odoo): nginx-hardening.sh --update --rename-to {name} does this work.").format(name=name)
    if re.search(r"unable to get local issuer|unable to verify the first|issuer certificate", message, re.I):
        return TR("the chain is INCOMPLETE or the issuer is unknown: ssl_certificate must point to fullchain.pem (/etc/letsencrypt/live/{name}/fullchain.pem), not cert.pem. "
                  "A certificate from a private or TEST authority (Let's Encrypt staging) is not recognized by browsers: reissue it without --staging.").format(name=name)
    if re.search(r"expired", message, re.I):
        return ("the certificate has EXPIRED: certbot renew (as root), then systemctl reload nginx. Why automatic renewal failed: systemctl status certbot.timer; "
                "certbot renew --dry-run; the ACME challenge goes through /var/www/letsencrypt (port 80 open).")
    if re.search(r"hostname mismatch|doesn't match|does not match|IP address mismatch", message, re.I):
        return TR("the certificate does NOT cover this name: certbot --nginx --expand -d {name} (adds this name to the certificate) or use the certificate of this name in the server block. "
                  "If the DNS name has just CHANGED (e.g. odoo-lab → odoo): nginx-hardening.sh --update --rename-to {name} (finds the old name in nginx, replaces it, obtains the certificate, reloads nginx).").format(name=name)
    return TR("The browser will refuse this certificate ({message}). Reissue with certbot --nginx -d {name} and reload nginx.").format(message=message, name=name)


def describe_certificate(der):
    """Subject, issuer and expiry of a DER certificate according to openssl; empty string if openssl is absent."""
    import ssl
    try:
        pem = ssl.DER_cert_to_PEM_cert(der)
        r = subprocess.run(["openssl", "x509", "-noout", "-subject", "-issuer", "-enddate"], input=pem, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return " ; ".join(l.strip() for l in r.stdout.splitlines() if l.strip()) if r.returncode == 0 else ""


def check_certificate(name, host_name=None, port=443, delay=8):
    """(level, finding, what to do): is the certificate that `name` presents (connection to `host`, otherwise to the name itself) accepted by a browser? Full check
    like a browser: recognized authority, complete chain, name covered, not expired."""
    import socket
    import ssl
    target = f"{name}:{port}" if host_name is None else f"{host_name}:{port} (name {name})"
    try:
        raw = socket.create_connection((host_name or name, port), timeout=delay)
    except OSError as e:
        return ("WARN", f"Certificate of {target}: cannot connect ({str(e)[:70]}).", f"Is port {port} served and open (nginx started, firewall)? For another server: run this diagnosis ON that server.")
    try:
        s = ssl.create_default_context().wrap_socket(raw, server_hostname=name)
        cert = s.getpeercert()
        s.close()
        remaining = (ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) / 86400
        issuer = next((v for r in cert.get("issuer", ()) for k, v in r if k == "organizationName"), "?")
        if remaining < 15:
            return ("WARN", f"Certificate of {target}: valid but expires in {remaining:.0f} days (issued by {issuer}).",
                    "Automatic renewal is not working: certbot renew --dry-run; systemctl status certbot.timer.")
        return ("OK", f"Certificate of {target}: accepted (issued by {issuer}, expires in {remaining:.0f} days).", "")
    except ssl.SSLCertVerificationError as e:
        message = f"{getattr(e, 'verify_message', '') or e}"
        details = ""
        try:
            raw2 = socket.create_connection((host_name or name, port), timeout=delay)
            context = ssl.create_default_context()
            context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
            s2 = context.wrap_socket(raw2, server_hostname=name)
            details = describe_certificate(s2.getpeercert(binary_form=True))
            s2.close()
        except (OSError, ssl.SSLError):
            pass
        advice = certificate_advice(message, name)
        return ("FAIL", f"Certificate of {target}: REFUSED by browsers (net::ERR_CERT_AUTHORITY_INVALID or similar) — {message}." + (f" Certificate presented: {details}." if details else ""), advice)
    except (OSError, ssl.SSLError) as e:
        return ("WARN", f"Certificate of {target}: TLS negotiation impossible ({str(e)[:80]}).", "does nginx listen in TLS on this port with a valid ssl_certificate? nginx -t")


def public_certificates(names):
    """Certificate seen BY THE INTERNET for each name (connection to the name through DNS, like a browser): without duplicates. A name that points to ANOTHER server is diagnosed
    from here, but its settings (nginx, certbot) are on that other server."""
    res, seen_set = [], set()
    for name in names:
        if name and name not in seen_set and "*" not in name and name not in ("_", "localhost"):
            seen_set.add(name)
            level, finding, advice = check_certificate(name)
            res.append((level, finding.replace("Certificate of ", "PUBLIC certificate of ", 1), advice + (" (The DNS of this name points to another server? Then fix it there.)" if level == "FAIL" else "")))
    return res


def site_diagnostic(profile, service, extra_hosts=()):
    """[(level, finding, what to do)]: level OK, WARN or FAIL. Each finding is checked (service, Odoo port, nginx upstream, local response, firewall)."""
    res = []
    http, gevent = int(profile.get("ODOO_HTTP_PORT") or 8069), int(profile.get("ODOO_GEVENT_PORT") or 8072)
    conf = profile.get("ODOO_CONF") or "the Odoo configuration"
    active = False
    if service:
        code, output = lancer(["systemctl", "is-active", service], 10)
        active = output.strip() == "active"
        if active:
            res.append(("OK", TR("Service {service} is active.").format(service=service), ""))
        else:
            res.append(("FAIL", TR("Service {service}: {state} (Odoo is stopped or failed: nginx serves the maintenance page).").format(service=service, state=TR(output.strip() or "unit not found")),
                        f"systemctl start {service} ; if it falls over again: journalctl -u {service} -n 50 --no-pager (and the ERROR / CRITICAL lines of the Odoo log)."))
    else:
        res.append(("WARN", "Odoo service: not found (--service NAME to specify it).", ""))
    listening = listening_ports()
    if listening is None:
        res.append(("WARN", "Listening ports: the ss command is missing, check skipped.", "apt install iproute2"))
    else:
        for caption, port in (("HTTP", http), ("gevent (instant chat)", gevent)):
            if port in listening:
                res.append(("OK", f"Port {caption} d'Odoo {port} : listening{' (' + ', '.join(sorted(set(listening[port]))) + ')' if listening[port] else ''}.", ""))
            else:
                others = sorted(p for p, names in listening.items() if any(re.search(r"python|odoo", x) for x in names))
                advice = (f"Odoo listens on {', '.join(map(str, others))}, not on {port} : fix http_port / gevent_port in {conf}, or nginx's upstream, then restart."
                           if others else (f"The service is active but not listening yet (still starting?): wait 30 s, otherwise journalctl -u {service} -n 50 --no-pager."
                                           if active else f"Start Odoo (the port {port} comes from {conf})."))
                res.append(("FAIL" if port == http else "WARN", f"Port {caption} d'Odoo {port} : NOBODY is listening (nginx gets « connection refused » = maintenance page).", advice))
    direct_code, body = local_request(http, "localhost", False, "/web/login")
    if direct_code is not None:
        res.append(("OK", f"Odoo answers directly on 127.0.0.1:{http} : HTTP {direct_code}.", ""))
    else:
        continuation = ""
        if "timeout" in body:
            rules = [l for l in lancer(["iptables", "-S"], 10)[1].splitlines() if re.search(rf"--dport {http}\b", l) and re.search(r"-j (DROP|REJECT)", l)]
            continuation = (" Firewall rules on this port: " + " ; ".join(rules[:3]) + ".") if rules else ""
            advice = ("A firewall may block even 127.0.0.1: allow the loopback interface (iptables -I INPUT -i lo -j ACCEPT ; ufw allow in on lo)." if continuation
                       else "No iptables rule targets this port: Odoo may be blocked or overloaded; journalctl -u " + str(service) + " -n 50 --no-pager.")
        else:
            advice = f"Odoo is not listening on port {http} : see the Odoo port above."
        res.append(("FAIL", f"Odoo does not answer on 127.0.0.1:{http} ({body}).{continuation}", advice))
    code_t, text_t = lancer(["nginx", "-T"], 30)
    if code_t != 0 or not text_t.strip():
        res.append(("WARN", "nginx configuration unreadable (nginx -T): upstreams and sites not checked.", "nginx -t (as root) gives the reason."))
        return res + public_certificates(list(extra_hosts))
    upstreams, names = nginx_upstreams(text_t)
    targeted = {}
    for name, host_name, port, file_path, text_line in upstreams:
        if re.match(r"odoo\d", name):                                  # other Odoo version (odoo17, odoo17_chat): own ports
            res.append(("OK", f"nginx upstream « {name} » ({file_path}:{text_line}): this is another Odoo version, not checked.", ""))
            continue
        if host_name in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            targeted.setdefault(port, []).append((name, file_path, text_line))
    expected = {http, gevent}
    for port, ou in sorted(targeted.items()):
        if port in expected:
            res.append(("OK", f"Upstream nginx 127.0.0.1:{port} ({ou[0][0]}, {ou[0][1]}:{ou[0][2]}) : it is Odoo's port.", ""))
        else:
            res.append(("FAIL", f"nginx upstream « {ou[0][0]} » targets 127.0.0.1:{port} ({ou[0][1]}:{ou[0][2]}), but Odoo is configured on {http} (HTTP) and {gevent} (gevent).",
                        TR("In {file}: replace « server 127.0.0.1:{port}; » with « server 127.0.0.1:{new_port}; », then nginx -t && systemctl reload nginx "
                           "(or set Odoo's http_port / gevent_port to the upstream's ports, then restart Odoo).").format(
                               file=ou[0][1], port=port, new_port=http if ou[0][0] == 'odoo' or 'chat' not in ou[0][0] else gevent)))
    if not targeted:
        res.append(("WARN", "No local upstream (127.0.0.1:PORT) in nginx -T: direct proxy_pass or Unix socket, not checked.", ""))
    for name in names[:6]:
        code_n, body_n = local_request(443, name, True)
        maintenance = MAINTENANCE_MARK.lower() in (body_n or "").lower()
        if code_n is None:
            res.append(("WARN", f"https://{name}/ (checked from this server) : {body_n}.", "nginx -t && systemctl status nginx ; is port 443 served for this name?"))
        elif maintenance or code_n in (502, 503, 504):
            res.append(("FAIL", f"https://{name}/ : HTTP {code_n}{' — MAINTENANCE PAGE served' if maintenance else ''}.",
                        "nginx cannot reach Odoo: fix the failure above (service, port, upstream), then refresh without cache (Ctrl+Shift+R): the page reloads itself every 30 s."))
        else:
            res.append(("OK", f"https://{name}/ : HTTP {code_n} — the site answers (no maintenance page).",
                        ""))
    for name in names[:6]:                                              # certificate served by nginx of THIS server (SNI), as a browser would see it
        res.append(check_certificate(name, "127.0.0.1"))
    return res + public_certificates(list(names[:6]) + list(extra_hosts))


# --- 1.86: versions of the nginx configuration and their dates (--diagnose, D key) -------------------------------------------------------------------
NGINX_ETC = os.environ.get("APP_LOG_LIVE_NGINX_ETC", "/etc/nginx")
NGINX_CONFIG_PARTS = ("conf.d", "sites-available", "snippets", "fail2ban")          # parts of nginx-odoo-config.zip copied under /etc/nginx
JOURNAL_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?")
VERSION_DATE_RE = re.compile(r"^(\d+\.\d+)(?:\.(\d{4})(\d{2})(\d{2})(?:\.(\d{2})(\d{2})\d{2})?)?$")


def file_date(path):
    """Local date and time of the last modification of a file (« 2026-10-17 09:12 »), None if unreadable."""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    except OSError:
        return None


def nginx_reloaded_at():
    """Local date and time of the last load of the nginx configuration: start of the oldest CURRENT worker (a reload replaces them all); None if unknown."""
    try:
        with open("/proc/stat") as f:
            btime = next(int(l.split()[1]) for l in f if l.startswith("btime"))
        tck = os.sysconf("SC_CLK_TCK")
        starts = []
        for pid in (x for x in os.listdir("/proc") if x.isdigit()):
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    if f.read().replace(b"\0", b" ").strip() != b"nginx: worker process":
                        continue
                with open(f"/proc/{pid}/stat") as f:
                    starts.append(btime + int(f.read().rsplit(")", 1)[1].split()[19]) / tck)
            except (OSError, ValueError, IndexError):
                continue
    except (OSError, StopIteration, ValueError):
        return None
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(min(starts))) if starts else None


def nginx_config_archive():
    """Folder nginx-odoo/ of the last nginx-odoo-config.zip unpacked next to the programs (deployment: « unzip nginx-odoo-config.X.Y.zip » in the folder of
    the programs), or None."""
    for folder in (os.path.join(SCRIPT_DIR, "nginx-odoo"), os.path.join(os.path.dirname(SCRIPT_DIR), "nginx-odoo")):
        if os.path.isfile(os.path.join(folder, "VERSION")):
            return folder
    return None


def version_text(version):
    """« 1.11 » or « 1.11.20261016.173838 » -> « 1.11 (2026-10-16 17:38) » when the version carries its date; as is otherwise."""
    m = VERSION_DATE_RE.match(version.strip())
    if m and m.group(2):
        return f"{m.group(1)} ({m.group(2)}-{m.group(3)}-{m.group(4)}" + (f" {m.group(5)}:{m.group(6)}" if m.group(5) else "") + ")"
    return version.strip() or "?"


def nginx_config_versions(limit=5):
    """1.86: lines « nginx configuration »: version of the nginx-odoo-config archive unpacked next to the programs (VERSION) and the date of its file, the
    latest DATED lines of its journal (README.md: one line per modification), then the files deployed under /etc/nginx compared with the archive (identical,
    different, absent) with their modification date, and the last reload of nginx. Without the archive: the most recently modified files of /etc/nginx."""
    lines = []
    archive = nginx_config_archive()
    deployed = []                                       # (date, relative path, state)
    if archive:
        try:
            with open(os.path.join(archive, "VERSION"), encoding="utf-8", errors="replace") as f:
                version = f.read().strip()
        except OSError:
            version = "?"
        lines.append(f"  Archive nginx-odoo-config: version {color_code('1;36', version_text(version))}"
                     + color_code("90", f" — {archive} (VERSION modified {file_date(os.path.join(archive, 'VERSION')) or '?'})"))
        journal = []
        try:
            with open(os.path.join(archive, "README.md"), encoding="utf-8", errors="replace") as f:
                for text_line in f:
                    m = JOURNAL_DATE_RE.search(text_line)
                    if m and text_line.lstrip()[:1] in "-*|#0123456789":
                        rest = (text_line[:m.start()] + text_line[m.end():]).strip(" -*|#:—\t\n")
                        journal.append((m.group(1) + (" " + m.group(2) if m.group(2) else ""), " ".join(rest.split())))
        except OSError:
            pass
        if journal:
            lines.append(f"  Latest changes of the nginx configuration (README.md journal, {len(journal)} dated lines):")
            for when, text_value in sorted(journal, key=lambda j: j[0], reverse=True)[:limit]:
                lines.append(f"    {color_code('36', when)}  {text_value[:150]}")
        for part in NGINX_CONFIG_PARTS:
            for root, _dirs, files in os.walk(os.path.join(archive, part)):
                for name in sorted(files):
                    rel = os.path.relpath(os.path.join(root, name), archive)
                    target = os.path.join(NGINX_ETC, rel)
                    if not os.path.isfile(target):
                        deployed.append((None, rel, "absent"))
                        continue
                    try:
                        with open(os.path.join(root, name), "rb") as a, open(target, "rb") as b:
                            state = "identical" if a.read() == b.read() else "different"
                    except OSError:
                        state = "unreadable"
                    deployed.append((file_date(target), rel, state))
        counts = collections.Counter(st for _, _, st in deployed)
        lines.append(f"  Deployed under {NGINX_ETC}: " + (" · ".join(f"{counts[k]} {k}" for k in ("identical", "different", "absent", "unreadable") if counts[k]) or "nothing to compare")
                     + color_code("90", " (files of the archive compared with the deployed ones; absent: not used on this server, or not yet deployed)"))
        for when, rel, state in sorted((d for d in deployed if d[2] != "absent"), key=lambda d: d[0] or "", reverse=True)[:limit]:
            style = "1;32" if state == "identical" else ORANGE
            lines.append(f"    {color_code('36', when or '?')}  {rel}  {color_code(style, state)}")
        if counts["different"]:
            lines.append("    " + color_code(ORANGE, "⚠ files different from the archive: ") + ", ".join(rel for _, rel, st in deployed if st == "different")[:300]
                         + color_code("90", " — copy them from nginx-odoo/ (doc/CONTEXTE.md section 5), then nginx -t && systemctl reload nginx"))
    else:
        files = []
        for part in NGINX_CONFIG_PARTS + ("sites-enabled",):
            for root, _dirs, names in os.walk(os.path.join(NGINX_ETC, part)):
                files += [(file_date(os.path.join(root, n)), os.path.relpath(os.path.join(root, n), NGINX_ETC)) for n in names]
        files.append((file_date(os.path.join(NGINX_ETC, "nginx.conf")), "nginx.conf"))
        files = [f for f in files if f[0]]
        lines.append(f"  Archive nginx-odoo-config: not found next to the programs ({os.path.join(SCRIPT_DIR, 'nginx-odoo')}/VERSION) — version unknown")
        if files:
            lines.append(f"  Most recently modified files of {NGINX_ETC} ({len(files)} files):")
            for when, rel in sorted(files, reverse=True)[:limit]:
                lines.append(f"    {color_code('36', when)}  {rel}")
        else:
            lines.append(f"  {NGINX_ETC}: no configuration file readable (root required?)")
    reloaded = nginx_reloaded_at()
    newest = max([d[0] for d in deployed if d[0]] or [""])
    lines.append("  Last reload of nginx: " + (color_code("36", reloaded) if reloaded else "unknown (no worker process visible)")
                 + (color_code(ORANGE, f" — ⚠ older than a deployed file ({newest}): nginx -t && systemctl reload nginx") if reloaded and newest and newest > reloaded else ""))
    return lines


def show_diagnostic(profile, service, write_line=print, color=True, extra_hosts=()):
    """Writes the diagnostic; code 1 if there is a FAIL, otherwise 0."""
    codes = {"OK": "1;32", "WARN": ORANGE, "FAIL": "1;31"}
    result = site_diagnostic(profile, service, extra_hosts)
    write_line("──── Site diagnosis (maintenance page, service, ports, nginx) ────")
    for level, finding, advice in result:
        tag = {"FAIL": TR("[FAIL]"), "WARN": TR("[WARN]")}.get(level, f"[{level}]")
        write_line(f"  {color_code(codes[level], tag) if color else tag} {finding}")
        if advice:
            write_line(f"         What to do: {advice}")
    failures = [r for r in result if r[0] == "FAIL"]
    if failures:
        write_line(f"  ⇒ {len(failures)} problems: fix them in the order above (the first is the most likely), then press the D key again.")
    else:
        write_line("  ⇒ Everything answers. If your browser still shows the maintenance page: Ctrl+Shift+R (cache), or purge the cache of the CDN / proxy in front of the site. A certificate error in the browser (net::ERR_CERT_…) is read in the « Certificate » lines above.")
    write_line("──── nginx configuration: versions and dates ────")          # 1.86
    for text_line in nginx_config_versions():
        write_line(text_line if color else ANSI_RE.sub("", text_line))
    return 1 if failures else 0


# ------------------------------------------------------------------------------------------------------------------
# Service, login history, stream
# ------------------------------------------------------------------------------------------------------------------
def load_profile(force):
    module = load_module("_profile")
    folder = os.path.join(SCRIPT_DIR, "apps")
    if module is None:
        return {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "APP_LOG_KIND": "log"}
    return module.charger_profil_app(folder, force)


def detect_service(profile):
    """(unit, namespace): first unit of DETECT_UNITS that exists; (None, '') otherwise."""
    for unit in (profile.get("DETECT_UNITS") or "erplibre.service erplibre_erplibre.service odoo.service").split():
        code, output = lancer(["systemctl", "list-unit-files", unit, "--no-legend"], 10)
        if code == 0 and any(l.split()[:1] == [unit] for l in output.splitlines()):
            ns = lancer(["systemctl", "show", "-p", "LogNamespace", "--value", unit], 10)[1].strip()
            return unit, ns
    return None, ""


# Odoo journal written to a FILE (logfile of its configuration, read by apps/_odoo_conf.py): apps/_odoo_journal.py gives each line the
# prefix of a systemd journal (Odoo's UTC time converted to local time): everything else in the program then works unchanged.
FILE_CONVERTER = os.path.join(SCRIPT_DIR, "apps", "_odoo_journal.py")
LOGS_MERGE = os.path.join(SCRIPT_DIR, "apps", "_logs_merge.py")          # 1.115 --log-nginx: streams merged in time order


def modules_on_disk(conf):
    """{module: (manifest version, folder)} for each folder of addons_path (Odoo configuration) that contains a __manifest__.py; the first folder of the list wins
    (like Odoo). Returns (modules, folders of addons_path not found)."""
    odoo_conf = load_module("_odoo_conf")
    raw = odoo_conf.valeur(conf, "addons_path") if odoo_conf and conf else ""
    modules, missing, database = {}, [], os.path.dirname(conf or "")
    for folder in [d.strip() for d in raw.split(",") if d.strip()]:
        folder = os.path.expanduser(folder)
        if not os.path.isabs(folder):
            folder = os.path.normpath(os.path.join(database, folder))
        if not os.path.isdir(folder):
            missing.append(folder)
            continue
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            manifest = os.path.join(folder, name, "__manifest__.py")
            if name in modules or not os.path.isfile(manifest):
                continue
            try:
                with open(manifest, encoding="utf-8", errors="replace") as f:
                    m = re.search(r"""["']version["']\s*:\s*["']([^"']+)["']""", f.read())
            except OSError:
                continue
            modules[name] = (m.group(1) if m else "", folder)
    return modules, missing


def full_version(version, series):
    """Manifest version completed like Odoo ("1.2.3" -> "18.0.1.2.3" when it does not start with the series)."""
    if not version:
        return ""
    return version if version == series or version.startswith(series + ".") else f"{series}.{version}"


def check_modules(odoo_db, conf, databases_seen):
    """Lines of the state of the Odoo modules at startup: are all the installed modules on disk (addons_path), at the installed version, without a pending update?
    Detail only for what is wrong; versions of the modules that are not Odoo S.A.'s. Returns a list of lines (empty if there is nothing to check)."""
    if odoo_db is None or not hasattr(odoo_db, "modules_etat") or not conf:
        return []
    disk, missing_folders = modules_on_disk(conf)
    lines = []
    if missing_folders:
        lines.append(color_code(ORANGE, "  ⚠ addons_path: folders not found: " + ", ".join(missing_folders[:5]) + (" …" if len(missing_folders) > 5 else "")))
    unreadable = []
    for database in databases_seen:
        state = odoo_db.modules_etat(database)
        if state is None:
            unreadable.append(database)
            continue
        kernel = next((m["version"] for m in state if m["nom"] == "base" and m["version"]), "")
        series = ".".join(kernel.split(".")[:2]) if kernel else ""
        installed = [m for m in state if m["etat"] in ("installed", "to upgrade", "to remove")]
        not_found = [m["nom"] for m in installed if m["nom"] not in disk]
        different = []
        for m in installed:
            if m["nom"] in disk and m["version"] and series:
                on_disk = full_version(disk[m["nom"]][0], series)
                if on_disk and on_disk != m["version"]:
                    different.append((m["nom"], m["version"], on_disk))
        pending = [(m["nom"], m["etat"]) for m in state if m["etat"] in ("to upgrade", "to install", "to remove")]
        good = not (not_found or different or pending or missing_folders)
        # ONE line per database: enough to see at a glance whether all is well; the detail appears only for what is wrong
        lines.append("  " + color_code("1", f"Odoo modules (database {database})") + " : " + color_code("1;36", str(len(installed))) + " installed modules"
                      + (f" · series {series}" if series else "") + color_code("90", f" · {len(disk)} on disk") + " · "
                      + (color_code("1;32", "✔ all present, at the installed version") if good else color_code("1;" + ORANGE, "⚠ to look at")))
        if not_found:
            lines.append("    " + color_code("1;31", f"✖ {len(not_found)} NOT FOUND on disk: ")
                          + ", ".join(not_found[:12]) + (" …" if len(not_found) > 12 else "")
                          + color_code("90", " — Odoo cannot load them: check addons_path or put the module back"))
        if different:
            lines.append("    " + color_code(ORANGE, f"⚠ {len(different)} versions different from the disk: ")
                          + " ; ".join(f"{n} installed {color_code('1;36', a)} ≠ disk {color_code('1;36', b)}" for n, a, b in different[:8]) + (" …" if len(different) > 8 else "")
                          + color_code("90", " — odoo -u NAME -d " + database + " (or odoo-update-module.sh)"))
        if pending:
            lines.append("    " + color_code(ORANGE, f"⚠ {len(pending)} pending: ") + ", ".join(f"{n} ({e})" for n, e in pending[:8])
                          + color_code("90", " — interrupted update or installation: restart with -u"))
        personal = [m for m in installed if "odoo s.a." not in m["auteur"].lower()]
        rlq = sorted((m for m in installed if m["nom"].lower().startswith("rlq")), key=lambda m: m["nom"])         # the Rencontres Linux Quebec modules: ALWAYS displayed, with their version
        if personal or rlq:
            others = [m for m in personal if not m["nom"].lower().startswith("rlq")]
            recent_ones = sorted((m for m in others if m.get("maj")), key=lambda m: (m["maj"], m["nom"]), reverse=True)[:5]
            lines.append("    " + color_code("33", "Non-Odoo S.A.") + " : " + color_code("1;36", str(len(personal))) + " modules"
                          + color_code("90", " — full table and sorting: M key or --modules"))
            width = max((len(m["nom"]) for m in rlq + recent_ones), default=0)

            def module_line(m):
                return "      " + color_code("1", m["nom"].ljust(width)) + "  " + color_code("36", (m["version"] or "?").ljust(14)) + " " + color_code("90", local_time(m["maj"]) if m.get("maj") else "")
            if rlq:
                lines.append("    " + color_code("1;32", "Modules rlq*") + " : " + color_code("1;36", str(len(rlq))) + " installed, with their version" + color_code("90", " (last modification, local time):"))
                lines += [module_line(m) for m in rlq]
            else:
                lines.append("    " + color_code(ORANGE, "No rlq* module installed") + color_code("90", " in this database"))
            if recent_ones:
                lines.append("    " + "Most recently modified among the others" + color_code("90", " (local time):"))
                lines += [module_line(m) for m in recent_ones]
    if unreadable:
        lines.append(color_code(ORANGE, "  ⚠ ") + color_code("1", "Odoo modules") + ": reading PostgreSQL is impossible for " + color_code("1;36", str(len(unreadable)))
                      + " databases" + color_code("90", " (root required, or database inaccessible)") + " : "
                      + ", ".join(color_code("1;33", b) for b in unreadable[:5]) + (" …" if len(unreadable) > 5 else ""))
    return lines


# Table of the installed modules (--modules, M key): sorted by name, modification date, creation date, version, author or state.
MODULES_SORTS = {"name": "nom", "date": "modification date", "created": "creation date", "version": "version", "author": "auteur", "state": "state"}
MODULES_SORT_LETTERS = {"n": "name", "d": "date", "c": "created", "v": "version", "a": "author", "e": "state"}
MODULES_SORT_DEFAULT = "date"
MODULES_DATES = ("date", "created")                  # natural order: from most recent to oldest


def read_modules_sort(text, default_value=(MODULES_SORT_DEFAULT, False, False)):
    """"d", "date", "-name", "N" (capital = reverse), "v p" (p: only the non-Odoo S.A. modules) -> (key, reverse, non_odoo); None if invalid.
    Natural order: alphabetical/ascending, except dates (recent first); "-" in front, or a capital, reverses. Empty: the default sort."""
    key_value, inverse, personal = default_value
    words = [m for m in re.split(r"[\s,;]+", (text or "").strip()) if m]
    for word in words:
        if word.lower() in ("p", "perso", "custom", "hors-odoo"):
            personal = True
            continue
        if word.lower() in ("all", "tous"):
            personal = False
            continue
        inv = word.startswith("-") or (len(word) == 1 and word.isupper())
        name = word.lstrip("-").lower()
        name = MODULES_SORT_LETTERS.get(name, name)
        if name not in MODULES_SORTS:
            return None
        key_value, inverse = name, inv
    return key_value, inverse, personal


def local_time(text):
    """"2026-10-14 20:11" (UTC, as Odoo's PostgreSQL records it) -> the same minute in the LOCAL time of this machine; a text that is not a date and time (date only, empty) is returned as is."""
    try:
        instant = datetime.datetime.strptime((text or "")[:16], "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return text or ""
    return instant.astimezone().strftime("%Y-%m-%d %H:%M")


def version_key(version):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", version or "")) or (0,)


def odoo_version(state):
    """Odoo version of a database: installed version of the "base" module (e.g. 18.0.1.3), "?" if unknown."""
    return next((m["version"] for m in state if m["nom"] == "base" and m["version"]), "?")


def custom_module(m):
    """Module that is not Odoo S.A.'s (author) or whose name starts with rlq (modules of Rencontres Linux Québec)."""
    return "odoo s.a." not in (m.get("auteur") or "").lower() or m["nom"].lower().startswith("rlq")


def modules_table(state, database, sort_by=(MODULES_SORT_DEFAULT, False, False), disk=None, limit=None, custom_header=None):
    """Lines of the table of the INSTALLED modules of a database (list of dicts name, state, version, author, updated, created), sorted. The modules that are not Odoo S.A.'s have their
    author in yellow; version in cyan; state "to upgrade" in orange, "to remove" in red. A module missing from the disk (addons_path) is marked ✖."""
    key_value, inverse, personal = sort_by
    installed = [m for m in state if m["etat"] in ("installed", "to upgrade", "to remove")]
    if personal:
        installed = [m for m in installed if "odoo s.a." not in m["auteur"].lower()]
    values = {"name": lambda m: m["nom"].lower(), "version": lambda m: version_key(m["version"]), "author": lambda m: (m["auteur"] or "").lower(),
               "state": lambda m: m["etat"], "date": lambda m: m.get("maj") or "", "created": lambda m: m.get("cree") or ""}
    with_value = [m for m in installed if values[key_value](m) not in ("", (0,))]
    without = [m for m in installed if m not in with_value]               # without a value (unknown date...): always at the end
    natural_reverse = key_value in MODULES_DATES
    with_value.sort(key=lambda m: (values[key_value](m), m["nom"]), reverse=natural_reverse != inverse)
    sort_lines = with_value + sorted(without, key=lambda m: m["nom"])
    total = len(sort_lines)
    n_rlq = 0
    if limit:        # the rlq* modules ALWAYS (all of them, with their version), then the `limit` latest other modules: custom ones (not Odoo S.A.) first, each group from most recent to oldest
        rlq = sorted((m for m in sort_lines if m["nom"].lower().startswith("rlq")), key=lambda m: m["nom"])
        others = sorted((m for m in sort_lines if not m["nom"].lower().startswith("rlq")), key=lambda m: not custom_module(m))[:limit]
        n_rlq, sort_lines = len(rlq), rlq + others
    direction = ("newest first" if not inverse else "oldest first") if key_value in MODULES_DATES else ("ascending" if not inverse else "descending")
    if custom_header:
        header = custom_header(n_rlq, len(sort_lines) - n_rlq, total, odoo_version(state))
    elif limit:
        header = (f"  rlq* modules: {color_code('1;36', str(n_rlq))} (always shown, with their version) then the {color_code('1;36', str(len(sort_lines) - n_rlq))} latest other installed modules out of {total}{' non-Odoo S.A.' if personal else ''} (base {database}, custom modules first) — Odoo "
                  + color_code("1;36", odoo_version(state)) + f" — sort: {MODULES_SORTS[key_value]} ({direction})")
    else:
        header = (f"  Installed modules (database {database}) : " + color_code("1;36", str(len(sort_lines))) + (" non-Odoo S.A." if personal else "")
                  + f" — sort: {MODULES_SORTS[key_value]} ({direction}) ; other sorts: --modules-sort name|date|created|version|author|state")
    if not sort_lines:
        return [header]
    columns = [("Nom", lambda m: ("✖ " if disk is not None and m["nom"] not in disk else "") + m["nom"][:42]), ("Version", lambda m: m["version"] or "?"),
                ("State", lambda m: m["etat"]), ("Modified", lambda m: local_time(m.get("maj"))), ("Seen on", lambda m: local_time(m.get("cree"))[:10]),
                ("Auteur", lambda m: (m["auteur"] or "")[:30])]
    widths = [max(len(heading), *(len(f(m)) for m in sort_lines)) for heading, f in columns]
    style = {"Version": "36", "Nom": "1"}
    res = [header, "  " + color_code("1;4", "  ".join(t.ljust(w) for (t, _), w in zip(columns, widths)).rstrip())]
    for m in sort_lines:
        cells = []
        for (heading, f), w in zip(columns, widths):
            text = f(m).ljust(w)
            if heading == "State":
                code = {"to upgrade": ORANGE, "to remove": "1;31"}.get(m["etat"])
            elif heading == "Auteur":
                code = "33" if "odoo s.a." not in (m["auteur"] or "").lower() else "90"
            elif heading == "Nom" and text.startswith("✖"):
                code = "1;31"
            else:
                code = style.get(heading)
            cells.append(color_code(code, text) if code else text)
        res.append("  " + "  ".join(cells).rstrip())
    return res


def display_width(text):
    """Columns taken on a terminal (colors ignored): a wide East Asian character (Chinese name…) takes 2, a combining mark 0 (1.82: names in Chinese shifted the columns)."""
    text = ANSI_RE.sub("", text)
    if text.isascii():
        return len(text)
    return sum(0 if unicodedata.combining(c) or unicodedata.category(c) in ("Mn", "Me", "Cf") else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def size_text(value):
    """1.121: the size of a line in at most 4 characters: "1234", then "2.9k", "600k", "4.5M" (decimal units: 1 k = 1 000 bytes); "-" unchanged."""
    if not value.isdigit():
        return value
    n = int(value)
    if n <= 9999:
        return str(n)
    for divisor, unit in ((1000, "k"), (1000000, "M"), (1000000000, "G")):
        v = n / divisor
        if round(v, 1) < 10:
            return f"{round(v, 1):.1f}{unit}"
        if round(v) < 1000:
            return f"{round(v)}{unit}"
    return f"{min(n // 1000000000, 999)}G"


def terminal_columns():
    """1.137: width of the terminal in columns ($COLUMNS first, then the terminal itself; 100 when unknown)."""
    try:
        return max(40, shutil.get_terminal_size((100, 24)).columns)
    except (OSError, ValueError):
        return 100


def terminal_rows():
    """1.120: height of the terminal in lines ($LINES first, then the terminal itself; 24 when unknown)."""
    try:
        return max(10, shutil.get_terminal_size((100, 24)).lines)
    except (OSError, ValueError):
        return 24


def terminal_columns():
    """Width of the terminal in columns ($COLUMNS first, then the terminal itself; 100 when unknown)."""
    try:
        return max(20, shutil.get_terminal_size((100, 24)).columns)
    except (OSError, ValueError):
        return 100


ANSI_SPLIT_RE = re.compile(r"(\x1b\[[0-9;]*m)")


def truncate_line(text_line, limit):
    """text_line cut to `limit` columns on screen (colors kept, wide characters count 2), ending with « … » and a color reset; unchanged if it fits (--truncate)."""
    if display_width(text_line) <= limit:
        return text_line
    stripped = text_line.rstrip(" ")                   # padding with spaces (lines that erase the status bar) is not content
    if display_width(stripped) <= limit:
        return stripped
    out, used, colored = [], 0, False
    for part in ANSI_SPLIT_RE.split(stripped):
        if ANSI_SPLIT_RE.fullmatch(part):
            out.append(part)
            colored = True
            continue
        for c in part:
            w = display_width(c)
            if used + w > limit - 1:
                return "".join(out) + "…" + ("\x1b[0m" if colored else "")
            out.append(c)
            used += w
    return "".join(out)


TAIL_RE = re.compile(r"(?:\[[^\]]*\]|\S+)\s+(?:\[[^\]]*\]|\S+)\s*$")      # last two words; "[banned: CrowdSec]" counts as ONE word (the URL stays visible)
TRUNCATE_AUTO = -2                                      # --truncate not given: on a terminal only (argparse would apply type=int to a text default)
ELLIPSIS = "…"                                         # 1.88 (1.123: one character): marker between the start of a shortened line and its last two words


def colored_suffix(text, start):
    """End of the colored `text` from its `start`-th visible character, preceded by the colors in effect at that point (shortened lines keep their colors)."""
    count, pos, active = 0, 0, ""
    for part in ANSI_SPLIT_RE.split(text):
        if ANSI_SPLIT_RE.fullmatch(part):
            active = "" if part in ("\x1b[0m", "\x1b[m") else active + part
        elif count + len(part) > start:
            return active + text[pos + start - count:]
        else:
            count += len(part)
        pos += len(part)
    return ""


def colored_prefix(text, limit):
    """Start of the colored `text` that takes at most `limit` columns (wide characters count 2), colors closed."""
    out, used, colored = [], 0, False
    for part in ANSI_SPLIT_RE.split(text):
        if ANSI_SPLIT_RE.fullmatch(part):
            out.append(part)
            colored = True
            continue
        for c in part:
            w = display_width(c)
            if used + w > limit:
                return "".join(out) + ("\x1b[0m" if colored else "")
            out.append(c)
            used += w
    return "".join(out) + ("\x1b[0m" if colored else "")


HTML_HEAD = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<title>{title}</title>\n"
             "<style>body{{background:#111;color:#ddd;margin:12px}} pre{{font:13px/1.35 monospace;white-space:pre}}</style>\n</head>\n<body>\n<pre>\n")
HTML_COLORS = {"30": "#666", "31": "#e5534b", "32": "#57ab5a", "33": "#c69026", "34": "#539bf5", "35": "#b083f0", "36": "#39c5cf", "37": "#ddd",
               "90": "#888", "91": "#ff7b72", "92": "#7ee787", "93": "#e3b341", "94": "#79c0ff", "95": "#d2a8ff", "96": "#56d4dd", "97": "#fff"}
HTML_LINE_WIDTH = 140           # 1.120: each line of the HTML copy is cut to this many characters (colours kept)


def ansi_to_html(text):
    """1.120: a line with its colour codes as HTML: one span per run of text with the same style (bold, underline, colours)."""
    import html as html_module
    out, style, opened = [], {}, False
    for part in ANSI_SPLIT_RE.split(text):
        if ANSI_SPLIT_RE.fullmatch(part):
            for code in (part[2:-1].split(";") if part[2:-1] else ["0"]):
                if code in ("0", ""):
                    style = {}
                elif code == "1":
                    style["font-weight"] = "bold"
                elif code == "4":
                    style["text-decoration"] = "underline"
                elif code in HTML_COLORS:
                    style["color"] = HTML_COLORS[code]
            continue
        if opened:
            out.append("</span>")
            opened = False
        if style:
            out.append('<span style="' + ";".join(f"{k}:{v}" for k, v in style.items()) + '">')
            opened = True
        out.append(html_module.escape(part))
    if opened:
        out.append("</span>")
    return "".join(out)


def html_line(text_line):
    """1.120: one journal line for the HTML copy: cut to HTML_LINE_WIDTH columns, colours kept."""
    return ansi_to_html(colored_prefix(text_line, HTML_LINE_WIDTH))


MESSAGE_START_RE = re.compile(r'"[A-Z]{3,9} ')                   # 1.91: start of the request of a werkzeug / nginx line ("GET  /url" with quotes)
COLUMN_PADDING_RE = re.compile(r" {3,}(?=\S)")                  # padding of a column: the message of an Odoo line starts after the last one


def message_start(plain):
    """1.91: index (in the uncolored line) where the MESSAGE starts: the request « "GET … » of a web line, otherwise the text after the last column padding
    (Odoo message after its padded logger); 0 when there is no column."""
    m = MESSAGE_START_RE.search(plain)
    if m:
        return m.start()
    runs = list(COLUMN_PADDING_RE.finditer(plain))
    return runs[-1].end() if runs else 0


def shorten_line(text_line, limit):
    """1.88 (--truncate, by default): a stream line longer than `limit` columns (a long URL…) becomes « start ... last two words », `limit` columns at most:
    the end of the line (the URL's last part, [banned: …], « ← slow ») stays visible. Last two words wider than a third of the line: only their end is kept.
    1.91: only the MESSAGE (the URL, the text of an Odoo message) is cut — the columns before it (time, address, name, numbers, logger) are never squeezed
    nor cut, so they stay aligned with the other lines. A screen too narrow for the columns themselves: the end of the line is cut (« … »)."""
    if display_width(text_line) <= limit:
        return text_line
    text_line = text_line.rstrip(" ")
    plain = ANSI_RE.sub("", text_line)
    if display_width(plain) <= limit:
        return text_line
    start = message_start(plain)
    room = limit - display_width(plain[:start])
    if limit < 24 or room < 20:
        return truncate_line(text_line, limit)
    m = TAIL_RE.search(plain, start)
    if not m:                                                               # one single word (no end to show): cut at the end
        return truncate_line(text_line, limit)
    tail_start, tail_max = max(m.start(), start), max(10, min(limit // 3, (room - len(ELLIPSIS) - 2) // 2))      # the room left after the columns: half for the start of the message, half for its end
    while tail_start < len(plain) and display_width(plain[tail_start:]) > tail_max:
        tail_start += 1
    tail = colored_suffix(text_line, tail_start)
    head = colored_prefix(text_line, limit - display_width(plain[tail_start:]) - len(ELLIPSIS))
    return head + color_code("90", ELLIPSIS) + tail      # 1.119: no space around "..."


def underline_line(text_line, width=None):
    """1.88: the line underlined (one line out of N, to follow a line across the screen), colors kept: each color reset is followed by the underline again.
    1.91: `width` (the terminal's $COLUMNS): a shorter line is underlined up to the END of the screen line (underlined spaces)."""
    if not COLOR or not text_line:
        return text_line
    padding = " " * max(0, (width or 0) - display_width(text_line))
    return "\x1b[4m" + re.sub(r"\x1b\[0?m", "\x1b[0;4m", text_line) + padding + "\x1b[0m"


REC_WIDTH = 4                                           # 1.93: "REC" occupies the 3 columns from $COLUMNS - 4 (0-based) and one column stays free at the end
REC_STYLE = "1;97;41"                                   # bold white on red (explicit text AND background: readable on any theme)
STEPS_LINE_STYLE = "30;107"                              # 1.99: steps line (F key): black text on white background, both explicit (white reverse video)
STEP_STYLE = "1;30;46"                                   # 1.95: step marker (N key): bold black on cyan, explicit background


def rec_mark(text_line, columns=None):
    """1.93: a stream line shown while a test is being recorded (R key): « REC » at column $COLUMNS - 4 of its LAST screen row (a line wider than one row keeps
    the marker on its last row). A line whose text would run into the marker is cut (« … »); the width is read again for each line (resized window)."""
    columns = columns or terminal_columns()
    start = max(0, columns - REC_WIDTH)
    width = display_width(text_line)
    rows = (width - 1) // columns if width > 0 else 0               # full screen rows before the last one
    last = width - rows * columns                                   # visible columns on the last row
    if last > start:
        text_line = truncate_line(text_line, rows * columns + start)
        width = display_width(text_line)
        rows = (width - 1) // columns if width > 0 else 0
        last = width - rows * columns
    return text_line + " " * max(0, start - last) + color_code(REC_STYLE, "REC")


def steps_line_text(steps, columns):
    """1.99 (F key, --steps-line): the steps of the recording on ONE line: number, state (✔ ended, ▶ open), description cut at 24 columns.
    If that does not fit the width, the descriptions are left out and only the last step is shown in full."""
    if not steps:
        return TR("Steps: none yet (N starts one)")
    mark = lambda s: "▶" if s["end"] is None else "✔"
    head = TR("Steps") + f" ({len(steps)}): "
    parts = []
    for s in steps:
        description = s["description"] or TR("(no description)")
        parts.append(f"{s['n']}{mark(s)} " + (description if len(description) <= 24 else description[:23] + "…"))
    text = head + " · ".join(parts)
    if display_width(text) <= columns:
        return text
    last = steps[-1]
    compact = head + " · ".join(f"{s['n']}{mark(s)}" for s in steps)
    return compact + " — " + f"{last['n']}{mark(last)} {last['description'] or ''}"


def truncate_text(text, limit):
    """Each line of `text` cut by truncate_line (limit: N columns; 0 = 2 × the width of the terminal, read again at each write: a resized window is followed)."""
    width = limit if limit and limit > 0 else 2 * terminal_columns()
    return "\n".join(truncate_line(l, width) if l else l for l in text.split("\n"))


ODOO_USERS_CACHE = {"when": 0.0, "state": {"banned": {}, "watched": {}}}


def registered_odoo_users():
    """Register of the banned / watched Odoo accounts (apps/_odoo_users.py), reread at most every 60 seconds; empty if the component is missing."""
    now_dt = time.time()
    if now_dt - ODOO_USERS_CACHE["when"] >= 60:
        ODOO_USERS_CACHE["when"] = now_dt
        try:
            spec = importlib.util.spec_from_file_location("_odoo_users", os.path.join(SCRIPT_DIR, "apps", "_odoo_users.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            ODOO_USERS_CACHE["state"] = module.state()
        except Exception:
            ODOO_USERS_CACHE["state"] = {"banned": {}, "watched": {}}
    return ODOO_USERS_CACHE["state"]


def odoo_logged_in(presence, now_dt):
    """[(name, address, seconds since the last activity)] of the people CURRENTLY logged in to Odoo (neither logged out nor idle since --idle), the most recent first."""
    if presence is None:
        return []
    res = [(e["nom"], e["ip"], now_dt - e["last_seen"]) for e in presence.state.values()
           if not e["logged_out"] and now_dt - e["last_seen"] < presence.idle_state]
    return sorted(res, key=lambda x: x[2])


def ssh_users():
    """{account: number of SSH sessions} from the sshd processes (« sshd: USER@pts/0 », « sshd-session: USER@notty » for sftp / scp; the « [priv] » half is not
    counted): also sees the sessions without a terminal, that who does not list (1.83). {} if ps is absent."""
    code, output = lancer(["ps", "-eo", "args="], 10)
    counts = Counter()
    for text_line in output.splitlines() if code == 0 else []:
        m = re.match(r"\s*sshd(?:-session)?: (\S+?)@(\S+)", text_line)
        if m:
            counts[m.group(1)] += 1
    return dict(counts)


def ssh_sessions():
    """[(account, terminal, "YYYY-MM-DD HH:MM" (local time), origin address)] of the open SSH sessions (who command); [] if who is absent or sees none."""
    code, output = lancer(["who"], 10)
    res = []
    for text_line in output.splitlines() if code == 0 else []:
        m = re.match(r"(\S+)\s+(\S+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?:\s+\((.*)\))?", text_line)
        if m and (m.group(4) or "").strip():
            res.append((m.group(1), m.group(2), m.group(3), m.group(4).strip()))
    return res


SSH_PORTS_CACHE = {"when": 0.0, "ports": None}      # ssh_ports(): the ports hardly ever change, looked up at most every 5 minutes


def ssh_ports(now_dt=None):
    """Sorted list of the TCP ports the SSH server listens on. Sources, in order: the listening sockets owned by sshd (ss -Htlnp, needs root to see the
    process), then the active configuration (sshd -T), then the "Port" lines of /etc/ssh/sshd_config and sshd_config.d/*.conf; 22 if nothing tells."""
    now_dt = now_dt or time.time()
    if SSH_PORTS_CACHE["ports"] is not None and now_dt - SSH_PORTS_CACHE["when"] < 300:
        return SSH_PORTS_CACHE["ports"]
    ports = set()
    code, output = lancer(["ss", "-Htlnp"], 10)
    for text_line in output.splitlines() if code == 0 else []:
        fields = text_line.split()
        if len(fields) >= 5 and "sshd" in text_line and fields[3].rpartition(":")[2].isdigit():
            ports.add(int(fields[3].rpartition(":")[2]))
    if not ports:
        code, output = lancer(["sshd", "-T"], 10)
        ports = {int(m.group(1)) for m in re.finditer(r"(?m)^port (\d+)\s*$", output)} if code == 0 else set()
    if not ports:
        for path in ["/etc/ssh/sshd_config"] + sorted(glob.glob("/etc/ssh/sshd_config.d/*.conf")):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    ports |= {int(m.group(1)) for m in re.finditer(r"(?mi)^\s*Port\s+(\d+)\b", f.read())}
            except OSError:
                continue
    SSH_PORTS_CACHE.update(when=now_dt, ports=sorted(p for p in ports if 0 < p < 65536) or [22])
    return SSH_PORTS_CACHE["ports"]


def logged_in_lines(presence, now_dt=None):
    """Two lines for the periodic reports: users logged in to Odoo, SSH sessions (+ TCP connections established on the SSH port(s), see ssh_ports())."""
    now_dt = now_dt or time.time()
    odoo = odoo_logged_in(presence, now_dt)
    res = []
    if presence is not None:
        res.append("  Connected to Odoo: " + color_code("1;36", str(len(odoo))) + (" — " + " ; ".join(f"{n} [{ip}] (active {duration(secs)} ago)" for n, ip, secs in odoo[:15])
                                                                         + (f"; … +{len(odoo) - 15}" if len(odoo) > 15 else "") if odoo else ""))
    ssh = ssh_sessions()
    ports = ssh_ports()
    code, output = lancer(["ss", "-Htn", "state", "established", "( " + " or ".join(f"sport = :{p}" for p in ports) + " )"], 10)
    tcp = len([l for l in output.splitlines() if l.strip()]) if code == 0 else None
    users = ssh_users()
    for u, _t, _d, _h in ssh:
        users.setdefault(u, 0)
    for u in users:                                    # who may see more terminals than ps lists (other namespace): the larger count wins
        users[u] = max(users[u], sum(1 for x in ssh if x[0] == u))
    sessions = sum(users.values())
    by_user = ", ".join(f"{u} " + color_code("1;36", f"×{n}") for u, n in sorted(users.items(), key=lambda x: (-x[1], x[0])))
    res.append("  Connected over SSH: " + color_code("1;36", str(sessions)) + (f" ({by_user})" if users else "")
               + (" — " + " ; ".join(f"{u} from {h} (opened {d}, {t})" for u, t, d, h in ssh[:15]) if ssh else "")
               + (f" · established TCP connections: {tcp} " + (f"(SSH port {ports[0]})" if len(ports) == 1 else "(SSH ports " + ", ".join(map(str, ports)) + ")")
                  if tcp is not None else ""))
    return res


MAIL_SENT_RE = re.compile(r"Mail \(mail\.mail\) with ID (\d+) and Message-Id '([^']*)' from '[^']*' to (?:\(redacted\) )?'([^']*)' successfully sent")
MAIL_TOTAL_RE = re.compile(r"Total emails tried by SMTP: 1\s*$")
MAIL_DELETED_RE = re.compile(r"User #\d+ deleted mail\.mail records with IDs: \[([\d, ]+)\]\s*$")      # 1.88: auto_delete right after the sending
MAIL_CACHE = {}


def mail_sent_text(L, people):
    """1.84: Odoo's « Mail (mail.mail) with ID 7573 and Message-Id '<…>' from '…' to (redacted) 'a***n@x.ca' successfully sent » becomes « E-mail #7573 sent to
    Ana Tremblay (a***n@x.ca) — « subject » — registration Ana Tremblay — Event »: recipients and subject read in PostgreSQL (READ-ONLY, the Message-Id must match:
    never the e-mail of another database). The address stays as Odoo wrote it (masked). None if the line is not a sent e-mail or if nothing is found."""
    m = MAIL_SENT_RE.search(L.text or "")
    odoo_db = getattr(people, "odoo_db", None) if people is not None else None
    if not m or odoo_db is None or not hasattr(odoo_db, "mail_detail"):
        return None
    mail_id, message_id, address = m.groups()
    if mail_id in MAIL_CACHE:
        return MAIL_CACHE[mail_id]
    databases = [L.database] if L.database and re.fullmatch(r"[\w.-]+", L.database) else []
    databases += [d for d in sorted(getattr(people, "databases_seen", None) or []) if d not in databases]
    if not databases and hasattr(odoo_db, "bases_odoo"):     # no sign-in seen yet: the Odoo databases of this server (looked up once)
        if "databases" not in MAIL_CACHE:
            MAIL_CACHE["databases"] = odoo_db.bases_odoo() or []
        databases = list(MAIL_CACHE["databases"])
    detail = {}
    for attempt in range(2):                         # 1.88: not found = maybe not visible yet (other transaction): one more try 0.5 s later
        for database in databases[:5]:
            try:
                try:
                    detail = odoo_db.mail_detail(database, mail_id, message_id, 5, address) or {}
                except TypeError:                    # older apps/_odoo_db.py (before 1.19): no `address` argument
                    detail = odoo_db.mail_detail(database, mail_id, message_id, 5) or {}
            except Exception:  # noqa: BLE001 - a lookup must never stop the reader thread (the raw Odoo line stays)
                detail = {}
            if detail:
                break
        if detail or attempt or not databases:
            break
        time.sleep(0.5)
    text = None
    if detail:
        who = ", ".join(detail["recipients"][:5]) + (f" +{len(detail['recipients']) - 5}" if len(detail["recipients"]) > 5 else "")
        text = (TR("E-mail #{id} sent to {who}").format(id=mail_id, who=raw(who or address)) + (f" ({address})" if who and address else "")
                + (" — « " + raw(detail["subject"]) + " »" if detail["subject"] else "")
                + (" — " + (TR("Registration: ") + raw(detail["record"][len("registration "):]) if detail["record"].startswith("registration ") else raw(detail["record"]))
                   if detail["record"] else ""))
    if len(MAIL_CACHE) > 500:
        MAIL_CACHE.clear()
    MAIL_CACHE[mail_id] = text
    return text


def ticket_report(rows):
    """I key (1.84): registrations grouped by event, then by ticket, each ticket with THE survey that confirms it (rlq_survey_id of the ticket); per ticket,
    the count of confirmed / unfinished / missing surveys; per registration, the state of ITS survey, and an answer to another survey pointed out (never
    counted as a confirmation: last year's survey, a test, the survey of another ticket). Texts translated BEFORE coloring (see numbers())."""
    if not rows:
        return ["    none"]
    out = []
    width = max(display_width(r["name"]) for r in rows)

    def day(t):
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
    groups = OrderedDict()
    for r in rows:
        groups.setdefault((r["event_id"], r["event"], r["event_start"]), OrderedDict()).setdefault((r["ticket_id"], r["ticket"], r["survey_id"], r["survey"]), []).append(r)
    for (_eid, event, start), tickets in groups.items():
        out.append("    " + color_code("1", raw(event)) + (f"  ({time.strftime('%Y-%m-%d', time.localtime(start))})" if start else ""))
        for (_tid, ticket, survey_id, survey), regs in tickets.items():
            active = [r for r in regs if r["state"] != "cancel"]
            done = sum(1 for r in active if r["answer"] and r["answer"]["state"] == "done")
            ongoing = sum(1 for r in active if r["answer"] and r["answer"]["state"] != "done")
            missing = len(active) - done - ongoing
            head = "      " + (TR("Ticket « {ticket} »").format(ticket=raw(ticket)) if ticket else TR("Without ticket"))
            if survey_id:
                head += (TR(" → survey « {survey} »: {n} active registrations — ").format(survey=raw(survey), n=len(active))
                         + color_code("1;32", TR("{n} confirmed").format(n=done)) + ", "
                         + color_code(ORANGE if ongoing else "90", TR("{n} unfinished").format(n=ongoing)) + ", "
                         + color_code(STYLES["error"] if missing else "90", TR("{n} without survey").format(n=missing)))
            else:
                head += color_code("90", TR(": no survey linked to this ticket — {n} active registrations").format(n=len(active)))
            out.append(head)
            for r in regs:
                left = f"        {day(r['when'])}  {raw(r['name'])}{' ' * (width - display_width(r['name']))}  ({r['state']})"
                if r["state"] == "cancel":
                    out.append(color_code("90", left + "  " + TR("cancelled")))
                    continue
                if not survey_id:
                    out.append(left)
                    continue
                a, o = r["answer"], r["other"]
                if a:
                    other_name = TR(" — answered as {name}").format(name=raw(a["name"])) if a["name"] and a["name"].lower() != r["name"].lower() else ""
                    state = color_code("1;32", TR("✔ survey completed")) if a["state"] == "done" else color_code(ORANGE, TR("⚠ survey NOT finished"))
                    out.append(f"{left}  {state} {day(a['when'])}{other_name}")
                else:
                    txt = color_code(STYLES["error"], TR("✖ no survey of this ticket — registration not confirmed"))
                    if o:
                        txt += color_code(ORANGE, TR(" (answered ANOTHER survey, not counted: « {title} », {when}, {state})").format(title=raw(o["title"]), when=day(o["when"]), state=o["state"]))
                    out.append(f"{left}  {txt}")
    return out


def rlq_group_label(groupe):
    """Nom d'un groupe RLQ* suivi de son identifiant « #12 » et de sa catégorie « [Événements] » quand Odoo les fournit (v1.103) : deux groupes qui portent
    le même nom se distinguent ainsi. Sans ces champs (données sans identifiant), seul le nom est écrit, comme avant."""
    texte = groupe["nom"]
    if "id" in groupe:
        texte += f" #{groupe['id']}"
    if groupe.get("categorie"):
        texte += f" [{groupe['categorie']}]"
    return texte


def rlq_group_columns(grouped, columns=None):
    """The groups as « RLQ23-Bénévole = 11 » (1.85: no « member(s) » word, no gap between the name and its number), in 4 columns on a wide terminal, 2 on
    a medium one, 1 otherwise; read from top to bottom, balanced columns; cells padded by display width (Chinese names aligned)."""
    cells = [rlq_group_label(g) + " = " + color_code("1;32" if g["membres"] else "90", str(g["membres"])) for g in grouped]
    cell_w = max(display_width(c) for c in cells)
    columns = columns or terminal_columns()
    n = next((k for k in (4, 2) if 4 + k * cell_w + (k - 1) * 4 <= columns), 1)
    n = min(n, len(cells)) if len(cells) > 1 else 1
    base, extra = divmod(len(cells), n)                         # balanced columns: 9 groups on 4 columns = 3 + 2 + 2 + 2 (never an empty column)
    starts = [c * base + min(c, extra) for c in range(n + 1)]
    res = []
    for r in range(base + (1 if extra else 0)):
        row = [cells[starts[c] + r] for c in range(n) if starts[c] + r < starts[c + 1]]
        res.append("    " + "    ".join([x + " " * (cell_w - display_width(x)) for x in row[:-1]] + [row[-1]]))
    return res


def rlq_group_lines(odoo_db, databases_seen):
    """Number of members (active accounts) of each RLQ* group of Odoo, per database: G key of the menu and end summary (Ctrl-C). Read-only in PostgreSQL."""
    if odoo_db is None or not hasattr(odoo_db, "groupes_rlq"):
        return ["  RLQ* groups: reading PostgreSQL is not possible for this application."]
    if not databases_seen:
        return ["  RLQ* groups: no Odoo database found (PostgreSQL unreachable: root required?)."]
    res = []
    for database in databases_seen:
        grouped = odoo_db.groupes_rlq(database)
        if grouped is None:
            res.append(f"  RLQ* groups (database {database}) : reading PostgreSQL is impossible (root required, or database inaccessible).")
        elif not grouped:
            res.append("  " + color_code("1", f"RLQ* groups (base {database})") + " : " + color_code(ORANGE, "no group whose name starts with RLQ"))
        else:
            total = sum(g["membres"] for g in grouped)
            res.append("  " + color_code("1", f"RLQ* groups (base {database})") + " : " + color_code("1;36", str(len(grouped))) + " groups, "
                       + color_code("1;36", str(total)) + " memberships" + color_code("90", " (active accounts):"))
            res += rlq_group_columns(grouped)
    return res


def module_lines(odoo_db, conf, databases_seen, sort_by, limit=None):
    """Table(s) of the installed modules of each database; clear messages when reading is impossible."""
    if odoo_db is None or not hasattr(odoo_db, "modules_etat"):
        return ["  Odoo modules: cannot read PostgreSQL for this application."]
    disk = modules_on_disk(conf)[0] if conf else None
    if not databases_seen:
        return ["  Odoo modules: no Odoo database found (PostgreSQL unreachable: root required?)."]
    res = []
    for database in databases_seen:
        state = odoo_db.modules_etat(database)
        if state is None:
            res.append(f"  Odoo modules (database {database}) : reading PostgreSQL is impossible (root required, or database inaccessible).")
            continue
        res += modules_table(state, database, sort_by, disk, limit) + [""]
    return res[:-1] if res and res[-1] == "" else res


def customs_tracking_lines(odoo_db, conf, databases_seen, sort_by=None):
    """Display at STARTUP (with --modules-startup only): "Tracking of custom modules not standard to Odoo" — the rlq* modules first (all of them, with their version), then
    the other modules that are not Odoo S.A.'s, sorted according to `sort_by` (--modules-sort: name, date, created, version, author, state; "-" in front = reverse order).
    Read from PostgreSQL (root required): otherwise a line explains why nothing is displayed."""
    key_value, inverse = (sort_by or (MODULES_SORT_DEFAULT, False, True))[:2]
    if odoo_db is None or not hasattr(odoo_db, "modules_etat"):
        return ["Tracking of custom (non-standard) Odoo modules: reading PostgreSQL is impossible for this application."]
    databases_seen = databases_seen or odoo_db.bases_odoo() or []
    if not databases_seen:
        return ["Tracking of custom (non-standard) Odoo modules: no database found (PostgreSQL unreachable: root required?) — press L to retry."]
    disk = modules_on_disk(conf)[0] if conf else None
    res = []
    for database in databases_seen:
        state = odoo_db.modules_etat(database)
        if state is None:
            res.append(f"Tracking of custom (non-standard) Odoo modules (database {database}) : reading PostgreSQL is impossible (root required, or database inaccessible).")
            continue
        customs = [m for m in state if m["etat"] in ("installed", "to upgrade", "to remove") and custom_module(m)]
        header = lambda n_rlq, n_others, total, v, database=database: (f"Tracking of custom (non-standard) Odoo modules (database {database}, Odoo {color_code('1;36', v)}) : {color_code('1;36', str(n_rlq))} modules rlq* "
                                                                 f"(first, with their version) then {color_code('1;36', str(n_others))} others not by Odoo S.A.")
        res += modules_table(customs + [m for m in state if m["nom"] == "base"], database, (key_value, inverse, True), disk, len(customs), header)
    return res


def odoo_journal_file(profile):
    """Odoo journal file (logfile of its configuration) if it exists, otherwise None: the systemd journal is then to be read."""
    file_path = profile.get("ODOO_LOGFILE") or ""
    return file_path if file_path and profile.get("APP_LOG_KIND") != "file" and os.path.isfile(file_path) and os.path.isfile(FILE_CONVERTER) else None


def journal_epoch(raw):
    """1.112: instant (epoch seconds) of a line of "journalctl -o short-iso-precise", or None when the line has no such header."""
    m = JOURNAL_RE.match(raw or "")
    if not m:
        return None
    a, mo, j, h, mi, s, us, offset, minutes = m.groups()[:9]
    try:
        zone = datetime.timezone(datetime.timedelta(hours=int(offset), minutes=(-1 if offset[0] == "-" else 1) * int(minutes or 0)))
        return datetime.datetime(int(a), int(mo), int(j), int(h), int(mi), int(s), int(us), tzinfo=zone).timestamp()
    except ValueError:
        return None


def days_window(days):
    """1.112: journalctl arguments for the last DAYS days. Whole days keep the form "-N days"; fractions (0.1 = 2.4 hours) become an epoch."""
    if float(days).is_integer():
        return ["--since", f"-{int(days)} days"]
    return ["--since", f"@{math.floor(time.time() - days * 86400)}"]


def read_history(people, service, ns, days, file_path=None, since=None, until=None):
    """Successful logins of the systemd journal (the DAYS last days, fractions allowed; 0 = the whole history) -> table of people;
    number of known addresses. 1.112: `since` / `until` (epoch seconds, from --since / --until) replace DAYS when given.
    `file`: Odoo journal as a file (logfile) rather than the systemd journal."""
    start = since if since is not None else (time.time() - days * 86400 if days else None)
    if file_path:
        code, output = lancer([sys.executable, FILE_CONVERTER, file_path, "+1", "0"], 600)
        for text_line in output.splitlines():
            m = HISTORY_RE.match(text_line)
            if not (m and "Login successful for" in text_line):
                continue
            when = journal_epoch(text_line)
            if when is None:
                kept = start is None and until is None
            else:
                kept = (start is None or when >= start) and (until is None or when < until)
            if kept:
                people.ajouter(m.group(4), m.group(2), m.group(3), m.group(1))
        return len(people.par_ip)
    window = (["--since", f"@{math.floor(since)}"] if since is not None else (days_window(days) if days else [])) \
        + (["--until", f"@{math.ceil(until)}"] if until is not None else [])
    cmd = ["journalctl", "-u", service, "-q", "--no-pager", "-o", "short-iso"] + window \
        + ["-g", "Login successful for"] + (["--namespace", ns] if ns else [])
    code, output = lancer(cmd, 600 if not (days or since is not None) else 180)
    for text_line in output.splitlines():
        m = HISTORY_RE.match(text_line)
        if m:
            people.ajouter(m.group(4), m.group(2), m.group(3), m.group(1))
    return len(people.par_ip)


def journal_options(args):
    """1.112: journalctl options of the stream: time window (--since, --until, epoch values set by main), --no-hostname,
    --grep (case-sensitive only when the pattern has an uppercase letter, as in journalctl's smart case)."""
    options_ = []
    if getattr(args, "since_epoch", None) is not None:
        options_ += ["--since", f"@{math.floor(args.since_epoch)}"]
    if getattr(args, "until_epoch", None) is not None:
        options_ += ["--until", f"@{math.ceil(args.until_epoch)}"]
    if getattr(args, "no_hostname", False):
        options_.append("--no-hostname")
    if getattr(args, "grep", None):
        options_ += ["-g", args.grep, f"--case-sensitive={'yes' if args.grep_sensitive else 'no'}"]
    return options_


def nginx_log_files(profile):
    """1.115 --log-nginx: the access and error logs of the site (ACCESS_LOGS and ERROR_LOGS of the profile, in NGINX_DIR); existing files only."""
    found = []
    for key in ("ACCESS_LOGS", "ERROR_LOGS"):
        for pattern in (profile.get(key) or "").split():
            found += sorted(glob.glob(os.path.join(NGINX_DIR, pattern)))
    return [f for f in OrderedDict.fromkeys(found) if os.path.isfile(f)]


def stream_command(args, profile, service, ns):
    """Command that produces the stream: journalctl (systemd journal), the converter of the Odoo file journal, or tail (file journals,
    BigBlueButton). 1.115 --log-nginx: the nginx logs of the site are merged with it in time order (apps/_logs_merge.py)."""
    nginx_files = nginx_log_files(profile) if profile.get("APP_LOG_KIND") != "file" else []   # 1.116: always read (key x shows them); BigBlueButton: as before
    if profile.get("APP_LOG_KIND") == "file":
        files_read = []
        for pattern in (profile.get("APP_LOG_FILES") or "").split():
            files_read += sorted(glob.glob(pattern))
        if not nginx_files:                                  # BigBlueButton: its nginx logs are followed here, unless merged below
            for pattern in (profile.get("ACCESS_LOGS") or "").split():
                files_read += sorted(glob.glob(os.path.join(NGINX_DIR, pattern)))
        files_read = [f for f in OrderedDict.fromkeys(files_read) if os.path.isfile(f)]
        base = (["tail", "-n", str(args.lines)] + (["-F"] if not args.no_follow else []) + files_read) if files_read else None
    else:
        file_path = odoo_journal_file(profile)
        if file_path:
            base = [sys.executable, "-u", FILE_CONVERTER, file_path, str(args.lines), "0" if args.no_follow else "1"]
        else:
            cmd = ["journalctl", "--lines", str(args.lines), "--no-pager", "-u", service, "-o", "short-iso-precise"]
            if not args.no_follow:
                cmd.insert(3, "--follow")
            base = cmd + journal_options(args) + (["--namespace", ns] if ns else [])
    if not nginx_files:
        return base
    merge = [sys.executable, "-u", LOGS_MERGE, "--lines", str(args.lines)] + (["--no-follow"] if args.no_follow else [])
    if getattr(args, "since_epoch", None) is not None:
        merge.append(f"--since={args.since_epoch}")
    if getattr(args, "until_epoch", None) is not None:
        merge.append(f"--until={args.until_epoch}")
    if getattr(args, "grep", None):
        merge += [f"--grep={args.grep}"] + (["--grep-sensitive"] if args.grep_sensitive else [])
    return merge + ["--nginx"] + nginx_files + ["--"] + (base or [])


def is_failed_request(L):
    """Entry "ERROR odoo.sql_db: bad query": its cause is in the NEXT line (concurrent update conflict = harmless)."""
    return L.level == "ERROR" and L.logger == "odoo.sql_db" and L.text.startswith("bad query")


TIME_UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
              "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "d": 86400, "day": 86400, "days": 86400,
              "w": 604800, "week": 604800, "weeks": 604800}
RELATIVE_TIME_RE = re.compile(r"^([+-]?)\s*(\d+(?:[.,]\d+)?)\s*([a-z]+)\s*(ago)?$", re.IGNORECASE)
ABSOLUTE_TIME_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,6}))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$", re.IGNORECASE)
TIME_OF_DAY_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _zone_of(text):
    """Time zone of "Z" or "+HH:MM" / "-HHMM" (None when absent)."""
    if not text:
        return None
    if text.upper() == "Z":
        return datetime.timezone.utc
    digits = text.replace(":", "")
    return datetime.timezone(datetime.timedelta(hours=int(digits[1:3]), minutes=int(digits[3:5])) * (-1 if digits[0] == "-" else 1))


def _epoch(naive, zone=None):
    """Epoch seconds of a naive date: in ZONE, else in UTC with --utc, else in local time."""
    if zone is None and TIME_UTC:
        zone = datetime.timezone.utc
    if zone is not None:
        naive = naive.replace(tzinfo=zone)
    return naive.timestamp()


def parse_time(text, end=False):
    """1.112: instant (epoch seconds) of a --since / --until value: "now", "today", "yesterday", "@EPOCH", "HH:MM[:SS]" (today),
    "YYYY-MM-DD [HH:MM[:SS]] [Z or +HH:MM]", or relative: "-2h", "+1 day", "0.5 hour", "3 days ago" (units s, min, h, d, w and long forms).
    Without a time zone: local time, or UTC with --utc. A date alone is the start of its day, or the start of the NEXT day for --until
    (so that the whole day is included). Raises ValueError for anything else."""
    value = (text or "").strip()
    low = value.lower()
    if low == "now":
        return time.time()
    if low.startswith("@"):
        return float(value[1:])
    today = (datetime.datetime.now(datetime.timezone.utc) if TIME_UTC else datetime.datetime.now()).date()
    if low in ("today", "yesterday"):
        day = today - datetime.timedelta(days=1 if low == "yesterday" else 0)
        return _epoch(datetime.datetime(day.year, day.month, day.day))
    m = TIME_OF_DAY_RE.match(value)
    if m:
        h, mi, s = m.groups()
        return _epoch(datetime.datetime(today.year, today.month, today.day, int(h), int(mi), int(s or 0)))
    m = ABSOLUTE_TIME_RE.match(value)
    if m:
        y, mo, d, h, mi, s, frac, zone_text = m.groups()
        if h is None:
            start = datetime.datetime(int(y), int(mo), int(d))
            if end:
                start += datetime.timedelta(days=1)
            return _epoch(start, _zone_of(zone_text))
        micro = int((frac or "0").ljust(6, "0")[:6])
        return _epoch(datetime.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0), micro), _zone_of(zone_text))
    m = RELATIVE_TIME_RE.match(value)
    if m:
        sign, amount, unit, _ago = m.groups()
        if unit.lower() not in TIME_UNITS:
            raise ValueError(f"unknown unit: {unit}")
        delta = float(amount.replace(",", ".")) * TIME_UNITS[unit.lower()]
        return time.time() + delta if sign == "+" else time.time() - delta
    raise ValueError(f"unrecognized time: {text}")


def window_keep(L, state, options):
    """1.112 --since, --until, --grep: is the line displayed? --grep tests each line (the message); --since and --until use the time header.
    A line without time header (Python trace, BigBlueButton) follows the time window of the previous timed line."""
    if options["grep"] is not None and options["grep"].search(L.text or "") is None:
        return False
    if L.instant is None:
        return state.get("window_ok", True)
    state["window_ok"] = (options["since"] is None or L.instant >= options["since"]) and (options["until"] is None or L.instant < options["until"])
    return state["window_ok"]


def country_keep(L, ips, pays, state, options):
    """1.112 --country / --exclude-country: is the line displayed according to the country of its FIRST address (the client)? A line with
    neither time header nor address follows the previous decision. A timed line without address: kept only without --country.
    An address without known country: dropped by --country, kept by --exclude-country."""
    wanted, unwanted = options["countries"], options["exclude_countries"]
    if not wanted and not unwanted:
        return True
    if L.ts_txt is None and not ips:
        return state.get("country_ok", True)
    if ips:
        code = (pays.get(ips[0][0]) or "").upper()
        ok = (not wanted or code in wanted) and not (unwanted and code in unwanted)
    else:
        ok = not wanted
    state["country_ok"] = ok
    return ok


class Bans:
    """CURRENTLY banned addresses: fail2ban (jails) and CrowdSec (ipsets crowdsec-blocklist-v4 / -v6 of sync-crowdsec-blocklist.sh; the "nomatch" entries are
    exceptions). Read at startup then every 60 s. Root (or « sudo -n » for the advanced commands) is needed; without fail2ban-client or readable ipset: no label, never an error."""
    DELAY = 60
    IPSETS = ("crowdsec-blocklist-v4", "crowdsec-blocklist-v6")

    def __init__(self):
        self.lock = threading.Lock()
        self.f2b = None                      # set of ipaddress, or None (unreadable source)
        self.cs = None                       # (addresses, networks, exceptions), or None
        self.pf = None                       # addresses blocked by a firewall rule (iptables / ip6tables / ufw: nginx-log-audit.sh --ban), or None (unreadable)

    @staticmethod
    def read_fail2ban():
        code, output = lancer_root(["fail2ban-client", "banned"], 10)
        if code == 0:
            try:                              # fail2ban >= 0.11: "[{'jail': ['1.2.3.4']}, ...]"
                return {ipaddress.ip_address(a) for jail in ast.literal_eval(output.strip() or "[]") for addresses in jail.values() for a in addresses}
            except (ValueError, SyntaxError, AttributeError, TypeError):
                pass
        code, output = lancer_root(["fail2ban-client", "status"], 10)             # fallback: "Jail list: a, b" then "Banned IP list: ..." per jail
        if code != 0:
            return None
        m = re.search(r"Jail list:\s*(.*)", output)
        ips = set()
        for jail in [j.strip() for j in (m.group(1).split(",") if m else []) if j.strip()]:
            mm = re.search(r"Banned IP list:\s*(.*)", lancer_root(["fail2ban-client", "status", jail], 10)[1])
            for a in (mm.group(1).split() if mm else []):
                try:
                    ips.add(ipaddress.ip_address(a))
                except ValueError:
                    pass
        return ips

    @classmethod
    def read_ipsets(cls):
        host_names, networks, exceptions, was_read = set(), [], [], False
        for name in cls.IPSETS:
            code, output = lancer_root(["ipset", "list", name], 20)
            if code != 0:
                continue
            was_read, member_list = True, False
            for text_line in output.splitlines():
                if text_line.startswith("Members:"):
                    member_list = True
                    continue
                field_list = text_line.split()
                if not member_list or not field_list:
                    continue
                try:
                    r = ipaddress.ip_network(field_list[0], strict=False)
                except ValueError:
                    continue
                if "nomatch" in field_list[1:]:
                    exceptions.append(r)
                elif r.num_addresses == 1:
                    host_names.add(r.network_address)
                else:
                    networks.append(r)
        return (host_names, networks, exceptions) if was_read else None

    @staticmethod
    def address_blocked_by_rule(text_line):
        """Single address blocked UNCONDITIONALLY by a rule "-A INPUT -s IP -j DROP|REJECT" (what nginx-log-audit.sh --ban sets); None for any other rule: network,
        rule limited to an interface (! -i lo), a port, a protocol, a state… Such a rule does not ban the address (e.g. anti-spoofing of 127.0.0.1)."""
        try:
            words = shlex.split(text_line)
        except ValueError:
            return None
        if words[:2] != ["-A", "INPUT"]:
            return None
        remaining, source, target, i = words[2:], None, None, 0
        while i < len(remaining):
            if remaining[i] == "-s" and i + 1 < len(remaining) and source is None:
                source, i = remaining[i + 1], i + 2
            elif remaining[i] == "-j" and i + 1 < len(remaining):
                target, i = remaining[i + 1], i + 2
            elif remaining[i:i + 2] == ["-m", "comment"] and remaining[i + 2:i + 3] == ["--comment"] and i + 3 < len(remaining):
                i += 4
            elif remaining[i] == "--reject-with" and i + 1 < len(remaining):
                i += 2
            else:
                return None
        if source is None or target not in ("DROP", "REJECT"):
            return None
        try:
            r = ipaddress.ip_network(source, strict=False)
        except ValueError:
            return None
        return r.network_address if r.num_addresses == 1 and not r.network_address.is_loopback else None

    @classmethod
    def read_firewall(cls):
        """Addresses banned by a firewall rule (iptables, ip6tables, "ufw deny from IP"): what nginx-log-audit.sh --ban sets. Conditional rules and the local
        loopback never count. None: nothing readable (root required)."""
        ips, was_read = set(), False
        for cmd in (["iptables", "-S", "INPUT"], ["ip6tables", "-S", "INPUT"]):
            code, output = lancer(cmd, 10)
            if code != 0:
                continue
            was_read = True
            ips |= {a for a in (cls.address_blocked_by_rule(l) for l in output.splitlines()) if a}
        code, output = lancer(["ufw", "status"], 10)
        if code == 0:
            was_read = True
            for text_line in output.splitlines():
                m = re.match(r"^Anywhere(?: \(v6\))?\s+(?:DENY|REJECT)(?: IN)?\s+(\S+)\s*(?:#.*)?$", text_line.strip())
                if m:
                    try:
                        r = ipaddress.ip_network(m.group(1), strict=False)
                    except ValueError:
                        continue
                    if r.num_addresses == 1 and not r.network_address.is_loopback:
                        ips.add(r.network_address)
        return ips if was_read else None

    def refresh(self):
        f2b, cs, pf = self.read_fail2ban(), self.read_ipsets(), self.read_firewall()
        with self.lock:
            self.f2b, self.cs, self.pf = f2b, cs, pf

    def start(self):
        """First read immediately (the first lines benefit), then re-read every 60 s in the background."""
        self.refresh()
        def loop():
            while True:
                time.sleep(self.DELAY)
                self.refresh()
        threading.Thread(target=loop, daemon=True).start()

    def summary(self):
        with self.lock:
            f2b, cs = self.f2b, self.cs
        sources = []
        if f2b is not None:
            sources.append(f"fail2ban {len(f2b)} address(es)")
        if cs is not None:
            sources.append(f"CrowdSec {len(cs[0]) + len(cs[1])} entry(ies)")
        if self.pf is not None:
            sources.append(f"firewall (iptables / ufw) {len(self.pf)} address(es)")
        return "Banned addresses: " + (", ".join(sources) if sources else "no readable source (fail2ban-client and ipset missing, or root required)")

    def source_of(self, ip):
        """"fail2ban", "firewall" (iptables / ufw), "CrowdSec" or None."""
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if a.is_loopback:
            return None                       # this server (warmup, health probes) is never "banned"
        with self.lock:
            f2b, cs, pf = self.f2b, self.cs, self.pf
        if f2b and a in f2b:
            return "fail2ban"
        if pf and a in pf:
            return "firewall"
        if cs:
            host_names, networks, exceptions = cs
            if (a in host_names or any(a in r for r in networks)) and not any(a in e for e in exceptions):
                return "CrowdSec"
        return None


def readable_bytes(n):
    """1536 -> "1.5 KB"."""
    n = float(n)
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unit == "Go":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024


class Resources:
    """What THIS program consumes (and its lookups: getent, geoiplookup, curl): processor, memory, input/output. On Linux from /proc/self; without /proc, what
    is missing is omitted (never an error)."""
    @staticmethod
    def measure():
        t = os.times()
        m = {"t": time.time(), "cpu": t.user + t.system + t.children_user + t.children_system, "rss": None, "peak": None,
             "was_read": None, "written": None, "disk_read": None, "disk_written": None, "threads": threading.active_count()}
        try:
            with open("/proc/self/status", encoding="ascii", errors="replace") as f:
                for text_line in f:
                    if text_line.startswith(("VmRSS:", "VmHWM:")):
                        m["rss" if text_line.startswith("VmRSS") else "peak"] = int(text_line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass
        try:
            with open("/proc/self/io", encoding="ascii", errors="replace") as f:
                values = dict(text_line.split(":", 1) for text_line in f if ":" in text_line)
            m.update(was_read=int(values["rchar"]), written=int(values["wchar"]), disk_read=int(values["read_bytes"]), disk_written=int(values["write_bytes"]))
        except (OSError, ValueError, KeyError):
            pass
        return m

    @staticmethod
    def cpu_pour_cent(before, after):
        duration_s = after["t"] - before["t"]
        return 100.0 * (after["cpu"] - before["cpu"]) / duration_s if duration_s > 0 else 0.0

    @classmethod
    def lines(cls, before, after):
        """"Program: …" lines between two measures: % of processor, memory, input/output (per second)."""
        duration_s = max(after["t"] - before["t"], 0.001)
        cpu = cls.cpu_pour_cent(before, after)
        chunks = [f"CPU {cpu:.1f} %"]
        if after["rss"] is not None:
            chunks.append(f"memory {readable_bytes(after['rss'])} (peak {readable_bytes(after['peak'] or after['rss'])})")
        chunks.append(f"{after['threads']} threads")
        res = ["  Program: " + " · ".join(chunks)]
        if after["was_read"] is not None and before["was_read"] is not None:
            res.append(f"  I/O: read {readable_bytes(after['was_read'] - before['was_read'])} ({readable_bytes((after['was_read'] - before['was_read']) / duration_s)}/s, of which disk "
                       f"{readable_bytes(after['disk_read'] - before['disk_read'])}) · written {readable_bytes(after['written'] - before['written'])} "
                       f"(of which disk {readable_bytes(after['disk_written'] - before['disk_written'])})")
        return res

    @staticmethod
    def alerts(before, after):
        """Alert texts: processor > 50 % over the period, memory > 1 GB."""
        res = []
        cpu = Resources.cpu_pour_cent(before, after)
        if after["t"] - before["t"] >= 5 and cpu > 50:
            res.append(f"program CPU at {cpu:.0f} %")
        if (after["rss"] or 0) > 1024 ** 3:
            res.append(f"program memory at {readable_bytes(after['rss'])}")
        return res


# ------------------------------------------------------------------------------------------------------------------
# 1.82: LATENCY - what slows the requests down over hours (disk, processor, memory, or the code itself). A sampler thread reads the kernel counters every
# LATENCY_SAMPLE_S seconds (apps/_sysperf.py: a few small /proc files, no external command); every Odoo request (SQL time + Python time of its journal
# line) is filed in the bin of its hour, classified "disk busy" or "disk calm" according to the last sample. Nothing is kept per request: a few numbers per
# hour, whatever the length of the session.
# ------------------------------------------------------------------------------------------------------------------
LATENCY_SAMPLE_S = float(os.environ.get("APP_LOG_LIVE_LATENCY_SAMPLE", "30"))
IO_BUSY_PSI = 10.0           # % of the time with at least one task waiting for the disk (PSI io "some") from which the disk is "busy"
IO_BUSY_UTIL = 60.0          # ... or % of utilization of the busiest disk
SLOW_LATENCY_S = 1.0         # slow request for the latency report (independent of --slow, which only colors the lines)
HIST_BASE, HIST_RATIO, HIST_N = 0.005, 1.25, 48           # duration histogram: 5 ms x 1.25^k (up to ~ 230 s)


def in_container():
    """True in an LXC / OpenVZ / Docker container (disk counters of /proc/diskstats then partial or those of the host)."""
    try:
        with open("/run/systemd/container", encoding="ascii") as f:
            return bool(f.read().strip())
    except OSError:
        pass
    try:
        with open("/proc/1/environ", "rb") as f:
            return b"container=" in f.read()
    except OSError:
        return False


class LatencyMonitor:
    """Session-long latency statistics (see the block comment above). Thread-safe; start() launches the sampler (daemon thread)."""

    def __init__(self, sysperf=None, sample_s=LATENCY_SAMPLE_S):
        self.sysperf, self.sample_s = sysperf, sample_s
        self.lock = threading.Lock()
        self.bins = {}                   # "YYYY-MM-DD HH" -> dict of counters (see _bin)
        self.samples = 0
        self.first_sample = None
        self.current = None              # last rates() result
        self.container = in_container()
        self.disks_seen = {}             # device -> rotational (True / False / None)
        self.started = False
        self.prev = None

    @staticmethod
    def _bin():
        return {"n": 0, "sum": 0.0, "sql": 0.0, "py": 0.0, "hist": [0] * HIST_N, "slow": 0, "busy_n": 0, "busy_sum": 0.0, "calm_n": 0, "calm_sum": 0.0,
                "slow_busy": 0, "s": 0, "io_some": 0.0, "io_some_max": 0.0, "io_full": 0.0, "cpu": 0.0, "iowait": 0.0, "steal": 0.0, "cpu_some": 0.0,
                "mem_some": 0.0, "util_max": 0.0, "util_dev": "", "util_sum": 0.0, "await_r": 0.0, "await_r_n": 0, "await_w": 0.0, "await_w_n": 0}

    def start(self):
        if self.started or self.sysperf is None:
            return
        self.started = True
        try:
            self.prev = self.sysperf.snapshot(net=False, arc=False)
        except Exception:       # noqa: BLE001 - a measurement never stops the stream
            self.prev = None
        threading.Thread(target=self._loop, daemon=True, name="latency-sampler").start()

    def _loop(self):
        while True:
            time.sleep(self.sample_s)
            try:
                self.sample()
            except Exception:   # noqa: BLE001
                continue

    def sample(self):
        """One sample: rates since the previous one, filed in the bin of the current hour."""
        cur = self.sysperf.snapshot(net=False, arc=False)
        if self.prev is None:
            self.prev = cur
            return None
        r = self.sysperf.rates(self.prev, cur)
        self.prev = cur
        key = time.strftime("%Y-%m-%d %H", time.localtime(r["wall"]))
        with self.lock:
            b = self.bins.setdefault(key, self._bin())
            b["s"] += 1
            io = r["psi"].get("io", {})
            b["io_some"] += io.get("some", 0.0)
            b["io_full"] += io.get("full", 0.0)
            b["io_some_max"] = max(b["io_some_max"], io.get("some", 0.0))
            b["cpu_some"] += r["psi"].get("cpu", {}).get("some", 0.0)
            b["mem_some"] += r["psi"].get("memory", {}).get("some", 0.0)
            if r["cpu"]:
                b["cpu"] += r["cpu"]["busy"]
                b["iowait"] += r["cpu"]["iowait"]
                b["steal"] += r["cpu"]["steal"]
            dev, util = self.sysperf.busiest_disk(r)
            b["util_sum"] += util
            if util >= b["util_max"]:
                b["util_max"], b["util_dev"] = util, dev or ""
            for d, v in r["disks"].items():
                if d not in self.disks_seen:
                    self.disks_seen[d] = md_rotational(d) if d.startswith("md") else self.sysperf.rotational(d)
                if v["r_await"] is not None and v["r_s"] >= 1:
                    b["await_r"] += v["r_await"]
                    b["await_r_n"] += 1
                if v["w_await"] is not None and v["w_s"] >= 1:
                    b["await_w"] += v["w_await"]
                    b["await_w_n"] += 1
            self.samples += 1
            self.first_sample = self.first_sample or r["wall"] - r["dt"]
            self.current = r
        return r

    def busy(self, r=None):
        """True / False: the disk is busy / calm according to the last sample; None before the first sample."""
        r = r or self.current
        if r is None:
            return None
        return r["psi"].get("io", {}).get("some", 0.0) >= IO_BUSY_PSI or self.sysperf.busiest_disk(r)[1] >= IO_BUSY_UTIL

    def request(self, instant, detail):
        """An Odoo request: detail = (size, SQL queries, SQL time, Python time) of its journal line (None: not an Odoo request with durations)."""
        if detail is None:
            return
        sql, py = detail[2], detail[3]
        total = sql + py
        instant = instant or time.time()
        key = time.strftime("%Y-%m-%d %H", time.localtime(instant))
        state = self.busy() if self.first_sample and instant >= self.first_sample - 60 else None      # startup history: before the first sample, unknown
        k = 0 if total <= HIST_BASE else min(HIST_N - 1, int(math.log(total / HIST_BASE, HIST_RATIO)) + 1)
        with self.lock:
            b = self.bins.setdefault(key, self._bin())
            b["n"] += 1
            b["sum"] += total
            b["sql"] += sql
            b["py"] += py
            b["hist"][k] += 1
            slow = total >= SLOW_LATENCY_S
            b["slow"] += slow
            if state is True:
                b["busy_n"] += 1
                b["busy_sum"] += total
                b["slow_busy"] += slow
            elif state is False:
                b["calm_n"] += 1
                b["calm_sum"] += total

    @staticmethod
    def percentile(hist, p):
        n = sum(hist)
        if not n:
            return None
        target, seen = p / 100.0 * n, 0
        for k, c in enumerate(hist):
            seen += c
            if seen >= target:
                return HIST_BASE * HIST_RATIO ** k
        return HIST_BASE * HIST_RATIO ** (HIST_N - 1)

    def totals(self):
        with self.lock:
            bins = copy.deepcopy(self.bins)
        t = self._bin()
        for b in bins.values():
            for k, v in b.items():
                if k == "hist":
                    t["hist"] = [x + y for x, y in zip(t["hist"], v)]
                elif k in ("io_some_max", "util_max"):
                    if v >= t[k]:
                        t[k] = v
                        if k == "util_max":
                            t["util_dev"] = b["util_dev"]
                elif k != "util_dev":
                    t[k] += v
        return t, bins

    def verdict(self, t):
        """(symbol, text): the conclusion about the disks over the session."""
        if t["s"] < 4 or t["n"] < 20:
            return "…", f"not enough data yet: one sample every {self.sample_s:g} s and at least 20 Odoo requests are needed (let it run a few hours)"
        io_avg = t["io_some"] / t["s"]
        p95 = self.percentile(t["hist"], 95) or 0
        slow_share = t["slow_busy"] / t["slow"] if t["slow"] else 0.0
        busy_mean = t["busy_sum"] / t["busy_n"] if t["busy_n"] >= 20 else None
        calm_mean = t["calm_sum"] / t["calm_n"] if t["calm_n"] >= 20 else None
        cpu_avg = t["cpu_some"] / t["s"]
        mem_avg = t["mem_some"] / t["s"]
        if mem_avg >= 10:
            return "✖", f"MEMORY is the limit (memory pressure {mem_avg:.0f} % of the time): add RAM or reduce Odoo workers / the ZFS ARC before thinking of SSD"
        if io_avg >= IO_BUSY_PSI or (t["slow"] >= 10 and slow_share >= 0.5) or (busy_mean and calm_mean and busy_mean >= 2 * calm_mean and t["busy_n"] >= 50):
            return "✖", (f"the DISKS slow the requests down (I/O pressure {io_avg:.0f} % on average — {slow_share * 100:.0f} % of the slow requests while the disk was busy"
                         + (f" — {busy_mean:.2f} s per request when the disk is busy against {calm_mean:.2f} s otherwise" if busy_mean and calm_mean else "")
                         + "): SSD justified — or, cheaper, an SSD as ZFS « special » device / L2ARC and more RAM for the ARC (host-perf-audit.py on the Proxmox host)")
        if cpu_avg >= 20:
            return "⚠", f"the PROCESSOR is the limit more than the disks (CPU pressure {cpu_avg:.0f} %): more cores or fewer simultaneous workers; SSD would not help much"
        if io_avg < 5 and slow_share < 0.3 and p95 < SLOW_LATENCY_S:
            return "✔", (f"the disks are NOT what slows the requests (I/O pressure {io_avg:.1f} % on average, 95 % of the requests under {p95:.2f} s): SATA disks are enough for "
                         "this load; the slowness of the first page loads after a restart is the cold cache (assets, views), not the disk")
        if slow_share < 0.3 and p95 < SLOW_LATENCY_S and busy_mean and calm_mean and busy_mean < 1.3 * calm_mean:
            return "✔", (f"the disk is busy at times (I/O pressure {io_avg:.1f} % on average) but the requests are NOT slower then ({busy_mean:.2f} s against "
                         f"{calm_mean:.2f} s): SATA disks are enough for this load")
        return "⚠", (f"occasional disk waits (I/O pressure {io_avg:.1f} % on average, peak {t['io_some_max']:.0f} % — {slow_share * 100:.0f} % of the slow requests while the disk "
                     "was busy): visible during startups, backups or nightly tasks, not enough by themselves to justify SSD — compare the hours below")

    def lines(self, level=9):
        """Lines of the LATENCY block for the dashboard and the summary: verdict (level 4), detail (6), per-hour table (8)."""
        t, bins = self.totals()
        if not t["n"] and not t["s"]:
            return [] if level < 9 else ["  Latency: no Odoo request with durations and no sample yet."]
        symbol, text = self.verdict(t)
        style = {"✔": "1;32", "⚠": "1;33", "✖": "1;31"}.get(symbol, "0")
        res = [(4, "  " + color_code(style, f"{symbol} Latency (since start)") + f" — {text}")]
        if t["n"]:
            med, p95, p99 = (self.percentile(t["hist"], p) for p in (50, 95, 99))
            res.append((6, numbers(f"    Odoo requests: {t['n']} · median {med:.2f} s · 95 % under {p95:.2f} s · 99 % under {p99:.2f} s · slow (≥ {SLOW_LATENCY_S:g} s): {t['slow']} "
                                   f"({100 * t['slow'] / t['n']:.1f} %) · time spent in PostgreSQL {100 * t['sql'] / max(t['sum'], 1e-9):.0f} %, in Python {100 * t['py'] / max(t['sum'], 1e-9):.0f} %")))
        if t["s"]:
            s = t["s"]
            disk = f"busiest disk {t['util_dev'] or '?'} {t['util_max']:.0f} % at most, {t['util_sum'] / s:.0f} % on average"
            aw = []
            if t["await_r_n"]:
                aw.append(f"read {t['await_r'] / t['await_r_n']:.1f} ms")
            if t["await_w_n"]:
                aw.append(f"write {t['await_w'] / t['await_w_n']:.1f} ms")
            kinds = [f"{d} " + ("ZFS volume" if d.startswith("zd") else ("RAID " if d.startswith("md") else "") + ("HDD" if v else "SSD" if v is False else "?")) for d, v in sorted(self.disks_seen.items())]      # 1.83: name + kind ("?, HDD" said nothing; zdN = ZFS volume)
            res.append((6, numbers(f"    Disks ({s} samples, every {self.sample_s:g} s): {disk}" + (f" · wait per operation: {', '.join(aw)}" if aw else "")
                                   + (f" · types: {', '.join(kinds)}" if kinds else ""))))
            source = (self.prev or {}).get("psi_source", "kernel")
            res.append((6, numbers(f"    Waiting time (PSI, {source}): disk {t['io_some'] / s:.1f} % (peak {t['io_some_max']:.0f} %, all tasks {t['io_full'] / s:.1f} %) · "
                                   f"processor {t['cpu_some'] / s:.1f} % · memory {t['mem_some'] / s:.1f} % · CPU busy {t['cpu'] / s:.0f} %, iowait {t['iowait'] / s:.1f} %, steal {t['steal'] / s:.1f} %")))
            no_sample = max(0, t["n"] - t["busy_n"] - t["calm_n"])              # 1.94: requests before the first disk sample, counted so that the figures add up
            if t["busy_n"] or t["calm_n"]:
                res.append((6, numbers(f"    Requests while the disk was busy: {t['busy_n']}" + (f" (mean {t['busy_sum'] / t['busy_n']:.2f} s)" if t["busy_n"] else "")
                                       + f" · calm: {t['calm_n']}" + (f" (mean {t['calm_sum'] / t['calm_n']:.2f} s)" if t["calm_n"] else "")
                                       + (f" · slow requests during a busy disk: {t['slow_busy']}/{t['slow']}" if t["slow"] else "") + (f" · without sample: {no_sample}" if no_sample else ""))))
            if self.container:
                res.append((6, "    (container: the disk counters can be partial; the waiting times above are those of THIS container — the real disks are seen by host-perf-audit.py on the Proxmox host)"))
        if len(bins) > 1 or level >= 8:
            titles = [TR(t) for t in ("Per hour", "requests", "median", "95 %", "slow", "SQL %", "disk max", "I/O wait", "CPU")]      # translated BEFORE padding
            res.append((8, f"    {titles[0]:<14}  {titles[1]:>8}  {titles[2]:>7}  {titles[3]:>6}  {titles[4]:>8}  {titles[5]:>6}  {titles[6]:>10}  {titles[7]:>11}  {titles[8]:>5}"))
            for key in sorted(bins)[-24:]:
                b = bins[key]
                med, p95 = self.percentile(b["hist"], 50), self.percentile(b["hist"], 95)
                cells = ["-" if med is None else f"{med:.2f}", "-" if p95 is None else f"{p95:.2f}", f"{100 * b['sql'] / b['sum']:.0f}" if b["sum"] else "-",
                         f"{b['util_max']:.0f} %" if b["s"] else "-", f"{b['io_some'] / b['s']:.1f} %" if b["s"] else "-", f"{b['cpu'] / b['s']:.0f} %" if b["s"] else "-"]
                res.append((8, numbers(f"    {key}h  {b['n']:>8}  {cells[0]:>7}  {cells[1]:>6}  {b['slow']:>8}  {cells[2]:>6}  {cells[3]:>10}  {cells[4]:>11}  {cells[5]:>5}")))
        return [line for n, line in res if n <= level]


LATENCY = LatencyMonitor(load_module("_sysperf"))


LANGUAGE_RE = re.compile(r"^/(?:([a-z]{2})_[A-Z]{2}|(en|fr|es|de|it|pt|nl|ar|zh|ja|ru))(?:/|$)")
# ROBOTS (Odoo's journal does NOT have the User-Agent): an address is a robot if it requested /robots.txt or a sitemap, or if its name (DNS, organization) is that of a known
# robot. "Stealth" robots (hosts without a telling name, fake browsers) cannot be detected here: the percentage of real visitors is therefore a MAXIMUM.
ROBOTS_FILES_RE = re.compile(r"^/(?:robots\.txt|[\w.-]*sitemap[\w.-]*\.xml(?:\.gz)?)$", re.I)
ROBOT_NAME_RE = re.compile(r"bot|crawl|spider|scrap|linkedin|facebook|fbsv|meta-|semrush|ahrefs|petal|yandex|baidu|bytespider|amazonbot|applebot|gptbot|ccbot|openai|anthropic|"
                          r"mj12|dotbot|seznam|sogou|bingpreview|msnbot|duckduck|ia_archiver|archive\.org|sofya|screaming|censys|shodan|zgrab|expanse|netcraft", re.I)

# User-Agent (nginx access journal, combined_host format: ..."referrer" "User-Agent" host="..."): robots recognized by their signature, or script tools; empty UA = robot.
ACCESS_AGENT_RE = re.compile(r'^(\S+) \S+ \S+ \[[^\]]*\] "[^"]*" \d{3} \S+ "[^"]*" "([^"]*)"')
STATIC_RE = re.compile(r"\.(?:css|js|map|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot|mp4|webm)$|^/(?:web/assets|web/static|web/image|web/content)/", re.I)
SURVEY_TOKEN_RE = re.compile(r"^/survey/(?:(?:start|submit|fill|print|results|begin|prefill|retry|test|get_certification)/)?([0-9a-fA-F][0-9a-fA-F-]{7,})(?:/|$)")
# 1.130: User-Agents refused with 403 by nginx/conf.d/bot_blocker.conf (same list as that file). Such a 403 is a POLICY, not a fault: it is
# shown with the [BOT] label, counted apart ("bots refused") and it does not lower the health percentage.
BOT_BLOCKED_CONF = "/etc/nginx/conf.d/bot_blocker.conf"                    # 1.132: read at start, so the label follows the policy
BOT_BLOCKED_DEFAULT = (r"AhrefsBot|MJ12bot|SemrushBot|DotBot|DataForSeoBot|PetalBot|SERankingBacklinksBot|GeedoShopProductFinder|"
                       r"Bytespider|CCBot|GPTBot|Amazonbot|ClaudeBot|Claude-SearchBot|CensysInspect|shodan|masscan|zgrab|Palo Alto Networks|"
                       r"LeakIX|l9scan|jscrawler|poc-suite|AteveSearchSourceUrlDiscovery|CyberConvoyScout|ForestEngine|Infrawatch|"
                       r"Reflectionbot|visionheight|python-requests|python-httpx|python-urllib|Wget")


def bot_blocked_re(path=BOT_BLOCKED_CONF):
    """1.132: the User-Agent names that bot_blocker.conf refuses ("~*(A|B) 1;" and "~*^(A|B)/ 1;" lines); the built-in list when the file is absent."""
    names = []
    try:
        with open(path, encoding="utf-8", errors="replace") as conf:
            for line in conf:
                if line.lstrip().startswith("#"):
                    continue
                found = re.search(r"~\*\^?\((.*?)\)/?\s+1;", line)
                if found:
                    names += [name.replace("\\ ", " ") for name in found.group(1).split("|") if name]
    except OSError:
        names = []
    if not names:
        return re.compile(BOT_BLOCKED_DEFAULT, re.I)
    return re.compile("|".join(re.escape(name) for name in names), re.I)


BOT_BLOCKED_UA_RE = bot_blocked_re()
REQUEST_CODE_RE = re.compile(r'"(?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s[^"]*" (\d{3})\s')


def is_bot_403(L):
    """1.130: True for an nginx request answered 403 to a User-Agent of the bot_blocker.conf list (a policy, not an error)."""
    if L.database != "nginx" or not L.text:
        return False
    m = REQUEST_CODE_RE.search(L.text)
    return bool(m and m.group(1) == "403" and BOT_BLOCKED_UA_RE.search(L.text))      # robots and scanners refused by policy


ROBOT_UA_RE = re.compile(r"bot\b|bot/|crawl|spider|slurp|scrap|facebookexternalhit|meta-external|python-|python/|curl/|wget/|go-http-client|httpx|java/|libwww|okhttp|headless|phantom|"
                         r"http[-_ ]?client|axios|node-fetch|monitor|uptime|preview|scan|censys|zgrab|masscan|semrush|ahrefs|mj12|dotbot|petal|bytespider|gptbot|claudebot|ccbot|amazonbot|"
                         r"applebot|yandex|baidu|duckduck|sogou|seznam|ia_archiver|archive\.org|linkedin|twitter|whatsapp|telegram|discord|pinterest|embedly|google-|googlebot|adsbot|"
                         r"mediapartners|lighthouse|pagespeed|gtmetrix|pingdom|statuscake|zabbix|nagios|compatible; (?!msie)|^-?$", re.I)
AGENTS_MAX = 300_000                                 # addresses kept in memory (known User-Agent)

NON_PAGE_RE = re.compile(r"^/(?:web/(?!login)|websocket|longpolling|bus/|mail/|jsonrpc|favicon|robots|apple-touch|static/|\.well-known)|\.(?:js|css|png|jpe?g|gif|svg|ico|woff2?|ttf|map|webp)$", re.I)
MAIL_ERROR_RE = re.compile(r"Mail Delivery Failed|SMTP|Failed to send|mail\.session|Connection refused", re.I)
# Odoo transaction retries (odoo/service/model.py, retrying function): "SERIALIZATION_FAILURE, 4 tries left, try again in 0.13 sec..." = retried conflict;
# "SERIALIZATION_FAILURE, maximum number of tries reached!" = final failure (the request fails). Same for DEADLOCK_DETECTED and LOCK_NOT_AVAILABLE.
RETRIED_CONFLICT_RE = re.compile(r"\b(SERIALIZATION_FAILURE|DEADLOCK_DETECTED|LOCK_NOT_AVAILABLE),\s*\d+ tries? left")
FINAL_CONFLICT_RE = re.compile(r"\b(SERIALIZATION_FAILURE|DEADLOCK_DETECTED|LOCK_NOT_AVAILABLE),\s*maximum number of tries reached")


def language_of(url):
    """"EN", "FR", "ES", "others" (other language prefix) or "no prefix" (default language of the site); None if it is not a page (file, websocket, /web/…)."""
    path = url.split("?", 1)[0]
    if NON_PAGE_RE.search(path):
        return None
    m = LANGUAGE_RE.match(path)
    if not m:
        return "without prefix"
    code = (m.group(1) or m.group(2)).lower()
    return code.upper() if code in ("en", "fr", "es") else "others"


DEFAULT_LANGUAGE = {}      # 1.106: default language of the site, read once per session from Odoo (root only)


def site_default_language():
    """1.106: code of the site's default language (e.g. "fr_CA") read from the Odoo database. Root only: None otherwise (the summary
    then says so). Read once per session (the database is not queried again at each refresh)."""
    if "value" not in DEFAULT_LANGUAGE:
        value = None
        if os.geteuid() == 0:
            module = load_module("_odoo_db")
            if module is not None and hasattr(module, "langue_defaut") and hasattr(module, "bases_odoo"):
                bases = module.bases_odoo() or []
                if bases:
                    value = module.langue_defaut(bases[0])
        DEFAULT_LANGUAGE["value"] = value
    return DEFAULT_LANGUAGE["value"]


def language_label(code):
    """1.106: label of a language bucket in the summary; the « without prefix » bucket names the site's default language."""
    if code != "without prefix":
        return code
    if os.geteuid() != 0:
        return TR("without prefix") + " (" + TR("default language not read (root required)") + ")"
    default = site_default_language()
    if default:
        return TR("without prefix") + f" ({default} = " + TR("default language of the site") + ")"
    return TR("without prefix") + " (" + TR("default language not read (database unreachable)") + ")"


class Stats:
    """What happened during the session, for the summary (Ctrl-C, --summary) and the dashboard (Ctrl-G, Ctrl-T): most active addresses, suspicious requests,
    5xx and 4xx errors, slow requests, banned addresses, pages per language, most requested URLs, Odoo errors. Counts only the DISPLAYED lines (after --only and --suspect)."""
    COUNTERS = ("par_ip", "by_name", "suspect_ips", "suspect_urls", "urls", "languages", "statuses", "odoo_errors", "pages", "pages_per_ip", "visits", "probes", "not_found", "conflict_codes", "failure_codes")
    VISIT_PAUSE = 1800                                 # seconds without a page view after which the return of an address is a NEW visit

    def __init__(self, slowest):
        self.start, self.slowest, self.period = time.time(), slowest, False      # period: difference between two displays (Ctrl-T)
        self.lines = self.requests = self.mails = 0
        self.conflicts = self.final_failures = 0          # conflicts retried by Odoo (harmless) / final failures after all the retries (the request failed)
        self.conflict_codes, self.failure_codes = Counter(), Counter()      # PostgreSQL code -> number
        self.recommended, self._reco_t, self.reco_state = {}, 0.0, ""            # {address: reason}: bans recommended by the last run of web-monitor.py (re-read every 60 s)
        self.mail_detail = None                      # function () -> lines: recipients of the failed e-mails to resend (set by follow(), reads PostgreSQL)
        self.par_ip, self.names = Counter(), {}
        self.by_name = Counter()                                                  # identified name (DNS column, person, team, server…) -> requests; bare addresses not counted
        self.suspect_ips, self.suspect_urls = Counter(), Counter()
        self.list_404 = False                                                      # --not-found: the summary lists ALL the 404 pages
        self.not_found = Counter()                                               # URL -> number of 404 responses
        self.ip_not_found = {}                                                   # address -> set of the DIFFERENT pages it requested in 404 (probe sweep)
        self.probes = Counter()                           # "suspicious" URLs requested by THIS server itself (health probes): counted apart, never to ban
        self.errors = {5: Counter(), 4: Counter()}
        self.urls, self.languages, self.statuses = Counter(), Counter(), Counter()
        self.odoo_errors = Counter()                     # (level, logger, message) -> number
        self.odoo_errors_time = {}                       # same key -> [first instant, last instant]
        self.http_errors = []                             # (instant, code, url, address) of each 4xx / 5xx response, in order of arrival
        self.slow_requests, self.banned = [], {}
        self.slow_info = []                              # same order as `slow_requests`: (SQL queries, SQL time, Python time, size, instant)
        self.pages, self.pages_per_ip, self.visits = Counter(), Counter(), Counter()   # pages viewed (path), pages viewed per address, visits (resumed after VISIT_PAUSE) per address
        self.last_seen_at, self.pays = {}, {}                                         # address -> instant of its last page view; address -> country (shared by the copies)
        self.is_banned = None                                                      # function(address) -> ban source or None (fail2ban, firewall, CrowdSec): checks the addresses never seen in the journal
        self.all_banned, self.protected_ones, self.people = set(), set(), set()      # shared (shallow copy): banned addresses, of the team or of a place, of known people
        self.watch_it, self.watched = [], []                                  # --watch: patterns (lowercase); (pattern, duration or None, code, URL, address) of the matching requests
        self.survey_titles = {}                                                   # {access token (lowercase): survey title} read from PostgreSQL, to name the surveys seen in --watch
        self.agents = {}                                                            # shared: address -> first User-Agent read in the nginx access journal
        self.robots_ips = set()                                                      # shared: addresses that requested robots.txt or a sitemap
        self.first = None                                                         # instant of the oldest line seen (window of the error detail)
        self.server = set()                                                        # shared: addresses of THIS server (local probes) - never to ban

    def already_banned(self, ip):
        """True if the address is already banned (seen banned in the journal, or blocked now by fail2ban, an iptables / ufw rule or CrowdSec)."""
        if ip in self.all_banned:
            return True
        try:
            source = self.is_banned(ip) if self.is_banned else None
        except Exception:
            source = None
        if source:
            self.all_banned.add(ip)
            return True
        return False

    def to_ban(self):
        """Addresses that made suspicious requests and that remain to be banned: neither already banned, nor of the whitelist or of a place,
        nor of a known person, nor of this server (127.0.0.1, ::1 or one of its addresses: never ban oneself)."""
        self.load_recommended()
        res = [(ip, n) for ip, n in self.suspect_ips.most_common()
               if ip != "?" and not self.already_banned(ip) and ip not in self.protected_ones and ip not in self.people
               and ip not in self.server and not local_address(ip)]
        views = {ip for ip, _ in res}
        for ip, pages in sorted(self.ip_not_found.items(), key=lambda kv: -len(kv[1])):          # sweep: 5 DIFFERENT pages in 404 (WordPress, debug, .env... ; a visitor's address almost never does that)
            if len(pages) >= THRESHOLD_404 and ip not in views and ip != "?" and not self.already_banned(ip) and ip not in self.protected_ones and ip not in self.people \
                    and ip not in self.server and not local_address(ip):
                res.append((ip, len(pages)))
                views.add(ip)
        for ip in self.recommended:                      # recommended by web-monitor.py (probes seen only by nginx: never in Odoo's journal): n = 0
            if ip not in views and ip != "?" and not self.already_banned(ip) and ip not in self.protected_ones and ip not in self.people \
                    and ip not in self.server and not local_address(ip):
                res.append((ip, 0))
        return res

    def load_recommended(self):
        """Addresses recommended for banning by the LAST run of web-monitor.py (recommended-bans.json, less than 48 h); unreadable or absent: none."""
        if time.time() - self._reco_t < 60:
            return
        self._reco_t = time.time()
        path = os.path.join(os.environ.get("WEB_MONITOR_STATE_DIR", "/var/lib/web-monitor"), "recommended-bans.json")
        self.reco_state = ""
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            age_h = (time.time() - float(d.get("time", 0))) / 3600
            if age_h > 48:
                self.reco_state = f"the last web-monitor.py run ({path}) is {age_h:.0f} h old: too old (48 h at most)"
                raise ValueError("too old")
            self.recommended = {x["ip"]: str(x.get("raison", "")) for x in d.get("ips", []) if isinstance(x, dict) and isinstance(x.get("ip"), str)}
        except PermissionError:
            self.recommended = {}
            self.reco_state = f"{path} unreadable: permission denied (run app-log-live.py with sudo, like web-monitor.py)"
        except FileNotFoundError:
            self.recommended = {}
            self.reco_state = f"{path} missing: web-monitor.py has not run here yet, or it writes elsewhere (WEB_MONITOR_STATE_DIR)"
        except (OSError, ValueError, TypeError, AttributeError):
            self.recommended = {}
            self.reco_state = self.reco_state or f"{path} unreadable"

    def reco_diagnostic(self):
        """Why the addresses recommended by web-monitor.py are not proposed for banning (empty text: nothing to explain)."""
        self.load_recommended()
        if self.reco_state:
            return self.reco_state
        discarded = {}                                                 # reason -> addresses (grouped: "ip, ip, ip already banned", not one phrase per address)
        for ip in self.recommended:
            if self.already_banned(ip):
                discarded.setdefault("already banned: ", []).append(ip)
            elif ip in self.protected_ones:
                discarded.setdefault("protected (team or place): ", []).append(ip)
            elif ip in self.people:
                discarded.setdefault("known person: ", []).append(ip)
            elif ip in self.server or local_address(ip):
                discarded.setdefault("this server: ", []).append(ip)
        if discarded:
            return f"web-monitor.py recommends {len(self.recommended)}, skipped — " + " ; ".join(reason + ", ".join(ips) for reason, ips in discarded.items())
        return ""

    def ban_reason(self, ip, n):
        """Why this address is to be banned: suspicious requests seen here, or recommendation of web-monitor.py (with its reason)."""
        if n and ip not in self.suspect_ips and len(self.ip_not_found.get(ip, ())) >= THRESHOLD_404:
            return f"{n} different pages not found (404): probe sweep"
        if n:
            return f"{n} suspicious requests"
        return "recommended by web-monitor.py" + (f" ({self.recommended[ip]})" if self.recommended.get(ip) else "")

    def count_conflict(self, L):
        """Odoo transaction retries, counted for ANY line read (even hidden by --min or --only): retried conflicts and final failures, apart from the errors."""
        m = RETRIED_CONFLICT_RE.search(L.text or "")
        if m:
            self.conflicts += 1
            self.conflict_codes[m.group(1)] += 1
            return
        m = FINAL_CONFLICT_RE.search(L.text or "")
        if m:
            self.final_failures += 1
            self.failure_codes[m.group(1)] += 1

    def ajouter(self, L, renderings, ban_source, benign=False):
        self.lines += 1
        if L.level in ("WARNING", "ERROR", "CRITICAL") and not benign:          # "bad query" of a retried conflict: counted in the conflicts, NOT in the errors
            message = re.sub(r"(?<![A-Za-z\d])\d+", "N", (L.text or "").strip())[:200]
            self.odoo_errors[(L.level, L.logger, message)] += 1
            t = L.instant or time.time()
            seen = self.odoo_errors_time.setdefault((L.level, L.logger, message), [t, t])
            seen[1] = max(seen[1], t)
            if L.level in ("ERROR", "CRITICAL") and ("mail" in (L.logger or "") or MAIL_ERROR_RE.search(L.text or "")):
                self.mails += 1
        r = REQUEST_RE.search(L.text)
        if not r:
            return
        ips = find_ips(L.text)
        ip = ips[0][2] if ips else "?"
        self.requests += 1
        if L.instant and (self.first is None or L.instant < self.first):
            self.first = L.instant
        self.par_ip[ip] += 1
        self.names.setdefault(ip, ANSI_RE.sub("", renderings[ip][0]) if ip in renderings else ip)
        if ip != "?" and self.names[ip] != ip:                                     # identified: a name, not the bare address (kept in step with --dns-max)
            self.by_name[self.names[ip]] += 1
        url, code = r.group(1), int(r.group(2))
        if ROBOTS_FILES_RE.match(url.split("?", 1)[0]):
            self.robots_ips.add(ip)
        self.urls[url.split("?", 1)[0]] += 1
        self.statuses[code // 100] += 1
        lang = language_of(url) if code < 400 else None
        if lang:
            self.languages[lang] += 1
            if not suspect_url(url):                                   # site VISIT: a page (not a file, nor an error, nor a security probe)
                instant = L.instant or time.time()
                self.pages[url.split("?", 1)[0]] += 1
                self.pages_per_ip[ip] += 1
                if instant - self.last_seen_at.get(ip, float("-inf")) > self.VISIT_PAUSE:
                    self.visits[ip] += 1
                self.last_seen_at[ip] = max(instant, self.last_seen_at.get(ip, instant))
        if suspect_url(url) and (ip in self.server or local_address(ip)):
            self.probes[url] += 1
        elif suspect_url(url):
            self.suspect_ips[ip] += 1
            self.suspect_urls[url] += 1
        if code >= 400:
            self.errors[5 if code >= 500 else 4][url] += 1
            self.http_errors.append((L.instant or time.time(), code, url, ip))
            del self.http_errors[:-2000]
        if code == 404:
            self.not_found[url] += 1
            self.ip_not_found.setdefault(ip, set()).add(url.split("?", 1)[0])
        total = request_duration(L.text)
        if not self.period:
            LATENCY.request(L.instant, request_detail(L.text))
        if self.slowest and total is not None and total >= self.slowest:
            self.slow_requests.append((total, url, ip))
            d = request_detail(L.text) or (None, 0, 0.0, total)
            self.slow_info.append((d[1], d[2], d[3], d[0], L.instant or time.time()))
        for pattern in self.watch_it:
            if pattern in url.lower():
                self.watched.append((pattern, total, code, url, ip))
        if ban_source:
            self.banned[ip] = ban_source
            self.all_banned.add(ip)
        if ip in renderings and renderings[ip][3] is not None:
            self.protected_ones.add(ip)

    # --- snapshots and differences (Ctrl-T) --------------------------------------------------------------------------------------------
    def snapshot(self):
        """Frozen copy of the counters, at the present instant."""
        c = copy.copy(self)
        for name in self.COUNTERS:
            setattr(c, name, Counter(getattr(self, name)))
        c.errors = {k: Counter(v) for k, v in self.errors.items()}
        c.slow_requests, c.slow_info, c.banned, c.end = list(self.slow_requests), list(self.slow_info), dict(self.banned), time.time()
        c.watched, c.watch_it = list(self.watched), list(self.watch_it)
        c.http_errors, c.odoo_errors_time = list(self.http_errors), {k: list(v) for k, v in self.odoo_errors_time.items()}
        return c

    def since(self, old):
        """What happened since the snapshot `old` (same program, other counters: only the differences)."""
        d = self.snapshot()
        for name in self.COUNTERS:
            setattr(d, name, getattr(self, name) - getattr(old, name))
        d.errors = {k: self.errors[k] - old.errors[k] for k in self.errors}
        d.lines, d.requests = self.lines - old.lines, self.requests - old.requests
        d.mails, d.conflicts = self.mails - old.mails, self.conflicts - old.conflicts
        d.final_failures = self.final_failures - old.final_failures
        d.slow_requests, d.slow_info = self.slow_requests[len(old.slow_requests):], self.slow_info[len(old.slow_info):]
        d.watched = self.watched[len(old.watched):]
        d.http_errors = [e for e in self.http_errors if e[0] > old.end]
        d.banned = {ip: src for ip, src in self.banned.items() if ip not in old.banned}
        d.start, d.period = old.end, True
        return d

    def http_error_detail(self, class_, n=5):
        """The last `n` error responses of the class (4 or 5): time, code, URL, address (name, and "known person" if it is an identified user)."""
        recent = [e for e in self.http_errors if e[1] // 100 == class_][-n:]
        res = []
        for instant, code, url, ip in reversed(recent):
            known = " — known user" if (ip in self.protected_ones or ip in self.people) and self.names.get(ip, ip) != ip else ""
            res.append(f"{time.strftime('%H:%M:%S', time.localtime(instant))}  {code}  {short_url(url, 70)}  ← {self.who(ip)}{known}")
        return res

    def odoo_error_times(self, key_value):
        """"(first at HH:MM:SS, last at HH:MM:SS)" of an Odoo error; empty if the time is unknown."""
        seen = self.odoo_errors_time.get(key_value)
        if not seen:
            return ""
        h = [time.strftime("%H:%M:%S", time.localtime(t)) for t in seen]
        return f" (at {h[0]})" if h[0] == h[1] else f" (first at {h[0]}, last at {h[1]})"

    def who(self, ip):
        name = self.names.get(ip, ip)
        return name if name == ip else f"{name} [{ip}]"

    @staticmethod
    def top(counter, n=5, width=60):
        return " ; ".join(f"{short_url(u, width)} " + color_code("1;36", f"×{c}") for u, c in counter.most_common(n))

    def analyze_slow(self, n=4):
        """Lines that EXPLAIN the slow requests: where the time goes (SQL / Python), the most affected pages with their probable cause, the addresses
        concerned, and whether they arrive in clusters (saturated server). Empty if there are none."""
        if not self.slow_requests or len(self.slow_info) != len(self.slow_requests):
            return []
        lines, grouped, par_ip, minutes = [], {}, Counter(), Counter()
        t_sql = t_py = 0.0
        for (total, url, ip), (sql_n, ts, tp, size, instant) in zip(self.slow_requests, self.slow_info):
            t_sql, t_py = t_sql + ts, t_py + tp
            g = grouped.setdefault(url_template(url), {"n": 0, "total": 0.0, "max": 0.0, "sql": 0.0, "py": 0.0, "req": 0, "size": None, "example": url})
            g["n"] += 1
            g["total"] += total
            g["sql"], g["py"], g["req"] = g["sql"] + ts, g["py"] + tp, max(g["req"], sql_n)
            if size is not None:
                g["size"] = max(g["size"] or 0, size)
            if total >= g["max"]:
                g["max"], g["example"] = total, url
            par_ip[ip] += 1
            minutes[int(instant // 60)] += 1
        all_items = t_sql + t_py
        if all_items > 0:
            lines.append(f"Where the time goes: SQL {100 * t_sql / all_items:.0f} % · Python {100 * t_py / all_items:.0f} % (total {all_items:.0f} s over {len(self.slow_requests)} requests)")
        for url, g in sorted(grouped.items(), key=lambda kv: -kv[1]["total"])[:n]:
            lines.append(f"{short_url(url, 48)} ×{g['n']} — {g['total']:.0f} s in total, the worst {g['max']:.1f} s : "
                          + request_cause(g["req"], g["sql"], g["py"], g["size"], g["example"]))
        if par_ip and len(self.slow_requests) > 3:                  # up to 3 requests are listed one by one WITH their address: no need to repeat them
            lines.append("Addresses: " + " ; ".join(f"{self.who(ip)} ×{c}" for ip, c in par_ip.most_common(3)))
        cold = sum(1 for _t, u, _ip in self.slow_requests if COLD_RE.search(u))
        if cold >= 2 and 2 * cold >= len(self.slow_requests):
            lines.append(TR("{cold} of the {total} slow requests are assets or views (cold Odoo cache): Odoo has probably just restarted or been updated; they should no longer be slow on the second pass").format(cold=cold, total=len(self.slow_requests)))
        if all_items > 0 and t_py >= 0.8 * all_items:
            state = read_state()
            if state:
                lines.append(f"Python alone is to blame (not the database): right now {system_state(state)} — {python_conclusion(state)}")
        cluster = max(minutes.values())
        if cluster >= 3:
            lines.append(f"{cluster} slow requests in the same minute: overloaded server or database lock (see “Program” and app-health-check.py)")
        return lines

    # --- health --------------------------------------------------------------------------------------------------------------------------
    def health(self, program_alerts=()):
        """(level, lines): 0 all is well, 1 to look at, 2 problem. One indicator per line (✔ ⚠ ✖); under a failing indicator, the detail to understand (URLs, messages,
        slowest requests). Only what was DISPLAYED (after --only / --suspect)."""
        lines, worst = [], 0
        styled = {0: ("✔", "1;32"), 1: ("⚠", ORANGE), 2: ("✖", "1;31")}

        def indicator(level, caption, detail=(), threshold=(1, 5), n=0):
            nonlocal worst
            state = 0 if n < threshold[0] else (1 if n < threshold[1] else 2)
            state = max(state, level)
            worst = max(worst, state)
            symbol, style = styled[state]
            lines.append("  " + color_code(style, f"{symbol} {caption}"))
            if state:
                lines.extend("        " + d for d in detail)
        n5 = sum(self.errors[5].values())
        indicator(0, "HTTP 5xx errors: " + (f"{n5}" if n5 else none_fem()), ["URL: " + self.top(self.errors[5], 5)] + self.http_error_detail(5) if n5 else (), (1, 5), n5)
        severe = Counter({k: v for k, v in self.odoo_errors.items() if k[0] in ("ERROR", "CRITICAL")})
        ng = sum(severe.values())
        detail = [f"{k[0]} {k[1]} ×{v} : {k[2]}" + self.odoo_error_times(k) for k, v in severe.most_common(3)]
        indicator(0, "Odoo errors (ERROR / CRITICAL): " + (f"{ng}" if ng else none_fem()), detail, (1, 5), ng)
        # Concurrent update conflicts: Odoo starts over by itself (up to 5 tries); only the final failure is a real problem
        final_detail = [f"{code} ×{n} : Odoo gave up after 5 tries, the user's request failed (see the traceback that follows in the log)" for code, n in self.failure_codes.most_common(3)]
        indicator(0, "Final failures of concurrent updates: " + (f"{self.final_failures}" if self.final_failures else "none"), final_detail, (1, 3), self.final_failures)
        retry_detail = [f"{code} ×{n}" for code, n in self.conflict_codes.most_common(3)]
        if self.conflicts >= 50:
            retry_detail.append("many retries: often the same user on several devices (phone and computer) or a very busy chat channel")
        indicator(0, "Retried update conflicts (harmless): " + (f"{self.conflicts}" if self.conflicts else "none"), retry_detail, (50, 500), self.conflicts)
        to_resend = []
        if self.mails and self.mail_detail is not None:
            try:
                to_resend = list(self.mail_detail())
            except Exception:                                       # the dashboard must never crash because of an unreadable database
                to_resend = []
        indicator(0, "Failed e-mails: " + (f"{self.mails}" if self.mails else "none"),
                   to_resend + ["odoo-mail-retry.py lists the unsent e-mails and offers to resend them; app-log-check.py explains the causes (452, 503, 550)"], (1, 3), self.mails)
        if self.slowest:
            info_lines = self.slow_info if len(self.slow_info) == len(self.slow_requests) else [(0, 0.0, 0.0, None, 0.0)] * len(self.slow_requests)
            more = sorted(zip(self.slow_requests, info_lines), key=lambda p: p[0], reverse=True)[:3]
            indicator(0, f"Slow requests (≥ {self.slowest:g} s) : " + (f"{len(self.slow_requests)}" if self.slow_requests else none_fem()),
                       [f"{t:.1f} s {short_url(u)} ({self.who(ip)})" + (f" — SQL {ts:.1f} s · Python {tp:.1f} s · {n} SQL queries" if ts or tp else "") + (f" · {clock_of(_instant)}" if _instant else "")
                        for (t, u, ip), (n, ts, tp, _size, _instant) in more]
                      + ([TR("… and {n} other slow requests").format(n=len(self.slow_requests) - len(more))] if len(self.slow_requests) > len(more) else [])
                      + self.analyze_slow(), (1, 5), len(self.slow_requests))
        if self.watch_it:
            batch = self.watched
            errors = sum(1 for _, _, c, _, _ in batch if c >= 400)
            slow_requests = [(d, u) for _, d, _, u, _ in batch if d is not None and self.slowest and d >= self.slowest]
            indicator(0, f"Watch ({', '.join(self.watch_it)}) : {len(batch)} requests, {errors} errors, {len(slow_requests)} slow",
                       [f"{d:.1f} s {short_url(u)}" for d, u in sorted(slow_requests, reverse=True)[:3]]
                       + [f"{c} {short_url(u)}" for _, _, c, u, _ in batch if c >= 400][:3], (1, 10), errors + len(slow_requests))
        indicator(0, "Program: " + ("high resources" if program_alerts else "normal resources"), list(program_alerts), (1, 99), len(program_alerts))
        if self.probes:
            lines.append("  " + color_code(STYLES["debug"], f"ℹ Probes from this server: {sum(self.probes.values())} local requests (app-health-check.py) ignored as suspicious — {self.top(self.probes, 3)}"))
        suspects = sum(self.suspect_urls.values())
        if suspects:
            lines.append("  " + color_code(STYLES["debug"], f"ℹ Suspicious requests seen: {suspects} de {len(self.suspect_ips)} address(es)"))
        header = {0: color_code("1;32", "✔ everything is fine"), 1: color_code(ORANGE, "⚠ to look at"), 2: color_code("1;31", "✖ problem")}[worst]
        return worst, [f"Health: {header}"] + lines

    def watch_lines(self):
        """--watch: for each pattern, requests, errors, median / 95th percentile / maximum duration, slow requests and confirmed registrations (registration/confirm)."""
        res = []
        for pattern in self.watch_it:
            batch = [x for x in self.watched if x[0] == pattern]
            if not batch:
                res.append(f"  Watch « {pattern} » : no request")
                continue
            durations = sorted(d for _, d, _, _, _ in batch if d is not None)
            errors = sum(1 for _, _, c, _, _ in batch if c >= 400)
            slow_requests = sum(1 for d in durations if self.slowest and d >= self.slowest)
            confirmed = sum(1 for _, _, c, u, _ in batch if "registration/confirm" in u and c < 400)
            t = f"  Watch « {pattern} » : {len(batch)} requests · {errors} errors"
            if durations:
                t += f" · median duration {durations[len(durations) // 2]:.2f} s · 95th percentile {durations[min(len(durations) - 1, int(0.95 * len(durations)))]:.2f} s · maximum {durations[-1]:.2f} s"
            if self.slowest:
                t += f" · {slow_requests} slow (≥ {self.slowest:g} s)"
            if confirmed:
                t += f" · {confirmed} confirmed registrations"
            res.append(numbers(t))
            res.extend(numbers(text_line) for text_line in self.watch_detail(batch))
        return res

    def watch_detail(self, batch):
        """--watch: most viewed pages (with their visitors), visitors including robots, and for each survey (/survey/…) its accesses, visitors and submissions, named by its title
        (read from PostgreSQL) — for example one survey per ticket type of an event. Neither static files nor requests under 400 (errors are counted above)."""
        pages, page_visitors, surveys, all_ = Counter(), {}, {}, set()
        for _, _, code, url, ip in batch:
            path = url.split("?", 1)[0]
            if STATIC_RE.search(path) or code >= 400:
                continue
            all_.add(ip)
            m = SURVEY_TOKEN_RE.match(path)
            if m:
                token = m.group(1).lower()
                name = self.survey_titles.get(token) or f"sondage {token[:8]}…"
                card = surveys.setdefault(name, {"access": 0, "posts": 0, "ips": set()})
                if path.startswith("/survey/submit/"):
                    card["posts"] += 1
                else:
                    card["access"] += 1
                card["ips"].add(ip)
                continue
            tag = path.rstrip("/") or "/"
            pages[tag] += 1
            page_visitors.setdefault(tag, set()).add(ip)
        res = []
        if all_:
            robots = sum(1 for ip in all_ if self.is_robot(ip))
            res.append(TR("    Visitors: {total} address(es) including {robots} probable robots").format(total=len(all_), robots=robots))
        if pages:
            res.append("    Pages : " + " · ".join(f"{short_url(c, 70)} ×{n} ({len(page_visitors[c])} visiteurs)" for c, n in pages.most_common(5)))
        for name, f in sorted(surveys.items(), key=lambda kv: -(kv[1]["access"] + kv[1]["posts"]))[:6]:
            res.append(f"    Survey « {name} » : {f['access']} access(es) · {len(f['ips'])} visitors · {f['posts']} answer submissions")
        return res

    def agents_note(self, visitors):
        """Reliability of the percentage: share of the visitors whose User-Agent is known (nginx access journal); otherwise, a maximum."""
        known_ones = sum(1 for ip in visitors if ip in self.agents)
        part = 100 * known_ones // len(visitors) if visitors else 0
        if part >= 90:
            return f"  (User-Agent read for {part} % of visitors)"
        return f"  (at most: User-Agent read for {part} % of visitors only; the others are recognized only by name or robots.txt)"

    def is_robot(self, ip):
        """Probable robot: requested robots.txt or a sitemap, or carries a known robot name. A known person or the team is never one."""
        if ip in self.people or ip in self.protected_ones or ip in self.server:
            return False
        ua = self.agents.get(ip)
        return ip in self.robots_ips or bool(ROBOT_NAME_RE.search(self.names.get(ip, ""))) or (ua is not None and bool(ROBOT_UA_RE.search(ua)))

    def visit_lines(self):
        """The lines of visit_levels(), without their level."""
        return [text_line for _, text_line in self.visit_levels()]

    def visit_levels(self):
        """[(level, line)] — Website visits: visits (an address that returns after 30 min counts as a new one), pages viewed, visitors (known people, team or place, anonymous),
        pages per visitor, countries of the visitors, most visited pages. Only PAGES (neither files, nor errors, nor suspicious requests)."""
        pages, visitors = sum(self.pages.values()), list(self.pages_per_ip)
        if not pages:
            return []
        known_list = sum(1 for ip in visitors if ip in self.people)
        protected_ones = sum(1 for ip in visitors if ip not in self.people and ip in self.protected_ones)
        anonymous = len(visitors) - known_list - protected_ones
        res = [numbers(f"  Site visits: {sum(self.visits.values())} visits · {pages} pages viewed · {len(visitors)} visitors "
                        f"[{known_list} known persons · {protected_ones} team or place · {anonymous} anonymous] · {pages / len(visitors):.1f} pages per visitor")]
        pays = Counter(self.pays.get(ip) for ip in visitors if self.pays.get(ip))
        if pays:
            unknown_ones = len(visitors) - sum(pays.values())
            shown_ones = pays.most_common(8)
            other_ones = sum(pays.values()) - sum(n for _, n in shown_ones)      # 1.94: the countries beyond the 8 most frequent were not counted on the line
            res.append(numbers("  Visitors' countries: " + " · ".join(f"{k} {n}" for k, n in shown_ones)
                               + (f" · other countries {other_ones}" if other_ones else "") + (f" · unknown country {unknown_ones}" if unknown_ones else "")))
        robots = [ip for ip in visitors if self.is_robot(ip)]
        robot_pages = sum(self.pages_per_ip[ip] for ip in robots)
        real = len(visitors) - len(robots)
        names = Counter(re.sub(r"\s*\[.*$", "", self.names.get(ip, ip)) for ip in robots)
        res.append(numbers(f"  Robots: {len(robots)} address(es) out of {len(visitors)} ({100 * len(robots) / len(visitors):.0f} %) · {robot_pages} pages seen "
                            f"({100 * robot_pages / pages:.0f} % of pages)" + (" — " + " ; ".join(f"{n} ×{c}" for n, c in names.most_common(3)) if robots else "")))
        res.append(numbers(f"  Real visitors: {real} out of {len(visitors)} ({100 * real / len(visitors):.0f} %) · {sum(self.visits[ip] for ip in visitors if ip not in robots)} visits · "
                            f"{(pages - robot_pages) / real:.1f} pages per real visitor" if real else "  Real visitors: none (all visitors are robots)")
                   + color_code(STYLES["debug"], self.agents_note(visitors)))
        res.append("  Most visited pages (responses below 400): " + self.top(self.pages, 5))
        return [(self.visit_line_level(text_line), text_line) for text_line in res]

    @staticmethod
    def visit_line_level(text_line):
        """Level of a visits line: country 5; visits, robots, real visitors 6; most visited pages 7."""
        raw = ANSI_RE.sub("", text_line).lstrip()
        if raw.startswith("Visitors' countries"):
            return 5
        if raw.startswith("Most visited pages"):
            return 7
        return 6

    def activity_one_line(self):
        """Levels 2 to 5: the essentials of the activity in one line (requests, pages, visitors including real ones and robots)."""
        pages, visitors = sum(self.pages.values()), list(self.pages_per_ip)
        if not pages:
            return f"  Activity: {self.requests} requests"
        robots = sum(1 for ip in visitors if self.is_robot(ip))
        return numbers(f"  Activity: {self.requests} requests · {pages} pages viewed · {len(visitors)} visitors ({len(visitors) - robots} real, {robots} bots)")

    def summary(self, extras=(), program_alerts=(), heading="Session summary", level=LEVEL_MAX, people=()):
        """Lines of the session summary (or of the period, for Ctrl-T): health, what happened, efficiency of the program (extras).
        `level` (1 to 9, keys 1 to 9, --level) chooses the detail; each level adds to the previous one, 9 shows everything:
        1 the health verdict and what is wrong · 2 + the activity in one line · 3 + all the health indicators · 4 + the alerts (suspicious, 4xx / 5xx, slow, bans) ·
        5 + most active addresses, countries, languages · 6 + visits, robots, real visitors · 7 + most visited pages, HTTP codes · 8 + top 10 URLs, Odoo errors ·
        9 + everything else ("none" included), efficiency of the program."""
        level = max(1, min(LEVEL_MAX, int(level)))
        end = getattr(self, "end", None) or time.time()
        start = self.start if self.period else (self.first or self.start)     # everything: from the oldest line seen (history included); Ctrl-T: from the last display
        duration_s = int(end - start)
        res = [color_code(STYLES["title"], TR("──── {heading} ({name} v{version}) : since {start} for {duration} · {lines} lines shown · {requests} requests ────").format(
                            heading=heading, name=os.path.basename(__file__), version=__version__, start=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start)),
                            duration=f"{duration_s // 3600:02d}:{duration_s % 3600 // 60:02d}:{duration_s % 60:02d}", lines=self.lines, requests=self.requests))]
        health = self.health(program_alerts)[1]
        if level < 3:                                               # verdict + only what is wrong (the check mark from level 3)
            health = [text_line for text_line in health if not ANSI_RE.sub("", text_line).lstrip().startswith("✔")]
        res.extend(health)
        if not self.requests:
            return res + ["  No request in the lines shown."] + (list(people) if level >= 5 else []) + (list(extras) if level >= 9 else [])
        blocks = []                                                   # [(minimum level, line)] in the display order of level 9
        if 2 <= level <= 5:
            blocks.append((2, self.activity_one_line()))
        blocks.append((5, "  Most active addresses: " + " ; ".join(f"{self.who(ip)} " + color_code("1;36", f"×{n}") for ip, n in self.par_ip.most_common(5))))
        named = sum(self.by_name.values())                                           # requests whose address has an identified name (DNS column)
        blocks.append((5, f"  Requests by name (DNS column): {named} identified, {self.requests - named} by address only"))
        pays_par_nom = {}                                                             # name -> Counter of the countries of its addresses (most frequent shown)
        for ip in self.par_ip:
            nom = self.names.get(ip, ip)
            if nom != ip and nom in self.by_name and self.pays.get(ip):
                pays_par_nom.setdefault(nom, Counter())[self.pays[ip]] += 1
        blocks.extend((5, f"      {name}" + (f" [{pays_par_nom[name].most_common(1)[0][0]}]" if name in pays_par_nom else "") + " " + color_code("1;36", f"×{n}"))
                      for name, n in self.by_name.most_common(10))
        if len(self.by_name) > 10:
            blocks.append((5, f"      +{len(self.by_name) - 10} names not shown"))
        if self.suspect_ips:
            blocks.append((4, color_code(STYLES["suspect"], " Suspicious requests ") + f" {sum(self.suspect_urls.values())} de {len(self.suspect_ips)} address(es) — "
                          + self.top(self.suspect_urls)))
            blocks.append((4, "      by address: " + " ; ".join(f"{self.who(ip)} " + color_code("1;36", f"×{n}") + (color_code(STYLES["banned"], f" [banned: {self.banned[ip]}]") if ip in self.banned else "")
                                                               for ip, n in self.suspect_ips.most_common(5))))
        else:
            blocks.append((9, f"  Suspicious requests: {none_found()}."))
        if self.probes:
            blocks.append((9, f"  Probes from this server: {sum(self.probes.values())} local requests (app-health-check.py), not counted as suspicious — {self.top(self.probes, 3)}"))
        for class_, caption, style in ((5, "5xx errors (critical)", STYLES["url_critical"]), (4, "4xx errors (warnings)", STYLES["url_warning"])):
            if self.errors[class_]:
                blocks.append((4, color_code(style, f" {caption} ") + f" {sum(self.errors[class_].values())} — " + self.top(self.errors[class_])))
                if class_ == 5:
                    blocks.extend((4, "      " + text_line) for text_line in self.http_error_detail(5))
            else:
                blocks.append((9, f"  {caption} : {none_found()}."))
        if self.not_found and self.list_404:
            blocks.append((1, color_code(STYLES["url_warning"], " Pages not found (404) ") + f" {len(self.not_found)} pages, {sum(self.not_found.values())} responses:"))
            blocks.extend((1, f"      {short_url(u, 100)} ×{n}") for u, n in self.not_found.most_common())
        if self.slowest:
            if self.slow_requests:
                more = max(self.slow_requests)
                slowest_at = self.slow_info[self.slow_requests.index(more)][4] if len(self.slow_info) == len(self.slow_requests) else None      # 1.94: its time
                blocks.append((4, color_code(STYLES["slow_request"], f" Slow requests (≥ {self.slowest:g} s) ") + f" {len(self.slow_requests)} — the slowest: {more[0]:.1f} s {short_url(more[1])} ({self.who(more[2])})" + (f" · {clock_of(slowest_at)}" if slowest_at else "")))
            else:
                blocks.append((9, f"  Slow requests (≥ {self.slowest:g} s) : {none_found()}."))
        views = {ip: src for ip, src in self.banned.items()}
        blocks.append((4 if views else 9, "  Banned addresses seen: " + color_code(ORANGE if views else "32", str(len(views))) + (" — " + " ; ".join(f"{self.who(ip)} ({src})" for ip, src in list(views.items())[:5]) if views else ".")))
        to_ban = self.to_ban()
        if to_ban:
            blocks.append((4, color_code(ORANGE, f"  Addresses to ban: {len(to_ban)}") + " — " + " ; ".join(f"{self.who(ip)} ({self.ban_reason(ip, n)})" for ip, n in to_ban[:5])
                          + "  (key b: ban them with nginx-log-audit.sh --ban, like web-monitor.py)"))
        else:
            blocks.append((9 if not self.reco_diagnostic() else 4, f"  Addresses to ban: {none_found()} (key b to check)." + (f" Recommendations from web-monitor.py: {self.reco_diagnostic()}." if self.reco_diagnostic() else "")))
        pages = sum(self.languages.values())
        if pages:
            blocks.append((5, numbers(f"  Pages by language ({pages} pages): " + " · ".join(f"{language_label(k)} {100 * v / pages:.0f} %" for k, v in self.languages.most_common()))))
        blocks.extend(self.visit_levels())
        blocks.extend((4, text_line) for text_line in self.watch_lines())
        total = sum(self.statuses.values())
        if total:
            blocks.append((7, "  HTTP codes: " + " · ".join(color_code(http_style(int(k) * 100), f"{k}xx {percent_text(self.statuses[k], total)} %") for k in sorted(self.statuses))))
        blocks.append((8, "  Top 10 URLs (all requests, errors included):"))
        for url, n in self.urls.most_common(10):
            blocks.append((8, "    " + color_code("1;36", f"{n:>6}") + f"  {short_url(url, 90)}"))
        if self.odoo_errors:
            blocks.append((8, f"  Odoo errors and warnings: {sum(self.odoo_errors.values())} — "
                          + " ; ".join(f"{k[0]} {k[1]} ×{v} : {cut_words(k[2], 200)}" for k, v in self.odoo_errors.most_common(5))))
        blocks.extend((4, text_line) for text_line in LATENCY.lines(level))       # session-long latency (also with Ctrl-T: labeled "since start")
        res.extend(text_line for n, text_line in blocks if n <= level)
        if level < LEVEL_MAX:
            res.append(color_code(STYLES["title"], f"  Level {level} out of {LEVEL_MAX}") + " — keys 1 to 9 for more or less detail (9 = everything)")
        return res + (list(people) if level >= 5 else []) + (list(extras) if level >= 9 else [])


BUFFER_DEFAULT = 200                # 1.113 --buffer N: last displayed lines kept in memory (f: displayed again with the current options; P: printed to a file)
STATUS_EVERY_DEFAULT = -1          # 1.113 --status-every N: status bar (reverse video) after every N displayed lines; 0 = never; -1 (1.120, 1.131): automatic = two thirds of the terminal height
# 1.113 SQL injection attempts, on the decoded URL: UNION SELECT, time or error functions (sleep, benchmark, extractvalue...), tautologies (' or 1=1), stacked statements
SQLI_RE = re.compile(r"union(?:\s|\+|/\*.*?\*/|%20)+(?:all(?:\s|\+|%20)+)?select|information_schema|\b(?:sleep|benchmark|pg_sleep|load_file|extractvalue|updatexml)\s*\("
                     r"|\bxp_cmdshell\b|\bor\s*['\"]?\d+['\"]?\s*=\s*['\"]?\d+|'\s*(?:or|and)\s|;\s*(?:drop|insert|update|delete|shutdown)\b|\bconcat\s*\(\s*0x", re.IGNORECASE)


STATUS_SLOW_S = 9.0            # 1.119: only the requests slower than this (seconds) change the colour of the status bar


def criticite(valeur, jaune, rouge):
    """1.125: SGR of a status bar figure: 32 green below `jaune`, 33 yellow from `jaune`, 31 red from `rouge` (more is worse)."""
    return "31" if valeur >= rouge else "33" if valeur >= jaune else "32"


class StatusBar:
    """1.113: cumulative summary of the recent problems, drawn as a reverse-video bar every N displayed lines (--status-every N): SQL injection attempts,
    4xx and 5xx answers, addresses currently banned (seen), slow requests (--slow). Reset by the detailed reports (Ctrl-T and g).
    Colour of the bar: white = nothing to see, green = a little (4xx, a few slow requests), yellow = to look at (SQL injection, 5xx, banned addresses,
    many slow requests), red = investigate now (repeated SQL injection, many 5xx, many slow requests).
    1.114: the three addresses with the most problem lines are shown (only when the addresses are displayed: --show-ip; hidden otherwise);
    `alerted` is set once the bar turns red, so that the alert (beep and line) is given once until the next reset."""
    TOP_IPS = 3

    def __init__(self, show_ips=False):
        self.show_ips = show_ips
        self.reset()

    def reset(self):
        self.sql_max = self.odoo_err = 0                 # 1.120: most SQL queries of one request; Odoo ERROR and CRITICAL lines
        self.ports = collections.Counter()               # 1.121: nginx requests per port (server port and Odoo upstream port)
        self.sqli = self.e4 = self.e5 = self.slow = 0
        self.bots403 = 0                                                       # 1.130: 403 answered to the bots refused by policy
        self.codes = collections.Counter()               # 1.124: 4xx and 5xx answers by code (403, 404, 500...)
        self.slow_max = 0.0
        self.banned = set()
        self.problems_by_ip = collections.Counter()
        self.alerted = False

    def observe(self, L, banned_ip, slow_threshold, ip=None):
        """Counts one displayed line (banned_ip: its address, when the line carries a [banned: ...] label; ip: its first address)."""
        problem = False
        werk = WERKZEUG_RE.search(L.text or "")
        if werk and werk.group(5):
            self.sql_max = max(self.sql_max, int(werk.group(5)))           # 1.120: the most SQL queries of one request (its "transaction")
        if L.level in ("ERROR", "CRITICAL") and L.database != "nginx":
            self.odoo_err += 1                                              # 1.120: Odoo errors (nginx errors are not counted here)
        if L.database == "nginx" and L.logger == "request":
            for port_re in (PORT_RE, UPSTREAM_PORT_RE):                     # 1.121: each nginx request counted for its port(s)
                found = port_re.search(L.text or "")
                if found:
                    self.ports[found.group(1)] += 1
        request = REQUEST_RE.search(L.text or "")
        if request:
            code = int(request.group(2))
            if 400 <= code < 500 and is_bot_403(L):
                self.bots403 += 1                                               # 1.130: policy, not an error: no health penalty, no problem address
            elif 400 <= code < 500:
                self.e4 += 1
                self.codes[code] += 1
                problem = True
            elif code >= 500:
                self.e5 += 1
                self.codes[code] += 1
                problem = True
            if SQLI_RE.search(unquote(request.group(1))):
                self.sqli += 1
                problem = True
        if banned_ip:
            self.banned.add(banned_ip)
            problem = True
        if ip and problem:
            self.problems_by_ip[ip] += 1
        total = request_duration(L.text or "")
        if total is not None and total > STATUS_SLOW_S:               # 1.119: the bar counts only the slow connections of more than 9 s
            self.slow += 1
            self.slow_max = max(self.slow_max, total)

    def pieces(self, users=None, ssh=None):
        """1.125: the bar as [(text, SGR)]: the figures are coloured by criticality (32 green, 33 yellow, 31 red); SGR None = colour of the bar."""
        groups = [
            [(TR("health state") + " ", None), (f"{self.health()} %", "32" if self.health() >= 90 else "33" if self.health() >= 70 else "31")],
            [(TR("SQLi attacks") + " ", None), (f"{self.sqli}", criticite(self.sqli, 1, 5))],
            self.codes_pieces(400, self.e4),
            self.codes_pieces(500, self.e5),
            [(TR("banned") + " ", None), (f"{len(self.banned)}", criticite(len(self.banned), 1, 5))],
            ([(TR("bots refused (403)") + " ", None), (f"{self.bots403}", None)] if self.bots403 else []),
            [(TR("slow") + " ", None), (f"{self.slow}", criticite(self.slow, 5, 20))] + ([(f" (max {self.slow_max:.1f} s)", None)] if self.slow else []),
            [(TR("max SQL") + " ", None), (f"{self.sql_max}", criticite(self.sql_max, 300, 1000))],
            [(TR("Odoo errors") + " ", None), (f"{self.odoo_err}", criticite(self.odoo_err, 1, 10))],
        ]
        if users is not None:
            groups.append([(TR("Odoo users") + " ", None), (f"{users}", None)])
        groups.append([(TR("per port") + " ", None), ((" · ".join(f"{p}: {n}" for p, n in sorted(self.ports.items())) if self.ports else TR("no port data")), None)])      # 1.121
        if ssh is not None:
            groups.append([(TR("SSH") + f" {ssh}", None)])
        top = self.top_ips()
        if top:
            groups.append([(top, None)])
        out = []
        for i, group in enumerate(groups):
            if i:
                out.append((" · ", None))
            out.extend(group)
        return out

    def color(self):
        """SGR code of the reverse-video bar: 37 white, 32 green, 33 yellow, 31 red.
        1.119: the colour follows ONLY the slow connections (more than 9 s): 1 to 4 green, 5 to 19 yellow, 20 and more red.
        The other problems (4xx, 5xx, SQL injection, banned addresses) are still counted and shown in the text of the bar."""
        if self.slow >= 20:
            return "31"
        if self.slow >= 5:
            return "33"
        if self.slow:
            return "32"
        return "37"

    def health(self):
        """1.120: health of the bar, out of 100 %: SQL injection attempts (3 points), 5xx (2), banned addresses (2 each), 4xx (0.1 each) and
        connections slower than 9 s (1 each) take points off. 1.130: the 403 answered to the bots refused by policy take none (counted apart).
        Reset by Ctrl-T and g, like the other counters."""
        penalty = 3 * self.sqli + 2 * self.e5 + 0.1 * self.e4 + 2 * len(self.banned) + self.slow
        return max(0, round(100 - penalty))

    def top_ips(self):
        """1.114: the addresses with the most problem lines, as "ip (count)", or the text saying they are hidden (--hide-ip)."""
        if not self.problems_by_ip or not self.show_ips:        # 1.116: nothing at all when the addresses are hidden (no "hidden" text)
            return ""
        best = self.problems_by_ip.most_common(self.TOP_IPS)
        return TR("top IP") + " " + ", ".join(f"{ip} ×{count}" for ip, count in best)      # 1.119: no parentheses

    def codes_pieces(self, first, total):
        """1.124: the 4xx (first=400) or 5xx (first=500) answers, split by code: "4xx 172 (403: 3 · 404: 169)"; no split when there is none. 1.125: coloured pieces."""
        thresholds = (20, 100) if first == 400 else (1, 5)
        codes = [(code, n) for code, n in sorted(self.codes.items()) if first <= code < first + 100]
        out = [(f"{first // 100}xx ", None), (f"{total}", criticite(total, *thresholds))]
        if codes:
            out.append((" (", None))
            for i, (code, n) in enumerate(codes):
                if i:
                    out.append((" · ", None))
                out.append((f"{code}: ", None))
                out.append((f"{n}", criticite(n, *thresholds)))
            out.append((")", None))
        return out

    def codes_text(self, first, total):
        """1.124: text of codes_pieces (no colour)."""
        return "".join(text for text, _ in self.codes_pieces(first, total))

    def summary(self, users=None, ssh=None):
        """1.120: users and ssh (number of people signed in to Odoo, of SSH sessions) are given by the caller when known. 1.125: text of pieces()."""
        return "".join(text for text, _ in self.pieces(users, ssh))


class Output:
    """Screen + DAILY JOURNAL: everything displayed is also appended, with its colors (escape sequences), to `FOLDER/app-log-live-YYYY-MM-DD.log` (one file per day,
    mode 600: the journal contains addresses and names) — to be re-read with "less -R file" or "tail -f file". Only the live stream, not the startup history (otherwise
    each launch would copy it again). Files older than `keep_days` days are deleted (0: never). A write error disables the journal, never the program."""
    def __init__(self, screen, folder=None, keep_days=30, screen_color=True, suffix=""):
        self.screen, self.folder, self.keep_days, self.screen_color, self.suffix = screen, folder, keep_days, screen_color, suffix
        self.active = False                               # true after the startup history
        self.file_path, self.day, self.path = None, None, None
        self.buffer = collections.deque(maxlen=4000)      # last chunks displayed, without colors: error report of the r key
        self.truncate = None                              # --truncate (1.83, by default since 1.88): None = whole lines; 0 = $COLUMNS - 10; N = N columns (stream lines, screen only, not the journal)
        self.anonymize = None                             # --anonymize (1.88, by default): Anonymiseur of apps/_anonymiser.py applied to the screen (the daily journal keeps everything)
        self.underline = UNDERLINE_DEFAULT                # 1.89: --no-underline / UNDERLINE=non: no line underlined; 1.91: --underline N = one line out of N (0 = none)
        self.anonymiser = None                            # 1.91: the Anonymiseur, kept when the A key turns --anonymize off (same pseudonyms when turned on again)
        self.html = True                                  # 1.120: a copy of the daily journal in HTML (app-log-live-DATE.html), --no-html-journal: none
        self.html_file, self.html_path = None, None
        self.rec_marker = False                           # 1.93: a test is being recorded (R key): "REC" at the end of each stream line, on screen only (never in the daily journal)

    def _open(self, day):
        os.makedirs(self.folder, mode=0o700, exist_ok=True)
        self.path = os.path.join(self.folder, f"{SCRIPT_NAME}-{day}{self.suffix}.log")
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.file_path = os.fdopen(descriptor, "a", encoding="utf-8", errors="replace")
        self.day = day
        if self.html:
            self._open_html(day)
        self.file_path.write(color_code(STYLES["title"], TR("──── {name}.py v{version} : log of {day}, opened at {time} ────").format(name=SCRIPT_NAME, version=__version__, day=day, time=time.strftime('%H:%M:%S'))) + "\n")
        self.purge(day)

    def _open_html(self, day):
        """1.120: the HTML copy of the day (same folder, mode 600); the page head is written only once, when the file is created."""
        import html as html_module
        self.close_html()                                  # 1.120: the page of the previous day is finished first (day change)
        self.html_path = os.path.join(self.folder, f"{SCRIPT_NAME}-{day}{self.suffix}.html")
        try:
            descriptor = os.open(self.html_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            self.html_file = os.fdopen(descriptor, "a", encoding="utf-8", errors="replace")
            if os.fstat(descriptor).st_size == 0:
                self.html_file.write(HTML_HEAD.format(title=html_module.escape(f"{SCRIPT_NAME} {day}")))
        except OSError:
            self.html_file = None

    def purge(self, day):
        """Deletes the daily journals older than `keep_days` days (according to the date in the file NAME)."""
        if not self.keep_days:
            return
        limit = datetime.date.fromisoformat(day) - datetime.timedelta(days=self.keep_days)
        for name in os.listdir(self.folder):
            m = re.fullmatch(re.escape(SCRIPT_NAME) + r"-(\d{4}-\d{2}-\d{2})(?:-filter|-filtre)?\.(?:log|html)", name)      # 1.120: .html too
            try:
                if m and datetime.date.fromisoformat(m.group(1)) < limit:
                    os.unlink(os.path.join(self.folder, name))
            except (ValueError, OSError):
                pass

    def _log(self, text):
        day = datetime.date.today().isoformat()
        try:
            if day != self.day:
                self.close()
                self._open(day)
            self.file_path.write(text)
            if self.html_file is not None:
                self.html_file.write(html_line(text) + "\n")      # 1.120
        except OSError as e:
            eprint(f"Daily log disabled: {e}")
            self.folder = None

    def screen_text(self, text):
        """Anonymized text for the screen: each piece between two color codes separately (an address in color stays recognized)."""
        if self.anonymize is None:
            return text
        text = self.anonymize.names_sub(text) if hasattr(self.anonymize, "names_sub") else text      # 1.91: names of people, colored and padded (whole line)
        return "".join(part if ANSI_SPLIT_RE.fullmatch(part) else self.anonymize(part) for part in ANSI_SPLIT_RE.split(text))

    def write(self, text, stream=False, underline=False):
        """`stream`: a line of the journal (1.88: shortened by --truncate, underlined if `underline`); other texts (menus, reports) are never cut."""
        text = translate_protected(text)
        self.buffer.append(ANSI_RE.sub("", self.screen_text(text)))
        if self.folder and self.active:
            self._log(text)
        shown = self.screen_text(text)
        if stream and self.truncate is not None:
            width = self.truncate if self.truncate > 0 else max(20, terminal_columns() - 10)
            shown = "\n".join(shorten_line(l, width) if l else l for l in shown.split("\n"))
        rec = stream and self.rec_marker
        if underline and self.underline:
            columns = terminal_columns()
            limit = int(columns * UNDERLINE_RATIO)                  # 1.107: 80 % of the terminal width
            if rec:
                limit = min(limit, columns - REC_WIDTH - 1)         # 1.93: the underline stops before "REC"
            shown = "\n".join(underline_line(l, limit) for l in shown.split("\n"))
        if rec:
            shown = "\n".join(rec_mark(l) if l else l for l in shown.split("\n"))
        self.screen.write(shown if self.screen_color else ANSI_RE.sub("", shown))

    def flush(self):
        if self.file_path is not None:
            try:
                self.file_path.flush()
            except OSError:
                pass
        self.screen.flush()

    def close_html(self):
        """1.120: writes the end of the HTML page and closes it (no-op when there is none)."""
        if self.html_file is not None:
            try:
                self.html_file.write("</pre>\n</body>\n</html>\n")
                self.html_file.close()
            except OSError:
                pass
            self.html_file = None

    def close(self):
        self.close_html()
        if self.file_path is not None:
            try:
                self.file_path.close()
            except OSError:
                pass
            self.file_path = None


def journal_folder(option, no_log_file):
    """Folder of the daily journals: --log-dir, otherwise APP_LOG_LIVE_LOG_DIR ("off": none), otherwise /var/log/app-log-live (root) or ~/.local/state/app-log-live. None: none."""
    if no_log_file:
        return None
    value = option or os.environ.get("APP_LOG_LIVE_LOG_DIR")
    if value is not None and value.lower() == "off":
        return None
    if value:
        return os.path.abspath(os.path.expanduser(value))
    if os.geteuid() == 0:
        return f"/var/log/{SCRIPT_NAME}"
    return os.path.join(os.path.expanduser("~"), ".local", "state", SCRIPT_NAME)


KEY_EVENT = "\0touche"        # marker of a keyboard event in the line queue
PROPOSAL = "\0proposal"      # marker of a repeat-offender address to propose for banning (verdict of nginx-log-audit.sh --evidence)
RECORD_EVENT = "\0record"    # 1.93: marker of a finished test recording (archive created in the background, or its error)
RECORD_STATIC_RE = re.compile(r'"(?:GET|HEAD) +(?:/web/assets/|/web/static/|/[\w.-]+/static/|/web/image|/website/image|/web/content/|/favicon\.ico|/apple-touch-icon|/robots\.txt'
                       r'|/sitemap|/[^ "?]*\.(?:css|js|map|png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|eot|otf)(?:[?#][^ "]*)?[ "])', re.I)   # 1.93: static files (recording noise)
WEBSOCKET_RE = re.compile(r'"GET +/(?:websocket|longpolling)\b')     # 1.93: chat / bus connections of an open tab (recording noise)
RECORD_MAX_LIMIT = 60.0        # 1.99: a test recording (R key) lasts 60 minutes at most: --record-max and RECORD_MAX cannot exceed it, nor be 0 (no limit)
RECORD_MAX_DEFAULT = RECORD_MAX_LIMIT     # 1.93: minutes after which a recording stops by itself (--record-max, RECORD_MAX)
REPEAT_MIN = seuil_commun("REPEAT_MIN", 2)            # past fail2ban bans from which an address is "often banned" (same threshold as nginx-log-audit.sh: "recidivism")
BAN_DELAY = 10              # seconds left to answer the ban proposal; without an answer, the tracking continues
KEYS = {b"\x07": "g", b"\x14": "t"}      # Ctrl-G: dashboard; Ctrl-T: only what changed since the last time
# Simple keys of the menu (? or h): toggles and settings of the command-line options, and a few commands
MENU_KEYS = {b"?": "help", b"h": "help", b"i": "i", b"m": "m", b"n": "n", b"r": "r", b"s": "s", b"v": "v", b"d": "dns", b"t": "dnst", b"H": "H", b"o": "o", b"V": "V",
                b"S": "S", b"I": "I", b"b": "b", b"a": "accent", b"c": "chime", b"e": "exclude", b"T": "report", b"E": "E", b"w": "watch", b"D": "D", b"l": "highlight", b"M": "modules", b"C": "save", b"L": "recent",
                b"G": "G", b"Y": "latency", b"P": "print", b"f": "refresh", b"A": "anonymize", b"R": "record", b"N": "step", b"F": "steps_line", b"q": "addons", b"U": "underline", b"x": "lognginx", b"u": "hideua", b"j": "reqlen"}
MENU_KEYS.update({str(n).encode(): f"level{n}" for n in range(1, LEVEL_MAX + 1)})   # 1 to 9: dashboard at the chosen level
KEYS.update(MENU_KEYS)


class Keyboard:
    """Reads the terminal keyboard during the live stream ("cbreak" mode: no echo, Ctrl-C stays active). While a program runs in the foreground, Ctrl-G
    and Ctrl-T belong neither to the shell (bash, zsh) nor to tmux (prefix Ctrl-b) nor to byobu (F keys). On macOS, Ctrl-T is the terminal's "status" key (SIGINFO): it is
    disabled here so that the program receives it (not verified on macOS). Only if input AND output are a terminal, in the foreground; under Windows (no termios): nothing.
    `interactive()` gives the terminal back to its normal mode (echo, line editing) for a question or a program that asks some."""
    def __init__(self, file):
        self.file, self.old, self.fd = file, None, None
        self.lock = threading.Lock()

    def _cbreak(self):
        import termios
        import tty
        tty.setcbreak(self.fd)
        if sys.platform == "darwin":                     # VSTATUS (Ctrl-T) = SIGINFO: without this, the byte never gets here
            modes = termios.tcgetattr(self.fd)
            modes[6][18] = b"\x00"
            termios.tcsetattr(self.fd, termios.TCSANOW, modes)

    def start(self):
        try:
            import termios
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                return False
            self.fd = sys.stdin.fileno()
            if os.getpgrp() != os.tcgetpgrp(self.fd):          # started in the background (&): does not touch the terminal
                return False
            self.old = termios.tcgetattr(self.fd)
            self._cbreak()
        except (ImportError, OSError, ValueError):
            self.old = None
            return False
        atexit.register(self.restore)
        threading.Thread(target=self._read, daemon=True).start()
        return True

    def _read(self):
        import select
        while self.old is not None:
            try:
                with self.lock:                       # held during the wait: interactive() takes it between two waits
                    ready_ones, _, _ = select.select([self.fd], [], [], 0.3)
                    byte = os.read(self.fd, 1) if ready_ones else None
                if ready_ones:
                    if not byte:
                        return
                    if byte in KEYS:
                        self.file.put((KEY_EVENT, KEYS[byte]))
                time.sleep(0.02)                        # leaves control to interactive()
            except (OSError, ValueError):
                return

    @contextlib.contextmanager
    def interactive(self):
        """Normal mode of the terminal (echo, line editing, Enter) for input() or a program that asks questions; pending keys discarded on return."""
        if self.old is None:
            yield
            return
        import termios
        with self.lock:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            except (OSError, ValueError):
                pass
            try:
                yield
            finally:
                try:
                    termios.tcflush(self.fd, termios.TCIFLUSH)
                    self._cbreak()
                except (OSError, ValueError):
                    pass

    def restore(self):
        if self.old is not None:
            old, self.old = self.old, None
            try:
                import termios
                termios.tcsetattr(self.fd, termios.TCSADRAIN, old)
            except (ImportError, OSError, ValueError):
                pass


def follow(cmd, people, resolver, options, output):
    """Launches the stream; each line waits at most WAIT_DELAY s for its names, in order; 0 or the code of the command.
    options: keep_ip, minimal, presence (Presence object or None), lines (history messages), recap (seconds)."""
    vcmd(cmd)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, universal_newlines=True, errors="replace",
                                start_new_session=True)       # the terminal's Ctrl-C does not reach journalctl: the tracking continues if we refuse to quit
    except OSError as e:
        eprint(f"ERROR: command « {cmd[0]} » not found or cannot be run ({e}).")
        return 1
    file = queue.Queue(maxsize=5000)
    def address_width():
        return COLUMN_WIDTH if options["keep_ip"] else 2
    form, presence = Formatting(options["minimal"], address_width(), options["slow"], options.get("status_header", False), hide_user_agent=options.get("hide_user_agent", False), request_length=options.get("request_length", False)), options["presence"]
    state = {"read_files": 0, "summarized": False, "keep_going": True}
    stats, banned_ips = Stats(options["slow"]), options["banned_ips"]
    LATENCY.start()                                         # 1.82: kernel counters every LATENCY_SAMPLE_S seconds (latency report: key P, Ctrl-G, summary)
    stats.is_banned = banned_ips.source_of if banned_ips is not None else None
    stats.watch_it = list(options.get("watch") or [])

    def load_survey_titles():
        """--watch: {access token: title} of the surveys of each Odoo database seen (read-only in PostgreSQL); empty if impossible or without --watch."""
        odoo_db = people.odoo_db if people is not None else None
        if odoo_db is None or not stats.watch_it or not hasattr(odoo_db, "jetons_sondages"):
            return
        databases_seen = sorted(people.databases_seen) or sorted({b for d in people.par_ip.values() for b, _ in d}) or (odoo_db.bases_odoo() or [])
        for database in databases_seen:
            stats.survey_titles.update(odoo_db.jetons_sondages(database) or {})

    load_survey_titles()
    mail_cache = {"t": 0.0, "lines": []}

    def mails_to_resend():
        """Lines "date  recipients — subject (cause)" of the e-mails that FAILED TO SEND and are still to be resent (state "exception" in PostgreSQL, read-only), FULL addresses
        (that is what tells who received nothing); at most 10, the most recent; memorized 30 s."""
        odoo_db = people.odoo_db if people is not None else None
        if odoo_db is None or options.get("app") not in (None, "odoo"):
            return []
        if time.time() - mail_cache["t"] < 30:
            return mail_cache["lines"]
        days = max(1, math.ceil((time.time() - (stats.first or stats.start)) / 86400))
        databases_seen = sorted(people.databases_seen) or sorted({b for d in people.par_ip.values() for b, _ in d}) or (odoo_db.bases_odoo() or [])     # otherwise: the databases that have e-mails
        all_ = []
        for database in databases_seen:
            was_read = odoo_db.courriels_en_echec(database, days)
            all_.extend((c, database) for c in (was_read or []))
        all_.sort(key=lambda cb: cb[0]["instant"], reverse=True)
        lines = []
        for c, database in all_[:10]:
            cause = (c["raison"] or "unknown cause")[:70]
            lines.append(f"To resend: {time.strftime('%Y-%m-%d %H:%M', time.localtime(c['instant']))}  {c['destinataires'] or '(unknown recipient)'} — {c['sujet'][:50] or '(no subject)'}"
                          f"{' [' + database + ']' if len(databases_seen) > 1 else ''} ({cause})")
        if len(all_) > 10:
            lines.append(f"… and {len(all_) - 10} more: odoo-mail-retry.py --details")
        mail_cache.update(t=time.time(), lines=lines)
        return lines
    stats.mail_detail = mails_to_resend
    resources0 = Resources.measure()
    ref = {"stats": stats.snapshot(), "res": resources0, "cache": Counter()}              # last display (Ctrl-G / Ctrl-T): base of the difference
    stats.list_404 = options["not_found"]
    disk_alert = {"next_one": 0.0, "reminder": {}}
    connections_alert = {"next_one": 0.0, "reminder": {}}
    service_state = {"next_one": time.time() + float(os.environ.get("APP_LOG_LIVE_SERVICE_WAIT", "30")), "warned": False}

    def check_service(now_dt):
        """Idle stream (journal of a systemd service): if the service is NOT active, no line will ever arrive from its journal. Odoo may be started by hand (odoo-bin) or under
        another unit: a single alert (re-armed when the service becomes active again) that says so and tells what to do."""
        service = options.get("service")
        if not service or not cmd or "journalctl" not in cmd or now_dt < service_state["next_one"]:
            return
        service_state["next_one"] = now_dt + 60
        code, text = lancer(["systemctl", "is-active", service], 5)
        status_code = (text or "").strip().splitlines()[-1] if (text or "").strip() else ""
        if status_code == "active":
            service_state["warned"] = False
            return
        if service_state["warned"] or not status_code:
            return
        service_state["warned"] = True
        _, processes = lancer(["pgrep", "-af", "odoo-bin"], 5)
        elsewhere = [l for l in processes.splitlines() if "pgrep" not in l][:2]
        lines = [color_code(STYLES["warning"], TR("⚠ The service {service} is '{status}': no more lines will come from its journal (the follow is not frozen, it is waiting).").format(service=service, status=status_code))]
        if elsewhere:
            lines.append(color_code(STYLES["warning"], "  Odoo is running outside this service though (started by hand?): " + " | ".join(l[:110] for l in elsewhere)))
            lines.append(color_code(STYLES["warning"], "  To follow that Odoo: set 'logfile = /var/log/odoo/odoo.log' in its config.conf and restart it (the program then reads that file if ODOO_CONF, in /etc/default, points to this config.conf), or start the service (systemctl start " + service + "), or use --service NAME if Odoo runs under another unit."))
        else:
            lines.append(color_code(STYLES["warning"], "  No odoo-bin process is running: start the service (systemctl start " + service + ")."))
        output.write("\n".join(lines) + "\n")
        output.flush()
    ip_state = {"next_one": 0.0}
    alert = {"stats": stats.snapshot(), "res": resources0, "next_one": time.time() + options["health"] * 60}
    keys = Keyboard(file) if options["keys"] else None
    tail_agents = read_agents(stats.agents, options.get("acces_logs"), NGINX_DIR) if options.get("agents") else None
    beep = {"last": 0.0, "mode": "bel"}
    periodic = {"next_report": time.time() + options["report_min"] * 60}
    recent_ones = []                                        # (arrival, line, address) of the lines WITHOUT A NAME: reminder after a login
    deferred = [None]                                   # "bad query" waiting for its cause (next line)
    record = {"r": None, "last": None, "pending": None, "auto": options.get("record_test_log"), "auto_started": False, "exit_after": False, "module": None}   # 1.93: test recording (R key)

    received = [0]                                        # lines taken out of the journal by the reader thread (watchdog)

    def reader():
        after_mail, sent_ids = False, set()
        for raw_line in proc.stdout:
            received[0] += 1
            L = Line(raw_line.rstrip("\n"))
            if "mail.mail" in L.text or "Total emails" in L.text:      # 1.84: who received the e-mail and what it is, instead of the raw Odoo message
                if after_mail and MAIL_TOTAL_RE.search(L.text):
                    after_mail = False
                    continue                                    # "Total emails tried by SMTP: 1" right after a sent e-mail: nothing more to say
                deleted = MAIL_DELETED_RE.search(L.text)
                if deleted and sent_ids and set(re.findall(r"\d+", deleted.group(1))) <= sent_ids:
                    continue                                    # 1.88: Odoo deletes the e-mails it just sent (auto_delete): already said by "E-mail #N sent to ..."
                sent = MAIL_SENT_RE.search(L.text)
                detail = mail_sent_text(L, people) if sent else None
                after_mail = sent is not None
                if sent:
                    sent_ids = (sent_ids if len(sent_ids) < 50 else set()) | {sent.group(1)}
                if detail:
                    L.text = detail
            else:
                after_mail = after_mail and L.text.startswith("Sent batch ")      # "Sent batch 1 emails via mail server ID #2" may come before "Total emails ..."
            m = LOGIN_RE.search(L.text)
            if m and people is not None:             # live login: learned BEFORE replacing the addresses
                people.ajouter(m.group(3), m.group(1), m.group(2), time.strftime("%Y-%m-%dT%H:%M:%S"))
            ips = find_ips(L.text)
            file.put((L, [(ip, resolver.future(ip), resolver.country_future(ip)) for _, _, ip in ips], time.time(), bool(m)))
        file.put(None)

    def renderings_of(L, results, pays):
        res = {}
        for ip, (kind_name, text, account) in results.items():
            if kind_name == "server":                      # the local program that makes this request, according to the requested page
                text = local_program(L.text) or text
            res[ip] = render(kind_name, text, ip, options["keep_ip"], pays.get(ip), resolver.category(ip), account in options["membres"])
            if kind_name == "person":
                stats.people.add(ip)
            if kind_name == "server" or local_address(ip):
                stats.server.add(ip)
            if pays.get(ip):
                stats.pays[ip] = pays[ip]
        return res

    def keep(L, raw_text, isolated=False):
        """--suspect and --only: is the line displayed? A continuation line (Python trace…) follows the decision of the previous line; an "isolated" line
        (reminder of an address) does not change that decision."""
        if not options["suspect"] and not options["only"] and not options["exclude"] and not options["not_found"]:
            return True
        if not isolated and L.level is None and L.ts_txt is not None:
            return state["keep_going"]
        line_ips = find_ips(L.text) if options["exclude"] else []
        ok = ((not options["not_found"] or request_not_found(L.text)) and (not options["suspect"] or suspicious_request(L.text)) and (not options["only"] or any(t in raw_text.lower() for t in options["only"]))
              and not (line_ips and excluded_address(line_ips[0][2], options["exclude"])))
        if not isolated:
            state["keep_going"] = ok
        return ok

    examined = set()                                   # addresses already submitted to nginx-log-audit.sh --evidence (only once per session)
    investigation_lock = threading.Lock()                   # one investigation at a time (reading the journals)

    def evaluate_repeat(ip):
        """Background thread: verdict of nginx-log-audit.sh --evidence; if "ban justified" AND often banned (≥ RECIDIVE_MIN times by fail2ban), proposes the ban."""
        nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
        app = ["--app", options["app"]] if options.get("app") else []
        try:
            with investigation_lock:
                r = subprocess.run(["bash", nla, "--evidence", ip] + app, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL, timeout=180,
                                   env=dict(os.environ, NGINX_TOOLS_LANG="fr"), start_new_session=True)      # 1.84: background work, the user's Ctrl-C is not for it
        except (OSError, subprocess.TimeoutExpired):
            return
        text = ANSI_RE.sub("", r.stdout)
        m = re.search(r"récidive : (\d+) bannissements", text)
        if r.returncode == 0 and "Verdict : bannissement justifié" in text and m and int(m.group(1)) >= REPEAT_MIN:
            file.put((PROPOSAL, ip, int(m.group(1))))

    def watch_repeat(ip, L):
        """An address with suspicious requests, not yet banned or protected: verdict in the background (once per session). Without a terminal or with --no-ban-prompt: nothing."""
        if not ip or ip in examined or not options.get("propose_ban") or keys is None or keys.old is None:
            return
        if ip not in {i for i, _ in stats.to_ban()} or (ip not in stats.suspect_ips and len(stats.ip_not_found.get(ip, ())) < THRESHOLD_404):
            return
        examined.add(ip)
        if os.path.isfile(os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")):
            threading.Thread(target=evaluate_repeat, args=(ip,), daemon=True).start()

    def ask_with_delay(prompt_text, delay):
        """A typed answer, awaited at most `delay` seconds; None if the time has run out (tracking continues), if Ctrl-C or end of input."""
        if keys is None:
            return None
        import select
        with keys.interactive():
            output.flush()
            sig["prompt_count"] += 1
            try:
                print(prompt_text, end="", flush=True)
                ready_ones, _, _ = select.select([sys.stdin], [], [], delay)
                if not ready_ones:
                    print("\n  No answer in " + str(delay) + " s: monitoring continues.")
                    return None
                text = os.read(sys.stdin.fileno(), 256).decode("utf-8", "replace")
                while re.search(r"[^\x08\x7f\n][\x08\x7f]", text):          # backspace (^H or ^?) typed without effect on the terminal: applied here
                    text = re.sub(r"[^\x08\x7f\n][\x08\x7f]", "", text, count=1)
                return text.replace("\x08", "").replace("\x7f", "").strip()
            except (EOFError, KeyboardInterrupt, OSError):
                print()
                return None
            finally:
                sig["prompt_count"] -= 1

    def propose_ban(ip, n):
        """Often-banned address whose verdict is "ban justified": a question with a delay; yes → nginx-log-audit.sh --ban IP --yes."""
        if ip in stats.all_banned:
            return
        write_out([color_code(ORANGE, f"──── Address often banned: {n} fail2ban bans — verdict: ban justified ────"),
                f"  {color_code(STYLES['suspect'], ' ' + ip + ' ')} {stats.who(ip)} — {stats.suspect_ips.get(ip, 0)} suspicious requests in this session"])
        rep = ask_with_delay(TR("Ban {ip} now? [y] yes  [N] no  ({delay} s, no answer: we continue): ").format(ip=ip, delay=BAN_DELAY), BAN_DELAY)
        if (rep or "").strip().lower() not in ("o", "oui", "y", "yes"):
            if rep is not None:
                write_out(["  Not banned."])
            return
        nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
        app = ["--app", options["app"]] if options.get("app") else []
        why = ["--reason", f"app-log-live.py: address often banned ({n} fail2ban bans), verdict: ban justified"]   # 1.87: kept in the ban journal
        r = run_captured(["bash", nla, "--ban", ip, "--yes"] + why + app, "nginx-log-audit.sh", env=dict(os.environ, NGINX_TOOLS_LANG="fr"))
        detail = next((l.strip() for l in r.stdout.splitlines() + r.stderr.splitlines() if re.search(r"Règle|Déjà|REFUSÉ|ÉCHEC", l)), "")
        write_out([f"  {ip} : {('already banned' if 'Déjà' in detail else 'now banned') if r.returncode == 0 else color_code(STYLES['error'], 'NOT banned')}{' — ' + detail if detail else ''}"])
        if r.returncode == 0:
            stats.all_banned.add(ip)

    def noise_category(L):
        """1.93: category of a line for the test recording — the noise (local probes, websockets, static files, robots) goes only to stream-all.log."""
        ips0 = find_ips(L.text)
        ip = ips0[0][2] if ips0 else None
        if ip is not None and (ip in stats.server or local_address(ip)):
            return "local"
        if WEBSOCKET_RE.search(L.text):
            return "websocket"
        if RECORD_STATIC_RE.search(L.text):
            return "static"
        if ip is not None and stats.is_robot(ip):
            return "robot"
        return "kept"

    status = StatusBar(show_ips=bool(options.get("keep_ip")))      # 1.113: counters of the status bar (reset by Ctrl-T and g); 1.114: top addresses if shown
    line_memory = collections.deque(maxlen=max(0, options.get("buffer", BUFFER_DEFAULT)))      # 1.113: last displayed lines (f and P keys)

    def compose(L, renderings, benign):
        """1.113: (base, text, first address, banned source) of a line: base = the line as rendered; text = base plus the [banned: ...] label of its address."""
        base = form.format_value(L, renderings, benign)
        text, ips0, source = base, find_ips(L.text), None
        if banned_ips is not None and ips0 and ips0[0][2] in renderings and renderings[ips0[0][2]][3] is None:        # never for the whitelist or a place
            source = banned_ips.source_of(ips0[0][2])
            if source:
                label = TR("[BANNED]") if L.database == "nginx" else f"[banned: {source}]"      # 1.119: nginx lines: [BANNIE] at the end
                text += " " + color_code(STYLES["banned"], label)
        return base, text, ips0, source

    def paint(L, text, inputs, benign, underline=False):
        """1.113: writes one line and keeps it in the buffer of the f (refresh) and P (print) keys; `inputs` = (results, pays) to render it again."""
        if not state.get("header_shown"):                     # 1.137: the column labels just before the first request line (its real columns)
            plain_line = ANSI_RE.sub("", text)
            if "H1.1" in plain_line:
                try:
                    show_header(plain_line)
                except (ValueError, IndexError, KeyError):   # 1.140: the header is decoration: a line it cannot read never stops the stream
                    state["header_shown"] = True
        shown = highlight_text(text, options["highlight_pattern"])
        if line_memory.maxlen:
            line_memory.append({"L": L, "inputs": inputs, "benign": benign, "shown": shown, "n": state.get("emitted", 0)})
        output.write(shown + "\n", stream=True, underline=underline)       # 1.91: one line out of N underlined

    def emit(L, renderings, benign=False, inputs=None):
        """Writes the line (if --only / --suspect keep it), with the [banned: …] label of its address and counting it for the summary.
        1.113: then the status bar every --status-every lines; `inputs` = (results, pays) of the line, kept for the f and P keys."""
        base, text, ips0, source = compose(L, renderings, benign)
        if record["r"] is not None:                       # 1.93: recorded whatever the display filters (--only, --suspect...): the analysis needs the whole test
            record["r"].add(ANSI_RE.sub("", base), noise_category(L))
        if not keep(L, ANSI_RE.sub("", text)):
            return
        stats.ajouter(L, renderings, source, benign)
        watch_repeat(ips0[0][2] if ips0 else None, L)
        state["emitted"] = state.get("emitted", 0) + 1
        if L.ts_txt:
            state["stamp"] = " ".join(x for x in (L.ts_txt.rpartition(" ")[0], L.host_name) if x)      # 1.125: date and host for the status bar (--status-header)
        paint(L, text, inputs, benign, underline=bool(output.underline) and state["emitted"] % output.underline == 0)
        status.observe(L, ips0[0][2] if source else None, options["slow"], ips0[0][2] if ips0 else None)
        if status.color() == "31" and not status.alerted:      # 1.114: the bar turns red: one beep and one line, until the next reset (Ctrl-T or g)
            status.alerted = True
            sonner(beep["mode"], output.screen)
            output.write(color_code("1;31", "  " + TR("ALERT: the status bar turned red, investigate now (Ctrl-T or g to acknowledge)")) + "\n")
        every = options["status_every"] if options["status_every"] >= 0 else max(5, terminal_rows() * 2 // 3)      # 1.131: automatic = 2/3 of the terminal height (1.120: height minus 2)
        if every and state["emitted"] % every == 0:
            output.write(status_line() + "\n")
        if options["chime"] is not None and is_reportable_error(L, options["chime"]) and time.time() - beep["last"] >= 2.0:       # at most one beep every 2 s
            beep["last"] = time.time()
            sonner(beep["mode"], output.screen)

    def status_line():
        """1.113: the status bar, reverse video, its colour according to the problems counted since the last detailed report.
        1.125: each figure is coloured on its own (reverse video too); the text is cut by its visible length, the escape codes do not count."""
        columns = terminal_columns()
        status.show_ips = bool(options.get("keep_ip"))          # 1.114: follows the H key (--hide-ip / --show-ip) on the fly
        users = len(odoo_logged_in(options.get("presence"), time.time())) if options.get("presence") is not None else None      # 1.120
        stamp = state.get("stamp") if options.get("status_header") else None      # 1.123 --status-header: date and host of the last line, first (1.125: date only)
        head = f" {stamp}  " if stamp else " "
        bar = status.color()
        pieces = [(head + TR("STATUS") + "  ", None)] + status.pieces(users, len(ssh_sessions())) + [("  ·  " + TR("since the last detailed report (Ctrl-T or g)") + " ", None)]
        limit = max(20, columns - 1)
        out, left = [], limit
        for text, code in pieces:
            if left <= 0:
                break
            chunk = text[:left]
            left -= len(chunk)
            out.append(color_code(f"7;1;{code}" if code else f"7;1;{bar}", chunk))
        visible = limit - left
        out.append(color_code(f"7;1;{bar}", " " * max(0, columns - 1 - visible)))
        return "".join(out)

    def show_header(plain=None):
        """1.137-1.139: column labels above the request columns, printed before the first request line and again after a change of --min or
        --request-length (at the next request line, measured on it). `plain`: that rendered line (None: measured on a sample)."""
        start = plain.index("H1.1") if plain is not None and "H1.1" in plain else None
        text = column_header(bool(options["request_length"]), bool(options["minimal"]), address_width(), terminal_columns(), start, plain)
        output.flush()                                          # the lines already written come first (stdout and stderr share the terminal)
        if text:
            eprint(color_code("1;36", text))                 # stderr: the lines of the stream (stdout) keep their own layout
        state["header_shown"] = True

    def refresh_lines():
        """f key: the lines of the buffer are displayed again with the CURRENT options (addresses, names, highlight, --only...). They are not counted again,
        and not written again to the daily journal."""
        entries = [entry for entry in line_memory if entry["inputs"] is not None]
        if not entries:
            write_out(["  " + TR("Nothing to refresh yet (the buffer keeps the last lines displayed: --buffer N).")])
            return
        write_out([color_code(STYLES["title"], TR("──── last {n} lines, displayed again with the current options ────").format(n=len(entries)))])
        active = output.active
        output.active = False                             # display only: the daily journal already has these lines
        try:
            for entry in entries:
                if (options["minimal"] and entry["L"].discard_in_min()) or (options["hide_addons"] and entry["L"].discard_addons()):
                    continue                                  # 1.137: --min and --hide-addons apply to the refreshed lines too
                results, pays = entry["inputs"]
                base, text, _ips0, _source = compose(entry["L"], renderings_of(entry["L"], results, pays), entry["benign"])
                if not keep(entry["L"], ANSI_RE.sub("", text)):
                    continue
                entry["shown"] = highlight_text(text, options["highlight_pattern"])
                output.write(entry["shown"] + "\n", stream=True, underline=bool(output.underline) and entry.get("n", 0) % output.underline == 0)   # 1.118: same lines underlined as on screen
        finally:
            output.active = active

    def print_lines():
        """P key: the lines of the buffer are written to a file WITH their colors (less -R shows them). Created with mode 600: the lines hold addresses and names."""
        available = [entry["shown"] for entry in line_memory]
        if not available:
            write_out(["  " + TR("Nothing to print yet (the buffer keeps the last lines displayed: --buffer N).")])
            return
        count = requested_int(TR("Lines to print (1 to {n}, Enter = all): ").format(n=len(available)), len(available), 1, len(available))
        if count is None:
            return
        default_name = os.path.join(output.folder or os.getcwd(), f"{SCRIPT_NAME}-print-{time.strftime('%Y%m%d-%H%M%S')}.log")
        answer = ask(TR("File (Enter = {name}): ").format(name=default_name))
        if answer is None:
            return
        path = answer.strip() or default_name
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", errors="replace") as file_out:
                file_out.write(color_code(STYLES["title"], f"──── {SCRIPT_NAME}.py v{__version__} : {count} lines printed {time.strftime('%Y-%m-%d %H:%M:%S')} ────") + "\n")
                for shown in available[-count:]:
                    file_out.write(shown + "\n")
        except OSError as error:
            write_out([color_code(STYLES["error"], "  " + TR("Print failed: {error}").format(error=error))])
            return
        write_out(["  " + TR("{n} lines written to {path} (colors kept: less -R {path}; mode 600, names and addresses inside)").format(n=count, path=path)])

    def release_deferred(benign):
        if deferred[0] is not None:
            text_line, renderings = deferred[0]
            deferred[0] = None
            emit(text_line, renderings, benign)
            output.flush()

    def cache_lines(before, after):
        """Efficiency of the address lookup between two instants: share of the requests resolved WITHOUT an external lookup."""
        d = Counter(after)
        d.subtract(before)
        requests_made = d["fast"] + d["memory"] + d["cache"] + d["dns"]
        if not requests_made:
            return ["  Address cache: no request in the period."]
        without = d["fast"] + d["memory"] + d["cache"]
        permanent = "permanent cache active" if resolver.cache is not None else "permanent cache disabled (--no-cache or unreadable)"
        country = d["country_memory"] + d["country_cache"] + d["country"]
        text = TR("  Address cache: {pct:.0f} % of the {total} requests without outside lookup — {mem} already seen in this session, "
                  "{cache} in the permanent cache, {fast} by the lists (person, team, this server), {dns} DNS lookups, {rdap} RDAP ({permanent})").format(
                      pct=100 * without / requests_made, total=requests_made, mem=d["memory"], cache=d["cache"], fast=d["fast"], dns=d["dns"], rdap=d["rdap"], permanent=TR(permanent))
        if country:
            text += TR(" ; countries: {known} out of {total} already known, {lookups} lookups").format(known=d["country_memory"] + d["country_cache"], total=country, lookups=d["country"])
        return [text]

    def socket_lines():
        """Network connections of Odoo NOW (chat / websocket, HTTP, PostgreSQL) with their ports, for the periodic reports and Ctrl-T; [] if nothing is measurable."""
        module, conf_chemin, odoo_conf = load_module("_connexions"), options["profile"].get("ODOO_CONF"), load_module("_odoo_conf")
        if not (module and odoo_conf and conf_chemin):
            return []
        try:
            measures = module.mesurer(odoo_conf.lire(conf_chemin), lambda key_value: odoo_conf.valeur(conf_chemin, key_value))
            text = module.resume(measures)
            fd = [f"{label}{o}/{l}" for label, key_value in (("chat descriptors: ", "fd_gevent"), ("HTTP descriptors: ", "fd_http")) if measures.get(key_value) for o, l in [measures[key_value]]]
        except Exception:  # noqa: BLE001 - a report must never fail because of one measurement
            return []
        return [measured_numbers("  Odoo network connections: " + " · ".join([text] + fd if text else fd))] if text or fd else []

    def table_rows(delta=False, heading="Dashboard since start (history shown included)", delta_heading="Since the last display", level=None):
        """Dashboard lines: everything since startup (Ctrl-G, Ctrl-C) or only since the last display (Ctrl-T). The last display becomes the new base."""
        now_dt, res, cache = stats.snapshot(), Resources.measure(), Counter(resolver.counters)
        before_res, before_cache = (ref["res"], ref["cache"]) if delta else (resources0, Counter())
        period = now_dt.since(ref["stats"]) if delta else now_dt
        # 1.110: "Who is connected now" is shown from level 5 (Ctrl-G and Ctrl-T); before, only at level 9.
        people = ["  " + color_code(STYLES["title"], "Who is connected now")] + logged_in_lines(options.get("presence"))
        extras = ["  " + color_code(STYLES["title"], "Program efficiency")] + [measured_numbers(l) for l in Resources.lines(before_res, res) + cache_lines(before_cache, cache)] + socket_lines()
        lines = period.summary(extras, Resources.alerts(before_res, res),
                                delta_heading if delta else heading, level or options["level"], people=people)
        ref.update(stats=now_dt, res=res, cache=cache)
        return lines

    def check_health(now_dt):
        """Automatic alert (--health MIN): at each period, IF something is wrong, the health and the detail (URLs, error messages, slow requests) are displayed in the stream."""
        if not options["health"] or now_dt < alert["next_one"] or not state["summarized"]:
            return
        instant, res = stats.snapshot(), Resources.measure()
        period = instant.since(alert["stats"])
        level, lines = period.health(Resources.alerts(alert["res"], res))
        if level:
            since = time.strftime("%H:%M:%S", time.localtime(alert["stats"].end))
            output.write(color_code(STYLES["title"], f"──── Health alert ({os.path.basename(__file__)} v{__version__}) : since {since} ────") + "\n" + "\n".join(lines) + "\n")
            output.flush()
        alert.update(stats=instant, res=res, next_one=now_dt + options["health"] * 60)

    def check_disk(now_dt):
        """--disk-min GB: every minute, the free space of the partitions where the journals are written (Odoo, nginx, systemd journal); WARNING in the stream below the threshold
        (repeated every 10 minutes as long as it lasts, and a line when the space becomes sufficient again)."""
        if not options["disk_min"] or now_dt < disk_alert["next_one"]:
            return
        disk_alert["next_one"] = now_dt + 60
        for point, free_amount in journals_free_space({"ODOO_LOGFILE": options["odoo_journal"]}).items():
            if free_amount < options["disk_min"] * 1024 ** 3:
                if now_dt - disk_alert["reminder"].get(point, 0.0) >= 600:
                    disk_alert["reminder"][point] = now_dt
                    output.write(color_code(STYLES["warning"], f"WARNING disk space: {free_amount / 1024 ** 3:.1f} GB free only (threshold {options['disk_min']:g} GB) on {point}, "
                                                       "where the journals are written — risk of Odoo, nginx and the database stopping") + "\n")
                    output.flush()
            elif disk_alert["reminder"].pop(point, None) is not None:
                output.write(color_code(STYLES["debug"], f"Disk space restored on {point} : {free_amount / 1024 ** 3:.1f} GB free") + "\n")
                output.flush()

    def check_connections(now_dt):
        """--connections PCT: every minute, the number of connections to Odoo (chat / websocket, HTTP, PostgreSQL, nginx) against their limits; WARNING in the stream at PCT % or more,
        with the parameter to change (repeated every 10 minutes as long as it lasts, and a line when everything is normal again)."""
        if not options["connections"] or now_dt < connections_alert["next_one"]:
            return
        connections_alert["next_one"] = now_dt + 60
        module, conf_chemin = load_module("_connexions"), options["profile"].get("ODOO_CONF")
        odoo_conf = load_module("_odoo_conf")
        if not (module and odoo_conf and conf_chemin):
            return
        try:
            measures = module.mesurer(odoo_conf.lire(conf_chemin), lambda key_value: odoo_conf.valeur(conf_chemin, key_value))
            findings = module.diagnostiquer(measures, options["connections"], options.get("service") or "odoo.service")
        except Exception:  # noqa: BLE001 - monitoring must never stop the live stream
            return
        seen_set = set()
        for level, finding, advice in findings:
            seen_set.add(finding.split(" : ")[0])
            if now_dt - connections_alert["reminder"].get(finding.split(" : ")[0], 0.0) >= 600:
                connections_alert["reminder"][finding.split(" : ")[0]] = now_dt
                output.write(color_code(STYLES["error"] if level == "critical" else STYLES["warning"],
                                  f"{'CRITICAL' if level == 'critical' else 'WARNING'} connections: {finding}\n    → setting to change: {advice}") + "\n")
                output.flush()
        for old in [c for c in connections_alert["reminder"] if c not in seen_set]:
            del connections_alert["reminder"][old]
            output.write(color_code(STYLES["debug"], f"Connections back to normal: {old}") + "\n")
            output.flush()

    def check_external_ip(now_dt, wait=False):
        """Every 10 minutes (curl ifconfig.me; never with --no-isp): if the external IP address changed since the last known one (memorized in a file),
        it is displayed in the stream with the /etc/default files to change. The first address seen is only memorized.
        The lookup (curl, up to 10 s) is done in a SEPARATE THREAD: it never holds back the display of lines. `wait`: end of the stream, we wait for the result."""
        if not options.get("external_ip"):
            return
        thread = ip_state.get("thread")
        if thread is None:
            if now_dt < ip_state["next_one"]:
                return
            ip_state["next_one"] = now_dt + 600
            ip_state["result"] = []

            def lookup():
                ip_state["result"].append(external_ip())
            ip_state["thread"] = thread = threading.Thread(target=lookup, daemon=True)
            thread.start()
        if wait:
            thread.join(15)
        if thread.is_alive():
            return
        ip_state["thread"] = None
        new_one = ip_state["result"][0] if ip_state["result"] else None
        if not new_one:
            return
        file_path, old_one = external_ip_file(), None
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as f:
                    old_one = f.read().strip() or None
            except OSError:
                old_one = None
        if old_one and old_one != new_one:
            output.write("\n".join(color_code(STYLES["warning"], l) for l in ip_change_message(old_one, new_one)) + "\n")
            output.flush()
        if file_path and old_one != new_one:
            with contextlib.suppress(OSError):
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_one + "\n")

    def periodic_report(now_dt):
        """--time-report MIN: every MIN minutes, the same report as Ctrl-T (what changed since the last display)."""
        if not options["report_min"] or now_dt < periodic["next_report"] or not state["summarized"]:
            return
        periodic["next_report"] = now_dt + options["report_min"] * 60
        output.write("\n" + "\n".join(table_rows(delta=True, delta_heading=f"Periodic report (every {options['report_min']:g} min): since the last display")) + "\n")
        output.flush()

    def show_summary():
        if presence is not None and not state["summarized"]:
            state["summarized"] = True
            for text_line in presence.summary(time.time(), state["read_files"]):
                output.write(text_line + "\n")
            output.flush()
        if not state["summarized"]:
            state["summarized"] = True
        if hasattr(output, "active") and not output.active:      # end of the history: the daily journal receives only the live stream
            output.active = True
            alert.update(stats=stats.snapshot(), res=Resources.measure(), next_one=time.time() + options["health"] * 60)

    def startup_status_bar():
        """1.126: the status bar once, after ALL the history lines are displayed: called when the queue is empty (idle), after at least one line was read,
        and no line is held by --log-merge. The journal gives fewer than N lines when the history is shorter: the idle moment is then the end too."""
        if state.get("startup_bar") or not state.get("consumed") or merge_held:
            return
        state["startup_bar"] = True
        if options["status_every"]:                              # --status-every 0 = never
            output.write(status_line() + "\n")
            output.flush()

    def reminder(L, ip, name):
        """A person has just logged in from ip: their recent lines, displayed higher up without a name, are displayed again with the name."""
        limit = (L.instant or time.time()) - options["recap"]            # window measured on the time of the LINES, not on their arrival here
        earlier = [e for e in recent_ones if e[2] == ip and e[0] >= limit]
        recent_ones[:] = [e for e in recent_ones if e[2] != ip]
        if not earlier or not options["recap"]:
            return
        reminder_form, lines = Formatting(options["minimal"], address_width(), options["slow"], options.get("status_header", False), hide_user_agent=options.get("hide_user_agent", False), request_length=options.get("request_length", False)), []
        for _, old_one, _ in earlier[-50:]:
            if (options["minimal"] and old_one.discard_in_min()) or (options["hide_addons"] and old_one.discard_addons()):
                continue
            renderings = {}
            for _, _, i in find_ips(old_one.text):
                try:
                    g, t, account_i = resolver.future(i).result(timeout=0)
                except Exception:
                    g, t, account_i = "unknown", i, None
                if g == "server":
                    t = local_program(old_one.text) or t
                country_future = resolver.country_future(i)
                try:
                    country_i = country_future.result(timeout=0) if country_future is not None else None
                except Exception:
                    country_i = None
                renderings[i] = render(g, t, i, options["keep_ip"], country_i, resolver.category(i), account_i in options["membres"])
            reminder_text = reminder_form.format_value(old_one, renderings)
            if keep(old_one, ANSI_RE.sub("", reminder_text), isolated=True):
                lines.append("  " + reminder_text)
        if lines:
            since = earlier[0][1].ts_txt[11:19] if earlier[0][1].ts_txt else "?"
            output.write(color_code("1;32", f"↻ {name} [{ip}] : {len(lines)} previous lines of this address (since {since}), "
                                      "shown above without name:") + "\n" + "\n".join(lines) + "\n")

    # --- menu touches (? or h): command line options changed on the fly ------------------------------------------------------
    def write_out(lines):
        output.write("\n".join(lines) + "\n")
        output.flush()

    sig = {"prompt_count": 0, "requested": False}                # prompt: questions in progress; request: Ctrl-C received, to be confirmed on the next loop turn

    def interruption(signum, frame):
        """Ctrl-C: without a terminal or during a question, immediate stop; otherwise only noted — the confirmation is asked by the loop (never in the middle of a write)."""
        if keys is None or keys.old is None or sig["prompt_count"]:
            raise KeyboardInterrupt
        sig["requested"] = True

    def confirm_exit():
        """Ctrl-C: "Quit?" — No: the tracking resumes; Yes, or a second Ctrl-C during the question: stop and summary."""
        write_out([status_line()])                          # 1.121: Ctrl-C shows the status bar before the question
        rep = ask("\nQuit " + os.path.basename(__file__) + " ? [y] yes  [N] no, continue  (Ctrl-C again = quit): ")
        if rep is None or rep.strip().lower() in ("o", "oui", "y", "yes"):
            raise KeyboardInterrupt
        write_out(["  Monitoring continues."])

    def error_details(ask_first):
        """Error detail: app-log-check.py --errors-only (traces and ERROR / CRITICAL messages over the period seen) and, if there are failed e-mails, odoo-mail-retry.py
        (list, without resending anything). At Ctrl-C: a question first."""
        severe = sum(v for k, v in stats.odoo_errors.items() if k[0] in ("ERROR", "CRITICAL"))
        if not severe and not stats.mails:
            if not ask_first:
                write_out(["  No error (ERROR / CRITICAL) or failed e-mail to detail."])
            return
        if ask_first:
            rep = ask(f"{severe} Odoo errors, {stats.mails} failed e-mails. More details on the errors? [y] yes  [N] no: ")
            if (rep or "").strip().lower() not in ("o", "oui", "y", "yes"):
                return
        hour_values = max(1, math.ceil((time.time() - (stats.first or stats.start)) / 3600))
        app = ["--app", options["app"]] if options.get("app") else []
        commands = []
        if severe:
            commands.append(("app-log-check.py", [sys.executable, os.path.join(SCRIPT_DIR, "app-log-check.py"), "--errors-only", "--full-trace", "--last", str(hour_values)] + app))
        if stats.mails and options.get("app") in (None, "odoo"):
            commands.append(("odoo-mail-retry.py", [sys.executable, os.path.join(SCRIPT_DIR, "odoo-mail-retry.py"), "--details", "--no-prompt", "--days", str(max(1, math.ceil(hour_values / 24)))]))
        for name, cmd in commands:
            if not os.path.isfile(cmd[1]):
                write_out([f"  {name} not found next to this program: detail impossible."])
                continue
            write_out([color_code(STYLES["title"], f"──── Error details: {name} (last {hour_values} h) ────")])
            try:
                r = run_captured(cmd, name, timeout=180)
                write_out((r.stdout + r.stderr).rstrip("\n").split("\n"))
            except subprocess.TimeoutExpired:
                write_out([color_code(STYLES["error"], f"  {name} : too long (more than 3 minutes), abandoned.")])
            except OSError as e:
                write_out([color_code(STYLES["error"], f"  {name} : cannot be run ({e}).")])

    def run_captured(cmd, name, timeout=None, env=None):
        """1.84: a program whose output is captured (nginx-log-audit.sh --ban --yes, web-monitor.py, app-log-check.py…), in its OWN session: the terminal's Ctrl-C
        no longer kills it silently. Ctrl-C asks « Interrupt NAME? [y/N] » right away (not at the end of the program): yes stops it (its whole process group),
        no lets it finish. subprocess.TimeoutExpired after `timeout` seconds (program stopped), like subprocess.run; CompletedProcess (code 130 if interrupted)."""
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, errors="replace", env=env, start_new_session=True)
        pending = {"n": 0}
        try:
            old = signal.signal(signal.SIGINT, lambda *_: pending.update(n=pending["n"] + 1))
        except ValueError:                                  # not the main thread: plain wait
            old = None
        deadline = time.time() + timeout if timeout else None
        try:
            while True:
                try:
                    out, err = proc.communicate(timeout=0.3)
                    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
                except subprocess.TimeoutExpired:
                    pass
                if deadline and time.time() > deadline:
                    stop_group(proc)
                    raise subprocess.TimeoutExpired(cmd, timeout)
                if pending["n"]:
                    pending["n"] = 0
                    answer = ask(TR("Interrupt {name}? [y/N] ").format(name=name))
                    if answer is None or answer.strip().lower() in ("o", "oui", "y", "yes"):      # second Ctrl-C or end of input during the question: yes (as everywhere)
                        stop_group(proc)
                        out, err = proc.communicate()
                        write_out([color_code(ORANGE, TR("  {name} interrupted (Ctrl-C).").format(name=name))])
                        return subprocess.CompletedProcess(cmd, 130, out, err)
                    write_out([TR("  {name} continues.").format(name=name)])
        finally:
            if old is not None:
                signal.signal(signal.SIGINT, old)

    def ask(prompt_text):
        """A typed answer (terminal in normal mode: echo and editing); None if Ctrl-C or end of input."""
        if keys is None:
            return None
        with keys.interactive():
            output.flush()
            sig["prompt_count"] += 1
            try:
                return input(prompt_text)
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            finally:
                sig["prompt_count"] -= 1

    def requested_int(prompt_text, default_value, mini, maximum):
        """Typed number (Enter alone: the default value); None if cancelled or invalid."""
        rep = ask(prompt_text)
        if rep is None:
            return None
        rep = rep.strip()
        try:
            n = int(rep) if rep else default_value
        except ValueError:
            n = None
        if n is None or not mini <= n <= maximum:
            write_out([color_code(STYLES["error"], TR("  Value refused « {value} »: a number between {mini} and {maximum} is expected.").format(value=rep, mini=mini, maximum=maximum))])
            return None
        return n

    def yes_no(current_state):
        return "yes" if current_state else "no"           # 1.98: option values in English only (same words as in the configuration file)

    config_at_start = config_values(options, VERBOSE, (NAME_WIDTH, NAME_TRUNCATE))           # settings at startup: the C key writes only what changed since

    # --- 1.93: test recording (R key, --record-test-log): apps/_record.py gathers the logs of the window into a .tar.xz to send for analysis ---------------
    def record_databases():
        """Odoo databases to sample, looked up once per recording (bases_odoo runs several psql)."""
        odoo_db = people.odoo_db if people is not None else None
        if odoo_db is None:
            return []
        if record.get("bases") is None:
            record["bases"] = sorted(people.databases_seen) or sorted({b for d in people.par_ip.values() for b, _ in d}) or (odoo_db.bases_odoo() or [])
        return record["bases"]

    def record_start(label):
        module = record["module"] or load_module("_record")
        if module is None:
            write_out([color_code(STYLES["error"], "  ✖ Recording impossible: apps/_record.py is missing.")])
            return
        record["module"], record["bases"] = module, None
        anonymiser = load_module("_anonymiser")
        odoo_db = people.odoo_db if people is not None else None
        profile = options.get("profile") or {}
        rec = module.Recorder(module.default_folder(options.get("journal_folder")), label,
                              mask=new_anonymiser(anonymiser) if anonymiser is not None else None,
                              query=getattr(odoo_db, "_requete", None) if odoo_db is not None and options.get("app") in (None, "odoo") else None,
                              databases=record_databases, service=options.get("service") if cmd and cmd[0] == "journalctl" else None,
                              namespace=options.get("namespace") or None, log_files=options.get("record_logs") or (), odoo_conf=profile.get("ODOO_CONF"),
                              max_seconds=(options.get("record_max") or 0) * 60, program="app-log-live.py", version=__version__,
                              versions={"_record": module.__version__, "_anonymiser": getattr(anonymiser, "__version__", "missing"),
                                        "_odoo_db": getattr(odoo_db, "__version__", "missing")},
                              ports=options.get("record_ports") or {}, app=options.get("app") or "odoo", filters=options.get("filters_text") or "")
        try:
            rec.start()
        except OSError as e:
            write_out([color_code(STYLES["error"], TR("  ✖ Recording impossible: {error}").format(error=e.strerror or e))])
            return
        record["r"] = rec
        output.rec_marker = output.screen.isatty()
        limit = f"{options['record_max']:g} min" if options.get("record_max") else TR("no limit")
        write_out([color_code(REC_STYLE, " ● REC ") + " " + TR("Recording started at {time}").format(time=time.strftime("%H:%M:%S"))
                   + (f" — « {label} »" if label else "") + " — " + TR("R again to stop (at most {limit}); the noise (robots, static files, websockets, local probes) is left out of records.log.").format(limit=limit)])

    def record_stop(reason, wait=False):
        """Stops the recording: « REC » leaves the screen at once; the archive is made in the background (RECORD_EVENT when done) or right here (wait)."""
        rec = record["r"]
        if rec is None:
            return
        record["r"] = None
        record["last"] = rec                              # 1.101: its steps stay on the F line until the next R
        output.rec_marker = False
        if wait:
            write_out(["  " + TR("Recording stopped: creating the archive…")])
            show_record_result(rec.stop(reason, wait=True))
            return
        record["pending"] = rec
        write_out(["  " + TR("Recording stopped after {seconds} s: creating the archive in the background (the live stream continues)…").format(seconds=f"{rec.elapsed():.0f}")])
        rec.stop(reason, done=lambda result: file.put((RECORD_EVENT, result)))

    def finish_recording(reason):
        """End of the program (Ctrl-C, end of the stream): a recording in progress is closed and its archive made before leaving; one being made is awaited."""
        if record["r"] is not None:
            record_stop(reason, wait=True)
        elif record["pending"] is not None:
            rec, record["pending"] = record["pending"], None
            write_out(["  " + TR("Waiting for the recording archive…")])
            result = rec.join(300)
            if result is not None:
                show_record_result(result)

    def show_record_result(result):
        if result is None:
            return
        if result.get("error") or not result.get("path"):
            write_out([color_code(STYLES["error"], TR("  ✖ Recording: archive not created ({error}).").format(error=result.get("error") or "unknown error"))])
            return
        counts = result.get("counts") or {}
        noise = sum(v for k, v in counts.items() if k != "kept")
        reasons = {"key": "R key", "duration": "maximum duration reached", "size": "maximum size reached", "end": "end of the stream", "interrupt": "Ctrl-C",
                   "test-log": "end of --record-test-log"}
        lines = [color_code("1;32", "  ✔ " + TR("Recording stopped ({reason}): {seconds} s, {kept} lines kept, {noise} noise lines left out").format(
                     reason=TR(reasons.get(result.get("reason"), result.get("reason") or "?")), seconds=f"{result.get('seconds', 0):.0f}", kept=counts.get("kept", 0), noise=noise)),
                 "    " + TR("Archive to send for analysis: {path} ({size})").format(path=result["path"], size=readable_bytes(result.get("size") or 0))]
        if result.get("notes"):
            lines.append(color_code(STYLES["warning"], "    " + TR("Missing or cut sources: {notes}").format(notes="; ".join(result["notes"])[:600])))
        write_out(lines)

    def show_steps_line():
        """1.99 (F key, --steps-line): all the steps of the recording on one line, white reverse video, at each change of step. Screen only: never in the journal or the archive.
        1.101: F works without a recording (R): the steps of the last recording are shown, or a hint when there is none yet."""
        if not options.get("steps_line"):
            return
        columns = terminal_columns()
        current = record["r"]
        source = current or record["last"]
        prefix = "" if current is not None or source is None else TR("Last recording") + " — "
        if source is None:
            body = TR("Steps: no recording yet (R starts one, then N a step)")
        else:
            body = steps_line_text(source.steps, columns - 1 - display_width(prefix))
        text = output.screen_text(truncate_line(prefix + body, columns - 1))     # anonymized like the stream
        output.screen.write(color_code(STEPS_LINE_STYLE, text + " " * max(0, columns - 1 - display_width(text))) + "\n")
        output.screen.flush()

    def check_record(now_dt):
        """Limits of the recording (duration, size) and --record-test-log (automatic start when the live stream begins, stop after MIN minutes, then exit)."""
        rec = record["r"]
        if rec is None:
            if record["auto"] and not record["auto_started"] and getattr(output, "active", True):
                record["auto_started"] = True
                record_start("")
            return
        reason = rec.limit_reason()
        if record["auto"] and rec.elapsed() >= record["auto"] * 60:
            reason, record["exit_after"] = "test-log", True
        if reason:
            if reason in ("duration", "size"):
                write_out([color_code(STYLES["warning"], "  ⚠ " + TR("Recording: {what} — stopped by itself.").format(
                    what=TR("maximum duration reached") if reason == "duration" else TR("maximum size reached")))])
            record_stop(reason)

    def rlq_groups_lines():
        odoo_db = people.odoo_db if people is not None else None
        databases_seen = sorted(people.databases_seen) if people is not None else []
        if not databases_seen and odoo_db is not None and hasattr(odoo_db, "bases_odoo"):
            databases_seen = odoo_db.bases_odoo() or []
        return rlq_group_lines(odoo_db, databases_seen)

    def menu():
        global_name = f"{NAME_WIDTH}" + (f", names cut at {NAME_TRUNCATE}" if NAME_TRUNCATE else ", names never cut")
        to_ban = len(stats.to_ban())
        bold = lambda t: color_code("1;36", t)
        lines = [color_code(STYLES["title"], "──── Keys (? or h: this menu) ────"), "  " + color_code(STYLES["debug"], version_with_date())]
        for key, text in (("Ctrl-G", "dashboard: health, program efficiency, pages by language, top 10 URLs…"),
                              ("1 to 9", "dashboard at the chosen level: 1 = one-line verdict, 5 = the essentials, 9 = everything (the level is kept for Ctrl-G, Ctrl-T and the final summary)"),
                              ("Ctrl-T", "only what changed since last time"),
                              ("Ctrl-C", "stop and session summary")):
            lines.append(f"  {bold(key):<{6 + len(bold('') )}}  {text}")
        lines.append("  Command-line options, changed on the fly ([current state]):")
        chimes = {0: "any error (4xx, 5xx, Odoo ERROR)", 1: "4xx", 2: "5xx and 4xx"}
        for key, option, text in sorted((("a", "--accentuate-group NAME", f"contacts of the Odoo tag in bold white on dark blue [{options['group'] or 'none'}"
                                                                      + (f", {len(options['membres'])} accounts]" if options["group"] else "]")),
                                      ("A", "--anonymize", f"pseudonyms on screen for the addresses, e-mails and names (membre-4f2a9c); the daily log keeps everything [{yes_no(output.anonymize is not None)}]"),
                                      ("c", "--chime N", f"beep on error: 0 all, 1 = 4xx, 2 = 5xx and 4xx [{chimes.get(options['chime'], 'none')}]"),
                                      ("d", "--dns-max N", f"width of the names column, without cutting them [{global_name}]"),
                                      ("t", "--dns-max-truncate N", "width AND limit of the names column (the rest is cut, « … »)"),
                                      ("e", "--exclude-ip IP,IP", f"hide the lines of these addresses or networks [{', '.join(str(r) for r in options['exclude']) or 'none'}]"),
                                      ("H", "--health MIN", f"minutes between two health alerts, 0 = never [{options['health']:g}]"),
                                      ("q", "--hide-addons", f"hide the INFO lines of the Odoo modules (odoo.addons.*), except errors, e-mails sent and generated files (PDF…) [{yes_no(options['hide_addons'])}]"),
                                      ("j", "--request-length", TR("the request length of the nginx lines (rl=) is shown in its own column before the GET") + f" [{yes_no(options['request_length'])}]"),
                                      ("u", "--hide-user-agent", TR("the User-Agent text of the nginx lines is not shown (the OS column stays)") + f" [{yes_no(options['hide_user_agent'])}]"),
                                      ("i", "--hide-ip", f"hide the IP address [{yes_no(not options['keep_ip'])}]"),
                                      ("l", "--highlight WORDS", f"highlight these words in cyan (+word adds, -word removes; comma = several, none = nothing) [{', '.join(options['highlight_words']) or 'none'}]"),
                                      ("m", "--min", f"the minimum of information [{yes_no(options['minimal'])}]"),
                                      ("M", "--modules", f"table of installed Odoo modules, with sorting (name, date, creation, version, author, state) [{options['modules_sort'][0]}]"),
                                      ("L", "--modules-latest N", "the 10 latest installed modules, with the current Odoo version"),
                                      ("n", "--not-found", f"only the pages not found (404) [{yes_no(options['not_found'])}]"),
                                      ("o", "--only TEXT", f"only the lines that contain the text (comma = OR) [{', '.join(options['only']) or 'none'}]"),
                                      ("r", "--report-err", "error report to copy and paste, based on what has been displayed so far"),
                                      ("F", "--steps-line", TR("the steps of the recording (or of the last one) on one white line, updated at each step; works without R") + f" [{yes_no(options['steps_line'])}]"),
                                      ("s", "--suspect", f"only the suspicious requests [{yes_no(options['suspect'])}]"),
                                      ("x", "--log-nginx", f"the nginx logs of the site (read with the application log, in time order; from the next line on) [{yes_no(options['log_nginx'])}]"),
                                      ("U", "--underline N", TR("one log line out of N underlined on screen, up to the end of the screen line (0 = none); UNDERLINE of the configuration file") + f" [{output.underline or 'none'}]"),
                                      ("T", "--time-report MIN", f"report like Ctrl-T every MIN minutes, 0 = never [{options['report_min']:g}]"),
                                      ("v", "--verbose", f"show every external command [{yes_no(VERBOSE)}]"),
                                      ("V", "--version", "program version"),
                                      ("w", "--watch TEXT", f"watch the requests whose URL contains the text: duration, errors, slowness [{', '.join(options['watch']) or 'none'}]")), key=lambda item: (item[0].lower(), item[0].isupper())):      # 1.113: alphabetical order of the short keys
            lines.append(f"    {bold(key)}  {option:<22} {text}")
        lines.append("  Others:")
        lines.append(f"    {bold('G')}  number of members of each Odoo RLQ* group (also in the final summary, Ctrl-C)")
        lines.append(f"    {bold('S')}  survey registrations of the last 30 days")
        lines.append(f"    {bold('I')}  event registrations of the last 30 days, per event and ticket, with the survey of each ticket (answers to another survey pointed out)")
        lines.append(f"    {bold('E')}  error details: app-log-check.py --errors-only, and odoo-mail-retry.py if there are failed e-mails")
        lines.append(f"    {bold('D')}  site diagnosis: why the maintenance page shows (service, Odoo ports, nginx upstream, firewall) and what to do")
        lines.append(f"    {bold('R')}  record a test: R starts (a label is asked), R again stops; « REC » at the end of each line meanwhile; a .tar.xz archive "
                     f"to send for analysis (logs of the window without the noise, raw nginx / Odoo / fail2ban extracts, network and PostgreSQL samples, addresses and names anonymized)"
                     + (" [" + TR("recording") + "]" if record["r"] is not None else ""))
        lines.append(f"    {bold('N')}  " + TR("step of a test (while recording): N starts a step (a description is asked), N again ends it; the steps (start, end, duration, description) go into steps.txt of the archive"))
        lines.append(f"    {bold('Y')}  latency: what slows the requests since start (disk, processor, memory: % of waiting time, % of disk use, per hour) and whether SSD disks are justified")
        lines.append(f"    {bold('P')}  print the last lines of the buffer (--buffer N) to a file, colors kept (asks the number of lines and the file name)")
        lines.append(f"    {bold('f')}  refresh: the last lines of the buffer are displayed again with the current options (IP, DNS, names, --only...), not counted again")
        lines.append(f"    {bold('C')}  save the settings changed since startup into {system_config_path()} (every option changeable on the fly: ACCENTUATE_GROUP, ANONYMIZE, CHIME, DNS_MAX*, EXCLUDE_IP, HEALTH, HIDE_IP, HIGHLIGHT, LEVEL, MIN, MODULES_*, NOT_FOUND, ONLY, SUSPECT, TIME_REPORT, UNDERLINE, VERBOSE, WATCH)")
        lines.append(f"    {bold('b')}  addresses to ban: {to_ban} — asks, then nginx-log-audit.sh --ban (like web-monitor.py)")
        others_at = lines.index("  Others:") + 1                 # 1.113: the other keys are also in alphabetical order
        lines[others_at:] = sorted(lines[others_at:], key=lambda text_line: (ANSI_RE.sub("", text_line).strip()[:1].lower(), ANSI_RE.sub("", text_line).strip()[:1].isupper()))
        write_out(lines)

    def survey_line(i, margin=0):
        """Right part of a registration to an event that requires a confirmation survey: the survey of the same person (finished = confirmed), or its absence."""
        srv = i.get("sondage")
        if not srv:
            return " " * margin + color_code(ORANGE, "Survey: NONE — registration not confirmed")
        finished = srv["etat"] == "done"
        remaining = f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(srv['quand']))}  {(srv['nom'] or i['nom']):<25} {srv['titre']}  ({srv['etat']})"
        return " " * margin + color_code("1;32" if finished else ORANGE, ("Survey completed: " if finished else "Survey NOT finished: ")) + remaining

    def registrations(kind_name):
        """S (surveys) and I (events) keys: last registrations of each database seen (read-only in PostgreSQL)."""
        odoo_db = people.odoo_db if people is not None else None
        if odoo_db is None:
            write_out(["  Registrations: available only for Odoo (reading PostgreSQL)."])
            return
        databases_seen = sorted(people.databases_seen) or sorted({b for d in people.par_ip.values() for b, _ in d})
        heading, func = ("surveys", "reponses_sondages") if kind_name == "S" else ("events", "inscriptions_avec_sondage")
        lines = [color_code(STYLES["title"], TR("──── Registrations to surveys: last 30 days ────" if kind_name == "S" else "──── Registrations to events: last 30 days ────"))]
        if not databases_seen:
            lines.append("  No Odoo database known yet (no sign-in seen).")
        for database in databases_seen:
            lines.append(TR("  Database {name}:").format(name=database))
            by_ticket = odoo_db.registrations_by_ticket(database, 30, 200) if kind_name == "I" and hasattr(odoo_db, "registrations_by_ticket") else None
            if by_ticket is not None:                   # 1.84: event -> ticket -> ITS survey (module rlq_survey_report); otherwise the old matching by title below
                lines += ticket_report(by_ticket)
                continue
            was_read = getattr(odoo_db, func)(database, 30, 15)
            if was_read is None:
                lines.append("    unreadable (PostgreSQL unreachable, program not run as root, or survey / events module not installed)")
            elif not was_read:
                lines.append("    none")
            left = [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(i['quand']))}  {i['nom']:<25} {i['titre']}{('  — ticket « ' + i['ticket'] + ' »') if i.get('ticket') else ''}  ({i['etat']})"
                      for i in was_read or []]
            width = max([len(g) for g in left] or [0])
            for g, i in zip(left, was_read or []):
                lines.append("    " + g + ("   " + survey_line(i, width - len(g)) if kind_name == "I" and i.get("avec_sondage") else ""))
        write_out(lines)

    def refresh_recommendations():
        """b key: relaunches web-monitor.py --dry-run --save-recommended (no e-mail, no position modified) to get the recommendations of RIGHT NOW, not those of the timer's last run."""
        wm = os.path.join(SCRIPT_DIR, "web-monitor.py")
        if not os.path.isfile(wm):
            return
        write_out(["  Updating the web-monitor.py recommendations (a few seconds)…"])
        app = ["--app", options["app"]] if options.get("app") else []
        try:
            r = run_captured([sys.executable, wm, "--dry-run", "--save-recommended", "--no-pager", "--no-prompt"] + app, "web-monitor.py",
                             timeout=300, env=dict(os.environ, NGINX_TOOLS_LANG="fr"))
            if r.returncode != 0:
                write_out([f"  web-monitor.py failed (code {r.returncode}): recommendations of the last run used."])
        except (OSError, subprocess.TimeoutExpired):
            write_out(["  web-monitor.py did not answer in time: recommendations of the last run used."])
        stats._reco_t = 0.0

    def ban():
        """b key: the addresses with suspicious requests (or recommended by web-monitor.py) not yet banned; a question, then nginx-log-audit.sh --ban for each (reversible: --unban IP)."""
        candidates = stats.to_ban()
        if not candidates:                              # addresses are already to ban (dashboard): no relaunch of web-monitor.py; otherwise a relaunch may find new ones
            refresh_recommendations()
            candidates = stats.to_ban()
        if not candidates:
            write_out(["  Addresses to ban: none (no suspicious request seen here, nor any web-monitor.py recommendation of an address that is not already banned, from the team, a place or a known person)."]
                   + ([f"  Recommendations from web-monitor.py: {stats.reco_diagnostic()}."] if stats.reco_diagnostic() else []))
            return
        write_out([color_code(ORANGE, f"──── {len(candidates)} address(es) to ban ────")]
               + [f"  {color_code(STYLES['suspect'], ' ' + ip + ' ')} " + (f"{stats.who(ip)} " if stats.who(ip) != ip else "") + f"— {stats.ban_reason(ip, n)}" for ip, n in candidates])
        nla = os.path.join(SCRIPT_DIR, "nginx-log-audit.sh")
        if not os.path.isfile(nla):
            write_out(["  nginx-log-audit.sh not found next to this program: banning impossible."])
            return
        rep = ask("Ban now? [y] all  [c] one by one (detailed investigation)  [N] none: ")
        rep = (rep or "").strip().lower()
        if rep not in ("o", "oui", "y", "yes", "c", "choisir", "choose"):
            write_out(["  No address banned."])
            return
        app = ["--app", options["app"]] if options.get("app") else []
        n_ok = 0
        for ip, n_seen in candidates:
            why = ["--reason", f"app-log-live.py: {stats.ban_reason(ip, n_seen)}"]   # 1.87: kept in the ban journal (date, time, justification)
            if rep in ("c", "choisir"):
                with keys.interactive():
                    print(f"\n{'=' * 70}\n{ip}" + (f" — {stats.who(ip)}" if stats.who(ip) != ip else ""))
                    with foreground_child():                # 1.84: Ctrl-C goes to nginx-log-audit.sh, which asks its own confirmation
                        code = subprocess.run(["bash", nla, "--ban", ip] + why + app).returncode
            else:
                r = run_captured(["bash", nla, "--ban", ip, "--yes"] + why + app, "nginx-log-audit.sh", env=dict(os.environ, NGINX_TOOLS_LANG="fr"))
                code = r.returncode
                detail = next((l.strip() for l in r.stdout.splitlines() + r.stderr.splitlines() if re.search(r"Règle|Déjà|REFUSÉ|ÉCHEC", l)), "")
                write_out([f"  {ip} : {('already banned' if 'Déjà' in detail else 'now banned') if code == 0 else color_code(STYLES['error'], 'NOT banned')}{' — ' + detail if detail else ''}"])
            if code == 0:
                stats.all_banned.add(ip)
                n_ok += 1
        write_out([f"  {n_ok}/{len(candidates)} address(es) banned (reversible: nginx-log-audit.sh --unban IP)."])

    def error_report():
        """r key: the error report (like --report-err) according to what has been displayed so far."""
        module = load_module("_rapport")
        if module is None:
            write_out(["  Report unavailable: apps/_rapport.py is missing."])
            return
        text = "".join(output.buffer) if hasattr(output, "buffer") else ""
        command = " ".join([os.path.basename(__file__)] + [a for a in sys.argv[1:] if a != "--report-err"])
        write_out(["", module.construire_rapport(os.path.basename(__file__), __version__, command, text, 0, int(time.time() - session_start), SCRIPT_DIR)])

    def key(key_value):
        """A keyboard key (menu or Ctrl-G / Ctrl-T)."""
        global VERBOSE, NAME_WIDTH, NAME_TRUNCATE
        if key_value in ("g", "t"):
            title = [color_code(STYLES["title"], TR("Real-time dashboard of {app}").format(app=options.get("app_label", "application")))]      # 1.119
            write_out(["", *(title if key_value == "t" else []), *table_rows(delta=key_value == "t")])
            write_out([status_line()])                      # 1.121: the bar is shown first, with the counters of the period just reported
            status.reset()                                  # 1.113: a detailed report starts a new period for the status bar
            write_out(["  " + TR("Status bar: counters reset (new period from now).")])
        elif key_value == "refresh":                        # 1.113: f key - last lines displayed again with the current options
            refresh_lines()
        elif key_value == "print":                          # 1.113: P key - last lines printed to a file, colors kept
            print_lines()
        elif key_value.startswith("level"):
            options["level"] = int(key_value[5:])
            write_out(["", *table_rows(level=options["level"])])
        elif key_value == "help":
            menu()
        elif key_value == "i":
            options["keep_ip"] = not options["keep_ip"]
            form.width = address_width()
            write_out([f"  --hide-ip : {yes_no(not options['keep_ip'])} (the following lines)"])
        elif key_value == "anonymize":                       # 1.91: --anonymize on / off on the fly (screen only: the daily journal always keeps everything)
            if os.environ.get("NGINX_TOOLS_ANON_ACTIF"):
                write_out([color_code(ORANGE, "  --anonymize: the output is already anonymized by the program that launched this one: unchanged.")])
            elif output.anonymize is not None:
                output.anonymize = None
                write_out(["  --anonymize : no — real addresses, e-mails and names (the following lines)"])
            else:
                if output.anonymiser is None:
                    module = load_module("_anonymiser")
                    output.anonymiser = new_anonymiser(module) if module is not None else None
                if output.anonymiser is None:
                    write_out([color_code(STYLES["error"], "  --anonymize: apps/_anonymiser.py is unreadable: real values stay.")])
                else:
                    output.anonymize = output.anonymiser
                    write_out(["  --anonymize : yes — pseudonyms IP-xxxxxx, usager-xxxxxx, membre-xxxxxx (the following lines)"])
            options["anonymize"] = output.anonymize is not None
        elif key_value == "reqlen":                # 1.136: the request length column (key j)
            options["request_length"] = not options["request_length"]
            form.request_length = options["request_length"]
            write_out([f"  --request-length : {yes_no(options['request_length'])} (the following lines)"])
            state["header_shown"] = False                  # 1.139: printed again at the next request line, on its real fields
        elif key_value == "hideua":                # 1.135: the User-Agent text of the nginx lines (key u)
            options["hide_user_agent"] = not options["hide_user_agent"]
            form.hide_user_agent = options["hide_user_agent"]
            write_out([f"  --hide-user-agent : {yes_no(options['hide_user_agent'])} (the following lines)"])
        elif key_value == "addons":
            options["hide_addons"] = not options["hide_addons"]
            hidden = state.get("addons_hidden", 0)
            write_out([f"  --hide-addons : {yes_no(options['hide_addons'])} (the following lines)" + (f"; lines hidden so far: {hidden}" if hidden else "")])
        elif key_value == "m":
            options["minimal"] = form.minimal = not options["minimal"]
            write_out([f"  --min : {yes_no(options['minimal'])} (the following lines)"])
            state["header_shown"] = False                  # 1.139: printed again at the next request line, on its real fields

        elif key_value == "n":
            options["not_found"] = not options["not_found"]
            stats.list_404 = options["not_found"]
            write_out([f"  --not-found : {yes_no(options['not_found'])} (the following lines)"])
        elif key_value == "lognginx":                                  # 1.116: nginx lines shown or hidden, from the next line on
            options["log_nginx"] = not options["log_nginx"]
            write_out([f"  --log-nginx : {yes_no(options['log_nginx'])}" + (" (the following lines)" if options["nginx_merged"] else " (no nginx log is read: nothing changes)")])
        elif key_value == "s":
            options["suspect"] = not options["suspect"]
            write_out([f"  --suspect : {yes_no(options['suspect'])} (the following lines)"])
        elif key_value == "v":
            VERBOSE = not VERBOSE
            write_out([f"  --verbose : {yes_no(VERBOSE)}"])
        elif key_value == "dns":
            n = requested_int(f"--dns-max N (names column, never cut; current {NAME_WIDTH}, Enter = {DNS_MAX_DEFAULT}) : ", DNS_MAX_DEFAULT, 4, 200)
            if n is not None:
                NAME_WIDTH, NAME_TRUNCATE = n, 0
                write_out([f"  --dns-max {n} (the following lines)"])
        elif key_value == "dnst":
            n = requested_int(f"--dns-max-truncate N (names column, cut at N; current {NAME_TRUNCATE or 'no cutting'}, Enter = {DNS_TRUNCATE_DEFAULT}) : ", DNS_TRUNCATE_DEFAULT, 4, 200)
            if n is not None:
                NAME_WIDTH = NAME_TRUNCATE = n
                write_out([f"  --dns-max-truncate {n} (the following lines)"])
        elif key_value == "H":
            n = requested_int(TR("--health MIN (minutes between two alerts, 0 = never; current {current:g}, Enter = {default:g}): ").format(current=options['health'], default=HEALTH_DEFAULT), int(HEALTH_DEFAULT), 0, 1440)
            if n is not None:
                options["health"] = float(n)
                alert["next_one"] = time.time() + n * 60
                write_out([f"  --health {n}" + (" (automatic alerts stopped)" if not n else "")])
        elif key_value == "highlight":
            rep = ask(TR("--highlight WORDS (+word adds, -word removes; or a full list: comma = several, none = nothing; Enter = {default}; current: {current}): ").format(
                default=HIGHLIGHT_DEFAULT, current=', '.join(options['highlight_words']) or 'none'))
            if rep is not None:
                options["highlight_words"] = read_highlight(rep.strip() or None, options["highlight_words"])
                options["highlight_pattern"] = highlight_pattern(options["highlight_words"])
                write_out(["  --highlight : " + (", ".join(color_code(STYLES["highlight"], m) for m in options["highlight_words"]) if options["highlight_words"] else "no word") + " (the following lines)"])
        elif key_value == "o":
            rep = ask(TR("--only TEXT (comma = OR, empty = show everything; current: {current}): ").format(current=', '.join(options['only']) or 'none'))
            if rep is not None:
                options["only"] = [t.strip().lower() for t in rep.split(",") if t.strip()]
                state["keep_going"] = True
                write_out(["  --only : " + (", ".join(options["only"]) if options["only"] else "no filter") + " (the following lines)"])
        elif key_value == "exclude":
            rep = ask(f"--exclude-ip IP,IP… (addresses or networks such as 10.0.0.0/8 separated by commas, empty = none; current: {', '.join(str(r) for r in options['exclude']) or TR('no address')}) : ")
            if rep is not None:
                networks, invalid = read_exclusions(rep)
                if invalid:
                    write_out([color_code(STYLES["error"], f"  Address(es) refused: {', '.join(invalid)} — nothing is changed.")])
                else:
                    options["exclude"] = networks
                    state["keep_going"] = True
                    write_out(["  --exclude-ip : " + (", ".join(str(r) for r in networks) if networks else none_fem()) + " (the following lines)"])
        elif key_value == "accent":
            rep = ask(f"--accentuate-group NAME (Odoo contact tag, empty = none; current: {options['group'] or TR('no tag')}) : ")
            if rep is not None:
                name = rep.strip()
                if not name:
                    options["group"], options["membres"] = None, set()
                    write_out(["  --accentuate-group: none"])
                else:
                    member_list, err, _ = load_group(people.odoo_db if people is not None else None, name, sorted(people.databases_seen) if people is not None else [])
                    if err:
                        write_out([color_code(STYLES["error"], f"  --accentuate-group : {err}")])
                    else:
                        options["group"], options["membres"] = name, member_list
                        write_out([f"  --accentuate-group {name} : {len(member_list)} accounts (the following lines): " + color_code(STYLES["accent"], " exemple ")])
        elif key_value == "chime":
            rep = ask(TR("--chime N (0 = any error, 1 = 4xx, 2 = 5xx and 4xx, n = no beep; current: {current}, Enter = 0): ").format(current=options['chime'] if options['chime'] is not None else 'none'))
            if rep is not None:
                rep = rep.strip().lower()
                if rep in ("n", "non", "off"):
                    options["chime"] = None
                    write_out(["  --chime: no beep"])
                elif rep in ("", "0", "1", "2"):
                    options["chime"] = int(rep or 0)
                    beep["mode"], advices = prepare_beep()
                    sonner(beep["mode"], output.screen)
                    write_out([f"  --chime {options['chime']} (test beep sent)"] + [color_code(ORANGE, "  ⚠ " + c) for c in advices])
                else:
                    write_out([color_code(STYLES["error"], f"  Value refused « {rep} » : 0, 1, 2 or n.")])
        elif key_value == "underline":                       # 1.102: U key - one log line out of N underlined (0 = none), saved by C
            n = requested_int(TR("--underline N (one log line out of N underlined, 0 = none; current: {current}, Enter = {default}): ").format(
                                  current=output.underline, default=UNDERLINE_DEFAULT), UNDERLINE_DEFAULT, 0, 1000)
            if n is not None:
                output.underline = options["underline"] = n
                write_out([f"  --underline {n}" + ("" if n else " (none)")])
        elif key_value == "report":
            n = requested_int(f"--time-report MIN (report like Ctrl-T every MIN minutes, 0 = never; current {options['report_min']:g}, Enter = {REPORT_DEFAULT:g}) : ", int(REPORT_DEFAULT), 0, 1440)
            if n is not None:
                options["report_min"] = float(n)
                periodic["next_report"] = time.time() + n * 60
                write_out([f"  --time-report {n}" + (" (periodic reports stopped)" if not n else "")])
        elif key_value == "V":
            write_out([f"  app-log-live.py version {__version__}"])
        elif key_value == "r":
            error_report()
        elif key_value == "G":
            write_out(["  Reading PostgreSQL…"])
            write_out(rlq_groups_lines())
        elif key_value in ("S", "I"):
            write_out(["  Reading PostgreSQL…"])
            registrations(key_value)
        elif key_value == "b":
            ban()
        elif key_value == "latency":
            lines_p = LATENCY.lines(LEVEL_MAX)
            write_out([color_code(STYLES["title"], "──── Latency: what slows the requests (since start) ────")] + (lines_p or ["  Latency: no sample yet (one every "
                                                                                                                             f"{LATENCY.sample_s:g} s)."]))
        elif key_value == "D":
            write_out(["  Checking the site (a few seconds)…"])
            lines_d = []
            show_diagnostic(options["profile"], options["service"], lines_d.append, True, options["diag_hosts"])
            write_out(lines_d)
        elif key_value == "save":
            changes = config_changes(config_values(options, VERBOSE, (NAME_WIDTH, NAME_TRUNCATE)), config_at_start)
            target = system_config_path()
            if not changes:
                write_out([f"  No setting changed since startup: nothing to save into {target}."])
            else:
                write_out([f"  Settings changed since startup (to write into {target}):"] + [f"    {color_code('1;36', k)}={v}   (before: {config_at_start.get(k)})" for k, v in sorted(changes.items())])
                rep = ask("Save? [o] yes  [p] in my personal file " + f"~/.{SCRIPT_NAME}.conf" + "  [N] no: ")
                choice = (rep or "").strip().lower()
                if choice in ("o", "oui", "y", "yes", "p"):
                    target = os.path.join(os.path.expanduser("~"), f".{SCRIPT_NAME}.conf") if choice == "p" else target
                    try:
                        write_out([f"  {write_config(target, changes)} settings written into {color_code('1;32', target)} (re-read at the next launch)."])
                        config_at_start.update(changes)
                    except OSError as e:
                        write_out([color_code(STYLES["error"], f"  Cannot write into {target} : {e.strerror or e}") + " — run again as root (sudo), or answer « p » for the personal file."])
                else:
                    write_out(["  Nothing is written."])
        elif key_value == "modules":
            current = options["modules_sort"]
            rep = ask("Modules sort: n name · d modification date · c creation · v version · a author · e state; capital letter or leading - = reverse order; "
                           f"p = non-Odoo S.A. only, all = all (current: {current[0]}{' reversed' if current[1] else ''}{', non-Odoo S.A.' if current[2] else ''}, Enter = keep): ")
            if rep is not None:
                new = read_modules_sort(rep, current)
                if new is None:
                    write_out([color_code(STYLES["error"], "  Unknown sort — expected: n, d, c, v, a, e (capital = reverse), p or all.")])
                else:
                    options["modules_sort"] = new
                    databases_seen = sorted(people.databases_seen) or (people.odoo_db.bases_odoo() if people.odoo_db is not None else None) or []
                    write_out(module_lines(people.odoo_db, options["profile"].get("ODOO_CONF"), databases_seen, new))
        elif key_value == "recent":
            databases_seen = sorted(people.databases_seen) or (people.odoo_db.bases_odoo() if people.odoo_db is not None else None) or []
            write_out(module_lines(people.odoo_db, options["profile"].get("ODOO_CONF"), databases_seen, (MODULES_SORT_DEFAULT, False, options["modules_sort"][2]), 10))
        elif key_value == "E":
            error_details(False)
        elif key_value == "record":                          # 1.93: R key - start / stop a test recording
            if record["r"] is None:
                if record["pending"] is not None:
                    write_out(["  " + TR("The previous archive is still being created: wait for its line, then press R again.")])
                    return
                label = ask(TR("Label of this recording (e.g. survey-abandoned; Enter = none, Ctrl-C = cancel): "))
                if label is None:
                    write_out(["  " + TR("Recording not started.")])
                    return
                record_start(label.strip())
            else:
                record_stop("key")
        elif key_value == "step":                            # 1.95: N key - start / end of a step of the test (a description is asked)
            if record["r"] is None:
                write_out(["  " + TR("Start a recording first (R): the steps are kept in it.")])
                return
            if record["r"].open_step is not None:
                number = record["r"].step_end()
                write_out([color_code(STEP_STYLE, f" ■ STEP {number} END ") + " " + TR("ended at {time}").format(time=time.strftime("%H:%M:%S"))])
                show_steps_line()
                return
            description = ask(TR("Description of this step (e.g. registration; Enter = none, Ctrl-C = cancel): "))
            if description is None:
                write_out(["  " + TR("Step not started.")])
                return
            number = record["r"].step_start(description.strip()) if record["r"] is not None else None
            if number is None:
                write_out(["  " + TR("Step not started.")])
                return
            write_out([color_code(STEP_STYLE, f" ▶ STEP {number} START ") + " " + TR("started at {time}").format(time=time.strftime("%H:%M:%S"))
                       + " — " + (description.strip() or TR("(no description)"))])
            show_steps_line()
        elif key_value == "steps_line":                     # 1.99: F key - the steps of the recording on one white line (toggle)
            options["steps_line"] = not options.get("steps_line")
            if not options["steps_line"]:
                write_out([TR("  --steps-line: off")])
            else:
                write_out([TR("  --steps-line: on — the steps are shown on one line at each step (R starts a recording, N a step)")])
                show_steps_line()
        elif key_value == "watch":
            rep = ask(TR("--watch TEXT (comma = several, e.g. registration; empty = stop; current: {current}): ").format(current=', '.join(options['watch']) or 'none'))
            if rep is not None:
                options["watch"] = stats.watch_it = [t.strip().lower() for t in rep.split(",") if t.strip()]
                load_survey_titles()
                write_out(["  --watch : " + (", ".join(options["watch"]) if options["watch"] else "none") + " (duration, errors and slowness in Ctrl-G / Ctrl-T)"])

    session_start = time.time()
    if options["chime"] is not None:
        beep["mode"], advices = prepare_beep()
        for c in advices:
            eprint(color_code(ORANGE, "  ⚠ beep: " + c))
    reader_thread = threading.Thread(target=reader, daemon=True, name="reader")
    reader_thread.start()
    start_watchdog(proc, file, state, received, reader_thread)
    if options["lines"] == 0 and hasattr(output, "active"):      # no history: everything is live
        output.active = True
    if keys is not None and keys.start():
        eprint("Keys: ? (or h) keys and options menu · Ctrl-G dashboard (health, efficiency, top 10 URLs…) · 1 to 9 dashboard detail level · Ctrl-T only what changed since last time · R record a test · N step while recording · Ctrl-C stop and summary")
    merge_ready, merge_held, merge_ended = collections.deque(), collections.deque(), [False]      # 1.123 --log-merge: lines to show now, held nginx lines, end of stream
    old_sigint = None
    if keys is not None and keys.old is not None:
        try:
            old_sigint = signal.signal(signal.SIGINT, interruption)
        except ValueError:                              # not the main thread
            old_sigint = None
    try:
        while True:
            if sig["requested"]:
                sig["requested"] = False
                confirm_exit()
            check_health(time.time())                   # 1.135: the periodic checks also run while the stream is busy (lines discarded by --min
            check_disk(time.time())                     # and the filters never reached them: the health alert came hours late); each one
            check_connections(time.time())              # returns at once when not due
            check_external_ip(time.time())
            skip_merge = bool(merge_ready)              # 1.123: a line released by --log-merge is shown as it is (already merged)
            if not merge_ready and merge_ended[0]:
                break
            try:
                item = merge_ready.popleft() if merge_ready else file.get(timeout=1.0)
            except queue.Empty:                         # idle stream: summary after the history, then inactivities
                merge_ready.extend(merge_release(merge_held, time.time()))      # 1.123: held nginx lines shown alone after MERGE_HOLD seconds
                if merge_ready:
                    continue
                release_deferred(False)
                show_summary()
                startup_status_bar()                    # 1.126: after the history lines
                check_service(time.time())
                check_health(time.time())
                check_disk(time.time())
                check_connections(time.time())
                check_external_ip(time.time())
                periodic_report(time.time())
                check_record(time.time())
                if presence is not None:
                    for kind_name, text in presence.check(time.time()):
                        output.write(presence.event(kind_name, text) + "\n")
                    output.flush()
                continue
            if item is None:                            # end of the stream: the lines still held are shown alone (1.123)
                merge_ended[0] = True
                merge_ready.extend(entry[0] for entry in merge_held)
                merge_held.clear()
                continue
            if item[0] == PROPOSAL:               # often banned address, verdict "ban justified" (computed in the background)
                with interaction():
                    propose_ban(item[1], item[2])
                continue
            if item[0] == KEY_EVENT:                    # Ctrl-G (full dashboard), Ctrl-T (differences since the last time) or a menu key
                with interaction():
                    key(item[1])
                continue
            if item[0] == RECORD_EVENT:                 # 1.93: archive of a recording created (or failed) in the background
                record["pending"] = None
                show_record_result(item[1])
                if record["exit_after"]:                # --record-test-log: the recording was the purpose of this run
                    break
                continue
            if options.get("log_merge") and options.get("log_nginx") and not skip_merge:       # 1.123 --log-merge
                ready_now = merge_step(item, merge_held)
                if not ready_now:                       # held (waiting for the Odoo line) or absorbed into the line before
                    continue
                item = ready_now[0]
                merge_ready.extendleft(reversed(ready_now[1:]))
            L, ips, arrival, is_login = item
            state["consumed"] = True                    # 1.127: at least one line really processed (the reader counts before queuing)
            if options["until"] is not None and L.instant is not None and L.instant >= options["until"]:
                state["until_reached"] = True           # 1.112 --until: the stream is in order, nothing more is displayed after this line
                break
            if L.program_name == "http" and options.get("nginx_merged") and not options.get("log_nginx"):     # 1.116: hidden nginx line: not counted, no lookup
                continue
            if not window_keep(L, state, options):      # 1.112 --since, --grep: decided before any lookup
                continue
            results, pays = {}, {}
            for ip, future, country_future in ips:
                try:
                    results[ip] = future.result(timeout=max(0.0, arrival + WAIT_DELAY - time.time()))
                except Exception:                       # delay exceeded: the address stays, the lookup continues for later
                    results[ip] = ("unknown", ip, None)
                if country_future is not None:
                    try:
                        pays[ip] = country_future.result(timeout=max(0.0, arrival + WAIT_DELAY - time.time()))
                    except Exception:
                        pays[ip] = None
            if not country_keep(L, ips, pays, state, options):   # 1.112 --country, --exclude-country: needs the country of the address
                continue
            state["read_files"] += 1
            stats.count_conflict(L)
            release_deferred("could not serialize access" in L.text)      # the cause of the previous line is this one
            if options["minimal"] and L.discard_in_min():
                continue
            if options["hide_addons"] and L.discard_addons():
                state["addons_hidden"] = state.get("addons_hidden", 0) + 1
                continue
            if is_failed_request(L):                 # written with the next line, which says whether the error is harmless
                deferred[0] = (L, renderings_of(L, results, pays))
                continue
            emit(L, renderings_of(L, results, pays), inputs=(results, pays))
            events = []
            if ips:
                ip = ips[0][0]                          # the client is the first address of the message
                kind_name, text, account = results[ip]
                if kind_name in ("dns", "org", "reseau", "unknown"):  # visitor without a name: kept for the reminder if they log in later
                    instant = L.instant or arrival
                    recent_ones.append((instant, L, ip))
                    while recent_ones and recent_ones[0][0] < instant - max(options["recap"], 1):
                        recent_ones.pop(0)
                if is_login and kind_name == "person":
                    reminder_due = (L, ip, text)
                else:
                    reminder_due = None
                if presence is not None and account is not None:
                    when = L.instant or time.time()
                    hour = L.ts_txt[:19] if L.ts_txt else None      # YYYY-MM-DD HH:MM:SS of the line itself
                    if is_login:
                        events = presence.login(account, text, ip, when, hour)
                    else:
                        events = presence.activity(account, text, ip, when, bool(LOGOUT_RE.search(L.text)), hour)
            else:
                reminder_due = None
            for kind_name, text in events:
                output.write(presence.event(kind_name, text) + "\n")
            if reminder_due is not None:
                reminder(*reminder_due)
            output.flush()
            if state["read_files"] == options["lines"]:        # end of the history: who is logged in?
                show_summary()
            check_health(time.time())
            check_disk(time.time())
            check_connections(time.time())
            check_external_ip(time.time())
            periodic_report(time.time())
            check_record(time.time())
        release_deferred(False)
        finish_recording("end")
        show_summary()
        startup_status_bar()
        check_external_ip(time.time(), wait=True)  # end of the stream (--no-follow): at least one check, we wait for its result
        if options["summary"]:
            output.write("\n".join(table_rows(heading="Session summary")) + "\n")
            if people is not None and people.odoo_db is not None:
                output.write("\n".join(rlq_groups_lines()) + "\n")
            output.flush()
    except KeyboardInterrupt:                           # Ctrl-C confirmed: the session summary, the error detail if requested, then the normal stop (protected_main)
        if old_sigint is not None:
            signal.signal(signal.SIGINT, signal.default_int_handler)  # the rest: one more Ctrl-C interrupts immediately (never a second "Interrupt the program?" question)
        try:
            finish_recording("interrupt")                  # 1.93: a recording in progress is never lost by Ctrl-C
            output.write("\n" + "\n".join(table_rows(heading="Session summary")) + "\n")
            output.flush()
            if people is not None and people.odoo_db is not None:
                output.write("\n".join(rlq_groups_lines()) + "\n")                    # members of the RLQ* groups (v1.79)
                output.flush()
            error_details(True)
        except KeyboardInterrupt:
            with contextlib.suppress(KeyboardInterrupt, OSError):
                write_out(["  Error details interrupted."])
        raise KeyboardInterrupt
    except BrokenPipeError:                             # "| head": silent stop
        pass
    finally:
        if old_sigint is not None:
            signal.signal(signal.SIGINT, old_sigint)
        if tail_agents is not None and tail_agents.poll() is None:
            tail_agents.terminate()
        if keys is not None:
            keys.restore()
        if hasattr(output, "close"):
            output.close()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0 if proc.returncode in (0, -signal.SIGTERM, None) else proc.returncode


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
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)          # "| head": silent stop, like cat
    try:
        text = changelog_section(CHANGELOG_FILE, "app-log-live.py")
    except OSError:
        eprint(f"Changelog not found: {CHANGELOG_FILE}")
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
    """Help options in ALPHABETICAL ORDER (long name, without the dashes)."""
    @staticmethod
    def _key(action):
        names = action.option_strings or [action.dest]
        return names[-1].lstrip("-").lower()

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, sorted(actions, key=self._key), groups, prefix)         # (--dns-max and --dns-max-truncate follow each other: the "one OR the other" group stays displayed)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._key))


class LocalizedArgumentParser(argparse.ArgumentParser):
    """Fallback parser (apps/_i18n.py missing): options in alphabetical order, English messages."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", SortedHelp)
        super().__init__(*args, **kwargs)


MENU_ENTREES = [
    ([], 'Live follow', 'Live follow', False),
    (['--diagnose'], 'Site diagnosis (maintenance page)', 'Site diagnosis (maintenance page)', False),
    (['--modules'], 'Odoo modules table', 'Odoo modules table', False),
    (['--no-follow'], 'Last messages, then stop', 'Last messages, then stop', False),
]


def main():
    global VERBOSE, NAME_WIDTH, NAME_TRUNCATE, COLOR, TIME_UTC
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="Real-time application log: local ISO time without duplicates, each IP address replaced by the name of the person already signed in (otherwise DNS name, otherwise owner of the address block), presence of people, colors.")
    parser.add_argument("--app", metavar="NAME", help="Application behind nginx (profile apps/NAME.conf: odoo, bbb…) — detected automatically by default")
    parser.add_argument("--accentuate-group", default=None, metavar="NAME",
                        help="Odoo contacts with the contact TAG NAME (e.g. Staff-2026) shown in bold white on dark blue; the tag must exist, otherwise stop")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("--cms", choices=["auto", "odoo", "wordpress"], default="auto", metavar="CMS",
                        help="Site CMS: odoo (/wp-admin, xmlrpc.php, *.php… are suspect), wordpress (normal pages) or auto (default: a wp-config.php under /var/www, /srv, /opt…)")
    parser.add_argument("--connections", type=float, default=CONNECTIONS_THRESHOLD_DEFAULT, metavar="PCT",
                        help=f"Every minute, WARNING in the stream when a connection limit (Odoo chat / websocket, HTTP, PostgreSQL, nginx) is used at PCT %% or more, "
                             f"with the setting to change (default: {CONNECTIONS_THRESHOLD_DEFAULT:g}; 0 = never)")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/app-log-live.conf, then the personal file .app-log-live.conf; options in UPPERCASE: APP, CONNECTIONS, DAYS, DNS_MAX, HEALTH, HIDE_IP, IDLE, LANGUAGE, LINES, LOG_DIR, LOG_KEEP_DAYS, LOG_MERGE, LOG_NGINX, MIN, NAMESPACE, NO_BANNED, NO_BAN_PROMPT, NO_CACHE, NO_HISTORY, NO_ISP, NO_KEYS, NO_LOG_FILE, NO_PRESENCE, NO_USER_AGENT, RECAP, SERVICE, SLOW, STATUS_HEADER, VERBOSE)")
    parser.add_argument("--config-merge", action="store_true",
                        help="Rewrite the configuration file from the NEW default configuration (example of the current language), keeping the values set in the file read until now; "
                             "the old file is copied first to FILE.bak-YYYYMMDD-HHMMSS (with -c: that file only). Then exit")
    parser.add_argument("--chime", type=int, nargs="?", const=0, default=None, choices=(0, 1, 2), metavar="N",
                        help="Beep (in byobu/tmux too: see the tips shown) when a displayed line is an error: 0 = any error (4xx, 5xx, Odoo ERROR), 1 = 4xx, 2 = 5xx and 4xx (0 without value)")
    parser.add_argument("--days", type=float, default=DAYS_DEFAULT, metavar="N",
                        help="Days of sign-in history read from the log, fractions allowed: 0.1 = 2.4 hours (default: 0 = the whole history of the log)")
    parser.add_argument("--diagnose", action="store_true",
                        help="Site diagnosis (why the maintenance page shows: service, Odoo ports, nginx upstream, firewall) and the versions of the nginx configuration with their dates, then exits; code 1 if there is a problem")
    parser.add_argument("--diagnose-host", action="append", default=[], metavar="NOM",
                        help="With --diagnose (or the D key): also check the certificate seen by the Internet for this name (repeatable), even if it is served by ANOTHER server")
    parser.add_argument("--disk-min", type=float, default=DISK_MIN_DEFAULT, metavar="GB",
                        help=f"WARNING in the stream when the free space of the logs' partition (Odoo, nginx, systemd journal) falls below GB gigabytes (default: {DISK_MIN_DEFAULT:g} ; 0 = never)")
    dns_column = parser.add_mutually_exclusive_group()
    dns_column.add_argument("--dns-max", type=int, nargs="?", const=DNS_MAX_DEFAULT, default=None, metavar="N",
                             help=f"Names column (DNS, person, place…) of N characters, never truncating a longer name (default: {NAME_WIDTH} ; "
                                  f"{DNS_MAX_DEFAULT} without a value; by default names are cut at {NAME_WIDTH}: this option removes the cut)")
    dns_column.add_argument("--dns-max-truncate", type=int, nargs="?", const=DNS_TRUNCATE_DEFAULT, default=None, metavar="N",
                             help=f"Names column of N characters, longer names are CUT at N (the last character becomes « … ») ({DNS_TRUNCATE_DEFAULT} without value)")
    parser.add_argument("--exclude-ip", action="append", default=None, metavar="IP,IP",
                        help="Do not show the lines of these addresses or networks (IP1,IP2,10.0.0.0/8); repeatable")
    parser.add_argument("--health", type=float, default=HEALTH_DEFAULT, metavar="MIN",
                        help=f"Every MIN minutes, IF something is wrong (5xx or Odoo errors, failed e-mails, slow requests, greedy program), show the health and "
                             f"details in the stream (default: {HEALTH_DEFAULT:g}; 0 = never)")
    parser.add_argument("--hide-addons", action="store_true",
                        help="Hide the INFO lines of the Odoo modules (odoo.addons.*), except errors (WARNING, ERROR, traces), e-mails sent and generated files (PDF reports…); q key on the fly")
    parser.add_argument("--hide-ip", dest="hide_ip", action="store_true", help="Do not show the IP address in brackets after the name (default)")
    parser.add_argument("--highlight", default=None, metavar="WORDS",
                        help=f"Words highlighted in cyan in the displayed lines (comma = several; an ALL-CAPS word, like POST, must be in caps in the line; others are case-insensitive); "
                             f"'none': no word; '+word' adds a word to the default list, '-word' removes it (--highlight=+odoo,-POST). Default: {HIGHLIGHT_DEFAULT}. HIGHLIGHT key of the configuration file; key l of the menu")
    parser.add_argument("--idle", type=float, default=IDLE_DEFAULT, metavar="MIN",
                        help=f"Minutes without activity before « no more activity » (default: {IDLE_DEFAULT:g})")
    parser.add_argument("--keep-ip", dest="hide_ip", action="store_false", help=argparse.SUPPRESS)       # old name of --show-ip (1.111: it had no effect since 1.107)
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--level", type=int, default=LEVEL_MAX, metavar="N",
                        help=f"Detail level of the dashboard and summary: 1 = one-line verdict … 5 = the essentials … {LEVEL_MAX} = everything (default: {LEVEL_MAX}; keys 1 to 9 on the fly)")
    parser.add_argument("-n", "--lines", type=int, default=LINES_DEFAULT, metavar="N",
                        help=f"History messages shown before the live stream (default: {LINES_DEFAULT})")
    parser.add_argument("--log-dir", default=None, metavar="DIR",
                        help="Folder of the daily log with colors (default: /var/log/app-log-live for root, otherwise ~/.local/state/app-log-live; APP_LOG_LIVE_LOG_DIR, « off »: none)")
    parser.add_argument("--log-keep-days", type=int, default=None, metavar="N",
                        help=f"Daily logs kept N days, the oldest are deleted (default: LOG_KEEP_DAYS from /etc/default/app-default.conf, otherwise {JOURNAL_DAYS_DEFAULT} ; 0 = never)")
    parser.add_argument("--log-nginx", action="store_true",
                        help="Also the nginx logs of the site (access and error) in the same stream, in time order, with the same date and time prefix as the application (LOG_NGINX in the configuration file)")
    parser.add_argument("--menu", action="store_true", help="interactive menu of the common operations (dialog if installed; terminal required)")
    parser.add_argument("--min", action="store_true", help="The minimum of information: without database name or « werkzeug », without the fetchmail lines (except errors); default since 1.98 (MIN key; --no-min: everything)")
    parser.add_argument("--modules", action="store_true",
                        help="Table of installed Odoo modules (name, version, state, modification and creation dates, author), then exit; sort: --modules-sort; menu key M")
    parser.add_argument("--modules-custom", action="store_true", help="With --modules (or the M key): only modules that are not by Odoo S.A.")
    parser.add_argument("--modules-latest", type=int, nargs="?", const=10, default=None, metavar="N",
                        help="The N latest installed modules (default: 10), with the current Odoo version, sorted by modification date, then exits; menu key L")
    parser.add_argument("--modules-startup", action="store_true",
                        help="At startup, first shows the tracking of custom (non-standard) modules (the rlq* with their version, then the others not by Odoo S.A.), sorted according to --modules-sort; L key to see them later")
    parser.add_argument("--modules-sort", default=MODULES_SORT_DEFAULT, metavar="KEY",
                        help="Module table sort: name, date (modification, newest first), created, version, author or state; leading '-': reverse order "
                             f"(default: {MODULES_SORT_DEFAULT}). MODULES_SORT key of the configuration file")
    parser.add_argument("--namespace", default=None, help="Journal namespace (default: that of the service, detected)")
    parser.add_argument("--no-cache", action="store_true", help="Neither read nor write the permanent address cache (DNS name, block owner, country: apps/_cache_ip.py)")
    parser.add_argument("--watch", nargs="?", const="registration", default=None, metavar="TEXT",
                        help="Watches the requests whose URL contains TEXT (comma = several; no value: registration, the event registrations): count, errors, median / 95th percentile / maximum duration, slow requests (--slow) and confirmed registrations, in Ctrl-G, Ctrl-T and the health state; most viewed pages with their visitors and robots, and for /survey/ addresses each survey (title read from PostgreSQL, ticket included) with its accesses and submissions (e.g. --watch journee-portes-ouvertes,/survey/). Does NOT filter the display: to see only those lines, add --only with the same text")
    parser.add_argument("--no-ban-prompt", action="store_true", help="Do not offer to ban an address often banned (verdict « ban justified » of nginx-log-audit.sh --evidence)")
    parser.add_argument("--no-banned", action="store_true", help="No [banned: …] label (reads neither fail2ban nor the CrowdSec ipsets)")
    parser.add_argument("--only", action="append", default=None, metavar="TEXT",
                        help="Only the lines that contain TEXT (name, address, URL, module…, case-insensitive); repeatable: one OR the other")
    parser.add_argument("--show-ip", dest="hide_ip", action="store_false",
                        help="Show the IP address in brackets after the name (default: hidden; HIDE_IP=no in the configuration file)")
    parser.add_argument("--slow", type=float, default=5.0, metavar="SECONDS",
                        help="Odoo requests slower than SECONDS (SQL + Python): durations in orange, in red at 3 times the threshold, with the total (default 5; 0: disabled)")
    parser.add_argument("--steps-line", action="store_true", help="The steps of a test recording (N key) on ONE white reverse-video line, updated at each step (screen only); F key of the menu; STEPS_LINE of the configuration file")
    parser.add_argument("--summary", action="store_true", help="Also show the session summary at the end of a --no-follow (with Ctrl-C, always shown)")
    parser.add_argument("--not-found", action="store_true", help="Only the requests answered with 404 (page not found); the summary lists ALL these pages with their count")
    parser.add_argument("--suspect", action="store_true", help="Only the suspicious requests (WordPress, .php, .env, .git, backups, directory traversal…)")
    parser.add_argument("--no-follow", action="store_true", help="Show the last messages then stop (no live stream)")
    parser.add_argument("--no-history", action="store_true", help="Do not read the sign-in history (people names learned only live)")
    parser.add_argument("--no-keys", action="store_true", help="Do not listen to the keyboard (? or h: keys menu, Ctrl-G: dashboard, Ctrl-T: changes since last time)")
    parser.add_argument("--no-log-file", action="store_true", help="No daily log (the live stream is written nowhere, except on screen)")
    parser.add_argument("--no-html-journal", action="store_true", help="No HTML copy of the daily journal (app-log-live-DATE.html, lines cut to 140 characters)")
    parser.add_argument("--no-isp", action="store_true", help="No outside request: no lookup of the address block owner or country (rdap.org, whois)")
    parser.add_argument("--hide-user-agent", action="store_true", help="Do not show the User-Agent text of the nginx lines (the OS column stays)")     # 1.134
    parser.add_argument("--request-length", action="store_true", help="Show the request length of the nginx lines (rl=) in its own column before the GET (default: not shown)")     # 1.136
    parser.add_argument("--no-user-agent", action="store_true", help="Do not read the User-Agent in the nginx access log (robots are then recognized only by name or robots.txt)")
    parser.add_argument("--no-presence", action="store_true", help="No presence tracking (sign-ins, sign-outs, inactivity)")
    parser.add_argument("--record-max", type=float, default=RECORD_MAX_DEFAULT, metavar="MIN",
                        help=f"A test recording (R key) stops by itself after MIN minutes (default: {RECORD_MAX_DEFAULT:g}; 0 refused, 60 at most); RECORD_MAX key")
    parser.add_argument("--record-test-log", type=float, default=None, metavar="MIN",
                        help="Records a test without the keyboard: starts with the live stream, stops after MIN minutes, writes the .tar.xz archive to send for analysis, "
                             "then exits (same content as the R key; folder: ~USER/app-log-live-records under sudo, otherwise LOG_DIR/records)")
    parser.add_argument("--rate-limit", default=None, metavar="IP",
                        help="Detail of the 429 refusals (nginx rate limiting) of ONE address from the nginx logs: URL, limit_req zone, peaks, effects, what to change; then exits")
    parser.add_argument("--recap", type=float, default=RECAP_DEFAUT, metavar="SEC",
                        help=f"When someone signs in, show again WITH their NAME their lines of the last SEC seconds, shown above "
                             f"without name (default: {RECAP_DEFAUT:g}; 0 = never)")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--service", default=None, help="Systemd unit to follow (default: detected)")
    parser.add_argument("--time-report", type=float, nargs="?", const=REPORT_DEFAULT, default=None, metavar="MIN",
                        help=f"Every MIN minutes, the same report as Ctrl-T (what changed since the last display) ({REPORT_DEFAULT:g} without value)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each external command run")
    parser.add_argument("--truncate", type=int, nargs="?", const=0, default=TRUNCATE_AUTO, metavar="N",
                        help="By default on a terminal: a log line wider than N columns (without N: $COLUMNS - 10) is shortened to « start … last two words » (long URLs); menus and reports are never cut; the daily log keeps the whole lines. TRUNCATE key; --no-truncate: whole lines")
    parser.add_argument("--no-min", dest="min", action="store_false", help="Show everything: database name, « werkzeug », fetchmail lines (cancels --min; MIN=no)")
    parser.add_argument("--no-truncate", dest="truncate", action="store_const", const=None, help="Whole log lines on screen, even very long ones (cancels --truncate)")
    if "--anonymize" not in parser._option_string_actions:       # added by apps/_i18n.py; fallback parser: added here
        parser.add_argument("--anonymize", action="store_true")
    parser._option_string_actions["--anonymize"].help = TR("By default on a terminal: IP addresses, e-mails, identifiers and tokens shown on screen replaced by stable pseudonyms (IP-4f2a9c, usager-9c1e03@anonyme.invalid; "
                                                          "names of people: membre-4f2a9c, team labels: equipe-4f2a9c); the daily log keeps everything. A key: on / off on the fly; ANONYMIZE key; --no-anonymize: real values")
    parser.add_argument("--no-anonymize", dest="anonymize", action="store_false", help="Show the real IP addresses, e-mails and names (cancels --anonymize)")
    parser.add_argument("--no-underline", dest="underline", action="store_const", const=0, help="No underlined line (same as --underline 0)")
    parser.add_argument("--underline", type=int, nargs="?", const=UNDERLINE_DEFAULT, default=UNDERLINE_DEFAULT, metavar="N",
                        help="One log line out of N underlined on screen, up to 80 percent of the screen width (without N: 10; default: 10; 0 = none); U key of the menu; UNDERLINE of the configuration file")      # 10 = UNDERLINE_DEFAULT
    parser.set_defaults(underline=UNDERLINE_DEFAULT)            # 1.91: --no-underline is declared first (its None would otherwise win)
    parser.set_defaults(min=MIN_DEFAULT)                       # 1.98: --min by default (MIN=no or --no-min: everything)
    parser.set_defaults(hide_ip=True)                           # 1.107: the IP address is hidden by default (HIDE_IP=no in the configuration file, or --show-ip)
    parser.set_defaults(anonymize=None)                         # None: on a terminal only (a pipe, another program, a test: real values)
    parser.add_argument("--buffer", type=int, default=BUFFER_DEFAULT, metavar="N",
                        help="Last displayed lines kept in memory for the f key (displayed again with the current options) and the P key (printed to a file): 0 = none (default: 200)")
    parser.add_argument("--status-every", type=int, default=STATUS_EVERY_DEFAULT, metavar="N",
                        help="Status bar in reverse video after every N displayed lines: SQL injection attempts, 4xx, 5xx, banned addresses, slow requests since the last detailed report (Ctrl-T or g); 0 = never; default: automatic, two thirds of the terminal height")
    parser.add_argument("--country", action="append", default=None, metavar="CC,CC",
                        help="Show only the lines whose first address is in these countries (two-letter codes such as CA,FR; repeatable). Lines without address are hidden")
    parser.add_argument("--exclude-country", action="append", default=None, metavar="CC,CC",
                        help="Hide the lines whose first address is in these countries (two-letter codes such as US,CN; repeatable). Addresses of unknown country are kept")
    parser.add_argument("-f", "--follow", action="store_true", dest="journalctl_follow",
                        help="Accepted for journalctl compatibility: the live stream is the default (use --no-follow to stop after the history)")
    parser.add_argument("-g", "--grep", metavar="REGEX",
                        help="Show only the lines whose message matches this regular expression. Case-insensitive unless REGEX has an uppercase letter (as journalctl)")
    parser.add_argument("--no-hostname", action="store_true",
                        help="Do not show the host name of the journal lines (as journalctl --no-hostname)")
    parser.add_argument("--log-merge", action="store_true",
                        help="Show the nginx line and the Odoo line of the SAME request (same URL and status, within 2 seconds) as ONE line: "
                             "the nginx part, then the SQL queries and the times of Odoo. Needs --log-nginx; an nginx line waiting for its Odoo line is shown alone after 3 seconds")
    parser.add_argument("--status-header", action="store_true",
                        help="The date and the host name are not shown at the start of each line: the time stays on each line, and the date and the host name are shown in the status bar instead (date and host of the last line)")
    parser.add_argument("--no-pager", action="store_true", dest="journalctl_no_pager",
                        help="Accepted for journalctl compatibility: the output is never paged")
    parser.add_argument("-S", "--since", metavar="TIME",
                        help="Show the lines from TIME: YYYY-MM-DD [HH:MM[:SS]] [Z or +HH:MM], HH:MM[:SS] (today), today, yesterday, @EPOCH, now, or relative (-2h, '-30 min', '0.5 day', '3 days ago'). Local time, or UTC with --utc")
    parser.add_argument("-U", "--until", metavar="TIME",
                        help="Show only the lines BEFORE TIME (same formats as --since); a date alone includes the whole day. With the live stream, the program stops at that time")
    parser.add_argument("--utc", action="store_true",
                        help="Times in UTC: the time of each line, and the times given to --since / --until without a time zone (default: local time)")
    parser.add_argument("--version", action="version", version=f"app-log-live.py version {__version__}")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version displays it itself)
        eprint(f"app-log-live.py v{__version__}")
    defaults, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    if args.menu:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_menu", os.path.join(SCRIPT_DIR, "apps", "_menu.py"))
        _menu = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_menu)
        _menu.menu(os.path.abspath(__file__), sys.argv[1:], MENU_ENTREES,
                   traduire=I18N.tr if I18N else None, langue=I18N.langue if I18N else "fr",
                   configuration=_menu.configuration_de(SCRIPT_DIR, "app-log-live", sys.argv[1:]),
                   nom=f"app-log-live.py v{__version__}")
    _cfg_root = load_module("_config")
    _notice = _cfg_root and _cfg_root.avis_non_root("app-log-live.py", "PostgreSQL databases (modules, registrations), fail2ban, firewall, nginx -T and some logs unreadable; the b key cannot ban")
    if _notice:
        eprint(_notice)
    if args.log_keep_days is None:                                       # neither option nor LOG_KEEP_DAYS of the program: that of the shared file, otherwise 180
        _cfg = load_module("_config")
        args.log_keep_days = _cfg.jours_journaux(JOURNAL_DAYS_DEFAULT) if _cfg else JOURNAL_DAYS_DEFAULT
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defaults, problems, sortie=eprint)
    VERBOSE = args.verbose
    # 1.112: time window (--since, --until, --utc), --grep, --country, --exclude-country: checked here, applied in the stream loop
    TIME_UTC = args.utc
    try:
        args.since_epoch = parse_time(args.since) if args.since is not None else None
        args.until_epoch = parse_time(args.until, end=True) if args.until is not None else None
    except (ValueError, OverflowError, OSError) as error:
        parser.error(f"--since / --until: {error} (see --help for the formats)")
    if args.buffer < 0 or args.status_every < -1:
        parser.error("--buffer and --status-every must be zero or positive")
    if args.days and args.since is not None:
        parser.error("--days and --since cannot be combined")
    if args.since_epoch is not None and args.until_epoch is not None and args.until_epoch <= args.since_epoch:
        parser.error("--until must be later than --since")
    args.grep_sensitive = any(ch.isupper() for ch in (args.grep or ""))            # journalctl's smart case: uppercase letter = case-sensitive
    try:
        grep_re = re.compile(args.grep, 0 if args.grep_sensitive else re.IGNORECASE) if args.grep else None
    except re.error as error:
        parser.error(f"--grep: invalid regular expression: {error}")
    countries = {c.upper() for value in (args.country or []) for c in re.split(r"[,\s]+", value) if c}
    unwanted_countries = {c.upper() for value in (args.exclude_country or []) for c in re.split(r"[,\s]+", value) if c}
    invalid_countries = sorted(c for c in countries | unwanted_countries if not re.fullmatch(r"[A-Z]{2}", c))
    if invalid_countries:
        parser.error(f"--country / --exclude-country: invalid country codes: {', '.join(invalid_countries)}")
    if args.changelog:
        return show_changelog()
    if args.config_merge:
        return config_merge(args.config)
    profile_module = load_module("_profile")
    regler_cms(profile_module.cms(None if args.cms == "auto" else args.cms) if profile_module is not None else (args.cms if args.cms != "auto" else "odoo"))
    if args.lines < 0 or not 0 <= args.days <= 36500 or args.idle <= 0 or args.recap < 0 or args.health < 0 or args.log_keep_days < 0:
        parser.error("--lines must be positive, --days between 0 (all) and 36500, --idle greater than 0, --recap, --health and --log-keep-days positive or zero")
    if not 1 <= args.level <= LEVEL_MAX:
        parser.error(f"--level must be between 1 and {LEVEL_MAX}")
    if args.time_report is not None and not 0 <= args.time_report <= 1440:
        parser.error("--time-report must be between 0 and 1440 minutes")
    if not 0 < (args.record_max or 0) <= RECORD_MAX_LIMIT or (args.record_test_log is not None and not 0 < args.record_test_log <= 1440):
        parser.error("--record-max must be greater than 0 and at most 60 minutes, --record-test-log greater than 0 and at most 1440")
    if args.record_test_log is not None and args.no_follow:
        parser.error("--record-test-log needs the live stream (not with --no-follow)")
    exclusions, invalid = read_exclusions(",".join(args.exclude_ip or []))
    if invalid:
        parser.error(f"--exclude-ip: invalid address(es) or networks: {', '.join(invalid)}")
    for option, value in (("--dns-max", args.dns_max), ("--dns-max-truncate", args.dns_max_truncate)):
        if value is not None and not 4 <= value <= 200:
            parser.error(f"{option} must be between 4 and 200")
    if args.dns_max is not None:
        NAME_WIDTH, NAME_TRUNCATE = args.dns_max, 0                  # width given without cut: never truncated
    if args.dns_max_truncate is not None:
        NAME_WIDTH = NAME_TRUNCATE = args.dns_max_truncate
    try:
        profile = load_profile(args.app)
    except Exception as e:                                  # ProfileError (message in French)
        eprint(f"ERROR: {e}")
        return 2
    if profile.get("APP_NAME") == "bbb":
        regler_cms(CMS, True)                               # BigBlueButton: any CMS is suspicious
    service, ns = args.service, args.namespace or ""
    modules_sort_state = read_modules_sort(args.modules_sort, (MODULES_SORT_DEFAULT, False, args.modules_custom))
    if modules_sort_state is None:
        parser.error(f"--modules-sort: '{args.modules_sort}' unknown (name, date, created, version, author, state; leading '-': reverse order)")
    if args.modules or args.modules_latest is not None:
        if args.modules_latest is not None and args.modules_latest < 1:
            parser.error("--modules-latest expects a positive number of modules")
        odoo_db = load_module("_odoo_db") if profile.get("APP_LOG_KIND") != "file" else None
        databases_seen = (odoo_db.bases_odoo() if odoo_db is not None else None) or []
        for text_line in module_lines(odoo_db, profile.get("ODOO_CONF"), databases_seen, modules_sort_state if args.modules else (MODULES_SORT_DEFAULT, False, args.modules_custom), None if args.modules else args.modules_latest):
            print(text_line)
        return 0
    if args.rate_limit:
        limits_module = load_module("_limites")
        try:
            ipaddress.ip_address(args.rate_limit)
        except ValueError:
            parser.error(f"--rate-limit: invalid IP address: {args.rate_limit}")
        if limits_module is None:
            eprint("ERROR: apps/_limites.py is missing.")
            return 2
        for text_line in limits_module.lignes(limits_module.analyser(args.rate_limit)):
            print(text_line)
        return 0
    if args.diagnose:
        return show_diagnostic(profile, service or (detect_service(profile)[0] if profile.get("APP_LOG_KIND") != "file" else None), print, sys.stdout.isatty(), args.diagnose_host)
    odoo_file = odoo_journal_file(profile)
    if profile.get("APP_LOG_KIND") != "file" and service is None:
        service, ns_detecte = detect_service(profile)
        ns = args.namespace or ns_detecte
        if service is None and not odoo_file:
            eprint("ERROR: no application unit found by systemctl — specify --service NAME.")
            return 2
    elif service and args.namespace is None:
        ns = lancer(["systemctl", "show", "-p", "LogNamespace", "--value", service], 10)[1].strip()
    cmd = stream_command(args, profile, service, ns)
    if cmd is None:
        eprint("ERROR: no log to follow (application log files missing).")
        return 2
    is_odoo = profile.get("APP_LOG_KIND") != "file"
    people = People(load_module("_odoo_db") if is_odoo else None)
    eprint(color_code(STYLES["title"], TR("Real-time dashboard of {app}").format(app=profile.get("APP_LABEL", "application"))))      # 1.119: title of the program
    if LOGS_MERGE in cmd:                                       # 1.116: the nginx logs read are named (shown with --log-nginx or key x)
        state_text = TR("+ nginx logs, merged in time order") if args.log_nginx else TR("nginx logs read, hidden (key x shows them)")
        eprint(color_code("1;36", state_text) + ": " + ", ".join(os.path.basename(f) for f in nginx_log_files(profile)))
    eprint(color_code("1;36", profile.get('APP_LABEL', 'application')) + " — "
           + ((f"log: file {odoo_file} (logfile from the Odoo configuration)" if odoo_file
               else f"service {service}" + (f" (namespace {ns})" if ns else "")) if is_odoo
              else "logs: " + " ".join(os.path.basename(c) for c in cmd if os.path.isfile(c))))
    if is_odoo and args.modules_startup:                   # on request (--modules-startup) and FIRST: the rlq* modules (with their version), then the other custom modules
        for text_line in customs_tracking_lines(people.odoo_db, profile.get("ODOO_CONF"), [], modules_sort_state):
            eprint(text_line)
    if is_odoo and not args.no_history:
        extent = (f"from {args.since}" if args.since is not None else f"{args.days:g} days" if args.days else "the whole log")       # 1.112: --since, fractions of --days
        if args.until is not None:
            extent += f" until {args.until}"
        eprint(color_code("90", f"Sign-in history ({extent}) : reading the log"
                    + (" (may take several minutes; --days N to limit)" if not (args.days or args.since is not None) else " (up to 3 minutes)") + "…"))
        start = time.time()
        n = read_history(people, service, ns, args.days, odoo_file, args.since_epoch, args.until_epoch)
        eprint("  " + color_code("1;36", str(n)) + color_code("90", f" address(es) known from a sign-in to the site (in {time.time() - start:.0f} s)."))
        people.preload()                              # names of the people read BEFORE the live stream
    if is_odoo and profile.get("ODOO_CONF") and people.odoo_db is not None:
        modules_databases = sorted(people.databases_seen) or sorted({b for d in people.par_ip.values() for b, _ in d}) or (people.odoo_db.bases_odoo() or [])
        for text_line in check_modules(people.odoo_db, profile.get("ODOO_CONF"), modules_databases):
            eprint(text_line)
    group_members = set()
    if args.accentuate_group:
        group_members, err, fatal = load_group(people.odoo_db, args.accentuate_group, sorted(people.databases_seen))
        if err:
            eprint(TR("ERROR: --accentuate-group: {err}" if fatal else "WARNING: --accentuate-group: {err}").format(err=err))
            if fatal:
                return 2
            group_members = set()
        else:
            eprint(f"Group « {args.accentuate_group} » : {len(group_members)} accounts shown in " + color_code(STYLES["accent"], " bold white on dark blue "))
    resolver = Resolver(people, read_lists(), server_addresses(), not args.no_isp, load_module("_reseau"),
                          None if args.no_cache else open_cache())
    eprint("Replacing IP addresses: " + ", ".join([color_code(STYLES["person"], "person or team"),
                                                         color_code(STYLES["dns"], "server or DNS name"),
                                                         color_code(STYLES["org"], "owner of the address block (org / network)")])
           + (" — no outside request (--no-isp)" if args.no_isp else
              " — addresses without a known name are sent to rdap.org to find their provider (--no-isp: never)"))
    if COLOR:
        eprint("Reverse video: " + ", ".join([color_code(STYLES["suspect"], "URL suspect"), color_code(STYLES["url_critical"], "5xx error URL"),
                                               color_code(STYLES["url_warning"], "4xx error URL"), color_code(STYLES["blanche"], "allow-list address"),
                                               color_code(STYLES["place_ip"], "address of a place")]) + " · " + color_code(STYLES["banned"], "[banned: …]") + " · "
               + color_code(STYLES["slow_request"], "slow duration"))
    eprint("Figures after the HTTP code — Odoo: « 200 - 105 0.046 0.426 » = response size in bytes (« - »: unknown) · number of SQL queries · SQL time s · Python time s; websocket: « 101 494 14.602 » = size · connection duration (s, long by nature)")
    if args.slow > 0:
        eprint("  Colors: " + ", ".join([color_code(STYLES["slow_request"], f"time ≥ {args.slow:g} s"), color_code(STYLES["slow_request"], f"SQL queries ≥ {SQL_HIGH}"),
                                            color_code(STYLES["slow_request"], f"size ≥ {SIZE_HIGH // 1_000_000} MB")]) + " in orange; "
               + ", ".join([color_code(STYLES["very_slow_request"], f"time ≥ {3 * args.slow:g} s"), color_code(STYLES["very_slow_request"], f"SQL ≥ {SQL_VERY_HIGH}"),
                            color_code(STYLES["very_slow_request"], f"size ≥ {SIZE_VERY_HIGH // 1_000_000} MB")]) + " in red (--slow SECONDS changes the time threshold; 0: no color)")
    if not args.no_isp and not shutil.which("geoiplookup"):
        eprint("RECOMMENDED: geoip-bin missing — the country of each address is looked up on the Internet (rdap.org), slowly. nginx-hardening.sh --update installs it (apt-get install geoip-bin geoip-database).")
    if exclusions:
        eprint(f"Excluded addresses (--exclude-ip): {', '.join(str(r) for r in exclusions)}")
    def shown_time(epoch):                                                   # the time as it is displayed: local, or UTC with --utc
        return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc if TIME_UTC else None).strftime("%Y-%m-%d %H:%M:%S") + (" UTC" if TIME_UTC else "")
    time_filters = [f"{TR('from')} {shown_time(args.since_epoch)}"] if args.since_epoch is not None else []
    if args.until_epoch is not None:
        time_filters.append(f"{TR('before')} {shown_time(args.until_epoch)}")
    filters_shown = time_filters + ([f"grep {args.grep}"] if args.grep else []) + ([f"{TR('country')} {','.join(sorted(countries))}"] if countries else []) \
        + ([f"{TR('not country')} {','.join(sorted(unwanted_countries))}"] if unwanted_countries else [])
    if filters_shown:
        eprint(TR("Filters (--since, --until, --grep, --country, --exclude-country): {filters}").format(filters="; ".join(filters_shown)))
    if args.time_report:
        eprint(f"Periodic report (--time-report): every {args.time_report:g} minutes, like Ctrl-T")
    if not args.no_follow:
        eprint("Live: Ctrl-C to stop.")
    banned_ips = None
    if not args.no_banned:
        banned_ips = Bans()
        banned_ips.start()
        eprint(banned_ips.summary())
    options = {"keep_ip": not args.hide_ip, "minimal": args.min, "hide_addons": args.hide_addons, "lines": args.lines, "recap": args.recap,
               "slow": max(0.0, args.slow), "only": [t.lower() for t in (args.only or []) if t], "highlight_words": read_highlight(args.highlight), "highlight_pattern": highlight_pattern(read_highlight(args.highlight)), "suspect": args.suspect, "disk_min": max(0.0, args.disk_min), "connections": max(0.0, min(100.0, args.connections)), "external_ip": not args.no_isp, "odoo_journal": profile.get("ODOO_LOGFILE"), "profile": profile, "service": service, "diag_hosts": args.diagnose_host, "not_found": args.not_found, "steps_line": args.steps_line, "summary": args.summary, "banned_ips": banned_ips,
               "presence": Presence(args.idle) if is_odoo and not args.no_presence else None, "health": args.health, "keys": not args.no_keys and not args.no_follow, "app": profile.get("APP_NAME"), "app_label": profile.get("APP_LABEL", "application"), "hide_user_agent": args.hide_user_agent, "request_length": args.request_length, "log_nginx": bool(args.log_nginx), "log_merge": bool(args.log_merge), "status_header": bool(args.status_header), "nginx_merged": LOGS_MERGE in cmd, "propose_ban": not args.no_ban_prompt, "watch": [t.strip().lower() for t in (args.watch or "").split(",") if t.strip()], "agents": not args.no_user_agent and not args.no_follow, "acces_logs": profile.get("ACCESS_LOGS"),
               "exclude": exclusions, "chime": args.chime, "group": args.accentuate_group if group_members else None, "membres": group_members,
               "report_min": args.time_report or 0.0, "level": args.level, "modules_sort": modules_sort_state}
    options.update({"buffer": args.buffer, "status_every": args.status_every,                          # 1.113: buffer of the f and P keys, status bar
                    "since": args.since_epoch, "until": args.until_epoch, "grep": grep_re,            # 1.112 filters of the stream loop
                    "countries": countries or None, "exclude_countries": unwanted_countries or None})
    # 1.93: test recording (R key, --record-test-log): log files read over the window, Odoo ports sampled, folder of the archives
    record_logs = []
    for key_name in ("ACCESS_LOGS", "ERROR_LOGS", "CATCHALL_LOG"):
        for pattern in (profile.get(key_name) or "").split():
            record_logs += sorted(glob.glob(os.path.join(NGINX_DIR, pattern)))
    record_logs += [os.path.join(NGINX_DIR, "blocked-probes.log"), os.environ.get("APP_LOG_LIVE_FAIL2BAN_LOG", "/var/log/fail2ban.log"), profile.get("ODOO_LOGFILE") or ""]
    for pattern in (profile.get("APP_LOG_FILES") or "").split():
        record_logs += sorted(glob.glob(pattern))
    record_ports = {}
    odoo_conf_module = load_module("_odoo_conf") if profile.get("ODOO_CONF") else None
    if odoo_conf_module is not None and hasattr(odoo_conf_module, "lire"):
        try:
            conf_values = odoo_conf_module.lire(profile["ODOO_CONF"])
            record_ports = {"http_port": conf_values.get("http_port"), "gevent_port": conf_values.get("gevent_port")}
        except Exception:                               # noqa: BLE001 - unreadable configuration: the default Odoo ports are not guessed, only 80 / 443
            record_ports = {}
    filters = [f"--only {', '.join(options['only'])}"] if options["only"] else []
    filters += [name for name, active in (("--suspect", args.suspect), ("--not-found", args.not_found), ("--min", args.min), ("--hide-addons", args.hide_addons)) if active]
    options.update(record_max=args.record_max or 0.0, record_test_log=args.record_test_log, namespace=ns, record_ports=record_ports, filters_text=" ".join(filters),
                   record_logs=[f for f in OrderedDict.fromkeys(record_logs) if f and os.path.isfile(f)], journal_folder=journal_folder(args.log_dir, False))
    if args.record_test_log:
        record_module = load_module("_record")
        eprint(TR("Test recording (--record-test-log): starts with the live stream, stops after {minutes} min, then the program exits; archive in {folder}").format(
            minutes=f"{args.record_test_log:g}", folder=record_module.default_folder(options["journal_folder"]) if record_module else "?"))
    folder = None if args.no_follow else journal_folder(args.log_dir, args.no_log_file)
    output = Output(sys.stdout, folder, args.log_keep_days, COLOR, "-filter" if args.only else "")        # a filtered launch (--only) has its own journal: several simultaneous launches do not mix their lines
    # 1.88: by default (and from the configuration file) only on a TERMINAL - a program that reads this output (pipe, tests) gets the real lines; an explicit
    # --truncate / --anonymize on the command line always applies
    on_terminal = sys.stdout.isatty()
    if args.truncate == TRUNCATE_AUTO:
        args.truncate = 0 if on_terminal else None
    output.underline = max(0, int(args.underline or 0)) if args.underline is not True else UNDERLINE_DEFAULT     # True: old UNDERLINE=oui read as a boolean
    output.html = not args.no_html_journal               # 1.120: HTML copy of the daily journal
    options["underline"] = output.underline              # 1.102: U key; saved by C
    output.truncate = None if args.truncate is None or args.truncate is False or args.truncate < 0 else args.truncate
    asked = any(a.startswith("--anon") and "--anonymize".startswith(a) for a in sys.argv[1:])
    anonymize = asked or (args.anonymize is not False and on_terminal)
    if anonymize and not os.environ.get("NGINX_TOOLS_ANON_ACTIF"):     # already filtered by a parent program: never twice
        anonymiser = load_module("_anonymiser")
        if anonymiser is None:
            eprint("ERROR: anonymization requested but apps/_anonymiser.py is unreadable: nothing is displayed (--no-anonymize: real values).")
            return 2
        output.anonymize = output.anonymiser = new_anonymiser(anonymiser)
    eprint("Screen: " + ("log lines shortened to " + (f"{output.truncate} columns (« start … last two words »; --no-truncate: whole lines)" if output.truncate
                                                       else "$COLUMNS - 10 (« start … last two words »; --no-truncate: whole lines)")
                         if output.truncate is not None else "whole log lines (--truncate: shortened)")
           + " · " + ("addresses, e-mails and names anonymized (--no-anonymize: real values)" if output.anonymize else "real addresses, e-mails and names (--anonymize: pseudonyms)")
           + (" · " + TR("one log line out of {n} underlined (--underline N, --no-underline: none)").format(n=output.underline) if output.underline else ""))
    if folder:
        COLOR = True                                  # the daily journal keeps the colors; the screen removes them if it is not a terminal (Output.write)
        eprint(f"Daily log (colors kept, permissions 600, {args.log_keep_days or 'all the'} days kept): {folder}/{SCRIPT_NAME}-YYYY-MM-DD{'-filter' if args.only else ''}.log — "
               f"read with: less -R FILE or tail -f FILE")
    options["anonymize"] = output.anonymize is not None              # 1.91: A key and C key (ANONYMIZE saved like the other settings)
    return follow(cmd, people, resolver, options, output)


def protected_main():
    """protected main(): Ctrl-C terminates cleanly, without a traceback (code 130)."""
    try:
        return main()
    except KeyboardInterrupt:
        with contextlib.suppress(KeyboardInterrupt, OSError):
            eprint("\nInterrupted (Ctrl-C).")
        return 130


def launch_with_report(func):
    """--report-err: error report to copy-paste at the end of the run (apps/_rapport.py, if it is next to it)."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        module = load_module("_rapport")
        if module is None:
            eprint("--report-err unavailable (apps/_rapport.py missing) — normal run.")
            return func()
        return module.lancer(func, os.path.basename(__file__), __version__, SCRIPT_DIR)
    return func()


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(protected_main))
    except KeyboardInterrupt:                           # Ctrl-C during the stop itself (summary, questions): clean exit, without a traceback
        sys.exit(130)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
