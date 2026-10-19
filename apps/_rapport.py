#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ========================================================================================================================
# Copyright (C) 2026  Services-Conseils Linux
# Licence : GNU Affero General Public License, version 3 ou ultérieure — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Rapport d'erreurs commun des programmes : option --report-err.

En fin d'exécution, un bloc court à copier-coller : programme et version, commande, serveur (nom, système, utilisateur),
durée et code de sortie, contexte lu dans la sortie (application, fichiers de configuration), versions de toute la suite, puis
les ÉCHECS, AVERTISSEMENTS et RECOMMANDATIONS à traiter avec leurs lignes de détail. Les mots de passe sont masqués.

  - programmes Python : lancer(fonction, programme, version, dossier) — la sortie est copiée au fil de l'eau (couleurs
    conservées dans le terminal) ;
  - programmes Bash : apps/_rapport.sh relance le programme en capturant sa sortie, puis appelle ce fichier en ligne de
    commande (python3 apps/_rapport.py --programme … --sortie FICHIER).

HISTORIQUE (résumé ; détail : doc/_rapport.changelog.txt)
#   1.11.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.10.20261013.103000 — apps/_courriel.py dans la ligne « Suite ».
#   1.9.20261008.120306 — _rapport.sh : REPORT_ERR_COULEUR (couleurs conservees avec --report-err).
#   1.8.20261007.175327 — odoo-mail-retry.py dans la ligne « Suite ».
#   1.7.20261007.171721 — apps/_cache_ip.py dans la ligne « Suite ».
#   1.6.20261007.093208 — apps/_listes.py dans la ligne « Suite ».
#   1.5.20261002.073514 — app-log-live.py, apps/_reseau.py et apps/_odoo_db.py dans la ligne « Suite ».
#   1.4.20261001.143624 — apps/_bbb.py dans la ligne « Suite ».
#   1.3.20261001.094048 — Suite de tests dans nginx-tools-tests/ (ancien tests/ encore lu pendant la transition).
#   1.2.20261001.092458 — zip-versions.py dans la ligne « Suite » du rapport.
#   1.1.20260930.225745 — Recommandations numérotées une seule fois (« 1. 1. » auparavant).
#   1.0.20260930.163902 — Première version : rapport d'erreurs commun (--report-err).
"""
import argparse
import datetime
import getpass
import os
import platform
import re
import socket
import sys
import time
import traceback

__version__ = "1.11.20261016.173838"

# Programmes de la suite dont la version est relevée (détecte un déploiement incomplet : fichiers d'âges différents).
FICHIERS_SUITE = ["nginx-hardening.sh", "nginx-log-audit.sh", "sync-crowdsec-blocklist.sh", "odoo-backup.sh",
                  "app-health-check.py", "app-log-check.py", "web-monitor.py", "zip-versions.py", "app-log-live.py", "odoo-mail-retry.py", "apps/_rapport.py", "apps/_bbb.py", "apps/_reseau.py",
                  "apps/_odoo_db.py", "apps/_listes.py", "apps/_cache_ip.py", "apps/_courriel.py",
                  "nginx-tools-tests/run-all.sh"]
# Suite de tests : dossier nginx-tools-tests/ (archive nginx-tools-tests.zip) ; « tests/ » avant la 1.3 — encore lu tant
# que l'ancienne copie existe, pour ne pas perdre la version de la suite pendant la transition.
SUITE = "nginx-tools-tests/"
ANCIEN_DOSSIER_SUITE = "tests/"
VERSION_RE = re.compile(r'(?:SCRIPT_VERSION=|__version__ = )"([^"]+)"')

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SECRET_RE = re.compile(r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key)[A-Za-z0-9_.-]*\s*[=:]\s*)(\S+)")
SECRET_FR_RE = re.compile(r"(?i)(mot de passe\s*[=:]\s*)(\S+)")

TAG_ECHEC = re.compile(r"\[(?:FAIL|ÉCHEC|ECHEC|ERR[A-ZÉ]*)\]")
ECHEC_LIGNE = re.compile(
    r"^\s*(?:ERREUR|ERROR|FAIL|FATAL)\b"                        # ligne QUI COMMENCE par… (pas « Erreurs Odoo : 0 »)
    r"|^\s*VERDICT\s*:.*ÉCHEC"
    r"|\*\*\* ARRÊT INATTENDU|Commande fautive"
    r"|\bÉCHEC\b|PAS démarré|N'EXISTE PAS|a échoué"                # messages d'échec sans étiquette (statuts, diagnostics)
    r"|command not found|Permission denied|No such file or directory|syntax error|unbound variable|Erreur de segmentation"
    r"|\[Errno \d+\]")
TAG_ATTN = re.compile(r"\[(?:ATTN|WARN|WARNING|INSTABLE|IGNORÉ)\]|^\s*(?:ATTENTION|WARNING)\b|^\s*⚠|^\s*VERDICT\s*:.*NON vérifié")
TAG_SKIP = re.compile(r"\[SKIP\]")
RECO_RE = re.compile(r"^\s*\d+\.\s+\[(HAUTE|MOYENNE|FAIBLE)\]")
CONTEXTE_RE = re.compile(r"^\s*(?:Application\s*:|Configuration lue\s*:|Options\s*:|Sommaire\s+—)")
TRACEBACK = "Traceback (most recent call last):"
DEJA_NUMEROTE = re.compile(r"^\d+\.\s+")       # « 1. [MOYENNE] … » : numéro du programme, remplacé par celui du rapport

MAX_ELEMENTS = 30            # par catégorie ; le reste est compté
LONGUEUR_LIGNE = 500         # caractères conservés par ligne
LONGUEUR_DETAIL = 400
LONGUEUR_RECO = 700          # « Comment : … » des recommandations : chemins, adresses — utiles en entier


def nettoyer(texte):
    """Texte sans codes de couleur ni retours chariot."""
    return ANSI_RE.sub("", texte).replace("\r", "")


def masquer(ligne):
    """Mots de passe, secrets et jetons remplacés par *** (le rapport est destiné à être collé dans une conversation)."""
    return SECRET_FR_RE.sub(r"\1***", SECRET_RE.sub(r"\1***", ligne))


def _tronquer(ligne, longueur):
    ligne = masquer(ligne.rstrip())
    return ligne if len(ligne) <= longueur else ligne[:longueur - 1] + "…"


def _indentation(ligne):
    return len(ligne) - len(ligne.lstrip())


def classer(lignes):
    """{'echecs', 'avertissements', 'recommandations', 'ignores', 'tracebacks'} : listes d'éléments, chacun étant la liste
    des lignes (la première, puis ses lignes de détail plus indentées). Chaque ligne n'est comptée qu'une fois."""
    res = {"echecs": [], "avertissements": [], "recommandations": [], "ignores": [], "tracebacks": []}
    consommees, vus = set(), set()

    def etiquetee(ligne):
        """Ligne qui est elle-même un élément du rapport (jamais le détail d'un autre)."""
        return bool(TAG_ECHEC.search(ligne) or TAG_ATTN.search(ligne) or TAG_SKIP.search(ligne) or RECO_RE.match(ligne)
                    or ligne.strip() == TRACEBACK)

    def detail(i, combien, longueur):
        """Lignes qui SUIVENT et sont plus indentées, jusqu'à la prochaine ligne étiquetée ; marquées comme consommées."""
        suite, j, base = [], i + 1, _indentation(lignes[i])
        while (j < len(lignes) and len(suite) < combien and lignes[j].strip() and not etiquetee(lignes[j])
               and _indentation(lignes[j]) > base):
            suite.append(_tronquer(lignes[j], longueur))
            consommees.add(j)
            j += 1
        return suite

    for i, ligne in enumerate(lignes):
        if i in consommees:
            continue
        if ligne.strip() == TRACEBACK:                              # trace d'appels Python : fin de la trace seulement
            j = i + 1
            while j < len(lignes) and lignes[j].startswith((" ", "\t")):
                j += 1
            bloc = [ligne] + lignes[max(i + 1, j - 4):j] + ([lignes[j]] if j < len(lignes) else [])
            res["tracebacks"].append([_tronquer(x, LONGUEUR_DETAIL) for x in bloc])
            consommees.update(range(i, min(j + 1, len(lignes))))
            continue
        reco = RECO_RE.match(ligne)
        if reco:
            if reco.group(1) != "FAIBLE":
                res["recommandations"].append([_tronquer(ligne, LONGUEUR_LIGNE)] + detail(i, 3, LONGUEUR_RECO))
            else:
                detail(i, 3, LONGUEUR_RECO)                           # FAIBLE : ses lignes Pourquoi/Comment, sans les lister
            continue
        if TAG_ECHEC.search(ligne) or (not TAG_ATTN.search(ligne) and ECHEC_LIGNE.search(ligne)):
            cle = ligne.strip()
            if cle not in vus:
                vus.add(cle)
                res["echecs"].append([_tronquer(ligne, LONGUEUR_LIGNE)] + detail(i, 6, LONGUEUR_DETAIL))
        elif TAG_ATTN.search(ligne):
            cle = ligne.strip()
            if cle not in vus:
                vus.add(cle)
                res["avertissements"].append([_tronquer(ligne, LONGUEUR_LIGNE)] + detail(i, 4, LONGUEUR_DETAIL))
        elif TAG_SKIP.search(ligne):
            res["ignores"].append([_tronquer(ligne, LONGUEUR_LIGNE)])
    return res


def contexte_dans_sortie(lignes, maximum=5):
    """Lignes de contexte que le programme imprime lui-même (application, fichiers de configuration lus, options)."""
    trouvees = []
    for ligne in lignes:
        if CONTEXTE_RE.match(ligne) and len(trouvees) < maximum:
            trouvees.append(_tronquer(ligne.strip(), LONGUEUR_LIGNE))
    return trouvees


def versions_suite(dossier):
    """(présentes, absentes) : « programme version » des fichiers de la suite trouvés dans le dossier des programmes."""
    presentes, absentes = [], []
    for relatif in FICHIERS_SUITE:
        chemin = os.path.join(dossier, relatif)
        if relatif.startswith(SUITE) and not os.path.isfile(chemin):
            chemin = os.path.join(dossier, ANCIEN_DOSSIER_SUITE + relatif[len(SUITE):])
        try:
            with open(chemin, encoding="utf-8", errors="replace") as f:
                m = VERSION_RE.search(f.read())
            presentes.append(f"{os.path.basename(relatif)} {m.group(1) if m else '?'}")
        except OSError:
            if not relatif.startswith(SUITE):              # suite absente : normal sur un serveur sans les tests
                absentes.append(os.path.basename(relatif))
    return presentes, absentes


def systeme(shell=None):
    """Nom du serveur et de son système, pour le rapport."""
    os_nom = ""
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for ligne in f:
                if ligne.startswith("PRETTY_NAME="):
                    os_nom = ligne.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    try:
        utilisateur = getpass.getuser()
    except Exception:
        utilisateur = str(os.geteuid())
    return {"hote": socket.gethostname(), "fqdn": socket.getfqdn(), "os": os_nom or platform.system(),
            "noyau": platform.release(), "utilisateur": utilisateur, "shell": shell or "", "python": platform.python_version(),
            "date": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")}


def construire_rapport(programme, version, commande, sortie, code, duree, dossier, shell=None, info=None):
    """Le bloc de rapport (texte). `info` (dict de systeme()) peut être fourni — les tests le fixent."""
    lignes = nettoyer(sortie).splitlines()
    classes = classer(lignes)
    info = info or systeme(shell)
    presentes, absentes = versions_suite(dossier) if dossier else ([], [])
    nom_hote = info["hote"] + (f" ({info['fqdn']})" if info["fqdn"] and info["fqdn"] != info["hote"] else "")
    n_echecs = len(classes["echecs"]) + len(classes["tracebacks"])
    n_attn, n_reco = len(classes["avertissements"]), len(classes["recommandations"])
    r = ["=" * 18 + " RAPPORT D'ERREURS (--report-err) — copier de cette ligne jusqu'à la dernière " + "=" * 18,
         f"Programme : {programme} v{version} — commande : {masquer(commande)}",
         f"Serveur   : {nom_hote} — {info['os']} — noyau {info['noyau']} — utilisateur {info['utilisateur']}"
         + (f" — {info['shell']}" if info["shell"] else "") + f" — Python {info['python']}",
         f"Exécution : {info['date']} — durée {duree} s — code de sortie {code}" + (" (ÉCHEC)" if code else "")]
    for i, ligne in enumerate(contexte_dans_sortie(lignes)):
        r.append(("Contexte  : " if i == 0 else "            ") + ligne)
    if presentes:
        r.append("Suite     : " + " · ".join(presentes) + (f" — ABSENTS : {', '.join(absentes)}" if absentes else ""))
    r.append(f"Bilan     : {n_echecs} échec(s), {n_attn} avertissement(s), {n_reco} recommandation(s) à traiter"
             + (f", {len(classes['ignores'])} vérification(s) ignorée(s)" if classes["ignores"] else "")
             + f" — sortie de {len(lignes)} ligne(s)")
    r.append("-" * 118)

    def section(titre, elements):
        if not elements:
            return
        r.append(f"{titre} ({len(elements)}) :")
        for n, element in enumerate(elements[:MAX_ELEMENTS], 1):
            # Élément déjà numéroté par le programme (« 1. [MOYENNE] … ») : son numéro est retiré (« 1. 1. » avant la 1.1).
            premiere = DEJA_NUMEROTE.sub("", element[0].strip())
            r.append(f"  {n}. {premiere}")
            r.extend(f"       {x.strip()}" for x in element[1:])
        if len(elements) > MAX_ELEMENTS:
            r.append(f"  … et {len(elements) - MAX_ELEMENTS} autre(s), non listé(s)")

    section("ÉCHECS", classes["echecs"])
    section("ERREURS PYTHON (trace d'appels)", classes["tracebacks"])
    section("AVERTISSEMENTS", classes["avertissements"])
    section("RECOMMANDATIONS HAUTE / MOYENNE", classes["recommandations"])
    if classes["ignores"]:
        r.append(f"VÉRIFICATIONS IGNORÉES ({len(classes['ignores'])}) : " + " | ".join(x[0].strip() for x in classes["ignores"][:5]))
    if not (n_echecs or n_attn or n_reco):
        if code:
            r.append(f"Code de sortie {code} sans message d'échec reconnu — dernières lignes de la sortie :")
            r.extend("  " + _tronquer(x, LONGUEUR_LIGNE) for x in lignes[-12:])
        else:
            r.append("Aucun échec ni avertissement détecté.")
    r.append("=" * 38 + " FIN DU RAPPORT " + "=" * 38)
    return "\n".join(r)


class _Tee:
    """Flux qui écrit dans le vrai flux ET garde une copie (stdout et stderr dans l'ordre réel des écritures)."""
    def __init__(self, reel, tampon):
        self._reel, self._tampon = reel, tampon

    def write(self, texte):
        self._tampon.append(texte)
        return self._reel.write(texte)

    def flush(self):
        self._reel.flush()

    def isatty(self):
        return self._reel.isatty()

    def __getattr__(self, nom):
        return getattr(self._reel, nom)


def _code_de_sortie(valeur):
    if valeur is None:
        return 0
    if isinstance(valeur, int):
        return valeur
    print(valeur, file=sys.stderr)                                  # sys.exit("message") : message, code 1
    return 1


def lancer(fonction, programme, version, dossier):
    """Exécute fonction() en copiant sa sortie, puis imprime le rapport ; renvoie le code de sortie (à passer à sys.exit)."""
    tampon, sortie, erreur = [], sys.stdout, sys.stderr
    commande = " ".join([programme] + [a for a in sys.argv[1:] if a != "--report-err"])
    debut, code = time.time(), 0
    sys.stdout, sys.stderr = _Tee(sortie, tampon), _Tee(erreur, tampon)
    try:
        try:
            code = _code_de_sortie(fonction())
        except SystemExit as e:
            code = _code_de_sortie(e.code)
        except KeyboardInterrupt:
            print("\nInterrompu (Ctrl-C).", file=sys.stderr)
            code = 130
        except Exception:
            traceback.print_exc()
            code = 1
    finally:
        sys.stdout, sys.stderr = sortie, erreur
    print(construire_rapport(programme, version, commande, "".join(tampon), code, int(time.time() - debut), dossier))
    sys.stdout.flush()
    return code


# ------------------------------------------------------------------------------------------------------------------------
# Ligne de commande : utilisée par apps/_rapport.sh (programmes bash)
# ------------------------------------------------------------------------------------------------------------------------
class _Aide(argparse.HelpFormatter):
    """Options de l'aide par ordre alphabétique (nom long, sans les tirets), comme les programmes de la suite."""
    @staticmethod
    def _cle(action):
        return (action.option_strings or [action.dest])[-1].lstrip("-").lower()

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions if groups else sorted(actions, key=self._cle), groups, prefix)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._cle))


class _Parseur(argparse.ArgumentParser):
    def format_help(self):
        return (super().format_help().replace("usage: ", "usage : ", 1).replace("\noptions:\n", "\noptions :\n")
                .replace("show this help message and exit", "affiche cette aide et quitte"))

    def format_usage(self):
        return super().format_usage().replace("usage: ", "usage : ", 1)


def afficher_changelog():
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "doc", "_rapport.changelog.txt")
    try:
        with open(chemin, encoding="utf-8") as f:
            texte = f.read()
    except OSError:
        print(f"Changelog introuvable : {chemin}", file=sys.stderr)
        return 1
    if sys.stdout.isatty():
        texte = re.sub(r"(\d+\.\d+\.\d{8}\.\d{6})", "\x1b[1;36m\\1\x1b[0m", texte)
    try:
        sys.stdout.write(texte)
    except BrokenPipeError:
        pass
    return 0


def main(argv=None):
    p = _Parseur(prog="_rapport.py", formatter_class=_Aide,
                 description="Rapport d'erreurs (--report-err) à partir de la sortie capturée d'un programme bash.")
    p.add_argument("--changelog", action="store_true", help="Affiche le journal des modifications")
    p.add_argument("--code", type=int, default=0, help="Code de sortie du programme")
    p.add_argument("--commande", default="", help="Commande lancée (programme et arguments)")
    p.add_argument("--dossier", default="", help="Dossier des programmes (versions de la suite)")
    p.add_argument("--duree", type=int, default=0, help="Durée d'exécution en secondes")
    p.add_argument("--programme", default="", help="Nom du programme")
    p.add_argument("--programme-version", default="?", help="Version du programme")
    p.add_argument("--shell", default="", help="Interpréteur (ex. « bash 5.1.16 »)")
    p.add_argument("--sortie", help="Fichier contenant la sortie capturée du programme")
    p.add_argument("--version", action="store_true", help="Affiche la version et quitte")
    args = p.parse_args(argv)
    if args.version:
        print(f"_rapport.py version {__version__}")
        return 0
    if args.changelog:
        return afficher_changelog()
    if not args.sortie:
        p.error("--sortie est requis (sauf avec --version ou --changelog)")
    try:
        with open(args.sortie, encoding="utf-8", errors="replace") as f:
            sortie = f.read()
    except OSError as e:
        print(f"_rapport.py : sortie illisible ({e})", file=sys.stderr)
        return 1
    print(construire_rapport(args.programme or "?", args.programme_version, args.commande or args.programme, sortie, args.code,
                             args.duree, args.dossier, shell=args.shell))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
