# -*- coding: utf-8 -*-
"""Fichier de configuration par défaut créé au premier démarrage (apps/_config.py, apps/_i18n.sh, odoo-mail-retry.py) et modèles doc/*.conf.example complets."""
import importlib.util
import os
import re
import stat
import subprocess
import unittest

from helpers import SCRIPTS_DIR, EnvTest, script_path

ENVIRONNEMENT = "commun"   # tous les serveurs


class ConfigParDefaut(EnvTest):
    def setUp(self):
        super().setUp()
        self.etc = os.path.join(self.d, "etc-modele")
        self.home = os.path.join(self.d, "home-modele")
        os.makedirs(self.etc)
        os.makedirs(self.home)
        self.env.update(NGINX_TOOLS_ETC_DEFAULT=self.etc, HOME=self.home, NGINX_TOOLS_CONFIG_CREER="1")

    def lancer(self, *args, **extra):
        env = dict(self.env, **extra)
        return subprocess.run(["python3", script_path("zip-versions.py"), "--lang", "fr", *args], capture_output=True, text=True, env=env, cwd=self.d, timeout=60)

    def test_cree_le_fichier_du_systeme_puis_ne_recree_plus(self):
        """Aucun fichier : /etc/default/PROGRAMME.conf est créé (copie du modèle, tout en commentaire) et la ligne « Configuration lue » le dit une seule fois."""
        r = self.lancer()
        chemin = os.path.join(self.etc, "zip-versions.conf")
        self.assertTrue(os.path.isfile(chemin), r.stdout + r.stderr)
        texte = open(chemin, encoding="utf-8").read()
        self.assertIn("Fichier créé automatiquement le", texte)
        self.assertIn("Modèle d’origine : doc/zip-versions.conf.example", texte)
        self.assertEqual(stat.S_IMODE(os.stat(chemin).st_mode), 0o644)
        actives = [l for l in texte.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        self.assertEqual(actives, [], "toutes les options doivent être en commentaire")
        self.assertIn(f"puis {chemin} (modifié le ", r.stdout + r.stderr)
        self.assertIn("(le dernier l'emporte) (fichier créé à l'instant", r.stdout + r.stderr)
        r2 = self.lancer()
        self.assertNotIn("créé à l'instant", r2.stdout + r2.stderr)
        self.assertEqual(open(chemin, encoding="utf-8").read(), texte)

    def test_sans_droits_sur_le_systeme_cree_le_fichier_personnel(self):
        r = self.lancer(NGINX_TOOLS_ETC_DEFAULT=os.path.join(self.d, "etc-inexistant"))
        perso = os.path.join(self.home, ".zip-versions.conf")
        self.assertTrue(os.path.isfile(perso), r.stdout + r.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(perso).st_mode), 0o600)

    def test_rien_n_est_cree_avec_help_version_config_ou_variable(self):
        for args, extra in ((["--help"], {}), (["--version"], {}), (["--changelog"], {}), (["-c", os.path.join(self.d, "x.conf")], {}), ([], {"NGINX_TOOLS_CONFIG_CREER": "0"})):
            with self.subTest(args=args, extra=extra):
                self.lancer(*args, **extra)
                self.assertEqual(os.listdir(self.etc), [])
                self.assertEqual(os.listdir(self.home), [])

    def test_un_fichier_existant_n_est_jamais_touche(self):
        perso = os.path.join(self.home, ".zip-versions.conf")
        with open(perso, "w") as f:
            f.write("# le mien\nLANGUAGE=fr\n")                                 # run-all 1.188 : une option ACTIVE (un fichier tout en commentaire suit le modèle depuis _config 1.7)
        self.lancer()
        self.assertEqual(os.listdir(self.etc), ["app-default.conf"])          # seul le fichier commun (1.3) est créé : celui du programme existe déjà (personnel)
        self.assertEqual(open(perso).read(), "# le mien\nLANGUAGE=fr\n")

    def test_bibliotheque_bash_cree_le_fichier(self):
        """apps/_i18n.sh : config_lire crée /etc/default/PROGRAMME.conf (nginx-log-audit, nginx-hardening, sync-crowdsec-blocklist, run-all)."""
        script = f'. "{SCRIPTS_DIR}/apps/_i18n.sh"; config_lire nginx-log-audit; config_afficher'
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=dict(self.env, NGINX_TOOLS_CONFIG_VUE=""), timeout=60)
        chemin = os.path.join(self.etc, "nginx-log-audit.conf")
        self.assertTrue(os.path.isfile(chemin), r.stdout + r.stderr)
        self.assertIn(f"puis {chemin} (modifié le ", r.stdout)
        self.assertIn("(le dernier l'emporte) (fichier créé à l'instant", r.stdout)
        self.assertEqual([l for l in open(chemin, encoding="utf-8").read().splitlines() if l.strip() and not l.startswith("#")], [])
        r = subprocess.run(["bash", "-c", script.replace("config_lire nginx-log-audit", "config_lire nginx-log-audit --help")], capture_output=True, text=True,
                           env=dict(self.env, NGINX_TOOLS_CONFIG_VUE=""), timeout=60)
        self.assertNotIn("créé à l'instant", r.stdout)

    def test_odoo_mail_retry_cree_le_fichier(self):
        spec = importlib.util.spec_from_file_location("odoo_mail_retry_test", script_path("odoo-mail-retry.py"))
        m = importlib.util.module_from_spec(spec)
        ancien = dict(os.environ)
        os.environ.update(NGINX_TOOLS_CONFIG_CREER="1", HOME=self.home, NGINX_TOOLS_ETC_DEFAULT=self.etc)
        try:
            spec.loader.exec_module(m)
            valeurs, fichiers, problemes = m.read_config()
        finally:
            os.environ.clear()
            os.environ.update(ancien)
        self.assertTrue(os.path.isfile(os.path.join(self.etc, "odoo-mail-retry.conf")))
        self.assertEqual((valeurs, problemes), ({}, []))


class ModelesComplets(unittest.TestCase):
    """Chaque doc/PROGRAMME.conf.example (et celui de run-all) cite TOUTES les options longues de l'aide du programme : celles qui se configurent (CLÉ=valeur) et, en fin de
    fichier, celles de la ligne de commande seulement."""
    PROGRAMMES = ("app-log-check.py", "app-log-live.py", "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "odoo-warmup.py", "web-monitor.py", "zip-versions.py", "host-perf-audit.py", "nginx-hardening.sh", "nginx-log-audit.sh",
                  "odoo-backup.sh", "odoo-update-module.sh", "sync-crowdsec-blocklist.sh")

    def test_toutes_les_options_sont_dans_le_modele(self):
        env = dict(os.environ, NGINX_TOOLS_CONFIG_CREER="0", COLUMNS="200")
        for programme in self.PROGRAMMES:
            with self.subTest(programme=programme):
                exe = ["python3", script_path(programme)] if programme.endswith(".py") else ["bash", script_path(programme)]
                aide = subprocess.run(exe + ["--help", "--lang", "fr"], capture_output=True, text=True, env=env, timeout=60).stdout
                options = set(re.findall(r"^  (?:-\w, )?(--[\w-]+)", aide, re.M)) - {"--help"}
                self.assertGreater(len(options), 5, aide)
                modele = open(script_path("doc/" + re.sub(r"\.(py|sh)$", "", programme) + ".conf.example"), encoding="utf-8").read()
                self.assertEqual(sorted(o for o in options if o not in modele), [], f"options absentes de doc/{programme}.conf.example")

    def test_cles_de_configuration_en_commentaire(self):
        """Le modèle est copié tel quel : aucune ligne active (CLÉ=valeur sans #)."""
        for programme in self.PROGRAMMES:
            with self.subTest(programme=programme):
                modele = open(script_path("doc/" + re.sub(r"\.(py|sh)$", "", programme) + ".conf.example"), encoding="utf-8").read()
                self.assertEqual([l for l in modele.splitlines() if l.strip() and not l.lstrip().startswith("#")], [])


if __name__ == "__main__":
    unittest.main()
