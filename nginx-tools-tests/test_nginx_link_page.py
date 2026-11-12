#!/usr/bin/env python3
# ENVIRONNEMENT: tests de nginx-link-page.sh (plusieurs pages, moteur par page). Aucun acces reseau : git, curl, nginx et
# systemctl sont remplaces par de faux programmes. Les tests d'installation exigent root et sont ignores sinon.
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PROG = RACINE / "nginx-link-page.sh"
EXEMPLE = RACINE / "nginx-link-page.conf.example"
CHANGELOG = RACINE / "CHANGELOG.md"
SHA = "3c9162c9f8324d5e002259ed8b4b3cc377b08486"
VERSION = re.search(r'^readonly SCRIPT_VERSION="([^"]+)"', PROG.read_text(encoding="utf-8"), re.M).group(1)

MINIMAL = """SITE_TITLE=Test
SITE_LANGUAGE=fr
LINK_1_LABEL=Accueil
LINK_1_URL=https://example.org/
PAGE_1_PATH=/liens/
PAGE_1_DIR=/var/www/liens
"""

GIT_STUB = """#!/bin/sh
if [ "$1" = "clone" ]; then
    for last; do :; done
    mkdir -p "$last/css" "$last/fonts" "$last/images/icons"
    echo body > "$last/css/style.css"; echo x > "$last/css/reset.css"; echo ".button-faceb {}" > "$last/css/brands.css"
    echo f > "$last/fonts/f.woff2"
    echo i > "$last/images/icons/facebook.svg"; echo i > "$last/images/icons/generic-website.svg"
    echo i > "$last/images/icons/youtube.svg"; echo i > "$last/images/icons/generic-calendar.svg"
    echo i > "$last/images/icons/generic-blog.svg"
    exit 0
fi
if [ "$1" = "-C" ]; then echo "${RLQ_STUB_SHA:-SHA_REEL}"; exit 0; fi
exit 1
""".replace("SHA_REEL", SHA)

CURL_STUB = r"""#!/bin/sh
out=""
while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift ;; esac
    shift
done
printf '\211PNG\r\n\032\nxxxx' > "$out"
exit 0
"""

NGINX_STUB = """#!/bin/sh
if [ "$1" = "-t" ]; then
    if [ -n "$RLQ_NGINX_FAIL" ]; then echo "erreur de test" >&2; exit 1; fi
    echo "nginx: test ok" >&2; exit 0
fi
exit 0
"""

SYSTEMCTL_STUB = "#!/bin/sh\nexit 0\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-rlq-link-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.etc = self.tmp / "etc"
        self.etc.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def conf(self, texte, nom="cfg.conf"):
        chemin = self.tmp / nom
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def lancer(self, *args, env=None):
        e = {"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C",
             "NGINX_LINK_PAGE_ETC_DEFAULT": str(self.etc)}
        e.update(env or {})
        return subprocess.run(["bash", str(PROG), *args], capture_output=True, text=True, env=e, timeout=120)


class Configuration(Base):
    def test_modele_commente_refuse_et_guide(self):
        r = self.lancer("-c", str(self.conf(EXEMPLE.read_text(encoding="utf-8"))), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SITE_TITLE", r.stderr)

    def test_modele_decommente_valide(self):
        lignes = [re.sub(r"^#(?=[A-Z])", "", ligne) for ligne in EXEMPLE.read_text(encoding="utf-8").splitlines()]
        r = self.lancer("-c", str(self.conf("\n".join(lignes) + "\n")), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("valide", r.stdout)

    def test_sans_configuration_cree_le_modele_automatiquement(self):
        r = self.lancer("--check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        cree = self.etc / "nginx-link-page.conf"
        self.assertTrue(cree.exists())
        self.assertEqual(cree.read_text(encoding="utf-8"), EXEMPLE.read_text(encoding="utf-8"))
        self.assertIn("Rien n'a ete installe", r.stdout)

    def test_sans_configuration_et_sans_creation_pour_version_et_aide(self):
        self.assertEqual(self.lancer("--version").returncode, 0)
        self.assertEqual(self.lancer("--help").returncode, 0)
        self.assertFalse((self.etc / "nginx-link-page.conf").exists())

    def test_config_explicite_absente_n_est_pas_creee(self):
        r = self.lancer("-c", str(self.tmp / "absent.conf"), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.tmp / "absent.conf").exists())
        self.assertFalse((self.etc / "nginx-link-page.conf").exists())

    def test_init_cree_puis_refuse_l_ecrasement(self):
        cible = self.tmp / "sous" / "nginx-link-page.conf"
        r = self.lancer("--init", "-c", str(cible))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(cible.read_text(encoding="utf-8"), EXEMPLE.read_text(encoding="utf-8"))
        r = self.lancer("--init", "-c", str(cible))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("existe", r.stderr)

    def test_minimal_valide(self):
        r = self.lancer("-c", str(self.conf(MINIMAL)), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_http_refuse(self):
        r = self.lancer("-c", str(self.conf(MINIMAL.replace("https://example.org/", "http://example.org/"))), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("https", r.stderr)

    def test_trou_dans_les_liens(self):
        texte = MINIMAL + "LINK_3_LABEL=X\nLINK_3_URL=https://example.org/x\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pas de trou", r.stderr)

    def test_moteur_linkstack_refuse(self):
        texte = MINIMAL.replace("PAGE_1_PATH", "PAGE_1_ENGINE=linkstack\nPAGE_1_PATH")
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("linkstack", r.stderr)

    def test_moteur_inconnu_refuse(self):
        texte = MINIMAL.replace("PAGE_1_PATH", "PAGE_1_ENGINE=wordpress\nPAGE_1_PATH")
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("wordpress", r.stderr)

    def test_chemin_duplique_refuse(self):
        texte = MINIMAL + "PAGE_2_PATH=/liens/\nPAGE_2_DIR=/var/www/autre\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("deja utilise", r.stderr)

    def test_dossiers_imbriques_refuses(self):
        texte = MINIMAL + "PAGE_2_PATH=/liens2/\nPAGE_2_DIR=/var/www/liens/deux\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("imbrique", r.stderr)

    def test_deux_pages_distinctes_acceptees(self):
        texte = MINIMAL + "PAGE_2_PATH=/liens2/\nPAGE_2_DIR=/var/www/liens2\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PAGE_2", r.stdout)

    def test_theme_invalide_refuse(self):
        r = self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_THEME=rose\n")), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("THEME", r.stderr)

    def test_chemin_relatif_sans_base_refuse(self):
        r = self.lancer("-c", str(self.conf("SITE_TITLE=Test\nLINK_1_LABEL=A\nLINK_1_URL=/a/\n")), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("LINK_1_URL", r.stderr)

    def test_chemin_relatif_dangereux_refuse(self):
        for url in ("//evil.example/x", "javascript:alert(1)", "/a/../b", "http://x.example/"):
            with self.subTest(url=url):
                texte = f"SITE_TITLE=Test\nSITE_BASE_URL=https://www.example.org/\nLINK_1_LABEL=A\nLINK_1_URL={url}\n"
                r = self.lancer("-c", str(self.conf(texte)), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("LINK_1_URL", r.stderr)

    def test_base_invalide_refusee(self):
        texte = "SITE_TITLE=Test\nSITE_BASE_URL=http://www.example.org/\nLINK_1_LABEL=A\nLINK_1_URL=https://a.example/\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SITE_BASE_URL", r.stderr)

    def certificat(self, *noms):
        le = self.tmp / "le"
        for nom in noms:
            (le / nom).mkdir(parents=True, exist_ok=True)
            (le / nom / "fullchain.pem").write_text("x", encoding="utf-8")
        return {"NGINX_LINK_PAGE_LETSENCRYPT_DIR": str(le)}

    def test_base_prise_dans_le_certificat_unique(self):
        env = self.certificat("exemple.example.org")
        texte = "SITE_TITLE=T\nLINK_1_LABEL=A\nLINK_1_URL=/a/\nPAGE_1_PATH=/liens/\nPAGE_1_DIR=/var/www/liens\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("https://exemple.example.org/", r.stdout)
        self.assertIn("certificat", r.stdout)

    def test_base_refusee_si_plusieurs_certificats(self):
        env = self.certificat("exemple.example.org", "mail.example.org")
        r = self.lancer("-c", str(self.conf("SITE_TITLE=T\nLINK_1_LABEL=A\nLINK_1_URL=/a/\n")), "--check", env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("LINK_1_URL", r.stderr)

    def test_site_base_url_prioritaire_sur_le_certificat(self):
        env = self.certificat("exemple.example.org")
        texte = ("SITE_TITLE=T\nSITE_BASE_URL=https://autre.example.net/\nLINK_1_LABEL=A\nLINK_1_URL=/a/\n"
                 "PAGE_1_PATH=/liens/\nPAGE_1_DIR=/var/www/liens\n")
        r = self.lancer("-c", str(self.conf(texte)), "--check", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("https://autre.example.net/", r.stdout)
        self.assertNotIn("exemple.example.org", r.stdout)

    def test_langues_invalides_refusees(self):
        for valeur in ("de", "fr,fr", "fr,en,de"):
            with self.subTest(valeur=valeur):
                r = self.lancer("-c", str(self.conf(MINIMAL + f"PAGE_1_LANGUAGES={valeur}\n")), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("LANGUAGES", r.stderr)

    def test_variantes_invalides_refusees(self):
        for ligne, cle in (("PAGE_1_BUTTONS=rond\n", "BUTTONS"),
                           ("PAGE_1_AVATAR=round\n", "AVATAR"),
                           ("PAGE_1_ACCENT=rouge\n", "ACCENT"),
                           ("PAGE_1_ACCENT=#12345\n", "ACCENT"),
                           ("PAGE_1_SWITCH=peut-etre\n", "SWITCH")):
            with self.subTest(ligne=ligne):
                r = self.lancer("-c", str(self.conf(MINIMAL + ligne)), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(cle, r.stderr)

    def test_variantes_valides_acceptees(self):
        r = self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_BUTTONS=brand\nPAGE_1_AVATAR=soft\n"
                                            "PAGE_1_ACCENT=#1a2B3c\nPAGE_1_SWITCH=yes\n")), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_image_d_apercu_invalide_refusee(self):
        r = self.lancer("-c", str(self.conf(MINIMAL + "SITE_SHARE_IMAGE_URL=http://example.org/a.png\nSITE_BASE_URL=https://www.example.org/\n")), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SITE_SHARE_IMAGE_URL", r.stdout + r.stderr)

    def test_icone_http_refusee(self):
        r = self.lancer("-c", str(self.conf(MINIMAL + "LINK_1_ICON=http://example.org/i.svg\n")), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("https", r.stderr)

    def test_commentaire_fin_de_ligne(self):
        r = self.lancer("-c", str(self.conf(MINIMAL.replace("SITE_TITLE=Test", "SITE_TITLE=Test # commentaire"))), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Site : Test ·", r.stdout)

    def test_config_explicite_lit_seulement_son_fichier(self):
        (self.etc / "nginx-link-page.conf").write_text("SITE_TITLE=Etc\n", encoding="utf-8")
        r = self.lancer("-c", str(self.conf(MINIMAL)), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(str(self.etc), r.stdout)

    def test_chaine_etc_puis_home(self):
        (self.etc / "nginx-link-page.conf").write_text(MINIMAL, encoding="utf-8")
        (self.home / ".nginx-link-page.conf").write_text("SITE_TITLE=Maison\n", encoding="utf-8")
        r = self.lancer("--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(self.etc / "nginx-link-page.conf"), r.stdout)
        self.assertIn(str(self.home / ".nginx-link-page.conf"), r.stdout)
        self.assertIn("Site : Maison", r.stdout)

    def test_version_dynamique(self):
        r = self.lancer("--version")
        self.assertEqual(r.stdout.strip(), f"nginx-link-page.sh version {VERSION}")

    def test_options_aide_triees(self):
        r = self.lancer("--help")
        cles = []
        for ligne in r.stdout.splitlines():
            if ligne.startswith("  -"):
                longues = re.findall(r"--[a-z]+", ligne)
                cles.append(longues[0] if longues else ligne.split()[0])
        self.assertTrue(cles)
        self.assertEqual(cles, sorted(cles))

    def test_changelog_sans_ansi_quand_redirige(self):
        r = self.lancer("--changelog")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("\x1b[", r.stdout)
        self.assertIn(VERSION, r.stdout)

    def test_depot_sans_donnees_de_groupe(self):
        # Motifs assembles par concatenation pour que ce fichier ne se trouve pas lui-meme.
        motifs = ["1374185" + "03088952", "1085" + "32398", "811" + "7971", "linuxmeetup" + "-mtl",
                  "rencontres-linux" + ".quebec/event", "rencontres-linux" + ".quebec/blog", "Rencontres-Linux" + ".Quebec"]
        textes = [PROG.read_text(encoding="utf-8"), EXEMPLE.read_text(encoding="utf-8")]
        section = []
        dans = False
        for ligne in CHANGELOG.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("## "):
                dans = ligne == "## nginx-link-page.sh"
            if dans:
                section.append(ligne)
        textes.append("\n".join(section))
        for texte in textes:
            for motif in motifs:
                self.assertIsNone(re.search(re.escape(motif), texte, re.I), f"donnee de groupe : {motif}")


class Installation(Base):
    def setUp(self):
        super().setUp()
        if os.geteuid() != 0:
            self.skipTest("installation : root requis")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for nom, corps in (("git", GIT_STUB), ("curl", CURL_STUB), ("nginx", NGINX_STUB), ("systemctl", SYSTEMCTL_STUB)):
            chemin = self.bin / nom
            chemin.write_text(corps, encoding="utf-8")
            chemin.chmod(0o755)
        self.www = self.tmp / "www"
        self.snippets = self.tmp / "snippets"
        self.snippets.mkdir()
        self.env = {"PATH": f"{self.bin}:{os.environ['PATH']}",
                    "NGINX_LINK_PAGE_SNIPPETS_DIR": str(self.snippets)}

    def config_deux_pages(self, page2_active="yes"):
        return f"""SITE_TITLE=Test & B
SITE_LANGUAGE=fr
SITE_LOGO_URL=https://example.org/logo.png
LINK_1_LABEL=Lien <A>
LINK_1_URL=https://example.org/a
LINK_1_ICON=builtin:facebook
LINK_2_LABEL=Autre
LINK_2_URL=https://example.org/b
LINK_2_ICON=https://example.org/i.png
LINK_2_ICON_DARK=https://example.org/d.png
PAGE_1_PATH=/liens/
PAGE_1_DIR={self.www}/liens
PAGE_1_THEME=auto
PAGE_2_ENABLED={page2_active}
PAGE_2_PATH=/liens2/
PAGE_2_DIR={self.www}/liens2
PAGE_2_THEME=dark
PAGE_2_TITLE=Deux
"""

    def test_installation_deux_pages(self):
        conf = self.conf(self.config_deux_pages())
        r = self.lancer("-c", str(conf), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nginx -t", r.stdout)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        deux = (self.www / "liens2" / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>Test &amp; B</title>", ici)
        self.assertIn("Lien &lt;A&gt;", ici)
        self.assertIn("<picture>", ici)
        self.assertNotIn("<script", ici)
        self.assertIn("<title>Deux</title>", deux)
        self.assertIn('class="theme-dark"', deux)
        self.assertTrue((self.www / "liens" / "css" / "style.css").exists())
        snippet = (self.snippets / "liens-publics.conf").read_text(encoding="utf-8")
        self.assertIn("location ^~ /liens/ {", snippet)
        self.assertIn("location ^~ /liens2/ {", snippet)
        self.assertIn("location = /liens {", snippet)
        self.assertIn("return 301 /liens/;", snippet)
        self.assertIn("location = /liens2 {", snippet)
        self.assertIn(f"alias {self.www}/liens/;", snippet)

    def test_variantes_marque_avatar_accent_bascule(self):
        texte = self.config_deux_pages("no").replace(
            "PAGE_1_THEME=auto",
            "PAGE_1_THEME=light\nPAGE_1_BUTTONS=brand\nPAGE_1_AVATAR=rounded\n"
            "PAGE_1_ACCENT=#FF0000\nPAGE_1_SWITCH=yes")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        autre = (self.www / "liens" / "autre.html").read_text(encoding="utf-8")
        self.assertIn('class="button button-faceb"', ici)
        self.assertIn('class="button button-default"', ici)
        self.assertIn("avatar--rounded", ici)
        self.assertIn('href="css/accent.css"', ici)
        self.assertIn('href="autre.html"', ici)
        self.assertIn("Passer au thème sombre", ici)
        self.assertIn('class="theme-dark"', autre)
        self.assertIn('href="index.html"', autre)
        self.assertIn("Passer au thème clair", autre)
        self.assertNotIn("<script", autre)
        accent = (self.www / "liens" / "css" / "accent.css").read_text(encoding="utf-8")
        self.assertIn("--button-background: #FF0000;", accent)

    def test_chemins_relatifs_resolus(self):
        texte = self.config_deux_pages("no").replace(
            "LINK_1_URL=https://example.org/a", "LINK_1_URL=/a/").replace(
            "LINK_2_ICON=https://example.org/i.png", "LINK_2_ICON=/images/i.png").replace(
            "SITE_LOGO_URL=https://example.org/logo.png", "SITE_LOGO_URL=/logo.png").replace(
            "SITE_TITLE=Test & B\n", "SITE_TITLE=Test & B\nSITE_BASE_URL=https://www.example.org/\n")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://www.example.org/a/"', ici)
        self.assertNotIn('href="/a/"', ici)

    def test_apercu_reseaux_sociaux_image_et_textes(self):
        """1.10: Open Graph and Twitter card; absolute addresses built from SITE_BASE_URL and the page path."""
        texte = self.config_deux_pages("no").replace(
            "SITE_TITLE=Test & B\n", "SITE_TITLE=Test & B\nSITE_BASE_URL=https://www.example.org/\nSITE_DESCRIPTION=Desc\n"
            "SITE_SHARE_IMAGE_URL=/images/apercu.png\nSITE_SHARE_TITLE=Nos \"liens\"\nSITE_SHARE_DESCRIPTION=Tous les liens\n"
            "SITE_SHARE_TITLE_EN=Our links\nPAGE_1_LANGUAGES=fr,en\n")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        en = (self.www / "liens" / "en" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta property="og:type" content="website">', ici)
        self.assertIn('<meta property="og:url" content="https://www.example.org/liens/">', ici)
        self.assertIn('<meta property="og:title" content="Nos &quot;liens&quot;">', ici)
        self.assertIn('<meta property="og:description" content="Tous les liens">', ici)
        self.assertIn('<meta property="og:image" content="https://www.example.org/liens/images/site/share.png">', ici)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', ici)
        self.assertIn('<meta name="twitter:image" content="https://www.example.org/liens/images/site/share.png">', ici)
        self.assertTrue((self.www / "liens" / "images" / "site" / "share.png").exists())
        self.assertIn("<title>Test &amp; B</title>", ici)          # the page title is unchanged
        self.assertIn('<meta property="og:url" content="https://www.example.org/liens/en/">', en)
        self.assertIn('<meta property="og:title" content="Our links">', en)
        self.assertIn('<meta property="og:description" content="Tous les liens">', en)      # no English text: the French one
        self.assertIn('content="https://www.example.org/liens/en/images/site/share.png"', en)

    def test_apercu_sans_image_logo_puis_rien(self):
        """1.10: without SITE_SHARE_IMAGE_URL the logo is used (small card); without a public base, no og:url nor og:image."""
        avec_base = self.config_deux_pages("no").replace("SITE_TITLE=Test & B\n", "SITE_TITLE=Test & B\nSITE_BASE_URL=https://www.example.org/\n")
        r = self.lancer("-c", str(self.conf(avec_base)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta property="og:image" content="https://www.example.org/liens/images/site/logo.png">', ici)
        self.assertIn('<meta name="twitter:card" content="summary">', ici)
        self.assertIn('<meta property="og:title" content="Test &amp; B">', ici)
        vide = self.tmp / "aucun-certificat"
        vide.mkdir()                                              # no certificate: no base can be guessed on the test machine
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no"))), "--update", "--yes",
                        env={**self.env, "NGINX_LINK_PAGE_LETSENCRYPT_DIR": str(vide)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<meta property="og:title"', ici)
        self.assertNotIn("og:image", ici)
        self.assertNotIn("og:url", ici)

    def test_deux_langues_detection_et_textes(self):
        texte = self.config_deux_pages("no").replace(
            "PAGE_1_THEME=auto", "PAGE_1_THEME=auto\nPAGE_1_LANGUAGES=fr,en").replace(
            "LINK_1_ICON=builtin:facebook\n", "LINK_1_ICON=builtin:facebook\nLINK_1_LABEL_EN=Link EN\n").replace(
            "SITE_TITLE=Test & B\n", "SITE_TITLE=Test & B\nSITE_TITLE_EN=Test EN\nSITE_HEADING_EN=Home EN\n")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fr = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        en = (self.www / "liens" / "en" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="fr"', fr)
        self.assertIn('lang="en"', en)
        self.assertIn("Lien &lt;A&gt;", fr)
        self.assertIn("Link EN", en)
        self.assertIn("<title>Test EN</title>", en)
        self.assertIn("<h1>Home EN</h1>", en)
        self.assertIn('href="/liens/en/"', fr)
        self.assertIn('href="/liens/"', en)
        self.assertTrue((self.www / "liens" / "en" / "css" / "style.css").exists())
        snippet = (self.snippets / "liens-publics.conf").read_text(encoding="utf-8")
        self.assertIn("location = /liens/ {", snippet)
        self.assertIn('if ($http_accept_language ~* "^en") {', snippet)
        self.assertIn("return 302 /liens/en/;", snippet)
        self.assertIn('add_header Vary "Accept-Language" always;', snippet)

    def test_page_desactivee_absente(self):
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no"))), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.www / "liens" / "index.html").exists())
        self.assertFalse((self.www / "liens2").exists())
        snippet = (self.snippets / "liens-publics.conf").read_text(encoding="utf-8")
        self.assertNotIn("/liens2/", snippet)

    def test_commit_inattendu_refuse(self):
        r = self.lancer("-c", str(self.conf(self.config_deux_pages())), "--update", "--yes",
                        env=dict(self.env, RLQ_STUB_SHA="0000000000000000000000000000000000000000"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("commit", r.stderr)
        self.assertFalse((self.www / "liens").exists())

    def test_nginx_t_echec_restaure_l_ancien_fragment(self):
        conf = self.conf(self.config_deux_pages())
        r = self.lancer("-c", str(conf), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ancien = (self.snippets / "liens-publics.conf").read_text(encoding="utf-8")
        conf2 = self.conf(self.config_deux_pages("no"), nom="cfg2.conf")
        r = self.lancer("-c", str(conf2), "--update", "--yes", env=dict(self.env, RLQ_NGINX_FAIL="1"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NON recharge", r.stderr)
        self.assertEqual((self.snippets / "liens-publics.conf").read_text(encoding="utf-8"), ancien)

    def test_update_refuse_sans_root_ou_confirmation(self):
        if os.geteuid() == 0:
            r = self.lancer("-c", str(self.conf(MINIMAL)), "--update", env=self.env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("--yes", r.stderr)


class HardeningPropose(unittest.TestCase):
    """nginx-hardening.sh asks before creating or updating the link page; nothing runs without the answer."""

    def setUp(self):
        self.texte = (RACINE / "nginx-hardening.sh").read_text(encoding="utf-8")

    def test_etape_0e_bis_presente(self):
        # 2.101: the step sits between 0e and 0f, so it is numbered "0e bis" (it was "12 ter", out of sequence)
        self.assertIn("--- 0e bis) Page de liens", self.texte)
        self.assertNotIn("12 ter)", self.texte)
        self.assertEqual(self.texte.count("# --- 12c)"), 1)

    def test_etape_avant_0f(self):
        # The link page is installed before the generic nginx configuration (step 0f), so that step 0f sees it.
        self.assertLess(self.texte.index("--- 0e bis) Page de liens"), self.texte.index('echo "--- 0f)'))

    def test_verification_avant_installation(self):
        verification = self.texte.index('"$LIENS_SCRIPT" --check >/dev/null')
        appel = self.texte.index('"$LIENS_SCRIPT" --update --yes')
        self.assertLess(verification, appel)

    def test_question_avant_creation(self):
        creation = self.texte.index("Créer une page de liens (LittleLink, /links/) maintenant")
        appel_creation = self.texte.index('"$LIENS_SCRIPT" --check || true')
        self.assertLess(creation, appel_creation)

    def test_sans_terminal_rien_n_est_lance(self):
        self.assertIn('if [[ -t 0 && -t 2 ]]; then', self.texte)


if __name__ == "__main__":
    unittest.main()
