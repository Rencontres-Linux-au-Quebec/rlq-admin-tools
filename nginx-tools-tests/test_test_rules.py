#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # --test-rules de nginx-hardening.sh (2.65) : nginx et curl simulés dans un dossier temporaire
# The option sends curl requests to the local nginx; stubs replace nginx and curl so that the verdict is tested without a server.
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")

NGINX = '#!/bin/sh\n[ "$1" = "-T" ] && echo "server { server_name odoo.test.example; }"\nexit 0\n'
CURL_OK = '#!/bin/sh\ncase "$*" in\n  *stfD*|*%2e%2e*|*/.env*) echo 404 ;;\n  *TRACE*) echo 405 ;;\n  *AhrefsBot*) echo 403 ;;\n  *) echo 200 ;;\nesac\n'


class TestRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)

    def stub(self, curl):
        for nom, texte in (("nginx", NGINX), ("curl", curl)):
            chemin = os.path.join(self.bin, nom)
            with open(chemin, "w") as f:
                f.write(texte)
            os.chmod(chemin, 0o755)

    def lancer(self):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), LANG="C", LC_ALL="C")
        return subprocess.run(["bash", SCRIPT, "--app=odoo", "--test-rules", "--lang", "en"],
                              capture_output=True, text=True, env=env, timeout=120)

    def test_regles_en_place_sortie_zero(self):
        self.stub(CURL_OK)
        r = self.lancer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("8 cases OK", r.stdout)
        self.assertIn("0 failed", r.stdout)

    def test_regle_absente_sortie_un(self):
        self.stub('#!/bin/sh\necho 200\n')
        r = self.lancer()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("[FAIL]", r.stdout)
        self.assertIn("expected: 404", r.stdout)


if __name__ == "__main__":
    unittest.main()
