"""system-hardening.sh (1.0) : durcissement du système sur un hôte Proxmox VE 9 (Debian 13), une VM Ubuntu 20.04+ ou Debian 12+, un conteneur LXC
Debian 12+ — unattended-upgrades (sécurité seulement), auditd (règles rlq-*, pas dans un conteneur), AIDE (exclusions, référence), sommaire quotidien
(--notify, minuteur), --rollback, --baseline-update. Outils système simulés ; tous les chemins sont dans le dossier du test."""
import os
import unittest

from helpers import EnvTest, ROOT_SIMULE, SANS_ROOT_SIMULE

ENVIRONNEMENT = "commun"
PROGRAMME = "system-hardening.sh"

OS_RELEASES = {
    "debian12": 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nID=debian\nVERSION_ID="12"\nVERSION_CODENAME=bookworm\n',
    "debian13": 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n',
    "ubuntu20": 'PRETTY_NAME="Ubuntu 20.04.6 LTS"\nID=ubuntu\nVERSION_ID="20.04"\nVERSION_CODENAME=focal\n',
    "debian11": 'PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"\nID=debian\nVERSION_ID="11"\nVERSION_CODENAME=bullseye\n',
}


class SystemHardening(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("system-hardening.sh")
        self.etc_default = os.path.join(self.d, "etc-default-vide")
        os.makedirs(self.etc_default, exist_ok=True)
        self.installed = self.write("state/installed.txt", "")
        self.chemins = {
            "SYSTEM_HARDENING_APT_DIR": self.path("apt.conf.d", "x")[:-2],
            "SYSTEM_HARDENING_AUDIT_DIR": self.path("audit", "rules.d", "x")[:-2],
            "SYSTEM_HARDENING_AIDE_DIR": self.path("aide", "aide.conf.d", "x")[:-2],
            "SYSTEM_HARDENING_AIDE_CONF": self.write("aide/aide.conf", "# aide\n"),
            "SYSTEM_HARDENING_AIDE_DB": self.path("lib-aide", "x")[:-2],
            "SYSTEM_HARDENING_AIDE_LOG": os.path.join(self.d, "log-aide", "aide.log"),
            "SYSTEM_HARDENING_AIDE_CRON": os.path.join(self.d, "cron.daily", "aide"),
            "SYSTEM_HARDENING_UU_LOG": os.path.join(self.d, "log-uu", "unattended-upgrades.log"),
            "SYSTEM_HARDENING_REBOOT_FILE": os.path.join(self.d, "run", "reboot-required"),
            "SYSTEM_HARDENING_SYSTEMD_DIR": self.path("systemd", "x")[:-2],
            "SYSTEM_HARDENING_LXC_DIR": self.path("lxc", "x")[:-2],
            "SYSTEM_HARDENING_MODULES_DIR": self.path("modules", "x")[:-2],
            "SYSTEM_HARDENING_HOME_ROOT": self.path("home", "x")[:-2],
            "SYSTEM_HARDENING_ROOT_HOME": self.path("root", "x")[:-2],
            "SYSTEM_HARDENING_ODOO_CONFS": os.path.join(self.d, "odoo", "*.conf"),
            "SYSTEM_HARDENING_OS_RELEASE": os.path.join(self.d, "os-release"),
        }
        os.makedirs(os.path.join(self.chemins["SYSTEM_HARDENING_ROOT_HOME"], ".ssh"))
        os.makedirs(os.path.join(self.chemins["SYSTEM_HARDENING_HOME_ROOT"], "alice", ".ssh"))
        self.write("odoo/odoo.conf", "[options]\ndata_dir = /srv/odoo-data\n")
        self.mock("dpkg-query", f'p="${{@: -1}}"; grep -qx "$p" {self.installed} && echo "install ok installed"; exit 0')
        self.mock("apt-get", f'echo "$@" >> {self.d}/apt.log\n'
                             f'case " $* " in *" -s "*) printf "Inst libssl3 [3.0.1] (3.0.2 Debian-Security:12/stable-security [amd64])\\nInst vim [1] (2 Debian:12/stable [amd64])\\n";; '
                             f'*" install "*) for a in "$@"; do case "$a" in -*|install|*=*) ;; *) echo "$a" >> {self.installed};; esac; done;; esac; exit 0')
        self.mock("systemctl", f'echo "$@" >> {self.d}/systemctl.log; exit 0')
        self.mock("augenrules", f'echo "$@" >> {self.d}/augenrules.log; exit 0')
        self.mock("auditctl", 'echo "-w /etc/sudoers -p wa -k rlq-sudo"; echo "-w /etc/crontab -p wa -k rlq-cron"')
        self.mock("ausearch", 'case "$*" in *rlq-ssh-keys*) printf -- "----\\ntype=SYSCALL\\n----\\ntype=SYSCALL\\n";; *) exit 1;; esac')
        self.mock("aide", f'echo "$@" >> {self.d}/aide.log; case " $* " in *" --update "*) echo nouvelle > {self.chemins["SYSTEM_HARDENING_AIDE_DB"]}/aide.db.new; exit 5;; esac; exit 0')
        self.mock("aideinit", f'echo "$@" >> {self.d}/aideinit.log; echo base > {self.chemins["SYSTEM_HARDENING_AIDE_DB"]}/aide.db')
        self.mock("python3", f'echo "$@" >> {self.d}/mail.log; exit 0')          # only the mail call of the program goes through python3

    def machine(self, os_name, virt):
        """virt: lxc (container), kvm (VM), proxmox (host: pveversion present, no virtualization)."""
        self.write("os-release", OS_RELEASES[os_name])
        conteneur = "echo lxc; exit 0" if virt == "lxc" else "exit 1"
        vm = "echo kvm; exit 0" if virt == "kvm" else "echo none; exit 1"
        self.mock("systemd-detect-virt", f'case "$1" in --container) {conteneur};; --vm) {vm};; esac')
        if virt == "proxmox":
            self.mock("pveversion", 'echo "pve-manager/9.0.10/abcdef (running kernel: 6.14.8-2-pve)"')

    def lancer(self, *args, env_extra=None):
        env = dict(self.chemins, NGINX_TOOLS_ETC_DEFAULT=self.etc_default, **(env_extra or {}))
        return self.run_cmd(["bash", self.prog, *args], env)

    def fichier(self, cle, nom):
        return os.path.join(self.chemins[cle], nom)

    def lire(self, chemin):
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    # --- LXC container, Debian 12 ---------------------------------------------------------------------------------
    def test_conteneur_lxc_verification_puis_update(self):
        self.machine("debian12", "lxc")
        rc, out, err = self.lancer()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("conteneur LXC", out)
        self.assertIn("[ÉCHEC] paquet unattended-upgrades absent", out)
        self.assertIn("l'audit du noyau appartient à l'hôte Proxmox", out)
        self.assertFalse(os.path.exists(self.fichier("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades")))     # check only: nothing written
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 0, out + err)
        installes = self.lire(self.installed).split()
        self.assertIn("unattended-upgrades", installes)
        self.assertIn("aide", installes)
        self.assertNotIn("auditd", installes)                                  # no kernel audit in a container
        uu = self.lire(self.fichier("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades"))
        self.assertIn("#clear Unattended-Upgrade::Origins-Pattern;", uu)
        self.assertIn("label=Debian-Security", uu)
        self.assertIn('Unattended-Upgrade::Automatic-Reboot "false";', uu)
        self.assertNotIn("Ubuntu", uu)
        self.assertFalse(os.path.exists(self.fichier("SYSTEM_HARDENING_AUDIT_DIR", "60-rlq-hardening.rules")))
        aide = self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DIR", "99_rlq_exclusions"))
        self.assertIn("!/var/lib/postgresql", aide)
        self.assertIn("!/srv/odoo-data", aide)                                 # data_dir of the Odoo configuration found
        self.assertIn("!/var/bigbluebutton", aide)
        self.assertTrue(os.path.exists(self.fichier("SYSTEM_HARDENING_AIDE_DB", "aide.db")))
        self.assertIn("-y -f", self.lire(os.path.join(self.d, "aideinit.log")))
        timer = self.lire(self.fichier("SYSTEM_HARDENING_SYSTEMD_DIR", "system-hardening-notify.timer"))
        self.assertIn("OnCalendar=*-*-* 07:30:00", timer)
        self.assertIn("--notify", self.lire(self.fichier("SYSTEM_HARDENING_SYSTEMD_DIR", "system-hardening-notify.service")))
        self.assertIn("enable --now system-hardening-notify.timer", self.lire(os.path.join(self.d, "systemctl.log")))
        rc, out, err = self.lancer()
        self.assertEqual(rc, 0, out + err)
        self.assertIn("aucun échec", out)
        self.assertIn("1 correctif(s) de sécurité en attente", out)          # vim is not a security update

    def test_update_idempotent(self):
        self.machine("debian12", "lxc")
        self.lancer("--update")
        uu = self.fichier("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades")
        os.utime(uu, (1000000000, 1000000000))
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(os.path.getmtime(uu), 1000000000)                       # same content: not rewritten
        self.assertIn("configuration déjà à jour", out)
        self.assertIn("base de référence déjà présente", out)

    # --- Proxmox host, Debian 13 ------------------------------------------------------------------------------------
    def test_hote_proxmox_regles_d_audit_et_conteneurs(self):
        self.machine("debian13", "proxmox")
        racine = os.path.join(self.chemins["SYSTEM_HARDENING_LXC_DIR"], "101", "rootfs")
        for sous in ("etc/cron.d", "root/.ssh", "home/bob/.ssh"):
            os.makedirs(os.path.join(racine, sous))
        self.write(os.path.join("lxc", "101", "rootfs", "etc", "passwd"), "root:x:0:0::/root:/bin/bash\n")
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("hôte Proxmox VE", out)
        self.assertIn("auditd", self.lire(self.installed).split())
        regles = self.lire(self.fichier("SYSTEM_HARDENING_AUDIT_DIR", "60-rlq-hardening.rules"))
        self.assertIn(f"-w {self.chemins['SYSTEM_HARDENING_ROOT_HOME']}/.ssh -p wa -k rlq-ssh-keys", regles)
        self.assertIn(f"-w {self.chemins['SYSTEM_HARDENING_HOME_ROOT']}/alice/.ssh -p wa -k rlq-ssh-keys", regles)
        self.assertIn(f"-w {racine}/root/.ssh -p wa -k rlq-ssh-keys", regles)          # files of the running container, seen from the host
        self.assertIn(f"-w {racine}/home/bob/.ssh -p wa -k rlq-ssh-keys", regles)
        self.assertIn(f"-w {racine}/etc/passwd -p wa -k rlq-identity", regles)
        self.assertNotIn(f"{racine}/etc/shadow", regles)                                # a missing file is never watched (augenrules would refuse)
        self.assertIn("--load", self.lire(os.path.join(self.d, "augenrules.log")))
        self.assertIn("!/etc/pve", self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DIR", "99_rlq_exclusions")))
        self.assertIn("paquets de Proxmox se mettent à jour à la main", out)
        rc, out, err = self.lancer()
        self.assertIn("2 règles rlq-* chargées dans le noyau", out)
        self.assertIn("rlq-ssh-keys 2", out)                                            # events of the last 24 h

    def test_hote_proxmox_sans_les_conteneurs(self):
        self.machine("debian13", "proxmox")
        os.makedirs(os.path.join(self.chemins["SYSTEM_HARDENING_LXC_DIR"], "102", "rootfs", "etc"))
        self.write("etc-default-vide/system-hardening.conf", "AUDIT_WATCH_CONTAINERS=no\n")
        self.lancer("--update")
        self.assertNotIn("/102/rootfs", self.lire(self.fichier("SYSTEM_HARDENING_AUDIT_DIR", "60-rlq-hardening.rules")))

    # --- Ubuntu 20.04 VM -----------------------------------------------------------------------------------------------
    def test_vm_ubuntu_2004(self):
        self.machine("ubuntu20", "kvm")
        self.mock("update-aide.conf", f'echo run >> {self.d}/update-aide.log')
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("machine virtuelle (kvm)", out)
        uu = self.lire(self.fichier("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades"))
        self.assertIn("origin=Ubuntu,archive=${distro_codename}-security", uu)
        self.assertIn("UbuntuESMApps", uu)
        self.assertNotIn("Debian-Security", uu)
        self.assertTrue(os.path.exists(os.path.join(self.d, "update-aide.log")))      # Ubuntu 20.04: the AIDE configuration is generated
        self.assertIn("auditd", self.lire(self.installed).split())

    def test_redemarrage_en_attente_noyau_plus_recent(self):
        self.machine("ubuntu20", "kvm")
        os.makedirs(os.path.join(self.chemins["SYSTEM_HARDENING_MODULES_DIR"], "999.0.0-test"))
        rc, out, err = self.lancer()
        self.assertIn("redémarrage en attente : noyau 999.0.0-test installé", out)

    # --- unsupported, root, configuration, English ------------------------------------------------------------------
    def test_systeme_non_prevu(self):
        self.machine("debian11", "kvm")
        rc, out, err = self.lancer()
        self.assertIn("système non prévu", out)
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.fichier("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades")))

    @unittest.skipUnless(ROOT_SIMULE, "lancé en root : le refus sans root ne peut pas être simulé")
    def test_update_sans_root_refuse(self):
        self.machine("debian12", "lxc")
        rc, out, err = self.lancer("--update", env_extra=SANS_ROOT_SIMULE)
        self.assertEqual(rc, 1)
        self.assertIn("--update demande root", err)

    def test_configuration_redemarrage_automatique_et_valeur_invalide(self):
        self.machine("debian12", "lxc")
        self.write("etc-default-vide/system-hardening.conf", "AUTOMATIC_REBOOT=yes\nAUTOMATIC_REBOOT_TIME=04:15\nNOTIFY_TIME=25:00\nAIDE_EXCLUDE=/opt/sauvegardes\n")
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Configuration lue :", out)
        self.assertIn("redémarrage automatique oui (04:15)", out)
        self.assertIn("valeur de configuration ignorée : NOTIFY_TIME=25:00", err)
        uu = self.lire(self.fichier("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades"))
        self.assertIn('Automatic-Reboot "true";', uu)
        self.assertIn('Automatic-Reboot-Time "04:15";', uu)
        self.assertIn("07:30:00", self.lire(self.fichier("SYSTEM_HARDENING_SYSTEMD_DIR", "system-hardening-notify.timer")))   # invalid time: default kept
        self.assertIn("!/opt/sauvegardes", self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DIR", "99_rlq_exclusions")))

    def test_anglais(self):
        self.machine("debian12", "lxc")
        rc, out, err = self.lancer("--lang", "en")
        self.assertIn("[FAIL] package unattended-upgrades missing", out)
        self.assertIn("LXC container", out)

    # --- rollback, AIDE baseline, daily summary -------------------------------------------------------------------
    def test_rollback_retire_seulement_ses_fichiers(self):
        self.machine("debian13", "proxmox")
        self.lancer("--update")
        autre = self.write(os.path.join("apt.conf.d", "50unattended-upgrades"), "// distribution\n")
        rc, out, err = self.lancer("--rollback")
        self.assertEqual(rc, 0, out + err)
        for cle, nom in (("SYSTEM_HARDENING_APT_DIR", "52rlq-unattended-upgrades"), ("SYSTEM_HARDENING_AUDIT_DIR", "60-rlq-hardening.rules"),
                         ("SYSTEM_HARDENING_AIDE_DIR", "99_rlq_exclusions"), ("SYSTEM_HARDENING_SYSTEMD_DIR", "system-hardening-notify.timer")):
            self.assertFalse(os.path.exists(self.fichier(cle, nom)), nom)
        self.assertTrue(os.path.exists(autre))                                            # a file of the distribution is never touched
        self.assertIn("disable --now system-hardening-notify.timer", self.lire(os.path.join(self.d, "systemctl.log")))
        self.assertIn("auditd", self.lire(self.installed).split())                        # packages stay
        rc, out, err = self.lancer("--rollback")
        self.assertIn("rien à retirer", out)

    def test_condenses_d_aide_sha512_et_retour_arriere(self):
        """1.1 : « Checksums = H » (tous les condensés compilés) devient sha512 ; l'ancienne ligne est gardée et remise par --rollback ; base recréée."""
        self.machine("debian12", "lxc")
        conf = self.chemins["SYSTEM_HARDENING_AIDE_CONF"]
        with open(conf, "w") as f:
            f.write("# H specifies that all checksums compiled in are used\nChecksums = H\nStaticFile = m+c+Checksums\n")
        self.write(os.path.join("lib-aide", "aide.db"), "ancienne")
        with open(self.installed, "w") as f:
            f.write("aide\n")                                                             # AIDE installed: its configuration is checked
        rc, out, err = self.lancer()
        self.assertIn("Checksums = H : TOUS les condensés compilés", out)
        rc, out, err = self.lancer("--update")
        self.assertEqual(rc, 0, out + err)
        texte = self.lire(conf)
        self.assertIn("Checksums = sha512\nStaticFile = m+c+Checksums", texte)        # changed where the groups are defined, before them
        self.assertIn("# Checksums = H", texte)
        self.assertIn("la base de référence est recréée", out)
        self.assertEqual(self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DB", "aide.db.previous")), "ancienne")
        self.assertEqual(self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DB", "aide.db")).strip(), "base")
        rc, out, err = self.lancer()
        self.assertIn("condensés d'AIDE : Checksums = sha512", out)
        rc, out, err = self.lancer("--update")
        self.assertNotIn("recréée", out)                                               # nothing changed: the baseline stays
        rc, out, err = self.lancer("--rollback")
        self.assertIn("ligne Checksums d'origine remise", out)
        self.assertEqual(self.lire(conf), "# H specifies that all checksums compiled in are used\nChecksums = H\nStaticFile = m+c+Checksums\n")

    def test_condenses_d_aide_gardes_avec_keep(self):
        self.machine("debian12", "lxc")
        conf = self.chemins["SYSTEM_HARDENING_AIDE_CONF"]
        with open(conf, "w") as f:
            f.write("Checksums = H\n")
        self.write("etc-default-vide/system-hardening.conf", "AIDE_CHECKSUMS=keep\n")
        self.lancer("--update")
        self.assertEqual(self.lire(conf), "Checksums = H\n")

    def test_baseline_update_nouvelle_reference(self):
        self.machine("debian12", "lxc")
        self.write(os.path.join("lib-aide", "aide.db"), "ancienne")
        rc, out, err = self.lancer("--baseline-update")
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DB", "aide.db")).strip(), "nouvelle")
        self.assertEqual(self.lire(self.fichier("SYSTEM_HARDENING_AIDE_DB", "aide.db.previous")), "ancienne")
        self.assertFalse(os.path.exists(self.fichier("SYSTEM_HARDENING_AIDE_DB", "aide.db.new")))

    def test_notify_courriel_quand_il_y_a_quelque_chose(self):
        self.machine("debian12", "lxc")
        self.lancer("--update")
        self.write("run/reboot-required", "*** System restart required ***\n")
        self.write("run/reboot-required.pkgs", "libc6\n")
        self.write("log-aide/aide.log", "AIDE found differences between database and filesystem!!\n  Added entries:\t\t2\n  Changed entries:\t\t1\n")
        import time
        maintenant = time.strftime("%Y-%m-%d %H:%M:%S")
        self.write("log-uu/unattended-upgrades.log", f"{maintenant},123 INFO Packages that will be upgraded: libssl3 openssl\n2020-01-01 00:00:00,1 INFO Packages that will be upgraded: vieux\n")
        self.write("etc-default-vide/nginx-tools-mail.conf", "MAIL_HOST=smtp.exemple.org\nMAIL_TO=admin@exemple.org\n")
        rc, out, err = self.lancer("--notify")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("correctifs de sécurité installés : libssl3 openssl", out)
        self.assertNotIn("vieux", out)
        self.assertIn("redémarrage en attente :", out)
        self.assertIn("(libc6)", out)
        self.assertIn("Added entries: 2", out)
        self.assertIn("[OK] courriel envoyé", out)
        appel = self.lire(os.path.join(self.d, "mail.log"))
        self.assertIn("apps/_courriel.py --send", appel)
        self.assertIn("à regarder", appel)

    def test_notify_rien_a_signaler_pas_de_courriel(self):
        self.machine("debian12", "lxc")
        self.lancer("--update")
        self.write("log-aide/aide.log", "AIDE found NO differences between database and filesystem. Looks okay!!\n")
        self.write("etc-default-vide/nginx-tools-mail.conf", "MAIL_HOST=smtp.exemple.org\nMAIL_TO=admin@exemple.org\n")
        rc, out, err = self.lancer("--notify")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("[OK] rien à signaler", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "mail.log")))
        self.write("etc-default-vide/system-hardening.conf", "NOTIFY_ALWAYS=yes\n")
        self.lancer("--notify")
        self.assertIn("rien à signaler", self.lire(os.path.join(self.d, "mail.log")))

    def test_notify_sans_courriel_configure(self):
        self.machine("debian12", "lxc")
        self.write("run/reboot-required", "x\n")
        rc, out, err = self.lancer("--notify")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("courriel non envoyé", err)


if __name__ == "__main__":
    unittest.main()
