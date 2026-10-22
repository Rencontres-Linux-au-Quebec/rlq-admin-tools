"""app-health-check.py — règle stricte « -dev. / .dev. », cohérence EXPECT_RESTRICTED_ACCESS, robots.txt, redirection
de langue de /web/login (Google OAuth), --create-config. Un vrai serveur HTTPS de test tourne sur un port libre ;
les connexions du script vers le port 443 y sont redirigées (aucun besoin du port 443, occupé par nginx en prod)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import shutil
import http.server
import importlib.util
import os
import ssl
import stat
import subprocess
import threading
import unittest
import unittest.mock

from helpers import sans_origine, EnvTest, script_path, sans_date

ETAT = {"robots": b"User-agent: *\nSitemap: https://x/sitemap.xml\n", "login_redirige": True, "google": True}


class Serveur(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reponse(self, code, body=b"", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/web/health"):                          # 2.7 : sonde légère d'Odoo
            ok = ETAT.get("health", True)
            corps = b'{"status": "pass"}' if ok else b'{"status": "fail", "error": "db"}'
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
            return
        host = self.headers.get("Host", "")
        if host in ("rencontres-linux.quebec", "odoo18.rencontres-linux.quebec"):
            return self.reponse(301, headers=[("Location", "https://www.rencontres-linux.quebec/")])
        if self.path == "/robots.txt":
            return self.reponse(200, ETAT["robots"])
        if self.path == "/web/login" and ETAT["login_redirige"]:
            return self.reponse(303, b'Redirecting... <a href="/en_CA/web/login">', [("Location", "/en_CA/web/login")])
        if self.path.endswith("/web/login"):
            lien = b'<a href="https://accounts.google.com/o/oauth2/auth?redirect_uri=https%3A%2F%2Fwww.rencontres-linux.quebec%2Fauth_oauth%2Fsignin">G</a>'
            return self.reponse(200, lien if ETAT["google"] else b"<form>login</form>")
        return self.reponse(200, b"OK")


class SanityCheck(EnvTest):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(script_path("app-health-check.py")):
            raise unittest.SkipTest("app-health-check.py absent")
        import tempfile
        cls.tls = tempfile.mkdtemp(prefix="test-rlq-tls-")     # clé privée de test : supprimée en fin de classe
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", f"{cls.tls}/k.pem", "-out",
                        f"{cls.tls}/c.pem", "-days", "1", "-nodes", "-subj", "/CN=test"], capture_output=True, check=True)
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Serveur)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(f"{cls.tls}/c.pem", f"{cls.tls}/k.pem")
        cls.srv.socket = ctx.wrap_socket(cls.srv.socket, server_side=True)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        spec = importlib.util.spec_from_file_location("sanity", script_path("app-health-check.py"))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        origine, port = cls.m.Http, cls.port

        class HttpRedirige(origine):
            def __init__(self, host, p, *a, **k):
                super().__init__(host, port if p == 443 else p, *a, **k)
        cls.m.Http = HttpRedirige

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        import shutil
        shutil.rmtree(cls.tls, ignore_errors=True)

    def setUp(self):
        super().setUp()
        ETAT.update(robots=b"User-agent: *\nSitemap: https://x/sitemap.xml\n", login_redirige=True, google=True, health=True)

    def resultats(self, cfg):
        return {l: (ok, d) for l, ok, d in self.m.check_http(cfg, "local")}

    # --- règle stricte (1.12) ---------------------------------------------------------------------------------------
    def test_detection_developpement_stricte(self):
        cas = {"odoo-dev.rencontres-linux.quebec": True, "odoo.dev.exemple.org": True, "dev.exemple.org": True,
               "ODOO-DEV.Exemple.org": True, "www.rencontres-linux.quebec": False, "odoo18.rencontres-linux.quebec": False,
               "devis.exemple.com": False, "device01.exemple.com": False, "developpeurs.exemple.org": False,
               "mondev.exemple.org": False, "odoo-dev2.exemple.org": False, "monsite.dev": False, "odoo-dev": False}
        for nom, attendu in cas.items():
            with self.subTest(nom=nom):
                self.assertEqual(self.m.nonprod_hint([nom])[0] is not None, attendu)

    def test_coherence_expect_restricted_access(self):
        c = self.m.check_restricted_coherence
        self.assertIs(c({"ODOO_PUBLIC_HOST": "www.rencontres-linux.quebec", "EXPECT_RESTRICTED_ACCESS": "true"}, "x")[0][1], False)
        self.assertIsNone(c({"ODOO_PUBLIC_HOST": "odoo-dev.rencontres-linux.quebec"}, "x")[0][1])            # suggestion
        self.assertIs(c({"ODOO_PUBLIC_HOST": "odoo-dev.rencontres-linux.quebec", "EXPECT_RESTRICTED_ACCESS": "true"}, "x")[0][1], True)
        self.assertIs(c({"ODOO_PUBLIC_HOST": "www.rencontres-linux.quebec"}, "x")[0][1], True)

    # --- robots.txt (1.9, 1.10) ---------------------------------------------------------------------------------------
    def test_robots_disallow_tout_explique_en_mode_public(self):
        ETAT["robots"] = b"User-agent: *\nDisallow: /\n"
        r = self.resultats({"ODOO_PUBLIC_HOST": "www.rencontres-linux.quebec", "EXPECT_GOOGLE_OAUTH": "true"})
        ok, detail = r["/robots.txt"]
        self.assertIs(ok, False)
        self.assertIn("FORBIDS THE WHOLE SITE", detail)
        r2 = self.resultats({"ODOO_PUBLIC_HOST": "odoo-dev.rencontres-linux.quebec", "EXPECT_RESTRICTED_ACCESS": "true"})
        self.assertIs(r2["/robots.txt"][0], True)

    # --- Google OAuth derrière la redirection de langue (1.14) ---------------------------------------------------------
    def test_google_oauth_suit_la_redirection_de_langue(self):
        r = self.resultats({"ODOO_PUBLIC_HOST": "www.rencontres-linux.quebec", "EXPECT_GOOGLE_OAUTH": "true"})
        cle = next(k for k in r if "Google" in k)
        self.assertIs(r[cle][0], True, r[cle][1])

    # --- --create-config (1.13) --------------------------------------------------------------------------------------
    def test_sonde_legere_web_health(self):
        """2.7 : /web/health en premier — réussite si « pass », échec si Odoo ou sa base ne répond pas."""
        cfg = {"ODOO_PUBLIC_HOST": "www.rencontres-linux.quebec", "EXPECT_GOOGLE_OAUTH": "true"}
        r = self.resultats(cfg)
        cle = next(k for k in r if k.startswith("Light probe /web/health"))
        self.assertIs(r[cle][0], True, r[cle][1])
        self.assertEqual(list(r)[0], cle)                                  # la toute première vérification
        ETAT["health"] = False
        try:
            r = self.resultats(cfg)
            self.assertIs(r[cle][0], False)
            self.assertIn("HTTP 500", r[cle][1])
        finally:
            ETAT["health"] = True

    def test_create_config_detecte_et_protege(self):
        self.mock("nginx", '[[ "$1" == -T ]] && printf "server_name www.rencontres-linux.quebec;\\n'
                           'server_name rencontres-linux.quebec odoo18.rencontres-linux.quebec; # server_name piege.exemple\\n"')
        self.mock("systemctl", '[[ "$1" == cat && "$2" == erplibre.service ]] && printf "ExecStart=/opt/odoo/erplibre/run.sh -d linux_meetup_odoo_18\\n" && exit 0; exit 1')
        ancien_path = os.environ["PATH"]
        os.environ["PATH"] = self.env["PATH"]                 # create_config lance nginx/systemctl via le PATH global
        self.addCleanup(os.environ.__setitem__, "PATH", ancien_path)
        chemin = self.path("etc", "sanity.conf")
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.m.create_config(chemin), 0)
        cfg = self.m.load_config(chemin)
        self.assertEqual(cfg["ODOO_PUBLIC_HOST"], "www.rencontres-linux.quebec")
        self.assertEqual(sorted(cfg["ADDITIONAL_PUBLIC_HOSTS"].split(",")), ["odoo18.rencontres-linux.quebec", "rencontres-linux.quebec"])
        self.assertEqual(cfg["EXPECT_RESTRICTED_ACCESS"], "false")
        self.assertEqual(cfg["ODOO_DB"], "linux_meetup_odoo_18")
        self.assertEqual(cfg["EXPECT_GOOGLE_OAUTH"], "true")
        self.assertNotIn("piege", open(chemin).read().split("ADDITIONAL_PUBLIC_HOSTS=")[1].splitlines()[0])
        self.assertEqual(stat.S_IMODE(os.stat(chemin).st_mode), 0o600)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.m.create_config(chemin), 1)                   # jamais d'écrasement sans --force



@unittest.skipUnless(shutil.which("openssl"), "openssl requis pour générer les certificats de test")
class CertificatTLS(EnvTest):
    """2.4 : certificat TLS — vrai serveur TLS local, certificats générés par openssl."""
    def serveur(self, jours, nom="www.exemple.org"):
        """Serveur TLS dans un PROCESSUS séparé (openssl s_server), arrêté en fin de test : aucun fil d'exécution
        résiduel (un fil bloqué dans accept() survivait à la fermeture du socket et perturbait les tests suivants)."""
        import socket, time
        cle, cert = self.path(f"k{jours}.pem"), self.path(f"c{jours}.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", cle, "-out", cert,
                        "-days", str(jours), "-subj", f"/O=Autorite de test/CN={nom}", "-addext", f"subjectAltName=DNS:{nom}"],
                       check=True, capture_output=True)
        with socket.socket() as t:
            t.bind(("127.0.0.1", 0))
            port = t.getsockname()[1]
        proc = subprocess.Popen(["openssl", "s_server", "-quiet", "-accept", f"127.0.0.1:{port}", "-cert", cert, "-key", cle, "-www"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        for _ in range(50):                                             # attendre l'écoute (5 s au plus)
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        return port, cert

    def verifier(self, port, ca):
        spec = importlib.util.spec_from_file_location("ahc", script_path("app-health-check.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        anciens = {k: os.environ.get(k) for k in ("APP_HEALTH_TLS_PORT", "SSL_CERT_FILE")}
        os.environ.update(APP_HEALTH_TLS_PORT=str(port), SSL_CERT_FILE=ca)
        try:
            return m.check_tls_certificate({"ODOO_PUBLIC_HOST": "www.exemple.org"}, "local")[0]
        finally:
            for k, v in anciens.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def test_valide_bientot_expire_et_refuse(self):
        port, ca = self.serveur(90)
        label, ok, detail = self.verifier(port, ca)
        self.assertTrue(ok, detail)
        self.assertRegex(detail, r"still valid for (89|90) days .* issued by Autorite de test")
        port, ca = self.serveur(10)
        label, ok, detail = self.verifier(port, ca)
        self.assertIs(ok, False)
        self.assertRegex(detail, r"expires in (9|10) day\(s\).*certbot renew --dry-run")
        port, _ = self.serveur(60)
        label, ok, detail = self.verifier(port, ca)                        # autorité non reconnue
        self.assertIs(ok, False)
        self.assertIn("certificate REFUSED", detail)
        self.assertIn("issuer: Autorite de test", detail)


if __name__ == "__main__":
    unittest.main()


FAUX_SMTP = r"""
import socket, sys
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
print(s.getsockname()[1], flush=True)
c, _ = s.accept(); f = c.makefile("rwb")
def dire(t): f.write((t + "\r\n").encode()); f.flush()
dire("220 faux-smtp")
donnees = False
for ligne in f:
    l = ligne.decode(errors="replace").rstrip("\r\n")
    if donnees:
        if l == ".":
            donnees = False; dire("250 message accepte")
        else:
            open(sys.argv[1], "a").write(l + "\n")
        continue
    cmd = l.split(" ")[0].upper()
    if cmd in ("EHLO", "HELO"): dire("250 faux-smtp")
    elif cmd in ("MAIL", "RCPT", "RSET", "NOOP"): dire("250 ok")
    elif cmd == "DATA": donnees = True; dire("354 envoyer")
    elif cmd == "QUIT": dire("221 au revoir"); break
    else: dire("502 non pris en charge")
"""


class Courriel(EnvTest):
    """2.8 : vérification DNS du courriel (MX, SPF, DMARC, DKIM, relais) et envoi de test."""
    def module(self):
        spec = importlib.util.spec_from_file_location("ahc", script_path("app-health-check.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def ecoute(self):
        import socket
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
        self.addCleanup(srv.close)
        return srv.getsockname()[1]

    def test_dns_complet_puis_defauts(self):
        m = self.module()
        zone = {("rencontres-linux.quebec", "MX"): ["10 mx.fournisseur.exemple."],
                ("exemple.org", "MX"): ["10 mx.exemple.org."],
                ("destinataire.exemple", "MX"): ["10 mx.destinataire.exemple."],
                ("rencontres-linux.quebec", "TXT"): ["v=spf1 include:_spf.fournisseur.exemple -all", "google-site-verification=x"],
                ("_dmarc.rencontres-linux.quebec", "TXT"): ["v=DMARC1; p=quarantine; rua=mailto:postmaster@rencontres-linux.quebec"],
                ("s1._domainkey.rencontres-linux.quebec", "TXT"): ["v=DKIM1; k=rsa; p=MIIB"]}
        m._dns = lambda nom, t: zone.get((nom, t), [])
        cfg = {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(self.ecoute()), "NOTIFY_EMAIL_FROM": "alertes@rencontres-linux.quebec",
               "NOTIFY_EMAIL_TO": "info@destinataire.exemple", "DKIM_SELECTOR": "s1"}
        niveaux = {msg.split(" :")[0]: n for n, msg, _ in m.check_email_dns(cfg)}
        self.assertEqual(set(niveaux.values()), {"OK"}, niveaux)
        # SPF en double, DMARC absent, destinataire sans MX, relais fermé
        zone[("rencontres-linux.quebec", "TXT")] = ["v=spf1 -all", "v=spf1 include:x -all"]
        del zone[("_dmarc.rencontres-linux.quebec", "TXT")]
        del zone[("destinataire.exemple", "MX")]
        cfg["SMTP_PORT"] = "1"
        res = m.check_email_dns(cfg)
        texte = "\n".join(f"[{n}] {msg} " + " | ".join(d) for n, msg, d in res)
        self.assertIn("[FAIL] 2 SPF records for rencontres-linux.quebec : invalid", texte)
        self.assertIn("[FAIL] no MX for the recipient domain destinataire.exemple", texte)
        self.assertIn("[FAIL] SMTP relay unreachable: 127.0.0.1:1", texte)
        self.assertIn('add to DNS: _dmarc.rencontres-linux.quebec. TXT "v=DMARC1; p=none; rua=mailto:postmaster@rencontres-linux.quebec; fo=1"', texte)
        self.assertEqual(m.check_email_dns({})[0][0], "FAIL")                    # non configuré

    def test_spf_exact_selon_le_relais_et_dkim_avec_modele(self):
        """2.20 : l'enregistrement SPF proposé est EXACT : include: du domaine du relais s'il publie un SPF, sinon a:HOTE ; relais local : mx a ; DKIM : modèle complet."""
        m = self.module()
        zone = {("libretrust.exemple", "TXT"): ["v=spf1 ip4:192.0.2.0/24 -all"]}
        m._dns = lambda nom, t: zone.get((nom, t), [])
        self.assertEqual(m.suggest_spf({"SMTP_HOST": "mail.libretrust.exemple"}, "rlq.exemple"), 'rlq.exemple. TXT "v=spf1 include:libretrust.exemple ~all"')
        self.assertEqual(m.suggest_spf({"SMTP_HOST": "mail.autre.exemple"}, "rlq.exemple"), 'rlq.exemple. TXT "v=spf1 a:mail.autre.exemple ~all"')
        self.assertEqual(m.suggest_spf({"SMTP_HOST": "127.0.0.1"}, "rlq.exemple"), 'rlq.exemple. TXT "v=spf1 mx a -all"')
        cfg = {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(self.ecoute()), "NOTIFY_EMAIL_FROM": "a@rlq.exemple", "NOTIFY_EMAIL_TO": "b@dest.exemple"}
        texte = "\n".join(" | ".join(d) for _, _, d in m.check_email_dns(cfg))
        self.assertIn('SELECTOR._domainkey.rlq.exemple. TXT "v=DKIM1; k=rsa; p=RELAY_PUBLIC_KEY"', texte)

    def test_configuration_commune_du_courriel_completee_sans_ecraser(self):
        """2.20 : sans SMTP_HOST propre au programme, la configuration commune (nginx-tools-mail.conf + fichier du mot de passe) fournit le relais ; les clés SMTP_* l'emportent."""
        m = self.module()
        mdp = self.write("etc/mail.pass", "secret-commun\n", 0o600)
        conf = self.write("etc/mail.conf", f'MAIL_HOST="smtp.exemple.org"\nMAIL_PORT="465"\nMAIL_USER="u@exemple.org"\nMAIL_FROM="f@exemple.org"\nMAIL_TO="t@exemple.org"\nMAIL_PASSWORD_FILE="{mdp}"\n')
        os.environ["NGINX_TOOLS_MAIL_CONF"] = conf
        self.addCleanup(os.environ.pop, "NGINX_TOOLS_MAIL_CONF", None)
        cfg = {}
        self.assertTrue(m.complete_common_mail(cfg))
        self.assertEqual((cfg["SMTP_HOST"], cfg["SMTP_PORT"], cfg["SMTP_SECURITY"], cfg["SMTP_USER"], cfg["NOTIFY_EMAIL_TO"], cfg["SMTP_PASSWORD"]),
                         ("smtp.exemple.org", "465", "ssl", "u@exemple.org", "t@exemple.org", "secret-commun"))
        propre = {"SMTP_HOST": "autre.exemple.org"}
        self.assertFalse(m.complete_common_mail(propre))
        self.assertEqual(propre, {"SMTP_HOST": "autre.exemple.org"})

    def test_envoi_reel_vers_un_faux_relais(self):
        m = self.module()
        m._dns = lambda nom, t: ["10 mx.exemple."] if t == "MX" else []
        recu = self.path("recu.txt")
        proc = subprocess.Popen(["python3", "-c", FAUX_SMTP, recu], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        port = proc.stdout.readline().strip()
        cfg = {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": port, "SMTP_SECURITY": "none",
               "NOTIFY_EMAIL_FROM": "alertes@rencontres-linux.quebec", "NOTIFY_EMAIL_TO": "info@rencontres-linux.quebec"}
        m.check_email_dns = lambda c: []                                          # DNS testé ailleurs
        import io, contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            m.test_email(cfg)
        self.assertIn("[OK] courriel de test envoyé à info@rencontres-linux.quebec", f.getvalue())
        proc.wait(timeout=10)
        message = open(recu).read()
        self.verifier_entetes(message)

    def verifier_entetes(self, message):
        """En-têtes LUS PAR UN ANALYSEUR (pas par expression régulière sur le texte brut) : Python replie un en-tête de plus
        de 78 caractères — « Message-ID:\\n <…> » — selon la longueur du PID et du nombre aléatoire ; le test échouait sur
        un serveur aux PID à 7 chiffres alors qu'il réussissait en développement."""
        import email
        import email.header
        import email.policy
        msg = email.message_from_string(message, policy=email.policy.default)
        self.assertTrue(str(msg["Subject"]).startswith("[app-health-check] Test d'envoi"), msg["Subject"])
        self.assertRegex(str(msg["Message-ID"]).strip(), r"^<[^<>\s]+@rencontres-linux\.quebec>$")   # replié : espace en tête
        self.assertTrue(msg["Date"])
        self.assertEqual(msg["From"], "alertes@rencontres-linux.quebec")

    def test_entetes_replies_lus_correctement(self):
        """Le message réellement reçu sur le serveur BBB de DEV (Message-ID replié sur deux lignes, sujet encodé)."""
        self.verifier_entetes("Subject: [app-health-check] Test d'envoi =?utf-8?b?4oCU?= bbb30\nFrom: alertes@rencontres-linux.quebec\n"
                              "To: info@rencontres-linux.quebec\nDate: Wed, 30 Sep 2026 08:25:33 -0400\nMessage-ID:\n "
                              "<179077113323.3245209.16440135464468107978@rencontres-linux.quebec>\n"
                              "Content-Type: text/plain; charset=\"utf-8\"\nMIME-Version: 1.0\n\ncorps\n")

    def test_modes_de_securite(self):
        m = self.module()
        self.assertEqual(m.smtp_security({"SMTP_PORT": "587"}), "starttls")
        self.assertEqual(m.smtp_security({"SMTP_PORT": "465"}), "ssl")
        self.assertEqual(m.smtp_security({"SMTP_PORT": "25", "SMTP_HOST": "127.0.0.1"}), "none")
        self.assertEqual(m.smtp_security({"SMTP_PORT": "587", "SMTP_SECURITY": "SSL"}), "ssl")


class ProgrammeComplet(EnvTest):
    """2.9 : le programme va jusqu'au bout sans SMTP (la 2.8 s'arrêtait sur « SMTP_HOST non configuré ») ; échec
    d'envoi signalé sans arrêt ; couleurs seulement dans un terminal."""
    def lancer(self, extra=""):
        prog = self.prepare("app-health-check.py")
        cfg = self.write("ahc.conf", "ODOO_PUBLIC_HOST=www.exemple.org\n" + extra)
        return self.run_cmd(["python3", prog, "--target", "local", "-c", cfg])

    def test_sans_smtp_jusqu_au_bout(self):
        rc, out, err = self.lancer()
        self.assertNotIn("Traceback", err)
        self.assertRegex(out, r"Résumé : \d+ échec\(s\) sur \d+ vérification\(s\)\.")
        self.assertNotIn("\x1b[", out)                                   # sortie capturée : jamais de couleur
        self.assertIn("Rapport app-health-check.py v", out)

    def test_relais_injoignable_signale_sans_arret(self):
        rc, out, err = self.lancer("SMTP_HOST=127.0.0.1\nSMTP_PORT=1\nNOTIFY_EMAIL_TO=a@exemple.org\n")
        self.assertNotIn("Traceback", err)
        self.assertIn("[FAIL] envoi du rapport par courriel impossible", out)
        self.assertIn("app-health-check.py --test-email", out)

    def test_check_email_dns_sans_target_ni_application(self):
        """2.10 : --check-email-dns sans --target (refusé en 2.8/2.9 : l'étape 13 recevait l'aide du programme), même
        sans application détectée."""
        prog = self.prepare("app-health-check.py")
        cfg = self.write("ahc.conf", "ODOO_PUBLIC_HOST=www.exemple.org\n")
        self.env.pop("APP_PROFILE", None)
        rc, out, err = self.run_cmd(["python3", prog, "--check-email-dns", "-c", cfg])
        self.assertNotIn("argument --target requis", err)
        self.assertIn("[FAIL] courriel non configuré", out)
        self.assertEqual(rc, 1)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_premiere_execution_cree_la_configuration(self):
        """2.11 : sans configuration, /etc/default/app-health-check.conf est créé (valeurs détectées) et le programme
        continue — avant, « aucun fichier de config trouve » (code 2) à chaque passage de web-monitor.py."""
        defaut = os.path.dirname(self.path("etc-default", "x")) + "/"
        prog = self.prepare("app-health-check.py", {"/etc/default/": defaut})
        rc, out, err = self.run_cmd(["python3", prog, "--target", "local"])
        self.assertNotIn("aucun fichier de config trouve", err)
        self.assertIn(f"Aucune configuration : création de {defaut}app-health-check.conf", out)
        self.assertTrue(os.path.isfile(defaut + "app-health-check.conf"))
        self.assertRegex(out, r"Résumé : \d+ échec\(s\)")
        self.assertNotIn("Traceback", err)
        rc, out, err = self.run_cmd(["python3", prog, "--target", "local"])
        self.assertNotIn("Aucune configuration", out)                       # une seule fois

    def test_couleurs_en_terminal_seulement(self):
        spec = importlib.util.spec_from_file_location("ahc", script_path("app-health-check.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        texte = "[OK  ] site\n[SKIP] oauth\n[FAIL] tls\n[ATTN] dmarc\nSummary: 1 failure(s) out of 4 check(s)."
        c = m.color(texte, tty=True)
        self.assertIn("\x1b[1;32m[OK  ]\x1b[0m", c)
        self.assertIn("\x1b[1;33m[SKIP]\x1b[0m", c)
        self.assertIn("\x1b[1;31m[FAIL]\x1b[0m", c)
        self.assertIn("\x1b[1;33m[ATTN]\x1b[0m", c)
        self.assertIn("\x1b[1;31m1 failure(s)\x1b[0m", c)
        self.assertIn("\x1b[1;32m0 failure(s)\x1b[0m", m.color("Summary: 0 failure(s) out of 4 check(s).", tty=True))
        self.assertEqual(m.color(texte, tty=False), texte)


class ConfigurationEnCouches(EnvTest):
    """2.14 : /etc/default/app-health-check.conf, PUIS ~/.app-health-check.conf, PUIS ./app-health-check.conf (le dernier
    l'emporte) ; -c seul ; fichiers lus et options importantes toujours affichés."""
    def module(self):
        spec = importlib.util.spec_from_file_location("ahc", script_path("app-health-check.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_report_err(self):
        prog = self.prepare("app-health-check.py")
        cfg = self.write("ahc.conf", "ODOO_PUBLIC_HOST=www.exemple.org\nSMTP_PASSWORD=motdepasse\n")
        rc, out, err = self.run_cmd(["python3", prog, "--report-err", "--check-email-dns", "-c", cfg, "--app", "odoo"])
        self.assertEqual(rc, 1, err)                                                # code conservé (courriel non configuré)
        self.assertLess(out.index("[FAIL] courriel non configuré"), out.index("RAPPORT D'ERREURS"))
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : app-health-check\.py v2\.\d+\.\d{8}\.\d{6} — commande : app-health-check\.py --check-email-dns -c \S+ --app odoo\n")
        self.assertIn("Contexte  : Application : Odoo", rapport)
        self.assertIn("Configuration lue : ", rapport)
        self.assertIn("ÉCHECS (1) :\n  1. [FAIL] courriel non configuré", rapport)
        self.assertIn("voir doc/email-setup.md", rapport)                          # ligne de détail
        self.assertNotIn("motdepasse", out)
        rc, out, err = self.run_cmd(["python3", prog, "--version", "--report-err"])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("RAPPORT D'ERREURS", out)

    def test_fusion_ordre_et_dedoublonnage(self):
        m = self.module()
        a = self.write("a.conf", "ODOO_PUBLIC_HOST=a.exemple.org\nSMTP_HOST=smtp.a\nEXPECT_GOOGLE_OAUTH=true\n")
        b = self.write("b.conf", "ODOO_PUBLIC_HOST=b.exemple.org\nEXPECT_RESTRICTED_ACCESS=true\n")
        cfg = m.load_config([a, b])
        self.assertEqual(cfg["ODOO_PUBLIC_HOST"], "b.exemple.org")              # le dernier l'emporte
        self.assertEqual(cfg["SMTP_HOST"], "smtp.a")                            # ce qui n'est pas redéfini vient du premier
        self.assertEqual(cfg["EXPECT_GOOGLE_OAUTH"], "true")
        self.assertEqual(cfg["EXPECT_RESTRICTED_ACCESS"], "true")
        self.assertEqual(m.load_config(a)["ODOO_PUBLIC_HOST"], "a.exemple.org")  # un seul chemin : inchangé

    def module_redirige(self):
        """Copie du programme dont « /etc/default/ » pointe vers un dossier de test : les fonctions qui RENOMMENT des fichiers
        (migration) ne doivent jamais toucher le vrai /etc/default (un test l'avait fait : run-all.sh le détecte maintenant)."""
        defaut = os.path.dirname(self.path("etc-default", "x")) + "/"
        prog = self.prepare("app-health-check.py", {"/etc/default/": defaut})
        spec = importlib.util.spec_from_file_location("ahc_redirige", prog)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m, defaut

    def test_resolve_config_paths_ordre_et_repertoire_courant_ignore(self):
        import io, contextlib
        m, defaut = self.module_redirige()
        home = os.path.dirname(self.path("home-vide", "x"))
        systeme = self.write("etc-default/app-health-check.conf", "X=0\n")
        perso = self.write("home-vide/.app-health-check.conf", "X=1\n")
        ancien = os.getcwd()
        os.chdir(self.d)
        self.addCleanup(os.chdir, ancien)
        courant = self.write("app-health-check.conf", "X=2\n")
        e = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"HOME": home}), contextlib.redirect_stderr(e):
            chemins = m.resolve_config_paths(None)
        self.assertEqual(chemins, [defaut + "app-health-check.conf", perso])      # /etc/default puis ~ : JAMAIS ./
        self.assertEqual(m.load_config(chemins)["X"], "1")                        # ~ l'emporte ; ./ (X=2) n'a aucun effet
        self.assertIn("app-health-check.conf exists but is NO LONGER read", e.getvalue())
        self.assertIn("mv ./app-health-check.conf ~/.app-health-check.conf", e.getvalue())
        self.assertTrue(os.path.exists(courant), "avec un fichier système, ./ est signalé, jamais déplacé")
        self.assertEqual(m.resolve_config_paths(perso), [perso])                  # -c : ce fichier seul
        with self.assertRaises(FileNotFoundError):
            m.resolve_config_paths("/nulle/part.conf")
        self.assertTrue(os.path.exists(systeme))

    def test_ancien_fichier_du_repertoire_courant_renomme_vers_etc_default(self):
        """Pas encore de fichier système : l'ancien ./app-health-check.conf (lu jusqu'en 2.14) y est RENOMMÉ, pas perdu."""
        import io, contextlib
        m, defaut = self.module_redirige()
        ancien = os.getcwd()
        os.chdir(self.d)
        self.addCleanup(os.chdir, ancien)
        self.write("app-health-check.conf", "ODOO_PUBLIC_HOST=www.exemple.org\n")
        e = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"HOME": os.path.join(self.d, "home-vide")}), contextlib.redirect_stderr(e):
            chemins = m.resolve_config_paths(None)
        self.assertEqual(chemins, [defaut + "app-health-check.conf"])
        self.assertFalse(os.path.exists("./app-health-check.conf"))
        self.assertEqual(m.load_config(chemins)["ODOO_PUBLIC_HOST"], "www.exemple.org")   # contenu conservé
        self.assertIn("Migration", e.getvalue())

    def test_affichage_des_fichiers_lus_et_des_options(self):
        import io, contextlib
        m = self.module()
        a = self.write("a.conf", "ODOO_PUBLIC_HOST=www.exemple.org\nADDITIONAL_PUBLIC_HOSTS=x.exemple.org y.exemple.org\nSMTP_HOST=smtp.exemple.org\nSMTP_PORT=465\n"
                                 "NOTIFY_EMAIL_TO=admin@exemple.org\nEXPECT_GOOGLE_OAUTH=true\n")
        b = self.write("b.conf", "EXPECT_RESTRICTED_ACCESS=true\nODOO_TEST_USER=u\nODOO_TEST_PASSWORD=p\n")
        def rendu(chemins, explicite=False):
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                m.show_config_read(m.load_config(chemins), chemins, explicite)
            return f.getvalue()
        out = rendu([a, b])
        self.assertIn(f"Configuration lue : {a}, puis {b} (le dernier l'emporte)", sans_date(out))
        self.assertIn("Options : --lang fr · site www.exemple.org + 2 autre(s) nom(s) · instance non publique : yes · connexion Google attendue : yes"
                      " · courriel : smtp.exemple.org:465 → admin@exemple.org · tests fonctionnels (JSON-RPC) : identifiants configurés", sans_origine(out))
        out = rendu([a], explicite=True)
        self.assertIn(f"{a} (demandé par -c/--config : aucun autre fichier n'est lu)", sans_date(out))
        self.assertIn("instance non publique : no", out)
        self.assertIn("identifiants absents (ignorés)", out)
        out = rendu([self.write("vide.conf", "")])
        self.assertIn("site (non défini)", out)
        self.assertIn("courriel : non configuré", out)

    @unittest.skipIf(os.geteuid() == 0, "fichier illisible seulement sans root (root lit tout)")
    def test_fichier_illisible_sans_root_signale_et_non_pris_pour_absent(self):
        """2.28 : un fichier de configuration présent mais illisible (600 root) est signalé ; s'il n'y en a pas d'autre, le programme
        s'arrête avec « run with sudo » au lieu de créer une configuration ou d'afficher « non configuré »."""
        home = os.path.dirname(self.path("home-illisible", "x"))
        perso = os.path.join(home, ".app-health-check.cfg")
        self.write("home-illisible/.app-health-check.cfg", "SMTP_HOST=smtp.exemple.org\n")
        os.chmod(perso, 0)
        prog = self.prepare("app-health-check.py")
        self.env["HOME"] = home
        rc, out, err = self.run_cmd(["python3", prog, "--check-email-dns"])
        if os.path.isfile("/etc/default/app-health-check.conf") and os.access("/etc/default/app-health-check.conf", os.R_OK):
            self.skipTest("une configuration système lisible existe sur cet hôte")
        self.assertEqual(rc, 2, err)
        self.assertIn("not readable without root", err)
        self.assertNotIn("creating", out)

    def test_programme_complet_lit_etc_default_puis_home(self):
        defaut = os.path.dirname(self.path("etc-default", "x")) + "/"
        prog = self.prepare("app-health-check.py", {"/etc/default/": defaut})
        home = os.path.dirname(self.path("home-vide", "x"))
        self.write("etc-default/app-health-check.conf", "ODOO_PUBLIC_HOST=www.exemple.org\nSMTP_HOST=smtp.exemple.org\nNOTIFY_EMAIL_TO=a@exemple.org\n")
        self.write("home-vide/.app-health-check.conf", "EXPECT_RESTRICTED_ACCESS=true\n")
        self.env["HOME"] = home
        rc, out, err = self.run_cmd(["python3", prog, "--check-email-dns"])      # affiche la configuration lue, sans vérifications réseau
        self.assertIn(f"Configuration lue : {defaut}app-health-check.conf, puis {home}/.app-health-check.conf (le dernier l'emporte)", sans_date(out))
        self.assertIn("site www.exemple.org", out)
        self.assertIn("instance non publique : yes", out)                       # vient du fichier de ~
        self.assertIn("courriel : smtp.exemple.org:587 → a@exemple.org", out)   # vient de /etc/default
