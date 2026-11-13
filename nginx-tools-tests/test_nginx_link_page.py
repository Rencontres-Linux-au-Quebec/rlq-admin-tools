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
SHA_EXT = "d7034f83a6bf71c4a663d2d046a03b37ec74ae45"
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
    case "$last" in
        *littlelink-extended)
            [ -n "$RLQ_STUB_NO_EXT" ] && exit 128
            mkdir -p "$last/css" "$last/images/icons-extended" "$last/js"
            echo ".button-codeberg {}" > "$last/css/brands-extended.css"; echo "alert(1)" > "$last/js/sensitive-content.js"
            echo i > "$last/images/icons-extended/codeberg.svg"; echo i > "$last/images/icons-extended/lemmy.svg"
            exit 0 ;;
    esac
    mkdir -p "$last/css" "$last/fonts" "$last/images/icons"
    echo body > "$last/css/style.css"; echo x > "$last/css/reset.css"; echo ".button-faceb {}" > "$last/css/brands.css"
    echo f > "$last/fonts/f.woff2"
    echo i > "$last/images/icons/facebook.svg"; echo i > "$last/images/icons/generic-website.svg"
    echo i > "$last/images/icons/youtube.svg"; echo i > "$last/images/icons/generic-calendar.svg"
    echo i > "$last/images/icons/generic-blog.svg"
    exit 0
fi
if [ "$1" = "-C" ]; then
    case "$2" in
        *littlelink-extended) echo "${RLQ_STUB_SHA_EXT:-SHA_DE_EXTENDED}" ;;
        *) echo "${RLQ_STUB_SHA:-SHA_REEL}" ;;
    esac
    exit 0
fi
exit 1
""".replace("SHA_REEL", SHA).replace("SHA_DE_EXTENDED", SHA_EXT)

CURL_STUB = r"""#!/bin/sh
out=""; fmt=""; url=""
while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift ;; -w) fmt="$2"; shift ;; -A|-r|--max-time) shift ;; -*) ;; *) url="$1" ;; esac
    shift
done
if [ "$fmt" = "%{http_code}" ]; then
    # 1.28: --check-links; RLQ_CURL_CODES="URL=CODE URL=CODE" (200 by default)
    code=200
    for paire in $RLQ_CURL_CODES; do [ "${paire%=*}" = "$url" ] && code="${paire##*=}"; done
    printf '%s' "$code"
    exit 0
fi
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

    def seul_script_local(self, html):
        """1.18 : la seule balise script permise est js/link-page.js, servi par la page elle-même."""
        self.assertEqual(re.findall(r"<script[^>]*>", html), ['<script src="js/link-page.js">'])

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
        self.seul_script_local(ici)
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

    def test_littlelink_extended_icones_et_boutons(self):
        """1.11: builtin:NAME is looked for in LittleLink, then in LittleLink Extended (icons-extended, brands-extended.css); no script copied."""
        texte = self.config_deux_pages("no").replace("LINK_2_ICON=https://example.org/i.png", "LINK_2_ICON=builtin:codeberg").replace(
            "PAGE_1_THEME=auto\n", "PAGE_1_THEME=auto\nPAGE_1_BUTTONS=brand\n")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LittleLink Extended v3.2.0", r.stdout)
        ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="images/icons-extended/codeberg.svg"', ici)
        self.assertIn('href="css/brands-extended.css"', ici)
        self.assertIn("button-codeberg", ici)
        self.assertIn('src="images/icons/facebook.svg"', ici)                  # LittleLink first
        self.assertTrue((self.www / "liens" / "images" / "icons-extended" / "lemmy.svg").exists())
        self.assertEqual([f.name for f in (self.www / "liens").rglob("*.js")], ["link-page.js"])   # 1.18: never sensitive-content.js
        self.seul_script_local(ici)

    def test_littlelink_extended_absent_ou_autre_commit(self):
        """1.11: Extended not reachable or another commit: [ATTN] and pages built without it; an Extended icon then stops the build."""
        conf = self.conf(self.config_deux_pages("no"))
        for env in ({"RLQ_STUB_NO_EXT": "1"}, {"RLQ_STUB_SHA_EXT": "0" * 40}):
            with self.subTest(env=env):
                r = self.lancer("-c", str(conf), "--update", "--yes", env={**self.env, **env})
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("[ATTN]", r.stdout)
                ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
                self.assertNotIn("brands-extended.css", ici)
        texte = self.config_deux_pages("no").replace("LINK_2_ICON=https://example.org/i.png", "LINK_2_ICON=builtin:codeberg")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env={**self.env, "RLQ_STUB_NO_EXT": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("codeberg", r.stdout + r.stderr)

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
        self.seul_script_local(autre)
        accent = (self.www / "liens" / "css" / "accent.css").read_text(encoding="utf-8")
        self.assertIn("--button-background: #FF0000;", accent)

    def test_113_chemin_insensible_a_la_casse(self):
        """1.13 : /LIENS, /Liens/, /LIENS/en/ redirigés vers /liens... (301, query string gardée) ; deux pages qui ne diffèrent que par la casse : refusé."""
        r = self.lancer("-c", str(self.conf(self.config_deux_pages())), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        snippet = (self.snippets / "liens-publics.conf").read_text(encoding="utf-8")
        self.assertIn("location ~* ^/liens(/.*)?$ {\n    return 301 /liens$1$is_args$args;\n}", snippet)
        self.assertIn("location ~* ^/liens2(/.*)?$ {", snippet)
        self.assertLess(snippet.index("location ~* ^/liens(/.*)?$"), snippet.index("location = /liens {"))
        import re as _re
        motif = _re.compile(r"^/liens(/.*)?$", _re.I)                              # what nginx does with ~*
        for demande, attendu in (("/LIENS", "/liens"), ("/Liens/", "/liens/"), ("/LIENS/en/", "/liens/en/")):
            with self.subTest(demande=demande):
                m = motif.match(demande)
                self.assertIsNotNone(m)
                self.assertEqual("/liens" + (m.group(1) or ""), attendu)
        self.assertIsNone(motif.match("/liens2/"))
        texte = self.config_deux_pages().replace("PAGE_2_PATH=/liens2/", "PAGE_2_PATH=/LIENS/")
        r = self.lancer("-c", str(self.conf(texte)), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PAGE_2_PATH=/LIENS/ deja utilise", r.stderr)

    def test_113_lien_vers_la_racine_du_site(self):
        """1.13 : LINK_n_URL=/ (racine du site) est accepté et résolu avec SITE_BASE_URL ; « // » reste refusé."""
        texte = self.config_deux_pages("no").replace("LINK_1_URL=https://example.org/a", "LINK_1_URL=/").replace(
            "SITE_TITLE=Test & B\n", "SITE_TITLE=Test & B\nSITE_BASE_URL=https://www.example.org/\n")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('href="https://www.example.org/"', (self.www / "liens" / "index.html").read_text(encoding="utf-8"))
        r = self.lancer("-c", str(self.conf(texte.replace("LINK_1_URL=/\n", "LINK_1_URL=//\n"))), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("LINK_1_URL", r.stderr)

    def test_114_image_d_apercu_de_plus_de_512_kio_et_raison_de_l_echec(self):
        """1.14 : l'image d'aperçu a sa limite (5 Mo, celle de LinkedIn) au lieu de 512 Kio ; un échec dit pourquoi (trop gros, code HTTP, pas une image)."""
        journal = self.tmp / "curl.log"
        (self.bin / "curl").write_text(f"""#!/bin/sh
echo "$@" >> {journal}
out=""; max=""; url=""
while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift ;; --max-filesize) max="$2"; shift ;; https://*) url="$1" ;; esac
    shift
done
case "$url" in
    *grosse*) [ "$max" -lt 2000000 ] && exit 63; printf '\\211PNG\\r\\n\\032\\nxxxx' > "$out"; printf '200 1500000'; exit 0 ;;
    *absente*) printf '404 0'; exit 22 ;;
    *texte*) echo "bonjour" > "$out"; printf '200 8'; exit 0 ;;
esac
printf '\\211PNG\\r\\n\\032\\nxxxx' > "$out"; printf '200 12'; exit 0
""", encoding="utf-8")
        base = self.config_deux_pages("no").replace("SITE_TITLE=Test & B\n", "SITE_TITLE=Test & B\nSITE_BASE_URL=https://www.example.org/\n")
        r = self.lancer("-c", str(self.conf(base + "SITE_SHARE_IMAGE_URL=https://example.org/grosse.png\n")), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--max-filesize 5242880", journal.read_text())
        self.assertIn("--max-filesize 524288 ", journal.read_text())                     # logo and icons keep 512 KiB
        for url, raison in (("absente.png", "le serveur repond HTTP 404"), ("texte.png", "ce n'est pas une image")):
            with self.subTest(url=url):
                r = self.lancer("-c", str(self.conf(base + f"SITE_SHARE_IMAGE_URL=https://example.org/{url}\n")), "--update", "--yes", env=self.env)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(raison, r.stdout + r.stderr)
        (self.bin / "curl").write_text("#!/bin/sh\nexit 63\n", encoding="utf-8")
        r = self.lancer("-c", str(self.conf(base)), "--update", "--yes", env=self.env)
        self.assertIn("fichier trop gros (plus de 512 Kio)", r.stdout + r.stderr)

    def test_115_cinq_themes_ajoutes(self):
        """1.15 : aurora, maple, river, terminal, tux : classe du thème, css/themes.css copié et lié, couleur de la barre du navigateur ;
        icône sombre pour les thèmes à base sombre ; seconde page (PAGE_n_SWITCH) dans le thème de base opposé ; thème inconnu refusé."""
        bases = {"aurora": "dark", "maple": "light", "river": "light", "terminal": "dark", "tux": "dark",
                 "tux-quebec": "light", "quebec": "dark", "boreal": "dark", "sunset": "dark", "winter": "light", "tux-flag": "light", "tux-poster": "light"}      # 1.21: 5 more, 1.22: tux-flag, 1.23: tux-poster
        for theme, base in bases.items():
            with self.subTest(theme=theme):
                texte = self.config_deux_pages("no").replace("PAGE_1_THEME=auto", f"PAGE_1_THEME={theme}\nPAGE_1_SWITCH=yes")
                r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
                self.assertIn(f'class="theme-{theme}"', ici)
                self.assertIn('<link rel="stylesheet" href="css/themes.css">', ici)
                self.assertLess(ici.index("css/brands.css"), ici.index("css/themes.css"))       # after LittleLink: it wins
                self.assertRegex(ici, r'<meta name="theme-color" content="#[0-9a-f]{6}">')
                self.assertTrue((self.www / "liens" / "css" / "themes.css").exists())
                (self.assertIn if base == "dark" else self.assertNotIn)("images/site/icon-2-sombre.", ici)     # dark icon on a dark base
                autre = (self.www / "liens" / "autre.html").read_text(encoding="utf-8")
                self.assertIn('class="theme-light"' if base == "dark" else 'class="theme-dark"', autre)
                self.assertNotIn("css/themes.css", autre)
                self.seul_script_local(ici)
        css = (self.www / "liens" / "css" / "themes.css").read_text(encoding="utf-8")
        for theme in bases:
            self.assertIn(f":root.theme-{theme} body", css)
        self.assertNotRegex(css, r"@import|https?:")                                     # nothing outside the page (CSP 'self')
        self.assertEqual(re.findall(r"url\(([^)]*)\)", css), ['"../images/themes/tux-quebec.jpg"', '"../images/themes/tux-flag.jpg"', '"../images/themes/tux-poster.jpg"'])   # local images only
        propres = css[css.index("/* ---- aurora: northern lights"):]                   # 1.23: after the common block, one theme per rule
        for ligne in propres.splitlines():
            if ligne.startswith(":root.theme-"):
                self.assertEqual(len(set(re.findall(r":root\.theme-([a-z-]+)", ligne))), 1, ligne)
        for image in ("tux-quebec.jpg", "tux-flag.jpg", "tux-poster.jpg"):
            self.assertTrue((self.www / "liens" / "images" / "themes" / image).exists())
        r = self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_THEME=rose\n")), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("aurora, maple, river, terminal, tux, tux-quebec, quebec, boreal, sunset, winter, tux-flag, tux-poster, ls-aurora", r.stderr)

    def test_116_quatre_themes_linkstack(self):
        """1.16 : ls-aurora, ls-dark, ls-dawn, ls-misty-rain : css/themes-linkstack.css (pas css/themes.css), images, polices et avis de licence
        copiés ; pluie de Misty Rain en CSS (éléments décoratifs, aucun script) ; base sombre ; seconde page claire."""
        for theme in ("ls-aurora", "ls-dark", "ls-dawn", "ls-misty-rain"):
            with self.subTest(theme=theme):
                texte = self.config_deux_pages("no").replace("PAGE_1_THEME=auto", f"PAGE_1_THEME={theme}\nPAGE_1_SWITCH=yes")
                r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                ici = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
                self.assertIn(f'class="theme-{theme}"', ici)
                self.assertIn('<link rel="stylesheet" href="css/themes-linkstack.css">', ici)
                self.assertNotIn('href="css/themes.css"', ici)
                self.assertIn("images/site/icon-2-sombre.", ici)
                self.seul_script_local(ici)
                self.assertEqual(ici.count('<div class="ls-rain" aria-hidden="true">'), 1 if theme == "ls-misty-rain" else 0)
                self.assertIn('class="theme-light"', (self.www / "liens" / "autre.html").read_text(encoding="utf-8"))
        page = self.www / "liens"
        for f in ("images/themes/ls-aurora.jpg", "images/themes/ls-dark-wallpaper.png", "images/themes/ls-dawn-background.jpg",
                  "fonts/themes/roboto-latin-400-normal.woff2", "fonts/themes/karla-latin-700-normal.woff2", "css/themes-linkstack-LICENSES.md"):
            self.assertTrue((page / f).exists(), f)
        css = (page / "css" / "themes-linkstack.css").read_text(encoding="utf-8")
        for url in __import__("re").findall(r'url\("([^"]+)"\)', css):          # every url() points to a file of the page
            self.assertTrue(url.startswith("../") and (page / "css" / url).resolve().exists(), url)
        self.assertNotRegex(__import__("re").sub(r"/\*.*?\*/", "", css, flags=__import__("re").S), r"@import|https?:")    # comments aside
        self.assertIn("MIT", (page / "css" / "themes-linkstack-LICENSES.md").read_text(encoding="utf-8"))

    def test_117_bouton_theme(self):
        """1.17 : PAGE_n_THEMES : une page complète par thème (index.html pour le thème de la page, theme-NOM.html pour les autres), menu
        <details> sans script dans chacune, thème courant marqué ; « all » : les 12 thèmes ; PAGE_n_SWITCH ignoré ; thème inconnu refusé ;
        les pages theme-*.html d'un passage précédent disparaissent."""
        texte = self.config_deux_pages("no").replace("PAGE_1_THEME=auto", "PAGE_1_THEME=aurora\nPAGE_1_THEMES=light, ls-dawn,aurora,terminal\nPAGE_1_SWITCH=yes")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PAGE_1_SWITCH=yes ignore", r.stdout + r.stderr)
        page = self.www / "liens"
        self.assertEqual(sorted(f.name for f in page.glob("*.html")), ["index.html", "theme-light.html", "theme-ls-dawn.html", "theme-terminal.html"])
        self.assertTrue((page / "css" / "theme-menu.css").exists())
        attendus = {"index.html": "aurora", "theme-light.html": "light", "theme-ls-dawn.html": "ls-dawn", "theme-terminal.html": "terminal"}
        for f, theme in attendus.items():
            with self.subTest(page=f):
                html = (page / f).read_text(encoding="utf-8")
                self.assertIn(f'class="theme-{theme}"', html)
                self.assertIn('<link rel="stylesheet" href="css/theme-menu.css">', html)
                self.assertIn('<details class="theme-menu">', html)
                self.assertIn("<summary>Thème</summary>", html)
                self.seul_script_local(html)
                self.assertEqual(html.count('aria-current="page"'), 1)
                self.assertIn(f'<li><a href="{f}" data-theme="{theme}" aria-current="page">', html)
                menu = html[html.index("<ul>"):html.index("</ul>")]
                self.assertEqual(__import__("re").findall(r'href="([^"]+)"', menu), ["index.html", "theme-light.html", "theme-ls-dawn.html", "theme-terminal.html"])
                self.assertNotIn("autre.html", html)
        self.assertIn(">aurore boréale</a>", (page / "index.html").read_text(encoding="utf-8"))
        texte = self.config_deux_pages("no").replace("PAGE_1_THEME=auto", "PAGE_1_THEME=dark\nPAGE_1_THEMES=all")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(list(page.glob("*.html"))), 19)                             # 1.23: 19 themes
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no"))), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([f.name for f in page.glob("*.html")], ["index.html"])           # old theme pages removed
        self.assertNotIn('<details class="theme-menu">', (page / "index.html").read_text(encoding="utf-8"))
        for valeur in ("all", "light,dark"):                                              # 1.20: THEME given a list: hint towards THEMES
            r = self.lancer("-c", str(self.conf(MINIMAL + f"PAGE_1_THEME={valeur}\n")), "--check")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(f"PAGE_1_THEMES={valeur} (avec un S)", r.stderr)
        r = self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_THEMES=light,rose\n")), "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("« rose »", r.stderr)

    def test_118_script_theme_langue_partage(self):
        """1.18 : js/link-page.js (CSP script-src 'self') : thème changé sur place et retenu, langue retenue, bouton Partager ;
        PAGE_n_SCRIPT=no : aucun script (script-src 'none') ; sans rien à faire (une langue, pas de menu, SHARE=no) : aucun script."""
        def bloc(snippet, chemin):
            return snippet[snippet.index("location ^~ " + chemin + " {"):].split("\n}\n", 1)[0]
        page = self.www / "liens"
        texte = self.config_deux_pages("no").replace("PAGE_1_THEME=auto", "PAGE_1_THEME=aurora\nPAGE_1_THEMES=light,ls-misty-rain\nPAGE_1_LANGUAGES=fr,en")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((page / "js" / "link-page.js").exists())
        self.assertTrue((page / "en" / "js" / "link-page.js").exists())
        fr = (page / "index.html").read_text(encoding="utf-8")
        en = (page / "en" / "index.html").read_text(encoding="utf-8")
        self.seul_script_local(fr)
        self.assertLess(fr.index('<script src="js/link-page.js">'), fr.index("</head>"))
        self.assertIn("script-src 'self'", fr)
        self.assertIn('data-page="/liens/"', fr)
        self.assertIn('data-themes="aurora|dark|#0b1026 light|light| ls-misty-rain|dark|#181b24"', fr)
        self.assertIn('data-other-lang="en" data-other-href="/liens/en/"', fr)
        self.assertIn('data-other-lang="fr" data-other-href="/liens/index.html"', en)
        self.assertIn('href="/liens/en/" data-lang="en"', fr)
        self.assertIn('href="/liens/index.html" data-lang="fr"', en)
        self.assertIn('<a href="theme-light.html" data-theme="light">', fr)
        self.assertIn('<link rel="stylesheet" href="css/themes.css">', fr)
        self.assertIn('<link rel="stylesheet" href="css/themes-linkstack.css">', fr)   # every offered theme can be applied in place
        self.assertIn('class="ls-rain"', fr)                                           # shown by CSS only with ls-misty-rain
        self.assertIn('<source data-icon-dark media="all"', fr)                        # dark base of aurora
        self.assertIn('<source data-icon-dark media="not all"', (page / "theme-light.html").read_text(encoding="utf-8"))
        self.assertIn('class="share-button" type="button" hidden', fr)
        self.assertIn('data-done="Lien copié">Partager</button>', fr)
        self.assertIn('data-done="Link copied">Share</button>', en)
        snippet = (self.snippets / "liens-publics.conf").read_text(encoding="utf-8")
        self.assertIn("script-src 'self'", bloc(snippet, "/liens/"))
        self.assertNotIn("script-src 'none'", snippet)
        # PAGE_n_SCRIPT=no: no script at all, even with the menu and two languages
        r = self.lancer("-c", str(self.conf(texte + "PAGE_1_SCRIPT=no\n")), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fr = (page / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", fr)
        self.assertNotIn("data-themes", fr)
        self.assertNotIn("share-button", fr)
        self.assertIn("script-src 'none'", fr)
        self.assertFalse((page / "js").exists())
        self.assertIn('<details class="theme-menu">', fr)                          # fallback: one page per theme
        self.assertIn("script-src 'none'", bloc((self.snippets / "liens-publics.conf").read_text(encoding="utf-8"), "/liens/"))
        # nothing for the script to do: one language, no menu, PAGE_n_SHARE=no
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no") + "PAGE_1_SHARE=no\n")), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fr = (page / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", fr)
        self.assertNotIn("theme-menu.css", fr)
        self.assertIn("script-src 'none'", fr)
        for cle in ("PAGE_1_SCRIPT=maybe", "PAGE_1_SHARE=oui"):
            with self.subTest(cle=cle):
                r = self.lancer("-c", str(self.conf(MINIMAL + cle + "\n")), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(cle, r.stderr)

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

    def test_124_cle_inconnue_et_ligne_invalide_signalees(self):
        """1.24 : une clé mal écrite ou inconnue, ou une ligne sans CLÉ=VALEUR, est refusée avec le fichier et la ligne ; la clé connue la plus
        proche est proposée (PAGE_3_THEMS -> PAGE_3_THEMES) ; rien n'est installé ; le modèle décommenté reste valide."""
        cas = {"PAGE_1_THEMS=all": "PAGE_1_THEMS (clé inconnue, ", "SITE_LANGAUGE=en": "vouliez-vous dire SITE_LANGUAGE ?",
               "LINK_1_URL_EN=x": "vouliez-vous dire LINK_1_URL ?", "BLABLA": "BLABLA : ligne ignorée, pas de forme CLE=VALEUR",
               "page-1-theme=dark": "page-1-theme=dark : ligne ignorée"}
        for ligne, attendu in cas.items():
            with self.subTest(ligne=ligne):
                conf = self.conf(MINIMAL + ligne + "\n")
                r = self.lancer("-c", str(conf), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(attendu, r.stderr)
                self.assertIn(f"{conf}:7", r.stderr)                                       # file and line
        self.assertIn("vouliez-vous dire PAGE_1_THEMES ?", self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_THEMS=all\n")), "--check").stderr)
        r = self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_THEMS=all\n")), "--check", "--lang", "en")
        self.assertIn("PAGE_1_THEMS (unknown key, ", r.stderr)
        self.assertIn("did you mean PAGE_1_THEMES ?", r.stderr)
        r = self.lancer("-c", str(self.conf(MINIMAL + "PAGE_1_THEMES=all\nPAGE_1_TITLE_EN=Links\nLINK_1_LABEL_EN=Home\n")), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_125_liens_par_page(self):
        """1.25 : LINK_n_PAGES : un lien va sur les pages données (N, N-M, liste, all) ; sans la clé, sur toutes ; page inexistante,
        valeur invalide ou page sans lien : refusées."""
        texte = self.config_deux_pages("yes") + "LINK_3_LABEL=Trois\nLINK_3_URL=https://example.org/c\nLINK_1_PAGES=1\nLINK_2_PAGES=2\n"
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        un = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        deux = (self.www / "liens2" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://example.org/a"', un)
        self.assertNotIn('href="https://example.org/b"', un)
        self.assertIn('href="https://example.org/b"', deux)
        self.assertNotIn('href="https://example.org/a"', deux)
        for page in (un, deux):
            self.assertIn('href="https://example.org/c"', page)                         # no LINK_3_PAGES: every page
        self.assertIn("PAGE_1 preparee (2 liens)", r.stdout + r.stderr)
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("yes") + "LINK_1_PAGES=1-2\nLINK_2_PAGES=all\n")), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cas = {"LINK_1_PAGES=3": "la page 3 n'existe pas", "LINK_1_PAGES=deux": "numéros de page N, N-M",
               "LINK_1_PAGES=2-1": "numéros de page N, N-M", "LINK_1_PAGES=2\nLINK_2_PAGES=2": "PAGE_1 : aucun lien ne va sur cette page"}
        for ajout, attendu in cas.items():
            with self.subTest(ajout=ajout):
                r = self.lancer("-c", str(self.conf(self.config_deux_pages("yes") + ajout + "\n")), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(attendu, r.stderr)

    def test_126_menu_de_liens(self):
        """1.26 : LINK_n_MENU : le lien n devient un menu (<details>, résumé en bouton) qui ouvre ses liens ; css/link-menu.css copié et lié ;
        les liens du menu ne sont plus au premier niveau ; refusés : menu inexistant, menu avec adresse, menu dans un menu, lien dans son
        propre menu, LINK_n_PAGES sur un lien de menu."""
        menu = ("LINK_3_LABEL=Événements\nLINK_4_LABEL=Calendrier\nLINK_4_URL=https://example.org/cal\nLINK_4_MENU=3\n"
                "LINK_5_LABEL=Archives\nLINK_5_URL=https://example.org/arch\nLINK_5_MENU=3\n")
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no") + menu)), "--update", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        html = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertTrue((self.www / "liens" / "css" / "link-menu.css").exists())
        self.assertIn('<link rel="stylesheet" href="css/link-menu.css">', html)
        bloc = html[html.index('<details class="link-menu">'):html.index("</details>", html.index('<details class="link-menu">'))]
        self.assertIn('<summary class="button button-default">', bloc)
        self.assertIn("Événements</summary>", bloc)
        self.assertLess(bloc.index("example.org/cal"), bloc.index("example.org/arch"))
        self.assertEqual(html.count("example.org/cal"), 1)                                 # only inside the menu
        self.assertIn("PAGE_1 preparee (4 liens)", r.stdout + r.stderr)
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no"))), "--update", "--yes", env=self.env)
        self.assertFalse((self.www / "liens" / "css" / "link-menu.css").exists())          # no menu: no style sheet
        cas = {"LINK_2_MENU=9": "le lien 9 n'existe pas", "LINK_2_MENU=2": "dans son propre menu",
               "LINK_2_MENU=1": "le lien 1 est un menu (LINK_n_MENU=1) : il n'a pas d'adresse",
               "LINK_3_LABEL=X\nLINK_2_MENU=3\nLINK_3_MENU=1": "un menu ne peut pas être dans un autre menu",
               "LINK_3_LABEL=X\nLINK_2_MENU=3\nLINK_2_PAGES=1": "il va sur les pages de son menu"}
        for ajout, attendu in cas.items():
            with self.subTest(ajout=ajout):
                r = self.lancer("-c", str(self.conf(self.config_deux_pages("no") + ajout + "\n")), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(attendu, r.stderr)

    def test_127_liens_dates(self):
        """1.27 : LINK_n_FROM / LINK_n_UNTIL : le lien est affiché entre ces dates (comprises) ; tâche quotidienne cron installée tant
        qu'un lien est daté, retirée ensuite ; dates invalides ou inversées refusées ; --check montre la période."""
        cron = self.tmp / "cron.d"
        env = dict(self.env, NGINX_LINK_PAGE_CRON_DIR=str(cron), NGINX_LINK_PAGE_TODAY="2026-11-22")
        texte = self.config_deux_pages("no") + "LINK_1_UNTIL=2026-11-21\nLINK_2_FROM=2026-11-22\n"
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        html = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("example.org/a", html)                                            # ended yesterday
        self.assertIn("example.org/b", html)                                               # starts today
        tache = (cron / "nginx-link-page").read_text(encoding="utf-8")
        self.assertRegex(tache, r"(?m)^5 0 \* \* \* root /.+/nginx-link-page\.sh --update --yes -c .+ 2>&1 \| logger -t nginx-link-page$")
        r = self.lancer("-c", str(self.conf(texte)), "--update", "--yes", env=dict(env, NGINX_LINK_PAGE_TODAY="2026-11-21"))
        html = (self.www / "liens" / "index.html").read_text(encoding="utf-8")
        self.assertIn("example.org/a", html)
        self.assertNotIn("example.org/b", html)
        r = self.lancer("-c", str(self.conf(texte)), "--check", env=env)
        self.assertIn("(au 2026-11-21 : caché aujourd'hui)", r.stdout)
        self.assertIn("(du 2026-11-22 : affiché aujourd'hui)", r.stdout)
        r = self.lancer("-c", str(self.conf(self.config_deux_pages("no"))), "--update", "--yes", env=env)
        self.assertFalse((cron / "nginx-link-page").exists())                             # no dated link: task removed
        for ajout, attendu in {"LINK_1_FROM=21-11-2026": "date AAAA-MM-JJ attendue", "LINK_1_UNTIL=2026-02-30": "date AAAA-MM-JJ attendue",
                               "LINK_1_FROM=2026-12-01\nLINK_1_UNTIL=2026-11-01": "le lien ne serait jamais affiché"}.items():
            with self.subTest(ajout=ajout):
                r = self.lancer("-c", str(self.conf(self.config_deux_pages("no") + ajout + "\n")), "--check")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(attendu, r.stderr)

    def test_128_check_links(self):
        """1.28 : --check-links : chaque adresse est demandée ; 404 et sans réponse = liens morts (code 1) ; 403 = à vérifier à la main
        (code 0) ; un menu n'est pas demandé."""
        texte = self.config_deux_pages("no") + "LINK_3_LABEL=Menu\nLINK_4_LABEL=Dans\nLINK_4_URL=https://example.org/d\nLINK_4_MENU=3\n"
        r = self.lancer("-c", str(self.conf(texte)), "--check-links", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[OK]   200 LINK_1 Lien <A> -> https://example.org/a", r.stdout)
        self.assertIn("LINK_4 Dans -> https://example.org/d", r.stdout)
        self.assertNotIn("LINK_3 Menu ->", r.stdout + r.stderr)
        self.assertIn("aucun lien mort", r.stdout)
        env = dict(self.env, RLQ_CURL_CODES="https://example.org/a=404 https://example.org/b=403 https://example.org/d=000")
        r = self.lancer("-c", str(self.conf(texte)), "--check-links", env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("404 LINK_1 Lien <A> -> https://example.org/a : lien mort ou en erreur", r.stderr)
        self.assertIn("pas de réponse LINK_4 Dans", r.stderr)
        self.assertIn("403 LINK_2 Autre -> https://example.org/b : le site refuse les robots", r.stdout)
        self.assertIn("2 lien(s) mort(s) ou en erreur, 1 à vérifier à la main", r.stderr)

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
        self.assertIn('href="/liens/index.html"', en)      # 1.18: /liens/ alone sends an English browser back to /liens/en/
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
