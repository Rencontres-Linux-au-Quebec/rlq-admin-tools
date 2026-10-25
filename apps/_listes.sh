# shellcheck shell=bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _listes.sh - common reader (bash) of the WHITE LIST and the PLACES: same files and same syntax as apps/_listes.py (see its header).
#   /etc/default/nginx-tools-white-list.conf (seulement /etc/default), /etc/default/nginx-tools-ip-location.conf puis ~/.nginx-tools-ip-location.conf.
# To be sourced (". apps/_listes.sh"); does nothing by itself.
#

LISTES_BLANCHE_DEFAUT="/etc/default/nginx-tools-white-list.conf"
LISTES_LIEUX_DEFAUT="/etc/default/nginx-tools-ip-location.conf"
LISTES_SEP=$'\037'             # field separator of listes_lire (never a tab: read merges it when a field is empty)

# listes_fichier_blanche: path of the white list READ - the new file; otherwise the old list apps/team-ips.list
# (transition, seulement sans surcharge d'environnement) ; rien si aucun n'existe.
listes_fichier_blanche() {
    local nouveau="${NGINX_TOOLS_WHITE_LIST:-$LISTES_BLANCHE_DEFAUT}" ancien="${SCRIPT_DIR:-.}/apps/team-ips.list"
    if [[ -f "$nouveau" ]]; then printf '%s\n' "$nouveau"
    elif [[ -z "${NGINX_TOOLS_WHITE_LIST:-}" && -f "$ancien" ]]; then printf '%s\n' "$ancien"
    fi
}

# _listes_personnel PATH.conf: personal file to read; an old PATH.cfg is renamed (apps/_i18n.sh config_migrer_ancien); without _i18n.sh: the .conf, or
# l'ancien fichier s'il est seul.
_listes_personnel() {
    local ancien="${1%.conf}.cfg"
    if declare -F config_migrer_ancien >/dev/null; then config_migrer_ancien "$1"; printf '%s\n' "$CFG_A_LIRE"
    elif [[ ! -e "$1" && -e "$ancien" ]]; then printf '%s\n' "$ancien"
    else printf '%s\n' "$1"; fi
}

# listes_fichiers_lieux: paths of the existing places files (only one if NGINX_TOOLS_IP_LOCATION is set), one per line.
listes_fichiers_lieux() {
    local f
    if [[ -n "${NGINX_TOOLS_IP_LOCATION:-}" ]]; then
        [[ -f "$NGINX_TOOLS_IP_LOCATION" ]] && printf '%s\n' "$NGINX_TOOLS_IP_LOCATION"
    else
        for f in "$LISTES_LIEUX_DEFAUT" "$(_listes_personnel "$HOME/.nginx-tools-ip-location.conf")"; do [[ -f "$f" ]] && printf '%s\n' "$f"; done
    fi
    return 0
}

# listes_lire FILE: one line per entry, "ADDRESS LABEL OPTIONS LINE-NUMBER" separated by the character 037 (octal: never a tab, which read would merge when a field is empty) (options: partagee, protegee,
# separated by commas; "inconnue:xxx" for an unknown option). The address is NOT validated here (see listes_adresse_valide).
listes_lire() {
    local fichier="$1" ligne adr com opts reste opt lib n=0
    [[ -r "$fichier" ]] || return 0
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        n=$((n + 1)); ligne=${ligne%$'\r'}
        [[ "$ligne" =~ ^[[:space:]]*(#|$) ]] && continue
        adr=${ligne%%#*}; read -r adr _ <<< "$adr"
        com=""; if [[ "$ligne" == *"#"* ]]; then com=${ligne#*#}; fi
        opts=""; reste=$com
        while [[ "$reste" =~ \[([^]]*)\] ]]; do
            opt=${BASH_REMATCH[1],,}; opt=${opt//é/e}; opt=${opt## }; opt=${opt%% }
            case "$opt" in
                partagee|protegee) opts+="${opts:+,}$opt" ;;
                *) opts+="${opts:+,}inconnue:$opt" ;;
            esac
            reste=${reste/"${BASH_REMATCH[0]}"/}
        done
        lib=${reste#"${reste%%[![:space:]]*}"}; lib=${lib%"${lib##*[![:space:]]}"}
        printf '%s\037%s\037%s\037%s\n' "$adr" "$lib" "$opts" "$n"
    done < "$fichier"
    return 0
}

# listes_adresse_valide ADDRESS: IPv4/IPv6 address or range of correct form (never written to nginx otherwise: it would refuse its whole configuration).
listes_adresse_valide() {
    [[ "$1" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?$ || "$1" =~ ^[0-9a-fA-F]*:[0-9a-fA-F]*:[0-9a-fA-F:]*(/[0-9]{1,3})?$ ]]
}

# listes_valides: filter (standard input -> standard output): keeps only the entries whose address is of correct form.
listes_valides() {
    local ligne adr
    while IFS= read -r ligne; do
        adr=${ligne%%$'\037'*}
        if listes_adresse_valide "$adr"; then printf '%s\n' "$ligne"; fi
    done
    return 0
}

# listes_blanche: white list entries (listes_lire format).
listes_blanche() {
    local f
    f=$(listes_fichier_blanche)
    [[ -n "$f" ]] && listes_lire "$f"
    return 0
}

# listes_lieux: entries of all the places files (listes_lire format).
listes_lieux() {
    local f
    while IFS= read -r f; do [[ -n "$f" ]] && listes_lire "$f"; done < <(listes_fichiers_lieux)
    return 0
}

# listes_ne_pas_bannir: addresses NEVER to ban (white list + [protected] places), one per line, without duplicate, valid addresses only.
listes_ne_pas_bannir() {
    { listes_blanche | listes_valides | cut -d "$LISTES_SEP" -f1
      listes_lieux | listes_valides | awk -F'\037' '$3 ~ /protegee/ { print $1 }'
    } | awk 'NF && !vu[$0]++'
}

# listes_resume: the line 'Listes : ...' (files read and number of valid addresses), for the programs' error output.
listes_resume() {
    local fb nb nl lieux a b
    fb=$(listes_fichier_blanche); lieux=$(listes_fichiers_lieux | paste -sd, - | sed 's/,/, /g')
    nb=$(listes_blanche | listes_valides | grep -c . || true); nl=$(listes_lieux | listes_valides | grep -c . || true)
    if [[ -n "$fb" ]]; then
        a="liste blanche $fb ($nb adresse(s))"
        if [[ "$fb" == */apps/team-ips.list ]]; then a+=" — ANCIEN emplacement, à migrer : nginx-hardening.sh --update"; fi
    else a="liste blanche : aucun fichier"; fi
    if [[ -n "$lieux" ]]; then b="lieux $lieux ($nl plage(s))"; else b="lieux : aucun fichier"; fi
    printf 'Listes : %s ; %s\n' "$a" "$b"
}
