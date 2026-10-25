"""apps/_courriel.py — envoi de courriels commun (relais SMTP configuré par le setup) : configuration, mot de passe à part, pièces jointes trop grosses remplacées par un lien."""
import importlib.util
import email
import os
import socketserver
import subprocess
import sys
import threading

ENVIRONNEMENT = "commun"   # tous les serveurs

from helpers import EnvTest, script_path


def module():
    spec = importlib.util.spec_from_file_location("_courriel", script_path("apps/_courriel.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FauxSMTP(socketserver.StreamRequestHandler):
    """Serveur SMTP minimal (sans TLS ni identification) : garde les messages reçus dans self.server.recus."""
    def handle(self):
        self.wfile.write(b"220 faux ESMTP\r\n")
        data = False
        corps = []
        while True:
            ligne = self.rfile.readline()
            if not ligne:
                return
            if data:
                if ligne.rstrip(b"\r\n") == b".":
                    self.server.recus.append(b"".join(corps).decode("utf-8", "replace"))
                    data, corps = False, []
                    self.wfile.write(b"250 ok\r\n")
                else:
                    corps.append(ligne)
                continue
            commande = ligne[:4].upper()
            if commande == b"EHLO" or commande == b"HELO":
                self.wfile.write(b"250 faux\r\n")
            elif commande == b"DATA":
                data = True
                self.wfile.write(b"354 go\r\n")
            elif commande == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


class Courriel(EnvTest):
    def setUp(self):
        super().setUp()
        self.m = module()
        self.serveur = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FauxSMTP)
        self.serveur.daemon_threads = True
        self.serveur.recus = []
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.addCleanup(self.serveur.server_close)
        self.addCleanup(self.serveur.shutdown)
        self.port = self.serveur.server_address[1]
        self.cfg = {"MAIL_HOST": "127.0.0.1", "MAIL_PORT": str(self.port), "MAIL_SECURITY": "none", "MAIL_FROM": "alertes@exemple.org", "MAIL_TO": "equipe@exemple.org",
                    "MAIL_LINK_DIR": os.path.join(self.d, "liens"), "MAIL_PASSWORD_FILE": os.path.join(self.d, "mdp")}

    def test_lecture_de_la_configuration_sans_mot_de_passe(self):
        fichier = self.write("mail.conf", '# commentaire\nMAIL_HOST="mail.exemple.org"\nMAIL_PORT=587 # port\nAUTRE="x"\nMAIL_USER=\'admin@exemple.org\'\n')
        cfg = self.m.lire_config([fichier])
        self.assertEqual((cfg["MAIL_HOST"], cfg["MAIL_PORT"], cfg["MAIL_USER"]), ("mail.exemple.org", "587", "admin@exemple.org"))
        self.assertNotIn("AUTRE", cfg)
        self.assertEqual(self.m.lire_config([os.path.join(self.d, "absent")]), {})

    def test_securite_deduite_du_port(self):
        self.assertEqual(self.m.securite({"MAIL_PORT": "465"}), "ssl")
        self.assertEqual(self.m.securite({"MAIL_PORT": "587"}), "starttls")
        self.assertEqual(self.m.securite({"MAIL_SECURITY": "NONE"}), "none")

    def test_mot_de_passe_depuis_le_fichier_a_part_et_droits(self):
        self.write("mdp", "secret-de-test\n")
        self.assertEqual(self.m.lire_mot_de_passe(self.cfg), "secret-de-test")
        os.chmod(self.cfg["MAIL_PASSWORD_FILE"], 0o644)
        self.assertTrue(any("chmod 600" in p for p in self.m.verifier_droits(self.cfg["MAIL_PASSWORD_FILE"])))
        os.chmod(self.cfg["MAIL_PASSWORD_FILE"], 0o600)
        self.assertEqual(self.m.verifier_droits(self.cfg["MAIL_PASSWORD_FILE"]), [])
        self.assertTrue(self.m.verifier_droits(os.path.join(self.d, "absent")))

    def test_envoi_simple_et_non_configure(self):
        self.m.envoyer("Sujet de test", "Bonjour\n", cfg=self.cfg)
        self.assertEqual(len(self.serveur.recus), 1)
        self.assertIn("Subject: Sujet de test", self.serveur.recus[0])
        self.assertIn("To: equipe@exemple.org", self.serveur.recus[0])
        self.assertIn("Message-ID:", self.serveur.recus[0])
        with self.assertRaises(self.m.ErreurCourriel):
            self.m.envoyer("x", "y", cfg={})
        with self.assertRaises(self.m.ErreurCourriel):
            self.m.envoyer("x", "y", cfg={"MAIL_HOST": "127.0.0.1"})
        with self.assertRaises(self.m.ErreurCourriel):
            self.m.envoyer("x", "y", cfg=dict(self.cfg, MAIL_PORT="1"))                 # relais injoignable : message lisible, jamais de trace

    @staticmethod
    def _texte(brut):
        """Message décodé par le module email (les frontières MIME « ===…123== » contiennent des « = » que quopri prendrait pour des octets) : en-têtes + parties texte décodées."""
        message = email.message_from_string(brut)
        morceaux = [brut.split("\n\n", 1)[0]]
        for partie in message.walk():
            if partie.get_content_maintype() == "text":
                morceaux.append(partie.get_payload(decode=True).decode("utf-8", errors="replace"))
            nom = partie.get_filename()
            if nom:
                morceaux.append(f'filename="{nom}"')
        return "\n".join(morceaux)

    def test_piece_jointe_petite_jointe_grosse_remplacee_par_un_lien(self):
        petit = self.write("petit.txt", "abc")
        gros = os.path.join(self.d, "gros.bin")
        with open(gros, "wb") as f:
            f.write(b"x" * 5000)
        cfg = dict(self.cfg, MAIL_ATTACH_MAX_MB="0.002", MAIL_LINK_URL="https://exemple.org/pj/")          # 0.002 MB ~ 2097 bytes
        self.m.envoyer("Avec pièces", "Corps\n", pieces=[petit, gros], cfg=cfg)
        message = self._texte(self.serveur.recus[0])
        self.assertIn('filename="petit.txt"', message)
        self.assertNotIn('filename="gros.bin"', message)
        self.assertRegex(message, r"https://exemple\.org/pj/[\w-]{20,}/gros\.bin")
        jetons = os.listdir(cfg["MAIL_LINK_DIR"])
        self.assertEqual(len(jetons), 1)
        self.assertTrue(os.path.isfile(os.path.join(cfg["MAIL_LINK_DIR"], jetons[0], "gros.bin")))
        # without MAIL_LINK_URL: the path on the server is given
        self.m.envoyer("Sans URL", "Corps\n", pieces=[gros], cfg=dict(cfg, MAIL_LINK_URL=""))
        self.assertIn("copié sur le serveur", self._texte(self.serveur.recus[1]))

    def test_liens_anciens_supprimes(self):
        vieux = os.path.join(self.cfg["MAIL_LINK_DIR"], "ancien")
        os.makedirs(vieux)
        os.utime(vieux, (1, 1))
        self.m.nettoyer_liens(self.cfg["MAIL_LINK_DIR"], 30)
        self.assertFalse(os.path.exists(vieux))

    def test_ligne_de_commande_test_et_show_config_sans_secret(self):
        conf = self.write("mail.conf", "\n".join(f'{k}="{v}"' for k, v in self.cfg.items()) + "\n")
        self.write("mdp", "secret-de-test\n")
        env = dict(self.env, NGINX_TOOLS_MAIL_CONF=conf)
        r = subprocess.run([sys.executable, script_path("apps/_courriel.py"), "--send", "Par CLI", "--body-file", self.write("corps.txt", "Le corps\n")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Subject: Par CLI", self.serveur.recus[0])
        r = subprocess.run([sys.executable, script_path("apps/_courriel.py"), "--show-config"], capture_output=True, text=True, env=env)
        self.assertIn("MAIL_HOST=127.0.0.1", r.stdout)
        self.assertNotIn("secret-de-test", r.stdout + r.stderr)
        self.assertIn("mot de passe : présent", r.stdout)
        r = subprocess.run([sys.executable, script_path("apps/_courriel.py"), "--version"], capture_output=True, text=True, env=env)
        self.assertRegex(r.stdout, r"^_courriel\.py version 1\.\d+\.\d{8}\.\d{6}$")
        r = subprocess.run([sys.executable, script_path("apps/_courriel.py"), "--send", "x"], capture_output=True, text=True,
                           env=dict(env, NGINX_TOOLS_MAIL_CONF=os.path.join(self.d, "absent")), input="corps")
        self.assertEqual(r.returncode, 1)
        self.assertIn("non configuré", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
