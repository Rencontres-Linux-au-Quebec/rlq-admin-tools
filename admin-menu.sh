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
# admin-menu.sh - one menu for all the administration programs of the repository.
#
# It lists every program of the folder that offers --menu (found automatically; PROGRAMS in the configuration file
# restricts the list), then starts the menu of the program chosen. dialog is offered when it is missing, and installed on
# request (apt, as root or with sudo). Messages are bilingual (French and English): LANGUAGE in the configuration file,
# otherwise LC_ALL / LC_MESSAGES / LANG. Ctrl+C asks for confirmation (apps/_i18n.sh).
#
# Usage : admin-menu.sh [OPTION]...   (on a terminal without option: the menu; otherwise: the list and this help)
#
# Options (sorted alphabetically):
#   --changelog                  show this program's change log
#   -c, --config FILE            this configuration file ONLY (default: /etc/default/admin-menu.conf, then
#                                ~/.admin-menu.conf if it exists; the command line has priority)
#   -h, --help                   show this help and exit
#   --install-dialog             install dialog (apt) if it is missing, without asking
#   --list                       list the programs that have --menu, their version and the state of dialog
#   --report-err                 print at the end an error report to copy and paste (apps/_rapport.sh)
#   -v, --verbose                print each command launched (also passed to the programs started)
#   --version                    show the version and exit
#
# Configuration (/etc/default/admin-menu.conf, then ~/.admin-menu.conf if it exists; the last one wins):
#   LANGUAGE=auto                en, fr or auto
#   PROGRAMS=                    programs to offer, separated by spaces (empty: every program of the folder that has --menu)
#   VERBOSE=no                   yes: print each command launched
#
# ========================================================================================================================

set -euo pipefail

readonly SCRIPT_VERSION="1.1.20261030.153422"
readonly SCRIPT_NAME="admin-menu"
SCRIPT_FILE="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_FILE
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_GREEN=$'\x1b[1;32m'; C_YELLOW=$'\x1b[1;33m'; C_CYAN=$'\x1b[1;36m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_RESET=""
fi

# First line of EVERY run, even with --help: the name and version (--version displays it itself).
case " $* " in *" --version "*) ;; *) echo "$SCRIPT_FILE v$SCRIPT_VERSION" ;; esac

# Shared libraries (apps/): configuration file reading and Ctrl+C confirmation are required; the report is optional.
if [[ ! -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    echo "ERROR: apps/_i18n.sh is missing next to $SCRIPT_FILE." >&2
    exit 1
fi
# shellcheck source=/dev/null  # library shipped next to the program
. "$SCRIPT_DIR/apps/_i18n.sh"
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_rapport.sh"
fi

ADMIN_LANGUE="fr"
PROGRAMMES=()

# t FRENCH ENGLISH: the text in the language chosen for this run.
t() {
    if [[ "$ADMIN_LANGUE" == "en" ]]; then printf '%s' "$2"; else printf '%s' "$1"; fi
}

# choisir_langue: LANGUAGE of the configuration file (en, fr, auto), otherwise the locale.
choisir_langue() {
    case "${CFG[LANGUAGE]:-auto}" in
        en*|EN*) ADMIN_LANGUE="en" ;;
        fr*|FR*) ADMIN_LANGUE="fr" ;;
        *)
            case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
                en*) ADMIN_LANGUE="en" ;;
                *) ADMIN_LANGUE="fr" ;;
            esac ;;
    esac
}

# Help: options in colour, sorted alphabetically (the names of the options are in English).
aide() {
    opt() { printf '  %s%-24s%s %s\n' "$C_CYAN" "$1" "$C_RESET" "$2"; }
    printf '%s\n' "$(t "Usage : admin-menu.sh [OPTION]..." "Usage: admin-menu.sh [OPTION]...")"
    printf '%s\n' "$(t "Menu unique des programmes d'administration du dépôt (ceux qui ont --menu)." \
        "One menu for the administration programs of the repository (those that have --menu).")"
    echo
    printf '%s\n' "$(t "Options (par ordre alphabétique) :" "Options (sorted alphabetically):")"
    opt "--changelog" "$(t "journal des modifications de ce programme" "change log of this program")"
    opt "-c, --config FILE" "$(t "ce fichier de configuration SEUL (défaut : /etc/default/admin-menu.conf, puis ~/.admin-menu.conf)" \
        "this configuration file ONLY (default: /etc/default/admin-menu.conf, then ~/.admin-menu.conf)")"
    opt "-h, --help" "$(t "affiche cette aide et quitte" "show this help and exit")"
    opt "--install-dialog" "$(t "installe dialog (apt) s'il manque, sans demander" "install dialog (apt) if missing, without asking")"
    opt "--list" "$(t "liste les programmes qui ont --menu, leur version et l'état de dialog" \
        "list the programs that have --menu, their version and the state of dialog")"
    opt "--report-err" "$(t "rapport d'erreurs à copier-coller à la fin" "error report to copy and paste at the end")"
    opt "-v, --verbose" "$(t "affiche chaque commande lancée (transmise aux programmes)" "print each command launched (passed to the programs)")"
    opt "--version" "$(t "affiche la version et quitte" "show the version and exit")"
    echo
    printf '%s\n' "$(t "Configuration (clés, une par ligne) :" "Configuration (keys, one per line):")"
    printf '  %sLANGUAGE%s=auto   %s\n' "$C_CYAN" "$C_RESET" "$(t "en, fr ou auto" "en, fr or auto")"
    printf '  %sPROGRAMS%s=       %s\n' "$C_CYAN" "$C_RESET" "$(t "programmes à proposer, séparés par des espaces (vide : tous)" \
        "programs to offer, separated by spaces (empty: all)")"
    printf '  %sVERBOSE%s=no      %s\n' "$C_CYAN" "$C_RESET" "$(t "yes : afficher chaque commande lancée" "yes: print each command launched")"
}

# config_resumer: the configuration file(s) really read, and the keys they set (the command line has priority).
config_resumer() {
    local fichier lus="" cle options=""
    if [[ -n "${CFG_EXPLICITE:-}" ]]; then
        lus="$CFG_EXPLICITE ($(t "par -c/--config : aucun autre fichier n'est lu" "given by -c/--config: no other file is read"))"
    elif (( ${#CFG_FICHIERS[@]} == 0 )); then
        lus="$(t "aucun fichier : valeurs par défaut" "no file: default values")"
    else
        for fichier in "${CFG_FICHIERS[@]}"; do lus+="${lus:+, }$fichier"; done
        lus+=" ($(t "le dernier l'emporte" "the last one wins"))"
    fi
    for cle in LANGUAGE PROGRAMS VERBOSE; do
        if [[ -n "${CFG[$cle]:-}" ]]; then options+=" $cle=${CFG[$cle]}"; fi
    done
    printf '%s\n' "$(t "Fichiers de configuration lus :" "Configuration files read:") $lus"
    echo "  $(t "Options lues dans ces fichiers :" "Options read from these files:")${options:- $(t "aucune" "none")}"
    for cle in ${CFG_PROBLEMES[@]+"${CFG_PROBLEMES[@]}"}; do
        echo "  [ATTN] $(t "valeur ignorée" "value ignored"): $cle" >&2
    done
}

# dialog_presente: true when the dialog command exists.
dialog_presente() { command -v dialog >/dev/null 2>&1; }

# installer_dialog: installs dialog with apt (root, or sudo): apt-get update, then install; each command is shown when --verbose.
installer_dialog() {
    local -a prefixe=() maj=() cmd=()
    if dialog_presente; then
        echo "${C_GREEN}[OK]${C_RESET} $(t "dialog est déjà installé." "dialog is already installed.")"
        return 0
    fi
    if (( EUID == 0 )); then
        prefixe=(env DEBIAN_FRONTEND=noninteractive)
    elif command -v sudo >/dev/null 2>&1; then
        prefixe=(sudo env DEBIAN_FRONTEND=noninteractive)
    else
        echo "${C_RED}[ERR]${C_RESET} $(t "installation impossible : il faut être root ou avoir sudo." \
            "cannot install: root or sudo is needed.")" >&2
        return 1
    fi
    maj=("${prefixe[@]}" apt-get update)
    cmd=("${prefixe[@]}" apt-get install -y dialog)
    printf '%s\n' "$(t "Mise à jour de la liste des paquets (apt), patientez..." "Updating the package list (apt), please wait...")"
    if (( VERBOSE == 1 )); then echo "+ ${maj[*]}"; fi
    if ! "${maj[@]}"; then
        echo "${C_YELLOW}[ATTN]${C_RESET} $(t "apt-get update a échoué : installation tentée quand même." \
            "apt-get update failed: trying the installation anyway.")" >&2
    fi
    printf '%s\n' "$(t "Installation de dialog (apt), patientez..." "Installing dialog (apt), please wait...")"
    if (( VERBOSE == 1 )); then echo "+ ${cmd[*]}"; fi
    if ! "${cmd[@]}"; then
        echo "${C_RED}[ERR]${C_RESET} $(t "échec de l'installation de dialog." "dialog installation failed.")" >&2
        return 1
    fi
    if dialog_presente; then
        echo "${C_GREEN}[OK]${C_RESET} $(t "dialog installé." "dialog installed.")"
        return 0
    fi
    echo "${C_RED}[ERR]${C_RESET} $(t "dialog reste introuvable après l'installation." "dialog is still missing after the installation.")" >&2
    return 1
}

# confirmer QUESTION: true when the answer is yes (o, oui, y, yes).
confirmer() {
    local rep=""
    read -r -p "$1 $(t "[o/N] " "[y/N] ")" rep || return 1
    case "${rep,,}" in
        o|oui|y|yes) return 0 ;;
    esac
    return 1
}

# decouvrir_programmes: files of the folder that are executable and mention --menu (this program excluded).
decouvrir_programmes() {
    local chemin nom
    PROGRAMMES=()
    for chemin in "$SCRIPT_DIR"/*; do
        nom="$(basename "$chemin")"
        [[ -f "$chemin" && -x "$chemin" && "$nom" != "$SCRIPT_FILE" ]] || continue
        grep -q -e '--menu' -- "$chemin" 2>/dev/null || continue
        if [[ -n "${CFG[PROGRAMS]:-}" ]]; then
            case " ${CFG[PROGRAMS]} " in
                *" $nom "*) ;;
                *) continue ;;
            esac
        fi
        PROGRAMMES+=("$nom")
    done
}

# description NAME: short bilingual description shown in the menu.
description() {
    case "$1" in
        app-health-check.py) t "Contrôle rapide de nginx et de l'application" "Quick check of nginx and the application" ;;
        app-log-check.py) t "Analyse du journal systemd de l'application" "Application systemd journal analysis" ;;
        app-log-live.py) t "Journal de l'application en temps réel" "Application journal in real time" ;;
        host-perf-audit.py) t "Audit des limites de performance du serveur" "Server performance bottleneck audit" ;;
        nginx-hardening.sh) t "Installation et durcissement de nginx" "nginx installation and hardening" ;;
        nginx-log-audit.sh) t "Audit des journaux nginx" "nginx log audit" ;;
        odoo-backup.sh) t "Sauvegarde et restauration d'Odoo" "Odoo backup and restore" ;;
        odoo-chat-post.py) t "Messages dans les canaux de discussion Odoo" "Messages to Odoo discussion channels" ;;
        odoo-docs.py) t "Publication de la documentation dans Odoo" "Publish the documentation into Odoo" ;;
        odoo-mail-retry.py) t "Courriels Odoo non envoyés" "Unsent Odoo e-mails" ;;
        odoo-sql-maint) t "Requêtes SQL de maintenance Odoo" "Odoo maintenance SQL queries" ;;
        odoo-update-module.sh) t "Mise à jour des modules Odoo" "Odoo module update" ;;
        odoo-warmup.py) t "Préchauffage du cache Odoo" "Odoo cache warm-up" ;;
        sync-crowdsec-blocklist.sh) t "Synchronisation de la liste CrowdSec" "CrowdSec blocklist sync" ;;
        web-monitor.py) t "Surveillance automatique" "Automatic monitoring" ;;
        zip-versions.py) t "Versions des archives du projet" "Project archive versions" ;;
        *) t "Programme du dépôt" "Repository program" ;;
    esac
}

# libelle NAME: menu label, the program name then its description.
libelle() { printf '%-26s %s' "$1" "$(description "$1")"; }

# lister: the programs with --menu, their version (from --version), and the state of dialog.
lister() {
    local nom version
    printf '%s\n' "$(t "Programmes du dépôt qui ont --menu :" "Repository programs that have --menu:")"
    if (( ${#PROGRAMMES[@]} == 0 )); then echo "  $(t "aucun" "none")"; fi
    for nom in ${PROGRAMMES[@]+"${PROGRAMMES[@]}"}; do
        version="$("$SCRIPT_DIR/$nom" --version 2>/dev/null | head -n 1 || true)"
        printf '  %s%-26s%s %s\n' "$C_CYAN" "$nom" "$C_RESET" "${version:-?}"
    done
    if dialog_presente; then
        echo "${C_GREEN}[OK]${C_RESET} $(t "dialog est installé (menu graphique)." "dialog is installed (graphical menu).")"
    else
        echo "${C_YELLOW}[ATTN]${C_RESET} $(t "dialog est absent : menu texte. Option --install-dialog pour l'installer." \
            "dialog is missing: text menu. Use --install-dialog to install it.")"
    fi
}

# afficher_changelog: only this program's section of CHANGELOG.md; version numbers in colour when the output is a terminal.
afficher_changelog() {
    if [[ ! -r "$CHANGELOG_FILE" ]]; then
        echo "CHANGELOG.md: $(t "fichier introuvable" "file not found")" >&2
        return 1
    fi
    awk -v cle="$SCRIPT_FILE" '/^## /{dans = ($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE" \
        | sed -E "s/^(### )([0-9]+[.][0-9]+[.][0-9]{8}[.][0-9]{6})/\1${C_CYAN}\2${C_RESET}/" || true
}

# dialog_run VAR ARGS...: the answer of dialog in VAR (--output-fd 3, as apps/_menu.sh).
dialog_run() {
    local __var="$1" reponse rc=0
    shift
    reponse="$(mktemp)" || return 1
    dialog --output-fd 3 "$@" 3>"$reponse" || rc=$?
    printf -v "$__var" '%s' "$(cat -- "$reponse")"
    rm -f -- "$reponse"
    return "$rc"
}

# lancer_programme NAME: starts the menu of the program (--menu); Ctrl+C is answered by the program itself.
lancer_programme() {
    local nom="$1" rc=0
    local -a options=(--menu)
    if (( VERBOSE == 1 )); then options+=(--verbose); fi
    echo
    printf '%s\n' "$(t "Ouverture du menu de" "Opening the menu of") $nom"
    if (( VERBOSE == 1 )); then echo "+ $SCRIPT_DIR/$nom ${options[*]}"; fi
    ctrl_c_child "$SCRIPT_DIR/$nom" "${options[@]}" || rc=$?
    echo
    if (( rc == 0 )); then
        echo "${C_GREEN}$(t "Terminé" "Done")${C_RESET} (code 0)."
    else
        echo "${C_RED}$(t "Code de retour" "Exit code"): $rc${C_RESET}"
    fi
}

# menu_principal: the loop of the menu, with dialog (window) or as text; a terminal is required.
menu_principal() {
    local choix="" i ui="texte" n=${#PROGRAMMES[@]}
    if (( n == 0 )); then
        printf '%s\n' "$(t "Aucun programme avec --menu dans ce dossier." "No program with --menu in this folder.")" >&2
        return 1
    fi
    if [[ ! -t 0 || ! -t 2 ]]; then
        printf '%s\n' "$(t "ERREUR : le menu demande un terminal (entrée et sortie interactives)." \
            "ERROR: the menu needs a terminal (interactive input and output).")" >&2
        return 1
    fi
    ctrl_c_installer
    if ! dialog_presente; then
        if confirmer "$(t "La commande dialog est absente. L'installer maintenant (apt) ?" \
            "The dialog command is missing. Install it now (apt)?")"; then
            installer_dialog || true
        fi
    fi
    if dialog_presente; then ui="dialog"; fi
    while true; do
        if [[ "$ui" == "dialog" ]]; then
            local -a items=()
            for ((i = 0; i < n; i++)); do items+=("$i" "$(libelle "${PROGRAMMES[i]}")"); done
            items+=("q" "$(t "Quitter" "Quit")")
            dialog_run choix --title "admin-menu $SCRIPT_VERSION" --menu \
                "$(t "Choisissez un programme :" "Choose a program:")" 22 100 14 "${items[@]}" || break
        else
            echo
            echo "=============================================================="
            echo " admin-menu $SCRIPT_VERSION"
            echo "=============================================================="
            for ((i = 0; i < n; i++)); do
                printf '  %s%2d%s  %s\n' "$C_GREEN" "$i" "$C_RESET" "$(libelle "${PROGRAMMES[i]}")"
            done
            printf '  %sq%s   %s\n' "$C_GREEN" "$C_RESET" "$(t "Quitter" "Quit")"
            echo
            read -r -p "$(t "Votre choix : " "Your choice: ")" choix || { echo; break; }
        fi
        case "$choix" in
            q|Q) break ;;
        esac
        if [[ "$choix" =~ ^[0-9]+$ ]] && (( choix < n )); then
            lancer_programme "${PROGRAMMES[choix]}"
            read -r -p "$(t "Entrée pour revenir au menu..." "Enter to return to the menu...")" _ || break
        else
            printf '%s\n' "$(t "Choix inconnu : " "Unknown choice: ")« $choix »."
        fi
    done
    return 0
}

# ------------------------------------------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------------------------------------------

# Configuration: /etc/default/admin-menu.conf, then ~/.admin-menu.conf (read, never executed); -c/--config: that file only.
config_lire "$SCRIPT_NAME" "$@"
if [[ -n "${CFG_EXPLICITE:-}" && ! -r "$CFG_EXPLICITE" ]]; then
    printf '%s\n' "$(t "fichier de configuration introuvable ou illisible : " "configuration file not found or unreadable: ")$CFG_EXPLICITE" >&2
    exit 2
fi
choisir_langue
VERBOSE=0
case "${CFG[VERBOSE]:-no}" in
    yes|oui|1|true|on|vrai) VERBOSE=1 ;;
esac

# --report-err: error report at the end of the run (apps/_rapport.sh), when the library is present.
if declare -F rapport_si_demande >/dev/null; then
    rapport_si_demande "$SCRIPT_DIR/$SCRIPT_FILE" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi

DO_CHANGELOG=0; DO_HELP=0; DO_INSTALL=0; DO_LIST=0; DO_VERSION=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --changelog) DO_CHANGELOG=1; shift ;;
        -c|--config)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option -c : fichier attendu" "option -c: file expected")" >&2; exit 2; fi
            shift 2 ;;                                  # read before (apps/_i18n.sh)
        --config=*) shift ;;
        -h|--help) DO_HELP=1; shift ;;
        --install-dialog) DO_INSTALL=1; shift ;;
        --list) DO_LIST=1; shift ;;
        --report-err) shift ;;                          # read before (apps/_rapport.sh)
        -v|--verbose) VERBOSE=1; shift ;;
        --version) DO_VERSION=1; shift ;;
        *)
            printf '%s\n' "$(t "Option inconnue : " "Unknown option: ")$1" >&2
            aide >&2
            exit 2 ;;
    esac
done

if (( DO_VERSION == 1 )); then echo "$SCRIPT_FILE version $SCRIPT_VERSION"; exit 0; fi
if (( DO_HELP == 1 )); then aide; exit 0; fi
if (( DO_CHANGELOG == 1 )); then afficher_changelog || exit 1; exit 0; fi

config_resumer
decouvrir_programmes

if (( DO_INSTALL == 1 )); then installer_dialog; exit $?; fi
if (( DO_LIST == 1 )); then lister; exit 0; fi
if [[ -t 0 && -t 2 ]]; then
    menu_principal
    exit $?
fi
lister
echo
aide
exit 0
