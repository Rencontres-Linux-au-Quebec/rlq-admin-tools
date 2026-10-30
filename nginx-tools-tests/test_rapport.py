"""apps/_rapport.py : rapport d'erreurs commun (--report-err) — classement, contexte, masquage, exécution Python, ligne de commande."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import unittest
import unittest.mock

from helpers import EnvTest, SCRIPTS_DIR

INFO = {"hote": "srv1", "fqdn": "srv1.exemple.org", "os": "Ubuntu 22.04.4 LTS", "noyau": "5.15.0", "utilisateur": "root",
        "shell": "bash 5.1.16", "python": "3.10.12", "date": "2026-09-30 12:00:00 EDT"}

ECHANTILLON = """app-health-check.py v2.15.20260930.132809
Application : Odoo (détectée automatiquement)
Configuration lue : /etc/default/app-health-check.conf
  Options : site www.exemple.org · courriel : non configuré
[OK] nginx répond
[FAIL] courriel non configuré (SMTP_HOST et NOTIFY_EMAIL_TO vides)
       voir doc/email-setup.md : choisir un relais SMTP
[FAIL] courriel non configuré (SMTP_HOST et NOTIFY_EMAIL_TO vides)
[ATTN] aucun DMARC pour exemple.org
[SKIP] Tests fonctionnels Odoo (JSON-RPC) — identifiants non configures — ignore
  [ÉCHEC] shellcheck nginx-hardening.sh : 1 signalements
      ./nginx-hardening.sh:960:61: note: Note that A && B || C is not if-then-else. [SC2015]
      FAIL: test_x (test_y.Z)
Erreurs Odoo (ERROR/CRITICAL)                                    0              40           1 895
RECOMMANDATIONS (par ordre d'importance)
  1. [HAUTE] Odoo sans limite mémoire (limit_memory_hard=0)
     Pourquoi : un worker qui s'emballe peut épuiser la RAM
     Comment  : appliquer la valeur de nginx-hardening.sh --check (étape 6)
  2. [FAIBLE] HSTS max-age=300 s seulement
     Pourquoi : trop court
  3. [MOYENNE] 343 requêtes malveillantes ont atteint Odoo
     Comment  : app-health-check.py --target local
Traceback (most recent call last):
  File "/root/scripts/web-monitor.py", line 2571, in <module>
    sys.exit(main())
  File "x.py", line 5, in f
    raise ValueError("boom")
ValueError: boom
open() "/srv/x" failed (13: Permission denied), client: 1.2.3.4
  ⚠ 3 adresses d'utilisateurs connectés bannies
    bannissement à lever : nginx-log-audit.sh --unban-check
Jails fail2ban installés, mais fail2ban n'est PAS démarré (inactive) : aucune jail n'est active.
"""


def charger(chemin=None):
    spec = importlib.util.spec_from_file_location("rapport_sous_test", chemin or os.path.join(SCRIPTS_DIR, "apps", "_rapport.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Classement(unittest.TestCase):
    def setUp(self):
        self.m = charger()
        self.c = self.m.classer(self.m.nettoyer(ECHANTILLON).splitlines())

    def test_echecs_avec_leur_detail_sans_doublon_ni_faux_positif(self):
        premiers = [e[0].strip() for e in self.c["echecs"]]
        self.assertEqual(premiers, [
            "[FAIL] courriel non configuré (SMTP_HOST et NOTIFY_EMAIL_TO vides)",     # only once despite the duplicate
            "[ÉCHEC] shellcheck nginx-hardening.sh : 1 signalements",
            'open() "/srv/x" failed (13: Permission denied), client: 1.2.3.4',
            "Jails fail2ban installés, mais fail2ban n'est PAS démarré (inactive) : aucune jail n'est active."])
        self.assertEqual([x.strip() for x in self.c["echecs"][0][1:]], ["voir doc/email-setup.md : choisir un relais SMTP"])
        detail = [x.strip() for x in self.c["echecs"][1][1:]]
        self.assertEqual(detail, ["./nginx-hardening.sh:960:61: note: Note that A && B || C is not if-then-else. [SC2015]",
                                  "FAIL: test_x (test_y.Z)"])                      # detail: never counted as one more failure
        self.assertFalse(any("Erreurs Odoo (ERROR/CRITICAL)" in e[0] for e in self.c["echecs"]))   # "Erreurs ... : 0" is not an error

    def test_avertissements_recommandations_ignores_et_trace(self):
        self.assertEqual([a[0].strip() for a in self.c["avertissements"]],
                         ["[ATTN] aucun DMARC pour exemple.org", "⚠ 3 adresses d'utilisateurs connectés bannies"])
        self.assertIn("bannissement à lever", self.c["avertissements"][1][1])
        titres = [r[0].strip() for r in self.c["recommandations"]]
        self.assertEqual(titres, ["1. [HAUTE] Odoo sans limite mémoire (limit_memory_hard=0)",
                                  "3. [MOYENNE] 343 requêtes malveillantes ont atteint Odoo"])     # LOW: not listed
        self.assertEqual([x.strip()[:10] for x in self.c["recommandations"][0][1:]], ["Pourquoi :", "Comment  :"])
        self.assertEqual(len(self.c["ignores"]), 1)
        (trace,) = self.c["tracebacks"]
        self.assertEqual(trace[0].strip(), "Traceback (most recent call last):")
        self.assertEqual(trace[-1].strip(), "ValueError: boom")
        self.assertLessEqual(len(trace), 6)                                            # start, last 4 lines, exception

    def test_recommandation_faible_n_avale_pas_la_suivante(self):
        c = self.m.classer(["  1. [FAIBLE] HSTS court", "  2. [MOYENNE] alertes par courriel non configurées", "     Comment  : suivre doc/email-setup.md"])
        self.assertEqual([r[0].strip() for r in c["recommandations"]], ["2. [MOYENNE] alertes par courriel non configurées"])
        self.assertEqual(len(c["recommandations"][0]), 2)                              # with its "Comment" line

    def test_contexte_lu_dans_la_sortie(self):
        ctx = self.m.contexte_dans_sortie(self.m.nettoyer(ECHANTILLON).splitlines())
        self.assertEqual(ctx, ["Application : Odoo (détectée automatiquement)",
                               "Configuration lue : /etc/default/app-health-check.conf",
                               "Options : site www.exemple.org · courriel : non configuré"])

    def test_etiquette_prioritaire_sur_l_expression_generique(self):
        """« [ATTN] … Permission denied » est un avertissement (étiquette explicite), pas un échec."""
        c = self.m.classer(["[ATTN] lecture impossible : Permission denied"])
        self.assertEqual((len(c["echecs"]), len(c["avertissements"])), (0, 1))

    def test_couleurs_retirees(self):
        texte = "\x1b[1;31m[FAIL]\x1b[0m base1 : AUCUNE sauvegarde\r\n"
        self.assertEqual(self.m.classer(self.m.nettoyer(texte).splitlines())["echecs"][0][0], "[FAIL] base1 : AUCUNE sauvegarde")


class Masquage(unittest.TestCase):
    def test_secrets_masques(self):
        m = charger()
        for brut, attendu in (("SMTP_PASSWORD=abc123", "SMTP_PASSWORD=***"), ("ODOO_TEST_PASSWORD = hunter2", "ODOO_TEST_PASSWORD = ***"),
                              ("mot de passe : hunter2", "mot de passe : ***"), ("Secret: deadbeef", "Secret: ***"),
                              ("api_key=XYZ token: 123", "api_key=*** token: ***"), ("bbb-conf --setsecret", "bbb-conf --setsecret"),
                              ("connexion réussie pour etienne", "connexion réussie pour etienne")):
            with self.subTest(brut=brut):
                self.assertEqual(m.masquer(brut), attendu)

    def test_le_rapport_ne_contient_aucun_secret(self):
        m = charger()
        r = m.construire_rapport("x.py", "1.0", "x.py --smtp-password=abc", "[FAIL] connexion : SMTP_PASSWORD=motdepasse refusé\n", 1, 0, "", info=INFO)
        self.assertNotIn("motdepasse", r)
        self.assertNotIn("abc", r.split("Programme")[1].split("\n")[0])
        self.assertIn("SMTP_PASSWORD=***", r)


class Rapport(unittest.TestCase):
    def test_contenu_complet(self):
        m = charger()
        with_dir = os.path.join(SCRIPTS_DIR)
        r = m.construire_rapport("app-health-check.py", "2.15.20260930.132809", "app-health-check.py --check-email-dns",
                                 ECHANTILLON, 1, 7, with_dir, info=INFO).splitlines()
        self.assertTrue(r[0].startswith("=") and "RAPPORT D'ERREURS (--report-err)" in r[0] and "copier de cette ligne" in r[0])
        self.assertEqual(r[1], "Programme : app-health-check.py v2.15.20260930.132809 — commande : app-health-check.py --check-email-dns")
        self.assertEqual(r[2], "Serveur   : srv1 (srv1.exemple.org) — Ubuntu 22.04.4 LTS — noyau 5.15.0 — utilisateur root — bash 5.1.16 — Python 3.10.12")
        self.assertEqual(r[3], "Exécution : 2026-09-30 12:00:00 EDT — durée 7 s — code de sortie 1 (ÉCHEC)")
        self.assertEqual(r[4], "Contexte  : Application : Odoo (détectée automatiquement)")
        self.assertTrue(r[5].startswith("            Configuration lue"))
        texte = "\n".join(r)
        self.assertIn("Suite     : ", texte)
        self.assertRegex(texte, r"Suite     : .*nginx-hardening\.sh \d+\.\d+\.\d{8}\.\d{6}")
        self.assertIn("Bilan     : 5 échecs, 2 avertissements, 2 recommandations à traiter, 1 vérifications ignorées — sortie de ", texte)
        self.assertIn("ÉCHECS (4) :", texte)
        self.assertIn("ERREURS PYTHON (trace d'appels) (1) :", texte)
        self.assertIn("AVERTISSEMENTS (2) :", texte)
        self.assertIn("RECOMMANDATIONS HAUTE / MOYENNE (2) :", texte)
        self.assertIn("VÉRIFICATIONS IGNORÉES (1) : [SKIP] Tests fonctionnels", texte)
        self.assertTrue(r[-1].startswith("=") and "FIN DU RAPPORT" in r[-1])

    def test_aucune_erreur_et_code_non_nul_sans_message(self):
        m = charger()
        ok = m.construire_rapport("x.py", "1.0", "x.py", "[OK] tout va bien\n", 0, 1, "", info=INFO)
        self.assertIn("Aucun échec ni avertissement détecté.", ok)
        self.assertIn("Bilan     : 0 échecs, 0 avertissements, 0 recommandations à traiter — sortie de 1 lignes", ok)
        muet = m.construire_rapport("x.py", "1.0", "x.py", "\n".join(f"ligne {i}" for i in range(30)) + "\n", 2, 1, "", info=INFO)
        self.assertIn("Code de sortie 2 sans message d'échec reconnu — dernières lignes de la sortie :", muet)
        self.assertIn("  ligne 29", muet)
        self.assertNotIn("ligne 5\n", muet)                                          # only the last 12

    def test_limite_par_categorie(self):
        m = charger()
        sortie = "".join(f"[FAIL] échec numéro {i}\n" for i in range(45))
        r = m.construire_rapport("x.py", "1.0", "x.py", sortie, 1, 1, "", info=INFO)
        self.assertIn("ÉCHECS (45) :", r)
        self.assertIn("  30. [FAIL] échec numéro 29", r)
        self.assertIn("… et 15 autres, non listés", r)

    def test_versions_de_la_suite_et_fichiers_absents(self):
        import tempfile
        m = charger()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "apps"))
            with open(os.path.join(d, "nginx-hardening.sh"), "w") as f:
                f.write('#!/bin/bash\n' + "# long en-tête\n" * 3000 + 'readonly SCRIPT_VERSION="2.15.20260930.084200"\n')
            with open(os.path.join(d, "web-monitor.py"), "w") as f:
                f.write('__version__ = "2.34.20260930.132809"\n')
            presentes, absentes = m.versions_suite(d)
        self.assertEqual(presentes, ["nginx-hardening.sh 2.15.20260930.084200", "web-monitor.py 2.34.20260930.132809"])
        self.assertIn("odoo-backup.sh", absentes)
        self.assertNotIn("run-all.sh", absentes)                                    # tests/ : normal sur un serveur sans les tests


class ExecutionPython(unittest.TestCase):
    def lancer(self, fonction, argv=("prog.py", "--report-err", "--x")):
        m = charger()
        sortie, erreur = io.StringIO(), io.StringIO()
        avant = sys.stdout
        with unittest.mock.patch.object(sys, "argv", list(argv)), contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = m.lancer(fonction, "prog.py", "1.0.20260930.000000", "")
        return code, sortie.getvalue(), erreur.getvalue(), avant

    def test_sortie_affichee_puis_rapport_et_code_conserve(self):
        def f():
            print("bonjour")
            print("[FAIL] problème signalé sur stderr", file=sys.stderr)
            return 3
        code, out, err, _ = self.lancer(f)
        self.assertEqual(code, 3)
        self.assertIn("bonjour", out)
        self.assertIn("[FAIL] problème signalé sur stderr", err)                     # still displayed on the real stream
        self.assertLess(out.index("bonjour"), out.index("RAPPORT D'ERREURS"))        # sortie du programme AVANT le rapport
        self.assertIn("commande : prog.py --x", out)                                 # --report-err n'y figure pas
        self.assertIn("1. [FAIL] problème signalé sur stderr", out)                   # stderr captured too
        self.assertIn("code de sortie 3 (ÉCHEC)", out)

    def test_exceptions_et_codes_de_sortie(self):
        def boom():
            raise ValueError("boom")
        code, out, err, _ = self.lancer(boom)
        self.assertEqual(code, 1)
        self.assertIn("ERREURS PYTHON (trace d'appels) (1) :", out)
        self.assertIn("ValueError: boom", out)
        self.assertIn("Traceback", err)
        def ctrl_c():
            raise KeyboardInterrupt
        code, out, err, _ = self.lancer(ctrl_c)
        self.assertEqual(code, 130)
        self.assertIn("Interrompu (Ctrl-C).", err)
        def sortie_message():
            sys.exit("arrêt demandé")
        code, out, err, _ = self.lancer(sortie_message)
        self.assertEqual(code, 1)
        self.assertIn("arrêt demandé", err)
        def sortie_2():
            sys.exit(2)
        self.assertEqual(self.lancer(sortie_2)[0], 2)
        self.assertEqual(self.lancer(lambda: None)[0], 0)
        self.assertEqual(self.lancer(lambda: sys.exit(None))[0], 0)

    def test_flux_restaures(self):
        m = charger()
        avant_out, avant_err = sys.stdout, sys.stderr
        with unittest.mock.patch.object(sys, "argv", ["prog.py"]), contextlib.redirect_stdout(io.StringIO()):
            apres_out = sys.stdout
            m.lancer(lambda: 0, "prog.py", "1.0", "")
            self.assertIs(sys.stdout, apres_out)
        self.assertIs(sys.stdout, avant_out)
        self.assertIs(sys.stderr, avant_err)

    def test_terminal_conserve_pour_les_couleurs(self):
        m = charger()
        class Tty(io.StringIO):
            def isatty(self):
                return True
        vu = {}
        def f():
            vu["tty"] = sys.stdout.isatty()
        with unittest.mock.patch.object(sys, "argv", ["prog.py"]), contextlib.redirect_stdout(Tty()):
            m.lancer(f, "prog.py", "1.0", "")
        self.assertTrue(vu["tty"])                                                   # le programme voit toujours un terminal


class CouleursAvecReportErr(EnvTest):
    """2.23 / _rapport 1.9 : --report-err fait passer la sortie par tee ; les couleurs doivent rester à l'écran (terminal) sans polluer le rapport."""
    def programme(self):
        return self.write("prog.sh", f'''#!/usr/bin/env bash
SCRIPT_DIR="{SCRIPTS_DIR}"
source "{SCRIPTS_DIR}/apps/_rapport.sh"
rapport_si_demande "$0" 1.0.20260101.000000 "$SCRIPT_DIR" "$@"
printf '\\033[1;31m[FAIL]\\033[0m exemple\\n'
echo "COUL=${{REPORT_ERR_COULEUR:-non}}"
''', 0o755)

    def test_couleurs_conservees_a_l_ecran_et_rapport_propre(self):
        prog = self.programme()
        out, _ = self.run_pty(["bash", prog, "--report-err"], [], env_extra={"TERM": "xterm"}, keep_ansi=True)
        avant, _, rapport = out.partition("RAPPORT D'ERREURS")
        self.assertIn("COUL=1", avant)
        self.assertIn("\x1b[1;31m[FAIL]", avant)                                    # color displayed
        self.assertNotIn("\x1b", rapport)                                           # report to copy: plain text

    def test_pas_de_couleur_si_la_sortie_n_est_pas_un_terminal_ou_no_color(self):
        prog = self.programme()
        rc, out, _ = self.run_cmd(["bash", prog, "--report-err"])
        self.assertIn("COUL=non", out)
        out, _ = self.run_pty(["bash", prog, "--report-err"], [], env_extra={"TERM": "xterm", "NO_COLOR": "1"}, keep_ansi=True)
        self.assertIn("COUL=non", out)


class LigneDeCommande(EnvTest):
    def appel(self, *args):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, "apps", "_rapport.py"), *args], capture_output=True, text=True)

    def test_rapport_depuis_un_fichier(self):
        sortie = self.write("sortie.txt", "\x1b[31m[FAIL]\x1b[0m base1 : AUCUNE sauvegarde\n[OK] autre\n")
        r = self.appel("--programme", "odoo-backup.sh", "--programme-version", "1.7.20260930.132809", "--commande", "odoo-backup.sh --status",
                       "--code", "1", "--duree", "3", "--shell", "bash 5.1.16", "--dossier", SCRIPTS_DIR, "--sortie", sortie)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Programme : odoo-backup.sh v1.7.20260930.132809 — commande : odoo-backup.sh --status", r.stdout)
        self.assertIn("durée 3 s — code de sortie 1 (ÉCHEC)", r.stdout)
        self.assertIn("bash 5.1.16", r.stdout)
        self.assertIn("1. [FAIL] base1 : AUCUNE sauvegarde", r.stdout)
        self.assertNotIn("\x1b", r.stdout)

    def test_version_changelog_et_aide_triee(self):
        r = self.appel("--version")
        self.assertRegex(r.stdout.strip(), r"^_rapport\.py version \d+\.\d+\.\d{8}\.\d{6}$")
        r = self.appel("--changelog")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"## \d+\.\d+\.\d{8}\.\d{6}")
        r = self.appel("--help")
        import re
        noms = [m.group(1).lstrip("-").lower() for m in re.finditer(r"(?m)^ {2,4}(?:-\w, )?(--[a-z0-9-]+)", r.stdout)]
        self.assertGreater(len(noms), 6)
        self.assertEqual(noms, sorted(noms), "options de l'aide hors de l'ordre alphabétique")
        self.assertIn("affiche cette aide et quitte", r.stdout)
        self.assertIn("usage : ", r.stdout)

    def test_sortie_illisible_et_obligatoire(self):
        self.assertEqual(self.appel("--sortie", "/nulle/part").returncode, 1)
        self.assertEqual(self.appel().returncode, 2)                               # --sortie requis


class Numerotation(unittest.TestCase):
    def test_recommandation_numerotee_une_seule_fois(self):
        """1.1 : « 1. 1. [MOYENNE] … » — le numéro du programme était gardé devant celui du rapport."""
        m = charger()
        sortie = ("  1. [MOYENNE] premier constat\n     Pourquoi : a\n     Comment  : b\n"
                  "  2. [HAUTE] second constat\n     Pourquoi : c\n     Comment  : d\n")
        r = m.construire_rapport("web-monitor.py", "1.0", "web-monitor.py --summary", sortie, 0, 1, "", info=INFO)
        self.assertIn("  1. [MOYENNE] premier constat", r)
        self.assertIn("  2. [HAUTE] second constat", r)
        self.assertNotIn("1. 1.", r)
        self.assertNotIn("2. 2.", r)


class DossierDeLaSuite(unittest.TestCase):
    def test_nouveau_dossier_puis_ancien(self):
        """1.3 : suite dans nginx-tools-tests/ (archive nginx-tools-tests.zip, pour ne plus écraser le tests/ d'autres
        programmes) ; l'ancien tests/run-all.sh est encore lu pendant la transition, le nouveau l'emporte."""
        import tempfile
        m = charger()
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "tests"))
            with open(os.path.join(d, "tests", "run-all.sh"), "w") as f:
                f.write('readonly SCRIPT_VERSION="1.55.20261001.092458"\n')
            presentes, _ = m.versions_suite(d)
            self.assertIn("run-all.sh 1.55.20261001.092458", presentes)
            os.makedirs(os.path.join(d, "nginx-tools-tests"))
            with open(os.path.join(d, "nginx-tools-tests", "run-all.sh"), "w") as f:
                f.write('readonly SCRIPT_VERSION="1.56.20261001.100000"\n')
            presentes, _ = m.versions_suite(d)
            self.assertIn("run-all.sh 1.56.20261001.100000", presentes)
            self.assertNotIn("run-all.sh 1.55.20261001.092458", presentes)
