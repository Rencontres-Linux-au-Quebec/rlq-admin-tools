#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _limites.py - details of the 429 refusals (nginx rate limiting) for ONE address: what, when, which zone, which effects, what to change (shared module, apps/).
#
"""Lit les journaux d'accès nginx (access.log, access.log.1, *.gz) et le journal d'erreurs (lignes « limiting requests, excess: … by zone "…" ») et dit, pour UNE adresse :
combien de requêtes, combien de 429, sur quelles URL, dans quelle zone limit_req (le journal d'accès seul ne le dit pas), à quelle pointe (requêtes par seconde), et les
EFFETS probables (page ou ressource refusée, action POST perdue, appel de fond d'Odoo en erreur). Chaque constat est suivi du réglage nginx à envisager.
Lecture seule ; les heures sont LOCALES. Utilisé par app-log-live.py --rate-limit IP."""
import collections
import datetime
import glob
import gzip
import os
import re

__version__ = "1.2.20261022.231529"
DOSSIER_DEFAUT = "/var/log/nginx"
ACCES_RE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "([^"]*)" (\d{3}) (\S+)')
ERREUR_RE = re.compile(r'^(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d) .*limiting (requests|connections)(?:, excess: ([\d.]+))? by zone "([^"]+)", client: (\S+),.*?request: "(\S+) (\S+)')
RESSOURCE_RE = re.compile(r"\.(?:js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|map)(?:\?|$)|/web/static/|/web/assets/|/web/image|/website/static/", re.I)
FOND_RE = re.compile(r"/websocket|/longpolling|/bus/|/web/dataset/call|/web/webclient/|/mail/|/track(?:\?|$)|/iframefallback|manifest\.webmanifest|/web/session/", re.I)


def _ouvrir(chemin):
    return gzip.open(chemin, "rt", encoding="utf-8", errors="replace") if chemin.endswith(".gz") else open(chemin, encoding="utf-8", errors="replace")


def _fichiers(dossier, motif):
    return sorted(set(glob.glob(os.path.join(dossier, motif)) + glob.glob(os.path.join(dossier, motif + ".*"))))


def _heure_locale(texte):
    """« 15/Oct/2026:08:30:00 -0400 » -> datetime local, ou None."""
    try:
        return datetime.datetime.strptime(texte, "%d/%b/%Y:%H:%M:%S %z").astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def analyser(ip, dossier=DOSSIER_DEFAUT, fichiers_acces=None, fichiers_erreur=None):
    """Dictionnaire de faits sur `ip` : requetes, codes, par_url (429 par URL), zones, pointe_seconde, pointe_minute, pointe_heure, effets, jours, exemples ; None si aucun journal lisible."""
    acces = fichiers_acces if fichiers_acces is not None else _fichiers(dossier, "*access.log")
    erreurs = fichiers_erreur if fichiers_erreur is not None else _fichiers(dossier, "*error.log")
    if not acces and not erreurs:
        return None
    faits = {"ip": ip, "requetes": 0, "codes": collections.Counter(), "par_url": collections.Counter(), "total_url": collections.Counter(), "zones": collections.Counter(),
             "zone_url": collections.defaultdict(collections.Counter), "par_seconde": collections.Counter(), "limites_seconde": collections.Counter(), "limites_minute": collections.Counter(),
             "days": collections.Counter(), "effets": collections.Counter(), "premiere": None, "derniere": None, "excess_max": 0.0, "files": len(acces) + len(erreurs)}
    for chemin in acces:
        try:
            with _ouvrir(chemin) as f:
                for ligne in f:
                    if not ligne.startswith(ip + " "):
                        continue
                    m = ACCES_RE.match(ligne)
                    if not m:
                        continue
                    quand, requete, code = _heure_locale(m.group(2)), m.group(3).split(), m.group(4)
                    methode, url = (requete[0], requete[1]) if len(requete) >= 2 else ("?", "?")
                    chemin_url = url.split("?")[0]
                    faits["requetes"] += 1
                    faits["codes"][code] += 1
                    faits["total_url"][chemin_url] += 1
                    if quand:
                        faits["par_seconde"][quand.strftime("%Y-%m-%d %H:%M:%S")] += 1
                        faits["days"][quand.strftime("%Y-%m-%d")] += 1
                        faits["premiere"] = min(faits["premiere"] or quand, quand)
                        faits["derniere"] = max(faits["derniere"] or quand, quand)
                    if code == "429":
                        faits["par_url"][chemin_url] += 1
                        if quand:
                            faits["limites_seconde"][quand.strftime("%Y-%m-%d %H:%M:%S")] += 1
                            faits["limites_minute"][quand.strftime("%Y-%m-%d %H:%M")] += 1
                        if methode not in ("GET", "HEAD"):
                            faits["effets"]["action"] += 1
                        elif RESSOURCE_RE.search(url):
                            faits["effets"]["ressource"] += 1
                        elif FOND_RE.search(url):
                            faits["effets"]["fond"] += 1
                        else:
                            faits["effets"]["page"] += 1
        except OSError:
            continue
    for chemin in erreurs:
        try:
            with _ouvrir(chemin) as f:
                for ligne in f:
                    m = ERREUR_RE.match(ligne)
                    if m and m.group(5) == ip:
                        zone = m.group(4) + (" (limit_conn)" if m.group(2) == "connections" else "")       # limit_conn: too many SIMULTANEOUS connections (not a rate)
                        faits["zones"][zone] += 1
                        faits["zone_url"][zone][m.group(7).split("?")[0]] += 1
                        faits["excess_max"] = max(faits["excess_max"], float(m.group(3) or 0))
        except OSError:
            continue
    return faits


def recommandations(faits, zones_connues=None):
    """[(constat, quoi changer)] d'après les faits (jamais de modification)."""
    res, n429 = [], faits["codes"].get("429", 0)
    if not n429:
        return [("aucun 429 pour cette adresse dans les journaux lus", "rien à changer")]
    if not faits["zones"]:
        res.append(("la zone limit_req n'est pas connue : le journal d'accès ne la dit pas",
                    "ajouter dans nginx : limit_req_log_level warn; (défaut : error) ou lire error.log (« limiting requests, excess: … by zone »), et mettre $limit_req_status dans log_format"))
    for url, n in faits["par_url"].most_common(3):
        total = faits["total_url"][url]
        if FOND_RE.search(url) and n >= 10:
            res.append((f"{url} : {n} refus sur {total} requêtes (appel répété de la page, pas une personne qui clique)",
                        "regrouper ces appels dans un location séparé avec sa propre limit_req_zone (rate plus haut, burst 20+) plutôt que la zone générale ; ou espacer l'appel côté site"))
    pointe = max(faits["par_seconde"].values()) if faits["par_seconde"] else 0
    if pointe >= 20:
        res.append((f"pointe de {pointe} requêtes en une seconde : typique d'un chargement de page avec beaucoup de ressources ou de plusieurs personnes derrière la même adresse (université, entreprise)",
                    "ajouter l'adresse à la liste blanche (nginx-tools-white-list.conf) si c'est un lieu connu, ou augmenter burst (ex. burst=100 nodelay) pour la zone odoo_general_v2"))
    if faits["effets"].get("action"):
        res.append((f"{faits['effets']['action']} action(s) POST refusée(s) : un formulaire ou une inscription a pu être perdu",
                    "ne jamais limiter les POST de formulaires de la même façon que les pages : zone séparée avec burst, ou exemption pour les adresses connues"))
    if faits["effets"].get("ressource", 0) >= 20:
        res.append((f"{faits['effets']['ressource']} ressource(s) (JS, CSS, images) refusée(s) : page mal affichée chez la personne",
                    "exclure /web/static/, /web/assets/ et /website/static/ de limit_req (location avec limit_req off ; ou cache navigateur : expires 7d)"))
    conn = sum(n for z, n in faits["zones"].items() if "(limit_conn)" in z)
    if conn:
        res.append((f"{conn} refus par limit_conn : trop de connexions SIMULTANÉES de cette personne (plusieurs onglets, pages avec appels longs comme /track, /websocket, chargements parallèles)",
                    "augmenter la limite (limit_conn odoo_visiteur_v2 16;) ou ne pas appliquer limit_conn aux appels longs (location /websocket et /longpolling) ; vérifier que les onglets ouverts ne se multiplient pas"))
    if "odoo_login_v2" in faits["zones"]:
        res.append((f"{faits['zones']['odoo_login_v2']} refus sur la zone odoo_login_v2 (5 par minute) : plusieurs tentatives de connexion rapprochées",
                    "normal contre le bourrage d'identifiants ; si c'est une vraie personne, attendre une minute ; ne pas relâcher cette zone"))
    if not res:
        res.append((f"{n429} refus répartis sans cause évidente", "relire les URL ci-dessus et les zones ; ajuster rate / burst de la zone concernée"))
    return res


def lignes(faits):
    """Texte (lignes) du rapport, en français, heures locales."""
    if faits is None:
        return ["  Journaux nginx illisibles ou absents (root requis ? dossier " + DOSSIER_DEFAUT + ")."]
    n429, total = faits["codes"].get("429", 0), faits["requetes"]
    res = [f"Limitation de débit (429) pour {faits['ip']} — {faits['files']} fichier(s) de journal lu(s)"]
    if not total:
        return res + ["  Aucune requête de cette adresse dans les journaux lus."]
    res.append(f"  Requêtes : {total} (du {faits['premiere']:%Y-%m-%d %H:%M} au {faits['derniere']:%Y-%m-%d %H:%M}, heure locale) ; refusées en 429 : {n429} ({100 * n429 / total:.1f} %)")
    res.append("  Codes : " + ", ".join(f"{c} ×{n}" for c, n in faits["codes"].most_common(8)))
    if n429:
        res.append("  URL les plus refusées (refus / requêtes de cette adresse sur cette URL) :")
        res += [f"    {n:>5} / {faits['total_url'][u]:<5} {u}" for u, n in faits["par_url"].most_common(8)]
        if faits["zones"]:
            res.append("  Zones limit_req (error.log) : " + ", ".join(f"{z} ×{n}" for z, n in faits["zones"].most_common()) + f" ; dépassement maximal vu : {faits['excess_max']:g} requête(s)")
        pointe = faits["par_seconde"].most_common(1)
        if pointe:
            res.append(f"  Pointe : {pointe[0][1]} requêtes en une seconde ({pointe[0][0]}) ; jusqu'à {max(faits['limites_seconde'].values(), default=0)} refus en une seconde ; "
                       f"minute la plus refusée : {faits['limites_minute'].most_common(1)[0][0]} ({faits['limites_minute'].most_common(1)[0][1]} refus)")
        res.append("  Par jour (requêtes) : " + ", ".join(f"{j} {n}" for j, n in sorted(faits["days"].items())[-7:]))
        libelles = {"page": "page refusée (la personne voit « Too Many Requests »)", "ressource": "ressource refusée (JS / CSS / image : page mal affichée)",
                    "fond": "appel de fond refusé (suivi, notifications, manifeste : fonction qui s'arrête sans message)", "action": "action POST refusée (formulaire ou inscription possiblement perdu)"}
        res.append("  Effets probables : " + (", ".join(f"{n} {libelles[k]}" for k, n in faits["effets"].most_common()) or "aucun"))
    res.append("  Quoi faire :")
    res += [f"    - {c} → {q}" for c, q in recommandations(faits)]
    return res
