"""apps/_record.py et touche R d'app-log-live.py : archive .tar.xz d'un test (fenêtre de temps, bruit retiré, anonymisation, sources absentes tolérées)
et marque REC à la colonne $COLUMNS - 4."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs).
ENVIRONNEMENT = "commun"
import importlib.util
import os
import tarfile
import tempfile
import time
import unittest

from helpers import SCRIPTS_DIR


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENREGISTREMENT = charger("_record", os.path.join(SCRIPTS_DIR, "apps", "_record.py"))
PROGRAMME = "app-log-live.py"                               # nom du programme (lu par stats_runner)
APP = charger("app_log_live_rec", os.path.join(SCRIPTS_DIR, "app-log-live.py"))


def faux_ss(commande, delai=10):
    if commande[0] == "ss":
        return 0, "ESTAB 0 0 10.0.0.2:443 11.97.88.180:55555 users:((\"nginx\",pid=1))\n"
    if commande[0] == "journalctl":
        return 0, "2026-10-20T22:00:00 odoo GET /survey/start/0b9c2a3e-1111-2222-3333-444455556666 de 11.42.88.181\n"
    return 0, "ActiveState=active\n"


class Enregistrement(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp(prefix="test-rlq-record-")
        self.journal = os.path.join(self.dossier, "access.log")
        with open(self.journal, "w") as f:
            f.write("ancienne ligne 11.97.88.180\n")
        # psql est retiré du PATH des tests (COMMANDES_SYSTEME) : on simule sa présence ici, sans dépendre du PATH du processus
        import shutil as _shutil
        from unittest import mock
        reel = _shutil.which
        patch = mock.patch.object(ENREGISTREMENT.shutil, "which", side_effect=lambda cmd, *a, **k: "/usr/bin/psql" if cmd == "psql" else reel(cmd, *a, **k))
        patch.start()
        self.addCleanup(patch.stop)

    def test_refus_sans_psql(self):
        """1.2 : sans psql, l'enregistrement est refusé avec un message clair (les échantillons PostgreSQL sont obligatoires)."""
        from unittest import mock
        rec = ENREGISTREMENT.Recorder(os.path.join(self.dossier, "archives"), label="sans psql", query=lambda base, sql: [["1"]], databases=lambda: ["prod"],
                                      service="odoo.service", log_files=[self.journal], run=faux_ss, sample_s=1, version="1.93", owner=False)
        with mock.patch.object(ENREGISTREMENT.shutil, "which", side_effect=lambda cmd, *a, **k: None if cmd == "psql" else None):
            with self.assertRaisesRegex(OSError, "psql"):
                rec.start()

    def archive(self, lignes, etapes=(), **options):
        def requete(base, sql):
            if "to_regclass" in sql:
                return [["t"] * len(ENREGISTREMENT.TABLES)]
            if "pg_stat_activity" in sql:
                return [["123", "odoo", "active", "", "3", "1", "INSERT INTO crm_lead (email) VALUES ('jean@exemple.org')"]]
            return [["x", "1"]]
        rec = ENREGISTREMENT.Recorder(os.path.join(self.dossier, "archives"), label="Sondage abandonné !", query=requete, databases=lambda: ["prod"],
                                      service="odoo.service", log_files=[self.journal, os.path.join(self.dossier, "absent.log")], run=faux_ss,
                                      sample_s=1, version="1.93", owner=False, **options)
        rec.start()
        with open(self.journal, "a") as f:
            f.write("nouvelle 11.97.88.180 GET /event/x/my_tickets?tickets_hash=09e189cd69a70f2dcfd9a3af407a5485221a12 jean@exemple.org\n")
        for ligne, categorie in lignes:
            rec.add(ligne, categorie)
        for genre, texte in etapes:                       # 1.1: N key — steps ("debut" = start, "fin" = end)
            rec.step_start(texte) if genre == "debut" else rec.step_end()
        time.sleep(1.2)
        resultat = rec.stop(reason="key", wait=True)
        self.assertIsNone(resultat["error"], resultat)
        return resultat

    def contenu(self, resultat):
        textes = {}
        with tarfile.open(resultat["path"]) as t:
            for membre in t.getmembers():
                if membre.isfile():
                    textes[membre.name.split("/", 1)[1]] = t.extractfile(membre).read().decode("utf-8", "replace")
        return textes

    def test_archive_avec_fenetre_bruit_retire_et_anonymisation(self):
        resultat = self.archive([("21:59:16 CA 11.97.88.180 POST /event/x/registration/new", "kept"),
                                 ("robot 66.249.66.1 GET /", "robot"),
                                 ("POST /web/assets/1/web.js", "static")])
        self.assertTrue(resultat["path"].endswith(".tar.xz"))
        self.assertIn("sondage-abandonne", os.path.basename(resultat["path"]))
        self.assertEqual(resultat["counts"]["kept"], 1)
        textes = self.contenu(resultat)
        for nom in ("README.txt", "records.log", "stream-all.log", "raw/access.log", "network/ss.log", "db/activity-prod.log", "context/program.txt"):
            self.assertIn(nom, textes, nom)
        self.assertNotIn("11.97.88.180", "".join(textes.values()), "adresse réelle dans l'archive")
        self.assertNotIn("jean@exemple.org", "".join(textes.values()), "courriel réel dans l'archive")
        self.assertNotIn("09e189cd69a70f2dcfd9a3af407a5485221a12", "".join(textes.values()), "jeton dans l'archive")
        self.assertNotIn("0b9c2a3e-1111-2222-3333-444455556666", "".join(textes.values()), "jeton de sondage dans l'archive")
        self.assertNotIn("INSERT INTO crm_lead (email) VALUES ('jean", "".join(textes.values()), "littéral SQL dans l'archive")
        self.assertIn("[robot]", textes["stream-all.log"])
        self.assertNotIn("[robot]", textes["records.log"])
        self.assertIn("registration/new", textes["records.log"])
        self.assertIn("Confidentialité", textes["README.txt"])
        self.assertIn("Sources absentes ou coupées", textes["README.txt"])
        self.assertIn("absent.log", textes["README.txt"])

    def test_etapes_debut_fin_dans_records_log_et_steps_txt(self):
        resultat = self.archive([("GET /event/x/registration/new 200", "kept"), ("GET /survey/start/x 200", "kept")],
                                etapes=[("debut", "inscription"), ("fin", None), ("debut", "sondage abandonné")])
        base = os.path.basename(resultat["path"])[:-len(".tar.xz")]
        with tarfile.open(resultat["path"]) as tar:
            def lire(nom):
                return tar.extractfile(f"{base}/{nom}").read().decode("utf-8")
            records, etapes, readme = lire("records.log"), lire("steps.txt"), lire("README.txt")
        self.assertIn("# STEP 1 START ", records)
        self.assertIn("STEP 1 END ", records)
        self.assertIn("STEP 2 START ", records)
        self.assertIn("(recording stopped)", records)          # the step still open at the stop is closed
        self.assertIn("inscription", etapes)
        self.assertIn("sondage abandonné", etapes)
        self.assertIn("steps.txt", readme)
        self.assertIn("Étapes           : 2", readme)

    def test_dossier_sudo_et_lien_symbolique_refuse(self):
        cible = os.path.join(self.dossier, "vrai")
        os.makedirs(cible)
        lien = os.path.join(self.dossier, "lien")
        os.symlink(cible, lien)
        rec = ENREGISTREMENT.Recorder(lien, run=faux_ss, owner=False)
        with self.assertRaises(OSError):
            rec.start()

    def test_dossier_par_defaut_sous_sudo(self):
        import pwd
        self.assertEqual(ENREGISTREMENT.default_folder(env={"APP_LOG_LIVE_RECORD_DIR": "/srv/x"}, euid=0), "/srv/x")
        try:
            accueil = pwd.getpwnam("nobody").pw_dir
        except KeyError:
            self.skipTest("no account nobody")
        dossier = ENREGISTREMENT.default_folder(env={"SUDO_USER": "nobody"}, euid=0)
        self.assertEqual(dossier, os.path.join(accueil, "app-log-live-records"))
        self.assertEqual(ENREGISTREMENT.default_folder(env={}, euid=1000, journal_folder=None).endswith(os.path.join("app-log-live", "records")), True)

    def test_etiquette_en_nom_de_fichier(self):
        self.assertEqual(ENREGISTREMENT.slug("Sondage abandonné !"), "sondage-abandonne")
        self.assertEqual(ENREGISTREMENT.slug("  ../../etc  "), "etc")

    def test_repli_sans_anonymiseur_masque_quand_meme(self):
        masque = ENREGISTREMENT.FallbackMask()
        texte = masque("de 11.97.88.180 à jean@exemple.org")
        self.assertNotIn("11.97.88.180", texte)
        self.assertNotIn("jean@exemple.org", texte)

    def test_marque_rec_a_la_colonne_columns_moins_quatre(self):
        for texte in ("court", "x" * 70, "y" * 200, "", "z" * 56):
            with self.subTest(texte=texte[:10]):
                sortie = APP.rec_mark(texte, 60)
                self.assertTrue(APP.ANSI_RE.sub("", sortie).endswith("REC"), sortie[-20:])
                self.assertEqual((APP.display_width(sortie) - 3) % 60, 56, sortie[-20:])     # REC starts at column $COLUMNS - 4 of its screen row

    def test_marque_rec_coupe_la_ligne_trop_large(self):
        self.assertNotIn("…", APP.ANSI_RE.sub("", APP.rec_mark("a" * 80, 60)))      # two rows: the marker fits on the second one, nothing cut
        sortie = APP.rec_mark("a" * 117, 60)                                             # the marker would run into the text: cut
        self.assertIn("…", APP.ANSI_RE.sub("", sortie))
        self.assertEqual((APP.display_width(sortie) - 3) % 60, 56)


if __name__ == "__main__":
    unittest.main()
