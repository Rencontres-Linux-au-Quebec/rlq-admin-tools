# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Library (sourced by nginx-hardening.sh, 2.130): two corrections that the program only proposes by default. Each one is
# opt-in (--badrequests-gate, --odoo-list-db-off), writes a copy first, and checks the result before it replaces the file.
# The copy is named FILE.AAAAMMJJ-HHMMSS.bak and kept in the backup folder given as argument; nothing is deleted.
# shellcheck shell=bash

# correctif_liste_bases_off FILE BACKUP_DIR CHECKER : list_db = False in the Odoo configuration (added, or replaced when the
# line exists). The new file is checked by CHECKER (apps/_odoo_conf_check.py) before it replaces FILE.
# Returns 0 when FILE was changed, 2 when it already says list_db = False, 1 on error (FILE untouched).
correctif_liste_bases_off() {
    local conf="$1" dossier="$2" checker="$3" tmp copie
    if grep -qE '^[[:space:]]*list_db[[:space:]]*=[[:space:]]*(False|false|0)[[:space:]]*$' "$conf"; then
        return 2
    fi
    copie="$dossier/$(basename -- "$conf").$(date +%Y%m%d-%H%M%S).bak"
    mkdir -p -- "$dossier" && cp -p -- "$conf" "$copie" || return 1
    tmp="$(mktemp "$conf.XXXXXX")" || return 1
    if grep -qE '^[[:space:]]*list_db[[:space:]]*=' "$conf"; then
        sed -E 's/^([[:space:]]*list_db[[:space:]]*=).*/\1 False/' "$conf" > "$tmp"
    else
        { cat -- "$conf"; printf '\n# list_db : no list of the databases (nginx-hardening.sh --odoo-list-db-off)\nlist_db = False\n'; } > "$tmp"
    fi
    chmod --reference="$conf" "$tmp" 2>/dev/null || true
    if [[ -n "$checker" ]] && ! python3 -I "$checker" "$tmp" >/dev/null 2>&1; then
        rm -f -- "$tmp"
        return 1
    fi
    if mv -f -- "$tmp" "$conf"; then return 0; fi
    rm -f -- "$tmp"
    return 1
}

# correctif_porte_badrequests FILE BACKUP_DIR : in the section [nginx-badrequests] of FILE, the action line becomes
# nginx-gate-ban (the ban goes through nginx-log-audit.sh). Returns 0 changed, 2 no action line in the section, 1 error.
correctif_porte_badrequests() {
    local fichier="$1" dossier="$2" tmp copie
    grep -q '^\[nginx-badrequests\]' -- "$fichier" || return 2
    grep -q 'nginx-gate-ban' -- "$fichier" && return 2
    copie="$dossier/$(basename -- "$fichier").$(date +%Y%m%d-%H%M%S).bak"
    mkdir -p -- "$dossier" && cp -p -- "$fichier" "$copie" || return 1
    tmp="$(mktemp "$fichier.XXXXXX")" || return 1
    awk 'BEGIN { dans = 0; fait = 0 }
         /^\[/ { dans = ($0 == "[nginx-badrequests]") }
         dans && !fait && /^[[:space:]]*action[[:space:]]*=/ { print "action   = nginx-gate-ban[name=nginx-badrequests]"; fait = 1; next }
         { print }
         END { exit (fait ? 0 : 3) }' "$fichier" > "$tmp" || { rm -f -- "$tmp"; return 2; }
    chmod --reference="$fichier" "$tmp" 2>/dev/null || true
    if mv -f -- "$tmp" "$fichier"; then return 0; fi
    rm -f -- "$tmp"
    return 1
}

# correctif_restaurer FILE COPY : puts the copy back over FILE (used when fail2ban refuses the new file).
correctif_restaurer() {
    cp -p -- "$2" "$1"
}
