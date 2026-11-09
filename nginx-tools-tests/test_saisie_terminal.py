"""Retour arrière : chaque question tapée remet le terminal en mode ligne avec écho et effacement (ECHOE) (1.x) ; 2026-11-09 : ^H ET ^? effacent partout.

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

    def test_saisie_a_son_editeur_de_ligne(self):
        """2026-11-09 (apps/_i18n.py 1.24) : le mode ligne du noyau ne connaît qu'une touche d'effacement ; la réponse est éditée par editer_ligne."""
        texte = lire("apps/_i18n.py")
        self.assertIn("EFFACEMENTS = (0x08, 0x7f)", texte)
        self.assertIn("ligne = editer_ligne(fd)", texte)

    def test_menu_python_passe_par_saisie(self):
        texte = lire("apps/_menu.py")
        self.assertIn("def _saisie(invite=\"\"):", texte)
        self.assertIn("return module.saisie(invite)", texte)

    def test_web_monitor_repond_par_saisie(self):
        texte = lire("web-monitor.py")
        self.assertIn("return _saisie_ligne(TR(prompt_text))", texte)
        self.assertIn('_load_module("_i18n").saisie', texte)

    def test_lectures_bash_par_readline(self):
        """2026-11-09 : chaque question des programmes Bash est lue par readline (read -e) : ^H ET ^? effacent, quel que soit stty erase."""
        for prog in PROGRAMMES_BASH:
            for n, ligne in enumerate(lire(prog).split("\n"), 1):
                if ligne.strip().startswith("#") or not LECTURE.search(ligne) or re.search(r"\bread (-[a-z]+ )*-s\b", ligne):
                    continue
                with self.subTest(programme=prog, ligne=n):
                    self.assertRegex(ligne, r"\bread (-[a-z]+ )*-e\b", ligne.strip()[:120])
        self.assertIn('tty_ligne; IFS= read -e -r -t "$3" -p "$1" reponse', lire("odoo-update-module.sh"))


class RetourArriereDansUnTerminal(unittest.TestCase):
    """2026-11-09 : dans un vrai pseudo-terminal réglé avec stty erase ^?, ^H (envoyé par PuTTY et certains clients ssh) ET ^? effacent :
    l'écran ne montre jamais « ^H » et la réponse ne garde aucun caractère d'effacement."""

    def lancer(self, argv, touches, attente=b"? "):
        import pty
        import select
        import time
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(RACINE)
            os.execvp(argv[0], argv)
        sortie = b""

        def lire_pendant(secondes, jusqua=None):
            nonlocal sortie
            fin = time.time() + secondes
            while time.time() < fin:
                if jusqua is not None and jusqua in sortie:
                    return
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    try:
                        sortie += os.read(fd, 4096)
                    except OSError:
                        return
        lire_pendant(10, attente)
        for octet in touches:
            os.write(fd, bytes([octet]))
            lire_pendant(0.05)
        lire_pendant(10, b"VAL=")
        lire_pendant(0.3)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        os.close(fd)
        return sortie

    def verifier(self, sortie, attendu):
        self.assertIn(f"VAL=[{attendu}]".encode(), sortie, sortie)
        self.assertNotIn(b"^H", sortie, sortie)
        self.assertNotIn(b"^?", sortie, sortie)

    def test_saisie_python(self):
        code = ("import sys; sys.path.insert(0, 'apps'); import _i18n; import os; os.system('stty erase ^?'); "
                "print('VAL=[' + _i18n.saisie('Q? ') + ']')")
        for touches, attendu in ((b"3\x08\x084\r", "4"), (b"35\x7f4\r", "34"), (b"ab\x1b[Dc\r", "abc"), (b"xyz\x15ok\r", "ok")):
            with self.subTest(touches=touches):
                self.verifier(self.lancer(["python3", "-c", code], touches), attendu)

    def test_question_de_odoo_update_module(self):
        script = ("stty erase '^?'; . apps/_i18n.sh; eval \"$(sed -n '/^question_reponse() {/,/^}/p' odoo-update-module.sh)\"; "
                  "v=$(question_reponse 'Attente ? [60] ' 60 10); echo \"VAL=[$v]\"")
        for touches, attendu in ((b"3\x08\x084\r", "4"), (b"35\x7f4\r", "34"), (b"\r", "60")):
            with self.subTest(touches=touches):
                self.verifier(self.lancer(["bash", "-c", script], touches), attendu)

    def test_question_ctrl_c_bash(self):
        script = "stty erase '^?'; . apps/_i18n.sh; printf 'Q? '; lire_ligne_editee r; echo \"VAL=[$r]\""
        self.verifier(self.lancer(["bash", "-c", script], b"o\x08n\x7fy\r"), "y")

    def test_appliquer_effacements(self):
        import subprocess
        r = subprocess.run(["bash", "-c", ". apps/_i18n.sh; printf '[%s]' \"$(appliquer_effacements $'ab\\bc\\x7f\\x7fz')\""],
                           cwd=RACINE, capture_output=True, text=True)
        self.assertEqual(r.stdout, "[z]")


if __name__ == "__main__":
    unittest.main()
