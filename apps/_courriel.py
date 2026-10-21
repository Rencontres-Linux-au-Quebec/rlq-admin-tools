#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Envoi de courriels commun aux programmes Python et Bash (relais SMTP, STARTTLS), configuré une seule fois par le programme de setup.

Configuration lue dans l'ordre (le dernier fichier lu l'emporte) : /etc/default/nginx-tools-mail.conf, puis ~/.nginx-tools-mail.conf.
Le MOT DE PASSE n'est JAMAIS dans ce fichier : il est dans un fichier à part (MAIL_PASSWORD_FILE, mode 0600, propriétaire root),
ou dans la variable d'environnement NGINX_TOOLS_MAIL_PASSWORD. Il n'est jamais affiché, ni journalisé, ni mis dans un courriel.

Clés : MAIL_HOST, MAIL_PORT (587), MAIL_SECURITY (starttls | ssl | none), MAIL_USER, MAIL_FROM, MAIL_TO, MAIL_PASSWORD_FILE,
MAIL_ATTACH_MAX_MB (100 : une pièce jointe plus grosse est remplacée par un LIEN), MAIL_LINK_DIR, MAIL_LINK_URL, MAIL_LINK_DAYS (30).

Utilisation depuis Python : from _courriel import envoyer ; depuis Bash : python3 apps/_courriel.py --send "Sujet" --body-file corps.txt [--attach fichier]

HISTORIQUE (résumé ; détail : doc/_courriel.changelog.txt)
#   1.3.20261020.211944 — Personal configuration file ~/.NAME.conf (not .cfg); a legacy ~/.NAME.cfg is renamed automatically.
#   1.2.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.1.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.0.20261013.103000 — Première version : envoi SMTP commun, pièces jointes de plus de 100 Mo remplacées par un lien, mot de passe à part.
"""
import argparse
import os
import re
import secrets
import shutil
import smtplib
import socket
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

__version__ = "1.3.20261020.211944"

CONFIG_SYSTEME = "/etc/default/nginx-tools-mail.conf"
CONFIG_UTILISATEUR = "~/.nginx-tools-mail.conf"
MOT_DE_PASSE_DEFAUT = "/etc/default/nginx-tools-mail.pass"
DOSSIER_LIENS_DEFAUT = "/var/lib/nginx-tools/pieces-jointes"
CLES = ("MAIL_HOST", "MAIL_PORT", "MAIL_SECURITY", "MAIL_USER", "MAIL_FROM", "MAIL_TO", "MAIL_PASSWORD_FILE",
        "MAIL_ATTACH_MAX_MB", "MAIL_LINK_DIR", "MAIL_LINK_URL", "MAIL_LINK_DAYS")
LIGNE_RE = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$')


class ErreurCourriel(Exception):
    """Configuration incomplète ou envoi impossible (message lisible, sans secret)."""


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


def fichiers_config():
    return [os.environ.get("NGINX_TOOLS_MAIL_CONF") or CONFIG_SYSTEME, _personnel(os.path.expanduser(CONFIG_UTILISATEUR))]


def lire_config(fichiers=None):
    """Dictionnaire des clés MAIL_* (valeurs sans guillemets). Fichier absent ou illisible : ignoré."""
    cfg = {}
    for chemin in (fichiers if fichiers is not None else fichiers_config()):
        try:
            with open(chemin, encoding="utf-8") as f:
                lignes = f.read().splitlines()
        except OSError:
            continue
        for ligne in lignes:
            if ligne.lstrip().startswith("#"):
                continue
            m = LIGNE_RE.match(ligne)
            if m and m.group(1) in CLES:
                valeur = m.group(2)
                if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                    valeur = valeur[1:-1]
                else:
                    valeur = valeur.split(" #")[0].strip()
                cfg[m.group(1)] = valeur
    return cfg


def lire_mot_de_passe(cfg):
    """Mot de passe : variable NGINX_TOOLS_MAIL_PASSWORD, sinon contenu du fichier MAIL_PASSWORD_FILE. Chaîne vide s'il n'y en a pas."""
    if os.environ.get("NGINX_TOOLS_MAIL_PASSWORD"):
        return os.environ["NGINX_TOOLS_MAIL_PASSWORD"]
    try:
        with open(cfg.get("MAIL_PASSWORD_FILE") or MOT_DE_PASSE_DEFAUT, encoding="utf-8") as f:
            return f.read().strip("\r\n")
    except OSError:
        return ""


def securite(cfg):
    mode = (cfg.get("MAIL_SECURITY") or "").strip().lower()
    if mode in ("starttls", "ssl", "none"):
        return mode
    return "ssl" if str(cfg.get("MAIL_PORT")) == "465" else "starttls"


def verifier_droits(chemin):
    """Problèmes de droits du fichier de mot de passe (liste de textes ; vide = correct)."""
    try:
        st = os.stat(chemin)
    except OSError:
        return [f"{chemin} introuvable"]
    problemes = []
    if st.st_mode & 0o077:
        problemes.append(f"{chemin} est lisible par d'autres utilisateurs (mode {st.st_mode & 0o777:o}) : chmod 600")
    if hasattr(os, "geteuid") and os.geteuid() == 0 and st.st_uid != 0:
        problemes.append(f"{chemin} n'appartient pas à root : chown root:root")
    return problemes


def nettoyer_liens(dossier, jours):
    """Supprime les dossiers de pièces jointes (liens) plus vieux que `jours` jours."""
    limite = time.time() - jours * 86400
    try:
        for nom in os.listdir(dossier):
            chemin = os.path.join(dossier, nom)
            if os.path.isdir(chemin) and os.path.getmtime(chemin) < limite:
                shutil.rmtree(chemin, ignore_errors=True)
    except OSError:
        pass


def pieces_ou_liens(cfg, pieces):
    """(pièces à joindre, lignes de texte avec les liens). Une pièce plus grosse que MAIL_ATTACH_MAX_MB est copiée dans MAIL_LINK_DIR/<jeton>/
    et remplacée par un lien (MAIL_LINK_URL/<jeton>/<nom>) ; sans MAIL_LINK_URL, le texte donne le chemin sur le serveur."""
    maximum = int(float(cfg.get("MAIL_ATTACH_MAX_MB") or 100) * 1024 * 1024)
    joindre, liens = [], []
    for chemin in pieces:
        if os.path.getsize(chemin) <= maximum:
            joindre.append(chemin)
            continue
        dossier = cfg.get("MAIL_LINK_DIR") or DOSSIER_LIENS_DEFAUT
        nettoyer_liens(dossier, int(cfg.get("MAIL_LINK_DAYS") or 30))
        jeton = secrets.token_urlsafe(24)                       # adresse impossible à deviner : seul le destinataire du courriel la connaît
        cible = os.path.join(dossier, jeton)
        os.makedirs(cible, mode=0o755, exist_ok=True)
        nom = os.path.basename(chemin)
        shutil.copy2(chemin, os.path.join(cible, nom))
        base = (cfg.get("MAIL_LINK_URL") or "").rstrip("/")
        taille = os.path.getsize(chemin) / 1024 / 1024
        liens.append(f"{nom} ({taille:.0f} Mo" if taille >= 10 else f"{nom} ({taille:.1f} Mo")
        liens[-1] += ") : " + (f"{base}/{jeton}/{nom}" if base else f"trop gros pour le courriel, copié sur le serveur : {os.path.join(cible, nom)}")
    return joindre, liens


def envoyer(sujet, corps, destinataires=None, pieces=(), cfg=None):
    """Envoie un courriel par le relais SMTP configuré. Lève ErreurCourriel (message sans secret)."""
    cfg = cfg if cfg is not None else lire_config()
    if not cfg.get("MAIL_HOST"):
        raise ErreurCourriel("courriel non configuré (MAIL_HOST absent) : lancer nginx-hardening.sh --update --mail-setup")
    a = destinataires or cfg.get("MAIL_TO")
    if not a:
        raise ErreurCourriel("aucun destinataire (MAIL_TO absent)")
    expediteur = cfg.get("MAIL_FROM") or cfg.get("MAIL_USER") or f"nginx-tools@{socket.getfqdn()}"
    joindre, liens = pieces_ou_liens(cfg, pieces)
    if liens:
        corps = corps.rstrip("\n") + "\n\nPièces jointes trop grosses, remplacées par un lien :\n" + "\n".join("  " + l for l in liens) + "\n"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = sujet, expediteur, a if isinstance(a, str) else ", ".join(a)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=expediteur.split("@")[-1].strip("> "))
    msg.set_content(corps)
    for chemin in joindre:
        with open(chemin, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="octet-stream", filename=os.path.basename(chemin))
    mode, port = securite(cfg), int(cfg.get("MAIL_PORT") or 587)
    try:
        classe = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
        kw = {"context": ssl.create_default_context()} if mode == "ssl" else {}
        with classe(cfg["MAIL_HOST"], port, timeout=20, **kw) as serveur:
            if mode == "starttls":
                serveur.starttls(context=ssl.create_default_context())
            if cfg.get("MAIL_USER"):
                serveur.login(cfg["MAIL_USER"], lire_mot_de_passe(cfg))
            serveur.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise ErreurCourriel("identification refusée par le relais (MAIL_USER ou mot de passe)")
    except smtplib.SMTPRecipientsRefused:
        raise ErreurCourriel("destinataire refusé par le relais")
    except smtplib.SMTPSenderRefused:
        raise ErreurCourriel("expéditeur refusé par le relais (MAIL_FROM doit être une adresse autorisée)")
    except (ssl.SSLError, smtplib.SMTPNotSupportedError) as e:
        raise ErreurCourriel(f"négociation TLS impossible ({e}) : vérifier MAIL_PORT et MAIL_SECURITY")
    except (OSError, smtplib.SMTPException) as e:
        raise ErreurCourriel(f"envoi impossible : {e}")


def afficher_config(cfg):
    """Configuration lisible SANS le mot de passe (seulement s'il existe et si ses droits sont corrects)."""
    for cle in CLES:
        print(f"{cle}={cfg.get(cle, '')}")
    mdp = cfg.get("MAIL_PASSWORD_FILE") or MOT_DE_PASSE_DEFAUT
    print(f"mot de passe : {'présent' if lire_mot_de_passe(cfg) else 'absent'} ({mdp}) ; droits : " + ("corrects" if not verifier_droits(mdp) else "; ".join(verifier_droits(mdp))))


def principal(argv=None):
    p = argparse.ArgumentParser(description="Envoi de courriels (relais SMTP configuré par le programme de setup).")
    p.add_argument("--attach", action="append", default=[], metavar="FICHIER", help="Pièce jointe (répétable) ; plus grosse que MAIL_ATTACH_MAX_MB : remplacée par un lien")
    p.add_argument("--body-file", metavar="FICHIER", help="Corps du message (défaut : l'entrée standard)")
    p.add_argument("--changelog", action="store_true", help="Affiche le journal des modifications")
    p.add_argument("--send", metavar="SUJET", help="Envoie un courriel avec ce sujet")
    p.add_argument("--show-config", action="store_true", help="Affiche la configuration (jamais le mot de passe) et vérifie les droits")
    p.add_argument("--test", action="store_true", help="Envoie un courriel de test au destinataire configuré")
    p.add_argument("--to", metavar="ADRESSE", help="Destinataire (défaut : MAIL_TO)")
    p.add_argument("--version", action="store_true", help="Affiche la version")
    a = p.parse_args(argv)
    if a.version:
        print(f"_courriel.py version {__version__}")
        return 0
    if a.changelog:
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "doc", "_courriel.changelog.txt")
        try:
            with open(chemin, encoding="utf-8") as f:
                sys.stdout.write(f.read())
        except OSError:
            print("journal introuvable : " + chemin, file=sys.stderr)
            return 1
        return 0
    cfg = lire_config()
    if a.show_config:
        afficher_config(cfg)
        return 0
    if not (a.send or a.test):
        p.print_usage(sys.stderr)
        return 2
    sujet = a.send or f"Test de courriel de {socket.getfqdn()}"
    corps = "Courriel de test des outils nginx-tools : si vous le lisez, l'envoi fonctionne.\n" if a.test else (
        open(a.body_file, encoding="utf-8").read() if a.body_file else sys.stdin.read())
    try:
        envoyer(sujet, corps, a.to, a.attach, cfg)
    except (ErreurCourriel, OSError) as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        return 1
    print("Courriel envoyé.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
