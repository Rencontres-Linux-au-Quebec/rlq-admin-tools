"""Verrous (flock) des programmes et source unique des adresses de l'équipe (nginx-hardening.sh, étape 12)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import fcntl
import os
import re
import subprocess
import tempfile
import unittest

from helpers import EnvTest, CONFIG_DIR, script_path


class Verrous(EnvTest):
    """Une seule exécution modifiante à la fois ; les modes en lecture seule ne prennent jamais le verrou."""
    def tenir(self, nom):
        f = open(os.path.join(self.env["NGINX_TOOLS_LOCK_DIR"], f"{nom}.lock"), "a")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(f.close)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_sync_crowdsec(self):
        prog = self.prepare("sync-crowdsec-blocklist.sh", {"/etc/iptables": os.path.dirname(self.path("etc-iptables", "x"))})
        self.tenir("sync-crowdsec-blocklist")
        rc, out, err = self.run_cmd(["bash", prog, "--dry-run"])
        self.assertEqual(rc, 75, out + err)
        self.assertIn("une autre exécution de sync-crowdsec-blocklist est en cours", err)
        rc, out, err = self.run_cmd(["bash", prog, "--status"])
        self.assertNotEqual(rc, 75)

    def test_nginx_log_audit(self):
        prog = self.prepare("nginx-log-audit.sh", {"/var/log/nginx": os.path.dirname(self.path("nginx", "x"))})
        self.write("nginx/rencontres_linux_quebec_prod-access.log", "")
        self.tenir("nginx-log-audit")
        rc, out, err = self.run_cmd(["bash", prog, "prod", "--no-prompt"])          # attente de 2 s puis abandon
        self.assertEqual(rc, 75, out + err)
        self.assertIn("une autre exécution de nginx-log-audit est en cours", err)
        rc, out, err = self.run_cmd(["bash", prog, "--investigate", "203.0.113.9"])   # lecture seule : sans verrou
        self.assertNotEqual(rc, 75)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_web_monitor(self):
        prog = self.prepare("web-monitor.py")
        self.tenir("web-monitor")
        rc, out, err = self.run_cmd(["python3", prog])
        self.assertEqual(rc, 75, out + err)
        self.assertIn("une autre exécution de web-monitor.py est en cours", err)
        rc, out, err = self.run_cmd(["python3", prog, "--status"])                  # lecture seule
        self.assertNotEqual(rc, 75)


class SourceUniqueEquipe(unittest.TestCase):
    """Adresses de l'équipe : seule la LISTE BLANCHE (/etc/default/nginx-tools-white-list.conf, hors des archives) les porte ; la configuration
    nginx inclut, par un joker, des fichiers GÉNÉRÉS qu'elle ne livre pas (ils doivent exister : nginx -t échoue si le joker ne correspond à rien)."""
    def generer(self, type_, liste):
        """Sortie de generer_equipe (nginx-hardening.sh) pour la liste blanche donnée, et les entrées invalides notées."""
        src = open(script_path("nginx-hardening.sh"), encoding="utf-8").read()
        fonction = re.search(r"^generer_equipe\(\) \{.*?^\}\n", src, re.M | re.S).group(0)
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "nginx-tools-white-list.conf")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(liste)
            r = subprocess.run(["bash", "-c", f'SCRIPT_DIR={script_path(".")}\n. "$SCRIPT_DIR/apps/_listes.sh"\n{fonction}\n'
                                              f'generer_equipe {type_}\necho "INVALIDES:$EQUIPE_INVALIDES" >&2'],
                               capture_output=True, text=True, env=dict(os.environ, NGINX_TOOLS_WHITE_LIST=chemin))
        return r.stdout, r.stderr.strip()

    @unittest.skipUnless(os.path.isdir(CONFIG_DIR), f"configuration nginx absente : {CONFIG_DIR} (privée, hors du dépôt : NGINX_ODOO_DIR ou nginx-tools-tests/nginx-odoo/)")
    def test_aucun_fichier_genere_dans_la_configuration_livree(self):
        """snippets/team-ips-geo.conf et team-ips-allow.conf contenaient de vraies adresses : générés sur chaque serveur, jamais livrés."""
        for type_ in ("geo", "allow"):
            with self.subTest(fichier=f"team-ips-{type_}.conf"):
                self.assertFalse(os.path.exists(os.path.join(CONFIG_DIR, "snippets", f"team-ips-{type_}.conf")),
                                 "fichier généré (adresses personnelles) : ne doit pas être dans l'archive de configuration")
        self.assertFalse(os.path.exists(script_path("apps/team-ips.list")), "ancienne liste : remplacée par /etc/default/nginx-tools-white-list.conf")

    def test_generateur_depuis_la_liste_blanche(self):
        liste = ("# commentaire\n203.0.113.10        # Étienne (maison)\n198.51.100.0/24  # Bureau  [protégée]\n"
                 "pas-une-adresse   # invalide\n2001:db8::/32     # Réseau v6\n")
        geo, err = self.generer("geo", liste)
        self.assertIn("# GÉNÉRÉ par nginx-hardening.sh à partir de la liste blanche (/etc/default/nginx-tools-white-list.conf)", geo)
        self.assertRegex(geo, r"(?m)^203\.0\.113\.10\s+1;\s+# Étienne \(maison\)$")
        self.assertRegex(geo, r"(?m)^198\.51\.100\.0/24\s+1;\s+# Bureau$")                      # l'option [protégée] n'est pas dans le libellé
        self.assertRegex(geo, r"(?m)^2001:db8::/32\s+1;\s+# Réseau v6$")
        self.assertNotIn("pas-une-adresse", geo)                                                  # jamais écrit dans nginx (il refuserait tout)
        self.assertIn("ligne 4 : « pas-une-adresse »", err)
        allow, _ = self.generer("allow", liste)
        self.assertRegex(allow, r"(?m)^allow 203\.0\.113\.10;\s+# Étienne \(maison\)$")
        self.assertRegex(allow, r"(?m)^allow 198\.51\.100\.0/24;\s+# Bureau$")
        # Liste absente ou vide : aucune adresse (DEV et LAB restent fermés), mais un fichier valide
        vide, _ = self.generer("allow", "")
        self.assertEqual([l for l in vide.splitlines() if not l.startswith("#")], [])

    @unittest.skipUnless(os.path.isdir(CONFIG_DIR), f"configuration nginx absente : {CONFIG_DIR} (privée, hors du dépôt : NGINX_ODOO_DIR ou nginx-tools-tests/nginx-odoo/)")
    def test_inclusions_a_joker_et_aucune_adresse_de_l_equipe_en_dur(self):
        """Inclusions par NOM EXACT (team-ips-geo.conf) : un joker (team-ips-geo*.conf) a fait échouer nginx -t sur un serveur même avec les fichiers présents. Les fichiers doivent exister avant nginx -t (créés par nginx-hardening.sh --update). Seules les adresses propres à un
        environnement (localhost, IP publique du serveur) restent dans env-*.conf."""
        glob_ = open(os.path.join(CONFIG_DIR, "conf.d", "odoo-global.conf"), encoding="utf-8").read()
        self.assertIn("include /etc/nginx/snippets/team-ips-geo.conf;", glob_.split("geo $is_trusted_ip", 1)[1].split("}", 1)[0])
        for env, n in (("prod", 1), ("lab", 1), ("dev", 2)):
            with self.subTest(env=env):
                txt = open(os.path.join(CONFIG_DIR, "snippets", "odoo", f"env-{env}.conf"), encoding="utf-8").read()
                self.assertEqual(txt.count("include /etc/nginx/snippets/team-ips-allow.conf;"), n)
                self.assertEqual(txt.count("team-ips-allow.conf;"), n)                       # aucune autre inclusion, aucune adresse en dur
                for ip in re.findall(r"(?m)^\s*allow ([0-9.]+);", txt):
                    self.assertTrue(ip == "127.0.0.1" or env == "dev", f"{ip} : adresse en dur dans env-{env}.conf (seule celle du serveur DEV est permise)")
