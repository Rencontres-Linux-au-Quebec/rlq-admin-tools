"""collect-all-advise.sh : --days N, configuration, collection on LXC and VM (pct, qm, ssh mocked), archive .tar.xz."""
import datetime
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ENVIRONNEMENT = "commun"   # Proxmox host: collection of the guests, not specific to Odoo or BigBlueButton

PROG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "collect-all-advise.sh")

# Fake commands: pct / qm (Proxmox), ssh (runs the command locally), sudo (no-op), and a fake app-log-live.py
# that writes the file given to --export-ai, so that the whole collection can be tested without a Proxmox host.
PCT = """#!/bin/bash
case "$1" in
    list) printf 'VMID       Status     Lock         Name\\n101        running                 bbb-lxc1\\n102        stopped                 bbb-lxc2\\n103        running                 web-odoo\\n' ;;
    exec) while [[ "$1" != "--" ]]; do shift; done; shift; exec "$@" ;;
    pull) cp "$3" "$4" ;;
esac
"""
QM = """#!/bin/bash
# qm guest cmd VMID network-get-interfaces: the guest agent of VM 201 answers 10.0.0.77 (NO_AGENT=1: no agent)
if [[ "$1" == guest ]]; then
    [[ -z "${NO_AGENT:-}" && "$3" == 201 ]] || exit 1
    echo '[{"name":"lo","ip-addresses":[{"ip-address":"127.0.0.1","ip-address-type":"ipv4"}]},{"name":"eth0","ip-addresses":[{"ip-address":"10.0.0.77","ip-address-type":"ipv4"}]}]'
    exit 0
fi
printf 'VMID NAME                 STATUS     MEM(MB)    BOOTDISK(GB) PID\\n201 bbb-vm1               running    8192       40.00        1\\n202 bbb-vm2               stopped    8192       40.00        0\\n'
"""
SSH = """#!/bin/bash
# ssh [options] TARGET COMMAND : the command runs here (the VM is simulated)
while [[ "$1" == -* ]]; do if [[ "$1" == "-o" ]]; then shift; fi; shift; done
echo "$1" >> "$SSH_LOG"
shift
exec bash -c "$1"
"""
SUDO = """#!/bin/bash
exec "$@"
"""
APP = """#!/bin/bash
# fake app-log-live.py: writes the report given to --export-ai, and records its arguments
dest=""
echo "$*" >> "$APP_LOG"
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--export-ai" ]]; then dest="$2"; shift; fi
    shift
done
echo "# fake report" > "$dest"
"""


class CollectAllAdvise(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="test-rlq-collect-")
        self.bin = os.path.join(self.d, "bin")
        os.makedirs(self.bin)
        self.dest = os.path.join(self.d, "audit")
        self.app_log = os.path.join(self.d, "app.log")
        self.ssh_log = os.path.join(self.d, "ssh.log")
        for nom, contenu in (("pct", PCT), ("qm", QM), ("ssh", SSH), ("sudo", SUDO), ("app-log-live.py", APP)):
            chemin = os.path.join(self.bin, nom)
            with open(chemin, "w") as f:
                f.write(contenu)
            os.chmod(chemin, 0o755)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], APP_LOG=self.app_log,
                        SSH_LOG=self.ssh_log, HOME=self.d)
        self.env.pop("LANGUAGE", None)
        self.env["LANG"] = "fr_CA.UTF-8"
        self.etc = os.path.join(self.d, "etc")
        os.makedirs(self.etc)
        self.env["NGINX_TOOLS_ETC_DEFAULT"] = self.etc
        self.env["COLLECT_NO_PROMPT"] = "1"            # no question on the terminal in the tests
        self.env["SUDO_USER"] = ""                     # the default folder is the home of the current user
        self.env["HOME"] = self.d
        self.env.pop("LC_ALL", None)
        self.env.pop("LC_MESSAGES", None)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def lancer(self, *args, config=None):
        options = ["--program", os.path.join(self.bin, "app-log-live.py"), *args]   # the fake program of the test folder
        if config is not None:
            chemin = os.path.join(self.d, "config.conf")
            with open(chemin, "w") as f:
                f.write(config)
            options = ["-c", chemin] + options
        return subprocess.run(["bash", PROG, *options], capture_output=True, text=True, env=self.env, timeout=120)

    def test_version_et_aide_en_francais_et_anglais(self):
        r = self.lancer("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"collect-all-advise\.sh version 1\.\d+\.\d{8}\.\d{6}")
        r = self.lancer("--help")
        self.assertIn("--days N", re.sub(r"\x1b\[[0-9;]*m", "", r.stdout))

    def test_days_refuse_les_valeurs_hors_plage(self):
        for valeur in ("0", "367", "abc", "-1"):
            r = self.lancer("--days", valeur, "--dest", self.dest)
            self.assertEqual(r.returncode, 2, valeur)
            self.assertIn("1 à 366", r.stderr, valeur)

    def test_configuration_et_options_en_ligne_de_commande(self):
        config = "DAYS=3\nDEST=" + self.dest + "\nNAME_REGEX=bbb-lxc1\nVM_HOST_201=10.0.0.21\n"
        r = self.lancer(config=config)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Configuration lue", r.stderr)
        self.assertIn("--advise --days 3 ", open(self.app_log).read())
        self.assertFalse(os.path.exists(self.ssh_log), "--name bbb-lxc1 : la VM bbb-vm1 ne doit pas être touchée")
        r = self.lancer("--days", "5", "--dest", self.dest, "--name", "bbb-lxc1", config=config)
        self.assertIn("--advise --days 5 ", open(self.app_log).read())

    def test_collecte_lxc_et_vm_puis_archive_des_seuls_md(self):
        config = "VM_HOST_201=10.0.0.21\n"
        r = self.lancer("--days", "2", "--dest", self.dest, config=config)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        sortie = r.stdout
        self.assertIn("LXC 101 bbb-lxc1", sortie)
        self.assertNotIn("bbb-lxc2", sortie)           # stopped
        self.assertNotIn("web-odoo", sortie)           # not a BigBlueButton name
        self.assertNotIn("bbb-vm2", sortie)            # stopped VM
        self.assertIn("--anonymize", open(self.app_log).read())
        dossiers = [n for n in os.listdir(self.dest) if n.isdigit() or re.match(r"\d{8}-\d{6}$", n)]
        self.assertEqual(len(dossiers), 1, os.listdir(self.dest))
        racine = os.path.join(self.dest, dossiers[0])
        self.assertTrue(os.path.isfile(os.path.join(racine, "lxc-101-bbb-lxc1", "export-ai-" + dossiers[0] + ".md")))
        archives = [n for n in os.listdir(self.dest) if n.endswith(".tar.xz")]
        self.assertEqual(len(archives), 1, archives)
        jour = datetime.date.today().isoformat()
        self.assertRegex(archives[0], r"^collect-all-advise\.[^.]+\." + jour + r"\.tar\.xz$")
        with tarfile.open(os.path.join(self.dest, archives[0]), "r:xz") as t:
            noms = [m.name for m in t.getmembers() if m.isfile()]
        self.assertTrue(noms, "archive vide")
        self.assertTrue(all(n.endswith(".md") for n in noms), noms)

    def test_adresse_de_vm_detectee_par_l_agent_invite(self):
        r = self.lancer("--days", "2", "--dest", self.dest)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("10.0.0.77", open(self.ssh_log).read())
        self.assertIn("(10.0.0.77)", r.stdout)

    def test_vm_sans_adresse_signalee_et_code_retour_1(self):
        self.env["NO_AGENT"] = "1"
        r = self.lancer("--days", "2", "--dest", self.dest)
        self.assertEqual(r.returncode, 1)
        self.assertIn("adresse introuvable", r.stdout)

    def test_configuration_par_defaut_creee_au_premier_lancement(self):
        self.env["NO_AGENT"] = "1"
        r = self.lancer("--days", "2", "--dest", self.dest)
        cible = os.path.join(self.etc, "collect-all-advise.conf") if os.geteuid() == 0 else os.path.join(self.d, ".collect-all-advise.conf")
        self.assertTrue(os.path.isfile(cible), r.stderr)
        texte = open(cible, encoding="utf-8").read()
        self.assertIn("DAYS=2", texte)
        self.assertIn("NAME_REGEX=bbb", texte)
        self.assertIn("PROGRAM=/opt/rlq-admin-tools/app-log-live.py", texte)
        self.assertIn("DEST=" + os.path.join(self.d, "audit", "collect-all-advise"), texte)
        self.assertNotIn("dcp9370", texte)
        self.assertIn("Configuration créée", r.stderr)
        r = self.lancer("--days", "2", "--dest", self.dest)
        self.assertIn("Configuration lue", r.stderr)          # the second run reads the file created by the first one

    def test_no_archive_garde_seulement_le_dossier(self):
        r = self.lancer("--days", "2", "--dest", self.dest, "--no-archive", "--no-anonymize")
        self.assertIn("--no-anonymize", open(self.app_log).read())
        self.assertFalse([n for n in os.listdir(self.dest) if n.endswith(".tar.xz")])

    def test_archive_du_meme_jour_ne_remplace_pas_la_precedente(self):
        self.lancer("--days", "2", "--dest", self.dest, "--name", "bbb-lxc1")
        self.lancer("--days", "2", "--dest", self.dest, "--name", "bbb-lxc1")
        archives = sorted(n for n in os.listdir(self.dest) if n.endswith(".tar.xz"))
        self.assertEqual(len(archives), 2, archives)
        self.assertTrue(any(n.endswith("-2.tar.xz") for n in archives), archives)

    def test_changelog_affiche_la_section_du_programme(self):
        r = self.lancer("--changelog")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1.0.", re.sub(r"\x1b\[[0-9;]*m", "", r.stdout))


if __name__ == "__main__":
    unittest.main()
