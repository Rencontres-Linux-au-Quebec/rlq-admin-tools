# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Bibliothèque commune (programmes Python) : lecture SEULE de la configuration YunoHost.

applications(racine=None) -> liste des applications installées, lues dans /etc/yunohost/apps/<nom>/settings.yml
(clés de premier niveau id, domain, path). Aucune écriture, aucune commande lancée. racine : préfixe des chemins
(défaut : APP_DETECT_ROOT, vide en production ; dossier temporaire pendant les tests).
est_yunohost(racine=None) -> True si /etc/yunohost/current_host ou /etc/yunohost/installed existe.
"""
import glob
import os
import re

RACINE_ENV = "APP_DETECT_ROOT"
MARQUES = ("/etc/yunohost/current_host", "/etc/yunohost/installed")
# Clés de premier niveau seulement : une clé indentée (sous-section du fichier) ne doit jamais remplacer la vraie.
CLE_RE = re.compile(r'^(id|domain|path):[ \t]*"?([^"\n]*?)"?[ \t]*$')


def _chemin(racine, *parties):
    return os.path.join(racine, *[p.lstrip("/") for p in parties])


def _racine(racine):
    return os.environ.get(RACINE_ENV, "") if racine is None else racine


def lire_settings(chemin):
    """Clés id, domain, path d'un settings.yml ; None si illisible (droits, fichier absent)."""
    valeurs = {}
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            for ligne in f:
                m = CLE_RE.match(ligne.rstrip("\n"))
                if m and m.group(1) not in valeurs:
                    valeurs[m.group(1)] = m.group(2).strip()
    except OSError:
        return None
    return valeurs


def est_yunohost(racine=None):
    racine = _racine(racine)
    return any(os.path.exists(_chemin(racine, marque)) for marque in MARQUES)


def applications(racine=None):
    """Applications YunoHost installées, triées par nom de dossier. Chaque entrée : name, id, domain, path, nginx_dir.
    Une application sans domaine lisible est retournée avec domain vide (à signaler, pas à ignorer)."""
    racine = _racine(racine)
    resultat = []
    for chemin in sorted(glob.glob(_chemin(racine, "/etc/yunohost/apps", "*", "settings.yml"))):
        valeurs = lire_settings(chemin)
        if valeurs is None:
            continue
        nom = os.path.basename(os.path.dirname(chemin))
        domaine = valeurs.get("domain", "")
        resultat.append({
            "name": nom,
            "id": valeurs.get("id") or nom,
            "domain": domaine,
            "path": valeurs.get("path") or "/",
            "nginx_dir": _chemin(racine, "/etc/nginx/conf.d", domaine + ".d") if domaine else "",
        })
    return resultat


def main(argv=None):
    """Sortie TSV (une application par ligne : nom, id, domaine, chemin), sans aucun secret.
    Usage : python3 apps/_yunohost.py [--root CHEMIN]  (sans --root : /etc, sous APP_DETECT_ROOT si défini)."""
    import argparse
    parser = argparse.ArgumentParser(description="Liste les applications YunoHost installées (lecture seule).")
    parser.add_argument("--root", default=None, help="racine des chemins (tests) ; défaut : APP_DETECT_ROOT ou /")
    args = parser.parse_args(argv)
    for app in applications(args.root):
        print("\t".join([app["name"], app["id"], app["domain"], app["path"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
