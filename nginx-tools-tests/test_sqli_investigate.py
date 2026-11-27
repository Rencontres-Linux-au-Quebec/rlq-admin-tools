"""sqli-investigate.py (0.1) : enquête en lecture seule sur les tentatives d'injection SQL des journaux nginx ; familles d'attaques, bannissements
fail2ban comparés aux réponses données ensuite, fichiers de résultats (droits 600 et 700), options, configuration, journal des modifications.
Les journaux de test utilisent les adresses de documentation (RFC 5737) : aucune adresse ni nom réel."""
import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest
import urllib.parse

from helpers import SCRIPTS_DIR

ENVIRONNEMENT = "commun"
PROGRAMME = "sqli-investigate.py"                           # nom du programme (lu par stats_runner)
SCRIPT = os.path.join(SCRIPTS_DIR, PROGRAMME)


def charger():
    spec = importlib.util.spec_from_file_location("sqli_investigate_t", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROG = charger()
ACCES = [
    '198.51.100.10 - - [26/Nov/2026:04:18:36 -0500] "GET /event/92/ics?action=1%27%20AND%201=1%20UNION%20SELECT%20NULL--%20-&text=5 HTTP/1.1" 200 5235 "-" "Agent A"',
    '198.51.100.10 - - [26/Nov/2026:04:18:39 -0500] "GET /event/92/ics?action=%27%29%20AND%20%28%27x%27%3D%27x%27%27&text=5 HTTP/1.1" 200 5235 "-" "Agent A"',
    '198.51.100.10 - - [26/Nov/2026:04:18:41 -0500] "GET /event/92/ics?action=TEMPLATE%27%20ORDER%20BY%201--%20-&text=5 HTTP/1.1" 200 5235 "-" "Agent B"',
    '198.51.100.10 - - [26/Nov/2026:04:18:51 -0500] "GET /event/92/ics?action=TEMPLATE%20AND%20EXTRACTVALUE%287838%2CCONCAT%280x7e%2C%28%28SELECT&text=5 HTTP/1.1" 200 5235 "-" "Agent C"',
    '198.51.100.10 - - [26/Nov/2026:04:19:22 -0500] "GET /event/92/ics?action=TEMPLATE%27%20UNION%20ALL%20SELECT%20%27azet&text=5 HTTP/1.1" 200 5235 "-" "Agent C"',
    '203.0.113.7 - - [26/Nov/2026:04:20:00 -0500] "GET /event/92/ics?action=TEMPLATE&text=5+%C3%A0+7+Trois-Rivi%C3%A8res HTTP/1.1" 200 5235 "-" "Agent D"',
    '203.0.113.7 - - [26/Nov/2026:04:20:08 -0500] "GET /event/92/ics?action=TEMPLATE%27%20ORDER%20BY%201000--%20-&dates=2026 HTTP/1.1" 404 146 "-" "Agent D"',
    '203.0.113.7 - - [26/Nov/2026:05:10:00 -0500] "GET /en_CA/event HTTP/1.1" 200 15000 "https://www.example.org/" "Agent E"',
]
F2B = [
    "2026-11-26 04:18:44,123 fail2ban.actions [1234]: NOTICE  [nginx-sqli] Ban 198.51.100.10",
    "2026-11-26 04:18:45,000 fail2ban.filter  [1234]: INFO    [sshd] Found 192.0.2.1",
    "2026-11-26 04:25:00,000 fail2ban.actions [1234]: NOTICE  [nginx-sqli] Unban 203.0.113.99",
]
ODOO = ["2026-11-26 04:18:50,100 1234 ERROR odoo18 odoo.sql_db: bad query", "2026-11-26 09:00:00,000 1234 INFO odoo18 odoo.http: fine"]


class Environnement(unittest.TestCase):
    """Dossiers temporaires : aucun fichier réel lu ni écrit (/etc/default, ~, /var/log)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-sqli-")
        self.env = dict(os.environ, NO_COLOR="1", TERM="dumb", HOME=os.path.join(self.tmp, "home"),
                        NGINX_TOOLS_ETC_DEFAULT=os.path.join(self.tmp, "etc"), NGINX_TOOLS_CONFIG_CREER="0", NGINX_TOOLS_LANG="fr")   # source in English: French display tested
        os.makedirs(os.path.join(self.tmp, "logs"))
        with open(os.path.join(self.tmp, "logs", "site-access.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(ACCES) + "\n")
        with open(os.path.join(self.tmp, "fail2ban.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(F2B) + "\n")
        with open(os.path.join(self.tmp, "odoo.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(ODOO) + "\n")

    def lancer(self, *args):
        r = subprocess.run(["python3", SCRIPT, *args], capture_output=True, text=True, timeout=120, env=self.env,
                           stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout, r.stderr

    def arguments_journaux(self, *extra):
        return ["--access-log", os.path.join(self.tmp, "logs", "*-access.log*"), "--fail2ban-log", os.path.join(self.tmp, "fail2ban.log"),
                "--no-lookup", *extra]

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class Familles(unittest.TestCase):
    """Chaque famille d'attaque est reconnue dans l'URL décodée ; une URL normale n'en déclenche aucune."""

    def familles(self, url):
        texte = urllib.parse.unquote_plus(url)
        return [nom for nom, rx in PROG.FAMILIES if rx.search(texte)]

    def test_familles_reconnues(self):
        cas = {
            "union": "/x?a=1%27%20UNION%20ALL%20SELECT%20NULL",
            "error": "/x?a=EXTRACTVALUE(1,CONCAT(0x7e,1))",
            "order-by": "/x?a=1%20ORDER%20BY%201000",
            "boolean": "/x?a=%27%29%20AND%20%281%3D1",
            "time": "/x?a=SLEEP(5)",
            "schema": "/x?a=information_schema.tables",
        }
        for famille, url in cas.items():
            with self.subTest(famille=famille):
                self.assertIn(famille, self.familles(url))

    def test_url_normale_sans_famille(self):
        self.assertEqual(self.familles("/event/92/ics?action=TEMPLATE&text=5+%C3%A0+7+Trois-Rivi%C3%A8res"), [])


class Analyse(unittest.TestCase):
    """Relecture des journaux : tentatives, réponses après un bannissement, erreurs Odoo proches."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-sqli-an-")
        self.journal = os.path.join(self.tmp, "site-access.log")
        with open(self.journal, "w", encoding="utf-8") as f:
            f.write("\n".join(ACCES) + "\n")
        with open(os.path.join(self.tmp, "odoo.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(ODOO) + "\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tentatives_et_reponses_apres_bannissement(self):
        avertissements = []
        f2b = os.path.join(self.tmp, "fail2ban.log")
        with open(f2b, "w", encoding="utf-8") as f:
            f.write("\n".join(F2B) + "\n")
        evenements = PROG.read_bans(f2b, "nginx-sqli", avertissements)
        self.assertEqual([(act, ip) for _, act, ip in evenements], [("Ban", "198.51.100.10"), ("Unban", "203.0.113.99")])
        tentatives, reponses = PROG.scan_access(os.path.join(self.tmp, "*-access.log*"), {"198.51.100.10"}, avertissements)
        self.assertEqual(len(tentatives), 6)       # two lines are normal pages
        self.assertEqual({t["ip"] for t in tentatives}, {"198.51.100.10", "203.0.113.7"})
        ban = evenements[0][0]
        apres = [s for ts, s in reponses["198.51.100.10"] if ts > ban]
        self.assertEqual(apres, [200, 200])        # the two requests after the ban of 04:18:44 (04:18:51 and 04:19:22)
        self.assertEqual(avertissements, [])

    def test_fenetres_de_bannissement_effectif(self):
        """Only the requests inside an effective ban count: a request after an Unban (or between two bans) is not a request under ban."""
        import datetime as dt
        def heure(h, m=0):
            return dt.datetime(2026, 11, 26, h, m, 0).astimezone()
        evenements = [(heure(1), "Ban", "198.51.100.10"), (heure(2), "Unban", "198.51.100.10"),
                      (heure(5), "Ban", "198.51.100.10"), (heure(6), "Ban", "198.51.100.10")]
        self.assertEqual(PROG.ban_windows(evenements),
                         [(heure(1), "198.51.100.10", heure(2)), (heure(5), "198.51.100.10", None)])
        reponses = {"198.51.100.10": [(heure(1, 30), 200), (heure(3), 200), (heure(5, 30), 404)]}
        lignes = PROG.build_summary([], reponses, PROG.ban_windows(evenements), {}, {}, None, 5, lambda c, t: t)
        self.assertIn("  198.51.100.10 banned at 2026-11-26 01:00:00: 1 request(s) during the ban, 1 with 2xx; ban ended: 2026-11-26 02:00:00",
                      lignes)
        self.assertIn("  198.51.100.10 banned at 2026-11-26 05:00:00: 1 request(s) during the ban, 0 with 2xx; ban ended: still active",
                      lignes)

    def test_fail2ban_absent_signale(self):
        avertissements = []
        self.assertEqual(PROG.read_bans(os.path.join(self.tmp, "absent*"), "nginx-sqli", avertissements), [])
        self.assertTrue(avertissements)

    def test_erreurs_odoo_proches(self):
        erreurs = PROG.read_odoo_errors(os.path.join(self.tmp, "odoo.log"), [])
        self.assertEqual(len(erreurs), 1)           # the INFO line is not an error
        tentative = {"time": PROG.parse_nginx_time("26/Nov/2026:04:18:36 -0500")}
        self.assertLessEqual(abs((erreurs[0] - tentative["time"]).total_seconds()), PROG.ODOO_WINDOW_S)

    def test_journal_absent_signale(self):
        avertissements = []
        PROG.scan_access(os.path.join(self.tmp, "introuvable*"), set(), avertissements)
        self.assertTrue(avertissements)


class Lecture(unittest.TestCase):
    """Le programme ne bannit, ne débanit et ne redémarre rien : seule la commande fail2ban-client status est lancée."""

    def test_aucune_commande_de_modification(self):
        with open(SCRIPT, encoding="utf-8") as f:
            source = f.read()
        self.assertIn('["fail2ban-client", "status", jail]', source)
        for interdit in ('"ban"', '"unban"', '"systemctl"', '"nginx", "-s"', '"reload"', '"restart"'):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, source)


class Execution(Environnement):
    """Lancements complets : sorties, droits, options, configuration, aide triée."""

    def test_premiere_ligne_et_resultats(self):
        code, sortie, erreur = self.lancer(*self.arguments_journaux("--output", os.path.join(self.tmp, "out")))
        self.assertEqual(code, 0, erreur)
        self.assertTrue(sortie.startswith(f"{PROGRAMME[:-3]}.py v"))
        self.assertIn("Tentatives : 6", sortie)
        self.assertIn("banni à 2026-11-26 04:18:44: 2 requête(s) pendant le bannissement, 2 en 2xx", sortie)
        dossier = os.path.join(self.tmp, "out")
        self.assertEqual(stat.S_IMODE(os.stat(dossier).st_mode), 0o700)
        for nom in ("sqli-requests.tsv", "sqli-summary.txt", "sqli-bans.txt"):
            with self.subTest(fichier=nom):
                self.assertEqual(stat.S_IMODE(os.stat(os.path.join(dossier, nom)).st_mode), 0o600)
        with open(os.path.join(dossier, "sqli-requests.tsv"), encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()), 1 + 6)

    def test_top_invalide_refuse(self):
        code, _, erreur = self.lancer(*self.arguments_journaux("--top", "0", "--output", os.path.join(self.tmp, "out")))
        self.assertEqual(code, 2)
        self.assertIn("--top", erreur)

    def test_config_explicite_absente(self):
        code, _, erreur = self.lancer("-c", os.path.join(self.tmp, "absent.conf"))
        self.assertEqual(code, 2)
        self.assertIn("introuvable", erreur)

    def test_configuration_lue_et_affichee(self):
        conf = os.path.join(self.tmp, "perso.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write("ACCESS_LOG=%s\nFAIL2BAN_LOG=%s\nNO_LOOKUP=yes\nTOP=3\n" % (os.path.join(self.tmp, "logs", "*-access.log*"),
                                                                              os.path.join(self.tmp, "fail2ban.log")))
        code, sortie, erreur = self.lancer("-c", conf, "--output", os.path.join(self.tmp, "out"))
        self.assertEqual(code, 0, erreur)
        self.assertIn("Configuration lue : " + conf, sortie)
        self.assertIn("sans recherche DNS", sortie)

    def test_changelog_section_du_programme(self):
        code, sortie, _ = self.lancer("--changelog")
        self.assertEqual(code, 0)
        self.assertIn("0.1.", sortie)
        self.assertIn("READ-ONLY investigation", sortie)

    def test_version_une_seule_ligne(self):
        code, sortie, _ = self.lancer("--version")
        self.assertEqual(code, 0)
        self.assertEqual(len([l for l in sortie.splitlines() if l.strip()]), 1)

    def test_aide_options_triees(self):
        code, sortie, _ = self.lancer("--help")
        self.assertEqual(code, 0)
        longues = []
        for ligne in sortie.splitlines():
            for morceau in ligne.strip().split():
                if morceau.startswith("--"):
                    longues.append(morceau.rstrip(",").lstrip("-"))
                    break
        self.assertGreater(len(longues), 5)
        self.assertEqual(longues, sorted(longues), "options de l'aide non triées par ordre alphabétique")


if __name__ == "__main__":
    unittest.main()
