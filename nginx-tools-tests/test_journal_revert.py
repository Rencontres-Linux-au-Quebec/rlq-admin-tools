#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# Licence: GNU Affero General Public License, version 3 or later - https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Journal des fichiers installés (apps/_journal.sh) : retour à la configuration de base. Tout se passe dans un dossier
temporaire ; NGINX_TOOLS_JOURNAL et NGINX_TOOLS_JOURNAL_ROOTS sont redirigés, rien n'est lu ni écrit dans /etc."""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import SCRIPTS_DIR

# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs).
ENVIRONNEMENT = "commun"

BIBLIO = os.path.join(SCRIPTS_DIR, "apps", "_journal.sh")


class JournalRevert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test-rlq-journal-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.racine = os.path.join(self.tmp, "etc-nginx")
        os.makedirs(self.racine)
        self.journal = os.path.join(self.tmp, "installed-files.tsv")

    def bash(self, script, *args):
        env = dict(os.environ, NGINX_TOOLS_JOURNAL=self.journal, NGINX_TOOLS_JOURNAL_ROOTS=self.racine)
        r = subprocess.run(["bash", "-c", f'. "{BIBLIO}"; {script}', "bash", *args], capture_output=True,
                           text=True, env=env, timeout=60)
        return r.returncode, r.stdout, r.stderr

    def ecrire(self, chemin, texte):
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)

    def lire(self, chemin):
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    def test_fichier_cree_est_retire(self):
        cree = os.path.join(self.racine, "conf.d", "odoo-global.conf")
        os.makedirs(os.path.dirname(cree))
        self.ecrire(cree, "x")
        rc, _, err = self.bash('journal_ajouter creer "$1" ""', cree)
        self.assertEqual(rc, 0, err)
        rc, out, err = self.bash("journal_restaurer")
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(cree))

    def test_fichier_remplace_est_restaure(self):
        fichier = os.path.join(self.racine, "conf.d", "bot_blocker.conf")
        copie = fichier + ".before-generic-20261125-170000"
        os.makedirs(os.path.dirname(fichier))
        self.ecrire(fichier, "ORIGINAL\n")
        self.ecrire(copie, "ORIGINAL\n")
        self.ecrire(fichier, "NOUVEAU\n")
        rc, _, err = self.bash('journal_ajouter remplacer "$1" "$2"', fichier, copie)
        self.assertEqual(rc, 0, err)
        rc, _, err = self.bash("journal_restaurer")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.lire(fichier), "ORIGINAL\n")

    def test_mode_simulation_ne_change_rien(self):
        cree = os.path.join(self.racine, "conf.d", "a.conf")
        os.makedirs(os.path.dirname(cree))
        self.ecrire(cree, "x")
        self.bash('journal_ajouter creer "$1" ""', cree)
        rc, out, _ = self.bash("journal_restaurer --dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("retirer " + cree, out)
        self.assertTrue(os.path.exists(cree))

    def test_hors_des_racines_refuse(self):
        hors = os.path.join(self.tmp, "ailleurs.conf")
        rc, _, _ = self.bash('journal_ajouter creer "$1" ""', hors)
        self.assertNotEqual(rc, 0)
        self.assertFalse(os.path.exists(self.journal))

    def test_ligne_hors_racine_jamais_restauree(self):
        # Journal écrit à la main ou altéré : une ligne hors des racines ne doit jamais toucher un fichier.
        hors = os.path.join(self.tmp, "ailleurs.conf")
        self.ecrire(hors, "ne pas supprimer")
        self.ecrire(self.journal, f"creer\t{hors}\t-\t20261125-170000\n")
        rc, out, _ = self.bash("journal_restaurer")
        self.assertNotEqual(rc, 0)
        self.assertTrue(os.path.exists(hors))

    def test_copie_absente_signalee(self):
        fichier = os.path.join(self.racine, "conf.d", "b.conf")
        os.makedirs(os.path.dirname(fichier))
        self.ecrire(self.journal, f"remplacer\t{fichier}\t{fichier}.absent\t20261125-170000\n")
        rc, out, _ = self.bash("journal_restaurer")
        self.assertNotEqual(rc, 0)
        self.assertIn("copie absente", out)

    def test_pas_de_journal_rien_a_faire(self):
        rc, out, _ = self.bash("journal_restaurer")
        self.assertEqual(rc, 0)
        self.assertIn("rien à restaurer", out)

    def test_journal_archive_pas_supprime(self):
        self.ecrire(self.journal, "")
        rc, _, err = self.bash("journal_archiver")
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(self.journal))
        archives = [n for n in os.listdir(self.tmp) if n.startswith("installed-files.tsv.reverted-")]
        self.assertEqual(len(archives), 1)


if __name__ == "__main__":
    unittest.main()
