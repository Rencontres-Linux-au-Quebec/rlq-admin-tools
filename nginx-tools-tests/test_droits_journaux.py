"""nginx-tools 1.102 : root exigé AU DÉBUT par les programmes qui en ont besoin, avis pour ceux qui voient moins sans root ; LOG_KEEP_DAYS du fichier commun (durée de conservation des journaux)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"
import importlib.util
import os
import shutil
import subprocess
import unittest
from unittest import mock

from helpers import EnvTest, SCRIPTS_DIR


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(SCRIPTS_DIR, "apps", nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RootEtAvis(unittest.TestCase):
    def test_refus_seulement_sans_root_et_jamais_pour_l_aide(self):
        c = charger("_config")
        with mock.patch("os.geteuid", return_value=1000):
            self.assertIn("doit être lancé en root", c.refus_non_root("prog.py", "PostgreSQL", ["--x"]))
            self.assertIn("PostgreSQL", c.refus_non_root("prog.py", "PostgreSQL", []))
            for a in ("--help", "-h", "--version", "--changelog"):
                self.assertIsNone(c.refus_non_root("prog.py", "PostgreSQL", [a]))
        with mock.patch("os.geteuid", return_value=0):
            self.assertIsNone(c.refus_non_root("prog.py", "PostgreSQL", []))

    def test_avis_sans_root_et_desactivable(self):
        c = charger("_config")
        with mock.patch("os.geteuid", return_value=1000), mock.patch.dict(os.environ, {"NGINX_TOOLS_AVIS_ROOT": "1"}):
            self.assertIn("Droits limités (pas root) : fail2ban", c.avis_non_root("prog.py", "fail2ban", []))
            self.assertIsNone(c.avis_non_root("prog.py", "fail2ban", ["--version"]))
        with mock.patch("os.geteuid", return_value=1000), mock.patch.dict(os.environ, {"NGINX_TOOLS_AVIS_ROOT": "0"}):
            self.assertIsNone(c.avis_non_root("prog.py", "fail2ban", []))
        with mock.patch("os.geteuid", return_value=0):
            self.assertIsNone(c.avis_non_root("prog.py", "fail2ban", []))


class DureeDesJournaux(EnvTest):
    def test_cle_du_fichier_commun_exportee_et_defaut_180(self):
        c = charger("_config")
        etc = os.path.join(self.d, "etc")
        os.makedirs(etc)
        self.write("etc/app-default.conf", "LOG_KEEP_DAYS=400\n")
        with mock.patch.dict(os.environ, {"NGINX_TOOLS_ETC_DEFAULT": etc, "NGINX_TOOLS_CONFIG_CREER": "0", "HOME": self.d}):
            os.environ.pop("NGINX_TOOLS_LOG_KEEP_DAYS", None)
            self.assertEqual(c.jours_journaux(), 180)
            cfg, fichiers = c.lire("prog")
            self.assertEqual(cfg.get("LOG_KEEP_DAYS"), "400")
            self.assertEqual(c.jours_journaux(), 400)
            os.environ["NGINX_TOOLS_LOG_KEEP_DAYS"] = "0"
            self.assertEqual(c.jours_journaux(), 0)
            os.environ["NGINX_TOOLS_LOG_KEEP_DAYS"] = "abc"
            self.assertEqual(c.jours_journaux(), 180)

    def test_bash_exporte_la_duree(self):
        etc = os.path.join(self.d, "etc")
        os.makedirs(etc)
        self.write("etc/app-default.conf", "LOG_KEEP_DAYS=365\n")
        env = dict(os.environ, NGINX_TOOLS_ETC_DEFAULT=etc, NGINX_TOOLS_CONFIG_CREER="0", HOME=self.d)
        env.pop("NGINX_TOOLS_LOG_KEEP_DAYS", None)
        r = subprocess.run(["bash", "-c", f'. "{SCRIPTS_DIR}/apps/_i18n.sh"; config_lire prog; echo "[$NGINX_TOOLS_LOG_KEEP_DAYS]"'], capture_output=True, text=True, env=env)
        self.assertIn("[365]", r.stdout, r.stderr)

    def test_exemple_documente_la_cle(self):
        with open(os.path.join(SCRIPTS_DIR, "doc", "app-default.conf.example"), encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("#LOG_KEEP_DAYS=180", texte)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which("setpriv"), "root et setpriv requis pour simuler un utilisateur ordinaire")
class SansRoot(EnvTest):
    def lancer(self, *cmd):
        os.chmod(self.d, 0o755)
        return subprocess.run(["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups"] + list(cmd), capture_output=True, text=True, timeout=60,
                              env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "NGINX_TOOLS_CONFIG_CREER": "0", "NGINX_TOOLS_LANG": "fr"}, cwd="/")

    def test_odoo_mail_retry_refuse_des_le_debut(self):
        r = self.lancer("python3", os.path.join(SCRIPTS_DIR, "odoo-mail-retry.py"), "--sent", "3")
        if "Permission denied" in r.stderr or "Permission non accordée" in r.stderr:
            self.skipTest("programme illisible pour l'utilisateur nobody")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("doit être lancé en root", r.stderr)

    def test_web_monitor_refuse_ce_qui_modifie_mais_pas_status(self):
        r = self.lancer("python3", os.path.join(SCRIPTS_DIR, "web-monitor.py"), "--install-timer")
        if "Permission" in r.stderr:
            self.skipTest("programme illisible pour l'utilisateur nobody")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("root requis (sudo) pour modifier", r.stderr)

    def test_aide_et_version_sans_avis(self):
        r = self.lancer("python3", os.path.join(SCRIPTS_DIR, "app-log-live.py"), "--version")
        if "Permission" in r.stderr:
            self.skipTest("programme illisible pour l'utilisateur nobody")
        self.assertNotIn("Droits limités", r.stderr)
