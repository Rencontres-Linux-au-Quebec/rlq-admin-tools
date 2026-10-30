"""odoo-backup.sh : sauvegarde et restauration au format d'Odoo (.zip ou .tar.xz), PostgreSQL simulé."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "odoo"   # sauvegarde d'Odoo (odoo-backup.sh : PostgreSQL d'Odoo)
import datetime
import json
import os
import subprocess
import unittest
import zipfile

from helpers import sans_origine, EnvTest, sans_date

FAUX_PSQL = r'''
tout="$*"
case "$tout" in
  *" -f "*) echo "$tout" >> "$D/psql.log"; exit 0 ;;
  *pg_database_size*) echo 1048576 ;;
  *"FROM pg_database WHERE datname"*)
      nom=$(printf '%s' "$tout" | sed -n "s/.*datname = '\([^']*\)'.*/\1/p")
      grep -qx "$nom" "$D/bases_existantes" 2>/dev/null && echo 1 ;;
  *"name = 'base'"*) echo 18.0.1.3 ;;
  *"SHOW server_version"*) echo "16.4 (Ubuntu 16.4-1)" ;;
  *"ORDER BY name"*) printf 'base=18.0.1.3\nweb=18.0.1.0\n' ;;
  *"count(*) FROM ir_module_module"*) echo 2 ;;
  *) echo base1 ;;
esac
'''


class OdooBackup(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("odoo-backup.sh")
        self.dest = os.path.dirname(self.path("sauvegardes", "x"))
        self.fsdir = os.path.dirname(self.path("filestores", "base1", "x"))
        for i in range(3):
            self.write(f"filestores/base1/ab/fichier{i}", f"contenu {i}\n")
        conf = self.write("odoo.conf", "[options]\ndb_user = odoo18\n")
        self.cfg = self.write("odoo-backup.conf", f"DEST={self.dest}\nDATABASES=base1\nFILESTORE_DIR={os.path.dirname(self.fsdir)}\n"
                                                 f"ODOO_CONF={conf}\nPG_USER=\n# commentaire\nINCONNUE=ignorée\n")
        self.env.update(ODOO_BACKUP_STATE_DIR=os.path.dirname(self.path("etat", "x")), D=self.d, TMPDIR=self.d)
        self.mock("pg_dump", 'echo "CREATE TABLE ir_module_module (id integer);"; echo "-- PostgreSQL database dump complete"')
        self.mock("psql", FAUX_PSQL)
        self.mock("createdb", 'echo "$*" >> "$D/createdb.log"')
        self.mock("dropdb", "exit 0")

    def lancer(self, *args):
        return self.run_cmd(["bash", self.prog, "--config", self.cfg] + list(args))

    def archives(self):
        d = os.path.join(self.dest, "base1")
        return sorted(f for f in os.listdir(d) if not f.endswith(".sha256") and not f.startswith(".")) if os.path.isdir(d) else []

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_zip_au_format_d_odoo(self):
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        (nom,) = self.archives()
        self.assertRegex(nom, r"^base1_\d{4}-\d{2}-\d{2}_\d{6}\.zip$")
        chemin = os.path.join(self.dest, "base1", nom)
        with zipfile.ZipFile(chemin) as z:
            noms = z.namelist()
            manifest = json.loads(z.read("manifest.json"))
        self.assertEqual(noms[:2], ["dump.sql", "manifest.json"])
        self.assertIn("filestore/ab/fichier2", noms)
        self.assertEqual(manifest["odoo_dump"], "1")
        self.assertEqual((manifest["db_name"], manifest["version"], manifest["major_version"], manifest["pg_version"]),
                         ("base1", "18.0", "18.0", "16.4"))
        self.assertEqual(manifest["version_info"], [18, 0, 0, "final", 0, ""])
        self.assertEqual(manifest["modules"], {"base": "18.0.1.3", "web": "18.0.1.0"})
        self.assertEqual(subprocess.run(["sha256sum", "-c", "--quiet", nom + ".sha256"], cwd=os.path.dirname(chemin)).returncode, 0)
        rc, out, err = self.lancer("--status")
        self.assertEqual(rc, 0, out)
        self.assertIn("base1 : dernière sauvegarde il y a 0 h", out)
        rc, out, err = self.lancer("--test-restore")
        self.assertEqual(rc, 0, out + err)
        self.assertRegex(out, r"base base1_restore_test_\d+ restaurée — 2 module\(s\) installé\(s\), 3 fichier\(s\) de filestore")

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_verbose_affiche_chaque_commande_externe(self):
        """2.x : odoo-backup.sh n'avait pas --verbose, que web-monitor.py lui transmet : chaque commande externe s'affiche."""
        rc, out, err = self.lancer("--verbose")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("+ psql -Atc", err)
        self.assertIn("+ pg_dump --no-owner -d base1", err)
        self.assertIn("+ python3 -", err)                                       # archive zip
        rc, out, err = self.lancer("--verbose", "--format", "tar.xz")
        self.assertIn("+ tar -cJf", err)
        self.assertNotIn("+ ", self.lancer()[2], "sans --verbose, aucune commande affichée")
        rc, out, err = self.run_cmd(["bash", self.prog, "--help"])
        self.assertIn("-v, --verbose", out)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_tar_xz_meme_contenu(self):
        rc, out, err = self.lancer("--format", "tar.xz")
        self.assertEqual(rc, 0, out + err)
        (nom,) = self.archives()
        self.assertTrue(nom.endswith(".tar.xz"))
        liste = subprocess.run(["tar", "-tJf", os.path.join(self.dest, "base1", nom)], capture_output=True, text=True).stdout.split()
        self.assertIn("dump.sql", liste)
        self.assertIn("manifest.json", liste)
        self.assertIn("filestore/ab/fichier1", liste)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_restauration_zip_et_tar_xz_sans_ecrasement(self):
        for fmt, cible in (("zip", "copie"), ("tar.xz", "copie2")):
            with self.subTest(format=fmt):
                self.lancer("--format", fmt)
                archive = os.path.join(self.dest, "base1", next(a for a in self.archives() if a.endswith(fmt)))
                rc, out, err = self.lancer("--restore", archive, "--db", cible)
                self.assertEqual(rc, 0, out + err)
                self.assertIn(f"--owner odoo18 {cible}", open(self.path("createdb.log")).read())
                self.assertIn('SET ROLE "odoo18"', open(self.path("psql.log")).read())
                self.assertEqual(len(os.listdir(os.path.join(os.path.dirname(self.fsdir), cible, "ab"))), 3)
                self.assertIn("Manifest : base d'origine base1, Odoo 18.0, PostgreSQL 16.4, 2 module(s)", out)
                self.assertIn("odoo-bin neutralize", out)
        # Base existante : refus ; filestore non vide : refus
        with open(self.path("bases_existantes"), "w") as f:
            f.write("prise\n")
        rc, out, err = self.lancer("--restore", archive, "--db", "prise")
        self.assertEqual(rc, 1)
        self.assertIn("la base prise existe déjà — jamais d'écrasement", out)
        rc, out, err = self.lancer("--restore", archive, "--db", "copie")
        self.assertIn("le filestore", out)
        self.assertIn("existe déjà et n'est pas vide", out)

    def test_archive_avec_chemin_dangereux_refusee(self):
        piege = self.path("piege.zip")
        with zipfile.ZipFile(piege, "w") as z:
            z.writestr("dump.sql", "-- PostgreSQL database dump complete\n")
            z.writestr("../../etc/cron.d/piege", "x")
        rc, out, err = self.lancer("--restore", piege, "--db", "x")
        self.assertEqual(rc, 1)
        self.assertIn("archive ZIP refusée ou illisible", out)
        self.assertFalse(os.path.exists(self.path("createdb.log")))

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_echecs_de_pg_dump_et_dump_incomplet(self):
        self.mock("pg_dump", 'echo "pg_dump: error: connection to server failed" >&2; exit 1')
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1)
        self.assertIn("pg_dump de base1 en échec : pg_dump: error: connection to server failed", out)
        self.mock("pg_dump", 'echo "CREATE TABLE coupe_en_plein"')
        rc, out, err = self.lancer()
        self.assertIn("dump de base1 incomplet (marque de fin de pg_dump absente)", out)
        self.assertEqual(self.archives(), [])
        self.assertEqual([f for f in os.listdir(os.path.join(self.dest, "base1")) if f.startswith(".partial")], [])

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_retention_jours_semaines_mois(self):
        auj = datetime.date.today()
        noms = [f"base1_{auj - datetime.timedelta(days=j):%Y-%m-%d}_{h}.zip" for j in range(1, 61) for h in ("020000", "140000")]
        os.makedirs(os.path.join(self.dest, "base1"))
        for n in noms:
            open(os.path.join(self.dest, "base1", n), "w").close()
        open(os.path.join(self.dest, "base1", "a-garder-toujours.zip"), "w").close()
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        garde = [n for n in self.archives() if n.startswith("base1_")]
        attendu, vus = set(), {"j": [], "s": [], "m": []}
        hier = str(auj - datetime.timedelta(days=1))
        for n in sorted(noms + [max(garde)], key=lambda x: x[6:23], reverse=True):
            j = n[6:16]; m = n[6:13]; s = datetime.date.fromisoformat(j).isocalendar()[:2]
            g = j >= hier                                                        # KEEP_RECENT_DAYS=2 : aujourd'hui et hier, en entier
            for cle, val, lim in (("j", j, 7), ("s", s, 4), ("m", m, 6)):
                if val not in vus[cle]:
                    vus[cle].append(val)
                    g = g or len(vus[cle]) <= lim
            if g:
                attendu.add(n)
        self.assertEqual(set(garde), attendu)
        self.assertIn("a-garder-toujours.zip", self.archives())
        # Independent retention per format: a tar.xz backup does not delete the zip of the same day
        rc, out, err = self.lancer("--format", "tar.xz")
        self.assertIn(max(garde), self.archives())

    def test_dry_run_statut_et_format_invalide(self):
        rc, out, err = self.lancer("--dry-run")
        self.assertEqual(rc, 0, out + err)
        self.assertRegex(out, r"\(--dry-run\) écrirait .*base1_.*\.zip \(dump\.sql, manifest\.json, filestore/\)")
        self.assertEqual(self.archives(), [])
        rc, out, err = self.lancer("--status")
        self.assertEqual(rc, 1)
        self.assertIn("base1 : AUCUNE sauvegarde", out)
        rc, out, err = self.lancer("--format", "rar")
        self.assertEqual(rc, 1)
        self.assertIn("format « rar » inconnu", err)


class EmplacementConfiguration(EnvTest):
    """1.6 : règle des fichiers de configuration — /etc/default/odoo-backup.conf, PUIS ~/.odoo-backup.conf s'il existe, PUIS la
    ligne de commande (prioritaire) ; fichiers lus toujours affichés ; ancien fichier renommé AVANT toute opération sur le
    timer ; timer référençant un fichier absent signalé ; --config introuvable = erreur."""
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("odoo-backup.sh")
        self.etc = os.path.dirname(self.path("etc-default", "x"))
        self.home = os.path.dirname(self.path("home", "x"))
        self.dest = os.path.dirname(self.path("sauvegardes", "x"))
        self.systemd = os.path.dirname(self.path("systemd", "x"))
        self.env.update(ODOO_BACKUP_DEFAULT_DIR=self.etc, HOME=self.home, ODOO_BACKUP_STATE_DIR=os.path.dirname(self.path("etat", "x")),
                        ODOO_BACKUP_SYSTEMD_DIR=self.systemd, D=self.d, TMPDIR=self.d)
        self.env.pop("ODOO_BACKUP_CONFIG", None)
        self.mock("pg_dump", 'echo "-- PostgreSQL database dump complete"')
        self.mock("psql", FAUX_PSQL)
        # systemctl: each call is noted WITH the state of the new configuration file at that instant
        self.mock("systemctl", 'echo "$*|conf=$([ -e "$ODOO_BACKUP_DEFAULT_DIR/odoo-backup.conf" ] && echo oui || echo non)" >> "$D/systemctl.log"')
        self.conf = os.path.join(self.etc, "odoo-backup.conf")
        self.perso = os.path.join(self.home, ".odoo-backup.conf")
        self.ancien = os.path.join(self.home, ".odoo-backup.cfg")            # 1.19: legacy personal name (renamed to .conf)

    def dry(self, *args):
        return self.run_cmd(["bash", self.prog, "--dry-run"] + list(args))

    def appels_systemctl(self):
        chemin = self.path("systemctl.log")
        return open(chemin).read().splitlines() if os.path.exists(chemin) else []

    def test_couches_ordre_priorite_et_affichage(self):
        self.write("etc-default/odoo-backup.conf", "DEST=/etc/dest\nDATABASES=base1\nKEEP_DAILY=5\nREMOTE=root@h:/x\nFORMAT=zip\n")
        self.write("home/.odoo-backup.conf", "DEST=/home/dest\nFORMAT=tar.xz\n")
        rc, out, err = self.dry()
        self.assertEqual(rc, 0, out + err)
        self.assertIn(f"Configuration lue : {self.conf}, puis {self.perso} (le dernier l'emporte)", sans_date(out))
        # /etc/default d'abord, ~ ensuite : DEST et FORMAT viennent de ~, le reste de /etc/default
        self.assertIn("Options : --lang fr · sauvegardes dans /home/dest (tar.xz) aux heures : 02:30 · bases : base1 · copie hors du serveur : root@h:/x"
                      " · rétention : tout sur 2 j, puis 5 j / 4 sem. / 6 mois", sans_origine(out))
        self.assertTrue(os.path.exists(self.perso))                              # --dry-run moves nothing
        # La ligne de commande l'emporte sur les deux fichiers, et le dit
        rc, out, err = self.dry("--dest", "/cli/dest", "--format", "zip")
        self.assertIn("sauvegardes dans /cli/dest (zip)", out)
        self.assertIn("ligne de commande (prioritaire) : --dest /cli/dest --format zip", out)
        # ~ only: read; nothing: default values, said
        os.remove(self.conf)
        rc, out, err = self.dry()
        self.assertIn(f"Configuration lue : {self.perso}\n", sans_date(out + "\n"))
        os.remove(self.perso)
        rc, out, err = self.dry()
        self.assertIn(f"Configuration lue : aucune (valeurs par défaut) — créée au premier lancement : {self.conf}", out)
        self.assertIn("copie hors du serveur : AUCUNE", out)

    def test_config_explicite_seule_et_introuvable(self):
        self.write("etc-default/odoo-backup.conf", "DEST=/etc/dest\nDATABASES=base1\n")
        autre = self.write("explicite.conf", "DEST=/expl/dest\nDATABASES=base1\n")
        rc, out, err = self.dry("--config", autre)
        self.assertIn(f"Configuration lue : {autre} (demandé par --config : ni /etc/default ni ~ ne sont lus)", sans_date(out))
        self.assertIn("sauvegardes dans /expl/dest", out)
        rc, out, err = self.dry("--config", "/nulle/part/odoo-backup.conf")
        self.assertEqual(rc, 1)
        self.assertIn("ERREUR: configuration introuvable : /nulle/part/odoo-backup.conf", err)
        rc, out, err = self.run_cmd(["bash", self.prog, "--dry-run"], env_extra={"ODOO_BACKUP_CONFIG": "/nulle/part/x.conf"})
        self.assertEqual(rc, 1)                                                 # same thing via the environment variable

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_ancien_fichier_renomme_avant_toute_operation_sur_le_timer(self):
        """L'ancien ~/.odoo-backup.cfg (avant la 1.5 : seule configuration) est RENOMMÉ en /etc/default d'abord ; le service (ancien chemin en dur)
        est corrigé sans arrêter le timer ; --install-timer n'arrête le timer qu'ENSUITE. Chaque appel à systemctl voit déjà le nouveau fichier."""
        self.write("home/.odoo-backup.cfg", "DATABASES=base1\nREMOTE=root@h:/x\n")
        unite = os.path.join(self.systemd, "odoo-backup.service")
        self.write("systemd/odoo-backup.service",
                   f"[Service]\nType=oneshot\nExecStart={self.prog} --config {self.ancien}\nNice=10\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--install-timer"])
        self.assertEqual(rc, 0, out + err)
        self.assertFalse(os.path.exists(self.ancien), "l'ancien fichier aurait dû être renommé")
        self.assertFalse(os.path.exists(self.perso), "l'ancien fichier va dans /etc/default, pas dans ~/.odoo-backup.conf")
        self.assertEqual(oct(os.stat(self.conf).st_mode & 0o777), "0o600")
        self.assertIn("REMOTE=root@h:/x", open(self.conf).read())                # content kept
        self.assertIn(f"Migration : configuration renommée {self.ancien} → {self.conf}", err)
        self.assertIn("Timer : chemin de l'ancien fichier retiré du service", err)
        self.assertIn("le timer n'a PAS été arrêté", err)
        self.assertNotIn("--config", open(unite).read())
        appels = self.appels_systemctl()
        self.assertEqual([a.split("|")[0] for a in appels],
                         ["daemon-reload", "daemon-reload", "enable odoo-backup.timer", "restart odoo-backup.timer"])
        self.assertTrue(all(a.endswith("|conf=oui") for a in appels), appels)    # jamais un appel avant le renommage
        # A system file already exists: the old ~/.odoo-backup.cfg is a DESIRED LAYER: never moved to /etc/default, renamed ~/.odoo-backup.conf (1.19)
        self.write("home/.odoo-backup.cfg", "KEEP_DAILY=3\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--install-timer"])
        self.assertTrue(os.path.exists(self.perso))
        self.assertFalse(os.path.exists(self.ancien))
        self.assertNotIn("Migration", err)
        self.assertIn(f"Configuration : ancien fichier {self.ancien} renommé en {self.perso}", err)
        self.assertIn(f"Configuration lue : {self.conf}, puis {self.perso}", sans_date(out))

    def test_ancien_nom_personnel_renomme_en_conf(self):
        """1.19 : un ~/.odoo-backup.cfg à côté d'un fichier système (couche) devient ~/.odoo-backup.conf, contenu et droits gardés, avis une fois ;
        les deux présents : le .conf est lu, l'ancien est signalé et IGNORÉ (jamais fusionné ni supprimé)."""
        self.write("etc-default/odoo-backup.conf", "DEST=/etc/dest\nDATABASES=base1\nREMOTE=root@h:/x\n")
        self.write("home/.odoo-backup.cfg", "DEST=/home/dest\n")
        os.chmod(self.ancien, 0o600)
        rc, out, err = self.dry()
        self.assertEqual(rc, 0, out + err)
        self.assertFalse(os.path.exists(self.ancien))
        self.assertEqual(open(self.perso).read(), "DEST=/home/dest\n")
        self.assertEqual(oct(os.stat(self.perso).st_mode & 0o777), "0o600")
        self.assertIn(f"Configuration : ancien fichier {self.ancien} renommé en {self.perso} (les fichiers personnels se terminent maintenant par .conf)", err)
        self.assertIn(f"Configuration lue : {self.conf}, puis {self.perso} (le dernier l'emporte)", sans_date(out))
        self.assertIn("sauvegardes dans /home/dest", out)
        rc, out, err = self.dry()
        self.assertNotIn("ancien fichier", err)                                   # only once: there is nothing left to rename
        self.write("home/.odoo-backup.cfg", "DEST=/autre/dest\n")
        rc, out, err = self.dry()
        self.assertIn(f"Configuration : ancien fichier {self.ancien} IGNORÉ ({self.perso} existe et l'emporte)", err)
        self.assertIn("sauvegardes dans /home/dest", out)
        self.assertTrue(os.path.exists(self.ancien))                              # never deleted

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_creation_au_premier_lancement(self):
        rc, out, err = self.run_cmd(["bash", self.prog, "--dest", self.dest])
        self.assertTrue(os.path.isfile(self.conf), out + err)
        self.assertEqual(oct(os.stat(self.conf).st_mode & 0o777), "0o600")
        texte = open(self.conf).read()
        for cle in ("REMOTE", "DEST", "FORMAT", "DATABASES", "ODOO_CONF", "FILESTORE_DIR", "PG_USER", "KEEP_DAILY", "KEEP_WEEKLY",
                    "KEEP_MONTHLY", "TIMER_TIME"):
            self.assertIn(f"#{cle}=", texte)                                    # fully commented template
        self.assertNotRegex(texte, r"(?m)^[A-Z_]+=")                            # no active value: behavior unchanged
        self.assertIn("PUIS ~/.odoo-backup.conf s'il existe", texte)
        self.assertIn(f"Configuration créée : {self.conf}", err)
        rc, out, err = self.run_cmd(["bash", self.prog, "--dest", self.dest])
        self.assertNotIn("Configuration créée", err)                            # une seule fois
        os.remove(self.conf)
        for args in (["--status"], ["--dry-run"]):                              # never created by an action that does not write
            self.run_cmd(["bash", self.prog, "--dest", self.dest] + args)
            self.assertFalse(os.path.exists(self.conf), args)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_timer_sans_chemin_en_dur(self):
        unite = os.path.join(self.systemd, "odoo-backup.service")
        self.write("etc-default/odoo-backup.conf", "DATABASES=base1\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--install-timer"])
        self.assertEqual(rc, 0, out + err)
        ligne = next(l for l in open(unite).read().splitlines() if l.startswith("ExecStart="))
        self.assertNotIn("--config", ligne)                                     # moving the file no longer breaks the timer
        self.assertTrue(ligne.endswith("odoo-backup.sh"), ligne)
        self.assertIn("arrêté puis relancé", out)
        autre = self.write("autre.conf", "DATABASES=base1\n")
        self.run_cmd(["bash", self.prog, "--install-timer", "--config", autre])
        self.assertIn(f"--config {autre}", open(unite).read())                  # explicit --config: written, as requested

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_statut_timer_vers_un_fichier_ou_un_script_absent(self):
        """Timer configuré mais qui utilise un fichier INEXISTANT (cas de la 1.4 : exécutée en silence avec les valeurs par
        défaut, sans REMOTE) : échec signalé ; fichier existant mais unique : avertissement."""
        self.write("etc-default/odoo-backup.conf", "DATABASES=base1\n")
        unite = "systemd/odoo-backup.service"
        self.write(unite, f"[Service]\nExecStart={self.prog} --config /nulle/part/odoo-backup.conf\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--status", "--dest", self.dest])
        self.assertRegex(out, r"\[FAIL\] le timer lit --config /nulle/part/odoo-backup\.conf, qui N'EXISTE PAS — chaque sauvegarde automatique échoue")
        self.assertEqual(rc, 1)
        self.write(unite, "[Service]\nExecStart=/nulle/part/odoo-backup.sh\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--status", "--dest", self.dest])
        self.assertRegex(out, r"\[FAIL\] le timer lance /nulle/part/odoo-backup\.sh, qui N'EXISTE PAS")
        autre = self.write("autre.conf", "DATABASES=base1\n")
        self.write(unite, f"[Service]\nExecStart={self.prog} --config {autre}\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--status", "--dest", self.dest])
        self.assertIn(f"le timer lit seulement --config {autre}, pas la configuration par défaut", out)
        self.assertNotIn("N'EXISTE PAS", out)


class PlusieursSauvegardesParJour(EnvTest):
    """1.7 : plusieurs sauvegardes par jour (TIMER_TIME="09:00 16:00 23:00" ou --times), rétention qui garde tout sur les N
    derniers jours (KEEP_RECENT_DAYS), seuil d'alerte calculé d'après les heures."""
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("odoo-backup.sh")
        self.etc = os.path.dirname(self.path("etc-default", "x"))
        self.dest = os.path.dirname(self.path("sauvegardes", "x"))
        self.systemd = os.path.dirname(self.path("systemd", "x"))
        self.etat = os.path.dirname(self.path("etat", "x"))
        self.env.update(ODOO_BACKUP_DEFAULT_DIR=self.etc, ODOO_BACKUP_STATE_DIR=self.etat, ODOO_BACKUP_SYSTEMD_DIR=self.systemd,
                        D=self.d, TMPDIR=self.d)
        self.env.pop("ODOO_BACKUP_CONFIG", None)
        self.mock("pg_dump", 'echo "-- PostgreSQL database dump complete"')
        self.mock("psql", FAUX_PSQL)
        self.mock("systemctl", "exit 0")
        self.conf = self.write("etc-default/odoo-backup.conf", "DATABASES=base1\nPG_USER=\n")

    def lancer(self, *args, conf=None):
        if conf is not None:
            with open(self.conf, "w") as f:
                f.write("DATABASES=base1\nPG_USER=\n" + conf)
        return self.run_cmd(["bash", self.prog, "--dest", self.dest] + list(args))

    def archives(self):
        d = os.path.join(self.dest, "base1")
        return sorted(f for f in os.listdir(d) if f.endswith(".zip")) if os.path.isdir(d) else []

    def test_report_err(self):
        """--report-err : le programme s'exécute normalement (sortie affichée, code de sortie conservé), puis un rapport à copier-coller."""
        rc, out, err = self.run_cmd(["bash", self.prog, "--dest", self.dest, "--status", "--report-err"])
        self.assertEqual(rc, 1, out)                                                # code du programme : pas de sauvegarde
        self.assertLess(out.index("[FAIL] base1 : AUCUNE sauvegarde"), out.index("RAPPORT D'ERREURS (--report-err)"))
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : odoo-backup\.sh v1\.\d+\.\d{8}\.\d{6} — commande : odoo-backup\.sh --dest \S+ --status\n")
        self.assertNotIn("--report-err —", rapport)                                 # the option is not in the reported command
        self.assertRegex(rapport, r"Serveur   : \S+ .*utilisateur \S+ — bash \d")
        self.assertIn("code de sortie 1 (ÉCHEC)", rapport)
        self.assertIn("Contexte  : Configuration lue : ", rapport)
        self.assertRegex(rapport, r"Suite     : .*odoo-backup\.sh \d+\.\d+\.\d{8}\.\d{6}")
        self.assertIn("ÉCHECS (1) :\n  1. [FAIL] base1 : AUCUNE sauvegarde", rapport)
        self.assertIn("AVERTISSEMENTS (3) :", rapport)                              # timer not installed, no copy off the server, no restoration test yet (1.24)
        self.assertIn("[ATTN] Timer : NON INSTALLÉ", rapport)
        self.assertIn("[ATTN] Copie hors du serveur : aucune (REMOTE)", rapport)
        self.assertEqual([f for f in os.listdir(self.d) if f.startswith("report-err.")], [], "fichier temporaire oublié")
        # --help et --version avec --report-err : comportement normal, sans rapport
        for option in ("--help", "--version"):
            rc, out, err = self.run_cmd(["bash", self.prog, option, "--report-err"])
            self.assertEqual(rc, 0, err)
            self.assertNotIn("RAPPORT D'ERREURS", out)
        # Component absent: clear message, normal run
        os.remove(os.path.join(os.path.dirname(self.prog), "apps", "_rapport.py"))
        rc, out, err = self.run_cmd(["bash", self.prog, "--dest", self.dest, "--status", "--report-err"])
        self.assertIn("--report-err indisponible", err)
        self.assertIn("[FAIL] base1 : AUCUNE sauvegarde", out)
        self.assertNotIn("RAPPORT D'ERREURS", out)

    def test_heures_normalisees_et_refusees(self):
        for saisie, attendu in (("9:00, 23:00 16:00", "09:00, 16:00, 23:00"), ("23:00 9:00 16:00", "09:00, 16:00, 23:00"),
                                ("02:30", "02:30"), ("09:00 9:00", "09:00")):
            with self.subTest(saisie=saisie):
                rc, out, err = self.lancer("--dry-run", conf=f"TIMER_TIME={saisie}\n")
                self.assertEqual(rc, 0, out + err)
                self.assertIn(f"aux heures : {attendu} ·", out)
        for mauvaise in ("25:00", "9h", "12:60", "", "09:00 midi", "24:00"):
            with self.subTest(mauvaise=mauvaise):
                rc, out, err = self.lancer("--dry-run", conf=f"TIMER_TIME={mauvaise}\n")
                self.assertEqual(rc, 1, out)
                self.assertIn("TIMER_TIME attend une ou plusieurs heures HH:MM", err)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_timer_une_ligne_par_heure_et_ligne_de_commande_prioritaire(self):
        unite = os.path.join(self.systemd, "odoo-backup.timer")
        with open(self.conf, "w") as f:
            f.write("DATABASES=base1\nTIMER_TIME=02:30\n")                    # the file says 02:30...
        rc, out, err = self.run_cmd(["bash", self.prog, "--install-timer", "--times", "23:00 9:00 16:00"])   # ...the command line wins
        self.assertEqual(rc, 0, out + err)
        lignes = [l for l in open(unite).read().splitlines() if l.startswith("OnCalendar=")]
        self.assertEqual(lignes, ["OnCalendar=*-*-* 09:00", "OnCalendar=*-*-* 16:00", "OnCalendar=*-*-* 23:00"])
        self.assertIn("3 sauvegarde(s) par jour, à 09:00, 16:00, 23:00", out)
        self.assertIn('ligne de commande (prioritaire) : --times "23:00 9:00 16:00"', out)
        self.assertIn("Persistent=true", open(unite).read())                     # catch-up if the server was off
        # Une seule heure : une seule ligne (comportement d'avant)
        rc, out, err = self.run_cmd(["bash", self.prog, "--install-timer"])
        self.assertEqual([l for l in open(unite).read().splitlines() if l.startswith("OnCalendar=")], ["OnCalendar=*-*-* 02:30"])
        self.assertIn("1 sauvegarde(s) par jour, à 02:30", out)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_statut_timer_different_de_la_configuration(self):
        self.run_cmd(["bash", self.prog, "--install-timer", "--times", "09:00 16:00 23:00"])
        self.write("etc-default/odoo-backup.conf", "DATABASES=base1\nTIMER_TIME=09:00 16:00 23:00\n")
        rc, out, err = self.run_cmd(["bash", self.prog, "--status", "--dest", self.dest])
        self.assertIn("chaque jour à 09:00, 16:00, 23:00", out)
        self.assertNotIn("ne correspond pas", out)
        self.write("etc-default/odoo-backup.conf", "DATABASES=base1\nTIMER_TIME=02:30\n")      # configuration changed, timer not reinstalled
        rc, out, err = self.run_cmd(["bash", self.prog, "--status", "--dest", self.dest])
        self.assertIn("le timer installé (09:00, 16:00, 23:00) ne correspond pas aux heures configurées (02:30)", out)

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_seuil_d_alerte_selon_les_heures(self):
        """Écart maximal entre deux sauvegardes (cyclique) + 2 h : une par jour → 26 h (comme avant) ; 09:00 16:00 23:00 → 12 h."""
        import time
        os.makedirs(os.path.join(self.dest, "base1"))
        vieille = os.path.join(self.dest, "base1", "base1_2026-09-20_020000.zip")
        open(vieille, "w").close()
        il_y_a_20_h = time.time() - 20 * 3600
        os.utime(vieille, (il_y_a_20_h, il_y_a_20_h))
        rc, out, err = self.lancer("--status", conf="TIMER_TIME=02:30\n")              # seuil 26 h : 20 h est acceptable
        self.assertRegex(out, r"\[OK\]\s+base1 : dernière sauvegarde il y a 20 h")
        rc, out, err = self.lancer("--status", conf="TIMER_TIME=09:00 16:00 23:00\n")  # seuil 12 h : 20 h est trop
        self.assertRegex(out, r"\[FAIL\]\s+base1 : dernière sauvegarde il y a 20 h \(.*; seuil 12 h pour les heures 09:00 16:00 23:00\)")
        self.assertEqual(rc, 1)
        rc, out, err = self.lancer("--status", conf="TIMER_TIME=00:00 12:00\n")         # deux par jour : 12 h + 2 = 14 h
        self.assertIn("seuil 14 h", out)
        # The threshold is written for web-monitor.py at each successful backup
        rc, out, err = self.lancer(conf="TIMER_TIME=09:00 16:00 23:00\n")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(open(os.path.join(self.etat, "max-age-hours")).read().strip(), "12")

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_retention_garde_tout_sur_les_derniers_jours(self):
        """Trois sauvegardes par jour : KEEP_RECENT_DAYS=2 (défaut) garde TOUT aujourd'hui et hier, puis la dernière de chaque jour ;
        KEEP_RECENT_DAYS=0 retrouve l'ancien comportement (une par jour, les précédentes effacées aussitôt)."""
        auj = datetime.date.today()
        def prepare():
            d = os.path.join(self.dest, "base1")
            if os.path.isdir(d):
                for f in os.listdir(d):
                    os.remove(os.path.join(d, f))
            os.makedirs(d, exist_ok=True)
            for jours in (1, 2, 3):
                for h in ("090000", "160000", "230000"):
                    open(os.path.join(d, f"base1_{auj - datetime.timedelta(days=jours)}_{h}.zip"), "w").close()
        prepare()
        rc, out, err = self.lancer(conf="")                                                  # KEEP_RECENT_DAYS=2 by default
        self.assertEqual(rc, 0, out + err)
        restes = self.archives()
        hier = [a for a in restes if str(auj - datetime.timedelta(days=1)) in a]
        self.assertEqual(len(hier), 3, restes)                                               # hier : les trois
        self.assertEqual(len([a for a in restes if str(auj) in a]), 1, restes)              # today: the one just made
        for jours in (2, 3):                                                                 # the day before yesterday and earlier: the last one of the day
            self.assertEqual([a for a in restes if str(auj - datetime.timedelta(days=jours)) in a],
                             [f"base1_{auj - datetime.timedelta(days=jours)}_230000.zip"])
        prepare()
        rc, out, err = self.lancer(conf="KEEP_RECENT_DAYS=0\n")
        restes = self.archives()
        self.assertEqual([a for a in restes if str(auj - datetime.timedelta(days=1)) in a],
                         [f"base1_{auj - datetime.timedelta(days=1)}_230000.zip"])           # une seule : comportement d'avant
        rc, out, err = self.lancer("--dry-run", conf="KEEP_RECENT_DAYS=deux\n")
        self.assertEqual(rc, 1)
        self.assertIn("KEEP_RECENT_DAYS doit être un entier", err)
