#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026  Services-Linux Conseils Inc <Martial@Bigras.ca> <Martial.Bigras@Services-Conseils-Linux.com>
#
# This file is part of the nginx configuration of Rencontres Linux Québec. Free software: you can
# redistribute it and/or modify it under the terms of the GNU Affero General Public License published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# odoo-mail-retry.py — Odoo's UNSENT E-MAILS: the list (each e-mail's TITLE, its date, its recipients, the cause of the failure), then the
# offer to RESEND them.
#   * List: e-mails in « Delivery Failed » (state « exception » of mail.mail) of the last --days days (30 by default), read READ-ONLY from
#     PostgreSQL (apps/_odoo_db.py, root). Addresses masked (j***@gmail.com) except with --details. Cause recognized from Odoo's error (messages-per-
#     connection limit 452, sender refused 550...) with the mention « transient » (a resend goes through) or « PERMANENT » (comes back until the setting is fixed:
#     see app-log-check.py, section [5]).
#   * Resend: on a terminal, a menu — [t] all, [l] the oldest (a batch), [c] one by one, [N] none. « Resend » = put the e-mail back in the « Outgoing » state,
#     exactly like Odoo's « Retry » button: the scheduled action « Mail: Email Queue Manager » sends it at its next run. This is the program's ONLY write;
#     it only touches e-mails still in failure, and each resend is recorded in /var/lib/nginx-tools/mail-retry.log.
#   * Without a terminal (pipe, scheduled task): list only; --resend --yes resends without a question (--batch N: only the N oldest).
#   * Warnings before resending: PERMANENT cause (it will fail again); mail.session.batch.size undefined with many e-mails (risk of hitting the
#     messages-per-connection limit again: resend in batches).
# Configuration (common rule): /etc/default/odoo-mail-retry.conf THEN ~/.odoo-mail-retry.cfg (the last one wins; keys BATCH, DAYS, DB, DETAILS, LANGUAGE, NO_PROMPT); -c/--config: that file ALONE;
# the command line takes priority. The files read are always displayed, with the important options.
#
# VERSION HISTORY (summary — see doc/odoo-mail-retry.changelog.txt for full detail):
#   1.12.20261017.105442 — Options line: which setting decided the display language (apps/_i18n.py 1.17).
#   1.11.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.10.20261016.114848 — Invalid e-mail addresses of event registrations (--invalid-emails): suggested correction, registration and contact fixed, failed e-mails resent (--fix --yes).
#   1.9.20261015.215256 — Follows app-log-check 2.20 (classify_diagnostic, « short » key); no change of behavior.
#   1.8.20261015.201033 — Source code, comments and changelog in English (display stays French/English via lang/odoo-mail-retry.fr.po).
#   1.7.20261015.080630 — Root required from the start (everything goes through PostgreSQL).
#   1.6.20261015.073057 — Modification date of the configuration files read.
#   1.5.20261014.175821 — Common file app-default.conf; keys VERBOSE and DEBUG_LEVEL.
#   1.4.20261013.081500 — --sent N: the N latest e-mails sent.
#   1.3.20261012.103600 — Configuration file created at first start (apps/_config.py).
#   1.2.20261010.215000 — French or English display (--lang, LANGUAGE of the configuration file), catalog lang/odoo-mail-retry.en.po.
#   1.1.20261007.200504 — « One by one » menu: each question says WHO the e-mail is addressed to.
#   1.0.20261007.175936 — First version: list of unsent e-mails (title, date, recipients, cause) and offer to resend them.
#
# Usage:
#   odoo-mail-retry.py                      list of unsent e-mails, then the resend menu (on a terminal)
#   odoo-mail-retry.py --details            full recipient addresses
#   odoo-mail-retry.py --days 7             only the last 7 days
#   odoo-mail-retry.py --resend --yes       resends everything without a question; --batch 5: only the 5 oldest
#   odoo-mail-retry.py --sent 10           the 10 latest e-mails SENT (title, date, recipients), then quits
#   odoo-mail-retry.py --no-prompt          list only, even on a terminal
#   --db NOM, --lang en|fr, --verbose, --report-err, --version, --changelog

import argparse
import importlib.util
import os
import re
import signal
import sys
import textwrap
import time

try:                    # line editing in prompts (backspace ^H or ^?, arrows)
    import readline  # noqa: F401
except ImportError:
    pass

__version__ = "1.12.20261017.105442"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "doc", f"{SCRIPT_NAME}.changelog.txt")
SYSTEM_CONF = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), "odoo-mail-retry.conf")      # variable: tests only
USER_CONF = "~/.odoo-mail-retry.cfg"
RESEND_LOG = os.environ.get("ODOO_MAIL_RETRY_LOG", "/var/lib/nginx-tools/mail-retry.log")
DEFAULT_DAYS, DEFAULT_BATCH = 30, 10
BATCH_THRESHOLD = 20                  # above this mail.session.batch.size: risk of the messages-per-connection limit
VERBOSE = False


def _start():
    """Common context (apps/_i18n.py: language, translated print / input, parser); module absent: source language."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "ODOO_MAIL_RETRY_LANG", ("_email_check", "_odoo_db", "app-log-check"))
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


def wrap(text, **kwargs):
    """Translate BEFORE wrapping: a message cut over two lines would no longer match its catalog entry."""
    return textwrap.fill(I18N.tr(text) if I18N else text, **kwargs)


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


def load_module(name):
    """Component of apps/ (None if absent)."""
    path = os.path.join(SCRIPT_DIR, "apps", name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_diagnostics():
    """The app-log-check.py module (diagnostics base: cause of an e-mail failure), or None if absent."""
    path = os.path.join(SCRIPT_DIR, "app-log-check.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("app_log_check", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module if hasattr(module, "classify_diagnostic") else None
    except (OSError, ImportError, SyntaxError):
        return None


def read_config(explicite=None):
    """(values, files read, problems): /etc/default/odoo-mail-retry.conf then ~/.odoo-mail-retry.cfg (the last one wins); explicit (-c/--config):
    that file ALONE, which must exist (FileNotFoundError otherwise). Keys: BATCH, DAYS (positive numbers), DB, DETAILS and NO_PROMPT (yes/no), LANGUAGE (en, fr, auto)."""
    values, files_read, problems = {}, [], []
    if explicite and not os.path.isfile(explicite):
        raise FileNotFoundError(f"configuration file not found: {explicite}")
    if not explicite:                                          # first start: creates the default file (all options commented out)
        try:
            load_module("_config").creer_par_defaut("odoo-mail-retry")
        except Exception:
            pass
    common = []                                               # COMMON file for all programs (app-default.conf), read first: LANGUAGE, VERBOSE, DEBUG_LEVEL only
    if not explicite:
        try:
            common = [c for c, exists_ in load_module("_config").chemins_communs() if exists_]
        except Exception:
            common = []
    for path in (common if not explicite else []) + ([explicite] if explicite else [SYSTEM_CONF, os.path.expanduser(USER_CONF)]):
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
            m = re.fullmatch(r"(BATCH|DAYS)\s*=\s*[\"']?(\d+)[\"']?", line)
            b = re.fullmatch(r"(DETAILS|NO_PROMPT)\s*=\s*[\"']?(\w+)[\"']?", line)
            v = re.fullmatch(r"(VERBOSE|DEBUG_LEVEL)\s*=\s*[\"']?(\w*)[\"']?", line)
            if path in common and not (v or re.match(r"LANGUAGE\s*=", line)):
                continue                                       # the common file defines only LANGUAGE, VERBOSE and DEBUG_LEVEL
            t = re.fullmatch(r"(DB|LANGUAGE)\s*=\s*[\"']?([\w.@-]*)[\"']?", line)
            if m and int(m.group(2)) > 0:
                values[m.group(1)] = int(m.group(2))
            elif b and b.group(2).lower() in ("1", "true", "yes", "oui", "on", "0", "false", "no", "non", "off"):
                values[b.group(1)] = b.group(2).lower() in ("1", "true", "yes", "oui", "on")
            elif v:
                if v.group(1) == "VERBOSE" and v.group(2).lower() in ("1", "true", "yes", "oui", "on", "0", "false", "no", "non", "off"):
                    values["VERBOSE"] = v.group(2).lower() in ("1", "true", "yes", "oui", "on")
                elif v.group(1) == "DEBUG_LEVEL" and v.group(2).isdigit():
                    values["DEBUG_LEVEL"] = int(v.group(2))
                else:
                    problems.append(f"{path}:{n} : line ignored « {line} » (VERBOSE: yes/no; DEBUG_LEVEL: number)")
            elif t:
                if t.group(2):
                    values[t.group(1)] = t.group(2)
            else:
                problems.append(f"{path}:{n} : line ignored « {line} » (keys: BATCH=batch, DAYS=days: positive numbers; DB=database; DETAILS and NO_PROMPT: yes/no; LANGUAGE: en, fr, auto)")
    level = values.get("DEBUG_LEVEL", 0)
    if level >= 1 and "VERBOSE" not in values:               # DEBUG_LEVEL >= 1 means VERBOSE=yes
        values["VERBOSE"] = True
    if level:
        os.environ["NGINX_TOOLS_DEBUG_LEVEL"] = str(level)
    return values, files_read, problems


def mask(addresses):
    """« jean.dupont@exemple.org, x@y.fr » -> « j***@exemple.org, x***@y.fr » (the domain stays visible)."""
    def one(a):
        a = a.strip()
        m = re.fullmatch(r"(.*<)?([^<>@\s]+)@([^<>\s]+?)(>)?", a)
        return f"{m.group(1) or ''}{m.group(2)[:1]}***@{m.group(3)}{m.group(4) or ''}" if m else a
    return ", ".join(one(a) for a in re.split(r"[;,]\s*", addresses) if a.strip())


def local_date(instant):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(instant)) if instant else "?"


def cause_of(reason, diag):
    """(short label, permanent?) of the cause of a failure, from Odoo's error text; failing that, the beginning of that text."""
    d = diag.classify_diagnostic(reason) if diag is not None and reason else None
    if d is not None:
        return d["short"], bool(d.get("permanent"))
    useful = re.sub(r"^.*?serveur SMTP '[^']*'\.\s*", "", re.sub(r"\s+", " ", reason))      # without the preamble « Failed to send ... via SMTP server 'None'. »
    return (useful[:70] or "unknown cause"), False


def show_list(database, failures, state, days_list, details, diag):
    """The TITLE of each unsent e-mail (with its number, date, recipients, cause), then the totals per title, cause and day."""
    e = (state or {}).get("etats", {})
    print()
    print("=" * 100)
    print(f" Unsent e-mails — database {database}, {days_list} days: {len(failures)} failed to send"
          + (f", {e['outgoing']} queued for sending" if e.get("outgoing") else "") + (f", {e.get('sent', 0)} sent" if state else ""))
    if failures and not details:
        print(" (addresses masked; --details to see them in full)")
    print("=" * 100)
    if not failures:
        print("\n  No e-mail failed to send.")
        return
    by_title, by_cause, by_day = {}, {}, {}
    checker = email_checker()
    for m in failures:
        cause, permanent = cause_of(m["raison"], diag)
        bad = invalid_recipient(m["destinataires"], checker)
        shown = cause
        if bad:                                  # 1.10: invalid address — resending without fixing it fails again
            cause, permanent = "invalid address", True
            shown = f"invalid address ({bad[1]['reason']})" + (f", suggested: {bad[1]['suggestion'] if details else mask(bad[1]['suggestion'])}" if bad[1]["suggestion"] else "")
        m["cause"], m["permanente"], m["invalide"] = cause, permanent, bool(bad)
        print()
        print(wrap(f"#{m['id']:<6} {local_date(m['instant'])}   « {m['sujet'] or '(no title)'} »", width=110, subsequent_indent=" " * 8))
        print(wrap(f"À : {(m['destinataires'] if details else mask(m['destinataires'])) or '(no recipient recorded)'} — cause: {shown}"
                            + (" — PERMANENT" if permanent else " — transient" if diag is not None and cause != "unknown cause" and m["raison"] else ""),
                            width=110, initial_indent=" " * 8, subsequent_indent=" " * 13))
        by_title[m["sujet"] or "(no title)"] = by_title.get(m["sujet"] or "(no title)", 0) + 1
        by_cause[cause] = by_cause.get(cause, 0) + 1
        day = local_date(m["instant"])[:10]
        by_day[day] = by_day.get(day, 0) + 1
    print()
    print(wrap("By title: " + " ; ".join(f"« {t} » ×{n}" for t, n in sorted(by_title.items(), key=lambda x: (-x[1], x[0]))),
                        width=110, subsequent_indent=" " * 11))
    print(wrap("By cause: " + " ; ".join(f"{c} ×{n}" for c, n in sorted(by_cause.items(), key=lambda x: (-x[1], x[0]))), width=110, subsequent_indent=" " * 11))
    print("By day  : " + " ; ".join(f"{j} ×{n}" for j, n in sorted(by_day.items())))


def show_sent(database, sent_mails, details):
    """The latest e-mails SENT (state « sent »), most recent first: number, date, title, recipients."""
    print()
    print("=" * 100)
    print(f" {len(sent_mails)} latest sent e-mails — database {database}")
    if sent_mails and not details:
        print(" (addresses masked; --details to see them in full)")
    print("=" * 100)
    if not sent_mails:
        print("\n  No e-mail sent.")
    for m in sent_mails:
        print()
        print(wrap(f"#{m['id']:<6} {local_date(m['instant'])}   « {m['sujet'] or '(no title)'} »", width=110, subsequent_indent=" " * 8))
        print(wrap(f"À : {(m['destinataires'] if details else mask(m['destinataires'])) or '(no recipient recorded)'}", width=110, initial_indent=" " * 8, subsequent_indent=" " * 13))


def warnings(db, database, failures):
    """Warnings BEFORE a resend: permanent causes (it will fail again), mail.session.batch.size (hitting the per-connection limit again)."""
    res = []
    invalid_list = [m for m in failures if m.get("invalide")]
    if invalid_list:
        res.append(f"[ATTN] {len(invalid_list)} e-mail(s) addressed to an INVALID address: resent as is, they fail again — fix the address first "
                   "(menu of the invalid addresses above, odoo-mail-retry.py --invalid-emails, or the contact in Odoo).")
    permanents_list = [m for m in failures if m.get("permanente") and not m.get("invalide")]
    if permanents_list:
        causes_list = sorted({m["cause"] for m in permanents_list})
        res.append(f"[ATTN] {len(permanents_list)} e-mail(s) have a PERMANENT cause ({' ; '.join(causes_list)}): they will fail again until the setting is fixed — "
                   "see app-log-check.py, section [5] (cause and solution).")
    parametres = db.parametres(database, "mail.") or {}
    batch_size = parametres.get("mail.session.batch.size", "")
    if len(failures) > DEFAULT_BATCH and not (batch_size.isdigit() and int(batch_size) <= BATCH_THRESHOLD):
        res.append(f"[ATTN] mail.session.batch.size is {'set to ' + batch_size if batch_size else 'not set'} : Odoo will send these {len(failures)} e-mails over ONE single SMTP connection "
                   "and may hit the per-connection message limit (error 452). Set this parameter first (app-log-check.py, section [5]) "
                   "or resend in batches (choice « l »).")
    return res


def ask(text):
    try:
        return input(text).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def choose(failures, batch_size, details=False):
    """The resend menu (on a terminal): returns the list of e-mail numbers to resend."""
    n = len(failures)
    print()
    print(f"Renvoyer ces {n} e-mail(s)?")
    answer = ask(f"  [a] all ({n})   [l] the {min(batch_size, n)} oldest   [c] choose one by one   [N] none: ")
    if answer in ("t", "tous", "o", "oui", "a", "all", "y", "yes"):
        return [m["id"] for m in failures]
    if answer in ("l", "lot"):
        return [m["id"] for m in failures[:batch_size]]
    if answer in ("c", "choisir", "choose"):
        ids = []
        for m in failures:
            recipient = (m["destinataires"] if details else mask(m["destinataires"]))[:80] or "(no recipient recorded)"      # titles look alike: say WHO it goes to
            r = ask(f"  #{m['id']} {local_date(m['instant'])} « {m['sujet'][:60]} » → to: {recipient} — {m['cause']} — resend? [y/N/q]: ")
            if r == "q":
                break
            if r in ("o", "oui", "y", "yes"):
                ids.append(m["id"])
        return ids
    return []


def record_resend(database, ids):
    """Record of each resend: date, database, count, numbers (RESEND_LOG). Silent if the folder is inaccessible."""
    try:
        os.makedirs(os.path.dirname(RESEND_LOG), exist_ok=True)
        with open(RESEND_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{database}\t{len(ids)}\t{','.join(map(str, ids))}\n")
        return True
    except OSError:
        return False


def resend_mails(db, database, ids):
    """Puts e-mails back in the « Outgoing » state (like « Retry » in Odoo); Odoo sends them at its next run."""
    resent = db.remettre_en_attente(database, ids)
    if resent is None:
        eprint(f"ERROR: unable to put the e-mails back in the queue (database {database} : PostgreSQL unreachable, or root required).")
        return 2
    ignored = sorted(set(ids) - set(resent))
    print()
    print(f"{len(resent)} e-mail(s) put back in the « Outgoing » state: {', '.join(f'#{i}' for i in resent) or 'none'}.")
    if ignored:
        print(f"  {len(ignored)} ignored: no longer failed (already resent or deleted): {', '.join(f'#{i}' for i in ignored)}.")
    if resent:
        record_resend(database, resent)
        print(wrap("Odoo will send them at the next run of the scheduled action « Mail: Email Queue Manager »; to do it right now: Settings ▸ Technical ▸ Scheduled Actions ▸ « Mail: Email Queue Manager » ▸ Run Manually. Then run odoo-mail-retry.py again: those that left are no longer in the list; those that fail again come back with their cause.", width=110))
    return 0


# --- 1.10: INVALID e-mail addresses (event registrations): detection, suggested correction, fix of the registration and its contact, resend --------
def email_checker():
    return load_module("_email_check")


def invalid_recipient(addresses, checker):
    """(address, check) of the first invalid address among the recipients of a failed e-mail, or None."""
    if checker is None:
        return None
    for a in re.split(r"[;,]\s*", addresses or ""):
        a = a.strip()
        m = re.search(r"<([^<>]*)>", a)
        a = m.group(1).strip() if m else a
        if not a:
            continue
        c = checker.check(a)
        if c["reason"]:
            return a, c
    return None


def find_invalid_registrations(db, database, days_list, checker):
    """[{registration…, "check"}] of the registrations of the last days whose e-mail address is invalid or has a probable typo (most recent first)."""
    if checker is None or not hasattr(db, "registration_emails"):
        return []
    regs = db.registration_emails(database, days_list) or []
    res = []
    for r in regs:
        c = checker.check(r["email"])
        if c["reason"]:
            r["check"] = c
            res.append(r)
    return res


def show_invalid(database, invalid, details):
    print()
    print("=" * 100)
    print(f" Invalid e-mail addresses of event registrations — database {database} — {len(invalid)} registration(s)")
    if invalid and not details:
        print(" (addresses masked; --details to see them in full — the correction menu shows them in full)")
    print("=" * 100)
    if not invalid:
        print("\n  No registration with an invalid e-mail address.")
        return
    for r in invalid:
        c = r["check"]
        addr = r["email"] if details else mask(r["email"])
        sug = (c["suggestion"] if details else mask(c["suggestion"])) if c["suggestion"] else ""
        print()
        print(wrap(f"Registration #{r['id']:<6} {local_date(r['when'])}   « {r['event'] or '(no event)'} » — {r['name'] or '(no name)'}", width=110, subsequent_indent=" " * 8))
        print(wrap(f"Address: {addr} — {c['reason']}" + (f" — suggested correction: {sug}" if sug else " — no automatic correction: to type")
                   + (f" — Odoo account: {r['login'] if details else mask(r['login'])} (login not changed)" if r.get("login") else ""),
                   width=110, initial_indent=" " * 8, subsequent_indent=" " * 13))


def record_fix(database, r, new, result):
    try:
        os.makedirs(os.path.dirname(RESEND_LOG), exist_ok=True)
        with open(RESEND_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{database}\tfix-email\tregistration={r['id']}\tpartner={r['partner_id']}\t{r['email']} -> {new}\t"
                    f"registration:{result['registration']} partner:{result['partner']} mails:{result['mails']}\n")
    except OSError:
        pass


def fix_one(db, database, r, new, checker):
    """Fixes the address of one registration (and of its contact if it holds the same address) and resends its failed e-mails. True on success."""
    c = checker.check(new)
    if not c["valid"]:
        print(f"  « {new} » is not a valid address either ({c['reason']}): nothing changed.")
        return False
    mails = db.failed_mails_for(database, r["id"], r["email"]) or []
    result = db.fix_registration_email(database, r["id"], r["partner_id"] if r.get("partner_email") == r["email"] else 0, r["email"], new, mails)
    if result is None:
        eprint(f"ERROR: registration #{r['id']} not fixed (PostgreSQL write failed, root required): nothing changed.")
        return False
    record_fix(database, r, new, result)
    print(f"  Registration #{r['id']} — {r['email']} → {new} — registration {'fixed' if result['registration'] else 'unchanged (address already modified)'}"
          + (f", contact {'fixed' if result['partner'] else 'unchanged'}" if r.get("partner_id") and r.get("partner_email") == r["email"] else "")
          + (f", {result['mails']} failed e-mail(s) put back in « Outgoing » (sent to the new address)" if result["mails"] else ", no failed e-mail to resend"))
    if not result["mails"]:
        print("    (the confirmation e-mail was never created with this address: resend it from Odoo — Events ▸ registration ▸ « Send by e-mail », or the « Invalid e-mails » menu of the rlq_survey_report module)")
    if r.get("login") and r["login"] == r["email"]:
        print(f"    The Odoo account keeps its login « {r['login']} » (the person logs in with it): change it in Odoo if needed (Settings ▸ Users).")
    return True


def fix_menu(db, database, invalid, yes, checker):
    """[a] every suggested correction, [c] one by one (accept, type another address or skip), [N] nothing. --fix --yes: the suggested corrections only."""
    with_sug = [r for r in invalid if r["check"]["suggestion"]]
    if yes:
        done = sum(fix_one(db, database, r, r["check"]["suggestion"], checker) for r in with_sug)
        print(f"{done} address(es) fixed; {len(invalid) - len(with_sug)} without automatic correction (to fix in the menu or in Odoo).")
        return 0
    print()
    answer = ask(f"Fix these addresses?  [a] the {len(with_sug)} suggested correction(s)   [c] one by one   [N] none: ")
    if answer in ("a", "all", "t", "tous", "o", "oui", "y", "yes"):
        done = sum(fix_one(db, database, r, r["check"]["suggestion"], checker) for r in with_sug)
        print(f"{done} address(es) fixed.")
    elif answer in ("c", "choose", "choisir"):
        for r in invalid:
            sug = r["check"]["suggestion"]
            prompt = (f"  #{r['id']} {r['name'][:40]} — {r['email']} ({r['check']['reason']}) → "
                      + (f"[Enter] {sug}  [another address]  [s] skip  [q] quit: " if sug else "[another address]  [Enter] skip  [q] quit: "))
            try:
                raw = input(prompt).strip()             # not lowercased: an address typed by hand stays as typed
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if raw.lower() == "q":
                break
            if raw.lower() in ("s", "skip", "p", "passer") or (not raw and not sug):
                continue
            fix_one(db, database, r, sug if not raw else raw, checker)
    else:
        print("No address fixed.")
    return 0


def show_changelog():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        with open(CHANGELOG_FILE, encoding="utf-8") as f:
            text = f.read()
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
        return super().add_usage(usage, actions if groups else sorted(actions, key=self._key), groups, prefix)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._key))


class LocalizedArgumentParser(argparse.ArgumentParser):
    """Fallback parser (apps/_i18n.py missing): options in alphabetical order, English messages."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", SortedHelp)
        super().__init__(*args, **kwargs)


def main():
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(description="List of the Odoo e-mails not sent (title, date, recipients, cause), then offer to resend them.")
    parser.add_argument("--batch", type=int, default=None, metavar="N",
                        help=f"Size of a resend batch (choice « l » of the menu: the N oldest; default {DEFAULT_BATCH}); with --resend --yes: resends only the N oldest")
    parser.add_argument("-c", "--config", default=None, metavar="FILE",
                        help=f"This configuration file ALONE (default: {SYSTEM_CONF}, then {USER_CONF}; keys BATCH, DAYS, DB, DETAILS, LANGUAGE, NO_PROMPT)")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("--days", type=int, default=None, metavar="N", help=f"E-mails of the last N days (default: {DEFAULT_DAYS})")
    parser.add_argument("--db", default=None, metavar="NAME", help="Odoo database (default: all databases that have e-mails)")
    parser.add_argument("--details", action="store_true", help="Full recipient addresses (masked by default)")
    parser.add_argument("--fix", action="store_true", help="With --yes: fix the invalid addresses of the registrations with the SUGGESTED correction and resend their e-mails, without questions")
    parser.add_argument("--invalid-emails", action="store_true",
                        help="Only the event registrations whose e-mail address is invalid (mariebc33@gmail'com, gmial.com…) with the suggested correction, then the offer to fix the registration and its contact and to resend the e-mail")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--no-prompt", action="store_true", help="List only: no question, even on a terminal")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--resend", action="store_true", help="With --yes: resend without asking")
    parser.add_argument("--sent", type=int, default=None, metavar="N", help="Shows the N latest SENT e-mails (title, date, recipients) and exits, without the list of failures")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show each external command run")
    parser.add_argument("--version", action="version", version=f"odoo-mail-retry.py version {__version__}")
    parser.add_argument("--yes", action="store_true", help="With --resend: confirm the resend (without it, never resend without a terminal)")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version prints it itself)
        print(f"odoo-mail-retry.py v{__version__}")
    args = parser.parse_args()
    refusal = load_module("_config").refus_non_root("odoo-mail-retry.py", "every reading or re-queuing of e-mails goes through PostgreSQL (postgres account)")
    if refusal:
        eprint(refusal)
        return 1
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
    days_list = args.days if args.days is not None else config.get("DAYS", DEFAULT_DAYS)
    batch_size = args.batch if args.batch is not None else config.get("BATCH", DEFAULT_BATCH)
    args.db = args.db or config.get("DB")
    args.details = args.details or config.get("DETAILS", False)
    args.no_prompt = args.no_prompt or config.get("NO_PROMPT", False)
    if days_list < 1 or batch_size < 1 or (args.sent is not None and args.sent < 1):
        parser.error("--days, --batch and --sent must be positive numbers")
    if args.config:
        read_files = f"{load_module('_config').avec_date(files_read[0])} (requested by -c/--config: no other file is read)"
    else:
        read_files = ", then ".join(load_module("_config").avec_date(c) for c in files_read) + (" (the last one wins)" if len(files_read) > 1 else "") if files_read else "no file (default values)"
    created = os.environ.get("NGINX_TOOLS_CONFIG_CREE")
    if created and created in files_read:
        read_files += " (file just created: every option is in a comment, default values)"
    print(f"Configuration read: {read_files}")
    print(f"  Options: --lang {LANGUAGE}{lang_origin()} · e-mails of the last {days_list} days · resend batch: {batch_size} e-mails"
          + (f" · database {args.db}" if args.db else "") + (" · full recipient addresses" if args.details else "") + (" · no questions" if args.no_prompt else ""))
    for p in problems:
        eprint(f"  ATTENTION {p}")
    db = load_module("_odoo_db")
    if db is None:
        eprint("ERROR: component apps/_odoo_db.py missing — deploy the complete nginx-tools.zip.")
        return 2
    db.VERBOSE = VERBOSE
    databases = [args.db] if args.db else db.bases_odoo()
    if databases is None:
        eprint("ERROR: PostgreSQL unreachable (psql command missing, or root required: run again as root).")
        return 2
    if not databases:
        eprint("No Odoo database (mail_mail table) found in PostgreSQL — specify --db NAME.")
        return 2
    if args.resend and args.yes and len(databases) > 1:
        eprint(f"ERROR: several databases ({', '.join(databases)}): specify --db NAME for a resend without questions.")
        return 2
    if args.sent is not None:
        code = 0
        for database in databases:
            sent_mails = db.courriels_envoyes(database, args.sent)
            if sent_mails is None:
                eprint(f"ERROR: database {database} unreadable (PostgreSQL unreachable, unknown database, or root required).")
                code = 2
                continue
            show_sent(database, sent_mails, args.details)
        return code
    diag = load_diagnostics()
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not args.no_prompt
    checker = email_checker()
    code = 0
    for database in databases:
        invalid = find_invalid_registrations(db, database, days_list, checker)
        if args.invalid_emails or invalid:          # 1.10: invalid addresses first — fixing them resends their e-mails
            show_invalid(database, invalid, args.details)
            if invalid and args.fix and args.yes:
                fix_menu(db, database, invalid, True, checker)
            elif invalid and interactive:
                fix_menu(db, database, invalid, False, checker)
            elif invalid:
                print("To fix them: run again on a terminal (menu), or with --fix --yes (suggested corrections only).")
        if args.invalid_emails:
            continue
        failures = db.courriels_en_echec(database, days_list)
        if failures is None:
            eprint(f"ERROR: database {database} unreadable (PostgreSQL unreachable, unknown database, or root required).")
            code = 2
            continue
        show_list(database, failures, db.courriels(database, days_list), days_list, args.details, diag)
        if not failures:
            continue
        print()
        for line in warnings(db, database, failures):
            print(wrap(line, width=110, subsequent_indent="       "))
        if args.resend and args.yes:
            ids = [m["id"] for m in failures][:args.batch] if args.batch is not None else [m["id"] for m in failures]
        elif interactive:
            ids = choose(failures, batch_size, args.details)
        else:
            print("To resend them: run again on a terminal (menu), or with --resend --yes (--batch N: only the N oldest).")
            continue
        if not ids:
            print("No e-mail resent.")
            continue
        code = max(code, resend_mails(db, database, ids))
    return code


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
