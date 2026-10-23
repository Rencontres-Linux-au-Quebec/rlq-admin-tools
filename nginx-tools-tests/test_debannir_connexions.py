"""web-monitor.py 2.59 : IP bannies qui semblent valides (à débannir), colonnes, unités en anglais ; apps/_connexions.py : limites de connexions (chat d'Odoo, PostgreSQL, nginx)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"
import datetime
import importlib.util
import os
import re

from helpers import EnvTest, SCRIPTS_DIR
import test_web_monitor


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(SCRIPTS_DIR, "apps", nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IpAdebannir(test_web_monitor.Bilan):
    def setUp(self):
        super().setUp()
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        A = lambda ip, m, u, c: f'{ip} - - [{T:%d}/{mois[T.month - 1]}/{T:%Y}:10:00:00 -0400] "{m} {u} HTTP/1.1" {c} 100 "-" "Mozilla/5.0"\n'
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines([A("10.0.0.20", "GET", "/a", 200), A("10.0.0.20", "GET", "/b", 200), A("10.0.0.20", "GET", "/web/assets/y.js", 200)])
        with open(self.path("journal.txt"), "a") as f:
            f.write(f"{T.isoformat()}T03:00:00-0400 odoo18 odoo[1]: {T.isoformat()} 07:00:00,000 1 INFO db odoo.addons.base.models.res_users: "
                    "Login successful for db:x login:membre@example.com from 10.0.0.1\n")
        self.mock("fail2ban-client", '''if [[ "$2" == nginx-catchall ]]; then echo "Status for the jail: nginx-catchall"; echo "   |- Currently banned: 3"
echo "   \\`- Banned IP list:	10.0.0.1 10.0.0.4 10.0.0.20"; else echo "Status"; echo "|- Number of jail:	1"; echo "\\`- Jail list:	nginx-catchall"; fi''')

    def test_ip_valides_bannies_listees_avec_la_commande(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--lang", "fr"])
        self.assertEqual(rc, 0, err)
        section = out.split("IP BANNIES QUI SEMBLENT VALIDES")[1].split("RECOMMANDATIONS")[0]
        self.assertRegex(section, r"10\.0\.0\.1\s+certaine\s+utilisateur connu")
        self.assertRegex(section, r"10\.0\.0\.20\s+probable\s+visiteur humain probable : 2 page")
        self.assertNotIn("10.0.0.4", section)                                  # requested /.env: rightly banned
        self.assertIn("fail2ban-client set nginx-catchall unbanip 10.0.0.1", section)
        self.assertIn("Débannir 2 IP valide(s)", out)
        self.assertIn("2 IP bannie(s) semblent valides (1 certaine(s)", out)

    def test_section_en_anglais_sans_francais_ni_unites_francaises(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--lang", "en"])
        self.assertEqual(rc, 0, err)
        self.assertIn("BANNED IPs THAT LOOK VALID (to unban)", out)
        self.assertIn("Unban 2 valid IP(s)", out)
        self.assertNotRegex(out, r"\d (Ko|Mo|Go|o)\b")                         # units: KB, MB, GB, B
        self.assertNotRegex(out, r"\[(MOYENNE|FAIBLE)\]")
        self.assertNotIn("semblent", out)
        self.assertNotIn("HAUTE", out)
        self.assertNotRegex(out, r"\d,\d+ (KB|MB|GB)")                         # decimal comma: point in English

    def test_colonne_sept_jours_supprimee_quand_la_periode_est_courte(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--days", "5", "--lang", "en"])
        entete = next(l for l in out.splitlines() if "Today" in l and "J-1" in l)
        self.assertNotIn("7 days", entete)
        self.assertIn("5 days", entete)

    def test_entetes_des_colonnes_au_dessus_des_chiffres_en_francais_et_en_anglais(self):
        """2.59 : chaque étiquette de période commence au-dessus de ses chiffres (plus de décalage de 8 caractères ni de « 30 day » coupé)."""
        for langue, aujourdhui in (("fr", "Aujourd'hui"), ("en", "Today")):
            with self.subTest(langue=langue):
                rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--lang", langue])
                lignes = out.splitlines()
                entete = next(l for l in lignes if aujourdhui in l and "J-1" in l)
                debuts = [m.start() for m in re.finditer(r"\S+(?: \S+)?\*?", entete.strip())]
                debuts = [d + len(entete) - len(entete.lstrip()) for d in debuts]
                self.assertEqual(len(debuts), 5, entete)
                ligne = next(l for l in lignes if l.lstrip().startswith(("Requêtes sur le site", "Requests on the site")))
                nombres = [(m.start(), m.end()) for m in re.finditer(r"\d+", ligne[45:])]
                nombres = [(a + 45, b + 45) for a, b in nombres][:5]
                for (debut_e, fin_e), (a, b) in zip(zip(debuts, debuts[1:] + [10 ** 6]), nombres):
                    self.assertGreaterEqual(a, debut_e - 0, ligne)             # the number starts under the label or to its right
                    self.assertLess(b, fin_e + 1, ligne)                        # and ends before the next label
                self.assertNotIn("30 day ", entete + " ")

    def test_url_inoffensive_refusee_n_est_pas_malveillante(self):
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        ligne = lambda u: f'8.8.8.8 - - [{T:%d}/{mois[T.month - 1]}/{T:%Y}:10:00:00 -0400] "GET {u} HTTP/1.1" 403 100 "-" "Mozilla/5.0" host="x"\n'
        self.write("nginx/blocked-probes.log", ligne("/robots.txt") + ligne("/.well-known/assetlinks.json") + ligne("/.env"))
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--lang", "fr"])
        malveillantes = next(l for l in out.splitlines() if l.strip().startswith("URL malveillantes"))
        self.assertIn("/.env", malveillantes)
        self.assertNotIn("robots.txt", malveillantes)
        self.assertNotIn("assetlinks", malveillantes)


for _nom in [n for n in dir(test_web_monitor.Bilan) if n.startswith("test") and n not in IpAdebannir.__dict__]:
    setattr(IpAdebannir, _nom, None)             # the tests inherited from Bilan run in test_web_monitor (here the data set is completed)


class Connexions(EnvTest):
    def setUp(self):
        super().setUp()
        self.c = charger("_connexions")

    def mesures(self, **v):
        base = {"http_port": "8069", "gevent_port": "8072", "workers": 13, "crons": 2, "db_maxconn": 64, "db_maxconn_gevent": 0,
                "websockets": 40, "http": 10, "nginx_clients": 100, "fd_gevent": (100, 1024), "fd_http": (200, 1024), "postgres": (20, 100), "worker_connections": 512}
        base.update(v)
        return base

    def test_rien_sous_le_seuil(self):
        self.assertEqual(self.c.diagnostiquer(self.mesures()), [])

    def test_chat_websocket_proche_de_la_limite_de_descripteurs(self):
        r = self.c.diagnostiquer(self.mesures(fd_gevent=(900, 1024), websockets=850), service="erplibre.service")
        self.assertEqual(len(r), 1)
        niveau, constat, conseil = r[0]
        self.assertEqual(niveau, "warn")
        self.assertIn("850 connexion(s) établie(s)", constat)
        self.assertIn("LimitNOFILE=65535", conseil)
        self.assertIn("systemctl edit erplibre.service", conseil)
        self.assertEqual(self.c.diagnostiquer(self.mesures(fd_gevent=(1000, 1024)))[0][0], "crit")

    def test_postgresql_et_parametres_d_odoo(self):
        r = self.c.diagnostiquer(self.mesures(postgres=(90, 100)))
        textes = " ".join(c + " " + p for _, c, p in r)
        self.assertIn("90 connexions sur max_connections = 100", textes)
        self.assertIn("max_connections", textes)
        self.assertIn("db_maxconn", textes)
        self.assertIn("db_maxconn_gevent", textes)
        self.assertTrue(any("peut ouvrir jusqu'à 1024 connexions" in c for _, c, _ in r))      # (13 + 2 + 1) x 64

    def test_nginx_worker_connections_et_seuil_personnalise(self):
        r = self.c.diagnostiquer(self.mesures(nginx_clients=450))
        self.assertIn("worker_connections 4096", r[0][2])
        self.assertEqual(self.c.diagnostiquer(self.mesures(nginx_clients=300), seuil=50)[0][0], "warn")      # 300/512 = 59 % >= 50 %

    def test_mesure_impossible_ignoree_et_resume(self):
        m = self.mesures(fd_gevent=None, fd_http=None, postgres=None, worker_connections=None, websockets=None, http=None)
        self.assertEqual(self.c.diagnostiquer(m), [])
        self.assertEqual(self.c.resume(m), "")
        self.assertIn("chat (websocket, port 8072) : 40", self.c.resume(self.mesures()))
        self.assertIn("PostgreSQL : 20/100", self.c.resume(self.mesures()))


class ConfigCommuneCreee(EnvTest):
    def test_le_fichier_commun_est_cree_s_il_n_existe_pas(self):
        config = charger("_config")
        etc = os.path.join(self.d, "etc-default")
        os.makedirs(etc)
        doc = os.path.join(self.d, "doc", "en")
        os.makedirs(doc, exist_ok=True)
        self.write("doc/en/app-default.conf.example", "#LANGUAGE=auto\n")
        self.write("doc/en/prog.conf.example", "#X=1\n")
        os.environ["NGINX_TOOLS_ETC_DEFAULT"] = etc
        os.environ.pop("NGINX_TOOLS_CONFIG_CREER", None)
        ancien_home = os.environ.get("HOME")
        os.environ["HOME"] = self.d
        try:
            self.write("etc-default/prog.conf", "X=2\n")                 # the program's own one already exists: the common one is created anyway
            config.creer_par_defaut("prog", dossier_doc=doc, argv=[])
            self.assertTrue(os.path.isfile(os.path.join(etc, "app-default.conf")))
            self.assertIn("#LANGUAGE=auto", open(os.path.join(etc, "app-default.conf")).read())
            self.assertIsNone(config.creer_par_defaut("prog", dossier_doc=doc, argv=["--help"]))
        finally:
            os.environ["NGINX_TOOLS_CONFIG_CREER"] = "0"
            if ancien_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = ancien_home
            os.environ.pop("NGINX_TOOLS_ETC_DEFAULT", None)


class ConfigDateModification(EnvTest):
    def test_ligne_de_configuration_donne_la_date_locale_de_modification(self):
        config = charger("_config")
        fichier = os.path.join(self.d, "essai.conf")
        with open(fichier, "w") as f:
            f.write("X=1\n")
        os.utime(fichier, (1760000000, 1760000000))
        import time
        attendu = time.strftime("%Y-%m-%d %H:%M", time.localtime(1760000000))
        self.assertEqual(config.date_modification(fichier), attendu)
        self.assertIn(f"{fichier} (modifié le {attendu})", config.ligne_configuration([fichier], None, "prog"))
        self.assertIn(f"(modifié le {attendu}) (demandé par -c/--config", config.ligne_configuration([fichier], fichier, "prog"))
        self.assertEqual(config.date_modification(os.path.join(self.d, "absent")), "?")

    def test_bash_donne_la_date_de_modification(self):
        import subprocess
        fichier = os.path.join(self.d, "essai.conf")
        with open(fichier, "w") as f:
            f.write("X=1\n")
        r = subprocess.run(["bash", "-c", f'. "{SCRIPTS_DIR}/apps/_i18n.sh"; config_date_modif "{fichier}"; config_date_modif /absent'], capture_output=True, text=True)
        lignes = r.stdout.split("\n")
        self.assertRegex(lignes[0], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
        self.assertEqual(lignes[1], "?")
