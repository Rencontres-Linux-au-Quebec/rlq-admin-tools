#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026  Services-Linux Conseils Inc <Martial@Bigras.ca> <Martial.Bigras@Services-Conseils-Linux.com>
# Licence : GNU Affero General Public License, version 3 ou ultérieure — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _reseau.py — PROPRIÉTAIRE du bloc d'adresses d'une IP (RDAP, sinon whois) : organisation enregistrée ou nom du réseau, plage, pays, adresse de
# signalement. Pas forcément un fournisseur d'accès : hébergeur, nuage, moteur de recherche, entreprise ; toutes les adresses du bloc ont le même.
# d'abus. RDAP (successeur de whois, réponse JSON) interrogé par https://rdap.org, qui redirige vers le bon registre
# (ARIN, RIPE, LACNIC, APNIC, AFRINIC) ; à défaut, la commande whois. Seule l'adresse demandée est envoyée.
# Utilisé par nginx-log-audit.sh (--investigate) et app-log-live.py.
#
# HISTORIQUE DE VERSION (resume — voir doc/_reseau.changelog.txt pour le detail complet) :
#   1.2.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.1.20261007.171721 — Cache permanent (apps/_cache_ip.py) ; --no-cache ; proprietaire du bloc d'adresses.
#   1.0.20261002.073514 — Premiere version : code RDAP/whois partage (auparavant integre a nginx-log-audit.sh 2.19).
#
# Usage (normalement appele par les programmes de la suite) :
#   python3 apps/_reseau.py IP            titulaire, reseau, plage, pays, abus (lisible)
#   python3 apps/_reseau.py --raw IP      une ligne, champs separes par le caractere 0x1f (pour les scripts bash)
#   python3 apps/_reseau.py --version

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

__version__ = "1.2.20261016.173838"

VERBOSE = False     # --verbose : chaque commande externe (curl, wget, whois) est affichee avant son execution
SEP = "\x1f"
CHAMPS = ("organisation", "reseau", "plage", "pays", "abus", "registre", "source")
WHOIS_CHAMPS = {"organisation": r"OrgName|org-name|owner|descr", "reseau": r"NetName|netname",
                "plage": r"CIDR|inetnum|NetRange|inet6num", "pays": r"Country", "abus": r"OrgAbuseEmail|abuse-mailbox"}


def lancer(cmd, delai):
    """Sortie standard d'une commande ; chaine vide si absente, en echec ou trop longue."""
    if VERBOSE:
        print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=delai + 2, universal_newlines=True, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _vcard(entite, champ):
    for x in (entite.get("vcardArray") or [None, []])[1]:
        if x and x[0] == champ:
            v = x[3]
            return " ".join(v) if isinstance(v, list) else str(v)
    return ""


def _entites(entite):
    for x in entite.get("entities") or []:
        yield x
        yield from _entites(x)


def lire_rdap(texte):
    """Champs d'une reponse RDAP (JSON) ; None si illisible."""
    try:
        d = json.loads(texte)
        organisation = abus = ""
        for e in _entites(d):
            roles = e.get("roles") or []
            if not organisation and ("registrant" in roles or "administrative" in roles):
                organisation = _vcard(e, "fn")
            if not abus and "abuse" in roles:
                abus = _vcard(e, "email")
        cidrs = ["%s/%s" % (c.get("v4prefix") or c.get("v6prefix"), c.get("length")) for c in d.get("cidr0_cidrs") or []]
        plage = ", ".join(cidrs) or " - ".join(x for x in (d.get("startAddress"), d.get("endAddress")) if x)
        return {"organisation": organisation, "reseau": d.get("name") or "", "plage": plage,
                "pays": d.get("country") or "", "abus": abus, "registre": d.get("port43") or "", "source": "RDAP"}
    except (ValueError, AttributeError, TypeError, IndexError):
        return None


def lire_whois(texte):
    r = {"registre": "", "source": "whois"}
    for champ, noms in WHOIS_CHAMPS.items():
        m = re.search(r"(?im)^(?:%s):[ \t]*(.+)$" % noms, texte)
        r[champ] = m.group(1).strip() if m else ""
    return r


def ouvrir_cache(cache):
    """« auto » : le cache par défaut (apps/_cache_ip.py, selon NGINX_TOOLS_IP_CACHE) ; None : aucun cache ; un objet Cache : tel quel.
    Jamais d'exception : composant absent ou cache inutilisable = pas de cache."""
    if cache != "auto":
        return cache if cache is not None and getattr(cache, "actif", False) else None
    try:
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache_ip.py")
        spec = importlib.util.spec_from_file_location("_cache_ip", chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        c = module.ouvrir()
        return c if c.actif else None
    except (OSError, AttributeError, ImportError):
        return None


def fournisseur(ip, delai=10, cache="auto"):
    """{organisation, reseau, plage, pays, abus, registre, source} ou None (ni rdap.org joignable, ni whois). Le résultat est mémorisé 90 jours
    dans le cache des adresses (apps/_cache_ip.py) : une adresse n'est demandée qu'une fois ; un ÉCHEC n'est jamais mémorisé."""
    c = ouvrir_cache(cache)
    if c is not None:
        memorise = c.rdap(ip)
        if memorise:
            if VERBOSE:
                print(f"+ (cache des adresses) propriétaire du bloc de {ip} : {memorise['organisation'] or memorise['reseau']}", file=sys.stderr)
            return memorise
    r = _interroger(ip, delai)
    if r is not None and c is not None:
        c.ecrire_rdap(ip, r)
    return r


def _interroger(ip, delai):
    texte = ""
    if shutil.which("curl"):
        texte = lancer(["curl", "-fsSL", "--max-time", str(delai), "-H", "Accept: application/rdap+json",
                        "https://rdap.org/ip/" + ip], delai)
    elif shutil.which("wget"):
        texte = lancer(["wget", "-qO-", "--timeout=%d" % delai, "https://rdap.org/ip/" + ip], delai)
    r = lire_rdap(texte) if texte else None
    if r is None and shutil.which("whois"):
        r = lire_whois(lancer(["whois", ip], delai))
    if r is None or not (r["organisation"] or r["reseau"] or r["plage"]):
        return None
    return r


def main():
    p = argparse.ArgumentParser(description="Propriétaire du bloc d'adresses (RDAP, sinon whois) d'une adresse IP.")
    p.add_argument("ip", nargs="?", help="adresse IP")
    p.add_argument("--no-cache", action="store_true", help="Ne lit ni n'écrit le cache des adresses (apps/_cache_ip.py)")
    p.add_argument("--raw", action="store_true", help="Une ligne, champs séparés par le caractère 0x1f (pour bash)")
    p.add_argument("-v", "--verbose", action="store_true", help="Affiche chaque commande externe exécutée")
    p.add_argument("--version", action="version", version=f"_reseau.py version {__version__}")
    a = p.parse_args()
    global VERBOSE
    VERBOSE = a.verbose
    if not a.ip or not re.fullmatch(r"[0-9a-fA-F:.]+", a.ip):
        p.error("une adresse IP est attendue")
    r = fournisseur(a.ip, cache=None if a.no_cache else "auto")
    if a.raw:
        if r:
            print(SEP.join(r[c].replace(SEP, " ").replace("\n", " ") for c in CHAMPS))
        return 0 if r else 1
    if not r:
        print("Propriétaire du bloc d'adresses : inconnu (ni rdap.org joignable par curl/wget, ni commande whois)")
        return 1
    print(f"Propriétaire du bloc d'adresses : {r['organisation'] or r['reseau']} ({'organisation' if r['organisation'] else 'nom du réseau'})"
          + (f" — pays {r['pays']}" if r["pays"] else ""))
    print(f"  réseau {r['reseau'] or '?'}" + (f" ({r['plage']})" if r["plage"] else "")
          + f" — source {r['source']}" + (f" ({r['registre']})" if r["registre"] else ""))
    if r["abus"]:
        print(f"  signalement d'abus : {r['abus']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)
