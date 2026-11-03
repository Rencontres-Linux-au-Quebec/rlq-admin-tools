"""apps/_theme.py 1.0, --theme N in app-log-live.py 1.161, web-monitor.py 2.87 and nginx-log-audit.sh 2.86.

The proof that "every color reads on the chosen background": for each theme 1 to 4, EVERY color code that the three programs write (read in their source and in
their style tables) is resolved, and the contrast between the text and its background (the reference background of the theme, or the explicit one) is computed
(WCAG ratio, 4.5 for the themes 1 and 2, 7 for the themes 3 and 4). A new color in a program is covered without touching this test.
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import importlib.util
import os
import re
import sys
import unittest

from helpers import EnvTest, script_path

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMMES = ("app-log-live.py", "web-monitor.py", "nginx-log-audit.sh")


def charger(chemin, nom):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


THEME = charger(os.path.join(RACINE, "apps", "_theme.py"), "theme_test_module")


def codes_des_programmes():
    """Every SGR code the programs write: literals of color_code(), of theme_sgr(), escape sequences, style defaults, and the style tables of app-log-live."""
    codes = set()
    for nom in PROGRAMMES:
        with open(os.path.join(RACINE, nom), encoding="utf-8") as f:
            source = f.read()
        for motif in (r"color_code\(\s*[\"']([0-9;]+)[\"']", r"theme_sgr\(\s*[\"']([0-9;]+)[\"']", r"style=[\"']([0-9;]+)[\"']",
                      r"\\x1b\[([0-9;]+)m", r"\"((?:[0-9]{1,3};)+[0-9]{1,3})\""):
            codes.update(re.findall(motif, source))
    live = charger(os.path.join(RACINE, "app-log-live.py"), "live_theme_test")
    for valeur in list(live.STYLES.values()) + list(live.OS_COLORS.values()) + [live.REC_STYLE, live.ORANGE]:
        codes.add(valeur)
    for numero in re.findall(r"color_code\(\s*(\d+)\s*,", open(os.path.join(RACINE, "web-monitor.py"), encoding="utf-8").read()):
        codes.add("1;" + numero)
    for numero in ("31", "32", "33", "35", "36"):                 # web-monitor: color_code("31") is written 1;31
        codes.add("1;" + numero)
    codes.update(code for code, _ in THEME.DEMO_CODES)
    return sorted(c for c in codes if c and c not in ("0", "00") and not c.startswith("0;0"))


class Contraste(unittest.TestCase):
    def test_il_y_a_des_codes_a_verifier(self):
        codes = codes_des_programmes()
        self.assertGreater(len(codes), 30, codes)
        for attendu in ("1;31", "1;33", "7;91", "7;93", "107;30", "1;97;44", "90", "36"):
            self.assertIn(attendu, codes)

    def test_chaque_couleur_se_lit_sur_le_fond_de_chaque_theme(self):
        codes = codes_des_programmes()
        for numero in (1, 2, 3, 4):
            _, _, fond, _, minimum = THEME.THEMES[numero]
            for code in codes:
                texte_code, avant, arriere = THEME.resolve(code, numero)
                with self.subTest(theme=numero, code=code, resultat=texte_code):
                    if avant is None:
                        continue                                    # no text color (bold, underline...): the terminal's own text, which the theme is chosen for
                    ratio = THEME.contrast(avant, arriere if arriere is not None else fond)
                    self.assertGreaterEqual(ratio + 1e-9, minimum, f"{code} -> {texte_code} : contraste {ratio:.2f} < {minimum}")

    def test_pas_de_video_inverse_dans_un_theme(self):
        """A reverse video depends on the colors of the terminal: in a theme it becomes an explicit text and background."""
        for numero in (1, 2, 3, 4):
            for code in ("7;35", "7;91", "7;93", "7;31", "7;90", "7;36"):
                with self.subTest(theme=numero, code=code):
                    texte, avant, arriere = THEME.resolve(code, numero)
                    self.assertNotIn("7", texte.split(";")[:1])
                    self.assertIn("48;5;", texte)
                    self.assertIn("38;5;", texte)

    def test_texte_sur_fond_explicite_a_son_propre_fond(self):
        for numero in (1, 2, 3, 4):
            for code in ("47", "100", "107;30", "30;46", "1;97;44"):
                texte, avant, arriere = THEME.resolve(code, numero)
                self.assertIsNotNone(arriere, (numero, code))
                self.assertIsNotNone(avant, (numero, code))

    def test_les_deux_themes_hauts_contrastes_sont_plus_exigeants(self):
        self.assertEqual([THEME.THEMES[n][4] for n in (1, 2, 3, 4)], [4.5, 4.5, 7.0, 7.0])
        for code in ("1;33", "36", "90", "1;92"):
            for sombre, contraste in ((1, 3), (2, 4)):
                a = THEME.resolve(code, sombre)[1]
                b = THEME.resolve(code, contraste)[1]
                fond = THEME.THEMES[sombre][2]
                self.assertGreaterEqual(THEME.contrast(b, fond), THEME.contrast(a, fond) - 1e-9, (code, sombre))

    def test_jaune_sur_fond_clair_devient_fonce_et_blanc_sur_fond_clair_noir(self):
        for numero in (2, 4):
            jaune = THEME.resolve("1;33", numero)[1]
            self.assertLess(THEME.luminance(jaune), 0.25, "yellow must be dark on a light background")
            blanc = THEME.resolve("1;97", numero)[1]
            self.assertLess(THEME.luminance(blanc), 0.25, "white text must be dark on a light background")
        for numero in (1, 3):
            bleu = THEME.resolve("34", numero)[1]
            self.assertGreater(THEME.luminance(bleu), 0.25, "blue must be light on a dark background")
            gris = THEME.resolve("90", numero)[1]
            self.assertGreater(THEME.luminance(gris), 0.25, "gray must be light on a dark background")


class Module(unittest.TestCase):
    def test_theme_0_ne_change_rien(self):
        for code in ("1;33", "7;91", "107;30", "90", "2", "", "38;5;208"):
            self.assertEqual(THEME.resolve(code, 0)[0], code)

    def test_choix_du_theme(self):
        self.assertEqual(THEME.parse_theme("3"), 3)
        self.assertEqual(THEME.parse_theme(" 0 "), 0)
        for mauvais in ("5", "-1", "a", "", "1.5", "10"):
            with self.assertRaises(ValueError):
                THEME.parse_theme(mauvais)

    def test_set_theme_exporte_pour_les_programmes_lances(self):
        ancien = os.environ.get(THEME.ENV_VARIABLE)
        try:
            THEME.set_theme("2")
            self.assertEqual(os.environ[THEME.ENV_VARIABLE], "2")
            self.assertEqual(THEME.current(), 2)
            self.assertEqual(THEME.sgr("1;33"), THEME.resolve("1;33", 2)[0])
            THEME.set_theme(0)
            self.assertEqual(THEME.sgr("1;33"), "1;33")
        finally:
            THEME._current = None
            if ancien is None:
                os.environ.pop(THEME.ENV_VARIABLE, None)
            else:
                os.environ[THEME.ENV_VARIABLE] = ancien

    def test_variable_d_environnement_invalide_donne_theme_0(self):
        ancien = os.environ.get(THEME.ENV_VARIABLE)
        try:
            os.environ[THEME.ENV_VARIABLE] = "zz"
            THEME._current = None
            self.assertEqual(THEME.current(), 0)
        finally:
            THEME._current = None
            if ancien is None:
                os.environ.pop(THEME.ENV_VARIABLE, None)
            else:
                os.environ[THEME.ENV_VARIABLE] = ancien

    def test_demo_montre_chaque_theme_sur_son_fond(self):
        for numero in (1, 2, 3, 4):
            lignes = THEME.demo_lines(numero, "fr")
            self.assertGreater(len(lignes), len(THEME.DEMO_CODES))
            self.assertIn("48;5;", "\n".join(lignes))
        self.assertEqual(len(THEME.demo_lines(0, "en")), 2)

    def test_sortie_pour_bash(self):
        sortie = THEME.bash_assignments(2)
        for variable in ("RED", "YELLOW", "GREEN", "CYAN", "MAL", "BOLD", "DIM"):
            self.assertRegex(sortie, rf"(?m)^THEME_SGR_{variable}='[0-9;]*'$")


class Programmes(EnvTest):
    def test_les_trois_programmes_proposent_theme(self):
        for nom in PROGRAMMES:
            with open(script_path(nom), encoding="utf-8") as f:
                source = f.read()
            self.assertIn("--theme", source, nom)
            self.assertIn("THEME", source, nom)
            self.assertIn("NGINX_TOOLS_THEME", source + open(script_path("apps/_theme.py"), encoding="utf-8").read(), nom)

    def test_la_cle_THEME_est_commune_a_tous_les_programmes(self):
        with open(script_path("apps/_config.py"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r'CLES_COMMUNES = \([^)]*"THEME"')
        with open(script_path("apps/_i18n.sh"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r"LANGUAGE\|VERBOSE\|DEBUG_LEVEL\|LOG_KEEP_DAYS\|ANONYMIZE\|THEME\)")

    def test_nginx_log_audit_refuse_un_theme_invalide(self):
        rc, out, err = self.run_cmd(["bash", script_path("nginx-log-audit.sh"), "prod", "--theme", "9"])
        self.assertEqual(rc, 1, out + err)
        self.assertIn("--theme attend un nombre de 0 à 4", err)

    def test_nginx_log_audit_changelog_prend_les_couleurs_du_theme(self):
        sombre = THEME.resolve("1;36", 1)[0]
        clair = THEME.resolve("1;36", 2)[0]
        self.assertNotEqual(sombre, clair)
        for numero, attendu in (("2", clair), ("1", sombre)):
            texte, _ = self.run_pty(["bash", script_path("nginx-log-audit.sh"), "--theme", numero, "--changelog"], [], keep_ansi=True)
            self.assertIn(f"\x1b[{attendu}m", texte, (numero, attendu))
        texte, _ = self.run_pty(["bash", script_path("nginx-log-audit.sh"), "--changelog"], [], keep_ansi=True)
        self.assertIn("\x1b[1;36m", texte, "theme 0: the code is unchanged")

    def test_nginx_log_audit_theme_depuis_la_configuration_et_l_environnement(self):
        """THEME in the configuration file, NGINX_TOOLS_THEME in the environment, and the command line over both."""
        dossier = os.path.join(self.d, "etc")
        os.makedirs(dossier, exist_ok=True)
        with open(os.path.join(dossier, "nginx-log-audit.conf"), "w", encoding="utf-8") as f:
            f.write("THEME=4\n")
        env = {"NGINX_TOOLS_ETC_DEFAULT": dossier}
        clair_contraste = THEME.resolve("1;36", 4)[0]
        texte, _ = self.run_pty(["bash", script_path("nginx-log-audit.sh"), "--changelog"], [], env_extra=env, keep_ansi=True)
        self.assertIn(f"\x1b[{clair_contraste}m", texte)
        texte, _ = self.run_pty(["bash", script_path("nginx-log-audit.sh"), "--theme", "1", "--changelog"], [], env_extra=env, keep_ansi=True)
        self.assertIn(f"\x1b[{THEME.resolve('1;36', 1)[0]}m", texte, "the command line wins over the configuration")
        texte, _ = self.run_pty(["bash", script_path("nginx-log-audit.sh"), "--changelog"], [], env_extra={"NGINX_TOOLS_THEME": "2"}, keep_ansi=True)
        self.assertIn(f"\x1b[{THEME.resolve('1;36', 2)[0]}m", texte, "NGINX_TOOLS_THEME applies without configuration")

    def test_app_log_live_color_code_suit_le_theme(self):
        live = charger(os.path.join(RACINE, "app-log-live.py"), "live_theme_test2")
        live.COLOR = True
        live.THEME_MODULE = None
        self.assertEqual(live.color_code("1;33", "x"), "\x1b[1;33mx\x1b[0m")
        THEME._current = None
        live.THEME_MODULE = THEME
        try:
            THEME.set_theme(2)
            self.assertEqual(live.color_code("1;33", "x"), f"\x1b[{THEME.resolve('1;33', 2)[0]}mx\x1b[0m")
            self.assertEqual(live.color_code("7;93", "x"), f"\x1b[{THEME.resolve('7;93', 2)[0]}mx\x1b[0m")
        finally:
            THEME.set_theme(0)
            THEME._current = None
            os.environ.pop(THEME.ENV_VARIABLE, None)

    def test_web_monitor_color_code_suit_le_theme(self):
        moniteur = charger(os.path.join(RACINE, "web-monitor.py"), "monitor_theme_test")
        moniteur.colors_on = lambda: True
        moniteur.THEME_MODULE = None
        self.assertEqual(moniteur.color_code("31", "x"), "\x1b[1;31mx\x1b[0m")
        moniteur.THEME_MODULE = THEME
        try:
            THEME.set_theme(2)
            self.assertEqual(moniteur.color_code("31", "x"), f"\x1b[{THEME.resolve('1;31', 2)[0]}mx\x1b[0m")
            self.assertEqual(moniteur.color_code("1", "x"), f"\x1b[{THEME.resolve('1', 2)[0]}mx\x1b[0m")
        finally:
            THEME.set_theme(0)
            THEME._current = None
            os.environ.pop(THEME.ENV_VARIABLE, None)


if __name__ == "__main__":
    unittest.main()
