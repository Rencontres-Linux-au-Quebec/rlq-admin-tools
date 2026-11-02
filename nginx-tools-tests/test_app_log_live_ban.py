"""app-log-live.py : aucun bannissement en lot, jamais de --yes, une adresse à la fois sur un terminal (1.148).

Chaque bannissement passe par « nginx-log-audit.sh --ban IP » au premier plan : son enquête et sa porte décident,
le mot BANNIR est demandé à la main si l'enquête ne recommande pas le bannissement. Statique : le programme n'est pas lancé.
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import re
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


class BanUneAUneAppLogLive(unittest.TestCase):
    def setUp(self):
        self.source = lire("app-log-live.py")

    def test_aucun_yes_dans_les_appels_de_bannissement(self):
        """Ni le bannissement groupé (touche b) ni la question sur une adresse ne passent par --yes."""
        self.assertNotIn('"--yes"', self.source)
        self.assertNotIn("'--yes'", self.source)

    def test_plus_d_option_tout_bannir(self):
        """La question de la touche b ne propose plus « [y] toutes » : une par une seulement."""
        self.assertNotIn("[y] all", self.source)
        self.assertIn("Ban now, one by one", self.source)

    def test_bannissement_refuse_sans_terminal(self):
        """Sans terminal, la touche b n'annonce aucun bannissement."""
        self.assertIn("if keys is None or not sys.stdin.isatty():", self.source)

    def test_chaque_bannissement_au_premier_plan_avec_son_enquete(self):
        """Chaque appel « nginx-log-audit.sh --ban IP » est lancé au premier plan (subprocess.run), avec sa justification."""
        appels = re.findall(r'subprocess\.run\(\["bash", nla, "--ban", ip\]', self.source)
        self.assertEqual(len(appels), 2, "une fois dans propose_ban, une fois dans ban")
        self.assertEqual(self.source.count('run_captured(["bash", nla, "--ban"'), 0)

    def test_reponses_tapees_en_mode_ligne(self):
        """1.149 : la réponse à la question de la touche b passe par saisie() (écho et effacement), pas par input() nu."""
        self.assertIn("I18N_MODULE.saisie(prompt_text)", self.source)

    def test_version_dynamique_et_a_jour(self):
        """1.151 : le test ne fige plus un numéro de version (il vérifie seulement le format MAJEUR.MINEUR.AAAAMMJJ.HHMMSS)."""
        self.assertRegex(self.source, r'__version__ = "\d+\.\d+\.\d{8}\.\d{6}"')


if __name__ == "__main__":
    unittest.main()
