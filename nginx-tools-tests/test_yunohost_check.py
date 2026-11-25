#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# Licence: GNU Affero General Public License, version 3 or later - https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""yunohost-check.sh sur un FAUX serveur (dossier temporaire) et un FAUX curl (aucune connexion réelle).
Domaines en .example.test uniquement."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import SCRIPTS_DIR

# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs).
ENVIRONNEMENT = "commun"

PROG = os.path.join(SCRIPTS_DIR, "yunohost-check.sh")

FAUX_CURL = """#!/bin/bash
# Faux curl : renvoie 200 pour ok.example.test, 503 pour les autres ; ne se connecte à rien.
url="${@: -1}"
case "$url" in
  *ok.example.test*) echo -n 200 ;;
  *) echo -n 503 ;;
esac
"""


FAUX_OPENSSL = """#!/bin/bash
# Faux openssl : certificat factice valable jusqu'en 2099 ; aucune connexion.
if [[ "$1" == x509 ]]; then echo "notAfter=Dec 31 23:59:59 2099 GMT"; fi
exit 0
"""


class YunohostCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-yunohost-check-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.racine = os.path.join(self.tmp, "racine")
        os.makedirs(self.racine)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        curl = os.path.join(self.bin, "curl")
        with open(curl, "w", encoding="utf-8") as f:
            f.write(FAUX_CURL)
        os.chmod(curl, 0o755)
        openssl = os.path.join(self.bin, "openssl")
        with open(openssl, "w", encoding="utf-8") as f:
            f.write(FAUX_OPENSSL)
        os.chmod(openssl, 0o755)

    def app(self, nom, domaine, chemin="/"):
        d = os.path.join(self.racine, "etc/yunohost/apps", nom)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "settings.yml"), "w", encoding="utf-8") as f:
            f.write(f"id: {nom}\ndomain: {domaine}\npath: {chemin}\n")

    def lancer(self, *args, racine=True):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), NO_COLOR="1",
                   HOME=self.tmp, NGINX_TOOLS_TEST_EUID="0")
        env["APP_DETECT_ROOT"] = self.racine if racine else os.path.join(self.tmp, "vide")
        r = subprocess.run(["bash", PROG, *args], capture_output=True, text=True, env=env, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def test_mode_interne_ok_et_echec(self):
        self.app("nextcloud", "ok.example.test")
        self.app("tiki", "bad.example.test", "/wiki")
        rc, out = self.lancer()
        self.assertIn("[OK]", out)
        self.assertIn("https://ok.example.test/", out)
        self.assertIn("[FAIL]", out)
        self.assertIn("https://bad.example.test/wiki", out)
        self.assertEqual(rc, 1, out)

    def test_tout_ok_rc_zero(self):
        self.app("nextcloud", "ok.example.test")
        rc, out = self.lancer()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("[FAIL]", out)

    def test_aucune_application(self):
        os.makedirs(os.path.join(self.tmp, "vide"), exist_ok=True)
        rc, out = self.lancer(racine=False)
        self.assertEqual(rc, 0, out)
        self.assertIn("Aucune application", out)

    def test_mode_externe_avec_fichier_cibles(self):
        cibles = os.path.join(self.tmp, "cibles.tsv")
        with open(cibles, "w", encoding="utf-8") as f:
            f.write("ok.example.test\t/\n")
        rc, out = self.lancer("--external", "--targets", cibles)
        self.assertEqual(rc, 0, out)
        self.assertIn("https://ok.example.test/", out)

    def test_externe_sans_cibles_refuse(self):
        rc, out = self.lancer("--external")
        self.assertEqual(rc, 2)
        self.assertIn("--targets", out)

    def test_list_ecrit_tsv_sans_secret(self):
        self.app("nextcloud", "ok.example.test")
        sortie = os.path.join(self.tmp, "apps.tsv")
        rc, out = self.lancer("--list", sortie)
        self.assertEqual(rc, 0, out)
        with open(sortie, encoding="utf-8") as f:
            contenu = f.read()
        self.assertEqual(contenu, "nextcloud\tnextcloud\tok.example.test\t/\n")

    def test_version_dynamique(self):
        rc, out = self.lancer("--version")
        self.assertEqual(rc, 0)
        self.assertRegex(out.strip(), r"^yunohost-check\.sh 0\.1\.\d{8}\.\d{6}$")

    def test_aide_options_triees(self):
        rc, out = self.lancer("--help")
        self.assertEqual(rc, 0)
        options = [m.group(1) for m in re.finditer(r"^  --([a-z-]+)", out, re.M)]
        self.assertGreater(len(options), 5)
        self.assertEqual(options, sorted(options))

    def test_save_puis_compare_sans_changement(self):
        self.app("nextcloud", "ok.example.test")
        base = os.path.join(self.tmp, "base.tsv")
        rc, out = self.lancer("--save", base)
        self.assertEqual(rc, 0, out)
        rc, out = self.lancer("--compare", base)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("changement", out)

    def test_compare_regression_bloque(self):
        self.app("tiki", "bad.example.test", "/wiki")
        base = os.path.join(self.tmp, "base.tsv")
        with open(base, "w", encoding="utf-8") as f:
            f.write("bad.example.test\t/wiki\t200\n")
        rc, out = self.lancer("--compare", base)
        self.assertEqual(rc, 1, out)
        self.assertIn("régression", out)

    def test_compare_changement_non_bloquant(self):
        self.app("nextcloud", "ok.example.test")
        base = os.path.join(self.tmp, "base.tsv")
        with open(base, "w", encoding="utf-8") as f:
            f.write("ok.example.test\t/\t404\n")
        rc, out = self.lancer("--compare", base)
        self.assertEqual(rc, 0, out)
        self.assertIn("changement", out)

    def test_option_inconnue(self):
        rc, out = self.lancer("--n-existe-pas")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
