"""sync-crowdsec-blocklist.sh — IP protégées (nomatch), course « grep -q », garde-fous, crochet ufw."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)
PROGRAMME = "sync-crowdsec-blocklist.sh"   # run-all 1.188 (statistics): the module name does not designate the program
import os
import unittest

from helpers import EnvTest, LISTE_EXEMPLE, IPS_EXEMPLE

FAUX_IPSET = r'''
import sys, json, os, ipaddress
D = os.environ["TEST_IPSET_DB"]
S = json.load(open(D)) if os.path.exists(D) else {}
def save(): json.dump(S, open(D, "w"))
a = sys.argv[1:]
def best(name, ip):
    ip = ipaddress.ip_address(ip); m = None
    for e, f in S.get(name, {}).items():
        n = ipaddress.ip_network(e, strict=False)
        if ip.version == n.version and ip in n and (m is None or n.prefixlen > m[0].prefixlen): m = (n, f)
    return m
if a[0] == "create":
    if a[1] in S and "-exist" not in a: sys.exit(1)
    S.setdefault(a[1], {}); save()
elif a[0] == "destroy": S.pop(a[1], None); save()
elif a[0] == "rename": S[a[2]] = S.pop(a[1]); save()
elif a[0] == "swap": S[a[1]], S[a[2]] = S[a[2]], S[a[1]]; save()
elif a[0] == "add": S[a[1]][a[2]] = {"nomatch": "nomatch" in a}; save()
elif a[0] == "del":
    if a[2] in S.get(a[1], {}): del S[a[1]][a[2]]; save()
    else: sys.exit(1)
elif a[0] == "test":
    m = best(a[1], a[2]); sys.exit(0 if m and not m[1]["nomatch"] else 1)
elif a[0] == "restore":
    for line in sys.stdin:
        p = line.split()
        if len(p) >= 3 and p[0] == "add": S[p[1]].setdefault(p[2], {"nomatch": False})
    save()
elif a[0] == "list":
    if a[1] == "-n":
        # ONE WRITE PER LINE, flushed at once: reproduces the "| grep -q" race (reader closed while still writing)
        for n in S:
            try: sys.stdout.write(n + "\n"); sys.stdout.flush()
            except BrokenPipeError: os._exit(141)
        sys.exit(0)
    if a[1] not in S: sys.exit(1)
    print("Members:")
    for e, f in S[a[1]].items(): print(e + " packets 0 bytes 0" + (" nomatch" if f["nomatch"] else ""))
'''

EQUIPE = ["11.126.46.49", "11.137.240.62"]


class SyncCrowdsec(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("sync-crowdsec-blocklist.sh", {"/etc/iptables": os.path.dirname(self.path("etc-iptables", "x"))})
        self.mock("ipset", FAUX_IPSET, shebang="#!/usr/bin/env python3")
        for t in ("iptables", "ip6tables"):
            self.mock(t, f'F={self.d}/r.{t}; touch $F; o=$1; shift; case $o in -C) grep -qxF "$*" $F;; -I) echo "$*" >> $F;; '
                         f'-D) grep -vxF "$*" $F > $F.t; mv $F.t $F;; esac')
        self.mock("nginx", '[[ "$1" == -T ]] && printf "location ~ x {\\n' + "".join(f"    allow {ip};\\n" for ip in ["127.0.0.1"] + EQUIPE) + '    deny all;\\n}\\n"')
        self.liste = self.path("www", "liste.txt")
        self.mock("curl", 'for a in "$@"; do [[ "$a" == *icanhazip* ]] && { echo 11.85.38.12; exit 0; }; done\n'
                          'out=""; prev=""; for a in "$@"; do [[ "$prev" == "-o" ]] && out="$a"; prev="$a"; done\n'
                          f'cp {self.liste} "$out"')
        self.mock("dpkg-query", f'[[ "$*" == *ufw* ]] && {{ [[ -f {self.d}/ufw-installe ]] && echo "install ok installed" || exit 1; }}; echo "install ok installed"')
        self.mock("apt-get", f'echo "apt-get $*" >> {self.d}/apt.log')
        self.mock_exit("netfilter-persistent"); self.mock_exit("logger"); self.mock_exit("debconf-set-selections")
        self.env.update(TEST_IPSET_DB=self.path("ipset.json"), SYNC_CROWDSEC_STATE_DIR=os.path.dirname(self.path("state", "x")),
                        SYNC_CROWDSEC_CRON_FILE=self.path("cron"), SYNC_CROWDSEC_ALLOW_FILE=self.path("allow"),
                        SYNC_CROWDSEC_UFW_AFTER_INIT=self.path("ufw", "after.init"))

    def ecrire_liste(self, extra=(), n=300):
        with open(self.liste, "w") as f:
            f.writelines(f"{e}\n" for e in extra)
            f.writelines(f"198.51.{i // 250}.{i % 250}\n" for i in range(n))

    def sync(self, *args):
        return self.run_cmd(["bash", self.prog, "--source", "http://exemple.test/liste.txt", *args])

    def bloquee(self, ip):
        return self.run_cmd(["ipset", "test", "crowdsec-blocklist-v4", ip])[0] == 0

    @unittest.skipUnless(os.geteuid() == 0, "la synchronisation exige root")
    def test_report_err_sur_un_echec_en_cours(self):
        self.ecrire_liste()
        self.mock("ipset", 'echo "ipset v7.19: Kernel error received: Operation not supported" >&2; exit 1')
        self.mock("curl", f'echo telecharge >> {self.d}/curl.log; exit 1')
        self.sync()
        rc, out, err = self.run_cmd(["bash", self.prog, "--status", "--report-err"])
        rapport = out[out.index("RAPPORT D'ERREURS"):]
        self.assertRegex(rapport, r"Programme : sync-crowdsec-blocklist\.sh v1\.\d+\.\d{8}\.\d{6} — commande : sync-crowdsec-blocklist\.sh --status\n")
        self.assertRegex(rapport, r"ÉCHECS \(\d+\) :\n(?:.*\n)*?  \d+\. .*ÉCHEC EN COURS : 1 tentatives consécutives")

    # --- 1.10: visible failures, dated and tracked; PATH under cron ------------------------------------------------------
    @unittest.skipUnless(os.geteuid() == 0, "la synchronisation exige root")
    def test_echec_ipset_diagnostic_suivi_puis_efface(self):
        """Cas réel : « impossible de créer les ipsets », sans date, répété à chaque passage du cron."""
        self.ecrire_liste()
        bon_ipset = open(self.path("bin", "ipset")).read()
        self.mock("ipset", 'echo "ipset v7.19: Kernel error received: Operation not supported" >&2; exit 1')
        self.mock("curl", f'echo telecharge >> {self.d}/curl.log; exit 1')
        rc, out, err = self.sync()
        self.assertEqual(rc, 1)
        self.assertRegex(out.splitlines()[0], r"^sync-crowdsec-blocklist\.sh v\d")                        # version header
        self.assertRegex(out.splitlines()[1], r"^Configuration : ")                                   # configuration file read (2 lines: Configuration..., Options...)
        self.assertRegex(out.splitlines()[3], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+$")             # dated
        self.assertIn("ipset inutilisable : module noyau ip_set non disponible (ipset v7.19: Kernel error", err)
        self.assertFalse(os.path.exists(self.path("curl.log")), "liste téléchargée malgré ipset inutilisable")
        self.assertIn("ÉCHEC n° 1 consécutif", err)
        rc, out, err = self.sync()
        self.assertIn("ÉCHEC n° 2 consécutif, depuis le ", err)
        rc, out, err = self.run_cmd(["bash", self.prog, "--status"])
        self.assertIn("ÉCHEC EN COURS : 2 tentatives consécutives", out)
        # Insufficient rights: other diagnosis (no more systematic LXC accusation)
        self.mock("ipset", 'echo "ipset v7.19: Operation not permitted" >&2; exit 1')
        rc, out, err = self.sync()
        self.assertIn("droits insuffisants pour ipset", err)
        # Success: tracking erased
        with open(self.path("bin", "ipset"), "w") as f:
            f.write(bon_ipset)
        self.setUp_curl()
        rc, out, err = self.sync()
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(self.path("state", "last-failure")))
        rc, out, err = self.run_cmd(["bash", self.prog, "--status"])
        self.assertNotIn("ÉCHEC EN COURS", out)

    def setUp_curl(self):
        self.mock("curl", 'for a in "$@"; do [[ "$a" == *icanhazip* ]] && { echo 11.85.38.12; exit 0; }; done\n'
                          'out=""; prev=""; for a in "$@"; do [[ "$prev" == "-o" ]] && out="$a"; prev="$a"; done\n'
                          f'cp {self.liste} "$out"')

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_cron_sans_path_complete_et_cron_neuf_avec_path(self):
        """Cause réelle : cron (PATH=/usr/bin:/bin) ne trouvait ni ipset ni iptables, dans /usr/sbin."""
        self.ecrire_liste()
        self.write("cron", "# Généré par sync-crowdsec-blocklist.sh --install-cron — ne pas éditer à la main.\n"
                           "17 * * * * root /root/scripts/sync-crowdsec-blocklist.sh >>/var/log/sync-crowdsec-blocklist.log 2>&1\n")
        rc, out, err = self.sync()
        self.assertEqual(rc, 0, err)
        cron = open(self.path("cron")).read()
        self.assertIn("\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n", cron)
        self.assertIn("17 * * * * root", cron)                                      # original line kept
        rc, out, err = self.sync()
        self.assertEqual(open(self.path("cron")).read().count("PATH="), 1)          # une seule fois
        os.remove(self.path("cron"))
        self.run_cmd(["bash", self.prog, "--install-cron"])
        self.assertIn("\nPATH=/usr/local/sbin", open(self.path("cron")).read())

    @unittest.skipUnless(os.geteuid() == 0, "exige root")
    def test_liste_unique_de_l_equipe_protegee(self):
        """1.12 : adresses de la liste blanche (/etc/default/nginx-tools-white-list.conf) protégées même sans liste « allow » nginx (BBB) ;
        les lieux [protégée] aussi, un lieu simplement [partagée] ou nommé jamais."""
        self.liste_blanche(LISTE_EXEMPLE)
        self.lieux("192.0.2.0/24  # Université exemple  [partagée]\n198.51.100.128/25  # Bureau  [protégée]\n192.0.2.7  # Maison\n")
        self.mock("nginx", "exit 1")
        rc, out, err = self.run_cmd(["bash", self.prog, "--status"])
        ligne = next(l for l in out.splitlines() if l.startswith("IP protégées"))
        for ip in IPS_EXEMPLE + ("198.51.100.128/25",):
            self.assertIn(ip, ligne)
        self.assertNotIn("192.0.2.0/24", ligne)                                      # shared only: not protected
        self.assertNotIn("192.0.2.7", ligne)

    def test_ip_protegees_jamais_bloquees_meme_via_une_plage(self):
        """1.4 : exclusion par « nomatch » — l'IP exacte ET une plage /16 qui contient une IP protégée."""
        self.ecrire_liste(["11.126.46.49", "11.137.0.0/16", "11.85.38.12", "10.1.2.3", "192.168.1.1"])
        rc, out, err = self.sync()
        self.assertEqual(rc, 0, err)
        for ip in EQUIPE + ["11.85.38.12"]:
            self.assertFalse(self.bloquee(ip), f"{ip} (protégée) bloquée")
        self.assertTrue(self.bloquee("11.137.1.1"), "le reste de la plage /16 doit rester bloqué")
        self.assertTrue(self.bloquee("198.51.0.10"))
        self.assertIn("figurait dans la liste communautaire", out)
        import json
        entrees = json.load(open(self.env["TEST_IPSET_DB"]))["crowdsec-blocklist-v4"]
        self.assertNotIn("10.1.2.3", entrees)                      # private networks discarded as early as the analysis

    def test_redemarrage_ufw_recree_la_regle_malgre_la_course_grep_q(self):
        """1.4 : « ipset list -n | grep -q » sous pipefail répondait « absent » (course SIGPIPE) — 0/10 avant."""
        self.ecrire_liste()
        self.sync()
        for i in range(10):
            with open(self.env["TEST_IPSET_DB"], "w") as f:
                f.write("{}")
            for t in ("iptables", "ip6tables"):
                p = os.path.join(self.d, f"r.{t}")
                if os.path.exists(p):
                    os.remove(p)
            self.run_cmd(["bash", self.prog, "--ufw-start"])
            with self.subTest(essai=i):
                self.assertIn("crowdsec-blocklist-v4", open(os.path.join(self.d, "r.iptables")).read())
                self.assertFalse(self.bloquee("11.126.46.49"), "exclusions non reposées au démarrage")

    def test_liste_trop_petite_refusee_ipsets_intacts(self):
        self.ecrire_liste(); self.sync()
        with open(self.liste, "w") as f:
            f.write("1.2.3.4\n")
        rc, _, err = self.sync()
        self.assertEqual(rc, 1)
        self.assertIn("mise à jour ANNULÉE", err)
        self.assertTrue(self.bloquee("198.51.0.10"), "ipsets modifiés malgré le refus")

    def test_liste_perimee_avertit(self):
        self.ecrire_liste(); self.sync()
        with open(os.path.join(self.env["SYNC_CROWDSEC_STATE_DIR"], "last-list-change"), "w") as f:
            import time
            f.write(str(int(time.time()) - 4 * 86400))
        _, out, _ = self.sync()
        self.assertIn("la liste n'a pas changé depuis 4 jours", out)

    def test_ufw_installe_jamais_iptables_persistent(self):
        """1.1 : installer iptables-persistent supprimerait ufw."""
        open(os.path.join(self.d, "ufw-installe"), "w").close()
        self.mock("dpkg-query", '[[ "$*" == *ufw* ]] && { echo "install ok installed"; exit 0; }; exit 1')
        self.ecrire_liste()
        self.sync()
        apt = open(os.path.join(self.d, "apt.log")).read() if os.path.exists(os.path.join(self.d, "apt.log")) else ""
        self.assertNotIn("iptables-persistent", apt)

    def test_crochet_ufw_retire_a_l_identique(self):
        original = "#!/bin/sh\nset -e\ncase \"$1\" in\nstart) ;;\nesac\n"
        after = self.write("ufw/after.init", original, 0o644)
        open(os.path.join(self.d, "ufw-installe"), "w").close()
        self.ecrire_liste(); self.sync()
        self.run_cmd(["bash", self.prog, "--ufw-hook"])
        self.assertIn("BEGIN sync-crowdsec-blocklist", open(after).read())
        rc, _, _ = self.run_cmd(["sh", after, "start"])
        self.assertEqual(rc, 0, "after.init ne doit jamais échouer")
        self.run_cmd(["bash", self.prog, "--ufw-hook-remove"])
        self.assertEqual(open(after).read(), original)
        self.assertEqual(oct(os.stat(after).st_mode & 0o777), "0o644")


if __name__ == "__main__":
    unittest.main()
