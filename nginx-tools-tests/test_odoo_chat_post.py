# -*- coding: utf-8 -*-
"""odoo-chat-post.py 1.1 : canaux et fils d'alertes dans Odoo (Discuss), premier message, publication d'alertes — contre un FAUX serveur XML-RPC d'Odoo."""
import json
import os
import subprocess
import threading
import unittest
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer


class Gestionnaire(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")

    def do_POST(self):
        if not self.path.startswith("/web/"):
            return super().do_POST()
        corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reponse = json.dumps(self.server.faux.web(self.path, corps["params"])).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reponse)))
        self.end_headers()
        self.wfile.write(reponse)

from helpers import EnvTest, script_path

ENVIRONNEMENT = "commun"


class FauxOdoo:
    """Odoo minimal en mémoire : discuss.channel (avec ou sans sous-canaux), ir.model.data, res.users, discuss.channel.member."""

    def __init__(self, sous_canaux=True, cle="bonne"):
        self.sous_canaux, self.cle = sous_canaux, cle
        self.canaux, self.messages, self.membres = {}, [], []
        self.groupes, self.ecritures_users, self.nouveaux_users, self.groupes_users = {}, [], [], {}
        self.mots_de_passe, self.web_ouvert, self.duree_max, self.identite, self.durees_demandees = [], True, 365, False, []
        self.srv_faux = None
        self.comptes = {"etienne.berube.ing@exemple.org": (20, 10), "tux-bot": (21, 11)}
        self.suivant = 100
        self.srv = SimpleXMLRPCServer(("127.0.0.1", 0), requestHandler=Gestionnaire, allow_none=True, logRequests=False)
        self.srv.register_function(self.authenticate, "authenticate")
        self.srv.register_function(self.execute_kw, "execute_kw")
        self.srv.faux = self
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def web(self, chemin, params):
        """Session web (JSON-RPC) minimale : connexion par mot de passe temporaire, vérification d'identité, assistant de clé API avec durée maximale."""
        if not self.web_ouvert:
            return {"error": {"message": "refusé", "data": {"message": "double authentification requise"}}}
        if chemin == "/web/session/authenticate":
            uid = self.comptes.get(params["login"], (None,))[0]
            return {"result": {"uid": uid if self.mots_de_passe and params["password"] == self.mots_de_passe[-1] else False}}
        modele, methode = params["model"], params["method"]
        if modele == "res.users.identitycheck":
            if methode == "run_check":
                self.identite = True
            return {"result": 1}
        if modele == "res.users.apikeys.description":
            if methode == "create":
                self.durees_demandees.append(int(params["args"][0]["duration"]))
                return {"result": 1}
            if not self.identite:
                return {"error": {"message": "x", "data": {"message": "identité non vérifiée"}}}
            if self.durees_demandees[-1] > self.duree_max:
                return {"error": {"message": "x", "data": {"message": "durée trop longue pour ce compte"}}}
            return {"result": {"context": {"default_key": "CLE-SECRETE-DU-ROBOT"}}}
        return {"error": {"message": "x", "data": {"message": "non prévu"}}}

    def arreter(self):
        self.srv.shutdown()
        self.srv.server_close()

    def authenticate(self, db, login, cle, ctx):
        return 7 if (db == "rlq" and login == "alertes" and cle == self.cle) else False

    def execute_kw(self, db, uid, cle, modele, methode, args, kwargs):
        if modele == "discuss.channel":
            if methode == "fields_get":
                return {"parent_channel_id": {"type": "many2one"}} if self.sous_canaux else {}
            if methode == "search":
                nom, parent = None, "x"
                for champ, _, valeur in args[0]:
                    if champ == "name":
                        nom = valeur
                    if champ == "parent_channel_id":
                        parent = valeur
                return [i for i, c in self.canaux.items() if c["name"] == nom and (parent == "x" or (c.get("parent_channel_id") or False) == parent)][:1]
            if methode == "create":
                self.suivant += 1
                self.canaux[self.suivant] = dict(args[0])
                return self.suivant
            if methode == "read":
                return [{"id": args[0][0], "group_public_id": ([self.canaux[args[0][0]]["group_public_id"], "g"] if self.canaux[args[0][0]].get("group_public_id") else False)}]
            if methode == "message_post":
                self.messages.append((args[0][0], kwargs["body"]))
                return 1
        if modele == "ir.model.data":
            return [{"res_id": {"group_user": 3, "group_system": 4, "group_erp_manager": 5}[args[0][1][2]]}] if args[0][1][2] in ("group_user", "group_system", "group_erp_manager") else []
        if modele == "res.groups":
            if methode == "search":
                return [i for i, nom in self.groupes.items() if nom == args[0][0][2]][:1]
            if methode == "create":
                self.suivant += 1
                self.groupes[self.suivant] = args[0]["name"]
                return self.suivant
        if modele == "res.users":
            if methode == "create":
                self.suivant += 1
                self.comptes[args[0]["login"]] = (self.suivant, self.suivant + 1000)
                self.nouveaux_users.append((args[0], kwargs.get("context")))
                return self.suivant
            if methode == "write":
                if "password" in args[1]:
                    self.mots_de_passe.append(args[1]["password"])
                self.ecritures_users.append((args[0], args[1]))
                return True
            if args[0][0][0] == "login":
                login = args[0][0][2].lower()
                if login in self.comptes:
                    uid, pid = self.comptes[login]
                    return [{"id": uid, "partner_id": [pid, login], "login": login, "groups_id": self.groupes_users.get(login, [3])}]
                return []
            return [{"partner_id": [10, "A"]}, {"partner_id": [11, "B"]}]
        if modele == "discuss.channel.member":
            if methode == "search_read":
                return [{"partner_id": [p, ""]} for c, p in self.membres if c == args[0][0][2]]
            if methode == "create":
                self.membres.append((args[0]["channel_id"], args[0]["partner_id"]))
                return 1
        raise Exception(f"faux Odoo : {modele}.{methode} non prévu")


class Canaux(EnvTest):
    def setUp(self):
        super().setUp()
        self.etc, self.home = os.path.join(self.d, "etc"), os.path.join(self.d, "home")
        os.makedirs(self.etc)
        os.makedirs(self.home)
        self.faux = None

    def tearDown(self):
        if self.faux:
            self.faux.arreter()
        super().tearDown()

    def demarrer(self, **kw):
        self.faux = FauxOdoo(**kw)
        with open(os.path.join(self.etc, "odoo-chat-post.conf"), "w", encoding="utf-8") as f:
            f.write(f"URL={self.faux.url}\nDB=rlq\nLOGIN=alertes\nAPI_KEY={self.faux.cle}\n")
        os.chmod(os.path.join(self.etc, "odoo-chat-post.conf"), 0o600)

    def lancer(self, *args, entree=None, env=None):
        e = dict(os.environ, NGINX_TOOLS_ETC_DEFAULT=self.etc, HOME=self.home, NGINX_TOOLS_CONFIG_CREER="0", NGINX_TOOLS_AVIS_ROOT="0")
        e.pop("ODOO_API_KEY", None)
        e.update(env or {})
        return subprocess.run(["python3", script_path("odoo-chat-post.py"), "--lang", "fr", *args], capture_output=True, text=True, input=entree, env=e, timeout=60)

    def test_creation_avec_premier_message(self):
        self.demarrer()
        r = self.lancer("--create")
        self.assertEqual(r.returncode, 0, r.stderr)
        noms = sorted(c["name"] for c in self.faux.canaux.values())
        self.assertIn("Odoo-Erreurs", noms)
        for fil in ("HTTP 4xx", "HTTP 5xx", "Linux", "Postgres", "NGINX", "BBB", "Autres", "Sommaire", "Pages les plus visitées", "JPOL26-Inscriptions", "JPOL26-Sondages"):
            self.assertIn(fil, noms)
        self.assertEqual(len(noms), 3 + 7 + 2 + 2)                      # 3 canaux, 11 fils
        self.assertEqual(len(self.faux.messages), len(noms))             # un premier message chacun
        self.assertTrue(all("Raison" in corps for _, corps in self.faux.messages))
        erreurs = next(i for i, c in self.faux.canaux.items() if c["name"] == "Odoo-Erreurs")
        self.assertTrue(all(c.get("parent_channel_id") == erreurs for c in self.faux.canaux.values() if c["name"] in ("HTTP 4xx", "Linux")))
        self.assertEqual(self.faux.canaux[erreurs]["group_public_id"], 3)
        self.assertEqual(len([m for m in self.faux.membres if m[0] == erreurs]), 2)       # les comptes du groupe sont membres

    def test_relance_sans_rien_changer(self):
        self.demarrer()
        self.lancer("--create")
        n, m = len(self.faux.canaux), len(self.faux.messages)
        r = self.lancer("--create")
        self.assertEqual((len(self.faux.canaux), len(self.faux.messages)), (n, m))
        self.assertIn("déjà présent", r.stdout)
        self.assertIn("0 canal(aux) / fil(s) créé(s)", r.stdout)

    def test_a_blanc_n_ecrit_rien(self):
        self.demarrer()
        r = self.lancer("--create", "--dry-run")
        self.assertEqual((self.faux.canaux, self.faux.messages), ({}, []))
        self.assertIn("À créer : canal Odoo-Erreurs", r.stdout)
        self.assertIn("rien n'a été écrit", r.stdout)

    def test_suggeres_seulement_sur_demande(self):
        self.demarrer()
        self.lancer("--create")
        self.assertNotIn("Odoo-Sécurité", [c["name"] for c in self.faux.canaux.values()])
        self.lancer("--create", "--suggested", "--event", "JPOL26", "--event", "JPOL27")
        noms = [c["name"] for c in self.faux.canaux.values()]
        for n in ("Odoo-Sécurité", "Bannissements", "Odoo-Sauvegardes", "JPOL27-Inscriptions", "JPOL27-Incidents"):
            self.assertIn(n, noms)

    def test_sans_sous_canaux_chaque_fil_est_un_canal(self):
        self.demarrer(sous_canaux=False)
        r = self.lancer("--create")
        self.assertEqual(r.returncode, 0, r.stderr)
        noms = [c["name"] for c in self.faux.canaux.values()]
        self.assertIn("Odoo-Erreurs — HTTP 5xx", noms)
        self.assertIn("pas de sous-canaux", r.stdout)

    def test_publier_une_alerte(self):
        self.demarrer()
        self.lancer("--create")
        avant = len(self.faux.messages)
        r = self.lancer("--post", "Odoo-Erreurs/HTTP 5xx", "--message", "Page de maintenance <b>affichée</b>\nsecond ligne")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.faux.messages), avant + 1)
        cible, corps = self.faux.messages[-1]
        self.assertEqual(self.faux.canaux[cible]["name"], "HTTP 5xx")
        self.assertIn("&lt;b&gt;affichée&lt;/b&gt;<br/>second ligne", corps)           # texte échappé : jamais de HTML venu d'un journal

    def test_publier_depuis_l_entree_standard(self):
        self.demarrer()
        self.lancer("--create")
        r = self.lancer("--post", "Odoo-Stats/Sommaire", "--message", "-", entree="visites : 120\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("visites : 120", self.faux.messages[-1][1])

    def test_publier_dans_un_fil_absent(self):
        self.demarrer()
        r = self.lancer("--post", "Odoo-Erreurs/HTTP 5xx", "--message", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("introuvable", r.stderr)

    def test_message_vide_refuse(self):
        self.demarrer()
        self.lancer("--create")
        r = self.lancer("--post", "Odoo-Erreurs/Linux", "--message", "   ")
        self.assertEqual(r.returncode, 2)

    def test_liste(self):
        self.demarrer()
        r = self.lancer("--list")
        self.assertIn("absent   Odoo-Erreurs", r.stdout)
        self.lancer("--create")
        self.assertIn("présent  Odoo-Erreurs", self.lancer("--list").stdout)

    def test_mauvaise_cle(self):
        self.demarrer()
        r = self.lancer("--list", env={"ODOO_API_KEY": "mauvaise"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("authentification refusée", r.stderr)

    def test_la_cle_n_est_jamais_affichee(self):
        self.demarrer()
        r = self.lancer("--create", "--dry-run")
        self.assertNotIn("bonne", r.stdout + r.stderr.replace("bonne", "") + "")
        self.assertNotIn("API_KEY=bonne", r.stdout + r.stderr)

    def test_fichier_de_cle_trop_ouvert(self):
        self.demarrer()
        os.chmod(os.path.join(self.etc, "odoo-chat-post.conf"), 0o644)
        r = self.lancer("--list")
        self.assertIn("chmod 600", r.stderr)
        self.assertEqual(r.returncode, 0)

    def test_reglages_manquants(self):
        r = self.lancer("--list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("réglages manquants", r.stderr)

    def test_action_obligatoire(self):
        self.demarrer()
        self.assertEqual(self.lancer().returncode, 2)

    def test_catalogue_perso(self):
        self.demarrer()
        chemin = os.path.join(self.d, "cat.json")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"canaux": [{"nom": "Mon-Canal", "raison": "x", "fils": [{"nom": "Un fil", "raison": "y"}]}]}, f)
        self.lancer("--create", "--catalog", chemin)
        self.assertEqual(sorted(c["name"] for c in self.faux.canaux.values()), ["Mon-Canal", "Un fil"])

    def test_acces_restreint_groupe_et_membres(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        r = self.lancer("--create", "--members", "Etienne.Berube.ing@exemple.org,tux-bot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.faux.groupes), 1)
        gid = next(iter(self.faux.groupes))
        erreurs = next(i for i, c in self.faux.canaux.items() if c["name"] == "Odoo-Erreurs")
        self.assertEqual(self.faux.canaux[erreurs]["group_public_id"], gid)          # PAS base.group_user
        self.assertEqual({p for c, p in self.faux.membres}, {10})                    # seul le compte de Étienne
        self.assertIn("ATTENTION : le compte tux-bot n'existe pas encore", r.stdout)
        self.assertIn("Accès restreint à : etienne.berube.ing@exemple.org", r.stdout)
        self.assertEqual(self.faux.ecritures_users, [([20], {"groups_id": [[4, gid]]})] * len(self.faux.ecritures_users))
        self.assertTrue(self.faux.ecritures_users)

    def test_acces_restreint_robot_ajoute_a_la_relance(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        self.lancer("--create", "--members", "etienne.berube.ing@exemple.org,tux-bot")
        n_canaux, n_messages = len(self.faux.canaux), len(self.faux.messages)
        self.faux.comptes["tux-bot"] = (21, 11)                                      # le compte vient d'être créé dans Odoo
        r = self.lancer("--create", "--members", "etienne.berube.ing@exemple.org,tux-bot")
        self.assertEqual((len(self.faux.canaux), len(self.faux.messages)), (n_canaux, n_messages))
        self.assertEqual({p for c, p in self.faux.membres}, {10, 11})
        self.assertEqual(len(self.faux.groupes), 1)                                  # groupe réutilisé, pas recréé
        self.assertIn("membre(s) ajouté(s) à Odoo-Erreurs", r.stdout)
        self.assertNotIn("ATTENTION", r.stdout)

    def test_acces_restreint_canal_existant_trop_ouvert_signale(self):
        self.demarrer()
        self.lancer("--create")                                                      # canaux créés d'abord pour tous les internes
        r = self.lancer("--create", "--members", "etienne.berube.ing@exemple.org")
        self.assertIn("Odoo-Erreurs est visible par un autre groupe", r.stdout)
        erreurs = next(i for i, c in self.faux.canaux.items() if c["name"] == "Odoo-Erreurs")
        self.assertEqual(self.faux.canaux[erreurs]["group_public_id"], 3)            # jamais modifié
        self.assertIn(10, {p for c, p in self.faux.membres if c == erreurs})

    def test_acces_restreint_suggeres_et_config(self):
        self.demarrer()
        with open(os.path.join(self.etc, "odoo-chat-post.conf"), "a", encoding="utf-8") as f:
            f.write("MEMBERS=etienne.berube.ing@exemple.org,tux-bot\nSUGGESTED=oui\nEVENTS=JPOL26\n")
        r = self.lancer("--create")
        self.assertEqual(r.returncode, 0, r.stderr)
        noms = [c["name"] for c in self.faux.canaux.values()]
        for n in ("Odoo-Sécurité", "Odoo-Courriels", "Odoo-Sauvegardes", "Odoo-Mises-à-jour", "Évent-Jour-J", "JPOL26-Affluence", "JPOL26-Incidents", "Certificats SSL"):
            self.assertIn(n, noms)
        gid = next(iter(self.faux.groupes))
        racines = [c for c in self.faux.canaux.values() if not c.get("parent_channel_id")]
        self.assertTrue(racines and all(c["group_public_id"] == gid for c in racines))
        self.assertEqual({p for c, p in self.faux.membres}, {10, 11})                # fils compris

    def test_acces_restreint_a_blanc_n_ecrit_rien(self):
        self.demarrer()
        r = self.lancer("--create", "--dry-run", "--members", "etienne.berube.ing@exemple.org")
        self.assertEqual((self.faux.canaux, self.faux.messages, self.faux.groupes, self.faux.membres, self.faux.ecritures_users), ({}, [], {}, [], []))
        self.assertIn("rien n'a été écrit", r.stdout)

    def test_robot_droits_minimaux(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        r = self.lancer("--create-bot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.faux.nouveaux_users), 1)
        valeurs, contexte = self.faux.nouveaux_users[0]
        self.assertEqual(valeurs["login"], "tux-bot")
        self.assertEqual(valeurs["groups_id"], [[6, 0, [3]]])                         # utilisateur interne SEUL
        self.assertNotIn("password", valeurs)                                          # aucun mot de passe
        self.assertTrue(contexte["no_reset_password"])                                 # aucun courriel d'invitation
        self.assertIn("mot de passe aléatoire", r.stdout)
        self.assertEqual(self.faux.canaux, {})                                          # --create-bot seul ne crée aucun canal

    def test_robot_existant_inchange_et_droits_admin_signales(self):
        self.demarrer()
        self.faux.groupes_users["tux-bot"] = [3, 4]
        r = self.lancer("--create-bot", "--bot-login", "Tux-Bot")
        self.assertEqual(self.faux.nouveaux_users, [])
        self.assertIn("déjà présent", r.stdout)
        self.assertIn("droits d'administration (base.group_system)", r.stdout)

    def test_robot_a_blanc(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        r = self.lancer("--create-bot", "--dry-run")
        self.assertEqual(self.faux.nouveaux_users, [])
        self.assertIn("À créer : compte tux-bot", r.stdout)

    def conf(self):
        with open(os.path.join(self.etc, "odoo-chat-post.conf"), encoding="utf-8") as f:
            return f.read()

    def test_robot_cle_creee_et_ecrite(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        with open(os.path.join(self.etc, "odoo-chat-post.conf"), "a", encoding="utf-8") as f:
            f.write("MEMBERS=etienne.berube.ing@exemple.org\n")
        r = self.lancer("--create-bot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.faux.durees_demandees, [365])                           # un an
        self.assertIn("valable 365 jour(s)", r.stdout)
        texte = self.conf()
        self.assertIn("API_KEY=CLE-SECRETE-DU-ROBOT", texte)
        self.assertIn("LOGIN=tux-bot", texte)
        self.assertNotIn("LOGIN=alertes", texte)
        self.assertNotIn("API_KEY=bonne", texte)
        self.assertIn("MEMBERS=etienne.berube.ing@exemple.org,tux-bot", texte)
        self.assertEqual(os.stat(os.path.join(self.etc, "odoo-chat-post.conf")).st_mode & 0o777, 0o600)
        sauvegardes = [f for f in os.listdir(self.etc) if f.endswith(".bak")]
        self.assertEqual(len(sauvegardes), 1)
        self.assertEqual(os.stat(os.path.join(self.etc, sauvegardes[0])).st_mode & 0o777, 0o600)
        self.assertNotIn("CLE-SECRETE-DU-ROBOT", r.stdout + r.stderr)                  # jamais affichée
        self.assertEqual(len(self.faux.mots_de_passe), 2)                              # mot de passe temporaire puis mot de passe jeté
        self.assertNotEqual(self.faux.mots_de_passe[0], self.faux.mots_de_passe[1])

    def test_robot_cle_duree_reduite_si_odoo_limite(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        self.faux.duree_max = 90
        r = self.lancer("--create-bot")
        self.assertEqual(self.faux.durees_demandees, [365, 180, 90])
        self.assertIn("valable 90 jour(s)", r.stdout)
        self.assertIn("durée maximale acceptée", r.stdout)
        self.assertIn("API_KEY=CLE-SECRETE-DU-ROBOT", self.conf())

    def test_robot_session_web_refusee_reste_manuel(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        self.faux.web_ouvert = False
        avant = self.conf()
        r = self.lancer("--create-bot")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("clé API non créée automatiquement", r.stdout)
        self.assertIn("Création manuelle", r.stdout)
        self.assertEqual(self.conf(), avant)                                            # configuration intacte
        self.assertEqual(len(self.faux.mots_de_passe), 2)                               # mot de passe rendu inutilisable malgré l'échec

    def test_robot_fichier_non_inscriptible_rien_cree(self):
        self.demarrer()
        self.faux.comptes.pop("tux-bot")
        r = self.lancer("--create-bot", "--bot-config", "/inexistant-xyz/odoo-chat-post.conf")
        self.assertEqual(r.returncode, 1)
        self.assertIn("rien n'est créé", r.stderr)
        self.assertEqual((self.faux.nouveaux_users, self.faux.mots_de_passe), ([], []))

    def test_robot_existant_cle_seulement_avec_renew_key(self):
        self.demarrer()
        r = self.lancer("--create-bot")
        self.assertIn("Aucune nouvelle clé créée", r.stdout)
        self.assertEqual(self.faux.durees_demandees, [])
        r = self.lancer("--create-bot", "--renew-key")
        self.assertEqual(self.faux.durees_demandees, [365])
        self.assertIn("API_KEY=CLE-SECRETE-DU-ROBOT", self.conf())

    def test_robot_login_administrateur_obligatoire(self):
        self.demarrer()
        r = self.lancer("--create-bot", "--login", "tux-bot")
        self.assertEqual(r.returncode, 1)
        self.assertIn("compte ADMINISTRATEUR", r.stderr)

    def test_options_triees_et_version(self):
        r = self.lancer("--help")
        options = [l.split()[0].lstrip("-") for l in r.stdout.splitlines() if l.startswith("  --")]
        self.assertEqual(options, sorted(options, key=str.lower))
        self.assertIn("odoo-chat-post.py version 1.", self.lancer("--version").stdout)


if __name__ == "__main__":
    unittest.main()
