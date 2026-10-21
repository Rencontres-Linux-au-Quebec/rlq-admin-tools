# -*- coding: utf-8 -*-
"""Fichier de configuration COMMUN à tous les programmes (app-default.conf : LANGUAGE, VERBOSE, DEBUG_LEVEL) et sauvegarde des réglages d'app-log-live (touche C)."""
import importlib.util
import os
import stat
import subprocess
import unittest
from unittest import mock

from helpers import EnvTest, script_path

ENVIRONNEMENT = "commun"   # tous les serveurs


def load(nom_fichier, name, env):
    with mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(name, script_path(nom_fichier))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class FichierCommun(EnvTest):
    def setUp(self):
        super().setUp()
        self.etc = os.path.join(self.d, "etc")
        self.home = os.path.join(self.d, "home")
        os.makedirs(self.etc)
        os.makedirs(self.home)
        self.env.update(NGINX_TOOLS_ETC_DEFAULT=self.etc, HOME=self.home, NGINX_TOOLS_CONFIG_CREER="0")

    def write_out(self, name, text, folder=None):
        with open(os.path.join(folder or self.etc, name), "w", encoding="utf-8") as f:
            f.write(text)

    def lire_py(self, program_name="prog", explicite=None):
        with mock.patch.dict(os.environ, self.env):
            os.environ.pop("NGINX_TOOLS_DEBUG_LEVEL", None)
            module = load("apps/_config.py", "cfg_test", self.env)
            res = module.lire(program_name, explicite)
            return res + (os.environ.get("NGINX_TOOLS_DEBUG_LEVEL"),)

    def lire_bash(self, program_name="prog", *args):
        code = (f'SCRIPT_DIR="{script_path(".")}"; . "$SCRIPT_DIR/apps/_i18n.sh"; config_lire {program_name} {" ".join(args)}; '
                'echo "V=${CFG[VERBOSE]:-} L=${CFG[LANGUAGE]:-} D=${CFG[DAYS]:-} N=${NGINX_TOOLS_DEBUG_LEVEL:-} F=${CFG_FICHIERS[*]:-}"')
        r = subprocess.run(["bash", "-c", code], capture_output=True, text=True, env=dict(self.env), timeout=30)
        return r.stdout.strip().splitlines()[-1]

    def test_python_commun_lu_d_abord_le_programme_l_emporte(self):
        self.write_out("app-default.conf", "LANGUAGE=en\nVERBOSE=oui\nDAYS=3\n")
        self.write_out("prog.conf", "LANGUAGE=fr\n")
        cfg, files_read, _ = self.lire_py()
        self.assertEqual(T(cfg["LANGUAGE"]), "fr")
        self.assertEqual(T(cfg["VERBOSE"]), "oui")
        self.assertNotIn("DAYS", T(cfg))                                           # le fichier commun ne définit que trois clés
        self.assertEqual([os.path.basename(f) for f in files_read], ["app-default.conf", "prog.conf"])

    def test_python_personnel_commun_apres_systeme_commun(self):
        self.write_out("app-default.conf", "LANGUAGE=en\n")
        self.write_out(".app-default.conf", "LANGUAGE=fr\n", self.home)
        cfg, files_read, _ = self.lire_py()
        self.assertEqual(T(cfg["LANGUAGE"]), "fr")
        self.assertEqual(len(files_read), 2)

    def test_python_config_explicite_ignore_le_commun(self):
        self.write_out("app-default.conf", "LANGUAGE=en\nVERBOSE=oui\n")
        autre = os.path.join(self.d, "autre.conf")
        self.write_out("autre.conf", "DAYS=5\n", self.d)
        cfg, files_read, _ = self.lire_py(explicite=autre)
        self.assertEqual(files_read, [autre])
        self.assertNotIn("VERBOSE", T(cfg))
        self.assertNotIn("LANGUAGE", T(cfg))

    def test_python_niveau_de_debug_active_verbose(self):
        self.write_out("app-default.conf", "DEBUG_LEVEL=2\n")
        cfg, _, env_niveau = self.lire_py()
        self.assertEqual(T(cfg["VERBOSE"]), "oui")
        self.assertEqual(T(env_niveau), "2")
        self.write_out("prog.conf", "VERBOSE=non\n")                              # VERBOSE écrit quelque part : il l'emporte
        cfg, _, _ = self.lire_py()
        self.assertEqual(T(cfg["VERBOSE"]), "non")

    def test_bash_meme_regle(self):
        self.write_out("app-default.conf", "LANGUAGE=en\nVERBOSE=non\nDAYS=3\nDEBUG_LEVEL=2\n")
        self.write_out("prog.conf", "LANGUAGE=fr\n")
        output = self.lire_bash()
        self.assertIn("V=non", T(output))                                          # VERBOSE écrit : DEBUG_LEVEL ne le force pas
        self.assertIn("L=fr", T(output))
        self.assertIn("D= ", T(output))                                            # clé non commune ignorée
        self.assertIn("N=2", T(output))
        self.assertRegex(T(output), r"F=\S*app-default\.conf \S*prog\.conf")

    def test_bash_debug_level_donne_verbose(self):
        self.write_out("app-default.conf", "DEBUG_LEVEL=1\n")
        self.assertIn("V=oui", T(self.lire_bash()))

    def test_bash_config_explicite_ignore_le_commun(self):
        self.write_out("app-default.conf", "VERBOSE=oui\n")
        self.write_out("autre.conf", "DAYS=5\n", self.d)
        output = self.lire_bash("prog", "-c", os.path.join(self.d, "autre.conf"))
        self.assertIn("V= ", T(output))

    def test_odoo_mail_retry_et_warmup_lisent_le_commun(self):
        self.write_out("app-default.conf", "VERBOSE=oui\nLANGUAGE=en\nBATCH=9\n")
        self.write_out("odoo-warmup.conf", "WAIT=7\n")
        for file_path, name in (("odoo-mail-retry.py", "mr"), ("odoo-warmup.py", "wu")):
            with self.subTest(program_name=file_path):
                module = load(file_path, name, self.env)
                with mock.patch.dict(os.environ, self.env):
                    values, files_read, problems = module.read_config()
                self.assertIs(values.get("VERBOSE"), True)
                self.assertEqual(T(values.get("LANGUAGE")), "en")
                self.assertNotIn("BATCH", T(values))                              # clé du programme dans le fichier commun : ignorée, sans avertissement
                self.assertEqual(problems, [])
                self.assertTrue(files_read[0].endswith("app-default.conf"))

    def test_odoo_warmup_debug_level_dans_le_commun(self):
        self.write_out("app-default.conf", "DEBUG_LEVEL=3\n")
        module = load("odoo-warmup.py", "wu2", self.env)
        with mock.patch.dict(os.environ, self.env):
            os.environ.pop("NGINX_TOOLS_DEBUG_LEVEL", None)
            values, _, _ = module.read_config()
            self.assertIs(values.get("VERBOSE"), True)
            self.assertEqual(T(os.environ["NGINX_TOOLS_DEBUG_LEVEL"]), "3")

    def test_modele_documente_et_en_commentaire(self):
        with open(script_path("doc/app-default.conf.example"), encoding="utf-8") as f:
            text = f.read()
        for key_value in ("LANGUAGE", "VERBOSE", "DEBUG_LEVEL"):
            self.assertIn(f"#{key_value}=", T(text))
        self.assertEqual([l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")], [])


class SauvegardeDesReglages(EnvTest):
    def live(self):
        return load("app-log-live.py", "live_sv", self.env)

    def options(self, live, **modif):
        o = {"health": 30.0, "keep_ip": True, "highlight_words": ["a", "b"], "level": 9, "minimal": False, "modules_sort": ("name", False, False), "not_found": False}
        o.update(modif)
        return o

    def test_valeurs_et_changements(self):
        live = self.live()
        start_state = live.config_values(self.options(live), False)
        self.assertEqual(start_state["HIDE_IP"], "no")
        self.assertEqual(start_state["HIGHLIGHT"], "a,b")
        after = live.config_values(self.options(live, keep_ip=False, modules_sort=("date", True, True), highlight_words=[]), True)
        self.assertEqual(live.config_changes(after, start_state), {"HIDE_IP": "yes", "HIGHLIGHT": "none", "MODULES_CUSTOM": "yes", "MODULES_SORT": "-date", "VERBOSE": "yes"})
        self.assertEqual(live.config_changes(start_state, start_state), {})
        # les valeurs écrites se relisent avec les lecteurs du programme
        self.assertEqual(live.read_modules_sort("-date")[:2], ("date", True))
        self.assertEqual(live.read_highlight("aucun"), [])

    def test_ecrire_remplace_active_ou_ajoute_en_gardant_le_reste(self):
        live = self.live()
        path = os.path.join(self.d, "app-log-live.conf")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# mon commentaire\nHIDE_IP=non\n#MIN=non\n# VERBOSE=non\nAUTRE=garde\n")
        os.chmod(path, 0o600)
        n = live.write_config(path, {"HIDE_IP": "oui", "MIN": "oui", "VERBOSE": "oui", "LEVEL": "5", "HIGHLIGHT": "x y , z#"})
        self.assertEqual(n, 5)
        lines = open(path, encoding="utf-8").read().splitlines()
        self.assertEqual(lines[:5], ["# mon commentaire", "HIDE_IP=oui", "MIN=oui", "VERBOSE=oui", "AUTRE=garde"])
        self.assertIn("LEVEL=5", T(lines))
        self.assertIn('HIGHLIGHT="x y , z#"', T(lines))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)         # droits gardés
        self.assertEqual([f for f in os.listdir(self.d) if ".tmp" in f], [])

    def test_ecrire_cree_depuis_le_modele_avec_droits_644(self):
        live = self.live()
        path = os.path.join(self.d, "neuf.conf")
        live.write_config(path, {"VERBOSE": "oui"})
        text = open(path, encoding="utf-8").read()
        self.assertIn("VERBOSE=oui", T(text.splitlines()))
        self.assertNotIn("#VERBOSE=non", T(text))                                # la ligne commentée du modèle est activée, pas dupliquée
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)

    def test_ecriture_impossible_leve_oserror(self):
        live = self.live()
        with self.assertRaises(OSError):
            live.write_config(os.path.join(self.d, "absent", "x.conf"), {"VERBOSE": "oui"})

    def test_chemin_systeme_suit_la_variable_des_tests(self):
        self.env["NGINX_TOOLS_ETC_DEFAULT"] = "/tmp/xyz"
        with mock.patch.dict(os.environ, self.env):
            self.assertEqual(T(self.live().system_config_path()), "/tmp/xyz/app-log-live.conf")

    def test_touche_c_dans_le_menu(self):
        live = self.live()
        self.assertEqual(T(live.MENU_KEYS[b"C"]), "save")


if __name__ == "__main__":
    unittest.main()


_LIVE_TR = None


def T(texte):
    """Texte renvoyé directement par une fonction du programme (source anglaise) -> même texte traduit en français, comme à l'écran."""
    global _LIVE_TR
    if _LIVE_TR is None:
        spec = importlib.util.spec_from_file_location("live_tr", script_path("app-log-live.py"))
        _LIVE_TR = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_LIVE_TR)
    if not isinstance(texte, str):
        texte = "\n".join(str(x) for x in texte)
    return _LIVE_TR.TR(texte)



class AncienNomPersonnel(EnvTest):
    """2026-10-20 : le fichier personnel est ~/.PROGRAMME.conf (plus .cfg). Un ancien ~/.PROGRAMME.cfg seul est RENOMMÉ (contenu et droits gardés, un avis) ;
    les deux présents : le .conf est lu, l'ancien est IGNORÉ et signalé (jamais fusionné ni supprimé) ; renommage impossible : l'ancien est lu tel quel.
    Même règle et mêmes messages en Python (apps/_config.py migrer_ancien) et en bash (apps/_i18n.sh config_migrer_ancien)."""
    def setUp(self):
        super().setUp()
        self.etc = os.path.join(self.d, "etc")
        self.home = os.path.join(self.d, "home")
        os.makedirs(self.etc)
        os.makedirs(self.home)
        self.env.update(NGINX_TOOLS_ETC_DEFAULT=self.etc, HOME=self.home, NGINX_TOOLS_CONFIG_CREER="0", NGINX_TOOLS_LANG="fr")
        self.env.pop("NGINX_TOOLS_CONFIG_SIGNALES", None)
        self.ancien = os.path.join(self.home, ".prog.cfg")
        self.nouveau = os.path.join(self.home, ".prog.conf")

    def ecrire(self, chemin, texte, mode=0o600):
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        os.chmod(chemin, mode)

    @staticmethod
    def contenu(chemin):
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    def lire_py(self):
        """(configuration, fichiers lus, sortie d'erreur) : apps/_config.py lire() dans un processus à part (stderr réel)."""
        code = ("import sys, json, importlib.util\n"
                f"spec = importlib.util.spec_from_file_location('c', {script_path('apps/_config.py')!r}); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                "cfg, lus = m.lire('prog'); cfg2, lus2 = m.lire('prog'); print(json.dumps([cfg, lus]))\n")
        r = subprocess.run(["python3", "-I", "-c", code], capture_output=True, text=True, env=dict(self.env), timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        cfg, lus = json.loads(r.stdout)
        return cfg, lus, r.stderr

    def lire_bash(self):
        code = (f'SCRIPT_DIR="{script_path(".")}"; . "$SCRIPT_DIR/apps/_i18n.sh"; config_lire prog; config_lire prog; '
                'echo "D=${CFG[DAYS]:-} F=${CFG_FICHIERS[*]:-}"')
        r = subprocess.run(["bash", "-c", code], capture_output=True, text=True, env=dict(self.env), timeout=30)
        return r.stdout.strip().splitlines()[-1], r.stderr

    def test_ancien_seul_renomme(self):
        for langage in ("python", "bash"):
            with self.subTest(langage=langage):
                for f in (self.ancien, self.nouveau):
                    if os.path.exists(f):
                        os.remove(f)
                self.ecrire(self.ancien, "DAYS=4\n")
                if langage == "python":
                    cfg, lus, err = self.lire_py()
                    self.assertEqual(cfg.get("DAYS"), "4")
                    self.assertEqual(lus, [self.nouveau])
                else:
                    sortie, err = self.lire_bash()
                    self.assertEqual(sortie, f"D=4 F={self.nouveau}")
                self.assertFalse(os.path.exists(self.ancien))
                self.assertEqual(self.contenu(self.nouveau), "DAYS=4\n")
                self.assertEqual(stat.S_IMODE(os.stat(self.nouveau).st_mode), 0o600)                 # droits gardés (fichier personnel : souvent secret)
                avis = f"Configuration : ancien fichier {self.ancien} renommé en {self.nouveau} (les fichiers personnels se terminent maintenant par .conf)"
                self.assertEqual(err.count(avis), 1, err)                                           # lu deux fois : un seul avis

    def test_les_deux_presents_conf_lu_ancien_ignore(self):
        for langage in ("python", "bash"):
            with self.subTest(langage=langage):
                self.ecrire(self.ancien, "DAYS=4\n")
                self.ecrire(self.nouveau, "DAYS=9\n")
                if langage == "python":
                    cfg, lus, err = self.lire_py()
                    self.assertEqual((cfg.get("DAYS"), lus), ("9", [self.nouveau]))
                else:
                    sortie, err = self.lire_bash()
                    self.assertEqual(sortie, f"D=9 F={self.nouveau}")
                avis = f"Configuration : ancien fichier {self.ancien} IGNORÉ ({self.nouveau} existe et l'emporte) — reporter ses réglages dans {self.nouveau}, puis le supprimer"
                self.assertEqual(err.count(avis), 1, err)
                self.assertEqual(self.contenu(self.ancien), "DAYS=4\n")                              # jamais modifié ni supprimé

    @unittest.skipIf(os.geteuid() == 0, "root renomme même dans un dossier sans droit d'écriture")
    def test_renommage_impossible_ancien_lu_tel_quel(self):
        for langage in ("python", "bash"):
            with self.subTest(langage=langage):
                self.ecrire(self.ancien, "DAYS=4\n")
                os.chmod(self.home, 0o500)
                try:
                    if langage == "python":
                        cfg, lus, err = self.lire_py()
                        self.assertEqual((cfg.get("DAYS"), lus), ("4", [self.ancien]))
                    else:
                        sortie, err = self.lire_bash()
                        self.assertEqual(sortie, f"D=4 F={self.ancien}")
                finally:
                    os.chmod(self.home, 0o700)
                self.assertIn(f"Configuration : impossible de renommer {self.ancien} (", err)
                self.assertIn(f") — l'ancien fichier est lu tel quel au lieu de {self.nouveau}", err)
                self.assertEqual(err.count("impossible de renommer"), 1, err)

    def test_avis_traduit_en_anglais(self):
        self.ecrire(self.ancien, "DAYS=4\n")
        self.env["NGINX_TOOLS_LANG"] = "en"
        cfg, lus, err = self.lire_py()
        self.assertIn(f"Configuration: legacy file {self.ancien} renamed to {self.nouveau} (personal files now end with .conf)", err)

    def test_commun_ancien_nom_aussi(self):
        """~/.app-default.cfg (fichier commun) suit la même règle."""
        self.ecrire(os.path.join(self.home, ".app-default.cfg"), "LANGUAGE=fr\n")
        cfg, lus, err = self.lire_py()
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".app-default.conf")))
        self.assertIn(os.path.join(self.home, ".app-default.conf"), lus)
