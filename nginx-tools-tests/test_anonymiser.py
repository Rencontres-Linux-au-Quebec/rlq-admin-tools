# -*- coding: utf-8 -*-
"""--anonymize : pseudonymes stables des IP, courriels, identifiants et jetons dans ce qu'affichent TOUS les programmes (apps/_anonymiser.py + filtre apps/_traduire.py)."""
import importlib.util
import os
import shutil
import stat
import subprocess
import unittest

from helpers import EnvTest, SCRIPTS_DIR, script_path

ENVIRONNEMENT = "commun"
PROGRAMMES_PYTHON = ("app-health-check", "app-log-check", "app-log-live", "odoo-chat-post", "odoo-docs", "odoo-mail-retry", "odoo-warmup", "web-monitor", "zip-versions", "host-perf-audit")
PROGRAMMES_BASH = ("nginx-hardening", "nginx-log-audit", "odoo-backup", "odoo-update-module", "sync-crowdsec-blocklist")


def charger():
    spec = importlib.util.spec_from_file_location("anon_t", script_path("apps/_anonymiser.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Motifs(unittest.TestCase):
    def setUp(self):
        self.m = charger()
        self.f = self.m.Anonymiseur(b"sel-de-test")

    def test_adresses_ip_v4_et_v6_stables(self):
        a = self.f("11.97.88.222 puis 11.97.88.222 et 11.26.17.163")
        ips = a.split()
        self.assertTrue(ips[0].startswith("IP-") and ips[0] == ips[2])               # même adresse : même pseudonyme
        self.assertNotEqual(ips[0], ips[4])
        self.assertNotIn("69.157", a)
        v6 = self.f("client 2001:db8::1 vu")
        self.assertRegex(v6, r"client IP-[0-9a-f]{6} vu")
        self.assertEqual(self.m.Anonymiseur(b"sel-de-test")("11.97.88.222"), self.f("11.97.88.222"))      # stable d'une exécution à l'autre (même sel)
        self.assertNotEqual(self.m.Anonymiseur(b"autre-sel")("11.97.88.222"), self.f("11.97.88.222"))

    def test_ce_qui_n_est_pas_une_personne_reste_intact(self):
        for texte in ("127.0.0.1:8069", "0.0.0.0", "::1", "masque 255.255.255.0", "Odoo 18.0.1.3", "rlq_survey_report.18.0.1.90.0.zip", "version 1.108.20261015.095427",
                      "heure 10:29:30", "mac aa:bb:cc:dd:ee:ff", "5 parties 1.2.3.4.5"):
            with self.subTest(texte=texte):
                self.assertEqual(self.f(texte), texte)

    def test_courriels_et_identifiants(self):
        a = self.f("de etienne.berube.ing@exemple.org et Etienne.Berube.ing@exemple.org, url ?login=marc%40ex.org")
        self.assertNotIn("gmail", a)
        self.assertNotIn("ex.org", a)
        self.assertEqual(a.split()[1], a.split()[3].rstrip(","))                      # casse ignorée : même courriel, même pseudonyme
        self.assertRegex(a, r"usager-[0-9a-f]{6}@anonyme\.invalid")
        b = self.f("Options : --login alertes · --bot-login tux-bot · LOGIN=alertes · user=jean")
        for nom in ("alertes", "tux-bot", "jean"):
            self.assertNotIn(nom, b)
        self.assertEqual(b.count("ID-"), 4)
        self.assertEqual(b.split("--login ")[1].split()[0], b.split("LOGIN=")[1].split()[0])

    def test_jetons_mots_de_passe_et_cookies(self):
        texte = 'GET /x?token=abc123&session_id=ff00&name=Jean+Dupont\nAuthorization: Bearer eyJhbGci.xyz\nCookie: session_id=abc; a=b\nAPI_KEY=secret1 password: "pa ss"'
        a = self.f(texte)
        for secret in ("abc123", "ff00", "Jean", "eyJhbGci", "abc;", "secret1", "pa ss"):
            self.assertNotIn(secret, a)
        self.assertIn("token=***", a)
        self.assertIn("Bearer ***", a)
        self.assertIn("Cookie: ***", a)

    def test_idempotent(self):
        a = self.f("1.2.3.4 a@b.org --login x token=y 2001:db8::5")
        self.assertEqual(self.f(a), a)

    def test_demande(self):
        d = self.m.demande
        self.assertTrue(d(["--anonymize"], {}, env={}, terminal=False))
        self.assertTrue(d(["--anon"], {}, env={}, terminal=False))                      # abréviation acceptée par argparse
        self.assertFalse(d(["--anonymize", "--help"], {}, env={}))
        self.assertFalse(d(["--anonymize"], {}, env={self.m.ACTIF_ENV: "1"}))             # déjà derrière le filtre
        self.assertTrue(d([], {"ANONYMIZE": "oui"}, env={}, terminal=True))
        self.assertFalse(d([], {"ANONYMIZE": "oui"}, env={}, terminal=False))             # configuration : seulement au terminal
        self.assertTrue(d([], {}, env={"NGINX_TOOLS_ANONYMIZE": "1"}, terminal=False))      # cron : variable
        self.assertFalse(d([], {"ANONYMIZE": "oui"}, env={"NGINX_TOOLS_ANONYMIZE": "0"}, terminal=True))
        self.assertEqual(self.m.sans_option(["a", "--anonymize", "--anon", "b"]), ["a", "b"])


class Executions(EnvTest):
    def lancer(self, *cmd, entree=None, env=None):
        e = dict(os.environ, NGINX_TOOLS_ETC_DEFAULT=os.path.join(self.d, "etc"), HOME=os.path.join(self.d, "home"), NGINX_TOOLS_CONFIG_CREER="0", NGINX_TOOLS_AVIS_ROOT="0",
                 NGINX_TOOLS_ANON_SEL="sel-de-test", NGINX_TOOLS_LANG="fr")
        for v in ("NGINX_TOOLS_ANON_ACTIF", "NGINX_TOOLS_ANONYMIZE"):
            e.pop(v, None)
        e.update(env or {})
        os.makedirs(e["NGINX_TOOLS_ETC_DEFAULT"], exist_ok=True)
        os.makedirs(e["HOME"], exist_ok=True)
        return subprocess.run(list(cmd), capture_output=True, text=True, input=entree, env=e, timeout=120)

    def test_filtre_en_ligne_de_commande(self):
        r = self.lancer("python3", script_path("apps/_anonymiser.py"), entree="vu 203.0.113.9 par a@b.org\n127.0.0.1\n")
        self.assertRegex(r.stdout, r"^vu IP-[0-9a-f]{6} par usager-[0-9a-f]{6}@anonyme\.invalid\n127\.0\.0\.1\n$")
        r = self.lancer("python3", script_path("apps/_anonymiser.py"), "--pseudonyme", "203.0.113.9", "alertes")
        self.assertRegex(r.stdout, r"203\.0\.113\.9 -> IP-[0-9a-f]{6}\nalertes -> ID-[0-9a-f]{6}\n")

    def test_sel_cree_en_600_et_reutilise(self):
        env = {"NGINX_TOOLS_ANON_SEL": ""}
        a = self.lancer("python3", script_path("apps/_anonymiser.py"), "--pseudonyme", "203.0.113.9", env=env).stdout
        sel = os.path.join(self.d, "etc", "nginx-tools-anon.salt")
        self.assertTrue(os.path.isfile(sel))
        self.assertEqual(stat.S_IMODE(os.stat(sel).st_mode), 0o600)
        self.assertEqual(self.lancer("python3", script_path("apps/_anonymiser.py"), "--pseudonyme", "203.0.113.9", env=env).stdout, a)
        os.remove(sel)
        self.assertNotEqual(self.lancer("python3", script_path("apps/_anonymiser.py"), "--pseudonyme", "203.0.113.9", env=env).stdout, a)       # nouveau sel : nouveaux pseudonymes

    def _conf_canaux(self, extra=""):
        with open(os.path.join(self.d, "etc", "odoo-chat-post.conf"), "w", encoding="utf-8") as f:
            f.write(f"URL=http://127.0.0.1:9\nDB=rlq\nLOGIN=marc.tremblay@exemple.org\n{extra}")

    def test_programme_python_avec_l_option(self):
        os.makedirs(os.path.join(self.d, "etc"), exist_ok=True)
        self._conf_canaux()
        clair = self.lancer("python3", script_path("odoo-chat-post.py"), "--list")
        self.assertIn("marc.tremblay@exemple.org", clair.stdout)                           # sans l'option : rien ne change
        r = self.lancer("python3", script_path("odoo-chat-post.py"), "--anonymize", "--list")
        self.assertNotIn("marc.tremblay", r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"usager-[0-9a-f]{6}@anonyme\.invalid")
        self.assertEqual(r.returncode, clair.returncode)                                   # code de retour conservé
        r2 = self.lancer("python3", script_path("odoo-chat-post.py"), "--list", env={"NGINX_TOOLS_ANONYMIZE": "1"})
        self.assertNotIn("marc.tremblay", r2.stdout)

    def test_configuration_seulement_au_terminal(self):
        os.makedirs(os.path.join(self.d, "etc"), exist_ok=True)
        self._conf_canaux("ANONYMIZE=oui\n")
        r = self.lancer("python3", script_path("odoo-chat-post.py"), "--list")                  # sortie capturée (tube) : pas de modification du texte
        self.assertIn("marc.tremblay@exemple.org", r.stdout)

    def test_aucun_double_filtre_pour_les_programmes_lances(self):
        r = self.lancer("python3", script_path("apps/_traduire.py"), "--anonymiser-seul", "--", "bash", "-c", 'echo "$NGINX_TOOLS_ANON_ACTIF 1.2.3.4"; echo 5.6.7.8 >&2')
        self.assertRegex(r.stdout, r"^1 IP-[0-9a-f]{6}\n$")
        self.assertRegex(r.stderr, r"^IP-[0-9a-f]{6}\n$")

    def test_programme_bash_option_retiree_et_sortie_filtree(self):
        faux = os.path.join(self.d, "faux.sh")
        with open(faux, "w", encoding="utf-8") as f:
            f.write('echo "arguments : $# [$*]"; echo "client 1.2.3.4 a@b.org"\nexit 3\n')
        r = self.lancer("python3", script_path("apps/_traduire.py"), "faux-prog", "FAUX_LANG", "--", "bash", faux, "--anonymize", "x")
        self.assertIn("arguments : 1 [x]", r.stdout)                                      # --anonymize n'arrive pas au script bash
        self.assertNotIn("1.2.3.4", r.stdout)
        self.assertNotIn("a@b.org", r.stdout)
        self.assertEqual(r.returncode, 3)

    def test_demande_sans_filtre_disponible_refus_net(self):
        copie = os.path.join(self.d, "copie")
        shutil.copytree(SCRIPTS_DIR, copie, ignore=shutil.ignore_patterns("__pycache__", "nginx-tools-tests", "*.zip"))
        os.remove(os.path.join(copie, "apps", "_traduire.py"))
        os.makedirs(os.path.join(self.d, "etc"), exist_ok=True)
        self._conf_canaux()
        r = self.lancer("python3", os.path.join(copie, "odoo-chat-post.py"), "--anonymize", "--list")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("introuvable", r.stderr)
        self.assertNotIn("marc.tremblay", r.stdout)                                        # jamais de données en clair quand l'anonymisation est demandée

    def test_option_dans_l_aide_de_chaque_programme(self):
        for nom in PROGRAMMES_PYTHON:
            with self.subTest(programme=nom):
                r = self.lancer("python3", script_path(nom + ".py"), "--help")
                self.assertIn("--anonymize", r.stdout)
        for nom in PROGRAMMES_BASH:
            with self.subTest(programme=nom):
                r = self.lancer("bash", script_path(nom + ".sh"), "--help")
                self.assertIn("--anonymize", r.stdout)


if __name__ == "__main__":
    unittest.main()
