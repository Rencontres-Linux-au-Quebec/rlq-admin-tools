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
# _email_check.py — e-mail address checks (shared module, apps/): syntax, suggested correction of a typo, disposable domain, mail
# server of the domain (DNS MX), and — only when the caller asks for it — Internet lookups (StopForumSpam, Gravatar, web search).
# Used by web-monitor.py (investigation of an Odoo account) and odoo-mail-retry.py (invalid addresses of registrations and failed e-mails).
#
# VERSION HISTORY (summary — see doc/_email_check.changelog.txt for the full detail):
#   1.2.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.1.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.0.20261016.114848 — First version: syntax, typo suggestion, disposable domains, DNS MX, StopForumSpam, Gravatar, web search.
"""E-mail address checks, without any side effect.

  check(address)              -> {"valid", "reason", "suggestion", "domain", "disposable"} (offline: syntax, typo, disposable list)
  suggest(address)            -> corrected address or None ("marieb.essai@gmail'com" -> "marieb.essai@gmail.com")
  mx_status(domain)           -> "mx" | "a-only" | "none" | "unknown" (dig, host, then getent; no tool: "unknown")
  internet_lookups(email, ips) -> {"stopforumspam": …, "gravatar": …, "web": …} — sends the address to third parties: the CALLER asks first.

Internet lookups are disabled by NGINX_TOOLS_INTERNET=off (tests, servers without outgoing access); every network failure gives
"unknown" (never an exception, never a false "clean"). No cache: an investigation is a deliberate, rare action."""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.2.20261019.150215"

TIMEOUT_S = 8
USER_AGENT = "nginx-tools-email-check/1.0 (+https://www.rencontres-linux.quebec)"
EXTRA_DISPOSABLE_FILE = os.environ.get("NGINX_TOOLS_DISPOSABLE_DOMAINS", "/etc/default/nginx-tools-disposable-domains.conf")

# Popular mailbox domains (Québec first): target of the typo suggestion (distance 1 or 2 from one of these).
POPULAR_DOMAINS = ("gmail.com", "hotmail.com", "hotmail.ca", "outlook.com", "outlook.fr", "live.ca", "live.com", "msn.com", "yahoo.com", "yahoo.ca",
                   "yahoo.fr", "icloud.com", "me.com", "mac.com", "videotron.ca", "sympatico.ca", "bell.net", "cogeco.ca", "cgocable.ca", "globetrotter.net",
                   "telus.net", "shaw.ca", "rogers.com", "protonmail.com", "proton.me", "pm.me", "gmx.com", "gmx.fr", "aol.com", "laposte.net",
                   "orange.fr", "free.fr", "videotron.qc.ca", "umontreal.ca", "ulaval.ca", "etsmtl.ca", "usherbrooke.ca", "uqam.ca", "mcgill.ca", "polymtl.ca")
# Frequent mistakes that a distance cannot guess safely (wrong top-level domain of a known name).
KNOWN_TYPOS = {"gmail.co": "gmail.com", "gmail.con": "gmail.com", "gmail.cm": "gmail.com", "gmail.om": "gmail.com", "gmail.ca": "gmail.com",
               "gmail.fr": "gmail.com", "gmail.comm": "gmail.com", "gmail.cmo": "gmail.com", "gmail.c": "gmail.com", "gmailcom": "gmail.com",
               "hotmail.co": "hotmail.com", "hotmail.con": "hotmail.com", "hotmailcom": "hotmail.com", "hotmail.c": "hotmail.com",
               "outlook.co": "outlook.com", "outlook.con": "outlook.com", "yahoo.co": "yahoo.com", "yahoo.con": "yahoo.com",
               "videotron.com": "videotron.ca", "videotron.qc": "videotron.ca", "videotron.cq": "videotron.ca", "videotron.c": "videotron.ca",
               "sympatico.com": "sympatico.ca", "icloud.co": "icloud.com", "icloud.con": "icloud.com"}
# Disposable (throw-away) mailbox domains: an account created with one of them is a weak sign of bad intent (not a proof).
DISPOSABLE_DOMAINS = {"mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com", "sharklasers.com", "grr.la",
                      "10minutemail.com", "10minutemail.net", "20minutemail.com", "temp-mail.org", "tempmail.com", "tempmail.net", "tempmailo.com",
                      "tempr.email", "temp-mail.io", "yopmail.com", "yopmail.fr", "yopmail.net", "trashmail.com", "trashmail.de", "trashmail.net",
                      "getnada.com", "nada.email", "dispostable.com", "maildrop.cc", "throwawaymail.com", "fakeinbox.com", "mintemail.com", "mohmal.com",
                      "emailondeck.com", "discard.email", "mailnesia.com", "spamgourmet.com", "mytemp.email", "burnermail.io", "mailcatch.com",
                      "moakt.com", "mailpoof.com", "inboxkitten.com", "getairmail.com", "spambox.us", "33mail.com", "anonaddy.me", "mail.tm",
                      "emltmp.com", "linshiyouxiang.net", "bccto.me", "chacuo.net", "027168.com", "dropmail.me", "10mail.org", "tmail.ws",
                      "luxusmail.org", "tmpmail.org", "tmpmail.net", "1secmail.com", "1secmail.org", "1secmail.net", "spam4.me", "incognitomail.com",
                      "mailforspam.com", "jetable.org", "trash-mail.com", "wegwerfmail.de", "einrot.com", "cuvox.de", "armyspy.com", "dayrep.com",
                      "fleckens.hu", "gustr.com", "jourrapide.com", "rhyta.com", "superrito.com", "teleworm.us"}

LOCAL_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
TLD_RE = re.compile(r"^(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{2,59})$")


def _extra_disposable():
    """Domains added by the administrator (one per line, # comments), or an empty set."""
    try:
        with open(EXTRA_DISPOSABLE_FILE, encoding="utf-8", errors="replace") as f:
            return {line.split("#", 1)[0].strip().lower() for line in f if line.split("#", 1)[0].strip()}
    except OSError:
        return set()


def is_disposable(domain):
    d = (domain or "").lower().rstrip(".")
    pool = DISPOSABLE_DOMAINS | _extra_disposable()
    return any(d == x or d.endswith("." + x) for x in pool)


def _distance(a, b, limit=3):
    """Damerau-Levenshtein distance (adjacent transposition counts 1), stopped at `limit`."""
    if abs(len(a) - len(b)) >= limit:
        return limit
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) >= limit:
            return limit
        prev2, prev = prev, cur
    return min(prev[-1], limit)


def _syntax_error(address):
    """None if the address is syntactically valid (practical rules of RFC 5321/5322, not the exotic quoted forms), otherwise the reason (English)."""
    if not address:
        return "empty address"
    if any(c.isspace() for c in address):
        return "space in the address"
    if address.count("@") != 1:
        return "no @ sign" if "@" not in address else "several @ signs"
    local, domain = address.split("@")
    if not local:
        return "nothing before the @ sign"
    if len(local) > 64:
        return "part before the @ sign too long (over 64 characters)"
    if not LOCAL_RE.match(local):
        return "invalid character or dot placement before the @ sign"
    if not domain:
        return "nothing after the @ sign"
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return "invalid domain name"
    if len(ascii_domain) > 253:
        return "domain name too long"
    bad = sorted(set(re.sub(r"[A-Za-z0-9.-]", "", ascii_domain)))
    if bad:
        return "invalid character in the domain name: " + " ".join(bad)
    labels = ascii_domain.rstrip(".").split(".")
    if len(labels) < 2:
        return "domain without a dot (e.g. gmail.com)"
    if not all(LABEL_RE.match(label) for label in labels):
        return "invalid character in the domain name"
    if not TLD_RE.match(labels[-1]):
        return "invalid top-level domain"
    return None


def suggest(address):
    """Corrected address for a typo that can be fixed without guessing who the person is, or None.
    Fixed: spaces, comma / apostrophe / semicolon instead of a dot in the domain, double dots, trailing dot, "gmail.con",
    a domain at distance 1-2 of a popular domain ("gmial.com"), "@@", missing dot before com ("gmailcom")."""
    a = (address or "").strip().strip("<>").strip()
    if not a:
        return None
    a = re.sub(r"\s+", "", a)
    a = re.sub(r"@+", "@", a)
    if a.count("@") != 1:
        return None
    local, domain = a.split("@")
    local = local.strip(".")
    domain = domain.lower()
    domain = re.sub(r"[,;'`´’:]+", ".", domain)
    domain = re.sub(r"\.{2,}", ".", domain).strip(".")
    domain = KNOWN_TYPOS.get(domain, domain)
    if domain not in POPULAR_DOMAINS and not is_disposable(domain):
        best, best_d = None, 3
        for p in POPULAR_DOMAINS:
            dist = _distance(domain, p)
            if dist < best_d:
                best, best_d = p, dist
        # distance 1 always; distance 2 only for long enough names (a short real domain is often 2 edits away from a popular one)
        if best and (best_d == 1 or (best_d == 2 and len(domain) >= 9)):
            domain = best
    fixed = f"{local}@{domain}"
    if fixed == address or _syntax_error(fixed):
        return None
    return fixed


def check(address):
    """Offline analysis: {"valid": True/False, "reason": text or None, "suggestion": text or None, "domain": text, "disposable": True/False}.
    A syntactically valid address can still get a suggestion ("gmial.com": valid syntax, probable typo)."""
    a = (address or "").strip()
    reason = _syntax_error(a)
    domain = a.split("@", 1)[1].lower() if a.count("@") == 1 else ""
    sug = suggest(a)
    if reason is None and sug and sug.split("@")[1] != domain:
        reason = f"probable typo in the domain ({domain})"
    return {"valid": _syntax_error(a) is None, "reason": reason, "suggestion": sug, "domain": domain, "disposable": bool(domain) and is_disposable(domain)}


def _run(cmd, timeout=TIMEOUT_S):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return None, ""


def mx_status(domain):
    """Mail server of the domain: "mx" (MX record), "a-only" (no MX but an address: mail still deliverable, RFC 5321), "none" (domain that
    receives no mail or does not exist), "unknown" (no DNS tool, timeout, NGINX_TOOLS_INTERNET=off)."""
    d = (domain or "").strip().rstrip(".").lower()
    if not d or os.environ.get("NGINX_TOOLS_INTERNET", "").lower() in ("off", "0", "no", "non"):
        return "unknown"
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        return "none"
    if not re.fullmatch(r"[a-z0-9.-]+", d):
        return "none"
    if shutil.which("dig"):
        code, out = _run(["dig", "+short", "+time=3", "+tries=2", "MX", d])
        if code == 0:
            if any(l.strip() and not l.strip().startswith(";") for l in out.splitlines()):
                return "mx" if not re.fullmatch(r"0 \.\s*", out.strip()) else "none"        # "0 ." = null MX (RFC 7505): receives no mail
            code_a, out_a = _run(["dig", "+short", "+time=3", "+tries=2", "A", d])
            return "a-only" if code_a == 0 and out_a.strip() else "none"
    if shutil.which("host"):
        code, out = _run(["host", "-W", "3", "-t", "MX", d])
        if code is not None:
            if "mail is handled by" in out:
                return "none" if re.search(r"mail is handled by 0 \.$", out, re.M) else "mx"
            if "NXDOMAIN" in out or "not found" in out:
                return "none"
            code_a, out_a = _run(["host", "-W", "3", "-t", "A", d])
            return "a-only" if code_a == 0 and "has address" in out_a else "none"
    code, out = _run(["getent", "ahosts", d])
    if code == 0 and out.strip():
        return "unknown"             # the domain exists, but nothing tells whether it receives mail
    return "unknown"


# ---------------------------------------------------------------------------------------------------------------------------
# Internet lookups (the address leaves the server: the caller must have asked)
# ---------------------------------------------------------------------------------------------------------------------------
def internet_allowed():
    return os.environ.get("NGINX_TOOLS_INTERNET", "").lower() not in ("off", "0", "no", "non")


def _fetch(url, timeout=TIMEOUT_S):
    """(HTTP status, text) of a GET; (None, "") on a network failure. Replaceable by the tests (no real network)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, OSError, ValueError):
        return None, ""


def stopforumspam(email=None, ips=()):
    """Spam database StopForumSpam (free, no key): {"email": {"appears", "frequency", "lastseen", "confidence"}, "ip": {address: same}} ;
    None if the service is unreachable. "appears": 0 = never reported (not a proof of innocence)."""
    params = [("json", "")]
    if email:
        params.append(("email", email))
    for ip in list(ips)[:15]:
        params.append(("ip[]", ip))
    status, text = _fetch("https://api.stopforumspam.org/api?" + urllib.parse.urlencode(params))
    if status != 200:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not data.get("success"):
        return None

    def clean(x):
        return {"appears": int(x.get("appears") or 0), "frequency": int(x.get("frequency") or 0), "lastseen": x.get("lastseen") or "",
                "confidence": float(x.get("confidence") or 0)}
    res = {"email": None, "ip": {}}
    em = data.get("email")
    if isinstance(em, list):
        em = em[0] if em else None
    if isinstance(em, dict):
        res["email"] = clean(em)
    ipd = data.get("ip")
    for x in (ipd if isinstance(ipd, list) else [ipd] if isinstance(ipd, dict) else []):
        if isinstance(x, dict) and x.get("value"):
            res["ip"][x["value"]] = clean(x)
    return res


def gravatar(email):
    """True: a Gravatar profile picture exists for this address (often a sign of an address used for years); False: none; None: unreachable."""
    h = hashlib.md5((email or "").strip().lower().encode("utf-8")).hexdigest()       # noqa: S324 — Gravatar's own identifier, not a security use
    status, _ = _fetch(f"https://www.gravatar.com/avatar/{h}?d=404&s=1")
    return True if status == 200 else False if status == 404 else None


def search_url(email):
    """Address of a web search of the exact e-mail (for the person to open in a browser)."""
    return "https://duckduckgo.com/?q=" + urllib.parse.quote(f'"{email}"')


def web_search(email, limit=5):
    """Web search of the exact address (DuckDuckGo, HTML version): {"count": N, "results": [(title, url)], "url": search address} ;
    None if the search engine is unreachable or refuses the request (anti-robot page)."""
    status, text = _fetch("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(f'"{email}"'))
    if status != 200 or not text:
        return None
    if "anomaly" in text.lower() and "result__a" not in text:
        return None
    results = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.S):
        href = html.unescape(m.group(1))
        q = urllib.parse.urlparse(href)
        if q.path.startswith("/l/"):
            href = (urllib.parse.parse_qs(q.query).get("uddg") or [href])[0]
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        results.append((title[:100], href[:200]))
    if not results and "no-results" not in text and "No results" not in text:
        return None
    return {"count": len(results), "results": results[:limit], "url": search_url(email)}


def internet_lookups(email, ips=()):
    """All the Internet lookups of an account: {"stopforumspam", "gravatar", "web"} (each None if unreachable) ; {} if NGINX_TOOLS_INTERNET=off."""
    if not internet_allowed():
        return {}
    return {"stopforumspam": stopforumspam(email if email and "@" in email else None, ips),
            "gravatar": gravatar(email) if email and "@" in email else None,
            "web": web_search(email) if email and "@" in email else None}


def main(argv):
    """python3 apps/_email_check.py ADDRESS… : offline analysis (and DNS MX), one line per address; --internet adds the Internet lookups; --version."""
    if "--version" in argv:
        print(__version__)
        return 0
    internet = "--internet" in argv
    for a in (x for x in argv if not x.startswith("--")):
        c = check(a)
        mx = mx_status(c["domain"]) if c["valid"] or c["suggestion"] else "-"
        print(f"{a}\tvalid={c['valid']}\treason={c['reason'] or '-'}\tsuggestion={c['suggestion'] or '-'}\tdisposable={c['disposable']}\tmx={mx}")
        if internet:
            print(json.dumps(internet_lookups(a), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
