#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026  Services-Conseils Linux
#
# This file is part of the nginx configuration of Rencontres Linux Québec. Free software: you can
# redistribute it and/or modify it under the terms of the GNU Affero General Public License published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# odoo-chat-post.py — Odoo DISCUSSION CHANNELS (Discuss) to keep the team informed about problems, WITHOUT access to the Linux console.
#   * --create: creates the missing channels and threads (Odoo 18 sub-channels), from doc/odoo-chat-post.catalogue.json (editable; --catalog FILE),
#     and writes in each one a FIRST MESSAGE that says why the channel exists, who feeds it and what to do. Existing channels are never modified or repeated.
#     The catalog's « suggested » channels are only created with --suggested. Event threads (e.g. JPOL26-Inscriptions) exist for each --event.
#   * --post CHANNEL/THREAD --message TEXT: posts an alert in a thread (« - »: the text comes from standard input), for scheduled tasks and other programs.
#   * --list: state of each channel and thread of the catalog (present or absent).
#   * --members LOGINS: RESTRICTED access — only these Odoo accounts (e.g. etienne.berube.ing@exemple.org,tux-bot) see the channels and are members; the account of the robot that posts
#     (--post) must be one of them. An account not yet created is reported; create it, then run --create again to add the missing members (nobody is ever removed).
#   Access: Odoo external API (XML-RPC) with an API KEY (Odoo: Preferences → Account Security → New API Key); the key is read from the configuration file
#   (mode 600 advised) or the ODOO_API_KEY variable, never on the command line or on screen. No root access, no write outside Odoo.
# Configuration (common rule): /etc/default/odoo-chat-post.conf THEN ~/.odoo-chat-post.cfg (the last one wins; keys API_KEY, DB, EVENTS, GROUP, LANGUAGE, LOGIN,
# MEMBERS, NO_MEMBERS, SUGGESTED, URL); -c/--config: that file ALONE; the command line takes priority. The files read are always displayed, with the important options.
#
# VERSION HISTORY (summary — see doc/odoo-chat-post.changelog.txt for full detail):
#   1.6.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.5.20261015.205140 — Program renamed odoo-canaux.py -> odoo-chat-post.py (English name; configuration odoo-chat-post.conf / .odoo-chat-post.cfg, ODOO_CHAT_POST_LANG).
#   1.4.20261015.203803 — Source code, comments and changelog in English (display stays French/English via lang/odoo-chat-post.fr.po); the message posted in Odoo follows the display language.
#   1.3.20261015.105354 — --create-bot also creates the robot's API key (one year if Odoo allows it) and writes it in the configuration files (--bot-config); --renew-key.
#   1.2.20261015.103039 — --create-bot: Tux-Bot robot account with minimal rights (internal user, no password); --bot-login.
#   1.1.20261015.095427 — Restricted access: --members (key MEMBERS) reserves the channels for specific accounts (group « Team alerts (odoo-chat-post) »); SUGGESTED in configuration; existing channels synchronized.
#   1.0.20261015.085700 — First version: creation of the Odoo-Errors, Odoo-Stats, Event-Registrations channels and threads (+ suggestions) with a first message; --post; --list.
#
# Usage:
#   odoo-chat-post.py --list
#   odoo-chat-post.py --create --dry-run                     shows what would be created, writes nothing
#   odoo-chat-post.py --create [--suggested] [--event JPOL26] [--members etienne.berube.ing@exemple.org,tux-bot]
#   odoo-chat-post.py --post "Odoo-Erreurs/HTTP 5xx" --message "Maintenance page shown since 08:12"
#   web-monitor.py --summary | odoo-chat-post.py --post "Odoo-Stats/Sommaire" --message -
#   ODOO_API_KEY=… odoo-chat-post.py --login ADMIN --create-bot [--bot-login tux-bot] [--bot-config FILE] [--renew-key] [--dry-run]   robot account (minimal rights) + its API key written with mode 600
#   --api-url, --bot-config, --bot-login, --renew-key, --catalog, --db, --group, --lang, --login, --members, --no-members, --report-err, --version, --changelog

import argparse
import datetime
import http.cookiejar
import html
import importlib.util
import json
import os
import re
import secrets
import signal
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import xmlrpc.client

__version__ = "1.6.20261016.173838"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "doc", f"{SCRIPT_NAME}.changelog.txt")
DEFAULT_CATALOG = os.path.join(SCRIPT_DIR, "doc", "odoo-chat-post.catalogue.json")
DEFAULT_GROUP = "base.group_user"
DEFAULT_BOT_CONFIG = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT") or "/etc/default", "odoo-chat-post.conf")     # receives the robot's LOGIN and API_KEY (--create-bot); the administrator gives HIS key through ODOO_API_KEY, never in a file
KEY_DURATIONS = (365, 180, 90, 30, 7)                        # key durations tried (days); the longest one accepted by Odoo is kept
RESTRICTED_GROUP = "Team alerts (odoo-chat-post)"      # group created by --members: only its accounts see the channels
DEFAULT_EVENT = "JPOL26"


def _start():
    """Common context (apps/_i18n.py: language, configuration, translated print / input, parser); module missing (script copied alone): French, no configuration."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "ODOO_CHAT_POST_LANG")
    except Exception:
        return None


I18N = _start()
LANGUAGE = I18N.langue if I18N else "fr"
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 — every displayed text goes through the translator (no effect when the display language is the source language)


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


# Configuration file options (/etc/default/odoo-chat-post.conf, then the personal file .odoo-chat-post.cfg): KEY -> (command-line option, type).
# LANGUAGE: en, fr or auto (follow LC_ALL / LANG). API_KEY is NOT a command-line option: read separately (read_api_key).
SCHEMA_CONFIG = {"DB": ("db", str), "MEMBERS": ("members", lambda v: [t.strip() for t in v.split(",") if t.strip()]), "SUGGESTED": ("suggested", bool), "EVENTS": ("events", lambda v: [t.strip() for t in v.split(",") if t.strip()]), "GROUP": ("group", str), "LOGIN": ("login", str),
                 "NO_MEMBERS": ("no_members", bool), "URL": ("api_url", str)}


class ChannelsError(Exception):
    """Error to display as is (message already written for the user), without a traceback."""


def read_api_key(paths_read):
    """API key: ODOO_API_KEY variable, otherwise key API_KEY of the last configuration file read that defines it; (key, file too open or None)."""
    key_value = os.environ.get("ODOO_API_KEY", "").strip()
    is_open = None
    for path in paths_read:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"\s*API_KEY\s*=\s*(.*?)\s*$", line)
                    if m and m.group(1).strip("\"'"):
                        key_value = key_value or m.group(1).strip("\"'")
                        if os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                            is_open = path
        except OSError:
            continue
    return key_value, is_open


def load_catalog(path, event_list, is_suggested):
    """[{name, reason, fed_by, threads: [{name, reason}]}]: the JSON catalog, the « per event » threads expanded for each event; without --suggested, the suggested channels are left out."""
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError) as e:
        raise ChannelsError(f"catalogue illisible : {path} ({e})")
    res = []
    for channel in payload.get("canaux", []):
        if channel.get("suggere") and not is_suggested:
            continue
        threads = []
        for thread in channel.get("fils", []):
            if channel.get("par_evenement"):
                threads += [{"nom": thread["nom"].replace("{EVENT}", ev), "raison": thread["raison"].replace("{EVENT}", ev)} for ev in event_list]
            else:
                threads.append(thread)
        res.append({"nom": channel["nom"], "raison": channel["raison"], "alimente": channel.get("alimente", ""), "fils": threads, "suggere": bool(channel.get("suggere"))})
    return res


def first_message(name, reason, fed_by, parent=None):
    """HTML of the first message of a channel or thread: reason, source, creation date (local time)."""
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    e = html.escape
    t = I18N.tr if I18N else (lambda text: text)          # the message posted in Odoo follows the display language
    body = f"<p><b>{e(t('Reason for this thread' if parent else 'Reason for this channel'))} :</b> {e(reason)}</p>"
    if parent:
        body += f"<p><b>{e(t('Channel:'))}</b> {e(parent)}</p>"
    if fed_by:
        body += f"<p><b>{e(t('Fed by:'))}</b> {e(fed_by)}</p>"
    body += f"<p><i>{e(t('Created on'))} {when}{e(t(' (local time) by odoo-chat-post.py'))} {__version__}.</i></p>"
    return body


class Odoo:
    """Odoo XML-RPC access: authentication by API key, execute_kw calls."""

    def __init__(self, url, db, login, key_value):
        self.url, self.db, self.login, self.key_value = url.rstrip("/"), db, login, key_value
        self.uid = None
        self._object = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/object", allow_none=True)

    def connect(self):
        try:
            common = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/common", allow_none=True)
            self.uid = common.authenticate(self.db, self.login, self.key_value, {})
        except (OSError, xmlrpc.client.Error) as e:
            raise ChannelsError(f"cannot connect to Odoo ({self.url}) : {e}")
        if not self.uid:
            raise ChannelsError(f"authentication refused (database {self.db}, account {self.login}): check the API key and the database name")
        return self.uid

    def call(self, model, method, args, kwargs=None):
        try:
            return self._object.execute_kw(self.db, self.uid, self.key_value, model, method, args, kwargs or {})
        except xmlrpc.client.Fault as e:
            raise ChannelsError(f"Odoo refused {model}.{method} : {str(e.faultString).strip().splitlines()[-1][:300]}")
        except (OSError, xmlrpc.client.Error) as e:
            raise ChannelsError(f"call to Odoo failed ({model}.{method}) : {e}")


class Channels:
    """Channels and threads (discuss.channel, Odoo 18 sub-channels: field parent_channel_id); without sub-channels, a thread becomes a « Channel — Thread » channel."""
    MODELE = "discuss.channel"

    def __init__(self, odoo, grp=DEFAULT_GROUP, member_list=True, logins=None, dry=False):
        self.odoo, self.grp, self.member_list = odoo, grp, member_list
        self.logins, self.dry = [l for l in (logins or []) if l], dry       # --members: access RESTRICTED to these accounts only
        self.accounts, self.not_found = [], []                                      # [(user id, partner id, login)] found; logins without an account
        self._restricted_group = None
        field_list = odoo.call(self.MODELE, "fields_get", [["parent_channel_id"]], {"attributes": ["type"]})
        self.subchannels = "parent_channel_id" in (field_list or {})
        self._group_id = None

    def find(self, name, parent_id=None):
        domain = [["name", "=", name]] + ([["parent_channel_id", "=", parent_id]] if self.subchannels and parent_id else ([["parent_channel_id", "=", False]] if self.subchannels else []))
        ids = self.odoo.call(self.MODELE, "search", [domain], {"limit": 1})
        return ids[0] if ids else None

    def group_id(self, xmlid=None):
        if xmlid:
            module, _, name = xmlid.partition(".")
            lines = self.odoo.call("ir.model.data", "search_read", [[["module", "=", module], ["name", "=", name]]], {"fields": ["res_id"], "limit": 1})
            if not lines:
                raise ChannelsError(f"group not found: {xmlid}")
            return lines[0]["res_id"]
        if self._group_id is None:
            module, _, name = self.grp.partition(".")
            lines = self.odoo.call("ir.model.data", "search_read", [[["module", "=", module], ["name", "=", name]]], {"fields": ["res_id"], "limit": 1})
            if not lines:
                raise ChannelsError(f"group not found: {self.grp} (--group option)")
            self._group_id = lines[0]["res_id"]
        return self._group_id

    def resolve_accounts(self):
        """Odoo accounts of the --members (case-insensitive); those that do not exist yet (e.g. Tux-Bot not created yet) are reported, never fatal."""
        if self.accounts or self.not_found or not self.logins:
            return
        for login in self.logins:
            lines = self.odoo.call("res.users", "search_read", [[["login", "=ilike", login]]], {"fields": ["partner_id", "login"], "limit": 1})
            if lines:
                self.accounts.append((lines[0]["id"], lines[0]["partner_id"][0], lines[0].get("login") or login))
            else:
                self.not_found.append(login)

    def restricted_group_id(self):
        """« Team alerts » group (created if needed) that the --members belong to: it is the only one to see the channels. None in dry mode if the group does not exist yet."""
        if self._restricted_group is None:
            ids = self.odoo.call("res.groups", "search", [[["name", "=", RESTRICTED_GROUP]]], {"limit": 1})
            if ids:
                self._restricted_group = ids[0]
            elif not self.dry:
                self._restricted_group = self.odoo.call("res.groups", "create", [{"name": RESTRICTED_GROUP}])
        if self._restricted_group and self.accounts:
            self.odoo.call("res.users", "write", [[c[0] for c in self.accounts], {"groups_id": [[4, self._restricted_group]]}])
        return self._restricted_group

    def sync_members(self, channel_id):
        """--members mode: the requested accounts (and only them) are members of the channel; returns the number added. Never removes anybody."""
        existing = {m["partner_id"][0] for m in self.odoo.call("discuss.channel.member", "search_read", [[["channel_id", "=", channel_id]]], {"fields": ["partner_id"]})}
        n = 0
        for _, pid, _login in self.accounts:
            if pid not in existing:
                self.odoo.call("discuss.channel.member", "create", [{"channel_id": channel_id, "partner_id": pid}])
                n += 1
        return n

    def create_one(self, name, reason, parent_id=None):
        values = {"name": name, "description": reason[:250], "channel_type": "channel"}
        if parent_id:
            values["parent_channel_id"] = parent_id
        elif self.logins:
            values["group_public_id"] = self.restricted_group_id()
        else:
            values["group_public_id"] = self.group_id()
        return self.odoo.call(self.MODELE, "create", [values])

    def add_members(self, channel_id):
        """The accounts of the group (or, with --members, only these accounts) become members of the channel; returns the number added."""
        if self.logins:
            return self.sync_members(channel_id)
        users = self.odoo.call("res.users", "search_read", [[["groups_id", "in", [self.group_id()]], ["active", "=", True], ["share", "=", False]]], {"fields": ["partner_id"]})
        existing = {m["partner_id"][0] for m in self.odoo.call("discuss.channel.member", "search_read", [[["channel_id", "=", channel_id]]], {"fields": ["partner_id"]})}
        n = 0
        for u in users:
            pid = u["partner_id"][0]
            if pid not in existing:
                self.odoo.call("discuss.channel.member", "create", [{"channel_id": channel_id, "partner_id": pid}])
                n += 1
        return n

    def channel_group(self, channel_id):
        """Id of the group that sees the channel (False: public), to warn if an existing channel is more open than requested."""
        lines = self.odoo.call(self.MODELE, "read", [[channel_id]], {"fields": ["group_public_id"]})
        value = (lines[0].get("group_public_id") if lines else False) or False
        return value[0] if isinstance(value, (list, tuple)) else value

    def publish(self, channel_id, body):
        return self.odoo.call(self.MODELE, "message_post", [[channel_id]], {"body": body, "message_type": "comment", "subtype_xmlid": "mail.mt_comment"})

    def flat_name(self, channel, thread):
        return f"{channel} — {thread}"


def resolve_thread(channels, target):
    """« Channel/Thread » or « Channel » -> id of the channel or thread; ChannelsError if it does not exist (run --create first)."""
    channel_name, _, thread_name = target.partition("/")
    channel_id = channels.find(channel_name.strip())
    if thread_name.strip() and channels.subchannels:
        thread_id = channels.find(thread_name.strip(), channel_id) if channel_id else None
        if not thread_id:
            raise ChannelsError(f"thread not found: {target} (create it with --create)")
        return thread_id
    if thread_name.strip():
        channel_id = channels.find(channels.flat_name(channel_name.strip(), thread_name.strip()))
    if not channel_id:
        raise ChannelsError(f"channel not found: {target} (create it with --create)")
    return channel_id


def list_state(channels, catalogue):
    """« state » lines of each channel and thread of the catalog."""
    res = []
    for c in catalogue:
        cid = channels.find(c["nom"])
        res.append(f"  {'present' if cid else 'absent '}  {c['nom']}" + ("  (suggested)" if c["suggere"] else ""))
        for f in c["fils"]:
            fid = (channels.find(f["nom"], cid) if cid else None) if channels.subchannels else channels.find(channels.flat_name(c["nom"], f["nom"]))
            res.append(f"  {'present' if fid else 'absent '}    └ {f['nom']}")
    return res


def create_all(channels, catalogue, dry):
    """Creates what is missing and writes the first message; returns the report lines. dry: nothing is written in Odoo.
    With --members: channels and threads already present also receive the missing members (never removed) and a warning if their group differs."""
    res, new_ones = [], 0
    restricted = bool(channels.logins)
    if restricted:
        for login in channels.not_found:
            res.append(f"  WARNING: the account {login} does not exist in Odoo yet: it is not a member; create it, then rerun --create")
        res.append("  Access restricted to: " + (", ".join(c[2] for c in channels.accounts) or "(no account found)") + f" (group \"{RESTRICTED_GROUP}\")")

    def check_existing(cid, name, margin, thread):
        if not restricted or dry:
            return
        added = channels.sync_members(cid)
        if added:
            res.append(f"{margin}{added} member(s) added to {name}")
        wanted = channels.restricted_group_id()
        if not thread and wanted and channels.channel_group(cid) != wanted:
            res.append(f"{margin}WARNING: {name} is visible to another group than \"{RESTRICTED_GROUP}\" (unchanged: change it in Odoo, Discuss → channel settings)")

    for c in catalogue:
        cid = channels.find(c["nom"])
        if cid:
            res.append(f"  Channel already present: {c['nom']} (unchanged)")
            check_existing(cid, c["nom"], "  ", False)
        elif dry:
            res.append(f"  To create: channel {c['nom']}")
        else:
            cid = channels.create_one(c["nom"], c["raison"])
            channels.publish(cid, first_message(c["nom"], c["raison"], c["alimente"]))
            added = channels.add_members(cid) if (channels.member_list or restricted) else 0
            new_ones += 1
            res.append(f"  Channel created: {c['nom']} (id {cid}, first message written, {added} member(s) added)")
        for f in c["fils"]:
            name = f["nom"] if channels.subchannels else channels.flat_name(c["nom"], f["nom"])
            fid = channels.find(f["nom"], cid) if (cid and channels.subchannels) else (None if channels.subchannels else channels.find(name))
            if fid:
                res.append(f"    Thread already present: {f['nom']} (unchanged)")
                check_existing(fid, f["nom"], "    ", channels.subchannels)
            elif dry or (channels.subchannels and not cid):
                res.append(f"    To create: thread {f['nom']}")
            else:
                fid = channels.create_one(name, f["raison"], cid if channels.subchannels else None)
                channels.publish(fid, first_message(f["nom"], f["raison"], c["alimente"], c["nom"]))
                if restricted:
                    channels.sync_members(fid)
                new_ones += 1
                res.append(f"    Thread created: {f['nom']} (id {fid}, first message written)")
    res.append(("  Dry run: nothing was written to Odoo." if dry else f"  {new_ones} channel(s) / thread(s) created."))
    if not channels.subchannels:
        res.append("  This Odoo version has no sub-channels: each thread is a channel named \"Channel — Thread\".")
    return res


class WebSession:
    """Odoo web session (JSON-RPC + session cookie), like a browser: the only way, in Odoo, to create an API key (the external API does not allow it)."""

    def __init__(self, url, db):
        self.url, self.db = url.rstrip("/"), db
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _post(self, path, params):
        request_data = urllib.request.Request(self.url + path, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}).encode(), headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request_data, timeout=60) as r:
                answer = json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ChannelsError(f"web session failed ({self.url}{path}) : {e}")
        if answer.get("error"):
            payload = answer["error"].get("data") or {}
            raise ChannelsError(str(payload.get("message") or answer["error"].get("message") or "Odoo error")[:300])
        return answer.get("result")

    def connect(self, login, password):
        result = self._post("/web/session/authenticate", {"db": self.db, "login": login, "password": password})
        if not result or not result.get("uid"):
            raise ChannelsError(f"web login refused for {login} (temporary password not accepted, or two-factor authentication enabled)")

    def call(self, model, method, args, kwargs=None):
        return self._post(f"/web/dataset/call_kw/{model}/{method}", {"model": model, "method": method, "args": args, "kwargs": kwargs or {}})


def generer_cle_api(url, db, login, password, name="odoo-chat-post", durees=KEY_DURATIONS):
    """As the person would do in Odoo (Preferences → Account Security → New API Key): identity check then key wizard;
    tries the durations from the longest to the shortest (Odoo limits the key duration of non-administrator accounts); returns (key, days)."""
    session = WebSession(url, db)
    session.connect(login, password)
    check = session.call("res.users.identitycheck", "create", [{"password": password}])
    session.call("res.users.identitycheck", "run_check", [[check]])
    last = "no duration tried"
    for jours in durees:
        try:
            wizard = session.call("res.users.apikeys.description", "create", [{"name": name, "duration": str(jours)}])
            action = session.call("res.users.apikeys.description", "make_key", [[wizard]])
            key_value = ((action or {}).get("context") or {}).get("default_key")
            if key_value:
                return key_value, jours
            last = "Odoo did not return the key (different version or wizard)"
        except ChannelsError as e:
            last = str(e)
    raise ChannelsError(f"API key creation refused by Odoo: {last}")


def check_writable(path):
    """Returns None if `path` can be created or rewritten, otherwise the reason (to check BEFORE creating a key, so that it is never lost)."""
    if os.path.exists(path):
        return None if os.access(path, os.W_OK) else f"{path} cannot be modified by this account (run as root?)"
    folder = os.path.dirname(os.path.abspath(path))
    return None if os.access(folder, os.W_OK) else f"{folder} cannot be modified by this account (run as root?)"


def write_key_config(path, login, key_value, expire, send_members=True):
    """Writes the robot's LOGIN and API_KEY in `path` (created with mode 600 if needed) keeping the other lines; the old version is saved as .YYYYMMDD-HHMMSS.bak (600).
    If MEMBERS exists without the robot, it is added. Returns the list of changes (never the key)."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        backup = f"{path}.{datetime.datetime.now():%Y%m%d-%H%M%S}.bak"
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    changes = []
    without = [l for l in lines if not re.match(r"\s*#?\s*(LOGIN|API_KEY)\s*=", l) and not l.startswith("# API key of ")]
    for i, l in enumerate(without):
        m = re.match(r"(\s*MEMBERS\s*=\s*)(.*?)\s*$", l)
        if m and send_members and login.lower() not in [t.strip().lower() for t in m.group(2).split(",")]:
            without[i] = m.group(1) + (m.group(2) + "," if m.group(2) else "") + login
            changes.append(f"{login} added to MEMBERS")
    without += ["", f"# API key of {login} created on {datetime.date.today()}, expires on {expire} (renouveler avant : odoo-chat-post.py --create-bot --renew-key)", f"LOGIN={login}", f"API_KEY={key_value}"]
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".odoo-chat-post-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(without).rstrip("\n") + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    changes.append(f"LOGIN and API_KEY written to {path} (droits 600)")
    return changes


def make_bot(channels, login, dry, args=None):
    """Account of the robot that posts the alerts (--create-bot): INTERNAL user with NO group other than « internal user » (no administration right, no usable password:
    only its API key is used); on the first run (or --renew-key) also creates its API key and writes it in the configuration files (--bot-config); returns the report lines."""
    odoo, res = channels.odoo, []
    renew = bool(args and args.renew_key)
    files_read = (args.bot_config if args and args.bot_config else None) or [DEFAULT_BOT_CONFIG]
    for f in files_read:                  # BEFORE any creation: a key that cannot be written would be lost
        reason = check_writable(f)
        if reason and not dry:
            raise ChannelsError(f"{reason}: nothing is created; rerun as root or choose --bot-config FILE")
        if reason:
            res.append(f"  WARNING: {reason} (the real run would stop here)")
    existing = odoo.call("res.users", "search_read", [[["login", "=ilike", login]]], {"fields": ["groups_id", "login"], "limit": 1, "context": {"active_test": False}})
    if existing:
        uid = existing[0]["id"]
        res.append(f"  Account {login} already present (id {uid}, unchanged)")
        dangerous = []
        for xmlid in ("base.group_system", "base.group_erp_manager"):
            module, _, name = xmlid.partition(".")
            line = odoo.call("ir.model.data", "search_read", [[["module", "=", module], ["name", "=", name]]], {"fields": ["res_id"], "limit": 1})
            if line and line[0]["res_id"] in (existing[0].get("groups_id") or []):
                dangerous.append(xmlid)
        if dangerous:
            res.append(f"  WARNING: {login} has administration rights ({', '.join(dangerous)}): not needed to post, remove them in Odoo (Settings → Users)")
        if not renew:
            return res + ["  No new key created (--renew-key to create a new one; the old one stays valid until it expires or is revoked in Odoo)"]
    elif dry:
        res.append(f"  To create: account {login} (internal user, no usable password)")
        uid = None
    else:
        uid = odoo.call("res.users", "create", [{"name": "Tux-Bot", "login": login, "groups_id": [[6, 0, [channels.group_id("base.group_user")]]], "notification_type": "inbox"}],
                           {"context": {"no_reset_password": True}})
        res.append(f"  Account {login} created (id {uid}): internal user, no other right, no email sent")
    if dry:
        return res + [f"  To create: API key of {login} (duration tried: {KEY_DURATIONS[0]} days, otherwise the longest Odoo allows); to be written to: {', '.join(files_read)}"]
    password = secrets.token_urlsafe(32)
    key_value, jours = None, 0
    try:
        odoo.call("res.users", "write", [[uid], {"password": password}])               # random temporary password, known to this program only
        key_value, jours = generer_cle_api(odoo.url, odoo.db, login, password)
    except ChannelsError as e:
        res.append(f"  WARNING: API key not created automatically: {e}")
    finally:
        odoo.call("res.users", "write", [[uid], {"password": secrets.token_urlsafe(48)}])  # new random password thrown away: web login impossible
    if not key_value:
        return res + make_bot_next(login)
    expire = datetime.date.today() + datetime.timedelta(days=jours)
    res.append(f"  API key created for {login} : valable {jours} day(s), until {expire}" + ("" if jours == KEY_DURATIONS[0] else " (longest duration Odoo accepts for this account)"))
    for f in files_read:
        res += [f"  {c}" for c in write_key_config(f, login, key_value, expire)]
    res.append(f"  The account password was replaced by a discarded random password; the key is not displayed. Renew before {expire} : odoo-chat-post.py --create-bot --renew-key")
    return res


def make_bot_next(login):
    return ["  Manual creation: Settings → Users → Actions → Change password (temporary), log in ONCE as this account,",
            "    Preferences → Account Security → New API key (name \"odoo-chat-post\"), copy it into " + DEFAULT_BOT_CONFIG + " (API_KEY=…, LOGIN=" + login + ", chmod 600),",
            f"    then set a random password again; add {login} to MEMBERS and rerun --create so that it becomes a member of the channels."]


def show_changelog():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)          # « | head »: silent stop, like cat
    try:
        text = open(CHANGELOG_FILE, encoding="utf-8").read()
    except OSError:
        print(f"Changelog not found: {CHANGELOG_FILE}", file=sys.stderr)
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
    """Options of the help in ALPHABETICAL ORDER (long name, without the dashes)."""
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


def run_main(args, parser):
    if not (args.create or args.create_bot or args.list or args.post):
        parser.error("choose an action: --create, --create-bot, --list or --post CHANNEL/THREAD")
    if args.post and args.message is None:
        parser.error("--post needs --message TEXT (\"-\": read standard input)")
    if args.create_bot and args.bot_login.lower() == (args.login or "").lower():
        eprint(f"ERROR: --login is the bot account ({args.bot_login}): use the ADMINISTRATOR account (--login ADMIN, its key in ODOO_API_KEY).")
        return 1
    read_files = I18N.fichiers if I18N else []
    key_value, is_open = read_api_key(read_files)
    if is_open:
        eprint(f"WARNING: {is_open} contains the API key and is readable by other accounts: chmod 600 {is_open}")
    if not (args.api_url and args.db and args.login and key_value):
        missing = [n for n, v in (("URL", args.api_url), ("DB", args.db), ("LOGIN", args.login), ("API_KEY (or the ODOO_API_KEY variable)", key_value)) if not v]
        eprint("ERROR: missing settings: " + ", ".join(missing) + " — write them in /etc/default/odoo-chat-post.conf (see doc/odoo-chat-post.conf.example).")
        return 2
    event_list = args.events or [DEFAULT_EVENT]
    try:
        catalogue = load_catalog(args.catalog, event_list, args.suggested)
        odoo = Odoo(args.api_url, args.db, args.login, key_value)
        odoo.connect()
        member_list = args.members if isinstance(args.members, list) else [t.strip() for t in (args.members or "").split(",")]       # command line: text; configuration: list
        channels = Channels(odoo, args.group or DEFAULT_GROUP, not args.no_members, member_list, args.dry_run)
        channels.resolve_accounts()
        if args.create_bot:
            for line in make_bot(channels, args.bot_login, args.dry_run, args):
                print(line)
            if not args.create:
                return 0
        if args.list:
            print("Channels and threads of the catalog:")
            for line in list_state(channels, catalogue):
                print(line)
            return 0
        if args.post:
            text = sys.stdin.read() if args.message == "-" else args.message
            if not text.strip():
                eprint("ERROR: empty message, nothing is published.")
                return 2
            target = resolve_thread(channels, args.post)
            body = "<br/>".join(html.escape(l) for l in text.strip().splitlines())
            channels.publish(target, body)
            print(f"Message published in {args.post} (id {target}).")
            return 0
        for line in create_all(channels, catalogue, args.dry_run):
            print(line)
        return 0
    except ChannelsError as e:
        eprint(f"ERROR: {e}")
        return 1


def main():
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="Creates in Odoo (Discuss) the team's alert channels and threads, with a first message giving the reason for each, and publishes alerts in them.")
    parser.add_argument("--api-url", default=None, metavar="URL", help="Odoo address (e.g. https://erp.example.org); URL key of the configuration file")
    parser.add_argument("--bot-config", action="append", default=None, metavar="FILE",
                        help=f"With --create-bot: file that receives the bot's LOGIN and API_KEY (mode 600, previous version backed up); repeatable; default: {DEFAULT_BOT_CONFIG}")
    parser.add_argument("--bot-login", default="tux-bot", metavar="LOGIN", help="With --create-bot: login of the bot account (default: tux-bot)")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, metavar="FILE", help="Catalog of channels and threads (JSON) (default: doc/odoo-chat-post.catalogue.json)")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/odoo-chat-post.conf, then the personal file .odoo-chat-post.cfg; UPPERCASE options: API_KEY, DB, EVENTS, GROUP, LANGUAGE, LOGIN, MEMBERS, NO_MEMBERS, SUGGESTED, URL)")
    parser.add_argument("--create", action="store_true", help="Creates the missing channels and threads, with their first message (never modifies an existing channel)")
    parser.add_argument("--create-bot", action="store_true",
                        help="Creates the bot account (--bot-login): internal user with NO other right; on the first run it also creates its API key (one year if Odoo allows it) and writes it to --bot-config; an existing account is not modified")
    parser.add_argument("--db", default=None, metavar="NAME", help="Odoo database")
    parser.add_argument("--dry-run", action="store_true", help="With --create: shows what would be created, without writing anything")
    parser.add_argument("--event", action="append", dest="events", default=None, metavar="NAME",
                        help=f"Event whose threads are created (e.g. JPOL26: JPOL26-Inscriptions, JPOL26-Sondages); repeatable; EVENTS key; default: {DEFAULT_EVENT}")
    parser.add_argument("--group", default=None, metavar="XMLID", help=f"Group that sees the channels and becomes a member (default: {DEFAULT_GROUP}, the internal users)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--list", action="store_true", help="Lists the catalog channels and threads (present or absent), then exits")
    parser.add_argument("--login", default=None, metavar="USER", help="Odoo account that owns the API key")
    parser.add_argument("--members", default=None, metavar="LOGINS",
                        help="RESTRICTED access: Odoo accounts (logins separated by commas) that see the channels and are their members, and nobody else (e.g. etienne.berube.ing@exemple.org,tux-bot); key MEMBERS")
    parser.add_argument("--message", default=None, metavar="TEXT", help="With --post: the text to publish (\"-\": read standard input)")
    parser.add_argument("--no-members", action="store_true", help="Do not add the group accounts as members of the new channels")
    parser.add_argument("--post", default=None, metavar="CHANNEL/THREAD", help="Publishes --message in this channel or thread (e.g. \"Odoo-Erreurs/HTTP 5xx\")")
    parser.add_argument("--renew-key", action="store_true", help="With --create-bot: creates a NEW API key for an existing bot (the old one stays valid until it expires)")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--suggested", action="store_true", help="Also includes the suggested catalog channels (security, emails, backups, updates, event day)")
    parser.add_argument("--version", action="version", version=f"odoo-chat-post.py version {__version__}")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version prints it by itself)
        print(f"odoo-chat-post.py v{__version__}")
    defauts, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defauts, problems)
    if args.changelog:
        return show_changelog()
    return run_main(args, parser)


def protected_main():
    """Protected main(): Ctrl-C ends cleanly, without a traceback (code 130)."""
    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrompu (Ctrl-C).", file=sys.stderr)
        return 130


def launch_with_report(func):
    """--report-err: error report to copy and paste at the end of the run (apps/_rapport.py, if next to it)."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        try:
            spec = importlib.util.spec_from_file_location("_rapport", os.path.join(SCRIPT_DIR, "apps", "_rapport.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"--report-err unavailable ({e}) — normal run.", file=sys.stderr)
            return func()
        return module.lancer(func, os.path.basename(__file__), __version__, SCRIPT_DIR)
    return func()


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(protected_main))
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
