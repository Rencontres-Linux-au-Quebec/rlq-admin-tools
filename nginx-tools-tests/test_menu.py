"""--menu (tous les programmes du dépôt) : l'option est dans l'aide, et sans terminal le menu refuse (code 1) sans rien lancer.
Le fonctionnement du menu dans un terminal (dialog ou texte) est vérifié à la main (voir les entrées de CHANGELOG.md)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
NATURE_TESTS = "fonctionnel"   # run-all 1.188 (statistics): versions, changelogs, headers, sorted options: files read, nothing executed (a test that runs a program stays "functional")
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import script_path

PROGRAMMES = ["nginx-log-audit.sh", "sync-crowdsec-blocklist.sh", "odoo-backup.sh", "odoo-update-module.sh",
              "app-health-check.py", "app-log-check.py", "app-log-live.py", "web-monitor.py", "zip-versions.py",
              "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "odoo-warmup.py", "host-perf-audit.py"]


def lancer(programme, *args):
    exe = ["python3", script_path(programme)] if programme.endswith(".py") else ["bash", script_path(programme)]
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, NO_COLOR="1", LANG="fr_CA.UTF-8", NGINX_TOOLS_CONFIG_CREER="0",
                   NGINX_TOOLS_ETC_DEFAULT=tmp, HOME=tmp)
        env.pop("LC_ALL", None)
        return subprocess.run(exe + list(args), capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)


class MenuTousLesProgrammes(unittest.TestCase):
    def test_menu_dans_l_aide(self):
        for programme in PROGRAMMES:
            with self.subTest(programme=programme):
                r = lancer(programme, "--help")
                self.assertIn("--menu", r.stdout, r.stdout[:300])

    def test_menu_sans_terminal_refuse(self):
        for programme in PROGRAMMES:
            with self.subTest(programme=programme):
                r = lancer(programme, "--menu")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("--menu demande un terminal", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
