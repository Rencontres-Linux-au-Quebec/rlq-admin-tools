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
# _odoo_addons.py - addons_path and server_wide_modules of an Odoo configuration (shared module, apps/), for nginx-hardening.sh step 17c.
#   * analysis: folders of addons_path, modules in them, modules installed in the databases (list given on standard input or in a file),
#     folders that hold no installed module (Odoo reads their manifests anyway: at the start, and in each worker for its static files);
#   * --trim: addons_path keeps only the folders that hold an installed module (and the folders of odoo itself, base and web);
#   * --preload DIR: DIR (folder of rlq_preload_statics) added to addons_path, rlq_preload_statics to server_wide_modules.
#   The configuration is written only with --write, after a copy FILE.bak-YYYYMMDD-HHMMSS. Output: KEY=VALUE lines, read by the Bash caller.
"""python3 _odoo_addons.py --conf FILE [--installed FILE] [--trim] [--preload DIR] [--write]"""
import argparse
import os
import re
import shutil
import sys
import time

__version__ = "1.0.20261118.192321"

PRELOAD = "rlq_preload_statics"
CORE_MODULES = ("base", "web")                      # a folder with one of them is the core of Odoo: always kept
DEFAULT_SWM = ("base", "web")                       # default server_wide_modules of Odoo (with « rpc » when the module exists: Odoo 18)
LINE_RE = r"^[ \t]*{key}[ \t]*=.*$"


def read_value(text, key):
    """Value of `key` in the [options] text (last line wins, like Odoo); None when absent."""
    values = re.findall(LINE_RE.format(key=re.escape(key)), text, re.M)
    return values[-1].split("=", 1)[1].strip() if values else None


def set_value(text, key, value):
    """Text with `key = value`: the existing line(s) replaced (the last one; the others removed), otherwise added after [options]."""
    pattern = re.compile(LINE_RE.format(key=re.escape(key)), re.M)
    found = list(pattern.finditer(text))
    if found:
        for m in reversed(found[:-1]):
            text = text[:m.start()] + text[m.end() + 1:]
        last = list(pattern.finditer(text))[-1]
        return text[:last.start()] + f"{key} = {value}" + text[last.end():]
    m = re.search(r"^\[options\][ \t]*$", text, re.M)
    if m:
        return text[:m.end()] + f"\n{key} = {value}" + text[m.end():]
    return f"[options]\n{key} = {value}\n" + text


def modules_of(folder):
    """Names of the modules directly in `folder` (sub-folders with a __manifest__.py)."""
    try:
        return sorted(n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n, "__manifest__.py")))
    except OSError:
        return []


def analyze(text, installed, preload_dir=None):
    """{"paths", "modules", "per_path": {path: [modules]}, "keep", "unused", "swm", "preload"} of a configuration text."""
    raw = read_value(text, "addons_path") or ""
    paths = [p.strip() for p in raw.split(",") if p.strip()]
    per_path = {p: modules_of(p) for p in paths}
    keep, unused = [], []
    for p in paths:
        mods = per_path[p]
        if not os.path.isabs(p) or not os.path.isdir(p) or set(mods) & set(installed) or set(mods) & set(CORE_MODULES) or PRELOAD in mods:
            keep.append(p)                                  # relative or missing folder: never touched; installed, core or ours: kept
        else:
            unused.append(p)
    swm = [m.strip() for m in (read_value(text, "server_wide_modules") or "").split(",") if m.strip()]
    if not swm:
        has_rpc = any("rpc" in mods for mods in per_path.values())
        swm = ["base", "rpc", "web"] if has_rpc else list(DEFAULT_SWM)
    preload = PRELOAD in swm and (preload_dir is None or os.path.realpath(preload_dir) in {os.path.realpath(p) for p in paths})
    return {"paths": paths, "modules": sum(len(m) for m in per_path.values()), "per_path": per_path, "keep": keep, "unused": unused,
            "swm": swm, "preload": preload,
            "installed_found": len(set(installed) & {m for mods in per_path.values() for m in mods}),
            "unused_modules": sum(len(per_path[p]) for p in unused)}


def new_text(text, result, trim, preload_dir):
    """Configuration text with addons_path trimmed (`trim`) and/or the preload added (`preload_dir`)."""
    paths = list(result["keep"] if trim else result["paths"])
    swm = list(result["swm"])
    if preload_dir:
        if os.path.realpath(preload_dir) not in {os.path.realpath(p) for p in paths}:
            paths.append(preload_dir)
        if PRELOAD not in swm:
            swm.append(PRELOAD)
        text = set_value(text, "server_wide_modules", ",".join(swm))
    if paths != result["paths"]:
        text = set_value(text, "addons_path", ",".join(paths))
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description="addons_path and server_wide_modules of an Odoo configuration (KEY=VALUE output)")
    ap.add_argument("--conf", required=True, help="Odoo configuration file")
    ap.add_argument("--installed", help="file with the names of the installed modules, one per line (- = standard input)")
    ap.add_argument("--preload", metavar="DIR", help="folder of rlq_preload_statics: added to addons_path, the module to server_wide_modules")
    ap.add_argument("--trim", action="store_true", help="addons_path: only the folders that hold an installed module")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--write", action="store_true", help="write the configuration (copy FILE.bak-YYYYMMDD-HHMMSS before)")
    a = ap.parse_args(argv)
    try:
        with open(a.conf, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"error={e}")
        return 2
    installed = []
    if a.installed:
        source = sys.stdin if a.installed == "-" else open(a.installed, encoding="utf-8")
        installed = [line.strip() for line in source if line.strip()]
    r = analyze(text, installed, a.preload)
    print(f"paths={len(r['paths'])}")
    print(f"modules={r['modules']}")
    print(f"installed={len(installed)}")
    print(f"installed_found={r['installed_found']}")
    print(f"keep={len(r['keep'])}")
    print(f"unused={len(r['unused'])}")
    print(f"unused_modules={r['unused_modules']}")
    print(f"swm={','.join(r['swm'])}")
    print(f"preload={1 if r['preload'] else 0}")
    if not (a.trim or a.preload):
        return 0
    if a.trim and installed and r["installed_found"] < len(set(installed)):
        missing = sorted(set(installed) - {m for mods in r["per_path"].values() for m in mods})
        print(f"missing={','.join(missing[:20])}")              # installed modules not found in addons_path: never trimmed blind
        return 3
    if a.trim and not installed:
        print("error=no installed module given: addons_path not trimmed")
        return 3
    text2 = new_text(text, r, a.trim, a.preload)
    if text2 == text:
        print("changed=0")
        return 0
    print("changed=1")
    if a.write:
        backup = f"{a.conf}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(a.conf, backup)
        st = os.stat(a.conf)
        with open(a.conf, "w", encoding="utf-8") as f:
            f.write(text2)
        try:
            os.chown(a.conf, st.st_uid, st.st_gid)
            os.chmod(a.conf, st.st_mode & 0o7777)
        except OSError:
            pass
        print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
