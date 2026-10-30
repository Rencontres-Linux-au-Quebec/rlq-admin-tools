"""odoo-mail-retry.py — liste des courriels d'Odoo non envoyés (titre, date, destinataires masqués, cause), puis proposition de les renvoyer."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"   # Odoo seulement : les courriels d'Odoo (mail.mail)
import os
import re
import time

from helpers import sans_origine, EnvTest, sans_date

SEP = "\x1f"
T0 = 1759784400                      # instant du premier courriel ; les suivants quelques minutes plus tard
RAISON_452 = "Échec de l'envoi de l'e-mail via le serveur SMTP 'None'. SMTPDataError: (452, b'4.4.5 Maximum number of messages per session exceeded.')"
RAISON_550 = ("Échec de l'envoi de l'e-mail via le serveur SMTP 'None'. SMTPDataError: (550, b'You are not allowed to send emails as \"etienne@exemple.org\" "
              "(header From) while using \"admin@exemple.org\" as envelope sender (MAIL FROM: ...). Please fix.')")
COURRIELS = [   # id, instant, title, recipients, reason - from the oldest to the most recent (order of the query)
    (7171, T0 - 86400 * 20, "Invitation à l'événement", "x@exemple.fr", RAISON_550),
    (7404, T0, "Bienvenue sur la plateforme", "jean.dupont@exemple.org", RAISON_452),
    (7405, T0 + 60, "Bienvenue sur la plateforme", "marie@exemple.org", RAISON_452),
    (7406, T0 + 120, "Votre inscription", "alex@exemple.org, sam@exemple.org", RAISON_452),
    (7500, T0 + 180, "Rappel", "", ""),
]


def heure(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


class _Base(EnvTest):
    """Faux PostgreSQL et lancement du programme (classe de base sans test)."""
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("odoo-mail-retry.py")
        self.prepare("app-log-check.py")                                   # diagnostics base (cause of a failure), next to the program
        self.env["ODOO_MAIL_RETRY_LOG"] = self.path("journal-renvois.log")
        self.env["HOME"] = self.path("maison", "x")[:-2]
        os.makedirs(self.env["HOME"], exist_ok=True)
        self.donnees(COURRIELS)
        self.postgresql()

    def donnees(self, courriels, deja=()):
        self.write("echecs.txt", "".join(SEP.join(map(str, c)) + "\n" for c in courriels))
        self.write("deja.txt", "".join(f"{i}\n" for i in deja))

    def postgresql(self, bases="linux_meetup_odoo_18\nautre_base\n", avec_courriels=("linux_meetup_odoo_18",), parametres=""):
        """runuser simulé : répond à chaque requête selon son contenu ; journalise tous les appels ; l'UPDATE ne renvoie que les courriels encore en échec."""
        self.write("bases.txt", bases)
        self.write("param.txt", parametres)
        self.write("avec.txt", "".join(f"{b}\n" for b in avec_courriels))
        d = self.d
        if not os.path.exists(self.path("inscriptions.txt")):
            self.write("inscriptions.txt", "")
        self.mock("runuser", f'''echo "$@" >> {d}/runuser.log
case "$*" in
 *"FROM event_registration r JOIN event_event e"*"LEFT JOIN res_partner"*) cat {d}/inscriptions.txt;;
 *information_schema.columns*) echo 1;;
 *"SELECT DISTINCT m.id FROM mail_mail"*) echo 7171;;
 *"UPDATE event_registration"*) printf 'registration\037%s\npartner\037%s\nemail_to\0371\nmails\0371\n' 1 "$(echo "$*" | grep -c 'UPDATE res_partner')";;
 *pg_database*) cat {d}/bases.txt;;
 *to_regclass*) for a in "$@"; do :; done; b=$(echo "$*" | sed -n 's/.*psql -d \\([^ ]*\\) .*/\\1/p'); grep -qx "$b" {d}/avec.txt && echo t || echo f;;
 *"UPDATE mail_mail"*) ids=$(echo "$*" | sed -n 's/.*IN (\\([0-9, ]*\\)).*/\\1/p' | tr -d ' ' | tr ',' '\\n'); for i in $ids; do grep -qx "$i" {d}/deja.txt || echo "$i"; done; echo "UPDATE 1";;
 *"state = 'sent'"*) cat {d}/envoyes.txt;;
 *string_agg*) cat {d}/echecs.txt;;
 *ir_config_parameter*) cat {d}/param.txt;;
 *"GROUP BY state"*) printf 'sent\\037120\\nexception\\0375\\noutgoing\\0373\\n';;
 *) ;;
esac''')

    def lancer(self, *args, env_extra=None):
        rc, out, err = self.run_cmd(["python3", self.prog, *args], env_extra)
        self.assertNotIn("Traceback", err, err)
        return rc, out, err

    def appels(self, motif=None):
        try:
            with open(self.path("runuser.log")) as f:
                l = f.read().splitlines()
        except OSError:
            return []
        return [x for x in l if motif is None or motif in x]

    def ids_remis(self):
        u = self.appels("UPDATE mail_mail")
        return [int(i) for i in re.search(r"IN \(([0-9, ]+)\)", u[-1]).group(1).replace(" ", "").split(",")] if u else []


class OdooMailRetry(_Base):
    def test_sent_derniers_courriels_envoyes(self):
        """1.4 : --sent N liste les N derniers courriels ENVOYÉS (adresses masquées sauf --details) et quitte, sans la liste des échecs ni le menu."""
        self.write("envoyes.txt", SEP.join(["9002", str(T0 + 60), "Merci de votre inscription", "jean.dupont@exemple.org"]) + "\n"
                   + SEP.join(["9001", str(T0), "Bienvenue", "marie@exemple.org"]) + "\n")
        rc, out, err = self.lancer("--sent", "2", "--db", "linux_meetup_odoo_18")
        self.assertEqual(rc, 0, err)
        self.assertIn("#9002", out)
        self.assertIn("« Merci de votre inscription »", out)
        self.assertIn("j***@exemple.org", out)
        self.assertNotIn("jean.dupont", out)
        self.assertNotIn("Courriels non envoyés", out)
        self.assertIn("LIMIT 2", "\n".join(self.appels("state = 'sent'")))
        rc, out, err = self.lancer("--sent", "2", "--db", "linux_meetup_odoo_18", "--details")
        self.assertIn("jean.dupont@exemple.org", out)
        rc, out, err = self.lancer("--sent", "0")
        self.assertEqual(rc, 2)

    # --- la liste ------------------------------------------------------------------------------------------------------
    def test_liste_titre_de_chaque_courriel_destinataires_masques_cause_et_totaux(self):
        rc, out, err = self.lancer("--no-prompt")
        self.assertEqual(rc, 0, err)
        self.assertRegex(out, r"^odoo-mail-retry\.py v1\.\d+\.\d{8}\.\d{6}\n")
        self.assertIn("Courriels non envoyés — base linux_meetup_odoo_18, 30 derniers jours : 5 en échec d'envoi, 3 en attente d'envoi, 120 envoyés", out)
        self.assertNotIn("autre_base", out)                                                    # without an e-mail table: ignored
        self.assertIn("(adresses masquées ; --details pour les voir en entier)", out)
        self.assertIn(f"#7404   {heure(T0)}   « Bienvenue sur la plateforme »", out)           # le TITRE de chaque courriel
        self.assertIn(f"#7406   {heure(T0 + 120)}   « Votre inscription »", out)
        self.assertIn(f"#7171   {heure(T0 - 86400 * 20)}   « Invitation à l'événement »", out)
        self.assertIn("À : j***@exemple.org — cause : limite de messages par connexion (452) — transitoire", out)
        self.assertIn("À : a***@exemple.org, s***@exemple.org — cause : limite de messages par connexion (452) — transitoire", out)
        self.assertIn("À : x***@exemple.fr — cause : expéditeur refusé (550) — PERMANENTE", out)
        self.assertIn("À : (aucun destinataire noté) — cause : cause inconnue", out)
        self.assertNotIn("jean.dupont", out)
        totaux = " ".join(out.split())
        self.assertIn("Par titre : « Bienvenue sur la plateforme » ×2 ; « Invitation à l'événement » ×1 ; « Rappel » ×1 ; « Votre inscription » ×1", totaux)
        self.assertIn("limite de messages par connexion (452) ×3", totaux)
        self.assertIn("Par jour  : ", out)
        self.assertIn("Pour les renvoyer : relancer sur un terminal (menu), ou avec --resend --yes", out)    # sans terminal : jamais de renvoi
        self.assertEqual(self.appels("UPDATE"), [], "la liste n'écrit rien")
        self.assertIn("Configuration lue : aucun fichier (valeurs par défaut)\n  Options : --lang fr · courriels des 30 derniers jours · lot de renvoi : 10 courriels", sans_origine(out))
        rc, out, err = self.lancer("--no-prompt", "--details")
        self.assertIn("À : jean.dupont@exemple.org — cause", out)
        self.assertNotIn("(adresses masquées", out)

    def test_aucun_courriel_en_echec(self):
        self.donnees([])
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, err)
        self.assertIn("0 en échec d'envoi", out)
        self.assertIn("Aucun courriel en échec d'envoi.", out)
        self.assertNotIn("Renvoyer", out)

    def test_sans_la_base_de_diagnostics_la_liste_reste_donnee(self):
        os.remove(self.path("prog", "app-log-check.py"))
        rc, out, err = self.lancer("--no-prompt")
        self.assertEqual(rc, 0, err)
        self.assertIn("« Bienvenue sur la plateforme »", out)
        self.assertIn("cause : SMTPDataError: (452, b'4.4.5 Maximum number of messages", " ".join(out.split()))      # without the useless preamble

    # --- le menu de renvoi ---------------------------------------------------------------------------------------------
    def menu(self, reponses, *args, colonnes=0):
        sortie, _ = self.run_pty(["python3", self.prog, *args], reponses, colonnes=colonnes)
        self.assertNotIn("Traceback", sortie, sortie)
        return sortie

    def test_menu_tous(self):
        sortie = self.menu([(b"[N] aucun : ", b"t\n", 0.1)])
        self.assertIn("Renvoyer ces 5 courriels ?", sortie)
        self.assertIn("[t] tous (5)   [l] les 5 plus anciens   [c] choisir un par un   [N] aucun :", sortie)
        self.assertEqual(self.ids_remis(), [7171, 7404, 7405, 7406, 7500])
        self.assertIn("5 courriels remis à l'état « En attente » : #7171, #7404, #7405, #7406, #7500.", sortie)
        self.assertIn("Mail: Email Queue Manager", sortie)
        with open(self.path("journal-renvois.log")) as f:                                      # each resend is logged
            self.assertRegex(f.read(), r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\tlinux_meetup_odoo_18\t5\t7171,7404,7405,7406,7500\n$")

    def test_menu_lot_des_plus_anciens(self):
        sortie = self.menu([(b"[N] aucun : ", b"l\n", 0.1)], "--batch", "2")
        self.assertIn("[l] les 2 plus anciens", sortie)
        self.assertEqual(self.ids_remis(), [7171, 7404])

    def test_menu_un_par_un(self):
        sortie = self.menu([(b"[o/N/q] : ", b"o\n", 0.05)] * 0 + [(b"[N] aucun : ", b"c\n", 0.1), (b"#7171", b"n\n", 0.1), (b"#7404", b"o\n", 0.1),
                                                                  (b"#7405", b"\n", 0.1), (b"#7406", b"o\n", 0.1), (b"#7500", b"q\n", 0.1)])
        self.assertIn("renvoyer ? [o/N/q] :", sortie)
        self.assertEqual(self.ids_remis(), [7404, 7406])
        self.assertIn("2 courriels remis", sortie)

    def test_menu_un_par_un_dit_a_qui_est_destine_chaque_courriel(self):
        """Les titres se ressemblent (« Rapport de sondage » ×5) : chaque question dit À QUI le courriel est destiné — masqué comme la liste, entier avec --details."""
        reponses = [(b"[N] aucun : ", b"c\n", 0.1), (b"[o/N/q] :", b"q\n", 0.1)]      # attend l'invite de la question (la liste affiche aussi « #7171 »)
        sortie = " ".join(self.menu(reponses, colonnes=200).split())      # invite longue : terminal large (sinon readline coupe le mot)
        self.assertIn(f"#7171 {heure(T0 - 86400 * 20)} « Invitation à l'événement » → à : x***@exemple.fr — expéditeur refusé (550) — renvoyer ? [o/N/q] :", sortie)
        sortie = " ".join(self.menu(reponses, "--details", colonnes=200).split())
        self.assertIn("« Invitation à l'événement » → à : x@exemple.fr — expéditeur refusé (550) — renvoyer ? [o/N/q] :", sortie)
        self.assertNotIn("x***@", sortie)
        invites = [(b"[o/N/q] :", b"n\n", 0.1)] * 4 + [(b"[o/N/q] :", b"q\n", 0.1)]          # 5 courriels : une invite chacun (on répond à l'invite, pas au n° de la liste)
        sortie = " ".join(self.menu([(b"[N] aucun : ", b"c\n", 0.1)] + invites, colonnes=200).split())
        self.assertIn("→ à : j***@exemple.org — limite de messages par connexion (452)", sortie)
        self.assertIn("→ à : a***@exemple.org, s***@exemple.org — limite", sortie)               # plusieurs destinataires : tous
        self.assertIn("« Rappel » → à : (aucun destinataire noté) —", sortie)
        self.assertNotIn("jean.dupont", sortie)

    def test_menu_aucun_ne_modifie_rien(self):
        for reponse in (b"\n", b"n\n", b"x\n"):
            self.menu([(b"[N] aucun : ", reponse, 0.1)])
        self.assertEqual(self.appels("UPDATE"), [])
        self.assertFalse(os.path.exists(self.path("journal-renvois.log")))
        self.assertIn("Aucun courriel renvoyé.", self.menu([(b"[N] aucun : ", b"\n", 0.1)]))

    def test_no_prompt_meme_sur_un_terminal(self):
        sortie = self.menu([], "--no-prompt")
        self.assertNotIn("[N] aucun", sortie)
        self.assertEqual(self.appels("UPDATE"), [])

    # --- sans terminal : --resend --yes ----------------------------------------------------------------------------------
    def test_resend_yes_sans_question_et_jamais_sans_yes(self):
        self.lancer("--resend")
        self.lancer("--yes")
        self.assertEqual(self.appels("UPDATE"), [], "ni --resend seul ni --yes seul ne renvoient")
        rc, out, err = self.lancer("--resend", "--yes", "--batch", "2")
        self.assertEqual(self.ids_remis(), [7171, 7404], "--batch N : seulement les N plus anciens")
        rc, out, err = self.lancer("--resend", "--yes")
        self.assertEqual(self.ids_remis(), [7171, 7404, 7405, 7406, 7500])
        self.assertIn("5 courriels remis à l'état « En attente »", out)

    def test_courriel_deja_renvoye_ou_supprime_est_ignore(self):
        self.donnees(COURRIELS, deja=(7404, 7500))                                              # no longer failing at the time of writing
        rc, out, err = self.lancer("--resend", "--yes")
        self.assertIn("3 courriels remis à l'état « En attente » : #7171, #7405, #7406.", out)
        self.assertIn("2 ignorés : plus en échec d'envoi (déjà renvoyés ou supprimés) : #7404, #7500.", out)

    # --- avertissements ----------------------------------------------------------------------------------------------------
    def test_avertissement_cause_permanente(self):
        rc, out, err = self.lancer("--resend", "--yes")
        a = " ".join(out.split())
        self.assertIn("[ATTN] 1 courriels ont une cause PERMANENTE (expéditeur refusé (550)) : ils échoueront de nouveau tant que le réglage n'est pas corrigé", a)
        self.assertIn("app-log-check.py, section [5]", a)
        self.assertNotIn("mail.session.batch.size", a, "5 courriels : pas d'avertissement sur la limite par connexion")

    def test_avertissement_limite_de_messages_par_connexion(self):
        douze = [(8000 + i, T0 + i, "Bienvenue", "p@exemple.org", RAISON_452) for i in range(12)]
        self.donnees(douze)
        a = " ".join(self.lancer("--no-prompt")[1].split())
        self.assertIn("[ATTN] mail.session.batch.size est non défini", a)                       # also in list-only mode: to know BEFORE resending
        a = " ".join(self.lancer("--resend", "--yes")[1].split())
        self.assertIn("[ATTN] mail.session.batch.size est non défini : Odoo enverra ces 12 courriels sur UNE seule connexion SMTP", a)
        self.assertIn("renvoyer par lots (choix « l »)", a)
        self.assertNotIn("PERMANENTE", a)
        self.postgresql(parametres="mail.session.batch.size\x1f10\n")
        a = " ".join(self.lancer("--resend", "--yes")[1].split())
        self.assertNotIn("[ATTN]", a, "paramètre déjà réglé à 10 : pas d'avertissement")
        self.postgresql(parametres="mail.session.batch.size\x1f500\n")
        a = " ".join(self.lancer("--resend", "--yes")[1].split())
        self.assertIn("mail.session.batch.size est défini à 500", a)

    # --- security of the queries ----------------------------------------------------------------------------------------------
    def test_lecture_seule_pour_la_liste_ecriture_gardee_pour_le_renvoi(self):
        self.lancer("--resend", "--yes")
        lectures = [a for a in self.appels() if "UPDATE" not in a]
        self.assertTrue(lectures)
        for a in lectures:
            self.assertIn("PGOPTIONS=-c default_transaction_read_only=on", a, a)               # PostgreSQL would refuse any write
        (ecriture,) = self.appels("UPDATE mail_mail")
        self.assertNotIn("PGOPTIONS", ecriture)
        self.assertIn("SET state = 'outgoing'", ecriture)
        self.assertIn("AND state = 'exception' RETURNING id", ecriture)                         # only what is STILL failing
        self.assertRegex(ecriture, r"IN \(7171, 7404, 7405, 7406, 7500\)")
        self.assertNotRegex(" ".join(self.appels()), r"smtp_pass|smtp_user|DELETE|DROP|TRUNCATE")
        self.assertNotIn("mail_message SET", ecriture)

    def test_postgresql_inaccessible_ou_base_inconnue(self):
        self.mock("runuser", "exit 1")
        rc, out, err = self.lancer("--resend", "--yes")
        self.assertEqual(rc, 2)
        self.assertIn("ERREUR : PostgreSQL inaccessible (commande psql absente, ou root requis : relancer en root).", err)
        rc, out, err = self.lancer("--db", "inconnue", "--resend", "--yes")
        self.assertEqual(rc, 2)
        self.assertIn("ERREUR : base inconnue illisible", err)
        self.postgresql(bases="", avec_courriels=())
        rc, out, err = self.lancer()
        self.assertEqual(rc, 2)
        self.assertIn("Aucune base Odoo (table des courriels mail_mail) trouvée", err)

    def test_plusieurs_bases_exigent_db_pour_un_renvoi_sans_question(self):
        self.postgresql(avec_courriels=("linux_meetup_odoo_18", "autre_base"))
        rc, out, err = self.lancer("--no-prompt")
        self.assertIn("base linux_meetup_odoo_18", out)
        self.assertIn("base autre_base", out)
        rc, out, err = self.lancer("--resend", "--yes")
        self.assertEqual(rc, 2)
        self.assertIn("plusieurs bases (linux_meetup_odoo_18, autre_base) : préciser --db NOM", err)
        self.assertEqual(self.appels("UPDATE"), [])
        rc, out, err = self.lancer("--resend", "--yes", "--db", "autre_base")
        self.assertEqual(rc, 0, err)
        self.assertIn("psql -d autre_base -v ON_ERROR_STOP=1 -tA -c UPDATE mail_mail", self.appels("UPDATE")[0])

    def test_journal_des_renvois_inscriptible_ou_non(self):
        rc, out, err = self.lancer("--resend", "--yes", env_extra={"ODOO_MAIL_RETRY_LOG": self.path("journal-renvois.log", "x")})
        self.assertEqual(rc, 0, err)                                                            # "folder" that is a file: the resend succeeds anyway
        self.assertIn("5 courriels remis", out)

    # --- configuration ---------------------------------------------------------------------------------------------------
    def test_configuration_fichiers_lus_et_ligne_de_commande_prioritaire(self):
        self.write("etc-default-vide/odoo-mail-retry.conf", "# commentaire\nDAYS=7\nBATCH=3\nBIDON=1\nDAYS=abc\n")
        self.write("maison/.odoo-mail-retry.conf", 'BATCH="4"\n')
        env = {}
        rc, out, err = self.lancer("--no-prompt", env_extra=env)
        self.assertIn(f"Configuration lue : {self.path('etc-default-vide', 'odoo-mail-retry.conf')}, puis {self.path('maison', '.odoo-mail-retry.conf')} (le dernier l'emporte)\n"
                      "  Options : --lang fr · courriels des 7 derniers jours · lot de renvoi : 4 courriels", sans_origine(sans_date(out)))
        self.assertIn("ligne ignorée « BIDON=1 »", err)
        self.assertIn("ligne ignorée « DAYS=abc »", err)
        self.assertIn("interval '7 days'", " ".join(self.appels("string_agg")))
        self.assertIn("7 derniers jours", out)
        self.lancer("--no-prompt", "--days", "2", env_extra=env)
        self.assertIn("interval '2 days'", self.appels("string_agg")[-1])
        # -c/--config : ce fichier SEUL (ni /etc/default ni ~), qui doit exister
        rc, out, err = self.lancer("--no-prompt", "-c", self.path("maison", ".odoo-mail-retry.conf"), env_extra=env)
        self.assertIn(f"Configuration lue : {self.path('maison', '.odoo-mail-retry.conf')} (demandé par -c/--config : aucun autre fichier n'est lu)", sans_date(out))
        self.assertIn("lot de renvoi : 4 courriels", out)
        self.assertIn("courriels des 30 derniers jours", out)                                  # DAYS=7 of the system file is no longer read
        rc, out, err = self.lancer("--config", self.path("inexistant.conf"))
        self.assertEqual(rc, 2)
        self.assertIn(f"ERREUR : fichier de config introuvable : {self.path('inexistant.conf')}", err)
        self.assertEqual(self.appels("UPDATE"), [])
        rc, out, err = self.lancer("--days", "0")
        self.assertEqual(rc, 2)
        self.assertIn("--days, --batch et --sent doivent être des nombres positifs", err)


class AdressesInvalides(_Base):
    """1.10 : inscriptions dont l'adresse courriel est invalide (« marieb.essai@gmail'com ») : liste, correction suggérée, correction de l'inscription et du contact
    en UNE transaction, courriels en échec renvoyés ; adresse invalide d'un courriel en échec signalée."""
    INSCRIPTIONS = [   # id, instant, event, name, e-mail, state, contact, contact's e-mail, Odoo identifier
        (1965, T0, "Journée portes ouvertes sur Linux 2026", "Marie B.", "marieb.essai@gmail'com", "open", 4, "marieb.essai@gmail'com", "marieb.essai@gmail'com"),
        (1966, T0 + 60, "Pause café Linux", "Jean", "jean@gmial.com", "open", 0, "", ""),
        (1967, T0 + 90, "Pause café Linux", "Ana", "ana@videotron.ca", "open", 0, "", ""),
        (1968, T0 + 99, "Pause café Linux", "Sans espoir", "pas une adresse", "open", 0, "", ""),
    ]

    def setUp(self):
        super().setUp()
        self.write("inscriptions.txt", "".join(SEP.join(map(str, c)) + "\n" for c in self.INSCRIPTIONS))
        self.donnees([(7171, T0, "Votre inscription", "marieb.essai@gmail'com", "Invalid recipient")])

    def test_liste_des_adresses_invalides_avec_correction_suggeree(self):
        rc, out, err = self.lancer("--invalid-emails", "--no-prompt", "--details")
        self.assertEqual(rc, 0, err)
        self.assertIn("Adresses courriel invalides des inscriptions aux événements — base linux_meetup_odoo_18 — 3 inscriptions", out)
        texte = " ".join(out.split())
        self.assertIn("Inscription #1965", texte)
        self.assertIn("Adresse : marieb.essai@gmail'com — caractère invalide dans le nom de domaine : ' — correction suggérée : marieb.essai@gmail.com", texte)
        self.assertIn("compte Odoo : marieb.essai@gmail'com (identifiant non modifié)", texte)
        self.assertIn("jean@gmial.com — faute de frappe probable dans le domaine (gmial.com) — correction suggérée : jean@gmail.com", texte)
        self.assertIn("pas une adresse — espace dans l'adresse — aucune correction automatique : à saisir", texte)
        self.assertNotIn("ana@videotron.ca", texte)
        self.assertNotIn("Courriels non envoyés", out)                                  # --invalid-emails : seulement les inscriptions
        self.assertIn("Pour les corriger : relancer sur un terminal (menu), ou avec --fix --yes", out)
        self.assertEqual(self.appels("UPDATE"), [])
        rc, out, err = self.lancer("--invalid-emails", "--no-prompt")
        self.assertIn("m***@gmail'com", out)                                            # addresses hidden by default
        self.assertNotIn("marieb.essai@", out)

    def test_courriel_en_echec_vers_une_adresse_invalide(self):
        rc, out, err = self.lancer("--no-prompt", "--details")
        texte = " ".join(out.split())
        self.assertIn("cause : adresse invalide (caractère invalide dans le nom de domaine : '), suggérée : marieb.essai@gmail.com — PERMANENTE", texte)
        self.assertIn("1 courriels adressés à une adresse INVALIDE : renvoyés tels quels, ils échoueront de nouveau", texte)
        self.assertIn("Par cause : adresse invalide ×1", texte)

    def test_fix_yes_corrige_inscription_contact_et_renvoie(self):
        rc, out, err = self.lancer("--invalid-emails", "--fix", "--yes", "--details")
        self.assertEqual(rc, 0, err)
        texte = " ".join(out.split())
        self.assertIn("Inscription #1965 — marieb.essai@gmail'com → marieb.essai@gmail.com — inscription corrigée, contact corrigée, 1 courriels en échec remis « En attente »", texte)
        self.assertIn("Le compte Odoo garde son identifiant « marieb.essai@gmail'com »", texte)
        self.assertIn("Inscription #1966 — jean@gmial.com → jean@gmail.com", texte)
        self.assertIn("2 adresses corrigées ; 1 sans correction automatique", texte)
        maj = self.appels("UPDATE event_registration")
        self.assertEqual(len(maj), 2)
        self.assertIn("psql -1 ", maj[0])                                               # une seule transaction
        self.assertIn("WHERE id = 1965 AND email = 'marieb.essai@gmail''com'", maj[0])    # old value rechecked; apostrophe doubled
        self.assertIn("UPDATE res_partner SET email = 'marieb.essai@gmail.com', email_normalized = lower('marieb.essai@gmail.com')", maj[0])
        self.assertIn("WHERE id = 4 AND email = 'marieb.essai@gmail''com'", maj[0])
        self.assertIn("UPDATE mail_mail SET state = 'outgoing'", maj[0])
        self.assertIn("WHERE id IN (7171) AND state = 'exception'", maj[0])
        self.assertNotIn("UPDATE res_partner", maj[1])                                  # registration without contact: contact never touched
        self.assertNotIn("UPDATE res_users", "\n".join(self.appels()))                 # identifier never changed
        journal = open(self.env["ODOO_MAIL_RETRY_LOG"]).read()
        self.assertIn("fix-email\tregistration=1965\tpartner=4\tmarieb.essai@gmail'com -> marieb.essai@gmail.com", journal)

    def test_menu_une_par_une_accepter_saisir_passer(self):
        """Menu sur un vrai terminal : [c] une par une — Entrée accepte la suggestion, une adresse saisie remplace (casse conservée), s passe."""
        texte, n = self.run_pty(["python3", self.prog, "--details"],
                                [(b"aucune : ", b"c\r", 0.2), (b"#1965", b"\r", 0.2), (b"#1966", b"Jean.X@Videotron.ca\r", 0.2), (b"#1968", b"s\r", 0.2),
                                 (b"[N] aucun", b"\r", 0.3)])
        self.assertGreaterEqual(n, 4, texte)
        maj = self.appels("UPDATE event_registration")
        self.assertEqual(len(maj), 2, texte)
        self.assertIn("SET email = 'marieb.essai@gmail.com'", maj[0])
        self.assertIn("SET email = 'Jean.X@Videotron.ca'", maj[1])
