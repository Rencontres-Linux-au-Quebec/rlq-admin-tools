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
# collect-all-advise.sh - run on the Proxmox host. On every running guest whose name matches --name (BigBlueButton and Odoo by
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
#   --dest DIR                   folder of the reports and of the archive (default: audit/collect-all-advise in the sudo user home)
#   -h, --help                   show this help and exit
#   --install-timer              install the systemd service and timer: run every day at TIMER_TIME (root)
#   --lang fr|en                 language of the messages (default: LANGUAGE of the configuration file, then LC_ALL / LC_MESSAGES / LANG)
#   --lxc-logs                   the logs of our programs of EVERY running LXC container, copied as they are (default; --no-lxc-logs: none)
#   --name REGEX                 only the guests whose name matches REGEX (default: bbb|odoo)
#   --no-anonymize               keep the real addresses, e-mails and names in the reports
#   --no-archive                 no archive: only the folder of the reports
#   --no-logs                    no archive of the raw logs in /var/lib/collect-all-advise/
#   --no-lxc-logs                no copy of the logs of the LXC containers
#   --no-sqli-evidence           no search of the SQL injection evidence in the Odoo containers
#   --no-security                no check of the security updates
#   --no-sync                    never offer to update the suite in the guests before the collection
#   --program PATH               app-log-live.py on the guests (default: /opt/rlq-admin-tools/app-log-live.py)
#   --remove-timer               disable and remove the systemd timer (root)
#   --sqli-evidence              SQL injection evidence in EVERY running Odoo container (default; --no-sqli-evidence: none)
#   --sqli-from "AAAA-MM-JJ HH:MM:SS"  start of the attack window, local time (default: 24 hours before now)
#   --sqli-to "AAAA-MM-JJ HH:MM:SS"    end of the attack window, local time (default: now)
#   --ssh-user USER              account used for the virtual machines; it needs sudo without a password (default: root)
#   --sync                       update the suite in the guests that are behind, without a question (host-perf-audit.py --guest-sync)
#   -v, --verbose                show each step and each command run in the guests (their address, exit codes)
#   --version                    show the version and exit
#
# Configuration (/etc/default/collect-all-advise.conf, then ~/.collect-all-advise.conf if it exists; the last one wins;
# read, never executed). KEY=VALUE lines, with # comments:
#   ANONYMIZE=yes               yes or no (--anonymize / --no-anonymize)
#   ARCHIVE=yes                 yes or no (--no-archive)
#   LOGS=yes                    yes or no (--no-logs): raw logs of the host (nginx, fail2ban, Odoo, PostgreSQL) packed in /var/lib/collect-all-advise/
#   LXC_LOGS=yes                yes or no (--no-lxc-logs): the logs of our programs (LXC_LOG_PATHS) of every running LXC container,
#                               copied as they are (no anonymisation), packed in one root-only archive *.lxc-logs.tar.xz
#   LXC_LOG_PATHS=...           paths or globs looked for in each LXC, separated by spaces (no space inside a path)
#   SQLI_EVIDENCE=yes           yes or no (--no-sqli-evidence): evidence of SQL injection in each Odoo container, archived as
#                               *.sqli-evidence.tar.xz, with a verdict per container (sqli-verdict.txt)
#   SQLI_FROM / SQLI_TO         attack window, "AAAA-MM-JJ HH:MM:SS" in local time (empty: the last 24 hours)
#   SQLI_QUERIES=...            odoo-sql-maint queries run in each Odoo container (default: xss-content,xss-persistence,push-count)
#   SQLI_ODOO_UNITS=...         systemd units of Odoo whose journal is searched (default: erplibre erplibre_erplibre)
#   ODOO_SQL_MAINT=PATH         odoo-sql-maint in an Odoo container (default: /opt/rlq-admin-tools/odoo-sql-maint)
#   SQLI_NGINX_LOGS=...         nginx access logs searched for the injection requests (default: access.log and access.log.1)
#   SECURITY=yes                yes or no (--no-security): check of the pending security updates of the host and the guests
#   SYNC=ask                    ask, yes or no (--sync / --no-sync): update the suite in the guests that are behind, before the collection
#   DAYS=2                      analysis window in days (--days)
#   DEST=...                    folder (--dest; default: audit/collect-all-advise in the sudo user home)
#   LANGUAGE=fr                 fr or en: language of the messages AND of the reports (--lang)
#   TIMER=no                    yes or no: a systemd timer runs the collection every day (--install-timer)
#   TIMER_TIME=03:30            time of the daily run, HH:MM (local time of the host)
#   NAME_REGEX=bbb|odoo         guests to collect (--name)
#   PROGRAM=/opt/rlq-admin-tools/app-log-live.py   program on the guests (--program)
#   SSH_USER=root               account of the virtual machines (--ssh-user)
#   VM_HOST_<VMID>=ADDRESS      ssh address of a virtual machine, for example VM_HOST_201=10.0.0.21
#   VM_PORT_<VMID>=PORT         ssh port of a virtual machine (22 by default), for example VM_PORT_433=3815; a Host block of
#                               ~/.ssh/config whose HostName is the address of the VM is used too (its alias, so its Port)
#
# ========================================================================================================================

set -euo pipefail

readonly SCRIPT_VERSION="1.15.20261128.105936"
# Roots of the raw logs and of the archive of the logs (variables only for the tests).
RACINE_LOG="${NGINX_TOOLS_LOG_ROOT:-/var/log}"
RACINE_VAR="${NGINX_TOOLS_VAR_ROOT:-/var/lib}"
readonly SCRIPT_NAME="collect-all-advise"
SCRIPT_FILE="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_FILE
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
ETC_DEFAULT="${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}"
SYSTEMD_DIR="${NGINX_TOOLS_SYSTEMD_DIR:-/etc/systemd/system}"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_CYAN=$'\x1b[1;36m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_YELLOW=""; C_CYAN=""; C_RESET=""
fi

# First line of EVERY run, even with --help: the name and version (--version displays it itself).
case " $* " in *" --version "*) ;; *) echo "$SCRIPT_FILE v$SCRIPT_VERSION" ;; esac

# PY_IPV4: first IPv4 address (not loopback, not link-local) in the answer of "qm guest cmd VMID network-get-interfaces".
read -r -d '' PY_IPV4 <<'PY' || true
import json, sys
for interface in json.load(sys.stdin):
    if interface.get("name") == "lo":
        continue
    for adresse in interface.get("ip-addresses", []):
        ip = adresse.get("ip-address", "")
        if adresse.get("ip-address-type") == "ipv4" and not ip.startswith(("127.", "169.254.")):
            print(ip)
            raise SystemExit
PY

declare -A CFG=()
CONFIG_EXPLICITE=""
CONFIG_LUES=()
CONFIG_CREEE=""
LANGUE="fr"

# t FRENCH ENGLISH: the message in the language chosen (--lang, LANGUAGE, then the locale).
t() {
    if [[ "$LANGUE" == "en" ]]; then printf '%s' "$2"; else printf '%s' "$1"; fi
}

# trace TEXT: with --verbose, one line on the standard error (the steps of the run; the output of the guests is in the files)
VERBOSE=0
trace() {
    if (( VERBOSE == 1 )); then printf '%s\n' "  [trace] $*" >&2; fi
}

# oui_non VALUE: 1 for yes / oui / true / 1 / on, 0 otherwise.
oui_non() {
    case "${1,,}" in
        yes|oui|o|y|true|1|on|vrai) echo 1 ;;
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
        fichiers=("$ETC_DEFAULT/$SCRIPT_NAME.conf" "${HOME:-/root}/.$SCRIPT_NAME.conf")
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
    if (( ${#CONFIG_LUES[@]} == 0 )) && [[ -z "$CONFIG_EXPLICITE" ]]; then
        creer_config
    fi
}

# creer_config: no configuration file yet: the default one is written (root: ETC_DEFAULT, otherwise ~/.NAME.conf).
# home_sudo: home folder of the user who ran sudo (SUDO_USER), otherwise of the current user.
home_sudo() {
    local h=""
    if [[ -n "${SUDO_USER:-}" ]]; then h="$(getent passwd "$SUDO_USER" 2>/dev/null | cut -d: -f6 || true)"; fi
    echo "${h:-${HOME:-/root}}"
}

# dest_defaut: the default folder of the reports (audit/collect-all-advise in the home folder of the sudo user).
dest_defaut() {
    echo "$(home_sudo)/audit/$SCRIPT_NAME"
}

# lang_donnee: 0 when --lang is on the command line (the language is then not asked on the first run).
lang_donnee() {
    local a
    for a in "${args[@]}"; do
        case "$a" in --lang|--lang=*) return 0 ;; esac
    done
    return 1
}

# lire_reponse QUESTION DEFAUT: one answer read on the terminal; Enter gives DEFAUT.
lire_reponse() {
    local reponse=""
    read -r -p "$1" reponse </dev/tty || reponse=""
    printf '%s' "${reponse:-$2}"
}

# creer_config: no configuration file yet. On a terminal the language is asked first (fr or en: the messages AND the reports),
# then the other questions, in that language only (Enter keeps the default). Without a terminal the default values are written.
# root: ETC_DEFAULT, otherwise ~/.NAME.conf. An existing file is never overwritten.
creer_config() {
    local cible dest prog ssh_user regex jours minuteur="no" heure="03:30" reponse="" interactif=0
    if (( EUID == 0 )); then cible="$ETC_DEFAULT/$SCRIPT_NAME.conf"; else cible="${HOME:-/root}/.$SCRIPT_NAME.conf"; fi
    mkdir -p "$(dirname "$cible")" 2>/dev/null || return 0
    if [[ -e "$cible" ]]; then return 0; fi
    dest="$(dest_defaut)"
    prog="/opt/rlq-admin-tools/app-log-live.py"
    ssh_user="root"
    regex="bbb|odoo"
    jours=2
    choisir_langue "${args[@]}"
    if [[ -z "${COLLECT_NO_PROMPT:-}" ]] && { : </dev/tty; } 2>/dev/null; then interactif=1; fi   # COLLECT_NO_PROMPT=1: never ask (tests, cron)
    if (( interactif == 1 )); then
        if ! lang_donnee; then
            reponse="$(lire_reponse "Langue des messages et des rapports / messages and reports language (fr, en) [$LANGUE] : " "$LANGUE")"
            case "${reponse,,}" in
                en*) LANGUE="en" ;;
                *) LANGUE="fr" ;;
            esac
        fi
        printf '%s\n' "$(t "Premier lancement : répondez aux questions (Entrée = valeur par défaut)." \
            "First run: answer the questions (Enter = default value).")" >&2
        dest="$(lire_reponse "$(t "Dossier des rapports [$dest] : " "Reports folder [$dest]: ")" "$dest")"
        while :; do
            jours="$(lire_reponse "$(t "Nombre de jours analysés, de 1 à 366 [$jours] : " "Number of days analysed, 1 to 366 [$jours]: ")" "$jours")"
            valider_jours "$jours" && break
            printf '%s\n' "$(t "Valeur refusée : un nombre de 1 à 366 est attendu." "Refused value: a number from 1 to 366 is expected.")" >&2
        done
        prog="$(lire_reponse "$(t "app-log-live.py sur les machines [$prog] : " "app-log-live.py on the guests [$prog]: ")" "$prog")"
        ssh_user="$(lire_reponse "$(t "Compte SSH des VM [$ssh_user] : " "SSH account of the VMs [$ssh_user]: ")" "$ssh_user")"
        regex="$(lire_reponse "$(t "Machines (expression, .* pour toutes) [$regex] : " "Guests (regex, .* for all) [$regex]: ")" "$regex")"
        if [[ "$(oui_non "$(lire_reponse "$(t "Lancer chaque jour automatiquement (minuteur systemd) ? [o/N] : " \
            "Run every day automatically (systemd timer)? [y/N]: ")" "n")")" == 1 ]]; then
            minuteur="yes"
            while :; do
                heure="$(lire_reponse "$(t "Heure du lancement HH:MM [$heure] : " "Start time HH:MM [$heure]: ")" "$heure")"
                [[ "$heure" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] && break
                printf '%s\n' "$(t "Heure refusée : HH:MM attendu (ex. 03:30)." "Refused time: HH:MM expected (e.g. 03:30).")" >&2
            done
        fi
    fi
    cat > "$cible" 2>/dev/null <<CONF || return 0
# collect-all-advise.conf - created by collect-all-advise.sh (the command line has priority).
# yes: pseudonyms in the reports (IP addresses, e-mails, names); no: the real values.
ANONYMIZE=yes
# yes: the reports are packed in one archive collect-all-advise.HOST.AAAA-MM-JJ.tar.xz; no: the folder only.
ARCHIVE=yes
# yes: the raw logs of the host (nginx, fail2ban, Odoo, PostgreSQL) are packed in /var/lib/collect-all-advise/, readable by root only; no: none.
LOGS=yes
# yes: the logs of our programs are searched in EVERY running LXC container and copied as they are (no anonymisation) into one root-only archive; no: none.
LXC_LOGS=yes
# paths or globs looked for in each LXC container, separated by spaces.
LXC_LOG_PATHS=$LXC_LOG_PATHS_DEFAUT
# yes: evidence of an SQL injection (Odoo journal, injection requests of nginx, odoo-sql-maint) in every running Odoo container, copied as they are
# into one root-only archive *.sqli-evidence.tar.xz, with a verdict per container; no: none.
SQLI_EVIDENCE=yes
# attack window, "AAAA-MM-JJ HH:MM:SS" in local time; empty: the last 24 hours.
SQLI_FROM=
SQLI_TO=
# odoo-sql-maint in the Odoo containers.
ODOO_SQL_MAINT=/opt/rlq-admin-tools/odoo-sql-maint
# analysis window in days, from 1 to 366.
DAYS=$jours
# folder of the reports and of the archive.
DEST=$dest
# fr or en: language of the messages AND of the reports (given to app-log-live.py as APP_LOG_LIVE_LANG).
LANGUAGE=$LANGUE
# guests whose name matches this regular expression (bbb|odoo: BigBlueButton and Odoo; .* : every guest).
NAME_REGEX=$regex
# app-log-live.py on the guests.
PROGRAM=$prog
# account used for the virtual machines; it needs sudo without a password.
SSH_USER=$ssh_user
# ask: before the collection, offer to update the suite in the guests whose app-log-live.py is older than the one of this host
# (host-perf-audit.py --guest-sync); yes: update them without a question; no: never.
SYNC=ask
# yes: a systemd timer runs the collection every day at TIMER_TIME (installed with --install-timer); no: no timer.
TIMER=$minuteur
# time of the daily run, HH:MM (local time of the host).
TIMER_TIME=$heure
# optional: ssh address of a virtual machine, when its automatic detection fails (VM_HOST_<VMID>=ADDRESS).
# VM_HOST_201=10.0.0.21
# optional: ssh port of a virtual machine, when it is not 22 (VM_PORT_<VMID>=PORT).
# VM_PORT_433=3815
CONF
    CONFIG_CREEE="$cible"
    CFG[DAYS]="$jours"; CFG[DEST]="$dest"; CFG[LANGUAGE]="$LANGUE"; CFG[NAME_REGEX]="$regex"
    CFG[PROGRAM]="$prog"; CFG[SSH_USER]="$ssh_user"; CFG[TIMER]="$minuteur"; CFG[TIMER_TIME]="$heure"
    if [[ "$minuteur" == "yes" ]]; then
        installer_minuteur || true
    fi
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
    printf '%s\n' "$(t "Usage" "Usage") : $SCRIPT_FILE [$(t "OPTION" "OPTION")]..."
    echo
    printf '%s\n' "$(t "Options (triées par ordre alphabétique) :" "Options (sorted alphabetically):")"
    while IFS= read -r o; do
        printf '  %s%s%s\n' "$C_CYAN" "$o" "$C_RESET"
    done <<'EOF'
--anonymize                  pseudonymes dans les rapports : adresses IP, courriels et noms (défaut) / pseudonyms in the reports (default)
--changelog                  journal des modifications de ce programme / change log of this program
-c, --config FILE            ce fichier de configuration SEUL / this configuration file ONLY
--days N                     fenêtre d'analyse en jours, de 1 à 366 (défaut 2) / analysis window in days, 1 to 366 (default 2)
--dest DIR                   dossier des rapports et de l'archive / folder of the reports and of the archive
-h, --help                   affiche cette aide et quitte / show this help and exit
--install-timer              installe le service et le minuteur systemd (quotidien, root) / install the systemd service and timer (daily, root)
--lang fr|en                 langue des messages et des rapports / language of the messages and the reports
--lxc-logs                   journaux de nos programmes dans TOUS les conteneurs LXC en marche, copiés tels quels / logs of our programs in EVERY running LXC container, copied as they are
--name REGEX                 seulement les machines dont le nom correspond (défaut bbb|odoo) / only the guests whose name matches (default bbb|odoo)
--no-anonymize               garde les vraies adresses, courriels et noms / keep the real addresses, e-mails and names
--no-archive                 pas d'archive : seulement le dossier / no archive: only the folder
--no-logs                    pas d'archive des journaux bruts dans /var/lib/collect-all-advise/ / no archive of the raw logs in /var/lib/collect-all-advise/
--no-lxc-logs                pas de copie des journaux des conteneurs LXC / no copy of the logs of the LXC containers
--no-sqli-evidence           pas de preuves d'injection SQL dans les conteneurs Odoo / no SQL injection evidence in the Odoo containers
--no-security                pas de vérification des mises à jour de sécurité / no check of the security updates
--no-sync                    ne propose pas de mettre à jour la suite dans les invités / never offer to update the suite in the guests
--program PATH               app-log-live.py sur les machines / app-log-live.py on the guests
--remove-timer               supprime le minuteur systemd (root) / remove the systemd timer (root)
--sqli-evidence              preuves d'injection SQL dans CHAQUE conteneur Odoo en marche (défaut) / SQL injection evidence in EVERY running Odoo container (default)
--sqli-from DATE             début de la fenêtre d'attaque, AAAA-MM-JJ HH:MM:SS, heure locale (défaut : 24 h) / start of the attack window, local time (default: 24 hours)
--sqli-to DATE               fin de la fenêtre d'attaque, heure locale (défaut : maintenant) / end of the attack window, local time (default: now)
--ssh-user USER              compte des VM (sudo sans mot de passe) / account of the VMs (sudo without a password)
--sync                       met à jour sans question la suite dans les invités en retard / update the suite in the guests that are behind, no question
-v, --verbose                affiche chaque étape et chaque commande lancée dans les invités / show each step and each command run in the guests
--version                    affiche la version et quitte / show the version and exit
EOF
    echo
    printf '%s\n' "$(t "Configuration : /etc/default/collect-all-advise.conf, puis ~/.collect-all-advise.conf (le dernier l'emporte)." \
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
# SECU_CIBLES: the machines to check for security updates, each "KIND ID ADDRESS NAME" ("hote - - NAME", "lxc VMID - NAME", "vm VMID ADDRESS NAME").
SECU_CIBLES=()

# COMMANDE_SECURITE: the pending security updates, one package name per line (the package lists are refreshed first).
COMMANDE_SECURITE='apt-get update -qq >/dev/null 2>&1; apt-get -s upgrade 2>/dev/null | grep "^Inst" | grep -e "-security" | cut -d " " -f 2'

# sur_machine KIND ID ADDRESS COMMAND: runs COMMAND as root on the host (hote), in an LXC container (pct exec) or on a VM (ssh, sudo).
# ssh_vm ADDRESS COMMAND: ssh to SSH_USER@ADDRESS in batch mode, 15 s to connect; ADDRESS may end with :PORT (VM_PORT_<VMID>).
ssh_vm() {
    local a="$1" port=()
    shift
    if [[ "$a" =~ ^(.+):([0-9]+)$ ]]; then a="${BASH_REMATCH[1]}"; port=(-p "${BASH_REMATCH[2]}"); fi
    ssh -o BatchMode=yes -o ConnectTimeout=15 "${port[@]}" "$SSH_USER@$a" "$@"
}

# alias_ssh ADDRESS: the first alias of a Host block of ~/.ssh/config (of the user running this script, root on the host) whose
# HostName is ADDRESS, so that its Port, User or IdentityFile apply; empty when there is none.
alias_ssh() {
    local fichier="${HOME:-/root}/.ssh/config"
    [[ -r "$fichier" ]] || return 0
    awk -v ip="$1" '
        tolower($1) == "host"     { alias = ""; for (i = 2; i <= NF; i++) if ($i !~ /[*?!]/) { alias = $i; break } }
        tolower($1) == "hostname" && $2 == ip && alias != "" { print alias; exit }
    ' "$fichier" 2>/dev/null || true
}

# port_ssh ALIAS: the Port of this Host block of ~/.ssh/config (for the trace only), empty when not given.
port_ssh() {
    local fichier="${HOME:-/root}/.ssh/config"
    [[ -r "$fichier" ]] || return 0
    awk -v h="$1" '
        tolower($1) == "host" { dans = 0; for (i = 2; i <= NF; i++) if ($i == h) dans = 1 }
        dans && tolower($1) == "port" { print $2; exit }
    ' "$fichier" 2>/dev/null || true
}

# conseil_ssh FILE VMID ADDRESS: one line of advice when the output of ssh shows a known cause.
conseil_ssh() {
    local f="$1" vmid="$2" adresse="$3"
    [[ -s "$f" ]] || return 0
    if grep -qiE 'port 22: (connection timed out|connection refused|no route)' "$f"; then
        printf '%s\n' "    $(t "conseil : si SSH écoute sur un autre port, mettez VM_PORT_$vmid=PORT dans la configuration, ou un bloc « Host ALIAS » avec « HostName ${adresse%:*} » et « Port PORT » dans ${HOME:-/root}/.ssh/config" \
            "advice: if SSH listens on another port, set VM_PORT_$vmid=PORT in the configuration, or a \"Host ALIAS\" block with \"HostName ${adresse%:*}\" and \"Port PORT\" in ${HOME:-/root}/.ssh/config")"
    elif grep -qiE 'connection timed out|connection refused|no route to host' "$f"; then
        printf '%s\n' "    $(t "conseil : la machine ne répond pas sur ce port : vérifiez le port SSH (VM_PORT_$vmid), le pare-feu et l'adresse (VM_HOST_$vmid)" \
            "advice: the machine does not answer on this port: check the SSH port (VM_PORT_$vmid), the firewall and the address (VM_HOST_$vmid)")"
    elif grep -qi 'host key verification failed' "$f"; then
        printf '%s\n' "    $(t "conseil : en root, connectez-vous une fois (ssh ${adresse%:*}, même port), vérifiez l'empreinte et acceptez-la" \
            "advice: as root, connect once (ssh ${adresse%:*}, same port), check the fingerprint and accept it")"
    elif grep -qi 'permission denied (publickey' "$f"; then
        printf '%s\n' "    $(t "conseil : la clé publique de root de cet hôte doit être dans authorized_keys de $SSH_USER sur la machine" \
            "advice: the public key of root of this host must be in authorized_keys of $SSH_USER on the machine")"
    elif grep -qiE 'a password is required|sudo: .*password' "$f"; then
        printf '%s\n' "    $(t "conseil : $SSH_USER doit avoir sudo sans mot de passe (system-hardening.sh --update --collect-account $SSH_USER --collect-key FICHIER)" \
            "advice: $SSH_USER needs sudo without a password (system-hardening.sh --update --collect-account $SSH_USER --collect-key FILE)")"
    fi
}

sur_machine() {
    local kind="$1" id="$2" adresse="$3" commande="$4" remote
    case "$kind" in
        hote) bash -c "$commande" ;;
        lxc) pct exec "$id" -- bash -c "$commande" ;;
        vm)
            printf -v remote '%q' "$commande"
            ssh_vm "$adresse" "sudo bash -c $remote" </dev/null ;;
    esac
}

# mises_a_jour_securite: lists the pending security updates of each machine and, on a terminal only, asks before installing them
# (apt-get install --only-upgrade of these packages). Nothing is installed without an answer; no reboot is done.
mises_a_jour_securite() {
    local cible kind id adresse nom pkgs rep journal rc
    printf '%s\n' "$(t "Mises à jour de sécurité :" "Security updates:")" >&2
    for cible in "${SECU_CIBLES[@]}"; do
        read -r kind id adresse nom <<<"$cible" || true
        if [[ "$kind" == "hote" && "$EUID" != 0 ]]; then
            printf '%s\n' "[ATTN] $nom : $(t "lancez en root pour vérifier l'hôte" "run as root to check the host")"
            continue
        fi
        pkgs="$(sur_machine "$kind" "$id" "$adresse" "$COMMANDE_SECURITE" 2>/dev/null | tr '\n' ' ' || true)"
        pkgs="${pkgs%" "}"
        if [[ -z "$pkgs" ]]; then
            printf '%s\n' "[OK] $nom : $(t "aucune mise à jour de sécurité en attente" "no security update pending")"
            continue
        fi
        printf '%s\n' "${C_YELLOW}[ATTN]$C_RESET $nom : $(t "mises à jour de sécurité en attente" "security updates pending") : $pkgs"
        if [[ -z "$INTERACTIF" ]]; then
            printf '%s\n' "$(t "  (pas de terminal : rien n'est installé ; relancez sur un terminal pour répondre)" "  (no terminal: nothing installed; run again on a terminal to answer)")"
            continue
        fi
        read -r -p "$(t "Installer ces mises à jour de sécurité sur $nom ? [o/N] " "Install these security updates on $nom? [y/N] ")" rep </dev/tty || rep=""
        echo >&2
        case "${rep,,}" in
            o|oui|y|yes)
                journal="$RUN/securite-$kind-$id-$nom.txt"
                rc=0
                sur_machine "$kind" "$id" "$adresse" "DEBIAN_FRONTEND=noninteractive apt-get install -y -q --only-upgrade $pkgs" >"$journal" 2>&1 || rc=$?
                if (( rc == 0 )); then
                    printf '%s\n' "[OK] $nom : $(t "mises à jour de sécurité installées (aucun redémarrage)" "security updates installed (no reboot)")"
                else
                    printf '%s\n' "${C_RED}[ATTN]$C_RESET $nom : $(t "échec de l'installation (code $rc, sortie complète : $journal)" "installation failed (code $rc, complete output: $journal)")"
                    grep -E '^(E|W): |dpkg: error|Errors were encountered|unmet dependencies|held broken' "$journal" 2>/dev/null | head -n 5 | sed 's/^/    /' || true
                    grep -qE '^(E|W): |dpkg: error' "$journal" 2>/dev/null || derniere_sortie "$journal"
                    conseil_apt "$journal" "$kind" "$id" "$nom"
                fi ;;
            *)
                printf '%s\n' "$(t "  $nom : non installé" "  $nom: not installed")" ;;
        esac
    done
}

# conseil_apt FILE KIND ID NAME: one line of advice for the known causes of a failed apt-get install.
conseil_apt() {
    local f="$1" kind="$2" id="$3" nom="$4" ou
    case "$kind" in
        lxc) ou="pct enter $id" ;;
        vm) ou="ssh $nom" ;;
        *) ou="$(t "sur l'hôte" "on the host")" ;;
    esac
    if grep -qiE 'could not get lock|unable to acquire the dpkg|is another process using it' "$f"; then
        printf '%s\n' "    $(t "conseil : apt ou dpkg est déjà utilisé (autre mise à jour, unattended-upgrades) : attendez la fin, puis relancez" \
            "advice: apt or dpkg is already in use (other update, unattended-upgrades): wait for its end, then run again")"
    elif grep -qiE 'dpkg was interrupted|dpkg --configure -a|not fully installed or removed|half-configured|post-installation script' "$f"; then
        printf '%s\n' "    $(t "conseil : un paquet est resté à moitié installé : $ou, puis dpkg --audit (quel paquet) et dpkg --configure -a (le message de son erreur)" \
            "advice: a package was left half installed: $ou, then dpkg --audit (which package) and dpkg --configure -a (the message of its error)")"
    elif grep -qiE 'unmet dependencies|held broken|have been kept back' "$f"; then
        printf '%s\n' "    $(t "conseil : dépendances non satisfaites : $ou, puis apt-get -s install --only-upgrade PAQUETS pour voir le paquet bloquant (apt-mark showhold)" \
            "advice: unmet dependencies: $ou, then apt-get -s install --only-upgrade PACKAGES to see the blocking package (apt-mark showhold)")"
    elif grep -qiE 'temporary failure resolving|could not resolve|failed to fetch|connection failed' "$f"; then
        printf '%s\n' "    $(t "conseil : les dépôts ne sont pas joignables (DNS, réseau ou proxy) : $ou, puis apt-get update" \
            "advice: the repositories cannot be reached (DNS, network or proxy): $ou, then apt-get update")"
    elif grep -qiE 'no space left on device' "$f"; then
        printf '%s\n' "    $(t "conseil : disque plein : $ou, puis df -h et apt-get clean" "advice: disk full: $ou, then df -h and apt-get clean")"
    else
        printf '%s\n' "    $(t "conseil : $ou, puis relancez l'installation à la main pour voir le message complet" "advice: $ou, then run the installation by hand to see the complete message")"
    fi
}

# derniere_sortie FILE: the last lines written by a failed command (the reason), indented.
derniere_sortie() {
    [[ -s "$1" ]] || return 0
    tail -n 3 "$1" | sed 's/^/    /'
}

# signaler_aucune NATURE SEEN SELECTED: when no guest is selected, says how many were seen and which expression selects them.
signaler_aucune() {
    local nature="$1" vus="$2" retenus="$3"
    if (( retenus == 0 )); then
        printf '%s\n' "${C_YELLOW}[ATTN]$C_RESET $nature : $(t "aucune machine en marche ne correspond à « $NAME_RE » (machines vues : $vus)" \
            "no running guest matches \"$NAME_RE\" (guests seen: $vus)")"
    fi
}

# LXC_LOG_PATHS_DEFAUT: the logs of our programs, searched in every running LXC container (paths or globs, see LXC_LOG_PATHS).
ODOO_SQL_MAINT_DEFAUT="${NGINX_TOOLS_ODOO_SQL_MAINT:-/opt/rlq-admin-tools/odoo-sql-maint}"
# SQLI_NGINX_LOGS_DEFAUT: nginx access logs searched for the injection requests in every running LXC container.
SQLI_NGINX_LOGS_DEFAUT="${NGINX_TOOLS_SQLI_NGINX_LOGS:-/var/log/nginx/access.log /var/log/nginx/access.log.1}"
# SQLI_MOTIF: regular expression (case insensitive) of an injection request, used by grep in the containers and by the verdict.
SQLI_MOTIF="union(\s|\+|%20|/\*|%2f)+(all(\s|\+|%20)+)?select|information_schema|pg_sleep|sleep\(|benchmark\(|waitfor(\s|\+|%20)+delay|extractvalue\(|updatexml\(|(\s|\+|%20)or(\s|\+|%20)+1(=|%3d)1|%27|'"
# PY_SQLI: the verdict of the three criteria (run with python3 -I, never from a file of the containers). Arguments: window start
# and end (epoch seconds, UTC), odoo-sql-maint output, Odoo journal lines, raw nginx lines, file for the window injection lines,
# injection regular expression. Standard output: key=value lines. Criteria: 1 = a row of the odoo-sql-maint output (xss-persistence:
# users, server actions, scheduled actions, API keys, views) created or modified in the window (Odoo dates are UTC); 2 = SQL errors or
# tracebacks in the Odoo journal of the window; 3 = an injection request of the window answered with a 5xx. VERDICT=REEL when at least
# one criterion holds (rule to be confirmed by the administrator).
read -r -d '' PY_SQLI <<'PY' || true
import datetime
import re
import sys

debut, fin = int(sys.argv[1]), int(sys.argv[2])
sql_fichier, journal_fichier, brut_fichier, sortie_fichier, motif = sys.argv[3:8]
ts_sql = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
erreurs_sql = re.compile(r"psycopg|programmingerror|syntax error|traceback", re.IGNORECASE)
acces = re.compile(r'\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}) ([+-]\d{4})\] "([A-Z]+ [^"]*)" (\d{3})')
injection = re.compile(motif, re.IGNORECASE)

def dans_fenetre(epoque):
    return debut <= epoque <= fin

criteres = [0, 0, 0]
with open(sql_fichier, encoding="utf-8", errors="replace") as f:
    for ligne in f:
        for m in ts_sql.finditer(ligne):
            moment = datetime.datetime(*map(int, m.groups()), tzinfo=datetime.timezone.utc)
            if dans_fenetre(moment.timestamp()):
                criteres[0] += 1
                break
with open(journal_fichier, encoding="utf-8", errors="replace") as f:
    criteres[1] = sum(1 for ligne in f if erreurs_sql.search(ligne))
requetes = 0
with open(brut_fichier, encoding="utf-8", errors="replace") as f, open(sortie_fichier, "w", encoding="utf-8") as out:
    for ligne in f:
        m = acces.search(ligne)
        if not m:
            continue
        moment = datetime.datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S")
        decalage = m.group(2)
        signe = 1 if decalage[0] == "+" else -1
        fuseau = datetime.timezone(signe * datetime.timedelta(hours=int(decalage[1:3]), minutes=int(decalage[3:5])))
        if not dans_fenetre(moment.replace(tzinfo=fuseau).timestamp()):
            continue
        if not injection.search(m.group(3)):
            continue
        requetes += 1
        out.write(ligne)
        if m.group(4).startswith("5"):
            criteres[2] += 1
print("REQUETES=%d" % requetes)
for i, valeur in enumerate(criteres, 1):
    print("CRITERE%d=%d" % (i, valeur))
print("VERDICT=" + ("REEL" if any(criteres) else "AUCUN"))
PY
LXC_LOG_PATHS_DEFAUT="${NGINX_TOOLS_LXC_LOG_PATHS:-/var/log/app-log-live /var/log/web-monitor /var/log/odoo-update-module /var/log/sync-crowdsec-blocklist.log* /var/log/nginx-log-audit-expiry.log* /var/lib/app-log-live /var/lib/web-monitor /var/lib/nginx-tools /var/lib/host-perf-audit /var/lib/odoo-backup /var/lib/odoo-warmup /var/lib/sync-crowdsec-blocklist /var/lib/sqli-investigate /var/lib/collect-all-advise}"

# SYSTEMD_DIR: unit files of the timer (/etc/systemd/system; NGINX_TOOLS_SYSTEMD_DIR for the tests).
# installer_minuteur: a service that runs this script (its configuration is read from /etc/default) and a timer that starts
# it every day at TIMER_TIME, enabled now. Root only.
installer_minuteur() {
    local heure="${CFG[TIMER_TIME]:-03:30}" script
    if (( EUID != 0 )); then
        echo "[ATTN] $(t "le minuteur s'installe en root : sudo $SCRIPT_FILE --install-timer" \
            "the timer is installed as root: sudo $SCRIPT_FILE --install-timer")" >&2
        return 1
    fi
    if ! [[ "$heure" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
        echo "[ATTN] $(t "TIMER_TIME refusé (HH:MM attendu) : $heure" "TIMER_TIME refused (HH:MM expected): $heure")" >&2
        return 1
    fi
    script="$(readlink -f "${BASH_SOURCE[0]}")"
    mkdir -p "$SYSTEMD_DIR"
    cat > "$SYSTEMD_DIR/$SCRIPT_NAME.service" <<UNIT
[Unit]
Description=collect-all-advise: --advise reports of the BigBlueButton and Odoo guests (configuration: /etc/default/$SCRIPT_NAME.conf)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
Environment=COLLECT_NO_PROMPT=1
ExecStart=$script
TimeoutStartSec=infinity
UNIT
    cat > "$SYSTEMD_DIR/$SCRIPT_NAME.timer" <<UNIT
[Unit]
Description=collect-all-advise every day at $heure

[Timer]
OnCalendar=*-*-* $heure:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT
    if command -v systemctl >/dev/null 2>&1; then
        if ! { systemctl daemon-reload && systemctl enable --now "$SCRIPT_NAME.timer"; }; then
            echo "[ATTN] $(t "systemctl n'a pas activé le minuteur (voir : systemctl status $SCRIPT_NAME.timer)" \
                "systemctl could not enable the timer (see: systemctl status $SCRIPT_NAME.timer)")" >&2
            return 1
        fi
    fi
    echo "[OK] $(t "minuteur installé : chaque jour à $heure (service $SCRIPT_NAME.service)" \
        "timer installed: every day at $heure (service $SCRIPT_NAME.service)")"
}

# desinstaller_minuteur: disables and removes the service and the timer. Root only.
desinstaller_minuteur() {
    if (( EUID != 0 )); then
        echo "[ATTN] $(t "la suppression du minuteur se fait en root : sudo $SCRIPT_FILE --remove-timer" \
            "the timer is removed as root: sudo $SCRIPT_FILE --remove-timer")" >&2
        return 1
    fi
    if command -v systemctl >/dev/null 2>&1; then
        systemctl disable --now "$SCRIPT_NAME.timer" >/dev/null 2>&1 || true
    fi
    rm -f "$SYSTEMD_DIR/$SCRIPT_NAME.service" "$SYSTEMD_DIR/$SCRIPT_NAME.timer"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload >/dev/null 2>&1 || true
    fi
    echo "[OK] $(t "minuteur supprimé" "timer removed")"
}

collecter_lxc() {
    local vmid="$1" name="$2" dossier="$3" rapport sortie rc=0
    rapport="/tmp/$SCRIPT_NAME-$STAMP-$vmid.md"
    sortie="$dossier/advise-$STAMP.txt"
    mkdir -p "$dossier"
    pct exec "$vmid" -- rm -f "$rapport" >/dev/null 2>&1 || true
    trace "LXC $vmid $name : pct exec $vmid -- $PROGRAM --advise --days $DAYS --export-ai $rapport $ANONYMIZE_OPT --no-follow --no-keys"
    pct exec "$vmid" -- env "APP_LOG_LIVE_LANG=$LANGUE" "$PROGRAM" --advise --days "$DAYS" --export-ai "$rapport" "$ANONYMIZE_OPT" \
           --no-follow --no-keys >"$sortie" 2>&1 </dev/null || rc=$?
    trace "LXC $vmid $name : $(t "code de retour $rc (sortie : $sortie)" "exit code $rc (output: $sortie)")"
    if (( rc == 0 )); then
        pct pull "$vmid" "$rapport" "$dossier/export-ai-$STAMP.md" </dev/null || rc=$?
        trace "LXC $vmid $name : $(t "copie du rapport, code de retour $rc" "report copy, exit code $rc")"
    fi
    if (( rc == 0 )); then
        printf '%s\n' "[OK] LXC $vmid $name -> $dossier/export-ai-$STAMP.md"
        SECU_CIBLES+=("lxc $vmid - $name")
        RAPPORTS_OK=$((RAPPORTS_OK + 1))
    else
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "LXC" "LXC") $vmid $name : $(t "pas de rapport" "no report") ($sortie)"
        derniere_sortie "$sortie"
        RAPPORTS_KO=$((RAPPORTS_KO + 1))
    fi
    pct exec "$vmid" -- rm -f "$rapport" >/dev/null 2>&1 || true
}

# adresse_vm VMID NAME: the address of a virtual machine: VM_HOST_<VMID> of the configuration, otherwise its IPv4 address given
# by the guest agent (qm guest cmd), otherwise the IPv4 address of its name in DNS (getent). Empty if none is found.
# adresse_avec_port VMID NAME ADDRESS: ADDRESS:PORT with VM_PORT_<VMID>; otherwise the alias of ~/.ssh/config whose HostName is
# ADDRESS (so its Port applies); otherwise ADDRESS.
adresse_avec_port() {
    local vmid="$1" name="$2" a="$3" alias port
    if [[ -n "${CFG[VM_PORT_$vmid]:-}" ]]; then
        trace "VM $vmid $name : $(t "port ${CFG[VM_PORT_$vmid]} (VM_PORT_$vmid de la configuration)" "port ${CFG[VM_PORT_$vmid]} (VM_PORT_$vmid of the configuration)")"
        echo "$a:${CFG[VM_PORT_$vmid]}"
        return 0
    fi
    alias="$(alias_ssh "$a")"
    if [[ -n "$alias" ]]; then
        port="$(port_ssh "$alias")"
        trace "VM $vmid $name : $(t "alias $alias de ${HOME:-/root}/.ssh/config pour $a (port ${port:-22})" "alias $alias of ${HOME:-/root}/.ssh/config for $a (port ${port:-22})")"
        echo "$alias"
        return 0
    fi
    echo "$a"
}

adresse_vm() {
    local vmid="$1" name="$2" ip=""
    if [[ -n "${CFG[VM_HOST_$vmid]:-}" ]]; then
        trace "VM $vmid $name : $(t "adresse ${CFG[VM_HOST_$vmid]} (VM_HOST_$vmid de la configuration)" "address ${CFG[VM_HOST_$vmid]} (VM_HOST_$vmid of the configuration)")"
        adresse_avec_port "$vmid" "$name" "${CFG[VM_HOST_$vmid]}"
        return 0
    fi
    if command -v qm >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
        ip="$(qm guest cmd "$vmid" network-get-interfaces 2>/dev/null | python3 -c "$PY_IPV4" 2>/dev/null || true)"
        [[ -z "$ip" ]] || trace "VM $vmid $name : $(t "adresse $ip (agent invité)" "address $ip (guest agent)")"
    fi
    if [[ -z "$ip" ]] && command -v getent >/dev/null 2>&1; then
        ip="$(getent ahostsv4 "$name" 2>/dev/null | awk 'NR == 1 {print $1}' || true)"
        [[ -z "$ip" ]] || trace "VM $vmid $name : $(t "adresse $ip (DNS de $name)" "address $ip (DNS of $name)")"
    fi
    [[ -n "$ip" ]] || { trace "VM $vmid $name : $(t "aucune adresse (ni VM_HOST_$vmid, ni l'agent invité, ni le DNS)" "no address (no VM_HOST_$vmid, no guest agent, no DNS)")"; echo ""; return 0; }
    adresse_avec_port "$vmid" "$name" "$ip"
}

# collecter_vm VMID NAME DIR: same through ssh; the report is read back on standard output.
collecter_vm() {
    local vmid="$1" name="$2" dossier="$3" adresse rapport="/tmp/$SCRIPT_NAME-$STAMP-$1.md"
    local cible sortie rc=0
    adresse="${4-$(adresse_vm "$vmid" "$name")}"
    cible="$SSH_USER@$adresse"
    if [[ -z "$adresse" ]]; then
        printf '%s\n' "${C_YELLOW}[ATTN]$C_RESET $(t "VM" "VM") $vmid $name : $(t "adresse introuvable (ni VM_HOST_$vmid, ni l'agent invité, ni le DNS) : ignorée" "no address found (no VM_HOST_$vmid, no guest agent, no DNS): skipped")"
        RAPPORTS_KO=$((RAPPORTS_KO + 1))
        return 0
    fi
    mkdir -p "$dossier"
    sortie="$dossier/advise-$STAMP.txt"
    trace "VM $vmid $name : ssh $cible \"sudo env APP_LOG_LIVE_LANG=$LANGUE $PROGRAM --advise --days $DAYS --export-ai $rapport $ANONYMIZE_OPT --no-follow --no-keys\""
    ssh_vm "$adresse" "sudo env APP_LOG_LIVE_LANG=$LANGUE $PROGRAM --advise --days $DAYS --export-ai $rapport $ANONYMIZE_OPT --no-follow --no-keys" \
        >"$sortie" 2>&1 </dev/null || rc=$?
    trace "VM $vmid $name : $(t "code de retour $rc (sortie : $sortie)" "exit code $rc (output: $sortie)")"
    if (( rc == 0 )); then
        ssh_vm "$adresse" "sudo cat $rapport" >"$dossier/export-ai-$STAMP.md" </dev/null || rc=$?
        trace "VM $vmid $name : $(t "lecture du rapport, code de retour $rc" "report read, exit code $rc")"
    fi
    if (( rc == 0 )); then
        printf '%s\n' "[OK] VM $vmid $name ($adresse) -> $dossier/export-ai-$STAMP.md"
        SECU_CIBLES+=("vm $vmid $adresse $name")
        RAPPORTS_OK=$((RAPPORTS_OK + 1))
    else
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "VM" "VM") $vmid $name : $(t "pas de rapport" "no report") ($sortie)"
        derniere_sortie "$sortie"
        conseil_ssh "$sortie" "$vmid" "$adresse"
        RAPPORTS_KO=$((RAPPORTS_KO + 1))
    fi
    ssh_vm "$adresse" "sudo rm -f $rapport" >/dev/null 2>&1 </dev/null || true
}

# version_invite KIND VMID ADDRESS: first line of "PROGRAM --version" in a guest (lxc: pct exec; vm: ssh), empty when it cannot be read.
version_invite() {
    local kind="$1" vmid="$2" adresse="$3"
    if [[ "$kind" == "lxc" ]]; then
        pct exec "$vmid" -- "$PROGRAM" --version 2>/dev/null </dev/null | head -1 || true
    else
        [[ -n "$adresse" ]] || return 0
        ssh_vm "$adresse" "$PROGRAM --version" 2>/dev/null </dev/null | head -1 || true
    fi
}

# version_num TEXT: the version number of a --version line ("app-log-live.py v1.210.20261124.212059" -> 1.210.20261124.212059).
version_num() {
    grep -oE '[0-9]+\.[0-9]+(\.[0-9]{8}(\.[0-9]{6})?)?' <<<"$1" | head -1 || true
}

# plus_ancienne A B: true when version A is older than version B (major, minor, date, time compared as numbers).
plus_ancienne() {
    [[ "$1" != "$2" && "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n | head -1)" == "$1" ]]
}

# verifier_suite: before the collection, compares app-log-live.py of each selected guest with the one next to this program (the folder
# of the suite). The guests behind (or whose version cannot be read) are listed; with SYNC=ask and a terminal, the update is offered,
# with SYNC=yes it is done, with SYNC=no nothing is checked. The update is "host-perf-audit.py --guest-sync" (copy of this folder).
verifier_suite() {
    local ref ref_num ligne kind vmid name adresse v vn retard=() ids=() rc=0
    [[ "$SYNC" == "no" ]] && { trace "$(t "mise à jour de la suite : désactivée (SYNC=no)" "update of the suite: disabled (SYNC=no)")"; return 0; }
    if [[ ! -x "$SCRIPT_DIR/app-log-live.py" || ! -x "$SCRIPT_DIR/host-perf-audit.py" ]]; then
        trace "$(t "mise à jour de la suite : app-log-live.py ou host-perf-audit.py absent de $SCRIPT_DIR" "update of the suite: app-log-live.py or host-perf-audit.py missing in $SCRIPT_DIR")"
        return 0
    fi
    ref="$("$SCRIPT_DIR/app-log-live.py" --version 2>/dev/null </dev/null | head -1 || true)"
    ref_num="$(version_num "$ref")"
    [[ -n "$ref_num" ]] || return 0
    printf '%s\n' "$(t "Version de la suite sur cet hôte : app-log-live.py $ref_num ($SCRIPT_DIR)" "Version of the suite on this host: app-log-live.py $ref_num ($SCRIPT_DIR)")"
    for ligne in "${CIBLES[@]}"; do
        read -r kind vmid name adresse <<<"$ligne"
        v="$(version_invite "$kind" "$vmid" "$adresse")"
        vn="$(version_num "$v")"
        if [[ -z "$vn" ]]; then
            retard+=("  ${C_YELLOW}[ATTN]$C_RESET ${kind^^} $vmid $name : $(t "version illisible (programme absent ou machine injoignable)" "version not readable (program missing or guest not reachable)")")
            ids+=("$vmid")
        elif plus_ancienne "$vn" "$ref_num"; then
            retard+=("  ${C_YELLOW}[ATTN]$C_RESET ${kind^^} $vmid $name : $vn ($(t "plus ancienne" "older"))")
            ids+=("$vmid")
        else
            trace "${kind^^} $vmid $name : app-log-live.py $vn ($(t "à jour" "up to date"))"
        fi
    done
    if (( ${#ids[@]} == 0 )); then
        printf '%s\n' "[OK] $(t "la suite est à jour dans les machines choisies" "the suite is up to date in the selected guests")"
        return 0
    fi
    printf '%s\n' "${retard[@]}"
    local liste commande
    liste="$(IFS=,; echo "${ids[*]}")"
    commande="$SCRIPT_DIR/host-perf-audit.py --guest-sync --guests $liste --sync-source $SCRIPT_DIR --yes"
    if [[ "$SYNC" == "ask" ]]; then
        if [[ -z "$INTERACTIF" ]]; then
            printf '%s\n' "  $(t "Pas de terminal : la suite n'est pas mise à jour. Pour le faire : " "No terminal: the suite is not updated. To do it: ")$commande"
            return 0
        fi
        local reponse=""
        read -r -p "$(t "Mettre à jour la suite dans ces machines avant la collecte ($liste) ? [o/N] " "Update the suite in these guests before the collection ($liste)? [y/N] ")" reponse </dev/tty || true
        if [[ "$(oui_non "$reponse")" != 1 ]]; then
            printf '%s\n' "  $(t "Collecte avec les versions actuelles des machines." "Collection with the current versions of the guests.")"
            return 0
        fi
    fi
    trace "$commande"
    "$SCRIPT_DIR/host-perf-audit.py" --guest-sync --guests "$liste" --sync-source "$SCRIPT_DIR" --yes --lang "$LANGUE" </dev/null || rc=$?
    if (( rc == 0 )); then
        printf '%s\n' "[OK] $(t "suite mise à jour dans : $liste" "suite updated in: $liste")"
    else
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "la mise à jour de la suite a échoué (code $rc) : la collecte continue avec les versions actuelles" "the update of the suite failed (code $rc): the collection goes on with the current versions")"
    fi
    return 0
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
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "archive non créée" "archive not created") : $archive"
        return 1
    fi
    printf '%s\n' "[OK] $(t "archive" "archive") : $archive"
}

# archiver_journaux: the raw logs of the host (nginx, Odoo, PostgreSQL in their folders, fail2ban) in
# RACINE_VAR/collect-all-advise/HOST.AAAA-MM-JJ.logs.tar.xz, readable by root only (folder 0750, archive 0640).
# Only the readable files are packed; the number of files is given. The archive is written under a temporary name, then renamed.
archiver_journaux() {
    local hote date_jour dossier base archive tmp liste n=2 nombre
    hote="$(uname -n)"
    date_jour="$(date +%Y-%m-%d)"
    dossier="$RACINE_VAR/$SCRIPT_NAME"
    base="$dossier/$SCRIPT_NAME.$hote.$date_jour.logs"
    archive="$base.tar.xz"
    while [[ -e "$archive" ]]; do
        archive="$base-$n.tar.xz"
        n=$((n + 1))
    done
    mkdir -p "$dossier" && chmod 0750 "$dossier" || { printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "dossier des journaux impossible" "logs folder not created") : $dossier"; return 1; }
    liste="$(mktemp)"
    tmp="$archive.part"
    # paths relative to the parent of RACINE_LOG, so that the archive stores log/nginx/... (no leading slash)
    if ! (cd "$RACINE_LOG/.." && { find "$(basename "$RACINE_LOG")/nginx" "$(basename "$RACINE_LOG")/odoo" "$(basename "$RACINE_LOG")/postgresql" \
            -type f -readable -print0 2>/dev/null; find "$(basename "$RACINE_LOG")" -maxdepth 1 -type f -name 'fail2ban.log*' -readable -print0; } > "$liste") \
        || ! (cd "$RACINE_LOG/.." && tar --null -T "$liste" -cJf "$tmp" 2>/dev/null); then
        rm -f "$liste" "$tmp"
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "archive des journaux non créée" "logs archive not created") : $archive"
        return 1
    fi
    nombre="$(tr -cd '\0' < "$liste" | wc -c)"
    rm -f "$liste"
    chmod 0640 "$tmp" && mv -f "$tmp" "$archive"
    printf '%s\n' "[OK] $(t "journaux bruts" "raw logs") : $archive ($nombre $(t "fichier(s)" "file(s)"))"
}

# collecter_journaux_lxc: the logs of our programs (LXC_LOG_PATHS) in EVERY running LXC container, whatever its name (--name does
# not apply), copied as they are (no anonymisation) into a root-only folder, then packed in one archive:
# RACINE_VAR/collect-all-advise/HOST.AAAA-MM-JJ.lxc-logs.tar.xz (folder 0750, archive 0640). Layout in the archive: VMID-NAME/ then
# the path of the container without its leading slash (for example 101-bbb-lxc1/var/log/app-log-live/...).
collecter_journaux_lxc() {
    local hote date_jour dossier stage base archive tmp n=2 vmid status name chemin cible rc=0
    local trouves=0 erreurs=0 conteneurs=0
    local -a rels
    command -v pct >/dev/null 2>&1 || { trace "$(t "pct introuvable : pas de journaux LXC" "pct not found: no LXC logs")"; return 0; }
    hote="$(uname -n)"
    date_jour="$(date +%Y-%m-%d)"
    dossier="$RACINE_VAR/$SCRIPT_NAME"
    mkdir -p "$dossier" && chmod 0750 "$dossier" || { printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "dossier des journaux impossible" "logs folder not created") : $dossier"; return 1; }
    stage="$(mktemp -d "$dossier/lxc-logs.XXXXXX")" || return 1
    chmod 0700 "$stage"
    while read -r vmid status name <&3; do
        [[ "$status" == "running" ]] || { trace "LXC $vmid $name : $(t "ignoré (état $status)" "skipped (status $status)")"; continue; }
        conteneurs=$((conteneurs + 1))
        rels=()
        # the paths that exist in the container (the globs are expanded there, by its own shell)
        while IFS= read -r chemin; do
            [[ -n "$chemin" ]] && rels+=("${chemin#/}")
        done < <(pct exec "$vmid" -- env "LISTE=$LXC_LOG_PATHS" sh -c 'for p in $LISTE; do for f in $p; do [ -e "$f" ] && printf "%s\n" "$f"; done; done' </dev/null 2>/dev/null || true)
        if (( ${#rels[@]} == 0 )); then
            trace "LXC $vmid $name : $(t "aucun journal de nos programmes" "no log of our programs")"
            continue
        fi
        cible="$stage/$vmid-$name"
        mkdir -p "$cible"
        trace "LXC $vmid $name : pct exec $vmid -- tar -C / -cf - ${rels[*]}"
        rc=0
        pct exec "$vmid" -- tar -C / -cf - --ignore-failed-read "${rels[@]}" </dev/null 2>/dev/null | tar -C "$cible" -xf - || rc=$?
        if (( rc == 0 )); then
            printf '%s\n' "[OK] LXC $vmid $name : ${#rels[@]} $(t "chemin(s) copié(s)" "path(s) copied")"
            trouves=$((trouves + 1))
        else
            printf '%s\n' "${C_RED}[ATTN]$C_RESET LXC $vmid $name : $(t "copie incomplète (code $rc)" "incomplete copy (code $rc)")"
            erreurs=$((erreurs + 1))
        fi
    done 3< <(pct list | awk 'NR > 1 {print $1, $2, $NF}')
    if (( conteneurs == 0 )); then
        printf '%s\n' "$(t "aucun conteneur LXC en marche : pas de journaux LXC" "no running LXC container: no LXC logs")"
        rm -rf "$stage"
        return 0
    fi
    if (( trouves == 0 )); then
        printf '%s\n' "$(t "aucun journal de nos programmes trouvé dans les conteneurs" "no log of our programs found in the containers")"
        rm -rf "$stage"
        if (( erreurs == 0 )); then return 0; fi
        return 1
    fi
    base="$dossier/$hote.$date_jour.lxc-logs"
    archive="$base.tar.xz"
    while [[ -e "$archive" ]]; do
        archive="$base-$n.tar.xz"
        n=$((n + 1))
    done
    tmp="$archive.part"
    if ! tar -C "$stage" -cJf "$tmp" .; then
        rm -f "$tmp"; rm -rf "$stage"
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "archive des journaux LXC non créée" "LXC logs archive not created") : $archive"
        return 1
    fi
    chmod 0640 "$tmp" && mv -f "$tmp" "$archive"
    rm -rf "$stage"
    printf '%s\n' "[OK] $(t "journaux LXC" "LXC logs") : $archive ($trouves $(t "conteneur(s)" "container(s)"))"
    if (( erreurs == 0 )); then return 0; fi
    return 1
}

# valeur_sqli KEY TEXT: the value of KEY=VALUE in the output of PY_SQLI.
valeur_sqli() {
    printf '%s\n' "$2" | sed -n "s/^$1=//p"
}

# collecter_preuves_sqli: evidence of an SQL injection in EVERY running Odoo container (the one that has odoo-sql-maint), for the
# attack window SQLI_DEBUT .. SQLI_FIN (local time): the queries of odoo-sql-maint (SQLI_QUERIES, as the odoo user), the lines of
# the Odoo journal (SQLI_ODOO_UNITS: SQL errors, tracebacks), the injection requests of the nginx access logs (SQLI_NGINX_LOGS),
# then the verdict of the three criteria (PY_SQLI). The raw excerpts are copied as they are (no anonymisation) into one root-only
# archive: RACINE_VAR/collect-all-advise/HOST.AAAA-MM-JJ.sqli-evidence.tar.xz (folder 0750, archive 0640). Each run appends one line
# per container to RACINE_VAR/collect-all-advise/sqli-verdict.txt.
collecter_preuves_sqli() {
    local hote date_jour dossier stage base archive tmp n=2 vmid status name cible rc=0 brut resultat verdict
    local trouves=0 erreurs=0 conteneurs=0 maintenant unite debut_s fin_s requetes c1 c2 c3
    local -a unites=()
    command -v pct >/dev/null 2>&1 || { trace "$(t "pct introuvable : pas de preuves SQL" "pct not found: no SQL evidence")"; return 0; }
    hote="$(uname -n)"
    date_jour="$(date +%Y-%m-%d)"
    maintenant="$(date '+%Y-%m-%d %H:%M')"
    dossier="$RACINE_VAR/$SCRIPT_NAME"
    mkdir -p "$dossier" && chmod 0750 "$dossier" || { printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "dossier des preuves impossible" "evidence folder not created") : $dossier"; return 1; }
    stage="$(mktemp -d "$dossier/sqli-evidence.XXXXXX")" || return 1
    chmod 0700 "$stage"
    debut_s="$(date -d "$SQLI_DEBUT" +%s)"
    fin_s="$(date -d "$SQLI_FIN" +%s)"
    read -r -a unites <<< "$SQLI_ODOO_UNITS"
    printf '%s\n' "$(t "Fenêtre d'attaque (heure locale) : $SQLI_DEBUT -> $SQLI_FIN" "Attack window (local time): $SQLI_DEBUT -> $SQLI_FIN")"
    while read -r vmid status name <&3; do
        [[ "$status" == "running" ]] || { trace "LXC $vmid $name : $(t "ignoré (état $status)" "skipped (status $status)")"; continue; }
        if ! pct exec "$vmid" -- test -x "$ODOO_SQL_MAINT" </dev/null >/dev/null 2>&1; then
            trace "LXC $vmid $name : $(t "pas de $ODOO_SQL_MAINT : pas un conteneur Odoo, ignoré" "no $ODOO_SQL_MAINT: not an Odoo container, skipped")"
            continue
        fi
        conteneurs=$((conteneurs + 1))
        cible="$stage/$vmid-$name"
        mkdir -p "$cible"
        # 1. the queries of odoo-sql-maint, as the odoo user (the exit code is written in the verdict)
        rc=0
        trace "LXC $vmid $name : pct exec $vmid -- sudo -u odoo $ODOO_SQL_MAINT --run $SQLI_QUERIES"
        pct exec "$vmid" -- sudo -u odoo "$ODOO_SQL_MAINT" --run "$SQLI_QUERIES" </dev/null >"$cible/odoo-sql-maint.txt" 2>&1 || rc=$?
        # 2. the Odoo journal: the lines of the window that mention SQL errors or tracebacks
        : > "$cible/odoo-journal.txt"
        for unite in "${unites[@]}"; do
            pct exec "$vmid" -- journalctl -u "$unite" --since "$SQLI_DEBUT" --until "$SQLI_FIN" --no-pager </dev/null 2>/dev/null \
                | grep -iE "psycopg|syntax|traceback|error" | sed "s/^/[$unite] /" >> "$cible/odoo-journal.txt" || true
        done
        # 3. the injection requests of the nginx access logs (raw here, the window is filtered by the verdict)
        brut="$(mktemp "$stage/brut.XXXXXX")"
        pct exec "$vmid" -- env "LISTE=$SQLI_NGINX_LOGS" "MOTIF=$SQLI_MOTIF" sh -c 'for f in $LISTE; do [ -r "$f" ] && grep -aiE -- "$MOTIF" "$f"; done; true' \
            </dev/null >"$brut" 2>/dev/null || true
        # 4. the verdict of the three criteria
        if ! resultat="$(python3 -I -c "$PY_SQLI" "$debut_s" "$fin_s" "$cible/odoo-sql-maint.txt" "$cible/odoo-journal.txt" \
                "$brut" "$cible/nginx-injections.txt" "$SQLI_MOTIF" 2>&1)"; then
            printf '%s\n' "${C_RED}[ATTN]$C_RESET LXC $vmid $name : $(t "analyse des preuves impossible" "evidence analysis failed") : $resultat"
            erreurs=$((erreurs + 1))
            rm -f -- "$brut"
            continue
        fi
        rm -f -- "$brut"
        { printf '%s\n' "# exit code of odoo-sql-maint: $rc" "# window: $SQLI_DEBUT -> $SQLI_FIN (local time)" "$resultat"; } > "$cible/verdict.txt"
        verdict="$(valeur_sqli VERDICT "$resultat")"
        requetes="$(valeur_sqli REQUETES "$resultat")"
        c1="$(valeur_sqli CRITERE1 "$resultat")"
        c2="$(valeur_sqli CRITERE2 "$resultat")"
        c3="$(valeur_sqli CRITERE3 "$resultat")"
        printf '%s %s %s %s requetes=%s critere1=%s critere2=%s critere3=%s sql_exit=%s\n' \
            "$maintenant" "$vmid" "$name" "$verdict" "$requetes" "$c1" "$c2" "$c3" "$rc" >> "$dossier/sqli-verdict.txt"
        trouves=$((trouves + 1))
        if [[ "$verdict" == "REEL" ]]; then
            printf '%s\n' "${C_RED}[ATTN]$C_RESET LXC $vmid $name : $(t "preuves d'une VRAIE ATTAQUE" "evidence of a REAL ATTACK") ($(t "requêtes d'injection" "injection requests") : $requetes ; $(t "critères 1, 2, 3" "criteria 1, 2, 3") : $c1, $c2, $c3)"
        else
            printf '%s\n' "[OK] LXC $vmid $name : $(t "aucune preuve d'attaque" "no evidence of an attack") ($(t "requêtes d'injection" "injection requests") : $requetes)"
        fi
    done 3< <(pct list | awk 'NR > 1 {print $1, $2, $NF}')
    if (( conteneurs == 0 )); then
        printf '%s\n' "$(t "aucun conteneur Odoo en marche : pas de preuves SQL" "no running Odoo container: no SQL evidence")"
        rm -rf "$stage"
        return 0
    fi
    base="$dossier/$hote.$date_jour.sqli-evidence"
    archive="$base.tar.xz"
    while [[ -e "$archive" ]]; do
        archive="$base-$n.tar.xz"
        n=$((n + 1))
    done
    tmp="$archive.part"
    if ! tar -C "$stage" -cJf "$tmp" .; then
        rm -f "$tmp"; rm -rf "$stage"
        printf '%s\n' "${C_RED}[ATTN]$C_RESET $(t "archive des preuves SQL non créée" "SQL evidence archive not created") : $archive"
        return 1
    fi
    chmod 0640 "$tmp" && mv -f "$tmp" "$archive"
    rm -rf "$stage"
    printf '%s\n' "[OK] $(t "preuves SQL" "SQL evidence") : $archive ($trouves $(t "conteneur(s)" "container(s)"))"
    if (( erreurs == 0 )); then return 0; fi
    return 1
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
    printf '%s\n' "$(t "fichier de configuration introuvable ou illisible : " "configuration file not found or unreadable: ")$CONFIG_EXPLICITE" >&2
    exit 2
fi
lire_config
choisir_langue "$@"

DO_CHANGELOG=0; DO_HELP=0; DO_VERSION=0; DO_TIMER=""
DAYS="${CFG[DAYS]:-2}"
DEST="${CFG[DEST]:-$(dest_defaut)}"
NAME_RE="${CFG[NAME_REGEX]:-bbb|odoo}"
PROGRAM="${CFG[PROGRAM]:-/opt/rlq-admin-tools/app-log-live.py}"
SSH_USER="${CFG[SSH_USER]:-root}"
ANONYMIZE_OPT="--anonymize"
if [[ "$(oui_non "${CFG[ANONYMIZE]:-yes}")" == 0 ]]; then ANONYMIZE_OPT="--no-anonymize"; fi
ARCHIVE=1
if [[ "$(oui_non "${CFG[ARCHIVE]:-yes}")" == 0 ]]; then ARCHIVE=0; fi
LOGS_ARCHIVE=1
if [[ "$(oui_non "${CFG[LOGS]:-yes}")" == 0 ]]; then LOGS_ARCHIVE=0; fi
LXC_LOGS=1
if [[ "$(oui_non "${CFG[LXC_LOGS]:-yes}")" == 0 ]]; then LXC_LOGS=0; fi
SQLI_EVIDENCE=1
if [[ "$(oui_non "${CFG[SQLI_EVIDENCE]:-yes}")" == 0 ]]; then SQLI_EVIDENCE=0; fi
SQLI_DEBUT="${CFG[SQLI_FROM]:-}"
SQLI_FIN="${CFG[SQLI_TO]:-}"
SQLI_QUERIES="${CFG[SQLI_QUERIES]:-xss-content,xss-persistence,push-count}"
SQLI_ODOO_UNITS="${CFG[SQLI_ODOO_UNITS]:-erplibre erplibre_erplibre}"
SQLI_NGINX_LOGS="${CFG[SQLI_NGINX_LOGS]:-$SQLI_NGINX_LOGS_DEFAUT}"
ODOO_SQL_MAINT="${CFG[ODOO_SQL_MAINT]:-$ODOO_SQL_MAINT_DEFAUT}"
LXC_LOG_PATHS="${CFG[LXC_LOG_PATHS]:-$LXC_LOG_PATHS_DEFAUT}"
SECURITY=1
if [[ "$(oui_non "${CFG[SECURITY]:-yes}")" == 0 ]]; then SECURITY=0; fi
SYNC="${CFG[SYNC]:-ask}"
case "${SYNC,,}" in
    yes|oui|y|o|1|true|on) SYNC="yes" ;;
    no|non|n|0|false|off) SYNC="no" ;;
    *) SYNC="ask" ;;
esac

while [[ $# -gt 0 ]]; do
    case "$1" in
        --anonymize) ANONYMIZE_OPT="--anonymize"; shift ;;
        --changelog) DO_CHANGELOG=1; shift ;;
        -c|--config) shift 2 ;;
        --config=*) shift ;;
        --days)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --days : nombre de jours attendu" "option --days: number of days expected")" >&2; exit 2; fi
            DAYS="$2"; shift 2 ;;
        --days=*) DAYS="${1#--days=}"; shift ;;
        --dest)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --dest : dossier attendu" "option --dest: folder expected")" >&2; exit 2; fi
            DEST="$2"; shift 2 ;;
        --dest=*) DEST="${1#--dest=}"; shift ;;
        -h|--help) DO_HELP=1; shift ;;
        --install-timer) DO_TIMER="install"; shift ;;
        --lang)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --lang : fr ou en attendu" "option --lang: fr or en expected")" >&2; exit 2; fi
            shift 2 ;;
        --lang=*) shift ;;
        --lxc-logs) LXC_LOGS=1; shift ;;
        --name)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --name : expression attendue" "option --name: expression expected")" >&2; exit 2; fi
            NAME_RE="$2"; shift 2 ;;
        --name=*) NAME_RE="${1#--name=}"; shift ;;
        --no-anonymize) ANONYMIZE_OPT="--no-anonymize"; shift ;;
        --no-archive) ARCHIVE=0; shift ;;
        --no-logs) LOGS_ARCHIVE=0; shift ;;
        --no-lxc-logs) LXC_LOGS=0; shift ;;
        --no-security) SECURITY=0; shift ;;
        --no-sync) SYNC="no"; shift ;;
        --program)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --program : chemin attendu" "option --program: path expected")" >&2; exit 2; fi
            PROGRAM="$2"; shift 2 ;;
        --program=*) PROGRAM="${1#--program=}"; shift ;;
        --remove-timer) DO_TIMER="remove"; shift ;;
        --no-sqli-evidence) SQLI_EVIDENCE=0; shift ;;
        --sqli-evidence) SQLI_EVIDENCE=1; shift ;;
        --sqli-from)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --sqli-from : date attendue" "option --sqli-from: date expected")" >&2; exit 2; fi
            SQLI_DEBUT="$2"; shift 2 ;;
        --sqli-from=*) SQLI_DEBUT="${1#--sqli-from=}"; shift ;;
        --sqli-to)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --sqli-to : date attendue" "option --sqli-to: date expected")" >&2; exit 2; fi
            SQLI_FIN="$2"; shift 2 ;;
        --sqli-to=*) SQLI_FIN="${1#--sqli-to=}"; shift ;;
        --sync) SYNC="yes"; shift ;;
        --ssh-user)
            if [[ $# -lt 2 ]]; then printf '%s\n' "$(t "option --ssh-user : utilisateur attendu" "option --ssh-user: user expected")" >&2; exit 2; fi
            SSH_USER="$2"; shift 2 ;;
        --ssh-user=*) SSH_USER="${1#--ssh-user=}"; shift ;;
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
if [[ "$DO_TIMER" == "install" ]]; then installer_minuteur; exit $?; fi
if [[ "$DO_TIMER" == "remove" ]]; then desinstaller_minuteur; exit $?; fi

if ! valider_jours "$DAYS"; then
    printf '%s\n' "$(t "--days : un nombre de jours de 1 à 366 est attendu (reçu : " "--days: a number of days from 1 to 366 is expected (got: ")$DAYS)" >&2
    exit 2
fi
# SQLI_DEBUT / SQLI_FIN: the attack window, local time (default: the last 24 hours). Checked before any collection.
if [[ -z "$SQLI_DEBUT" ]]; then SQLI_DEBUT="$(date -d '24 hours ago' '+%Y-%m-%d %H:%M:%S')"; fi
if [[ -z "$SQLI_FIN" ]]; then SQLI_FIN="$(date '+%Y-%m-%d %H:%M:%S')"; fi
if ! debut_s="$(date -d "$SQLI_DEBUT" +%s 2>/dev/null)" || ! fin_s="$(date -d "$SQLI_FIN" +%s 2>/dev/null)" || (( debut_s > fin_s )); then
    printf '%s\n' "$(t "--sqli-from / --sqli-to : date AAAA-MM-JJ HH:MM:SS attendue, le début avant la fin (reçu : $SQLI_DEBUT -> $SQLI_FIN)" "--sqli-from / --sqli-to: date YYYY-MM-DD HH:MM:SS expected, start before end (got: $SQLI_DEBUT -> $SQLI_FIN)")" >&2
    exit 2
fi
# --name is a regular expression used only to filter the guest names (never executed): it must compile (bash status 2 otherwise).
# regex_valide: 0 when NAME_RE compiles (the test is only a compile check, never matched against a name).
regex_valide() { [[ "" =~ $NAME_RE ]] 2>/dev/null; }
rc_regex=0; regex_valide || rc_regex=$?
if (( rc_regex == 2 )); then
    printf '%s\n' "$(t "--name : expression refusée : " "--name: expression refused: ")$NAME_RE" >&2
    exit 2
fi

# Configuration read, shown on standard error (the reports are on standard output of the run): each candidate file is
# named with its state (read, absent, created), then the important options on two lines.
cfg_etat() {
    local f="$1"
    if [[ " ${CONFIG_LUES[*]:-} " == *" $f "* ]]; then printf '%s\n' "$(t "lu" "read")"
    elif [[ -n "$CONFIG_CREEE" && "$f" == "$CONFIG_CREEE" ]]; then printf '%s\n' "$(t "créé" "created")"
    else printf '%s\n' "$(t "absent" "absent")"; fi
}
if [[ -n "$CONFIG_EXPLICITE" ]]; then
    cfg_candidats=("$CONFIG_EXPLICITE")
else
    cfg_candidats=("$ETC_DEFAULT/$SCRIPT_NAME.conf" "${HOME:-/root}/.$SCRIPT_NAME.conf")
fi
cfg_resume=""
for cfg_f in "${cfg_candidats[@]}"; do
    cfg_resume+="$cfg_f ($(cfg_etat "$cfg_f")) ; "
done
printf '%s\n' "$(t "Configuration lue / configuration read : " "Configuration lue / configuration read: ")${cfg_resume%" ; "}" >&2
if [[ -n "$CONFIG_CREEE" ]]; then
    printf '%s\n' "$(t "Configuration créée (valeurs par défaut) : " "Configuration created (default values): ")$CONFIG_CREEE" >&2
fi
echo "  $(t "Options : fenêtre $DAYS jour(s) · langue $LANGUE · machines $NAME_RE · dossier $DEST"     "Options: window $DAYS day(s) · language $LANGUE · guests $NAME_RE · folder $DEST")" >&2
echo "  $(t "Archive : $([[ $ARCHIVE == 1 ]] && echo oui || echo non) · sécurité : $([[ $SECURITY == 1 ]] && echo oui || echo non) · minuteur : ${CFG[TIMER]:-no} · anonymisation : $ANONYMIZE_OPT" \
    "Archive: $([[ $ARCHIVE == 1 ]] && echo yes || echo no) · security: $([[ $SECURITY == 1 ]] && echo yes || echo no) · timer: ${CFG[TIMER]:-no} · anonymization: $ANONYMIZE_OPT")" >&2

STAMP="$(date +%Y%m%d-%H%M%S)"
RUN="$DEST/$STAMP"
mkdir -p "$RUN"
RAPPORTS_OK=0
RAPPORTS_KO=0
SECU_CIBLES=("hote - - $(uname -n)")
INTERACTIF=""
if [[ -z "${COLLECT_NO_PROMPT:-}" ]] && { : </dev/tty; } 2>/dev/null; then INTERACTIF=1; fi

# 1.10: the guests are selected first (CIBLES: "lxc VMID NAME -" or "vm VMID NAME ADDRESS"), the suite is checked in them, then collected.
CIBLES=()
# LXC containers (pct list: VMID STATUS LOCK NAME, the name is the last column).
LXC_VUS=0; LXC_RETENUS=0
if command -v pct >/dev/null 2>&1; then
    while read -r vmid status name <&3; do
        LXC_VUS=$((LXC_VUS + 1))
        [[ "$status" == "running" && "$name" =~ $NAME_RE ]] || { trace "LXC $vmid $name : $(t "ignorée (état $status, ou nom hors de $NAME_RE)" "skipped (status $status, or name outside $NAME_RE)")"; continue; }
        LXC_RETENUS=$((LXC_RETENUS + 1))
        CIBLES+=("lxc $vmid $name -")
    done 3< <(pct list | awk 'NR > 1 {print $1, $2, $NF}')
    signaler_aucune "LXC" "$LXC_VUS" "$LXC_RETENUS"
else
    printf '%s\n' "$(t "pct introuvable : pas de conteneur LXC collecté" "pct not found: no LXC container collected")" >&2
fi

# Virtual machines (qm list: VMID NAME STATUS ...).
VM_VUES=0; VM_RETENUES=0
if command -v qm >/dev/null 2>&1; then
    while read -r vmid status name <&3; do
        VM_VUES=$((VM_VUES + 1))
        [[ "$status" == "running" && "$name" =~ $NAME_RE ]] || { trace "VM $vmid $name : $(t "ignorée (état $status, ou nom hors de $NAME_RE)" "skipped (status $status, or name outside $NAME_RE)")"; continue; }
        VM_RETENUES=$((VM_RETENUES + 1))
        CIBLES+=("vm $vmid $name $(adresse_vm "$vmid" "$name" </dev/null)")
    done 3< <(qm list | awk 'NR > 1 {print $1, $3, $2}')
    signaler_aucune "VM" "$VM_VUES" "$VM_RETENUES"
else
    printf '%s\n' "$(t "qm introuvable : pas de machine virtuelle collectée" "qm not found: no virtual machine collected")" >&2
fi

if (( ${#CIBLES[@]} > 0 )); then
    verifier_suite
fi

for ligne in "${CIBLES[@]}"; do
    read -r kind vmid name adresse <<<"$ligne"
    if [[ "$kind" == "lxc" ]]; then
        collecter_lxc "$vmid" "$name" "$RUN/lxc-$vmid-$name"
    else
        collecter_vm "$vmid" "$name" "$RUN/vm-$vmid-$name" "$adresse"
    fi
done

LXC_LOGS_OK=1
if (( LXC_LOGS == 1 )); then
    collecter_journaux_lxc || LXC_LOGS_OK=0
fi

ARCHIVE_OK=1
if (( ARCHIVE == 1 && RAPPORTS_OK > 0 )); then
    archiver || ARCHIVE_OK=0
fi

SQLI_OK=1
if (( SQLI_EVIDENCE == 1 )); then
    collecter_preuves_sqli || SQLI_OK=0
fi

LOGS_OK=1
if (( LOGS_ARCHIVE == 1 )); then
    archiver_journaux || LOGS_OK=0
fi

printf '%s\n' "$(t "Rapports collectés : $RAPPORTS_OK · en échec : $RAPPORTS_KO · dossier : $RUN" \
    "Reports collected: $RAPPORTS_OK · failed: $RAPPORTS_KO · folder: $RUN")"

if (( SECURITY == 1 )); then
    mises_a_jour_securite
fi

if (( RAPPORTS_KO > 0 || ARCHIVE_OK == 0 || LOGS_OK == 0 || LXC_LOGS_OK == 0 || SQLI_OK == 0 )); then exit 1; fi
exit 0
