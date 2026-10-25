"""odoo-update-module.sh : mise à jour des modules rlq_* puis redémarrage d'Odoo par systemd (systemctl, runuser, pgrep, ss simulés ; Odoo simulé)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"
import datetime
import getpass
import os
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
        self.assertIn("écriture(s) HTTP", out)
        rc, out, err = self.lancer("--check-activity", ODOO_UPDATE_MODULE_NOW=self._epoch("2026-10-22 16:23:00 UTC"))     # 12:23 EDT: last write at 12:17
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site calme", out)

    def test_199_attente_annulee_sans_force_et_passee_avec_force_busy(self):
        self._journal_exemple()
        occupe = self._epoch("2026-10-22 16:09:00 UTC")
        rc, out, err = self.lancer("--wait-quiet", "0", ODOO_UPDATE_MODULE_NOW=occupe)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("ANNULÉE", out)
        self.assertNotIn("systemctl stop erplibre_erplibre.service", self.appels())          # nothing was stopped
        rc, out, err = self.lancer("--wait-quiet", "0", "--force-busy", ODOO_UPDATE_MODULE_NOW=occupe)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("systemctl stop erplibre_erplibre.service", self.appels())

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
print("Préchauffage terminé en 3 s : 12 appel(s), 4 asset(s) public(s), %d échec(s)" + "%s")
sys.exit(%d)
"""

    def faux_prechauffage(self, lignes="", echecs=0, suite="", code=0):
        self.write("prog/odoo-warmup.py", self.FAUX_PRECHAUFFAGE % (lignes, echecs, suite, code), 0o755)

    def test_prechauffage_apres_le_redemarrage(self):
        self.faux_prechauffage()
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("[6/7] Préchauffage du cache", out)
        self.assertIn("cache préchauffé en 3 s : 12 appel(s)", out)
        a = self.appels()
        i_start = a.index("systemctl start erplibre_erplibre.service")
        i_warm = next(i for i, l in enumerate(a) if l.startswith("warmup "))
        self.assertGreater(i_warm, i_start)                                            # AFTER the restart
        self.assertIn("--url http://127.0.0.1:10000 --db base_prod", a[i_warm])
        self.assertLess(out.index("[5/7] Redémarrage"), out.index("[6/7] Préchauffage"))
        self.assertIn("✔ mise à jour terminée", out)

    def test_prechauffage_echecs_et_absence_sont_des_avertissements(self):
        self.faux_prechauffage('print("  [ÉCHEC ] /event/x                       HTTP 500  plus lent :   1.0 s  (1 échec(s) sur 1)")', 1, "", 1)
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

    def test_site_occupe_attente_puis_mise_a_jour_quand_il_devient_calme(self):
        """1.11 : 5 visiteurs actifs (robots exclus) : attente ; quand ils sont partis, arrêt et mise à jour."""
        self.journal_nginx([f"198.51.100.{i}" for i in range(5)], robots=4)
        self.mock("sleep", 'echo "sleep $*" >> "$D/appels.log"; rm -f "$D/nginx/site-access.log"; touch "$D/nginx/vide-access.log"')
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("site occupé :", out)
        self.assertIn("5 visiteur(s) actif(s)", out)                          # les 4 robots ne comptent pas
        self.assertIn("site calme : aucune écriture HTTP ni en base", out)
        a = self.appels()
        self.assertLess(a.index("sleep 0"), a.index("systemctl stop erplibre_erplibre.service"))

    def test_site_calme_aucune_attente_et_wait_quiet_0(self):
        self.journal_nginx(["198.51.100.1"])
        rc, out, err = self.lancer()
        self.assertIn("site calme : aucune écriture HTTP ni en base, visiteurs actifs sous le seuil de 3", out)
        rc, out, err = self.lancer("--wait-quiet", "0")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Attente d'un site calme (au plus 0 min", out)   # a single check, no wait
        self.journal_nginx([f"198.51.100.{i}" for i in range(5)])
        rc, out, err = self.lancer("--dry-run")
        self.assertIn("maintenant occupé : 5 visiteur(s) actif(s)", out)

    def test_copie_des_modules_avant_la_mise_a_jour(self):
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        copies = sorted(f for f in os.listdir(os.path.join(self.d, "copies")) if f.endswith(".tar.gz"))
        self.assertEqual(len(copies), 1)
        self.assertIn("2 module(s) copié(s)", out)
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

    def test_aide_options_1_11_en_ordre_alphabetique(self):
        rc, out, err = self.lancer("--help")
        options = [l.split()[0] for l in out.splitlines() if l.startswith("  --") or l.startswith("  -")]
        for o in ("--busy-visitors", "--no-rollback", "--wait-quiet"):
            self.assertIn(o, options)
        cles = [o.lstrip("-").split(",")[0] for o in options]
        self.assertEqual([c for c in cles if c not in ("c", "h", "v")], sorted(c for c in cles if c not in ("c", "h", "v")))


if __name__ == "__main__":
    unittest.main()
