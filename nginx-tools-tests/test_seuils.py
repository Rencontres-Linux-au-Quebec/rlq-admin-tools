#!/usr/bin/env python3
"""Tests de apps/_seuils.py (seuils communs à web-monitor.py et app-log-live.py) et de leur branchement dans les deux programmes."""
import importlib.util
import os
import tempfile
import unittest

ENVIRONNEMENT = "commun"
RACINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def charger_module():
    spec = importlib.util.spec_from_file_location("_seuils", os.path.join(RACINE, "apps", "_seuils.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Seuils(unittest.TestCase):
    def setUp(self):
        self.m = charger_module()
        self.d = tempfile.mkdtemp(prefix="test-rlq-seuils-")

    def ecrire(self, texte):
        chemin = os.path.join(self.d, "seuils.conf")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        return chemin

    def test_valeurs_par_defaut(self):
        valeurs, lus, avis = self.m.charger(fichiers=())
        self.assertEqual(valeurs, {"BURST_PAGES": 15, "BURST_WINDOW_S": 10, "CONNECTIONS_PCT": 80.0, "PROBE_404": 5, "REPEAT_MIN": 2})
        self.assertEqual((lus, avis), ([], []))

    def test_fichier_modifie_une_valeur(self):
        chemin = self.ecrire("# commentaire\nBURST_PAGES=20   \nPROBE_404='7'\n")
        valeurs, lus, avis = self.m.charger(fichiers=(chemin,))
        self.assertEqual((valeurs["BURST_PAGES"], valeurs["PROBE_404"], valeurs["REPEAT_MIN"]), (20, 7, 2))
        self.assertEqual(lus, [chemin])
        self.assertEqual(avis, [])

    def test_le_dernier_fichier_lu_gagne(self):
        premier = self.ecrire("BURST_WINDOW_S=30\n")
        second = os.path.join(self.d, "second.conf")
        with open(second, "w", encoding="utf-8") as f:
            f.write("BURST_WINDOW_S=5\n")
        valeurs, _, _ = self.m.charger(fichiers=(premier, second))
        self.assertEqual(valeurs["BURST_WINDOW_S"], 5)

    def test_valeurs_invalides_ignorees_avec_avis(self):
        chemin = self.ecrire("CONNECTIONS_PCT=150\nBURST_PAGES=1\nREPEAT_MIN=abc\nINCONNUE=3\n")
        valeurs, _, avis = self.m.charger(fichiers=(chemin,))
        self.assertEqual(valeurs["CONNECTIONS_PCT"], 80.0)
        self.assertEqual(valeurs["BURST_PAGES"], 15)
        self.assertEqual(valeurs["REPEAT_MIN"], 2)
        self.assertEqual(len(avis), 4)

    def test_zero_accepte_pour_le_pourcentage(self):
        chemin = self.ecrire("CONNECTIONS_PCT=0\n")
        valeurs, _, avis = self.m.charger(fichiers=(chemin,))
        self.assertEqual((valeurs["CONNECTIONS_PCT"], avis), (0.0, []))

    def test_fichier_absent_ou_illisible(self):
        valeurs, lus, avis = self.m.charger(fichiers=(os.path.join(self.d, "absent.conf"),))
        self.assertEqual((valeurs["PROBE_404"], lus, avis), (5, [], []))


class Branchement(unittest.TestCase):
    """web-monitor.py et app-log-live.py lisent les seuils communs : plus de valeur écrite en dur à côté."""

    def lire(self, nom):
        with open(os.path.join(RACINE, nom), encoding="utf-8") as f:
            return f.read()

    def test_web_monitor_lit_les_seuils_communs(self):
        src = self.lire("web-monitor.py")
        self.assertIn("charger_seuils_communs()", src)
        self.assertNotIn("\nBURST_PAGES = 15\n", src)

    def test_app_log_live_lit_les_seuils_communs(self):
        src = self.lire("app-log-live.py")
        for cle in ("CONNECTIONS_PCT", "PROBE_404", "REPEAT_MIN"):
            self.assertIn(f'seuil_commun("{cle}"', src)


if __name__ == "__main__":
    unittest.main()
