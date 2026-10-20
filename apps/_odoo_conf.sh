# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Bibliothèque commune (sourcée par les programmes bash) : trouver la configuration d'Odoo et en lire les réglages.
#   odoo_conf_chemins            chemins (ou motifs) candidats, un par ligne
#   odoo_conf_trouver            premier fichier de configuration d'Odoo lisible (affiche son chemin ; code 1 si aucun)
#   odoo_conf_valeur FICHIER CLÉ dernière valeur de CLÉ dans le fichier (sans espaces ni guillemets ; vide si absente)
#   odoo_conf_charger FICHIER    définit ODOO_CONF_HTTP_PORT, ODOO_CONF_GEVENT_PORT, ODOO_CONF_LOGFILE, ODOO_CONF_INTERFACE
#                                (valeurs de la configuration ; ports par défaut d'Odoo 8069 / 8072 si absents)
# Liste des candidats (premier trouvé gagne), par ordre de priorité : variable d'environnement ODOO_CONF_PATHS, puis ligne
# ODOO_CONF_PATHS="..." de ~/.nginx-hardening.cfg, puis de /etc/default/nginx-hardening.conf, puis la liste ci-dessous.
# Séparateur : espace ; les motifs avec * sont développés. APP_DETECT_ROOT (tests) préfixe tous les chemins.
# shellcheck shell=bash

ODOO_CONF_PATHS_DEFAUT="/etc/odoo/odoo-linux_meetup.conf /opt/odoo/erplibre/config.conf /home/utilisateur/git/erplibre/config.conf /etc/odoo/odoo.conf /etc/odoo/*.conf /home/*/git/erplibre/config.conf /opt/odoo/*/config.conf"

# Valeur de CLÉ="..." dans un fichier de réglages du programme (dernier gagne), sans guillemets.
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
    [[ -n "$liste" ]] || liste=$(_odoo_conf_reglage "${HOME:-/nonexistent}/.nginx-hardening.cfg" ODOO_CONF_PATHS) || liste=""
    [[ -n "$liste" ]] || liste=$(_odoo_conf_reglage "$etc/nginx-hardening.conf" ODOO_CONF_PATHS) || liste=""
    [[ -n "$liste" ]] || liste="$ODOO_CONF_PATHS_DEFAUT"
    set -f   # séparation par espaces SANS développer les motifs (fait plus tard, sous APP_DETECT_ROOT)
    # shellcheck disable=SC2086  # séparation par espaces voulue
    printf '%s\n' $liste
    set +f
}

odoo_conf_trouver() {
    local racine="${APP_DETECT_ROOT:-}" motif f
    while IFS= read -r motif; do
        [[ -n "$motif" ]] || continue
        # shellcheck disable=SC2086  # développement du motif voulu
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

# shellcheck disable=SC2034  # variables lues par les programmes qui sourcent cette bibliothèque
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
    # Service systemd : souvent nommé d'après db_user (ex. odoo-linux_meetup) ou d'après le fichier de configuration.
    ODOO_CONF_DB_USER=$(odoo_conf_valeur "$f" db_user)
    ODOO_CONF_UNITES=""
    local nom
    for nom in "$ODOO_CONF_DB_USER" "$(basename "$f" .conf)"; do
        if [[ -n "$nom" && "$nom" != "False" && " $ODOO_CONF_UNITES " != *" $nom.service "* ]]; then ODOO_CONF_UNITES="${ODOO_CONF_UNITES:+$ODOO_CONF_UNITES }$nom.service"; fi
    done
    return 0
}
