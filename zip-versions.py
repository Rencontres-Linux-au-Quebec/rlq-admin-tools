#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# zip-versions.py - versions contained in the project archives (nginx-tools.zip, nginx-tools-tests.zip, nginx-odoo-config.zip),
# WITHOUT extracting them: version of each program, date of the nginx configuration log, most recent file.
# Any other archive (e.g. an Odoo module): version of its manifest, of its CHANGELOG, of package.json, etc.
# Several archives of the same type (e.g. "nginx-tools (2).zip" in downloads): the most recent one is designated,
# the one to attach to the discussion. --installed: comparison with what is deployed on the server.
#
#
# Usage:
#   zip-versions.py                       archives (*.zip) of the current directory
#   zip-versions.py ~/Downloads           archives of a directory (and the installation it contains, if any)
#   zip-versions.py a.zip b.zip           these archives
#   zip-versions.py --installed           ... compared with /root/scripts (programs) and /etc/nginx (configuration)
#   zip-versions.py --installed DIR --nginx-dir DIR2
#   --version ; --changelog ; --report-err

import argparse
import datetime
import fnmatch
import glob
import importlib.util
import os
import re
import signal
import sys
import zipfile

__version__ = "1.16.20261022.231529"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
def _start():
    """Common context (apps/_i18n.py: language, configuration, translated print / input, parser); module missing (script copied alone): source language, no configuration."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "ZIP_VERSIONS_LANG")
    except Exception:
        return None


I18N = _start()
LANGUAGE = I18N.langue if I18N else "fr"
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 - every displayed text goes through the translator (no effect when the display language is the source language)
# Configuration file options (/etc/default/zip-versions.conf, then the personal file .zip-versions.conf): KEY -> (command-line option, type).
# LANGUAGE: en, fr, or auto (follow LC_ALL / LANG).
SCHEMA_CONFIG = {"INSTALLED": ("installed", str), "NGINX_DIR": ("nginx_dir", str)}
DEFAULT_INSTALLATION = "/root/scripts"
DEFAULT_NGINX = "/etc/nginx"
VERSION_RE = re.compile(r'(?:SCRIPT_VERSION|__version__)\s*=\s*"(\d+\.\d+\.\d{8}\.\d{6})"')
CONFIG_LOG_RE = re.compile(r"(?m)^- (\d{4}-\d{2}-\d{2}) :")
PROGRAM_RE = re.compile(r"\.(sh|py)$")
BARE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d{8}\.\d{6}$")
SUITE_VERSION_FILE = "doc/nginx-tools.version"   # version of the nginx-tools archive (own name: no shared "VERSION")
# File carrying the archive version, per type: nginx-tools: doc/nginx-tools.version; nginx-odoo-config: VERSION
# (the configuration has no program to version; it is delivered as nginx-odoo-config.1.0.zip).
VERSION_FILES = {"nginx-tools": SUITE_VERSION_FILE, "nginx-odoo-config": "VERSION"}
MAX_READ_SIZE = 4 * 1024 * 1024          # guard: a larger member is not one of our programs

COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def color(code, text):
    return f"\x1b[{code}m{text}\x1b[0m" if COLOR else text


DATED_VERSION_RE = re.compile(r"(?<!\x1b\[1;32m)\b(\d+\.\d+\.(\d{8})\.\d{6})\b")
_print = print
DATE_ISO_RE = re.compile(r"(?<![\w:-])((\d{4})-(\d\d)-(\d\d)(?: \d\d:\d\d(?::\d\d)?)?)(?![\w-])")      # "2026-10-15 17:28": date of a file (module versions without a date)
VIEWS = {"today": False}


def colorize_versions(text):
    """In EVERY displayed line (all sections, including « ARCHIVES TO ATTACH TO THE DISCUSSION »): a version dated today turns bold green."""
    if not COLOR or not isinstance(text, str):
        return text

    def substitute(m):
        if m.group(2) != today():
            return m.group(0)
        VIEWS["today"] = True
        return color("1;32", m.group(1))
    def substitute_date(m):
        if m.group(2) + m.group(3) + m.group(4) != today():
            return m.group(0)
        VIEWS["today"] = True
        return color("1;32", m.group(1))
    # ISO dates are colored only in the segments outside ANSI codes (an already green version is not recolored)
    pieces = re.split(r"(\x1b\[[0-9;]*m)", DATED_VERSION_RE.sub(substitute, text))
    res, colored = [], False
    for m in pieces:
        if m.startswith("\x1b["):
            colored = m not in ("\x1b[0m", "\x1b[m")
            res.append(m)
        else:
            res.append(m if colored else DATE_ISO_RE.sub(substitute_date, m))
    return "".join(res)


def print(*args, **kwargs):  # noqa: A001 - the program's single output path: color of today's versions in all sections
    _print(*(colorize_versions(a) for a in args), **kwargs)


def OK(t):
    return f"{color('1;32', '[OK]')}   {t}"


def ATTN(t):
    return f"{color('1;33', '[ATTN]')} {t}"


def today():
    """Local date of the day in the version format (YYYYMMDD)."""
    return datetime.datetime.now().strftime("%Y%m%d")


def is_today(v):
    """True if the version « 2.37.20261001.090925 » carries today's local date."""
    try:
        return str(v).split(".")[2] == today()
    except IndexError:
        return False


def colored_version(v):
    """The version in bold green if it is dated today (the most recently modified one stands out at a glance), otherwise unchanged."""
    return color("1;32", v) if is_today(v) else v


def date_key(v):
    """Date and time of a version (« 2.37.20261001.090925 » -> (20261001, 90925)): recency order between programs."""
    return version_key(v)[2:] or (-1,)


def version_key(v):
    """« 2.37.20261001.090925 » -> (2, 37, 20261001, 90925): order MAJOR, MINOR, date, time."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (AttributeError, ValueError):
        return (-1,)


# ------------------------------------------------------------------------------------------------------------------
# Reading a source: .zip archive (no extraction) or installed directory. Common result:
#   {"name", "path", "type", "date" (most recent file), "programs" {relative path: version},
#    "config_log" (last date of the nginx-odoo README log), "config_files" {relative path: bytes}}
# ------------------------------------------------------------------------------------------------------------------
OUR_TYPES = ("nginx-tools", "nginx-tools-tests", "nginx-odoo-config")
# Archives of other programs (1.2): version read from the usual files, whatever the project.
CHANGELOG_RE = re.compile(r"(?i)(^|/)(changelog|changes|history|historique|news)(\.(md|txt|rst))?$|\.changelog\.txt$")
TITLE_VERSION_RE = re.compile(r"(?im)^[ \t]*#{1,4}[ \t]*\[?[ \t]*(?:version[ \t]+|v)?(\d+(?:\.\d+){1,5})\b")
TITLE_DATE_RE = re.compile(r"(?m)^[ \t]*#{1,4}.*?\b(\d{4}-\d{2}-\d{2})\b")
MANIFEST_RE = re.compile(r"(?:^|/)__(?:manifest|openerp)__\.py$")
MANIFEST_VERSION_RE = re.compile(r"""['"]version['"]\s*:\s*['"]([^'"]+)['"]""")
JSON_VERSION_RE = re.compile(r'"version"\s*:\s*"([^"]+)"')
TOML_VERSION_RE = re.compile(r'(?m)^\s*version\s*=\s*"([^"]+)"')
CODE_VERSION_RE = re.compile(r"""(?m)^\s*(?:readonly\s+)?(?:__version__|SCRIPT_VERSION|VERSION)\s*=\s*['"](\d+(?:\.\d+){1,5})['"]""")
TESTS_DIR_RE = re.compile(r"(?:^|/)(?:tests?|testing)/|(?:^|/)test_[^/]*$|_test\.py$")
SUITE_SIGNATURE = "test_web_monitor.py"     # recognizes OUR suite in an old "tests/" folder (shared name)


def archive_type(names):
    """(type, old name?) from the top-level directory: nginx-tools, nginx-tools-tests, nginx-odoo-config.
    A « tests/ » is our suite (old name, before 1.1) only if it contains test_web_monitor.py: the tests.zip
    of other programs are « other » (ignored)."""
    roots = {n.split("/", 1)[0] for n in names if "/" in n}
    for root, t in (("nginx-tools-tests", "nginx-tools-tests"), ("nginx-tools", "nginx-tools"), ("nginx-odoo", "nginx-odoo-config")):
        if root in roots:
            return t, False
    if "tests" in roots:
        return ("nginx-tools-tests", True) if f"tests/{SUITE_SIGNATURE}" in names else ("autre", False)
    if len(roots) == 1 and all("/" in n for n in names):
        return roots.pop(), False                          # other program: its top-level directory (1.2)
    return "unknown", False


def relative(name):
    """Path without the archive's top-level directory (nginx-tools/apps/_rapport.py -> apps/_rapport.py)."""
    return name.split("/", 1)[1] if "/" in name else name


def is_program(source_type, rel):
    """Versioned program of the suite: top-level *.sh and *.py, apps/*, and tests/run-all.sh (test modules
    contain fake versions in their data: never read as programs)."""
    if source_type == "nginx-tools-tests":
        return rel == "run-all.sh"
    if source_type == "installation" and "/" in rel and not rel.startswith("apps/"):
        return rel in ("nginx-tools-tests/run-all.sh", "tests/run-all.sh")
    return bool(PROGRAM_RE.search(rel)) and (rel.count("/") == 0 or rel.startswith("apps/"))


def parse_text(res, rel, text, size_bytes):
    if is_program(res["type"], rel):
        m = VERSION_RE.search(text)
        if m:
            res["programs"][rel] = m.group(1)
    if res["type"] == "nginx-odoo-config":
        if rel == "README.md":
            dates = CONFIG_LOG_RE.findall(text)
            res["config_log"] = max(dates) if dates else None
        res["config_files"][rel] = size_bytes


def generic_key(v):
    """Order of any version (« 18.0.1.4.0 », « v2.3 »): its numbers, in order."""
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def should_read_generic(rel):
    """File where any program declares its version (1.2)."""
    name = rel.rsplit("/", 1)[-1]
    return bool(CHANGELOG_RE.search(rel) or MANIFEST_RE.search(rel) or name in ("package.json", "pyproject.toml", "VERSION")
                or (PROGRAM_RE.search(rel) and not TESTS_DIR_RE.search(rel)))


def parse_generic(res, rel, text):
    """Versions of any program: manifest (Odoo), CHANGELOG (highest version and most recent title date),
    package.json, pyproject.toml, VERSION file, __version__ / SCRIPT_VERSION / VERSION of the code (outside tests)."""
    name = rel.rsplit("/", 1)[-1]
    found = None
    if MANIFEST_RE.search(rel):
        m = MANIFEST_VERSION_RE.search(text)
        found = ("manifest", m.group(1)) if m else None
    elif CHANGELOG_RE.search(rel):
        versions = TITLE_VERSION_RE.findall(text)
        dates = TITLE_DATE_RE.findall(text)
        v = max(versions, key=generic_key) if versions else None
        d = max(dates) if dates else None
        if v or d:
            found = ("changelog", (v or "") + (f" ({d})" if v and d else d if d else ""))
            res["log_date"] = max(res.get("log_date") or "", d or "")
    elif name == "package.json":
        m = JSON_VERSION_RE.search(text)
        found = ("package", m.group(1)) if m else None
    elif name == "pyproject.toml":
        m = TOML_VERSION_RE.search(text)
        found = ("package", m.group(1)) if m else None
    elif name == "VERSION":
        v = text.strip().splitlines()[0].strip() if text.strip() else ""
        found = ("VERSION file", v) if re.match(r"v?\d+(\.\d+)+", v) else None
    else:
        m = CODE_VERSION_RE.search(text)
        found = ("code", m.group(1)) if m else None
    if found:
        res["infos"].append((rel, found[0], found[1]))


NAME_VERSION_RE = re.compile(r"^(.+?)\.(\d+(?:\.\d+)+)\.zip$", re.IGNORECASE)


def version_from_name(path):
    """Version written in the file name (« nginx-tools.1.1.20261002.093000.zip », « rlq_survey_report.18.0.1.90.0.zip »)."""
    m = NAME_VERSION_RE.match(os.path.basename(path))
    return m.group(2) if m else None


def short_version(v):
    """« 1.60.20261002.100000 » -> « 1.60 »: version WITHOUT the date, as it appears in the name of delivered archives
    (nginx-tools.1.1.zip). Other version form (Odoo module: 18.0.1.90.0): unchanged."""
    return ".".join(v.split(".")[:2]) if BARE_VERSION_RE.match(v or "") else v


def name_matches(name_version, version):
    """Does the file name announce the right version? Equal, or name version = beginning of the content's
    (« 1.60 » for « 1.60.20261002.100000 »); the old full form (with the date) is still accepted."""
    return name_version == version or version.startswith(name_version + ".")


def main_version(s):
    """Version that represents the archive. Ours: VERSION file of nginx-tools, run-all.sh of nginx-tools-tests.
    Others: manifest, then package, then VERSION, then log, then code (highest)."""
    if s.get("archive_version"):
        return s["archive_version"]
    if s.get("type") == "nginx-tools-tests" and s["programs"].get("run-all.sh"):
        return s["programs"]["run-all.sh"]
    for kind in ("manifest", "package", "VERSION file", "changelog", "code"):
        vs = [v.split(" (")[0] for _, g, v in s.get("infos", []) if g == kind and v.split(" (")[0]]
        if vs:
            return max(vs, key=generic_key)
    return None


def read_zip(path):
    res = {"name": os.path.normpath(path), "path": path, "programs": {}, "config_log": None, "config_files": {},
           "date": None, "error": None, "old_name": False, "infos": [], "crc": {}, "log_date": None,
           "archive_version": None}
    try:
        with zipfile.ZipFile(path) as z:
            infos = [i for i in z.infolist() if not i.is_dir() and "__pycache__" not in i.filename]
            res["type"], res["old_name"] = archive_type([i.filename for i in infos])
            for i in infos:
                when = datetime.datetime(*i.date_time)
                if res["date"] is None or when > res["date"]:
                    res["date"] = when
                rel = relative(i.filename)
                res["crc"][rel] = (i.CRC, i.file_size)
                if res["type"] not in OUR_TYPES and res["type"] not in ("autre", "unknown") and i.file_size <= MAX_READ_SIZE \
                        and should_read_generic(rel):
                    parse_generic(res, rel, z.read(i).decode("utf-8", "replace"))
                    continue
                if rel == VERSION_FILES.get(res["type"]) and i.file_size < 100:                   # archive version (1.3, 1.5)
                    v = z.read(i).decode("utf-8", "replace").strip()
                    res["archive_version"] = v if BARE_VERSION_RE.match(v) else None
                    continue
                if res["type"] == "nginx-tools-tests" and rel.startswith("nginx-odoo/"):
                    continue                                   # tested copy of the configuration: not a program
                if i.file_size > MAX_READ_SIZE:
                    continue
                if is_program(res["type"], rel) or res["type"] == "nginx-odoo-config":
                    content = z.read(i)
                    parse_text(res, rel, content.decode("utf-8", "replace"), content)
    except (OSError, zipfile.BadZipFile) as e:
        res["type"], res["error"] = "unknown", f"archive illisible : {e}"
    return res


def is_installation(folder):
    return os.path.isfile(os.path.join(folder, "web-monitor.py")) or os.path.isfile(os.path.join(folder, "nginx-hardening.sh"))


def read_installation(folder):
    """Programs deployed in a directory (e.g. /root/scripts): its *.sh, *.py, apps/*, nginx-tools-tests/run-all.sh,
    and the old tests/run-all.sh if it really is our suite (signature)."""
    res = {"name": folder, "path": folder, "type": "installation", "programs": {}, "config_log": None,
           "config_files": {}, "date": None, "error": None, "old_name": False}
    old = os.path.join(folder, "tests", "run-all.sh")
    suites = glob.glob(os.path.join(folder, "nginx-tools-tests", "run-all.sh"))
    if os.path.isfile(os.path.join(folder, "tests", SUITE_SIGNATURE)) and os.path.isfile(old):
        suites.append(old)
        res["old_name"] = True
    for path in sorted(glob.glob(os.path.join(folder, "*.sh")) + glob.glob(os.path.join(folder, "*.py"))
                         + glob.glob(os.path.join(folder, "apps", "*.*")) + suites):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read(MAX_READ_SIZE)
            when = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        except OSError:
            continue
        if res["date"] is None or when > res["date"]:
            res["date"] = when
        parse_text(res, os.path.relpath(path, folder), text, b"")
    v = ""
    try:
        with open(os.path.join(folder, SUITE_VERSION_FILE), encoding="utf-8") as f:
            v = f.read(100).strip()
    except OSError:
        pass
    res["archive_version"] = v if BARE_VERSION_RE.match(v) else None
    return res


def requested_sources(arguments):
    """Archives and installations to examine: given .zip files, or contents of given directories (current by default)."""
    zips, installations, absent = [], [], []
    for a in arguments or ["."]:
        a = os.path.expanduser(a)
        if os.path.isdir(a):
            zips += sorted(glob.glob(os.path.join(a, "*.zip")))
            if is_installation(a):
                installations.append(os.path.abspath(a))
        elif os.path.isfile(a):
            zips.append(a)
        else:
            absent.append(a)
    seen, unique = set(), []
    for z in zips:                                             # same file given twice: only once
        if os.path.realpath(z) not in seen:
            seen.add(os.path.realpath(z))
            unique.append(z)
    return unique, installations, absent


# ------------------------------------------------------------------------------------------------------------------
# Display
# ------------------------------------------------------------------------------------------------------------------
def fmt_date(d):
    return f"{d:%Y-%m-%d %H:%M}" if d else "—"


def source_key(s):
    """Recency order of an archive: highest version of its programs, date of the configuration log, most recent
    file. Two archives of the same type are told apart this way even if one was recompressed later."""
    dates = sorted((date_key(v) for v in s["programs"].values()), reverse=True)
    return (version_key(s["archive_version"]) if s.get("archive_version") else (), dates[:1], s["config_log"] or "",
            generic_key(main_version(s)), s.get("log_date") or "",
            s["date"] or datetime.datetime.min)


def print_source(s):
    size = ""
    if os.path.isfile(s["path"]):
        size = f", {os.path.getsize(s['path']) // 1024} Ko"
    print(f"{color('1', s['name'])} — {s['type']} — most recent file: {fmt_date(s['date'])}{size}")
    if s["error"]:
        print("  " + ATTN(s["error"]))
        return
    if s["type"] == "autre":
        print("  (« tests » archive of another program: ignored)")
        return
    name_v = version_from_name(s["path"]) if s["type"] != "installation" else None
    if s.get("archive_version"):
        label = "archive version"
        print(f"  {label:<32} {s['archive_version']}")   # archive version: MAJOR.MINOR only, no date
    if name_v and main_version(s) and not name_matches(name_v, main_version(s)):
        print("  " + ATTN(f"the file name says version {name_v}, the content {main_version(s)}"
                          f" (expected name: {s['type']}.{short_version(main_version(s))}.zip)"))
        s["inconsistent"] = True
    elif not name_v and s["type"] in OUR_TYPES and main_version(s):
        print(f"  (name without version: the archive would be {s['type']}.{short_version(main_version(s))}.zip)")
    elif not name_v and s["type"] == "nginx-tools":
        print("  (name without version, and without doc/nginx-tools.version: archive older than archive numbering)")
    if s["old_name"] and s["type"] != "installation":
        print("  " + ATTN("old name (tests/ folder): extracting it would overwrite the tests/ of other programs — use nginx-tools-tests.zip"))
    for rel in sorted(s["programs"]):
        print(f"  {rel:<32} {colored_version(s['programs'][rel])}")
    if any(is_today(v) for v in s["programs"].values()):
        print("  " + color("1;32", "green = version or file dated today") + f" ({today()[:4]}-{today()[4:6]}-{today()[6:]})")
    if s["type"] == "nginx-odoo-config":
        print(f"  {'nginx configuration (log)':<32} {s['config_log'] or 'no date in README.md'}"
              f" — {len(s['config_files'])} file(s)")
    seen = set()
    for rel, kind, v in sorted(s.get("infos", [])):
        if (kind, v) in seen and kind == "code":
            continue                                          # same version repeated in several modules: once
        seen.add((kind, v))
        print(f"  {rel:<32} {v}  ({kind})")
    if not s["programs"] and not s.get("infos") and s["type"] != "nginx-odoo-config":
        print("  (no declared version: no CHANGELOG, manifest or __version__; compared by file dates)")


def compare_archives(sources):
    """Several archives of the same type: the most recent, and for each other one, the older programs."""
    by_type = {}
    for s in sources:
        if not s["error"] and s["type"] not in ("unknown", "autre"):
            by_type.setdefault(s["type"], []).append(s)
    kept = {}
    for t, items_list in sorted(by_type.items()):
        items_list.sort(key=source_key, reverse=True)
        kept[t] = items_list[0]
        if len(items_list) < 2:
            continue
        print()
        print(f"COMPARISON — {len(items_list)} archives of type {t}")
        for s in items_list[1:]:
            older = [f"{r} {v} < {items_list[0]['programs'][r]}" for r, v in sorted(s["programs"].items())
                          if r in items_list[0]["programs"] and version_key(v) < version_key(items_list[0]["programs"][r])]
            if not older and source_key(s) == source_key(items_list[0]):
                print("  " + OK(f"{s['name']} : same versioned content as {items_list[0]['name']}"))
            else:
                detail = " ; ".join(older[:4]) + (f" … (+{len(older) - 4})" if len(older) > 4 else "")
                if not older and t == "nginx-odoo-config":
                    detail = f"log {s['config_log'] or '—'} < {items_list[0]['config_log'] or '—'}"
                elif not older and t not in OUR_TYPES:
                    va, vb = main_version(s), main_version(items_list[0])
                    detail = (f"version {va} < {vb}" if va and vb and va != vb
                              else f"most recent file {fmt_date(s['date'])} < {fmt_date(items_list[0]['date'])}")
                print("  " + ATTN(f"{s['name']} is older than {items_list[0]['name']}" + (f" : {detail}" if detail else "")))
    return kept


def compare_installation(kept, folder, nginx_dir):
    """Selected archives compared with the server: programs of FOLDER (versions), configuration of NGINX_DIR (content)."""
    print()
    print(f"COMPARISON WITH THE INSTALLATION — programs: {folder}; configuration: {nginx_dir}")
    n_attn = 0
    inst = read_installation(folder) if os.path.isdir(folder) else None
    if inst is not None and inst["old_name"]:
        print("  " + ATTN(f"old copy of the suite in {os.path.join(folder, 'tests')}"
                          " (before nginx-tools-tests/): to remove once nginx-tools-tests/ is deployed (this folder may also hold the tests of other"
                          " programs: remove only our files)"))
        n_attn += 1
    s = kept.get("nginx-tools")
    if s and inst is not None and s.get("archive_version"):
        if inst.get("archive_version") == s["archive_version"]:
            print("  " + OK(f"archive nginx-tools {s['archive_version']} deployed"))
        else:
            print("  " + ATTN(f"nginx-tools archive installed: {inst.get('archive_version') or 'unknown (before 1.3)'}, "
                              f"archive : {s['archive_version']}"))
            n_attn += 1
    for t in ("nginx-tools", "nginx-tools-tests"):
        s = kept.get(t)
        if not s:
            continue
        if inst is None:
            print("  " + ATTN(f"{folder} not found: programs not compared"))
            n_attn += 1
            break
        for rel, v in sorted(s["programs"].items()):
            target = rel if t == "nginx-tools" else "nginx-tools-tests/" + rel
            deployed = inst["programs"].get(target)
            if deployed is None and t == "nginx-tools-tests":
                deployed = inst["programs"].get("tests/" + rel)        # old folder, still alone in place
            if deployed is None:
                print("  " + ATTN(f"{target} : absent from the installation (archive: {v}) — to deploy"))
            elif version_key(deployed) < version_key(v):
                print("  " + ATTN(f"{target} : installed {deployed} < archive {v} — to deploy"))
            elif version_key(deployed) > version_key(v):
                print("  " + ATTN(f"{target} : installed {deployed} > archive {v} — outdated archive, do not send it"))
            else:
                print("  " + OK(f"{target} {colored_version(v)}"))
                continue
            n_attn += 1
    s = kept.get("nginx-odoo-config")
    if s:
        if not os.path.isdir(nginx_dir):
            print("  " + ATTN(f"{nginx_dir} not found: configuration not compared"))
            n_attn += 1
        else:
            identical, different, absent = 0, [], []
            with zipfile.ZipFile(s["path"]) as z:
                for i in z.infolist():
                    rel = relative(i.filename)
                    if i.is_dir() or not fnmatch.fnmatch(rel, "*.conf") or rel.startswith("fail2ban/"):
                        continue                               # fail2ban/: copied elsewhere by nginx-hardening.sh
                    target = os.path.join(nginx_dir, rel)
                    if not os.path.isfile(target):
                        absent.append(rel)
                    elif open(target, "rb").read() == z.read(i):
                        identical += 1
                    else:
                        different.append(rel)
            print("  " + OK(f"configuration: {identical} file(s) identical to the archive"))
            if different:
                n_attn += 1
                print("  " + ATTN(f"{len(different)} file(s) different from the archive: " + ", ".join(different[:6])
                                  + (" …" if len(different) > 6 else "")))
            if absent:
                print(f"         {len(absent)} absent from {nginx_dir} (normal for sites not used on this server): "
                      + ", ".join(absent[:6]) + (" …" if len(absent) > 6 else ""))
    return n_attn


def consistency(kept):
    """Tests archive and program archive (« X_tests » or « X-tests » <-> « X »; tested copy of the nginx configuration
    <-> nginx-odoo-config): common files must be identical (CRC), otherwise the tests do not cover this version of
    the program. Number of gaps."""
    pairs = [("nginx-tools-tests", "nginx-odoo-config", "nginx-odoo/")]
    for t in kept:
        for suffix in ("_tests", "-tests"):
            if t.endswith(suffix) and t[:-len(suffix)] in kept and t != "nginx-tools-tests":
                pairs.append((t, t[:-len(suffix)], ""))
    lines, gaps = [], 0
    for t_tests, t_prog, prefix_ in pairs:
        if t_tests in kept:
            kept[t_tests].pop("matches", None)
        if t_tests not in kept or t_prog not in kept:
            continue
        a, b = kept[t_tests], kept[t_prog]
        common = [r for r in a["crc"] if r.startswith(prefix_) and r[len(prefix_):] in b["crc"]]
        if not common:
            continue
        different = [r[len(prefix_):] for r in common if a["crc"][r] != b["crc"][r[len(prefix_):]]]
        absent = [r for r in b["crc"] if prefix_ and prefix_ + r not in a["crc"]]
        if different or absent:
            gaps += 1
            lines.append("  " + ATTN(f"{os.path.basename(a['path'])} ↔ {os.path.basename(b['path'])} : "
                                      + (f"{len(different)} common file(s) differ: " + ", ".join(different[:5])
                                         + (" …" if len(different) > 5 else "") if different else "")
                                      + (" ; " if different and absent else "")
                                      + (f"{len(absent)} absent from the tested copy: " + ", ".join(absent[:3]) if absent else "")
                                      + " — the tests do not cover exactly this version"))
        else:
            lines.append("  " + OK(f"{os.path.basename(a['path'])} ↔ {os.path.basename(b['path'])} : "
                                    f"{len(common)} common file(s), all identical"))
            if t_prog not in OUR_TYPES:          # tests archive without a version: it matches the program's
                a["matches"] = f"{t_prog} {main_version(b) or fmt_date(b['date'])}"
    if lines:
        print()
        print("CONSISTENCY OF THE TEST ARCHIVES WITH THEIR PROGRAM")
        for line in lines:
            print(line)
    return gaps


def run(args):
    zips, installations, absent = requested_sources(args.sources)
    print(f"Options: sources = {', '.join(args.sources) if args.sources else 'current directory'}"
          + (f" ; installation = {args.installed}, configuration = {args.nginx_dir}" if args.installed else ""))
    for a in absent:
        print(ATTN(f"{a} : not found"))
    if not zips and not installations:
        print("No archive (.zip) found — give a directory (e.g. ~/Downloads) or .zip files.")
        return 1
    sources = [read_zip(z) for z in zips] + [read_installation(d) for d in installations]
    for s in sources:
        print()
        print_source(s)
    kept = compare_archives([s for s in sources if s["type"] != "installation"])
    n_attn = sum(1 for s in sources if s["error"] or s.get("inconsistent")) + len(absent)
    n_attn += consistency(kept)
    if args.installed:
        n_attn += compare_installation(kept, args.installed, args.nginx_dir)
    print()
    if kept:
        print("ARCHIVES TO ATTACH TO THE DISCUSSION (the most recent of each type):")
        width = max(len(t) for t in kept) + 1
        for t in [t for t in OUR_TYPES if t in kept] + sorted(t for t in kept if t not in OUR_TYPES):
            s = kept[t]
            v = max(s["programs"].items(), key=lambda x: date_key(x[1])) if s["programs"] else None
            if v:
                v = (f"version {main_version(s)}, " if main_version(s) and main_version(s) != v[1] else "") \
                    + f"most recent: {v[0]} {v[1]}"
            elif t == "nginx-odoo-config":
                v = (f"version {main_version(s)}, " if main_version(s) else "") + f"most recent: {s['config_log'] or '—'}"
            else:
                v = (f"version {main_version(s)}, " if main_version(s) else "") + f"most recent file {fmt_date(s['date'])}"
                if s.get("matches") and not main_version(s):
                    v += f" ; common files identical to {s['matches']}"
            print(f"  {t:<{width}} {s['path']}  ({v})")
        missing = [t for t in ("nginx-tools", "nginx-tools-tests") if t not in kept]
        if missing and any(t in kept for t in OUR_TYPES):
            print("  manquant(s) : " + ", ".join(missing) + " (always attach nginx-tools.zip and nginx-tools-tests.zip)")
        if VIEWS["today"]:
            print("  " + color("1;32", "green = version or file dated today") + f" ({today()[:4]}-{today()[4:6]}-{today()[6:]})")
        if any(kept[t]["old_name"] for t in kept):
            print("  " + ATTN("an archive kept has the old name (tests/): regenerate it as nginx-tools-tests.zip"))
    return 1 if n_attn else 0


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
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)          # "| head": silent stop, like cat
    try:
        text = changelog_section(CHANGELOG_FILE, "zip-versions.py")
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
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="Versions of the programs and configuration held in the project archives (without extracting them); designates the most recent archive of each type, to attach to the discussion.")
    parser.add_argument("sources", nargs="*", metavar="ZIP_OR_DIR",
                        help="zip archives, or directories whose zips are examined (default: current directory)")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/zip-versions.conf, then the personal file .zip-versions.conf; options in UPPERCASE: INSTALLED, LANGUAGE, NGINX_DIR)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG",
                        help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--installed", nargs="?", const=DEFAULT_INSTALLATION, metavar="DIR",
                        help=f"Also compare with the installation: programs of DIR (default: {DEFAULT_INSTALLATION}), "
                             "configuration of --nginx-dir")
    parser.add_argument("--nginx-dir", default=DEFAULT_NGINX, metavar="DIR",
                        help=f"With --installed: deployed nginx configuration (default: {DEFAULT_NGINX})")
    parser.add_argument("--report-err", action="store_true",
                        help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--version", action="version", version=f"zip-versions.py version {__version__}")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version (--version prints it itself)
        print(f"zip-versions.py v{__version__}")
    defaults, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defaults, problems)
    if args.changelog:
        return show_changelog()
    return run(args)


def protected_main():
    """main() protected: Ctrl-C ends cleanly, without traceback (code 130)."""
    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrompu (Ctrl-C).", file=sys.stderr)
        return 130


def launch_with_report(function):
    """--report-err: paste-ready error report at the end of the run (apps/_rapport.py, if next to this file)."""
    arguments = sys.argv[1:]
    if "--report-err" in arguments and not {"-h", "--help", "--version", "--changelog"} & set(arguments):
        try:
            spec = importlib.util.spec_from_file_location("_rapport", os.path.join(SCRIPT_DIR, "apps", "_rapport.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"--report-err indisponible ({e}) — normal run.", file=sys.stderr)
            return function()
        return module.lancer(function, os.path.basename(__file__), __version__, SCRIPT_DIR)
    return function()


if __name__ == "__main__":
    try:
        sys.exit(launch_with_report(protected_main))
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
