"""Configuration d'Odoo : détection du fichier (liste ODOO_CONF_PATHS), reconnaissance de l'application Odoo, ports lus dans la
configuration (pare-feu), journal en fichier (logfile). Bibliothèques apps/_odoo_conf.sh et apps/_odoo_conf.py, identiques."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs
import os
import re

from helpers import EnvTest, SCRIPTS_DIR

CONF = "[options]\nhttp_port = {http}\ngevent_port = {gevent}\n{extra}admin_passwd = x\n"


class ConfigurationOdoo(EnvTest):
    def setUp(self):
        super().setUp()
        self.racine = os.path.join(self.d, "racine-vide")
        os.makedirs(os.path.join(self.racine, "etc", "odoo"), exist_ok=True)
        self.apps = os.path.join(SCRIPTS_DIR, "apps")
        self.env["APP_DETECT_ROOT"] = self.racine
        self.env.pop("ODOO_CONF_PATHS", None)
        self.env.pop("APP_PROFILE", None)                              # real detection

    def conf(self, chemin, http=8069, gevent=8072, extra=""):
        complet = os.path.join(self.racine, chemin.lstrip("/"))
        os.makedirs(os.path.dirname(complet), exist_ok=True)
        with open(complet, "w") as f:
            f.write(CONF.format(http=http, gevent=gevent, extra=extra))
        return complet

    def bash(self, code):
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{self.apps}/_odoo_conf.sh"; {code}'])
        return out.strip()

    def python(self, code):
        rc, out, err = self.run_cmd(["python3", "-c", f'import sys; sys.path.insert(0, "{self.apps}"); import _odoo_conf as c\n{code}'])
        return out.strip()

    def test_chemin_cite_par_l_utilisateur_en_premier(self):
        meetup = self.conf("/etc/odoo/odoo-linux_meetup.conf", 8070, 8073)
        self.conf("/etc/odoo/odoo.conf")
        self.assertEqual(self.bash("odoo_conf_trouver"), meetup)
        self.assertEqual(self.python("print(c.trouver())"), meetup)

    def test_motif_et_liste_personnalisee(self):
        autre = self.conf("/srv/odoo/mon.conf")
        self.conf("/etc/odoo/odoo-linux_meetup.conf")
        self.env["ODOO_CONF_PATHS"] = "/srv/odoo/*.conf"
        self.assertEqual(self.bash("odoo_conf_trouver"), autre)
        self.assertEqual(self.python("print(c.trouver())"), autre)

    def test_liste_dans_le_fichier_de_configuration_du_programme(self):
        autre = self.conf("/srv/odoo/mon.conf")
        dossier = self.env["NGINX_TOOLS_ETC_DEFAULT"]
        os.makedirs(dossier, exist_ok=True)
        with open(os.path.join(dossier, "nginx-hardening.conf"), "w") as f:
            f.write('ODOO_CONF_PATHS="/srv/odoo/mon.conf"   # liste\n')
        self.assertEqual(self.bash("odoo_conf_trouver"), autre)
        self.assertEqual(self.python("print(c.trouver())"), autre)

    def test_fichier_qui_n_est_pas_une_configuration_odoo_ignore(self):
        chemin = os.path.join(self.racine, "etc", "odoo", "autre.conf")
        with open(chemin, "w") as f:
            f.write("rien = a voir\n")
        self.assertEqual(self.bash("odoo_conf_trouver || echo AUCUN"), "AUCUN")
        self.assertEqual(self.python("print(c.trouver())"), "None")

    def test_ports_et_journal_lus_avec_alias_et_valeurs_par_defaut(self):
        f = self.conf("/etc/odoo/odoo.conf", 10000, 10002, extra="logfile = /var/log/odoo/odoo.log\nhttp_interface = 127.0.0.1\n")
        self.assertEqual(self.bash(f'odoo_conf_charger "{f}"; echo $ODOO_CONF_HTTP_PORT $ODOO_CONF_GEVENT_PORT $ODOO_CONF_LOGFILE $ODOO_CONF_INTERFACE'),
                         "10000 10002 /var/log/odoo/odoo.log 127.0.0.1")
        lu = self.python(f'r = c.lire("{f}"); print(r["http_port"], r["gevent_port"], r["logfile"], r["interface"])')
        self.assertEqual(lu, "10000 10002 /var/log/odoo/odoo.log 127.0.0.1")
        ancien = os.path.join(self.d, "ancien.conf")
        with open(ancien, "w") as fh:
            fh.write("[options]\nxmlrpc_port = 8000\nlongpolling_port = 8001\nlogfile = False\n")
        self.assertEqual(self.bash(f'odoo_conf_charger "{ancien}"; echo "$ODOO_CONF_HTTP_PORT $ODOO_CONF_GEVENT_PORT [$ODOO_CONF_LOGFILE]"'), "8000 8001 []")
        self.assertEqual(self.python(f'r = c.lire("{ancien}"); print(r["http_port"], r["gevent_port"], "[" + r["logfile"] + "]")'), "8000 8001 []")
        vide = os.path.join(self.d, "vide.conf")
        with open(vide, "w") as fh:
            fh.write("[options]\n")
        self.assertEqual(self.bash(f'odoo_conf_charger "{vide}"; echo $ODOO_CONF_HTTP_PORT $ODOO_CONF_GEVENT_PORT'), "8069 8072")

    def test_service_deduit_de_db_user_et_du_nom_du_fichier(self):
        f = self.conf("/etc/odoo/odoo-linux_meetup.conf", extra="db_user = odoo-linux_meetup\n")
        self.assertEqual(self.bash(f'odoo_conf_charger "{f}"; echo $ODOO_CONF_DB_USER "$ODOO_CONF_UNITES"'),
                         "odoo-linux_meetup odoo-linux_meetup.service")
        g = self.conf("/etc/odoo/autre.conf", extra="db_user = odoo-x\n")
        self.assertEqual(self.bash(f'odoo_conf_charger "{g}"; echo "$ODOO_CONF_UNITES"'), "odoo-x.service autre.service")
        self.assertEqual(self.python(f'print(c.lire("{g}")["unites"])'), "['odoo-x.service', 'autre.service']")

    def test_application_odoo_reconnue_par_sa_configuration(self):
        """Aucune unité systemd, aucun fichier de profil : la seule configuration d'Odoo suffit (bash et Python identiques)."""
        self.mock("systemctl", "exit 1")
        f = self.conf("/etc/odoo/odoo-linux_meetup.conf", 8069, 8072, extra="logfile = /var/log/odoo/odoo.log\n")
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{self.apps}/_profile.sh"; charger_profil_app "{self.apps}" && echo "$APP_NAME|$APP_DETECTION|$ODOO_CONF_HTTP_PORT|$ODOO_CONF_LOGFILE"'])
        self.assertEqual(out.strip(), f"odoo|détectée automatiquement ; configuration d'Odoo : {f}|8069|/var/log/odoo/odoo.log")
        rc, out, err = self.run_cmd(["python3", "-c", f'import sys; sys.path.insert(0, "{self.apps}"); import _profile as p; r = p.charger_profil_app("{self.apps}")\n'
                                     'print(r["APP_NAME"], r["ODOO_CONF"], r["ODOO_HTTP_PORT"], r["ODOO_LOGFILE"])'])
        self.assertEqual(out.strip(), f"odoo {f} 8069 /var/log/odoo/odoo.log")

    def test_sans_configuration_ni_unite_aucune_application(self):
        self.mock("systemctl", "exit 1")
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{self.apps}/_profile.sh"; charger_profil_app "{self.apps}"'])
        self.assertIn("aucune application reconnue", err)


class PareFeuSelonLaConfiguration(EnvTest):
    """nginx-hardening.sh : ports du pare-feu lus dans la configuration d'Odoo."""
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("nginx-hardening.sh", {"/var/www": os.path.dirname(self.path("var-www", "x")),
                                                       "/var/log/nginx": os.path.dirname(self.path("var-log-nginx", "x"))})
        self.env["APP_DETECT_ROOT"] = ""                               # absolute ODOO_CONF_PATHS paths, not prefixed
        self.mock("systemctl", 'exit 1')
        self.mock("ss", "exit 0")
        self.mock("ufw", f'[[ "$1" == status ]] && exit 0; echo "$@" >> {self.d}/ufw.log; exit 0')

    def lancer(self, *args):
        rc, out, err = self.run_cmd(["bash", self.prog, *args])
        self.assertNotIn("ARRÊT INATTENDU", err, err)
        return out

    def test_ports_de_la_configuration_visent_le_pare_feu(self):
        f = self.path("meetup.conf")
        with open(f, "w") as fh:
            fh.write(CONF.format(http=8169, gevent=8172, extra="proxy_mode = True\n"))
        self.env["ODOO_CONF_PATHS"] = f
        out = self.lancer("--app", "odoo")
        self.assertIn(f"Configuration d'Odoo : {f}", out)
        self.assertIn("Ports : HTTP 8169, gevent 8172", out)
        self.assertRegex(out, r"ufw : aucune règle DENY pour le port 8169/tcp")
        self.assertRegex(out, r"ufw : aucune règle DENY pour le port 8172/tcp")
        self.assertIn("Journal d'Odoo : journal systemd", out)
        self.assertNotRegex(out, r"port 10000/tcp")

    def test_option_explicite_l_emporte_sur_la_configuration(self):
        f = self.path("meetup.conf")
        with open(f, "w") as fh:
            fh.write(CONF.format(http=8169, gevent=8172, extra=""))
        self.env["ODOO_CONF_PATHS"] = f
        out = self.lancer("--app", "odoo", "--odoo-http-port", "9000")
        self.assertIn("Ports : HTTP 9000, gevent 8172", out)

    def test_sans_configuration_ports_historiques(self):
        self.env["ODOO_CONF_PATHS"] = self.path("introuvable.conf")
        out = self.lancer("--app", "odoo")
        self.assertRegex(out, r"ufw : aucune règle DENY pour le port 10000/tcp")
        self.assertNotIn("Configuration d'Odoo :", out)

    def test_journal_en_fichier_et_rotation(self):
        journal = self.path("odoo.log")
        open(journal, "w").close()
        f = self.path("meetup.conf")
        with open(f, "w") as fh:
            fh.write(CONF.format(http=8169, gevent=8172, extra=f"logfile = {journal}\n"))
        self.env["ODOO_CONF_PATHS"] = f
        out = self.lancer("--app", "odoo")
        self.assertIn(f"Journal d'Odoo : fichier {journal}", out)
        self.assertIn("11b)", out)
        self.assertRegex(out, r"Aucune règle logrotate ne mentionne")
        self.assertTrue(re.search(r"--- 11b\)", out))


class ServiceEtProgrammes(PareFeuSelonLaConfiguration):
    """nginx-hardening.sh : service d'après db_user ; installation des programmes qui manquent."""
    def test_service_odoo_trouve_par_db_user(self):
        f = self.path("meetup.conf")
        with open(f, "w") as fh:
            fh.write(CONF.format(http=8169, gevent=8172, extra="db_user = odoo-linux_meetup\n"))
        self.env["ODOO_CONF_PATHS"] = f
        self.mock("systemctl", '[[ "$1" == list-unit-files && "$2" == odoo-linux_meetup.service ]] && { echo "odoo-linux_meetup.service enabled"; exit 0; }; exit 1')
        out = self.lancer("--app", "odoo")
        self.assertNotIn("Aucun service Odoo connu", out)
        self.assertNotIn("Odoo service not determined", out)
        self.assertNotIn("Service Odoo non déterminé", out)

    def test_programme_manquant_installe_par_update_seulement(self):
        script = open(self.prog, encoding="utf-8").read()
        debut = script.index("paquet_installer() {")
        fonction = script[debut:script.index("\n}\n", debut) + 2]
        self.mock("apt-get", f'echo "$@" >> {self.d}/apt.log; printf "#!/bin/bash\\nexit 0\\n" > {self.bin}/outil-test-absent; chmod +x {self.bin}/outil-test-absent')
        base = ('pass() { echo "PASS $1"; }; warn() { echo "WARN $1"; }; fail() { echo "FAIL $1"; }; run() { "$@"; }; '
                f'{fonction}; CHECK_ONLY=@C@; paquet_installer outil-test-absent paquet-test')
        rc, out, err = self.run_cmd(["bash", "-c", base.replace("@C@", "1")])
        self.assertIn("WARN outil-test-absent absent (paquet paquet-test) — relancer avec --update", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "apt.log")))
        rc, out, err = self.run_cmd(["bash", "-c", base.replace("@C@", "0")])
        self.assertIn("PASS outil-test-absent installé (paquet paquet-test)", out)
        self.assertIn("install -y paquet-test", open(os.path.join(self.d, "apt.log")).read())


class MiseEnPlace(PareFeuSelonLaConfiguration):
    """nginx-hardening.sh --update : fuseau horaire, dossier de cache nginx, rotation du journal d'Odoo, sortie entièrement anglaise."""
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("nginx-hardening.sh", {"/var/www": os.path.dirname(self.path("var-www", "x")),
                                                       "/var/log/nginx": os.path.dirname(self.path("var-log-nginx", "x")),
                                                       "/etc/nginx": os.path.dirname(self.path("etc-nginx", "x")),
                                                       "/etc/logrotate.d": os.path.dirname(self.path("logrotate-d", "x")),
                                                       "/var/cache/nginx": os.path.dirname(self.path("cache-nginx", "x"))})
        self.etc_nginx, self.logrotate, self.cache = self.path("etc-nginx"), self.path("logrotate-d"), self.path("cache-nginx")
        self.zoneinfo = self.path("zoneinfo")
        os.makedirs(os.path.join(self.zoneinfo, "America"), exist_ok=True)
        for zone in ("Montreal", "Toronto"):
            open(os.path.join(self.zoneinfo, "America", zone), "w").close()
        self.env["NGINX_HARDENING_ZONEINFO"] = self.zoneinfo
        self.env["NGINX_TOOLS_ETC_DEFAULT"] = self.path("etc-default")
        os.makedirs(self.env["NGINX_TOOLS_ETC_DEFAULT"], exist_ok=True)
        self.mock("timedatectl", f'if [[ "$1" == show ]]; then cat {self.d}/tz 2>/dev/null || echo UTC; else echo "$@" >> {self.d}/timedatectl.log; echo "$2" > {self.d}/tz; fi')
        self.mock("nginx", "exit 0")
        self.mock("logrotate", "exit 0")
        self.mock("install", 'for a in "$@"; do last="$a"; done; /usr/bin/install -d "$last"')
        os.makedirs(self.etc_nginx, exist_ok=True)
        with open(os.path.join(self.etc_nginx, "odoo-global.conf"), "w") as f:
            f.write(f"proxy_cache_path {self.cache}/odoo levels=1:2 keys_zone=odoo_cache:10m;\n")
        self.journal = self.path("odoo.log")
        open(self.journal, "w").close()
        self.conf_odoo = self.path("meetup.conf")
        with open(self.conf_odoo, "w") as fh:
            fh.write(CONF.format(http=8169, gevent=8172, extra=f"logfile = {self.journal}\n"))
        self.env["ODOO_CONF_PATHS"] = self.conf_odoo

    def mise_a_jour(self, *args):
        return self.lancer("--app", "odoo", "--update", *args)

    def test_fuseau_horaire_verifie_puis_regle_par_update(self):
        out = self.lancer("--app", "odoo")
        self.assertIn("Fuseau horaire : UTC (souhaité : America/Montreal) — relancer avec --update", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "timedatectl.log")))
        out = self.mise_a_jour()                                     # without a terminal: the default is applied
        self.assertIn("Fuseau horaire réglé à America/Montreal (avant : UTC)", out)
        self.assertIn("set-timezone America/Montreal", open(os.path.join(self.d, "timedatectl.log")).read())
        self.assertIn("TIMEZONE=America/Montreal", open(os.path.join(self.env["NGINX_TOOLS_ETC_DEFAULT"], "nginx-hardening.conf")).read())
        out = self.lancer("--app", "odoo")
        self.assertIn("Fuseau horaire : America/Montreal.", out)

    def test_fuseau_horaire_none_ne_change_rien(self):
        out = self.mise_a_jour("--timezone", "none")
        self.assertIn("fuseau horaire laissé tel quel", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "timedatectl.log")))

    def test_dossier_de_cache_nginx_cree(self):
        cible = os.path.join(self.cache, "odoo")
        out = self.lancer("--app", "odoo")
        self.assertIn(f"{cible} n'existe pas : nginx -t refuse la configuration", out)
        self.assertFalse(os.path.exists(cible))
        out = self.mise_a_jour()
        self.assertIn(f"{cible} créé", out)
        self.assertTrue(os.path.isdir(cible))

    def test_rotation_du_journal_d_odoo_creee(self):
        regle = os.path.join(self.logrotate, "odoo")
        out = self.lancer("--app", "odoo")
        self.assertIn("il grossira sans fin — --update crée", out)
        self.assertFalse(os.path.exists(regle))
        out = self.mise_a_jour()
        self.assertTrue(os.path.isfile(regle), out)
        contenu = open(regle).read()
        self.assertIn(f"{self.journal} {{", contenu)
        for mot in ("weekly", "rotate 13", "compress", "copytruncate", "missingok", "notifempty"):
            self.assertIn(mot, contenu)
        self.assertIn("tourné chaque semaine", out)
        # An "odoo" file already exists with other content: never overwritten
        os.remove(regle)
        with open(regle, "w") as f:
            f.write("/autre/journal {\n}\n")
        self.mise_a_jour()
        self.assertEqual(open(regle).read(), "/autre/journal {\n}\n")
        self.assertIn(self.journal, open(os.path.join(self.logrotate, "odoo-nginx-hardening")).read())

    def test_sortie_anglaise_sans_francais(self):
        out = self.mise_a_jour("--lang", "en")
        restes = [l for l in out.splitlines() if re.search(r"[éèàêôçù]", l) and self.d not in l]      # (titles containing a test path: other catalog keys)
        self.assertEqual(restes, [], "lignes restées en français avec --lang en")

    def test_page_de_maintenance_copiee_depuis_la_configuration_nginx_deployee(self):
        source = os.path.join(self.etc_nginx, "maintenance")
        os.makedirs(source, exist_ok=True)
        with open(os.path.join(source, "index.html"), "w") as f:
            f.write("<html>maintenance</html>")
        out = self.mise_a_jour()
        self.assertRegex(out, r"index\.html installé depuis .*etc-nginx/maintenance/index\.html")

    def test_iptables_persistent_installe_quand_les_regles_ne_sont_pas_enregistrees(self):
        os.remove(os.path.join(self.bin, "ufw"))
        self.mock("iptables", f'case "$1" in -C) exit 1;; *) echo "$@" >> {self.d}/iptables.log;; esac')
        self.mock("apt-get", f'echo "$@" >> {self.d}/apt.log; printf "#!/bin/bash\\\\nexit 0\\\\n" > {self.bin}/netfilter-persistent; chmod +x {self.bin}/netfilter-persistent')
        out = self.mise_a_jour()
        self.assertRegex(out, r"iptables : règles enregistrées \(netfilter-persistent\)|iptables-persistent installé et règles enregistrées")
        self.assertNotIn("mémoire seulement", out)
