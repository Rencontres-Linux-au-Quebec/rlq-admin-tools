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
# _bbb.py — état de BigBlueButton : versions (paquets, Greenlight), empreinte des fichiers de configuration GÉRÉS PAR BBB
# et des NÔTRES, vérifications de compatibilité avec notre durcissement nginx. Instantané conservé entre deux passages :
# une mise à jour de BBB (apt upgrade, bbb-install.sh) apparaît comme une différence au passage suivant.
# Utilisé par nginx-hardening.sh (--before au début, --after à la fin) et par web-monitor.py --summary (fonction resume).
#
#
# Usage (normalement appele par les programmes de la suite) :
#   python3 apps/_bbb.py --before            etat + ce qui a change depuis le dernier instantane (mise a jour de BBB ?)
#   python3 apps/_bbb.py --after [--save]    etat + verifications + ce que ce passage a change ; --save : instantane
#   python3 apps/_bbb.py --summary           etat + verifications + changements depuis l'instantane (rien d'ecrit)
#   python3 apps/_bbb.py --version

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import sys

__version__ = "1.3.20261019.150215"

ETC_BBB = os.environ.get("NGINX_TOOLS_BBB_ETC", "/etc/bigbluebutton")
NGINX_BBB = os.environ.get("NGINX_HARDENING_BBB_NGINX_DIR", os.path.join(ETC_BBB, "nginx"))
ETC_NGINX = os.environ.get("NGINX_TOOLS_NGINX_ETC", "/etc/nginx")
HAPROXY_CFG = os.environ.get("NGINX_TOOLS_HAPROXY_CFG", "/etc/haproxy/haproxy.cfg")
ETC_FAIL2BAN = os.environ.get("NGINX_TOOLS_FAIL2BAN_ETC", "/etc/fail2ban")
LOGROTATE = os.environ.get("NGINX_HARDENING_LOGROTATE_DIR", "/etc/logrotate.d")
PROPRIETES_DEFAUT = os.environ.get("NGINX_TOOLS_BBB_PROPERTIES", "/usr/share/bbb-web/WEB-INF/classes/bigbluebutton.properties")
ETAT = os.environ.get("NGINX_TOOLS_BBB_STATE", "/var/lib/nginx-tools/bbb-state.json")
REGLES = os.path.join(NGINX_BBB, "zz-nginx-hardening-security.nginx")
PORT = int(os.environ.get("NGINX_TOOLS_BBB_PORT", "443"))     # tests : port sans service
UA = "Mozilla/5.0 (verification de BigBlueButton) app-health-check/bbb"      # exclu des chiffres de web-monitor.py
PAQUETS_CLES = ["bigbluebutton", "bbb-html5", "bbb-web", "bbb-config", "bbb-webrtc-sfu", "bbb-freeswitch-core",
                "bbb-apps-akka", "bbb-playback", "nginx", "haproxy"]
HSTS_RE = re.compile(r"(?m)^\s*http-after-response\s+set-header\s+Strict-Transport-Security\b")


VERBOSE = False     # --verbose : chaque commande externe est affichee avant son execution


def lancer(cmd, timeout=60):
    """(code, sortie) ; commande absente ou trop longue : (127, "")."""
    if VERBOSE:
        print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           timeout=timeout, universal_newlines=True, errors="replace")
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def empreinte(chemin):
    try:
        with open(chemin, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except OSError:
        return None


def lire(chemin):
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# ------------------------------------------------------------------------------------------------------------------
# Relevé de l'état
# ------------------------------------------------------------------------------------------------------------------
def fichiers_bbb():
    """Fichiers de configuration gérés par BBB (paquets ou bbb-install.sh) : jamais modifiés par nos outils."""
    liste = [os.path.join(ETC_NGINX, "sites-available", "bigbluebutton"), HAPROXY_CFG,
             os.path.join(ETC_BBB, "bbb-web.properties"), os.path.join(ETC_BBB, "bbb-html5.yml"),
             os.path.join(ETC_BBB, "bbb-conf", "apply-config.sh"), PROPRIETES_DEFAUT]
    liste += [f for f in sorted(glob.glob(os.path.join(NGINX_BBB, "*.nginx"))) if f != REGLES]
    return [f for f in liste if os.path.isfile(f)]


def fichiers_nous():
    """Nos fichiers sur un serveur BBB (nginx-hardening.sh --update)."""
    return [REGLES, os.path.join(ETC_FAIL2BAN, "jail.d", "nginx-blocked-probes.conf"),
            os.path.join(ETC_FAIL2BAN, "filter.d", "nginx-blocked-probes.conf"),
            os.path.join(ETC_FAIL2BAN, "jail.d", "zz-nginx-hardening-ignoreip.local"), os.path.join(LOGROTATE, "nginx")]


def proprietaires(chemins):
    """Paquet propriétaire de chaque fichier (dpkg -S) ; absent = fichier qu'aucune mise à jour de paquet n'écrase."""
    if not chemins:
        return {}
    _, out = lancer(["dpkg", "-S"] + list(chemins), timeout=30)
    res = {}
    for ligne in out.splitlines():
        m = re.match(r"^([^:]+(?::[a-z0-9]+)?(?:, [^:]+)*): (/.+)$", ligne)
        if m:
            res[m.group(2)] = m.group(1)
    return res


def releve():
    """État courant : dict sérialisable (instantané)."""
    _, out = lancer(["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${db:Status-Abbrev}\n"], timeout=60)
    paquets = {}
    for ligne in out.splitlines():
        p = ligne.split("\t")
        if len(p) >= 3 and p[2].startswith("ii") and (p[0].startswith("bbb-") or p[0] in PAQUETS_CLES):
            paquets[p[0]] = p[1]
    release = re.search(r"BIGBLUEBUTTON_RELEASE=(\S+)", lire(os.path.join(ETC_BBB, "bigbluebutton-release")))
    _, docker = lancer(["docker", "ps", "--format", "{{.Image}}"], timeout=20)
    greenlight = sorted({i for i in docker.split() if "greenlight" in i})
    surveilles = fichiers_bbb() + fichiers_nous()
    return {"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "outil": __version__,
            "release": release.group(1) if release else None, "paquets": paquets, "greenlight": greenlight,
            "fichiers_bbb": {f: empreinte(f) for f in fichiers_bbb()},
            "fichiers_nous": {f: empreinte(f) for f in fichiers_nous()},
            "proprietaires": proprietaires([f for f in surveilles if os.path.isfile(f)]),
            "hsts_haproxy": bool(HSTS_RE.search(lire(HAPROXY_CFG))) if os.path.isfile(HAPROXY_CFG) else None}


def charger(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


ETAT_PAR_DEFAUT = "/var/lib/nginx-tools/bbb-state.json"


def ecriture_interdite(chemin):
    """Pendant la suite de tests (NGINX_TOOLS_TESTS), le VRAI instantané du serveur ne doit jamais être écrit : une ancienne
    suite, qui ne redirigeait pas NGINX_TOOLS_BBB_STATE, l'avait rempli de chemins temporaires (« notre fichier … a DISPARU »)."""
    return bool(os.environ.get("NGINX_TOOLS_TESTS")) and os.path.dirname(chemin) == os.path.dirname(ETAT_PAR_DEFAUT)


def enregistrer(chemin, etat):
    """Écriture atomique ; dossier créé au besoin. False si impossible (sans root, par exemple, ou sous les tests)."""
    if ecriture_interdite(chemin):
        return False
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        tmp = chemin + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(etat, f, indent=1, sort_keys=True)
        os.replace(tmp, chemin)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------------------------------------------------------
# Vérifications de compatibilité (nos règles ↔ BBB)
# ------------------------------------------------------------------------------------------------------------------
def nom_serveur():
    """Nom public de BBB : bigbluebutton.web.serverURL (surcharge de /etc/bigbluebutton, puis valeur par défaut)."""
    for f in (os.path.join(ETC_BBB, "bbb-web.properties"), PROPRIETES_DEFAUT):
        m = re.search(r"(?m)^\s*bigbluebutton\.web\.serverURL\s*=\s*https?://([^/\s:]+)", lire(f))
        if m:
            return m.group(1)
    return socket.getfqdn()


def get(chemin, nom, timeout=8):
    """GET https://127.0.0.1:443 (HAProxy ou nginx de BBB) avec SNI et Host du site : (statut, corps) ou None."""
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout) as brut:
            with ctx.wrap_socket(brut, server_hostname=nom) as s:
                s.sendall(f"GET {chemin} HTTP/1.1\r\nHost: {nom}\r\nUser-Agent: {UA}\r\nConnection: close\r\n\r\n".encode())
                donnees = b""
                while len(donnees) < 2000000:
                    bloc = s.recv(65536)
                    if not bloc:
                        break
                    donnees += bloc
    except (OSError, ssl.SSLError):
        return None
    tete, _, corps = donnees.partition(b"\r\n\r\n")
    m = re.match(rb"HTTP/\d(?:\.\d)? (\d{3})", tete)
    return (int(m.group(1)), corps) if m else None


def verifier(etat, avec_bbb_conf=True):
    """Lignes « [OK] / [ATTN] / [FAIL] … » (format lu par nginx-hardening.sh) et problèmes (pour web-monitor.py)."""
    lignes, problemes = [], []
    def ok(t): lignes.append("[OK] " + t)
    def attn(t, comment=""):
        lignes.append("[ATTN] " + t)
        problemes.append((2, t, comment))
    def echec(t, comment=""):
        lignes.append("[FAIL] " + t)
        problemes.append((1, t, comment))
    texte_T = lancer(["nginx", "-T"], timeout=30)[1]
    if not os.path.isfile(REGLES):
        echec(f"nos règles de sécurité sont absentes ({REGLES})", "nginx-hardening.sh --update les installe")
    else:
        proprio = etat["proprietaires"].get(REGLES)
        if proprio:
            attn(f"{REGLES} appartient au paquet {proprio} : une mise à jour de ce paquet l'écraserait")
        else:
            ok(f"nos règles ({os.path.basename(REGLES)}) n'appartiennent à aucun paquet : aucune mise à jour de BBB ne les écrase")
        if texte_T.strip() and f"# configuration file {REGLES}:" not in texte_T:
            echec("nos règles ne sont pas chargées par nginx (absentes de nginx -T) : la configuration de BBB n'inclut "
                  "plus /etc/bigbluebutton/nginx/*.nginx", "examiner le bloc server de BBB après sa mise à jour")
        elif texte_T.strip():
            ok("nos règles sont chargées par nginx (incluses par le bloc server de BBB)")
    code_t, sortie_t = lancer(["nginx", "-t"], timeout=30)
    if code_t == 0:
        ok("nginx -t : configuration valide")
    elif code_t != 127:
        echec("nginx -t refuse la configuration : " + " | ".join(l.strip() for l in sortie_t.splitlines()[-2:]),
              "ne pas recharger nginx avant correction")
    if etat["hsts_haproxy"] is True:
        ok("HSTS présent dans HAProxy (http-after-response)")
    elif etat["hsts_haproxy"] is False:
        attn("HSTS absent de HAProxy (http-after-response) — bbb-install.sh régénère haproxy.cfg à chaque passage",
             "nginx-hardening.sh --check indique la ligne à remettre dans la section « frontend » du 443")
    nom = nom_serveur()
    essais = [("/bigbluebutton/api", "API"), ("/html5client/", "client HTML5"), ("/", "accueil (Greenlight)")]
    for chemin, libelle in essais:
        r = get(chemin, nom)
        if r is None:
            lignes.append(f"       {libelle} ({chemin}) : essai impossible (rien n'écoute sur 127.0.0.1:443 ?)")
            continue
        statut, corps = r
        if chemin == "/bigbluebutton/api":
            if statut == 200 and b"SUCCESS" in corps:
                ok(f"{libelle} de BBB répond (https://{nom}{chemin} → 200 SUCCESS)")
            else:
                echec(f"{libelle} de BBB : https://{nom}{chemin} → {statut} (attendu 200 SUCCESS)",
                      "vérifier bbb-conf --status ; si 404, une règle de sécurité capte l'URL")
        elif statut == 404 and len(corps) < 2048:
            echec(f"{libelle} : https://{nom}{chemin} → 404 minimal (refus de nginx : nos règles captent-elles cette URL ?)",
                  "comparer avec blocked-probes.log")
        elif statut >= 500:
            echec(f"{libelle} : https://{nom}{chemin} → {statut}", "bbb-conf --status")
        else:
            ok(f"{libelle} : https://{nom}{chemin} → {statut}")
    if avec_bbb_conf:
        code, out = lancer(["bbb-conf", "--check"], timeout=180)
        if code == 127 and not out:
            lignes.append("       bbb-conf --check : indisponible")
        else:
            bloc = out.split("# Potential problems", 1)
            if len(bloc) == 2:
                pbs = [l.strip() for l in bloc[1].splitlines()[1:] if l.strip() and not set(l.strip()) <= {"#", "-", "="}]
                attn(f"bbb-conf --check signale {len(pbs)} problème(s) potentiel(s) : " + " | ".join(pbs[:4])
                     + (" …" if len(pbs) > 4 else ""), "voir bbb-conf --check")
            else:
                ok("bbb-conf --check : aucun problème potentiel signalé")
    return lignes, problemes


# ------------------------------------------------------------------------------------------------------------------
# Affichage et comparaison
# ------------------------------------------------------------------------------------------------------------------
def lignes_etat(etat):
    p = etat["paquets"]
    autres = sorted(set(p) - set(PAQUETS_CLES))
    r = [f"       BigBlueButton {etat['release'] or '(version inconnue : bigbluebutton-release absent)'}"
         + (f" — Greenlight : {', '.join(etat['greenlight'])}" if etat["greenlight"] else "")]
    cles = [f"{n} {p[n]}" for n in PAQUETS_CLES if n in p]
    for i in range(0, len(cles), 3):
        r.append("       " + " · ".join(cles[i:i + 3]))
    if autres:
        r.append(f"       et {len(autres)} autre(s) paquet(s) bbb-* (détail : dpkg -l 'bbb-*')")
    modifies = [f for f, h in etat["fichiers_bbb"].items() if h and f in etat["proprietaires"]]
    r.append(f"       Configuration de BBB surveillée : {len(etat['fichiers_bbb'])} fichier(s)"
             + (f", dont {len(modifies)} livré(s) par un paquet" if modifies else "")
             + f" ; nos fichiers : {sum(1 for h in etat['fichiers_nous'].values() if h)}/{len(etat['fichiers_nous'])} présents")
    return r


def differences(ancien, nouveau, quoi):
    """Lignes décrivant ce qui a changé entre deux instantanés ; vide si rien."""
    r = []
    if ancien.get("release") != nouveau.get("release"):
        r.append(f"[ATTN] BigBlueButton {ancien.get('release')} → {nouveau.get('release')} ({quoi})")
    pa, pn = ancien.get("paquets", {}), nouveau.get("paquets", {})
    changes = [f"{n} {pa.get(n, '—')} → {pn.get(n, '—')}" for n in sorted(set(pa) | set(pn)) if pa.get(n) != pn.get(n)]
    if changes:
        r.append(f"       {len(changes)} paquet(s) changé(s) ({quoi}) : " + " ; ".join(changes[:6])
                 + (f" … (+{len(changes) - 6})" if len(changes) > 6 else ""))
    if ancien.get("greenlight") != nouveau.get("greenlight"):
        r.append(f"       Greenlight : {', '.join(ancien.get('greenlight') or ['—'])} → {', '.join(nouveau.get('greenlight') or ['—'])}")
    fa, fn = ancien.get("fichiers_bbb", {}), nouveau.get("fichiers_bbb", {})
    mod = [os.path.basename(f) if f != HAPROXY_CFG else "haproxy.cfg" for f in sorted(set(fa) | set(fn)) if fa.get(f) != fn.get(f)]
    if mod:
        r.append(f"       configuration de BBB modifiée ({quoi}) : " + ", ".join(mod))
    na, nn = ancien.get("fichiers_nous", {}), nouveau.get("fichiers_nous", {})
    for f in sorted(set(na) | set(nn)):
        if na.get(f) and not nn.get(f):
            r.append(f"[FAIL] notre fichier {f} a DISPARU ({quoi})")
        elif na.get(f) != nn.get(f):
            r.append(f"       notre fichier {os.path.basename(f)} : {'créé' if not na.get(f) else 'modifié'} ({quoi})")
    if ancien.get("hsts_haproxy") and nouveau.get("hsts_haproxy") is False:
        r.append(f"[FAIL] HSTS retiré de HAProxy ({quoi}) — bbb-install.sh a régénéré haproxy.cfg : remettre la ligne")
    return r


def resume(mode="summary", sauver=False):
    """mode before/after/summary : (lignes à afficher, problèmes [(priorité, constat, comment)]). Rien n'est affiché."""
    etat = releve()
    lignes, problemes = lignes_etat(etat), []
    precedent = charger(ETAT)
    ignore = ""
    if precedent and set(precedent.get("fichiers_nous", {})) != set(etat["fichiers_nous"]):
        # Instantané écrit pour d'AUTRES emplacements (tests, ancienne installation) : sans valeur, jamais une « disparition ».
        ignore = (f"       Instantané du {precedent.get('date')} ignoré : il décrit d'autres emplacements de fichiers "
                  "(écrit par une exécution de test ou une ancienne installation) — il sera remplacé par le prochain --update")
        precedent = None
    if mode == "before":
        if precedent:
            diff = differences(precedent, etat, f"depuis le passage du {precedent.get('date')}")
            lignes += diff or [f"[OK] rien n'a changé depuis le passage du {precedent.get('date')} (versions et configuration)"]
        else:
            lignes.append(ignore or "       Premier relevé : aucun instantané précédent (il sera écrit à la fin de --update)")
        enregistrer(ETAT + ".before", etat)
    else:
        verif, problemes = verifier(etat, avec_bbb_conf=True)
        lignes += verif
        if mode == "after":
            avant = charger(ETAT + ".before")
            if avant:
                diff = differences(avant, etat, "par ce passage")
                lignes += diff or ["       ce passage n'a modifié ni BBB ni nos fichiers"]
            if sauver:
                lignes.append(f"       Instantané écrit : {ETAT}" if enregistrer(ETAT, etat)
                              else f"[ATTN] instantané non écrit ({ETAT} : droits ?)")
        elif precedent:
            diff = differences(precedent, etat, f"depuis le dernier --update ({precedent.get('date')})")
            lignes += diff
            for l in diff:
                if l.startswith("[FAIL]"):
                    problemes.append((1, l[7:], "nginx-hardening.sh --update"))
            if any("BigBlueButton" in l and "→" in l for l in diff) or any("paquet(s) changé(s)" in l for l in diff):
                problemes.append((2, "BigBlueButton a été mis à jour depuis le dernier nginx-hardening.sh --update",
                                  "nginx-hardening.sh --update (vérifie et réapplique nos règles, puis enregistre l'état), "
                                  "puis une réunion de test"))
        else:
            lignes.append(ignore or "       Aucun instantané : nginx-hardening.sh --update en écrira un (référence pour la prochaine mise à jour de BBB)")
    return lignes, problemes


def main():
    p = argparse.ArgumentParser(description="État de BigBlueButton et compatibilité avec le durcissement nginx.")
    p.add_argument("--after", action="store_true", help="État, vérifications et changements faits par ce passage")
    p.add_argument("--before", action="store_true", help="État et changements depuis le dernier instantané")
    p.add_argument("--save", action="store_true", help="Avec --after : écrire l'instantané")
    p.add_argument("--summary", action="store_true", help="État, vérifications et changements depuis l'instantané")
    p.add_argument("-v", "--verbose", action="store_true", help="Affiche chaque commande externe exécutée")
    p.add_argument("--version", action="version", version=f"_bbb.py version {__version__}")
    a = p.parse_args()
    global VERBOSE
    VERBOSE = a.verbose
    mode = "before" if a.before else "after" if a.after else "summary"
    lignes, _ = resume(mode, sauver=a.save)
    for ligne in lignes:
        print(ligne)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)
