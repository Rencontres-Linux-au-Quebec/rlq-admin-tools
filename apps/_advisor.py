#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _advisor.py - analysis of the problems raised by the dashboard of app-log-live.py (z key), with recommended solutions
# and a history of the analyses for continuous improvement (shared module, apps/).
#
"""Three steps, all read-only:

  1. FACTS: app-log-live.py hands over the counters of its summary (5xx and 4xx errors, 404 of the sitemap, Odoo errors, conflicts,
     failed e-mails, slow requests, addresses to ban, account forms, latency sample) as a plain dictionary (see analyze()).
  2. DETAILS read in the logs, only for the problems raised: the Odoo traceback that follows each ERROR / CRITICAL message
     (Odoo logfile or systemd journal, a few seconds around its time) and, for the URLs answering 4xx, the status codes, the
     referers (where the dead link is) and the User-Agents found in the nginx access logs.
  3. FINDINGS: each rule turns facts and details into a finding (stable identifier, severity, evidence, probable cause,
     recommendations). The History compares the findings with the previous analyses (advisor-history.json in the state folder of
     app-log-live.py): new, recurring, resolved, and the problems seen most often (what to fix first).

Every text goes through `tr` (catalogue lang/_advisor.fr.po, the module is written in English) and every piece of log data through
`raw` (never translated). Nothing is modified on the server; the only file written is the history."""
import calendar
import gzip
import hashlib
import json
import os
import re
import time
from collections import Counter

__version__ = "1.16.20261109.234500"

PROBLEM, LOOK, INFO = 2, 1, 0                         # severities: problem, to look at, information

HISTORY_FILE = "advisor-history.json"
ACK_FILE = "acknowledged.json"                        # 1.9: findings checked by an administrator (app-log-live.py --ack CODE)
ACK_GROWTH = 2                                        # 1.9: an acknowledged finding comes back when its count is more than twice the count at the check
HISTORY_MAX_RUNS = 200                                # analyses kept in the history
HISTORY_MAX_DAYS = 90                                 # ... and never older than this
TAIL_BYTES = 30 * 1024 * 1024                         # end of each log file read for the details
TRACE_MAX_LINES = 80                                  # lines of one traceback kept

# Two-letter codes of ISO 639-1: a path "/xx" whose xx is not one of them cannot be a language prefix of Odoo.
ISO_639_1 = set("aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu "
                "fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko "
                "kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa "
                "pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty "
                "ug uk ur uz ve vi vo wa wo xh yi yo za zh zu".split())

LANGUAGE_PATH_RE = re.compile(r"^/[a-z]{2}(?:_[A-Z]{2})?/?$")            # the whole path is one language-like segment ("/ev", "/fr_CA")
LANGUAGE_PREFIX_RE = re.compile(r"^/[a-z]{2}(?:_[A-Z]{2})?(?=/|$)")
COLD_RE = re.compile(r"/web/assets/|/web/bundle/|/get_views\b|/web/webclient/(?:load_menus|translations)")
SHOP_EVENT_RE = re.compile(r"/(?:shop|event)/[^/?]+")
ODOO_HEADER_RE = re.compile(r"^(?:\S+\s+)?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,.]\d+)?\s+\d+\s+(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)\s")
EXCEPTION_RE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Failure|NotFound|Timeout|Exit|Interrupt|Forbidden|Unauthorized|Conflict))(?::\s*(.*))?$")
FRAME_RE = re.compile(r'^\s*File "([^"]+)", line (\d+), in (\S+)')
ADDON_RE = re.compile(r"[/_-]addons/([A-Za-z0-9_]+)/")          # .../addons/MODULE/, .../rlq-addons/MODULE/, .../custom_addons/MODULE/
NGINX_LINE_RE = re.compile(r'\[(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})\]\s+"(GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH)\s+(\S+)'
                           r'[^"]*"\s+(\d{3})\s+\S+\s+"([^"]*)"\s+"([^"]*)"')
BYTES_RE = re.compile(r'"\s\d{3}\s(\d+)\s')                 # 1.5: size of the response (a 404 of nginx is about 150 bytes, a 404 page of Odoo several KB)
# 1.5: robots, link previews and tools (they have no cookie: Odoo pages reserved to a visitor answer them 404)
ROBOT_PATTERN = (r"bot\b|bot/|crawl|spider|slurp|Google-Read-Aloud|WhatsApp|facebookexternalhit|LinkedInBot|Twitterbot|Slackbot|Telegram|Discord|preview|"
                 r"curl/|python|wget|Go-http|okhttp|\bJava/|axios|node-fetch|HeadlessChrome|Lighthouse")
ROBOT_AGENT_RE = re.compile(ROBOT_PATTERN, re.I)
ROBOT_NAME_RE = re.compile(r"[\w.-]*(?:" + ROBOT_PATTERN + r")[\w./-]*", re.I)          # 1.6: the NAME of the robot (Google-Read-Aloud, WhatsApp/2.23...), not the start of the User-Agent
REGISTRATION_SUCCESS_RE = re.compile(r"/event/[^/]+/registration/success$")
HOST_RE = re.compile(r'\bhost="?([^"\s]+)"?')          # 1.3: host="$host" of the nginx log format is QUOTED (the quotes made every referer "another site")
# 1.3: query strings of a vulnerability scanner (fuzzing): quotes and brackets, "zqzz" markers, SQL and script fragments
FUZZ_RE = re.compile(r"zqzz|[\"'](?:\)|\()|\(\(|%2[27]|%3[Cc]|<script|\bsleep\(|\bunion\b.*\bselect\b|\.\./|\bor\b\s*\d+\s*=\s*\d+", re.I)
NGINX_TAG_RE = re.compile(r"^\[(?:error|crit|alert|emerg|warn)\]\s+N#N:\s*(?:\*N\s+)?")
UPSTREAM_RE = re.compile(r"while connecting to upstream|upstream timed out|no live upstreams|upstream prematurely closed|while reading response header from upstream")
EVENT_ID_RE = re.compile(r"^(?:/[a-z]{2}(?:_[A-Z]{2})?)?/event/[^/]*?-(\d+)(?:/|$)")
PRODUCT_ID_RE = re.compile(r"^(?:/[a-z]{2}(?:_[A-Z]{2})?)?/shop/(?:product/)?[^/]*?-(\d+)(?:/|$)")
WP_SITEMAP_RE = re.compile(r"/(?:sitemap_index|wp-sitemap|sitemap-index|post-sitemap|page-sitemap)\.xml$|/sitemap\.xml\.gz$")
LONG_CONNECTION_RE = re.compile(r"/(?:websocket|longpolling)(?:[/?\s\"]|$)")          # 1.4: a connection kept open (chat, bus): its duration is not a slowness
KILLED_RE = re.compile(r"oom-kill|code=killed|status=9/KILL|Failed with result|Killing process|signal=KILL|core-dump|Main process exited, code=(?:exited, status=[1-9]|killed|dumped)")
FILE_RE = re.compile(r"/static/|^/(?:[a-z]{2}(?:_[A-Z]{2})?/)?web/(?:image|content)\b|\.(?:png|jpe?g|gif|webp|svg|ico|woff2?|ttf|css|js)(?:\?|$)", re.I)   # 1.16: files (no computation by Odoo)
TOGETHER_S = 2                                        # 1.14: slow requests that end less than this apart, with almost no SQL: a common wait (disk)


def ended_together(items, window=TOGETHER_S):
    """1.14: (count, first end) of the largest group of at least 3 slow requests that END within `window` seconds of each other with less than 10 % of
    their time in SQL and at least 2 s outside SQL; (0, None) otherwise. items: [(end epoch, SQL s, Python s)]."""
    quiet = sorted(t for t, sql, py in items if py >= 2 and sql < 0.1 * (sql + py))
    best, first = 0, None
    for i, t in enumerate(quiet):
        k = sum(1 for u in quiet[i:] if u - t <= window)
        if k > best:
            best, first = k, t
    return (best, first) if best >= 3 else (0, None)


SIMULTANEOUS_S = 60                                   # 1.7: slow requests on different pages less than this apart slowed down together
BACKEND_RPC_RE = re.compile(r"^/(?:web/dataset/|web/action/|mail/(?:thread|data)|web/webclient/)")
CALL_BUTTON_RE = re.compile(r"/web/dataset/call_(?:button|kw)/([\w.]+)/(\w+)")
RESOLVED_AFTER = 3600                                 # 1.7: an interruption over for more than one hour, Odoo running again: history (information)
ODOO_DEFAULTS = {"workers": 0, "max_cron_threads": 2, "limit_time_cpu": 60, "limit_time_real": 120, "limit_memory_soft": 2048, "limit_memory_hard": 2560}
VIRTUAL_OVERHEAD_MB = 400     # 1.11: virtual memory of an Odoo 18 worker beyond its RSS (libraries, reservations), when it cannot be measured
IDLE_WORKER_VMS_MB = 700      # 1.11: virtual memory of an Odoo 18 worker at rest, when it cannot be measured (PROD 2026-11-09: 660 MB)
SOFT_FLOOR_MB = 1024          # 1.11: limit_memory_soft never suggested under this (nor under 1.5 × a worker at rest)


def memory_plan(total, other, workers, cron, idle_vms=None, overhead=None):
    """1.11: limits of the Odoo processes for `total` MB of memory, the same calculation as step 6 of nginx-hardening.sh 2.85. The RAM (RSS) is shared:
    reserve for what runs outside Odoo (what it uses now, at least 15 %), margin of 10 % (at least 512 MB), the rest by workers + cron + 1 gevent;
    the limits are VIRTUAL memory: RSS share + overhead. limit_memory_soft never under max(1024 MB, 1.5 × a worker at rest): when the memory is too
    short for that, too_many is set with the largest number of workers that fits."""
    idle = idle_vms or IDLE_WORKER_VMS_MB
    over = overhead if overhead is not None else VIRTUAL_OVERHEAD_MB
    processes = max(1, workers + cron + 1)
    reserve = max(int(total * 0.15), other or 0)
    budget = max(0, total - reserve - max(512, total // 10))
    hard = budget // processes + over
    soft = hard * 85 // 100
    floor = max(SOFT_FLOOR_MB, idle * 3 // 2)
    too_many = soft < floor
    if too_many:
        soft = floor
        hard = max(hard, floor * 6 // 5)
    max_workers = max(1, budget // max(1, hard - over) - cron - 1)
    return {"hard": hard, "soft": soft, "budget": budget, "reserve": reserve, "overhead": over, "idle_vms": idle, "too_many": too_many, "max_workers": max_workers,
            "ram_needed": ram_needed(processes * max(0, COMFORT_HARD_MB - over), total, other) if hard < COMFORT_HARD_MB else total}


def ram_needed(need_mb, total, other=None):
    """1.12: smallest memory (MB, in steps of 1 GB) whose share for Odoo (memory_plan: reserve of 15 % or what runs outside Odoo, margin of 10 %, at least
    512 MB) holds `need_mb` of RAM; `total` when it already does."""
    size = max(total, 1024)
    while size - max(int(size * 0.15), other or 0) - max(512, size // 10) < need_mb and size < 1048576:
        size += 1024
    return size


COMFORT_HARD_MB = 1536        # 1.12: limit_memory_hard under which more memory is recommended (about 1100 MB of real RAM: big reports, exports, imports)
GEVENT_SOFT_MB, GEVENT_HARD_MB = 2048, 2560   # 1.12: limit_memory_soft_gevent / limit_memory_hard_gevent recommended (the Odoo defaults of the workers)


MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}

# Known Odoo messages: (pattern on "logger: message", severity, cause, recommendation). The first match wins.
KNOWN_MESSAGES = (
    (r"\.map should have been generated through debug assets", INFO,
     "a browser with its developer tools open asked for a source map (.map) of the assets: harmless",
     "nothing to do; it disappears when nobody opens the developer tools (or in debug=assets mode)"),
    (r"No CSRF validation token provided", INFO,
     "a form sent without its security token (CSRF): a robot or a scanner that posts to the site, or a page left open so long that its token expired",
     "nothing to do if it is rare; many times from one address: look at that address (it may be a scanner to ban)"),
    (r"dbfilter rejects it", INFO,
     "a browser came back with a session of another database (an old copy or a test database): Odoo closes that session",
     "nothing to do; it stops once the person signs in again"),
    (r"called ignoring args", INFO,
     "a browser sent an argument that this version of Odoo no longer expects: an old copy of the web client kept in the browser cache",
     "nothing to do if it is rare; frequent after an update: the users reload the page (Ctrl-Shift-R)"),
    (r"(?:not allowed to access|pas autoris).*mail\.guest|mail\.guest.*(?:access|accès)", INFO,
     "a visitor of the live chat came back with an expired guest session (cookie of an old conversation)",
     "nothing to do if it is rare; many times a day: check the live chat module and the cookie settings"),
    (r"Exception during request handling", LOOK,
     "a request raised an exception: the cause is in the traceback that follows the message",
     "read the traceback below (or key E); fix the module named in the last frame, or report it to its author"),
    # 1.7: a "bad query" is not always a retried conflict: the unique violation of mail_push_device (a browser that subscribes again to the push
    # notifications) was called "concurrent update retried by Odoo", which it is not (Odoo does not retry a unique violation)
    (r"mail_push_device|endpoint must be unique|point de terminaison doit [êe]tre unique", INFO,
     "a browser subscribed again to the push notifications with an endpoint Odoo already holds: PostgreSQL refuses the copy (unique constraint), the existing subscription stays valid",
     "nothing to do: harmless; frequent with several tabs open or after a reconnection"),
    (r"could not serialize access|SerializationFailure", INFO,
     "concurrent update retried by Odoo",
     "nothing to do while the final failures stay at zero"),
    (r"bad query", LOOK,
     "a SQL query refused by PostgreSQL: the reason (constraint, conflict, syntax) is on the line that follows it in the log",
     "read the line that follows it (key E): a unique constraint is usually a form sent twice; anything else: the module named in the traceback"),
)

# Exceptions found at the end of a traceback: (pattern on the exception line, cause, recommendation). The first match wins.
TRACEBACK_HINTS = (
    (r"AccessError|AccessDenied", "the user had no right on a record (access rule or group missing)",
     "check the groups of the user and the record rules of the model named in the message; normal when a visitor follows an old link"),
    (r"MissingError", "the record no longer exists (deleted) while a page or a link still points to it",
     "find who points to it (link, menu, e-mail, scheduled action) and remove or update the reference"),
    (r"ValidationError|UserError", "a validation of the module refused the data entered",
     "usually a user message, not a bug; if it repeats, read the message: a constraint or a mandatory field"),
    (r"psycopg2\.errors\.(?:SerializationFailure|LockNotAvailable)|could not serialize|deadlock", "concurrent updates of the same record",
     "Odoo retries by itself; repeated final failures: a scheduled action and users write the same record at the same time"),
    (r"psycopg2\.(?:OperationalError|InterfaceError)|connection (?:refused|already closed)|too many clients", "PostgreSQL connection lost or refused",
     "check PostgreSQL (systemctl status postgresql), max_connections and db_maxconn of odoo.conf"),
    (r"MemoryError|limit_memory", "an Odoo worker ran out of memory",
     "raise limit_memory_soft / limit_memory_hard in odoo.conf, or find the heavy report or export"),
    (r"Timeout|TimeoutError|limit_time", "a request ran longer than the allowed time",
     "find the slow page (slow requests, key Y); raise limit_time_real only if the page is legitimately long"),
    (r"werkzeug\.exceptions\.(?:NotFound|BadRequest|Forbidden)", "a client asked for something that does not exist or is not allowed",
     "nothing to fix in Odoo if the URL is not one of the site's pages"),
    (r"InvalidVapidError|Invalid VAPID public key",
     "a browser registered for push notifications with a VAPID public key different from the one stored in Odoo (ir.config_parameter mail.web_push_vapid_public_key): usually after a database restore or copy, or a regenerated key",
     "harmless for the site: only the push notifications of these browsers fail; nothing to fix if the key was changed on purpose, the browsers subscribe again when their site data is cleared"),
    (r"KeyError|AttributeError|TypeError|IndexError|ValueError|NameError", "a programming error in a module",
     "the module named in the last frame of the traceback has a bug: update it, or report it to its author with the traceback"),
)

# 1.7: (pattern on the failure reason, solution track). Several may apply to one e-mail; the first ones are the most specific.
SMTP_HINTS = (
    (r"4\.4\.5|messages? per session|too many messages", "the mail server accepts only a few e-mails per SMTP connection: set the system parameter mail.session.batch.size (Settings > Technical > System Parameters) to that limit or below (for example 3): Odoo then opens a new SMTP connection every 3 e-mails; then resend"),
    (r"\b535\b|authentication|auth\w* fail|password not accepted|identifiants", "the mail server refused the user name or the password: check them in Settings > Technical > Outgoing Mail Servers, then « Test Connection »"),
    (r"\b5\.7\.\d+\b|\bSPF\b|\bDKIM\b|\bDMARC\b|not permitted to relay|relay access denied|sender address rejected", "the sender is refused: send from an address of the domain of the mail server (FROM filter of the server, mail.default.from), and check SPF and DKIM of that domain"),
    (r"\b5\.1\.1\b|user unknown|does not exist|no such user|mailbox unavailable|recipient address rejected", "the recipient address does not exist: correct the e-mail of the contact, then resend"),
    (r"\b552\b|quota|mailbox full|over quota", "the mailbox of the recipient is full: nothing to fix on our side, resend later"),
    (r"\b421\b|\b45[0-2]\b|temporar|try again later|greylist|rate limit|too many", "the mail server refuses for now (rate limit, greylisting): resend later; if it repeats, the provider limits the e-mails per hour"),
    (r"\b503\b|\b530\b|STARTTLS|must issue", "the mail server expects another order of the commands (STARTTLS or authentication missing): check the encryption of the outgoing server (STARTTLS on port 587, SSL/TLS on 465)"),
    (r"certificate|\bSSL\b|\bTLS\b|handshake", "the secure connection to the mail server failed (certificate or protocol): check the encryption and the port of the outgoing server"),
    (r"Connection refused|timed out|unreachable|Name or service not known|getaddrinfo|No route to host|Temporary failure in name resolution", "the mail server could not be reached: check its name and port, the DNS and the firewall of this server (nc -vz SERVER PORT)"),
    (r"invalid email|invalid address|mail_email_invalid|no valid recipient|missing email|mail_email_missing|adresse.{0,20}invalide", "the recipient has no valid e-mail address in Odoo: correct the contact, then resend"),
    (r"\b550\b|\b554\b|rejected|blocked|spam", "the recipient server refused the e-mail (content or reputation of the sender): read the message of the server above; check SPF, DKIM and the sender address"),
)
GENERIC_MAIL_REASON_RE = re.compile(r"^\s*(?:[ÉE]chec d'envoi de l'e-mail|Mail Delivery Failed|Failed to send|Unknown error)\W*$", re.I)


def _identity(text):
    return text


def _cut(text, limit):
    """Text cut at `limit` characters, with « … » when something was cut."""
    text = text or ""
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _span(seconds):
    """1.7: "45 s", "12 min", "8 h 22 min", "50 h 03 min" (units written the same way in French and in English)."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip())


# ------------------------------------------------------------------------------------------------------------------
# Details read in the logs
# ------------------------------------------------------------------------------------------------------------------
def read_tail(path, max_bytes=TAIL_BYTES):
    """Lines of the end of a file (max_bytes at most, the first partial line dropped); [] if unreadable.
    1.2: a rotated log compressed with gzip (.gz) is decompressed, and the end of its text is kept the same way."""
    if path.endswith(".gz"):
        try:
            with gzip.open(path, "rb") as f:
                data = f.read()
        except (OSError, EOFError):
            return []
        lines = data[-max_bytes:].decode("utf-8", "replace").splitlines()
        return lines[1:] if len(data) > max_bytes and lines else lines
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[1:] if size > max_bytes and lines else lines


def odoo_trace(lines, logger, message):
    """The message line of `logger` that contains `message`, and the lines that follow it until the next Odoo header (the traceback).
    The LAST occurrence is kept (the most recent). [] if not found."""
    # the message as counted by app-log-live.py: numbers replaced by N, so the pieces between the N are searched
    parts = [p for p in re.split(r"(?<![A-Za-z\d])N(?![A-Za-z\d])", _norm(message)[:80]) if p.strip()] or [_norm(message)[:80]]
    found = None
    for i, text_line in enumerate(lines):
        if logger and logger not in text_line:
            continue
        if all(p.strip() in text_line for p in parts):
            found = i
    if found is None:
        return []
    trace = [lines[found]]
    for text_line in lines[found + 1:found + 1 + TRACE_MAX_LINES]:
        if ODOO_HEADER_RE.match(text_line):
            break
        trace.append(text_line)
    return trace


def exception_counts(lines, logger, message):
    """Counter {"Exception: message": n} of the exceptions that end the tracebacks of EVERY occurrence of the message (not only the last one): the same
    « Exception during request handling » hides different causes. Works on a complete log and on the output of journalctl -g (headers and exception lines only)."""
    parts = [p for p in re.split(r"(?<![A-Za-z\d])N(?![A-Za-z\d])", _norm(message)[:80]) if p.strip()] or [_norm(message)[:80]]
    res, inside = Counter(), False
    for text_line in lines:
        if ODOO_HEADER_RE.match(text_line):
            inside = (not logger or logger in text_line) and all(p.strip() in text_line for p in parts)
            continue
        if inside:
            m = EXCEPTION_RE.match(text_line.strip())
            if m:
                res[m.group(1).rsplit(".", 1)[-1] + (": " + _cut(m.group(2).strip(), 80) if m.group(2) else "")] += 1
                inside = False
    return res


def parse_traceback(trace):
    """{"exception": type, "message": text, "module": addon of the last frame in an addons folder, "frame": "file:line in function"} or {}."""
    if len(trace) < 2:
        return {}
    exception = message = module = frame = ""
    for text_line in trace[1:]:
        m = FRAME_RE.match(text_line)
        if m:
            a = ADDON_RE.search(m.group(1))
            if a:
                module = a.group(1)
                frame = f"{os.path.basename(m.group(1))}:{m.group(2)} in {m.group(3)}"
            continue
        m = EXCEPTION_RE.match(text_line.strip())
        if m:
            exception, message = m.group(1), (m.group(2) or "").strip()
    if not exception:
        return {}
    return {"exception": exception, "message": message[:300], "module": module, "frame": frame}


def nginx_details(files, urls, since=None, max_bytes=TAIL_BYTES):
    """For each URL of `urls` (path, without the query): {"codes", "referers", "agents", "hosts", "methods": Counter} read in the nginx access logs
    (end of each file, lines after `since` when given)."""
    wanted = {u.split("?", 1)[0] for u in urls}
    res = {u: {"codes": Counter(), "referers": Counter(), "agents": Counter(), "hosts": Counter(), "methods": Counter(), "robots": Counter(), "browser_hits": 0,
               "browser_ips": set(), "browser_queries": Counter(), "queries": Counter(), "bytes_4xx": []} for u in wanted}
    if not wanted:
        return res
    for path in files:
        for text_line in read_tail(path, max_bytes):
            m = NGINX_LINE_RE.search(text_line)
            if not m:
                continue
            url = m.group(11).split("?", 1)[0]
            if url not in wanted:
                continue
            if since is not None:
                try:
                    offset = (int(m.group(8)) * 3600 + int(m.group(9)) * 60) * (-1 if m.group(7) == "-" else 1)
                    t = calendar.timegm((int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)), int(m.group(6)), 0, 0, 0)) - offset
                except (KeyError, ValueError, OverflowError):
                    t = None
                if t is not None and t < since:
                    continue
            d = res[url]
            d["methods"][m.group(10)] += 1
            d["codes"][m.group(12)] += 1
            if m.group(13) and m.group(13) != "-":
                d["referers"][m.group(13)] += 1
            d["agents"][m.group(14)[:80]] += 1
            h = HOST_RE.search(text_line)
            if h:
                d["hosts"][h.group(1)] += 1
            query = m.group(11).partition("?")[2]
            if query:
                d["queries"][query[:200]] += 1
            if m.group(12)[:1] == "4":
                b = BYTES_RE.search(text_line)
                if b and len(d["bytes_4xx"]) < 200:
                    d["bytes_4xx"].append(int(b.group(1)))
            if ROBOT_AGENT_RE.search(m.group(14)):
                name = ROBOT_NAME_RE.search(m.group(14))
                d["robots"][(name.group(0) if name else m.group(14))[:60]] += 1
            else:
                d["browser_hits"] += 1
                d["browser_ips"].add(text_line.split(" ", 1)[0])
                if query:
                    d["browser_queries"][query[:200]] += 1
    return res


def _bare_host(host):
    """www.example.org:443 -> example.org (the site is the same with or without www, on any port)."""
    host = (host or "").strip('"').lower().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def internal_referers(detail, site_hosts=()):
    """Referers of the site itself (same host as the request, or one of `site_hosts`, with or without www): the page that holds the dead link."""
    hosts = {_bare_host(h) for h in list(detail.get("hosts") or ()) + list(site_hosts or ()) if h}
    res = Counter()
    for ref, n in (detail.get("referers") or {}).items():
        m = re.match(r"^https?://([^/]+)", ref)
        if m and (not hosts or _bare_host(m.group(1)) in hosts):
            res[ref] += n
    return res


ODOO_TIME_RE = re.compile(r"^(?:\S+\s+)?(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


def trace_near(lines, instant, margin=3):
    """The first ERROR / CRITICAL traceback of Odoo whose header time (UTC, as Odoo writes it) is within `margin` seconds of `instant`; [] if none."""
    for i, text_line in enumerate(lines):
        if not ODOO_HEADER_RE.match(text_line) or not re.search(r"\s(?:ERROR|CRITICAL)\s", text_line[:80]):
            continue
        m = ODOO_TIME_RE.match(text_line)
        if not m:
            continue
        t = calendar.timegm(tuple(int(x) for x in m.groups()) + (0, 0, 0))
        if abs(t - instant) <= margin:
            return first_error_trace(lines[i:])
    return []


def first_error_trace(lines):
    """The first ERROR / CRITICAL line of Odoo in `lines` and the lines that follow it (its traceback); [] if none."""
    for i, text_line in enumerate(lines):
        if ODOO_HEADER_RE.match(text_line) and re.search(r"\s(?:ERROR|CRITICAL)\s", text_line[:80]):
            trace = [text_line]
            for following in lines[i + 1:i + 1 + TRACE_MAX_LINES]:
                if ODOO_HEADER_RE.match(following):
                    break
                trace.append(following)
            return trace
    return []


def odoo_settings_advice(conf, cpus, mem_mb, slowest=None):
    """(evidence, advice, cause or "") from the settings of odoo.conf (`conf`: key -> text), the processors and the memory of the machine, following the
    rules of the Odoo deployment guide: at most (2 x CPU) + 1 workers; about 150 MB per light worker and 1 GB per heavy one (80 % / 20 %)."""
    def number(key):
        value = (conf.get(key) or "").strip()
        try:
            return int(float(value))
        except ValueError:
            return None
    evidence, advice, cause = [], [], ""
    workers = number("workers") if number("workers") is not None else ODOO_DEFAULTS["workers"]
    cron = number("max_cron_threads") if number("max_cron_threads") is not None else ODOO_DEFAULTS["max_cron_threads"]
    t_cpu = number("limit_time_cpu") or ODOO_DEFAULTS["limit_time_cpu"]
    t_real = number("limit_time_real") or ODOO_DEFAULTS["limit_time_real"]
    soft = (number("limit_memory_soft") or ODOO_DEFAULTS["limit_memory_soft"] * 1048576) // 1048576
    hard = (number("limit_memory_hard") or ODOO_DEFAULTS["limit_memory_hard"] * 1048576) // 1048576
    evidence.append("odoo.conf : workers={w} · max_cron_threads={c} · limit_time_cpu={tc} s · limit_time_real={tr} s · limit_memory_soft={ms} MB · limit_memory_hard={mh} MB".format(
        w=workers, c=cron, tc=t_cpu, tr=t_real, ms=soft, mh=hard))
    best = 2 * cpus + 1 if cpus else None
    need = round(workers * (0.8 * 150 + 0.2 * 1024) + cron * 150) if workers else None
    if workers == 0:
        cause = "workers=0"
        advice.append(("workers0", best, max(1, int((mem_mb or 0) * 0.7 // 325)) if mem_mb else None))
    elif best and workers > best:
        cause = "too-many"
        advice.append(("too-many", best, workers))
    elif best and workers < cpus:
        # 1.15: the memory bound of nginx-hardening.sh 2.93 (each process may reach limit_memory_hard 1536 MB, 400 MB of which take no RAM), not
        # 325 MB per worker: DEV (16 GB) was told « up to 13 workers » while step 6 recommends 7
        cron = number("max_cron_threads") if number("max_cron_threads") is not None else ODOO_DEFAULTS["max_cron_threads"]
        bound = memory_plan(mem_mb, None, 1, cron)["budget"] // (COMFORT_HARD_MB - VIRTUAL_OVERHEAD_MB) - cron - 1 if mem_mb else best
        advice.append(("few", max(1, min(best, bound)), workers))
    if need and mem_mb and need > 0.8 * mem_mb:
        advice.append(("memory", need, mem_mb))
    if slowest and slowest >= 0.8 * t_real:
        advice.append(("limit-real", round(slowest), t_real))
    return evidence, advice, cause


# ------------------------------------------------------------------------------------------------------------------
# Rules
# ------------------------------------------------------------------------------------------------------------------
class Analyzer:
    """analyze(facts, details) -> list of findings {"id", "severity", "title", "count", "evidence": [...], "cause": text, "advice": [...], "fix": (kind, data) or None}.
    `details` holds what app-log-live.py read for these problems: logs (tracebacks, nginx), Odoo settings, database, current answer of the site."""

    def __init__(self, tr=_identity, raw=_identity):
        self.tr, self.raw = tr, raw
        self.findings = []

    def add(self, fid, severity, title, count=1, evidence=(), cause="", advice=(), fix=None, confirmed=False):
        """confirmed (1.7): the cause is PROVEN by what was read (PostgreSQL message, database, service journal), not drawn from a general rule."""
        self.findings.append({"id": fid, "severity": severity, "title": title, "count": count, "evidence": [e for e in evidence if e], "cause": cause,
                              "advice": list(advice), "fix": fix, "confirmed": bool(confirmed)})

    def run(self, facts, details=None):
        details = details or {}
        self.findings = []
        for rule in (self.rule_5xx, self.rule_nginx_upstream, self.rule_sitemap_404, self.rule_repeated_4xx, self.rule_odoo_errors, self.rule_conflicts,
                     self.rule_push_duplicates, self.rule_mails, self.rule_slow, self.rule_memory, self.rule_odoo_conf_check, self.rule_odoo_runtime, self.rule_hot_pairs, self.rule_bans,
                     self.rule_account_forms,
                     self.rule_latency_sample):
            try:
                rule(facts, details)
            except Exception as problem:                     # one rule never stops the others
                self.add("advisor-rule-failed:" + rule.__name__, INFO, self.tr("Rule {name} could not run: {problem}").format(name=rule.__name__, problem=self.raw(str(problem))))
        if not any(f["severity"] >= LOOK for f in self.findings):
            self.add("all-clear", INFO, self.tr("Nothing to fix in this window: no error that needs an action"))
        self.findings.sort(key=lambda f: (-f["severity"], -f["count"], f["id"]))
        return self.findings

    # --- shared pieces ---------------------------------------------------------------------------------------------------------------
    def referer_lines(self, detail, facts):
        tr, raw = self.tr, self.raw
        lines = []
        inside = internal_referers(detail, facts.get("site_hosts") or ())
        if inside:
            lines.append(tr("Linked from the site itself: ") + " ; ".join(f"{raw(r)} ×{n}" for r, n in inside.most_common(3)))
        outside = Counter({r: n for r, n in (detail.get("referers") or {}).items() if r not in inside})
        if outside:
            lines.append(tr("Linked from other sites: ") + " ; ".join(f"{raw(r)} ×{n}" for r, n in outside.most_common(3)))
        return lines

    @staticmethod
    def origin_kind(detail):
        """1.6: "nginx" when the 404 page is the small one of nginx (median size of the 4xx answers of 400 bytes or less), "odoo" when it is a page of several KB, None if unknown."""
        sizes = sorted(detail.get("bytes_4xx") or [])
        if not sizes:
            return None
        return "nginx" if sizes[len(sizes) // 2] <= 400 else "odoo"

    def server_name(self, who, ip):
        """1.6: how a requester is named: the name known by the dashboard, "this server" translated, a loopback address as this server."""
        name = who.get(ip, ip)
        if name.startswith("this server"):
            name = self.tr("this server") + name[len("this server"):]
        elif ip.startswith("127.") or ip == "::1":
            name = self.tr("this server") + f" [{ip}]"
        return name

    def origin_lines(self, detail):
        """1.5: what the program checks itself in the access log, instead of asking the administrator: WHO asked (robots / link previews or browsers), WHAT answered
        (the 404 page of nginx is about 150 bytes: a rule of nginx; a page of several KB is Odoo's) and whether a visitor retried the same address."""
        tr, raw = self.tr, self.raw
        lines = []
        sizes = sorted(detail.get("bytes_4xx") or [])
        if sizes:
            middle = sizes[len(sizes) // 2]
            if self.origin_kind(detail) == "nginx":
                lines.append(tr("The 404 page is the one of nginx ({n} bytes): a rule or a location of nginx refuses this address (securite-commune.conf, bot_blocker.conf...), not Odoo").format(n=middle))
            else:
                lines.append(tr("The 404 page is the one of Odoo ({kb} KB): the request reached Odoo, nginx did not refuse it").format(kb=f"{middle / 1024:.1f}"))
        robots = detail.get("robots") or Counter()
        browsers = detail.get("browser_hits") or 0
        if robots or browsers:
            text = tr("Asked by: ")
            parts = []
            if robots:
                parts.append(tr("{n} robots, link previews or tools").format(n=sum(robots.values())) + " (" + " ; ".join(f"{raw(a)} ×{k}" for a, k in robots.most_common(2)) + ")")
            if browsers:
                parts.append(tr("{n} browsers from {k} addresses").format(n=browsers, k=len(detail.get("browser_ips") or ())))
            lines.append(text + " ; ".join(parts))
        repeated = [(q, k) for q, k in (detail.get("browser_queries") or Counter()).most_common(3) if k >= 2]
        if repeated:
            lines.append(tr("The same address asked again by browsers: ") + " ; ".join(f"?{raw(_cut(q, 60))} ×{k}" for q, k in repeated))
        return lines

    def codes_line(self, codes):
        """'Codes: 404 ×25, 403 ×3 (and 7 redirects 301 / 303 to the secure address or with www, normal)'."""
        tr = self.tr
        errors = {c: k for c, k in codes.items() if str(c)[:1] in ("4", "5")}
        redirects = sum(k for c, k in codes.items() if str(c)[:1] == "3")
        if not errors and not redirects:
            return ""
        text = tr("Codes: ") + ", ".join(f"{c} ×{k}" for c, k in sorted(errors.items(), key=lambda ck: -ck[1]))
        if redirects:
            text += " " + tr("(and {n} redirections 3xx before, normal: secure address or www)").format(n=redirects)
        return text

    def site_lines(self, path, details):
        """What app-log-live.py checked for this page: its answer now, the record in Odoo, a redirect already defined."""
        tr, raw = self.tr, self.raw
        lines, state = [], {}
        now = (details.get("now") or {}).get(path)
        if now is not None:
            state["now"] = now
            lines.append(tr("Answer of the site now: {code}").format(code=now))
        rec = (details.get("records") or {}).get(path)
        if rec:
            state["record"] = rec
            flags = lambda r: ((" · " + (tr("published") if r.get("published") else tr("NOT published"))) + ("" if r.get("active", True) else " · " + tr("archived"))
                               + (" · " + (tr("ends on {end}") if r["end"] >= time.strftime("%Y-%m-%d") else tr("ended on {end}")).format(end=r["end"]) if r.get("end") else ""))      # 1.8: a future end
            if rec.get("kind") == "missing":
                lines.append((tr("In Odoo: no event with the number {id} (deleted)") if rec.get("what") == "event" else tr("In Odoo: no product with the number {id} (deleted)")).format(id=rec.get("id")))
            elif rec.get("kind") in ("event", "product"):
                lines.append((tr("In Odoo: event n° {id} « {title} »") if rec["kind"] == "event" else tr("In Odoo: product n° {id} « {title} »")).format(
                    id=rec.get("id"), title=raw(_cut(rec.get("name") or "", 60))) + flags(rec))
            elif rec.get("kind") == "page":
                lines.append(tr("In Odoo: web page {url}").format(url=raw(rec.get("url") or path)) + flags(rec))
            elif rec.get("kind") == "no-page":
                lines.append(tr("In Odoo: no web page at this address") + (" · " + tr("similar pages: ") + " ; ".join(raw(u) for u in rec.get("similar") or ()) if rec.get("similar") else ""))
        rewrite = (details.get("rewrites") or {}).get(path)
        if rewrite:
            state["rewrite"] = rewrite
            lines.append(tr("Redirect already defined in Odoo: {kind} to {target}").format(kind=rewrite[1], target=raw(rewrite[0])))
        return lines, state

    # --- 5xx, grouped by page --------------------------------------------------------------------------------------------------------
    def rule_5xx(self, facts, details):
        tr, raw = self.tr, self.raw
        groups = {}
        for url, n in Counter(facts.get("errors5") or {}).items():
            g = groups.setdefault(url.split("?", 1)[0], {"n": 0, "urls": Counter(), "codes": Counter(), "ips": Counter(), "times": []})
            g["n"] += n
            g["urls"][url] += n
        for t, code, url, ip in facts.get("http_errors5") or ():
            g = groups.get(url.split("?", 1)[0])
            if g is not None:
                g["codes"][str(code)] += 1
                g["ips"][ip] += 1
                g["times"].append(t)
        for path, g in groups.items():                       # no time-stamped answer kept (older facts): the codes counted per URL
            if not g["codes"]:
                for url in g["urls"]:
                    g["codes"].update({str(c): k for c, k in ((facts.get("codes_by_url") or {}).get(url) or {}).items() if int(c) >= 500})
        who = facts.get("who") or {}
        traces = details.get("traces_5xx") or {}
        server = set(facts.get("server_ips") or ())
        is_server = lambda ip: ip in server or ip.startswith("127.") or ip == "::1"
        self.server_exceptions, self.visitor_exceptions = set(), set()          # 1.6: exceptions of the 5xx made by this server itself / by visitors
        for path, g in sorted(groups.items(), key=lambda pg: -pg[1]["n"])[:5]:
            n = g["n"]
            fuzz = sum(k for u, k in g["urls"].items() if FUZZ_RE.search(u))
            gateway = sum(k for c, k in g["codes"].items() if c in ("502", "503", "504"))
            evidence = [tr("Codes: ") + ", ".join(f"{c} ×{k}" for c, k in g["codes"].most_common())] if g["codes"] else []
            if len(g["urls"]) > 1 or next(iter(g["urls"])) != path:
                evidence.append(tr("Addresses asked: ") + " ; ".join(f"{raw(_cut(u, 90))} ×{k}" for u, k in g["urls"].most_common(3)))
            if g["ips"]:
                evidence.append(tr("Requested by: ") + " ; ".join(f"{raw(self.server_name(who, ip))} ×{k}" for ip, k in g["ips"].most_common(3)))
            parsed = parse_traceback(traces.get(path) or [])
            made_here = bool(g["ips"]) and all(is_server(ip) for ip in g["ips"])
            if parsed:
                (self.server_exceptions if made_here else self.visitor_exceptions).add(parsed["exception"] + ": " + parsed["message"])
            if parsed:
                evidence.append(tr("Exception: ") + raw(_cut(parsed["exception"] + (": " + parsed["message"] if parsed["message"] else ""), 200)))
                if parsed["module"]:
                    evidence.append(tr("Module of the last frame: {module} ({frame})").format(module=raw(parsed["module"]), frame=raw(parsed["frame"])))
            elif traces.get(path) is not None:
                evidence.append(tr("Traceback not found in the logs read (logfile or systemd journal around this time)"))
            if made_here:
                severity = INFO
                cause = tr("requests made by this server itself (a test, a probe or a curl of the administrator), no visitor involved")
                advice = [tr("nothing to do; if the page needs parameters (registration_ids...), Odoo answers 500 instead of 404 when they are missing: a robot could do the same")]
            elif fuzz and fuzz >= n / 2:
                severity = LOOK
                cause = tr("a vulnerability scanner sends malformed parameters (quotes, brackets, « zqzz »): Odoo answers 500 instead of 400, the site is not harmed")
                advice = [tr("ban the address if it keeps going (key b, or --apply with --advise); nothing to fix in Odoo")]
            elif gateway and gateway >= n / 2:
                severity = PROBLEM if n >= 5 else LOOK
                cause = tr("nginx got no answer from Odoo (502, 503, 504): service stopped or restarting, every worker busy, or a request longer than the timeout")
                advice = [tr("key D: site diagnosis (service, Odoo ports, nginx upstream)"), tr("app-health-check.py: workers, memory and PostgreSQL connections")]
            else:
                severity = PROBLEM if n >= 3 else LOOK
                cause = tr("Odoo answered with an internal error (500): an exception in a module")
                hint = next((h for h in TRACEBACK_HINTS if parsed and re.search(h[0], parsed["exception"] + " " + parsed["message"])), None)
                if hint:
                    cause = tr(hint[1])
                advice = ([tr(hint[2])] if hint else []) + ([tr("fix or update the module named in the traceback")] if parsed and parsed.get("module")
                                                            else [tr("key E: the traceback of the error (app-log-check.py --errors-only --full-trace)")])
                if "/post" in path or "/submit" in path or "/register" in path:
                    advice.insert(0, tr("a form of the site fails for its visitors: test it yourself, the visitors' data is lost at each error"))
            self.add("http-5xx:" + path, severity, tr("HTTP 5xx errors on {url}: {n}").format(url=raw(path), n=n), n, evidence, cause, advice)

    # --- nginx could not reach Odoo --------------------------------------------------------------------------------------------------
    def rule_nginx_upstream(self, facts, details):
        tr, raw = self.tr, self.raw
        groups = {}
        others = Counter()
        for e in facts.get("nginx_errors") or ():
            message = NGINX_TAG_RE.sub("", e["message"])
            kind = message.split(", client:", 1)[0]
            if UPSTREAM_RE.search(message):
                g = groups.setdefault(kind, {"n": 0, "first": None, "last": None, "times": []})
                g["n"] += e["n"]
                g["times"] += list(e.get("times") or ())          # 1.15: each refused connection, to cut the interruptions
                for key, pick in (("first", min), ("last", max)):
                    if e.get(key):
                        g[key] = pick(g[key], e[key]) if g[key] else e[key]
            else:
                others[kind] += e["n"]
        restarts = (details.get("service") or {}).get("events") or []
        state = (details.get("service") or {}).get("state")
        now = facts.get("end") or time.time()
        stamp = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
        for kind, g in sorted(groups.items(), key=lambda kg: -kg[1]["n"]):
            evidence = [raw(_cut(kind, 160))]
            cuts = []
            for t in sorted(g["times"]):
                if cuts and t - cuts[-1][1] <= 300:
                    cuts[-1][1] = t
                else:
                    cuts.append([t, t])
            if len(cuts) > 1:
                # 1.15: several short interruptions (restarts), not one of hours: PROD 2026-11-09 showed « 49 refused connections over 3 h 32 min »
                evidence.append(tr("{k} interruptions, {n} refused connections: ").format(k=len(cuts), n=g["n"]) + " ; ".join(
                    f"{stamp(a)} ({_span(b - a) if b > a else tr('one moment')})" for a, b in cuts[-6:]))
            elif g["first"] and g["last"]:
                evidence.append(tr("From {first} to {last}").format(first=stamp(g["first"]), last=stamp(g["last"]))
                                + " (" + tr("{n} refused connections over {span}").format(n=g["n"], span=_span(g["last"] - g["first"])) + ")")
            near = [(t, text) for t, text in restarts if g["first"] and g["last"] and g["first"] - 600 <= t <= g["last"] + 600]
            # 1.7: the requests of the visitors that got no answer, and why the service stopped (killed, out of memory, failure)
            lost = sum(1 for t, code, _u, _ip in facts.get("http_errors5") or () if code in (502, 503, 504) and g["first"] and g["first"] - 60 <= t <= g["last"] + 60)
            if lost:
                evidence.append(tr("Requests answered 502, 503 or 504 during that time: {n}").format(n=lost))
            killed = [(t, text) for t, text in near if KILLED_RE.search(text)]
            started = [t for t, text in restarts if re.search(r"\bStarted\b", text) and g["last"] and t >= g["last"] - 120]
            resolved = bool(g["last"] and now - g["last"] > RESOLVED_AFTER and state and state.startswith("active") and (started or not restarts))
            if near:
                evidence.append(tr("Service journal at that time: ") + " ; ".join(f"{time.strftime('%H:%M:%S', time.localtime(t))} {raw(_cut(text, 70))}" for t, text in near[:4]))
            confirmed = False
            if killed:
                evidence.append(tr("Reason of the stop in the service journal: ") + " ; ".join(f"{time.strftime('%H:%M:%S', time.localtime(t))} {raw(_cut(text, 90))}" for t, text in killed[:2]))
                cause = tr("Odoo was stopped by the system (killed or failed, see the reason above), not by a restart that was wanted")
                severity, confirmed = PROBLEM, True
                advice = [tr("an « oom-kill » or « status=9/KILL »: the memory ran out, see the finding on the memory risk; otherwise: journalctl -u SERVICE --since the time above")]
            elif near:
                cause = tr("Odoo was stopped or restarting at that time (see the service journal): nginx found its port closed")
                severity, confirmed = LOOK, True
                advice = [tr("nothing to do if the restart was wanted (update, maintenance); otherwise read why the service stopped: journalctl -u SERVICE --since the time above")]
            else:
                cause = tr("nginx could not reach Odoo: service stopped, restarting or crashed, or its port is not the one nginx uses")
                severity = PROBLEM
                advice = [tr("key D: site diagnosis (service, Odoo ports, nginx upstream)"), tr("journalctl -u SERVICE around these times: why Odoo stopped")]
            if state:
                evidence.append(tr("Service now: {svc}").format(svc=raw(state)))
            requests_start = facts.get("requests_start")
            if requests_start and g["last"] and g["last"] < requests_start:
                evidence.append(tr("Before the first request read (the requests start on {when}): this comes from the history of the nginx error log").format(when=stamp(requests_start)))
            if "Connection refused" in kind and g["n"] >= 1:
                evidence.append(tr("These lines come from the nginx error log; before app-log-live.py 1.167 they were counted as Odoo errors and as failed e-mails"))
            title = tr("Odoo unreachable from nginx: {n} times").format(n=g["n"])
            if resolved and not killed:
                # 1.7: over for more than RESOLVED_AFTER, Odoo running again: history, not a problem of today ("0 resolved" while it was over for two days)
                severity = INFO
                title = tr("Odoo was unreachable from nginx (over): {n} times").format(n=g["n"])
                evidence.append(tr("Over for {span}: Odoo answers again and nginx has logged no refusal since").format(span=_span(now - g["last"])))
                advice = [tr("nothing to do now; to know why it stopped: journalctl -u SERVICE --since the time above")] + advice[1:]
            elif resolved:
                severity = LOOK
                evidence.append(tr("Over for {span}: Odoo answers again and nginx has logged no refusal since").format(span=_span(now - g["last"])))
            self.add("nginx-upstream:" + kind[:80], severity, title, g["n"], evidence, cause, advice, confirmed=confirmed)
        if others and sum(others.values()) >= 20:
            self.add("nginx-errors", INFO, tr("Other messages of the nginx error log: {n}").format(n=sum(others.values())), sum(others.values()),
                     [f"{raw(_cut(k, 120))} ×{v}" for k, v in others.most_common(3)], tr("files not found, clients that left, invalid requests: usually harmless"),
                     [tr("nothing to do unless one message repeats a lot")])

    # --- 404 of the sitemap ------------------------------------------------------------------------------------------------------
    def rule_sitemap_404(self, facts, details):
        tr, raw = self.tr, self.raw
        paths = facts.get("sitemap_paths")
        nginx = details.get("nginx") or {}
        for url, n in Counter(facts.get("gone_404") or {}).most_common(5):
            path = url.split("?", 1)[0]
            detail = nginx.get(path) or {}
            refs = self.referer_lines(detail, facts)
            if LANGUAGE_PATH_RE.match(path):
                code = path.strip("/").split("_")[0]
                kind = tr("not a language code") if code not in ISO_639_1 else tr("a language code that the site may not offer")
                self.add("sitemap-404-false:" + path, INFO, tr("404 on {url} counted as a sitemap page: false alarm").format(url=raw(url)), n,
                         [tr("The path is a single segment of two letters ({kind}): app-log-live.py removes it as a language prefix and compares the home page (/), which is in the sitemap").format(kind=kind)] + refs,
                         tr("a truncated or mistyped URL, not a page of the site that disappeared"),
                         [tr("nothing to fix on the site; since app-log-live.py 1.164 only the codes of ISO 639-1 are taken for language prefixes")])
                continue
            site, state = self.site_lines(path, details)
            longer = sorted(p for p in (paths or ()) if p.startswith(path) and p != path)[:3] if paths else []
            if state.get("now") == 200:
                self.add("sitemap-404-now-ok:" + path, INFO, tr("{n} answers 404 on {url} (sitemap page), but it answers 200 now").format(n=n, url=raw(url)), n, site + refs,
                         tr("the 404 were temporary: the page was published or restored since, or Odoo was restarting"), [tr("nothing to do")])
                continue
            if longer:
                self.add("sitemap-404-truncated:" + path, LOOK, tr("404 on {url}: beginning of a real page, a truncated link").format(url=raw(url)), n,
                         [tr("Pages of the sitemap that start the same way: ") + " ; ".join(raw(p) for p in longer)] + site + refs,
                         tr("a link cut in an e-mail, a message or a post"),
                         [tr("correct the link at its source (see the referers); optional: a 301 redirect to the full page (Website > Configuration > Redirects)")])
                continue
            cause, advice = self.record_cause(state)
            self.add("sitemap-404:" + path, LOOK, tr("{n} answers 404 on {url}, a page listed in sitemap.xml").format(n=n, url=raw(url)), n, site + refs,
                     cause or tr("the page was deleted, unpublished or renamed while the sitemap or a link still lists it"),
                     advice or [tr("publish the page again, or add a 301 redirect to its replacement (Website > Configuration > Redirects)"),
                                tr("then correct the menus and links that point to it (see the referers)")])

    def record_cause(self, state):
        """(cause, advice) from the record found in Odoo for a page answering 404; ("", []) when nothing is known."""
        tr = self.tr
        rec, rewrite = state.get("record") or {}, state.get("rewrite")
        if rewrite:
            return (tr("a redirect is defined in Odoo for this address, but the visitors still get 404: the redirect may point to a page that does not exist either"),
                    [tr("check the target of the redirect (Website > Configuration > Redirects)")])
        if rec.get("kind") == "missing":
            return (tr("the record was deleted while links still point to it"),
                    [tr("add a 301 redirect to its replacement (Website > Configuration > Redirects), or leave the 404 if it is gone for good")])
        if rec.get("kind") in ("event", "product", "page") and not rec.get("published"):
            return (tr("the record exists but is not published: Odoo answers 404 to visitors"),
                    [tr("publish it again if it should be visible, or add a 301 redirect to its replacement")])
        if rec.get("kind") in ("event", "product") and not rec.get("active"):
            return (tr("the record is archived: Odoo answers 404 to visitors"), [tr("restore it, or add a 301 redirect to its replacement")])
        if rec.get("kind") == "no-page" and rec.get("similar"):
            return (tr("the page was renamed or replaced: a similar page exists"), [tr("add a 301 redirect to the similar page (Website > Configuration > Redirects)")])
        return "", []

    # --- repeated 4xx outside the sitemap -----------------------------------------------------------------------------------------
    def rule_repeated_4xx(self, facts, details):
        tr, raw = self.tr, self.raw
        nginx = details.get("nginx") or {}
        gone = {u.split("?", 1)[0] for u in (facts.get("gone_404") or {})}
        by_path = Counter()
        for url, n in (facts.get("plain_4xx") or {}).items():
            by_path[url.split("?", 1)[0]] += n
        for path, n in by_path.most_common(8):
            if path in gone or n < 3:
                continue
            detail = nginx.get(path) or {}
            codes = Counter(detail.get("codes") or {})
            if not codes:
                for url, c in (facts.get("codes_by_url") or {}).items():
                    if url.split("?", 1)[0] == path:
                        codes.update(c)
            n404 = codes.get("404", 0) + codes.get("410", 0)
            evidence = [self.codes_line(codes)] + self.referer_lines(detail, facts) + (self.origin_lines(detail) if n404 else [])
            agents = Counter(detail.get("agents") or {})
            if REGISTRATION_SUCCESS_RE.search(path) and n404:
                self.registration_success(path, n404, detail, evidence, details.get("registrations"))
                continue
            if path.rstrip("/").endswith("sitemap.xml") and not WP_SITEMAP_RE.search(path):
                refused = {str(c) for c in codes if str(c)[:1] in ("4", "5")}          # 1.4: the 200 of the visitors and of the program itself do not count
                if refused and refused <= {"403"}:
                    self.add("sitemap-xml-403", INFO, tr("sitemap.xml refused (403) to robots of the blocking list"), n, evidence,
                             tr("bot_blocker.conf refuses these robots: expected"), [tr("nothing to do, unless a search engine you want is refused")])
                else:
                    self.add("sitemap-xml-4xx", LOOK, tr("sitemap.xml answers {codes}").format(codes=", ".join(sorted(str(c) for c in codes if str(c)[:1] == "4")) or "4xx"), n,
                             evidence + ([tr("User-Agents: ") + " ; ".join(f"{raw(a)} ×{k}" for a, k in agents.most_common(3))] if agents else []),
                             tr("Odoo builds sitemap.xml for the domain of the website: a request for another host name, or nginx not passing it to Odoo"),
                             [tr("check the domain of the website (Website > Configuration > Settings > Domain) and that nginx sends /sitemap.xml to Odoo"),
                              tr("open https://YOUR-SITE/sitemap.xml in a browser: it must answer 200")])
                continue
            if codes and not n404:
                continue                                                # 403 / 405 / 499...: robots refused, clients gone: not a dead page
            count = n404 or n
            if WP_SITEMAP_RE.search(path):
                self.add("wp-sitemap:" + path, INFO, tr("{n} answers 404 on {url}: a WordPress sitemap name").format(n=count, url=raw(path)), count, evidence,
                         tr("robots look for the sitemap of a WordPress site (Yoast, WordPress): Odoo's is /sitemap.xml"),
                         [tr("nothing to fix; optional: a 301 redirect from this address to /sitemap.xml (Website > Configuration > Redirects)")])
                continue
            site, state = self.site_lines(path, details)
            if state.get("now") == 200:
                self.add("dead-link-now-ok:" + path, INFO, tr("{n} answers 404 on {url}, but it answers 200 now").format(n=count, url=raw(path)), count, evidence + site,
                         tr("the 404 were temporary: the page was published or restored since, or Odoo was restarting"), [tr("nothing to do")])
                continue
            inside = internal_referers(detail, facts.get("site_hosts") or ())
            cause, advice = self.record_cause(state)
            if cause:
                severity = LOOK
            elif inside and self.origin_kind(detail) == "nginx":
                cause = tr("nginx refuses an address that the site itself offers: a rule of nginx is too strict, or the nginx configuration is not up to date")
                advice = [tr("sudo nginx-hardening.sh --update (installs the latest rules of nginx/), then run this analysis again"),
                          tr("if it still answers 404: find the rule with sudo nginx -T | grep -n 'return 404' and the address in the access log")]
                severity = LOOK
            elif inside:
                cause = tr("a link of the site itself points to a page that no longer answers")
                severity = LOOK
            elif SHOP_EVENT_RE.search(path):
                cause = tr("product or event unpublished, archived or renamed, still reached from search engines or old links")
                severity = LOOK if count >= 5 else INFO
            else:
                cause = tr("old or mistyped link; not in sitemap.xml, so not counted in the health")
                severity = LOOK if count >= 10 else INFO
            if inside and self.origin_kind(detail) != "nginx":
                advice = advice + [tr("correct the link in the page that holds it (Linked from the site itself)")]
            advice = advice or [tr("add a 301 redirect to the replacement page (Website > Configuration > Redirects), or publish it again")]
            self.add("dead-link:" + path, severity, tr("{n} answers 404 on {url}").format(n=count, url=raw(path)), count, evidence + site, cause, advice)

    def registration_success(self, path, count, detail, evidence, regs):
        """1.5: 404 on the confirmation page of an event registration. Odoo 18 shows it only to the visitor (cookie) who registered and answers 404 to anybody else, even
        when the registration exists. `regs` = what app-log-live.py read in the database for the registration_ids of these links (None: database not readable)."""
        tr, raw = self.tr, self.raw
        evidence = list(evidence)
        browsers = detail.get("browser_hits") or 0
        if regs and regs.get("asked"):
            evidence.append(tr("Registrations of these links in Odoo: {found} found of {asked}, {nov} with no visitor recorded (no cookie at the registration)").format(
                found=regs["found"], asked=regs["asked"], nov=regs["no_visitor"]))
            if regs.get("duplicates"):
                evidence.append(tr("{n} people registered several times for the same event (to check: a new try after the 404, or the form sent twice)").format(n=regs["duplicates"]))
        if not browsers:
            self.add("registration-404:" + path, INFO, tr("{n} answers 404 on {url}: confirmation page opened by robots or link previews").format(n=count, url=raw(path)), count, evidence,
                     tr("Odoo shows the confirmation of a registration only to the visitor who registered (cookie): a robot or a link preview has none"),
                     [tr("nothing to do")])
            return
        advice = [tr("rlq-odoo-addons: show a thank-you page (the confirmation e-mail was sent) instead of the 404 when the visitor is unknown"),
                  tr("check the cookies bar of the website (Website > Configuration > Settings): without the cookie, Odoo cannot recognise the visitor"),
                  tr("Events > Registrations: look for the same e-mail registered twice for the same event")]
        if regs and regs.get("found") and not regs.get("no_visitor"):
            cause = tr("the registrations were made WITH a visitor, but Odoo does not recognise it when the page is opened again: cookie replaced (sign-in, another browser or device, in-app browser) or page reopened later")
        else:
            cause = tr("the registration exists, but Odoo shows its confirmation only to the visitor (cookie) who made it: private browsing, blocked cookies or another browser give a 404")
        self.add("registration-404:" + path, LOOK, tr("{n} answers 404 on {url}: confirmation page of a registration").format(n=count, url=raw(path)), count, evidence,
                 cause, advice)

    # --- Odoo errors ---------------------------------------------------------------------------------------------------------------
    def rule_odoo_errors(self, facts, details):
        tr, raw = self.tr, self.raw
        traces = details.get("tracebacks") or {}
        merged = {}
        for e in facts.get("odoo_errors") or ():
            level, logger, message, n = e["level"], e["logger"] or "", e["message"] or "", e["n"]
            if NGINX_TAG_RE.match(message):
                continue                                                # a line of the nginx error log: rule_nginx_upstream
            text = f"{logger}: {message}"
            known = next((k for k in KNOWN_MESSAGES if re.search(k[0], text, re.I)), None)
            if level not in ("ERROR", "CRITICAL") and not known:
                continue                                                # unknown warnings: the dashboard lists them, no advice here
            trace = traces.get((level, logger, message)) or []
            parsed = parse_traceback(trace)
            key = (level, logger, known[0] if known and known[1] == INFO else message, parsed.get("exception") if parsed else "")
            m = merged.setdefault(key, {"e": e, "n": 0, "known": known, "parsed": parsed, "trace": trace, "messages": Counter()})
            m["n"] += n
            m["messages"][message] += n
            if (e.get("last") or 0) > (m["e"].get("last") or 0):
                m["e"] = e
        for (level, logger, _k, _x), m in merged.items():
            e, n, known, parsed = m["e"], m["n"], m["known"], m["parsed"]
            message = e["message"] or ""
            when = e.get("when") or ""
            evidence = [f"{level} {raw(logger)} ×{n} : {raw(_cut(message, 160))}" + (" (" + tr("last on {when}").format(when=when) + ")" if when else "")]
            if len(m["messages"]) > 1:
                evidence.append(tr("{k} variants of the message (numbers or versions differ)").format(k=len(m["messages"])))
            example = (e.get("raw") or "").strip()
            if example and re.sub(r"(?<![A-Za-z\d])\d+", "N", example)[:200] != example[:200]:      # 1.7: the real line, the grouped one has N for the numbers
                evidence.append(tr("Example as written in the log: ") + raw(_cut(example, 220)))
            severity = PROBLEM if level == "CRITICAL" or n >= 5 else LOOK
            cause, advice = "", []
            if known:
                severity = min(severity, known[1]) if known[1] == INFO else severity
                cause, advice = tr(known[2]), [tr(known[3])]
            counts = (details.get("exceptions") or {}).get((level, logger, message)) or Counter()
            if len(counts) > 1:
                evidence.append(tr("Exceptions of all the occurrences: ") + " ; ".join(f"{raw(x)} ×{k}" for x, k in counts.most_common(4)))
            elif counts:
                evidence.append(tr("All the occurrences read end with the same exception ({k})").format(k=sum(counts.values())))
            if parsed:
                evidence.append(tr("Exception of the last occurrence: ") + raw(_cut(parsed["exception"] + (": " + parsed["message"] if parsed["message"] else ""), 200)))
                if parsed["module"]:
                    evidence.append(tr("Module of the last frame: {module} ({frame})").format(module=raw(parsed["module"]), frame=raw(parsed["frame"])))
                hint = next((h for h in TRACEBACK_HINTS if re.search(h[0], parsed["exception"] + " " + parsed["message"])), None)
                if hint and len(counts) > 1 and counts.most_common(1)[0][0].split(":", 1)[0] != parsed["exception"].rsplit(".", 1)[-1]:
                    hint = None                                         # the last occurrence is not the usual one: no cause drawn from it
                if hint:
                    cause, advice = tr(hint[1]), [tr(hint[2])]
                    if "werkzeug" in parsed["exception"] and severity < PROBLEM:
                        severity = INFO
                    if "Vapid" in parsed["exception"] or "VAPID" in parsed["message"]:
                        severity = INFO if n < 50 else LOOK
                        vapid = details.get("vapid")
                        if vapid:
                            evidence.append(tr("Key stored in Odoo: written on {when}").format(when=raw(vapid)))
                elif known and "Exception during request handling" in known[0]:
                    cause = tr("an exception in the module named above, while handling a request")
                    advice = [tr("update the module {module}, or report the exception to its author with the traceback (key E)").format(module=raw(parsed.get("module") or "?"))]
            elif level in ("ERROR", "CRITICAL") and (not known or known[1] != INFO):
                evidence.append(tr("Traceback not found in the logs read (logfile or systemd journal around this time)"))
                advice.append(tr("key E shows the complete traces (app-log-check.py --errors-only --full-trace)"))
            if not cause:
                cause = tr("an error of Odoo not yet known to this analysis")
                advice = advice or [tr("key E for the traceback; then fix or update the module concerned")]
            if parsed:
                signature = parsed["exception"] + ": " + parsed["message"]
                if signature in getattr(self, "server_exceptions", ()) and signature not in getattr(self, "visitor_exceptions", ()):
                    severity, cause = INFO, tr("the same exception as the HTTP 5xx made by this server itself (tests): no visitor was affected")
                    advice = [tr("nothing to do")]
            title = parsed["exception"].rsplit(".", 1)[-1] if parsed else _cut(message, 90)
            fid = "odoo:" + logger + ":" + (parsed["exception"] if parsed else re.sub(r"\s+", " ", message)[:80])
            self.add(fid, severity, tr("Odoo {level}: {message}").format(level=level, message=raw(title)), n, evidence, cause, advice)

    # --- conflicts ---------------------------------------------------------------------------------------------------------------
    def rule_conflicts(self, facts, details):
        tr = self.tr
        final = facts.get("final_failures") or 0
        if final:
            self.add("final-conflicts", PROBLEM if final >= 3 else LOOK, tr("Final failures of concurrent updates: {n}").format(n=final), final,
                     [", ".join(f"{c} ×{k}" for c, k in Counter(facts.get("failure_codes") or {}).most_common(3))],
                     tr("Odoo gave up after 5 tries: two writers on the same record (scheduled action and users, or the same user on several devices)"),
                     [tr("find the record in the traceback that follows in the log; spread the scheduled actions that write the same model")])
        retried = facts.get("conflicts") or 0
        if retried >= 50:
            self.add("many-retries", INFO, tr("Many retried update conflicts: {n}").format(n=retried), retried, [],
                     tr("often the same user on several devices, or a very busy chat channel"), [tr("nothing to do while the final failures stay at zero")])

    # --- push subscriptions already registered (1.7) -----------------------------------------------------------------------------------
    def rule_push_duplicates(self, facts, details):
        tr = self.tr
        n, warnings = facts.get("push_duplicates") or 0, facts.get("push_duplicate_warnings") or 0
        if not n and not warnings:
            return
        evidence = [tr("Lines « bad query » on mail_push_device: {n} · warnings « endpoint must be unique »: {w}").format(n=n, w=warnings)]
        times = facts.get("push_times") or []
        if len(times) == 2:
            evidence.append(tr("First at {first}, last at {last}").format(first=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(times[0])),
                                                                         last=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(times[1]))))
        evidence.append(tr("PostgreSQL error: unique violation (constraint mail_push_device_endpoint_unique), not a concurrent update conflict: Odoo does not retry it and nothing is lost"))
        after = facts.get("push_after_conflict") or 0
        if after:
            # 1.8: on PROD, 15 push duplicates and 15 retried conflicts: two tabs subscribe at the same moment, one waits (conflict retried), then finds the
            # subscription the other one just wrote (duplicate)
            evidence.append(tr("{k} of them came less than 5 s after a retried conflict: two tabs or devices subscribed at the same moment; the second one, retried by Odoo, found the subscription the first had just written").format(k=after))
        advice = [tr("nothing to do; counted apart since app-log-live.py 1.178 (before: Odoo errors, and the health showed « problem »)")]
        if n + warnings >= 100:
            advice.append(tr("many times: one browser subscribes again in a loop; the person can clear the site data of the browser (or block the notifications of the site)"))
        self.add("push-duplicates", INFO, tr("Push subscriptions already registered (harmless): {n}").format(n=max(n, warnings)), max(n, warnings), evidence,
                 tr("a browser subscribed again to the push notifications with an endpoint Odoo already holds: PostgreSQL refuses the copy (unique constraint), the existing subscription stays valid"),
                 advice, confirmed=True)

    # --- e-mails: the database decides ---------------------------------------------------------------------------------------------
    def mail_hints(self, text):
        """1.7: the solution tracks that match a failure reason (several may apply), most specific first."""
        return [h for pattern, h in SMTP_HINTS if re.search(pattern, text or "", re.I)]

    def rule_mails(self, facts, details):
        tr, raw = self.tr, self.raw
        n_log = facts.get("mails") or 0
        db = details.get("mail_db")
        if db is None:
            if not n_log:
                return
            texts = " ".join(e.get("message", "") for e in facts.get("odoo_errors") or ())
            hints = [tr(h) for h in self.mail_hints(texts)]
            self.add("mail-failures", PROBLEM if n_log >= 3 else LOOK, tr("Failed e-mails (journal): {n}").format(n=n_log), n_log,
                     hints + [tr("Database not read (run with sudo): the count comes from the journal lines only")],
                     tr("the mail server refused or could not be reached"),
                     [tr("odoo-mail-retry.py lists the unsent e-mails and offers to resend them; app-log-check.py explains the causes")], fix=("mail", None))
            return
        failed = db.get("exception", 0)
        waiting = db.get("outgoing", 0)
        evidence = [tr("Database, last {nd} days: {failed} in failure, {waiting} waiting, {sent} sent").format(
            nd=db.get("days", "?"), failed=failed, waiting=waiting, sent=db.get("sent", 0))]
        listed = details.get("mail_failed") or []
        if not listed:
            evidence += [tr("Cause: ") + f"{raw(_cut(r, 140))} ×{k}" for r, k in (db.get("reasons") or [])[:3]]
        reasons_text, generic_only = [], True
        for c in listed:
            # 1.7: each failed e-mail: date and time, subject, recipients and the FULL reason recorded by Odoo
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("instant") or 0))
            reason = (c.get("raison") or "").strip()
            reasons_text.append(reason)
            if reason and not GENERIC_MAIL_REASON_RE.match(reason):
                generic_only = False
            recipients = [r for r in re.split(r"\s*[,;]\s*", c.get("destinataires") or "") if r]
            evidence.append(tr("{when} · subject « {subject} » · to: {to}").format(when=when, subject=raw(_cut(c.get("sujet") or tr("(no subject)"), 90)),
                                                                               to=raw(_cut(c.get("destinataires") or tr("(unknown recipient)"), 120)))
                            + (" (" + tr("{n} recipients").format(n=len(recipients)) + ")" if len(recipients) > 3 else "")
                            + (" [" + raw(c["base"]) + "]" if len({x.get("base") for x in listed}) > 1 and c.get("base") else "")
                            + (" · " + tr("before the window, still not resent") if facts.get("start") and (c.get("instant") or 0) < facts["start"] else ""))
            evidence.append("    " + tr("Reason: ") + raw(_cut(reason or tr("(none recorded)"), 240)))
        servers = details.get("mail_servers") or []
        if servers:
            evidence.append(tr("Outgoing mail servers of Odoo: ") + " ; ".join(
                f"n° {x.get('id')} « {raw(x.get('nom') or '')} » {raw(str(x.get('hote')))}:{x.get('port')} ({raw(x.get('chiffrement') or 'none')})"
                + (" " + tr("FROM filter: {f}").format(f=raw(x["filtre"])) if x.get("filtre") else "") + ("" if x.get("actif", True) else " " + tr("(inactive)"))
                for x in servers))
        elif db.get("servers"):
            evidence.append(tr("Outgoing mail servers of Odoo: ") + " ; ".join(raw(x) for x in db["servers"]))
        params = details.get("params") or {}
        shown = [(k, params[k]) for k in ("mail.session.batch.size", "mail.mail.queue.batch.size", "mail.mail.force.send.limit") if k in params]
        if shown:
            # 1.10: the values an administrator would otherwise look up in Settings > Technical > System Parameters
            evidence.append(tr("Odoo parameters now: ") + " · ".join(f"{k} = {v}" + ("" if is_set else " " + tr("(not set: Odoo default)")) for k, (v, is_set) in shown))
        same = Counter((str(x.get("hote")), str(x.get("port"))) for x in servers if x.get("actif", True))
        doubles = [hp for hp, k in same.items() if k > 1]
        if failed:
            joined = " ".join(reasons_text) or " ".join(r for r, _k in db.get("reasons") or ())
            hints = []
            for h in self.mail_hints(joined):
                if tr(h) not in hints:
                    hints.append(tr(h))
            if listed and generic_only:
                hints.append(tr("the reason recorded by Odoo is only the generic message: the SMTP answer is in the Odoo log at that time (key E, or app-log-check.py --errors-only around the time above)"))
            if doubles:
                hints.append(tr("{k} outgoing servers for {host}: Odoo takes the first one (sequence) whose FROM filter matches the sender; check that the other one is not an old copy with a wrong password, then archive it").format(
                    k=same[doubles[0]], host=raw(":".join(doubles[0]))))
            hints.append(tr("once the cause is fixed: odoo-mail-retry.py lists these e-mails and offers to resend them"))
            self.add("mail-failures", PROBLEM if failed >= 3 else LOOK, tr("Failed e-mails: {n}").format(n=failed), failed, evidence,
                     tr("the mail server refused these e-mails (see the reason of each one above)"), hints, fix=("mail", db.get("days")), confirmed=bool(listed))
        elif n_log:
            self.add("mail-failures-not-confirmed", INFO, tr("Failed e-mails in the journal not confirmed: the database has none"), n_log, evidence,
                     tr("the journal lines counted were not failures of Odoo's mail queue"), [tr("nothing to do")])
        if waiting >= 20:
            self.add("mail-queue", LOOK, tr("E-mails waiting to be sent: {n}").format(n=waiting), waiting, evidence[:1],
                     tr("the scheduled action that sends the e-mails is late or stopped (Mail: Email Queue Manager)"),
                     [tr("check that the scheduled action « Mail: Email Queue Manager » is active, and the cron threads of odoo.conf (max_cron_threads)")])

    # --- slow requests -----------------------------------------------------------------------------------------------------------
    def rule_slow(self, facts, details):
        tr, raw = self.tr, self.raw
        slow = [s for s in (facts.get("slow") or []) if not LONG_CONNECTION_RE.search(s.get("url") or "")]          # 1.4: a websocket is open for hours: not slow
        if not slow:
            return
        t_sql = sum(s.get("t_sql") or 0 for s in slow)
        t_py = sum(s.get("t_py") or 0 for s in slow)
        cold = sum(1 for s in slow if COLD_RE.search(s.get("url") or ""))
        pages = Counter(s.get("url", "").split("?", 1)[0] for s in slow)
        evidence = [tr("Pages: ") + " ; ".join(f"{raw(u)} ×{k}" for u, k in pages.most_common(3))]
        if t_sql + t_py > 0:
            evidence.append(tr("Time in SQL {sql} %, outside SQL {py} % (Python computation, templates, waiting for a lock or for the processor)").format(
                sql=round(100 * t_sql / (t_sql + t_py)), py=round(100 * t_py / (t_sql + t_py))))
        slowest = max((s.get("total") or 0) for s in slow)
        hours = Counter(time.strftime("%Y-%m-%d %Hh", time.localtime(s["t"])) for s in slow if s.get("t"))
        if hours:
            top = hours.most_common(3)
            evidence.append(tr("Busiest hours: ") + " ; ".join(f"{h} ×{k}" for h, k in top) + " (" + tr("the slowest: {s} s").format(s=f"{slowest:.1f}") + ")")
        who = facts.get("who") or {}
        for x in sorted(slow, key=lambda x: -(x.get("total") or 0))[:5]:
            # 1.7: each slow request: when, how long, who, where the time went
            action = CALL_BUTTON_RE.search(x.get("url") or "")
            evidence.append("    " + (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x["t"])) + " · " if x.get("t") else "") + f"{x.get('total') or 0:.1f} s · "
                            + raw(_cut(x.get("url") or "", 80)) + " · " + raw(who.get(x.get("ip"), x.get("ip") or "?"))
                            + " · " + tr("SQL {sql} s ({n} queries), Python {py} s").format(sql=f"{x.get('t_sql') or 0:.1f}", n=x.get("sql_n") or 0, py=f"{x.get('t_py') or 0:.1f}")
                            + (" · " + tr("action {method} of the model {model}").format(method=raw(action.group(2)), model=raw(action.group(1))) if action else ""))
        timed = sorted((x["t"], (x.get("url") or "").split("?", 1)[0]) for x in slow if x.get("t"))
        # 1.15: the largest group inside ONE window of SIMULTANEOUS_S seconds. Before, the pairs were chained: PROD 2026-11-09 showed « 16 slow
        # requests on different pages within 73787 s » for groups spread over 20 hours
        together = set()
        for i, (t1, _u1) in enumerate(timed):
            group = {(t, u) for t, u in timed[i:] if t - t1 <= SIMULTANEOUS_S}
            if len({u for _t, u in group}) >= 2 and len(group) > len(together):
                together = group
        if together:
            first, last = min(together)[0], max(together)[0]
            evidence.append(tr("{k} slow requests on different pages within {s} s ({when}): slowed down together, not each page on its own").format(
                k=len(together), s=int(last - first), when=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(first))))
        # 1.14: several requests that END in the same 2 seconds with almost no SQL waited for the same thing outside the database and outside Python
        # computation: reading the disk (images and files of the filestore, files of the modules) or sending the response (DEV 2026-11-09: 4 images,
        # 4 workers, 10 s each, 0.01 s of SQL, ended at 20:35:28; reads of the SATA disks: 160 to 230 ms each, measured by host-perf-audit.py)
        disk_k, disk_when = ended_together([(x["t"], x.get("t_sql") or 0, x.get("t_py") or 0) for x in slow if x.get("t")])
        # 1.16: a static file or an image that takes seconds without SQL: Odoo has nothing to compute, it reads a file (PROD 2026-11-09: 11 of the 20
        # slow requests, 9 to 10 s each, alone or together)
        files = [x for x in slow if FILE_RE.search(x.get("url") or "") and (x.get("t_sql") or 0) < 0.1 * max(0.01, x.get("total") or 0) and (x.get("t_py") or 0) >= 2]
        if len(files) >= 2:
            evidence.append(tr("{k} slow requests are static files or images with almost no SQL (Odoo had nothing to compute: it read a file): ").format(k=len(files))
                            + " ; ".join(raw(_cut(x.get("url") or "", 50)) for x in files[:3]))
        if disk_k:
            evidence.append(tr("{k} slow requests ended in the same 2 seconds ({when}) with almost no SQL: they waited together outside the database").format(
                k=disk_k, when=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(disk_when))))
        # 1.15: slow requests during a backup of the suite (odoo-backup.service: pg_dump and the filestore read the same disks)
        windows, opened = [], None
        for t, text in sorted(details.get("backup_events") or ()):
            if re.search(r"Starting|Started", text):
                opened = t
            elif opened is not None and re.search(r"Finished|Deactivated", text):
                windows.append((opened, t))
                opened = None
        during = [x for x in slow if x.get("t") and any(a - 60 <= x["t"] <= b + 60 for a, b in windows)]
        if during:
            a, b = next((a, b) for a, b in windows if any(a - 60 <= x["t"] <= b + 60 for x in during))
            evidence.append(tr("{k} slow requests during the backup of {start} to {end} (odoo-backup.service: the database and the filestore read on the same disks)").format(
                k=len(during), start=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(a)), end=time.strftime("%H:%M:%S", time.localtime(b))))
        crons = details.get("crons") or []
        if crons:
            evidence.append(tr("Scheduled actions whose last run was around then: ") + " ; ".join(
                f"{time.strftime('%H:%M:%S', time.localtime(t))} {raw(_cut(name, 50))}" for t, name in crons[:5]))
        restarts = [t for t, text in ((details.get("service") or {}).get("events") or []) if re.search(r"Started|Starting", text)]
        after = sum(1 for s in slow if s.get("t") and any(0 <= s["t"] - r <= 600 for r in restarts))
        if restarts:
            evidence.append(tr("{k} of them in the 10 minutes after a start of Odoo ({r} starts in the window)").format(k=after, r=len(restarts)))
        conf = details.get("odoo_conf")
        conf_advice, conf_cause = [], ""
        if conf is not None:
            ev, adv, conf_cause = odoo_settings_advice(conf.get("values") or {}, conf.get("cpus"), conf.get("mem_mb"), slowest)
            evidence += [tr("Settings read in ") + raw(conf.get("path") or "odoo.conf") + " : " + ev[0].split(" : ", 1)[1]] + [tr("Machine: {cpus} processors, {mem} MB of memory").format(
                cpus=conf.get("cpus") or "?", mem=conf.get("mem_mb") or "?")]
            for kind, a, b in adv:
                if kind == "workers0":
                    conf_advice.append(tr("workers=0: Odoo runs in ONE process (threads): a slow request holds the others, and limit_time_* do not apply; set workers to {best} at most for this processor count (the memory allows about {mem} workers)").format(best=a or "2 x CPU + 1", mem=b or "?"))
                elif kind == "too-many":
                    conf_advice.append(tr("workers={now} is more than (2 x CPU) + 1 = {best}: the workers fight for the processor and each request gets slower; lower workers to {best}").format(now=b, best=a))
                elif kind == "few":
                    conf_advice.append(tr("workers={now} for this machine: up to {best} workers are possible (Odoo guide: (2 x CPU) + 1, and what the memory holds at limit_memory_hard 1536 MB, as nginx-hardening.sh step 6)").format(now=b, best=a))
                elif kind == "memory":
                    conf_advice.append(tr("the workers may need about {need} MB, close to the {mem} MB of the machine: add memory or lower workers").format(need=a, mem=b))
                elif kind == "limit-real":
                    if a > b:
                        conf_advice.append(tr("the slowest request took {s} s, more than limit_time_real={limit} s: Odoo stops such a request (the visitor gets an error), unless it is a long connection (websocket)").format(s=a, limit=b))
                    else:
                        conf_advice.append(tr("the slowest request took {s} s, close to limit_time_real={limit} s: beyond it, Odoo stops the request (the visitor gets an error)").format(s=a, limit=b))
        if cold >= 2 and 2 * cold >= len(slow) or (restarts and after * 2 >= len(slow)):
            cause = tr("cold cache after a restart or an update: assets and views computed once")
            advice = [tr("odoo-warmup.py right after each restart or update of Odoo (odoo-update-module.sh does it)")]
            fix = ("warmup", None)
        elif during and 2 * len(during) >= len(slow):
            cause = tr("the backup of the suite was running: pg_dump and the copy of the filestore read the same disks as Odoo")
            advice = [tr("move the backup to a quieter hour (odoo-backup.timer), or give the disks more speed (SSD for PostgreSQL and the filestore)"),
                      tr("nothing to do if it happens only during the backup at night")]
            fix = None
        elif t_sql > t_py and together and 2 * len(together) >= len(slow):
            # 1.7: several pages slow at the same moment: the database was busy or locked for everyone, an index would not change it
            cause = tr("several pages slow at the same moment: PostgreSQL was busy or held by a lock (scheduled action, backup, autovacuum), not a missing index on each page")
            advice = [tr("look at what ran at that time (scheduled actions above, backup, ZFS snapshots); if it repeats at the same hour, move that task"),
                      tr("to see the locks next time: log_lock_waits = on and log_min_duration_statement = 2000 in postgresql.conf (reload PostgreSQL)")]
            fix = None
        elif (disk_k and 2 * disk_k >= len(slow)) or (len(files) >= 2 and 2 * len(files) >= len(slow)):
            cause = tr("waiting for the disk: several requests ended together with almost no SQL and no computation to do (images, files): reading the filestore or the files of the modules on slow disks, or writing a temporary file")
            advice = [tr("host-perf-audit.py on the Proxmox host (read wait of the disks; --duration 24h): above about 20 ms per read, the disks are the limit"),
                      tr("nginx-hardening.sh --update: cache of the images of Odoo and temporary files of nginx in memory; on the host: an SSD for the filestore and PostgreSQL (ZFS: special vdev or L2ARC)")]
            fix = None
        elif t_sql > t_py:
            cause = tr("the database: heavy searches, missing indexes or tables to clean")
            advice = [tr("odoo-sql-maint: VACUUM ANALYZE and the index checks"), tr("look at the filters and the number of records of the slow pages")]
            fix = None
        else:
            cause = tr("time spent outside the database: heavy pages, too few or too many workers for the processor, or the machine busy with something else at these hours")
            advice = conf_advice or [tr("app-health-check.py: workers, memory, processor")]
            if not conf_advice and conf is None:
                advice.append(tr("odoo.conf not read (run with sudo): workers, limit_time_cpu and limit_time_real not checked"))
            advice.append(tr("host-perf-audit.py on the Proxmox host during the busy hours above: is the processor or the disk the limit?"))
            fix = None
        if conf_advice and advice is not conf_advice:
            advice = advice + [a for a in conf_advice if a not in advice]
        n = len(slow)
        # 1.15: the probes of this server (app-health-check.py measures a cold Odoo just after its start) and the cold cache after a start are said,
        # not counted in the severity: DEV 2026-11-09 showed « ✖ Slow requests: 6 » for 6 probes of /en_CA/web/login after restarts
        server = set(facts.get("server_ips") or ()) | {"127.0.0.1", "::1"}
        real = [x for x in slow if x.get("ip") not in server and not (x.get("t") and any(0 <= x["t"] - r <= 600 for r in restarts))]
        if during:
            real = [x for x in real if x not in during] if len(during) * 2 >= len(slow) else real
        k = len(real)
        severity = PROBLEM if k >= 5 else LOOK if k else INFO
        if k < n:
            evidence.append(tr("Counted in the severity: {k} of {n} (left out: the probes of this server and the cold cache in the 10 minutes after a start of Odoo)").format(k=k, n=n))
        self.add("slow-requests", severity, tr("Slow requests: {n}").format(n=n), n, evidence, cause, advice, fix=fix)

    # --- memory risk (1.7) ----------------------------------------------------------------------------------------------------------
    def rule_memory(self, facts, details):
        tr, raw = self.tr, self.raw
        conf = details.get("odoo_conf")
        memory = details.get("memory") or {}
        if not conf:
            return
        values = conf.get("values") or {}

        def number(key):
            try:
                return int(float((values.get(key) or "").strip()))
            except ValueError:
                return None
        workers = number("workers") if number("workers") is not None else ODOO_DEFAULTS["workers"]
        if not workers:
            return                                                  # one process: limit_memory_* do not apply
        cron = number("max_cron_threads") if number("max_cron_threads") is not None else ODOO_DEFAULTS["max_cron_threads"]
        hard = (number("limit_memory_hard") or ODOO_DEFAULTS["limit_memory_hard"] * 1048576) // 1048576
        soft = (number("limit_memory_soft") or ODOO_DEFAULTS["limit_memory_soft"] * 1048576) // 1048576
        total = memory.get("limit_mb") or conf.get("mem_mb")
        if not total:
            return
        # 1.11: Odoo compares limit_memory_soft with the VIRTUAL memory of a worker and limit_memory_hard is RLIMIT_AS (virtual too); the RAM really taken
        # is the RSS, about VIRTUAL - overhead (shared libraries, reservations: about 400 MB on Odoo 18). Before, the virtual limits were shared as if they
        # were RAM: PROD (13 workers) got limit_memory_soft = 652 MB, under the 660 MB of a worker at rest, and every worker was recycled at birth.
        plan = memory_plan(total, memory.get("other_mb"), workers, cron, memory.get("worker_vms_mb"), memory.get("worker_overhead_mb"))
        overhead, idle = plan["overhead"], plan["idle_vms"]
        worst = (workers + cron) * max(0, hard - overhead)
        self._gevent_limits(number, soft, hard, memory, total, plan)
        self._memory_low_now(memory, total, workers, plan)
        born = memory.get("recycled_at_birth") or 0
        if soft <= idle or born >= 3:
            evidence = [tr("limit_memory_soft {s} MB, a worker at rest already uses {v} MB of virtual memory{measured}").format(
                s=soft, v=idle, measured=tr(" (measured now)") if memory.get("worker_vms_mb") else tr(" (usual value for Odoo 18)"))]
            if born:
                evidence.append(tr("Workers stopped before their first request (« request_count: 0 ») in the Odoo log of the period: {n}").format(n=born))
            self.add("memory-limit-too-low", PROBLEM, tr("Odoo workers recycled at birth: limit_memory_soft is under the memory of a worker at rest"), max(1, born), evidence,
                     tr("Odoo compares limit_memory_soft with the VIRTUAL memory of the process: under the size of a worker at rest, each worker stops just after starting, Odoo starts another one, in a loop; the requests wait or fail"),
                     [tr("in odoo.conf (values in bytes): limit_memory_soft = {sb} ({s} MB) and limit_memory_hard = {hb} ({h} MB), then restart Odoo").format(
                         sb=plan["soft"] * 1048576, s=plan["soft"], hb=plan["hard"] * 1048576, h=plan["hard"]),
                      tr("these limits are virtual memory: about {o} MB more than the RAM really used by a worker").format(o=overhead)],
                     confirmed=bool(born))
        oom = memory.get("kernel") or []
        kills = memory.get("oom_kills")
        if worst <= 0.8 * total and not oom and not kills and not plan["too_many"]:
            return
        evidence = [tr("Worst case of the Odoo processes: ({w} workers + {c} cron) × (limit_memory_hard {h} MB - {o} MB of virtual memory without RAM) = {worst} MB, for {total} MB of memory{where}").format(
            w=workers, c=cron, h=hard, o=overhead, worst=worst, total=total, where=tr(" (limit of this container)") if memory.get("limit_mb") else ""),
            tr("At limit_memory_soft ({s} MB each, where Odoo recycles a worker): {total_soft} MB; PostgreSQL and the system need memory too").format(
                s=soft, total_soft=(workers + cron) * max(0, soft - overhead))]
        if kills:
            evidence.append(tr("Processes killed for lack of memory in this container since its start (memory.events): {n}").format(n=kills))
        if oom:
            evidence.append(tr("Kernel messages about the memory: ") + " ; ".join(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))} {raw(_cut(text, 90))}" for t, text in oom[:3]))
        if memory.get("other_mb") is not None:
            evidence.append(tr("Used outside Odoo now: {other} MB (reserve kept: {reserve} MB)").format(other=memory["other_mb"], reserve=plan["reserve"]))
        advice = [tr("set limit_memory_hard to about {hard} MB and limit_memory_soft to about {soft} MB in odoo.conf ({budget} MB of RAM shared by {w} workers + {c} cron + 1 gevent, + {o} MB of virtual memory each, as nginx-hardening.sh step 6), then restart Odoo").format(
                      hard=plan["hard"], soft=plan["soft"], budget=plan["budget"], w=workers, c=cron, o=overhead)]
        if plan["too_many"]:
            advice.append(tr("the memory is too short for {w} workers at these limits: about {m} workers at most").format(w=workers, m=plan["max_workers"]))
        if plan["ram_needed"] > total:
            advice.append(tr("or add about {gb} GB of memory to this server ({need} MB in all; Proxmox: memory of the container) to keep {w} workers at limit_memory_hard {c} MB, with room for big reports and exports").format(
                gb=-(-(plan["ram_needed"] - total) // 1024), need=plan["ram_needed"], w=workers, c=COMFORT_HARD_MB))
        else:
            advice.append(tr("or lower workers, or give more memory to this server (Proxmox: memory of the container)"))
        severity = PROBLEM if oom or kills else (LOOK if worst > total or plan["too_many"] else INFO)
        title = (tr("Memory risk: the Odoo processes may use more than the memory of the server") if worst > total
                 else tr("Too many Odoo workers for the memory of the server") if plan["too_many"] and worst <= 0.8 * total
                 else tr("Memory nearly full in the worst case of the Odoo processes"))
        self.add("memory-risk", severity, title, 1, evidence,
                 tr("if every worker reaches limit_memory_hard at the same time, the server runs out of memory and the kernel kills a process (Odoo or PostgreSQL): the site stops")
                 + ("" if not (oom or kills) else " " + tr("(it already happened: see the lines above)")), advice, confirmed=bool(oom or kills))

    def _gevent_limits(self, number, soft, hard, memory, total, plan):
        """1.12: the gevent process (live chat, notifications: one websocket per open Odoo tab) has the limits of the workers when limit_memory_soft_gevent /
        limit_memory_hard_gevent are not set (odoo/service/server.py: limit_memory_soft_gevent or limit_memory_soft). Its memory grows with the number of
        people connected at the same time; at the limit it restarts and every discussion is cut for a few seconds."""
        tr = self.tr
        soft_g = (number("limit_memory_soft_gevent") or 0) // 1048576 or None
        hard_g = (number("limit_memory_hard_gevent") or 0) // 1048576 or None
        restarts = memory.get("gevent_restarts") or 0          # 1.15: since the start of the running Odoo (app-log-live.py 1.187)
        want_soft, want_hard = GEVENT_SOFT_MB, GEVENT_HARD_MB
        if (soft_g or soft) >= GEVENT_SOFT_MB and (hard_g or hard) >= GEVENT_HARD_MB:
            if not restarts:
                return
            # 1.15: already at the recommended values and still restarted since the start: half as much again (PROD 2026-11-09 repeated 2048 / 2560)
            want_soft, want_hard = (soft_g or soft) * 3 // 2, (hard_g or hard) * 3 // 2
        now = tr("limit_memory_soft_gevent {s}, limit_memory_hard_gevent {h}").format(
            s=f"{soft_g} MB" if soft_g else tr("not set (limit_memory_soft: {v} MB)").format(v=soft),
            h=f"{hard_g} MB" if hard_g else tr("not set (limit_memory_hard: {v} MB)").format(v=hard))
        evidence = [now]
        if restarts:
            evidence.append(tr("Restarts of the gevent process for memory in the Odoo log of the period (« Gevent virtual memory limit reached »): {n}").format(n=restarts))
        advice = [tr("in odoo.conf (values in bytes): limit_memory_soft_gevent = {sb} ({s} MB) and limit_memory_hard_gevent = {hb} ({h} MB), then restart Odoo").format(
                      sb=want_soft * 1048576, s=want_soft, hb=want_hard * 1048576, h=want_hard)]
        more = want_hard - (hard_g or hard)
        if more > 0:
            advice.append(tr("it gives the live chat room for many more people at the same time (one connection per open Odoo tab) without cutting them; it is one process: at most about {r} MB more of real RAM").format(r=more))
        self.add("gevent-memory-limit", LOOK if restarts else INFO,
                 tr("Live chat (gevent process) limited like a worker: raise limit_memory_soft_gevent and limit_memory_hard_gevent"), max(1, restarts), evidence,
                 tr("the gevent process keeps the connections of the discussion and of the notifications open (one per open Odoo tab); its memory grows with the number of people connected at the same time and, at its limit, it restarts: every discussion is cut for a few seconds"),
                 advice, confirmed=bool(restarts))

    def _memory_low_now(self, memory, total, workers, plan):
        """1.12: memory available NOW (MemAvailable) under 15 % of the memory: the server is short of RAM, more memory recommended."""
        tr = self.tr
        available = memory.get("available_mb")
        if available is None or available >= total * 0.15:
            return
        need = max(plan["ram_needed"], total + 2048)
        self.add("memory-low-now", LOOK, tr("Memory nearly used up now: {a} MB available of {t} MB").format(a=available, t=total), 1,
                 [tr("Memory available now (MemAvailable): {a} MB, {p} % of {t} MB").format(a=available, p=available * 100 // max(1, total), t=total)],
                 tr("the system has little memory left for PostgreSQL, its cache and the Odoo processes: the site slows down, and the kernel may stop a process"),
                 [tr("add about {gb} GB of memory to this server (Proxmox: memory of the container), or lower workers ({w} now)").format(gb=-(-(need - total) // 1024), w=workers)])

    # --- the file odoo.conf read the way Odoo reads it (1.13) ---------------------------------------------------------------------------
    def rule_odoo_conf_check(self, facts, details):
        tr, raw = self.tr, self.raw
        found = details.get("odoo_conf_check") or []
        errors = [r for r in found if r[0] == "error"]
        warnings = [r for r in found if r[0] == "warning"]
        if not found:
            return
        path = (details.get("odoo_conf") or {}).get("path") or "odoo.conf"
        evidence = [(tr("line {n}: ").format(n=line) if line else "") + (f"{key}: " if key else "") + raw(_cut(text, 220)) for _lvl, line, key, text in (errors + warnings)[:8]]
        self.add("odoo-conf-check", PROBLEM if errors else LOOK,
                 tr("odoo.conf: {e} errors and {w} warnings when read the way Odoo reads it").format(e=len(errors), w=len(warnings)), max(1, len(errors)), evidence,
                 tr("Odoo reads its file with configparser: a comment after a value stays IN the value, a key given twice or a value of the wrong type stops Odoo at its next start"),
                 [tr("fix the lines above in {path}, then check again: python3 /opt/rlq-admin-tools/apps/_odoo_conf_check.py {path}").format(path=path),
                  tr("only after that, restart Odoo (a running Odoo keeps the values of its start: an error shows at the next restart)")])

    # --- the configuration in effect in the running Odoo (1.10) -------------------------------------------------------------------
    def rule_odoo_runtime(self, facts, details):
        tr, raw = self.tr, self.raw
        rt = details.get("odoo_runtime") or {}
        if not rt:
            return
        stamp = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else "?"
        base = [tr("Odoo started on {start}; odoo.conf modified on {mtime}").format(start=stamp(rt.get("start")), mtime=stamp(rt.get("file_mtime")))]
        if rt.get("changed"):
            self.add("odoo-conf-not-applied", LOOK, tr("odoo.conf changed since Odoo started: {n} values not in effect until a restart").format(n=len(rt["changed"])),
                     len(rt["changed"]), base + [tr("{key}: in effect {running}, in the file {file}").format(key=raw(k), running=raw(a or "-"), file=raw(b or "-")) for k, a, b in rt["changed"][:10]],
                     tr("Odoo reads its configuration only when it starts: the running processes still use the values of the start"),
                     [tr("restart Odoo at a quiet moment (systemctl restart {svc}), then odoo-warmup.py").format(svc=raw((details.get("service") or {}).get("name") or "SERVICE"))], confirmed=True)
        elif rt.get("after_start") and not rt.get("known"):
            self.add("odoo-conf-not-applied", INFO, tr("odoo.conf modified after Odoo started: the values in effect are not known"), 1, base,
                     tr("the file changed after the start and no copy of the values of the start was kept (the analysis keeps one from its first run after each start)"),
                     [tr("restart Odoo at a quiet moment so that the file is in effect (systemctl restart {svc})").format(svc=raw((details.get("service") or {}).get("name") or "SERVICE"))])
        ignored = [(k, v, f) for k, v, f in rt.get("overrides") or () if f]
        if ignored:
            self.add("odoo-conf-command-line", INFO, tr("Options of the command line override odoo.conf: {n}").format(n=len(ignored)), len(ignored),
                     [tr("{key}: {cli} on the command line (in the file: {file}, ignored)").format(key=raw(k), cli=raw(v), file=raw(f)) for k, v, f in ignored[:10]],
                     tr("the service starts Odoo with these options (run.sh or the unit): changing them in odoo.conf has no effect"),
                     [tr("change them where the service starts Odoo, or remove them there so that odoo.conf is used")], confirmed=True)
        if rt.get("expected") and rt.get("processes") and rt["processes"] < rt["expected"]:
            self.add("odoo-processes", INFO, tr("Odoo runs {n} processes, its configuration gives {m}").format(n=rt["processes"], m=rt["expected"]), 1,
                     [tr("1 main process + workers + cron threads + 1 gevent")],
                     tr("a worker was being replaced at that instant (recycled at limit_memory_soft, or after limit_time_*), or the cron threads are lower in effect"),
                     [tr("nothing to do if it is back at the next analysis; otherwise look at the Odoo log around that time (key E)")])

    # --- one address, one page, again and again (1.7) ---------------------------------------------------------------------------
    def rule_hot_pairs(self, facts, details):
        tr, raw = self.tr, self.raw
        who = facts.get("who") or {}
        for h in facts.get("hot_pairs") or ():
            codes = Counter({str(c): k for c, k in (h.get("codes") or {}).items()})
            ok = sum(k for c, k in codes.items() if c.startswith("2"))
            name = raw(who.get(h["ip"], h["ip"]))
            evidence = [tr("{n} requests to {url}, {pct} % of the requests of this address ({total})").format(
                            n=h["n"], url=raw(_cut(h["url"], 90)), pct=round(100 * h["n"] / max(1, h.get("ip_total") or h["n"])), total=h.get("ip_total") or h["n"]),
                        tr("Answers: ") + ", ".join(f"{c} ×{k}" for c, k in codes.most_common(4))]
            backend = BACKEND_RPC_RE.search(h["url"])
            if backend:
                evidence.append(tr("Call of the Odoo back office (JSON-RPC): it needs a signed-in session"))
            devices = (details.get("devices") or {}).get(h["ip"]) or []
            staff = [d for d in devices if not d.get("share")]
            for d in devices[:2]:
                # 1.9: the device log of Odoo (res.device.log, Odoo 17+) says whose session it is: no guess left
                evidence.append(tr("Odoo device log: session of {name} ({login}), {device}, last activity {when}{revoked}").format(
                    name=raw(d.get("name") or "?"), login=raw(d.get("login") or "?"), device=raw(" ".join(x for x in (d.get("platform"), d.get("browser")) if x) or "?"),
                    when=time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("last") or 0)), revoked=" " + tr("(session revoked)") if d.get("revoked") else ""))
            if backend and staff and not h.get("known"):
                severity = INFO
                cause = tr("a tab of the Odoo back office of {name}, a user of the site, repeats the same call (a loop of the web client): the session is really theirs").format(name=raw(staff[0].get("name") or "?"))
                advice = [tr("ask the person to reload or close the tab; once checked: app-log-live.py --ack {code} (the analysis then lists it apart)").format(code=ack_code("hot-pair:" + h["ip"] + ":" + h["url"][:60]))]
                self.add("hot-pair:" + h["ip"] + ":" + h["url"][:60], severity, tr("One address asks the same page again and again: {who} ×{n}").format(who=name, n=h["n"]),
                         h["n"], evidence, cause, advice, confirmed=True)
                continue
            if backend and h.get("known"):
                severity = INFO
                cause = tr("an open tab of the Odoo back office of a known person repeats the same call (a dialog left open, a session that expired, or a module that asks again)")
                advice = [tr("ask the person to reload or close the tab; nothing else to do")]
            elif backend and ok * 2 >= h["n"]:
                severity = LOOK
                cause = tr("a valid Odoo session is used from this address, which is not known to the site, and repeats the same call: an open tab left running, or a session used by someone else")
                advice = [tr("check who signed in from this address (web-monitor.py --list-users shows each user with the addresses seen); if it is not one of your users, change their password and end their sessions"),
                          tr("if it is one of your users travelling or on a mobile network: ask them to close the tab")]
            elif backend:
                severity = INFO
                cause = tr("an old tab of the Odoo back office whose session has expired keeps calling: it is refused each time")
                advice = [tr("nothing to do: harmless; it stops when the tab is closed")]
            else:
                severity = LOOK if not h.get("known") else INFO
                cause = tr("a robot, a script or a monitoring tool asks the same page again and again")
                advice = [tr("if it is hostile or useless: key b (nginx-log-audit.sh --ban checks the white list and its score, threshold 3); if it is a monitoring tool of yours: add its address to the white list")]
            self.add("hot-pair:" + h["ip"] + ":" + h["url"][:60], severity, tr("One address asks the same page again and again: {who} ×{n}").format(who=name, n=h["n"]),
                     h["n"], evidence, cause, advice)

    # --- bans ---------------------------------------------------------------------------------------------------------------------
    def rule_bans(self, facts, details):
        tr, raw = self.tr, self.raw
        to_ban = facts.get("to_ban") or []
        devices = details.get("devices") or {}
        signed = [(ip, who, reason) for ip, who, reason in to_ban if any(not d.get("share") for d in devices.get(ip) or ())]
        if signed:
            # 1.9: an address where a user of the site has an Odoo session is never proposed for a ban (a colleague behind the same address)
            to_ban = [x for x in to_ban if x not in signed]
            self.add("ban-held-session", LOOK, tr("Addresses NOT proposed for banning: a user of the site has an Odoo session there: {n}").format(n=len(signed)), len(signed),
                     [f"{raw(who)} : {reason} · " + tr("session of {name}").format(name=raw(next(d.get('name') for d in devices[ip] if not d.get('share')) or '?'))
                      for ip, who, reason in signed[:5]],
                     tr("suspicious requests from an address shared with a user of the site (same network, VPN, mobile carrier)"),
                     [tr("look at the requests of that address before anything: a ban would also block the user")], confirmed=True)
        if to_ban:
            self.add("ban-pending", LOOK, tr("Addresses to ban: {n}").format(n=len(to_ban)), len(to_ban),
                     [f"{raw(who)} : {reason}" for _ip, who, reason in to_ban[:5]] + ([tr("… and {n} more").format(n=len(to_ban) - 5)] if len(to_ban) > 5 else [])
                     + [tr("The score of nginx-log-audit.sh (0 to 7, ban from 3) is computed when key b investigates each address; the white list and the CDN names are checked first")],
                     tr("suspicious requests (.env, wp-includes, probes) from addresses that are neither banned nor protected"),
                     [tr("key b: nginx-log-audit.sh --ban checks the white list and its score (threshold 3) before banning; CDN relays are never proposed")],
                     fix=("ban", [(ip, who, reason) for ip, who, reason in to_ban]))
        during = facts.get("banned_during") or []
        if during:
            # 1.7: the bans made by fail2ban during the window (the summary line "banned addresses seen" counts only the requests of addresses ALREADY banned)
            who = facts.get("who") or {}
            self.add("banned-during", INFO, tr("Addresses banned by fail2ban during the window: {n}").format(n=len(during)), len(during),
                     [f"{raw(who.get(ip, ip))} : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))} ({', '.join(jails)})" for ip, t, jails in during[:5]]
                     + ([tr("… and {n} more").format(n=len(during) - 5)] if len(during) > 5 else []),
                     tr("their attacks matched a fail2ban rule: they are blocked"), [tr("nothing to do")], confirmed=True)
        held = facts.get("not_proposed") or []
        if held:
            self.add("ban-held", INFO, tr("Addresses not proposed for banning: {n}").format(n=len(held)), len(held),
                     [f"{raw(who)} : {reason}" for _ip, who, reason in held[:5]],
                     tr("shared relays (CDN) or a verdict of nginx-log-audit.sh other than BANNIR"), [tr("nothing to do: banning them would block legitimate visitors")])

    # --- account forms -----------------------------------------------------------------------------------------------------------
    def rule_account_forms(self, facts, details):
        tr, raw = self.tr, self.raw
        ips = Counter(facts.get("account_ips") or {})
        total = sum(ips.values())
        if total < 10:
            return
        who = facts.get("who") or {}
        evidence = [tr("By address: ") + " ; ".join(f"{raw(who.get(ip, ip))} ×{k}" for ip, k in ips.most_common(3))]
        nginx = details.get("nginx") or {}
        methods = Counter()
        for url in facts.get("account_urls") or ():
            methods.update((nginx.get(url.split("?", 1)[0]) or {}).get("methods") or {})
        posts = methods.get("POST", 0)
        if methods:
            found = sum(methods.values())
            evidence.append(tr("Forms sent (POST): {posts} · pages only shown (GET): {gets}").format(posts=posts, gets=methods.get("GET", 0))
                            + (" · " + tr("not found in the access logs read: {n} (older rotated logs, or other methods)").format(n=total - found) if total > found else ""))
        signup = details.get("signup") or {}
        accounts = signup.get("accounts") or []
        never = sum(1 for a in accounts if not a.get("logins"))
        if signup:
            scope = signup.get("scope")
            evidence.append((tr("Sign-up in Odoo: free (anyone can create an account)") if scope == "b2c" else tr("Sign-up in Odoo: on invitation") if scope == "b2b"
                             else tr("Sign-up in Odoo: {scope}").format(scope=raw(str(scope or "?"))))
                            + (" · " + tr("portal accounts created in the window: {n}").format(n=signup["new_users"]) if signup.get("new_users") is not None else ""))
            for a in accounts[:5]:
                # 1.7: each account created: when, domain of the login, signed in since or never
                evidence.append("    " + time.strftime("%Y-%m-%d %H:%M", time.localtime(a.get("t") or 0)) + " · @" + raw(a.get("domain") or "?") + " · "
                                + (tr("signed in {n} times since").format(n=a["logins"]) if a.get("logins") else tr("never signed in")))
        # 1.7: "known" = an address where a person signed in, or of the team; before, any address with a NAME (an amazonaws.com host...) was "known"
        known_ips = set(facts.get("known_ips") or ())
        known = sum(k for ip, k in ips.items() if ip in known_ips)
        if never >= 3 and signup.get("scope") == "b2c":
            advice = [tr("look at the portal accounts created recently (Settings > Users, filter « Portal »): remove the fake ones"),
                      tr("enable reCAPTCHA or Cloudflare Turnstile (Website > Configuration > Settings), or set the sign-up to « On invitation »")]
            self.add("account-forms", LOOK, tr("Accounts created that never signed in: {n}").format(n=never), never, evidence,
                     tr("accounts created by a robot (it creates the account and never comes back), or people who did not confirm"), advice, confirmed=True)
        elif known * 2 >= total and posts < 30:
            evidence.append(tr("Requests of people already known to the site (an account signed in from this address): {kn} of {all_n}").format(kn=known, all_n=total))
            self.add("account-forms", INFO, tr("Sign-up and password reset forms: {n} requests, mostly from people already known").format(n=total), total, evidence,
                     tr("people who have an account use the forms (forgotten password, sign-up for an event): not a robot"),
                     [tr("nothing to do; if the same person comes back often, check that the sign-in works for them")])
        elif methods and posts < 5:
            evidence.append(tr("Requests of people already known to the site (an account signed in from this address): {kn} of {all_n}").format(kn=known, all_n=total))
            self.add("account-forms", INFO, tr("Sign-up and password reset forms: {n} requests, almost all only shown").format(n=total), total, evidence,
                     tr("robots and search engines following the links of the site: no account attempts"), [tr("nothing to do")])
        elif posts >= 10 or (not methods and (ips.most_common(1)[0][1] >= 5 or total >= 30)):
            advice = [tr("enable reCAPTCHA or Cloudflare Turnstile (Website > Configuration > Settings), or set the sign-up to « On invitation »")]
            if signup.get("new_users"):
                advice.append(tr("look at the portal accounts created recently (Settings > Users, filter « Portal »): remove the fake ones"))
            self.add("account-forms", LOOK, tr("Sign-up and password reset forms used a lot: {n} requests").format(n=total), total, evidence,
                     tr("a robot that creates accounts or tests addresses"), advice)
        else:
            self.add("account-forms", INFO, tr("Sign-up and password reset forms: {n} requests from {k} addresses").format(n=total, k=len(ips)), total, evidence,
                     tr("normal use and search engines following the links"), [tr("nothing to do")])

    # --- latency sample ----------------------------------------------------------------------------------------------------------
    def rule_latency_sample(self, facts, details):
        tr = self.tr
        n, requests = facts.get("latency_n"), facts.get("requests") or 0
        if n is None or requests < 1000 or n >= requests * 0.05:
            return
        self.add("latency-sample", INFO, tr("Latency measured on {n} Odoo requests only, for {total} requests").format(n=n, total=requests), n, [],
                 tr("most requests are answered without an Odoo line that gives its duration (static files, cache, chat websocket)"),
                 [tr("the latency verdict is indicative; let the program run longer before deciding on hardware")])


def ack_code(fid):
    """1.9: short and stable code of a finding (6 hexadecimal characters), shown after its title and given to app-log-live.py --ack CODE."""
    return hashlib.sha1(fid.encode("utf-8")).hexdigest()[:6]


class Acknowledgements:
    """1.9: acknowledged.json (state folder of app-log-live.py): the findings an administrator checked ("it was a volunteer, a bug of Odoo"). Each
    entry: code, id, title, note, by, at, until, count (count of the finding when it was checked). A checked finding is listed apart, out of the
    summary, until its date; it comes back when its count grows beyond ACK_GROWTH times the count of the check."""

    def __init__(self, path):
        self.path, self.entries, self.error = path, [], None
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self.entries = [e for e in (data.get("entries") or []) if isinstance(e, dict) and e.get("code")]
            except (OSError, ValueError, AttributeError) as problem:
                self.error = str(problem)

    def active(self, now=None):
        now = now or time.time()
        return {e["code"]: e for e in self.entries if float(e.get("until") or 0) > now}

    def add(self, code, fid, title, note, by, days, count=0, now=None):
        now = now or time.time()
        self.entries = [e for e in self.entries if e.get("code") != code]
        entry = {"code": code, "id": fid, "title": title, "note": note or "", "by": by or "?", "at": now, "until": now + max(1, days) * 86400, "count": int(count or 0)}
        self.entries.append(entry)
        return entry

    def remove(self, code):
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.get("code") != code]
        return len(self.entries) < before

    def save(self):
        if not self.path:
            return False
        tmp = self.path + ".tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "entries": self.entries}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            return True
        except OSError as problem:
            self.error = str(problem)
            return False


def split_acknowledged(findings, active):
    """1.9: (findings still to look at, [(finding, entry)] checked by an administrator). A finding comes back when its count is more than ACK_GROWTH
    times the count at the check (entry["grown"] is then set for the display)."""
    shown, checked = [], []
    for f in findings:
        entry = active.get(ack_code(f["id"]))
        if entry is None or f["id"] == "all-clear":
            shown.append(f)
        elif entry.get("count") and f["count"] > ACK_GROWTH * int(entry["count"]):
            f = dict(f, acknowledged=entry)
            shown.append(f)
        else:
            checked.append((f, entry))
    return shown, checked


def analyze(facts, details=None, tr=_identity, raw=_identity):
    return Analyzer(tr, raw).run(facts, details)


def timeline(facts, details=None, tr=_identity, raw=_identity, limit=60):
    """1.7: the events of the window in time order, from what the analysis read: starts and stops of the service, interruptions seen by nginx, Odoo
    errors (first and last), slow requests, bans made by fail2ban, failed e-mails, push duplicates, memory messages of the kernel, scheduled actions.
    [(epoch, text)], at most `limit` (the most recent kept). Lets a reader see causes and effects side by side."""
    details = details or {}
    events = []
    for t, text in (details.get("service") or {}).get("events") or ():
        events.append((t, tr("service: ") + raw(_cut(text, 100))))
    for t, text in details.get("backup_events") or ():
        events.append((t, tr("backup: ") + raw(_cut(text, 100))))      # 1.10: odoo-backup.service
    for t, text in (details.get("service") or {}).get("odoo_events") or ():
        events.append((t, tr("Odoo (journal): ") + raw(_cut(text, 100))))      # 1.8: an auto_backup that starts or ends, for instance
    groups = {}
    for e in facts.get("nginx_errors") or ():
        message = NGINX_TAG_RE.sub("", e["message"])
        if UPSTREAM_RE.search(message) and e.get("first") and e.get("last"):
            # 1.16: one entry per interruption (5 minutes without refusal = a new one), from the instants of app-log-live.py 1.187
            times = sorted(e.get("times") or ())
            if times:
                for t in times:
                    near = next((k for k, v in groups.items() if k[0] == "t" and 0 <= t - v[1] <= 300), None)
                    if near:
                        groups[near][1] = t
                        groups[near][2] += 1
                    else:
                        groups[("t", int(t))] = [t, t, 1]
                continue
            g = groups.setdefault(message.split(", client:", 1)[0], [e["first"], e["last"], 0])
            g[0], g[1], g[2] = min(g[0], e["first"]), max(g[1], e["last"]), g[2] + e["n"]
    for first, last, n in groups.values():
        events.append((first, tr("nginx: Odoo unreachable, start ({n} refusals until {last})").format(n=n, last=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last)))))
        if last != first:
            events.append((last, tr("nginx: Odoo unreachable, last refusal")))
    for e in facts.get("odoo_errors") or ():
        if e.get("level") in ("ERROR", "CRITICAL") and e.get("first"):
            label = f"{e['level']} {raw(e.get('logger') or '')} ×{e['n']} : {raw(_cut(e.get('message') or '', 80))}"
            events.append((e["first"], tr("Odoo, first: ") + label))
            if e.get("last") and e["last"] != e["first"]:
                events.append((e["last"], tr("Odoo, last: ") + label))
    who = facts.get("who") or {}
    for x in facts.get("slow") or ():
        if x.get("t") and not LONG_CONNECTION_RE.search(x.get("url") or ""):
            events.append((x["t"], tr("slow request: {s} s ").format(s=f"{x.get('total') or 0:.1f}") + raw(_cut(x.get("url") or "", 70)) + " (" + raw(who.get(x.get("ip"), x.get("ip") or "?")) + ")"))
    for ip, t, jails in facts.get("banned_during") or ():
        events.append((t, tr("fail2ban: ban of ") + raw(who.get(ip, ip)) + f" ({', '.join(jails)})"))
    for c in details.get("mail_failed") or ():
        if c.get("instant"):
            events.append((c["instant"], tr("failed e-mail: « {subject} » to {to}").format(subject=raw(_cut(c.get("sujet") or "", 60)), to=raw(_cut(c.get("destinataires") or "?", 60)))))
    times = facts.get("push_times") or []
    if len(times) == 2:
        events.append((times[0], tr("push subscription already registered, first (harmless)")))
    for t, text in (details.get("memory") or {}).get("kernel") or ():
        events.append((t, tr("kernel: ") + raw(_cut(text, 100))))
    for t, name in details.get("crons") or ():
        events.append((t, tr("scheduled action (last run): ") + raw(_cut(name, 60))))
    start = facts.get("start")
    events = sorted((t, text) for t, text in events if t and (not start or t >= start - 3600))
    return events[-limit:]


# ------------------------------------------------------------------------------------------------------------------
# History: continuous improvement
# ------------------------------------------------------------------------------------------------------------------
class History:
    """advisor-history.json: the last analyses (instant, session, new occurrences per finding) and the title of each finding.
    record() compares the findings with the analyses before and returns the trends; save() writes the file atomically (mode 600)."""

    def __init__(self, path):
        self.path = path
        self.data = {"version": 1, "runs": [], "titles": {}}
        self.error = None
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and isinstance(d.get("runs"), list):
                    self.data = {"version": 1, "runs": [r for r in d["runs"] if isinstance(r, dict)], "titles": dict(d.get("titles") or {})}
            except (OSError, ValueError) as problem:
                self.error = str(problem)

    def record(self, findings, session, now=None):
        """Adds this analysis. New occurrences = count minus the count of the previous analysis of the SAME session (the counters of
        app-log-live.py grow during a session). Returns {"previous": instant or None, "tags": {id: tag}, "resolved": [titles], "top": [(title, runs)], "runs": n}."""
        now = now or time.time()
        runs = [r for r in self.data["runs"] if now - float(r.get("t", 0)) < HISTORY_MAX_DAYS * 86400]
        same = next((r for r in reversed(runs) if r.get("session") == session), None)
        counts = {f["id"]: int(f["count"]) for f in findings if f["id"] != "all-clear"}
        before = (same or {}).get("counts") or {}
        new = {fid: c - int(before.get(fid, 0)) if same else c for fid, c in counts.items()}
        previous = runs[-1] if runs else None
        tags, resolved = {}, []
        for f in findings:
            fid = f["id"]
            if fid == "all-clear":
                continue
            past = [r for r in runs if (r.get("new") or {}).get(fid, 0) > 0]
            streak = 0
            for r in reversed(runs):
                if (r.get("new") or {}).get(fid, 0) > 0:
                    streak += 1
                else:
                    break
            if new.get(fid, 0) <= 0 and fid in before:
                tags[fid] = ("quiet", 0)
            elif not past:
                tags[fid] = ("new", 0)
            elif streak == len(runs) or streak >= 2:
                tags[fid] = ("streak", streak + 1)
            elif previous is not None and (previous.get("new") or {}).get(fid, 0) <= 0:
                tags[fid] = ("back", len(past) + 1)
            else:
                tags[fid] = ("seen", len(past) + 1)
        if previous is not None:
            for fid, k in (previous.get("new") or {}).items():
                if k > 0 and fid not in counts:
                    resolved.append(self.data["titles"].get(fid, fid))
        for f in findings:
            self.data["titles"][f["id"]] = f["title"]
        runs.append({"t": now, "session": session, "counts": counts, "new": {k: v for k, v in new.items() if v > 0},
                     "severity": max([f["severity"] for f in findings] or [0])})
        self.data["runs"] = runs[-HISTORY_MAX_RUNS:]
        frequency = Counter()
        for r in self.data["runs"]:
            for fid, k in (r.get("new") or {}).items():
                if k > 0:
                    frequency[fid] += 1
        self.data["titles"] = {k: v for k, v in self.data["titles"].items() if k in frequency or k in counts}
        # 1.16: only the findings still present in THIS analysis (DEV 2026-11-09 still listed « 5xx on /en_CA/web/login ×8 » and « Missing model »
        # of analyses of the week before, gone since)
        top = [(self.data["titles"].get(fid, fid), k) for fid, k in frequency.most_common() if k >= 2 and counts.get(fid)][:5]
        return {"previous": float(previous["t"]) if previous else None, "tags": tags, "resolved": resolved, "top": top, "runs": len(self.data["runs"])}

    def save(self):
        if not self.path:
            return False
        tmp = self.path + ".tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            return True
        except OSError as problem:
            self.error = str(problem)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return False


# ------------------------------------------------------------------------------------------------------------------
# Display
# ------------------------------------------------------------------------------------------------------------------
def render(findings, trend=None, tr=_identity, color=lambda style, text: text, history_path=None, history_error=None, apply_hint="", acknowledged=None):
    """Lines of the analysis: summary, each finding (evidence, cause, recommendations, trend), resolved problems and priorities.
    1.9: each finding shows its code ([a1b2c3], for app-log-live.py --ack CODE); `acknowledged` = [(finding, entry)] checked by an administrator,
    listed apart at the end and left out of the summary."""
    trend = trend or {}
    symbols = {PROBLEM: ("✖", "1;31"), LOOK: ("⚠", "1;33"), INFO: ("ℹ", "2")}
    counts = Counter(f["severity"] for f in findings if f["id"] != "all-clear")
    lines = ["  " + tr("Summary: {p} problems, {l} to look at, {i} for information").format(p=counts[PROBLEM], l=counts[LOOK], i=counts[INFO])]
    tags = trend.get("tags") or {}
    if trend.get("previous"):
        new = sum(1 for t in tags.values() if t[0] == "new")
        again = sum(1 for t in tags.values() if t[0] in ("streak", "back", "seen"))
        lines.append("  " + tr("Compared with the previous analysis ({when}): {new} new, {again} seen before, {resolved} resolved").format(
            when=time.strftime("%Y-%m-%d %H:%M", time.localtime(trend["previous"])), new=new, again=again, resolved=len(trend.get("resolved") or ())))
    else:
        lines.append("  " + tr("First analysis kept: the next ones will say what is new, recurring or resolved"))
    for f in findings:
        symbol, style = symbols[f["severity"]]
        tag = tags.get(f["id"])
        tag_text = ""
        if tag:
            kind, k = tag
            tag_text = {"new": tr("[new]"), "quiet": tr("[no new occurrence since the last analysis]"),
                        "streak": tr("[recurring: {k} analyses in a row]").format(k=k), "back": tr("[back: seen in {k} analyses]").format(k=k),
                        "seen": tr("[seen in {k} analyses]").format(k=k)}.get(kind, "")
        lines.append("  " + color(style, f"{symbol} {f['title']}") + (" " + color("1;35", tag_text) if tag_text else "")
                     + ("" if f["id"] == "all-clear" else " " + color("2", f"[{ack_code(f['id'])}]")))
        if f.get("acknowledged"):
            e = f["acknowledged"]
            lines.append("        " + color("1;33", tr("Checked by {by} on {when} ({count} at the time), but {now} now: to look at again").format(
                by=e.get("by", "?"), when=time.strftime("%Y-%m-%d", time.localtime(float(e.get("at") or 0))), count=e.get("count", "?"), now=f["count"])))
        for e in f["evidence"]:
            if e:
                lines.append("        " + e)
        if f["cause"]:
            lines.append("        " + (tr("Cause (confirmed): ") if f.get("confirmed") else tr("Probable cause: ")) + f["cause"])
        for a in f["advice"]:
            lines.append("        " + color("1;36", "→ ") + a)
        if f.get("fix") and apply_hint:
            lines.append("        " + color("1;32", "⚙ ") + apply_hint)
    if acknowledged:
        lines.append("  " + color("1;32", "✔ " + tr("Checked by an administrator, left out of the summary: {n}").format(n=len(acknowledged))))
        for f, e in acknowledged:
            lines.append("        " + f"{f['title']} " + color("2", f"[{e['code']}]") + " : " + (e.get("note") or tr("no note"))
                         + " · " + tr("by {by} on {when}, until {until}").format(by=e.get("by", "?"), when=time.strftime("%Y-%m-%d", time.localtime(float(e.get("at") or 0))),
                                                                              until=time.strftime("%Y-%m-%d", time.localtime(float(e.get("until") or 0)))))
    if trend.get("resolved"):
        lines.append("  " + color("1;32", "✔ " + tr("Resolved since the previous analysis: ")) + " ; ".join(trend["resolved"][:8]))
    if trend.get("top"):
        lines.append("  " + tr("Problems seen most often (to fix first): ") + " ; ".join(f"{t} ×{k}" for t, k in trend["top"]))
    if history_path:
        lines.append("  " + color("2", tr("History: {path} ({n} analyses kept)").format(path=history_path, n=trend.get("runs", 0))))
    elif history_error is not None:
        lines.append("  " + color("2", tr("History not kept: {problem}").format(problem=history_error)))
    return lines
