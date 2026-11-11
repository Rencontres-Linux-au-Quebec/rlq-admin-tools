#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # page de liens LittleLink (nginx-hardening.sh --link-page, étape 12d) : testée sur des dossiers temporaires
# 2.95: the step 12d is extracted from the script and run with stub nginx / git; the snippets and the link folder are temporary.
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
PAGE = os.path.join(ROOT, "nginx", "liens", "index.html")
COMMUN = os.path.join(ROOT, "nginx", "snippets", "odoo", "_odoo-common.conf")
SECURITE_INCLUDE = "include /etc/nginx/snippets/securite-commune.conf;"
PAGE_INCLUDE = "include /etc/nginx/snippets/liens-publics.conf;"


def texte_script():
    with open(SCRIPT, encoding="utf-8") as f:
        return f.read()


def etape_12d():
    t = texte_script()
    return t[t.index("# --- 12d)"):t.index("# --- 13) Courriel")]


class PageLiens(unittest.TestCase):
    """Contenu de nginx/liens/index.html : seuls les liens voulus, en HTTPS, sans exemple LittleLink."""
    def setUp(self):
        with open(PAGE, encoding="utf-8") as f:
            self.html = f.read()
        # seuls les liens <a> comptent ; css, polices et icônes sont des fichiers locaux
        self.liens = re.findall(r'<a [^>]*href="([^"]+)"', self.html)

    def test_aucun_lien_de_demonstration(self):
        for mauvais in ("yourwebsite", 'href="#"', "littlelink.io", "Your Name"):
            self.assertNotIn(mauvais, self.html)

    def test_tous_les_liens_en_https(self):
        for lien in self.liens:
            self.assertTrue(lien.startswith("https://"), lien)

    def test_liens_attendus(self):
        for attendu in ("facebook.com/groups/137418503088952", "linkedin.com/company/108532398/",
                        "linkedin.com/groups/8117971/", "youtube.com/@Rencontres-Linux.Quebec",
                        "framateam.org/linuxmeetup-mtl/", "rencontres-linux.quebec/event/journee-portes-ouvertes-sur-linux-2026-125/"):
            self.assertTrue(any(attendu in lien for lien in self.liens), attendu)

    def test_logo_du_site_present_et_reference(self):
        logo = os.path.join(ROOT, "nginx", "liens", "images", "rlq-logo.png")
        with open(logo, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertIn("images/rlq-logo.png", self.html)

    def test_pas_de_script_ni_de_formulaire(self):
        # la politique CSP de la page n'autorise aucun script ; la page ne doit pas en contenir
        self.assertNotIn("<script", self.html.lower())
        self.assertNotIn("<form", self.html.lower())


class IntegrationGabarit(unittest.TestCase):
    def test_include_apres_securite_et_avant_les_locations(self):
        with open(COMMUN, encoding="utf-8") as f:
            t = f.read()
        self.assertIn(PAGE_INCLUDE, t)
        self.assertLess(t.index(SECURITE_INCLUDE), t.index(PAGE_INCLUDE))
        self.assertLess(t.index(PAGE_INCLUDE), t.index("\nlocation / {"))

    def test_fragment_vide_cree_a_l_etape_0f(self):
        ligne = [l for l in texte_script().split("\n") if l.startswith("    for f in team-ips-geo.conf")]
        self.assertEqual(len(ligne), 1)
        self.assertIn("liens-publics.conf", ligne[0])

    def test_pinne_tag_et_sha(self):
        t = etape_12d()
        self.assertIn('LINKPAGE_TAG="v3.11.0"', t)
        self.assertRegex(re.search(r'LINKPAGE_SHA="([0-9a-f]+)"', t).group(1), r"^[0-9a-f]{40}$")

    def test_fragment_limite_a_get_et_head(self):
        self.assertIn("limit_except GET HEAD { deny all; }", etape_12d())


class EtapeExecutee(unittest.TestCase):
    """Exécute l'étape 12d avec des fonctions factices (nginx, git) dans un dossier temporaire."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-liens-")
        self.snip = os.path.join(self.tmp, "snippets")
        self.liens = os.path.join(self.tmp, "liens")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.snip)
        os.makedirs(self.bin)
        self.fragment = os.path.join(self.snip, "liens-publics.conf")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _faux_git(self, sha, avec_dossiers=True):
        # faux git : « clone » crée le tag ; « rev-parse » renvoie le SHA donné
        dossiers = "mkdir -p \"$dest/css\" \"$dest/fonts\" \"$dest/images\"; echo x > \"$dest/css/a.css\"; echo x > \"$dest/fonts/f.woff2\"; echo x > \"$dest/images/i.png\";" if avec_dossiers else ""
        script = (
            "#!/bin/bash\n"
            "if [ \"$1\" = clone ]; then\n"
            "  dest=\"${@: -1}\"; mkdir -p \"$dest\"; " + dossiers + "\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$3\" = rev-parse ] || [ \"$1\" = -C ]; then echo " + sha + "; exit 0; fi\n"
            "exit 1\n")
        chemin = os.path.join(self.bin, "git")
        with open(chemin, "w") as f:
            f.write(script)
        os.chmod(chemin, 0o755)

    def _executer(self, lp_option, check=0, nginx_ok=1, sha_recu=None, avec_dossiers=True):
        if sha_recu is not None:
            self._faux_git(sha_recu, avec_dossiers)
        faux_nginx = os.path.join(self.bin, "nginx")
        with open(faux_nginx, "w") as f:
            f.write("#!/bin/bash\n[ \"$1\" = -t ] && exit " + ("0" if nginx_ok else "1") + "\nexit 0\n")
        os.chmod(faux_nginx, 0o755)
        prelude = (
            "set -u\n"
            f"export PATH={self.bin}:$PATH\n"
            f"SCRIPT_DIR={ROOT!r}\n"
            "APP_NAME=odoo; CHECK_ONLY=%d; ROLLBACK_YES=1; LINK_PAGE=%d\n" % (check, lp_option)
            + f"NGINX_HARDENING_SNIPPETS_DIR={self.snip!r}; NGINX_HARDENING_LIENS_DIR={self.liens!r}\n"
            "PASS=0; FAIL=0; WARN=0\n"
            "pass() { echo \"OK $1\"; PASS=$((PASS+1)); }\n"
            "fail() { echo \"FAIL $1\"; FAIL=$((FAIL+1)); }\n"
            "warn() { echo \"ATTN $1\"; WARN=$((WARN+1)); }\n"
            "tty_ligne() { :; }\n"
            "run() { \"$@\"; }\n"
            "nginx_appliquer() { NGINX_APPLIQUE=reloaded; return 0; }\n"
        )
        chemin = os.path.join(self.tmp, "etape.sh")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(prelude + etape_12d())
        return subprocess.run(["bash", chemin], capture_output=True, text=True, timeout=120)

    def test_sans_option_et_sans_page_ne_cree_rien(self):
        r = self._executer(0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.fragment))
        self.assertFalse(os.path.exists(self.liens))

    def test_no_link_page_desactive_sans_supprimer_les_fichiers(self):
        os.makedirs(self.liens)
        with open(self.fragment, "w") as f:
            f.write("# liens : actif\nlocation ^~ /liens/ { alias x/; }\n")
        r = self._executer(-1)
        self.assertIn("OK page de liens inactive", r.stdout)
        contenu = open(self.fragment).read()
        self.assertIn("# liens : inactif", contenu)
        self.assertNotIn("location", contenu)

    def test_check_only_ne_modifie_rien(self):
        r = self._executer(1, check=1)
        self.assertIn("ATTN page de liens", r.stdout)
        self.assertFalse(os.path.exists(self.fragment))

    def test_nginx_t_refuse_restaure_l_ancien_fragment(self):
        with open(self.fragment, "w") as f:
            f.write("# liens : inactif\n")
        r = self._executer(1, nginx_ok=0, sha_recu="3c9162c9f8324d5e002259ed8b4b3cc377b08486")
        self.assertIn("FAIL nginx -t refuse la page de liens", r.stdout)
        self.assertEqual(open(self.fragment).read(), "# liens : inactif\n")

    def test_sha_different_refuse_et_ne_copie_rien(self):
        r = self._executer(1, sha_recu="0" * 40)
        self.assertIn("SHA", r.stdout)
        self.assertIn("installation refusée", r.stdout)
        self.assertFalse(os.path.exists(self.fragment))
        self.assertFalse(os.path.exists(os.path.join(self.liens, "css")))

    def test_installation_complete_avec_sha_correct(self):
        r = self._executer(1, sha_recu="3c9162c9f8324d5e002259ed8b4b3cc377b08486")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("page de liens active", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.liens, "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(self.liens, "css", "a.css")))
        self.assertTrue(os.path.isfile(os.path.join(self.liens, "images", "rlq-logo.png")))
        contenu = open(self.fragment).read()
        self.assertIn("location ^~ /liens/ {", contenu)
        self.assertIn(f"alias {self.liens}/;", contenu)


if __name__ == "__main__":
    unittest.main()
