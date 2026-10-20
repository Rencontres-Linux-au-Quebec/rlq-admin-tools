#!/usr/bin/env python3
"""Saisie interactive : effacement (^H / ^?) possible partout, nombres sans séparateur de milliers."""
import os
import re
import sys
import unittest

import helpers  # noqa: F401  (isole l'environnement)

ENVIRONNEMENT = "commun"   # tous les serveurs

SCRIPTS = os.environ.get("TEST_SCRIPTS_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(os.path.join(SCRIPTS, chemin), encoding="utf-8") as f:
        return f.read()


class TestSaisie(unittest.TestCase):
    def test_readline_importe_par_la_bibliotheque_python(self):
        self.assertRegex(lire("apps/_i18n.py"), r"(?m)^\s*import readline")

    def test_saisies_bash_avec_edition(self):
        for chemin in ("apps/_i18n.sh", "nginx-tools-tests/run-all.sh"):
            f = os.path.join(SCRIPTS, chemin)
            if not os.path.exists(f):
                continue
            for ligne in lire(chemin).splitlines():
                if re.search(r"\bread\b", ligne) and "-r" in ligne and "-p" in ligne and "<" not in ligne:
                    self.assertIn("-e", ligne.split("read", 1)[1].split()[:3], ligne)

    def test_web_monitor_sans_separateur_de_milliers(self):
        sys.path.insert(0, SCRIPTS)
        import importlib.util
        spec = importlib.util.spec_from_file_location("web_monitor_saisie", os.path.join(SCRIPTS, "web-monitor.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.fmt(3403), "3403")
        self.assertEqual(mod.fmt(1234567), "1234567")

    def test_demander_delai_gere_le_retour_arriere(self):
        self.assertRegex(lire("app-log-live.py"), r"\\x7f|\\x08|\\b")


if __name__ == "__main__":
    unittest.main()
