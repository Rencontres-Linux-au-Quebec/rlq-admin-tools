"""host-perf-audit.py (1.0) et apps/_sysperf.py : ce qui limite les performances d'un hôte Proxmox — processeur, mémoire, disques, ZFS, réseau, invités —,
verdict, réponse à « des disques SSD sont-ils justifiés ? », réglages suggérés, --csv, Ctrl-C. Faux /proc, /sys, /etc/pve, zpool et zfs : aucune mesure réelle."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # program for the Proxmox host: tested everywhere
import importlib.util
import io
import os
import contextlib
import unittest

from helpers import EnvTest, script_path


def charger(nom, chemin, env=None):
    sauvegarde = dict(os.environ)
    os.environ.update(env or {})
    try:
        spec = importlib.util.spec_from_file_location(nom, script_path(chemin))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(sauvegarde)


def faux_proc(racine, ticks=(1000, 0, 500, 8000, 100, 0, 0, 0), io_total=0, disque=(100, 0, 800, 50, 0, 0, 400, 0, 0, 900, 1200)):
    """Arborescence /proc et /sys minimale sous `racine` (compteurs passés en paramètre pour simuler deux instants)."""
    def ecrire(rel, texte):
        p = os.path.join(racine, rel.lstrip("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(texte)
    ecrire("/proc/stat", "cpu  " + " ".join(map(str, ticks)) + "\ncpu0 1 1 1 1 1 0 0 0\ncpu1 1 1 1 1 1 0 0 0\n")
    for kind in ("cpu", "memory"):
        ecrire(f"/proc/pressure/{kind}", "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    ecrire("/proc/pressure/io", f"some avg10=1.00 avg60=1.00 avg300=1.00 total={io_total}\nfull avg10=0.00 avg60=0.00 avg300=0.00 total={io_total // 2}\n")
    ecrire("/proc/diskstats", "   8       0 sda " + " ".join(map(str, disque)) + " 0 0 0 0\n   8       1 sda1 1 0 1 1 1 0 1 1 0 1 1 0 0 0 0\n"
                              "   7       0 loop0 1 0 1 1 1 0 1 1 0 1 1 0 0 0 0\n")
    ecrire("/sys/block/sda/queue/rotational", "1\n")
    ecrire("/sys/block/sda/queue/scheduler", "[mq-deadline] none\n")
    ecrire("/sys/block/sda/device/model", "WDC WD40EFRX\n")
    ecrire("/sys/block/sda/size", "7814037168\n")
    os.makedirs(os.path.join(racine, "sys/block/loop0"), exist_ok=True)
    ecrire("/proc/meminfo", "MemTotal:       32768000 kB\nMemAvailable:   16000000 kB\nSwapTotal:      8000000 kB\nSwapFree:       7000000 kB\n")
    ecrire("/proc/net/dev", "Inter-|   Receive\n face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n"
                            "    lo: 10 1 0 0 0 0 0 0 10 1 0 0 0 0 0 0\n vmbr0: 1048576 10 0 0 0 0 0 0 2097152 20 0 0 0 0 0 0\n")
    ecrire("/proc/loadavg", "0.50 0.40 0.30 1/200 12345\n")
    ecrire("/proc/cpuinfo", "model name\t: AMD Ryzen 7 5700G\n")
    ecrire("/proc/sys/vm/swappiness", "60\n")
    ecrire("/proc/spl/kstat/zfs/arcstats", "13 1 0x01 1 2 3 4\nname type data\nhits 4 9000\nmisses 4 1000\nsize 4 8589934592\nc_max 4 17179869184\nc_min 4 1073741824\n")
    ecrire("/sys/fs/cgroup/cgroup.controllers", "cpu io memory\n")
    cg = "/sys/fs/cgroup/lxc/101"
    ecrire(cg + "/cpu.stat", "usage_usec 5000000\n")
    ecrire(cg + "/memory.current", str(2 * 1024 ** 3) + "\n")
    ecrire(cg + "/memory.max", str(4 * 1024 ** 3) + "\n")
    ecrire(cg + "/io.stat", "8:0 rbytes=1048576 wbytes=2097152 rios=10 wios=20\n")
    ecrire(cg + "/io.pressure", "some avg10=0.00 avg60=0.00 avg300=0.00 total=1000\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")


class SysPerf(unittest.TestCase):
    """apps/_sysperf.py : deux instantanés sur un faux /proc, et leur différence."""

    def test_taux_entre_deux_instantanes(self):
        import tempfile
        import shutil
        d = tempfile.mkdtemp(prefix="test-rlq-sysperf-")
        self.addCleanup(shutil.rmtree, d)
        m = charger("sp_t", "apps/_sysperf.py", {"NGINX_TOOLS_PROC_ROOT": d})
        faux_proc(d)
        a = m.snapshot()
        self.assertEqual(sorted(a["disks"]), ["sda"])                         # partition and loop ignored
        self.assertEqual(a["psi_source"], "/sys/fs/cgroup")
        # 10 s later: 50 % busy, 10 % iowait; disk busy 8 s out of 10; 2 s of I/O wait
        faux_proc(d, ticks=(1400, 0, 600, 8400, 200, 0, 0, 0), io_total=2_000_000, disque=(200, 0, 1600, 2050, 100, 0, 1200, 4000, 0, 8900, 9200))
        b = m.snapshot()
        b["t"] = a["t"] + 10.0
        r = m.rates(a, b)
        self.assertAlmostEqual(r["cpu"]["busy"], 50.0, places=1)
        self.assertAlmostEqual(r["cpu"]["iowait"], 10.0, places=1)
        self.assertAlmostEqual(r["disks"]["sda"]["util"], 80.0, places=1)
        self.assertAlmostEqual(r["disks"]["sda"]["r_await"], 20.0, places=1)    # 2000 ms pour 100 lectures
        self.assertAlmostEqual(r["disks"]["sda"]["w_await"], 40.0, places=1)    # 4000 ms for 100 writes
        self.assertAlmostEqual(r["psi"]["io"]["some"], 20.0, places=1)          # 2 s sur 10 s
        self.assertEqual(m.busiest_disk(r), ("sda", r["disks"]["sda"]["util"]))
        self.assertTrue(m.rotational("sda"))


class Rapport(unittest.TestCase):
    """Analyse sur des échantillons synthétiques (en anglais) : disques HDD saturés → « YES », calmes → « NO »."""

    def setUp(self):
        self.m = charger("hpa_t", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en"})

    def echantillons(self, util, io_some, await_ms, n=20):
        return [{"dt": 60, "wall": 1_800_000_000 + 60 * i, "cpu": {"busy": 30.0, "iowait": io_some / 2, "steal": 0.0, "user": 20, "system": 10, "n": 8},
                 "psi": {"io": {"some": io_some, "full": io_some / 3}, "cpu": {"some": 1.0}, "memory": {"some": 0.0, "full": 0.0}},
                 "disks": {"sda": {"util": util, "r_s": 50, "w_s": 30, "rkb_s": 2048, "wkb_s": 1024, "r_await": await_ms, "w_await": await_ms, "queue": 2.0}},
                 "net": {}, "arc": {"hit": 80.0, "size": 8 * 2 ** 30, "c_max": 8 * 2 ** 30, "c_min": 2 ** 30, "throttle": 0, "l2_hit": None},
                 "mem": {"MemTotal": 32 * 1048576, "MemAvailable": 16 * 1048576}, "load": 2.0, "guests": {}, "psi_source": "/proc/pressure"} for i in range(n)]

    def faits(self):
        return {"host": "pve1", "kernel": "6.8", "pve": "pve-manager/8.2.4", "cpu_model": "AMD", "cores": 8, "governor": "performance", "swappiness": "10",
                "ksm": "0", "ksm_sharing": "0", "thp": "madvise", "arc_max_param": "0", "mem": {"MemTotal": 32 * 1048576, "SwapTotal": 0, "SwapFree": 0},
                "disks": {"sda": {"kind": "HDD", "model": "WDC", "scheduler": "mq-deadline", "size_gb": 4000}}}

    def rapport(self, samples):
        class Args:
            no_guests = True
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fd = self.m.report(samples, self.faits(), {}, {}, {}, lambda s, o: [], Args(), 0.12)
        return out.getvalue(), fd

    def test_hdd_sature_ssd_justifie(self):
        texte, fd = self.rapport(self.echantillons(util=92.0, io_some=22.0, await_ms=45.0))
        self.assertIn("YES: the HDD (sda) are a measured bottleneck", texte)
        self.assertIn("disks are the LIMIT", texte)
        self.assertEqual(fd.verdicts["disks"][0], "bad")
        self.assertIn("this program used 0.12 s of processor in all", texte)
        self.assertIn("« special » mirrored SSD", texte)                                 # intermediate step before replacing everything

    def test_hdd_calmes_ssd_non_justifies(self):
        texte, fd = self.rapport(self.echantillons(util=8.0, io_some=0.5, await_ms=6.0))
        self.assertIn("NO: the HDD are not a limit for this load", texte)
        self.assertEqual(fd.verdicts["disks"][0], "ok")
        self.assertIn("ARC hit ratio only 80 %", " ".join(t for _, t, _, _ in fd.suggestions))     # free RAM: larger ARC suggested, with --apply

    def test_aucun_echantillon(self):
        texte, fd = self.rapport([])
        self.assertIn("No sample taken", texte)

    def test_duree(self):
        self.assertEqual(self.m.parse_duration("90"), 90)
        self.assertEqual(self.m.parse_duration("10m"), 600)
        self.assertEqual(self.m.parse_duration("1h30m"), 5400)
        with self.assertRaises(ValueError):
            self.m.parse_duration("bientôt")


class Programme(EnvTest):
    """Exécution complète (5 s) sur un faux hôte : ZFS, invité nommé, CSV, français."""

    def setUp(self):
        super().setUp()
        self.prog = self.prepare("host-perf-audit.py")
        self.racine = os.path.join(self.d, "racine")
        faux_proc(self.racine)
        self.write("pve/lxc/101.conf", "arch: amd64\nhostname: odoo18\nmemory: 4096\n")
        self.write("pve/qemu-server/120.conf", "name: bbb3\nscsi0: local-zfs:vm-120-disk-0,size=64G\nsata1: local-zfs:vm-120-disk-1,size=8G\ncpu: kvm64\n")
        self.mock("pveversion", 'echo "pve-manager/8.2.4/faaa0b8e (running kernel: 6.8.12-1-pve)"')
        self.mock("zpool", '''case "$*" in
 "list -H -p -o name,size,alloc,free,frag,cap,health") printf "rpool\\t4000000000000\\t3400000000000\\t600000000000\\t55\\t85\\tONLINE\\n";;
 "status -P") printf "  pool: rpool\\n state: ONLINE\\nconfig:\\n\\n\\tNAME\\tSTATE\\n\\trpool\\tONLINE\\n\\t  mirror-0\\tONLINE\\n\\t    /dev/sda2\\tONLINE\\n";;
 "get -H -p -o name,value ashift") printf "rpool\\t12\\n";;
 "iostat -l -H -p") printf "rpool\\t1\\t2\\t3\\t4\\t5\\t6\\t9000000\\t30000000\\t8000000\\t25000000\\t0\\t40000000\\t0\\t20000000\\t0\\n";;
esac''')
        self.mock("zfs", 'printf "rpool/data\\tcompression\\toff\\nrpool/data\\tatime\\ton\\nrpool/data\\trelatime\\toff\\nrpool/data\\tsync\\tstandard\\n"')
        self.env.update(NGINX_TOOLS_PROC_ROOT=self.racine, HOST_PERF_AUDIT_PVE_DIR=os.path.join(self.d, "pve"))

    def test_execution_complete_en_francais_avec_csv(self):
        csv = os.path.join(self.d, "perf.csv")
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "5", "--interval", "1", "--csv", csv, "--lang", "fr"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("Traceback", err)
        self.assertTrue(out.startswith("host-perf-audit.py v1."))
        self.assertIn("Mesure pendant 5 s, un échantillon toutes les 1 s (1 disque(s), 1 invité(s) en marche, pool(s) ZFS : rpool)", out)
        self.assertIn("PERFORMANCES DE ", out)
        self.assertIn("pve-manager/8.2.4", out)
        self.assertIn("PROCESSEUR — AMD Ryzen 7 5700G, 2 cœur(s) logique(s)", out)
        self.assertRegex(out, r"sda\s+HDD\s+0%")
        self.assertIn("pool rpool — 4.00 To, utilisé à 85 %, fragmentation 55 %, ONLINE, ashift 12, vdevs mirror, aucun périphérique special / log / cache", out)
        self.assertIn("attentes moyennes depuis l'importation du pool", out)
        self.assertRegex(out, r"101 lxc\s+odoo18")
        self.assertIn("VERDICT — ce qui limite les performances", out)
        self.assertIn("DES DISQUES SSD SONT-ILS JUSTIFIÉS ?", out)
        self.assertIn("NON : les HDD ne sont pas une limite pour cette charge", out)
        self.assertIn("[MOYENNE] pool rpool : utilisé à 85 % — ZFS ralentit fortement au-delà de 80 %", out)
        self.assertIn("dataset rpool/data : compression désactivée", out)
        self.assertIn("     --apply : zfs set compression=lz4 rpool/data", out)
        self.assertIn("disponible au moins 15.3 Gio (moyenne 15.3 Gio)", out)
        self.assertIn("file synchrone en écriture 40.0 ms", out)
        self.assertNotIn("Processeurs les processeurs sont parfois saturés", out)          # frozen counters: no false 100 %
        self.assertIn("dataset rpool/data : atime=on sans relatime", out)
        self.assertIn("VM 120 (bbb3) : disque sur le bus SATA (émulé, lent)", out)
        self.assertIn("VM 120 (bbb3) : le type de CPU kvm64", out)
        self.assertIn("les écritures synchrones attendent 40 ms en moyenne", out)
        lignes = open(csv).read().splitlines()
        self.assertTrue(lignes[0].startswith("time,cpu_busy,iowait,steal,psi_cpu,psi_io_some"))
        self.assertIn("sda_util", lignes[0])
        self.assertGreaterEqual(len(lignes), 4)

    def test_anglais_et_aide(self):
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "5", "--interval", "2", "--lang", "en", "--no-guests"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("ARE SSD DISKS JUSTIFIED?", out)
        self.assertNotIn("GUESTS", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--help", "--lang", "fr"])
        self.assertIn("--duration", out)
        self.assertIn("Durée de la mesure", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "3"])
        self.assertEqual(rc, 2)
        self.assertIn("--duration attend entre 5 secondes et 7 jours", err)

    def test_ctrl_c_donne_quand_meme_le_rapport(self):
        texte, n = self.run_pty(["python3", self.prog, "--duration", "60", "--interval", "1", "--lang", "fr", "--no-guests"],
                                [(b"donne quand m", b"", 3.5), (b"", b"\x03", 0.2), (b"[o/N]", b"o\r", 0.3)], timeout=60)
        self.assertIn("rapport sur ce qui a été mesuré", texte)
        self.assertIn("DES DISQUES SSD SONT-ILS JUSTIFIÉS ?", texte)


if __name__ == "__main__":
    unittest.main()
