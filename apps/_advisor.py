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

__version__ = "1.2.20261104.183145"

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
NGINX_LINE_RE = re.compile(r'\[(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})\]\s+"(?:GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH)\s+(\S+)'
                           r'[^"]*"\s+(\d{3})\s+\S+\s+"([^"]*)"\s+"([^"]*)"')
HOST_RE = re.compile(r"\bhost=(\S+)")
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
    """For each URL of `urls` (path, without the query): {"codes": Counter, "referers": Counter, "agents": Counter, "hosts": Counter}
    read in the nginx access logs (end of each file, lines after `since` when given)."""
    wanted = {u.split("?", 1)[0] for u in urls}
    res = {u: {"codes": Counter(), "referers": Counter(), "agents": Counter(), "hosts": Counter()} for u in wanted}
    if not wanted:
        return res
    for path in files:
        for text_line in read_tail(path, max_bytes):
            m = NGINX_LINE_RE.search(text_line)
            if not m:
                continue
            url = m.group(10).split("?", 1)[0]
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
            d["codes"][m.group(11)] += 1
            if m.group(12) and m.group(12) != "-":
                d["referers"][m.group(12)] += 1
            d["agents"][m.group(13)[:80]] += 1
            h = HOST_RE.search(text_line)
            if h:
                d["hosts"][h.group(1)] += 1
    return res


def internal_referers(detail):
    """Referers of the site itself (same host as the request): the page that holds the dead link."""
    hosts = set(detail.get("hosts") or ())
    res = Counter()
    for ref, n in (detail.get("referers") or {}).items():
        m = re.match(r"^https?://([^/]+)", ref)
        if m and (not hosts or m.group(1) in hosts):
            res[ref] += n
    return res


# ------------------------------------------------------------------------------------------------------------------
# Rules
# ------------------------------------------------------------------------------------------------------------------
class Analyzer:
    """analyze(facts, details) -> list of findings {"id", "severity", "title", "count", "evidence": [...], "cause": text, "advice": [...]}."""

    def __init__(self, tr=_identity, raw=_identity):
        self.tr, self.raw = tr, raw
        self.findings = []

    def add(self, fid, severity, title, count=1, evidence=(), cause="", advice=()):
        self.findings.append({"id": fid, "severity": severity, "title": title, "count": count, "evidence": list(evidence), "cause": cause, "advice": list(advice)})

    def run(self, facts, details=None):
        details = details or {}
        self.findings = []
        for rule in (self.rule_5xx, self.rule_sitemap_404, self.rule_repeated_4xx, self.rule_odoo_errors, self.rule_conflicts, self.rule_mails,
                     self.rule_slow, self.rule_bans, self.rule_account_forms, self.rule_latency_sample):
            try:
                rule(facts, details)
            except Exception as problem:                     # one rule never stops the others
                self.add("advisor-rule-failed:" + rule.__name__, INFO, self.tr("Rule {name} could not run: {problem}").format(name=rule.__name__, problem=self.raw(str(problem))))
        if not any(f["severity"] >= LOOK for f in self.findings):
            self.add("all-clear", INFO, self.tr("Nothing to fix in this window: no error that needs an action"))
        self.findings.sort(key=lambda f: (-f["severity"], -f["count"], f["id"]))
        return self.findings

    def referer_lines(self, detail):
        tr, raw = self.tr, self.raw
        lines = []
        inside = internal_referers(detail)
        if inside:
            lines.append(tr("Linked from the site itself: ") + " ; ".join(f"{raw(r)} ×{n}" for r, n in inside.most_common(3)))
        outside = Counter({r: n for r, n in (detail.get("referers") or {}).items() if r not in inside})
        if outside:
            lines.append(tr("Linked from other sites: ") + " ; ".join(f"{raw(r)} ×{n}" for r, n in outside.most_common(3)))
        return lines

    # --- 5xx ---------------------------------------------------------------------------------------------------------------------
    def rule_5xx(self, facts, details):
        tr, raw = self.tr, self.raw
        codes = facts.get("codes_by_url") or {}
        for url, n in Counter(facts.get("errors5") or {}).most_common(3):
            by_code = {c: k for c, k in (codes.get(url) or {}).items() if int(c) >= 500}
            gateway = sum(k for c, k in by_code.items() if int(c) in (502, 503, 504))
            if gateway and gateway >= n / 2:
                cause = tr("nginx got no answer from Odoo (502, 503, 504): service stopped or restarting, every worker busy, or a request longer than the timeout")
                advice = [tr("key D: site diagnosis (service, Odoo ports, nginx upstream)"), tr("app-health-check.py: workers, memory and PostgreSQL connections")]
            else:
                cause = tr("Odoo answered with an internal error (500): an exception in a module")
                advice = [tr("key E: the traceback of the error (app-log-check.py --errors-only --full-trace)"), tr("fix or update the module named in the traceback")]
            self.add("http-5xx:" + url, PROBLEM if n >= 5 else LOOK, tr("HTTP 5xx errors on {url}").format(url=raw(url)), n,
                     [tr("Codes: ") + ", ".join(f"{c} ×{k}" for c, k in sorted(by_code.items()))] if by_code else [], cause, advice)

    # --- 404 of the sitemap ------------------------------------------------------------------------------------------------------
    def rule_sitemap_404(self, facts, details):
        tr, raw = self.tr, self.raw
        paths = facts.get("sitemap_paths")
        nginx = details.get("nginx") or {}
        for url, n in Counter(facts.get("gone_404") or {}).most_common(5):
            path = url.split("?", 1)[0]
            detail = nginx.get(path) or {}
            refs = self.referer_lines(detail)
            if LANGUAGE_PATH_RE.match(path):
                code = path.strip("/").split("_")[0]
                kind = tr("not a language code") if code not in ISO_639_1 else tr("a language code that the site may not offer")
                self.add("sitemap-404-false:" + path, INFO, tr("404 on {url} counted as a sitemap page: false alarm").format(url=raw(url)), n,
                         [tr("The path is a single segment of two letters ({kind}): app-log-live.py removes it as a language prefix and compares the home page (/), which is in the sitemap").format(kind=kind)] + refs,
                         tr("a truncated or mistyped URL, not a page of the site that disappeared"),
                         [tr("nothing to fix on the site; since app-log-live.py 1.164 only the codes of ISO 639-1 are taken for language prefixes")])
                continue
            longer = sorted(p for p in (paths or ()) if p.startswith(path) and p != path)[:3] if paths else []
            if longer:
                self.add("sitemap-404-truncated:" + path, LOOK, tr("404 on {url}: beginning of a real page, a truncated link").format(url=raw(url)), n,
                         [tr("Pages of the sitemap that start the same way: ") + " ; ".join(raw(p) for p in longer)] + refs,
                         tr("a link cut in an e-mail, a message or a post"),
                         [tr("correct the link at its source (see the referers); optional: a 301 redirect to the full page (Website > Configuration > Redirects)")])
                continue
            self.add("sitemap-404:" + path, LOOK, tr("404 on {url}, a page listed in sitemap.xml").format(url=raw(url)), n, refs,
                     tr("the page was deleted, unpublished or renamed while the sitemap or a link still lists it"),
                     [tr("publish the page again, or add a 301 redirect to its replacement (Website > Configuration > Redirects)"),
                      tr("then correct the menus and links that point to it (see the referers)")])

    # --- repeated 4xx outside the sitemap -----------------------------------------------------------------------------------------
    def rule_repeated_4xx(self, facts, details):
        tr, raw = self.tr, self.raw
        nginx = details.get("nginx") or {}
        gone = {u.split("?", 1)[0] for u in (facts.get("gone_404") or {})}
        for url, n in Counter(facts.get("plain_4xx") or {}).most_common(6):
            path = url.split("?", 1)[0]
            if path in gone or n < 3:
                continue
            detail = nginx.get(path) or {}
            codes = Counter(detail.get("codes") or (facts.get("codes_by_url") or {}).get(url) or {})
            evidence = ([tr("Codes: ") + ", ".join(f"{c} ×{k}" for c, k in sorted(codes.items()))] if codes else []) + self.referer_lines(detail)
            agents = Counter(detail.get("agents") or {})
            if path.rstrip("/").endswith("sitemap.xml"):
                if codes and all(str(c) == "403" for c in codes):
                    self.add("sitemap-xml-403", INFO, tr("sitemap.xml refused (403) to robots of the blocking list"), n, evidence,
                             tr("bot_blocker.conf refuses these robots: expected"), [tr("nothing to do, unless a search engine you want is refused")])
                else:
                    self.add("sitemap-xml-4xx", LOOK, tr("sitemap.xml answers {codes}").format(codes=", ".join(sorted(str(c) for c in codes)) or "4xx"), n,
                             evidence + ([tr("User-Agents: ") + " ; ".join(f"{raw(a)} ×{k}" for a, k in agents.most_common(3))] if agents else []),
                             tr("Odoo builds sitemap.xml for the domain of the website: a request for another host name, or nginx not passing it to Odoo"),
                             [tr("check the domain of the website (Website > Configuration > Settings > Domain) and that nginx sends /sitemap.xml to Odoo"),
                              tr("open https://YOUR-SITE/sitemap.xml in a browser: it must answer 200")])
                continue
            if codes and not any(str(c) == "404" or str(c) == "410" for c in codes):
                continue                                                # 403 / 405 / 499...: robots refused, clients gone: not a dead page
            inside = internal_referers(detail)
            if inside:
                cause = tr("a link of the site itself points to a page that no longer answers")
                severity = LOOK
            elif SHOP_EVENT_RE.search(path):
                cause = tr("product or event unpublished, archived or renamed, still reached from search engines or old links")
                severity = LOOK if n >= 5 else INFO
            else:
                cause = tr("old or mistyped link; not in sitemap.xml, so not counted in the health")
                severity = LOOK if n >= 10 else INFO
            self.add("dead-link:" + path, severity, tr("{n} answers 404 on {url}").format(n=n, url=raw(url)), n, evidence, cause,
                     [tr("add a 301 redirect to the replacement page (Website > Configuration > Redirects), or publish it again"),
                      tr("correct the page that holds the link (Linked from the site itself), if any")])

    # --- Odoo errors ---------------------------------------------------------------------------------------------------------------
    def rule_odoo_errors(self, facts, details):
        tr, raw = self.tr, self.raw
        traces = details.get("tracebacks") or {}
        for e in facts.get("odoo_errors") or ():
            level, logger, message, n = e["level"], e["logger"] or "", e["message"] or "", e["n"]
            text = f"{logger}: {message}"
            known = next((k for k in KNOWN_MESSAGES if re.search(k[0], text, re.I)), None)
            if level not in ("ERROR", "CRITICAL") and not known:
                continue                                                # unknown warnings: the dashboard lists them, no advice here
            when = e.get("when") or ""
            evidence = [f"{level} {raw(logger)} ×{n} : {raw(_cut(message, 160))}" + (f" ({when})" if when else "")]
            severity = PROBLEM if level == "CRITICAL" or n >= 5 else LOOK
            cause, advice = "", []
            if known:
                severity = min(severity, known[1]) if known[1] == INFO else severity
                cause, advice = tr(known[2]), [tr(known[3])]
            trace = traces.get((level, logger, message)) or []
            parsed = parse_traceback(trace)
            if parsed:
                evidence.append(tr("Exception: ") + raw(parsed["exception"] + (": " + parsed["message"] if parsed["message"] else "")))
                if parsed["module"]:
                    evidence.append(tr("Module of the last frame: {module} ({frame})").format(module=raw(parsed["module"]), frame=raw(parsed["frame"])))
                hint = next((h for h in TRACEBACK_HINTS if re.search(h[0], parsed["exception"] + " " + parsed["message"])), None)
                if hint:
                    cause, advice = tr(hint[1]), [tr(hint[2])]
                    if "werkzeug" in parsed["exception"] and severity < PROBLEM:
                        severity = INFO
            elif level in ("ERROR", "CRITICAL") and (not known or known[1] != INFO):
                evidence.append(tr("Traceback not found in the logs read (logfile or systemd journal around this time)"))
                advice.append(tr("key E shows the complete traces (app-log-check.py --errors-only --full-trace)"))
            if not cause:
                cause = tr("an error of Odoo not yet known to this analysis")
                advice = advice or [tr("key E for the traceback; then fix or update the module concerned")]
            fid = "odoo:" + logger + ":" + re.sub(r"\s+", " ", message)[:80]
            self.add(fid, severity, tr("Odoo {level}: {message}").format(level=level, message=raw(_cut(message, 90))), n, evidence, cause, advice)

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

    # --- e-mails -----------------------------------------------------------------------------------------------------------------
    def rule_mails(self, facts, details):
        tr = self.tr
        n = facts.get("mails") or 0
        if not n:
            return
        texts = " ".join(e.get("message", "") for e in facts.get("odoo_errors") or ())
        hints = [tr(h) for code, h in SMTP_HINTS if re.search(r"\b" + code + r"\b", texts)]
        self.add("mail-failures", PROBLEM if n >= 3 else LOOK, tr("Failed e-mails: {n}").format(n=n), n, hints,
                 tr("the mail server refused or could not be reached"),
                 [tr("odoo-mail-retry.py lists the unsent e-mails and offers to resend them; app-log-check.py explains the causes")])

    # --- slow requests -----------------------------------------------------------------------------------------------------------
    def rule_slow(self, facts, details):
        tr, raw = self.tr, self.raw
        slow = facts.get("slow") or []
        if not slow:
            return
        t_sql = sum(s.get("t_sql") or 0 for s in slow)
        t_py = sum(s.get("t_py") or 0 for s in slow)
        cold = sum(1 for s in slow if COLD_RE.search(s.get("url") or ""))
        pages = Counter(s.get("url", "").split("?", 1)[0] for s in slow)
        evidence = [tr("Pages: ") + " ; ".join(f"{raw(u)} ×{k}" for u, k in pages.most_common(3))]
        if t_sql + t_py > 0:
            evidence.append(tr("Time in SQL {sql} %, in Python {py} %").format(sql=round(100 * t_sql / (t_sql + t_py)), py=round(100 * t_py / (t_sql + t_py))))
        if cold >= 2 and 2 * cold >= len(slow):
            cause = tr("cold cache after a restart or an update: assets and views computed once")
            advice = [tr("odoo-warmup.py right after each restart or update of Odoo")]
        elif t_sql > t_py:
            cause = tr("the database: heavy searches, missing indexes or tables to clean")
            advice = [tr("odoo-sql-maint: VACUUM ANALYZE and the index checks"), tr("look at the filters and the number of records of the slow pages")]
        else:
            cause = tr("Python: heavy computation or report, or too few workers for the load")
            advice = [tr("app-health-check.py: workers, memory, processor"), tr("check workers, limit_time_cpu and limit_time_real in odoo.conf")]
        n = len(slow)
        self.add("slow-requests", PROBLEM if n >= 5 else LOOK, tr("Slow requests: {n}").format(n=n), n, evidence, cause, advice)

    # --- bans ---------------------------------------------------------------------------------------------------------------------
    def rule_bans(self, facts, details):
        tr, raw = self.tr, self.raw
        to_ban = facts.get("to_ban") or []
        if to_ban:
            self.add("ban-pending", LOOK, tr("Addresses to ban: {n}").format(n=len(to_ban)), len(to_ban),
                     [f"{raw(who)} : {reason}" for _ip, who, reason in to_ban[:5]],
                     tr("suspicious requests (.env, wp-includes, probes) from addresses that are neither banned nor protected"),
                     [tr("key b: nginx-log-audit.sh --ban checks the white list and its score (threshold 3) before banning; CDN relays are never proposed")])
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
        busiest = ips.most_common(1)[0][1] if ips else 0
        who = facts.get("who") or {}
        evidence = [tr("By address: ") + " ; ".join(f"{raw(who.get(ip, ip))} ×{k}" for ip, k in ips.most_common(3))]
        if busiest >= 5 or total >= 30:
            self.add("account-forms", LOOK, tr("Sign-up and password reset forms used a lot: {n} requests").format(n=total), total, evidence,
                     tr("a robot that creates accounts or tests addresses"),
                     [tr("enable reCAPTCHA or Cloudflare Turnstile (Website > Configuration > Settings), or set the sign-up to « On invitation »")])
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
def render(findings, trend=None, tr=_identity, color=lambda style, text: text, history_path=None, history_error=None):
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
    if trend.get("resolved"):
        lines.append("  " + color("1;32", "✔ " + tr("Resolved since the previous analysis: ")) + " ; ".join(trend["resolved"][:8]))
    if trend.get("top"):
        lines.append("  " + tr("Problems seen most often (to fix first): ") + " ; ".join(f"{t} ×{k}" for t, k in trend["top"]))
    if history_path:
        lines.append("  " + color("2", tr("History: {path} ({n} analyses kept)").format(path=history_path, n=trend.get("runs", 0))))
    elif history_error is not None:
        lines.append("  " + color("2", tr("History not kept: {problem}").format(problem=history_error)))
    return lines
