#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# link-page-events.py - upcoming events of Odoo for the link pages of nginx-link-page.sh (PAGE_n_EVENTS, PAGE_n_COUNTDOWN).
# Copyright (C) 2026 Services-Conseils Linux Inc. - AGPL-3.0-or-later (see LICENSE).
#
# Usage: link-page-events.py COUNT LANG   (LANG: fr or en; the names of the events are read in that language)
# Environment: ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_KEY_FILE (file holding only the API key, mode 600; the key never appears on a
#   command line). For the tests: NGINX_LINK_PAGE_EVENTS_JSON=FILE (a list of events, same fields as Odoo) replaces the call to Odoo.
# Output: one line per event, fields separated by tabs: BEGIN (YYYY-MM-DD HH:MM, local time of the event) END (YYYY-MM-DD) NAME URL.
# Only the published events that are not over are read (event.event, search_read, read only). Exit code 1 with a message on stderr
# when Odoo cannot be reached or refuses the account.
import datetime
import json
import os
import sys
import xmlrpc.client

try:
    from zoneinfo import ZoneInfo
except ImportError:                      # Python < 3.9: times stay in UTC
    ZoneInfo = None

LANGUES_ODOO = {"fr": "fr_CA", "en": "en_US"}


def lire_odoo(nombre, langue):
    url = os.environ.get("ODOO_URL", "").rstrip("/")
    db, login = os.environ.get("ODOO_DB", ""), os.environ.get("ODOO_LOGIN", "")
    with open(os.environ.get("ODOO_KEY_FILE", ""), encoding="utf-8") as f:
        cle = f.read().strip()
    commun = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common", allow_none=True)
    uid = commun.authenticate(db, login, cle, {})
    if not uid:
        raise RuntimeError("authentication refused (EVENTS_ODOO_LOGIN, key file)")
    objets = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object", allow_none=True)
    maintenant = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return objets.execute_kw(db, uid, cle, "event.event", "search_read",
                             [[("date_end", ">=", maintenant), ("website_published", "=", True)]],
                             {"fields": ["name", "date_begin", "date_end", "date_tz", "website_url"], "order": "date_begin asc",
                              "limit": nombre, "context": {"lang": LANGUES_ODOO.get(langue, "en_US")}}), url


def locale(valeur, fuseau):
    """'YYYY-MM-DD HH:MM:SS' in UTC (Odoo) -> datetime in the time zone of the event."""
    moment = datetime.datetime.strptime(str(valeur)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    if ZoneInfo and fuseau:
        try:
            return moment.astimezone(ZoneInfo(fuseau))
        except Exception:                # unknown zone name: UTC
            pass
    return moment


def main():
    nombre, langue = int(sys.argv[1]), sys.argv[2]
    try:
        if os.environ.get("NGINX_LINK_PAGE_EVENTS_JSON"):
            with open(os.environ["NGINX_LINK_PAGE_EVENTS_JSON"], encoding="utf-8") as f:
                evenements, base = json.load(f)[:nombre], os.environ.get("ODOO_URL", "").rstrip("/")
        else:
            evenements, base = lire_odoo(nombre, langue)
    except (OSError, ValueError, RuntimeError, xmlrpc.client.Error) as erreur:
        print(f"Odoo: {erreur}", file=sys.stderr)
        return 1
    for e in evenements:
        fuseau = e.get("date_tz") or "America/Toronto"
        debut, fin = locale(e["date_begin"], fuseau), locale(e["date_end"], fuseau)
        nom = " ".join(str(e.get("name") or "").split())
        adresse = str(e.get("website_url") or "")
        if adresse.startswith("/"):
            adresse = base + adresse
        if not nom or not adresse.startswith("https://"):
            continue
        print(f"{debut:%Y-%m-%d %H:%M}\t{fin:%Y-%m-%d}\t{nom}\t{adresse}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
