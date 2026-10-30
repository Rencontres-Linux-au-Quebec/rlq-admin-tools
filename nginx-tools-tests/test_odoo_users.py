"""Comptes Odoo connectés : activité suspecte (sommaire de web-monitor.py 2.65), enquête, bannissement et surveillance d'un compte (--ban-odoo-user,
--unban-odoo-user, --watch-odoo-user), registre apps/_odoo_users.py, vérification des adresses courriel (apps/_email_check.py), alignement des noms
chinois dans --list-users --table, et nginx-log-audit.sh qui ne tient plus pour « utilisateur légitime » une adresse d'un compte banni."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"   # comptes Odoo (journal systemd d'Odoo, PostgreSQL)
import datetime
import importlib.util
import os
import unicodedata
import unittest

from helpers import SANS_ROOT_SIMULE, EnvTest, script_path

SEP = "\\037"
MOIS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, script_path(chemin))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def largeur(texte):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 0 if unicodedata.combining(c) else 1 for c in texte)


class ComptesOdoo(EnvTest):
    """Faux serveur Odoo : journal systemd (connexions, accès refusés), journal nginx, PostgreSQL simulé (runuser), nginx-log-audit.sh simulé."""

    def setUp(self):
        super().setUp()
        self.prog = self.prepare("web-monitor.py")
        self.aujourdhui = datetime.date.today()
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        self.nginx = os.path.dirname(self.path("nginx", "x"))
        self.env.update(TZ="America/Toronto",                    # run-all 1.188: expected hours in Eastern time, even on a machine in UTC
                        WEB_MONITOR_NGINX_DIR=self.nginx, WEB_MONITOR_FAIL2BAN_LOG=self.path("fail2ban.log"),
                        NGINX_LOG_AUDIT_STATE_DIR=os.path.dirname(self.path("chk", "x")), SYNC_CROWDSEC_STATE_DIR=os.path.dirname(self.path("cs", "x")))
        self.write("fail2ban.log", "")
        # nginx-log-audit.sh simulated: investigation (verdict) and logged bans
        self.write("prog/nginx-log-audit.sh", f'echo "$@" >> {self.d}/nla.log\n'
                   'case "$*" in *--investigate*) echo "      → Score 1/7 — connectée à Odoo avec le compte x : un compte n\'est pas une preuve de bonne foi,";; esac\n'
                   'exit 0\n', 0o755)
        self.postgresql()

    def postgresql(self, partage="t"):
        """runuser simulé : utilisateurs (UID 849 portail, 42 interne), détail d'un compte, écritures journalisées."""
        d = self.d
        self.mock("runuser", f'''echo "$@" >> {d}/runuser.log
case "$*" in
 *information_schema.columns*) ;;
 *res_users_log*) case "$*" in
     *"login = 'joe@exemple.org'"*) printf '42{SEP}joe@exemple.org{SEP}Joe Interne{SEP}joe@exemple.org{SEP}t{SEP}f{SEP}1700000000{SEP}5{SEP}1700000000{SEP}5{SEP}\\n';;
     *) printf '849{SEP}fantome5075@exemple.org{SEP}张三李四{SEP}fantome5075@exemple.org{SEP}t{SEP}{partage}{SEP}%s{SEP}1{SEP}%s{SEP}3{SEP}\\n' "$(date +%s)" "$(date +%s)";;
   esac;;
 *"FROM mail_message WHERE author_id"*) echo 0;;
 *"public.survey_user_input"*) echo f;;
 *"UPDATE res_users"*) id=$(echo "$*" | sed -n 's/.*WHERE u.id = \\([0-9]*\\).*/\\1/p'); echo "$id"; echo "UPDATE 1";;
 *"FROM res_users u JOIN res_partner p ON p.id = u.partner_id ORDER BY u.id"*)
     printf '849{SEP}fantome5075@exemple.org{SEP}张三李四{SEP}t\\n42{SEP}joe@exemple.org{SEP}Joe Interne{SEP}f\\n7{SEP}ana@exemple.org{SEP}Ana Tremblay{SEP}f\\n';;
 *) ;;
esac''')

    def journal(self, lignes):
        self.write("journal.txt", "".join(lignes))
        self.mock("journalctl", f"cat {self.d}/journal.txt")

    def connexion(self, quand, login, ip, base="base"):
        return f"{quand}-0400 odoo18 odoo[1]: x INFO {base} odoo.addons.base.models.res_users: Login successful for db:{base} login:{login} from {ip}\n"

    def acces(self, jour, ip, secondes, url, code=200, methode="GET", ua="Mozilla/5.0 (X11; Linux x86_64; rv:157.0) Gecko/20100101 Firefox/157.0"):
        d = f"{jour:%d}/{MOIS[jour.month - 1]}/{jour:%Y}"
        return f'{ip} - - [{d}:04:41:{secondes:02d} -0400] "{methode} {url} HTTP/1.1" {code} 900 "-" "{ua}"\n'

    def scenario(self):
        """fantome (nouveau, 19 pages en 9 s) et ana (ancien compte, lecture normale)."""
        t = self.aujourdhui
        self.journal([self.connexion(f"{t - datetime.timedelta(days=200)}T09:00:00", "ana@exemple.org", "11.36.1.2"),
                      self.connexion(f"{t}T04:47:00", "fantome5075@exemple.org", "11.95.32.106"),
                      self.connexion(f"{t}T08:00:00", "ana@exemple.org", "11.36.1.2")])
        lignes = [self.acces(t, "11.95.32.106", i // 2, f"/en_CA/event/page-{i}") for i in range(19)]
        lignes += [self.acces(t, "11.36.1.2", 10 + 2 * i, f"/event/page-{i}") for i in range(4)]
        self.write("nginx/site-access.log", "".join(lignes))

    def lancer(self, *args, env=None):
        rc, out, err = self.run_cmd(["python3", self.prog, *args], env)
        self.assertNotIn("Traceback", err, err)
        return rc, out, err

    def section(self, out):
        debut = out.index("ACTIVITÉ SUSPECTE D'UTILISATEURS CONNECTÉS")
        fin = out.find("\nCOUVERTURE", debut)
        return out[debut:fin if fin > 0 else None]

    # --- sommaire ----------------------------------------------------------------------------------------------------
    def test_sommaire_section_activite_suspecte_nouveau_compte_et_rafale(self):
        """2.65 : nouveau compte + rafale de 19 pages en 10 s = score 3 « à surveiller » ; un compte ancien qui lit normalement n'y est pas."""
        self.scenario()
        rc, out, err = self.lancer("--summary", "--no-prompt")
        s = self.section(out)
        self.assertIn("— un compte n'est pas une preuve de bonne foi (30 jours)", s)
        self.assertIn("▶ fantome5075@exemple.org — 张三李四 (UID 849, portail/public) — score 3 — à surveiller", s)
        self.assertRegex(s, r"\+2 rafale : 19 pages en 10 s \(\d{4}-\d\d-\d\d 04:41:0\d\) — une personne lit une page à la fois")
        self.assertIn(f"+1 nouveau compte : première connexion {self.aujourdhui} 04:47", s)
        self.assertIn("première connexion", s)
        self.assertNotIn("ana@exemple.org", s)
        self.assertIn("web-monitor.py --suspect-users", s)

    def test_sommaire_acces_refuses_par_odoo_et_formulaires_en_masse(self):
        """Accès refusés par Odoo (ACL, règles) pour l'UID du compte, et 60 formulaires d'inscription : score SUSPECT."""
        self.scenario()
        t = self.aujourdhui
        refus = [f"{t}T05:0{i}:00-0400 odoo18 odoo[1]: x INFO base odoo.addons.base.models.ir_model: Access Denied by ACLs for operation: read, uid: 849, model: res.partner\n"
                 for i in range(4)]
        with open(self.path("journal.txt"), "a") as f:
            f.writelines(refus)
        with open(self.path("nginx", "site-access.log"), "a") as f:
            f.writelines(self.acces(t, "11.95.32.106", i % 60, "/event/jpo-125/registration/confirm", methode="POST") for i in range(60))
        rc, out, err = self.lancer("--summary", "--no-prompt")
        s = self.section(out)
        self.assertRegex(s, r"fantome5075@exemple\.org — .* — score [4-9]\d* — SUSPECT")
        self.assertIn("+2 accès refusés par Odoo : 4 fois (res.partner ×4) — essaie de lire ce qui lui est interdit", s)
        self.assertIn("+2 formulaires soumis : 60 (/event/…/registration ×60)", s)

    def test_sommaire_en_anglais(self):
        self.scenario()
        rc, out, err = self.lancer("--summary", "--no-prompt", "--lang", "en")
        self.assertIn("SUSPICIOUS ACTIVITY OF LOGGED-IN USERS", out)
        self.assertIn("score 3 — to watch", out)
        self.assertIn("burst: 19 pages in 10 s", out)

    # --- surveillance --------------------------------------------------------------------------------------------------
    @unittest.skipUnless(os.geteuid() == 0, "surveiller un compte exige root")
    def test_surveiller_puis_ne_plus_surveiller(self):
        """--watch-odoo-user : le compte reste listé (même sans indice) avec [surveillé] ; --unwatch-odoo-user le retire ; registre jamais réécrit."""
        t = self.aujourdhui
        self.journal([self.connexion(f"{t - datetime.timedelta(days=100)}T09:00:00", "ana@exemple.org", "11.36.1.2"),
                      self.connexion(f"{t}T08:00:00", "ana@exemple.org", "11.36.1.2")])
        self.write("nginx/site-access.log", self.acces(t, "11.36.1.2", 1, "/event"))
        rc, out, err = self.lancer("--watch-odoo-user", "ana@exemple.org")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("ana@exemple.org — surveillé — listé dans chaque sommaire", out)
        registre = open(self.env["NGINX_TOOLS_ODOO_USERS"]).read()
        self.assertRegex(registre, r"\twatched\tbase\t\tana@exemple\.org\t11\.36\.1\.2\tweb-monitor\.py\n")
        self.assertEqual(oct(os.stat(self.env["NGINX_TOOLS_ODOO_USERS"]).st_mode & 0o777), "0o600")
        rc, out, err = self.lancer("--summary", "--no-prompt")
        s = self.section(out)
        self.assertIn("▶ ana@exemple.org", s)
        self.assertIn("[surveillé]", s)
        self.assertIn("aucun indice sur la période (compte surveillé", s)
        rc, out, err = self.lancer("--watch-odoo-user", "ana@exemple.org")
        self.assertIn("est déjà surveillé", out)
        rc, out, err = self.lancer("--unwatch-odoo-user", "ana@exemple.org")
        self.assertIn("n'est plus surveillé", out)
        rc, out, err = self.lancer("--summary", "--no-prompt")
        self.assertNotIn("ana@exemple.org", self.section(out))
        self.assertEqual(open(self.env["NGINX_TOOLS_ODOO_USERS"]).read().count("\n"), 2)        # two events, the history is kept

    # --- bannissement --------------------------------------------------------------------------------------------------
    @unittest.skipUnless(os.geteuid() == 0, "bannir un compte exige root")
    def test_bannir_puis_lever_un_compte_portail(self):
        """--ban-odoo-user --yes : enquête (toutes les adresses), compte archivé (UPDATE gardé), adresse propre au compte bannie, adresse partagée
        épargnée, registre ; --unban-odoo-user --yes : compte rétabli et adresse débannie."""
        self.scenario()
        with open(self.path("journal.txt"), "a") as f:
            f.write(self.connexion(f"{self.aujourdhui}T09:00:00", "fantome5075@exemple.org", "11.36.1.2"))          # address also used by ana
        rc, out, err = self.lancer("--ban-odoo-user", "fantome5075@exemple.org", "--yes")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("ENQUÊTE SUR LE COMPTE ODOO fantome5075@exemple.org", out)
        self.assertIn("[2] Ses adresses IP (2 dans tout le journal)", out)
        self.assertIn("11.36.1.2 — 1 connexions — aussi utilisée par : ana@exemple.org", out)
        self.assertIn("non cherché (--internet pour l'autoriser sans question)", out)       # --yes: never sent to third parties without agreement
        self.assertIn("BANNISSEMENT DU COMPTE ODOO fantome5075@exemple.org (UID 849, base base)", out)
        self.assertIn("non bannie : 11.36.1.2 (aussi utilisée par ana@exemple.org)", out)
        self.assertIn("Compte Odoo : archivé", out)
        maj = [l for l in open(self.path("runuser.log")).read().splitlines() if "UPDATE res_users" in l]
        self.assertEqual(len(maj), 1)
        self.assertIn("SET active = false", maj[0])
        self.assertIn("WHERE u.id = 849 AND u.share AND u.active", maj[0])                     # guards in the SQL itself
        self.assertIn("'public_user', 'user_root', 'user_admin'", maj[0])
        nla = open(self.path("nla.log")).read()
        self.assertIn("--ban 11.95.32.106 --yes", nla)
        self.assertNotIn("--ban 11.36.1.2", nla)
        registre = open(self.env["NGINX_TOOLS_ODOO_USERS"]).read()
        self.assertRegex(registre, r"\tbanned\tbase\t849\tfantome5075@exemple\.org\t11\.95\.32\.106\tscore \d+")
        # the banned account is no longer a "known user" nor listed in the section
        rc, out, err = self.lancer("--summary", "--no-prompt")
        self.assertNotIn("▶ fantome5075@exemple.org", self.section(out))
        rc, out, err = self.lancer("--ban-odoo-user", "fantome5075@exemple.org", "--yes")
        self.assertIn("est déjà banni", out)
        rc, out, err = self.lancer("--unban-odoo-user", "fantome5075@exemple.org", "--yes")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Compte Odoo : rétabli", out)
        self.assertIn("SET active = true", open(self.path("runuser.log")).read())
        self.assertIn("--unban 11.95.32.106 --yes", open(self.path("nla.log")).read())
        self.assertIn("\tunbanned\t", open(self.env["NGINX_TOOLS_ODOO_USERS"]).read())

    @unittest.skipUnless(os.geteuid() == 0, "bannir un compte exige root")
    def test_compte_interne_jamais_banni(self):
        t = self.aujourdhui
        self.journal([self.connexion(f"{t}T08:00:00", "joe@exemple.org", "11.36.9.9")])
        self.write("nginx/site-access.log", self.acces(t, "11.36.9.9", 1, "/odoo"))
        rc, out, err = self.lancer("--ban-odoo-user", "joe@exemple.org", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("Compte INTERNE (employé, bénévole avec accès au back-office) : jamais banni par ce programme", out)
        self.assertIn("REFUSÉ : joe@exemple.org est un compte INTERNE", out)
        self.assertNotIn("UPDATE res_users", open(self.path("runuser.log")).read())
        self.assertFalse(os.path.exists(self.path("nla.log")) and "--ban " in open(self.path("nla.log")).read())

    def test_sans_root_le_bannissement_est_refuse(self):
        if os.geteuid() == 0:
            self.skipTest("test du refus sans root")
        rc, out, err = self.lancer("--ban-odoo-user", "x@exemple.org", "--yes", env=dict(self.env, **SANS_ROOT_SIMULE))      # run-all 1.190: real refusal, without simulated root
        self.assertEqual(rc, 2)

    # --- table: width of Chinese characters ------------------------------------------------------------------------------
    def test_list_users_table_noms_chinois_alignes(self):
        """2.65 : un nom chinois (« 张三李四 », 4 caractères mais 8 colonnes du terminal) décalait toutes les colonnes de la ligne."""
        self.scenario()
        rc, out, err = self.lancer("--list-users", "--table")
        tableau = [l for l in out.splitlines() if l.startswith("|")]
        self.assertTrue(any("张三李四" in l for l in tableau))
        self.assertEqual({largeur(l) for l in tableau}, {largeur(tableau[0])}, "\n".join(tableau))
        chinois = next(l for l in tableau if "张三李四" in l)
        bornes = [largeur(chinois[:i]) for i, c in enumerate(chinois) if c == "|"]
        self.assertEqual(bornes, [i for i, c in enumerate(tableau[0]) if c == "|"])        # each bar at the same place as the header

    def test_list_users_table_alignee_en_francais_et_en_anglais_avec_donnees_d_exemple(self):
        """run-all 1.188 : comptes d'exemple (donnees_exemples.py : accents, anglais, accent combinant NFD, chinois) — en français ET en anglais, chaque « | »
        du tableau est à la même colonne d'écran que dans l'en-tête (les en-têtes traduits n'ont pas la même longueur : « Identifiant » / « Login »)."""
        import donnees_exemples as ex
        lignes = "".join(f"{uid}{SEP}{login}{SEP}{nom}{SEP}t\\n" for uid, login, nom in ex.COMPTES).replace("'", "'\\''")     # "O'Brien": apostrophe for the shell
        self.mock("runuser", f'''case "$*" in
 *"FROM res_users u JOIN res_partner p ON p.id = u.partner_id ORDER BY u.id"*) printf '{lignes}';;
 *) ;;
esac''')
        t = self.aujourdhui
        self.journal([self.connexion(f"{t}T0{i % 9}:00:00", login, ex.IP_PUBLIQUES[i % len(ex.IP_PUBLIQUES)]) for i, (_, login, _) in enumerate(ex.COMPTES)])
        self.write("nginx/site-access.log", "".join(self.acces(t, ip, 1, "/fr/événement") for ip in ex.IP_PUBLIQUES))
        for langue in ("fr", "en"):
            with self.subTest(langue=langue):
                rc, out, err = self.lancer("--list-users", "--table", f"--lang={langue}")
                tableau = [l for l in out.splitlines() if l.startswith("|")]
                self.assertTrue(any(ex.PERSONNE_CJK in l for l in tableau) and any("Hélène Côté" in l for l in tableau), out)
                attendu = ex.bornes(tableau[0])
                for l in tableau:
                    self.assertEqual(ex.bornes(l), attendu, f"{langue} :\n" + "\n".join(tableau))

    def test_tronquer_en_colonnes_du_terminal(self):
        wm = charger("wm_t", "web-monitor.py")
        self.assertEqual(wm.display_width("张三李四"), 8)
        self.assertEqual(wm.display_width("José"), 4)
        self.assertEqual(wm.display_width("é"), 1)                                        # combining character
        cellule = wm.truncate_column("张三李四张三李四", 9)
        self.assertEqual(wm.display_width(cellule), 9)
        self.assertTrue(cellule.endswith("… ") or cellule.endswith("…"))


class NginxLogAuditCompteBanni(EnvTest):
    """nginx-log-audit.sh 2.37 : connexions d'un compte BANNI ignorées ; compte SURVEILLÉ signalé."""

    def setUp(self):
        super().setUp()
        self.logs = os.path.dirname(self.path("logs", "x"))
        self.prog = self.prepare("nginx-log-audit.sh", {"/var/log/nginx": self.logs})
        d = datetime.date.today().strftime("%d/%b/%Y")
        with open(os.path.join(self.logs, "rencontres_linux_quebec_prod-access.log"), "w") as f:
            f.writelines(f'11.95.32.106 - - [{d}:10:00:{i:02d} -0400] "GET /page{i} HTTP/1.1" 200 300 "-" "Mozilla/5.0 Chrome/152"\n' for i in range(5))
        self.mock("journalctl", 'echo "2026-10-16T04:47:00-0400 odoo18 odoo[1]: 2026-10-16 08:47:00,1 1 INFO base odoo.addons.base.models.res_users: '
                                'Login successful for db:base login:fantome5075@exemple.org from 11.95.32.106"')

    def registre(self, *evenements):
        with open(self.env["NGINX_TOOLS_ODOO_USERS"], "w") as f:
            f.writelines(f"2026-10-16T09:00:00-04:00\t{e}\tbase\t849\tfantome5075@exemple.org\t11.95.32.106\ttest\n" for e in evenements)

    def test_compte_banni_n_est_plus_un_utilisateur_legitime(self):
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "11.95.32.106"])
        self.assertIn("connectée à Odoo avec le compte fantome5075@exemple.org : un compte n'est pas une preuve de bonne foi", out)
        os.makedirs(os.path.dirname(self.env["NGINX_TOOLS_ODOO_USERS"]), exist_ok=True)
        self.registre("banned")
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "11.95.32.106"])
        self.assertNotIn("Connectée à Odoo avec un compte", out)
        self.assertNotIn("connectée à Odoo avec le compte", out)
        self.registre("banned", "unbanned")
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "11.95.32.106"])
        self.assertIn("Connectée à Odoo avec un compte", out)

    def test_compte_surveille_signale(self):
        os.makedirs(os.path.dirname(self.env["NGINX_TOOLS_ODOO_USERS"]), exist_ok=True)
        self.registre("watched")
        rc, out, err = self.run_cmd(["bash", self.prog, "--investigate", "11.95.32.106"])
        self.assertIn("SOUS SURVEILLANCE : jamais bannie automatiquement", out)
        self.assertIn("web-monitor.py --investigate-user fantome5075@exemple.org", out)


class Registre(unittest.TestCase):
    """apps/_odoo_users.py : dernier événement de chaque compte, fichier 600, désactivable."""

    def setUp(self):
        import tempfile
        self.d = tempfile.mkdtemp(prefix="test-rlq-registre-")
        self.addCleanup(__import__("shutil").rmtree, self.d)
        self.ancien = os.environ.get("NGINX_TOOLS_ODOO_USERS")
        os.environ["NGINX_TOOLS_ODOO_USERS"] = os.path.join(self.d, "sous", "odoo-users.tsv")
        self.addCleanup(lambda: os.environ.__setitem__("NGINX_TOOLS_ODOO_USERS", self.ancien or "off"))
        self.m = charger("ou_t", "apps/_odoo_users.py")

    def test_etat_selon_le_dernier_evenement(self):
        m = self.m
        self.assertEqual(m.state(), {"banned": {}, "watched": {}})
        m.record("banned", "base", 849, "a@x", ["1.2.3.4"], "raison\tavec tab")
        m.record("watched", "base", 7, "b@x")
        m.record("unbanned", "base", 849, "a@x", ["1.2.3.4"])
        m.record("banned", "base", 9, "c@x", ["5.6.7.8", "9.9.9.9"])
        s = m.state()
        self.assertEqual(sorted(s["banned"]), ["c@x"])
        self.assertEqual(s["banned"]["c@x"]["ips"], ["5.6.7.8", "9.9.9.9"])
        self.assertEqual(sorted(s["watched"]), ["b@x"])
        self.assertEqual(oct(os.stat(os.environ["NGINX_TOOLS_ODOO_USERS"]).st_mode & 0o777), "0o600")
        self.assertEqual(open(os.environ["NGINX_TOOLS_ODOO_USERS"]).read().count("\n"), 4)
        self.assertNotIn("avec tab\t", open(os.environ["NGINX_TOOLS_ODOO_USERS"]).read())
        with self.assertRaises(ValueError):
            m.record("supprimé", "base", 1, "x")

    def test_registre_desactive(self):
        os.environ["NGINX_TOOLS_ODOO_USERS"] = "off"
        self.assertIsNone(self.m.record("watched", "b", 1, "x"))
        self.assertEqual(self.m.state(), {"banned": {}, "watched": {}})


class VerificationCourriel(unittest.TestCase):
    """apps/_email_check.py : syntaxe, correction suggérée, domaines jetables, serveur de courriel, StopForumSpam, recherche Web (réseau simulé)."""

    def setUp(self):
        self.m = charger("ec_t", "apps/_email_check.py")

    def test_cas_signale_apostrophe_dans_le_domaine(self):
        c = self.m.check("marieb.essai@gmail'com")
        self.assertFalse(c["valid"])
        self.assertEqual(c["reason"], "invalid character in the domain name: '")
        self.assertEqual(c["suggestion"], "marieb.essai@gmail.com")

    def test_suggestions_et_adresses_valides(self):
        m = self.m
        self.assertEqual(m.check("x@gmial.com")["suggestion"], "x@gmail.com")
        self.assertTrue(m.check("x@gmial.com")["valid"])
        self.assertEqual(m.suggest("x@gmail,com"), "x@gmail.com")
        self.assertEqual(m.suggest("x@videotron.cq"), "x@videotron.ca")
        for ok in ("jean@videotron.ca", "hugues.thibodeau@videotron.qc.ca", "o'brien@example.com", "a+b@sub.domaine.quebec"):
            with self.subTest(ok=ok):
                self.assertIsNone(m.check(ok)["reason"])
                self.assertIsNone(m.suggest(ok))
        self.assertEqual(m.check("a@b")["reason"], "domain without a dot (e.g. gmail.com)")
        self.assertTrue(m.check("x@yopmail.com")["disposable"])
        self.assertTrue(m.check("x@mail.yopmail.com")["disposable"])

    def test_serveur_de_courriel_dig_simule(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix="test-rlq-dig-")
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "dig"), "w") as f:
            f.write('#!/bin/bash\ncase "$*" in *"MX gmail.com"*) echo "5 gmail-smtp-in.l.google.com.";; *"MX nul.example"*) echo "0 .";; '
                    '*"A seul.example"*) echo 1.2.3.4;; esac\n')
        os.chmod(os.path.join(d, "dig"), 0o755)
        ancien = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(ancien)))
        os.environ["PATH"] = d + ":" + os.environ["PATH"]
        os.environ["NGINX_TOOLS_INTERNET"] = "on"
        self.assertEqual(self.m.mx_status("gmail.com"), "mx")
        self.assertEqual(self.m.mx_status("nul.example"), "none")
        self.assertEqual(self.m.mx_status("seul.example"), "a-only")
        self.assertEqual(self.m.mx_status("rien.example"), "none")
        os.environ["NGINX_TOOLS_INTERNET"] = "off"
        self.assertEqual(self.m.mx_status("gmail.com"), "unknown")

    def test_stopforumspam_gravatar_et_recherche_web_reseau_simule(self):
        m = self.m
        appels = []

        def faux(url, timeout=8):
            appels.append(url)
            if "stopforumspam" in url:
                return 200, '{"success":1,"email":{"value":"x@y.z","appears":1,"frequency":12,"lastseen":"2026-10-01 10:00:00","confidence":87.5},' \
                            '"ip":[{"value":"11.95.32.106","appears":0,"frequency":0}]}'
            if "gravatar" in url:
                return 404, ""
            return 200, ('<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fforum.example%2Fu%2F1&amp;rut=x">Profil <b>x@y.z</b></a>')
        m._fetch = faux
        os.environ["NGINX_TOOLS_INTERNET"] = "on"
        self.addCleanup(os.environ.__setitem__, "NGINX_TOOLS_INTERNET", "off")
        r = m.internet_lookups("x@y.z", ["11.95.32.106"])
        self.assertEqual(r["stopforumspam"]["email"]["frequency"], 12)
        self.assertEqual(r["stopforumspam"]["ip"]["11.95.32.106"]["appears"], 0)
        self.assertFalse(r["gravatar"])
        self.assertEqual(r["web"]["results"], [("Profil x@y.z", "https://forum.example/u/1")])
        self.assertTrue(any("email=x%40y.z" in u for u in appels))
        m._fetch = lambda url, timeout=8: (None, "")
        r = m.internet_lookups("x@y.z", [])
        self.assertIsNone(r["stopforumspam"])
        self.assertIsNone(r["gravatar"])
        self.assertIsNone(r["web"])
        os.environ["NGINX_TOOLS_INTERNET"] = "off"
        self.assertEqual(m.internet_lookups("x@y.z", []), {})


if __name__ == "__main__":
    unittest.main()
