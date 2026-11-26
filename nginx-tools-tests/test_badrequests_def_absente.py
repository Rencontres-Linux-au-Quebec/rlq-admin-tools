#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# Licence: GNU Affero General Public License, version 3 or later - https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""nginx-hardening.sh, jail nginx-badrequests (2.128): la ligne qui lit la définition de la jail arrêtait tout le script
(set -euo pipefail) quand l'un des deux fichiers était absent (104 et 105, 2026-11-25). Le test reprend la ligne exacte du
script, redirige les deux chemins vers des fichiers absents ou présents, et exige que le shell continue."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import SCRIPTS_DIR

ENVIRONNEMENT = "commun"

SCRIPT = os.path.join(SCRIPTS_DIR, "nginx-hardening.sh")
CHEMIN_CONF = "/etc/fail2ban/jail.d/nginx-badrequests.conf"
CHEMIN_LOCAL = "/etc/fail2ban/jail.local"


def ligne_du_script():
    with open(SCRIPT, encoding="utf-8") as f:
        for ligne in f:
            m = re.match(r"^\s*(f2b_badreq_def=\$\(.*\))\s*$", ligne)
            if m:
                return m.group(1)
    raise AssertionError("ligne f2b_badreq_def introuvable dans nginx-hardening.sh")


class BadrequestsDefAbsente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-badreq-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.conf = os.path.join(self.tmp, "nginx-badrequests.conf")
        self.local = os.path.join(self.tmp, "jail.local")
        self.ligne = (ligne_du_script().replace(CHEMIN_CONF, self.conf).replace(CHEMIN_LOCAL, self.local))

    def executer(self):
        script = f'set -euo pipefail\n{self.ligne}\nprintf "CONTINUE\\n%s\\n" "$f2b_badreq_def"\n'
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30, check=False)

    def test_deux_fichiers_absents_le_script_continue(self):
        r = self.executer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CONTINUE", r.stdout)
        self.assertEqual(r.stdout.split("CONTINUE\n", 1)[1].strip(), "")

    def test_un_seul_fichier_present_le_script_continue(self):
        with open(self.local, "w", encoding="utf-8") as f:
            f.write("[DEFAULT]\n\n[nginx-badrequests]\nenabled = true\n\n[sshd]\nenabled = true\n")
        r = self.executer()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CONTINUE", r.stdout)

    def test_definition_extraite_sans_la_section_suivante(self):
        with open(self.local, "w", encoding="utf-8") as f:
            f.write("[nginx-badrequests]\nenabled = true\n\n[sshd]\nenabled = true\n")
        r = self.executer()
        self.assertEqual(r.returncode, 0, r.stderr)
        extrait = r.stdout.split("CONTINUE\n", 1)[1]
        self.assertIn("[nginx-badrequests]", extrait)
        # sed prints the header of the next section, but not its keys: only one "enabled" line (ours)
        self.assertEqual(extrait.count("enabled"), 1)


if __name__ == "__main__":
    unittest.main()
