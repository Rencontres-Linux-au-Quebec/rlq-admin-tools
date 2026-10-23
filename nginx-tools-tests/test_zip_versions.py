"""zip-versions.py — versions contenues dans les archives (sans extraction), archive la plus récente par type,
comparaison avec l'installation et la configuration déployées."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import zipfile

from helpers import EnvTest, script_path


def programme(version, bash=False):
    return (f'#!/bin/bash\nreadonly SCRIPT_VERSION="{version}"\n' if bash else f'#!/usr/bin/env python3\n__version__ = "{version}"\n')


class ZipVersions(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = script_path("zip-versions.py")
        self.dossier = os.path.dirname(self.path("dl", "x"))

    def archive(self, nom, membres):
        chemin = os.path.join(self.dossier, nom)
        with zipfile.ZipFile(chemin, "w") as z:
            for rel, contenu in membres.items():
                z.writestr(rel, contenu)
        return chemin

    def outils(self, nom, wm, rapport="1.1.20260930.225745"):
        return self.archive(nom, {"nginx-tools/web-monitor.py": programme(wm),
                                  "nginx-tools/nginx-hardening.sh": programme("2.16.20260930.163902", bash=True),
                                  "nginx-tools/apps/_rapport.py": programme(rapport),
                                  "nginx-tools/doc/web-monitor.changelog.txt": "## x\n"})

    def lancer(self, *arguments):
        rc, out, err = self.run_cmd(["python3", self.prog] + list(arguments), {"NO_COLOR": "1"})
        self.assertNotIn("Traceback", err, err)
        return rc, out

    def test_versions_des_trois_archives_et_la_plus_recente(self):
        """1.0 : la 2.35 avait été envoyée à la place de la 2.36 — l'archive la plus récente de chaque type est désignée."""
        self.outils("nginx-tools.zip", "2.35.20260930.163902", rapport="1.0.20260930.163902")
        self.outils("nginx-tools (1).zip", "2.37.20261001.090925")
        self.archive("nginx-tools-tests.zip", {"nginx-tools-tests/run-all.sh": programme("1.54.20261001.090925", bash=True),
                                               "nginx-tools-tests/test_rapport.py": 'X = """__version__ = "9.9.20991231.000000"""\n',
                                               "nginx-tools-tests/nginx-odoo/README.md": "## Historique\n- 2026-09-30 : a\n- 2026-10-01 : b\n",
                                               "nginx-tools-tests/nginx-odoo/conf.d/odoo-global.conf": "x;\n"})
        self.archive("nginx-odoo-config.zip", {"nginx-odoo/README.md": "## Historique\n- 2026-09-30 : a\n- 2026-10-01 : b\n",
                                               "nginx-odoo/conf.d/odoo-global.conf": "x;\n"})
        self.archive("vieille-config.zip", {"nginx-odoo/README.md": "- 2026-09-28 : a\n", "nginx-odoo/conf.d/odoo-global.conf": "y;\n"})
        rc, out = self.lancer(self.dossier)
        self.assertIn("web-monitor.py                   2.35.20260930.163902", out)
        self.assertIn("apps/_rapport.py                 1.1.20260930.225745", out)
        self.assertIn("nginx-hardening.sh               2.16.20260930.163902", out)
        self.assertIn("run-all.sh                       1.54.20261001.090925", out)
        self.assertNotIn("9.9.20991231", out)                                  # fake version of the test data ignored
        self.assertIn("configuration nginx (journal)    2026-10-01 — 2 fichier(s)", out)
        self.assertIn("nginx-tools.zip est plus ancienne que", out)
        self.assertIn("web-monitor.py 2.35.20260930.163902 < 2.37.20261001.090925", out)
        self.assertIn("vieille-config.zip est plus ancienne que", out)
        a_joindre = out.split("ARCHIVES À JOINDRE")[1]
        self.assertIn("nginx-tools (1).zip  (plus récent : web-monitor.py 2.37.20261001.090925)", a_joindre)
        self.assertIn(os.path.join(self.dossier, "nginx-odoo-config.zip"), a_joindre)
        self.assertIn("nginx-tools-tests.zip  (plus récent : run-all.sh 1.54.20261001.090925)", a_joindre)
        self.assertIn("nginx-tools-tests.zip ↔ nginx-odoo-config.zip : 2 fichier(s) commun(s), tous identiques", out)
        self.assertEqual(rc, 0)

    def test_versions_datees_d_aujourd_hui_en_vert(self):
        """1.9 : les programmes dont la version porte la date d'aujourd'hui sont en vert (valider d'un coup d'œil la dernière version) ; une légende l'explique."""
        import datetime
        import importlib.util
        aujourdhui = datetime.datetime.now().strftime("%Y%m%d")
        spec = importlib.util.spec_from_file_location("zip_versions_test", self.prog)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.COLOR = True
        self.assertEqual(mod.colored_version(f"2.41.{aujourdhui}.101500"), f"\x1b[1;32m2.41.{aujourdhui}.101500\x1b[0m")
        self.assertEqual(mod.colored_version("2.41.20200101.101500"), "2.41.20200101.101500")
        self.assertFalse(mod.is_today("pas une version"))
        self.archive("nginx-tools.zip", {"nginx-tools/web-monitor.py": programme(f"2.60.{aujourdhui}.101500"),
                                         "nginx-tools/nginx-hardening.sh": programme("2.16.20260930.163902", bash=True),
                                         "nginx-tools/doc/web-monitor.changelog.txt": "## x\n"})
        rc, out = self.lancer(self.dossier)
        self.assertIn("vert = version ou fichier daté d'aujourd'hui", out)

    def test_couleur_des_versions_du_jour_dans_toutes_les_sections(self):
        """1.10 : toute ligne affichée — dont « ARCHIVES À JOINDRE À LA DISCUSSION » — colore les versions du jour, sans double couleur ni toucher aux anciennes."""
        import datetime
        import importlib.util
        j = datetime.datetime.now().strftime("%Y%m%d")
        spec = importlib.util.spec_from_file_location("zip_versions_test2", self.prog)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.COLOR = True
        ligne = f"  nginx-tools /tmp/nginx-tools.1.104.zip  (version 1.104.{j}.090500, plus récent : app-log-live.py 1.76.{j}.083721 ; ancien 1.2.20200101.000000)"
        r = mod.colorize_versions(ligne)
        self.assertIn(f"\x1b[1;32m1.104.{j}.090500\x1b[0m", r)
        self.assertIn(f"\x1b[1;32m1.76.{j}.083721\x1b[0m", r)
        self.assertIn(" ancien 1.2.20200101.000000)", r)
        self.assertNotIn("nginx-tools.1.104.zip\x1b", r)                # the archive name (without date) is not touched
        self.assertEqual(mod.colorize_versions(r), r)                   # idempotent
        mod.COLOR = False
        self.assertEqual(mod.colorize_versions(ligne), ligne)
        self.assertTrue(mod.VIEWS["today"])

    def test_archive_corrompue_et_source_absente(self):
        with open(os.path.join(self.dossier, "abime.zip"), "wb") as f:
            f.write(b"pas une archive")
        self.outils("nginx-tools.zip", "2.37.20261001.090925")
        rc, out = self.lancer(self.dossier, os.path.join(self.dossier, "nexiste-pas.zip"))
        self.assertIn("[ATTN] archive illisible", out)
        self.assertIn("nexiste-pas.zip : introuvable", out)
        self.assertIn("manquant(s) : nginx-tools-tests", out)
        self.assertEqual(rc, 1)

    def test_comparaison_avec_l_installation_et_la_configuration(self):
        """--installed : à déployer, archive périmée, identique ; configuration nginx comparée par contenu."""
        zip_outils = self.outils("nginx-tools.zip", "2.37.20261001.090925")
        inst = os.path.dirname(self.path("scripts", "x"))
        self.write("scripts/web-monitor.py", programme("2.35.20260930.163902"))           # older: to deploy
        self.write("scripts/nginx-hardening.sh", programme("2.17.20261002.080000", bash=True))  # newer: archive outdated
        self.write("scripts/apps/_rapport.py", programme("1.1.20260930.225745"))           # identique
        self.archive("nginx-odoo-config.zip", {"nginx-odoo/README.md": "- 2026-10-01 : b\n",
                                               "nginx-odoo/conf.d/odoo-global.conf": "x;\n",
                                               "nginx-odoo/sites-available/10-prod.conf": "server {}\n",
                                               "nginx-odoo/sites-available/30-lab.conf": "server {}\n",
                                               "nginx-odoo/fail2ban/odoo-auth.filter.conf": "[Definition]\n"})
        ngx = os.path.dirname(self.path("nginx", "conf.d", "x"))
        self.write("nginx/conf.d/odoo-global.conf", "x;\n")
        self.write("nginx/sites-available/10-prod.conf", "server { listen 80; }\n")
        rc, out = self.lancer(zip_outils, os.path.join(self.dossier, "nginx-odoo-config.zip"),
                              "--installed", inst, "--nginx-dir", os.path.dirname(ngx))
        self.assertIn("web-monitor.py : installé 2.35.20260930.163902 < archive 2.37.20261001.090925 — à déployer", out)
        self.assertIn("nginx-hardening.sh : installé 2.17.20261002.080000 > archive 2.16.20260930.163902 — archive périmée", out)
        self.assertIn("[OK]   apps/_rapport.py 1.1.20260930.225745", out)
        self.assertIn("configuration : 1 fichier(s) identique(s)", out)
        self.assertIn("1 fichier(s) différent(s) de l'archive : sites-available/10-prod.conf", out)
        self.assertIn("1 absent(s)", out)
        self.assertNotIn("fail2ban/odoo-auth.filter.conf", out)                   # copied elsewhere: not compared
        self.assertEqual(rc, 1)

    def test_aucune_archive(self):
        vide = os.path.dirname(self.path("vide", "x"))
        rc, out = self.lancer(vide)
        self.assertIn("Aucune archive (.zip) trouvée", out)
        self.assertEqual(rc, 1)

    def test_ancien_nom_tests_et_archive_d_un_autre_programme(self):
        """1.1 : la suite s'appelle nginx-tools-tests (archive et dossier) — un tests.zip d'un autre programme n'est pas
        pris pour le nôtre ; notre ancien tests.zip est reconnu (signature) et signalé ; le nouveau l'emporte."""
        self.archive("tests.zip", {"tests/run-all.sh": programme("9.0.20261005.000000", bash=True),   # autre programme
                                   "tests/test_autre.py": "x = 1\n"})
        self.archive("tests (1).zip", {"tests/run-all.sh": programme("1.55.20261001.092458", bash=True),
                                       "tests/test_web_monitor.py": "x = 1\n"})
        self.archive("nginx-tools-tests.zip", {"nginx-tools-tests/run-all.sh": programme("1.56.20261001.100000", bash=True),
                                               "nginx-tools-tests/test_web_monitor.py": "x = 1\n"})
        self.outils("nginx-tools.zip", "2.37.20261001.090925")
        rc, out = self.lancer(self.dossier)
        self.assertIn("archive « tests » d'un autre programme : ignorée", out)
        self.assertNotIn("9.0.20261005", out.split("ARCHIVES À JOINDRE")[1])
        self.assertIn("ancien nom (dossier tests/)", out)
        self.assertIn("tests (1).zip est plus ancienne que", out)
        self.assertIn("nginx-tools-tests.zip  (plus récent : run-all.sh 1.56.20261001.100000)", out.split("ARCHIVES À JOINDRE")[1])
        # Installation: old copy of OUR suite in tests/ reported; the new one is compared
        inst = os.path.dirname(self.path("scripts", "x"))
        self.write("scripts/web-monitor.py", programme("2.37.20261001.090925"))
        self.write("scripts/tests/run-all.sh", programme("1.55.20261001.092458", bash=True))
        self.write("scripts/tests/test_web_monitor.py", "x = 1\n")
        rc, out = self.lancer(self.dossier, "--installed", inst, "--nginx-dir", inst)
        self.assertIn("nginx-tools-tests/run-all.sh : installé 1.55.20261001.092458 < archive 1.56.20261001.100000 — à déployer", out)
        self.assertIn("ancienne copie de la suite dans", out)
        self.write("scripts/nginx-tools-tests/run-all.sh", programme("1.56.20261001.100000", bash=True))
        rc, out = self.lancer(self.dossier, "--installed", inst, "--nginx-dir", inst)
        self.assertIn("[OK]   nginx-tools-tests/run-all.sh 1.56.20261001.100000", out)

    def test_archive_d_un_autre_programme_versions_usuelles(self):
        """1.2 : toute archive est reconnue — type = son répertoire de premier niveau ; version lue dans le manifeste
        (Odoo), le CHANGELOG (plus haute version des titres, plus récente date), package.json, pyproject.toml, VERSION, ou
        __version__ du code hors tests ; archive de tests sans version comparée à son programme (fichiers communs)."""
        journal = "# Journal\n\n## 18.0.1.6.0 — 2026-09-30\n- a\n\n## 18.0.1.7.0 — 2026-10-01\n- b\n"
        self.archive("rlq_survey_report.zip", {
            "rlq_survey_report/doc/CHANGELOG.md": journal,
            "rlq_survey_report/__manifest__.py": "{\n    'name': 'RLQ',\n    'version': '18.0.1.7.0',\n}\n",
            "rlq_survey_report/models/report_builder.py": "x = 1\n",
            "rlq_survey_report/tests/test_wizard.py": '__version__ = "9.9.9"\n'})          # test data: ignored
        self.archive("rlq_survey_report (1).zip", {
            "rlq_survey_report/__manifest__.py": "{'version': '18.0.1.6.0'}\n",
            "rlq_survey_report/models/report_builder.py": "x = 0\n"})
        self.archive("rlq_survey_report_tests.zip", {
            "rlq_survey_report_tests/README.md": "# Tests\n",
            "rlq_survey_report_tests/models/report_builder.py": "x = 1\n",
            "rlq_survey_report_tests/tests/test_wizard.py": '__version__ = "9.9.9"\n'})
        self.archive("outil-js.zip", {"outil-js/package.json": '{\n  "name": "outil",\n  "version": "3.2.1"\n}\n'})
        self.archive("outil-py.zip", {"outil-py/pyproject.toml": '[project]\nname = "x"\nversion = "0.4.0"\n',
                                      "outil-py/outil.py": '__version__ = "0.4.0"\n'})
        rc, out = self.lancer(self.dossier)
        self.assertIn("rlq_survey_report.zip — rlq_survey_report —", out)
        self.assertIn("__manifest__.py                  18.0.1.7.0  (manifeste)", out)
        self.assertIn("doc/CHANGELOG.md                 18.0.1.7.0 (2026-10-01)  (journal)", out)
        self.assertNotIn("9.9.9", out)
        self.assertIn("rlq_survey_report (1).zip est plus ancienne que", out)
        self.assertIn("version 18.0.1.6.0 < 18.0.1.7.0", out)
        self.assertIn("package.json                     3.2.1  (paquet)", out)
        self.assertIn("pyproject.toml                   0.4.0  (paquet)", out)
        self.assertIn("aucune version déclarée", out)                            # archive de tests
        self.assertIn("[OK]   rlq_survey_report_tests.zip ↔ rlq_survey_report.zip : 2 fichier(s) commun(s), tous identiques", out)
        a_joindre = out.split("ARCHIVES À JOINDRE")[1]
        self.assertIn("rlq_survey_report.zip  (version 18.0.1.7.0", a_joindre)
        self.assertIn("fichiers communs identiques à rlq_survey_report 18.0.1.7.0", a_joindre)
        self.assertNotIn("manquant(s)", a_joindre)                               # aucune de nos archives ici
        self.assertNotIn("(aucun programme versionné reconnu)", out)
        # Tests qui ne correspondent plus au programme
        self.archive("rlq_survey_report_tests.zip", {"rlq_survey_report_tests/models/report_builder.py": "x = 2\n"})
        rc, out = self.lancer(self.dossier)
        self.assertIn("1 fichier(s) commun(s) différent(s) : models/report_builder.py", out)
        self.assertEqual(rc, 1)

    def test_copie_testee_de_la_configuration_identique(self):
        """nginx-tools-tests/nginx-odoo/ ↔ nginx-odoo-config.zip : fichiers identiques (CONTEXTE, section 10, point 1)."""
        self.archive("nginx-tools-tests.zip", {"nginx-tools-tests/run-all.sh": programme("1.58.20261002.090000", bash=True),
                                               "nginx-tools-tests/nginx-odoo/README.md": "- 2026-10-01 : a\n",
                                               "nginx-tools-tests/nginx-odoo/conf.d/odoo-global.conf": "x;\n"})
        self.archive("nginx-odoo-config.zip", {"nginx-odoo/README.md": "- 2026-10-01 : a\n", "nginx-odoo/conf.d/odoo-global.conf": "y;\n"})
        rc, out = self.lancer(self.dossier)
        self.assertIn("nginx-tools-tests.zip ↔ nginx-odoo-config.zip : 1 fichier(s) commun(s) différent(s) : conf.d/odoo-global.conf", out)

    def test_version_dans_le_nom_des_archives(self):
        """1.3 / 1.4 : archives livrées avec leur version SANS la date dans le nom (nginx-tools.1.1.zip) ; version de
        l'archive nginx-tools dans doc/nginx-tools.version ; nom et contenu comparés sur MAJEUR.MINEUR ; l'ancienne forme
        complète (avec la date) reste acceptée ; installation comparée."""
        v = "1.1.20261002.100000"
        self.archive("nginx-tools.1.1.zip", {"nginx-tools/web-monitor.py": programme("2.38.20261001.143624"),
                                            "nginx-tools/doc/nginx-tools.version": v + "\n"})
        self.archive("nginx-tools-tests.1.59.zip",
                     {"nginx-tools-tests/run-all.sh": programme("1.60.20261002.100000", bash=True)})        # name != content
        self.archive("rlq_survey_report.18.0.1.90.0.zip", {"rlq_survey_report/__manifest__.py": "{'version': '18.0.1.90.0'}\n"})
        self.archive("nginx-tools.zip", {"nginx-tools/web-monitor.py": programme("2.37.20261001.090925")})  # ancien, sans version
        self.archive("nginx-tools.1.0.20261002.064915.zip", {"nginx-tools/web-monitor.py": programme("2.37.20261001.090925"),
                                                            "nginx-tools/doc/nginx-tools.version": "1.0.20261002.064915\n"})
        rc, out = self.lancer(self.dossier)
        self.assertIn("version de l’archive             1.1.20261002.100000", out)
        self.assertIn("[ATTN] le nom du fichier indique la version 1.59, le contenu 1.60.20261002.100000 "
                      "(nom attendu : nginx-tools-tests.1.60.zip)", out)
        self.assertNotIn("le nom du fichier indique la version 18.0.1.90.0", out)              # consistent
        self.assertNotIn("le nom du fichier indique la version 1.1,", out)                     # "1.1" = start of 1.1.2026...
        self.assertNotIn("le nom du fichier indique la version 1.0.20261002.064915", out)      # old full form: accepted
        self.assertIn("(nom sans version, et sans doc/nginx-tools.version : archive antérieure", out)
        a_joindre = out.split("ARCHIVES À JOINDRE")[1]
        self.assertIn(f"nginx-tools.1.1.zip  (version {v}, plus récent : web-monitor.py 2.38.20261001.143624)", a_joindre)
        self.assertEqual(rc, 1)
        # Archive name without a version for one of our types that has a version: the expected name is given, without the date
        self.archive("nginx-tools-tests.zip", {"nginx-tools-tests/run-all.sh": programme("1.61.20261003.080000", bash=True)})
        rc, out = self.lancer(os.path.join(self.dossier, "nginx-tools-tests.zip"))
        self.assertIn("(nom sans version : l'archive serait nginx-tools-tests.1.61.zip)", out)
        # Installation: version of the deployed archive
        inst = os.path.dirname(self.path("scripts", "x"))
        self.write("scripts/web-monitor.py", programme("2.38.20261001.143624"))
        self.write("scripts/doc/nginx-tools.version", "1.0.20261001.000000\n")
        rc, out = self.lancer(os.path.join(self.dossier, "nginx-tools.1.1.zip"), "--installed", inst, "--nginx-dir", inst)
        self.assertIn(f"archive nginx-tools installée : 1.0.20261001.000000, archive : {v}", out)
        self.write("scripts/doc/nginx-tools.version", v + "\n")
        rc, out = self.lancer(os.path.join(self.dossier, "nginx-tools.1.1.zip"), "--installed", inst, "--nginx-dir", inst)
        self.assertIn(f"[OK]   archive nginx-tools {v} déployée", out)

    def test_version_de_la_configuration_nginx(self):
        """1.5 : nginx-odoo-config porte sa version (fichier VERSION) et se livre sous le nom nginx-odoo-config.1.0.zip."""
        v = "1.0.20261002.093000"
        self.archive("nginx-odoo-config.1.0.zip", {"nginx-odoo/VERSION": v + "\n", "nginx-odoo/README.md": "- 2026-10-02 : a\n",
                                                   "nginx-odoo/conf.d/odoo-global.conf": "x;\n"})
        self.archive("nginx-odoo-config.2.0.zip", {"nginx-odoo/VERSION": v + "\n", "nginx-odoo/README.md": "- 2026-10-02 : a\n"})   # name != content
        rc, out = self.lancer(os.path.join(self.dossier, "nginx-odoo-config.1.0.zip"))
        self.assertIn(f"version de l’archive             {v}", out)
        self.assertIn("configuration nginx (journal)    2026-10-02 — 2 fichier(s)", out)           # VERSION n'est pas un fichier de configuration
        self.assertNotIn("le nom du fichier indique", out)
        self.assertIn(f"nginx-odoo-config.1.0.zip  (version {v}, plus récent : 2026-10-02)", out.split("ARCHIVES À JOINDRE")[1])
        rc, out = self.lancer(os.path.join(self.dossier, "nginx-odoo-config.2.0.zip"))
        self.assertIn("[ATTN] le nom du fichier indique la version 2.0, le contenu 1.0.20261002.093000 (nom attendu : nginx-odoo-config.1.0.zip)", out)
        self.assertEqual(rc, 1)

    def test_date_du_fichier_du_jour_en_vert_pour_les_versions_sans_date(self):
        """1.11 : un module Odoo (version « 18.0.1.107.0 », sans date) dont le fichier le plus récent date d'aujourd'hui voit cette date en vert ; les anciennes dates, non."""
        import datetime
        import importlib.util
        spec = importlib.util.spec_from_file_location("zip_versions_test3", self.prog)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.COLOR = True
        d = datetime.datetime.now().strftime("%Y-%m-%d")
        r = mod.colorize_versions(f"  rlq_survey_report ./x.zip  (version 18.0.1.107.0, fichier le plus récent {d} 17:28) ; ancien 2020-01-01 10:00")
        self.assertIn(f"\x1b[1;32m{d} 17:28\x1b[0m", r)
        self.assertIn(" ancien 2020-01-01 10:00", r)
        self.assertNotIn("18.0.1.107.0\x1b", r)                          # the version without a date is not colored
        self.assertEqual(mod.colorize_versions(r), r)                    # idempotent
        j = d.replace("-", "")
        v = mod.colorize_versions(f"1.5.{j}.101500 ({d})")
        self.assertEqual(v.count("\x1b[1;32m"), 2)                       # a version of the day and a date of the day, each colored once
