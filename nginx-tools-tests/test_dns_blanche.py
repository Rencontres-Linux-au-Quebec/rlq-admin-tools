"""Noms DNS dans la liste blanche (adresses dynamiques) : les lecteurs les reconnaissent sans les écrire comme adresses,
nginx-hardening.sh --dns-refresh les résout, ne change l'état que si une adresse change, et garde la dernière adresse connue
quand la résolution échoue. Résolveur simulé (NGINX_TOOLS_GETENT) : aucun accès réseau."""
import os
import re
import stat
import subprocess
import sys
import textwrap
import importlib.util

from helpers import EnvTest, SCRIPTS_DIR, script_path

LISTE = """203.0.113.10        # Maison (IP fixe)
odoo-etienne.example.net  # Étienne (DNS dynamique)
2001:db8::1         # v6
"""

GETENT = """#!/bin/bash
f="$FAKE_DNS_DIR/$2"
[[ -f "$f" ]] && while read -r ip; do printf '%s STREAM %s\\n' "$ip" "$2"; done < "$f"
exit 0
"""


def module():
    spec = importlib.util.spec_from_file_location("_listes", script_path("apps/_listes.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fonctions_dns(dossier):
    """Copie des fonctions DNS et de generer_equipe de nginx-hardening.sh (sans exécuter le programme)."""
    with open(script_path("nginx-hardening.sh"), encoding="utf-8") as f:
        texte = f.read()
    debut = texte.index("dns_etat() {")
    fin = texte.index("generer_equipe() {")
    fin = texte.index("\n}\n", fin) + 3
    chemin = os.path.join(dossier, "dns-fonctions.sh")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(texte[debut:fin])
    return chemin


class DnsBlanche(EnvTest):
    def setUp(self):
        super().setUp()
        self.liste = self.write("blanche.conf", LISTE)
        self.etat = os.path.join(self.d, "etat", "dns.tsv")
        self.dns = os.path.join(self.d, "dns")
        os.makedirs(self.dns)
        self.getent = self.write("getent", GETENT)
        os.chmod(self.getent, os.stat(self.getent).st_mode | stat.S_IXUSR)

    def bash(self, commande, **env):
        e = dict(os.environ, NGINX_TOOLS_WHITE_LIST=self.liste, NGINX_TOOLS_IP_LOCATION=self.write("lieux.conf", ""),
                 NGINX_TOOLS_DNS_STATE=self.etat, NGINX_TOOLS_GETENT=self.getent, FAKE_DNS_DIR=self.dns, SCRIPT_DIR=SCRIPTS_DIR)
        e.update(env)
        script = (f'set -u\nwarn() {{ echo "WARN $1"; }}; pass() {{ echo "PASS $1"; }}; CHECK_ONLY=0\n'
                  f'. "{os.path.join(SCRIPTS_DIR, "apps", "_listes.sh")}"\n. "{fonctions_dns(self.d)}"\n{commande}')
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_lecteur_python_ignore_le_nom_sans_erreur(self):
        L = module().charger(os.path.join(SCRIPTS_DIR, "apps"), {"NGINX_TOOLS_WHITE_LIST": self.liste, "NGINX_TOOLS_IP_LOCATION": self.write("l.conf", "")})
        self.assertEqual(sorted(str(e.reseau) for e in L.blanche), ["2001:db8::1/128", "203.0.113.10/32"])
        self.assertEqual(L.noms, ["odoo-etienne.example.net"])
        self.assertEqual(L.problemes, [])

    def test_bash_meme_liste_de_noms_que_python(self):
        self.assertEqual(self.bash("listes_noms_dns").split(), ["odoo-etienne.example.net"])
        self.assertEqual(self.bash("listes_blanche | listes_valides | cut -d $'\\037' -f1").split(), ["203.0.113.10", "2001:db8::1"])

    def test_resolution_changement_et_repli(self):
        with open(os.path.join(self.dns, "odoo-etienne.example.net"), "w") as f:
            f.write("198.51.100.7\n")
        self.assertIn("CHANGED", self.bash("dns_rafraichir && echo CHANGED || echo UNCHANGED"))
        self.assertIn("198.51.100.7", self.bash("generer_equipe allow"))
        self.assertIn("UNCHANGED", self.bash("dns_rafraichir && echo CHANGED || echo UNCHANGED"))  # même adresse : rien à faire
        with open(os.path.join(self.dns, "odoo-etienne.example.net"), "w") as f:
            f.write("198.51.100.99\n")
        self.assertIn("CHANGED", self.bash("dns_rafraichir && echo CHANGED || echo UNCHANGED"))   # IP changée : nouvel état
        self.assertIn("allow 198.51.100.99;", self.bash("generer_equipe allow"))
        os.remove(os.path.join(self.dns, "odoo-etienne.example.net"))
        sortie = self.bash("dns_rafraichir || true")                                              # panne DNS
        self.assertIn("non résolu — dernière adresse connue conservée (198.51.100.99)", sortie)
        self.assertIn("allow 198.51.100.99;", self.bash("generer_equipe allow"))                  # la dernière IP reste autorisée

    def test_check_n_ecrit_rien(self):
        with open(os.path.join(self.dns, "odoo-etienne.example.net"), "w") as f:
            f.write("198.51.100.7\n")
        self.bash("CHECK_ONLY=1; dns_rafraichir || true", CHECK_ONLY="1")
        self.assertFalse(os.path.exists(self.etat))

    def test_option_dns_refresh_dans_l_aide(self):
        with open(script_path("nginx-hardening.sh"), encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("--dns-refresh", texte)
        self.assertRegex(texte, r"\n  --dns-refresh\s+")
        self.assertIn("DNS_RAFRAICHIR=1", texte)
