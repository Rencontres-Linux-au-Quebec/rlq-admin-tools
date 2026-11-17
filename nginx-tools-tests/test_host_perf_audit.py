"""host-perf-audit.py (1.0) et apps/_sysperf.py : ce qui limite les performances d'un hôte Proxmox — processeur, mémoire, disques, ZFS, réseau, invités —,
verdict, réponse à « des disques SSD sont-ils justifiés ? », réglages suggérés, --csv, Ctrl-C. Faux /proc, /sys, /etc/pve, zpool et zfs : aucune mesure réelle."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # program for the Proxmox host: tested everywhere
import importlib.util
import io
import os
import re
import sys
import time
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
        self.assertIn("Mesure pendant 5 s, un échantillon toutes les 1 s (1 disques, 1 invités en marche, pools ZFS : rpool)", out)
        self.assertIn("PERFORMANCES DE ", out)
        self.assertIn("pve-manager/8.2.4", out)
        self.assertIn("PROCESSEUR — AMD Ryzen 7 5700G, 2 cœurs logiques", out)
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

    def hote_plein(self):
        """Host like the real one of 1.10: sync and compression inherited by every dataset, one almost full container disk, backups without retention on the pool."""
        G = 2 ** 30
        lignes = []
        def ds(nom, **props):
            for cle, (valeur, source) in props.items():
                lignes.append(f"{nom}\t{cle}\t{valeur}\t{source}")
        vz = os.path.join(self.d, "vz")
        ds("rpool", compression=("off", "default"), sync=("standard", "default"), used=(3500 * G, "-"), available=(235 * G, "-"), usedbydataset=(0, "-"),
           usedbysnapshots=(0, "-"), usedbychildren=(3500 * G, "-"), refquota=(0, "default"), mountpoint=("/rpool", "default"))
        ds("rpool/data", compression=("off", "inherited from rpool"), sync=("disabled", "local"), used=(3500 * G, "-"), available=(235 * G, "-"),
           usedbydataset=(2900 * G, "-"), usedbysnapshots=(0, "-"), usedbychildren=(400 * G, "-"), refquota=(0, "default"), mountpoint=(vz, "local"))
        for nom, libre, quota in (("subvol-101-disk-0", 20 * G, 50 * G), ("subvol-101-disk-2", 2 * G, 55 * G)):
            ds("rpool/data/" + nom, compression=("off", "inherited from rpool"), sync=("disabled", "inherited from rpool/data"), used=(57 * G, "-"), available=(libre, "-"),
               usedbydataset=(quota - libre, "-"), usedbysnapshots=(4 * G, "-"), usedbychildren=(0, "-"), refquota=(quota, "local"), mountpoint=("/rpool/data/" + nom, "default"))
        self.write("zfs-get.txt", "\n".join(lignes) + "\n")
        self.write("zfs-snap.txt", "rpool/data/subvol-101-disk-2@Debian13\t81920\t1772335260\n")
        self.mock("zfs", f'case "$1" in get) cat {self.d}/zfs-get.txt;; list) cat {self.d}/zfs-snap.txt;; esac')
        self.write("pve/lxc/101.conf", "arch: amd64\nhostname: odoo18\nrootfs: local-zfs:subvol-101-disk-0,size=50G\nmp1: local-zfs:subvol-101-disk-2,mp=/opt/odoo,size=55G\n")
        self.write("pve/qemu-server/120.conf", "name: bbb3\ncipassword: secret123\nscsi0: local-zfs:vm-120-disk-0,size=64G\nscsi1: local-zfs:vm-120-disk-1,size=8G\n")
        self.write("pve/storage.cfg", f"dir: local\n\tpath {vz}\n\tcontent iso,vztmpl,backup\n\nzfspool: local-zfs\n\tpool rpool/data\n\tcontent images,rootdir\n")
        self.write("pve/jobs.cfg", "vzdump: backup-1\n\tschedule 02:30\n\tstorage local\n\tall 1\n\tmode snapshot\n\tcompress zstd\n")
        for jour in range(1, 7):
            self.write(f"vz/dump/latest/vzdump-lxc-101-2026_11_{jour:02d}-02_30_00.tar.zst", "x" * 2048)
            self.write(f"vz/dump/latest/vzdump-lxc-101-2026_11_{jour:02d}-02_30_00.log", "INFO\n")
        os.makedirs(os.path.join(vz, "tmp"), exist_ok=True)
        debut = int(time.time()) - 3600
        self.write("tasks-index", f"UPID:pve1:0000ABCD:00112233:{debut:08X}:vzdump:101:root@pam: {debut + 1500:08X} OK\n")
        self.write("vzdump.conf", "# none\n")
        self.env.update(HOST_PERF_AUDIT_TASKS=os.path.join(self.d, "tasks-index"), HOST_PERF_AUDIT_VZDUMP_CONF=os.path.join(self.d, "vzdump.conf"),
                        HOST_PERF_AUDIT_STATE_DIR=os.path.join(self.d, "etat"))

    def test_valeurs_heritees_espace_et_sauvegardes(self):
        """1.10: an inherited value gives ONE line; the report says where the space goes, which guest disk is almost full and what the backups weigh."""
        self.hote_plein()
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "5", "--interval", "2", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(out.count("sync=disabled"), 1, out)                                          # was one line per dataset
        self.assertIn("dataset rpool/data (and 2 datasets that inherit it): sync=disabled", out)
        self.assertIn("add the SLOG first", out)
        self.assertEqual(out.count("compression off"), 1, out)
        self.assertIn("dataset rpool (and 3 datasets that inherit it): compression off", out)
        self.assertIn("--apply: zfs set compression=lz4 rpool\n", out)
        self.assertIn("space of pool rpool — 235.0 GiB free, 3.4 TiB used · snapshots 8.0 GiB (1 snapshots, the oldest of 2026-0", out)
        self.assertIn("files stored directly in rpool/data (", out)
        self.assertRegex(out, r"outside the guests: dump \d+ MiB")
        self.assertIn("container 101 (odoo18): disk subvol-101-disk-2 mounted on /opt/odoo has only 2.0 GiB free of 55.0 GiB", out)
        self.assertIn("pct resize 101 mp1 +14G", out)
        self.assertNotIn("disk subvol-101-disk-0", out)                                               # 20 of 50 GiB free: not reported
        self.assertIn("BACKUPS (vzdump)", out)
        self.assertRegex(out, r"storage local \(.*/vz/dump\) — 6 backups, 0 MiB — the oldest of 2026-11-01, the newest of 2026-11-06 · retention: none")
        self.assertRegex(out, r"101 odoo18\s+6 backups")
        self.assertIn("job backup-1: schedule 02:30, storage local, guests all of them, mode snapshot, compression zstd, retention none (everything is kept)", out)
        self.assertIn("storage local — 6 backup files (0 MiB) and no retention — they fill pool rpool (used 85 %)", out)
        self.assertIn("the backups are on pool rpool, the disks of the guests", out)
        self.assertRegex(out, r"backups of the last 3 days.*\n.* \(25 min 00 s\) guest 101 — OK")
        self.assertEqual(out.count("without iothread=1"), 1, out)                                     # was one line per disk, the disk not named
        self.assertIn("VM 120 (bbb3): SCSI disk without iothread=1: scsi0, scsi1", out)
        self.assertNotRegex(out, r"above 1\d\d(\.\d)? %")                                             # a hit ratio is never above 100 %

    def test_export_ai(self):
        """1.10 --export-ai: the report and the raw state in a Markdown file, mode 600, passwords hidden."""
        self.hote_plein()
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "5", "--interval", "2", "--lang", "en", "--export-ai"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        m = re.search(r"--export-ai: written to (\S+) \(\d+ lines, mode 600\)", out)
        self.assertIsNotNone(m, out)
        self.assertRegex(os.path.basename(m.group(1)), r"^export-ai-.+-\d{8}-\d{6}\.md$")
        self.assertEqual(os.stat(m.group(1)).st_mode & 0o777, 0o600)
        texte = open(m.group(1), encoding="utf-8").read()
        self.assertIn("# host-perf-audit.py v1.", texte)
        self.assertIn("VERDICT", texte)
        self.assertIn("SUGGESTED SETTINGS", texte)
        self.assertIn("## Guest 101 (lxc, odoo18)", texte)
        self.assertIn("## Proxmox jobs.cfg", texte)
        self.assertIn("vzdump 101: OK", texte)
        self.assertIn("cipassword: ***", texte)
        self.assertNotIn("secret123", texte)
        self.assertNotIn("\x1b[", texte)
        fichier = os.path.join(self.d, "ailleurs.md")
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "5", "--interval", "2", "--lang", "fr", "--export-ai", fichier], timeout=60)
        self.assertIn("conteneur 101 (odoo18) : le disque subvol-101-disk-2 monté sur /opt/odoo", out)        # names of datasets are never translated
        self.assertIn("SAUVEGARDES (vzdump)", out)
        self.assertTrue(os.path.isfile(fichier), out + err)

    def test_compteurs_zfs_par_invite(self):
        """1.11 : les écritures de chaque invité lues dans les compteurs ZFS de ses datasets (le cgroup ne compte rien sur ZFS), les volumes zdN nommés,
        et l'invité qui fait la plupart des écritures désigné."""
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix="test-rlq-hpa-z-")
        self.addCleanup(shutil.rmtree, d)
        faux_proc(d)

        def objset(nom, fichier, lectures, ecritures):
            chemin = os.path.join(d, "proc/spl/kstat/zfs/data", fichier)
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            with open(chemin, "w") as f:
                f.write(f"49 1 0x01 7 2160 1 2\nname type data\ndataset_name 7 {nom}\nwrites 4 {ecritures}\nnwritten 4 {ecritures * 4096}\n"
                        f"reads 4 {lectures}\nnread 4 {lectures * 8192}\nnunlinks 4 0\n")
        objset("data/zd0/vm-433-disk-0", "objset-0x10", 100, 1000)
        objset("data/zd0/vm-433-disk-1", "objset-0x11", 0, 500)
        objset("data/zd0/subvol-105-disk-2", "objset-0x12", 40, 30)
        objset("data/zd0", "objset-0x2", 5, 5)                                    # not a guest
        zv = os.path.join(d, "zvol/data/zd0")
        os.makedirs(zv)
        os.symlink("../../../zd16", os.path.join(zv, "vm-433-disk-0"))
        os.symlink("../../../zd16p1", os.path.join(zv, "vm-433-disk-0-part1"))
        m = charger("hpa_z", "host-perf-audit.py", {"NGINX_TOOLS_PROC_ROOT": d, "HOST_PERF_AUDIT_ZVOL_DIR": os.path.join(d, "zvol"),
                                                    "HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en"})
        self.assertEqual(m.zfs_objset_counters(), {"433": [100, 819200, 1500, 6144000], "105": [40, 327680, 30, 122880]})
        self.assertEqual(m.zvol_names(), {"zd16": "data/zd0/vm-433-disk-0"})
        # two guests: the VM writes 30 times a second, the container 2 — the cgroup of both counts nothing
        g = lambda w, r: {"cpu": 5.0, "mem": 2 ** 30, "mem_max": None, "io_r": 0.0, "io_w": 0.0, "io_some": 0.2, "cpu_some": 0.0, "z_w_ops": w, "z_r_ops": r, "z_w": w * 4096.0, "z_r": r * 8192.0}
        echantillons = [{"guests": {"433": g(30, 1), "105": g(2, 4)}, "psi": {"io": {"some": 6.0}}} for _ in range(3)]
        noms = {"433": ("vm", "bbb3-26", ""), "105": ("lxc", "odoo18", "")}
        out = []
        lignes = m.analyze_guests(echantillons, noms, 8, out)
        texte = "\n".join(out)
        self.assertIn("ZFS counters of its datasets", texte)
        self.assertIn("writes/s", texte)
        self.assertLess(texte.index("bbb3-26"), texte.index("odoo18"))          # sorted by operations
        self.assertRegex(texte, r"433 vm\s+bbb3-26 .* 0\.12\s+30\.0\s+1\.0")
        fd = m.Findings()
        m.guest_writers(lignes, echantillons, {"disks": {"sda": {"kind": "HDD"}}}, noms, fd)
        conseils = [t for _p, t, _a, _l in fd.suggestions]
        self.assertEqual(len(conseils), 1, conseils)
        self.assertIn("guest 433 (bbb3-26) makes 94 % of the writes of the guests (30 per second)", conseils[0])
        self.assertIn("pidstat -d 10 6", conseils[0])
        fd = m.Findings()
        m.guest_writers(lignes, [{"psi": {"io": {"some": 0.5}}}], {"disks": {"sda": {"kind": "HDD"}}}, noms, fd)
        self.assertEqual(fd.suggestions, [])                                        # the disks do not make anyone wait: nothing to say
        fd = m.Findings()
        m.guest_writers(lignes, echantillons, {"disks": {"nvme0n1": {"kind": "NVMe"}}}, noms, fd)
        self.assertEqual(fd.suggestions, [])

    def hote_sante(self, realloues=0, attente=0, cksum=0):
        """Faux hôte pour --health : smartctl, zpool status, journal du noyau, pct et qm (agent absent sur la VM 120)."""
        self.mock("smartctl", f"""cat <<'X'
SMART overall-health self-assessment test result: PASSED
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   0x0033   100   100   005    Pre-fail  Always       -       {realloues}
  9 Power_On_Hours          0x0012   091   091   000    Old_age   Always       -       65402
194 Temperature_Celsius     0x0002   171   171   000    Old_age   Always       -       35
197 Current_Pending_Sector  0x0022   100   100   000    Old_age   Always       -       {attente}
199 UDMA_CRC_Error_Count    0x000a   200   200   000    Old_age   Always       -       0
X""")
        self.mock("zpool", f'''case "$*" in
 "list -H -p -o name,size,alloc,free,frag,cap,health") printf "rpool\\t4000000000000\\t2400000000000\\t1600000000000\\t20\\t60\\tONLINE\\n";;
 "status") printf "  pool: rpool\\n state: ONLINE\\n  scan: scrub repaired 0B in 05:10:11 with 0 errors on $(LC_ALL=C date -d "-3 days" "+%%a %%b %%e %%H:%%M:%%S %%Y")\\nconfig:\\n\\n\\tNAME        STATE     READ WRITE CKSUM\\n\\trpool       ONLINE       0     0     0\\n\\t  mirror-0  ONLINE       0     0     0\\n\\t    sda2    ONLINE       0     0     {cksum}\\n\\nerrors: No known data errors\\n";;
 "get -H -p -o name,value ashift") printf "rpool\\t12\\n";;
esac'''.replace("%%", "%"))
        self.write("pve/lxc/101.conf", "arch: amd64\nhostname: odoo18\nmemory: 4096\nonboot: 1\nunprivileged: 1\ncores: 4\n")
        self.write("pve/qemu-server/120.conf", "name: bbb3\nonboot: 1\nmemory: 8192\nscsi0: local-zfs:vm-120-disk-0,discard=on,iothread=1,size=64G\n")
        self.write("pve/jobs.cfg", "vzdump: backup-1\n\tschedule 02:30\n\tstorage local\n\tall 1\n")
        recent = int(time.time()) - 7200
        self.write("taches-sante", f"UPID:pve1:0000ABCD:00112233:{recent:08X}:vzdump:101:root@pam: {recent + 600:08X} OK\n")
        self.mock("zfs", "exit 0")
        self.mock("journalctl", "exit 0")
        self.mock("systemctl", "echo active")
        dedans = ("@@io1\\n100 1000 ntopng\\n200 5000 postgres\\n@@docker\\ngrafana|Up 2 weeks\\nprometheus|Restarting (1) 22 seconds ago\\n@@failed\\n"
                  "@@journal\\n   3492 dockerd\\n     40 systemd\\n@@jsize\\nArchived and active journals take up 4.0G in the file system.\\n"
                  "@@df\\n/dev/sda1 100000 96000 4000 96%% /var\\n/dev/sda2 100000 10000 90000 10%% /\\n@@io2\\n100 901000 ntopng\\n200 6000 postgres\\n")
        self.dedans = dedans
        self.mock("pct", f'printf "{dedans}"')
        self.mock("qm", "echo ne-doit-pas-etre-appele; exit 1")
        os.makedirs(os.path.join(self.racine, "sys/fs/cgroup/qemu.slice/120.scope"), exist_ok=True)
        self.env.update(HOST_PERF_AUDIT_STATE_DIR=os.path.join(self.d, "etat"), HOST_PERF_AUDIT_MAIL_FILE=os.path.join(self.d, "courriel.txt"),
                        HOST_PERF_AUDIT_TASKS=os.path.join(self.d, "taches-sante"), HOST_PERF_AUDIT_SYSTEMD_DIR=os.path.join(self.d, "systemd"))

    def test_health_disque_qui_faiblit(self):
        """1.12 --health : un disque sain donne 0 ; un compteur SMART qui monte ou un secteur en attente donne 2, avec les commandes à lancer."""
        self.hote_sante()
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("HEALTH OF", out)
        self.assertIn("sda: SMART passed, no reallocated, pending or uncorrectable sector · 65402 h (7.5 years) — past 5 years", out)
        self.assertIn("pool rpool: ONLINE, no error, used 60 %", out)
        self.assertIn("Verdict: nothing to report", out)
        self.assertIn("[OK] container 101 (odoo18): starts with the host · in a backup job · disks in the backups: rootfs · unprivileged", out)   # 1.14: said when all is well
        self.assertNotIn("smartctl -a /dev/sda", out)                                     # a healthy disk asks for nothing
        self.hote_sante(realloues=8, attente=2, cksum=14)
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 2, out + err)
        self.assertIn("sda: signs of failure — reallocated sectors: 8 (was 0); sectors pending reallocation: 2 (was 0) — plan its replacement", out)
        self.assertIn("pool rpool: errors on sda2 (read 0, write 0, checksum 14)", out)
        self.assertIn("Verdict: 2 problems, 0 to watch", out)
        self.assertIn("COMMANDS — [read]: run by the program, output below · [change]: run only after your confirmation", out)
        self.assertIn("  [read]   smartctl -a /dev/sda\n", out)
        self.assertIn("  [change] smartctl -t long /dev/sda", out)
        self.assertIn("  [read]   zpool status -v rpool\n", out)
        self.hote_sante(realloues=8)                                              # stable since the last run, nothing pending: to watch only
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 1, out + err)
        self.assertIn("reallocated sectors: 8 — to watch", out)

    def test_health_interieur_des_invites_et_alerte(self):
        """1.12 --inside --notify : conteneur qui redémarre en boucle, journal qui déborde, disque plein vus DANS l'invité ; VM sans agent : la marche à
        suivre ; une alerte par courriel, pas répétée tant que rien ne change, puis le retour à la normale."""
        self.hote_sante()
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--inside", "--notify", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 2, out + err)
        self.assertIn("guest 101 (odoo18): container prometheus restarts in a loop (Restarting (1) 22 seconds ago)", out)
        self.assertIn("guest 101 (odoo18): dockerd wrote 3492 lines to the journal in 10 minutes (5.8 per second)", out)
        self.assertIn("guest 101 (odoo18): the journal takes 4.0 GiB", out)
        self.assertIn("guest 101 (odoo18): /var is 96% full (3 MiB free)", out)
        self.assertIn("guest 101 (odoo18): processes that write the most: ntopng 88 kB/s", out)
        self.assertNotIn("grafana", out.split("COMMANDS —")[0])
        self.assertIn("guest 120 (bbb3): the QEMU guest agent is not enabled", out)
        self.assertIn("  [change] qm set 120 --agent enabled=1", out)
        self.assertIn("  [read]   pct exec 101 -- docker logs --tail 30 prometheus\n", out)
        self.assertNotIn("ne-doit-pas-etre-appele", out + err)                    # no agent: qm guest exec is not tried
        self.assertIn("Alert: written to", out)
        self.assertIn("COLLECTED — output of the [read] commands (send it with this report)", out)      # 1.15: run by the program
        self.assertIn("  $ pct exec 101 -- docker logs --tail 30 prometheus\n", out)
        self.assertIn("CHANGES — ", out)
        self.assertIn("commands not run: no terminal to confirm them", out)
        courriel = open(os.path.join(self.d, "courriel.txt"), encoding="utf-8").read()
        self.assertIn("Subject: [host-perf-audit] ", courriel)
        self.assertIn(": 1 problems, 3 to watch", courriel)
        self.assertIn("[FAIL] guest 101 (odoo18): container prometheus restarts in a loop", courriel)
        self.assertIn("pct exec 101 -- docker logs --tail 30 prometheus", courriel)
        self.assertIn("COLLECTED — output of the [read] commands", courriel)                            # the outputs go with the alert
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--inside", "--notify", "--lang", "en"], timeout=60)
        self.assertIn("Alert: not sent (nothing new since the last one", out)
        self.assertEqual(open(os.path.join(self.d, "courriel.txt"), encoding="utf-8").read().count("Subject:"), 1)
        self.mock("pct", 'printf "@@io1\\n@@docker\\ngrafana|Up 2 weeks\\n@@failed\\n@@journal\\n@@jsize\\n@@df\\n@@io2\\n"')
        self.mock("pct", f'printf "{self.dedans}"')
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--inside", "--no-collect", "--lang", "fr"], timeout=60)
        self.assertIn("[lecture] pct exec 101 -- docker logs --tail 30 prometheus", out)                 # 1.15, in French
        self.assertIn("[modif.]  qm set 120 --agent enabled=1", out)
        self.assertNotIn("COLLECTÉ", out)                                                                # --no-collect
        self.mock("pct", 'printf "@@io1\\n@@docker\\ngrafana|Up 2 weeks\\n@@failed\\n@@journal\\n@@jsize\\n@@df\\n@@io2\\n"')
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--inside", "--notify", "--lang", "fr"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(open(os.path.join(self.d, "courriel.txt"), encoding="utf-8").read().count("Subject:"), 2)   # back to normal, once
        self.assertNotIn("Traceback", err)

    def test_minuteur_de_sante(self):
        """1.12 --install-timer / --uninstall-timer : unités systemd qui lancent --health --inside --notify chaque heure."""
        self.hote_sante()
        rc, out, err = self.run_cmd(["python3", self.prog, "--install-timer", "--lang", "en"], timeout=30)
        self.assertEqual(rc, 0, out + err)
        service = open(os.path.join(self.d, "systemd", "host-perf-audit-health.service"), encoding="utf-8").read()
        self.assertRegex(service, r"ExecStart=\S+ \S+host-perf-audit\.py --health --inside --notify\n")
        self.assertIn("OnCalendar=*-*-* *:17:00", open(os.path.join(self.d, "systemd", "host-perf-audit-health.timer"), encoding="utf-8").read())
        rc, out, err = self.run_cmd(["python3", self.prog, "--uninstall-timer"], timeout=30)
        self.assertEqual(os.listdir(os.path.join(self.d, "systemd")), [])

    def test_configuration_des_invites(self):
        """1.13 : les configurations des conteneurs et des VM sont vérifiées et annoncées au démarrage ; les enjeux majeurs d'abord, avec la commande."""
        m = charger("hpa_c", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en", "HOST_PERF_AUDIT_PVE_DIR": os.path.join(self.d, "pve"),
                                                    "NGINX_TOOLS_PROC_ROOT": self.racine})
        self.write("pve/jobs.cfg", "vzdump: backup-1\n\tschedule 02:30\n\tstorage local\n\tvmid 105,433\n")
        noms = {
            "105": ("lxc", "odoo18", "hostname: odoo18\nmemory: 16384\nonboot: 1\nunprivileged: 1\ncores: 6\nrootfs: local-zfs:subvol-105-disk-0,size=10G\n"
                                     "mp0: local-zfs:subvol-105-disk-1,mp=/var/log,size=32G,backup=1\nmp1: local-zfs:subvol-105-disk-2,mp=/opt/odoo,size=55G\nmp2: /srv/partage,mp=/mnt/partage\n"),
            "433": ("vm", "bbb3-26", "name: bbb3-26\nmemory: 8192\nonboot: 1\nagent: 1\nscsi0: local-zfs:vm-433-disk-0,discard=on,size=50G\n"
                                     "scsi1: local-zfs:vm-433-disk-1,cache=unsafe,size=200G\nnet0: e1000=AA:BB:CC:DD:EE:FF,bridge=vmbr0\nide2: none,media=cdrom\n"),
            "430": ("vm", "bbb30.dev", "name: bbb30.dev\nmemory: 16384\nscsi0: local-zfs:vm-430-disk-0,size=60G\nunused0: local-zfs:vm-430-disk-9\n"),
            "900": ("vm", "modele", "name: modele\ntemplate: 1\nmemory: 2048\n"),
        }
        en_marche = {"105": ("lxc", ""), "433": ("vm", ""), "430": ("vm", "")}
        trouve = m.guest_config_check(noms, en_marche, {"pools": {}})
        par_niveau = lambda n: [t for l, _v, t, _c in trouve if l == n]
        majeurs = "\n".join(par_niveau("major"))
        self.assertIn("container 105 (odoo18): mount point mp1 (/opt/odoo) is NOT in the backups (backup=1 missing)", majeurs)
        self.assertNotIn("mp0", majeurs)                                                    # backup=1 is there
        self.assertIn("VM 433 (bbb3-26): disk scsi1 with cache=unsafe", majeurs)
        self.assertIn("VM 430 (bbb30.dev): runs now but does not start with the host (onboot missing)", majeurs)
        self.assertIn("VM 430 (bbb30.dev): in no scheduled backup job", majeurs)
        self.assertEqual(len(par_niveau("major")), 5, majeurs)                                   # the four above and the memory promised twice
        commandes = [c for _l, _v, _t, cs in trouve for c in cs]
        self.assertIn("pct set 105 --mp1 local-zfs:subvol-105-disk-2,mp=/opt/odoo,size=55G,backup=1", commandes)
        self.assertIn("qm set 433 --scsi1 local-zfs:vm-433-disk-1,size=200G", commandes)
        self.assertIn("qm set 430 --onboot 1", commandes)
        ameliorer = "\n".join(par_niveau("improve"))
        self.assertIn("VM 430 (bbb30.dev): QEMU guest agent not enabled", ameliorer)
        self.assertIn("VM 430 (bbb30.dev): disk scsi0 without discard=on", ameliorer)
        self.assertIn("VM 433 (bbb3-26): network card net0 emulated (e1000)", ameliorer)
        self.assertNotIn("433 (bbb3-26): QEMU guest agent", ameliorer)
        notes = "\n".join(par_niveau("note"))
        self.assertIn("container 105 (odoo18): mp2 (/mnt/partage) is a folder of the host (/srv/partage)", notes)
        self.assertIn("VM 430 (bbb30.dev): 1 unused disks kept", notes)
        self.assertNotIn("modele", majeurs + ameliorer + notes)                               # a template is not a guest
        # memory promised: 40 GiB for the 31 GiB of the fake host
        self.assertIn("host: the running guests are promised 40 GiB of memory for 31 GiB in the machine (128 %)", "\n".join(par_niveau("major") + par_niveau("improve")))

    def test_configuration_annoncee_au_demarrage(self):
        self.write("pve/lxc/101.conf", "hostname: odoo18\nmemory: 4096\nunprivileged: 1\ncores: 2\nonboot: 1\nrootfs: rpool/data:subvol-101-disk-0,size=8G\n"
                                       "mp1: rpool/data:subvol-101-disk-2,mp=/opt/odoo,size=55G\n")
        self.write("pve/jobs.cfg", "vzdump: backup-1\n\tschedule 02:30\n\tstorage local\n\tall 1\n")
        rc, out, err = self.run_cmd(["python3", self.prog, "--duration", "5", "--interval", "2", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertLess(out.index("GUEST CONFIGURATIONS — 2 containers and VMs checked: 1 major issues"), out.index("Measuring for"))     # said at the start
        self.assertIn("[FAIL] container 101 (odoo18): mount point mp1 (/opt/odoo) is NOT in the backups", out.split("Measuring for")[0])
        self.assertIn("To correct quickly: the commands are in the block", out.split("Measuring for")[0])
        fin = out.split("SUGGESTED SETTINGS")[1]
        self.assertIn("GUEST CONFIGURATIONS — 2 containers and VMs checked", fin)                   # in full at the end
        self.assertIn("QEMU guest agent not enabled", fin)
        self.assertIn("  [change] pct set 101 --mp1 rpool/data:subvol-101-disk-2,mp=/opt/odoo,size=55G,backup=1\n", fin)
        rc, out, err = self.run_cmd(["python3", self.prog, "--health", "--lang", "fr"], timeout=60)
        self.assertEqual(rc, 1, out + err)                                                          # a major configuration issue: to watch
        self.assertIn("n'est PAS dans les sauvegardes", out)
        self.assertNotIn("Traceback", err)

    def test_vieux_instantanes_et_tout_est_correct(self):
        """1.14 : les instantanés de plus de 60 jours sont nommés avec la place que leur suppression rend (zfs destroy -n, rien n'est détruit) ;
        un invité sans rien à corriger a sa ligne [OK] avec ce qui a été vérifié."""
        vieux, recent = int(time.time()) - 250 * 86400, int(time.time()) - 5 * 86400
        self.write("zfs-destroy.log", "")
        self.mock("zfs", f'''case "$1" in
 destroy) echo "$*" >> {self.d}/zfs-destroy.log; case "$*" in *-n*) printf "destroy\\tx\\nreclaim\\t4294967296\\n";; *) echo INTERDIT >> {self.d}/zfs-destroy.log;; esac;;
esac''')
        m = charger("hpa_s", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en", "HOST_PERF_AUDIT_PVE_DIR": os.path.join(self.d, "pve"),
                                                    "NGINX_TOOLS_PROC_ROOT": self.racine, "PATH": self.env["PATH"]})
        self.write("pve/jobs.cfg", "vzdump: backup-1\n\tschedule 02:30\n\tstorage local\n\tall 1\n")
        G = 2 ** 30
        zfs = {"pools": {"data": {"free": 235 * G}}, "datasets": {"data": {"available": str(235 * G)}, "data/zd0/vm-430-state-Avant": {"used": str(1 * G)}},
               "snapshots": [("data/zd0/subvol-105-disk-0@Debian13", 300 * 2 ** 20, vieux), ("data/zd0/subvol-105-disk-2@Debian13", 80000, vieux),
                             ("data/zd0/subvol-105-disk-2@Hier", 5 * G, recent), ("data/zd0/vm-430-disk-0@Avant", 3 * G, vieux),
                             ("data/zd0/subvol-105-disk-0@__replicate_1", G, vieux), ("data/autre@vieux", G, vieux)]}
        noms = {"105": ("lxc", "odoo18", "hostname: odoo18\nmemory: 2048\nonboot: 1\nunprivileged: 1\ncores: 4\nrootfs: data:subvol-105-disk-0,size=10G\n"
                                         "mp1: data:subvol-105-disk-2,mp=/opt/odoo,size=55G,backup=1\n"),
                "430": ("vm", "bbb30.dev", "name: bbb30.dev\nmemory: 2048\nonboot: 1\nagent: 1\nscsi0: data:vm-430-disk-0,discard=on,size=60G\n"),
                "101": ("lxc", "ancien", "hostname: ancien\nmemory: 1024\nonboot: 1\nunprivileged: 1\ncores: 1\nrootfs: data:subvol-101-disk-0,size=8G\n")}
        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self.env["PATH"]
        try:
            trouve = m.guest_config_check(noms, {"105": ("lxc", ""), "430": ("vm", ""), "101": ("lxc", "")}, zfs)
        finally:
            os.environ["PATH"] = ancien_path
        textes = {(l, v): t for l, v, t, _c in trouve}
        t105 = textes[("improve", "105")]
        self.assertRegex(t105, r"container 105 \(odoo18\): 1 snapshots older than 60 days: Debian13 \(\d{4}-\d\d-\d\d\) — deleting them frees 8\.0 GiB in pool data")
        self.assertNotIn("Hier", t105)                                              # 5 days old: kept
        self.assertNotIn("__replicate", t105)                                       # replication snapshots are not the administrator's
        self.assertIn("deleting them frees 5.0 GiB", textes[("improve", "430")])     # 4 GiB of the disk + 1 GiB of the saved memory image
        commandes = [c for _l, v, _t, cs in trouve for c in cs]
        self.assertIn("pct delsnapshot 105 Debian13", commandes)
        self.assertIn("qm delsnapshot 430 Avant", commandes)
        self.assertTrue(any(c.startswith("zpool list -o name,alloc,free,cap data   # after: compare with 235.0 GiB free before") for c in commandes), commandes)
        self.assertIn("old snapshots: 2 in all, 13.0 GiB to free by deleting them", textes[("note", "")])
        self.assertEqual(textes[("ok", "101")], "container 101 (ancien): starts with the host · in a backup job · disks in the backups: rootfs · unprivileged · no old snapshot")
        self.assertIn("disks in the backups: rootfs, mp1", textes[("ok", "105")])
        journal = open(os.path.join(self.d, "zfs-destroy.log"), encoding="utf-8").read()
        self.assertIn("destroy -nvp data/zd0/subvol-105-disk-0@Debian13", journal)
        self.assertNotIn("INTERDIT", journal)                                       # every destroy was a dry run

    def test_commandes_de_lecture_et_de_changement(self):
        """1.15 : seules les commandes en lecture seule sont lancées par le programme ; toute autre est un changement, jamais lancé sans confirmation."""
        m = charger("hpa_r", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en"})
        lecture = ["smartctl -a /dev/sda", "zpool status -v data", "zfs list -o space -r data", "zfs list -t snapshot -o name,used,creation -s used -r data | tail -15",
                   "pct exec 105 -- systemctl status logrotate.service --no-pager -n 15", "qm guest exec 430 --timeout 50 -- docker logs --tail 30 keycloak",
                   "qm guest exec 430 -- docker inspect keycloak --format '{{.RestartCount}} restarts, {{.State.Error}}'",
                   "pct exec 105 -- sh -c 'du -xh --max-depth=2 /opt 2>/dev/null | sort -h | tail -15'", "pct exec 105 -- journalctl --since -2min -t odoo --no-pager -o cat | tail -15",
                   "xargs -d '\\n' -a /var/lib/host-perf-audit/backups-to-delete-local.txt du -ch | tail -1", "zpool list -o name,alloc,free,cap data   # after: compare"]
        changement = ["pct resize 105 mp1 +14G", "qm set 430 --onboot 1", "pct delsnapshot 105 Debian13", "smartctl -t long /dev/sda   # long self-test",
                      "qm guest exec 430 -- journalctl --vacuum-size=500M", "qm guest exec 430 -- fstrim -av", "pct exec 105 -- systemctl disable --now chrony.service",
                      "xargs -d '\\n' -a /var/lib/host-perf-audit/backups-to-delete-local.txt rm -v --", "zpool scrub data", "zfs set compression=lz4 data",
                      "ls /tmp > /tmp/liste", "cat $(rm -rf /x)", "pct exec 105 -- sh -c 'df -h; rm -f /tmp/x'", "apt install -y qemu-guest-agent",
                      "find / -name x -delete", "sed -i s/a/b/ /etc/x", "qm shutdown 430 && qm start 430", "systemctl enable --now smartmontools"]
        for c in lecture:
            self.assertTrue(m.is_read_only(c), c)
        for c in changement:
            self.assertFalse(m.is_read_only(c), c)
        self.assertEqual(m.unique_commands([("a", ["x", "y"]), ("b", ["y   # pourquoi", "z"])]), [("a", ["x", "y"]), ("b", ["z"])])

    def test_verrou_d_une_sauvegarde_en_cours(self):
        """1.16 : un invité « locked (backup) » pendant que sa sauvegarde tourne n'est pas une sauvegarde interrompue : jamais « pct unlock » ;
        ses instantanés attendent la fin ; la sortie de l'agent invité QEMU est remise en UTF-8."""
        actives = self.write("taches-actives", "UPID:pve1:0000ABCD:00112233:6915F4A0:vzdump:105:root@pam:\n"
                                               "UPID:pve1:0000ABCE:00112234:6915F4A0:vzdump:104:root@pam: 6915F8A0 OK\n")
        m = charger("hpa_v", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en", "HOST_PERF_AUDIT_PVE_DIR": os.path.join(self.d, "pve"),
                                                    "HOST_PERF_AUDIT_TASKS_ACTIVE": actives})
        self.assertEqual(m.running_tasks(), {"105": ["vzdump"]})                     # 104 has ended
        try:
            noms = {"105": ("lxc", "odoo18", "hostname: odoo18\nonboot: 1\nunprivileged: 1\ncores: 2\nmemory: 1024\nlock: backup\n"),
                    "104": ("lxc", "odoo-dev", "hostname: odoo-dev\nonboot: 1\nunprivileged: 1\ncores: 2\nmemory: 1024\nlock: backup\n")}
            trouve = m.guest_config_check(noms, {"105": ("lxc", ""), "104": ("lxc", "")}, {})
        finally:
            pass
        textes = {(l, v): (t, c) for l, v, t, c in trouve}
        self.assertIn("container 105 (odoo18): locked (backup) by a task running now (vzdump) — normal", textes[("note", "105")][0])
        self.assertNotIn(("improve", "105"), textes)
        self.assertIn("and no task of it is running", textes[("improve", "104")][0])
        self.assertIn("pct unlock 104", textes[("improve", "104")][1][0])
        self.assertTrue(m.is_read_only("crontab -l 2>/dev/null | grep -v '^#'"))
        self.assertFalse(m.is_read_only("crontab -r"))
        self.mock("qm", "printf '%s' '{\"exitcode\":3,\"out-data\":\"\\u00e2\\u0097\\u008f logrotate.service\"}'")
        ancien = os.environ.get("PATH", "")
        os.environ["PATH"] = self.env["PATH"]
        try:
            code, sortie = m.run_collected("qm guest exec 433 -- systemctl status logrotate.service", 20)
        finally:
            os.environ["PATH"] = ancien
        self.assertEqual((code, sortie), (3, "● logrotate.service"))

    def test_commande_dans_les_invites(self):
        """1.17 --guest-run : nginx-hardening.sh --update lancé dans les invités choisis, après avoir vérifié qu'il existe dans chacun ; refusé sans
        terminal ni --yes ; chaque sortie gardée, avec un report.md à envoyer."""
        self.hote_sante()
        self.write("pve/lxc/104.conf", "hostname: odoo-dev\nonboot: 1\nunprivileged: 1\ncores: 2\nmemory: 1024\n")
        self.write("pve/qemu-server/433.conf", "name: bbb3-26\nonboot: 1\nagent: 1\nmemory: 8192\n")
        for vmid, d in (("104", "lxc/104"), ("433", "qemu.slice/433.scope")):
            os.makedirs(os.path.join(self.racine, "sys/fs/cgroup", d), exist_ok=True)
        trace = os.path.join(self.d, "lance.txt")
        self.mock("pct", f'''id="$2"; shift 3; script="$*"
case "$script" in
  *"if [ -x"*) [ "$id" = 104 ] && echo MISSING || printf "FOUND\\nnginx-hardening.sh version 2.106.20261115.074443\\n";;
  *--update*) echo "$id" >> {trace}; printf "\\033[32m[OK]\\033[0m   étape 1\\n  [FAIL] fail2ban absent\\n  [ATTN] HSTS absent\\nRÉSUMÉ : 40 OK, 1 avertissements, 1 échecs.\\n"; exit 1;;
esac''')
        self.mock("qm", f'''id="$3"; case "$*" in
  *"if [ -x"*) printf \'{{"exitcode":0,"exited":1,"out-data":"FOUND\\\\nnginx-hardening.sh version 2.106\\\\n"}}\';;
  *--update*) echo "$id" >> {trace}; case "$*" in *'HOME="${{HOME:-/root}}"'*) echo "$id" >> {trace}.home;; esac; printf \'{{"exitcode":0,"exited":1,"out-data":"[OK] tout\\\\nR\\\\u00c3\\\\u0089SUM\\\\u00c3\\\\u0089 : tout est en ordre (40 v\\\\u00c3\\\\u00a9rifications).\\\\n"}}\';;
esac''')
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-run", "--guests", "101,104,433,999,120", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 2, out + err)                                                # no terminal, no --yes: nothing run
        self.assertIn("COMMAND IN THE GUESTS — /opt/rlq-admin-tools/nginx-hardening.sh --update", out)
        self.assertIn("[OK] 101 (odoo18): /opt/rlq-admin-tools/nginx-hardening.sh found · nginx-hardening.sh version 2.106.20261115.074443", out)
        self.assertIn("[FAIL] 104 (odoo-dev): /opt/rlq-admin-tools/nginx-hardening.sh is not there", out)
        self.assertIn("999 (?): left out — no such container or VM", out)
        self.assertIn("120 (bbb3): left out — QEMU guest agent not enabled", out)
        self.assertIn("Not run: this command changes the guests and there is no terminal to confirm it", out)
        self.assertIn("1 guests without the suite (104): --guest-sync copies it there first (host-perf-audit.py --guest-sync --guest-run --guests 104)", out)   # 1.19
        self.assertFalse(os.path.exists(trace))
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-run", "--guests", "101,104,433", "--yes", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 1, out + err)                                                # a failure in the output of 101
        self.assertEqual(open(trace).read(), "101\n433\n")                               # 104 has no program: not run
        self.assertEqual(open(trace + ".home").read(), "433\n")                          # 1.21: HOME given to the VM (qm guest exec has none)
        self.assertIn("[FAIL] 101 (odoo18): exit code 1", out)
        self.assertIn("1 failures, 1 warnings · RÉSUMÉ : 40 OK, 1 avertissements, 1 échecs.", out)
        self.assertIn("      [FAIL] fail2ban absent", out)
        self.assertIn("[OK] 433 (bbb3-26): exit code 0", out)
        self.assertIn("RÉSUMÉ : tout est en ordre (40 vérifications).", out)          # UTF-8 of the agent decoded
        m = re.search(r"to send for analysis: (\S+report-\S+\.md)", out)
        self.assertIsNotNone(m, out)
        rapport = open(m.group(1), encoding="utf-8").read()
        self.assertEqual(os.stat(m.group(1)).st_mode & 0o777, 0o600)
        self.assertIn("| 101 odoo18 | nginx-hardening.sh version 2.106.20261115.074443 | 1 |", rapport)
        self.assertIn("## 433 (bbb3-26)", rapport)
        self.assertIn("[FAIL] fail2ban absent", rapport)
        self.assertNotIn("\x1b[", rapport)                                                # colours removed
        journaux = sorted(f for f in os.listdir(os.path.dirname(m.group(1))) if f.endswith(".log"))
        self.assertEqual(journaux, ["101-odoo18.log", "433-bbb3-26.log"])
        os.makedirs(self.env["NGINX_TOOLS_ETC_DEFAULT"], exist_ok=True)
        with open(os.path.join(self.env["NGINX_TOOLS_ETC_DEFAULT"], "host-perf-audit.conf"), "w") as f:     # the guests from the configuration
            f.write("GUESTS=433\n")
        os.remove(trace)
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-run", "--yes", "--lang", "en"], timeout=60)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(open(trace).read(), "433\n")
        self.assertNotIn("Traceback", err)

    def test_copie_de_la_suite_dans_les_invites(self):
        """1.18 --guest-sync : le dossier de la suite copié dans /opt/rlq-admin-tools de chaque invité (conteneur : pct exec avec l'archive en entrée ;
        VM : morceaux de moins de 1 Mio par l'agent invité, empreinte vérifiée) ; l'ancienne copie gardée ; l'invité qui porte la source laissé tel quel ;
        puis --guest-run, et le nom du serveur dans le nom du rapport."""
        self.hote_sante()
        self.write("pve/qemu-server/433.conf", "name: bbb3-26\nonboot: 1\nagent: 1\nmemory: 8192\n")
        self.write("pve/lxc/104.conf", "hostname: odoo-dev\nonboot: 1\nunprivileged: 1\ncores: 2\nmemory: 1024\n")
        for d in ("lxc/104", "qemu.slice/433.scope"):
            os.makedirs(os.path.join(self.racine, "sys/fs/cgroup", d), exist_ok=True)
        source = os.path.join(self.d, "source")
        self.write("source/nginx-hardening.sh", "#!/bin/sh\necho 'nginx-hardening.sh v2.106.20261115.074443'\n")
        os.chmod(os.path.join(source, "nginx-hardening.sh"), 0o755)
        self.write("source/apps/x.py", "print(1)\n")
        self.write("source/apps/__pycache__/x.cpython-311.pyc", "binaire")
        self.write("source/gros.bin", "z" * (1500 * 1024))                          # several chunks for the VM
        self.write("source/.git/HEAD", "ref: refs/heads/main\n")
        invites = os.path.join(self.d, "invites")
        for vmid in ("101", "104", "433"):
            os.makedirs(os.path.join(invites, vmid), exist_ok=True)
        self.write("invites/101/rlq-admin-tools/nginx-hardening.sh", "#!/bin/sh\necho 'nginx-hardening.sh v2.104.20261113.102013'\n")
        os.chmod(os.path.join(invites, "101/rlq-admin-tools/nginx-hardening.sh"), 0o755)
        dest = "/opt/rlq-admin-tools"
        # the guest « file systems »: the destination of each guest is a folder of the test (105: the source itself)
        carte = f'case "$id" in 105) d="{source}";; *) d="{invites}/$id/rlq-admin-tools";; esac'
        self.mock("pct", f'''id="$2"; shift 3; {carte}
script=$(printf "%s" "$3" | sed "s#{dest}#$d#g"); exec sh -c "$script"''')
        aide = self.write("qm-aide.py", f'''import json, subprocess, sys
a = sys.argv[1:]
vm = a[2]
script = a[a.index("--") + 3]
d = "{invites}/" + vm + "/rlq-admin-tools"
script = script.replace("{dest}", d)
data = sys.stdin.buffer.read() if "--pass-stdin" in a else b""
p = subprocess.run(["sh", "-c", script], input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
print(json.dumps({{"exitcode": p.returncode, "exited": 1, "out-data": p.stdout.decode()}}))
''')
        self.mock("qm", f'case "$*" in *"guest exec"*) exec python3 {aide} "$@";; esac')
        self.env["HOST_PERF_AUDIT_SYNC_DEST"] = dest
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-sync", "--guests", "101,104,105,433", "--sync-source", source, "--lang", "en"], timeout=90)
        self.assertEqual(rc, 2, out + err)                                                # no terminal, no --yes
        self.assertIn("Not done: no terminal to confirm it (add --yes).", out)
        self.assertFalse(os.path.exists(os.path.join(invites, "104/rlq-admin-tools")))
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-sync", "--guests", "101,104,105,433", "--sync-source", source, "--yes", "--lang", "en"], timeout=90)
        self.assertEqual(rc, 0, out + err)
        self.assertIn(f"COPY OF THE SUITE TO THE GUESTS — {source} (nginx-hardening.sh v2.106.20261115.074443) -> {dest}", out)
        self.assertIn("[OK] 101 (odoo18): updated, nginx-hardening.sh v2.104.20261113.102013 -> nginx-hardening.sh v2.106.20261115.074443", out)
        self.assertIn("[OK] 104 (odoo-dev): updated, none -> nginx-hardening.sh v2.106.20261115.074443", out)
        self.assertIn("[OK] 433 (bbb3-26): updated, none -> nginx-hardening.sh v2.106.20261115.074443", out)
        for vmid in ("101", "104", "433"):
            copie = os.path.join(invites, vmid, "rlq-admin-tools")
            self.assertEqual(open(os.path.join(copie, "gros.bin")).read(), "z" * (1500 * 1024), vmid)      # the chunks put back together
            self.assertFalse(os.path.exists(os.path.join(copie, "apps/__pycache__")), vmid)
            self.assertFalse([f for f in os.listdir(copie) if f.startswith(".sync-token")], vmid)
        self.assertTrue(os.path.isfile(os.path.join(invites, "101/rlq-admin-tools.previous/nginx-hardening.sh")))   # the old copy kept
        # 1.20: by default .git goes to the containers, not to the VMs (slow chunks through the agent); progress of the copy to the VM
        self.assertTrue(os.path.isfile(os.path.join(invites, "101/rlq-admin-tools/.git/HEAD")))
        self.assertFalse(os.path.exists(os.path.join(invites, "433/rlq-admin-tools/.git")))
        self.assertRegex(out, r"archive: [0-9.]+ MiB with \.git \(101, 104\) · [0-9.]+ MiB without \.git \(433\) — --sync-git containers")
        self.assertIn("… 433 (bbb3-26): 100 %", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-sync", "--guests", "433", "--sync-source", source, "--sync-git", "all", "--yes", "--lang", "en"], timeout=90)
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(os.path.isfile(os.path.join(invites, "433/rlq-admin-tools/.git/HEAD")))
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-sync", "--guests", "101", "--sync-source", source, "--sync-git", "none", "--yes", "--lang", "en"], timeout=90)
        self.assertFalse(os.path.exists(os.path.join(invites, "101/rlq-admin-tools/.git")))
        self.assertIn("is no longer a git clone", out)
        self.assertFalse([f for f in os.listdir(source) if f.startswith(".sync-token")])
        self.write("pve/lxc/105.conf", "hostname: odoo18b\nonboot: 1\nunprivileged: 1\ncores: 2\nmemory: 1024\n")
        os.makedirs(os.path.join(self.racine, "sys/fs/cgroup/lxc/105"), exist_ok=True)
        rc, out, err = self.run_cmd(["python3", self.prog, "--guest-sync", "--guest-run", "--guests", "105,104", "--sync-source", source, "--yes", "--lang", "en"], timeout=90)
        self.assertIn("105 (odoo18b): this guest holds the source folder itself", out)
        self.assertTrue(os.path.isfile(os.path.join(source, "nginx-hardening.sh")))    # the source was not touched
        self.assertFalse(os.path.exists(source + ".previous"))
        self.assertTrue(os.path.isfile(os.path.join(source, "gros.bin")))
        m = re.search(r"to send for analysis: (\S+)", out)
        self.assertIsNotNone(m, out)
        self.assertRegex(os.path.basename(m.group(1)), r"^report-[^-].*-\d{8}-\d{6}\.md$")
        self.assertIn(os.uname().nodename, os.path.basename(m.group(1)))
        self.assertNotIn("Traceback", err)

    def test_changements_confirmes_un_par_un(self):
        """1.15 : chaque changement est demandé ; seul celui qui reçoit « y » est lancé."""
        import builtins
        import io
        m = charger("hpa_k", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en"})
        trace = os.path.join(self.d, "trace")
        commandes = [("disque", [f"echo un >> {trace}", f"touch {trace}.deux"]), ("lecture", ["true"])]
        reponses = iter(["n", "y"])
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        anciens = (sys.stdin, sys.stdout, builtins.input, os.geteuid)
        sortie = Terminal()
        sys.stdin, sys.stdout, builtins.input, os.geteuid = Terminal(), sortie, lambda _q="": next(reponses), lambda: 0
        m.input = builtins.input                                                    # the module may hold its own (translated) input
        try:
            m.confirm_changes(commandes)
        finally:
            sys.stdin, sys.stdout, builtins.input, os.geteuid = anciens
        self.assertFalse(os.path.exists(trace))                                     # answered « n »
        self.assertTrue(os.path.exists(trace + ".deux"))                            # answered « y »
        self.assertIn("CHANGES — 2 commands that modify something", sortie.getvalue())
        self.assertIn("not run", sortie.getvalue())

    def test_suppression_irreversible_exige_delete(self):
        """1.22 : une commande qui supprime des données (rm, delsnapshot, zfs destroy) n'accepte pas « y » ; seul « DELETE » ou « SUPPRIMER » la lance."""
        import builtins
        import io
        m = charger("hpa_irr", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en"})
        self.assertTrue(m.is_irreversible(f"rm -- {self.d}/a"))
        self.assertTrue(m.is_irreversible("xargs -d '\\n' -a /tmp/liste rm -v --   # deletes the files"))
        self.assertTrue(m.is_irreversible("pct delsnapshot 105 Debian13"))
        self.assertTrue(m.is_irreversible("zfs destroy data/zd0/test@old"))
        self.assertFalse(m.is_irreversible("touch /tmp/x"))
        self.assertFalse(m.is_irreversible("echo rm"))
        self.assertFalse(m.is_irreversible("zpool list -o name,alloc,free,cap data"))
        fa, fb = os.path.join(self.d, "a"), os.path.join(self.d, "b")
        for f in (fa, fb):
            open(f, "w").close()
        commandes = [("supprimer a", [f"rm -- {fa}"]), ("supprimer b", [f"rm -- {fb}"])]
        reponses = iter(["y", "DELETE"])
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        anciens = (sys.stdin, sys.stdout, builtins.input, os.geteuid)
        sortie = Terminal()
        sys.stdin, sys.stdout, builtins.input, os.geteuid = Terminal(), sortie, lambda _q="": next(reponses), lambda: 0
        m.input = builtins.input
        try:
            m.confirm_changes(commandes)
        finally:
            sys.stdin, sys.stdout, builtins.input, os.geteuid = anciens
        self.assertTrue(os.path.exists(fa))                                         # « y » refused
        self.assertFalse(os.path.exists(fb))                                        # « DELETE » accepted
        self.assertIn("IRREVERSIBLE", sortie.getvalue())

    def test_retention_qui_ne_s_applique_pas(self):
        """1.15 : des sauvegardes dans un sous-dossier que Proxmox ne voit pas (sa rétention ne s'y applique jamais) ; au-delà de keep-last, la liste
        des fichiers à supprimer est écrite et la place libérée annoncée ; les sauvegardes d'un invité disparu sont gardées."""
        vz = os.path.join(self.d, "vz")
        self.write("pve/storage.cfg", f"dir: local\n\tpath {vz}\n\tcontent iso,vztmpl,backup\n\tprune-backups keep-last=2\n")
        self.write("pve/lxc/105.conf", "hostname: odoo18\nonboot: 1\nunprivileged: 1\ncores: 2\nmemory: 1024\n")
        for jour in range(1, 6):
            self.write(f"vz/dump/latest/vzdump-lxc-105-2026_11_{jour:02d}-23_40_00.tar.zst", "x" * 4096)
            self.write(f"vz/dump/latest/vzdump-lxc-105-2026_11_{jour:02d}-23_40_00.log", "INFO\n")
        self.write("vz/dump/latest/vzdump-qemu-435-2025_12_02-02_00_00.vma.zst", "y" * 4096)
        self.mock("pvesm", "echo 'Volid Format  Type  Size VMID'")
        etat = os.path.join(self.d, "etat")
        m = charger("hpa_b", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en", "HOST_PERF_AUDIT_PVE_DIR": os.path.join(self.d, "pve"),
                                                    "HOST_PERF_AUDIT_STATE_DIR": etat, "HOST_PERF_AUDIT_VZDUMP_CONF": os.path.join(self.d, "rien.conf")})
        ancien = os.environ.get("PATH", "")
        os.environ["PATH"] = self.env["PATH"]
        try:
            trouve = m.backup_findings(m.guest_names())
        finally:
            os.environ["PATH"] = ancien
        textes = "\n".join(t for _l, t, _c in trouve)
        self.assertIn(f"storage local: 6 backups under {vz}/dump but Proxmox sees 0 — 6 are in a sub-folder (latest) where the retention (keep-last=2) never applies", textes)
        self.assertIn("storage local: 3 backups beyond the retention (keep-last=2, the 2 newest of each guest kept) — deleting them frees", textes)
        self.assertIn("105 (odoo18): 3 (", textes)
        self.assertIn("backups of guests that no longer exist, kept: 435: 1 (", textes)
        liste = open(os.path.join(etat, "backups-to-delete-local.txt"), encoding="utf-8").read().split()
        self.assertEqual(sorted(os.path.basename(x) for x in liste),
                         [f"vzdump-lxc-105-2026_11_0{j}-23_40_00.{e}" for j in (1, 2, 3) for e in ("log", "tar.zst")])     # the 3 oldest, their logs; never 435
        commandes = [c for _l, _t, cs in trouve for c in cs]
        self.assertTrue(any(c.startswith("xargs -d '\\n' -a ") and " rm -v --" in c for c in commandes), commandes)
        self.assertFalse(any(m.is_read_only(c) for c in commandes if " rm " in c))

    def test_aucun_invite_n_attend(self):
        """1.10: « Guest that waited most ... (0.0 % of its time) » contradicted the verdict: the wait is then in the tasks of the host."""
        m = charger("hpa_g", "host-perf-audit.py", {"HOST_PERF_AUDIT_LANG": "en", "NGINX_TOOLS_LANG": "en"})
        faits = {"disks": {"sda": {"kind": "HDD"}}}
        ligne = (0, "430", "vm", "bbb30.dev", 15, 79, 0, 0, 0.01, 0)
        out = []
        m.ssd_answer(m.Findings(), [], 16.0, 6.0, faits, [ligne], out, {"vzdump 101"})
        texte = "\n".join(out)
        self.assertNotIn("Guest that waited most", texte)
        self.assertIn("No guest waited for the disk during this measurement: the wait is in the tasks of the host itself", texte)
        self.assertIn("seen running: vzdump 101", texte)
        out = []
        m.ssd_answer(m.Findings(), [], 16.0, 6.0, faits, [ligne[:8] + (12.5, 40)], out)
        self.assertIn("Guest that waited most for the disk: 430 bbb30.dev (12.5 % of its time)", "\n".join(out))

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
