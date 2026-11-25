"""odoo-sql-maint 1.6 : tables qu'aucun modèle d'Odoo n'utilise (orphan-tables), --export-drop-table (export vérifié puis DROP), sauvegardes
planifiées faites dans Odoo (backup-crons, -disable, -enable). Le test avec PostgreSQL crée une grappe jetable (initdb) ; sans initdb, il est sauté.
Données inventées (schéma Odoo réduit à ir_model, ir_model_fields, ir_cron et ir_model_data)."""
ENVIRONNEMENT = "commun"
import glob
import os
import pwd
import shutil
import subprocess
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROG = os.path.join(RACINE, "odoo-sql-maint")
INITDB = next(iter(sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))), None) or shutil.which("initdb")


def lancer(*args, conf=None, entree=None):
    env = dict(os.environ, LANG="C.UTF-8", NO_COLOR="1")
    cmd = [PROG] + (["--config", conf] if conf else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env, input=entree)
    return r.returncode, r.stdout + r.stderr


class SansBase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="test-rlq-sqlmaint-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.conf = os.path.join(self.d, "c.conf")
        with open(self.conf, "w") as f:
            f.write("PG_DATABASE=testdb\nUI_LANG=en\n")

    def test_16_requetes_et_option_dans_l_aide(self):
        rc, out = lancer("--list", conf=self.conf)
        self.assertEqual(rc, 0, out)
        for nom in ("orphan-tables", "backup-crons", "backup-crons-disable", "backup-crons-enable"):
            self.assertIn(nom, out)
        self.assertIn("backup-crons-disable", [l.split()[0] for l in out.splitlines() if "[destructive]" in l])
        rc, out = lancer("--help", conf=self.conf)
        options = [l.split()[0] for l in out.splitlines() if l.startswith("  --")]
        self.assertIn("--export-drop-table", options)
        self.assertEqual(options, sorted(options))                                  # alphabetical
        self.assertIn("EXPORT_DIR", out)


@unittest.skipUnless(INITDB and shutil.which("psql") and shutil.which("pg_dump") and os.geteuid() == 0, "initdb, psql, pg_dump and root needed")
class AvecPostgreSQL(unittest.TestCase):
    PORT = "55439"

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="test-rlq-sqlmaint-pg-")
        os.chmod(cls.d, 0o777)
        pg = pwd.getpwnam("postgres")
        os.chown(cls.d, pg.pw_uid, pg.pw_gid)
        bindir = os.path.dirname(INITDB)
        su = lambda c: subprocess.run(["su", "postgres", "-c", c], check=True, capture_output=True, timeout=120)
        su(f"{INITDB} -D {cls.d}/data -A trust -U odoo")
        su(f"{bindir}/pg_ctl -D {cls.d}/data -o '-p {cls.PORT} -k {cls.d} -c listen_addresses=' -l {cls.d}/log -w start")
        cls.psql("postgres", "CREATE DATABASE testdb;")
        cls.psql("testdb", """
            CREATE TABLE ir_model (id serial primary key, model varchar);
            CREATE TABLE ir_model_fields (id serial primary key, relation_table varchar);
            INSERT INTO ir_model(model) VALUES ('res.partner'), ('ir.model'), ('ir.model.fields'), ('ir.cron'), ('ir.model.data');
            CREATE TABLE res_partner (id serial primary key, name varchar);
            CREATE TABLE res_groups_users_rel (gid int, uid int);
            INSERT INTO ir_model_fields(relation_table) VALUES ('res_groups_users_rel');
            CREATE TABLE backup_page_history_steps (id int, content text);
            INSERT INTO backup_page_history_steps SELECT g, repeat('x', 100) FROM generate_series(1, 229) g;
            CREATE TABLE old_parent (id int primary key);
            CREATE TABLE child_of_old (pid int references old_parent(id));
            CREATE TABLE ir_cron (id serial primary key, cron_name varchar, active bool, interval_number int, interval_type varchar, nextcall timestamp);
            CREATE TABLE ir_model_data (id serial, module varchar, name varchar, model varchar, res_id int);
            INSERT INTO ir_cron(cron_name, active, interval_number, interval_type) VALUES ('Backup Scheduler', true, 1, 'days'),
                ('Backup : Daily Database Backup', true, 1, 'days'), ('Mail: Email Queue Manager', true, 5, 'minutes');
            INSERT INTO ir_model_data(module, name, model, res_id) VALUES ('auto_backup', 'a', 'ir.cron', 1), ('auto_database_backup', 'b', 'ir.cron', 2),
                ('mail', 'c', 'ir.cron', 3);
            ANALYZE;""")
        cls.conf = os.path.join(cls.d, "c.conf")
        with open(cls.conf, "w") as f:
            f.write(f"PG_HOST={cls.d}\nPG_PORT={cls.PORT}\nPG_USER=odoo\nPG_DATABASE=testdb\nEXPORT_DIR={cls.d}/exports\nUI_LANG=en\nPROD_PATTERN=prod\n")

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["su", "postgres", "-c", f"{os.path.dirname(INITDB)}/pg_ctl -D {cls.d}/data -m immediate stop"], capture_output=True, timeout=60)
        shutil.rmtree(cls.d, True)

    @classmethod
    def psql(cls, base, sql):
        return subprocess.run(["psql", "-X", "-q", "-At", "-h", cls.d, "-p", cls.PORT, "-U", "odoo", "-d", base, "-c", sql],
                              check=True, capture_output=True, text=True, timeout=60).stdout.strip()

    def test_16_tables_orphelines(self):
        rc, out = lancer("--run", "orphan-tables", conf=self.conf)
        self.assertEqual(rc, 0, out)
        self.assertIn("backup_page_history_steps", out)
        for odoo in ("res_partner", "res_groups_users_rel", "old_parent"):           # model, many2many, referenced by another table
            self.assertNotIn(odoo + " ", out)

    def test_16_refus(self):
        for table, attendu in (("res_partner", "belongs to Odoo"), ("res_groups_users_rel", "belongs to Odoo"), ("old_parent", "other tables point to old_parent"),
                               ("x;drop", "Invalid table name"), ("absente", "not found")):
            rc, out = lancer("--export-drop-table", table, "--yes", conf=self.conf)
            self.assertEqual(rc, 4, out)
            self.assertIn(attendu, out)
        rc, out = lancer("--export-drop-table", "backup_page_history_steps", conf=self.conf, entree="")
        self.assertEqual(rc, 4, out)                                                   # no terminal and no --yes: refused
        rc, out = lancer("--export-drop-table", "backup_page_history_steps", "--database", "prod_copy", "--yes", conf=self.conf)
        self.assertEqual(rc, 4, out)

    def test_16_export_puis_drop(self):
        rc, out = lancer("--export-drop-table", "backup_page_history_steps", "--yes", "--dry-run", conf=self.conf)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.psql("testdb", "SELECT count(*) FROM backup_page_history_steps"), "229")          # dry run: still there
        rc, out = lancer("--export-drop-table", "backup_page_history_steps", "--yes", conf=self.conf)
        self.assertEqual(rc, 0, out)
        self.assertIn("Export checked", out)
        self.assertEqual(self.psql("testdb", "SELECT to_regclass('public.backup_page_history_steps') IS NULL"), "t")
        export = sorted(glob.glob(os.path.join(self.d, "exports", "*.sql.gz")))[-1]
        self.assertEqual(oct(os.stat(export).st_mode & 0o777), "0o600")
        subprocess.run(f"gunzip -c {export} | psql -X -q -h {self.d} -p {self.PORT} -U odoo -d testdb", shell=True, check=True, capture_output=True, timeout=60)
        self.assertEqual(self.psql("testdb", "SELECT count(*) FROM backup_page_history_steps"), "229")          # the export puts it back

    def test_17_detection_de_la_base_odoo(self):
        # 1.8: no database in the configuration. Two Odoo-like bases (ir_module_module) and one that is not Odoo.
        # connection-test is used: it reads no table, so the bases need no Odoo schema beyond ir_module_module.
        for base in ("odoo_a", "odoo_b", "zz_sans_odoo"):
            self.psql("postgres", f"CREATE DATABASE {base};")
        for base in ("odoo_a", "odoo_b"):
            self.psql(base, "CREATE TABLE ir_module_module (id serial primary key, name varchar);")
        conf = os.path.join(self.d, "sans-base.conf")
        with open(conf, "w") as f:
            f.write(f"PG_HOST={self.d}\nPG_PORT={self.PORT}\nPG_USER=odoo\nUI_LANG=en\n")
        rc, out = lancer("--run", "connection-test", "--dry-run", conf=conf, entree="")
        self.assertEqual(rc, 4, out)                                   # no terminal: nothing is guessed, nothing runs
        self.assertIn("odoo_a", out)
        self.assertIn("odoo_b", out)
        self.assertNotIn("zz_sans_odoo", out)
        self.assertNotIn("Query finished", out)
        rc, out = lancer("--run", "connection-test", "--dry-run", "--yes", conf=conf)
        self.assertEqual(rc, 4, out)                                   # two bases and --yes: refused, the user chooses
        self.assertIn("choose one", out)
        rc, out = lancer("--run", "connection-test", "--dry-run", "--database", "odoo_a", conf=conf)
        self.assertEqual(rc, 0, out)                                   # explicit base: no detection, the query runs
        self.assertIn("Query finished", out)
        self.psql("odoo_b", "DROP TABLE ir_module_module;")            # now only one Odoo base: --yes accepts it
        rc, out = lancer("--run", "connection-test", "--dry-run", "--yes", conf=conf)
        self.assertEqual(rc, 0, out)
        self.assertIn("Database detected and used: odoo_a", out)
        self.assertIn("Query finished", out)

    def test_17_pas_de_question_de_mot_de_passe(self):
        # 1.9: psql runs with -w: a server that asks for a password fails at once, with the hint about ~/.pgpass; nothing waits on the terminal.
        conf = os.path.join(self.d, "mauvais-port.conf")
        with open(conf, "w") as f:
            f.write(f"PG_HOST={self.d}\nPG_PORT=1\nPG_USER=odoo\nUI_LANG=en\n")
        rc, out = lancer("--run", "connection-test", "--dry-run", conf=conf, entree="")
        self.assertEqual(rc, 4, out)
        self.assertIn("pgpass", out)

    def test_16_sauvegardes_planifiees(self):
        rc, out = lancer("--run", "backup-crons-disable", "--yes", conf=self.conf)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.psql("testdb", "SELECT string_agg(id || ':' || active, ',' ORDER BY id) FROM ir_cron"), "1:false,2:false,3:true")
        rc, out = lancer("--run", "backup-crons-enable", "--yes", conf=self.conf)
        self.assertEqual(self.psql("testdb", "SELECT string_agg(id || ':' || active, ',' ORDER BY id) FROM ir_cron"), "1:true,2:true,3:true")


if __name__ == "__main__":
    unittest.main()
