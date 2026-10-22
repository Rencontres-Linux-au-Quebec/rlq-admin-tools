"""Conventions de versionnage et de changelog, vérifiées pour TOUS les programmes :
version MAJEUR.MINEUR.AAAAMMJJ.HHMMSS valide ; --version dynamique et identique à la version déclarée ; résumé
d'en-tête à jour ; changelog présent, version la plus récente EN PREMIER, versions décroissantes ; --changelog
sans code ANSI quand la sortie est redirigée ; interruption d'un tube (« --changelog | head ») sans message
d'erreur ni trace Python (bugs trouvés en session : option absente de app-health-check.py, faux « ARRÊT
INATTENDU (code 141) » des scripts Bash)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
NATURE_TESTS = "conformité"   # run-all 1.188 (statistiques) : versions, changelogs, en-têtes, options triées : fichiers lus, rien d'exécuté (un test qui lance un programme reste « fonctionnel »)
import datetime
import os
import re
import subprocess
import unittest

from helpers import CONFIG_DIR, EnvTest, script_path, SCRIPTS_DIR

# Dossier de la suite (nginx-tools-tests ; « tests » avant run-all.sh 1.56) : nom réel, pour suivre un renommage.
NOM_SUITE = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

PROGRAMMES = ["nginx-log-audit.sh", "nginx-hardening.sh", "sync-crowdsec-blocklist.sh", "odoo-backup.sh", "odoo-update-module.sh",
              "app-log-check.py", "app-health-check.py", "web-monitor.py", "zip-versions.py", "app-log-live.py", "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "odoo-warmup.py", "host-perf-audit.py", f"{NOM_SUITE}/run-all.sh"]
VERSION_RE = r"(\d+)\.(\d+)\.(\d{8})\.(\d{6})"


def declared_version(text):
    m = re.search(r'(?:SCRIPT_VERSION|__version__)\s*=\s*"(' + VERSION_RE + r')"', text)
    return m.group(1) if m else None


def changelog_sections():
    """{cle: [versions]} lu dans CHANGELOG.md a la racine du depot (sections « ## cle », versions « ### x.y.z.w »)."""
    sections, cle = {}, None
    with open(os.path.join(SCRIPTS_DIR, "CHANGELOG.md"), encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.rstrip("\n")
            if ligne.startswith("## "):
                cle = ligne[3:].strip()
                sections.setdefault(cle, [])
            elif ligne.startswith("### ") and cle is not None:
                sections[cle].append(ligne[4:].strip())
    return sections


def launcher(name):
    return ["bash", script_path(name)] if name.endswith(".sh") else ["python3", script_path(name)]


PROGRAMMES_ANGLAIS = ("app-health-check.py", "zip-versions.py", "odoo-warmup.py", "host-perf-audit.py", "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "app-log-check.py", "web-monitor.py", "app-log-live.py")       # programmes dont le code est déjà en anglais (migration par étapes)


class Conventions(EnvTest):
    def each(self):
        for name in PROGRAMMES:
            if os.path.isfile(script_path(name)):
                with open(script_path(name), encoding="utf-8") as f:
                    yield name, f.read()

    def test_version_format_et_date_valide(self):
        for name, text in self.each():
            with self.subTest(programme=name):
                v = declared_version(text)
                self.assertIsNotNone(v, "variable de version absente ou mal formée")
                m = re.fullmatch(VERSION_RE, v)
                datetime.datetime.strptime(m.group(3) + m.group(4), "%Y%m%d%H%M%S")   # date et heure réelles

    def test_option_version_dynamique(self):
        for name, text in self.each():
            with self.subTest(programme=name):
                rc, out, err = self.run_cmd(launcher(name) + ["--version"])
                self.assertEqual(rc, 0, err)
                self.assertIn(declared_version(text), out)

    def test_entete_sans_historique(self):
        """L'historique des versions vit dans CHANGELOG.md : l'en-tete d'un programme ne le repete pas."""
        motif = re.compile(r"VERSION HISTORY|HISTORIQUE DE VERSION|HISTORIQUE \(|^#\s+\d+\.\d+\.\d{8}\.\d{6}\s")
        for name, text in self.each():
            with self.subTest(programme=name):
                entete = [l for l in text.splitlines()[:200] if l.lstrip().startswith("#")]
                fautifs = [l for l in entete if motif.search(l)]
                self.assertEqual(fautifs, [], "historique de versions dans l'en-tête (à retirer : voir CHANGELOG.md)")

    def test_changelog_plus_recent_en_premier(self):
        """CHANGELOG.md (racine du depot) : une section « ## NOM » par programme ; sa 1re version « ### » est la version
        courante et les versions sont decroissantes (plus recente d'abord)."""
        sections = changelog_sections()
        for name, text in self.each():
            with self.subTest(programme=name):
                cle = name if name.startswith("apps/") else os.path.basename(name)
                self.assertIn(cle, sections, f"pas de section « ## {cle} » dans CHANGELOG.md")
                versions = sections[cle]
                self.assertTrue(versions, "aucune entrée « ### version » dans la section du programme")
                self.assertEqual(versions[0], declared_version(text), "1re entrée ≠ version courante")
                cles = [tuple(int(x) for x in v.split(".")) for v in versions]
                self.assertEqual(cles, sorted(cles, reverse=True), "versions non décroissantes (plus récente d'abord)")

    def test_changelog_sans_ansi_si_redirige(self):
        for name, _ in self.each():
            with self.subTest(programme=name):
                r = subprocess.run(launcher(name) + ["--changelog"], capture_output=True, env=self.env)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertNotIn(b"\x1b[", r.stdout, "codes ANSI alors que la sortie est redirigée")

    def test_changelog_couleur_dans_un_terminal(self):
        for name, _ in self.each():
            with self.subTest(programme=name):
                raw, _ = self.run_pty(launcher(name) + ["--changelog"], [], keep_ansi=True)
                self.assertIn("\x1b[1;36m", raw, "numéros de version non colorés dans un terminal")

    def test_changelog_tube_interrompu_proprement(self):
        for name, _ in self.each():
            with self.subTest(programme=name):
                # 5 repetitions : l'echec depend de la vitesse relative des deux processus (course) — un seul essai
                # passait en session alors que le bug existait (app-log-check.py).
                cmd = " ".join(launcher(name)) + " --changelog | head -1 >/dev/null"
                for _ in range(5):
                    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=self.env)
                    self.assertNotIn("ARRÊT INATTENDU", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertNotIn("BrokenPipe", r.stderr)


class SansApplication(EnvTest):
    """2.3 : --version et --changelog fonctionnent sur une machine SANS application détectable (poste de travail) —
    web-monitor.py 2.0 à 2.2 chargeait le profil avant --changelog et échouait (« aucune application reconnue »)."""
    def test_version_et_changelog_sans_application(self):
        del self.env["APP_PROFILE"]
        self.mock_exit("systemctl", 1)                                  # aucune unité : aucune application détectée
        for name in PROGRAMMES:
            if not os.path.isfile(script_path(name)):
                continue
            for option in ("--version", "--changelog"):
                with self.subTest(programme=name, option=option):
                    rc, out, err = self.run_cmd(launcher(name) + [option])
                    self.assertEqual(rc, 0, err)
                    self.assertNotIn("ERREUR", err)

    def test_changelog_montre_seulement_sa_section(self):
        """--changelog n'affiche que la section du programme, sans bandeau de configuration."""
        for name in ("nginx-log-audit.sh", "app-log-check.py"):
            with self.subTest(programme=name):
                rc, out, err = self.run_cmd(launcher(name) + ["--changelog"])
                self.assertEqual(rc, 0, err)
                titres = re.findall(r"(?m)^## (\S+)", out)
                self.assertEqual(titres, [os.path.basename(name)], "autres sections ou titre absent")
                self.assertNotIn("Configuration :", out, "bandeau de configuration affiché avec --changelog")


class CompatibilitePython38(unittest.TestCase):
    """Python 3.8 minimum (Ubuntu 20.04, serveur BigBlueButton de PROD) : web-monitor.py 2.10 plantait sur
    str.removesuffix (3.9). Fonctions et syntaxes postérieures à 3.8 refusées dans tous les programmes Python."""
    INTERDITS = [r"\.removesuffix\(", r"\.removeprefix\(", r"BooleanOptionalAction", r"zip\([^)]*strict=",
                 r"\broot_dir=", r"\.bit_count\(", r"datetime\.UTC\b", r"import tomllib", r"^\s*match \S.*:\s*$",
                 r"functools\.cache\b", r"math\.lcm", r"(:|->) ?(list|dict|tuple|set)\[", r": ?\w+ ?\| ?None\b"]

    def test_aucune_fonction_posterieure_a_python_3_8(self):
        for name in ("app-health-check.py", "app-log-check.py", "web-monitor.py", "zip-versions.py", "app-log-live.py", "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "odoo-warmup.py", "host-perf-audit.py", "apps/_profile.py",
                     "apps/_reseau.py", "apps/_odoo_db.py", "apps/_bbb.py", "apps/_listes.py", "apps/_cache_ip.py", "apps/_courriel.py", "apps/_email_check.py",
                     "apps/_odoo_users.py", "apps/_sysperf.py", "apps/_record.py"):
            src = open(script_path(name), encoding="utf-8").read().splitlines()
            for motif in self.INTERDITS:
                with self.subTest(programme=name, motif=motif):
                    lignes = [f"{i}: {l.strip()}" for i, l in enumerate(src, 1) if re.search(motif, l) and not l.lstrip().startswith("#")]
                    self.assertEqual(lignes, [], "incompatible avec Python 3.8")


class RapportErreurs(unittest.TestCase):
    """--report-err dans CHAQUE programme : aide, acceptée avec --help/--version (sans rapport), appel du composant commun."""
    def test_dans_l_aide_et_sans_effet_avec_version(self):
        import subprocess
        for name in PROGRAMMES:
            if not os.path.isfile(script_path(name)):
                continue
            with self.subTest(programme=name):
                env = dict(os.environ, APP_PROFILE="odoo", NO_COLOR="1", NGINX_TOOLS_LANG="fr")      # l'aide est testée en français, même si run-all.sh tourne avec --lang en
                aide = subprocess.run(launcher(name) + ["--help"], capture_output=True, text=True, env=env).stdout
                self.assertIn("--report-err", aide)
                self.assertIn("rapport d'erreurs à copier-coller", aide.replace("\n", " ").replace("  ", " "))
                v = subprocess.run(launcher(name) + ["--version", "--report-err"], capture_output=True, text=True, env=env)
                self.assertEqual(v.returncode, 0, v.stderr)
                self.assertRegex(v.stdout, r"(?:version |v)\d+\.\d+\.\d{8}\.\d{6}")
                self.assertNotIn("RAPPORT D'ERREURS", v.stdout)

    def test_chaque_programme_appelle_le_composant_commun(self):
        for name in PROGRAMMES:
            with self.subTest(programme=name):
                texte = open(script_path(name), encoding="utf-8").read()
                if name.endswith(".sh"):
                    self.assertIn('. "$SCRIPT_DIR/apps/_rapport.sh"' if not name.endswith("run-all.sh") else '. "$PROG_DIR/apps/_rapport.sh"', texte)
                    self.assertIn("rapport_si_demande", texte)
                    self.assertIn("--report-err) shift ;;", texte)                   # accepté par l'analyseur d'options
                else:
                    lanceur = "launch_with_report" if name in PROGRAMMES_ANGLAIS else "lancer_avec_rapport"
                    self.assertIn(f"{lanceur}(", texte)
                    self.assertIn('add_argument("--report-err"', texte)
                    self.assertIn(f"sys.exit({lanceur}(", texte)


class RegleDesConfigurations(unittest.TestCase):
    """Règle commune des fichiers de configuration : /etc/default/<programme>.conf, PUIS ~/.<programme>.conf s'il existe, PUIS
    la ligne de commande (prioritaire) ; -c/--config : ce fichier seul ; les fichiers lus sont TOUJOURS affichés."""
    PYTHON = ("web-monitor", "zip-versions", "odoo-mail-retry", "odoo-chat-post", "odoo-docs", "odoo-warmup", "app-health-check", "app-log-check", "app-log-live", "host-perf-audit")
    BASH = ("sync-crowdsec-blocklist", "odoo-backup", "odoo-update-module", "nginx-log-audit", "nginx-hardening")
    PROPRES = {"odoo-backup", "app-health-check", "odoo-mail-retry", "odoo-warmup"}        # programmes qui lisent eux-mêmes leurs fichiers (en plus de la règle commune)
    AVEC_CONFIGURATION = {f"{n}.py": (f"{n}.conf", f".{n}.conf") for n in PYTHON}
    AVEC_CONFIGURATION.update({f"{n}.sh": (f"{n}.conf", f".{n}.conf") for n in BASH})

    def test_les_deux_emplacements_et_l_affichage(self):
        """Chaque programme applique la règle (module partagé apps/_config.py ou apps/_i18n.sh, ou son propre code) et la bibliothèque affiche les fichiers lus."""
        for nom, (systeme, perso) in self.AVEC_CONFIGURATION.items():
            with self.subTest(programme=nom):
                texte = open(script_path(nom), encoding="utf-8").read()
                base = nom.rsplit(".", 1)[0]
                if base in self.PROPRES:
                    self.assertRegex(texte, rf"/etc/default\}}?/{re.escape(systeme)}")
                    self.assertIn(perso, texte)
                    anglais = nom in PROGRAMMES_ANGLAIS
                    self.assertIn("Configuration read: " if anglais else "Configuration lue : ", texte)
                    self.assertIn("(the last one wins)" if anglais else "(le dernier l'emporte)", texte)
                else:
                    self.assertTrue("SCHEMA_CONFIG" in texte or "config_lire " in texte, "le programme doit lire son fichier de configuration (apps/_config.py ou apps/_i18n.sh)")
                    self.assertIn("LANGUAGE", texte, "la clé LANGUAGE doit être documentée dans le programme")
        for lib in ("apps/_config.py", "apps/_i18n.sh"):
            with self.subTest(bibliotheque=lib):
                texte = open(script_path(lib), encoding="utf-8").read()
                self.assertIn("Configuration lue : ", texte)
                self.assertIn("le dernier l'emporte", texte)
                self.assertIn("/etc/default", texte)
                self.assertIn(".conf", texte)

    def test_exemple_de_configuration_pour_chaque_programme(self):
        """doc/en/PROGRAMME.conf.example existe, cite la règle de lecture et la clé LANGUAGE."""
        for nom, (systeme, perso) in self.AVEC_CONFIGURATION.items():
            base = nom.rsplit(".", 1)[0]
            with self.subTest(programme=base):
                chemin = script_path(f"doc/en/{base}.conf.example")
                self.assertTrue(os.path.isfile(chemin), f"doc/en/{base}.conf.example absent")
                texte = open(chemin, encoding="utf-8").read()
                self.assertIn(f"/etc/default/{systeme}", texte)
                self.assertIn(perso, texte)
                self.assertRegex(texte, r"(?m)^#?LANGUAGE=")

    def test_aucune_autre_configuration_dans_le_repertoire_personnel(self):
        """Seuls les fichiers de la règle (~/.<programme>.conf) — pas de chemin personnel inventé ailleurs."""
        permis = {perso for _, perso in self.AVEC_CONFIGURATION.values()} | {".run-all.conf", ".app-default.conf"}
        for name in PROGRAMMES:
            with self.subTest(programme=name):
                for n, ligne in enumerate(open(script_path(name), encoding="utf-8"), 1):
                    for m in re.finditer(r"(?:~|\$HOME|\$\{HOME[^}]*\}|/root)/(\.[A-Za-z0-9_-]+\.(?:cfg|conf))", ligne):
                        if m.group(1).endswith(".cfg"):         # legacy name (rule before 2026-10-20): only on a line that handles the migration
                            if re.match(r"^\s*#\s+\d+\.\d+\.\d{8}\.\d{6} — ", ligne):
                                continue                            # summary line of a PAST version (history, never rewritten)
                            self.assertRegex(ligne, r"(?i)ancien|legacy", f"{name}:{n}: ~/.NAME.cfg is the legacy name — the rule is ~/.NAME.conf")
                            self.assertIn(m.group(1)[:-len(".cfg")] + ".conf", permis, f"{name}:{n}: {ligne.strip()[:100]}")
                        else:
                            self.assertIn(m.group(1), permis, f"{name}:{n}: {ligne.strip()[:100]}")

    def test_extension_conf_et_jamais_cfg(self):
        """2026-10-20 : le fichier personnel est ~/.PROGRAMME.conf, jamais .cfg — ni dans l'aide des programmes, ni dans les modèles doc/*.conf.example,
        ni dans la documentation (docs/, doc/*.md) ; l'ancien nom n'apparaît que dans le code qui le renomme."""
        motif = re.compile(r"~/\.[A-Za-z0-9_<>{}-]+\.cfg\b")
        fichiers = [os.path.join("doc", f) for f in os.listdir(script_path("doc")) if f.endswith((".conf.example", ".md"))]
        for langue in ("fr", "en"):
            dossier = script_path(os.path.join("docs", langue))
            if os.path.isdir(dossier):
                fichiers += [os.path.join("docs", langue, f) for f in os.listdir(dossier) if f.endswith(".md")]
        for f in sorted(fichiers):
            with self.subTest(fichier=f):
                self.assertIsNone(motif.search(open(script_path(f), encoding="utf-8").read()), f)


class CtrlC(unittest.TestCase):
    """Ctrl-C ne doit jamais afficher une trace d'appels Python : chaque programme Python l'intercepte au point d'entrée."""
    def test_programmes_python_interceptent_ctrl_c(self):
        for name in ("web-monitor.py", "app-health-check.py", "app-log-check.py", "zip-versions.py", "app-log-live.py", "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "host-perf-audit.py"):
            with self.subTest(programme=name):
                texte = open(script_path(name), encoding="utf-8").read()
                # web-monitor : executer() ; les autres : principal_protege() — appelés par le point d'entrée (lancer_avec_rapport)
                # programs migrated to English (SOURCE_EN): protected_main() / launch_with_report()
                en = name in PROGRAMMES_ANGLAIS
                fonction = "def execute():" if name == "web-monitor.py" else ("def protected_main():" if en else "def principal_protege():")
                lanceur = "launch_with_report" if en else "lancer_avec_rapport"
                self.assertIn(fonction, texte)
                self.assertIn("except KeyboardInterrupt", texte.split(fonction)[1][:500])
                self.assertIn(f"{lanceur}({fonction[4:-3]})", texte.split('if __name__ == "__main__":')[-1])


class MotifEtOu(unittest.TestCase):
    """« A && B || C » n'est pas un « si … sinon » : C s'exécute aussi quand B échoue. ShellCheck (SC2015) le signale, mais
    SELON SA VERSION — la 0.11 ne le voit pas, celle de Debian/Ubuntu oui (run-all.sh échouait sur le serveur alors qu'il
    réussissait en développement). Ce test cherche le motif lui-même : B doit être une commande qui ne peut pas échouer
    (echo, printf, return, exit, true, affectation) ; sinon, écrire un « if »."""
    SANS_RISQUE = {"echo", "printf", "return", "exit", "true", "false", ":", "break", "continue", "local", "read", "trap", "set", "unset"}

    @staticmethod
    def nettoyer(ligne):
        """Ligne sans commentaire, sans chaînes entre guillemets, ni contenus de [[ ]], (( )), $( ) et { } / ( ) groupés."""
        ligne = re.sub(r"'[^']*'", "Q", ligne)
        ligne = re.sub(r'"(?:[^"\\]|\\.)*"', "Q", ligne)
        ligne = re.sub(r"\s#.*$", "", ligne)
        if re.match(r"\s*\w+\(\)\s*\{", ligne):                 # fonction sur une ligne : son corps est analysé, pas avalé
            ligne = re.sub(r"^\s*\w+\(\)\s*\{\s*", "", ligne)
            ligne = re.sub(r";?\s*\}\s*$", "", ligne)
        for _ in range(6):
            nouvelle = re.sub(r"\[\[.*?\]\]|\(\(.*?\)\)|\$\([^()]*\)|\$\{[^{}]*\}|\{ [^{}]*; \}|\([^()]*\)", "G", ligne)
            if nouvelle == ligne:
                break
            ligne = nouvelle
        return ligne

    def test_aucun_et_ou_risque(self):
        for name in PROGRAMMES:
            if not name.endswith(".sh") or not os.path.isfile(script_path(name)):
                continue
            with self.subTest(programme=name):
                fautes = []
                for n, brut in enumerate(open(script_path(name), encoding="utf-8"), 1):
                    if brut.lstrip().startswith("#") or re.match(r"\s*(if|elif|while|until)\b", brut):
                        continue
                    ligne = self.nettoyer(brut.rstrip("\n"))
                    m = re.search(r"&&\s*([^|&;]*?)\s*\|\|", ligne)
                    if not m:
                        continue
                    mots = m.group(1).split()
                    premier = mots[0] if mots else ""
                    if premier in self.SANS_RISQUE or re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=", premier) or premier == "G":
                        continue
                    fautes.append(f"{name}:{n}: {brut.strip()[:110]}")
                self.assertEqual(fautes, [], "motif « A && B || C » avec B pouvant échouer : écrire un « if »")


class AideTriee(unittest.TestCase):
    """Options de l'aide (--help) par ORDRE ALPHABÉTIQUE dans tous les programmes (nom long, sans les tirets)."""
    def test_options_de_l_aide_par_ordre_alphabetique(self):
        import subprocess
        for name in PROGRAMMES:
            if not os.path.isfile(script_path(name)):
                continue
            with self.subTest(programme=name):
                r = subprocess.run(launcher(name) + ["--help"], capture_output=True, text=True,
                                   env=dict(os.environ, APP_PROFILE="odoo", NO_COLOR="1"))
                noms = [m.group(2).lstrip("-").lower() for m in
                        re.finditer(r"(?m)^ {2,4}(?:(-\w), )?(--[a-z0-9][a-z0-9.-]*)", r.stdout)]
                self.assertGreater(len(noms), 2, r.stdout[:300])
                self.assertEqual(noms, sorted(noms), "options de l'aide hors de l'ordre alphabétique")
                self.assertIn("help", noms)


class CheminSousCron(unittest.TestCase):
    """PATH complété (sync 1.10, audit 2.6, hardening 2.2) : sous cron, /usr/sbin et /sbin manquent."""
    def test_sbin_ajoutes_a_la_fin_sans_masquer(self):
        import subprocess
        for name in ("sync-crowdsec-blocklist.sh", "nginx-log-audit.sh", "nginx-hardening.sh", "odoo-backup.sh"):
            src = open(script_path(name), encoding="utf-8").read()
            bloc = re.search(r"^for _d in /usr/local/sbin /usr/sbin /sbin;.*\n(?:#.*\n)*export PATH\n", src, re.M)
            with self.subTest(programme=name):
                self.assertIsNotNone(bloc, "PATH non complété")
                self.assertLess(bloc.start(), src.index("\nset -euo pipefail\n") + 400)  # dès le début (après son commentaire)
                for depart, attendu in (("/usr/bin:/bin", "/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"),
                                        ("/tmp/mocks:/usr/sbin:/usr/bin", "/tmp/mocks:/usr/sbin:/usr/bin:/usr/local/sbin:/sbin")):
                    r = subprocess.run(["/bin/bash", "-c", bloc.group(0) + 'printf %s "$PATH"'], env={"PATH": depart},
                                       capture_output=True, text=True)
                    # suffixe : un bash qui ajoute ses propres dossiers en tête (environnement) ne fausse pas le test
                    self.assertTrue(r.stdout.endswith(attendu), r.stdout)
                # Pendant les tests (NGINX_TOOLS_TESTS) : PATH inchangé, /usr/sbin/ufw & co jamais joignables
                r = subprocess.run(["/bin/bash", "-c", bloc.group(0) + 'printf %s "$PATH"'],
                                   env={"PATH": "/usr/bin:/bin", "NGINX_TOOLS_TESTS": "1"}, capture_output=True, text=True)
                self.assertEqual(r.stdout, "/usr/bin:/bin")

    def test_aucune_commande_systeme_joignable_depuis_les_tests(self):
        """Un test a modifié le vrai ufw d'un serveur BigBlueButton (ufw actif, non simulé, trouvé dans /usr/sbin)."""
        import shutil
        from helpers import COMMANDES_SYSTEME, chemin_sans_commandes_systeme
        chemin = chemin_sans_commandes_systeme()
        joignables = [c for c in sorted(COMMANDES_SYSTEME) if shutil.which(c, path=chemin)]
        self.assertEqual(joignables, [])
        self.assertTrue(shutil.which("python3", path=chemin) and shutil.which("bash", path=chemin))


class OptionsEnAnglais(unittest.TestCase):
    """Noms d'options en ANGLAIS dans tous les programmes (les messages, eux, restent en français) — ex. --bilan
    renommée --summary en 1.4. Vérifie les caractères (aucun accent) et une liste de mots français courants."""
    MOTS_FRANCAIS = {"bilan", "aide", "jours", "semaine", "mois", "etat", "sommaire", "verbeux", "rapport",
                     "liste", "controle", "verifier", "sauvegarde", "annuler", "forcer", "creer", "effacer", "bannir"}

    def test_noms_des_options(self):
        for name in PROGRAMMES:
            chemin = script_path(name)
            if not os.path.isfile(chemin):
                continue
            texte = open(chemin, encoding="utf-8").read()
            if name.endswith(".py"):
                options = re.findall(r'add_argument\((?:"-\w", )?"--([^"]+)"', texte)
            else:
                options = re.findall(r'^\s+(?:-\w\|)?--([\w-]+)(?:\|[\w-]+)?\)', texte, re.M)
            self.assertTrue(options, f"aucune option trouvée dans {name}")
            for opt in options:
                with self.subTest(programme=name, option=opt):
                    self.assertRegex(opt, r"^[a-z0-9-]+$", "caractères non ASCII dans un nom d'option")
                    self.assertFalse(set(opt.split("-")) & self.MOTS_FRANCAIS, "mot français dans un nom d'option")


class NomsDeFichiersEnAnglais(unittest.TestCase):
    """2.2 : noms des fichiers LIVRÉS et des fichiers CRÉÉS par les programmes en anglais. Les lignes de migration, qui
    contiennent les anciens noms par nature, sont tolérées (elles citent migrer / ancien / _migr)."""
    MOTS = re.compile(r"(outils|aide_|lisezmoi|bannissements|derniere|dernier-|bloquees|publique|normalise|\.avant-|sauvegarde\.)", re.I)

    def test_fichiers_livres(self):
        racine = SCRIPTS_DIR
        liste = lambda d: os.listdir(d) if os.path.isdir(d) else []   # dossier absent (installation incomplète) : pas de plantage
        noms = liste(racine) + [f"apps/{n}" for n in liste(os.path.join(racine, "apps"))] + \
               [f"{NOM_SUITE}/{n}" for n in liste(os.path.dirname(os.path.abspath(__file__)))]
        for n in noms:
            if n.endswith(".changelog.txt") or n.startswith(".") or "__pycache__" in n:
                continue
            with self.subTest(fichier=n):
                self.assertIsNone(self.MOTS.search(n), "nom de fichier en français")

    def test_fichiers_crees_par_les_programmes(self):
        for name in PROGRAMMES + ["apps/_profile.sh", "apps/_profile.py"]:
            chemin = script_path(name)
            if not os.path.isfile(chemin):
                continue
            for i, ligne in enumerate(open(chemin, encoding="utf-8"), 1):
                if ligne.lstrip().startswith("#") or re.search(r"migr|ancien|new_or_old", ligne, re.I):
                    continue          # commentaires (dont l'historique) et migrations : anciens noms voulus
                # Formes de NOMS DE FICHIERS seulement (les messages, eux, restent en français : « bannissements »).
                m = re.search(r"[\w.$/{}-]*(bannissements\.tsv|derniere-[a-z]|dernier-[a-z]|ip-bloquees|ip-publique|\.avant-[a-z])[\w.-]*", ligne)
                with self.subTest(programme=name, ligne=i):
                    self.assertIsNone(m, f"nom de fichier en français : {m.group(0) if m else ''}")


class CopieConfiguration(unittest.TestCase):
    def test_copie_tests_nginx_odoo_identique_a_la_config_livree(self):
        """nginx-tools-tests/nginx-odoo/ doit être IDENTIQUE à nginx-odoo/ quand les deux existent : sinon les tests valident une
        autre configuration que celle livrée."""
        import filecmp
        livree = os.path.join(SCRIPTS_DIR, "nginx-odoo")
        copie = CONFIG_DIR                                        # run-all 1.188 : NGINX_ODOO_DIR d'abord
        if not (os.path.isdir(livree) and os.path.isdir(copie)):
            # Cas normal sur un serveur (seule la copie de la suite existe) : rien a comparer, donc rien de NON verifie
            # — le test reussit au lieu de se desactiver (il comptait a tort comme « point non verifie »).
            return
        ecarts = []
        def parcours(c):
            ecarts.extend(os.path.join(os.path.relpath(c.left, livree), f) for f in c.diff_files + c.left_only + c.right_only)
            for sous in c.subdirs.values():
                parcours(sous)
        parcours(filecmp.dircmp(livree, copie))
        self.assertEqual(ecarts, [], "copie désynchronisée")


if __name__ == "__main__":
    unittest.main()


class EnvironnementDesTests(unittest.TestCase):
    """2.x : les tests sont étiquetés par environnement (commun, odoo, bbb) ; run-all.sh n'exécute sur un serveur que les
    modules communs et ceux de SON environnement (un serveur BigBlueButton n'exécutait que par erreur des tests d'Odoo)."""
    RUN_ALL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-all.sh")

    def etiquettes(self):
        dossier = os.path.dirname(self.RUN_ALL)
        res = {}
        for f in sorted(os.listdir(dossier)):
            if f.startswith("test_") and f.endswith(".py"):
                m = re.search(r'(?m)^ENVIRONNEMENT = "([a-z0-9_-]+)"', open(os.path.join(dossier, f), encoding="utf-8").read())
                res[f[:-3]] = m.group(1) if m else None
        return res

    def lister(self, *options):
        import subprocess
        r = subprocess.run(["bash", self.RUN_ALL, "--list", *options], capture_output=True, text=True,
                           env=dict(os.environ, TEST_SCRIPTS_DIR=SCRIPTS_DIR, APP_PROFILE=""), timeout=60)
        retenus = re.search(r"Modules retenus \(\d+\) : (.*)", r.stdout)
        ecartes = re.search(r"Modules écartés \(\d+\) : (.*)", r.stdout)
        return (r.returncode, r.stdout + r.stderr, (retenus.group(1).split() if retenus else []),
                [m for m in (ecartes.group(1).split() if ecartes else []) if m != "aucun"])

    def test_chaque_module_declare_son_environnement(self):
        profils = {os.path.splitext(f)[0] for f in os.listdir(os.path.join(SCRIPTS_DIR, "apps")) if f.endswith(".conf")}
        for module, etiquette in self.etiquettes().items():
            with self.subTest(module=module):
                self.assertIsNotNone(etiquette, "ligne « ENVIRONNEMENT = \"commun|odoo|bbb\" » absente")
                self.assertIn(etiquette, profils | {"commun"})

    def test_selection_par_environnement(self):
        tous = set(self.etiquettes())
        odoo = {m for m, e in self.etiquettes().items() if e == "odoo"}
        bbb = {m for m, e in self.etiquettes().items() if e == "bbb"}
        self.assertTrue(odoo and bbb, "au moins un module propre à chaque environnement")
        rc, out, retenus, ecartes = self.lister("--app", "bbb")
        self.assertEqual(rc, 0, out)
        self.assertIn("Environnement : BigBlueButton (bbb) — forcé (--app)", out)
        self.assertTrue(bbb <= set(retenus) and not (odoo & set(retenus)), out)
        self.assertEqual(set(ecartes), odoo)
        rc, out, retenus, ecartes = self.lister("--app", "odoo")
        self.assertTrue(odoo <= set(retenus) and not (bbb & set(retenus)), out)
        self.assertEqual(set(ecartes), bbb)
        # Tous les environnements, ou serveur non reconnu : tous les modules
        rc, out, retenus, ecartes = self.lister("--app", "bbb", "--all-environments")
        self.assertEqual(set(retenus), tous)
        self.assertEqual(ecartes, [])
        rc, out, retenus, ecartes = self.lister()
        if "non reconnu" in out:
            self.assertEqual(set(retenus), tous)
        # Les modules communs tournent partout
        communs = {m for m, e in self.etiquettes().items() if e == "commun"}
        self.assertTrue(communs <= set(self.lister("--app", "bbb")[2]) and communs <= set(self.lister("--app", "odoo")[2]))

    def test_profil_inconnu_refuse(self):
        rc, out, retenus, ecartes = self.lister("--app", "inconnu")
        self.assertEqual(rc, 1)
        self.assertIn("profil d'application inconnu : inconnu", out)
        self.assertIn("bbb", out)


class EnTeteDeVersion(unittest.TestCase):
    """2.x : la PREMIÈRE ligne de TOUTE exécution — même --help, --changelog ou une option inconnue — est « nom vVERSION » ; --version
    n'affiche que la version (une seule ligne, pas de doublon). Programmes seulement : les composants apps/ sont internes (leur sortie est
    lue par d'autres programmes)."""
    PROGRAMMES = ["nginx-hardening.sh", "nginx-log-audit.sh", "odoo-backup.sh", "odoo-update-module.sh", "sync-crowdsec-blocklist.sh", "web-monitor.py",
                  "app-health-check.py", "app-log-check.py", "app-log-live.py", "odoo-mail-retry.py", "odoo-chat-post.py", "odoo-docs.py", "odoo-warmup.py", "host-perf-audit.py", "zip-versions.py", "run-all.sh"]
    SUR_STDERR = ("app-log-live.py",)        # sa sortie standard est le flux du journal : l'en-tête va sur la sortie d'erreur

    def chemin(self, nom):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), nom) if nom == "run-all.sh" else os.path.join(SCRIPTS_DIR, nom)

    def lancer(self, nom, *args):
        import subprocess
        interprete = "python3" if nom.endswith(".py") else "bash"
        env = dict(os.environ, NO_COLOR="1", TERM="dumb", HOME=os.path.join(os.path.dirname(os.path.abspath(__file__)), "no-home"))
        r = subprocess.run([interprete, self.chemin(nom), *args], capture_output=True, text=True, timeout=60, env=env, stdin=subprocess.DEVNULL)
        return r.stdout.splitlines(), r.stderr.splitlines()

    def version(self, nom):
        with open(self.chemin(nom), encoding="utf-8") as f:
            return re.search(r'(?:SCRIPT_VERSION=|__version__ = )"([^"]+)"', f.read()).group(1)

    def test_premiere_ligne_de_toute_execution(self):
        for nom in self.PROGRAMMES:
            attendu = f"{nom} v{self.version(nom)}"
            for option in ("--help", "--changelog", "--option-inconnue"):
                with self.subTest(programme=nom, option=option):
                    sortie, erreur = self.lancer(nom, option)
                    flux = erreur if nom in self.SUR_STDERR else sortie
                    self.assertTrue(flux, f"{nom} {option} : aucune sortie sur le flux attendu")
                    self.assertEqual(flux[0], attendu)
                    self.assertEqual((sortie + erreur).count(attendu), 1, "l'en-tête ne doit apparaître qu'une fois")

    def test_version_une_seule_ligne(self):
        for nom in self.PROGRAMMES:
            with self.subTest(programme=nom):
                sortie, erreur = self.lancer(nom, "--version")
                self.assertEqual(len([l for l in sortie + erreur if l.strip()]), 1, sortie + erreur)
                self.assertIn(self.version(nom), sortie[0])
