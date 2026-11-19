"""apps/_odoo_addons.py et nginx-hardening.sh 2.116 étape 17c : dossiers d'addons_path sans module installé, réduction, module rlq_preload_statics."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"   # Odoo seulement
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import script_path

SCRIPTS = os.path.dirname(script_path("nginx-hardening.sh"))
sys.path.insert(0, os.path.join(SCRIPTS, "apps"))
import _odoo_addons as oa  # noqa: E402


class OdooAddons(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="test-rlq-addons-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.chemins = {}
        for dossier, modules in (("odoo/addons", ("base", "web", "rpc", "website")), ("OCA_a", ("a1", "a2")), ("OCA_b", ("b1",)),
                                 ("vide", ()), ("perso", ("p1", "p2", "p3"))):
            p = os.path.join(self.d, dossier)
            os.makedirs(p)
            for m in modules:
                os.makedirs(os.path.join(p, m))
                open(os.path.join(p, m, "__manifest__.py"), "w").write("{}")
            self.chemins[dossier] = p
        self.conf = os.path.join(self.d, "config.conf")
        ordre = ("odoo/addons", "OCA_a", "OCA_b", "vide", "perso")
        open(self.conf, "w").write("[options]\naddons_path = " + ",".join(self.chemins[k] for k in ordre) + "\nxmlrpc_port = 10000\n")
        self.inst = os.path.join(self.d, "installes")
        open(self.inst, "w").write("base\nweb\nwebsite\na2\n")

    def lancer(self, *args):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "apps", "_odoo_addons.py"), "--conf", self.conf, *args],
                           capture_output=True, text=True, timeout=30)
        return p.returncode, dict(l.split("=", 1) for l in p.stdout.splitlines() if "=" in l)

    def test_analyse_sans_rien_ecrire(self):
        code, v = self.lancer("--installed", self.inst)
        self.assertEqual(code, 0)
        self.assertEqual((v["paths"], v["modules"], v["installed"], v["keep"], v["unused"], v["unused_modules"]), ("5", "10", "4", "2", "3", "4"))
        self.assertEqual(v["swm"], "base,rpc,web")                                      # default of Odoo 18 (rpc present)
        self.assertEqual(v["preload"], "0")
        self.assertNotIn("changed", v)

    def test_reduction_et_prechargement_ecrits_avec_copie(self):
        avant = open(self.conf).read()
        module = os.path.join(SCRIPTS, "odoo-addons")
        code, v = self.lancer("--installed", self.inst, "--trim", "--preload", module, "--write")
        self.assertEqual(code, 0, v)
        self.assertEqual(open(v["backup"]).read(), avant)
        texte = open(self.conf).read()
        self.assertEqual(oa.read_value(texte, "addons_path").split(","), [self.chemins["odoo/addons"], self.chemins["OCA_a"], module])
        self.assertEqual(oa.read_value(texte, "server_wide_modules"), "base,rpc,web,rlq_preload_statics")
        self.assertIn("xmlrpc_port = 10000", texte)                                     # the rest of the file untouched
        code, v = self.lancer("--installed", self.inst, "--trim", "--preload", module)
        self.assertEqual((v["preload"], v["unused"], v["changed"]), ("1", "0", "0"))   # nothing more to do

    def test_jamais_reduit_a_l_aveugle(self):
        open(self.inst, "a").write("introuvable\n")
        code, v = self.lancer("--installed", self.inst, "--trim", "--write")
        self.assertEqual(code, 3)
        self.assertEqual(v["missing"], "introuvable")
        self.assertNotIn("backup", v)
        open(self.inst, "w").close()
        code, v = self.lancer("--installed", self.inst, "--trim", "--write")
        self.assertEqual(code, 3)                                                       # no installed module read: never trimmed

    def test_117_module_deja_dans_addons_path(self):
        """2.117 : rlq_preload_statics déjà dans un dossier d'addons_path (rlq-odoo-addons) : seulement server_wide_modules complété."""
        rlq = os.path.join(self.d, "rlq-odoo-addons")
        os.makedirs(os.path.join(rlq, "rlq_preload_statics"))
        open(os.path.join(rlq, "rlq_preload_statics", "__manifest__.py"), "w").write("{}")
        texte = open(self.conf).read().replace("\nxmlrpc", "," + rlq + "\nxmlrpc")
        open(self.conf, "w").write(texte)
        code, v = self.lancer("--installed", self.inst, "--preload", os.path.join(SCRIPTS, "odoo-addons"))
        self.assertEqual((v["preload"], v["preload_path"]), ("0", rlq))
        code, v = self.lancer("--installed", self.inst, "--preload", os.path.join(SCRIPTS, "odoo-addons"), "--write")
        nouveau = open(self.conf).read()
        self.assertEqual(oa.read_value(nouveau, "addons_path"), oa.read_value(texte, "addons_path"))     # nothing added
        self.assertEqual(oa.read_value(nouveau, "server_wide_modules"), "base,rpc,web,rlq_preload_statics")
        code, v = self.lancer("--installed", self.inst, "--trim")
        self.assertEqual(v["keep"], "3")                                                # its folder is always kept

    def test_117_post_load_du_module_livre(self):
        """2.117 : post_load du module livré (odoo-addons/) avec un faux odoo : liste construite une fois ; rien en gevent ; jamais
        « import odoo.http » dans la fonction (odoo devenait un nom local : UnboundLocalError dès la première ligne, en 2.116)."""
        import importlib.util
        import types

        class Racine:
            appels = 0

            @property
            def statics(self):
                Racine.appels += 1
                return {"web": "/w"}
        for evented, attendu in ((False, 1), (True, 0)):
            faux = types.ModuleType("odoo")
            faux.evented = evented
            faux.http = types.ModuleType("odoo.http")
            faux.http.root = Racine()
            Racine.appels = 0
            avant = {k: sys.modules.get(k) for k in ("odoo", "odoo.http")}
            sys.modules["odoo"], sys.modules["odoo.http"] = faux, faux.http
            try:
                spec = importlib.util.spec_from_file_location("rlq_preload_t", os.path.join(SCRIPTS, "odoo-addons", "rlq_preload_statics", "__init__.py"))
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                m.post_load()
            finally:
                for k, val in avant.items():
                    if val is None:
                        sys.modules.pop(k, None)
                    else:
                        sys.modules[k] = val
            self.assertEqual(Racine.appels, attendu)

    def test_valeurs_et_lignes(self):
        t = "[options]\naddons_path = /a\nx = 1\naddons_path=/b\n"
        self.assertEqual(oa.read_value(t, "addons_path"), "/b")                         # last line wins, like Odoo
        t2 = oa.set_value(t, "addons_path", "/c")
        self.assertEqual(t2.count("addons_path"), 1)
        self.assertEqual(oa.read_value(t2, "addons_path"), "/c")
        self.assertIn("[options]\nserver_wide_modules = base", oa.set_value(t, "server_wide_modules", "base"))

    def test_module_prechargement(self):
        manifeste = eval(open(os.path.join(SCRIPTS, "odoo-addons", "rlq_preload_statics", "__manifest__.py")).read())  # noqa: S307 - our file
        self.assertEqual(manifeste["post_load"], "post_load")
        self.assertEqual(manifeste["license"], "AGPL-3")
        texte = open(os.path.join(SCRIPTS, "odoo-addons", "rlq_preload_statics", "__init__.py")).read()
        self.assertIn("def post_load():", texte)
        self.assertIn("odoo.http.root.statics", texte)
        self.assertIn('getattr(odoo, "evented", False)', texte)                        # never in the gevent process

    def test_etape_17c_de_nginx_hardening(self):
        psql = os.path.join(self.d, "psql")
        open(psql, "w").write("#!/bin/bash\ncase \"${@: -1}\" in *to_regclass*) echo t ;; *ir_module_module*) printf 'base\\nweb\\nwebsite\\na2\\n' ;; esac\nexit 0\n")
        os.chmod(psql, 0o755)
        ps = os.path.join(self.d, "ps")
        open(ps, "w").write("python3 ./odoo-bin -c ./config.conf -d base1\n")
        with open(script_path("nginx-hardening.sh"), encoding="utf-8") as f:
            src = f.read()
        fonction = ""
        for nom in ("odoo_bases_servies() {", "odoo_modules_et_chemins() {"):
            debut = src.index(nom)
            fonction += src[debut:src.index("\n}\n", debut) + 3]

        def etape(check, options=""):
            script = (f"SCRIPT_DIR={SCRIPTS}\nNGINX_HARDENING_PSQL={psql}\nNGINX_HARDENING_PS={ps}\nODOO_CONF={self.conf}\nCHECK_ONLY={check}\nEUID=0\n{options}\n"
                      "odoo_service=\nodoo_conf_valeur() { return 0; }\nsystemctl() { return 0; }\n"
                      "pass() { echo \"PASS $*\"; }\nwarn() { echo \"WARN $*\"; }\n" + fonction + "\nodoo_modules_et_chemins\n")
            return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60).stdout
        out = etape(1)
        self.assertIn("addons_path : 5 dossiers, 10 modules ; 4 modules installés (bases : base1", out)
        self.assertIn("WARN Odoo : 3 dossiers d'addons_path (4 modules) ne contiennent aucun module installé", out)
        self.assertIn("--odoo-trim-addons-path", out)
        self.assertIn("--odoo-preload-statics", out)
        avant = open(self.conf).read()
        self.assertEqual(open(self.conf).read(), avant)                                 # --check: nothing written
        out = etape(0, "ODOO_TRIM_ADDONS_PATH=1\nODOO_PRELOAD_STATICS=1")
        self.assertIn("PASS Odoo : addons_path réduit à 2 dossiers", out)
        self.assertIn("PASS Odoo : rlq_preload_statics ajouté à server_wide_modules", out)
        self.assertIn("--restart-only", out)
        texte = open(self.conf).read()
        self.assertIn("rlq_preload_statics", texte)
        self.assertNotIn(self.chemins["vide"], texte)
        out = etape(1)
        self.assertIn("PASS Odoo : chaque dossier d'addons_path contient un module installé", out)
        self.assertIn("PASS Odoo : rlq_preload_statics dans server_wide_modules", out)

    def test_118_odoo_sans_d_ni_db_name(self):
        """2.118 : Odoo lancé sans -d et db_name = False (DEV d'ERPLibre) : toutes les bases du serveur, sauf celles qui ne sont pas d'Odoo ;
        modules de plusieurs bases comptés une fois."""
        psql = os.path.join(self.d, "psql")
        open(psql, "w").write("#!/bin/bash\nbase=\"$2\"\ncase \"${@: -1}\" in\n"
                              "  *pg_database*) printf 'base_dev\\nautre\\nbase_test\\n' ;;\n"
                              "  *to_regclass*) [[ $base == autre ]] && echo f || echo t ;;\n"
                              "  *ir_module_module*) printf 'base\\nweb\\nwebsite\\na2\\n' ;;\nesac\nexit 0\n")
        os.chmod(psql, 0o755)
        ps = os.path.join(self.d, "ps")
        open(ps, "w").write("python3 ./odoo18.0/odoo/odoo-bin -c ./config.conf\n")
        with open(script_path("nginx-hardening.sh"), encoding="utf-8") as f:
            src = f.read()
        fonction = ""
        for nom in ("odoo_bases_servies() {", "odoo_modules_et_chemins() {"):
            debut = src.index(nom)
            fonction += src[debut:src.index("\n}\n", debut) + 3]
        script = (f"SCRIPT_DIR={SCRIPTS}\nNGINX_HARDENING_PSQL={psql}\nNGINX_HARDENING_PS={ps}\nODOO_CONF={self.conf}\nCHECK_ONLY=1\nEUID=0\n"
                  "odoo_service=\nodoo_conf_valeur() { echo False; }\nsystemctl() { return 0; }\n"
                  "pass() { echo \"PASS $*\"; }\nwarn() { echo \"WARN $*\"; }\n" + fonction + "\nodoo_modules_et_chemins\n")
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60).stdout
        self.assertIn("4 modules installés (bases : base_dev base_test)", out)
        self.assertIn("WARN Odoo : 3 dossiers d'addons_path", out)


if __name__ == "__main__":
    unittest.main()
