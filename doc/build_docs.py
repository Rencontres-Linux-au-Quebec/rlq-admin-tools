#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# build_docs.py - builds the bilingual (en/fr) documentation of nginx-tools.
#
"""Documentation builder.

Sources: doc/<lang>/NN-name.md. The placeholder {{HELP}} is replaced by the REAL `--help` output of the program of the same name (in that language), so the option lists
never go out of date. Outputs:
  * doc/build/<lang>/*.md              — complete Markdown (GitHub, wiki)
  * <out>/rlq_tools_docs/               — an Odoo 18 module (depends on `website`) that publishes the pages at /doc/<lang>/<slug>

Usage:  build_docs.py [--out DIR] [--check]      (--check: build to a temporary folder, validate the XML, change nothing)"""
import argparse
import html
import os
import re
import subprocess
import sys
import tempfile
import xml.dom.minidom

import markdown

__version__ = "1.7.20261022.231529"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANGS = ("en", "fr")
TITLES = {"en": "nginx-tools documentation", "fr": "Documentation de nginx-tools"}
NOISE = re.compile(r"^(Configuration (read|lue)\b|\s+(Options|Options ):)")
MODULE = "rlq_tools_docs"
# Personal data still present in some program help texts: masked in the published pages until the sources themselves are cleaned (see the GitHub plan).
SCRUB = (("etienne.berube.ing@exemple.org", "admin@example.org"), (" /home/utilisateur/git/erplibre/config.conf", ""))


def program_for(slug):
    for ext in (".py", ".sh"):
        if os.path.isfile(os.path.join(ROOT, slug + ext)):
            return slug + ext
    return None


def help_text(program, lang):
    env = dict(os.environ, NGINX_TOOLS_LANG=lang, NGINX_TOOLS_CONFIG_CREER="0", NGINX_TOOLS_AVIS_ROOT="0", COLUMNS="100", NO_COLOR="1")
    cmd = (["python3"] if program.endswith(".py") else ["bash"]) + [os.path.join(ROOT, program), "--help"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60, stdin=subprocess.DEVNULL)
    lines = (r.stdout or r.stderr).splitlines()
    lines = [l.rstrip() for l in lines[1:] if not NOISE.match(l)]            # the first line (NAME vVERSION) changes at each release: omitted
    texte = "\n".join(lines).strip("\n")
    for avant, apres in SCRUB:
        texte = texte.replace(avant, apres)
    return texte


def pages(lang):
    folder = os.path.join(HERE, lang)
    res = []
    for name in sorted(os.listdir(folder)):
        m = re.fullmatch(r"(\d\d)-(.+)\.md", name)
        if m:
            text = open(os.path.join(folder, name), encoding="utf-8").read()
            title = re.match(r"# (.+)", text).group(1).strip()
            res.append({"order": m.group(1), "slug": m.group(2), "title": title, "source": text})
    return res


def expand(page, lang):
    program = program_for(page["slug"])
    if "{{HELP}}" in page["source"]:
        if not program:
            raise SystemExit(f"{lang}/{page['order']}-{page['slug']}.md: {{{{HELP}}}} but no program named {page['slug']}")
        page["source"] = page["source"].replace("{{HELP}}", "\n```text\n" + help_text(program, lang) + "\n```\n")
    return page["source"]


def to_html(md_text):
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"], output_format="xhtml")
    body = body.replace("<table>", '<table class="table table-sm table-bordered">')
    return body.replace("&nbsp;", "&#160;")


def nav(lang, current, all_pages):
    other = "fr" if lang == "en" else "en"
    items = "".join(f'<a class="list-group-item list-group-item-action{" active" if p["slug"] == current else ""}" href="/docs/{lang}/{p["slug"]}">{html.escape(p["title"])}</a>'
                    for p in all_pages)
    switch = f'<p><a href="/docs/{other}/{current}">{"Français" if other == "fr" else "English"}</a></p>'
    return f'<nav class="list-group mb-3">{items}</nav>{switch}'


def xml_for(lang, plist):
    out = []
    for p in plist:
        slug = p["slug"]
        view_id = f"{lang}_{slug.replace('-', '_')}"
        body = to_html(p["expanded"])
        arch = (f'<t t-name="{MODULE}.{view_id}"><t t-call="website.layout"><t t-set="pageName" t-value="\'{view_id}\'"/>'
                f'<div id="wrap" class="oe_structure"><section class="container py-4"><div class="row">'
                f'<div class="col-lg-3">{nav(lang, slug, plist)}</div><div class="col-lg-9">{body}</div></div></section></div></t></t>')
        out.append(f'  <record id="view_{view_id}" model="ir.ui.view">\n    <field name="name">{html.escape(p["title"])} ({lang})</field>\n'
                   f'    <field name="type">qweb</field>\n    <field name="key">{MODULE}.{view_id}</field>\n    <field name="arch" type="xml">{arch}</field>\n  </record>\n'
                   f'  <record id="page_{view_id}" model="website.page">\n    <field name="url">/docs/{lang}/{slug}</field>\n    <field name="is_published" eval="True"/>\n'
                   f'    <field name="website_indexed" eval="True"/>\n    <field name="view_id" ref="view_{view_id}"/>\n  </record>\n')
    first = plist[0]["slug"]
    # /doc/<lang> redirects to the first page
    out.append(f'  <record id="redirect_{lang}" model="website.rewrite">\n    <field name="name">docs {lang}</field>\n    <field name="url_from">/docs/{lang}</field>\n'
               f'    <field name="url_to">/docs/{lang}/{first}</field>\n    <field name="redirect_type">301</field>\n  </record>\n')
    return "".join(out)


def build(out_dir):
    all_md = {}
    xml_parts = []
    for lang in LANGS:
        plist = pages(lang)
        for p in plist:
            p["expanded"] = expand(p, lang)
        all_md[lang] = plist
        os.makedirs(os.path.join(out_dir, "build", lang), exist_ok=True)
        for p in plist:
            with open(os.path.join(out_dir, "build", lang, f"{p['order']}-{p['slug']}.md"), "w", encoding="utf-8") as f:
                f.write(p["expanded"])
        xml_parts.append(xml_for(lang, plist))
    en, fr = ({p["slug"] for p in all_md[l]} for l in LANGS)
    if en != fr:
        raise SystemExit(f"pages differ between languages: only en {sorted(en - fr)}, only fr {sorted(fr - en)}")
    data = '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n' + "".join(xml_parts) + "</odoo>\n"
    xml.dom.minidom.parseString(data.encode("utf-8"))                       # raises if the XML is not well-formed
    mod = os.path.join(out_dir, MODULE)
    os.makedirs(os.path.join(mod, "data"), exist_ok=True)
    with open(os.path.join(mod, "data", "docs_pages.xml"), "w", encoding="utf-8") as f:
        f.write(data)
    with open(os.path.join(mod, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
    manifest = {
        "name": "nginx-tools documentation (website pages)", "version": "18.0.1.7.0", "category": "Website", "license": "AGPL-3",
        "summary": "Bilingual (en/fr) administrator documentation of nginx-tools, published as website pages /docs/en and /docs/fr.",
        "author": "Services-Conseils Linux Inc., Rencontres Linux au Québec contributors", "depends": ["website"], "data": ["data/docs_pages.xml"], "installable": True, "application": False,
    }
    with open(os.path.join(mod, "__manifest__.py"), "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n# GENERATED by doc/build_docs.py — edit doc/<lang>/*.md and rebuild; do not edit by hand.\n" + repr(manifest).replace("', '", "',\n    '") + "\n")
    return sum(len(v) for v in all_md.values())


def main(argv):
    ap = argparse.ArgumentParser(description="Builds the bilingual documentation (Markdown + Odoo website module).")
    ap.add_argument("--check", action="store_true", help="build into a temporary folder and validate, keep nothing")
    ap.add_argument("--out", default=os.path.join(HERE, "out"), help="output folder (default: doc/out)")
    ap.add_argument("--version", action="version", version=f"build_docs.py {__version__}")
    a = ap.parse_args(argv[1:])
    if a.check:
        with tempfile.TemporaryDirectory() as d:
            print(f"OK: {build(d)} pages validated")
        return 0
    print(f"{build(a.out)} pages written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
