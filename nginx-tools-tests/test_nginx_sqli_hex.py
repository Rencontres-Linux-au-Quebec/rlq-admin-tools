#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # jail nginx-sqli defined by hand on the Odoo server (jail.local + filter.d)
# Tests of step 9b bis of nginx-hardening.sh (2.123): the token 0x[0-9a-fA-F]+ of the filter nginx-sqli gets the lookbehind
# (?<![0-9A-Za-z]), so that a size of image in a name (2160x2160 -> "0x2160") no longer bans a visitor. Case of 2026-11-21:
# 172.216.14.68, 196.250.117.3 and 142.172.32.100, signed in to Odoo, banned 24 h by nginx-sqli after 3 requests for a broken
# image of a message of the discussion. The function is extracted from the script; the regular expressions are checked with
# Python's re, the engine used by fail2ban, and with the real fail2ban-regex when it is installed.
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "nginx-hardening.sh")

# Filter found on the Odoo PROD server on 2026-11-21 (written by hand, not delivered by the repository).
FILTRE = r'''[Definition]
# On restreint la recherche exclusivement entre les guillemets de la requête HTTP ("GET /cible HTTP/1.x")
failregex = ^<HOST> .*"[A-Z]+ [^"]*(?:UNION%%20ALL%%20SELECT|UNION%%20SELECT|EXTRACTVALUE\(|INFORMATION_SCHEMA|SLEEP\(|WAITFOR%%20DELAY|0x[0-9a-fA-F]+)[^"]* HTTP/[0-9.]+"
            ^<HOST> .*"[A-Z]+ [^"]*(?:%%27|%%22|\-\-)[^"]*(?:%%20SELECT|%%20UNION|%%20INSERT|%%20DELETE|%%20UPDATE|%%20DROP)[^"]* HTTP/[0-9.]+"
ignoreregex =
'''


def ligne(requete, ip="172.216.14.68"):
    return (f'{ip} - - [21/Nov/2026:08:57:07 -0500] "{requete} HTTP/1.1" 404 9946 '
            f'"https://www.rencontres-linux.quebec/discuss/channel/118" "Mozilla/5.0 (X11; Linux x86_64) Chrome/158.0.0.0" '
            f'host="www.rencontres-linux.quebec" rl=1155 rt=0.680 urt="0.680" us=404')


IMAGE = ("GET /rails/active_storage/blobs/redirect/eyJfcmFpbHMiOnsiZGF0YSI6ImUxNmE1NTZiLTc1YzUtNDJjMy1iM2ZlLWM5ZTEwMzRkM2Y4ZSIsInB1ciI6ImJs"
         "b2JfaWQifX0=--223cd340cc73446b6e8dbcec16131087781e222e/Tux-FleurDeLys-shadow-RLQ-v2-fondTransp.2160x2160.png")
LEGITIMES = [IMAGE, "GET /web/image/5507-1efa100c/EvoluData-Logo-1200x390.webp", "GET /apple-touch-icon-120x120.png",
             "GET /en_CA/web/image/website/1/app_icon/180x180", "GET /link-page-shared/images/photo-1920x1080.jpg"]
ATTAQUES = ["GET /shop?id=1%20UNION%20SELECT%201,2", "GET /page?id=0x414243", "GET /x?q=CHAR(0x41)",
            "GET /x?q=1%27%20AND%201=1--%20SELECT", "GET /x?id=1%20AND%20EXTRACTVALUE(1,0x5c)", "GET /x?a=0x7e"]


def corriger(texte):
    fonction = open(SCRIPT, encoding="utf-8").read()
    debut = fonction.index("\nf2b_sqli_hex_fix() {") + 1
    fin = fonction.index("\n}\n", debut) + 3
    variables = "\n".join(re.findall(r"(?m)^F2B_SQLI_HEX_(?:OLD|NEW)=.*$", fonction))
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, encoding="utf-8") as f:
        f.write(texte)
    try:
        r = subprocess.run(["bash", "-c", "set -euo pipefail\n" + variables + "\n" + fonction[debut:fin] + '\nf2b_sqli_hex_fix "$1"', "bash", f.name],
                           capture_output=True, text=True)
    finally:
        os.unlink(f.name)
    assert r.returncode == 0, r.stderr
    return r.stdout


def regex(texte):
    """failregex lines of the filter, as fail2ban compiles them (%% -> %, <HOST> -> address)."""
    corps = texte.split("failregex =", 1)[1].split("ignoreregex", 1)[0]
    return [re.compile(l.strip().replace("%%", "%").replace("<HOST>", r"(?P<host>\S+)")) for l in corps.splitlines() if l.strip()]


def capte(texte, requete):
    return any(rx.search(ligne(requete)) for rx in regex(texte))


class FiltreSqliTaillesDImage(unittest.TestCase):
    def test_avant_correction_l_image_cassee_faisait_bannir(self):
        self.assertTrue(capte(FILTRE, IMAGE), "le filtre d'origine doit capter l'image (cause des bannissements du 2026-11-21)")

    def test_tailles_d_image_plus_captees(self):
        corrige = corriger(FILTRE)
        for requete in LEGITIMES:
            with self.subTest(requete=requete[:60]):
                self.assertFalse(capte(corrige, requete), f"{requete} : taille d'image prise pour du SQL")

    def test_vraies_injections_toujours_captees(self):
        corrige = corriger(FILTRE)
        for requete in ATTAQUES:
            with self.subTest(requete=requete):
                self.assertTrue(capte(corrige, requete), f"{requete} : injection SQL qui n'est plus captée")

    def test_seul_le_jeton_0x_change_et_correction_idempotente(self):
        corrige = corriger(FILTRE)
        self.assertEqual(corrige.count("(?<![0-9A-Za-z])0x[0-9a-fA-F]+"), 1)
        self.assertEqual(corrige.replace("(?<![0-9A-Za-z])0x", "0x"), FILTRE)
        self.assertEqual(corriger(corrige), corrige, "une deuxième correction ne doit rien changer")

    def test_commentaires_et_filtre_sans_jeton_inchanges(self):
        sans = "[Definition]\n# exemple 0x[0-9a-fA-F]+ dans un commentaire\nfailregex = ^<HOST> .*UNION%%20SELECT\nignoreregex =\n"
        self.assertEqual(corriger(sans), sans)

    @unittest.skipUnless(shutil.which("fail2ban-regex"), "fail2ban-regex absent (installé sur les serveurs : test réel là-bas)")
    def test_vrai_fail2ban_regex(self):
        with tempfile.TemporaryDirectory() as d:
            filtre = os.path.join(d, "nginx-sqli.conf")
            journal = os.path.join(d, "access.log")
            open(filtre, "w", encoding="utf-8").write(corriger(FILTRE))
            open(journal, "w", encoding="utf-8").write("\n".join(ligne(r) for r in LEGITIMES + ATTAQUES) + "\n")
            r = subprocess.run(["fail2ban-regex", journal, filtre], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, rf"Lines: {len(LEGITIMES) + len(ATTAQUES)} lines, 0 ignored, {len(ATTAQUES)} matched")


if __name__ == "__main__":
    unittest.main()
