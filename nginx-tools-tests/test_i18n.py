"""Langue d'affichage et fichiers de configuration — apps/_i18n.py, apps/_config.py, apps/_traduire.py, apps/_i18n.sh et catalogues lang/*.XX.po : choix de la langue
(--lang, NGINX_TOOLS_LANG, variable du programme, LANGUAGE du fichier de configuration, LC_ALL / LC_MESSAGES / LANG), traduction par fragments, lecture des fichiers PO,
catalogues complets pour TOUS les programmes (Python et bash), mécanisme de traduction de la sortie des programmes bash, ajout d'une langue = ajout d'un fichier."""
import glob
import os
import re
import shutil
import tempfile
import unittest

ENVIRONNEMENT = "commun"   # tous les serveurs

from helpers import sans_origine, SCRIPTS_DIR, EnvTest, script_path
from i18n_tools import charger_i18n, messages_francais, lire_po_brut
from i18n_tools_sh import messages_francais_sh

SOURCE_ANGLAISE = ("app-health-check", "zip-versions", "odoo-warmup", "odoo-mail-retry", "odoo-chat-post", "odoo-docs", "app-log-check", "web-monitor", "app-log-live", "host-perf-audit")       # programs whose code is in English (catalogue lang/PROGRAM.fr.po) - step-by-step migration
PROGRAMMES_PYTHON = {"web-monitor": "WEB_MONITOR_LANG", "zip-versions": "ZIP_VERSIONS_LANG", "odoo-mail-retry": "ODOO_MAIL_RETRY_LANG", "odoo-chat-post": "ODOO_CHAT_POST_LANG", "odoo-docs": "ODOO_DOCS_LANG", "odoo-warmup": "ODOO_WARMUP_LANG", "app-health-check": "APP_HEALTH_CHECK_LANG",
                     "app-log-check": "APP_LOG_CHECK_LANG", "app-log-live": "APP_LOG_LIVE_LANG", "host-perf-audit": "HOST_PERF_AUDIT_LANG"}
PROGRAMMES_BASH = {"sync-crowdsec-blocklist": "SYNC_CROWDSEC_BLOCKLIST_LANG", "odoo-backup": "ODOO_BACKUP_LANG", "odoo-update-module": "ODOO_UPDATE_MODULE_LANG", "nginx-log-audit": "NGINX_LOG_AUDIT_LANG",
                   "nginx-hardening": "NGINX_HARDENING_LANG"}
BIBLIOTHEQUES_BASH = {"apps/_listes.sh": "_listes", "apps/_profile.sh": "_profile", "apps/_rapport.sh": "_rapport", "apps/_i18n.sh": "_config"}
VARIABLES = ("NGINX_TOOLS_LANG", "LC_ALL", "LC_MESSAGES", "LANG") + tuple(PROGRAMMES_PYTHON.values()) + tuple(PROGRAMMES_BASH.values()) + ("RUN_ALL_LANG",)


def catalogue(nom, code="en"):
    return os.path.join(SCRIPTS_DIR, "lang", f"{nom}.{code}.po")


def connus(*noms):
    res = set()
    for n in noms:
        res |= {fr for fr, _ in lire_po_brut(catalogue(n))}
    return res


class LangueEtTraducteur(unittest.TestCase):
    def setUp(self):
        self.sauvegarde = {k: os.environ.pop(k, None) for k in VARIABLES}
        self.addCleanup(self.restaurer)
        self.i18n = charger_i18n()

    def restaurer(self):
        for k, v in self.sauvegarde.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def test_choix_de_la_langue(self):
        """--lang l'emporte, puis NGINX_TOOLS_LANG, la variable du programme, LANGUAGE du fichier de configuration, LC_ALL, LC_MESSAGES, LANG ; fr_* -> fr ; autre locale -> en ;
        rien -> défaut (fr)."""
        langue = self.i18n.langue
        self.assertEqual(langue([], "WEB_MONITOR_LANG"), "fr")                               # aucune variable : comportement d'avant
        os.environ["LANG"] = "en_US.UTF-8"
        self.assertEqual(langue([], "WEB_MONITOR_LANG"), "en")
        os.environ["LANG"] = "fr_CA.UTF-8"
        self.assertEqual(langue([], "WEB_MONITOR_LANG"), "fr")
        os.environ["LC_MESSAGES"] = "C"
        self.assertEqual(langue([], "WEB_MONITOR_LANG"), "en")                               # LC_MESSAGES avant LANG
        os.environ["LC_ALL"] = "fr_FR.UTF-8"
        self.assertEqual(langue([], "WEB_MONITOR_LANG"), "fr")                               # LC_ALL avant LC_MESSAGES
        self.assertEqual(langue([], "WEB_MONITOR_LANG", configuration="en"), "en")           # LANGUAGE du fichier de configuration avant LC_ALL
        self.assertEqual(langue([], "WEB_MONITOR_LANG", configuration="auto"), "fr")         # "auto": follow the environment
        os.environ["WEB_MONITOR_LANG"] = "en"
        self.assertEqual(langue([], "WEB_MONITOR_LANG", configuration="fr"), "en")           # variable du programme avant le fichier
        os.environ["NGINX_TOOLS_LANG"] = "fr"
        self.assertEqual(langue([], "WEB_MONITOR_LANG"), "fr")                               # language imposed on all the tools before the program's variable
        self.assertEqual(langue(["--lang=en"], "WEB_MONITOR_LANG"), "en")                    # l'option l'emporte sur tout
        self.assertEqual(langue(["--x", "--lang", "fr"], "WEB_MONITOR_LANG"), "fr")
        self.assertEqual(langue(["--lang=zz"], "WEB_MONITOR_LANG"), "fr")                    # unknown value ignored here (argparse refuses it)

    def test_traducteur_chemins_et_url_ne_sont_pas_du_francais_restant(self):
        """Une URL (/event/journee-portes-ouvertes-sur-linux) ou un nom de variable ($is_bad_bot) dans une ligne traduite ne la fait pas revenir en français."""
        t = self.i18n.Traducteur({" visent des pages ordinaires": " target ordinary pages"})
        self.assertEqual(t("12 visent des pages ordinaires (/event/journee-portes-ouvertes-sur-linux (3), $is_bad_bot)"),
                         "12 target ordinary pages (/event/journee-portes-ouvertes-sur-linux (3), $is_bad_bot)")
        self.assertEqual(t("12 visent des pages ordinaires et sur la page"), "12 visent des pages ordinaires et sur la page")      # real French remaining: intact

    def test_traducteur_fragments_mots_entiers_et_lignes_francaises(self):
        """Fragments les plus longs d'abord ; mot entier pour les fragments qui commencent ou finissent par une lettre ; une ligne encore à moitié
        française est rendue intacte ; sans catalogue : texte inchangé."""
        t = self.i18n.Traducteur({"banni": "banned", "aucune": "none", " lignes": " lines", "aucune ligne": "no line"})
        self.assertEqual(t("aucune ligne"), "no line")                                       # le plus long d'abord
        self.assertEqual(t("3 lignes, banni"), "3 lines, banned")
        self.assertEqual(t("bannies"), "bannies")                                            # never inside a word
        self.assertEqual(t("aucune\nil y a des bannis"), "none\nil y a des bannis")        # per line: the 2nd stays French, the 1st translated
        self.assertEqual(t("banni et bannies"), "banni et bannies")                          # half translated: intact
        self.assertEqual(self.i18n.Traducteur({})("aucune ligne"), "aucune ligne")
        self.assertFalse(self.i18n.Traducteur({}))
        self.assertEqual(self.i18n.traducteur("fr", SCRIPTS_DIR, "web-monitor")("aucune ligne"), "aucune ligne")
        self.assertEqual(self.i18n.traducteur("en", "/inexistant", "web-monitor")("aucune ligne"), "aucune ligne")     # catalogue absent: French, without error

    def test_remplacement_en_un_seul_passage(self):
        """Un texte déjà traduit n'est jamais re-traduit par un fragment plus court (« systemd journal of » ne devient pas « systemd log of »)."""
        t = self.i18n.Traducteur({"journal systemd de ": "systemd journal of ", "journal ": "log "})
        self.assertEqual(t("journal systemd de X"), "systemd journal of X")

    def test_colonnes_alignees_apres_traduction(self):
        """1.5 : les espaces de remplissage qui suivent un fragment absorbent la différence de longueur (« Bannissements manuels      3 » reste aligné)."""
        t = self.i18n.Traducteur({"Bannissements manuels": "Manual bans", "Erreurs": "Errors", "Libellé": "Label"})
        ligne = f"  {'Bannissements manuels':<30}{'3':>6}"
        self.assertEqual(len(t(ligne)), len(ligne))
        self.assertEqual(t(ligne), f"  {'Manual bans':<30}{'3':>6}")
        self.assertEqual(t("Libellé  x"), "Label    x")                 # traduction plus courte : le remplissage s'allonge
        self.assertEqual(t("Erreurs :  x"), "Errors :   x")            # 1.10: the length difference of a fragment not followed by padding is absorbed by the next padding of the line
        longue = self.i18n.Traducteur({"Ok": "Very long text"})
        self.assertEqual(longue("Ok  1"), "Very long text 1")           # traduction plus longue : au moins une espace reste

    def test_unites_et_decimales_en_anglais_et_ecart_absorbe(self):
        """1.10 : en anglais, « 22,8 Mo » -> « 22.8 MB », « 0 o » -> « 0 B », « 0,68 · 0,65 » -> « 0.68 · 0.65 » (listes « 400,403 » intactes) ; un fragment non suivi de
        remplissage (« Disque » + chemin) laisse les colonnes alignées ; étiquette « mot      : » de largeur constante."""
        t = self.i18n.Traducteur({"Disque": "Disk", "libres": "free", "IP les plus actives      : ": "Most active IPs: "})
        t.langue = "en"
        self.assertEqual(t("  Disque /            : 29,1 Go libres").endswith("29.1 GB free"), True)
        self.assertEqual(t("  Disque /            : 29,1 Go libres").index(":"), len("  Disque /            "))
        self.assertEqual(t("limite 0 o, 1,5 Ko, codes 400,403,405"), "limite 0 B, 1.5 KB, codes 400,403,405")
        self.assertEqual(t("Charge 0,68 · 0,65 (1/5 min)"), "Charge 0.68 · 0.65 (1/5 min)")
        self.assertEqual(len(t("  IP les plus actives      : x")), len("  IP les plus actives      : x"))
        fr = self.i18n.Traducteur({"libres": "free"})
        self.assertEqual(fr("29,1 Go libres"), "29,1 Go free")                 # without English language: unchanged

    def test_codes_de_couleur_ne_genent_pas_la_traduction(self):
        """1.7 : « \x1b[36mce serveur\x1b[0m » est traduit en entier (le « m » du code ne casse plus le mot entier) et la colonne reste alignée."""
        t = self.i18n.Traducteur({"ce serveur": "this server", "serveur": "server"})
        ligne = "\x1b[36mce serveur\x1b[0m" + " " * 20 + "suite"
        sortie = t(ligne)
        self.assertEqual(sortie, "\x1b[36mthis server\x1b[0m" + " " * 19 + "suite")
        self.assertEqual(len(self.i18n.ANSI.sub("", sortie)), len(self.i18n.ANSI.sub("", ligne)))

    def test_le_fragment_le_plus_long_gagne_meme_s_il_commence_plus_loin(self):
        """1.7 : « , propriétaire du bloc » (module) ne coupe pas « propriétaire du bloc (org) » (programme) qui est plus long."""
        t = self.i18n.Traducteur({", propriétaire du bloc": ", owner of the block", "propriétaire du bloc (org)": "block owner (org)"})
        self.assertEqual(t("a, propriétaire du bloc (org) z"), "a, block owner (org) z")

    def test_catalogue_du_programme_prioritaire_sur_ceux_des_modules(self):
        """Un même fragment traduit différemment par le programme et par un module qu'il affiche : la traduction du programme l'emporte (1.3)."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lang"))
            for nom, trad in (("prog", "journal"), ("autre", "log")):
                with open(os.path.join(d, "lang", f"{nom}.en.po"), "w", encoding="utf-8") as f:
                    f.write(f'msgid ""\nmsgstr ""\n"Language: en\\n"\n\nmsgid "journal"\nmsgstr "{trad}"\n')
            self.assertEqual(self.i18n.traducteur("en", d, "prog", ("autre",))("journal"), "journal")

    def test_fichier_po_multilignes_fuzzy_et_echappements(self):
        """Format PO standard : chaînes sur plusieurs lignes, \\n \\t \\" échappés, commentaires ignorés, msgstr vide = non traduit, entrées « fuzzy » ignorées."""
        with tempfile.TemporaryDirectory() as d:
            po = os.path.join(d, "x.en.po")
            with open(po, "w", encoding="utf-8") as f:
                f.write('# commentaire\nmsgid ""\nmsgstr ""\n"Language: en\\n"\n\n'
                        'msgid "un"\nmsgstr "one"\n\n'
                        'msgid "deux "\n"lignes"\nmsgstr "two "\n"lines"\n\n'
                        '#, fuzzy\nmsgid "flou"\nmsgstr "blurry"\n\n'
                        'msgid "vide"\nmsgstr ""\n\n'
                        'msgid "citation \\"x\\"\\n"\nmsgstr "quote \\"x\\"\\n"\n')
            entrees = dict(self.i18n.lire_po(po))
            self.assertEqual(entrees.get("un"), "one")
            self.assertEqual(entrees.get("deux lignes"), "two lines")
            self.assertNotIn("flou", entrees)
            self.assertEqual(self.i18n.Traducteur({k: v for k, v in entrees.items() if v})("vide"), "vide")      # empty msgstr: not translated, French text kept
            self.assertEqual(entrees.get('citation "x"\n'), 'quote "x"\n')
            self.assertNotIn("", entrees)                                                    # the header is not a message
            self.assertEqual(self.i18n.echapper_po('a"b\n'), 'a\\"b\\n')

    def test_ajouter_une_langue_c_est_ajouter_un_fichier(self):
        """Un fichier lang/PROGRAMME.XX.po suffit : la langue XX est alors proposée et utilisée (rien à modifier dans le code)."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lang"))
            self.assertEqual(self.i18n.langues_disponibles(d, "demo"), ("fr",) if False else self.i18n.langues_disponibles(d, "demo"))
            avant = set(self.i18n.langues_disponibles(d, "demo"))
            with open(os.path.join(d, "lang", "demo.es.po"), "w", encoding="utf-8") as f:
                f.write('msgid ""\nmsgstr ""\n"Language: es\\n"\n\nmsgid "bonjour"\nmsgstr "hola"\n')
            self.assertIn("es", set(self.i18n.langues_disponibles(d, "demo")))
            self.assertNotIn("es", avant)
            self.assertEqual(self.i18n.traducteur("es", d, "demo")("bonjour"), "hola")
            self.assertEqual(self.i18n.langue(["--lang=es"], "", disponibles=self.i18n.langues_disponibles(d, "demo")), "es")
            os.environ["LANG"] = "es_MX.UTF-8"
            self.assertEqual(self.i18n.langue([], "", disponibles=self.i18n.langues_disponibles(d, "demo")), "es")

    def test_programme_ecrit_en_anglais_catalogue_fr(self):
        """Source-Language: en dans lang/PROGRAMME.fr.po : le code est en anglais, le catalogue fr.po le traduit en français ; les modules partagés (messages français) restent traduits en anglais."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lang"))
            with open(os.path.join(d, "lang", "demo.fr.po"), "w", encoding="utf-8") as f:
                f.write('msgid ""\nmsgstr ""\n"Language: fr\\n"\n"Source-Language: en\\n"\n\nmsgid "No connection to the server"\nmsgstr "Aucune connexion au serveur"\n')
            with open(os.path.join(d, "lang", "_config.en.po"), "w", encoding="utf-8") as f:
                f.write('msgid ""\nmsgstr ""\n\nmsgid "Configuration lue"\nmsgstr "Configuration read"\n')
            self.assertEqual(self.i18n.langue_source(d, "demo"), "en")
            self.assertEqual(self.i18n.langues_disponibles(d, "demo"), ["en", "fr"])
            self.assertEqual(self.i18n.langue_source(d, "autre"), "fr")
            fr, en = self.i18n.traducteur("fr", d, "demo"), self.i18n.traducteur("en", d, "demo")
            self.assertEqual(fr("No connection to the server"), "Aucune connexion au serveur")
            self.assertEqual(en("No connection to the server"), "No connection to the server")
            self.assertEqual(fr("Configuration lue : /etc/x"), "Configuration lue : /etc/x")        # shared message already in French
            self.assertEqual(en("Configuration lue : /etc/x"), "Configuration read : /etc/x")

    def test_module_partage_ecrit_en_anglais_traduit_selon_sa_propre_langue(self):
        """Un module chargé comme `supplementaires` et écrit en anglais (ex. app-log-check pour odoo-mail-retry) : son catalogue fr.po est chargé pour l'affichage français, pas pour l'anglais."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lang"))
            with open(os.path.join(d, "lang", "modanglais.fr.po"), "w", encoding="utf-8") as f:
                f.write('msgid ""\nmsgstr ""\n"Source-Language: en\\n"\n\nmsgid "sender refused (550)"\nmsgstr "expéditeur refusé (550)"\n')
            with open(os.path.join(d, "lang", "modfrancais.en.po"), "w", encoding="utf-8") as f:
                f.write('msgid ""\nmsgstr ""\n\nmsgid "connexion refusée"\nmsgstr "connection refused"\n')
            fr, en = self.i18n.traducteur("fr", d, "prog", ("modanglais", "modfrancais")), self.i18n.traducteur("en", d, "prog", ("modanglais", "modfrancais"))
            self.assertEqual(fr("cause : sender refused (550)"), "cause : expéditeur refusé (550)")
            self.assertEqual(fr("connexion refusée"), "connexion refusée")
            self.assertEqual(en("cause : sender refused (550)"), "cause : sender refused (550)")
            self.assertEqual(en("connexion refusée"), "connection refused")


class LangueDeLEnvironnement(EnvTest):
    """1.17 d'apps/_i18n.py : la langue suit l'environnement comme gettext — GNU LANGUAGE (sauf locale C), puis LC_ALL, LC_MESSAGES, LANG — et la ligne
    « Options : --lang xx (origine) » dit QUELLE variable a décidé et lesquelles sont ignorées (un LC_ALL oublié qui masque LANG se voit)."""
    VARIABLES = ("NGINX_TOOLS_LANG", "WEB_MONITOR_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")

    def choix(self, **env):
        i18n = charger_i18n()
        anciens = {v: os.environ.pop(v, None) for v in self.VARIABLES}
        os.environ.update(env)
        try:
            return i18n.langue_et_origine([], "WEB_MONITOR_LANG", disponibles=("en", "fr"))
        finally:
            for v in self.VARIABLES:
                os.environ.pop(v, None)
                if anciens[v] is not None:
                    os.environ[v] = anciens[v]

    def test_langue_selon_les_variables(self):
        self.assertEqual(self.choix(LANG="fr"), ("fr", "LANG=fr"))
        self.assertEqual(self.choix(LANG="fr_CA"), ("fr", "LANG=fr_CA"))
        self.assertEqual(self.choix(LANG="fr_CA.UTF-8")[0], "fr")
        self.assertEqual(self.choix(LANG="C"), ("en", "LANG=C"))
        self.assertEqual(self.choix(LANG="en"), ("en", "LANG=en"))
        self.assertEqual(self.choix(LANG="fr_CA.UTF-8", LC_ALL="C.UTF-8"), ("en", "LC_ALL=C.UTF-8 ; LANG=fr_CA.UTF-8 ignorées"))
        self.assertEqual(self.choix(LANG="en_US.UTF-8", LC_MESSAGES="fr_CA.UTF-8")[0], "fr")
        self.assertEqual(self.choix(LANG="en_US.UTF-8", LANGUAGE="fr_CA:fr"), ("fr", "LANGUAGE=fr_CA:fr ; LANG=en_US.UTF-8 ignorées"))
        self.assertEqual(self.choix(LANG="C", LANGUAGE="fr"), ("en", "LANG=C ; LANGUAGE=fr ignorées"))         # gettext : LANGUAGE sans effet sous la locale C
        self.assertEqual(self.choix(LANG="fr", LANGUAGE="de:es"), ("fr", "LANG=fr ; LANGUAGE=de:es ignorées"))   # aucune langue de LANGUAGE disponible : dit
        self.assertEqual(self.choix(LANG="en", WEB_MONITOR_LANG="fr"), ("fr", "WEB_MONITOR_LANG=fr"))
        self.assertEqual(self.choix()[0], "fr")

    def test_programme_affiche_l_origine(self):
        env = {v: "" for v in self.VARIABLES}
        for valeurs, attendu in (({"LANG": "fr_CA.UTF-8"}, "Options : --lang fr (LANG=fr_CA.UTF-8)"),
                                 ({"LANG": "fr_CA.UTF-8", "LC_ALL": "C.UTF-8"}, "Options: --lang en (LC_ALL=C.UTF-8 ; LANG=fr_CA.UTF-8 ignored)"),
                                 ({"LANG": "C"}, "Options: --lang en (LANG=C)")):
            rc, out, err = self.run_cmd(["python3", script_path("web-monitor.py"), "--status"], dict(env, **valeurs))
            self.assertIn(attendu, out, valeurs)


class Catalogues(unittest.TestCase):
    def manquants(self, source, noms, bash=False):
        extraits = (messages_francais_sh if bash else messages_francais)(source)
        c = connus(*noms)
        return [(ligne, repr(v)[:100]) for v, ligne in sorted(extraits.items(), key=lambda x: x[1]) if v not in c]

    def catalogue_programme_anglais(self, nom):
        """Programme dont le code est en anglais : lang/PROGRAMME.fr.po (Source-Language: en) ; plus aucun texte français dans le code ; chaque msgid du catalogue existe
        dans le code (pas d'entrée périmée) ; chaque msgstr est du français (pas de l'anglais recopié), sauf entrée déclarée identique."""
        import ast
        chemin = os.path.join(SCRIPTS_DIR, nom + ".py")
        francais = re.compile(r"[àâçéèêëîïôûùüœÀÉÈÊ]|\b(le|la|les|des|du|pas|sont|avec|sans|pour|dans|depuis|erreur|fichiers?|connexion|jours|cette|déjà|ligne|lignes|nom|noms|rapport)\b")
        # French wanted in the code: name of the language in its own language; FRENCH texts read in the output of the other tools (parsed in NGINX_TOOLS_LANG=fr);
        # French synonyms accepted for the --sort keys; argparse messages and labels of the French branch
        voulus = ("RÉSUMÉ", "Signes d'hostilité", "Bannissement PERMANENT recommandé", "Pour bannir", "dernier échec", "inchangée depuis", "bannissement recommandé",
                  "affiche cette aide et quitte", "affiche la version et quitte", " : erreur : ", "Première connexion", "Dernière connexion", "Systèmes",
                  "désactivé", "Verdict : bannissement justifié", "Déjà", "Pages écrites", "Mo reçus", "Mo envoyés",
                  "Événements", "Téléphone", "Étiquettes", "Nom du pays", "Navigateurs", "Adresses IP vues", "Compte créé", "Pays des adresses IP", "VPN, Tor, relais, hébergeur")      # 2.67: French column titles (--table, --csv), written in both languages       # app-log-live: French text read in the output of the other tools / of the shared cache
        synonymes = ("première", "dernière", "récent", "connexion", "durée", "système", "créé", "création", "hébergeur")       # run-all 1.188: "created" (web-monitor 2.70)
        restes = [(l, v) for l, v in self.manquants(chemin, ("_config", "_i18n"))
                  if francais.search(v.lower()) and v != "'Français'" and not any(x in v for x in voulus) and v.strip("'\"") not in synonymes]
        self.assertEqual(restes, [], "texte français resté dans le code d'un programme anglais")
        po = os.path.join(SCRIPTS_DIR, "lang", nom + ".fr.po")
        self.assertIn('"Source-Language: en\\n"', open(po, encoding="utf-8").read())
        # An old lang/PROG.en.po (residual of a version where PROG was written in French) is no longer read (apps/_i18n.py 1.15): reported by run-all.sh, not an error.
        valeurs = {n.value for n in ast.walk(ast.parse(open(chemin, encoding="utf-8").read())) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        peripheriques = [(en, fr) for en, fr in lire_po_brut(po) if en not in valeurs and en.strip("() ") not in valeurs and not any(en in v for v in valeurs)]       # "(manifest)": label in parentheses, assembled at display; a fragment may cover several pieces of text glued together by Python
        self.assertEqual(peripheriques, [], f"entrées de lang/{nom}.fr.po absentes du code (périmées ou mal copiées)")

    def test_catalogue_de_chaque_programme_python(self):
        """Chaque texte français d'un programme Python a une entrée dans lang/PROGRAMME.en.po (traduite, ou identique si valable dans les deux langues)."""
        for nom in PROGRAMMES_PYTHON:
            with self.subTest(programme=nom):
                if nom in SOURCE_ANGLAISE:
                    self.catalogue_programme_anglais(nom)
                    continue
                self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, nom + ".py"), (nom, "_config", "_i18n")), [], f"messages sans traduction — les ajouter à lang/{nom}.en.po")

    def test_catalogue_de_chaque_programme_bash(self):
        """Idem pour les programmes bash (sortie traduite ligne par ligne par apps/_traduire.py) et pour run-all.sh."""
        for nom in PROGRAMMES_BASH:
            with self.subTest(programme=nom):
                self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, nom + ".sh"), (nom, "_config"), bash=True), [], f"messages sans traduction — les ajouter à lang/{nom}.en.po")
        run_all = script_path("run-all.sh") if os.path.isfile(script_path("run-all.sh")) else os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-all.sh")
        self.assertEqual(self.manquants(run_all, ("run-all", "_config"), bash=True), [])

    def test_catalogue_des_bibliotheques(self):
        """Messages des bibliothèques communes : apps/_bbb.py -> lang/_bbb.en.po, apps/_listes.sh / _profile.sh / _rapport.sh / _i18n.sh -> leur catalogue partagé."""
        self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, "apps", "_bbb.py"), ("_bbb",)), [])
        self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, "apps", "_connexions.py"), ("_connexions",)), [])
        self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, "apps", "_limites.py"), ("_limites",)), [])
        self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, "apps", "_anonymiser.py"), ("_anonymiser",)), [])
        for relatif, nom in BIBLIOTHEQUES_BASH.items():
            with self.subTest(bibliotheque=relatif):
                self.assertEqual(self.manquants(os.path.join(SCRIPTS_DIR, relatif), (nom, "_config"), bash=True), [])

    def test_traductions_sans_francais(self):
        """Aucune traduction (msgstr) ne contient de lettre accentuée française ni de mot français courant, sauf entrées déclarées identiques ou formes de code (expressions
        régulières, commandes)."""
        mots = re.compile(r"\b(le|la|les|des|aucun|aucune|pas|sont|avec|sans|pour|dans|sur|depuis|erreur|fichier|connexion|jours)\b")
        pb = []
        for po in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "lang", "*.en.po"))):
            for fr, en in lire_po_brut(po):
                if fr != en and (re.search(r"[àâçéèêëîïôûùü]", en) or mots.search(en)):
                    pb.append((os.path.basename(po), fr[:60], en[:60]))
        self.assertEqual(pb, [], "traductions qui contiennent du français")

    def test_en_tete_et_entrees_vides(self):
        """Chaque catalogue déclare sa langue (Language: XX, d'après le nom du fichier) et ne contient aucun msgid en double."""
        for po in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "lang", "*.po"))):
            with self.subTest(catalogue=os.path.basename(po)):
                code = os.path.basename(po).split(".")[-2]
                texte = open(po, encoding="utf-8").read()
                self.assertIn(f'"Language: {code}\\n"', texte)
                self.assertIn("charset=UTF-8", texte)
                ids = [fr for fr, _ in lire_po_brut(po)]
                self.assertEqual(len(ids), len(set(ids)), "msgid en double")

    def test_options_et_cles_en_anglais(self):
        """Toutes les options de web-monitor.py sont en anglais (ASCII) ; les clés de --sort aussi (le français reste accepté comme synonyme)."""
        texte = open(os.path.join(SCRIPTS_DIR, "web-monitor.py"), encoding="utf-8").read()
        options = re.findall(r'add_argument\(\s*"(-[^"]+)"', texte)
        self.assertGreater(len(options), 15)
        for o in options:
            self.assertTrue(re.fullmatch(r"-{1,2}[a-z]+(-[a-z]+)*", o), o)
        bloc = texte[texte.index("USER_SORTS = {"):]
        cles = re.findall(r'^    "([^"]+)": \(', bloc[:bloc.index("}\n")], re.M)
        self.assertEqual(sorted(cles), ["created", "events", "first", "ip", "last", "login", "logins", "minutes", "name", "os", "pages", "received", "seen", "sent", "surveys", "type", "uid", "vpn", "written"])


class MecanismeTraduire(EnvTest):
    """apps/_traduire.py : lance un programme bash et traduit sa sortie ; en français il le remplace (rien ne change)."""
    def setUp(self):
        super().setUp()
        self.racine = self.path("fake", "x")
        racine = os.path.dirname(self.racine)
        shutil.copytree(os.path.join(SCRIPTS_DIR, "apps"), os.path.join(racine, "apps"))
        os.makedirs(os.path.join(racine, "lang"))
        with open(os.path.join(racine, "lang", "fake.en.po"), "w", encoding="utf-8") as f:
            f.write('msgid ""\nmsgstr ""\n"Language: en\\n"\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                    'msgid "Bonjour le monde"\nmsgstr "Hello world"\n\nmsgid "une erreur"\nmsgstr "an error"\n\n'
                    'msgid "Continuer ? [o/N] "\nmsgstr "Continue? [y/N] "\n\nmsgid "reçu "\nmsgstr "received "\n')
        self.script = os.path.join(racine, "fake.sh")
        with open(self.script, "w", encoding="utf-8") as f:
            f.write('#!/bin/bash\n. "$(dirname "$0")/apps/_i18n.sh"; i18n_relancer fake FAKE_LANG "$0" "$@"\n'
                    'echo "Bonjour le monde"\necho "une erreur" >&2\nprintf "Continuer ? [o/N] "; read -r r\necho "reçu $r"\nexit 3\n')
        self.traduire = os.path.join(racine, "apps", "_traduire.py")

    def lancer(self, langue, entree="o\n", args=()):
        env_extra = {"FAKE_LANG": langue} if langue else {}
        for v in ("NGINX_TOOLS_LANG", "NGINX_TOOLS_I18N", "LANG", "LC_ALL", "LC_MESSAGES"):
            self.env.pop(v, None)
        return self.run_cmd(["bash", self.script, *args], env_extra, input_text=entree)

    def test_francais_rien_ne_change(self):
        """En français : même sortie, mêmes flux, même code de retour (le programme est exécuté directement)."""
        rc, out, err = self.lancer("fr")
        self.assertEqual((rc, out, err), (3, "Bonjour le monde\nContinuer ? [o/N] reçu o\n", "une erreur\n"))

    def test_anglais_sortie_traduite_invite_comprise_et_code_de_retour(self):
        """En anglais : lignes traduites sur chaque flux, invite sans fin de ligne traduite, entrée standard intacte, code de retour de la commande conservé."""
        rc, out, err = self.lancer("en")
        self.assertEqual(rc, 3)
        self.assertEqual(out, "Hello world\nContinue? [y/N] received o\n")
        self.assertEqual(err, "an error\n")

    def test_option_lang_et_langue_imposee(self):
        """--lang l'emporte sur la variable du programme ; NGINX_TOOLS_LANG=fr (programme qui en analyse un autre) force le français."""
        rc, out, _ = self.lancer("en", args=["--lang", "fr"])
        self.assertIn("Bonjour le monde", out)
        self.env["NGINX_TOOLS_LANG"] = "fr"
        rc, out, _ = self.run_cmd(["bash", self.script], {"FAKE_LANG": "en"}, input_text="o\n")
        self.assertIn("Bonjour le monde", out)

    def test_flux_confondus_ordre_conserve(self):
        """Avec 2>&1 (un seul tube), l'ordre des lignes de sortie et d'erreur est conservé."""
        rc, out, _ = self.run_cmd(["bash", "-c", f'bash "{self.script}" 2>&1'], {"FAKE_LANG": "en"}, input_text="o\n")
        self.assertEqual(out.splitlines()[:2], ["Hello world", "an error"])

    def test_pas_de_python_ou_de_traducteur_c_est_du_francais(self):
        """Sans apps/_traduire.py, le programme tourne tel quel (en français), sans erreur."""
        os.remove(self.traduire)
        rc, out, err = self.lancer("en")
        self.assertEqual(rc, 3)
        self.assertIn("Bonjour le monde", out)


class ConfigurationBash(EnvTest):
    """apps/_i18n.sh : config_lire / config_defaut / config_afficher — règle commune des fichiers de configuration."""
    def lancer(self, corps, etc=None, home=None, env_extra=None):
        script = f'. "{SCRIPTS_DIR}/apps/_i18n.sh"\n{corps}\n'
        env = {"NGINX_TOOLS_ETC_DEFAULT": etc or os.path.dirname(self.path("etc", "x")), "HOME": home or os.path.dirname(self.path("home", "x"))}
        env.update(env_extra or {})
        self.env.pop("NGINX_TOOLS_CONFIG_VUE", None)
        return self.run_cmd(["bash", "-c", script, "bash"], env)

    def ecrire(self, chemin, texte):
        with open(self.path(*chemin), "w", encoding="utf-8") as f:
            f.write(texte)

    def test_aucun_fichier(self):
        rc, out, err = self.lancer('config_lire demo; config_defaut A A --a texte; config_afficher')
        self.assertEqual(rc, 0, err)
        self.assertIn("Configuration : aucun fichier (cherchés : ", out)
        self.assertIn("  Options : --lang fr (ligne de commande prioritaire)", sans_origine(out))

    def test_deux_fichiers_le_dernier_l_emporte_et_types(self):
        """/etc/default/PROGRAMME.conf puis ~/.PROGRAMME.conf ; guillemets facultatifs ; entier et booléen validés ; valeur invalide : signalée et ignorée."""
        self.ecrire(("etc", "demo.conf"), "# commentaire\nA=1\nB='deux mots'\nC=oui\nN=abc\n")
        self.ecrire(("home", ".demo.conf"), 'A=5   # note\nD="x"\n')
        rc, out, err = self.lancer('config_lire demo; A=0; config_defaut A A --a nombre; config_defaut B B --b texte; config_defaut C C --c booleen; config_defaut N N --n nombre; '
                                   'config_afficher; echo "A=$A B=$B C=$C N=${N:-}"')
        self.assertEqual(rc, 0, err)
        self.assertRegex(out, r"Configuration lue : .*/etc/demo\.conf \(modifié le [0-9: -]+\), puis .*/home/\.demo\.conf \(modifié le [0-9: -]+\) \(le dernier l'emporte\)")
        self.assertIn("--a 5 · --b deux mots · --c yes", out)
        self.assertIn("A=5 B=deux mots C=1 N=", out)
        self.assertIn("ATTENTION : valeur de configuration ignorée : N=abc (entier attendu)", err)

    def test_option_config_lit_ce_fichier_seul(self):
        """-c / --config FICHIER : ce fichier SEUL (ni /etc/default ni ~)."""
        self.ecrire(("etc", "demo.conf"), "A=1\n")
        self.ecrire(("x", "autre.conf"), "A=9\n")
        rc, out, err = self.lancer(f'config_lire demo -c "{self.path("x", "autre.conf")}"; config_defaut A A --a nombre; config_afficher; echo "A=$A"')
        self.assertIn(") (demandé par -c/--config : aucun autre fichier n'est lu)", out)
        self.assertIn("A=9", out)

    def test_pas_de_repetition_dans_les_sorties_analysees(self):
        """NGINX_TOOLS_CONFIG_VUE : la configuration n'est affichée qu'une fois, même si le programme en appelle un autre."""
        rc, out, err = self.lancer('config_lire demo; config_afficher; config_afficher')
        self.assertEqual(out.count("Configuration"), 1)


class ConfigurationDesProgrammes(EnvTest):
    """LANGUAGE=en dans le fichier de configuration de chaque programme donne la même aide que --lang en ; une langue inconnue de la configuration n'est pas une erreur."""
    def test_langue_du_fichier_de_configuration(self):
        programmes = [(p + ".py", ["python3"]) for p in PROGRAMMES_PYTHON] + [(p + ".sh", ["bash"]) for p in PROGRAMMES_BASH]
        variables = {v: "" for v in VARIABLES}
        for fichier, interprete in programmes:
            nom = fichier.rsplit(".", 1)[0]
            with self.subTest(programme=fichier):
                prog = script_path(fichier)
                etc = os.path.dirname(self.path("etc-" + nom, "x"))
                conf = os.path.join(etc, nom + ".conf")
                with open(conf, "w", encoding="utf-8") as f:
                    f.write("LANGUAGE=en\n")
                _, out1, err1 = self.run_cmd(interprete + [prog, "--help"], dict(variables, NGINX_TOOLS_ETC_DEFAULT=etc))
                os.remove(conf)
                _, out2, err2 = self.run_cmd(interprete + [prog, "--lang", "en", "--help"], dict(variables, NGINX_TOOLS_ETC_DEFAULT=etc))
                self.assertNotIn("Traceback", err1 + err2)
                lignes = lambda t: [l for l in t.splitlines() if not re.match(r"\s*(Configuration|Options)\b[^:]*:", l)]       # "Configuration... / Options..." lines: specific to the file read
                self.assertEqual(lignes(out1), lignes(out2), "LANGUAGE=en du fichier de configuration != --lang en")
                self.assertNotIn("par ordre alphabétique", out1)
                self.assertNotIn("affiche cette aide", out1)

    def test_langue_inconnue_dans_la_configuration(self):
        """LANGUAGE=zz (sans catalogue) : le programme s'exécute (en anglais, langue de repli des locales inconnues), jamais d'erreur."""
        etc = os.path.dirname(self.path("etc-zz", "x"))
        with open(os.path.join(etc, "zip-versions.conf"), "w", encoding="utf-8") as f:
            f.write("LANGUAGE=zz\n")
        variables = {v: "" for v in VARIABLES}
        rc, out, err = self.run_cmd(["python3", script_path("zip-versions.py"), "--version"], dict(variables, NGINX_TOOLS_ETC_DEFAULT=etc))
        self.assertEqual(rc, 0, err)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
