#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # jail nginx-sqli definie a la main sur le serveur Odoo (jail.local)
# Tests of step 9b of nginx-hardening.sh (2.58): the logpath of the hand-written jail nginx-sqli also reads blocked-probes.log.
# The two helper functions are extracted from the script and run on a copy of a jail.local file.
import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
LOG = "/var/log/nginx/blocked-probes.log"

JAIL = """[DEFAULT]
ignoreip = 127.0.0.1/8

[nginx-sqli]
enabled  = true
filter   = nginx-sqli
logpath  = /var/log/nginx/*access.log
maxretry = 3
bantime  = 86400

[nginx-badrequests]
enabled  = true
logpath  = /var/log/nginx/*access.log
"""

JAIL_MULTI = """[nginx-sqli]
logpath  = /var/log/nginx/site-access.log
           /var/log/nginx/other-access.log
[nginx-badrequests]
logpath  = /var/log/nginx/*access.log
"""


def fonctions(*noms):
    """Bash text of the named functions, copied from nginx-hardening.sh."""
    texte = open(SCRIPT, encoding="utf-8").read()
    morceaux = []
    for nom in noms:
        debut = texte.index(f"\n{nom}() {{") + 1
        fin = texte.index("\n}\n", debut) + 3
        morceaux.append(texte[debut:fin])
    return "\n".join(morceaux)


def bash(corps, *args):
    prog = "set -euo pipefail\n" + fonctions("f2b_section_contient", "f2b_logpath_ajouter") + "\n" + corps
    return subprocess.run(["bash", "-c", prog, "bash", *args], capture_output=True, text=True)


class LogpathStep(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def fichier(self, texte):
        chemin = os.path.join(self.dir, "jail.local")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        return chemin

    def test_absent_then_present_after_insertion(self):
        chemin = self.fichier(JAIL)
        absent = bash('f2b_section_contient "$1" nginx-sqli "$2"', chemin, LOG)
        self.assertNotEqual(absent.returncode, 0)
        sortie = bash('f2b_logpath_ajouter "$1" nginx-sqli "$2"', chemin, LOG)
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        self.assertIn(LOG, sortie.stdout)
        ecrit = self.fichier(sortie.stdout)
        present = bash('f2b_section_contient "$1" nginx-sqli "$2"', ecrit, LOG)
        self.assertEqual(present.returncode, 0)

    def test_only_nginx_sqli_section_changes(self):
        chemin = self.fichier(JAIL)
        sortie = bash('f2b_logpath_ajouter "$1" nginx-sqli "$2"', chemin, LOG).stdout
        autres = [l for l in sortie.splitlines() if LOG in l]
        self.assertEqual(len(autres), 1)
        # The line sits right after the nginx-sqli logpath, before the next section.
        lignes = sortie.splitlines()
        i = lignes.index(autres[0])
        self.assertTrue(lignes[i - 1].strip().startswith("logpath"))
        self.assertLess(sortie.index(LOG), sortie.index("[nginx-badrequests]"))
        self.assertEqual(sortie.count("[nginx-badrequests]"), 1)
        self.assertEqual(sortie.count(LOG), 1)

    def test_multiline_logpath_keeps_continuation(self):
        chemin = self.fichier(JAIL_MULTI)
        sortie = bash('f2b_logpath_ajouter "$1" nginx-sqli "$2"', chemin, LOG).stdout
        self.assertIn("/var/log/nginx/site-access.log", sortie)
        self.assertIn("/var/log/nginx/other-access.log", sortie)
        self.assertIn(LOG, sortie)
        self.assertEqual(bash('f2b_section_contient "$1" nginx-sqli "$2"', self.fichier(sortie), LOG).returncode, 0)

    def test_missing_section_gives_no_change(self):
        chemin = self.fichier("[nginx-badrequests]\nlogpath = /var/log/nginx/x-access.log\n")
        sortie = bash('f2b_logpath_ajouter "$1" nginx-sqli "$2"', chemin, LOG).stdout
        self.assertEqual(sortie, open(chemin, encoding="utf-8").read())
        self.assertNotIn(LOG, sortie)


if __name__ == "__main__":
    unittest.main()
