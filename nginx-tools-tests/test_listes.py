"""apps/_listes.py et apps/_listes.sh — liste blanche (/etc/default/nginx-tools-white-list.conf) et lieux (nginx-tools-ip-location.conf) :
un lecteur commun pour six programmes, en Python et en bash, qui doivent donner les mêmes résultats."""
import importlib.util
import os
import re
import subprocess
import sys

ENVIRONNEMENT = "commun"   # tous les serveurs

from helpers import EnvTest, SCRIPTS_DIR, script_path

SEP = "\x1f"
BLANCHE = """# commentaire seul

203.0.113.10        # Étienne (maison)
198.51.100.0/24     # Bureau
198.51.100.77
203.0.113.50        # Invité   [partagée]
pas-une-adresse     # invalide
203.0.113.99        # Option inconnue [bizarre]
"""
LIEUX = """192.0.2.0/24        # Université exemple     [partagée]
192.0.2.128/25      # Labo (sous-réseau)     [Partagee] [PROTEGEE]
2001:db8::/32       # Réseau v6
"""


ABSENT = "/nonexistent-rlq-tests/absent.conf"


def module(isole=True):
    """Le lecteur Python, ses emplacements par défaut (/etc/default/nginx-tools-*.conf) pointés vers un chemin ABSENT : sur un serveur réel ces
    fichiers existent et fausseraient tout test « sans surcharge d'environnement »."""
    spec = importlib.util.spec_from_file_location("_listes", script_path("apps/_listes.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if isole:
        m.BLANCHE_DEFAUT = m.LIEUX_DEFAUT = ABSENT
    return m


def listes_sh(dossier):
    """Copie de apps/_listes.sh dans `dossier` dont les emplacements par défaut sont ABSENTS (même raison que module())."""
    with open(script_path("apps/_listes.sh"), encoding="utf-8") as f:
        texte = f.read()
    texte = re.sub(r'(?m)^(LISTES_(?:BLANCHE|LIEUX)_DEFAUT)=".*"$', r'\1="' + ABSENT + '"', texte)
    chemin = os.path.join(dossier, "_listes-isole.sh")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(texte)
    return chemin


class ListesPython(EnvTest):
    def charge(self):
        return module().charger(os.path.join(SCRIPTS_DIR, "apps"), {"NGINX_TOOLS_WHITE_LIST": self.write("blanche.conf", BLANCHE),
                                                                    "NGINX_TOOLS_IP_LOCATION": self.write("lieux.conf", LIEUX)})

    def test_syntaxe_options_et_problemes(self):
        L = self.charge()
        blanche = {str(e.reseau): (e.libelle, e.partagee, e.protegee) for e in L.blanche}
        self.assertEqual(blanche["203.0.113.10/32"], ("Étienne (maison)", False, False))
        self.assertEqual(blanche["198.51.100.77/32"][0], "")                                    # adresse sans libellé
        self.assertEqual(blanche["203.0.113.50/32"][0], "Invité")                               # une option n'est jamais dans le libellé
        self.assertEqual(len(L.blanche), 5)                                                     # 6 lignes utiles, 1 invalide
        lieux = {str(e.reseau): (e.libelle, e.partagee, e.protegee) for e in L.lieux}
        self.assertEqual(lieux["192.0.2.0/24"], ("Université exemple", True, False))
        self.assertEqual(lieux["192.0.2.128/25"], ("Labo (sous-réseau)", True, True))           # casse et accents : [Partagee] [PROTEGEE]
        self.assertEqual(lieux["2001:db8::/32"][0], "Réseau v6")
        problemes = "\n".join(L.problemes)
        self.assertIn("blanche.conf:7 : adresse invalide « pas-une-adresse »", problemes)
        self.assertIn("blanche.conf:8 : option inconnue « [bizarre] »", problemes)
        self.assertEqual(len(L.problemes), 2)

    def test_plage_la_plus_precise_et_priorites(self):
        L = self.charge()
        self.assertEqual(L.lieu("192.0.2.200").libelle, "Labo (sous-réseau)")                   # /25 avant /24
        self.assertEqual(L.lieu("192.0.2.5").libelle, "Université exemple")
        self.assertIsNone(L.lieu("8.8.8.8"))
        self.assertEqual(L.etiquette("203.0.113.10"), "Étienne (maison)")                       # liste blanche d'abord
        self.assertEqual(L.etiquette("192.0.2.5"), "Université exemple")                        # puis le lieu
        self.assertEqual(L.etiquette("8.8.8.8"), "")
        self.assertTrue(L.protegee("203.0.113.10"))                                            # liste blanche : jamais bannie
        self.assertTrue(L.protegee("192.0.2.200"))                                             # lieu [protégée]
        self.assertFalse(L.protegee("192.0.2.5"))                                              # lieu seulement [partagée] : non
        self.assertFalse(L.protegee("not-an-ip"))
        reseaux = [str(r) for r in L.reseaux_ne_pas_bannir()]
        self.assertIn("192.0.2.128/25", reseaux)
        self.assertNotIn("192.0.2.0/24", reseaux)

    def test_liste_blanche_seulement_dans_etc_default_lieux_aussi_dans_home(self):
        home = os.path.dirname(self.path("home", "x"))
        with open(os.path.join(home, ".nginx-tools-white-list.conf"), "w") as f:
            f.write("203.0.113.1  # caché dans ~\n")                                           # ne doit JAMAIS être lu : la liste blanche donne accès
        with open(os.path.join(home, ".nginx-tools-ip-location.conf"), "w") as f:
            f.write("192.0.2.0/24  # Lieu de l'utilisateur  [partagée]\n")
        ancien_home = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            L = module().charger(os.path.join(SCRIPTS_DIR, "apps"), {})                         # aucune surcharge : chemins par défaut
            blanche, _, lieux = module(isole=False).chemins({})          # les VRAIS emplacements par défaut (chemins seulement : rien n'est lu)
        finally:
            if ancien_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = ancien_home
        self.assertEqual(blanche, "/etc/default/nginx-tools-white-list.conf")
        self.assertEqual(lieux, ["/etc/default/nginx-tools-ip-location.conf", os.path.join(home, ".nginx-tools-ip-location.conf")])
        self.assertEqual(L.blanche, [])
        self.assertEqual(L.lieu("192.0.2.9").libelle, "Lieu de l'utilisateur")
        self.assertIn("liste blanche : aucun fichier", L.resume())

    def test_ancien_emplacement_transitoire(self):
        apps = os.path.dirname(self.write("apps/team-ips.list", "203.0.113.10  # ancienne liste\n"))
        L = module().charger(apps, {})                                                          # sans surcharge d'environnement
        self.assertTrue(L.ancien)
        self.assertEqual(L.etiquette("203.0.113.10"), "ancienne liste")
        self.assertIn("ANCIEN emplacement, à migrer : nginx-hardening.sh --update", L.resume())
        nouveau = self.write("nouveau.conf", "203.0.113.10  # nouvelle liste\n")                # le nouveau fichier l'emporte
        L = module().charger(apps, {"NGINX_TOOLS_WHITE_LIST": nouveau})
        self.assertFalse(L.ancien)
        self.assertEqual(L.etiquette("203.0.113.10"), "nouvelle liste")
        L = module().charger(apps, {"NGINX_TOOLS_WHITE_LIST": os.path.join(self.d, "absent.conf")})   # chemin explicite absent : pas de repli
        self.assertEqual(L.blanche, [])

    def test_ligne_de_resume_et_cli(self):
        blanche, lieux = self.write("blanche.conf", BLANCHE), self.write("lieux.conf", LIEUX)
        env = dict(os.environ, NGINX_TOOLS_WHITE_LIST=blanche, NGINX_TOOLS_IP_LOCATION=lieux)
        r = subprocess.run([sys.executable, script_path("apps/_listes.py"), "--resume"], capture_output=True, text=True, env=env)
        self.assertIn(f"Listes : liste blanche {blanche} (5 adresse(s)) ; lieux {lieux} (3 plage(s))", r.stdout)
        self.assertIn("ATTENTION", r.stdout)
        r = subprocess.run([sys.executable, script_path("apps/_listes.py"), "--ip", "192.0.2.200"], capture_output=True, text=True, env=env)
        self.assertIn("lieu : Labo (sous-réseau) [partagée] [protégée] ; protégée : oui", r.stdout)
        r = subprocess.run([sys.executable, script_path("apps/_listes.py"), "--version"], capture_output=True, text=True, env=env)
        self.assertRegex(r.stdout, r"^_listes\.py version 1\.\d+\.\d{8}\.\d{6}$")


class ListesBash(EnvTest):
    def bash(self, commande, **env):
        e = dict(os.environ, NGINX_TOOLS_WHITE_LIST=self.write("blanche.conf", BLANCHE), NGINX_TOOLS_IP_LOCATION=self.write("lieux.conf", LIEUX),
                 SCRIPT_DIR=SCRIPTS_DIR)
        e.update(env)
        r = subprocess.run(["bash", "-c", f'. "{listes_sh(self.d)}"\n{commande}'], capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def normaliser(self, entrees):
        """[(adresse, libellé, options)] comparables entre bash (texte) et Python (objets)."""
        res = []
        for e in entrees:
            a = e.reseau
            adr = str(a.network_address) if a.prefixlen == a.max_prefixlen else str(a)
            res.append((adr, e.libelle, ",".join(o for o, v in (("partagee", e.partagee), ("protegee", e.protegee)) if v)))
        return res

    def test_meme_resultat_que_python(self):
        """Le lecteur bash et le lecteur Python doivent donner les mêmes entrées valides (adresse, libellé, options), pour les deux listes."""
        L = module().charger(os.path.join(SCRIPTS_DIR, "apps"), {"NGINX_TOOLS_WHITE_LIST": self.write("blanche.conf", BLANCHE),
                                                                  "NGINX_TOOLS_IP_LOCATION": self.write("lieux.conf", LIEUX)})
        for commande, entrees in (("listes_blanche", L.blanche), ("listes_lieux", L.lieux)):
            with self.subTest(liste=commande):
                bash = [tuple(l.split(SEP)[:3]) for l in self.bash(f"{commande} | listes_valides").splitlines()]
                bash = [(a, lib, ",".join(o for o in opts.split(",") if o in ("partagee", "protegee"))) for a, lib, opts in bash]
                self.assertEqual(bash, self.normaliser(entrees))

    def test_champs_vides_conserves_et_numeros_de_ligne(self):
        """listes_lire sépare par le caractère 037 : « read » avec une tabulation fusionnait les champs vides (numéro de ligne perdu :
        « ligne  : pas-une-adresse »)."""
        lignes = {l.split(SEP)[0]: l.split(SEP) for l in self.bash("listes_blanche").splitlines()}
        self.assertEqual(lignes["pas-une-adresse"], ["pas-une-adresse", "invalide", "", "7"])
        self.assertEqual(lignes["198.51.100.77"], ["198.51.100.77", "", "", "5"])                # libellé ET options vides
        self.assertEqual(lignes["203.0.113.99"][2], "inconnue:bizarre")
        lieux = {l.split(SEP)[0]: l.split(SEP) for l in self.bash("listes_lieux").splitlines()}
        self.assertEqual(lieux["192.0.2.128/25"], ["192.0.2.128/25", "Labo (sous-réseau)", "partagee,protegee", "2"])

    def test_ne_pas_bannir_resume_et_fichiers(self):
        protegees = self.bash("listes_ne_pas_bannir").split()
        for a in ("203.0.113.10", "198.51.100.0/24", "198.51.100.77", "203.0.113.50", "203.0.113.99", "192.0.2.128/25"):
            self.assertEqual(protegees.count(a), 1, a)                                           # liste blanche + lieux [protégée], sans doublon
        for a in ("192.0.2.0/24", "2001:db8::/32", "pas-une-adresse"):
            self.assertNotIn(a, protegees)                                                       # lieu non protégé, adresse invalide : jamais
        blanche, lieux = os.path.join(self.d, "blanche.conf"), os.path.join(self.d, "lieux.conf")
        self.assertEqual(self.bash("listes_resume").strip(), f"Listes : liste blanche {blanche} (5 adresse(s)) ; lieux {lieux} (3 plage(s))")
        home = os.path.dirname(self.path("home", "x"))
        vide = self.bash("listes_resume", NGINX_TOOLS_WHITE_LIST=os.path.join(self.d, "absent"), NGINX_TOOLS_IP_LOCATION=os.path.join(self.d, "absent2"), HOME=home).strip()
        self.assertEqual(vide, "Listes : liste blanche : aucun fichier ; lieux : aucun fichier")
        with open(os.path.join(home, ".nginx-tools-ip-location.conf"), "w") as f:
            f.write("192.0.2.0/24  # Lieu\n")
        r = subprocess.run(["bash", "-c", f'. "{listes_sh(self.d)}"; listes_resume'], capture_output=True, text=True,
                           env={k: v for k, v in dict(os.environ, NGINX_TOOLS_WHITE_LIST=os.path.join(self.d, "absent"), HOME=home, SCRIPT_DIR=SCRIPTS_DIR).items()
                                if k != "NGINX_TOOLS_IP_LOCATION"})
        self.assertIn(f"lieux {home}/.nginx-tools-ip-location.conf (1 plage(s))", r.stdout)

    def test_ancien_emplacement_en_bash(self):
        dossier = os.path.dirname(self.write("scripts/apps/team-ips.list", "203.0.113.10  # ancienne\n"))
        env = {k: v for k, v in os.environ.items() if k not in ("NGINX_TOOLS_WHITE_LIST", "NGINX_TOOLS_IP_LOCATION")}
        env["SCRIPT_DIR"] = os.path.dirname(dossier)
        r = subprocess.run(["bash", "-c", f'. "{listes_sh(self.d)}"; listes_resume'], capture_output=True, text=True, env=env)
        self.assertIn("(1 adresse(s)) — ANCIEN emplacement, à migrer : nginx-hardening.sh --update", r.stdout)
