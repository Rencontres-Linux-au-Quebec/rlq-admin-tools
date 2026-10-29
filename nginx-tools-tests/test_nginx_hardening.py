"""nginx-hardening.sh — étape 10 (HSTS empirique à travers les include), étape 9 (jails fail2ban), message list_db."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import os
import shutil
import subprocess
import re
import unittest

from helpers import EnvTest, CONFIG_DIR, LISTE_EXEMPLE, SCRIPTS_DIR

NGINX_T_PROD = """nginx: configuration file /etc/nginx/nginx.conf test is successful
# configuration file /etc/nginx/sites-enabled/00-catchall-default.conf:
server { listen 443 ssl default_server; server_name _; return 444; }
# configuration file /etc/nginx/sites-enabled/10-prod.conf:
server {
    listen 443 ssl;
    # Only this block really serves the Odoo content - server_name restricted to www, see the comment above.
    include /etc/nginx/snippets/odoo/prod-www.name.conf;
}
# configuration file /etc/nginx/snippets/odoo/prod-www.name.conf:
server_name www.rencontres-linux.quebec;
# configuration file /etc/nginx/snippets/odoo/prod-noncanonical.name.conf:
server_name rencontres-linux.quebec odoo18.rencontres-linux.quebec;
# configuration file /etc/nginx/sites-enabled/legacy.conf:
server { listen 80; server_name ~^legacy\\d+$ *.wild.example http-seulement.example; }
location ~ x {
    allow 127.0.0.1;
    allow 11.126.46.49;
    deny all;
}
location ~* ^/(web/database/.*|xmlrpc/(2/)?db)$ { }
"""


MOCK_F2B_IGNOREIP = 'case "$1 $2" in\n "status ") printf \'%s\\n\' \'|- Number of jail: 2\' \'`- Jail list: sshd, nginx-catchall\';;\n "get sshd"|"get nginx-catchall") printf \'%s\\n\' \'These IP addresses/networks are ignored:\' \'|- 127.0.0.1/8\' \'|- 10.0.0.0/8\' \'`- 11.126.46.49\';;\n reload*) exit 0;;\nesac\n'   # apostrophes : les accents graves de fail2ban ne sont pas des substitutions


class SetupNginxOdoo(EnvTest):
    def setUp(self):
        super().setUp()
        self.f2b = os.path.dirname(self.path("f2b", "x"))
        src = os.path.dirname(self.path("f2b-src", "x"))
        self.modeles = os.path.join(CONFIG_DIR, "fail2ban")
        for n in ("nginx-catchall.filter.conf", "nginx-catchall.jail.conf", "odoo-auth.filter.conf", "odoo-auth.jail.conf.template",
                  "nginx-blocked-probes.filter.conf", "nginx-blocked-probes.jail.conf"):
            p = os.path.join(self.modeles, n)
            if os.path.isfile(p):
                with open(p) as a, open(os.path.join(src, n), "w") as b:
                    b.write(a.read())
        self.write("machine-id", "abc123\n")
        self.prog = self.prepare("nginx-hardening.sh", {
            "/var/www": os.path.dirname(self.path("var-www", "x")), "/var/log/nginx": os.path.dirname(self.path("var-log-nginx", "x")),
            "/etc/default/": os.path.dirname(self.path("etc-default", "x")) + "/", "/etc/fail2ban": self.f2b,
            "/etc/nginx/fail2ban": src, "/etc/machine-id": self.path("machine-id")})
        self.write("nginx-T", NGINX_T_PROD)
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; exit 0')
        self.mock("curl", 'for a in "$@"; do [[ "$prev" == "--resolve" ]] && name="${a%%:*}"; prev="$a"; done\n'
                          'case "$name" in\n'
                          '  www.rencontres-linux.quebec) printf "HTTP/1.1 200 OK\\r\\nStrict-Transport-Security: max-age=31536000\\r\\n\\r\\n";;\n'
                          '  rencontres-linux.quebec|odoo18.rencontres-linux.quebec) printf "HTTP/1.1 301 Moved\\r\\nstrict-transport-security: max-age=300\\r\\n\\r\\n";;\n'
                          '  *) exit 52;;\nesac')
        self.mock("systemctl", f'[[ "$1" == list-unit-files && "$2" == erplibre.service ]] && {{ echo "erplibre.service enabled"; exit 0; }}\n'
                               f'[[ "$1" == show && "$*" == *LogNamespace* ]] && {{ cat {self.d}/ns 2>/dev/null; exit 0; }}\nexit 1')
        self.mock("fail2ban-client", f'L={self.d}/charges\ncase "$1" in\n reload) ls {self.f2b}/jail.d 2>/dev/null | sed "s/\\.conf$//" > $L; '
                                     f'[[ -f {self.d}/casse ]] && sed -i "/odoo-auth/d" $L; exit 0;;\n'
                                     f' status) [[ -z "$2" ]] && exit 0; grep -qx "$2" $L 2>/dev/null;;\nesac')
        for t in ("ss", "ufw"):
            self.mock_exit(t)
        self.write("odoo.conf", "[options]\nproxy_mode = True\n")
        # SECURITY: step 11 (retention) modifies /etc/logrotate.d and the journald configuration with --update -
        # always redirect to the test folder (the suite may run as root on a real server).
        self.write("logrotate.d/nginx", "/var/log/nginx/*.log {\n\tdaily\n\tmissingok\n\trotate 14\n\tcompress\n}\n")
        self.write("logrotate.d/fail2ban", "/var/log/fail2ban.log {\n    weekly\n    rotate 4\n}\n")
        self.env.update(NGINX_HARDENING_LOGROTATE_DIR=os.path.dirname(self.path("logrotate.d", "x")),
                        NGINX_HARDENING_JOURNALD_DIR=os.path.dirname(self.path("systemd", "x")))
        # SECURITY: --update archives /etc/nginx and /etc/fail2ban (--rollback): test folders only, never the real ones.
        racines = [os.path.join(self.d, "sauv-nginx"), os.path.join(self.d, "sauv-fail2ban")]
        for r in racines:
            os.makedirs(r, exist_ok=True)
        self.env.update(NGINX_HARDENING_ARCHIVE_DIR=os.path.join(self.d, "archives"),
                        NGINX_HARDENING_BACKUP_ROOTS=" ".join(racines))

    def exiger_modeles(self):
        """Les tests du jail odoo-auth ont besoin des modèles du dossier nginx-odoo/fail2ban/ (config extraite du zip
        à côté des programmes) : sans eux, test désactivé ET signalé, plutôt qu'un échec obscur."""
        if not os.path.isfile(os.path.join(self.modeles, "odoo-auth.jail.conf.template")):
            self.skipTest(f"modèles fail2ban absents ({self.modeles}) — le dossier nginx-tools-tests/nginx-odoo/ est livré avec la suite")

    def setup(self, *args):
        rc, out, err = self.run_cmd(["bash", self.prog, "--odoo-conf", self.path("odoo.conf"), *args])
        self.assertNotIn("ARRÊT INATTENDU", err, err)
        return out

    def etape(self, out, n):
        m = re.search(rf"--- {n}\).*?(?=\n--- \d+\)|\n=====)", out, re.S)
        return m.group(0) if m else ""

    def _amont(self, http=10000, chat=10002, port_odoo=8069):
        """Configuration nginx de test (sites-enabled/ → lien vers sites-available/) et configuration d'Odoo avec ses ports."""
        base = os.path.dirname(self.path("nginx-dir", "x"))
        os.makedirs(os.path.join(base, "sites-available"), exist_ok=True)
        os.makedirs(os.path.join(base, "sites-enabled"), exist_ok=True)
        fic = os.path.join(base, "sites-available", "30-lab.conf")
        with open(fic, "w", encoding="utf-8") as f:
            f.write(f"upstream odoo {{\n    server 127.0.0.1:{http};\n}}\n# upstream odoo {{ server 127.0.0.1:1; }}\n"
                    f"upstream odoo_chat {{\n    server 127.0.0.1:{chat};\n}}\n"
                    "server {\n    location /websocket {\n        proxy_pass http://odoo_chat;\n        proxy_http_version 1.1;\n"
                    "        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection \"upgrade\";\n        proxy_read_timeout 300s;\n    }\n}\n")
        lien = os.path.join(base, "sites-enabled", "30-lab.conf")
        if not os.path.islink(lien):
            os.symlink(fic, lien)
        self.write("odoo.conf", f"[options]\nproxy_mode = True\nhttp_port = {port_odoo}\ngevent_port = {port_odoo + 3}\n")
        self.env["NGINX_HARDENING_NGINX_DIR"] = base
        self.env["NGINX_HARDENING_BACKUP_DIR"] = os.path.join(base, "sauvegardes")
        return fic

    def test_etape4_amont_nginx_different_du_port_dodoo(self):
        """2.37 : le port de l'« upstream » nginx (10000) n'est pas celui d'Odoo (http_port 8069) : [FAIL] avec le fichier et la ligne ;
        --update corrige les deux amonts dans le fichier réel (lien suivi), sauvegarde hors de sites-enabled, nginx -t, rechargement ; ensuite [OK]."""
        fic = self._amont()
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("l'amont « odoo »", out)
        self.assertIn("vise le port 10000, mais Odoo (HTTP) est configuré sur 8069", out)
        self.assertIn("30-lab.conf:2", out)
        self.assertIn("vise le port 10002, mais Odoo (gevent) est configuré sur 8072", out)
        self.assertIn("--update", out)
        with open(fic, encoding="utf-8") as f:
            self.assertIn("10000", f.read())                              # --check ne modifie rien
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update")), 4)
        self.assertIn("passe du port 10000 à 8069", out)
        self.assertIn("passe du port 10002 à 8072", out)
        with open(fic, encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("server 127.0.0.1:8069;", texte)
        self.assertIn("server 127.0.0.1:8072;", texte)
        self.assertIn("# upstream odoo { server 127.0.0.1:1; }", texte)  # commentaire intact
        self.assertTrue(os.path.islink(os.path.join(os.path.dirname(os.path.dirname(fic)), "sites-enabled", "30-lab.conf")))
        sauv = os.listdir(self.env["NGINX_HARDENING_BACKUP_DIR"])
        self.assertTrue(sauv and sauv[0].endswith(".bak"), sauv)
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("vise le port 8069, qui est celui d'Odoo (HTTP)", out)
        self.assertNotIn("[FAIL]", out.replace("[FAIL] Port", ""))

    def test_etape4_amont_odoo17_ni_verifie_ni_modifie_par_update(self):
        """2.46 : les amonts d'une autre version d'Odoo (odoo17, odoo17_chat : 8069/8072) ne sont ni comptés ni « corrigés » par --update vers les ports de cette instance."""
        fic = self._amont(http=8069, chat=8072, port_odoo=10000)
        base = os.path.dirname(os.path.dirname(fic))
        autre = os.path.join(base, "sites-available", "40-odoo17.conf")
        with open(autre, "w", encoding="utf-8") as f:
            f.write("upstream odoo17 {\n    server 127.0.0.1:8069;\n}\nupstream odoo17_chat {\n    server 127.0.0.1:8072;\n}\n")
        os.symlink(autre, os.path.join(base, "sites-enabled", "40-odoo17.conf"))
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update")), 4)
        self.assertIn("l'amont « odoo17 »", out)
        self.assertIn("est celui d'une autre version d'Odoo (port 8069) : non vérifié, non modifié.", out)
        self.assertIn("passe du port 8069 à 10000", out)                  # the "odoo" upstream of this instance, for its part, is corrected
        with open(autre, encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("server 127.0.0.1:8069;", texte)
        self.assertIn("server 127.0.0.1:8072;", texte)
        self.assertNotIn("10000", texte)

    def test_etape4_amont_nginx_refus_de_nginx_t_restaure(self):
        """2.37 : si nginx -t refuse la correction, l'ancienne version est restaurée, [FAIL], nginx non rechargé."""
        fic = self._amont()
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && exit 1; exit 0')
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update")), 4)
        self.assertIn("ancienne version restaurée", out)
        with open(fic, encoding="utf-8") as f:
            self.assertIn("server 127.0.0.1:10000;", f.read())

    def _site_websocket(self, entete_ws, delai_ws="", extra=""):
        """Site nginx de test : amonts odoo (8069) et odoo_chat (8072) + un location /websocket dont le contenu est donné."""
        base = os.path.dirname(self.path("nginx-dir", "x"))
        os.makedirs(os.path.join(base, "sites-available"), exist_ok=True)
        os.makedirs(os.path.join(base, "sites-enabled"), exist_ok=True)
        fic = os.path.join(base, "sites-available", "40-ws.conf")
        with open(fic, "w", encoding="utf-8") as f:
            f.write("upstream odoo {\n    server 127.0.0.1:8069;\n}\nupstream odoo_chat {\n    server 127.0.0.1:8072;\n}\n"
                    "server {\n    listen 443 ssl;\n    proxy_set_header Host $host;\n"
                    f"    location /websocket {{\n        proxy_pass http://odoo_chat;\n{entete_ws}{delai_ws}    }}\n"
                    "    location / {\n        proxy_pass http://odoo;\n    }\n}\n" + extra)
        lien = os.path.join(base, "sites-enabled", "40-ws.conf")
        if not os.path.islink(lien):
            os.symlink(fic, lien)
        self.write("odoo.conf", "[options]\nproxy_mode = True\nhttp_port = 8069\ngevent_port = 8072\n")
        self.env["NGINX_HARDENING_NGINX_DIR"] = base
        self.env["NGINX_HARDENING_BACKUP_DIR"] = os.path.join(base, "sauvegardes")
        return fic

    ENTETES_WS = "        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection \"upgrade\";\n        proxy_set_header Host $host;\n"

    def test_etape4_websocket_bien_configure(self):
        """2.44 : location /websocket vers le port gevent, HTTP 1.1, Upgrade, Connection, délai de 300 s : [OK] (rien à corriger)."""
        self._site_websocket("        proxy_http_version 1.1;\n" + self.ENTETES_WS, "        proxy_read_timeout 300s;\n")
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("vise le port gevent 8072, HTTP 1.1, en-têtes Upgrade et Connection, délai de lecture 300 s", out)
        self.assertNotIn("Modèle de location", out)

    def test_etape4_websocket_sans_http11_ni_delai_check_puis_update(self):
        """2.44 : sans proxy_http_version 1.1 (défaut 1.0) et avec le délai de lecture par défaut (60 s) : --check signale ([FAIL] / [ATTN]) sans rien modifier ;
        --update ajoute les deux directives dans le fichier réel (lien suivi), avec sauvegarde, nginx -t et rechargement ; ensuite [OK]. Les en-têtes ne sont pas touchés."""
        fic = self._site_websocket(self.ENTETES_WS)
        avant = open(fic, encoding="utf-8").read()
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("n'a pas « proxy_http_version 1.1; »", out)
        self.assertIn("coupe un websocket muet après 60 s", out)
        self.assertIn("40-ws.conf:", out)
        self.assertEqual(open(fic, encoding="utf-8").read(), avant)               # --check ne modifie rien
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update")), 4)
        self.assertIn("« proxy_http_version 1.1; » ajouté", out)
        self.assertIn("« proxy_read_timeout 300s; » ajouté", out)
        texte = open(fic, encoding="utf-8").read()
        self.assertIn("        proxy_pass http://odoo_chat;\n        proxy_read_timeout 300s;\n        proxy_http_version 1.1;\n", texte.replace("        proxy_http_version 1.1;\n        proxy_read_timeout 300s;\n", "        proxy_read_timeout 300s;\n        proxy_http_version 1.1;\n"))
        self.assertEqual(texte.count("proxy_http_version 1.1;"), 1)
        self.assertEqual(texte.count("proxy_read_timeout 300s;"), 1)
        self.assertIn('proxy_set_header Connection "upgrade";', texte)            # headers intact
        self.assertTrue(os.path.islink(os.path.join(os.path.dirname(os.path.dirname(fic)), "sites-enabled", "40-ws.conf")))
        self.assertTrue(os.listdir(self.env["NGINX_HARDENING_BACKUP_DIR"]))
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("websocket (discussions en temps réel) bien configuré", out)

    def test_etape4_websocket_delai_existant_trop_court_est_remplace(self):
        """2.44 : un proxy_read_timeout propre au location (30s) est REMPLACÉ (pas dupliqué) par 300s."""
        fic = self._site_websocket("        proxy_http_version 1.1;\n" + self.ENTETES_WS, "        proxy_read_timeout 30s;\n")
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update")), 4)
        self.assertIn("proxy_read_timeout modifié : 30 s → 300 s", out)
        texte = open(fic, encoding="utf-8").read()
        self.assertEqual(texte.count("proxy_read_timeout"), 1)
        self.assertIn("proxy_read_timeout 300s;", texte)

    def test_etape4_websocket_sans_en_tetes_modele_propose_sans_modifier(self):
        """2.44 : sans Upgrade ni Connection : [FAIL] pour chacun, avec le modèle de location ; JAMAIS de correction automatique (ajouter un proxy_set_header à un location
        retirerait ceux du serveur)."""
        fic = self._site_websocket("        proxy_http_version 1.1;\n", "        proxy_read_timeout 300s;\n")
        avant = open(fic, encoding="utf-8").read()
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update")), 4)
        self.assertIn("n'envoie pas « proxy_set_header Upgrade $http_upgrade; »", out)
        self.assertIn("n'envoie pas « proxy_set_header Connection \"upgrade\"; »", out)
        self.assertIn("Modèle de location pour le websocket d'Odoo", out)
        self.assertIn("proxy_pass http://127.0.0.1:8072;", out)
        self.assertEqual(open(fic, encoding="utf-8").read(), avant)

    def test_etape4_websocket_vers_le_port_http_et_connexions_insuffisantes(self):
        """2.44 : /websocket envoyé au port HTTP (8069) : [FAIL] ; worker_connections < 1024 : [ATTN]. Un site sans /websocket du tout : [FAIL]."""
        base = os.path.dirname(self.path("nginx-dir", "x"))
        os.makedirs(os.path.join(base, "sites-enabled"), exist_ok=True)
        with open(os.path.join(base, "nginx.conf"), "w", encoding="utf-8") as f:
            f.write("events {\n    worker_connections 768;\n}\nhttp {\n    include sites-enabled/*;\n}\n")
        with open(os.path.join(base, "sites-enabled", "50.conf"), "w", encoding="utf-8") as f:
            f.write("upstream odoo {\n    server 127.0.0.1:8069;\n}\nserver {\n    location /websocket {\n        proxy_pass http://odoo;\n    }\n}\n")
        self.write("odoo.conf", "[options]\nproxy_mode = True\nhttp_port = 8069\ngevent_port = 8072\n")
        self.env["NGINX_HARDENING_NGINX_DIR"] = base
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("vise le port HTTP d'Odoo (8069) au lieu du port gevent (8072)", out)
        self.assertIn("worker_connections = 768", out)
        with open(os.path.join(base, "sites-enabled", "50.conf"), "w", encoding="utf-8") as f:
            f.write("upstream odoo {\n    server 127.0.0.1:8069;\n}\nserver {\n    location / {\n        proxy_pass http://odoo;\n    }\n}\n")
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("aucun location vers le port gevent d'Odoo (8072)", out)

    def test_etape4_websocket_vraie_configuration_avec_variable_proxy_pass(self):
        """2.45 : la configuration livrée (nginx-odoo/) écrit « set $odoo_backend_chat odoo_chat; » dans le serveur et « proxy_pass http://$odoo_backend_chat; » dans
        location /websocket (include de snippets) : la variable est RÉSOLUE, le websocket est reconnu et [OK] (2.44 disait à tort « aucun location vers le port gevent »).
        Une variable que le script ne sait pas résoudre n'est jamais un [FAIL]."""
        source = CONFIG_DIR
        if not os.path.isfile(os.path.join(source, "sites-available", "20-rencontres-linux-quebec-dev.conf")):
            self.skipTest("configuration nginx-odoo/ absente")
        base = os.path.dirname(self.path("nginx-dir", "x"))
        shutil.copytree(os.path.join(source, "snippets"), os.path.join(base, "snippets"), dirs_exist_ok=True)
        os.makedirs(os.path.join(base, "sites-enabled"), exist_ok=True)
        shutil.copy(os.path.join(source, "sites-available", "20-rencontres-linux-quebec-dev.conf"), os.path.join(base, "sites-enabled", "20-dev.conf"))
        with open(os.path.join(base, "nginx.conf"), "w", encoding="utf-8") as f:
            f.write("events {\n    worker_connections 768;\n}\nhttp {\n    include /etc/nginx/sites-enabled/*;\n}\n")
        self.write("odoo.conf", "[options]\nproxy_mode = True\nhttp_port = 10000\ngevent_port = 10002\n")
        self.env["NGINX_HARDENING_NGINX_DIR"] = base
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("location « /websocket »", out)
        self.assertIn("vise le port gevent 10002, HTTP 1.1, en-têtes Upgrade et Connection, délai de lecture 720 s", out)
        self.assertNotIn("aucun location vers le port gevent", out)
        self.assertIn("worker_connections = 768", out)                           # vrai avertissement, lui
        # Variable inconnue : jamais un [FAIL]
        with open(os.path.join(base, "sites-enabled", "20-dev.conf"), "a", encoding="utf-8") as f:
            f.write("server {\n    location /websocket {\n        proxy_pass http://$inconnue;\n    }\n}\n")
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("envoie vers une variable que ce script ne sait pas résoudre ($inconnue)", out)

    def test_etape4_websocket_include_snippet_et_entetes_herites(self):
        """2.44 : les « include » sont suivis (en-têtes dans un snippet) ; les en-têtes du serveur sont hérités quand le location n'en définit aucun."""
        base = os.path.dirname(self.path("nginx-dir", "x"))
        os.makedirs(os.path.join(base, "sites-enabled"), exist_ok=True)
        os.makedirs(os.path.join(base, "snippets"), exist_ok=True)
        with open(os.path.join(base, "snippets", "ws.conf"), "w", encoding="utf-8") as f:
            f.write("proxy_http_version 1.1;\nproxy_read_timeout 600s;\n")
        with open(os.path.join(base, "nginx.conf"), "w", encoding="utf-8") as f:
            f.write("events {\n    worker_connections 4096;\n}\nhttp {\n    include sites-enabled/*;\n}\n")
        with open(os.path.join(base, "sites-enabled", "60.conf"), "w", encoding="utf-8") as f:
            f.write("upstream odoo {\n    server 127.0.0.1:8069;\n}\nserver {\n    proxy_set_header Upgrade $http_upgrade;\n    proxy_set_header Connection $connection_upgrade;\n"
                    "    location /websocket {\n        include snippets/ws.conf;\n        proxy_pass http://127.0.0.1:8072;\n    }\n}\n")
        self.write("odoo.conf", "[options]\nproxy_mode = True\nhttp_port = 8069\ngevent_port = 8072\n")
        self.env["NGINX_HARDENING_NGINX_DIR"] = base
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), 4)
        self.assertIn("HTTP 1.1, en-têtes Upgrade et Connection, délai de lecture 600 s", out)
        self.assertNotIn("worker_connections", out)

    def test_etape0a_nginx_avant_les_changements_valide_ou_refuse_avec_aide(self):
        """2.43 : avant tout changement, « nginx -t » est lancé : valide = [OK] ; refusé = [FAIL] avec le message de nginx, les lignes du fichier en cause et la marche à suivre
        (certificat introuvable -> --rename-to / certbot) ; rien n'est modifié par cette étape."""
        fic = self.path("site.conf")
        with open(fic, "w", encoding="utf-8") as f:
            f.write("server {\n  listen 443 ssl;\n  ssl_certificate /etc/letsencrypt/live/odoo.exemple.org/fullchain.pem;\n  ssl_certificate_key /x;\n}\n")
        self.mock("nginx", 'exit 0')
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), "0a")
        self.assertIn("la configuration est valide avant les changements", out)
        self.mock("nginx", f'[[ "$1" == -t ]] && {{ echo "nginx: [emerg] cannot load certificate \\"/etc/letsencrypt/live/odoo.exemple.org/fullchain.pem\\": BIO_new_file() failed in {fic}:3" >&2; exit 1; }}; exit 0')
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), "0a")
        self.assertIn("[FAIL] nginx -t REFUSE la configuration AVANT tout changement", out)
        self.assertIn("nginx -t : nginx: [emerg] cannot load certificate", out)
        self.assertIn("--update --rename-to NOUVEAU_NOM", out)
        self.assertIn(f"Lignes en cause ({fic}, ligne 3)", out)
        self.assertIn("|   ssl_certificate /etc/letsencrypt/live/odoo.exemple.org/fullchain.pem;", out)
        self.mock("nginx", '[[ "$1" == -t ]] && { echo "nginx: [emerg] unknown directive \\"geoip_country\\" in /nonexistent:9" >&2; exit 1; }; exit 0')
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check")), "0a")
        self.assertIn("libnginx-mod-http-geoip", out)

    def test_hors_root_nginx_t_et_iptables_non_verifies_sans_echec(self):
        """2.54 : --check lancé sans root : nginx -t refusé par « Permission denied » et iptables -C refusé par manque de droits
        donnent [ATTN] « non vérifié sans root », jamais [FAIL] « absent » (ni « REFUSE »)."""
        self.env["NGINX_TOOLS_TEST_EUID"] = "1000"
        self.mock("nginx", 'echo "nginx: [emerg] open() \"/run/nginx.pid\" failed (13: Permission denied)" >&2; exit 1')
        self.mock("iptables", 'echo "iptables v1.8.9: can\'t initialize iptables table: Permission denied (you must be root)" >&2; exit 3')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
        self.assertIn("nginx -t (configuration) : non vérifié sans root", out)
        self.assertNotIn("nginx -t REFUSE", out)
        self.assertRegex(out, r"(ufw : règle DENY|iptables : règle DROP) du port \d+/tcp : non vérifié sans root")   # ufw d'abord, puis iptables
        self.assertNotIn("[FAIL] iptables", out)
        self.assertNotIn("[FAIL] ufw", out)

    def _generique(self, *args, copie=False):
        """2.56 : étape 0f. Le dossier nginx/ du dépôt est copié à côté du programme de test ; /etc/nginx est simulé par NGINX_HARDENING_NGINX_DIR."""
        shutil.copytree(os.path.join(SCRIPTS_DIR, "nginx"), os.path.join(os.path.dirname(self.prog), "nginx"), dirs_exist_ok=True)
        dest = self.path("etc-nginx-generique")
        os.makedirs(dest, exist_ok=True)
        if copie:
            shutil.copytree(os.path.join(SCRIPTS_DIR, "nginx", "conf.d"), os.path.join(dest, "conf.d"), dirs_exist_ok=True)
            shutil.copytree(os.path.join(SCRIPTS_DIR, "nginx", "snippets"), os.path.join(dest, "snippets"), dirs_exist_ok=True)
            shutil.copytree(os.path.join(SCRIPTS_DIR, "nginx", "fail2ban"), os.path.join(dest, "fail2ban"), dirs_exist_ok=True)
            os.makedirs(os.path.join(dest, "snippets"), exist_ok=True)
            with open(os.path.join(dest, "snippets", "robots-disallow.conf"), "w", encoding="utf-8") as f:
                f.write("# test\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--odoo-conf", self.path("odoo.conf"), *args],
                                    env_extra={"NGINX_HARDENING_NGINX_DIR": dest})
        self.assertNotIn("ARRÊT INATTENDU", err, err)
        return re.sub(r"\x1b\[[0-9;]*m", "", out), dest

    def test_generique_check_montre_le_plan_sans_rien_ecrire(self):
        """2.56 : --check liste les fichiers génériques à créer dans /etc/nginx (y compris le fichier propre au site) et n'écrit rien."""
        out, dest = self._generique("--check")
        etape = self.etape(out, "0f")
        self.assertIn("creer conf.d/bot_blocker.conf", etape)
        self.assertIn("creer conf.d/odoo-global.conf", etape)
        self.assertIn("creer snippets/robots-disallow.conf", etape)
        self.assertIn("creer fail2ban/nginx-catchall.filter.conf", etape)
        self.assertIn("relancer avec --update", etape)
        self.assertEqual(os.listdir(dest), [], "--check ne doit rien créer")

    def test_generique_identique_rien_a_faire(self):
        """2.56 : tous les fichiers déjà identiques au dépôt : aucun changement proposé."""
        out, _ = self._generique("--check", copie=True)
        self.assertIn("Configuration nginx générique à jour", self.etape(out, "0f"))

    def test_generique_fichier_modifie_propose_le_remplacement(self):
        """2.56 : un fichier modifié à la main est signalé « remplacer » avec un extrait des différences ; --check ne le touche pas."""
        out, dest = self._generique("--check", copie=True)
        chemin = os.path.join(dest, "conf.d", "bot_blocker.conf")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write("# modifié à la main\n")
        avant = open(chemin, encoding="utf-8").read()
        out, _ = self._generique("--check")
        self.assertIn("remplacer conf.d/bot_blocker.conf", self.etape(out, "0f"))
        self.assertIn("Différences pour conf.d/bot_blocker.conf", self.etape(out, "0f"))
        self.assertEqual(open(chemin, encoding="utf-8").read(), avant, "--check ne modifie pas le fichier")

    def test_generique_confirme_remplace_avec_sauvegarde_puis_refuse_si_nginx_t_echoue(self):
        """2.56 : --update dans un vrai terminal : la confirmation « o » remplace le fichier modifié (sauvegarde datée conservée) ;
        si nginx -t refuse, l'état précédent est rétabli (ici nginx -t est simulé en échec)."""
        self._generique("--check", copie=True)            # copie du dossier nginx/ à côté du programme
        dest = self.path("etc-nginx-generique")
        chemin = os.path.join(dest, "conf.d", "bot_blocker.conf")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write("# modifié à la main\n")
        avant = open(chemin, encoding="utf-8").read()
        # nginx -t refuse seulement la version MODIFIÉE (pas celle du dépôt) : l'état d'avant l'étape 0f passe, la nouvelle version échoue
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T\n'
                           f'[[ "$1" == -t ]] && {{ grep -q "modifié à la main" {chemin} && exit 0; [[ -f {chemin} ]] && ! grep -q "modifié à la main" {chemin} && {{ echo "test refusé" >&2; exit 1; }}; }}\n'
                           f'exit 0')
        # Question du courriel (0d, [o/N]) : « n » ; confirmation de l'étape 0f, la suivante : « o »
        texte, _ = self.run_pty(["bash", self.prog, "--odoo-conf", self.path("odoo.conf"), "--update", "--timezone", "none"],
                                [(b"[o/N]", b"n\n", 0.3), (b"[o/N]", b"o\n", 0.3)], env_extra={"NGINX_HARDENING_NGINX_DIR": dest}, timeout=90)
        self.assertIn("nginx -t refuse la configuration générique", texte)
        self.assertEqual(open(chemin, encoding="utf-8").read(), avant, "après refus de nginx -t, le fichier modifié est rétabli")
        self.assertFalse([n for n in os.listdir(os.path.dirname(chemin)) if ".before-generic-" in n], "sauvegarde retirée après rétablissement")
        self.assertEqual(open(os.path.join(dest, "snippets", "robots-disallow.conf"), encoding="utf-8").read(), "# test\n",
                         "fichier préexistant (propre au site) jamais touché")

    def test_generique_confirme_remplace_et_garde_une_sauvegarde_si_nginx_t_passe(self):
        """2.56 : confirmation « o » et nginx -t réussi : le fichier modifié est remplacé par la version du dépôt, la sauvegarde datée reste."""
        self._generique("--check", copie=True)
        dest = self.path("etc-nginx-generique")
        chemin = os.path.join(dest, "conf.d", "bot_blocker.conf")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write("# modifié à la main\n")
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; exit 0')
        texte, _ = self.run_pty(["bash", self.prog, "--odoo-conf", self.path("odoo.conf"), "--update", "--timezone", "none"],
                                [(b"[o/N]", b"n\n", 0.3), (b"[o/N]", b"o\n", 0.3)], env_extra={"NGINX_HARDENING_NGINX_DIR": dest}, timeout=90)
        self.assertIn("nginx -t réussit", texte)
        self.assertEqual(open(chemin, encoding="utf-8").read(), open(os.path.join(SCRIPTS_DIR, "nginx", "conf.d", "bot_blocker.conf"), encoding="utf-8").read())
        sauvegardes = [n for n in os.listdir(os.path.dirname(chemin)) if ".before-generic-" in n]
        self.assertEqual(len(sauvegardes), 1, "une sauvegarde datée de la version modifiée")
        self.assertIn("# modifié à la main", open(os.path.join(os.path.dirname(chemin), sauvegardes[0]), encoding="utf-8").read())

    def test_generique_update_sans_terminal_ne_modifie_rien(self):
        """2.56 : --update sans terminal ne peut pas demander la confirmation : rien n'est écrit, le message l'indique."""
        out, dest = self._generique("--update")
        self.assertIn("Pas de terminal", self.etape(out, "0f"))
        self.assertEqual(os.listdir(dest), [], "sans confirmation, aucun fichier ne doit être créé")

    def test_menu_sans_terminal_refuse_et_l_aide_le_liste(self):
        """2.61 : --menu demande un terminal (sinon refus, code 1, rien n'est lancé) ; l'aide liste --menu."""
        rc, out, err = self.run_cmd(["bash", self.prog, "--menu"])
        self.assertEqual(rc, 1, out + err)
        self.assertIn("--menu demande un terminal", out + err)
        rc, out, err = self.run_cmd(["bash", self.prog, "--help"])
        self.assertIn("--menu", out)

    def _mail(self, *args, mdp="secret-de-test"):
        env = dict(self.env, NGINX_TOOLS_MAIL_PASSWORD=mdp) if mdp else self.env
        rc, out, err = self.run_cmd(["bash", self.prog, "--odoo-conf", self.path("odoo.conf"), *args], env_extra=env if mdp else None)
        self.assertNotIn("secret-de-test", out + err, "le mot de passe ne doit jamais être affiché")
        return re.sub(r"\x1b\[[0-9;]*m", "", out)

    def test_etape0d_courriel_verification_seule_puis_configuration(self):
        """2.38 : l'étape 0d (courriel des programmes) : --check signale l'absence de configuration sans rien écrire ; --update avec les réponses (options + mot de passe
        de l'environnement) écrit le fichier commun SANS mot de passe, le mot de passe dans un fichier à part en 0600, et /etc/msmtprc (mot de passe lu par passwordeval) ;
        deuxième passage : déjà configuré ; un /etc/msmtprc d'un autre auteur est laissé tel quel."""
        conf, mdp, rc = self.env["NGINX_TOOLS_MAIL_CONF"], self.env["NGINX_TOOLS_MAIL_PASSWORD_FILE"], self.env["NGINX_TOOLS_MSMTPRC"]
        out = self.etape(self._mail("--check", mdp=None), "0d")
        self.assertIn("Courriel non configuré", out)
        self.assertFalse(os.path.exists(conf))
        args = ("--update", "--mail-host", "smtp.exemple.org", "--mail-port", "587", "--mail-security", "starttls", "--mail-user", "alertes@exemple.org", "--mail-to", "equipe@exemple.org")
        out = self.etape(self._mail(*args), "0d")
        self.assertIn("Courriel configuré", out)
        with open(conf, encoding="utf-8") as f:
            texte = f.read()
        self.assertIn('MAIL_HOST="smtp.exemple.org"', texte)
        self.assertIn('MAIL_FROM="alertes@exemple.org"', texte)                                 # default: the identifier
        self.assertIn('MAIL_ATTACH_MAX_MB="100"', texte)
        self.assertNotIn("secret-de-test", texte)
        with open(mdp, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "secret-de-test")
        self.assertEqual(os.stat(mdp).st_mode & 0o777, 0o600)
        with open(rc, encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("host smtp.exemple.org", texte)
        self.assertIn("tls_starttls on", texte)
        self.assertIn("passwordeval cat " + mdp, texte)
        self.assertNotIn("secret-de-test", texte)
        out = self.etape(self._mail("--check", mdp=None), "0d")
        self.assertIn("Courriel configuré : smtp.exemple.org:587", out)
        out = self.etape(self._mail("--update", mdp=None), "0d")
        self.assertIn("Courriel déjà configuré", out)
        with open(rc, "w", encoding="utf-8") as f:
            f.write("# fichier d'un autre auteur\n")
        out = self.etape(self._mail("--update", "--mail-setup", *args[1:]), "0d")
        self.assertIn("n'a pas été créé par ce programme", out)
        with open(rc, encoding="utf-8") as f:
            self.assertEqual(f.read(), "# fichier d'un autre auteur\n")

    def test_etape0d_questions_posees_meme_si_la_sortie_est_redirigee(self):
        """2.40 : les questions du courriel sont posées dans un terminal même quand la sortie est redirigée (« | tee journal ») : l'entrée et l'erreur standard suffisent ;
        une introduction dit ce qui est demandé et où c'est gardé ; le mot de passe n'est pas affiché."""
        conf, mdp = self.env["NGINX_TOOLS_MAIL_CONF"], self.env["NGINX_TOOLS_MAIL_PASSWORD_FILE"]
        env = {k: v for k, v in self.env.items() if k != "NGINX_TOOLS_MAIL_PASSWORD"}
        texte, envoyees = self.run_pty(
            ["bash", "-c", 'bash "$0" "$@" | cat', self.prog, "--odoo-conf", self.path("odoo.conf"), "--update", "--timezone", "none"],
            [(b"[o/N] : ", b"o\r", 0.1), (b"(relais) : ", b"smtp.exemple.org\r", 0.1), (b"Port [587] : ", b"\r", 0.1), (b"[starttls] : ", b"\r", 0.1), (b"Nom d'utilisateur : ", b"alertes@exemple.org\r", 0.1),
             (b"Adresse d'exp", b"\r", 0.1), (b"Adresse de destination", b"\r", 0.1), (b"Mot de passe de", b"secret-de-test\r", 0.1), (b"Envoyer un courriel de test", b"n\r", 0.1)],
            env_extra=env, timeout=90)
        self.assertEqual(envoyees, 9, texte)
        self.assertIn("Configuration du courriel des programmes (demandée une seule fois)", texte)
        self.assertNotIn("secret-de-test", texte)
        with open(conf, encoding="utf-8") as f:
            self.assertIn('MAIL_HOST="smtp.exemple.org"', f.read())
        with open(mdp, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "secret-de-test")
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", "--mail-setup")), "0d")                      # without terminal: clear message, nothing blocked
        self.assertIn("Aucun terminal pour poser les questions du courriel", out)

    def test_etape0d_question_oui_non_reponse_non_par_defaut(self):
        """2.41 : avec --update dans un terminal, le setup du courriel est d'abord demandé (o/N, NON par défaut) : Entrée ou « n » saute les questions SMTP, rien n'est écrit."""
        conf = self.env["NGINX_TOOLS_MAIL_CONF"]
        env = {k: v for k, v in self.env.items() if k != "NGINX_TOOLS_MAIL_PASSWORD"}
        for reponse in (b"\r", b"n\r"):
            texte, envoyees = self.run_pty(
                ["bash", self.prog, "--odoo-conf", self.path("odoo.conf"), "--update", "--timezone", "none"],
                [(b"[o/N] : ", reponse, 0.1)], env_extra=env, timeout=90)
            self.assertEqual(envoyees, 1, texte)
            self.assertIn("setup reporté", texte)
            self.assertNotIn("Serveur SMTP (relais)", texte)
            self.assertFalse(os.path.exists(conf))

    def test_etape0d_courriel_refus_des_caracteres_dangereux_et_valeurs_manquantes(self):
        """2.38 : sans terminal ni réponses : [ATTN] et rien d'écrit ; guillemets ou $ dans une réponse : [FAIL], rien d'écrit ; chiffrement inconnu : [FAIL]."""
        conf = self.env["NGINX_TOOLS_MAIL_CONF"]
        out = self.etape(self._mail("--update", mdp=None), "0d")
        self.assertIn("Courriel non configuré : serveur SMTP ou identifiant manquant", out)
        out = self.etape(self._mail("--update", "--mail-host", "smtp.exemple.org", "--mail-user", 'a"b@exemple.org'), "0d")
        self.assertIn("refusés dans les réponses", out)
        out = self.etape(self._mail("--update", "--mail-host", "smtp.exemple.org", "--mail-user", "a@exemple.org", "--mail-security", "tls13"), "0d")
        self.assertIn("starttls, ssl ou none attendus", out)
        self.assertFalse(os.path.exists(conf))

    def _renom(self):
        """Configuration nginx de test pour le changement de nom (odoo-lab → odoo) : un bloc 80 et un bloc 443 avec certificat de l'ancien nom."""
        base = os.path.dirname(self.path("nginx-dir", "x"))
        os.makedirs(os.path.join(base, "sites-enabled"), exist_ok=True)
        fic = os.path.join(base, "sites-enabled", "30-lab.conf")
        with open(fic, "w", encoding="utf-8") as f:
            f.write("server {\n    listen 80;\n    server_name odoo-lab.exemple.org;\n    return 301 https://odoo-lab.exemple.org$request_uri;\n}\n"
                    "server {\n    listen 443 ssl;\n    server_name odoo-lab.exemple.org www.odoo-lab.exemple.org;\n"
                    "    ssl_certificate /etc/letsencrypt/live/odoo-lab.exemple.org/fullchain.pem;\n"
                    "    ssl_certificate_key /etc/letsencrypt/live/odoo-lab.exemple.org/privkey.pem;\n}\n")
        le = os.path.join(base, "letsencrypt")
        self.env.update(NGINX_HARDENING_NGINX_DIR=base, NGINX_HARDENING_BACKUP_DIR=os.path.join(base, "sauvegardes"), NGINX_HARDENING_LETSENCRYPT_DIR=le)
        self.mock("getent", 'echo "203.0.113.7 $2"')
        self.mock("certbot", f'mkdir -p {le}/live/odoo.exemple.org; echo cert > {le}/live/odoo.exemple.org/fullchain.pem; echo "$*" > {self.d}/certbot-args; exit 0')
        return fic, le

    def test_etape0e_changement_de_nom_dns(self):
        """2.39 : --rename-from/--rename-to. Sans --update : rapport seul, rien de modifié. Avec --update : sauvegarde, noms remplacés (server_name, redirection ; le sous-domaine
        www.odoo-lab… n'est pas touché), certbot (webroot) pour le nouveau nom, chemins du certificat remplacés, nginx rechargé ; rappels (DNS, web.base.url)."""
        fic, le = self._renom()
        args = ("--rename-from", "odoo-lab.exemple.org", "--rename-to", "odoo.exemple.org")
        with open(fic, encoding="utf-8") as f:
            avant = f.read()
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check", *args)), "0e")
        self.assertIn("Changement de nom odoo-lab.exemple.org → odoo.exemple.org à faire", out)
        with open(fic, encoding="utf-8") as f:
            self.assertEqual(f.read(), avant)
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", *args)), "0e")
        self.assertIn("certificat de odoo.exemple.org en service", out)
        self.assertIn("web.base.url = https://odoo.exemple.org", out)
        with open(fic, encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("server_name odoo.exemple.org www.odoo-lab.exemple.org;", texte)
        self.assertIn("return 301 https://odoo.exemple.org$request_uri;", texte)
        self.assertIn("/etc/letsencrypt/live/odoo.exemple.org/fullchain.pem", texte)
        self.assertNotIn("live/odoo-lab.exemple.org", texte)
        with open(os.path.join(self.d, "certbot-args"), encoding="utf-8") as f:
            a = f.read()
        self.assertIn("certonly --webroot", a)
        self.assertIn("-d odoo.exemple.org", a)
        sauv = os.listdir(self.env["NGINX_HARDENING_BACKUP_DIR"])
        self.assertTrue(sauv and sauv[0].endswith(".bak"), sauv)

    def test_etape0e_ancien_nom_trouve_dans_nginx_quand_seul_le_nouveau_est_donne(self):
        """2.42 : --rename-to seul (sans --rename-from) : l'ancien nom est cherché dans les server_name de nginx ; un seul nom du même domaine : retenu et le changement se fait ;
        plusieurs : message clair, rien de modifié."""
        fic, le = self._renom()
        with open(fic, encoding="utf-8") as f:
            avant = f.read()
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check", "--rename-to", "odoo.exemple.org")), "0e")
        self.assertIn("Ancien nom (--rename-from non donné) : odoo-lab.exemple.org", out)
        self.assertIn("Changement de nom odoo-lab.exemple.org → odoo.exemple.org à faire", out)
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", "--rename-to", "odoo.exemple.org")), "0e")
        self.assertIn("certificat de odoo.exemple.org en service", out)
        with open(fic, encoding="utf-8") as f:
            self.assertIn("server_name odoo.exemple.org www.odoo-lab.exemple.org;", f.read())
        with open(fic, "w", encoding="utf-8") as f:                                                    # two old possible names of the same domain
            f.write(avant.replace("server_name odoo-lab.exemple.org", "server_name odoo-lab.exemple.org autre.exemple.org", 1))
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", "--rename-to", "odoo.exemple.org")), "0e")
        self.assertIn("Noms trouvés dans les server_name de nginx : autre.exemple.org odoo-lab.exemple.org", out)
        self.assertIn("Plusieurs anciens noms possibles", out)
        self.assertIn("l'ancien nom est introuvable ou ambigu", out)

    def test_etape0e_certificat_existant_refus_de_nginx_et_echec_de_certbot(self):
        """2.39 : certificat du nouveau nom déjà valide : certbot n'est pas lancé ; nginx -t refuse : tout est restauré ; certbot en échec : [FAIL], noms changés
        mais chemins de l'ancien certificat gardés ; noms invalides ou identiques : [FAIL]."""
        fic, le = self._renom()
        args = ("--rename-from", "odoo-lab.exemple.org", "--rename-to", "odoo.exemple.org")
        with open(fic, encoding="utf-8") as f:
            avant = f.read()
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && exit 1; exit 0')
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", *args)), "0e")
        self.assertIn("anciennes versions restaurées", out)
        with open(fic, encoding="utf-8") as f:
            self.assertEqual(f.read(), avant)
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; exit 0')
        self.mock("certbot", 'echo "Challenge failed for domain odoo.exemple.org"; exit 1')
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", *args)), "0e")
        self.assertIn("certbot n'a pas pu obtenir le certificat", out)
        self.assertIn("Challenge failed", out)
        self.assertIn("seront refusé", out.replace("refuseront", "seront refusé"))
        with open(fic, encoding="utf-8") as f:
            texte = f.read()
        self.assertIn("server_name odoo.exemple.org", texte)
        self.assertIn("live/odoo-lab.exemple.org/fullchain.pem", texte)
        self.mock("certbot", f'echo appele > {self.d}/certbot-appele; exit 0')
        os.makedirs(os.path.join(le, "live", "odoo.exemple.org"), exist_ok=True)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30", "-subj", "/CN=odoo.exemple.org", "-addext", "subjectAltName=DNS:odoo.exemple.org",
                        "-keyout", os.path.join(self.d, "k.pem"), "-out", os.path.join(le, "live", "odoo.exemple.org", "fullchain.pem")], check=True, capture_output=True)
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", *args)), "0e")
        self.assertIn("Certificat de odoo.exemple.org déjà présent", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "certbot-appele")))
        with open(fic, encoding="utf-8") as f:
            self.assertIn("live/odoo.exemple.org/fullchain.pem", f.read())
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", "--rename-from", "pas un nom", "--rename-to", "odoo.exemple.org")), "0e")
        self.assertIn("deux noms de domaine complets sont attendus", out)
        out = self.etape(re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update", "--rename-from", "a.exemple.org", "--rename-to", "a.exemple.org")), "0e")
        self.assertIn("identiques", out)

    def test_etape15_bip_byobu_tmux_indique_la_configuration(self):
        """2.24 : si byobu/tmux est installé, l'étape 15 dit QUELLE configuration changer pour le bip de app-log-live.py --chime (rien n'est modifié) ;
        tout est déjà bon : [OK]."""
        self.mock("tmux", 'case "$*" in *bell-action*) echo none;; *visual-bell*) echo on;; *allow-passthrough*) echo off;; esac')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
        bloc = out[out.index("--- 15)"):]
        self.assertIn("~/.byobu/.tmux.conf", bloc)
        for ligne in ("set -g bell-action any", "set -g visual-bell off", "set -g allow-passthrough on"):
            self.assertIn(ligne, bloc)
        self.mock("tmux", 'case "$*" in *bell-action*) echo any;; *visual-bell*) echo off;; *allow-passthrough*) echo on;; esac')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
        self.assertIn("byobu/tmux laisse passer le bip", out[out.index("--- 15)"):])

    def test_etape16_python_requests_vers_le_nom_public(self):
        """2.25 : étape 16 (Odoo) : curl -sI -A python-requests/2.31 https://NOM/mass_mailing_themes depuis le serveur, SANS --resolve. 403 pour python-requests seulement : [FAIL] ;
        403 aussi pour un navigateur : [ATTN] ; sinon [OK] ; nom injoignable : [INFO]."""
        def curl(corps):
            self.mock("curl", 'case "$*" in *--resolve*) printf "HTTP/1.1 200 OK\\r\\nStrict-Transport-Security: max-age=31536000\\r\\n\\r\\n"; exit 0;; esac\n'
                              'for a in "$@"; do [[ "$prev" == "-A" ]] && ua="$a"; prev="$a"; done\n' + corps)

        def e16():
            out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
            return out[out.index("--- 16)"):]
        curl('case "$ua" in python-requests*) printf 403;; *) printf 200;; esac')
        bloc = e16()
        self.assertIn("[FAIL] www.rencontres-linux.quebec : HTTP 403 pour python-requests mais HTTP 200 pour un navigateur", bloc)
        self.assertIn("nginx-odoo-config 1.5", bloc)
        curl('printf 403')
        self.assertIn("[ATTN] www.rencontres-linux.quebec : HTTP 403 aussi pour un navigateur", e16())
        curl('printf 200')
        self.assertIn("[OK]   www.rencontres-linux.quebec : python-requests passe (HTTP 200", e16())
        curl('printf 000; exit 6')
        bloc = e16()
        self.assertIn("pas de réponse depuis ce serveur", bloc)
        self.assertIn("test impossible ici", bloc)

    def test_etape14_geoip_bin_recommande_puis_installe(self):
        """2.19 : geoip-bin n'est PAS facultatif (sans lui, le pays de chaque adresse est cherché sur Internet) : --check le recommande
        (avec [ATTN]), --update l'installe ; paquet introuvable dans les dépôts : dit clairement ; base absente : signalée."""
        appels = os.path.join(self.d, "apt-get.log")
        self.mock("apt-get", f'echo "$@" >> {appels}; exit 0')
        self.mock("apt-cache", 'echo "geoip-bin:"; echo "  Installed: (none)"; echo "  Candidate: 1.6.12-10"')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
        self.assertIn("--- 14) Pays des adresses IP : geoip-bin (base locale) ---", out)
        self.assertIn("[ATTN] geoip-bin absent — RECOMMANDÉ (pas facultatif)", out)
        self.assertFalse(os.path.exists(appels), "--check ne doit rien installer")
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update"))
        self.assertIn("geoip-bin et geoip-database installés", out)
        with open(appels) as f:
            self.assertIn("install -y geoip-bin geoip-database", f.read())
        # Package not found in the repositories (possible case on a recent distribution)
        os.remove(appels)       # (step 0 may have installed other programs: only geoip counts below)
        self.mock("apt-cache", 'echo "geoip-bin:"; echo "  Installed: (none)"; echo "  Candidate: (none)"')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update"))
        self.assertIn("geoip-bin est introuvable dans les dépôts de cette distribution", out)
        self.assertNotIn("geoip", open(appels).read() if os.path.exists(appels) else "", "rien à installer si le paquet n'existe pas")
        # Installed and database responding: [OK]; installed without database: [ATTN]
        self.mock("geoiplookup", 'echo "GeoIP Country Edition: US, United States"')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
        self.assertIn("[OK]   geoip-bin installé et sa base répond", out)
        self.mock("geoiplookup", 'echo "GeoIP Country Edition: IP Address not found"')
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--check"))
        self.assertIn("[ATTN] geoip-bin est installé mais sa base de pays est introuvable", out)

    def test_etape12_migration_de_l_ancienne_liste_et_modeles(self):
        """Les listes vivent dans /etc/default (hors des archives) : --check signale l'ANCIEN emplacement ; --update migre apps/team-ips.list
        (copie, ancien fichier renommé .migre), crée un modèle de lieux, ne modifie JAMAIS un fichier existant."""
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        blanche, lieux = self.env["NGINX_TOOLS_WHITE_LIST"], self.env["NGINX_TOOLS_IP_LOCATION"]
        ancien = os.path.join(os.path.dirname(self.prog), "apps", "team-ips.list")
        with open(ancien, "w", encoding="utf-8") as f:
            f.write(LISTE_EXEMPLE)
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup())
        self.assertIn("[ATTN] Liste blanche : ANCIEN emplacement", out)
        self.assertIn("— --update la migre vers", out)
        self.assertFalse(os.path.exists(blanche), "--check ne doit rien écrire")
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update"))
        self.assertIn("[OK]   Liste blanche migrée", out)
        self.assertEqual(open(blanche).read(), LISTE_EXEMPLE)
        self.assertFalse(os.path.exists(ancien))
        self.assertTrue(os.path.exists(ancien + ".migre"))
        self.assertIn("Lieux : modèle créé", out)
        self.assertTrue(os.path.exists(lieux))
        self.assertIn("203.0.113.5", open(os.path.join(snip, "team-ips-geo.conf")).read())             # nginx generated from the migrated list
        # Files present: never modified
        with open(blanche, "a") as f:
            f.write("192.0.2.77    # ajout\n")
        with open(lieux, "w") as f:
            f.write("198.51.100.0/24   # Université exemple   [partagée]\n")
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update"))
        self.assertIn("[OK]   Liste blanche :", out)
        self.assertIn("(4 adresse(s))", out)
        self.assertIn("[OK]   Lieux :", out)
        self.assertIn("(1 plage(s))", out)
        self.assertIn("192.0.2.77", open(blanche).read())
        self.assertEqual(open(lieux).read(), "198.51.100.0/24   # Université exemple   [partagée]\n")
        # Neither old list nor white list: an empty file to fill in is created (nothing is invented)
        os.remove(blanche)
        out = re.sub(r"\x1b\[[0-9;]*m", "", self.setup("--update"))
        self.assertIn("Liste blanche créée VIDE", out)
        self.assertEqual([l for l in open(blanche).read().splitlines() if l.strip() and not l.startswith("#")], [])

    def test_lieux_proteges_ignores_par_fail2ban_sans_acces_nginx(self):
        """Un lieu [protégée] est ignoré par fail2ban (jamais banni) mais n'entre PAS dans les fichiers nginx (aucun accès à DEV/LAB) ;
        un lieu seulement [partagée] n'est ni protégé ni autorisé."""
        self.exiger_modeles()
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        self.liste_blanche(LISTE_EXEMPLE)
        self.lieux("203.0.113.64/26   # Bureau   [protégée]\n198.51.100.128/25   # Université exemple   [partagée]\n")
        with open(os.path.join(self.d, "nginx-T"), "a") as f:
            f.write("geo $is_trusted_ip {\n    default 0;\n    127.0.0.1 1;\n}\n")
        self.mock("fail2ban-client", MOCK_F2B_IGNOREIP)
        out = self.setup()
        ligne = next(l for l in out.splitlines() if "adresses de l'équipe NON ignorées" in l)
        self.assertIn("203.0.113.64/26", ligne)
        self.assertNotIn("198.51.100.128/25", ligne)
        self.setup("--update")
        ign = open(os.path.join(self.f2b, "jail.d", "zz-nginx-hardening-ignoreip.local")).read()
        self.assertIn("203.0.113.64/26", ign)
        self.assertNotIn("198.51.100.128/25", ign)
        for fichier in ("team-ips-geo.conf", "team-ips-allow.conf"):
            contenu = open(os.path.join(snip, fichier)).read()
            self.assertIn("203.0.113.5", contenu)                                                      # white list: access
            self.assertNotIn("203.0.113.64", contenu)                                                  # protected place: NO access
            self.assertNotIn("198.51.100.128", contenu)

    def test_hsts_empirique_a_travers_les_include(self):
        """1.14 : l'analyse statique croyait que « nginx -T » développe les include — faux [FAIL] et faux « sans nom »."""
        e10 = self.etape(self.setup(), 10)
        self.assertIn("HSTS présent — www.rencontres-linux.quebec", e10)
        self.assertIn("HSTS présent — odoo18.rencontres-linux.quebec (HTTP 301, max-age=300s", e10)
        self.assertIn("http-seulement.example : aucune réponse HTTPS", e10)      # name in compact line (fixed in 1.14)
        self.assertNotIn("Seul ce bloc", e10)                                     # un commentaire n'est jamais un nom
        self.assertNotIn("legacy", e10)                                           # regex names ignored
        self.assertNotIn("[FAIL]", e10)

    def test_jail_blocked_probes_et_ignoreip_de_l_equipe(self):
        """2.6 : jail nginx-blocked-probes installée ; adresses de l'équipe (table $is_trusted_ip) ignorées par fail2ban."""
        self.exiger_modeles()
        self.liste_blanche(LISTE_EXEMPLE)
        with open(os.path.join(self.d, "nginx-T"), "a") as f:
            f.write("geo $is_trusted_ip {\n    default 0;\n    127.0.0.1 1;\n    11.126.46.49 1;\n    11.148.77.5 1;\n}\n")
        self.mock("fail2ban-client", MOCK_F2B_IGNOREIP)
        out = self.setup()
        self.assertIn("Jail nginx-blocked-probes absent", out)
        ligne = next(l for l in out.splitlines() if "adresses de l'équipe NON ignorées" in l)
        self.assertIn("(jails : nginx-catchall sshd)", ligne)
        self.assertIn("11.148.77.5", ligne)                                    # table $is_trusted_ip de nginx
        self.assertIn("100.64.0.21", ligne)                                    # liste blanche (/etc/default/nginx-tools-white-list.conf)
        self.assertNotRegex(ligne, r" 11\.126\.46\.49( |$)")               # already ignored
        out = self.setup("--update")
        self.assertIn("Jail nginx-blocked-probes installé", out)
        self.assertTrue(os.path.isfile(os.path.join(self.f2b, "jail.d", "nginx-blocked-probes.conf")))
        ign = open(os.path.join(self.f2b, "jail.d", "zz-nginx-hardening-ignoreip.local")).read()
        self.assertIn("[DEFAULT]", ign)
        self.assertRegex(ign, r"ignoreip = 127\.0\.0\.1/8 ::1 10\.0\.0\.0/8 11\.126\.46\.49 ")   # existing ones kept, at the top
        for ip in ("11.148.77.5", "100.64.0.21", "198.51.100.9"):
            self.assertIn(ip, ign)

    def test_etape12_adresses_de_l_equipe_generees(self):
        """2.8 : team-ips-geo.conf et team-ips-allow.conf générés depuis apps/team-ips.list ; nginx -t avant rechargement ;
        ancienne version restaurée si nginx refuse ; entrée invalide : rien n'est écrit."""
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        liste = self.liste_blanche(LISTE_EXEMPLE)
        geo = os.path.join(snip, "team-ips-geo.conf")
        out = self.setup()
        self.assertIn("team-ips-geo.conf absent — --update le régénérera", out)
        self.assertFalse(os.path.exists(geo))                                    # --check: nothing written
        out = self.setup("--update")
        self.assertRegex(open(geo).read(), r"(?m)^100\.64\.0\.21\s+1;   # Étienne \(Tailscale : poste-2\)$")
        self.assertRegex(open(os.path.join(snip, "team-ips-allow.conf")).read(), r"(?m)^allow 198\.51\.100\.9;\s+# Mathis$")
        self.assertIn("team-ips-allow.conf à jour", self.setup())
        # Address added, but nginx -t refuses: old version restored
        avant = open(geo).read()
        with open(liste, "a") as f:
            f.write("198.51.100.7    # bénévole\n")
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && exit 1; exit 0')
        out = self.setup("--update")
        self.assertIn("ancienne version restaurée, nginx NON rechargé", out)
        self.assertEqual(open(geo).read(), avant)
        self.assertIn("nginx -t refuse AUSSI la version d'avant", out + "")                  # ici le mock refuse toujours
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && {{ echo "nginx: [emerg] unknown directive \\"boum\\" in /etc/nginx/x.conf:3" >&2; exit 1; }}; exit 0')
        out = self.setup("--update")
        self.assertIn('nginx -t : nginx: [emerg] unknown directive "boum" in /etc/nginx/x.conf:3', out)
        self.assertIn("DÉJÀ invalide", out)
        # nginx accepts: address added
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; exit 0')
        self.setup("--update")
        self.assertIn("198.51.100.7", open(geo).read())
        # Invalid entry: nothing is written
        with open(liste, "a") as f:
            f.write("pas-une-adresse    # erreur de saisie\n")
        out = self.setup("--update")
        self.assertIn("entrée(s) invalide(s) — ligne", out)
        self.assertIn("« pas-une-adresse »", out)
        self.assertNotIn("pas-une-adresse", open(geo).read())

    def test_etape12_recharge_si_les_fichiers_sont_plus_recents_que_la_configuration_chargee(self):
        """2.28 : fichiers team-ips-*.conf déjà à jour, mais nginx tourne depuis AVANT leur écriture (adresse refusée en 403) : --check le signale,
        --update recharge nginx (nginx -t d'abord) ; configuration chargée plus récente que les fichiers : rien à faire ; âge inconnu : rien."""
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        self.liste_blanche(LISTE_EXEMPLE)
        self.setup("--update")
        self.env["NGINX_HARDENING_WORKER_AGE"] = "0"                   # workers started just now: configuration loaded up to date
        out = self.setup("--update")
        self.assertIn("team-ips-allow.conf à jour", out)
        self.assertNotIn("plus récents que la configuration chargée", out)
        self.env["NGINX_HARDENING_WORKER_AGE"] = "86400"               # yesterday's workers, files written a few seconds ago
        out = self.setup()
        self.assertIn("plus récents que la configuration chargée par nginx", out)
        self.assertIn("--update le recharge", out)
        self.mock("systemctl", f'echo "$@" >> {self.d}/systemctl.log; exit 0')
        out = self.setup("--update")
        self.assertIn("nginx rechargé : team-ips-*.conf étaient plus récents que la configuration chargée.", out)
        self.assertIn("reload nginx", open(os.path.join(self.d, "systemctl.log")).read())
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && {{ echo "nginx: [emerg] boum" >&2; exit 1; }}; exit 0')
        out = self.setup("--update")
        self.assertIn("nginx -t refuse la configuration — nginx NON rechargé", out)
        self.env["NGINX_HARDENING_WORKER_AGE"] = "inconnu"
        self.assertNotIn("plus récents que la configuration chargée", self.setup("--update"))

    def test_etape12b_reseaux_partages_generes_depuis_les_lieux(self):
        """2.30 : les lieux [partagée] deviennent shared-ips-geo.conf (limites de débit plus larges) ; --check le signale s'il est absent ; ni [protégée] seul ni adresse
        invalide ; sans lieu partagé : fichier sans adresse ; nginx -t refusé : ancienne version restaurée."""
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        dst = os.path.join(snip, "shared-ips-geo.conf")
        lieux = os.path.join(self.d, "lieux.conf")
        self.env["NGINX_TOOLS_IP_LOCATION"] = lieux
        with open(lieux, "w", encoding="utf-8") as f:
            f.write("192.0.2.0/24   # Université exemple   [partagée]\n198.51.100.7   # Bureau   [protégée]\n2001:db8::/32   # Réseau v6   [partagée]\nnimporte quoi   # x   [partagée]\n")
        if os.path.exists(dst):
            os.remove(dst)
        self.liste_blanche(LISTE_EXEMPLE)
        out = self.setup()
        self.assertIn("shared-ips-geo.conf absent", out)
        self.assertFalse(os.path.exists(dst))
        self.mock("systemctl", f'echo "$@" >> {self.d}/systemctl.log; exit 0')
        out = self.setup("--update")
        self.assertIn("Réseaux partagés régénérés (2)", out)
        texte = open(dst, encoding="utf-8").read()
        self.assertRegex(texte, r"(?m)^192\.0\.2\.0/24\s+1;\s+# Université exemple$")
        self.assertRegex(texte, r"(?m)^2001:db8::/32\s+1;")
        self.assertNotIn("198.51.100.7", texte)
        self.assertNotIn("nimporte", texte)
        self.assertIn("à jour (2 réseau(x) partagé(s))", self.setup("--update"))
        with open(lieux, "w", encoding="utf-8") as f:
            f.write("198.51.100.7   # Bureau   [protégée]\n")
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && {{ echo "nginx: [emerg] boum" >&2; exit 1; }}; exit 0')
        out = self.setup("--update")
        self.assertIn("ancienne version restaurée", out)
        self.assertIn("192.0.2.0/24", open(dst, encoding="utf-8").read())

    def test_etape12_les_fichiers_existent_toujours(self):
        """2.22 : nginx refuse un include à joker sans fichier correspondant ([emerg] open() ... No such file) : les deux fichiers
        team-ips-*.conf existent donc TOUJOURS après --update — sans liste blanche, et après un refus de nginx -t (jamais de rm)."""
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        geo, allow = (os.path.join(snip, f"team-ips-{t}.conf") for t in ("geo", "allow"))
        for f in (geo, allow):
            if os.path.exists(f):
                os.remove(f)
        self.setup()                                                             # --check: nothing is created
        self.assertFalse(os.path.exists(geo))
        # Without white list: files created anyway
        blanche = self.env["NGINX_TOOLS_WHITE_LIST"]
        self.env["NGINX_TOOLS_WHITE_LIST"] = os.path.join(self.d, "inexistante.conf")
        self.setup("--update")
        for f in (geo, allow):                                                   # --update creates a list template then generates: the files exist
            self.assertTrue(os.path.exists(f), f)
        for f in (geo, allow):
            os.remove(f)
        # With white list, but nginx -t refuses and there was nothing before: valid empty files, not deleted
        self.env["NGINX_TOOLS_WHITE_LIST"] = blanche
        self.liste_blanche(LISTE_EXEMPLE)
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && exit 1; exit 0')
        self.setup("--update")
        for f in (geo, allow):
            self.assertTrue(os.path.exists(f), f)
            self.assertTrue(open(f).read().startswith("# vide"))

    def test_fragments_generes_absents_et_nginx_arrete(self):
        """2.53 : cas réel — les trois fragments générés absents et nginx arrêté. nginx -t refusait tant que shared-ips-geo.conf (étape 12b) n'existait
        pas : l'étape 12 restaurait alors des team-ips-*.conf VIDES (liste blanche perdue) et « systemctl reload » échouait sur le service arrêté.
        --update crée les fragments manquants AVANT tout nginx -t, garde les adresses de l'équipe et DÉMARRE nginx arrêté ; --check ne crée rien."""
        snip = os.path.dirname(self.path("snippets", "x"))
        self.env["NGINX_HARDENING_SNIPPETS_DIR"] = snip
        frag = {n: os.path.join(snip, n) for n in ("team-ips-geo.conf", "team-ips-allow.conf", "shared-ips-geo.conf")}
        for f in frag.values():
            if os.path.exists(f):
                os.remove(f)
        self.liste_blanche(LISTE_EXEMPLE)
        # nginx -t refuse tant qu'un des trois fragments manque (comme les include par nom exact de odoo-global.conf)
        tests_f = " && ".join(f'[[ -e {f} ]]' for f in frag.values())
        self.mock("nginx", f'[[ "$1" == -T ]] && cat {self.d}/nginx-T; [[ "$1" == -t ]] && {{ {tests_f} || {{ echo "nginx: [emerg] open() \\"{frag["shared-ips-geo.conf"]}\\" failed (2: No such file or directory) in /etc/nginx/conf.d/odoo-global.conf:61" >&2; exit 1; }}; }}; exit 0')
        out = self.setup()                                                       # --check: nothing is created, but the advice points to --update
        for f in frag.values():
            self.assertFalse(os.path.exists(f), f)
        self.assertIn("ce fragment est GÉNÉRÉ par ce script", out)
        # nginx stopped: is-active fails; start succeeds
        self.mock("systemctl", f'echo "$@" >> {self.d}/systemctl.log; [[ "$1" == is-active ]] && exit 3; '
                               f'[[ "$1" == list-unit-files && "$2" == erplibre.service ]] && {{ echo "erplibre.service enabled"; exit 0; }}; exit 0')
        out = self.setup("--update")
        self.assertIn("était absent : créé vide pour que nginx -t réussisse", out)
        self.assertIn("nginx -t : la configuration est valide avant les changements", out)
        self.assertNotIn("ancienne version restaurée", out)
        self.assertIn("Adresses de l'équipe régénérées depuis la liste blanche ; nginx -t réussi, nginx démarré (il était arrêté).", out)
        self.assertRegex(open(frag["team-ips-geo.conf"]).read(), r"(?m)^100\.64\.0\.21\s+1;")      # la liste blanche n'est PAS perdue
        self.assertRegex(open(frag["team-ips-allow.conf"]).read(), r"(?m)^allow 198\.51\.100\.9;")
        self.assertTrue(os.path.exists(frag["shared-ips-geo.conf"]))
        journal = open(os.path.join(self.d, "systemctl.log")).read()
        self.assertIn("start nginx", journal)
        self.assertNotIn("reload nginx", journal)

    def test_report_err(self):
        out = self.setup("--report-err")
        self.assertIn("--- 13)", out)                                                # the program ran entirely
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : nginx-hardening\.sh v2\.\d+\.\d{8}\.\d{6} — commande : nginx-hardening\.sh --odoo-conf \S+\n")
        self.assertRegex(rapport, r"Bilan     : \d+ échec\(s\), \d+ avertissement\(s\), 0 recommandation\(s\) à traiter — sortie de \d+ ligne")
        self.assertIn("Application : ", rapport)
        self.assertTrue(rapport.rstrip().endswith("FIN DU RAPPORT " + "=" * 38))

    def test_etape13_courriel(self):
        """2.9 : étape 13 — lignes [OK]/[ATTN]/[FAIL] de app-health-check.py --check-email-dns comptées, détails affichés."""
        self.write("prog/app-health-check.py", 'print("[OK] relais SMTP joignable : smtp.x:587 (starttls)")\n'
                                               'print("[FAIL] aucun SPF pour rencontres-linux.quebec : refus")\n'
                                               'print("       ajouter au DNS : rencontres-linux.quebec. TXT \\"v=spf1 include:x -all\\"")\n'
                                               'print("[ATTN] aucun DMARC pour rencontres-linux.quebec")\n')
        out = self.setup()
        bloc = out[out.index("--- 13)"):]
        self.assertRegex(bloc, r"\[OK\]\s+relais SMTP joignable")
        self.assertRegex(bloc, r"\[FAIL\]\s+aucun SPF pour rencontres-linux\.quebec")
        self.assertIn('ajouter au DNS : rencontres-linux.quebec. TXT "v=spf1 include:x -all"', bloc)
        self.assertIn("app-health-check.py --test-email", bloc)
        # No result recognized (e.g. program refusing the option): never "all is in order" without verification
        self.write("prog/app-health-check.py", 'import sys\nprint("usage : app-health-check.py [-h]")\n'
                                               'print("app-health-check.py : erreur : argument --target requis", file=sys.stderr)\nsys.exit(2)\n')
        out = self.setup()
        bloc = out[out.index("--- 13)"):]
        self.assertIn("vérification du courriel impossible : app-health-check.py n'a produit aucun résultat reconnu", bloc)
        self.assertNotIn("tout est en ordre", out)

    def test_jail_odoo_auth_genere_charge_puis_difference_detectee(self):
        """1.16 : jail odoo-auth généré pour CE serveur, vérifié chargé ; liste blanche modifiée → « différent »."""
        self.exiger_modeles()
        self.assertIn("Jail odoo-auth absent", self.etape(self.setup(), 9))
        out = self.setup("--update")
        self.assertIn("Jail odoo-auth : chargé et actif", out)
        # 1.20: "systemd-journal[journalmatch=...]" made fail2ban-regex crash - journalmatch goes through -m
        self.assertIn('journalctl -u erplibre.service --since "10 min ago" --no-pager > /tmp/odoo-journal.txt', out)   # 2.26 : test sur texte
        self.assertRegex(out, r"fail2ban-regex /tmp/odoo-journal\.txt \S+/filter\.d/odoo-auth\.conf")
        self.assertIn("IGNORÉE par fail2ban", out)                                                                   # the team's address is never counted
        self.assertIn("MAUVAIS mot de passe", out)                    # 1.21: procedure explained
        self.assertNotIn("[journalmatch", out)
        jail = open(os.path.join(self.f2b, "jail.d", "odoo-auth.conf")).read()
        self.assertIn("journalmatch = _SYSTEMD_UNIT=erplibre.service", jail)
        self.assertIn("11.126.46.49", jail)                                     # ignoreip <- nginx white list
        self.assertNotRegex(jail, r"@[A-Z_]+@", "marqueur du modèle non remplacé")
        self.assertNotIn("MODÈLE", jail)
        self.assertNotIn("et l'installe vers", jail, "phrase orpheline du paragraphe « MODÈLE »")   # fixed in 1.18
        self.assertEqual(jail.count("127.0.0.1 "), 0, "127.0.0.1 répétée alors que couverte par 127.0.0.1/8")
        self.assertIn("Jail odoo-auth à jour", self.etape(self.setup(), 9))
        with open(self.path("nginx-T"), "a") as f:
            f.write("location ~ y {\n    allow 198.51.100.200;\n    deny all;\n}\n")
        self.assertIn("Jail odoo-auth différent", self.etape(self.setup(), 9))

    def test_jail_odoo_auth_lit_le_fichier_quand_odoo_a_un_logfile(self):
        """2.32 : configuration d'Odoo avec logfile → jail odoo-auth en backend auto + logpath (plus de journalmatch systemd), ports lus dans la configuration."""
        self.exiger_modeles()
        journal = self.path("odoo-fichier.log")
        open(journal, "w").close()
        self.write("odoo.conf", f"[options]\nproxy_mode = True\nhttp_port = 8169\ngevent_port = 8172\nlogfile = {journal}\n")
        out = self.setup("--update")
        self.assertIn("Ports : HTTP 8169, gevent 8172", out)
        self.assertIn("Jail odoo-auth", self.etape(out, 9))
        jail = open(os.path.join(self.f2b, "jail.d", "odoo-auth.conf")).read()
        self.assertIn("backend      = auto", jail)
        self.assertIn(f"logpath      = {journal}", jail)
        self.assertNotIn("journalmatch", jail)
        self.assertIn("11b)", out)

    def test_jail_non_charge_signale(self):
        self.exiger_modeles()
        open(self.path("casse"), "w").close()
        out = self.setup("--update")
        self.assertIn("Jail odoo-auth : NON chargé", out)

    def test_namespace_de_journal(self):
        self.exiger_modeles()
        self.write("ns", "odoo\n")
        self.setup("--update")
        jail = open(os.path.join(self.f2b, "jail.d", "odoo-auth.conf")).read()
        self.assertIn("backend      = systemd[journalpath=/var/log/journal/abc123.odoo]", jail)

    def test_message_list_db_selon_la_regle_nginx_active(self):
        """1.15 : l'ancien message affirmait à tort « déjà restreint par IP »."""
        e8 = self.etape(self.setup(), 8)
        self.assertIn("toutes les routes /web/database/*", e8)
        self.assertIn("/jsonrpc", e8)
        with open(self.path("nginx-T")) as f:
            t = f.read().replace("web/database/.*|xmlrpc", "web/database/(manager|selector)|xmlrpc")
        self.write("nginx-T", t)
        self.assertIn("/web/database/list (liste des bases en JSON) reste joignable par TOUS", self.etape(self.setup(), 8))


if __name__ == "__main__":
    unittest.main()
