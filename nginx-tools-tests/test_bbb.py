"""apps/_bbb.py — état de BigBlueButton (versions, configuration de BBB et la nôtre), compatibilité avec nos règles,
instantané avant/après une mise à jour ; intégration dans nginx-hardening.sh et web-monitor.py --summary."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "bbb"   # BigBlueButton : état de BBB (apps/_bbb.py), instantané avant / après
import importlib.util
import json
import os

from helpers import EnvTest, script_path


class EtatBBB(EnvTest):
    def setUp(self):
        super().setUp()
        self.e = self.env
        self.regles = os.path.join(self.e["NGINX_TOOLS_BBB_ETC"], "nginx", "zz-nginx-hardening-security.nginx")
        self.write("bbb-etc/bigbluebutton-release", "BIGBLUEBUTTON_RELEASE=2.7.12\n")
        self.write("bbb-etc/nginx/bbb-html5.nginx", "location /html5client { }\n")
        self.write("bbb-etc/nginx/zz-nginx-hardening-security.nginx", "# GÉNÉRÉ par nginx-hardening.sh\n")
        self.write("bbb-etc/bbb-web.properties", "bigbluebutton.web.serverURL=https://bbb3.exemple.org\n")
        self.write("nginx-etc/sites-available/bigbluebutton", "server { include /etc/bigbluebutton/nginx/*.nginx; }\n")
        self.write("haproxy/haproxy.cfg", "frontend f\n  http-after-response set-header Strict-Transport-Security \"max-age=300\"\n")
        self.paquets("2.7.12")
        self.mock("dpkg", 'for f in "${@:2}"; do case "$f" in *bigbluebutton) echo "bbb-config: $f";; *) echo "dpkg-query: no path found matching pattern $f" >&2;; esac; done; exit 1')
        self.mock("nginx", f'if [ "$1" = "-T" ]; then echo "# configuration file {self.regles}:"; echo "location ~ /\\. {{"; fi; exit 0')
        self.mock("bbb-conf", 'echo "BigBlueButton Server 2.7.12"; exit 0')
        self.mock("docker", 'echo "bigbluebutton/greenlight:v3.3.1"')
        self.avant_env = dict(os.environ)
        self.addCleanup(self.restaurer, dict(os.environ))          # copie AVANT les modifications (sinon rien n'est restauré)
        os.environ.update({k: v for k, v in self.e.items() if k.startswith(("NGINX_TOOLS_", "WEB_MONITOR_"))})
        os.environ["PATH"] = self.e["PATH"]

    def restaurer(self, ancien):
        os.environ.clear()
        os.environ.update(ancien)

    def paquets(self, version, html5=None):
        self.mock("dpkg-query", f"""cat <<'X'
bigbluebutton\t1:{version}-1\tii 
bbb-html5\t1:{html5 or version}-2\tii 
bbb-web\t1:{version}-1\tii 
nginx\t1.18.0-0ubuntu1.4\tii 
haproxy\t2.6.15-1\tii 
bbb-learning-dashboard\t1:{version}-1\tii 
bbb-ancien\t1:2.6.0-1\trc 
X""")

    def module(self):
        spec = importlib.util.spec_from_file_location("_bbb", script_path("apps/_bbb.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.get = lambda chemin, nom, timeout=8: (200, b"<returncode>SUCCESS</returncode>") if "api" in chemin else (200, b"x" * 5000)
        return m

    def test_releve_versions_et_fichiers(self):
        e = self.module().releve()
        self.assertEqual(e["release"], "2.7.12")
        self.assertEqual(e["paquets"]["bbb-html5"], "1:2.7.12-2")
        self.assertNotIn("bbb-ancien", e["paquets"])                          # désinstallé (rc) : ignoré
        self.assertEqual(e["greenlight"], ["bigbluebutton/greenlight:v3.3.1"])
        self.assertIn(self.regles, e["fichiers_nous"])
        self.assertNotIn(self.regles, e["fichiers_bbb"])
        self.assertEqual(e["proprietaires"][os.path.join(self.e["NGINX_TOOLS_NGINX_ETC"], "sites-available", "bigbluebutton")], "bbb-config")
        self.assertTrue(e["hsts_haproxy"])

    def test_verifications_de_compatibilite(self):
        m = self.module()
        lignes, problemes = m.verifier(m.releve())
        texte = "\n".join(lignes)
        self.assertIn("[OK] nos règles (zz-nginx-hardening-security.nginx) n'appartiennent à aucun paquet", texte)
        self.assertIn("[OK] nos règles sont chargées par nginx", texte)
        self.assertIn("[OK] nginx -t : configuration valide", texte)
        self.assertIn("[OK] HSTS présent dans HAProxy", texte)
        self.assertIn("[OK] API de BBB répond (https://bbb3.exemple.org/bigbluebutton/api → 200 SUCCESS)", texte)
        self.assertIn("[OK] bbb-conf --check : aucun problème potentiel signalé", texte)
        self.assertEqual(problemes, [])
        # Une de nos règles capte le client HTML5 : 404 minimal de nginx → échec
        m.get = lambda chemin, nom, timeout=8: (404, b"<html>404</html>") if "html5" in chemin else (200, b"SUCCESS")
        lignes, problemes = m.verifier(m.releve())
        self.assertIn("[FAIL] client HTML5 : https://bbb3.exemple.org/html5client/ → 404 minimal", "\n".join(lignes))
        # Règles non chargées (BBB a retiré l'include) et bbb-conf --check qui signale un problème
        self.mock("nginx", 'if [ "$1" = "-T" ]; then echo "# configuration file /etc/nginx/nginx.conf:"; fi; exit 0')
        self.mock("bbb-conf", 'echo "# Potential problems described below"; echo "# Warning: mismatch IP"; echo ""; exit 0')
        m = self.module()
        lignes, problemes = m.verifier(m.releve())
        texte = "\n".join(lignes)
        self.assertIn("[FAIL] nos règles ne sont pas chargées par nginx", texte)
        self.assertIn("[ATTN] bbb-conf --check signale 1 problème(s) potentiel(s) : # Warning: mismatch IP", texte)

    def test_mise_a_jour_de_bbb_entre_deux_passages(self):
        """--update écrit l'instantané ; une mise à jour de BBB qui régénère haproxy.cfg (sans HSTS) et change les versions
        apparaît AVANT au passage suivant, et dans le sommaire (recommandation)."""
        m = self.module()
        m.resume("before")
        lignes, _ = m.resume("after", sauver=True)
        self.assertIn("ce passage n'a modifié ni BBB ni nos fichiers", "\n".join(lignes))
        with open(self.e["NGINX_TOOLS_BBB_STATE"], encoding="utf-8") as f:
            etat = json.load(f)
        self.assertEqual(etat["release"], "2.7.12")
        # Mise à jour de BBB : versions, haproxy.cfg régénéré, fichier de BBB modifié
        self.write("bbb-etc/bigbluebutton-release", "BIGBLUEBUTTON_RELEASE=2.7.14\n")
        self.paquets("2.7.14")
        self.write("haproxy/haproxy.cfg", "frontend f\n  bind :443\n")
        self.write("bbb-etc/nginx/bbb-html5.nginx", "location /html5client { proxy_pass x; }\n")
        m = self.module()
        lignes, _ = m.resume("before")
        texte = "\n".join(lignes)
        self.assertIn("[ATTN] BigBlueButton 2.7.12 → 2.7.14", texte)
        self.assertIn("paquet(s) changé(s)", texte)
        self.assertIn("bigbluebutton 1:2.7.12-1 → 1:2.7.14-1", texte)
        self.assertIn("configuration de BBB modifiée", texte)
        self.assertIn("haproxy.cfg", texte)
        self.assertIn("bbb-html5.nginx", texte)
        self.assertIn("[FAIL] HSTS retiré de HAProxy", texte)
        self.assertNotIn("notre fichier", texte)                                 # nos fichiers intacts
        lignes, problemes = m.resume("summary")
        constats = " | ".join(p[1] for p in problemes)
        self.assertIn("BigBlueButton a été mis à jour depuis le dernier nginx-hardening.sh --update", constats)
        self.assertIn("HSTS retiré de HAProxy", constats)
        # Notre fichier disparu
        os.remove(self.regles)
        lignes, problemes = self.module().resume("summary")
        self.assertIn("a DISPARU", "\n".join(lignes))
        self.assertIn("nos règles de sécurité sont absentes", " | ".join(p[1] for p in problemes))

    def test_nginx_hardening_avant_apres_sur_bbb(self):
        """nginx-hardening.sh (profil bbb) : sections AVANT et APRÈS, instantané écrit seulement par --update."""
        prog = self.prepare("nginx-hardening.sh")
        env = dict(self.e, APP_PROFILE="bbb", NGINX_HARDENING_BBB_NGINX_DIR=os.path.dirname(self.regles))
        rc, out, err = self.run_cmd(["bash", prog, "--check"], env)
        self.assertIn("--- BigBlueButton AVANT ce passage", out, out + err)
        self.assertIn("--- BigBlueButton APRÈS ce passage", out)
        self.assertIn("BigBlueButton 2.7.12", out)
        self.assertIn("[OK]   nos règles sont chargées par nginx", out.replace("\x1b[1;32m", "").replace("\x1b[0m", ""))
        self.assertFalse(os.path.exists(self.e["NGINX_TOOLS_BBB_STATE"]), "--check ne doit pas écrire l'instantané")
        self.lignes_check = out
        self.assertNotIn("+ dpkg-query", out, "sans --verbose, aucune commande affichée")
        # --verbose est transmis à apps/_bbb.py : ses commandes externes s'affichent dans la section
        rc, out, err = self.run_cmd(["bash", prog, "--check", "--verbose"], env)
        self.assertIn("+ dpkg-query -W -f", out + err)
        self.assertIn("+ nginx -T", out + err)

    def test_section_du_sommaire_de_web_monitor(self):
        """web-monitor.py --summary (profil bbb) : section BIGBLUEBUTTON ; mise à jour non suivie d'un --update →
        recommandation et correction proposée (nginx-hardening.sh --update)."""
        import contextlib
        import io
        m = self.module()
        m.resume("before")
        m.resume("after", sauver=True)
        self.paquets("2.7.14")
        spec = importlib.util.spec_from_file_location("wm", script_path("web-monitor.py"))
        wm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wm)
        wm.PROFILE = {"APP_NAME": "bbb", "APP_LABEL": "BigBlueButton"}
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            problemes = wm.show_bbb_state()
        out = f.getvalue()
        self.assertIn("BIGBLUEBUTTON — VERSIONS, CONFIGURATION ET COMPATIBILITÉ AVEC NOS RÈGLES", out)
        self.assertIn("bigbluebutton 1:2.7.12-1 → 1:2.7.14-1", out)
        self.assertTrue(any("mis à jour depuis le dernier nginx-hardening.sh --update" in p[1] for p in problemes))
        wm.run = lambda cmd, timeout=0, env_extra=None: (0, "")
        wm.load_sanity_module = lambda: None
        wm._certificate_via_health = lambda: (None, "")
        class C:
            def get(self, k, i): return 0
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            wm.recommendations(C(), {"non_filtrees": {}, "jails": {"sshd": 1}, "robots": {}, "bbb_problemes": problemes}, {})
        out = f.getvalue()
        self.assertIn("BigBlueButton : BigBlueButton a été mis à jour", out)
        self.assertIn("(nginx-hardening.sh --update)", out.split("CORRECTIONS QUE LE PROGRAMME")[1])
        # Autre application : aucune section
        wm.PROFILE = {"APP_NAME": "odoo"}
        self.assertEqual(wm.show_bbb_state(), [])

    def test_instantane_d_un_autre_emplacement_ignore(self):
        """2.17 sur bbb30 : l'ancienne suite de tests avait écrit le VRAI instantané avec des chemins /tmp/test-rlq-… ;
        « --update » annonçait alors « [FAIL] notre fichier … a DISPARU ». Un instantané qui décrit d'autres emplacements
        est ignoré (dit en une ligne), jamais traité comme une disparition."""
        m = self.module()
        m.resume("before")
        m.resume("after", sauver=True)
        with open(self.e["NGINX_TOOLS_BBB_STATE"], encoding="utf-8") as f:
            etat = json.load(f)
        etat["fichiers_nous"] = {"/tmp/test-rlq-abc/bbb-nginx/zz-nginx-hardening-security.nginx": "abc123456789"}
        with open(self.e["NGINX_TOOLS_BBB_STATE"], "w", encoding="utf-8") as f:
            json.dump(etat, f)
        lignes, problemes = self.module().resume("before")
        texte = "\n".join(lignes)
        self.assertIn("ignoré : il décrit d'autres emplacements de fichiers", texte)
        self.assertNotIn("DISPARU", texte)
        self.assertNotIn("[FAIL]", texte)
        lignes, problemes = self.module().resume("summary")
        self.assertNotIn("DISPARU", "\n".join(lignes))
        self.assertEqual([p for p in problemes if "DISPARU" in p[1]], [])

    def test_vrai_instantane_jamais_ecrit_sous_les_tests(self):
        """Sous les tests (NGINX_TOOLS_TESTS), le fichier réel /var/lib/nginx-tools/bbb-state.json n'est jamais écrit, même
        si une suite plus ancienne ne redirige pas NGINX_TOOLS_BBB_STATE ; un emplacement redirigé reste écrit."""
        m = self.module()
        self.assertFalse(m.enregistrer(m.ETAT_PAR_DEFAUT, {"x": 1}))
        self.assertFalse(m.enregistrer(m.ETAT_PAR_DEFAUT + ".before", {"x": 1}))
        self.assertTrue(m.enregistrer(self.e["NGINX_TOOLS_BBB_STATE"], {"x": 1}))
        os.environ.pop("NGINX_TOOLS_TESTS", None)
        self.assertFalse(m.ecriture_interdite(m.ETAT_PAR_DEFAUT), "hors tests, l'écriture réelle reste permise")

    def test_environnement_restaure_apres_chaque_test(self):
        """Les variables posées par ces tests ne doivent pas fuir vers les tests suivants (même processus)."""
        avant = dict(os.environ)
        self.assertIn("NGINX_TOOLS_BBB_STATE", os.environ)
        self.doCleanups()
        self.assertEqual({k: v for k, v in os.environ.items() if k.startswith(("NGINX_TOOLS_", "WEB_MONITOR_"))},
                         {k: v for k, v in self.avant_env.items() if k.startswith(("NGINX_TOOLS_", "WEB_MONITOR_"))})
        os.environ.clear()
        os.environ.update(avant)
