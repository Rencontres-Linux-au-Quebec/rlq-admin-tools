"""apps/_cache_ip.py — cache permanent des adresses IP (nom DNS, propriétaire du bloc RDAP, pays) : une adresse n'est cherchée qu'une fois."""
import importlib.util
import os
import sqlite3
import subprocess
import sys
import threading

ENVIRONNEMENT = "commun"   # tous les serveurs

from helpers import EnvTest, script_path

JOUR = 86400.0


def module():
    spec = importlib.util.spec_from_file_location("_cache_ip", script_path("apps/_cache_ip.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


RDAP = {"organisation": "Videotron Ltee", "reseau": "VL-Q", "plage": "11.40.0.0/14", "pays": "CA", "abus": "abuse@exemple.org", "registre": "whois.arin.net",
        "source": "RDAP"}


class CacheIP(EnvTest):
    def cache(self, nom="cache.sqlite"):
        c = module().Cache(os.path.join(self.d, nom))
        self.assertTrue(c.actif, c.raison)
        c.horloge = [1_000_000.0]
        c.maintenant = lambda: c.horloge[0]
        return c

    def test_chemin_selon_l_environnement(self):
        m = module()
        self.assertIsNone(m.chemin_cache({"NGINX_TOOLS_IP_CACHE": "off"}))                 # désactivé
        self.assertIsNone(m.chemin_cache({"NGINX_TOOLS_IP_CACHE": "NON"}))
        self.assertEqual(m.chemin_cache({"NGINX_TOOLS_IP_CACHE": "/tmp/x.sqlite"}), "/tmp/x.sqlite")
        defaut = m.chemin_cache({})
        self.assertEqual(defaut, m.DEFAUT_ROOT if os.geteuid() == 0 else os.path.join(os.path.expanduser("~"), ".cache", "nginx-tools", "ip-cache.sqlite"))
        self.assertFalse(m.Cache(None).actif)
        self.assertEqual(m.Cache(None).raison, "désactivé")

    def test_creation_droits_600_et_ligne_de_resume(self):
        c = self.cache()
        self.assertEqual(oct(os.stat(c.chemin).st_mode & 0o777), "0o600")                  # des adresses IP sont des renseignements personnels
        self.assertEqual(c.resume(), f"Cache des adresses : {c.chemin} (0 adresse(s), {os.path.getsize(c.chemin) // 1024} Ko)")
        self.assertEqual(module().Cache(None).resume(), "Cache des adresses : désactivé")

    def test_durees_de_validite_et_jamais_les_echecs(self):
        c = self.cache()
        self.assertIsNone(c.ptr("203.0.113.9"))                                            # jamais cherchée
        c.ecrire_ptr("203.0.113.9", "srv.exemple.org")
        c.ecrire_ptr("203.0.113.10", "")                                                   # le DNS dit qu'il n'y a pas de nom
        c.ecrire_rdap("203.0.113.9", RDAP)
        c.ecrire_pays("203.0.113.11", "US", "geoip")
        self.assertEqual(c.ptr("203.0.113.9"), "srv.exemple.org")
        self.assertEqual(c.ptr("203.0.113.10"), "")                                        # « aucun nom » est une réponse
        self.assertEqual(c.rdap("203.0.113.9"), RDAP)
        self.assertEqual((c.pays("203.0.113.9"), c.pays("203.0.113.11")), ("CA", "US"))   # le pays vient du RDAP ou de geoip
        c.horloge[0] += 2 * JOUR
        self.assertEqual(c.ptr("203.0.113.10"), "", "« aucun nom » encore valide après 2 jours")
        c.horloge[0] += 2 * JOUR                                                           # 4 jours : « aucun nom » périmé (3 j) ; nom trouvé encore valide (30 j)
        self.assertIsNone(c.ptr("203.0.113.10"))
        self.assertEqual(c.ptr("203.0.113.9"), "srv.exemple.org")
        c.horloge[0] += 27 * JOUR                                                          # 31 jours : nom périmé
        self.assertIsNone(c.ptr("203.0.113.9"))
        self.assertEqual(c.rdap("203.0.113.9"), RDAP)                                      # propriétaire et pays : 90 jours
        c.horloge[0] += 60 * JOUR                                                          # 91 jours
        self.assertIsNone(c.rdap("203.0.113.9"))
        self.assertIsNone(c.pays("203.0.113.9"))
        self.assertIsNone(c.pays("203.0.113.11"))

    def test_ecritures_partielles_se_completent_et_comptage_des_vues(self):
        c = self.cache()
        c.toucher("203.0.113.9")
        c.horloge[0] += 100
        c.toucher("203.0.113.9")
        c.ecrire_ptr("203.0.113.9", "srv.exemple.org")
        c.ecrire_rdap("203.0.113.9", dict(RDAP, pays=""))                                  # RDAP sans pays : n'efface pas un pays connu
        c.ecrire_pays("203.0.113.9", "US", "geoip")
        c.ecrire_pays("203.0.113.9", "", "geoip")                                          # pays vide : ignoré
        e = c.lire("203.0.113.9")
        self.assertEqual((e["n"], e["vu1"], e["vu2"]), (2, 1_000_000.0, 1_000_100.0))
        self.assertEqual((e["ptr"], e["organisation"], e["pays"], e["pays_src"]), ("srv.exemple.org", "Videotron Ltee", "US", "geoip"))
        self.assertIsNone(c.lire("198.51.100.1"))

    def test_purge_vie_privee_stats_et_vidage(self):
        c = self.cache()
        for i, age in enumerate((10, 100, 179, 181, 400)):
            c.horloge[0] = 1_000_000.0 - age * JOUR
            c.ecrire_ptr(f"203.0.113.{i}", f"h{i}")
        c.horloge[0] = 1_000_000.0
        s = c.stats()
        self.assertEqual((s["adresses"], s["avec_ptr"]), (5, 5))
        self.assertEqual(c.purger(), 2)                                                    # 181 et 400 jours sans nouvelle vue : effacées (180 j)
        self.assertEqual(c.stats()["adresses"], 3)
        self.assertEqual(c.purger(50), 2)                                                  # durée donnée : 100 et 179 jours
        c.vider()
        self.assertEqual(c.stats()["adresses"], 0)

    def test_fichier_abime_ou_inaccessible_jamais_une_exception(self):
        abime = os.path.join(self.d, "abime.sqlite")
        with open(abime, "wb") as f:
            f.write(b"ceci n'est pas une base SQLite " * 40)
        c = module().Cache(abime)
        self.assertFalse(c.actif)
        self.assertIn("inutilisable", c.raison)
        self.assertIsNone(c.ptr("203.0.113.9"))                                            # toutes les méthodes restent silencieuses
        c.ecrire_ptr("203.0.113.9", "x")
        c.toucher("203.0.113.9")
        self.assertEqual(c.purger(), 0)
        self.assertEqual(c.stats()["adresses"], 0)
        self.assertIn("inutilisable", c.resume())
        sous_un_fichier = module().Cache(os.path.join(abime, "impossible", "cache.sqlite"))   # le « dossier » est un fichier
        self.assertFalse(sous_un_fichier.actif)

    def test_plusieurs_fils_et_plusieurs_processus(self):
        c = self.cache()
        def ecrire(debut):
            for i in range(debut, debut + 100):
                c.ecrire_ptr(f"10.1.{debut // 100}.{i % 100}", f"h{i}")
        fils = [threading.Thread(target=ecrire, args=(k * 100,)) for k in range(6)]
        [f.start() for f in fils]
        [f.join() for f in fils]
        self.assertEqual(c.stats()["adresses"], 600)
        code = ("import importlib.util,sys;s=importlib.util.spec_from_file_location('c',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                "c=m.Cache(sys.argv[2]);[c.ecrire_ptr('10.2.%s.%d'%(sys.argv[3],i),'p') for i in range(150)]")
        procs = [subprocess.Popen([sys.executable, "-c", code, script_path("apps/_cache_ip.py"), c.chemin, str(k)]) for k in range(3)]
        self.assertEqual([p.wait(timeout=60) for p in procs], [0, 0, 0])
        self.assertEqual(c.stats()["adresses"], 600 + 450)                                 # écritures de processus différents : aucune perdue

    def test_ligne_de_commande(self):
        chemin = os.path.join(self.d, "cli.sqlite")
        c = module().Cache(chemin)
        c.ecrire_ptr("203.0.113.9", "srv.exemple.org")
        c.ecrire_rdap("203.0.113.9", RDAP)
        env = dict(os.environ, NGINX_TOOLS_IP_CACHE=chemin)
        def cli(*args):
            r = subprocess.run([sys.executable, script_path("apps/_cache_ip.py"), *args], capture_output=True, text=True, env=env)
            return r.returncode, r.stdout, r.stderr
        rc, out, _ = cli("--stats")
        self.assertIn(f"Cache des adresses : {chemin} (1 adresse(s)", out)
        self.assertIn("avec nom DNS : 1 ; avec propriétaire du bloc (organisation) : 1 ; avec pays : 1", out)
        rc, out, _ = cli("--show", "203.0.113.9")
        self.assertIn("nom DNS : srv.exemple.org", out)
        self.assertIn("propriétaire du bloc : Videotron Ltee (organisation) — plage 11.40.0.0/14", out)
        self.assertIn("pays : CA (rdap)", out)
        self.assertEqual(cli("--show", "198.51.100.1")[0], 1)
        self.assertIn("effacée(s)", cli("--purge", "0")[1])
        self.assertIn("vidé", cli("--clear")[1])
        self.assertRegex(cli("--version")[1], r"^_cache_ip\.py version 1\.\d+\.\d{8}\.\d{6}$")
        r = subprocess.run([sys.executable, script_path("apps/_cache_ip.py"), "--stats"], capture_output=True, text=True,
                           env=dict(os.environ, NGINX_TOOLS_IP_CACHE="off"))
        self.assertEqual(r.returncode, 1)                                                  # désactivé : code 1, message sur la sortie d'erreur
        self.assertIn("Cache des adresses : désactivé", r.stderr)


class CacheEtReseau(EnvTest):
    """_reseau.py (partagé par nginx-log-audit.sh et app-log-live.py) consulte et alimente le cache : une adresse n'est demandée qu'une fois."""
    def setUp(self):
        super().setUp()
        self.ip = "11.42.88.181"
        self.cache = os.path.join(self.d, "ip.sqlite")
        self.mock("curl", f'echo "$@" >> {self.d}/curl.log; cat {self.d}/rdap.json')
        import json
        self.write("rdap.json", json.dumps({"name": "VL-Q", "country": "CA", "cidr0_cidrs": [{"v4prefix": "11.40.0.0", "length": 14}],
                                            "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Videotron Ltee"]]]}]}))

    def reseau(self, *args, cache=True):
        r = self.run_cmd(["python3", script_path("apps/_reseau.py"), *args, self.ip], {"NGINX_TOOLS_IP_CACHE": self.cache if cache else "off"})
        return r

    def appels(self):
        try:
            with open(os.path.join(self.d, "curl.log")) as f:
                return f.read().count("rdap.org")
        except OSError:
            return 0

    def test_une_seule_requete_puis_le_cache(self):
        rc, out, err = self.reseau("--raw")
        self.assertEqual(rc, 0, err)
        premier = out
        self.assertEqual(self.appels(), 1)
        rc, out, err = self.reseau("--raw")
        self.assertEqual((rc, out), (0, premier), "même réponse depuis le cache")
        self.assertEqual(self.appels(), 1, "aucune nouvelle requête : l'adresse est dans le cache")
        rc, out, err = self.reseau("--verbose")
        self.assertIn("+ (cache des adresses) propriétaire du bloc de 11.42.88.181 : Videotron Ltee", err)
        self.assertIn("Propriétaire du bloc d'adresses : Videotron Ltee (organisation) — pays CA", out)
        self.assertEqual(self.appels(), 1)

    def test_no_cache_ne_lit_ni_n_ecrit(self):
        self.reseau("--raw", "--no-cache")
        self.reseau("--raw", "--no-cache")
        self.assertEqual(self.appels(), 2)
        self.assertFalse(os.path.exists(self.cache), "--no-cache n'écrit rien")
        self.reseau("--raw")                                                               # écrit
        self.reseau("--raw", "--no-cache")                                                 # ne lit pas
        self.assertEqual(self.appels(), 4)
        self.assertEqual(self.reseau("--raw", cache=False)[0], 0)                          # NGINX_TOOLS_IP_CACHE=off : désactivé
        self.assertEqual(self.appels(), 5)

    def test_un_echec_n_est_jamais_memorise(self):
        self.mock("curl", f'echo "$@" >> {self.d}/curl.log; exit 22')
        rc, out, err = self.reseau("--raw")
        self.assertEqual(rc, 1)
        self.mock("curl", f'echo "$@" >> {self.d}/curl.log; cat {self.d}/rdap.json')
        rc, out, err = self.reseau("--raw")
        self.assertEqual(rc, 0, "l'échec précédent n'a pas été mémorisé : la recherche est retentée")
        self.assertEqual(self.appels(), 2)
        self.assertEqual(module().Cache(self.cache).stats()["avec_proprietaire"], 1)

    def test_cache_perime_apres_90_jours(self):
        self.reseau("--raw")
        base = sqlite3.connect(self.cache)
        base.execute("UPDATE ip SET rdap_t = rdap_t - ?", (91 * JOUR,))
        base.commit()
        base.close()
        self.reseau("--raw")
        self.assertEqual(self.appels(), 2, "entrée périmée : redemandée")
