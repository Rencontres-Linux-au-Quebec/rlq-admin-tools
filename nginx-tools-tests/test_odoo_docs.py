# -*- coding: utf-8 -*-
"""odoo-docs.py 1.0: publishing the documentation into the OCA document_page wiki or website pages — against a FAKE Odoo XML-RPC server."""
import os
import subprocess
import threading
import unittest
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

from helpers import EnvTest, script_path

import importlib.util as _iu
MARKDOWN = _iu.find_spec("markdown") is not None      # run-all 1.188 : docs/build_docs.py importe markdown (paquet python3-markdown)

ENVIRONNEMENT = "commun"


class Handler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")


def matches(rec, domain):
    for field, _, value in domain:
        if (rec.get(field) or False) != value:
            return False
    return True


class FakeOdoo:
    """In-memory Odoo: ir.module.module, ir.model, document.page(+history), website.page, ir.ui.view."""

    def __init__(self, wiki="installed", website="installed", broken_content=False, rights=True):
        self.modules = {"document_page": {"state": wiki, "installed_version": "18.0.1.0.0"}, "website": {"state": website, "installed_version": "18.0.1.0"}}
        self.models = {"document.page", "document.page.history", "website.page", "ir.ui.view"}
        if wiki == "absent":
            del self.modules["document_page"]
            self.models -= {"document.page", "document.page.history"}
        self.broken_content, self.rights = broken_content, rights
        self.data = {m: {} for m in ("document.page", "document.page.history", "website.page", "ir.ui.view")}
        self.next_id = 100
        self.unlinked = []
        self.srv = SimpleXMLRPCServer(("127.0.0.1", 0), requestHandler=Handler, allow_none=True, logRequests=False)
        self.srv.register_function(lambda db, login, key, ctx: 7 if (db, login, key) == ("rlq", "docs", "bonne") else False, "authenticate")
        self.srv.register_function(self.execute_kw, "execute_kw")
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def execute_kw(self, db, uid, key, model, method, args, kwargs):
        if model == "ir.module.module":
            return [dict(m, name=n) for n, m in self.modules.items() if n == args[0][0][2]]
        if model == "ir.model":
            return [1] if args[0][0][2] in self.models else []
        if method == "check_access_rights":
            return self.rights
        store = self.data[model]
        if method == "fields_get":
            return {"name": {}, "type": {}, "parent_id": {}, "content": {"readonly": self.broken_content}}
        if method == "search":
            return [i for i, r in store.items() if matches(r, args[0])][:kwargs.get("limit", 99)]
        if method == "search_read":
            return [dict(r, id=i, **({"view_id": [r["view_id"], "view"]} if r.get("view_id") else {}))      # many2one as [id, name], like the real Odoo
                    for i, r in store.items() if matches(r, args[0])][:kwargs.get("limit", 99)]
        if method == "search_count":
            return len([r for r in store.values() if r.get("page_id") == args[0][0][2]])
        if method == "create":
            self.next_id += 1
            rec = dict(args[0])
            store[self.next_id] = rec
            if model == "document.page" and rec.get("type") == "content":
                self.data["document.page.history"][self.next_id + 5000] = {"page_id": self.next_id}
            if model == "website.page":
                pass
            if model == "ir.ui.view":
                pass
            return self.next_id
        if method == "write":
            for i in args[0]:
                store[i].update(args[1])
                if model == "document.page":
                    self.data["document.page.history"][i + 9000 + len(store)] = {"page_id": i}
            return True
        if method == "read":
            return [dict({f: store[i].get(f) for f in args[1]}, id=i) for i in args[0]]
        if method == "unlink":
            for i in args[0]:
                self.unlinked.append(store.pop(i)["name"])
            return True
        raise Exception(f"unexpected {model}.{method}")


class TestOdooDocs(EnvTest):
    def setUp(self):
        super().setUp()
        self.etc, self.home = os.path.join(self.d, "etc"), os.path.join(self.d, "home")
        os.makedirs(self.etc)
        os.makedirs(self.home)
        self.fake = None

    def tearDown(self):
        if self.fake:
            self.fake.stop()
        super().tearDown()

    def start(self, **kw):
        self.fake = FakeOdoo(**kw)
        path = os.path.join(self.etc, "odoo-docs.conf")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"URL={self.fake.url}\nDB=rlq\nLOGIN=docs\nAPI_KEY=bonne\n")
        os.chmod(path, 0o600)

    def run_prog(self, *args):
        env = dict(os.environ, NGINX_TOOLS_ETC_DEFAULT=self.etc, HOME=self.home, NGINX_TOOLS_CONFIG_CREER="0", NGINX_TOOLS_AVIS_ROOT="0")
        env.pop("ODOO_API_KEY", None)
        return subprocess.run(["python3", script_path("odoo-docs.py"), "--lang", "fr", *args], capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)

    def wiki_pages(self):
        return self.fake.data["document.page"]

    def test_target_is_required(self):
        self.start()
        r = self.run_prog()
        self.assertEqual(r.returncode, 2)
        self.assertIn("--target wiki", r.stderr)

    def test_check_validates_and_leaves_nothing(self):
        self.start()
        r = self.run_prog("--check", "--target", "wiki")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("module document_page installé", r.stdout)
        self.assertIn("essai d'écriture réussi", r.stdout)
        self.assertEqual(self.wiki_pages(), {})                       # temporary page and category deleted
        self.assertEqual(len(self.fake.unlinked), 2)

    def test_module_not_installed_refuses_before_writing(self):
        self.start(wiki="uninstalled")
        r = self.run_prog("--target", "wiki")
        self.assertEqual(r.returncode, 1)
        self.assertIn("n'est pas installé", r.stderr)
        self.assertEqual(self.wiki_pages(), {})

    def test_module_missing(self):
        self.start(wiki="absent")
        r = self.run_prog("--target", "wiki")
        self.assertEqual(r.returncode, 1)
        self.assertIn("introuvable", r.stderr)

    def test_broken_module_detected_by_fields(self):
        self.start(broken_content=True)
        r = self.run_prog("--target", "wiki")
        self.assertEqual(r.returncode, 1)
        self.assertIn("lecture seule", r.stderr)
        self.assertEqual(self.wiki_pages(), {})

    def test_missing_rights(self):
        self.start(rights=False)
        r = self.run_prog("--target", "wiki")
        self.assertEqual(r.returncode, 1)
        self.assertIn("droit", r.stderr)

    def pages_attendues(self):
        """Number of pages published: NN-name.md files of docs/en and docs/fr next to the program (a server may hold one page more or less)."""
        import re as _re
        dossier = os.path.join(os.path.dirname(script_path("odoo-docs.py")), "docs")
        return sum(1 for lang in ("en", "fr") for f in os.listdir(os.path.join(dossier, lang)) if _re.fullmatch(r"\d\d-.+\.md", f))

    @unittest.skipUnless(MARKDOWN, "module Python « markdown » absent (apt install python3-markdown)")
    def test_wiki_publication_is_idempotent(self):
        self.start()
        r = self.run_prog("--target", "wiki")
        self.assertEqual(r.returncode, 0, r.stderr)
        pages = self.wiki_pages()
        contents = [p for p in pages.values() if p["type"] == "content"]
        cats = [p["name"] for p in pages.values() if p["type"] == "category"]
        self.assertEqual(sorted(cats), ["English", "Français", "nginx-tools"])
        self.assertEqual(len(contents), self.pages_attendues())          # every page of docs/en and docs/fr (counted, never a fixed number)
        self.assertFalse(any(p["content"].lstrip().startswith("<h1>") for p in contents))
        r2 = self.run_prog("--target", "wiki")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(len(self.wiki_pages()), len(pages))
        self.assertNotIn("créée : ", r2.stdout.split("Publication")[1])
        self.assertIn("inchangée", r2.stdout)

    @unittest.skipUnless(MARKDOWN, "module Python « markdown » absent (apt install python3-markdown)")
    def test_dry_run_writes_nothing(self):
        self.start()
        r = self.run_prog("--target", "wiki", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.wiki_pages(), {})
        self.assertIn("[simulation]", r.stdout)

    @unittest.skipUnless(MARKDOWN, "module Python « markdown » absent (apt install python3-markdown)")
    def test_website_target(self):
        self.start()
        r = self.run_prog("--target", "website")
        self.assertEqual(r.returncode, 0, r.stderr)
        urls = sorted(p["url"] for p in self.fake.data["website.page"].values())
        self.assertEqual(len(urls), self.pages_attendues())
        self.assertTrue(all(u.startswith(("/docs/en/", "/docs/fr/")) for u in urls))
        views = len(self.fake.data["ir.ui.view"])
        r2 = self.run_prog("--target", "website")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(len(self.fake.data["ir.ui.view"]), views)    # updated, not duplicated

    def test_website_module_missing(self):
        self.start(website="uninstalled")
        r = self.run_prog("--target", "website")
        self.assertEqual(r.returncode, 1)
        self.assertIn("website", r.stderr)


if __name__ == "__main__":
    unittest.main()
