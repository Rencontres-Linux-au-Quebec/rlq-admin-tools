"""nginx-log-audit.sh 2.68 : injection SQL reconnue meme encodee (%28), et jamais levee par --unban-check.

Les URL sont celles relevees le 2026-10-28 pour 37.65.66.209 (banni par --ban-sqli, puis propose a la levee a tort).
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import re
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sqli_re():
    with open(os.path.join(RACINE, "nginx-log-audit.sh"), encoding="utf-8") as f:
        m = re.search(r"^SQLI_RE='(.*)'$", f.read(), re.M)
    return m.group(1)


def correspond(url):
    # Meme ERE que le programme (grep -E, insensible a la casse).
    return re.search(sqli_re(), url, re.I) is not None


class SqliUnbanCheck(unittest.TestCase):
    def test_union_select_reconnu(self):
        self.assertTrue(correspond("/shop/x?order=website_sequence%20asc%27%20UNION%20ALL%20SELECT%20%27ndwcjm"))

    def test_extractvalue_parenthese_encodee_reconnu(self):
        """Regression 2.68 : la parenthese est encodee en %28 dans le journal, le motif ne la voyait pas."""
        self.assertTrue(correspond("/shop/x?order=website_sequence%20asc%29%20AND%20EXTRACTVALUE%285623%2CCONC"))
        self.assertTrue(correspond("/shop/x?order=website_sequence%20asc%60%20AND%20EXTRACTVALUE%285248%2CCONC"))

    def test_parenthese_litterale_toujours_reconnue(self):
        self.assertTrue(correspond("/x?a=extractvalue(1,concat(0x7e,version()))"))

    def test_urls_normales_non_reconnues(self):
        self.assertFalse(correspond("/shop/tasse-du-22e-11-onces-19?order=website_sequence%20asc"))
        self.assertFalse(correspond("/web/assets/1/bc7974c/web.assets_frontend_lazy.min.js"))

    def test_recommander_garde_si_injection(self):
        """2.85 : la règle est dans recommander() (le moteur de verdict unique de --investigate, --unban-check et --unban-low-score) :
        un verdict LEVER LE BANNISSEMENT devient GARDER LE BANNISSEMENT si sqli_hits_ip trouve une injection (sauf adresse protégée)."""
        with open(os.path.join(RACINE, "nginx-log-audit.sh"), encoding="utf-8") as f:
            s = f.read()
        corps = re.search(r"^recommander\(\) \{(.*?)^\}", s, re.S | re.M).group(1)
        self.assertIn('n_sqli=$(sqli_hits_ip "$ip")', corps)
        garde = corps[corps.index("sqli_hits_ip"):]
        self.assertIn('verdict="GARDER LE BANNISSEMENT"', garde.split("noms_refuses")[0])
        self.assertIn('"$verdict" == "LEVER LE BANNISSEMENT" && -z "$prot"', corps)
        self.assertNotIn("decide_unban", s)


if __name__ == "__main__":
    unittest.main()
