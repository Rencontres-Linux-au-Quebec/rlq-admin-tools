# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _menu.sh - menu --menu commun aux programmes bash (sourcé, apps/) : dialog si disponible, sinon menu texte.
#
# Usage, dans un programme, APRES SCRIPT_DIR, config_lire (apps/_i18n.sh) et ARGS_INITIAUX=("$@") :
#   . "$SCRIPT_SOUS_DOSSIER/apps/_menu.sh"
#   MENU_ENTREES=("--stats|Statistiques du trafic|Traffic statistics|0" "|Rapport|Report|0")   # TAG|FR|EN|CONFIRMATION (1 = demander)
#   menu_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$@"   # quitte si --menu ; sinon ne fait rien
# TAG : options à relancer (plusieurs mots possibles, « --sent 20 ») ; vide = sans option. Le menu ajoute la configuration lue,
# --changelog et Quitter. Les options reçues sur la ligne de commande sont reprises à chaque opération (sauf --menu).
# La langue suit NGINX_TOOLS_I18N_LANGUE (fr par défaut ; en : libellés anglais).
# shellcheck shell=bash

MENU_UI=""
DIALOG_BIN="${DIALOG_BIN:-dialog}"
MENU_ENTREES=("${MENU_ENTREES[@]+"${MENU_ENTREES[@]}"}")

_menu_langue_en() { [[ "${NGINX_TOOLS_I18N_LANGUE:-fr}" == en* ]]; }

# menu_si_demande PROGRAMME ARGS... : si --menu est demandé (et pas --help / --version / --changelog), lance le menu et quitte.
menu_si_demande() {
    local programme="$1" a menu=0 info=0
    shift
    for a in "$@"; do
        case "$a" in
            --menu) menu=1 ;;
            -h|--help|--version|--changelog) info=1 ;;
        esac
    done
    (( menu == 1 )) || return 0
    ARGS_INITIAUX=("$@")
    if (( info == 1 )); then return 0; fi
    menu_principal "$programme"
}

_menu_dialog_run() {    # _menu_dialog_run VAR ARGS... : réponse de dialog dans VAR (fichier --output-fd, comme odoo-sql-maint)
    local __var="$1" reponse rc=0
    shift
    reponse="$(mktemp)" || return 1
    "$DIALOG_BIN" --output-fd 3 "$@" 3>"$reponse" || rc=$?
    printf -v "$__var" '%s' "$(cat -- "$reponse")"
    rm -f -- "$reponse"
    return "$rc"
}

_menu_confirmer() {     # _menu_confirmer QUESTION : 0 si oui
    local rep="" rc=0
    if [[ "$MENU_UI" == "dialog" ]]; then
        "$DIALOG_BIN" --title "${MENU_TITRE:-menu}" --yesno "$1" 8 72 || rc=$?
        return "$rc"
    fi
    read -r -p "$1 [o/N] " rep || return 1
    case "${rep,,}" in o|oui|y|yes) return 0 ;; esac
    return 1
}

# _menu_relancer PROGRAMME TAG... : relance le programme avec les options reçues (sans --menu) et TAG ; affiche le code de retour.
_menu_relancer() {
    local programme="$1" a rc=0
    shift
    local -a args=()
    for a in ${ARGS_INITIAUX[@]+"${ARGS_INITIAUX[@]}"}; do
        [[ "$a" == "--menu" ]] || args+=("$a")
    done
    args+=("$@")
    echo
    bash "$programme" ${args[@]+"${args[@]}"} || rc=$?
    echo
    if (( rc == 0 )); then echo "${C_GREEN:-}Terminé${C_RESET:-} (code 0)."; else echo "${C_RED:-}Code de retour : $rc${C_RESET:-}"; fi
}

# _menu_config : fichiers lus et options par défaut qu'ils donnent (CFG_* de config_lire) ; sans config_lire : rien.
_menu_config() {
    local f p
    if ! declare -F config_lire >/dev/null; then
        local -a existants=()
        for f in ${MENU_FICHIERS_CONFIG[@]+"${MENU_FICHIERS_CONFIG[@]}"}; do [[ -r "$f" ]] && existants+=("$f"); done
        CFG_FICHIERS=(${existants[@]+"${existants[@]}"}); CFG_EXPLICITE=""; CFG_OPTIONS=(); CFG_PROBLEMES=()
    fi
    if _menu_langue_en; then
        echo "Configuration files read (the last one wins):"
        if [[ -n "${CFG_EXPLICITE:-}" ]]; then echo "  $CFG_EXPLICITE (-c/--config: no other file is read)"
        elif (( ${#CFG_FICHIERS[@]} == 0 )); then echo "  none (program default values)"
        else for f in "${CFG_FICHIERS[@]}"; do echo "  $f"; done; fi
        echo; echo "Default options read from these files (the command line overrides them):"
    else
        echo "Fichiers de configuration lus (le dernier l'emporte) :"
        if [[ -n "${CFG_EXPLICITE:-}" ]]; then echo "  $CFG_EXPLICITE (demandé par -c/--config : aucun autre fichier n'est lu)"
        elif (( ${#CFG_FICHIERS[@]} == 0 )); then echo "  aucun (valeurs par défaut du programme)"
        else for f in "${CFG_FICHIERS[@]}"; do echo "  $f"; done; fi
        echo; echo "Options par défaut lues dans ces fichiers (la ligne de commande les remplace) :"
    fi
    if (( ${#CFG_OPTIONS[@]} == 0 )); then echo "  aucune"
    else for p in "${CFG_OPTIONS[@]}"; do echo "  ${p%% *} ${p#* }"; done; fi
    for p in ${CFG_PROBLEMES[@]+"${CFG_PROBLEMES[@]}"}; do echo "  [ATTN] valeur ignorée : $p"; done
    return 0
}

# _menu_action PROGRAMME INDEX : lance l'entrée INDEX de la liste (0 = configuration, 1 = changelog, 2 = quitter) ; retour 1 si inconnue.
_menu_action() {
    local programme="$1" choix="$2" tag confirme="" fr en
    local -a mots=()
    if [[ "$choix" == "config" ]]; then _menu_config; return 0; fi
    if [[ "$choix" == "changelog" ]]; then _menu_relancer "$programme" --changelog; return 0; fi
    [[ "$choix" =~ ^[0-9]+$ ]] || return 1
    (( choix < ${#MENU_ENTREES[@]} )) || return 1
    IFS='|' read -r tag fr en confirme <<< "${MENU_ENTREES[$choix]}"
    local libelle="$fr"
    _menu_langue_en && libelle="$en"
    if [[ "${confirme:-0}" == "1" ]] && ! _menu_confirmer "$libelle : confirmer ?"; then
        echo "Annulé : rien n'est modifié."; return 0
    fi
    read -r -a mots <<< "$tag"
    _menu_relancer "$programme" ${mots[@]+"${mots[@]}"}
}

# menu_principal PROGRAMME : boucle du menu ; dialog (fenêtre de choix) ou texte ; terminal requis.
menu_principal() {
    local programme="$1" choix="" i n libelle tag fr en confirme
    if [[ ! -t 0 || ! -t 2 ]]; then
        echo "ERREUR: --menu demande un terminal (entrée et sortie interactives)." >&2
        exit 1
    fi
    MENU_TITRE="$("$programme" --version 2>/dev/null | head -1)"; MENU_TITRE="${MENU_TITRE:-$(basename "$programme")}"
    if command -v "$DIALOG_BIN" >/dev/null 2>&1 && { : >/dev/tty; } 2>/dev/null; then
        MENU_UI="dialog"
    else
        MENU_UI="texte"
        command -v "$DIALOG_BIN" >/dev/null 2>&1 || echo "[ATTN] commande dialog absente : menu texte (sudo apt install dialog pour le menu graphique)." >&2
    fi
    n=${#MENU_ENTREES[@]}
    while true; do
        if [[ "$MENU_UI" == "dialog" ]]; then
            local -a items=()
            for ((i = 0; i < n; i++)); do
                IFS='|' read -r tag fr en confirme <<< "${MENU_ENTREES[$i]}"
                libelle="$fr"; _menu_langue_en && libelle="$en"
                items+=("$i" "$libelle")
            done
            items+=("config" "$(_menu_langue_en && echo "Show the configuration read" || echo "Voir la configuration lue")")
            items+=("changelog" "$(_menu_langue_en && echo "Change log (--changelog)" || echo "Journal des modifications (--changelog)")")
            items+=("q" "$(_menu_langue_en && echo "Quit" || echo "Quitter")")
            _menu_dialog_run choix --title "$MENU_TITRE" --menu "$(_menu_langue_en && echo "Choose an operation:" || echo "Choisissez une opération :")" \
                22 76 14 "${items[@]}" || break
            [[ "$choix" == "q" ]] && break
            _menu_action "$programme" "$choix" || true
            read -r -p "$(_menu_langue_en && echo "Enter to return to the menu..." || echo "Entrée pour revenir au menu...")" _ || break
        else
            echo
            echo "=============================================================="
            echo " $MENU_TITRE"
            echo "=============================================================="
            for ((i = 0; i < n; i++)); do
                IFS='|' read -r tag fr en confirme <<< "${MENU_ENTREES[$i]}"
                libelle="$fr"; _menu_langue_en && libelle="$en"
                printf '  %s%2d%s  %s\n' "${C_GREEN:-}" "$i" "${C_RESET:-}" "$libelle"
            done
            echo "  ${C_GREEN:-}c${C_RESET:-}  $(_menu_langue_en && echo "Show the configuration read" || echo "Voir la configuration lue")"
            echo "  ${C_GREEN:-}l${C_RESET:-}  $(_menu_langue_en && echo "Change log (--changelog)" || echo "Journal des modifications (--changelog)")"
            echo "  ${C_GREEN:-}q${C_RESET:-}  $(_menu_langue_en && echo "Quit" || echo "Quitter")"
            echo
            read -r -p "$(_menu_langue_en && echo "Your choice: " || echo "Votre choix : ")" choix || { echo; break; }
            case "$choix" in
                q|Q) break ;;
                c|C) choix="config" ;;
                l|L) choix="changelog" ;;
            esac
            _menu_action "$programme" "$choix" || echo "$(_menu_langue_en && echo "Unknown choice: " || echo "Choix inconnu : ")« $choix »."
            read -r -p "$(_menu_langue_en && echo "Enter to return to the menu..." || echo "Entrée pour revenir au menu...")" _ || break
        fi
    done
    exit 0
}
