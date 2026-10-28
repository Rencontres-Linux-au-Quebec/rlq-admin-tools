#!/usr/bin/env python3
ENVIRONNEMENT = "odoo"   # configuration nginx Odoo (snippets, conf.d, jail fail2ban)
# Tests of the SQL injection prevention (nginx-hardening.sh 2.58): map $is_sqli_probe, refusal rule, fail2ban jail nginx-sqli.
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NGINX = os.path.join(ROOT, "nginx")

# Real requests of 2026-10-28 (attacks) and legitimate ones (must not match).
ATTAQUES = [
    "/es/shop?order=website_sequence%20asc'%20UNION%20ALL%20SELECT%20'mhekckqbaukhdkzebdlwawokrrbdmajt'--%20xx3c4t",
    "/es/shop?order=website_sequence%20asc))%20AND%20EXTRACTVALUE(6985,CONCAT(0x7e,((SELECT%20(ELT(6985%3D6985,1)))),0x7e))--%20-",
    "/es/shop?order=website_sequence%20asc%20ORDER%20BY%201000--%20-",
    "/es/shop?order=website_sequence%20asc%20UNION%20ALL%20SELECT%20NULL,'x'--%2043fgim",
]
LEGITIMES = [
    "/es/shop?order=website_sequence%20asc",
    "/en_CA/event?order=is_published%20desc",
    "/event/journee-portes-ouvertes-sur-linux-23/track/open-source-8",
]


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


def motif_map():
    """The regex of the map $is_sqli_probe, as written in nginx/conf.d/odoo-global.conf (first ~* line of the map)."""
    bloc = re.search(r"map \$request_uri \$is_sqli_probe \{(.*?)\n\}", lire(os.path.join(NGINX, "conf.d", "odoo-global.conf")), re.S)
    assert bloc, "map $is_sqli_probe absente de conf.d/odoo-global.conf"
    regle = re.search(r"~\*(.*?) 1;", bloc.group(1))
    assert regle, "regex de la map introuvable"
    return regle.group(1)


def motif_fail2ban():
    """failregex of nginx/fail2ban/nginx-sqli.filter.conf, adapted to Python (the <HOST> tag becomes a group)."""
    ligne = re.search(r"^failregex = (.*)$", lire(os.path.join(NGINX, "fail2ban", "nginx-sqli.filter.conf")), re.M).group(1)
    return re.compile(ligne.replace("^<HOST>", r"^(?P<host>\S+)"))


class SqliPrevention(unittest.TestCase):
    def test_map_matches_attacks_and_not_legit(self):
        rx = re.compile(motif_map(), re.I)
        for u in ATTAQUES:
            self.assertIsNotNone(rx.search(u), u)
        for u in LEGITIMES:
            self.assertIsNone(rx.search(u), u)

    def test_map_has_no_backslash_nor_space(self):
        # nginx reads the map line word by word: a backslash or a space would break "nginx -t" (see securite-commune.conf).
        motif = motif_map()
        self.assertNotIn("\\", motif)
        self.assertNotIn(" ", motif)
        self.assertNotIn(";", motif)

    def test_fail2ban_filter_matches_attack_log_lines(self):
        rx = motif_fail2ban()
        for u in ATTAQUES:
            ligne = f'89.93.186.67 - - [28/Oct/2026:09:49:57 -0400] "GET {u} HTTP/1.1" 400 25 "-" "Mozilla/5.0"'
            m = rx.search(ligne)
            self.assertIsNotNone(m, u)
            self.assertEqual(m.group("host"), "89.93.186.67")
        for u in LEGITIMES:
            ligne = f'192.0.2.7 - - [28/Oct/2026:09:50:00 -0400] "GET {u} HTTP/1.1" 200 25 "-" "Mozilla/5.0"'
            self.assertIsNone(rx.search(ligne), u)

    def test_refusal_rule_in_securite_commune(self):
        s = lire(os.path.join(NGINX, "snippets", "securite-commune.conf"))
        self.assertRegex(s, r"if \(\$is_sqli_probe\) \{\s*return 403;\s*\}")

    def test_jail_and_installer(self):
        jail = lire(os.path.join(NGINX, "fail2ban", "nginx-sqli.jail.conf"))
        self.assertRegex(jail, r"\[nginx-sqli\]")
        self.assertRegex(jail, r"filter\s*= nginx-sqli")
        self.assertRegex(jail, r"maxretry = 3")
        self.assertRegex(jail, r"bantime\s*= 86400")
        script = lire(os.path.join(ROOT, "nginx-hardening.sh"))
        self.assertIn("fail2ban/nginx-sqli.filter.conf fail2ban/nginx-sqli.jail.conf", script)
        self.assertIn("installer_jail_copie nginx-sqli", script)


if __name__ == "__main__":
    unittest.main()
