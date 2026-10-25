# -*- coding: utf-8 -*-
"""app-log-live 1.76 : TOUS les réglages changés à la volée sont sauvegardés (touche C), adresses déjà bannies (iptables / ufw) retirées de la liste, suivi des modules customs
au démarrage, connectés Odoo / SSH ; apps/_limites.py : détail des 429 d'une adresse (--rate-limit)."""
import datetime
import importlib.util
import os
import re
import subprocess
import sys
import time
import unittest
from unittest import mock

from helpers import EnvTest, script_path

ENVIRONNEMENT = "commun"


def load(nom_fichier, name, env=None):
    with mock.patch.dict(os.environ, env or {}):
        spec = importlib.util.spec_from_file_location(name, script_path(nom_fichier))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class Base(EnvTest):
    def setUp(self):
        super().setUp()
        self.env.update(NGINX_TOOLS_ETC_DEFAULT=os.path.join(self.d, "etc"), HOME=self.d, NGINX_TOOLS_CONFIG_CREER="0")
        os.makedirs(os.path.join(self.d, "etc"), exist_ok=True)

    def live(self):
        return load("app-log-live.py", "live_rbl", self.env)


class ToutEstSauvegarde(Base):
    def options(self, **modif):
        o = {"health": 30.0, "keep_ip": True, "highlight_words": [], "level": 9, "minimal": False, "modules_sort": ("name", False, False), "not_found": False,
             "suspect": False, "only": [], "exclude": [], "group": None, "chime": None, "report_min": 0.0, "watch": []}
        o.update(modif)
        return o

    def test_time_report_est_sauvegarde(self):
        """Le cas signalé : --time-report 10 changé par la touche T doit apparaître dans les réglages à écrire."""
        live = self.live()
        start_state = live.config_values(self.options(), False, (45, 45))
        after = live.config_values(self.options(report_min=10.0), False, (45, 45))
        self.assertEqual(live.config_changes(after, start_state), {"TIME_REPORT": "10"})

    def test_chaque_option_changee_par_le_menu_a_sa_cle(self):
        """Toute option modifiée par la fonction touche() (options["x"] = …) doit être lue par valeurs_config, sinon « Aucun réglage changé »."""
        text = open(script_path("app-log-live.py"), encoding="utf-8").read()
        start = text.index("    def key(key_value):")
        key = text[start:text.index("\n    def ", start + 10)]
        modifiees = set(re.findall(r'options\["([a-z_]+)"\]\s*=(?!=)', key)) | set(re.findall(r'^\s*options\["([a-z_]+)"\],', key, re.M))
        derives = {"highlight_pattern", "membres"}                         # recalculated from another option
        body = text[text.index("def config_values"):text.index("def config_changes")]
        for name in sorted(modifiees - derives):
            with self.subTest(option=name):
                self.assertRegex(T(body), rf'options(?:\[|\.get\()["\']{name}["\']', f"options['{name}'] est changée par le menu mais pas sauvegardée (valeurs_config)")

    def test_toutes_les_cles_de_valeurs_config_sont_dans_le_schema(self):
        live = self.live()
        values = live.config_values(self.options(), False, (45, 0))
        for key_value in values:
            self.assertIn(key_value, live.SCHEMA_CONFIG, f"{key_value} sauvegardée mais jamais relue au lancement")

    def test_relecture_des_valeurs_ecrites(self):
        """Ce que la touche C écrit doit être relu comme valeur par défaut des options au lancement suivant."""
        live = self.live()
        cfg = load("apps/_config.py", "cfg_rbl", self.env)
        values = live.config_values(self.options(report_min=10.0, chime=1, only=["a", "b"], suspect=True, watch=["reg"], group="Equipe"), False, (60, 0))
        defaults, problems = cfg.defauts_options(values, live.SCHEMA_CONFIG)
        self.assertEqual(problems, [])
        self.assertEqual((defaults["time_report"], defaults["chime"], defaults["only"], defaults["suspect"], defaults["watch"], defaults["accentuate_group"], defaults["dns_max"]),
                         (10.0, 1, ["a", "b"], True, "reg", "Equipe", 60))
        self.assertNotIn("dns_max_truncate", defaults)        # empty: option not touched

    def test_ecriture_dans_le_fichier(self):
        live = self.live()
        path = os.path.join(self.d, "app-log-live.conf")
        live.write_config(path, {"TIME_REPORT": "10", "ONLY": ""})
        lines = open(path, encoding="utf-8").read().splitlines()
        self.assertIn("TIME_REPORT=10", T(lines))
        self.assertIn("ONLY=", T(lines))

    def test_chime_valide(self):
        live = self.live()
        self.assertEqual(live._chime_config("2"), 2)
        with self.assertRaises(ValueError):
            live._chime_config("7")


class DejaBannie(Base):
    def test_iptables_et_ufw_sont_lus(self):
        self.mock("iptables", 'echo "-P INPUT ACCEPT"; echo "-A INPUT -s 11.26.17.163/32 -j DROP"; echo "-A INPUT -s 10.0.0.0/8 -j DROP"; echo "-A INPUT -p tcp --dport 80 -j ACCEPT"')
        self.mock("ip6tables", "exit 1")
        self.mock("ufw", 'echo "Status: active"; echo "Anywhere                   DENY        11.0.67.32"; echo "22/tcp ALLOW Anywhere"')
        with mock.patch.dict(os.environ, {"PATH": self.bin + os.pathsep + os.environ["PATH"]}):
            live = self.live()
            ips = {str(a) for a in live.Bans.read_firewall()}
        self.assertEqual(ips, {"11.26.17.163", "11.0.67.32"})      # the network 10.0.0.0/8 is not an address

    def test_pare_feu_illisible(self):
        self.mock("iptables", "exit 1")
        self.mock("ip6tables", "exit 1")
        self.mock("ufw", "exit 1")
        with mock.patch.dict(os.environ, {"PATH": self.bin + os.pathsep + os.environ["PATH"]}):
            self.assertIsNone(self.live().Bans.read_firewall())

    def test_regles_conditionnelles_et_boucle_locale_ne_sont_pas_des_bannissements(self):
        """Défaut vu en 1.76 : 127.0.0.1 (warmup, sondes) étiqueté [banni : pare-feu] à cause d'une règle limitée à une interface."""
        self.mock("iptables", '''echo "-A INPUT -s 127.0.0.1/32 ! -i lo -j DROP"; echo "-A INPUT -s 127.0.0.1/32 -j DROP"; echo "-A INPUT -s 5.5.5.5/32 -p tcp -m tcp --dport 22 -j DROP"
echo "-A INPUT -s 6.6.6.6/32 -m comment --comment \\"ban nginx-log-audit\\" -j DROP"; echo "-A INPUT -s 7.7.7.7/32 -j REJECT --reject-with icmp-port-unreachable"; echo "-A INPUT -s 8.8.8.8/32 -j ACCEPT"''')
        self.mock("ip6tables", "exit 1")
        self.mock("ufw", 'echo "22/tcp                     DENY        9.9.9.9"; echo "Anywhere                   DENY IN     4.4.4.4"; echo "Anywhere                   DENY        127.0.0.1"')
        with mock.patch.dict(os.environ, {"PATH": self.bin + os.pathsep + os.environ["PATH"]}):
            live = self.live()
            ips = {str(a) for a in live.Bans.read_firewall()}
            b = live.Bans()
            b.pf = {__import__("ipaddress").ip_address("127.0.0.1")}
            self.assertIsNone(b.source_of("127.0.0.1"))
        self.assertEqual(ips, {"6.6.6.6", "7.7.7.7", "4.4.4.4"})

    def test_source_de_dit_pare_feu(self):
        live = self.live()
        b = live.Bans()
        import ipaddress
        b.pf = {ipaddress.ip_address("11.26.17.163")}
        self.assertEqual(T(b.source_of("11.26.17.163")), "pare-feu")
        self.assertIsNone(b.source_of("1.2.3.4"))

    def test_a_bannir_retire_les_adresses_deja_bloquees(self):
        """Le bogue signalé : 5 adresses proposées, dont 11.26.17.163 déjà dans iptables."""
        live = self.live()
        import ipaddress
        b = live.Bans()
        b.pf = {ipaddress.ip_address("11.26.17.163")}
        st = live.Stats(5.0)
        st.is_banned = b.source_of
        st.recommended = ["11.131.143.24", "11.26.17.163"]
        st._reco_t = time.time()
        res = [ip for ip, _ in st.to_ban()]
        self.assertEqual(res, ["11.131.143.24"])
        self.assertIn("11.26.17.163", T(st.all_banned))


class SuiviCustoms(Base):
    class Db:
        def __init__(self, state):
            self.state = state

        def bases_odoo(self):
            return ["rlq"]

        def modules_etat(self, database):
            return self.state

    def state(self):
        m = lambda name, v, auteur: {"nom": name, "etat": "installed", "version": v, "auteur": auteur, "maj": "2026-10-01 10:00:00", "cree": "2026-09-01 10:00:00"}
        return [m("base", "18.0.1.3", "Odoo S.A."), m("web", "18.0.1.0", "Odoo S.A."), m("zzz_autre", "1.0", "Quelqu'un"), m("rlq_survey_report", "18.0.1.105.0", "RLQ"), m("rlq_a", "18.0.1.2.0", "RLQ")]

    def test_rlq_en_premier_avec_versions_puis_les_autres_customs(self):
        live = self.live()
        lines = live.customs_tracking_lines(self.Db(self.state()), None, [])
        text = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines))
        self.assertIn("Suivi des modules customs non-standard à Odoo", T(text))
        self.assertLess(text.index("rlq_a"), text.index("rlq_survey_report"))
        self.assertLess(text.index("rlq_survey_report"), text.index("zzz_autre"))
        self.assertIn("18.0.1.105.0", T(text))
        self.assertNotIn("Odoo S.A.", T(text.split("Version", 1)[1]))            # standard modules are not listed
        self.assertIn("Odoo 18.0.1.3", T(text))

    def test_lecture_impossible_est_expliquee(self):
        live = self.live()
        class Vide(self.Db):
            def bases_odoo(self):
                return None
        self.assertIn("root requis", T(" ".join(live.customs_tracking_lines(Vide([]), None, []))))
        self.assertIn("impossible", T(" ".join(live.customs_tracking_lines(None, None, []))))

    def test_affiche_avant_l_historique_et_seulement_avec_l_option(self):
        text = open(script_path("app-log-live.py"), encoding="utf-8").read()
        self.assertLess(text.index("customs_tracking_lines(people.odoo_db"), text.index("Sign-in history ("))
        self.assertIn("if is_odoo and args.modules_startup:", T(text))
        self.assertIn("MODULES_STARTUP", T(text))

    def test_tri_des_colonnes_selon_modules_sort(self):
        live = self.live()
        m = lambda name, v: {"nom": name, "etat": "installed", "version": v, "auteur": "RLQ", "maj": None, "cree": None}
        state = [m("base", "18.0.1.3"), m("rlq_b", "1.0"), m("rlq_a", "2.0"), m("zeta", "9.0"), m("alpha", "1.5")]
        raw = lambda sort_by: re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(live.customs_tracking_lines(self.Db(state), None, [], sort_by)))
        t = raw(("name", True, True))                               # decreasing name: the rlq* ones stay at the top
        self.assertLess(t.index("rlq_a"), t.index("rlq_b"))
        self.assertLess(t.index("rlq_b"), t.index("zeta"))
        self.assertLess(t.index("zeta"), t.index("alpha"))
        t = raw(("name", False, True))
        self.assertLess(t.index("alpha"), t.index("zeta"))


class Connectes(Base):
    def test_odoo_et_ssh(self):
        self.mock("who", 'echo "marcel   pts/0        2026-10-15 08:01 (192.0.2.7)"; echo "root     tty1         2026-10-15 07:00"')
        self.mock("ss", 'case "$*" in *-Htlnp*) echo \'LISTEN 0 128 0.0.0.0:2222 0.0.0.0:* users:(("sshd",pid=7,fd=3))\';; *) echo "ESTAB 0 0 10.0.0.1:2222 192.0.2.7:5555";; esac')   # 1.81: sshd listens on 2222
        live = self.live()
        p = live.Presence(15)
        now = time.time()
        p.login("a", "Alice", "192.0.2.1", now - 60)
        p.login("b", "Bob", "192.0.2.2", now - 4000)
        with mock.patch.dict(os.environ, {"PATH": self.bin + os.pathsep + os.environ["PATH"]}):
            text = re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(live.logged_in_lines(p, now)))
        self.assertIn("Connectés à Odoo : 1", T(text))
        self.assertIn("Alice", T(text))
        self.assertNotIn("Bob", T(text))                                  # inactif depuis plus de 15 minutes
        self.assertIn("Connectés en SSH : 1", T(text))
        self.assertIn("marcel depuis 192.0.2.7", T(text))
        self.assertIn("connexions TCP établies : 1 (port SSH 2222)", T(text))


class Limites429(Base):
    def setUp(self):
        super().setUp()
        self.m = load("apps/_limites.py", "lim_rbl")
        self.folder = os.path.join(self.d, "nginx")
        os.makedirs(self.folder)
        T = datetime.datetime(2026, 10, 13, 10, 0, 0, tzinfo=datetime.timezone.utc)
        L = lambda ip, i, req, code: f'{ip} - - [{(T + datetime.timedelta(seconds=i)).strftime("%d/%b/%Y:%H:%M:%S +0000")}] "{req} HTTP/1.1" {code} 10 "-" "UA"\n'
        with open(os.path.join(self.folder, "access.log"), "w") as f:
            f.writelines([L("11.97.88.222", 0, "GET /event/x/track", 429) for _ in range(30)] + [L("11.97.88.222", 1, "GET /event/x/track", 200)]
                         + [L("11.97.88.222", 2, "GET /web/static/a.js", 429), L("11.97.88.222", 3, "POST /web/login", 429), L("11.97.88.222", 4, "GET /page", 429),
                            L("9.9.9.9", 0, "GET /autre", 429)])
        with open(os.path.join(self.folder, "error.log"), "w") as f:
            f.write('2026/10/13 06:00:00 [error] 1#1: *1 limiting requests, excess: 61.500 by zone "odoo_general", client: 11.97.88.222, server: x, request: "GET /event/x/track HTTP/2.0", host: "x"\n'
                    '2026/10/13 06:00:01 [error] 1#1: *2 limiting requests, excess: 1.000 by zone "odoo_login", client: 9.9.9.9, server: x, request: "POST /web/login HTTP/2.0", host: "x"\n'
                    '2026/10/13 06:00:02 [warn] 1#1: *3 limiting connections by zone "odoo_visiteur", client: 11.97.88.222, server: x, request: "GET /event/x/track HTTP/2.0", host: "x"\n')

    def test_analyse(self):
        f = self.m.analyser("11.97.88.222", self.folder)
        self.assertEqual(f["requetes"], 34)
        self.assertEqual(f["codes"]["429"], 33)
        self.assertEqual(f["par_url"].most_common(1)[0], ("/event/x/track", 30))
        self.assertEqual(f["zones"], {"odoo_general": 1, "odoo_visiteur (limit_conn)": 1})
        self.assertEqual(f["excess_max"], 61.5)
        self.assertEqual((f["effets"]["fond"], f["effets"]["ressource"], f["effets"]["action"], f["effets"]["page"]), (30, 1, 1, 1))

    def test_une_autre_adresse_n_est_pas_melangee(self):
        f = self.m.analyser("9.9.9.9", self.folder)
        self.assertEqual(f["requetes"], 1)
        self.assertEqual(f["zones"], {"odoo_login": 1})

    def test_rapport_et_recommandations(self):
        text = "\n".join(self.m.lignes(self.m.analyser("11.97.88.222", self.folder)))
        self.assertIn("refusées en 429 : 33", T(text))
        self.assertIn("/event/x/track", T(text))
        self.assertIn("odoo_general ×1", T(text))
        self.assertIn("odoo_visiteur (limit_conn) ×1", T(text))
        self.assertIn("limit_conn odoo_visiteur 16", T(text))
        self.assertIn("action(s) POST refusée(s)", T(text))
        self.assertIn("burst", T(text))

    def test_aucun_journal(self):
        empty = os.path.join(self.d, "vide")
        os.makedirs(empty)
        self.assertIsNone(self.m.analyser("1.2.3.4", empty))
        self.assertIn("illisibles", T("".join(self.m.lignes(None))))

    def test_journal_compresse(self):
        import gzip
        with open(os.path.join(self.folder, "access.log"), "rb") as f, gzip.open(os.path.join(self.folder, "access.log.2.gz"), "wb") as g:
            g.write(f.read())
        self.assertEqual(self.m.analyser("11.97.88.222", self.folder)["requetes"], 68)

    def test_option_rate_limit_adresse_invalide(self):
        r = subprocess.run([sys.executable, script_path("app-log-live.py"), "--rate-limit", "pas-une-ip"], capture_output=True, text=True, env=dict(os.environ, **self.env))
        self.assertEqual(r.returncode, 2)
        self.assertIn("adresse IP invalide", r.stderr)


if __name__ == "__main__":
    unittest.main()


_LIVE_TR = None


def T(texte):
    """Texte renvoyé directement par une fonction du programme (source anglaise) -> même texte traduit en français, comme à l'écran."""
    global _LIVE_TR
    if _LIVE_TR is None:
        spec = importlib.util.spec_from_file_location("live_tr", script_path("app-log-live.py"))
        _LIVE_TR = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_LIVE_TR)
    if not isinstance(texte, str):
        texte = "\n".join(str(x) for x in texte)
    return _LIVE_TR.TR(texte)

