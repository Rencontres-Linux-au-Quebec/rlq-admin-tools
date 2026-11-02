"""nginx-log-audit.sh — un test par bug trouvé en session (non-régression), plus les comportements clés."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import gzip
import os
import time
import re
import subprocess
import unittest

from helpers import EnvTest

CHROME = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"


def acc(ip, date, time, path, code=200, ua=CHROME):
    return f'{ip} - - [{date}:{time} -0400] "GET {path} HTTP/1.1" {code} 512 "-" "{ua}"\n'


def catchall(ip, date, path="/.env", ua="Mozilla/5.0"):
    return f'{ip} - [{date}:14:32:38 -0400] "GET {path} HTTP/1.1" 444 host="x" ua="{ua}"\n'


class ChkNginxLogs(EnvTest):
    def setUp(self):
        super().setUp()
        self.logs = os.path.dirname(self.path("nginx", "x"))
        self.prog = self.prepare("nginx-log-audit.sh", {"/var/log/nginx": self.logs, "/etc/iptables": self.path("etc-iptables", "x")[:-2]})
        for f in ("rencontres_linux_quebec_prod-error.log", "odoo-catchall-444.log"):
            open(os.path.join(self.logs, f), "a").close()
        self.access = os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log")
        open(self.access, "a").close()
        self.mock_exit("curl", 1)                                    # public IP unavailable by default
        self.mock("iptables", f'F={self.d}/rules; touch $F; o=$1; shift; case $o in -C) grep -qxF "$*" $F;; '
                              f'-I) echo "$*" >> $F;; -D) grep -vxF "$*" $F > $F.t; mv $F.t $F;; esac')
        self.mock("host", 'case "$1" in\n'
                          ' 11.22.62.38) echo "x pointer ec2-11-22-62-38.us-east-2.compute.amazonaws.com.";;\n'
                          ' 66.249.66.1) echo "x pointer crawl-66-249-66-1.googlebot.com.";;\n'
                          ' 11.55.161.77) echo "x pointer 77.161.55.11.bc.googleusercontent.com.";;\n'
                          ' 11.83.10.20) echo "x pointer ip20.ip-51-75-10.eu.";;\n'
                          ' *) exit 1;;\nesac')
        self.mock("getent", '[[ "$1" == ahosts && "$2" == crawl-66-249-66-1.googlebot.com ]] && '
                            'echo "66.249.66.1 STREAM x"; exit 0')
        self.env["NGINX_LOG_AUDIT_STATE_DIR"] = self.path("state", "x")[:-2]

    def add(self, *lines):
        with open(self.access, "a") as f:
            f.writelines(lines)

    def report(self, *args, env_extra=None):
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--init", "--no-prompt", *args], env_extra)
        self.assertNotIn("ARRÊT INATTENDU", err, err)
        return rc, out, err

    def test_263_compare_24_heures_contre_24_precedentes(self):
        """2.63 --compare : la dernière journée contre la précédente (blocages, erreurs, IP), fichier écrit en mode 600, lecture seule."""
        maintenant = time.time()
        def ligne(ip, heure_epoch, code, chemin="/x"):
            date = time.strftime("%d/%b/%Y:%H:%M:%S %z", time.localtime(heure_epoch))
            return f'{ip} - - [{date}] "GET {chemin} HTTP/1.1" {code} 10 "-" "ua"\n'
        self.add(ligne("11.1.1.1", maintenant - 3600, 404),           # dernières 24 h : bloquée
                 ligne("11.1.1.1", maintenant - 7200, 404),           # dernières 24 h : bloquée
                 ligne("11.9.9.9", maintenant - 1800, 200, "/web"),   # dernières 24 h : normale
                 ligne("11.2.2.2", maintenant - 30 * 3600, 404),      # 24 h précédentes : bloquée
                 ligne("11.3.3.3", maintenant - 50 * 3600, 404))      # hors fenêtre : ignorée
        fichier = os.path.join(self.d, "comparaison.txt")
        rc, out, err = self.report("--compare", fichier)
        self.assertEqual(rc, 0, err)
        texte = open(fichier, encoding="utf-8").read()
        self.assertIn("Bloquées (403/404/405/429/444) : 2  (24 h précédentes : 1)", texte)
        self.assertIn("Requêtes         :        3  (24 h précédentes :        1)", texte)
        self.assertNotIn("11.3.3.3", texte, "une ligne hors des 48 heures n'est pas comptée")
        self.assertEqual(oct(os.stat(fichier).st_mode & 0o777), "0o600", "le rapport contient des adresses IP")
        self.assertNotIn("Rapport nginx", out, "le mode --compare ne lance pas le rapport complet")

    def ip_block(self, out, ip):
        """Bloc d'enquête de la section [10] (ou --investigate) pour une IP."""
        m = re.search(r"▶ " + re.escape(ip) + r" .*?(?=\n  ▶ |\n--- |\n=====|\Z)", out, re.S)
        return m.group(0) if m else ""

    # --- bugs found during the session ------------------------------------------------------------------------------------
    def test_report_err(self):
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--no-prompt", "--report-err"])
        self.assertIn("RAPPORT D'ERREURS (--report-err)", out)
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : nginx-log-audit\.sh v2\.\d+\.\d{8}\.\d{6} — commande : nginx-log-audit\.sh prod --no-prompt\n")
        self.assertIn(f"code de sortie {rc}", rapport)
        self.assertIn("Bilan     : ", rapport)

    def test_error_log_refus_voulus_resumes_pas_listes_comme_erreurs(self):
        """2.17 : « access forbidden by rule » (accès restreint par IP) et « limiting requests » (limitation de débit) sont
        des refus VOULUS : résumés, jamais listés en jaune comme des erreurs ; une vraie erreur reste listée."""
        err = os.path.join(self.logs, "rencontres_linux_quebec_prod-error.log")
        regle = '2026/09/30 04:14:09 [error] 436452#436452: *{n} access forbidden by rule, client: {ip}, server: odoo-dev.x, request: "GET / HTTP/1.1", host: "x"\n'
        with open(err, "a") as f:
            f.writelines(regle.format(n=i, ip="11.160.68.185") for i in range(3))
            f.write(regle.format(n=9, ip="11.59.36.114"))
            f.write('2026/09/30 04:30:00 [error] 4#4: *3 limiting requests, excess: 20.5 by zone "perip", client: 203.0.113.9, server: x, request: "GET /web HTTP/1.1", host: "x"\n')
        rc, out, e = self.run_cmd(["bash", self.prog, "prod", "--no-prompt"])
        s7 = out[out.index("--- [7]"):out.index("--- [8]")]
        self.assertIn("RIEN", s7)
        self.assertIn("4 refus par règle d'accès (access forbidden by rule) — attendu : accès restreint par IP ; clients les plus actifs : 11.160.68.185 (3), 11.59.36.114 (1)", s7)
        self.assertIn("1 requêtes freinées par la limitation de débit (voir [429])", s7)
        self.assertNotIn("access forbidden by rule, client", s7)                 # never listed as errors
        with open(err, "a") as f:
            f.write('2026/09/30 05:00:00 [error] 4#4: *7 open() "/srv/x" failed (13: Permission denied), client: 1.2.3.4, server: x, request: "GET /x HTTP/1.1"\n')
        rc, out, e = self.run_cmd(["bash", self.prog, "prod", "--no-prompt"])
        s7 = out[out.index("--- [7]"):out.index("--- [8]")]
        self.assertIn("Permission denied", s7)                                   # une vraie erreur reste visible
        self.assertNotIn("RIEN", s7)

    def test_sigpipe_ip_tres_active_fail2ban_details(self):
        """1.27 : arrêt en code 141 sur une IP à 770 requêtes (plus de 64 Ko dans un tube)."""
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "w") as f:
            f.writelines(catchall("11.89.160.73", "25/Sep/2026", f"/.env{i}") for i in range(770))
        self.mock("fail2ban-client", f'case "$2" in "") echo \'`- Jail list:\tnginx-catchall\';; '
                                     f'*) echo "|- Banned IP list:\t11.89.160.73"; '
                                     f'echo \'`- File list:\t{self.logs}/odoo-catchall-444.log\';; esac')
        rc, out, err = self.report("--fail2ban", "--details")
        self.assertEqual(rc, 0, err)
        self.assertIn("770 requêtes au total", out)
        self.assertIn("RÉSUMÉ", out)

    def test_champs_alignes_meme_si_champ_vide(self):
        """1.24 : IFS=tab fusionnait les champs vides — « Codes HTTP : 24x curl/8.5.0 »."""
        for p in ("/.env", "/.git/HEAD", "/wp-login.php", "/phpmyadmin/", "/config.php"):
            self.add(*(acc("11.83.10.20", "25/Sep/2026", f"07:12:1{k}", f"{p}?x={k}", 403, "curl/8.5.0") for k in range(4)))
        _, out, _ = self.report()
        bloc = self.ip_block(out, "11.83.10.20")
        codes = re.search(r"Codes HTTP : (.*)", bloc).group(1)
        self.assertIn("403", codes)
        self.assertNotIn("curl", codes)
        self.assertIn("Serveur loué", bloc)                            # OVH reverse DNS recognized (pattern added in 1.24)

    def test_motifs_awk_non_degrades(self):
        """1.25 : motifs passés par « awk -v », dégradés par gawk (« \\.env » devenait « .env »)."""
        self.add(*(acc("198.51.100.9", "25/Sep/2026", f"07:50:0{k}", f"/xenv{k}", 404, "python-requests/2.32") for k in range(9)))
        _, out, _ = self.report()
        bloc = self.ip_block(out, "198.51.100.9")
        self.assertIn("Recherche de fichiers sensibles : 0", bloc, "« /xenv » compté à tort comme recherche de « .env »")

    def test_ip_protegees_jamais_proposees(self):
        """1.25 : 127.0.0.1 (app-health-check.py --target local) proposé au bannissement en DEV."""
        pages = ["/", "/robots.txt", "/sitemap.xml", "/web/login", "/event", "/shop", "/blog", "/contactus", "/x?y=1"]
        self.add(*(acc("127.0.0.1", "25/Sep/2026", f"07:24:5{i}", p) for i, p in enumerate(pages)))
        self.add(acc("127.0.0.1", "25/Sep/2026", "07:24:59", "/", 403, "curl/8.14.1"))
        _, out, _ = self.report()
        self.assertNotIn("▶ 127.0.0.1", out)
        rc, _, err = self.run_cmd(["bash", self.prog, "--ban", "127.0.0.1", "--yes"])
        self.assertEqual(rc, 1)
        self.assertIn("REFUSÉ", err)

    def test_moteur_verifie_jamais_propose_faux_moteur_signale(self):
        pages = [f"/page{i}" for i in range(10)]
        self.add(*(acc("66.249.66.1", "25/Sep/2026", f"07:10:0{i}", p, 200,
                       "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)") for i, p in enumerate(pages)))
        self.add(acc("11.55.161.77", "25/Sep/2026", "07:11:00", "/.env", 404, "Mozilla/5.0 (compatible; Googlebot/2.1)"),
                 acc("11.55.161.77", "25/Sep/2026", "07:11:01", "/.git/config", 404, "Mozilla/5.0 (compatible; GPTBot/1.1)"),
                 acc("11.55.161.77", "25/Sep/2026", "07:11:02", "/x.bak", 404, "Mozilla/5.0 (compatible; ChatGPT-User/1.0)"))
        _, vrai, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "66.249.66.1", "--no-prompt"])
        self.assertIn("Moteur de recherche VÉRIFIÉ", vrai)
        self.assertNotIn("bannissement recommandé", vrai)
        _, faux, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.55.161.77", "--no-prompt"])
        self.assertIn("Faux moteur de recherche : se dit robot de Google", faux)   # 1.26 : ne cite que les moteurs

    def test_section9_nat_ignore_multi_organisations_signale(self):
        """1.22 : un NAT (plusieurs navigateurs) n'est pas une usurpation ; plusieurs ORGANISATIONS de robots, si."""
        for ua in ("Mozilla/5.0 (Windows NT 10.0) Firefox/140.0", "Mozilla/5.0 (Macintosh) Safari/605.1.15",
                   "Mozilla/5.0 (X11; Linux x86_64) Chrome/140.0", "Mozilla/5.0 (iPhone) Mobile Safari/604.1"):
            self.add(acc("11.123.0.10", "25/Sep/2026", "08:00:00", "/", 200, ua))
        for ua in ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                   "Mozilla/5.0 (compatible; GPTBot/1.1; +https://openai.com/gptbot)",
                   "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)"):
            self.add(acc("11.55.161.77", "25/Sep/2026", "08:00:01", "/", 200, ua))
        _, out, _ = self.report()
        s9 = out[out.index("--- [9]"):out.index("--- [10]")]
        self.assertIn("11.55.161.77", s9)
        self.assertNotIn("11.123.0.10", s9)

    def test_section11_requetes_dynamiques_en_parallele(self):
        """2.29 : 6 requêtes dynamiques dans la même seconde AVEC erreurs -> signalé (information seulement) ; sans erreur (plusieurs personnes derrière une même
        adresse), statiques, adresse protégée ou lieu connu (université) -> RIEN."""
        self.lieux("203.0.113.80/32   # ETS - Université   [partagée]\n")
        for sec in ("09:00:01", "09:00:02", "09:00:03"):
            self.add(*(acc("203.0.113.50", "25/Sep/2026", sec, f"/event/{i}/track", 500 if i == 0 else 200) for i in range(6)))
        for sec in ("09:00:01", "09:00:02", "09:00:03", "09:00:04"):
            self.add(*(acc("203.0.113.90", "25/Sep/2026", sec, f"/survey/{i}/submit") for i in range(9)))             # beaucoup de monde, aucune erreur : normal
            self.add(*(acc("203.0.113.80", "25/Sep/2026", sec, f"/event/{i}/register", 500) for i in range(6)))       # known place: ignored
        self.add(*(acc("203.0.113.60", "25/Sep/2026", "09:01:00", f"/web/assets/{i}/a.js", 500) for i in range(12)))     # statiques : exclus
        self.add(*(acc("127.0.0.1", "25/Sep/2026", "09:03:00", f"/p{i}", 500) for i in range(6)))
        _, out, _ = self.report()
        s11 = out[out.index("--- [11]"):]
        s11 = s11[:s11.index("\n\n")] if "\n\n" in s11 else s11
        self.assertIn("203.0.113.50 : 3 secondes", s11)
        self.assertIn("dont 3 en erreur 5xx/429", s11)
        self.assertIn("aucun bannissement proposé", s11)
        for autre in ("203.0.113.90", "203.0.113.80", "203.0.113.60", "127.0.0.1"):
            self.assertNotIn(autre, s11)
        _, out2, _ = self.report("--parallel-threshold", "7")
        self.assertIn("RIEN", out2[out2.index("--- [11]"):])

    def test_recidiviste_sur_rotation_gz_une_seule_fois(self):
        """1.28 : IP bannie active sur plusieurs jours (dont une rotation .gz), bannie par deux jails."""
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "w") as f:
            f.write(catchall("11.89.160.73", "25/Sep/2026"))
        with open(os.path.join(self.logs, "odoo-catchall-444.log.1"), "w") as f:
            f.write(catchall("11.89.160.73", "18/Sep/2026"))
        with gzip.open(os.path.join(self.logs, "odoo-catchall-444.log.2.gz"), "wt") as f:
            f.write(catchall("11.89.160.73", "15/Sep/2026"))
        self.mock("fail2ban-client", f'case "$2" in "") echo \'`- Jail list:\tnginx-catchall, nginx-sensitive-files\';; '
                                     f'*) echo "|- Banned IP list:\t11.89.160.73"; '
                                     f'echo \'`- File list:\t{self.logs}/odoo-catchall-444.log\';; esac')
        _, out, _ = self.report("--fail2ban")
        self.assertIn("actif sur 3 jours distincts (15/Sep, 18/Sep, 25/Sep)", out)
        recap = out[out.index("Bannissement PERMANENT recommandé"):]
        self.assertEqual(recap.count("▶ 11.89.160.73"), 1, "doublon dans le récapitulatif")

    def test_fail2ban_progression_un_fichier_a_la_fois_sans_relecture(self):
        """2.20 : « nginx-log-audit.sh --fail2ban --verbose » semblait gelé — aucune ligne pendant la lecture des journaux
        compressés, relus pour CHAQUE jail (même ceux sans IP bannie). Maintenant : un fichier à la fois, avec le temps
        écoulé ; un jail sans IP bannie ne lit rien ; un fichier surveillé par deux jails n'est lu qu'une fois."""
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "w") as f:
            f.write(catchall("11.89.160.73", "25/Sep/2026"))
        with open(os.path.join(self.logs, "odoo-catchall-444.log.1"), "w") as f:
            f.write(catchall("11.89.160.73", "18/Sep/2026"))
        with gzip.open(os.path.join(self.logs, "odoo-catchall-444.log.2.gz"), "wt") as f:
            f.write(catchall("11.89.160.73", "15/Sep/2026"))
        fichier = f"{self.logs}/odoo-catchall-444.log"
        self.mock("fail2ban-client", f'case "$2" in "") echo \'`- Jail list:\tjail-a, jail-b, jail-c\';; '
                                     f'jail-c) echo "|- Banned IP list:"; echo \'`- File list:\t{self.logs}/autre.log\';; '
                                     f'*) echo "|- Banned IP list:\t11.89.160.73"; echo \'`- File list:\t{fichier}\';; esac')
        rc, out, err = self.report("--fail2ban", "--verbose", "--details")
        self.assertEqual(rc, 0, err)
        lignes = [re.sub(r"^\[\s*\d+ s\] ", "", l) for l in err.splitlines() if re.match(r"^\[\s*\d+ s\] ", l)]
        self.assertIn("Jail jail-a : 1 IP bannies ; lecture des journaux surveillés (1 fichiers et leurs rotations)", lignes)
        self.assertIn("Lecture du journal 1/3 : odoo-catchall-444.log (1 Ko)", lignes)
        self.assertIn("Lecture du journal 2/3 : odoo-catchall-444.log.1 (1 Ko)", lignes)
        self.assertTrue(any(l.startswith("Lecture du journal 3/3 : odoo-catchall-444.log.2.gz (1 Ko, compressé)") for l in lignes), lignes)
        self.assertEqual(sum(l.startswith("Lecture du journal 1/3") for l in lignes), 1, "journal relu pour le second jail")
        self.assertIn("Journal odoo-catchall-444.log déjà lu pour un autre jail : réutilisé", lignes)
        self.assertIn("Jail jail-a — IP 1/1 : 11.89.160.73 (DNS inverse, whois, requêtes dans les journaux)", lignes)
        self.assertFalse(any(l.startswith("Jail jail-c") for l in lignes), "un jail sans IP bannie ne doit rien lire")
        self.assertFalse(any("autre.log" in l for l in lignes))
        self.assertIn("Aucune IP actuellement bannie", out)
        self.assertIn("actif sur 3 jours distincts (15/Sep, 18/Sep, 25/Sep)", out)       # the result does not change
        # Without --verbose nor terminal (scheduled task, pipe): no progress line
        rc, out, err = self.report("--fail2ban")
        self.assertNotRegex(err, r"\[\s*\d+ s\]")

    def test_progression_un_point_par_journal_sans_details(self):
        """2.47 : sans --details, une seule ligne « Lecture des journaux » puis un point par journal lu,
        sans le détail de chaque fichier (le détail reste disponible avec --details)."""
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "w") as f:
            f.write(catchall("11.89.160.73", "25/Sep/2026"))
        with open(os.path.join(self.logs, "odoo-catchall-444.log.1"), "w") as f:
            f.write(catchall("11.89.160.73", "18/Sep/2026"))
        with gzip.open(os.path.join(self.logs, "odoo-catchall-444.log.2.gz"), "wt") as f:
            f.write(catchall("11.89.160.73", "15/Sep/2026"))
        fichier = f"{self.logs}/odoo-catchall-444.log"
        self.mock("fail2ban-client", f'case "$2" in "") echo \'`- Jail list:\tjail-a\';; '
                                     f'*) echo "|- Banned IP list:\t11.89.160.73"; echo \'`- File list:\t{fichier}\';; esac')
        rc, out, err = self.report("--fail2ban", "--verbose")
        self.assertEqual(rc, 0, err)
        lignes = err.splitlines()
        self.assertTrue(any(re.fullmatch(r"\[\s*\d+ s\] Lecture des journaux", l) for l in lignes), lignes)
        self.assertFalse(any("Lecture du journal" in l for l in lignes), "détail par fichier affiché sans --details")
        self.assertIn(". . .", lignes, "un point par journal lu attendu")
        self.assertNotIn(". . . .", lignes)

    @unittest.skipUnless(os.geteuid() == 0, "--unban-low-score exige root")
    def test_unban_low_score_leve_seulement_si_unban_check_recommande(self):
        """2.50 : --unban-low-score applique le verdict de --unban-check (même processus, journaux lus une fois).
        Une IP « garder » n'est JAMAIS levée (même avec un score bas) ; une IP « lever » l'est avec --yes.
        Une étape par adresse est affichée (erreur standard, terminal ou --verbose)."""
        garder = "11.89.160.73"      # 3 refus sur le site : indices d'hostilité, verdict « garder »
        lever = "11.89.160.80"       # 3 pages normales, sans rafale ni signe d'hostilité : verdict « lever »
        self.add(*(acc(garder, "25/Sep/2026", f"07:12:1{k}", f"{p}?x={k}", 403, "curl/8.5.0") for k, p in enumerate(["/.env", "/.git/config", "/wp-admin/"] * 2)))
        self.add(*(acc(lever, "25/Sep/2026", f"08:00:0{k}", f"/page-{k}", 200, "Mozilla/5.0 (X11; Linux x86_64) Firefox/120.0") for k in range(3)))
        self.mock("fail2ban-client", f'case "$1 $2" in "ping ") exit 0;; "status ") echo \'`- Jail list:\tjail-a\';; '
                                     f'"status jail-a") echo "|- Banned IP list:\t{garder} {lever}"; echo \'`- File list:\t{self.logs}/odoo-catchall-444.log\';; '
                                     f'"set jail-a") echo "$*" >> {self.d}/f2b-set.log;; '
                                     f'*) exit 0;; esac')
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--unban-low-score", "--no-prompt", "--yes", "--verbose"])
        self.assertEqual(rc, 0, err)
        self.assertRegex(out, r"\s" + re.escape(garder) + r"\s+\d/7\s+garder\s+fail2ban:jail-a\n", out)
        self.assertRegex(out, r"\s" + re.escape(lever) + r"\s+\d/7\s+LEVÉE recommandée\s+fail2ban:jail-a\n", out)
        self.assertIn(f"Réévaluation 1/2 : {garder} (lecture seule)", err)                # a step is shown per address
        self.assertIn(f"Réévaluation 2/2 : {lever} (lecture seule)", err)
        with open(f"{self.d}/f2b-set.log") as f:
            levees = f.read()
        self.assertIn(f"unbanip {lever}", levees)
        self.assertNotIn(f"unbanip {garder}", levees, "une IP « garder » ne doit jamais être levée")

    @unittest.skipUnless(os.geteuid() == 0, "--unban-low-score exige root")
    def test_unban_low_score_ordre_numerique_des_ip(self):
        """2.51 : les IP sont listées dans l'ordre numérique (13.x avant 104.x), pas dans l'ordre alphabétique."""
        self.mock("fail2ban-client", 'case "$1 $2" in "ping ") exit 0;; "status ") echo \'`- Jail list:\tjail-a\';; '
                                     '"status jail-a") echo "|- Banned IP list:\t104.8.8.8 13.8.8.8 9.1.1.1";; *) exit 0;; esac')
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--unban-low-score", "--no-prompt"])
        self.assertEqual(rc, 0, err)
        ordre = [out.index(ip) for ip in ("9.1.1.1", "13.8.8.8", "104.8.8.8")]
        self.assertEqual(ordre, sorted(ordre), "ordre numérique attendu : 9.x, 13.x, 104.x")

    def test_rafale_du_service_worker_ne_compte_pas_mais_une_vraie_rafale_oui(self):
        """2.52 : les pages préchargées par le service worker (Referer .../service-worker.js) ne forment pas une rafale
        humaine ; le même volume de pages sans ce Referer reste une rafale (témoin)."""
        sw = "https://www.rencontres-linux.quebec/en_CA/event/service-worker.js"
        self.add(*(f'198.51.100.61 - - [26/Oct/2026:10:00:00 -0400] "GET /en_CA/event/page-{i} HTTP/1.1" 200 512 "{sw}" "{CHROME}"\n'
                   for i in range(16)))
        self.add(*(acc("198.51.100.62", "26/Oct/2026", "10:00:00", f"/en_CA/event/page-{i}", 200, CHROME) for i in range(16)))
        _, prefetch, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "198.51.100.61", "--no-prompt"])
        self.assertNotRegex(prefetch, r"Rafale : \d+ pages distinctes")
        self.assertIn("au plus 0 pages", prefetch)
        _, vraie, err = self.run_cmd(["bash", self.prog, "prod", "--investigate", "198.51.100.62", "--no-prompt"])
        self.assertRegex(vraie, r"Rafale : 16 pages distinctes")

    @unittest.skipUnless(os.geteuid() == 0, "--unban-check exige root")
    def test_icones_du_capteur_catchall_ne_justifient_pas_le_bannissement(self):
        """2.52 : apple-touch-icon et favicon.ico reçus du capteur catch-all (ancien nom de serveur) ne sont pas hostiles :
        sans autre trace, l'IP est proposée à la levée au lieu d'être justifiée."""
        self._bannissements()
        with open(os.path.join(self.d, "rules"), "a") as f:
            f.write("INPUT -s 198.51.100.60 -j DROP\n")
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "w") as f:
            f.writelines(catchall("198.51.100.60", "26/Oct/2026", p, "com.apple.WebKit.Networking")
                         for p in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/favicon.ico"))
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--unban-check", "--no-prompt"])
        self.assertEqual(rc, 0, err)
        self.assertIn("3 requêtes d'icône", out)
        apres = out[out.index("3 requêtes d'icône"):].split("\n  ▶")[0]
        self.assertIn("non hostiles", apres)
        self.assertNotIn("Bannissement JUSTIFIÉ", apres)

    def test_ban_ufw_inactif_utilise_iptables_et_sauvegarde_sans_f2b(self):
        """1.27 : ufw installé mais inactif utilisé à tort ; règles non sauvegardées ; chaînes fail2ban à exclure."""
        self.mock("ufw", '[[ "$1" == status ]] && echo "Status: inactive"; echo "ufw $*" >> ' + self.d + "/ufw.log")
        v4 = self.path("etc-iptables", "rules.v4")
        self.mock("netfilter-persistent", f'{{ echo ":f2b-sshd - [0:0]"; echo "-A INPUT -j f2b-sshd"; '
                                          f'sed "s/^/-A /" {self.d}/rules; }} > {v4}')
        self._preuves_sqli("203.0.113.10")
        rc, out, _ = self.run_cmd(["bash", self.prog, "--ban", "203.0.113.10", "--yes"])
        self.assertEqual(rc, 0)
        self.assertIn("Règle iptables ajoutée", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "ufw.log")) and "deny" in open(os.path.join(self.d, "ufw.log")).read())
        sauvegarde = open(v4).read()
        self.assertIn("203.0.113.10", sauvegarde)
        self.assertNotIn("f2b-", sauvegarde)

    def test_ban_installe_iptables_persistent_s_il_manque(self):
        """Pas de ufw ni d'outil de sauvegarde : le paquet est installé (root, apt) puis les règles sont enregistrées — au lieu de seulement conseiller de l'installer."""
        if os.geteuid() != 0:
            self.skipTest("l'installation de paquets demande root")
        v4 = self.path("etc-iptables", "rules.v4")
        self.mock("apt-get", f'echo "$@" >> {self.d}/apt.log; printf "#!/bin/bash\\nsed s/^/-A\\ / {self.d}/rules > {v4}\\n" > {self.bin}/netfilter-persistent; chmod +x {self.bin}/netfilter-persistent')
        self._preuves_sqli("203.0.113.11")
        rc, out, _ = self.run_cmd(["bash", self.prog, "--ban", "203.0.113.11", "--yes"])
        self.assertEqual(rc, 0, out)
        self.assertIn("installation de iptables-persistent et ipset-persistent", out)
        self.assertIn("install -y iptables-persistent ipset-persistent", open(os.path.join(self.d, "apt.log")).read())
        self.assertIn("203.0.113.11", open(v4).read())
        self.assertNotIn("mémoire seulement", out)

    def test_environnement_lab_detecte(self):
        """[3] Le journal du site « lab » (rencontres_linux_quebec_lab-access.log) est reconnu comme prod et dev."""
        os.remove(self.access)
        lab = os.path.join(self.logs, "rencontres_linux_quebec_lab-access.log")
        open(lab, "w").close()
        open(os.path.join(self.logs, "rencontres_linux_quebec_lab-error.log"), "w").close()
        rc, out, err = self.run_cmd(["bash", self.prog, "--init", "--no-prompt"])
        self.assertNotIn("aucun fichier /var/log", err)
        self.assertIn("Rapport nginx — lab", out)                                  # the detected environment is "lab"
        open(self.access, "w").close()                                                  # prod AND lab: the auto-detection does not choose
        rc, out, err = self.run_cmd(["bash", self.prog, "--init", "--no-prompt"])
        self.assertEqual(rc, 1)
        self.assertIn("plusieurs jeux de logs (prod lab)", err)

    def test_robot_inoffensif_jamais_propose_et_url_affichees(self):
        """1.33 : faux positif réel — 11.68.110.86, 3/7 avec seulement des signes d'AUTOMATISATION (outil de
        script, double identité, hébergeur) pour 3 visites de /events. Proposition seulement avec un signe d'hostilité."""
        self.mock("host", '[[ "$1" == 11.68.110.86 ]] && echo "x pointer 86.110.68.11.bc.googleusercontent.com."')
        self.add(acc("11.68.110.86", "27/Sep/2026", "03:04:47", "/events", 403, "python-requests/2.33.0"),
                 acc("11.68.110.86", "27/Sep/2026", "03:37:43", "/events", 303, "Mozilla/5.0"),
                 acc("11.68.110.86", "27/Sep/2026", "03:37:43", "/en_CA/events", 200, "Mozilla/5.0"),
                 acc("11.68.110.86", "27/Sep/2026", "04:00:17", "/events", 303, "Mozilla/5.0 (compatible; DocsalotResearch/1.0)"),
                 acc("11.68.110.86", "27/Sep/2026", "04:00:18", "/en_CA/events", 200, "Mozilla/5.0 (compatible; DocsalotResearch/1.0)"))
        _, out, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.68.110.86", "--no-prompt"])
        self.assertIn("3x /events", out)
        self.assertIn("2x /en_CA/events", out)
        self.assertIn("Signes d'hostilité : 0", out)
        self.assertIn("pas de bannissement proposé", out)
        self.assertNotIn("bannissement recommandé", out)

    def test_signe_d_hostilite_toujours_propose(self):
        """Un vrai scanner (recherches de .env, .git… en 403) reste proposé : la nouvelle règle ne rate pas les attaques."""
        for p in ("/.env", "/.git/HEAD", "/wp-login.php", "/phpmyadmin/", "/config.php"):
            self.add(*(acc("11.83.10.20", "25/Sep/2026", f"07:12:1{k}", f"{p}?x={k}", 403, "curl/8.5.0") for k in range(4)))
        _, out, _ = self.report()
        bloc = self.ip_block(out, "11.83.10.20")
        self.assertIn("bannissement recommandé", bloc)
        self.assertRegex(bloc, r"Signes d'hostilité : [1-9]")

    # --- 2.1: reasoning before --ban, airy output, color of malicious elements ---------------------------------
    def _robot_et_scanner(self):
        self.mock("host", '[[ "$1" == 11.68.110.86 ]] && echo "x pointer 86.110.68.11.bc.googleusercontent.com."; exit 0')
        self.add(acc("11.68.110.86", "27/Sep/2026", "03:04:47", "/events", 403, "python-requests/2.33.0"),
                 acc("11.68.110.86", "27/Sep/2026", "03:37:43", "/en_CA/events", 200, "Mozilla/5.0"))
        for p in ("/.env", "/.git/HEAD", "/wp-login.php", "/phpmyadmin/", "/config.php"):
            self.add(*(acc("11.83.10.20", "25/Sep/2026", f"07:12:1{k}", f"{p}?x={k}", 403, "curl/8.5.0") for k in range(4)))

    def _preuves_sqli(self, ip):
        """2.69 : --ban exige des preuves ; trois tentatives d'injection SQL (404) de cette IP en fournissent."""
        self.add(*(acc(ip, "27/Sep/2026", f"09:0{k}:00", f"/es/shop?order={k}%20union%20select%201,2", 404, "Mozilla/5.0")
                   for k in range(3)))

    @unittest.skipUnless(os.geteuid() == 0, "--ban exige root")
    def test_ban_affiche_le_raisonnement_et_avertit_sans_hostilite(self):
        self._robot_et_scanner()
        rc, out, err = self.run_cmd(["bash", self.prog, "--ban", "11.68.110.86"], input_text="n\n")
        saisie = out + err
        self.assertIn("Enquête détaillée sur les requêtes au site", out)
        self.assertIn("URL demandées :", out)
        self.assertIn("Signes d'hostilité : 0", out)
        self.assertIn("ATTENTION : aucun signe d'hostilité", out)
        self.assertLess(out.index("PREUVES RASSEMBLÉES POUR"), saisie.index("LES PREUVES NE JUSTIFIENT PAS CE BANNISSEMENT"))
        self.assertNotEqual(rc, 0)                                                     # 2.69 : refusé, aucune preuve pour
        self.assertIn("Refusé.", saisie)
        self.assertNotIn("Ceci va bloquer TOUT le trafic", out)                        # la question de bannissement n'est jamais posée
        self.assertIn("PTR : 86.110.68.11.bc.googleusercontent.com", out)             # same DNS answer as the investigation
        self.assertIn("robot probablement\n", out)
        self.assertIn("inoffensif (vérifier les URL demandées ci-dessus)", out)          # full verdict, not truncated
        rc, out, err = self.run_cmd(["bash", self.prog, "--ban", "11.83.10.20"], input_text="n\n")
        self.assertIn("Recherche de fichiers sensibles : 20", out)
        self.assertNotIn("ATTENTION : aucun signe d'hostilité", out)

    def test_enquete_aeree(self):
        self._robot_et_scanner()
        _, out, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.83.10.20", "--no-prompt"])
        bloc = out[out.index("▶ 11.83.10.20"):]
        for titre in ("\n\n      Indices :\n", "\n\n      Pour vérifier soi-même :\n        host 11.83.10.20\n"):
            self.assertIn(titre, bloc)
        self.assertNotIn("Commandes équivalentes : host", bloc)                          # no line longer than 150 characters

    def test_malveillant_en_magenta_dans_un_terminal_seulement(self):
        self._robot_et_scanner()
        texte, _ = self.run_pty(["bash", self.prog, "prod", "--investigate", "11.83.10.20", "--no-prompt"], [], keep_ansi=True)
        self.assertIn("\x1b[1;35m/.env", texte)
        self.assertRegex(texte, r"\dx\x1b\[1;35m403")
        r = subprocess.run(["bash", self.prog, "prod", "--investigate", "11.83.10.20", "--no-prompt"], capture_output=True, env=self.env)
        self.assertNotIn(b"\x1b[", r.stdout)

    # --- 2.11: address ranges (mobile phone with a dynamic address) ----------------------------------------------------
    def test_plages_equipe_et_liste_blanche(self):
        """11.148.77.105 puis 11.148.77.5 : plage 11.148.77.0/24 dans TEAM_IPS ; plage « allow » de nginx reconnue."""
        import datetime
        d = datetime.date.today().strftime("%d/%b/%Y")
        L = lambda ip, s, u, c, ua: f'{ip} - - [{d}:10:00:{s:02d} -0400] "GET {u} HTTP/1.1" {c} 300 "-" "{ua}"\n'
        self.liste_blanche("11.148.77.5   # Étienne (cellulaire, adresse actuelle)\n")        # adresse de la liste blanche
        lignes = []
        for ip in ("11.148.77.5", "198.51.100.77"):
            lignes += [L(ip, i, f"/page{i}", 200, "python-requests/2.32") for i in range(10)]
            lignes += [L(ip, 20 + i, u, 404, "python-requests/2.32") for i, u in enumerate(["/.env", "/.git/config"])]
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(lignes)
        self.mock("nginx", '[[ "$1" == -T ]] && printf "location ~ x {\\n    allow 198.51.100.0/24;\\n    deny all;\\n}\\n"; exit 0')
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "11.148.77.5"])
        self.assertIn("IP protégée (IP de l'équipe)", out)                 # adresse actuelle du cellulaire (2.12)
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "198.51.100.77"])
        self.assertIn("liste blanche, plage 198.51.100.0/24", out)
        self.assertNotIn("bannissement recommandé", out)

    # --- 2.13: single team list (apps/team-ips.list) -----------------------------------------------------------------
    def test_liste_unique_de_l_equipe(self):
        self.liste_blanche("198.51.100.200   # bénévole (essai)\n")
        import datetime
        d = datetime.date.today().strftime("%d/%b/%Y")
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(f'198.51.100.200 - - [{d}:10:00:{i:02d} -0400] "GET /.env HTTP/1.1" 404 300 "-" "python-requests/2"\n' for i in range(12))
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "198.51.100.200"])
        self.assertIn("IP protégée (IP de l'équipe)", out)

    # --- 2.10: an IP connected to Odoo with an account is never proposed for banning -----------------------------------
    def test_ip_connectee_a_odoo_jamais_proposee(self):
        import datetime
        d = datetime.date.today().strftime("%d/%b/%Y")
        L = lambda s, u, c, ua: f'203.0.113.9 - - [{d}:10:00:{s:02d} -0400] "GET {u} HTTP/1.1" {c} 300 "-" "{ua}"\n'
        lignes = [L(i, f"/page{i}", 200, "Mozilla/5.0 Chrome/152") for i in range(10)]
        lignes += [L(20 + i, u, 404, "python-requests/2.32") for i, u in enumerate(["/.env", "/.git/config", "/wp-login.php"])]
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(lignes)
        self.mock("journalctl", 'echo "2026-09-20T09:00:00-0400 odoo18 odoo[1]: 2026-09-20 13:00:00,1 1 INFO base odoo.addons.base.models.res_users: '
                                'Login successful for db:base login:benevole@exemple.org from 203.0.113.9"')
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "203.0.113.9"])
        self.assertIn("benevole@exemple.org (1 connexions, dernière 2026-09-20T09:00)", out)
        self.assertIn("connectée à Odoo avec le compte benevole@exemple.org : un compte n'est pas une preuve de bonne foi", out)
        self.assertNotIn("bannissement recommandé", out)
        if os.geteuid() == 0:                                             # --ban: reason "against", verdict
            self.mock("iptables", '[[ "$1" == -S ]] && echo "-P INPUT ACCEPT"; exit 1')
            rc, out, err = self.run_cmd(["bash", self.prog, "--ban", "203.0.113.9"], input_text="")
            self.assertIn("− connectée à Odoo avec un compte (benevole@exemple.org)", out)
            self.assertNotIn("bannissement justifié", out)

    # --- 2.60: --ban-sqli shows the context of each address; an address with normal activity in Odoo is never banned in bulk ---
    def test_ban_sqli_contexte_et_activite_normale_jamais_bannie_en_lot(self):
        import datetime
        if os.geteuid() != 0:
            self.skipTest("--ban-sqli demande root")
        d = datetime.date.today().strftime("%d/%b/%Y")
        sqli = "/es/shop?order=1%20union%20select%201,2"

        def ligne(ip, meth, u, c, s):
            return f'{ip} - - [{d}:10:00:{s:02d} -0400] "{meth} {u} HTTP/1.1" {c} 300 "-" "Mozilla/5.0 Chrome/152"\n'
        lignes = [
            ligne("203.0.113.50", "GET", sqli, 200, 1),                  # connecté à Odoo : jamais bannie en lot
            ligne("203.0.113.50", "POST", "/shop/cart/update", 200, 2),
            ligne("203.0.113.60", "GET", sqli, 404, 3),                  # attaque seule : bannie
            ligne("198.51.100.7", "GET", sqli, 200, 4),                  # a passé une commande : jamais bannie en lot
            ligne("198.51.100.7", "POST", "/shop/confirm_order", 200, 5),
        ]
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(lignes)
        self.mock("journalctl", 'echo "2026-09-20T09:00:00-0400 odoo18 odoo[1]: 2026-09-20 13:00:00,1 1 INFO base odoo.addons.base.models.res_users: '
                                'Login successful for db:base login:benevole@exemple.org from 203.0.113.50"')
        self.mock("iptables", f'echo "$@" >> {self.d}/iptables.log; [[ "$1" == -C ]] && exit 1; exit 0')
        rc, out, err = self.run_cmd(["bash", self.prog, "--ban-sqli", "--no-lookup"], input_text="")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("comptes Odoo connectés : benevole@exemple.org", out)
        self.assertIn("panier, commande ou paiement : 1 requêtes", out)
        self.assertIn("URL les plus demandées : 1× ", out)
        self.assertIn("activité Odoo normale : jamais bannie en lot (nginx-log-audit.sh --ban 203.0.113.50", out)
        self.assertIn("activité Odoo normale : jamais bannie en lot (nginx-log-audit.sh --ban 198.51.100.7", out)
        self.assertIn("2 adresses ont une activité Odoo normale (connexion ou commande) : elles ne seront PAS bannies en lot.", out)
        self.assertEqual(out.count("!! réponse 2xx"), 2, out)               # 2 adresses seulement : la 404 n'est pas « réussie »
        self.assertIn("DNS inverse : non vérifié (--no-lookup)", out)
        with open(os.path.join(self.d, "iptables.log")) as f:
            insertions = [l for l in f if l.startswith("-I ")]    # -C : simple vérification « déjà bannie »
        self.assertEqual(insertions, [], insertions)                # 2.69 : sans terminal, aucune insertion ; jamais en lot
        rc, out, err = self.run_cmd(["bash", self.prog, "--ban-sqli", "--no-lookup", "--yes"])
        self.assertNotEqual(rc, 0)                                  # 2.69 : --yes refusé pour --ban-sqli
        self.assertIn("n'accepte pas --yes", out + err)

    # --- 2.8: user logged in to the back office (real case 11.97.88.180) ------------------------------------------------
    def test_back_office_sans_fausse_rafale_et_boucle_signalee(self):
        """Une page du back-office déclenche des dizaines d'appels internes : ce n'est pas une rafale de pages ; une URL
        répétée des milliers de fois (get_web_dialog_size_config) est une boucle de module, pas une attaque."""
        import datetime
        d = datetime.date.today().strftime("%d/%b/%Y")
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152.0.0.0 Safari/537.36"
        L = lambda sec, u, c: f'11.97.88.180 - - [{d}:12:02:{sec:02d} -0400] "POST {u} HTTP/1.1" {c} 300 "-" "{ua}"\n'
        lignes = [L(i % 10, f"/web/dataset/call_kw/modele{i}/web_read", 200) for i in range(20)]
        lignes += [L(i % 60, f"/mail/thread/data?n={i}", 200) for i in range(5)]
        lignes += [L(i % 60, "/web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config", 200 if i % 3 else 429) for i in range(300)]
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(lignes)
        self.mock("journalctl", 'echo "2026-09-28T11:02:07-0400 odoo18 run.sh[812]: 2026-09-28 15:02:07,1 812 INFO linux_meetup_odoo_18 '
                                'odoo.addons.base.models.res_users: Login successful for db:linux_meetup_odoo_18 login:jean@exemple.org from 11.97.88.180"')
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "11.97.88.180"])
        self.assertIn("[i] Connectée à Odoo avec un compte (journal, 100 jours) :", out)
        self.assertIn("jean@exemple.org (1 connexions, dernière 2026-09-28T11:02)", out)
        self.assertNotRegex(out, r"\[✓\] Rafale")                          # appels internes : pas des pages
        self.assertIn("[i] Session ouverte dans le back-office : 325 appels internes", out)
        self.assertRegex(out, r"\[i\] Répétition : 92 % des requêtes sur une seule URL \(300 x /web/dataset/call_kw/ir\.config_parameter/get_web_dialog_size_config\)")

    # --- 2.7: requests of our programs excluded; devices in --stats -----------------------------------------------------
    def test_nos_programmes_exclus_du_rapport_et_appareils_dans_stats(self):
        import datetime
        T = datetime.date.today()
        d = T.strftime("%d/%b/%Y")
        L = lambda ip, u, c, ua: f'{ip} - - [{d}:10:00:00 -0400] "GET {u} HTTP/1.1" {c} 300 "-" "{ua}"\n'
        IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"
        PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/152 Safari/537.36"
        humain = lambda ip, ua: [L(ip, "/event", 200, ua), L(ip, "/web/assets/1/abc/web.assets_frontend.min.css", 200, ua)]
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines([L("127.0.0.1", "/some/page?file=../conf/conf.php", 404, "Mozilla/5.0 Chrome/131 app-health-check/2.3")] * 3
                         + humain("24.1.1.1", IPHONE) + humain("24.1.1.2", IPHONE) + humain("24.1.1.3", PC)
                         + [L("35.1.1.1", "/event", 200, PC)] * 4)                                # scraper sans CSS/JS
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--init", "--no-prompt"])
        self.assertIn("3 requêtes de nos propres programmes exclues de ce rapport", out)
        self.assertNotIn("127.0.0.1 - -", out)
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--stats", "--no-prompt"])
        self.assertIn("(3 de nos propres programmes exclues", out)
        bloc = out[out.index("--- Appareils des visiteurs (humains probables) ---"):]
        self.assertRegex(bloc, r"Ordinateur\s+1 \( *33\.3%\)")
        self.assertRegex(bloc, r"Cellulaire\s+2 \( *66\.7%\)")
        self.assertRegex(bloc, r"Tablette\s+0 \( *0\.0%\)")
        self.assertRegex(bloc, r"Total\s+3 visiteurs humains probables")

    # --- 2.5 : preuves avant un bannissement (toutes les sources) ----------------------------------------------------
    def _preuves(self, ip, dig=None, getent="exit 2", journal="", f2b="", catchall="", site="", option="--ban"):
        """Lance --ban en interactif (refus faute de réponse) et renvoie la sortie sans couleurs."""
        import gzip, re as _re
        self.mock("iptables", '[[ "$1" == -S ]] && echo "-P INPUT ACCEPT"; exit 1')
        if dig is not None:
            self.mock("host", dig)                       # simulated DNS answer (host, like the investigation)
        self.mock("getent", getent)
        self.mock("journalctl", f"printf '%s' '{journal}'")
        os.makedirs(self.path("f2b"), exist_ok=True)
        with gzip.open(self.path("f2b", "fail2ban.log.1.gz"), "wt") as g:
            g.write(f2b)
        self.write("f2b/fail2ban.log", "")
        self.env["FAIL2BAN_LOG_FILE"] = self.path("f2b", "fail2ban.log")
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "a") as f:
            f.write(catchall)
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "a") as f:
            f.write(site)
        rc, out, err = self.run_cmd(["bash", self.prog, option, ip], input_text="")
        return _re.sub(r"\x1b\[[0-9;]*m", "", out + err)

    @unittest.skipUnless(os.geteuid() == 0, "--ban exige root")
    def test_preuves_scanner_banni_par_le_capteur(self):
        """Cas DEV réel : 11.134.146.52 bannie par nginx-catchall — avant la 2.5, « aucune occurrence » et « enquête
        indisponible », car seuls les journaux du SITE étaient lus."""
        out = self._preuves(
            "11.134.146.52", dig='[[ "$1" == 11.134.146.52 ]] && echo "x domain name pointer scanner-20.ch1.censys-scanner.com."; exit 0',
            getent='[[ "$1" == ahosts ]] && echo "11.134.146.52 STREAM x"; exit 0',
            f2b="2026-09-23 04:11:06,220 fail2ban.actions [812]: NOTICE  [nginx-catchall] Ban 11.134.146.52\n"
                "2026-09-28 05:02:44,303 fail2ban.actions [812]: NOTICE  [nginx-catchall] Ban 11.134.146.52\n",
            catchall='11.134.146.52 - [23/Sep/2026:04:11:02 -0400] "GET / HTTP/1.1" 444 host="198.51.100.7"\n')
        self.assertIn("scanner-20.ch1.censys-scanner.com (confirmé", out)
        self.assertIn("Scanner Internet déclaré", out)
        self.assertIn("Jail nginx-catchall : 2 bannissements temporaires les 2026-09-23, 2026-09-28", out)
        self.assertIn("Capteur catch-all : 1 requêtes", out)
        self.assertIn("Verdict : bannissement justifié", out)
        self.assertNotIn("Aucune occurrence trouvée", out)
        self.assertNotIn("enquête indisponible", out)

    @unittest.skipUnless(os.geteuid() == 0, "--evidence lit les journaux du système")
    def test_evidence_preuves_et_verdict_sans_question(self):
        """2.26 : --evidence IP = les preuves et le verdict de --ban, sans question ni bannissement (utilisé par app-log-live.py)."""
        out = self._preuves(
            "11.134.146.52", dig='[[ "$1" == 11.134.146.52 ]] && echo "x domain name pointer scanner-20.ch1.censys-scanner.com."; exit 0',
            getent='[[ "$1" == ahosts ]] && echo "11.134.146.52 STREAM x"; exit 0',
            f2b="2026-09-23 04:11:06,220 fail2ban.actions [812]: NOTICE  [nginx-catchall] Ban 11.134.146.52\n"
                "2026-09-28 05:02:44,303 fail2ban.actions [812]: NOTICE  [nginx-catchall] Ban 11.134.146.52\n",
            catchall='11.134.146.52 - [23/Sep/2026:04:11:02 -0400] "GET / HTTP/1.1" 444 host="198.51.100.7"\n', option="--evidence")
        self.assertIn("PREUVES RASSEMBLÉES POUR 11.134.146.52", out)
        self.assertIn("récidive : 2 bannissements temporaires par fail2ban (nginx-catchall)", out)
        self.assertIn("Verdict : bannissement justifié", out)
        self.assertNotIn("Ceci va bloquer", out)                                         # aucune question de bannissement

    @unittest.skipUnless(os.geteuid() == 0, "--ban exige root")
    def test_preuves_jail_sshd_sans_ptr_avec_journal(self):
        out = self._preuves(
            "11.110.46.244", dig="exit 0",
            journal="2026-09-27T03:10:01-0400 odoo18 sshd[901]: Invalid user admin from 11.110.46.244 port 51234",
            f2b="2026-09-26 03:10:05,1 fail2ban.actions [812]: NOTICE  [sshd] Ban 11.110.46.244\n"
                "2026-09-27 03:10:05,1 fail2ban.actions [812]: NOTICE  [sshd] Ban 11.110.46.244\n")
        self.assertIn("PTR : aucun", out)
        self.assertIn("Journal système (jails hors nginx : sshd)", out)
        self.assertIn("Invalid user admin from 11.110.46.244", out)
        self.assertIn("+ récidive : 2 bannissements temporaires par fail2ban (sshd)", out)

    @unittest.skipUnless(os.geteuid() == 0, "--ban exige root")
    def test_preuves_dns_injoignable_ou_absent(self):
        out = self._preuves("198.51.100.99", dig='echo ";; connection timed out; no servers could be reached"; exit 1')
        self.assertIn("PTR : non vérifiable — délai dépassé", out)
        self.assertIn("Aucune preuve dans les journaux conservés", out)   # rien d'autre : ne pas bannir

    @unittest.skipUnless(os.geteuid() == 0, "--ban exige root")
    def test_preuves_sans_ptr_seul_ne_justifie_jamais(self):
        """Absence de PTR = indice FAIBLE : une IP sans aucune activité ne doit jamais obtenir « justifié »."""
        out = self._preuves("198.51.100.98", dig="exit 0")
        self.assertIn("Indice faible (jamais suffisant seul)", out)
        self.assertIn("Aucune preuve dans les journaux conservés", out)
        self.assertNotIn("bannissement justifié", out)

    @unittest.skipUnless(os.geteuid() == 0, "--ban exige root")
    def test_preuves_vrai_moteur_de_recherche_plaide_contre(self):
        jour = __import__("datetime").date.today().strftime("%d/%b/%Y")
        out = self._preuves(
            "66.249.66.1", dig='echo "x domain name pointer crawl-66-249-66-1.googlebot.com."; exit 0',
            getent='[[ "$1" == ahosts ]] && echo "66.249.66.1 STREAM x"; exit 0',
            site=f'66.249.66.1 - - [{jour}:10:00:00 -0400] "GET /event HTTP/1.1" 200 100 "-" "Googlebot/2.1"\n')
        self.assertIn("− moteur de recherche AUTHENTIQUE", out)
        self.assertIn("Verdict : ne pas bannir", out)
        self.assertNotIn("bannissement justifié", out)

    # --- 2.4 : export et import des bannissements entre serveurs ----------------------------------------------------------
    @unittest.skipUnless(os.geteuid() == 0, "--export-bans et --import-bans exigent root")
    def test_export_puis_import_classe_et_ne_bannit_que_les_nouvelles(self):
        self._bannissements()                              # 5 manual bans, among non-manual rules
        with open(os.path.join(self.env["NGINX_LOG_AUDIT_STATE_DIR"], "bans.tsv"), "w") as f:
            f.write("2026-09-25 08:00\tbanni\t11.55.161.77\n")
        rc, export, err = self.run_cmd(["bash", self.prog, "--export-bans"])
        self.assertEqual(rc, 0, err)
        self.assertIn("11.55.161.77\t2026-09-25 08:00\t", export)
        self.assertNotIn("nginx-log-audit.sh v", export)                                      # the redirected list stays clean...
        self.assertRegex(err.splitlines()[0], r"^nginx-log-audit\.sh v\d")                     # ... the version is the first line, on the error output
        self.assertEqual(len([l for l in export.splitlines() if l and not l.startswith("#")]), 5)   # non-manual rules excluded
        # Destination server: 11.68.110.86 already banned; addition of a private IP, an invalid line and a duplicate
        with open(os.path.join(self.d, "rules"), "w") as f:
            f.write("INPUT -s 11.68.110.86 -j DROP\n")
        fichier = self.write("export.tsv", export + "10.0.0.5\t\t\npas-une-ip\t\t\n11.55.161.77\t\t\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--import-bans", fichier], input_text="")
        self.assertIn("Annulé.", out)                                                         # without answer: nothing
        self.assertNotIn("11.55.161.77", open(os.path.join(self.d, "rules")).read())
        self.assertRegex(out, r"\[protégée ici\] 11\.126\.46\.49")                        # liste blanche nginx locale
        self.assertRegex(out, r"\[protégée ici\] 10\.0\.0\.5")
        self.assertIn("[invalide] pas-une-ip", out)
        self.assertIn("3 à bannir, 1 déjà bannies ici, 2 protégées ici (ignorées), 1 invalides.", out)
        self.add(*(acc("198.51.100.99", "27/Sep/2026", f"10:0{k}:00", "/es/shop?x=1%20union%20select%201,2", 404, "Mozilla/5.0")
                   for k in range(3)))                                                            # 2.69 : preuves avant le bannissement importé
        rc, out, err = self.run_cmd(["bash", self.prog, "--import-bans", "-", "--yes"], input_text=export)
        self.assertIn("3 IP bannies", out)
        regles = open(os.path.join(self.d, "rules")).read()
        for ip in ("11.55.161.77", "11.159.48.202", "198.51.100.99"):
            self.assertIn(ip, regles)
        self.assertNotIn("11.126.46.49", regles)
        journal = open(os.path.join(self.env["NGINX_LOG_AUDIT_STATE_DIR"], "bans.tsv")).read()
        self.assertRegex(journal, r"\tbanni\t11\.55\.161\.77\timporté de \S+( — [^\t\n]*)?(\t[^\n]*)?\n")          # origine en 4e colonne (2.40 : justification, qui)

    # --- --unban-check (1.34) ------------------------------------------------------------------------------------------
    def _bannissements(self):
        """Six bannissements de natures différentes, mêlés aux règles qui ne sont PAS des bannissements manuels."""
        self.mock("iptables", f'F={self.d}/rules; touch $F; o=$1; shift\ncase $o in\n'
                              f' -S) echo "-P INPUT ACCEPT"; echo "-A INPUT ! -s 127.0.0.1/32 -p tcp -m tcp --dport 10000 -j DROP"; '
                              f'echo "-A INPUT -m set --match-set crowdsec-blocklist-v4 src -j DROP"; echo "-A INPUT -j f2b-sshd"; '
                              f'sed -E "s#^INPUT -s ([^ ]+) -j DROP\\$#-A INPUT -s \\1/32 -j DROP#" $F;;\n'
                              f' -C) grep -qxF "$*" $F;; -I) echo "$*" >> $F;; -D) grep -qxF "$*" $F || exit 1; grep -vxF "$*" $F > $F.t; mv $F.t $F;;\nesac')
        with open(os.path.join(self.d, "rules"), "w") as f:
            f.writelines(f"INPUT -s {ip} -j DROP\n" for ip in ("11.68.110.86", "11.55.161.77", "11.159.48.202", "11.126.46.49", "198.51.100.99"))
        self.mock("host", 'case "$1" in 11.68.110.86) echo "x pointer 86.110.68.11.bc.googleusercontent.com.";; '
                          '11.55.161.77) echo "x pointer 77.161.55.11.bc.googleusercontent.com.";; *) exit 1;; esac')
        self.mock("nginx", '[[ "$1" == -T ]] && printf "allow 11.126.46.49;\\n"')
        self.add(acc("11.68.110.86", "27/Sep/2026", "03:04:47", "/events", 403, "python-requests/2.33.0"),
                 acc("11.68.110.86", "27/Sep/2026", "03:37:43", "/en_CA/events", 200, "Mozilla/5.0"),
                 acc("11.55.161.77", "25/Sep/2026", "12:22:01", "/config/.env", 404, "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
                 acc("11.55.161.77", "25/Sep/2026", "12:22:02", "/src/.env", 404, "CCBot/2.0"),
                 acc("11.55.161.77", "25/Sep/2026", "12:22:03", "/app/.env", 404, "Mozilla/5.0 (compatible; GPTBot/1.1)"),
                 acc("11.126.46.49", "26/Sep/2026", "10:00:00", "/web", 200, "Mozilla/5.0 (Windows NT 10.0) Chrome/152"))
        with open(os.path.join(self.logs, "odoo-catchall-444.log"), "w") as f:
            f.write(catchall("11.159.48.202", "25/Sep/2026", "/.env"))

    @unittest.skipUnless(os.geteuid() == 0, "--unban-check exige root")
    def test_unban_check_verdicts(self):
        self._bannissements()
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--unban-check", "--no-prompt"])
        self.assertEqual(rc, 0, err)
        self.assertIn("5 bannissements manuels", out)                 # port rules, ipset, fail2ban excluded
        bloc = lambda ip: out[out.index(f"] {ip} —"):].split("\n--- [")[0]
        self.assertIn("Levée RECOMMANDÉE : aucun signe d'hostilité", bloc("11.68.110.86"))
        self.assertIn("1x /events", bloc("11.68.110.86"))
        self.assertIn("Bannissement JUSTIFIÉ", bloc("11.55.161.77"))
        self.assertIn("Bannissement JUSTIFIÉ : scanner", bloc("11.159.48.202"))   # catch-all seulement
        self.assertIn("IP protégée", bloc("11.126.46.49"))
        self.assertIn("Réévaluation impossible", bloc("198.51.100.99"))
        self.assertNotRegex(out, r"banni le \S+ \S+\S+ \S+", "date doublée")
        self.assertIn("2 justifiés, 2 levées recommandées", out)

    @unittest.skipUnless(os.geteuid() == 0, "--unban-check exige root")
    def test_unban_check_refus_repetes_justifient_le_bannissement(self):
        """2.45 : une IP sans aucune requête au site ni au capteur catch-all, mais refusée à répétition (blocked-probes.log),
        est justifiée (ce sont des refus certains), au lieu d'être « sans trace »."""
        self._bannissements()
        with open(os.path.join(self.d, "rules"), "a") as f:
            f.write("INPUT -s 198.51.100.98 -j DROP\n")
        with open(os.path.join(self.logs, "blocked-probes.log"), "w") as f:
            f.writelines(acc("198.51.100.98", "26/Oct/2026", f"09:00:{i:02d}", "/.git/config", 404, "curl/8.5.0") for i in range(3))
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--unban-check", "--no-prompt"])
        self.assertEqual(rc, 0, err)
        bloc = out[out.index("] 198.51.100.98 "):].split("\n--- [")[0]
        self.assertIn("requêtes REFUSÉES par nginx", bloc)
        self.assertIn("Bannissement JUSTIFIÉ : requêtes répétées refusées", bloc)
        self.assertNotIn("Réévaluation impossible", bloc)

    @unittest.skipUnless(os.geteuid() == 0, "--unban-check exige root")
    def test_unban_check_une_seule_rafale_a_verifier(self):
        """2.45 : une seule rafale de pages, sans signe fort, n'est plus un motif suffisant pour garder le bannissement :
        « à vérifier » ; la section de revue liste l'adresse avec les commandes à lancer."""
        self._bannissements()
        with open(os.path.join(self.d, "rules"), "a") as f:
            f.write("INPUT -s 198.51.100.97 -j DROP\n")
        self.add(*(acc("198.51.100.97", "26/Oct/2026", "10:00:00", f"/shop/produit-{i}", 200, CHROME) for i in range(16)))
        rc, out, err = self.run_cmd(["bash", self.prog, "prod", "--unban-check", "--no-prompt"])
        self.assertEqual(rc, 0, err)
        bloc = out[out.index("] 198.51.100.97 "):].split("\n--- [")[0]
        self.assertIn("À VÉRIFIER : un seul signe d'hostilité", bloc)
        self.assertNotIn("Bannissement JUSTIFIÉ", bloc)
        self.assertIn("1 à vérifier", out)
        revue = out[out.index("AUTRES POINTS À RE-VÉRIFIER"):]
        self.assertIn("nginx-log-audit.sh --investigate 198.51.100.97 --no-prompt", revue)
        self.assertIn("1) Adresses de l'équipe", revue)
        self.assertIn("5) Bannissements à vérifier à la main", revue)

    @unittest.skipUnless(os.geteuid() == 0, "--unban-check exige root")
    def test_unban_check_leve_meme_si_le_fichier_n_est_pas_executable(self):
        """1.34 : la relance directe exigeait le droit d'exécution — lancé par « bash », la levée échouait en silence
        (« Permission denied » filtré) et arrêtait le script. Relance désormais par « bash »."""
        self._bannissements()
        os.chmod(self.prog, 0o644)
        # 2.51: addresses are in numeric order (11.68 before 11.126), so the answers follow that order.
        text, sent = self.run_pty(["bash", self.prog, "prod", "--unban-check"],
                                  [(b"Lever le bannissement de 11.68.110.86", b"n\n", 0.3),
                                   (b"Lever le bannissement de 11.126.46.49", b"o\n", 0.3)])
        self.assertIn("Règle iptables retirée pour 11.126.46.49", text)
        self.assertIn("Bannissement conservé", text)
        self.assertIn("dont 1 effectuée", text)
        regles = open(os.path.join(self.d, "rules")).read()
        self.assertNotIn("11.126.46.49", regles)
        self.assertIn("11.68.110.86", regles)
        self.assertIn("leve\t11.126.46.49", open(os.path.join(self.env["NGINX_LOG_AUDIT_STATE_DIR"], "bans.tsv")).read())

    # --- interactif (vrai terminal, root requis pour la question) -------------------------------------------------------
    def _burst_aws(self):
        self.add(*(acc("11.22.62.38", "25/Sep/2026", f"19:28:5{i % 10}", f"/page{i}") for i in range(10)))
        self.add(acc("11.22.62.38", "25/Sep/2026", "19:30:00", "/x", 200, "python-httpx/0.28.1"))

    @unittest.skipUnless(os.geteuid() == 0, "la question de bannissement exige root")
    def test_ctrl_c_a_la_question_vaut_non_et_rapport_continue(self):
        """1.26 : Ctrl-C arrêtait tout le rapport (et bash 5.2 reprend un « read » après un piège INT)."""
        self._burst_aws()
        text, sent = self.run_pty(["bash", self.prog, "prod", "--init"], [(b"maintenant ? [o/N]", b"\x03", 0.3)])
        self.assertEqual(sent, 1)
        self.assertIn("Ctrl-C : non banni, le rapport continue", text)
        self.assertIn("RÉSUMÉ", text)
        self.assertFalse(os.path.exists(os.path.join(self.d, "rules")) and "11.22.62.38" in open(os.path.join(self.d, "rules")).read())

    @unittest.skipUnless(os.geteuid() == 0, "la question de bannissement exige root")
    def test_reponse_corrigee_avec_effacement_h_et_del(self):
        """1.32 : la touche d'effacement affichait « ^H » sans effacer (clients SSH qui envoient ^H) — readline."""
        for effacement in (b"\x08", b"\x7f"):
            with self.subTest(touche=effacement):
                if os.path.exists(os.path.join(self.d, "rules")):
                    os.remove(os.path.join(self.d, "rules"))
                for f in os.listdir(self.env["NGINX_LOG_AUDIT_STATE_DIR"]) if os.path.isdir(self.env["NGINX_LOG_AUDIT_STATE_DIR"]) else []:
                    os.remove(os.path.join(self.env["NGINX_LOG_AUDIT_STATE_DIR"], f))
                with open(self.access, "w"):
                    pass
                self._burst_aws()
                text, _ = self.run_pty(["bash", self.prog, "prod", "--init"],
                                       [(b"maintenant ? [o/N]", b"n" + effacement + b"o\n", 0.2), (b"> ", b"\n", 0.3)])
                self.assertIn("Règle iptables ajoutée", text, "réponse « n », effacée, puis « o » : doit bannir")

    @unittest.skipUnless(os.geteuid() == 0, "la question de bannissement exige root")
    def test_reponse_tapee_lentement_acceptee(self):
        """1.26 : « $? » après un « if » sans « else » valait 0 — une réponse tapée en plus d'1 s était ignorée."""
        self._burst_aws()
        text, _ = self.run_pty(["bash", self.prog, "prod", "--init"], [(b"maintenant ? [o/N]", b"o\n", 1.5), (b"> ", b"\n", 0.3)])
        self.assertIn("Règle iptables ajoutée", text)
        self.assertIn("11.22.62.38", open(os.path.join(self.d, "rules")).read())


    def refus(self, ip, jour, url, code=404, n=1):
        """Lignes du journal des REFUS de nginx (blocked-probes.log, format combined_host)."""
        return "".join(f'{ip} - - [{jour}:10:00:0{i} +0000] "GET {url} HTTP/1.1" {code} 146 "-" "zgrab/0.x" host="www.exemple.org"\n' for i in range(n))

    def test_preuves_de_bannissement_incluent_les_requetes_refusees(self):
        """2.22 : « Site : aucune requête » alors que fail2ban avait détecté 11 fois l'adresse : ce que fait bannir le jail
        nginx-blocked-probes est dans blocked-probes.log (nos règles de refus y écrivent À LA PLACE du journal du site), qui n'était
        lu nulle part. Les preuves listent maintenant les pages refusées."""
        ip = "11.29.164.196"
        with open(os.path.join(self.logs, "blocked-probes.log"), "w") as f:
            f.write(self.refus(ip, "02/Oct/2026", "/.env", n=3) + self.refus(ip, "02/Oct/2026", "/wp-admin/", n=2))
        with open(os.path.join(self.logs, "blocked-probes.log.1"), "w") as f:
            f.write(self.refus(ip, "30/Sep/2026", "/.git/config?x=1") + self.refus("45.33.32.156", "30/Sep/2026", "/autre", n=4))
        ancien = time.time() - 3 * 86400                                                      # une rotation est plus ancienne que le journal courant
        os.utime(os.path.join(self.logs, "blocked-probes.log.1"), (ancien, ancien))
        _, out, err = self.run_cmd(["bash", self.prog, "prod", "--ban", ip, "--no-prompt"], input_text="n\n")
        self.assertIn("Site : aucune requête (les requêtes REFUSÉES par nginx ne sont pas dans ces journaux : voir ci-dessous)", out)
        self.assertIn("Requêtes REFUSÉES par nginx : 6 requêtes (jours : 30/Sep/2026, 02/Oct/2026)", out)
        self.assertIn("c'est ce que voit le jail nginx-blocked-probes", out)
        self.assertRegex(out, r"\s+3  /\.env \(404\)\n")
        self.assertRegex(out, r"\s+2  /wp-admin/ \(404\)\n")
        self.assertRegex(out, r"\s+1  /\.git/config \(404\)\n")                         # parameters removed
        self.assertNotIn("/autre", out)                                                  # another address is not mixed in
        self.assertIn("+ 6 requêtes refusées par nginx (fichiers sensibles, failles, outils d'attaque), sur 2 jours", out)
        self.assertIn("Verdict : bannissement justifié", re.sub(r"\x1b\[[0-9;]*m", "", out))
        # No refused request kept: says it clearly, without inventing evidence
        for nom in ("blocked-probes.log", "blocked-probes.log.1"):
            os.remove(os.path.join(self.logs, nom))
        _, out, _ = self.run_cmd(["bash", self.prog, "prod", "--ban", ip, "--no-prompt"], input_text="n\n")
        self.assertIn("Requêtes refusées par nginx (blocked-probes.log) : aucune dans les journaux conservés", out)
        self.assertNotIn("Requêtes REFUSÉES par nginx", out)

    def test_lieu_partage_ou_protege_est_un_argument_contre_le_bannissement(self):
        """Une adresse d'un lieu [partagée] (université…) : « la bannir bloquerait toutes les personnes de ce lieu » (argument CONTRE, même
        avec des requêtes refusées) ; un lieu [protégée] : « IP protégée » comme la liste blanche, jamais proposée au bannissement."""
        ip = "11.105.216.7"
        with open(os.path.join(self.logs, "blocked-probes.log"), "w") as f:
            f.write(self.refus(ip, "02/Oct/2026", "/.env", n=3))
        self.lieux("11.105.0.0/16    # ETS - Université   [partagée]\n203.0.113.64/26   # Bureau   [protégée]\n")
        _, out, err = self.run_cmd(["bash", self.prog, "prod", "--ban", ip, "--no-prompt"], input_text="n\n")
        propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
        self.assertIn("Lieu (/etc/default/nginx-tools-ip-location.conf)", propre)
        self.assertIn("ETS - Université (plage 11.105.0.0/16) — options : partagee", propre)
        self.assertIn("adresse PARTAGÉE (ETS - Université) : la bannir bloquerait toutes les personnes de ce lieu", propre)
        self.assertIn("Requêtes REFUSÉES par nginx : 3 requêtes", propre)                               # both arguments are presented
        self.assertIn("Listes : liste blanche : aucun fichier ; lieux ", err)                            # fichiers lus, sur la sortie d'erreur
        # Protected place: treated like the white list (warning, investigation: protected IP)
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(f'203.0.113.70 - - [02/Oct/2026:10:00:{i:02d} -0400] "GET /.env HTTP/1.1" 404 300 "-" "python-requests/2"\n' for i in range(12))
        _, out, _ = self.run_cmd(["bash", self.prog, "--investigate", "203.0.113.70"])
        self.assertIn("IP protégée (lieu protégé : Bureau (plage 203.0.113.64/26))", out)
        # A place only [shared] is NOT "protected": the investigation continues
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(f'11.105.216.7 - - [02/Oct/2026:10:00:{i:02d} -0400] "GET /.env HTTP/1.1" 404 300 "-" "python-requests/2"\n' for i in range(12))
        _, out, _ = self.run_cmd(["bash", self.prog, "--investigate", "11.105.216.7"])
        self.assertNotIn("IP protégée", out)

    def test_recidiviste_indique_ce_que_l_adresse_a_demande(self):
        """2.22 : « récidiviste : 2 jours (…), jail nginx-blocked-probes — bannissements temporaires répétés » sans dire pourquoi : la
        raison cite maintenant les pages refusées par nginx (« a demandé : /.env (404) ×3, … »)."""
        ip = "11.89.160.73"
        with open(os.path.join(self.logs, "blocked-probes.log"), "w") as f:
            f.write(self.refus(ip, "25/Sep/2026", "/.env", n=3) + self.refus(ip, "25/Sep/2026", "/wp-admin/", n=2))
        with open(os.path.join(self.logs, "blocked-probes.log.1"), "w") as f:
            f.write(self.refus(ip, "18/Sep/2026", "/.env", n=2))
        with open(os.path.join(self.logs, "blocked-probes.log.2"), "w") as f:
            f.write(self.refus(ip, "15/Sep/2026", "/.git/config"))
        fichier = f"{self.logs}/blocked-probes.log"
        self.mock("fail2ban-client", f'case "$2" in "") echo \'`- Jail list:\tnginx-blocked-probes\';; '
                                     f'*) echo "|- Banned IP list:\t{ip}"; echo \'`- File list:\t{fichier}\';; esac')
        rc, out, err = self.report("--fail2ban")
        self.assertEqual(rc, 0, err)
        propre = re.sub(r"\x1b\[[0-9;]*m", "", out)
        self.assertRegex(propre, rf"▶ {re.escape(ip)} — 3 jours \(.*\), jail nginx-blocked-probes, a demandé : /\.env \(404\) ×5, /wp-admin/ \(404\) ×2, /\.git/config \(404\) ×1")

    def test_lecture_de_chaque_fichier_seulement_avec_details(self):
        """2.21 : les lignes « [ 5 s]   lecture de odoo-catchall-444.log.14.gz (30 Ko) » (une par fichier de rotation) ne s'affichent
        qu'avec --details ; les autres étapes (« Preuves pour… », « Section… ») restent visibles avec --verbose."""
        for nom, contenu in (("odoo-catchall-444.log", catchall("11.89.160.73", "25/Sep/2026")), ("odoo-catchall-444.log.1", catchall("11.89.160.73", "18/Sep/2026"))):
            with open(os.path.join(self.logs, nom), "w") as f:
                f.write(contenu)
        with gzip.open(os.path.join(self.logs, "odoo-catchall-444.log.2.gz"), "wt") as f:
            f.write(catchall("11.89.160.73", "15/Sep/2026"))
        self.add(acc("11.89.160.73", "25/Sep/2026", "10:00:00", "/event", 200, "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0"))
        ban = ["bash", self.prog, "prod", "--ban", "11.89.160.73", "--no-prompt", "--verbose"]       # the "evidence" precedes the confirmation
        _, out, err = self.run_cmd(ban, input_text="n\n")
        self.assertIn("Preuves pour 11.89.160.73 : journaux du capteur catch-all", err)
        self.assertNotIn("lecture de odoo-catchall-444.log", err, "« lecture de… » sans --details")
        _, out, err = self.run_cmd(ban + ["--details"], input_text="n\n")
        self.assertIn("Preuves pour 11.89.160.73 : journaux du capteur catch-all", err)
        for fichier in ("odoo-catchall-444.log ", "odoo-catchall-444.log.1 ", "odoo-catchall-444.log.2.gz "):
            self.assertRegex(err, r"\[\s*\d+ s\]   lecture de " + re.escape(fichier) + r"\(\d+ Ko\)")

    def test_enquete_affiche_le_fournisseur_d_acces(self):
        """2.19 : --investigate affiche le propriétaire du bloc d'adresses (RDAP via rdap.org, sinon whois) ; réseau, pays, adresse
        de signalement d'abus. Rapport ordinaire : aucune interrogation réseau."""
        rdap = {"name": "VL-Q-RES", "country": "CA", "port43": "whois.arin.net",
                "cidr0_cidrs": [{"v4prefix": "11.40.0.0", "length": 14}],
                "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                                                               ["fn", {}, "text", "Videotron Ltee"]]],
                              "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["email", {}, "text", "abuse@videotron.ca"]]]}]}]}
        import json
        self.write("rdap.json", json.dumps(rdap))
        self.mock("curl", f'echo "$@" >> {self.d}/curl.log; [[ "$*" == *rdap.org/ip/11.42.88.181* ]] && cat {self.d}/rdap.json || exit 22')
        self.add(acc("11.42.88.181", "01/Oct/2026", "23:02:14", "/event", 200, "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0"))
        _, out, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.42.88.181", "--no-prompt"])
        self.assertIn("Propriétaire du bloc d'adresses : Videotron Ltee (organisation ; pas forcément un fournisseur d'accès) — pays CA", out)
        self.assertIn("réseau VL-Q-RES (11.40.0.0/14) — source RDAP (whois.arin.net)", out)
        self.assertIn("signalement d'abus : abuse@videotron.ca", out)
        # --verbose est transmis au composant : ses commandes (curl) s'affichent
        _, out, err = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.42.88.181", "--no-prompt", "--verbose"])
        self.assertIn("+ curl -fsSL --max-time 10 -H Accept: application/rdap+json https://rdap.org/ip/11.42.88.181", out + err)
        self.assertIn("Propriétaire du bloc d'adresses : Videotron Ltee (organisation", out)
        # rdap.org injoignable, whois disponible
        self.mock_exit("curl", 22)
        self.mock("whois", 'printf "NetRange: 11.40.0.0 - 11.43.255.255\nNetName: VL-Q-RES\nOrgName: Videotron Ltee\nCountry: CA\nOrgAbuseEmail: abuse@videotron.ca\n"')
        _, out, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.42.88.181", "--no-prompt"])
        self.assertIn("Propriétaire du bloc d'adresses : Videotron Ltee (organisation ; pas forcément un fournisseur d'accès) — pays CA", out)
        self.assertIn("source whois", out)
        # Ni l'un ni l'autre
        self.mock_exit("whois", 1)
        _, out, _ = self.run_cmd(["bash", self.prog, "prod", "--investigate", "11.42.88.181", "--no-prompt"])
        self.assertIn("Propriétaire du bloc d'adresses : inconnu", out)
        # Ordinary report: nothing sent to rdap.org
        open(os.path.join(self.d, "curl.log"), "w").close()
        self.mock("curl", f'echo "$@" >> {self.d}/curl.log; exit 1')
        self.report()
        with open(os.path.join(self.d, "curl.log")) as f:
            self.assertNotIn("rdap.org", f.read())


if __name__ == "__main__":
    unittest.main()
