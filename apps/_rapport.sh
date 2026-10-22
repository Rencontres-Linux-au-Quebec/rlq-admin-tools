# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Bibliothèque commune (sourcée par les programmes bash) : option --report-err. Composant versionné avec apps/_rapport.py
# (CHANGELOG.md).
#   rapport_si_demande CHEMIN_DU_PROGRAMME VERSION DOSSIER_DES_PROGRAMMES "$@"
# Sans --report-err (ou avec --help, --version, --changelog) : ne fait rien. Avec --report-err : relance le programme SANS cette
# option en copiant sa sortie (stdout et stderr) dans un fichier tout en l'affichant, puis imprime le rapport d'erreurs
# (apps/_rapport.py) et termine avec le code de sortie du programme. Les questions interactives sont désactivées (la
# sortie du programme n'est plus un terminal) ; les couleurs sont conservées si NOTRE sortie est un terminal (REPORT_ERR_COULEUR).
# shellcheck shell=bash

rapport_si_demande() {
    local script="$1" version="$2" dossier="$3" demande=0 court=0 a tmp code=0 debut commande
    shift 3
    local -a restant=()
    for a in "$@"; do
        case "$a" in
            --report-err) demande=1 ;;
            -h|--help|--version|--changelog) court=1; restant+=("$a") ;;
            *) restant+=("$a") ;;
        esac
    done
    if (( ! demande )) || (( court )) || [[ -n "${REPORT_ERR_ENFANT:-}" ]]; then return 0; fi
    if ! command -v python3 >/dev/null 2>&1 || [[ ! -r "$dossier/apps/_rapport.py" ]]; then
        echo "--report-err indisponible : python3 ou $dossier/apps/_rapport.py introuvable — exécution normale." >&2
        return 0
    fi
    tmp=$(mktemp "${TMPDIR:-/tmp}/report-err.XXXXXX") || return 0
    debut=$SECONDS
    # La sortie du programme passe par tee (donc n'est plus un terminal) : on lui dit si NOTRE sortie en est un, pour qu'il garde ses couleurs.
    if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != dumb ]]; then export REPORT_ERR_COULEUR=1; fi
    # Le code de sortie du programme est celui du PREMIER élément du tube (tee ne doit pas le masquer).
    if REPORT_ERR_ENFANT=1 bash "$script" ${restant[@]+"${restant[@]}"} 2>&1 | tee "$tmp"; then code=0; else code=${PIPESTATUS[0]}; fi
    commande="$(basename "$script")"
    if (( ${#restant[@]} > 0 )); then commande+=" ${restant[*]}"; fi
    python3 "$dossier/apps/_rapport.py" --programme "$(basename "$script")" --programme-version "$version" \
        --commande "$commande" --code "$code" --duree "$((SECONDS - debut))" --shell "bash ${BASH_VERSION%%(*}" \
        --dossier "$dossier" --sortie "$tmp" || true
    rm -f "$tmp"
    exit "$code"
}
