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
# nginx-link-page.sh - builds and installs one or more link pages on the Odoo site (for example /links/ with LittleLink and
# /links2/ with another engine, to compare them). EVERYTHING specific to a group (titles, links, logo, icons, themes, paths)
# comes from the configuration file: nothing about a group is written in this program or in the repository.
#
# Engines: "littlelink" (static pages, LittleLink v3.11.0 + LittleLink Extended v3.2.0, pinned tags and commits). "linkstack" is reserved: LinkStack is a
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
readonly SCRIPT_VERSION="1.34.20261112.224301"
readonly SCRIPT_NAME="nginx-link-page"
# --config-merge: same rule as the other programs (apps/_config.py fusionner): the configuration file is rewritten from the new template,
# keeping its active values; the old file is copied to FILE.bak-YYYYMMDD-HHMMSS. Then exit.
_fusion=0; _fusion_cfg=""; _fusion_lang="${NGINX_TOOLS_I18N_LANGUE:-fr}"; _prec=""
for _a in "$@"; do
    case "$_a" in --config-merge) _fusion=1 ;; --config=*) _fusion_cfg="${_a#--config=}" ;; --lang=*) _fusion_lang="${_a#--lang=}" ;; esac
    case "$_prec" in -c|--config) _fusion_cfg="$_a" ;; --lang) _fusion_lang="$_a" ;; esac
    _prec="$_a"
done
if (( _fusion )); then
    if ! command -v python3 >/dev/null 2>&1 || [[ ! -r "$SCRIPT_DIR/apps/_config.py" ]]; then
        echo "--config-merge : python3 ou $SCRIPT_DIR/apps/_config.py introuvable / not found" >&2; exit 1
    fi
    NGINX_TOOLS_ETC_DEFAULT="${NGINX_LINK_PAGE_ETC_DEFAULT:-${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}}" \
        python3 "$SCRIPT_DIR/apps/_config.py" --merge "$SCRIPT_NAME" --lang "${_fusion_lang%%[_.-]*}" ${_fusion_cfg:+--config "$_fusion_cfg"}
    exit $?
fi
unset _fusion _fusion_cfg _fusion_lang _prec _a
readonly CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"

# LittleLink, pinned: tag and commit (verified after cloning).
readonly LINKPAGE_REPO="https://github.com/sethcottle/littlelink"
readonly LINKPAGE_TAG="v3.11.0"
readonly LINKPAGE_SHA="3c9162c9f8324d5e002259ed8b4b3cc377b08486"
# 1.11: LittleLink Extended (MIT): 76 more icons and brand buttons (Codeberg, Lemmy, PeerTube, Matrix, ORCID...), same pinning rule.
# Only css/brands-extended.css and images/icons-extended/ are copied (its sensitive-content.js is not: the pages forbid any script).
readonly LINKPAGE_EXT_REPO="https://github.com/sethcottle/littlelink-extended"
readonly LINKPAGE_EXT_TAG="v3.2.0"
readonly LINKPAGE_EXT_SHA="d7034f83a6bf71c4a663d2d046a03b37ec74ae45"
readonly MAX_ASSET_BYTES=524288
# 1.15: themes of PAGE_n_THEME: the 3 of LittleLink, then the 5 of apps/link-page-themes.css (copied as css/themes.css into each page)
# 1.16: and the 4 LinkStack themes adapted in apps/link-page-themes/ (linkstack.css, images, fonts; MIT and OFL, LICENSES.md)
readonly THEMES_RE="auto|light|dark|aurora|maple|river|terminal|tux|tux-quebec|quebec|boreal|sunset|winter|tux-flag|tux-poster|ls-aurora|ls-dark|ls-dawn|ls-misty-rain"
readonly THEMES_LISTE="auto, light, dark, aurora, maple, river, terminal, tux, tux-quebec, quebec, boreal, sunset, winter, tux-flag, tux-poster, ls-aurora, ls-dark, ls-dawn ou ls-misty-rain"
readonly THEMES_CSS="$SCRIPT_DIR/apps/link-page-themes.css"
# themes of link-page-themes.css (1.15: 5 themes; 1.21: 5 more, tux-quebec with its image apps/link-page-themes/images/tux-quebec.jpg)
readonly THEMES_MAISON="aurora|maple|river|terminal|tux|tux-quebec|quebec|boreal|sunset|winter|tux-flag|tux-poster"
readonly THEMES_LINKSTACK="$SCRIPT_DIR/apps/link-page-themes"
# 1.17: "Theme" button (PAGE_n_THEMES): style sheet copied as css/theme-menu.css; "all" = every theme of THEMES_RE
readonly THEME_MENU_CSS="$SCRIPT_DIR/apps/link-page-theme-menu.css"
# 1.26: link menus (LINK_n_MENU): style sheet copied as css/link-menu.css
readonly LINK_MENU_CSS="$SCRIPT_DIR/apps/link-page-link-menu.css"
# 1.31: featured links (LINK_n_STYLE) and QR code link (PAGE_n_QR): style sheet copied as css/extras.css
readonly EXTRAS_CSS="$SCRIPT_DIR/apps/link-page-extras.css"
# 1.18: script of the pages (PAGE_n_SCRIPT): theme in place and remembered, language remembered, "Share" button; copied as js/link-page.js
readonly LINK_PAGE_JS="$SCRIPT_DIR/apps/link-page.js"
readonly THEMES_TOUS="auto light dark aurora maple river terminal tux tux-quebec quebec boreal sunset winter tux-flag tux-poster ls-aurora ls-dark ls-dawn ls-misty-rain"
# themes_offerts VALUE: the themes of PAGE_n_THEMES, one per word, without duplicates, in the given order ("all": THEMES_TOUS)
themes_offerts() {
    local v="${1// /}" t u vus=" "
    [[ -n "$v" ]] || return 0
    IFS=',' read -r -a _liste <<< "$v"
    for t in "${_liste[@]}"; do
        if [[ "${t,,}" == all ]]; then                 # "all" anywhere in the list: every theme, after those already given
            for u in $THEMES_TOUS; do [[ "$vus" != *" $u "* ]] && { vus+="$u "; printf '%s\n' "$u"; }; done
            continue
        fi
        [[ -n "$t" && "$vus" != *" $t "* ]] || continue
        vus+="$t "; printf '%s\n' "$t"
    done
}
# 1.14: the preview image of the social networks (1200 x 627 advised) is often a poster of more than 512 KiB: its own limit, the one of LinkedIn (5 MB)
readonly MAX_SHARE_BYTES=5242880
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
  ${C_OPT}--check-links${C_RESET}              demande chaque adresse des liens et signale les liens morts (404, sans réponse...) / request every link address and report the dead links (404, no answer...)
  ${C_OPT}--clicks${C_RESET}                   clics de chaque lien (PAGE_n_CLICKS=yes), lus dans les journaux d'accès de nginx / clicks of each link (PAGE_n_CLICKS=yes), read in the nginx access logs
  ${C_OPT}-c, --config FILE${C_RESET}          lit SEUL ce fichier / read ONLY this file
  ${C_OPT}--config-merge${C_RESET}             reecrit la configuration d'apres le nouveau modele en gardant ses valeurs (copie FICHIER.bak-...), puis quitte / rewrite the configuration from the new template, keeping its values (copy FILE.bak-...), then exit
  ${C_OPT}-h, --help${C_RESET}                 affiche cette aide / show this help
  ${C_OPT}--init${C_RESET}                     cree la configuration depuis le modele / create the configuration from the template
  ${C_OPT}--lang LANG${C_RESET}                langue des messages : fr ou en / message language: fr or en
  ${C_OPT}--rollback${C_RESET}                 remet les pages et le fragment nginx d'avant le dernier --update / put back the pages and the nginx snippet of before the last --update
  ${C_OPT}--update${C_RESET}                   installe ou met a jour les pages (root, confirmation) / install or update (root, asks first)
  ${C_OPT}--version${C_RESET}                  affiche la version / show the version
  ${C_OPT}--yes${C_RESET}                      avec --update : sans question / with --update: no question

Configuration lue : /etc/default/$SCRIPT_NAME.conf puis ~/.$SCRIPT_NAME.conf (le dernier gagne), ou seulement -c FILE.
Configuration read: /etc/default/$SCRIPT_NAME.conf then ~/.$SCRIPT_NAME.conf (the last one wins), or only -c FILE.

Cles / keys (voir nginx-link-page.conf.example) :
  SITE_* (contenu partage / shared content), LINK_n_* (liens / links : ICON, ICON_DARK, LABEL, LABEL_EN, MENU, PAGES, URL),
  PAGE_n_* (ACCENT, AVATAR, BUTTONS, DIR, ENABLED, ENGINE, LANGUAGES, PATH, SCRIPT, SHARE, SWITCH, THEME, THEMES, TITLE,
  TITLE_EN : une page par bloc / one page per block) ; une clé inconnue est refusée / an unknown key is refused
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
declare -A CFG_LIGNE=()       # 1.24: KEY -> FILE:LINE where its value was read (for the error messages)
LIGNES_INVALIDES=()           # 1.24: FILE:LINE: text of the lines that are neither empty, nor a comment, nor KEY=VALUE
lire_fichier() {
    local f="$1" ligne cle valeur n=0
    [[ -r "$f" ]] || return 0
    declare -p CFG_LIGNE &>/dev/null || declare -gA CFG_LIGNE=()
    CFG_FICHIERS+=("$f")
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        n=$((n + 1))
        ligne="${ligne#"${ligne%%[![:space:]]*}"}"
        [[ -z "$ligne" || "$ligne" == "#"* ]] && continue
        if [[ "$ligne" != *=* ]]; then LIGNES_INVALIDES+=("$f:$n: $ligne"); continue; fi
        cle="${ligne%%=*}"; valeur="${ligne#*=}"
        if [[ "$valeur" =~ ^[[:space:]]+# ]]; then valeur=""; fi          # "KEY=    # comment": empty value, not the text of the comment
        cle="${cle//[[:space:]]/}"; cle="${cle^^}"
        valeur="${valeur#"${valeur%%[![:space:]]*}"}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"
        if [[ "${valeur:0:1}" == '"' || "${valeur:0:1}" == "'" ]] && [[ "${valeur: -1}" == "${valeur:0:1}" && ${#valeur} -ge 2 ]]; then
            valeur="${valeur:1:${#valeur}-2}"
        elif [[ "$valeur" == *" #"* ]]; then
            valeur="${valeur%% #*}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"   # commentaire en fin de ligne
        fi
        if [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
            CFG["$cle"]="$valeur"; CFG_LIGNE["$cle"]="$f:$n"
        else
            LIGNES_INVALIDES+=("$f:$n: $ligne")
        fi
    done < "$f"
}
if [[ -n "$CONFIG_EXPLICIT" ]]; then
    lire_fichier "$CONFIG_EXPLICIT"
else
    lire_fichier "${NGINX_LINK_PAGE_ETC_DEFAULT:-/etc/default}/$SCRIPT_NAME.conf"
    lire_fichier "${HOME:-/root}/.$SCRIPT_NAME.conf"
fi

# init_config CIBLE : writes the commented template to CIBLE; never overwrites an existing file.
init_config() {   # init_config CIBLE [auto] : "auto" means no configuration was found at all
    local cible="$1" modele="$SCRIPT_DIR/nginx-link-page.conf.example"
    if [[ ! -r "$modele" ]]; then err "$(m "modele introuvable : $modele" "template not found: $modele")"; exit 1; fi
    if [[ -e "$cible" ]]; then err "$(m "existe deja, rien n'a ete ecrit : $cible" "already exists, nothing written: $cible")"; exit 1; fi
    if ! mkdir -p "$(dirname "$cible")" 2>/dev/null || ! cp "$modele" "$cible" 2>/dev/null; then
        err "$(m "ecriture impossible dans $cible : lancer avec sudo" "cannot write to $cible: run with sudo")"; exit 1
    fi
    chmod 644 "$cible"
    if [[ "${2:-}" == "auto" ]]; then
        attn "$(m "Aucune configuration trouvee : le modele a ete copie dans $cible." "No configuration found: the template was copied to $cible.")"
        echo "  $(m "Remplissez ce fichier (decommenter les lignes utiles), puis relancez. Rien n'a ete installe." "Fill in this file (uncomment the lines you need), then run again. Nothing was installed.")"
        exit 1
    fi
    ok "$(m "configuration creee" "configuration created") : $cible"
    echo "  $(m "Ensuite : editer ce fichier (decommenter les lignes utiles), puis --check, puis --update --yes." "Next: edit this file (uncomment the lines you need), then --check, then --update --yes.")"
    exit 0
}

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
        --check-links) MODE="links"; shift ;;
        --clicks) MODE="clicks"; shift ;;
        --init) MODE="init"; shift ;;
        --update) MODE="update"; shift ;;
        --rollback) MODE="rollback"; shift ;;
        --yes) YES=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --version) echo "$SCRIPT_NAME.sh version $SCRIPT_VERSION"; exit 0 ;;
        *) echo "Argument inconnu / unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# 1.33: previous version of the pages: copied by --update before it installs, put back by --rollback (whatever the configuration)
ETAT_DIR="${NGINX_LINK_PAGE_STATE_DIR:-/var/lib/$SCRIPT_NAME}"
readonly FICHIERS_GERES="css fonts images js index.html autre.html en fr qr.svg qr.png"      # what --update replaces in a page folder
if [[ "$MODE" == "rollback" ]]; then
    if [[ "$(id -u)" -ne 0 ]]; then err "$(m "--rollback écrit dans les dossiers des pages : lancer avec sudo." "--rollback writes to the page folders: run with sudo.")"; exit 1; fi
    prec="$ETAT_DIR/previous"
    if [[ ! -s "$prec/manifest" ]]; then err "$(m "aucune version précédente" "no previous version") ($prec)"; exit 1; fi
    echo "$(m "Version précédente du" "Previous version of") $(cat "$prec/date" 2>/dev/null || echo "?") :"
    snippet_remis=""
    while IFS=$'\t' read -r type nom chemin; do
        case "$type" in
            page)
                mkdir -p "$chemin"
                for x in $FICHIERS_GERES; do rm -rf "${chemin:?}/$x"; done
                rm -f "${chemin:?}"/theme-*.html
                if cp -a "$prec/$nom/." "$chemin/"; then ok "$(m "page remise" "page put back") : $chemin"; else err "$(m "copie impossible" "copy failed") : $chemin"; exit 1; fi ;;
            snippet)
                cp -a "$prec/$nom" "$chemin" && snippet_remis="$chemin" && ok "$(m "fragment nginx remis" "nginx snippet put back") : $chemin" ;;
            cron)
                if [[ "$nom" == "-" ]]; then rm -f "$chemin"; else mkdir -p "$(dirname "$chemin")"; cp -a "$prec/$nom" "$chemin"; fi ;;
        esac
    done < "$prec/manifest"
    if [[ -n "$snippet_remis" ]]; then
        if nginx_erreur=$(nginx -t 2>&1); then
            { systemctl reload nginx >/dev/null 2>&1 || nginx -s reload >/dev/null 2>&1; } && ok "$(m "nginx -t réussi, nginx rechargé" "nginx -t passed, nginx reloaded")"
        else
            err "$(m "nginx -t refuse la configuration après le retour arrière" "nginx -t refuses the configuration after the rollback")"
            printf '%s\n' "$nginx_erreur" | head -8 | sed 's/^/        nginx -t : /'
            exit 1
        fi
    fi
    exit 0
fi

# --init writes the template and stops: there is no configuration to validate yet
if [[ "$MODE" == "init" ]]; then
    init_config "${CONFIG_EXPLICIT:-${NGINX_LINK_PAGE_ETC_DEFAULT:-/etc/default}/$SCRIPT_NAME.conf}"
fi
# No configuration file at all (and no -c): the template is copied automatically, then the program stops so that it is
# filled in first. Written to /etc/default when that folder is writable (root), otherwise to ~/.nginx-link-page.conf.
if (( ${#CFG_FICHIERS[@]} == 0 )) && [[ -z "$CONFIG_EXPLICIT" ]]; then
    cible="${NGINX_LINK_PAGE_ETC_DEFAULT:-/etc/default}/$SCRIPT_NAME.conf"
    if [[ ! -d "$(dirname "$cible")" || ! -w "$(dirname "$cible")" ]]; then
        cible="${HOME:-/root}/.$SCRIPT_NAME.conf"
    fi
    init_config "$cible" auto
fi

# ---- validation ----
PROBLEMES=()
valeur_ou() { local v="${CFG[$1]:-}"; [[ -n "$v" ]] && printf '%s' "$v" || printf '%s' "$2"; }

# 1.24: every key of the files must be known (a mistyped key was ignored without a word: PAGE_3_THEMS=all, SITE_LANGAUGE=en)
readonly CLES_SITE="BASE_URL DESCRIPTION DESCRIPTION_EN FOOTER FOOTER_EN HEADING HEADING_EN LANGUAGE LOGO_ALT LOGO_URL SHARE_DESCRIPTION SHARE_DESCRIPTION_EN SHARE_IMAGE_URL SHARE_TITLE SHARE_TITLE_EN TITLE TITLE_EN"
readonly CLES_EVENTS="ODOO_DB ODOO_KEY_FILE ODOO_LOGIN ODOO_URL"      # 1.34: upcoming events read in Odoo
readonly CLES_LIEN="FROM ICON ICON_DARK LABEL LABEL_EN MENU PAGES STYLE UNTIL URL"
readonly CLES_PAGE="ACCENT AVATAR BUTTONS CLICKS DIR ENABLED ENGINE EVENTS LANGUAGES PATH QR SCRIPT SHARE SWITCH THEME THEMES TITLE TITLE_EN"
cle_connue() {   # cle_connue KEY: 0 when KEY is read by the program
    local k="$1" s
    if [[ "$k" =~ ^SITE_(.+)$ ]]; then for s in $CLES_SITE; do [[ "${BASH_REMATCH[1]}" == "$s" ]] && return 0; done; return 1; fi
    if [[ "$k" =~ ^LINK_[0-9]+_(.+)$ ]]; then for s in $CLES_LIEN; do [[ "${BASH_REMATCH[1]}" == "$s" ]] && return 0; done; return 1; fi
    if [[ "$k" =~ ^PAGE_[0-9]+_(.+)$ ]]; then for s in $CLES_PAGE; do [[ "${BASH_REMATCH[1]}" == "$s" ]] && return 0; done; return 1; fi
    if [[ "$k" =~ ^EVENTS_(.+)$ ]]; then for s in $CLES_EVENTS; do [[ "${BASH_REMATCH[1]}" == "$s" ]] && return 0; done; return 1; fi
    return 1
}
cle_proche() {   # cle_proche KEY: the closest known key (same LINK_n or PAGE_n number), or nothing; needs python3
    local k="$1" num=1 s candidats=()
    [[ "$k" =~ ^[A-Z]+_([0-9]+)_ ]] && num="${BASH_REMATCH[1]}"
    for s in $CLES_SITE; do candidats+=("SITE_$s"); done
    for s in $CLES_EVENTS; do candidats+=("EVENTS_$s"); done
    for s in $CLES_LIEN; do candidats+=("LINK_${num}_$s"); done
    for s in $CLES_PAGE; do candidats+=("PAGE_${num}_$s"); done
    command -v python3 >/dev/null 2>&1 || return 0
    python3 -I -c 'import difflib, sys; m = difflib.get_close_matches(sys.argv[1], sys.argv[2:], 1, 0.7); print(m[0] if m else "")' "$k" "${candidats[@]}" 2>/dev/null || true
}
for ligne_inv in ${LIGNES_INVALIDES[@]+"${LIGNES_INVALIDES[@]}"}; do
    PROBLEMES+=("$ligne_inv : $(m "ligne ignorée, pas de forme CLE=VALEUR" "line ignored, not in the form KEY=VALUE")")
done
while IFS= read -r cle; do
    [[ -z "$cle" ]] && continue
    cle_connue "$cle" && continue
    proche="$(cle_proche "$cle")"
    PROBLEMES+=("$cle ($(m "clé inconnue" "unknown key"), ${CFG_LIGNE[$cle]:-?})${proche:+ : $(m "vouliez-vous dire" "did you mean") $proche ?}")
done < <(printf '%s\n' "${!CFG[@]}" | sort)
URL_RE='^https://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+$'
CHEMIN_RE='^/[A-Za-z0-9_-]+/$'

# SITE_BASE_URL (optional, https://): base for relative addresses such as /event/ in LINK_n_URL, icons and logo
SITE_BASE_URL_V=$(valeur_ou SITE_BASE_URL "")
LE_DIR="${NGINX_LINK_PAGE_LETSENCRYPT_DIR:-/etc/letsencrypt/live}"
# base_depuis_certificat: the server has one domain; certbot names each certificate folder after it.
# Prints https://DOMAINE/ when exactly one folder with a fullchain.pem exists, returns 1 otherwise.
base_depuis_certificat() {
    local d nom
    local -a noms=()
    [[ -d "$LE_DIR" ]] || return 1
    for d in "$LE_DIR"/*/; do
        [[ -f "${d}fullchain.pem" ]] || continue
        nom="${d%/}"; nom="${nom##*/}"
        noms+=("$nom")
    done
    (( ${#noms[@]} == 1 )) || return 1
    printf 'https://%s/' "${noms[0]}"
}
SITE_BASE_SOURCE="SITE_BASE_URL"
if [[ -z "$SITE_BASE_URL_V" ]] && nom_base="$(base_depuis_certificat)"; then
    SITE_BASE_URL_V="$nom_base"; SITE_BASE_SOURCE="certificat / certificate"
fi
# 1.13: "/" alone (the root of the site, SITE_BASE_URL) is a valid relative path too; "//" and ".." stay refused
REL_RE='^(/|/?[A-Za-z0-9][A-Za-z0-9._~%?#=&+/-]*)$'
# resoudre_url VALEUR: prints the absolute https:// address, returns 1 when it cannot be resolved
resoudre_url() {
    local v="$1" abs
    if [[ "$v" =~ $URL_RE ]]; then printf '%s' "$v"; return 0; fi
    [[ -n "$SITE_BASE_URL_V" && "$v" =~ $REL_RE && "$v" != *..* ]] || return 1
    abs="${SITE_BASE_URL_V%/}/${v#/}"
    [[ "$abs" =~ $URL_RE ]] || return 1
    printf '%s' "$abs"
}

SITE_TITLE_V=$(valeur_ou SITE_TITLE "")
SITE_HEADING_V=$(valeur_ou SITE_HEADING "$SITE_TITLE_V")
SITE_DESCRIPTION_V=$(valeur_ou SITE_DESCRIPTION "")
SITE_LANGUAGE_V=$(valeur_ou SITE_LANGUAGE fr)
SITE_FOOTER_V=$(valeur_ou SITE_FOOTER "")
SITE_TITLE_EN_V=$(valeur_ou SITE_TITLE_EN "")
SITE_HEADING_EN_V=$(valeur_ou SITE_HEADING_EN "")
SITE_DESCRIPTION_EN_V=$(valeur_ou SITE_DESCRIPTION_EN "")
SITE_FOOTER_EN_V=$(valeur_ou SITE_FOOTER_EN "")
SITE_LOGO_URL_V=$(valeur_ou SITE_LOGO_URL "")
SITE_LOGO_ALT_V=$(valeur_ou SITE_LOGO_ALT "$SITE_TITLE_V")
# 1.10: preview shown by LinkedIn, Facebook, Mastodon... when the page address is shared (Open Graph). All optional:
# without SITE_SHARE_IMAGE_URL the logo is used; without the texts, the title and the description of the page.
SITE_SHARE_IMAGE_URL_V=$(valeur_ou SITE_SHARE_IMAGE_URL "")
SITE_SHARE_TITLE_V=$(valeur_ou SITE_SHARE_TITLE "")
SITE_SHARE_TITLE_EN_V=$(valeur_ou SITE_SHARE_TITLE_EN "")
SITE_SHARE_DESCRIPTION_V=$(valeur_ou SITE_SHARE_DESCRIPTION "")
SITE_SHARE_DESCRIPTION_EN_V=$(valeur_ou SITE_SHARE_DESCRIPTION_EN "")
if [[ -n "$SITE_BASE_URL_V" ]] && ! [[ "$SITE_BASE_URL_V" =~ $URL_RE ]]; then
    PROBLEMES+=("SITE_BASE_URL doit etre une adresse https:// / must be an https:// address")
fi
if [[ -n "$SITE_LOGO_URL_V" ]] && abs="$(resoudre_url "$SITE_LOGO_URL_V")"; then SITE_LOGO_URL_V="$abs"; fi
if [[ -n "$SITE_SHARE_IMAGE_URL_V" ]] && abs="$(resoudre_url "$SITE_SHARE_IMAGE_URL_V")"; then SITE_SHARE_IMAGE_URL_V="$abs"; fi
SNIPPETS_DIR="${NGINX_LINK_PAGE_SNIPPETS_DIR:-/etc/nginx/snippets}"
LIEN_FICHIER="$SNIPPETS_DIR/liens-publics.conf"

[[ -n "$SITE_TITLE_V" ]] || PROBLEMES+=("SITE_TITLE absent / missing")
[[ "$SITE_LANGUAGE_V" =~ ^(fr|en)$ ]] || PROBLEMES+=("SITE_LANGUAGE=$SITE_LANGUAGE_V (fr ou en / fr or en)")
if [[ -n "$SITE_LOGO_URL_V" ]] && ! [[ "$SITE_LOGO_URL_V" =~ $URL_RE ]]; then
    PROBLEMES+=("SITE_LOGO_URL doit etre une adresse https:// ou un chemin avec SITE_BASE_URL / must be an https:// address or a path with SITE_BASE_URL")
fi

if [[ -n "$SITE_SHARE_IMAGE_URL_V" ]] && ! [[ "$SITE_SHARE_IMAGE_URL_V" =~ $URL_RE ]]; then
    PROBLEMES+=("SITE_SHARE_IMAGE_URL doit etre une adresse https:// ou un chemin avec SITE_BASE_URL / must be an https:// address or a path with SITE_BASE_URL")
fi
if [[ -n "$SITE_SHARE_IMAGE_URL_V" && -z "$SITE_BASE_URL_V" ]]; then
    PROBLEMES+=("SITE_SHARE_IMAGE_URL demande SITE_BASE_URL (l'apercu exige l'adresse publique complete de l'image) / needs SITE_BASE_URL (the preview requires the full public address of the image)")
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
# 1.26: LINK_m_MENU=n puts link m in the menu of link n (a button that opens its links below it); one level only
declare -A MENU_ENFANTS=() EST_ENFANT=()
for i in ${LIENS_N[@]+"${LIENS_N[@]}"}; do
    mv="${CFG[LINK_${i}_MENU]:-}"
    [[ -z "$mv" ]] && continue
    if [[ ! "$mv" =~ ^[0-9]+$ || " ${LIENS_N[*]} " != *" $((10#$mv)) "* ]]; then
        PROBLEMES+=("LINK_${i}_MENU=$mv : $(m "le lien $mv n'existe pas (LINK_${mv}_LABEL)" "link $mv does not exist (LINK_${mv}_LABEL)")")
        continue
    fi
    mv=$((10#$mv))
    if (( mv == i )); then
        PROBLEMES+=("LINK_${i}_MENU=$mv : $(m "un lien ne peut pas être dans son propre menu" "a link cannot be in its own menu")")
        continue
    fi
    MENU_ENFANTS[$mv]+="$i "; EST_ENFANT[$i]=1
done
for mv in "${!MENU_ENFANTS[@]}"; do
    if [[ -n "${CFG[LINK_${mv}_MENU]:-}" ]]; then
        PROBLEMES+=("LINK_${mv}_MENU : $(m "le lien $mv est un menu : un menu ne peut pas être dans un autre menu (un seul niveau)" "link $mv is a menu: a menu cannot be in another menu (one level only)")")
    fi
    if [[ -n "${CFG[LINK_${mv}_URL]:-}" ]]; then
        PROBLEMES+=("LINK_${mv}_URL : $(m "le lien $mv est un menu (LINK_n_MENU=$mv) : il n'a pas d'adresse, retirer LINK_${mv}_URL" "link $mv is a menu (LINK_n_MENU=$mv): it has no address, remove LINK_${mv}_URL")")
    fi
done
for i in "${!EST_ENFANT[@]}"; do
    if [[ -n "${CFG[LINK_${i}_PAGES]:-}" ]]; then
        PROBLEMES+=("LINK_${i}_PAGES : $(m "le lien $i est dans un menu : il va sur les pages de son menu (LINK_${CFG[LINK_${i}_MENU]}_PAGES)" "link $i is in a menu: it goes on the pages of its menu (LINK_${CFG[LINK_${i}_MENU]}_PAGES)")")
    fi
done
for i in "${LIENS_N[@]}"; do
    lab="${CFG[LINK_${i}_LABEL]:-}"; url="${CFG[LINK_${i}_URL]:-}"
    [[ -n "$lab" && ${#lab} -le 80 ]] || PROBLEMES+=("LINK_${i}_LABEL vide ou trop long (80 caracteres max) / empty or too long")
    [[ -z "${CFG[LINK_${i}_LABEL_EN]:-}" || ${#CFG[LINK_${i}_LABEL_EN]} -le 80 ]] || PROBLEMES+=("LINK_${i}_LABEL_EN trop long (80 caracteres max) / too long (80 characters max)")
    if [[ -n "$url" ]] && abs="$(resoudre_url "$url")"; then url="$abs"; CFG[LINK_${i}_URL]="$abs"; fi
    [[ -n "${MENU_ENFANTS[$i]:-}" || "$url" =~ $URL_RE ]] || PROBLEMES+=("LINK_${i}_URL doit etre une adresse https:// ou un chemin relatif (SITE_BASE_URL, ou un seul certificat sur le serveur) / must be an https:// address or a relative path (SITE_BASE_URL, or a single certificate on the server)")
    for cle in LINK_${i}_ICON LINK_${i}_ICON_DARK; do
        ic="${CFG[$cle]:-}"
        [[ -z "$ic" ]] && continue
        if [[ "$ic" != builtin:* ]] && abs="$(resoudre_url "$ic")"; then ic="$abs"; CFG[$cle]="$abs"; fi
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
# 1.25: LINK_n_PAGES: the pages that show the link (N, N-M, comma list, or all; default: every page)
pages_du_lien() {   # pages_du_lien N: page numbers of link N, one per line; return 1 when the value is invalid
    local v="${CFG[LINK_${1}_PAGES]:-all}" morceau a b q morceaux=()
    v="${v//[[:space:]]/}"
    if [[ "${v,,}" == all ]]; then printf '%s\n' ${PAGES_N[@]+"${PAGES_N[@]}"}; return 0; fi
    [[ "$v" =~ ^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$ ]] || return 1
    IFS=',' read -r -a morceaux <<< "$v"
    for morceau in "${morceaux[@]}"; do
        a=$((10#${morceau%-*})); b=$((10#${morceau#*-}))
        (( a >= 1 && a <= b )) || return 1
        for ((q = a; q <= b; q++)); do printf '%s\n' "$q"; done
    done
}
declare -A LIEN_SUR_PAGE=()      # "LINK:PAGE" -> 1
for i in ${LIENS_N[@]+"${LIENS_N[@]}"}; do
    if ! liste_pages="$(pages_du_lien "$i")"; then
        PROBLEMES+=("LINK_${i}_PAGES=${CFG[LINK_${i}_PAGES]} : $(m "numéros de page N, N-M, séparés par des virgules, ou all (ex. 2-4 ou 1,3)" "page numbers N, N-M, separated by commas, or all (e.g. 2-4 or 1,3)")")
        continue
    fi
    for q in $liste_pages; do
        if [[ " ${PAGES_N[*]:-} " != *" $q "* ]]; then
            PROBLEMES+=("LINK_${i}_PAGES=${CFG[LINK_${i}_PAGES]} : $(m "la page $q n'existe pas (pages : ${PAGES_N[*]:-aucune})" "page $q does not exist (pages: ${PAGES_N[*]:-none})")")
            continue
        fi
        LIEN_SUR_PAGE["$i:$q"]=1
    done
done
liens_de_la_page() {   # liens_de_la_page P: link numbers shown on page P, in order (1.26: without the links of a menu, drawn inside it)
    local n
    for n in ${LIENS_N[@]+"${LIENS_N[@]}"}; do
        [[ -z "${EST_ENFANT[$n]:-}" && -n "${LIEN_SUR_PAGE[$n:$1]:-}" ]] && printf '%s\n' "$n"
    done
    return 0
}
# 1.27: dated links: LINK_n_FROM / LINK_n_UNTIL (YYYY-MM-DD, local date, both included); a daily task rebuilds the pages
AUJOURDHUI="${NGINX_LINK_PAGE_TODAY:-$(date +%F)}"
date_valide() { [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && date -d "$1" +%F >/dev/null 2>&1 && [[ "$(date -d "$1" +%F)" == "$1" ]]; }
for i in ${LIENS_N[@]+"${LIENS_N[@]}"}; do
    sv="${CFG[LINK_${i}_STYLE]:-normal}"                     # 1.31: featured link
    [[ "$sv" =~ ^(normal|featured)$ ]] || PROBLEMES+=("LINK_${i}_STYLE=$sv (normal $(m "ou" "or") featured)")
    for cle in FROM UNTIL; do
        dv="${CFG[LINK_${i}_${cle}]:-}"
        [[ -z "$dv" ]] && continue
        date_valide "$dv" || PROBLEMES+=("LINK_${i}_${cle}=$dv : $(m "date AAAA-MM-JJ attendue (ex. 2026-11-21)" "date YYYY-MM-DD expected (e.g. 2026-11-21)")")
    done
    if [[ -n "${CFG[LINK_${i}_FROM]:-}" && -n "${CFG[LINK_${i}_UNTIL]:-}" && "${CFG[LINK_${i}_FROM]}" > "${CFG[LINK_${i}_UNTIL]}" ]]; then
        PROBLEMES+=("LINK_${i}_FROM=${CFG[LINK_${i}_FROM]} > LINK_${i}_UNTIL=${CFG[LINK_${i}_UNTIL]} : $(m "le lien ne serait jamais affiché" "the link would never be shown")")
    fi
done
LIENS_DATES=0
for i in ${LIENS_N[@]+"${LIENS_N[@]}"}; do [[ -n "${CFG[LINK_${i}_FROM]:-}${CFG[LINK_${i}_UNTIL]:-}" ]] && LIENS_DATES=1; done
# 1.34: PAGE_n_EVENTS=N: the N next published events of Odoo (event.event), read with a read-only account and its API key
EVENEMENTS_MAX=0
EVENTS_URL_V="$(valeur_ou EVENTS_ODOO_URL "${SITE_BASE_URL_V%/}")"; EVENTS_URL_V="${EVENTS_URL_V%/}"
EVENTS_CLE_V="$(valeur_ou EVENTS_ODOO_KEY_FILE "${NGINX_LINK_PAGE_ETC_DEFAULT:-/etc/default}/$SCRIPT_NAME.odoo-key")"
for i in ${PAGES_N[@]+"${PAGES_N[@]}"}; do
    ev="$(valeur_ou "PAGE_${i}_EVENTS" 0)"
    if [[ ! "$ev" =~ ^[0-9]+$ ]] || (( 10#$ev > 10 )); then
        PROBLEMES+=("PAGE_${i}_EVENTS=$ev : $(m "nombre d'événements de 0 à 10" "number of events from 0 to 10")"); continue
    fi
    (( 10#$ev > EVENEMENTS_MAX )) && EVENEMENTS_MAX=$((10#$ev))
done
if (( EVENEMENTS_MAX > 0 )); then
    [[ "$EVENTS_URL_V" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]] || PROBLEMES+=("EVENTS_ODOO_URL=${EVENTS_URL_V:-?} : $(m "adresse https:// du site Odoo (par défaut SITE_BASE_URL)" "https:// address of the Odoo site (SITE_BASE_URL by default)")")
    [[ -n "${CFG[EVENTS_ODOO_DB]:-}" ]] || PROBLEMES+=("EVENTS_ODOO_DB : $(m "base de données Odoo manquante (PAGE_n_EVENTS)" "Odoo database missing (PAGE_n_EVENTS)")")
    [[ -n "${CFG[EVENTS_ODOO_LOGIN]:-}" ]] || PROBLEMES+=("EVENTS_ODOO_LOGIN : $(m "compte Odoo en lecture seule manquant (PAGE_n_EVENTS)" "read-only Odoo account missing (PAGE_n_EVENTS)")")
    if [[ ! -e "$EVENTS_CLE_V" ]]; then
        PROBLEMES+=("EVENTS_ODOO_KEY_FILE=$EVENTS_CLE_V : $(m "fichier absent (la clé d'API seule, chmod 600)" "file missing (the API key only, chmod 600)")")
    elif [[ -r "$EVENTS_CLE_V" && -n "$(find "$EVENTS_CLE_V" -perm /077 2>/dev/null)" ]]; then
        PROBLEMES+=("EVENTS_ODOO_KEY_FILE=$EVENTS_CLE_V : $(m "lisible par d'autres comptes : chmod 600" "readable by other accounts: chmod 600")")
    fi
fi
lien_visible() {   # lien_visible N: 0 when link N is shown today (no dates, or today between LINK_n_FROM and LINK_n_UNTIL)
    local du="${CFG[LINK_${1}_FROM]:-}" au="${CFG[LINK_${1}_UNTIL]:-}"
    [[ -n "$du" && "$AUJOURDHUI" < "$du" ]] && return 1
    [[ -n "$au" && "$AUJOURDHUI" > "$au" ]] && return 1
    return 0
}
enfants_visibles() {   # enfants_visibles N: links of menu N shown today
    local e
    for e in ${MENU_ENFANTS[$1]:-}; do lien_visible "$e" && printf '%s\n' "$e"; done
    return 0
}
liens_visibles_de_la_page() {   # liens_visibles_de_la_page P: links of page P shown today (a menu without any link shown today is hidden)
    local n
    for n in $(liens_de_la_page "$1"); do
        lien_visible "$n" || continue
        [[ -n "${MENU_ENFANTS[$n]:-}" && -z "$(enfants_visibles "$n")" ]] && continue
        printf '%s\n' "$n"
    done
    return 0
}
nb_liens_page() {   # nb_liens_page P: number of links shown on page P, the links of its menus included
    local n t=0 e
    for n in $(liens_de_la_page "$1"); do
        if [[ -n "${MENU_ENFANTS[$n]:-}" ]]; then for e in ${MENU_ENFANTS[$n]}; do t=$((t + 1)); done; else t=$((t + 1)); fi
    done
    echo "$t"
}
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
    if [[ "$enabled" =~ ^(yes|oui|1)$ && ${#LIENS_N[@]} -gt 0 && -z "$(liens_de_la_page "$i")" ]]; then      # 1.25
        PROBLEMES+=("PAGE_${i} : $(m "aucun lien ne va sur cette page (voir les LINK_n_PAGES)" "no link goes on this page (see the LINK_n_PAGES)")")
    fi
    case "$engine" in
        littlelink) ;;
        linkstack) PROBLEMES+=("${pre}ENGINE=linkstack : moteur reserve, pas encore pris en charge (PHP/Laravel + base de donnees) / engine reserved, not yet supported") ;;
        *) PROBLEMES+=("${pre}ENGINE=$engine (moteurs pris en charge / supported: $MOTEURS_PRIS_EN_CHARGE)") ;;
    esac
    [[ "$chemin" =~ $CHEMIN_RE ]] || PROBLEMES+=("${pre}PATH=$chemin (ex. /links/ ou /links2/)")
    if [[ -n "$chemin" ]]; then
        # 1.13: the paths are reached whatever their case (/L/ = /l/): two paths that differ only by their case are the same page
        [[ -z "${CHEMINS_VUS[${chemin,,}]:-}" ]] || PROBLEMES+=("${pre}PATH=$chemin deja utilise (majuscules et minuscules confondues) / already used (case ignored)")
        CHEMINS_VUS["${chemin,,}"]=1
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
    if [[ ! "$theme" =~ ^($THEMES_RE)$ ]]; then
        if [[ "$theme" == *,* || "$theme" =~ ^[[:space:]]*all[[:space:]]*$ ]]; then      # 1.20: a list or "all" belongs to PAGE_n_THEMES
            PROBLEMES+=("${pre}THEME=$theme : un seul thème ici ; pour le bouton Thème, écrire ${pre}THEMES=$theme (avec un S) / one theme only here; for the Theme button, write ${pre}THEMES=$theme (with an S)")
        else
            PROBLEMES+=("${pre}THEME=$theme ($THEMES_LISTE)")
        fi
    fi
    if [[ "$theme" =~ ^($THEMES_MAISON)$ && ! -r "$THEMES_CSS" ]]; then
        PROBLEMES+=("${pre}THEME=$theme : $THEMES_CSS absent (livre avec le depot) / missing (shipped with the repository)")
    fi
    if [[ "$theme" =~ ^(tux-quebec|tux-flag|tux-poster)$ && ! -r "$THEMES_LINKSTACK/images/$theme.jpg" ]]; then    # 1.21 to 1.23: background image of the theme
        PROBLEMES+=("${pre}THEME=$theme : $THEMES_LINKSTACK/images/$theme.jpg absent (livre avec le depot) / missing (shipped with the repository)")
    fi
    if [[ "$theme" == ls-* && ! -r "$THEMES_LINKSTACK/linkstack.css" ]]; then
        PROBLEMES+=("${pre}THEME=$theme : $THEMES_LINKSTACK/linkstack.css absent (livre avec le depot) / missing (shipped with the repository)")
    fi
    langues_v="$(valeur_ou "${pre}LANGUAGES" "$SITE_LANGUAGE_V")"
    [[ "$langues_v" =~ ^(fr|en|fr,en|en,fr)$ ]] || PROBLEMES+=("${pre}LANGUAGES=$langues_v (fr, en, fr,en ou en,fr / fr, en, fr,en or en,fr)")
    [[ "$(valeur_ou "${pre}BUTTONS" default)" =~ ^(default|brand)$ ]] || PROBLEMES+=("${pre}BUTTONS=$(valeur_ou "${pre}BUTTONS" default) (default ou brand)")
    [[ "$(valeur_ou "${pre}AVATAR" none)" =~ ^(none|soft|rounded)$ ]] || PROBLEMES+=("${pre}AVATAR=$(valeur_ou "${pre}AVATAR" none) (none, soft ou rounded)")
    acc_v="$(valeur_ou "${pre}ACCENT" "")"
    [[ -z "$acc_v" || "$acc_v" =~ ^#[0-9A-Fa-f]{6}$ ]] || PROBLEMES+=("${pre}ACCENT=$acc_v (vide ou couleur #RRGGBB)")
    [[ "$(valeur_ou "${pre}SWITCH" no)" =~ ^(yes|no)$ ]] || PROBLEMES+=("${pre}SWITCH=$(valeur_ou "${pre}SWITCH" no) (yes ou no)")
    # 1.17: PAGE_n_THEMES: themes offered by the "Theme" button (comma list, or all)
    for t in $(themes_offerts "$(valeur_ou "${pre}THEMES" "")"); do
        [[ "$t" =~ ^($THEMES_RE)$ ]] || PROBLEMES+=("${pre}THEMES : theme inconnu / unknown theme « $t » ($THEMES_LISTE, ou all)")
    done
    # 1.18: PAGE_n_SCRIPT and PAGE_n_SHARE (yes or no, yes by default)
    [[ "$(valeur_ou "${pre}SCRIPT" yes)" =~ ^(yes|no)$ ]] || PROBLEMES+=("${pre}SCRIPT=$(valeur_ou "${pre}SCRIPT" yes) (yes ou no)")
    [[ "$(valeur_ou "${pre}SHARE" yes)" =~ ^(yes|no)$ ]] || PROBLEMES+=("${pre}SHARE=$(valeur_ou "${pre}SHARE" yes) (yes ou no)")
    [[ "$(valeur_ou "${pre}CLICKS" no)" =~ ^(yes|no)$ ]] || PROBLEMES+=("${pre}CLICKS=$(valeur_ou "${pre}CLICKS" no) (yes ou no)")      # 1.30
    qr_v="$(valeur_ou "${pre}QR" no)"                                                   # 1.32: QR code of the page
    [[ "$qr_v" =~ ^(yes|no)$ ]] || PROBLEMES+=("${pre}QR=$qr_v (yes ou no)")
    if [[ "$qr_v" == yes ]]; then
        command -v qrencode >/dev/null 2>&1 || PROBLEMES+=("${pre}QR=yes : $(m "qrencode absent (sudo apt install qrencode)" "qrencode not found (sudo apt install qrencode)")")
        [[ -n "$SITE_BASE_URL_V" ]] || PROBLEMES+=("${pre}QR=yes : $(m "adresse publique inconnue : SITE_BASE_URL (ou un seul certificat sur le serveur)" "public address unknown: SITE_BASE_URL (or a single certificate on the server)")")
    fi
    if [[ "$(valeur_ou "${pre}SCRIPT" yes)" == yes && ! -r "$LINK_PAGE_JS" ]]; then
        PROBLEMES+=("${pre}SCRIPT=yes : $LINK_PAGE_JS absent (livre avec le depot) / missing (shipped with the repository)")
    fi
    if [[ -n "$(valeur_ou "${pre}THEMES" "")" && ! -r "$THEME_MENU_CSS" ]]; then
        PROBLEMES+=("${pre}THEMES : $THEME_MENU_CSS absent (livre avec le depot) / missing (shipped with the repository)")
    fi
done

# ---- summary of the files read and of the pages ----
if (( ${#CFG_FICHIERS[@]} > 0 )); then
    echo "Configuration lue / configuration read : ${CFG_FICHIERS[*]}"
else
    echo "Configuration lue / configuration read : aucune / none (valeurs par defaut / defaults)"
fi
echo "  $(m "Site" "Site") : ${SITE_TITLE_V:-?} · ${#LIENS_N[@]} $(m "liens" "links") · ${#PAGES_N[@]} $(m "page(s)" "page(s)")"
if [[ -n "$SITE_BASE_URL_V" ]]; then
    echo "  $(m "Base des chemins relatifs" "Base for relative paths") : $SITE_BASE_URL_V ($SITE_BASE_SOURCE)"
fi
for i in "${PAGES_N[@]}"; do
    echo "    PAGE_${i} : $(valeur_ou "PAGE_${i}_PATH" "?") -> $(valeur_ou "PAGE_${i}_DIR" "?") · $(valeur_ou "PAGE_${i}_ENGINE" littlelink) · $(valeur_ou "PAGE_${i}_ENABLED" yes) · $(nb_liens_page "$i") $(m "liens" "links")"
done

if (( ${#PROBLEMES[@]} > 0 )); then
    if (( ${#CFG_FICHIERS[@]} == 0 )); then
        echo "  $(m "Astuce : sudo $SCRIPT_NAME.sh --init cree la configuration a partir du modele." "Tip: sudo $SCRIPT_NAME.sh --init creates the configuration from the template.")" >&2
    fi
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

# telecharger URL BASE [MAX_BYTES] : downloads an image to BASE.ext; sets RES_FICHIER (full path) on success.
# 1.14: on failure, RES_ERREUR gives the reason (too big, HTTP code, network, not an image), shown by the callers.
RES_FICHIER=""
RES_ERREUR=""
telecharger() {
    local url="$1" base="$2" max="${3:-$MAX_ASSET_BYTES}" tmp type ext code rc http taille
    RES_FICHIER=""; RES_ERREUR=""
    tmp=$(mktemp) || return 1
    code=$(curl -fsSL --proto '=https' --tlsv1.2 --max-time 30 --max-filesize "$max" -w '%{http_code} %{size_download}' -o "$tmp" "$url" 2>/dev/null)
    rc=$?
    http="${code%% *}"; taille="${code##* }"
    if (( rc == 0 )) && [[ "$taille" =~ ^[0-9]+$ ]] && (( taille > max )); then rc=63; fi
    if (( rc != 0 )); then
        case "$rc" in
            63) RES_ERREUR="$(m "fichier trop gros (plus de $((max / 1024)) Kio)" "file too big (more than $((max / 1024)) KiB)")" ;;
            22) RES_ERREUR="$(m "le serveur repond HTTP $http" "the server answers HTTP $http")" ;;
            28) RES_ERREUR="$(m "delai depasse (30 s)" "timed out (30 s)")" ;;
            6|7|35|60) RES_ERREUR="$(m "serveur injoignable ou certificat refuse (curl $rc)" "server unreachable or certificate refused (curl $rc)")" ;;
            *) RES_ERREUR="$(m "echec du telechargement (curl $rc)" "download failed (curl $rc)")" ;;
        esac
        rm -f "$tmp"; return 1
    fi
    type=$(type_image "$tmp") || { RES_ERREUR="$(m "ce n'est pas une image PNG, JPEG, WebP ou SVG" "not a PNG, JPEG, WebP or SVG image")"; rm -f "$tmp"; return 1; }
    case "$type" in jpg) ext=jpg ;; *) ext="$type" ;; esac
    if install -m 644 "$tmp" "$base.$ext"; then RES_FICHIER="$base.$ext"; fi
    rm -f "$tmp"
    [[ -n "$RES_FICHIER" ]]
}

# periode_lien N: " (du ... au ... : affiché / caché aujourd'hui)" for a dated link, nothing otherwise
periode_lien() {
    local du="${CFG[LINK_${1}_FROM]:-}" au="${CFG[LINK_${1}_UNTIL]:-}"
    [[ -z "$du$au" ]] && return 0
    local periode="${du:+$(m "du" "from") $du}"
    [[ -n "$au" ]] && periode+="${periode:+ }$(m "au" "until") $au"
    local etat
    if lien_visible "$1"; then etat="$(m "affiché aujourd'hui" "shown today")"; else etat="$(m "caché aujourd'hui" "hidden today")"; fi
    printf ' (%s : %s)' "$periode" "$etat"
}
# ---- --check: nothing is written, no network ----
echo
echo "$(m "Verification" "Check") :"
ok "$(m "configuration valide" "valid configuration")"
for i in "${LIENS_N[@]}"; do
    [[ -n "${EST_ENFANT[$i]:-}" ]] && continue                 # 1.26: shown under its menu
    if [[ -n "${MENU_ENFANTS[$i]:-}" ]]; then
        echo "  - ${CFG[LINK_${i}_LABEL]} -> $(m "menu" "menu")"
        for e in ${MENU_ENFANTS[$i]}; do echo "      - ${CFG[LINK_${e}_LABEL]} -> ${CFG[LINK_${e}_URL]:-}$(periode_lien "$e")"; done
    else
        echo "  - ${CFG[LINK_${i}_LABEL]} -> ${CFG[LINK_${i}_URL]:-}$(periode_lien "$i")"
    fi
done
# 1.30: --clicks: requests "GET PATH/go/N" answered 302 in the nginx access logs (rotated and .gz included), per page and link
if [[ "$MODE" == "clicks" ]]; then
    shopt -s nullglob
    # shellcheck disable=SC2206   # the variable is a glob on purpose (access.log, access.log.1, access.log.2.gz...)
    journaux=(${NGINX_LINK_PAGE_ACCESS_LOGS:-/var/log/nginx/access.log*})
    shopt -u nullglob
    echo
    if (( ${#journaux[@]} == 0 )); then err "$(m "aucun journal d'accès" "no access log") (${NGINX_LINK_PAGE_ACCESS_LOGS:-/var/log/nginx/access.log*})"; exit 1; fi
    for j in "${journaux[@]}"; do [[ -r "$j" ]] || { err "$(m "journal illisible (lancer avec sudo)" "log not readable (run with sudo)") : $j"; exit 1; }; done
    echo "$(m "Clics" "Clicks") ($(m "journaux" "logs") : ${#journaux[@]} $(m "fichier(s)" "file(s)"), ${journaux[0]%/*}) :"
    avec_clics=0
    for i in "${PAGES_N[@]}"; do
        [[ "$(valeur_ou "PAGE_${i}_CLICKS" no)" == yes ]] || continue
        avec_clics=1
        chemin="$(valeur_ou "PAGE_${i}_PATH" "")"
        echo "  PAGE_${i} ${chemin} :"
        resultat="$(zcat -f -- "${journaux[@]}" 2>/dev/null | awk -v p="\"GET ${chemin}go/" '
            { d = index($0, p); if (!d) next
              reste = substr($0, d + length(p)); n = reste; sub(/[^0-9].*/, "", n); if (n == "") next
              apres = substr(reste, index(reste, "\"") + 1); split(apres, f, " "); if (f[1] != "302") next
              total[n]++; if (!((n, $1) in vu)) { vu[n, $1] = 1; ips[n]++ } }
            END { for (n in total) printf "%d %d %s\n", total[n], ips[n], n }' | sort -k1,1nr -k3,3n)"
        if [[ -z "$resultat" ]]; then echo "    $(m "aucun clic" "no click")"; continue; fi
        while read -r total ips n; do
            printf '    %6s %s, %s %s  LINK_%s %s\n' "$total" "$(m "clics" "clicks")" "$ips" "$(m "adresses" "addresses")" "$n" "${CFG[LINK_${n}_LABEL]:-?}"
        done <<< "$resultat"
    done
    (( avec_clics )) || attn "$(m "aucune page avec PAGE_n_CLICKS=yes : les liens vont directement à leur adresse" "no page with PAGE_n_CLICKS=yes: the links go straight to their address")"
    exit 0
fi
# 1.28: --check-links: every address is requested (HEAD, then GET when HEAD is refused); dead links make the exit code 1
if [[ "$MODE" == "links" ]]; then
    command -v curl >/dev/null 2>&1 || { err "curl $(m "absent" "not found")"; exit 1; }
    echo
    echo "$(m "Vérification des liens" "Checking the links") :"
    morts=0; douteux=0
    for i in "${LIENS_N[@]}"; do
        [[ -n "${MENU_ENFANTS[$i]:-}" ]] && continue                 # a menu has no address
        url="${CFG[LINK_${i}_URL]:-}"
        code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -L -I -A "$SCRIPT_NAME/$SCRIPT_VERSION" "$url" 2>/dev/null || true)"
        if [[ ! "$code" =~ ^[23] ]]; then
            code2="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -L -r 0-0 -A "$SCRIPT_NAME/$SCRIPT_VERSION" "$url" 2>/dev/null || true)"
            [[ "$code2" =~ ^[0-9]{3}$ && "$code2" != 000 ]] && code="$code2"
        fi
        code="${code:-000}"
        quoi="LINK_${i} ${CFG[LINK_${i}_LABEL]} -> $url"
        case "$code" in
            2??|3??) ok "$code $quoi" ;;
            401|403|429|999) attn "$code $quoi : $(m "le site refuse les robots ou demande une connexion : à vérifier dans un navigateur" "the site refuses robots or asks for a sign-in: check it in a browser")"; douteux=$((douteux + 1)) ;;
            000) err "$(m "pas de réponse" "no answer") $quoi : $(m "adresse, nom de domaine ou certificat à vérifier" "check the address, the domain name or the certificate")"; morts=$((morts + 1)) ;;
            *) err "$code $quoi : $(m "lien mort ou en erreur" "dead link or error")"; morts=$((morts + 1)) ;;
        esac
    done
    echo
    if (( morts )); then
        err "$(m "$morts lien(s) mort(s) ou en erreur, $douteux à vérifier à la main" "$morts dead or failing link(s), $douteux to check by hand")"
        exit 1
    fi
    ok "$(m "aucun lien mort" "no dead link")$( (( douteux )) && echo " ($douteux $(m "à vérifier à la main" "to check by hand"))")"
    exit 0
fi
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
SCRIPT_PAGE=()            # 1.18: yes when the page loads js/link-page.js (script-src of its Content-Security-Policy)
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
    # 1.11: LittleLink Extended, at its pinned tag and commit. Not reachable or another commit: [ATTN], the pages are built
    # without it (a configuration that uses one of its icons then stops on "unknown built-in icon").
    if timeout 180 git clone --quiet --depth 1 --branch "$LINKPAGE_EXT_TAG" "$LINKPAGE_EXT_REPO" "$TMP/littlelink-extended" >/dev/null 2>&1; then
        sha_ext=$(git -C "$TMP/littlelink-extended" rev-parse HEAD 2>/dev/null || true)
        if [[ "$sha_ext" != "$LINKPAGE_EXT_SHA" ]]; then
            attn "$(m "LittleLink Extended $LINKPAGE_EXT_TAG : commit ${sha_ext:-inconnu} different du commit epingle : non utilise." "LittleLink Extended $LINKPAGE_EXT_TAG: commit ${sha_ext:-unknown} differs from the pinned commit: not used.")"
        elif [[ -f "$TMP/littlelink-extended/css/brands-extended.css" && -d "$TMP/littlelink-extended/images/icons-extended" ]]; then
            cp "$TMP/littlelink-extended/css/brands-extended.css" "$TMP/littlelink/css/"
            cp -r "$TMP/littlelink-extended/images/icons-extended" "$TMP/littlelink/images/"
            ok "LittleLink Extended $LINKPAGE_EXT_TAG (${sha_ext:0:12})"
        else
            attn "$(m "LittleLink Extended : css/brands-extended.css ou images/icons-extended/ absent : non utilise." "LittleLink Extended: css/brands-extended.css or images/icons-extended/ missing: not used.")"
        fi
    else
        attn "$(m "LittleLink Extended $LINKPAGE_EXT_TAG non telechargeable (reseau ?) : pages construites sans ses icones." "LittleLink Extended $LINKPAGE_EXT_TAG cannot be cloned (network?): pages built without its icons.")"
    fi
fi

# 2) logo and icons: downloaded once, checked, kept in the work folder (pages load nothing from other sites)
LOGO_LOCAL=""
if [[ -n "$SITE_LOGO_URL_V" ]]; then
    telecharger "$SITE_LOGO_URL_V" "$TMP/assets/images/site/logo" || { err "$(m "logo non telechargeable ou pas une image : $SITE_LOGO_URL_V ($RES_ERREUR)" "logo not downloadable or not an image: $SITE_LOGO_URL_V ($RES_ERREUR)")"; exit 1; }
    LOGO_LOCAL="images/site/${RES_FICHIER##*/}"
    ok "$(m "logo" "logo") -> $LOGO_LOCAL"
fi
# 1.10: image of the preview on social networks. PNG, JPEG or WebP only (LinkedIn and Facebook do not show an SVG).
# Without SITE_SHARE_IMAGE_URL: the logo, when it is not an SVG (small square preview).
PARTAGE_LOCAL=""; PARTAGE_CARTE="summary"
if [[ -n "$SITE_SHARE_IMAGE_URL_V" ]]; then
    telecharger "$SITE_SHARE_IMAGE_URL_V" "$TMP/assets/images/site/share" "$MAX_SHARE_BYTES" || { err "$(m "image d'apercu non telechargeable ou pas une image : $SITE_SHARE_IMAGE_URL_V ($RES_ERREUR)" "preview image not downloadable or not an image: $SITE_SHARE_IMAGE_URL_V ($RES_ERREUR)")"; exit 1; }
    if [[ "$RES_FICHIER" == *.svg ]]; then
        err "$(m "SITE_SHARE_IMAGE_URL : image SVG refusee par les reseaux sociaux ; fournir un PNG ou un JPEG (1200 x 627 conseille)" "SITE_SHARE_IMAGE_URL: SVG images are not shown by social networks; give a PNG or a JPEG (1200 x 627 advised)")"; exit 1
    fi
    PARTAGE_LOCAL="images/site/${RES_FICHIER##*/}"; PARTAGE_CARTE="summary_large_image"
    ok "$(m "image d'apercu (reseaux sociaux)" "preview image (social networks)") -> $PARTAGE_LOCAL"
elif [[ -n "$LOGO_LOCAL" && "$LOGO_LOCAL" != *.svg && -n "$SITE_BASE_URL_V" ]]; then
    PARTAGE_LOCAL="$LOGO_LOCAL"
    attn "$(m "apercu sur les reseaux sociaux : logo utilise (SITE_SHARE_IMAGE_URL absent ; image de 1200 x 627 conseillee)" "preview on social networks: logo used (SITE_SHARE_IMAGE_URL missing; a 1200 x 627 image is advised)")"
else
    attn "$(m "apercu sur les reseaux sociaux : aucune image (definir SITE_SHARE_IMAGE_URL et SITE_BASE_URL)" "preview on social networks: no image (set SITE_SHARE_IMAGE_URL and SITE_BASE_URL)")"
fi
declare -A ICONE_RESOLUE=()
RES_ICONE=""
icone_resoudre() {   # icone_resoudre VALEUR CLE : sets RES_ICONE (path relative to a page folder)
    local v="$1" cle="$2" nom
    RES_ICONE=""
    if [[ "$v" == builtin:* ]]; then
        nom="${v#builtin:}"
        # 1.11: LittleLink first, then LittleLink Extended (same builtin:NAME)
        if [[ -f "$TMP/littlelink/images/icons/$nom.svg" ]]; then RES_ICONE="images/icons/$nom.svg"; return 0; fi
        if [[ -f "$TMP/littlelink/images/icons-extended/$nom.svg" ]]; then RES_ICONE="images/icons-extended/$nom.svg"; return 0; fi
        err "$(m "icone integree inconnue : $nom" "unknown built-in icon: $nom")"; return 1
    fi
    if [[ -n "${ICONE_RESOLUE[$v]:-}" ]]; then RES_ICONE="${ICONE_RESOLUE[$v]}"; return 0; fi
    telecharger "$v" "$TMP/assets/images/site/icon-$cle" || { err "$(m "icone non telechargeable ou pas une image : $v ($RES_ERREUR)" "icon not downloadable or not an image: $v ($RES_ERREUR)")"; return 1; }
    ICONE_RESOLUE[$v]="images/site/${RES_FICHIER##*/}"
    RES_ICONE="${ICONE_RESOLUE[$v]}"
}
declare -A ICONE_CLAIR=() ICONE_SOMBRE=() BOUTON_MARQUE=()
for i in "${LIENS_N[@]}"; do
    ic="${CFG[LINK_${i}_ICON]:-builtin:generic-website}"
    icone_resoudre "$ic" "$i-clair" || exit 1; ICONE_CLAIR[$i]="$RES_ICONE"
    # LittleLink brand button for a built-in icon (facebook -> button-faceb); no match: default button
    BOUTON_MARQUE[$i]=""
    if [[ "$ic" == builtin:* ]]; then
        cand="${ic#builtin:}"
        case "$cand" in facebook) cand=faceb ;; youtube) cand=yt ;; linkedin) cand=linked ;; esac
        if grep -Eq "\.button-${cand}[^a-zA-Z0-9_-]" "$TMP/littlelink/css/brands.css" "$TMP/littlelink/css/brands-extended.css" 2>/dev/null; then BOUTON_MARQUE[$i]="button-$cand"; fi
    fi
    ICONE_SOMBRE[$i]=""
    if [[ -n "${CFG[LINK_${i}_ICON_DARK]:-}" ]]; then
        icone_resoudre "${CFG[LINK_${i}_ICON_DARK]}" "$i-sombre" || exit 1; ICONE_SOMBRE[$i]="$RES_ICONE"
    fi
done

# 1.34: upcoming events of Odoo, read once per language of the pages that show them (a failure leaves the section out)
if (( EVENEMENTS_MAX > 0 )); then
    for lg in $(for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do (( 10#$(valeur_ou "PAGE_${i}_EVENTS" 0) > 0 )) && valeur_ou "PAGE_${i}_LANGUAGES" "$SITE_LANGUAGE_V" | tr ',' '\n'; done | sort -u); do
        if ODOO_URL="$EVENTS_URL_V" ODOO_DB="${CFG[EVENTS_ODOO_DB]:-}" ODOO_LOGIN="${CFG[EVENTS_ODOO_LOGIN]:-}" ODOO_KEY_FILE="$EVENTS_CLE_V" \
           python3 -I "$SCRIPT_DIR/apps/link-page-events.py" "$EVENEMENTS_MAX" "$lg" > "$TMP/events-$lg.tsv" 2> "$TMP/events-$lg.err"; then
            ok "$(m "événements Odoo" "Odoo events") ($lg) : $(wc -l < "$TMP/events-$lg.tsv") ($EVENTS_URL_V)"
        else
            : > "$TMP/events-$lg.tsv"
            attn "$(m "événements Odoo non lus, section omise" "Odoo events not read, section left out") ($lg) : $(head -1 "$TMP/events-$lg.err")"
        fi
    done
fi
# 3) one folder per enabled page: assets + index.html generated with the page's theme and title
# theme_nom THEME / bascule_libelle THEME: labels in the page language
theme_nom() {
    if [[ "$L_LANG" == en ]]; then
        case "$1" in light) echo light ;; dark) echo dark ;; aurora) echo "northern lights" ;; maple) echo maple ;; river) echo river ;;
                     terminal) echo terminal ;; tux) echo Tux ;; ls-aurora) echo "Aurora (LinkStack)" ;; ls-dark) echo "Dark (LinkStack)" ;;
                     tux-quebec) echo "Quebec Tux" ;; quebec) echo "Quebec flag" ;; boreal) echo "boreal forest" ;; sunset) echo sunset ;; winter) echo winter ;; tux-flag) echo "Tux and the Quebec flag" ;; tux-poster) echo "Tux poster" ;;
                     ls-dawn) echo "Dawn (LinkStack)" ;; ls-misty-rain) echo "Misty Rain (LinkStack)" ;; *) echo automatic ;; esac
    else
        case "$1" in light) echo clair ;; dark) echo sombre ;; aurora) echo "aurore boréale" ;; maple) echo érable ;; river) echo fleuve ;;
                     terminal) echo terminal ;; tux) echo Tux ;; ls-aurora) echo "Aurora (LinkStack)" ;; ls-dark) echo "Dark (LinkStack)" ;;
                     tux-quebec) echo "Tux québécois" ;; quebec) echo fleurdelisé ;; boreal) echo "forêt boréale" ;; sunset) echo "coucher de soleil" ;; winter) echo hiver ;; tux-flag) echo "Tux et drapeau du Québec" ;; tux-poster) echo "affiche Tux" ;;
                     ls-dawn) echo "Dawn (LinkStack)" ;; ls-misty-rain) echo "Misty Rain (LinkStack)" ;; *) echo automatique ;; esac
    fi
}
# theme_base THEME: light or dark (choice of the icons of LINK_n_ICON_DARK, theme of the second page with PAGE_n_SWITCH), auto for auto
theme_base() {
    case "$1" in dark|aurora|terminal|tux|quebec|boreal|sunset|ls-*) echo dark ;; light|maple|river|tux-quebec|winter|tux-flag|tux-poster) echo light ;; *) echo auto ;; esac
}
# theme_couleur THEME: colour of the browser bar (meta theme-color) of the 5 themes of link-page-themes.css
theme_couleur() {
    case "$1" in aurora) echo "#0b1026" ;; maple) echo "#b3261e" ;; river) echo "#0e6b7f" ;; terminal) echo "#050805" ;; tux) echo "#1c1f24" ;;
                 tux-quebec) echo "#0033a0" ;; quebec) echo "#003da5" ;; boreal) echo "#0f2318" ;; sunset) echo "#2b1a4a" ;; winter) echo "#dcebf7" ;; tux-flag) echo "#0033a0" ;; tux-poster) echo "#0033a0" ;;
                 ls-aurora) echo "#24123d" ;; ls-dark) echo "#1f232e" ;; ls-dawn) echo "#223344" ;; ls-misty-rain) echo "#181b24" ;; esac
}
bascule_libelle() {
    if [[ "$L_LANG" == en ]]; then echo "Switch to $(theme_nom "$1") theme"; else echo "Passer au thème $(theme_nom "$1")"; fi
}

# libelle_lien N: link label in the language of the page being generated (LINK_N_LABEL_EN if set)
libelle_lien() {
    if [[ "$L_LANG" == en && -n "${CFG[LINK_${1}_LABEL_EN]:-}" ]]; then printf '%s' "${CFG[LINK_${1}_LABEL_EN]}"; else printf '%s' "${CFG[LINK_${1}_LABEL]}"; fi
}
# preparer_dossier DOSSIER: LittleLink assets and site images for one language folder
preparer_dossier() {
    local d="$1"
    mkdir -p "$d/images/site"
    cp -r "$TMP/littlelink/css" "$TMP/littlelink/fonts" "$d/"
    cp -r "$TMP/littlelink/images" "$d/"
    if [[ -r "$THEMES_CSS" ]]; then install -m 644 "$THEMES_CSS" "$d/css/themes.css"; fi        # 1.15: the 5 added themes
    if [[ -r "$THEMES_LINKSTACK/linkstack.css" ]]; then                                        # 1.16: the 4 LinkStack themes, their images and fonts
        install -m 644 "$THEMES_LINKSTACK/linkstack.css" "$d/css/themes-linkstack.css"
        install -m 644 "$THEMES_LINKSTACK/LICENSES.md" "$d/css/themes-linkstack-LICENSES.md"
        mkdir -p "$d/images/themes" "$d/fonts/themes"
        install -m 644 "$THEMES_LINKSTACK"/images/* "$d/images/themes/"
        install -m 644 "$THEMES_LINKSTACK"/fonts/* "$d/fonts/themes/"
    fi
    cp -r "$TMP/assets/images/site/." "$d/images/site/"
}

# 1.18: csp_script: script-src of the page being generated ('self' with js/link-page.js, 'none' otherwise)
csp_script() { if [[ "$P_JS" == yes ]]; then echo "'self'"; else echo "'none'"; fi; }
# menu_contient REGEX: a theme of the "Theme" button matches REGEX
menu_contient() { local t; for t in ${P_MENU[@]+"${P_MENU[@]}"}; do [[ "$t" =~ $1 ]] && return 0; done; return 1; }

# page_a_extras: 0 when the page being generated (P_LIENS) has a featured link, in a menu or not, or shows its QR code
# 1.34: date_evenement "YYYY-MM-DD HH:MM": date and time in the language of the page; delai_jours BEGIN_DAY END_DAY: "dans 9 jours"...
date_evenement() {
    local jour="${1% *}" heure="${1#* }" js ms h mi
    js=$(LC_ALL=C date -d "$jour" +%u); ms=$(( 10#$(LC_ALL=C date -d "$jour" +%m) )); h=$((10#${heure%:*})); mi="${heure#*:}"
    if [[ "$L_LANG" == en ]]; then
        local jours=(x Monday Tuesday Wednesday Thursday Friday Saturday Sunday) mois=(x January February March April May June July August September October November December)
        printf '%s, %s %s · %s:%s' "${jours[$js]}" "${mois[$ms]}" "$((10#${jour##*-}))" "$h" "$mi"
    else
        local jours=(x lundi mardi mercredi jeudi vendredi samedi dimanche) mois=(x janvier février mars avril mai juin juillet août septembre octobre novembre décembre)
        printf '%s %s %s · %s h%s' "${jours[$js]}" "$((10#${jour##*-}))" "${mois[$ms]}" "$h" "$( [[ "$mi" != 00 ]] && echo " $mi")"
    fi
}
# tp FR EN: text in the language of the page being generated (m follows the language of the messages of the program)
tp() { if [[ "${L_LANG:-fr}" == en ]]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }
delai_jours() {
    local d
    d=$(( ( $(date -d "$1 12:00" +%s) - $(date -d "$AUJOURDHUI 12:00" +%s) ) / 86400 ))
    if (( d < 0 )); then [[ "$AUJOURDHUI" > "$2" ]] && return 0; tp "en cours" "now on"; return 0; fi
    case "$d" in
        0) tp "aujourd'hui" "today" ;;
        1) tp "demain" "tomorrow" ;;
        *) tp "dans $d jours" "in $d days" ;;
    esac
}
# section_evenements: the section of the upcoming events of the page being generated (P_EVENTS lines of $TMP/events-LANG.tsv)
section_evenements() {
    local f="$TMP/events-$L_LANG.tsv" debut fin nom adresse quand n=0
    (( ${P_EVENTS:-0} > 0 )) && [[ -s "$f" ]] || return 0
    echo "      <section class=\"events\" aria-labelledby=\"events-title\">"
    echo "        <h2 id=\"events-title\">$(tp "Prochains événements" "Upcoming events")</h2>"
    while IFS=$'\t' read -r debut fin nom adresse; do
        (( n >= P_EVENTS )) && break
        n=$((n + 1))
        quand="$(date_evenement "$debut")"
        [[ -n "$(delai_jours "${debut% *}" "$fin")" ]] && quand+=" · $(delai_jours "${debut% *}" "$fin")"
        echo "        <a class=\"button button-default event-link\" href=\"$(html_echap "$adresse")\" target=\"_blank\" rel=\"noopener noreferrer\"><span class=\"event-when\">$(html_echap "$quand")</span><span class=\"event-name\">$(html_echap "$nom")</span></a>"
    done < "$f"
    echo "      </section>"
}
page_a_extras() {
    local n e
    [[ "${P_QR:-no}" == yes ]] && return 0
    (( ${P_EVENTS:-0} > 0 )) && return 0                      # 1.34
    for n in ${P_LIENS[@]+"${P_LIENS[@]}"}; do
        [[ "${CFG[LINK_${n}_STYLE]:-normal}" == featured ]] && return 0
        for e in ${MENU_ENFANTS[$n]:-}; do [[ "${CFG[LINK_${e}_STYLE]:-normal}" == featured ]] && return 0; done
    done
    return 1
}
# icone_lien N: <img> (or <picture>) of the icon of link N for the page being generated (theme base in $base, set by genere_index)
icone_lien() {
    local clair="${ICONE_CLAIR[$1]}" sombre="${ICONE_SOMBRE[$1]}" media
    if [[ -n "$sombre" && "$P_JS" == yes && ${#P_MENU[@]} -gt 0 ]]; then    # 1.18: the script sets the media of <source> per theme
        case "$base" in dark) media="all" ;; light) media="not all" ;; *) media="(prefers-color-scheme: dark)" ;; esac
        printf '<picture><source data-icon-dark media="%s" srcset="%s"><img class="icon" aria-hidden="true" src="%s" alt=""></picture>' "$media" "$sombre" "$clair"
    elif [[ -n "$sombre" && "$base" == "auto" ]]; then
        printf '<picture><source media="(prefers-color-scheme: dark)" srcset="%s"><img class="icon" aria-hidden="true" src="%s" alt=""></picture>' "$sombre" "$clair"
    elif [[ -n "$sombre" && "$base" == "dark" ]]; then
        printf '<img class="icon" aria-hidden="true" src="%s" alt="">' "$sombre"
    else
        printf '<img class="icon" aria-hidden="true" src="%s" alt="">' "$clair"
    fi
}
# bouton_lien N: the button of link N (1.26: shared by the page and the menus)
bouton_lien() {
    local classe_bouton="button-default"
    if [[ "$P_BOUTONS" == brand && -n "${BOUTON_MARQUE[$1]:-}" ]]; then classe_bouton="${BOUTON_MARQUE[$1]}"; fi
    [[ "${CFG[LINK_${1}_STYLE]:-normal}" == featured ]] && classe_bouton+=" button-featured"      # 1.31
    local cible="${CFG[LINK_${1}_URL]}"
    [[ "${P_CLICS:-no}" == yes ]] && cible="${P_CHEMIN}go/$1"       # 1.30: redirection by nginx, written in its log
    echo "        <a class=\"button $classe_bouton\" href=\"$(html_echap "$cible")\" target=\"_blank\" rel=\"noopener noreferrer\">"
    echo "          $(icone_lien "$1")$(html_echap "$(libelle_lien "$1")")</a>"
}

genere_index() {   # genere_index DOSSIER THEME TITRE [FICHIER] [CIBLE_BASCULE] [LIBELLE_BASCULE]
    local dossier="$1" theme="$2" titre="$3" fichier="${4:-index.html}" cible="${5:-}" libelle="${6:-}" t f
    local classe lab url clair sombre classe_bouton i e base attrs donnees media
    classe="theme-$theme"                               # 1.15: theme-auto, theme-light, theme-dark or one of link-page-themes.css
    base="$(theme_base "$theme")"
    {
        echo "<!DOCTYPE html>"
        echo "<!-- Genere par $SCRIPT_NAME.sh $SCRIPT_VERSION a partir de la configuration. Ne pas editer a la main. -->"
        echo "<!-- Built on LittleLink (MIT, https://github.com/sethcottle/littlelink), tag $LINKPAGE_TAG. -->"
        if [[ "$P_JS" == yes ]]; then                     # 1.18: data read by js/link-page.js
            attrs=" data-page=\"$(html_echap "$P_CHEMIN")\""
            if (( ${#P_MENU[@]} )); then
                donnees=""
                for t in "${P_MENU[@]}"; do donnees+="$t|$(theme_base "$t")|$(theme_couleur "$t") "; done
                attrs+=" data-themes=\"${donnees% }\""
            fi
            if [[ -n "${L_AUTRE_HREF:-}" ]]; then attrs+=" data-other-lang=\"$L_AUTRE_LANG\" data-other-href=\"$(html_echap "$L_AUTRE_HREF")\""; fi
            echo "<html class=\"$classe\" lang=\"$L_LANG\"$attrs>"
        else
            echo "<html class=\"$classe\" lang=\"$L_LANG\">"
        fi
        echo "  <head>"
        echo "    <meta charset=\"utf-8\">"
        echo "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        echo "    <title>$(html_echap "$titre")</title>"
        if [[ -n "$L_DESCRIPTION" ]]; then echo "    <meta name=\"description\" content=\"$(html_echap "$L_DESCRIPTION")\">"; fi
        # 1.10: Open Graph (LinkedIn, Facebook, Mastodon...) and Twitter card. Addresses must be absolute: only with a public base.
        echo "    <meta property=\"og:type\" content=\"website\">"
        echo "    <meta property=\"og:site_name\" content=\"$(html_echap "$SITE_TITLE_V")\">"
        echo "    <meta property=\"og:title\" content=\"$(html_echap "${L_PARTAGE_TITRE:-$titre}")\">"
        if [[ -n "${L_PARTAGE_DESCRIPTION:-$L_DESCRIPTION}" ]]; then echo "    <meta property=\"og:description\" content=\"$(html_echap "${L_PARTAGE_DESCRIPTION:-$L_DESCRIPTION}")\">"; fi
        if [[ "$L_LANG" == en ]]; then echo "    <meta property=\"og:locale\" content=\"en\">"; else echo "    <meta property=\"og:locale\" content=\"fr\">"; fi
        if [[ -n "$L_URL_PUBLIQUE" ]]; then
            echo "    <meta property=\"og:url\" content=\"$(html_echap "$L_URL_PUBLIQUE")\">"
            if [[ -n "$PARTAGE_LOCAL" ]]; then
                echo "    <meta property=\"og:image\" content=\"$(html_echap "${L_URL_PUBLIQUE}${PARTAGE_LOCAL}")\">"
                echo "    <meta property=\"og:image:alt\" content=\"$(html_echap "$SITE_LOGO_ALT_V")\">"
                echo "    <meta name=\"twitter:card\" content=\"$PARTAGE_CARTE\">"
                echo "    <meta name=\"twitter:image\" content=\"$(html_echap "${L_URL_PUBLIQUE}${PARTAGE_LOCAL}")\">"
            fi
        fi
        if [[ -n "$(theme_couleur "$theme")" ]]; then
            echo "    <meta name=\"theme-color\" content=\"$(theme_couleur "$theme")\">"
        else
            echo "    <meta name=\"theme-color\" content=\"#ffffff\" media=\"(prefers-color-scheme: light)\">"
            echo "    <meta name=\"theme-color\" content=\"#121212\" media=\"(prefers-color-scheme: dark)\">"
        fi
        echo "    <meta name=\"referrer\" content=\"strict-origin-when-cross-origin\">"
        echo "    <meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src 'self'; style-src 'self'; font-src 'self'; script-src $(csp_script); object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'\">"
        echo "    <link rel=\"stylesheet\" href=\"css/reset.css\">"
        echo "    <link rel=\"stylesheet\" href=\"css/style.css\">"
        echo "    <link rel=\"stylesheet\" href=\"css/brands.css\">"
        if [[ -f "$dossier/css/brands-extended.css" ]]; then echo "    <link rel=\"stylesheet\" href=\"css/brands-extended.css\">"; fi
        # 1.18: with the script, the menu changes the theme in place: the style sheets of every offered theme are loaded
        if [[ -f "$dossier/css/themes.css" ]] && { [[ -n "$(theme_couleur "$theme")" && "$theme" != ls-* ]] || { [[ "$P_JS" == yes ]] && menu_contient "^($THEMES_MAISON)\$"; }; }; then
            echo "    <link rel=\"stylesheet\" href=\"css/themes.css\">"
        fi
        if [[ -f "$dossier/css/themes-linkstack.css" ]] && { [[ "$theme" == ls-* ]] || { [[ "$P_JS" == yes ]] && menu_contient '^ls-'; }; }; then
            echo "    <link rel=\"stylesheet\" href=\"css/themes-linkstack.css\">"
        fi
        if (( ${#P_MENU[@]} )) || [[ "$P_JS" == yes && "$P_PARTAGE" == yes ]]; then echo "    <link rel=\"stylesheet\" href=\"css/theme-menu.css\">"; fi
        if [[ -f "$dossier/css/link-menu.css" ]]; then echo "    <link rel=\"stylesheet\" href=\"css/link-menu.css\">"; fi      # 1.26
        if [[ -f "$dossier/css/extras.css" ]]; then echo "    <link rel=\"stylesheet\" href=\"css/extras.css\">"; fi            # 1.31
        if [[ -f "$dossier/css/accent.css" ]]; then echo "    <link rel=\"stylesheet\" href=\"css/accent.css\">"; fi
        if [[ "$P_JS" == yes ]]; then echo "    <script src=\"js/link-page.js\"></script>"; fi      # 1.18: in <head>: theme set before drawing
        echo "  </head>"
        echo "  <body>"
        if [[ "$P_JS" == yes && "$P_PARTAGE" == yes ]]; then   # 1.18: "Share" button, shown by the script when the browser can share or copy
            if [[ "$L_LANG" == en ]]; then
                echo "    <button class=\"share-button\" type=\"button\" hidden data-url=\"$(html_echap "$L_URL_PUBLIQUE")\" data-done=\"Link copied\">Share</button>"
            else
                echo "    <button class=\"share-button\" type=\"button\" hidden data-url=\"$(html_echap "$L_URL_PUBLIQUE")\" data-done=\"Lien copié\">Partager</button>"
            fi
        fi
        if (( ${#P_MENU[@]} )); then                         # 1.17: "Theme" button: one complete page per theme (fallback without script)
            echo "    <details class=\"theme-menu\">"
            echo "      <summary>$( [[ "$L_LANG" == en ]] && echo Theme || echo Thème )</summary>"
            echo "      <ul>"
            for t in "${P_MENU[@]}"; do
                if [[ "$t" == "$P_THEME" ]]; then f="index.html"; else f="theme-$t.html"; fi
                if [[ "$t" == "$theme" ]]; then
                    echo "        <li><a href=\"$f\" data-theme=\"$t\" aria-current=\"page\">$(html_echap "$(theme_nom "$t")")</a></li>"
                else
                    echo "        <li><a href=\"$f\" data-theme=\"$t\">$(html_echap "$(theme_nom "$t")")</a></li>"
                fi
            done
            echo "      </ul>"
            echo "    </details>"
        fi
        if [[ "$theme" == ls-misty-rain ]] || { [[ "$P_JS" == yes ]] && menu_contient '^ls-misty-rain$'; }; then   # 1.16: rain of Misty Rain, pure CSS
            printf '    <div class="ls-rain" aria-hidden="true">%s</div>\n' "$(printf '<i></i>%.0s' {1..24})"
        fi
        echo "    <div class=\"container\"><div class=\"column\"><main>"
        if [[ -n "$LOGO_LOCAL" ]]; then
            echo "      <img class=\"avatar avatar--$P_AVATAR\" src=\"$LOGO_LOCAL\" width=\"128\" height=\"128\" alt=\"$(html_echap "$SITE_LOGO_ALT_V")\">"
        fi
        echo "      <h1>$(html_echap "$L_HEADING")</h1>"
        if [[ -n "$L_DESCRIPTION" ]]; then echo "      <p>$(html_echap "$L_DESCRIPTION")</p>"; fi
        echo "      <nav class=\"button-stack\" aria-label=\"$( [[ "$L_LANG" == en ]] && echo Links || echo Liens )\">"
        for i in ${P_LIENS[@]+"${P_LIENS[@]}"}; do          # 1.25: only the links of this page (LINK_n_PAGES)
            if [[ -n "${MENU_ENFANTS[$i]:-}" ]]; then        # 1.26: menu: a button that opens its links below it (<details>, no script)
                echo "        <details class=\"link-menu\">"
                echo "          <summary class=\"button button-default$( [[ "${CFG[LINK_${i}_STYLE]:-normal}" == featured ]] && echo " button-featured")\">$(icone_lien "$i")$(html_echap "$(libelle_lien "$i")")</summary>"
                echo "          <div class=\"link-menu-items\">"
                for e in $(enfants_visibles "$i"); do bouton_lien "$e"; done      # 1.27: links shown today
                echo "          </div>"
                echo "        </details>"
            else
                bouton_lien "$i"
            fi
        done
        echo "      </nav>"
        section_evenements                                     # 1.34: upcoming events of Odoo (PAGE_n_EVENTS)
        if [[ -n "$cible" ]]; then
            echo "      <p><a class=\"button button-default\" href=\"$cible\">$(html_echap "$libelle")</a></p>"
        fi
        if [[ -n "${L_AUTRE_HREF:-}" ]]; then
            if [[ "$P_JS" == yes ]]; then
                echo "      <p><a class=\"button button-default\" href=\"$L_AUTRE_HREF\" data-lang=\"$L_AUTRE_LANG\">$(html_echap "$L_AUTRE_LIBELLE")</a></p>"
            else
                echo "      <p><a class=\"button button-default\" href=\"$L_AUTRE_HREF\">$(html_echap "$L_AUTRE_LIBELLE")</a></p>"
            fi
        fi
        if [[ -f "$dossier/qr.svg" ]]; then                  # 1.32: QR code of the page (PNG to download for posters and slides)
            echo "      <p class=\"qr-link\"><a href=\"qr.png\" download><img src=\"qr.svg\" alt=\"\">$( [[ "$L_LANG" == en ]] && echo "QR code of this page" || echo "Code QR de cette page" )</a></p>"
        fi
        echo "    </main>"
        if [[ -n "$L_FOOTER" ]]; then echo "    <footer>$(html_echap "$L_FOOTER")</footer>"; fi
        echo "    </div></div>"
        echo "  </body>"
        echo "</html>"
    } > "$dossier/$fichier"
}

for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do
    site="$TMP/page-$i"
    mkdir -p "$site"
    mapfile -t P_LIENS < <(liens_visibles_de_la_page "$i")   # 1.25: links of this page; 1.27: shown today
    if (( ${#P_LIENS[@]} == 0 )); then attn "PAGE_${i} : $(m "aucun lien affiché aujourd'hui ($AUJOURDHUI, voir LINK_n_FROM et LINK_n_UNTIL)" "no link shown today ($AUJOURDHUI, see LINK_n_FROM and LINK_n_UNTIL)")"; fi
    P_THEME="$(valeur_ou "PAGE_${i}_THEME" auto)"
    P_TITRE="$(valeur_ou "PAGE_${i}_TITLE" "$SITE_TITLE_V")"
    P_BOUTONS="$(valeur_ou "PAGE_${i}_BUTTONS" default)"
    P_AVATAR="$(valeur_ou "PAGE_${i}_AVATAR" none)"
    P_ACCENT="$(valeur_ou "PAGE_${i}_ACCENT" "")"
    P_BASCULE="$(valeur_ou "PAGE_${i}_SWITCH" no)"
    # 1.17: themes of the "Theme" button; the theme of the page comes first; PAGE_n_SWITCH is ignored when the button exists
    P_MENU=()
    if [[ -n "$(valeur_ou "PAGE_${i}_THEMES" "")" ]]; then
        mapfile -t P_MENU < <(themes_offerts "$P_THEME,$(valeur_ou "PAGE_${i}_THEMES" "")")
        if (( ${#P_MENU[@]} < 2 )); then P_MENU=(); fi
        if [[ "$P_BASCULE" == yes && ${#P_MENU[@]} -gt 0 ]]; then
            attn "PAGE_${i}_SWITCH=yes $(m "ignore : le bouton Theme (PAGE_${i}_THEMES) le remplace" "ignored: the Theme button (PAGE_${i}_THEMES) replaces it")"
            P_BASCULE=no
        fi
    fi
    P_CHEMIN="$(valeur_ou "PAGE_${i}_PATH" "")"
    P_LANGUES="$(valeur_ou "PAGE_${i}_LANGUAGES" "$SITE_LANGUAGE_V")"
    IFS=',' read -r -a P_LISTE <<< "$P_LANGUES"
    # 1.18: script of the page: only when it has something to do (theme button, "Share" button or two languages)
    P_PARTAGE="$(valeur_ou "PAGE_${i}_SHARE" yes)"
    P_CLICS="$(valeur_ou "PAGE_${i}_CLICKS" no)"             # 1.30: the links go through PATH/go/N (counted in the nginx logs)
    P_QR="$(valeur_ou "PAGE_${i}_QR" no)"
    P_EVENTS=$((10#$(valeur_ou "PAGE_${i}_EVENTS" 0)))      # 1.34: upcoming events of Odoo                     # 1.32: qr.svg and qr.png of the page, link above the footer
    P_JS=no
    if [[ "$(valeur_ou "PAGE_${i}_SCRIPT" yes)" == yes ]] && { (( ${#P_MENU[@]} )) || [[ "$P_PARTAGE" == yes ]] || (( ${#P_LISTE[@]} == 2 )); }; then
        P_JS=yes
    fi
    SCRIPT_PAGE[i]="$P_JS"
    for k in "${!P_LISTE[@]}"; do
        L_LANG="${P_LISTE[$k]}"
        # the first language is the root page (/liens/); any other language lives in a sub-folder (/liens/en/)
        if (( k == 0 )); then dossier="$site"; else dossier="$site/$L_LANG"; fi
        preparer_dossier "$dossier"
        if [[ "$L_LANG" == en ]]; then
            L_TITRE="$(valeur_ou "PAGE_${i}_TITLE_EN" "${SITE_TITLE_EN_V:-$P_TITRE}")"
            L_HEADING="${SITE_HEADING_EN_V:-$SITE_HEADING_V}"
            L_DESCRIPTION="${SITE_DESCRIPTION_EN_V:-$SITE_DESCRIPTION_V}"
            L_FOOTER="${SITE_FOOTER_EN_V:-$SITE_FOOTER_V}"
        else
            L_TITRE="$P_TITRE"; L_HEADING="$SITE_HEADING_V"; L_DESCRIPTION="$SITE_DESCRIPTION_V"; L_FOOTER="$SITE_FOOTER_V"
        fi
        # 1.10: preview texts and public address of THIS page (og:url, og:image): base + page path (+ language folder)
        if [[ "$L_LANG" == en ]]; then
            L_PARTAGE_TITRE="${SITE_SHARE_TITLE_EN_V:-$SITE_SHARE_TITLE_V}"; L_PARTAGE_DESCRIPTION="${SITE_SHARE_DESCRIPTION_EN_V:-$SITE_SHARE_DESCRIPTION_V}"
        else
            L_PARTAGE_TITRE="$SITE_SHARE_TITLE_V"; L_PARTAGE_DESCRIPTION="$SITE_SHARE_DESCRIPTION_V"
        fi
        L_URL_PUBLIQUE=""
        if [[ -n "$SITE_BASE_URL_V" ]]; then
            L_URL_PUBLIQUE="${SITE_BASE_URL_V%/}/${P_CHEMIN#/}"
            if (( k > 0 )); then L_URL_PUBLIQUE+="$L_LANG/"; fi
        fi
        # link to the other language (two languages only)
        # 1.18: index.html for the first language: the bare path goes back to the second language when the browser prefers it
        L_AUTRE_HREF=""; L_AUTRE_LIBELLE=""; L_AUTRE_LANG=""
        if (( ${#P_LISTE[@]} == 2 )); then
            if (( k == 0 )); then autre="${P_LISTE[1]}"; L_AUTRE_HREF="${P_CHEMIN}${autre}/"; else autre="${P_LISTE[0]}"; L_AUTRE_HREF="${P_CHEMIN}index.html"; fi
            L_AUTRE_LANG="$autre"
            if [[ "$autre" == en ]]; then L_AUTRE_LIBELLE="English"; else L_AUTRE_LIBELLE="Français"; fi
        fi
        if [[ -n "$P_ACCENT" ]]; then
            printf '.button.button-default { --button-background: %s; }\n' "$P_ACCENT" > "$dossier/css/accent.css"
        fi
        if [[ "$P_JS" == yes ]]; then mkdir -p "$dossier/js"; install -m 644 "$LINK_PAGE_JS" "$dossier/js/link-page.js"; fi
        if [[ "$P_QR" == yes ]]; then                          # 1.32: QR code of the public address of this language
            if qrencode -t SVG -l M -m 2 -s 6 -o "$dossier/qr.svg" "$L_URL_PUBLIQUE" && qrencode -t PNG -l M -m 4 -s 12 -o "$dossier/qr.png" "$L_URL_PUBLIQUE"; then
                ok "$(m "code QR" "QR code") : ${L_URL_PUBLIQUE}qr.png"
            else
                attn "$(m "code QR non créé (qrencode)" "QR code not created (qrencode)") : $L_URL_PUBLIQUE"; rm -f "$dossier/qr.svg" "$dossier/qr.png"
            fi
        fi
        if (( ${#P_MENU[@]} )) || [[ "$P_JS" == yes && "$P_PARTAGE" == yes ]]; then
            if [[ -r "$THEME_MENU_CSS" ]]; then install -m 644 "$THEME_MENU_CSS" "$dossier/css/theme-menu.css"; fi
        fi
        if [[ -r "$EXTRAS_CSS" ]] && page_a_extras; then      # 1.31: a featured link (or, 1.32, the QR code) on this page
            install -m 644 "$EXTRAS_CSS" "$dossier/css/extras.css"
        fi
        if [[ -r "$LINK_MENU_CSS" ]]; then                    # 1.26: a menu on this page
            for e in ${P_LIENS[@]+"${P_LIENS[@]}"}; do
                if [[ -n "${MENU_ENFANTS[$e]:-}" ]]; then install -m 644 "$LINK_MENU_CSS" "$dossier/css/link-menu.css"; break; fi
            done
        fi
        if (( ${#P_MENU[@]} )); then
            for t in "${P_MENU[@]}"; do
                if [[ "$t" == "$P_THEME" ]]; then genere_index "$dossier" "$t" "$L_TITRE" index.html
                else genere_index "$dossier" "$t" "$L_TITRE" "theme-$t.html"; fi
            done
        elif [[ "$P_BASCULE" == yes ]]; then
            # second complete page with the other theme (no script: the CSP forbids it); dark for light/auto, light for dark
            if [[ "$(theme_base "$P_THEME")" == dark ]]; then P_AUTRE=light; else P_AUTRE=dark; fi      # 1.15: by the base of the theme
            genere_index "$dossier" "$P_THEME" "$L_TITRE" index.html autre.html "$(bascule_libelle "$P_AUTRE")"
            genere_index "$dossier" "$P_AUTRE" "$L_TITRE" autre.html index.html "$(bascule_libelle "$P_THEME")"
        else
            genere_index "$dossier" "$P_THEME" "$L_TITRE"
        fi
    done
    ok "$(m "page" "page") PAGE_${i} $(m "preparee" "prepared") ($(nb_liens_page "$i") $(m "liens" "links"))"
done

# 1.29: entetes_page PAGE INDENT CACHE: the add_header lines of a page (Content-Security-Policy, nosniff, Referrer-Policy, Cache-Control)
entetes_page() {
    local scr="'none'"
    [[ "${SCRIPT_PAGE[$1]:-no}" == yes ]] && scr="'self'"
    printf '%sadd_header Content-Security-Policy "%s" always;\n' "$2" "default-src 'none'; img-src 'self'; style-src 'self'; font-src 'self'; script-src $scr; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    printf '%sadd_header X-Content-Type-Options "nosniff" always;\n' "$2"
    printf '%sadd_header Referrer-Policy "strict-origin-when-cross-origin" always;\n' "$2"
    printf '%sadd_header Cache-Control "%s" always;' "$2" "$3"
}
# 4) one nginx snippet, one location per enabled page (distinct paths: /liens/ does not catch /liens2/)
LIEN_NOUVEAU="# Genere par $SCRIPT_NAME.sh : ne pas editer a la main."$'\n'
if (( ${#ACTIVES[@]} == 0 )); then
    LIEN_NOUVEAU+="# liens : inactif"$'\n'
else
    LIEN_NOUVEAU+="# liens : actif"$'\n'
    for i in "${ACTIVES[@]}"; do
        chemin_page="$(valeur_ou "PAGE_${i}_PATH" "")"
        dir_page="$(valeur_ou "PAGE_${i}_DIR" "")"
        langues_page="$(valeur_ou "PAGE_${i}_LANGUAGES" "$SITE_LANGUAGE_V")"
        autre_page=""
        if [[ "$langues_page" == *,* ]]; then autre_page="${langues_page#*,}"; fi
        # 1.13: the same path in another case (/LIENS, /Liens/, /LIENS/en/...) is redirected to the configured one (301, query string kept).
        # Regular expression location: nginx tries it only when no exact (=) or ^~ location of the configured path matched, so the
        # configured case never goes through it.
        if [[ "$chemin_page" =~ [A-Za-z] ]]; then
            LIEN_NOUVEAU+="location ~* ^${chemin_page%/}(/.*)?\$ {"$'\n'
            LIEN_NOUVEAU+="    return 301 ${chemin_page%/}\$1\$is_args\$args;"$'\n'
            LIEN_NOUVEAU+="}"$'\n'
        fi
        # /liens (without the final slash) is redirected to /liens/ : the page is reached with or without the slash.
        LIEN_NOUVEAU+="location = ${chemin_page%/} {"$'\n'
        LIEN_NOUVEAU+="    return 301 ${chemin_page};"$'\n'
        LIEN_NOUVEAU+="}"$'\n'
        if [[ -n "$autre_page" ]]; then
            # two languages: the root path goes to the second language when the browser prefers it (Accept-Language)
            LIEN_NOUVEAU+="location = ${chemin_page} {"$'\n'
            LIEN_NOUVEAU+="    if (\$http_accept_language ~* \"^${autre_page}\") {"$'\n'
            LIEN_NOUVEAU+="        return 302 ${chemin_page}${autre_page}/;"$'\n'
            LIEN_NOUVEAU+="    }"$'\n'
            LIEN_NOUVEAU+="    alias ${dir_page}/;"$'\n'
            LIEN_NOUVEAU+="    index index.html;"$'\n'
            LIEN_NOUVEAU+="    limit_except GET HEAD { deny all; }"$'\n'
            LIEN_NOUVEAU+="    add_header Vary \"Accept-Language\" always;"$'\n'
            LIEN_NOUVEAU+="$(entetes_page "$i" "    " "no-cache")"$'\n'
            LIEN_NOUVEAU+="}"$'\n'
        fi
        # 1.30: PAGE_n_CLICKS=yes: one exact location per link of the page, a 302 to its address (counted by --clicks in the access log)
        if [[ "$(valeur_ou "PAGE_${i}_CLICKS" no)" == yes ]]; then
            for n in $(liens_visibles_de_la_page "$i"); do
                for e in $( [[ -n "${MENU_ENFANTS[$n]:-}" ]] && enfants_visibles "$n" || echo "$n" ); do
                    cible="${CFG[LINK_${e}_URL]}"; cible="${cible//\$/%24}"; cible="${cible//\"/%22}"
                    LIEN_NOUVEAU+="location = ${chemin_page}go/$e {"$'\n'
                    LIEN_NOUVEAU+="    add_header Cache-Control \"no-store\" always;"$'\n'
                    LIEN_NOUVEAU+="    return 302 \"$cible\";"$'\n'
                    LIEN_NOUVEAU+="}"$'\n'
                done
            done
        fi
        LIEN_NOUVEAU+="location ^~ ${chemin_page} {"$'\n'
        LIEN_NOUVEAU+="    alias ${dir_page}/;"$'\n'
        LIEN_NOUVEAU+="    index index.html;"$'\n'
        LIEN_NOUVEAU+="    limit_except GET HEAD { deny all; }"$'\n'
        LIEN_NOUVEAU+="$(entetes_page "$i" "    " "no-cache")"$'\n'
        # 1.29: style sheets and scripts kept 1 hour (an update changes them), images and fonts 7 days, by the browsers and by Cloudflare;
        # the pages themselves are checked each time (no-cache). A nested location does not inherit add_header: the headers are repeated.
        for regle in "css|js:public, max-age=3600" "png|jpe?g|webp|gif|svg|ico|woff2?:public, max-age=604800"; do
            LIEN_NOUVEAU+="    location ~* \\.(${regle%%:*})\$ {"$'\n'
            LIEN_NOUVEAU+="        limit_except GET HEAD { deny all; }"$'\n'
            LIEN_NOUVEAU+="$(entetes_page "$i" "        " "${regle#*:}")"$'\n'
            LIEN_NOUVEAU+="    }"$'\n'
        done
        LIEN_NOUVEAU+="}"$'\n'
    done
fi

# 5) install the folders, then the snippet: nginx -t, reload; the previous snippet is restored on refusal
# 1.33: copy of what is replaced (page folders, snippet, daily task), put back by --rollback; not by the daily task (it would replace
# the copy of before a manual update by the same pages every night)
if [[ "${NGINX_LINK_PAGE_NO_BACKUP:-0}" != 1 ]]; then
    nouv="$ETAT_DIR/previous.new"; rm -rf "$nouv"; mkdir -p "$nouv"; : > "$nouv/manifest"
    date '+%Y-%m-%d %H:%M:%S' > "$nouv/date"
    for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do
        dossier="$(valeur_ou "PAGE_${i}_DIR" "")"
        [[ -f "$dossier/index.html" ]] || continue
        mkdir -p "$nouv/page-$i"
        for x in $FICHIERS_GERES; do [[ -e "$dossier/$x" ]] && cp -a "$dossier/$x" "$nouv/page-$i/"; done
        for x in "$dossier"/theme-*.html; do [[ -e "$x" ]] && cp -a "$x" "$nouv/page-$i/"; done
        printf 'page\tpage-%s\t%s\n' "$i" "$dossier" >> "$nouv/manifest"
    done
    if [[ -f "$LIEN_FICHIER" ]]; then cp -a "$LIEN_FICHIER" "$nouv/snippet.conf"; printf 'snippet\tsnippet.conf\t%s\n' "$LIEN_FICHIER" >> "$nouv/manifest"; fi
    cron_f="${NGINX_LINK_PAGE_CRON_DIR:-/etc/cron.d}/$SCRIPT_NAME"
    if [[ -f "$cron_f" ]]; then cp -a "$cron_f" "$nouv/cron"; printf 'cron\tcron\t%s\n' "$cron_f" >> "$nouv/manifest"; else printf 'cron\t-\t%s\n' "$cron_f" >> "$nouv/manifest"; fi
    if grep -q '^page' "$nouv/manifest" || grep -q '^snippet' "$nouv/manifest"; then
        rm -rf "$ETAT_DIR/previous"; mv "$nouv" "$ETAT_DIR/previous"; chmod 700 "$ETAT_DIR"
        ok "$(m "version précédente gardée (--rollback)" "previous version kept (--rollback)") : $ETAT_DIR/previous"
    else
        rm -rf "$nouv"                                     # first install: nothing to put back
    fi
fi
mkdir -p "$SNIPPETS_DIR"
LIEN_ANCIEN=""; [[ -f "$LIEN_FICHIER" ]] && LIEN_ANCIEN=$(cat "$LIEN_FICHIER")
for i in ${ACTIVES[@]+"${ACTIVES[@]}"}; do
    dossier="$(valeur_ou "PAGE_${i}_DIR" "")"
    mkdir -p "$dossier"
    for x in $FICHIERS_GERES; do rm -rf "${dossier:?}/$x"; done      # 1.18: js; 1.32: qr; 1.33: FICHIERS_GERES
    rm -f "${dossier:?}"/theme-*.html                    # 1.17: pages of the "Theme" button of the previous run
    cp -r "$TMP/page-$i/." "$dossier/" || { err "$(m "copie impossible dans" "copy failed in") $dossier"; exit 1; }
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
    # 1.27: dated links: a daily task (/etc/cron.d/nginx-link-page) rebuilds the pages at 00:05; removed when no link is dated
    CRON_FICHIER="${NGINX_LINK_PAGE_CRON_DIR:-/etc/cron.d}/$SCRIPT_NAME"
    if (( LIENS_DATES || EVENEMENTS_MAX > 0 )); then         # 1.34: the events of Odoo too
        mkdir -p "$(dirname "$CRON_FICHIER")"
        {
            echo "# Genere par $SCRIPT_NAME.sh : liens dates (LINK_n_FROM, LINK_n_UNTIL) ou evenements Odoo (PAGE_n_EVENTS), pages reconstruites chaque jour. Ne pas editer a la main."
            echo "SHELL=/bin/bash"
            echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            echo "5 0 * * * root NGINX_LINK_PAGE_NO_BACKUP=1 $SCRIPT_DIR/$SCRIPT_NAME.sh --update --yes${CONFIG_EXPLICIT:+ -c $CONFIG_EXPLICIT} 2>&1 | logger -t $SCRIPT_NAME"
        } > "$CRON_FICHIER.tmp" && chmod 644 "$CRON_FICHIER.tmp" && mv -f "$CRON_FICHIER.tmp" "$CRON_FICHIER"
        ok "$(m "liens datés ou événements : pages reconstruites chaque jour à 00:05" "dated links or events: pages rebuilt every day at 00:05") ($CRON_FICHIER)"
    elif [[ -f "$CRON_FICHIER" ]]; then
        rm -f "$CRON_FICHIER"
        ok "$(m "plus de lien daté ni d'événement : tâche quotidienne retirée" "no dated link nor event any more: daily task removed") ($CRON_FICHIER)"
    fi
else
    if [[ -n "$LIEN_ANCIEN" ]]; then printf '%s\n' "$LIEN_ANCIEN" > "$LIEN_FICHIER"; else printf '%s\n' "# liens : inactif" > "$LIEN_FICHIER"; fi
    err "$(m "nginx -t refuse la configuration : ancien fragment restaure, nginx NON recharge" "nginx -t refuses the configuration: previous snippet restored, nginx NOT reloaded")"
    printf '%s\n' "$nginx_erreur" | head -8 | sed 's/^/        nginx -t : /'
    exit 1
fi
