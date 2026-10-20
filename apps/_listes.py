#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _listes.py — les DEUX listes d'adresses propres à une installation, lues hors des archives (jamais livrées) :
#   * LISTE BLANCHE  /etc/default/nginx-tools-white-list.conf : adresses de confiance (équipe) — jamais bannies, accès aux sites DEV et
#     LAB. Lue SEULEMENT dans /etc/default (elle donne accès : aucun fichier utilisateur caché).
#   * LIEUX          /etc/default/nginx-tools-ip-location.conf puis ~/.nginx-tools-ip-location.cfg : un NOM pour une adresse ou une plage
#     (université, bureau…). Descriptif : ne donne AUCUN accès.
# Syntaxe commune, une entrée par ligne :   ADRESSE-OU-PLAGE   # libellé   [option] [option]
#   [partagée]  plusieurs personnes derrière la même adresse : on affiche le lieu, jamais un nom de personne
#   [protégée]  jamais bannie ni recommandée au bannissement (sans aucun accès : c'est la liste blanche qui en donne)
# Transition : tant que /etc/default/nginx-tools-white-list.conf n'existe pas, l'ancienne liste apps/team-ips.list est lue (avec un avertissement) ;
# nginx-hardening.sh --update la migre. Variables d'environnement (tests) : NGINX_TOOLS_WHITE_LIST, NGINX_TOOLS_IP_LOCATION (fichier unique).
#
# HISTORIQUE DE VERSION (resume — voir doc/_listes.changelog.txt pour le detail complet) :
#   1.2.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.1.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.0.20261007.093208 — Premiere version : liste blanche et lieux, lecteur commun (remplace six analyseurs).
#
# Usage (normalement appele par les programmes de la suite) :
#   python3 apps/_listes.py --resume          fichiers lus et nombre d'entrees
#   python3 apps/_listes.py --ip ADRESSE      libelles connus pour cette adresse
#   python3 apps/_listes.py --version

import ipaddress
import os
import re
import sys

__version__ = "1.2.20261019.150215"

BLANCHE_DEFAUT = "/etc/default/nginx-tools-white-list.conf"
LIEUX_DEFAUT = "/etc/default/nginx-tools-ip-location.conf"
LIEUX_UTILISATEUR = "~/.nginx-tools-ip-location.cfg"
LIGNE_RE = re.compile(r"^\s*([0-9A-Fa-f:.]+(?:/\d{1,3})?)\s*(?:#(.*))?$")
OPTION_RE = re.compile(r"\[([^\]]*)\]")
OPTIONS = {"partagee": "partagee", "partagée": "partagee", "protegee": "protegee", "protégée": "protegee"}


class Entree(object):
    """Une ligne d'une liste : réseau, libellé, options, et d'où elle vient (fichier:ligne)."""
    __slots__ = ("reseau", "libelle", "partagee", "protegee", "source")

    def __init__(self, reseau, libelle, partagee, protegee, source):
        self.reseau, self.libelle, self.partagee, self.protegee, self.source = reseau, libelle, partagee, protegee, source


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
        for brut in OPTION_RE.findall(commentaire):
            nom = OPTIONS.get(brut.strip().lower())
            if nom:
                options.add(nom)
            else:
                problemes.append(f"{chemin}:{n} : option inconnue « [{brut}] » (options : [partagée] [protégée])")
        libelle = OPTION_RE.sub("", commentaire).strip()
        entrees.append(Entree(reseau, libelle, "partagee" in options, "protegee" in options, f"{chemin}:{n}"))
    return entrees, problemes


def _plus_specifique(entrees, ip):
    """L'entrée dont la plage contient ip, la plus précise (préfixe le plus long) ; à égalité, la dernière lue."""
    try:
        adresse = ipaddress.ip_address(ip)
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
        a = (f"liste blanche {blanche} ({len(self.blanche)} adresse(s))" + (" — ANCIEN emplacement, à migrer : nginx-hardening.sh --update"
                                                                          if self.ancien else "")) if blanche else "liste blanche : aucun fichier"
        b = f"lieux {', '.join(lieux)} ({len(self.lieux)} plage(s))" if lieux else "lieux : aucun fichier"
        return f"Listes : {a} ; {b}"


def chemins(env=None, dossier_apps=None):
    """(chemin de la liste blanche, ancien chemin ou None, [chemins des lieux]) selon l'environnement."""
    env = os.environ if env is None else env
    blanche = env.get("NGINX_TOOLS_WHITE_LIST") or BLANCHE_DEFAUT
    ancien = None
    if not env.get("NGINX_TOOLS_WHITE_LIST") and dossier_apps:
        ancien = os.path.join(dossier_apps, "team-ips.list")
    lieux = [env["NGINX_TOOLS_IP_LOCATION"]] if env.get("NGINX_TOOLS_IP_LOCATION") else [LIEUX_DEFAUT, os.path.expanduser(LIEUX_UTILISATEUR)]
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
    entrees_lieux = []
    for chemin in lieux:
        e, p = lire_fichier(chemin)
        entrees_lieux += e
        problemes += p
        if os.path.isfile(chemin):
            fichiers.setdefault("lieux", []).append(chemin)
    return Listes(entrees_blanche, entrees_lieux, fichiers, est_ancien, problemes)


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
