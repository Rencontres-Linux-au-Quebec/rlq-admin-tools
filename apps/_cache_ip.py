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
# _cache_ip.py - PERMANENT CACHE of information about IP addresses: DNS name (PTR), owner of the address block (RDAP: organization,
# network, range, abuse address), country. An address is looked up on the Internet only ONCE, then served instantly: the start of
# app-log-live.py no longer waits for its lookups, and nginx-log-audit.sh --investigate does not ask again what it already knows.
#   * Fichier SQLite : /var/lib/nginx-tools/ip-cache.sqlite (root), sinon ~/.cache/nginx-tools/ip-cache.sqlite ; droits 600. Variable
#     NGINX_TOOLS_IP_CACHE: other path, or "off" to disable (the tests set it to "off").
#   * Validity periods: DNS name found 30 days, "no name" 3 days; block owner and country 90 days. A lookup that FAILED
#     (network unreachable) is NEVER stored: it will be retried.
#   * Privacy: an IP address is personal information. Addresses not seen for 180 days are erased (purge at program startup
#     of the programs); "--no-cache" (app-log-live.py, _reseau.py) reads and writes nothing; "_cache_ip.py --clear" erases everything.
#
#
# Usage (normalement appele par les programmes de la suite) :
#   python3 apps/_cache_ip.py --stats          contenu du cache
#   python3 apps/_cache_ip.py --show ADRESSE   ce que le cache sait d'une adresse
#   python3 apps/_cache_ip.py --purge [DAYS]  erases the addresses not seen for DAYS days (180 by default)
#   python3 apps/_cache_ip.py --clear          efface tout le cache
#   python3 apps/_cache_ip.py --version

import os
import sqlite3
import sys
import threading
import time

__version__ = "1.4.20261030.153422"

DEFAUT_ROOT = "/var/lib/nginx-tools/ip-cache.sqlite"
JOUR = 86400.0
VALIDITE = {"ptr": 30 * JOUR, "ptr_vide": 3 * JOUR, "rdap": 90 * JOUR, "pays": 90 * JOUR}
RETENTION_JOURS = 180
CHAMPS_RDAP = ("organisation", "reseau", "plage", "pays", "abus", "registre", "source")
SCHEMA = """CREATE TABLE IF NOT EXISTS ip (
    ip TEXT PRIMARY KEY,
    ptr TEXT, ptr_t REAL,
    organisation TEXT, reseau TEXT, plage TEXT, abus TEXT, registre TEXT, source TEXT, rdap_t REAL,
    pays TEXT, pays_t REAL, pays_src TEXT,
    vu1 REAL, vu2 REAL, n INTEGER NOT NULL DEFAULT 0)"""


def chemin_cache(env=None):
    """Chemin du fichier de cache, ou None si le cache est désactivé (NGINX_TOOLS_IP_CACHE=off)."""
    env = os.environ if env is None else env
    explicite = env.get("NGINX_TOOLS_IP_CACHE", "")
    if explicite.lower() in ("off", "non", "0", "no"):
        return None
    if explicite:
        return explicite
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return DEFAUT_ROOT
    return os.path.join(os.path.expanduser("~"), ".cache", "nginx-tools", "ip-cache.sqlite")


class Cache(object):
    """Le cache. Jamais d'exception pour l'appelant : fichier impossible à ouvrir ou abîmé = cache désactivé (self.raison dit pourquoi)."""
    maintenant = staticmethod(time.time)

    def __init__(self, chemin):
        self.chemin, self.conn, self.raison = chemin, None, ""
        self.verrou = threading.Lock()
        if not chemin:
            self.raison = "désactivé"
            return
        try:
            os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
            neuf = not os.path.exists(chemin)
            self.conn = sqlite3.connect(chemin, timeout=15, isolation_level=None, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute(SCHEMA)
            if neuf:
                os.chmod(chemin, 0o600)
        except (OSError, sqlite3.Error) as e:
            self._abandonner(e)

    def _abandonner(self, erreur):
        self.raison = f"inutilisable ({type(erreur).__name__}: {erreur})"
        try:
            if self.conn:
                self.conn.close()
        except sqlite3.Error:
            pass
        self.conn = None

    @property
    def actif(self):
        return self.conn is not None

    def _executer(self, requete, args=()):
        if not self.conn:
            return None
        with self.verrou:
            try:
                return self.conn.execute(requete, args).fetchall()
            except sqlite3.Error as e:
                self._abandonner(e)
                return None

    def lire(self, ip):
        """Toutes les colonnes connues de l'adresse (dict), ou None."""
        lignes = self._executer("SELECT * FROM ip WHERE ip = ?", (ip,))
        if not lignes:
            return None
        colonnes = [c[1] for c in (self._executer("PRAGMA table_info(ip)") or [])]
        return dict(zip(colonnes, lignes[0]))

    def _frais(self, horodatage, duree):
        return horodatage is not None and self.maintenant() - horodatage < duree

    def ptr(self, ip):
        """Nom DNS mémorisé : le nom, \"\" (aucun nom, vérifié récemment) ou None (inconnu ou périmé : à chercher)."""
        e = self.lire(ip)
        if not e or e["ptr"] is None:
            return None
        return e["ptr"] if self._frais(e["ptr_t"], VALIDITE["ptr"] if e["ptr"] else VALIDITE["ptr_vide"]) else None

    def rdap(self, ip):
        """Propriétaire du bloc mémorisé (mêmes champs que _reseau.fournisseur), ou None (inconnu ou périmé)."""
        e = self.lire(ip)
        if not e or not self._frais(e["rdap_t"], VALIDITE["rdap"]):
            return None
        return {c: e[c] or "" for c in CHAMPS_RDAP}

    def pays(self, ip):
        """Code du pays mémorisé, ou None (inconnu ou périmé)."""
        e = self.lire(ip)
        return e["pays"] if e and e["pays"] and self._frais(e["pays_t"], VALIDITE["pays"]) else None

    def _ecrire(self, ip, champs):
        t = self.maintenant()
        colonnes = list(champs)
        self._executer(f"INSERT INTO ip (ip, vu1, vu2, {', '.join(colonnes)}) VALUES (?, ?, ?, {', '.join('?' * len(colonnes))}) "
                       f"ON CONFLICT(ip) DO UPDATE SET {', '.join(c + ' = excluded.' + c for c in colonnes)}",
                       (ip, t, t) + tuple(champs[c] for c in colonnes))

    def ecrire_ptr(self, ip, nom):
        """Nom DNS trouvé, ou \"\" quand le DNS dit qu'il n'y en a pas (jamais pour une erreur de réseau)."""
        self._ecrire(ip, {"ptr": nom or "", "ptr_t": self.maintenant()})

    def ecrire_rdap(self, ip, r):
        """Réponse de _reseau.fournisseur ; le pays qu'elle contient est mémorisé aussi."""
        champs = {c: r.get(c) or "" for c in CHAMPS_RDAP if c != "pays"}
        champs["rdap_t"] = self.maintenant()
        if r.get("pays"):
            champs.update(pays=r["pays"], pays_t=self.maintenant(), pays_src="rdap")
        self._ecrire(ip, champs)

    def ecrire_pays(self, ip, pays, source):
        if pays:
            self._ecrire(ip, {"pays": pays, "pays_t": self.maintenant(), "pays_src": source})

    def toucher(self, ip):
        """Note que l'adresse vient d'être vue (dernière vue, nombre de passages) ; la crée au besoin."""
        t = self.maintenant()
        self._executer("INSERT INTO ip (ip, vu1, vu2, n) VALUES (?, ?, ?, 1) ON CONFLICT(ip) DO UPDATE SET vu2 = excluded.vu2, n = n + 1", (ip, t, t))

    def purger(self, jours=RETENTION_JOURS):
        """Efface les adresses non revues depuis JOURS jours ; retourne leur nombre."""
        avant = self._executer("SELECT COUNT(*) FROM ip")
        self._executer("DELETE FROM ip WHERE vu2 IS NULL OR vu2 < ?", (self.maintenant() - jours * JOUR,))
        apres = self._executer("SELECT COUNT(*) FROM ip")
        return (avant[0][0] - apres[0][0]) if avant and apres else 0

    def vider(self):
        self._executer("DELETE FROM ip")

    def stats(self):
        """{adresses, avec_ptr, avec_proprietaire, avec_pays, plus_ancienne, taille} (taille du fichier en octets)."""
        r = self._executer("SELECT COUNT(*), COUNT(NULLIF(ptr, '')), COUNT(NULLIF(organisation, '') ), COUNT(pays), MIN(vu2) FROM ip")
        if not r:
            return {"adresses": 0, "avec_ptr": 0, "avec_proprietaire": 0, "avec_pays": 0, "plus_ancienne": None, "taille": 0}
        try:
            taille = os.path.getsize(self.chemin)
        except OSError:
            taille = 0
        return {"adresses": r[0][0], "avec_ptr": r[0][1], "avec_proprietaire": r[0][2], "avec_pays": r[0][3], "plus_ancienne": r[0][4], "taille": taille}

    def resume(self):
        """Une ligne pour la sortie d'erreur des programmes : fichier, nombre d'adresses, taille."""
        if not self.actif:
            return f"Cache des adresses : {self.raison}"
        s = self.stats()
        return f"Cache des adresses : {self.chemin} ({s['adresses']} adresses, {s['taille'] // 1024} Ko)"


def ouvrir(env=None, chemin=None):
    """Le cache par défaut (selon l'environnement) ou celui du chemin donné ; toujours un objet (éventuellement désactivé)."""
    return Cache(chemin if chemin is not None else chemin_cache(env))


def _date(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "jamais"


def main():
    args = sys.argv[1:]
    if "--version" in args:
        print(f"_cache_ip.py version {__version__}")
        return 0
    cache = ouvrir()
    if not cache.actif:
        print(f"Cache des adresses : {cache.raison}", file=sys.stderr)
        return 1
    if "--stats" in args:
        s = cache.stats()
        print(cache.resume())
        print(f"  avec nom DNS : {s['avec_ptr']} ; avec propriétaire du bloc (organisation) : {s['avec_proprietaire']} ; avec pays : {s['avec_pays']}")
        print(f"  la plus ancienne vue : {_date(s['plus_ancienne'])} (purge : plus de {RETENTION_JOURS} jours sans nouvelle vue)")
        return 0
    if "--show" in args:
        ip = args[args.index("--show") + 1] if len(args) > args.index("--show") + 1 else ""
        e = cache.lire(ip)
        if not e:
            print(f"{ip} : inconnue du cache")
            return 1
        print(f"{ip} : vue {e['n']} fois, du {_date(e['vu1'])} au {_date(e['vu2'])}")
        print(f"  nom DNS : {e['ptr'] if e['ptr'] is not None else 'pas encore cherché'}{' (aucun nom)' if e['ptr'] == '' else ''}"
              + (f" — cherché le {_date(e['ptr_t'])}" if e["ptr_t"] else ""))
        print(f"  propriétaire du bloc : {e['organisation'] or e['reseau'] or 'pas encore cherché'}"
              + (f" ({'organisation' if e['organisation'] else 'nom du réseau'}) — plage {e['plage']}" if e["organisation"] or e["reseau"] else ""))
        print(f"  pays : {e['pays'] or 'inconnu'}" + (f" ({e['pays_src']})" if e["pays_src"] else ""))
        return 0
    if "--purge" in args:
        i = args.index("--purge")
        jours = int(args[i + 1]) if len(args) > i + 1 and args[i + 1].isdigit() else RETENTION_JOURS
        print(f"{cache.purger(jours)} adresses non revues depuis {jours} jours effacées.")
        return 0
    if "--clear" in args:
        cache.vider()
        print("Cache des adresses vidé.")
        return 0
    print("usage : _cache_ip.py --stats | --show ADRESSE | --purge [JOURS] | --clear | --version", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
