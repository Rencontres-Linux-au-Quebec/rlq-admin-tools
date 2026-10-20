"""Outils des tests de traduction : extraction des messages français d'un programme Python (ce que le catalogue PO doit couvrir)."""
import ast
import importlib.util
import os
import re

from helpers import SCRIPTS_DIR

# Un texte est « français » s'il contient une lettre accentuée / un signe typographique français, ou un mot courant du vocabulaire des programmes.
MARQUES_FR = re.compile(r"[àâçéèêëîïôûùüœÀÉÈÊ«»…→—]|\b(le|la|les|des|du|de|un|une|aucun|aucune|pas|est|sont|avec|sans|pour|dans|sur|ou|et|depuis|erreur|adresse|fichier"
                        r"|fichiers|connexion|jours|par|ce|cette|trop|déjà|plus|moins|lancé|affiche|liste|lue|lus|lu|langue|options?|valeurs?|ignorée?s?|demandé|cherchés?"
                        r"|configuration|défaut|introuvable|inconnue?|absente?s?|présente?s?|requêtes?|ligne|lignes|nom|noms|mot|passage|rapport|journal|journaux"
                        r"|vérification|vérifier|échec|réussi|sauvegarde|serveur|courriel|envoyé|trouvé|attendu|valide|invalide|en|attente|envoi|envois|envoyés|courriels|titre|titres|tous|toutes|heures|fois|nombre|mois|jour|semaine|quel|quelle|mais|aussi|ici|oui|non|quitter|continuer|encore|aucune|tout|toute|toutes)\b", re.IGNORECASE)
FONCTIONS_REGEX = {"compile", "search", "match", "sub", "findall", "fullmatch", "split", "finditer", "startswith", "endswith"}


def charger_i18n():
    spec = importlib.util.spec_from_file_location("_i18n_test", os.path.join(SCRIPTS_DIR, "apps", "_i18n.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def messages_francais(chemin):
    """{texte: ligne} : constantes de texte français d'un programme Python (hors docstrings et expressions régulières) — ce que le catalogue doit couvrir."""
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    parents = {c: n for n in ast.walk(arbre) for c in ast.iter_child_nodes(n)}
    docstrings = {n.body[0].value for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
    res = {}
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)) or n in docstrings:
            continue
        v = n.value
        if len(v.strip()) < 4 or not MARQUES_FR.search(v):
            continue
        p = parents.get(n)
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute) and p.func.attr in FONCTIONS_REGEX:
            continue
        res.setdefault(v, n.lineno)
    return res


def lire_po_brut(chemin):
    """[(msgid, msgstr)] du catalogue PO, y compris les entrées identiques."""
    return charger_i18n().lire_po(chemin)


def manquants(programme, catalogue):
    """[(ligne, texte)] des messages du programme sans entrée traduite dans le catalogue PO."""
    connus = {fr for fr, en in lire_po_brut(catalogue) if en}
    return [(l, v) for v, l in sorted(messages_francais(programme).items(), key=lambda x: x[1]) if v not in connus]
