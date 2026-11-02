"""nginx-log-audit.sh 2.69 : aucun bannissement sans verification. --yes ne saute jamais l'enquete ni le verdict ;
--ban-sqli n'accepte pas --yes et ne bannit plus en lot.

Limite : les tests lisent le code (pas de pare-feu reel dans l'environnement de test). Le test fonctionnel du garde-fou
(refus sans preuve, meme avec --yes) a ete fait avec un faux iptables ; le chemin « exception BANNIR » exige un terminal.
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def script():
    with open(os.path.join(RACINE, "nginx-log-audit.sh"), encoding="utf-8") as f:
        return f.read()


def bloc_ban(s):
    debut = s.index('if [[ -n "$BAN_IP" ]]; then')
    fin = s.index("\nfi\n", debut)
    return s[debut:fin]


class BanGate(unittest.TestCase):
    def test_preuves_toujours_verifiees(self):
        """preuves_ip et l'enquete ne sont plus sautees par --yes."""
        b = bloc_ban(script())
        self.assertIn('    preuves_ip "$BAN_IP"', b)
        self.assertNotIn('[[ "$ASSUME_YES" != "1" ]] && preuves_ip', b)
        self.assertNotIn('if [[ "$ASSUME_YES" != "1" ]]; then\n        echo "Enquête détaillée', b)

    def test_refus_si_verdict_non_justifie(self):
        """Sans verdict « justifie », le programme refuse (exit 1) si aucune exception n'est possible."""
        b = bloc_ban(script())
        self.assertIn('if [[ "$PREUVES_VERDICT" != "justifie" && "$BAN_RECOMMANDE" != "1" ]]; then', b)
        self.assertIn('grep_q "Score [0-9]/7 : bannissement recommandé"', b)
        self.assertRegex(b, r'Refusé\. Pour une exception[^\n]*\n\s*exit 1')

    def test_exception_exige_raison_terminal_et_mot_BANNIR(self):
        b = bloc_ban(script())
        self.assertIn('if [[ -z "$BAN_REASON" ]]; then', b)
        self.assertIn('if [[ ! -t 0 ]]; then', b)
        self.assertIn('if [[ "$confirmation_exception" != "BANNIR" ]]; then', b)
        self.assertIn('BAN_OVERRIDE=1', b)
        self.assertIn('[[ "$BAN_OVERRIDE" == "1" ]] && BAN_REASON="EXCEPTION', script())

    def test_yes_ne_contourne_pas_la_confirmation_d_exception(self):
        """Avec une exception, la question « Confirmer [o/N] » n'est pas reposee : la saisie de BANNIR la remplace."""
        self.assertIn('if [[ "$ASSUME_YES" != "1" && "$BAN_OVERRIDE" != "1" ]]; then', bloc_ban(script()))

    def test_verdict_des_preuves_inclut_les_injections_sql(self):
        """Une injection SQL dans le journal du site est une preuve pour le bannissement."""
        s = script()
        self.assertIn('n_sqli=$(printf \'%s\\n\' "$site" | grep -Eic -- "$SQLI_RE" || true)', s)
        self.assertRegex(s, r'\(\( n_sqli > 0 \)\) && pour\+=')

    def test_ban_sqli_sans_yes_ni_question_en_lot(self):
        s = script()
        self.assertNotIn('Bannir ces adresses au pare-feu ?', s)
        self.assertIn("n'accepte pas --yes", s)
        self.assertIn('"$SELF_PATH" --ban "$ip" --reason "$why"', s)
        self.assertNotIn('--ban "$ip" --yes --reason "$why"', s)

    def test_version_dynamique(self):
        self.assertIn('readonly SCRIPT_VERSION="2.69.20261101.204354"', script())


if __name__ == "__main__":
    unittest.main()
