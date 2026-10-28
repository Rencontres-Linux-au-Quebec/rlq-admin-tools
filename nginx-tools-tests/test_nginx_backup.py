#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # sauvegarde et --rollback de nginx-hardening.sh (nginx et fail2ban), testés sur des dossiers temporaires
# Tests of the backups of nginx-hardening.sh (2.59): archive before --update, pruning, restore, and undo when "nginx -t" refuses.
# The functions are extracted from the script; the roots are temporary folders, never /etc.
import os
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
FONCTIONS = ("sauvegarde_elaguer", "sauvegarde_creer", "archive_extraire", "archive_appliquer")


def extraire(nom):
    texte = open(SCRIPT, encoding="utf-8").read()
    debut = texte.index(f"\n{nom}() {{") + 1
    fin = texte.index("\n}\n", debut) + 3
    return texte[debut:fin]


def bash(corps, env):
    prog = "set -euo pipefail\n" + "\n".join(extraire(n) for n in FONCTIONS) + "\n" + corps
    return subprocess.run(["bash", "-c", prog], capture_output=True, text=True, env=env)


class Sauvegardes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.nginx = os.path.join(self.tmp, "etc", "nginx")
        self.f2b = os.path.join(self.tmp, "etc", "fail2ban")
        os.makedirs(self.nginx)
        os.makedirs(self.f2b)
        self.sauv = os.path.join(self.tmp, "backups")
        self.env = dict(os.environ, ARCHIVE_DIR=self.sauv, BACKUP_KEEP="2", SCRIPT_VERSION="test",
                        ROOTS_NGINX=self.nginx, ROOTS_F2B=self.f2b)
        self.roots = 'BACKUP_ROOTS=("$ROOTS_NGINX" "$ROOTS_F2B")\n'

    def ecrire(self, chemin, texte):
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)

    def lire(self, chemin):
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    def test_archive_keeps_only_the_newest(self):
        self.ecrire(os.path.join(self.nginx, "nginx.conf"), "A\n")
        for i in range(3):
            r = bash(self.roots + f'sauvegarde_creer test{i} >/dev/null\nsleep 0.01\n', self.env)
            self.assertEqual(r.returncode, 0, r.stderr)
        archives = sorted(f for f in os.listdir(self.sauv) if f.endswith(".tar.gz"))
        self.assertEqual(len(archives), 2)
        self.assertTrue(all(os.path.exists(os.path.join(self.sauv, a + ".txt")) for a in archives))
        self.assertTrue(archives[-1].endswith("-test2.tar.gz"))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.sauv, archives[0])).st_mode), 0o600)

    def test_restore_puts_back_content_and_removes_new_files(self):
        self.ecrire(os.path.join(self.nginx, "nginx.conf"), "A\n")
        self.ecrire(os.path.join(self.f2b, "jail.local"), "jail A\n")
        r = bash(self.roots + 'sauvegarde_creer avant\n', self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        archive = r.stdout.strip()
        # the state changes after the backup
        self.ecrire(os.path.join(self.nginx, "nginx.conf"), "B\n")
        self.ecrire(os.path.join(self.nginx, "nouveau.conf"), "nouveau\n")
        tmp = tempfile.mkdtemp()
        r = bash(self.roots + f'archive_extraire "{archive}" "{tmp}"\narchive_appliquer "{tmp}"\n', self.env)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.lire(os.path.join(self.nginx, "nginx.conf")), "A\n")
        self.assertFalse(os.path.exists(os.path.join(self.nginx, "nouveau.conf")))
        self.assertEqual(self.lire(os.path.join(self.f2b, "jail.local")), "jail A\n")
        # no leftover copy of the replaced folders
        self.assertEqual([d for d in os.listdir(os.path.dirname(self.nginx)) if "rollback-old" in d], [])

    def test_restore_is_undone_when_nginx_test_fails(self):
        self.ecrire(os.path.join(self.nginx, "nginx.conf"), "A\n")
        r = bash(self.roots + 'sauvegarde_creer avant\n', self.env)
        archive = r.stdout.strip()
        self.ecrire(os.path.join(self.nginx, "nginx.conf"), "B\n")
        # a fake "nginx" that refuses the configuration
        fake = os.path.join(self.tmp, "bin")
        os.makedirs(fake)
        with open(os.path.join(fake, "nginx"), "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(fake, "nginx"), 0o755)
        env = dict(self.env, PATH=fake + os.pathsep + self.env["PATH"])
        tmp = tempfile.mkdtemp()
        r = bash(self.roots + f'archive_extraire "{archive}" "{tmp}"\nif archive_appliquer "{tmp}"; then echo OK; else echo REFUS; fi\n', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REFUS", r.stdout)
        self.assertEqual(self.lire(os.path.join(self.nginx, "nginx.conf")), "B\n")
        self.assertEqual([d for d in os.listdir(os.path.dirname(self.nginx)) if "rollback-old" in d], [])


if __name__ == "__main__":
    unittest.main()
