"""nginx-hardening.sh : la clé CDN de /etc/default/nginx-hardening.conf (ou ~/.nginx-hardening.conf) est lue.

Sans cette lecture, « CDN=cloudflare » dans le fichier de configuration était ignoré : un --update sans --cdn
remettait cdn-realip.conf à « none ». Le test reproduit la séquence du script (CDN par défaut, config_lire,
config_defaut) dans un répertoire temporaire, sans toucher à nginx ni à /etc/default.
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import subprocess
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


class CdnConfigFile(unittest.TestCase):
    def _valeur_cdn(self, contenu):
        """Exécute la séquence du script avec un fichier de configuration contenant `contenu`, renvoie CDN."""
        with tempfile.TemporaryDirectory() as tmp:
            if contenu is not None:
                with open(os.path.join(tmp, "nginx-hardening.conf"), "w", encoding="utf-8") as f:
                    f.write(contenu)
            script = (
                'set -u\n'
                f'source "{os.path.join(RACINE, "apps", "_i18n.sh")}"\n'
                'CDN="none"\n'
                'config_lire nginx-hardening\n'
                'config_defaut CDN CDN --cdn texte\n'
                'printf "%s" "$CDN"\n'
            )
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "NGINX_TOOLS_ETC_DEFAULT": tmp}
            res = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
            return res.stdout

    def test_cle_cdn_du_fichier_applique(self):
        """CDN=cloudflare dans le fichier de configuration : --update n'a pas besoin de --cdn cloudflare."""
        self.assertEqual(self._valeur_cdn("CDN=cloudflare\n"), "cloudflare")

    def test_sans_cle_cdn_reste_none(self):
        """Sans clé CDN dans le fichier, la valeur par défaut « none » est conservée."""
        self.assertEqual(self._valeur_cdn("LOG_RETENTION_MONTHS=3\n"), "none")

    def test_sans_fichier_reste_none(self):
        self.assertEqual(self._valeur_cdn(None), "none")

    def test_config_defaut_cdn_apres_config_lire(self):
        """Statique : nginx-hardening.sh lit la clé CDN après config_lire (sinon la valeur du fichier serait ignorée)."""
        script = lire("nginx-hardening.sh")
        self.assertIn("config_defaut CDN CDN --cdn texte", script)
        self.assertLess(script.index("config_lire nginx-hardening"), script.index("config_defaut CDN CDN --cdn texte"))

    def test_cdn_de_la_ligne_de_commande_ecrit_dans_l_etat(self):
        """2.73 (statique) : --cdn valide est écrit comme CDN= dans le fichier d'état, en remplaçant l'ancienne ligne."""
        script = lire("nginx-hardening.sh")
        self.assertIn('if [[ "$CDN" == none || "$CDN" == cloudflare ]]; then CDN_A_ENREGISTRER="$CDN"; fi', script)
        self.assertIn('conserve="$(printf \'%s\\n\' "$conserve" | grep -vE \'^CDN=\' || true)"', script)
        self.assertIn('echo "CDN=$CDN_A_ENREGISTRER"', script)

    def test_version_dynamique_et_a_jour(self):
        self.assertIn('readonly SCRIPT_VERSION="2.73.20261101.214534"', lire("nginx-hardening.sh"))


if __name__ == "__main__":
    unittest.main()
