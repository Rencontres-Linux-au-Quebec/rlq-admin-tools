# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
# Licence : GNU Affero General Public License, version 3 ou ultérieure — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Données d'exemple FICTIVES de la suite (run-all.sh 1.188) : personnes, courriels, événements, lieux et organisations, en français (accents,
traits d'union, apostrophes) et en anglais, plus les cas qui décalent les colonnes d'un terminal : accent COMBINANT (forme NFD : 2 caractères Python,
1 colonne), caractères chinois (1 caractère, 2 colonnes). Aucune personne réelle : noms inventés, domaines exemple.org / example.com (réservés),
adresses IP de documentation (RFC 5737) ou des blocs du DoD américain (11.x, jamais attribués à un particulier) quand une adresse PUBLIQUE est requise."""
import unicodedata

PERSONNES_FR = ["Hélène Côté", "François Lévesque", "Zoé Bérubé", "Gaëtan Brûlé", "Noël Ouellet-Béliveau", "Ève D'Aragon"]
PERSONNES_EN = ["John Smith", "Mary O'Brien", "Christopher Whitfield"]
PERSONNE_NFD = unicodedata.normalize("NFD", "Renée Gagné")         # « e » + accent combinant : len() = 13, largeur = 11
PERSONNE_CJK = "张三李四"                                            # « Zhang San, Li Si » (Monsieur Tout-le-monde) : 4 caractères, 8 colonnes
PERSONNES = PERSONNES_FR + PERSONNES_EN + [PERSONNE_NFD, PERSONNE_CJK]


def courriel(nom):
    """« Hélène Côté » -> « helene.cote@exemple.org » (sans accents, sans apostrophe)."""
    simple = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    return ".".join(m for m in simple.replace("'", "").replace("-", " ").split()) + "@exemple.org"


COMPTES = [(100 + i, courriel(n) if ord(n[0]) < 0x3000 else "zhang.san@exemple.org", n) for i, n in enumerate(PERSONNES)]
EVENEMENTS_FR = ["Journée portes ouvertes Linux 2026", "Soirée « Libérez vos données »", "Atelier : réparer son ordinateur"]
EVENEMENTS_EN = ["Linux Open House 2026", "Free Software Evening", "Hands-on: repair your laptop"]
LIEUX_FR = ["Université du Québec à Montréal", "Bibliothèque Gabrielle-Roy", "Café des Écrivains"]
LIEUX_EN = ["Public Library", "Community Center", "Maker Space"]
ORGANISATIONS = ["Vidéotron ltée", "Télébec", "Example Networks Inc.", "Réseau d'exemple"]
# Adresses : documentation (privées pour Python : jamais recherchées) et publiques fictives (blocs du DoD, recherchées comme une vraie adresse)
IP_DOC = ["192.0.2.10", "198.51.100.20", "203.0.113.30"]
IP_PUBLIQUES = ["11.5.88.10", "11.9.16.20", "11.13.216.30", "11.17.240.40"]


def largeur(texte):
    """Colonnes d'un terminal : accent combinant 0, caractère chinois 2, autre 1 (même règle que les programmes)."""
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in texte)


def bornes(ligne, separateur="|"):
    """Colonnes d'écran où se trouve chaque `separateur` de la ligne (tableaux encadrés)."""
    return [largeur(ligne[:i]) for i, c in enumerate(ligne) if c == separateur]


def debuts_de_colonnes(ligne):
    """Colonnes d'écran où commence chaque cellule d'une ligne de tableau sans cadre (cellules séparées par 2 espaces ou plus)."""
    res, i, n = [], 0, len(ligne)
    while i < n:
        if ligne[i] != " " and (i == 0 or ligne[i - 1] == " " and (i < 2 or ligne[i - 2] == " ")):
            res.append(largeur(ligne[:i]))
        i += 1
    return res
