# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Common library (sourced by the bash programs): find the Odoo configuration and read its settings.
#   odoo_conf_chemins            chemins (ou motifs) candidats, un par ligne
#   odoo_conf_trouver            premier fichier de configuration d'Odoo lisible (affiche son chemin ; code 1 si aucun)
#   odoo_conf_valeur FILE KEY   last value of KEY in the file (without spaces or quotes; empty if absent)
#   odoo_conf_charger FILE      sets ODOO_CONF_HTTP_PORT, ODOO_CONF_GEVENT_PORT, ODOO_CONF_LOGFILE, ODOO_CONF_INTERFACE
#                                (configuration values; default Odoo ports 8069 / 8072 if absent)
# List of candidates (first found wins), by priority: environment variable ODOO_CONF_PATHS, then line
# ODOO_CONF_PATHS="..." de ~/.nginx-hardening.conf, puis de /etc/default/nginx-hardening.conf, puis la liste ci-dessous.
# Separator: space; patterns with * are expanded. APP_DETECT_ROOT (tests) prefixes all the paths.
# shellcheck shell=bash

ODOO_CONF_PATHS_DEFAUT="/etc/odoo/odoo-linux_meetup.conf /opt/odoo/erplibre/config.conf /home/utilisateur/git/erplibre/config.conf /etc/odoo/odoo.conf /etc/odoo/*.conf /home/*/git/erplibre/config.conf /opt/odoo/*/config.conf"

# Value of KEY="..." in a program's settings file (last one wins), without quotes.
_odoo_conf_reglage() {
    local fichier="$1" cle="$2" v
    [[ -r "$fichier" ]] || return 1
    v=$(grep -E "^[[:space:]]*${cle}=" "$fichier" 2>/dev/null | tail -1) || true
    [[ -n "$v" ]] || return 1
    v="${v#*=}"; v="${v%%#*}"
    v="${v#"${v%%[![:space:]\"\']*}"}"; v="${v%"${v##*[![:space:]\"\']}"}"
    printf '%s\n' "$v"
}

odoo_conf_chemins() {
    local liste="${ODOO_CONF_PATHS:-}" etc="${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}"
    local perso="${HOME:-/nonexistent}/.nginx-hardening.conf"
    if declare -F config_migrer_ancien >/dev/null; then config_migrer_ancien "$perso"; perso="$CFG_A_LIRE"          # legacy ~/.nginx-hardening.cfg renamed
    elif [[ ! -e "$perso" && -e "${perso%.conf}.cfg" ]]; then perso="${perso%.conf}.cfg"; fi
    [[ -n "$liste" ]] || liste=$(_odoo_conf_reglage "$perso" ODOO_CONF_PATHS) || liste=""
    [[ -n "$liste" ]] || liste=$(_odoo_conf_reglage "$etc/nginx-hardening.conf" ODOO_CONF_PATHS) || liste=""
    [[ -n "$liste" ]] || liste="$ODOO_CONF_PATHS_DEFAUT"
    set -f   # splitting by spaces WITHOUT expanding the patterns (done later, under APP_DETECT_ROOT)
    # shellcheck disable=SC2086  # splitting by spaces is intended
    printf '%s\n' $liste
    set +f
}

odoo_conf_trouver() {
    local racine="${APP_DETECT_ROOT:-}" motif f
    while IFS= read -r motif; do
        [[ -n "$motif" ]] || continue
        # shellcheck disable=SC2086  # pattern expansion is intended
        for f in $racine$motif; do
            if [[ -f "$f" && -r "$f" ]] && grep -Eq '^\[options\]|^[[:space:]]*(db_host|addons_path|http_port|xmlrpc_port|admin_passwd)[[:space:]]*=' "$f" 2>/dev/null; then
                printf '%s\n' "$f"
                return 0
            fi
        done
    done < <(odoo_conf_chemins)
    return 1
}

odoo_conf_valeur() {
    local fichier="$1" cle="$2" v
    v=$(grep -E "^[[:space:]]*${cle}[[:space:]]*=" "$fichier" 2>/dev/null | tail -1) || true
    v="${v#*=}"
    v="${v#"${v%%[![:space:]\"\']*}"}"; v="${v%"${v##*[![:space:]\"\']}"}"
    printf '%s\n' "$v"
}

# shellcheck disable=SC2034  # variables read by the programs that source this library
odoo_conf_charger() {
    local f="$1" v
    v=$(odoo_conf_valeur "$f" http_port); [[ -n "$v" ]] || v=$(odoo_conf_valeur "$f" xmlrpc_port)
    ODOO_CONF_HTTP_PORT="${v:-8069}"
    v=$(odoo_conf_valeur "$f" gevent_port); [[ -n "$v" ]] || v=$(odoo_conf_valeur "$f" longpolling_port)
    ODOO_CONF_GEVENT_PORT="${v:-8072}"
    ODOO_CONF_LOGFILE=$(odoo_conf_valeur "$f" logfile)
    [[ "$ODOO_CONF_LOGFILE" == "False" || "$ODOO_CONF_LOGFILE" == "false" ]] && ODOO_CONF_LOGFILE=""
    ODOO_CONF_INTERFACE=$(odoo_conf_valeur "$f" http_interface)
    [[ -n "$ODOO_CONF_INTERFACE" ]] || ODOO_CONF_INTERFACE=$(odoo_conf_valeur "$f" xmlrpc_interface)
    # systemd service: often named after db_user (e.g. odoo-linux_meetup) or after the configuration file.
    ODOO_CONF_DB_USER=$(odoo_conf_valeur "$f" db_user)
    ODOO_CONF_UNITES=""
    local nom
    for nom in "$ODOO_CONF_DB_USER" "$(basename "$f" .conf)"; do
        if [[ -n "$nom" && "$nom" != "False" && " $ODOO_CONF_UNITES " != *" $nom.service "* ]]; then ODOO_CONF_UNITES="${ODOO_CONF_UNITES:+$ODOO_CONF_UNITES }$nom.service"; fi
    done
    return 0
}
