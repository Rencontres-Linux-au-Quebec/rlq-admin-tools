#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _config.py — fichiers de configuration des programmes Python (module partagé, apps/) : règle commune /etc/default/PROGRAMME.conf, PUIS le fichier personnel
# PROGRAMME.conf (point devant, dans le répertoire personnel ; un ancien ~/.PROGRAMME.cfg est renommé), PUIS la ligne de commande (prioritaire).
#
# HISTORIQUE DE VERSION (résumé — voir doc/_config.changelog.txt pour le détail complet) :
#   1.8.20261020.211944 — Personal file is now ~/.PROGRAMME.conf (not .cfg): legacy ~/.PROGRAMME.cfg renamed automatically (migrer_ancien, personnel).
#   1.7.20261019.150215 — Configuration files with no active option rewritten from the current template at the next run; new copyright.
#   1.6.20261015.143436 — ANONYMIZE : clé commune (app-default.conf).
#   1.5.20261015.080630 — est_root, refus_non_root, avis_non_root ; jours_journaux (LOG_KEEP_DAYS commun).
#   1.4.20261015.073057 — Date de modification des fichiers lus (heure locale).
#   1.3.20261015.065821 — Le fichier commun /etc/default/app-default.conf est créé s'il n'existe pas.
#   1.2.20261014.175821 — Fichier commun à tous les programmes : /etc/default/app-default.conf PUIS ~/.app-default.cfg, lus AVANT le fichier du programme (LANGUAGE, VERBOSE, DEBUG_LEVEL).
#   1.1.20261012.103600 — Premier démarrage : creer_par_defaut() crée le fichier de configuration (copie de doc/PROGRAMME.conf.example, toutes les options en commentaire).
#   1.0.20261010.211030 — Création : lecture KEY=VALUE des deux fichiers, valeurs par défaut des options argparse, ligne « Configuration lue : ».
"""Fichiers KEY=VALUE (une clé par ligne, # = commentaire, guillemets facultatifs), les clés en MAJUSCULES. Le dernier fichier lu l'emporte. Chaque programme
déclare un SCHÉMA {CLÉ: (option argparse, type)} : les valeurs du fichier deviennent les valeurs par défaut des options, que la ligne de commande remplace.
Variable NGINX_TOOLS_ETC_DEFAULT : autre dossier à la place de /etc/default (tests)."""
import os
import re
import sys
import tempfile
import time

__version__ = "1.8.20261020.211944"
OUI = ("1", "true", "yes", "oui", "on", "vrai")
NON = ("0", "false", "no", "non", "off", "faux", "")


COMMUN = "app-default"                                         # fichier commun à tous les programmes : /etc/default/app-default.conf, ~/.app-default.conf
CLES_COMMUNES = ("LANGUAGE", "VERBOSE", "DEBUG_LEVEL", "LOG_KEEP_DAYS", "ANONYMIZE")         # les seules clés lues dans le fichier commun (le fichier du programme l'emporte)


def chemins_communs():
    """[(chemin, existe)] du fichier commun à tous les programmes (système, puis personnel), dans l'ordre de lecture ; lu AVANT le fichier du programme."""
    return chemins_regle(COMMUN)


JOURNAUX_JOURS_DEFAUT = 180            # jours de journaux gardés par les programmes qui écrivent les leurs (LOG_KEEP_DAYS du fichier commun) ; 0 = jamais effacés


def jours_journaux(defaut=JOURNAUX_JOURS_DEFAUT):
    """Durée de conservation (jours) des journaux propres aux programmes : LOG_KEEP_DAYS des fichiers de configuration (variable NGINX_TOOLS_LOG_KEEP_DAYS exportée par lire()),
    sinon `defaut` (180). 0 = ne jamais effacer."""
    try:
        return max(0, int(os.environ.get("NGINX_TOOLS_LOG_KEEP_DAYS", "").strip()))
    except ValueError:
        return defaut


def niveau_debug(cfg):
    """DEBUG_LEVEL du fichier (entier, 0 si absent ou invalide)."""
    try:
        return max(0, int(str(cfg.get("DEBUG_LEVEL", "0")).strip() or 0))
    except ValueError:
        return 0


ANCIEN_SUFFIXE = ".cfg"                  # 1.8: suffix of the personal files before the rule became ~/.PROGRAMME.conf


def _deja_signale(ancien):
    """True if this legacy file was already reported by this program or the program that started it (variable NGINX_TOOLS_CONFIG_SIGNALES, inherited by the
    child programs: one notice per file and per run, even when apps/_config.py is loaded several times); otherwise it is recorded and False is returned."""
    deja = [c for c in os.environ.get("NGINX_TOOLS_CONFIG_SIGNALES", "").split(os.pathsep) if c]
    if ancien in deja:
        return True
    os.environ["NGINX_TOOLS_CONFIG_SIGNALES"] = os.pathsep.join(deja + [ancien])
    return False


def _avis(texte):
    """Notice on the standard error (never on the standard output, which may be data). The configuration is read BEFORE the program knows its display
    language: the French text is translated here by lang/_config.XX.po, in the language given by --lang, NGINX_TOOLS_LANG or the locale (apps/_i18n.py)."""
    try:
        import importlib.util
        dossier = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location("_i18n_avis", os.path.join(dossier, "_i18n.py"))
        i18n = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(i18n)
        texte = i18n.traducteur(i18n.langue(sys.argv[1:]), os.path.dirname(dossier), "_config")(texte)
    except Exception:                                            # noqa: BLE001 — translation is a comfort: the French notice is displayed anyway
        pass
    try:
        print(texte, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def migrer_ancien(chemin):
    """1.8 — path of a personal file to READ, after migration of its legacy name. `chemin` ends with .conf (ex. ~/.web-monitor.conf); the legacy file is the same
    name with .cfg (~/.web-monitor.cfg, rule before 1.8):
      * no legacy file: `chemin`, nothing done;
      * legacy file only: RENAMED to `chemin` (same owner, rights and content), one notice on stderr; rename impossible (read-only home…): the legacy file is
        returned so that its settings still apply, with a notice;
      * both files: `chemin` is read, the legacy file is IGNORED, one notice per run (never merged nor deleted automatically: its settings may differ).
    NGINX_TOOLS_CONFIG_MIGRER=0: no rename (the legacy file is still read when it is the only one). Never raises."""
    if not chemin.endswith(".conf"):
        return chemin
    ancien = chemin[:-len(".conf")] + ANCIEN_SUFFIXE
    try:
        if not os.path.lexists(ancien):
            return chemin
        if os.path.lexists(chemin):
            if not _deja_signale(ancien):
                _avis(f"Configuration : ancien fichier {ancien} IGNORÉ ({chemin} existe et l'emporte) — reporter ses réglages dans {chemin}, puis le supprimer")
            return chemin
        if os.environ.get("NGINX_TOOLS_CONFIG_MIGRER") == "0":
            return ancien
        os.rename(ancien, chemin)
    except OSError as e:
        if not _deja_signale(ancien):
            _avis(f"Configuration : impossible de renommer {ancien} ({e.strerror}) — l'ancien fichier est lu tel quel au lieu de {chemin}")
        return ancien
    _deja_signale(ancien)
    _avis(f"Configuration : ancien fichier {ancien} renommé en {chemin} (les fichiers personnels se terminent maintenant par .conf)")
    return chemin


def personnel(programme):
    """1.8 — personal file of a program to read: ~/.PROGRAMME.conf (a legacy ~/.PROGRAMME.cfg is renamed first, see migrer_ancien)."""
    return migrer_ancien(os.path.join(os.path.expanduser("~"), f".{programme}.conf"))


def chemins_regle(programme):
    """[(chemin, existe)] des deux fichiers de la règle, dans l'ordre de lecture : /etc/default/PROGRAMME.conf, puis ~/.PROGRAMME.conf (1.8 : un ancien
    ~/.PROGRAMME.cfg est renommé d'abord, voir migrer_ancien)."""
    systeme = os.path.join(os.environ.get("NGINX_TOOLS_ETC_DEFAULT", "/etc/default"), f"{programme}.conf")
    perso = personnel(programme)
    return [(c, os.path.isfile(c)) for c in (systeme, perso)]


def lire_fichier(chemin):
    """{CLÉ: valeur} d'un fichier KEY=VALUE ; illisible : {}."""
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
                elif " #" in valeur:
                    valeur = valeur.split(" #", 1)[0].rstrip()
                res[cle.strip().upper()] = valeur
    except OSError:
        pass
    return res


SANS_CREATION = ("-h", "--help", "--version", "--changelog")      # arguments qui n'exécutent rien : aucun fichier n'est créé


def est_root():
    """Vrai si le programme tourne avec les droits de root."""
    return hasattr(os, "geteuid") and os.geteuid() == 0


def refus_non_root(programme, raison, argv=None):
    """Message d'ERREUR (ou None) d'un programme qui a absolument besoin de root pour ce qu'on lui demande : à afficher puis quitter AU DÉBUT, avant tout travail. Jamais avec
    --help / --version / --changelog (SANS_CREATION) ni si le programme est déjà root. `raison` : ce qui exige root (en français, ex. « lecture de PostgreSQL »)."""
    argv = sys.argv[1:] if argv is None else argv
    if est_root() or any(a in SANS_CREATION for a in argv):
        return None
    return f"ERREUR : {programme} doit être lancé en root (sudo {programme} …) : {raison}."


def avis_non_root(programme, limites, argv=None):
    """Avis (ou None) d'un programme qui fonctionne sans root mais en voyant moins : une ligne qui dit ce qui sera incomplet. Aucun avis si root, avec --help / --version /
    --changelog ou si NGINX_TOOLS_AVIS_ROOT=0."""
    argv = sys.argv[1:] if argv is None else argv
    if est_root() or os.environ.get("NGINX_TOOLS_AVIS_ROOT") == "0" or any(a in SANS_CREATION for a in argv):
        return None
    return f"Droits limités (pas root) : {limites} — relancer avec sudo pour une vue complète."


def creer_par_defaut(programme, dossier_doc=None, argv=None):
    """Premier démarrage : si AUCUN fichier de la règle n'existe, crée celui du système (/etc/default/PROGRAMME.conf, root) ou, sans les droits, le fichier personnel
    (~/.PROGRAMME.conf) : copie de doc/PROGRAMME.conf.example (toutes les options y sont en commentaire = valeurs par défaut) précédée de trois lignes d'origine.
    Rien n'est créé avec -c/--config, avec --help / --version / --changelog, si NGINX_TOOLS_CONFIG_CREER=0 ou si le modèle est absent. Retourne le chemin créé ou None ;
    il est aussi inscrit dans la variable NGINX_TOOLS_CONFIG_CREE (pour la ligne « Configuration lue : … »)."""
    argv = sys.argv[1:] if argv is None else argv
    if os.environ.get("NGINX_TOOLS_CONFIG_CREER") == "0" or any(a in SANS_CREATION or a == "-c" or a.startswith("--config") for a in argv):
        return None
    dossier_doc = dossier_doc or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "doc", "en")
    _creer(chemins_communs(), COMMUN, dossier_doc, variable="NGINX_TOOLS_CONFIG_COMMUN_CREE")      # le fichier commun d'abord (1.3) : créé s'il n'existe pas, même si celui du programme existe
    chemins = chemins_regle(programme)
    for nom, liste in ((COMMUN, chemins_communs()), (programme, chemins)):       # 1.7 : fichiers jamais modifiés (aucune option active) remis au modèle actuel
        for chemin, existe in liste:
            if existe:
                rafraichir(chemin, nom, dossier_doc)
    if any(existe for _, existe in chemins):
        return None
    return _creer(chemins, programme, dossier_doc, variable="NGINX_TOOLS_CONFIG_CREE")


ACTIVE_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")
ENTETE_MAJ = "# Fichier mis à jour automatiquement le {DATE} par {NOM} : aucune option n’y était active, il suit le modèle actuel."


def options_actives(texte):
    """Vrai si le texte d'un fichier de configuration contient au moins une ligne CLÉ=VALEUR hors commentaire (l'utilisateur l'a modifié)."""
    return any(ACTIVE_RE.match(ligne) for ligne in texte.splitlines())


def rafraichir(chemin, nom, dossier_doc):
    """1.7 : un fichier de configuration EXISTANT dont aucune option n'est active (tout en commentaire = jamais modifié) est réécrit à partir du modèle
    doc/NOM.conf.example quand celui-ci a changé (nouvelles clés, nouveaux commentaires) : il montre toujours toutes les options du programme installé.
    Un fichier avec au moins une option active n'est JAMAIS touché. Écriture sûre : fichier temporaire du même dossier, mêmes droits et propriétaire, puis
    renommage. Retourne le chemin mis à jour ou None ; il est ajouté à la variable NGINX_TOOLS_CONFIG_MAJ (ligne « Configuration lue : … »)."""
    if os.environ.get("NGINX_TOOLS_CONFIG_MAJ_AUTO") == "0":
        return None
    try:
        with open(os.path.join(dossier_doc, f"{nom}.conf.example"), encoding="utf-8") as f:
            modele = f.read()
        with open(chemin, encoding="utf-8") as f:
            actuel = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    if options_actives(actuel) or actuel.endswith(modele):
        return None
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config-entete.txt"), encoding="utf-8") as f:
            lignes = f.read().splitlines(True)
    except OSError:
        lignes = []
    entete = "".join([ENTETE_MAJ + "\n"] + lignes[1:]).replace("{DATE}", time.strftime("%Y-%m-%d %H:%M")).replace("{NOM}", nom)
    dossier = os.path.dirname(os.path.abspath(chemin))
    if not os.access(dossier, os.W_OK) or not os.access(chemin, os.W_OK):
        return None
    temporaire = None
    try:
        etat = os.stat(chemin)
        fd, temporaire = tempfile.mkstemp(prefix=f".{os.path.basename(chemin)}.", dir=dossier)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(entete + modele)
        os.chmod(temporaire, etat.st_mode & 0o7777)
        if est_root():
            os.chown(temporaire, etat.st_uid, etat.st_gid)
        os.replace(temporaire, chemin)
    except OSError:
        if temporaire and os.path.exists(temporaire):
            try:
                os.unlink(temporaire)
            except OSError:
                pass
        return None
    deja = [c for c in os.environ.get("NGINX_TOOLS_CONFIG_MAJ", "").split(os.pathsep) if c]
    os.environ["NGINX_TOOLS_CONFIG_MAJ"] = os.pathsep.join(deja + [chemin])
    return chemin


def _creer(chemins, nom, dossier_doc, variable):
    """Crée le premier fichier de `chemins` [(chemin, existe)] qui peut l'être (système puis personnel) à partir de doc/NOM.conf.example, si aucun n'existe ; chemin créé ou None."""
    if any(existe for _, existe in chemins):
        return None
    modele = os.path.join(dossier_doc, f"{nom}.conf.example")
    try:
        with open(modele, encoding="utf-8") as f:
            texte = f.read()
    except OSError:
        return None
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config-entete.txt"), encoding="utf-8") as f:
            entete = f.read().replace("{DATE}", time.strftime("%Y-%m-%d %H:%M")).replace("{NOM}", nom)
    except OSError:
        entete = ""
    for (chemin, _), mode in zip(chemins, (0o644, 0o600)):
        try:
            if not os.access(os.path.dirname(chemin), os.W_OK):
                continue
            fd = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(entete + texte)
            os.environ[variable] = chemin
            return chemin
        except OSError:
            continue
    return None


def lire(programme, explicite=None):
    """(configuration, [fichiers lus]) : fusion des fichiers de la règle (le dernier l'emporte) ; `explicite` (-c / --config) : ce fichier seul.
    Aucun fichier : le fichier par défaut est créé (creer_par_defaut). Sans `explicite`, le fichier COMMUN à tous les programmes (app-default.conf : LANGUAGE, VERBOSE,
    DEBUG_LEVEL) est lu d'abord, puis celui du programme, qui l'emporte. DEBUG_LEVEL >= 1 vaut VERBOSE=oui (sauf VERBOSE écrit quelque part) ; le niveau est exporté
    dans NGINX_TOOLS_DEBUG_LEVEL."""
    if not explicite:
        creer_par_defaut(programme)
    communs = [] if explicite else [c for c, existe in chemins_communs() if existe]
    propres = [explicite] if explicite else [c for c, existe in chemins_regle(programme) if existe]
    cfg = {}
    for c in communs:
        cfg.update({k: v for k, v in lire_fichier(c).items() if k in CLES_COMMUNES})
    for c in propres:
        cfg.update(lire_fichier(c))
    niveau = niveau_debug(cfg)
    if niveau >= 1 and "VERBOSE" not in cfg:
        cfg["VERBOSE"] = "oui"
    if niveau:
        os.environ["NGINX_TOOLS_DEBUG_LEVEL"] = str(niveau)
    if str(cfg.get("LOG_KEEP_DAYS", "")).strip().isdigit():
        os.environ["NGINX_TOOLS_LOG_KEEP_DAYS"] = str(cfg["LOG_KEEP_DAYS"]).strip()
    return cfg, communs + propres


def booleen(valeur, defaut=False):
    v = str(valeur).strip().lower()
    return True if v in OUI else False if v in NON else defaut


def defauts_options(cfg, schema):
    """({option argparse: valeur}, [problèmes]) : convertit les valeurs du fichier selon le schéma {CLÉ: (option, type)} ; type = bool, int, str ou une fonction
    (qui lève ValueError / argparse.ArgumentTypeError si la valeur est invalide). Clé absente ou vide : option non touchée ; valeur invalide : signalée, ignorée."""
    res, problemes = {}, []
    for cle, (option, type_) in schema.items():
        valeur = cfg.get(cle, "").strip()
        if not valeur:
            continue
        try:
            res[option] = booleen(valeur, None) if type_ is bool else type_(valeur)
            if res[option] is None:
                raise ValueError(valeur)
        except (ValueError, TypeError, Exception) as e:       # noqa: B014 — fonction de type fournie par le programme (peut lever ArgumentTypeError)
            problemes.append(f"{cle}={valeur} ({e})")
    return res, problemes


def date_modification(chemin):
    """Date et heure LOCALES de dernière modification du fichier (« 2026-10-15 07:12 »), « ? » s'il est illisible."""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(chemin)))
    except OSError:
        return "?"


def avec_date(chemin):
    """« /chemin/absolu (modifié le 2026-10-15 07:12) » : le fichier de configuration lu et sa dernière modification (heure locale)."""
    return f"{os.path.abspath(chemin)} (modifié le {date_modification(chemin)})"


def ligne_configuration(fichiers, explicite=None, programme=""):
    """« Configuration lue : A, puis B (le dernier l'emporte) » ; aucun fichier : « Configuration : aucun fichier (cherchés : …) — valeurs par défaut »."""
    if explicite:
        return f"Configuration lue : {avec_date(explicite)} (demandé par -c/--config : aucun autre fichier n'est lu)"
    if not fichiers:
        return "Configuration : aucun fichier (cherchés : " + ", ".join(c for c, _ in chemins_regle(programme)) + ") — valeurs par défaut"
    cree = os.environ.get("NGINX_TOOLS_CONFIG_CREE")
    note = " (fichier créé à l'instant : toutes les options y sont en commentaire, valeurs par défaut)" if cree and cree in fichiers else ""
    maj = [c for c in os.environ.get("NGINX_TOOLS_CONFIG_MAJ", "").split(os.pathsep) if c and c in fichiers]
    if maj and not note:
        note = (" (" + ", ".join(os.path.basename(c) for c in maj)
                + " mis à jour à l'instant d'après le nouveau modèle : aucune option n'y était active)")
    return "Configuration lue : " + ", puis ".join(avec_date(c) for c in fichiers) + (" (le dernier l'emporte)" if len(fichiers) > 1 else "") + note
