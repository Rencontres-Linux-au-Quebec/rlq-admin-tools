#!/usr/bin/env python3
"""apps/_odoo_conf_check.py : le fichier de configuration d'Odoo lu comme Odoo 18 le lit (configparser + types des options), sans démarrer Odoo ;
nginx-hardening.sh (étape 8) et l'analyse d'app-log-live.py (apps/_advisor.py, constat odoo-conf-check) s'en servent."""
ENVIRONNEMENT = "odoo"     # serveurs Odoo
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401  (isole l'environnement)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROG = os.path.join(RACINE, "apps", "_odoo_conf_check.py")


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class OdooConfCheck(unittest.TestCase):
    def setUp(self):
        self.m = charger("odoo_conf_check_t", PROG)
        self.d = tempfile.mkdtemp(prefix="test-rlq-odooconf-")
        self.addCleanup(shutil.rmtree, self.d, True)

    def fichier(self, texte):
        chemin = os.path.join(self.d, "config.conf")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte)
        return chemin

    def niveaux(self, res):
        return [(r[0], r[1], r[2]) for r in res if r[0] != "info"]

    def test_commentaire_apres_la_valeur(self):
        """Cas réel du 2026-11-09 : « limit_memory_soft_gevent = 2147483648 # (2048 Mo » : Odoo refuse l'entier et ne démarre pas."""
        c = self.fichier("[options]\nworkers = 13\nlimit_memory_soft = 1342177280\nlimit_memory_hard = 1610612736\n"
                         "limit_memory_soft_gevent = 2147483648 # (2048 Mo\nlimit_memory_hard_gevent = 2684354560 # 2560 Mo\n"
                         "# un vrai commentaire\n; un autre\n")
        res = self.m.check(c, language="fr", use_odoo=False)
        self.assertEqual(self.niveaux(res), [("error", 5, "limit_memory_soft_gevent"), ("error", 6, "limit_memory_hard_gevent")])
        self.assertIn("mettre « limit_memory_soft_gevent = 2147483648 »", res[0][3])
        r = subprocess.run([sys.executable, PROG, "--lang", "en", "--odoo-bin", "/nonexistent", "--python", sys.executable, c], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[FAIL] line 5 limit_memory_soft_gevent: comment after the value", r.stdout)

    def test_doublon_type_unites_et_memoire(self):
        c = self.fichier("[options]\nworkers = 3\nworkers = 4\nhttp_port = 80x\nlimit_memory_soft = 1740\nlimit_memory_hard = 2147483648\n"
                         "transient_age_limit = 1.0\nproxy_mode = True\n")
        res = self.m.check(c, language="en", use_odoo=False)
        self.assertIn(("error", 3, "workers"), self.niveaux(res))                     # given twice: configparser refuses the file
        self.assertIn(("error", 4, "http_port"), self.niveaux(res))                   # not an integer
        self.assertIn(("error", 5, "limit_memory_soft"), self.niveaux(res))           # 1740 bytes: meant 1740 MB?
        self.assertTrue(any("1824522240" in r[3] for r in res))
        self.assertTrue(any(r[0] == "info" and r[2] == "limit_memory_soft_gevent" for r in res))
        c = self.fichier("[options]\nworkers = 13\nlimit_memory_soft = 683671552\nlimit_memory_hard = 805306368\n"
                         "limit_memory_soft_gevent = 2147483648\nlimit_memory_hard_gevent = 2684354560\n")
        self.assertEqual(self.niveaux(self.m.check(c, use_odoo=False)), [("warning", 3, "limit_memory_soft")])     # under 1024 MB of virtual memory
        c = self.fichier("workers = 3\n[options]\n")
        self.assertIn(("error", 1, "workers"), self.niveaux(self.m.check(c, use_odoo=False)))        # before any section

    def test_analyse_par_odoo_lui_meme(self):
        """Avec l'Odoo du serveur : sa propre lecture (config.parse_config) et les clés qu'il ne connaît pas. Un faux paquet odoo la simule ici."""
        racine = os.path.join(self.d, "odoo18")
        os.makedirs(os.path.join(racine, "odoo", "tools"))
        open(os.path.join(racine, "odoo-bin"), "w").close()
        open(os.path.join(racine, "odoo", "__init__.py"), "w").close()
        with open(os.path.join(racine, "odoo", "tools", "__init__.py"), "w") as f:
            f.write("import configparser, sys\nclass C:\n    options = {'workers': 0, 'db_name': False}\n    casts = {}\n"
                    "    def parse_config(self, args):\n        p = configparser.RawConfigParser(); p.read(args[1])\n"
                    "        v = p.get('options', 'workers')\n        if not v.isdigit():\n"
                    "            print('odoo-bin: error: option --workers: invalid integer value: %r' % v, file=sys.stderr); sys.exit(2)\n"
                    "config = C()\n")
        c = self.fichier("[options]\nworkers = 4\nwrokers = 3\n")
        res = self.m.check(c, os.path.join(racine, "odoo-bin"), sys.executable, "en")
        self.assertIn(("warning", 3, "wrokers"), self.niveaux(res))                   # unknown to Odoo: typo
        self.assertTrue(any(r[0] == "info" and "read without error by the Odoo of the server" in r[3] for r in res))
        c = self.fichier("[options]\nworkers = 4x\n")
        res = self.m.check(c, os.path.join(racine, "odoo-bin"), sys.executable, "en")
        self.assertTrue(any(r[0] == "error" and "Odoo refuses this file" in r[3] and "invalid integer value" in r[3] for r in res), res)

    def test_constat_de_l_analyse(self):
        adv = charger("adv_conf_t", os.path.join(RACINE, "apps", "_advisor.py"))
        import test_advisor
        details = {"odoo_conf_check": [("error", 5, "limit_memory_soft_gevent", "comment after the value")], "odoo_conf": {"path": "/opt/odoo/erplibre/config.conf"}}
        f = test_advisor.par_id(adv.analyze(test_advisor.faits(), details))
        self.assertEqual(f["odoo-conf-check"]["severity"], adv.PROBLEM)
        self.assertTrue(any("_odoo_conf_check.py /opt/odoo/erplibre/config.conf" in a for a in f["odoo-conf-check"]["advice"]))

    def test_etape_8_de_nginx_hardening(self):
        with open(os.path.join(RACINE, "nginx-hardening.sh"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('python3 "$SCRIPT_DIR/apps/_odoo_conf_check.py" --tsv "$ODOO_CONF"', src)


if __name__ == "__main__":
    unittest.main()
