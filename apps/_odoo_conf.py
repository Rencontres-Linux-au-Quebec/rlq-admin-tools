# ========================================================================================================================
# Copyright (C) 2026  Services-Linux Conseils Inc <Martial@Bigras.ca> <Martial.Bigras@Services-Conseils-Linux.com>
# Licence : GNU Affero General Public License, version 3 ou ultérieure — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Bibliothèque commune (programmes Python) : trouver la configuration d'Odoo et en lire les réglages — même logique que
apps/_odoo_conf.sh. Candidats (premier trouvé gagne) : variable d'environnement ODOO_CONF_PATHS, ligne ODOO_CONF_PATHS="..." de
~/.nginx-hardening.cfg puis de /etc/default/nginx-hardening.conf, puis la liste par défaut. Les motifs avec * sont développés ;
APP_DETECT_ROOT (tests) préfixe tous les chemins."""
import glob
import os
import re

__version__ = "1.1.20261016.173838"

CHEMINS_DEFAUT = ("/etc/odoo/odoo-linux_meetup.conf /opt/odoo/erplibre/config.conf /home/mathben/git/erplibre/config.conf /etc/odoo/odoo.conf "
                  "/etc/odoo/*.conf /home/*/git/erplibre/config.conf /opt/odoo/*/config.conf")
_RECONNAISSANCE = re.compile(r"^\[options\]|^\s*(db_host|addons_path|http_port|xmlrpc_port|admin_passwd)\s*=", re.M)


def _reglage(fichier, cle):
    try:
        with open(fichier, encoding="utf-8", errors="replace") as f:
            valeur = None
            for ligne in f:
                m = re.match(rf"^\s*{cle}=(.*)$", ligne)
                if m:
                    valeur = m.group(1)
    except OSError:
        return None
    if valeur is None:
        return None
    return valeur.split("#", 1)[0].strip().strip("\"'").strip() or None


def chemins_candidats():
    liste = os.environ.get("ODOO_CONF_PATHS")
    etc = os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default")
    for fichier in (os.path.join(os.environ.get("HOME", "/nonexistent"), ".nginx-hardening.cfg"), os.path.join(etc, "nginx-hardening.conf")):
        liste = liste or _reglage(fichier, "ODOO_CONF_PATHS")
    return (liste or CHEMINS_DEFAUT).split()


def trouver():
    """Chemin du premier fichier de configuration d'Odoo lisible, ou None."""
    racine = os.environ.get("APP_DETECT_ROOT", "")
    for motif in chemins_candidats():
        for chemin in sorted(glob.glob(racine + motif)):
            try:
                with open(chemin, encoding="utf-8", errors="replace") as f:
                    if os.path.isfile(chemin) and _RECONNAISSANCE.search(f.read()):
                        return chemin
            except OSError:
                continue
    return None


def valeur(chemin, cle):
    """Dernière valeur de `cle` (sans espaces ni guillemets), ou ''."""
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            trouve = ""
            for ligne in f:
                m = re.match(rf"^\s*{re.escape(cle)}\s*=(.*)$", ligne)
                if m:
                    trouve = m.group(1).strip().strip("\"'").strip()
    except OSError:
        return ""
    return trouve


def unites(chemin):
    """Unités systemd probables : db_user (ex. odoo-linux_meetup) puis nom du fichier de configuration, avec le suffixe .service."""
    noms = []
    for nom in (valeur(chemin, "db_user"), os.path.basename(chemin)[:-5] if chemin.endswith(".conf") else ""):
        if nom and nom.lower() != "false" and nom + ".service" not in noms:
            noms.append(nom + ".service")
    return noms


def lire(chemin):
    """{'chemin', 'http_port', 'gevent_port', 'logfile', 'interface'} (ports par défaut d'Odoo : 8069 / 8072 ; logfile '' = journal systemd)."""
    logfile = valeur(chemin, "logfile")
    return {"chemin": chemin,
            "http_port": valeur(chemin, "http_port") or valeur(chemin, "xmlrpc_port") or "8069",
            "gevent_port": valeur(chemin, "gevent_port") or valeur(chemin, "longpolling_port") or "8072",
            "logfile": "" if logfile.lower() in ("false", "none") else logfile,
            "interface": valeur(chemin, "http_interface") or valeur(chemin, "xmlrpc_interface"),
            "unites": unites(chemin)}
