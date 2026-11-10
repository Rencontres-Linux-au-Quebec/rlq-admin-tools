#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _odoo_conf_check.py - checks an Odoo configuration file the way Odoo reads it (shared module, apps/; also a command).
#
"""Odoo has no command that only checks its configuration file: an error is seen when Odoo starts (or, worse, later). This module reads the
file as Odoo 18 does (odoo/tools/config.py: configparser.RawConfigParser, then optparse casts of the typed options) and reports:
  * a comment after a value (« limit_memory_soft_gevent = 2147483648 # 2048 MB »): Odoo keeps it IN the value, the integer is refused and Odoo
    does not start (only a line that STARTS with # or ; is a comment);
  * a key given twice in a section (configparser refuses the whole file), a line outside any section, no [options] section;
  * a typed option whose value is not of its type (integer, decimal number);
  * when the Odoo of the server is found (or given with --odoo-bin / --python): the real parsing of Odoo (config.parse_config) and the keys that
    Odoo does not know (typo: silently ignored);
  * a few sanity checks of the memory limits (values in BYTES; limit_memory_soft under a worker at rest; gevent limits for the live chat).

Command:  python3 apps/_odoo_conf_check.py [--lang fr|en] [--odoo-bin PATH] [--python PATH] [--tsv] FILE
Exit code: 0 = no error, 1 = errors (Odoo would refuse the file or misread a value), 2 = file unreadable. Reads only, never changes the file.
Library:  check(path, odoo_bin=None, python=None, language="fr") -> [(level, line, key, message)], level "error", "warning" or "info"."""
import configparser
import glob
import os
import re
import subprocess
import sys

__version__ = "1.0.20261109.211500"

# Typed options of Odoo 18 (odoo/tools/config.py, type="int" or "float"); the others are text. "True"/"False" are accepted for all of them
# (Odoo turns them into booleans before the casts).
INT_KEYS = {"http_port", "gevent_port", "longpolling_port", "xmlrpc_port", "db_port", "db_maxconn", "db_maxconn_gevent", "smtp_port", "workers",
            "max_cron_threads", "limit_memory_soft", "limit_memory_soft_gevent", "limit_memory_hard", "limit_memory_hard_gevent",
            "limit_time_cpu", "limit_time_real", "limit_time_real_cron", "limit_time_worker_cron", "limit_request", "osv_memory_count_limit",
            "list_db_size"}
FLOAT_KEYS = {"transient_age_limit", "osv_memory_age_limit"}
MB = 1048576

TEXTS = {
    "unreadable": ("fichier illisible : {e}", "file unreadable: {e}"),
    "no_options": ("aucune section [options] : Odoo n'en lit aucun réglage", "no [options] section: Odoo reads none of its settings"),
    "outside": ("ligne hors de toute section (avant [options]) : configparser refuse le fichier", "line outside any section (before [options]): configparser refuses the file"),
    "inline": ("commentaire après la valeur : Odoo le garde DANS la valeur ({v!r}) ; seule une ligne qui COMMENCE par # ou ; est un commentaire : "
               "mettre « {k} = {clean} » et le commentaire sur sa propre ligne, au-dessus",
               "comment after the value: Odoo keeps it IN the value ({v!r}); only a line that STARTS with # or ; is a comment: "
               "write « {k} = {clean} » and put the comment on its own line, above"),
    "duplicate": ("clé donnée deux fois (déjà à la ligne {first}) : configparser refuse tout le fichier, Odoo ne démarre pas",
                  "key given twice (already on line {first}): configparser refuses the whole file, Odoo does not start"),
    "int": ("entier attendu, lu {v!r} : Odoo refuse de démarrer (« invalid integer value »)", "integer expected, read {v!r}: Odoo refuses to start (« invalid integer value »)"),
    "float": ("nombre attendu, lu {v!r} : Odoo refuse de démarrer", "number expected, read {v!r}: Odoo refuses to start"),
    "syntax": ("syntaxe refusée par configparser (comme Odoo) : {e}", "syntax refused by configparser (as Odoo does): {e}"),
    "odoo_refuses": ("Odoo refuse ce fichier : {e}", "Odoo refuses this file: {e}"),
    "odoo_ok": ("lu sans erreur par l'Odoo du serveur ({bin})", "read without error by the Odoo of the server ({bin})"),
    "odoo_absent": ("Odoo du serveur introuvable (préciser --odoo-bin et --python) : vérification par Odoo lui-même non faite",
                    "Odoo of the server not found (give --odoo-bin and --python): no check by Odoo itself"),
    "unknown": ("clé inconnue d'Odoo, ignorée sans message (faute de frappe ?)", "key unknown to Odoo, ignored without a message (typo?)"),
    "soft_hard": ("limit_memory_soft ({s} Mo) au-dessus de limit_memory_hard ({h} Mo) : la limite dure arrive d'abord (MemoryError en pleine requête)",
                  "limit_memory_soft ({s} MB) above limit_memory_hard ({h} MB): the hard limit comes first (MemoryError during a request)"),
    "soft_low": ("limit_memory_soft {s} Mo : sous 1024 Mo de mémoire VIRTUELLE, les workers d'Odoo 18 (environ 660 Mo au repos) sont recyclés très souvent, "
                 "ou dès leur démarrage", "limit_memory_soft {s} MB: under 1024 MB of VIRTUAL memory, the Odoo 18 workers (about 660 MB at rest) are recycled "
                 "very often, or as soon as they start"),
    "units": ("{k} = {v} : valeur en OCTETS ; {v} octets, c'est presque rien (voulu {v} Mo ? -> {b})", "{k} = {v}: value in BYTES; {v} bytes is almost nothing (meant {v} MB? -> {b})"),
    "gevent": ("{k} non défini : le processus gevent (discussion en direct) prend la limite des workers ; conseillé : limit_memory_soft_gevent = 2147483648 "
               "et limit_memory_hard_gevent = 2684354560", "{k} not set: the gevent process (live chat) takes the limit of the workers; recommended: "
               "limit_memory_soft_gevent = 2147483648 and limit_memory_hard_gevent = 2684354560"),
}


def _t(key, language, **values):
    fr, en = TEXTS[key]
    return (en if language.startswith("en") else fr).format(**values)


def _number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_odoo(path):
    """(odoo-bin, python) of the running Odoo that uses `path` (or of any running Odoo), from /proc; (None, None) when not found (no root: the
    processes of the odoo account cannot be read)."""
    real = os.path.realpath(path)
    found = (None, None)
    for cmdline in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(cmdline, "rb") as f:
                argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
            proc = os.path.dirname(cmdline)
            cwd, exe = os.readlink(os.path.join(proc, "cwd")), os.readlink(os.path.join(proc, "exe"))
        except OSError:
            continue
        binary = next((a for a in argv[:3] if os.path.basename(a) in ("odoo-bin", "odoo")), None)
        if not binary or not os.path.basename(exe).startswith("python"):
            continue
        binary = os.path.normpath(os.path.join(cwd, binary))
        conf = next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("-c", "--config")), None) or \
            next((a.split("=", 1)[1] for a in argv if a.startswith("--config=")), None)
        if conf and os.path.realpath(os.path.join(cwd, conf)) == real:
            return binary, exe
        found = found if found[0] else (binary, exe)
    return found


ODOO_PARSE = r"""
import configparser, os, sys
root, conf = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
import odoo
from odoo.tools import config
try:
    config.parse_config(["-c", conf])
except SystemExit as e:
    sys.exit(3 if e.code else 0)
p = configparser.RawConfigParser()
p.read(conf)
known = set(config.options) | set(getattr(config, "casts", {}))
print("UNKNOWN|" + "|".join(k for k in (p.options("options") if p.has_section("options") else []) if k not in known))
"""


def check(path, odoo_bin=None, python=None, language="fr", use_odoo=True):
    """[(level, line, key, message)] for the file `path` (see the module text). Reads only. use_odoo=False: without the parsing of Odoo itself (fast)."""
    res = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        return [("error", 0, "", _t("unreadable", language, e=e))]
    section, seen, values = None, {}, {}
    for n, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text or text[0] in "#;":
            continue
        m = re.match(r"^\[([^\]]+)\]\s*$", text)
        if m:
            section = m.group(1).strip()
            continue
        m = re.match(r"^([^=:]+?)\s*[=:]\s*(.*)$", raw.strip())
        if not m:
            continue
        key, value = m.group(1).strip().lower(), m.group(2).strip()
        if section is None:
            res.append(("error", n, key, _t("outside", language)))
            continue
        if (section, key) in seen:
            res.append(("error", n, key, _t("duplicate", language, first=seen[(section, key)])))
        seen[(section, key)] = n
        comment = re.search(r"\s[#;]", value)
        if comment:
            clean = value[:comment.start()].strip()
            res.append(("error", n, key, _t("inline", language, v=value, k=key, clean=clean)))
            value = clean if section != "options" else value
        if section != "options":
            continue
        values[key] = (n, value)
        if value in ("True", "true", "False", "false") or comment:
            continue
        if key in INT_KEYS and not re.fullmatch(r"[+-]?\d+", value):
            res.append(("error", n, key, _t("int", language, v=value)))
        elif key in FLOAT_KEYS:
            try:
                float(value)
            except ValueError:
                res.append(("error", n, key, _t("float", language, v=value)))
    if not any(s == "options" for s, _k in seen) and not any(re.match(r"^\s*\[options\]", l) for l in lines):
        res.append(("error", 0, "", _t("no_options", language)))
    try:
        configparser.RawConfigParser().read_string("\n".join(lines), source=path)
    except configparser.Error as e:
        message = str(e).splitlines()[0]
        if not any(r[0] == "error" and ("twice" in r[3] or "deux fois" in r[3] or "section" in r[3]) for r in res):
            res.append(("error", getattr(e, "lineno", 0) or 0, "", _t("syntax", language, e=message)))
    # sanity of the memory limits (BYTES)
    soft, hard = (_number(values.get(k, (0, None))[1]) for k in ("limit_memory_soft", "limit_memory_hard"))
    workers = _number(values.get("workers", (0, None))[1]) or 0
    for key in ("limit_memory_soft", "limit_memory_hard", "limit_memory_soft_gevent", "limit_memory_hard_gevent"):
        v = _number(values.get(key, (0, None))[1])
        if v is not None and 0 < v < 100000:
            res.append(("error", values[key][0], key, _t("units", language, k=key, v=v, b=v * MB)))
    if soft and hard and soft > hard and hard >= 100000:
        res.append(("warning", values["limit_memory_soft"][0], "limit_memory_soft", _t("soft_hard", language, s=soft // MB, h=hard // MB)))
    if workers and soft and 100000 <= soft < 1024 * MB:
        res.append(("warning", values["limit_memory_soft"][0], "limit_memory_soft", _t("soft_low", language, s=soft // MB)))
    if workers:
        for key in ("limit_memory_soft_gevent", "limit_memory_hard_gevent"):
            if key not in values or values[key][1] in ("False", "false", ""):
                res.append(("info", values.get(key, (0,))[0], key, _t("gevent", language, k=key)))
    # the real parsing of Odoo, when it is found
    if not use_odoo:
        pass
    elif not (odoo_bin and python):
        found_bin, found_python = find_odoo(path)
        odoo_bin, python = odoo_bin or found_bin, python or found_python
    if use_odoo and odoo_bin and python and os.path.exists(odoo_bin):
        try:
            r = subprocess.run([python, "-I", "-c", ODOO_PARSE, os.path.dirname(os.path.abspath(odoo_bin)), path],
                               capture_output=True, text=True, timeout=120, cwd="/")
        except (OSError, subprocess.SubprocessError) as e:
            res.append(("warning", 0, "", _t("odoo_refuses", language, e=e)))
        else:
            if r.returncode:
                last = next((l for l in reversed(r.stderr.splitlines()) if l.strip()), "") or f"code {r.returncode}"
                res.append(("error", 0, "", _t("odoo_refuses", language, e=last[:300])))
            else:
                for out in r.stdout.splitlines():
                    if out.startswith("UNKNOWN|"):
                        for key in filter(None, out[8:].split("|")):
                            res.append(("warning", values.get(key, (0,))[0], key, _t("unknown", language)))
                res.append(("info", 0, "", _t("odoo_ok", language, bin=odoo_bin)))
    elif use_odoo:
        res.append(("info", 0, "", _t("odoo_absent", language)))
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(res, key=lambda r: (order[r[0]], r[1]))


def main(argv=None):
    import argparse
    lang_env = os.environ.get("NGINX_TOOLS_I18N_LANGUE") or os.environ.get("LANG", "fr")
    parser = argparse.ArgumentParser(prog="_odoo_conf_check.py", description="Checks an Odoo configuration file the way Odoo 18 reads it / "
                                     "Vérifie un fichier de configuration d'Odoo comme Odoo 18 le lit")
    parser.add_argument("--lang", choices=("en", "fr"), default="en" if lang_env.startswith("en") else "fr", help="language of the messages / langue des messages")
    parser.add_argument("--odoo-bin", help="odoo-bin of the server (found in the running processes otherwise) / odoo-bin du serveur")
    parser.add_argument("--python", help="Python of Odoo (its virtual environment) / Python d'Odoo")
    parser.add_argument("--tsv", action="store_true", help="LEVEL<TAB>LINE<TAB>KEY<TAB>MESSAGE lines (for the other programs) / lignes séparées par des tabulations")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("file", help="odoo.conf / config.conf")
    args = parser.parse_args(argv)
    if not os.access(args.file, os.R_OK):
        print(_t("unreadable", args.lang, e=args.file), file=sys.stderr)
        return 2
    results = check(args.file, args.odoo_bin, args.python, args.lang)
    colour = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    tags = {"error": ("[ÉCHEC]" if args.lang == "fr" else "[FAIL]", "31"), "warning": ("[ATTN]", "33"), "info": ("[INFO]", "36")}
    for level, line, key, message in results:
        if args.tsv:
            print(f"{level}\t{line}\t{key}\t{message}")
            continue
        tag, code = tags[level]
        where = (f"ligne {line}" if args.lang == "fr" else f"line {line}") if line else ""
        prefix = " ".join(x for x in (where, key) if x)
        print(f"{chr(27)}[{code}m{tag}{chr(27)}[0m " if colour else f"{tag} ", end="")
        print(f"{prefix} : {message}" if prefix and args.lang == "fr" else f"{prefix}: {message}" if prefix else message)
    if not args.tsv and not any(r[0] == "error" for r in results):
        print("[OK] " + ("aucune erreur dans " if args.lang == "fr" else "no error in ") + args.file)
    return 1 if any(r[0] == "error" for r in results) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
