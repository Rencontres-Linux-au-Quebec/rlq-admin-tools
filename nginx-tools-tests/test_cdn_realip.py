"""nginx-hardening.sh --cdn cloudflare : plages publiees par Cloudflare, generation de cdn-realip.conf, include dans odoo-global.conf.

Limite : le test n'execute pas nginx-hardening.sh de bout en bout (nginx, systemd). Il verifie la liste des plages, la
fonction generer_cdn extraite du script (sortie reelle) et l'include. Le test de bout en bout se fait sur un serveur de test.
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import ipaddress
import os
import re
import subprocess
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


class CdnRealIp(unittest.TestCase):
    def test_plages_cloudflare_valides(self):
        """Chaque ligne utile de nginx/cdn/cloudflare-ips.txt est un CIDR IPv4 ou IPv6 valide (et il y en a une vingtaine)."""
        plages = [l.strip() for l in lire("nginx/cdn/cloudflare-ips.txt").splitlines() if l.strip() and not l.startswith("#")]
        for p in plages:
            ipaddress.ip_network(p)   # leve ValueError si invalide
        self.assertGreaterEqual(len(plages), 20)
        self.assertIn("104.16.0.0/12", plages)   # bloc CLOUDFLARENET (RDAP, enquete du 2026-11-01)
        self.assertTrue(any(ipaddress.ip_address("104.28.221.220") in ipaddress.ip_network(p) for p in plages))

    def test_generer_cdn_cloudflare(self):
        """La fonction generer_cdn du script produit un set_real_ip_from par plage, puis CF-Connecting-IP."""
        script = lire("nginx-hardening.sh")
        m = re.search(r"^generer_cdn\(\) \{.*?^\}", script, re.S | re.M)
        self.assertIsNotNone(m, "fonction generer_cdn absente")
        commande = m.group(0) + '\nCDN=cloudflare\ngenerer_cdn\n'
        sortie = subprocess.run(["bash", "-c", commande], capture_output=True, text=True,
                                env={"SCRIPT_DIR": RACINE, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}).stdout
        self.assertEqual(sortie.count("set_real_ip_from "), len(
            [l for l in lire("nginx/cdn/cloudflare-ips.txt").splitlines() if l.strip() and not l.startswith("#")]))
        self.assertIn("real_ip_header CF-Connecting-IP;", sortie)
        self.assertIn("real_ip_recursive on;", sortie)

    def test_generer_cdn_aucun(self):
        """Sans CDN, le fichier ne contient que des commentaires : aucune directive real_ip (aucun changement de comportement)."""
        script = lire("nginx-hardening.sh")
        m = re.search(r"^generer_cdn\(\) \{.*?^\}", script, re.S | re.M)
        commande = m.group(0) + '\nCDN=none\ngenerer_cdn\n'
        sortie = subprocess.run(["bash", "-c", commande], capture_output=True, text=True,
                                env={"SCRIPT_DIR": RACINE, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}).stdout
        self.assertNotIn("real_ip", sortie)
        self.assertTrue(all(l.startswith("#") for l in sortie.splitlines() if l.strip()))

    def test_include_dans_odoo_global(self):
        """odoo-global.conf inclut cdn-realip.conf une seule fois (contexte http)."""
        self.assertEqual(lire("nginx/conf.d/odoo-global.conf").count("include /etc/nginx/snippets/cdn-realip.conf;"), 1)

    def test_fichier_liste_dans_les_fragments_generes(self):
        """Le fichier est cree vide par fragments_generes_assurer : nginx -t ne refuse jamais la configuration a cause de lui."""
        self.assertRegex(lire("nginx-hardening.sh"), r"for f in [^;]*cdn-realip\.conf; do")

    def test_option_cdn_documentee_et_lue(self):
        """L'option --cdn est lue, documentee dans l'aide et dans l'en-tete, et valeur inconnue refusee."""
        script = lire("nginx-hardening.sh")
        self.assertIn('--cdn) CDN="${2:-}"', script)                 # 2.73: suite sur plusieurs lignes (CDN_A_ENREGISTRER)
        self.assertIn('shift 2 ;;', script)
        self.assertIn("--cdn NOM", script)
        self.assertIn('[[ "$CDN" != "none" && "$CDN" != "cloudflare" ]]', script)


if __name__ == "__main__":
    unittest.main()
