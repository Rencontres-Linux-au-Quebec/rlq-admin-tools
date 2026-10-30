#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _seuils.py - thresholds shared by web-monitor.py and app-log-live.py (shared module, apps/).
#
"""Seuils communs : une seule valeur par notion, lue par les deux programmes (web-monitor.py et app-log-live.py).

Les valeurs par défaut sont celles que les programmes utilisaient déjà. Un fichier les modifie, dans cet ordre (le dernier lu gagne) :
  /etc/default/app-seuils.conf, puis ~/.app-seuils.conf
Format : une clé par ligne, CLÉ=valeur ; les lignes commençant par # sont ignorées. Une valeur invalide est ignorée (avis sur stderr).

Clés (English: one value per notion, read by both programs):
  BURST_PAGES      pages distinctes dans BURST_WINDOW_S secondes à partir desquelles une rafale est un indice (>= 2)
  BURST_WINDOW_S   durée de la fenêtre de rafale, en secondes (>= 1)
  CONNECTIONS_PCT  % d'utilisation d'une limite à partir duquel un AVERTISSEMENT s'affiche, 0 = jamais (0 à 100)
  PROBE_404        pages 404 DIFFÉRENTES pour une même adresse : balayage de sondes (>= 1)
  REPEAT_MIN       bannissements fail2ban passés à partir desquels une adresse est « souvent bannie » (>= 1)

Utilisation : charger() -> (valeurs, fichiers lus, avis). Ne lève jamais d'exception pour un fichier absent ou mal formé.
"""
import os

__version__ = "1.0.20261029.212344"

FICHIERS = ("/etc/default/app-seuils.conf", os.path.join(os.path.expanduser("~"), ".app-seuils.conf"))

# Valeurs par défaut (types : int, sauf CONNECTIONS_PCT en float)
DEFAUTS = {
    "BURST_PAGES": 15,
    "BURST_WINDOW_S": 10,
    "CONNECTIONS_PCT": 80.0,
    "PROBE_404": 5,
    "REPEAT_MIN": 2,
}


def lire(chemin):
    """{CLÉ: valeur brute} d'un fichier CLÉ=valeur ; fichier absent ou illisible : {}."""
    res = {}
    try:
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#") or "=" not in ligne:
                    continue
                cle, _, valeur = ligne.partition("=")
                valeur = valeur.strip()
                if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                    valeur = valeur[1:-1]
                res[cle.strip().upper()] = valeur
    except (OSError, UnicodeDecodeError):
        pass
    return res


def valide(cle, valeur):
    """True si la valeur est dans la plage admise pour la clé."""
    if cle == "CONNECTIONS_PCT":
        return 0 <= valeur <= 100
    if cle == "BURST_PAGES":
        return valeur >= 2
    return valeur >= 1


def charger(fichiers=FICHIERS):
    """(valeurs, fichiers lus, avis) : valeurs = DEFAUTS modifié par les fichiers ; avis = messages pour les clés ignorées."""
    valeurs = dict(DEFAUTS)
    lus, avis = [], []
    for chemin in fichiers:
        if not os.path.isfile(chemin):
            continue
        lus.append(chemin)
        for cle, brute in lire(chemin).items():
            if cle not in DEFAUTS:
                avis.append(f"{chemin}: unknown key {cle} ignored / clé inconnue {cle} ignorée")
                continue
            try:
                valeur = float(brute) if isinstance(DEFAUTS[cle], float) else int(brute)
            except ValueError:
                avis.append(f"{chemin}: {cle}={brute!r} is not a number / n'est pas un nombre : défaut conservé")
                continue
            if not valide(cle, valeur):
                avis.append(f"{chemin}: {cle}={brute} out of range / hors limites : défaut conservé")
                continue
            valeurs[cle] = valeur
    return valeurs, lus, avis
