"""_logs_merge.py (apps/) and app-log-live.py --logs-nginx: nginx lines merged in time order, with the journal prefix of the application."""
import datetime
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)

from helpers import EnvTest, script_path

FUSEAU = datetime.timezone(datetime.timedelta(hours=-4))
MERGE = os.path.join(os.path.dirname(script_path("app-log-live.py")), "apps", "_logs_merge.py")
PREFIXE_JOURNAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}[+-]\d{4} \S+ \S+: ")


def acces(heure, texte="GET /web HTTP/1.1"):
    """Ligne du journal d'accès nginx à 2026-10-29 HEURE (heure locale -0400)."""
    return f'1.2.3.4 - - [29/Oct/2026:{heure} -0400] "{texte}" 200 10 "-" "Mozilla" host="odoo.exemple"\n'


def erreur(heure, texte="[error] 123#0: *5 open() failed"):
    """Ligne du journal d'erreurs nginx (heure locale du serveur, sans décalage)."""
    return f"2026/10/29 {heure} {texte}\n"


def application(heure, message):
    """Ligne « journalctl -o short-iso-precise » d'Odoo à 2026-10-29 HEURE (-0400)."""
    fraction = "" if "." in heure else ".000000"
    return f"2026-10-29T{heure}{fraction}-0400 odoo[1]: {message}\n"


class LogsMergeTest(EnvTest):
    def setUp(self):
        super().setUp()
        self.dossier = tempfile.mkdtemp(prefix="test-rlq-merge-")
        self.acces = os.path.join(self.dossier, "site-access.log")
        self.erreurs = os.path.join(self.dossier, "site-error.log")
        self.app = os.path.join(self.dossier, "app.txt")

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)
        super().tearDown()

    def ecrire(self, chemin, lignes):
        with open(chemin, "w", encoding="utf-8") as f:
            f.writelines(lignes)

    def fusion(self, *arguments):
        """Lance _logs_merge.py ; la commande de l'application est « cat app.txt » (le flux est déjà horodaté)."""
        cmd = [sys.executable, MERGE] + list(arguments)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_ordre_chronologique_des_deux_flux(self):
        self.ecrire(self.acces, [acces("10:00:01"), acces("10:00:09", "GET /.env HTTP/1.1")])
        self.ecrire(self.erreurs, [erreur("10:00:06")])
        self.ecrire(self.app, [application("10:00:00.500", "premiere"), application("10:00:07", "ERROR base boom"),
                               application("10:00:10", "derniere")])
        lignes = self.fusion("--no-follow", "--nginx", self.acces, self.erreurs, "--", "cat", self.app)
        heures = [re.search(r"T(\d{2}:\d{2}:\d{2})", l).group(1) for l in lignes]
        self.assertEqual(heures, sorted(heures))
        self.assertEqual(len(lignes), 6)                                      # 2 accès, 1 erreur, 3 lignes d'Odoo
        self.assertIn("premiere", lignes[0])
        self.assertIn("derniere", lignes[-1])

    def test_prefixe_identique_a_celui_du_journal(self):
        self.ecrire(self.acces, [acces("10:00:01")])
        self.ecrire(self.app, [])
        lignes = self.fusion("--no-follow", "--nginx", self.acces, "--", "cat", self.app)
        self.assertEqual(len(lignes), 1)
        self.assertRegex(lignes[0], PREFIXE_JOURNAL)
        self.assertIn(" nginx: ", lignes[0])
        # la date de la requête est dans le préfixe : elle n'est plus répétée dans le texte
        self.assertNotIn("[29/Oct/2026", lignes[0])
        self.assertIn('1.2.3.4 - - "GET /web HTTP/1.1" 200', lignes[0])

    def test_heure_locale_avec_le_decalage_du_journal(self):
        self.ecrire(self.acces, [acces("10:00:01")])
        self.ecrire(self.app, [])
        lignes = self.fusion("--no-follow", "--nginx", self.acces, "--", "cat", self.app)
        attendu = datetime.datetime(2026, 10, 29, 10, 0, 1, tzinfo=FUSEAU).astimezone().replace(tzinfo=None)   # heure locale de cette machine
        self.assertEqual(datetime.datetime.strptime(lignes[0][:26], "%Y-%m-%dT%H:%M:%S.%f"), attendu)

    def test_erreur_nginx_sans_date_repetee(self):
        self.ecrire(self.erreurs, [erreur("10:00:06")])
        self.ecrire(self.app, [])
        lignes = self.fusion("--no-follow", "--nginx", self.erreurs, "--", "cat", self.app)
        self.assertRegex(lignes[0], PREFIXE_JOURNAL)
        self.assertTrue(lignes[0].endswith("[error] 123#0: *5 open() failed"), lignes[0])

    def test_filtres_grep_since_until_ne_touchent_que_nginx(self):
        self.ecrire(self.acces, [acces("10:00:01"), acces("10:00:09", "GET /.env HTTP/1.1")])
        self.ecrire(self.app, [application("10:00:05", "message odoo")])
        lignes = self.fusion("--no-follow", "--grep", r"\.env", "--nginx", self.acces, "--", "cat", self.app)
        self.assertEqual(len(lignes), 2)                                       # le message d'Odoo n'est pas filtré
        self.assertIn("message odoo", lignes[0])
        self.assertIn("/.env", lignes[1])
        debut = datetime.datetime(2026, 10, 29, 10, 0, 5, tzinfo=FUSEAU).timestamp()
        lignes = self.fusion("--no-follow", "--since", str(debut), "--nginx", self.acces, "--", "cat", self.app)
        self.assertEqual([l for l in lignes if "nginx:" in l], [lignes[-1]])   # seule la ligne de 10:00:09 reste

    def test_ligne_sans_horodatage_suit_son_flux(self):
        self.ecrire(self.app, [application("10:00:05", "Traceback (most recent call last):"),
                               "  File \"x.py\", line 1\n", application("10:00:08", "fin")])
        lignes = self.fusion("--no-follow", "--", "cat", self.app)
        self.assertEqual(len(lignes), 3)
        self.assertTrue(lignes[1].startswith("  File"))                      # sans préfixe : gardée telle quelle, à sa place

    def test_version_dynamique(self):
        result = subprocess.run([sys.executable, MERGE, "--version"], stdout=subprocess.PIPE, universal_newlines=True, timeout=30)
        with open(MERGE, encoding="utf-8") as f:
            version = re.search(r'__version__ = "([^"]+)"', f.read()).group(1)
        self.assertIn(version, result.stdout)

    def test_app_log_live_construit_la_fusion(self):
        """--logs-nginx : la commande du flux est celle du fusionneur (journalctl ou convertisseur après « -- »)."""
        spec = importlib.util.spec_from_file_location("live_logs", script_path("app-log-live.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as nginx_dir:
            open(os.path.join(nginx_dir, "site-access.log"), "w").close()
            open(os.path.join(nginx_dir, "site-error.log"), "w").close()
            module.NGINX_DIR = nginx_dir
            profil = {"APP_LOG_KIND": "journal", "ACCESS_LOGS": "*-access.log", "ERROR_LOGS": "*-error.log"}
            args = type("A", (), {"lines": 20, "no_follow": True, "logs_nginx": True, "since_epoch": None,
                                  "until_epoch": None, "grep": None, "grep_sensitive": False, "since": None, "until": None})()
            cmd = module.stream_command(args, profil, "odoo.service", None)
            self.assertIn(module.LOGS_MERGE, cmd)
            self.assertIn("--no-follow", cmd)
            self.assertIn("--", cmd)
            self.assertEqual(cmd[cmd.index("--") + 1], "journalctl")
            self.assertEqual(sorted(os.path.basename(f) for f in cmd[cmd.index("--nginx") + 1:cmd.index("--")]),
                             ["site-access.log", "site-error.log"])
            args.logs_nginx = False
            self.assertEqual(module.stream_command(args, profil, "odoo.service", None)[0], "journalctl")


if __name__ == "__main__":
    unittest.main()
