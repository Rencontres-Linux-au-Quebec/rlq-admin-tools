#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026  Services-Linux Conseils Inc <Martial@Bigras.ca> <Martial.Bigras@Services-Conseils-Linux.com>
# License: GNU Affero General Public License, version 3 or later — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _odoo_users.py — register of the Odoo accounts BANNED or WATCHED by web-monitor.py (--ban-odoo-user, --watch-odoo-user) (shared module, apps/).
# One tab-separated line per event, never rewritten (history kept): the LAST event of an account decides its state.
# Read by web-monitor.py (summary, --list-users), nginx-log-audit.sh (an address used by a BANNED account is no longer "a legitimate user")
# and app-log-live.py (mark of a watched or banned account).
#
# VERSION HISTORY (summary — see doc/_odoo_users.changelog.txt for the full detail):
#   1.1.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.0.20261016.114848 — First version: register of banned and watched Odoo accounts.
"""Register of banned / watched Odoo accounts.

File: /var/lib/nginx-tools/odoo-users.tsv (NGINX_TOOLS_ODOO_USERS to change it; "off" disables it), rights 600, columns:
  date (ISO, local) <TAB> event <TAB> database <TAB> uid <TAB> login <TAB> addresses (comma-separated) <TAB> reason
events: banned, unbanned (ban state), watched, unwatched (watch state). The format is read by nginx-log-audit.sh with awk: keep it simple."""
import datetime
import os

__version__ = "1.1.20261016.173838"

DEFAULT_PATH = "/var/lib/nginx-tools/odoo-users.tsv"
BAN_EVENTS = ("banned", "unbanned")
WATCH_EVENTS = ("watched", "unwatched")


def path():
    p = os.environ.get("NGINX_TOOLS_ODOO_USERS", DEFAULT_PATH)
    return None if p.lower() in ("off", "") else p


def _clean(value):
    return " ".join(str(value or "").replace("\t", " ").split())


def events():
    """[{"date", "event", "db", "uid", "login", "ips": [..], "reason"}] in file order; [] if the file is missing or unreadable."""
    p = path()
    if not p:
        return []
    res = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                c = line.rstrip("\n").split("\t")
                if len(c) >= 5 and c[1] in BAN_EVENTS + WATCH_EVENTS:
                    res.append({"date": c[0], "event": c[1], "db": c[2], "uid": c[3], "login": c[4],
                                "ips": [x for x in (c[5] if len(c) > 5 else "").split(",") if x], "reason": c[6] if len(c) > 6 else ""})
    except OSError:
        return []
    return res


def state():
    """{"banned": {login: last "banned" event}, "watched": {login: last "watched" event}} (accounts whose last event of the kind is banned / watched)."""
    ban, watch = {}, {}
    for e in events():
        target = ban if e["event"] in BAN_EVENTS else watch
        if e["event"] in ("banned", "watched"):
            target[e["login"]] = e
        else:
            target.pop(e["login"], None)
    return {"banned": ban, "watched": watch}


def banned_logins():
    return set(state()["banned"])


def watched_logins():
    return set(state()["watched"])


def record(event, db, uid, login, ips=(), reason=""):
    """Appends an event; returns the path written, or None if impossible (no right, register disabled). The directory is created (700), the file is 600."""
    if event not in BAN_EVENTS + WATCH_EVENTS:
        raise ValueError(event)
    p = path()
    if not p:
        return None
    try:
        os.makedirs(os.path.dirname(p) or ".", mode=0o700, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write("\t".join([datetime.datetime.now().astimezone().isoformat(timespec="seconds"), event, _clean(db), _clean(uid), _clean(login),
                               ",".join(_clean(i) for i in ips if i), _clean(reason)[:300]]) + "\n")
        return p
    except OSError:
        return None


def main(argv):
    """python3 apps/_odoo_users.py [--banned | --watched | --version]: logins of the banned (or watched) accounts, one per line."""
    if "--version" in argv:
        print(__version__)
        return 0
    s = state()
    for login in sorted(s["watched" if "--watched" in argv else "banned"]):
        print(login)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
