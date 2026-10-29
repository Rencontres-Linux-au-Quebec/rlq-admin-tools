#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # --disable-uri / --enable-uri de nginx-hardening.sh (2.60), testés sur des dossiers temporaires
# Step 12c (URI refusées) extracted from the script and run with a stub nginx; the snippets folder is a temporary folder.
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
SECURITE = os.path.join(ROOT, "nginx", "snippets", "securite-commune.conf")


def etape():
    texte = open(SCRIPT, encoding="utf-8").read()
    debut = texte.index("# uri_noms_testables:")
    fin = texte.index("# --- 13) Courriel")
    return texte[debut:fin]


class UriRefusees(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.snip = os.path.join(self.tmp, "snippets")
        os.makedirs(os.path.join(self.tmp, "bin"))
        # faux nginx : « nginx -T » déclare un nom public ; faux curl : répond le code de CODE_HTTP (404 par défaut)
        with open(os.path.join(self.tmp, "bin", "nginx"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = "-T" ] && echo "server { server_name exemple.test; }"\nexit 0\n')
        with open(os.path.join(self.tmp, "bin", "curl"), "w") as f:
            f.write('#!/bin/sh\necho "${CODE_HTTP:-404}"\n')
        with open(os.path.join(self.tmp, "bin", "systemctl"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        for nom in ("nginx", "curl", "systemctl"):
            os.chmod(os.path.join(self.tmp, "bin", nom), 0o755)

    def lancer(self, ajouts, retraits, oui=True):
        prog = (
            'set -uo pipefail\n'
            'pass(){ echo "PASS $*"; }; warn(){ echo "WARN $*"; }; fail(){ echo "FAIL $*"; }\n'
            'run(){ "$@"; }; nginx_appliquer(){ NGINX_APPLIQUE=rechargé; return 0; }\n'
            f'export PATH="{self.tmp}/bin:$PATH"\n'
            f'APP_NAME=odoo; CHECK_ONLY=0; NGINX_HARDENING_SNIPPETS_DIR="{self.snip}"\n'
            f'DISABLE_URI_LIST=({" ".join(ajouts)}); ENABLE_URI_LIST=({" ".join(retraits)}); ROLLBACK_YES={1 if oui else 0}\n'
            + etape()
        )
        return subprocess.run(["bash", "-c", prog], capture_output=True, text=True)

    def lire(self):
        with open(os.path.join(self.snip, "uri-desactivees.conf"), encoding="utf-8") as f:
            return f.read()

    def test_ajout_genere_une_location_par_chemin_toutes_langues(self):
        r = self.lancer(['"/shop"'], [])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("location ~ ^(/[A-Za-z0-9_-]+)?/shop(/|$) { return 404; }", self.lire())
        self.assertIn("# uri : /shop", self.lire())

    def test_sans_confirmation_ni_terminal_rien_n_est_modifie(self):
        r = self.lancer(['"/shop"'], [], oui=False)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.snip, "uri-desactivees.conf")))
        self.assertIn("Pas de terminal", r.stdout)

    def test_verification_404_sur_chaque_nom_public(self):
        r = self.lancer(['"/shop"'], [])
        self.assertIn("toutes répondent 404", r.stdout, r.stdout + r.stderr)

    def test_verification_signale_un_200(self):
        with unittest.mock.patch.dict(os.environ, {"CODE_HTTP": "200"}):
            r = self.lancer(['"/shop"'], [])
        self.assertIn("ne répondent pas 404", r.stdout, r.stdout + r.stderr)
        self.assertIn("exemple.test/shop : HTTP 200", r.stdout)

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


class FiltreTagsEvenements(unittest.TestCase):
    """securite-commune.conf, regle 3 bis (v1.15): ?tags= malforme sur /event -> 404 (Odoo: literal_eval -> 500)."""

    def motif(self):
        texte = open(SECURITE, encoding="utf-8").read()
        m = re.search(r'if \(\$request_uri ~\* "(\^\(/\[a-z_\]\+\)\?/event.*?)"\) \{', texte)
        self.assertIsNotNone(m, "regle 3 bis introuvable dans securite-commune.conf")
        return m.group(1)

    def refuse(self, uri):
        return re.search(self.motif(), uri, re.IGNORECASE) is not None

    def test_valeurs_malformees_refusees(self):
        for uri in ("/event?tags=stfD", "/en_CA/event?search=zqzz&tags=stfD", "/event?tags=[x]", "/event?tags=[35]x",
                    "/event?tags=[35]&tags=stfD", "/event?date=upcoming&tags=[zz]", "/es/event?tags=%5B35%5D"):
            self.assertTrue(self.refuse(uri), uri)

    def test_liens_legitimes_du_site_acceptes(self):
        for uri in ("/es/event/jornada-linux-2025-23/track?tags=[35,+40,+12,+37]", "/event?tags=[1]&date=x",
                    "/event?tags=[1,2,3]", "/event?tags=[35,%2B40]", "/event", "/event/x/track", "/shop?tags=stfD"):
            self.assertFalse(self.refuse(uri), uri)


if __name__ == "__main__":
    unittest.main()
