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
import json
import os
import re
import time
from collections import Counter

__version__ = "1.5.20261106.094106"

PROBLEM, LOOK, INFO = 2, 1, 0                         # severities: problem, to look at, information

HISTORY_FILE = "advisor-history.json"
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
ROBOT_AGENT_RE = re.compile(r"bot\b|bot/|crawl|spider|slurp|Google-Read-Aloud|WhatsApp|facebookexternalhit|LinkedInBot|Twitterbot|Slackbot|Telegram|Discord|preview|"
                            r"curl/|python|wget|Go-http|okhttp|\bJava/|axios|node-fetch|HeadlessChrome|Lighthouse", re.I)
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
ODOO_DEFAULTS = {"workers": 0, "max_cron_threads": 2, "limit_time_cpu": 60, "limit_time_real": 120, "limit_memory_soft": 2048, "limit_memory_hard": 2560}
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}

# Known Odoo messages: (pattern on "logger: message", severity, cause, recommendation). The first match wins.
KNOWN_MESSAGES = (
    (r"\.map should have been generated through debug assets", INFO,
     "a browser with its developer tools open asked for a source map (.map) of the assets: harmless",
     "nothing to do; it disappears when nobody opens the developer tools (or in debug=assets mode)"),
    (r"called ignoring args", INFO,
     "a browser sent an argument that this version of Odoo no longer expects: an old copy of the web client kept in the browser cache",
     "nothing to do if it is rare; frequent after an update: the users reload the page (Ctrl-Shift-R)"),
    (r"(?:not allowed to access|pas autoris).*mail\.guest|mail\.guest.*(?:access|accès)", INFO,
     "a visitor of the live chat came back with an expired guest session (cookie of an old conversation)",
     "nothing to do if it is rare; many times a day: check the live chat module and the cookie settings"),
    (r"Exception during request handling", LOOK,
     "a request raised an exception: the cause is in the traceback that follows the message",
     "read the traceback below (or key E); fix the module named in the last frame, or report it to its author"),
    (r"bad query|could not serialize access|SerializationFailure", INFO,
     "concurrent update retried by Odoo",
     "nothing to do while the final failures stay at zero"),
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

SMTP_HINTS = (("452", "the mail server refuses for now (quota, rate limit): retry later"),
              ("503", "the mail server refuses the order of the commands (authentication missing?)"),
              ("550", "the recipient or the sender is refused: check the address and the sender domain (SPF, DKIM)"))


def _identity(text):
    return text


def _cut(text, limit):
    """Text cut at `limit` characters, with « … » when something was cut."""
    text = text or ""
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


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
                d["robots"][m.group(14)[:60]] += 1
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
        advice.append(("few", min(best, int((mem_mb or 10 ** 9) * 0.7 // 325)) if mem_mb else best, workers))
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

    def add(self, fid, severity, title, count=1, evidence=(), cause="", advice=(), fix=None):
        self.findings.append({"id": fid, "severity": severity, "title": title, "count": count, "evidence": [e for e in evidence if e], "cause": cause,
                              "advice": list(advice), "fix": fix})

    def run(self, facts, details=None):
        details = details or {}
        self.findings = []
        for rule in (self.rule_5xx, self.rule_nginx_upstream, self.rule_sitemap_404, self.rule_repeated_4xx, self.rule_odoo_errors, self.rule_conflicts,
                     self.rule_mails, self.rule_slow, self.rule_bans, self.rule_account_forms, self.rule_latency_sample):
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

    def origin_lines(self, detail):
        """1.5: what the program checks itself in the access log, instead of asking the administrator: WHO asked (robots / link previews or browsers), WHAT answered
        (the 404 page of nginx is about 150 bytes: a rule of nginx; a page of several KB is Odoo's) and whether a visitor retried the same address."""
        tr, raw = self.tr, self.raw
        lines = []
        sizes = sorted(detail.get("bytes_4xx") or [])
        if sizes:
            middle = sizes[len(sizes) // 2]
            if middle <= 400:
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
                               + (" · " + tr("ended on {end}").format(end=r["end"]) if r.get("end") else ""))
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
        for path, g in sorted(groups.items(), key=lambda pg: -pg[1]["n"])[:5]:
            n = g["n"]
            fuzz = sum(k for u, k in g["urls"].items() if FUZZ_RE.search(u))
            gateway = sum(k for c, k in g["codes"].items() if c in ("502", "503", "504"))
            evidence = [tr("Codes: ") + ", ".join(f"{c} ×{k}" for c, k in g["codes"].most_common())] if g["codes"] else []
            if len(g["urls"]) > 1 or next(iter(g["urls"])) != path:
                evidence.append(tr("Addresses asked: ") + " ; ".join(f"{raw(_cut(u, 90))} ×{k}" for u, k in g["urls"].most_common(3)))
            if g["ips"]:
                evidence.append(tr("Requested by: ") + " ; ".join(f"{raw(who.get(ip, ip))} ×{k}" for ip, k in g["ips"].most_common(3)))
            parsed = parse_traceback(traces.get(path) or [])
            if parsed:
                evidence.append(tr("Exception: ") + raw(_cut(parsed["exception"] + (": " + parsed["message"] if parsed["message"] else ""), 200)))
                if parsed["module"]:
                    evidence.append(tr("Module of the last frame: {module} ({frame})").format(module=raw(parsed["module"]), frame=raw(parsed["frame"])))
            elif traces.get(path) is not None:
                evidence.append(tr("Traceback not found in the logs read (logfile or systemd journal around this time)"))
            if fuzz and fuzz >= n / 2:
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
                g = groups.setdefault(kind, {"n": 0, "first": None, "last": None})
                g["n"] += e["n"]
                for key, pick in (("first", min), ("last", max)):
                    if e.get(key):
                        g[key] = pick(g[key], e[key]) if g[key] else e[key]
            else:
                others[kind] += e["n"]
        restarts = (details.get("service") or {}).get("events") or []
        state = (details.get("service") or {}).get("state")
        for kind, g in sorted(groups.items(), key=lambda kg: -kg[1]["n"]):
            evidence = [raw(_cut(kind, 160))]
            if g["first"] and g["last"]:
                evidence.append(tr("From {first} to {last}").format(first=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(g["first"])),
                                                                      last=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(g["last"]))))
            near = [(t, text) for t, text in restarts if g["first"] and g["last"] and g["first"] - 600 <= t <= g["last"] + 600]
            if near:
                evidence.append(tr("Service journal at that time: ") + " ; ".join(f"{time.strftime('%H:%M:%S', time.localtime(t))} {raw(_cut(text, 70))}" for t, text in near[:4]))
                cause = tr("Odoo was stopped or restarting at that time (see the service journal): nginx found its port closed")
                severity = LOOK
                advice = [tr("nothing to do if the restart was wanted (update, maintenance); otherwise read why the service stopped: journalctl -u SERVICE --since the time above")]
            else:
                cause = tr("nginx could not reach Odoo: service stopped, restarting or crashed, or its port is not the one nginx uses")
                severity = PROBLEM
                advice = [tr("key D: site diagnosis (service, Odoo ports, nginx upstream)"), tr("journalctl -u SERVICE around these times: why Odoo stopped")]
            if state:
                evidence.append(tr("Service now: {svc}").format(svc=raw(state)))
            if "Connection refused" in kind and g["n"] >= 1:
                evidence.append(tr("These lines come from the nginx error log; before app-log-live.py 1.167 they were counted as Odoo errors and as failed e-mails"))
            self.add("nginx-upstream:" + kind[:80], severity, tr("Odoo unreachable from nginx: {n} times").format(n=g["n"]), g["n"], evidence, cause, advice)
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
            elif inside:
                cause = tr("a link of the site itself points to a page that no longer answers")
                severity = LOOK
            elif SHOP_EVENT_RE.search(path):
                cause = tr("product or event unpublished, archived or renamed, still reached from search engines or old links")
                severity = LOOK if count >= 5 else INFO
            else:
                cause = tr("old or mistyped link; not in sitemap.xml, so not counted in the health")
                severity = LOOK if count >= 10 else INFO
            if inside:
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
                evidence.append(tr("{n} people registered several times for the same event (they probably tried again after the 404)").format(n=regs["duplicates"]))
        if not browsers:
            self.add("registration-404:" + path, INFO, tr("{n} answers 404 on {url}: confirmation page opened by robots or link previews").format(n=count, url=raw(path)), count, evidence,
                     tr("Odoo shows the confirmation of a registration only to the visitor who registered (cookie): a robot or a link preview has none"),
                     [tr("nothing to do")])
            return
        advice = [tr("rlq-odoo-addons: show a thank-you page (the confirmation e-mail was sent) instead of the 404 when the visitor is unknown"),
                  tr("check the cookies bar of the website (Website > Configuration > Settings): without the cookie, Odoo cannot recognise the visitor"),
                  tr("Events > Registrations: look for the same e-mail registered twice for the same event")]
        self.add("registration-404:" + path, LOOK, tr("{n} answers 404 on {url}: confirmation page of a registration").format(n=count, url=raw(path)), count, evidence,
                 tr("the registration exists, but Odoo shows its confirmation only to the visitor (cookie) who made it: private browsing, blocked cookies or another browser give a 404"),
                 advice)

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

    # --- e-mails: the database decides ---------------------------------------------------------------------------------------------
    def rule_mails(self, facts, details):
        tr, raw = self.tr, self.raw
        n_log = facts.get("mails") or 0
        db = details.get("mail_db")
        if db is None:
            if not n_log:
                return
            texts = " ".join(e.get("message", "") for e in facts.get("odoo_errors") or ())
            hints = [tr(h) for code, h in SMTP_HINTS if re.search(r"\b" + code + r"\b", texts)]
            self.add("mail-failures", PROBLEM if n_log >= 3 else LOOK, tr("Failed e-mails (journal): {n}").format(n=n_log), n_log,
                     hints + [tr("Database not read (run with sudo): the count comes from the journal lines only")],
                     tr("the mail server refused or could not be reached"),
                     [tr("odoo-mail-retry.py lists the unsent e-mails and offers to resend them; app-log-check.py explains the causes")], fix=("mail", None))
            return
        failed = db.get("exception", 0)
        waiting = db.get("outgoing", 0)
        evidence = [tr("Database, last {nd} days: {failed} in failure, {waiting} waiting, {sent} sent").format(
            nd=db.get("days", "?"), failed=failed, waiting=waiting, sent=db.get("sent", 0))]
        evidence += [tr("Cause: ") + f"{raw(_cut(r, 140))} ×{k}" for r, k in (db.get("reasons") or [])[:3]]
        if db.get("servers"):
            evidence.append(tr("Outgoing mail servers of Odoo: ") + " ; ".join(raw(x) for x in db["servers"]))
        if failed:
            joined = " ".join(r for r, _k in db.get("reasons") or ())
            hints = [tr(h) for code, h in SMTP_HINTS if re.search(r"\b" + code + r"\b", joined)]
            self.add("mail-failures", PROBLEM if failed >= 3 else LOOK, tr("Failed e-mails: {n}").format(n=failed), failed, evidence + hints,
                     tr("the mail server refused these e-mails (see the cause above)"),
                     [tr("odoo-mail-retry.py lists them and offers to resend them, once the cause is fixed")], fix=("mail", db.get("days")))
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
                    conf_advice.append(tr("workers={now} for this machine: up to {best} workers are possible (Odoo guide: (2 x CPU) + 1, about 325 MB each)").format(now=b, best=a))
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
        self.add("slow-requests", PROBLEM if n >= 5 else LOOK, tr("Slow requests: {n}").format(n=n), n, evidence, cause, advice, fix=fix)

    # --- bans ---------------------------------------------------------------------------------------------------------------------
    def rule_bans(self, facts, details):
        tr, raw = self.tr, self.raw
        to_ban = facts.get("to_ban") or []
        if to_ban:
            self.add("ban-pending", LOOK, tr("Addresses to ban: {n}").format(n=len(to_ban)), len(to_ban),
                     [f"{raw(who)} : {reason}" for _ip, who, reason in to_ban[:5]] + ([tr("… and {n} more").format(n=len(to_ban) - 5)] if len(to_ban) > 5 else []),
                     tr("suspicious requests (.env, wp-includes, probes) from addresses that are neither banned nor protected"),
                     [tr("key b: nginx-log-audit.sh --ban checks the white list and its score (threshold 3) before banning; CDN relays are never proposed")],
                     fix=("ban", [(ip, who, reason) for ip, who, reason in to_ban]))
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
            evidence.append(tr("Forms sent (POST): {posts} · pages only shown (GET): {gets}").format(posts=posts, gets=methods.get("GET", 0)))
        signup = details.get("signup") or {}
        if signup:
            scope = signup.get("scope")
            evidence.append((tr("Sign-up in Odoo: free (anyone can create an account)") if scope == "b2c" else tr("Sign-up in Odoo: on invitation") if scope == "b2b"
                             else tr("Sign-up in Odoo: {scope}").format(scope=raw(str(scope or "?"))))
                            + (" · " + tr("portal accounts created in the window: {n}").format(n=signup["new_users"]) if signup.get("new_users") is not None else ""))
        if methods and posts < 5:
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


def analyze(facts, details=None, tr=_identity, raw=_identity):
    return Analyzer(tr, raw).run(facts, details)


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
        top = [(self.data["titles"].get(fid, fid), k) for fid, k in frequency.most_common(5) if k >= 2]
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
def render(findings, trend=None, tr=_identity, color=lambda style, text: text, history_path=None, history_error=None, apply_hint=""):
    """Lines of the analysis: summary, each finding (evidence, cause, recommendations, trend), resolved problems and priorities."""
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
        lines.append("  " + color(style, f"{symbol} {f['title']}") + (" " + color("1;35", tag_text) if tag_text else ""))
        for e in f["evidence"]:
            if e:
                lines.append("        " + e)
        if f["cause"]:
            lines.append("        " + tr("Probable cause: ") + f["cause"])
        for a in f["advice"]:
            lines.append("        " + color("1;36", "→ ") + a)
        if f.get("fix") and apply_hint:
            lines.append("        " + color("1;32", "⚙ ") + apply_hint)
    if trend.get("resolved"):
        lines.append("  " + color("1;32", "✔ " + tr("Resolved since the previous analysis: ")) + " ; ".join(trend["resolved"][:8]))
    if trend.get("top"):
        lines.append("  " + tr("Problems seen most often (to fix first): ") + " ; ".join(f"{t} ×{k}" for t, k in trend["top"]))
    if history_path:
        lines.append("  " + color("2", tr("History: {path} ({n} analyses kept)").format(path=history_path, n=trend.get("runs", 0))))
    elif history_error is not None:
        lines.append("  " + color("2", tr("History not kept: {problem}").format(problem=history_error)))
    return lines
