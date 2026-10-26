"""odoo-warmup.py — préchauffage du cache d'Odoo (pages publiques, assets, administration, démarrage automatique systemd) contre un FAUX serveur Odoo."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"   # Odoo seulement
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from helpers import EnvTest, require_script, script_path

PAGE = '<html><link href="/web/assets/1/web.assets_frontend.min.css"><script src="/web/assets/2/web.assets_frontend.min.js"></script></html>'
PAGE_EVENTS = ('<html><a href="/event/jpol-1">a</a><a href="/event/jpol-2/register">b</a><a href="/event/jpol-1">dup</a><a href="/web/login">x</a>'
               '<a href="/event/photo.png">img</a><a href="/event">liste</a><a href="/event/jpol-3">c</a>'
               '<script src="/web/assets/1/web.assets_frontend.min.js"></script></html>')
ALTERNATES = ('<link rel="alternate" hreflang="fr" href="http://site.exemple/event"/><link rel="alternate" hreflang="en-ca" href="http://site.exemple/en_CA/event"/>'
              '<link rel="alternate" hreflang="es" href="/es_MX/event"/><link rel="alternate" hreflang="de" href="/de/event"/><link rel="alternate" hreflang="x-default" href="/event"/>')
CLIENT = '<html><script src="/web/assets/3/web.assets_web.min.js"></script></html>'


class FauxOdoo(BaseHTTPRequestHandler):
    appels = []
    cle_valide = "cle-secrete"
    survey_ok = True
    survey_redirige = False

    def log_message(self, *a):
        pass

    def _repondre(self, code, corps, type_="text/html"):
        donnees = corps.encode()
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        FauxOdoo.appels.append(("GET", self.path))
        if self.path == "/event":
            self._repondre(200, PAGE_EVENTS.replace("<html>", "<html>" + ALTERNATES, 1))
        elif self.path == "/survey" and not FauxOdoo.survey_ok:
            self._repondre(404, "")
        elif self.path == "/survey" and FauxOdoo.survey_redirige:
            self.send_response(303)
            self.send_header("Location", "/en_CA/survey")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path in ("/en_CA/event", "/es_MX/event", "/contactus", "/blog", "/", "/web/login", "/survey", "/event/jpol-1", "/event/jpol-2/register", "/event/jpol-3", "/event/dernier-9", "/survey/start/tok1"):
            self._repondre(200, PAGE)
        elif self.path.startswith("/web/assets/"):
            self._repondre(200, "x")
        elif self.path == "/odoo":
            self._repondre(200, CLIENT)
        elif self.path == "/web/webclient/load_menus":
            self._repondre(200, "{}")
        else:
            self._repondre(404, "")

    def do_POST(self):
        taille = int(self.headers.get("Content-Length") or 0)
        demande = json.loads(self.rfile.read(taille) or b"{}")
        FauxOdoo.appels.append(("POST", self.path))
        if self.path == "/web/session/authenticate":
            ok = demande["params"]["password"] == FauxOdoo.cle_valide
            self._repondre(200, json.dumps({"result": {"uid": 2} if ok else {"uid": False}}), "application/json")
        elif self.path.endswith("/search_read"):
            champ = demande["params"]["kwargs"]["fields"][0]
            valeurs = {"website_url": ["http://site.exemple/event/dernier-9", "/event/non-publie-8"], "survey_start_url": ["http://site.exemple/survey/start/tok1"]}[champ]
            self._repondre(200, json.dumps({"result": [{champ: v} for v in valeurs]}), "application/json")
        elif self.path.endswith("/get_views"):
            erreur = {"error": {"data": {"message": "AccessError"}}} if "res.partner" in self.path else {"result": {}}
            self._repondre(200, json.dumps(erreur), "application/json")
        else:
            self._repondre(404, "")


class OdooWarmup(EnvTest):
    def setUp(self):
        super().setUp()
        require_script(self, "odoo-warmup.py")
        FauxOdoo.appels = []
        FauxOdoo.cle_valide = "cle-secrete"
        FauxOdoo.survey_ok = True
        FauxOdoo.survey_redirige = False
        self.serveur = HTTPServer(("127.0.0.1", 0), FauxOdoo)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.addCleanup(self.serveur.server_close)
        self.addCleanup(self.serveur.shutdown)
        self.url = f"http://127.0.0.1:{self.serveur.server_port}"
        self.etc = os.path.join(self.d, "etc")
        os.makedirs(self.etc)
        self.cle = os.path.join(self.d, "cle")
        with open(self.cle, "w") as f:
            f.write("cle-secrete\n")
        os.chmod(self.cle, 0o600)
        self.env["NGINX_TOOLS_ETC_DEFAULT"] = self.etc
        self.env["HOME"] = self.d
        self.env["NGINX_TOOLS_SYSTEMD_DIR"] = os.path.join(self.d, "systemd")

    def conf(self, texte):
        with open(os.path.join(self.etc, "odoo-warmup.conf"), "w") as f:
            f.write(texte)

    def lancer(self, *args):
        return self.run_cmd(["python3", script_path("odoo-warmup.py"), "--lang", "fr", *args], timeout=60)

    def test_pages_publiques_et_assets_sans_administration(self):
        code, out, err = self.lancer("--url", self.url, "--wait", "5")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Configuration lue :", out)
        for page in ("/", "/web/login", "/event", "/survey"):
            self.assertIn(("GET", page), FauxOdoo.appels)
        self.assertIn(("GET", "/web/assets/1/web.assets_frontend.min.css"), FauxOdoo.appels)
        self.assertIn(("GET", "/web/assets/2/web.assets_frontend.min.js"), FauxOdoo.appels)
        self.assertIn("administration non préchauffée", out)
        self.assertNotIn(("POST", "/web/session/authenticate"), FauxOdoo.appels)

    def test_administration_menus_et_vues_des_modeles(self):
        self.conf(f"LOGIN=prechauffage\nKEY_FILE={self.cle}\nDB=base1\nMODELS=event.event,survey.survey\nPAGES=/event\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--repeat", "2")
        self.assertEqual(code, 0, out + err)
        self.assertIn(("POST", "/web/session/authenticate"), FauxOdoo.appels)
        self.assertIn(("GET", "/odoo"), FauxOdoo.appels)
        self.assertIn(("GET", "/web/assets/3/web.assets_web.min.js"), FauxOdoo.appels)
        self.assertIn(("GET", "/web/webclient/load_menus"), FauxOdoo.appels)
        self.assertEqual(FauxOdoo.appels.count(("POST", "/web/dataset/call_kw/event.event/get_views")), 2)      # --repeat 2
        self.assertEqual(FauxOdoo.appels.count(("POST", "/web/dataset/call_kw/survey.survey/get_views")), 2)
        self.assertNotIn(("GET", "/survey"), FauxOdoo.appels)                                                   # PAGES replaces the default list
        self.assertNotIn("administration non préchauffée", out)

    def test_pages_liees_decouvertes_et_limitees(self):
        """1.1 : les pages liées (/event/…, /survey/…) des pages publiques sont chargées aussi, sans doublon ni asset ni fichier, au plus --links."""
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--links", "2")
        self.assertEqual(code, 0, out + err)
        self.assertIn(("GET", "/event/jpol-1"), FauxOdoo.appels)
        self.assertIn(("GET", "/event/jpol-2/register"), FauxOdoo.appels)
        self.assertNotIn(("GET", "/event/jpol-3"), FauxOdoo.appels)                      # au plus 2 liens
        self.assertNotIn(("GET", "/event/photo.png"), FauxOdoo.appels)
        self.assertEqual(FauxOdoo.appels.count(("GET", "/event/jpol-1")), 1)
        FauxOdoo.appels.clear()
        self.lancer("--url", self.url, "--wait", "5", "--links", "0")
        self.assertNotIn(("GET", "/event/jpol-1"), FauxOdoo.appels)

    def test_derniers_evenements_et_sondages_par_l_administration(self):
        """1.1 : avec LOGIN et KEY_FILE, les pages des N derniers événements et sondages sont préchauffées ; une page non publique n'est pas un échec."""
        self.conf(f"LOGIN=u\nKEY_FILE={self.cle}\nDB=base1\nMODELS=event.event\nPAGES=/survey\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--repeat", "1", "--links", "0", "--latest", "2")
        self.assertEqual(code, 0, out + err)
        self.assertIn(("POST", "/web/dataset/call_kw/event.event/search_read"), FauxOdoo.appels)
        self.assertIn(("POST", "/web/dataset/call_kw/survey.survey/search_read"), FauxOdoo.appels)
        self.assertIn(("GET", "/event/dernier-9"), FauxOdoo.appels)                      # absolute address reduced to the path
        self.assertIn(("GET", "/survey/start/tok1"), FauxOdoo.appels)
        self.assertIn(("GET", "/event/non-publie-8"), FauxOdoo.appels)
        self.assertIn("/event/non-publie-8 (non public)", out)
        FauxOdoo.appels.clear()
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--repeat", "1", "--links", "0", "--latest", "0")
        self.assertNotIn(("POST", "/web/dataset/call_kw/event.event/search_read"), FauxOdoo.appels)

    def test_pages_dans_les_trois_langues(self):
        """Chaque page est chargée dans fr, en et es quand le site les propose (liens hreflang) ; pas les autres langues (de) ; --site-languages aucune : seulement l'adresse."""
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--links", "0")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(FauxOdoo.appels.count(("GET", "/en_CA/event")), 1)
        self.assertEqual(FauxOdoo.appels.count(("GET", "/es_MX/event")), 1)
        self.assertEqual(FauxOdoo.appels.count(("GET", "/event")), 1)                    # the language of the page itself is not reloaded
        self.assertNotIn(("GET", "/de/event"), FauxOdoo.appels)
        FauxOdoo.appels.clear()
        self.lancer("--url", self.url, "--wait", "5", "--links", "0", "--site-languages", "es")
        self.assertIn(("GET", "/es_MX/event"), FauxOdoo.appels)
        self.assertNotIn(("GET", "/en_CA/event"), FauxOdoo.appels)
        FauxOdoo.appels.clear()
        self.lancer("--url", self.url, "--wait", "5", "--links", "0", "--site-languages", "aucune")
        self.assertNotIn(("GET", "/es_MX/event"), FauxOdoo.appels)

    def test_pages_supplementaires_du_fichier_etc_default(self):
        """Les pages du fichier odoo-warmup-pages.conf s'ajoutent aux pages par défaut ; une ligne invalide est signalée ; une page absente est un échec."""
        with open(os.path.join(self.etc, "odoo-warmup-pages.conf"), "w") as f:
            f.write("# commentaire\n/contactus\n/blog  # fin de ligne\nmauvaise\n/introuvable\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--links", "0")
        self.assertIn(("GET", "/contactus"), FauxOdoo.appels)
        self.assertIn(("GET", "/blog"), FauxOdoo.appels)
        self.assertIn(("GET", "/introuvable"), FauxOdoo.appels)
        self.assertEqual(code, 1, out + err)                                              # /introuvable : 404
        self.assertIn("ligne ignorée « mauvaise »", err)
        self.assertIn("3 page(s) dans", out)

    def test_fichier_des_pages_cree_au_premier_lancement(self):
        self.env["NGINX_TOOLS_CONFIG_CREER"] = "1"
        self.lancer("--url", self.url, "--wait", "5", "--links", "0")
        chemin = os.path.join(self.etc, "odoo-warmup-pages.conf")
        with open(chemin, encoding="utf-8") as f:
            texte = f.read()
        for page in ("/blog", "/event/journee-portes-ouvertes-sur-linux-2026-125/agenda", "/a-propos/collaborateurs-jpol-2026", "/contactus"):
            self.assertIn(page, texte.splitlines())

    def test_pages_de_sondages_optionnelles(self):
        """Une page /survey qui échoue (404) est notée « (optionnel) » mais ne fait pas échouer le préchauffage."""
        FauxOdoo.survey_ok = False
        self.conf("PAGES=/,/survey\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--links", "0")
        self.assertEqual(code, 0, out + err)
        self.assertIn("/survey (optionnel)", out)

    def test_une_vue_en_erreur_donne_un_echec_sans_arreter_le_reste(self):
        self.conf(f"LOGIN=u\nKEY_FILE={self.cle}\nDB=base1\nMODELS=res.partner,event.event\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--repeat", "1")
        self.assertEqual(code, 1, out + err)
        self.assertIn("ÉCHEC", out)
        self.assertIn(("POST", "/web/dataset/call_kw/event.event/get_views"), FauxOdoo.appels)

    def test_connexion_refusee(self):
        FauxOdoo.cle_valide = "autre"
        self.conf(f"LOGIN=u\nKEY_FILE={self.cle}\nDB=base1\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5")
        self.assertEqual(code, 1, out + err)
        self.assertIn("refusée", out)
        self.assertNotIn("get_views", " ".join(p for _, p in FauxOdoo.appels))

    def test_clef_jamais_affichee_et_base_obligatoire(self):
        self.conf(f"LOGIN=u\nKEY_FILE={self.cle}\n")
        code, out, err = self.lancer("--url", self.url, "--wait", "5")
        self.assertEqual(code, 2)
        self.assertIn("base à préciser", err)
        self.assertNotIn("cle-secrete", out + err)

    def test_odoo_qui_ne_repond_pas(self):
        code, out, err = self.lancer("--url", "http://127.0.0.1:9", "--wait", "1")
        self.assertEqual(code, 2)
        self.assertIn("Odoo ne répond pas", err)

    def test_systemd_installer_puis_retirer(self):
        code, out, err = self.lancer("--systemd-install", "--service", "odoo-test.service", "--wait", "90")
        self.assertEqual(code, 0, out + err)
        fichier = os.path.join(self.d, "systemd", "odoo-test.service.d", "odoo-warmup.conf")
        with open(fichier) as f:
            contenu = f.read()
        self.assertIn("ExecStartPost=-+/usr/bin/systemd-run", contenu)
        self.assertIn("--no-block", contenu)
        self.assertIn("--wait 90", contenu)
        code, out, err = self.lancer("--systemd-remove", "--service", "odoo-test.service")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(os.path.exists(fichier))
        code, out, err = self.lancer("--systemd-remove", "--service", "odoo-test.service")
        self.assertIn("Rien à retirer", out)

    def test_unite_systemd_trouvee_par_le_processus_odoo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("odoo_warmup_module", script_path("odoo-warmup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        proc = os.path.join(self.d, "proc")
        for pid, commande, cgroupe in (("101", b"python3\0/opt/erplibre/odoo-bin\0", "0::/system.slice/erplibre.service\n"),
                                       ("102", b"bash\0-c\0sleep\0", "0::/system.slice/ssh.service\n"),
                                       ("103", b"python3\0/usr/bin/odoo\0", "0::/system.slice/user.slice/erplibre-worker.service\n")):
            os.makedirs(os.path.join(proc, pid))
            with open(os.path.join(proc, pid, "cmdline"), "wb") as f:
                f.write(commande)
            with open(os.path.join(proc, pid, "cgroup"), "w") as f:
                f.write(cgroupe)
        self.assertEqual(module.odoo_units(proc), ["erplibre-worker.service", "erplibre.service"])
        self.assertEqual(module.odoo_units(os.path.join(self.d, "vide")), [])

    def test_ports_lus_dans_la_ligne_de_commande_du_service(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("odoo_warmup_module2", script_path("odoo-warmup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.ports_de_ligne_de_commande("python3 odoo-bin --http-port=10000 --gevent-port 10002 -c /etc/odoo.conf"),
                         ([10000], [10002], "/etc/odoo.conf"))
        self.assertEqual(module.ports_de_ligne_de_commande("ExecStart={ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 odoo-bin --config /x.conf }"),
                         ([], [], "/x.conf"))
        # Un faux /proc avec un processus Odoo, et un faux systemctl qui renvoie l'ExecStart de l'unité
        proc = os.path.join(self.d, "proc2")
        os.makedirs(os.path.join(proc, "201"))
        with open(os.path.join(proc, "201", "cmdline"), "wb") as f:
            f.write(b"python3\0odoo-bin\0--http-port=10000\0")
        with open(os.path.join(proc, "201", "cgroup"), "w") as f:
            f.write("0::/system.slice/erplibre.service\n")
        bin_dir = os.path.join(self.d, "bin-faux-systemctl")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "systemctl"), "w") as f:
            f.write("#!/bin/sh\necho 'ExecStart={ argv[]=/usr/bin/python3 odoo-bin --gevent-port=10002 }'\n")
        os.chmod(os.path.join(bin_dir, "systemctl"), 0o755)
        ancien = os.environ.get("PATH", "")
        os.environ["PATH"] = bin_dir + os.pathsep + ancien
        try:
            http, gevent, config = module.ports_du_service(proc)
        finally:
            os.environ["PATH"] = ancien
        self.assertEqual((http, gevent, config), ([10000], [10002], None))

    def test_processus_erplibre_reconnu_sans_le_mot_odoo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("odoo_warmup_module3", script_path("odoo-warmup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.est_processus_odoo(b"python3\0/home/mathben/git/erplibre/serveur.py\0"))
        self.assertTrue(module.est_processus_odoo(b"python3\0odoo-bin\0"))
        self.assertFalse(module.est_processus_odoo(b"bash\0-c\0erplibre\0"))
        self.assertFalse(module.est_processus_odoo(b"python3\0/usr/bin/autre.py\0"))

    def test_redirection_d_un_sondage_non_suivie(self):
        FauxOdoo.survey_redirige = True
        code, out, err = self.lancer("--url", self.url, "--wait", "5", "--links", "0")
        self.assertEqual(code, 0, out + err)
        self.assertIn(("GET", "/survey"), FauxOdoo.appels)
        self.assertNotIn(("GET", "/en_CA/survey"), FauxOdoo.appels)

    def test_pas_de_variante_de_langue_pour_une_page_de_sondage(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("odoo_warmup_module4", script_path("odoo-warmup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        html = '<html><link rel="alternate" hreflang="en" href="/en_CA/survey"/><link rel="alternate" hreflang="fr" href="/survey"/></html>'
        self.assertEqual(module.language_variants(html, ("fr", "en", "es"), "/survey"), [])
        self.assertEqual(module.language_variants(html, ("fr", "en", "es"), "/event"), ["/en_CA/survey", "/survey"])

    def test_version_et_changelog(self):
        code, out, err = self.run_cmd(["python3", script_path("odoo-warmup.py"), "--version"])
        self.assertRegex(out, r"odoo-warmup.py version 1\.\d+\.\d{8}\.\d{6}")
        code, out, err = self.run_cmd(["python3", script_path("odoo-warmup.py"), "--changelog"])
        self.assertIn("## odoo-warmup.py", out)
        self.assertRegex(out, r"(?m)^### 1\.\d+\.\d{8}\.\d{6}( - .*)?$")
