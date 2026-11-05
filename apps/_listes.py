#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _listes.py - the TWO address lists specific to an installation, read outside the archives (never shipped):
#   * WHITE LIST  /etc/default/nginx-tools-white-list.conf: trusted addresses (team) - never banned, access to the DEV and
#     LAB sites. Read ONLY in /etc/default (it grants access: no hidden user file).
#   * LIEUX          /etc/default/nginx-tools-ip-location.conf puis ~/.nginx-tools-ip-location.conf : un NOM pour une adresse ou une plage
#     (university, office...). Description: grants NO access.
# Common syntax, one entry per line:   ADDRESS-OR-RANGE   # label   [option] [option]
#   [shared]  several people behind the same address: the place is shown, never a person's name
#   [protected]  never banned nor recommended for banning (grants no access by itself: the white list does that)
# Transition : tant que /etc/default/nginx-tools-white-list.conf n'existe pas, l'ancienne liste apps/team-ips.list est lue (avec un avertissement) ;
# nginx-hardening.sh --update la migre. Variables d'environnement (tests) : NGINX_TOOLS_WHITE_LIST, NGINX_TOOLS_IP_LOCATION (fichier unique).
#
#
# Usage (normalement appele par les programmes de la suite) :
#   python3 apps/_listes.py --resume          fichiers lus et nombre d'entrees
#   python3 apps/_listes.py --ip ADRESSE      libelles connus pour cette adresse
#   python3 apps/_listes.py --version

import datetime
import functools
import ipaddress
import os
import re
import sys

__version__ = "1.8.20261104.204925"

BLANCHE_DEFAUT = "/etc/default/nginx-tools-white-list.conf"
LIEUX_DEFAUT = "/etc/default/nginx-tools-ip-location.conf"
LIEUX_UTILISATEUR = "~/.nginx-tools-ip-location.conf"
NOM_DNS_RE = re.compile(r"^(?=.*[A-Za-z])[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")
LIGNE_RE = re.compile(r"^\s*([0-9A-Fa-f:.]+(?:/\d{1,3})?)\s*(?:#(.*))?$")
OPTION_RE = re.compile(r"\[([^\]]*)\]")
OPTIONS = {"partagee": "partagee", "partagée": "partagee", "protegee": "protegee", "protégée": "protegee"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")     # [temporaire AAAA-MM-JJ HH:MM:SS] (heure locale)


class Entree(object):
    """Une ligne d'une liste : réseau, libellé, options, et d'où elle vient (fichier:ligne)."""
    __slots__ = ("reseau", "libelle", "partagee", "protegee", "source", "temporaire", "expiration")

    def __init__(self, reseau, libelle, partagee, protegee, source, temporaire=False, expiration=""):
        self.reseau, self.libelle, self.partagee, self.protegee, self.source = reseau, libelle, partagee, protegee, source
        self.temporaire, self.expiration = temporaire, expiration      # expiration : "AAAA-MM-JJ HH:MM:SS" ; "" si absente ou invalide


def est_nom_dns(ligne):
    """True si la première colonne de la ligne est un nom DNS (une adresse IP n'en est jamais un)."""
    premier = ligne.split("#")[0].split()
    return bool(premier) and NOM_DNS_RE.match(premier[0]) is not None


def noms_dns(chemin):
    """Noms DNS d'un fichier de liste (adresses dynamiques) ; fichier absent : []."""
    try:
        with open(chemin, encoding="utf-8") as f:
            lignes = f.read().splitlines()
    except OSError:
        return []
    return [ligne.split("#")[0].split()[0] for ligne in lignes if ligne.strip() and not ligne.lstrip().startswith("#") and est_nom_dns(ligne)]


def lire_fichier(chemin):
    """(entrées, problèmes) d'un fichier ; problèmes : « fichier:ligne : texte ». Fichier absent ou illisible : ([], [])."""
    entrees, problemes = [], []
    try:
        with open(chemin, encoding="utf-8") as f:
            lignes = f.read().splitlines()
    except OSError:
        return entrees, problemes
    for n, ligne in enumerate(lignes, 1):
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        if est_nom_dns(ligne):                                # nom DNS (adresse dynamique) : résolu par nginx-hardening.sh, pas ici
            continue
        m = LIGNE_RE.match(ligne)
        try:
            if not m:
                raise ValueError(ligne.strip())
            reseau = ipaddress.ip_network(m.group(1), strict=False)
        except ValueError:
            problemes.append(f"{chemin}:{n} : adresse invalide « {ligne.split('#')[0].strip()} »")
            continue
        commentaire = m.group(2) or ""
        options = set()
        expiration, temporaire = "", False
        for brut in OPTION_RE.findall(commentaire):
            if brut.strip().lower().startswith("temporaire"):
                temporaire = True
                date = brut.strip()[len("temporaire"):].strip()
                expiration = date if DATE_RE.match(date) else ""
                if not expiration:
                    problemes.append(f"{chemin}:{n} : [temporaire] sans date valide (AAAA-MM-JJ HH:MM:SS) : ligne ignorée")
                continue
            nom = OPTIONS.get(brut.strip().lower())
            if nom:
                options.add(nom)
            else:
                problemes.append(f"{chemin}:{n} : option inconnue « [{brut}] » (options : [partagée] [protégée])")
        libelle = OPTION_RE.sub("", commentaire).strip()
        entrees.append(Entree(reseau, libelle, "partagee" in options, "protegee" in options, f"{chemin}:{n}", temporaire, expiration))
    return entrees, problemes


def maintenant(env=None):
    """Date et heure locales (AAAA-MM-JJ HH:MM:SS) ; NGINX_TOOLS_MAINTENANT la remplace (tests)."""
    env = os.environ if env is None else env
    return env.get("NGINX_TOOLS_MAINTENANT") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@functools.lru_cache(maxsize=8192)
def _adresse(ip):
    """1.8 : adresse analysée une seule fois (app-log-live.py --advise cherchait la même adresse des centaines de milliers de fois) ;
    l'objet est immuable, le cache ne peut pas donner une réponse périmée. ValueError n'est pas gardé en cache."""
    return ipaddress.ip_address(ip)


def _plus_specifique(entrees, ip):
    """L'entrée dont la plage contient ip, la plus précise (préfixe le plus long) ; à égalité, la dernière lue."""
    try:
        adresse = _adresse(ip)
    except ValueError:
        return None
    meilleure = None
    for e in entrees:
        if e.reseau.version == adresse.version and adresse in e.reseau and (meilleure is None or e.reseau.prefixlen >= meilleure.reseau.prefixlen):
            meilleure = e
    return meilleure


class Listes(object):
    def __init__(self, blanche, lieux, fichiers, ancien, problemes):
        self.blanche, self.lieux, self.fichiers, self.ancien, self.problemes = blanche, lieux, fichiers, ancien, problemes

    def blanche_de(self, ip):
        """L'entrée de la liste blanche qui contient ip, ou None."""
        return _plus_specifique(self.blanche, ip)

    def lieu(self, ip):
        """Le lieu (le plus précis) qui contient ip, ou None."""
        return _plus_specifique(self.lieux, ip)

    def etiquette(self, ip):
        """Libellé court d'une adresse : liste blanche d'abord, puis lieu ; '' si inconnue."""
        e = self.blanche_de(ip) or self.lieu(ip)
        return e.libelle if e else ""

    def protegee(self, ip):
        """Adresse à ne jamais bannir : liste blanche, ou lieu [protégée]."""
        lieu = self.lieu(ip)
        return bool(self.blanche_de(ip) or (lieu and lieu.protegee))

    def reseaux_ne_pas_bannir(self):
        return [e.reseau for e in self.blanche] + [e.reseau for e in self.lieux if e.protegee]

    def resume(self):
        """Une ligne : fichiers lus et nombre d'entrées (« Listes : … »)."""
        blanche = self.fichiers.get("blanche")
        lieux = self.fichiers.get("lieux") or []
        a = (f"liste blanche {blanche} ({len(self.blanche)} adresses)" + (" — ANCIEN emplacement, à migrer : nginx-hardening.sh --update"
                                                                          if self.ancien else "")) if blanche else "liste blanche : aucun fichier"
        b = f"lieux {', '.join(lieux)} ({len(self.lieux)} plages)" if lieux else "lieux : aucun fichier"
        return f"Listes : {a} ; {b}"


def _personnel(chemin):
    """~/.NOM.conf à lire ; un ancien ~/.NOM.cfg est renommé d'abord (apps/_config.py migrer_ancien, mêmes avis que les programmes). Sans apps/_config.py :
    le .conf, ou l'ancien fichier s'il est seul (jamais d'exception)."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_config_voisin", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_config.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.migrer_ancien(chemin)
    except Exception:                                        # noqa: BLE001
        ancien = chemin[:-len(".conf")] + ".cfg" if chemin.endswith(".conf") else chemin
        return ancien if not os.path.exists(chemin) and os.path.exists(ancien) else chemin


def chemins(env=None, dossier_apps=None):
    """(chemin de la liste blanche, ancien chemin ou None, [chemins des lieux]) selon l'environnement."""
    env = os.environ if env is None else env
    blanche = env.get("NGINX_TOOLS_WHITE_LIST") or BLANCHE_DEFAUT
    ancien = None
    if not env.get("NGINX_TOOLS_WHITE_LIST") and dossier_apps:
        ancien = os.path.join(dossier_apps, "team-ips.list")
    lieux = [env["NGINX_TOOLS_IP_LOCATION"]] if env.get("NGINX_TOOLS_IP_LOCATION") else [LIEUX_DEFAUT, _personnel(os.path.expanduser(LIEUX_UTILISATEUR))]
    return blanche, ancien, lieux


def charger(dossier_apps=None, env=None):
    """Lit les deux listes (jamais d'exception : fichier absent = liste vide)."""
    blanche, ancien_chemin, lieux = chemins(env, dossier_apps)
    fichiers, problemes, est_ancien = {}, [], False
    entrees_blanche, p = lire_fichier(blanche)
    problemes += p
    if os.path.isfile(blanche):
        fichiers["blanche"] = blanche
    elif ancien_chemin and os.path.isfile(ancien_chemin):
        entrees_blanche, p = lire_fichier(ancien_chemin)
        problemes += p
        fichiers["blanche"], est_ancien = ancien_chemin, True
    maint = maintenant(env)
    # [temporaire] : entrées dont la date est atteinte, ou sans date valide, ignorées (nginx et fail2ban ne les reçoivent pas)
    expirees = [e for e in entrees_blanche if e.temporaire and (not e.expiration or maint >= e.expiration)]
    entrees_blanche = [e for e in entrees_blanche if e not in expirees]
    entrees_lieux = []
    for chemin in lieux:
        e, p = lire_fichier(chemin)
        entrees_lieux += e
        problemes += p
        if os.path.isfile(chemin):
            fichiers.setdefault("lieux", []).append(chemin)
    listes = Listes(entrees_blanche, entrees_lieux, fichiers, est_ancien, problemes)
    listes.expirees = expirees                                          # entrées [temporaire] ignorées
    listes.noms = [] if est_ancien else noms_dns(blanche)     # noms DNS de la liste blanche (résolus par nginx-hardening.sh)
    return listes


def main():
    if "--version" in sys.argv[1:]:
        print(f"_listes.py version {__version__}")
        return 0
    listes = charger(os.path.dirname(os.path.abspath(__file__)))
    if "--resume" in sys.argv[1:]:
        print(listes.resume())
        for p in listes.problemes:
            print(f"  ATTENTION {p}")
        return 0
    if "--ip" in sys.argv[1:]:
        ip = sys.argv[sys.argv.index("--ip") + 1] if len(sys.argv) > sys.argv.index("--ip") + 1 else ""
        b, lieu = listes.blanche_de(ip), listes.lieu(ip)
        print(f"{ip} : liste blanche : {b.libelle if b else 'non'} ; lieu : "
              + (f"{lieu.libelle}" + (" [partagée]" if lieu.partagee else "") + (" [protégée]" if lieu.protegee else "") if lieu else "non")
              + f" ; protégée : {'oui' if listes.protegee(ip) else 'non'}")
        return 0
    print("usage : _listes.py --resume | --ip ADRESSE | --version", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
