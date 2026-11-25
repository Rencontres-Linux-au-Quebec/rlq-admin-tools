"""nginx-hardening.sh 2.128 : aucune jail fail2ban ne bannit directement.

Chaque bannissement demandé par une jail (nginx-blocked-probes, nginx-catchall) passe par l'action nginx-gate-ban,
qui appelle nginx-log-audit.sh --ban (enquete, score >= 3, liste blanche, relais CDN). Sans notifications courriel
configurees (SMTP_HOST et NOTIFY_EMAIL_TO), l'action ne fait que journaliser : aucun blocage.

Limite : pas de pare-feu reel ici. Les tests lisent le code et executent la generation de l'action (sans root).
"""
import os
import re
import subprocess
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


def fonction(s, nom):
    """Corps d'une fonction shell « nom() { ... } » (de la ligne d'en-tête à l'accolade fermante en début de ligne)."""
    debut = s.index(nom + "() {")
    fin = s.index("\n}\n", debut)
    return s[debut:fin + 3]


def generer_action():
    """Execute action_nginx_gate_ban de nginx-hardening.sh (sans rien installer)."""
    script = fonction(lire("nginx-hardening.sh"), "action_nginx_gate_ban")
    return subprocess.run(["bash", "-c", script + "\naction_nginx_gate_ban"],
                          capture_output=True, text=True, cwd=RACINE, check=True).stdout


class PorteFail2ban(unittest.TestCase):
    def test_jail_blocked_probes_passe_par_la_porte(self):
        """La jail generee ne bannit plus avec iptables-multiport : elle utilise l'action nginx-gate-ban."""
        jail = fonction(lire("nginx-hardening.sh"), "jail_blocked_probes")
        self.assertIn("action   = nginx-gate-ban[name=nginx-blocked-probes]", jail)
        self.assertNotIn("iptables-multiport", jail)

    def test_fichier_depot_identique_a_la_generation(self):
        """nginx/fail2ban/nginx-blocked-probes.jail.conf = jail_blocked_probes (les deux chemins d'installation)."""
        jail = fonction(lire("nginx-hardening.sh"), "jail_blocked_probes")
        # Texte du heredoc : entre la ligne « cat <<'EOF' » et la ligne « EOF ».
        corps = jail.split("cat <<'EOF'\n", 1)[1].split("\nEOF\n", 1)[0]
        self.assertEqual(lire("nginx/fail2ban/nginx-blocked-probes.jail.conf").strip(), corps.strip())

    def test_jail_catchall_passe_par_la_porte(self):
        """La jail catch-all du depot passe aussi par la porte, jamais par iptables direct."""
        jail = lire("nginx/fail2ban/nginx-catchall.jail.conf")
        self.assertIn("action   = nginx-gate-ban[name=nginx-catchall]", jail)
        self.assertNotIn("iptables-multiport", jail)

    def test_action_appelle_la_porte_avec_duree_de_la_jail(self):
        """Quand SMTP est configure, l'action appelle nginx-log-audit.sh --ban, sans --yes qui sauterait l'enquete,
        avec --ban-days 1 (duree de la jail, pas la duree par origine de 365 jours)."""
        action = generer_action()
        if "actionban = logger" in action:
            self.skipTest("SMTP non configure sur cette machine : le mode journal seulement est verifie plus bas")
        self.assertRegex(action, r'actionban = ".*nginx-log-audit\.sh" --ban <ip> --yes --no-prompt --ban-days 1')
        self.assertIn("--reason \"fail2ban <name>\"", action)

    def test_sans_smtp_journal_seulement(self):
        """Sans SMTP_HOST et NOTIFY_EMAIL_TO, l'action ne bannit jamais : elle journalise seulement."""
        if os.path.exists("/etc/default/app-health-check.conf"):
            self.skipTest("fichier de configuration present : le test sans SMTP ne s'applique pas")
        action = generer_action()
        self.assertIn("actionban = logger -t nginx-gate-ban", action)
        self.assertNotIn('actionban = "', action)   # aucune commande de bannissement, seulement le journal

    def test_jail_copie_remplacee_si_differente(self):
        """Un serveur installe avant 2.128 (jail differente du depot) est migre par --update, pas seulement installe."""
        s = lire("nginx-hardening.sh")
        self.assertIn('cmp -s "$F2B_SRC_DIR/$nom.jail.conf" "$jail"', s)
        self.assertIn('F2B_ACTION_FILE="/etc/fail2ban/action.d/nginx-gate-ban.conf"', s)

    def test_porte_existe_et_expose_les_options(self):
        """Les options utilisees par l'action existent dans nginx-log-audit.sh."""
        audit = lire("nginx-log-audit.sh")
        for option in ("--ban)", "--yes)", "--no-prompt)", "--ban-days)", "--reason)"):
            self.assertIn(option, audit, option)


if __name__ == "__main__":
    unittest.main()
