"""Extraction des messages français d'un programme bash (ce que le catalogue PO doit couvrir) : morceaux de texte des chaînes entre guillemets, des chaînes entre apostrophes
et des documents « ici » (<<TAG), coupés aux expansions ($var, ${…}, $(…)), aux séquences de couleur et aux directives de printf — comme les morceaux de phrase que le
traducteur voit à l'exécution (apps/_i18n.py)."""
import re

from i18n_tools import MARQUES_FR

MARQUES_SH = re.compile(r"\b(environnements?|modules?|retenus?|programmes?|section|étape|étapes)\b", re.IGNORECASE)      # mots français sans accent propres aux programmes bash
DIRECTIVE_PRINTF = re.compile(r"%[-0-9.*]*[sdiufxXoceEgG]")
COUPURES = re.compile(r"\\033\[[0-9;]*m|\\x1b\[[0-9;]*m|\\e\[[0-9;]*m|\\[nrt]|\x1b\[[0-9;]*m|" + DIRECTIVE_PRINTF.pattern)


def _decouper(texte):
    """Morceaux de texte entre séquences de couleur, retours à la ligne échappés et directives printf."""
    return COUPURES.split(texte)


def _fin_accolades(t, i):
    """Index de l'accolade fermante de ${…} dont l'ouverture est en i (t[i] == '{')."""
    prof = 0
    while i < len(t):
        if t[i] == "\\":
            i += 2
            continue
        if t[i] == "{":
            prof += 1
        elif t[i] == "}":
            prof -= 1
            if prof == 0:
                return i
        i += 1
    return len(t) - 1


def _fin_parentheses(t, i):
    """Index de la parenthèse fermante de $(…) dont l'ouverture est en i (t[i] == '(')."""
    prof = 0
    while i < len(t):
        c = t[i]
        if c == "\\":
            i += 2
            continue
        if c in "\"'":
            i = _fin_chaine(t, i)
            continue
        if c == "(":
            prof += 1
        elif c == ")":
            prof -= 1
            if prof == 0:
                return i
        i += 1
    return len(t) - 1


def _fin_chaine(t, i):
    """Index qui suit la chaîne ('…' ou "…") ouverte en i."""
    q = t[i]
    i += 1
    while i < len(t):
        if q == '"' and t[i] == "\\":
            i += 2
            continue
        if q == '"' and t[i] == "$" and i + 1 < len(t) and t[i + 1] == "(":
            i = _fin_parentheses(t, i + 1) + 1
            continue
        if q == '"' and t[i] == "$" and i + 1 < len(t) and t[i + 1] == "{":
            i = _fin_accolades(t, i + 1) + 1
            continue
        if t[i] == q:
            return i + 1
        i += 1
    return len(t)


OPERATEUR_DEFAUT = re.compile(r"^[#!]?[A-Za-z_0-9@*]*(?:\[[^\]]*\])?:?[-+=?](.+)$", re.S)


def _mot_defaut(interieur, ligne, res):
    """Texte par défaut d'une expansion ${variable:-texte} (ou :+ := :?) : c'est un message qui s'affichera, comme une chaîne entre guillemets."""
    m = OPERATEUR_DEFAUT.match(interieur)
    if m and not m.group(1).startswith(("#", "%")):
        _guillemets('"' + m.group(1).replace('"', '\\"') + '"', 0, [ligne], res)


def _guillemets(t, i, ligne, res):
    """Chaîne "…" ouverte en i : ajoute ses morceaux littéraux ; retourne l'index qui suit."""
    i += 1
    morceau = []
    n = len(t)

    def vider():
        if morceau:
            texte = "".join(morceau)
            morceau.clear()
            for p in _decouper(texte):
                res.append((p, ligne[0]))
    while i < n and t[i] != '"':
        c = t[i]
        if c == "\n":
            ligne[0] += 1
        if c == "\\" and i + 1 < n:
            suivant = t[i + 1]
            if suivant in '"\\$`':
                morceau.append(suivant)
            elif suivant == "\n":
                ligne[0] += 1
            else:
                morceau.append(c + suivant)
            i += 2
            continue
        if c == "$" and i + 1 < n and t[i + 1] == "{":
            vider()
            fin = _fin_accolades(t, i + 1)
            _mot_defaut(t[i + 2:fin], ligne[0], res)
            ligne[0] += t.count("\n", i, fin)
            i = fin + 1
            continue
        if c == "$" and i + 1 < n and t[i + 1] == "(":
            vider()
            fin = _fin_parentheses(t, i + 1)
            interieur = t[i + 2:fin].lstrip("(")
            res.extend(_extraire(interieur, ligne[0]))
            ligne[0] += t.count("\n", i, fin)
            i = fin + 1
            continue
        if c == "$" and i + 1 < n and re.match(r"[A-Za-z_0-9@*#?!$-]", t[i + 1]):
            vider()
            m = re.match(r"\$([A-Za-z_][A-Za-z_0-9]*|[0-9@*#?!$-])", t[i:])
            i += len(m.group(0)) if m else 2
            continue
        if c == "`":
            vider()
            fin = t.find("`", i + 1)
            fin = n - 1 if fin < 0 else fin
            res.extend(_extraire(t[i + 1:fin], ligne[0]))
            i = fin + 1
            continue
        morceau.append(c)
        i += 1
    vider()
    return i + 1


def _extraire(t, ligne0=1):
    """[(morceau, ligne)] de tout le code bash `t`."""
    res, n, i = [], len(t), 0
    ligne = [ligne0]
    heredocs = []                          # (étiquette, entre guillemets, avec tabulations) en attente du prochain retour à la ligne
    while i < n:
        c = t[i]
        if c == "\n":
            ligne[0] += 1
            i += 1
            for etiquette, litteral, tabs in heredocs:
                debut = i
                while i < n:
                    fin = t.find("\n", i)
                    fin = n if fin < 0 else fin
                    brut = t[i:fin]
                    if (brut.lstrip("\t") if tabs else brut) == etiquette:
                        break
                    i = fin + 1
                corps = t[debut:i]
                if litteral:
                    for p in _decouper(corps):
                        res.append((p, ligne[0]))
                else:
                    sous = []
                    _guillemets('"' + corps.replace('"', '\\"') + '"', 0, [ligne[0]], sous)
                    res.extend(sous)
                ligne[0] += corps.count("\n")
                fin = t.find("\n", i)
                i = n if fin < 0 else fin
            heredocs = []
            continue
        if c == "#" and (i == 0 or t[i - 1] in " \t\n;|&()"):
            fin = t.find("\n", i)
            i = n if fin < 0 else fin
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "<" and t.startswith("<<<", i):
            i += 3
            continue
        if c == "<" and t.startswith("<<", i) and not t.startswith("<<(", i):
            m = re.match(r"<<(-?)\s*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][A-Za-z_0-9]*))", t[i:])
            if m:
                heredocs.append((m.group(2) or m.group(3) or m.group(4), bool(m.group(2) or m.group(3) or t[i + m.end(0) - len(m.group(4) or "") - 1:i + m.end(0)].startswith("\\")), bool(m.group(1))))
                i += m.end(0)
                continue
        if c == "$" and t.startswith("$'", i):
            fin = i + 2
            while fin < n and t[fin] != "'":
                fin += 2 if t[fin] == "\\" else 1
            for p in _decouper(t[i + 2:fin]):
                res.append((p, ligne[0]))
            ligne[0] += t.count("\n", i, fin)
            i = fin + 1
            continue
        if c == "$" and i + 1 < n and t[i + 1] in "({":
            fin = _fin_parentheses(t, i + 1) if t[i + 1] == "(" else _fin_accolades(t, i + 1)
            if t[i + 1] == "(":
                res.extend(_extraire(t[i + 2:fin], ligne[0]))
            ligne[0] += t.count("\n", i, fin)
            i = fin + 1
            continue
        if c == "'":
            fin = t.find("'", i + 1)
            fin = n if fin < 0 else fin
            interieur = t[i + 1:fin]
            if '"' in interieur:                  # code entre apostrophes (trap, awk, sed…) : ses chaînes "…" sont des messages
                res.extend(_extraire(interieur, ligne[0]))
            else:
                for p in _decouper(interieur):
                    res.append((p, ligne[0]))
            ligne[0] += t.count("\n", i, fin)
            i = fin + 1
            continue
        if c == '"':
            i = _guillemets(t, i, ligne, res)
            continue
        i += 1
    return res


def messages_francais_sh(chemin):
    """{texte: ligne} des morceaux de texte français d'un programme bash. Le filtre de sortie (apps/_traduire.py) traduit ligne par ligne : un texte sur plusieurs lignes
    (aide, modèle de fichier) est donc compté ligne par ligne. Le code d'autres langages (python embarqué) n'est pas un message."""
    res = {}
    source = open(chemin, encoding="utf-8").read()
    if "/^# Usage :/,/^# HISTORIQUE/p" in source:                 # aide affichée depuis le bloc de commentaires de l'en-tête (sed -n '/^# Usage :/,/^# HISTORIQUE/p')
        debut, fin = source.index("\n# Usage :"), source.index("\n# HISTORIQUE")
        for k, brut in enumerate(source[debut + 1:fin].split("\n")):
            partie = re.sub(r"^# ?", "", brut)
            if len(partie.strip()) >= 4:                                   # tout le bloc d'aide : chaque ligne est affichée
                res.setdefault(partie, source[:debut + 1].count("\n") + 1 + k)
    for texte, ligne in _extraire(source):
        if re.match(r"\s*(import |#!)", texte) or "sys.argv" in texte:
            continue
        for k, partie in enumerate(texte.split("\n")):
            if len(partie.strip()) >= 4 and (MARQUES_FR.search(partie) or MARQUES_SH.search(partie)):
                res.setdefault(partie, ligne + k)
    return res
