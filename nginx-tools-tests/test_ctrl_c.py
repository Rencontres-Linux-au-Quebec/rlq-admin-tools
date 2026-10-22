"""Ctrl+C demande TOUJOURS confirmation avant de quitter — apps/_i18n.py (installer_confirmation_ctrl_c, programmes Python) et apps/_i18n.sh (ctrl_c_installer, programmes bash),
en français et en anglais (derrière le traducteur) : non -> le programme reprend ; oui / o / y -> arrêt ; second Ctrl+C pendant la question -> arrêt ; hors terminal -> rien."""
import os
import shutil
import unittest

ENVIRONNEMENT = "commun"   # tous les serveurs

from helpers import SCRIPTS_DIR, EnvTest

CTRL_C = b"\x03"
QUESTION_FR = b"Interrompre le programme ? [o/N]"
QUESTION_EN = b"Stop the program? [y/N]"


class ConfirmationCtrlC(EnvTest):
    def setUp(self):
        super().setUp()
        for v in ("NGINX_TOOLS_LANG", "NGINX_TOOLS_I18N", "NGINX_TOOLS_I18N_LANGUE", "NGINX_TOOLS_CTRL_C", "LANG", "LC_ALL", "LC_MESSAGES"):
            self.env.pop(v, None)
        self.racine = os.path.dirname(self.path("fake", "x"))
        shutil.copytree(os.path.join(SCRIPTS_DIR, "apps"), os.path.join(self.racine, "apps"))
        shutil.copytree(os.path.join(SCRIPTS_DIR, "lang"), os.path.join(self.racine, "lang"))
        self.py = os.path.join(self.racine, "toy.py")
        with open(self.py, "w", encoding="utf-8") as f:
            f.write('import importlib.util, os, sys, time\n'
                    'spec = importlib.util.spec_from_file_location("_i18n", os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps", "_i18n.py"))\n'
                    'm = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n'
                    'ctx = m.demarrer(os.path.dirname(os.path.abspath(__file__)), "toy", "TOY_LANG")\n'
                    'print("DEBUT", flush=True)\n'
                    'try:\n'
                    '    for i in range(80):\n'
                    '        time.sleep(0.1)\n'
                    '        if i == 3: print("MILIEU", flush=True)\n'
                    'except KeyboardInterrupt:\n'
                    '    print("INTERROMPU", flush=True); sys.exit(130)\n'
                    'print("FIN", flush=True)\n')
        self.py_question = os.path.join(self.racine, "toy_question.py")           # Ctrl+C PENDANT un input() (readline) : « can't re-enter readline » en 1.8
        with open(self.py_question, "w", encoding="utf-8") as f:
            f.write('import importlib.util, os, sys\n'
                    'spec = importlib.util.spec_from_file_location("_i18n", os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps", "_i18n.py"))\n'
                    'm = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n'
                    'ctx = m.demarrer(os.path.dirname(os.path.abspath(__file__)), "toy", "TOY_LANG")\n'
                    'try:\n'
                    '    r = ctx.input("  [t] tous   [N] aucun : ")\n'
                    '    print("REPONSE=" + r, flush=True)\n'
                    'except KeyboardInterrupt:\n'
                    '    print("INTERROMPU", flush=True); sys.exit(130)\n')
        self.sh_question = os.path.join(self.racine, "toy_question.sh")
        with open(self.sh_question, "w", encoding="utf-8") as f:
            f.write('#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                    'read -e -r -p "  [t] tous   [N] aucun : " r\necho "REPONSE=$r"\n')
        self.sh = os.path.join(self.racine, "toy.sh")
        with open(self.sh, "w", encoding="utf-8") as f:
            f.write('#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                    'echo DEBUT\nfor i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40; do sleep 0.1; done\necho FIN\n')

    def lancer(self, cmd, reponses, langue="", env=None):
        env_extra = dict(env or {})
        if langue:
            env_extra["TOY_LANG"] = langue
        texte, envoyees = self.run_pty(cmd, reponses, env_extra, timeout=30)
        return texte, envoyees

    def cas(self, cmd, question, langue, reponse, attendu_fin, mot_reprise):
        texte, _ = self.lancer(cmd, [(b"DEBUT", CTRL_C, 0.5), (question, reponse, 0.2)], langue)
        self.assertIn(question.decode(), texte)
        if attendu_fin:
            self.assertNotIn("FIN", texte)
        else:
            self.assertIn(mot_reprise, texte)
            self.assertIn("FIN", texte)
        return texte

    def test_python_non_le_programme_reprend(self):
        self.cas(["python3", self.py], QUESTION_FR, "", b"n\r", False, "Reprise.")

    def test_python_oui_arret_avec_keyboardinterrupt(self):
        texte = self.cas(["python3", self.py], QUESTION_FR, "", b"o\r", True, "")
        self.assertIn("INTERROMPU", texte)

    def test_python_second_ctrl_c_confirme(self):
        texte, _ = self.lancer(["python3", self.py], [(b"DEBUT", CTRL_C, 0.5), (QUESTION_FR, CTRL_C, 0.3)])
        self.assertIn("INTERROMPU", texte)
        self.assertNotIn("FIN", texte)

    def test_python_anglais(self):
        texte = self.cas(["python3", self.py], QUESTION_EN, "en", b"n\r", False, "Resuming.")
        self.assertNotIn("Interrompre", texte)

    def test_bash_non_le_script_reprend(self):
        self.cas(["bash", self.sh], QUESTION_FR, "", b"n\r", False, "Reprise.")

    def test_bash_oui_arret_code_130(self):
        texte = self.cas(["bash", self.sh], QUESTION_FR, "", b"oui\r", True, "")
        self.assertNotIn("FIN", texte)

    def test_bash_second_ctrl_c_confirme(self):
        texte, _ = self.lancer(["bash", self.sh], [(b"DEBUT", CTRL_C, 0.5), (QUESTION_FR, CTRL_C, 0.3)])
        self.assertNotIn("FIN", texte)

    def test_bash_anglais_derriere_le_traducteur(self):
        texte = self.cas(["bash", self.sh], QUESTION_EN, "en", b"n\r", False, "Resuming.")
        self.assertNotIn("Interrompre", texte)

    def test_bash_anglais_oui(self):
        self.cas(["bash", self.sh], QUESTION_EN, "en", b"y\r", True, "")

    def test_python_ctrl_c_pendant_une_question_sans_trace(self):
        """Ctrl+C pendant input() : pas de « can't re-enter readline » ; non -> la question reste active et sa réponse est lue ; oui -> arrêt propre."""
        texte, _ = self.lancer(["python3", self.py_question], [(b"aucun :", CTRL_C, 0.4), (QUESTION_FR, b"n\r", 0.2), (b"Reprise.", b"t\r", 0.4)])
        self.assertNotIn("Traceback", texte)
        self.assertNotIn("re-enter", texte)
        self.assertIn("REPONSE=t", texte)
        texte, _ = self.lancer(["python3", self.py_question], [(b"aucun :", CTRL_C, 0.4), (QUESTION_FR, b"o\r", 0.2)])
        self.assertNotIn("Traceback", texte)
        self.assertIn("INTERROMPU", texte)
        texte, _ = self.lancer(["python3", self.py_question], [(b"none :", CTRL_C, 0.4)], "en")      # anglais : question traduite, sans trace
        self.assertNotIn("Traceback", texte)

    def test_bash_ctrl_c_pendant_une_question_sans_erreur(self):
        texte, _ = self.lancer(["bash", self.sh_question], [(b"aucun :", CTRL_C, 0.4), (QUESTION_FR, b"n\r", 0.2), (b"Reprise.", b"t\r", 0.4)])
        self.assertNotIn("rror", texte)
        self.assertIn("REPONSE=t", texte)
        texte, _ = self.lancer(["bash", self.sh_question], [(b"aucun :", CTRL_C, 0.4), (QUESTION_FR, b"o\r", 0.2)])
        self.assertNotIn("REPONSE=", texte)
        # _i18n.sh 1.13 : un SECOND Ctrl+C pendant « Interrompre le programme ? » (après un Ctrl+C reçu pendant la question) arrête le programme — il était
        # ignoré (« ^C^C^C »), sans erreur de bash (« trap_handler: bad signal 2 »)
        texte, envoyees = self.lancer(["bash", self.sh_question], [(b"aucun :", CTRL_C, 0.4), (QUESTION_FR, CTRL_C, 0.3)])
        self.assertEqual(envoyees, 2, texte)
        self.assertNotIn("REPONSE=", texte)
        self.assertNotIn("bad signal", texte)
        self.assertNotIn("Aborting", texte)

    def test_variable_pour_desactiver_et_hors_terminal(self):
        """NGINX_TOOLS_CTRL_C=0 : comportement habituel (arrêt immédiat) ; sans terminal (tube) : aucun gestionnaire installé."""
        texte, _ = self.lancer(["bash", self.sh], [(b"DEBUT", CTRL_C, 0.5)], env={"NGINX_TOOLS_CTRL_C": "0"})
        self.assertNotIn("Interrompre", texte)
        self.assertNotIn("FIN", texte)
        rc, out, err = self.run_cmd(["python3", self.py])
        self.assertEqual((rc, out.split()[-1]), (0, "FIN"))
        self.assertNotIn("Interrompre", err)


    # --- 1.11 / 1.16 : Ctrl+C PENDANT une commande longue et entre programmes (demande répétée) --------------------------------------------------
    def ecrire(self, nom, texte):
        chemin = os.path.join(self.racine, nom)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        return chemin

    def test_bash_ctrl_c_pendant_timeout_foreground_question_immediate(self):
        """Le cas de nginx-log-audit.sh appelé par app-log-live.py : « timeout 60 journalctl … » SANS --foreground mettait la commande hors du groupe du terminal :
        Ctrl+C n'avait aucun effet avant la fin du délai. Avec --foreground : question tout de suite, et « oui » arrête."""
        sh = self.ecrire("long.sh", '#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                                    'echo DEBUT\nx=$(timeout --foreground 20 bash -c "while :; do :; done") || x=""\necho FIN\n')
        import time
        t0 = time.time()
        texte, envoyees = self.lancer(["bash", sh], [(b"DEBUT", CTRL_C, 0.5), (QUESTION_FR, b"o\r", 0.2)])
        self.assertEqual(envoyees, 2, texte)
        self.assertLess(time.time() - t0, 12)
        self.assertNotIn("FIN", texte)

    def test_bash_run_interruptible_non_puis_oui(self):
        """apps/_i18n.sh run_interruptible : la commande longue tourne en arrière-plan ; Ctrl+C -> question IMMÉDIATE ; non -> elle continue et son code est rendu ;
        oui -> elle est arrêtée avec le programme."""
        sh = self.ecrire("ri.sh", '#!/bin/bash\nset -euo pipefail\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                                  'echo DEBUT\ncode=0\nrun_interruptible bash -c "sleep 2; exit 7" > /dev/null || code=$?\necho "FIN code=$code"\n')
        texte, _ = self.lancer(["bash", sh], [(b"DEBUT", CTRL_C, 0.5), (QUESTION_FR, b"n\r", 0.2)])
        self.assertIn("Reprise.", texte)
        self.assertIn("FIN code=7", texte)
        texte, _ = self.lancer(["bash", sh], [(b"DEBUT", CTRL_C, 0.5), (QUESTION_FR, b"o\r", 0.2)])
        self.assertNotIn("FIN", texte)

    def test_bash_parent_et_enfant_une_seule_question(self):
        """ctrl_c_child : un script qui lance un autre script interactif ne repose pas la question une seconde fois quand l'enfant a répondu."""
        enfant = self.ecrire("enfant.sh", '#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                                          'echo ENFANT\nfor i in $(seq 30); do sleep 0.1; done\necho FIN-ENFANT\n')
        parent = self.ecrire("parent.sh", '#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                                          f'echo DEBUT\nctrl_c_child bash "{enfant}"\necho FIN-PARENT\n')
        texte, _ = self.lancer(["bash", parent], [(b"ENFANT", CTRL_C, 0.5), (QUESTION_FR, b"n\r", 0.2)])
        self.assertEqual(texte.count("Interrompre le programme"), 1, texte)
        self.assertIn("FIN-ENFANT", texte)
        self.assertIn("FIN-PARENT", texte)

    def test_python_parent_enfant_au_premier_plan_une_seule_question(self):
        """apps/_i18n.py foreground_child (web-monitor.py, app-log-live.py -> nginx-log-audit.sh) : seul l'enfant pose la question ; le parent continue ensuite."""
        enfant = self.ecrire("enfant2.sh", '#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer toy TOY_LANG "$0" "$@"\n'
                                           'echo ENFANT\nfor i in $(seq 30); do sleep 0.1; done\necho FIN-ENFANT\n')
        py = self.ecrire("parent.py", 'import importlib.util, os, subprocess, sys\n'
                                      'spec = importlib.util.spec_from_file_location("_i18n", os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps", "_i18n.py"))\n'
                                      'm = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n'
                                      'ctx = m.demarrer(os.path.dirname(os.path.abspath(__file__)), "toy", "TOY_LANG")\n'
                                      f'print("DEBUT", flush=True)\nm.run_foreground(["bash", "{enfant}"])\nprint("FIN-PARENT", flush=True)\n')
        texte, _ = self.lancer(["python3", py], [(b"ENFANT", CTRL_C, 0.5), (QUESTION_FR, b"n\r", 0.2)])
        self.assertEqual(texte.count("Interrompre le programme"), 1, texte)
        self.assertIn("FIN-ENFANT", texte)
        self.assertIn("FIN-PARENT", texte)
        self.assertNotIn("Traceback", texte)

    def test_aucun_timeout_sans_foreground_dans_les_programmes_bash(self):
        """Toute commande « timeout » d'un programme bash garde Ctrl+C (--foreground) : sinon Ctrl+C reste sans effet jusqu'à la fin du délai."""
        import glob
        import re
        fautes = []
        for chemin in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.sh"))) + [os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-all.sh")]:
            with open(chemin, encoding="utf-8") as f:
                lignes = f.readlines()
            for n, ligne in enumerate(lignes, 1):
                if ligne.lstrip().startswith("#") or "lancer=(timeout" in ligne:     # odoo-update-module.sh : la mise à jour passe par run_interruptible
                    continue
                if re.search(r"(?<![-\w])timeout (?!--foreground)\S", ligne):
                    fautes.append(f"{os.path.basename(chemin)}:{n}: {ligne.strip()[:100]}")
        self.assertEqual(fautes, [])


if __name__ == "__main__":
    unittest.main()
