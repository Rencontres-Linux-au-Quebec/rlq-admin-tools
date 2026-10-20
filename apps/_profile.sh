# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Bibliothèque commune (sourcée par les programmes bash) : choix du profil d'application apps/<nom>.conf.
#   charger_profil_app DOSSIER_APPS [NOM_FORCÉ]
# Sans nom forcé : détection automatique (unités systemd ou fichiers DETECT_*). Aucune application détectée, ou
# plusieurs : message clair et arrêt (préciser --app=NOM). Définit toutes les clés du profil + APP_DETECTION.
# shellcheck shell=bash

# Charge la bibliothèque de configuration d'Odoo (apps/_odoo_conf.sh) si ce n'est déjà fait.
_profil_charger_odoo_conf() {
    declare -F odoo_conf_trouver >/dev/null && return 0
    # shellcheck source=/dev/null
    [[ -r "$1/_odoo_conf.sh" ]] && . "$1/_odoo_conf.sh"
    return 0
}

_profil_detecte() {
    local f="$1" u fichier
    # Lecture des seules clés de détection, dans un sous-shell (le profil n'est pas encore choisi).
    local units files
    units=$( ( # shellcheck source=/dev/null
               . "$f"; echo "${DETECT_UNITS:-}" ) ) || return 1
    files=$( ( # shellcheck source=/dev/null
               . "$f"; echo "${DETECT_FILES:-}" ) ) || return 1
    # APP_DETECT_ROOT : racine des fichiers de détection (vide en production ; dossier vide pendant les tests, pour ne
    # jamais dépendre de ce qui est installé sur la machine qui les exécute).
    for fichier in $files; do [[ -e "${APP_DETECT_ROOT:-}$fichier" ]] && return 0; done
    # DETECT_ODOO_CONF="yes" : la présence d'un fichier de configuration d'Odoo (apps/_odoo_conf.sh) suffit.
    local detecte_conf
    detecte_conf=$( ( # shellcheck source=/dev/null
                      . "$f"; echo "${DETECT_ODOO_CONF:-}" ) ) || detecte_conf=""
    if [[ "$detecte_conf" == "yes" ]]; then
        _profil_charger_odoo_conf "$(dirname "$f")"
        odoo_conf_trouver >/dev/null 2>&1 && return 0
    fi
    if command -v systemctl >/dev/null 2>&1; then
        for u in $units; do
            systemctl list-unit-files "$u" --no-legend 2>/dev/null | awk '{print $1}' | grep -qxF "$u" && return 0
        done
    fi
    return 1
}

# APP_DETECTION : lue par les programmes qui sourcent cette bibliotheque (affichage de l'application retenue).
# shellcheck disable=SC2034
charger_profil_app() {
    local dossier="$1" force="${2:-${APP_PROFILE:-}}" f trouves=()   # APP_PROFILE : equivalent de --app
    if [[ -n "$force" ]]; then
        f="$dossier/$force.conf"
        if [[ ! -r "$f" ]]; then
            local dispo="" p
            for p in "$dossier"/*.conf; do [[ -r "$p" ]] && dispo+="$(basename "$p" .conf) "; done
            echo "ERREUR: profil d'application inconnu : $force (disponibles : ${dispo:-aucun})" >&2
            return 2
        fi
        APP_DETECTION="forcée (--app=$force)"
    else
        for f in "$dossier"/*.conf; do
            [[ -r "$f" ]] || continue
            _profil_detecte "$f" && trouves+=("$f")
        done
        if (( ${#trouves[@]} == 0 )); then
            echo "ERREUR: aucune application reconnue sur ce serveur (profils : $dossier/*.conf) — précisez --app=NOM." >&2
            return 2
        elif (( ${#trouves[@]} > 1 )); then
            echo "ERREUR: plusieurs applications détectées ($(for t in "${trouves[@]}"; do basename "$t" .conf; done | paste -sd' ' -)) — précisez --app=NOM." >&2
            return 2
        fi
        f="${trouves[0]}"
        APP_DETECTION="détectée automatiquement"
    fi
    APP_NAME=""
    # shellcheck source=/dev/null
    . "$f"
    # Profil à configuration d'Odoo : fichier trouvé, ports et journal lus (variables ODOO_CONF_*).
    ODOO_CONF_TROUVE=""
    if [[ "${DETECT_ODOO_CONF:-}" == "yes" ]]; then
        _profil_charger_odoo_conf "$dossier"
        if declare -F odoo_conf_trouver >/dev/null && ODOO_CONF_TROUVE=$(odoo_conf_trouver); then
            odoo_conf_charger "$ODOO_CONF_TROUVE"
            [[ "$APP_DETECTION" == "détectée automatiquement" ]] && APP_DETECTION="détectée automatiquement ; configuration d'Odoo : $ODOO_CONF_TROUVE"
        else
            ODOO_CONF_TROUVE=""
        fi
    fi
    if [[ -z "${APP_NAME:-}" ]]; then
        echo "ERREUR: profil invalide : $f (clé APP_NAME absente — fichier vide ou tronqué ?)" >&2
        return 2
    fi
    return 0
}
