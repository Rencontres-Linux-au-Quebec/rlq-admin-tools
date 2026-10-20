# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
# Licence : GNU Affero General Public License, version 3 ou ultérieure — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Outils communs de la suite de tests : environnement temporaire, faux outils système, préparation des scripts
(chemins système redirigés vers le répertoire de test), lancement normal ou dans un vrai pseudo-terminal.

Variables d'environnement reconnues :
  TEST_SCRIPTS_DIR : répertoire des programmes testés (défaut : parent du dossier de la suite, nginx-tools-tests/).
  TEST_AWK         : chemin de l'awk à utiliser (ex. /usr/bin/gawk) — run-all.sh lance la suite une fois par awk
                     disponible, pour attraper les différences gawk/mawk (bug « awk -v » de nginx-log-audit.sh 1.24).
"""
import os
import pty
import re
import select
import signal
import shutil
import subprocess
import tempfile
import time
import unittest

# run-all 1.188 : heures attendues en heure de l'Est (journaux « -0400 » des serveurs) — fixées pour la suite ET les programmes lancés, même sur une machine
# en UTC (avant : dépendait d'un test précédent qui laissait TZ posé). TEST_TZ : un autre fuseau.
os.environ["TZ"] = os.environ.get("TEST_TZ") or "America/Toronto"
time.tzset()
SCRIPTS_DIR = os.environ.get("TEST_SCRIPTS_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Configuration nginx testee : NGINX_ODOO_DIR (run-all 1.188 : la configuration est PRIVEE, jamais dans le depot Git public — copie locale, ex. un
# clone de rlq-nginx-config), sinon nginx-tools-tests/nginx-odoo/ (livree avec l'archive de la suite), sinon nginx-odoo/ a cote des programmes.
# Absente : les tests qui en ont besoin sont desactives (« configuration absente »), jamais en echec.
CONFIG_DIR = next((d for d in ([os.path.abspath(os.environ["NGINX_ODOO_DIR"])] if os.environ.get("NGINX_ODOO_DIR") else [])
                   + [os.path.join(os.path.dirname(os.path.abspath(__file__)), "nginx-odoo"),
                      os.path.join(SCRIPTS_DIR, "nginx-odoo")] if os.path.isdir(d)),
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "nginx-odoo"))


def script_path(name):
    return os.path.join(SCRIPTS_DIR, name)


def require_script(testcase, name):
    if not os.path.isfile(script_path(name)):
        testcase.skipTest(f"{name} absent de {SCRIPTS_DIR}")


# Commandes système jamais joignables depuis un test (sauf faux outil du test lui-même) : elles modifient ou interrogent
# l'état réel de la machine (pare-feu, services, réseau, journaux, paquets, BigBlueButton).
COMMANDES_SYSTEME = {"ufw", "iptables", "ip6tables", "iptables-save", "ip6tables-save", "iptables-restore",
                     "ip6tables-restore", "iptables-legacy", "iptables-nft", "ipset", "nft", "fail2ban-client",
                     "fail2ban-server", "netfilter-persistent", "systemctl", "journalctl", "nginx", "logrotate", "apt",
                     "apt-get", "certbot", "service", "reboot", "shutdown", "curl", "wget", "host", "dig", "nslookup",
                     "bbb-conf", "haproxy", "docker", "dpkg", "dpkg-query", "whois", "psql", "runuser", "geoiplookup", "apt-cache"}   # dpkg, docker : relevé de BBB (apps/_bbb.py)
_CHEMIN_TESTS = None


def _isoler_proc():
    """/proc de la machine d'essai : web-monitor.py y lit l'heure du dernier rechargement de nginx (nginx_charge_depuis). Sur un
    serveur où nginx tourne, des tests qui chargent web-monitor.py DANS le processus de test (sans passer par self.env) en
    dépendaient — échec « nginx n'a pas été rechargé depuis » (run-all 1.58 sur odoo18). Isolé pour TOUT le processus, à
    l'import : un dossier vide, quelle que soit la valeur déjà présente dans l'environnement."""
    import atexit
    dossier = tempfile.mkdtemp(prefix="test-rlq-proc-")
    atexit.register(shutil.rmtree, dossier, True)
    os.environ["WEB_MONITOR_PROC_DIR"] = dossier
    return dossier


PROC_ISOLE = _isoler_proc()


def _isoler_listes():
    """Liste blanche et lieux (/etc/default/nginx-tools-*.conf) : jamais les VRAIS fichiers du serveur d'essai. Chemins d'un dossier temporaire
    vide pour TOUT le processus (les tests qui chargent un programme dans le processus lisent os.environ) ; un test qui veut des entrées écrit
    dans ces chemins."""
    import atexit
    dossier = tempfile.mkdtemp(prefix="test-rlq-listes-")
    atexit.register(shutil.rmtree, dossier, True)
    os.environ["NGINX_TOOLS_WHITE_LIST"] = os.path.join(dossier, "nginx-tools-white-list.conf")
    os.environ["NGINX_TOOLS_IP_LOCATION"] = os.path.join(dossier, "nginx-tools-ip-location.conf")
    return dossier


LISTES_ISOLEES = _isoler_listes()


def _isoler_etat_web_monitor():
    """État de web-monitor.py (/var/lib/web-monitor : recommended-bans.json, last-alert.json…) : jamais le VRAI du serveur d'essai. Sur un serveur où web-monitor.py
    a recommandé des bannissements, test_a_bannir_jamais_le_serveur_lui_meme trouvait des adresses en trop (run-all 1.107 sur odoo18). Dossier vide pour TOUT le
    processus ; un test qui veut un état donne son propre WEB_MONITOR_STATE_DIR."""
    import atexit
    dossier = tempfile.mkdtemp(prefix="test-rlq-etat-")
    atexit.register(shutil.rmtree, dossier, True)
    os.environ["WEB_MONITOR_STATE_DIR"] = dossier
    return dossier


ETAT_WEB_MONITOR_ISOLE = _isoler_etat_web_monitor()
# Cache permanent des adresses (/var/lib/nginx-tools/ip-cache.sqlite) : DÉSACTIVÉ par défaut dans les tests (jamais le vrai cache du serveur, et
# aucune réponse mémorisée ne fausse un test qui lance le même programme plusieurs fois) ; un test du cache donne son propre chemin.
os.environ["NGINX_TOOLS_IP_CACHE"] = "off"
# Journal quotidien d'app-log-live.py (/var/log/app-log-live ou ~/.local/state) : DÉSACTIVÉ par défaut dans les tests ; un test du journal donne son propre dossier.
os.environ["APP_LOG_LIVE_LOG_DIR"] = "off"
# Registre des comptes Odoo bannis / surveillés (apps/_odoo_users.py, /var/lib/nginx-tools/odoo-users.tsv) : jamais le vrai ; recherches Internet
# (apps/_email_check.py : StopForumSpam, Gravatar, DuckDuckGo, DNS MX) : jamais pendant les tests.
os.environ["NGINX_TOOLS_ODOO_USERS"] = "off"
os.environ["NGINX_TOOLS_INTERNET"] = "off"
os.environ.pop("NGINX_TOOLS_CONFIG_VUE", None)                  # run-all.sh l'exporte après avoir affiché sa configuration : les tests des programmes doivent voir les lignes « Configuration… / Options… »
for _v in ("NGINX_TOOLS_I18N", "NGINX_TOOLS_I18N_LANGUE", "NGINX_TOOLS_LANG"):     # run-all.sh lancé en anglais passe par le traducteur et exporte ces variables : les tests ne doivent pas en hériter
    os.environ.pop(_v, None)
os.environ["NGINX_TOOLS_CONFIG_CREER"] = "0"                                # premier démarrage : les programmes créeraient leur fichier de configuration par défaut ; seul test_config_defaut.py le demande
os.environ["NGINX_TOOLS_ETC_DEFAULT"] = "/inexistant-etc-default"            # apps/_config.py : jamais les vrais /etc/default/PROGRAMME.conf de la machine
VARIABLES_LANGUE = ("APP_HEALTH_CHECK_LANG", "APP_LOG_CHECK_LANG", "APP_LOG_LIVE_LANG", "NGINX_HARDENING_LANG", "NGINX_LOG_AUDIT_LANG", "ODOO_BACKUP_LANG",
                    "ODOO_MAIL_RETRY_LANG", "RUN_ALL_LANG", "SYNC_CROWDSEC_BLOCKLIST_LANG", "WEB_MONITOR_LANG", "ZIP_VERSIONS_LANG", "HOST_PERF_AUDIT_LANG")
for _v in VARIABLES_LANGUE:
    os.environ.setdefault(_v, "fr")            # les tests vérifient les messages français ; l'anglais : --lang=en


# Liste blanche d'essai (adresses FICTIVES) : les tests n'utilisent jamais la vraie liste d'une installation.
LISTE_EXEMPLE = """# liste blanche d'essai
203.0.113.5      # Étienne (maison)
100.64.0.21      # Étienne (Tailscale : poste-2)
198.51.100.9     # Mathis
"""
IPS_EXEMPLE = ("203.0.113.5", "100.64.0.21", "198.51.100.9")


def ecrire_liste(chemin_variable, contenu):
    """Écrit une liste (liste blanche : NGINX_TOOLS_WHITE_LIST ; lieux : NGINX_TOOLS_IP_LOCATION) dans le chemin isolé du test en cours."""
    chemin = os.environ[chemin_variable]
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)
    return chemin


def chemin_sans_commandes_systeme():
    """Dossier de liens vers les exécutables du PATH, SAUF COMMANDES_SYSTEME (construit une fois par session)."""
    global _CHEMIN_TESTS
    if _CHEMIN_TESTS is None:
        import atexit
        dossier = tempfile.mkdtemp(prefix="test-rlq-path-")
        atexit.register(shutil.rmtree, dossier, True)
        vus = set()
        for rep in os.environ.get("PATH", "/usr/bin:/bin").split(":"):
            if not os.path.isdir(rep):
                continue
            for nom in os.listdir(rep):
                cible = os.path.join(rep, nom)
                if nom in vus or nom in COMMANDES_SYSTEME or not (os.path.isfile(cible) and os.access(cible, os.X_OK)):
                    continue
                vus.add(nom)
                os.symlink(cible, os.path.join(dossier, nom))
        _CHEMIN_TESTS = dossier
    return _CHEMIN_TESTS


def sans_date(texte):
    """Retire les « (modifié le AAAA-MM-JJ HH:MM) » de la ligne « Configuration lue » (date de modification des fichiers : change à chaque essai)."""
    return re.sub(r" \((?:modifié le|modified on) [0-9?: -]+\)", "", texte)


class EnvTest(unittest.TestCase):
    """Classe de base : chaque test reçoit un répertoire temporaire self.d, un dossier self.bin placé en tête du PATH
    (faux outils), et l'awk choisi par TEST_AWK."""

    def liste_blanche(self, contenu):
        """Écrit la liste blanche DE CE TEST (chemin NGINX_TOOLS_WHITE_LIST de self.env) ; retourne le chemin."""
        return self._liste("NGINX_TOOLS_WHITE_LIST", contenu)

    def lieux(self, contenu):
        """Écrit la liste des lieux DE CE TEST (chemin NGINX_TOOLS_IP_LOCATION de self.env) ; retourne le chemin."""
        return self._liste("NGINX_TOOLS_IP_LOCATION", contenu)

    def _liste(self, variable, contenu):
        chemin = self.env[variable]
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)
        return chemin

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="test-rlq-")
        # Enregistre AUSSITOT : les nettoyages s'executent meme si la suite de setUp echoue ou desactive le test
        # (tearDown, lui, n'est pas appele dans ce cas — repertoires laisses dans /tmp).
        self.addCleanup(shutil.rmtree, self.d, True)
        self.bin = os.path.join(self.d, "bin")
        os.makedirs(self.bin)
        awk = os.environ.get("TEST_AWK")
        if awk:
            os.symlink(awk, os.path.join(self.bin, "awk"))
        # APP_PROFILE=odoo par défaut : les tests ne dépendent pas de ce qui est installé sur la machine (un test de
        # détection automatique retire cette variable).
        # PATH SANS les commandes système sensibles (ufw, iptables, systemctl, nginx…) : un outil non simulé par le test
        # est ABSENT, jamais la vraie commande de la machine (un test a modifié le vrai ufw d'un serveur BigBlueButton).
        # NGINX_TOOLS_TESTS empêche les programmes de rajouter /usr/sbin ; APP_DETECT_ROOT isole la détection par fichiers.
        os.makedirs(os.path.join(self.d, "racine-vide"))
        self.env = dict(os.environ, PATH=f"{self.bin}:{chemin_sans_commandes_systeme()}", LC_ALL="C.UTF-8", APP_PROFILE="odoo", **{v: os.environ[v] for v in VARIABLES_LANGUE},
                        NGINX_TOOLS_TESTS="1", APP_DETECT_ROOT=os.path.join(self.d, "racine-vide"),
                        NGINX_TOOLS_LOCK_DIR=os.path.join(self.d, "racine-vide"), NGINX_TOOLS_LOCK_WAIT="2",
                        HOME=os.path.join(self.d, "home-vide"), NGINX_TOOLS_ETC_DEFAULT=os.path.join(self.d, "etc-default-vide"),
                        NGINX_TOOLS_MAIL_CONF=os.path.join(self.d, "etc-default-vide", "nginx-tools-mail.conf"),          # courriel : jamais le vrai /etc/default, /etc/msmtprc de la machine de test
                        NGINX_TOOLS_MAIL_PASSWORD_FILE=os.path.join(self.d, "etc-default-vide", "nginx-tools-mail.pass"),
                        NGINX_TOOLS_MSMTPRC=os.path.join(self.d, "etc-default-vide", "msmtprc"),          # jamais le vrai ~/.programme.cfg de la machine de test
                        # État de BigBlueButton (apps/_bbb.py) : instantané et fichiers lus dans le dossier du test
                        NGINX_TOOLS_BBB_STATE=os.path.join(self.d, "state", "bbb-state.json"),
                        NGINX_TOOLS_BBB_ETC=os.path.join(self.d, "bbb-etc"),
                        NGINX_TOOLS_NGINX_ETC=os.path.join(self.d, "nginx-etc"),
                        NGINX_TOOLS_HAPROXY_CFG=os.path.join(self.d, "haproxy", "haproxy.cfg"),
                        NGINX_TOOLS_FAIL2BAN_ETC=os.path.join(self.d, "fail2ban-etc"),
                        NGINX_TOOLS_BBB_PROPERTIES=os.path.join(self.d, "bbb-web", "bigbluebutton.properties"),
                        NGINX_TOOLS_BBB_PORT="1",                        # aucune connexion au vrai 443 de la machine
                        # /proc : web-monitor.py y lit l'heure du dernier rechargement de nginx — sur un serveur où nginx tourne,
                        # un test dépendait de la vraie heure (échec « nginx n'a pas été rechargé depuis », 2.37). Dossier vide.
                        WEB_MONITOR_PROC_DIR=PROC_ISOLE,
                        NGINX_TOOLS_IP_CACHE="off",
                        APP_LOG_LIVE_LOG_DIR="off",
                        NGINX_TOOLS_ODOO_USERS=os.path.join(self.d, "state", "odoo-users.tsv"),     # registre des comptes bannis / surveillés : celui du test
                        NGINX_TOOLS_INTERNET="off",
                        WEB_MONITOR_STATE_DIR=os.path.join(self.d, "web-monitor-state"),       # recommended-bans.json : jamais celui du vrai serveur
                        NGINX_TOOLS_WHITE_LIST=os.path.join(self.d, "etc-default", "nginx-tools-white-list.conf"),
                        NGINX_TOOLS_IP_LOCATION=os.path.join(self.d, "etc-default", "nginx-tools-ip-location.conf"))

    # --- fichiers et faux outils --------------------------------------------------------------------------------
    def path(self, *parts):
        p = os.path.join(self.d, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def write(self, rel, content, mode=None):
        p = self.path(rel)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        if mode:
            os.chmod(p, mode)
        return p

    def mock(self, name, body, shebang="#!/bin/bash"):
        """Crée un faux outil exécutable dans self.bin (prioritaire dans le PATH)."""
        p = os.path.join(self.bin, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"{shebang}\n{body}\n")
        os.chmod(p, 0o755)
        return p

    def mock_exit(self, name, code=0):
        return self.mock(name, f"exit {code}")

    def prepare(self, name, subs=None):
        """Copie un programme dans le répertoire de test en remplaçant des chemins système (ex. /var/log/nginx) par
        des chemins du test. Le changelog est copié aussi (--changelog le cherche à côté du programme)."""
        require_script(self, name)
        with open(script_path(name), encoding="utf-8") as f:
            text = f.read()
        for old, new in (subs or {}).items():
            text = text.replace(old, new)
        dst = self.path("prog", name)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(dst, 0o755)
        apps = os.path.join(SCRIPTS_DIR, "apps")          # profils d'application, livrés à côté des programmes
        cible = os.path.join(os.path.dirname(dst), "apps")
        if os.path.isdir(apps) and not os.path.isfile(os.path.join(cible, "_profile.sh")):
            shutil.copytree(apps, cible, dirs_exist_ok=True)
        langues = os.path.join(SCRIPTS_DIR, "lang")           # catalogues de traduction (lang/PROGRAMME.en.tsv)
        if os.path.isdir(langues):
            shutil.copytree(langues, os.path.join(os.path.dirname(dst), "lang"), dirs_exist_ok=True)
        base = os.path.splitext(name)[0]
        cl = script_path(f"doc/{base}.changelog.txt")
        if os.path.isfile(cl):
            shutil.copy(cl, self.path("prog", "doc", f"{base}.changelog.txt"))
        return dst

    # --- lancement -----------------------------------------------------------------------------------------------
    def run_cmd(self, cmd, env_extra=None, input_text=None, timeout=120):
        env = dict(self.env, **(env_extra or {}))
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, input=input_text, timeout=timeout)
        return r.returncode, ANSI_RE.sub("", r.stdout), ANSI_RE.sub("", r.stderr)

    def run_pty(self, cmd, answers, env_extra=None, timeout=60, keep_ansi=False):
        """Lance cmd dans un VRAI pseudo-terminal. answers : liste de (texte attendu, octets à envoyer, délai avant
        envoi) — ex. (b"[o/N]", b"\\x03", 0.3) envoie un vrai Ctrl-C (caractère INTR du terminal) à la question.
        Retourne (texte complet sans couleurs, nombre de réponses envoyées)."""
        env = dict(self.env, **(env_extra or {}))
        pid, fd = pty.fork()
        if pid == 0:
            signal.signal(signal.SIGINT, signal.SIG_DFL)          # lancé en arrière-plan (&, nohup), SIGINT est IGNORÉ et hérité : Ctrl-C ne ferait rien
            os.execvpe(cmd[0], cmd, env)
        out, sent, t0 = b"", 0, time.time()
        pending = list(answers)
        # Questions posées par app-log-live.py à la fin d'un Ctrl-C (confirmation de sortie ; « plus de détails ? ») : répondues AUTOMATIQUEMENT (o ; Entrée = non) tant que le test
        # n'attend pas lui-même cette question (réponse prévue dans `answers`), pour que les tests existants de Ctrl-C voient toujours le résumé.
        auto = [(b"[N] non, continuer", b"o\r"), (b"Plus de d\xc3\xa9tails sur les erreurs", b"\r"),
                (b"Interrompre le programme ? [o/N]", b"o\r"), (b"Stop the program? [y/N]", b"y\r")]      # confirmation commune de Ctrl+C (apps/_i18n.py / _i18n.sh)
        vus = {motif: 0 for motif, _ in auto}
        while time.time() - t0 < timeout:
            r, _, _ = select.select([fd], [], [], 0.3)
            if r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
                if pending and pending[0][0] in out[-4096:]:
                    _, keys, delay = pending.pop(0)
                    time.sleep(delay)
                    for k in keys:
                        os.write(fd, bytes([k]))
                        time.sleep(delay if len(keys) > 1 else 0)
                    sent += 1
                    for motif, _ in auto:
                        vus[motif] = out.count(motif)
                else:
                    for motif, reponse in auto:
                        if out.count(motif) > vus[motif]:
                            vus[motif] = out.count(motif)
                            time.sleep(0.2)
                            for k in reponse:
                                os.write(fd, bytes([k]))
            else:
                try:
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        break
                except ChildProcessError:
                    break
        # Tout le groupe de processus : pty.fork fait de l'enfant un chef de session, son groupe porte son PID. Tuer
        # seulement le programme laissait ses enfants actifs, capables de recreer des fichiers dans le repertoire de
        # test pendant sa suppression (repertoire test-rlq-* laisse dans /tmp).
        for sig_target in (lambda: os.killpg(pid, 9), lambda: os.kill(pid, 9)):
            try:
                sig_target()
            except OSError:
                pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        text = out.decode("utf-8", "replace").replace("\r", "")
        return (text if keep_ansi else ANSI_RE.sub("", text)), sent


def awk_name():
    """Nom de l'awk utilisé pour ce passage (affiché par run-all.sh)."""
    a = os.environ.get("TEST_AWK") or shutil.which("awk") or "awk"
    return os.path.basename(os.path.realpath(a))


def sans_origine(texte):
    """1.17 d'apps/_i18n.py : « --lang fr (LANG=fr_CA.UTF-8) » ou « --lang fr (défaut (aucune variable …)) » — l'origine de la langue retirée pour comparer
    le reste de la ligne (« (ligne de commande prioritaire) » reste)."""
    return re.sub(r"--lang (\w+) \((?:[^()]*=[^()]*(?:\([^()]*\)[^()]*)?|(?:défaut|default) \([^()]*\))\)", r"--lang \1", texte)