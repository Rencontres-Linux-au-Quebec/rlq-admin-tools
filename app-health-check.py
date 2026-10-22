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
# app-health-check.py — quick check (nginx + application) to run before/after an update, or continuously from
# cron (2-3 times a day recommended). No external dependency: only the Python 3 standard library.
#
#
# Usage:
#   python3 app-health-check.py --create-config          (first installation: generates the configuration)
#   python3 app-health-check.py --target local
#   python3 app-health-check.py --target external -c /etc/default/app-health-check.conf
#   python3 app-health-check.py --target local --verbose
#
#   --target local    : direct TCP connection to 127.0.0.1, Host header forced manually, certificate not verified
#                        (normal: DNS/real routing is deliberately bypassed). Exercises the whole local nginx pipeline,
#                        including the bad-bot exemption for local requests.
#   --target external : connection through the real domain name (real DNS), certificate verified normally. For a TRULY external
#                        test (one that would detect a firewall or DNS problem, or a block specific to an IP range),
#                        run this script from a machine DIFFERENT from the server (your workstation, a small monitoring VPS) — run
#                        from the server itself in "external" mode, it still exercises the whole real nginx path, just from the same machine.
#   --create-config [PATH] : generates the configuration file (default: /etc/default/app-health-check.conf) by
#                        DETECTING on this server: ODOO_PUBLIC_HOST (the name that serves the site) and
#                        ADDITIONAL_PUBLIC_HOSTS (those that redirect to it), from nginx -T and a local HTTPS request
#                        per name; EXPECT_RESTRICTED_ACCESS (true only for « -dev. » or « .dev. »); ODOO_DB
#                        (-d of the systemd unit, otherwise db_name of odoo.conf); EXPECT_GOOGLE_OAUTH (current state of
#                        /web/login). Passwords, SMTP and recipients are left commented out, never guessed.
#                        Permissions 600. If several names serve a site: a question on a terminal, otherwise the first one.
#   --force            : with --create-config, replaces an existing file (.before-create-config copy made).
#   -v/--verbose       : also shows, at the start of the analysis, the detected Odoo version and the configured database
#                        name, as well as every HTTP request made during the checks.
#
# Configuration files (KEY=VALUE, one per line, # for a comment) — see doc/app-health-check.conf.example. READ IN THIS
# ORDER and merged (the last one wins): (1) /etc/default/app-health-check.conf, (2) ~/.app-health-check.conf if it exists;
# the current directory is no longer read; -c/--config: that file ALONE. The files read and the important options are always
# displayed. Recommended permissions: chmod 600, owner root or the user who runs the cron job.
#
# Exit codes: 0 = everything passed. 1 = at least one failure (handy for a cron/systemd job that watches the exit
# code, or for "MAILTO=" in crontab, which automatically sends stdout/stderr when the output is not silent).
# ========================================================================================================================

import argparse
import http.client
import importlib.util
import json
import os
import re
try:                    # line editing in prompts (backspace ^H or ^?, arrows): without readline, input() shows « ^H »
    import readline  # noqa: F401
except ImportError:
    pass
import shlex
import signal
import socket
import smtplib
import shutil
import ssl
import subprocess
import sys
import time
from urllib.parse import urlparse, parse_qs, unquote

__version__ = "2.26.20261020.211944"
# Marker added at the END of the « browser » User-Agent (2.2): our test requests are recognizable in all the
# logs (nginx, Odoo) and excluded from the statistics by web-monitor.py. Matches no pattern of the bot filter.
UA_MARKER = " app-health-check/" + ".".join(__version__.split(".")[:2])

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]


def _start():
    """Common context (apps/_i18n.py: language, configuration, translated print / input, parser); module missing: English, no configuration."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "APP_HEALTH_CHECK_LANG", ("_bbb",))
    except Exception:
        return None


I18N = _start()
LANGUAGE = I18N.langue if I18N else "fr"


def lang_origin():
    """« (LANG=fr_CA.UTF-8) »: which setting decided the display language (apps/_i18n.py 1.17); empty without it."""
    origin = getattr(I18N, "origine_langue", "") if I18N else ""
    return f" ({origin})" if origin else ""
TR = I18N.tr if I18N else (lambda text: text)
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 — every displayed text goes through the translator (no effect when the display language is the source language)


def _target(value):
    if value not in ("local", "external"):
        raise ValueError("local or external")
    return value


# Configuration file options (besides the program's own keys): KEY -> (command-line option, type).
# APP: application (profile), LANGUAGE: en, fr or auto (follow LC_ALL / LANG), TARGET: local or external, VERBOSE: yes / no.
SCHEMA_CONFIG = {"APP": ("app", str), "TARGET": ("target", _target), "VERBOSE": ("verbose", bool)}

# Forces the output encoding to UTF-8, whatever the system locale — cron and some services often run
# with a minimal locale (C/POSIX), which can degrade the display of accented characters, or even
# crash print() with UnicodeEncodeError. reconfigure() exists since Python 3.7.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------------------------------------------------------
# Resolution of the configuration files: -c/--config alone, otherwise /etc/default, then ~ (merged, the last one wins).
# Raises FileNotFoundError (message already written for the user) if none exists.
# ------------------------------------------------------------------------------------------------------------------
def migrate_path(old, new):
    """Renaming of the programs in 2.0: renames the old file or directory if it exists and the new one does NOT exist yet
    (never overwrites); silent if there is nothing to do or if the rights are missing."""
    if os.path.exists(old) and not os.path.exists(new):
        try:
            os.makedirs(os.path.dirname(new) or ".", exist_ok=True)
            os.rename(old, new)
            print(f"Migration (programs renamed, version 2.0): {old} → {new}", file=sys.stderr)
        except OSError:
            pass


def personal_config_path():
    """~/.app-health-check.conf (2.x common rule); a legacy ~/.app-health-check.cfg is renamed to it first (apps/_config.py migrer_ancien)."""
    path = os.path.join(os.path.expanduser("~"), ".app-health-check.conf")
    try:
        spec = importlib.util.spec_from_file_location("_config", os.path.join(SCRIPT_DIR, "apps", "_config.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.migrer_ancien(path)
    except Exception:                                    # noqa: BLE001 — apps/_config.py missing or unreadable: the rule without migration
        return path


def resolve_config_paths(explicit_path):
    """Configuration files to read, IN ORDER (the last one wins) — common rule of the programs:
    /etc/default/app-health-check.conf, THEN ~/.app-health-check.conf if it exists. The current directory is NO LONGER read (2.15):
    the result depended on where the program was started (~/scripts by hand, « / » under systemd). -c/--config: that file
    ALONE, which must exist."""
    if explicit_path:
        if not os.path.isfile(explicit_path):
            raise FileNotFoundError(f"configuration file not found: {explicit_path}")
        return [explicit_path]
    migrate_path("/etc/default/sanity-check-odoo.conf", "/etc/default/app-health-check.conf")
    # Old file of the current directory (read until 2.14): RENAMED to /etc/default if there is none yet, otherwise reported
    # (it is no longer read: its settings have no effect any more).
    migrate_path("./app-health-check.conf", "/etc/default/app-health-check.conf")
    migrate_path("./sanity-check-odoo.conf", "/etc/default/app-health-check.conf")
    candidats = ["/etc/default/app-health-check.conf", personal_config_path()]
    found_list, seen = [], set()
    for candidat in candidats:
        real = os.path.realpath(candidat)
        if os.path.isfile(candidat) and real not in seen:
            found_list.append(candidat)
            seen.add(real)
    for ignore in ("./app-health-check.conf", "./sanity-check-odoo.conf"):
        if os.path.isfile(ignore) and os.path.realpath(ignore) not in seen:
            print(f"WARNING: {os.path.abspath(ignore)} exists but is NO LONGER read (read: /etc/default/app-health-check.conf, then "
                  f"~/.app-health-check.conf) — its settings have no effect; move it: mv {ignore} ~/.app-health-check.conf",
                  file=sys.stderr)
    if not found_list:
        raise FileNotFoundError("no configuration file found. Searched: explicit -c/--config, " + ", ".join(candidats))
    return found_list


# ------------------------------------------------------------------------------------------------------------------
# Loading the configuration (plain KEY=VALUE, no python-dotenv dependency)
# ------------------------------------------------------------------------------------------------------------------
def load_config(paths):
    """Configuration (KEY=VALUE) of a file, or merge of a LIST of files in order: the last one wins."""
    cfg = {}
    for path in ([paths] if isinstance(paths, str) else paths):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def complete_common_mail(cfg):
    """E-mail: if SMTP_HOST is not defined here, the suite's COMMON configuration (/etc/default/nginx-tools-mail.conf, created by
    nginx-hardening.sh --update; apps/_courriel.py) provides the relay, the login, the password (separate file), the sender and the
    recipient. The SMTP_* keys of this program always take precedence. Returns True if the common configuration was used."""
    if cfg.get("SMTP_HOST"):
        return False
    try:
        spec = importlib.util.spec_from_file_location("_courriel", os.path.join(SCRIPT_DIR, "apps", "_courriel.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        common = module.lire_config()
        if not common.get("MAIL_HOST"):
            return False
        cfg["SMTP_HOST"], cfg["SMTP_PORT"] = common["MAIL_HOST"], common.get("MAIL_PORT") or "587"
        cfg["SMTP_SECURITY"] = module.securite(common)
        for key_value, source in (("SMTP_USER", "MAIL_USER"), ("NOTIFY_EMAIL_FROM", "MAIL_FROM"), ("NOTIFY_EMAIL_TO", "MAIL_TO")):
            if not cfg.get(key_value) and common.get(source):
                cfg[key_value] = common[source]
        if not cfg.get("SMTP_PASSWORD"):
            cfg["SMTP_PASSWORD"] = module.lire_mot_de_passe(common)
        cfg["_COURRIEL_COMMUN"] = "1"
        return True
    except Exception:       # component missing or unreadable: the program's own configuration stays alone
        return False


def _with_date(path):
    """« /path (modified on YYYY-MM-DD HH:MM) »: last modification of the configuration file, local time."""
    try:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    except OSError:
        when = "?"
    return f"{os.path.abspath(path)} (modified on {when})"


def show_config_read(cfg, paths, explicit_given):
    """Two lines: WHICH files were read (in order), and the important options that result."""
    if explicit_given:
        read_files = f"{_with_date(paths[0])} (requested by -c/--config: no other file is read)"
    else:
        read_files = ", then ".join(_with_date(c) for c in paths) + (" (the last one wins)" if len(paths) > 1 else "")
    yes_no = lambda key_value: ("yes" if cfg.get(key_value, "false").strip().lower() == "true" else "no") if LANGUAGE != "fr" else ("oui" if cfg.get(key_value, "false").strip().lower() == "true" else "non")
    host_name = cfg.get("ODOO_PUBLIC_HOST") or "(not set)"
    others = len([h for h in cfg.get("ADDITIONAL_PUBLIC_HOSTS", "").replace(",", " ").split() if h])
    mail = (f"{cfg['SMTP_HOST']}:{cfg.get('SMTP_PORT', '587') or '587'} → {cfg['NOTIFY_EMAIL_TO']}"
                if cfg.get("SMTP_HOST") and cfg.get("NOTIFY_EMAIL_TO") else "not configured")
    tests = "credentials configured" if cfg.get("ODOO_TEST_USER") and cfg.get("ODOO_TEST_PASSWORD") else "credentials missing (ignored)"
    print(f"Configuration read: {read_files}")
    print(f"  Options: --lang {LANGUAGE}{lang_origin()} · site {host_name}{f' + {others} other name(s)' if others else ''} · non-public instance: {yes_no('EXPECT_RESTRICTED_ACCESS')}"
          f" · Google sign-in expected: {yes_no('EXPECT_GOOGLE_OAUTH')} · e-mail: {mail}{' (common configuration nginx-tools-mail.conf)' if cfg.get('_COURRIEL_COMMUN') else ''} · functional tests (JSON-RPC): {tests}")


# ------------------------------------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------------------------------------
class SortedHelp(argparse.HelpFormatter):
    """Help options in ALPHABETICAL ORDER (long name, without the dashes: « -h, --help » is sorted under « help »),
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


class Http:
    def __init__(self, connect_host, connect_port, host_header, verify_tls, timeout=15, verbose=False):
        self.connect_host = connect_host
        self.connect_port = connect_port
        self.host_header = host_header
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.cookies = {}
        self.verbose = verbose

    def _connection(self):
        if self.verify_tls:
            ctx = ssl.create_default_context()
        else:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return http.client.HTTPSConnection(
            self.connect_host, self.connect_port, timeout=self.timeout, context=ctx
        )

    def request(self, method, path, body=None, extra_headers=None, follow_redirects=0):
        if self.verbose:
            print(f">>> {method} https://{self.host_header}{path} (actual connection: {self.connect_host})", file=sys.stderr)
        conn = self._connection()
        # Default browser UA for EVERY normal request: "app-health-check/1.0" (the former default) was
        # blocked at least once in real conditions (seen in an nginx-log-audit.sh --details report,
        # bad-bot section), skewing the result of a test that had nothing to do with bot blocking.
        # The few tests that DELIBERATELY check the blocking (curl, SERankingBacklinksBot, etc. — see further
        # down in check_http) pass their own User-Agent through extra_headers, which always takes precedence.
        default_ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" + UA_MARKER
        headers = {"User-Agent": extra_headers.pop("User-Agent", default_ua)} if extra_headers else {
            "User-Agent": default_ua
        }
        if extra_headers:
            headers.update(extra_headers)
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if body is not None:
            headers.setdefault("Content-Type", "application/json")
            headers["Content-Length"] = str(len(body))

        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", self.host_header)
        for k, v in headers.items():
            conn.putheader(k, v)
        conn.endheaders(body.encode("utf-8") if isinstance(body, str) else body)

        resp = conn.getresponse()
        data = resp.read()
        for raw_cookie in resp.msg.get_all("Set-Cookie", []):
            name, _, rest = raw_cookie.partition("=")
            value = rest.split(";", 1)[0]
            self.cookies[name.strip()] = value.strip()
        conn.close()

        if follow_redirects > 0 and resp.status in (301, 302, 303, 307, 308):
            location = resp.getheader("Location")
            if location:
                parsed = urlparse(location)
                next_host_header = parsed.netloc or self.host_header
                next_path = parsed.path or "/"
                if parsed.query:
                    next_path += "?" + parsed.query
                # If the redirection changes domain, it is followed with the SAME connection mode (local/external)
                # but a new Host — useful to check the complete chain (e.g. apex -> www).
                sub = Http(self.connect_host, self.connect_port, next_host_header, self.verify_tls, self.timeout, self.verbose)
                sub.cookies = dict(self.cookies)
                return sub.request(method, next_path, body, dict(extra_headers or {}), follow_redirects - 1)

        return resp.status, dict(resp.getheaders()), data


# ------------------------------------------------------------------------------------------------------------------
# Banner at the start of the analysis: detected Odoo version (public route /web/webclient/version_info, needs
# no authentication) and configured database name. Displayed unconditionally at the start of
# the analysis (not only in verbose mode) — verbose mode also adds the detail of each HTTP request.
# ------------------------------------------------------------------------------------------------------------------
def print_odoo_banner(cfg, target, verbose=False):
    host = cfg["ODOO_PUBLIC_HOST"]
    connect_host = "127.0.0.1" if target == "local" else host
    verify_tls = target != "local"
    client = Http(connect_host, 443, host, verify_tls, verbose=verbose)
    try:
        info = jsonrpc_call(client, "/web/webclient/version_info", {})
        server_version = info.get("server_version", "unknown") if info else "unknown"
    except Exception as e:
        server_version = f"cannot be determined ({e})"
    db_name = cfg.get("ODOO_DB", "(not configured)")
    print(f"Version Odoo detectee : {server_version}")
    print(f"Configured database: {db_name}")


# ------------------------------------------------------------------------------------------------------------------
# HTTP / nginx checks
# ------------------------------------------------------------------------------------------------------------------
def load_profile(force):
    """Profile apps/<name>.conf (detected, or forced by --app / APP_PROFILE); without an apps/ folder: Odoo by default."""
    folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), "apps")
    if not os.path.isfile(os.path.join(folder, "_profile.py")):
        return {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "HEALTH_CHECKS": "odoo",
                "APP_DETECTION": "default (apps/ folder missing next to the program)"}
    sys.path.insert(0, folder)
    import _profile
    return _profile.charger_profil_app(folder, force)


def check_bbb(cfg, target, verbose=False):
    """BigBlueButton-specific checks: home page, API (returncode SUCCESS, version). The HTTP redirection
    to HTTPS and HSTS are checked by check_hsts_multi_host, common to all applications."""
    results = []
    host = cfg["ODOO_PUBLIC_HOST"]
    connect_host = "127.0.0.1" if target == "local" else host
    client = Http(connect_host, 443, host, target != "local", verbose=verbose)
    try:
        status, _, _ = client.request("GET", "/", follow_redirects=3)
        results.append(("Page d'accueil BigBlueButton (/)", status == 200, f"status final: {status}"))
    except Exception as e:
        results.append(("Page d'accueil BigBlueButton (/)", False, f"exception: {e}"))
    try:
        status, _, body = client.request("GET", "/bigbluebutton/api")
        text = body.decode("utf-8", "replace")
        ok = status == 200 and "<returncode>SUCCESS</returncode>" in text
        version = re.search(r"<bbbVersion>([^<]*)</bbbVersion>", text)
        detail = f"status: {status}" + (f", BigBlueButton {version.group(1)}" if version else "")
        if not ok:
            detail += " — expected answer: <returncode>SUCCESS</returncode> (bbb-web stopped? see bbb-conf --status)"
        results.append(("API BigBlueButton (/bigbluebutton/api)", ok, detail))
    except Exception as e:
        results.append(("API BigBlueButton (/bigbluebutton/api)", False, f"exception: {e}"))
    return results


def check_http(cfg, target, verbose=False):
    results = []
    host = cfg["ODOO_PUBLIC_HOST"]
    connect_host = "127.0.0.1" if target == "local" else host
    verify_tls = target != "local"

    def client(host_header=None):
        return Http(connect_host, 443, host_header or host, verify_tls, verbose=verbose)

    # 0) Light probe first: /web/health (Odoo 16 and later). db_server_status=1: Odoo 17/18 also checks the
    # PostgreSQL connection (ignored by Odoo 16). The following checks exercise REAL pages, on purpose:
    # that is how the nginx rules (robots, sensitive files, traversal...) are verified.
    try:
        status, _, body = client().request("GET", "/web/health?db_server_status=1")
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
        label = "Light probe /web/health (application and database)"
        if status == 200 and '"pass"' in text:
            results.append((label, True, "Odoo and PostgreSQL respond (status: pass)"))
        elif status == 404:
            results.append((label, None, "route missing (Odoo older than 16) — the following checks are enough"))
        else:
            results.append((label, False, f"HTTP {status} — Odoo or its database is not responding correctly: {text[:120]}"))
    except Exception as e:
        results.append(("Light probe /web/health", False, f"exception: {e}"))

    # 1) Home page, follows redirections, checks that we land on the right domain.
    try:
        status, headers, body = client().request("GET", "/", follow_redirects=3)
        ok = status == 200
        results.append(("Page d'accueil (/)", ok, f"status final: {status}"))
    except Exception as e:
        results.append(("Page d'accueil (/)", False, f"exception: {e}"))
        body, headers = b"", {}

    # 2) Security headers present on a normal response.
    expected_headers = [
        "X-Frame-Options",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "Permissions-Policy",
    ]
    missing = [h for h in expected_headers if h not in headers]
    results.append(("Security headers present", not missing, f"manquants: {missing}" if missing else "OK"))

    # Non-public instance (EXPECT_RESTRICTED_ACCESS=true): nginx itself serves an « everything forbidden » robots.txt
    # (map $robots_disallow_all in conf.d/odoo-global.conf), in place of the one generated by Odoo — the robots.txt checks
    # therefore expect « Disallow: / » rather than the Sitemap and anti-facet rules of PROD.
    restricted = cfg.get("EXPECT_RESTRICTED_ACCESS", "false").lower() == "true"

    def robots_ok(status, body):
        if restricted:
            return status == 200 and re.search(rb"(?m)^Disallow:\s*/\s*$", body) is not None
        return status == 200 and b"Sitemap" in body

    robots_attendu = "« Disallow: / » (non-public instance)" if restricted else "« Sitemap » (Odoo's robots.txt)"

    def robots_detail(status, body):
        # Public mode but « everything forbidden » robots.txt: two possible causes, with opposite consequences.
        if not restricted and status == 200 and re.search(rb"(?m)^Disallow:\s*/\s*$", body):
            return (f"status: {status} — robots.txt FORBIDS THE WHOLE SITE (« Disallow: / »). Non-public instance "
                    "(DEV/LAB): normal, add EXPECT_RESTRICTED_ACCESS=true to the configuration file "
                    "shown at the top. PROD: SERIOUS, the whole site drops out of the search engines — check the map "
                    "$robots_disallow_all (conf.d/odoo-global.conf) and the robots.txt configured in Odoo.")
        return f"status: {status}, expected: {robots_attendu}"

    # 3) robots.txt (historical bug: wrongly blocked by the .txt extensions rule — see securite-commune.conf)
    try:
        status, _, body_robots = client().request("GET", "/robots.txt")
        ok = robots_ok(status, body_robots)
        results.append(("/robots.txt", ok, robots_detail(status, body_robots)))
    except Exception as e:
        results.append(("/robots.txt", False, f"exception: {e}"))

    # 4) sitemap.xml
    try:
        status, _, _ = client().request("GET", "/sitemap.xml")
        results.append(("/sitemap.xml", status == 200, f"status: {status}"))
    except Exception as e:
        results.append(("/sitemap.xml", False, f"exception: {e}"))

    # 5) Login page + Google OAuth link: checks that redirect_uri points to the REAL domain (regression
    #    test of the fixed bug — redirect_uri used to point to "http://odoo/..." before the fix).
    # EXPECT_GOOGLE_OAUTH in the configuration (true/false, default false): if true, the ABSENCE of the link becomes a real
    # failure (FAIL) rather than a simple piece of information — useful if you know that Google must be active on this
    # instance and want to be alerted if it disappears.
    expect_oauth = cfg.get("EXPECT_GOOGLE_OAUTH", "false").lower() == "true"
    try:
        # follow_redirects: Odoo redirects /web/login to the version in the visitor's language (303 to
        # /en_CA/web/login); without following, the « Redirecting... » page (219 bytes) was analyzed, without a Google link —
        # a false failure although the Google login worked. --create-config already followed redirections, hence
        # EXPECT_GOOGLE_OAUTH=true detected then contradicted by this check.
        status, _, body_login = client().request("GET", "/web/login", follow_redirects=3)
        html = body_login.decode("utf-8", errors="replace")
        http_summary = f"(status /web/login: {status}, {len(body_login)} octets)"
        if verbose:
            dump_path = "/tmp/app-health-check-web-login.html"
            with open(dump_path, "wb") as f:
                f.write(body_login)
            print(f">>> /web/login response saved in {dump_path} (equivalent of the manual curl)", file=sys.stderr)
        m = re.search(r'href="([^"]*accounts\.google\.com[^"]*)"', html)
        if m:
            google_url = m.group(1).replace("&amp;", "&")
            qs = parse_qs(urlparse(google_url).query)
            redirect_uri = unquote(qs.get("redirect_uri", [""])[0])
            expected_prefix = f"https://{host}/auth_oauth/signin"
            ok = redirect_uri == expected_prefix
            if ok:
                detail = f"Google authentication ACTIVE and working — redirect_uri correct: {redirect_uri!r} {http_summary}"
            else:
                detail = (
                    f"Google authentication ACTIVE but BROKEN — redirect_uri obtained {redirect_uri!r}, "
                    f"but expected {expected_prefix!r} {http_summary}"
                )
            results.append(("Authentification Google (OAuth)", ok, detail))
        elif expect_oauth:
            results.append((
                "Authentification Google (OAuth)",
                False,
                f"EXPECTED (EXPECT_GOOGLE_OAUTH=true) but Google link ABSENT from /web/login {http_summary}. "
                "Check, in this order: "
                "(1) Settings > General Settings > 'Integrations' section > 'OAuth Authentication' box checked; "
                "(2) developer mode active, then Settings > Users & Companies > OAuth Authentication > "
                "provider 'Google' > 'Active' box checked AND a Client ID filled in. If this is intended (Google "
                "deliberately disabled), set EXPECT_GOOGLE_OAUTH=false in the configuration to stop this alert. "
                "Run again with -v/--verbose to save the full response and inspect it yourself.",
            ))
        else:
            results.append((
                "Authentification Google (OAuth)",
                None,
                f"INACTIVE on this instance (no Google link on /web/login) {http_summary} — normal if "
                "intended; set EXPECT_GOOGLE_OAUTH=true in the configuration if it must always be active. "
                "Run again with -v/--verbose to save the full response and inspect it yourself.",
            ))
    except Exception as e:
        results.append(("Authentification Google (OAuth)", False, f"exception: {e}"))

    # 6) DB manager: must NOT be open to the public. EXCEPTION: in "local" mode, 127.0.0.1 is
    # now explicitly allowed in env-*.conf (for this script and manual diagnostics) — a 200 is
    # therefore expected and correct there, not a leak. In "external" mode, a 200 stays abnormal unless explicitly configured.
    default_expect_open = "true" if target == "local" else "false"
    expect_open = cfg.get("EXPECT_DB_MANAGER_OPEN", default_expect_open).lower() == "true"
    try:
        status, _, _ = client().request("GET", "/web/database/manager")
        is_open = status == 200
        ok = is_open == expect_open
        detail = f"status: {status} (open expected: {expect_open}, default for this mode: {default_expect_open})"
        if not ok and target == "local" and is_open and "EXPECT_DB_MANAGER_OPEN" in cfg:
            # Typical case: EXPECT_DB_MANAGER_OPEN=false written in the configuration (by --create-config before
            # 1.18), which forces « closed » even locally, where 127.0.0.1 is allowed by the nginx whitelist.
            detail += (" — locally, 127.0.0.1 is on the nginx allow list: 200 is NORMAL. Remove (or comment out) EXPECT_DB_MANAGER_OPEN from the configuration file: the default expectation depends on the mode (closed with --target external, the real check of the protection).")
        results.append(("/web/database/manager stays protected", ok, detail))
    except Exception as e:
        results.append(("/web/database/manager stays protected", False, f"exception: {e}"))

    # 7) Bad-bot blocking: in external mode, a "curl" UA must be blocked (403). In local mode, it must PASS
    #    (exemption $is_internal_client) — both check the same rule from a different angle.
    try:
        status, _, _ = client().request("GET", "/", extra_headers={"User-Agent": "curl/8.14.1"})
        if target == "external":
            ok = status == 403
            results.append(("Bad-bot blocking (external, must be 403)", ok, f"status: {status}"))
        else:
            ok = status != 403
            results.append(("Local exemption from bad-bot blocking", ok, f"status: {status}"))
    except Exception as e:
        results.append(("Blocage bad-bot", False, f"exception: {e}"))

    # 8) A real static file (JS bundle), discovered dynamically from the home page so as never to
    #    depend on a frozen assets hash (which changes with every Odoo update).
    try:
        m = re.search(rb'src="(/web/assets/[^"]+\.js)"', body)
        if m:
            asset_path = m.group(1).decode()
            status, _, _ = client().request("GET", asset_path)
            results.append(("Asset statique JS", status == 200, f"{asset_path} -> {status}"))
        else:
            results.append(("Asset statique JS", None, "no JS asset found in the home page"))
    except Exception as e:
        results.append(("Asset statique JS", False, f"exception: {e}"))

    # 9) New commercial bots added to bot_blocker.conf: must be blocked like the others. Only
    #    meaningful in external mode (locally, $is_internal_client exempts any UA blocking — see check 7).
    if target == "external":
        for bot_ua in ("SERankingBacklinksBot", "GeedoShopProductFinder"):
            try:
                status, _, _ = client().request("GET", "/", extra_headers={"User-Agent": f"Mozilla/5.0 (compatible; {bot_ua}/1.0)"})
                results.append((f"Blocage {bot_ua}", status == 403, f"status: {status}"))
            except Exception as e:
                results.append((f"Blocage {bot_ua}", False, f"exception: {e}"))
    else:
        results.append(("Blocage SERankingBacklinksBot/GeedoShopProductFinder", None,
                         "test not applicable in local mode ($is_internal_client exempts all blocking by UA) — run again with --target external"))

    # 10) /robots.txt must stay reachable EVEN to a recognized bad bot (otherwise it never sees the Disallow that
    #     concerns it — counter-productive). Only meaningful in external mode, for the same reason as above.
    if target == "external":
        try:
            status, _, body_robots_bot = client().request("GET", "/robots.txt", extra_headers={"User-Agent": "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)"})
            ok = robots_ok(status, body_robots_bot)
            results.append(("/robots.txt exempt from bad-bot blocking", ok,
                            f"status: {status}" if ok else robots_detail(status, body_robots_bot)))
        except Exception as e:
            results.append(("/robots.txt exempt from bad-bot blocking", False, f"exception: {e}"))
    else:
        results.append(("/robots.txt exempt from bad-bot blocking", None,
                         "test not applicable in local mode ($is_internal_client exempts all blocking by UA) — run again with --target external"))

    # 11) Directory traversal IN THE QUERY STRING (not only the path): must be blocked by NGINX
    #     (rule 3, securite-commune.conf), not let through to Odoo. Both produce a 404 status, so
    #     the status alone cannot tell them apart — Odoo's error page (rendered by its website
    #     theme, several KB with CSS/JS) is much larger than nginx's minimal 404 page
    #     (a few hundred bytes at most, no layout). A short body is therefore a reliable sign
    #     that NGINX answered, not Odoo.
    try:
        status, _, body_trav = client().request("GET", "/some/page?file=../conf/conf.php")
        blocked_by_nginx = status in (403, 404, 444) and len(body_trav) < 1000
        origin = "probablement nginx" if len(body_trav) < 1000 else "probably Odoo (page too large to be nginx's minimal 404 page)"     # 2.23: no backslash in an f-string (Python 3.8)
        results.append((
            "Traversal in the query string blocked by nginx",
            blocked_by_nginx,
            f"status: {status}, {len(body_trav)} byte(s) — {origin}",
        ))
    except Exception as e:
        results.append(("Traversal in the query string blocked by nginx", False, f"exception: {e}"))
    # Sensitive files refused by nginx ITSELF (rule « location ~ /\. » of securite-commune.conf): small nginx
    # 404 page, never Odoo's 404 page — otherwise these requests reach the application (recommendation of the summary).
    try:
        passes = []
        for path in ("/.env", "/en_CA/.env", "/.git/config"):
            status, _, body = client().request("GET", path)
            if not (status in (403, 404, 444) and len(body) < 1000):
                passes.append(f"{path} → {status}, {len(body)} octet(s)")
        results.append(("Sensitive files denied by nginx (/.env, /en_CA/.env, /.git/config)", not passes,
                        "OK — minimal nginx response" if not passes else
                        "passed to the application: " + " ; ".join(passes) + " — check that the server block includes snippets/securite-commune.conf, with no regex location placed before it"))
    except Exception as e:
        results.append(("Sensitive files denied by nginx", False, f"exception: {e}"))

    # 12) DEV/LAB only (EXPECT_RESTRICTED_ACCESS=true in the configuration): X-Robots-Tag must be present on
    #     EVERY response, including an access refusal (hence "always" on the nginx side); the refused access from a non-
    #     authorized IP only makes sense to check from the outside, and only if the machine running this script
    #     is NOT itself on the whitelist — impossible to guarantee automatically, hence a note rather than
    #     a decided failure/success (see the initial request: "provide an option or a warning").
    if cfg.get("EXPECT_RESTRICTED_ACCESS", "false").lower() == "true":
        try:
            status, headers_dev, _ = client().request("GET", "/")
            has_tag = "X-Robots-Tag" in headers_dev and "noindex" in headers_dev.get("X-Robots-Tag", "")
            results.append(("X-Robots-Tag present (DEV/LAB)", has_tag, f"value: {headers_dev.get('X-Robots-Tag', '(absent)')}"))
            if target == "external":
                note = (
                    f"status obtained: {status} — 200 means that THIS machine's IP is on the whitelist "
                    "(normal if you run this script from a team workstation); 403 confirms that access is "
                    "properly restricted for an unauthorized IP. This script cannot automatically know "
                    "which of the two situations applies — read the status above to decide for yourself."
                )
            else:
                note = "status not meaningful in local mode (127.0.0.1 is always on the allow list)."
            results.append(("DEV/LAB restricted access (to be interpreted manually)", None, note))
        except Exception as e:
            results.append(("X-Robots-Tag present (DEV/LAB)", False, f"exception: {e}"))

    # 13) robots.txt must contain the Disallow rules set manually in Odoo (Website > Configuration
    #     > Settings > Robots.txt) against the facet trap on the events/blog page filters
    #     (e.g. /event?tags=[3,+2] generates a combinatorial explosion of indexable URLs, already seen with
    #     SERankingBacklinksBot exploring these combinations). This setting is made in the Odoo UI, NOT in
    #     a file — this script can only VERIFY it, never apply it itself.
    if restricted:
        results.append(("robots.txt: facet trap /*?tags= blocked", None,
                         "not applicable on a non-public instance (robots.txt « Disallow: / » served by nginx)"))
        return results
    try:
        status, _, body_robots = client().request("GET", "/robots.txt")
        has_tags_disallow = status == 200 and b"Disallow: /*?tags=" in body_robots and b"Disallow: /*&tags=" in body_robots
        if not has_tags_disallow and status == 200 and re.search(rb"(?m)^Disallow:\s*/\s*$", body_robots):
            results.append(("robots.txt: facet trap /*?tags= blocked", None,
                            "not applicable: robots.txt already forbids the whole site (see the /robots.txt line above)"))
            return results
        results.append((
            "robots.txt: facet trap /*?tags= blocked",
            has_tags_disallow,
            (f"status: {status}" if has_tags_disallow else
             "to configure in Odoo: Website → Configuration → Settings → Robots.txt (add Disallow: /*?tags= and Disallow: /*&tags=)"),
        ))
    except Exception as e:
        results.append(("robots.txt: facet trap /*?tags= blocked", False, f"exception: {e}"))

    return results


# ------------------------------------------------------------------------------------------------------------------
# HSTS check + single-hop redirection, on ALL the public names of an instance (not only
# ODOO_PUBLIC_HOST) — only has an effect if ADDITIONAL_PUBLIC_HOSTS is set in the configuration (empty by default,
# hence no impact on DEV/LAB, which have a single name). For PROD: checks that the bare domain and the old name
# odoo18 both redirect to https://www... in a single hop, AND that HSTS is present from the redirection
# itself (not only on the final response) — otherwise a browser that NEVER visited www directly
# before has no HTTPS guarantee before that very first unencrypted round trip (for the HTTP entry).
# ------------------------------------------------------------------------------------------------------------------
TLS_DAYS_THRESHOLD = 21     # certbot renews at 30 days: under 21, the renewal has been failing for at least 9 days


def cert_days(host, connect_host, port=443, timeout=10):
    """(days left, expiry date, issuer, verification error or None) of the certificate presented for
    « host » (SNI). On refusal (expired, name, chain), the certificate is read again without verification to date the expiry."""
    import ssl
    import socket as _socket
    def issuer_of(cert):
        field_list = dict(x[0] for x in cert.get("issuer", ()) if x)
        return field_list.get("organizationName") or field_list.get("commonName") or "?"
    try:
        ctx = ssl.create_default_context()
        with _socket.create_connection((connect_host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        end = ssl.cert_time_to_seconds(cert["notAfter"])
        return int((end - time.time()) // 86400), time.strftime("%Y-%m-%d", time.localtime(end)), issuer_of(cert), None
    except ssl.SSLCertVerificationError as e:
        err = getattr(e, "verify_message", "") or str(e)
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with _socket.create_connection((connect_host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    output = subprocess.run(["openssl", "x509", "-noout", "-enddate", "-issuer"], input=ssl.DER_cert_to_PEM_cert(der),
                            capture_output=True, text=True, timeout=10).stdout
    m = re.search(r"notAfter=(.+)", output)
    end = ssl.cert_time_to_seconds(m.group(1).strip()) if m else None
    o = re.search(r"\bO ?= ?([^,\n/]+)", output)
    return (int((end - time.time()) // 86400) if end else None,
            time.strftime("%Y-%m-%d", time.localtime(end)) if end else "?", o.group(1).strip() if o else "?", err)


def check_tls_certificate(cfg, target, verbose=False):
    """TLS certificate of each public name (ODOO_PUBLIC_HOST, ADDITIONAL_PUBLIC_HOSTS): validity (chain, name,
    expiry), days left — FAILURE under TLS_DAYS_THRESHOLD, hence a web-monitor.py alert — and automatic renewal."""
    results = []
    host_names = [cfg["ODOO_PUBLIC_HOST"]] + [h.strip() for h in cfg.get("ADDITIONAL_PUBLIC_HOSTS", "").split(",") if h.strip()]
    port = int(os.environ.get("APP_HEALTH_TLS_PORT", "443"))
    for h in host_names:
        label = f"TLS certificate — {h}"
        try:
            days, date, issuer, err = cert_days(h, "127.0.0.1" if target == "local" else h, port)
        except Exception as e:
            results.append((label, False, f"TLS connection impossible ({e})"))
            continue
        if err:
            results.append((label, False, f"certificate REFUSED: {err} (expiration : {date}, issuer: {issuer})"))
        elif days is None:
            results.append((label, False, "date d'expiration illisible"))
        elif days < 0:
            results.append((label, False, f"EXPIRED since {-days} day(s) (on {date})"))
        elif days < TLS_DAYS_THRESHOLD:
            results.append((label, False, f"expires in {days} day(s), on {date} — the automatic renewal (at 30 days) "
                                          "seems to be failing: certbot renew --dry-run"))
        else:
            results.append((label, True, f"still valid for {days} days (until {date}), issued by {issuer}"))
    active = [t for t in ("certbot.timer", "snap.certbot.renew.timer") if shutil.which("systemctl")
              and subprocess.run(["systemctl", "is-active", t], capture_output=True, text=True, timeout=10).stdout.strip() == "active"]
    if active or os.path.exists("/etc/cron.d/certbot"):
        results.append(("Automatic certificate renewal", True, ", ".join(active) or "/etc/cron.d/certbot"))
    else:
        results.append(("Automatic certificate renewal", None,
                        "none found (certbot.timer, snap.certbot.renew.timer, /etc/cron.d/certbot) — check how the certificate is renewed"))
    return results


def check_hsts_multi_host(cfg, target, verbose=False):
    results = []
    host = cfg["ODOO_PUBLIC_HOST"]
    extra_hosts = [h.strip() for h in cfg.get("ADDITIONAL_PUBLIC_HOSTS", "").split(",") if h.strip()]
    verify_tls = target != "local"
    browser_ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" + UA_MARKER

    def connect_for(hostname):
        return "127.0.0.1" if target == "local" else hostname

    def check_hsts_on(headers, label):
        hsts = headers.get("Strict-Transport-Security", "")
        present = bool(hsts)
        results.append((f"HSTS present — {label}", present, f"value: {hsts!r}" if present else "absent"))
        if present:
            m = re.search(r"max-age=(\d+)", hsts)
            if m and int(m.group(1)) < 86400:
                results.append((
                    f"HSTS max-age sufficient — {label}", None,
                    f"max-age={m.group(1)}s, still short — normal just after an initial deployment; "
                    "raise it to 31536000 after a few trouble-free days.",
                ))

    if not extra_hosts:
        return results

    # 1) The canonical name itself, in direct HTTPS: normal 200 response, HSTS expected (already tested by check_http,
    #    but reconfirmed here to have the 3 PROD names in the same report, side by side).
    try:
        status, headers, _ = Http(connect_for(host), 443, host, verify_tls, verbose=verbose).request("GET", "/")
        results.append((f"Direct access {host} (HTTPS)", status == 200, f"status: {status}"))
        check_hsts_on(headers, host)
    except Exception as e:
        results.append((f"Direct access {host} (HTTPS)", False, f"exception: {e}"))

    for extra in extra_hosts:
        # 2) HTTP entry (port 80, cleartext): must redirect in ONE hop to https://host/, with HSTS from this
        #    very first response — the Http class only handles HTTPS, simple HTTP request here through http.client.
        try:
            conn = http.client.HTTPConnection(connect_for(extra), 80, timeout=15)
            conn.putrequest("GET", "/", skip_host=True)
            conn.putheader("Host", extra)
            conn.putheader("User-Agent", browser_ua)
            conn.endheaders()
            resp = conn.getresponse()
            resp.read()
            headers_http = dict(resp.getheaders())
            location = resp.getheader("Location", "")
            status_http = resp.status
            conn.close()
            ok_redirect = status_http in (301, 302) and location == f"https://{host}/"
            results.append((
                f"Redirection HTTP {extra} → https://{host}/ in one hop", ok_redirect,
                f"status: {status_http}, Location: {location!r}",
            ))
            check_hsts_on(headers_http, f"{extra} (HTTP, redirection)")
        except Exception as e:
            results.append((f"Redirection HTTP {extra}", False, f"exception: {e}"))

        # 3) Direct HTTPS entry (SNI = extra, without going through port 80): same requirement.
        try:
            status, headers, _ = Http(connect_for(extra), 443, extra, verify_tls, verbose=verbose).request("GET", "/")
            location = headers.get("Location", "")
            ok_redirect = status in (301, 302) and location == f"https://{host}/"
            results.append((
                f"Redirection HTTPS {extra} → https://{host}/ in one hop", ok_redirect,
                f"status: {status}, Location: {location!r}",
            ))
            check_hsts_on(headers, f"{extra} (HTTPS, redirection)")
        except Exception as e:
            results.append((f"Redirection HTTPS {extra}", False, f"exception: {e}"))

    return results


# ------------------------------------------------------------------------------------------------------------------
# Consistency between the instance NAME and EXPECT_RESTRICTED_ACCESS. This option must be active on a development
# instance (non-public: robots.txt « Disallow: / », X-Robots-Tag noindex, IP-restricted access) and ABOVE ALL
# NOT in PROD: there it would make the check EXPECT a « Disallow: / » robots.txt — and so hide exactly the most
# serious failure for a public site, its complete removal from the search engines.
# Detection deliberately STRICT, on public domain names only (those robots see): an entire « dev » label
# followed by a dot — « -dev. » (odoo-dev.example.org), « .dev. » (odoo.dev.example.org) or « dev. »
# at the very start of the name (dev.example.org). Nothing else: no substring (devis, device, developers, mondev), no
# variant (dev2), no « .dev » top-level domain (which also serves real public sites), no other word
# (lab, test...), no machine name.
# ------------------------------------------------------------------------------------------------------------------
DEV_NAME_RE = re.compile(r"(^|[.-])dev\.", re.IGNORECASE)


def nonprod_hint(names):
    """Returns (name, pattern found) for the first domain name containing « -dev. », « .dev. » or starting with
    « dev. », otherwise (None, None)."""
    for name in names:
        n = name.strip()
        m = DEV_NAME_RE.search(n)
        if m:
            return n, f"« {m.group(0)} » in the domain name"
    return None, None


def check_restricted_coherence(cfg, config_path):
    names = [cfg.get("ODOO_PUBLIC_HOST", "")]
    names += [h for h in cfg.get("ADDITIONAL_PUBLIC_HOSTS", "").split(",") if h.strip()]
    hit_name, hit_reason = nonprod_hint(names)
    explicit = "EXPECT_RESTRICTED_ACCESS" in cfg
    restricted = cfg.get("EXPECT_RESTRICTED_ACCESS", "false").strip().lower() == "true"
    label = "Consistency of instance name / EXPECT_RESTRICTED_ACCESS"
    if hit_name and restricted:
        return [(label, True, f"non-public instance ({hit_reason} : {hit_name}), option enabled — consistent")]
    if hit_name and not explicit:
        return [(label, None,
                 f"SUGGESTION : {hit_name} looks like a development instance ({hit_reason}). Add "
                 f"EXPECT_RESTRICTED_ACCESS=true to {config_path}. Why: a development instance must not "
                 "be indexed or probed by robots — nginx serves a « Disallow: / » robots.txt there, an "
                 "X-Robots-Tag noindex header and restricts access by IP; this option tells the script to CHECK these "
                 "protections (without it, it expects Odoo's public robots.txt and reports false failures). If this "
                 "instance is deliberately public, set EXPECT_RESTRICTED_ACCESS=false explicitly to no "
                 "longer see this suggestion.")]
    if hit_name and not restricted:
        return [(label, None,
                 f"{hit_name} looks like a development instance ({hit_reason}), but it is declared "
                 "deliberately public (explicit EXPECT_RESTRICTED_ACCESS=false). Make sure this is intended: "
                 "a public development instance is indexable and probed by robots.")]
    if restricted:
        return [(label, False,
                 "EXPECT_RESTRICTED_ACCESS=true although no domain name (" + ", ".join(n for n in names if n) + ") contains neither « -dev. » nor « .dev. ». If this is PROD: remove this option IMMEDIATELY — it makes the script expect a robots.txt « Disallow: / », which would hide a complete de-indexing of the site. If this really is a non-public instance, its domain name must contain « -dev. » or « .dev. » (e.g. odoo-dev.example.org) to make this failure disappear.")]
    return [(label, True, "public instance, option disabled — consistent")]



# ------------------------------------------------------------------------------------------------------------------
# Functional Odoo checks through JSON-RPC (authentication + reading a few key models)
# ------------------------------------------------------------------------------------------------------------------
def jsonrpc_call(http_client, path, method_params):
    payload = json.dumps({"jsonrpc": "2.0", "method": "call", "params": method_params})
    status, _, body = http_client.request("POST", path, body=payload)
    if status != 200:
        raise RuntimeError(f"HTTP {status} sur {path}")
    data = json.loads(body.decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"].get("data", {}).get("message", str(data["error"])))
    return data.get("result")


# ------------------------------------------------------------------------------------------------------------------
# Check of the initial setup (directories, firewall) — reuses nginx-hardening.sh --check rather than
# reimplementing the same logic in Python: a single source of truth for what makes a complete setup.
# ------------------------------------------------------------------------------------------------------------------
def check_local_setup(verbose=False):
    results = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    setup_script = os.path.join(script_dir, "nginx-hardening.sh")
    if not os.path.isfile(setup_script) or not os.access(setup_script, os.X_OK):
        # Not deployed next to this one — silently ignored rather than failing (same logic as
        # nginx-log-audit.sh, which also skips this check if the script is not found).
        return results
    if verbose:
        print(f">>> {setup_script} --check", file=sys.stderr)
    try:
        proc = subprocess.run(
            [setup_script, "--check"], capture_output=True, text=True, timeout=15,
        )
        output = proc.stdout
    except Exception as e:
        results.append(("Initial setup (directories, firewall)", False, f"exception while running nginx-hardening.sh: {e}"))
        return results

    found_any = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("[OK]"):
            found_any = True
            results.append((f"Setup: {stripped[4:].strip()}", True, "see nginx-hardening.sh --check for details"))
        elif stripped.startswith("[FAIL]"):
            found_any = True
            results.append((f"Setup: {stripped[6:].strip()}", False, "fix with: nginx-hardening.sh --update"))
        elif stripped.startswith("[ATTN]"):
            found_any = True
            results.append((f"Setup: {stripped[6:].strip()}", None, "non-blocking warning — see nginx-hardening.sh --check"))
    if not found_any:
        results.append(("Initial setup (directories, firewall)", None, "nginx-hardening.sh --check produced no recognized line"))
    return results


def check_odoo_functional(cfg, target, verbose=False):
    results = []
    if not cfg.get("ODOO_TEST_USER") or not cfg.get("ODOO_TEST_PASSWORD"):
        results.append(("Tests fonctionnels Odoo (JSON-RPC)", None, "credentials not configured — ignored"))
        return results

    host = cfg["ODOO_PUBLIC_HOST"]
    connect_host = "127.0.0.1" if target == "local" else host
    verify_tls = target != "local"
    client = Http(connect_host, 443, host, verify_tls, verbose=verbose)

    try:
        auth_result = jsonrpc_call(client, "/web/session/authenticate", {
            "db": cfg["ODOO_DB"],
            "login": cfg["ODOO_TEST_USER"],
            "password": cfg["ODOO_TEST_PASSWORD"],
        })
        uid = auth_result.get("uid") if auth_result else None
        results.append(("Test user authentication", bool(uid), f"uid={uid}"))
        if not uid:
            return results
    except Exception as e:
        results.append(("Test user authentication", False, f"exception: {e}"))
        return results

    def call_kw(model, method, args, kwargs=None):
        return jsonrpc_call(client, "/web/dataset/call_kw", {
            "model": model, "method": method, "args": args, "kwargs": kwargs or {},
        })

    try:
        me = call_kw("res.users", "search_read", [[["id", "=", uid]], ["name", "login"]])
        results.append(("res.users read (self)", bool(me), f"{me}"))
    except Exception as e:
        results.append(("res.users read (self)", False, f"exception: {e}"))

    models_to_check = [m.strip() for m in cfg.get("ODOO_SMOKE_MODELS", "res.partner,event.event").split(",") if m.strip()]
    for model in models_to_check:
        try:
            recs = call_kw(model, "search_read", [[], ["id"]], {"limit": 1})
            results.append((f"Lecture {model} (limit 1)", True, f"{len(recs)} record(s) read without error"))
        except Exception as e:
            results.append((f"Lecture {model} (limit 1)", False, f"exception: {e}"))

    return results, client, uid


# ------------------------------------------------------------------------------------------------------------------
# Notifications: e-mail (SMTP) and message in Odoo Discuss
# ------------------------------------------------------------------------------------------------------------------
REPORT_APP_LABEL = ["Odoo"]         # application label in the report header (detected profile)
COLORS = {"OK": "\x1b[1;32m", "SKIP": "\x1b[1;33m", "ATTN": "\x1b[1;33m", "FAIL": "\x1b[1;31m", "ERR": "\x1b[1;31m"}


def color(text, tty=None):
    """Colored labels — [OK] green, [SKIP] and [ATTN] yellow, [FAIL] and [ERR…] red — ONLY on a
    terminal (never in a report sent by e-mail, a redirected output or one read by another program), and
    never with NO_COLOR or TERM=dumb."""
    if tty is None:
        tty = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    if not tty:
        return text
    text = re.sub(r"\[(OK *|SKIP|ATTN|FAIL|ERR[A-ZÉ]*)\]",
                   lambda m: f"{COLORS[m.group(1).strip()[:4].replace('ERRO', 'ERR')]}[{m.group(1)}]\x1b[0m", text)
    return re.sub(r"(Summary: )([1-9]\d* failure\(s\))", "\\1\x1b[1;31m\\2\x1b[0m",
                  re.sub(r"(Summary: )(0 failure\(s\))", "\\1\x1b[1;32m\\2\x1b[0m", text))


def format_report(target, all_results):
    lines = [f"Report app-health-check.py {'v' + __version__} ({REPORT_APP_LABEL[0]}) — target: {target} — "
             f"{time.strftime('%Y-%m-%d %H:%M:%S %Z')}", ""]
    n_fail = 0
    for label, ok, detail in all_results:
        symbol = "OK  " if ok else ("SKIP" if ok is None else "FAIL")
        if ok is False:
            n_fail += 1
        lines.append(f"[{symbol}] {label} — {detail}")
    lines.append("")
    lines.append(f"Summary: {n_fail} failure(s) out of {len(all_results)} check(s).")
    return "\n".join(lines), n_fail


def smtp_security(cfg):
    """starttls (587, default), ssl (465: TLS from the connection) or none (local relay without TLS, e.g. Postfix on
    127.0.0.1:25). Key SMTP_SECURITY; otherwise deduced from the port and the host."""
    mode = (cfg.get("SMTP_SECURITY") or "").strip().lower()
    if mode in ("starttls", "ssl", "none"):
        return mode
    port = int(cfg.get("SMTP_PORT", "587") or 587)
    if port == 465:
        return "ssl"
    if port == 25 and cfg.get("SMTP_HOST", "") in ("127.0.0.1", "localhost", "::1"):
        return "none"
    return "starttls"


def send_email(cfg, subject, body):
    if not cfg.get("SMTP_HOST"):
        raise RuntimeError("SMTP_HOST not configured")
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    msg = EmailMessage()
    msg["Subject"] = TR(subject)
    msg["From"] = cfg.get("NOTIFY_EMAIL_FROM") or f"app-health-check@{socket.getfqdn()}"
    msg["To"] = cfg["NOTIFY_EMAIL_TO"]
    msg["Date"] = formatdate(localtime=True)                        # Date and Message-ID: required by the filters
    msg["Message-ID"] = make_msgid(domain=msg["From"].split("@")[-1].strip("> "))
    msg.set_content(TR(body))
    mode, port = smtp_security(cfg), int(cfg.get("SMTP_PORT", "587") or 587)
    classe = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
    kw = {"context": ssl.create_default_context()} if mode == "ssl" else {}
    with classe(cfg["SMTP_HOST"], port, timeout=15, **kw) as server:
        if mode == "starttls":
            server.starttls(context=ssl.create_default_context())
        if cfg.get("SMTP_USER"):
            server.login(cfg["SMTP_USER"], cfg.get("SMTP_PASSWORD", ""))
        server.send_message(msg)


def _dns(name, type_):
    """DNS records (list of strings) through dig, otherwise host; None if no DNS tool is available."""
    if shutil.which("dig"):
        r = subprocess.run(["dig", "+short", "+time=3", "+tries=1", type_, name], capture_output=True, text=True, timeout=10)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip() and not l.startswith(";")]
    elif shutil.which("host"):
        r = subprocess.run(["host", "-W", "3", "-t", type_, name], capture_output=True, text=True, timeout=10)
        lines = []
        for l in r.stdout.splitlines():
            m = re.search(r"(?:mail is handled by|descriptive text|has address) (.+)$", l)
            if m:
                lines.append(m.group(1).strip())
    else:
        return None
    if type_ == "TXT":                                              # "part 1" "part 2" -> a single string
        return ["".join(re.findall(r'"((?:[^"\\]|\\.)*)"', l)) or l for l in lines]
    return lines


def suggest_spf(cfg, dom):
    """EXACT SPF record to publish for the sender's domain, according to the configured SMTP relay: the relay domain's « include: »
    if it publishes an SPF, otherwise « a: » (addresses of the relay server); local relay: the addresses of this server (mx a)."""
    host_name = (cfg.get("SMTP_HOST") or "").strip().lower()
    if host_name in ("127.0.0.1", "localhost", "::1", ""):
        return f'{dom}. TXT "v=spf1 mx a -all"'
    parties = host_name.split(".")
    parent = ".".join(parties[-2:]) if len(parties) > 2 else host_name
    if parent != host_name and any(t.lower().startswith("v=spf1") for t in (_dns(parent, "TXT") or [])):
        return f'{dom}. TXT "v=spf1 include:{parent} ~all"'
    return f'{dom}. TXT "v=spf1 a:{host_name} ~all"'


def check_email_dns(cfg):
    """Alert e-mail: reachable SMTP relay, MX of the sender and of the recipients, SPF, DMARC, DKIM.
    List of (level OK/ATTN/FAIL, message, [detail lines]) — records to add are indicated."""
    res = []
    if not cfg.get("SMTP_HOST") or not cfg.get("NOTIFY_EMAIL_TO"):
        return [("FAIL", "e-mail not configured (SMTP_HOST and NOTIFY_EMAIL_TO empty)",
                 ["see doc/email-setup.md: choose an SMTP relay, fill in the configuration, then run this test again"])]
    sender = cfg.get("NOTIFY_EMAIL_FROM") or ""
    dom = sender.split("@")[-1].strip("> ").lower() if "@" in sender else ""
    if _dns("example.org", "MX") is None:
        return [("ATTN", "no DNS tool (dig or host): DNS checks impossible", ["apt install bind9-dnsutils"])]
    # SMTP relay reachable
    try:
        socket.create_connection((cfg["SMTP_HOST"], int(cfg.get("SMTP_PORT", "587") or 587)), timeout=5).close()
        res.append(("OK", f"SMTP relay reachable: {cfg['SMTP_HOST']}:{cfg.get('SMTP_PORT', '587')} ({smtp_security(cfg)})", []))
    except OSError as e:
        res.append(("FAIL", f"SMTP relay unreachable: {cfg['SMTP_HOST']}:{cfg.get('SMTP_PORT', '587')} ({e})",
                    ["port blocked by the hosting provider or the firewall? try 587 (STARTTLS) or 465 (SSL)"]))
    # recipients' MX: without MX, the alerts cannot be delivered
    for dest in {d.split("@")[-1].strip("> ").lower() for d in cfg["NOTIFY_EMAIL_TO"].split(",") if "@" in d}:
        mx = _dns(dest, "MX")
        res.append(("OK", f"MX of the recipient {dest} : {', '.join(mx[:3])}", []) if mx else
                   ("FAIL", f"no MX for the recipient domain {dest} : alerts cannot be delivered", []))
    if not dom:
        res.append(("FAIL", "NOTIFY_EMAIL_FROM missing or invalid: the sender must be an address of YOUR domain", []))
        return res
    # sender's MX: receiving servers check that the domain can receive (bounces, replies)
    mx = _dns(dom, "MX")
    res.append(("OK", f"MX of the sender {dom} : {', '.join(mx[:3])}", []) if mx else
               ("FAIL", f"no MX for the sender domain {dom} : e-mails often refused, bounces lost",
                [f"add to DNS: {dom}. MX 10 <mail server of your provider>."]))
    # SPF
    spf = [t for t in (_dns(dom, "TXT") or []) if t.lower().startswith("v=spf1")]
    spf_suggestion = suggest_spf(cfg, dom)
    if not spf:
        res.append(("FAIL", f"no SPF for {dom} : Gmail and Outlook refuse or classify as spam", [f"add to DNS: {spf_suggestion}"]))
    elif len(spf) > 1:
        res.append(("FAIL", f"{len(spf)} SPF records for {dom} : invalid (only one allowed) — merge them", spf))
    elif re.search(r"(^|\s)\+all\b", spf[0]):
        res.append(("FAIL", f"SPF of {dom} ends in « +all »: any server in the world can send on your behalf", [spf[0]]))
    else:
        detail = [spf[0]]
        if cfg["SMTP_HOST"] not in ("127.0.0.1", "localhost") and "include:" not in spf[0] and "ip4:" not in spf[0] and " a " not in f" {spf[0]} ":
            detail.append(f"check that this SPF authorizes the relay {cfg['SMTP_HOST']} (include: of your provider)")
        res.append(("OK" if re.search(r"[-~]all\b", spf[0]) else "ATTN", f"SPF of {dom} present", detail))
    # DMARC
    dmarc = [t for t in (_dns(f"_dmarc.{dom}", "TXT") or []) if t.lower().startswith("v=dmarc1")]
    if not dmarc:
        res.append(("ATTN", f"no DMARC for {dom} : recommended (required by Gmail and Yahoo above small volumes)",
                    [f'add to DNS: _dmarc.{dom}. TXT "v=DMARC1; p=none; rua=mailto:postmaster@{dom}; fo=1"',
                     "then, after a few weeks of uneventful reports: p=quarantine, and finally p=reject"]))
    else:
        p = re.search(r"\bp=(\w+)", dmarc[0])
        res.append(("OK", f"DMARC of {dom} : politique {p.group(1) if p else '?'}", [dmarc[0]]))
    # DKIM (selector provided by the relay)
    selector = (cfg.get("DKIM_SELECTOR") or "").strip()
    if selector:
        dk = [t for t in (_dns(f"{selector}._domainkey.{dom}", "TXT") or []) if "p=" in t]
        res.append(("OK", f"DKIM {selector}._domainkey.{dom} published", []) if dk else
                   ("FAIL", f"DKIM absent: {selector}._domainkey.{dom}", ["publish the TXT record provided by your SMTP relay"]))
    else:
        res.append(("ATTN", "DKIM not verified (DKIM_SELECTOR not set)",
                    ["enable DKIM at your SMTP relay (it generates the key and gives the selector), then publish: "
                     f'SELECTOR._domainkey.{dom}. TXT "v=DKIM1; k=rsa; p=RELAY_PUBLIC_KEY" ; then set DKIM_SELECTOR=SELECTOR']))
    return res


def show_email_dns(cfg):
    n_fail = 0
    for level, message, detail in check_email_dns(cfg):
        print(color(f"[{level}] {message}"))
        for d in detail:
            print(f"       {d}")
        n_fail += level == "FAIL"
    return 1 if n_fail else 0


def test_email(cfg):
    """--test-email: DNS check, then real sending of a test e-mail, with a diagnosis on failure."""
    code = show_email_dns(cfg)
    if not cfg.get("SMTP_HOST") or not cfg.get("NOTIFY_EMAIL_TO"):
        return 1
    print()
    try:
        send_email(cfg, f"[app-health-check] Send test — {socket.gethostname()}",
                   f"Test e-mail sent by app-health-check.py {'v' + __version__} from {socket.gethostname()}.\n"
                   "If it arrives in the inbox (not in the spam folder), the alerts will arrive too.\n")
        print(color(f"[OK] test e-mail sent to {cfg['NOTIFY_EMAIL_TO']} — check it was received, and that it is NOT classified as spam"))
        return code
    except smtplib.SMTPAuthenticationError:
        print(color("[FAIL] authentication refused by the relay (SMTP_USER / SMTP_PASSWORD) — application password?"))
    except smtplib.SMTPRecipientsRefused as e:
        print(color(f"[FAIL] recipient refused by the relay: {e}"))
    except smtplib.SMTPSenderRefused as e:
        print(color(f"[FAIL] sender refused by the relay (NOTIFY_EMAIL_FROM must be an authorized address): {e}"))
    except (ssl.SSLError, smtplib.SMTPNotSupportedError) as e:
        print(color(f"[FAIL] TLS negotiation impossible ({e}) — check SMTP_PORT and SMTP_SECURITY (starttls, ssl or none)"))
    except (OSError, smtplib.SMTPException) as e:
        print(color(f"[FAIL] sending impossible: {e}"))
    return 1


def post_to_discuss(cfg, client, body):
    channel_name = cfg.get("ODOO_DISCUSS_CHANNEL")
    if not channel_name or client is None:
        return
    model = cfg.get("ODOO_DISCUSS_MODEL", "discuss.channel")  # "mail.channel" on Odoo <17
    try:
        channels = jsonrpc_call(client, "/web/dataset/call_kw", {
            "model": model, "method": "search_read",
            "args": [[["name", "=", channel_name]], ["id"]], "kwargs": {"limit": 1},
        })
        if not channels:
            return
        channel_id = channels[0]["id"]
        jsonrpc_call(client, "/web/dataset/call_kw", {
            "model": model, "method": "message_post",
            "args": [[channel_id]], "kwargs": {"body": TR(body).replace("\n", "<br/>")},
        })
    except Exception:
        pass  # the Discuss notification is a bonus, it must never make the main script fail


# ------------------------------------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------------------------------------
# --create-config: generates the configuration file by DETECTING what can be on this server (public names,
# non-public instance or not, database, Google connection state), and leaving commented out what must
# never be guessed (passwords, SMTP, recipients). Avoids forgetting a setting such as
# EXPECT_RESTRICTED_ACCESS, and values copied from another server.
# ------------------------------------------------------------------------------------------------------------------
DEFAULT_CONFIG_PATH = "/etc/default/app-health-check.conf"
ODOO_CONF_CANDIDATES = ["/opt/odoo/erplibre/config.conf", "/home/utilisateur/git/erplibre/config.conf", "/etc/odoo/odoo.conf"]
ODOO_SERVICE_CANDIDATES = ["erplibre.service", "erplibre_erplibre.service"]


def run_cmd(cmd, verbose=False):
    """Runs an external command (shown if --verbose); returns its output, or "" on failure."""
    if verbose:
        print("+ " + shlex.join(cmd), file=sys.stderr)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def nginx_server_names(verbose=False):
    """Names declared by server_name in the active nginx configuration (all files of « nginx -T », snippets included),
    without comments, without « _ » (catch-all), without regular expressions and generic names."""
    names = []
    for line in run_cmd(["nginx", "-T"], verbose).splitlines():
        line = line.split("#", 1)[0]
        for m in re.finditer(r"(?:^|[\s;{])server_name\s+([^;]+);", line):
            for n in m.group(1).split():
                if n != "_" and not n.startswith("~") and "*" not in n and n not in names:
                    names.append(n)
    return names


def classify_public_names(names, verbose=False):
    """Queries each name in local HTTPS (right SNI, certificate not verified): a name that REDIRECTS to another host
    is an additional name; a name that answers itself (including a redirection to its own host, e.g. the
    language on « / ») serves the site. Returns (servers, {additional_name: target}, unreachable)."""
    servers, redirects, unreachable = [], {}, []
    for name in names:
        try:
            status, headers, _ = Http("127.0.0.1", 443, name, False, verbose=verbose).request("GET", "/")
        except Exception:
            unreachable.append(name)
            continue
        location = next((v for k, v in headers.items() if k.lower() == "location"), "")
        target = (urlparse(location).hostname or "").lower() if location else ""
        if 300 <= status < 400 and target and target != name.lower():
            redirects[name] = target
        else:
            servers.append(name)
    return servers, redirects, unreachable


def detect_odoo_db(verbose=False):
    for svc in ODOO_SERVICE_CANDIDATES:
        out = run_cmd(["systemctl", "cat", svc], verbose)
        m = re.search(r"^ExecStart=.*?(?:\s-d\s+|\s--database[= ]|\s-d)(\S+)", out, re.M)
        if m:
            return m.group(1), f"systemd unit {svc} (ExecStart … -d)"
    for conf in ODOO_CONF_CANDIDATES:
        try:
            with open(conf, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^\s*db_name\s*=\s*(\S+)\s*$", line)
                    if m and m.group(1).lower() not in ("false", "none"):
                        return m.group(1), f"{conf} (db_name)"
        except OSError:
            continue
    return "", None


def detect_google_oauth(host, verbose=False):
    try:
        _, _, body = Http("127.0.0.1", 443, host, False, verbose=verbose).request("GET", "/web/login", follow_redirects=2)
        return b"accounts.google.com" in body
    except Exception:
        return None


def create_config(path, force=False, verbose=False, profile=None):
    print(f"Creating the configuration file: {path}")
    if os.path.exists(path) and not force:
        print(f"ERROR: {path} already exists — nothing was modified. Run again with --force to replace it (a backup copy "
              f"{path}.before-create-config will be made).", file=sys.stderr)
        return 1
    detected = []

    names = nginx_server_names(verbose)
    servers, redirects, unreachable = classify_public_names(names, verbose) if names else ([], {}, [])
    if not names:
        detected.append(("ODOO_PUBLIC_HOST", "NOT DETECTED", "« nginx -T » returned nothing (nginx missing, or not root?)"))
    if len(servers) > 1 and sys.stdin.isatty():
        print("Several names serve a site on this server:")
        for i, n in enumerate(servers, 1):
            print(f"  {i}) {n}")
        choice = input(f"Which one is the instance to check? [1-{len(servers)}, default 1] ").strip()
        idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(servers) else 0
        servers = [servers[idx]] + [n for i, n in enumerate(servers) if i != idx]
    public_host = servers[0] if servers else ""
    additional = [n for n, t in redirects.items() if public_host and t == public_host.lower()]
    if public_host:
        src = "only name that serves the site" if len(servers) == 1 else f"choisi parmi {', '.join(servers)}"
        detected.append(("ODOO_PUBLIC_HOST", public_host, f"nginx -T + local HTTPS request ({src})"))
        detected.append(("ADDITIONAL_PUBLIC_HOSTS", ",".join(additional) or "(none)",
                         "names that redirect to the main name"))

    hit_name, hit_reason = nonprod_hint([public_host] + additional)
    restricted = "true" if hit_name else "false"
    detected.append(("EXPECT_RESTRICTED_ACCESS", restricted,
                     f"development instance: {hit_reason} ({hit_name})" if hit_name
                     else "no name contains « -dev. » or « .dev. »: public instance"))

    if (profile or {}).get("HEALTH_CHECKS", "odoo") == "odoo":
        db, db_src = detect_odoo_db(verbose)
        detected.append(("ODOO_DB", db or "NOT DETECTED", db_src or "neither a systemd unit (-d), nor db_name in odoo.conf"))
        google = detect_google_oauth(public_host, verbose) if public_host else None
        google_val = "true" if google else "false"
        detected.append(("EXPECT_GOOGLE_OAUTH", google_val,
                         "Google link present on /web/login today" if google
                         else ("Google link absent from /web/login" if google is False else "page /web/login injoignable")))
    else:
        # Other application (e.g. BigBlueButton): neither an Odoo database nor a Google connection to detect.
        db, db_src, google, google_val = None, None, None, "false"
        detected.append(("ODOO_DB", "not applicable", f"application {profile.get('APP_LABEL')} : no Odoo database"))

    now = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    content = f"""# ==================================================================================================================\n# Configuration of app-health-check.py — generated on {now} by: app-health-check.py --create-config\n# (version {__version__}). Values marked « detected »: verified on this server at generation time.\n# Permissions 600: this file will hold passwords. See doc/app-health-check.conf.example for details.\n# ==================================================================================================================\n\n# --- Language and command-line options (the command line takes precedence) ---\n# LANGUAGE: en, fr or auto (follow LC_ALL / LANG); TARGET: local or external (--target); APP: application profile (--app); VERBOSE: true or false.\n#LANGUAGE=auto\n#TARGET=\n#APP=\n#VERBOSE=false\n\n# --- Target (detected: nginx -T + local HTTPS request on each name) ---\nODOO_PUBLIC_HOST={public_host}\n# Names that redirect to ODOO_PUBLIC_HOST (checked: HSTS from the redirect, a single hop).\nADDITIONAL_PUBLIC_HOSTS={",".join(additional)}\n\n# --- Non-public instance? (detected: « -dev. » or « .dev. » in a domain name) ---\n# true ONLY on a development instance (robots.txt « Disallow: / », X-Robots-Tag, access restricted by\n# IP); NEVER in PROD, where it would hide a complete de-indexing of the site.\nEXPECT_RESTRICTED_ACCESS={restricted}\n\n# --- Odoo (detected: {db_src or "NOT DETECTED — to fill in"}) ---
ODOO_DB={db}\n# DEDICATED test user, minimal rights (read-only) — to create in Odoo, never an administrator account.\n# Without these two values, the JSON-RPC functional tests are simply ignored.\n#ODOO_TEST_USER=sanity.check@example.org\n#ODOO_TEST_PASSWORD=\nODOO_SMOKE_MODELS=res.partner,event.event\n\n# --- Expected behaviors ---\n# Database manager: do NOT set in normal times. The expectation depends on the mode: open locally (127.0.0.1 is\n# on the nginx allow list), closed in external. A value here would apply to BOTH modes (false failure locally).\n#EXPECT_DB_MANAGER_OPEN=\n# Detected: {"Google link present today — its disappearance will be reported" if google else "Google link absent today"}.
EXPECT_GOOGLE_OAUTH={google_val}\n\n# --- E-mail notification (optional — never guessed) ---\n#SMTP_HOST=\n#SMTP_PORT=587\n#SMTP_USER=\n#SMTP_PASSWORD=\n#NOTIFY_EMAIL_FROM=\n#NOTIFY_EMAIL_TO=\n#SMTP_SECURITY=        # starttls (587, default), ssl (465) or none (local relay without TLS) — see doc/email-setup.md\n#DKIM_SELECTOR=        # DKIM selector provided by the relay (checked by --check-email-dns)\n\n# --- Notification in Odoo Discuss (optional) ---\n#ODOO_DISCUSS_CHANNEL=Sanity Check\n#ODOO_DISCUSS_MODEL=discuss.channel\n"""
    if os.path.exists(path):
        migrate_path(path + ".avant-create-config", path + ".before-create-config")      # English name (2.1)
        backup = path + ".before-create-config"
        with open(path, "rb") as src_f, open(backup, "wb") as dst_f:
            dst_f.write(src_f.read())
        os.chmod(backup, 0o600)
        print(f"Backup copy of the old file: {backup}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(TR(content))
    os.chmod(path, 0o600)

    print()
    print("Detected values:")
    for key, val, why in detected:
        print(f"  {key:26} = {val}")
        print(f"  {'':26}   ({why})")
    if unreachable:
        print(f"  (no local HTTPS answer, ignored: {', '.join(unreachable)})")
    print()
    print(f"File written: {path} (permissions 600)")
    print("To do next:")
    if not public_host or not db:
        print("  - Fill in the values marked NOT DETECTED.")
    print("  - (optional) Create a dedicated read-only Odoo user and fill in ODOO_TEST_USER/ODOO_TEST_PASSWORD.")
    print("  - (optional) Uncomment the SMTP section to receive the report by e-mail.")
    print("  - Run: app-health-check.py --target local   (then --target external from another machine)")
    return 0


def changelog_path(name):
    """CHANGELOG.md at the root of the repository (next to the program)."""
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), "CHANGELOG.md")


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
    """Shows CHANGELOG.md: version numbers in bold cyan if the output is a terminal (standard
    ANSI color, which follows the terminal theme), plain text if it is redirected; a reader that closes early
    (e.g. « | head ») ends cleanly, without a Python traceback."""
    # SIGPIPE keeps its default behavior (like cat or grep): if the reader closes early (« | head »), the
    # process stops silently. Python ignores it otherwise, and a BrokenPipeError can occur until the final
    # flush of the buffers (« Exception ignored on flushing sys.stdout »), out of reach of any try/except.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    path = changelog_path("CHANGELOG.md")
    try:
        text = changelog_section(path, "app-health-check.py")
    except OSError:
        print(f"Changelog not found: {path}", file=sys.stderr)
        return 1
    if sys.stdout.isatty():
        text = re.sub(r"(\d+\.\d+\.\d{8}\.\d{6})", "\x1b[1;36m\\1\x1b[0m", text)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


def main():
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(description="Health check of nginx + Odoo")
    parser.add_argument("--target", choices=["local", "external"], required=False,
                        help="Connection mode (required, except with --create-config)")
    parser.add_argument("--check-email-dns", action="store_true",
                        help="Check the alert e-mail: SMTP relay, MX, SPF, DMARC, DKIM (records to add)")
    parser.add_argument("--test-email", action="store_true",
                        help="DNS checks of the e-mail, then actually send a test e-mail")
    parser.add_argument("--create-config", nargs="?", const=DEFAULT_CONFIG_PATH, metavar="PATH",
                        help=f"Create the configuration file by detecting the values on this server "
                             f"(default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--changelog", action="store_true",
                        help="Show the change log (version numbers in color on a terminal)")
    parser.add_argument("--app", metavar="NAME",
                        help="Application behind nginx (profile apps/NAME.conf: odoo, bbb…) — detected automatically by default")
    parser.add_argument("--force", action="store_true",
                        help="With --create-config: replace an existing file (backup copy made)")
    parser.add_argument("-c", "--config", required=False, metavar="FILE",
                         help="This configuration file ALONE (default: /etc/default/app-health-check.conf, then ~/.app-health-check.conf; command-line options in the file: APP, LANGUAGE, TARGET, VERBOSE)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("-v", "--verbose", action="store_true",
                         help="Show the Odoo version, the database, and each HTTP request")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--version", action="version", version=f"app-health-check.py version {__version__}")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version prints it by itself)
        print(f"app-health-check.py v{__version__}")
    defauts, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    for problem in problems:
        print(f"  WARNING: configuration value ignored: {problem}", file=sys.stderr)

    if args.changelog:
        sys.exit(show_changelog())

    try:
        profile = load_profile(args.app)
    except Exception as e:            # ProfileError (message already written for the user)
        if not (args.check_email_dns or args.test_email):
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)
        # E-mail: independent of the application (workstation without Odoo or BBB, application not detected).
        profile = {"APP_LABEL": "no application detected", "APP_DETECTION": "not applicable for e-mail"}
    print(f"Application : {profile['APP_LABEL']} ({profile['APP_DETECTION']})")
    if args.create_config:
        sys.exit(create_config(args.create_config, force=args.force, verbose=args.verbose, profile=profile))
    # --check-email-dns and --test-email do not query the site: --target is useless (2.10 — forgotten in 2.8, step 13
    # of nginx-hardening.sh received the program's help instead of the diagnosis).
    if not args.target and not (args.check_email_dns or args.test_email):
        parser.error("argument --target required (local or external), except with --create-config, --check-email-dns or --test-email")

    try:
        config_paths = resolve_config_paths(args.config)
    except FileNotFoundError as e:
        # First run (2.11): default configuration created automatically (detected values, same
        # function as --create-config), unless an explicit path was given or without write rights.
        if args.config or not os.access(os.path.dirname(DEFAULT_CONFIG_PATH) or ".", os.W_OK):
            print(f"ERROR: {e}", file=sys.stderr)
            print(f"  To create it: app-health-check.py --create-config (as root: {DEFAULT_CONFIG_PATH})", file=sys.stderr)
            sys.exit(2)
        print(f"No configuration: creating {DEFAULT_CONFIG_PATH} with the detected values (to check afterwards).")
        if create_config(DEFAULT_CONFIG_PATH, force=False, verbose=args.verbose, profile=profile) != 0 or not os.path.isfile(DEFAULT_CONFIG_PATH):
            print(f"ERROR: creating {DEFAULT_CONFIG_PATH} impossible — app-health-check.py --create-config", file=sys.stderr)
            sys.exit(2)
        config_paths = [DEFAULT_CONFIG_PATH]
    cfg = load_config(config_paths)
    complete_common_mail(cfg)
    # File quoted in the messages (where to add a setting): the /etc/default one if it is read, otherwise the first.
    config_path = DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH in config_paths else config_paths[0]
    # Always displayed (and no longer only in --verbose): several locations are read, and a « forgotten » setting
    # (e.g. EXPECT_RESTRICTED_ACCESS) often comes from reading a different file from the one that was edited.
    show_config_read(cfg, config_paths, bool(args.config))
    if args.check_email_dns:
        sys.exit(show_email_dns(cfg))
    if args.test_email:
        sys.exit(test_email(cfg))

    client_for_discuss = None
    all_results = check_restricted_coherence(cfg, os.path.abspath(config_path))
    if profile.get("HEALTH_CHECKS") == "bbb":
        all_results += check_bbb(cfg, args.target, verbose=args.verbose)
        all_results += check_hsts_multi_host(cfg, args.target, verbose=args.verbose)
        all_results += check_tls_certificate(cfg, args.target, verbose=args.verbose)
    else:
        print_odoo_banner(cfg, args.target, verbose=args.verbose)
        all_results += check_http(cfg, args.target, verbose=args.verbose)
        all_results += check_hsts_multi_host(cfg, args.target, verbose=args.verbose)
        all_results += check_tls_certificate(cfg, args.target, verbose=args.verbose)
        all_results += check_local_setup(verbose=args.verbose)
        odoo_check = check_odoo_functional(cfg, args.target, verbose=args.verbose)
        if isinstance(odoo_check, tuple):
            odoo_results, client_for_discuss, _uid = odoo_check
            all_results += odoo_results
        else:
            all_results += odoo_check

    REPORT_APP_LABEL[0] = profile.get("APP_LABEL", "Odoo")
    report, n_fail = format_report(args.target, all_results)
    print(color(report))

    subject = f"[{'ERROR' if n_fail else 'OK'}] Health check {profile['APP_LABEL']} ({args.target}) — {n_fail} failure(s)"
    # E-mail report ONLY if SMTP is configured (2.9: 2.8 called send_email unconditionally and the
    # program stopped on « SMTP_HOST not configured » after checking everything). Sending failure: reported, no stop.
    if cfg.get("SMTP_HOST") and cfg.get("NOTIFY_EMAIL_TO"):
        try:
            send_email(cfg, subject, report)
        except Exception as e:
            print(color(f"[FAIL] sending the report by e-mail impossible: {e} — diagnosis: app-health-check.py --test-email"))
    try:
        post_to_discuss(cfg, client_for_discuss, report)
    except Exception as e:
        print(color(f"[FAIL] publishing the report in Discuss impossible: {e}"))

    sys.exit(1 if n_fail else 0)


def launch_with_report(func):
    """--report-err: copies the output and prints at the end of the run an error report to copy and paste (apps/_rapport.py).
    Without the option (or with --help, --version, --changelog): normal run."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        folder = os.path.dirname(os.path.abspath(__file__))
        try:
            spec = importlib.util.spec_from_file_location("_rapport", os.path.join(folder, "apps", "_rapport.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"--report-err indisponible ({e}) — normal run.", file=sys.stderr)
            return func()
        return module.lancer(func, os.path.basename(__file__), __version__, folder)
    return func()


def protected_main():
    """main() with Ctrl-C cleanly interrupted (code 130, no traceback)."""
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu (Ctrl-C).", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(launch_with_report(protected_main))
