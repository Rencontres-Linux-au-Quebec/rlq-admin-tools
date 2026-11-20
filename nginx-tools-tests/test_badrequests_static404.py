#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # jail nginx-badrequests defined by hand on the Odoo server (jail.local + filter.d)
# Tests of step 9c of nginx-hardening.sh (2.120): filter.d/nginx-badrequests.local adds ignoreregex lines so that the 404
# answered to a browser of Odoo on static files (Apps menu: icons of modules missing on the disk, deleted images, old
# bundles) are never counted, while probes still are. Case of 2026-11-20: 45.47.166.86, logged in to Odoo, banned 24 h.
# The functions are extracted from the script; the regular expressions are checked with Python's re, which is the engine
# used by fail2ban (no tag such as <HOST> in these lines).
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
IP = "45.47.166.86"


def ligne(requete, statut=404, ip=IP, referer="https://rencontres-linux.quebec/odoo/action-908", hote="rencontres-linux.quebec"):
    """One line of the access log (format combined_host of nginx/conf.d/odoo-global.conf)."""
    ua = '"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:160.0) Gecko/20100101 Firefox/160.0"'
    return (f'{ip} - - [20/Nov/2026:12:26:30 -0500] "{requete}" {statut} 153 "{referer}" {ua} host="{hote}" '
            f'rl=512 rt=0.004 urt="0.004" us=404')


def directe(requete, statut=404):
    """Same line without Referer: typed address, old link of an e-mail, or a scanner."""
    return ligne(requete, statut, referer="-")


def fonctions(*noms):
    texte = open(SCRIPT, encoding="utf-8").read()
    morceaux = []
    for nom in noms:
        debut = texte.index(f"\n{nom}() {{") + 1
        fin = texte.index("\n}\n", debut) + 3
        morceaux.append(texte[debut:fin])
    return "\n".join(morceaux)


def bash(corps, *args):
    marque = re.search(r'^F2B_BADREQ_MARK=.*$', open(SCRIPT, encoding="utf-8").read(), re.M).group(0)
    prog = "set -euo pipefail\n" + marque + "\n" + fonctions("f2b_static404_regex", "f2b_static404_local") + "\n" + corps
    return subprocess.run(["bash", "-c", prog, "bash", *args], capture_output=True, text=True)


def regex():
    r = bash("f2b_static404_regex")
    assert r.returncode == 0, r.stderr
    return [re.compile(x) for x in r.stdout.splitlines() if x.strip()]


def ignoree(texte, motifs):
    # fail2ban: a line is ignored when one ignoreregex matches it (re.search)
    return any(m.search(texte) for m in motifs)


class Static404Ignored(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motifs = regex()

    def test_requetes_du_menu_applications(self):
        for url in ("/account_avatax_oca/static/description/icon.png", "/openeducat_core/static/description/icon.png",
                    "/web/static/src/libs/fontawesome/fonts/fontawesome-webfont.woff2?v=4.7.0",
                    "/web/image/9718-5bbd03e0/20230923_132235.img_1096-EDIT.jpg.bbbb.jpg",
                    "/web/assets/1/86fbdfd/web.assets_frontend.min.css", "/website/image/ir.attachment/12_abc/datas"):
            with self.subTest(url=url):
                self.assertTrue(ignoree(ligne(f"GET {url} HTTP/2.0"), self.motifs), url)
                self.assertTrue(ignoree(ligne(f"HEAD {url} HTTP/1.1"), self.motifs), url)

    def test_les_sondes_comptent_toujours(self):
        for req in ("GET /.env HTTP/1.1", "GET /wp-login.php HTTP/1.1", "GET /admin/static/shell.php HTTP/1.1",
                    "GET /web/static/../../etc/passwd HTTP/1.1", "GET /web/image/../../../etc/passwd HTTP/1.1",
                    "GET /base/static/.env HTTP/1.1", "GET /base/static/.git/config HTTP/1.1",
                    "POST /web/image/1 HTTP/1.1", "GET /static/admin/x.png.php HTTP/1.1", "GET /cgi-bin/static/x.png HTTP/1.1"):
            with self.subTest(req=req):
                self.assertFalse(ignoree(directe(req), self.motifs), req)

    def test_autres_statuts_comptent(self):
        for statut in (400, 403, 444, 405):
            with self.subTest(statut=statut):
                self.assertFalse(ignoree(directe("GET /account/static/description/icon.png HTTP/2.0", statut), self.motifs))

    def test_cas_du_2026_11_20(self):
        # 39 icons answered 404 within one second: none is counted any more
        lignes = [ligne(f"GET /module_{i}/static/description/icon.png HTTP/2.0") for i in range(39)]
        self.assertEqual(sum(ignoree(x, self.motifs) for x in lignes), 39)

    def test_prefixe_de_langue_du_site(self):
        # 2.121: 132.211.165.182 (2026-11-20), the Apps menu after a change of language: icons asked under /en_CA/
        for url in ("/en_CA/account_avatax_oca/static/description/icon.png", "/fr/openeducat_core/static/description/icon.png",
                    "/es_ES/web/image/9718-5bbd03e0/x.jpg", "/en_CA/web_editor/static/src/img/x.svg", "/en/web/assets/1/abc/web.assets_frontend.min.css"):
            with self.subTest(url=url):
                self.assertTrue(ignoree(ligne(f"GET {url} HTTP/2.0"), self.motifs), url)
        for req in ("GET /en_CA/.env HTTP/1.1", "GET /fr/wp-login.php HTTP/1.1", "GET /en_CA/base/static/.git/config HTTP/1.1",
                    "GET /en_CA/web/static/../../etc/passwd HTTP/1.1", "GET /en_CA/admin/static/shell.php HTTP/1.1"):
            with self.subTest(req=req):
                self.assertFalse(ignoree(directe(req), self.motifs), req)

    def test_cas_du_2026_11_20_hec(self):
        modules = [f"module_{i}" for i in range(43)]
        lignes = [ligne(f"GET /{m}/static/description/icon.png HTTP/2.0") for m in modules]
        lignes += [ligne(f"GET /en_CA/{m}/static/description/icon.png HTTP/2.0") for m in modules]
        self.assertEqual(sum(ignoree(x, self.motifs) for x in lignes), 86)

    def test_pages_cachees_d_odoo(self):
        # 2.122: 404 answered to a visitor who may not see the page (not published, members only, internal users only)
        for url in ("/chat/80/T7kyKvEKT5", "/chat/128/syTPEribmg", "/discuss/channel/12", "/en_CA/event/open-house-on-linux-2026-25",
                    "/event/journee-portes-ouvertes-sur-linux-2026-125/track/reprendre-le-controle-154", "/event/diner-linux-123/register",
                    "/es/shop/sponsors-conferences-7", "/blog/nouvelles-1/post-12", "/my/tickets", "/odoo/action-908", "/slides/cours-3",
                    "/survey/start/abc?answer_token=x"):
            with self.subTest(url=url):
                self.assertTrue(ignoree(directe(f"GET {url} HTTP/2.0"), self.motifs), url)
        for req in ("GET /chat/../../etc/passwd HTTP/1.1", "GET /event/.env HTTP/1.1", "GET /events.php HTTP/1.1", "GET /mysql/admin HTTP/1.1",
                    "GET /shopping-cart.bak HTTP/1.1", "POST /chat/80/x HTTP/1.1"):
            with self.subTest(req=req):
                self.assertFalse(ignoree(directe(req), self.motifs), req)

    def test_lien_du_site_lui_meme(self):
        # an unpublished page linked from a published one (Referer on the same host as the request)
        self.assertTrue(ignoree(ligne("GET /plan-commandite HTTP/2.0", referer="https://rencontres-linux.quebec/a-propos"), self.motifs))
        self.assertTrue(ignoree(ligne("GET /prix-de-presence HTTP/2.0", referer="https://rencontres-linux.quebec"), self.motifs))
        self.assertTrue(ignoree(ligne("GET /en_CA/prix-de-presence HTTP/2.0", referer="http://rencontres-linux.quebec/en_CA/"), self.motifs))
        # without Referer, from another site, or a Referer naming another host: still counted
        self.assertFalse(ignoree(directe("GET /plan-commandite HTTP/2.0"), self.motifs))
        self.assertFalse(ignoree(ligne("GET /some/page HTTP/1.1", referer="https://scanner.example.net/"), self.motifs))
        self.assertFalse(ignoree(ligne("GET /some/page HTTP/1.1", referer="https://rencontres-linux.quebec.evil.net/"), self.motifs))
        self.assertFalse(ignoree(ligne("GET /x HTTP/1.1", referer="https://www.rencontres-linux.quebec/"), self.motifs))   # other host name
        # never "..", a dot file, or another status
        self.assertFalse(ignoree(ligne("GET /../../etc/passwd HTTP/1.1"), self.motifs))
        self.assertFalse(ignoree(ligne("GET /.git/config HTTP/1.1"), self.motifs))
        self.assertFalse(ignoree(ligne("GET / HTTP/1.1", statut=403), self.motifs))

    def test_pas_de_pourcent(self):
        # a "%" alone is an interpolation error in a fail2ban configuration file
        r = bash("f2b_static404_regex")
        self.assertNotIn("%", r.stdout)


class LocalFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def conf(self, texte):
        chemin = os.path.join(self.dir, "nginx-badrequests.conf")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        return chemin

    def test_garde_les_lignes_du_filtre(self):
        c = self.conf("[Definition]\nfailregex = ^<HOST> .* (400|404|444) \nignoreregex = \\.ico\n")
        out = bash('f2b_static404_local "$1"', c).stdout
        self.assertIn("[Definition]", out)
        self.assertIn("ignoreregex = %(known/ignoreregex)s", out)
        self.assertTrue(out.startswith("# GENERATED by nginx-hardening.sh"))
        self.assertGreaterEqual(out.count("HTTP/[0-9.]+"), 3)

    def test_filtre_sans_ignoreregex(self):
        c = self.conf("[Definition]\nfailregex = ^<HOST> .* 404 \n")
        out = bash('f2b_static404_local "$1"', c).stdout
        self.assertNotIn("known/ignoreregex", out)
        self.assertIn("ignoreregex =\n", out)

    def test_lignes_de_suite_indentees(self):
        c = self.conf("[Definition]\nignoreregex =\n")
        out = bash('f2b_static404_local "$1"', c).stdout.splitlines()
        i = next(n for n, x in enumerate(out) if x.startswith("ignoreregex ="))
        suite = out[i + 1:]
        self.assertTrue(suite and all(x.startswith("              \"") for x in suite), suite)

    def test_etape_dans_le_script(self):
        texte = open(SCRIPT, encoding="utf-8").read()
        self.assertIn("--- 9c) Jail $F2B_BADREQ_JAIL", texte)
        self.assertIn('fail2ban-client reload "$F2B_BADREQ_JAIL"', texte)
        # a hand-written .local is never overwritten
        self.assertIn('! grep -qF "$F2B_BADREQ_MARK" "$F2B_BADREQ_LOCAL"', texte)


if __name__ == "__main__":
    unittest.main()
