#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _config.py - configuration files of the Python programs (shared module, apps/): common rule /etc/default/PROGRAM.conf, THEN the personal file
# PROGRAM.conf (dot in front, in the home folder; an old ~/.PROGRAM.cfg is renamed), THEN the command line (which takes priority).
#
"""Fichiers KEY=VALUE (une clé par ligne, # = commentaire, guillemets facultatifs), les clés en MAJUSCULES. Le dernier fichier lu l'emporte. Chaque programme
déclare un SCHÉMA {CLÉ: (option argparse, type)} : les valeurs du fichier deviennent les valeurs par défaut des options, que la ligne de commande remplace.
Variable NGINX_TOOLS_ETC_DEFAULT : autre dossier à la place de /etc/default (tests)."""
import os
import re
import sys
import tempfile
import time

__version__ = "1.15.20261113.074229"
OUI = ("1", "true", "yes", "oui", "on", "vrai")
NON = ("0", "false", "no", "non", "off", "faux", "")
# 1.9: values are written in English only; these old French values are still read (same meaning), with a warning (valeurs_francaises).
FRANCAIS = {"oui": "yes", "non": "no", "vrai": "true", "faux": "false", "aucun": "none", "aucune": "none"}


COMMUN = "app-default"                                         # common file for all the programs: /etc/default/app-default.conf, ~/.app-default.conf
CLES_COMMUNES = ("LANGUAGE", "VERBOSE", "DEBUG_LEVEL", "LOG_KEEP_DAYS", "ANONYMIZE", "THEME")         # the only keys read in the common file (the program's file wins)


def chemins_communs():
    """[(chemin, existe)] du fichier commun à tous les programmes (système, puis personnel), dans l'ordre de lecture ; lu AVANT le fichier du programme."""
    return chemins_regle(COMMUN)


JOURNAUX_JOURS_DEFAUT = 180            # days of logs kept by the programs that write their own (LOG_KEEP_DAYS of the common file); 0 = never erased


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
    except Exception:                                            # noqa: BLE001 - translation is a comfort: the French notice is displayed anyway
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


def lire_texte(texte):
    """{CLÉ: valeur} d'un texte KEY=VALUE (1.13 : séparé de lire_fichier pour vérifier le résultat de --config-merge avant de l'écrire)."""
    res = {}
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        if re.match(r"\s+#", valeur):            # 1.13: "KEY=    # comment" is an empty value, not the text of the comment
            valeur = ""
        valeur = valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
            valeur = valeur[1:-1]
        elif " #" in valeur:
            valeur = valeur.split(" #", 1)[0].rstrip()
        res[cle.strip().upper()] = valeur
    return res


def lire_fichier(chemin):
    """{CLÉ: valeur} d'un fichier KEY=VALUE ; illisible : {}."""
    try:
        with open(chemin, encoding="utf-8") as f:
            return lire_texte(f.read())
    except OSError:
        return {}


SANS_CREATION = ("-h", "--help", "--version", "--changelog")      # arguments that run nothing: no file is created


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
    _creer(chemins_communs(), COMMUN, dossier_doc, variable="NGINX_TOOLS_CONFIG_COMMUN_CREE")      # the common file first (1.3): created if it does not exist, even if the program's own one exists
    chemins = chemins_regle(programme)
    for nom, liste in ((COMMUN, chemins_communs()), (programme, chemins)):       # 1.7: files never modified (no active option) reset to the current template
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
    DEBUG_LEVEL) est lu d'abord, puis celui du programme, qui l'emporte. DEBUG_LEVEL >= 1 vaut VERBOSE=yes (sauf VERBOSE écrit quelque part) ; le niveau est exporté
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
        cfg["VERBOSE"] = "yes"
    if niveau:
        os.environ["NGINX_TOOLS_DEBUG_LEVEL"] = str(niveau)
    if str(cfg.get("LOG_KEEP_DAYS", "")).strip().isdigit():
        os.environ["NGINX_TOOLS_LOG_KEEP_DAYS"] = str(cfg["LOG_KEEP_DAYS"]).strip()
    return cfg, communs + propres


def valeurs_francaises(cfg):
    """[« CLÉ=oui → yes », …] : clés dont la valeur est un ancien mot français (oui, non, vrai, faux, aucun) ; lues quand même, à remplacer par l'anglais."""
    return [f"{cle}={valeur} → {FRANCAIS[str(valeur).strip().lower()]}" for cle, valeur in sorted(cfg.items())
            if str(valeur).strip().lower() in FRANCAIS]


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
        except (ValueError, TypeError, Exception) as e:       # noqa: B014 - function type provided by the program (may raise ArgumentTypeError)
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


# ---- 1.12: --config-merge, shared by every program (Python: fusionner_cli(); Bash: python3 apps/_config.py --merge PROGRAM) ----
_MESSAGES_FUSION = {
    "fr": {"modele": "Configuration par défaut introuvable : {chemin}", "ecriture": "Écriture impossible de {chemin} : {erreur}",
           "fait": "Configuration fusionnée dans {chemin}", "lus": "  lu(s) : {fichiers}", "aucun": "aucun (nouveau fichier)",
           "nouveau": "  nouvelle configuration par défaut : {chemin}", "copie": "  copie de l'ancien fichier : {chemin}", "sans": "aucune",
           "gardees": "  valeurs gardées : {n}", "inconnues": "  clés absentes du modèle, gardées avec leur lien ou leur page : {cles}",
           "repris": "# Repris de l'ancien fichier par --config-merge le {date} : ses commentaires absents du modèle, puis ses lignes inactives (clé écrite deux fois : la valeur plus bas comptait ; renuméroter ou supprimer). À relire.",
           "doublons": "  clés écrites deux fois dans l'ancien fichier : la dernière valeur (celle qui comptait) est gardée, les autres en commentaire à la fin : {cles}",
           "entete": "# Clés de l'ancien fichier absentes du modèle (gardées par --config-merge le {date})",
           "refus": "Fusion refusée, {chemin} n'est pas modifié : {raison}", "perdues": "valeurs qui seraient perdues : {cles}",
           "plus_court": "le nouveau fichier serait plus petit que l'ancien ({apres} lignes et {apres_o} octets, avant {avant} lignes et {avant_o} octets)",
           "avant": "Fusion refusée, rien n'est modifié : corriger d'abord ces problèmes de la configuration, puis relancer --config-merge :",
           "deux_fois": "{cle} écrite deux fois ({lieu}) : une seule ligne compte ; renuméroter ou supprimer l'autre",
           "invalide": "{lieu} : ligne qui n'est ni vide, ni un commentaire, ni CLÉ=VALEUR : {ligne}"},
    "en": {"modele": "Default configuration not found: {chemin}", "ecriture": "Cannot write {chemin}: {erreur}",
           "fait": "Configuration merged into {chemin}", "lus": "  read: {fichiers}", "aucun": "none (new file)",
           "nouveau": "  new default configuration: {chemin}", "copie": "  backup of the previous file: {chemin}", "sans": "none",
           "gardees": "  values kept: {n}", "inconnues": "  keys not in the template, kept with their link or page: {cles}",
           "repris": "# Taken from the old file by --config-merge on {date}: its comments absent from the template, then its inactive lines (key written twice: the value lower counted; renumber or remove). Read again.",
           "doublons": "  keys written twice in the old file: the last value (the one in effect) is kept, the others as comments at the end: {cles}",
           "entete": "# Keys of the old file not in the template (kept by --config-merge on {date})",
           "refus": "Merge refused, {chemin} is not changed: {raison}", "perdues": "values that would be lost: {cles}",
           "plus_court": "the new file would be smaller than the old one ({apres} lines and {apres_o} bytes, before {avant} lines and {avant_o} bytes)",
           "avant": "Merge refused, nothing is changed: first fix these problems of the configuration, then run --config-merge again:",
           "deux_fois": "{cle} written twice ({lieu}): only one line counts; renumber or remove the other one",
           "invalide": "{lieu}: line that is neither empty, nor a comment, nor KEY=VALUE: {ligne}"},
}


def modele_par_defaut(programme, langue="fr", dossier_doc=None):
    """Chemin du modèle doc/LANGUE/PROGRAMME.conf.example (puis doc/en, doc/fr, puis PROGRAMME.conf.example à la racine du dépôt) ; None si aucun."""
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dossier_doc = dossier_doc or os.path.join(racine, "doc")
    candidats = [os.path.join(dossier_doc, l, f"{programme}.conf.example") for l in dict.fromkeys((langue, "en", "fr"))]
    candidats.append(os.path.join(racine, f"{programme}.conf.example"))
    return next((c for c in candidats if os.path.isfile(c)), None)


def commentaire_fin(ligne):
    """1.13 : commentaire en fin de ligne d'une ligne CLÉ=valeur (avec ses espaces, ex. « # fr or en » précédé de ses espaces) ; "" s'il n'y en a pas."""
    brut = ligne.split("=", 1)[1] if "=" in ligne else ""
    if re.match(r"\s+#", brut):
        return brut
    nette = brut.lstrip()
    if nette[:1] in ("'", '"'):
        fin = nette.find(nette[0], 1)
        reste = nette[fin + 1:] if fin > 0 else ""
        return reste if re.match(r"\s+#", reste) else ""
    trouve = re.search(r"\s+#.*$", brut)
    return trouve.group(0) if trouve else ""


def appliquer_valeurs(lignes, valeurs):
    """Lignes d'un fichier de configuration avec {CLÉ: valeur} appliqué : la ligne active CLÉ=… est remplacée, sinon la première ligne #CLÉ=… est activée,
    sinon CLÉ=… est ajoutée à la fin. Les autres lignes (commentaires compris) restent telles quelles. 1.13 : le commentaire en fin de ligne du modèle
    (« # fr or en ») est gardé."""
    lignes = list(lignes)
    for cle, valeur in valeurs.items():
        texte = f'"{valeur}"' if valeur != valeur.strip() or "#" in valeur else valeur
        actives = [i for i, ligne in enumerate(lignes) if re.match(rf"\s*{re.escape(cle)}\s*=", ligne)]
        commentees = [i for i, ligne in enumerate(lignes) if re.match(rf"\s*#\s*{re.escape(cle)}\s*=", ligne)]
        if actives:
            lignes[actives[-1]] = f"{cle}={texte}{commentaire_fin(lignes[actives[-1]])}"
        elif commentees:
            lignes[commentees[0]] = f"{cle}={texte}{commentaire_fin(lignes[commentees[0]])}"
        else:
            lignes.append(f"{cle}={texte}")
    return lignes


ENTETES_HORS_MODELE = ("# Clés de l'ancien fichier absentes du modèle", "# Keys of the old file not in the template",
                       "# Repris de l'ancien fichier", "# Taken from the old file")
FAMILLE_RE = re.compile(r"^([A-Z]+)_([0-9]+)_")          # 1.14: LINK_4_URL -> family LINK_4, kind LINK


def cle_de_ligne(ligne):
    """1.14 : CLÉ d'une ligne CLÉ=... ou #CLÉ=... (réglage commenté du modèle), en majuscules ; None sinon."""
    trouve = re.match(r"\s*#?\s*([A-Za-z][A-Za-z0-9_]*)\s*=", ligne)
    return trouve.group(1).upper() if trouve else None


def placer_hors_modele(lignes, blocs):
    """1.14 : range chaque bloc d'une clé absente du modèle avec sa famille : après la dernière ligne (active ou commentée) du même LINK_n ou
    PAGE_n ; pour un numéro que le modèle ne montre pas, après la dernière ligne du même genre (LINK_, PAGE_...) ; sinon à la fin.
    Retourne (lignes, blocs laissés pour la fin)."""
    lignes, fin = list(lignes), []
    for cle, bloc in blocs.items():
        trouve = FAMILLE_RE.match(cle)
        if not trouve:
            fin.append(bloc)
            continue
        famille, genre = f"{trouve.group(1)}_{trouve.group(2)}_", re.compile(rf"^{trouve.group(1)}_[0-9]+_")
        pos = max((i for i, l in enumerate(lignes) if (cle_de_ligne(l) or "").startswith(famille)), default=None)
        meme_famille = pos is not None
        if pos is None:
            pos = max((i for i, l in enumerate(lignes) if genre.match(cle_de_ligne(l) or "")), default=None)
        if pos is None:
            fin.append(bloc)
            continue
        if meme_famille:                                  # one link or one page stays one block: no blank line inside
            bloc = [x for x in bloc if x.strip()]
        elif not bloc or bloc[0].strip():                 # a new number starts after a blank line
            bloc = [""] + bloc
        lignes[pos + 1:pos + 1] = bloc
    return lignes, fin


def repris_de_l_ancien(chemin, lignes_modele, deja):
    """1.14 : lignes de l'ancien fichier qui seraient perdues : (1) ses commentaires absents du modèle (notes de l'administrateur, réglages
    commentés) ; (2) les lignes inactives d'une clé écrite deux fois (la valeur plus bas comptait), mises en commentaire. Les lignes déjà
    gardées (`deja`), les en-têtes d'une fusion précédente, les séparateurs et les descriptions d'un ancien modèle (« # PAGE_n_... ») sont
    laissés de côté. Retourne (commentaires, inactives)."""
    try:
        with open(chemin, encoding="utf-8") as f:
            lignes = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return [], []
    du_modele = {l.strip() for l in lignes_modele}
    commentaires, vus = [], set()
    for ligne in lignes:
        nette = ligne.strip()
        if (not nette.startswith("#") or nette in du_modele or ligne in deja or nette in vus or nette.startswith(ENTETES_HORS_MODELE)
                or re.fullmatch(r"#[\s=#-]*", nette) or re.match(r"#\s+[A-Z][A-Z0-9]*_n_", nette)):
            continue
        vus.add(nette)
        commentaires.append(ligne)
    derniere = {}
    for i, ligne in enumerate(lignes):
        if not ligne.strip().startswith("#") and cle_de_ligne(ligne):
            derniere[cle_de_ligne(ligne)] = i
    inactives = ["#" + ligne.strip() for i, ligne in enumerate(lignes)
                 if not ligne.strip().startswith("#") and cle_de_ligne(ligne) and derniere[cle_de_ligne(ligne)] != i]
    return commentaires, inactives


def lignes_hors_modele(fichiers, connues):
    """1.13 : {CLÉ: [lignes]} des clés actives absentes du modèle (LINK_11_URL, PAGE_3_PATH... d'un modèle qui ne montre que les premiers numéros), dans
    l'ordre du fichier, avec les commentaires écrits juste au-dessus ; la ligne est recopiée telle quelle (guillemets et commentaire de fin compris).
    Une clé présente dans plusieurs fichiers : celle du dernier lu (même règle que la lecture). Les lignes « #CLÉ= » du modèle ne sont pas reprises."""
    res = {}
    for chemin in fichiers:
        try:
            with open(chemin, encoding="utf-8") as f:
                lignes = f.read().splitlines()
        except OSError:
            continue
        commentaires, vide_avant, precedente_vide = [], False, True
        for ligne in lignes:
            nette = ligne.strip()
            if nette.startswith("#"):
                if re.match(r"#\s*[A-Za-z][A-Za-z0-9_]*\s*=", nette) or nette.startswith(ENTETES_HORS_MODELE):   # header of a previous merge: not kept twice
                    commentaires = []
                else:
                    if not commentaires:
                        vide_avant = precedente_vide
                    commentaires.append(ligne)
                precedente_vide = False
                continue
            cle = re.match(r"([A-Za-z][A-Za-z0-9_]*)\s*=", nette)
            if cle and cle.group(1).upper() not in connues:
                if not commentaires:
                    vide_avant = precedente_vide
                res.pop(cle.group(1).upper(), None)
                res[cle.group(1).upper()] = ([""] if vide_avant else []) + commentaires + [ligne]     # blank line kept before the block
            commentaires, precedente_vide = [], not nette
    return res


def problemes_avant_fusion(fichiers, m):
    """1.15 : problèmes qu'une fusion ne doit pas trancher à la place de l'administrateur : une clé écrite deux fois dans le même fichier (laquelle
    garder ?) et une ligne qui n'est ni vide, ni un commentaire, ni CLÉ=VALEUR (elle serait perdue). Liste de messages ; vide : la fusion peut se faire."""
    res = []
    for chemin in fichiers:
        try:
            with open(chemin, encoding="utf-8") as f:
                lignes = f.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        vues = {}
        for n, ligne in enumerate(lignes, 1):
            nette = ligne.strip()
            if not nette or nette.startswith("#"):
                continue
            cle = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", nette)
            if not cle:
                res.append(m["invalide"].format(lieu=f"{chemin}:{n}", ligne=nette))
                continue
            cle = cle.group(1).upper()
            if cle in vues:
                res.append(m["deux_fois"].format(cle=cle, lieu=f"{chemin}:{vues[cle]}:{n}"))
            vues[cle] = n
    return res


def fusionner(programme, explicite=None, langue="fr", cles=(), dossier_doc=None):
    """--config-merge : le fichier lu jusqu'ici (le dernier de la règle /etc/default puis ~/.PROGRAMME.conf, ou `explicite` avec -c) est réécrit à partir du
    NOUVEAU modèle (doc/LANGUE/PROGRAMME.conf.example) en gardant les valeurs actives qu'il contient. 1.13 : les clés absentes du modèle (et de `cles`)
    sont GARDÉES à la fin du fichier, avec leurs commentaires, et listées ; avant d'écrire, le résultat est relu : si une valeur manque ou si le
    fichier serait plus petit (lignes ou octets) que l'ancien, rien n'est écrit (code 1). L'ancien fichier est d'abord copié en FICHIER.bak-AAAAMMJJ-HHMMSS (heure locale) ; droits et propriétaire gardés.
    Aucun fichier : /etc/default/PROGRAMME.conf si ce dossier est accessible en écriture (root), sinon ~/.PROGRAMME.conf.
    Retourne (code, lignes) : 0, ou 1 si le modèle manque ou si l'écriture échoue."""
    m = _MESSAGES_FUSION["en" if langue == "en" else "fr"]
    if explicite:
        fichiers, cible = ([explicite] if os.path.isfile(explicite) else []), explicite
    else:
        regle = chemins_regle(programme)
        fichiers = [c for c, existe in regle if existe]
        if fichiers:
            cible = fichiers[-1]
        else:
            systeme = regle[0][0]
            cible = systeme if os.access(os.path.dirname(systeme) or ".", os.W_OK) else regle[1][0]
    # 1.15: a key written twice or an invalid line: the merge is refused until the administrator fixes the file (nothing is written)
    problemes = problemes_avant_fusion(fichiers, m)
    if problemes:
        return 1, [m["avant"]] + [f"  [FAIL] {p}" for p in problemes]
    modele = modele_par_defaut(programme, langue, dossier_doc)
    if not modele:
        return 1, [m["modele"].format(chemin=os.path.join("doc", langue, f"{programme}.conf.example"))]
    with open(modele, encoding="utf-8") as f:
        lignes_modele = f.read().splitlines()
    anciennes = {}
    for c in fichiers:
        anciennes.update(lire_fichier(c))
    connues = {k.upper() for k in cles} | set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)\s*=", "\n".join(lignes_modele), re.MULTILINE))
    gardees = {k: v for k, v in anciennes.items() if k in connues}
    hors_modele = lignes_hors_modele(fichiers, connues)
    laissees = list(hors_modele)
    nouvelles = appliquer_valeurs(lignes_modele, gardees)
    # 1.14: each key absent from the template goes next to its link or page (1.13 put them all at the end)
    nouvelles, a_la_fin = placer_hors_modele(nouvelles, hors_modele)
    if a_la_fin:
        nouvelles += ["", m["entete"].format(date=time.strftime("%Y-%m-%d %H:%M"))]
        for bloc in a_la_fin:
            nouvelles += bloc
    # 1.14: the comments of the administrator and the inactive lines of a key written twice are kept (1.13 removed them)
    commentaires, inactives = repris_de_l_ancien(cible, lignes_modele, {l for b in hors_modele.values() for l in b}) if os.path.isfile(cible) else ([], [])
    if commentaires or inactives:                         # one header: a second merge gives the same file
        nouvelles += ["", m["repris"].format(date=time.strftime("%Y-%m-%d %H:%M"))] + commentaires + inactives
    texte = "\n".join(nouvelles) + "\n"
    doublons = []
    # 1.13: safeguards before writing: every old value is still there, and the file is not smaller than the old one
    apres = lire_texte(texte)
    perdues = sorted(k for k, v in anciennes.items() if apres.get(k) != v)
    if perdues:
        return 1, [m["refus"].format(chemin=cible, raison=m["perdues"].format(cles=", ".join(perdues)))]
    if os.path.isfile(cible):
        try:
            with open(cible, encoding="utf-8") as f:
                ancien = f.read()
        except (OSError, UnicodeDecodeError) as erreur:
            return 1, [m["ecriture"].format(chemin=cible, erreur=erreur)]
        avant, avant_o = len(ancien.splitlines()), len(ancien.encode("utf-8"))
        nb, nb_o = len(texte.splitlines()), len(texte.encode("utf-8"))
        # the only lines allowed to go: a key written twice in the old file, whose first line was already replaced by the next one (dead line)
        vues, mortes_n, mortes_o = {}, 0, 0
        for ligne in ancien.splitlines():
            cle = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\s*=", ligne)
            if cle:
                cle = cle.group(1).upper()
                if cle in vues:
                    mortes_n += 1
                    mortes_o += len(vues[cle].encode("utf-8")) + 1
                    doublons.append(cle)
                vues[cle] = ligne
        if nb < avant - mortes_n or nb_o < avant_o - mortes_o:
            return 1, [m["refus"].format(chemin=cible, raison=m["plus_court"].format(apres=nb, apres_o=nb_o, avant=avant, avant_o=avant_o))]
    copie, temporaire = None, None
    try:
        etat = os.stat(cible) if os.path.isfile(cible) else None
        if etat is not None:
            copie = f"{cible}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
            with open(cible, "rb") as source, open(copie, "wb") as dest:
                dest.write(source.read())
            os.chmod(copie, etat.st_mode & 0o7777)
        dossier = os.path.dirname(os.path.abspath(cible))
        os.makedirs(dossier, exist_ok=True)
        fd, temporaire = tempfile.mkstemp(prefix=f".{os.path.basename(cible)}.", dir=dossier)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        os.chmod(temporaire, (etat.st_mode & 0o7777) if etat else 0o644)
        if etat is not None and est_root():
            os.chown(temporaire, etat.st_uid, etat.st_gid)
        os.replace(temporaire, cible)
    except OSError as erreur:
        if temporaire and os.path.exists(temporaire):
            os.unlink(temporaire)
        return 1, [m["ecriture"].format(chemin=cible, erreur=erreur)]
    res = [m["fait"].format(chemin=cible), m["lus"].format(fichiers=", ".join(fichiers) if fichiers else m["aucun"]),
           m["nouveau"].format(chemin=modele), m["copie"].format(chemin=copie or m["sans"]),
           m["gardees"].format(n=len(gardees)) + (f" ({', '.join(sorted(gardees))})" if gardees else "")]
    if laissees:
        res.append(m["inconnues"].format(cles=", ".join(laissees)))
    if doublons:
        res.append(m["doublons"].format(cles=", ".join(sorted(set(doublons)))))
    return 0, res


def fusionner_cli(programme, explicite=None, langue="fr", cles=()):
    """--config-merge d'un programme Python : affiche le résultat de fusionner() (erreur sur la sortie d'erreur) et retourne le code de sortie."""
    code, lignes = fusionner(programme, explicite, langue, cles)
    try:
        print("\n".join(lignes), file=sys.stderr if code else sys.stdout)
        (sys.stderr if code else sys.stdout).flush()
    except BrokenPipeError:                                  # 1.13: output cut (| head): the merge is done, no traceback
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), (sys.stderr if code else sys.stdout).fileno())
        except OSError:
            pass
    return code


if __name__ == "__main__":
    # python3 apps/_config.py --merge PROGRAM [--config FILE] [--lang fr|en]: --config-merge of the Bash programs
    import argparse
    parser = argparse.ArgumentParser(description="--config-merge of the Bash programs (same rule as the Python programs)")
    parser.add_argument("--config", default=None, metavar="FILE", help="file given with -c / --config (only this one)")
    parser.add_argument("--lang", default="fr", metavar="LANG", help="language of the default configuration and of the messages (fr, en)")
    parser.add_argument("--merge", required=True, metavar="PROGRAM", help="name of the program (without .sh)")
    arguments = parser.parse_args()
    sys.exit(fusionner_cli(arguments.merge, arguments.config or None, arguments.lang))
