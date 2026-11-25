#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# Licence: GNU Affero General Public License, version 3 or later - https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Détection des applications YunoHost (apps/_yunohost.py) sur un FAUX serveur temporaire : aucun vrai domaine,
aucune lecture de /etc. Les noms de domaine sont en .test."""
import os
import shutil
import sys
import tempfile
import unittest

from helpers import SCRIPTS_DIR

# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs).
ENVIRONNEMENT = "commun"

APPS = os.path.join(SCRIPTS_DIR, "apps")
if APPS not in sys.path:
    sys.path.insert(0, APPS)
import _yunohost  # noqa: E402


class ApplicationsYunohost(unittest.TestCase):
    def setUp(self):
        self.racine = tempfile.mkdtemp(prefix="test-rlq-yunohost-apps-")
        self.addCleanup(shutil.rmtree, self.racine, True)

    def ecrire(self, chemin, texte=""):
        complet = os.path.join(self.racine, chemin.lstrip("/"))
        os.makedirs(os.path.dirname(complet), exist_ok=True)
        with open(complet, "w", encoding="utf-8") as f:
            f.write(texte)

    def settings(self, nom, domaine, chemin="/", identifiant=None):
        self.ecrire(f"/etc/yunohost/apps/{nom}/settings.yml",
                    f"id: {identifiant or nom}\n"
                    f"domain: {domaine}\n"
                    f"path: {chemin}\n"
                    "current_revision: 0.0.1\n"
                    "install_time: 1700000000\n"
                    "  domain: sous-section-a-ignorer\n")

    def test_applications_lues_depuis_settings(self):
        self.settings("nextcloud", "nuage.example.test")
        self.settings("tiki", "tiki.example.test", "/wiki")
        apps = _yunohost.applications(self.racine)
        self.assertEqual([a["name"] for a in apps], ["nextcloud", "tiki"])
        self.assertEqual(apps[0]["domain"], "nuage.example.test")
        self.assertEqual(apps[1]["path"], "/wiki")

    def test_cle_indentee_ignoree(self):
        self.settings("nextcloud", "nuage.example.test")
        self.assertEqual(_yunohost.applications(self.racine)[0]["domain"], "nuage.example.test")

    def test_identifiant_par_defaut_nom_du_dossier(self):
        self.ecrire("/etc/yunohost/apps/mattermost/settings.yml", "domain: equipe.example.test\npath: /\n")
        app = _yunohost.applications(self.racine)[0]
        self.assertEqual(app["id"], "mattermost")

    def test_application_sans_domaine_signalee_pas_ignoree(self):
        self.ecrire("/etc/yunohost/apps/orpheline/settings.yml", "id: orpheline\n")
        app = _yunohost.applications(self.racine)[0]
        self.assertEqual(app["domain"], "")
        self.assertEqual(app["nginx_dir"], "")

    def test_repertoire_de_configuration_nginx_du_domaine(self):
        self.settings("nextcloud", "nuage.example.test")
        app = _yunohost.applications(self.racine)[0]
        self.assertTrue(app["nginx_dir"].endswith("/etc/nginx/conf.d/nuage.example.test.d"))

    def test_sans_yunohost_liste_vide(self):
        self.assertEqual(_yunohost.applications(self.racine), [])
        self.assertFalse(_yunohost.est_yunohost(self.racine))

    def test_est_yunohost_par_marque(self):
        self.ecrire("/etc/yunohost/current_host", "example.test\n")
        self.assertTrue(_yunohost.est_yunohost(self.racine))

    def test_settings_illisible_ignore(self):
        self.ecrire("/etc/yunohost/apps/cassee/settings.yml", "domain: x.example.test\n")
        os.chmod(os.path.join(self.racine, "etc/yunohost/apps/cassee/settings.yml"), 0)
        self.addCleanup(os.chmod, os.path.join(self.racine, "etc/yunohost/apps/cassee/settings.yml"), 0o644)
        if os.geteuid() == 0:
            self.skipTest("root lit tout : permissions non testables")
        self.assertEqual(_yunohost.applications(self.racine), [])


if __name__ == "__main__":
    unittest.main()
