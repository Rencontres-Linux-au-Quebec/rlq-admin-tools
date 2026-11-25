#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# Licence: GNU Affero General Public License, version 3 or later - https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Profil d'application YunoHost (apps/yunohost.conf) : détection par les fichiers /etc/yunohost, choix explicite par
--app / APP_PROFILE, et même résultat en bash (apps/_profile.sh) et en Python (apps/_profile.py).
Aucune donnée réelle : le faux serveur est un dossier temporaire (APP_DETECT_ROOT)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import SCRIPTS_DIR

# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs).
ENVIRONNEMENT = "commun"

APPS = os.path.join(SCRIPTS_DIR, "apps")
if APPS not in sys.path:
    sys.path.insert(0, APPS)
import _profile  # noqa: E402


class ProfilYunohost(unittest.TestCase):
    def setUp(self):
        self.racine = tempfile.mkdtemp(prefix="test-rlq-yunohost-")
        self.addCleanup(shutil.rmtree, self.racine, True)
        ancienne = os.environ.get("APP_DETECT_ROOT")
        os.environ["APP_DETECT_ROOT"] = self.racine
        self.addCleanup(self._restaurer, ancienne)

    @staticmethod
    def _restaurer(ancienne):
        if ancienne is None:
            os.environ.pop("APP_DETECT_ROOT", None)
        else:
            os.environ["APP_DETECT_ROOT"] = ancienne

    def marquer(self, chemin):
        """Crée un fichier de marque YunoHost dans le faux serveur."""
        complet = os.path.join(self.racine, chemin.lstrip("/"))
        os.makedirs(os.path.dirname(complet), exist_ok=True)
        open(complet, "w").close()

    def test_fichier_current_host_detecte_yunohost(self):
        self.marquer("/etc/yunohost/current_host")
        profil = _profile.charger_profil_app(APPS)
        self.assertEqual(profil["APP_NAME"], "yunohost")
        self.assertEqual(profil["APP_DETECTION"], "détectée automatiquement")

    def test_fichier_installed_detecte_yunohost(self):
        self.marquer("/etc/yunohost/installed")
        self.assertEqual(_profile.charger_profil_app(APPS)["APP_NAME"], "yunohost")

    def test_sans_marque_pas_detecte(self):
        with self.assertRaises(_profile.ProfilError):
            _profile.charger_profil_app(APPS)

    def test_option_force_sans_marque(self):
        profil = _profile.charger_profil_app(APPS, "yunohost")
        self.assertEqual(profil["APP_NAME"], "yunohost")
        self.assertIn("forcée", profil["APP_DETECTION"])

    def test_cles_du_profil(self):
        profil = _profile.charger_profil_app(APPS, "yunohost")
        self.assertEqual(profil["ACCESS_LOGS"], "*-access.log")
        self.assertEqual(profil["ERROR_LOGS"], "*-error.log")
        self.assertEqual(profil["CATCHALL_LOG"], "")
        self.assertEqual(profil["DETECT_ODOO_CONF"], "no")
        self.assertEqual(profil["ODOO_SPECIFIC_STEPS"], "no")
        self.assertEqual(profil["BACKEND_PORTS"], "")
        self.assertIn("/yunohost/sso/", profil["LOGIN_PATHS"])
        self.assertIn("/yunohost/admin/", profil["ADMIN_PATHS"])

    def test_bash_et_python_identiques(self):
        self.marquer("/etc/yunohost/current_host")
        env = dict(os.environ)
        rc, sortie, erreur = self._bash(env)
        self.assertEqual(rc, 0, erreur)
        self.assertEqual(sortie.strip(), "yunohost")
        self.assertEqual(_profile.charger_profil_app(APPS)["APP_NAME"], "yunohost")

    def _bash(self, env):
        script = ('. "$1/_profile.sh"; charger_profil_app "$1" && echo "$APP_NAME"')
        r = subprocess.run(["bash", "-c", script, "bash", APPS], capture_output=True, text=True, env=env, timeout=60)
        return r.returncode, r.stdout, r.stderr


if __name__ == "__main__":
    unittest.main()
