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
# odoo-docs.py — publishes the suite's documentation (docs/en, docs/fr) INTO Odoo, through the external API (XML-RPC, API key):
#   --target wiki     pages of the OCA module « document_page » (knowledge repository): a category tree, one page per document, per language.
#   --target website  website pages /docs/<lang>/<page> (module « website »), created and updated idempotently.
# Before writing anything in the wiki the program VALIDATES that document_page is installed and WORKS (module state, access rights, fields,
# then a real create / read / history / delete round trip on a temporary page). --check does only that validation.
#
import argparse
import importlib.util
import os
import re
import signal
import stat
import sys
import xmlrpc.client

__version__ = "1.4.20261020.211944"

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "CHANGELOG.md")
DOCS_DIR_DEFAULT = os.path.join(SCRIPT_DIR, "doc")
WIKI_MODULE = "document_page"
WIKI_MODEL = "document.page"
HISTORY_MODEL = "document.page.history"
TEST_PAGE_NAME = "odoo-docs validation (temporary, deleted at once)"
LANG_NAMES = {"en": "English", "fr": "Français"}
ROOT_DEFAULT = "nginx-tools"


def _start():
    """Common context (apps/_i18n.py: language, configuration, translated print / input, parser); module missing (script copied alone): English, no configuration."""
    try:
        spec = importlib.util.spec_from_file_location("_i18n", os.path.join(SCRIPT_DIR, "apps", "_i18n.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.demarrer(SCRIPT_DIR, SCRIPT_NAME, "ODOO_DOCS_LANG")
    except Exception:
        return None


I18N = _start()
if I18N:
    print, input = I18N.print, I18N.input          # noqa: A001 — every displayed text goes through the translator (no effect when the display language is the source language)


def eprint(*args):
    print(*args, file=sys.stderr, flush=True)


# Configuration file options (/etc/default/odoo-docs.conf, then ~/.odoo-docs.conf): KEY -> (command-line option, type).
# API_KEY is NOT a command-line option: read apart (read_api_key). LANGUAGE: en, fr or auto.
SCHEMA_CONFIG = {"DB": ("db", str), "DOCS_DIR": ("docs_dir", str), "LOGIN": ("login", str), "ROOT": ("root", str), "TARGET": ("target", str), "URL": ("api_url", str)}


class DocsError(Exception):
    """Error shown as is (message already written for the user), without traceback."""


def read_api_key(read_files):
    """API key: ODOO_API_KEY variable, else API_KEY of the last configuration file read that defines it; (key, file readable by others or None)."""
    key = os.environ.get("ODOO_API_KEY", "").strip()
    open_file = None
    for path in read_files:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"\s*API_KEY\s*=\s*(.*?)\s*$", line)
                    if m and m.group(1).strip("\"'"):
                        key = key or m.group(1).strip("\"'")
                        if os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                            open_file = path
        except OSError:
            continue
    return key, open_file


class Odoo:
    """XML-RPC access to Odoo: API key authentication, execute_kw calls."""

    def __init__(self, url, db, login, key):
        self.url, self.db, self.login, self.key = url.rstrip("/"), db, login, key
        self.uid = None
        self._object = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/object", allow_none=True)

    def connect(self):
        try:
            common = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/common", allow_none=True)
            self.uid = common.authenticate(self.db, self.login, self.key, {})
        except (OSError, xmlrpc.client.Error) as e:
            raise DocsError(f"cannot connect to Odoo ({self.url}) : {e}")
        if not self.uid:
            raise DocsError(f"authentication refused (database {self.db}, account {self.login}): check the API key and the database name")
        return self.uid

    def call(self, model, method, args, kwargs=None):
        try:
            return self._object.execute_kw(self.db, self.uid, self.key, model, method, args, kwargs or {})
        except xmlrpc.client.Fault as e:
            raise DocsError(f"Odoo refused {model}.{method} : {str(e.faultString).strip().splitlines()[-1][:300]}")
        except (OSError, xmlrpc.client.Error) as e:
            raise DocsError(f"call to Odoo failed ({model}.{method}) : {e}")


# ---------------------------------------------------------------------------------------------------------------- validation
def check_module(odoo, module, label):
    """Module installed? Returns its installed version; raises DocsError with the remedy otherwise."""
    found = odoo.call("ir.module.module", "search_read", [[("name", "=", module)]], {"fields": ["state", "installed_version"], "limit": 1})
    if not found:
        raise DocsError(f"the module « {module} » ({label}) is not found in this database: update the apps list, then install it")
    if found[0]["state"] != "installed":
        raise DocsError(f"the module « {module} » ({label}) is not installed (state: {found[0]['state']}): install it from Apps")
    return found[0].get("installed_version") or ""


def check_wiki(odoo, write_test=True):
    """Validates document_page: installed, models and fields present, rights, then (write_test) a real round trip. Returns the report lines.
    The temporary page is deleted even when the round trip fails."""
    lines = []
    version = check_module(odoo, WIKI_MODULE, "OCA knowledge / document_page")
    lines.append(f"module {WIKI_MODULE} installed (version {version})")
    for model in (WIKI_MODEL, HISTORY_MODEL):
        if not odoo.call("ir.model", "search", [[("model", "=", model)]], {"limit": 1}):
            raise DocsError(f"the model « {model} » does not exist: the module {WIKI_MODULE} is incomplete or of an incompatible version")
    fields = odoo.call(WIKI_MODEL, "fields_get", [], {"attributes": ["type", "readonly", "required"]})
    missing = [n for n in ("name", "type", "parent_id", "content") if n not in fields]
    if missing:
        raise DocsError(f"{WIKI_MODEL} lacks the field(s) {', '.join(missing)}: module version incompatible with odoo-docs.py")
    if fields["content"].get("readonly"):
        raise DocsError(f"the content field of {WIKI_MODEL} is read-only: module version incompatible with odoo-docs.py")
    lines.append("models and fields present (name, type, parent_id, content)")
    for right in ("create", "write", "unlink"):
        if not odoo.call(WIKI_MODEL, "check_access_rights", [right], {"raise_exception": False}):
            raise DocsError(f"the account {odoo.login} does not have the « {right} » right on {WIKI_MODEL}: add the « Document Page / Editor » group or make it administrator")
    lines.append(f"create, write and delete rights for {odoo.login}")
    if not write_test:
        lines.append("write test not done (--dry-run)")
        return lines
    category = page = None
    try:
        category = odoo.call(WIKI_MODEL, "create", [{"name": TEST_PAGE_NAME + " [category]", "type": "category"}])
        page = odoo.call(WIKI_MODEL, "create", [{"name": TEST_PAGE_NAME, "type": "content", "parent_id": category, "content": "<p>test 1</p>"}])
        odoo.call(WIKI_MODEL, "write", [[page], {"content": "<p>test 2</p>"}])
        back = odoo.call(WIKI_MODEL, "read", [[page], ["content", "name"]])[0]
        if "test 2" not in str(back.get("content") or ""):
            raise DocsError("write test: the content read back does not match what was written (the module does not work as expected)")
        history = odoo.call(HISTORY_MODEL, "search_count", [[("page_id", "=", page)]])
        lines.append(f"write test succeeded: creation, edit, read back, history ({history} version(s))")
    finally:
        for model_id in (page, category):
            if model_id:
                try:
                    odoo.call(WIKI_MODEL, "unlink", [[model_id]])
                except DocsError as e:
                    eprint(f"WARNING: test page {model_id} not deleted ({e}): delete it by hand in the wiki.")
    return lines


def check_website(odoo):
    version = check_module(odoo, "website", "site web")
    lines = [f"module website installed (version {version})"]
    for model in ("website.page", "ir.ui.view"):
        if not odoo.call(model, "check_access_rights", ["create"], {"raise_exception": False}):
            raise DocsError(f"the account {odoo.login} is not allowed to create {model}: use a website administrator account")
    lines.append(f"right to create pages and views for {odoo.login}")
    return lines


# ---------------------------------------------------------------------------------------------------------------- documents
def load_builder(docs_dir):
    """doc/build_docs.py (Markdown -> HTML, real --help insertion)."""
    path = os.path.join(docs_dir, "build_docs.py")
    if not os.path.isfile(path):
        raise DocsError(f"documentation builder not found: {path}")
    spec = importlib.util.spec_from_file_location("build_docs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_pages(builder, langs):
    """{lang: [page]} with the expanded Markdown source."""
    res = {}
    for lang in langs:
        res[lang] = builder.pages(lang)
        for page in res[lang]:
            page["expanded"] = builder.expand(page, lang)
    return res


def publish_wiki(odoo, builder, pages, root, dry_run):
    lines = []

    def find_or_create(vals, domain):
        found = odoo.call(WIKI_MODEL, "search", [domain], {"limit": 1})
        if found:
            return found[0], False
        if dry_run:
            return 0, True
        return odoo.call(WIKI_MODEL, "create", [vals]), True

    root_id, created = find_or_create({"name": root, "type": "category"}, [("name", "=", root), ("type", "=", "category"), ("parent_id", "=", False)])
    lines.append(("created" if created else "present") + f": category « {root} »")
    for lang, plist in pages.items():
        cat_id, created = find_or_create({"name": LANG_NAMES.get(lang, lang), "type": "category", "parent_id": root_id},
                                         [("name", "=", LANG_NAMES.get(lang, lang)), ("type", "=", "category"), ("parent_id", "=", root_id)])
        lines.append(("created" if created else "present") + f": category « {root} / {LANG_NAMES.get(lang, lang)} »")
        for sequence, page in enumerate(plist, 1):
            body = builder.to_html(page["expanded"])
            body = re.sub(r"^\s*<h1>.*?</h1>\s*", "", body, count=1, flags=re.S)      # the wiki shows the page name as the title
            domain = [("name", "=", page["title"]), ("type", "=", "content"), ("parent_id", "=", cat_id)]
            existing = odoo.call(WIKI_MODEL, "search", [domain], {"limit": 1}) if cat_id else []
            if existing:
                current = odoo.call(WIKI_MODEL, "read", [existing, ["content"]])[0].get("content") or ""
                if current.strip() == body.strip():
                    lines.append(f"unchanged: {lang} / {page['title']}")
                    continue
                if not dry_run:
                    odoo.call(WIKI_MODEL, "write", [existing, {"content": body, "draft_summary": f"odoo-docs.py {__version__}"}])
                lines.append(f"updated: {lang} / {page['title']}")
            else:
                if not dry_run:
                    odoo.call(WIKI_MODEL, "create", [{"name": page["title"], "type": "content", "parent_id": cat_id, "content": body, "draft_summary": f"odoo-docs.py {__version__}", "sequence": sequence}])
                lines.append(f"created: {lang} / {page['title']}")
    return lines


def publish_website(odoo, builder, pages, dry_run):
    lines = []
    module = "odoo_docs"
    for lang, plist in pages.items():
        for page in plist:
            slug = page["slug"]
            key = f"{module}.{lang}_{slug.replace('-', '_')}"
            body = builder.to_html(page["expanded"])
            arch = (f'<t t-name="{key}"><t t-call="website.layout"><div id="wrap" class="oe_structure"><section class="container py-4"><div class="row">'
                    f'<div class="col-lg-3">{builder.nav(lang, slug, plist)}</div><div class="col-lg-9">{body}</div></div></section></div></t></t>')
            url = f"/docs/{lang}/{slug}"
            existing = odoo.call("website.page", "search_read", [[("url", "=", url)]], {"fields": ["view_id"], "limit": 1})
            if existing:
                view_id = existing[0]["view_id"][0]
                if not dry_run:
                    odoo.call("ir.ui.view", "write", [[view_id], {"arch": arch}])
                lines.append(f"updated: {url}")
            else:
                if not dry_run:
                    view_id = odoo.call("ir.ui.view", "create", [{"name": f"{page['title']} ({lang})", "type": "qweb", "key": key, "arch": arch}])
                    odoo.call("website.page", "create", [{"url": url, "view_id": view_id, "is_published": True, "website_indexed": True}])
                lines.append(f"created: {url}")
    return lines


# ---------------------------------------------------------------------------------------------------------------- command line
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
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)          # « | head »: silent stop, like cat
    try:
        text = changelog_section(CHANGELOG_FILE, "odoo-docs.py")
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
    """Help options in ALPHABETICAL order (long name, without dashes)."""
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


def run(args, parser):
    target = (args.target or "").lower()
    if target and target not in ("wiki", "website"):
        parser.error("--target must be wiki or website")
    if not target and not args.check:
        parser.error("choose where to write the documentation: --target wiki (document_page module) or --target website (website pages), or --check")
    read_files = I18N.fichiers if I18N else []
    key, open_file = read_api_key(read_files)
    if open_file:
        eprint(f"WARNING: {open_file} contains the API key and is readable by other accounts: chmod 600 {open_file}")
    if not (args.api_url and args.db and args.login and key):
        missing = [n for n, v in (("URL", args.api_url), ("DB", args.db), ("LOGIN", args.login), ("API_KEY (or the ODOO_API_KEY variable)", key)) if not v]
        eprint("ERROR: missing settings: " + ", ".join(missing) + " — write them in /etc/default/odoo-docs.conf (see doc/en/odoo-docs.conf.example).")
        return 2
    try:
        odoo = Odoo(args.api_url, args.db, args.login, key)
        odoo.connect()
        print(f"Connected to {args.api_url} (database {args.db}, account {args.login}).")
        checks = []
        if target in ("wiki", "") :
            checks.append(("wiki (document_page)", lambda: check_wiki(odoo, write_test=not args.dry_run)))
        if target == "website" or (args.check and not target):
            checks.append(("site web", lambda: check_website(odoo)))
        for name, fn in checks:
            print(f"Validation — {name} :")
            for line in fn():
                print(f"  ✔ {line}")
        if args.check:
            return 0
        docs_dir = args.docs_dir or DOCS_DIR_DEFAULT
        builder = load_builder(docs_dir)
        langs = tuple(builder.LANGS)
        pages = load_pages(builder, langs)
        print(f"Publishing {sum(len(v) for v in pages.values())} page(s) ({', '.join(langs)}) — target: {target}" + (" [simulation]" if args.dry_run else "") + " :")
        lines = publish_wiki(odoo, builder, pages, args.root or ROOT_DEFAULT, args.dry_run) if target == "wiki" else publish_website(odoo, builder, pages, args.dry_run)
        for line in lines:
            print("  " + line)
        return 0
    except DocsError as e:
        eprint(f"ERROR: {e}")
        return 1


def main():
    parser = (I18N.parser if I18N else LocalizedArgumentParser)(
        description="Publishes the suite's documentation (doc/en, doc/fr) into Odoo: wiki of the document_page module (OCA) or website pages.")
    parser.add_argument("--api-url", default=None, metavar="URL", help="Odoo address (e.g. https://erp.example.org); URL key of the configuration file")
    parser.add_argument("--changelog", action="store_true", help="Show the change log")
    parser.add_argument("--check", action="store_true",
                        help="Validate only: connection, module installed and WORKING (real test: create, read back and delete a temporary page), publishes nothing")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="Configuration file to read ALONE (otherwise: /etc/default/odoo-docs.conf, then the personal file .odoo-docs.conf; UPPERCASE options: API_KEY, DB, DOCS_DIR, LANGUAGE, LOGIN, ROOT, TARGET, URL)")
    parser.add_argument("--db", default=None, metavar="NAME", help="Odoo database")
    parser.add_argument("--docs-dir", default=None, metavar="DIR", help=f"Folder of the documentation sources (default: {DOCS_DIR_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show what would be created or updated, writing nothing (no write test)")
    parser.add_argument("--lang", choices=I18N.disponibles if I18N else ["fr"], metavar="LANG", help="Display language: en or fr (default: from LC_ALL / LC_MESSAGES / LANG)")
    parser.add_argument("--login", default=None, metavar="USER", help="Odoo account owning the API key")
    parser.add_argument("--report-err", action="store_true", help="Print at the end an error report to copy and paste (program, version, server, failures, warnings)")
    parser.add_argument("--root", default=None, metavar="NAME", help=f"With --target wiki: root category of the wiki (default: {ROOT_DEFAULT})")
    parser.add_argument("--target", default=None, metavar="wiki|website",
                        help="Where to write: wiki (pages of the document_page module, OCA knowledge) or website (website pages, /docs/<lang>/<page>)")
    parser.add_argument("--version", action="version", version=f"odoo-docs.py version {__version__}")
    if "--version" not in sys.argv[1:]:       # first line of EVERY run, even --help: name and version
        print(f"odoo-docs.py v{__version__}")
    defaults, problems = I18N.defauts(parser, SCHEMA_CONFIG) if I18N else ({}, [])
    args = parser.parse_args()
    if args.config and not os.path.isfile(args.config):
        parser.error(f"configuration file not found: {args.config}")
    if I18N:
        I18N.afficher_configuration(defaults, problems)
    if args.changelog:
        return show_changelog()
    return run(args, parser)


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
