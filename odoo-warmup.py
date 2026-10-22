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
# odoo-warmup.py — WARMS UP the Odoo cache after a restart or a module update: the first users no longer suffer the 5 to 10 seconds
# needed to build assets (JS/CSS), compiled views and menus.
#   * PUBLIC pages (no password): home, /web/login, /event, /survey... (PAGES list of the configuration file) and all the assets (/web/assets/...) these
#     pages request.
#   * ADMINISTRATION screens (key LOGIN and file KEY_FILE: an Odoo API key, never a password on the command line): login, page
#     /odoo (web client and its assets), menus, then get_views (list, form, search, kanban) of each model of MODELS (events, surveys,
#     registrations, contacts... to adapt). Use a dedicated read-only user; the calls modify NOTHING.
#   * Odoo has several processes (workers) and some caches are PER process: each request is repeated --repeat times IN PARALLEL to reach several
#     processes (no guarantee to reach them all, but the assets are shared through the database).
#   * Waits for Odoo to answer (--wait seconds at most): can be started right after the start.
#   * Automatic start: --systemd-install adds to Odoo's unit (--service) a .d file that starts this program in the background after each start
#     (systemd-run, without delaying Odoo's start); --systemd-remove removes it.
# Configuration (common rule): /etc/default/odoo-warmup.conf THEN ~/.odoo-warmup.conf (the last one wins); -c/--config: that file ALONE; the command line
# takes priority. The files read are always displayed, with the important options.
#
#
# Usage:
#   odoo-warmup.py                          warm up (public pages; plus administration if LOGIN and KEY_FILE are set)
#   odoo-warmup.py --url http://127.0.0.1:8069 --db linux_meetup_odoo_18
#   odoo-warmup.py --repeat 6 --wait 180    6 parallel passes; waits for Odoo 180 s at most
#   odoo-warmup.py --systemd-install --service odoo-linux_meetup.service     starts the warm-up after each Odoo start
#   odoo-warmup.py --systemd-remove --service odoo-linux_meetup.service
#   --lang en|fr, --report-err, --verbose, --version, --changelog

import argparse
import concurrent.futures
import http.cookiejar
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:                    # line editing in prompts
    import readline  # noqa: F401
except ImportError:
    pass

__version__ = "1.9.20261020.211944"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
SYSTEM_CONF = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), "odoo-warmup.conf")      # variable: tests only
USER_CONF = "~/.odoo-warmup.conf"
SYSTEMD_DIR = os.environ.get("NGINX_TOOLS_SYSTEMD_DIR", "/etc/systemd/system")                       # variable: tests only
DEFAULT_URL = "http://127.0.0.1:8069"
DEFAULT_PAGES = ["/", "/web/login", "/event", "/survey"]
DEFAULT_MODELS = ["event.event", "event.registration", "event.event.ticket", "survey.survey", "survey.user_input", "res.partner"]
VIEWS = [[False, "list"], [False, "form"], [False, "search"], [False, "kanban"]]
DEFAULT_REPETITIONS, DEFAULT_WAIT, REQUEST_TIMEOUT = 4, 120, 120
DEFAULT_LINKS, DEFAULT_LATEST = 6, 5                    # linked pages discovered in the public pages; latest events / surveys (administration)
LATEST_KINDS = (("event.event", "website_url", "events"), ("survey.survey", "survey_start_url", "surveys"))
DEFAULT_SERVICE = "odoo.service"
DEFAULT_LANGUAGES = "fr,en,es"                             # site languages warmed up for each public page (key LANGS, --site-languages)
PAGES_FILE = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), "odoo-warmup-pages.conf")      # extra pages, one per line
VERBOSE = False


def load_module(name):
    """Component of apps/ (None if absent)."""
    path = os.path.join(SCRIPT_DIR, "apps", name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _start():
    """Common context (apps/_i18n.py: language, translated print / input, parser); module absent: source language."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "ODOO_WARMUP_LANG", ())
    except Exception:
        return None


I18N = _start()
LANGUAGE = I18N.langue if I18N else "fr"


def lang_origin():
    """« (LANG=fr_CA.UTF-8) »: which setting decided the display language (apps/_i18n.py 1.17); empty without it."""
    origin = getattr(I18N, "origine_langue", "") if I18N else ""
    return f" ({origin})" if origin else ""
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 — every displayed text goes through the translator (no effect when the display language is the source language)


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)

def personal_conf():
    """Personal configuration file to read: ~/.odoo-warmup.conf; a legacy ~/.odoo-warmup.cfg is renamed to it first (apps/_config.py migrer_ancien)."""
    path = os.path.expanduser(USER_CONF)
    try:
        return load_module("_config").migrer_ancien(path)
    except Exception:
        return path


def read_config(explicite=None):
    """(values, files read, problems): /etc/default/odoo-warmup.conf then ~/.odoo-warmup.conf (the last one wins); explicit (-c/--config):
    that file ALONE, which must exist (FileNotFoundError otherwise). Keys: URL, DB, LOGIN, KEY_FILE, PAGES_FILE, LANGS, PAGES and MODELS (comma-separated lists),
    REPEAT and WAIT (positive numbers), LINKS and LATEST (numbers, 0 = none), SERVICE, LANGUAGE (en, fr, auto)."""
    values, files_read, problems = {}, [], []
    if explicite and not os.path.isfile(explicite):
        raise FileNotFoundError(f"configuration file not found: {explicite}")
    if not explicite:                                          # first start: creates the default file (all options commented out)
        try:
            load_module("_config").creer_par_defaut("odoo-warmup")
        except Exception:
            pass
    common = []                                               # COMMON file for all programs (app-default.conf), read first: LANGUAGE, VERBOSE, DEBUG_LEVEL only
    if not explicite:
        try:
            common = [c for c, exists_ in load_module("_config").chemins_communs() if exists_]
        except Exception:
            common = []
    for path in (common if not explicite else []) + ([explicite] if explicite else [SYSTEM_CONF, personal_conf()]):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        files_read.append(path)
        for n, line in enumerate(lines, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            m = re.fullmatch(r"(REPEAT|WAIT|LINKS|LATEST)\s*=\s*[\"']?(\d+)[\"']?", line)
            v = re.fullmatch(r"(VERBOSE|DEBUG_LEVEL)\s*=\s*[\"']?(\w*)[\"']?", line)
            if path in common and not (v or re.match(r"LANGUAGE\s*=", line)):
                continue                                       # the common file defines only LANGUAGE, VERBOSE and DEBUG_LEVEL
            t = re.fullmatch(r"(URL|DB|LOGIN|KEY_FILE|PAGES|PAGES_FILE|LANGS|MODELS|SERVICE|LANGUAGE)\s*=\s*[\"']?([^\"']*)[\"']?", line)
            if m and (int(m.group(2)) > 0 or m.group(1) in ("LINKS", "LATEST")):
                values[m.group(1)] = int(m.group(2))
            elif v:
                if v.group(1) == "VERBOSE" and v.group(2).lower() in ("1", "true", "yes", "oui", "on", "0", "false", "no", "non", "off"):
                    values["VERBOSE"] = v.group(2).lower() in ("1", "true", "yes", "oui", "on")
                elif v.group(1) == "DEBUG_LEVEL" and v.group(2).isdigit():
                    values["DEBUG_LEVEL"] = int(v.group(2))
                else:
                    problems.append(f"{path}:{n} : line ignored « {line} » (VERBOSE: yes/no; DEBUG_LEVEL: number)")
            elif t:
                if t.group(2).strip():
                    values[t.group(1)] = t.group(2).strip()
            else:
                problems.append(f"{path}:{n} : line ignored « {line} » (keys: URL, DB, LOGIN, KEY_FILE, PAGES, PAGES_FILE, LANGS, MODELS, SERVICE: text; REPEAT, WAIT: positive numbers; LINKS, LATEST: numbers; LANGUAGE: en, fr, auto)")
    level = values.get("DEBUG_LEVEL", 0)
    if level >= 1 and "VERBOSE" not in values:               # DEBUG_LEVEL >= 1 means VERBOSE=yes
        values["VERBOSE"] = True
    if level:
        os.environ["NGINX_TOOLS_DEBUG_LEVEL"] = str(level)
    return values, files_read, problems


def split_list(text, default_value):
    """List separated by commas (or spaces); empty: the default value."""
    elements = [e for e in re.split(r"[,\s]+", text or "") if e]
    return elements or list(default_value)


def read_key(path):
    """Content of the API key file (one line), or None. Warns if the file is readable by others."""
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            key = f.read().strip()
        mode = os.stat(os.path.expanduser(path)).st_mode & 0o077
    except OSError:
        return None
    if mode:
        eprint(f"  ATTENTION {path} is readable by other users: chmod 600 advised.")
    return key or None


class Client:
    """Small HTTP client with cookies (Odoo session), measures the time of each request."""

    def __init__(self, base_url):
        self.database = base_url.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.cookies)]
        if re.match(r"https?://(127\.0\.0\.1|localhost|\[::1\])(:|/|$)", self.database):      # local Odoo: never through the system proxy
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def request_(self, path, payload=None):
        """(HTTP code, seconds, body as text); code 0 if the connection fails."""
        url = path if path.startswith("http") else self.database + path
        headers_list = {"User-Agent": "odoo-warmup", "Accept-Encoding": "identity"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers_list["Content-Type"] = "application/json"
        start = time.time()
        try:
            with self.opener.open(urllib.request.Request(url, data=body, headers=headers_list), timeout=REQUEST_TIMEOUT) as r:
                text = r.read().decode("utf-8", "replace")
                return r.status, time.time() - start, text
        except urllib.error.HTTPError as e:
            return e.code, time.time() - start, ""
        except (urllib.error.URLError, OSError, ValueError):
            return 0, time.time() - start, ""


def wait_for_odoo(client, seconds):
    """True as soon as /web/login answers (200 or redirect); False after `seconds`."""
    end = time.time() + seconds
    while True:
        code, _, _ = client.request_("/web/login")
        if code in (200, 303, 302):
            return True
        if time.time() >= end:
            return False
        time.sleep(2)


def assets_of(text):
    """Addresses of the assets (/web/assets/...) cited by an HTML page (no duplicates, in order)."""
    seen = []
    for a in re.findall(r"""(?:src|href)=["'](/web/assets/[^"']+)["']""", text):
        a = a.replace("&amp;", "&")
        if a not in seen:
            seen.append(a)
    return seen


def rpc(client, path, params):
    """JSON-RPC call: (code, seconds, result or None, error message or '')."""
    code, duration, text = client.request_(path, {"jsonrpc": "2.0", "method": "call", "params": params})
    try:
        response = json.loads(text) if text else {}
    except ValueError:
        response = {}
    error_text = ""
    if isinstance(response.get("error"), dict):
        error_text = (response["error"].get("data") or {}).get("message") or response["error"].get("message") or "error"
    return code, duration, response.get("result"), error_text


def in_parallel(jobs, repetitions):
    """Runs each (name, function) `repetitions` times in parallel; returns [(name, result)]."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, repetitions)) as pool:
        futures = [(name, pool.submit(function)) for name, function in jobs for _ in range(repetitions)]
        for name, future in futures:
            try:
                results.append((name, future.result()))
            except Exception as e:  # noqa: BLE001 — a failure does not stop the warm-up
                results.append((name, (0, 0.0, f"{type(e).__name__}: {e}")))
    return results


class Tally:
    def __init__(self):
        self.lines = []         # (name, code, slowest, failures, attempts)

    def add_item(self, name, results):
        codes = [r[0] for r in results]
        bad = sum(1 for c in codes if not (200 <= c < 400))
        self.lines.append((name, max(codes) if codes else 0, max((r[1] for r in results), default=0.0), bad, len(results)))

    def add_ignore(self, name, code, duration, reason="not public"):
        """Page that is not public (403 / 404: unpublished event or survey) or optional (surveys): noted, never counted as a failure."""
        self.lines.append((f"{name} ({reason})", code, duration, 0, 1))

    def display(self):
        for name, code, slowest, bad, attempts in self.lines:
            state = "OK    " if bad == 0 else "FAILED "
            print(f"  [{state}] {name[:70]:<70} HTTP {code}  slowest: {slowest:5.1f} s" + (f"  ({bad} failure(s) out of {attempts})" if bad else ""))
        return sum(1 for line in self.lines if line[3])


def links_of(text, prefixes, already):
    """Linked pages (href="/event/...", "/survey/...") of an HTML page: no duplicates, no assets or files, in order. `prefixes`: allowed first segments."""
    found = []
    for h in re.findall(r"""href=["'](/[^"'#?\s]+)""", text):
        h = h.replace("&amp;", "&").rstrip("/")
        segments = h.strip("/").split("/")
        if len(segments) < 2 or segments[0] not in prefixes or re.search(r"\.(css|js|png|jpe?g|gif|svg|ico|pdf|zip|woff2?)$", h, re.I):
            continue
        if h not in already and h not in found:
            found.append(h)
    return found


def is_optional(path):
    """Survey pages (/survey..., with or without a language prefix) are optional: their failure is never counted."""
    segments = re.sub(r"^/[a-z]{2}(?:_[A-Za-z]{2})?(?=/|$)", "", path.split("?")[0]).strip("/").split("/")
    return segments[0] == "survey"


def language_variants(text, languages, path):
    """Paths of the page's versions in the `languages` (fr, en, es...), read from its <link rel="alternate" hreflang="...">. One version per language; the language
    of the page itself is excluded."""
    path = path.split("?")[0].rstrip("/")
    found, families = [], set()
    alternates = []
    for tag in re.findall(r"<link\b[^>]*>", text):
        if not re.search(r"""rel=["']alternate["']""", tag):
            continue
        h, href = re.search(r"""hreflang=["']([^"']+)["']""", tag), re.search(r"""href=["']([^"']+)["']""", tag)
        if h and href and h.group(1).lower() != "x-default":
            alternates.append((h.group(1).lower().split("-")[0].split("_")[0], path_of(href.group(1).replace("&amp;", "&"))))
    families = {f for f, c in alternates if c and c.split("?")[0].rstrip("/") == path}          # the language of the page itself
    for family, c in alternates:
        if family in languages and family not in families and c:
            families.add(family)
            found.append(c)
    return found


def load_page(client, path, tally, assets, languages=()):
    """A public page (failure of an optional page: noted, not counted), its assets and its versions in the `languages`. Returns the HTML text."""
    code, duration, text = client.request_(path)
    if is_optional(path) and not 200 <= code < 400:
        tally.add_ignore(path, code, duration, "optional")
    else:
        tally.add_item(path, [(code, duration, "")])
    for a in assets_of(text):
        if a not in assets:
            assets.append(a)
    for variant in language_variants(text, languages, path) if languages else []:
        load_page(client, variant, tally, assets)
    return text


def warm_public(client, pages, repetitions, tally, links_count=0, languages=()):
    """Public pages (each in the `languages`), `links` linked pages discovered in them (event pages, surveys...), then their assets. Returns the number of assets loaded."""
    assets = []
    prefixes = {p.strip("/").split("/")[0] for p in pages if p.strip("/")} - {"web"} | {"event", "survey"}
    texts = [load_page(client, page, tally, assets, languages) for page in pages]
    visited = list(pages)
    for text in texts:
        for link in links_of(text, prefixes, visited):
            if len(visited) - len(pages) >= links_count:
                break
            visited.append(link)
            load_page(client, link, tally, assets, languages)
    if not assets:
        return 0
    for name, results in group_results(in_parallel([(a, (lambda a=a: client.request_(a))) for a in assets], 1)):
        tally.add_item(name, results)
    return len(assets)


def read_pages(path):
    """([paths], [problems]) of the extra pages file (one per line, # = comment); file absent: ([], [])."""
    pages, problems = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return pages, problems
    for n, line in enumerate(lines, 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("/"):
            if line not in pages:
                pages.append(line)
        else:
            problems.append(f"{path}:{n} : line ignored « {line} » (a path starting with / is expected)")
    return pages, problems


def create_default_pages(path):
    """First start: creates the pages file (copy of doc/en/odoo-warmup-pages.conf.example, mode 644) if it does not exist; silent failure."""
    if os.path.exists(path) or os.environ.get("NGINX_TOOLS_CONFIG_CREER") == "0":
        return
    try:
        with open(os.path.join(SCRIPT_DIR, "doc", "en", "odoo-warmup-pages.conf.example"), encoding="utf-8") as f:
            model = f.read()
        with open(path, "x", encoding="utf-8") as f:
            f.write(model)
        os.chmod(path, 0o644)
        print(f"Pages file created: {path}")
    except OSError:
        pass


def group_results(pairs):
    """[(name, result)] -> [(name, [results])] keeping the order."""
    order, groups_ = [], {}
    for name, result in pairs:
        if name not in groups_:
            groups_[name] = []
            order.append(name)
        groups_[name].append(result)
    return [(name, groups_[name]) for name in order]


def warm_admin(client, database, login, key, models, repetitions, tally, latest=0, languages=()):
    """Administration session, web client, menus and get_views of the models. Returns False if the login is refused."""
    code, duration, result, error_text = rpc(client, "/web/session/authenticate", {"db": database, "login": login, "password": key})
    if code != 200 or not isinstance(result, dict) or not result.get("uid"):
        tally.lines.append((f"login of {login} (base {database}) refused" + (f" : {error_text}" if error_text else ""), code, duration, 1, 1))
        return False
    tally.add_item(f"login of {login} (base {database})", [(code, duration, "")])
    code, duration, text = client.request_("/odoo")
    if code in (404, 0):
        code, duration, text = client.request_("/web")
    tally.add_item("client web (/odoo)", [(code, duration, "")])
    for name, results in group_results(in_parallel([(a, (lambda a=a: client.request_(a))) for a in assets_of(text)], 1)):
        tally.add_item(name, results)
    jobs = [("menus (load_menus)", lambda: client.request_("/web/webclient/load_menus"))]
    for model in models:
        def call(model=model):
            c, d, res, err = rpc(client, f"/web/dataset/call_kw/{model}/get_views",
                                 {"model": model, "method": "get_views", "args": [VIEWS], "kwargs": {"options": {}}})
            return (c if not err else 500), d, err
        jobs.append((f"views of {model}", call))
    for name, results in group_results(in_parallel(jobs, repetitions)):
        tally.add_item(name, results)
    if latest:
        warm_latest(client, latest, tally, languages)
    return True


def path_of(address):
    """« https://site/event/x-12?a=1 » -> « /event/x-12?a=1 »; None if it is not an address."""
    m = re.match(r"(?:https?://[^/]+)?(/[^\s]*)", address or "")
    return m.group(1) if m else None


def warm_latest(client, number, tally, languages=()):
    """Public pages of the `number` latest events and surveys (read with the administration session, read-only): their build is the slowest."""
    for model, field, name in LATEST_KINDS:
        code, duration, lines, error_text = rpc(client, f"/web/dataset/call_kw/{model}/search_read",
                                          {"model": model, "method": "search_read", "args": [[]],
                                           "kwargs": {"fields": [field], "order": "id desc", "limit": number}})
        if code != 200 or error_text or not isinstance(lines, list):
            tally.lines.append((f"latest {name}: cannot read" + (f" ({error_text[:50]})" if error_text else ""), code, duration, 0, 1))
            continue
        for line in lines:
            path = path_of(str(line.get(field) or ""))
            if not path:
                continue
            c, d, page = client.request_(path)
            if c in (403, 404):
                tally.add_ignore(path, c, d)
                continue
            assets = []
            if is_optional(path) and not 200 <= c < 400:
                tally.add_ignore(path, c, d, "optional")
            else:
                tally.add_item(path, [(c, d, "")])
            for a in assets_of(page):
                tally.add_item(a, [client.request_(a)])
            for variant in language_variants(page, languages, path) if languages else []:
                load_page(client, variant, tally, assets)
            for a in assets:
                tally.add_item(a, [client.request_(a)])


def systemd_content(service, program_path, wait_seconds):
    """systemd .d file: starts the warm-up in the background (systemd-run, without delaying Odoo) after each start."""
    return ("# Generated by odoo-warmup.py --systemd-install — Odoo cache warm-up after every start (remove with --systemd-remove).\n"
            "[Service]\n"
            f"ExecStartPost=-+/usr/bin/systemd-run --quiet --no-block --unit=odoo-warmup-run {sys.executable} {program_path} --wait {wait_seconds}\n")


def dropin_path(service):
    return os.path.join(SYSTEMD_DIR, f"{service}.d", "odoo-warmup.conf")


def systemd_install_unit(service, wait_seconds):
    path = dropin_path(service)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(systemd_content(service, os.path.realpath(__file__), wait_seconds))
    except OSError as e:
        eprint(f"ERROR: cannot write {path} ({e.strerror}) : run again as root.")
        return 2
    print(f"File created: {path}")
    if os.environ.get("NGINX_TOOLS_SYSTEMD_DIR") is None:
        subprocess.run(["systemctl", "daemon-reload"], check=False)
    print(f"The warm-up will run at every start of {service} (essai maintenant : systemctl restart {service}).")
    return 0


def systemd_remove_unit(service):
    path = dropin_path(service)
    if not os.path.isfile(path):
        print(f"Nothing to remove: {path} does not exist.")
        return 0
    try:
        os.remove(path)
        try:
            os.rmdir(os.path.dirname(path))
        except OSError:
            pass
    except OSError as e:
        eprint(f"ERROR: cannot delete {path} ({e.strerror}) : run again as root.")
        return 2
    if os.environ.get("NGINX_TOOLS_SYSTEMD_DIR") is None:
        subprocess.run(["systemctl", "daemon-reload"], check=False)
    print(f"File deleted: {path}")
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
    """Fallback parser (apps/_i18n.py missing): options in alphabetical order, English messages."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", SortedHelp)
        super().__init__(*args, **kwargs)


def main():
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(description="Warms up the Odoo cache (public pages, assets, administration screens) after a restart.")
    parser.add_argument("-c", "--config", default=None, metavar="FILE",
                        help=f"This configuration file ONLY (default: {SYSTEM_CONF}, then {USER_CONF} ; keys URL, DB, LOGIN, KEY_FILE, PAGES, PAGES_FILE, LANGS, MODELS, REPEAT, WAIT, SERVICE, LANGUAGE)")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("--db", default=None, metavar="NAME", help="Odoo database for administration (required with LOGIN if Odoo has several databases)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--latest", type=int, default=None, metavar="N", help=f"Also warms up the public pages of the N latest events and surveys, read with the administration session (default: {DEFAULT_LATEST}; 0: none). Key LATEST")
    parser.add_argument("--links", type=int, default=None, metavar="N", help=f"Also loads N linked pages found in the public pages (event pages, surveys…) (default: {DEFAULT_LINKS}; 0: none). Key LINKS")
    parser.add_argument("--pages-file", default=None, metavar="FILE", help=f"File of additional public pages, one path per line (default: {PAGES_FILE}; created at first run). Key PAGES_FILE")
    parser.add_argument("--repeat", type=int, default=None, metavar="N", help=f"Parallel passes of each administration call (default: {DEFAULT_REPETITIONS}) : touche plusieurs processus d'Odoo")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--service", default=None, metavar="UNIT", help=f"Odoo systemd unit for --systemd-install and --systemd-remove (default: {DEFAULT_SERVICE})")
    parser.add_argument("--site-languages", default=None, metavar="LIST", help=f"Site languages warmed up for every public page, comma-separated (default: {DEFAULT_LANGUAGES}; none: none). Key LANGS")
    parser.add_argument("--systemd-install", action="store_true", help="Run the warm-up after every start of the Odoo unit (systemd .d file, root)")
    parser.add_argument("--systemd-remove", action="store_true", help="Remove the automatic start installed by --systemd-install")
    parser.add_argument("--url", default=None, metavar="URL", help=f"Odoo address (default: {DEFAULT_URL} : Odoo's HTTP port, bypassing nginx)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each external command run")
    parser.add_argument("--version", action="version", version=f"odoo-warmup.py version {__version__}")
    parser.add_argument("--wait", type=int, default=None, metavar="SECONDS", help=f"Waits for Odoo to answer for {DEFAULT_WAIT} seconds at most (default) before warming up")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help (--version prints it itself)
        print(f"odoo-warmup.py v{__version__}")
    args = parser.parse_args()
    global VERBOSE
    VERBOSE = args.verbose
    if args.changelog:
        return show_changelog()
    try:
        config, files_read, problems = read_config(args.config)
    except FileNotFoundError as e:
        eprint(f"ERROR: {e}")
        return 2
    VERBOSE = VERBOSE or bool(config.get("VERBOSE"))               # VERBOSE / DEBUG_LEVEL of the configuration file (common or own)
    url = args.url or config.get("URL", DEFAULT_URL)
    database = args.db or config.get("DB")
    login = config.get("LOGIN")
    key_file = config.get("KEY_FILE")
    pages = split_list(config.get("PAGES"), DEFAULT_PAGES)
    pages_file = args.pages_file or config.get("PAGES_FILE") or PAGES_FILE
    if not args.config and not (args.pages_file or config.get("PAGES_FILE")):
        create_default_pages(pages_file)
    extra_pages, page_problems = read_pages(pages_file)
    problems += page_problems
    pages += [p for p in extra_pages if p not in pages]
    languages_text = args.site_languages if args.site_languages is not None else config.get("LANGS", DEFAULT_LANGUAGES)
    languages = tuple(l.lower() for l in split_list(languages_text, []) if l.lower() not in ("aucune", "none", "-"))
    models = split_list(config.get("MODELS"), DEFAULT_MODELS)
    repetitions = args.repeat if args.repeat is not None else config.get("REPEAT", DEFAULT_REPETITIONS)
    wait_seconds = args.wait if args.wait is not None else config.get("WAIT", DEFAULT_WAIT)
    service = args.service or config.get("SERVICE", DEFAULT_SERVICE)
    links_count = args.links if args.links is not None else config.get("LINKS", DEFAULT_LINKS)
    latest = args.latest if args.latest is not None else config.get("LATEST", DEFAULT_LATEST)
    if repetitions < 1 or wait_seconds < 1:
        parser.error("--repeat and --wait must be positive numbers")
    if links_count < 0 or latest < 0:
        parser.error("--links and --latest must be positive numbers or zero")
    if args.config:
        read_files = f"{load_module('_config').avec_date(files_read[0])} (requested by -c/--config: no other file is read)"
    else:
        read_files = ", then ".join(load_module("_config").avec_date(c) for c in files_read) + (" (the last one wins)" if len(files_read) > 1 else "") if files_read else "no file (default values)"
    created = os.environ.get("NGINX_TOOLS_CONFIG_CREE")
    if created and created in files_read:
        read_files += " (file just created: every option is in a comment, default values)"
    print(f"Configuration read: {read_files}")
    print(f"  Options: --lang {LANGUAGE}{lang_origin()} · Odoo {url} · {len(pages)} page(s) publique(s) + {links_count} lien(s) · {len(extra_pages)} page(s) in {pages_file} · site languages: {', '.join(languages) or 'no variants'}"
          + (f" · administration : {login} (base {database or 'to be specified'}), {len(models)} model(s), {latest} latest event(s)/survey(s), {repetitions} pass(es)" if login and key_file else " · administration: not configured (LOGIN and KEY_FILE)"))
    for p in problems:
        eprint(f"  ATTENTION {p}")
    if args.systemd_install and args.systemd_remove:
        parser.error("--systemd-install and --systemd-remove are mutually exclusive")
    if args.systemd_install:
        return systemd_install_unit(service, wait_seconds)
    if args.systemd_remove:
        return systemd_remove_unit(service)
    client = Client(url)
    print(f"Waiting for Odoo ({url}, {wait_seconds} s at most)…")
    if not wait_for_odoo(client, wait_seconds):
        eprint(f"ERROR: Odoo does not answer at {url} after {wait_seconds} s (service stopped? different HTTP port: --url).")
        return 2
    tally = Tally()
    start = time.time()
    n_assets = warm_public(client, pages, repetitions, tally, links_count, languages)
    administration = None
    if login and key_file:
        key = read_key(key_file)
        if not key:
            eprint(f"ERROR: API key file unreadable or empty: {key_file}")
            return 2
        if not database:
            eprint("ERROR: database to be specified (DB key or --db) for administration.")
            return 2
        administration = warm_admin(client, database, login, key, models, repetitions, tally, latest, languages)
    failures = tally.display()
    print(f"Warm-up finished in {time.time() - start:.0f} s : {len(tally.lines)} appel(s), {n_assets} asset(s) public(s), {failures} failure(s)"
          + ("" if administration is not None else " ; administration not warmed up (set LOGIN and KEY_FILE)."))
    return 1 if failures or administration is False else 0


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
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        text = changelog_section(CHANGELOG_FILE, "odoo-warmup.py")
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


def protected_main():
    try:
        return main()
    except KeyboardInterrupt:
        eprint("\nInterrompu (Ctrl-C).")
        return 130


def launch_with_report(function):
    """--report-err: paste-ready error report at the end of the run (apps/_rapport.py, if next to this file)."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        module = load_module("_rapport")
        if module is None:
            eprint("--report-err unavailable (apps/_rapport.py missing) — normal run.")
            return function()
        return module.lancer(function, os.path.basename(__file__), __version__, SCRIPT_DIR)
    return function()


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(protected_main))
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
