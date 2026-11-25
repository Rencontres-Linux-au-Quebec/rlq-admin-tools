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
port=22
while [[ "$1" == -* ]]; do if [[ "$1" == "-p" ]]; then port="$2"; fi; if [[ "$1" == "-o" || "$1" == "-p" ]]; then shift; fi; shift; done
echo "$1 $2" >> "$SSH_LOG"   # target and command
echo "port=$port" >> "$SSH_LOG"
if [[ -n "${SSH_FAIL:-}" ]]; then echo "$SSH_FAIL" >&2; exit 255; fi
shift
exec bash -c "$1"
"""
SUDO = """#!/bin/bash
exec "$@"
"""
APT = """#!/bin/bash
# fake apt-get: one pending security update (openssl) and one normal update (vim); APT_NONE=1: nothing pending
case "$*" in
    *"-s upgrade"*)
        if [[ -z "${APT_NONE:-}" ]]; then
            echo "Inst openssl [3.0.1] (3.0.2 Debian-Security:12/stable-security [amd64])"
            echo "Inst vim [1] (2 Debian:12 [amd64])"
        fi ;;
    *install*) echo "$*" >> "$APT_LOG" ;;
esac
exit 0
"""
APP = """#!/bin/bash
# fake app-log-live.py: writes the report given to --export-ai, and records its arguments
dest=""
if [[ "$1" == "--version" ]]; then echo "app-log-live.py v${GUEST_VERSION:-1.200.20261101.000000}"; exit 0; fi
echo "$*" >> "$APP_LOG"
echo "LANG=${APP_LOG_LIVE_LANG:-}" >> "$APP_LOG"
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
        for nom, contenu in (("pct", PCT), ("qm", QM), ("ssh", SSH), ("sudo", SUDO), ("apt-get", APT), ("app-log-live.py", APP)):
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
        self.env["APT_LOG"] = os.path.join(self.d, "apt.log")
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
        self.assertIn("web-odoo", sortie)              # an Odoo name: collected by default (bbb|odoo)
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
        self.assertIn("NAME_REGEX=bbb|odoo", texte)
        self.assertIn("LANGUAGE=", texte)
        self.assertIn("PROGRAM=/opt/rlq-admin-tools/app-log-live.py", texte)
        self.assertIn("DEST=" + os.path.join(self.d, "audit", "collect-all-advise"), texte)
        self.assertNotIn("dcp9370", texte)
        self.assertIn("Configuration créée", r.stderr)
        r = self.lancer("--days", "2", "--dest", self.dest)
        self.assertIn("Configuration lue", r.stderr)          # the second run reads the file created by the first one

    def test_mises_a_jour_de_securite_signalees_sans_installation(self):
        r = self.lancer("--days", "2", "--dest", self.dest, config="VM_HOST_201=10.0.0.21\n")
        self.assertIn("Mises à jour de sécurité", r.stdout + r.stderr)
        self.assertIn("openssl", r.stdout)
        self.assertNotIn("vim", r.stdout)                                  # not a security update
        self.assertIn("bbb-lxc1 : " , r.stdout)                              # the container is checked too
        self.assertIn("pas de terminal", r.stdout)
        self.assertFalse(os.path.exists(self.env["APT_LOG"]), "rien ne doit être installé sans réponse")

    def test_pas_de_verification_avec_no_security(self):
        r = self.lancer("--days", "2", "--dest", self.dest, "--no-security", config="VM_HOST_201=10.0.0.21\n")
        self.assertNotIn("Mises à jour de sécurité", r.stdout + r.stderr)

    def test_aucune_mise_a_jour_de_securite(self):
        self.env["APT_NONE"] = "1"
        r = self.lancer("--days", "2", "--dest", self.dest, config="VM_HOST_201=10.0.0.21\n")
        self.assertIn("aucune mise à jour de sécurité en attente", r.stdout)

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


    def test_langue_des_rapports_donnee_au_programme(self):
        config = "LANGUAGE=en\nVM_HOST_201=10.0.0.21\n"
        r = self.lancer("--days", "2", "--dest", self.dest, config=config)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("LANG=en", open(self.app_log).read())          # the container, through pct exec
        self.assertIn("sudo env APP_LOG_LIVE_LANG=en", open(self.ssh_log).read())   # the VM, through ssh
        r = self.lancer("--days", "2", "--dest", self.dest, "--lang", "fr", config=config)
        self.assertIn("LANG=fr", open(self.app_log).read())          # --lang wins over the configuration

    def test_aucune_machine_correspondante_signalee(self):
        r = self.lancer("--days", "2", "--dest", self.dest, "--name", "zzz-pas-de-machine")
        sortie = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
        self.assertIn("aucune machine en marche ne correspond", sortie)
        self.assertIn("zzz-pas-de-machine", sortie)

    def test_rapport_en_echec_affiche_la_raison(self):
        r = self.lancer("--days", "2", "--dest", self.dest, "--program", "/chemin/inexistant/app-log-live.py",
                        config="VM_HOST_201=10.0.0.21\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No such file", r.stdout)                      # the reason of the failure is shown, not only the path

    def test_verbose_montre_les_etapes(self):
        """1.9 --verbose: each guest (selected or skipped), its address and the exit code of each step on the standard error; none without it."""
        r = self.lancer("--days", "2", "--dest", self.dest, "--verbose", config="VM_HOST_201=10.0.0.21\n")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        trace = re.sub(r"\x1b\[[0-9;]*m", "", r.stderr)
        self.assertIn("[trace] LXC 101 bbb-lxc1 : pct exec 101", trace)
        self.assertIn("[trace] LXC 101 bbb-lxc1 : code de retour 0", trace)
        self.assertIn("[trace] LXC 102 bbb-lxc2 : ignorée (état stopped", trace)
        self.assertIn("[trace] VM 201 bbb-vm1 : adresse 10.0.0.21 (VM_HOST_201 de la configuration)", trace)
        self.assertIn("[trace] VM 201 bbb-vm1 : ssh root@10.0.0.21 \"sudo env", trace)
        self.assertNotIn("[trace]", r.stdout)
        r = self.lancer("--days", "2", "--dest", self.dest, config="VM_HOST_201=10.0.0.21\n")
        self.assertNotIn("[trace]", r.stdout + r.stderr)

    def suite_locale(self):
        """1.10: a copy of the program in a folder of the suite with its own app-log-live.py (version of reference) and a fake
        host-perf-audit.py that records its arguments."""
        suite = os.path.join(self.d, "suite")
        os.makedirs(suite)
        shutil.copy(PROG, os.path.join(suite, "collect-all-advise.sh"))
        self.sync_log = os.path.join(self.d, "sync.log")
        for nom, contenu in (("app-log-live.py", '#!/bin/bash\necho "app-log-live.py v1.210.20261124.212059"\n'),
                             ("host-perf-audit.py", f'#!/bin/bash\necho "$*" >> {self.sync_log}\n')):
            with open(os.path.join(suite, nom), "w") as f:
                f.write(contenu)
            os.chmod(os.path.join(suite, nom), 0o755)
        return os.path.join(suite, "collect-all-advise.sh")

    def lancer_suite(self, prog, *args):
        options = ["--program", os.path.join(self.bin, "app-log-live.py"), "--days", "2", "--dest", self.dest, *args]
        chemin = os.path.join(self.d, "config.conf")
        with open(chemin, "w") as f:
            f.write("VM_HOST_201=10.0.0.21\n")
        r = subprocess.run(["bash", prog, "-c", chemin, *options], capture_output=True, text=True, env=self.env, timeout=120)
        return r, re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)

    def test_suite_en_retard_signalee_sans_terminal(self):
        """1.10: SYNC=ask without a terminal: the guests behind are listed with the command to run; nothing is copied."""
        prog = self.suite_locale()
        r, sortie = self.lancer_suite(prog)
        self.assertEqual(r.returncode, 0, sortie)
        self.assertIn("Version de la suite sur cet hôte : app-log-live.py 1.210.20261124.212059", sortie)
        self.assertIn("[ATTN] LXC 101 bbb-lxc1 : 1.200.20261101.000000 (plus ancienne)", sortie)
        self.assertIn("[ATTN] VM 201 bbb-vm1 : 1.200.20261101.000000 (plus ancienne)", sortie)
        self.assertIn("host-perf-audit.py --guest-sync --guests 101,103,201", sortie)
        self.assertFalse(os.path.exists(self.sync_log))
        self.assertIn("[OK] LXC 101 bbb-lxc1", sortie)                                  # the collection still runs

    def test_suite_mise_a_jour_avec_sync(self):
        """1.10: --sync: host-perf-audit.py --guest-sync is run for the guests behind, before the collection."""
        prog = self.suite_locale()
        r, sortie = self.lancer_suite(prog, "--sync")
        self.assertEqual(r.returncode, 0, sortie)
        appel = open(self.sync_log).read()
        self.assertIn("--guest-sync --guests 101,103,201 --sync-source", appel)
        self.assertIn("--yes", appel)
        self.assertIn("[OK] suite mise à jour dans : 101,103,201", sortie)

    def test_suite_a_jour_ou_no_sync(self):
        """1.10: guests up to date: nothing offered; --no-sync: no check at all."""
        prog = self.suite_locale()
        self.env["GUEST_VERSION"] = "1.210.20261124.212059"
        r, sortie = self.lancer_suite(prog, "--sync")
        self.assertIn("[OK] la suite est à jour dans les machines choisies", sortie)
        self.assertFalse(os.path.exists(self.sync_log))
        del self.env["GUEST_VERSION"]
        r, sortie = self.lancer_suite(prog, "--no-sync")
        self.assertNotIn("Version de la suite", sortie)
        self.assertFalse(os.path.exists(self.sync_log))

    def test_port_de_la_vm_et_alias_ssh(self):
        """1.11: VM_PORT_<VMID> gives ssh -p; without it, a Host block of ~/.ssh/config whose HostName is the address of the VM is used
        (its alias); a time out on port 22 gives advice."""
        r = self.lancer("--days", "2", "--dest", self.dest, "--no-sync", config="VM_PORT_201=3815\n")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        journal = open(self.ssh_log).read()
        self.assertIn("root@10.0.0.77 sudo env", journal)
        self.assertIn("port=3815", journal)
        os.remove(self.ssh_log)
        os.makedirs(os.path.join(self.d, ".ssh"))
        with open(os.path.join(self.d, ".ssh", "config"), "w") as f:
            f.write("Ciphers aes128-ctr\nHost vm201\n    HostName 10.0.0.77\n    Port 3815\n")
        r = self.lancer("--days", "2", "--dest", self.dest, "--no-sync", "--verbose")
        self.assertIn("root@vm201 sudo env", open(self.ssh_log).read())
        self.assertIn("alias vm201 de", r.stderr)
        self.assertIn("(port 3815)", r.stderr)
        self.env["SSH_FAIL"] = "ssh: connect to host 10.0.0.77 port 22: Connection timed out"
        os.remove(os.path.join(self.d, ".ssh", "config"))
        r = self.lancer("--days", "2", "--dest", self.dest, "--no-sync")
        self.assertIn("conseil : si SSH écoute sur un autre port, mettez VM_PORT_201=PORT", r.stdout)

    def lancer_sur_terminal(self, args, reponses):
        """Runs the program on a pseudo-terminal (its /dev/tty), sends the answers, returns everything it printed."""
        import pty, select, time
        maitre, esclave = pty.openpty()
        proc = subprocess.Popen(["bash", PROG, "--program", os.path.join(self.bin, "app-log-live.py"), *args], stdin=esclave,
                                stdout=esclave, stderr=esclave, env=self.env, start_new_session=True,
                                preexec_fn=lambda: __import__("fcntl").ioctl(0, __import__("termios").TIOCSCTTY, 0))
        os.close(esclave)
        sortie, fin = b"", time.time() + 60
        while time.time() < fin:
            r, _, _ = select.select([maitre], [], [], 0.2)
            if r:
                try:
                    bloc = os.read(maitre, 4096)
                except OSError:
                    break
                if not bloc:
                    break
                sortie += bloc
                if b"[o/N]" in bloc or b"[y/N]" in bloc:
                    os.write(maitre, reponses.encode())
            elif proc.poll() is not None:
                break
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        os.close(maitre)
        return re.sub(r"\x1b\[[0-9;]*m", "", sortie.decode("utf-8", "replace")).replace("\r", "")

    def test_echec_de_mise_a_jour_de_securite_detaille(self):
        """1.11: a failed apt-get install shows its code, its E: lines, the file of the complete output and advice."""
        apt = os.path.join(self.bin, "apt-get")
        with open(apt, "w") as f:
            f.write(APT.replace('*install*) echo "$*" >> "$APT_LOG" ;;',
                                '*install*) echo "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 123"; exit 100 ;;'))
        os.chmod(apt, 0o755)
        self.env.pop("COLLECT_NO_PROMPT")
        chemin = os.path.join(self.d, "config.conf")
        with open(chemin, "w") as f:
            f.write("SYNC=no\n")
        sortie = self.lancer_sur_terminal(["-c", chemin, "--days", "2", "--dest", self.dest, "--name", "bbb-lxc1"], reponses="o\n")
        self.assertIn("échec de l'installation (code 100, sortie complète :", sortie)
        self.assertIn("    E: Could not get lock", sortie)
        self.assertIn("conseil : apt ou dpkg est déjà utilisé", sortie)

    def test_paquet_a_moitie_installe_conseil_dpkg(self):
        """1.11: "1 not fully installed or removed" in the output of apt-get gives the advice dpkg --audit and dpkg --configure -a."""
        apt = os.path.join(self.bin, "apt-get")
        with open(apt, "w") as f:
            f.write(APT.replace('*install*) echo "$*" >> "$APT_LOG" ;;',
                                '*install*) echo "1 not fully installed or removed."; echo "E: Sub-process /usr/bin/dpkg returned an error code (1)"; exit 100 ;;'))
        os.chmod(apt, 0o755)
        self.env.pop("COLLECT_NO_PROMPT")
        chemin = os.path.join(self.d, "config.conf")
        with open(chemin, "w") as f:
            f.write("SYNC=no\n")
        sortie = self.lancer_sur_terminal(["-c", chemin, "--days", "2", "--dest", self.dest, "--name", "bbb-lxc1"], reponses="o\n")
        self.assertIn("conseil : un paquet est resté à moitié installé : pct enter 101, puis dpkg --audit", sortie)

    def test_minuteur_installe_en_root_refuse_sinon(self):
        dossier_systemd = os.path.join(self.d, "systemd")
        journal = os.path.join(self.d, "systemctl.log")
        with open(os.path.join(self.bin, "systemctl"), "w") as f:
            f.write('#!/bin/bash\necho "$*" >> "$SYSTEMCTL_LOG"\n')
        os.chmod(os.path.join(self.bin, "systemctl"), 0o755)
        self.env["NGINX_TOOLS_SYSTEMD_DIR"] = dossier_systemd
        self.env["SYSTEMCTL_LOG"] = journal
        r = self.lancer("--install-timer", "--days", "2", "--dest", self.dest, config="TIMER_TIME=03:30\n")
        if os.geteuid() != 0:
            self.assertEqual(r.returncode, 1)
            self.assertIn("en root", r.stdout + r.stderr)
            self.assertFalse(os.path.exists(os.path.join(dossier_systemd, "collect-all-advise.timer")))
            return
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        minuteur = open(os.path.join(dossier_systemd, "collect-all-advise.timer"), encoding="utf-8").read()
        self.assertIn("OnCalendar=*-*-* 03:30:00", minuteur)
        service = open(os.path.join(dossier_systemd, "collect-all-advise.service"), encoding="utf-8").read()
        self.assertIn("Environment=COLLECT_NO_PROMPT=1", service)
        self.assertIn("ExecStart=" + os.path.realpath(PROG), service)
        self.assertIn("enable --now collect-all-advise.timer", open(journal).read())
        r = self.lancer("--remove-timer", config="TIMER_TIME=03:30\n")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse(os.path.exists(os.path.join(dossier_systemd, "collect-all-advise.timer")))

    def test_heure_du_minuteur_refusee_si_invalide(self):
        self.env["NGINX_TOOLS_SYSTEMD_DIR"] = os.path.join(self.d, "systemd")
        r = self.lancer("--install-timer", config="TIMER_TIME=25:99\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("TIMER_TIME refusé", r.stdout + r.stderr) if os.geteuid() == 0 else self.assertIn("en root", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
