"""Retour arrière : chaque question tapée remet le terminal en mode ligne avec écho et effacement (ECHOE) (1.x).

Sans ECHOE, la touche d'effacement supprime le caractère mais l'écran affiche « ^H » (« d^H^H^H^H » dans nginx-hardening.sh).
Statique : toutes les lectures interactives des programmes Bash appellent tty_ligne ; les programmes Python passent par saisie()
(apps/_i18n.py) ou par leur propre lecteur en mode ligne (apps/_menu.py). Aucun programme n'est lancé ici.
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import re
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROGRAMMES_BASH = ["nginx-hardening.sh", "nginx-log-audit.sh", "odoo-update-module.sh", "admin-menu.sh", "apps/_menu.sh"]
# lecture interactive : read avec -p (invite) ou -e (readline) ; -s (mot de passe, écho coupé volontairement) exclu
LECTURE = re.compile(r"\bread (?=(?:-[a-z]+ )*-[ep]\b)")


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


class LecturesBashPreparees(unittest.TestCase):
    def test_chaque_lecture_interactive_remet_le_terminal_en_mode_ligne(self):
        for prog in PROGRAMMES_BASH:
            for n, ligne in enumerate(lire(prog).split("\n"), 1):
                if ligne.strip().startswith("#") or not LECTURE.search(ligne):
                    continue
                if re.search(r"\bread (-[a-z]+ )*-s\b", ligne):
                    continue
                with self.subTest(programme=prog, ligne=n):
                    self.assertIn("tty_ligne", ligne, ligne.strip()[:120])

    def test_tty_ligne_definie_partout(self):
        """Chaque programme a tty_ligne : par apps/_i18n.sh, ou par un repli défini après le chargement."""
        for prog in PROGRAMMES_BASH:
            with self.subTest(programme=prog):
                texte = lire(prog)
                self.assertTrue("tty_ligne() {" in texte or "_i18n.sh" in texte, prog)
                if "tty_ligne() {" not in lire("apps/_i18n.sh"):
                    self.fail("apps/_i18n.sh ne définit pas tty_ligne")

    def test_tty_ligne_active_echo_et_effacement(self):
        texte = lire("apps/_i18n.sh")
        self.assertRegex(texte, r"tty_ligne\(\) \{\n\s+\[\[ -t 0 \]\] \|\| return 0\n\s+stty icanon echo echoe icrnl")


class SaisiePython(unittest.TestCase):
    def test_saisie_definie_et_utilisee_par_le_contexte(self):
        texte = lire("apps/_i18n.py")
        self.assertIn("def saisie(invite=\"\"):", texte)
        self.assertIn("self._print, self._input = print, saisie", texte)

    def test_saisie_met_echo_et_effacement(self):
        texte = lire("apps/_i18n.py")
        self.assertIn("termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG", texte)

    def test_menu_python_a_son_lecteur_en_mode_ligne(self):
        texte = lire("apps/_menu.py")
        self.assertIn("def _saisie(invite=\"\"):", texte)
        self.assertIn("termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG", texte)
        self.assertNotRegex(texte, r"(?<![_\w])input\((?!invite)")

    def test_web_monitor_repond_par_saisie(self):
        texte = lire("web-monitor.py")
        self.assertIn("return _saisie_ligne(TR(prompt_text))", texte)
        self.assertIn('_load_module("_i18n").saisie', texte)

    def test_versions_a_jour(self):
        self.assertIn('readonly SCRIPT_VERSION="2.74.20261101.231500"', lire("nginx-hardening.sh"))
        self.assertIn('readonly SCRIPT_VERSION="2.71.20261101.231500"', lire("nginx-log-audit.sh"))
        self.assertIn('readonly SCRIPT_VERSION="1.24.20261101.231500"', lire("odoo-update-module.sh"))
        self.assertIn('readonly SCRIPT_VERSION="1.2.20261101.231500"', lire("admin-menu.sh"))
        self.assertIn('__version__ = "2.85.20261101.231500"', lire("web-monitor.py"))
        self.assertIn('__version__ = "1.22.20261101.231500"', lire("apps/_i18n.py"))


if __name__ == "__main__":
    unittest.main()
