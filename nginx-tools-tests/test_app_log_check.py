"""app-log-check.py — bruit connu, regroupement de la section [3] avec la raison PostgreSQL, détection du service."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import unittest

from helpers import EnvTest

Q = ('odoo.sql_db: bad query: b"\\n WITH visitor AS (\\n INSERT INTO website_visitor (\\n partner_id, access_token) '
     "VALUES (NULL, '0fe1e11ea990d5b994fc670f51aaa834')\\n ON CONFLICT (access_token) DO UPDATE SET visit_count = 2\\n\"")
JOURNAL = "\n".join([
    "2026-09-24 00:05:20,773 306478 ERROR linux_meetup_odoo_18_dev odoo.addons.web.controllers.binary: .map should have been generated through debug assets, (version 058194b most likely outdated)",
    "2026-09-24 02:11:31,398 3224 ERROR linux_meetup_odoo_18_dev odoo.addons.web.controllers.binary: .map should have been generated through debug assets, (version 6d84ab9 most likely outdated)",
    *[f"2026-09-23 23:28:5{i},858 28054{i} ERROR linux_meetup_odoo_18 {Q}\nERROR: could not serialize access due to concurrent update" for i in range(3)],
    *[f"2026-09-23 23:28:5{i},100 28055{i} ERROR linux_meetup_odoo_18 {Q}" for i in (6, 7)],
    "2026-09-24 01:00:00,000 2805 ERROR linux_meetup_odoo_18 odoo.sql_db: bad query: b\"INSERT INTO res_partner (name) VALUES ('x')\"",
    'ERROR: duplicate key value violates unique constraint "res_partner_uniq"',
    "2026-09-24 22:20:43,888 1830 ERROR linux_meetup_odoo_18 odoo.addons.auth_oauth.controllers.main: Exception during request handling",
    "Traceback (most recent call last):",
    '  File "/opt/odoo/erplibre/odoo18.0/odoo/addons/auth_oauth/models/res_users.py", line 120, in _auth_oauth_validate',
    "Exception: invalid_request",
    "2026-09-26 19:15:23,393 1853 ERROR linux_meetup_odoo_18 odoo.addons.bus.websocket: Exception occurred during websocket request handling",
    "Traceback (most recent call last):",
    '  File "/opt/odoo/erplibre/odoo18.0/odoo/addons/web_editor/models/ir_websocket.py", line 26, in _build_bus_channel_list',
    "    raise AccessDenied()",
    "odoo.exceptions.AccessDenied: Access Denied",
    "2026-09-26 19:16:00,000 1853 ERROR linux_meetup_odoo_18 odoo.http: Exception during request handling",
    "Traceback (most recent call last):",
    '  File "/opt/odoo/erplibre/odoo18.0/odoo/addons/base/models/res_users.py", line 900, in check',
    "odoo.exceptions.AccessDenied: Access Denied",
]) + "\n"


class ChkOdooLogs(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("app-log-check.py")
        self.write("journal.txt", JOURNAL)
        self.mock("journalctl", f"cat {self.d}/journal.txt")
        self.mock("systemctl", '[[ "$2" == erplibre.service ]] && echo "erplibre.service enabled enabled"; exit 0')
        self.env["APP_LOG_CHECK_STATE_DIR"] = os.path.dirname(self.path("state", "x"))
        # white list and places: paths isolated by helpers (empty); a test that wants entries uses self.liste_blanche() / self.lieux()

    def test_ligne_en_base64_jamais_affichee_comme_message(self):
        """Une trace dont la dernière ligne est une image en base64 : le titre du groupe est la ligne utile précédente, jamais le bloc de données ; toute ligne affichée est abrégée."""
        spec = __import__("importlib.util").util.spec_from_file_location("alc", self.prog)
        alc = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(alc)
        blob = "xWdp8XOCBQsDVq06i3nz59Az0Mdc8XrL7bfQ1d1HNt2OXByPMrl0nVwmJK/FxMCcPhYvX8qiJYtZtnIlF1x0kWw80OJjhlALKqKQWqWsaklCuSQetdLFWjol43Q+h1XC8uS7iZeibgNqDqxpZd7MpaAtg8mm8XXu5VNYXdu2NLRniQVWE0d6HmcCkmyKRFuFKFiTzWHUt1GCSBTkXTtNAFKShuKIESXGQy5HLPuKlKximWoiwhgcf0a2ZjwPo7"
        entree = ["2026-10-13 03:19:16,939 1983510 WARNING db odoo.addons.mass_mailing: This file could not be decoded", "Traceback (most recent call last):",
                  "  File \"x.py\", line 3, in f", "PIL.UnidentifiedImageError: cannot identify image file", blob]
        self.assertEqual(alc.extract_headline(entree), "PIL.UnidentifiedImageError: cannot identify image file")
        sans_exception = entree[:3] + ["données reçues non valides", blob]
        self.assertEqual(alc.extract_headline(sans_exception), "données reçues non valides")
        self.assertLessEqual(len(alc.abbreviate("a" * 500)), 200)
        self.assertNotIn(blob, alc.abbreviate("image " + blob))
        self.assertIn("[data: ", alc.abbreviate("image " + blob))

    def lancer(self, *args):
        rc, out, err = self.run_cmd(["python3", self.prog, "--init", *args])
        self.assertNotIn("Traceback", err, err)
        return out

    def test_errors_only_seulement_le_detail_des_erreurs(self):
        """2.14 : --errors-only = traces [2], autres erreurs [3] et diagnostics [5] ; ni sommaire, ni protocole [1], ni bruit connu [4], ni RÉSUMÉ."""
        out = self.lancer("--errors-only")
        self.assertIn("--- [2]", out)
        self.assertIn("--- [3]", out)
        self.assertNotIn("--- [1]", out)
        self.assertNotIn("--- [4]", out)
        self.assertNotIn("RÉSUMÉ", out)
        self.assertNotIn("SOMMAIRE", out.upper().split("--- [2]")[0].split("Fenêtre")[-1])
        self.assertIn("Access Denied", out)
        complet = self.lancer()
        self.assertIn("--- [4]", complet)                                  # without the option: unchanged

    def test_report_err(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--init", "--report-err"])
        self.assertNotIn("Traceback", err, err)
        self.assertIn("RAPPORT D'ERREURS (--report-err)", out)
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : app-log-check\.py v2\.\d+\.\d{8}\.\d{6} — commande : app-log-check\.py --init\n")
        self.assertIn(f"code de sortie {rc}", rapport)
        self.assertTrue(rapport.rstrip().endswith("FIN DU RAPPORT " + "=" * 38))

    def section(self, out, n):
        a = out.index(f"--- [{n}]")
        b = out.find("--- [", a + 5)
        return out[a:b if b > 0 else len(out)]

    # --- rapport par heure et par jour (--by-hour) ---------------------------------------------------------------------
    def horaire(self, jour, h, mi, s, pid, message):
        return f"{jour}T{h:02d}:{mi:02d}:{s:02d}-0400 odoo18 odoo[{pid}]: {message}"

    def journal_session(self, ips=("11.97.88.180",), restart=True):
        """Journal « -o short-iso » : rafale de « Session expired » (19 h, le 2026-10-02) suivis de leur requête, 404 à 21 h, erreurs
        à 03 h la veille, un conflit SQL sans gravité, et un redémarrage du service à 19 h 50."""
        l = []
        corps = lambda ip, page: (f'2026-10-02 23:58:47,740 1 INFO base werkzeug: {ip} - - [02/Oct/2026 23:58:47] "POST {page} HTTP/1.1" 200 - 1 0.000 0.003')
        sessions = "2026-10-02 23:58:47,700 1 INFO base odoo.http: Session expired"
        if restart:
            l.append("2026-10-02T19:50:00-0400 odoo18 systemd[1]: Started erplibre.service - ERPLibre.")
        for i in range(30):
            ip = ips[i % len(ips)]
            pid = 500 + i % 3
            l += [self.horaire("2026-10-02", 19 + (i >= 25), 58, i, pid, sessions),
                  self.horaire("2026-10-02", 19 + (i >= 25), 58, i, pid, corps(ip, "/web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config?x=1"))]
        for i in range(3):
            l.append(self.horaire("2026-10-02", 21, 10, i, 600, corps("45.33.32.156", "/wp-admin/").replace(" 200 ", " 404 ")))
        for i in range(2):
            l.append(self.horaire("2026-10-01", 3, 5, i, 700, "2026-10-01 07:05:00,000 1 ERROR base odoo.http: Exception during request handling 12345"))
        l.append(self.horaire("2026-10-01", 3, 6, 0, 700, "2026-10-01 07:06:00,000 1 WARNING base odoo.modules.loading: Attention module 7"))
        l += [self.horaire("2026-10-02", 20, 1, 0, 701, "2026-10-02 00:01:00,000 1 ERROR base odoo.sql_db: bad query: b' UPDATE \"discuss_channel_member\" SET x=1'"),
              self.horaire("2026-10-02", 20, 1, 0, 701, "ERROR: could not serialize access due to concurrent update"),
              self.horaire("2026-10-02", 20, 1, 1, 701, "2026-10-02 00:01:01,000 1 INFO base odoo.service.model: SERIALIZATION_FAILURE, 4 tries left")]
        self.write("journal.txt", "\n".join(l) + "\n")
        self.mock("journalctl", f'echo "$@" >> {self.d}/journalctl.log; cat {self.d}/journal.txt')

    def par_heure(self, *args):
        rc, out, err = self.run_cmd(["python3", self.prog, "--by-hour", *args])
        self.assertNotIn("Traceback", err, err)
        return rc, out, err

    def test_rapport_par_heure_et_par_jour(self):
        """--by-hour : table heure × jour, pics, pages en erreur, messages, « Session expired » rattaché à la page demandée."""
        self.journal_session()
        rc, out, err = self.par_heure()
        self.assertEqual(rc, 0, err)
        self.assertIn("RAPPORT DES PROBLÈMES PAR HEURE ET PAR JOUR — erplibre.service — 7 derniers jours", out)
        # table: 19 h = 25 "Session expired", 20 h = 5 + 1 SQL conflict, 21 h = 3 404 pages (on 10-02); 03 h = 3 (on 10-01)
        t = out[out.index("[1]"):out.index("[2]")]
        self.assertRegex(t, r"  19 h  \|\s+\.\s+25 \|\s+25 ")
        self.assertRegex(t, r"  20 h  \|\s+\.\s+6 \|\s+6 ")
        self.assertRegex(t, r"  21 h  \|\s+\.\s+3 \|\s+3 ")
        self.assertRegex(t, r"  03 h  \|\s+3\s+\. \|\s+3 ")
        self.assertRegex(t, r"  Total \|\s+3\s+34 \|\s+37")
        self.assertNotIn("  00 h  |", t)                                                       # only the hours concerned are listed
        self.assertIn("Heures sans problème : 00 h–02 h, 04 h–18 h, 22 h–23 h", t)
        self.assertIn("Heures les plus chargées : 19 h (25), 20 h (6), 03 h (3), 21 h (3)", t)
        # pages: "Session expired" attached to the NEXT request of the same process; identifiers and parameters removed
        p = out[out.index("[2]"):out.index("[3]")]
        self.assertRegex(p, r"\s+30  Session expirée /web/dataset/call_kw/ir\.config_parameter/get_web_dialog_size_config\n")
        self.assertRegex(p, r"\s+3  HTTP 404\s+/wp-admin/\n")
        self.assertIn("pics : 19 h (25), 20 h (5)", p)
        # messages: errors, warnings and SQL conflict (harmless), grouped without the numbers
        m = out[out.index("[3]"):out.index("[4]")]
        self.assertRegex(m, r"\s+2  ERREUR  .*Exception during request handling N")
        self.assertRegex(m, r"\s+1  AVERT\.\s+odoo\.modules\.loading: Attention module N")     # sans horodatage ni niveau
        self.assertIn("Conflit de mise à jour simultanée", m)
        self.assertIn("(sans gravité)", m)
        # window asked of journalctl, in local time, without touching the remembered position
        with open(os.path.join(self.d, "journalctl.log")) as f:
            self.assertIn("-o short-iso --no-pager --since -7 days", f.read())
        self.assertFalse(os.path.exists(os.path.join(self.env["APP_LOG_CHECK_STATE_DIR"], "x")))
        self.assertEqual(os.listdir(self.env["APP_LOG_CHECK_STATE_DIR"]) if os.path.isdir(self.env["APP_LOG_CHECK_STATE_DIR"]) else [], [])

    def test_session_expired_un_seul_client_ou_plusieurs(self):
        """Diagnostic de « Session expired » : une seule adresse = onglet resté ouvert ; plusieurs adresses = sessions perdues."""
        self.journal_session()
        rc, out, err = self.par_heure("--days", "3")
        d = " ".join(out[out.index("[4]"):].split())
        self.assertIn("« Session expired » : 30 fois", d)
        self.assertIn("11.97.88.180", d)
        self.assertIn("(100 %)", d)
        self.assertIn("VERDICT : UN SEUL CLIENT (11.97.88.180", d)
        self.assertIn("Ce n'est PAS un défaut du serveur", d)
        self.assertIn("Redémarrages du service dans la période : 1 ; 83 % des « Session expired » surviennent dans l'heure qui suit", d)
        # Several addresses, just after a restart: sessions lost at restart
        self.journal_session(ips=("11.97.88.180", "11.101.16.52", "11.114.10.1"))
        d = self.par_heure()[1]
        d = " ".join(d[d.index("[4]"):].split())
        self.assertIn("VERDICT : PLUSIEURS CLIENTS, surtout juste après un redémarrage", d)
        self.assertIn("data_dir/sessions", d)
        # Several addresses, without restart: other cause
        self.journal_session(ips=("11.97.88.180", "11.101.16.52", "11.114.10.1"), restart=False)
        d = self.par_heure()[1]
        d = " ".join(d[d.index("[4]"):].split())
        self.assertIn("PLUSIEURS CLIENTS, sans lien avec un redémarrage", d)
        self.assertIn("Redémarrages du service dans la période : 0.", d)

    PC1, PC2 = "11.97.88.180", "11.126.46.49"

    def journal_deux_postes(self, avec_connexions=True):
        """Un compte, DEUX adresses (deux PC) : rafales de « Session expired » sur PC1 à 09 h et 15 h, sur PC2 à 11 h ; chacune précédée
        (sauf si avec_connexions est faux) d'une connexion du même compte depuis L'AUTRE adresse, 2 à 3 minutes avant."""
        l, jour = [], "2026-10-02"
        corps = lambda ip: (f'2026-10-02 23:58:47,740 1 INFO base werkzeug: {ip} - - [02/Oct/2026 23:58:47] '
                            '"POST /web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config HTTP/1.1" 200 - 1 0.000 0.003')
        def connexion(h, mi, ip):
            return self.horaire(jour, h, mi, 0, 800, "2026-10-02 00:00:00,000 1 INFO base odoo.addons.base.models.res_users: "
                                f"Login successful for db:base login:m@exemple.org from {ip}")
        def rafale(h, mi, ip, n, pid):
            for i in range(n):
                l.append(self.horaire(jour, h, mi, i, pid, "2026-10-02 23:58:47,700 1 INFO base odoo.http: Session expired"))
                l.append(self.horaire(jour, h, mi, i, pid, corps(ip)))
        l.append(connexion(7, 0, self.PC1))
        l.append(connexion(7, 5, self.PC2))                                 # le compte est connu sur les deux adresses
        if avec_connexions:
            l.append(connexion(8, 58, self.PC2))
        rafale(9, 0, self.PC1, 30, 501)
        if avec_connexions:
            l.append(connexion(10, 58, self.PC1))
        rafale(11, 0, self.PC2, 17, 502)
        if avec_connexions:
            l.append(connexion(14, 57, self.PC2))
        rafale(15, 0, self.PC1, 30, 503)
        self.write("journal.txt", "\n".join(l) + "\n")
        self.mock("journalctl", f'echo "$@" >> {self.d}/journalctl.log; cat {self.d}/journal.txt')

    def test_deux_postes_un_compte_rafales_apres_une_connexion_ailleurs(self):
        """Un compte sur DEUX adresses (deux PC) n'est pas « plusieurs clients » : c'est un seul compte. Les rafales qui commencent juste
        après une connexion du même compte depuis l'autre adresse montrent que se connecter sur un poste invalide la session de l'autre."""
        self.journal_deux_postes()
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; printf "auth_session_timeout\\nbase_user_login_one_session\\n"')
        rc, out, err = self.par_heure()
        self.assertEqual(rc, 0, err)
        d = " ".join(out[out.index("[4]"):].split())
        self.assertIn(f"{self.PC1} 60 (78 %) [compte : m@exemple.org]", d)
        self.assertIn(f"{self.PC2} 17 (22 %) [compte : m@exemple.org]", d)
        self.assertIn("Rafales (séries espacées de moins de 10 min) : 3 ; 3 commencent moins de 5 min après une connexion du même compte depuis une autre adresse.", d)
        self.assertIn(f"{self.PC1} (30 événement(s)) ← m@exemple.org connecté depuis {self.PC2}", d)
        self.assertIn("Modules installés dont le nom évoque les sessions ou la connexion : auth_session_timeout, base_user_login_one_session", d)
        self.assertIn(f"VERDICT : UN SEUL COMPTE (m@exemple.org) sur 2 adresses ({self.PC1}, {self.PC2})", d)
        self.assertIn("3 rafale(s) sur 3 commencent juste après une connexion du même compte depuis une autre adresse : se connecter sur un poste "
                      "semble INVALIDER la session de l'autre (une seule session par compte). Odoo CE n'impose pas cela", d)
        with open(os.path.join(self.d, "runuser.log")) as f:
            appel = f.read()
        self.assertIn("-u postgres -- psql -d base -tA -c", appel)
        self.assertIn("ir_module_module", appel)
        self.assertNotRegex(appel.upper(), r"\b(INSERT|UPDATE|DELETE|DROP|ALTER)\b")                  # lecture seule

    def test_deux_postes_sans_connexion_prealable_et_modules_illisibles_ou_absents(self):
        self.journal_deux_postes(avec_connexions=False)
        d = " ".join(self.par_heure()[1].split())
        self.assertIn("Rafales (séries espacées de moins de 10 min) : 3 ; 0 commencent", d)
        self.assertIn("Les rafales ne suivent pas une connexion depuis une autre adresse : ce n'est pas une session unique par compte.", d)
        self.assertIn("Modules installés évoquant les sessions ou la connexion : illisibles (PostgreSQL inaccessible, ou root requis).", d)   # runuser absent
        self.mock("runuser", "exit 0")
        d = " ".join(self.par_heure()[1].split())
        self.assertIn("Modules installés dont le nom évoque une limite de sessions : aucun (Odoo CE autorise normalement plusieurs sessions simultanées", d)

    def test_table_sans_separateur_de_milliers_et_volume_du_journal(self):
        """Dans la table, « 10 510 » à côté d'autres cellules se lisait comme trois nombres : chiffres collés. Ligne de volume du journal."""
        l = [self.horaire("2026-10-02", 9, 10, i % 60, 600, '2026-10-02 13:10:00,000 1 INFO base werkzeug: 45.33.32.156 - - [02/Oct/2026 13:10:00] "GET /absent HTTP/1.1" 404 - 1 0.0 0.0')
             for i in range(1200)]
        self.write("journal.txt", "\n".join(l) + "\n")
        out = self.par_heure()[1]
        t = out[out.index("[1]"):out.index("Heures sans problème")]                               # la TABLE seulement
        self.assertRegex(t, r"  09 h  \|\s+1200 \|\s+1200  █")
        self.assertRegex(t, r"  Total \|\s+1200 \|\s+1200")
        self.assertNotIn("1 200", t)
        self.assertRegex(out, r" Journal : 1 200 lignes \(≈ \d+ Mo\) sur 7 jours ; « Session expired » et leurs requêtes : ≈ 0 lignes \(0 %\)\.")
        self.assertRegex(out, r"1 200  HTTP 404\s+/absent")                                         # totals in prose keep their separator

    def test_lieu_partage_adresse_partagee_et_pas_un_seul_onglet(self):
        """Adresse d'un lieu [partagée] : le tableau des clients nomme le lieu, et le verdict ne conclut pas à « un seul onglet » : plusieurs
        personnes peuvent se trouver derrière cette adresse."""
        self.journal_session(ips=("11.97.88.180",), restart=False)
        self.lieux("11.97.88.0/24   # ETS - Université   [partagée]\n")
        d = " ".join(self.par_heure()[1].split())
        self.assertIn("11.97.88.180 30 (100 %) ETS - Université", d)
        self.assertIn("VERDICT : ADRESSE PARTAGÉE (11.97.88.180 — ETS - Université, 100 %). Plusieurs personnes se trouvent derrière cette adresse", d)
        self.assertNotIn("UN SEUL CLIENT", d)
        # Without a place: the usual interpretation
        self.lieux("")
        d = " ".join(self.par_heure()[1].split())
        self.assertIn("VERDICT : UN SEUL CLIENT (11.97.88.180", d)

    def test_rapport_par_heure_adresse_de_l_equipe_nommee_et_cas_limites(self):
        self.journal_session()
        self.liste_blanche("11.97.88.180  # Étienne (Bell — adresse actuelle)\n")
        out = self.par_heure()[1]
        self.assertIn("11.97.88.180", out)
        self.assertRegex(out, r"11\.97\.88\.180\s+30  \(100 %\)  Étienne \(Bell\)")                      # short label of the team
        self.assertIn("VERDICT : UN SEUL CLIENT (11.97.88.180 — Étienne (Bell), 100 %)", out)
        # Log without any problem
        self.write("journal.txt", "2026-10-02T10:00:00-0400 odoo18 odoo[1]: 2026-10-02 14:00:00,000 1 INFO base werkzeug: 1.2.3.4 - - \"GET / HTTP/1.1\" 200 - 1 0.0 0.0\n")
        self.assertIn("Aucun problème dans la fenêtre", self.par_heure()[1])
        # --days invalide, BigBlueButton (journaux en fichiers : non pris en charge, dit clairement)
        rc, out, err = self.run_cmd(["python3", self.prog, "--by-hour", "--days", "0"])
        self.assertEqual(rc, 2)
        rc, out, err = self.run_cmd(["python3", self.prog, "--by-hour", "--app", "bbb"])
        self.assertEqual(rc, 2)
        self.assertIn("--by-hour : disponible pour le journal d'Odoo", err)

    # --- sommaire et diagnostics des erreurs de courriel ------------------------------------------------------------------
    def entree_courriel(self, ts, mid, exception, detail, pid=803748):
        return [f"{ts} {pid} ERROR linux_meetup_odoo_18 odoo.addons.mail.models.mail_mail: failed sending mail (id: {mid}) due to Échec d'envoi de l'e-mail",
                "Traceback (most recent call last):", '  File "/opt/odoo/odoo/addons/base/models/ir_mail_server.py", line 769, in send_email',
                "    smtp.send_message(message, smtp_from, smtp_to_list)", f"smtplib.{exception}: {detail}",
                "During handling of the above exception, another exception occurred:", "Traceback (most recent call last):",
                'odoo.addons.base.models.ir_mail_server.MailDeliveryException: ("Échec d\'envoi de l\'e-mail", '
                f'"Échec de l\'envoi de l\'e-mail via le serveur SMTP \'None\'.\\n{exception}: {detail}")']

    def journal_courriels(self):
        """Les trois erreurs du rapport d'odoo18 : 5 × 452 (limite par session), 4 × 503 (cascade), 1 × 550 (expéditeur) — plus du bruit connu."""
        l = []
        for i in range(5):
            l += self.entree_courriel(f"2026-10-06 20:51:16,{400 + i}", 7404 + i, "SMTPDataError", "(452, b'4.4.5 Maximum number of messages per session exceeded.')")
        for i in range(4):
            l += self.entree_courriel(f"2026-10-06 20:51:16,{660 + i}", 7409 + i, "SMTPSenderRefused", "(503, b'5.5.1 Multiple MAIL commands not allowed.', 'admin@exemple.org')")
        l += self.entree_courriel("2026-09-08 22:30:48,391", 7171, "SMTPDataError", "(550, b'You are not allowed to send emails as \"etienne@exemple.org\" "
                                                                              "(header From) while using \"admin@exemple.org\" as envelope sender (MAIL FROM: ...). Please fix.')", 3975575)
        l += [f"2026-10-05 16:06:5{i},077 803742 INFO linux_meetup_odoo_18 odoo.addons.base.models.ir_model: Access Denied by ACLs for operation: write, uid: 31, model: website.page"
              for i in range(3)]
        self.write("journal.txt", "\n".join(l) + "\n")

    def faux_postgresql(self, serveurs="", parametres="", etats="", jours="", sujets=""):
        """runuser simulé : répond à chaque requête de lecture selon son contenu ; journalise les appels."""
        self.mock("runuser", f'''echo "$@" >> {self.d}/runuser.log
case "$*" in
 *ir_mail_server*) printf '{serveurs}';;
 *ir_config_parameter*) printf '{parametres}';;
 *"GROUP BY state"*) printf '{etats}';;
 *"to_char(date"*) printf '{jours}';;
 *"left(COALESCE(g.subject"*) printf '{sujets}';;
esac''')

    def test_sommaire_et_diagnostics_des_courriels_non_envoyes(self):
        """4 (retour d'essai) : « les gens n'ont pas reçu leur courriel d'inscription » : un SOMMAIRE en tête, puis pour chaque erreur reconnue la
        cause et la solution, et l'état réel des courriels dans Odoo (lu en lecture seule)."""
        self.journal_courriels()
        self.faux_postgresql(parametres="mail.catchall.domain\\037exemple.org\\nmail.default.from\\037notifications\\n",
                             etats="sent\\037120\\nexception\\0379\\noutgoing\\0373\\n", jours="2026-10-06\\0379\\n",
                             sujets="Bienvenue sur la plateforme\\0377\\nVotre inscription\\0372\\n")
        out = self.lancer()
        propre = " ".join(out.replace("\u00a0", " ").split())
        sommaire = out[out.index("--- SOMMAIRE ---"):out.index("--- [1]")]
        self.assertLess(out.index("--- SOMMAIRE ---"), out.index("--- [1]"))                      # the summary is AT THE TOP
        self.assertIn("[!]  COURRIEL        10 échec(s) d'envoi (10 courriel(s) distinct(s)), du 2026-09-08 22:30:48 au 2026-10-06 20:51:16 : "
                      "5 × limite de messages par connexion (452), 4 × « MAIL multiple » (503), 1 × expéditeur refusé (550)", sommaire)
        self.assertIn("des personnes n'ont PAS reçu leur courriel (inscription, invitation…) : cause et solution en [5]", sommaire)
        self.assertIn("[!]  TRACES PYTHON   10 occurrence(s) en 3 groupe(s), dont 10 liée(s) aux courriels → [2]", sommaire)
        self.assertIn("[ok] PROTOCOLE       rien", sommaire)
        self.assertIn("[i]  BRUIT CONNU     3 message(s) sans gravité → [4]", sommaire)
        d5 = " ".join(self.section(out, 5).replace("\u00a0", " ").split())
        # 452 : limite par connexion
        self.assertIn("le serveur SMTP limite le nombre de messages par connexion (452 4.4.5) — 5 occurrence(s)", d5)
        self.assertIn("courriels (id) : 7404, 7405, 7406, 7407, 7408", d5)
        self.assertIn("réutilisant UNE connexion SMTP pour tout le lot", d5)
        self.assertIn("créer ou modifier la clé « mail.session.batch.size » avec une valeur INFÉRIEURE à la limite du serveur de courriel (essayer 10", d5)
        self.assertIn("Renvoyer les courriels déjà en échec", d5)
        # 503 : cascade du 452
        self.assertIn("« Multiple MAIL commands not allowed » (503), en cascade après un autre échec — 4 occurrence(s)", d5)
        self.assertIn("Conséquence du refus 452", d5)
        # 550: sender, with the two addresses found in the error
        self.assertIn("l'adresse « De » n'est pas celle de l'expéditeur autorisé par le serveur de courriel (550) — 1 occurrence(s)", d5)
        self.assertIn("Constaté : De : etienne@exemple.org ; expéditeur de l'enveloppe (compte SMTP) : admin@exemple.org (1×)", d5)
        self.assertIn("Filtre De » (From filter)", d5)
        # state read in Odoo
        self.assertIn("État des courriels dans Odoo (lecture seule, base linux_meetup_odoo_18, 7 derniers jours)", d5)
        self.assertIn("Serveurs de courrier sortant : AUCUN enregistré — Odoo utilise les réglages smtp_* de odoo.conf", d5)
        self.assertIn("mail.session.batch.size : non défini — Odoo envoie jusqu'à 1000 courriels par connexion SMTP", d5)
        self.assertIn("Autres paramètres mail.* : mail.catchall.domain = exemple.org ; mail.default.from = notifications", d5)
        self.assertIn("Courriels : 120 envoyé(s), 9 en ÉCHEC D'ENVOI (à renvoyer), 3 en attente", d5)
        self.assertIn("Échecs par jour : 2026-10-06 (9)", d5)
        self.assertIn("Sujets en échec : « Bienvenue sur la plateforme » (7) ; « Votre inscription » (2)", d5)
        self.assertIn("Causes et solutions : section [5].", propre)
        # READ ONLY: transaction forced to read-only by PostgreSQL, no write in the queries, never a recipient's address
        with open(os.path.join(self.d, "runuser.log")) as f:
            appels = f.read()
        self.assertIn("PGOPTIONS=-c default_transaction_read_only=on psql -d linux_meetup_odoo_18", appels)
        self.assertNotRegex(appels.upper(), r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b")
        self.assertIn("JOIN mail_message g ON g.id = m.mail_message_id", appels)                   # the subject is in mail_message (mail.mail inherits from it), not in mail_mail
        self.assertNotIn("COALESCE(subject", appels)                                                 # old faulty query: mail_mail has no subject column
        self.assertNotIn("email_to", appels)
        self.assertNotIn("recipient", appels)
        self.assertNotRegex(appels, r"smtp_pass|smtp_user|smtp_authentication")                    # jamais d'identifiant ni de mot de passe SMTP lus
        self.assertIn("key !~* '(secret|password|passwd|token|apikey|private)'", appels)             # parameter keys that suggest a secret: excluded

    def test_diagnostic_courriel_serveur_deja_regle_postgresql_illisible_et_autres_erreurs(self):
        self.journal_courriels()
        self.faux_postgresql(serveurs="3\\037Courriel organisme\\037smtp.exemple.org\\037587\\037starttls\\037admin@exemple.org\\037t\\n",
                             parametres="mail.session.batch.size\\03710\\n", etats="exception\\0372\\n")
        d5 = " ".join(self.section(self.lancer(), 5).replace("\u00a0", " ").split())
        self.assertIn("Serveur sortant : « Courriel organisme » (smtp.exemple.org:587, starttls), filtre De « admin@exemple.org »", d5)
        self.assertIn("mail.session.batch.size : 10 (si les erreurs 452 continuent, choisir une valeur plus petite)", d5)
        self.assertNotIn("AUCUN enregistré", d5)
        # Without PostgreSQL (runuser absent): the diagnosis is still given, the state is said unreadable
        os.remove(os.path.join(self.d, "bin", "runuser"))
        d5 = " ".join(self.section(self.lancer(), 5).replace("\u00a0", " ").split())
        self.assertIn("Pourquoi : Odoo envoie les courriels en attente par lots", d5)
        self.assertIn("illisible (PostgreSQL inaccessible, ou root requis)", d5)

    def test_autres_diagnostics_smtp_et_aucun_faux_positif(self):
        """Authentification, relais, serveur injoignable : reconnus ; une erreur SANS contexte SMTP (« Connection refused » ailleurs) : jamais classée courriel."""
        l = self.entree_courriel("2026-10-06 20:00:00,100", 1, "SMTPAuthenticationError", "(535, b'5.7.8 Username and Password not accepted.')")
        l += self.entree_courriel("2026-10-06 20:00:01,100", 2, "SMTPRecipientsRefused", "{'x@exemple.org': (554, b'5.7.1 Relay access denied')}")
        l += self.entree_courriel("2026-10-06 20:00:02,100", 3, "SMTPServerDisconnected", "Connection unexpectedly closed: timed out")
        l += ["2026-10-06 20:00:03,100 77 ERROR linux_meetup_odoo_18 odoo.addons.base.models.res_partner: Connection refused par le service de géocodage",
              "Traceback (most recent call last):", "ConnectionRefusedError: [Errno 111] Connection refused"]
        self.write("journal.txt", "\n".join(l) + "\n")
        out = self.lancer()
        sommaire = out[out.index("--- SOMMAIRE ---"):out.index("--- [1]")]
        self.assertIn("3 échec(s) d'envoi", sommaire)
        self.assertIn("1 × authentification refusée (535), 1 × relais refusé, 1 × serveur SMTP injoignable", sommaire)
        d5 = " ".join(self.section(out, 5).replace("\u00a0", " ").split())
        for titre in ("le serveur SMTP refuse l'identifiant ou le mot de passe (535)", "le serveur SMTP refuse de relayer", "le serveur SMTP est injoignable"):
            self.assertIn(titre, d5)
        self.assertIn("mot de passe d'application", d5)
        self.assertIn("TRACES PYTHON   4 occurrence(s) en 4 groupe(s), dont 3 liée(s) aux courriels", sommaire)        # la 4e (sans contexte SMTP) n'en fait pas partie

    def test_sans_erreur_connue_pas_de_section_5(self):
        """Sans erreur reconnue : le sommaire existe (tout « rien » ou bruit), aucune section [5] ni accès à PostgreSQL."""
        self.write("journal.txt", JOURNAL)
        self.faux_postgresql()
        out = self.lancer()
        self.assertIn("--- SOMMAIRE ---", out)
        self.assertNotIn("--- [5]", out)
        self.assertNotIn("COURRIEL", out.split("--- [1]")[0])
        self.assertFalse(os.path.exists(os.path.join(self.d, "runuser.log")), "aucune requête à la base sans diagnostic de courriel")

    def test_bruit_connu_classe_a_part(self):
        s4 = self.section(self.lancer(), 4)
        self.assertIn("[2x] Carte de source (.map)", s4)
        self.assertIn("[3x] Conflit de mise à jour simultanée", s4)          # reason confirmed in the log
        self.assertIn("Connexion OAuth (Google) refusée", s4)
        self.assertIn("[1x] Abonnement websocket refusé par web_editor", s4)            # 1.7 : bug Odoo 18 connu
        self.assertIn("[1x] odoo.exceptions.AccessDenied", self.section(self.lancer(), 2),
                      "un AccessDenied AILLEURS que dans web_editor doit rester signalé")

    def test_refus_de_droits_acl_expliques_par_utilisateur(self):
        """2.8 : « Access Denied by ACLs for operation: write, uid: 506, model: event.event » (niveau INFO, à chaque
        page d'événement) : classé en bruit connu, détaillé par utilisateur ; identifiant de connexion lu dans
        PostgreSQL quand c'est possible, sinon lien vers la fiche."""
        ligne = ("2026-10-02 03:02:{s:02d},865 50239{p} INFO linux_meetup_odoo_18 odoo.addons.base.models.ir_model: "
                 "Access Denied by ACLs for operation: {op}, uid: {uid}, model: {m}\n")
        with open(os.path.join(self.d, "journal.txt"), "a") as f:
            for i in range(5):
                f.write(ligne.format(s=i, p=i, op="write", uid=506, m="event.event"))
            f.write(ligne.format(s=9, p=1, op="unlink", uid=7, m="res.partner"))
        out = self.lancer()
        s4 = self.section(out, 4)
        self.assertIn("[6x] Vérification de droits refusée (Access Denied by ACLs, niveau INFO)", s4)
        self.assertIn("5x  write sur event.event — utilisateur uid 506 (fiche : /web#id=506&model=res.users&view_type=form)"
                      " — base linux_meetup_odoo_18", s4)
        self.assertIn("1x  unlink sur res.partner — utilisateur uid 7", s4)
        self.assertNotIn("Access Denied by ACLs", self.section(out, 3))
        # Identifiant lu dans PostgreSQL (lecture seule, en tant que postgres)
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; [[ "$*" == *"WHERE u.id = 506"* ]] && '
                             'echo "benevole@exemple.org (Bénévole, portail/public)"; exit 0')
        s4 = self.section(self.lancer(), 4)
        self.assertIn("5x  write sur event.event — utilisateur uid 506 : benevole@exemple.org (Bénévole, portail/public)", s4)
        with open(os.path.join(self.d, "runuser.log")) as f:
            appel = f.read()
        self.assertIn("-u postgres -- psql -d linux_meetup_odoo_18 -tAc SELECT", appel)

    def test_section3_regroupee_avec_raison_postgresql(self):
        """1.4 : 15 blocs de requête identiques ; la raison PostgreSQL (ligne « ERROR: ») restait cachée."""
        s3 = self.section(self.lancer(), 3)
        self.assertIn("[2x] odoo.sql_db: requête SQL en échec sur « website_visitor » — raison PostgreSQL absente", s3)
        self.assertIn("« res_partner » — ERROR: duplicate key value violates unique constraint", s3)
        self.assertNotIn("could not serialize", s3, "un conflit confirmé ne doit pas rester en [3]")

    def test_detection_service_par_nom_exact(self):
        """1.3 : « erplibre.service » est une sous-chaîne de « erplibre_erplibre.service »."""
        self.mock("systemctl", '[[ "$2" == erplibre_erplibre.service ]] && echo "erplibre_erplibre.service enabled enabled"; exit 0')
        out = self.lancer("--verbose")
        self.assertIn("service : erplibre_erplibre.service", out)

    def test_verbose_affiche_les_commandes(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--init", "--verbose"])
        self.assertIn("+ journalctl -u erplibre.service", err + out)


if __name__ == "__main__":
    unittest.main()
