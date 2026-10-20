"""Refonte 2.0 : profils d'application (détection, --app, APP_PROFILE), migration des anciens chemins, et chaque
programme en mode BigBlueButton (configuration réelle BBB 3.0.37 : bigbluebutton.access.log, TLS par HAProxy,
bbb-web.log, pas de capteur catch-all)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import glob
import os
import unittest

from helpers import EnvTest, SCRIPTS_DIR, LISTE_EXEMPLE

BBB_LOG = ('203.0.113.20 - - [27/Sep/2026:10:00:01 -0400] "GET /html5client/join HTTP/1.1" 200 5120 "-" "Mozilla/5.0 Chrome/152"\n'
           '45.9.8.7 - - [27/Sep/2026:10:05:00 -0400] "GET /.env HTTP/1.1" 404 146 "-" "curl/8.5.0"\n'
           '45.9.8.7 - - [27/Sep/2026:10:05:01 -0400] "GET /.git/config HTTP/1.1" 404 146 "-" "curl/8.5.0"\n'
           '45.9.8.7 - - [27/Sep/2026:10:05:02 -0400] "GET /wp-login.php HTTP/1.1" 404 146 "-" "curl/8.5.0"\n')


def systemctl_unites(*unites):
    """Faux systemctl : list-unit-files ne connaît que les unités données."""
    liste = " ".join(unites)
    return f'for u in {liste}; do [[ "$1" == list-unit-files && "$2" == "$u" ]] && echo "$u enabled"; done; exit 0'


class Profils(EnvTest):
    def setUp(self):
        super().setUp()
        del self.env["APP_PROFILE"]                                   # détection réelle
        self.prog = self.prepare("nginx-log-audit.sh")
        self.apps = os.path.join(os.path.dirname(self.prog), "apps")

    def detecter(self, *unites, force=""):
        self.mock("systemctl", systemctl_unites(*unites))
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{self.apps}/_profile.sh"; charger_profil_app "{self.apps}" "{force}" && echo "$APP_NAME"'])
        rcp, outp, errp = self.run_cmd(["python3", "-c", f'import sys; sys.path.insert(0, "{self.apps}"); import _profile as p\n'
                                        f'try: print(p.charger_profil_app("{self.apps}", "{force}" or None)["APP_NAME"])\n'
                                        f'except p.ProfilError as e: print("ERREUR", e)'])
        return (out.strip() or err.strip()), (outp.strip())

    def test_detection_identique_bash_et_python(self):
        for unites, attendu in ((("erplibre_erplibre.service",), "odoo"), (("bbb-web.service",), "bbb")):
            with self.subTest(unites=unites):
                b, p = self.detecter(*unites)
                self.assertEqual(b, attendu)
                self.assertEqual(p, attendu)

    def test_aucune_ou_plusieurs_applications_demande_app(self):
        for unites, motif in (((), "aucune application reconnue"), (("erplibre.service", "bbb-web.service"), "plusieurs applications")):
            with self.subTest(unites=unites):
                b, p = self.detecter(*unites)
                self.assertIn(motif, b)
                self.assertIn(motif, p)
                self.assertIn("--app=NOM", b)

    def test_app_force_et_nom_inconnu(self):
        self.assertEqual(self.detecter("erplibre.service", "bbb-web.service", force="bbb"), ("bbb", "bbb"))
        b, p = self.detecter(force="moodle")
        self.assertIn("profil d'application inconnu : moodle", b)
        self.assertIn("disponibles : bbb odoo", p)

    def test_profil_vide_refuse(self):
        open(os.path.join(self.apps, "bbb.conf"), "w").close()
        b, p = self.detecter(force="bbb")
        self.assertIn("profil invalide", b)
        self.assertIn("profil invalide", p)

    def test_profils_complets(self):
        requises = {"APP_NAME", "APP_LABEL", "DETECT_UNITS", "DETECT_FILES", "SERVICES", "ACCESS_LOGS", "ERROR_LOGS", "CATCHALL_LOG",
                    "APP_LOG_KIND", "APP_LOG_FILES", "TLS_TERMINATION", "HEALTH_CHECKS", "ODOO_SPECIFIC_STEPS", "HARDENING_CONFIG"}
        import sys
        sys.path.insert(0, os.path.join(SCRIPTS_DIR, "apps"))
        import _profile
        for f in ("odoo", "bbb"):
            with self.subTest(profil=f):
                p = _profile.lire_profil(os.path.join(SCRIPTS_DIR, "apps", f"{f}.conf"))
                self.assertEqual(requises - set(p), set(), "clés manquantes")
                self.assertEqual(p["APP_NAME"], f)


class ProfilsLivres(unittest.TestCase):
    """Tout fichier apps/*.conf est chargé comme PROFIL d'application : la liste de l'équipe, d'abord livrée sous le nom
    apps/team-ips.conf, faisait échouer tous les programmes (« profil invalide ») — elle s'appelle apps/team-ips.list."""
    def test_chaque_conf_de_apps_est_un_profil(self):
        for f in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "apps", "*.conf"))):
            with self.subTest(fichier=os.path.basename(f)):
                self.assertRegex(open(f, encoding="utf-8").read(), r"(?m)^APP_NAME=", "fichier .conf de apps/ qui n'est pas un profil")
        self.assertFalse(os.path.isfile(os.path.join(SCRIPTS_DIR, "apps", "team-ips.list")),
                         "ancienne liste d'adresses (personnelles) : remplacée par /etc/default/nginx-tools-white-list.conf, jamais livrée")


class DurcissementBBB(EnvTest):
    """2.10 : règles de sécurité BBB dans un fichier À NOUS (/etc/bigbluebutton/nginx/), jail nginx-blocked-probes."""
    def test_regles_et_jail_installees_restaurees_si_refus(self):
        f2b = os.path.dirname(self.path("f2b", "x"))
        prog = self.prepare("nginx-hardening.sh", {"/etc/fail2ban": f2b, "/var/log/nginx": os.path.dirname(self.path("nl", "x")),
                                                   "/etc/default/": os.path.dirname(self.path("etc-default", "x")) + "/"})
        bbb = os.path.dirname(self.path("bbb-nginx", "x"))
        self.env.update(APP_PROFILE="bbb", NGINX_HARDENING_BBB_NGINX_DIR=bbb,
                        NGINX_HARDENING_LOGROTATE_DIR=os.path.dirname(self.path("lr", "x")),
                        NGINX_HARDENING_JOURNALD_DIR=os.path.dirname(self.path("jd", "x")))
        self.mock("nginx", '[[ "$1" == -T ]] && echo "    include /etc/bigbluebutton/nginx/*.nginx;"; exit 0')
        self.mock("curl", 'printf "HTTP/1.1 200 OK\\r\\n\\r\\n"')
        self.mock("fail2ban-client", "exit 0")
        fichier = os.path.join(bbb, "zz-nginx-hardening-security.nginx")
        rc, out, err = self.run_cmd(["bash", prog])
        self.assertIn("Règles de sécurité BBB absentes — --update les installera", out)
        self.assertIn("Jail nginx-blocked-probes absente", out)
        self.assertFalse(os.path.exists(fichier))
        rc, out, err = self.run_cmd(["bash", prog, "--update"])
        self.assertIn("Règles de sécurité BBB installées", out)
        regles = open(fichier).read()
        self.assertIn("location ~ /\\.(?!well-known/) {", regles)
        self.assertRegex(regles, r"access_log \S*/blocked-probes\.log;")   # (chemin réécrit vers un dossier de test)
        self.assertNotIn("proxy_", regles)                                        # aucun emplacement de BBB touché
        self.assertRegex(open(os.path.join(f2b, "jail.d", "nginx-blocked-probes.conf")).read(), r"logpath  = \S*/blocked-probes\.log")
        # Fichier modifié à la main, puis nginx -t refuse la version régénérée : la version en place est restaurée
        with open(fichier, "w") as f:
            f.write("# version locale\n")
        self.mock("nginx", '[[ "$1" == -T ]] && echo "    include /etc/bigbluebutton/nginx/*.nginx;"; [[ "$1" == -t ]] && exit 1; exit 0')
        rc, out, err = self.run_cmd(["bash", prog, "--update"])
        self.assertIn("nginx -t refuse les règles de sécurité BBB — ancienne version restaurée", out)
        self.assertEqual(open(fichier).read(), "# version locale\n")
        self.assertNotIn("unbound variable", err)
        # fail2ban non démarré : cause dite, commande donnée (cas réel du serveur BBB de DEV)
        for f in ("jail.d", "filter.d"):
            os.remove(os.path.join(f2b, f, "nginx-blocked-probes.conf"))
        self.mock("fail2ban-client", "exit 1")
        self.mock("systemctl", '[[ "$1 $2" == "is-active fail2ban" ]] && { echo inactive; exit 3; }; exit 1')
        self.mock("nginx", '[[ "$1" == -T ]] && echo "    include /etc/bigbluebutton/nginx/*.nginx;"; exit 0')
        rc, out, err = self.run_cmd(["bash", prog, "--update"])
        self.assertIn("fail2ban n'est PAS démarré (inactive)", out)
        self.assertIn("systemctl enable --now fail2ban", out)


class HstsRedirection(EnvTest):
    """2.13 : réponse de « / » en redirection vers le même nom (BBB : « / » → « /b ») : page d'arrivée vérifiée ;
    HSTS présent à l'arrivée → avertissement ; absent partout → échec, conseil HAProxy « http-after-response »."""
    def lancer(self, hsts_arrivee):
        prog = self.prepare("nginx-hardening.sh", {"/etc/fail2ban": os.path.dirname(self.path("f2b", "x")),
                                                   "/var/log/nginx": os.path.dirname(self.path("nl", "x")),
                                                   "/etc/default/": os.path.dirname(self.path("etc-default", "x")) + "/"})
        self.env.update(APP_PROFILE="bbb", NGINX_HARDENING_BBB_NGINX_DIR=os.path.dirname(self.path("bbb", "x")),
                        NGINX_HARDENING_LOGROTATE_DIR=os.path.dirname(self.path("lr", "x")),
                        NGINX_HARDENING_JOURNALD_DIR=os.path.dirname(self.path("jd", "x")))
        self.mock("nginx", '[[ "$1" == -T ]] && printf "server {\\n    server_name bbb3.exemple.org;\\n}\\n"; exit 0')
        entete = 'printf "Strict-Transport-Security: max-age=31536000\\r\\n"' if hsts_arrivee else "true"
        self.mock("curl", 'url="${@: -1}"\n'
                          'case "$url" in\n'
                          '  */b) printf "HTTP/1.1 200 OK\\r\\n"; ' + entete + ';;\n'
                          '  */) printf "HTTP/1.1 301 Moved Permanently\\r\\nLocation: /b\\r\\n";;\n'
                          'esac')
        rc, out, err = self.run_cmd(["bash", prog])
        return out[out.index("--- 10)"):out.index("--- 11)")]

    def test_hsts_sur_la_page_d_arrivee_conforme(self):
        """2.15 : HSTS est enregistré par le navigateur sur la réponse finale : redirection sans HSTS mais arrivée avec
        → conforme ([OK]), ni avertissement ni échec (cas réel de BBB de PROD : « / » → /rooms/…/join)."""
        bloc = self.lancer(True)
        self.assertIn("HSTS présent — bbb3.exemple.org (la redirection HTTP 301 n'en porte pas, mais la page d'arrivée /b l'envoie : max-age=31536000", bloc)
        self.assertNotIn("[FAIL]", bloc)
        self.assertNotIn("[ATTN]", bloc)

    def test_hsts_absent_partout_echec_et_conseil_haproxy(self):
        bloc = self.lancer(False)
        self.assertIn("HSTS ABSENT — bbb3.exemple.org (HTTP 301, et sur la page d'arrivée /b)", bloc)
        self.assertIn("http-after-response set-header Strict-Transport-Security", bloc)
        self.assertIn("s'applique AUSSI aux redirections produites par HAProxy", bloc)


class Migration(EnvTest):
    """[3] Anciens fichiers renommés automatiquement, jamais d'écrasement."""
    def test_etat_nginx_log_audit_migre(self):
        prog = self.prepare("nginx-log-audit.sh", {"/var/log/nginx": os.path.dirname(self.path("nginx", "x"))})
        self.write("home/.local/state/chk-nginx-logs/bans.tsv", "2026-09-27 09:00\tbanni\t1.2.3.4\n")
        self.env["HOME"] = os.path.dirname(self.path("home", "x"))
        self.env.pop("NGINX_LOG_AUDIT_STATE_DIR", None)
        rc, out, err = self.run_cmd(["bash", prog, "--version"])
        rc, out, err = self.run_cmd(["bash", prog, "--ban", "127.0.0.1", "--yes"])          # refusé, mais migration faite
        self.assertIn("Migration (renommage des programmes, version 2.0)", err)
        self.assertTrue(os.path.isfile(self.path("home", ".local/state/nginx-log-audit/bans.tsv")))
        self.assertFalse(os.path.exists(self.path("home", ".local/state/chk-nginx-logs")))

    def test_fichiers_d_etat_en_anglais_migres(self):
        """2.2 : bannissements.tsv -> bans.tsv (contenu conservé), ip-publique -> public-ip."""
        prog = self.prepare("nginx-log-audit.sh")
        etat = os.path.dirname(self.path("etat", "x"))
        self.write("etat/bannissements.tsv", "2026-09-27 09:00\tbanni\t1.2.3.4\n")
        self.write("etat/ip-publique", "11.85.38.12\n")
        self.env["NGINX_LOG_AUDIT_STATE_DIR"] = etat
        self.run_cmd(["bash", prog, "--ban", "127.0.0.1", "--yes"])
        self.assertEqual(open(os.path.join(etat, "bans.tsv")).read(), "2026-09-27 09:00\tbanni\t1.2.3.4\n")
        self.assertTrue(os.path.isfile(os.path.join(etat, "public-ip")))
        self.assertFalse(os.path.exists(os.path.join(etat, "bannissements.tsv")))

    def test_etat_crowdsec_en_anglais_migre(self):
        prog = self.prepare("sync-crowdsec-blocklist.sh")
        etat = os.path.dirname(self.path("cs", "x"))
        for n in ("derniere-liste.txt", "derniere-liste.sha256", "ip-bloquees.tsv", "derniere-synchro", "dernier-changement-liste", "ip-publique"):
            self.write(f"cs/{n}", "x\n")
        self.env.update(SYNC_CROWDSEC_STATE_DIR=etat, SYNC_CROWDSEC_UFW_AFTER_INIT=self.path("ufw", "after.init"))
        self.run_cmd(["bash", prog, "--version"])
        self.assertEqual(sorted(os.listdir(etat)), ["blocked-ips.tsv", "last-list-change", "last-list.sha256", "last-list.txt", "last-sync", "public-ip"])

    def test_derniere_alerte_web_monitor_migree(self):
        prog = self.prepare("web-monitor.py")
        self.write("etat/derniere-alerte.json", '{"quand": "2026-09-27 10:00"}')
        self.write("etat/dernier-passage", "2026-09-27 10:00:00 — rien à signaler\n")
        self.env.update(WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("etat", "x")), WEB_MONITOR_LOG_DIR=os.path.dirname(self.path("log", "x")),
                        WEB_MONITOR_SYSTEMD_DIR=os.path.dirname(self.path("sd", "x")))
        self.mock_exit("systemctl", 1)
        self.run_cmd(["python3", prog, "--status"])
        self.assertTrue(os.path.isfile(self.path("etat", "last-alert.json")))
        self.assertTrue(os.path.isfile(self.path("etat", "last-run")))

    def test_jamais_d_ecrasement(self):
        prog = self.prepare("nginx-log-audit.sh")
        self.write("home/.local/state/chk-nginx-logs/ancien.txt", "ancien")
        self.write("home/.local/state/nginx-log-audit/nouveau.txt", "nouveau")
        self.env["HOME"] = os.path.dirname(self.path("home", "x"))
        self.run_cmd(["bash", prog, "--ban", "127.0.0.1", "--yes"])
        self.assertTrue(os.path.isfile(self.path("home", ".local/state/chk-nginx-logs/ancien.txt")), "ancien conservé")
        self.assertFalse(os.path.exists(self.path("home", ".local/state/nginx-log-audit/ancien.txt")))

    def test_etat_app_log_check_migre(self):
        prog = self.prepare("app-log-check.py")
        self.write("home/.local/state/chk-odoo-logs/erplibre.service.last", "2026-09-27 09:00:00")
        self.env["HOME"] = os.path.dirname(self.path("home", "x"))
        self.mock("journalctl", "exit 0")
        self.mock("systemctl", systemctl_unites("erplibre.service"))
        rc, out, err = self.run_cmd(["python3", prog])
        self.assertTrue(os.path.isfile(self.path("home", ".local/state/app-log-check/erplibre.service.last")), err)

    @unittest.skipUnless(os.geteuid() == 0, "la migration du timer exige root")
    def test_timer_surveillance_odoo_remplace_meme_intervalle(self):
        prog = self.prepare("web-monitor.py")
        sd = os.path.dirname(self.path("systemd", "x"))
        self.write("systemd/surveillance-odoo.timer", "[Timer]\nOnCalendar=*-*-* 00/2:05:00\nPersistent=true\n")
        self.write("systemd/surveillance-odoo.service", "[Service]\nExecStart=/root/scripts/surveillance-odoo.py\n")
        self.write("etat/chk-nginx-logs/access.pos", "12")
        self.mock("systemctl", f'echo "$*" >> {self.d}/systemctl.log; exit 0')
        self.env.update(WEB_MONITOR_SYSTEMD_DIR=sd, WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("etat", "x")),
                        WEB_MONITOR_LOG_DIR=os.path.dirname(self.path("log", "x")))
        rc, out, err = self.run_cmd(["python3", prog, "--status"])
        self.assertFalse(os.path.exists(os.path.join(sd, "surveillance-odoo.timer")))
        self.assertIn("00/2:05:00", open(os.path.join(sd, "web-monitor.timer")).read())
        self.assertIn(prog, open(os.path.join(sd, "web-monitor.service")).read())
        self.assertTrue(os.path.isfile(self.path("etat", "nginx-log-audit/access.pos")))
        self.assertIn("disable --now surveillance-odoo.timer", open(os.path.join(self.d, "systemctl.log")).read())


class BigBlueButton(EnvTest):
    def setUp(self):
        super().setUp()
        self.env["APP_PROFILE"] = "bbb"

    def test_nginx_log_audit_journal_bbb_sans_capteur(self):
        n = os.path.dirname(self.path("nginx", "x"))
        prog = self.prepare("nginx-log-audit.sh", {"/var/log/nginx": n})
        self.write("nginx/bigbluebutton.access.log", BBB_LOG)
        self.write("nginx/error.log", "")
        self.mock_exit("curl", 1); self.mock_exit("host", 1)
        self.env["NGINX_LOG_AUDIT_STATE_DIR"] = os.path.dirname(self.path("st", "x"))
        rc, out, err = self.run_cmd(["bash", prog, "--init", "--no-prompt"])
        self.assertNotIn("ARRÊT INATTENDU", err, err)
        self.assertIn("Rapport nginx — bbb", out)
        self.assertIn("Sans objet : pas de capteur catch-all dans la configuration de BigBlueButton", out)
        self.assertIn("Recherche de fichiers sensibles : 3", out)

    def test_app_log_check_fichier_bbb_regroupe_et_incremental(self):
        prog = self.prepare("app-log-check.py")
        log = self.write("bbb-web.log", "2026-09-27T10:00:01.456-04:00 bbb-web ERROR o.b.w.c.ApiController - Failed to create meeting 5678: timeout after 3000 ms\n"
                                        "2026-09-27T10:05:01.456-04:00 bbb-web ERROR o.b.w.c.ApiController - Failed to create meeting 9012: timeout after 3000 ms\n"
                                        "2026-09-27T10:06:00.000-04:00 bbb-web WARN  o.b.a.Redis - Slow message processing 250 ms\n")
        conf = os.path.join(os.path.dirname(prog), "apps", "bbb.conf")
        contenu = open(conf).read().replace("/var/log/bigbluebutton/bbb-web.log", log)
        open(conf, "w").write(contenu)
        self.env["APP_LOG_CHECK_STATE_DIR"] = os.path.dirname(self.path("st", "x"))
        rc, out, err = self.run_cmd(["python3", prog])
        self.assertIn("[2x] 2026-09-27T10:00:01.456-04:00 bbb-web ERROR", out)          # même erreur, numéros différents
        self.assertIn("RÉSUMÉ : 2 erreur(s) à examiner", out)
        with open(log, "a") as f:
            f.write("2026-09-27T11:00:00.000-04:00 bbb-web ERROR o.b.w.c.RecordingService - Recording 777 not found\n")
        rc, out, err = self.run_cmd(["python3", prog])
        self.assertIn("RÉSUMÉ : 1 erreur(s) à examiner", out)                         # seulement la nouvelle ligne

    def test_nginx_hardening_etapes_odoo_sans_objet_et_retention(self):
        prog = self.prepare("nginx-hardening.sh", {"/etc/default/": os.path.dirname(self.path("etc-default", "x")) + "/",
                                                   "/var/log/nginx": os.path.dirname(self.path("nl", "x")), "/var/www": os.path.dirname(self.path("www", "x"))})
        lr = self.write("logrotate.d/nginx", "/var/log/nginx/*.log {\n\tdaily\n\tmissingok\n\trotate 14\n\tcompress\n}\n")
        self.write("logrotate.d/fail2ban", "/var/log/fail2ban.log {\n    weekly\n    rotate 4\n}\n")
        self.env.update(NGINX_HARDENING_LOGROTATE_DIR=os.path.dirname(lr), NGINX_HARDENING_JOURNALD_DIR=os.path.dirname(self.path("systemd", "x")))
        self.mock("nginx", '[[ "$1" == -T ]] && echo "server_name bbb30.exemple.org;"; exit 0')
        self.mock("curl", 'printf "HTTP/1.1 200 OK\\r\\n\\r\\n"')                                 # HSTS absent (HAProxy)
        for t in ("systemctl", "ss", "ufw", "fail2ban-client", "logrotate"):
            self.mock_exit(t)
        self.liste_blanche(LISTE_EXEMPLE)
        # 2.7 : ignoreip vérifié aussi pour BBB (jail sshd), avec la liste blanche
        self.mock("fail2ban-client", 'case "$1 $2" in\n "status ") printf \'%s\\n\' \'`- Jail list: sshd\';;\n "get sshd") printf \'%s\\n\' \'These IP addresses/networks are ignored:\' \'`- 127.0.0.1/8\';;\nesac\n')   # apostrophes : accents graves de fail2ban non interprétés
        rc, out, err = self.run_cmd(["bash", prog])
        ligne = next(l for l in out.splitlines() if "adresses de l'équipe NON ignorées (jails : sshd)" in l)
        for ip in ("203.0.113.5", "100.64.0.21", "198.51.100.9"):
            self.assertIn(ip, ligne)
        self.assertNotIn("unbound variable", err)                   # 2.5 : PORT_EXPOSED, initialisée à l'étape 4 (Odoo) seulement
        self.assertIn("Application : BigBlueButton", out)
        self.assertIn("Sans objet pour BigBlueButton : odoo.conf", out)
        self.assertIn("Sans objet pour BigBlueButton : pas de capteur catch-all", out)
        self.assertIn("/etc/haproxy/haproxy.cfg", out)                                   # conseil HSTS adapté à HAProxy
        self.assertIn("--update passera à « rotate 92 »", out)
        self.assertIn("--update passera à « rotate 14 »", out)
        self.assertIn("MaxRetentionSec=3month", out)
        rc, out, err = self.run_cmd(["bash", prog, "--update"])
        self.assertRegex(open(lr).read(), r"\trotate 92\n")
        self.assertIn("rotate 14", open(os.path.join(os.path.dirname(lr), "fail2ban")).read())
        self.assertTrue(os.path.isfile(lr + ".before-nginx-hardening"))
        self.assertIn("MaxRetentionSec=3month", open(self.path("systemd", "journald.conf.d/90-nginx-hardening-retention.conf")).read())
        rc, out, err = self.run_cmd(["bash", prog])
        self.assertRegex(out, r"nginx : rotation quotidienne, 92 conservés ≈ 92 jours")
        # 2.3 : --log-retention-months 6 → rotate 183 (quotidien), 27 (hebdomadaire) ; journal : 3month → 6month
        # (valeur déjà fixée, mais dans le fichier de ce script et option explicite : mise à jour)
        rc, out, err = self.run_cmd(["bash", prog, "--update", "--log-retention-months", "6"])
        self.assertIn("Rétention des journaux (cible : 6 mois)", out)
        self.assertRegex(open(lr).read(), r"\trotate 183\n")
        self.assertIn("rotate 27", open(os.path.join(os.path.dirname(lr), "fail2ban")).read())
        conf = open(self.path("systemd", "journald.conf.d/90-nginx-hardening-retention.conf")).read()
        self.assertIn("MaxRetentionSec=6month", conf)
        self.assertNotIn("3month", conf)
        self.assertNotIn("${LOG_RETENTION_MONTHS}", conf)                              # valeur, pas la variable
        rc, out, err = self.run_cmd(["bash", prog, "--log-retention-months", "0"])
        self.assertEqual(rc, 1)
        self.assertIn("entre 1 et 24", err)
        # 2.5 : cas réel du serveur BBB — /var/log inscriptible par le groupe syslog : logrotate refuse tout fichier sans
        # directive « su » ; fail2ban.log ne tournait donc pas du tout, même avec une durée de conservation suffisante.
        f2b = os.path.join(os.path.dirname(lr), "fail2ban")
        with open(f2b, "w") as f:
            f.write("/var/log/fail2ban.log {\n    weekly\n    rotate 14\n    compress\n}\n")
        self.mock("logrotate", 'f="${@: -1}"; grep -qE "^[[:space:]]*su " "$f" && exit 0\n'
                               'echo "error: skipping \\"/var/log/fail2ban.log\\" because parent directory has insecure permissions" >&2; exit 1')
        rc, out, err = self.run_cmd(["bash", prog])
        self.assertIn("fail2ban : NE TOURNE PAS — logrotate refuse (error: skipping", out)
        self.assertNotIn("unbound variable", err)
        rc, out, err = self.run_cmd(["bash", prog, "--update"])
        self.assertRegex(open(f2b).read(), r"^/var/log/fail2ban\.log \{\n    su \S+ \S+\n    weekly\n    rotate 14\n")
        self.assertIn("directive « su", out)
        self.assertNotIn("refusé par logrotate", out)
        rc, out, err = self.run_cmd(["bash", prog])
        self.assertNotIn("NE TOURNE PAS", out)                      # accepté ensuite

    def test_web_monitor_summary_bbb(self):
        prog = self.prepare("web-monitor.py")
        n = os.path.dirname(self.path("nginx", "x"))
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        self.write("nginx/bigbluebutton.access.log", BBB_LOG.replace("27/Sep/2026", f"{T:%d}/{mois}/{T:%Y}"))
        self.write("nginx/rencontres_linux_quebec_prod-access.log", "")                 # autre site : ignoré pour BBB
        log = self.write("bbb-web.log", f"{T.isoformat()}T10:00:01.456-04:00 bbb-web ERROR x - y\n")
        conf = os.path.join(os.path.dirname(prog), "apps", "bbb.conf")
        contenu = open(conf).read().replace("/var/log/bigbluebutton/bbb-web.log", log)
        open(conf, "w").write(contenu)
        self.mock_exit("systemctl"); self.mock_exit("journalctl")
        self.env.update(WEB_MONITOR_NGINX_DIR=n, WEB_MONITOR_FAIL2BAN_LOG=self.path("f2b.log"),
                        WEB_MONITOR_LOGROTATE_DIR=os.path.dirname(self.path("lr", "x")))
        rc, out, err = self.run_cmd(["python3", prog, "--summary"])
        self.assertEqual(rc, 0, err)
        self.assertIn("BigBlueButton (forcée (--app=bbb))", out)
        ligne = lambda l: [x for x in out.splitlines() if x.strip().startswith(l)][0]
        v = ligne("Requêtes sur le site").split()[-5:]                          # aujourd'hui, J-1, J-2, 7 j, 30 j
        self.assertTrue([v[0], v[3], v[4]] == ["4", "4", "4"], ligne("Requêtes sur le site"))
        self.assertIn("BIGBLUEBUTTON", out)
        self.assertTrue((lambda v: [v[0], v[3], v[4]])(ligne("Erreurs BigBlueButton").split()[-5:]) == ["1", "1", "1"])
        self.assertNotIn("Échecs de connexion", out)                                     # pas de source pour BBB
        self.assertNotIn("Capteur catch-all (nginx)", out)
        self.assertIn("RESSOURCES", out)


class Ressources(EnvTest):
    """[8] Ce qui reste dans la VM ou le conteneur, et la consommation par service."""
    def test_ressources_et_alertes(self):
        prog = self.prepare("web-monitor.py")
        self.write("meminfo", "MemTotal:       16384000 kB\nMemAvailable:    1024000 kB\nSwapTotal:      2048000 kB\nSwapFree:       1024000 kB\n")
        self.mock("systemd-detect-virt", "echo lxc")
        self.mock("systemctl", f'''if [[ "$1" == show ]]; then
  n=$(cat {self.d}/n 2>/dev/null || echo 0); echo $((n+1)) > {self.d}/n
  for u in "$@"; do case "$u" in nginx.service|erplibre.service) ;; *) continue;; esac
    echo "Id=$u"; echo "LoadState=loaded"; echo "ActiveState=active"
    [[ $u == nginx.service ]] && echo "CPUUsageNSec=$((1000000000 + n*5000000))" && echo "MemoryCurrent=47185920" && echo "MemoryMax=infinity"
    [[ $u == erplibre.service ]] && echo "CPUUsageNSec=$((9000000000 + n*120000000))" && echo "MemoryCurrent=3328599654" && echo "MemoryMax=3500000000"
    echo "IOReadBytes=104857600"; echo "IOWriteBytes=52428800"; echo; done; fi; exit 0''')
        self.env.update(WEB_MONITOR_MEMINFO=self.path("meminfo"), WEB_MONITOR_NGINX_DIR=os.path.dirname(self.path("nginx", "x")),
                        WEB_MONITOR_FAIL2BAN_LOG=self.path("f2b.log"))
        rc, out, err = self.run_cmd(["python3", prog, "--summary"])
        r = out[out.index("RESSOURCES"):]
        self.assertIn("virtualisation : lxc", r)
        self.assertIn("Mémoire      : 1000,0 Mo disponibles sur 15,6 Go (6 % libres)", r)
        self.assertIn("échange : 1000,0 Mo utilisés sur 2,0 Go", r)
        self.assertRegex(r, r"erplibre\s+12,0 %\s+3,1 Go\s+3,3 Go \(95 %\)\s+100,0 Mo / 50,0 Mo")
        self.assertRegex(r, r"nginx\s+0,5 %\s+45,0 Mo\s+sans limite")
        self.assertIn("⚠ mémoire disponible faible (6 %)", r)
        self.assertIn("⚠ erplibre.service proche de sa limite mémoire (95 %)", r)

    def test_colonne_es_masquee_si_indisponible(self):
        """2.6 : E/S « n/d » partout (comptabilité désactivée, fréquent en LXC) : colonne masquée, note affichée."""
        prog = self.prepare("web-monitor.py")
        self.mock("systemctl", '''if [[ "$1" == show ]]; then for u in "$@"; do [[ $u == nginx.service ]] || continue
  echo "Id=$u"; echo "LoadState=loaded"; echo "ActiveState=active"; echo "CPUUsageNSec=100"; echo "MemoryCurrent=1000"
  echo "MemoryMax=infinity"; echo "IOReadBytes=[not set]"; echo "IOWriteBytes=[not set]"; echo; done; fi; exit 0''')
        self.env.update(WEB_MONITOR_NGINX_DIR=os.path.dirname(self.path("nginx", "x")), WEB_MONITOR_FAIL2BAN_LOG=self.path("f2b.log"))
        rc, out, err = self.run_cmd(["python3", prog, "--summary"])
        self.assertNotIn("lu / écrit", out)
        self.assertIn("lectures/écritures non mesurées", out)


if __name__ == "__main__":
    unittest.main()
