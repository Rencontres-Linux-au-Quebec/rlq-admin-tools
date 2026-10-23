# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Bibliothèque commune (programmes Python) : choix du profil d'application apps/<nom>.conf — même logique que
apps/_profile.sh. charger_profil_app(dossier, force=None) -> dict des clés du profil (+ APP_DETECTION), ou lève
ProfilError (message en français) si aucune application, plusieurs, ou un nom inconnu."""
import glob
import os
import re
import subprocess
import sys


class ProfilError(Exception):
    pass


def lire_profil(chemin):
    """Clés du profil ; ProfilError si APP_NAME manque (fichier vide, tronqué ou d'un autre format)."""
    profil = {}
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            m = re.match(r'^\s*([A-Z_][A-Z0-9_]*)=(?:"([^"]*)"|(\S*))\s*(?:#.*)?$', ligne)
            if m:
                profil[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    if not profil.get("APP_NAME"):
        raise ProfilError(f"profil invalide : {chemin} (clé APP_NAME absente — fichier vide ou tronqué ?)")
    return profil


def _unite_existe(unite):
    try:
        r = subprocess.run(["systemctl", "list-unit-files", unite, "--no-legend"], capture_output=True, text=True, timeout=20)
        return any(l.split()[:1] == [unite] for l in r.stdout.splitlines())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _odoo_conf():
    """Module apps/_odoo_conf.py (à côté de celui-ci), ou None."""
    dossier = os.path.dirname(os.path.abspath(__file__))
    if dossier not in sys.path:
        sys.path.insert(0, dossier)
    try:
        import _odoo_conf
        return _odoo_conf
    except ImportError:
        return None


def detecte(profil):
    racine = os.environ.get("APP_DETECT_ROOT", "")      # vide en production ; dossier vide pendant les tests
    if profil.get("DETECT_ODOO_CONF") == "yes":          # un fichier de configuration d'Odoo suffit (apps/_odoo_conf.py)
        lib = _odoo_conf()
        if lib is not None and lib.trouver():
            return True
    if any(os.path.exists(racine + f) for f in profil.get("DETECT_FILES", "").split()):
        return True
    return any(_unite_existe(u) for u in profil.get("DETECT_UNITS", "").split())


def _avec_configuration_odoo(profil):
    """Profil à configuration d'Odoo : ajoute ODOO_CONF, ODOO_HTTP_PORT, ODOO_GEVENT_PORT, ODOO_LOGFILE si un fichier est trouvé."""
    if profil.get("DETECT_ODOO_CONF") == "yes":
        lib = _odoo_conf()
        chemin = lib.trouver() if lib is not None else None
        if chemin:
            r = lib.lire(chemin)
            profil.update({"ODOO_CONF": chemin, "ODOO_HTTP_PORT": r["http_port"], "ODOO_GEVENT_PORT": r["gevent_port"], "ODOO_LOGFILE": r["logfile"]})
            if r["unites"]:                                    # service named after db_user / the file: tried first
                profil["DETECT_UNITS"] = " ".join(r["unites"] + [u for u in profil.get("DETECT_UNITS", "").split() if u not in r["unites"]])
            if profil.get("APP_DETECTION") == "détectée automatiquement":
                profil["APP_DETECTION"] = f"détectée automatiquement ; configuration d'Odoo : {chemin}"
    return profil


def charger_profil_app(dossier, force=None):
    force = force or os.environ.get("APP_PROFILE") or None          # APP_PROFILE : equivalent de --app
    disponibles = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(dossier, "*.conf")))
    if force:
        chemin = os.path.join(dossier, f"{force}.conf")
        if not os.path.isfile(chemin):
            raise ProfilError(f"profil d'application inconnu : {force} (disponibles : {' '.join(disponibles) or 'aucun'})")
        profil = lire_profil(chemin)
        profil["APP_DETECTION"] = f"forcée (--app={force})"
        return _avec_configuration_odoo(profil)
    trouves = [n for n in disponibles if detecte(lire_profil(os.path.join(dossier, f"{n}.conf")))]   # profil invalide : erreur
    if not trouves:
        raise ProfilError(f"aucune application reconnue sur ce serveur (profils : {dossier}/*.conf) — précisez --app=NOM")
    if len(trouves) > 1:
        raise ProfilError(f"plusieurs applications détectées ({' '.join(trouves)}) — précisez --app=NOM")
    profil = lire_profil(os.path.join(dossier, f"{trouves[0]}.conf"))
    profil["APP_DETECTION"] = "détectée automatiquement"
    return _avec_configuration_odoo(profil)


def cms(force=None):
    """« wordpress » ou « odoo » : le CMS du site, qui décide si /wp-admin, /wp-login.php, /wordpress, xmlrpc.php, *.php sont des URL SUSPECTS
    (sur un site Odoo seulement : Odoo n'en a aucun) ou des pages normales (site WordPress). Ordre : force (--cms oui/non ≠ auto), variable
    NGINX_TOOLS_CMS, fichier /etc/default/nginx-tools-cms.conf (CMS=odoo|wordpress|auto), puis détection : un wp-config.php sous /var/www, /srv,
    /usr/share/nginx ou /opt (3 niveaux au plus). Sans rien de tout cela : odoo."""
    choix = (force or "").strip().lower()
    if choix not in ("odoo", "wordpress"):
        choix = os.environ.get("NGINX_TOOLS_CMS", "").strip().lower()
    if choix not in ("odoo", "wordpress"):
        fichier = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), "nginx-tools-cms.conf")
        try:
            with open(fichier, encoding="utf-8") as f:
                for ligne in f:
                    m = re.match(r"^\s*CMS\s*=\s*[\"']?(\w+)[\"']?\s*(?:#.*)?$", ligne)
                    if m:
                        choix = m.group(1).lower()
        except OSError:
            pass
    if choix in ("odoo", "wordpress"):
        return choix
    racine = os.environ.get("APP_DETECT_ROOT", "")
    for base in ("/var/www", "/srv", "/usr/share/nginx", "/opt"):
        for profondeur in ("", "/*", "/*/*", "/*/*/*"):
            if glob.glob(racine + base + profondeur + "/wp-config.php"):
                return "wordpress"
    return "odoo"
