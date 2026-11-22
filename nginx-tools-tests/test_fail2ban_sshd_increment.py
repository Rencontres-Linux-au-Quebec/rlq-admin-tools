#!/usr/bin/env python3
ENVIRONNEMENT = "commun"   # jail sshd: Odoo and BigBlueButton servers
# Tests of step 9d of nginx-hardening.sh (2.124): the jail sshd bans a repeat offender longer at each new ban
# (bantime.increment, up to one week), in a separate file jail.d/zz-nginx-hardening-sshd-increment.local. Case of 2026-11-21
# on bbb3: 209.99.190.186 banned 17 times by sshd in one day. The functions are extracted from the script and run with a
# fake fail2ban-client; the real fail2ban reads the file when it is installed.
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")


def fonctions(*noms):
    with open(SCRIPT, encoding="utf-8") as f:
        texte = f.read()
    morceaux = []
    for nom in noms:
        debut = texte.index(f"\n{nom}() {{") + 1
        fin = texte.index("\n}\n", debut) + 3
        morceaux.append(texte[debut:fin])
    return "\n".join(morceaux)


def executer(corps, version="Fail2Ban v0.11.2", sshd=True, check_only="0", fichier=None, euid_root=True):
    """Runs the functions of step 9d with a fake fail2ban-client in PATH; returns (completed process, file path)."""
    d = tempfile.mkdtemp(prefix="test-rlq-sshd-")
    faux = os.path.join(d, "fail2ban-client")
    with open(faux, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n"
                f'if [[ "$1" == --version ]]; then echo "{version}"; exit 0; fi\n'
                f'if [[ "$1" == status && "$2" == sshd ]]; then {"exit 0" if sshd else "exit 1"}; fi\n'
                "exit 0\n")
    os.chmod(faux, 0o755)
    fichier = fichier or os.path.join(d, "jail.d", "zz-nginx-hardening-sshd-increment.local")
    prog = ("set -uo pipefail\n"
            'run() { "$@"; }\n'
            'pass() { echo "[OK] $1"; }\nwarn() { echo "[ATTN] $1"; }\n'
            'sans_objet() { echo "[--] $1"; }\nsans_root_verif() { echo "[ATTN] $1"; }\n'
            f'CHECK_ONLY={check_only}\nNEED_FAIL2BAN_RESTART=0\nF2B_SSHD_INCREMENT_FILE="{fichier}"\n'
            + fonctions("f2b_sshd_increment_local", "f2b_version_ok", "verifier_sshd_increment") + "\n" + corps)
    env = dict(os.environ, PATH=d + os.pathsep + os.environ.get("PATH", ""), TMPDIR=d)
    return subprocess.run(["bash", "-c", prog], capture_output=True, text=True, env=env), fichier


class JailSshdRecidive(unittest.TestCase):
    def test_contenu_limite_a_la_jail_sshd(self):
        r, _ = executer("f2b_sshd_increment_local")
        self.assertEqual(r.returncode, 0, r.stderr)
        sections = re.findall(r"(?m)^\[([^\]]+)\]", r.stdout)
        self.assertEqual(sections, ["sshd"], "seule la jail sshd est touchée (jamais [DEFAULT] : les jails nginx-* gardent leur durée)")
        self.assertRegex(r.stdout, r"(?m)^bantime\.increment = true$")
        self.assertRegex(r.stdout, r"(?m)^bantime\.maxtime = 1w$")
        self.assertRegex(r.stdout, r"(?m)^bantime\.overalljails = false$")
        self.assertNotRegex(r.stdout, r"(?m)^(bantime|maxretry|findtime|ignoreip|enabled)\s*=", "ni la durée de base, ni les seuils, ni la liste blanche")

    def test_version_de_fail2ban(self):
        for version, attendu in (("Fail2Ban v0.11.2", 0), ("Fail2Ban v1.0.2", 0), ("Fail2Ban v1.1.0", 0), ("Fail2Ban v0.10.2", 1), ("", 1)):
            with self.subTest(version=version):
                r, _ = executer("f2b_version_ok", version=version)
                self.assertEqual(r.returncode, attendu, r.stdout + r.stderr)

    def test_update_ecrit_le_fichier_puis_ok_sans_changement(self):
        r, fichier = executer('verifier_sshd_increment; echo "restart=$NEED_FAIL2BAN_RESTART"')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("restart=1", r.stdout)
        self.assertTrue(os.path.isfile(fichier))
        r2, _ = executer('verifier_sshd_increment; echo "restart=$NEED_FAIL2BAN_RESTART"', fichier=fichier)
        self.assertIn("[OK] Jail sshd : chaque nouveau bannissement", r2.stdout)
        self.assertIn("restart=0", r2.stdout, "fichier déjà à jour : pas de rechargement de fail2ban")

    def test_check_seul_ne_modifie_rien(self):
        r, fichier = executer('verifier_sshd_increment; echo "restart=$NEED_FAIL2BAN_RESTART"', check_only="1")
        self.assertIn("[ATTN] Jail sshd", r.stdout)
        self.assertIn("restart=0", r.stdout)
        self.assertFalse(os.path.exists(fichier))

    def test_sans_jail_sshd_ou_fail2ban_ancien_rien_n_est_ecrit(self):
        for options in ({"sshd": False}, {"version": "Fail2Ban v0.10.5"}):
            with self.subTest(**options):
                r, fichier = executer("verifier_sshd_increment", **options)
                self.assertIn("[--]", r.stdout)
                self.assertFalse(os.path.exists(fichier))

    @unittest.skipUnless(shutil.which("fail2ban-client"), "fail2ban absent (installé sur les serveurs : test réel là-bas)")
    def test_vrai_fail2ban_lit_le_fichier(self):
        r, _ = executer("f2b_sshd_increment_local")
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree("/etc/fail2ban", os.path.join(d, "fail2ban"), dirs_exist_ok=True)
            with open(os.path.join(d, "fail2ban", "jail.d", "zz-test-sshd-increment.local"), "w", encoding="utf-8") as f:
                f.write(r.stdout)
            t = subprocess.run(["fail2ban-client", "-c", os.path.join(d, "fail2ban"), "-t"], capture_output=True, text=True)
            self.assertEqual(t.returncode, 0, t.stdout + t.stderr)


if __name__ == "__main__":
    unittest.main()
