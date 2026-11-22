"""odoo-update-module.sh : mise à jour des modules rlq_* puis redémarrage d'Odoo par systemd (systemctl, runuser, pgrep, ss simulés ; Odoo simulé)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"
import datetime
import getpass
import os
import re
import shutil
import tarfile
import unittest
import zipfile

from helpers import EnvTest

FAUX_SYSTEMCTL = r'''
echo "systemctl $*" >> "$D/appels.log"
case "$1" in
  list-units) cat "$D/unites" 2>/dev/null; exit 0 ;;
  show) shift; nom="${2:-}"; [ "$1" = "-p" ] && nom="$2"; cat "$D/prop.$nom" 2>/dev/null; exit 0 ;;
  is-active) cat "$D/etat" 2>/dev/null || echo inactive; [ "$(cat "$D/etat" 2>/dev/null)" = active ] ;;
  stop) echo inactive > "$D/etat" ;;
  start) [ -e "$D/demarrage_impossible" ] && exit 1; echo active > "$D/etat" ;;
esac
'''

FAUX_ODOO = r'''#!/bin/bash
echo "odoo $*" >> "$D/appels.log"
[ "$1" = shell ] && cat > "$D/odoo_stdin"
if [ -n "${RLQ_REMOVE:-}" ]; then echo "retrait=$RLQ_REMOVE" >> "$D/appels.log"; printf 'RLQ_REMOVED\t%s\t%s\n' "$(echo $RLQ_REMOVE | wc -w)" "$RLQ_REMOVE"; exit 0; fi
echo "etat_service=$(cat "$D/etat")" >> "$D/appels.log"
pwd >> "$D/appels.log"
[ -e "$D/odoo_sortie" ] && cat "$D/odoo_sortie"
[ -e "$D/odoo_duree" ] && sleep "$(cat "$D/odoo_duree")"
exit "$(cat "$D/odoo_code" 2>/dev/null || echo 0)"
'''


class OdooUpdateModule(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("odoo-update-module.sh")
        self.odoo = os.path.dirname(self.path("odoo", "x"))
        for mod in ("rlq_survey_report", "rlq_autre"):
            self.write(f"odoo/custom/{mod}/__manifest__.py", "{}\n")
        self.write("odoo/custom/autre_module/__manifest__.py", "{}\n")
        self.write("odoo/custom/rlq_sans_manifeste/readme", "x\n")
        self.conf = self.write("odoo/config.conf", "[options]\naddons_path = addons,custom\nhttp_port = 10000\ndb_name = False\n")
        self.write("odoo/odoo_bin.sh", FAUX_ODOO, 0o755)
        self.log = os.path.join(self.d, "appels.log")
        self.write("etat", "active\n")
        self.write("prop.LoadState", "loaded\n")
        self.write("prop.User", getpass.getuser() + "\n")
        self.write("prop.WorkingDirectory", self.odoo + "\n")
        self.write("prop.ExecStart", "{ path=/x/run.sh ; argv[]=/x/run.sh -d base_prod ; ignore_errors=no ; start_time=[n/a] }\n")
        self.mock("systemctl", FAUX_SYSTEMCTL)
        self.mock("pgrep", 'cat "$D/pgrep" 2>/dev/null; exit 0')
        self.mock("ss", 'echo "LISTEN 0 128 *:10000 *:*"')
        self.mock("curl", 'echo "curl $*" >> "$D/appels.log"; printf 200')       # 1.33: first HTTP answer of Odoo after the start
        self.mock("sleep", "exit 0") if False else None
        self.mock("journalctl", 'echo "journalctl $*" >> "$D/appels.log"; cat "$D/journal_service" 2>/dev/null; exit 0')
        self.write("nginx/exemple-access.log", "")                         # 1.15: a readable nginx log without requests: the site is calm
        self.env.update(D=self.d, ODOO_UPDATE_MODULE_LOG_DIR=os.path.join(self.d, "journaux"), NGINX_TOOLS_ETC_DEFAULT=os.path.join(self.d, "etc"),
                        NGINX_TOOLS_CONFIG_CREER="0", TMPDIR=self.d, ODOO_UPDATE_MODULE_BACKUP_DIR=os.path.join(self.d, "copies"),
                        ODOO_UPDATE_MODULE_NGINX_DIR=os.path.join(self.d, "nginx"), ODOO_UPDATE_MODULE_QUIET_POLL="0", ODOO_UPDATE_MODULE_SETTLE="0",
                        ODOO_UPDATE_MODULE_PG_AS=self.write("pg-ok.sh", "#!/bin/bash\necho 0\n", 0o755), ODOO_UPDATE_MODULE_SAMPLE="0")

    def lancer(self, *args, **env):
        return self.run_cmd(["bash", self.prog, "--lang", "fr", *args], env_extra=env or None)

    def appels(self):
        return open(self.log, encoding="utf-8").read().splitlines() if os.path.exists(self.log) else []

    # --- 1.15: activity guard (writes in nginx and in PostgreSQL), replayed on the anonymized log of a real test (fixtures/) ----------------------

    def _journal_exemple(self):
        """Puts the nginx access log of the recorded test (fixtures/app-log-live-record-exemple-tests-en-dev.tar.xz) in the nginx folder of the test."""
        fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "app-log-live-record-exemple-tests-en-dev.tar.xz")
        with tarfile.open(fixtures) as t:
            t.extractall(self.d)
        source = os.path.join(self.d, "app-log-live-record-exemple-tests-en-dev", "raw", "exemple_dev-access.log")
        shutil.copy(source, os.path.join(self.d, "nginx", "exemple_dev-access.log"))

    @staticmethod
    def _epoch(stamp):
        """UTC epoch of a « YYYY-MM-DD HH:MM:SS UTC » text (the test recording was made at 12:xx EDT = 16:xx UTC)."""
        return str(int(datetime.datetime.strptime(stamp.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()))

    def test_199_activite_refuse_pendant_les_ecritures_et_accepte_apres(self):
        self._journal_exemple()
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=self._epoch("2026-10-22 16:09:00 UTC"))     # 12:09 EDT : soumissions de sondage
        self.assertEqual(rc, 3, out + err)
        self.assertIn("écritures HTTP", out)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=self._epoch("2026-10-22 16:23:00 UTC"))     # 12:23 EDT: last write at 12:17
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site calme", out)

    def test_199_attente_annulee_meme_avec_force_busy_si_ecriture(self):
        self._journal_exemple()
        occupe = self._epoch("2026-10-22 16:09:00 UTC")
        rc, out, err = self.lancer("--wait-quiet", "0", ODOO_UPDATE_MODULE_NOW=occupe)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("ANNULÉE", out)
        self.assertNotIn("systemctl stop erplibre_erplibre.service", self.appels())          # nothing was stopped
        rc, out, err = self.lancer("--wait-quiet", "0", "--force-busy", ODOO_UPDATE_MODULE_NOW=occupe)     # 1.17: une ECRITURE bloque toujours
        self.assertEqual(rc, 3, out + err)
        self.assertNotIn("systemctl stop erplibre_erplibre.service", self.appels())

    def _journal_post(self, *adresses, ip="198.51.100.20"):
        """1.26: a nginx log of POST requests at 19:00:00 UTC on 2026-11-09 (one line per address); returns the epoch of 19:01:00 UTC."""
        lignes = [f'{ip} - - [09/Nov/2026:19:00:00 +0000] "POST {a} HTTP/1.1" 200 12 "-" "Mozilla/5.0"' for a in adresses]
        self.write("nginx/exemple-access.log", "\n".join(lignes) + "\n")
        return self._epoch("2026-11-09 19:01:00 UTC")

    def test_226_bus_et_discussion_ne_bloquent_pas(self):
        """1.26 : POST /bus/has_missed_notifications (sondage du bus) n'est pas une écriture : le site reste calme.
        1.39 : la discussion (écriture légère) retarde la mise à jour, et elle est annulée si elle continue ; LIGHT_WRITES_WAIT=no : simple note."""
        maintenant = self._journal_post("/bus/has_missed_notifications", "/websocket", "/bus/im_status")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 0, out + err)
        maintenant = self._journal_post("/im_livechat/get_session", "/mail/message/post", "/discuss/channel/notify_typing")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)                     # 1.39: LIGHT_WRITES_WAIT=yes (default): the chat delays the update
        self.assertIn("écritures légères", out)
        self.assertNotIn("écritures HTTP (POST", out)
        rc, out, err = self.lancer("--wait-quiet", "0", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("ANNULÉE", out)                           # still busy at the end of the wait: cancelled, nothing stopped
        self.write("etc/odoo-update-module.conf", "LIGHT_WRITES_WAIT=no\n")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 0, out + err)                     # 1.32: LIGHT_WRITES_WAIT=no: a note only
        rc, out, err = self.lancer("--wait-quiet", "0", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertNotIn("ANNULÉE", out, out + err)
        self.assertIn("site calme", out)

    def test_139_utilisateur_connecte_qui_lit_n_est_jamais_coupe(self):
        """1.39 (option A) : un membre connecté qui navigue (GET, POST de lecture) retarde la mise à jour ; à la fin de l'attente elle est
        ANNULÉE, rien n'est arrêté. Un visiteur anonyme qui lit ne la retarde pas."""
        self.journal_nginx(["198.51.100.7"])
        self.env["ODOO_UPDATE_MODULE_PG_AS"] = self.pg_connectes(["198.51.100.7"])
        rc, out, err = self.lancer("--check-activity")
        self.assertEqual(rc, 3, out + err)
        self.assertIn("1 visiteurs actifs (connectés à Odoo ou en écriture)", out)
        self.assertIn("leur session n'est pas coupée", out)
        rc, out, err = self.lancer("--wait-quiet", "0")
        self.assertEqual(rc, 3, out + err)
        self.assertIn("ANNULÉE", out)
        self.assertNotIn("systemctl stop erplibre_erplibre.service", self.appels())
        self.journal_nginx(["198.51.100.8"])                   # anonymous visitor only: not waited for
        self.env["ODOO_UPDATE_MODULE_PG_AS"] = self.pg_connectes([])
        rc, out, err = self.lancer("--check-activity")
        self.assertEqual(rc, 0, out + err)

    def test_226_vraie_ecriture_bloque_toujours_et_light_writes(self):
        maintenant = self._journal_post("/survey/submit/abc/def", "/bus/has_missed_notifications")
        rc, out, err = self.lancer("--wait-quiet", "0", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("ANNULÉE", out)
        self.assertIn("/survey/submit", out)
        self.write("etc/odoo-update-module.conf", "LIGHT_WRITES=survey/submit/\\S*\nLIGHT_WRITES_WAIT=yes\n")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertIn("écritures légères", out, out + err)
        self.write("etc/odoo-update-module.conf", "LIGHT_WRITES=survey/(\n")          # invalid expression: ignored, the write still blocks
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("écritures HTTP (POST", out)

    def test_229_lectures_post_ignorees(self):
        """1.29 : cas réel des 2026-11-13 et 2026-11-14 : /website_mail/is_follower (robots), /xmlrpc/2/db (sonde), /web/login et
        call_kw/.../has_access annulaient la mise à jour. Ce sont des lectures : site calme ; une vraie écriture bloque toujours."""
        lectures = ("/website_mail/is_follower", "/xmlrpc/2/db", "/xmlrpc/2/common", "/web/login", "/html_editor/get_ice_servers",
                    "/web/dataset/call_kw/project.project/has_access", "/web/dataset/call_kw/res.partner/name_search")
        maintenant = self._journal_post(*lectures)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site calme", out)
        maintenant = self._journal_post("/html_editor/bus_broadcast", *lectures)          # collaborative editor: a light write
        self.write("etc/odoo-update-module.conf", "LIGHT_WRITES_WAIT=yes\n")                # 1.32: light writes delay the update only with this key
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("écritures légères", out)
        self.assertNotIn("écritures HTTP (POST", out)
        self.assertIn(f"{len(lectures)} requêtes POST en lecture seule ignorées", out)
        for ecriture in ("/web/dataset/call_kw/res.partner/web_save", "/web/dataset/call_kw/res.partner/unlink", "/xmlrpc/2/object",
                         "/web/dataset/call_kw/project.task/action_done"):
            maintenant = self._journal_post(ecriture, *lectures)
            rc, out, err = self.lancer("--wait-quiet", "0", ODOO_UPDATE_MODULE_NOW=maintenant)
            self.assertEqual(rc, 3, ecriture + out + err)
            self.assertIn("ANNULÉE", out, ecriture)

    def test_232_ecriture_terminee_formulaire_en_cours_et_administration(self):
        """1.32 : cas réel du 2026-11-17 (comptoir d'inscription) : un web_save terminé depuis plus de WRITE_GRACE s ne bloque plus ; un onchange
        après lui (formulaire en cours de modification) bloque ; load_breadcrumbs, init_barcode_interface et ir.config_parameter/get_* sont des
        lectures ; une adresse de l'administration est un utilisateur connecté ; WRITE_GRACE=0 : comme avant."""
        def journal(*lignes):
            self.write("nginx/exemple-access.log", "\n".join(f'96.21.220.4 - - [09/Nov/2026:19:00:{s:02d} +0000] "POST {a} HTTP/1.1" 200 12 "-" "Mozilla/5.0"'
                                                             for s, a in lignes) + "\n")
        maintenant = self._epoch("2026-11-09 19:02:00 UTC")
        lectures = [(1, "/web/action/load_breadcrumbs"), (2, "/event/init_barcode_interface"),
                    (3, "/web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config")]
        journal(*lectures)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 0, out + err)
        journal((10, "/web/dataset/call_kw/rlq.registration.desk/onchange"), (20, "/web/dataset/call_kw/rlq.registration.desk/web_save"), *lectures)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 0, out + err)                     # saved 100 s ago, no form opened after
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=self._epoch("2026-11-09 19:00:50 UTC"))
        self.assertEqual(rc, 3, out + err)                     # saved 30 s ago: still blocks
        self.assertIn("écritures HTTP (POST", out)
        journal((10, "/web/dataset/call_kw/rlq.registration.desk/web_save"), (30, "/web/dataset/call_kw/rlq.volunteer.coordinator/onchange"))
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("formulaire(s) en cours de modification", out)
        self.assertIn("rlq.volunteer.coordinator", out)
        self.assertIn("écritures terminées depuis plus de 60 s", out)
        self.assertIn("utilisateur connecté (compte non identifié)", out)
        self.assertNotIn("visiteur non connecté", out)
        journal((10, "/web/dataset/call_kw/rlq.registration.desk/web_save"))
        self.write("etc/odoo-update-module.conf", "WRITE_GRACE=0\n")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("écritures HTTP (POST", out)
        journal((10, "/survey/submit/a/b"))                    # a write of the public site keeps the 5-minute window
        self.write("etc/odoo-update-module.conf", "")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)

    def test_229_read_requests(self):
        """1.29 : READ_REQUESTS ajoute des lectures ; une expression invalide est ignorée (l'écriture bloque toujours)."""
        maintenant = self._journal_post("/my_module/status")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.write("etc/odoo-update-module.conf", "READ_REQUESTS=my_module/status\n")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 0, out + err)
        self.write("etc/odoo-update-module.conf", "READ_REQUESTS=my_module/(\n")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("écritures HTTP (POST", out)

    def test_227_qui_on_attend(self):
        """1.27 : la mise à jour dit qui elle attend : adresse, pays, utilisateur d'Odoo (res_device_log) et nombre de requêtes ; puis les utilisateurs
        connectés à Odoo depuis une autre adresse."""
        lignes = [f'198.51.100.20 - - [09/Nov/2026:19:00:{s:02d} +0000] "GET /web HTTP/1.1" 200 12 "-" "Mozilla/5.0"' for s in range(3)]
        lignes += ['203.0.113.7 - - [09/Nov/2026:19:00:30 +0000] "POST /survey/submit/a/b HTTP/1.1" 200 12 "-" "Mozilla/5.0"']
        self.write("nginx/exemple-access.log", "\n".join(lignes) + "\n")
        maintenant = self._epoch("2026-11-09 19:01:00 UTC")
        pg = self.write("pg-who.sh", "#!/bin/bash\ncase \"$*\" in\n*res_device_log*) printf '198.51.100.20|benevole1|Bénévole Un|Canada|1762714800\\n192.0.2.9|admin|Administrateur|France|1762714700\\n' ;;\n"
                                   "*) echo 0 ;;\nesac\n", 0o755)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=maintenant, ODOO_UPDATE_MODULE_PG_AS=pg)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("en attente de :", out)
        self.assertRegex(out, r"198\.51\.100\.20 \S.* · benevole1 \(Bénévole Un\) · 3 requêtes")
        self.assertRegex(out, r"203\.0\.113\.7 .* · visiteur non connecté · 1 requêtes, dernière à \d\d:\d\d:\d\d, 1 POST")
        self.assertIn("admin (Administrateur) · connecté à Odoo", out)
        self.assertIn("(203.0.113.7)", out)                     # the write shows its address
        self.assertNotIn("I|", out)
        self.assertNotIn("W|", out)

    def test_199_base_illisible_compte_comme_occupee(self):
        mauvais = self.write("pg-ko.sh", "#!/bin/bash\nexit 1\n", 0o755)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_PG_AS=mauvais)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("base PostgreSQL illisible", out)

    def test_succes_arret_mise_a_jour_puis_demarrage(self):
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        a = self.appels()
        i_stop = a.index("systemctl stop erplibre_erplibre.service")
        i_odoo = next(i for i, l in enumerate(a) if l.startswith("odoo "))
        i_start = a.index("systemctl start erplibre_erplibre.service")
        self.assertLess(i_stop, i_odoo)
        self.assertLess(i_odoo, i_start)
        commande = a[i_odoo]
        self.assertIn("-d base_prod", commande)                       # base of the "-d" of the service's command
        self.assertIn("-u rlq_autre,rlq_survey_report", commande.replace("rlq_survey_report,rlq_autre", "rlq_autre,rlq_survey_report"))
        self.assertNotIn("autre_module", commande)
        self.assertNotIn("rlq_sans_manifeste", commande)
        for option in ("--stop-after-init", "--no-http", "--workers=0", "--max-cron-threads=0", "--limit-time-real=1800", "-c " + self.conf):
            self.assertIn(option, commande)
        self.assertEqual(a[i_odoo + 1], "etat_service=inactive")        # Odoo runs with the service STOPPED
        self.assertEqual(os.path.realpath(a[i_odoo + 2]), os.path.realpath(self.odoo))
        self.assertIn("mise à jour terminée", out)
        self.assertTrue(os.listdir(os.path.join(self.d, "journaux")))
        # 1.33: duration of each phase and time the site was unavailable
        self.assertRegex(out, r"service erplibre_erplibre.service arrêté \(en \d+ s\)")
        self.assertIn("Odoo répond (HTTP 200 sur /web/login)", out)
        self.assertIn("site indisponible", out)
        self.assertRegex(out, r"Durées :.*arrêt \d+ s · mise à jour des modules \d+ s · démarrage \d+ s · première réponse")
        self.assertIn("Site coupé :", out)
        self.assertTrue(any(l.startswith("curl ") and "127.0.0.1:10000/web/login" in l for l in self.appels()))

    def test_134_redemarrage_seulement(self):
        """1.34 --restart-only : arrêt puis démarrage, aucune mise à jour de module, aucune copie des modules, durées affichées."""
        rc, out, err = self.lancer("--restart-only")
        self.assertEqual(rc, 0, out + err)
        a = self.appels()
        self.assertFalse([l for l in a if l.startswith("odoo ")])                             # no update of the modules
        self.assertLess(a.index("systemctl stop erplibre_erplibre.service"), a.index("systemctl start erplibre_erplibre.service"))
        self.assertNotIn("systemctl restart postgresql", a)
        self.assertIn("redémarrage terminé", out)
        self.assertIn("aucun (redémarrage seulement)", out)
        self.assertIn("Site coupé :", out)
        self.assertFalse(os.path.isdir(os.path.join(self.d, "copies")) and os.listdir(os.path.join(self.d, "copies")))     # no copy of the modules

    def test_141_liste_des_applications_sans_arreter_odoo(self):
        """1.41 --update-list : « odoo shell » sous le compte du service, le script Python sur l'entrée standard (update_list, commit), le
        service jamais arrêté ni redémarré ; nombres et modules sans code sur le disque affichés."""
        self.write("odoo_sortie", "RLQ_UPDATE_LIST\t3\t1\nRLQ_MISSING\tom_hospital openeducat_core plm\n")
        rc, out, err = self.lancer("--update-list")
        self.assertEqual(rc, 0, out + err)
        a = self.appels()
        odoo = [l for l in a if l.startswith("odoo ")]
        self.assertEqual(len(odoo), 1, a)
        self.assertTrue(odoo[0].startswith("odoo shell -c ") and " -d base_prod " in odoo[0] and "--no-http" in odoo[0], odoo[0])
        self.assertIn("etat_service=active", a)                                               # Odoo still running during the shell
        self.assertFalse([l for l in a if l.startswith(("systemctl stop", "systemctl start", "systemctl restart"))], a)
        entree = open(os.path.join(self.d, "odoo_stdin"), encoding="utf-8").read()
        self.assertIn('env["ir.module.module"].update_list()', entree)
        self.assertIn("env.cr.commit()", entree)
        self.assertIn("3 modules mis à jour, 1 ajoutés", re.sub(r"\x1b\[[0-9;]*m", "", out))
        self.assertIn("3 modules non installés sans code sur le disque", out)
        self.assertIn("om_hospital openeducat_core plm", out)
        self.assertIn("get_module_path(m.name, display_warning=False)", entree)                 # 1.42: not installed AND not on the disk
        self.assertIn("--remove-missing", out)                                                 # the way to remove them is named
        self.assertFalse([l for l in a if l.startswith("retrait=")])                           # nothing removed without --remove-missing

    def test_141_liste_des_applications_echec_et_simulation(self):
        self.write("odoo_code", "1\n")
        self.write("odoo_sortie", "Traceback (most recent call last):\npsycopg2.OperationalError: x\n")
        rc, out, err = self.lancer("--update-list")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("la mise à jour de la liste des applications a échoué (code 1", out)
        self.assertIn("psycopg2.OperationalError", out)
        os.remove(os.path.join(self.d, "odoo_code"))
        rc, out, err = self.lancer("--update-list", "--dry-run")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("(simulation)", out)
        self.assertFalse([l for l in self.appels() if l.startswith("odoo ") and "--dry" in l])

    def test_142_retrait_des_modules_sans_code(self):
        """1.42 --remove-missing : sans terminal ni --yes, rien n'est retiré (code 1) ; avec --yes, un second « odoo shell » retire exactement les
        modules listés par le premier ; Odoo n'est jamais arrêté."""
        self.write("odoo_sortie", "RLQ_UPDATE_LIST\t473\t0\nRLQ_MISSING\tom_hospital openeducat_core\n")
        rc, out, err = self.lancer("--remove-missing")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("confirmation requise (--yes sans terminal)", out)
        self.assertFalse([l for l in self.appels() if l.startswith("retrait=")])
        rc, out, err = self.lancer("--remove-missing", "--yes")
        self.assertEqual(rc, 0, out + err)
        a = self.appels()
        self.assertIn("retrait=om_hospital openeducat_core", a)
        self.assertIn("2 modules retirés de la base", re.sub(r"\x1b\[[0-9;]*m", "", out))
        entree = open(os.path.join(self.d, "odoo_stdin"), encoding="utf-8").read()                 # the second script: the removal
        self.assertIn('("state", "in", ("uninstalled", "uninstallable"))', entree)
        self.assertIn("cibles.unlink()", entree)
        self.assertFalse([l for l in a if l.startswith(("systemctl stop", "systemctl start", "systemctl restart"))], a)

    def test_135_prechauffage_du_redemarrage_seulement(self):
        """1.35 --restart-only : le journal du préchauffage a un vrai nom (restart-BASE-...-prechauffage.log dans le dossier des journaux), jamais
        « -prechauffage.log » dans le dossier courant (grep et tail le prenaient pour une option)."""
        self.faux_prechauffage()
        rc, out, err = self.lancer("--restart-only")
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("invalid option", out + err)
        self.assertIn("cache préchauffé en 3 s : 12 appels", out)
        journaux = os.listdir(os.path.join(self.d, "journaux"))
        self.assertTrue(any(n.startswith("restart-") and n.endswith("-prechauffage.log") for n in journaux), journaux)

    def test_134_redemarrage_avec_postgresql_dans_l_ordre(self):
        """1.34 --restart-postgresql : Odoo arrêté, PostgreSQL redémarré et prêt, puis Odoo démarré ; échec de PostgreSQL : Odoo redémarré quand même."""
        self.mock("pg_isready", "exit 0")
        rc, out, err = self.lancer("--restart-postgresql")
        self.assertEqual(rc, 0, out + err)
        a = self.appels()
        i_stop, i_pg, i_start = (a.index("systemctl stop erplibre_erplibre.service"), a.index("systemctl restart postgresql"),
                                 a.index("systemctl start erplibre_erplibre.service"))
        self.assertLess(i_stop, i_pg)
        self.assertLess(i_pg, i_start)
        self.assertIn("PostgreSQL redémarré et prêt", out)
        self.assertRegex(out, r"Durées :.*PostgreSQL \d+ s")
        self.assertIn("redémarrage terminé (PostgreSQL et Odoo)", out)
        os.remove(self.log)
        self.mock("pg_isready", "exit 2")
        self.write("etc/odoo-update-module.conf", "WAIT=3\n")                                # PostgreSQL never ready: 3 s of waiting, not 90
        rc, out, err = self.lancer("--restart-postgresql", ODOO_UPDATE_MODULE_PG_AS=self.write("pg-ko.sh", "#!/bin/bash\ncase \"$*\" in *\"SELECT 1\"*) exit 2 ;; esac\necho 0\n", 0o755))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("PostgreSQL n'accepte pas les connexions", out)
        self.assertIn("systemctl start erplibre_erplibre.service", self.appels())             # the site never stays stopped

    def test_echec_d_odoo_redemarre_quand_meme(self):
        self.write("odoo_code", "3\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("terminée avec le code 3", out)
        self.assertIn("systemctl start erplibre_erplibre.service", self.appels())

    def test_erreurs_dans_le_journal_d_odoo(self):
        self.write("odoo_sortie", "2026-10-14 10:00:00,000 1 ERROR base_prod odoo.modules.loading: Failed to load module\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("ERROR/CRITICAL", out)
        self.assertIn("Failed to load module", out)
        self.assertIn("systemctl start erplibre_erplibre.service", self.appels())

    def test_delai_depasse_tue_odoo_et_redemarre(self):
        self.write("odoo_duree", "30\n")
        rc, out, err = self.lancer("--timeout", "1")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("processus tué", out)
        self.assertIn("systemctl start erplibre_erplibre.service", self.appels())

    def test_odoo_lance_a_la_main_est_refuse_et_le_service_remis_en_route(self):
        self.write("pgrep", "4242 /usr/bin/python3 ./odoo-bin -c config.conf -u rlq_survey_report -d base_prod\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("HORS systemd", out)
        a = self.appels()
        self.assertFalse([l for l in a if l.startswith("odoo ")])
        self.assertEqual(a[-1], "systemctl start erplibre_erplibre.service")        # it was active: we restart it
        rc, out, err = self.lancer("--force")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("--force : on continue", out)

    def test_sortie_lisible_etapes_numerotees_et_couleurs(self):
        """1.0 -> 1.1 : en-tête compact (service, base, modules), étapes [1/7]…, ✔ vert ; sans terminal (tube) : aucun code de couleur."""
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        for etape in ("[1/7] Attente d'un site calme", "[2/7] Copie des modules", "[3/7] Arrêt du service", "[4/7] Mise à jour des modules dans la base base_prod", "[5/7] Redémarrage du service", "[7/7] Contrôle du journal d'Odoo"):     # 1.11: 7 steps
            self.assertIn(etape, out)
        self.assertIn("✔ mise à jour terminée", out)
        self.assertNotIn("\x1b[", out)
        self.assertNotIn("[OK]", out)
        texte, _ = self.run_pty(["bash", self.prog, "--lang", "fr"], [], dict(self.env), timeout=60, keep_ansi=True)
        self.assertIn("\x1b[1;36m▶ [3/7] Arrêt du service", texte)                       # step in bold cyan
        self.assertIn("\x1b[1;32m✔\x1b[0m", texte)                                       # success in green
        self.assertIn("\x1b[1;33mbase_prod", texte)                                      # la base en jaune gras

    FAUX_PRECHAUFFAGE = """#!/usr/bin/env python3
import sys
open(__import__("os").environ["D"] + "/appels.log", "a").write("warmup " + " ".join(sys.argv[1:]) + "\\n")
print("odoo-warmup.py v1.1")
print("  [OK    ] /event                                                               HTTP 200  plus lent :   0.2 s")
%s
print("Préchauffage terminé en 3 s : 12 appels, 4 assets publics, %d échecs" + "%s")
sys.exit(%d)
"""

    def faux_prechauffage(self, lignes="", echecs=0, suite="", code=0):
        self.write("prog/odoo-warmup.py", self.FAUX_PRECHAUFFAGE % (lignes, echecs, suite, code), 0o755)

    def test_prechauffage_apres_le_redemarrage(self):
        self.faux_prechauffage()
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("[6/7] Préchauffage du cache", out)
        self.assertIn("cache préchauffé en 3 s : 12 appels", out)
        a = self.appels()
        i_start = a.index("systemctl start erplibre_erplibre.service")
        i_warm = next(i for i, l in enumerate(a) if l.startswith("warmup "))
        self.assertGreater(i_warm, i_start)                                            # AFTER the restart
        self.assertIn("--url http://127.0.0.1:10000 --db base_prod", a[i_warm])
        self.assertLess(out.index("[5/7] Redémarrage"), out.index("[6/7] Préchauffage"))
        self.assertIn("✔ mise à jour terminée", out)

    def test_prechauffage_echecs_et_absence_sont_des_avertissements(self):
        self.faux_prechauffage('print("  [ÉCHEC ] /event/x                       HTTP 500  plus lent :   1.0 s  (1 échecs sur 1)")', 1, "", 1)
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)                                              # never a failure of the update
        self.assertIn("[ATTN] préchauffage terminé avec des échecs", out)
        self.assertIn("/event/x", out)
        os.remove(os.path.join(self.d, "prog", "odoo-warmup.py"))
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("odoo-warmup.py (ou python3) introuvable", out)

    def test_sans_prechauffage_et_administration_non_configuree(self):
        self.faux_prechauffage()
        rc, out, err = self.lancer("--no-warmup")
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("Préchauffage", out)
        self.assertFalse([l for l in self.appels() if l.startswith("warmup ")])
        self.assertIn("[5/6] Redémarrage", out)
        self.write("etc/odoo-update-module.conf", "WARMUP=non\n")
        rc, out, err = self.lancer()
        self.assertFalse([l for l in self.appels() if l.startswith("warmup ")])
        self.faux_prechauffage(suite=" ; administration non préchauffée (définir LOGIN et KEY_FILE).")
        self.write("etc/odoo-update-module.conf", "")
        rc, out, err = self.lancer()
        self.assertIn("LOGIN et KEY_FILE à définir", out)

    # --- 1.4: versions before / after, .zip archive ----------------------------------------------------------------------
    FAUX_RUNUSER = r"""
SEP=$'\x1f'
if grep -q '^odoo ' "$D/appels.log" 2>/dev/null; then f="$D/modules_apres"; else f="$D/modules_avant"; fi
[ -e "$f" ] || exit 1
while IFS='|' read -r n e v a m c; do printf '%s\n' "$n$SEP$e$SEP$v$SEP$a$SEP$m$SEP$c"; done < "$f"
"""

    def faux_versions(self, avant, apres):
        self.write("modules_avant", avant)
        self.write("modules_apres", apres)
        self.mock("runuser", self.FAUX_RUNUSER)

    def zip_modules(self, nom="rlq_survey_report.zip", modules=(("rlq_survey_report", "18.0.1.101.0"),), dossier=None, extra=None):
        chemin = os.path.join(dossier or self.d, nom)
        with zipfile.ZipFile(chemin, "w") as z:
            for module, version in modules:
                z.writestr(f"{module}/__manifest__.py", "{'name': 'X', 'version': '%s'}\n" % version)
                z.writestr(f"{module}/models/__init__.py", "")
            for n in (extra or []):
                z.writestr(n, "x")
        return chemin

    def test_versions_avant_et_apres(self):
        self.faux_versions("base|installed|18.0.1.3|Odoo S.A.|2026-10-01 10:00|2026-10-01 10:00\nrlq_survey_report|installed|18.0.1.100.0|RLQ|2026-10-10 12:00|2026-10-01 10:00\n"
                           "rlq_autre|installed|18.0.1.5.0|RLQ|2026-10-11 12:00|2026-10-01 10:00\n",
                           "base|installed|18.0.1.3|Odoo S.A.|2026-10-01 10:00|2026-10-01 10:00\nrlq_survey_report|installed|18.0.1.101.0|RLQ|2026-10-14 22:00|2026-10-01 10:00\n"
                           "rlq_autre|installed|18.0.1.5.0|RLQ|2026-10-14 22:00|2026-10-01 10:00\nnouveau_mod|installed|18.0.1.0.0|RLQ|2026-10-14 22:01|2026-10-14 22:01\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Versions des modules installés (base base_prod) — Odoo 18.0.1.3", out)
        self.assertRegex(out, r"rlq_survey_report\s+18\.0\.1\.100\.0 → 18\.0\.1\.101\.0\s+\(mis à jour\)")
        self.assertRegex(out, r"rlq_autre\s+18\.0\.1\.5\.0\s+\(inchangé\)")
        self.assertRegex(out, r"nouveau_mod\s+18\.0\.1\.0\.0\s+\(nouveau\)")
        self.assertLess(out.index("[4/7] Mise à jour"), out.index("Versions des modules installés"))
        self.assertLess(out.index("Versions des modules installés"), out.index("[5/7] Redémarrage"))

    def test_versions_illisibles_ne_cassent_rien(self):
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("versions des modules illisibles", out)

    def test_136_module_server_wide_jamais_dans_u(self):
        """1.36 : module server-wide de l'archive (post_load) non installé dans la base : décompressé, gardé dans la copie, jamais dans -u ;
        la commande qui l'active est affichée ; archive avec ce seul module : aucune mise à jour dans la base, redémarrage quand même."""
        chemin = os.path.join(self.d, "deux.zip")
        with zipfile.ZipFile(chemin, "w") as z:
            z.writestr("rlq_survey_report/__manifest__.py", "{'name': 'X', 'version': '18.0.1.101.0'}\n")
            z.writestr("rlq_preload_statics/__manifest__.py", "{'name': 'P', 'version': '18.0.1.0.0', 'post_load': 'post_load'}\n")
            z.writestr("rlq_preload_statics/__init__.py", "")
        dest = os.path.join(self.d, "destination")
        os.makedirs(dest)
        rc, out, err = self.lancer("--zip", chemin, "--addons-dir", dest)
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(dest, "rlq_preload_statics", "__init__.py")))
        odoo = [l for l in self.appels() if l.startswith("odoo ")]
        self.assertTrue(odoo)
        self.assertIn("rlq_survey_report", odoo[0])
        self.assertNotIn("rlq_preload_statics", odoo[0])
        self.assertIn("Server-wide :", out)
        self.assertIn("nginx-hardening.sh --update --odoo-preload-statics", out)
        os.remove(self.log)
        seul = os.path.join(self.d, "rlq_preload_statics.1.0.zip")
        with zipfile.ZipFile(seul, "w") as z:
            z.writestr("rlq_preload_statics/__manifest__.py", "{'name': 'P', 'version': '18.0.1.0.0', 'post_load': 'post_load'}\n")
        self.write("odoo/config.conf", "[options]\naddons_path = addons,custom\nhttp_port = 10000\ndb_name = False\nserver_wide_modules = base,web,rlq_preload_statics\n")
        rc, out, err = self.lancer("--module", "rlq_preload_statics", "--zip", seul, "--addons-dir", dest)
        self.assertEqual(rc, 0, out + err)
        self.assertFalse([l for l in self.appels() if l.startswith("odoo ")])               # nothing in the database
        self.assertIn("aucun module à mettre à jour dans la base", out)
        self.assertIn("déjà dans server_wide_modules", out)
        self.assertTrue(any(l.startswith("systemctl start") for l in self.appels()))         # restarted: the new code is taken

    def test_archive_decompressee_dans_le_dossier_demande(self):
        archive = self.zip_modules()
        dest = os.path.join(self.d, "destination")
        os.makedirs(dest)
        rc, out, err = self.lancer("--zip", archive, "--addons-dir", dest)
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(dest, "rlq_survey_report", "__manifest__.py")))
        self.assertIn("[4/8] Décompression de rlq_survey_report.zip", out)
        self.assertIn("18.0.1.101.0", out)
        self.assertIn("Archive :", out)
        entete = out.split("Archive :")[1].split("Compte :")[0]                            # 1.6: version of the manifest from the header
        self.assertIn("rlq_survey_report", entete)
        self.assertIn("version 18.0.1.101.0", entete)
        a = self.appels()
        self.assertLess(a.index("systemctl stop erplibre_erplibre.service"), next(i for i, l in enumerate(a) if l.startswith("odoo ")))
        self.assertTrue(os.path.isfile(archive))                                          # the archive is not deleted

    def test_archive_destination_deduite_de_addons_path_et_modules_ajoutes(self):
        """Sans --addons-dir : le dossier d'addons_path qui contient déjà le module ; un module nouveau de l'archive est mis à jour aussi."""
        archive = self.zip_modules(modules=(("rlq_survey_report", "18.0.1.101.0"), ("autre_nouveau", "18.0.1.0.0")))
        rc, out, err = self.lancer("--zip", archive)
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(self.odoo, "custom", "rlq_survey_report", "models", "__init__.py")))
        self.assertTrue(os.path.isfile(os.path.join(self.odoo, "custom", "autre_nouveau", "__manifest__.py")))
        commande = next(l for l in self.appels() if l.startswith("odoo "))
        self.assertIn("autre_nouveau", commande)

    def test_archive_du_dossier_courant_et_cle_zip_non(self):
        self.zip_modules(dossier=self.d)
        commande = f'cd "{self.d}" && bash "{self.prog}" --lang fr --addons-dir "{self.odoo}/custom"'
        rc, out, err = self.run_cmd(["bash", "-c", commande])
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Décompression de rlq_survey_report.zip", out)
        rc, out, err = self.run_cmd(["bash", "-c", commande + " --zip non"])
        self.assertNotIn("Décompression", out)

    def test_archive_dans_la_configuration(self):
        archive = self.zip_modules()
        self.write("etc/odoo-update-module.conf", f"ZIP={archive}\nADDONS_DIR={self.odoo}/custom\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Décompression de rlq_survey_report.zip", out)

    def test_archive_refusee_introuvable_dangereuse_destination_inconnue(self):
        rc, out, err = self.lancer("--zip", os.path.join(self.d, "absent.zip"))
        self.assertEqual(rc, 1, out + err)
        self.assertIn("archive introuvable", out)
        mauvaise = self.zip_modules("mauvaise.zip", extra=["../evasion.txt"])
        rc, out, err = self.lancer("--zip", mauvaise, "--addons-dir", f"{self.odoo}/custom")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("sort du dossier de destination", out)
        self.assertFalse(os.path.exists(os.path.join(self.odoo, "evasion.txt")))
        inconnu = self.zip_modules("inconnu.zip", modules=(("module_inconnu", "1.0"),))
        rc, out, err = self.lancer("--zip", inconnu)
        self.assertEqual(rc, 1, out + err)
        self.assertIn("préciser --addons-dir", out)
        self.assertFalse([l for l in self.appels() if l.startswith("systemctl stop")])      # nothing is stopped
        faux = os.path.join(self.d, "faux.zip")
        with open(faux, "w") as f:
            f.write("pas un zip")
        rc, out, err = self.lancer("--zip", faux, "--addons-dir", f"{self.odoo}/custom")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("archive illisible", out)

    def test_simulation_avec_archive_ne_decompresse_pas(self):
        archive = self.zip_modules(modules=(("rlq_survey_report", "18.0.1.101.0"),))
        dest = os.path.join(self.d, "destination")
        os.makedirs(dest)
        rc, out, err = self.lancer("--dry-run", "--zip", archive, "--addons-dir", dest)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("(simulation)", out)
        self.assertEqual(os.listdir(dest), [])

    def test_simulation_ne_touche_a_rien(self):
        rc, out, err = self.lancer("--dry-run")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual([l for l in self.appels() if "stop" in l or "start" in l or l.startswith("odoo ")], [])
        self.assertIn("(simulation) systemctl stop erplibre_erplibre.service", out)
        self.assertIn("--stop-after-init", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "journaux")))

    def test_230_i18n_overwrite_transmis_a_odoo(self):
        """1.30: --i18n-overwrite is passed to « odoo -u » (a corrected translation of a module replaces the loaded one); without
        it, the command is unchanged."""
        rc, out, err = self.lancer("--dry-run", "--i18n-overwrite")
        self.assertEqual(rc, 0, out + err)
        ligne = [l for l in out.splitlines() if "--stop-after-init" in l][0]
        self.assertIn("--i18n-overwrite", ligne)
        self.assertIn("traductions déjà chargées remplacées", out)
        rc, out, err = self.lancer("--dry-run")
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("--i18n-overwrite", [l for l in out.splitlines() if "--stop-after-init" in l][0])

    def test_service_detecte_unique(self):
        self.write("unites", "odoo-warmup.service loaded inactive dead x\nerplibre.service loaded active running ERPLibre\nnginx.service loaded active running n\n")
        self.lancer_detecte = self.lancer()
        rc, out, err = self.lancer_detecte
        self.assertEqual(rc, 0, out + err)
        self.assertIn("systemctl stop erplibre.service", self.appels())
        self.assertIn("(détecté)", out)

    def test_service_detecte_actif_prefere(self):
        self.write("unites", "erplibre.service loaded inactive dead x\nodoo.service loaded active running y\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("systemctl stop odoo.service", self.appels())

    def test_service_detecte_ambigu(self):
        self.write("unites", "erplibre.service loaded active running x\nodoo.service loaded active running y\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1)
        self.assertIn("plusieurs services Odoo possibles", out + err)
        self.assertFalse([l for l in self.appels() if " stop " in l])

    def test_service_explicite_l_emporte_sur_la_detection(self):
        self.write("unites", "odoo.service loaded active running y\n")
        rc, out, err = self.lancer("--service", "autre")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("systemctl stop autre.service", self.appels())
        self.assertNotIn("(détecté)", out)

    def test_base_et_modules_en_option(self):
        rc, out, err = self.lancer("--db", "ma_base", "--module", "rlq_autre", "--service", "autre")
        self.assertEqual(rc, 0, out + err)
        commande = next(l for l in self.appels() if l.startswith("odoo "))
        self.assertIn("-d ma_base", commande)
        self.assertIn("-u rlq_autre ", commande + " ")
        self.assertNotIn("rlq_survey_report", commande)
        self.assertIn("systemctl stop autre.service", self.appels())

    def test_base_depuis_la_configuration_d_odoo(self):
        self.write("prop.ExecStart", "{ path=/x/run.sh ; argv[]=/x/run.sh ; ignore_errors=no }\n")
        self.write("odoo/config.conf", "[options]\naddons_path = custom\nhttp_port = 10000\ndb_name = base_conf\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("-d base_conf", next(l for l in self.appels() if l.startswith("odoo ")))

    def test_base_introuvable_rien_n_est_arrete(self):
        self.write("prop.ExecStart", "{ path=/x/run.sh ; argv[]=/x/run.sh ; ignore_errors=no }\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("base introuvable", out)
        self.assertFalse([l for l in self.appels() if " stop " in l])

    def test_service_inconnu_modules_absents_et_motif_invalide(self):
        self.write("prop.LoadState", "not-found\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1)
        self.assertIn("introuvable (systemctl)", out)
        self.write("prop.LoadState", "loaded\n")
        rc, out, err = self.lancer("--module", "zzz_*")
        self.assertEqual(rc, 1)
        self.assertIn("aucun module trouvé", out)
        rc, out, err = self.lancer("--module", "rlq_*; rm -rf /")
        self.assertEqual(rc, 1)
        self.assertIn("motif de module invalide", out)
        self.assertEqual([l for l in self.appels() if " stop " in l or l.startswith("odoo ")], [])

    def test_sauvegarde_en_echec_abandonne_avant_l_arret(self):
        self.write("prog/odoo-backup.sh", '#!/bin/bash\necho "backup $*" >> "$D/appels.log"\nexit 1\n', 0o755)
        rc, out, err = self.lancer("--backup")
        self.assertEqual(rc, 1, out + err)
        self.assertEqual([l for l in self.appels() if not l.startswith(("systemctl show", "systemctl list-units"))], ["backup --db base_prod"])
        self.write("prog/odoo-backup.sh", '#!/bin/bash\necho "backup $*" >> "$D/appels.log"\nexit 0\n', 0o755)
        rc, out, err = self.lancer("--backup")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("backup --db base_prod", self.appels())
        self.assertIn("[1/8] Sauvegarde de la base base_prod", out)
        self.assertIn("[6/8] Redémarrage du service", out)

    def test_demarrage_impossible(self):
        self.write("demarrage_impossible", "")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1)
        self.assertIn("a échoué", out)

    def test_configuration_lue_et_resumee(self):
        self.write("etc/odoo-update-module.conf", "TIMEOUT=900\nMODULES=rlq_autre\n")
        rc, out, err = self.lancer("--dry-run")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Configuration lue : ", out)
        self.assertIn("odoo-update-module.conf", out)
        self.assertIn("--limit-time-real=900", out)
        self.assertNotIn("rlq_survey_report", out.split("Modules :")[1].splitlines()[0])


    # --- 1.11: quiet site before the stop, copy of the modules, check after the start, rollback ----------------------------------------
    def journal_nginx(self, adresses, robots=0):
        import datetime
        t = datetime.datetime.now(datetime.timezone.utc).astimezone().strftime("%d/%b/%Y:%H:%M:%S %z")
        lignes = [f'{ip} - - [{t}] "GET /event HTTP/1.1" 200 512 "-" "Mozilla/5.0 (X11; Linux x86_64) Firefox/131.0"' for ip in adresses]
        lignes += [f'66.249.66.{i} - - [{t}] "GET / HTTP/1.1" 200 512 "-" "Mozilla/5.0 (compatible; Googlebot/2.1)"' for i in range(robots)]
        self.write("nginx/site-access.log", "\n".join(lignes) + "\n")

    def pg_connectes(self, adresses):
        """1.29: a psql stand-in whose res_device_log lists these addresses as users logged in to Odoo (other queries: 0)."""
        lignes = "".join(f"{ip}|user{i}|User {i}|Canada|1762714800\\n" for i, ip in enumerate(adresses))
        return self.write("pg-connectes.sh", "#!/bin/bash\ncase \"$*\" in\n*res_device_log*) printf '" + lignes + "' ;;\n*) echo 0 ;;\nesac\n", 0o755)

    def test_229_visiteurs_non_connectes_en_lecture_ne_comptent_pas(self):
        """1.29 : cas réel du 2026-11-13 (42 visiteurs non connectés) : seuls les visiteurs connectés à Odoo, ou ceux qui écrivent, comptent."""
        self.journal_nginx([f"198.51.100.{i}" for i in range(40)])
        rc, out, err = self.lancer("--check-activity")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site calme", out)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_PG_AS=self.pg_connectes(["198.51.100.1", "198.51.100.2", "198.51.100.3"]))
        self.assertEqual(rc, 3, out + err)
        self.assertIn("3 visiteurs actifs (connectés à Odoo ou en écriture)", out)
        self.assertIn("198.51.100.2 ", out)
        self.assertNotIn("198.51.100.30 ", out)                 # not logged in, only reads: not waited for
        mauvais = self.write("pg-ko.sh", "#!/bin/bash\nexit 1\n", 0o755)      # database unreadable: every address counts, never blind
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_PG_AS=mauvais)
        self.assertIn("40 visiteurs actifs", out, out + err)

    def test_229_onglet_ouvert_sans_activite_ne_compte_pas(self):
        """1.29 : cas réel du 2026-11-14 : un onglet d'Odoo laissé ouvert (GET /websocket, POST /bus/has_missed_notifications) n'est pas une activité."""
        import datetime
        t = datetime.datetime.now(datetime.timezone.utc).astimezone().strftime("%d/%b/%Y:%H:%M:%S %z")
        ips = [f"198.51.100.{i}" for i in range(4)]
        lignes = [f'{ip} - - [{t}] "{r} HTTP/1.1" 200 45 "-" "Mozilla/5.0"' for ip in ips for r in ("GET /websocket?version=18.0-7", "POST /bus/has_missed_notifications")]
        self.write("nginx/site-access.log", "\n".join(lignes) + "\n")
        pg = self.pg_connectes(ips)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_PG_AS=pg)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site calme", out)
        lignes += [f'{ip} - - [{t}] "GET /odoo/project/6/tasks/131 HTTP/1.1" 200 45 "-" "Mozilla/5.0"' for ip in ips[:3]]
        self.write("nginx/site-access.log", "\n".join(lignes) + "\n")
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_PG_AS=pg)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("3 visiteurs actifs", out)
        self.assertRegex(out, r"198\.51\.100\.0 .* · 1 requêtes")       # the polls of the bus are not counted

    def test_site_occupe_attente_puis_mise_a_jour_quand_il_devient_calme(self):
        """1.11 : 5 visiteurs actifs (robots exclus) : attente ; quand ils sont partis, arrêt et mise à jour."""
        self.journal_nginx([f"198.51.100.{i}" for i in range(5)], robots=4)
        self.mock("sleep", 'echo "sleep $*" >> "$D/appels.log"; rm -f "$D/nginx/site-access.log"; touch "$D/nginx/vide-access.log"')
        self.env["ODOO_UPDATE_MODULE_PG_AS"] = self.pg_connectes([f"198.51.100.{i}" for i in range(5)])      # 1.29: logged in to Odoo
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site occupé :", out)
        self.assertIn("5 visiteurs actifs", out)                          # les 4 robots ne comptent pas
        self.assertIn("site calme : aucune écriture HTTP ni en base", out)
        a = self.appels()
        self.assertLess(a.index("sleep 0"), a.index("systemctl stop erplibre_erplibre.service"))

    def test_site_calme_aucune_attente_et_wait_quiet_0(self):
        self.journal_nginx(["198.51.100.1"])
        rc, out, err = self.lancer()
        self.assertIn("site calme : aucune écriture HTTP ni en base, aucun utilisateur connecté actif", out)
        rc, out, err = self.lancer("--wait-quiet", "0")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("attente maximale : 0 min", out)   # a single check, no wait
        self.journal_nginx([f"198.51.100.{i}" for i in range(5)])
        self.env["ODOO_UPDATE_MODULE_PG_AS"] = self.pg_connectes([f"198.51.100.{i}" for i in range(5)])      # 1.29: logged in to Odoo
        rc, out, err = self.lancer("--dry-run")
        self.assertIn("maintenant occupé : 5 visiteurs actifs", out)

    def test_copie_des_modules_avant_la_mise_a_jour(self):
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        copies = sorted(f for f in os.listdir(os.path.join(self.d, "copies")) if f.endswith(".tar.gz"))
        self.assertEqual(len(copies), 1)
        self.assertIn("2 modules copiés", out)
        import tarfile
        with tarfile.open(os.path.join(self.d, "copies", copies[0])) as t:
            noms = t.getnames()
        self.assertTrue(any(n.endswith("custom/rlq_survey_report/__manifest__.py") for n in noms), noms)
        self.assertFalse(any("autre_module" in n for n in noms))

    def test_erreurs_apres_le_demarrage_retour_arriere_automatique(self):
        """1.11 : erreurs dans le journal du service après le démarrage → modules d'avant remis, nouvelle mise à jour, redémarrage ; sans terminal : automatique."""
        ancien = os.path.join(self.odoo, "custom", "rlq_survey_report")
        self.write("odoo/custom/rlq_survey_report/ANCIEN", "version d'avant\n")
        archive = self.zip_modules()
        self.mock("journalctl", 'echo "journalctl $*" >> "$D/appels.log"; n=$(cat "$D/n_journal" 2>/dev/null || echo 0); echo $((n + 1)) > "$D/n_journal"; '
                                '[ "$n" = 0 ] && echo "2026-10-16 15:00:00,000 1 ERROR base_prod odoo.http: Exception during request handling."; exit 0')
        rc, out, err = self.lancer("--zip", archive)
        self.assertEqual(rc, 1, out + err)
        self.assertIn("ERROR/CRITICAL dans le journal d'Odoo depuis le démarrage", out)
        self.assertIn("Exception during request handling", out)
        self.assertIn("Retour arrière des modules", out)
        self.assertIn("retour arrière réussi", out)
        self.assertIn("mise à jour ANNULÉE", out)
        self.assertTrue(os.path.isfile(os.path.join(ancien, "ANCIEN")))                   # la version d'avant est revenue
        self.assertFalse(os.path.exists(os.path.join(ancien, "models")))                   # les fichiers de l'archive sont partis
        a = self.appels()
        self.assertEqual(len([l for l in a if l.startswith("odoo ")]), 2)                  # update, then update with the previous modules
        self.assertEqual(a.count("systemctl start erplibre_erplibre.service"), 2)
        self.assertEqual(a[-1].split()[0], "journalctl")

    def test_pas_de_retour_arriere_sans_archive_ou_avec_no_rollback(self):
        self.write("journal_service", "2026-10-16 15:00:00,000 1 CRITICAL base_prod odoo.service.server: boum\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("pas de retour arrière : ce programme n'a pas remplacé le code", out)
        archive = self.zip_modules()
        rc, out, err = self.lancer("--zip", archive, "--no-rollback")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("retour arrière désactivé", out)
        self.assertEqual(len([l for l in self.appels() if l.startswith("odoo ")]), 2)    # one update per launch, no more

    def test_echec_de_la_mise_a_jour_retour_arriere(self):
        self.write("odoo/custom/rlq_survey_report/ANCIEN", "x\n")
        self.write("odoo_code", "1\n")
        rc, out, err = self.lancer("--zip", self.zip_modules())
        self.assertEqual(rc, 1, out + err)
        self.assertIn("Retour arrière des modules", out)
        self.assertTrue(os.path.isfile(os.path.join(self.odoo, "custom", "rlq_survey_report", "ANCIEN")))
        self.assertIn("la mise à jour avec les modules d'avant a échoué aussi", out)       # the fake Odoo always fails: says it clearly
        a = self.appels()
        self.assertGreater(len(a) - 1 - a[::-1].index("systemctl start erplibre_erplibre.service"), max(i for i, l in enumerate(a) if l.startswith("odoo ")))
        self.assertEqual(open(self.path("etat")).read().strip(), "active")                 # the site never stays stopped

    def test_137_plusieurs_archives_par_plusieurs_zip(self):
        """1.37 : --zip répétable : les deux archives sont décompressées l'une après l'autre, leurs modules sont mis à jour ensemble."""
        a = self.zip_modules("a.zip", modules=(("rlq_survey_report", "18.0.1.101.0"),))
        b = self.zip_modules("b.zip", modules=(("rlq_nouveau_zip", "18.0.1.0.0"),))
        rc, out, err = self.lancer("--zip", a, "--zip", b, "--addons-dir", f"{self.odoo}/custom")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Décompression de a.zip", out)
        self.assertIn("Décompression de b.zip", out)
        self.assertLess(out.index("Décompression de a.zip"), out.index("Décompression de b.zip"))
        self.assertTrue(os.path.isfile(os.path.join(self.odoo, "custom", "rlq_nouveau_zip", "__manifest__.py")))
        commande = next(l for l in self.appels() if l.startswith("odoo "))
        self.assertIn("rlq_nouveau_zip", commande)
        self.assertIn("rlq_survey_report", commande)

    def test_138_compteur_d_etapes_avec_plusieurs_archives(self):
        """1.38 : le total d'étapes compte une étape par archive : la dernière étape affichée est [N/N], jamais [N+1/N]."""
        a = self.zip_modules("a.zip", modules=(("rlq_survey_report", "18.0.1.101.0"),))
        b = self.zip_modules("b.zip", modules=(("rlq_nouveau_zip", "18.0.1.0.0"),))
        rc, out, err = self.lancer("--zip", a, "--zip", b, "--addons-dir", f"{self.odoo}/custom")
        self.assertEqual(rc, 0, out + err)
        etapes = [int(m.group(1)) for m in re.finditer(r"\[(\d+)/(\d+)\]", re.sub(r"\x1b\[[0-9;]*m", "", out))]
        totaux = {int(m.group(2)) for m in re.finditer(r"\[(\d+)/(\d+)\]", re.sub(r"\x1b\[[0-9;]*m", "", out))}
        self.assertEqual(len(totaux), 1, out)
        total = totaux.pop()
        self.assertLessEqual(max(etapes), total, out)
        self.assertEqual(max(etapes), total, out)

    def test_137_un_module_dans_deux_archives_refuse(self):
        a = self.zip_modules("a.zip", modules=(("rlq_survey_report", "18.0.1.101.0"),))
        b = self.zip_modules("b.zip", modules=(("rlq_survey_report", "18.0.1.102.0"),))
        rc, out, err = self.lancer("--zip", a, "--zip", b, "--addons-dir", f"{self.odoo}/custom")
        self.assertNotEqual(rc, 0, out + err)
        self.assertIn("rlq_survey_report présent dans deux archives", out + err)
        self.assertFalse([l for l in self.appels() if l.startswith("odoo ")])        # nothing updated

    def test_137_archive_indiquee_deux_fois_refusee_et_non_avec_autre_archive(self):
        a = self.zip_modules("a.zip", modules=(("rlq_survey_report", "18.0.1.101.0"),))
        rc, out, err = self.lancer("--zip", a, "--zip", a, "--addons-dir", f"{self.odoo}/custom")
        self.assertNotEqual(rc, 0, out + err)
        self.assertIn("indiquée deux fois", out + err)
        rc, out, err = self.lancer("--zip", "non", "--zip", a, "--addons-dir", f"{self.odoo}/custom")
        self.assertNotEqual(rc, 0, out + err)
        self.assertIn("ne se combine pas", out + err)

    def test_137_zip_de_la_configuration_plusieurs_noms_et_option_remplace_la_configuration(self):
        a = self.zip_modules("a.zip", modules=(("rlq_survey_report", "18.0.1.101.0"),))
        b = self.zip_modules("b.zip", modules=(("rlq_nouveau_zip", "18.0.1.0.0"),))
        self.write("etc/odoo-update-module.conf", f"ZIP={a} {b}\nADDONS_DIR={self.odoo}/custom\n")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Décompression de a.zip", out)
        self.assertIn("Décompression de b.zip", out)
        self.write("etc/odoo-update-module.conf", f"ZIP={a} {b}\nADDONS_DIR={self.odoo}/custom\n")
        rc, out, err = self.lancer("--zip", b)
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("Décompression de a.zip", out)                                 # the option replaces the ZIP of the configuration
        self.assertIn("Décompression de b.zip", out)

    def test_aide_options_1_11_en_ordre_alphabetique(self):
        rc, out, err = self.lancer("--help")
        options = [l.split()[0] for l in out.splitlines() if l.startswith("  --") or l.startswith("  -")]
        for o in ("--busy-visitors", "--no-rollback", "--wait-quiet"):
            self.assertIn(o, options)
        cles = [o.lstrip("-").split(",")[0] for o in options]
        self.assertEqual([c for c in cles if c not in ("c", "h", "v")], sorted(c for c in cles if c not in ("c", "h", "v")))


class DetailVif140(unittest.TestCase):
    """1.40: in the activity report, e-mail addresses (cyan), times (green) and numbers (yellow) stand out of the dim detail line."""
    COULEURS = {"C_RESET": "<R>", "C_CYAN": "<C>", "C_GREEN": "<G>", "C_YELLOW": "<Y>", "C_DIM": "<D>", "C_BOLD": "<B>"}

    def vif(self, texte, couleurs=True):
        import subprocess
        prog = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "odoo-update-module.sh"), encoding="utf-8").read()
        debut = prog.index("\ndetail() {") + 1
        fin = prog.index("\n}\n", prog.index("\ndetail_vif() {")) + 3
        env = dict(os.environ, **(self.COULEURS if couleurs else {k: "" for k in self.COULEURS}))
        r = subprocess.run(["bash", "-c", prog[debut:fin] + '\ndetail_vif "$1"', "bash", texte], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.rstrip("\n")

    @unittest.skipIf(shutil.which("perl") is None, "perl absent")
    def test_courriel_heure_et_nombres(self):
        out = self.vif("69.157.88.222 CA (Canada) · julien.touche+rencontreslinux@gmail.com (Julien T) · 57 requêtes, dernière à 18:46:04, 1 POST")
        self.assertIn("<R><C>julien.touche+rencontreslinux@gmail.com<R><D>", out)
        self.assertIn("<R><G>18:46:04<R><D>", out)
        self.assertIn("<R><Y>57<R><D> requêtes", out)
        self.assertIn("<R><Y>1<R><D> POST", out)
        self.assertIn("69.157.88.222 CA", out)                      # an IP address keeps the colour of the line
        self.assertTrue(out.startswith("    <D>") and out.endswith("<R>"))

    @unittest.skipIf(shutil.which("perl") is None, "perl absent")
    def test_chemins_et_versions_inchanges(self):
        out = self.vif("· 2 écritures HTTP (POST…) dans les 5 dernières minutes, la plus récente : 18:51:50 POST /event/journee-2026-125/registration/new (72.143.215.147)")
        self.assertIn("/event/journee-2026-125/registration/new (72.143.215.147)", out)
        self.assertIn("<Y>2<R><D> écritures", out)
        self.assertIn("<Y>5<R><D> dernières", out)
        self.assertIn("<G>18:51:50<R>", out)
        self.assertIn("version 18.0.1.0.0", self.vif("version 18.0.1.0.0"))
        self.assertIn("<Y>60<R><D> min", self.vif("· attente maximale : 60 min (utilisateur connecté actif)"))

    def test_sortie_redirigee_sans_couleur(self):
        texte = "martial.bigras.ing@gmail.com · 6 requêtes, dernière à 18:49:28"
        self.assertEqual(self.vif(texte, couleurs=False), "    " + texte)


if __name__ == "__main__":
    unittest.main()
