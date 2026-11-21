"""app-log-live.py : bannissements lus dans le journal de fail2ban (1.151).

Une adresse bannie par fail2ban après une attaque doit apparaître dans le tableau de bord, même si le bannissement
n'est plus actif au moment de l'affichage : la lecture du journal donne l'heure et la jail du bannissement.
Partie statique (le texte du programme) et partie fonctionnelle (le programme est chargé, sans être lancé, sur un journal d'exemple).
"""
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
import importlib.util
import os
import tempfile
import time
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL_EXEMPLE = """\
2026-11-02 07:41:22,901 fail2ban.filter [1201]: INFO [nginx-sensitive-files] Found 34.173.12.79 - 2026-11-02 07:41:22
2026-11-02 07:41:23,410 fail2ban.actions [1201]: NOTICE [nginx-sensitive-files] Ban 34.173.12.79
2026-11-02 07:41:23,415 fail2ban.actions [1201]: NOTICE [nginx-blocked-probes] Ban 34.173.12.79
2026-11-02 08:00:00,000 fail2ban.actions [1201]: NOTICE [nginx-catchall] Unban 10.0.0.1
2026-11-02 09:00:00,000 fail2ban.actions NOTICE [nginx-blocked-probes] Ban 2001:db8::5
"""


def lire(chemin):
    with open(os.path.join(RACINE, chemin), encoding="utf-8") as f:
        return f.read()


def charger_programme(journal):
    """Charge app-log-live.py comme module, en pointant le journal fail2ban vers « journal » (lu à la définition de la classe)."""
    os.environ["APP_LOG_LIVE_FAIL2BAN_LOG"] = journal
    try:
        spec = importlib.util.spec_from_file_location("app_log_live_test", os.path.join(RACINE, "app-log-live.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        del os.environ["APP_LOG_LIVE_FAIL2BAN_LOG"]


class LectureJournalFail2banStatique(unittest.TestCase):
    def setUp(self):
        self.source = lire("app-log-live.py")

    def test_journal_lu_par_defaut_et_par_variable(self):
        """Le journal est /var/log/fail2ban.log, modifiable par APP_LOG_LIVE_FAIL2BAN_LOG (documenté dans le CHANGELOG)."""
        self.assertIn('os.environ.get("APP_LOG_LIVE_FAIL2BAN_LOG", "/var/log/fail2ban.log")', self.source)

    def test_bannissements_relus_au_demarrage_et_toutes_les_60_secondes(self):
        """La lecture du journal fait partie de refresh(), donc du démarrage et de la relecture périodique."""
        self.assertIn("journal = self.read_fail2ban_journal(unbans)", self.source)        # 1.205: the Unban lines in the same reading
        self.assertIn("self.unbans = unbans", self.source)
        self.assertIn("self.f2b, self.cs, self.pf, self.journal = f2b, cs, pf, journal", self.source)

    def test_etiquette_fail2ban_sur_les_lignes_bannies_apres_la_requete(self):
        """Une ligne d'une adresse bannie après cette requête reçoit « [banned: fail2ban HEURE] » (ou [BANNIE] pour nginx)."""
        self.assertIn("history = banned_ips.ban_before(ips0[0][2], L.instant)", self.source)
        self.assertIn('f"[banned: fail2ban {clock_of(history[0])}]"', self.source)

    def test_resume_des_adresses_suspectes_indique_le_bannissement(self):
        """Le résumé « by address » indique l'heure et les jails du bannissement fail2ban."""
        self.assertIn("+ self.fail2ban_note(ip)", self.source)
        self.assertIn("stats.ban_info = banned_ips.first_ban_of", self.source)

    def test_aucun_bannissement_declenche_par_la_lecture(self):
        """Lire le journal ne modifie rien : aucun appel à fail2ban-client set, unbanip ou banip dans le code de lecture."""
        lecture = self.source[self.source.index("def read_fail2ban_journal"):self.source.index("def read_fail2ban():")]
        self.assertNotIn("banip", lecture)
        self.assertNotIn("unbanip", lecture)
        self.assertNotIn("fail2ban-client", lecture)


class LectureJournalFail2banFonctionnelle(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp(prefix="test-rlq-f2b-")
        self.journal = os.path.join(self.dossier, "fail2ban.log")
        with open(self.journal, "w", encoding="utf-8") as f:
            f.write(JOURNAL_EXEMPLE)
        self.programme = charger_programme(self.journal)
        self.bans = self.programme.Bans()
        self.bans.journal = self.programme.Bans.read_fail2ban_journal()
        self.instant_ban = time.mktime(time.strptime("2026-11-02 07:41:23", "%Y-%m-%d %H:%M:%S"))

    def tearDown(self):
        for nom in os.listdir(self.dossier):
            os.remove(os.path.join(self.dossier, nom))
        os.rmdir(self.dossier)

    def test_seuls_les_bannissements_sont_lus(self):
        """Les lignes « Found » et « Unban » sont ignorées ; les deux bannissements d'une même adresse sont gardés."""
        self.assertEqual(len(self.bans.journal[self.programme.ipaddress.ip_address("34.173.12.79")]), 2)
        self.assertNotIn(self.programme.ipaddress.ip_address("10.0.0.1"), self.bans.journal)

    def test_adresse_ipv6_lue(self):
        self.assertIn(self.programme.ipaddress.ip_address("2001:db8::5"), self.bans.journal)

    def test_ligne_avant_le_bannissement_non_etiquetee(self):
        self.assertIsNone(self.bans.ban_before("34.173.12.79", self.instant_ban - 1))

    def test_ligne_apres_le_bannissement_etiquetee_avec_la_jail(self):
        epoque, jail = self.bans.ban_before("34.173.12.79", self.instant_ban + 5)
        self.assertEqual(epoque, self.instant_ban)
        self.assertEqual(jail, "nginx-sensitive-files")         # deux jails dans la même seconde : le tri (heure, nom) garde la plus grande

    def test_bannissement_trop_ancien_non_etiquete(self):
        self.assertIsNone(self.bans.ban_before("34.173.12.79", self.instant_ban + self.programme.Bans.BAN_LABEL_WINDOW + 60))

    def test_premier_bannissement_et_jails(self):
        epoque, jails = self.bans.first_ban_of("34.173.12.79")
        self.assertEqual(epoque, self.instant_ban)
        self.assertEqual(jails, ["nginx-blocked-probes", "nginx-sensitive-files"])

    def test_adresse_inconnue_et_entree_invalide(self):
        self.assertIsNone(self.bans.first_ban_of("8.8.8.8"))
        self.assertIsNone(self.bans.ban_before("pas-une-adresse", self.instant_ban))

    def test_journal_illisible_donne_none(self):
        """Sans journal lisible (root requis, pas de fail2ban) : None, jamais d'erreur."""
        absent = charger_programme(os.path.join(self.dossier, "absent.log"))
        self.assertIsNone(absent.Bans.read_fail2ban_journal())


class LeveeDeBannissement1205(unittest.TestCase):
    """1.205 : une ligne « Unban » (fin du bannissement ou levée par nginx-log-audit.sh --unban) arrête l'étiquette « banni ».
    2026-11-20 : 132.211.165.182 banni à 16:15:42, débanni à 17:25, encore affiché « [banni : fail2ban 16:15:42] » à 21:01."""
    JOURNAL = """\
2026-11-20 16:15:42,100 fail2ban.actions [900]: NOTICE [nginx-badrequests] Ban 132.211.165.182
2026-11-20 17:25:10,200 fail2ban.actions [900]: NOTICE [nginx-badrequests] Unban 132.211.165.182
2026-11-20 18:00:00,000 fail2ban.actions [900]: NOTICE [nginx-badrequests] Ban 198.51.100.7
2026-11-20 18:00:00,500 fail2ban.actions [900]: NOTICE [nginx-sensitive-files] Ban 198.51.100.7
2026-11-20 18:30:00,000 fail2ban.actions [900]: NOTICE [nginx-badrequests] Unban 198.51.100.7
2026-11-20 19:00:00,000 fail2ban.actions [900]: NOTICE [nginx-catchall] Ban 203.0.113.9
2026-11-20 19:10:00,000 fail2ban.actions [900]: NOTICE [nginx-catchall] Unban 203.0.113.9
2026-11-20 19:20:00,000 fail2ban.actions [900]: NOTICE [nginx-catchall] Ban 203.0.113.9
"""

    def setUp(self):
        self.dossier = tempfile.mkdtemp(prefix="test-rlq-f2b-")
        self.journal = os.path.join(self.dossier, "fail2ban.log")
        with open(self.journal, "w", encoding="utf-8") as f:
            f.write(self.JOURNAL)
        self.programme = charger_programme(self.journal)
        self.bans = self.programme.Bans()
        self.bans.unbans = {}
        self.bans.journal = self.programme.Bans.read_fail2ban_journal(self.bans.unbans)

    def tearDown(self):
        for nom in os.listdir(self.dossier):
            os.remove(os.path.join(self.dossier, nom))
        os.rmdir(self.dossier)

    @staticmethod
    def t(texte):
        return time.mktime(time.strptime("2026-11-20 " + texte, "%Y-%m-%d %H:%M:%S"))

    def test_debanni_n_est_plus_etiquete(self):
        self.assertIsNotNone(self.bans.ban_before("132.211.165.182", self.t("16:30:00")))      # banned at that time
        self.assertIsNone(self.bans.ban_before("132.211.165.182", self.t("21:01:39")))         # unbanned at 17:25: no label any more

    def test_unban_lu_a_part_journal_des_bans_inchange(self):
        ip = self.programme.ipaddress.ip_address("132.211.165.182")
        self.assertEqual(len(self.bans.journal[ip]), 1)
        self.assertEqual(len(self.bans.unbans[ip]), 1)
        self.assertEqual(self.bans.first_ban_of("132.211.165.182")[1], ["nginx-badrequests"])     # summary: first ban unchanged

    def test_une_seule_jail_levee_l_autre_reste(self):
        epoque, jail = self.bans.ban_before("198.51.100.7", self.t("18:45:00"))
        self.assertEqual(jail, "nginx-sensitive-files")

    def test_banni_de_nouveau_apres_la_levee(self):
        self.assertIsNone(self.bans.ban_before("203.0.113.9", self.t("19:15:00")))
        epoque, jail = self.bans.ban_before("203.0.113.9", self.t("19:25:00"))
        self.assertEqual(epoque, self.t("19:20:00"))

    def test_sans_dictionnaire_des_levees_comportement_d_avant(self):
        journal = self.programme.Bans.read_fail2ban_journal()
        self.assertEqual(len(journal[self.programme.ipaddress.ip_address("198.51.100.7")]), 2)


if __name__ == "__main__":
    unittest.main()
