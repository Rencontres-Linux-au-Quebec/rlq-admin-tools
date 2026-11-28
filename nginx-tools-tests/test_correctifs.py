#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# Licence: GNU Affero General Public License, version 3 or later - https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""apps/_correctifs.sh (2.130) et journal_renommer_copie (apps/_journal.sh) : les corrections opt-in de nginx-hardening.sh
(list_db = False dans odoo.conf, jail nginx-badrequests passée par nginx-gate-ban) et le suivi du journal quand une copie
sort de /etc/logrotate.d. Tout se passe dans un dossier temporaire : rien n'est lu ni écrit dans /etc."""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import SCRIPTS_DIR

ENVIRONNEMENT = "commun"

BIBLIO_CORRECTIFS = os.path.join(SCRIPTS_DIR, "apps", "_correctifs.sh")
BIBLIO_JOURNAL = os.path.join(SCRIPTS_DIR, "apps", "_journal.sh")
VERIFIEUR = os.path.join(SCRIPTS_DIR, "apps", "_odoo_conf_check.py")

JAIL_DIRECTE = """[nginx-badrequests]
enabled  = true
port     = http,https
filter   = nginx-badrequests
logpath  = /var/log/nginx/access.log
maxretry = 20
findtime = 60
bantime  = 86400
action   = iptables-multiport[name=nginx-badrequests, port="http,https", protocol=tcp]

[sshd]
enabled = true
action  = iptables-multiport[name=sshd, port="ssh", protocol=tcp]
"""


class Correctifs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-correctifs-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sauv = os.path.join(self.tmp, "correctifs")
        self.journal = os.path.join(self.tmp, "installed-files.tsv")
        self.racine = os.path.join(self.tmp, "etc")
        os.makedirs(self.racine)

    def bash(self, script, *args):
        env = dict(os.environ, NGINX_TOOLS_JOURNAL=self.journal, NGINX_TOOLS_JOURNAL_ROOTS=self.racine,
                   NGINX_TOOLS_JOURNAL_BACKUPS=os.path.join(self.tmp, "journal-backups"))
        entete = f'. "{BIBLIO_JOURNAL}"; . "{BIBLIO_CORRECTIFS}"; '
        r = subprocess.run(["bash", "-c", entete + script, "bash", *args], capture_output=True, text=True, env=env,
                           check=False)
        return r.returncode, r.stdout + r.stderr

    def ecrire(self, nom, contenu):
        chemin = os.path.join(self.tmp, nom)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)
        return chemin

    def lire(self, chemin):
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    # --- list_db ----------------------------------------------------------------------------------------------------
    def test_list_db_ajoute_quand_absent(self):
        conf = self.ecrire("odoo.conf", "[options]\nhttp_port = 8069\nproxy_mode = True\n")
        rc, out = self.bash('correctif_liste_bases_off "$1" "$2" "$3"', conf, self.sauv, VERIFIEUR)
        self.assertEqual(rc, 0, out)
        self.assertIn("list_db = False", self.lire(conf))
        self.assertIn("http_port = 8069", self.lire(conf))                       # the rest is untouched
        copies = os.listdir(self.sauv)
        self.assertEqual(len(copies), 1, copies)
        self.assertIn("list_db", self.lire(conf))

    def test_list_db_remplace_la_valeur_existante(self):
        conf = self.ecrire("odoo.conf", "[options]\nlist_db = True\nproxy_mode = True\n")
        rc, out = self.bash('correctif_liste_bases_off "$1" "$2" "$3"', conf, self.sauv, VERIFIEUR)
        self.assertEqual(rc, 0, out)
        texte = self.lire(conf)
        self.assertIn("list_db = False", texte)
        self.assertNotIn("list_db = True", texte)
        self.assertEqual(texte.count("list_db"), 1)

    def test_list_db_deja_desactive_ne_change_rien(self):
        conf = self.ecrire("odoo.conf", "[options]\nlist_db = False\n")
        rc, out = self.bash('correctif_liste_bases_off "$1" "$2" "$3"', conf, self.sauv, VERIFIEUR)
        self.assertEqual(rc, 2, out)
        self.assertFalse(os.path.exists(self.sauv))

    def test_list_db_verification_refusee_ne_remplace_rien(self):
        conf = self.ecrire("odoo.conf", "[options]\nhttp_port = 8069\n")
        rc, out = self.bash('correctif_liste_bases_off "$1" "$2" /bin/false', conf, self.sauv)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.lire(conf), "[options]\nhttp_port = 8069\n")

    # --- jail nginx-badrequests -------------------------------------------------------------------------------------
    def test_badrequests_action_remplacee_dans_la_section_seulement(self):
        jail = self.ecrire("jail.local", JAIL_DIRECTE)
        rc, out = self.bash('correctif_porte_badrequests "$1" "$2"', jail, self.sauv)
        self.assertEqual(rc, 0, out)
        texte = self.lire(jail)
        self.assertIn("action   = nginx-gate-ban[name=nginx-badrequests]", texte)
        self.assertNotIn("iptables-multiport[name=nginx-badrequests", texte)
        self.assertIn('action  = iptables-multiport[name=sshd, port="ssh", protocol=tcp]', texte)   # other jail untouched
        self.assertEqual(len(os.listdir(self.sauv)), 1)

    def test_badrequests_deja_passee_par_la_porte(self):
        jail = self.ecrire("jail.local", JAIL_DIRECTE.replace("iptables-multiport[name=nginx-badrequests, port=\"http,https\", protocol=tcp]", "nginx-gate-ban[name=nginx-badrequests]"))
        rc, out = self.bash('correctif_porte_badrequests "$1" "$2"', jail, self.sauv)
        self.assertEqual(rc, 2, out)

    def test_badrequests_section_absente(self):
        jail = self.ecrire("jail.local", "[sshd]\nenabled = true\n")
        rc, out = self.bash('correctif_porte_badrequests "$1" "$2"', jail, self.sauv)
        self.assertEqual(rc, 2, out)
        self.assertEqual(self.lire(jail), "[sshd]\nenabled = true\n")

    def test_restaurer_remet_la_copie(self):
        jail = self.ecrire("jail.local", JAIL_DIRECTE)
        rc, out = self.bash('correctif_porte_badrequests "$1" "$2"', jail, self.sauv)
        self.assertEqual(rc, 0, out)
        copie = os.path.join(self.sauv, os.listdir(self.sauv)[0])
        rc, out = self.bash('correctif_restaurer "$1" "$2"', jail, copie)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.lire(jail), JAIL_DIRECTE)

    # --- journal : une copie sortie de /etc/logrotate.d reste retrouvable ------------------------------------------
    def test_journal_suit_la_copie_deplacee(self):
        ancienne = os.path.join(self.racine, "logrotate.d-fail2ban.before-revert-20261125-190825")
        nouvelle = os.path.join(self.tmp, "backups", "fail2ban.before-revert-20261125-190825")
        autre = os.path.join(self.racine, "nginx.conf.before-revert-x")
        with open(self.journal, "w", encoding="utf-8") as f:
            f.write(f"remplacer\t{self.racine}/fail2ban\t{ancienne}\t20261125-190825\n")
            f.write(f"remplacer\t{self.racine}/nginx.conf\t{autre}\t20261125-190826\n")
        rc, out = self.bash('journal_renommer_copie "$1" "$2"', ancienne, nouvelle)
        self.assertEqual(rc, 0, out)
        lignes = self.lire(self.journal).splitlines()
        self.assertIn(f"remplacer\t{self.racine}/fail2ban\t{nouvelle}\t20261125-190825", lignes)
        self.assertIn(f"remplacer\t{self.racine}/nginx.conf\t{autre}\t20261125-190826", lignes)   # other line untouched

    def test_journal_absent_ne_fait_rien(self):
        rc, out = self.bash('journal_renommer_copie "$1" "$2"', "/a", "/b")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(self.journal))


if __name__ == "__main__":
    unittest.main()
