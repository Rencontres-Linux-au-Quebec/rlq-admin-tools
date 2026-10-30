#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _connexions.py - connections to Odoo (HTTP, chat / websocket, PostgreSQL, nginx) and nearby limits (shared module, apps/).
#
"""Mesure, sans rien modifier, ce qui s'approche d'une limite quand le nombre de connexions monte (chat d'Odoo = websockets sur le port gevent, pages HTTP,
PostgreSQL, nginx) et dit QUEL PARAMÈTRE changer. Utilisé par app-log-live.py (vérification chaque minute) et web-monitor.py (sommaire).

Limites regardées (pourcentage d'utilisation) :
  - descripteurs de fichiers du processus gevent (websockets : un par connexion du chat) et du processus HTTP d'Odoo : limite « Max open files » du processus
    (LimitNOFILE de l'unité systemd) ;
  - connexions PostgreSQL / max_connections, et total théorique d'Odoo ((workers + crons + gevent) × db_maxconn) contre max_connections ;
  - connexions établies sur les ports 80/443 contre worker_connections de nginx.
Aucune mesure impossible (pas root, outil absent) ne fait échouer : la mesure vaut None et le diagnostic l'ignore."""
import os
import re
import subprocess

__version__ = "1.4.20261030.153422"
POSTGRES_RUN = ["runuser", "-u", "postgres", "--"] if os.geteuid() == 0 else ["sudo", "-n", "-u", "postgres", "--"]     # 1.2: root or sudo -n (see _odoo_db.py)
SEUIL_DEFAUT = 80          # % utilization from which a warning is shown
SEUIL_CRITIQUE = 95


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def etablies(port):
    """Nombre de connexions TCP établies dont le port local est `port` (ss) ; None si ss est absent."""
    code, sortie = _run(["ss", "-Htn", "state", "established", f"( sport = :{port} )"])
    return len([l for l in sortie.splitlines() if l.strip()]) if code == 0 else None


def pid_ecoute(port):
    """PID du processus qui écoute sur `port` (ss -p, root requis pour voir les processus des autres comptes), ou None."""
    code, sortie = _run(["ss", "-Htlnp", f"( sport = :{port} )"])
    m = re.search(r"pid=(\d+)", sortie) if code == 0 else None
    return int(m.group(1)) if m else None


def descripteurs(pid):
    """(ouverts, limite souple) de /proc/PID ; None si illisible."""
    try:
        ouverts = len(os.listdir(f"/proc/{pid}/fd"))
        with open(f"/proc/{pid}/limits", encoding="utf-8", errors="replace") as f:
            m = re.search(r"Max open files\s+(\d+|unlimited)", f.read())
    except OSError:
        return None
    if not m or m.group(1) == "unlimited":
        return None
    return ouverts, int(m.group(1))


def _entier(valeur, defaut):
    try:
        return int(str(valeur).strip())
    except ValueError:
        return defaut


def postgres():
    """(connexions clientes, max_connections) de PostgreSQL ; None si impossible (pas root, psql absent)."""
    if os.geteuid() != 0:
        return None
    code, sortie = _run(POSTGRES_RUN + ["psql", "-Atc",
                         "select (select count(*) from pg_stat_activity where backend_type = 'client backend'), current_setting('max_connections')"], 20)
    m = re.match(r"^(\d+)\|(\d+)$", sortie.strip()) if code == 0 else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def worker_connections_nginx():
    """worker_connections de nginx (nginx -T), 512 par défaut ; None si nginx est absent."""
    code, sortie = _run(["nginx", "-T"], 20)
    if code != 0:
        return None
    m = re.search(r"^\s*worker_connections\s+(\d+)\s*;", sortie, re.M)
    return int(m.group(1)) if m else 512


def mesurer(conf, valeur):
    """Mesures brutes. `conf` : dict d'apps/_odoo_conf.lire() ; `valeur(cle)` : lecture d'un réglage du fichier de configuration d'Odoo (apps/_odoo_conf.valeur)."""
    http, gevent = conf.get("http_port", "8069"), conf.get("gevent_port", "8072")
    m = {"http_port": http, "gevent_port": gevent,
         "workers": _entier(valeur("workers"), 0), "crons": _entier(valeur("max_cron_threads"), 2),
         "db_maxconn": _entier(valeur("db_maxconn"), 64), "db_maxconn_gevent": _entier(valeur("db_maxconn_gevent"), 0),
         "websockets": etablies(gevent), "http": etablies(http), "nginx_clients": None, "fd_gevent": None, "fd_http": None,
         "postgres": postgres(), "worker_connections": worker_connections_nginx()}
    https = [n for n in (etablies(80), etablies(443)) if n is not None]
    m["nginx_clients"] = sum(https) if https else None
    for cle, port in (("fd_gevent", gevent), ("fd_http", http)):
        pid = pid_ecoute(port)
        m[cle] = descripteurs(pid) if pid else None
    return m


def _niveau(pct, seuil):
    return "crit" if pct >= SEUIL_CRITIQUE else "warn" if pct >= seuil else None


def diagnostiquer(m, seuil=SEUIL_DEFAUT, service="odoo.service"):
    """[(niveau 'warn'|'crit', constat, paramètre à changer)] pour les limites atteintes à `seuil` % ou plus (textes en français)."""
    res = []

    def ajouter(pct, constat, conseil):
        niveau = _niveau(pct, seuil)
        if niveau:
            res.append((niveau, constat, conseil))
    systemd = (f"systemd : « systemctl edit {service} » puis, sous [Service], LimitNOFILE=65535, « systemctl restart {service} » ; "
               "nginx : worker_rlimit_nofile (nginx.conf) au moins égal")
    if m.get("fd_gevent"):
        ouverts, limite = m["fd_gevent"]
        ajouter(100 * ouverts / limite, f"processus du chat d'Odoo (websocket, port {m['gevent_port']}) : {ouverts} descripteurs de fichiers sur {limite} "
                f"({m['websockets'] if m['websockets'] is not None else '?'} connexions établies)",
                f"chaque connexion du chat en utilise un : augmenter la limite — {systemd}")
    if m.get("fd_http"):
        ouverts, limite = m["fd_http"]
        ajouter(100 * ouverts / limite, f"processus HTTP d'Odoo (port {m['http_port']}) : {ouverts} descripteurs de fichiers sur {limite}", f"augmenter la limite — {systemd}")
    pg = m.get("postgres")
    if pg:
        ajouter(100 * pg[0] / pg[1], f"PostgreSQL : {pg[0]} connexions sur max_connections = {pg[1]}",
                "postgresql.conf : max_connections (redémarrage de PostgreSQL) ; ou, dans la configuration d'Odoo, réduire db_maxconn (par processus) / "
                "db_maxconn_gevent (processus du chat)")
        total = (m["workers"] + m["crons"] + 1) * m["db_maxconn"] if m["workers"] else m["db_maxconn"]
        if total >= pg[1] and (pg[0] * 100 / pg[1]) >= seuil:
            res.append(("warn", f"Odoo peut ouvrir jusqu'à {total} connexions ((workers {m['workers']} + crons {m['crons']} + chat) × db_maxconn {m['db_maxconn']}) "
                                f"pour max_connections = {pg[1]}",
                        "configuration d'Odoo : db_maxconn plus bas, ou max_connections plus haut dans postgresql.conf"))
    if m.get("worker_connections") and m.get("nginx_clients") is not None:
        ajouter(100 * m["nginx_clients"] / m["worker_connections"], f"nginx : {m['nginx_clients']} connexions clientes établies pour worker_connections = {m['worker_connections']} par processus",
                "nginx.conf, bloc events { worker_connections 4096; } (et worker_rlimit_nofile), puis « nginx -t && systemctl reload nginx »")
    return res


def resume(m):
    """Une ligne de chiffres (chat, HTTP, PostgreSQL) pour le sommaire ou la touche de diagnostic ; chaîne vide si rien n'est mesurable."""
    morceaux = []
    if m.get("websockets") is not None:
        morceaux.append(f"chat (websocket, port {m['gevent_port']}) : {m['websockets']}")
    if m.get("http") is not None:
        morceaux.append(f"HTTP (port {m['http_port']}) : {m['http']}")
    if m.get("postgres"):
        morceaux.append(f"PostgreSQL : {m['postgres'][0]}/{m['postgres'][1]}")
    return " · ".join(morceaux)
