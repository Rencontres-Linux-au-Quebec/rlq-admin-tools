#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# yunohost-check.sh : tests fonctionnels des applications YunoHost (interne depuis le serveur, externe depuis Internet).
#   --list (sur le serveur)     : écrit la liste des applications (domaine et chemin, sans secret) dans un fichier TSV.
#   --internal (défaut, serveur): chaque application est jointe en HTTPS sur 127.0.0.1, avec son nom de domaine.
#   --external (autre machine)  : chaque application est jointe par son nom public, depuis Internet (--targets FICHIER).
# Lecture seule : aucune donnée n'est envoyée, aucun formulaire n'est soumis, aucune connexion n'est tentée.
# ========================================================================================================================
SCRIPT_VERSION="0.1.20261125.182600"
SCRIPT_NAME="yunohost-check"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"

# Configuration : /etc/default/yunohost-check.conf puis ~/.yunohost-check.conf (le dernier lu l'emporte ; la ligne de commande l'emporte sur les deux).
CONF_SYSTEME="/etc/default/$SCRIPT_NAME.conf"
CONF_UTILISATEUR="${HOME:-/root}/.$SCRIPT_NAME.conf"
TIMEOUT=15                                   # secondes par requête (clé TIMEOUT)
EXPECT_CODES="200 204 301 302 303 307 308 401 403"   # codes HTTP acceptés comme « vivant » (clé EXPECT_CODES)
CERT_ALERT_DAYS=14
CONF_LUES=()

lire_config() {
    local f
    for f in "$CONF_SYSTEME" "$CONF_UTILISATEUR"; do
        [[ -r "$f" ]] || continue
        CONF_LUES+=("$f")
        while IFS= read -r ligne || [[ -n "$ligne" ]]; do
            case "$ligne" in
                TIMEOUT=*) TIMEOUT="${ligne#TIMEOUT=}" ;;
                EXPECT_CODES=*) EXPECT_CODES="${ligne#EXPECT_CODES=}" ;;
                CERT_ALERT_DAYS=*) CERT_ALERT_DAYS="${ligne#CERT_ALERT_DAYS=}" ;;
            esac
        done < "$f"
    done
    TIMEOUT="${TIMEOUT//[!0-9]/}"; TIMEOUT="${TIMEOUT:-15}"
    CERT_ALERT_DAYS="${CERT_ALERT_DAYS//[!0-9]/}"; CERT_ALERT_DAYS="${CERT_ALERT_DAYS:-14}"
}

# Couleurs : désactivées si la sortie est redirigée ou si NO_COLOR est défini.
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_OK=$'\e[32m'; C_SKIP=$'\e[33m'; C_FAIL=$'\e[31m'; C_NUM=$'\e[36m'; C_RESET=$'\e[0m'
else
    C_OK=""; C_SKIP=""; C_FAIL=""; C_NUM=""; C_RESET=""
fi

OPT_MODE="internal"
OPT_TARGETS=""
OPT_LIST_FILE=""
OPT_SAVE=""
OPT_COMPARE=""
CODE_OBTENU=""
OPT_REPORT_ERR=0
COMPTE_OK=0; COMPTE_SKIP=0; COMPTE_FAIL=0

ok()    { echo "  ${C_OK}[OK]${C_RESET}   $1"; COMPTE_OK=$((COMPTE_OK+1)); }
skip()  { echo "  ${C_SKIP}[SKIP]${C_RESET} $1"; COMPTE_SKIP=$((COMPTE_SKIP+1)); }
fail()  { echo "  ${C_FAIL}[FAIL]${C_RESET} $1"; COMPTE_FAIL=$((COMPTE_FAIL+1)); }

afficher_aide() {
    cat <<AIDE
Usage : $SCRIPT_NAME.sh [OPTION]...
Tests fonctionnels des applications YunoHost. Par défaut : mode interne, sur le serveur.

Options (par ordre alphabétique) :
  --changelog                  affiche le journal des modifications de ce programme
  --compare FICHIER            compare les codes HTTP à ceux enregistrés par --save ; signale les changements
  --external                   mode externe : joint les applications par leur nom public (avec --targets)
  --help                       affiche cette aide
  --internal                   mode interne : joint les applications sur 127.0.0.1 avec leur nom de domaine (défaut)
  --list FICHIER               écrit la liste des applications (TSV : nom, id, domaine, chemin) puis quitte
  --report-err                 ajoute en fin d'exécution un sommaire à copier-coller pour un diagnostic
  --save FICHIER               enregistre le code HTTP de chaque cible (base de comparaison, écrasée)
  --targets FICHIER            liste TSV (domaine, chemin) pour --external (produite par --list)
  --timeout N                  délai par requête en secondes (défaut : $TIMEOUT ; clé TIMEOUT)
  --version                    affiche la version du programme

Configuration lue : ${CONF_SYSTEME} puis ${CONF_UTILISATEUR} (le dernier l'emporte ; la ligne de commande l'emporte sur les deux).
  TIMEOUT          délai par requête (secondes)
  EXPECT_CODES     codes HTTP considérés comme vivants (liste séparée par des espaces)
  CERT_ALERT_DAYS  échec si le certificat expire dans moins de N jours (mode externe)

Codes de sortie : 0 tout est OK ; 1 au moins un échec ; 2 usage ou fichier illisible.
AIDE
}

afficher_changelog() {
    # Seule la section de ce programme, avec les numéros de version en couleur ; sans couleur si la sortie est redirigée.
    if [[ ! -r "$CHANGELOG_FILE" ]]; then echo "CHANGELOG.md introuvable : $CHANGELOG_FILE" >&2; return 2; fi
    awk -v nom="$SCRIPT_NAME.sh" '
        /^## / { dans = ($0 == "## " nom); next }
        dans { print }' "$CHANGELOG_FILE" | if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
            sed -E $'s/^(### )([0-9][0-9.]*)/\\1\e[36m\\2\e[0m/' 2>/dev/null || true
        else
            cat
        fi
    return 0
}

# --- Liste des applications (mode --list) : délégué à apps/_yunohost.py, qui ne lit que id, domain et path ---
lister_applications() {
    local sortie="$1"
    if ! command -v python3 >/dev/null 2>&1; then echo "ERREUR: python3 absent." >&2; return 2; fi
    if ! python3 "$SCRIPT_DIR/apps/_yunohost.py" > "$sortie.tmp" 2>/dev/null; then
        rm -f -- "$sortie.tmp"; echo "ERREUR: lecture des applications impossible." >&2; return 2
    fi
    mv -- "$sortie.tmp" "$sortie"
    echo "Liste écrite : $sortie ($(wc -l < "$sortie") application(s))."
    return 0
}

verifier_cible() {     # $1 domaine, $2 chemin, $3 mode (internal|external)
    local domaine="$1" chemin="${2:-/}" mode="$3" url code cert_fin jours
    [[ "$chemin" == /* ]] || chemin="/$chemin"
    url="https://$domaine$chemin"
    local -a opts=(-sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" -H "User-Agent: yunohost-check/$SCRIPT_VERSION")
    if [[ "$mode" == internal ]]; then
        opts+=(--resolve "$domaine:443:127.0.0.1")
    fi
    code=$(curl "${opts[@]}" "$url" 2>/dev/null) || code="000"
    CODE_OBTENU="$code"
    if [[ "$code" == "000" ]]; then
        fail "$url : aucune réponse HTTPS (délai ou connexion refusée)."
        return 0
    fi
    if [[ "$code" =~ ^5 ]]; then
        fail "$url : erreur serveur HTTP $code."
    elif [[ " $EXPECT_CODES " == *" $code "* ]]; then
        ok "$url : HTTP $code"
    else
        skip "$url : HTTP $code (code non attendu : voir EXPECT_CODES)."
    fi
    if [[ "$mode" == external ]]; then
        if ! command -v openssl >/dev/null 2>&1; then
            skip "$domaine : certificat non vérifié (openssl absent)."
            return 0
        fi
        cert_fin=$(echo | timeout "$TIMEOUT" openssl s_client -servername "$domaine" -connect "$domaine:443" 2>/dev/null \
                   | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
        if [[ -z "$cert_fin" ]]; then
            fail "$domaine : certificat illisible."
            return 0
        fi
        jours=$(( ( $(date -d "$cert_fin" +%s 2>/dev/null || echo 0) - $(date +%s) ) / 86400 ))
        if (( jours < CERT_ALERT_DAYS )); then
            fail "$domaine : certificat expire dans ${C_NUM}${jours}${C_RESET} jour(s) (seuil : $CERT_ALERT_DAYS)."
        else
            ok "$domaine : certificat valable encore ${C_NUM}${jours}${C_RESET} jour(s)."
        fi
    fi
    return 0
}

enregistrer_ou_comparer() {    # $1 domaine, $2 chemin : --save écrit le code ; --compare signale un changement par rapport au fichier
    local domaine="$1" chemin="$2" ancien=""
    if [[ -n "$OPT_SAVE" ]]; then
        printf '%s\t%s\t%s\n' "$domaine" "$chemin" "$CODE_OBTENU" >> "$OPT_SAVE" || fail "écriture impossible : $OPT_SAVE"
    fi
    if [[ -n "$OPT_COMPARE" ]]; then
        ancien=$(awk -F'\t' -v d="$domaine" -v c="$chemin" '$1==d && $2==c {v=$3} END {print v}' "$OPT_COMPARE")
        if [[ -z "$ancien" ]]; then
            skip "$domaine$chemin : aucune référence dans $OPT_COMPARE."
        elif [[ "$ancien" != "$CODE_OBTENU" ]]; then
            if [[ "$CODE_OBTENU" =~ ^5 || "$CODE_OBTENU" == "000" ]]; then
                fail "$domaine$chemin : régression, HTTP $ancien avant, $CODE_OBTENU maintenant."
            else
                skip "$domaine$chemin : changement, HTTP $ancien avant, $CODE_OBTENU maintenant."
            fi
        fi
    fi
}

executer_tests() {    # $1 mode, $2 fichier TSV (ou vide : mode interne, liste lue sur le serveur)
    local mode="$1" fichier="$2" tmp ligne domaine chemin nom
    local -a lignes=()
    if [[ -n "$fichier" ]]; then
        [[ -r "$fichier" ]] || { echo "ERREUR: fichier illisible : $fichier" >&2; return 2; }
        mapfile -t lignes < "$fichier"
    else
        tmp=$(mktemp) || return 2
        if ! python3 "$SCRIPT_DIR/apps/_yunohost.py" > "$tmp" 2>/dev/null; then
            rm -f -- "$tmp"; echo "ERREUR: lecture des applications impossible (YunoHost absent ?)." >&2; return 2
        fi
        mapfile -t lignes < "$tmp"; rm -f -- "$tmp"
    fi
    if (( ${#lignes[@]} == 0 )); then
        echo "Aucune application à tester."
        return 0
    fi
    for ligne in "${lignes[@]}"; do
        # Deux formats acceptés : « nom id domaine chemin » (sortie de --list) ou « domaine chemin ».
        local -a champs=()
        IFS=$'\t' read -r -a champs <<< "$ligne"
        if (( ${#champs[@]} == 2 )); then
            nom="${champs[0]}"; domaine="${champs[0]}"; chemin="${champs[1]}"
        else
            nom="${champs[0]:-}"; domaine="${champs[2]:-}"; chemin="${champs[3]:-}"
        fi
        if [[ -z "$domaine" ]]; then
            skip "${nom:-?} : pas de domaine lisible, non testé."
            continue
        fi
        echo "== ${nom}"
        verifier_cible "$domaine" "${chemin:-/}" "$mode"
        enregistrer_ou_comparer "$domaine" "${chemin:-/}"
    done
    return 0
}

sommaire_erreurs() {
    echo
    echo "--- Sommaire à copier-coller ($SCRIPT_NAME.sh $SCRIPT_VERSION, $(hostname 2>/dev/null || echo ?), $(date '+%Y-%m-%d %H:%M:%S')) ---"
    echo "mode=$OPT_MODE OK=$COMPTE_OK SKIP=$COMPTE_SKIP FAIL=$COMPTE_FAIL"
    echo "configuration : ${CONF_LUES[*]:-aucune}"
}

interruption() {
    local rep=""
    echo
    read -r -p "Interrompre les tests ? [o/N] " rep < /dev/tty 2>/dev/null || rep="n"
    [[ "$rep" =~ ^[oOyY]$ ]] && { echo "Interrompu."; exit 130; }
    echo "Reprise."
}
trap interruption INT

# --- Options ---
lire_config
while [[ $# -gt 0 ]]; do
    case "$1" in
        --changelog) afficher_changelog; exit $? ;;
        --external) OPT_MODE="external"; shift ;;
        --help|-h) afficher_aide; exit 0 ;;
        --internal) OPT_MODE="internal"; shift ;;
        --list) OPT_LIST_FILE="${2:-}"; shift 2 ;;
        --compare) OPT_COMPARE="${2:-}"; shift 2 ;;
        --report-err) OPT_REPORT_ERR=1; shift ;;
        --save) OPT_SAVE="${2:-}"; shift 2 ;;
        --targets) OPT_TARGETS="${2:-}"; shift 2 ;;
        --timeout) TIMEOUT="${2:-15}"; shift 2 ;;
        --version) echo "$SCRIPT_NAME.sh $SCRIPT_VERSION"; exit 0 ;;
        *) echo "Option inconnue : $1 (voir --help)" >&2; exit 2 ;;
    esac
done
TIMEOUT="${TIMEOUT//[!0-9]/}"; TIMEOUT="${TIMEOUT:-15}"

echo "$SCRIPT_NAME.sh $SCRIPT_VERSION"
if (( ${#CONF_LUES[@]} )); then
    echo "Configuration lue : ${CONF_LUES[*]}"
else
    echo "Configuration lue : aucune (valeurs par défaut)"
fi

if [[ -n "$OPT_LIST_FILE" ]]; then
    lister_applications "$OPT_LIST_FILE" || exit 2
    exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "ERREUR: curl absent (apt-get install curl)." >&2
    exit 2
fi

if [[ "$OPT_MODE" == external && -z "$OPT_TARGETS" ]]; then
    echo "ERREUR: --external demande --targets FICHIER (produit par --list sur le serveur)." >&2
    exit 2
fi

if [[ -n "$OPT_SAVE" ]]; then : > "$OPT_SAVE" || { echo "ERREUR: fichier non écrivable : $OPT_SAVE" >&2; exit 2; }; fi
if [[ -n "$OPT_COMPARE" && ! -r "$OPT_COMPARE" ]]; then echo "ERREUR: fichier de référence illisible : $OPT_COMPARE" >&2; exit 2; fi
executer_tests "$OPT_MODE" "$OPT_TARGETS" || exit 2
(( OPT_REPORT_ERR )) && sommaire_erreurs
echo
echo "Bilan : ${C_OK}OK=$COMPTE_OK${C_RESET} ${C_SKIP}SKIP=$COMPTE_SKIP${C_RESET} ${C_FAIL}FAIL=$COMPTE_FAIL${C_RESET}"
(( COMPTE_FAIL == 0 )) || exit 1
exit 0
