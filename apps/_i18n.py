#!/usr/bin/env python3
# _i18n.py — langue d'affichage (fr / en) des programmes Python et traduction de leurs messages (module partagé, apps/).
#
# HISTORIQUE DE VERSION (résumé — voir doc/_i18n.changelog.txt pour le détail complet) :
#   1.17.20261017.105442 — Language: GNU LANGUAGE variable (as gettext); « Options : --lang xx (origin) » says which setting decided and which ones were ignored.
#   1.16.20261016.173838 — foreground_child() / run_foreground(): Ctrl+C belongs to the child program that owns the terminal (no second question from the parent).
#   1.15.20261016.151148 — Old catalog lang/PROGRAM.<source language>.po (left by an earlier version) ignored: it no longer cancels the translation of shared modules.
#   1.14.20261015.230615 — Programme écrit dans la langue choisie : les clés des catalogues de modules qui figurent dans ses propres messages sont ignorées (« journal » ne devient plus « log »).
#   1.13.20261015.220234 — Modules partagés écrits en anglais (ex. app-log-check pour odoo-mail-retry) : leur catalogue est chargé selon LEUR langue source.
#   1.12.20261015.191427 — Langue source par programme (en-tête Source-Language) : base de la migration du code en anglais.
#   1.11.20261015.143436 — --anonymize ajoutée à chaque analyseur d'arguments ; relance derrière le filtre (Contexte).
#   1.10.20261015.065821 — Anglais : unités (o/Ko/Mo/Go → B/KB/MB/GB), virgules décimales → points ; colonnes alignées malgré la différence de longueur.
#   1.9.20261014.154520 — Ctrl+C pendant une question input() : plus de « can't re-enter readline ».
#   1.8.20261013.084000 — Chemins, URL et variables ignorés pour détecter le français restant.
#   1.7.20261012.183000 — Codes de couleur masqués pendant la traduction (« ce serveur » mal traduit, colonnes décalées) ; le fragment le plus long gagne même s’il commence plus loin ; plus de mots français détectés.
#   1.6.20261012.163000 — readline chargé pour toutes les invites ; la question de Ctrl+C accepte le retour arrière.
#   1.5.20261012.094953 — Traducteur : les espaces de remplissage qui suivent un fragment absorbent la différence de longueur (colonnes alignées).
#   1.4.20261011.144500 — Ctrl+C : installer_confirmation_ctrl_c (« Interrompre le programme ? [o/N] »), installée par demarrer().
#   1.3.20261010.222500 — Le catalogue du programme l'emporte sur ceux des modules affichés (un même fragment, deux traductions : « journal » était rendu « log » dans web-monitor.py) ; remplacement en un seul passage (un texte traduit n'est jamais re-traduit).
#   1.2.20261010.213500 — Contexte commun (demarrer) : langue + configuration + print/input traduits + analyseur argparse localisé, partagés par tous les programmes Python.
#   1.1.20261010.210952 — Catalogues au format PO (standard gettext : Poedit, Weblate…), langues ouvertes (lang/PROGRAMME.XX.po), langue du fichier de configuration.
#   1.0.20261010.200936 — Création : choix de la langue (--lang, WEB_MONITOR_LANG, LC_ALL, LC_MESSAGES, LANG) et traduction par fragments d'un catalogue lang/PROGRAMME.en.tsv.
"""Principe : les messages du programme sont écrits en français dans le code ; si la langue choisie n'est pas le français, chaque texte affiché passe par
Traducteur, qui remplace les FRAGMENTS français connus du catalogue de cette langue par leur traduction. Les catalogues sont des fichiers PO (le format
standard de gettext, lisibles par Poedit, Weblate, Crowdin… : msgid = fragment français, msgstr = traduction), un par programme et par langue :
lang/PROGRAMME.XX.po (XX = code de langue : en, es…). Ajouter une langue = ajouter un fichier : aucune modification du programme. Un fragment absent du catalogue
reste en français (jamais d'erreur). Les tests vérifient que tous les messages du programme figurent dans le catalogue anglais."""
import argparse
import contextlib
import glob
import importlib.util
import os
import re
import sys

try:                    # édition de la ligne dans toutes les invites input() (retour arrière ^H ou ^?, flèches) : sans readline, un terminal qui envoie ^H affiche « ^H »
    import readline  # noqa: F401
except ImportError:     # Windows, Python sans readline
    pass

__version__ = "1.17.20261017.105442"
LANGUE_SOURCE = "fr"          # langue des messages dans le code


def langue_source(dossier_programme, programme):
    """Langue des messages DANS LE CODE du programme : « fr » par défaut ; « en » si un de ses catalogues lang/PROGRAMME.XX.po porte l'en-tête
    « Source-Language: en » (programme migré vers l'anglais : le catalogue fr.po traduit alors l'anglais vers le français)."""
    for chemin in sorted(glob.glob(os.path.join(dossier_programme, "lang", f"{programme}.*.po"))):
        try:
            with open(chemin, encoding="utf-8") as f:
                m = re.search(r'^"Source-Language:\s*([A-Za-z_]+)\\n"', f.read(2000), re.M)
        except OSError:
            continue
        if m:
            return m.group(1).lower()
    return LANGUE_SOURCE


def langues_disponibles(dossier_programme, programme):
    """['fr', 'en', …] : la langue du code (voir langue_source) et chaque lang/PROGRAMME.XX.po présent à côté du programme."""
    source = langue_source(dossier_programme, programme)
    trouvees = {re.sub(r"^.*\.([A-Za-z_]+)\.po$", r"\1", c) for c in glob.glob(os.path.join(dossier_programme, "lang", f"{programme}.*.po"))}
    return [source] + sorted(trouvees - {source})


def _code(valeur, disponibles):
    """Code de langue d'une valeur « fr_CA.UTF-8 », « en », « es_MX@euro »… : celui des langues disponibles, sinon None (« C », « POSIX », langue sans catalogue)."""
    v = re.split(r"[.@]", valeur.strip().lower())[0]
    for candidat in (v, v.split("_")[0]):
        if candidat in disponibles:
            return candidat
    return None


def langue(argv=None, variable_programme="", defaut="fr", disponibles=("en", "fr"), configuration=""):
    """Langue d'affichage (code seulement) : voir langue_et_origine."""
    return langue_et_origine(argv, variable_programme, defaut, disponibles, configuration)[0]


LOCALE_C = ("c", "posix")


def langue_et_origine(argv=None, variable_programme="", defaut="fr", disponibles=("en", "fr"), configuration=""):
    """(langue, origine) : la langue d'affichage et CE QUI l'a décidée (affiché dans « Options : --lang xx (origine) »). Ordre : --lang=xx / --lang xx,
    NGINX_TOOLS_LANG (langue imposée à tous les outils), la variable du programme (ex. WEB_MONITOR_LANG), l'option LANGUAGE du fichier de configuration
    (« auto » ou vide = suivre l'environnement), puis l'environnement comme gettext (1.17) : la variable GNU LANGUAGE (liste « fr_CA:fr:en », la première
    langue disponible) sauf si la locale est « C » / « POSIX », puis LC_ALL, LC_MESSAGES, LANG (la première définie et non vide l'emporte : un LC_ALL
    oublié masque LANG — l'origine le dit). Une locale dont la langue a un catalogue (fr_CA -> fr) donne cette langue ; toute autre (« en_US », « C »,
    « POSIX »…) donne l'anglais ; aucune variable -> `defaut`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    for i, a in enumerate(argv):
        if a.startswith("--lang="):
            v = a.split("=", 1)[1]
        elif a == "--lang" and i + 1 < len(argv):
            v = argv[i + 1]
        else:
            continue
        if v.lower() in disponibles:
            return v.lower(), ""                          # la ligne de commande : rien à expliquer
    for nom, v in [("NGINX_TOOLS_LANG", os.environ.get("NGINX_TOOLS_LANG", ""))] + ([(variable_programme, os.environ.get(variable_programme, ""))] if variable_programme else []):
        if v.strip():
            return _code(v, disponibles) or "en", f"{nom}={v.strip()}"
    if configuration.strip() and configuration.strip().lower() != "auto":
        return _code(configuration, disponibles) or "en", f"LANGUAGE={configuration.strip()} du fichier de configuration"
    definies = [(n, os.environ.get(n, "").strip()) for n in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG") if os.environ.get(n, "").strip()]
    locale = next((v for n, v in definies if n != "LANGUAGE"), "")
    choix = None
    gnu = os.environ.get("LANGUAGE", "").strip()
    if gnu and re.split(r"[.@]", locale.lower())[0] not in LOCALE_C:
        for partie in gnu.split(":"):
            code = _code(partie, disponibles) if partie.strip() else None
            if code:
                choix = (code, "LANGUAGE", gnu)
                break
    if choix is None:
        for n, v in definies:
            if n != "LANGUAGE":
                choix = (_code(v, disponibles) or "en", n, v)
                break
    if choix is None:
        return defaut, "défaut (aucune variable LANGUAGE, LC_ALL, LC_MESSAGES ni LANG)"
    code, nom, valeur = choix
    ignorees = [f"{n}={v}" for n, v in definies if n != nom and (n != "LANGUAGE" or True) and
                ((_first_code(v, disponibles) if n == "LANGUAGE" else (_code(v, disponibles) or "en")) != code)]
    return code, f"{nom}={valeur}" + (f" ; {', '.join(ignorees)} ignorée(s)" if ignorees else "")


def _first_code(liste, disponibles):
    """Première langue disponible d'une liste GNU « fr_CA:fr:en » (None si aucune)."""
    return next((c for c in (_code(p, disponibles) for p in liste.split(":") if p.strip()) if c), None)


def _echappe(texte):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(m.group(1), m.group(0)), texte)


def echapper_po(texte):
    """Texte -> contenu d'une chaîne PO entre guillemets (\\ \" \n \t échappés)."""
    return texte.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def lire_po(chemin):
    """[(msgid, msgstr)] d'un fichier PO (chaînes multi-lignes, #  commentaires, entrée d'en-tête et entrées « #, fuzzy » ignorées). Fichier absent : []."""
    res, courant, champ, flou = [], {"msgid": None, "msgstr": None}, None, False

    def clore():
        nonlocal courant, flou
        if courant["msgid"] and courant["msgstr"] is not None and not flou:
            res.append((courant["msgid"], courant["msgstr"]))
        courant, flou = {"msgid": None, "msgstr": None}, False
    try:
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.rstrip("\n")
                if not ligne.strip():
                    clore()
                    champ = None
                elif ligne.startswith("#,"):
                    flou = flou or "fuzzy" in ligne
                elif ligne.startswith("#"):
                    continue
                elif ligne.startswith(("msgid ", "msgstr ")):
                    champ, _, reste = ligne.partition(" ")
                    if champ == "msgid" and courant["msgid"] is not None:
                        clore()
                    courant[champ] = _echappe(reste.strip()[1:-1])
                elif ligne.startswith('"') and champ in courant and courant[champ] is not None:
                    courant[champ] += _echappe(ligne.strip()[1:-1])
        clore()
    except OSError:
        return []
    return res


def lire_catalogue(chemin):
    """{français: traduction} d'un fichier PO ; msgstr vide (non traduit) ou identique au msgid (valable dans les deux langues) : ignoré (utilisé par les outils ; traducteur() garde les entrées identiques)."""
    return {fr: en for fr, en in lire_po(chemin) if fr and en and fr != en}


MOTS_FRANCAIS = re.compile(r"\b(?:le|la|les|des|du|une?|aucune?|pas|est|sont|avec|sans|pour|dans|sur|depuis|mais|nos|ses|cette|ont|été|ou|et|au|aux|par|plus|moins|déjà|vers|chez|listes?|lieux?|fichiers?|aucun|aucuns|désactivée?s?|couleurs?|taille|temps|adresses?|réseaux?|réseau|propriétaire|durée|plages?|requêtes?|nombre|lecture|connexions?|bloc|bannies?|banni|surveillées?|activés?|activée?)\b",
                           re.IGNORECASE)


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CHEMINS = re.compile(r"(?<!\w)/\S+|\S*[_$]\S*")        # chemins et URL (« /event/journee-portes-ouvertes-sur-linux »), noms de variables : des DONNÉES, pas des phrases françaises restées à traduire


class Traducteur:
    """Remplace les fragments français du catalogue, LIGNE PAR LIGNE (les plus longs d'abord ; un fragment qui commence ou finit par une lettre n'est
    remplacé qu'en mot entier : « banni » ne touche jamais « bannies »). Une ligne qui contient encore des mots français après remplacement (message
    absent du catalogue, ou venu d'un autre programme) est rendue INTACTE en français : jamais de phrase à moitié traduite. Variable
    NGINX_TOOLS_I18N_DEBUG=FICHIER : ces lignes restées en français y sont ajoutées (diagnostic des fragments manquants). Sans catalogue : texte inchangé."""
    def __init__(self, catalogue):
        self.table = dict(catalogue)
        for cle, valeur in list(self.table.items()):      # variantes automatiques : sans espaces finaux (texte « strip »é), première lettre en minuscule (« installer … » après « a) »)
            variantes = [(cle.rstrip(), valeur.rstrip())] if cle != cle.rstrip() and len(cle.rstrip()) >= 12 else []
            for k, v in [(cle, valeur)] + variantes:
                if k[:1].isupper() and k[1:2].islower() and v[:1].isupper() and v[1:2].islower():
                    variantes.append((k[0].lower() + k[1:], v[0].lower() + v[1:]))
            for k, v in variantes:
                self.table.setdefault(k, v)
        for cle, valeur in list(self.table.items()):      # étiquette à remplissage INTERNE (« IP les plus actives      : ») : la traduction garde la même largeur
            self.table[cle] = self._meme_largeur(cle, valeur)
        self.cles = sorted(self.table, key=lambda k: (-len(k), k))
        self.multi = [k for k in self.cles if "\n" in k]
        self.simples = [k for k in self.cles if "\n" not in k]
        self.motifs, self.cache = {}, {}
        self.langue = None          # code de la langue d'affichage (renseigné par traducteur()) : règles propres à la langue (_locale)

    def __bool__(self):
        return bool(self.table)

    @staticmethod
    def _meme_largeur(cle, valeur):
        """Fragment « étiquette + remplissage + deux-points » (ex. « IP les plus actives      : ») : le remplissage de la traduction est recalculé pour que
        le fragment garde sa largeur (les « : » restent alignés d'une ligne à l'autre) ; inchangé si la forme ne correspond pas ou si le texte ne tient pas."""
        forme = re.compile(r"^(\s*)(\S(?:.*?\S)?)( {2,})(:\s*)$")
        a, b = forme.match(cle), re.match(r"^(\s*)(\S(?:.*?\S)?)( *)(:\s*)$", valeur)
        if not a or not b or "\n" in cle:
            return valeur
        voulu = len(cle) - len(b.group(1)) - len(b.group(2)) - len(b.group(4))
        return valeur if voulu < 1 else b.group(1) + b.group(2) + " " * voulu + b.group(4)

    def _remplacer(self, texte, cles):
        """Remplacement en UN SEUL passage (alternance, fragments les plus longs d'abord) : un texte déjà traduit n'est jamais re-traduit par un fragment plus court."""
        motif = self.motifs.get(id(cles))
        if motif is None:
            morceaux = []
            for cle in cles:
                avant = r"(?<!\w)" if re.match(r"\w", cle[0]) else ""
                apres = r"(?!\w)" if re.match(r"\w", cle[-1]) else ""
                morceaux.append(avant + re.escape(cle) + apres)
            motif = self.motifs[id(cles)] = re.compile("(?:" + "|".join(morceaux) + ")(\ue000*)( {2,})?") if morceaux else False
        if not motif:
            return texte
        # Le plus long gagne même s'il commence plus loin : « , propriétaire du bloc d'adresses » (module) ne coupe plus « propriétaire du bloc d'adresses (org / réseau) » (programme)
        morceaux, pos, n = [], 0, len(texte)
        reste = 0          # écart de longueur d'un fragment NON suivi de remplissage (« Disque » + chemin) : absorbé par le prochain remplissage de la ligne (colonnes alignées)
        while pos <= n:
            m = motif.search(texte, pos)
            if m is None:
                break
            suivant = motif.search(texte, m.start() + 1)
            while suivant is not None and suivant.start() < m.end():
                if suivant.end() > m.end() and len(suivant.group(0)) > len(m.group(0)):
                    m = suivant
                suivant = motif.search(texte, suivant.start() + 1)
            entre, reste = self._compenser(texte[pos:m.start()], reste)
            morceaux.append(entre)
            substitue = self._substitution(m)
            if not m.group(2):
                reste += len(substitue) - len(m.group(0))
            morceaux.append(substitue)
            pos = max(m.end(), m.start() + 1) if m.end() == m.start() else m.end()
        morceaux.append(self._compenser(texte[pos:], reste)[0])
        return "".join(morceaux)

    @staticmethod
    def _compenser(segment, reste):
        """Premier remplissage (2 espaces ou plus) du segment : raccourci ou rallongé de `reste` (jamais sous 2 espaces) ; rend (segment, reste non absorbé)."""
        if not reste:
            return segment, 0
        m = re.search(r" {2,}", segment)
        if not m:
            return segment, reste
        nouveau = max(2, len(m.group(0)) - reste)
        return segment[:m.start()] + " " * nouveau + segment[m.end():], reste - (len(m.group(0)) - nouveau)

    def _substitution(self, m):
        """Traduction d'un fragment ; les espaces de remplissage qui le SUIVENT (colonnes alignées : « Manuels      3 ») absorbent la différence de longueur :
        les colonnes restent alignées. (Une étiquette alignée à droite se traduit avant le remplissage, dans le programme.)"""
        codes, apres = m.group(1) or "", m.group(2) or ""
        fragment = m.group(0)[:len(m.group(0)) - len(codes) - len(apres)]
        traduit = self.table[fragment]
        if apres and len(fragment) != len(traduit):
            apres = " " * max(1, len(apres) + len(fragment) - len(traduit))
        return traduit + codes + apres

    def _ligne(self, original, traduite):
        if self.langue != "fr" and traduite != original and MOTS_FRANCAIS.search(CHEMINS.sub(" ", traduite)):
            fichier = os.environ.get("NGINX_TOOLS_I18N_DEBUG")
            if fichier:
                try:
                    with open(fichier, "a", encoding="utf-8") as f:
                        f.write(original + "\n")
                except OSError:
                    pass
            return original
        return traduite

    def __call__(self, texte):
        if not self.table or not isinstance(texte, str) or len(texte) < 3:
            return texte
        res = self.cache.get(texte)
        if res is not None:
            return res
        codes = ANSI.findall(texte) if "\x1b" in texte else []
        if codes:                                           # codes de couleur : masqués pendant la traduction (sinon « \x1b[36mce serveur » n'est pas un mot entier), puis remis en place
            res = self._traduire(ANSI.sub("\ue000", texte))
            if res.count("\ue000") == len(codes):
                it = iter(codes)
                res = re.sub("\ue000", lambda _m: next(it), res)
            else:
                res = texte
        else:
            res = self._traduire(texte)
        if len(self.cache) < 5000:
            self.cache[texte] = res
        return res

    def _traduire(self, texte):
        entier = self._remplacer(texte, self.multi) if any(k in texte for k in self.multi) else texte
        lignes_o, lignes_t = texte.split("\n"), entier.split("\n")
        if len(lignes_o) != len(lignes_t):
            lignes_o = lignes_t = entier.split("\n")
        res = "\n".join(self._ligne(o, self._locale(self._remplacer(t, self.simples))) for o, t in zip(lignes_o, lignes_t))
        return res

    UNITES_EN = {"o": "B", "Ko": "KB", "Mo": "MB", "Go": "GB", "To": "TB"}

    def _locale(self, ligne):
        """Langue anglaise : unités (o, Ko, Mo, Go, To -> B, KB, MB, GB, TB) et virgule décimale (« 22,8 Mo » -> « 22.8 MB », « 0,68 · 0,65 » -> « 0.68 · 0.65 ») ; la largeur
        change au plus d'un caractère : l'espace de remplissage qui suit l'absorbe. Autre langue : inchangé."""
        if self.langue != "en":
            return ligne
        ligne = re.sub(r"(?<![\w.,])(\d+)(?:,(\d+))? (o|Ko|Mo|Go|To)(?![\w])",
                       lambda m: m.group(1) + ("." + m.group(2) if m.group(2) else "") + " " + self.UNITES_EN[m.group(3)], ligne)
        return re.sub(r"(?<![\w.,])(\d+),(\d{1,2})(?=\s*(?:·|%|\)|$)|\s+(?:\(|·))", r"\1.\2", ligne)


def traducteur(langue_choisie, dossier_programme, programme, supplementaires=()):
    """Traducteur du programme pour la langue choisie : langue du code -> aucun remplacement pour le programme ; autre langue -> catalogue lang/PROGRAMME.XX.po
    à côté du programme. Les modules partagés (_config, _i18n et `supplementaires`, ex. « _bbb » : lang/_bbb.XX.po) ont leurs messages en français : ils sont
    traduits dès que la langue choisie n'est pas leur langue source (le français, sauf un module écrit en anglais, voir langue_source), même si le programme, lui, est écrit en anglais."""
    source = langue_source(dossier_programme, programme)
    noms = (() if langue_choisie == source else (programme,)) + tuple(nom for nom in ("_config", "_i18n") + tuple(supplementaires)
                                                                       if langue_choisie != langue_source(dossier_programme, nom))
    if not noms:
        return Traducteur({})
    catalogue = {}
    for nom in noms:
        for fr, traduit in lire_po(os.path.join(dossier_programme, "lang", f"{nom}.{langue_choisie}.po")):
            if fr and traduit:                           # msgstr vide : non traduit ; identique au msgid : valable dans les deux langues, MAIS il compte (il masque la traduction d'un module)
                catalogue.setdefault(fr, traduit)        # le catalogue du programme l'emporte sur ceux des modules affichés (même fragment, autre traduction)
    if langue_choisie == source and catalogue:
        # Programme écrit dans la langue choisie : ses propres mots ne doivent pas être « retraduits » par un fragment d'un catalogue de module écrit dans une autre
        # langue (ex. le « journal » anglais du programme ne devient pas « log » à cause de la clé française « journal »). Les clés dont le texte figure dans les
        # messages du programme sont donc ignorées (les clés identiques à leur traduction, qui masquent une traduction, restent).
        propres = []
        for chemin in glob.glob(os.path.join(dossier_programme, "lang", f"{programme}.*.po")):
            if chemin.endswith(f".{source}.po"):         # 1.15: old catalog of the time the program was written in the other language (residual file): its msgids are NOT the program's words
                continue
            propres += [msgid for msgid, _ in lire_po(chemin)]
        texte_propre = "\n".join(propres)
        if texte_propre:
            catalogue = {fr: tr for fr, tr in catalogue.items()
                         if fr == tr or len(fr.strip()) < 3 or not re.search(r"(?<!\w)" + re.escape(fr.strip()) + r"(?!\w)", texte_propre)}
    t = Traducteur(catalogue)
    t.langue = langue_choisie
    return t


# ------------------------------------------------------------------------------------------------------------------
# Contexte commun des programmes Python : langue, fichiers de configuration, print / input traduits, analyseur de la ligne de commande
# ------------------------------------------------------------------------------------------------------------------
class AideTriee(argparse.HelpFormatter):
    """Options de l'aide par ORDRE ALPHABÉTIQUE (nom long, sans les tirets : « -h, --help » se range à « help »), dans la liste comme dans la ligne « usage »."""
    @staticmethod
    def _cle(action):
        noms = action.option_strings or [action.dest]
        return noms[-1].lstrip("-").lower()

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions if groups else sorted(actions, key=self._cle), groups, prefix)

    def add_arguments(self, actions):
        return super().add_arguments(sorted(actions, key=self._cle))


def config_explicite(argv):
    """-c FICHIER / --config FICHIER / --config=FICHIER de la ligne de commande (lu avant argparse : la langue en dépend), ou None."""
    for i, a in enumerate(argv):
        if a.startswith("--config="):
            return a.split("=", 1)[1]
        if a in ("-c", "--config") and i + 1 < len(argv):
            return argv[i + 1]
    return None


def _module_voisin(nom):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(os.path.dirname(os.path.abspath(__file__)), nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Contexte:
    """Résultat de demarrer() : .langue, .tr (traducteur), .disponibles, .config ({CLÉ: valeur}), .fichiers (lus), .explicite (-c), .print, .input, .parser(),
    .defauts(), .afficher_configuration()."""
    def __init__(self, dossier, programme, variable, supplementaires=(), argv=None):
        self.programme, self.argv = programme, list(sys.argv[1:] if argv is None else argv)
        self.explicite = config_explicite(self.argv)
        self.config, self.fichiers = {}, []
        try:
            self.config, self.fichiers = _module_voisin("_config").lire(programme, self.explicite)
        except Exception:
            pass
        self.disponibles = langues_disponibles(dossier, programme)
        self.langue, self.origine_langue = langue_et_origine(self.argv, variable, disponibles=self.disponibles, configuration=self.config.get("LANGUAGE", ""))
        self.tr = traducteur(self.langue, dossier, programme, supplementaires)
        self._print, self._input = print, input
        if argv is None:                                  # exécution réelle du programme (pas une analyse d'arguments d'un autre) : --anonymize relance derrière le filtre
            try:
                anonymiser = _module_voisin("_anonymiser")
            except Exception:
                anonymiser = None
            if anonymiser is not None:
                anonymiser.relancer_si_demande(self.argv, self.config)

    def print(self, *a, **k):
        self._print(*(self.tr(x) if isinstance(x, str) else x for x in a), **k)

    def input(self, invite=""):
        return self._input(self.tr(invite))

    def parser(self, **kwargs):
        """argparse dans la langue d'affichage : description et aides traduites ; en français, messages d'erreur et titres traduits aussi."""
        return _analyseur(self)(**kwargs)

    def defauts(self, parser, schema):
        """Applique le fichier de configuration comme valeurs par défaut des options ({CLÉ: (option, type)}) ; ({option: valeur}, [problèmes])."""
        try:
            defauts, problemes = _module_voisin("_config").defauts_options(self.config, schema)
            parser.set_defaults(**defauts)
            return defauts, problemes
        except Exception as e:
            return {}, [f"apps/_config.py illisible ({e})"]

    def oui_non(self, valeur):
        return ("yes" if valeur else "no") if self.langue != "fr" else ("oui" if valeur else "non")

    def options_importantes(self, defauts):
        """Résumé « --lang fr · --days 7 · … » des valeurs venant du fichier de configuration."""
        return " · ".join([f"--lang {self.langue} ({getattr(self, 'origine_langue', '')})" if getattr(self, "origine_langue", "") else f"--lang {self.langue}"] + [f"--{o.replace('_', '-')} {self.oui_non(v) if isinstance(v, bool) else v}" for o, v in sorted(defauts.items())])

    def afficher_configuration(self, defauts, problemes, sortie=None):
        """Deux lignes de départ : QUEL(S) fichier(s) de configuration ont été lus, et les options importantes qui en résultent (langue comprise)."""
        sortie = sortie or self.print
        if os.environ.get("NGINX_TOOLS_CONFIG_VUE"):          # déjà affichée par le programme appelant : pas de répétition dans les sorties qu'il analyse
            return
        os.environ["NGINX_TOOLS_CONFIG_VUE"] = "1"
        try:
            sortie(_module_voisin("_config").ligne_configuration(self.fichiers, self.explicite, self.programme))
        except Exception:
            return
        sortie("  Options : " + self.options_importantes(defauts) + " (ligne de commande prioritaire)")
        for p in problemes:
            self.print(f"  ATTENTION : valeur de configuration ignorée : {p}", file=sys.stderr)


def _analyseur(ctx):
    class ArgumentParserLocalise(argparse.ArgumentParser):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("formatter_class", AideTriee)             # options par ordre alphabétique
            if kwargs.get("description"):
                kwargs["description"] = ctx.tr(kwargs["description"])
            super().__init__(*args, **kwargs)
            if "--anonymize" not in self._option_string_actions:
                self.add_argument("--anonymize", action="store_true", help="Anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE")

        def add_argument(self, *args, **kwargs):
            if isinstance(kwargs.get("help"), str):
                kwargs["help"] = ctx.tr(kwargs["help"])
            return super().add_argument(*args, **kwargs)

        def error(self, message):
            message = ctx.tr(message)
            if ctx.langue == "fr":
                message = re.sub(r"^the following arguments are required: (.+)$", r"argument(s) requis manquant(s) : \1", message)
                message = re.sub(r"^unrecognized arguments: (.+)$", r"argument(s) non reconnu(s) : \1", message)
                message = re.sub(r"^argument (\S+): invalid int value: (.+)$", r"argument \1 : entier invalide : \2", message)
                message = message.replace("invalid choice:", "valeur invalide :").replace("(choose from", "(choix possibles :").replace("expected one argument", "une valeur est attendue")
            self.print_usage(sys.stderr)
            self.exit(2, f"{self.prog} : erreur : {message}\n" if ctx.langue == "fr" else f"{self.prog}: error: {message}\n")

        def format_usage(self):
            return super().format_usage().replace("usage: ", "usage : ", 1) if ctx.langue == "fr" else super().format_usage()

        def format_help(self):
            texte = super().format_help()
            if ctx.langue != "fr":
                return texte
            return (texte.replace("usage: ", "usage : ", 1).replace("\noptions:\n", "\noptions :\n").replace("\npositional arguments:\n", "\narguments :\n")
                    .replace("show this help message and exit", "affiche cette aide et quitte").replace("show program's version number and exit", "affiche la version et quitte"))
    return ArgumentParserLocalise


QUESTION_CTRL_C = "Interrompre le programme ? [o/N] "
REPRISE_CTRL_C = "  Reprise."
REPONSES_OUI = ("o", "oui", "y", "yes")


def _lire_reponse_terminal():
    """Une ligne lue au terminal SANS input() : si Ctrl+C arrive pendant un input() qui utilise readline (import readline), un second input() lève
    « RuntimeError: can't re-enter readline ». Le terminal est remis en mode ligne (écho, retour arrière) le temps de la réponse, puis dans son état d'avant
    (celui que readline attend pour reprendre). EOFError à la fin de fichier."""
    try:
        import termios
        fd = sys.stdin.fileno()
        ancien = termios.tcgetattr(fd)
    except Exception:                                  # pas de termios (ou stdin sans descripteur) : lecture simple
        termios, fd, ancien = None, None, None
    if ancien is not None:
        nouveau = list(ancien)
        nouveau[3] |= termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG
        nouveau[0] |= termios.ICRNL
        termios.tcsetattr(fd, termios.TCSADRAIN, nouveau)
    try:
        ligne = sys.stdin.readline()
    finally:
        if ancien is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, ancien)
    if ligne == "":
        raise EOFError
    return ligne


@contextlib.contextmanager
def foreground_child():
    """While a child program runs IN THE FOREGROUND of the terminal (it reads the keyboard, asks its own questions): Ctrl+C belongs to the child, which asks its own
    confirmation (bash: ctrl_c_installer, Python: installer_confirmation_ctrl_c). The parent gets the same signal (same process group): a neutral handler here,
    so that two « Interrupt the program? » questions never compete for the terminal (1.16). A Python handler, NOT SIG_IGN: an ignored signal stays ignored after
    exec, and the child could no longer be interrupted at all. The parent's handler is put back afterwards. Not the main thread: nothing changes."""
    import signal
    try:
        old = signal.signal(signal.SIGINT, lambda *_: None)
    except ValueError:
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, old)


def run_foreground(cmd, **kwargs):
    """subprocess.run(cmd) of a program that owns the terminal, inside foreground_child(); its CompletedProcess."""
    import subprocess
    with foreground_child():
        return subprocess.run(cmd, **kwargs)


def installer_confirmation_ctrl_c(tr=None):
    """Ctrl+C demande TOUJOURS confirmation avant de quitter (« Interrompre le programme ? [o/N] ») : oui / o / y -> KeyboardInterrupt habituel ; autre réponse -> reprise là où
    le programme en était ; un second Ctrl+C (ou la fin de fichier) pendant la question vaut oui. Sans effet hors terminal interactif (cron, tuyau, tests) et si
    NGINX_TOOLS_CTRL_C=0. Retourne True si le gestionnaire est installé."""
    import signal
    if os.environ.get("NGINX_TOOLS_CTRL_C") == "0":
        return False
    try:
        if not (sys.stdin.isatty() and sys.stderr.isatty()):
            return False
    except (AttributeError, ValueError):
        return False
    tr = tr or (lambda texte: texte)
    etat = {"question": False}

    def gestionnaire(numero, cadre):
        if etat["question"]:                           # Ctrl+C pendant la question : confirmé
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            raise KeyboardInterrupt
        etat["question"] = True
        try:
            sys.stderr.write("\r\n" + tr(QUESTION_CTRL_C))
            sys.stderr.flush()
            try:
                reponse = _lire_reponse_terminal()     # pas input() : « can't re-enter readline » si Ctrl+C arrive pendant un input()
                confirme = reponse.strip().lower() in REPONSES_OUI
            except EOFError:                           # fin de fichier : oui
                confirme = True
        finally:
            etat["question"] = False
        if confirme:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            raise KeyboardInterrupt
        sys.stderr.write(tr(REPRISE_CTRL_C) + "\n")
        sys.stderr.flush()

    try:
        signal.signal(signal.SIGINT, gestionnaire)
    except ValueError:                                 # pas le fil principal
        return False
    return True


def demarrer(dossier, programme, variable="", supplementaires=(), argv=None, confirmer_ctrl_c=True):
    """Point d'entrée des programmes : Contexte (langue, configuration, print/input traduits, analyseur argparse) ; installe aussi la confirmation de Ctrl+C."""
    ctx = Contexte(dossier, programme, variable, supplementaires, argv)
    if confirmer_ctrl_c:
        installer_confirmation_ctrl_c(ctx.tr)
    return ctx
