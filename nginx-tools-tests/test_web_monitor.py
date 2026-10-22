"""web-monitor.py — décision d'alerte (bruit ignoré), un seul courriel, anti-rafale par élément, états séparés."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import datetime
import importlib.util
import os
import time
import re
import unittest

from helpers import sans_origine, EnvTest, script_path, ecrire_liste, sans_date

FAUX_SANITY = '''import os, sys
def resolve_config_paths(x): return ["x"]
def load_config(p): return {"SMTP_HOST": "smtp.exemple.org", "NOTIFY_EMAIL_TO": "admin@exemple.org"}
def send_email(cfg, subject, body): open(os.environ["TEST_COURRIELS"], "a").write(f"=== {subject}\\n{body}\\n")
if __name__ == "__main__":
    fails = open(os.environ["TEST_FAILS"]).read().split("\\n") if os.path.exists(os.environ["TEST_FAILS"]) else []
    fails = [f for f in fails if f]
    for f in fails: print(f"[FAIL] {f}")
    print(f"Résumé : {len(fails)} échec(s)"); sys.exit(1 if fails else 0)
'''
FAUX_NGINX = '''if [[ "$1" == --unban-check ]]; then echo "REEVALUATION DES BANNISSEMENTS $*"; exit 0; fi
if [[ "$1" == --ban ]]; then echo "--ban $*" >> "$TEST_BANS"; echo "Règle iptables ajoutée : DROP depuis $2"; exit 0; fi
echo "$NGINX_LOG_AUDIT_STATE_DIR" > "$TEST_ENV_NGINX"
cat <<'OUT'
--- [4] 404 correspondant a la règle de traversee ---
11.85.38.12 - - [25/Sep/2026:23:05:56 -0400] "GET /some/page?file=../conf/conf.php HTTP/1.1" 404 548
--- [6] 5xx (erreurs serveur) ---
RIEN
--- [7] Erreurs upstream (error.log) ---
2026/09/25 23:05:56 [error] 1#1: *1 access forbidden by rule, client: 11.85.38.12, server: www
--- [10] Enquête sur les IP suspectes ---
OUT
[[ -n "$TEST_BAN_IP" ]] && printf "  ▶ %s — 35 requête(s)\\n      Signes d'hostilité : 2 (rafale, fichiers sensibles)\\n      → Score 5/7 : bannissement recommandé.\\n" "$TEST_BAN_IP"
# Deuxième enquête de la même section, NON recommandée : ne doit jamais être proposée au bannissement (2.5)
[[ -n "$TEST_BAN_IP" ]] && printf "  ▶ 11.68.110.86 — 5 requête(s)\\n      Signes d'hostilité : 0\\n      → Score 3/7 — signes d'AUTOMATISATION seulement : robot probablement inoffensif\\n"
echo " RÉSUMÉ : au moins une section contient du nouveau"
'''


class Surveillance(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("web-monitor.py")
        self.write("prog/app-health-check.py", FAUX_SANITY)
        self.write("prog/nginx-log-audit.sh", FAUX_NGINX)
        self.write("prog/app-log-check.py", 'import os; open(os.environ["TEST_ENV_ODOO"],"w").write(os.environ.get("APP_LOG_CHECK_STATE_DIR",""))\n'
                                            'print("RÉSUMÉ : rien de suspect dans cette fenêtre.")\n')
        self.mock_exit("systemctl", 1)
        self.mock("logger", f"cat >> {self.d}/journal.txt")                  # enregistre chaque ligne reçue
        self.env.update(WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("state", "x")),
                        WEB_MONITOR_LOG_DIR=os.path.dirname(self.path("log", "x")),
                        TEST_COURRIELS=self.path("courriels.txt"), TEST_FAILS=self.path("fails.txt"),
                        TEST_ENV_NGINX=self.path("env-nginx"), TEST_ENV_ODOO=self.path("env-odoo"), TEST_BAN_IP="",
                        TEST_BANS=self.path("bans.log"))

    def passage(self, fails=(), ban_ip=""):
        self.write("fails.txt", "\n".join(fails))
        rc, out, err = self.run_cmd(["python3", self.prog], {"TEST_BAN_IP": ban_ip})
        self.assertNotIn("Traceback", err, err)
        return rc, out

    def courriels(self):
        p = self.path("courriels.txt")
        return open(p).read().split("=== ")[1:] if os.path.exists(p) else []

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_bruit_habituel_n_alerte_pas(self):
        """Traversée bloquée et « access forbidden » (dont les tests du serveur lui-même) : jamais d'alerte."""
        rc, out = self.passage()
        self.assertEqual(rc, 0)
        self.assertIn("rien à signaler", out)
        self.assertEqual(self.courriels(), [])

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_anti_rafale_par_element(self):
        rc, _ = self.passage(["HSTS présent — www : absent"], ban_ip="11.55.161.77")
        self.assertEqual(rc, 1)
        self.assertEqual(len(self.courriels()), 1, "un seul courriel groupé attendu")
        self.passage(["HSTS présent — www : absent"], ban_ip="11.55.161.77")
        self.assertEqual(len(self.courriels()), 1, "même situation : pas de nouveau courriel")
        self.passage([], ban_ip="11.55.161.77")
        self.assertEqual(len(self.courriels()), 1, "problème résolu : pas de nouveau courriel")
        self.passage(["Certificat TLS — www : expire dans 5 jours"], ban_ip="11.55.161.77")
        self.assertEqual(len(self.courriels()), 2, "nouveau problème (même outil, autre vérification) : courriel")
        self.assertIn("NOUVEAU depuis le courriel", self.courriels()[-1])
        self.assertIn("vérification en échec : Certificat TLS", self.courriels()[-1])
        self.passage(["Certificat TLS — www : expire dans 5 jours"], ban_ip="45.9.8.7")
        self.assertIn("bannissement recommandé pour 45.9.8.7", self.courriels()[-1])

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_etats_separes_des_lancements_manuels(self):
        self.passage()
        etat = self.env["WEB_MONITOR_STATE_DIR"]
        self.assertEqual(open(self.path("env-nginx")).read().strip(), os.path.join(etat, "nginx-log-audit"))
        self.assertEqual(open(self.path("env-odoo")).read().strip(), os.path.join(etat, "app-log-check"))

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_sommaire_des_points_en_fin_de_passage(self):
        """1.2 : seul le NOMBRE d'alertes était affiché (« Résultat : 4 alerte(s) »)."""
        _, out = self.passage(["HSTS présent — www : absent"], ban_ip="11.55.161.77")
        self.assertIn("Points à examiner (2) :", out)
        self.assertIn("■ app-health-check.py : vérification(s) en échec", out)
        self.assertIn("[FAIL] HSTS présent — www : absent", out)
        self.assertIn("▶ 11.55.161.77", out)
        self.assertLess(out.index("Points à examiner"), out.index("Rapport complet"))

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_journal_systeme_contient_le_detail(self):
        """1.2 : « journalctl -t web-monitor » ne montrait que le sujet du courriel."""
        self.passage(["HSTS présent — www : absent"])
        j = open(self.path("journal.txt")).read()
        self.assertIn("point(s) à examiner", j)
        self.assertIn("[FAIL] HSTS présent — www : absent", j)
        self.assertIn("Passage ", j)
        self.passage(["HSTS présent — www : absent"])                     # même situation : pas de nouveau détail
        j2 = open(self.path("journal.txt")).read()
        self.assertEqual(j2.count("[FAIL] HSTS présent"), 1, "détail répété alors que l'alerte est déjà signalée")
        self.assertIn("déjà signalées", j2)

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_proposition_less_en_fin_de_passage(self):
        """2.1 : dans un terminal, proposer d'ouvrir le rapport complet dans less ; jamais avec --no-pager."""
        self.mock("less", f'echo "less $*" > {self.d}/less.log')
        self.write("fails.txt", "HSTS présent — www : absent")
        texte, envoye = self.run_pty(["python3", self.prog], [(b"ouvrir le rapport complet dans less", b"\n", 0.2)])
        self.assertEqual(envoye, 1)
        self.assertRegex(open(os.path.join(self.d, "less.log")).read(), r"less -R .*\.log")
        os.remove(os.path.join(self.d, "less.log"))
        texte, envoye = self.run_pty(["python3", self.prog, "--no-pager"], [])
        self.assertNotIn("ouvrir le rapport complet dans less", texte)
        self.assertFalse(os.path.exists(os.path.join(self.d, "less.log")))

    def test_status_timer_absent_courriel_non_configure(self):
        """2.4 : --status disait seulement « inactive » et recopiait la sortie brute de systemctl."""
        self.mock_exit("systemctl", 1)
        self.write("etat/last-run", "2026-09-27 13:22:25 EDT — 2 alerte(s) — courriel non envoyé (journalctl -t surveillance-odoo)\n")
        self.env.update(WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("etat", "x")), WEB_MONITOR_SYSTEMD_DIR=os.path.dirname(self.path("sd", "x")))
        rc, out, err = self.run_cmd(["python3", self.prog, "--status"])
        self.assertEqual(rc, 0, err)
        self.assertIn("NON INSTALLÉ : la surveillance ne tourne pas automatiquement", out)
        self.assertIn("web-monitor.py --install-timer", out)
        self.assertIn("(message écrit par une version antérieure au renommage des programmes)", out)
        self.assertIn("Configuré : alertes envoyées à admin@exemple.org", out)   # configuration du faux app-health-check.py
        self.assertNotIn("0 timers listed", out)
        # Sans SMTP dans la configuration : l'état et la marche à suivre sont dits
        self.write("prog/app-health-check.py", FAUX_SANITY.replace('"SMTP_HOST": "smtp.exemple.org", "NOTIFY_EMAIL_TO": "admin@exemple.org"', ""))
        rc, out, err = self.run_cmd(["python3", self.prog, "--status"])
        self.assertIn("NON configuré : les alertes vont seulement dans le journal système", out)
        self.assertIn("renseigner SMTP_HOST et NOTIFY_EMAIL_TO", out)

    def test_status_timer_actif_et_passage_en_retard(self):
        self.write("sd/web-monitor.timer", "[Timer]\nOnCalendar=*-*-* 00/2:05:00\n")
        self.mock("systemctl", '''case "$1 $2" in
 "is-active web-monitor.timer") echo active;; "is-enabled web-monitor.timer") echo enabled;;
 "show web-monitor.timer") echo "NextElapseUSecRealtime=Sun 2026-09-27 20:05:00 EDT"; echo "LastTriggerUSec=Sun 2026-09-27 18:05:00 EDT";;
 "show web-monitor.service") echo "ExecMainStatus=1";; esac''')
        p = self.write("etat/last-run", "2026-09-27 13:22:25 EDT — rien à signaler\n")
        old = time.time() - 6 * 3600
        os.utime(p, (old, old))
        self.env.update(WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("etat", "x")), WEB_MONITOR_SYSTEMD_DIR=os.path.dirname(self.path("sd", "x")))
        rc, out, err = self.run_cmd(["python3", self.prog, "--status"])
        self.assertIn("État              : active, activé au démarrage", out)
        self.assertIn("toutes les 2 heure(s)", out)
        self.assertIn("Dernier résultat  : code 1 (alerte(s))", out)
        self.assertIn("(il y a 6 h)", out)
        self.assertIn("⚠ en retard", out)

    # --- 2.5 : bannissement en fin de passage, --ban-recommended ------------------------------------------------------
    def bans(self):
        p = self.path("bans.log")
        return open(p).read() if os.path.exists(p) else ""

    def test_regles_de_refus_ignorent_les_log_format(self):
        """Les lignes d'un log_format (« $http_user_agent » entre guillemets, sur plusieurs lignes) et des deny/return 403 réels : seuls les derniers sont des règles de refus."""
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        texte = ("# configuration file /etc/nginx/conf.d/odoo-global.conf:\n"
                 "log_format catchall444 '$remote_addr - [$time_local] \"$request\" $status host=\"$http_host\" '\n"
                 "                       '\"$http_referer\" \"$http_user_agent\" host=\"$host\"';\n"
                 "map $http_user_agent $is_bad_bot {\n"
                 "    deny all;\n")
        regles = wm.deny_rules(texte)
        self.assertEqual(len(regles), 2, regles)
        self.assertIn("map $http_user_agent $is_bad_bot {", regles[0])
        self.assertIn("deny all;", regles[1])
        self.assertFalse(any("log_format" in r or "catchall444" in r or "$http_referer" in r for r in regles))
        # WordPress : /wp-login.php n'est plus sensible
        wm.SENSITIVE_RE = wm.re.compile(wm.SENSITIVE_BASE + "|" + wm.SENSITIVE_WP)
        self.assertTrue(wm.SENSITIVE_RE.search("/wp-login.php"))
        wm.SENSITIVE_RE = wm.re.compile(wm.SENSITIVE_BASE)
        self.assertFalse(wm.SENSITIVE_RE.search("/wp-login.php"))
        self.assertTrue(wm.SENSITIVE_RE.search("/.env"))

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_echec_de_synchronisation_crowdsec_alerte(self):
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        alertes = wm.analyze_crowdsec(0, "Dernière synchronisation : 2026-09-20 03:17\n"
                                         "ÉCHEC EN COURS : 190 tentative(s) consécutive(s) depuis le 2026-09-20 04:17 (dernière : 2026-09-28 08:17)\n"
                                         "  impossible de créer les ipsets : commande ipset introuvable\n")
        self.assertEqual(wm.TR(alertes[0][0]), "sync-crowdsec-blocklist.sh : synchronisation en échec")
        self.assertIn("190 tentative(s)", alertes[0][1][0])
        self.assertEqual(alertes[0][2], ["crowdsec:echec"])

    def test_conseil_workers_odoo(self):
        """2.10 : configuration des workers (fichier + ligne de commande), pire cas mémoire, saturation, avis."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm._meminfo = lambda: {"MemTotal": 16 << 30}                         # RAM fixée : résultat indépendant de la machine
        conf = self.write("odoo.conf", "[options]\nworkers = 6\nmax_cron_threads = 2\nlimit_memory_hard = 4294967296\n")
        ligne_cmd = {"v": f"ExecStart={{ path=/x ; argv[]=/opt/erplibre/.venv/bin/python3 odoo-bin -c {conf} --workers=4 ; }}"}
        wm.run = lambda cmd, timeout=0: (0, ligne_cmd["v"])
        class C:
            def __init__(self, **v): self.v = v
            def get(self, k, i): return self.v.get(k, 0)
        def avis(compteurs, mem=4 << 30):
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.workers_advice("erplibre.service", compteurs, mem, 250 << 20)
            return f.getvalue()
        out = avis(C(workers_temps=3))
        self.assertIn("workers=4, max_cron_threads=2", out)                    # la ligne de commande l'emporte
        self.assertIn("(prioritaires, ligne de commande : workers)", out)
        self.assertIn("pire cas (limit_memory_hard × 6 workers et crons) : 24,0 Go pour 16,0 Go de RAM", out)
        self.assertIn("pire cas mémoire au-delà de la RAM", out)
        self.assertIn("3 arrêt(s) pour temps réel", out)
        self.assertIn("des requêtes dépassent limit_time_real", out)
        # Mode multithread : suggestion de workers
        self.write("odoo.conf", "[options]\nworkers = 0\n")
        ligne_cmd["v"] = f"ExecStart={{ path=/x ; argv[]=odoo-bin -c {conf} ; }}"
        out = avis(C())
        self.assertIn("mode multithread (workers=0)", out)
        self.assertRegex(out, r"essayer workers=\d+")
        # limit_memory_hard=0 (cas réel de PROD) : AUCUNE limite, jamais « pire cas 0 o » ni « aucun signe de saturation »
        self.write("odoo.conf", "[options]\nworkers = 3\nmax_cron_threads = 1\nlimit_memory_hard = 0\n")
        out = avis(C(), mem=1 << 30)
        self.assertIn("pire cas : ILLIMITÉ (limit_memory_hard=0)", out)
        self.assertIn("AUCUNE limite mémoire", out)
        self.assertNotIn("aucun signe de saturation", out)
        # Configuration saine, sans saturation
        self.write("odoo.conf", "[options]\nworkers = 3\nmax_cron_threads = 1\nlimit_memory_hard = 2147483648\n")  # 3 ≤ 2 × cœurs + 1 partout
        out = avis(C(), mem=1 << 30)
        self.assertIn("aucun signe de saturation", out)
        self.assertNotIn("pire cas mémoire au-delà", out)

    def test_recommandations_cas_bbb_prod(self):
        """2.11 : recommandations classées, sur les chiffres réels du sommaire BBB de PROD."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}
        wm.run = lambda cmd, timeout=0: (0, "")
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        dossier_bbb = os.path.dirname(self.path("bbb-nginx", "x"))               # jamais le vrai /etc/bigbluebutton
        os.environ["NGINX_HARDENING_BBB_NGINX_DIR"] = dossier_bbb
        self.addCleanup(os.environ.pop, "NGINX_HARDENING_BBB_NGINX_DIR", None)
        class C:
            v = {"transmises": 12890, "transmises_suspectes": 3087, "fichiers_sensibles": 3590, "erreurs5xx": 3}
            def get(self, k, i): return self.v.get(k, 0)
        class CSansAujourdhui(C):                                                  # aucune requête malveillante aujourd'hui
            def get(self, k, i): return 0 if (k == "transmises_suspectes" and i == 0) else self.v.get(k, 0)
        faits = {"non_filtrees": {"/.env": 108, "/.env.local": 95, "/.env.backup": 90}, "jails": {"sshd": 2},
                 "robots": {"Googlebot": 3002, "browser (Windows)": 1511, "libredtail-http": 607},
                 "refus_navigateurs": {"/b": 900, "/bigbluebutton/api/join": 400}}
        def recos(classe):
            g = io.StringIO()
            with contextlib.redirect_stdout(g):
                wm.recommendations(classe(), faits, {"site": ("daily", 14, 14, "/etc/logrotate.d/nginx"), "fail2ban": None})
            return g.getvalue()
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.recommendations(C(), faits, {"site": ("daily", 14, 14, "/etc/logrotate.d/nginx"), "fail2ban": None})
        out = f.getvalue()
        lignes = [l for l in out.splitlines() if re.match(r"  \d+\. \[", l)]
        self.assertIn("3087 requêtes malveillantes (/.env, /.env.local, /.env.backup…) ont atteint BigBlueButton en 7 jours (24 % du trafic transmis)", lignes[0])
        self.assertIn("[HAUTE]", lignes[0])
        # Règles pas encore installées : la commande qui les installe (jamais d'écriture à la main)
        self.assertIn("nginx-hardening.sh --update : il installe", out)
        self.assertIn("zz-nginx-hardening-security.nginx", out)
        self.assertNotIn("zz-security.nginx", out)
        self.assertIn("aucune jail fail2ban ne bannit les scanners web", lignes[1])
        self.assertTrue(any("Googlebot essaie d'indexer ce serveur BigBlueButton" in l and "[FAIBLE]" in l for l in lignes))
        self.assertTrue(any("navigateurs ordinaires" in l for l in lignes))
        self.assertIn("1300 visent des pages ordinaires (/b (900), /bigbluebutton/api/join (400))", out)
        self.assertFalse(any("pas de capteur catch-all" in l for l in lignes))    # sans objet sur BBB (HAProxy)
        # Règles installées : plus de recommandation si rien aujourd'hui ; sinon, vérifier l'inclusion
        with open(os.path.join(dossier_bbb, "zz-nginx-hardening-security.nginx"), "w") as fh:
            fh.write("# règles\n")
        self.assertNotIn("requêtes malveillantes", recos(CSansAujourdhui))
        out2 = recos(C)                                   # 2.36 : plus de commande à taper — essai fait par le programme
        self.assertIn("essai à travers nginx impossible", out2)
        self.assertNotIn("nginx -T | grep", out2)
        # Une seule correction pour plusieurs recommandations qui demandent la même commande (libellés réunis)
        self.assertEqual(out.count("(nginx-hardening.sh --update)"), 1, out)
        self.assertIn("CORRECTIONS QUE LE PROGRAMME PEUT FAIRE LUI-MÊME", out)
        self.assertTrue(any("journaux conservés moins de 3 mois : nginx (14 jours)" in l and "[FAIBLE]" in l for l in lignes))
        prios = [re.search(r"\[(HAUTE|MOYENNE|FAIBLE)", re.sub(r"\x1b\[[0-9;]*m", "", l)).group(1) for l in lignes]
        self.assertEqual(prios, sorted(prios, key=["HAUTE", "MOYENNE", "FAIBLE"].index))    # classées

    def test_liste_blanche_avec_plage(self):
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.WHITELIST.clear()
        wm.WHITELIST.update({"11.126.46.49", "11.148.77.0/24"})
        self.assertTrue(wm.in_whitelist("11.126.46.49"))
        self.assertTrue(wm.in_whitelist("11.148.77.5"))                   # cellulaire, adresse dynamique
        self.assertFalse(wm.in_whitelist("11.148.78.5"))
        self.assertFalse(wm.in_whitelist("2001:db8::1"))
        self.assertFalse(wm.in_whitelist("pas-une-ip"))

    def test_utilisation_par_la_liste_blanche(self):
        """2.19 : part du trafic de chaque adresse de la liste blanche (libellés de apps/team-ips.list), total."""
        import io, contextlib, datetime
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.run = lambda cmd, timeout=0: (0, "")
        wm.PROFILE = {"APP_LABEL": "Odoo"}
        ecrire_liste("NGINX_TOOLS_WHITE_LIST", "11.97.88.180   # Étienne (Bell)\n100.97.213.61   # Étienne (Tailscale : poste-r7-u24-1)\n11.137.240.62  # Mathis\n")
        wm.WHITELIST.clear()
        wm.WHITELIST.update(wm.team())
        st = {}
        for _ in range(30):
            wm.accumulate_ip(st, "11.97.88.180", "GET", "/odoo/discuss", "200", datetime.date(2026, 9, 28), [0, 1, 2])
        for _ in range(10):
            wm.accumulate_ip(st, "100.97.213.61", "GET", "/event", "200", datetime.date(2026, 9, 20), [2])
        class C:
            def get(self, k, i): return {0: 100, 1: 200, 2: 400}[i] if k == "requetes" else 0
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.show_whitelist(C(), {"stats_ip": st})
        out = f.getvalue()
        self.assertIn("UTILISATION PAR LA LISTE BLANCHE (équipe)", out)
        self.assertRegex(out, r"11\.97\.88\.180\s+Étienne \(Bell\)\s+30 \(30 %\)\s+30 \(15 %\)\s+30 \(8 %\)\s+30  2026-09-28")
        self.assertRegex(out, r"100\.97\.213\.61\s+Étienne \(Tailscale : poste-r7-u24-1\)\s+0 \(0 %\)\s+0 \(0 %\)\s+10 \(2 %\)")
        self.assertRegex(out, r"11\.137\.240\.62\s+Mathis .* aucune activité")
        self.assertRegex(out, r"Toute la liste blanche\s+30 \(30 %\)\s+30 \(15 %\)\s+40 \(10 %\)")

    def test_section_des_connexions_odoo_et_bbb(self):
        """2.13 : comptes connectés (Odoo) ou participants (BBB), IP bannie d'un utilisateur connecté signalée."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        faits = {"comptes": {}}
        wm.note_account(faits["comptes"], "etienne@exemple.org", "11.97.88.180", [0, 1, 2], "2026-09-28 12:02")
        wm.note_account(faits["comptes"], "etienne@exemple.org", "11.126.46.49", [2], "2026-09-10 08:00")
        wm.note_account(faits["comptes"], "benevole@exemple.org", "203.0.113.9", [1, 2], "2026-09-25 19:30")
        wm.note_account(faits["comptes"], "lecteur@exemple.org", "11.126.46.49", [2], "2026-09-24 07:42")   # adresse partagée
        def sortie(profil):
            wm.PROFILE = profil
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.show_accounts(faits, {"203.0.113.9"})
            return re.sub(r"\x1b\[[0-9;]*m", "", f.getvalue())
        out = sortie({"APP_NAME": "odoo", "APP_LABEL": "Odoo"})
        self.assertIn("CONNEXIONS À ODOO (connexions réussies, journal)", out)
        # Une ligne vide puis le nom, puis une information par ligne étiquetée
        self.assertRegex(out, r"\n\n  etienne@exemple\.org\n    Connexions      : aujourd'hui 1 · 7 j 1 · 30 j 2 — dernière 2026-09-28 12:02"
                              r"\n    Adresses IP     : 11\.97\.88\.180, 11\.126\.46\.49 \(partagée : 2 comptes\)")
        self.assertIn("203.0.113.9 (bannie)", out)
        self.assertIn("⚠ 1 adresse(s) d'utilisateurs connectés bannie(s) : 203.0.113.9", out)
        self.assertIn("PARTICIPANTS BIGBLUEBUTTON", sortie({"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}))

    def test_list_users_details_les_5_jours_les_plus_actifs_par_utilisateur(self):
        """2.43 : --list-users --details : les 5 jours les plus actifs de chaque compte, du plus actif au moins actif (requêtes par jour,
        toutes les adresses du compte) ; le sommaire garde « Jour le + actif » (un seul jour)."""
        journal = "\n".join(f"2026-09-2{i}T10:00:00-0400 odoo18 odoo[1]: x INFO base odoo.addons.base.models.res_users: "
                            f"Login successful for db:base login:etienne@exemple.org from {ip}" for i, ip in ((6, "203.0.113.5"), (7, "198.51.100.9")))
        self.write("journal.txt", journal + "\n")
        self.mock("journalctl", f"cat {self.d}/journal.txt")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        requetes = {20: 3, 21: 7, 22: 5, 23: 9, 24: 1, 25: 4, 26: 6}                      # jour de septembre -> requêtes de l'adresse 203.0.113.5
        lignes = [f'203.0.113.5 - - [{j}/Sep/2026:10:00:{i:02d} -0400] "GET /odoo/discuss HTTP/1.1" 200 100 "-" "x"\n' for j, n in requetes.items() for i in range(n)]
        lignes += [f'198.51.100.9 - - [21/Sep/2026:11:00:{i:02d} -0400] "GET /event HTTP/1.1" 200 100 "-" "x"\n' for i in range(4)]   # 2e adresse du compte
        lignes += [f'45.33.32.156 - - [24/Sep/2026:11:00:{i:02d} -0400] "GET /event HTTP/1.1" 200 100 "-" "x"\n' for i in range(50)]   # autre visiteur : ignoré
        os.makedirs(os.path.join(self.d, "nginx"), exist_ok=True)
        with open(os.path.join(self.d, "nginx", "site-access.log"), "w") as f:
            f.writelines(lignes)
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--details"],
                                    {"WEB_MONITOR_NGINX_DIR": os.path.join(self.d, "nginx")})
        self.assertNotIn("Traceback", err, err)
        propre = re.sub(r"\x1b\[[0-9;]*m", "", out).replace("\u202f", " ")
        self.assertIn("Jours + actifs  : 2026-09-21 (11 req.), 2026-09-23 (9 req.), 2026-09-26 (6 req.), 2026-09-22 (5 req.), 2026-09-25 (4 req.)", propre)
        self.assertNotIn("2026-09-20 (", propre)                                              # 6e et 7e jours : absents
        self.assertNotIn("2026-09-24 (", propre)                                              # (l'autre visiteur n'est pas ce compte)
        self.assertNotIn("Jour le + actif", propre)
        # Moins de 5 jours : tous, du plus actif au moins actif
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        a = {"req": 5, "pages": 5, "err": {}, "days": {"2026-09-01": 1, "2026-09-02": 3, "2026-09-03": 1}, "modules": {}, "urls": {}}
        self.assertIn("Jours + actifs  : 2026-09-02 (3 req.), 2026-09-01 (1 req.), 2026-09-03 (1 req.)", wm.TR("\n".join(wm.detail_lines(a, day_count=5))))

    def _journal_tableau(self, fuseau="-0400"):
        """Trois comptes : ana (2 connexions, session de 4 minutes + pause), zoe (1 connexion sans requête), bob (nom long) ; journal nginx de 3 adresses."""
        journal = "\n".join(f"{q}{fuseau} odoo18 odoo[1]: x INFO base odoo.addons.base.models.res_users: Login successful for db:base login:{l} from {ip}" for q, l, ip in [
            ("2026-09-20T10:00:00", "ana@exemple.org", "203.0.113.5"), ("2026-09-20T15:00:00", "ana@exemple.org", "203.0.113.5"),
            ("2026-09-25T09:00:00", "zoe@exemple.org", "198.51.100.9"), ("2026-09-22T08:00:00", "bob@exemple.org", "192.0.2.77")])
        self.write("journal.txt", journal + "\n")
        self.mock("journalctl", f"cat {self.d}/journal.txt")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        self.mock("runuser", 'printf "7\\037ana@exemple.org\\037Ana Tremblay\\037f\\n12\\037zoe@exemple.org\\037Zoé\\037t\\n'
                             '5\\037bob@exemple.org\\037Bob avec un nom vraiment beaucoup trop long pour la colonne\\037f\\n"')
        lignes = [f'203.0.113.5 - - [20/Sep/2026:10:0{m}:00 -0400] "GET /odoo HTTP/1.1" 200 1 "-" "x"\n' for m in (0, 1, 3, 4)]       # 10:00 à 10:04 = 5 minutes
        lignes += [f'203.0.113.5 - - [20/Sep/2026:15:0{m}:00 -0400] "GET /odoo HTTP/1.1" 200 1 "-" "x"\n' for m in (0, 2)]            # 15:00 à 15:02 = 3 minutes
        lignes += ['203.0.113.5 - - [20/Sep/2026:18:00:00 -0400] "GET /odoo HTTP/1.1" 200 1 "-" "x"\n']                               # trop tard : autre visite, pas de connexion
        lignes += ['192.0.2.77 - - [22/Sep/2026:08:00:00 -0400] "POST /web/login HTTP/1.1" 303 1 "-" "x"\n',
                   '192.0.2.77 - - [22/Sep/2026:08:40:00 -0400] "GET /odoo HTTP/1.1" 200 1 "-" "x"\n']                                # 40 min plus tard : > 30 min, hors session
        os.makedirs(os.path.join(self.d, "nginx"), exist_ok=True)
        with open(os.path.join(self.d, "nginx", "site-access.log"), "w") as f:
            f.writelines(lignes)
        return {"WEB_MONITOR_NGINX_DIR": os.path.join(self.d, "nginx")}

    def lignes_tableau(self, out):
        """Lignes du tableau (sans couleurs) et cellules de chaque ligne — 2.67 : aucune espace autour des cellules."""
        propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
        tableau = [l for l in propre.splitlines() if l.startswith("|")]
        return propre, tableau, [l.strip("|").split("|") for l in tableau]

    def test_list_users_table_compacte_colonnes_ajustees_et_minutes(self):
        """2.67 (remplace 2.45) : tableau COMPACT — aucune espace autour des cellules, chaque colonne aussi large que sa donnée (au moins 4, plafond du champ,
        « … » au-delà), titre coupé à cette largeur et sur DEUX lignes quand il a deux mots ; nombres alignés à droite ; UID, IP, connexions, minutes estimées."""
        env = self._journal_tableau()
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table"], env)
        self.assertNotIn("Traceback", err, err)
        propre, tableau, cellules = self.lignes_tableau(out)
        self.assertEqual(len({len(l) for l in tableau}), 1, tableau)                     # largeur identique partout
        largeurs = [len(x) for x in tableau[0].strip("|").split("|")]
        self.assertTrue(all(w >= 4 for w in largeurs), largeurs)
        self.assertTrue(set(tableau[0]) <= {"|", "-"})
        titre1, titre2 = cellules[1], cellules[2]                                        # deux lignes de titres
        col = {(a.strip(), b.strip()): i for i, (a, b) in enumerate(zip(titre1, titre2))}    # run-all 1.188 : colonnes par leur titre (2.70 en a ajouté 3)
        self.assertEqual([c.strip() for c in titre1[:3]], ["N°", "UID", "IP"])
        self.assertEqual(titre1[col[("Conn", "")]], "Conn")                                # « Connexions » coupé à la largeur des données (minimum 4)
        self.assertIn(("Première", "connexion"), col)                                      # deux mots : deux lignes
        self.assertIn(("Page", "lues"), col)
        ana = next(c for c in cellules if "ana@exemple.org" in "".join(c))
        self.assertEqual(ana[0], "   1")                                                  # nombres à droite, sans espace autour
        self.assertEqual(ana[2].strip(), "203.0.113.5")
        self.assertEqual(ana[3].strip(), "203.0.113.5 09-20 18:00")                        # 2.69 « IP vue » : sa dernière requête (18 h, après la connexion de 15 h)
        self.assertNotIn("Étiq", tableau[1])                                                # 2.69 : étiquettes hors du tableau par défaut
        self.assertEqual(ana[4].strip(), "Ana Tremblay")
        premiere = col[("Première", "connexion")]
        self.assertEqual([x.strip() for x in ana[premiere:premiere + 4]], ["2026-09-20 10:00", "2026-09-20 15:00", "2", "8"])    # 5 + 3 minutes
        self.assertEqual(ana[col[("Type", "")]].strip(), "interne")
        bob = next(c for c in cellules if "bob@exemple.org" in "".join(c))
        self.assertTrue(bob[4].endswith("…"))                                             # nom trop long : coupé (21 au plus)
        self.assertEqual(len(bob[4]), 21)
        self.assertEqual(bob[col[("Conn", "")]].strip(), "1")
        zoe = next(c for c in cellules if "zoe@exemple.org" in "".join(c))
        self.assertEqual(zoe[col[("Type", "")]].strip(), "portail")                         # « portail/public » raccourci
        self.assertNotIn(" | ", tableau[3])
        self.assertIn("Journaux d'accès nginx lus (1 fichier(s)", propre)
        self.assertIn("Total : 3 compte(s), 4 connexion(s), 10 minute(s) de connexion", propre)

    def test_list_users_table_avec_bannissements_enregistres(self):
        """2.68 : avec un fichier bans.tsv (bannissements de nginx-log-audit.sh), --table plantait (« KeyError: '2026-10-12 08:55' ») : la boucle de lecture
        réutilisait le nom de la liste des champs. Adresse bannie d'un compte : signalée."""
        env = self._journal_tableau()
        etat = os.path.join(self.d, "etat-nla")
        os.makedirs(etat, exist_ok=True)
        with open(os.path.join(etat, "bans.tsv"), "w") as f:
            f.write("2026-10-12 08:55\tbanni\t192.0.2.77\tmanuel\n2026-10-12 09:00\tbanni\t198.18.0.1\tmanuel\n")
        env = dict(env, NGINX_LOG_AUDIT_STATE_DIR=etat)
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--sort=last"], env)
        self.assertNotIn("Traceback", err, err)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("bob@exemple.org", out)
        self.assertIn("adresse(s) bannie(s) d'utilisateurs connectés : 192.0.2.77", out)

    def test_list_users_table_systemes_navigateurs_et_pages(self):
        """2.64 : --list-users --table : colonnes Systèmes, Navigateurs et Pages vues (User-Agent et pages des adresses du compte) ; robots et outils ne comptent pas ; --sort os / pages."""
        env = self._journal_tableau()
        win = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        andr = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
        mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        with open(os.path.join(self.d, "nginx", "site-access.log"), "a") as f:
            for ua in (win, win, andr, "curl/8.5.0"):
                f.write(f'203.0.113.5 - - [21/Sep/2026:10:00:00 -0400] "GET /odoo/discuss HTTP/1.1" 200 1 "-" "{ua}"\n')
            f.write(f'192.0.2.77 - - [22/Sep/2026:09:00:00 -0400] "GET /odoo HTTP/1.1" 200 1 "-" "{mac}"\n')
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table-fields", "login,systems,browsers,read", "--lang=fr"], env)
        self.assertNotIn("Traceback", err, err)
        propre, tableau, cellules = self.lignes_tableau(out)
        self.assertEqual([c.strip() for c in cellules[1]], ["Identifiant", "Systèmes", "Naviga", "Page"])   # --table-fields : ces colonnes, dans cet ordre ; « Navigateurs » coupé à la largeur de « Chrome »
        self.assertEqual([c.strip() for c in cellules[2]], ["", "", "", "lues"])
        ligne = {nom: [c.strip() for c in next(c for c in cellules if nom in "".join(c))] for nom in ("ana@", "bob@", "zoe@")}
        self.assertEqual(ligne["ana@"][1:], ["Windows,Android", "Chrome", "11"])                 # 2.67 : aucune espace dans les listes
        self.assertEqual(ligne["bob@"][1:], ["macOS", "Safari", "2"])
        self.assertEqual(ligne["zoe@"][1:], ["-", "-", "0"])
        self.assertIn("systèmes, navigateurs et pages vues", propre)
        self.assertEqual(self.run_cmd(["python3", self.prog, "--list-users", "--table-fields", "login,zzz"], env)[0], 2)      # champ inconnu : refusé
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--sort", "pages"], env)
        ordre = [m.group(0) for m in re.finditer(r"(ana|bob|zoe)@exemple", re.sub(r"\x1b\[[0-9;]*m", "", out))]
        self.assertEqual(ordre[:3], ["ana@exemple", "bob@exemple", "zoe@exemple"], out)            # décroissant : 11, 2, 0
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--lang=en", "--sort", "os", "--reverse"], env)
        self.assertNotIn("Traceback", err, err)
        self.assertIn("Syst", out)                                                     # titres coupés à la largeur des données (2.67)
        self.assertIn("Brow", out)

    def test_list_users_table_pages_ecrites_et_mo_recus_envoyes(self):
        """2.66 : colonnes Pages écrites (POST / PUT / DELETE qui changent quelque chose ; pas les lectures du client web ni le clavardage), Mo reçus
        ($body_bytes_sent) et Mo envoyés (« rl= » de nginx-odoo-config 1.11 ; « ? » sans ce champ) ; --sort written / received / sent."""
        env = self._journal_tableau()
        ua = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/131.0"
        with open(os.path.join(self.d, "nginx", "site-access.log"), "a") as f:
            for methode, url, code, octets, rl in (("POST", "/event/12/registration/confirm", 303, 900, 2_500_000), ("POST", "/my/account", 200, 1500, 1200),
                                                   ("POST", "/web/dataset/call_kw/res.partner/web_search_read", 200, 3_000_000, 800),
                                                   ("POST", "/websocket", 101, 0, 500), ("POST", "/web/dataset/call_kw/res.partner/write", 200, 200, 900),
                                                   ("GET", "/odoo/contacts", 200, 4_000_000, 600), ("POST", "/web/login", 403, 100, 300)):
                f.write(f'203.0.113.5 - - [21/Sep/2026:10:00:00 -0400] "{methode} {url} HTTP/1.1" {code} {octets} "-" "{ua}" host="exemple.org" rl={rl}\n')
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table-fields", "login,written,received,sent", "--lang=fr"], env)
        self.assertNotIn("Traceback", err, err)
        propre, tableau, cellules = self.lignes_tableau(out)
        ana = [c.strip() for c in next(c for c in cellules if "ana@" in "".join(c))]
        bob = [c.strip() for c in next(c for c in cellules if "bob@" in "".join(c))]
        self.assertEqual(ana[1], "3")                          # inscription, compte, write — pas la lecture, le websocket ni le refus 403
        self.assertEqual(ana[2], "7.0")                        # 900 + 1500 + 3 000 000 + 0 + 200 + 4 000 000 + 100 octets (+ quelques octets avant) ≈ 7.0 Mo
        self.assertEqual(ana[3], "2.5")                        # rl= : 2 500 000 + … ≈ 2.5 Mo
        self.assertEqual(bob[3], "?")                          # ses lignes n'ont pas de champ rl=
        self.assertNotIn("AUCUNE ligne des journaux nginx lus", propre)                 # des lignes ont rl= : pas d'alerte
        self.assertIn("Mo envoyés : taille de ses requêtes", propre)
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--sort", "written"], env)
        ordre = [m.group(0) for m in re.finditer(r"(ana|bob|zoe)@exemple", re.sub(r"\x1b\[[0-9;]*m", "", out))]
        self.assertEqual(ordre[0], "ana@exemple", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--lang=en", "--sort", "sent"], env)
        self.assertNotIn("Traceback", err, err)
        self.assertIn("MB received", out)

    def _profils_odoo(self):
        """PostgreSQL simulé (2.67) : comptes (UID, nom, type) et profils — courriel, téléphone, pays, ville, groupes (module), étiquettes, événements, sondages."""
        profils = ("ana@exemple.org\\037ana@exemple.org\\037+1 514 555-0101\\037CA\\037Canada\\037Montréal\\037RLQ23-Bénévole\\002rlq_survey_report\\003Internal User\\002base"
                   "\\037Bénévole\\003Membre\\0373\\0372\\n"
                   "bob@exemple.org\\037bob@exemple.org\\037\\037FR\\037France\\037Lyon\\037RLQ23-Visiteur\\002\\003Internal User\\002base\\037\\0371\\0370\\n"
                   "zoe@exemple.org\\037zoe@exemple.org\\037\\037CA\\037Canada\\037Québec\\037Portal\\002base\\037Membre\\0370\\0371\\n")
        self.mock("runuser", 'case "$*" in *to_regclass*) printf "t\\037t\\037t\\n";; *information_schema*) printf "1\\n";; '
                             f'*res_groups_users_rel*) printf "{profils}";; '
                             '*) printf "7\\037ana@exemple.org\\037Ana Tremblay\\037f\\n12\\037zoe@exemple.org\\037Zoé\\037t\\n5\\037bob@exemple.org\\037Bob Martin\\037f\\n";; esac')

    def test_list_users_table_evenements_sondages_telephone_pays_ville_groupes_etiquettes(self):
        """2.67 : champs lus dans PostgreSQL (lecture seule) : événements (inscriptions non annulées), sondages complétés, téléphone, pays, ville, groupes
        (créés dans Odoo ou par un module rlq_* : pas les groupes techniques), étiquettes ; listes sans espace."""
        env = self._journal_tableau()
        self._profils_odoo()
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table-fields", "login,events,surveys,phone,country,city,groups,tags", "--lang=fr"], env)
        self.assertNotIn("Traceback", err, err)
        propre, tableau, cellules = self.lignes_tableau(out)
        ana = [c.strip() for c in next(c for c in cellules if "ana@" in "".join(c))]
        self.assertEqual(ana[1:], ["3", "2", "+1 514 555-0101", "CA", "Montréal", "RLQ23-Bénévole", "Bénévole,Membre"])
        bob = [c.strip() for c in next(c for c in cellules if "bob@" in "".join(c))]
        self.assertEqual(bob[1:], ["1", "0", "-", "FR", "Lyon", "RLQ23-Visiteur", "-"])      # groupe sans module (créé dans Odoo) : affiché ; « Internal User » : non
        zoe = [c.strip() for c in next(c for c in cellules if "zoe@" in "".join(c))]
        self.assertEqual(zoe[6], "-")                                                          # « Portal » : groupe technique
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--sort", "events"], env)
        ordre = [m.group(0) for m in re.finditer(r"(ana|bob|zoe)@exemple", re.sub(r"\x1b\[[0-9;]*m", "", out))]
        self.assertEqual(ordre[:3], ["ana@exemple", "bob@exemple", "zoe@exemple"], out)

    def test_list_users_group_csv_repeat_header_et_stats(self):
        """2.67 : --group (membres d'un groupe, nom partiel, accents ignorés), --csv (toutes les valeurs, « ; », BOM, virgule décimale), --repeat-header, --stats."""
        env = self._journal_tableau()
        self._profils_odoo()
        rc, out, err = self.run_cmd(["python3", self.prog, "--group", "benevole", "--lang=fr"], env)            # implique --list-users --table
        self.assertEqual(rc, 0, out + err)
        propre, tableau, cellules = self.lignes_tableau(out)
        self.assertIn("Groupe RLQ23-Bénévole — 1 membre(s) avec une connexion dans l'historique", propre)
        self.assertEqual([c for c in cellules if "@" in "".join(c)][0][5].strip(), "ana@exemple.org")
        self.assertEqual(len([c for c in cellules if "@" in "".join(c)]), 1)
        rc, out, err = self.run_cmd(["python3", self.prog, "--group", "zzz-inconnu"], env)
        self.assertEqual(rc, 1)
        self.assertIn("Aucun groupe Odoo nommé « zzz-inconnu »", out)
        self.assertIn("RLQ23-Bénévole", out)                                                  # les groupes RLQ connus sont proposés
        chemin = os.path.join(self.d, "comptes.csv")
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--csv", chemin, "--lang=fr"], env)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("CSV écrit : " + chemin, out)
        self.assertNotIn("|---", out)                                                          # --csv seul : pas de tableau
        brut = open(chemin, "rb").read()
        self.assertTrue(brut.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", brut)                                                            # fins de ligne Windows                                       # BOM : Excel lit l'UTF-8
        import csv
        import io as io_
        lignes = list(csv.reader(io_.StringIO(brut.decode("utf-8-sig"), newline=""), delimiter=";"))
        titres = lignes[0]
        self.assertIn("Adresses IP (connexions)", titres)
        self.assertIn("Nom du pays", titres)
        ana = dict(zip(titres, next(l for l in lignes if "ana@exemple.org" in l)))
        self.assertEqual(ana["Groupes"], "RLQ23-Bénévole")
        self.assertEqual(ana["Étiquettes"], "Bénévole, Membre")
        self.assertEqual(ana["Adresses IP (connexions)"], "203.0.113.5 (2)")
        self.assertEqual(ana["Mo reçus"], "0,000")                                             # virgule décimale en français
        self.assertEqual(ana["Ville"], "Montréal")
        bob = dict(zip(titres, next(l for l in lignes if "bob@exemple.org" in l)))
        self.assertEqual(bob["Nom"], "Bob Martin")                                              # jamais coupé
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table-fields", "login,logins", "--repeat-header", "--stats", "--lang=fr"], env)
        propre, tableau, cellules = self.lignes_tableau(out)
        self.assertEqual(sum(1 for c in cellules if c[0].strip() == "Identifiant"), 2)            # titres en haut ET en bas
        self.assertIn("──── Statistiques des 3 compte(s) de la liste ────", propre)
        for titre in ("Membres par groupe", "Membres par étiquette", "Interne / portail", "Pays (contact Odoo)", "Domaines de courriel", "Navigateurs",
                      "Les 10 comptes les plus actifs"):
            self.assertIn(titre, propre)
        self.assertRegex(propre, r"RLQ23-Bénévole\s+1 compte\(s\) \(33 %\)")
        self.assertRegex(propre, r"CA\s+2 compte\(s\) \(67 %\)")
        self.assertRegex(propre, r"exemple\.org\s+3 compte\(s\) \(100 %\)")
        self.assertRegex(propre, r"nombre de connexions\s+Ana Tremblay 2")

    def test_list_users_couleurs_aujourd_hui_et_comptes_les_plus_actifs(self):
        """2.67 : dans un terminal, dernière connexion d'aujourd'hui en vert, compte créé aujourd'hui en cyan, valeurs les plus élevées en jaune ; sans terminal : aucun code."""
        import datetime
        env = self._journal_tableau()
        aujourdhui = datetime.date.today().isoformat()
        with open(os.path.join(self.d, "journal.txt"), "a") as f:
            f.write(f"{aujourdhui}T09:00:00-0400 odoo18 odoo[1]: x INFO base odoo.addons.base.models.res_users: Login successful for db:base login:neo@exemple.org from 203.0.113.99\n")
        texte, _ = self.run_pty(["python3", self.prog, "--list-users", "--table-fields", "login,first,last,logins"], [], dict(self.env, **env), timeout=60, keep_ansi=True)
        self.assertIn(f"\x1b[1;32m{aujourdhui} 09:00", texte)                                 # dernière connexion : aujourd'hui
        self.assertIn(f"\x1b[1;36m{aujourdhui} 09:00", texte)                                 # première connexion aujourd'hui : compte nouveau
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table"], env)
        self.assertNotIn("\x1b[", out)

    def test_list_users_ip_vue_titre_trie_en_couleur_et_cles_de_configuration(self):
        """2.69 : colonne « IP vue » (adresse du compte avec la requête la plus récente dans nginx, même sans nouvelle connexion ; CSV : toutes, avec l'heure),
        --sort seen ; titre de la colonne triée en couleur ; TABLE_FIELDS / STATS / GROUP / CSV du fichier de configuration : réglages de --list-users,
        jamais une raison de lister (le timer, sans option, continue de surveiller)."""
        env = self._journal_tableau()
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table-fields", "login,ipseen", "--sort", "seen"], env)
        propre, tableau, cellules = self.lignes_tableau(out)
        lignes = [[c.strip() for c in l] for l in cellules if "@" in "".join(l)]
        self.assertEqual(lignes[0], ["bob@exemple.org", "192.0.2.77 09-22 08:40"])            # vu le plus récemment (requête de 08:40, connexion à 08:00)
        self.assertEqual(lignes[1], ["ana@exemple.org", "203.0.113.5 09-20 18:00"])
        self.assertEqual(lignes[2], ["zoe@exemple.org", "-"])                                  # aucune requête de son adresse
        chemin = os.path.join(self.d, "vus.csv")
        self.run_cmd(["python3", self.prog, "--list-users", "--csv", chemin, "--lang=fr"], env)
        with open(chemin, encoding="utf-8-sig") as f:
            texte = f.read()
        self.assertIn("Adresses IP vues (dernière requête)", texte)
        self.assertIn("203.0.113.5 (2026-09-20 18:00)", texte)
        texte, _ = self.run_pty(["python3", self.prog, "--list-users", "--table-fields", "login,last,logins", "--sort", "last"], [], dict(self.env, **env),
                                timeout=60, keep_ansi=True)
        self.assertIn("\x1b[1;36mDernière", texte)                                              # colonne triée : titre en cyan
        self.assertIn("\x1b[1mIdentifiant", texte)                                              # les autres : gras
        etc = self.env["NGINX_TOOLS_ETC_DEFAULT"]
        os.makedirs(etc, exist_ok=True)
        with open(os.path.join(etc, "web-monitor.conf"), "w") as f:
            f.write("TABLE_FIELDS=login,logins\nSTATS=oui\nGROUP=zzz\nCSV=" + os.path.join(self.d, "jamais.csv") + "\n")
        rc, out, err = self.run_cmd(["python3", self.prog, "--status"], dict(env, WEB_MONITOR_LANG=""))
        self.assertIn("TIMER", out)
        self.assertNotIn("|----", out)                                                          # les clés ne lancent pas --list-users
        self.assertFalse(os.path.exists(os.path.join(self.d, "jamais.csv")))
        with open(os.path.join(etc, "web-monitor.conf"), "w") as f:
            f.write("TABLE_FIELDS=login,logins\nTABLE=oui\n")
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users"], env)
        propre, tableau, cellules = self.lignes_tableau(out)
        self.assertEqual([c.strip() for c in cellules[1]], ["Identifiant", "Conn"])              # TABLE_FIELDS du fichier appliqué

    def test_list_users_minutes_avec_fuseau_a_deux_points(self):
        """2.46 : journalctl -o short-iso récent écrit le fuseau « -04:00 » (ou « Z ») : les minutes de connexion ne tombent plus à 0."""
        for fuseau in ("-04:00", "Z"):
            env = self._journal_tableau(fuseau)
            rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table"], env)
            self.assertNotIn("Traceback", err, err)
            propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
            ana = next(l for l in propre.splitlines() if "ana@exemple.org" in l)
            entete = [c.strip() for c in next(l for l in propre.splitlines() if l.startswith("|") and not set(l) <= set("|-")).strip("|").split("|")]
            minutes = [c.strip() for c in ana.strip("|").split("|")][next(i for i, c in enumerate(entete) if c.startswith("Min"))]      # run-all 1.188 : par l'en-tête, coupé à la largeur des données (2.70 : colonne « Compte créé » ajoutée avant)
            self.assertGreaterEqual(int(minutes), 1, (fuseau, ana))
            if fuseau == "-04:00":
                self.assertEqual(minutes, "8", ana)

    def test_langue_anglaise_aide_tableau_et_statut(self):
        """2.47 : --lang=en (ou WEB_MONITOR_LANG, LC_ALL, LANG) : aide, tableau, statut et erreurs en anglais ; --lang=fr en français ; l'option l'emporte sur l'environnement."""
        env = self._journal_tableau()
        accents = re.compile(r"[àâçéèêëîïôûùü]")
        rc, out, err = self.run_cmd(["python3", self.prog, "--help", "--lang=en"], env)
        self.assertEqual(rc, 0, err)
        self.assertIn("Automatic nginx + Odoo monitoring", out)
        self.assertIn("options:", out)
        self.assertIn("--sort KEY", out)
        self.assertFalse(accents.search(out.replace("—", "").replace("…", "")), [l for l in out.splitlines() if accents.search(l)])
        rc, out, err = self.run_cmd(["python3", self.prog, "--help", "--lang=fr"], env)
        self.assertIn("Surveillance automatique nginx + Odoo", out)
        self.assertIn("options :", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table", "--lang=en", "--sort=minutes"], env)
        propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
        self.assertIn("Connections to Odoo — systemd journal of erplibre.service", propre)
        self.assertIn("3 account(s), sorted by login minutes", propre)
        self.assertRegex(propre, r"\|#\s*\|UID\s*\|IP\s*\|")                                  # 2.67 : tableau compact
        for mot in ("Name", "Login", "First", "Last", "Logi", "Minu", "Type"):
            self.assertIn(mot, propre)
        self.assertIn("|portal", propre)
        self.assertIn("Total: 3 account(s), 4 login(s), 10 login minute(s)", propre)
        rc, out, err = self.run_cmd(["python3", self.prog, "--status", "--lang=en"], env)
        self.assertIn("TIMER (automatic monitoring)", out)
        self.assertIn("NOT INSTALLED: monitoring does not run automatically", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--sort=zzz", "--lang=en"], env)
        self.assertEqual(rc, 2)
        self.assertIn("web-monitor.py: error: argument --sort: unknown sort key « zzz »", err)
        self.assertEqual(self.run_cmd(["python3", self.prog, "--lang=de"], env)[0], 2)
        # Environnement : LC_ALL=en_US -> anglais ; l'option --lang=fr l'emporte ; WEB_MONITOR_LANG=fr (test) l'emporte sur LC_ALL
        env_en = dict(env, LC_ALL="en_US.UTF-8")
        env_en["WEB_MONITOR_LANG"] = ""                       # variable du programme vide : ignorée
        self.assertIn("TIMER (automatic monitoring)", self.run_cmd(["python3", self.prog, "--status"], env_en)[1])
        self.assertIn("TIMER (surveillance automatique)", self.run_cmd(["python3", self.prog, "--status", "--lang=fr"], env_en)[1])
        self.assertIn("TIMER (surveillance automatique)", self.run_cmd(["python3", self.prog, "--status"], dict(env_en, LC_ALL="fr_CA.UTF-8"))[1])
        self.assertIn("TIMER (surveillance automatique)", self.run_cmd(["python3", self.prog, "--status"], dict(env, LC_ALL="en_US.UTF-8"))[1])

    def test_fichier_de_configuration_langue_et_options(self):
        """2.48 : /etc/default/web-monitor.conf puis le fichier personnel (le dernier l'emporte) : LANGUAGE et les options (TABLE, SORT, DAYS…) deviennent les valeurs
        par défaut ; la ligne de commande est prioritaire ; les fichiers lus et les options sont affichés au départ ; valeur invalide : signalée et ignorée."""
        env = self._journal_tableau()
        etc = self.env["NGINX_TOOLS_ETC_DEFAULT"]
        os.makedirs(etc, exist_ok=True)
        perso_dir = self.env["HOME"]
        os.makedirs(perso_dir, exist_ok=True)
        open(os.path.join(etc, "web-monitor.conf"), "w").write("# commentaire\nLANGUAGE=en\nTABLE=yes\nSORT=minutes\nDAYS=abc\n")
        env = dict(env, WEB_MONITOR_LANG="")                                         # la variable du programme (fixée par les tests) laisserait la main au fichier
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users"], env)
        propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
        self.assertIn(f"Configuration read: {os.path.join(etc, 'web-monitor.conf')}", propre)            # un seul fichier : pas de « le dernier l'emporte »
        self.assertIn("Options: --lang en · --sort minutes · --table yes (command line takes precedence)", sans_origine(propre))
        self.assertRegex(propre, r"\|#\s*\|UID\s*\|IP\s*\|")                                  # TABLE=yes : tableau (compact, 2.67), SORT=minutes
        self.assertIn("sorted by login minutes", propre)
        self.assertIn("configuration value ignored: DAYS=abc", err)
        # Fichier personnel : lu ensuite, le dernier l'emporte
        open(os.path.join(perso_dir, ".web-monitor.conf"), "w").write('LANGUAGE="fr"\nSORT=name\n')
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users"], env)
        self.assertRegex(sans_date(out), r"Configuration lue : .*web-monitor\.conf, puis .*\.web-monitor\.conf \(le dernier l'emporte\)")
        self.assertIn("Options : --lang fr · --sort name · --table oui (ligne de commande prioritaire)", sans_origine(out))
        self.assertIn("valeur de configuration ignorée : DAYS=abc", err)
        self.assertIn("par ordre alphabétique", out)
        # La ligne de commande l'emporte ; -c : ce fichier seul
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--lang=en", "--sort=last"], env)
        self.assertIn("sorted by last login", out)
        explicite = os.path.join(self.d, "autre.conf")
        open(explicite, "w").write("LANGUAGE=en\nREVERSE=oui\n")
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "-c", explicite], env)
        self.assertIn(f"Configuration read: {explicite} (requested by -c/--config: no other file is read)", sans_date(out))
        self.assertIn("reverse yes", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--status", "-c", os.path.join(self.d, "absent.conf")], env)
        self.assertEqual(rc, 2)
        # Aucun fichier : la ligne le dit
        os.remove(os.path.join(etc, "web-monitor.conf"))
        os.remove(os.path.join(perso_dir, ".web-monitor.conf"))
        rc, out, err = self.run_cmd(["python3", self.prog, "--status"], dict(env, WEB_MONITOR_LANG="fr"))
        self.assertIn("Configuration : aucun fichier (cherchés : ", out)

    def test_list_users_sort_cles_anglaises_et_synonymes_francais(self):
        """2.47 : --sort accepte les clés anglaises (name, login, first, last, logins, minutes, type, uid, ip) et, comme synonymes, les clés françaises."""
        env = self._journal_tableau()

        def ordre(*options):
            rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table"] + list(options), env)
            self.assertEqual(rc, 0, err)
            return [c.split("@")[0] for c in re.findall(r"\b(\w+@exemple\.org)", re.sub(r"\x1b\[[0-9;]*m", "", out))]
        self.assertEqual(ordre("--sort=last"), ordre("--sort=derniere"))
        self.assertEqual(ordre("--sort=first"), ordre("--sort=premiere"))
        self.assertEqual(ordre("--sort=login"), ordre("--sort=identifiant"))
        self.assertEqual(ordre("--sort=logins"), ordre("--sort=connexions"))
        self.assertEqual(ordre("--sort=name"), ordre("--sort=nom"))
        self.assertEqual(ordre("--sort=last"), ["zoe", "bob", "ana"])

    def test_list_users_sort_cles_synonymes_et_reverse(self):
        """2.45 : --sort nom|identifiant|uid|ip|premiere|derniere|connexions|minutes|type (synonymes : name, latest, first…), --reverse inverse ; clé inconnue : erreur claire."""
        env = self._journal_tableau()

        def ordre(*options):
            rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--table"] + list(options), env)
            self.assertNotIn("Traceback", err, err)
            propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
            return [c.split("@")[0] for c in re.findall(r"\b(\w+@exemple\.org)", propre)]
        self.assertEqual(ordre(), ["ana", "bob", "zoe"])                                  # défaut : nom (Ana, Bob, Zoé)
        self.assertEqual(ordre("--sort=name", "--reverse"), ["zoe", "bob", "ana"])
        self.assertEqual(ordre("--sort=latest"), ["zoe", "bob", "ana"])                    # dernière connexion : la plus récente d'abord
        self.assertEqual(ordre("--sort=derniere", "--reverse"), ["ana", "bob", "zoe"])
        self.assertEqual(ordre("--sort=first"), ["ana", "bob", "zoe"])                     # première connexion : la plus ancienne d'abord
        self.assertEqual(ordre("--sort", "UID"), ["bob", "ana", "zoe"])                    # 5, 7, 12
        self.assertEqual(ordre("--sort=minutes"), ["ana", "bob", "zoe"])                   # 8, 1, 1 (égalité : ordre alphabétique conservé)
        self.assertEqual(ordre("--sort=connexions"), ["ana", "bob", "zoe"])
        self.assertEqual(ordre("--sort=ip"), ["bob", "zoe", "ana"])                        # 192.0.2.77, 198.51.100.9, 203.0.113.5
        self.assertEqual(ordre("--sort=type"), ["ana", "bob", "zoe"])                      # interne, interne, portail
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--sort=couleur"], env)
        self.assertNotEqual(rc, 0)
        self.assertIn("clé de tri inconnue « couleur »", err)
        # Sans --table : liste par compte, même tri, entête qui le dit
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--sort=latest"], env)
        self.assertIn("3 compte(s), triés par dernière connexion", out)
        self.assertLess(out.index("zoe@exemple.org"), out.index("bob@exemple.org"))

    def test_list_users_details_affiche_l_uid_odoo(self):
        """2.39 : --list-users --details affiche l'UID Odoo de chaque compte (lu en lecture seule dans PostgreSQL) ; sans
        --details, aucune requête à la base ; base illisible ou compte disparu : dit pourquoi."""
        journal = "\n".join(f"2026-09-2{i}T10:00:00-0400 odoo18 odoo[1]: x INFO base odoo.addons.base.models.res_users: "
                            f"Login successful for db:{b} login:{l} from {ip}" for i, b, l, ip in [
                                (6, "base", "etienne@exemple.org", "11.97.88.180"), (7, "base", "etienne@exemple.org", "11.97.88.180"),
                                (5, "base", "disparu@exemple.org", "203.0.113.9"), (4, "autre", "etienne@exemple.org", "11.148.77.5")])
        self.write("journal.txt", journal + "\n")
        self.mock("journalctl", f"cat {self.d}/journal.txt")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; case "$*" in *"-d base "*) '
                             'printf "506\\037etienne@exemple.org\\037Étienne Dupont\\037f\\n7\\037x@exemple.org\\037X\\037t\\n";; *) exit 2;; esac')
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--details"])
        self.assertNotIn("Traceback", err, err)
        out = re.sub(r"\x1b\[[0-9;]*m", "", out)
        self.assertIn("UID Odoo        : 506 — Étienne Dupont (interne), base base", out)
        self.assertIn("UID Odoo        : illisible (base autre : PostgreSQL inaccessible, ou root requis)", out)
        self.assertIn("UID Odoo        : introuvable (base base : compte supprimé ou renommé depuis)", out)
        with open(os.path.join(self.d, "runuser.log")) as f:
            appels = f.read()
        self.assertIn("-u postgres -- psql -d base -tA", appels)
        self.assertEqual(appels.count("-d base "), 1, "une seule requête par base")
        self.assertIn("SELECT", appels.upper())
        self.assertNotRegex(appels.upper(), r"\b(INSERT|UPDATE|DELETE|DROP|ALTER)\b")      # lecture seule
        # Sans --details : ni UID ni requête à la base
        os.remove(os.path.join(self.d, "runuser.log"))
        rc, out, err = self.run_cmd(["python3", self.prog, "--list-users"])
        self.assertNotIn("UID Odoo", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "runuser.log")))

    def test_list_users_odoo_et_bbb(self):
        """2.15 : --list-users — toutes les connexions, par ordre alphabétique (sans égard à la casse), IP bannie signalée."""
        import io, contextlib, datetime
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        journal = "\n".join(f"{q}T10:00:00-0400 odoo18 odoo[1]: x INFO base odoo.addons.base.models.res_users: Login successful "
                            f"for db:base login:{l} from {ip}" for q, l, ip in [
                                ("2026-09-20", "zoe@exemple.org", "203.0.113.9"), ("2026-09-28", "Etienne@exemple.org", "11.97.88.180"),
                                ("2026-09-25", "etienne@exemple.org", "11.148.77.5"), ("2026-09-26", "zoe@exemple.org", "203.0.113.9")])
        wm.run = lambda cmd, timeout=0: (0, journal)
        wm.detect_odoo_service = lambda: ("erplibre.service", "")
        wm.first_journal_date = lambda svc, ns: "2026-07-23"
        wm.CHK_STATE = os.path.dirname(self.write("chk/bans.tsv", "2026-09-27 10:00\tbanni\t203.0.113.9\n"))
        def sortie(profil):
            wm.PROFILE = profil
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                self.assertEqual(wm.list_users(), 0)
            return re.sub(r"\x1b\[[0-9;]*m", "", f.getvalue())
        out = sortie({"APP_NAME": "odoo", "APP_LABEL": "Odoo", "APP_LOG_KIND": "journal"})
        noms = [l.strip() for l in out.splitlines() if l.startswith("  ") and not l.startswith("   ") and "@" in l]
        self.assertEqual(noms, ["Etienne@exemple.org", "etienne@exemple.org", "zoe@exemple.org"])   # sans égard à la casse ; à égalité, majuscule d'abord
        self.assertRegex(out, r"\n\n  zoe@exemple\.org\n    Connexions      : 2 \(première 2026-09-20 10:00, dernière 2026-09-26 10:00\)"
                              r"\n    Adresses IP     : 203\.0\.113\.9 \(bannie\)")
        self.assertIn("3 compte(s), par ordre alphabétique", out)
        self.assertIn("depuis le 2026-07-23", out)
        # --days : journal borné (--since), source indiquée
        commandes = []
        wm.run = lambda cmd, timeout=0: (commandes.append(cmd), (0, journal))[1]
        wm.DAYS, wm.DAYS_GIVEN = 10, True
        self.addCleanup(setattr, wm, "JOURS_DONNE", False)
        out = sortie({"APP_NAME": "odoo", "APP_LABEL": "Odoo", "APP_LOG_KIND": "journal"})
        self.assertIn("--since", commandes[-1])
        self.assertIn("10 derniers jours", out)
        wm.DAYS_GIVEN = False
        # 2.16 : détails de trafic des adresses du compte (tous les journaux nginx conservés)
        self.write("nginx/rencontres_linux_quebec_prod-access.log",
                   '11.97.88.180 - - [28/Sep/2026:12:02:11 -0400] "POST /web/dataset/call_kw/survey.survey/web_read HTTP/1.1" 200 300 "-" "Mozilla/5.0"\n'
                   '11.97.88.180 - - [28/Sep/2026:12:02:12 -0400] "GET /odoo/action-908 HTTP/1.1" 200 3000 "-" "Mozilla/5.0"\n')
        wm.NGINX_DIR = os.path.dirname(self.path("nginx", "x"))
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "APP_LOG_KIND": "journal", "ACCESS_LOGS": "*-access.log"}
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.list_users()                                              # défaut : sans détails (2.20)
        self.assertNotIn("Trafic          :", f.getvalue())
        self.assertIn("web-monitor.py --list-users --details", f.getvalue())
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.list_users(details=True)
        bloc = f.getvalue().split("Etienne@exemple.org", 1)[1].split("etienne@exemple.org", 1)[0]
        self.assertIn("Trafic          : 1 pages vues · 2 requêtes · 0 erreur", bloc)
        self.assertIn("Jours + actifs  : 2026-09-28 (2 req.)", bloc)                              # --details : les 5 jours les plus actifs
        self.assertIn("Modules Odoo    : survey (1)", bloc)
        # BigBlueButton : liens de participation dans les journaux nginx
        d = datetime.date.today().strftime("%d/%b/%Y")
        self.write("nginx/bigbluebutton.access.log", f'198.51.100.4 - - [{d}:19:00:00 -0400] "GET /bigbluebutton/api/join?fullName=Ren%C3%A9e+T&meetingID=x HTTP/1.1" 302 0 "-" "Mozilla/5.0"\n')
        wm.NGINX_DIR = os.path.dirname(self.path("nginx", "x"))
        out = sortie({"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton", "ACCESS_LOGS": "bigbluebutton.access.log"})
        self.assertIn("1 participant(s), par ordre alphabétique", out)
        self.assertRegex(out, r"\n\n  Renée T\n    Connexions      : 1 \(première " + datetime.date.today().isoformat())

    def test_statistiques_par_compte_et_part_des_connectes(self):
        """2.16 : pages vues, erreurs, modules Odoo, jour le plus actif par compte ; part du trafic des utilisateurs connectés."""
        import datetime
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        st, j1, j2 = {}, datetime.date(2026, 9, 27), datetime.date(2026, 9, 28)
        acc = lambda ip, m, u, c, d, idx=(1, 2): wm.accumulate_ip(st, ip, m, u, c, d, list(idx))
        acc("11.97.88.180", "GET", "/odoo/discuss", "200", j1)
        for _ in range(3):
            acc("11.97.88.180", "POST", "/web/dataset/call_kw/mail.message/message_format", "200", j2)
        acc("11.97.88.180", "POST", "/web/dataset/call_kw/res.partner/web_read", "200", j2)
        acc("11.97.88.180", "POST", "/web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config", "429", j2)
        acc("11.148.77.5", "GET", "/event", "200", j2)
        acc("203.0.113.9", "GET", "/event", "200", j2)                     # visiteur anonyme
        a = wm.aggregate_ips(st, {"11.97.88.180": 5, "11.148.77.5": 1})
        self.assertEqual((a["req"], a["pages"]), (7, 2))
        texte = wm.TR("\n".join(wm.detail_lines(a))).replace("\u202f", " ")
        self.assertIn("Trafic          : 2 pages vues · 7 requêtes · 1 erreur(s) (429 : 1)", texte)
        self.assertIn("Jour le + actif : 2026-09-28 (6 requêtes)", texte)
        self.assertIn("Modules Odoo    : mail (3), base (2)", texte)              # res.* et ir.* → base
        self.assertIn("Pages + vues    : /event (1), /odoo/discuss (1)", texte)
        class C:
            n = {}
        c = C()
        wm.WHITELIST.clear()
        wm.WHITELIST.add("11.148.77.5")                                     # équipe
        wm.logged_in_shares(c, {"stats_ip": st, "ips_connues": {"11.97.88.180", "11.148.77.5"}})
        self.assertEqual((c.n[("req_connectes", 2)], c.n[("pages_connectes", 2)]), (7, 2))  # l'anonyme n'y est pas
        self.assertEqual(c.n[("req_connus_hors_equipe", 2)], 6)            # 2.23 : l'équipe retirée

    def test_recommandation_requetes_malveillantes(self):
        """2.15 : « requêtes malveillantes » (ancien vocabulaire retiré) ; marche à suivre selon qu'il y en a encore aujourd'hui."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "CATCHALL_LOG": "x"}
        wm.run = lambda cmd, timeout=0: (0, "")
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        class C:
            def __init__(self, auj): self.auj = auj
            def get(self, k, i): return {("transmises", 1): 79483, ("transmises_suspectes", 1): 895, ("transmises_suspectes", 0): self.auj}.get((k, i), 0)
        faits = {"non_filtrees": {"/.env": 193, "/.git/config": 110}, "non_filtrees_derniere": "2026-09-24", "jails": {"nginx-sqli": 1}, "robots": {},
                 "non_filtrees_hotes": {"odoo18.exemple.org": 5}}
        for auj, attendu in ((0, "aucune aujourd'hui (dernière le 2026-09-24)"), (12, "12 encore aujourd'hui")):
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(auj), faits, {})
            out = f.getvalue()
            self.assertIn("895 requêtes malveillantes (/.env, /.git/config…) ont atteint Odoo".replace("895", "895"), out.replace("\u202f", ""))
            self.assertIn(attendu, out)
            self.assertNotIn("app-health-check.py --target local", out)       # 2.36 : l'essai est fait par le programme
            self.assertNotIn("sondage", out.lower())
            if auj:                                                      # nom demandé (format combined_host de nginx)
                self.assertIn("Noms concernés : odoo18.exemple.org (5) — c'est le bloc server de ce nom qu'il faut corriger.", out)

    # ---------------------------------------------------------------------------------------------------------------
    # 2.36 : les recommandations ne renvoient plus à des commandes à taper — le programme les fait lui-même.
    # ---------------------------------------------------------------------------------------------------------------
    def module_wm(self, profil, nginx_t="", investigate=""):
        """Module web-monitor chargé pour un test de recommandations : commandes système simulées."""
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = profil
        def faux_run(cmd, timeout=0, env_extra=None):
            if cmd[:2] == ["nginx", "-T"]:
                return 0, nginx_t
            if "--investigate" in cmd:
                return 0, investigate
            return 0, ""
        wm.run = faux_run
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        wm.nginx_loaded_since = lambda: None
        return wm

    def recos_de(self, wm, c, faits):
        import io, contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.recommendations(c, faits, {})
        return f.getvalue()

    def reco(self, out, cle):
        """Bloc (constat, Pourquoi, Comment) de la recommandation qui contient cle."""
        lignes = out.splitlines()
        i = next(i for i, l in enumerate(lignes) if cle in l)
        return "\n".join(lignes[i:i + 3])

    def test_fuites_bbb_diagnostiquees_par_le_programme(self):
        """2.36 : « vérifier que la configuration de BBB inclut… (nginx -T | grep), puis nginx-hardening.sh --check » était à
        faire à la main. Le programme vérifie lui-même : rechargement, inclusion, heure des requêtes, essai réel."""
        dossier = os.path.dirname(self.path("bbb-nginx", "x"))
        regles = os.path.join(dossier, "zz-nginx-hardening-security.nginx")
        with open(regles, "w") as fh:
            fh.write("# règles\n")
        installe = time.time() - 3600
        os.utime(regles, (installe, installe))
        os.environ["NGINX_HARDENING_BBB_NGINX_DIR"] = dossier
        self.addCleanup(os.environ.pop, "NGINX_HARDENING_BBB_NGINX_DIR", None)
        class C:
            v = {"transmises": 15000, "transmises_suspectes": 306, "fichiers_sensibles": 10}
            def get(self, k, i): return 17 if (k == "transmises_suspectes" and i == 0) else self.v.get(k, 0)
        avant = [(installe - 600, "/.env", "bbb30.exemple.org")] * 17
        faits = {"non_filtrees": {"/.env": 200, "/.git/config": 106}, "jails": {"nginx-blocked-probes": 1}, "robots": {},
                 "non_filtrees_jour": avant}
        bbb = {"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}
        avec_regles = f"# configuration file /etc/nginx/sites-enabled/bbb:\nserver {{\n# configuration file {regles}:\nlocation ~ /\\. {{\n"
        # a) nginx pas rechargé depuis l'installation : rechargement proposé (correction du programme)
        wm = self.module_wm(bbb, avec_regles)
        wm.nginx_loaded_since = lambda: installe - 7200
        out = self.recos_de(wm, C(), faits)
        self.assertIn("nginx n'a pas été rechargé depuis", out)
        self.assertIn("nginx -t && systemctl reload nginx", [a[1] for a in wm.ACTIONS])
        self.assertIn("a) Recharger nginx pour appliquer les règles de sécurité de BigBlueButton", out)
        self.assertNotIn("nginx -T | grep", out)
        # b) rechargé, mais fichier absent de nginx -T : la configuration de BBB ne l'inclut pas
        wm = self.module_wm(bbb, "# configuration file /etc/nginx/sites-enabled/bbb:\nserver {\n")
        wm.nginx_loaded_since = lambda: installe + 60
        out = self.recos_de(wm, C(), faits)
        self.assertIn("est absent de nginx -T", out)
        self.assertNotIn("nginx -t && systemctl reload nginx", [a[1] for a in wm.ACTIONS])
        # c) toutes antérieures à l'entrée en vigueur, et nginx les refuse maintenant : FAIBLE, rien à faire
        wm = self.module_wm(bbb, avec_regles)
        wm.nginx_loaded_since = lambda: installe + 60
        wm.read_page = lambda chemin, hote=None: (404, b"x" * 150)
        out = self.recos_de(wm, C(), faits)
        bloc = self.reco(out, "requêtes malveillantes")
        self.assertIn("[FAIBLE]", bloc)
        self.assertIn("datent toutes d'avant l'entrée en vigueur des règles", bloc)
        self.assertIn("nginx refuse maintenant /.env → 404 (150 o)", bloc)
        self.assertIn("Rien à faire", bloc)
        # d) postérieures, et une location prioritaire de BBB les capte : le programme le montre (fichier:ligne)
        apres = [(installe + 120, "/html5client/.env", "bbb30.exemple.org")] * 5
        faits_d = dict(faits, non_filtrees_jour=avant + apres)
        texte = avec_regles + "# configuration file /etc/bigbluebutton/nginx/bbb-html5.nginx:\nlocation ^~ /html5client {\n"
        wm = self.module_wm(bbb, texte)
        wm.nginx_loaded_since = lambda: installe + 60
        wm.read_page = lambda chemin, hote=None: (200, b"x" * 9000) if chemin.startswith("/html5client") else (404, b"")
        out = self.recos_de(wm, C(), faits_d)
        bloc = self.reco(out, "requêtes malveillantes")
        self.assertIn("5 depuis l'entrée en vigueur des règles", bloc)
        self.assertIn("nginx laisse encore passer /html5client/.env → 200 (9000 o)", bloc)
        self.assertIn("/etc/bigbluebutton/nginx/bbb-html5.nginx:1 « location ^~ /html5client »", bloc)

    def test_fuites_odoo_regle_manquante_ou_non_appliquee(self):
        """2.40 : /wp-admin/ traversait nginx (303 de 219 octets, puis 404 de 32 Ko d'Odoo) ; le conseil « le bloc server doit
        inclure securite-commune.conf » envoyait chercher au mauvais endroit : le bloc était correct, la RÈGLE manquait. Le
        programme évalue maintenant les « location ~ » de nginx -T sur chaque chemin qui passe."""
        class C:
            def get(self, k, i): return {("transmises", 1): 79483, ("transmises_suspectes", 1): 145, ("transmises_suspectes", 0): 3}.get((k, i), 0)
        faits = {"non_filtrees": {"/wp-admin/": 3}, "non_filtrees_derniere": "2026-10-02", "jails": {"nginx-x": 1}, "robots": {},
                 "non_filtrees_jour": [(time.time(), "/wp-admin/", "www.exemple.org"), (time.time(), "/en_CA/wp-admin/", "www.exemple.org"),
                                       (time.time(), "/en_CA/wp-admin", "www.exemple.org")]}
        odoo = {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "CATCHALL_LOG": "x"}
        reponses = {"/wp-admin/": (303, b"r" * 219), "/en_CA/wp-admin/": (301, b"r" * 217), "/en_CA/wp-admin": (404, b"p" * 32752)}
        regles = ("# configuration file /etc/nginx/snippets/securite-commune.conf:\n"
                  "location ~ /\\. {\n    return 404;\n}\nlocation ~* ^/(_hcms|wp-content|wp-json|server-status) {\n    return 404;\n}\n"
                  'location ~* "^/(?:[a-z]{2}(?:_[A-Z]{2})?/)?(?!web/)zzz" {\n')
        # 1. AUCUNE règle ne vise ces chemins : la règle manque (et ce n'est pas un problème d'inclusion)
        wm = self.module_wm(odoo, regles)
        wm.read_page = lambda chemin, hote=None: reponses[chemin]
        bloc = self.reco(self.recos_de(wm, C(), faits), "requêtes malveillantes")
        self.assertIn("nginx laisse encore passer /wp-admin/ → 303 (219 o), /en_CA/wp-admin/ → 301 (217 o), /en_CA/wp-admin → 404 (32752 o)", bloc)
        self.assertIn("AUCUNE règle de nginx -T ne vise /wp-admin/, /en_CA/wp-admin/, /en_CA/wp-admin", bloc)
        self.assertIn("le bloc server est correct, il MANQUE une règle", bloc)
        self.assertNotIn("doit inclure snippets/securite-commune.conf", bloc)
        # 2. Règle wp-admin SANS préfixe de langue : seul /wp-admin/ est visé ; le programme nomme ceux qui ne le sont toujours pas
        sans_prefixe = regles.replace("wp-content|wp-json", "wp-admin|wp-content|wp-json")
        wm = self.module_wm(odoo, sans_prefixe)
        wm.read_page = lambda chemin, hote=None: reponses[chemin]
        bloc = self.reco(self.recos_de(wm, C(), faits), "requêtes malveillantes")
        self.assertIn("AUCUNE règle de nginx -T ne vise /en_CA/wp-admin/, /en_CA/wp-admin :", bloc)
        self.assertNotIn("vise /wp-admin/", bloc)
        # 3. Règle livrée (préfixe de langue facultatif) : tout est visé, mais nginx répond quand même → bloc server sans cette règle
        livree = regles.replace("(_hcms|wp-content|wp-json|server-status)", "(wp-admin|wp-content)").replace(
            "location ~* ^/(", 'location ~* "^/(?:[a-z]{2}(?:_[A-Z]{2})?/)?(').replace("(wp-admin|wp-content) {", '(wp-admin|wp-content)" {')
        wm = self.module_wm(odoo, livree)
        wm.read_page = lambda chemin, hote=None: reponses[chemin]
        bloc = self.reco(self.recos_de(wm, C(), faits), "requêtes malveillantes")
        self.assertNotIn("AUCUNE règle", bloc)
        self.assertIn("des règles les visent (/etc/nginx/snippets/securite-commune.conf:4 « location ~* ^/(?:[a-z]{2}", bloc)
        self.assertIn("ne les inclut pas, ou une autre location les précède", bloc)
        # 4. nginx -T illisible : cause non déterminée (jamais une cause inventée)
        wm = self.module_wm(odoo, "")
        wm.read_page = lambda chemin, hote=None: reponses[chemin]
        bloc = self.reco(self.recos_de(wm, C(), faits), "requêtes malveillantes")
        self.assertIn("configuration de nginx illisible (nginx -T) : cause non déterminée", bloc)
        self.assertNotIn("MANQUE", bloc)

    def test_fuites_odoo_essai_reel_a_travers_nginx(self):
        """2.36 : « Confirmer avec app-health-check.py --target local » : le programme fait l'essai lui-même."""
        class C:
            def __init__(self, auj): self.auj = auj
            def get(self, k, i): return {("transmises", 1): 79483, ("transmises_suspectes", 1): 895, ("transmises_suspectes", 0): self.auj}.get((k, i), 0)
        faits = {"non_filtrees": {"/.env": 193}, "non_filtrees_derniere": "2026-09-24", "jails": {"nginx-x": 1}, "robots": {}}
        odoo = {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "CATCHALL_LOG": "x"}
        wm = self.module_wm(odoo)
        wm.read_page = lambda chemin, hote=None: (404, b"<html>404</html>")
        bloc = self.reco(self.recos_de(wm, C(0), faits), "requêtes malveillantes")
        self.assertIn("[FAIBLE]", bloc)
        self.assertIn("nginx refuse maintenant /.env → 404", bloc)
        self.assertIn("Rien à faire", bloc)
        wm = self.module_wm(odoo, "# configuration file /etc/nginx/sites-enabled/odoo:\nlocation ^~ /en_CA {\n")
        wm.read_page = lambda chemin, hote=None: (404, b"y" * 30000) if chemin == "/en_CA/.env" else (404, b"")
        bloc = self.reco(self.recos_de(wm, C(3), dict(faits, non_filtrees_jour=[(time.time(), "/en_CA/.env", "www.exemple.org")] * 3)),
                         "requêtes malveillantes")
        self.assertIn("[MOYENNE]", bloc)
        self.assertIn("nginx laisse encore passer /en_CA/.env → 404 (30000 o)", bloc)
        self.assertIn("/etc/nginx/sites-enabled/odoo:1 « location ^~ /en_CA »", bloc)

    def test_403_enquete_et_regles_relevees_par_le_programme(self):
        """2.36 : enquête sur l'adresse dominante faite par le programme (bannissement proposé si recommandé), règles de
        refus relevées dans nginx -T, et part des autres adresses qui ont AUSSI obtenu des pages normales."""
        ips = {"11.76.10.18": 489}
        ips.update({f"198.51.{i // 250}.{i % 250 + 1}": 3 for i in range(246)})
        texte = ("# configuration file /etc/nginx/conf.d/robots.conf:\nmap $http_user_agent $mauvais_robot {\n"
                 "# configuration file /etc/nginx/sites-enabled/bbb:\nserver {\n  if ($mauvais_robot) { return 403; }\n")
        wm = self.module_wm({"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}, texte,
                            "      Signes d'hostilité : 2\n      → Score 5/7 : bannissement recommandé.\n")
        class C:
            def get(self, k, i): return 0
        faits = {"non_filtrees": {}, "jails": {"sshd": 1}, "robots": {"browser (Windows)": 1922},
                 "refus_navigateurs": {"/": 531, "/signin": 44, "/login": 33, "/signup": 30, "/x": 584}, "refus_nav_scanners": 700,
                 "refus_nav_ip": ips, "refus_nav_petits": 1200, "ips_2xx": {f"198.51.0.{i}" for i in range(1, 41)}}
        out = self.recos_de(wm, C(), faits)
        bloc = self.reco(out, "navigateurs ordinaires")
        self.assertIn("Enquête du programme : 11.76.10.18 : Score 5/7 : bannissement recommandé. — bannissement proposé", bloc)
        self.assertIn(("11.76.10.18", "489 refus 403 de navigateur en 30 jours ; enquête : Score 5/7 : bannissement recommandé."),
                      wm.RECOMMENDED)
        self.assertIn("40 ont aussi obtenu des pages normales", bloc)
        self.assertIn("206 n'ont reçu que des refus", bloc)
        self.assertIn("/etc/nginx/conf.d/robots.conf:1 « map $http_user_agent $mauvais_robot {", bloc)
        self.assertIn("/etc/nginx/sites-enabled/bbb:2 « if ($mauvais_robot) { return 403; } »", bloc)
        self.assertNotIn("--investigate", bloc)
        self.assertNotIn("Détail : nginx-log-audit.sh", bloc)
        self.assertIn("▶ bannir 11.76.10.18", out)
        # Adresse déjà bannie : ni enquête ni proposition
        wm = self.module_wm({"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}, texte, "→ Score 5/7 : bannissement recommandé.")
        out = self.recos_de(wm, C(), dict(faits, bannies={"11.76.10.18": "banni"}))
        self.assertIn("11.76.10.18 déjà bannie, rien à faire", out)
        self.assertEqual(wm.RECOMMENDED, [])

    def test_robots_txt_lu_par_le_programme(self):
        """2.36 : « curl -s https://…/robots.txt » remplacé par la lecture faite par le programme."""
        class C:
            def get(self, k, i): return 0
        faits = {"non_filtrees": {}, "jails": {"sshd": 1}, "robots": {"Googlebot": 3598}}
        wm = self.module_wm({"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"})
        wm.read_page = lambda chemin, hote=None: (200, b"User-agent: *\nDisallow: /\n")
        self.assertIn("« Disallow: / » présent — rien à faire", self.recos_de(wm, C(), faits))
        wm.read_page = lambda chemin, hote=None: (200, b"User-agent: *\nDisallow: /admin\n")
        out = self.recos_de(wm, C(), faits)
        self.assertIn("« Disallow: / » ABSENT", out)
        self.assertIn("Disallow: /admin", out)

    def test_corrections_faites_par_le_programme_en_fin_de_sommaire(self):
        """2.36 : --apply --yes fait toutes les corrections sans question ; sans terminal ni --apply : la commande à lancer."""
        import io, contextlib, unittest.mock
        wm = self.module_wm({"APP_NAME": "odoo", "APP_LABEL": "Odoo"})
        faits_par = []
        wm.ACTIONS[:] = [("Recharger nginx", "nginx -t && systemctl reload nginx", lambda: faits_par.append("reload")),
                         ("Installer le timer", "web-monitor.py --install-timer", lambda: faits_par.append("timer"))]
        wm.RECOMMENDED[:] = [("203.0.113.9", "enquête : Score 5/7")]
        wm.ban = lambda liste, choose: faits_par.append(("ban", [i for i, _ in liste], choose))
        with unittest.mock.patch("os.geteuid", return_value=0):
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.offer_fixes()                                     # sans terminal, sans --apply
            self.assertIn("web-monitor.py --apply --yes", f.getvalue())
            self.assertEqual(faits_par, [])
            wm.APPLY, wm.YES = True, True
            with contextlib.redirect_stdout(io.StringIO()):
                wm.offer_fixes()
        self.assertEqual(faits_par, [("ban", ["203.0.113.9"], False), "reload", "timer"])
        with unittest.mock.patch("os.geteuid", return_value=1000), unittest.mock.patch.dict(os.environ, {"NGINX_TOOLS_TEST_EUID": ""}):   # run-all 1.190 : sans root simulé
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.offer_fixes()
        self.assertIn("root requis", f.getvalue())
        rc, out, err = self.run_cmd(["python3", self.prog, "--help"])
        self.assertIn("--apply", out)

    def test_sauvegarde_recommandation_et_alerte(self):
        """2.24 : jamais de sauvegarde → recommandation HAUTE ; sauvegarde qui fonctionnait puis échoue → alerte."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.BACKUP_STATE = os.path.dirname(self.path("etat-sauvegarde", "x"))
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "CATCHALL_LOG": "x"}
        wm.run = lambda cmd, timeout=0: (0, "")
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        class C:
            def get(self, k, i): return 0
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.recommendations(C(), {"non_filtrees": {}, "jails": {"nginx-x": 1}, "robots": {}}, {})
        self.assertRegex(f.getvalue(), r"\[.*HAUTE.*\] aucune sauvegarde automatique d'Odoo")
        self.assertEqual(wm.analyze_backup(1, "[FAIL] base : AUCUNE sauvegarde"), [])          # jamais configurée
        self.write("etat-sauvegarde/last-success", "1\t2026-09-20 02:30\tbase\n")
        alertes = wm.analyze_backup(1, "  [FAIL] base : dernière sauvegarde il y a 50 h (2026-09-27_023000)")
        self.assertEqual(wm.TR(alertes[0][0]), "odoo-backup.sh : sauvegarde d'Odoo trop ancienne ou en échec")
        self.assertIn("il y a 50 h", alertes[0][1][0])

    def test_options_d_odoo_du_processus_en_cours_puis_du_script(self):
        """2.25 : options passées par run.sh → odoo_bin.sh (cas réel de DEV) prioritaires sur le fichier de configuration."""
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        conf = self.write("erplibre/config.conf", "[options]\nworkers = 3\nmax_cron_threads = 2\nlimit_memory_hard = 0\nlimit_time_real = 99999\n")
        run_sh = self.write("erplibre/run.sh", "#!/bin/bash\n# lancement\nexec bash /home/x/erplibre/odoo_bin.sh -c ./config.conf "
                                               "--limit-time-real 1200 --limit-time-cpu 1200 --limit-memory-soft=4631560192 --limit-memory-hard=5449449472\n")
        proc = os.path.dirname(self.path("proc", "x"))
        for pid, ppid, nom, args in (("100", "1", "bash", ["bash", run_sh]),
                                     ("101", "100", "python3", ["python3", "odoo-bin", "-c", conf, "--limit-time-real", "1800",
                                                                "--limit-memory-soft=4631560192", "--limit-memory-hard=6000000000"])):
            self.write(f"proc/{pid}/stat", f"{pid} ({nom}) S {ppid} 0 0\n")
            with open(os.path.join(proc, pid, "cmdline"), "wb") as f:
                f.write(b"\0".join(a.encode() for a in args) + b"\0")
        os.environ["PROC_DIR"] = proc
        self.addCleanup(os.environ.pop, "PROC_DIR", None)
        reponses = {"MainPID": "100", "ExecStart": f"ExecStart={{ path=/bin/bash ; argv[]=/bin/bash {run_sh} ; }}"}
        wm.run = lambda cmd, timeout=0: (0, next((v for k, v in reponses.items() if k in " ".join(cmd)), ""))
        chemin, v, origine = wm.odoo_config("erplibre.service")
        self.assertEqual(chemin, conf)
        self.assertEqual((v["limit_memory_hard"], v["limit_time_real"], v["limit_time_cpu"], v["workers"]), (6000000000, 1800, 1200, 3))
        self.assertEqual((wm.TR(origine["limit_memory_hard"]), wm.TR(origine["limit_time_cpu"]), wm.TR(origine["workers"])),
                         ("processus en cours", "script de démarrage", "fichier"))
        # Processus illisible (Odoo arrêté) : valeurs du script de démarrage, jamais « 0 = illimité » du fichier
        reponses["MainPID"] = "0"
        chemin, v, origine = wm.odoo_config("erplibre.service")
        self.assertEqual((v["limit_memory_hard"], v["limit_time_real"]), (5449449472, 1200))
        self.assertEqual(wm.TR(origine["limit_memory_hard"]), "script de démarrage")

    def test_recommandation_jails_web_selon_fail2ban(self):
        """2.27 : jail chargée sans bannissement encore → pas de recommandation ; fail2ban arrêté → dit ; texte à jour."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        class C:
            def get(self, k, i): return 901 if k == "fichiers_sensibles" else 0
        faits = {"non_filtrees": {}, "jails": {"sshd": 2}, "robots": {}}
        def recos(reponse_f2b):
            wm.run = lambda cmd, timeout=0: reponse_f2b if cmd[:2] == ["fail2ban-client", "status"] else (0, "")
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(), faits, {})
            return f.getvalue()
        out = recos((0, "Status\n|- Number of jail: 2\n`- Jail list: sshd, nginx-blocked-probes"))
        self.assertNotIn("aucune jail fail2ban ne bannit les scanners web", out)       # chargée, même sans bannissement
        out = recos((0, "Status\n`- Jail list: sshd"))
        self.assertIn("aucune jail fail2ban ne bannit les scanners web (901", out)
        self.assertIn("nginx-hardening.sh --update", out)
        self.assertIn("zz-nginx-hardening-security.nginx (fichiers de BBB intacts)", out)
        self.assertNotIn("nginx-odoo-config.zip (fail2ban/", out)
        out = recos((1, "Failed to access socket path: /var/run/fail2ban/fail2ban.sock"))
        self.assertIn("fail2ban ne répond pas (arrêté ?)", out)
        self.assertIn("systemctl enable --now fail2ban", out)

    def recos_403(self, faits_403):
        """Recommandations (BBB) pour des refus 403 de navigateurs ; renvoie le texte de la recommandation 403."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}
        wm.run = lambda cmd, timeout=0: (0, "")
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        class C:
            def get(self, k, i): return 0
        faits = {"non_filtrees": {}, "jails": {"sshd": 1}, "robots": {"browser (Windows)": 1909}}
        faits.update(faits_403)
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.recommendations(C(), faits, {})
        return f.getvalue()

    def test_403_navigateurs_regle_ou_robots(self):
        """2.29 : 403 de navigateurs — pages ordinaires séparées des URL de scanners ; peu d'adresses = robots ;
        beaucoup d'adresses = règle à trouver ; taille de la réponse = nginx ou application."""
        # Cas réel de BBB de PROD : « / » 519, « /signin » 44, « /login » 33, « /.env » 41 — ici concentrés sur 3 adresses
        out = self.recos_403({"refus_navigateurs": {"/": 519, "/signin": 44, "/login": 33}, "refus_nav_scanners": 41,
                              "refus_nav_ip": {"203.0.113.5": 500, "203.0.113.6": 60, "203.0.113.7": 36}, "refus_nav_petits": 590})
        self.assertIn("596 visent des pages ordinaires (/ (519), /signin (44), /login (33))", out)
        self.assertIn("41 visent des URL de scanners (.env, .php…) : refus normal", out)
        self.assertIn("Concentrées sur 3 adresse(s) (les plus actives : 203.0.113.5 (500), 203.0.113.6 (60), 203.0.113.7 (36))", out)
        self.assertIn("probablement des robots", out)
        self.assertIn("Réponses très courtes : typique d'un refus de nginx lui-même", out)
        self.assertNotIn("RÈGLE", out)
        # Mêmes refus répartis sur 300 adresses, réponses longues : une règle refuse de vrais visiteurs
        ips = {f"198.51.{i // 250}.{i % 250 + 1}": 2 for i in range(300)}
        out = self.recos_403({"refus_navigateurs": {"/": 600}, "refus_nav_ip": ips, "refus_nav_petits": 10})
        self.assertIn("Réparties sur 300 adresses différentes : probablement une RÈGLE qui refuse de vrais visiteurs", out)
        self.assertNotIn("nginx -T | grep", out)                                  # 2.36 : relevé par le programme
        self.assertIn("Configuration de nginx illisible (nginx -T)", out)
        self.assertIn("Réponses longues : plutôt l'application que nginx", out)
        self.assertNotIn("probablement des robots", out)
        # Cas réel de BBB de PROD : 233 adresses, dont UNE à 34 % — ni « concentrées » ni « règle » : un robot domine
        ips = {"11.76.10.201": 430, "11.141.105.161": 108, "11.75.218.193": 72}
        ips.update({f"198.51.{i // 250}.{i % 250 + 1}": 3 if i < 191 else 2 for i in range(230)})
        out = self.recos_403({"refus_navigateurs": {"/": 748, "/rooms/dmd-nuj-ic7-gmb/join": 398, "/api/host.describe": 49,
                                                   "/login": 36, "/dashboard": 30}, "refus_nav_ip": ips, "refus_nav_petits": 1200})
        self.assertIn("1261 visent des pages ordinaires", out)
        self.assertIn("Réparties sur 233 adresses, mais une seule (11.76.10.201) en représente 34 % (430)", out)
        self.assertIn("Enquête du programme : 11.76.10.201 : enquête impossible", out)   # 2.36 : faite par le programme
        self.assertNotIn("--investigate", out)
        self.assertIn("Les 232 autres adresses se partagent le reste", out)
        self.assertNotIn("Concentrées sur", out)                               # 233 adresses ne sont pas « concentrées »
        self.assertNotIn("probablement une RÈGLE qui refuse", out)

    def test_googlebot_403_bbb_ou_odoo(self):
        """2.31 : sur BBB, être indexé n'est pas souhaitable (liens de salles) → FAIBLE, refus voulu, robots.txt ; sur Odoo,
        l'avertissement d'origine ; dans les deux cas, les pages demandées par le robot."""
        import io, contextlib
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        def recos(profil):
            wm = __import__("importlib.util").util.module_from_spec(spec)
            spec.loader.exec_module(wm)
            wm.PROFILE = profil
            wm.run = lambda cmd, timeout=0: (0, "")
            wm.load_sanity_module = lambda: None
            wm._certificate_via_health = lambda: (None, "")
            class C:
                def get(self, k, i): return 0
            faits = {"non_filtrees": {}, "jails": {"sshd": 1}, "robots": {"Googlebot": 3598},
                     "refus_robots_chemins": {"Googlebot": {"/rooms/dmd-nuj-ic7-gmb/join": 398, "/": 12}}}
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(), faits, {})
            return f.getvalue(), wm
        out, wm = recos({"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"})
        ligne = next(l for l in out.splitlines() if "essaie d'indexer ce serveur BigBlueButton" in l)
        self.assertIn("[FAIBLE]", ligne)
        self.assertIn("3598 refus 403", ligne)
        self.assertIn("Pages demandées : /rooms/dmd-nuj-ic7-gmb/join (398), / (12).", out)
        self.assertIn("robots.txt non vérifié", out)                              # 2.36 : lu par le programme (ici impossible)
        self.assertNotIn("curl -s", out)
        self.assertNotIn("peut retirer le site de ses résultats", out)                # sans objet sur BBB
        out, wm = recos({"APP_NAME": "odoo", "APP_LABEL": "Odoo"})
        ligne = next(l for l in out.splitlines() if "Googlebot reçoit des refus 403" in l)
        self.assertIn("[MOYENNE]", ligne)
        self.assertIn("peut retirer le site de ses résultats", out)
        self.assertIn("Pages demandées : /rooms/dmd-nuj-ic7-gmb/join (398), / (12).", out)

    def test_ctrl_c_sans_trace_d_appels(self):
        """2.30 : Ctrl-C pendant less ne lève plus KeyboardInterrupt (le signal part aussi à ce programme) ; Ctrl-C
        ailleurs termine proprement (code 130, sans trace d'appels)."""
        import io, contextlib, signal, sys, types
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        # 1) n'importe où : fin propre
        def interrompu():
            raise KeyboardInterrupt
        wm.main = interrompu
        e = io.StringIO()
        with contextlib.redirect_stderr(e):
            self.assertEqual(wm.execute(), 130)
        self.assertIn("Interrompu (Ctrl-C).", e.getvalue())
        self.assertNotIn("Traceback", e.getvalue())
        # 2) pendant less : un VRAI SIGINT est envoyé à ce processus pendant que less « tourne »
        class Tty(io.StringIO):
            def isatty(self):
                return True
        vus = {}
        def faux_less(cmd, *a, **k):
            vus["gestionnaire"] = signal.getsignal(signal.SIGINT)
            os.kill(os.getpid(), signal.SIGINT)
        wm.NO_PAGER = False
        wm.sys = types.SimpleNamespace(stdin=Tty(), stdout=Tty(), stderr=sys.stderr)
        wm.shutil = types.SimpleNamespace(which=lambda n: "/usr/bin/less")
        wm.subprocess = types.SimpleNamespace(run=faux_less)
        wm.input = lambda *_: ""                                                 # Entrée : ouvrir less
        avant = signal.getsignal(signal.SIGINT)
        try:
            wm.offer_less("/tmp/rapport.txt")
        except KeyboardInterrupt:
            self.fail("Ctrl-C pendant less a levé KeyboardInterrupt (trace d'appels chez l'utilisateur)")
        finally:
            signal.signal(signal.SIGINT, avant)
        self.assertTrue(callable(vus["gestionnaire"]) and vus["gestionnaire"] is not avant)
        self.assertIsNot(vus["gestionnaire"], signal.SIG_IGN)                    # jamais SIG_IGN : less en hériterait

    def test_seuil_de_la_sauvegarde_selon_les_heures_configurees(self):
        """2.34 : âge maximal toléré de la dernière sauvegarde = celui écrit par odoo-backup.sh selon les heures configurées
        (plusieurs sauvegardes par jour : 12 h au lieu de 26 h) ; 26 h tant qu'il n'existe pas ou s'il est illisible."""
        import io, contextlib, time
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        etat = os.path.dirname(self.path("etat-sauvegarde", "x"))
        wm.BACKUP_STATE = etat
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo", "CATCHALL_LOG": "x"}
        wm.run = lambda cmd, timeout=0: (0, "")
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        class C:
            def get(self, k, i): return 0
        succes = self.write("etat-sauvegarde/last-success", "1\t2026-09-30 09:00\tbase\n")
        il_y_a_20_h = time.time() - 20 * 3600
        os.utime(succes, (il_y_a_20_h, il_y_a_20_h))
        def recos():
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(), {"non_filtrees": {}, "jails": {"nginx-x": 1}, "robots": {}}, {})
            return f.getvalue()
        self.assertEqual(wm.backup_threshold_hours(), 26)                              # pas de fichier : une sauvegarde par jour
        self.assertNotIn("dernière sauvegarde d'Odoo réussie", recos())                  # 20 h < 26 h
        self.write("etat-sauvegarde/max-age-hours", "12\n")                              # 09:00 16:00 23:00
        self.assertEqual(wm.backup_threshold_hours(), 12)
        self.assertIn("dernière sauvegarde d'Odoo réussie il y a 20 h (seuil : 12 h)", recos())
        self.write("etat-sauvegarde/max-age-hours", "n'importe quoi\n")
        self.assertEqual(wm.backup_threshold_hours(), 26)                              # illisible : valeur prudente d'avant

    def test_timers_referencant_un_fichier_absent(self):
        """2.33 : timer (systemd ou cron) de nos outils qui lance un script absent ou lit une configuration absente — cas d'un
        --config introuvable, ignoré en silence par odoo-backup.sh avant la 1.5."""
        import unittest.mock as mock
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.SYSTEMD_DIR = os.path.dirname(self.path("sd", "x"))
        script = self.write("scripts/outil.sh", "#!/bin/bash\n")
        conf = self.write("ok.conf", "")
        self.write("sd/odoo-backup.service", f"[Service]\nExecStart={script} --config {conf}\n")
        self.write(f"sd/{wm.UNIT}.service", f"[Service]\nExecStart=/usr/bin/python3 {script}\n")
        cron = self.write("cron/sync", f"SHELL=/bin/bash\nPATH=/usr/bin\n17 * * * * root /usr/bin/flock -n /run/lock/s.lock {script} > /dev/null 2>&1\n")
        with mock.patch.dict(os.environ, {"SYNC_CROWDSEC_CRON_FILE": cron}):
            self.assertEqual(wm.timers_missing_files(), [])                   # tout existe : rien à signaler
            self.assertEqual(wm.analyze_timers(), [])
        # Tout est absent : configuration (--config ET -c ET --config=), script systemd, script cron
        self.write("sd/odoo-backup.service", f"[Service]\nExecStart={script} --config /nulle/odoo-backup.conf\n")
        self.write(f"sd/{wm.UNIT}.service", "[Service]\nExecStart=/usr/bin/python3 /nulle/web-monitor.py -c /nulle/autre.conf\n")
        cron2 = self.write("cron/sync2", "PATH=/usr/bin\n17 * * * * root /nulle/sync-crowdsec-blocklist.sh --config=/nulle/sync.conf\n")
        with mock.patch.dict(os.environ, {"SYNC_CROWDSEC_CRON_FILE": cron2}):
            problemes = sorted(wm.timers_missing_files())
            alertes = wm.analyze_timers()
        self.assertEqual(problemes, [("odoo-backup", "config", "/nulle/odoo-backup.conf"),
                                     ("sync-crowdsec-blocklist", "config", "/nulle/sync.conf"),
                                     ("sync-crowdsec-blocklist", "script", "/nulle/sync-crowdsec-blocklist.sh"),
                                     (wm.UNIT, "config", "/nulle/autre.conf"), (wm.UNIT, "script", "/nulle/web-monitor.py")])
        titres = [wm.TR(a[0]) for a in alertes]
        self.assertIn("odoo-backup : le timer lit un fichier de configuration qui n'existe pas (/nulle/odoo-backup.conf)", titres)
        self.assertIn("sync-crowdsec-blocklist : le timer lance un script qui n'existe pas (/nulle/sync-crowdsec-blocklist.sh)", titres)
        detail = wm.TR(next(a[1][0] for a in alertes if "odoo-backup" in a[0]))
        self.assertIn("odoo-backup.sh --install-timer (sans --config", detail)
        self.assertEqual(next(a[2] for a in alertes if "odoo-backup" in a[0]), ["timer:odoo-backup:config:/nulle/odoo-backup.conf"])

    def test_report_err_status_sans_pager_ni_question(self):
        self.mock_exit("systemctl", 1)
        sd = os.path.dirname(self.path("sd", "x"))
        self.write("sd/odoo-backup.service", "[Service]\nExecStart=/bin/true --config /nulle/odoo-backup.conf\n")
        self.env.update(WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("etat", "x")), WEB_MONITOR_SYSTEMD_DIR=sd,
                        SYNC_CROWDSEC_CRON_FILE=self.path("cron-absent"))
        rc, out, err = self.run_cmd(["python3", self.prog, "--status", "--report-err"])
        self.assertEqual(rc, 0, err)
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : web-monitor\.py v2\.\d+\.\d{8}\.\d{6} — commande : web-monitor\.py --status\n")
        self.assertIn("AVERTISSEMENTS (1) :\n  1. ⚠ odoo-backup : le timer lit un fichier de configuration qui n'existe pas (/nulle/odoo-backup.conf)", rapport)
        self.assertIn("odoo-backup.sh --install-timer", rapport)                    # ligne de détail de l'avertissement

    def test_report_err_desactive_pager_et_questions(self):
        """--report-err implique --no-prompt et --no-pager : un rapport à copier-coller ne s'interrompt jamais."""
        s = open(self.prog, encoding="utf-8").read()
        self.assertIn("NO_PAGER = args.no_pager or args.report_err", s)
        self.assertIn("NO_PROMPT = args.no_prompt or args.report_err", s)

    def test_status_signale_un_timer_vers_un_fichier_absent(self):
        self.mock_exit("systemctl", 1)
        sd = os.path.dirname(self.path("sd", "x"))
        self.write("sd/odoo-backup.service", "[Service]\nExecStart=/bin/true --config /nulle/odoo-backup.conf\n")
        self.env.update(WEB_MONITOR_STATE_DIR=os.path.dirname(self.path("etat", "x")), WEB_MONITOR_SYSTEMD_DIR=sd,
                        SYNC_CROWDSEC_CRON_FILE=self.path("cron-absent"))
        rc, out, err = self.run_cmd(["python3", self.prog, "--status"])
        self.assertEqual(rc, 0, err)
        self.assertIn("⚠ odoo-backup : le timer lit un fichier de configuration qui n'existe pas (/nulle/odoo-backup.conf)", out)

    def test_couleurs_des_connexions_en_terminal_seulement(self):
        """2.28 : connexions du jour en vert, erreurs 5xx en rouge, 429 en jaune, adresse bannie en magenta — dans un
        terminal SEULEMENT (jamais dans un rapport capturé) ; NO_COLOR les retire ; --days 3 : pas de colonne « 7 j »."""
        import io, contextlib, datetime
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo"}
        st, comptes = {}, {}
        for _ in range(3):
            wm.accumulate_ip(st, "203.0.113.9", "GET", "/event", "200", datetime.date(2026, 9, 26), [0, 1, 2])
        wm.accumulate_ip(st, "203.0.113.9", "GET", "/x", "429", datetime.date(2026, 9, 26), [2])
        wm.accumulate_ip(st, "203.0.113.9", "GET", "/y", "502", datetime.date(2026, 9, 26), [2])
        wm.note_account(comptes, "zoe@exemple.org", "203.0.113.9", [0, 1, 2], "2026-09-29 12:36")
        class Tty(io.StringIO):
            def isatty(self):
                return True
        def rendu(tty, no_color=False):
            sortie = Tty() if tty else io.StringIO()
            ancien = os.environ.pop("NO_COLOR", None)
            if no_color:
                os.environ["NO_COLOR"] = "1"
            try:
                with contextlib.redirect_stdout(sortie):
                    wm.show_accounts({"comptes": comptes, "stats_ip": st}, {"203.0.113.9"})
            finally:
                os.environ.pop("NO_COLOR", None)
                if ancien is not None:
                    os.environ["NO_COLOR"] = ancien
            return sortie.getvalue()
        c = rendu(True)
        self.assertIn("aujourd'hui \x1b[1;32m1\x1b[0m", c)                           # connexions du jour : vert
        self.assertIn("\x1b[1;31m2 erreur(s)\x1b[0m", c)                              # il y a une 5xx : rouge
        self.assertIn("\x1b[1;31m502 : 1\x1b[0m", c)
        self.assertIn("\x1b[1;33m429 : 1\x1b[0m", c)                                  # limitation de débit : jaune
        self.assertIn("\x1b[1;35m203.0.113.9 (bannie)\x1b[0m", c)                     # adresse bannie : magenta
        self.assertIn("\x1b[1mzoe@exemple.org\x1b[0m", c)                            # nom en gras
        self.assertNotIn("\x1b[", rendu(False))                                       # rapport capturé : aucun code
        self.assertNotIn("\x1b[", rendu(True, no_color=True))                         # NO_COLOR respecté
        self.assertIn("7 j 1 · 30 j 1", rendu(False))
        wm.DAYS = 3
        self.assertNotIn("7 j", rendu(False))
        self.assertIn("aujourd'hui 1 · 3 j 1", rendu(False))

    def test_unban_check_passe_la_main_a_nginx_log_audit(self):
        """--unban-check, ancienne option de chk-nginx-logs.sh : disponible aussi depuis web-monitor.py."""
        rc, out, err = self.run_cmd(["python3", self.prog, "--unban-check"])
        self.assertEqual(rc, 0, err)
        self.assertIn("REEVALUATION DES BANNISSEMENTS --unban-check --app odoo", out)

    def test_recommandations_precedentes_gardees_48_h(self):
        """2.56 : un passage (ou la relance par la touche b d'app-log-live.py) ne lit que les lignes nouvelles : une adresse recommandée plus tôt et absente de ce passage reste
        recommandée avec sa raison pendant 48 h après sa dernière recommandation, puis est oubliée ; une adresse revue prend la raison du passage en cours."""
        import json
        import time
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.STATE_DIR = self.path("state-reco")
        os.makedirs(wm.STATE_DIR)
        fichier = os.path.join(wm.STATE_DIR, "recommended-bans.json")
        now = time.time()
        with open(fichier, "w") as f:
            json.dump({"when": "x", "time": now - 3600, "ips": [{"ip": "11.35.176.5", "raison": "enquête : Score 4/7", "vu": now - 3600},
                                                              {"ip": "9.9.9.9", "raison": "vieille", "vu": now - 49 * 3600},
                                                              {"ip": "11.0.67.32", "raison": "ancienne raison", "vu": now - 7200}]}, f)
        wm.RECOMMENDED[:] = [("11.0.67.32", "nouvelle raison")]
        wm.remember_recommendations(datetime.datetime.now())
        ips = {x["ip"]: x["raison"] for x in json.load(open(fichier))["ips"]}
        self.assertEqual(ips, {"11.0.67.32": "nouvelle raison", "11.35.176.5": "enquête : Score 4/7"})
        wm.RECOMMENDED.clear()

    def test_raison_detaillee_d_un_recidiviste(self):
        spec = __import__("importlib.util").util.spec_from_file_location("wm", self.prog)
        wm = __import__("importlib.util").util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.RECOMMENDED.clear()
        wm.analyze_nginx_logs(0, "--- Bannissement PERMANENT recommandé : 1 IP récidiviste(s) ---\n"
                                 "  ▶ 11.134.146.52 — 2 jours (23/Sep, 28/Sep), jail nginx-catchall\n RÉSUMÉ\n")
        self.assertEqual(wm.RECOMMENDED, [("11.134.146.52", "récidiviste : 2 jours (23/Sep, 28/Sep), jail nginx-catchall"
                                                             " — bannissements temporaires répétés")])

    def test_seules_les_ip_recommandees_et_commande_dans_le_courriel(self):
        """Avant la 2.5, toutes les IP de la section [10] étaient retenues dès qu'une seule était recommandée."""
        self.passage(ban_ip="45.9.8.7")
        import json
        reco = json.load(open(self.path("state", "recommended-bans.json")))
        self.assertEqual([x["ip"] for x in reco["ips"]], ["45.9.8.7"])            # pas le robot inoffensif
        self.assertIn("Score 5/7, 2 signe(s) d'hostilité", reco["ips"][0]["raison"])
        self.assertIn("web-monitor.py --ban-recommended", self.courriels()[-1])

    @unittest.skipUnless(os.geteuid() == 0, "la question exige root")
    def test_fin_de_passage_o_bannit_toutes_n_aucune(self):
        self.write("fails.txt", "")
        self.env["TEST_BAN_IP"] = "45.9.8.7"
        texte, envoye = self.run_pty(["python3", self.prog, "--no-pager"], [(b"[N] aucune", b"o\n", 0.2)])
        self.assertEqual(envoye, 1)
        self.assertIn("▶ 45.9.8.7", texte)
        self.assertNotIn("▶ 11.68.110.86 —", texte.split("recommandée(s) au bannissement")[-1])
        self.assertIn("--ban 45.9.8.7 --yes", self.bans())
        self.assertIn("1/1 IP bannie(s)", texte)
        os.remove(self.path("bans.log"))
        texte, _ = self.run_pty(["python3", self.prog, "--no-pager"], [(b"[N] aucune", b"\n", 0.2)])
        self.assertIn("Plus tard : web-monitor.py --ban-recommended", texte)
        self.assertEqual(self.bans(), "")

    @unittest.skipUnless(os.geteuid() == 0, "la question exige root")
    def test_fin_de_passage_c_passe_par_l_enquete_de_ban(self):
        self.write("fails.txt", "")
        self.env["TEST_BAN_IP"] = "45.9.8.7"
        self.run_pty(["python3", self.prog, "--no-pager"], [(b"[N] aucune", b"c\n", 0.2)])
        self.assertRegex(self.bans(), r"--ban 45\.9\.8\.7 (--reason .* )?--app")         # nginx-log-audit 2.40 : --reason (justification) avant --app
        self.assertNotIn("--yes", self.bans())                              # --ban interactif : raisonnement et question

    @unittest.skipUnless(os.geteuid() == 0, "le mode normal exige root")
    def test_ban_recommended_apres_un_passage_sans_terminal(self):
        self.passage(ban_ip="45.9.8.7")                                     # comme le timer : pas de terminal
        self.assertEqual(self.bans(), "")
        rc, out, err = self.run_cmd(["python3", self.prog, "--ban-recommended"])
        self.assertEqual(rc, 2)
        self.assertIn("ajouter --yes", err)
        rc, out, err = self.run_cmd(["python3", self.prog, "--ban-recommended", "--yes"])
        self.assertEqual(rc, 0, err)
        self.assertIn("--ban 45.9.8.7 --yes", self.bans())
        rc, out, err = self.run_cmd(["python3", self.prog, "--ban-recommended", "--yes"])
        self.assertIn("Aucune IP recommandée", out)                         # liste traitée : vidée

    def test_verbose_transmis_a_tous_les_programmes_lances(self):
        """2.39 : « web-monitor.py --verbose » n'affichait que SES commandes ; les programmes qu'il lance (app-health-check.py,
        app-log-check.py, nginx-log-audit.sh) ne recevaient pas --verbose. Transmis à tous, et leurs commandes s'affichent."""
        journal = os.path.join(self.d, "argv.log")
        self.env["TEST_ARGV"] = journal
        trace = 'open(os.environ["TEST_ARGV"], "a").write("%s " + " ".join(sys.argv[1:]) + "\\n")\n'
        self.write("prog/app-health-check.py", FAUX_SANITY.replace('if __name__ == "__main__":\n',
                   'if __name__ == "__main__":\n    ' + trace % "app-health-check"))
        self.write("prog/app-log-check.py", "import os, sys\n" + trace % "app-log-check" + 'print("RÉSUMÉ : rien de suspect dans cette fenêtre.")\n'
                   'import os\nopen(os.environ["TEST_ENV_ODOO"],"w").write(os.environ.get("APP_LOG_CHECK_STATE_DIR",""))\n')
        self.write("prog/nginx-log-audit.sh", 'echo "nginx-log-audit $*" >> "$TEST_ARGV"\n' + FAUX_NGINX)
        self.write("prog/sync-crowdsec-blocklist.sh", 'echo "sync-crowdsec $*" >> "$TEST_ARGV"; echo "ok"\n')
        def commandes(*options):
            if os.path.exists(journal):
                os.remove(journal)
            rc, out, err = self.run_cmd(["python3", self.prog, "--dry-run", *options])
            self.assertNotIn("Traceback", err, err)
            with open(journal) as f:
                return {l.split()[0]: l.split()[1:] for l in f.read().splitlines() if l.strip()}, err
        avec, err = commandes("--verbose")
        for programme in ("app-health-check", "app-log-check", "nginx-log-audit", "sync-crowdsec"):
            self.assertIn("--verbose", avec[programme], f"{programme} n'a pas reçu --verbose : {avec[programme]}")
        self.assertIn("+ ", err)                                              # les commandes de web-monitor lui-même
        sans, err = commandes()
        for programme in ("app-health-check", "app-log-check", "nginx-log-audit", "sync-crowdsec"):
            self.assertNotIn("--verbose", sans[programme], f"{programme} : --verbose sans qu'il ait été demandé")

    def test_list_users_details_verbose_affiche_la_commande_psql(self):
        journal = "2026-09-26T10:00:00-0400 odoo18 odoo[1]: x INFO base odoo.addons.base.models.res_users: Login successful for db:base login:m@exemple.org from 11.97.88.180"
        self.write("journal.txt", journal + "\n")
        self.mock("journalctl", f"cat {self.d}/journal.txt")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        self.mock("runuser", 'printf "506\\037m@exemple.org\\037M\\037f\\n"')
        _, out, err = self.run_cmd(["python3", self.prog, "--list-users", "--details", "--verbose"])
        self.assertIn("+ runuser -u postgres -- psql -d base -tA", err)
        self.assertIn("UID Odoo", out)

    def test_geoip_bin_recommande_avec_installation_proposee(self):
        """2.42 : geoip-bin absent (et disponible dans les dépôts) : recommandation MOYENNE et installation proposée en fin de sommaire ;
        paquet introuvable ou déjà installé : aucune recommandation inutile."""
        from unittest import mock
        spec = importlib.util.spec_from_file_location("wm", self.prog)
        wm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo"}
        appels = []
        def faux_run(cmd, timeout=0, env_extra=None):
            appels.append(cmd)
            if cmd[0] == "apt-cache":
                return 0, "geoip-bin:\n  Installed: (none)\n  Candidate: " + wm_candidat[0] + "\n"
            return 0, ""
        wm_candidat = ["1.6.12-10"]
        wm.run = faux_run
        wm.load_sanity_module = lambda: None
        class C:
            def get(self, k, i): return 0
        faits = {"non_filtrees": {}, "jails": {"sshd": 1}, "robots": {}}
        reel = wm.shutil.which
        with mock.patch.object(wm.shutil, "which", lambda n, *a, **k: None if n == "geoiplookup" else reel(n, *a, **k)):
            import contextlib
            import io
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(), faits, {})
            out = f.getvalue()
            self.assertIn("[MOYENNE] geoip-bin absent (recommandé, pas facultatif)", out)
            self.assertRegex(out, r"\w\) Installer geoip-bin \(pays des adresses IP lu localement, sans Internet\) \(apt-get install -y geoip-bin geoip-database\)")
            fonction = next(a[2] for a in wm.ACTIONS if a[1].startswith("apt-get install -y geoip-bin"))
            fonction()
            self.assertIn(["apt-get", "install", "-y", "geoip-bin", "geoip-database"], appels)
            # Paquet introuvable : rien de recommandé
            wm.ACTIONS.clear()
            wm_candidat[0] = "(none)"
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(), faits, {})
            self.assertNotIn("geoip-bin", f.getvalue())
        # Déjà installé : rien non plus
        wm.ACTIONS.clear()
        wm_candidat[0] = "1.6.12-10"
        with mock.patch.object(wm.shutil, "which", lambda n, *a, **k: "/usr/bin/geoiplookup" if n == "geoiplookup" else reel(n, *a, **k)):
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                wm.recommendations(C(), faits, {})
            self.assertNotIn("geoip-bin", f.getvalue())

    def test_sommaire_comptes_lieu_partage_remplace_le_nombre_de_comptes(self):
        """Adresse d'un lieu [partagée] : « (partagée : ETS - Université) » au lieu de « (partagée : 4 comptes) » ; plusieurs comptes sur une
        adresse sans lieu : toujours le nombre ; équipe() : liste blanche + lieux [protégée] (jamais un lieu seulement partagé)."""
        import contextlib
        import io
        ecrire_liste("NGINX_TOOLS_WHITE_LIST", "203.0.113.5   # Étienne (maison)\n")
        ecrire_liste("NGINX_TOOLS_IP_LOCATION", "11.105.0.0/16   # ETS - Université   [partagée]\n203.0.113.64/26   # Bureau   [protégée]\n")
        spec = importlib.util.spec_from_file_location("wm", self.prog)
        wm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo"}
        self.assertEqual(wm.team(), {"203.0.113.5": "Étienne (maison)", "203.0.113.64/26": "Bureau"})
        comptes = {"a@exemple.org": {"n": (1, 3, 3), "last": "2026-10-02 10:00", "ips": {"11.105.216.7": 3, "45.33.32.156": 1}},
                   "b@exemple.org": {"n": (1, 2, 2), "last": "2026-10-02 11:00", "ips": {"11.105.216.7": 2, "45.33.32.156": 2}},
                   "c@exemple.org": {"n": (0, 1, 1), "last": "2026-10-01 11:00", "ips": {"11.105.1.1": 1}}}
        self.assertEqual(wm.shared_mark(comptes), {"45.33.32.156": 2, "11.105.216.7": "ETS - Université", "11.105.1.1": "ETS - Université"})
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.show_accounts({"comptes": comptes}, {})
        texte = re.sub(r"\x1b\[[0-9;]*m", "", f.getvalue())
        self.assertIn("11.105.216.7 (partagée : ETS - Université)", texte)
        self.assertIn("45.33.32.156 (partagée : 2 comptes)", texte)
        self.assertIn("11.105.1.1 (partagée : ETS - Université)", texte)                              # un seul compte, mais lieu partagé
        self.assertEqual(wm.TR(wm.shared_text(4)), "4 comptes")
        self.assertEqual(wm.shared_text("ETS - Université"), "ETS - Université")

    def test_retour_arriere_dans_les_invites(self):
        """2.41 : « Bannir maintenant ? … : v^Hc^H^H^H^H^C » — input() sans readline n'efface pas avec ^H (touche de retour arrière de
        certains terminaux, ssh depuis Windows…). Les programmes qui posent des questions chargent readline : ^H et ^? effacent."""
        try:
            import readline  # noqa: F401
        except ImportError:
            self.skipTest("module readline absent de ce Python")
        charge = ("import importlib.util as u; s = u.spec_from_file_location('p', %r); m = u.module_from_spec(s); s.loader.exec_module(m); "
                  "print('REPONSE=' + repr(input('Bannir ? ')))")
        for programme in ("web-monitor.py", "app-health-check.py"):
            for touche, nom in ((b"\x08", "^H"), (b"\x7f", "^?")):
                with self.subTest(programme=programme, retour_arriere=nom):
                    texte, _ = self.run_pty(["python3", "-c", charge % script_path(programme)], [(b"Bannir ?", b"v" + touche + b"c\n", 0.05)])
                    self.assertIn("REPONSE='c'", texte, f"{nom} n'a pas effacé le « v » : {texte!r}")
        # Témoin : sans readline (Python nu), ^H n'efface rien — c'est le défaut qu'on avait
        texte, _ = self.run_pty(["python3", "-c", "print('REPONSE=' + repr(input('Bannir ? ')))"], [(b"Bannir ?", b"v\x08c\n", 0.05)])
        self.assertNotIn("REPONSE='c'", texte)

    def test_sommaire_comptes_toutes_les_adresses_sans_plus_n(self):
        """2.41 : « Adresses IP : 11.126.46.49 (partagée : 4 comptes), 11.97.88.180, 11.148.77.194 (+1) » dans le sommaire — toutes les
        adresses, jamais « (+N) » (--list-users les montrait déjà toutes)."""
        import contextlib
        import io
        spec = importlib.util.spec_from_file_location("wm", self.prog)
        wm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "odoo", "APP_LABEL": "Odoo"}
        ips = ["11.148.77.194", "11.97.88.180", "11.126.46.49", "11.101.16.52", "11.114.10.1", "45.33.32.156"]
        comptes = {"m@exemple.org": {"n": (1, 6, 6), "last": "2026-10-02 10:00", "ips": {ip: 6 - i for i, ip in enumerate(ips)}},
                   "a@exemple.org": {"n": (0, 1, 1), "last": "2026-10-01 10:00", "ips": {"11.126.46.49": 1}}}
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.show_accounts({"comptes": comptes}, {"11.101.16.52": "banni"})
        ligne = next(l for l in re.sub(r"\x1b\[[0-9;]*m", "", f.getvalue()).splitlines() if "Adresses IP" in l and "11.148.77.194" in l)
        for ip in ips:
            self.assertIn(ip, ligne)
        self.assertIn("11.126.46.49 (partagée : 2 comptes)", ligne)
        self.assertIn("11.101.16.52 (bannie)", ligne)
        self.assertNotRegex(ligne, r"\(\+\d+\)")

    def test_dry_run_sans_courriel_ni_etat(self):
        self.write("fails.txt", "HSTS présent — www : absent")
        rc, out, _ = self.run_cmd(["python3", self.prog, "--dry-run"])
        self.assertIn("non envoyé (--dry-run)", out)
        self.assertEqual(self.courriels(), [])
        self.assertFalse(os.path.exists(os.path.join(self.env["WEB_MONITOR_STATE_DIR"], "last-alert.json")))

    def test_intervalle_valide(self):
        rc, _, err = self.run_cmd(["python3", self.prog, "--install-timer", "--interval-hours", "30"])
        self.assertNotEqual(rc, 0)
        self.assertIn("erreur", err)



class Bilan(EnvTest):
    """--summary (1.3, renommée en 1.4) : valeurs EXACTES sur un jeu de données calculé à la main (dates relatives à aujourd'hui)."""
    def setUp(self):
        super().setUp()
        import datetime, gzip
        self.prog = self.prepare("web-monitor.py")
        T = datetime.date.today(); J = lambda n: T - datetime.timedelta(days=n)
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        ng = lambda d: f"{d:%d}/{mois[d.month - 1]}/{d:%Y}"
        A = lambda ip, d, m, u, c: f'{ip} - - [{ng(d)}:10:00:00 -0400] "{m} {u} HTTP/1.1" {c} 100 "-" "Mozilla/5.0"\n'
        n = os.path.dirname(self.path("nginx", "x"))
        self.write("nginx/rencontres_linux_quebec_prod-access.log", "".join([
            A("10.0.0.1", T, "GET", "/", 200), A("10.0.0.1", T, "GET", "/event", 200), A("10.0.0.2", T, "GET", "/shop", 200),
            A("10.0.0.2", T, "GET", "/web/assets/x.js", 200), A("10.0.0.3", T, "GET", "/img.png", 200),
            A("10.0.0.3", T, "GET", "/contactus", 200), A("10.0.0.4", T, "GET", "/.env", 403), A("10.0.0.5", T, "GET", "/x", 429),
            A("10.0.0.1", T, "GET", "/boom", 500), A("10.0.0.1", T, "POST", "/web/login", 200)]))
        self.write("nginx/rencontres_linux_quebec_prod-access.log.1", "".join([
            A("10.0.0.6", J(3), "GET", "/", 200), A("10.0.0.6", J(3), "GET", "/", 200), A("10.0.0.7", J(3), "GET", "/.git/config", 404),
            A("10.0.0.7", J(3), "GET", "/wp-login.php", 403), A("10.0.0.8", J(3), "GET", "/page", 200)]))
        self.gz = os.path.join(n, "rencontres_linux_quebec_prod-access.log.2.gz")
        with gzip.open(self.gz, "wt") as f:
            f.writelines([A("10.0.0.9", J(20), "GET", "/", 200)] * 4 + [A("10.0.0.10", J(40), "GET", "/", 200)])
        C = lambda ip, d: f'{ip} - [{ng(d)}:01:00:00 -0400] "GET / HTTP/1.1" 444 host="x" ua="-"\n'
        self.write("nginx/odoo-catchall-444.log", "".join([C("9.9.9.1", T)] * 2 + [C("9.9.9.2", J(5))] * 3))
        F = lambda d, ip: f"{d.isoformat()} 03:04:47,123 fail2ban.actions [123]: NOTICE [nginx-catchall] Ban {ip}\n"
        self.write("fail2ban.log", F(T, "1.1.1.1") * 2 + F(T, "2.2.2.2") + F(J(10), "3.3.3.3")
                   + f"{T.isoformat()} 03:05:00,000 fail2ban.actions [123]: NOTICE [x] Unban 1.1.1.1\n")
        self.write("chk/bans.tsv", f"{T.isoformat()} 09:00\tbanni\t5.5.5.5\n{J(8).isoformat()} 09:00\tbanni\t6.6.6.6\n"
                                             f"{T.isoformat()} 10:00\tleve\t6.6.6.6\n")
        self.write("cs/blocked-ips.tsv", f"7.7.7.1\t10\t600\t{J(20).isoformat()} 01:00\t{T.isoformat()} 01:00\n"
                                        f"7.7.7.2\t3\t180\t{J(2).isoformat()} 01:00\t{J(2).isoformat()} 01:00\n"
                                        f"7.7.7.3\t1\t60\t{J(15).isoformat()} 01:00\t{J(15).isoformat()} 01:00\n")
        jl = lambda d, msg: f"{d.isoformat()}T03:00:00-0400 odoo18 odoo[1]: {d.isoformat()} 07:00:00,000 1 {msg}\n"
        self.write("journal.txt", jl(T, "INFO db odoo.addons.base.models.res_users: Login failed for db:x login:a from 1.2.3.4") * 2
                   + jl(T, "ERROR db odoo.sql_db: bad query") + jl(J(4), "ERROR db x: y") + jl(J(4), "ERROR db x: z")
                   + jl(J(4), "CRITICAL db x: w") + jl(T, "INFO db werkzeug: GET /"))
        self.mock("journalctl", f"cat {self.d}/journal.txt")
        self.mock("systemctl", '[[ "$1" == list-unit-files && "$2" == erplibre.service ]] && echo "erplibre.service enabled"; exit 0')
        self.write("logrotate/nginx", "/var/log/nginx/*.log {\n\tdaily\n\tmissingok\n\trotate 14\n\tcompress\n}\n")
        self.write("logrotate/fail2ban", "/var/log/fail2ban.log {\n    weekly\n    rotate 4\n    compress\n}\n")
        self.env["WEB_MONITOR_LOGROTATE_DIR"] = os.path.dirname(self.path("logrotate", "x"))
        self.env.update(WEB_MONITOR_NGINX_DIR=n, WEB_MONITOR_FAIL2BAN_LOG=self.path("fail2ban.log"),
                        SYNC_CROWDSEC_STATE_DIR=os.path.dirname(self.path("cs", "x")), NGINX_LOG_AUDIT_STATE_DIR=os.path.dirname(self.path("chk", "x")))

    def valeurs(self, out, libelle, j12=False):
        """Aujourd'hui, 7 jours, 30 jours (colonnes 1, 4 et 5 depuis la 2.25) ; j12=True : les cinq, dans l'ordre affiché."""
        ligne = next(l for l in out.splitlines() if l.strip().startswith(libelle))
        v = [int(x.replace("\u202f", "")) for x in ligne[48:].split()]
        return v if j12 or len(v) != 5 else [v[0], v[3], v[4]]

    def test_colonnes_j1_et_j2(self):
        """2.25 : J-1 (hier) et J-2 (avant-hier), entre « Aujourd'hui » et « 7 jours »."""
        import datetime
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        _, avant, _ = self.run_cmd(["python3", self.prog, "--summary"])
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            for jours, n in ((1, 3), (2, 2)):
                d = datetime.date.today() - datetime.timedelta(days=jours)
                f.writelines([f'203.0.113.{jours} - - [{d:%d}/{mois[d.month - 1]}/{d:%Y}:10:00:00 -0400] "GET /event HTTP/1.1" 200 900 "-" "Mozilla/5.0"\n'] * n)
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        entete = next(l for l in out.splitlines() if "Aujourd'hui" in l)
        self.assertRegex(entete, r"Aujourd'hui\*?\s+J-1\*?\s+J-2\*?\s+7 jours\*?\s+30 jours")
        a, b = self.valeurs(avant, "Requêtes sur le site", j12=True), self.valeurs(out, "Requêtes sur le site", j12=True)
        self.assertEqual([y - x for x, y in zip(a, b)], [0, 3, 2, 5, 5])       # hier 3, avant-hier 2, inclus dans 7 et 30 j

    def test_option_days(self):
        """2.26 : --days N — période longue de N jours ; colonnes sans objet retirées ; valeur invalide refusée."""
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--days", "3"])
        self.assertEqual(rc, 0, err)
        entete = next(l for l in out.splitlines() if "Aujourd'hui" in l)
        self.assertRegex(entete, r"Aujourd'hui\*?\s+J-1\*?\s+J-2\*?\s+3 jours\*?\s*$")        # plus de « 7 jours »
        self.assertIn("FAITS MARQUANTS (3 jours)", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--days", "1"])
        entete = next(l for l in out.splitlines() if "Aujourd'hui" in l)
        self.assertRegex(entete, r"Aujourd'hui\*?\s+1 jour\*?\s*$")
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--days", "0"])
        self.assertNotEqual(rc, 0)
        self.assertIn("--days attend un nombre de jours entre 1 et 366", err)

    def test_valeurs_exactes(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertEqual(rc, 0, err)
        attendu = {"Requêtes sur le site": [10, 15, 19], "Visiteurs distincts": [5, 8, 9],
                   "Pages vues": [4, 7, 11],                                       # POST et images exclus
                   "Refus 403 (robots, outils": [1, 2, 2], "Tentatives sur le capteur": [2, 5, 5],
                   "Requêtes freinées": [1, 1, 1], "Accès à des fichiers sensibles": [1, 3, 3],
                   "IP bannies par fail2ban": [2, 2, 3],                           # IP distinctes, Unban ignoré
                   "Bannissements manuels": [1, 1, 2],                             # « leve » ignoré
                   "IP de la liste CrowdSec": [1, 2, 3], "Échecs de connexion": [2, 2, 2],
                   "Erreurs Odoo": [1, 4, 4],                                      # INFO non compté
                   "Erreurs serveur": [1, 1, 1]}
        for libelle, v in attendu.items():
            with self.subTest(indicateur=libelle):
                self.assertEqual(self.valeurs(out, libelle), v)
        self.assertNotIn("partielle", out)                                         # la rotation remonte à 40 jours

    def test_faits_marquants_couverture_et_conseils_de_retention(self):
        """1.4 : faits marquants des 30 jours ; couverture EXACTE de chaque journal ; modification à faire pour 3 mois."""
        import datetime
        T = datetime.date.today()
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertEqual(rc, 0, err)
        self.assertIn(f"Jour le plus chargé      : {T:%Y-%m-%d} (10 requêtes)", out)
        self.assertIn("IP les plus actives      : 10.0.0.1 (4), 10.0.0.9 (4)", out)          # égalité : ordre stable
        self.assertRegex(out, r"URL malveillantes        : .*/\.env \(1\)")
        self.assertIn("Pages valides les + vues : / (7)", out)
        self.assertIn("Clients bloqués (403)    : navigateur (autre) (2)", out)
        self.assertIn("fail2ban, IP par jail    : nginx-catchall (3)", out)
        couverture = out[out.index("COUVERTURE DES JOURNAUX"):]
        self.assertRegex(couverture, rf"Journaux du site \(nginx\)\s+{T - datetime.timedelta(days=40):%Y-%m-%d}\s+3 fichier\(s\) — rotation quotidienne, 14 conservé\(s\) ≈ 14 jours")
        self.assertRegex(couverture, rf"fail2ban\.log\s+{T - datetime.timedelta(days=10):%Y-%m-%d}\s+1 fichier\(s\) — rotation hebdomadaire, 4 conservé\(s\) ≈ 28 jours")
        self.assertIn("remplacer « rotate 14 » par « rotate 92 »", out)                   # nginx quotidien : 92 jours
        self.assertIn("remplacer « rotate 4 » par « rotate 14 »", out)                    # fail2ban hebdo : 14 semaines
        self.assertIn("MaxRetentionSec=3month", out)

    def test_entonnoir_valeurs_exactes(self):
        """2.1 : arrivées (site + capteur), rejetées par nginx, transmises à l'application (dont suspectes), en %."""
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        cellules = lambda l: (lambda v: [v[0], v[3], v[4]] if len(v) == 5 else v)(
            re.findall(r"\d+(?: \(\d+ %\))?", next(x for x in out.splitlines() if x.strip().startswith(l))[52:]))
        self.assertEqual(cellules("Arrivées à nginx"), ["12", "20", "24"])
        # 2.9 : /.git/config en 404 avec une PETITE page = réponse de nginx lui-même → rejetée (et non plus « parvenue à
        # Odoo ») ; le cas d'un vrai 404 d'Odoo (page lourde) est couvert par test_appareils_des_visiteurs_humains_et_404_de_nginx.
        self.assertEqual(cellules("Rejetées par nginx"), ["4 (33 %)", "9 (45 %)", "9 (37 %)"])
        self.assertEqual(cellules("Transmises à Odoo"), ["8 (66 %)", "11 (55 %)", "15 (62 %)"])
        self.assertEqual(cellules("dont URL malveillantes"), ["0 (0 %)", "0 (0 %)", "0 (0 %)"])
        self.assertIn("Journal d'Odoo (systemd)", out)

    def test_sommaire_chiffres_alignes_a_droite_avec_les_pourcentages_a_part(self):
        """2.50 : dans chaque colonne de période, les chiffres s'alignent à droite (avec ou sans « (12 %) », qui a sa propre colonne), en français comme en anglais."""
        for langue in ("fr", "en"):
            with self.subTest(langue=langue):
                rc, out, err = self.run_cmd(["python3", self.prog, "--summary", "--lang", langue])
                self.assertEqual(rc, 0, err)
                fins = [[m.end() for m in re.finditer(r"\d(?= \(\d+ %\)|\s{3,}|\s*$)", l[52:])] for l in out.splitlines() if re.match(r"  \S", l) and len(l) > 70]
                fins = [f for f in fins if len(f) >= 3]
                self.assertGreater(len(fins), 15, out)
                colonnes = max(len(f) for f in fins)
                reference = next(f for f in fins if len(f) == colonnes)
                for f in fins:
                    if len(f) == colonnes:
                        self.assertEqual(f, reference, out)

    def test_paquets_bloques_au_pare_feu_par_origine(self):
        """2.1 : compteurs d'iptables par origine ; une règle de port (setup) n'est pas un bannissement manuel."""
        self.mock("iptables", r'''case "$2" in
INPUT) cat <<'X'
Chain INPUT (policy ACCEPT 0 packets, 0 bytes)
    pkts      bytes target     prot opt in     out     source               destination
     150     9000 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0            match-set crowdsec-blocklist-v4 src
      12      720 f2b-nginx-catchall  tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            multiport dports 80,443
       7      420 DROP       all  --  *      *       11.68.110.86        0.0.0.0/0
       3      180 DROP       tcp  --  *      *      !127.0.0.1            0.0.0.0/0            tcp dpt:10000
X
;;
f2b-nginx-catchall) cat <<'X'
Chain f2b-nginx-catchall (1 references)
    pkts      bytes target     prot opt in     out     source               destination
      10      600 REJECT     all  --  *      *       1.2.3.4              0.0.0.0/0            reject-with icmp-port-unreachable
       2      120 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0
X
;;
*) exit 1;;
esac''')
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertIn("Pare-feu : 167 paquets bloqués AVANT nginx", out)
        self.assertIn("CrowdSec : 150, fail2ban : 10, bannissements manuels : 7", out)

    def test_classification_cas_reels_prod_et_dev(self):
        """2.6 : un 403 ou un 444 refuse un CLIENT, il ne rend pas une URL malveillante (cas PROD : PetalBot bloqué sur
        une page d'événement listée comme « URL malveillante ») ; tests du serveur exclus ; IP de l'équipe marquée."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        L = lambda ip, u, c, ua, m="GET": f'{ip} - - [{d}:10:00:00 -0400] "{m} {u} HTTP/1.1" {c} 100 "-" "{ua}"\n'
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines([L("11.119.1.1", "/event/rencontre-linux-octobre-2025-24/track", 403, "Mozilla/5.0 (compatible; PetalBot)")] * 6
                         + [L("11.126.46.49", "/event", 200, "Mozilla/5.0 (Windows NT 10.0) Chrome/152")] * 9
                         + [L("127.0.0.1", "/", 403, "app-health-check/1.0")] * 3
                         + [L("45.1.2.3", "www.instagram.com:443", 400, "-", "CONNECT")])
        self.mock("nginx", '[[ "$1" == -T ]] && printf "location ~ x {\\n    allow 11.126.46.49;\\n    deny all;\\n}\\n"; exit 0')
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        mal = next(l for l in out.splitlines() if l.strip().startswith("URL malveillantes"))
        self.assertNotIn("/event/rencontre-linux-octobre-2025-24/track", mal)
        self.assertIn("www.instagram.com:443 (1)", mal)
        clients = next(l for l in out.splitlines() if l.strip().startswith("Clients bloqués"))
        self.assertIn("PetalBot (6)", clients)
        self.assertNotIn("app-health-check", clients)                    # nos propres tests : exclus
        self.assertIn("11.126.46.49 (9, liste blanche)", out)
        self.assertIn("dont URL malveillantes non filtrées par nginx", out)
        self.assertRegex(out, r"Non filtrées par nginx   : .*\(Odoo a répondu, souvent 404\)")

    def test_appareils_des_visiteurs_humains_et_404_de_nginx(self):
        """2.9 : répartition ordinateur/cellulaire/tablette des HUMAINS probables (pages ET CSS/JS chargés) ; un 404 de
        nginx (petite page) à une URL malveillante compte comme rejeté, pas comme transmis à Odoo."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        L = lambda ip, u, c, ua, t=5000: f'{ip} - - [{d}:10:00:00 -0400] "GET {u} HTTP/1.1" {c} {t} "-" "{ua}"\n'
        IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
        ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/152 Mobile Safari/537.36"
        IPAD = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
        PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
        humain = lambda ip, ua: [L(ip, "/event", 200, ua), L(ip, "/web/assets/1/abc/web.assets_frontend.min.css", 200, ua)]
        self.mock("nginx", '[[ "$1" == -T ]] && printf "location ~ x {\\n    allow 11.126.46.49;\\n}\\n"; exit 0')
        valeurs = lambda o, l: re.findall(r"\d+(?: \(\d+ %\))?", next(x for x in o.splitlines() if x.strip().startswith(l))[52:])
        n = lambda o, l: int(valeurs(o, l)[0].split()[0])
        _, avant, _ = self.run_cmd(["python3", self.prog, "--summary"])       # visiteurs déjà présents dans les données
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines(humain("24.1.1.1", IPHONE) + humain("24.1.1.2", ANDROID) + humain("24.1.1.3", IPAD)
                         + humain("24.1.1.4", PC)
                         + [L("35.1.1.1", "/event", 200, PC)] * 5                          # scraper : jamais de CSS/JS
                         + humain("66.249.66.1", "Mozilla/5.0 (compatible; Googlebot/2.1)")
                         + humain("24.1.1.5", "curl/8.5.0")
                         + humain("11.126.46.49", PC)                                     # équipe (liste blanche)
                         + [L("45.1.1.1", "/.env", 404, "-", 162),                          # 404 de nginx : rejeté
                            L("45.1.1.2", "/.env", 404, "-", 48213)])                       # 404 d'Odoo : non filtré
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertEqual(n(out, "Ordinateur") - n(avant, "Ordinateur"), 1)                  # scraper, équipe, robots exclus
        self.assertEqual(n(out, "Cellulaire") - n(avant, "Cellulaire"), 2)
        self.assertEqual(n(out, "Tablette") - n(avant, "Tablette"), 1)
        self.assertIn("comme un Mac : il compte comme ordinateur", out)
        non_filtrees = next(x for x in out.splitlines() if x.strip().startswith("Non filtrées par nginx"))
        self.assertIn("/.env (1)", non_filtrees)                                             # seul le 404 d'Odoo
        self.assertIn("web-monitor.py v", out.splitlines()[0])

    def test_redirection_de_nginx_a_une_url_malveillante_est_rejetee(self):
        """2.37 : rencontres-linux.quebec redirigeait /.env vers www (« return 301 » de nginx, page de 162 octets) : compté
        « non filtré par nginx » alors que la requête n'avait jamais atteint Odoo. La redirection d'Odoo (plus lourde)
        reste comptée comme transmise."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        L = lambda ip, u, c, t, h: f'{ip} - - [{d}:10:00:00 -0400] "GET {u} HTTP/1.1" {c} {t} "-" "curl/8" host="{h}"\n'
        self.mock("nginx", 'exit 0')
        ligne = lambda o, l: next(x for x in o.splitlines() if x.strip().startswith(l))
        _, avant, _ = self.run_cmd(["python3", self.prog, "--summary"])
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines([L("45.2.2.1", "/.env", 301, 162, "rencontres-linux.quebec"),          # nginx : rejetée
                          L("45.2.2.2", "/.git/config", 301, 169, "odoo18.rencontres-linux.quebec"),  # nginx avec version
                          L("45.2.2.3", "/en_CA/.env", 303, 289, "www.rencontres-linux.quebec")])   # Odoo : transmise
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertNotIn("Traceback", err, err)
        non_filtrees = ligne(out, "Non filtrées par nginx")
        self.assertIn("/en_CA/.env (1)", non_filtrees)
        self.assertNotIn("/.git/config", non_filtrees)
        self.assertNotIn("rencontres-linux.quebec (", ligne(out, "… des non filtrées").replace("www.rencontres-linux.quebec", ""))
        n = lambda o, l: int(re.findall(r"\d+", ligne(o, l)[52:].replace("\u202f", ""))[0])
        self.assertEqual(n(out, "Rejetées par nginx") - n(avant, "Rejetées par nginx"), 2)
        self.assertEqual(n(out, "dont URL malveillantes non filtrées") - n(avant, "dont URL malveillantes non filtrées"), 1)
        self.assertIn("404 et redirections (3xx) de nginx lui-même", out)

    def test_nos_programmes_exclus_de_tous_les_chiffres(self):
        """2.10 : les requêtes de nos programmes (127.0.0.1, adresses du serveur, User-Agent app-health-check) ne
        comptent ni comme visites, ni comme rejets, ni comme erreurs ou accès à des fichiers sensibles : comptées à part."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        valeurs = lambda o, l: re.findall(r"\d+(?: \(\d+ %\))?", next(x for x in o.splitlines() if x.strip().startswith(l))[52:])
        n = lambda o, l: int(valeurs(o, l)[0].split()[0])
        _, avant, _ = self.run_cmd(["python3", self.prog, "--summary"])
        L = lambda ip, u, c, ua: f'{ip} - - [{d}:10:00:00 -0400] "GET {u} HTTP/1.1" {c} 300 "-" "{ua}"\n'
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines([L("127.0.0.1", "/some/page?file=../conf/conf.php", 404, "Mozilla/5.0 Chrome/131"),
                          L("127.0.0.1", "/web/database/manager", 200, "curl/8.14.1"),
                          L("127.0.0.1", "/web", 502, "Mozilla/5.0"),
                          L("198.51.100.20", "/", 200, "Mozilla/5.0 (X11) Chrome/131.0.0.0 Safari/537.36 app-health-check/2.3")])
        with open(self.path("nginx", "odoo-catchall-444.log"), "a") as f:
            f.write(f'127.0.0.1 - [{d}:10:00:00 -0400] "GET / HTTP/1.1" 444 host="198.51.100.7"\n')
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        for ligne in ("Requêtes sur le site", "Visiteurs distincts", "Rejetées par nginx", "Erreurs serveur (5xx)",
                      "Tentatives sur le capteur", "Refus 403"):
            with self.subTest(indicateur=ligne):
                self.assertEqual(n(out, ligne), n(avant, ligne))
        self.assertEqual(n(out, "Requêtes de nos programmes") - n(avant, "Requêtes de nos programmes"), 5)

    def test_refus_des_regles_journal_dedie(self):
        """2.18 : blocked-probes.log (refus des règles de sécurité) compté dans le sommaire."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        self.write("nginx/blocked-probes.log", "".join(
            f'203.0.113.{i} - - [{d}:10:00:00 -0400] "GET {u} HTTP/1.1" 404 162 "-" "curl/8" host="www.exemple.org"\n'
            for i, u in enumerate(["/.env", "/.git/config", "/wp-login.php"])))
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        ligne = next(x for x in out.splitlines() if x.strip().startswith("Refus des règles de sécurité"))
        self.assertRegex(ligne[52:], r"^\s*3\s+0\s+0\s+3\s+3")                 # aujourd'hui, J-1, J-2, 7 j, 30 j
        self.assertIn("Refus des règles (nginx)", out)                     # couverture et espace disque

    def test_403_navigateurs_collecte_dans_les_vrais_journaux(self):
        """2.29 : collecte : pages ordinaires, URL de scanners, adresses distinctes et taille, lues dans le journal nginx."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        lignes = [f'198.51.{i // 250}.{i % 250 + 1} - - [{d}:10:00:00 -0400] "GET / HTTP/1.1" 403 153 "-" "{ua}"\n' for i in range(250)]
        lignes += [f'203.0.113.50 - - [{d}:10:01:00 -0400] "GET /.env HTTP/1.1" 403 153 "-" "{ua}"\n'] * 20
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines(lignes)
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertEqual(rc, 0, err[-400:])
        self.assertIn("250 visent des pages ordinaires (/ (250))", out.replace("\u202f", " "))
        m = re.search(r"(\d+) visent des URL de scanners \(\.env, \.php…\) : refus normal", out)
        self.assertIsNotNone(m, out[-800:])
        self.assertGreaterEqual(int(m.group(1)), 20)                     # + les refus .env déjà présents dans le journal de test
        self.assertIn("Réparties sur 250 adresses différentes", out.replace("\u202f", " "))
        self.assertIn("Réponses très courtes", out)

    def test_googlebot_403_pages_demandees_dans_les_vrais_journaux(self):
        """2.31 : pages demandées par Googlebot refusé en 403, lues dans le journal nginx (scanners exclus)."""
        import datetime
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        d = f"{T:%d}/{mois}/{T:%Y}"
        ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        lignes = [f'66.249.66.{i % 20 + 1} - - [{d}:10:00:00 -0400] "GET /rooms/abc-def/join HTTP/1.1" 403 153 "-" "{ua}"\n' for i in range(120)]
        lignes += [f'66.249.66.5 - - [{d}:10:01:00 -0400] "GET /.env HTTP/1.1" 403 153 "-" "{ua}"\n'] * 5      # scanner : exclu
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.writelines(lignes)
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertEqual(rc, 0, err[-400:])
        self.assertIn("Pages demandées : /rooms/abc-def/join (120).", out)
        self.assertNotIn("/.env (", out.split("Pages demandées :")[1].split("\n")[0])

    def test_ligne_geante_tronquee_sans_explosion_du_temps(self):
        """2.22 : une ligne de journal de plusieurs Mo (attaque, trace énorme) est tronquée à 64 Ko avant les expressions
        régulières : le sommaire reste rapide et ne plante pas."""
        import datetime, time as _t
        T = datetime.date.today()
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][T.month - 1]
        with open(self.path("nginx", "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.write(f'203.0.113.9 - - [{T:%d}/{mois}/{T:%Y}:10:00:00 -0400] "GET /?q=' + "%2e%2e/" * 700000 + ' HTTP/1.1" 404 162 "-" "x"\n')
        debut = _t.time()
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertEqual(rc, 0, err[-500:])
        self.assertLess(_t.time() - debut, 60)

    def test_espace_disque_des_journaux_et_projection(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        bloc = out[out.index("ESPACE DISQUE DES JOURNAUX"):]
        self.assertRegex(bloc, r"Journaux du site \(nginx\)\s+[\d,]+ (o|Ko|Mo)\s+≈ [\d,]+ (o|Ko|Mo)/jour")
        self.assertRegex(bloc, r"Projection à rythme constant : 3 mois ≈ .+ · 6 mois ≈ .+ · 12 mois ≈ .+ — partition de /var/log")
        self.assertIn("--log-retention-months N", bloc)

    def test_retention_suffisante_pas_de_conseil(self):
        self.write("logrotate/nginx", "/var/log/nginx/*.log {\n\tdaily\n\trotate 92\n}\n")
        self.write("logrotate/fail2ban", "/var/log/fail2ban.log {\n    weekly\n    rotate 14\n}\n")
        _, out, _ = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertNotIn("CONSERVER 3 MOIS", out)

    def test_periode_partielle_signalee(self):
        import gzip
        with gzip.open(self.gz, "wt") as f:                                        # plus de ligne de 40 jours
            f.write(open(self.path("nginx", "rencontres_linux_quebec_prod-access.log")).read().splitlines(True)[0])
        rc, out, err = self.run_cmd(["python3", self.prog, "--summary"])
        self.assertIn("30 jours*", out)
        self.assertIn("Période partielle", out)

if __name__ == "__main__":
    unittest.main()
