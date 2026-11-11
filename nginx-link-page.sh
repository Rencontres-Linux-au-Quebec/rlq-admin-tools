#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# nginx-link-page.sh - builds and installs one or more link pages on the Odoo site (for example /liens/ with LittleLink and
# /liens2/ with another engine, to compare them). EVERYTHING specific to a group (titles, links, logo, icons, themes, paths)
# comes from the configuration file: nothing about a group is written in this program or in the repository.
#
# Engines: "littlelink" (static pages, LittleLink v3.11.0, pinned tag and commit). "linkstack" is reserved: LinkStack is a
# PHP/Laravel application with a database and a setup wizard, so it is refused until it is implemented.
#
# Safety: LittleLink is fetched at a pinned tag AND commit (a different commit is refused); the logo and the icons are
# downloaded over HTTPS only, size-limited, and kept only if their content really is PNG, JPEG, WebP or SVG; the pages have
# no script; nginx serves only GET and HEAD for each path, with a Content-Security-Policy; nginx -t must pass before nginx is
# reloaded, and the previous snippet is restored if it does not.
#
# Configuration: /etc/default/nginx-link-page.conf, then ~/.nginx-link-page.conf (the last one read wins); -c/--config FILE
# reads that file ONLY; the command line wins over the file. Keys are KEY=VALUE (uppercase), see
# nginx-link-page.conf.example: SITE_* (shared content), LINK_n_* (shared links), PAGE_n_* (one block per page, n = 1, 2...).
#
# Usage: sudo nginx-link-page.sh [--check | --update] [--yes] [-c FILE]        (also: --changelog, --help, --version)

set -u
LANG_C="${LC_ALL:-${LC_MESSAGES:-${LANG:-C}}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
readonly SCRIPT_VERSION="1.1.20261111.093000"
readonly SCRIPT_NAME="nginx-link-page"
readonly CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"

# LittleLink, pinned: tag and commit (verified after cloning).
readonly LINKPAGE_REPO="https://github.com/sethcottle/littlelink"
readonly LINKPAGE_TAG="v3.11.0"
readonly LINKPAGE_SHA="3c9162c9f8324d5e002259ed8b4b3cc377b08486"
readonly MAX_ASSET_BYTES=524288
readonly MOTEURS_PRIS_EN_CHARGE="littlelink"

# ---- colours (only on a terminal; never when the output is redirected) ----
C_CYAN=""; C_GREEN=""; C_RED=""; C_YELLOW=""; C_OPT=""; C_RESET=""
if [[ -t 1 ]]; then
    C_CYAN=$'\033[1;36m'; C_GREEN=$'\033[32m'; C_RED=$'\033[31m'; C_YELLOW=$'\033[33m'; C_OPT=$'\033[1;35m'; C_RESET=$'\033[0m'
fi

# ---- language: fr by default, en when LANG / LC_ALL say so (messages only) ----
MSG_EN=0
case "$LANG_C" in en*|EN*) MSG_EN=1 ;; esac
m() { if (( MSG_EN )); then printf '%s' "$2"; else printf '%s' "$1"; fi; }

ok()   { echo "  ${C_GREEN}[OK]${C_RESET}   $1"; }
attn() { echo "  ${C_YELLOW}[ATTN]${C_RESET} $1"; }
err()  { echo "  ${C_RED}[FAIL]${C_RESET} $1" >&2; }

changelog_section() {
    awk -v cle="$SCRIPT_NAME.sh" '/^## /{dans=($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE"
}

usage() {
    cat <<AIDE
Usage : $SCRIPT_NAME.sh [OPTION]...
Construit et installe une ou plusieurs pages de liens sur le site Odoo, a partir du fichier de configuration.
Builds and installs one or more link pages on the Odoo site, from the configuration file.

Options (ordre alphabetique / alphabetical order) :
  ${C_OPT}--changelog${C_RESET}                affiche le journal des modifications / show the change log
  ${C_OPT}--check${C_RESET}                    verifie la configuration, n'ecrit rien (defaut) / check only, writes nothing (default)
  ${C_OPT}-c, --config FILE${C_RESET}          lit SEUL ce fichier / read ONLY this file
  ${C_OPT}-h, --help${C_RESET}                 affiche cette aide / show this help
  ${C_OPT}--lang LANG${C_RESET}                langue des messages : fr ou en / message language: fr or en
  ${C_OPT}--update${C_RESET}                   installe ou met a jour les pages (root, confirmation) / install or update (root, asks first)
  ${C_OPT}--version${C_RESET}                  affiche la version / show the version
  ${C_OPT}--yes${C_RESET}                      avec --update : sans question / with --update: no question

Configuration lue : /etc/default/$SCRIPT_NAME.conf puis ~/.$SCRIPT_NAME.conf (le dernier gagne), ou seulement -c FILE.
Configuration read: /etc/default/$SCRIPT_NAME.conf then ~/.$SCRIPT_NAME.conf (the last one wins), or only -c FILE.

Cles / keys (voir nginx-link-page.conf.example) :
  SITE_* (contenu partage / shared content), LINK_n_* (liens / links),
  PAGE_n_* (ENABLED, ENGINE, PATH, DIR, THEME, TITLE : une page par bloc / one page per block)
AIDE
}

# ---- argument scan before the configuration: --config, --lang ----
CONFIG_EXPLICIT=""
MODE="check"
YES=0
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
    case "${args[i]}" in
        -c|--config) CONFIG_EXPLICIT="${args[i+1]:-}" ;;
        --config=*) CONFIG_EXPLICIT="${args[i]#--config=}" ;;
        --lang) case "${args[i+1]:-}" in en) MSG_EN=1 ;; fr) MSG_EN=0 ;; esac ;;
        --lang=*) case "${args[i]#--lang=}" in en) MSG_EN=1 ;; fr) MSG_EN=0 ;; esac ;;
    esac
done

# ---- configuration: /etc/default then ~/.file (or the explicit file only); later files win ----
declare -A CFG=()
CFG_FICHIERS=()
lire_fichier() {
    local f="$1" ligne cle valeur
    [[ -r "$f" ]] || return 0
    CFG_FICHIERS+=("$f")
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        ligne="${ligne#"${ligne%%[![:space:]]*}"}"
        [[ -z "$ligne" || "$ligne" == "#"* || "$ligne" != *=* ]] && continue
        cle="${ligne%%=*}"; valeur="${ligne#*=}"
        cle="${cle//[[:space:]]/}"; cle="${cle^^}"
        valeur="${valeur#"${valeur%%[![:space:]]*}"}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"
        if [[ "${valeur:0:1}" == '"' || "${valeur:0:1}" == "'" ]] && [[ "${valeur: -1}" == "${valeur:0:1}" && ${#valeur} -ge 2 ]]; then
            valeur="${valeur:1:${#valeur}-2}"
        elif [[ "$valeur" == *" #"* ]]; then
            valeur="${valeur%% #*}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"   # commentaire en fin de ligne
        fi
        [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]] && CFG["$cle"]="$valeur"
    done < "$f"
}
if [[ -n "$CONFIG_EXPLICIT" ]]; then
    lire_fichier "$CONFIG_EXPLICIT"
else
    lire_fichier "${NGINX_LINK_PAGE_ETC_DEFAULT:-/etc/default}/$SCRIPT_NAME.conf"
    lire_fichier "${HOME:-/root}/.$SCRIPT_NAME.conf"
fi

# ---- command line (after the configuration: it wins) ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--config|--lang) shift 2 ;;
        --config=*|--lang=*) shift ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then echo "Changelog introuvable / not found: $CHANGELOG_FILE" >&2; exit 1; fi
            if [[ -t 1 ]]; then
                changelog_section | sed -E $'s/([0-9]+\\.[0-9]+\\.[0-9]{8}\\.[0-9]{6})/\\x1b[1;36m\\1\\x1b[0m/' || true
            else
                changelog_section || true
            fi
            exit 0 ;;
        --check) MODE="check"; shift ;;
        --update) MODE="update"; shift ;;
        --yes) YES=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --version) echo "$SCRIPT_NAME.sh version $SCRIPT_VERSION"; exit 0 ;;
        *) echo "Argument inconnu / unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# ---- validation ----
PROBLEMES=()
valeur_ou() { local v="${CFG[$1]:-}"; [[ -n "$v" ]] && printf '%s' "$v" || printf '%s' "$2"; }
URL_RE='^https://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+$'
CHEMIN_RE='^/[A-Za-z0-9_-]+/$'

SITE_TITLE_V=$(valeur_ou SITE_TITLE "")
SITE_HEADING_V=$(valeur_ou SITE_HEADING "$SITE_TITLE_V")
SITE_DESCRIPTION_V=$(valeur_ou SITE_DESCRIPTION "")
SITE_LANGUAGE_V=$(valeur_ou SITE_LANGUAGE fr)
SITE_FOOTER_V=$(valeur_ou SITE_FOOTER "")
SITE_LOGO_URL_V=$(valeur_ou SITE_LOGO_URL "")
SITE_LOGO_ALT_V=$(valeur_ou SITE_LOGO_ALT "$SITE_TITLE_V")
SNIPPETS_DIR="${NGINX_LINK_PAGE_SNIPPETS_DIR:-/etc/nginx/snippets}"
LIEN_FICHIER="$SNIPPETS_DIR/liens-publics.conf"

[[ -n "$SITE_TITLE_V" ]] || PROBLEMES+=("SITE_TITLE absent / missing")
[[ "$SITE_LANGUAGE_V" =~ ^(fr|en)$ ]] || PROBLEMES+=("SITE_LANGUAGE=$SITE_LANGUAGE_V (fr ou en / fr or en)")
if [[ -n "$SITE_LOGO_URL_V" ]] && ! [[ "$SITE_LOGO_URL_V" =~ $URL_RE ]]; then
    PROBLEMES+=("SITE_LOGO_URL doit etre une adresse https:// / must be an https:// address")
fi

# shared links: LINK_1_..., LINK_2_... without gaps
LIENS_N=()
n=1
while [[ -n "${CFG[LINK_${n}_LABEL]:-}${CFG[LINK_${n}_URL]:-}" ]]; do LIENS_N+=("$n"); n=$((n + 1)); done
for k in "${!CFG[@]}"; do
    if [[ "$k" =~ ^LINK_([0-9]+)_ ]] && (( BASH_REMATCH[1] >= n )); then
        PROBLEMES+=("$k sans lien precedent (pas de trou) / $k without a previous link (no gap)")
    fi
done
for i in "${LIENS_N[@]}"; do
    lab="${CFG[LINK_${i}_LABEL]:-}"; url="${CFG[LINK_${i}_URL]:-}"
    [[ -n "$lab" && ${#lab} -le 80 ]] || PROBLEMES+=("LINK_${i}_LABEL vide ou trop long (80 caracteres max) / empty or too long")
    [[ "$url" =~ $URL_RE ]] || PROBLEMES+=("LINK_${i}_URL doit etre une adresse https:// / must be an https:// address")
    for cle in LINK_${i}_ICON LINK_${i}_ICON_DARK; do
        ic="${CFG[$cle]:-}"
        [[ -z "$ic" ]] && continue
        [[ "$ic" =~ ^builtin:[a-z0-9-]+$ || "$ic" =~ $URL_RE ]] || PROBLEMES+=("$cle : builtin:NOM ou https:// / builtin:NAME or https://")
    done
done
(( ${#LIENS_N[@]} > 0 )) || PROBLEMES+=("aucun lien (LINK_1_LABEL et LINK_1_URL) / no link (LINK_1_LABEL and LINK_1_URL)")

# pages: PAGE_1_..., PAGE_2_... without gaps; each page has its own engine, path, folder and theme
PAGES_N=()
p=1
while [[ -n "${CFG[PAGE_${p}_PATH]:-}${CFG[PAGE_${p}_DIR]:-}${CFG[PAGE_${p}_ENGINE]:-}" ]]; do PAGES_N+=("$p"); p=$((p + 1)); done
for k in "${!CFG[@]}"; do
    if [[ "$k" =~ ^PAGE_([0-9]+)_ ]] && (( BASH_REMATCH[1] >= p )); then
        PROBLEMES+=("$k sans page precedente (pas de trou) / $k without a previous page (no gap)")
    fi
done
(( ${#PAGES_N[@]} > 0 )) || PROBLEMES+=("aucune page (PAGE_1_PATH, PAGE_1_DIR) / no page (PAGE_1_PATH, PAGE_1_DIR)")
declare -A CHEMINS_VUS=() DOSSIERS_VUS=()
DOSSIERS_LISTE=()
for i in "${PAGES_N[@]}"; do
    pre="PAGE_${i}_"
    enabled="$(valeur_ou "${pre}ENABLED" yes)"
    engine="$(valeur_ou "${pre}ENGINE" littlelink)"
    chemin="$(valeur_ou "${pre}PATH" "")"
    dossier="$(valeur_ou "${pre}DIR" "")"
    theme="$(valeur_ou "${pre}THEME" auto)"
    [[ "$enabled" =~ ^(yes|no|oui|non|1|0)$ ]] || PROBLEMES+=("${pre}ENABLED=$enabled (yes ou no)")
    case "$engine" in
        littlelink) ;;
        linkstack) PROBLEMES+=("${pre}ENGINE=linkstack : moteur reserve, pas encore pris en charge (PHP/Laravel + base de donnees) / engine reserved, not yet supported") ;;
        *) PROBLEMES+=("${pre}ENGINE=$engine (moteurs pris en charge / supported: $MOTEURS_PRIS_EN_CHARGE)") ;;
    esac
    [[ "$chemin" =~ $CHEMIN_RE ]] || PROBLEMES+=("${pre}PATH=$chemin (ex. /liens/ ou /liens2/)")
    if [[ -n "$chemin" ]]; then
        [[ -z "${CHEMINS_VUS[$chemin]:-}" ]] || PROBLEMES+=("${pre}PATH=$chemin deja utilise / already used")
        CHEMINS_VUS["$chemin"]=1
    fi
    [[ "$dossier" == /* && "$dossier" != "/" ]] || PROBLEMES+=("${pre}DIR=$dossier (chemin absolu, pas /)")
    d2="${dossier%/}"
    if [[ -n "$d2" ]]; then
        [[ -z "${DOSSIERS_VUS[$d2]:-}" ]] || PROBLEMES+=("${pre}DIR=$dossier deja utilise / already used")
        if (( ${#DOSSIERS_LISTE[@]} )); then
            for autre in "${DOSSIERS_LISTE[@]}"; do
                if [[ "$d2/" == "$autre/"* || "$autre/" == "$d2/"* ]]; then
                    PROBLEMES+=("${pre}DIR=$dossier imbrique avec un autre dossier / nested with another folder")
                fi
            done
        fi
        DOSSIERS_VUS["$d2"]=1
        DOSSIERS_LISTE+=("$d2")
    fi
    [[ "$theme" =~ ^(auto|light|dark)$ ]] || PROBLEMES+=("${pre}THEME=$theme (auto, light ou dark)")
done

# ---- summary of the files read and of the pages ----
if (( ${#CFG_FICHIERS[@]} > 0 )); then
    echo "Configuration lue / configuration read : ${CFG_FICHIERS[*]}"
else
    echo "Configuration lue / configuration read : aucune / none (valeurs par defaut / defaults)"
fi
echo "  $(m "Site" "Site") : ${SITE_TITLE_V:-?} · ${#LIENS_N[@]} $(m "liens" "links") · ${#PAGES_N[@]} $(m "page(s)" "page(s)")"
for i in "${PAGES_N[@]}"; do
    echo "    PAGE_${i} : $(valeur_ou "PAGE_${i}_PATH" "?") -> $(valeur_ou "PAGE_${i}_DIR" "?") · $(valeur_ou "PAGE_${i}_ENGINE" littlelink) · $(valeur_ou "PAGE_${i}_ENABLED" yes)"
done

if (( ${#PROBLEMES[@]} > 0 )); then
    for pb in "${PROBLEMES[@]}"; do err "$pb"; done
    exit 1
fi

# ---- helpers: HTML escaping, asset download and type check ----
html_echap() {
    local s="$1"
    # "\&" : in a bash 5.2 replacement (patsub_replacement), an unescaped "&" stands for the matched text.
    s="${s//&/\&amp;}"; s="${s//</\&lt;}"; s="${s//>/\&gt;}"; s="${s//\"/\&quot;}"; s="${s//\'/\&#39;}"
    printf '%s' "$s"
}

# type_image FILE : prints png, jpg, webp or svg for a real image, nothing (and fails) otherwise.
type_image() {
    local f="$1" sig
    sig=$(head -c 12 "$f" 2>/dev/null | od -An -tx1 | tr -d ' \n')
    case "$sig" in
        89504e470d0a1a0a*) echo png; return 0 ;;
        ffd8ff*) echo jpg; return 0 ;;
        52494646*) if [[ "${sig:16:8}" == "57454250" ]]; then echo webp; return 0; fi ;;
    esac
    if head -c 512 "$f" 2>/dev/null | tr -d '\000' | grep -qi '<svg'; then echo svg; return 0; fi
    return 1
}

# telecharger URL BASE : downloads an image to BASE.ext; sets RES_FICHIER (full path) on success.
RES_FICHIER=""
telecharger() {
    local url="$1" base="$2" tmp type ext
    RES_FICHIER=""
    tmp=$(mktemp) || return 1
    if ! curl -fsSL --proto '=https' --tlsv1.2 --max-time 30 --max-filesize "$MAX_ASSET_BYTES" -o "$tmp" "$url" 2>/dev/null; then
        rm -f "$tmp"; return 1
    fi
    type=$(type_image "$tmp") || { rm -f "$tmp"; return 1; }
    case "$type" in jpg) ext=jpg ;; *) ext="$type" ;; esac
    if install -m 644 "$tmp" "$base.$ext"; then RES_FICHIER="$base.$ext"; fi
    rm -f "$tmp"
    [[ -n "$RES_FICHIER" ]]
}

# ---- --check: nothing is written, no network ----
echo
echo "$(m "Verification" "Check") :"
ok "$(m "configuration valide" "valid configuration")"
for i in "${LIENS_N[@]}"; do
    echo "  - ${CFG[LINK_${i}_LABEL]} -> ${CFG[LINK_${i}_URL]}"
done
if [[ "$MODE" == "check" ]]; then
    echo
    echo "$(m "Rien n'a ete modifie (--check). Lancer avec --update (root) pour installer." "Nothing was changed (--check). Run with --update (root) to install.")"
    exit 0
fi

# ---- --update ----
if [[ "$(id -u)" -ne 0 ]]; then
    err "$(m "--update ecrit dans les dossiers des pages et dans $SNIPPETS_DIR : lancer avec sudo." "--update writes to the page folders and to $SNIPPETS_DIR: run with sudo.")"
    exit 1
fi
if (( ! YES )); then
    if [[ -t 0 ]]; then
        read -r -p "$(m "Installer ces pages ? [o/N] " "Install these pages? [y/N] ")" rep || rep=""
        [[ "$rep" =~ ^[OoYy] ]] || { attn "$(m "Rien n'a ete modifie." "Nothing was changed.")"; exit 0; }
    else
        err "$(m "pas de terminal : ajouter --yes pour confirmer." "no terminal: add --yes to confirm.")"; exit 1
    fi
fi
for c in git curl nginx; do
    command -v "$c" >/dev/null 2>&1 || { err "$c $(m "absent" "not found")"; exit 1; }
done

TMP=$(mktemp -d) || { err "$(m "dossier temporaire" "temporary folder")"; exit 1; }
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/assets/images/site"

ACTIVES=()
for i in "${PAGES_N[@]}"; do
    [[ "$(valeur_ou "PAGE_${i}_ENABLED" yes)" =~ ^(yes|oui|1)$ ]] && ACTIVES+=("$i")
done

# 1) LittleLink, once, at the pinned tag and commit (only if an enabled page uses it)
needs_littlelink=0
for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do
    [[ "$(valeur_ou "PAGE_${i}_ENGINE" littlelink)" == littlelink ]] && needs_littlelink=1
done
if (( needs_littlelink )); then
    if ! timeout 180 git clone --quiet --depth 1 --branch "$LINKPAGE_TAG" "$LINKPAGE_REPO" "$TMP/littlelink" >/dev/null 2>&1; then
        err "$(m "clonage de LittleLink $LINKPAGE_TAG impossible (reseau ?)" "cannot clone LittleLink $LINKPAGE_TAG (network?)")"; exit 1
    fi
    sha=$(git -C "$TMP/littlelink" rev-parse HEAD 2>/dev/null || true)
    if [[ "$sha" != "$LINKPAGE_SHA" ]]; then
        err "$(m "LittleLink $LINKPAGE_TAG : commit ${sha:-inconnu} different du commit epingle : refuse." "LittleLink $LINKPAGE_TAG: commit ${sha:-unknown} differs from the pinned commit: refused.")"; exit 1
    fi
    for d in css fonts images; do
        [[ -d "$TMP/littlelink/$d" ]] || { err "LittleLink : $d/ absent / missing"; exit 1; }
    done
    ok "LittleLink $LINKPAGE_TAG (${sha:0:12})"
fi

# 2) logo and icons: downloaded once, checked, kept in the work folder (pages load nothing from other sites)
LOGO_LOCAL=""
if [[ -n "$SITE_LOGO_URL_V" ]]; then
    telecharger "$SITE_LOGO_URL_V" "$TMP/assets/images/site/logo" || { err "$(m "logo non telechargeable ou pas une image : $SITE_LOGO_URL_V" "logo not downloadable or not an image: $SITE_LOGO_URL_V")"; exit 1; }
    LOGO_LOCAL="images/site/${RES_FICHIER##*/}"
    ok "$(m "logo" "logo") -> $LOGO_LOCAL"
fi
declare -A ICONE_RESOLUE=()
RES_ICONE=""
icone_resoudre() {   # icone_resoudre VALEUR CLE : sets RES_ICONE (path relative to a page folder)
    local v="$1" cle="$2" nom
    RES_ICONE=""
    if [[ "$v" == builtin:* ]]; then
        nom="${v#builtin:}"
        [[ -f "$TMP/littlelink/images/icons/$nom.svg" ]] || { err "$(m "icone integree inconnue : $nom" "unknown built-in icon: $nom")"; return 1; }
        RES_ICONE="images/icons/$nom.svg"; return 0
    fi
    if [[ -n "${ICONE_RESOLUE[$v]:-}" ]]; then RES_ICONE="${ICONE_RESOLUE[$v]}"; return 0; fi
    telecharger "$v" "$TMP/assets/images/site/icon-$cle" || { err "$(m "icone non telechargeable ou pas une image : $v" "icon not downloadable or not an image: $v")"; return 1; }
    ICONE_RESOLUE[$v]="images/site/${RES_FICHIER##*/}"
    RES_ICONE="${ICONE_RESOLUE[$v]}"
}
declare -A ICONE_CLAIR=() ICONE_SOMBRE=()
for i in "${LIENS_N[@]}"; do
    ic="${CFG[LINK_${i}_ICON]:-builtin:generic-website}"
    icone_resoudre "$ic" "$i-clair" || exit 1; ICONE_CLAIR[$i]="$RES_ICONE"
    ICONE_SOMBRE[$i]=""
    if [[ -n "${CFG[LINK_${i}_ICON_DARK]:-}" ]]; then
        icone_resoudre "${CFG[LINK_${i}_ICON_DARK]}" "$i-sombre" || exit 1; ICONE_SOMBRE[$i]="$RES_ICONE"
    fi
done

# 3) one folder per enabled page: assets + index.html generated with the page's theme and title
genere_index() {   # genere_index DOSSIER THEME TITRE
    local dossier="$1" theme="$2" titre="$3" classe lab url clair sombre
    case "$theme" in auto) classe="theme-auto" ;; light) classe="theme-light" ;; dark) classe="theme-dark" ;; esac
    {
        echo "<!DOCTYPE html>"
        echo "<!-- Genere par $SCRIPT_NAME.sh $SCRIPT_VERSION a partir de la configuration. Ne pas editer a la main. -->"
        echo "<!-- Built on LittleLink (MIT, https://github.com/sethcottle/littlelink), tag $LINKPAGE_TAG. -->"
        echo "<html class=\"$classe\" lang=\"$SITE_LANGUAGE_V\">"
        echo "  <head>"
        echo "    <meta charset=\"utf-8\">"
        echo "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        echo "    <title>$(html_echap "$titre")</title>"
        if [[ -n "$SITE_DESCRIPTION_V" ]]; then echo "    <meta name=\"description\" content=\"$(html_echap "$SITE_DESCRIPTION_V")\">"; fi
        echo "    <meta name=\"theme-color\" content=\"#ffffff\" media=\"(prefers-color-scheme: light)\">"
        echo "    <meta name=\"theme-color\" content=\"#121212\" media=\"(prefers-color-scheme: dark)\">"
        echo "    <meta name=\"referrer\" content=\"strict-origin-when-cross-origin\">"
        echo "    <meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src 'self'; style-src 'self'; font-src 'self'; script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'\">"
        echo "    <link rel=\"stylesheet\" href=\"css/reset.css\">"
        echo "    <link rel=\"stylesheet\" href=\"css/style.css\">"
        echo "    <link rel=\"stylesheet\" href=\"css/brands.css\">"
        echo "  </head>"
        echo "  <body>"
        echo "    <div class=\"container\"><div class=\"column\"><main>"
        if [[ -n "$LOGO_LOCAL" ]]; then
            echo "      <img class=\"avatar avatar--none\" src=\"$LOGO_LOCAL\" width=\"128\" height=\"128\" alt=\"$(html_echap "$SITE_LOGO_ALT_V")\">"
        fi
        echo "      <h1>$(html_echap "$SITE_HEADING_V")</h1>"
        if [[ -n "$SITE_DESCRIPTION_V" ]]; then echo "      <p>$(html_echap "$SITE_DESCRIPTION_V")</p>"; fi
        echo "      <nav class=\"button-stack\" aria-label=\"$(m "Liens" "Links")\">"
        for i in "${LIENS_N[@]}"; do
            lab="${CFG[LINK_${i}_LABEL]}"; url="${CFG[LINK_${i}_URL]}"
            clair="${ICONE_CLAIR[$i]}"; sombre="${ICONE_SOMBRE[$i]}"
            echo "        <a class=\"button button-default\" href=\"$(html_echap "$url")\" target=\"_blank\" rel=\"noopener noreferrer\">"
            if [[ -n "$sombre" && "$theme" == "auto" ]]; then
                echo "          <picture><source media=\"(prefers-color-scheme: dark)\" srcset=\"$sombre\"><img class=\"icon\" aria-hidden=\"true\" src=\"$clair\" alt=\"\"></picture>$(html_echap "$lab")</a>"
            elif [[ -n "$sombre" && "$theme" == "dark" ]]; then
                echo "          <img class=\"icon\" aria-hidden=\"true\" src=\"$sombre\" alt=\"\">$(html_echap "$lab")</a>"
            else
                echo "          <img class=\"icon\" aria-hidden=\"true\" src=\"$clair\" alt=\"\">$(html_echap "$lab")</a>"
            fi
        done
        echo "      </nav>"
        echo "    </main>"
        if [[ -n "$SITE_FOOTER_V" ]]; then echo "    <footer>$(html_echap "$SITE_FOOTER_V")</footer>"; fi
        echo "    </div></div>"
        echo "  </body>"
        echo "</html>"
    } > "$dossier/index.html"
}

for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do
    site="$TMP/page-$i"
    mkdir -p "$site/images/site"
    cp -r "$TMP/littlelink/css" "$TMP/littlelink/fonts" "$site/"
    cp -r "$TMP/littlelink/images" "$site/"
    cp -r "$TMP/assets/images/site/." "$site/images/site/"
    genere_index "$site" "$(valeur_ou "PAGE_${i}_THEME" auto)" "$(valeur_ou "PAGE_${i}_TITLE" "$SITE_TITLE_V")"
    ok "$(m "page" "page") PAGE_${i} $(m "preparee" "prepared") (${#LIENS_N[@]} $(m "liens" "links"))"
done

# 4) one nginx snippet, one location per enabled page (distinct paths: /liens/ does not catch /liens2/)
LIEN_NOUVEAU="# Genere par $SCRIPT_NAME.sh : ne pas editer a la main."$'\n'
if (( ${#ACTIVES[@]} == 0 )); then
    LIEN_NOUVEAU+="# liens : inactif"$'\n'
else
    LIEN_NOUVEAU+="# liens : actif"$'\n'
    for i in "${ACTIVES[@]}"; do
        LIEN_NOUVEAU+="location ^~ $(valeur_ou "PAGE_${i}_PATH" "") {"$'\n'
        LIEN_NOUVEAU+="    alias $(valeur_ou "PAGE_${i}_DIR" "")/;"$'\n'
        LIEN_NOUVEAU+="    index index.html;"$'\n'
        LIEN_NOUVEAU+="    limit_except GET HEAD { deny all; }"$'\n'
        LIEN_NOUVEAU+="    add_header Content-Security-Policy \"default-src 'none'; img-src 'self'; style-src 'self'; font-src 'self'; script-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'\" always;"$'\n'
        LIEN_NOUVEAU+="    add_header X-Content-Type-Options \"nosniff\" always;"$'\n'
        LIEN_NOUVEAU+="    add_header Referrer-Policy \"strict-origin-when-cross-origin\" always;"$'\n'
        LIEN_NOUVEAU+="}"$'\n'
    done
fi

# 5) install the folders, then the snippet: nginx -t, reload; the previous snippet is restored on refusal
mkdir -p "$SNIPPETS_DIR"
LIEN_ANCIEN=""; [[ -f "$LIEN_FICHIER" ]] && LIEN_ANCIEN=$(cat "$LIEN_FICHIER")
for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do
    dossier="$(valeur_ou "PAGE_${i}_DIR" "")"
    mkdir -p "$dossier"
    for x in css fonts images index.html; do rm -rf "${dossier:?}/$x"; done
    cp -r "$TMP/page-$i/css" "$TMP/page-$i/fonts" "$TMP/page-$i/images" "$TMP/page-$i/index.html" "$dossier/" || { err "$(m "copie impossible dans" "copy failed in") $dossier"; exit 1; }
    chmod -R a+rX "$dossier"
    ok "$(m "fichiers installes dans" "files installed in") $dossier"
done
LIEN_TMP=$(mktemp "$SNIPPETS_DIR/.liens-publics.XXXXXX")
printf '%s' "$LIEN_NOUVEAU" > "$LIEN_TMP" && chmod 644 "$LIEN_TMP" && mv -f "$LIEN_TMP" "$LIEN_FICHIER"
if nginx_erreur=$(nginx -t 2>&1); then
    if systemctl reload nginx >/dev/null 2>&1 || nginx -s reload >/dev/null 2>&1; then
        ok "$(m "nginx -t reussi, nginx recharge" "nginx -t passed, nginx reloaded") ($LIEN_FICHIER)"
    else
        attn "$(m "nginx -t reussi mais rechargement impossible : systemctl status nginx --no-pager" "nginx -t passed but reload failed: systemctl status nginx --no-pager")"
    fi
else
    if [[ -n "$LIEN_ANCIEN" ]]; then printf '%s\n' "$LIEN_ANCIEN" > "$LIEN_FICHIER"; else printf '%s\n' "# liens : inactif" > "$LIEN_FICHIER"; fi
    err "$(m "nginx -t refuse la configuration : ancien fragment restaure, nginx NON recharge" "nginx -t refuses the configuration: previous snippet restored, nginx NOT reloaded")"
    printf '%s\n' "$nginx_erreur" | head -8 | sed 's/^/        nginx -t : /'
    exit 1
fi
