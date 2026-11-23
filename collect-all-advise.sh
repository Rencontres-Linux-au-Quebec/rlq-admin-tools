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
# collect-all-advise.sh - run on the Proxmox host. On every running guest whose name matches --name (BigBlueButton by
# default), it runs "app-log-live.py --advise --days N --export-ai FILE": the LXC containers with pct exec, the virtual
# machines with ssh (sudo). The Markdown reports are copied into DEST/STAMP/, then archived in one file:
#   DEST/collect-all-advise.HOST.AAAA-MM-JJ.tar.xz   (only the *.md reports; read with: tar -tJf FILE)
# The archive name is that of this program (no version), the host is "uname -n" of the Proxmox host.
#
# Usage: collect-all-advise.sh [OPTION]...
#
# Options (sorted alphabetically):
#   --anonymize                  pseudonyms in the reports: IP addresses, e-mails and names (default)
#   --changelog                  show this program's change log
#   -c, --config FILE            this configuration file ONLY (default: /etc/default/collect-all-advise.conf, then
#                                ~/.collect-all-advise.conf if it exists; the command line has priority)
#   --days N                     analysis window in days, from 1 to 366 (default: 2)
#   --dest DIR                   folder of the reports and of the archive (default: /home/dcp9370/audit/rlq-admin-tools)
#   -h, --help                   show this help and exit
#   --lang fr|en                 language of the messages (default: LANGUAGE of the configuration file, then LC_ALL / LC_MESSAGES / LANG)
#   --name REGEX                 only the guests whose name matches REGEX (default: bbb)
#   --no-anonymize               keep the real addresses, e-mails and names in the reports
#   --no-archive                 no archive: only the folder of the reports
#   --program PATH               app-log-live.py on the guests (default: /usr/local/bin/app-log-live.py)
#   --ssh-user USER              account used for the virtual machines; it needs sudo without a password (default: root)
#   --version                    show the version and exit
#
# Configuration (/etc/default/collect-all-advise.conf, then ~/.collect-all-advise.conf if it exists; the last one wins;
# read, never executed). KEY=VALUE lines, with # comments:
#   ANONYMIZE=yes               yes or no (--anonymize / --no-anonymize)
#   ARCHIVE=yes                 yes or no (--no-archive)
#   DAYS=2                      analysis window in days (--days)
#   DEST=/home/dcp9370/audit/rlq-admin-tools   folder (--dest)
#   LANGUAGE=auto               fr, en or auto (--lang)
#   NAME_REGEX=bbb              guests to collect (--name)
#   PROGRAM=/usr/local/bin/app-log-live.py     program on the guests (--program)
#   SSH_USER=root               account of the virtual machines (--ssh-user)
#   VM_HOST_<VMID>=ADDRESS      ssh address of a virtual machine, for example VM_HOST_201=10.0.0.21
#
# ========================================================================================================================

set -euo pipefail

readonly SCRIPT_VERSION="1.0.20261123.101934"
readonly SCRIPT_NAME="collect-all-advise"
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

declare -A CFG=()
CONFIG_EXPLICITE=""
CONFIG_LUES=()
LANGUE="fr"

# t FRENCH ENGLISH: the message in the language chosen (--lang, LANGUAGE, then the locale).
t() {
    if [[ "$LANGUE" == "en" ]]; then printf '%s' "$2"; else printf '%s' "$1"; fi
}

# oui_non VALUE: 1 for yes / oui / true / 1 / on, 0 otherwise.
oui_non() {
    case "${1,,}" in
        yes|oui|true|1|on|vrai) echo 1 ;;
        *) echo 0 ;;
    esac
}

# lire_config: /etc/default/NAME.conf then ~/.NAME.conf (or -c FILE only). KEY=VALUE lines, never executed.
lire_config() {
    local -a fichiers=()
    local f ligne cle valeur
    if [[ -n "$CONFIG_EXPLICITE" ]]; then
        fichiers=("$CONFIG_EXPLICITE")
    else
        fichiers=("/etc/default/$SCRIPT_NAME.conf" "${HOME:-/root}/.$SCRIPT_NAME.conf")
    fi
    for f in "${fichiers[@]}"; do
        [[ -r "$f" ]] || continue
        CONFIG_LUES+=("$f")
        while IFS= read -r ligne || [[ -n "$ligne" ]]; do
            ligne="${ligne%%#*}"
            ligne="${ligne#"${ligne%%[![:space:]]*}"}"
            ligne="${ligne%"${ligne##*[![:space:]]}"}"
            [[ "$ligne" == *=* ]] || continue
            cle="${ligne%%=*}"; valeur="${ligne#*=}"
            cle="${cle//[[:space:]]/}"; cle="${cle^^}"
            valeur="${valeur#"${valeur%%[![:space:]]*}"}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"
            if [[ "$valeur" == \"*\" && ${#valeur} -ge 2 ]]; then valeur="${valeur:1:${#valeur}-2}"; fi
            [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]] && CFG["$cle"]="$valeur"
        done < "$f"
    done
}

# choisir_langue ARGUMENTS...: --lang, then LANGUAGE of the configuration file, then the locale (fr by default).
choisir_langue() {
    local valeur="" i
    local -a args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do
        case "${args[i]}" in
            --lang) valeur="${args[i+1]:-}" ;;
            --lang=*) valeur="${args[i]#--lang=}" ;;
        esac
    done
    [[ -n "$valeur" ]] || valeur="${CFG[LANGUAGE]:-auto}"
    if [[ "$valeur" == auto || -z "$valeur" ]]; then valeur="${LC_ALL:-${LC_MESSAGES:-${LANG:-fr}}}"; fi
    case "${valeur,,}" in
        en*) LANGUE="en" ;;
        *) LANGUE="fr" ;;
    esac
}

aide() {
    local o
    echo "$(t "Usage" "Usage") : $SCRIPT_FILE [$(t "OPTION" "OPTION")]..."
    echo
    echo "$(t "Options (triées par ordre alphabétique) :" "Options (sorted alphabetically):")"
    while IFS= read -r o; do
        printf '  %s%s%s\n' "$C_CYAN" "$o" "$C_RESET"
    done <<'EOF'
--anonymize                  pseudonymes dans les rapports : adresses IP, courriels et noms (défaut) / pseudonyms in the reports (default)
--changelog                  journal des modifications de ce programme / change log of this program
-c, --config FILE            ce fichier de configuration SEUL / this configuration file ONLY
--days N                     fenêtre d'analyse en jours, de 1 à 366 (défaut 2) / analysis window in days, 1 to 366 (default 2)
--dest DIR                   dossier des rapports et de l'archive / folder of the reports and of the archive
-h, --help                   affiche cette aide et quitte / show this help and exit
--lang fr|en                 langue des messages / language of the messages
--name REGEX                 seulement les machines dont le nom correspond (défaut bbb) / only the guests whose name matches (default bbb)
--no-anonymize               garde les vraies adresses, courriels et noms / keep the real addresses, e-mails and names
--no-archive                 pas d'archive : seulement le dossier / no archive: only the folder
--program PATH               app-log-live.py sur les machines / app-log-live.py on the guests
--ssh-user USER              compte des VM (sudo sans mot de passe) / account of the VMs (sudo without a password)
--version                    affiche la version et quitte / show the version and exit
EOF
    echo
    echo "$(t "Configuration : /etc/default/collect-all-advise.conf, puis ~/.collect-all-advise.conf (le dernier l'emporte)." \
        "Configuration: /etc/default/collect-all-advise.conf, then ~/.collect-all-advise.conf (the last one wins).")"
}

afficher_changelog() {
    if [[ ! -r "$CHANGELOG_FILE" ]]; then
        echo "CHANGELOG.md: $(t "fichier introuvable" "file not found")" >&2
        return 1
    fi
    awk -v cle="## $SCRIPT_FILE" '/^## /{dans = ($0 == cle); if (dans) print; next} dans' "$CHANGELOG_FILE" \
        | sed -E "s/^(### )([0-9]+[.][0-9]+[.][0-9]{8}[.][0-9]{6})/\1${C_CYAN}\2${C_RESET}/" || true
}

# valider_jours VALUE: an integer from 1 to 366.
valider_jours() {
    [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1 && 10#$1 <= 366 ))
}

# collecter_lxc VMID NAME DIR: run the program in the container, copy the report out, remove it from the container.
collecter_lxc() {
    local vmid="$1" name="$2" dossier="$3" rapport sortie
    rapport="/tmp/$SCRIPT_NAME-$STAMP-$vmid.md"
    sortie="$dossier/advise-$STAMP.txt"
    mkdir -p "$dossier"
    pct exec "$vmid" -- rm -f "$rapport" >/dev/null 2>&1 || true
    if pct exec "$vmid" -- "$PROGRAM" --advise --days "$DAYS" --export-ai "$rapport" "$ANONYMIZE_OPT" --no-follow --no-keys >"$sortie" 2>&1 \
       && pct pull "$vmid" "$rapport" "$dossier/export-ai-$STAMP.md"; then
        printf '%s\n' "[OK] LXC $vmid $name -> $dossier/export-ai-$STAMP.md"
        RAPPORTS_OK=$((RAPPORTS_OK + 1))
    else
        printf '%s\n' "$C_RED[ATTN]$C_RESET $(t "LXC" "LXC") $vmid $name : $(t "pas de rapport" "no report") ($sortie)"
        RAPPORTS_KO=$((RAPPORTS_KO + 1))
    fi
    pct exec "$vmid" -- rm -f "$rapport" >/dev/null 2>&1 || true
}

# collecter_vm VMID NAME DIR: same through ssh; the report is read back on standard output.
collecter_vm() {
    local vmid="$1" name="$2" dossier="$3" adresse="${CFG[VM_HOST_$1]:-}" rapport="/tmp/$SCRIPT_NAME-$STAMP-$1.md"
    local cible="$SSH_USER@$adresse" sortie
    if [[ -z "$adresse" ]]; then
        printf '%s\n' "$C_YELLOW[ATTN]$C_RESET $(t "VM" "VM") $vmid $name : $(t "adresse absente (VM_HOST_$vmid dans la configuration) : ignorée" "no address (VM_HOST_$vmid in the configuration): skipped")"
        RAPPORTS_KO=$((RAPPORTS_KO + 1))
        return 0
    fi
    mkdir -p "$dossier"
    sortie="$dossier/advise-$STAMP.txt"
    if ssh -o BatchMode=yes "$cible" "sudo $PROGRAM --advise --days $DAYS --export-ai $rapport $ANONYMIZE_OPT --no-follow --no-keys" >"$sortie" 2>&1 \
       && ssh -o BatchMode=yes "$cible" "sudo cat $rapport" >"$dossier/export-ai-$STAMP.md"; then
        printf '%s\n' "[OK] VM $vmid $name -> $dossier/export-ai-$STAMP.md"
        RAPPORTS_OK=$((RAPPORTS_OK + 1))
    else
        printf '%s\n' "$C_RED[ATTN]$C_RESET $(t "VM" "VM") $vmid $name : $(t "pas de rapport" "no report") ($sortie)"
        RAPPORTS_KO=$((RAPPORTS_KO + 1))
    fi
    ssh -o BatchMode=yes "$cible" "sudo rm -f $rapport" >/dev/null 2>&1 || true
}

# archiver: DEST/collect-all-advise.HOST.AAAA-MM-JJ.tar.xz with the *.md reports of this run (a suffix -2, -3... if the day has one).
archiver() {
    local hote date_jour base archive n=2
    hote="$(uname -n)"
    date_jour="$(date +%Y-%m-%d)"
    base="$DEST/$SCRIPT_NAME.$hote.$date_jour"
    archive="$base.tar.xz"
    while [[ -e "$archive" ]]; do
        archive="$base-$n.tar.xz"
        n=$((n + 1))
    done
    if ! (cd "$RUN" && find . -name '*.md' -print0 | tar --null -T - -cJf "$archive"); then
        printf '%s\n' "$C_RED[ATTN]$C_RESET $(t "archive non créée" "archive not created") : $archive"
        return 1
    fi
    printf '%s\n' "[OK] $(t "archive" "archive") : $archive"
}

# ------------------------------------------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------------------------------------------

args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
    case "${args[i]}" in
        -c|--config)
            if (( i + 1 >= ${#args[@]} )); then echo "option -c : fichier attendu / file expected" >&2; exit 2; fi
            CONFIG_EXPLICITE="${args[i+1]}" ;;
        --config=*) CONFIG_EXPLICITE="${args[i]#--config=}" ;;
    esac
done
if [[ -n "$CONFIG_EXPLICITE" && ! -r "$CONFIG_EXPLICITE" ]]; then
    echo "$(t "fichier de configuration introuvable ou illisible : " "configuration file not found or unreadable: ")$CONFIG_EXPLICITE" >&2
    exit 2
fi
lire_config
choisir_langue "$@"

DO_CHANGELOG=0; DO_HELP=0; DO_VERSION=0
DAYS="${CFG[DAYS]:-2}"
DEST="${CFG[DEST]:-/home/dcp9370/audit/rlq-admin-tools}"
NAME_RE="${CFG[NAME_REGEX]:-bbb}"
PROGRAM="${CFG[PROGRAM]:-/usr/local/bin/app-log-live.py}"
SSH_USER="${CFG[SSH_USER]:-root}"
ANONYMIZE_OPT="--anonymize"
if [[ "$(oui_non "${CFG[ANONYMIZE]:-yes}")" == 0 ]]; then ANONYMIZE_OPT="--no-anonymize"; fi
ARCHIVE=1
if [[ "$(oui_non "${CFG[ARCHIVE]:-yes}")" == 0 ]]; then ARCHIVE=0; fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --anonymize) ANONYMIZE_OPT="--anonymize"; shift ;;
        --changelog) DO_CHANGELOG=1; shift ;;
        -c|--config) shift 2 ;;
        --config=*) shift ;;
        --days)
            if [[ $# -lt 2 ]]; then echo "$(t "option --days : nombre de jours attendu" "option --days: number of days expected")" >&2; exit 2; fi
            DAYS="$2"; shift 2 ;;
        --days=*) DAYS="${1#--days=}"; shift ;;
        --dest)
            if [[ $# -lt 2 ]]; then echo "$(t "option --dest : dossier attendu" "option --dest: folder expected")" >&2; exit 2; fi
            DEST="$2"; shift 2 ;;
        --dest=*) DEST="${1#--dest=}"; shift ;;
        -h|--help) DO_HELP=1; shift ;;
        --lang)
            if [[ $# -lt 2 ]]; then echo "$(t "option --lang : fr ou en attendu" "option --lang: fr or en expected")" >&2; exit 2; fi
            shift 2 ;;
        --lang=*) shift ;;
        --name)
            if [[ $# -lt 2 ]]; then echo "$(t "option --name : expression attendue" "option --name: expression expected")" >&2; exit 2; fi
            NAME_RE="$2"; shift 2 ;;
        --name=*) NAME_RE="${1#--name=}"; shift ;;
        --no-anonymize) ANONYMIZE_OPT="--no-anonymize"; shift ;;
        --no-archive) ARCHIVE=0; shift ;;
        --program)
            if [[ $# -lt 2 ]]; then echo "$(t "option --program : chemin attendu" "option --program: path expected")" >&2; exit 2; fi
            PROGRAM="$2"; shift 2 ;;
        --program=*) PROGRAM="${1#--program=}"; shift ;;
        --ssh-user)
            if [[ $# -lt 2 ]]; then echo "$(t "option --ssh-user : utilisateur attendu" "option --ssh-user: user expected")" >&2; exit 2; fi
            SSH_USER="$2"; shift 2 ;;
        --ssh-user=*) SSH_USER="${1#--ssh-user=}"; shift ;;
        --version) DO_VERSION=1; shift ;;
        *)
            echo "$(t "Option inconnue : " "Unknown option: ")$1" >&2
            aide >&2
            exit 2 ;;
    esac
done

if (( DO_VERSION == 1 )); then echo "$SCRIPT_FILE version $SCRIPT_VERSION"; exit 0; fi
if (( DO_HELP == 1 )); then aide; exit 0; fi
if (( DO_CHANGELOG == 1 )); then afficher_changelog || exit 1; exit 0; fi

if ! valider_jours "$DAYS"; then
    echo "$(t "--days : un nombre de jours de 1 à 366 est attendu (reçu : " "--days: a number of days from 1 to 366 is expected (got: ")$DAYS)" >&2
    exit 2
fi
# --name is a regular expression used only to filter the guest names (never executed): it must compile (bash status 2 otherwise).
rc_regex=0; [[ "" =~ $NAME_RE ]] 2>/dev/null || rc_regex=$?
if (( rc_regex == 2 )); then
    echo "$(t "--name : expression refusée : " "--name: expression refused: ")$NAME_RE" >&2
    exit 2
fi

# Configuration read, shown on standard error (the reports are on standard output of the run).
if (( ${#CONFIG_LUES[@]} == 0 )); then
    echo "$(t "Configuration : aucun fichier (valeurs par défaut)" "Configuration: no file (default values)")" >&2
else
    echo "$(t "Configuration lue : " "Configuration read: ")${CONFIG_LUES[*]}" >&2
fi
echo "$(t "Fenêtre : $DAYS jour(s) · anonymisation : $ANONYMIZE_OPT · machines : $NAME_RE · dossier : $DEST" \
    "Window: $DAYS day(s) · anonymization: $ANONYMIZE_OPT · guests: $NAME_RE · folder: $DEST")" >&2

STAMP="$(date +%Y%m%d-%H%M%S)"
RUN="$DEST/$STAMP"
mkdir -p "$RUN"
RAPPORTS_OK=0
RAPPORTS_KO=0

# LXC containers (pct list: VMID STATUS LOCK NAME, the name is the last column).
if command -v pct >/dev/null 2>&1; then
    while read -r vmid status name; do
        [[ "$status" == "running" && "$name" =~ $NAME_RE ]] || continue
        collecter_lxc "$vmid" "$name" "$RUN/lxc-$vmid-$name"
    done < <(pct list | awk 'NR > 1 {print $1, $2, $NF}')
else
    echo "$(t "pct introuvable : pas de conteneur LXC collecté" "pct not found: no LXC container collected")" >&2
fi

# Virtual machines (qm list: VMID NAME STATUS ...).
if command -v qm >/dev/null 2>&1; then
    while read -r vmid status name; do
        [[ "$status" == "running" && "$name" =~ $NAME_RE ]] || continue
        collecter_vm "$vmid" "$name" "$RUN/vm-$vmid-$name"
    done < <(qm list | awk 'NR > 1 {print $1, $3, $2}')
else
    echo "$(t "qm introuvable : pas de machine virtuelle collectée" "qm not found: no virtual machine collected")" >&2
fi

ARCHIVE_OK=1
if (( ARCHIVE == 1 && RAPPORTS_OK > 0 )); then
    archiver || ARCHIVE_OK=0
fi

echo "$(t "Rapports collectés : $RAPPORTS_OK · en échec : $RAPPORTS_KO · dossier : $RUN" \
    "Reports collected: $RAPPORTS_OK · failed: $RAPPORTS_KO · folder: $RUN")"

if (( RAPPORTS_KO > 0 || ARCHIVE_OK == 0 )); then exit 1; fi
exit 0
