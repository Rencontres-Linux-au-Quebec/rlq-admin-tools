#!/usr/bin/env python3
ENVIRONNEMENT = "commun"   # option of nginx-hardening.sh, Odoo and BigBlueButton servers
# Tests of nginx-hardening.sh 2.125: --update --yes applies without a question the two steps that asked for a confirmation
# (0f, generic nginx configuration; 9b bis, filter nginx-sqli), so that host-perf-audit.py --guest-run (no terminal) can
# apply them. Case of 2026-11-21: run from Proxmox, both steps said "Pas de terminal : ... non modifié" on odoo18 and
# odoo-dev, and the fixes of the bans stayed inactive. Step 9b bis is extracted from the script and run with a fake
# fail2ban-client; step 0f is checked on the code (it needs nginx).
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")
TEXTE = open(SCRIPT, encoding="utf-8").read()
FILTRE = ('[Definition]\nfailregex = ^<HOST> .*"[A-Z]+ [^"]*(?:UNION%%20SELECT|0x[0-9a-fA-F]+)[^"]* HTTP/[0-9.]+"\n'
          "ignoreregex =\n")


def fonction(nom):
    debut = TEXTE.index(f"\n{nom}() {{") + 1
    return TEXTE[debut:TEXTE.index("\n}\n", debut) + 3]


def etape_9b_bis(yes, check_only="0", reload_ok=True):
    """Runs step 9b bis (no terminal: stdin is not a tty) on a copy of the filter; returns (output, filter after, files)."""
    d = tempfile.mkdtemp(prefix="test-rlq-yes-")
    os.makedirs(os.path.join(d, "filter.d"))
    filtre = os.path.join(d, "filter.d", "nginx-sqli.conf")
    with open(filtre, "w", encoding="utf-8") as f:
        f.write(FILTRE)
    faux = os.path.join(d, "fail2ban-client")
    with open(faux, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n" + ('exit 0\n' if reload_ok else '[[ "$1" == reload ]] && exit 1\nexit 0\n'))
    os.chmod(faux, 0o755)
    debut = TEXTE.index('echo "--- 9b bis)')
    bloc = TEXTE[debut:TEXTE.index("# --- 9c)", debut)].replace("/etc/fail2ban/filter.d/", d + "/filter.d/")
    variables = "\n".join(re.findall(r"(?m)^F2B_SQLI_HEX_(?:OLD|NEW)=.*$", TEXTE))
    prog = ("set -uo pipefail\n"
            'pass() { echo "[OK] $1"; }\nwarn() { echo "[ATTN] $1"; }\nfail() { echo "[FAIL] $1"; }\n'
            'sans_objet() { echo "[--] $1"; }\ntty_ligne() { :; }\n'
            f'APP_NAME=odoo\nF2B_SQLI_JAIL=nginx-sqli\nCHECK_ONLY={check_only}\nROLLBACK_YES={1 if yes else 0}\n'
            + variables + "\n" + fonction("f2b_sqli_hex_fix") + "\n" + bloc)
    env = dict(os.environ, PATH=d + os.pathsep + os.environ.get("PATH", ""), TMPDIR=d)
    r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    with open(filtre, encoding="utf-8") as f:
        apres = f.read()
    return r.stdout + r.stderr, apres, os.listdir(os.path.join(d, "filter.d"))


class UpdateYes(unittest.TestCase):
    def test_sans_yes_ni_terminal_rien_n_est_modifie(self):
        sortie, apres, _ = etape_9b_bis(yes=False)
        self.assertIn("Pas de terminal", sortie)
        self.assertIn("--update --yes", sortie, "le message doit dire comment appliquer sans terminal")
        self.assertEqual(apres, FILTRE)

    def test_yes_applique_sans_question_avec_sauvegarde(self):
        sortie, apres, fichiers = etape_9b_bis(yes=True)
        self.assertIn("--yes : changement appliqué sans question", sortie)
        self.assertIn("[OK] Jail nginx-sqli : filtre corrigé", sortie)
        self.assertIn("(?<![0-9A-Za-z])0x[0-9a-fA-F]+", apres)
        self.assertTrue(any(f.startswith("nginx-sqli.conf.before-hex-") for f in fichiers), "sauvegarde attendue")

    def test_yes_et_fail2ban_refuse_retour_au_filtre_d_origine(self):
        sortie, apres, _ = etape_9b_bis(yes=True, reload_ok=False)
        self.assertIn("[FAIL]", sortie)
        self.assertEqual(apres, FILTRE)

    def test_yes_sans_update_ne_modifie_rien(self):
        sortie, apres, _ = etape_9b_bis(yes=True, check_only="1")
        self.assertIn("[ATTN]", sortie)
        self.assertEqual(apres, FILTRE)

    def test_etape_0f_suit_yes_et_garde_le_retour_en_arriere(self):
        debut = TEXTE.index('GEN_REP=""')
        bloc = TEXTE[debut:TEXTE.index("# --- 1) Directory for ACME", debut)]
        self.assertRegex(bloc, r'if \[\[ "\$ROLLBACK_YES" == "1" \]\]; then GEN_REP="o"')
        self.assertLess(bloc.index("ROLLBACK_YES"), bloc.index("[[ -t 0 ]]"), "--yes avant la question du terminal")
        self.assertIn("nginx -t refuse la configuration générique : retour à l'état précédent", bloc)
        self.assertIn(".before-generic-", bloc)

    def test_aide_decrit_yes_avec_update(self):
        self.assertRegex(TEXTE, r"(?m)^  --yes\s+avec --rollback, --disable-uri, --enable-uri ou --update")


if __name__ == "__main__":
    unittest.main()
