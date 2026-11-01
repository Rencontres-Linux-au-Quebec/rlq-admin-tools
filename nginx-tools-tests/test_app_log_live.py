"""app-log-live.py — journal de l'application en temps réel : heure ISO locale sans doublons, adresses IP remplacées (personne,
équipe, DNS, ISP) suivies de l'adresse, --min, couleurs, présence des personnes, flux jamais bloqué par une recherche lente."""
import contextlib
import datetime
import collections
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest.mock

ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo : journal systemd ; BigBlueButton : journaux en fichiers)

from helpers import SCRIPTS_DIR, EnvTest, script_path

# Ordinary PUBLIC addresses: the documentation ones (192.0.2.x, 198.51.100.x, 203.0.113.x) are "private" for Python.
PERSONNE, DNS, ISP, LENT = "11.97.88.180", "93.184.216.34", "11.42.88.181", "8.8.4.4"
AUTRE, TROISIEME = "11.101.16.52", "11.114.10.1"
FUSEAU = datetime.timezone(datetime.timedelta(hours=-4))


ANSI = re.compile(r"\x1b\[[0-9;]*m|[\ue001\ue002]")
os.environ.setdefault("APP_LOG_LIVE_SITEMAP", "off")      # 1.143: the programs run here have no network: no default sitemap read


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
    return _LIVE_TR.translate_protected(texte)


def ts(delta=0.0, fixe=None):
    """Horodatage de « journalctl -o short-iso-precise » (heure locale) ; delta = secondes dans le passé."""
    dt = fixe or (datetime.datetime.now(FUSEAU) - datetime.timedelta(seconds=delta))
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")


def block(code="200", req="GET  /event", sql="105", t1="0.046", t2="0.426"):
    """Fin d'une ligne de werkzeug telle qu'elle est affichée : le bloc « H1.1 200 … » AVANT la requête."""
    return f'H1.1 {code} {"-":>4} {sql:>4} {t1:>6} {t2:>6}       {req}'  # 1.133: 4 more blanks: the OS column (3 characters) sits before the GET; 1.121: size column 4 wide


def odoo(level, database, logger, text, delta=0.0, fixe=None):
    dt = fixe or (datetime.datetime.now(FUSEAU) - datetime.timedelta(seconds=delta))
    utc = dt.astimezone(datetime.timezone.utc)
    return (f"{ts(delta, fixe)} odoo18 odoo[502385]: {utc:%Y-%m-%d %H:%M:%S},{utc.microsecond // 1000:03d} 502385 {level} {database} {logger}: {text}")


def live_width(line):
    """Columns of a screen line (colors ignored, a wide character counts 2)."""
    import unicodedata
    plain = ANSI.sub("", line)
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in plain)


def werkzeug(ip, url="/event", code=200, delta=0.0, fixe=None, methode="GET"):
    dt = fixe or (datetime.datetime.now(FUSEAU) - datetime.timedelta(seconds=delta))
    utc = dt.astimezone(datetime.timezone.utc)
    return odoo("INFO", "base", "werkzeug", f'{ip} - - [{utc:%d/%b/%Y %H:%M:%S}] "{methode} {url} HTTP/1.1" {code} - 105 0.046 0.426', delta, fixe)


def login(ip, login, delta=0.0, database="base", fixe=None):
    return odoo("INFO", database, "odoo.addons.base.models.res_users", f"Login successful for db:{database} login:{login} from {ip}", delta, fixe)


def histo(ip, login, database="base"):
    return (f"2026-09-28T10:00:00-0400 odoo18 odoo[1]: 2026-09-28 14:00:00,000 1 INFO {database} "
            f"odoo.addons.base.models.res_users Login successful for db:{database} login:{login} from {ip}")


UTILISATEURS = ("506\\037etienne@exemple.org\\037Étienne Dupont\\037f\\n507\\037alice@exemple.org\\037Alice A\\037f\\n"
                "508\\037bob@exemple.org\\037Bob B\\037f\\n509\\037carl@exemple.org\\037Carl C\\037t\\n")


def column(visible, width=18):
    """La colonne d'adresse telle que le programme l'écrit : « pays adresse » (sans crochets) complétée à la largeur fixe, puis un espace ; 1.91 : une adresse
    SANS pays est précédée de 3 espaces (sous les adresses des autres lignes)."""
    if not re.match(r"[A-Z]{2} ", visible):
        visible = "   " + visible
    return visible.ljust(width) + " "


class AppLogLive(EnvTest):
    def setUp(self):
        super().setUp()
        self.prog = self.prepare("app-log-live.py")
        self.mock("fail2ban-client", "exit 1")           # never the real bans of the test server: "unreadable" sources by default
        self.mock("ipset", "exit 1")
        # CONTROLLED team list: the test does not depend on the real list (11.97.88.180 is in it: the country is not shown for the team)
        self.equipe_ip, self.equipe_nom = "100.64.0.7", "Étienne (cellulaire Vidéotron, adresse actuelle — peut changer)"
        self.liste_blanche(f"{self.equipe_ip}  # {self.equipe_nom}\n")
        self.write("history.txt", histo(PERSONNE, "etienne@exemple.org") + "\n")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        self.journal([werkzeug(PERSONNE), werkzeug(DNS), werkzeug(ISP), werkzeug("127.0.0.1"), werkzeug(self.equipe_ip)])
        self.mock("getent", f'echo "$@" >> {self.d}/getent.log; case "$2" in {DNS}) echo "{DNS} srv.exemple.org"; exit 0;; '
                            f'{LENT}) sleep 2; echo "{LENT} lent.exemple.org"; exit 0;; esac; exit 2')
        self.write("rdap.json", json.dumps({"name": "VL-Q", "country": "CA", "cidr0_cidrs": [{"v4prefix": "11.40.0.0", "length": 14}],
                                            "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Videotron Ltee"]]]}]}))
        self.mock("curl", f'[[ "$*" == *ifconfig.me* ]] && exit 22; echo "$@" >> {self.d}/curl.log; [[ "$*" == *rdap.org/ip/{ISP}* ]] && cat {self.d}/rdap.json || exit 22')
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; printf "{UTILISATEURS}"')

    def journal(self, lines, after=""):
        self.write("stream.txt", "\n".join(lines) + "\n")
        self.mock("journalctl", f'echo "$@" >> {self.d}/journalctl.log; case "$*" in *" -g "*) cat {self.d}/history.txt;; '
                                f'*) cat {self.d}/stream.txt; {after or "true"};; esac')

    def run_cmd(self, cmd, *args, **kwargs):
        """1.98 : --min est actif par défaut ; les tests écrits pour l'affichage complet (base, « werkzeug ») demandent --no-min, sauf s'ils passent
        eux-mêmes --min ou --no-min."""
        return super().run_cmd(self.sans_min(cmd, ip=True), *args, **kwargs)

    def sans_min(self, cmd, ip=False):
        """1.112 : l'adresse IP est masquée PAR DÉFAUT (HIDE_IP, 1.107) ; les tests qui lisent les adresses demandent --show-ip, sauf ceux qui testent ce défaut
        (nom du test : hide_ip / par_defaut / ip_gardee) ou qui passent eux-mêmes une option d'adresse."""
        if len(cmd) > 1 and cmd[1] == self.prog and not any(o in cmd for o in ("--min", "--no-min", "--help", "--version", "--changelog")):
            extra = ["--no-min"]
            if ip and not any(m in self._testMethodName for m in ("hide_ip", "par_defaut", "ip_gardee")) and not any(o in cmd for o in ("--show-ip", "--hide-ip")):
                extra.append("--show-ip")
            return cmd[:2] + extra + cmd[2:]
        return cmd

    def lancer(self, *args, env_extra=None):
        if "--status-every" not in args:                                   # 1.125: the status bar is shown at startup; the tests that count the lines do not want it
            args = (*args, "--status-every", "0")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", *args], env_extra)
        self.assertNotIn("Traceback", err, err)
        return rc, out, err

    def run_pty(self, cmd, *args, **kwargs):
        """Dans un vrai terminal, app-log-live 1.88-1.89 anonymise, raccourcit et souligne une ligne sur 5 PAR DÉFAUT : les tests qui comparent les couleurs et
        les adresses exactes demandent l'affichage brut (sauf un test qui passe lui-même une de ces options)."""
        if len(cmd) > 1 and cmd[1] == self.prog and not any(o in cmd for o in ("--anonymize", "--no-anonymize", "--truncate", "--no-truncate", "--no-underline")):
            cmd = cmd[:2] + ["--no-anonymize", "--no-truncate", "--no-underline"] + cmd[2:]
        return super().run_pty(self.sans_min(cmd), *args, **kwargs)

    def test_valeurs_par_defaut_198_min_underline_highlight_et_valeurs_en_anglais(self):
        """1.98 : MIN=yes, UNDERLINE=10 et « -2026- » dans HIGHLIGHT par défaut ; --no-min ou MIN=no : tout ; une valeur française (MIN=non) est lue
        (même sens) avec un avertissement demandant l'anglais ; le menu et le résumé des options écrivent yes / no."""
        live = self.module_live()
        self.assertTrue(live.MIN_DEFAULT)
        self.assertEqual(live.UNDERLINE_DEFAULT, 10)
        self.assertEqual(live._underline_config("yes"), 10)
        self.assertIn("-2026-", live.read_highlight(None))
        self.assertIn("-2026-", live.read_highlight("+odoo"))                     # "+word" is added to the default list, which keeps "-2026-"
        base = ["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--no-presence", "--no-banned"]
        rc, out, err = super().run_cmd(base)                                      # without --no-min added by the test: the program's default value
        self.assertNotIn("Traceback", err, err)
        self.assertIn("srv.exemple.org", out)
        self.assertNotIn("werkzeug", out)
        rc, out, err = super().run_cmd(base + ["--no-min"])
        self.assertIn("base werkzeug", out)
        etc = os.path.join(self.d, "etc-defaut-198")
        os.makedirs(etc)
        with open(os.path.join(etc, "app-log-live.conf"), "w", encoding="utf-8") as f:
            f.write("MIN=non\nHIDE_IP=no\n")
        rc, out, err = super().run_cmd(base, {"NGINX_TOOLS_ETC_DEFAULT": etc, "APP_LOG_LIVE_LANG": "fr"})
        self.assertNotIn("Traceback", err, err)
        self.assertIn("base werkzeug", out)                                       # MIN=non lu comme MIN=no
        self.assertIn("MIN=non → no", err)
        self.assertNotIn("HIDE_IP=no →", err)
        self.assertIn("--min no", out + err)                                      # options summary: values in English, even in French
        self.assertNotIn("--min non", out + err)

    def test_199_steps_line_touche_F_et_limite_d_enregistrement_60_minutes(self):
        """1.99 : --steps-line (touche F) affiche les étapes d'un enregistrement sur UNE ligne blanche, tronquée si besoin ; --record-max est plafonné
        à 60 minutes (0 et plus de 60 sont refusés à la ligne de commande comme dans le fichier de configuration)."""
        live = self.module_live()
        self.assertEqual(live.RECORD_MAX_DEFAULT, 60.0)
        self.assertEqual(live.RECORD_MAX_LIMIT, 60.0)
        self.assertEqual(live.STEPS_LINE_STYLE, "30;107")                        # texte noir sur fond blanc, les deux explicites
        self.assertEqual(live.MENU_KEYS.get(b"F"), "steps_line")
        self.assertTrue(live.steps_line_text([], 120))                           # "no step": never an empty line
        steps = [{"n": 1, "description": "Connexion", "start": 0.0, "end": 1.0}, {"n": 2, "description": "Sondage complet", "start": 1.0, "end": None}]
        full = live.steps_line_text(steps, 200)
        self.assertIn("1✔ Connexion", full)
        self.assertIn("2▶ Sondage complet", full)                                 # the current step is marked with ">"
        short = live.steps_line_text(steps, 10)                                  # too narrow: descriptions removed, the last step complete
        self.assertIn("2▶ Sondage complet", short)
        self.assertNotIn("1✔ Connexion", short)
        base = ["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--no-presence", "--no-banned"]
        for valeur in ("0", "61"):
            rc, out, err = super().run_cmd(base + ["--record-max", valeur])
            self.assertNotEqual(rc, 0, valeur)
            self.assertIn("60 minutes", err)                                     # message in English or in French
        rc, out, err = super().run_cmd(base + ["--steps-line"])
        self.assertNotIn("Traceback", err, err)

    def test_terminal_par_defaut_soulignee_anonymisee_et_raccourcie_mais_jamais_dans_un_tube(self):
        """1.88-1.89 : dans un terminal, par défaut : une ligne sur 5 soulignée, adresses en pseudonymes (IP-xxxxxx), ligne trop large raccourcie en
        « début ... deux derniers mots » à $COLUMNS - 10 ; dans un tube (un autre programme lit la sortie) : lignes entières, vraies adresses, rien de souligné."""
        longue = "/event/journee-portes-ouvertes-2026/registration/confirm?ticket=12&utm_source=infolettre-octobre&utm_campaign=rappel-final-de-la-journee" + "&x=" + "y" * 80 + "&fin=journee"
        self.journal([werkzeug(DNS, f"/page-{i}") for i in range(9)] + [werkzeug(DNS, longue), werkzeug(DNS, "/fin")])
        text, _ = super().run_pty(["python3", self.prog, "--no-follow", "--no-min", "--no-history", "--no-isp", "--no-presence", "--no-banned", "--show-ip"], [],
                                  env_extra={"COLUMNS": "230"}, keep_ansi=True)      # 1.91: wide enough for the columns (only the message is cut)
        lignes = [l for l in text.splitlines() if "werkzeug" in ANSI.sub("", l)]
        self.assertEqual(len(lignes), 11, text)
        self.assertEqual([l.startswith("\x1b[4m") for l in lignes], [False] * 9 + [True, False])      # 1.98: the 10th line of the stream (UNDERLINE=10 by default)
        self.assertTrue(all(DNS not in ANSI.sub("", l) and "IP-" in ANSI.sub("", l) for l in lignes), "\n".join(lignes))
        cinquieme = ANSI.sub("", lignes[9]).rstrip()
        self.assertLessEqual(len(cinquieme), 220, cinquieme)
        self.assertIn("…", cinquieme)
        self.assertTrue(cinquieme.endswith("journee"), cinquieme)                                      # la fin de l'URL reste visible
        rc, out, err = self.lancer("--show-ip", "--no-history", "--no-isp", "--no-presence", "--no-banned")
        self.assertIn(longue, out)
        self.assertIn(DNS, out)
        self.assertNotIn("\x1b[4m", out)
        self.assertNotIn("IP-", out)

    # ---------------------------------------------------------------------------------------------------------------
    def test_colonnes_alignees_en_francais_et_en_anglais_avec_accents_nfd_et_chinois(self):
        """run-all 1.188 : données d'exemple (donnees_exemples.py) — noms accentués, anglais, accent COMBINANT (NFD) et chinois à la place de l'adresse :
        dans les deux langues, « base werkzeug » et « H1.1 » commencent à la même COLONNE d'écran sur chaque ligne (largeur, pas nombre de caractères)."""
        import donnees_exemples as ex
        noms = ex.PERSONNES_FR[:3] + ex.PERSONNES_EN[:2] + [ex.PERSONNE_NFD, ex.PERSONNE_CJK]
        ips = [f"100.64.1.{i + 1}" for i in range(len(noms))]
        self.liste_blanche("".join(f"{ip}  # {nom}\n" for ip, nom in zip(ips, noms)))
        self.journal([werkzeug(ip, f"/événement/{i}") for i, ip in enumerate(ips)] + [odoo("INFO", "base", "odoo.addons.mail.models.mail_mail", "Courriel envoyé à Hélène")])
        for langue in ("fr", "en"):
            with self.subTest(langue=langue):
                rc, out, err = self.lancer("--no-presence", "--no-isp", "--lang", langue)
                lignes = [ANSI.sub("", l) for l in out.splitlines() if l.strip()]
                self.assertEqual(len(lignes), len(noms) + 1, out + err)
                for nom, l in zip(noms, lignes):
                    self.assertIn(nom, l)
                http = {ex.largeur(l[:l.index("H1.1")]) for l in lignes[:-1]}
                self.assertEqual(len(http), 1, "H1.1 à des colonnes différentes :\n" + "\n".join(lignes))
                logger = {ex.largeur(l[:l.index("base ")]) for l in lignes}
                self.assertEqual(len(logger), 1, "\n".join(lignes))

    def test_adresses_remplacees_dans_l_ordre_de_priorite(self):
        rc, out, err = self.lancer("--no-presence", "--dns-max", "45")
        self.assertEqual(rc, 0, err)
        lines = out.splitlines()
        self.assertEqual(len(lines), 5, out)
        # The address (and its country) is in a fixed-width COLUMN just after the level; the NAME takes its place in the text
        self.assertRegex(T(lines[0]), rf'INFO +{PERSONNE}\s+base werkzeug Étienne Dupont\s+H1\.1 \d+[ \d.-]*GET  /event')             # nobody already connected
        self.assertRegex(T(lines[1]), rf'INFO +{DNS}\s+base werkzeug srv\.exemple\.org\s+')                          # nom DNS
        self.assertRegex(T(lines[2]), rf'INFO CA {ISP}\s+base werkzeug Videotron Ltee \(org\)\s+')                 # owner of the block + country
        self.assertRegex(T(lines[3]), r'INFO +127\.0\.0\.1\s+base werkzeug ce serveur\s+')                              # boucle locale
        self.assertRegex(T(lines[4]), rf'INFO +{self.equipe_ip}\s+base werkzeug Étienne \(cellulaire Vidéotron, adresse actuelle\)\s+')
        self.assertEqual(len({l.index("base werkzeug") for l in lines}), 1, "les messages doivent être alignés :\n" + out)
        self.assertNotIn("(équipe)", out)
        self.assertNotIn("\x1b[", out, "pas de couleur dans un tube")
        self.assertIn("1 adresses connues par une connexion au site", err)
        with open(os.path.join(self.d, "journalctl.log")) as f:
            commands = f.read()
        self.assertIn("--lines 50 --no-pager -u erplibre.service -o short-iso-precise", commands)

    def test_format_iso_local_sans_doublons(self):
        """Heure locale 2026-10-02 10:07:18.33 (centièmes arrondis), sans l'heure UTC d'Odoo, sans les deux PID, sans la date de
        werkzeug ; les « : » de l'heure ne sont pas des adresses IPv6 ; adresse en colonne fixe après le niveau."""
        fixe = datetime.datetime(2026, 10, 2, 10, 7, 18, 326421, FUSEAU)
        self.journal([werkzeug(PERSONNE, fixe=fixe)])
        rc, out, err = self.lancer("--no-presence")
        self.assertEqual(out.strip(), '2026-10-02 10:07:18.33 odoo18 odoo INFO ' + column(PERSONNE)
                                      + 'base werkzeug ' + 'Étienne Dupont'.ljust(45) + ' ' + block())       # name on 45 characters
        for doublon in ("14:07:18", "02/Oct/2026", "502385", "[]"):
            self.assertNotIn(doublon, out)
        # Rounding with carry: .996 -> next second; line of another program (not Odoo): header normalized too
        self.journal([werkzeug(PERSONNE, fixe=datetime.datetime(2026, 10, 2, 10, 7, 18, 996400, FUSEAU)),
                      f"{ts(fixe=fixe)} odoo18 systemd[1]: Started erplibre.service - ERPLibre."])
        out = self.lancer("--no-presence")[1]
        self.assertTrue(out.startswith("2026-10-02 10:07:19.00 odoo18 odoo INFO"), out)
        self.assertIn("2026-10-02 10:07:18.33 odoo18 systemd: Started erplibre.service - ERPLibre.", out)

    def test_min_sans_base_ni_werkzeug_et_sans_le_bruit_de_fetchmail(self):
        fixe = datetime.datetime(2026, 10, 2, 10, 7, 18, 326421, FUSEAU)
        self.journal([werkzeug(PERSONNE, fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.mail.models.fetchmail", "Fetching mail from server 'x'", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.base.models.ir_cron", "Job 'Mail: Fetchmail Service' (9) starting", fixe=fixe),
                      odoo("ERROR", "base", "odoo.addons.mail.models.fetchmail", "Failed to fetch mail", fixe=fixe),
                      odoo("WARNING", "base", "odoo.addons.base.models.ir_cron", "Job 'Mail: Fetchmail Service' (9) failed", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.base.models.ir_cron", "Job 'Autovacuum' (3) starting", fixe=fixe)])
        out = self.lancer("--min", "--show-ip", "--no-presence")[1]
        lines = out.splitlines()
        self.assertEqual(lines[0], '2026-10-02 10:07:18.33 odoo18 odoo INFO ' + column(PERSONNE)
                                    + 'Étienne Dupont'.ljust(45) + ' ' + block())
        self.assertNotIn("werkzeug", out)
        self.assertNotIn("Fetching mail", out)                                                    # INFO noise discarded
        self.assertNotIn("(9) starting", out)
        self.assertRegex(out, r"ERR\s+odoo\.addons\.mail\.models\.fetchmail\s+Failed to fetch mail")       # error: never discarded
        self.assertRegex(out, r"WARN\s+odoo\.addons\.base\.models\.ir_cron\s+Job 'Mail: Fetchmail Service' \(9\) failed")
        self.assertIn("Job 'Autovacuum' (3) starting", out)                                       # other task: kept
        self.assertEqual(len(lines), 4)
        self.assertNotIn(" base ", out)                                                           # plus de nom de base
        complete = self.lancer("--no-presence")[1]                                                  # sans --min : tout, avec la base
        self.assertIn("Fetching mail", complete)
        self.assertRegex(complete, rf"INFO +{PERSONNE}\s+base werkzeug ")

    def test_hide_addons_cache_le_bruit_des_modules_sauf_erreurs_courriels_et_pdf(self):
        fixe = datetime.datetime(2026, 10, 2, 10, 7, 18, 326421, FUSEAU)
        self.journal([werkzeug(PERSONNE, fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.base.models.ir_cron", "Job 'Autovacuum' (3) starting", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.bus.websocket", "Websocket connection opened", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.mail.models.fetchmail", "Fetching mail from server 'x'", fixe=fixe),
                      odoo("ERROR", "base", "odoo.addons.mail.models.fetchmail", "Failed to fetch mail", fixe=fixe),
                      odoo("WARNING", "base", "odoo.addons.base.models.ir_cron", "Job 'Autovacuum' (3) failed", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.mail.models.mail_mail", "Mail with ID 42 and Message-Id '<a@b>' successfully sent", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.base.models.ir_mail_server", "Mail delivery to 1 recipient", fixe=fixe),
                      odoo("INFO", "base", "odoo.addons.base.models.ir_actions_report", "The PDF report has been generated for model: sale.order, records [7].", fixe=fixe),
                      odoo("INFO", "base", "odoo.modules.loading", "Modules loaded.", fixe=fixe)])
        out = self.lancer("--hide-addons", "--no-presence", "--no-isp")[1]
        self.assertNotIn("(3) starting", out)                                                     # module noise: hidden
        self.assertNotIn("Websocket connection opened", out)
        self.assertNotIn("Fetching mail", out)
        self.assertIn("Failed to fetch mail", out)                                                # errors: never hidden
        self.assertIn("(3) failed", out)
        self.assertIn("successfully sent", out)                                                   # emails sent: kept
        self.assertIn("Mail delivery to 1 recipient", out)
        self.assertIn("The PDF report has been generated", out)                                   # generated file: kept
        self.assertIn("Modules loaded.", out)                                                     # outside odoo.addons.*: kept
        self.assertRegex(out, rf"INFO +{PERSONNE}\s+base werkzeug ")                              # requests: kept
        complete = self.lancer("--no-presence", "--no-isp")[1]                                      # sans l'option : tout
        self.assertIn("(3) starting", complete)
        self.assertIn("Websocket connection opened", complete)
        self.write("app-log-live.conf", "HIDE_ADDONS=oui\n")                                       # configuration key
        out = self.lancer("-c", os.path.join(self.d, "app-log-live.conf"), "--no-presence", "--no-isp")[1]
        self.assertNotIn("Websocket connection opened", out)
        self.assertIn("successfully sent", out)

    def test_couleurs_http_erreurs_et_connexions(self):
        flux = [werkzeug(PERSONNE, "/event", 200), werkzeug(DNS, "/x", 303), werkzeug(DNS, "/absent", 404), werkzeug(DNS, "/boum", 500),
                werkzeug(DNS, "/web/login", 200), werkzeug(DNS, "/web/session/logout", 303),
                odoo("ERROR", "base", "odoo.http", "Exception during request handling."),
                f"{ts()} odoo18 odoo[1]: Traceback (most recent call last):", f'{ts()} odoo18 odoo[1]:   File "/opt/odoo/x.py", line 1, in f',
                f"{ts()} odoo18 odoo[1]: ValueError: boom",
                odoo("INFO", "base", "odoo.service.server", "Redémarrage normal"),
                odoo("WARNING", "base", "odoo.modules.loading", "Un avertissement"),
                login(PERSONNE, "etienne@exemple.org"),
                odoo("INFO", "base", "odoo.addons.base.models.res_users", f"Login failed for db:base login:pirate@exemple.org from {DNS}")]
        self.journal(flux)
        text, _ = self.run_pty(["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--no-presence"], [], keep_ansi=True)
        orange = r"\x1b\[(?:33|38;5;208)m"
        self.assertIn('\x1b[32m200\x1b[0m    -  105', text)                              # 200 : vert
        self.assertIn('\x1b[36m303\x1b[0m    -  105', text)                              # 3xx : cyan
        self.assertIn('\x1b[31m404\x1b[0m    -  105', text)                              # 404 : rouge
        self.assertIn('\x1b[1;31m500\x1b[0m    -  105', text)                            # 5xx : rouge gras
        self.assertIn("\x1b[1;37;44m/web/login\x1b[0m", text)                       # page de connexion
        self.assertIn("\x1b[1;37;44m/web/session/logout\x1b[0m", text)
        self.assertIn("\x1b[1;31mERR\x1b[0m", text)                                # niveau
        self.assertRegex(text, orange + "WARN" + r"\x1b\[0m")
        self.assertIn("\x1b[1;31mTraceback (most recent call last):\x1b[0m", text)   # trace : lignes en rouge
        self.assertIn('\x1b[1;31m  File "/opt/odoo/x.py", line 1, in f\x1b[0m', text)
        self.assertIn("\x1b[1;31mValueError: boom\x1b[0m", text)
        self.assertNotIn("\x1b[1;31mRedémarrage normal", text)                       # the trace stops at the next entry
        self.assertIn("\x1b[1;37;44mLogin successful\x1b[0m", text)                  # successful login: identifier
        self.assertIn("\x1b[1;37;44mlogin:etienne@exemple.org\x1b[0m", text)
        self.assertRegex(text, r"\x1b\[1;(?:33|38;5;208)mLogin failed\x1b\[0m")      # failure: bold orange
        self.assertRegex(text, r"\x1b\[1;(?:33|38;5;208)mlogin:pirate@exemple.org\x1b\[0m")
        # Same stream in a pipe: no color code
        self.assertNotIn("\x1b[", self.lancer("--no-history", "--no-isp", "--no-presence")[1])

    def test_ip_gardee_par_defaut_hide_ip_et_libelle_court(self):
        self.journal([werkzeug(DNS)])
        out = self.lancer("--no-isp", "--no-presence")[1]                                        # 1.107 : par défaut, l'IP est masquée (le nom reste)
        self.assertRegex(out, r"INFO\s+base werkzeug srv\.exemple\.org\s+")
        self.assertNotIn(DNS, out)
        out = self.lancer("--no-isp", "--no-presence", "--hide-ip")[1]
        self.assertRegex(out, r"INFO\s+base werkzeug srv\.exemple\.org\s+")
        self.assertNotIn(DNS, out)
        out = self.lancer("--no-isp", "--no-presence", "--show-ip")[1]
        self.assertRegex(out, rf"INFO +{DNS}\s+base werkzeug srv\.exemple\.org\s+")
        rc, out, err = self.lancer("--no-isp", "--no-presence", "--keep-ip")                      # ancien nom de --show-ip : accepté, l'IP reste affichée
        self.assertEqual(rc, 0, err)
        self.assertIn(f"INFO    {DNS} ", out)
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        c = live.short_caption
        self.assertEqual(T(c("Étienne (cellulaire Vidéotron, adresse actuelle — peut changer)")), "Étienne (cellulaire Vidéotron, adresse actuelle)")
        self.assertEqual(T(c("Étienne (Bell)")), "Étienne (Bell)")
        self.assertEqual(T(c("Étienne (Tailscale : Proxmox1)")), "Étienne (Tailscale : Proxmox1)")
        self.assertEqual(T(c("Bureau — adresse fixe")), "Bureau")
        self.assertEqual(T(c("Étienne (adresse actuelle — peut changer")), "Étienne (adresse actuelle")

    def test_historique_illimite_et_50_lignes_par_defaut(self):
        self.lancer()
        with open(os.path.join(self.d, "journalctl.log")) as f:
            commands = f.read()
        histoire = [l for l in commands.splitlines() if " -g " in l][0]
        self.assertNotIn("--since", histoire, "par défaut : tout l'historique du journal")
        self.assertIn("--lines 50", commands)
        os.remove(os.path.join(self.d, "journalctl.log"))
        rc, out, err = self.lancer("--days", "30", "--lines", "50")
        with open(os.path.join(self.d, "journalctl.log")) as f:
            commands = f.read()
        self.assertIn("--since -30 days", [l for l in commands.splitlines() if " -g " in l][0])
        self.assertIn("--lines 50", commands)
        self.assertIn("lecture du journal (jusqu'à 3 minutes)", err)
        out = self.lancer()[2]
        self.assertIn("Historique des connexions (tout le journal)", out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--help"])
        aide = " ".join(out.split())                                   # argparse cuts lines: spaces normalized
        self.assertIn("(défaut : 50)", T(aide))
        self.assertIn("(défaut : 0 = tout l'historique du journal)", T(aide))

    # --- country, fast path, local server, reminder, non-serious errors ---
    def geoip(self):
        self.mock("geoiplookup", f'echo "$@" >> {self.d}/geoip.log; case "$1" in {DNS}) echo "GeoIP Country Edition: US, United States";; '
                                 f'{PERSONNE}|{ISP}) echo "GeoIP Country Edition: CA, Canada";; '
                                 '*) echo "GeoIP Country Edition: IP Address not found";; esac')

    def test_pays_de_l_adresse(self):
        """[5] Le pays suit l'adresse dans la colonne : « [adresse, CA] ». Base locale (geoiplookup) d'abord, sinon RDAP (le même appel que
        le fournisseur d'accès) ; aucun pays pour ce serveur, un réseau privé ou l'équipe ; --hide-ip : « [CA] »."""
        self.geoip()
        rc, out, err = self.lancer("--no-presence")
        lines = out.splitlines()
        self.assertRegex(T(lines[0]), rf"INFO CA {PERSONNE}\s+base werkzeug Étienne Dupont\s+")
        self.assertRegex(T(lines[1]), rf"INFO US {DNS}\s+base werkzeug srv\.exemple\.org\s+")
        self.assertRegex(T(lines[2]), rf"INFO CA {ISP}\s+base werkzeug Videotron Ltee \(org\)\s+")
        self.assertRegex(T(lines[3]), r"INFO +127\.0\.0\.1\s+base werkzeug ce serveur\s+")                  # pas de pays pour ce serveur
        self.assertRegex(T(lines[4]), rf"INFO +{self.equipe_ip}\s+base werkzeug Étienne")
        self.assertNotRegex(T(lines[4]), r"\[[^\]]*, [A-Z]{2}\]")                                # not for the team either
        with open(os.path.join(self.d, "geoip.log")) as f:
            self.assertNotIn("127.0.0.1", T(f.read()))
        out = self.lancer("--no-presence", "--hide-ip")[1].splitlines()
        self.assertRegex(out[0], r"INFO CA base werkzeug Étienne Dupont\s+")
        self.assertRegex(out[1], r"INFO US base werkzeug srv\.exemple\.org\s+")
        # Without local database: the country comes from RDAP only (a single request per address), never with --no-isp
        self.mock_exit("geoiplookup", 127)
        out = self.lancer("--no-presence")[1].splitlines()
        self.assertRegex(out[2], rf"INFO CA {ISP}\s+base werkzeug Videotron Ltee \(org\)\s+")
        self.assertRegex(out[1], rf"INFO +{DNS}\s+base werkzeug srv\.exemple\.org")           # DNS : RDAP indisponible, pas de pays
        out = self.lancer("--no-presence", "--no-isp")[1].splitlines()
        self.assertRegex(out[2], rf"INFO +{ISP}\s+base werkzeug {ISP}\s+")                    # sans nom ni pays : l'adresse reste aussi dans le texte
        self.assertNotRegex(out[2], r"\[[^\]]*, [A-Z]{2}\]")

    def test_adresse_locale_nomme_le_programme_jamais_une_personne(self):
        """[3] 127.0.0.1 n'est pas une personne (même si quelqu'un s'est « connecté » depuis le serveur, par un tunnel) : les sondes
        d'app-health-check.py sont nommées ; une autre requête locale reste « ce serveur »."""
        self.write("history.txt", "\n".join([histo("127.0.0.1", "etienne@exemple.org"), histo("127.0.0.1", "alice@exemple.org"),
                                              histo(PERSONNE, "etienne@exemple.org")]) + "\n")
        def local(url, methode="GET", code=200):
            return odoo("INFO", "base", "werkzeug", f'127.0.0.1 - - [02/Oct/2026 12:20:52] "{methode} {url} HTTP/1.1" {code} - 10 0.010 0.015')
        self.journal([local("/", code=303), local("/web/webclient/version_info", "POST"), local("/web/health?db_server_status=1"),
                      local("/web/assets/1/x.js"), werkzeug(PERSONNE)])
        rc, out, err = self.lancer("--no-presence")
        l = out.splitlines()
        self.assertRegex(T(l[0]), r'INFO +127\.0\.0\.1\s+base werkzeug app-health-check\.py\s+H1\.1 303[ \d.-]*GET  /')
        self.assertRegex(T(l[1]), r'127\.0\.0\.1\s+base werkzeug app-health-check\.py\s+H1\.1 \d+[ \d.-]*POST /web/webclient/version_info')
        self.assertRegex(T(l[2]), r'127\.0\.0\.1\s+base werkzeug app-health-check\.py\s+H1\.1 \d+[ \d.-]*GET  /web/health\?db_server_status=1')
        self.assertRegex(T(l[3]), r'127\.0\.0\.1\s+base werkzeug ce serveur\s+H1\.1 \d+[ \d.-]*GET  /web/assets/1/x\.js')
        self.assertNotIn("Étienne", T("\n".join(l[:4])))
        self.assertNotIn("autres comptes", out)
        self.assertRegex(T(l[4]), rf"{PERSONNE}\s+base werkzeug Étienne Dupont")                  # une vraie personne reste une personne

    def test_le_nom_apparait_meme_quand_les_recherches_lentes_sont_saturees(self):
        """[5] Cause du nom absent après une connexion : les threads de recherche, tous retenus par des DNS lents, n'avaient plus de
        place pour le nom de la personne. Voie rapide : le nom ne dépend d'aucune recherche lente."""
        lents = [f"8.8.8.{i}" for i in range(1, 9)]
        self.mock("getent", 'case "$2" in 8.8.8.*) sleep 2; exit 2;; esac; exit 2')
        self.write("history.txt", "")
        self.journal([werkzeug(ip, "/lent", delta=10) for ip in lents]
                     + [login(AUTRE, "alice@exemple.org", delta=5), werkzeug(AUTRE, "/apres", delta=4)])
        start = time.time()
        rc, out, err = self.lancer("--no-history", "--no-isp", "--no-presence", env_extra={"APP_LOG_LIVE_WAIT": "0.3"})
        lines = out.splitlines()
        self.assertRegex(lines[8], r"11\.101\.16\.52\s+base odoo\.addons\.base\.models\.res_users\s+Login successful for db:base login:alice@exemple\.org from Alice A")
        self.assertRegex(T(lines[9]), r'11\.101\.16\.52\s+base werkzeug Alice A\s+H1\.1 \d+[ \d.-]*GET  /apres')           # le nom, pas l'adresse seule
        self.assertLess(time.time() - start, 5, "le flux a attendu les recherches lentes")

    def test_rappel_des_lignes_d_un_visiteur_devenu_connu(self):
        """[5] Quelqu'un se connecte : ses lignes des 2 dernières minutes, affichées plus haut sans nom, sont ré-affichées avec son
        nom (sans relancer journalctl) ; une ligne plus ancienne que --recap ne l'est pas ; --recap 0 : jamais."""
        self.write("history.txt", "")
        flux = [werkzeug(AUTRE, "/trop-ancien", delta=300), werkzeug(AUTRE, "/page-1", delta=50), werkzeug(DNS, "/autre-visiteur", delta=45),
                werkzeug(AUTRE, "/page-2", delta=40), login(AUTRE, "alice@exemple.org", delta=30), werkzeug(AUTRE, "/apres", delta=20)]
        self.journal(flux)
        rc, out, err = self.lancer("--no-history", "--no-isp", "--no-presence", "--recap", "120")
        self.assertIn(f"↻ Alice A [{AUTRE}] : 2 lignes précédentes de cette adresse (depuis ", out)
        reminder = out.split("↻")[1]
        self.assertRegex(T(reminder), r'11\.101\.16\.52\s+base werkzeug Alice A\s+H1\.1 \d+[ \d.-]*GET  /page-1')
        self.assertRegex(T(reminder), r'11\.101\.16\.52\s+base werkzeug Alice A\s+H1\.1 \d+[ \d.-]*GET  /page-2')
        self.assertNotIn("/trop-ancien", T(reminder))                                             # outside the window
        self.assertNotIn("/autre-visiteur", T(reminder))                                          # autre adresse
        self.assertEqual(out.count("↻"), 1)
        self.assertEqual(self.lancer("--no-history", "--no-isp", "--no-presence", "--recap", "0")[1].count("↻"), 0)
        # The lines of the first part stayed without a name (the address was not known at the time)
        premieres = out.split("↻")[0]
        self.assertRegex(T(premieres), r'11\.101\.16\.52\s+base werkzeug 11\.101\.16\.52\s+H1\.1 \d+[ \d.-]*GET  /page-1')

    def test_conflit_de_mise_a_jour_simultanee_en_orange_pas_en_rouge(self):
        """[7][8] « ERROR odoo.sql_db: bad query » suivi de « could not serialize access » : Odoo réessaie tout seul (SERIALIZATION_FAILURE,
        N tries left). Orange avec sa raison — pas le rouge d'une vraie erreur. Une autre cause (syntaxe) reste en rouge."""
        sql = odoo("ERROR", "base", "odoo.sql_db", "bad query: b' UPDATE \"discuss_channel_member\" SET \"fold_state\" = 1'")
        self.journal([sql, f"{ts()} odoo18 odoo[1]: ERROR: could not serialize access due to concurrent update", f"{ts()} odoo18 odoo[1]:",
                      odoo("INFO", "base", "odoo.service.model", "SERIALIZATION_FAILURE, 4 tries left, try again in 0.17 sec..."),
                      sql, f"{ts()} odoo18 odoo[1]: ERROR: syntax error at or near \"SET\"",
                      odoo("INFO", "base", "odoo.service.model", "suite")])
        text, _ = self.run_pty(["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--no-presence"], [], keep_ansi=True)
        orange = r"\x1b\[(?:33|38;5;208)m"
        lines = [l for l in text.splitlines() if "bad query" in l]
        self.assertEqual(len(lines), 2, text)
        self.assertRegex(lines[0], orange + "ERR" + r"\x1b\[0m")                            # non-serious: orange
        self.assertNotIn("\x1b[1;31mERROR", T(lines[0]))
        self.assertIn("(conflit de mise à jour simultanée : Odoo réessaie automatiquement)", T(lines[0]))
        self.assertIn("\x1b[1;31mERR\x1b[0m", T(lines[1]))                                     # vraie erreur : rouge
        self.assertNotIn("conflit de mise à jour simultanée", T(lines[1]))
        self.assertRegex(text, orange + "ERROR: could not serialize access due to concurrent update")   # la cause aussi
        # A "bad query" line last (stream finished) is still written, in red
        self.journal([sql])
        out = self.lancer("--no-history", "--no-isp", "--no-presence")[1]
        self.assertIn("bad query", out)
        self.assertNotIn("conflit de mise à jour simultanée", out)

    def test_conflits_reessayes_et_echecs_definitifs_comptes_a_part_des_erreurs(self):
        """1.53 : « SERIALIZATION_FAILURE, N tries left » = conflit réessayé (sans gravité) ; « …, maximum number of tries reached! » = échec définitif. Deux compteurs à part,
        par code PostgreSQL ; les « bad query » d'un conflit réessayé ne comptent PLUS comme erreurs d'Odoo ; compté même si la ligne est masquée (--min)."""
        live = self.module_live()
        st = live.Stats(5.0)
        for text in ("SERIALIZATION_FAILURE, 4 tries left, try again in 0.13 sec...", "SERIALIZATION_FAILURE, 3 tries left, try again in 1.18 sec...",
                      "DEADLOCK_DETECTED, 4 tries left, try again in 0.20 sec...", "SERIALIZATION_FAILURE, maximum number of tries reached!", "autre message sans rapport"):
            L = live.Line(odoo("INFO", "base", "odoo.service.model", text))
            st.count_conflict(L)
            st.ajouter(L, {}, None)
        sql = live.Line(odoo("ERROR", "base", "odoo.sql_db", "bad query: b' UPDATE \"discuss_channel_member\" SET x = 1'"))
        st.ajouter(sql, {}, None, True)                                                     # retried conflict: not an error
        vraie = live.Line(odoo("ERROR", "base", "odoo.sql_db", "bad query: b' SELEKT 1'"))
        st.ajouter(vraie, {}, None, False)                                                  # real error: counted
        self.assertEqual((st.conflicts, st.final_failures), (3, 1))
        self.assertEqual(dict(st.conflict_codes), {"SERIALIZATION_FAILURE": 2, "DEADLOCK_DETECTED": 1})
        self.assertEqual(dict(st.failure_codes), {"SERIALIZATION_FAILURE": 1})
        self.assertEqual(sum(v for k, v in st.odoo_errors.items() if k[0] == "ERROR"), 1)
        level, lines = st.health()
        t = "\n".join(lines)
        self.assertIn("Échecs définitifs de mise à jour simultanée : 1", T(t))
        self.assertIn("Odoo a abandonné après 5 essais", T(t))
        self.assertIn("Conflits de mise à jour réessayés (sans gravité) : 3", T(t))
        self.assertGreaterEqual(level, 1)                                                  # a final failure: to look at
        # Difference between two displays
        before = st.snapshot()
        st.count_conflict(live.Line(odoo("INFO", "base", "odoo.service.model", "SERIALIZATION_FAILURE, 4 tries left, try again in 0.1 sec...")))
        d = st.since(before)
        self.assertEqual((d.conflicts, d.final_failures), (1, 0))
        self.assertEqual(dict(d.conflict_codes), {"SERIALIZATION_FAILURE": 1})
        # Only retried conflicts (no failure): green "none" indicator for failures
        propre = live.Stats(5.0)
        propre.count_conflict(live.Line(odoo("INFO", "base", "odoo.service.model", "SERIALIZATION_FAILURE, 4 tries left, try again in 0.1 sec...")))
        self.assertIn("Échecs définitifs de mise à jour simultanée : aucun", T("\n".join(propre.health()[1])))

    def test_requetes_par_nom_dns_seulement_identifies_et_difference_ctrl_t(self):
        """1.104 : « Requests by name (DNS column) » du sommaire (Ctrl-T compris) : requêtes par nom affiché ; une adresse sans nom n'est jamais comptée comme nom,
        elle est comptée à part ; la différence entre deux affichages ne reprend que les nouvelles requêtes."""
        live = self.module_live()
        st = live.Stats(5.0)

        def acc(ip):
            return live.Line(f'{ip} - - [23/Oct/2026:10:00:00 -0400] "GET /web/login HTTP/1.1" 200 1234 "-" "Mozilla/5.0"')

        renderings = {"198.51.100.7": ("odoo.exemple.ca", [], False, None), "198.51.100.8": ("198.51.100.8", [], True, None)}
        for ip in ["198.51.100.7"] * 3 + ["198.51.100.8"] * 2 + ["198.51.100.9"]:        # 9 : pas de rendu, donc sans nom
            st.ajouter(acc(ip), renderings, None)
        self.assertEqual(dict(st.by_name), {"odoo.exemple.ca": 3})
        self.assertEqual(st.requests, 6)
        lignes = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", x) for x in st.summary(level=5))
        self.assertIn("Requests by name (DNS column): 3 identified, 3 by address only", lignes)
        self.assertIn("odoo.exemple.ca ×3", lignes)
        self.assertNotIn("      198.51.100.8 ×", lignes)                    # the bare address is never a line of the name block
        self.assertIn("Requêtes par nom (colonne DNS) : 3 identifiées, 3 seulement par adresse", T("Requests by name (DNS column): 3 identified, 3 by address only"))
        before = st.snapshot()
        st.ajouter(acc("198.51.100.7"), renderings, None)
        d = st.since(before)
        self.assertEqual(dict(d.by_name), {"odoo.exemple.ca": 1})
        self.assertEqual(d.requests, 1)

    def test_conflits_comptes_de_bout_en_bout_dans_le_resume(self):
        """1.53 : de bout en bout : le résumé de santé compte les conflits réessayés et l'échec définitif."""
        self.journal([odoo("INFO", "base", "odoo.service.model", "SERIALIZATION_FAILURE, 4 tries left, try again in 0.13 sec..."),
                      odoo("INFO", "base", "odoo.service.model", "SERIALIZATION_FAILURE, 3 tries left, try again in 1.18 sec..."),
                      odoo("INFO", "base", "odoo.service.model", "SERIALIZATION_FAILURE, maximum number of tries reached!")])
        rc, out, err = self.lancer("--no-history", "--no-isp", "--no-presence", "--min", "--summary")
        self.assertIn("Échecs définitifs de mise à jour simultanée : 1", out + err)
        self.assertIn("Conflits de mise à jour réessayés (sans gravité) : 2", out + err)

    def test_recherche_de_l_ip_externe_ne_retient_pas_l_affichage(self):
        """1.59 : « curl ifconfig.me » (jusqu'à 10 s) bloquait la boucle d'affichage : les lignes arrivaient d'un coup, en retard. La recherche se fait dans un fil à part."""
        import subprocess
        import time
        text_line = lambda n: f'2026-10-13T21:40:0{n}.000000-04:00 h odoo[1]: 2026-10-13 21:40:0{n},123 7 INFO base werkzeug: 127.0.0.1 - - [13/Oct/2026 21:40:0{n}] "GET /web/x{n} HTTP/1.1" 200 - 3 0.01 0.02'
        self.mock("journalctl", f'case "$*" in *" -g "*) exit 0;; esac; echo \'{text_line(1)}\'; sleep 2; echo \'{text_line(2)}\'; sleep 1')
        self.mock("curl", '[[ "$*" == *ifconfig.me* ]] && { sleep 7; echo 203.0.113.9; exit 0; }; exit 22')
        env = dict(self.env, APP_LOG_LIVE_WAIT="0.2", APP_LOG_LIVE_STATE_DIR=os.path.dirname(self.path("etat-ip2", "x")))
        start = time.time()
        proc = subprocess.Popen(["python3", "-u", self.prog, "--lines", "0", "--no-presence"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        vue = {}
        for l in proc.stdout:
            for n in (1, 2):
                if f"/web/x{n}" in l and n not in vue:
                    vue[n] = time.time() - start
        proc.wait(timeout=60)
        self.assertEqual(sorted(vue), [1, 2], vue)
        self.assertLess(vue[2], 6.0, f"la ligne 2 est arrivée trop tard (la recherche de l'IP externe retient l'affichage) : {vue}")

    def test_chien_de_garde_signale_un_fil_de_lecture_bloque_avec_sa_pile(self):
        """1.60 : si le journal a des lignes prêtes et que le fil de lecture ne les prend pas, UNE alerte avec la pile du fil ; pas d'alerte quand tout avance."""
        import queue
        import subprocess
        import threading
        import time
        live = self.module_live()
        messages = []
        proc = subprocess.Popen(["bash", "-c", "echo une ligne; sleep 30"], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.kill)
        bloque = threading.Event()

        def lecteur_bloque():
            bloque.wait(30)                                   # ne lit jamais proc.stdout
        thread = threading.Thread(target=lecteur_bloque, daemon=True, name="reader")
        thread.start()
        self.addCleanup(bloque.set)
        time.sleep(0.3)
        with unittest.mock.patch.object(live, "WATCHDOG_DELAY", 2.0), unittest.mock.patch.object(live, "eprint", lambda *a, **k: messages.append(" ".join(map(str, a)))):
            live.start_watchdog(proc, queue.Queue(), {"read_files": 0}, [0], thread)
            time.sleep(5)
        text = "\n".join(messages)
        self.assertEqual(T(text).count("Chien de garde"), 1, text)
        self.assertIn("le fil de lecture ne les prend pas", T(text))
        self.assertIn("lecteur_bloque", T(text))                # the stack of the blocked thread

    def test_chien_de_garde_se_tait_pendant_une_question_a_l_utilisateur(self):
        """1.64 : bannissement / enquête / menu : la boucle attend EXPRÈS une réponse (« Confirmer le bannissement ? [o/N] ») ; aucune fausse alerte."""
        import queue
        import subprocess
        import threading
        import time
        live = self.module_live()
        messages = []
        proc = subprocess.Popen(["bash", "-c", "echo une ligne; sleep 30"], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.kill)
        bloque = threading.Event()
        thread = threading.Thread(target=lambda: bloque.wait(30), daemon=True, name="reader")
        thread.start()
        self.addCleanup(bloque.set)
        time.sleep(0.3)
        with unittest.mock.patch.object(live, "WATCHDOG_DELAY", 2.0), unittest.mock.patch.object(live, "eprint", lambda *a, **k: messages.append(" ".join(map(str, a)))):
            with live.interaction():
                live.start_watchdog(proc, queue.Queue(), {"read_files": 0}, [0], thread)
                time.sleep(4.5)
                self.assertEqual(live.INTERACTIVE[0], 1)
        self.assertEqual(messages, [])
        self.assertEqual(live.INTERACTIVE[0], 0)

    def test_service_arrete_avertit_au_lieu_de_sembler_fige(self):
        """1.61 : le service suivi est arrêté (Odoo lancé à la main) : plus aucune ligne n'arrive ; UNE alerte le dit, nomme l'Odoo qui tourne ailleurs et la marche à suivre."""
        import subprocess
        self.mock("journalctl", 'case "$*" in *" -g "*) exit 0;; esac; sleep 6')
        self.mock("systemctl", 'case "$1" in is-active) echo inactive; exit 3;; esac; case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        self.mock("pgrep", 'echo "123 python3 ./odoo18.0/odoo/odoo-bin -c ./config.conf"')
        env = dict(self.env, APP_LOG_LIVE_SERVICE_WAIT="1")
        r = subprocess.run(["python3", self.prog, "--lines", "0", "--no-presence", "--no-isp"], capture_output=True, text=True, env=env, timeout=60)
        out = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        self.assertEqual(out.count("est « inactive »"), 1, out)
        self.assertIn("Odoo tourne pourtant hors de ce service", T(out))
        self.assertIn("odoo-bin -c ./config.conf", T(out))
        self.assertIn("logfile", T(out))

    def test_surlignage_des_mots_en_cyan(self):
        """1.58 : --highlight / HIGHLIGHT / touche l. Mots surlignés (noir sur fond cyan) sans casser les couleurs de la ligne ; POST (tout en majuscules) sensible à la casse ; rien sans couleur."""
        live = self.module_live()
        self.assertEqual(live.read_highlight(None), ["POST", "webclient", "discuss", "avatar", "20-ans", "21-ans", "portes", "ouvertes", "-2026-"])      # 1.88: "-2026-"
        self.assertEqual(live.read_highlight("webclient,-2026-"), ["webclient", "-2026-"])          # 1.88: "-2026-" is a WORD (start AND end "-"), not "remove 2026-"
        self.assertNotIn("-2026-", live.read_highlight("--2026-"))                                  # "--2026-" removes it
        self.assertEqual(live.read_highlight(" a , b,,"), ["a", "b"])
        self.assertEqual(live.read_highlight("none"), [])
        self.assertEqual(live.read_highlight(""), [])
        pattern = live.highlight_pattern(live.read_highlight(None))
        cy = "\x1b[" + live.STYLES["highlight"] + "m"
        with unittest.mock.patch.object(live, "COLOR", True):
            self.assertEqual(T(live.highlight_text('"POST /web/webclient/x HTTP"', pattern)), f'"{cy}POST\x1b[0m /web/{cy}webclient\x1b[0m/x HTTP"')
            self.assertEqual(T(live.highlight_text("postgres Discuss.channel journee-PORTES-ouvertes", pattern)),
                             f"postgres {cy}Discuss\x1b[0m.channel journee-{cy}PORTES\x1b[0m-{cy}ouvertes\x1b[0m")       # "postgres": not POST; free case for the others
            # existing colors: restored after the word, never overwritten
            self.assertEqual(T(live.highlight_text("\x1b[1;32mhello avatar bye\x1b[0m fin", pattern)), f"\x1b[1;32mhello {cy}avatar\x1b[0m\x1b[1;32m bye\x1b[0m fin")
            self.assertEqual(T(live.highlight_text("x", None)), "x")
        with unittest.mock.patch.object(live, "COLOR", False):
            self.assertEqual(T(live.highlight_text("POST avatar", pattern)), "POST avatar")                                  # pipe: text unchanged

    def test_surlignage_ajouter_et_enlever_avec_plus_et_moins(self):
        """1.67 : « +mot » ajoute, « -mot » enlève (casse indifférente) ; sans signe : la liste complète remplace ; ligne de commande : relatif à la liste par défaut."""
        live = self.module_live()
        database = ["POST", "webclient", "20-ans"]
        self.assertEqual(live.read_highlight("+odoo", database), ["POST", "webclient", "20-ans", "odoo"])
        self.assertEqual(live.read_highlight("-post -WEBCLIENT", database), ["20-ans"])
        self.assertEqual(live.read_highlight("+a,+b -20-ans", database), ["POST", "webclient", "a", "b"])
        self.assertEqual(live.read_highlight("+webclient", database), database)                                  # already present: no duplicate
        self.assertEqual(live.read_highlight("c, d", database), ["c", "d"])                                  # sans signe : remplace
        self.assertEqual(live.read_highlight("20-ans,x", database), ["20-ans", "x"])                          # "20-ans" does not start with "-"
        self.assertEqual(live.read_highlight("none", database), [])
        self.assertEqual(live.read_highlight("-inconnu", database), database)
        default_value = live.read_highlight(None)
        self.assertEqual(live.read_highlight("+odoo,-POST"), [m for m in default_value if m != "POST"] + ["odoo"])
        self.assertIsNone(live.modify_highlight(database, "a,b"))
        self.assertIsNone(live.modify_highlight(database, "-"))

    def test_surlignage_cle_de_configuration_et_ligne_de_commande(self):
        """1.58 : HIGHLIGHT dans le fichier de configuration, --highlight prioritaire ; sans couleur dans un tube, le texte est inchangé."""
        self.write("cfg.conf", "HIGHLIGHT=zzz\n")
        rc, out, err = self.lancer("--no-presence", "--highlight", "werkzeug,none", "--config", self.path("cfg.conf"))
        self.assertEqual(rc, 0, err)
        self.assertNotIn("\x1b[", out)
        self.assertIn("--highlight", self.run_cmd(["python3", self.prog, "--help"])[1])

    def test_masquage_des_secrets_reste_rapide_sur_les_longues_lignes(self):
        """1.57 : le masquage (1.54) prenait des secondes puis des minutes sur une longue ligne de mots_separes_par_des_soulignes : l'affichage en direct s'arrêtait. Temps linéaire exigé."""
        import time
        live = self.module_live()
        for text in ("ab_" * 100000 + "= x", "token_" * 50000 + "x", "a_token" * 50000, '"a_' * 50000 + "token", '"token": "' * 30000, "x" * 500000 + "=1"):
            start = time.time()
            live.mask_secrets(text)
            self.assertLess(time.time() - start, 2.0, text[:30])
        self.assertEqual(T(live.mask_secrets('{"access_token": "abc", "token_type": "Bearer"} x?refresh_token=zz&a=1 Bearer abcdefgh123')),
                         '{"access_token": "***", "token_type": "Bearer"} x?refresh_token=***&a=1 Bearer ***')

    def test_secrets_masques_a_l_affichage(self):
        """1.54 : la VALEUR de access_token=, token=, password=, … (URL, formulaire, JSON / dict Python, Bearer) est remplacée par *** à l'affichage, dans les statistiques
        et partout ailleurs ; « token_type=Bearer » n'est pas un secret ; le journal d'Odoo n'est pas modifié."""
        live = self.module_live()
        case = {
            "GET /auth_oauth/signin?state=x&access_token=ya29.SECRET_TOKEN-abc&token_type=Bearer&expires_in=3599": "access_token=***&token_type=Bearer&expires_in=3599",
            "POST /web/login?login=a@exemple.org&password=Sup3rSecret&redirect=/web": "password=***&redirect=/web",
            "GET /web/reset_password?token=AbCd1234&db=x": "token=***&db=x",
            "values: {'password': 'abc123', 'login': 'x', 'signup_token': 'zzz'}": "{'password': '***', 'login': 'x', 'signup_token': '***'}",
            "Authorization: Bearer eyJhbGciOi.payload.signature": "Authorization: Bearer ***",
        }
        for raw, attendu in case.items():
            output = live.mask_secrets(raw)
            self.assertIn(attendu, output)
            for secret in ("SECRET_TOKEN", "Sup3rSecret", "AbCd1234", "abc123", "zzz", "eyJhbGciOi"):
                self.assertNotIn(secret, output)
        self.assertEqual(T(live.mask_secrets("GET /event/a=b?x=1")), "GET /event/a=b?x=1")          # nothing to hide: unchanged
        L = live.Line(werkzeug("8.8.8.8", "/auth_oauth/signin?access_token=ya29.SECRET_TOKEN-abc&token_type=Bearer"))
        self.assertNotIn("SECRET_TOKEN", T(L.text + L.raw_line))
        st = live.Stats(5.0)
        L.instant = time.time()
        st.ajouter(L, {"8.8.8.8": ("ok.exemple.org", [], False, None)}, None)
        self.assertNotIn("SECRET_TOKEN", T(" ".join(st.summary([], (), "Test", 9)) + repr(dict(st.urls))))
        self.journal([werkzeug("8.8.8.8", "/auth_oauth/signin?access_token=ya29.SECRET_TOKEN-abc&token_type=Bearer&password=hunter2xx")])
        rc, out, err = self.lancer("--no-history", "--no-isp", "--no-presence")
        self.assertNotIn("SECRET_TOKEN", out + err)
        self.assertNotIn("hunter2xx", out + err)
        self.assertIn("access_token=***&token_type=Bearer&password=***", out)

    # --- presence ---
    def test_resume_de_presence_apres_l_historique(self):
        """Qui est encore connecté ? Connecté (activité récente), inactif (plus d'activité), déconnecté (/web/session/logout)."""
        self.write("history.txt", "\n".join([histo(PERSONNE, "alice@exemple.org"), histo(AUTRE, "bob@exemple.org"),
                                              histo(TROISIEME, "carl@exemple.org")]) + "\n")
        self.journal([werkzeug(AUTRE, "/ancien", delta=2400),
                      werkzeug(TROISIEME, "/page", delta=3000), werkzeug(TROISIEME, "/web/session/logout", code=303, delta=2900),
                      werkzeug(PERSONNE, "/event", delta=150), werkzeug(DNS, "/anonyme", delta=100)])
        rc, out, err = self.lancer()
        summary = out.split("Présence d'après les 5 derniers messages")[1]
        self.assertIn("(inactif après 15 min ; dernière activité la plus récente en premier)", T(summary))
        # [8] IN COLUMNS (state, name, address, date and time of last activity, detail): all lines have the columns at the same positions
        columns = [l for l in summary.splitlines() if l.startswith("  ") and ("●" in l or "○" in l or "✕" in l or "État" in l)]
        self.assertEqual(len(columns), 4, summary)
        self.assertEqual(T(" ".join(columns[0].split())), "État Nom Adresse Dernière activité Détail")
        self.assertEqual(len({l.index("Alice A" if "Alice A" in l else "Bob B" if "Bob B" in l else "Carl C" if "Carl C" in l else "Nom") for l in columns}), 1,
                         "la colonne des noms est alignée")
        self.assertEqual(len({l.index("[") for l in columns[1:]}), 1, "la colonne des adresses est alignée")
        r = " ".join(summary.split())
        self.assertRegex(T(r), rf"● connecté\(e\) Alice A \[{PERSONNE}\] \d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d il y a 2 min · 1 requêtes vues")
        self.assertRegex(T(r), rf"○ inactif\(ve\) Bob B \[{AUTRE}\] \d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d depuis 40 min")
        self.assertRegex(T(r), rf"✕ déconnecté\(e\) Carl C \[{TROISIEME}\] \d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d à la déconnexion")
        self.assertNotIn("anonyme", T(summary))                                    # visiteur non reconnu : pas une personne
        # Aucun suivi avec --no-presence
        out = self.lancer("--no-presence")[1]
        self.assertNotIn("Présence", out)
        self.assertNotIn("●", out)

    def test_evenements_connexion_et_deconnexion_dans_le_flux(self):
        self.write("history.txt", "")
        self.journal([login(AUTRE, "alice@exemple.org", delta=60), werkzeug(AUTRE, "/event", delta=30),
                      werkzeug(AUTRE, "/web/session/logout", code=303, delta=5)])
        rc, out, err = self.lancer("--no-history", "--no-presence".replace("--no-presence", "--no-isp"))
        lines = out.splitlines()
        self.assertIn("Login successful for db:base login:alice@exemple.org from Alice A", lines[0])
        self.assertRegex(T(lines[1]), rf"^● \d\d:\d\d:\d\d Alice A \[{AUTRE}\] vient de se connecter$")
        self.assertIn("werkzeug Alice A", T(lines[2]))
        self.assertIn("/event", T(lines[2]))
        self.assertRegex(T(lines[4]), rf"^✕ \d\d:\d\d:\d\d Alice A \[{AUTRE}\] s'est déconnecté\(e\) \(/web/session/logout\)$")
        self.assertRegex(out.split("Présence d'après")[1], r"✕ déconnecté\(e\)\s+Alice A")

    def test_heure_des_evenements_reprise_de_la_ligne_du_journal(self):
        """L'heure d'un événement de présence est celle de la ligne qu'il commente (10:07:18), pas l'heure recalculée avec le fuseau
        de la machine (le journal est en -0400 ici, la machine d'essai en UTC : 14:07:18)."""
        t0 = datetime.datetime(2026, 10, 2, 10, 7, 18, 326421, FUSEAU)
        self.journal([login(AUTRE, "alice@exemple.org", fixe=t0),
                      werkzeug(AUTRE, "/web/session/logout", code=303, fixe=t0 + datetime.timedelta(minutes=2))])
        out = self.lancer("--no-history", "--no-isp")[1]
        self.assertIn(f"● 10:07:18 Alice A [{AUTRE}] vient de se connecter", out)
        self.assertIn(f"✕ 10:09:18 Alice A [{AUTRE}] s'est déconnecté(e) (/web/session/logout)", out)
        self.assertIn(f"✕ déconnecté(e) Alice A [{AUTRE}] 2026-10-02 10:09:18", " ".join(out.split()))   # the summary too, with the DATE
        self.assertNotIn("14:07", out)

    def test_plus_d_activite_en_direct_puis_retour(self):
        """Flux au repos : « plus d'activité depuis N s/min » ; une nouvelle requête : « de retour »."""
        self.write("history.txt", histo(PERSONNE, "alice@exemple.org") + "\n")
        self.journal([werkzeug(PERSONNE, "/event", delta=0)], after="sleep 6")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--idle", "0.04", "--lines", "1"])        # 2.4 s of inactivity (0.6 s: too short when the machine is loaded)
        self.assertRegex(T(out), r"● connecté\(e\)\s+Alice A")                                                          # summary: connected
        self.assertRegex(T(out), rf"○ \d\d:\d\d:\d\d Alice A \[{PERSONNE}\] : plus d'activité depuis \d+ s \(session peut-être encore valide\)")
        self.assertEqual(out.count("plus d'activité"), 1, "un seul événement par période d'inactivité")
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        p = live.Presence(15)
        account = ("base", "alice@exemple.org")
        self.assertEqual(p.activity(account, "Alice A", PERSONNE, 1000), [])
        event = p.check(1000 + 16 * 60)
        self.assertEqual(len(event), 1)
        self.assertIn("plus d'activité depuis 16 min", T(event[0][1]))
        self.assertEqual(p.check(1000 + 17 * 60), [], "pas de répétition")
        retour = p.activity(account, "Alice A", PERSONNE, 1000 + 20 * 60)
        self.assertEqual(len(retour), 1)
        self.assertIn("de retour après 20 min d'inactivité", T(retour[0][1]))
        self.assertEqual(p.activity(account, "Alice A", PERSONNE, 1000 + 21 * 60), [])
        # After a disconnection, inactivity is no longer reported
        p.activity(account, "Alice A", PERSONNE, 1000 + 22 * 60, logout=True)
        self.assertEqual(p.check(1000 + 99 * 60), [])

    def test_un_espace_avant_http_meme_si_le_nom_remplit_sa_colonne(self):
        """1.27 : « 127.0.0.1  ce server<espaces>H1.1 200 » — jamais « ce serverH1.1 » : au moins un espace avant HTTP."""
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        f = live.Formatting()
        colle = f.aligned_request('127.0.0.1 ce server"GET  /a HTTP/1.1" 200 - 13 0.006 0.066', [])
        self.assertIn("ce server H1.1 200", T(colle))
        normal = f.aligned_request('127.0.0.1 ce server   "GET  /a HTTP/1.1" 200 - 13 0.006 0.066', [])
        self.assertIn("ce server   H1.1 200", T(normal))                       # existing spaces: no space added

    def test_tableau_de_bord_entierement_traduit_en_anglais(self):
        """1.27 : le tableau de bord (Ctrl-G / Ctrl-C) en anglais ne mélange plus les langues (« Sondes de this server », « Vrais visiteurs », « Erreurs 4xx »…)."""
        spec = importlib.util.spec_from_file_location("i18n", script_path("apps/_i18n.py"))
        i18n = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(i18n)
        tr = i18n.traducteur("fr", SCRIPTS_DIR, "app-log-live", ("_bbb", "nginx-log-audit"))
        lines = ["  ✔ HTTP 5xx errors: none", "  ⚠ Odoo errors (ERROR / CRITICAL): 2", "  ✔ Program: normal resources",
                  "  Robots: 338 address(es) out of 1624", "  Real visitors: 1286 out of 1624 (79 %)", "  Site visits: 1712 visits · 3306 pages viewed · 1624 visitors [2 known persons]",
                  "  Banned addresses seen: 0.", "  Activity: 120 requests", "  Level 5 of 9", "  HTTP codes: 1xx 1 % · 2xx 57 %",
                  "  Pages by language (3306 pages): without prefix 45 %"]
        anglais = re.compile(r"(?i:\b(none|visitors?|banned|activity|level|language|real|visits?|efficiency|resources|out of|without)\b)|\berrors\b")
        for l in lines:
            with self.subTest(text_line=l):
                self.assertIsNone(anglais.search(tr(l)), tr(l))

    # --- reste du comportement -------------------------------------------------------------------------------------
    def test_lieu_partage_nomme_le_lieu_et_jamais_une_personne(self):
        """Une adresse d'un lieu [partagée] (université…) : le LIEU remplace « Étienne +3 autre(s) compte(s) » — même si des comptes s'y sont
        connectés ; aucun événement de présence ni rappel pour une adresse partagée. Un lieu non partagé passe après la personne et la
        liste blanche. Le lieu le plus précis gagne ; les deux fichiers de lieux comptent."""
        ets = "11.105.216.7"
        self.write("history.txt", "\n".join([histo(ets, "etienne@exemple.org"), histo(ets, "alice@exemple.org"), histo(ets, "bob@exemple.org"),
                                              histo("11.105.1.1", "carl@exemple.org"), histo("11.101.16.52", "alice@exemple.org")]) + "\n")
        self.lieux("11.105.0.0/16        # ETS - Université   [partagée]\n"
                   "11.105.216.0/24      # ETS - Laboratoire   [partagée]\n"
                   "11.101.16.0/24        # Quartier Rosemont\n"
                   f"{self.equipe_ip}     # Autre libellé de la liste blanche\n")
        self.journal([werkzeug(ets, "/event"), werkzeug("11.105.1.1", "/web/login"), werkzeug("11.101.16.52", "/odoo"),
                      werkzeug(self.equipe_ip, "/team"), werkzeug(DNS, "/dns")])
        rc, out, err = self.lancer()
        l = out.splitlines()
        self.assertRegex(T(l[0]), rf'INFO +{ets}\s+base werkzeug ETS - Laboratoire\s+H1\.1 \d+[ \d.-]*GET  /event')        # most precise range
        self.assertRegex(T(l[1]), r'INFO +11\.105\.1\.1\s+base werkzeug ETS - Université\s+H1\.1 \d+[ \d.-]*GET  /web/login')
        self.assertRegex(T(l[2]), r'INFO +11\.101\.16\.52\s+base werkzeug Alice A \| Quartier Rosemont\s+H1\.1 \d+[ \d.-]*GET  /odoo')         # non-shared place: the person AND the place
        self.assertRegex(T(l[3]), rf'INFO +{self.equipe_ip}\s+base werkzeug Étienne \(cellulaire')          # liste blanche avant un lieu
        self.assertRegex(T(l[4]), rf'INFO +{DNS}\s+base werkzeug srv\.exemple\.org')
        self.assertNotIn("autres comptes", out)
        self.assertNotIn("Bob B", out)                                                                       # no person name for a shared place
        presence = out.split("Présence d'après")[1]
        self.assertIn("Alice A", T(presence))
        self.assertNotIn("ETS", T(presence))                                                                    # no individual presence for a shared place
        self.assertIn("lieux ", err)                                                                         # French output text shown as an example: "Listes: ... lieux ...(4 plage(s))"
        self.assertIn("(4 plages)", err)
        # Non-shared and with no known person (--no-history): the place replaces the DNS
        out = self.lancer("--no-history", "--no-presence")[1].splitlines()
        self.assertRegex(out[2], r'INFO +11\.101\.16\.52\s+base werkzeug Quartier Rosemont\s+')
        self.assertRegex(out[4], rf'{DNS}\s+base werkzeug srv\.exemple\.org')

    def test_colonne_d_adresse_alignee_meme_sans_adresse_et_en_ipv6(self):
        """Les messages démarrent à la même colonne, qu'il y ait une adresse ou non ; une adresse IPv6 plus longue que la colonne ne casse rien."""
        v6 = "2001:db8:85a3:0:0:8a2e:370:7334"
        self.write("history.txt", "")
        self.journal([werkzeug(DNS), odoo("INFO", "base", "odoo.addons.base.models.ir_cron", "Job 'Autovacuum' (3) starting"),
                      odoo("WARNING", "base", "odoo.modules.loading", "Un avertissement"), werkzeug(v6, "/ipv6"), werkzeug(DNS, "/fin")])
        rc, out, err = self.lancer("--no-isp", "--no-presence")
        self.assertNotIn("Traceback", err)
        lines = out.splitlines()
        self.assertEqual(len(lines), 5, out)
        for text_line in (lines[0], lines[3]):
            self.assertIn("base werkzeug ", T(text_line))
        self.assertEqual(lines[0].index("base werkzeug"), lines[1].index("base odoo.addons"))     # with or without address: same column
        self.assertEqual(lines[0].index("base werkzeug"), lines[4].index("base werkzeug"))
        self.assertIn(f"INFO    {v6} ", T(lines[3]))                                                        # IPv6: column exceeded, whole address
        self.assertRegex(T(lines[2]), r"WARN\s+base odoo\.modules\.loading\s+Un avertissement")

    def test_proprietaire_du_bloc_organisation_ou_nom_de_reseau(self):
        """« (ISP) » laissait croire à un fournisseur d'accès : c'est le PROPRIÉTAIRE du bloc d'adresses d'après RDAP. « Nom (org) » :
        organisation enregistrée ; « NOM (réseau) » : seulement le nom technique du réseau (ex. « meta-mnt »). Même nom pour tout le bloc."""
        self.journal([werkzeug(ISP)])
        self.write("rdap.json", json.dumps({"name": "META-MNT", "country": "BE", "cidr0_cidrs": [{"v4prefix": "11.40.0.0", "length": 14}]}))
        out = self.lancer("--no-presence")[1]
        self.assertRegex(out, rf"INFO BE {ISP}\s+base werkzeug META-MNT \(réseau\)\s+")
        self.assertNotIn("(org)", out)
        self.assertNotIn("ISP", out)
        self.write("rdap.json", json.dumps({"name": "VL-Q", "country": "CA", "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Videotron Ltee"]]]}]}))
        out = self.lancer("--no-presence")[1]
        self.assertRegex(out, rf"INFO CA {ISP}\s+base werkzeug Videotron Ltee \(org\)\s+")
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        self.assertEqual(live.Resolver.block_name({"organisation": "Meta Platforms", "reseau": "X"}, "1.2.3.4"), ("org", "Meta Platforms", None))
        self.assertEqual(live.Resolver.block_name({"organisation": "", "reseau": "meta-mnt"}, "1.2.3.4"), ("reseau", "meta-mnt", None))
        self.assertEqual(live.Resolver.block_name(None, "1.2.3.4"), ("unknown", "1.2.3.4", None))
        rc, out, err = self.run_cmd(["python3", self.prog, "--help"])
        self.assertIn("propriétaire du bloc d'adresses", " ".join(out.split()))

    # --- alignment, suspicious requests, reverse video ---
    def en_couleur(self, *args):
        """Sortie dans un VRAI terminal (couleurs actives, séquences conservées) : (stdout+stderr du pty)."""
        extra = [] if any(o in args for o in ("--show-ip", "--hide-ip")) else ["--show-ip"]     # 1.112 : IP masquée par défaut ; ces tests de couleur lisent l'adresse
        text, _ = self.run_pty(["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--no-presence", *extra, *args], [], keep_ansi=True)
        return text

    def test_nom_sur_au_moins_45_caracteres_jamais_tronque_et_logger_sans_adresse_sur_45(self):
        """Le nom qui remplace l'adresse occupe AU MOINS 45 caractères (un nom plus long dépasse, sans être coupé) ; sur une ligne SANS adresse, le premier
        champ (avant « : ») aussi : le texte s'aligne."""
        long_nom = "Étienne (cellulaire Vidéotron, adresse actuelle)"                # 47 characters: longer than 42
        self.liste_blanche(f"{self.equipe_ip}  # {long_nom}\n")
        self.journal([werkzeug(DNS, "/a"), werkzeug(PERSONNE, "/b"), werkzeug(self.equipe_ip, "/c"),
                      odoo("INFO", "base", "odoo.addons.mail.models.mail_mail", "Courriel envoyé"),
                      odoo("ERROR", "base", "odoo.addons.base.models.ir_mail_server.un_nom_de_logger_vraiment_tres_long", "Échec"),
                      odoo("INFO", "base", "odoo.addons.base.models.res_users", f"Login failed for db:base login:x from {DNS}")])
        lines = self.lancer("--no-presence", "--dns-max", "45")[1].splitlines()
        self.assertRegex(lines[0], re.escape("base werkzeug " + "srv.exemple.org".ljust(45) + " ") + r'H1\.1 \d+[ \d.-]*GET  /a')
        self.assertRegex(lines[1], re.escape("base werkzeug " + "Étienne Dupont".ljust(45) + " ") + r'H1\.1 \d+[ \d.-]*GET  /b')
        self.assertIn("base werkzeug " + long_nom + ' H1.1 200', lines[2], "nom de 47 caractères : jamais tronqué, un seul espace avant la suite")
        # The URLs of request lines start at the SAME column when the name fits in 45 characters
        self.assertEqual(lines[0].index('GET'), lines[1].index('GET'))
        # Line without address: "odoo.addons.mail.models.mail_mail" on 45 characters, then the text
        self.assertRegex(lines[3], r"base odoo\.addons\.mail\.models\.mail_mail\s+Courriel envoyé")
        self.assertRegex(lines[4], r"odoo\.addons\.base\.models\.ir_mail_server\.un_nom_de_logger_vraiment_tres_long\s+Échec")    # longer: intact (padded up to the GET column)
        self.assertEqual(lines[3].index("Courriel"), lines[0].index('GET'))        # the text starts at the GET / POST column of requests
        # Line that has an address elsewhere than in the field ("... from IP"): its logger is not lengthened
        self.assertRegex(lines[5], r"base odoo\.addons\.base\.models\.res_users\s+Login failed")

    def test_requetes_suspectes_en_video_inverse(self):
        """WordPress, .php, phpMyAdmin, .env, .git, sauvegardes, traversée de répertoires, gestionnaire de bases : le URL (seulement) en vidéo inverse,
        sans couleur ; les pages normales d'Odoo et de BigBlueButton jamais."""
        suspects = ["/wp-login.php", "/wordpress/wp-admin/", "/xmlrpc.php", "/index.php?id=1", "/phpmyadmin/index.php", "/.env", "/.git/config", "/.aws/credentials",
                    "/backup.sql", "/site.bak", "/cgi-bin/test.sh", "/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/web/database/manager",
                    "/server-status", "/vendor/phpunit/src/Util/PHP/eval-stdin.php", "/actuator/env", "/config.json", "/id_rsa"]
        normaux = ["/event", "/web/login", "/odoo/discuss", "/web/assets/1/web.assets_web.min.js", "/web/content/12/rapport.zip", "/en_CA/contactus",
                   "/bigbluebutton/api/getMeetings?checksum=abc", "/html5client/join?sessionToken=x", "/xmlrpc/2/common", "/web/static/src/img/logo.png",
                   "/learning-analytics-dashboard/?meeting=1&report=2", "/.well-known/acme-challenge/token", "/web/image/res.partner/3/avatar_128"]
        self.journal([werkzeug(DNS, u, 404 if i % 2 else 200) for i, u in enumerate(suspects + normaux)])
        text = self.en_couleur()
        for u in suspects:
            self.assertIn(f"\x1b[7;35m{u}\x1b[0m", text, f"{u} devrait être en vidéo inverse (requête suspecte)")
        for u in normaux:
            self.assertNotIn(f"\x1b[7;35m{u}\x1b[0m", text, f"{u} est une page normale")
        self.assertIn("\x1b[31m404\x1b[0m", text)                                   # the HTTP code keeps its color: only the URL is reversed
        self.assertIn("\x1b[32m200\x1b[0m", text)

    def test_url_en_erreur_critique_rouge_et_avertissement_jaune_en_video_inverse(self):
        """5xx : URL en vidéo inverse rouge ; 4xx : URL en vidéo inverse jaune (seulement le URL) ; 200 et 3xx : aucun ; la page de connexion garde son style
        (sauf en 5xx) ; une page suspecte garde la vidéo inverse magenta."""
        self.journal([werkzeug(DNS, "/boum", 500), werkzeug(DNS, "/panne", 503), werkzeug(DNS, "/absent", 404), werkzeug(DNS, "/interdit", 403),
                      werkzeug(DNS, "/trop", 429), werkzeug(DNS, "/ok", 200), werkzeug(DNS, "/ailleurs", 303), werkzeug(DNS, "/web/login", 429),
                      werkzeug(DNS, "/web/login", 500), werkzeug(DNS, "/wp-login.php", 500)])
        text = self.en_couleur()
        for u in ("/boum", "/panne"):
            self.assertIn(f"\x1b[7;91m{u}\x1b[0m", text)
        for u in ("/absent", "/interdit", "/trop"):
            self.assertIn(f"\x1b[7;93m{u}\x1b[0m", text)
        for u in ("/ok", "/ailleurs"):
            self.assertNotRegex(text, rf"\x1b\[7[0-9;]*m{u}\x1b")
        self.assertIn("\x1b[1;37;44m/web/login\x1b[0m", text)                       # connexion en 429 : son style (bleu)
        self.assertIn("\x1b[7;91m/web/login\x1b[0m", text)                           # connexion en 500 : critique d'abord
        self.assertIn("\x1b[7;35m/wp-login.php\x1b[0m", text)                           # suspicious, even in a 500: magenta reverse video
        self.assertIn("\x1b[1;31m500\x1b[0m", text)                                  # le code garde sa couleur

    def test_adresse_de_la_liste_blanche_en_blanc_et_des_lieux_en_gris_en_video_inverse(self):
        """Adresse de la liste blanche : fond BLANC ; adresse du fichier des lieux : fond GRIS (texte noir : couleurs explicites, jamais « 7;90 » qui devenait noir sur noir) (la liste blanche l'emporte) ; une autre
        adresse : aucune. Avec --hide-ip (pas d'adresse affichée), c'est le NOM qui l'est."""
        self.liste_blanche(f"{self.equipe_ip}  # Étienne (cellulaire)\n10.9.8.7  # Bureau test\n")
        self.lieux("11.101.16.52  # Quartier Rosemont\n10.9.8.7  # Lieu aussi dans la liste blanche\n")
        self.journal([werkzeug(self.equipe_ip, "/a"), werkzeug("11.101.16.52", "/b"), werkzeug(DNS, "/c"), werkzeug("10.9.8.7", "/d")])
        text = self.en_couleur()
        self.assertIn("INFO    \x1b[107;30m" + self.equipe_ip + "\x1b[0m", text)               # liste blanche : fond blanc, texte noir
        self.assertRegex(text, r"INFO +\x1b\[(?:48;5;245|47);30m11\.101\.16\.52\x1b\[0m")        # place: gray background, black text (explicit: readable on any theme)
        self.assertIn("\x1b[107;30m10.9.8.7\x1b[0m", text)                                                          # dans les deux : la liste blanche l'emporte
        self.assertNotIn("\x1b[107;30m" + DNS, text)                                                                # autre adresse : rien
        self.assertNotRegex(text, r"\x1b\[(?:48;5;245|47);30m" + re.escape(DNS))
        masque = self.en_couleur("--hide-ip")
        self.assertIn("\x1b[107;30mÉtienne (cellulaire)", masque)                                                    # --hide-ip: the name is reversed
        self.assertRegex(masque, r"\x1b\[(?:48;5;245|47);30mQuartier Rosemont")
        self.assertNotIn(self.equipe_ip, masque)

    def test_liste_blanche_et_lieux_ont_fond_et_texte_explicites(self):
        """« 7;90 » (gris inversé) était noir sur noir sur un thème où le noir brillant est noir : fond ET texte sont explicites, indépendants du thème."""
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        for name in ("blanche", "place_ip"):
            self.assertRegex(T(live.STYLES[name]), r"^(?:107|47|48;5;\d+);30$", f"{name} : fond et texte explicites")
        self.assertNotEqual(live.STYLES["blanche"], live.STYLES["place_ip"])

    def test_legende_au_demarrage_et_aucune_sequence_dans_un_tube(self):
        text = self.en_couleur()
        self.assertIn("Vidéo inverse : ", text)
        for caption in ("URL suspect", "URL en erreur 5xx", "URL en erreur 4xx", "adresse de la liste blanche", "adresse d'un lieu"):
            self.assertIn(caption, text)
        self.journal([werkzeug(DNS, "/wp-login.php", 500), werkzeug(self.equipe_ip, "/x", 404)])
        rc, out, err = self.lancer("--no-presence")
        self.assertNotIn("\x1b[", out + err, "dans un tube : aucune séquence, mais le même texte")
        self.assertIn('H1.1 500    -  105  0.046  0.426       GET  /wp-login.php', out)
        self.assertNotIn("Vidéo inverse", err)

    def test_presentation_compacte_sans_deux_points_crochets_ni_tirets(self):
        """Ligne structurée d'Odoo : « odoo18 odoo INFO » (sans « : »), adresse et pays SANS crochets dans la colonne de 18 caractères, logger sans « : », et le
        « - - » (identité RFC 1413 et utilisateur HTTP, toujours « - » dans Odoo) retiré ; le nom et le premier champ occupent au moins 45 caractères."""
        self.geoip()
        self.journal([werkzeug(DNS, "/event"), odoo("INFO", "base", "odoo.addons.base.models.ir_cron", "Job 'Mail' (9) starting"), werkzeug(self.equipe_ip, "/web/login")])
        rc, out, err = self.lancer("--no-presence")
        l = out.splitlines()
        horloge = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d\d "
        self.assertRegex(l[0], "^" + horloge + "odoo18 odoo INFO " + re.escape(f"US {DNS}".ljust(18)) + " base werkzeug " + re.escape("srv.exemple.org".ljust(45))
                         + " " + re.escape(block()) + "$")
        self.assertRegex(l[1], "^" + horloge + "odoo18 odoo INFO " + " " * 18 + " base odoo\\.addons\\.base\\.models\\.ir_cron\\s+Job 'Mail' \\(9\\) starting$")
        for text_line in l:
            self.assertNotIn(" - - ", T(text_line))                                           # identity and user: always "-"
            self.assertNotIn("odoo:", T(text_line))                                           # ":" after the program
            self.assertNotRegex(T(text_line), r"INFO \[")                                     # colonne sans crochets
            self.assertNotIn("werkzeug:", T(text_line))
            self.assertNotIn("ir_cron ", T(text_line.replace("ir_cron" + " " * 8, "")))       # (the logger is followed by spaces, never ":")
            self.assertNotRegex(T(text_line), r"ir_cron\s*:")
        self.assertRegex(l[2], r"INFO +" + re.escape(self.equipe_ip) + r"\s+base werkzeug Étienne")
        # BigBlueButton / nginx: "- -" removed only if it is "- -"; an authenticated HTTP user stays visible
        nginx = os.path.dirname(self.path("nginx", "x"))
        with open(os.path.join(nginx, "bigbluebutton.access.log"), "w") as f:
            f.write(f'{DNS} - - [02/Oct/2026:03:02:14 +0000] "GET /bigbluebutton/api HTTP/1.1" 200 5\n'
                    f'{DNS} - alice [02/Oct/2026:03:02:15 +0000] "GET /bigbluebutton/api HTTP/1.1" 200 5\n')
        rc, out, err = self.lancer("--app", "bbb", "--no-isp", env_extra={"APP_LOG_LIVE_NGINX_DIR": nginx})
        self.assertIn(f"srv.exemple.org [US {DNS}]".ljust(45) + ' [02/Oct/2026:03:02:14 +0000] "GET', out)
        self.assertIn(f"srv.exemple.org [US {DNS}]".ljust(45) + ' - alice [02/Oct/2026:03:02:15 +0000] "GET', out)

    def test_url_de_get_et_de_post_alignes(self):
        """[3] « GET » (3 lettres) est suivi d'un espace de plus : le URL d'un GET ou d'un PUT commence à la même colonne que celui d'un POST ou d'un HEAD."""
        self.journal([werkzeug(DNS, "/a"), werkzeug(DNS, "/b", methode="POST"), werkzeug(DNS, "/c", methode="PUT"), werkzeug(DNS, "/d", methode="HEAD")])
        rc, out, err = self.lancer("--no-presence")
        lines = out.splitlines()
        self.assertEqual(len(lines), 4, out)
        self.assertIn('GET  /a', T(lines[0]))
        self.assertIn('POST /b', T(lines[1]))
        self.assertIn('PUT  /c', T(lines[2]))
        self.assertIn('HEAD /d', T(lines[3]))
        self.assertEqual({l.index(" /") for l in lines}, {lines[0].index(" /")}, "les URL doivent commencer à la même colonne")

    def test_option_pages_introuvables_404(self):
        """[1] --not-found : seulement les réponses 404 ; le résumé liste TOUTES les pages introuvables avec leur nombre."""
        self.journal([werkzeug(DNS, "/a", code=200), werkzeug(DNS, "/absente", code=404), werkzeug(DNS, "/absente", code=404), werkzeug(PERSONNE, "/autre", code=404),
                      werkzeug(DNS, "/interdite", code=403), odoo("INFO", "base", "odoo.modules.registry", "Caches invalidated")])
        rc, out, err = self.lancer("--no-presence", "--no-isp", "--not-found", "--summary")
        body = out.split("──── Résumé")[0]
        self.assertEqual(len([l for l in body.splitlines() if 'GET' in l]), 3, out)
        for absent in ("/a\"", "/interdite", "Caches invalidated"):
            self.assertNotIn(absent, body)
        r = " ".join(out.split())
        self.assertIn("Pages introuvables (404) 2 pages, 3 réponses :", T(r))
        self.assertIn("/absente ×2", T(r))
        self.assertIn("/autre ×1", T(r))

    def test_avertissement_espace_disque_des_journaux(self):
        """[3] WARNING dans le flux quand la partition des journaux a moins de --disk-min Go libres ; --disk-min 0 : jamais."""
        self.journal([werkzeug(DNS, "/a")])
        rc, out, err = self.lancer("--no-presence", "--no-isp", "--disk-min", "100000000")
        self.assertRegex(out, r"WARNING espace disque : [\d.]+ Go libres seulement \(seuil 1e\+08 Go\) sur /")
        rc, out, err = self.lancer("--no-presence", "--no-isp", "--disk-min", "0")
        self.assertNotIn("WARNING espace disque", out)

    def test_messages_d_odoo_alignes_sur_le_get_des_requetes(self):
        """[1] Les messages d'Odoo qui ne sont pas des requêtes (cron, registre, connexion, avertissements) commencent à la colonne du « GET / POST »,
        jamais au-dessus des colonnes de chiffres — quel que soit le niveau (INFO, WARNING, ERROR…)."""
        self.journal([werkzeug(DNS, "/a"), odoo("INFO", "base", "odoo.modules.registry", "Caches invalidated"), login(PERSONNE, "etienne@exemple.org"),
                      odoo("WARNING", "base", "odoo.http", "Avertissement"), odoo("ERROR", "base", "odoo.addons.mail.models.mail_mail", "Echec d'envoi")])
        for options in ((), ("--min",)):
            rc, out, err = self.lancer("--no-presence", "--no-isp", *options)
            lines = [ANSI.sub("", l) for l in out.splitlines()]
            self.assertEqual(len(lines), 5, out)
            column = lines[0].index('GET')
            for text_line, text in zip(lines[1:], ("Caches invalidated", "Login successful", "Avertissement", "Echec d'envoi")):
                self.assertEqual(text_line.index(text), column, f"{options} : {text_line}")

    # --- 1.11: websocket date, digits after the HTTP code, name width, place + person, team country ---
    def test_date_iso_du_websocket_retiree_si_c_est_le_meme_instant(self):
        """[1] « [2026-10-08 13:11:22] » (UTC) après le nom, alors que la ligne porte déjà 09:11:22 (local) : retirée, et le GET s'aligne sur les autres lignes ;
        une date qui n'est PAS le même instant est gardée."""
        fixe = datetime.datetime(2026, 10, 8, 9, 11, 22, 150000, FUSEAU)
        utc = fixe.astimezone(datetime.timezone.utc)
        autre = utc + datetime.timedelta(hours=1)
        self.journal([odoo("INFO", "base", "longpolling", f'{DNS} - - [{utc:%Y-%m-%d %H:%M:%S}] "GET /websocket?version=18.0-7 HTTP/1.1" 101 494 14.602170', fixe=fixe),
                      odoo("INFO", "base", "longpolling", f'{DNS} - - [{autre:%Y-%m-%d %H:%M:%S}] "GET /websocket?version=18.0-7 HTTP/1.1" 101 494 1.5', fixe=fixe),
                      werkzeug(DNS, "/event", fixe=fixe)])
        rc, out, err = self.lancer("--no-presence", "--no-isp")
        l = out.splitlines()
        self.assertNotIn(f"[{utc:%Y-%m-%d}", T(l[0]))
        self.assertIn(f"[{autre:%Y-%m-%d %H:%M:%S}]", T(l[1]))                                   # another instant: kept
        self.assertRegex(T(l[0]), r'base longpolling srv\.exemple\.org {28}H1\.1 101  494 {13}14\.602       GET  /websocket\?version=18\.0-7$')
        self.assertEqual(l[0].index('GET'), l[2].index('GET'), "le GET du websocket est aligné sur celui des autres lignes")
        m = self.lancer("--no-presence", "--no-isp", "--min")[1].splitlines()                 # 2.40 --min: neither "werkzeug" nor "longpolling" (a REQUEST): names aligned
        self.assertNotIn("longpolling", m[0])
        self.assertEqual(m[0].index('GET'), m[2].index('GET'))
        self.assertEqual(m[0].index("srv.exemple.org"), m[2].index("srv.exemple.org"), "le nom du websocket commence à la même colonne que celui des autres requêtes")

    def test_changement_d_ip_externe_affiche_les_fichiers_de_etc_default(self):
        """2.40 : curl ifconfig.me ; la première adresse est seulement mémorisée ; si elle change : WARNING avec l'ancienne et la nouvelle adresse et les fichiers
        de /etc/default qui contiennent l'ancienne ; adresse inchangée : rien ; --no-isp : jamais de requête ; réponse invalide : rien."""
        state = os.path.dirname(self.path("etat-ip", "x"))
        default_value = os.path.dirname(self.path("etc-default-ip", "x"))
        self.write("etc-default-ip/nginx-tools-lists.conf", "WHITELIST=\"203.0.113.7 198.51.100.1\"\n")
        self.write("etc-default-ip/autre.conf", "X=\"1203.0.113.70\"\n")                      # contient la suite de chiffres, pas l'adresse
        env = {"APP_LOG_LIVE_STATE_DIR": state, "APP_LOG_LIVE_DEFAULT_DIR": default_value}
        self.journal([werkzeug(DNS, "/event")])

        def curl(reponse):
            self.mock("curl", f'echo "{reponse}"; echo "$@" >> {self.d}/curl-ip.log')
        curl("203.0.113.7")
        rc, out, err = self.lancer("--no-presence", env_extra=env)
        self.assertNotIn("a changé", out + err)                                                   # first address: remembered
        with open(os.path.join(state, "ip-externe.txt")) as f:
            self.assertEqual(T(f.read().strip()), "203.0.113.7")
        with open(os.path.join(self.d, "curl-ip.log")) as f:
            self.assertIn("ifconfig.me", T(f.read()))
        rc, out, err = self.lancer("--no-presence", env_extra=env)
        self.assertNotIn("a changé", out + err)                                                   # unchanged
        curl("198.51.100.99")
        rc, out, err = self.lancer("--no-presence", env_extra=env)
        self.assertIn("l'adresse IP externe de ce serveur a changé : 203.0.113.7 → 198.51.100.99", out)
        self.assertIn("doivent être changés", out)
        self.assertIn(os.path.join(default_value, "nginx-tools-lists.conf"), out)
        self.assertNotIn("autre.conf", out)
        with open(os.path.join(state, "ip-externe.txt")) as f:
            self.assertEqual(T(f.read().strip()), "198.51.100.99")                               # remembered: no repetition
        rc, out, err = self.lancer("--no-presence", env_extra=env)
        self.assertNotIn("a changé", out)
        curl("pas une adresse")
        rc, out, err = self.lancer("--no-presence", env_extra=env)
        self.assertNotIn("a changé", out)
        curl("192.0.2.5")
        rc, out, err = self.lancer("--no-presence", "--no-isp", env_extra=env)
        self.assertNotIn("a changé", out)                                                         # --no-isp: no external request
        with open(os.path.join(state, "ip-externe.txt")) as f:
            self.assertEqual(T(f.read().strip()), "198.51.100.99")

    def test_url_avec_guillemets_reste_alignee(self):
        """1.43 : une URL qui contient des guillemets (lien « <a href%3D"https://…"> » d'un robot) ne casse plus l'alignement : le bloc des chiffres passe avant la requête
        comme sur les autres lignes, et le code HTTP est reconnu."""
        url = '/event/1/ics?action=TEMPLATE&text=21+ans&details=<a+href%3D"https://exemple.org/event/1/register">21+ans</a>%0AInscrivez&location=ETS,+Montreal'
        self.journal([werkzeug(DNS, "/event"), werkzeug(DNS, url, 200), werkzeug(DNS, "/event")])
        rc, out, err = self.lancer("--no-presence", "--no-isp", "--min")
        l = out.splitlines()
        self.assertEqual(len(l), 3, out)
        self.assertEqual(l[0].index("H1.1"), l[1].index("H1.1"), out)
        self.assertEqual(l[0].index('GET'), l[1].index('GET'), out)
        self.assertTrue(l[1].rstrip().endswith('Montreal'), l[1])
        live = self.module_live()
        self.assertEqual(T(live.REQUEST_RE.search(f'"GET {url} HTTP/1.1" 404').group(2)), "404")
        self.assertEqual(T(live.STATUS_RE.search(f'"GET {url} HTTP/1.1" 404').group(1)), "404")

    def test_legende_des_chiffres_apres_le_code_http_et_couleurs_des_valeurs_elevees(self):
        """[2] Légende au démarrage ; nombre de requêtes SQL (>= 300 orange, >= 1000 rouge) et taille (>= 1 Mo orange, >= 10 Mo rouge) colorés ; --slow 0 : aucune couleur."""
        rc, out, err = self.lancer("--no-presence")
        self.assertIn("taille de la réponse en octets", err)
        self.assertIn("nombre de requêtes SQL", err)
        self.assertIn("temps SQL s · temps Python s", err)
        self.assertIn("websocket", err)
        database = werkzeug(DNS, "/p")
        self.journal([database.replace("200 - 105 0.046", "200 - 400 0.046"), database.replace("200 - 105 0.046", "200 - 1500 0.046"),
                      database.replace("200 - 105 0.046", "200 2500000 105 0.046"), database.replace("200 - 105 0.046", "200 25000000 105 0.046"),
                      database.replace("200 - 105 0.046", "200 999 105 0.046")])
        text = self.en_couleur()
        orange = r"\x1b\[1;(?:33|38;5;208)m"
        self.assertRegex(text, orange + r"400\x1b\[0m")
        self.assertIn("\x1b[1;31m1500\x1b[0m", text)
        self.assertRegex(text, orange + r"2500000\x1b\[0m")
        self.assertIn("\x1b[1;31m25000000\x1b[0m", text)
        self.assertNotRegex(text, r"m999\x1b\[0m")                                         # sous le seuil : rien
        self.assertNotRegex(self.en_couleur("--slow", "0"), orange + r"400\x1b")

    def test_journal_d_odoo_en_fichier_logfile(self):
        """2.32 : la configuration d'Odoo (ODOO_CONF_PATHS) indique un logfile → les lignes du fichier sont lues (heure UTC convertie), sans journalctl."""
        journal = self.path("odoo-fichier.log")
        with open(journal, "w") as f:
            f.write('2026-10-12 14:07:18,326 502389 INFO base werkzeug: %s - - [12/Oct/2026 14:07:18] "GET /event HTTP/1.1" 200 - 105 0.046 0.426\n' % DNS)
            f.write("2026-10-12 14:07:19,001 502389 ERROR base odoo.http: Exception during request handling.\n")
            f.write("Traceback (most recent call last):\n")
        conf = self.path("odoo-meetup.conf")
        with open(conf, "w") as f:
            f.write(f"[options]\nhttp_port = 8169\nlogfile = {journal}\n")
        rc, out, err = self.lancer("--no-presence", env_extra={"ODOO_CONF_PATHS": conf, "APP_DETECT_ROOT": "", "TZ": "America/Toronto"})
        self.assertEqual(rc, 0, err)
        self.assertIn("journal : fichier " + journal, err)
        self.assertIn("2026-10-12 10:07:18.33", out)                       # 14:07 UTC = 10:07 heure de l'Est (FUSEAU des tests)
        self.assertIn('GET  /event', out)
        self.assertIn("ERR", out)                                                # 1.123: level on 4 characters
        self.assertIn("Traceback (most recent call last):", out)

    def test_demarrage_en_anglais_sans_francais(self):
        """Avec --lang en, aucun message de démarrage (sortie d'erreur) ne contient de mot français : « Listes : », « Couleurs : », « Adresses bannies : »…"""
        rc, out, err = self.lancer("--lang", "en", "--no-presence")
        words = re.compile(r"\b(?:listes?|lieux|fichiers?|aucune?|désactivé|couleurs?|taille|temps|adresses|bannies|réseau|propriétaire|requêtes|visiteurs)\b", re.I)
        for text_line in err.splitlines():
            self.assertIsNone(words.search(text_line), text_line)
        self.assertIn("Lists: white list", err)
        self.assertIn("size ≥ 1 MB", err)

    def test_dns_max_et_dns_max_truncate(self):
        """[3] largeur par défaut 45 ; [4] --dns-max-truncate [N] coupe à N (32 sans valeur) ; [5] --dns-max [N] fixe la largeur sans couper (20 sans valeur)."""
        long_nom = "Étienne (cellulaire Vidéotron, adresse actuelle)"                       # 48 characters
        self.liste_blanche(f"{self.equipe_ip}  # {long_nom}\n")
        self.journal([werkzeug(DNS, "/a"), werkzeug(self.equipe_ip, "/b")])

        def names(*args):
            l = self.lancer("--no-presence", *args)[1].splitlines()
            return [re.search(r"werkzeug (.*?) {1,}H1\.1 ", x).group(1) for x in l], l
        n, l = names()
        self.assertEqual(n, ["srv.exemple.org", long_nom[:44] + "…"])                       # default: width 45, name cut with "..."
        self.assertEqual(l[0].index("H1.1"), l[0].index("srv.exemple.org") + 45 + 1)
        n, l = names("--dns-max", "45")
        self.assertEqual(n, ["srv.exemple.org", long_nom])                                  # --dns-max removes the cut
        n, l = names("--dns-max-truncate")
        self.assertEqual(n, ["srv.exemple.org", long_nom[:31] + "…"])                      # 32 characters at most, the last one is "..."
        self.assertEqual(len(n[1]), 32)
        self.assertEqual(l[0].index("H1.1"), l[0].index("srv.exemple.org") + 32 + 1)
        n, l = names("--dns-max-truncate", "10")
        self.assertEqual(n, ["srv.exemp…", "Étienne (…"])
        n, l = names("--dns-max", "20")
        self.assertEqual(n[1], long_nom)                                                    # never truncated
        self.assertEqual(l[0].index("H1.1"), l[0].index("srv.exemple.org") + 20 + 1)
        n, l = names("--dns-max")                                                            # sans valeur : 20
        self.assertEqual(l[0].index("H1.1"), l[0].index("srv.exemple.org") + 20 + 1)
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "--dns-max", "30", "--dns-max-truncate", "30"])
        self.assertEqual(rc, 2)                                                             # l'un OU l'autre
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "--dns-max", "2"])
        self.assertEqual(rc, 2)
        self.assertIn("--dns-max doit être compris entre 4 et 200", T(err))
        aide = self.run_cmd(["python3", self.prog, "--help"])[2] + self.run_cmd(["python3", self.prog, "--help"])[1]
        self.assertIn("--dns-max-truncate", aide)

    def test_lieu_et_personne_sur_la_meme_adresse(self):
        """[7bis] Adresse d'un lieu (non partagé) où une personne s'est connectée : « Personne | Lieu » ; plusieurs comptes : le lieu d'abord (on ne sait pas qui fait la requête)."""
        self.write("history.txt", "\n".join([histo(AUTRE, "alice@exemple.org"), histo(TROISIEME, "alice@exemple.org"), histo(TROISIEME, "bob@exemple.org")]) + "\n")
        self.lieux(f"{AUTRE}        # ETS-Université\n{TROISIEME}   # Bureau\n")
        self.journal([werkzeug(AUTRE, "/a"), werkzeug(TROISIEME, "/b")])
        l = self.lancer("--no-presence")[1].splitlines()
        self.assertRegex(l[0], r"werkzeug Alice A \| ETS-Université +H1\.1 \d+[ \d.-]*GET")
        self.assertRegex(l[1], r"werkzeug Bureau \| BobB\+AliceA +H1\.1 \d+[ \d.-]*GET")

    def test_le_pays_s_affiche_aussi_pour_l_equipe(self):
        """[8bis] Une adresse de la liste blanche publique garde son pays (seules les adresses locales, privées et celles de ce serveur n'en ont pas)."""
        publique = "11.97.88.181"
        self.liste_blanche(f"{publique}  # Maison-ÉtienneB\n")
        self.mock("geoiplookup", f'case "$1" in {publique}) echo "GeoIP Country Edition: CA, Canada";; *) echo "GeoIP Country Edition: IP Address not found";; esac')
        self.journal([werkzeug(publique, "/websocket"), werkzeug(publique, "/bus/has_missed_notifications", methode="POST"), werkzeug("127.0.0.1")])
        l = self.lancer("--no-presence")[1].splitlines()
        self.assertRegex(l[0], rf"INFO CA {publique}\s+base werkzeug Maison-ÉtienneB")
        self.assertRegex(l[1], rf"INFO CA {publique}\s+base werkzeug Maison-ÉtienneB")
        self.assertRegex(l[2], r"INFO +127\.0\.0\.1\s+base werkzeug ce serveur")

    # --- 1.11: dashboard (Ctrl-G, Ctrl-T), health, daily log ---
    def journal_tableau(self, waiting=12):
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/fr_CA/event"), werkzeug(DNS, "/en_US/shop"), werkzeug(DNS, "/es/x"), werkzeug(DNS, "/web/assets/1/a.js"),
                      werkzeug(DNS, "/absent", 404), werkzeug(DNS, "/boum", 500), werkzeug(DNS, "/boum?x=1", 500),
                      odoo("ERROR", "base", "odoo.addons.base.models.ir_mail_server", "Mail Delivery Failed pour 12 destinataires"),
                      self.lente(DNS, "/lente", "2.0", "9.0"), werkzeug(DNS, "/event")], after=f"sleep {waiting}")

    def test_tableau_de_bord_ctrl_g_puis_changements_ctrl_t(self):
        """[6][7] Ctrl-G : tableau de bord (santé, efficacité du programme, cache, pages par langue, top 10 des URLs, erreurs d'Odoo) ; Ctrl-T : seulement ce qui a changé depuis la dernière fois."""
        self.journal_tableau()
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "1"],
                                       [(b"/event", b"\x07", 0.8), (b"Top 10 des URLs", b"\x14", 0.8), (b"Depuis le dernier affichage", b"\x03", 0.5)], timeout=60)
        self.assertEqual(envoyees, 3, text)
        self.assertIn("Touches : ? (ou h) menu", text)
        self.assertIn("Ctrl-G tableau de bord", text)
        table_rows = text[text.index("Tableau de bord depuis le démarrage"):text.index("Depuis le dernier affichage")]
        t = " ".join(table_rows.split())
        self.assertIn("Santé : ⚠ à regarder", T(t))                                              # 2 5xx errors, 1 email error, 1 slow request: under the "problem" thresholds (5)
        self.assertIn("⚠ Erreurs HTTP 5xx : 2 URL : /boum ×1 ; /boum?x=1 ×1", T(t))
        self.assertIn("Erreurs d'Odoo (ERROR / CRITICAL) : 1", T(t))
        self.assertIn("ERROR odoo.addons.base.models.ir_mail_server ×1 : Mail Delivery Failed pour N destinataires", T(t))     # numbers normalized
        self.assertIn("Courriels en échec : 1", T(t))
        self.assertIn("odoo-mail-retry.py", T(t))
        self.assertIn("Requêtes lentes (≥ 5 s) : 1", T(t))
        self.assertIn("Efficacité du programme", T(t))
        self.assertRegex(T(t), r"Programme : CPU \d+\.\d %")
        self.assertRegex(T(t), r"mémoire \d+(\.\d)? (Ko|Mo)")
        self.assertRegex(T(t), r"Cache des adresses : \d+ % des \d+ demandes sans recherche extérieure")
        self.assertRegex(T(t), r"Pages par langue \(\d+ pages\) : .*FR \d+ %")
        for lang in ("EN", "ES", "sans préfixe"):
            self.assertIn(lang, t)
        self.assertIn("Codes HTTP : 2xx", T(t))
        self.assertIn("Top 10 des URLs (toutes les requêtes, erreurs comprises) :", T(t))
        self.assertRegex(T(t), r"2 /event")                                                      # most requested first, with its count
        # Ctrl-T right after: nothing changed since the last display
        after = " ".join(text[text.index("Depuis le dernier affichage"):].split())
        self.assertIn("0 lignes affichées · 0 requêtes", T(after))
        self.assertIn("Santé : ✔ tout va bien", T(after))

    def test_diagnostic_des_recommandations_de_web_monitor(self):
        """1.29 : « Adresses à bannir : aucune » dit POURQUOI les adresses recommandées par web-monitor.py ne sont pas proposées (fichier absent, illisible, trop ancien, adresses écartées)."""
        live = self.module_live()
        folder = os.path.join(self.d, "wm-diag")
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, "recommended-bans.json")
        patcher = unittest.mock.patch.dict(os.environ, {"WEB_MONITOR_STATE_DIR": folder})
        patcher.start()
        self.addCleanup(patcher.stop)
        st = live.Stats(5.0)
        self.assertIn("absent", T(st.reco_diagnostic()))
        with open(file_path, "w") as f:
            json.dump({"time": time.time() - 100 * 3600, "ips": [{"ip": "11.60.140.42", "raison": "x"}]}, f)
        st._reco_t = 0
        self.assertIn("trop ancien", T(st.reco_diagnostic()))
        with open(file_path, "w") as f:
            json.dump({"time": time.time(), "ips": [{"ip": "11.60.140.42", "raison": "x"}, {"ip": "11.49.124.180", "raison": "y"}]}, f)
        st._reco_t = 0
        st.all_banned.add("11.60.140.42")
        self.assertEqual(dict(st.to_ban()), {"11.49.124.180": 0})
        self.assertIn("déjà bannies : 11.60.140.42", T(st.reco_diagnostic()))
        st.all_banned.add("11.49.124.180")
        st._reco_t = 0
        self.assertEqual(st.to_ban(), [])
        self.assertIn("web-monitor.py en recommande 2, écartées — déjà bannies : 11.60.140.42, 11.49.124.180", T(st.reco_diagnostic()))   # 2.0: grouped by reason
        L = live.Line(werkzeug("8.8.8.8", "/a", 200))
        L.instant = time.time()
        st.ajouter(L, {"8.8.8.8": ("ok.exemple.org", [], False, None)}, None)
        self.assertIn("Recommandations de web-monitor.py", T(" ".join(st.summary())))

    def test_sommaire_en_couleurs_compteurs_aucune_et_codes_http(self):
        """1.50 : dans le sommaire, les « ×N » et les comptes du Top 10 sont en couleur, « aucune » en vert, chaque classe de codes HTTP a la couleur de son code
        (2xx vert, 3xx cyan, 4xx rouge, 5xx rouge gras) ; sans couleur (sortie redirigée) le texte est identique."""
        live = self.module_live()
        st = live.Stats(5.0)
        for path, code in (("/event", 200), ("/event", 200), ("/ancien", 301), ("/introuvable", 404), ("/boum", 500)):
            L = live.Line(werkzeug("8.8.8.8", path, code))
            L.instant = time.time()
            st.ajouter(L, {"8.8.8.8": ("ok.exemple.org", [], False, None)}, None)
        live.COLOR = True
        try:
            t = "\n".join(st.summary(["  Efficacité du programme"], (), "Test", 9))
        finally:
            live.COLOR = False
        self.assertIn("\x1b[1;36m×5\x1b[0m", T(t))                                   # adresses les plus actives
        self.assertIn("\x1b[1;36m     2\x1b[0m  /event", T(t))                        # Top 10
        self.assertIn("\x1b[32maucune\x1b[0m", T(t))
        self.assertIn("\x1b[32m2xx 40 %\x1b[0m", T(t))
        self.assertIn("\x1b[1;31m5xx 20 %\x1b[0m", T(t))
        self.assertIn("\x1b[31m4xx 20 %\x1b[0m", T(t))
        propre = "\n".join(st.summary(["  Efficacité du programme"], (), "Test", 9))
        self.assertNotIn("\x1b", T(propre))
        self.assertIn("Codes HTTP : 2xx 40 % · 3xx 20 % · 4xx 20 % · 5xx 20 %", T(propre))

    def test_details_des_erreurs_heure_adresse_utilisateur_et_version_de_l_alerte(self):
        """1.52 : sous « Erreurs HTTP 5xx », les dernières erreurs avec l'heure, le code, l'URL, l'adresse (et « utilisateur connu » pour une personne identifiée) ; les erreurs
        d'Odoo donnent l'heure (première / dernière) ; le titre de l'alerte santé porte la version du programme."""
        live = self.module_live()
        st = live.Stats(5.0)
        st.people.add("8.8.8.8")
        for path in ("/boum", "/pan"):
            L = live.Line(werkzeug("8.8.8.8", path, 500))
            L.instant = time.time()
            st.ajouter(L, {"8.8.8.8": ("Issam", [], False, None)}, None)
        st.names["8.8.8.8"] = "Issam"
        L = live.Line(odoo("ERROR", "base", "odoo.http", "Exception during request handling."))
        L.instant = time.time()
        st.ajouter(L, {}, None)
        lines = [ANSI.sub("", l) for l in st.health(())[1]]
        text = "\n".join(lines)
        self.assertRegex(T(text), r"\d\d:\d\d:\d\d  500  /pan  ← Issam \[8\.8\.8\.8\] — utilisateur connu")
        self.assertRegex(T(text), r"ERROR odoo\.http ×1 : Exception during request handling\. \(à \d\d:\d\d:\d\d\)")
        with open(script_path("app-log-live.py"), encoding="utf-8") as f:
            self.assertIn('Alerte santé ({os.path.basename(__file__)} v{__version__})', T(f.read()))

    def test_modules_d_odoo_presents_sur_le_disque_versions_et_mises_a_jour(self):
        """1.52 : au démarrage, état des modules installés : introuvables sur le disque (✖), version du disque ≠ version installée (⚠), mises à jour en attente (⚠), sinon ✔ ;
        versions des modules qui ne sont pas d'Odoo S.A."""
        live = self.module_live()
        self.timezone("UTC")                                                                             # PostgreSQL dates are in UTC, shown in local time
        addons = self.path("addons", "x")
        racine = os.path.dirname(addons)

        def manifest(name, version):
            os.makedirs(os.path.join(racine, name), exist_ok=True)
            with open(os.path.join(racine, name, "__manifest__.py"), "w", encoding="utf-8") as f:
                f.write(f"{{'name': '{name}', 'version': '{version}'}}\n")
        manifest("base", "1.3")
        manifest("event", "1.9")
        manifest("rlq_survey_report", "1.97.0")
        conf = self.path("odoo.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write(f"[options]\naddons_path = {racine},{self.d}/absent\n")

        class Faux:
            state = [{"nom": "base", "etat": "installed", "version": "18.0.1.3", "auteur": "Odoo S.A."},
                    {"nom": "event", "etat": "installed", "version": "18.0.1.9", "auteur": "Odoo S.A."},
                    {"nom": "rlq_survey_report", "etat": "installed", "version": "18.0.1.96.0", "auteur": "Rencontres Linux", "maj": "2026-10-14 09:12", "cree": "2026-10-01"},
                    {"nom": "perdu", "etat": "installed", "version": "18.0.1.0", "auteur": "Autre", "maj": "2026-09-02 16:40", "cree": "2026-09-02"},
                    {"nom": "web_x", "etat": "to upgrade", "version": "18.0.1.0", "auteur": "Odoo S.A."}]

            @staticmethod
            def modules_etat(database):
                return Faux.state if database == "b1" else None
        text = "\n".join(ANSI.sub("", l) for l in live.check_modules(Faux, conf, ["b1", "b2"]))
        self.assertIn("addons_path : dossiers introuvables", T(text))
        self.assertIn("Modules d'Odoo (base b1) : 5 installés · série 18.0", T(text))
        self.assertIn("⚠ à regarder", T(text))
        self.assertIn("2 INTROUVABLE(S) sur le disque : perdu, web_x", T(text))
        self.assertIn("rlq_survey_report installé 18.0.1.96.0 ≠ disque 18.0.1.97.0", T(text))
        self.assertIn("web_x (to upgrade)", T(text))
        self.assertIn("Hors Odoo S.A. : 2 modules", T(text))                                       # 1.66 : compte + 5 derniers en colonnes, plus la longue liste
        self.assertIn("touche M ou --modules", T(text))
        self.assertIn("Modules rlq* : 1 installés, avec leur version", T(text))
        self.assertIn("Derniers modifiés parmi les autres (heure locale) :", T(text))
        self.assertRegex(T(text), r"rlq_survey_report\s+18\.0\.1\.96\.0\s+2026-10-14 09:12")
        self.assertRegex(T(text), r"perdu\s+18\.0\.1\.0\s+2026-09-02 16:40")
        self.assertLess(text.index("rlq_survey_report  "), text.index("perdu  "))                # les rlq* d'abord, puis les autres
        self.assertIn("Modules d'Odoo : lecture de PostgreSQL impossible pour 1 bases (root requis, ou base inaccessible) : b2", T(text))      # bases illisibles : UNE ligne
        self.assertEqual(T(text).count("Modules d'Odoo (base"), 1)
        self.assertNotIn("Modules hors Odoo S.A. (version installée)", T(text))
        live.COLOR = True
        raw = "\n".join(live.check_modules(Faux, conf, ["b1"]))
        self.assertIn(live.color_code("1;31", "✖ 2 INTROUVABLE(S) sur le disque : "), T(raw))
        self.assertIn(live.color_code("1;36", "5"), raw)
        live.COLOR = False
        Faux.state = [m for m in Faux.state if m["nom"] in ("base", "event")]
        with open(conf, "w", encoding="utf-8") as f:
            f.write(f"[options]\naddons_path = {racine}\n")
        text = "\n".join(ANSI.sub("", l) for l in live.check_modules(Faux, conf, ["b1"]))
        self.assertIn("✔ tous présents, à la version installée", T(text))
        self.assertEqual(len([l for l in text.splitlines() if l.strip()]), 1)                      # tout va bien : une seule ligne
        self.assertEqual(live.check_modules(None, conf, ["b1"]), [])

    def test_modules_rlq_toujours_affiches_meme_plus_anciens_que_les_autres(self):
        """Démarrage : les rlq* sont listés (avec leur version) AVANT les derniers modules modifiés, même s'ils sont plus vieux que 5 modules d'OCA ; absents : une ligne le dit."""
        live = self.module_live()
        self.timezone("UTC")
        racine = os.path.join(self.d, "addons")
        os.makedirs(os.path.join(racine, "base"))
        with open(os.path.join(racine, "base", "__manifest__.py"), "w", encoding="utf-8") as f:
            f.write("{'name': 'base', 'version': '1.3'}\n")
        conf = self.path("odoo2.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write(f"[options]\naddons_path = {racine}\n")
        oca = [{"nom": f"oca_{i}", "etat": "installed", "version": "18.0.1.0.0", "auteur": "OCA", "maj": f"2026-10-14 22:4{i}", "cree": "2026-10-14"} for i in range(6)]
        database = {"nom": "base", "etat": "installed", "version": "18.0.1.3", "auteur": "Odoo S.A."}
        rlq = {"nom": "rlq_survey_report", "etat": "installed", "version": "18.0.1.90.0", "auteur": "Rencontres Linux Québec", "maj": "2026-09-01 10:00", "cree": "2026-09-01"}

        def output(state):
            class Faux:
                @staticmethod
                def modules_etat(base_):
                    return state
            return "\n".join(ANSI.sub("", l) for l in live.check_modules(Faux, conf, ["b"]))
        text = output([database, rlq] + oca)
        self.assertRegex(T(text), r"rlq_survey_report\s+18\.0\.1\.90\.0\s+2026-09-01 10:00")
        self.assertLess(text.index("rlq_survey_report"), text.index("oca_5"))
        self.assertNotIn("oca_0", T(text).split("Derniers modifiés parmi les autres")[1])       # 5 derniers modules seulement parmi les autres
        without = output([database] + oca)
        self.assertIn("Aucun module rlq* installé dans cette base", T(without))

    def test_niveaux_du_tableau_de_bord_de_1_a_9(self):
        """1.28 : le tableau de bord a 9 niveaux, chacun ajoute au précédent ; le 9 montre tout ; --level et les touches 1 à 9 choisissent le niveau."""
        live = self.module_live()
        st = live.Stats(5.0)
        for path, code in (("/event", 200), ("/event", 200), ("/boum", 500), ("/introuvable", 404)):
            L = live.Line(werkzeug("8.8.8.8", path, code))
            L.instant = time.time()
            st.ajouter(L, {"8.8.8.8": ("ok.exemple.org", [], False, None)}, None)

        def text(n):
            return " ".join(ANSI.sub("", " ".join(st.summary(["  Efficacité du programme"], (), "Test", n))).split())
        self.assertEqual(live.LEVEL_MAX, 9)
        self.assertIn("Santé :", T(text(1)))
        self.assertIn("Erreurs HTTP 5xx", T(text(1)))                       # what goes wrong is visible from level 1
        self.assertNotIn("Activité :", T(text(1)))
        self.assertIn("Activité : 4 requêtes", T(text(2)))
        self.assertNotIn("Activité :", T(text(6)))                           # one-line activity is replaced by the detail
        self.assertNotIn("Adresses les plus actives", T(text(4)))
        self.assertIn("Adresses les plus actives", T(text(5)))
        self.assertNotIn("Codes HTTP", T(text(6)))
        self.assertIn("Codes HTTP", T(text(7)))
        self.assertNotIn("Top 10 des URLs", T(text(7)))
        self.assertIn("Top 10 des URLs", T(text(8)))
        self.assertNotIn("Efficacité du programme", T(text(8)))
        self.assertIn("Efficacité du programme", T(text(9)))
        self.assertIn("Requêtes suspectes : aucune", T(text(9)))
        self.assertNotIn("Requêtes suspectes : aucune", T(text(8)))          # the "none" only at level 9
        self.assertIn("Niveau 5 sur 9", T(text(5)))
        self.assertNotIn("Niveau", T(text(9)))
        longueurs = [len(text(n)) for n in range(1, 10)]
        self.assertEqual(longueurs[0], min(longueurs))
        self.assertEqual(longueurs[8], max(longueurs))

    def test_option_level_et_touches_1_a_9(self):
        """1.28 : --level N (1 à 9, refus des autres valeurs) ; touche 1 à 9 : tableau de bord à ce niveau."""
        r = subprocess.run(["python3", self.prog, "--level", "10", "--no-follow"], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--level doit être compris entre 1 et 9", r.stderr)
        self.journal_tableau()
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--level", "3"],
                                       [(b"/event", b"\x07", 0.8), (b"Niveau 3 sur 9", b"1", 0.8), (b"Niveau 1 sur 9", b"\x03", 0.5)], timeout=60)
        self.assertEqual(envoyees, 3, text)
        self.assertIn("Niveau 3 sur 9", text)
        self.assertIn("Niveau 1 sur 9", text)

    def test_alerte_de_sante_automatique_avec_detail(self):
        """[9] --health MIN : s'il y a un problème, la santé et le détail s'affichent dans le flux ; sans problème : rien."""
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/boum", 500), werkzeug(DNS, "/boum", 500), werkzeug(DNS, "/boum", 500)], after="sleep 4")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--health", "0.02", "--no-keys"])
        self.assertRegex(T(out), r"Alerte santé \(app-log-live\.py v[\d.]+\) : depuis")
        r = " ".join(out.split("Alerte santé")[1].split())
        self.assertIn("⚠ Erreurs HTTP 5xx : 3 URL : /boum ×3", T(r))
        self.assertEqual(out.count("Alerte santé"), 1, "une seule alerte : la période suivante est sans problème")
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/ok")], after="sleep 3")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--health", "0.02", "--no-keys"])
        self.assertNotIn("Alerte santé", T(out))
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--health", "0", "--no-keys"])
        self.assertNotIn("Alerte santé", T(out))

    def test_lancement_filtre_a_son_propre_journal_quotidien(self):
        """1.47 : avec --only, le journal quotidien est app-log-live-YYYY-MM-DD-filter.log : deux lancements en même temps (l'un complet, l'autre filtré) ne mélangent pas leurs lignes ;
        la purge des vieux jours inclut ces fichiers."""
        folder = os.path.join(self.d, "journaux")
        os.makedirs(folder)
        vieux = os.path.join(folder, "app-log-live-2020-01-01-filtre.log")
        with open(vieux, "w") as h:
            h.write("x\n")
        self.journal([werkzeug(PERSONNE, "/histoire"), werkzeug(DNS, "/event/jpo", 200), werkzeug(DNS, "/autre", 200)])
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--no-keys", "--log-dir", folder, "--only", "/event/jpo"])
        self.assertEqual(rc, 0, err)
        day = datetime.date.today().isoformat()
        self.assertIn("app-log-live-YYYY-MM-DD-filter.log", T(err))
        self.assertTrue(os.path.isfile(os.path.join(folder, f"app-log-live-{day}-filter.log")), os.listdir(folder))
        self.assertFalse(os.path.exists(os.path.join(folder, f"app-log-live-{day}.log")))
        self.assertFalse(os.path.exists(vieux), "purgé comme les autres journaux")

    def test_journal_quotidien_avec_couleurs(self):
        """[10] Le direct est aussi écrit, AVEC ses séquences de couleur, dans un fichier par jour (droits 600) ; pas l'historique du départ ; purge des vieux jours ;
        --no-log-file et --no-follow : aucun fichier."""
        folder = os.path.join(self.d, "journaux")
        os.makedirs(folder)
        vieux, recent = os.path.join(folder, "app-log-live-2020-01-01.log"), os.path.join(folder, "app-log-live-2999-01-01.log")
        autre = os.path.join(folder, "autre-programme-2020-01-01.log")
        for f in (vieux, recent, autre):
            with open(f, "w") as h:
                h.write("x\n")
        self.journal([werkzeug(PERSONNE, "/histoire-1"), werkzeug(PERSONNE, "/histoire-2"), werkzeug(DNS, "/direct-1", 500), werkzeug(DNS, "/direct-2", 404)])
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "2", "--no-keys", "--log-dir", folder])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("\x1b[", T(out))                                                       # the screen (a pipe) stays without color
        self.assertIn("Journal quotidien (couleurs conservées", T(err))
        day = datetime.date.today().isoformat()
        file_path = os.path.join(folder, f"app-log-live-{day}.log")
        self.assertTrue(os.path.isfile(file_path), os.listdir(folder))
        self.assertEqual(T(oct(os.stat(file_path).st_mode & 0o777)), "0o600")
        with open(file_path, encoding="utf-8") as f:
            contenu = f.read()
        self.assertIn("\x1b[", T(contenu))                                                      # colors kept (less -R)
        self.assertRegex(T(contenu), r"\x1b\[[0-9;]*m/direct-1\x1b\[0m")                           # le URL en erreur 5xx est en couleur
        without = ANSI.sub("", contenu)
        self.assertIn("/direct-1", T(without))
        self.assertIn("/direct-2", T(without))
        self.assertNotIn("/histoire-1", T(without))                                                 # start history: not copied
        self.assertNotIn("/histoire-2", T(without))
        self.assertIn("journal du " + day, without)
        self.assertFalse(os.path.exists(vieux), "plus de 30 jours : effacé")
        self.assertTrue(os.path.exists(recent) and os.path.exists(autre), "ni un jour récent ni le fichier d'un autre programme")
        # A second start APPENDS to the same file of the day
        self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "2", "--no-keys", "--log-dir", folder])
        with open(file_path, encoding="utf-8") as f:
            self.assertEqual(ANSI.sub("", f.read()).count("/direct-1"), 2)
        # --log-keep-days 0 : jamais de purge ; --no-log-file et --no-follow : rien
        with open(vieux, "w") as h:
            h.write("x\n")
        self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "2", "--no-keys", "--log-dir", folder, "--log-keep-days", "0"])
        self.assertTrue(os.path.exists(vieux))
        os.unlink(file_path)
        self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "2", "--no-keys", "--log-dir", folder, "--no-log-file"])
        self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "2", "--no-follow", "--log-dir", folder])
        self.assertFalse(os.path.exists(file_path))
        # Test default: APP_LOG_LIVE_LOG_DIR=off
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "2", "--no-keys"])
        self.assertNotIn("Journal quotidien", T(err))
        self.assertFalse(os.path.exists(file_path))

    # --- banned addresses, slow requests, filters, summary ---
    def bannissements(self, fail2ban_banned=None, ipset_v4=None, fail2ban_status=None):
        """Simule fail2ban-client et ipset (sorties réelles de leurs versions courantes) ; les appels sont journalisés dans bans.log."""
        d = self.d
        f2b = ["echo \"$@\" >> " + d + "/bans.log"]
        if fail2ban_banned is not None:
            f2b.append(f"case \"$*\" in banned) echo \"{fail2ban_banned}\"; exit 0;; esac")
        if fail2ban_status is not None:
            f2b.append("case \"$*\" in status) printf 'Status\\n|- Number of jail:\\t2\\n`- Jail list:\\tsshd, nginx-blocked-probes\\n'; exit 0;; "
                       + "\"status sshd\") printf 'Status for the jail: sshd\\n`- Actions\\n   |- Banned IP list:\\t93.184.216.34 100.64.0.7\\n'; exit 0;; "
                       + "\"status nginx-blocked-probes\") printf '`- Banned IP list:\\t2001:db8::5\\n'; exit 0;; esac")
        f2b.append("exit 1")
        self.mock("fail2ban-client", "; ".join(f2b))
        if ipset_v4 is None:
            self.mock("ipset", "echo \"$@\" >> " + d + "/bans.log; exit 1")
        else:
            self.write("ipset-v4.txt", ipset_v4)
            self.mock("ipset", "echo \"$@\" >> " + d + "/bans.log; case \"$*\" in \"list crowdsec-blocklist-v4\") cat " + d + "/ipset-v4.txt;; *) exit 1;; esac")

    IPSET_V4 = ("Name: crowdsec-blocklist-v4\nType: hash:net\nRevision: 7\nHeader: family inet hashsize 1024 maxelem 65536 counters\nSize in memory: 1000\n"
                "References: 1\nNumber of entries: 3\nMembers:\n11.42.88.181 packets 5 bytes 300\n198.51.100.0/24 packets 0 bytes 0\n"
                "198.51.100.77 nomatch packets 0 bytes 0\n")

    def test_adresses_bannies_etiquette_fail2ban_et_crowdsec(self):
        """Une ligne dont l'adresse est actuellement bannie (fail2ban, ipsets CrowdSec) porte [banni : source] ; les entrées « nomatch » sont des exceptions ;
        jamais pour la liste blanche ; une plage CrowdSec couvre ses adresses ; IPv6 aussi."""
        v6 = "2001:db8::5"
        self.bannissements(fail2ban_banned=f"[{{'sshd': ['{DNS}', '{self.equipe_ip}'], 'nginx-blocked-probes': ['{v6}']}}, {{'autre': []}}]", ipset_v4=self.IPSET_V4)
        self.journal([werkzeug(DNS, "/a"), werkzeug(ISP, "/b"), werkzeug("198.51.100.9", "/c"), werkzeug("198.51.100.77", "/d"), werkzeug(PERSONNE, "/e"),
                      werkzeug(self.equipe_ip, "/f"), werkzeug(v6, "/g")])
        rc, out, err = self.lancer("--no-presence")
        l = out.splitlines()
        self.assertTrue(l[0].endswith('[banni : fail2ban]'), l[0])
        self.assertTrue(l[1].endswith('[banni : CrowdSec]'), l[1])                      # adresse seule de l'ipset
        self.assertTrue(l[2].endswith('[banni : CrowdSec]'), l[2])                      # dans la plage 198.51.100.0/24
        self.assertNotIn("banned", T(l[3]))                                                 # "nomatch": ipset exception
        self.assertNotIn("banned", T(l[4]))                                                 # adresse non bannie
        self.assertNotIn("banned", T(l[5]))                                                 # white list: never, even if fail2ban contains it
        self.assertTrue(l[6].endswith('[banni : fail2ban]'), l[6])                      # IPv6
        self.assertIn("Adresses bannies : fail2ban 3 adresses, CrowdSec 2 entrées", err)
        self.assertIn("\x1b[1;91m[banni : fail2ban]\x1b[0m", self.en_couleur())

    def test_bannis_repli_sur_status_no_banned_et_sources_illisibles(self):
        self.bannissements(fail2ban_status=True)                                        # unknown "banned" (old fail2ban): "status" then "status JAIL"
        self.journal([werkzeug(DNS, "/a"), werkzeug("2001:db8::5", "/b"), werkzeug(PERSONNE, "/c")])
        rc, out, err = self.lancer("--no-presence")
        l = out.splitlines()
        self.assertTrue(l[0].endswith("[banni : fail2ban]"), l[0])
        self.assertTrue(l[1].endswith("[banni : fail2ban]"), l[1])
        self.assertNotIn("banned", T(l[2]))
        self.assertIn("Adresses bannies : fail2ban 3 adresses", err)
        self.assertNotIn("CrowdSec", err)                                               # ipset illisible : source absente
        os.remove(os.path.join(self.d, "bans.log"))
        rc, out, err = self.lancer("--no-presence", "--no-banned")
        self.assertNotIn("banned", out + err)
        self.assertFalse(os.path.exists(os.path.join(self.d, "bans.log")), "--no-banned : ni fail2ban-client ni ipset ne sont appelés")
        self.mock("fail2ban-client", "exit 1")
        self.mock("ipset", "exit 1")
        rc, out, err = self.lancer("--no-presence")
        self.assertEqual(rc, 0, err)
        self.assertIn("Adresses bannies : aucune source lisible (fail2ban-client et ipset absents, ou root requis)", err)
        self.assertNotIn("banni :", out)

    def lente(self, ip, url, sql, py, code=200):
        return werkzeug(ip, url, code).replace("0.046 0.426", f"{sql} {py}")

    def test_port_ssh_lu_dans_sshd_et_non_fixe_a_22(self):
        """1.81 : « Connectés en SSH » compte les connexions sur le VRAI port de sshd (ss -p, puis sshd -T, puis sshd_config, sinon 22), pas sur le port 22 fixe."""
        live = self.module_live()
        appels = []

        def faux_lancer(cmd, delay=10):
            appels.append(cmd)
            if cmd[:2] == ["ss", "-Htlnp"]:
                return 0, ('LISTEN 0 128 0.0.0.0:2222 0.0.0.0:* users:(("sshd",pid=7,fd=3))\nLISTEN 0 128 [::]:2222 [::]:* users:(("sshd",pid=7,fd=4))\n'
                           'LISTEN 0 128 127.0.0.1:8069 0.0.0.0:* users:(("python3",pid=9,fd=5))\n')
            if cmd[0] == "ss":                                                             # established connections: 2 on the filtered port
                return 0, "ESTAB 0 0 10.0.0.1:2222 1.2.3.4:5555\nESTAB 0 0 10.0.0.1:2222 5.6.7.8:6666\n"
            if cmd[0] == "who":
                return 0, ""
            return 1, ""
        live.SSH_PORTS_CACHE.update(when=0.0, ports=None)
        with unittest.mock.patch.object(live, "lancer", faux_lancer):
            self.assertEqual(live.ssh_ports(), [2222])                                      # IPv4 et IPv6 : un seul port, sans port 8069 (pas sshd)
            texte = T(" ".join(live.logged_in_lines(None)))
        filtre = next(c for c in appels if c[0] == "ss" and "established" in c)
        self.assertEqual(filtre[-1], "( sport = :2222 )")
        self.assertIn("Connectés en SSH : 0", texte)
        self.assertIn("connexions TCP établies : 2 (port SSH 2222)", texte)
        self.assertNotIn("port 22:", texte)
        # Deux ports (Port 22 et Port 2222) ; sans ss -p : sshd -T
        live.SSH_PORTS_CACHE.update(when=0.0, ports=None)

        def faux_lancer2(cmd, delay=10):
            if cmd[0] == "ss":
                return 1, ""
            if cmd[0] == "sshd":
                return 0, "port 22\nport 2222\nlistenaddress 0.0.0.0\n"
            return 1, ""
        with unittest.mock.patch.object(live, "lancer", faux_lancer2):
            self.assertEqual(live.ssh_ports(), [22, 2222])
        # Ni ss ni sshd : fichier de configuration, sinon 22
        live.SSH_PORTS_CACHE.update(when=0.0, ports=None)
        with unittest.mock.patch.object(live, "lancer", lambda cmd, delay=10: (1, "")), \
                unittest.mock.patch.object(live.glob, "glob", lambda pattern: []), \
                unittest.mock.patch("builtins.open", unittest.mock.mock_open(read_data="# Port 22\nPort 2022\n")):
            self.assertEqual(live.ssh_ports(), [2022])
        live.SSH_PORTS_CACHE.update(when=0.0, ports=None)
        with unittest.mock.patch.object(live, "lancer", lambda cmd, delay=10: (1, "")), unittest.mock.patch.object(live.glob, "glob", lambda pattern: []), \
                unittest.mock.patch("builtins.open", side_effect=OSError):
            self.assertEqual(live.ssh_ports(), [22])
        live.SSH_PORTS_CACHE.update(when=0.0, ports=None)

    def test_causes_des_requetes_lentes_dans_le_resume(self):
        """1.32 : le résumé explique les requêtes lentes : où va le temps (SQL / Python), pages regroupées (nombres normalisés) avec cause probable, adresses, grappe."""
        self.journal([self.lente(DNS, "/web/dataset/call_kw/document.page/web_read", "7.0", "0.5"), self.lente(DNS, "/web/dataset/call_kw/document.page/web_read", "6.0", "0.5"),
                      self.lente(PERSONNE, "/event/journee-2026-125/registration/confirm", "0.2", "5.5"),
                      self.lente(PERSONNE, "/event/journee-2026-126/registration/confirm", "0.2", "6.5")])
        rc, out, err = self.lancer("--no-presence", "--summary")
        r = " ".join(out[out.index("──── Résumé"):].split())
        self.assertIn("Où va le temps : SQL", T(r))
        self.assertRegex(T(r), r"/web/dataset/call_kw/document\.page/web_read ×2 — 14 s en tout, la pire 7\.5 s : requêtes SQL longues")
        self.assertRegex(T(r), r"/event/journee-N-N/registration/confirm ×2 — 12 s en tout, la pire 6\.7 s : temps Python")
        self.assertIn("Adresses : ", T(r))
        self.assertIn("4 requêtes lentes dans la même minute", T(r))

    def test_requetes_lentes_surlignees_avec_leur_duree_et_slow(self):
        """SQL + Python >= 5 s (--slow) : les deux durées en orange gras et le total ajouté ; à 3 fois le seuil : rouge gras ; sous le seuil : rien."""
        self.journal([self.lente(DNS, "/ok", "0.5", "4.4"), self.lente(DNS, "/lente", "2.100", "3.400"), self.lente(DNS, "/tres", "4.0", "11.0"),
                      self.lente(DNS, "/rapide", "0.001", "0.002")])
        rc, out, err = self.lancer("--no-presence")
        l = out.splitlines()
        self.assertNotIn("lente :", T(l[0]))                                               # 4.9 s : sous le seuil
        self.assertTrue(l[1].endswith("← lente : 5.5 s") and " 2.100  3.400  " in l[1], l[1])
        self.assertTrue(l[2].endswith("← lente : 15.0 s") and "   4.0   11.0  " in l[2], l[2])
        self.assertNotIn("lente :", T(l[3]))
        text = self.en_couleur()
        self.assertRegex(text, r"\x1b\[33m2\.100\x1b\[0m +\x1b\[33m3\.400\x1b\[0m")        # 1.134: feu tricolore : 5.5 s = rouge (3 s et plus)
        self.assertRegex(text, r"\x1b\[1;31m4\.0\x1b\[0m +\x1b\[1;31m11\.0\x1b\[0m")                               # rouge gras : 15 s = 3 fois le seuil
        self.assertNotIn("lente :", self.lancer("--no-presence", "--slow", "0")[1])     # disabled
        self.assertEqual(self.lancer("--no-presence", "--slow", "20")[1].count("lente :"), 0)
        self.assertEqual(self.lancer("--no-presence", "--slow", "1")[1].count("lente :"), 3)

    def journal_mixte(self):
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/wp-login.php", 404), werkzeug(DNS, "/web/login"), werkzeug(DNS, "/.env", 404),
                      odoo("INFO", "base", "odoo.addons.mail.models.mail_mail", "Courriel envoyé à Alice"),
                      odoo("ERROR", "base", "odoo.addons.base.models.ir_mail_server", "Échec boum"),
                      f"{ts()} odoo18 odoo[1]: Traceback (most recent call last):", f'{ts()} odoo18 odoo[1]:   File "/opt/odoo/x.py", line 1, in boum',
                      f"{ts()} odoo18 odoo[1]: ValueError: boum",
                      odoo("ERROR", "base", "odoo.addons.base.models.autre", "Autre échec"),
                      f"{ts()} odoo18 odoo[1]: Traceback (most recent call last):", f"{ts()} odoo18 odoo[1]: KeyError: autre"])

    def test_only_filtre_sur_le_texte_affiche_nom_adresse_url_module_et_suites_de_trace(self):
        self.journal_mixte()
        def lines(*args):
            return self.lancer("--no-presence", *args)[1].splitlines()
        self.assertEqual(len(lines()), 12)
        l = lines("--only", "ÉTIENNE DUPONT")                                          # the name DISPLAYED, regardless of case
        self.assertEqual(len(l), 1)
        self.assertIn("/event", T(l[0]))
        self.assertEqual(len(lines("--only", DNS)), 3)                                  # l'adresse (colonne)
        self.assertEqual(len(lines("--only", "SRV.EXEMPLE.ORG")), 3)                    # le nom DNS
        self.assertEqual(len(lines("--only", "/web/login")), 1)                         # le URL
        self.assertEqual(len(lines("--only", "mail_mail")), 1)                          # le module (logger)
        self.assertEqual(len(lines("--only", "mail_mail", "--only", "/event")), 2)      # repeatable: one OR the other
        trace = lines("--only", "échec boum")                                           # an error entry carries its trace, not that of the next entry
        self.assertEqual(len(trace), 4, trace)
        self.assertIn("ValueError: boum", T(trace[3]))
        self.assertNotIn("KeyError", T(" ".join(trace)))
        self.assertEqual(lines("--only", "n'existe-pas"), [])

    def test_suspect_ne_garde_que_les_requetes_suspectes(self):
        self.journal_mixte()
        l = self.lancer("--no-presence", "--suspect")[1].splitlines()
        self.assertEqual(len(l), 2, l)
        self.assertIn("/wp-login.php", l[0])
        self.assertIn("/.env", l[1])
        l = self.lancer("--no-presence", "--suspect", "--only", ".env")[1].splitlines()      # les deux filtres s'ajoutent (ET)
        self.assertEqual(len(l), 1)
        self.assertIn("/.env", l[0])

    def journal_resume(self, after="true"):
        self.journal([werkzeug(DNS, "/wp-login.php", 404), werkzeug(DNS, "/wp-login.php", 404), werkzeug(DNS, "/.env", 200), werkzeug(DNS, "/boum", 500),
                      werkzeug(DNS, "/absent", 404), self.lente(DNS, "/lente", "2.0", "10.0"), werkzeug(PERSONNE, "/event"), werkzeug(PERSONNE, "/event")],
                     after=after)

    def faux_audit_recidive(self, verdict="bannissement justifié", bans=3):
        faux = os.path.join(os.path.dirname(self.prog), "nginx-log-audit.sh")
        with open(faux, "w") as f:
            f.write(f'#!/usr/bin/env bash\necho "$@" >> {self.d}/ban.log\ncase "$1" in --evidence)\n'
                    f'  echo "    Pour le bannissement :"; echo "      + récidive : {bans} bannissements temporaires par fail2ban (nginx-botsearch)"\n'
                    f'  echo "    Verdict : {verdict} (aucune raison contraire trouvée)." ;;\n--ban) echo "Règle ajoutée" ;;\nesac\nexit 0\n')
        os.chmod(faux, 0o755)

    def test_adresse_bannie_souvent_proposee_avec_delai(self):
        """1.19 : adresse à requêtes suspectes, bannie ≥ 2 fois (fail2ban) et verdict « bannissement justifié » : question avec délai de 10 s ; oui → --ban IP --yes ; sans réponse : on continue."""
        self.faux_audit_recidive()
        self.journal([werkzeug(DNS, "/wp-login.php", 404), werkzeug(DNS, "/.env", 404)], after="sleep 40")
        sequence = [(b"Bannir " + DNS.encode() + b" maintenant", b"o\r", 0.3), (b"banni", b"\x03", 0.5)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "5"], sequence, timeout=60)
        self.assertEqual(envoyees, 2, text)
        t = " ".join(text.split())
        self.assertIn("Adresse bannie souvent : 3 bannissements fail2ban — verdict : bannissement justifié", T(t))
        journal = open(os.path.join(self.d, "ban.log")).read()
        self.assertIn(f"--evidence {DNS}", journal)
        self.assertIn(f"--ban {DNS} --yes", journal)

    def test_adresse_bannie_souvent_sans_reponse_ou_verdict_different_ou_option(self):
        """Sans réponse en 10 s : le suivi continue, rien n'est banni ; verdict « à examiner » ou une seule fois : aucune question ; --no-ban-prompt : aucune enquête."""
        self.faux_audit_recidive()
        self.journal([werkzeug(DNS, "/wp-login.php", 404)], after="sleep 40")
        sequence = [(b"Pas de r\xc3\xa9ponse en 10 s", b"\x03", 0.5)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "5"], sequence, timeout=70)
        self.assertEqual(envoyees, 1, text)
        self.assertNotIn("--ban", open(os.path.join(self.d, "ban.log")).read())
        for verdict, bans, extra in (("à examiner", 3, []), ("bannissement justifié", 1, []), ("bannissement justifié", 3, ["--no-ban-prompt"])):
            os.remove(os.path.join(self.d, "ban.log"))
            self.faux_audit_recidive(verdict, bans)
            self.journal([werkzeug(DNS, "/wp-login.php", 404)], after="sleep 8")
            sequence = [(b"/wp-login.php", b"", 0.1)]
            text, _ = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "5", *extra], sequence, timeout=14)
            self.assertNotIn("Adresse bannie souvent", text, (verdict, bans, extra))
            if extra:
                self.assertFalse(os.path.exists(os.path.join(self.d, "ban.log")), "--no-ban-prompt : aucune enquête")

    def test_ctrl_c_demande_confirmation_puis_detail_des_erreurs(self):
        """1.18 : Ctrl-C demande « Quitter ? » (Non : le suivi continue) ; le résumé porte la version ; s'il y a des erreurs, « Plus de détails ? » lance app-log-check.py --errors-only."""
        faux = os.path.join(os.path.dirname(self.prog), "app-log-check.py")
        with open(faux, "w") as f:
            f.write("import sys\nprint('DETAIL-ERREURS', *sys.argv[1:])\n")
        self.journal([werkzeug(PERSONNE, "/event"), odoo("ERROR", "base", "odoo.http", "Exception during request handling.")], after="sleep 25")
        sequence = [(b"Exception during", b"\x03", 0.5), (b"Quitter app-log-live.py ?", b"n\r", 0.2), (b"Le suivi continue", b"\x03", 0.5),
                    (b"Quitter app-log-live.py ?", b"o\r", 1.0), (b"Plus de d\xc3\xa9tails sur les erreurs", b"o\r", 0.2), (b"DETAIL-ERREURS", b"", 0.1)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "5"], sequence, timeout=60)
        self.assertEqual(envoyees, 6, text)
        self.assertIn("Le suivi continue.", text)
        self.assertRegex(text, r"Résumé de la session \(app-log-live\.py v1\.\d+")
        self.assertIn("1 erreurs d'Odoo, 0 courriels en échec", text)
        self.assertIn("DETAIL-ERREURS --errors-only --full-trace --last 1", text)

    def test_resume_de_la_session_avec_summary_et_filtres(self):
        self.bannissements(fail2ban_banned=f"[{{'sshd': ['{DNS}']}}]")
        self.journal_resume()
        rc, out, err = self.lancer("--no-presence", "--summary")
        r = " ".join(out[out.index("──── Résumé"):].split())
        self.assertRegex(r, r"──── Résumé de la session \(app-log-live\.py v1\.\d+\.\d{8}\.\d{6}\) : depuis \d{4}-\d\d-\d\d \d\d:\d\d:\d\d pendant \d\d:\d\d:\d\d · 8 lignes affichées · 8 requêtes ────")
        self.assertIn(f"Adresses les plus actives : srv.exemple.org [{DNS}] ×6 ; Étienne Dupont [{PERSONNE}] ×2", r)
        self.assertIn("Requêtes suspectes 3 de 1 adresses — /wp-login.php ×2 ; /.env ×1", r)
        self.assertIn(f"par adresse : srv.exemple.org [{DNS}] ×3 [banni : fail2ban]", r)
        self.assertIn("Erreurs 5xx (critiques) 1 — /boum ×1", r)
        self.assertIn("Erreurs 4xx (avertissements) 3 — /wp-login.php ×2 ; /absent ×1", r)
        self.assertIn(f"Requêtes lentes (≥ 5 s) 1 — la plus lente : 12.0 s /lente (srv.exemple.org [{DNS}])", r)
        self.assertIn(f"Adresses bannies vues : 1 — srv.exemple.org [{DNS}] (fail2ban)", r)
        out2 = self.lancer("--no-presence")[1]
        self.assertNotIn("Résumé de la session", out2, "sans --summary : jamais au bout d'un --no-follow (le résumé est pour Ctrl-C)")
        r = " ".join(self.lancer("--no-presence", "--summary", "--suspect")[1].split())              # the summary only counts DISPLAYED lines
        self.assertIn("3 lignes affichées · 3 requêtes", r)
        self.assertRegex(r, r": depuis \d{4}-\d\d-\d\d \d\d:\d\d:\d\d pendant \d\d:\d\d:\d\d · 3 ligne", "la période des statistiques : début et durée")
        self.assertIn("Erreurs 5xx (critiques) : aucune.", r)
        self.assertIn("Requêtes lentes (≥ 5 s) : aucune.", r)
        r = " ".join(self.lancer("--no-presence", "--summary", "--only", "zzz")[1].split())
        self.assertIn("0 lignes affichées", r)
        self.assertIn("Aucune requête dans les lignes affichées.", r)

    def test_ctrl_c_affiche_le_resume_de_la_session_puis_s_arrete_proprement(self):
        self.journal_resume("sleep 60")                                                 # the stream stays open (sleep 60): only Ctrl-C stops it
        text, _ = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned"], [(b"/event", b"\x03", 0.6)], timeout=40)
        self.assertNotIn("Traceback", text, text)
        r = " ".join(text.split())
        self.assertIn("Résumé de la session", T(r))
        self.assertIn("8 requêtes", T(r))
        self.assertIn("Requêtes suspectes 3 de 1 adresses", T(r))
        self.assertIn("Interrompu (Ctrl-C).", T(r))

    # --- cache permanent des adresses -------------------------------------------------------------------------------
    def avec_cache(self, *args, cache=None):
        path = cache or os.path.join(self.d, "ip-cache.sqlite")
        return self.lancer(*args, env_extra={"NGINX_TOOLS_IP_CACHE": path})

    def account(self, name):
        try:
            with open(os.path.join(self.d, name)) as f:
                return len(f.read().splitlines())
        except OSError:
            return 0

    def test_cache_permanent_une_adresse_n_est_cherchee_qu_une_fois(self):
        """Premier passage : DNS, propriétaire du bloc (RDAP) et pays sont cherchés puis mémorisés ; deuxième passage : AUCUNE recherche (ni
        getent, ni curl, ni geoiplookup), même affichage, résultat immédiat."""
        self.geoip()
        self.journal([werkzeug(DNS), werkzeug(ISP), werkzeug(DNS, "/encore")])
        rc, out1, err1 = self.avec_cache("--no-presence", "--no-history")
        self.assertIn(f"Cache des adresses : {os.path.join(self.d, 'ip-cache.sqlite')} (0 adresses", T(err1))
        rc, out1, err1 = self.avec_cache("--no-presence", "--no-history")                 # 2nd pass to fix the reference state with the cache already filled
        getent, curl, geo = self.account("getent.log"), self.account("curl.log"), self.account("geoip.log")
        self.assertEqual(getent, 2, "un seul DNS par adresse au tout premier passage (deux adresses)")
        self.assertEqual(curl, 1, "un seul RDAP (l'adresse sans nom DNS)")
        rc, out2, err2 = self.avec_cache("--no-presence", "--no-history")
        self.assertEqual(out2, out1, "même affichage depuis le cache")
        self.assertEqual((self.account("getent.log"), self.account("curl.log"), self.account("geoip.log")), (getent, curl, geo), "aucune recherche au 2e passage")
        self.assertRegex(T(out2), rf"INFO US {DNS}\s+base werkzeug srv\.exemple\.org\s+")
        self.assertRegex(T(out2), rf"INFO CA {ISP}\s+base werkzeug Videotron Ltee \(org\)\s+")
        self.assertIn("(2 adresses", T(err2))

    def test_cache_no_cache_ne_lit_ni_n_ecrit(self):
        self.geoip()
        self.journal([werkzeug(DNS)])
        self.avec_cache("--no-presence", "--no-history")
        before = self.account("getent.log")
        rc, out, err = self.avec_cache("--no-presence", "--no-history", "--no-cache")
        self.assertEqual(self.account("getent.log"), before + 1, "--no-cache : le DNS est refait")
        self.assertNotIn("Cache des adresses : /", T(err))
        import sqlite3
        autre = os.path.join(self.d, "autre.sqlite")
        self.avec_cache("--no-presence", "--no-history", "--no-cache", cache=autre)
        self.assertFalse(os.path.exists(autre), "--no-cache n'écrit rien")
        self.assertIn("Cache des adresses : désactivé", self.lancer("--no-presence", "--no-history")[2])      # test default: off
        self.assertEqual(sqlite3.connect(os.path.join(self.d, "ip-cache.sqlite")).execute("SELECT COUNT(*) FROM ip").fetchone()[0], 1)

    def test_cache_aucun_nom_dns_passe_directement_a_rdap_et_no_isp_sans_requete(self):
        """Adresse sans nom DNS (réponse « aucun » du DNS) : mémorisée comme telle ; ensuite seul RDAP est interrogé, jamais le DNS. Avec
        --no-isp, le cache sert quand même (aucune requête extérieure)."""
        self.journal([werkzeug(ISP)])
        self.avec_cache("--no-presence", "--no-history", "--no-isp")                       # --no-isp : DNS seulement ; pas de RDAP
        self.assertEqual((self.account("getent.log"), self.account("curl.log")), (1, 0))
        out = self.avec_cache("--no-presence", "--no-history")[1]                          # RDAP requested, DNS never redone
        self.assertEqual((self.account("getent.log"), self.account("curl.log")), (1, 1))
        self.assertRegex(T(out), r"Videotron Ltee \(org\)")
        out = self.avec_cache("--no-presence", "--no-history", "--no-isp")[1]              # --no-isp but the cache knows the owner
        self.assertEqual((self.account("getent.log"), self.account("curl.log")), (1, 1), "aucune requête")
        self.assertRegex(T(out), r"Videotron Ltee \(org\)")

    def test_cache_perime_redemande_et_purge_des_adresses_oubliees(self):
        import sqlite3
        path = os.path.join(self.d, "ip-cache.sqlite")
        self.journal([werkzeug(DNS)])
        self.avec_cache("--no-presence", "--no-history")
        database = sqlite3.connect(path)
        database.execute("UPDATE ip SET ptr_t = ptr_t - ?", (31 * 86400.0,))                  # stale DNS name (30 days)
        database.execute("INSERT INTO ip (ip, ptr, ptr_t, vu1, vu2, n) VALUES ('198.51.100.250', 'vieux', 1.0, 1.0, 1.0, 1)")   # non revue depuis toujours
        database.commit()
        database.close()
        before = self.account("getent.log")
        rc, out, err = self.avec_cache("--no-presence", "--no-history")
        self.assertEqual(self.account("getent.log"), before + 1, "nom périmé : redemandé")
        self.assertIn("1 adresses non revues depuis 180 jours effacées", T(err))
        database = sqlite3.connect(path)
        self.assertEqual([r[0] for r in database.execute("SELECT ip FROM ip ORDER BY ip")], [DNS])
        database.close()
        # Cache inutilisable : le programme fonctionne sans lui
        with open(path, "wb") as f:
            f.write(b"pas une base" * 100)
        rc, out, err = self.avec_cache("--no-presence", "--no-history")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("Traceback", T(err))
        self.assertIn("Cache des adresses : inutilisable", T(err))
        self.assertIn("srv.exemple.org", T(out))

    def test_geoip_bin_recommande_au_demarrage(self):
        """[2] geoip-bin absent : rappel sur la sortie d'erreur (le pays de chaque adresse irait sur Internet) ; rien avec --no-isp ni s'il est là."""
        rc, out, err = self.lancer("--no-presence")
        self.assertIn("RECOMMANDÉ : geoip-bin absent — le pays de chaque adresse est cherché sur Internet (rdap.org), lentement.", err)
        self.assertIn("nginx-hardening.sh --update l'installe", err)
        self.assertNotIn("geoip-bin absent", self.lancer("--no-presence", "--no-isp")[2])
        self.geoip()
        self.assertNotIn("geoip-bin absent", self.lancer("--no-presence")[2])

    def test_verbose_affiche_chaque_commande_externe(self):
        rc, out, err = self.lancer("--verbose")
        self.assertIn("+ systemctl list-unit-files erplibre.service --no-legend", err)
        self.assertIn("+ journalctl --lines 50 --no-pager -u erplibre.service -o short-iso-precise", err)
        self.assertIn("+ journalctl -u erplibre.service -q --no-pager -o short-iso -g 'Login successful for'", err)
        self.assertIn("+ getent hosts 93.184.216.34", err)
        self.assertNotIn("+ ", self.lancer()[2])

    def test_une_seule_recherche_par_adresse(self):
        self.journal([werkzeug(DNS)] * 4 + [werkzeug(ISP)] * 3)
        rc, out, err = self.lancer("--lines", "300", "--no-history", "--no-presence")
        self.assertEqual(len(re.findall(r"werkzeug srv\.exemple\.org\s+H1\.1 \d+[ \d.-]*GET", out)), 4)
        self.assertEqual(len(re.findall(r"werkzeug Videotron Ltee \(org\)\s+H1\.1 \d+[ \d.-]*GET", out)), 3)
        with open(os.path.join(self.d, "getent.log")) as f:
            self.assertEqual(f.read().count(f"hosts {DNS}"), 1, "une seule recherche DNS par adresse")
        with open(os.path.join(self.d, "curl.log")) as f:
            requests = f.read()
        self.assertEqual(requests.count(f"rdap.org/ip/{ISP}"), 1, "une seule requête RDAP par adresse (fournisseur ET pays : le même appel)")
        self.assertEqual(requests.count(f"rdap.org/ip/{DNS}"), 1, "adresse avec nom DNS : une seule requête, pour son pays")
        with open(os.path.join(self.d, "journalctl.log")) as f:
            commands = f.read()
        self.assertIn("--lines 300", commands)
        self.assertNotIn("-g Login", T(commands), "--no-history : aucune lecture de l'historique des connexions")

    def test_no_isp_aucune_requete_exterieure(self):
        self.journal([werkzeug(ISP)])
        rc, out, err = self.lancer("--no-isp", "--no-presence")
        self.assertIn(ISP, out)
        self.assertIn("aucune requête extérieure (--no-isp)", err)
        self.assertFalse(os.path.exists(os.path.join(self.d, "curl.log")), "--no-isp : rdap.org ne doit jamais être interrogé")

    def test_connexion_apprise_en_direct(self):
        """Une connexion qui arrive PENDANT l'affichage donne tout de suite le nom aux lignes suivantes de cette adresse."""
        self.journal([werkzeug(ISP, "/avant", delta=20), login(ISP, "etienne@exemple.org", delta=10), werkzeug(ISP, "/apres", delta=5)])
        rc, out, err = self.lancer("--no-history", "--no-presence", "--recap", "0")
        lines = out.splitlines()
        self.assertIn("Videotron Ltee (org)", T(lines[0]))                                    # before the connection: owner of the block
        self.assertIn("Login successful for db:base login:etienne@exemple.org from Étienne Dupont", lines[1])
        self.assertIn("werkzeug Étienne Dupont", T(lines[2]))                               # after: the person

    def test_flux_jamais_bloque_par_une_recherche_lente(self):
        """Une recherche DNS de 2 s : la ligne attend au plus APP_LOG_LIVE_WAIT, garde l'adresse, et l'ordre est conservé."""
        self.journal([werkzeug(LENT, "/lente"), werkzeug(DNS, "/rapide")])
        start = time.time()
        rc, out, err = self.lancer("--no-history", "--no-isp", "--no-presence", env_extra={"APP_LOG_LIVE_WAIT": "0.4"})
        self.assertLess(time.time() - start, 1.9, "le flux a attendu la recherche lente")
        lines = out.splitlines()
        self.assertRegex(T(lines[0]), rf"werkzeug {re.escape(LENT)}\s+")
        self.assertIn("/lente", T(lines[0]))
        self.assertIn("werkzeug srv.exemple.org", T(lines[1]))
        self.assertIn("/rapide", T(lines[1]))

    def test_ipv6_et_faux_positifs(self):
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        ips = lambda t: [i for _, _, i in live.find_ips(t)]
        self.assertEqual(ips("from 2001:db8::1 - - x"), ["2001:db8::1"])
        self.assertEqual(ips("connexion de ::1 puis 10.0.0.5."), ["::1", "10.0.0.5"])
        self.assertEqual(ips("2026-10-02 03:02:14,775 502385 INFO base 03:02:14 aa:bb:cc:dd:ee:ff"), [])
        self.assertEqual(ips("version 18.0.1.0.0 et 300.1.1.1 et 1.2.3.4.5"), [])
        self.assertEqual(ips("(from ('11.97.88.1', 4242))"), ["11.97.88.1"])

    def test_bigbluebutton_suit_les_journaux_en_fichiers(self):
        nginx = os.path.dirname(self.path("nginx", "x"))
        with open(os.path.join(nginx, "bigbluebutton.access.log"), "w") as f:
            f.write(f'{DNS} - - [02/Oct/2026:03:02:14 +0000] "GET /bigbluebutton/api HTTP/1.1" 200 5\n')
        rc, out, err = self.lancer("--app", "bbb", "--no-isp", env_extra={"APP_LOG_LIVE_NGINX_DIR": nginx})
        self.assertEqual(rc, 0, err)
        self.assertIn(f'srv.exemple.org [{DNS}]'.ljust(45) + ' [02/Oct/2026:03:02:14 +0000] "GET  /bigbluebutton/api HTTP/1.1" 200 5', out)      # name + [address] on 42 characters
        self.assertNotIn("Historique des connexions", err, "BigBlueButton : pas de comptes Odoo")
        self.assertNotIn("Présence", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "runuser.log")))

    def test_service_introuvable_version_changelog_et_rapport(self):
        self.mock("systemctl", "exit 1")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow"])
        self.assertEqual(rc, 2)
        self.assertIn("aucune unité de l'application trouvée", T(err))
        rc, out, err = self.run_cmd(["python3", self.prog, "--version"])
        self.assertRegex(T(out), r"app-log-live\.py version 1\.\d+\.\d{8}\.\d{6}")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--report-err"])
        self.assertIn("RAPPORT D'ERREURS (--report-err)", out)
        self.assertIn("Programme : app-log-live.py v1.", T(out))

    # --- 1.12: presence sort, summarized accounts, colored figures, key menu ---
    def module_live(self):
        spec = importlib.util.spec_from_file_location("live_112", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        return live

    def test_presence_triee_par_derniere_activite(self):
        """[1] Le résumé de présence montre la dernière activité la plus récente EN PREMIER."""
        live = self.module_live()
        p = live.Presence(15)
        now_dt = time.time()
        p.login("base/vieux", "Vieux V", "1.1.1.1", now_dt - 3000)
        p.login("base/recent", "Recent R", "2.2.2.2", now_dt - 60)
        p.login("base/milieu", "Milieu M", "3.3.3.3", now_dt - 600)
        lines = [l for l in p.summary(now_dt, 10) if "[" in l]
        self.assertEqual([T(x).split()[2] for x in lines], ["Recent", "Milieu", "Vieux"], lines)

    def test_comptes_d_une_adresse_resumes_prenom_et_initiale(self):
        """[4] « Josée Desrosiers +1 autre(s) compte(s) » devient « JoséeD+ÉtienneB+JoséD » (le plus récent d'abord) ; une personne seule garde son nom entier."""
        live = self.module_live()
        pers = live.People(None)
        pers.databases_seen["b"] = (time.time(), {"s@x": {"nom": "Josée Desrosiers"}, "m@x": {"nom": "Étienne Bérubé"}, "j@x": {"nom": "José Desrosiers"}, "seul@x": {"nom": "Alice Un Deux"}})
        self.assertEqual(T(pers.tag([("b", "s@x")], "Josée Desrosiers")), "Josée Desrosiers")
        self.assertEqual(T(pers.tag([("b", "j@x"), ("b", "m@x"), ("b", "s@x")], "Josée Desrosiers")), "JoséeD+ÉtienneB+JoséD")
        self.assertEqual(T(pers.tag([("b", "s@x"), ("b", "s@x")], "Josée Desrosiers")), "Josée Desrosiers")       # same person
        self.assertEqual(T(pers.short("Alice Un Deux")), "AliceD")
        self.assertEqual(T(pers.short("sans-nom@exemple.org")), "sans-nom")
        beaucoup = [("b", f"u{i}@x") for i in range(8)]
        pers.databases_seen["b"] = (time.time(), {f"u{i}@x": {"nom": f"Prenom{i} Nom{i}"} for i in range(8)})
        self.assertTrue(pers.tag(beaucoup, "x").endswith("+etc"))
        self.assertEqual(pers.tag(beaucoup, "x").count("+"), 6)

    def test_etiquette_sans_doublon_des_comptes_d_une_meme_personne(self):
        """Les connexions « etienne.berube.ing » et « admin » (nom introuvable) ne s'ajoutent pas à « ÉtienneB » et « Administrateur » : « ÉtienneB+JoséR+Administrateur »."""
        live = self.module_live()
        pers = live.People(None)
        pers.databases_seen["b"] = (time.time(), {"m@x": {"nom": "Étienne Bérubé"}, "j@x": {"nom": "José Roy"}, "a@x": {"nom": "Administrateur"}})
        pers.databases_seen["autre"] = (time.time(), None)                # base illisible : seulement les identifiants
        accounts = [("autre", "admin"), ("autre", "etienne.berube.ing@exemple.org"), ("b", "a@x"), ("b", "j@x"), ("b", "m@x")]
        self.assertEqual(T(pers.tag(accounts, "Étienne Bérubé")), "ÉtienneB+JoséR+Administrateur")
        # a single known name + an identifier: the whole name, even if the identifier is the most recent
        self.assertEqual(T(pers.tag([("b", "m@x"), ("autre", "admin")], "admin")), "Étienne Bérubé")
        # no known name: the identifiers (no duplicate, case ignored)
        self.assertEqual(T(pers.tag([("autre", "Admin"), ("autre", "admin"), ("autre", "bob")], "bob")), "bob+admin")

    def test_chiffres_du_sommaire_en_couleur(self):
        """[3] Pages par langue et Codes HTTP : les nombres (et leur %) en couleur ; « 2xx » et les langues restent tels quels."""
        live = self.module_live()
        live.COLOR = True
        t = live.numbers("  Pages par langue (8782 pages) : sans préfixe 52 % · EN 32 % · FR 0 %")
        self.assertIn("\x1b[1;36m8782\x1b[0m", T(t))
        self.assertIn("\x1b[1;36m52 %\x1b[0m", T(t))
        self.assertIn("EN \x1b[1;36m32 %\x1b[0m", T(t))
        t = live.numbers("  Codes HTTP : 1xx 1 % · 2xx 66 % · 4xx 1 %")
        self.assertIn("1xx \x1b[1;36m1 %\x1b[0m", T(t))
        self.assertNotIn("\x1b[1;36m2\x1b[0m", T(t))
        live.COLOR = False
        self.assertEqual(T(live.numbers("2xx 66 %")), "2xx 66 %")

    def test_touche_f_redessine_les_lignes_soulignees(self):
        """1.118 : la touche f réaffiche les dernières lignes AVEC le soulignement d'une ligne sur N (mêmes lignes que sur l'écran)."""
        self.journal_tableau()
        sequence = [(b"/event", b"f", 1.0), (b"/event", b"\x03", 0.6)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "3", "--underline", "1"],
                                      sequence, timeout=60, colonnes=200, keep_ansi=True)
        self.assertEqual(envoyees, len(sequence), text)
        lignes = text.split("\n")
        titres = [i for i, l in enumerate(lignes) if "────" in l]
        self.assertTrue(titres, text)
        fin = next((i for i in titres if i > titres[0]), len(lignes))
        reaffichees = [l for l in lignes[titres[0] + 1:fin] if "odoo18" in l]
        self.assertTrue(reaffichees, text)
        for l in reaffichees:
            self.assertIn("\x1b[4m", l, "la ligne réaffichée doit être soulignée")

    def test_menu_des_touches_et_options_a_la_volee(self):
        """[6] ? ouvre le menu ; i, m, s, v basculent ; d, H, o demandent une valeur ; V affiche la version."""
        self.journal_tableau()
        sequence = [(b"/event", b"?", 0.4), (b"inscriptions aux \xc3\xa9v\xc3\xa9nements", b"i", 0.4), (b"--hide-ip : no", b"m", 0.4), (b"--min : yes", b"s", 0.4),
                    (b"--suspect : yes", b"d", 0.4), (b"Entr\xc3\xa9e = 20", b"30\r", 0.2), (b"--dns-max 30", b"t", 0.4), (b"Entr\xc3\xa9e = 32", b"\r", 0.2),
                    (b"--dns-max-truncate 32", b"H", 0.4), (b"Entr\xc3\xa9e = 10", b"0\r", 0.2), (b"alertes automatiques arr\xc3\xaat\xc3\xa9es", b"o", 0.4),
                    (b"tout afficher", b"zzz\r", 0.2), (b"--only : zzz", b"V", 0.4), (b"app-log-live.py version", b"v", 0.4), (b"--verbose : yes", b"\x03", 0.4)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "1"], sequence, timeout=60, colonnes=200)
        self.assertEqual(envoyees, len(sequence), text)
        menu = text[text.index("Touches (? ou h"):text.index("--hide-ip : no")]
        for attendu in ("Ctrl-G", "Ctrl-T", "Ctrl-C", "--dns-max N", "--dns-max-truncate N", "--health MIN", "--hide-ip", "--min", "--only TEXTE", "--report-err", "--suspect",
                        "--verbose", "--version", "inscriptions aux sondages", "inscriptions aux événements", "adresses à bannir : 0"):
            self.assertIn(attendu, menu)
        self.assertRegex(T(menu), r"app-log-live version \d+\.\d+\.\d{8}\.\d{6} \(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\)")        # 1.41 : version ET date dans le menu
        self.assertIn("--dns-max-truncate 32", text)
        self.assertRegex(text, r"app-log-live\.py version 1\.\d+\.\d{8}\.\d{6}")

    def test_inscriptions_aux_sondages_et_aux_evenements(self):
        """[6] S et I : dernières inscriptions de chaque base, plus récentes d'abord (lecture seule dans PostgreSQL)."""
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; case "$*" in *information_schema*) exit 0;; *event_registration*) printf "1760000000\\037Soirée Linux\\037Alice A\\037open\\037Billet Membre\\0371\\0371760000300\\037Portes ouvertes Linux (Visiteur)\\037Alice\\037done\\n1759990000\\037Soirée Linux\\037Bob\\037open\\037Billet Membre\\0371\\037\\037\\037\\037\\n1759980000\\037Pause café\\037Carl\\037done\\037\\0370\\037\\037\\037\\037\\n";; \\\n'
                             f'*survey_user_input*) printf "1760000100\\037Sondage JPO\\037Bob B\\037done\\n";; *) printf "{UTILISATEURS}";; esac')
        self.journal_tableau()
        sequence = [(b"/event", b"S", 0.4), (b"Sondage JPO", b"I", 0.4), (b"Soir\xc3\xa9e Linux", b"\x03", 0.4)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1"], sequence, timeout=60)
        self.assertEqual(envoyees, 3, text)
        self.assertRegex(text, r"Inscriptions aux sondages \(surveys\).*\n\s+Base base :\n\s+\d{4}-\d\d-\d\d \d\d:\d\d  Bob B\s+Sondage JPO  \(done\)")
        simple = re.sub(r"\x1b\[[0-9;]*m", "", text)
        self.assertRegex(T(simple), r"Inscriptions aux événements.*\n\s+Base base :\n\s+\d{4}-\d\d-\d\d \d\d:\d\d  Alice A\s+Soirée Linux  — billet « Billet Membre »  \(open\)"
                                 r"\s+Sondage complété : \d{4}-\d\d-\d\d \d\d:\d\d  Alice\s+Portes ouvertes Linux \(Visiteur\)  \(done\)")   # 1.23 : sondage de confirmation
        self.assertRegex(T(simple), r"Bob\s+Soirée Linux  — billet « Billet Membre »  \(open\)\s+Sondage : AUCUN — inscription non confirmée")
        self.assertRegex(T(simple), r"Carl\s+Pause café\s+\(done\)\n")                                                # event without poll: nothing added
        journal = open(os.path.join(self.d, "runuser.log")).read()
        self.assertIn("event_registration", T(journal))
        self.assertIn("event_event_ticket", T(journal))                                              # 1.21 : nom du billet (ticket) de chaque inscription
        self.assertIn("default_transaction_read_only=on", T(journal))                               # read-only forced

    def test_inscriptions_avec_sondage_requete_et_analyse(self):
        """1.23 : _odoo_db.inscriptions_avec_sondage : motif nettoyé (aucune injection), courriel comparé jamais renvoyé, sondage absent = None, lecture seule."""
        spec = importlib.util.spec_from_file_location("odoo_db", os.path.join(SCRIPTS_DIR, "apps", "_odoo_db.py"))
        db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(db)
        views = []
        db._requete = lambda database, sql, delay=20: views.append(sql) or [["1760000000", "JPO", "Alice", "open", "Visiteur", "1", "1760000300", "Sondage JPO", "", "done"],
                                                                      ["1759990000", "Pause", "Bob", "done", "", "0", "", "", "", ""]]
        was_read = db.inscriptions_avec_sondage("base", 30, 15, "portes'; DROP TABLE x; --")
        self.assertNotIn("'; DROP", T(views[0]))
        self.assertIn("ILIKE '%portes DROP TABLE x --%'", views[0])
        self.assertIn("survey_user_input", T(views[0]))
        self.assertNotIn("r.email,", T(views[0].split("FROM event_registration")[0]))                      # le courriel n'est jamais lu en sortie
        self.assertEqual(was_read[0]["sondage"], {"quand": 1760000300, "titre": "Sondage JPO", "nom": "", "etat": "done"})
        self.assertTrue(was_read[0]["avec_sondage"])
        self.assertFalse(was_read[1]["avec_sondage"])
        self.assertIsNone(was_read[1]["sondage"])
        db._requete = lambda database, sql, delay=20: None
        self.assertIsNone(db.inscriptions_avec_sondage("base"))

    def test_courriels_en_echec_adresses_des_destinataires_dans_le_tableau_de_bord(self):
        """1.21 : sous « Courriels en échec », les adresses (en entier) des courriels à renvoyer, lues en lecture seule dans PostgreSQL."""
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; case "$*" in *pg_database*) printf "base\\n";; *to_regclass*) printf "t\\n";; *"state = \'exception\'"*) '
                             'printf "7\\0371760000000\\037Confirmation JPO\\037alice@exemple.org\\037Mail Delivery Failed 550\\n";; *) printf "' + UTILISATEURS + '";; esac')
        self.journal_tableau()
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "1"],
                                       [(b"/event", b"\x07", 0.8), (b"Top 10 des URLs", b"\x03", 0.5)], timeout=60)
        self.assertEqual(envoyees, 2, text)
        t = " ".join(text[text.index("Tableau de bord depuis le démarrage"):].split())
        self.assertIn("Courriels en échec : 1", T(t))
        self.assertRegex(T(t), r"À renvoyer : \d{4}-\d\d-\d\d \d\d:\d\d alice@exemple\.org — Confirmation JPO \(Mail Delivery Failed 550\)")
        self.assertIn("odoo-mail-retry.py liste", T(t))
        self.assertIn("default_transaction_read_only=on", T(open(os.path.join(self.d, "runuser.log")).read()))

    def test_adresses_a_renvoyer_plafonnees_a_dix(self):
        """1.21 : le détail est affiché tel quel (10 lignes puis « et N autre(s) ») ; base illisible : aucune ligne, jamais d'exception."""
        live = self.module_live()
        st = live.Stats(3.0)
        st.mails = 1
        st.mail_detail = lambda: [f"À renvoyer : x{i}@exemple.org" for i in range(10)] + ["… et 3 autres : odoo-mail-retry.py --details"]
        text = " ".join(st.health()[1])
        self.assertIn("x9@exemple.org", T(text))
        self.assertIn("… et 3 autres", T(text))
        st.mail_detail = lambda: 1 / 0
        self.assertIn("odoo-mail-retry.py liste", T(" ".join(st.health()[1])))

    def test_images_base64_resumees_et_suites_de_lignes_omises(self):
        """1.22 : une image collée dans un courriel (data:image/webp;base64,…) ne remplit plus l'écran : texte résumé, suites base64 omises, un seul groupe d'erreurs au sommaire."""
        live = self.module_live()
        blob = "UklGRtQfAQBXRUJQVlA4WAoAAAAgAAAAfwcAegEASUNDUMgBAAAAAAHIAAAAAAQwAABtbnRy" * 3
        L = live.Line(odoo("ERROR", "base", "odoo.addons.mass_mailing.models.mailing", f"No connection adapters were found for 'data:image/webp;base64,{blob}"))
        self.assertEqual(T(L.level), "ERROR")
        self.assertIn("No connection adapters were found for 'data:image/webp;base64,[… base64 omis]", T(L.text))
        self.assertNotIn("UklGR", T(L.text))
        continuation = live.Line(f"{ts(0)} odoo18 odoo[1]: {blob}'")
        self.assertRegex(T(continuation.text), r"^\[… \d+ caractères base64 omis\]$")
        sans_entete = live.Line(blob)
        self.assertIn("base64 omis", T(sans_entete.text))
        st = live.Stats(3.0)
        st.ajouter(L, {}, None)
        self.assertIn("base64,[… base64 omis]", T(" ".join(st.health()[1])))
        self.assertNotIn("baseN", T(" ".join(st.health()[1])))

    def test_adresses_a_bannir_dans_le_sommaire_et_touche_b(self):
        """[6] Le sommaire compte les adresses à bannir (requêtes suspectes, ni bannies ni protégées) ; la touche b demande, puis appelle nginx-log-audit.sh --ban."""
        faux = os.path.join(os.path.dirname(self.prog), "nginx-log-audit.sh")
        with open(faux, "w") as f:
            f.write(f'#!/usr/bin/env bash\necho "$@" >> {self.d}/ban.log\necho "Règle ajoutée"\nexit 0\n')
        os.chmod(faux, 0o755)
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/wp-login.php", 404), werkzeug(DNS, "/.env", 404), werkzeug(PERSONNE, "/wp-admin/", 404)], after="sleep 12")
        wm = os.path.join(os.path.dirname(self.prog), "web-monitor.py")                  # faux web-monitor.py : note chaque lancement
        with open(wm, "w") as f:
            f.write(f'import sys\nopen("{self.d}/wm.log", "a").write(" ".join(sys.argv[1:]) + "\\n")\n')
        sequence = [(b"/.env", b"\x07", 0.5), (b"Top 10 des URLs", b"b", 0.5), (b"Bannir maintenant", b"o\r", 0.2), (b"adresses bannies", b"b", 0.5),
                    (b"aucune requ", b"\x07", 0.5), (b"Top 10 des URLs", b"\x03", 0.3)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1"], sequence, timeout=60)
        self.assertEqual(envoyees, 6, text)
        t = " ".join(text.split())
        # 1.42: with addresses ALREADY to ban, web-monitor.py is not restarted; once the list is empty, the b key restarts it (only once)
        appels = open(os.path.join(self.d, "wm.log")).read().splitlines()
        self.assertEqual(len(appels), 1, appels)
        self.assertIn("--save-recommended", appels[0])
        self.assertEqual(t.count("Mise à jour des recommandations de web-monitor.py"), 1, t)
        self.assertLess(t.index("1/1 adresses bannies"), t.index("Mise à jour des recommandations"))
        self.assertIn("Adresses à bannir : 1 — srv.exemple.org [93.184.216.34] (2 requêtes suspectes)", T(t))          # the known person is never proposed
        self.assertNotIn(f"[{PERSONNE}] ×", T(t.split("Adresses à bannir")[1].split("Top 10")[0]))
        self.assertIn("1 adresses à bannir", T(t))
        self.assertNotRegex(T(t), r"(\d+\.\d+\.\d+\.\d+) \1 —")                              # 1.49: the address is never repeated when its unknown name is the address itself
        self.assertIn(f"{DNS} : banni — Règle ajoutée", T(t))
        self.assertIn("1/1 adresses bannies", T(t))
        self.assertIn(f"--ban {DNS} --yes", open(os.path.join(self.d, "ban.log")).read())
        self.assertIn("Adresses à bannir : aucune", T(t.split("1/1 adresses bannies")[1]))        # after the ban: nothing left to ban

    def test_sondes_wordpress_debug_et_balayage_de_404_a_bannir(self):
        """1.37 : /wp, /wordpress, /_ignition, /debug/default sont suspects (même sous /en_CA) ; 5 pages DIFFÉRENTES en 404 pour une adresse = à bannir, sans autre signe."""
        live = self.module_live()
        for url in ("/wp", "/en_CA/wp", "/wordpress", "/en_CA/_ignition/execute-solution", "/en_CA/debug/default/index", "/wp?x=1"):
            self.assertTrue(live.suspect_url(url), url)
        for url in ("/en_CA/blog", "/new", "/demo", "/web/login", "/wpad.html", "/event/wp-club"):
            self.assertFalse(live.suspect_url(url), url)
        os.environ["WEB_MONITOR_STATE_DIR"] = os.path.join(self.d, "absent")
        self.addCleanup(os.environ.pop, "WEB_MONITOR_STATE_DIR", None)
        st = live.Stats(5.0)
        for url in ("/aa", "/bb", "/cc", "/dd", "/dd"):                       # 4 different pages only
            L = live.Line(werkzeug("7.7.7.7", url, 404))
            L.instant = time.time()
            st.ajouter(L, {}, None)
        self.assertEqual(st.to_ban(), [])
        L = live.Line(werkzeug("7.7.7.7", "/ee?x=1", 404))
        L.instant = time.time()
        st.ajouter(L, {}, None)
        self.assertEqual(st.to_ban(), [("7.7.7.7", 5)])
        self.assertIn("5 pages différentes introuvables (404)", T(st.ban_reason("7.7.7.7", 5)))
        st.all_banned.add("7.7.7.7")
        self.assertEqual(st.to_ban(), [])

    def test_cms_wordpress_urls_normales_et_odoo_urls_suspectes(self):
        """1.38 : sous WordPress, /wp-login.php, /wp-admin, xmlrpc.php et *.php sont des pages normales ; sur un site Odoo seul, elles sont suspectes. --cms, NGINX_TOOLS_CMS,
        nginx-tools-cms.conf ou un wp-config.php détecté décident ; .env et les autres sondes restent suspects partout."""
        live = self.module_live()
        profile = importlib.util.module_from_spec(importlib.util.spec_from_file_location("p", script_path("apps/_profile.py")))
        profile.__spec__.loader.exec_module(profile)
        wp = ("/wp-login.php", "/wp-admin/", "/en_CA/wp", "/xmlrpc.php", "/index.php", "/wordpress/")
        for url in wp:
            self.assertTrue(live.suspect_url(url), url)                          # default: Odoo site
        live.regler_cms("wordpress")
        for url in wp:
            self.assertFalse(live.suspect_url(url), url)
        for url in ("/.env", "/phpmyadmin/", "/_ignition/execute-solution", "/backup.sql"):
            self.assertTrue(live.suspect_url(url), url)
        live.regler_cms("odoo")
        self.assertTrue(live.suspect_url("/wp-login.php"))
        racine = os.path.join(self.d, "racine")
        os.makedirs(os.path.join(racine, "var", "www", "blog"))
        etc = os.path.join(self.d, "etc-defaut")
        os.makedirs(etc)
        env = {"APP_DETECT_ROOT": racine, "NGINX_TOOLS_ETC_DEFAULT": etc}
        with unittest.mock.patch.dict(os.environ, env):
            os.environ.pop("NGINX_TOOLS_CMS", None)
            self.assertEqual(T(profile.cms()), "odoo")
            open(os.path.join(racine, "var", "www", "blog", "wp-config.php"), "w").close()
            self.assertEqual(T(profile.cms()), "wordpress")                           # detection
            with open(os.path.join(etc, "nginx-tools-cms.conf"), "w") as f:
                f.write("# CMS\nCMS=odoo\n")
            self.assertEqual(T(profile.cms()), "odoo")                                # the file wins over detection
            os.environ["NGINX_TOOLS_CMS"] = "wordpress"
            self.assertEqual(T(profile.cms()), "wordpress")                           # la variable l'emporte sur le fichier
            self.assertEqual(T(profile.cms("odoo")), "odoo")                          # --cms l'emporte sur tout

    def test_diagnostic_du_certificat_comme_un_navigateur(self):
        """1.44 : touche D / --diagnose vérifie le certificat comme un navigateur (autorité reconnue, chaîne, nom, expiration) : auto-signé / autorité inconnue → ECHEC avec le certificat
        présenté et que faire (certbot) ; nom non couvert → certbot --expand ; accepté → OK avec l'émetteur et les jours restants ; --diagnose-host ajoute un nom servi ailleurs."""
        import socket
        import ssl
        import threading
        if not shutil.which("openssl"):
            self.skipTest("openssl absent")
        key_value, cert = os.path.join(self.d, "k.pem"), os.path.join(self.d, "c.pem")
        r = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key_value, "-out", cert, "-days", "30", "-subj", "/CN=localhost/O=Test Auto",
                            "-addext", "subjectAltName=DNS:localhost"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key_value)
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(5)
        self.addCleanup(server.close)
        port = server.getsockname()[1]

        def servir():
            while True:
                try:
                    c, _ = server.accept()
                except OSError:
                    return
                try:
                    context.wrap_socket(c, server_side=True).close()
                except (OSError, ssl.SSLError):
                    c.close()
        threading.Thread(target=servir, daemon=True).start()
        live = self.module_live()
        level, finding, advice = live.check_certificate("localhost", "127.0.0.1", port)                 # unknown authority: the test certificate is not in the system authorities
        self.assertEqual(T(level), "FAIL", finding)
        self.assertIn("REFUSÉ par les navigateurs", T(finding))
        self.assertIn("Certificat présenté", T(finding))
        self.assertIn("Test Auto", T(finding))
        self.assertIn("certbot", T(advice))
        self.assertIn("localhost", T(advice))
        old = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = cert                                                                # recognized authority: this certificate becomes a trusted authority
        self.addCleanup(lambda: os.environ.__setitem__("SSL_CERT_FILE", old) if old else os.environ.pop("SSL_CERT_FILE", None))
        level, finding, advice = live.check_certificate("localhost", "127.0.0.1", port)
        self.assertEqual((level, advice), ("OK", ""), finding)
        self.assertRegex(T(finding), r"accepté \(émis par Test Auto, expire dans (29|30) jours\)")
        level, finding, advice = live.check_certificate("autre.exemple.org", "127.0.0.1", port)         # nom non couvert par le certificat
        self.assertEqual(T(level), "FAIL", finding)
        self.assertIn("certbot --nginx --expand -d autre.exemple.org", advice)
        level, finding, _ = live.check_certificate("localhost", "127.0.0.1", 1)                          # nobody listening
        self.assertEqual(T(level), "WARN", finding)
        # Le diagnostic complet : noms de nginx (via 127.0.0.1:443), puis --diagnose-host (vu par Internet)
        appels = []
        with unittest.mock.patch.object(live, "check_certificate", lambda name, host_name=None, port=443, delay=8: (appels.append((name, host_name)), ("FAIL", f"Certificate of {name}: REFUSED", "x"))[1]):
            res = live.public_certificates(["a.exemple.org", "a.exemple.org", "*.exemple.org", "_", "b.exemple.org"])
        self.assertEqual(appels, [("a.exemple.org", None), ("b.exemple.org", None)])
        self.assertIn("Certificat PUBLIC de a.exemple.org", T(res[0][1]))
        self.assertIn("pointe vers un autre serveur", T(res[0][2]))

    def test_diagnostic_page_de_maintenance_upstream_sur_un_autre_port(self):
        """1.39 : touche D / --diagnose. nginx vise 127.0.0.1:10000, Odoo écoute sur 8069 : « connexion refusée » = page de maintenance ; le diagnostic le dit et donne la correction."""
        live = self.module_live()
        nginx_t = ("# configuration file /etc/nginx/sites-enabled/10-prod.conf:\nupstream odoo {\n    server 127.0.0.1:10000;\n}\nupstream odoo_chat {\n    server 127.0.0.1:10002;\n}\n"
                   "upstream odoo17 {\n    server 127.0.0.1:8069;\n}\nupstream odoo17_chat {\n    server 127.0.0.1:9072;\n}\n"
                   "server {\n    server_name odoo.exemple.org;\n}\n")
        state = {"listening": "LISTEN 0 128 127.0.0.1:8069 0.0.0.0:* users:((\"python3\",pid=7,fd=3))\nLISTEN 0 128 127.0.0.1:8072 0.0.0.0:* users:((\"python3\",pid=7,fd=4))\n",
                "active": "active\n", "web": (502, "<title>Maintenance en cours — X</title>")}

        def faux_lancer(cmd, delay=10):
            if cmd[0] == "systemctl":
                return 0, state["active"]
            if cmd[0] == "ss":
                return 0, state["listening"]
            if cmd[0] == "nginx":
                return 0, nginx_t
            return 1, ""

        def faux_requete(port, host_name, tls=False, path="/", delay=8):
            if tls:
                return state["web"]
            return (303, "") if port == 8069 else (None, "connexion refusée")
        profile = {"ODOO_HTTP_PORT": "8069", "ODOO_GEVENT_PORT": "8072", "ODOO_CONF": "/etc/odoo/odoo-x.conf"}
        with unittest.mock.patch.object(live, "lancer", faux_lancer), unittest.mock.patch.object(live, "local_request", faux_requete), \
                unittest.mock.patch.object(live, "check_certificate", lambda name, host_name=None, port=443, delay=8: ("OK", f"Certificat de {name} : accepté", "")):
            output = []
            code = live.show_diagnostic(profile, "odoo-x.service", output.append, False)
            text = "\n".join(output)
            self.assertEqual(code, 1)
            self.assertIn("[OK] Le service odoo-x.service est actif.", T(text))
            self.assertIn("[OK] Port HTTP d'Odoo 8069 : en écoute (python3).", T(text))
            self.assertIn("Upstream nginx « odoo » vise 127.0.0.1:10000 (/etc/nginx/sites-enabled/10-prod.conf:2), mais Odoo est configuré sur 8069", T(text))
            self.assertIn("remplacer « server 127.0.0.1:10000; » par « server 127.0.0.1:8069; », puis nginx -t && systemctl reload nginx", T(text))
            self.assertIn("« server 127.0.0.1:10002; » par « server 127.0.0.1:8072; »", T(text))
            self.assertIn("https://odoo.exemple.org/ : HTTP 502 — PAGE DE MAINTENANCE servie", T(text))
            self.assertIn("Upstream nginx « odoo17 » (/etc/nginx/sites-enabled/10-prod.conf:", T(text))       # 1.56: other Odoo version, never a failure
            self.assertIn("c'est une autre version d'Odoo, non vérifié.", T(text))
            self.assertNotIn("« odoo17_chat » vise", T(text))
            # Service stopped and nobody listening
            state.update(active="inactive\n", listening="")
            output.clear()
            live.show_diagnostic(profile, "odoo-x.service", output.append, False)
            text = "\n".join(output)
            self.assertIn("[ECHEC] Service odoo-x.service : inactive", T(text))
            self.assertIn("systemctl start odoo-x.service", text)
            self.assertIn("Port HTTP d'Odoo 8069 : PERSONNE n'écoute", T(text))
            # All good: upstream aligned, site responding
            nginx_t = nginx_t.replace("10000", "8069").replace("10002", "8072")
            state.update(active="active\n", listening="LISTEN 0 1 127.0.0.1:8069 x users:((\"python3\",pid=1))\nLISTEN 0 1 127.0.0.1:8072 x users:((\"python3\",pid=1))\n", web=(200, "<html>Accueil"))
            output.clear()
            code = live.show_diagnostic(profile, "odoo-x.service", output.append, False)
            self.assertEqual(code, 0, output)
            self.assertIn("https://odoo.exemple.org/ : HTTP 200 — le site répond (pas de page de maintenance).", T("\n".join(output)))
            self.assertIn("Tout répond.", T("\n".join(output)))

    def test_serveur_bigbluebutton_tout_cms_est_suspect(self):
        """1.39 : sur un serveur BigBlueButton, WordPress, Joomla, Drupal, *.php… sont suspects même si le CMS réglé est wordpress ; les pages de BBB ne le sont pas."""
        live = self.module_live()
        live.regler_cms("wordpress", True)
        for url in ("/wp-login.php", "/administrator/index.php", "/joomla/", "/sites/default/files/x", "/typo3/", "/index.php", "/shell.aspx", "/node/12"):
            self.assertTrue(live.suspect_url(url), url)
        for url in ("/html5client/join", "/bigbluebutton/api/create", "/b/abc-def", "/learning-dashboard/", "/graphql", "/playback/presentation/2.3/x"):
            self.assertFalse(live.suspect_url(url), url)
        live.regler_cms("odoo")
        self.assertFalse(live.suspect_url("/joomla/"))

    def test_ctrl_c_pendant_l_arret_sortie_propre(self):
        """1.39 : un Ctrl-C de plus pendant l'arrêt (résumé, message d'interruption) : code 130, jamais de trace d'appels."""
        live = self.module_live()

        def main_interrompu():
            raise KeyboardInterrupt

        def eprint_interrompu(*a, **k):
            raise KeyboardInterrupt
        with unittest.mock.patch.object(live, "main", main_interrompu), unittest.mock.patch.object(live, "eprint", eprint_interrompu):
            self.assertEqual(live.protected_main(), 130)

    def test_adresses_recommandees_par_web_monitor_dans_a_bannir(self):
        """1.24 : la touche b et le tableau de bord ajoutent les adresses recommandées par le dernier passage de web-monitor.py (sondes vues seulement par nginx), sauf celles déjà
        bannies, protégées, connues, locales ou trop anciennes (48 h)."""
        live = self.module_live()
        folder = os.path.join(self.d, "web-monitor-state")
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, "recommended-bans.json")

        def ecrire_reco(age_h=1.0):
            with open(file_path, "w") as f:
                json.dump({"when": "2026-10-10 16:33", "time": time.time() - age_h * 3600, "ips": [
                    {"ip": "11.65.131.103", "raison": "enquête : Score 4/7"}, {"ip": "11.76.10.40", "raison": "récidiviste : 4 jours"},
                    {"ip": "10.9.9.9", "raison": "serveur"}, {"ip": "127.0.0.1", "raison": "local"}, {"ip": "1.1.1.1", "raison": "banned"}, {"ip": "2.2.2.2", "raison": "équipe"}]}, f)
        ecrire_reco()
        patcher = unittest.mock.patch.dict(os.environ, {"WEB_MONITOR_STATE_DIR": folder})
        patcher.start()
        self.addCleanup(patcher.stop)
        st = live.Stats(5.0)
        st.server.add("10.9.9.9")
        st.all_banned.add("1.1.1.1")
        st.protected_ones.add("2.2.2.2")
        self.assertEqual(sorted(ip for ip, _ in st.to_ban()), ["11.65.131.103", "11.76.10.40"])
        self.assertEqual(dict(st.to_ban()), {"11.65.131.103": 0, "11.76.10.40": 0})
        self.assertEqual(T(st.ban_reason("11.65.131.103", 0)), "recommandée par web-monitor.py (enquête : Score 4/7)")
        self.assertEqual(T(st.ban_reason("9.9.9.9", 3)), "3 requêtes suspectes")
        L = live.Line(werkzeug("8.8.8.8", "/a", 200))
        L.instant = time.time()
        st.ajouter(L, {"8.8.8.8": ("ok.exemple.org", [], False, None)}, None)
        t = " ".join(" ".join(st.summary()).split())
        self.assertIn("Adresses à bannir : 2 — 11.65.131.103 (recommandée par web-monitor.py (enquête : Score 4/7)) ; 11.76.10.40 (recommandée par web-monitor.py (récidiviste : 4 jours))", T(t))
        # Suspicious requests seen here: first, and a recommended address is not counted twice
        st2 = live.Stats(5.0)
        st2.server.add("10.9.9.9")
        st2.all_banned.add("1.1.1.1")
        st2.protected_ones.add("2.2.2.2")
        st2.suspect_ips["11.76.10.40"] += 3
        self.assertEqual(st2.to_ban(), [("11.76.10.40", 3), ("11.65.131.103", 0)])
        # Fichier trop ancien, absent ou illisible : aucune recommandation, jamais d'exception
        ecrire_reco(age_h=50)
        self.assertEqual(live.Stats(5.0).to_ban(), [])
        os.remove(file_path)
        self.assertEqual(live.Stats(5.0).to_ban(), [])
        with open(file_path, "w") as f:
            f.write("pas du json")
        self.assertEqual(live.Stats(5.0).to_ban(), [])

    def test_robots_et_vrais_visiteurs(self):
        """1.17 : robot = a demandé robots.txt / un plan de site, ou nom de robot connu ; jamais une personne connue ; % de vrais visiteurs."""
        live = self.module_live()
        st = live.Stats(5.0)

        def request_data(ip, url, name, code=200):
            L = live.Line(werkzeug(ip, url, code))
            L.instant = 1_760_000_000.0
            st.ajouter(L, {ip: (name, [], False, None)}, None)
        st.people.add("1.1.1.1")
        request_data("1.1.1.1", "/a", "Étienne")
        request_data("2.2.2.2", "/a", "visiteur.exemple.org")
        request_data("3.3.3.3", "/robots.txt", "inconnu.exemple.net")          # robots.txt : robot
        request_data("3.3.3.3", "/a", "inconnu.exemple.net")
        request_data("4.4.4.4", "/a", "108-174-8-25.fwd.linkedin.com")        # nom de robot connu
        request_data("4.4.4.4", "/b", "108-174-8-25.fwd.linkedin.com")
        request_data("5.5.5.5", "/news_sitemap.xml", "x.exemple.net", 404)
        lines = " ".join(" ".join(st.visit_lines()).split())
        self.assertIn("Robots : 2 adresses sur 4 (50 %) · 3 pages vues (60 % des pages)", T(lines))
        self.assertIn("Vrais visiteurs : 2 sur 4 (50 %)", T(lines))
        self.assertFalse(st.is_robot("1.1.1.1"))
        self.assertTrue(st.is_robot("5.5.5.5"))                           # sitemap requested, even in a 404

    def test_user_agent_du_journal_d_acces_et_robots(self):
        """1.20 : le User-Agent lu dans le journal d'accès nginx décide des robots ; la note dit la part des visiteurs dont il est connu."""
        live = self.module_live()
        folder = os.path.dirname(self.path("nginx", "x"))
        with open(os.path.join(folder, "site-access.log"), "w") as f:
            f.write(f'{DNS} - - [09/Oct/2026:14:00:00 -0400] "GET /a HTTP/1.1" 200 5 "-" "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" host="x"\n'
                    f'{ISP} - - [09/Oct/2026:14:00:01 -0400] "GET /a HTTP/1.1" 200 5 "-" "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0" host="x"\n'
                    f'{LENT} - - [09/Oct/2026:14:00:02 -0400] "GET /a HTTP/1.1" 200 5 "-" "python-requests/2.31.0" host="x"\n')
        agents = {}
        proc = live.read_agents(agents, "*-access.log", folder, lines=10)
        try:
            for _ in range(50):
                if len(agents) == 3:
                    break
                time.sleep(0.1)
        finally:
            proc.terminate()
        self.assertEqual(sorted(agents), sorted([DNS, ISP, LENT]))
        st = live.Stats(5.0)
        st.agents.update(agents)
        for ip in (DNS, ISP, LENT):
            L = live.Line(werkzeug(ip, "/a"))
            L.instant = 1_760_000_000.0
            st.ajouter(L, {ip: ("inconnu", [], False, None)}, None)
        self.assertTrue(st.is_robot(DNS))
        self.assertFalse(st.is_robot(ISP))
        self.assertTrue(st.is_robot(LENT))
        lines = " ".join(" ".join(st.visit_lines()).split())
        self.assertIn("Robots : 2 adresses sur 3 (67 %)", T(lines))
        self.assertIn("Vrais visiteurs : 1 sur 3 (33 %)", T(lines))
        self.assertIn("User-Agent lu pour 100 % des visiteurs", T(lines))

    def test_watch_registration_duree_erreurs_et_inscriptions(self):
        """1.20 : --watch TEXTE : requêtes, erreurs, durée médiane / 95e centile / maximum, lentes, inscriptions confirmées ; indicateur de santé."""
        live = self.module_live()
        st = live.Stats(3.0)
        st.watch_it = ["registration"]

        def request_data(url, code, sql, py):
            st.ajouter(live.Line(f'2026-10-09 14:00:00.00 odoo18 odoo INFO base werkzeug {PERSONNE} "POST {url} HTTP/1.1" {code} - 12 {sql} {py}'), {PERSONNE: ("inconnu", [], False, None)}, None)
        request_data("/event/jpo-1/registration/new", 200, 0.1, 0.3)
        request_data("/event/jpo-1/registration/confirm", 303, 0.2, 0.4)
        request_data("/event/jpo-1/registration/confirm", 303, 1.0, 4.9)
        request_data("/event/jpo-1/registration/confirm", 500, 0.1, 0.2)
        request_data("/web/login", 200, 0.1, 0.1)                                  # hors surveillance
        lines = " ".join(" ".join(st.watch_lines()).split())
        self.assertIn("Surveillance « registration » : 4 requêtes · 1 erreurs · durée médiane 0.60 s · 95e centile 5.90 s · maximum 5.90 s · 1 lentes (≥ 3 s) · 2 inscriptions confirmées", T(lines))
        health = " ".join(" ".join(st.health()[1]).split())
        self.assertIn("Surveillance (registration) : 4 requêtes, 1 erreurs, 1 lentes", T(health))
        before = st.snapshot()
        request_data("/event/jpo-1/registration/confirm", 303, 0.1, 0.1)
        period = st.since(before)
        self.assertIn("1 requêtes · 0 erreurs", T(" ".join(" ".join(period.watch_lines()).split())))

    def test_watch_pages_visiteurs_et_sondages_par_billet(self):
        """1.45 : --watch détaille les pages les plus vues (visiteurs, robots) et chaque sondage /survey/<jeton> (titre lu dans PostgreSQL, accès, visiteurs, envois) ;
        fichiers statiques et erreurs ignorés ; _odoo_db.jetons_sondages : lecture seule, repli sans module rlq."""
        live = self.module_live()
        st = live.Stats(3.0)
        st.watch_it = ["journee-portes-ouvertes", "/survey/"]
        token = "0a1b2c3d-1111-2222-3333-444455556666"
        st.survey_titles = {token: "Portes ouvertes (Bénévole) — billet Bénévole"}
        autre = "203.0.113.9"

        def request_data(url, ip=PERSONNE, code=200):
            st.ajouter(live.Line(f'2026-10-13 14:00:00.00 odoo18 odoo INFO base werkzeug {ip} "GET {url} HTTP/1.1" {code} - 12 0.1 0.2'), {ip: ("inconnu", [], False, None)}, None)
        request_data("/event/journee-portes-ouvertes-sur-linux-2026-125/page/introduction")
        request_data("/event/journee-portes-ouvertes-sur-linux-2026-125/page/introduction/", autre)
        request_data("/event/journee-portes-ouvertes-sur-linux-2026-125/page/horaire?x=1")
        request_data("/event/journee-portes-ouvertes-sur-linux-2026-125/static.css")
        request_data("/event/journee-portes-ouvertes-sur-linux-2026-125/page/absente", code=404)
        request_data(f"/survey/start/{token}?answer_token=abc")
        request_data(f"/survey/{token}/def", autre)
        request_data(f"/survey/submit/{token}/def", autre)
        request_data("/survey/start/ffffffff-0000-1111-2222-333344445555", autre)
        lines = "\n".join(" ".join(x.split()) for x in st.watch_lines())
        self.assertIn("Visiteurs : 2 adresses dont", T(lines))
        self.assertIn("/event/journee-portes-ouvertes-sur-linux-2026-125/page/introduction ×2 (2 visiteurs)", T(lines))
        self.assertNotIn("static.css", T(lines))
        self.assertNotIn("absente", T(lines))
        self.assertIn("Sondage « Portes ouvertes (Bénévole) — billet Bénévole » : 2 accès · 2 visiteurs · 1 envois de réponses", T(lines))
        self.assertIn("Sondage « sondage ffffffff… » : 1 accès", T(lines))
        spec = importlib.util.spec_from_file_location("odoo_db", os.path.join(SCRIPTS_DIR, "apps", "_odoo_db.py"))
        db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(db)
        views = []

        def faux(database, sql, delay=20):
            views.append(sql)
            return None if "rlq_survey_id" in sql else [["AbC-1", "Portes ouvertes (Bénévole)", ""]]
        db._requete = faux
        self.assertEqual(db.jetons_sondages("base"), {"AbC-1": "Portes ouvertes (Bénévole)"})
        self.assertEqual(len(views), 2)
        db._requete = lambda database, sql, delay=20: [["tok", "Titre", "Bénévole"], ["tok2", "Titre Visiteur", "Visiteur"]]
        self.assertEqual(db.jetons_sondages("base"), {"tok": "Titre — billet Bénévole", "tok2": "Titre Visiteur"})
        db._requete = lambda database, sql, delay=20: None
        self.assertIsNone(db.jetons_sondages("base"))

    def test_requete_lente_tout_en_python_indique_l_etat_du_serveur(self):
        """1.45/1.48 : quand le temps est presque tout du Python (pas du SQL), une ligne donne l'état du serveur et ce qu'il en conclut : causes retenues (charge, swap, disque) ou, si aucune,
        celles qui restent (cache à froid, verrou) ; assets et get_views : indice de cache à froid ; volumes ZFS regroupés ; rien si /proc est illisible."""
        live = self.module_live()
        state = {"load": 1.4, "cores": 6, "swap_mb": 0, "mem_gb": 12.9, "io": (0.0, 1.0), "disks": [("sda", True), ("zd0", False), ("zd16", False)]}
        live.read_state = lambda: dict(state)
        st = live.Stats(3.0)
        for url in ("/odoo/action-908/128", "/web/assets/1/bc7974c/web.assets_frontend_lazy.min.js", "/web/dataset/call_kw/event.event/get_views"):
            st.ajouter(live.Line(f'2026-10-13 14:00:00.00 odoo18 odoo INFO base werkzeug {PERSONNE} "GET {url} HTTP/1.1" 200 - 77 0.0 5.2'), {PERSONNE: ("inconnu", [], False, None)}, None)
        text = " ".join(" ".join(st.analyze_slow()).split())
        self.assertIn("Python seul en cause (pas la base) : à cet instant charge 1.4 sur 6 cœurs · swap utilisé 0 Mo · mémoire disponible 12.9 Go · attente disque 0 % (pression I/O sur 10 s : 1 %)", T(text))
        self.assertIn("disques : sda disque dur (rotatif), 2 volumes ZFS (type réel : celui des disques du pool)", T(text))
        self.assertIn("la charge, le swap et le disque ne sont PAS en cause à cet instant ; il reste : cache d'Odoo à froid", T(text))
        self.assertIn("assets (JS/CSS) recalculés", T(text))
        self.assertIn("vues ou menus recompilés (cache d'Odoo à froid)", T(text))
        state.update(load=7.0, swap_mb=500, io=(25.0, None))
        text = " ".join(" ".join(st.analyze_slow()).split())
        self.assertIn("causes probables : serveur saturé", T(text))
        self.assertIn("mémoire pleine (swap utilisé)", T(text))
        self.assertIn("disque trop lent (attente disque de 10 % et plus", T(text))
        live.read_state = lambda: None
        self.assertNotIn("Python seul en cause", T(" ".join(st.analyze_slow())))

    def test_attente_disque_et_type_de_disques_dans_l_etat_du_serveur(self):
        """1.46 : etat_systeme() ajoute l'attente disque (iowait de /proc/stat sur ~0,3 s, mémorisée 30 s), la pression I/O du noyau et le type de chaque disque (rotatif ou SSD) ; chacun est facultatif."""
        import builtins
        from unittest import mock
        live = self.module_live()
        stat = iter(["cpu  100 0 50 800 50 0 0 0 0 0\n", "cpu  110 0 55 860 75 0 0 0 0 0\n"])         # +100 au total, +25 d'attente disque : 25 %
        files_read = {"/proc/loadavg": "0.50 0.40 0.30 1/200 999\n", "/proc/meminfo": "MemAvailable:    3145728 kB\nSwapTotal: 1048576 kB\nSwapFree: 1048576 kB\n",
                    "/proc/pressure/io": "some avg10=8.50 avg60=3.00 avg300=1.00 total=1\nfull avg10=2.00 avg60=1.00 avg300=0.50 total=1\n",
                    "/sys/block/sda/queue/rotational": "1\n", "/sys/block/nvme0n1/queue/rotational": "0\n"}
        vrai_open = builtins.open

        def faux_open(path, *a, **k):
            if path == "/proc/stat":
                return mock.mock_open(read_data=next(stat))()
            if path in files_read:
                return mock.mock_open(read_data=files_read[path])()
            return vrai_open(path, *a, **k)
        live._CACHE_IO.update(t=0.0, v=None)
        with mock.patch("builtins.open", faux_open), mock.patch.object(live.os, "listdir", lambda d: ["loop0", "nvme0n1", "sda", "dm-0"] if d == "/sys/block" else []), \
                mock.patch.object(live.time, "sleep", lambda s: None):
            text = live.system_state()
            self.assertIn("attente disque 25 % (pression I/O sur 10 s : 8 %)", T(text.replace("8 %", "8 %")))
            self.assertIn("disques : nvme0n1 SSD, sda disque dur (rotatif)", T(text))
            self.assertNotIn("loop0", T(text))
            self.assertIn("swap utilisé 0 Mo", T(text))
            self.assertEqual(live.io_wait()[0], 25.0)                                          # remembered: /proc/stat is no longer read
        live._CACHE_IO.update(t=0.0, v=None)
        with mock.patch.object(live, "physical_disks", lambda: []), mock.patch.object(live, "io_wait", lambda: None):
            self.assertNotIn("attente disque", T(live.system_state()))

    def test_requetes_lentes_assets_et_vues_cache_a_froid(self):
        """1.48 : assets (/web/assets/…) et get_views lents, tout en Python : cause nommée (cache d'Odoo à froid) et ligne de synthèse quand ils sont la moitié des lentes ou plus ;
        une page ordinaire lente garde la cause générique."""
        live = self.module_live()
        live.system_state = lambda state=None: ""
        st = live.Stats(3.0)

        def request_data(url, py):
            st.ajouter(live.Line(f'2026-10-13 14:47:00.00 odoo18 odoo INFO base werkzeug {PERSONNE} "GET {url} HTTP/1.1" 200 - 12 0.1 {py}'), {PERSONNE: ("inconnu", [], False, None)}, None)
        request_data("/web/assets/1/bc7974c/web.assets_frontend_lazy.min.js", 7.9)
        request_data("/web/dataset/call_kw/event.event/get_views", 8.0)
        request_data("/web/dataset/call_kw/document.page/get_views", 7.9)
        request_data("/es/event/21-ans/track", 10.7)
        text = " ".join(" ".join(st.analyze_slow()).split())
        self.assertIn("assets (JS/CSS) recalculés : normal une fois après un redémarrage", T(text))
        self.assertIn("vues ou menus recompilés (cache d'Odoo à froid)", T(text))
        self.assertIn("3 des 4 requêtes lentes sont des assets ou des vues (cache d'Odoo à froid)", T(text))
        self.assertIn("/es/event/N-ans/track ×1 — 11 s en tout, la pire 10.8 s : temps Python (calcul, attente d'un verrou ou serveur surchargé)", T(text))
        seul = live.Stats(3.0)
        seul.ajouter(live.Line(f'2026-10-13 14:47:00.00 odoo18 odoo INFO base werkzeug {PERSONNE} "GET /es/event/21-ans/track HTTP/1.1" 200 - 12 0.1 9.0'), {PERSONNE: ("inconnu", [], False, None)}, None)
        self.assertNotIn("cache d'Odoo à froid) : Odoo vient", T(" ".join(seul.analyze_slow())))

    def test_a_bannir_jamais_le_serveur_lui_meme(self):
        """1.15 : 127.0.0.1, ::1 et les adresses de ce serveur ne sont jamais proposés par la touche b."""
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        st = live.Stats(5.0)
        for ip in ("127.0.0.1", "127.0.1.1", "::1", "10.9.9.9", DNS):
            st.suspect_ips[ip] += 5
        st.server.add("10.9.9.9")                         # server address, learned by resolution
        self.assertEqual([ip for ip, _ in st.to_ban()], [DNS])

    def test_sondes_locales_et_urls_raccourcies_au_milieu(self):
        """1.16 : les requêtes suspectes du serveur lui-même sont des « sondes », à part ; une URL longue garde sa fin."""
        spec = importlib.util.spec_from_file_location("live", script_path("app-log-live.py"))
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        st = live.Stats(5.0)
        text_line = live.Line('127.0.0.1 - - [09/Oct/2026:09:00:00 +0000] "GET /web/database/manager HTTP/1.1" 200 5')
        st.ajouter(text_line, {}, None)
        self.assertEqual(sum(st.probes.values()), 1)
        self.assertEqual(len(st.suspect_ips), 0)
        self.assertTrue(any("Sondes de ce serveur : 1" in T(x) for x in st.health()[1]))
        u = "/event/journee-portes-ouvertes-sur-linux-2026-125/registration/confirm"
        self.assertTrue(live.short_url(u).endswith("/registration/confirm"))
        self.assertLessEqual(len(live.short_url(u)), 60)
        self.assertEqual(T(live.short_url("/a")), "/a")

    def test_rapport_d_erreurs_a_la_demande_touche_r(self):
        """[6] r : rapport d'erreurs d'après ce qui s'est affiché jusqu'ici."""
        self.journal([werkzeug(PERSONNE, "/event"), odoo("ERROR", "base", "odoo.http", "Exception during request handling.")], after="sleep 8")
        sequence = [(b"Exception during", b"r", 0.5), (b"FIN DU RAPPORT", b"\x03", 0.3)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "5"], sequence, timeout=60)
        self.assertEqual(envoyees, 2, text)
        self.assertIn("RAPPORT D'ERREURS (--report-err)", text)
        self.assertIn("Programme : app-log-live.py v1.", text)

    # --- 1.13 : --exclude-ip, --accentuate-group, --chime, --time-report ------------------------------------------------------------
    def groupe_mock(self):
        self.mock("runuser", f'echo "$@" >> {self.d}/runuser.log; case "$*" in *"count(*) FROM res_partner_category"*Collaborateurs-2026*) printf "1\\n";; \\\n'
                             f'*"count(*) FROM res_partner_category"*) printf "0\\n";; *"SELECT DISTINCT u.login"*) printf "etienne@exemple.org\\n";; \\\n'
                             f'*"FROM res_partner_category c ORDER BY"*) printf "Bénévoles\\nVIP\\n";; *) printf "{UTILISATEURS}";; esac')

    def test_exclure_des_adresses(self):
        """[1] --exclude-ip IP,IP,RÉSEAU : les lignes de ces adresses ne sont ni affichées ni comptées ; une adresse invalide est refusée."""
        self.journal([werkzeug(PERSONNE, "/garde"), werkzeug(DNS, "/exclue-1"), werkzeug(ISP, "/exclue-2"), werkzeug(AUTRE, "/exclue-3"), werkzeug(TROISIEME, "/garde-2")])
        rc, out, err = self.lancer("--no-presence", "--exclude-ip", f"{DNS},{ISP}", "--exclude-ip", "11.101.16.0/24")
        self.assertEqual(rc, 0, err)
        self.assertIn('/garde', out)
        self.assertIn("/garde-2", out)
        for exclue in ("/exclue-1", "/exclue-2", "/exclue-3"):
            self.assertNotIn(exclue, out)
        self.assertIn("Adresses exclues (--exclude-ip) : 93.184.216.34/32, 11.42.88.181/32, 11.101.16.0/24", err)
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "--exclude-ip", "pas-une-adresse,1.2.3.4"])
        self.assertEqual(rc, 2)
        self.assertIn("pas-une-adresse", err)

    def test_groupe_de_contacts_en_blanc_gras_sur_bleu_fonce(self):
        """[2] --accentuate-group NOM : les comptes de l'étiquette de contact Odoo en blanc gras sur bleu foncé ; une étiquette inexistante arrête le programme."""
        self.groupe_mock()
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/autre")])
        text, _ = self.run_pty(["python3", self.prog, "--no-follow", "--no-isp", "--no-presence", "--accentuate-group", "Collaborateurs-2026"], [], keep_ansi=True)
        self.assertRegex(text, r"\x1b\[1;97;(?:48;5;18|44)mÉtienne Dupont")
        self.assertNotRegex(text, r"\x1b\[1;97;(?:48;5;18|44)msrv\.exemple")
        self.assertIn("Groupe « Collaborateurs-2026 » : 1 comptes", text)
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "--no-isp", "--no-presence", "--accentuate-group", "Inexistant"])
        self.assertEqual(rc, 2, err)
        self.assertIn("l'étiquette de contact « Inexistant » n'existe dans aucune base d'Odoo. Étiquettes existantes : Bénévoles, VIP", T(err))
        self.assertNotIn("Traceback", T(err))

    def test_bip_sur_erreur_niveaux_et_byobu(self):
        """[3] --chime N : 0 toute erreur (4xx, 5xx, ERROR d'Odoo), 1 = 4xx, 2 = 5xx et 4xx ; dans tmux/byobu, conseils si le bip est avalé, ou passage direct (allow-passthrough)."""
        def bips(level, flux, env=None):
            self.journal(flux)
            text, _ = self.run_pty(["python3", self.prog, "--no-follow", "--no-history", "--no-isp", "--no-presence", "--chime", str(level)], [], env_extra=env, keep_ansi=True)
            return text
        e404, e500, err = werkzeug(DNS, "/absent", 404), werkzeug(DNS, "/boum", 500), odoo("ERROR", "base", "odoo.http", "Exception")
        ok = werkzeug(DNS, "/ok")
        self.assertNotIn("\x07", T(bips(1, [ok, e500])))                                  # 1 : 4xx seulement
        self.assertIn("\x07", T(bips(1, [ok, e404])))
        self.assertIn("\x07", T(bips(2, [ok, e500])))                                     # 2 : 5xx
        self.assertIn("\x07", T(bips(2, [ok, e404])))                                     # ... et 4xx
        self.assertNotIn("\x07", T(bips(2, [ok, err])))                                # mais pas une erreur d'Odoo
        self.assertIn("\x07", T(bips(0, [ok, err])))                                   # 0 : tout
        self.assertNotIn("\x07", T(bips(0, [ok])))
        self.assertEqual(bips(0, [e404, e500, e404]).count("\x07"), 1, "au plus un bip toutes les 2 secondes")
        # Dans byobu (tmux) : bell-action none et visual-bell on avalent le bip -> conseils
        self.mock("tmux", 'case "$*" in *allow-passthrough*) exit 1;; *bell-action*) echo none;; *visual-bell*) echo on;; esac')
        text = bips(0, [e404], {"TMUX": "/tmp/tmux-0/default,1,0"})
        self.assertIn("bell-action vaut « none »", text)
        self.assertIn("tmux set -g bell-action any", text)
        self.assertIn("visual-bell vaut « on »", text)
        self.assertIn("allow-passthrough on", text)
        # tmux 3.3+ avec allow-passthrough : le BEL traverse tmux jusqu'au terminal, sans conseil
        self.mock("tmux", 'case "$*" in *allow-passthrough*) echo on;; esac')
        text = bips(0, [e404], {"TMUX": "/tmp/tmux-0/default,1,0"})
        self.assertIn("\x1bPtmux;\x07\x1b\\", text)
        self.assertNotIn("bip :", text)

    def test_rapport_periodique(self):
        """[4] --time-report MIN : le rapport de Ctrl-T toutes les MIN minutes."""
        self.journal([werkzeug(PERSONNE, "/event"), werkzeug(DNS, "/boum", 500)], after="sleep 6")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--time-report", "0.03", "--no-keys"])
        self.assertIn("Rapport périodique (--time-report) : toutes les 0.03 minutes", T(err))
        self.assertGreaterEqual(out.count("Rapport périodique (toutes les 0.03 min) : depuis le dernier affichage"), 1, out)
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1", "--time-report", "--no-keys"])
        self.assertIn("toutes les 60 minutes", T(err))                                  # sans valeur : 60
        self.assertNotIn("Rapport périodique (toutes", T(out))

    def test_menu_exclure_groupe_bip_et_rapport(self):
        """[1][2][3][4] Touches e, a, c, T du menu."""
        self.groupe_mock()
        self.journal_tableau(waiting=45)
        sequence = [(b"/event", b"?", 0.4), (b"adresses \xc3\xa0 bannir : 0", b"e", 0.4), (b"vide = aucune", b"93.184.216.34\r", 0.2), (b"--exclude-ip : 93.184.216.34/32", b"e", 0.4),
                    (b"vide = aucune", b"pas-une-adresse\r", 0.2), (b"Adresses refus", b"a", 0.4), (b"vide = aucune ; actuel : aucune", b"Collaborateurs-2026\r", 0.2),
                    (b"1 comptes (les lignes", b"a", 0.4), (b"vide = aucune ; actuel : Collab", b"Inexistant\r", 0.2), (b"existe dans aucune base", b"c", 0.4),
                    (b"Entr\xc3\xa9e = 0", b"1\r", 0.2), (b"--chime 1 (bip", b"T", 0.4), (b"Entr\xc3\xa9e = 60", b"5\r", 0.2), (b"--time-report 5", b"\x03", 0.4)]
        text, envoyees = self.run_pty(["python3", self.prog, "--no-isp", "--no-presence", "--no-banned", "--lines", "1"], sequence, timeout=60, colonnes=200)
        self.assertEqual(envoyees, len(sequence), text)
        menu = text[text.index("Touches (? ou h"):text.index("--exclude-ip : 93.184")]
        for attendu in ("--accentuate-group NOM", "--chime N", "--exclude-ip IP,IP", "--time-report MIN"):
            self.assertIn(attendu, menu)

    # --- 1.14 : visites du site web dans Ctrl-G et Ctrl-T ------------------------------------------------------------------------
    def test_statistiques_des_visites_du_site(self):
        """Visites = pages vues (ni fichiers, ni erreurs, ni requêtes suspectes) ; une adresse qui revient après 30 min est une NOUVELLE visite ; visiteurs : connus, équipe ou lieu, anonymes ;
        les différences (Ctrl-T) ne comptent que la période."""
        live = self.module_live()
        st = live.Stats(5.0)
        database = 1_760_000_000.0

        def request_data(ip, url, code=200, offset=0.0):
            L = live.Line(werkzeug(ip, url, code))
            L.instant = database + offset
            st.pays.setdefault(ip, {"1.1.1.1": "CA", "2.2.2.2": "FR"}.get(ip))
            st.ajouter(L, {ip: ("nom", [], False, None)}, None)
        st.people.add("1.1.1.1")
        st.protected_ones.add("3.3.3.3")
        request_data("1.1.1.1", "/fr_CA/a")
        request_data("1.1.1.1", "/web/assets/1/x.js")                            # fichier : pas une page
        request_data("1.1.1.1", "/b", offset=60)
        request_data("1.1.1.1", "/a", offset=7200)                            # 2 h plus tard : nouvelle visite
        request_data("2.2.2.2", "/a", offset=10)
        request_data("3.3.3.3", "/c", offset=20)
        request_data("4.4.4.4", "/wp-login.php", 404, offset=30)              # erreur : pas une page
        request_data("4.4.4.4", "/x.php", 200, offset=31)                     # suspect : pas une page
        lines = " ".join(" ".join(st.visit_lines()).split())
        self.assertIn("Visites du site : 4 visites · 5 pages vues · 3 visiteurs [1 personnes connues · 1 équipe ou lieu · 1 anonymes] · 1.7 pages par visiteur", T(lines))
        self.assertIn("Pays des visiteurs : CA 1 · FR 1 · pays inconnu 1", T(lines))
        self.assertIn("Pages les plus visitées (réponses sous 400) : /a ×2 ; /fr_CA/a ×1 ; /b ×1 ; /c ×1", T(lines))
        # Ctrl-T: only the period
        before = st.snapshot()
        request_data("2.2.2.2", "/d", offset=7300)
        period = " ".join(" ".join(st.since(before).visit_lines()).split())
        self.assertIn("Visites du site : 1 visites · 1 pages vues · 1 visiteurs [0 personnes connues · 0 équipe ou lieu · 1 anonymes]", T(period))
        self.assertIn("Pages les plus visitées (réponses sous 400) : /d ×1", T(period))
        self.assertEqual(live.Stats(5.0).visit_lines(), [])

    def test_visites_dans_le_tableau_de_bord(self):
        """Ctrl-G : la ligne « Visites du site » avec les pages vues et les visiteurs."""
        self.journal_tableau()
        text, envoyees = self.run_pty(["python3", self.prog, "--no-history", "--no-isp", "--no-presence", "--no-banned", "--lines", "1"],
                                       [(b"/event", b"\x07", 0.8), (b"Top 10 des URLs", b"\x03", 0.5)], timeout=60)
        self.assertEqual(envoyees, 2, text)
        t = " ".join(text.split())
        self.assertRegex(T(t), r"Visites du site : 2 visites · 6 pages vues · 2 visiteurs \[0 personnes connues · 0 équipe ou lieu · 2 anonymes\] · 3\.0 pages par visiteur")
        self.assertIn("Pages les plus visitées (réponses sous 400) : /event ×2", T(t))

    # ---- 1.65: modules table (--modules, M key) and colored figures of "Program efficiency" ----
    ETAT_MODULES = [
        {"nom": "base", "etat": "installed", "version": "18.0.1.3", "auteur": "Odoo S.A.", "maj": "2026-01-05 10:00", "cree": "2026-01-01"},
        {"nom": "event", "etat": "installed", "version": "18.0.1.10", "auteur": "Odoo S.A.", "maj": "2026-03-01 08:00", "cree": "2026-01-01"},
        {"nom": "rlq_survey_report", "etat": "installed", "version": "18.0.1.100.0", "auteur": "Rencontres Linux", "maj": "2026-10-14 09:12", "cree": "2026-10-01"},
        {"nom": "perdu", "etat": "to upgrade", "version": "18.0.1.9", "auteur": "Autre", "maj": "2026-09-02 16:40", "cree": "2026-09-02"},
        {"nom": "ancien", "etat": "uninstalled", "version": "18.0.1.0", "auteur": "X", "maj": "2026-10-20 00:00", "cree": "2026-10-20"},
        {"nom": "sans_date", "etat": "installed", "version": "", "auteur": "Odoo S.A.", "maj": "", "cree": ""}]

    def timezone(self, name):
        old = os.environ.get("TZ")

        def restore():
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()
        self.addCleanup(restore)
        os.environ["TZ"] = name
        time.tzset()

    def noms_modules(self, live, sort_by):
        lines = [ANSI.sub("", l) for l in live.modules_table(self.ETAT_MODULES, "b1", sort_by)]
        return [l.split()[0] for l in lines[2:]], lines

    def test_tableau_des_modules_tris_et_filtre(self):
        live = self.module_live()
        live.COLOR = True
        d = ("date", False, False)
        self.assertEqual(live.read_modules_sort("", d), d)
        self.assertEqual(live.read_modules_sort("n"), ("name", False, False))
        self.assertEqual(live.read_modules_sort("N"), ("name", True, False))
        self.assertEqual(live.read_modules_sort("-version p"), ("version", True, True))
        self.assertEqual(live.read_modules_sort("tous", ("date", False, True)), ("date", False, False))
        self.assertIsNone(live.read_modules_sort("bidon"))
        names, lines = self.noms_modules(live, ("date", False, False))
        self.assertEqual(names, ["rlq_survey_report", "perdu", "event", "base", "sans_date"])        # recent first, without date at the end, "uninstalled" excluded
        self.assertIn("Modules installés (base b1) : 5", T(lines[0]))
        self.assertEqual(self.noms_modules(live, ("date", True, False))[0], ["base", "event", "perdu", "rlq_survey_report", "sans_date"])
        self.assertEqual(self.noms_modules(live, ("name", False, False))[0], ["base", "event", "perdu", "rlq_survey_report", "sans_date"])
        self.assertEqual(self.noms_modules(live, ("name", True, False))[0], ["sans_date", "rlq_survey_report", "perdu", "event", "base"])
        self.assertEqual(self.noms_modules(live, ("version", False, False))[0][:4], ["base", "perdu", "event", "rlq_survey_report"])   # 1.3 < 1.9 < 1.10 < 1.100.0
        self.assertEqual(T(self.noms_modules(live, ("created", False, False))[0][0]), "rlq_survey_report")
        names, lines = self.noms_modules(live, ("name", False, True))
        self.assertEqual(names, ["perdu", "rlq_survey_report"])
        self.assertIn("hors Odoo S.A.", T(lines[0]))
        raw = "\n".join(live.modules_table(self.ETAT_MODULES, "b1", ("name", False, True)))
        self.assertIn(live.color_code(live.ORANGE, "to upgrade"), raw)
        self.assertIn("\x1b[", T(raw))
        self.assertEqual(len(live.modules_table([], "b1")), 1)
        output = live.modules_table(self.ETAT_MODULES, "b1", d, {"base", "event"})
        self.assertIn("✖ perdu", T("\n".join(ANSI.sub("", l) for l in output)))

    def test_derniers_modules_installes_avec_la_version_d_odoo(self):
        """1.70 : --modules-latest N / touche L : les N derniers modules installés (par date de modification), avec la version actuelle d'Odoo."""
        live = self.module_live()
        self.assertEqual(T(live.odoo_version(self.ETAT_MODULES)), "18.0.1.3")
        self.assertEqual(T(live.odoo_version([])), "?")
        lines = [ANSI.sub("", l) for l in live.modules_table(self.ETAT_MODULES, "b1", ("date", False, False), None, 2)]
        self.assertIn("Modules rlq* : 1 (toujours affichés, avec leur version) puis les 2 derniers autres modules installés sur 5", T(lines[0]))
        self.assertIn("Odoo 18.0.1.3", T(lines[0]))
        self.assertEqual([l.split()[0] for l in lines[2:]], ["rlq_survey_report", "perdu", "event"])      # rlq* d'abord, puis 2 autres
        class Faux:
            @staticmethod
            def modules_etat(database):
                return self.ETAT_MODULES
        output = "\n".join(ANSI.sub("", l) for l in live.module_lines(Faux, None, ["b1"], ("date", False, True), 1))
        self.assertIn("derniers autres modules installés sur 2 hors Odoo S.A.", T(output))
        self.assertEqual(T(live.MENU_KEYS[b"L"]), "recent")

    def test_derniers_modules_customs_d_abord(self):
        """1.72 : touche L / --modules-latest : les modules customs (hors Odoo S.A., rlq_*) AVANT les autres, même s'ils sont plus anciens."""
        live = self.module_live()
        state = [{"nom": "web", "etat": "installed", "version": "18.0.1.0", "auteur": "Odoo S.A.", "maj": "2026-10-20 10:00", "cree": "2026-01-01"},
                {"nom": "mail", "etat": "installed", "version": "18.0.1.0", "auteur": "Odoo S.A.", "maj": "2026-10-19 10:00", "cree": "2026-01-01"},
                {"nom": "rlq_vieux", "etat": "installed", "version": "18.0.1.5", "auteur": "Odoo S.A.", "maj": "2026-02-01 10:00", "cree": "2026-01-01"},
                {"nom": "autre_custom", "etat": "installed", "version": "1.0", "auteur": "Moi", "maj": "2026-03-01 10:00", "cree": "2026-01-01"}]
        lines = [ANSI.sub("", l) for l in live.modules_table(state, "b1", ("date", False, False), None, 3)]
        self.assertEqual([l.split()[0] for l in lines[2:]], ["rlq_vieux", "autre_custom", "web", "mail"])      # tous les rlq* d'abord, puis 3 autres (customs d'abord)
        self.assertIn("customs d'abord", T(lines[0]))

    def test_modules_rlq_toujours_tous_affiches_meme_avec_beaucoup_de_customs(self):
        """1.74 : les modules rlq* sont TOUS affichés avec leur version, avant les N derniers autres modules, même si des customs plus récents remplissent la liste."""
        live = self.module_live()
        state = [{"nom": f"autre_{i}", "etat": "installed", "version": "1.0", "auteur": "Moi", "maj": f"2026-10-{10 + i} 10:00", "cree": "2026-01-01"} for i in range(8)]
        state += [{"nom": "rlq_a", "etat": "installed", "version": "18.0.1.105.0", "auteur": "RLQ", "maj": "2026-01-01 10:00", "cree": "2026-01-01"},
                 {"nom": "rlq_b", "etat": "installed", "version": "18.0.2.0.0", "auteur": "RLQ", "maj": "2025-01-01 10:00", "cree": "2026-01-01"}]
        lines = [ANSI.sub("", l) for l in live.modules_table(state, "b1", ("date", False, False), None, 3)]
        names = [l.split()[0] for l in lines[2:]]
        self.assertEqual(names[:2], ["rlq_a", "rlq_b"])
        self.assertEqual(len(names), 5)
        self.assertIn("18.0.1.105.0", T(lines[2]))

    def test_heures_des_modules_en_heure_locale_et_infos_de_demarrage_en_couleurs(self):
        """1.68 : les dates de modules (UTC dans PostgreSQL) sont affichées en heure LOCALE ; lignes « Listes » / « Cache » : chemins et nombres en couleur ; bases illisibles en jaune."""
        live = self.module_live()
        live.COLOR = True
        self.timezone("America/Toronto")
        self.assertEqual(T(live.local_time("2026-10-14 20:11")), "2026-10-14 16:11")
        self.assertEqual(T(live.local_time("2026-01-05 03:30")), "2026-01-04 22:30")                  # EST (winter): previous day
        self.assertEqual(T(live.local_time("2026-10-01")), "2026-10-01")                              # date only, empty: unchanged
        self.assertEqual(T(live.local_time("")), "")
        state = [dict(self.ETAT_MODULES[2], maj="2026-10-14 20:11", cree="2026-10-15 01:30")]
        table_rows = "\n".join(ANSI.sub("", l) for l in live.modules_table(state, "b1", ("date", False, False)))
        self.assertIn("2026-10-14 16:11", T(table_rows))
        self.assertNotIn("20:11", T(table_rows))
        self.assertRegex(T(table_rows), r"2026-10-14 16:11\s+2026-10-14\s")                                  # "seen on": LOCAL day (21:30 the day before)
        class Faux:
            @staticmethod
            def modules_etat(database):
                return state if database == "b1" else None
        raw = "\n".join(ANSI.sub("", l) for l in live.check_modules(Faux, None or self.conf_modules(), ["b1", "b2", "b3"]))
        self.assertIn("2026-10-14 16:11", T(raw))
        self.assertIn("b2, b3", T(raw))
        colored_text = "\n".join(live.check_modules(Faux, self.conf_modules(), ["b2", "b3"]))
        self.assertIn(live.color_code("1;33", "b2"), colored_text)
        info = live.color_info("Listes : liste blanche /etc/default/nginx-tools-white-list.conf (8 adresses) ; lieux /etc/x.conf (0 plages)")
        self.assertEqual(T(ANSI.sub("", info)), "Listes : liste blanche /etc/default/nginx-tools-white-list.conf (8 adresses) ; lieux /etc/x.conf (0 plages)")
        self.assertIn(live.color_code("1", "Listes"), info)
        self.assertIn(live.color_code("36", "/etc/default/nginx-tools-white-list.conf"), info)
        self.assertIn(live.color_code("1;36", "8"), info)
        cache = live.color_info("Cache des adresses : /var/lib/nginx-tools/ip-cache.sqlite (16 adresses, 4 Ko)")
        self.assertIn(live.color_code("1;36", "4 Ko"), cache)
        self.assertIn(live.color_code("36", "/var/lib/nginx-tools/ip-cache.sqlite"), cache)

    def conf_modules(self):
        racine = self.path("addons", "x")
        racine = os.path.dirname(racine)
        os.makedirs(os.path.join(racine, "rlq_survey_report"), exist_ok=True)
        with open(os.path.join(racine, "rlq_survey_report", "__manifest__.py"), "w", encoding="utf-8") as f:
            f.write("{'name': 'x', 'version': '1.100.0'}\n")
        conf = self.path("odoo-heure.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write(f"[options]\naddons_path = {racine}\n")
        return conf

    def test_option_modules_en_ligne_de_commande(self):
        """--modules : tableau puis fin ; --modules-sort invalide : erreur claire."""
        rc, out, err = self.lancer("--modules-sort", "bidon", "--modules")
        self.assertEqual(rc, 2, err)
        self.assertIn("--modules-sort", err)
        rc, out, err = self.lancer("--modules", "--modules-sort=-name", "--modules-custom")
        self.assertEqual(rc, 0, err)
        self.assertIn("Modules", out + err)

    def test_chiffres_mesures_en_couleurs(self):
        live = self.module_live()
        live.COLOR = True
        lines = ["  Programme : CPU 0.4 % · mémoire 39.8 Mo (pic 39.8 Mo) · 15 threads",
                  "  Entrées-sorties : lu 2.6 Mo (55.5 Ko/s, dont disque 0 o) · écrit 168.1 Ko (dont disque 101.5 Ko)",
                  "  Cache des adresses : 99 % des 194 demandes sans recherche extérieure — 147 déjà vues dans cette session, 0 RDAP (cache permanent actif) ; pays : 174 sur 175 déjà connus"]
        for l in lines:
            colored = live.measured_numbers(l)
            self.assertEqual(ANSI.sub("", colored), l)                                       # the text is not modified
            self.assertIn("\x1b[", T(colored))
        c = live.measured_numbers(lines[0])
        for value in ("0.4 %", "39.8 Mo", "15"):
            self.assertIn(live.color_code("1;36", value), c)
        c = live.measured_numbers(lines[1])
        for value in ("2.6 Mo", "55.5 Ko/s", "0 o", "168.1 Ko", "101.5 Ko"):
            self.assertIn(live.color_code("1;36", value), c)
        c = live.measured_numbers(lines[2])
        for value in ("99 %", "194", "147", "174", "175"):
            self.assertIn(live.color_code("1;36", value), c)
        self.assertNotIn("RDAP\x1b", T(c))                                                    # the words are not touched

    def test_groupes_rlq_membres_dans_le_menu_et_le_resume(self):
        """v1.79 : nombre de membres de chaque groupe RLQ* (touche G, résumé Ctrl-C) ; lecture PostgreSQL impossible signalée clairement."""
        live = self.module_live()
        spec = importlib.util.spec_from_file_location("odoo_db_t", script_path("apps/_odoo_db.py"))
        odoo_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(odoo_db)
        odoo_db._requete = lambda database, sql, delay=20: ([["RLQ-JPOL26-Visiteur", "12"], ['{"en_US": "RLQ-JPOL26-Bénévole", "fr_CA": "RLQ-JPOL26-Bénévole"}', "0"],
                                                         ["Autre RLQ", "3"], ["pas un nombre", "x"]] if database == "b1" else None)
        grouped = odoo_db.groupes_rlq("b1")
        self.assertEqual([(g["nom"], g["membres"]) for g in grouped], [("RLQ-JPOL26-Bénévole", 0), ("RLQ-JPOL26-Visiteur", 12)])      # "Autre RLQ" does not start with RLQ
        self.assertIsNone(odoo_db.groupes_rlq("b2"))
        self.assertIsNone(odoo_db.groupes_rlq("b1", prefixe="x'; DROP"))                                                            # prefix never injected
        text = "\n".join(ANSI.sub("", l) for l in live.rlq_group_lines(odoo_db, ["b1", "b2"]))
        self.assertIn("Groupes RLQ* (base b1) : 2 groupes, 12 appartenances", T(text))
        self.assertIn("RLQ-JPOL26-Visiteur = 12", T(text))                                    # 1.85: "name = number"
        self.assertIn("RLQ-JPOL26-Bénévole = 0", T(text))
        self.assertIn("Groupes RLQ* (base b2) : lecture de PostgreSQL impossible", T(text))
        self.assertIn("lecture de PostgreSQL impossible pour cette application", T(live.rlq_group_lines(None, ["b1"])[0]))
        self.assertIn("aucune base", T(live.rlq_group_lines(odoo_db, [])[0]))

    # --- 1.82: latency (does the disk slow down requests?), G and P keys, watched / banned accounts ---
    def _latence(self, live, lent_si_occupe):
        """Moniteur de latence avec un échantillonneur simulé : un échantillon sur trois « disque occupé » (PSI io 25 %, sda 80 %)."""
        class FauxSysperf:
            def __init__(self):
                self.i = 0

            def snapshot(self, **k):
                self.i += 1
                return {"i": self.i, "psi_source": "/sys/fs/cgroup"}

            def rates(self, a, b):
                occupe = b["i"] % 3 == 0
                return {"dt": 30, "wall": time.time(), "cpu": {"busy": 20, "iowait": 5 if occupe else 0.5, "steal": 0},
                        "psi": {"io": {"some": 25 if occupe else 1, "full": 5}, "cpu": {"some": 2}, "memory": {"some": 0}},
                        "disks": {"sda": {"util": 80 if occupe else 5, "r_s": 10, "w_s": 5, "r_await": 15.0, "w_await": 30.0}}}

            def busiest_disk(self, r):
                return "sda", r["disks"]["sda"]["util"]

            def rotational(self, d):
                return True
        m = live.LatencyMonitor(FauxSysperf(), 30)
        m.prev = m.sysperf.snapshot()
        for _ in range(12):
            m.sample()
            for _ in range(30):
                m.request(time.time(), (100, 5, 0.05, (1.5 if m.busy() else 0.1) if lent_si_occupe else 0.1))
        return m

    def test_latence_disque_coupable_ou_innocent(self):
        """1.82 : requêtes lentes seulement quand le disque est occupé → « les DISQUES ralentissent les requêtes … SSD justifiés » ; requêtes rapides
        partout → « les disques ne sont PAS ce qui ralentit les requêtes » ; détail (niveau 6) et tableau par heure (niveau 8)."""
        live = self.module_live()
        texte = T("\n".join(self._latence(live, True).lines(9)))
        self.assertIn("✖ Latence (depuis le départ) — les DISQUES ralentissent les requêtes", texte)
        self.assertIn("100 % des requêtes lentes pendant que le disque était occupé", texte)
        self.assertIn("SSD justifiés", texte)
        self.assertRegex(texte, r"Requêtes Odoo : 360 · médiane [\d.]+ s · 95 % en moins de [\d.]+ s")
        self.assertIn("disque le plus occupé sda 80 % au plus", texte)
        self.assertIn("types : sda HDD", texte)                     # 1.83 : nom du disque + type
        self.assertRegex(texte, r"Par heure\s+requêtes\s+médiane")
        texte = T("\n".join(self._latence(live, False).lines(9)))
        self.assertIn("✔ Latence (depuis le départ) — le disque est occupé par moments (pression d'E-S 9.0 % en moyenne) mais les requêtes ne sont PAS plus lentes à ces moments", texte)
        self.assertIn("des disques SATA suffisent pour cette charge", texte)
        court = T("\n".join(self._latence(live, False).lines(4)))
        self.assertNotIn("Par heure", court)                          # niveau 4 : le verdict seulement
        self.assertNotIn("Requêtes Odoo :", court)
        vide = live.LatencyMonitor(None)
        self.assertEqual(vide.lines(4), [])
        vide.request(time.time(), (1, 1, 0.1, 0.1))
        self.assertIn("pas encore assez de données", T("\n".join(vide.lines(9))))

    def test_ecran_sans_anglais_dans_les_lignes_colorees(self):
        """1.83 : à l'écran, les nombres sont en couleur ; « 95 % under », « at most », « in Python », « of pages », « all tasks » restaient en anglais
        parce que le code de couleur coupait le fragment à traduire. Chemin réel : Output.write (translate_protected sur le texte coloré)."""
        live = self.module_live()
        ecran = "\n".join(ANSI.sub("", live.translate_protected(l)) for l in self._latence(live, False).lines(9))
        for anglais in (" under ", "at most", "on average", "in Python", "all tasks", "busiest disk", "types: "):
            self.assertNotIn(anglais, ecran, ecran)
        self.assertIn("95 % en moins de", ecran)
        robots = ANSI.sub("", live.translate_protected(live.numbers("  Robots: 2 address(es) out of 4 (50 %) · 3 pages seen (23 % of pages)")))
        self.assertIn("(23 % des pages)", robots)
        es = ANSI.sub("", live.translate_protected(live.measured_numbers("  Odoo network connections: chat descriptors: 26/1024 · HTTP descriptors: 59/1024")))
        self.assertIn("descripteurs du chat : 26/1024 · descripteurs HTTP : 59/1024", es)
        self.assertEqual(live.percent_text(1, 297), "<1")
        self.assertEqual(live.percent_text(0, 297), "0")
        self.assertEqual(live.percent_text(99, 297), "33")

    def test_utilisateurs_ssh_et_nombre_de_sessions(self):
        """1.83 : « Connectés en SSH : 3 (etienne ×2, root ×1) » — sessions comptées par compte à partir des processus sshd (sftp sans terminal compris,
        la moitié « [priv] » non comptée), complétées par who (adresse d'origine)."""
        live = self.module_live()
        ps = "/usr/sbin/sshd -D [listener]\nsshd: etienne [priv]\nsshd: etienne@pts/0\nsshd-session: etienne@notty\nsshd: root@pts/1\nbash\n"
        who = "etienne  pts/0        2026-10-16 15:00 (11.97.88.222)\n"
        live.lancer = lambda cmd, delay=10: (0, ps) if cmd[0] == "ps" else (0, who) if cmd[0] == "who" else (0, "a\nb\nc\n")
        live.SSH_PORTS_CACHE.update(when=time.time() + 3600, ports=[3812])
        self.assertEqual(live.ssh_users(), {"etienne": 2, "root": 1})
        ligne = T(ANSI.sub("", live.logged_in_lines(None)[-1]))
        self.assertIn("Connectés en SSH : 3 (etienne ×2, root ×1) — etienne depuis 11.97.88.222 (ouverte le 2026-10-16 15:00, pts/0)", ligne)
        self.assertIn("connexions TCP établies : 3 (port SSH 3812)", ligne)
        live.lancer = lambda cmd, delay=10: (1, "")
        self.assertEqual(T(ANSI.sub("", live.logged_in_lines(None)[-1])), "  Connectés en SSH : 0")

    def test_groupes_rlq_sur_2_ou_4_colonnes(self):
        """1.85 : groupes RLQ* écrits « RLQ23-Bénévole = 11 » (sans « membre(s) »), sur 4 colonnes (terminal large), 2 (moyen) ou 1 (étroit), de haut en bas
        puis de gauche à droite, colonnes équilibrées (9 groupes sur 4 colonnes : 3 + 2 + 2 + 2), alignées même avec un nom chinois."""
        live = self.module_live()
        g = [{"nom": f"RLQ23-G{i}", "membres": i} for i in range(1, 9)] + [{"nom": "RLQ-张三李四", "membres": 1}]
        quatre = [ANSI.sub("", l) for l in live.rlq_group_columns(g, 200)]
        self.assertEqual(len(quatre), 3)
        self.assertRegex(quatre[0], r"^    RLQ23-G1 = 1\s+RLQ23-G4 = 4\s+RLQ23-G6 = 6\s+RLQ23-G8 = 8$")
        self.assertRegex(quatre[1], r"^    RLQ23-G2 = 2\s+RLQ23-G5 = 5\s+RLQ23-G7 = 7\s+RLQ-张三李四 = 1$")
        self.assertNotIn("membre", " ".join(quatre))
        self.assertEqual(live.display_width(quatre[0].split("RLQ23-G8")[0]), live.display_width(quatre[1].split("RLQ-张三李四")[0]))     # aligned columns
        self.assertEqual(len(live.rlq_group_columns(g, 60)), 5)
        self.assertEqual(len(live.rlq_group_columns(g, 20)), 9)
        self.assertEqual(len(live.rlq_group_columns(g[:1], 200)), 1)

    def test_groupes_rlq_homonymes_distingues_par_identifiant_et_categorie(self):
        """1.103 : deux groupes RLQ* qui portent le même nom sont affichés avec leur identifiant « #12 » et leur catégorie « [Événements] » ; un groupe
        sans identifiant garde l'ancien affichage « nom = nombre »."""
        live = self.module_live()
        spec = importlib.util.spec_from_file_location("odoo_db_t2", script_path("apps/_odoo_db.py"))
        odoo_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(odoo_db)
        odoo_db._requete = lambda database, sql, delay=20: ([
            ['{"en_US": "RLQ22-Visiteur", "fr_CA": "RLQ22-Visiteur"}', "70", "13", '{"fr_CA": "Événements", "en_US": "Events"}'],
            ["RLQ22-Visiteur", "0", "9", ""],
            ["RLQ22-Visiteur", "0", "21", '{"en_US": "Events"}'],
        ] if database == "b1" else None)
        grouped = odoo_db.groupes_rlq("b1")
        self.assertEqual([(g["nom"], g["id"], g["membres"], g["categorie"]) for g in grouped],
                         [("RLQ22-Visiteur", 9, 0, ""), ("RLQ22-Visiteur", 13, 70, "Événements"), ("RLQ22-Visiteur", 21, 0, "Events")])
        text = "\n".join(ANSI.sub("", l) for l in live.rlq_group_lines(odoo_db, ["b1"]))
        self.assertIn("RLQ22-Visiteur #9 = 0", T(text))
        self.assertIn("RLQ22-Visiteur #13 [Événements] = 70", T(text))
        self.assertIn("RLQ22-Visiteur #21 [Events] = 0", T(text))
        self.assertEqual(live.rlq_group_label({"nom": "RLQ23-Visiteur", "membres": 4}), "RLQ23-Visiteur")          # sans identifiant : affichage d'avant

    def test_ligne_raccourcie_debut_points_et_deux_derniers_mots(self):
        """1.88 : ligne plus large que la limite = « début ... deux derniers mots » ; « [banned: …] » compte pour UN mot (la fin de l'URL reste) ; le
        remplissage des colonnes est réduit d'abord (une ligne qui tient alors n'est pas coupée) ; couleurs gardées des deux côtés."""
        live = self.module_live()
        live.COLOR = True
        ligne = "2026-10-20 09:05 INFO 11.85.88.10  " + "base werkzeug Hélène Côté" + " " * 30 + 'GET /event/' + "x" * 120 + '/fin" \x1b[31m[banned: CrowdSec]\x1b[0m'
        court = live.shorten_line(ligne, 160)                                         # 1.91: the columns (about 90) fit: only the message is cut
        visible = ANSI.sub("", court)
        self.assertLessEqual(live.display_width(visible), 160)
        self.assertTrue(visible.startswith("2026-10-20 09:05 INFO 11.85.88.10  base werkzeug Hélène Côté" + " " * 30 + "GET /e"), visible)
        self.assertIn("…", visible)
        self.assertTrue(visible.endswith('/fin" [banned: CrowdSec]'), visible)
        self.assertIn("\x1b[31m[banned: CrowdSec]", court)                               # label color kept
        aere = "début" + " " * 80 + "suite et fin"
        coupe = ANSI.sub("", live.shorten_line(aere, 40))                            # 1.91: column padding is NEVER reduced (alignment kept)
        self.assertTrue(coupe.startswith("début" + " " * 20), coupe)
        self.assertLessEqual(live.display_width(coupe), 40)
        self.assertEqual(ANSI.sub("", live.shorten_line("court", 40)), "court")
        self.assertEqual(live.underline_line("\x1b[31ma\x1b[0m b"), "\x1b[4m\x1b[31ma\x1b[0;4m b\x1b[0m")    # underline survives resets
        self.assertEqual(live.underline_line("\x1b[31ma\x1b[0m b", 6), "\x1b[4m\x1b[31ma\x1b[0;4m b   \x1b[0m")   # 1.91: to the end of the screen line

    def test_colonnes_jamais_tassees_pays_noms_anonymises_et_souligne_tous_les_n(self):
        """1.91 : [1] adresse sans pays (boucle locale…) sous les adresses des autres lignes ; noms de l'équipe anonymisés (equipe-xxxxxx) avec --anonymize ;
        [2][3] une ligne trop longue est coupée dans le MESSAGE, jamais dans le remplissage des colonnes ; [4] ligne soulignée jusqu'à $COLUMNS ; [5] --underline N."""
        import donnees_exemples as ex
        noms = ex.PERSONNES_FR[:2]
        ips = ["100.64.1.1", "100.64.1.2"]
        self.liste_blanche("".join(f"{ip}  # {nom}\n" for ip, nom in zip(ips, noms)))
        longue = "/event/journee-portes-ouvertes-2026/page/introduction-" + "x" * 150 + "/fin"
        self.journal([werkzeug(ips[0], "/a"), werkzeug("127.0.0.1", "/b"), werkzeug(ips[1], longue), werkzeug(ips[0], "/c"),
                      odoo("INFO", "base", "odoo.models.unlink", "User #1 deleted ir.attachment records with IDs: [" + ", ".join(str(i) for i in range(80)) + "]")])
        text, _ = super().run_pty(["python3", self.prog, "--no-follow", "--no-min", "--no-history", "--no-isp", "--no-presence", "--no-banned", "--anonymize", "--show-ip", "--truncate",
                                   "--underline", "2"], [], env_extra={"COLUMNS": "230"}, keep_ansi=True)
        lignes = [l for l in text.splitlines() if re.search(r"werkzeug|odoo\.models", ANSI.sub("", l))]
        self.assertEqual(len(lignes), 5, text)
        visibles = [ANSI.sub("", l) for l in lignes]
        for nom in noms:
            self.assertNotIn(nom, text)
        self.assertEqual(sum("equipe-" in v for v in visibles), 3, "\n".join(visibles))
        self.assertEqual(len({v.index("H1.1") for v in visibles[:4]}), 1, "\n".join(visibles))         # aligned columns, even the cut line
        self.assertEqual(visibles[1].index("127.0.0.1"), visibles[0].index("IP-"), "\n".join(visibles))    # l'adresse sans pays sous les autres
        self.assertIn("…", visibles[2])
        debut_message = [v.index("User #1") for v in visibles[4:]]
        self.assertEqual(debut_message, [visibles[0].index('GET')], "\n".join(visibles))                 # Odoo message cut, logger not squeezed
        self.assertEqual([l.startswith("\x1b[4m") for l in lignes], [False, True, False, True, False])
        self.assertEqual(live_width(lignes[1]), 230, lignes[1])                                             # underlined to the end of the screen
        rc, aide, err = self.run_cmd(["python3", self.prog, "--help"], {"APP_LOG_LIVE_LANG": "fr"})
        self.assertIn("--underline [N]", aide)

    def test_troncature_des_lignes(self):
        """1.83 : --truncate [N] coupe chaque ligne affichée à N colonnes (sans N : 2 × $COLUMNS) avec « … », couleurs gardées ; le journal quotidien garde tout."""
        live = self.module_live()
        rouge = "\x1b[31m" + "x" * 50 + "\x1b[0m" + "y" * 50
        coupe = live.truncate_line(rouge, 60)
        self.assertEqual(ANSI.sub("", coupe), "x" * 50 + "y" * 9 + "…")
        self.assertTrue(coupe.endswith("…\x1b[0m"))
        self.assertEqual(live.display_width(live.truncate_line("张三" * 40, 21)), 21)
        self.assertEqual(live.truncate_line("court" + " " * 300, 60), "court")       # padding spaces removed
        self.assertEqual(live.truncate_line("court", 60), "court")
        os.environ["COLUMNS"] = "40"
        try:
            self.assertEqual(live.truncate_text("a" * 200 + "\nb", 0), "a" * 79 + "…\nb")
        finally:
            del os.environ["COLUMNS"]
        ecran = io.StringIO()
        out = live.Output(ecran, self.path("journaux-tronques"), 30, True)
        out.active, out.truncate = True, 30
        out.write("z" * 100 + "\n", stream=True)                                     # 1.88 : seules les lignes du JOURNAL sont raccourcies
        self.assertEqual(ecran.getvalue(), "z" * 29 + "…\n")
        out.write("menu " * 30 + "\n")                                               # menus and reports: never cut
        self.assertIn("menu " * 30, ecran.getvalue())
        out.close()
        with open(out.path, encoding="utf-8") as f:
            self.assertIn("z" * 100, f.read())
        rc, aide, err = self.run_cmd(["python3", self.prog, "--help"], {"APP_LOG_LIVE_LANG": "fr"})
        self.assertIn("--truncate [N]", aide)
        self.assertIn("début … deux derniers mots", " ".join(aide.split()))          # 1.88: $COLUMNS - 10, "start … last two words" (1.123)

    def test_inscriptions_par_evenement_billet_et_sondage_du_billet(self):
        """1.84 (touche I) : regroupement événement -> billet -> LE sondage de ce billet ; une réponse au sondage de l'an dernier ou d'un autre billet n'est
        plus une confirmation (signalée à part) ; nom différent dans le sondage signalé ; annulées grisées et non comptées."""
        live = self.module_live()
        e = {"event_id": 1, "event": "Journée portes ouvertes sur Linux 2026", "event_start": 1792846800}
        def r(nom, billet, tid, sid, sondage, reponse=None, autre=None, etat="open", quand=1792160000):
            return dict(e, id=1, when=quand, ticket_id=tid, ticket=billet, state=etat, name=nom, survey_id=sid, survey=sondage, answer=reponse, other=autre)
        lignes = [r("Frédéric Lapointe", "Visiteur", 1, 2, "Portes ouvertes Linux, 24 oct 2026 (Visiteur)", {"when": 1792161000, "name": "Frédéric Lapointe", "state": "done"}),
                  r("Sora Huang", "Visiteur", 1, 2, "Portes ouvertes Linux, 24 oct 2026 (Visiteur)", {"when": 1792161000, "name": "张三李四", "state": "in_progress"}),
                  r("Chloé Poirier", "Visiteur", 1, 2, "Portes ouvertes Linux, 24 oct 2026 (Visiteur)"),
                  r("MWIKIZA CISIRIKA", "Visiteur", 1, 2, "Portes ouvertes Linux, 24 oct 2026 (Visiteur)", etat="cancel"),
                  r("Hugues Thibodeau", "Bénévole", 2, 3, "Portes ouvertes Linux 24 oct 2026 (Bénévole)",
                    autre={"when": 1761595080, "title": "Aidez-nous à améliorer la Journée Portes Ouvertes Linux 2025", "name": "Hugues Thibodeau", "state": "done"}),
                  dict(r("Ana Tremblay", "Gratuit", 4, 0, ""), event_id=2, event="Rencontre de novembre", event_start=0)]
        texte = "\n".join(ANSI.sub("", live.translate_protected(l)) for l in live.ticket_report(lignes))
        self.assertIn("Journée portes ouvertes sur Linux 2026  (2026-10-24)", texte)
        self.assertIn("Billet « Visiteur » → sondage « Portes ouvertes Linux, 24 oct 2026 (Visiteur) » : 3 inscriptions actives — 1 confirmées, 1 non terminées, 1 sans sondage", texte)
        self.assertRegex(texte, r"Frédéric Lapointe\s+\(open\)  ✔ sondage complété 2026-")
        self.assertIn("⚠ sondage NON terminé", texte)
        self.assertIn("répondu sous le nom 张三李四", texte)
        self.assertRegex(texte, r"Chloé Poirier\s+\(open\)  ✖ aucun sondage de ce billet — inscription non confirmée")
        self.assertRegex(texte, r"MWIKIZA CISIRIKA\s+\(cancel\)  annulée")
        self.assertIn("Billet « Bénévole » → sondage « Portes ouvertes Linux 24 oct 2026 (Bénévole) » : 1 inscriptions actives — 0 confirmées", texte)
        self.assertIn("(a répondu à un AUTRE sondage, non compté : « Aidez-nous à améliorer la Journée Portes Ouvertes Linux 2025 », 2025-10-27", texte)
        self.assertIn("Billet « Gratuit » : aucun sondage lié à ce billet — 1 inscriptions actives", texte)
        noms = [l for l in texte.splitlines() if "(open)" in l or "(cancel)" in l]
        self.assertEqual(len({l.index("(") for l in noms}), 1, noms)                      # state column aligned (Chinese names included)
        self.assertEqual(live.ticket_report([]), ["    none"])

    def test_registrations_by_ticket_requete_et_lecture(self):
        """_odoo_db 1.15 : sondage attendu = celui du billet (rlq_survey_id), sinon celui de l'événement ; réponse cherchée DANS ce sondage seulement ; lecture seule."""
        spec = importlib.util.spec_from_file_location("odoo_db_rbt", script_path("apps/_odoo_db.py"))
        odoo_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(odoo_db)
        vues = []
        def requete(base, sql, delai=20):
            vues.append(sql)
            if "information_schema" in sql:
                return [["1"]] if "event_event_ticket" in sql else []
            return [["5", "1792160000", "1", "JPO 2026", "1792846800", "2", "Bénévole", "open", "Pierre", "3", "JPO (Bénévole)", "", "", "", "1761595080", "JPO 2025", "Pierre", "done"]]
        odoo_db._requete = requete
        res = odoo_db.registrations_by_ticket("b1")
        self.assertEqual(res[0]["survey"], "JPO (Bénévole)")
        self.assertIsNone(res[0]["answer"])
        self.assertEqual(res[0]["other"]["title"], "JPO 2025")
        sql = vues[-1]
        self.assertIn("LEFT JOIN survey_survey s ON s.id = COALESCE(t.rlq_survey_id, 0)", sql)
        self.assertIn("WHERE i.survey_id = s.id", sql)
        self.assertNotIn("e.survey_id", sql)                                              # column absent: never used
        odoo_db._requete = lambda base, sql, delai=20: []                                  # ni rlq_survey_id ni survey_id : l'ancien rapport
        self.assertIsNone(odoo_db.registrations_by_ticket("b1"))

    def test_courriel_envoye_nom_du_destinataire_et_titre(self):
        """1.84 : « Mail (mail.mail) with ID 7573 … to (redacted) 'a***n@x' successfully sent » devient « Courriel no 7573 envoyé à NOM (a***n@x) — « sujet » — inscription … » ;
        Message-Id vérifié (jamais le courriel d'une autre base) ; rien trouvé : la ligne d'Odoo reste."""
        live = self.module_live()
        brut = ("2026-10-16T11:25:41.920000-04:00 odoo18 odoo[1]: 2026-10-16 15:25:41,920 1969 INFO ? odoo.addons.mail.models.mail_mail: Mail (mail.mail) with ID 7573 "
                "and Message-Id '<398.1792164279-event.registration@odoo18>' from 'admin@exemple.org' to (redacted) 'a********ai@exemple.ca' successfully sent")
        appels = []
        class FauxDb:
            @staticmethod
            def mail_detail(base, mail_id, message_id, delai=10):
                appels.append((base, mail_id, message_id))
                return {"subject": "Confirmation : JPO 2026", "recipients": ["Ana Tremblay"], "record": "registration Ana Tremblay — JPO 2026"} if base == "b2" else {}
        class Gens:
            odoo_db = FauxDb()
            databases_seen = {"b1": 1, "b2": 1}
        texte = ANSI.sub("", live.translate_protected(live.mail_sent_text(live.Line(brut), Gens())))
        self.assertEqual(texte, "Courriel no 7573 envoyé à Ana Tremblay (a********ai@exemple.ca) — « Confirmation : JPO 2026 » — Inscription : Ana Tremblay — JPO 2026")
        self.assertEqual(appels, [("b1", "7573", "<398.1792164279-event.registration@odoo18>"), ("b2", "7573", "<398.1792164279-event.registration@odoo18>")])
        live.MAIL_CACHE.clear()
        class Vide(Gens):
            odoo_db = type("V", (), {"mail_detail": staticmethod(lambda *a, **k: {})})()
        self.assertIsNone(live.mail_sent_text(live.Line(brut), Vide()))
        self.assertIsNone(live.mail_sent_text(live.Line(brut.replace("successfully sent", "x")), Gens()))
        self.assertTrue(live.MAIL_TOTAL_RE.search("Total emails tried by SMTP: 1"))
        self.assertFalse(live.MAIL_TOTAL_RE.search("Total emails tried by SMTP: 12"))

    def test_touches_g_et_p_reliees(self):
        """1.82 : la touche G (membres des groupes RLQ*) était décrite dans le menu mais jamais reliée ; P = latence."""
        live = self.module_live()
        self.assertEqual(live.MENU_KEYS.get(b"G"), "G")
        self.assertEqual(live.MENU_KEYS.get(b"Y"), "latency")       # 1.113: P prints the buffer, Y is the latency report
        self.assertEqual(live.MENU_KEYS.get(b"P"), "print")
        self.assertEqual(live.MENU_KEYS.get(b"f"), "refresh")
        self.assertEqual(len(set(live.MENU_KEYS)), len(live.MENU_KEYS))

    def test_comptes_surveilles_et_bannis_marques(self):
        """1.82 : le nom d'un compte du registre de web-monitor.py est suivi de « [surveillé] » ou « [compte banni] »."""
        live = self.module_live()
        registre = self.path("state", "odoo-users.tsv")
        with open(registre, "w") as f:
            f.write("2026-10-16T09:00:00-04:00\twatched\tbase\t849\tghost@exemple.org\t11.95.32.106\tt\n"
                    "2026-10-16T09:00:00-04:00\tbanned\tbase\t850\tspam@exemple.org\t1.2.3.4\tt\n")
        ancien = os.environ.get("NGINX_TOOLS_ODOO_USERS")
        os.environ["NGINX_TOOLS_ODOO_USERS"] = registre
        try:
            live.ODOO_USERS_CACHE["when"] = 0.0
            p = live.People.__new__(live.People)
            p.databases_seen = {}
            self.assertEqual(T(p.tag([("base", "ghost@exemple.org")], "ghost")), "ghost [surveillé]")
            self.assertEqual(T(p.tag([("base", "spam@exemple.org")], "spam")), "spam [compte banni]")
            self.assertEqual(p.tag([("base", "ana@exemple.org")], "ana"), "ana")
        finally:
            os.environ["NGINX_TOOLS_ODOO_USERS"] = ancien or "off"
        self.assertEqual(live.display_width("张三李四"), 8)

    def test_112_temps_fractions_de_jour_fenetre_et_commandes_journalctl(self):
        """1.112 : --since / --until (formats, relatifs, epoch), --days fractionnaire, options journalctl transmises en epoch."""
        live = self.module_live()
        now = time.time()
        self.assertAlmostEqual(live.parse_time("-2h"), now - 7200, delta=5)
        self.assertAlmostEqual(live.parse_time("0.5 hour"), now - 1800, delta=5)
        self.assertAlmostEqual(live.parse_time("+1 day"), now + 86400, delta=5)
        self.assertEqual(live.parse_time("@1700000000"), 1700000000.0)
        with self.assertRaises(ValueError):
            live.parse_time("n'importe quoi")
        self.assertEqual(live.days_window(30), ["--since", "-30 days"], "un nombre entier de jours garde sa forme d'origine")
        self.assertEqual(live.days_window(0.1)[0], "--since")
        self.assertTrue(live.days_window(0.1)[1].startswith("@"), "0.1 jour = 2,4 heures : une date epoch")

        class Args:
            pass
        args = Args()
        args.lines, args.no_follow, args.since_epoch, args.until_epoch = 50, False, 1700000000.5, None
        args.no_hostname, args.grep, args.grep_sensitive = True, "Foo", True
        cmd = live.stream_command(args, {}, "odoo", None)
        self.assertIn("--no-hostname", cmd)
        self.assertIn("--case-sensitive=yes", cmd)
        self.assertIn("@1700000000", cmd)
        self.assertIn("Foo", cmd)

    def test_112_fenetre_grep_et_pays_des_lignes(self):
        """1.112 : --until arrete la fenetre, --grep teste chaque ligne, --country garde le pays de l'adresse du client."""
        live = self.module_live()
        opts = {"since": 100.0, "until": 200.0, "grep": re.compile("erreur", re.I), "countries": {"CA"}, "exclude_countries": None}
        state = {}
        L = live.Line("2026-10-29T10:00:00.000000-0400 odoo[1]: erreur B")
        L.instant = 150.0
        self.assertTrue(live.window_keep(L, state, opts))
        L.instant = 250.0
        self.assertFalse(live.window_keep(L, state, opts), "apres --until : hors fenetre")
        pays = {"11.1.1.1": "CA", "8.8.8.8": "US"}
        L.instant = 150.0
        self.assertTrue(live.country_keep(L, [("11.1.1.1", None, None)], pays, {}, opts))
        self.assertFalse(live.country_keep(L, [("8.8.8.8", None, None)], pays, {}, opts))
        self.assertFalse(live.country_keep(L, [], {}, {}, opts), "ligne horodatee sans adresse : cachee par --country")

    def test_113_barre_d_etat_couleur_et_injection_sql(self):
        """1.113 : barre d'état (blanc, vert, jaune, rouge selon les problèmes comptés) et détection des injections SQL sur l'URL décodée."""
        live = self.module_live()
        bar = live.StatusBar()
        self.assertEqual(bar.color(), "37", "rien à signaler : blanc")
        attaque = live.Line('2026-10-29T10:00:00.000000-0400 odoo[1]: 2026-10-29 14:00:00,000 1 INFO db werkzeug: 11.1.1.1 - - "GET /shop?id=1%20UNION%20SELECT%20password HTTP/1.1" 500 - 1 0.1 0.2')
        self.assertTrue(live.SQLI_RE.search("/shop?id=1 UNION SELECT password"), "UNION SELECT détecté")
        self.assertTrue(live.SQLI_RE.search("/x?a=' or 1=1"), "tautologie détectée")
        self.assertFalse(live.SQLI_RE.search("/web/image/12/logo.png"), "URL normale ignorée")
        bar.observe(attaque, None, 5.0)
        self.assertEqual((bar.sqli, bar.e5), (1, 1))
        self.assertEqual(bar.color(), "37", "1.119 : une injection et une erreur 5xx ne changent pas la couleur (seules les connexions de plus de 9 s)")
        lente = live.Line('2026-10-29T10:00:00.000000-0400 odoo[1]: 2026-10-29 14:00:00,000 1 INFO db werkzeug: 11.1.1.1 - - "GET /lent HTTP/1.1" 200 - 1 5.0 6.0')
        bar.observe(lente, None, 5.0)
        self.assertEqual(bar.color(), "32", "une connexion de plus de 9 s : vert")
        for _ in range(4):
            bar.observe(lente, None, 5.0)
        self.assertEqual(bar.color(), "33", "cinq connexions de plus de 9 s : jaune")
        for _ in range(15):
            bar.observe(lente, None, 5.0)
        self.assertEqual(bar.color(), "31", "vingt connexions de plus de 9 s : rouge")
        rapide = live.Line('2026-10-29T10:00:00.000000-0400 odoo[1]: 2026-10-29 14:00:00,000 1 INFO db werkzeug: 11.1.1.1 - - "GET /vite HTTP/1.1" 200 - 1 0.1 8.0')
        bar.reset()
        bar.observe(rapide, None, 5.0)
        self.assertEqual(bar.color(), "37", "8 s : pas plus de 9 s, la barre ne change pas")
        self.assertEqual((bar.sqli, bar.e5, bar.slow), (0, 0, 0), "Ctrl-T ou g : bilan remis à zéro")
        self.assertIn("SQLi", bar.summary())

    def test_114_ip_principales_et_alerte_rouge(self):
        """1.114 : la barre d'état nomme les trois adresses les plus fautives (masquées sans --show-ip) et l'alerte rouge ne se répète pas."""
        live = self.module_live()
        bar = live.StatusBar(show_ips=True)
        attaque = live.Line('2026-10-29T10:00:00.000000-0400 odoo[1]: 2026-10-29 14:00:00,000 1 INFO db werkzeug: 11.1.1.1 - - "GET /shop?id=1%20UNION%20SELECT%20password HTTP/1.1" 500 - 1 0.1 0.2')
        for _ in range(3):
            bar.observe(attaque, None, 5.0, "11.1.1.1")
        bar.observe(attaque, None, 5.0, "22.2.2.2")
        self.assertIn("11.1.1.1 ×3", bar.summary(), "l'adresse la plus fautive est nommée avec son compte")
        self.assertIn("22.2.2.2 ×1", bar.summary())
        cachee = live.StatusBar(show_ips=False)
        cachee.observe(attaque, None, 5.0, "11.1.1.1")
        self.assertNotIn("11.1.1.1", cachee.summary(), "adresse cachée sans --show-ip")
        self.assertNotIn("(--show-ip)", cachee.summary(), "1.116 : aucun texte sur les adresses masquees")
        self.assertFalse(bar.alerted, "pas d'alerte avant le passage au rouge")
        bar.alerted = True
        bar.reset()
        self.assertFalse(bar.alerted, "Ctrl-T ou g réarme l'alerte")
        self.assertEqual(bar.problems_by_ip, {}, "le palmarès repart à zéro")


class AppLogLive120(unittest.TestCase):
    """1.120: santé sur 100, compteurs de la barre d'état, copie HTML du journal (140 caractères par ligne), ligne de statut automatique."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("live120", script_path("app-log-live.py"))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_120_ligne_html_coupee_a_140_caracteres(self):
        texte = "\x1b[33m" + "x" * 300
        out = self.m.html_line(texte)
        self.assertEqual(out.count("x"), 140)
        self.assertIn('<span style="color:#c69026">', out)

    def test_120_html_echappe_et_couleurs(self):
        out = self.m.ansi_to_html("\x1b[1;31mERR\x1b[0m <a> \x1b[4mu\x1b[0m")
        self.assertIn('<span style="font-weight:bold;color:#e5534b">ERR</span>', out)
        self.assertIn("&lt;a&gt;", out)
        self.assertIn("text-decoration:underline", out)

    def test_120_sante_baisse_avec_les_attaques_et_se_reinitialise(self):
        sb = self.m.StatusBar()
        self.assertEqual(sb.health(), 100)
        sb.sqli, sb.e5, sb.e4, sb.banned, sb.slow = 2, 1, 10, {"1.2.3.4"}, 3
        self.assertEqual(sb.health(), 100 - (6 + 2 + 1 + 2 + 3))
        sb.reset()
        self.assertEqual((sb.health(), sb.sql_max, sb.odoo_err), (100, 0, 0))

    def test_120_barre_d_etat_contient_les_nouveaux_compteurs(self):
        sb = self.m.StatusBar()
        sb.sql_max, sb.odoo_err = 7, 2
        texte = sb.summary(users=3, ssh=1)
        for morceau in (self.m.TR("health state") + " 100 %", self.m.TR("max SQL") + " 7", self.m.TR("Odoo errors") + " 2",
                        self.m.TR("Odoo users") + " 3", self.m.TR("SSH") + " 1"):
            self.assertIn(morceau, texte)

    def test_120_journal_html_un_fichier_par_jour(self):
        import tempfile
        dossier = tempfile.mkdtemp()

        class Ecran:
            def write(self, texte):
                pass

        sortie = self.m.Output(Ecran(), folder=dossier, keep_days=30, screen_color=False)
        sortie._open("2026-10-30")
        sortie.active = True
        sortie.write("bonjour <b>\n")
        sortie._open("2026-10-31")
        sortie.close()
        with open(os.path.join(dossier, "app-log-live-2026-10-30.html"), encoding="utf-8") as f:
            jour1 = f.read()
        with open(os.path.join(dossier, "app-log-live-2026-10-31.html"), encoding="utf-8") as f:
            jour2 = f.read()
        self.assertIn("bonjour &lt;b&gt;", jour1)
        self.assertTrue(jour1.rstrip().endswith("</html>"))
        self.assertEqual(jour2.count("<!doctype html>"), 1)
        self.assertTrue(jour2.rstrip().endswith("</html>"))

    def test_120_lignes_de_statut_automatiques(self):
        self.assertGreaterEqual(self.m.terminal_rows(), 10)
        self.assertEqual(self.m.STATUS_EVERY_DEFAULT, -1)


def _charger_live_123():
    """Module app-log-live.py, chargé comme les autres tests (--log-merge, --status-header, niveaux sur 4 caractères)."""
    spec = importlib.util.spec_from_file_location("live_123", script_path("app-log-live.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppLogLive123(EnvTest):
    """1.123 : --log-merge fusionne la ligne nginx et la ligne Odoo d'une même requête ; --status-header sort la date et l'hôte des lignes ; les niveaux
    s'écrivent sur 4 caractères (ERR, WARN) et le protocole en H1.1."""
    NGINX = ('2026-10-31T09:53:27.000000-0400 odoo18 http: 179.201.24.98 - - "GET /web/abc?lang=en_CA HTTP/1.1" 303 345 '
             '"https://exemple.org/" "Mozilla/5.0" host=exemple.org rl=864')
    ODOO = ('2026-10-31T09:53:27.790000-0400 odoo18 odoo[1]: 2026-10-31 05:53:27,790 1 INFO base werkzeug: 179.201.24.98 - - '
            '[31/Oct/2026 09:53:27] "GET /web/abc?lang=en_CA HTTP/1.1" 303 - 1 0.000 0.002')

    def setUp(self):
        super().setUp()
        self.m = _charger_live_123()
        self.prog = self.prepare("app-log-live.py")
        self.mock("fail2ban-client", "exit 1")
        self.mock("ipset", "exit 1")
        self.mock("systemctl", 'case "$*" in *list-unit-files*erplibre.service*) echo "erplibre.service enabled enabled";; esac; exit 0')

    def journal_123(self, lines):
        """Flux du journal simule (comme AppLogLive.journal)."""
        self.write("stream.txt", "\n".join(lines) + "\n")
        self.mock("journalctl", f'echo "$@" >> {self.d}/journalctl.log; case "$*" in *" -g "*) cat {self.d}/history.txt;; '
                                f'*) cat {self.d}/stream.txt;; esac')

    def lancer_123(self, *options):
        return self.run_cmd(["python3", self.prog, "--no-follow", "--log-nginx", "--no-history", "--no-isp", "--no-presence",
                             "--no-banned", "--show-ip", "--no-min", "--service", "erplibre.service", *options])

    def test_bout_en_bout_une_ligne_par_requete_avec_log_merge(self):
        self.journal_123([self.NGINX, self.ODOO])
        rc, out, err = self.lancer_123("--log-merge")
        requetes = [l for l in out.splitlines() if "GET" in l]
        self.assertEqual(len(requetes), 1, out)
        self.assertIn("H1.1 303", requetes[0])
        self.assertIn("0.002", requetes[0])
        rc, out, err = self.lancer_123()                                             # sans --log-merge : les deux lignes restent
        self.assertEqual(len([l for l in out.splitlines() if "GET" in l]), 2, out)

    def test_bout_en_bout_status_header_date_et_hote_dans_la_barre(self):
        """1.125 : l'heure reste sur la ligne ; la date (sans l'heure) et l'hôte sont au début de la barre d'état."""
        self.journal_123([self.ODOO])
        rc, out, err = self.lancer_123("--status-header", "--status-every", "1")
        ligne = [l for l in out.splitlines() if "GET" in l]
        self.assertEqual(len(ligne), 1, out)
        self.assertNotIn("odoo18", ligne[0])                                         # l'hôte n'est plus dans la ligne
        self.assertNotIn("2026-10-31", ligne[0])                                     # ni la date
        self.assertIn("09:53:27.79", ligne[0])                                       # mais l'heure, oui
        self.assertRegex(out, r"(?m)^ 2026-10-31 odoo18  ", out)                     # date et hôte au début de la barre d

    def _item(self, raw):
        L = self.m.Line(raw)
        return (L, [], 0.0, False)

    def test_fusion_une_seule_ligne_avec_les_temps_d_odoo(self):
        held = collections.deque()
        self.assertEqual(self.m.merge_step(self._item(self.NGINX), held), [])          # attend sa ligne Odoo
        ready = self.m.merge_step(self._item(self.ODOO), held)
        self.assertEqual(len(ready), 1, "une seule ligne doit sortir de la paire")
        L = ready[0][0]
        self.assertEqual(L.odoo_times, ("1", "0.000", "0.002"))
        shown = self.m.Formatting(False, 40, 0.0, False).format_value(L, {}, False)
        self.assertIn("H1.1 303", shown)
        self.assertEqual(shown.count("GET"), 1, shown)
        self.assertEqual(len(held), 0)

    def test_ligne_nginx_sans_partenaire_affichee_seule_apres_l_attente(self):
        held = collections.deque()
        self.assertEqual(self.m.merge_step(self._item(self.NGINX), held), [])
        self.assertEqual(self.m.merge_release(held, time.time()), [])                  # pas encore : attente de MERGE_HOLD secondes
        alone = self.m.merge_release(held, time.time() + self.m.MERGE_HOLD + 1)
        self.assertEqual(len(alone), 1)
        self.assertIsNone(alone[0][0].odoo_times)

    def test_requete_differente_pas_fusionnee(self):
        held = collections.deque()
        autre = self.ODOO.replace("303 - 1", "404 - 1")                               # même URL, statut différent
        self.m.merge_step(self._item(self.NGINX), held)
        ready = self.m.merge_step(self._item(autre), held)
        self.assertEqual(ready, [])                                                   # 1.135: la ligne Odoo attend, elle aussi, sa ligne nginx
        self.assertEqual(len(held), 2)                                                # les deux attendent ...
        released = self.m.merge_release(held, time.time() + 10)                       # ... puis sont affichées seules après MERGE_HOLD
        self.assertEqual(len(released), 2)
        self.assertTrue(all(item[0].odoo_times is None for item in released))

    def test_niveau_sur_4_caracteres(self):
        erreur = self.m.Line("2026-10-31T09:53:28.000000-0400 odoo18 odoo[1]: 2026-10-31 05:53:28,000 1 ERROR base odoo.http: Exception")
        shown = self.m.Formatting(False, 40, 0.0, False).format_value(erreur, {}, False)
        self.assertIn("ERR", shown)
        self.assertNotIn("ERROR", shown)

    def test_status_header_heure_sans_date_ni_hote_dans_la_ligne(self):
        """1.125 : avec STATUS_HEADER la ligne garde l'heure (sans la date) ; l'hôte n'est pas dans la ligne."""
        ligne = self.m.Line(self.ODOO)
        normal = self.m.Formatting(False, 40, 0.0, False).format_value(ligne, {}, False)
        sans = self.m.Formatting(False, 40, 0.0, True).format_value(ligne, {}, False)
        self.assertIn("2026-10-31 09:53:27.79", normal)
        self.assertIn("09:53:27.79", sans)
        self.assertNotIn("2026-10-31", sans)
        self.assertNotIn("odoo18", sans)
        self.assertIn("INFO", sans)

    def test_criticite_vert_jaune_rouge(self):
        """1.125 : couleur d'un chiffre de la barre selon sa criticité."""
        self.assertEqual(self.m.criticite(0, 1, 5), "32")
        self.assertEqual(self.m.criticite(1, 1, 5), "33")
        self.assertEqual(self.m.criticite(4, 1, 5), "33")
        self.assertEqual(self.m.criticite(5, 1, 5), "31")

    def test_barre_chiffres_colores_par_criticite(self):
        """1.125 : le total 5xx (5 réponses) et chaque code sont des morceaux colorés en rouge ; les libellés restent sans couleur."""
        bar = self.m.StatusBar(show_ips=False)
        for _ in range(5):
            line = self.m.Line('2026-10-31T09:53:27.790000-0400 odoo18 odoo[1]: 2026-10-31 05:53:27,790 1 INFO base werkzeug: 1.2.3.4 - - '
                               '[31/Oct/2026 09:53:27] "GET /x HTTP/1.1" 500 - 1 0.000 0.002')
            bar.observe(line, None, 9.0)
        pieces = bar.pieces()
        self.assertIn(("5", "31"), pieces)
        self.assertIn(("0", "32"), pieces)                                           # 0 banni, 0 injection : vert
        self.assertEqual("".join(t for t, _ in pieces), bar.summary())

    def test_nom_du_domaine_rlq_affiche_en_tag_RLQ(self):
        """1.127 : ".rencontres-linux.quebec" est affiché ".RLQ." (en couleur) ; le reste du nom ne change pas ; les autres noms restent intacts."""
        name, _parts, _raw, _cat = self.m.render("dns", "odoo18.rencontres-linux.quebec", "1.2.3.4", False)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", name)
        self.assertEqual(plain, "odoo18.RLQ.")
        self.assertIn(self.m.color_code(self.m.STYLES["place"], ".RLQ."), name)     # the tag is in colour
        autre, _p, _r, _c = self.m.render("dns", "srv.exemple.org", "1.2.3.4", False)
        self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", autre), "srv.exemple.org")

    def test_texte_de_la_ligne_domaine_RLQ_et_url_decodee(self):
        """1.128 : dans le texte de la ligne, le domaine devient .RLQ (referer et host=) ; une URL codée en %XX est affichée décodée."""
        raw = ("2026-10-31T13:02:01.000000-0400 odoo18 nginx[123]: 1.2.3.4 - - [31/Oct/2026:13:02:01 -0400] "
               "\"GET /web/image/8982-89f82e4c/Article%20de%20blog%20'Saint-Hyacinthe,%2015%20juin%202026'%20cover%20image.webp HTTP/1.1\" 200 15203 "
               "\"https://odoo-dev.rencontres-linux.quebec/\" \"Mozilla/5.0\" host=odoo-dev.rencontres-linux.quebec rl=95")
        shown = self.m.Formatting(False, 40, 0.0, False).format_value(self.m.Line(raw), {}, False)
        plain = re.sub(r"\x1b\[[0-9;]*m|[\ue000-\uf8ff]", "", shown)           # colours (and their markers, without colour) removed
        self.assertIn('"https://odoo-dev.RLQ/"', plain)
        self.assertIn("host=odoo-dev.RLQ rl=95", plain)
        self.assertNotIn("rencontres-linux", plain)
        self.assertIn("/web/image/8982-89f82e4c/Article de blog 'Saint-Hyacinthe, 15 juin 2026' cover image.webp", plain)
        self.assertNotIn("%20", plain)

    def test_version_du_navigateur_n_est_pas_une_adresse(self):
        """1.129 : Chrome/146.0.0.0 dans le User-Agent n'est pas une adresse IP (pas de nom ni de pays à la place de la version) ;
        une adresse dans une URL (https://1.2.3.4/) ou en texte reste reconnue."""
        self.assertEqual(self.m.find_ips("GET /x - Mozilla/5.0 (Macintosh) Chrome/146.0.0.0 Safari/537.36 host=rencontres-linux.quebec"), [])
        self.assertEqual([ip for _, _, ip in self.m.find_ips("GET https://1.2.3.4/ from 87.192.109.76")], ["1.2.3.4", "87.192.109.76"])

    def test_config_merge_garde_les_valeurs_et_sauvegarde(self):
        """1.125 : --config-merge réécrit depuis la nouvelle configuration, garde les valeurs réglées, sauvegarde l'ancien fichier."""
        conf = os.path.join(self.d, "merge.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write("SLOW=7\nFOO=bar\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = self.m.config_merge(conf)
        self.assertEqual(rc, 0)
        texte = open(conf, encoding="utf-8").read()
        self.assertRegex(texte, r"(?m)^SLOW=7$")
        self.assertNotIn("FOO", texte)                                               # clé inconnue : écartée
        self.assertRegex(texte, r"(?m)^#STATUS_HEADER=no$")                          # la nouvelle valeur par défaut est présente
        backups = [n for n in os.listdir(self.d) if n.startswith("merge.conf.bak-")]
        self.assertEqual(len(backups), 1, backups)
        self.assertIn("FOO=bar", open(os.path.join(self.d, backups[0]), encoding="utf-8").read())
        self.assertIn("FOO", out.getvalue())                                         # signalée

    def test_bout_en_bout_bar_de_statut_apres_l_historique(self):
        """1.125 : la barre de statut est affichée une fois au démarrage, après les lignes de l'historique (sans barre périodique : --status-every -1 seulement)."""
        self.journal_123([self.ODOO])
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "--log-nginx", "--no-isp", "--no-presence", "--no-banned", "--show-ip",
                                     "--no-min", "--service", "erplibre.service", "--status-every", "-1", "--status-header"])
        self.assertEqual(rc, 0, err)
        barre = re.search(r"ÉTAT|STATUS", out)
        self.assertIsNotNone(barre, out)
        self.assertGreater(barre.start(), out.rindex("GET"), out)                   # après TOUTES les lignes de l'historique
        self.assertRegex(out, r"(?m)^ 2026-10-31 odoo18  ÉTAT", out)                # 1.126: la date et l'hôte sont au début de la barre (avant ÉTAT)

    def test_barre_de_statut_4xx_et_5xx_par_code(self):
        """1.124 : la barre d'état sépare les réponses 4xx et 5xx par code (403, 404, 500...)."""
        bar = self.m.StatusBar(show_ips=False)
        for code in (403, 404, 404, 500):
            line = self.m.Line(f'2026-10-31T09:53:27.790000-0400 odoo18 odoo[1]: 2026-10-31 05:53:27,790 1 INFO base werkzeug: 1.2.3.4 - - '
                               f'[31/Oct/2026 09:53:27] "GET /x HTTP/1.1" {code} - 1 0.000 0.002')
            bar.observe(line, None, 9.0)
        text = bar.summary()
        self.assertIn("4xx 3 (403: 1 · 404: 2)", text)
        self.assertIn("5xx 1 (500: 1)", text)
        self.assertIn("4xx 0", self.m.StatusBar(show_ips=False).summary())           # rien à séparer : le total seul

    def test_cles_de_configuration_log_merge_et_status_header(self):
        """1.124 : LOG_MERGE et STATUS_HEADER sont lues dans le fichier de configuration (comme les autres options)."""
        self.assertEqual(self.m.SCHEMA_CONFIG["LOG_MERGE"][0], "log_merge")
        self.assertEqual(self.m.SCHEMA_CONFIG["STATUS_HEADER"][0], "status_header")

    def test_bout_en_bout_configuration_fusion_et_en_tete(self):
        """1.124 : LOG_MERGE=yes et STATUS_HEADER=yes dans un fichier (-c) donnent la même sortie que les options de la ligne de commande."""
        self.journal_123([self.NGINX, self.ODOO])
        conf = os.path.join(self.d, "app-log-live.conf")
        with open(conf, "w", encoding="utf-8") as f:
            f.write("LOG_NGINX=yes\nLOG_MERGE=yes\nSTATUS_HEADER=yes\nSTATUS_EVERY=1\n")
        rc, out, err = self.run_cmd(["python3", self.prog, "--no-follow", "-c", conf, "--no-history", "--no-isp", "--no-presence",
                                     "--no-banned", "--show-ip", "--no-min", "--service", "erplibre.service"])
        requetes = [l for l in out.splitlines() if "GET" in l]
        self.assertEqual(len(requetes), 1, out + err)
        self.assertIn("H1.1 303", requetes[0])
        self.assertNotIn("odoo18", requetes[0])


class AppLogLive142(unittest.TestCase):
    """1.142 --sitemap : pages 404 listées dans le sitemap.xml (importantes, comptées dans la santé) et pages 404 jamais existantes (non comptées),
    étiquette [dans / pas dans sitemap.xml] avant la colonne OS, en-tête SITEMAP, lecture du sitemap (index compris)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("live142", script_path("app-log-live.py"))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        self.m.SITEMAP = None

    def tearDown(self):
        self.m.SITEMAP = None

    class Fixe:
        """Sitemap sans lecture réseau : chemins donnés (None : pas encore lu)."""
        def __init__(self, paths):
            self.url, self.error = "https://www.example.org/sitemap.xml", None
            self.paths = None if paths is None else frozenset(paths)

        def listed(self, url):
            return None if self.paths is None else self.m_path(url) in self.paths

        @staticmethod
        def m_path(url):
            return AppLogLive142.m.sitemap_path(url)

    def ligne_nginx(self, chemin, code="404"):
        return ('2026-10-31T20:42:41.000000-0400 odoo18 http: 4.4.4.4 - - "GET ' + chemin + ' HTTP/1.1" ' + code +
                ' 7576 "-" "Mozilla/5.0 (X11; Linux x86_64)" host=www.example.org rl=1')

    def test_142_chemin_sans_langue_ni_requete(self):
        """Le chemin comparé : sans schéma, hôte, requête, préfixe de langue (/fr_CA/) ni barre finale."""
        self.assertEqual(self.m.sitemap_path("https://www.example.org/fr_CA/a-propos/?x=1"), "/a-propos")
        self.assertEqual(self.m.sitemap_path("/en_US/about-us"), "/about-us")
        self.assertEqual(self.m.sitemap_path("/fr"), "/")
        self.assertEqual(self.m.sitemap_path("/web/abc?lang=en_CA"), "/web/abc")
        self.assertEqual(self.m.sitemap_path("/blog/x%20y"), "/blog/x y")

    def test_142_adresse_non_http_refusee(self):
        with self.assertRaises(ValueError):
            self.m.Sitemap("ftp://www.example.org/sitemap.xml", start=False)

    def test_142_liste_non_liste_pas_encore_lu(self):
        sm = self.m.Sitemap("https://www.example.org/sitemap.xml", start=False)
        self.assertIsNone(sm.listed("/about-us"))
        sm.paths = frozenset({"/about-us"})
        self.assertTrue(sm.listed("/fr_CA/about-us?x=1"))
        self.assertFalse(sm.listed("/wp-login.php"))

    def test_142_lecture_du_sitemap_et_de_l_index(self):
        """Un sitemap simple et un index de sitemaps (les sitemaps listés sont lus à leur tour)."""
        pages = {
            "https://www.example.org/index.xml": b'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                                 b'<sitemap><loc>https://www.example.org/s1.xml</loc></sitemap></sitemapindex>',
            "https://www.example.org/s1.xml": b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                              b'<url><loc>https://www.example.org/fr_CA/a-propos</loc></url>'
                                              b'<url><loc>https://www.example.org/blog/</loc></url></urlset>',
        }

        class Reponse:
            def __init__(self, data):
                self.data = data

            def read(self, n=-1):
                return self.data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def ouvrir(request, timeout=None):
            return Reponse(pages[request.full_url])
        sm = self.m.Sitemap("https://www.example.org/index.xml", start=False)
        with unittest.mock.patch("urllib.request.urlopen", side_effect=ouvrir):
            self.assertEqual(sm.read(sm.url, 0), {"/a-propos", "/blog"})

    def test_142_etiquette_404_avant_la_colonne_os(self):
        """Ligne nginx 404 : [in sitemap.xml] ou [not in sitemap.xml] avant OS ; ligne 200 : colonne vide ; sans --sitemap : aucune colonne."""
        m = self.m
        sans = m.Formatting(False, 40, 0.0, False).format_value(m.Line(self.ligne_nginx("/about-us")), {}, False)
        self.assertNotIn(m.TR("[in sitemap.xml]"), sans)
        m.SITEMAP = self.Fixe({"/about-us"})
        for chemin, attendu in (("/fr_CA/about-us", m.TR("[in sitemap.xml]")), ("/wp-login.php", m.TR("[not in sitemap.xml]"))):
            texte = ANSI.sub("", m.Formatting(False, 40, 0.0, False).format_value(m.Line(self.ligne_nginx(chemin)), {}, False))
            self.assertIn(attendu, texte)
            self.assertLess(texte.index(attendu), texte.index("MAC") if "MAC" in texte else texte.index("LIN"))
        ok = ANSI.sub("", m.Formatting(False, 40, 0.0, False).format_value(m.Line(self.ligne_nginx("/about-us", "200")), {}, False))
        self.assertNotIn(m.TR("[not in sitemap.xml]"), ok)

    def test_142_etiquette_pas_encore_lu(self):
        m = self.m
        m.SITEMAP = self.Fixe(None)
        texte = ANSI.sub("", m.Formatting(False, 40, 0.0, False).format_value(m.Line(self.ligne_nginx("/about-us")), {}, False))
        self.assertIn(m.TR("[not read yet]"), texte)

    def test_142_entete_SITEMAP_sur_la_colonne_de_l_etiquette(self):
        """L'en-tête SITEMAP est au-dessus de l'étiquette, et RL juste avant elle (--request-length)."""
        m = self.m
        m.SITEMAP = self.Fixe({"/about-us"})
        for rl in (False, True):
            plain = ANSI.sub("", m.Formatting(False, 40, 0.0, False, request_length=rl).format_value(m.Line(self.ligne_nginx("/about-us")), {}, False))
            debut = plain.index("H1.1")
            entete = m.column_header(rl, False, 400, None, debut, plain)
            tag = plain.index(m.TR("[in sitemap.xml]"))
            self.assertEqual(entete.index(m.TR("SITEMAP")), tag, entete)
            if rl:
                self.assertLess(entete.index("RL"), entete.index(m.TR("SITEMAP")))

    def test_142_404_listee_comptee_inconnue_non_comptee(self):
        """Pourcentage de santé (barre d'état) : une page du sitemap qui répond 404 le baisse ; une URL absente du sitemap (attaque) ne le baisse pas."""
        m = self.m
        m.SITEMAP = self.Fixe({"/about-us"})
        barre = m.StatusBar()
        for _ in range(30):                                  # 30 x 0.1 point = 3 points off
            barre.observe(m.Line(self.ligne_nginx("/about-us")), None, 0.0, "4.4.4.4")
        self.assertEqual(barre.gone_404, 30)
        sante_avant = barre.health()
        self.assertEqual(sante_avant, 97)
        for i in range(40):
            barre.observe(m.Line(self.ligne_nginx(f"/wp-login-{i}.php")), None, 0.0, "4.4.4.5")
        self.assertEqual(barre.unknown_404, 40)
        self.assertEqual(barre.health(), sante_avant)


class AppLogLive143(unittest.TestCase):
    """1.143 : fusion des URL encodées différemment (nginx / Odoo) et des websockets ; chemins refusés volontairement (--disable-uri) étiquetés
    [désactivé] et non comptés ; --log-chk-sitemap ; sitemap lu par défaut."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("live143", script_path("app-log-live.py"))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def setUp(self):
        self.m.SITEMAP = None
        self.m.DISABLED_RE = None

    def tearDown(self):
        self.m.SITEMAP = None
        self.m.DISABLED_RE = None

    def nginx(self, requete, code="200"):
        return ('2026-11-01T10:21:02.000000-0500 odoo18 http: 1.2.3.4 - - "' + requete + ' HTTP/1.1" ' + code +
                ' 112k "https://www.example.org/en_CA" "Mozilla/5.0 (Linux)" host=www.example.org rl=300')

    def odoo(self, requete, code="200", sql="5 0.001 0.007"):
        taille = "-" if sql.count(" ") == 2 else ""               # a websocket line has its size, then one duration
        return ('2026-11-01T10:21:02.410000-0500 odoo18 odoo[1]: 2026-11-01 10:21:02,410 1 INFO base werkzeug: 1.2.3.4 - - '
                '[01/Nov/2026 10:21:02] "' + requete + ' HTTP/1.1" ' + code + ' ' + (taille + " " if taille else "") + sql)

    def test_143_fusion_url_encodee_differemment(self):
        """nginx garde %20 et %C3%A9 du client ; Odoo peut montrer les caractères : une seule ligne doit sortir."""
        held = collections.deque()
        self.assertEqual(self.m.merge_step([self.m.Line(self.nginx("GET /web/image/9079/EDIT%20(1).webp%20%C3%89"))], held), [])
        ready = self.m.merge_step([self.m.Line(self.odoo("GET /web/image/9079/EDIT (1).webp É"))], held)
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(held), 0)
        self.assertEqual(ready[0][0].odoo_times, ("5", "0.001", "0.007"))

    def test_143_fusion_websocket(self):
        """Une ligne websocket Odoo (une seule durée, sans requêtes SQL) se fusionne avec sa ligne nginx 101."""
        held = collections.deque()
        self.m.merge_step([self.m.Line(self.nginx("GET /websocket?version=18.0-7", "101"))], held)
        ready = self.m.merge_step([self.m.Line(self.odoo("GET /websocket?version=18.0-7", "101", "494 1730.555"))], held)
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(held), 0)
        shown = self.m.Formatting(False, 40, 0.0, False).format_value(ready[0][0], {}, False)
        self.assertEqual(shown.count("GET"), 1, shown)
        self.assertIn("1730.555", shown)

    def test_143_chemins_refuses_volontairement(self):
        """--disable-uri : "# uri : /shop" couvre /shop et /es/shop/panier, pas /shopping."""
        with tempfile.TemporaryDirectory() as dossier:
            conf = os.path.join(dossier, "uri-desactivees.conf")
            with open(conf, "w", encoding="utf-8") as f:
                f.write("# Généré\n# uri : /shop\nlocation ~ x { return 404; }\n")
            self.m.DISABLED_RE = self.m.disabled_uri_re(conf)
        self.assertTrue(self.m.is_disabled("/es/shop/panier?x=1"))
        self.assertFalse(self.m.is_disabled("/shopping"))
        self.assertIsNone(self.m.disabled_uri_re(os.path.join(tempfile.gettempdir(), "absent-app-log-live.conf")))

    def test_143_refuse_non_compte_dans_la_sante(self):
        """404 sur un chemin refusé volontairement : étiquette [désactivé], aucune pénalité."""
        m = self.m
        with tempfile.TemporaryDirectory() as dossier:
            conf = os.path.join(dossier, "uri.conf")
            with open(conf, "w", encoding="utf-8") as f:
                f.write("# uri : /shop\n")
            m.DISABLED_RE = m.disabled_uri_re(conf)
        m.SITEMAP = AppLogLive142.Fixe({"/about-us"})
        barre = m.StatusBar()
        for _ in range(50):
            barre.observe(m.Line(self.nginx("GET /shop/panier", "404")), None, 0.0, "4.4.4.4")
        self.assertEqual(barre.disabled_404, 50)
        self.assertEqual(barre.health(), 100)
        texte = ANSI.sub("", m.Formatting(False, 40, 0.0, False).format_value(m.Line(self.nginx("GET /shop/panier", "404")), {}, False))
        self.assertIn(m.TR("[disabled]"), texte)

    def test_143_etiquette_non_lu(self):
        m = self.m
        m.SITEMAP = AppLogLive142.Fixe(None)
        texte = ANSI.sub("", m.Formatting(False, 40, 0.0, False).format_value(m.Line(self.nginx("GET /about-us", "404")), {}, False))
        self.assertIn(m.TR("[not read yet]"), texte)

    def test_143_rapport_log_chk_sitemap(self):
        """--log-chk-sitemap : pages 404 listées (avec les variantes ?query et /fr_CA/), refusées volontairement, jamais existantes ; sitemap non lu : code 2."""
        m = self.m
        with tempfile.TemporaryDirectory() as dossier:
            with open(os.path.join(dossier, "access.log"), "w", encoding="utf-8") as f:
                f.write('1.2.3.4 - - [01/Nov/2026:10:00:00 -0400] "GET /en_CA/about-us HTTP/1.1" 404 7576 "-" "x" host=a rl=1\n')
                f.write('1.2.3.4 - - [01/Nov/2026:10:00:01 -0400] "GET /about-us?x=1 HTTP/1.1" 404 7576 "-" "x" host=a rl=1\n')
                f.write('5.6.7.8 - - [01/Nov/2026:10:00:02 -0400] "GET /wp-login.php HTTP/1.1" 404 7576 "-" "x" host=a rl=1\n')
                f.write('5.6.7.8 - - [01/Nov/2026:10:00:03 -0400] "GET /about-us HTTP/1.1" 200 7576 "-" "x" host=a rl=1\n')
            m.DISABLED_RE = None
            with unittest.mock.patch.object(m.Sitemap, "read", return_value={"/about-us"}):
                lignes, code = m.sitemap_report("https://www.example.org/sitemap.xml", dossier)
            self.assertEqual(code, 0)
            texte = "\n".join(ANSI.sub("", x) for x in lignes)
            self.assertIn(f"{2:>6}  /about-us", texte)                # /en_CA/about-us et /about-us?x=1 : une seule page, deux réponses
            self.assertIn("/wp-login.php", texte)                     # jamais existante : listée à part
            with unittest.mock.patch.object(m.Sitemap, "read", side_effect=OSError("hors ligne")):
                lignes, code = m.sitemap_report("https://www.example.org/sitemap.xml", dossier)
            self.assertEqual(code, 2)

    def test_143_option_sitemap_par_defaut_et_desactivation(self):
        """Le sitemap du site est lu par défaut ; --no-sitemap le désactive (configuration SITEMAP et NO_SITEMAP)."""
        m = self.m
        self.assertEqual(m.DEFAULT_SITEMAP_URL, "https://www.rencontres-linux.quebec/sitemap.xml")
        self.assertEqual(m.SCHEMA_CONFIG["NO_SITEMAP"][0], "no_sitemap")
        self.assertEqual(m.SCHEMA_CONFIG["SITEMAP"][0], "sitemap")
        self.assertTrue(m.SITEMAP_OFF_BY_ENV or m.DEFAULT_SITEMAP_URL)
