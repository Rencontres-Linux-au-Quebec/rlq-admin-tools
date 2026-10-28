#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # --disable-uri / --enable-uri de nginx-hardening.sh (2.60), testés sur des dossiers temporaires
# Step 12c (URI refusées) extracted from the script and run with a stub nginx; the snippets folder is a temporary folder.
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
SECURITE = os.path.join(ROOT, "nginx", "snippets", "securite-commune.conf")


def etape():
    texte = open(SCRIPT, encoding="utf-8").read()
    debut = texte.index("# --- 12c) URI")
    fin = texte.index("# --- 13) Courriel")
    return texte[debut:fin]


class UriRefusees(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.snip = os.path.join(self.tmp, "snippets")
        os.makedirs(os.path.join(self.tmp, "bin"))
        for nom in ("nginx", "systemctl"):
            with open(os.path.join(self.tmp, "bin", nom), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(os.path.join(self.tmp, "bin", nom), 0o755)

    def lancer(self, ajouts, retraits):
        prog = (
            'set -uo pipefail\n'
            'pass(){ echo "PASS $*"; }; warn(){ echo "WARN $*"; }; fail(){ echo "FAIL $*"; }\n'
            'run(){ "$@"; }; nginx_appliquer(){ NGINX_APPLIQUE=rechargé; return 0; }\n'
            f'export PATH="{self.tmp}/bin:$PATH"\n'
            f'APP_NAME=odoo; CHECK_ONLY=0; NGINX_HARDENING_SNIPPETS_DIR="{self.snip}"\n'
            f'DISABLE_URI_LIST=({" ".join(ajouts)}); ENABLE_URI_LIST=({" ".join(retraits)})\n'
            + etape()
        )
        return subprocess.run(["bash", "-c", prog], capture_output=True, text=True)

    def lire(self):
        with open(os.path.join(self.snip, "uri-desactivees.conf"), encoding="utf-8") as f:
            return f.read()

    def test_ajout_genere_une_location_par_chemin_toutes_langues(self):
        r = self.lancer(['"/shop"'], [])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("location ~ ^(/[A-Za-z_-]+)?/shop(/|$) { return 404; }", self.lire())
        self.assertIn("# uri : /shop", self.lire())

    def test_point_echappe_dans_le_motif(self):
        self.lancer(['"/blog.x"'], [])
        self.assertIn(r"/blog\.x(/|$)", self.lire())

    def test_retrait_puis_conservation_sans_option(self):
        self.lancer(['"/shop"', '"/blog"'], [])
        self.lancer([], ['"/shop"'])
        self.assertNotIn("/shop", self.lire())
        self.assertIn("# uri : /blog", self.lire())
        self.lancer([], [])                       # sans option : la liste du fichier est conservée
        self.assertIn("# uri : /blog", self.lire())

    def test_liste_vide_fichier_valide_sans_location(self):
        self.lancer(['"/shop"'], [])
        self.lancer([], ['"/shop"'])
        self.assertNotIn("location", self.lire())
        self.assertIn("Aucune URI refusée", self.lire())

    def test_include_present_dans_securite_commune(self):
        with open(SECURITE, encoding="utf-8") as f:
            self.assertIn("include /etc/nginx/snippets/uri-desactivees.conf;", f.read())


if __name__ == "__main__":
    unittest.main()
