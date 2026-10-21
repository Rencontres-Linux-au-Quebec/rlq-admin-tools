#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _anonymiser.py — anonymise ce qu'affichent les programmes (option --anonymize) : pseudonymes STABLES (module partagé, apps/).
#
# HISTORIQUE DE VERSION (résumé — voir doc/_anonymiser.changelog.txt pour le détail complet) :
#   1.3.20261020.203430 — Names of people registered by a program (names=, names_lock=) replaced by « membre-4f2a9c » (stable, per account), column padding kept; NGINX_TOOLS_ANON_SELF: no relaunch.
#   1.2.20261020.103939 — Masked e-mails (« b****ss@exemple.org ») replaced whole; fixed_width: IP pseudonyms padded to the width of the address (aligned columns).
#   1.1.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.0.20261015.143436 — Création : adresses IP (v4, v6), courriels, identifiants (login, user), jetons / mots de passe / cookies, paramètres d'URL ; filtre de lignes ; sel secret par machine.
"""Remplace, dans le texte affiché, les données qui identifient quelqu'un par des PSEUDONYMES STABLES : une même valeur donne toujours le même pseudonyme (on suit « la même
personne » d'un rapport à l'autre sans pouvoir l'identifier). Le pseudonyme est un HMAC-SHA256 de la valeur avec un SEL SECRET propre à la machine (jamais affiché) : sans le sel,
on ne peut ni retrouver la valeur ni vérifier une hypothèse ; avec la machine, `_anonymiser.py --pseudonyme VALEUR` dit quel pseudonyme correspond à une valeur connue.
1.3 : les NOMS de personnes qu'un programme connaît (app-log-live.py : personnes connectées au site, étiquettes de l'équipe) lui sont confiés (names=) et deviennent
« membre-4f2a9c » (même pseudonyme pour le nom complet, le nom court et l'identifiant d'un même compte) ; le remplissage d'une colonne qui suit le nom est ajusté.

Remplacements :
  adresse IP (v4, v6)                  -> IP-4f2a9c           (jamais 127.x, ::1, 0.0.0.0, 255.x : masques et boucle locale ; ni les versions « 18.0.1.3 »)
  courriel (aussi %40 dans une URL)    -> usager-9c1e03@anonyme.invalid
  --login X, login=X, user=X, email=X, name=X (dans une URL) -> ID-3b7d11 / usager-…
  token=, password=, secret=, api_key=, session_id=, Authorization: Bearer …, Cookie: … -> ***
Sel : variable NGINX_TOOLS_ANON_SEL, sinon /etc/default/nginx-tools-anon.salt, sinon ~/.nginx-tools-anon.salt (créé en droits 600 au premier usage ; le supprimer change tous les
pseudonymes). Limite : seuls les motifs ci-dessus sont reconnus (un nom de personne écrit en clair dans un texte libre ne l'est pas).
Filtre en ligne de commande : `commande | _anonymiser.py` ; `_anonymiser.py --pseudonyme 203.0.113.9`."""
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import sys
import threading
import unicodedata

__version__ = "1.3.20261020.203430"
SEL_ENV = "NGINX_TOOLS_ANON_SEL"
ACTIF_ENV = "NGINX_TOOLS_ANON_ACTIF"          # posé pour tout ce qui est lancé derrière le filtre : rien n'est filtré deux fois
SOI_ENV = "NGINX_TOOLS_ANON_SELF"             # 1.3: posé par un programme qui anonymise lui-même son affichage (app-log-live.py) : jamais relancé derrière le filtre
DEMANDE_ENV = "NGINX_TOOLS_ANONYMIZE"          # 1 : anonymiser (même sans terminal, ex. cron) ; 0 : ne jamais le faire d'après la configuration
DOMAINE_ANONYME = "anonyme.invalid"
OUI = ("1", "oui", "yes", "true", "on", "vrai", "o", "y")
ANSI_CODES = r"(?:\x1b\[[0-9;]*m)*"               # 1.3: color codes allowed between a name and the padding spaces of its column


def _largeur(texte):
    """Columns taken on a terminal: a wide East Asian character takes 2, a combining mark 0 (names in a padded column stay aligned)."""
    if texte.isascii():
        return len(texte)
    return sum(0 if unicodedata.combining(c) or unicodedata.category(c) in ("Mn", "Me", "Cf") else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in texte)

IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\w|\.\d)")
H = r"[0-9A-Fa-f]{1,4}"
IPV6 = re.compile(rf"(?<![\w:.])(?:(?:{H}:){{7}}{H}|(?:{H}:){{1,7}}:(?:{H}(?::{H}){{0,6}})?|::{H}(?::{H}){{0,6}})(?![\w:.])")
COURRIEL = re.compile(r"[A-Za-z0-9._+*-]+(?:@|%40)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
SECRET = re.compile(r"(?i)(?<![\w-])((?:[\w-]*(?:token|secret|passw(?:or)?d|pwd|api[_-]?key|apikey|session[_-]?id|signature|authorization))[\"']?\s*[=:]\s*(?:(?:Bearer|Basic)\s+)?)"
                    r"(\"[^\"]*\"|'[^']*'|[^\s&;,\"')]+)")
COOKIE = re.compile(r"(?im)\b(cookie:\s*)(.+)$")
IDENT_EGAL = re.compile(r"(?i)(?<![\w-])((?:bot_)?(?:login|username|user|email|e-mail|courriel|usager)=)([^\s&;,\"')]+)")
IDENT_URL = re.compile(r"(?i)([?&;](?:name|partner_name|phone|mobile)=)([^&\s\"']+)")
IDENT_OPTION = re.compile(r"(?i)(?<![\w-])(--(?:bot-)?login\s+)([^\s&;,\"')]+)")


def _lire_sel():
    """Sel secret de la machine (créé au premier usage, droits 600) ; None si rien n'est lisible ni inscriptible (sel éphémère alors)."""
    valeur = os.environ.get(SEL_ENV, "")
    if valeur:
        return valeur.encode()
    etc = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT") or "/etc/default", "nginx-tools-anon.salt")
    perso = os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".nginx-tools-anon.salt")
    for chemin in (etc, perso):
        try:
            with open(chemin, "rb") as f:
                contenu = f.read().strip()
            if contenu:
                return contenu
        except OSError:
            continue
    nouveau = secrets.token_hex(32).encode()
    for chemin in (etc, perso):
        try:
            fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(nouveau + b"\n")
        return nouveau
    return nouveau                                 # ni /etc ni le dossier personnel inscriptibles : sel éphémère (pseudonymes valables pour cette exécution seulement)


class Anonymiseur:
    """Callable : Anonymiseur()(texte) -> texte anonymisé. Un même sel donne les mêmes pseudonymes d'une exécution à l'autre."""

    def __init__(self, sel=None, fixed_width=False, names=None, names_lock=None):
        self.sel = sel if sel is not None else _lire_sel()
        self.cache = {}
        self.fixed_width = fixed_width             # 1.2: « IP-4f2a9c » padded with spaces to the width of the address it replaces (columns stay aligned)
        self.names = names if names is not None else {}      # 1.3: {name shown: (prefix, stable key)} — filled by the program, read here
        self.names_lock = names_lock or threading.Lock()
        self._names_re, self._names_n = None, -1

    def add_name(self, name, key=None, prefix="membre"):
        """1.3: `name` (a person's name, a short name, a login) will be shown as « prefix-xxxxxx »; the same `key` (an account) gives the same pseudonym to all its names."""
        name = (name or "").strip()
        if len(name) >= 3:
            with self.names_lock:
                self.names.setdefault(name, (prefix, key or name))

    def _names_pattern(self):
        """Regex of the registered names (longest first), rebuilt only when names were added; None when there is none."""
        with self.names_lock:
            if len(self.names) == self._names_n:
                return self._names_re
            self._names_n = len(self.names)
            keys = sorted((k for k in self.names if len(k) >= 3), key=len, reverse=True)
        self._names_re = (re.compile(r"(^|[^\w@./%-]|\x1b\[[0-9;]*m)(" + "|".join(re.escape(k) for k in keys) + r")(?![\w@/%-])(" + ANSI_CODES + r")( *)")
                          if keys else None)
        return self._names_re

    def _name(self, m):
        before, name, codes, spaces = m.group(1), m.group(2), m.group(3), m.group(4)
        with self.names_lock:
            prefix, key = self.names.get(name, ("membre", name))
        res = f"{prefix}-{self.pseudonyme('name', str(key))}"
        if spaces:                                 # padding of a column: as many columns in all as before (at least one space: never glued to the next column)
            spaces = " " * max(1, _largeur(name) + len(spaces) - len(res))
        elif self.fixed_width and len(res) < _largeur(name) and codes:
            res = res.ljust(_largeur(name))
        return before + res + codes + spaces

    def names_sub(self, texte):
        """1.3: the registered names replaced by their pseudonym; works on COLORED text (a colored name followed by the padding of its column)."""
        pattern = self._names_pattern() if self.names else None
        return pattern.sub(self._name, texte) if pattern is not None and texte else texte

    def pseudonyme(self, genre, valeur):
        cle = (genre, valeur.lower())
        if cle not in self.cache:
            self.cache[cle] = hmac.new(self.sel, f"{genre}:{valeur.lower()}".encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:6]
        return self.cache[cle]

    def _ip(self, m):
        texte = m.group(0)
        try:
            adresse = ipaddress.ip_address(texte)
        except ValueError:
            return texte
        if adresse.is_loopback or adresse.is_unspecified or texte.startswith("255.") or (adresse.version == 4 and re.fullmatch(r"1[5-9]\.0\.\d+\.\d+", texte)):
            return texte                                                  # boucle locale, masque, version « 18.0.1.3 » d'un module Odoo
        res = "IP-" + self.pseudonyme("ip", str(adresse))
        return res.ljust(len(texte)) if self.fixed_width else res

    def _courriel(self, m):
        texte = m.group(0)
        local, _, domaine = texte.replace("%40", "@").rpartition("@")
        if domaine.lower() == DOMAINE_ANONYME:
            return texte
        return f"usager-{self.pseudonyme('mail', local + '@' + domaine)}@{DOMAINE_ANONYME}"

    def _ident(self, m):
        valeur = m.group(2)
        if valeur.startswith(("usager-", "ID-", "IP-", "***")):
            return m.group(0)
        return m.group(1) + "ID-" + self.pseudonyme("ident", valeur)

    def __call__(self, texte):
        if not texte:
            return texte
        texte = self.names_sub(texte)
        texte = COURRIEL.sub(self._courriel, texte)
        texte = SECRET.sub(lambda m: m.group(1) + ("***" if not m.group(2).startswith("***") else m.group(2)), texte)
        texte = COOKIE.sub(lambda m: m.group(1) + "***", texte)
        texte = IDENT_EGAL.sub(self._ident, texte)
        texte = IDENT_URL.sub(self._ident, texte)
        texte = IDENT_OPTION.sub(self._ident, texte)
        texte = IPV4.sub(self._ip, texte)
        return IPV6.sub(self._ip, texte)


def _vrai(valeur):
    return str(valeur or "").strip().lower() in OUI


def demande(argv, config=None, env=None, terminal=None):
    """Faut-il anonymiser cette exécution ? --anonymize (ou son abréviation « --anon… ») ; sinon NGINX_TOOLS_ANONYMIZE (1 : oui, 0 : non) ; sinon la clé ANONYMIZE de la
    configuration, SEULEMENT si la sortie est un terminal (un programme qui en analyse un autre, ou un tube, ne doit pas recevoir un texte déjà modifié). Jamais si le texte est
    déjà filtré par un programme parent (NGINX_TOOLS_ANON_ACTIF) ni pour --help / --version / --changelog."""
    env = os.environ if env is None else env
    if env.get(ACTIF_ENV):
        return False
    if any(a in ("-h", "--help", "--version", "--changelog") for a in argv):
        return False
    if any(a.startswith("--anon") and "--anonymize".startswith(a) for a in argv):
        return True
    explicite = env.get(DEMANDE_ENV, "")
    if explicite:
        return _vrai(explicite)
    if terminal is None:
        terminal = sys.stdout.isatty()
    return bool(terminal and config and _vrai(config.get("ANONYMIZE")))


def sans_option(argv):
    """argv sans --anonymize (pour les programmes bash, qui ne la connaissent pas : le filtre est posé par apps/_traduire.py)."""
    return [a for a in argv if not (a.startswith("--anon") and "--anonymize".startswith(a))]


def relancer_si_demande(argv, config, sortie_terminal=None):
    """Python : relance le programme derrière le filtre de sortie (apps/_traduire.py --anonymiser-seul) quand l'anonymisation est demandée ; ne revient pas dans ce cas.
    Échoue FERMÉ : si le filtre est introuvable, le programme s'arrête plutôt que d'afficher des données en clair."""
    if os.environ.get(SOI_ENV) or not demande(argv, config, terminal=sortie_terminal):
        return
    traducteur = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_traduire.py")
    if not os.path.isfile(traducteur):
        raise SystemExit("ERREUR : anonymisation demandée mais apps/_traduire.py est introuvable : rien n'est affiché.")
    os.execv(sys.executable, [sys.executable, traducteur, "--anonymiser-seul", "--", sys.executable] + sys.argv)


def main(argv):
    if argv[1:2] == ["--version"]:
        print(f"_anonymiser.py version {__version__}")
        return 0
    anonymiseur = Anonymiseur()
    if argv[1:2] == ["--pseudonyme"]:
        for valeur in argv[2:]:
            sortie = anonymiseur(valeur)
            if sortie == valeur:                 # valeur nue (sans motif) : IP ou courriel reconnus d'après leur forme, sinon identifiant
                sortie = "ID-" + anonymiseur.pseudonyme("ident", valeur)
            print(f"{valeur} -> {sortie}")
        return 0
    try:
        for ligne in sys.stdin:
            sys.stdout.write(anonymiseur(ligne))
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
