"""Configuration nginx et fail2ban (nginx-tools-tests/nginx-odoo/) — vérifications statiques, sans nginx : syntaxe (accolades,
directives terminées par « ; »), include existants, pas de location en double, motifs (filtre à robots, limite de
connexion, règle /web/database/*), filtres fail2ban sur des lignes réelles ; et le VRAI fail2ban-regex s'il est
installé (serveur)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"   # configuration nginx des serveurs Odoo (nginx-odoo/)
NATURE_TESTS = "conformité"   # run-all 1.188 (statistiques) : configuration nginx / fail2ban lue et vérifiée sans nginx (un test qui lance un programme reste « fonctionnel »)
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import CONFIG_DIR, script_path

# Snippets fournis par les paquets Debian (pas par ce projet) : présents sur tout serveur, absents du dépôt.
SNIPPETS_SYSTEME = {"snakeoil.conf", "fastcgi-php.conf"}

NAVIGATEURS = ["Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
               "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
               "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 Version/18.1 Mobile/15E148 Safari/604.1",
               "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Firefox/140.0"]


def conf_files():
    return sorted(glob.glob(os.path.join(CONFIG_DIR, "**", "*.conf"), recursive=True))


def lire(rel):
    with open(os.path.join(CONFIG_DIR, rel), encoding="utf-8") as f:
        return f.read()


def tokens(text):
    """Analyseur lexical minimal de la syntaxe nginx : mots, « ; », « { », « } » ; chaînes entre guillemets et
    commentaires gérés comme nginx (un « { » non protégé termine un mot, d'où l'obligation de mettre entre
    guillemets une expression régulière qui en contient)."""
    i, n, mot = 0, len(text), ""
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            mot += text[i:j + 1]
            i = j + 1
            continue
        if c == "#" and not mot:
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c.isspace() or c in ";{}":
            if mot:
                yield mot
                mot = ""
            if c in ";{}":
                yield c
            i += 1
            continue
        mot += c
        i += 1
    if mot:
        yield mot


@unittest.skipUnless(os.path.isdir(CONFIG_DIR), f"configuration absente : {CONFIG_DIR}")
class ConfigNginx(unittest.TestCase):
    def test_syntaxe_accolades_et_points_virgules(self):
        for f in conf_files():
            if "/fail2ban/" in f:
                continue
            with self.subTest(fichier=os.path.relpath(f, CONFIG_DIR)):
                profondeur, en_cours = 0, []
                for t in tokens(open(f, encoding="utf-8").read()):
                    if t == "{":
                        profondeur += 1; en_cours = []
                    elif t == "}":
                        self.assertEqual(en_cours, [], f"directive sans « ; » avant « }} » : {' '.join(en_cours)}")
                        profondeur -= 1
                        self.assertGreaterEqual(profondeur, 0, "« } » en trop")
                    elif t == ";":
                        en_cours = []
                    else:
                        en_cours.append(t)
                self.assertEqual(profondeur, 0, "accolades non équilibrées")
                self.assertEqual(en_cours, [], f"dernière directive sans « ; » : {' '.join(en_cours)}")

    def test_include_pointent_vers_des_fichiers_existants(self):
        for f in conf_files():
            for cible in re.findall(r"^\s*include\s+(/etc/nginx/(?:snippets|conf\.d)/\S+?);", open(f, encoding="utf-8").read(), re.M):
                if "*" in cible or os.path.basename(cible) in SNIPPETS_SYSTEME or os.path.basename(cible).startswith(("team-ips-", "shared-ips-")):      # team-ips-* et shared-ips-* : GÉNÉRÉS, jamais livrés
                    continue
                with self.subTest(fichier=os.path.relpath(f, CONFIG_DIR), include=cible):
                    self.assertTrue(os.path.isfile(os.path.join(CONFIG_DIR, cible[len("/etc/nginx/"):])), "fichier inclus absent")

    def test_entetes_hsts_valides(self):
        """Valeur Strict-Transport-Security conforme (RFC 6797) : un « ; » manquant la rend invalide — les navigateurs
        ignorent alors l'en-tête, sans aucune erreur de nginx."""
        valeurs = []
        for f in conf_files():
            valeurs += [(os.path.relpath(f, CONFIG_DIR), v) for v in
                        re.findall(r'^\s*add_header\s+Strict-Transport-Security\s+"([^"]*)"', open(f, encoding="utf-8").read(), re.M | re.I)]
        self.assertTrue(valeurs, "aucun en-tête HSTS trouvé")
        for fichier, v in valeurs:
            with self.subTest(fichier=fichier, valeur=v):
                self.assertRegex(v, r"^max-age=\d+(; ?includeSubDomains)?(; ?preload)?$")

    def test_requete_du_serveur_vers_lui_meme_exemptee_du_filtre_a_robots(self):
        """1.5 : Odoo s'appelle par son nom public (python-requests, ex. mass_mailing_themes) : $remote_addr == $server_addr désactive le blocage par User-Agent (sinon 403)."""
        texte = lire("snippets/securite-commune.conf")
        m = re.search(r"if \(\$remote_addr = \$server_addr\) \{\s*set \$is_bad_bot 0;\s*\}", texte)
        self.assertIsNotNone(m, "exception $remote_addr = $server_addr absente")
        self.assertLess(m.start(), texte.index("if ($is_bad_bot_enforced)"), "l'exception doit précéder le refus 403")

    def test_une_seule_location_robots_txt(self):
        """Une deuxième « location = /robots.txt » ferait échouer nginx -t (« duplicate location »)."""
        n = sum(len(re.findall(r"^\s*location\s*=\s*/robots\.txt", open(f, encoding="utf-8").read(), re.M)) for f in conf_files())
        self.assertEqual(n, 1)

    def test_filtre_a_robots(self):
        texte = lire("conf.d/bot_blocker.conf")
        # « (?:\\ |\S)+ » : un motif peut contenir des espaces protégées (« Palo\ Alto\ Networks »), valides pour nginx.
        motifs = [re.compile(m.group(1).strip('"'), re.I) for m in re.finditer(r'^\s*~\*((?:\\ |\S)+)\s+1;', texte, re.M)]
        self.assertGreaterEqual(len(motifs), 5)
        bloque = lambda ua: any(m.search(ua) for m in motifs)
        for ua in ("python-httpx/0.28.1", "Python-urllib/3.11", "curl/8.5.0", "python-requests/2.32",
                   "Mozilla/5.0 (compatible; SERankingBacklinksBot/1.0)", "Mozilla/5.0 (compatible; GeedoShopProductFinder/1.0)"):
            with self.subTest(bloque=ua):
                self.assertTrue(bloque(ua))
        for ua in NAVIGATEURS:
            with self.subTest(laisse=ua):
                self.assertFalse(bloque(ua), "un vrai navigateur serait bloqué")

    def test_limite_de_connexion(self):
        m = re.search(r'"~(\^0:POST:[^"]+)"\s+\$binary_remote_addr', lire("conf.d/odoo-global.conf"))
        rx = re.compile(m.group(1))
        for cle in ("0:POST:/web/login", "0:POST:/en_CA/web/login", "0:POST:/web/login/totp", "0:POST:/web/session/authenticate"):
            with self.subTest(limite=cle):
                self.assertTrue(rx.search(cle))
        for cle in ("0:GET:/web/login", "1:POST:/web/login", "0:POST:/web/dataset/call_kw", "0:POST:/shop/cart/update"):
            with self.subTest(illimite=cle):
                self.assertFalse(rx.search(cle))
        self.assertIn("limit_req zone=odoo_login", lire("snippets/odoo/_odoo-common.conf"))

    def test_limite_de_connexions_simultanees_par_cookie_de_visiteur(self):
        """1.7 : limit_conn par cookie visitor_uuid (conflits d'écriture website_visitor) : clé vide pour les IP de confiance et sans cookie ; 429 ; location / seulement."""
        glob = lire("conf.d/odoo-global.conf")
        self.assertIn("limit_conn_zone $limit_key_visiteur zone=odoo_visiteur:10m;", glob)
        self.assertIn("limit_conn_status 429;", glob)
        m = re.search(r'map "\$is_trusted_ip:\$cookie_visitor_uuid" \$limit_key_visiteur \{(.*?)\}', glob, re.S)
        self.assertTrue(m)
        rx = re.search(r'"~(\^[^"]+)"', m.group(1))
        self.assertTrue(re.search(rx.group(1), "0:abc-123"))
        self.assertFalse(re.search(rx.group(1), "1:abc-123"))
        self.assertFalse(re.search(rx.group(1), "0:"))
        commun = lire("snippets/odoo/_odoo-common.conf")
        self.assertEqual(commun.count("limit_conn odoo_visiteur 8;"), 1)
        self.assertLess(commun.index("location / {"), commun.index("limit_conn odoo_visiteur 8;"))

    def test_reseaux_partages_ont_leurs_propres_zones_plus_larges(self):
        """1.9 : les adresses des lieux [partagée] (université) passent par des zones plus larges (3 fois le débit, 5 fois les connexions) ; chaque zone n'a de clé que pour
        son groupe (adresse ordinaire ou partagée), jamais les deux ; le fichier généré est inclus."""
        glob = lire("conf.d/odoo-global.conf")
        self.assertIn("include /etc/nginx/snippets/shared-ips-geo.conf;", glob)
        self.assertIn("limit_req_zone $limit_key_general_std zone=odoo_general:10m rate=30r/s;", glob)
        self.assertIn("limit_req_zone $limit_key_general_partage zone=odoo_general_partage:10m rate=90r/s;", glob)
        self.assertIn("limit_req_zone $limit_key_login_std zone=odoo_login:10m rate=5r/m;", glob)
        self.assertIn("limit_req_zone $limit_key_login_partage zone=odoo_login_partage:10m rate=25r/m;", glob)
        for nom, groupe in (("general_std", "0"), ("general_partage", "1"), ("login_std", "0"), ("login_partage", "1")):
            m = re.search(r'map "\$is_shared_ip:\$limit_key_[a-z]+" \$limit_key_' + nom + r' \{\s*"~(\^[^"]+)"\s+\$1;', glob)
            self.assertTrue(m, nom)
            rx = re.compile(m.group(1))
            self.assertTrue(rx.search(groupe + ":203.0.113.5"), nom)
            self.assertFalse(rx.search(("1" if groupe == "0" else "0") + ":203.0.113.5"), nom)
            self.assertFalse(rx.search(groupe + ":"), nom)                         # clé vide (IP de confiance, GET…) : jamais de limite
        commun = lire("snippets/odoo/_odoo-common.conf")
        self.assertIn("limit_req zone=odoo_general_partage burst=180 nodelay;", commun)
        self.assertIn("limit_req zone=odoo_login_partage burst=25 nodelay;", commun)

    def test_regle_gestion_des_bases_dans_chaque_environnement(self):
        for env in ("prod", "dev", "lab"):
            with self.subTest(env=env):
                texte = lire(f"snippets/odoo/env-{env}.conf")
                m = re.search(r"location ~\* (\S+) \{", texte)
                rx = re.compile(m.group(1), re.I)
                for u in ("/web/database/manager", "/web/database/list", "/web/database/backup", "/xmlrpc/2/db"):
                    self.assertTrue(rx.search(u), f"{u} non réservé aux IP autorisées")
                for u in ("/web/login", "/jsonrpc", "/xmlrpc/2/object"):
                    self.assertFalse(rx.search(u), f"{u} bloqué à tort")
                bloc = texte[m.end():texte.index("}", m.end())]
                self.assertIn("deny all;", bloc)

    def test_robots_tout_interdit_pour_dev_seulement(self):
        m = re.search(r"map \$server_name \$robots_disallow_all \{(.*?)\}", lire("conf.d/odoo-global.conf"), re.S)
        self.assertRegex(m.group(1), r"odoo-dev\.rencontres-linux\.quebec\s+1;")
        self.assertNotRegex(m.group(1), r"www\.rencontres-linux\.quebec\s+1;")

    # --- fail2ban ------------------------------------------------------------------------------------------------------
    def failregex(self, nom):
        bloc = lire(f"fail2ban/{nom}.filter.conf").split("failregex =", 1)[1].split("ignoreregex", 1)[0]
        return [re.compile(l.strip().replace("<HOST>", r"(?:::f{4,6}:)?(?P<host>[\w\-.^_:]*\w)")) for l in bloc.strip().splitlines()]

    def hote(self, regs, ligne):
        for r in regs:
            m = r.search(ligne)
            if m:
                return m.group("host")
        return None

    def test_filtre_odoo_auth(self):
        regs = self.failregex("odoo-auth")
        base = "2026-09-25 23:20:43,888 1830 INFO linux_meetup_odoo_18 odoo.addons.base.models.res_users: "
        self.assertEqual(self.hote(regs, base + "Login failed for db:linux_meetup_odoo_18 login:admin from 203.0.113.9"), "203.0.113.9")
        self.assertEqual(self.hote(regs, base + "Login failed for login:x@y.org from 2001:db8::42"), "2001:db8::42")
        self.assertEqual(self.hote(regs, "… auth_signup: Password reset attempt for <admin> by user <__system__> from 198.51.100.7"), "198.51.100.7")
        self.assertIsNone(self.hote(regs, base + "Login successful for db:x login:admin from 11.126.46.49"))
        # Injection : un identifiant piégé ne peut pas faire bannir une autre IP (l'IP réelle est toujours en fin de ligne)
        self.assertEqual(self.hote(regs, base + "Login failed for db:x login:a from 11.126.46.49 from 198.51.100.66"), "198.51.100.66")

    def test_filtre_catchall(self):
        regs = self.failregex("nginx-catchall")
        self.assertEqual(self.hote(regs, '11.134.146.49 - [25/Sep/2026:01:04:59 -0400] "GET / HTTP/1.1" 444 host="11.85.38.12" ua="x"'), "11.134.146.49")
        self.assertIsNone(self.hote(regs, '11.134.146.49 - [25/Sep/2026:01:04:59 -0400] "GET / HTTP/1.1" 200 host="x" ua="x"'))

    def test_modele_jail_odoo_auth(self):
        """1.16 : marqueurs attendus par nginx-hardening.sh ; journalmatch jamais entre les crochets du backend."""
        t = lire("fail2ban/odoo-auth.jail.conf.template")
        self.assertEqual(set(re.findall(r"@[A-Z_]+@", t)), {"@ODOO_UNIT@", "@BACKEND@", "@IGNOREIP@"})
        self.assertNotRegex(t, r"systemd\[[^\]]*journalmatch")
        self.assertNotRegex(lire("fail2ban/odoo-auth.filter.conf"), r"systemd-journal\[[^\]]*journalmatch",
                            "commande fail2ban-regex erronée dans le commentaire (journalmatch passe par -m)")

    @unittest.skipUnless(shutil.which("fail2ban-regex"), "fail2ban-regex absent (installé sur les serveurs : test réel là-bas)")
    def test_vrai_fail2ban_regex(self):
        """Validation RÉELLE des filtres par fail2ban lui-même (dates, <HOST>, ancrages) — impossible à émuler."""
        cas = {"odoo-auth": ["2026-09-26 19:15:23,393 1853 INFO linux_meetup_odoo_18 odoo.addons.base.models.res_users: "
                             "Login failed for db:linux_meetup_odoo_18 login:admin from 203.0.113.9",
                             "2026-09-26 19:15:24,000 1853 INFO linux_meetup_odoo_18 odoo.addons.base.models.res_users: "
                             "Login successful for db:linux_meetup_odoo_18 login:admin from 11.126.46.49"],
               "nginx-catchall": ['11.134.146.49 - [26/Sep/2026:01:04:59 -0400] "GET / HTTP/1.1" 444 host="x" ua="-"',
                                  '11.134.146.49 - [26/Sep/2026:01:05:00 -0400] "GET /.env HTTP/1.1" 444 host="x" ua="-"']}
        attendu = {"odoo-auth": 1, "nginx-catchall": 2}
        for nom, lignes in cas.items():
            with self.subTest(filtre=nom):
                with tempfile.NamedTemporaryFile("w", suffix=".log", prefix="test-rlq-", delete=False) as f:
                    f.write("\n".join(lignes) + "\n")
                self.addCleanup(os.remove, f.name)
                r = subprocess.run(["fail2ban-regex", f.name, os.path.join(CONFIG_DIR, "fail2ban", f"{nom}.filter.conf")],
                                   capture_output=True, text=True, timeout=60)
                m = re.search(r"Lines: \d+ lines, \d+ ignored, (\d+) matched", r.stdout)
                self.assertIsNotNone(m, r.stdout + r.stderr)
                self.assertEqual(int(m.group(1)), attendu[nom], r.stdout)


if __name__ == "__main__":
    unittest.main()


class FormatDesJournaux(unittest.TestCase):
    """combined_host (2026-09-29) : format « combined » + host="$host" EN FIN de ligne, pour tous les sites Odoo — ce
    qui lit ces journaux (awk, fail2ban, web-monitor.py) doit continuer de fonctionner sans changement."""
    CONF = CONFIG_DIR

    def test_format_defini_et_utilise_par_les_trois_sites(self):
        glob_ = open(os.path.join(self.CONF, "conf.d", "odoo-global.conf"), encoding="utf-8").read()
        m = re.search(r"log_format combined_host\s+((?:'[^']*'\s*)+);", glob_)
        self.assertIsNotNone(m, "log_format combined_host absent")
        fmt_ = "".join(re.findall(r"'([^']*)'", m.group(1)))
        self.assertTrue(fmt_.startswith('$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent '
                                        '"$http_referer" "$http_user_agent"'), "le début doit rester le format combined")
        self.assertTrue(fmt_.endswith(' host="$host" rl=$request_length'))        # 1.11 : taille de la requête TOUT À LA FIN (web-monitor.py : Mo envoyés)
        for env in ("prod", "dev", "lab"):
            with self.subTest(site=env):
                ssl = open(os.path.join(self.CONF, "snippets", "odoo", f"rencontres-linux-quebec-{env}.ssl.conf"), encoding="utf-8").read()
                self.assertRegex(ssl, rf"(?m)^access_log /var/log/nginx/rencontres_linux_quebec_{env}-access\.log combined_host;")

    def test_ligne_produite_reste_lisible_par_awk(self):
        ligne = '203.0.113.9 - - [29/Sep/2026:10:00:00 -0400] "GET /.env HTTP/1.1" 404 48213 "-" "Mozilla/5.0 (X11)" host="odoo18.exemple.org"\n'
        champs = lambda prog: subprocess.run([os.environ.get("TEST_AWK", "awk"), prog], input=ligne, capture_output=True, text=True).stdout.strip()
        self.assertEqual(champs("BEGIN { FS = \"\\\"\" } { print $6 }"), "Mozilla/5.0 (X11)")   # User-Agent
        self.assertEqual(champs("{ print $9, $10, $7 }"), "404 48213 /.env")                       # code, taille, URL


class RefusJournalises(unittest.TestCase):
    """Refus des règles de sécurité journalisés dans blocked-probes.log (jamais « access_log off ») ; jail dédiée."""
    CONF = CONFIG_DIR
    LIGNE = '203.0.113.9 - - [29/Sep/2026:10:00:00 -0400] "GET /.env HTTP/1.1" 404 162 "-" "curl/8" host="www.exemple.org"'

    def test_aucun_refus_sans_journal(self):
        sec = open(os.path.join(self.CONF, "snippets", "securite-commune.conf"), encoding="utf-8").read()
        self.assertNotRegex(sec, r"(?m)^\s*access_log off;")
        self.assertEqual(sec.count("access_log /var/log/nginx/blocked-probes.log combined_host;"), 8)

    def test_filtre_et_jail_ecrits_sur_bbb_identiques_aux_fichiers_livres(self):
        """2.15 : nginx-hardening.sh écrit le filtre et la jail sur BBB (nginx-odoo n'y est pas déployé) — OCTET POUR OCTET
        comme les fichiers livrés, sinon run-all.sh (étape 5, cmp) signale une différence sur ce serveur."""
        script = open(script_path("nginx-hardening.sh"), encoding="utf-8").read()
        for fonction, fichier in (("filtre_blocked_probes", "nginx-blocked-probes.filter.conf"),
                                  ("jail_blocked_probes", "nginx-blocked-probes.jail.conf")):
            with self.subTest(fichier=fichier):
                m = re.search(rf"(?ms)^{fonction}\(\) \{{\n    cat <<'EOF'\n(.*?)\nEOF\n\}}", script)
                self.assertIsNotNone(m, f"{fonction} introuvable dans nginx-hardening.sh")
                livre = open(os.path.join(self.CONF, "fail2ban", fichier), encoding="utf-8").read()
                self.assertEqual(m.group(1) + "\n", livre)

    def test_filtre_et_jail(self):
        filtre = open(os.path.join(self.CONF, "fail2ban", "nginx-blocked-probes.filter.conf"), encoding="utf-8").read()
        regex = re.search(r"failregex = (.+)", filtre).group(1).replace("<HOST>", r"(?P<host>\S+)")
        self.assertEqual(re.match(regex, self.LIGNE).group("host"), "203.0.113.9")
        jail = open(os.path.join(self.CONF, "fail2ban", "nginx-blocked-probes.jail.conf"), encoding="utf-8").read()
        self.assertIn("logpath  = /var/log/nginx/blocked-probes.log", jail)
        self.assertIn("filter   = nginx-blocked-probes", jail)

    @unittest.skipUnless(shutil.which("fail2ban-regex"), "fail2ban-regex absent (installé sur les serveurs : test réel là-bas)")
    def test_vrai_fail2ban_regex(self):
        r = subprocess.run(["fail2ban-regex", self.LIGNE, os.path.join(self.CONF, "fail2ban", "nginx-blocked-probes.filter.conf")],
                           capture_output=True, text=True)
        self.assertRegex(r.stdout, r"Lines: 1 lines, 0 ignored, 1 matched")


def blocs_server(texte):
    """Blocs « server { … } » d'un fichier : liste de (directives de premier niveau, includes de premier niveau). Chaque
    directive est la liste de ses mots ; les blocs imbriqués (location, if) ne sont pas descendus."""
    blocs, pile, mots, courant = [], [], [], None
    for t in tokens(texte):
        if t == "{":
            pile.append(mots[:1])
            if mots[:1] == ["server"] and len(pile) == 1:
                courant = ([], [])
                blocs.append(courant)
            elif courant is not None and len(pile) == 2:
                courant[0].append(mots + ["{"])
            mots = []
        elif t == "}":
            pile.pop()
            if not pile:
                courant = None
            mots = []
        elif t == ";":
            if courant is not None and len(pile) == 1:
                courant[0].append(mots)
                if mots[:1] == ["include"]:
                    courant[1].append(os.path.basename(mots[1]))
            mots = []
        else:
            mots.append(t)
    return blocs


def regles_de_refus(chemin_fichier):
    """[(operateur, expression)] des « location ~ … » / « location ~* … » d'un fichier (guillemets retirés)."""
    mots, regles = [], []
    for t in tokens(open(chemin_fichier, encoding="utf-8").read()):
        if t in "{};":
            if len(mots) >= 3 and mots[0] == "location" and mots[1] in ("~", "~*"):
                regles.append((mots[1], mots[2].strip("\"'")))
            mots = []
        else:
            mots.append(t)
    return regles


@unittest.skipUnless(os.path.isdir(CONFIG_DIR), f"configuration absente : {CONFIG_DIR}")
class RegleWordPress(unittest.TestCase):
    """2026-10-02 : /wp-admin/ (un répertoire, pas un .php) traversait nginx jusqu'à Odoo (303 puis page 404 de 32 Ko), alors que
    wp-content, wp-json et tous les .php étaient déjà refusés. Les expressions sont évaluées par Python (même syntaxe PCRE)."""
    def refuse(self, chemin):
        regles = regles_de_refus(os.path.join(CONFIG_DIR, "snippets", "securite-commune.conf"))
        import re
        return any(re.search(rx, chemin, re.I if op == "~*" else 0) for op, rx in regles)

    def test_wordpress_refuse_avec_ou_sans_prefixe_de_langue(self):
        for chemin in ("/wp-admin/", "/wp-admin", "/en_CA/wp-admin/", "/en_CA/wp-admin", "/fr/wp-admin/install.php", "/fr_CA/wp-login",
                       "/wp-includes/js/jquery.js", "/WP-ADMIN/", "/wp-content/uploads/x", "/wp-json/wp/v2/users", "/en_CA/wp-json/"):
            with self.subTest(chemin=chemin):
                self.assertTrue(self.refuse(chemin), f"{chemin} devrait être refusé par nginx")

    def test_routes_d_odoo_jamais_refusees(self):
        """Vraies routes tirées du journal du site : aucune règle de sécurité ne doit les capter."""
        for chemin in ("/", "/event", "/event/service-worker.js", "/event/manifest.webmanifest", "/web/login", "/web/session/logout",
                       "/en_CA/shop", "/fr_CA/event/journee-portes-ouvertes-sur-linux-2026-125/page/introduction", "/website/info",
                       "/website/translations/ef6863651737cba0f7efc1a44ed8284c97f6e410", "/my/home", "/web/content/123",
                       "/web/image/9725-35c703c7/23-09-23 14-26-48 8748.jpg jjjj.webp", "/web/image/website/1/app_icon/192x192",
                       "/web/image/wp-admin.png", "/web_editor/shape/web_editor/Rainy/09_001.svg",
                       "/website_event_track/static/lib/idb-keyval/idb-keyval.js", "/event/journee-portes-ouvertes-sur-linux-2026-125/exhibitors"):
            with self.subTest(chemin=chemin):
                self.assertFalse(self.refuse(chemin), f"{chemin} est une route d'Odoo : elle ne doit pas être refusée")

    def test_accolades_de_l_expression_entre_guillemets(self):
        """nginx refuse « {2} » non protégé dans une expression régulière : l'expression doit être entre guillemets."""
        texte = open(os.path.join(CONFIG_DIR, "snippets", "securite-commune.conf"), encoding="utf-8").read()
        for ligne in texte.splitlines():
            if ligne.startswith("location") and "{" in ligne.split(" {")[0]:
                self.assertRegex(ligne, r'^location ~\*? "', f"expression avec accolade non protégée : {ligne[:80]}")


@unittest.skipUnless(os.path.isdir(CONFIG_DIR), f"configuration absente : {CONFIG_DIR}")
class IconeEcranDAccueil(unittest.TestCase):
    """2026-10-07 : Safari / iOS / Android demandent /apple-touch-icon*.png à la racine ; Odoo répondait 303 puis une page 404 complète (~0,3 s de calcul). Une
    règle de _odoo-common.conf sert l'icône d'application du site par une réécriture interne."""
    COMMUN = os.path.join("snippets", "odoo", "_odoo-common.conf")
    DEMANDES = ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/apple-touch-icon-120x120.png", "/apple-touch-icon-152x152-precomposed.png",
                "/en_CA/apple-touch-icon.png", "/en_CA/apple-touch-icon-precomposed.png", "/fr/apple-touch-icon.png", "/fr_CA/apple-touch-icon-180x180.png")

    def bloc(self):
        texte = lire(self.COMMUN)
        lignes = [l for l in texte.splitlines() if l.startswith("location") and "apple-touch-icon" in l]
        self.assertEqual(len(lignes), 1, "une seule règle pour l'icône")
        debut = texte.index(lignes[0])
        return lignes[0], texte[debut:texte.index("\n}\n", debut) + 3]

    def expression(self):
        m = re.match(r'^location ~ "(.*)" \{$', self.bloc()[0])
        self.assertIsNotNone(m, "expression entre guillemets (« {2} » non protégé est refusé par nginx)")
        return m.group(1)

    def test_les_demandes_des_navigateurs_sont_captees_et_rien_d_autre(self):
        rx = self.expression()
        for chemin in self.DEMANDES:
            with self.subTest(chemin=chemin):
                self.assertTrue(re.search(rx, chemin), f"{chemin} devrait être servi par la règle")
        for chemin in ("/apple-touch-icon.png.php", "/apple-touch-icon.jpg", "/web/image/apple-touch-icon.png", "/web/content/12/apple-touch-icon.png",
                       "/x/apple-touch-icon.png", "/en_CA/shop/apple-touch-icon.png", "/apple-touch-icons.png", "/apple-touch-icon.png/x", "/xapple-touch-icon.png",
                       "/favicon.ico", "/web/image/website/1/app_icon/192x192", "/en_CA/event"):
            with self.subTest(chemin=chemin):
                self.assertFalse(re.search(rx, chemin), f"{chemin} ne doit pas être touché (pièce jointe, autre fichier ou route d'Odoo)")

    def test_aucune_regle_de_refus_ne_capte_ces_demandes(self):
        regles = regles_de_refus(os.path.join(CONFIG_DIR, "snippets", "securite-commune.conf"))
        for chemin in self.DEMANDES + ("/web/image/website/1/app_icon/180x180",):
            with self.subTest(chemin=chemin):
                self.assertFalse(any(re.search(rx, chemin, re.I if op == "~*" else 0) for op, rx in regles), f"{chemin} serait refusé par nginx")

    def test_reecriture_interne_sans_redirection_ni_perte_des_en_tetes(self):
        _, bloc = self.bloc()
        self.assertIn("rewrite ^ /web/image/website/1/app_icon/180x180 break;", bloc)       # l'icône d'application d'Odoo, en 180x180 (taille d'iOS)
        self.assertIn("proxy_pass http://$odoo_backend;", bloc)
        self.assertNotRegex(bloc, r"\breturn\s+30\d\b")                                       # jamais une redirection : iOS ne la suit pas toujours
        self.assertNotIn("proxy_set_header", bloc, "un seul proxy_set_header ferait perdre TOUS ceux du niveau serveur (voir _odoo-common.conf)")
        self.assertIn("limit_req zone=odoo_general", bloc)
        self.assertIn("odoo_general", lire(os.path.join("conf.d", "odoo-global.conf")))      # la zone existe

    def test_regle_dans_le_fichier_inclus_par_les_vhosts_https_seulement(self):
        """$odoo_backend n'existe que dans les vhosts https : la règle ne doit PAS être dans securite-commune.conf (aussi inclus par les blocs du port 80)."""
        self.assertNotIn("apple-touch-icon", lire(os.path.join("snippets", "securite-commune.conf")))
        for site in glob.glob(os.path.join(CONFIG_DIR, "sites-available", "*prod.conf")) + glob.glob(os.path.join(CONFIG_DIR, "sites-available", "*dev.conf")):
            self.assertIn("_odoo-common.conf", open(site, encoding="utf-8").read(), os.path.basename(site))


@unittest.skipUnless(os.path.isdir(CONFIG_DIR), f"configuration absente : {CONFIG_DIR}")
class BlocsDeRedirection(unittest.TestCase):
    def test_redirection_apres_les_regles_de_securite(self):
        """2026-10-01 : le bloc https des noms non canoniques faisait « return 301 » au niveau du server — exécuté AVANT
        toute location, /.env y était redirigé vers www au lieu d'être refusé (jamais journalisé dans blocked-probes.log ni
        banni ; « non filtré » pour web-monitor.py). Tout bloc qui ne sert pas Odoo doit inclure securite-commune.conf et
        rediriger dans une location."""
        vus = 0
        for f in sorted(glob.glob(os.path.join(CONFIG_DIR, "sites-available", "*.conf"))):
            for directives, includes in blocs_server(open(f, encoding="utf-8").read()):
                if "_odoo-common.conf" in includes or any(d[:2] == ["server_name", "_"] for d in directives):
                    continue                                           # bloc d'Odoo, ou capteur catch-all (444)
                vus += 1
                with self.subTest(fichier=os.path.basename(f), includes=includes):
                    self.assertIn("securite-commune.conf", includes)
                    self.assertFalse([d for d in directives if d[:1] == ["return"]],
                                     "« return » au niveau du server : exécuté avant les règles de sécurité")
                    self.assertTrue(any(d[:2] == ["location", "/"] for d in directives), "redirection attendue dans « location / »")
        self.assertGreaterEqual(vus, 4)            # port 80 de prod, dev, lab + https non canonique de prod

    def test_robots_txt_redirige_avant_la_regle_txt(self):
        """robots.txt d'un nom non canonique : redirigé (location regex placée AVANT l'include de securite-commune.conf,
        dont la règle « .txt » le refuserait en 404 et le compterait pour la jail)."""
        texte = lire(os.path.join("sites-available", "10-rencontres-linux-quebec-prod.conf"))
        bloc = next(d for d, inc in blocs_server(texte) if "rencontres-linux-quebec-prod-noncanonical.name.conf" in inc)
        ordre = [" ".join(d[:2]) if d[0] == "location" else os.path.basename(d[1]) for d in bloc if d[0] in ("location", "include")]
        self.assertLess(ordre.index("location ~"), ordre.index("securite-commune.conf"))
