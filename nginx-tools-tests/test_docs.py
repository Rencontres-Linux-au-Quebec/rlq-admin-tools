"""Documentation bilingue (doc/en, doc/fr) : mêmes pages en anglais et en français, une page par programme, aide réelle insérée, XML du module de pages Site web valide,
aucune donnée personnelle dans les pages produites."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import importlib.util
import os
import re
import tempfile
import unittest

from helpers import script_path

try:
    import markdown  # noqa: F401
except ImportError:
    markdown = None

PROGRAMMES = ("nginx-hardening", "nginx-log-audit", "sync-crowdsec-blocklist", "web-monitor", "app-health-check", "app-log-check", "app-log-live", "odoo-backup",
              "odoo-update-module", "odoo-warmup", "odoo-mail-retry", "odoo-chat-post", "odoo-docs", "zip-versions", "host-perf-audit")
def _termes_personnels():
    """run-all 1.188 : termes personnels (noms, pseudonymes de l'équipe) HORS du dépôt public — NGINX_TOOLS_PERSONAL_TERMS (virgules), sinon
    /etc/default/nginx-tools-personal-terms.conf (NGINX_TOOLS_ETC_DEFAULT), un terme par ligne (# : commentaire) ; s'ajoutent aux termes génériques."""
    termes = [t for t in os.environ.get("NGINX_TOOLS_PERSONAL_TERMS", "").split(",") if t.strip()]
    chemin = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), "nginx-tools-personal-terms.conf")
    try:
        termes += [l.strip() for l in open(chemin, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        pass
    return [re.escape(t.strip()) for t in termes]


PERSONNEL = re.compile("|".join([r"gmail\.com", r"rencontres-linux\.quebec", r"services-conseils"] + _termes_personnels()), re.I)

# run-all 1.192 : le nom LÉGAL de l'entreprise est permis comme auteur du module Odoo (titulaire du droit d'auteur, champ exigé par Odoo), et SEULEMENT
# là : clé « author » d'un __manifest__.py. Seul ce nom exact est retiré de la ligne avant la recherche ; le reste de la ligne reste vérifié (un courriel
# ou un nom personnel ajouté à l'auteur échoue toujours) ; ailleurs (pages, XML, autres clés du manifeste) le terme reste interdit.
AUTEUR_LEGAL = re.compile(r"Services-Conseils Linux Inc\.")
CLE_AUTEUR = re.compile(r"""^\s*\{?\s*['"]author['"]\s*:""")


def donnee_personnelle(fichier, ligne):
    """Le terme personnel trouvé dans la ligne (re.Match), ou None ; le nom légal n'est toléré que dans la clé « author » d'un __manifest__.py."""
    if os.path.basename(fichier) == "__manifest__.py" and CLE_AUTEUR.match(ligne):
        ligne = AUTEUR_LEGAL.sub("", ligne)
    return PERSONNEL.search(ligne)


def charger():
    spec = importlib.util.spec_from_file_location("build_docs_t", script_path("doc/build_docs.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(markdown is None, "module Python « markdown » absent (apt install python3-markdown)")
class Documentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = charger()
        cls.dossier = tempfile.TemporaryDirectory()
        cls.n = cls.m.build(cls.dossier.name)

    @classmethod
    def tearDownClass(cls):
        cls.dossier.cleanup()

    def noms(self, langue):
        return sorted(f for f in os.listdir(os.path.join(self.dossier.name, "build", langue)))

    def test_memes_pages_dans_les_deux_langues(self):
        self.assertEqual(self.noms("en"), self.noms("fr"))
        self.assertGreaterEqual(self.n, 34)

    def test_une_page_par_programme_avec_l_aide_reelle(self):
        for programme in PROGRAMMES:
            for langue in ("en", "fr"):
                with self.subTest(programme=programme, langue=langue):
                    page = [f for f in self.noms(langue) if f.endswith(f"-{programme}.md")]
                    self.assertEqual(len(page), 1, programme)
                    texte = open(os.path.join(self.dossier.name, "build", langue, page[0]), encoding="utf-8").read()
                    self.assertNotIn("{{HELP}}", texte)
                    self.assertIn("--report-err", texte)                              # l'aide réelle du programme est dans la page
                    self.assertIn("--anonymize", texte)

    def test_langue_de_l_aide_inseree(self):
        fr = open(os.path.join(self.dossier.name, "build", "fr", "08-odoo-backup.md"), encoding="utf-8").read()
        en = open(os.path.join(self.dossier.name, "build", "en", "08-odoo-backup.md"), encoding="utf-8").read()
        self.assertIn("affiche le journal des modifications", fr)
        self.assertIn("show the change log", en)

    def test_module_de_pages_xml_valide_et_adresses(self):
        xml = open(os.path.join(self.dossier.name, "rlq_tools_docs", "data", "docs_pages.xml"), encoding="utf-8").read()
        self.assertIn('<field name="url">/docs/en/overview</field>', xml)
        self.assertIn('<field name="url">/docs/fr/odoo-chat-post</field>', xml)
        self.assertEqual(xml.count('model="website.page"'), self.n)

    def test_aucune_donnee_personnelle_dans_les_pages(self):
        for racine, _, fichiers in os.walk(self.dossier.name):
            for f in fichiers:
                chemin = os.path.join(racine, f)
                for i, ligne in enumerate(open(chemin, encoding="utf-8"), 1):
                    with self.subTest(fichier=f, ligne=i):
                        self.assertIsNone(donnee_personnelle(chemin, ligne), ligne[:120])

    def test_auteur_du_manifeste_exception_etroite(self):
        """run-all 1.192 : le nom légal passe dans la clé « author » d'un __manifest__.py, et nulle part ailleurs."""
        auteur = "    'author': 'Services-Conseils Linux Inc., Rencontres Linux au Québec contributors',\n"
        self.assertIsNone(donnee_personnelle("rlq_tools_docs/__manifest__.py", auteur))
        self.assertIsNone(donnee_personnelle("__manifest__.py", "{'author': 'Services-Conseils Linux Inc.',\n"))
        cas_refuses = (
            ("__manifest__.py", "    'author': 'Services-Conseils Linux Inc., Jean Exemple <jean.exemple@gmail.com>',\n"),  # courriel ajouté à l'auteur
            ("__manifest__.py", "    'author': 'services-conseils',\n"),                                       # pas le nom légal exact
            ("__manifest__.py", "    'summary': 'Services-Conseils Linux Inc. documentation',\n"),             # autre clé du manifeste
            ("__manifest__.py", "    'website': 'https://rencontres-linux.quebec',\n"),
            ("08-odoo-backup.md", "Auteur : Services-Conseils Linux Inc.\n"),                                 # page de documentation
            ("docs_pages.xml", "    'author': 'Services-Conseils Linux Inc.',\n"),                            # même ligne hors du manifeste
        )
        for fichier, ligne in cas_refuses:
            with self.subTest(fichier=fichier, ligne=ligne.strip()):
                self.assertIsNotNone(donnee_personnelle(fichier, ligne))


if __name__ == "__main__":
    unittest.main()
