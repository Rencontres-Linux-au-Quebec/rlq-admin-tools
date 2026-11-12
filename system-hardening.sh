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
# system-hardening.sh - hardening of the operating system itself, wherever it runs: Proxmox VE host (Debian 13), virtual
# machine (Ubuntu 20.04 and later, Debian 12 and later) or LXC container (Debian 12 and later).
#
#   1. unattended-upgrades: SECURITY updates only, applied every day; no automatic reboot by default.
#   2. auditd: rules tagged rlq-* (sudo, SSH keys, cron, identity files, PAM, sshd, systemd units). Not in an LXC container:
#      the kernel audit belongs to the Proxmox host, where the rules also watch the files of the running containers.
#   3. AIDE: file integrity, with the folders that change all the time excluded (databases, logs, Odoo filestore,
#      BigBlueButton recordings, Proxmox storage), baseline created once, checked every day.
#   4. A daily summary by e-mail (--notify, systemd timer), sent with the mail settings of the suite (apps/_courriel.py):
#      security updates installed, reboot pending, AIDE differences, audit events.
#
# NO DANGER BY DEFAULT: without --update, it ONLY checks and changes nothing. --update installs the packages and writes ONLY files
# of its own (52rlq-unattended-upgrades, 60-rlq-hardening.rules, 99_rlq_exclusions, system-hardening-notify.*), plus ONE line of
# /etc/aide/aide.conf (Checksums, the old value kept in a comment above it): --rollback removes them and restores the line (the packages stay). Must be run as root for --update, --rollback and --baseline-update.
#
# Usage : system-hardening.sh [OPTION]...
#
# Options (sorted alphabetically):
#   --baseline-update      accept the current files as the new AIDE baseline (after legitimate changes: updates, new modules)
#   --changelog        show this program's change log
#   --check            check only (default)
#   -c, --config FILE  this configuration file ONLY (default: /etc/default/system-hardening.conf, then ~/.system-hardening.conf)
#   -h, --help         show this help and exit
#   --lang LANG        fr or en
#   --menu             menu of the usual operations (dialog if installed)
#   --notify           daily summary: printed, and sent by e-mail when something needs attention (used by the timer)
#   --report-err       print at the end an error report to copy and paste (apps/_rapport.sh)
#   --rollback         remove the files written by --update (packages kept)
#   --update           apply: packages, configuration, audit rules, AIDE baseline, daily timer
#   -v, --verbose      print each system command
#   --version          show the version and exit
#
# Configuration (/etc/default/system-hardening.conf, then ~/.system-hardening.conf if it exists; the last one wins):
#   LANGUAGE, VERBOSE, UNATTENDED_UPGRADES, AUTOMATIC_REBOOT, AUTOMATIC_REBOOT_TIME, AUDITD, AUDIT_WATCH_CONTAINERS,
#   AIDE, AIDE_CHECKSUMS, AIDE_EXCLUDE, NOTIFY, NOTIFY_TIME, NOTIFY_ALWAYS (see doc/en/system-hardening.conf.example)
#
# ========================================================================================================================

set -euo pipefail
# PATH completed: under cron or a systemd timer, PATH may lack /usr/sbin and /sbin (auditctl, augenrules, aide). Added AT THE END.
for _d in /usr/local/sbin /usr/sbin /sbin; do [[ -n "${NGINX_TOOLS_TESTS:-}" ]] && break; case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac; done
# (During the test suite, NGINX_TOOLS_TESTS disables this addition: the real system commands stay out of reach.)
export PATH

readonly SCRIPT_VERSION="1.2.20261112.082236"
readonly SCRIPT_NAME="system-hardening"
SCRIPT_FILE="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_FILE
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"

# System paths (an environment variable replaces each one: tests, unusual layouts).
OS_RELEASE="${SYSTEM_HARDENING_OS_RELEASE:-/etc/os-release}"
APT_CONF_DIR="${SYSTEM_HARDENING_APT_DIR:-/etc/apt/apt.conf.d}"
AUDIT_RULES_DIR="${SYSTEM_HARDENING_AUDIT_DIR:-/etc/audit/rules.d}"
AIDE_CONF_DIR="${SYSTEM_HARDENING_AIDE_DIR:-/etc/aide/aide.conf.d}"
AIDE_MAIN_CONF="${SYSTEM_HARDENING_AIDE_CONF:-/etc/aide/aide.conf}"
AIDE_DB_DIR="${SYSTEM_HARDENING_AIDE_DB:-/var/lib/aide}"
AIDE_LOG="${SYSTEM_HARDENING_AIDE_LOG:-/var/log/aide/aide.log}"
AIDE_CRON="${SYSTEM_HARDENING_AIDE_CRON:-/etc/cron.daily/aide}"
UU_LOG="${SYSTEM_HARDENING_UU_LOG:-/var/log/unattended-upgrades/unattended-upgrades.log}"
REBOOT_FILE="${SYSTEM_HARDENING_REBOOT_FILE:-/var/run/reboot-required}"
SYSTEMD_DIR="${SYSTEM_HARDENING_SYSTEMD_DIR:-/etc/systemd/system}"
LXC_DIR="${SYSTEM_HARDENING_LXC_DIR:-/var/lib/lxc}"
MODULES_DIR="${SYSTEM_HARDENING_MODULES_DIR:-/lib/modules}"
HOME_ROOT="${SYSTEM_HARDENING_HOME_ROOT:-/home}"
ROOT_HOME="${SYSTEM_HARDENING_ROOT_HOME:-/root}"
MAIL_CONF="${NGINX_TOOLS_MAIL_CONF:-/etc/default/nginx-tools-mail.conf}"
ODOO_CONF_CANDIDATES="${SYSTEM_HARDENING_ODOO_CONFS:-/etc/odoo/*.conf /opt/odoo/erplibre/config.conf /home/*/git/erplibre/config.conf}"

# Files written by this program (and only these: --rollback removes them).
UU_FILE="$APT_CONF_DIR/52rlq-unattended-upgrades"
AUDIT_FILE="$AUDIT_RULES_DIR/60-rlq-hardening.rules"
AIDE_FILE="$AIDE_CONF_DIR/99_rlq_exclusions"
NOTIFY_SERVICE="$SYSTEMD_DIR/system-hardening-notify.service"
NOTIFY_TIMER="$SYSTEMD_DIR/system-hardening-notify.timer"
readonly AUDIT_KEYS="rlq-sudo rlq-sudo-exec rlq-ssh-keys rlq-sshd rlq-cron rlq-identity rlq-pam rlq-preload rlq-systemd rlq-apt"
readonly AUDIT_ALERT_KEYS="rlq-sudo rlq-ssh-keys rlq-sshd rlq-cron rlq-identity rlq-pam rlq-preload"   # changes worth a mail (not each sudo run)

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_GREEN=$'\x1b[1;32m'; C_YELLOW=$'\x1b[1;33m'; C_CYAN=$'\x1b[1;36m'; C_DIM=$'\x1b[2m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_DIM=""; C_RESET=""
fi

# First line of EVERY run, even with --help: the name and version (--version displays it itself).
case " $* " in *" --version "*) ;; *) echo "$SCRIPT_FILE v$SCRIPT_VERSION" ;; esac

if [[ ! -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    echo "ERROR: apps/_i18n.sh is missing next to $SCRIPT_FILE." >&2
    exit 1
fi
# shellcheck source=/dev/null  # library shipped next to the program
. "$SCRIPT_DIR/apps/_i18n.sh"
config_fusion_si_demande system-hardening "$@"      # --config-merge (apps/_i18n.sh -> apps/_config.py): rewrites the configuration from the new default one, then exits
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_rapport.sh"
fi

UI_LANG="fr"
# t FRENCH ENGLISH: the text in the language of this run.
t() {
    if [[ "$UI_LANG" == "en" ]]; then printf '%s' "$2"; else printf '%s' "$1"; fi
}

# choose_language ARGS...: --lang, then SYSTEM_HARDENING_LANG / NGINX_TOOLS_LANG, then LANGUAGE of the configuration, then the locale.
choose_language() {
    local value="" i
    local -a args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do
        case "${args[i]}" in
            --lang) value="${args[i+1]:-}" ;;
            --lang=*) value="${args[i]#--lang=}" ;;
        esac
    done
    [[ -n "$value" ]] || value="${SYSTEM_HARDENING_LANG:-${NGINX_TOOLS_LANG:-}}"
    if [[ -z "$value" || "$value" == auto ]]; then value="${CFG[LANGUAGE]:-auto}"; fi
    if [[ "$value" == auto ]]; then value="${LC_ALL:-${LC_MESSAGES:-${LANG:-fr}}}"; fi
    case "$value" in
        en*|EN*) UI_LANG="en" ;;
        *) UI_LANG="fr" ;;
    esac
    export NGINX_TOOLS_I18N_LANGUE="$UI_LANG"            # apps/_menu.sh follows it
}

# Counters and messages: one line per point, with the tag read by apps/_rapport.sh.
N_OK=0; N_WARN=0; N_FAIL=0
pass() { N_OK=$((N_OK + 1)); echo "  ${C_GREEN}[OK]${C_RESET} $*"; }
warn() { N_WARN=$((N_WARN + 1)); echo "  ${C_YELLOW}[ATTN]${C_RESET} $*"; }
fail() { N_FAIL=$((N_FAIL + 1)); echo "  ${C_RED}$(t "[ÉCHEC]" "[FAIL]")${C_RESET} $*"; }
info() { echo "  ${C_DIM}[INFO]${C_RESET} $*"; }
skip() { echo "  ${C_DIM}[SKIP]${C_RESET} $*"; }
title() { echo; echo "${C_CYAN}$*${C_RESET}"; }

# run COMMAND...: the command, shown first with --verbose.
run() {
    if (( VERBOSE == 1 )); then echo "  + $*" >&2; fi
    "$@"
}

have() { command -v "$1" >/dev/null 2>&1; }
is_root() { (( EUID == 0 )); }

# yes_value VALUE: true for yes, true, 1, on (oui and vrai still read).
yes_value() {
    case "${1,,}" in yes|true|1|on|oui|vrai) return 0 ;; esac
    return 1
}

# ------------------------------------------------------------------------------------------------------------------------
# Help, configuration and change log
# ------------------------------------------------------------------------------------------------------------------------
usage() {
    opt() { printf '  %s%-20s%s %s\n' "$C_CYAN" "$1" "$C_RESET" "$2"; }
    printf '%s\n' "$(t "Usage : system-hardening.sh [OPTION]..." "Usage: system-hardening.sh [OPTION]...")"
    printf '%s\n' "$(t "Durcissement du système : correctifs de sécurité automatiques (unattended-upgrades), audit (auditd), intégrité des fichiers (AIDE)." \
        "System hardening: automatic security updates (unattended-upgrades), audit (auditd), file integrity (AIDE).")"
    printf '%s\n' "$(t "Sans --update, vérifie seulement et ne modifie rien. Hôte Proxmox VE 9, VM Ubuntu 20.04+ ou Debian 12+, conteneur LXC Debian 12+." \
        "Without --update, it only checks and changes nothing. Proxmox VE 9 host, Ubuntu 20.04+ or Debian 12+ VM, Debian 12+ LXC container.")"
    echo
    printf '%s\n' "$(t "Options (par ordre alphabétique) :" "Options (sorted alphabetically):")"
    opt "--baseline-update" "$(t "accepte les fichiers actuels comme nouvelle référence d'AIDE (après des changements voulus)" "accept the current files as the new AIDE baseline (after wanted changes)")"
    opt "--changelog" "$(t "journal des modifications de ce programme" "change log of this program")"
    opt "--check" "$(t "vérification seulement (par défaut)" "check only (default)")"
    opt "-c, --config FILE" "$(t "ce fichier de configuration SEUL (défaut : /etc/default/system-hardening.conf, puis ~/.system-hardening.conf)" \
        "this configuration file ONLY (default: /etc/default/system-hardening.conf, then ~/.system-hardening.conf)")"
    opt "--config-merge" "$(t "réécrit le fichier de configuration d'après la NOUVELLE configuration par défaut en gardant ses valeurs (copie FICHIER.bak-AAAAMMJJ-HHMMSS), puis quitte" \
        "rewrite the configuration file from the NEW default configuration, keeping its values (copy FILE.bak-YYYYMMDD-HHMMSS), then exit")"
    opt "-h, --help" "$(t "affiche cette aide et quitte" "show this help and exit")"
    opt "--lang LANG" "$(t "langue des messages : fr ou en" "language of the messages: fr or en")"
    opt "--menu" "$(t "menu des opérations courantes (dialog s'il est installé)" "menu of the usual operations (dialog if installed)")"
    opt "--notify" "$(t "sommaire quotidien : affiché, et envoyé par courriel s'il y a quelque chose à voir (utilisé par le minuteur)" \
        "daily summary: printed, and sent by e-mail when something needs attention (used by the timer)")"
    opt "--report-err" "$(t "rapport d'erreurs à copier-coller à la fin" "error report to copy and paste at the end")"
    opt "--rollback" "$(t "retire les fichiers écrits par --update (les paquets restent installés)" "remove the files written by --update (packages stay installed)")"
    opt "--update" "$(t "applique : paquets, configuration, règles d'audit, référence d'AIDE, minuteur quotidien (root)" \
        "apply: packages, configuration, audit rules, AIDE baseline, daily timer (root)")"
    opt "-v, --verbose" "$(t "affiche chaque commande système" "print each system command")"
    opt "--version" "$(t "affiche la version et quitte" "show the version and exit")"
    echo
    printf '%s\n' "$(t "Configuration (clés, une par ligne ; modèle : doc/en/system-hardening.conf.example) :" \
        "Configuration (keys, one per line; template: doc/en/system-hardening.conf.example):")"
    local key
    for key in "LANGUAGE=auto" "VERBOSE=no" "UNATTENDED_UPGRADES=yes" "AUTOMATIC_REBOOT=no" "AUTOMATIC_REBOOT_TIME=03:30" "AUDITD=yes" \
               "AUDIT_WATCH_CONTAINERS=yes" "AIDE=yes" "AIDE_CHECKSUMS=sha512" "AIDE_EXCLUDE=" "NOTIFY=yes" "NOTIFY_TIME=07:30" "NOTIFY_ALWAYS=no"; do
        printf '  %s%s%s=%s\n' "$C_CYAN" "${key%%=*}" "$C_RESET" "${key#*=}"
    done
}

# load_settings: values of the configuration file(s), defaults otherwise (the command line has priority, read afterwards).
load_settings() {
    VERBOSE=0; yes_value "${CFG[VERBOSE]:-no}" && VERBOSE=1
    DO_UU=1; DO_AUDIT=1; DO_AIDE=1; DO_NOTIFY_TIMER=1; AUTO_REBOOT=0; NOTIFY_ALWAYS=0; WATCH_CONTAINERS=1
    local key var
    for key in UNATTENDED_UPGRADES:DO_UU AUDITD:DO_AUDIT AIDE:DO_AIDE NOTIFY:DO_NOTIFY_TIMER AUTOMATIC_REBOOT:AUTO_REBOOT \
               NOTIFY_ALWAYS:NOTIFY_ALWAYS AUDIT_WATCH_CONTAINERS:WATCH_CONTAINERS; do
        var="${key#*:}"; key="${key%%:*}"
        [[ -n "${CFG[$key]:-}" ]] || continue
        if yes_value "${CFG[$key]}"; then printf -v "$var" '%s' 1
        else
            case "${CFG[$key],,}" in
                no|false|0|off|non|faux) printf -v "$var" '%s' 0 ;;
                *) CFG_PROBLEMES+=("$key=${CFG[$key]}") ;;
            esac
        fi
    done
    REBOOT_TIME="${CFG[AUTOMATIC_REBOOT_TIME]:-03:30}"
    NOTIFY_TIME="${CFG[NOTIFY_TIME]:-07:30}"
    if [[ ! "$REBOOT_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then CFG_PROBLEMES+=("AUTOMATIC_REBOOT_TIME=$REBOOT_TIME"); REBOOT_TIME="03:30"; fi
    if [[ ! "$NOTIFY_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then CFG_PROBLEMES+=("NOTIFY_TIME=$NOTIFY_TIME"); NOTIFY_TIME="07:30"; fi
    AIDE_EXTRA="${CFG[AIDE_EXCLUDE]:-}"
    AIDE_SUMS="${CFG[AIDE_CHECKSUMS]:-sha512}"                    # 1.1: one strong checksum instead of every one compiled in (Checksums = H)
    if [[ ! "$AIDE_SUMS" =~ ^(keep|[a-z0-9]+(\+[a-z0-9]+)*)$ ]]; then CFG_PROBLEMES+=("AIDE_CHECKSUMS=$AIDE_SUMS"); AIDE_SUMS="sha512"; fi
}

# show_config: the configuration file(s) really read, and a one-line summary of the important options.
show_config() {
    local f read_files=""
    if [[ -n "${CFG_EXPLICITE:-}" ]]; then
        read_files="$CFG_EXPLICITE ($(t "par -c/--config : aucun autre fichier n'est lu" "given by -c/--config: no other file is read"))"
    elif (( ${#CFG_FICHIERS[@]} == 0 )); then
        read_files="$(t "aucun fichier : valeurs par défaut" "no file: default values")"
    else
        for f in "${CFG_FICHIERS[@]}"; do read_files+="${read_files:+, }$f"; done
        if (( ${#CFG_FICHIERS[@]} > 1 )); then read_files+=" ($(t "le dernier l'emporte" "the last one wins"))"; fi
    fi
    echo "$(t "Configuration lue :" "Configuration read:") $read_files"
    echo "  $(t "Options :" "Options:") --lang $UI_LANG · unattended-upgrades $(onoff "$DO_UU") · $(t "redémarrage automatique" "automatic reboot") $(onoff "$AUTO_REBOOT")$( (( AUTO_REBOOT == 1 )) && echo " ($REBOOT_TIME)") · auditd $(onoff "$DO_AUDIT") · AIDE $(onoff "$DO_AIDE") ($AIDE_SUMS)${AIDE_EXTRA:+ (+$AIDE_EXTRA)} · $(t "courriel quotidien" "daily mail") $(onoff "$DO_NOTIFY_TIMER") ($NOTIFY_TIME) · $(t "ligne de commande prioritaire" "command line has priority")"
    for f in ${CFG_PROBLEMES[@]+"${CFG_PROBLEMES[@]}"}; do
        echo "  [ATTN] $(t "valeur de configuration ignorée :" "configuration value ignored:") $f" >&2
    done
}
onoff() { if [[ "$1" == 1 ]]; then t "oui" "yes"; else t "non" "no"; fi; }

# show_changelog: only this program's section of CHANGELOG.md; version numbers in colour when the output is a terminal.
show_changelog() {
    if [[ ! -r "$CHANGELOG_FILE" ]]; then
        echo "CHANGELOG.md: $(t "fichier introuvable" "file not found")" >&2
        return 1
    fi
    awk -v key="$SCRIPT_FILE" '/^## /{inside = ($0 == "## " key); if (inside) print; next} inside' "$CHANGELOG_FILE" 2>/dev/null \
        | sed -E "s/^(### )([0-9]+[.][0-9]+[.][0-9]{8}[.][0-9]{6})/\1${C_CYAN}\2${C_RESET}/" 2>/dev/null || true
}

# ------------------------------------------------------------------------------------------------------------------------
# Where are we? Distribution, version, and kind of machine
# ------------------------------------------------------------------------------------------------------------------------
OS_ID=""; OS_VERSION=""; OS_NAME=""; MACHINE="physical"; SUPPORTED=0
detect_system() {
    local virt="" line key value
    if [[ -r "$OS_RELEASE" ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ "$line" == *=* ]] || continue
            key="${line%%=*}"; value="${line#*=}"; value="${value%\"}"; value="${value#\"}"
            case "$key" in
                ID) OS_ID="$value" ;;
                VERSION_ID) OS_VERSION="$value" ;;
                PRETTY_NAME) OS_NAME="$value" ;;
            esac
        done < "$OS_RELEASE"
    fi
    if have systemd-detect-virt; then
        if systemd-detect-virt --container >/dev/null 2>&1; then
            virt="$(systemd-detect-virt --container 2>/dev/null || true)"
            MACHINE="container:${virt:-unknown}"
        elif virt="$(systemd-detect-virt --vm 2>/dev/null)" && [[ -n "$virt" && "$virt" != none ]]; then
            MACHINE="vm:$virt"
        fi
    fi
    if [[ "$MACHINE" == physical ]] && have pveversion; then MACHINE="proxmox"; fi
    if [[ "$MACHINE" == vm:* ]] && have pveversion; then MACHINE="proxmox"; fi       # Proxmox installed in a test VM
    local major="${OS_VERSION%%.*}"
    case "$OS_ID" in
        debian) [[ "$major" =~ ^[0-9]+$ ]] && (( major >= 12 )) && SUPPORTED=1 ;;
        ubuntu) [[ "$major" =~ ^[0-9]+$ ]] && (( major >= 20 )) && SUPPORTED=1 ;;
    esac
    return 0
}
in_container() { [[ "$MACHINE" == container:* ]]; }
# host_word: "the Proxmox host" for an LXC container, "the host" for another kind of container.
host_word() { if [[ "$MACHINE" == container:lxc ]]; then t "l'hôte Proxmox" "the Proxmox host"; else t "l'hôte" "the host"; fi; }

describe_machine() {
    case "$MACHINE" in
        proxmox) t "hôte Proxmox VE ($(pveversion 2>/dev/null | head -n 1 || true))" "Proxmox VE host ($(pveversion 2>/dev/null | head -n 1 || true))" ;;
        container:lxc) t "conteneur LXC" "LXC container" ;;
        container:*) t "conteneur (${MACHINE#container:})" "container (${MACHINE#container:})" ;;
        vm:*) t "machine virtuelle (${MACHINE#vm:})" "virtual machine (${MACHINE#vm:})" ;;
        *) t "machine physique" "physical machine" ;;
    esac
}

# ------------------------------------------------------------------------------------------------------------------------
# Packages
# ------------------------------------------------------------------------------------------------------------------------
pkg_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"; }

APT_UPDATED=0
pkg_install() {
    local -a missing=() p
    for p in "$@"; do pkg_installed "$p" || missing+=("$p"); done
    (( ${#missing[@]} == 0 )) && return 0
    if (( APT_UPDATED == 0 )); then
        echo "  $(t "Mise à jour de la liste des paquets (apt-get update)..." "Updating the package list (apt-get update)...")"
        run env DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 || warn "$(t "apt-get update a échoué : installation tentée quand même." "apt-get update failed: trying the installation anyway.")"
        APT_UPDATED=1
    fi
    echo "  $(t "Installation de" "Installing") ${missing[*]}..."
    if ! run env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq -o Dpkg::Options::=--force-confold "${missing[@]}" >/dev/null; then
        fail "$(t "échec de l'installation de" "installation failed:") ${missing[*]}"
        return 1
    fi
    pass "$(t "installé :" "installed:") ${missing[*]}"
}

# write_if_changed FILE CONTENT MODE: writes FILE only when its content differs (idempotent); true when the file was written.
write_if_changed() {
    local file="$1" content="$2" mode="${3:-644}" tmp
    if [[ -f "$file" ]] && [[ "$(cat -- "$file")" == "$content" ]]; then return 1; fi
    mkdir -p "$(dirname "$file")"
    tmp="$(mktemp "$(dirname "$file")/.$(basename "$file").XXXXXX")"
    printf '%s\n' "$content" > "$tmp"
    chmod "$mode" "$tmp"
    mv -f -- "$tmp" "$file"
    return 0
}

systemd_running() { [[ -d /run/systemd/system ]] || [[ -n "${NGINX_TOOLS_TESTS:-}" ]]; }

# ------------------------------------------------------------------------------------------------------------------------
# 1. unattended-upgrades: security updates only
# ------------------------------------------------------------------------------------------------------------------------
uu_content() {
    local origins
    # shellcheck disable=SC2016  # ${distro_codename} is expanded by unattended-upgrades, not by bash
    if [[ "$OS_ID" == ubuntu ]]; then
        origins='        "origin=Ubuntu,archive=${distro_codename}-security,label=Ubuntu";
        "origin=UbuntuESMApps,archive=${distro_codename}-apps-security";
        "origin=UbuntuESM,archive=${distro_codename}-infra-security";'
    else
        # shellcheck disable=SC2016  # same: expanded by unattended-upgrades
        origins='        "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
        "origin=Debian,codename=${distro_codename},label=Debian-Security";'
    fi
    cat <<EOF
// Written by system-hardening.sh (rlq-admin-tools) - do not edit: change /etc/default/system-hardening.conf, then system-hardening.sh --update.
// Security updates only; the lists of the distribution file (50unattended-upgrades) are cleared first.
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
#clear Unattended-Upgrade::Origins-Pattern;
#clear Unattended-Upgrade::Allowed-Origins;
Unattended-Upgrade::Origins-Pattern {
$origins
};
Unattended-Upgrade::Automatic-Reboot "$( (( AUTO_REBOOT == 1 )) && echo true || echo false)";
Unattended-Upgrade::Automatic-Reboot-Time "$REBOOT_TIME";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
EOF
}

uu_check() {
    title "1. unattended-upgrades ($(t "correctifs de sécurité" "security updates"))"
    if (( DO_UU == 0 )); then skip "$(t "désactivé (UNATTENDED_UPGRADES=no)" "disabled (UNATTENDED_UPGRADES=no)")"; return 0; fi
    if pkg_installed unattended-upgrades; then
        pass "$(t "paquet unattended-upgrades installé" "package unattended-upgrades installed")"
    else
        fail "$(t "paquet unattended-upgrades absent" "package unattended-upgrades missing") : system-hardening.sh --update"
    fi
    if [[ -f "$UU_FILE" ]] && [[ "$(cat -- "$UU_FILE")" == "$(uu_content)" ]]; then
        pass "$(t "configuration : sécurité seulement, redémarrage automatique" "configuration: security only, automatic reboot") $(onoff "$AUTO_REBOOT") ($UU_FILE)"
    elif [[ -f "$UU_FILE" ]]; then
        warn "$(t "configuration différente de celle attendue (réglages changés) :" "configuration differs from the expected one (settings changed):") $UU_FILE : system-hardening.sh --update"
    else
        fail "$(t "configuration absente :" "configuration missing:") $UU_FILE : system-hardening.sh --update"
    fi
    if have systemctl && systemd_running; then
        if systemctl is-enabled apt-daily-upgrade.timer >/dev/null 2>&1; then
            pass "$(t "minuteur apt-daily-upgrade.timer actif" "timer apt-daily-upgrade.timer enabled")"
        else
            warn "$(t "minuteur apt-daily-upgrade.timer inactif : les mises à jour ne passent pas" "timer apt-daily-upgrade.timer not enabled: updates do not run") : system-hardening.sh --update"
        fi
    fi
    local last
    if [[ -r "$UU_LOG" ]]; then
        last="$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} ' "$UU_LOG" 2>/dev/null | tail -n 1 | cut -c1-16 || true)"
        if [[ -n "$last" ]]; then info "$(t "dernier passage :" "last run:") $last"; fi
    fi
    local pending
    pending="$(pending_security)"
    if [[ -n "$pending" && "$pending" != 0 ]]; then
        warn "$pending $(t "correctif(s) de sécurité en attente (appliqués au prochain passage, ou : unattended-upgrade -v)" "security update(s) pending (applied at the next run, or: unattended-upgrade -v)")"
    elif [[ "$pending" == 0 ]]; then
        pass "$(t "aucun correctif de sécurité en attente" "no security update pending")"
    fi
    reboot_check
}

# pending_security: number of security updates that apt would install now (simulation, no root needed); empty if unknown.
pending_security() {
    have apt-get || return 0
    local out
    out="$(LC_ALL=C apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null)" || return 0
    printf '%s\n' "$out" | grep -E '^Inst ' | grep -ciE 'security' || true
}

# reboot_pending: reason text when a reboot is needed (reboot-required file, or a newer kernel installed than the one running).
reboot_pending() {
    if [[ -f "$REBOOT_FILE" ]]; then
        local pkgs=""
        [[ -r "$REBOOT_FILE.pkgs" ]] && pkgs="$(sort -u "$REBOOT_FILE.pkgs" | tr '\n' ' ' | sed 's/ *$//')"
        echo "$REBOOT_FILE${pkgs:+ ($pkgs)}"
        return 0
    fi
    in_container && return 0                                  # no kernel of its own
    local running newest
    running="$(uname -r)"
    [[ -d "$MODULES_DIR" ]] || return 0
    newest="$(find "$MODULES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -V | tail -n 1 || true)"
    if [[ -n "$newest" && "$newest" != "$running" ]] && [[ "$(printf '%s\n%s\n' "$running" "$newest" | sort -V | tail -n 1)" == "$newest" ]]; then
        echo "$(t "noyau" "kernel") $newest $(t "installé, " "installed, ")$running $(t "en marche" "running")"
    fi
    return 0
}

reboot_check() {
    local why
    why="$(reboot_pending)"
    if [[ -n "$why" ]]; then
        warn "$(t "redémarrage en attente :" "reboot pending:") $why : $(t "à faire au moment qui convient (le service est coupé pendant le redémarrage)" "to do at a convenient time (the service stops during the reboot)")"
    elif in_container; then
        info "$(t "conteneur : le noyau est celui de" "container: the kernel belongs to") $(host_word) ($(t "son redémarrage se gère sur l'hôte" "its reboot is handled on the host"))"
    else
        pass "$(t "aucun redémarrage en attente" "no reboot pending")"
    fi
}

uu_apply() {
    title "1. unattended-upgrades"
    if (( DO_UU == 0 )); then skip "$(t "désactivé (UNATTENDED_UPGRADES=no)" "disabled (UNATTENDED_UPGRADES=no)")"; return 0; fi
    pkg_install unattended-upgrades || return 0
    if write_if_changed "$UU_FILE" "$(uu_content)" 644; then
        pass "$(t "configuration écrite :" "configuration written:") $UU_FILE ($(t "sécurité seulement" "security only"))"
    else
        pass "$(t "configuration déjà à jour :" "configuration already up to date:") $UU_FILE"
    fi
    if have systemctl && systemd_running; then
        run systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || warn "$(t "impossible d'activer les minuteurs apt-daily" "cannot enable the apt-daily timers")"
    fi
    if (( AUTO_REBOOT == 1 )); then
        warn "$(t "redémarrage automatique activé à" "automatic reboot enabled at") $REBOOT_TIME $(t "quand un correctif l'exige (AUTOMATIC_REBOOT=yes)" "when an update needs it (AUTOMATIC_REBOOT=yes)")"
    fi
    if [[ "$MACHINE" == proxmox ]]; then
        info "$(t "Proxmox : seuls les correctifs de sécurité de Debian passent ; les paquets de Proxmox se mettent à jour à la main (apt full-upgrade)" \
            "Proxmox: only the Debian security updates are applied; the Proxmox packages are updated by hand (apt full-upgrade)")"
    fi
}

# ------------------------------------------------------------------------------------------------------------------------
# 2. auditd: rules tagged rlq-*
# ------------------------------------------------------------------------------------------------------------------------
# watch PATH KEY: one watch rule when the path exists (a missing file makes augenrules refuse the whole set).
watch() {
    if [[ -e "$1" ]]; then printf -- '-w %s -p wa -k %s\n' "$1" "$2"; fi
}

# container_roots: root folders of the running LXC containers, seen from the Proxmox host.
container_roots() {
    local d
    [[ -d "$LXC_DIR" ]] || return 0
    for d in "$LXC_DIR"/*/rootfs; do
        [[ -d "$d/etc" ]] && printf '%s\n' "$d"
    done
    return 0
}

audit_content() {
    local h sudo_bin root
    echo "## Written by system-hardening.sh (rlq-admin-tools) - do not edit: system-hardening.sh --update regenerates it."
    echo "## Keys: ausearch -k rlq-sudo (or rlq-ssh-keys, rlq-cron, rlq-identity...) -i"
    echo "## sudo: configuration and runs by real users"
    watch /etc/sudoers rlq-sudo
    watch /etc/sudoers.d rlq-sudo
    for sudo_bin in /usr/bin/sudo /bin/sudo; do
        if [[ -e "$sudo_bin" && ! -L "$sudo_bin" ]]; then
            echo "-a always,exit -F path=$sudo_bin -F perm=x -F auid>=1000 -F auid!=unset -k rlq-sudo-exec"
            break
        fi
    done
    echo "## SSH: authorized keys of root and of each user, server configuration"
    watch "$ROOT_HOME/.ssh" rlq-ssh-keys
    for h in "$HOME_ROOT"/*/.ssh; do watch "$h" rlq-ssh-keys; done
    watch /etc/ssh/sshd_config rlq-sshd
    watch /etc/ssh/sshd_config.d rlq-sshd
    echo "## Scheduled tasks"
    watch /etc/crontab rlq-cron
    for h in /etc/cron.d /etc/cron.hourly /etc/cron.daily /etc/cron.weekly /etc/cron.monthly /var/spool/cron; do watch "$h" rlq-cron; done
    echo "## Accounts, authentication, preloaded libraries, services, package sources"
    for h in /etc/passwd /etc/shadow /etc/group /etc/gshadow; do watch "$h" rlq-identity; done
    watch /etc/pam.d rlq-pam
    watch /etc/ld.so.preload rlq-preload
    watch /etc/systemd/system rlq-systemd
    watch /etc/apt/sources.list rlq-apt
    watch /etc/apt/sources.list.d rlq-apt
    if [[ "$MACHINE" == proxmox ]] && (( WATCH_CONTAINERS == 1 )); then
        echo "## Running LXC containers, seen from the host (rules regenerated by --update: rerun it after a container is restarted)"
        while IFS= read -r root; do
            [[ -n "$root" ]] || continue
            watch "$root/etc/sudoers" rlq-sudo
            watch "$root/etc/sudoers.d" rlq-sudo
            watch "$root/root/.ssh" rlq-ssh-keys
            for h in "$root"/home/*/.ssh; do watch "$h" rlq-ssh-keys; done
            watch "$root/etc/crontab" rlq-cron
            watch "$root/etc/cron.d" rlq-cron
            watch "$root/var/spool/cron" rlq-cron
            watch "$root/etc/passwd" rlq-identity
            watch "$root/etc/shadow" rlq-identity
            watch "$root/etc/ssh/sshd_config" rlq-sshd
        done < <(container_roots)
    fi
}

audit_check() {
    title "2. auditd ($(t "audit des changements sensibles" "audit of sensitive changes"))"
    if (( DO_AUDIT == 0 )); then skip "$(t "désactivé (AUDITD=no)" "disabled (AUDITD=no)")"; return 0; fi
    if in_container; then
        info "$(t "conteneur : l'audit du noyau appartient à" "container: the kernel audit belongs to") $(host_word). $(t "Lancer system-hardening.sh --update sur l'hôte : ses règles surveillent aussi les fichiers sensibles des conteneurs LXC en marche." \
            "Run system-hardening.sh --update on the host: its rules also watch the sensitive files of the running LXC containers.")"
        return 0
    fi
    if pkg_installed auditd; then pass "$(t "paquet auditd installé" "package auditd installed")"
    else fail "$(t "paquet auditd absent" "package auditd missing") : system-hardening.sh --update"; return 0; fi
    if have systemctl && systemd_running; then
        if systemctl is-active auditd >/dev/null 2>&1; then pass "$(t "service auditd actif" "service auditd active")"
        else fail "$(t "service auditd arrêté" "service auditd stopped") : systemctl enable --now auditd"; fi
    fi
    if [[ -f "$AUDIT_FILE" ]] && [[ "$(cat -- "$AUDIT_FILE")" == "$(audit_content)" ]]; then
        pass "$(t "règles rlq-* à jour :" "rlq-* rules up to date:") $AUDIT_FILE ($(grep -c '^-' "$AUDIT_FILE" || true) $(t "règles" "rules"))"
    elif [[ -f "$AUDIT_FILE" ]]; then
        warn "$(t "règles à régénérer (un fichier, un compte ou un conteneur a changé) :" "rules to regenerate (a file, an account or a container changed):") system-hardening.sh --update"
    else
        fail "$(t "règles absentes :" "rules missing:") $AUDIT_FILE : system-hardening.sh --update"
    fi
    if ! is_root; then
        warn "$(t "règles chargées non vérifiées : il faut root (auditctl -l)" "loaded rules not checked: root is needed (auditctl -l)")"
        return 0
    fi
    local loaded
    loaded="$(auditctl -l 2>/dev/null | grep -cE '(-k |key=)rlq-' || true)"        # "-w PATH -p wa -k KEY" and "-a ... -F key=KEY"
    if [[ "${loaded:-0}" -gt 0 ]]; then pass "$loaded $(t "règles rlq-* chargées dans le noyau" "rlq-* rules loaded in the kernel")"
    else warn "$(t "aucune règle rlq-* chargée dans le noyau" "no rlq-* rule loaded in the kernel") : augenrules --load"; fi
    local counts
    counts="$(audit_counts)"
    if [[ -n "$counts" ]]; then info "$(t "événements des dernières 24 h :" "events of the last 24 h:") $counts"; fi
}

# audit_counts [KEYS]: "key N, key N" for the keys that have events since yesterday (ausearch).
audit_counts() {
    local keys="${1:-$AUDIT_KEYS}" k n res=""
    have ausearch || return 0
    for k in $keys; do
        n="$(ausearch -k "$k" --start yesterday 2>/dev/null | grep -c '^----' || true)"
        if [[ "${n:-0}" -gt 0 ]]; then res+="${res:+, }$k $n"; fi
    done
    printf '%s' "$res"
}

audit_apply() {
    title "2. auditd"
    if (( DO_AUDIT == 0 )); then skip "$(t "désactivé (AUDITD=no)" "disabled (AUDITD=no)")"; return 0; fi
    if in_container; then
        skip "$(t "conteneur : l'audit se fait sur" "container: the audit is done on") $(host_word) (system-hardening.sh --update $(t "sur l'hôte" "on the host"))"
        return 0
    fi
    pkg_install auditd || return 0
    if write_if_changed "$AUDIT_FILE" "$(audit_content)" 640; then
        pass "$(t "règles écrites :" "rules written:") $AUDIT_FILE"
    else
        pass "$(t "règles déjà à jour :" "rules already up to date:") $AUDIT_FILE"
    fi
    if have systemctl && systemd_running; then
        run systemctl enable --now auditd >/dev/null 2>&1 || warn "$(t "impossible de démarrer auditd" "cannot start auditd")"
    fi
    if have augenrules; then
        if run augenrules --load >/dev/null 2>&1; then
            pass "$(t "règles chargées (augenrules --load)" "rules loaded (augenrules --load)")"
        else
            fail "$(t "augenrules --load a refusé les règles : voir augenrules --check et" "augenrules --load refused the rules: see augenrules --check and") $AUDIT_FILE"
        fi
    fi
    if [[ "$MACHINE" == proxmox ]] && (( WATCH_CONTAINERS == 1 )); then
        info "$(t "les fichiers des conteneurs en marche sont surveillés depuis l'hôte ; après le redémarrage d'un conteneur, relancer --update" \
            "the files of the running containers are watched from the host; after a container restarts, rerun --update")"
    fi
}

# ------------------------------------------------------------------------------------------------------------------------
# 3. AIDE: file integrity
# ------------------------------------------------------------------------------------------------------------------------
# odoo_data_dirs: data_dir of the Odoo configurations found (filestore and sessions: they change all the time).
odoo_data_dirs() {
    local f
    # shellcheck disable=SC2086  # the candidates are patterns, expanded here on purpose
    for f in $ODOO_CONF_CANDIDATES; do
        [[ -r "$f" ]] || continue
        sed -nE 's/^[[:space:]]*data_dir[[:space:]]*=[[:space:]]*([^[:space:]#]+).*/\1/p' "$f" 2>/dev/null || true
    done | sort -u
}

aide_escape() { printf '%s' "$1" | sed -e 's/[.[\]()*+?{}|^$\\]/\\&/g'; }

aide_content() {
    local p
    echo "# Written by system-hardening.sh (rlq-admin-tools) - do not edit: AIDE_EXCLUDE in /etc/default/system-hardening.conf, then --update."
    echo "# Folders that change all the time: checking them would hide the real changes among thousands of alerts."
    for p in /var/log /var/cache /var/tmp /tmp /var/spool /var/backups /var/lib/apt /var/lib/dpkg /var/lib/systemd /var/lib/postgresql \
             /var/lib/docker /var/lib/containerd /var/bigbluebutton /var/lib/aide /var/lib/fail2ban /var/lib/crowdsec /var/lib/app-log-live /var/lib/web-monitor \
             /var/lib/lxc /var/lib/vz /var/lib/ceph /var/lib/rrdcached /var/lib/pve-cluster /etc/pve /rpool /mnt/pve /run /proc /sys /dev; do
        printf '!%s\n' "$(aide_escape "$p")"
    done
    echo '!/home/[^/]+/\.local/share/Odoo'
    echo '!/opt/odoo/\.local/share/Odoo'
    echo '!/home/[^/]+/\.cache'
    while IFS= read -r p; do
        [[ -n "$p" ]] && printf '!%s\n' "$(aide_escape "$p")"
    done < <(odoo_data_dirs)
    for p in $AIDE_EXTRA; do
        printf '!%s\n' "$(aide_escape "$p")"
    done
}

aide_config_file() {
    if [[ -f "$AIDE_DB_DIR/aide.conf.autogenerated" ]]; then echo "$AIDE_DB_DIR/aide.conf.autogenerated"; else echo "$AIDE_MAIN_CONF"; fi
}

aide_daily_enabled() {
    if have systemctl && systemd_running && systemctl is-enabled dailyaidecheck.timer >/dev/null 2>&1; then return 0; fi
    [[ -x "$AIDE_CRON" ]]
}

# aide_last_result: "date|ok" or "date|differences|summary" from the log of the last daily check; empty if none.
aide_last_result() {
    [[ -r "$AIDE_LOG" ]] || return 0
    local when summary
    when="$(date -r "$AIDE_LOG" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '?')"
    if grep -qE 'found differences' "$AIDE_LOG" 2>/dev/null; then
        summary="$(grep -E '^[[:space:]]*(Added|Removed|Changed) entries' "$AIDE_LOG" 2>/dev/null | tr -s ' \t' ' ' | sed 's/^ //' | tr '\n' ';' | sed 's/;$//; s/;/, /g' || true)"
        echo "$when|differences|$summary"
    elif grep -qE 'Looks okay|NO differences' "$AIDE_LOG" 2>/dev/null; then
        echo "$when|ok"
    fi
    return 0
}

# ------------------------------------------------------------------------------------------------------------------------
# 1.1: the checksums of AIDE. The distribution sets "Checksums = H": EVERY checksum compiled in (md5, sha1, sha256, sha512, rmd160, tiger, whirlpool,
# gost, stribog, crc32...) is computed for every file, several times the processor time of one, for no real gain: SHA-512 alone is enough to detect a
# changed file. The groups of aide.conf (Full, VarFile...) take the value of Checksums when THEY are defined, so the line must be changed where it is
# (a later definition in aide.conf.d would change nothing). The old line is kept in a comment just above, --rollback puts it back.
# ------------------------------------------------------------------------------------------------------------------------
AIDE_SUMS_MARK="# system-hardening.sh: Checksums changed, the line before was:"
aide_checksums_now() {
    [[ -r "$AIDE_MAIN_CONF" ]] || return 0
    sed -nE 's/^[[:space:]]*Checksums[[:space:]]*=[[:space:]]*([^#]*[^#[:space:]])[[:space:]]*(#.*)?$/\1/p' "$AIDE_MAIN_CONF" | tail -n 1
}

# aide_checksums_set: puts "Checksums = $AIDE_SUMS" in aide.conf (old line in a comment above it); true when the file was changed.
aide_checksums_set() {
    local now tmp
    [[ "$AIDE_SUMS" == keep ]] && return 1
    now="$(aide_checksums_now)"
    [[ -z "$now" || "$now" == "$AIDE_SUMS" ]] && return 1
    tmp="$(mktemp "$(dirname "$AIDE_MAIN_CONF")/.aide.conf.XXXXXX")"
    awk -v mark="$AIDE_SUMS_MARK" -v sums="$AIDE_SUMS" '
        /^[[:space:]]*Checksums[[:space:]]*=/ && !done { print mark; print "# " $0; print "Checksums = " sums; done = 1; next }
        { print }' "$AIDE_MAIN_CONF" > "$tmp"
    chmod --reference="$AIDE_MAIN_CONF" "$tmp" 2>/dev/null || chmod 644 "$tmp"
    mv -f -- "$tmp" "$AIDE_MAIN_CONF"
    return 0
}

# aide_checksums_restore: the line kept by aide_checksums_set comes back (--rollback); true when the file was changed.
aide_checksums_restore() {
    local tmp
    if [[ ! -r "$AIDE_MAIN_CONF" ]] || ! grep -qF "$AIDE_SUMS_MARK" "$AIDE_MAIN_CONF"; then return 1; fi
    tmp="$(mktemp "$(dirname "$AIDE_MAIN_CONF")/.aide.conf.XXXXXX")"
    awk -v mark="$AIDE_SUMS_MARK" '
        $0 == mark { restore = 1; next }
        restore == 1 { sub(/^# /, ""); print; restore = 2; next }
        restore == 2 && /^[[:space:]]*Checksums[[:space:]]*=/ { restore = 0; next }
        { print }' "$AIDE_MAIN_CONF" > "$tmp"
    chmod --reference="$AIDE_MAIN_CONF" "$tmp" 2>/dev/null || chmod 644 "$tmp"
    mv -f -- "$tmp" "$AIDE_MAIN_CONF"
    return 0
}

aide_checksums_check() {
    local now
    now="$(aide_checksums_now)"
    if [[ -z "$now" ]]; then
        info "$(t "aucune ligne Checksums dans" "no Checksums line in") $AIDE_MAIN_CONF"
    elif [[ "$AIDE_SUMS" == keep || "$now" == "$AIDE_SUMS" ]]; then
        pass "$(t "condensés d'AIDE :" "AIDE checksums:") Checksums = $now"
    elif [[ "$now" == H ]]; then
        warn "$(t "Checksums = H : TOUS les condensés compilés sont calculés pour chaque fichier (md5, sha1, sha256, sha512, rmd160, tiger, whirlpool, gost...), plusieurs fois plus long qu'un seul, sans gain réel ; --update met Checksums =" "Checksums = H: EVERY checksum compiled in is computed for each file (md5, sha1, sha256, sha512, rmd160, tiger, whirlpool, gost...), several times longer than one, for no real gain; --update sets Checksums =") $AIDE_SUMS"
    else
        warn "$(t "Checksums = $now : --update met Checksums =" "Checksums = $now: --update sets Checksums =") $AIDE_SUMS (AIDE_CHECKSUMS)"
    fi
}

aide_check() {
    title "3. AIDE ($(t "intégrité des fichiers" "file integrity"))"
    if (( DO_AIDE == 0 )); then skip "$(t "désactivé (AIDE=no)" "disabled (AIDE=no)")"; return 0; fi
    if pkg_installed aide; then pass "$(t "paquet aide installé" "package aide installed")"
    else fail "$(t "paquet aide absent" "package aide missing") : system-hardening.sh --update"; return 0; fi
    if [[ -f "$AIDE_FILE" ]] && [[ "$(cat -- "$AIDE_FILE")" == "$(aide_content)" ]]; then
        pass "$(t "exclusions à jour :" "exclusions up to date:") $AIDE_FILE"
    elif [[ -f "$AIDE_FILE" ]]; then
        warn "$(t "exclusions à régénérer (AIDE_EXCLUDE ou configuration d'Odoo changée) :" "exclusions to regenerate (AIDE_EXCLUDE or Odoo configuration changed):") system-hardening.sh --update"
    else
        fail "$(t "exclusions absentes :" "exclusions missing:") $AIDE_FILE : system-hardening.sh --update"
    fi
    aide_checksums_check
    if [[ -f "$AIDE_DB_DIR/aide.db" || -f "$AIDE_DB_DIR/aide.db.gz" ]]; then
        pass "$(t "base de référence présente" "baseline present") ($AIDE_DB_DIR)"
    else
        fail "$(t "aucune base de référence : AIDE ne peut rien comparer" "no baseline: AIDE cannot compare anything") : system-hardening.sh --update"
    fi
    if aide_daily_enabled; then pass "$(t "vérification quotidienne active" "daily check enabled")"
    else warn "$(t "aucune vérification quotidienne (dailyaidecheck.timer ou" "no daily check (dailyaidecheck.timer or") $AIDE_CRON)"; fi
    local result
    result="$(aide_last_result)"
    case "$result" in
        *"|ok") pass "$(t "dernière vérification" "last check") (${result%%|*}) : $(t "aucune différence" "no difference")" ;;
        *"|differences|"*) warn "$(t "dernière vérification" "last check") (${result%%|*}) : $(t "fichiers changés" "files changed") (${result##*|}) : $(t "lire" "read") $AIDE_LOG ; $(t "si les changements sont voulus :" "if the changes are wanted:") system-hardening.sh --baseline-update" ;;
        *) info "$(t "aucun résultat de vérification pour l'instant" "no check result yet") ($AIDE_LOG)" ;;
    esac
}

aide_apply() {
    title "3. AIDE"
    if (( DO_AIDE == 0 )); then skip "$(t "désactivé (AIDE=no)" "disabled (AIDE=no)")"; return 0; fi
    pkg_install aide || return 0
    if write_if_changed "$AIDE_FILE" "$(aide_content)" 644; then
        pass "$(t "exclusions écrites :" "exclusions written:") $AIDE_FILE"
    else
        pass "$(t "exclusions déjà à jour :" "exclusions already up to date:") $AIDE_FILE"
    fi
    local sums_changed=0
    if aide_checksums_set; then
        sums_changed=1
        pass "$(t "condensés d'AIDE : Checksums =" "AIDE checksums: Checksums =") $AIDE_SUMS ($AIDE_MAIN_CONF ; $(t "l'ancienne ligne est gardée en commentaire, --rollback la remet" "the old line is kept in a comment, --rollback puts it back"))"
    fi
    if have update-aide.conf; then run update-aide.conf >/dev/null 2>&1 || warn "update-aide.conf $(t "a échoué" "failed")"; fi
    if have aide && ! run aide --config-check -c "$(aide_config_file)" >/dev/null 2>&1; then
        fail "$(t "configuration d'AIDE refusée : aide --config-check -c" "AIDE configuration refused: aide --config-check -c") $(aide_config_file)"
        return 0
    fi
    if have systemctl && systemd_running && systemctl list-unit-files dailyaidecheck.timer >/dev/null 2>&1; then
        run systemctl enable --now dailyaidecheck.timer >/dev/null 2>&1 || true
    fi
    if [[ -f "$AIDE_DB_DIR/aide.db" || -f "$AIDE_DB_DIR/aide.db.gz" ]] && (( sums_changed == 1 )); then
        # The old baseline holds the old checksums: every file would be reported as changed. It is created again with the new ones.
        warn "$(t "les condensés ont changé : la base de référence est recréée (lire d'abord le dernier rapport d'AIDE :" "the checksums changed: the baseline is created again (read the last AIDE report first:") $AIDE_LOG)"
        for f in "$AIDE_DB_DIR"/aide.db "$AIDE_DB_DIR"/aide.db.gz; do
            if [[ -f "$f" ]]; then mv -f -- "$f" "$f.previous"; fi
        done
    elif [[ -f "$AIDE_DB_DIR/aide.db" || -f "$AIDE_DB_DIR/aide.db.gz" ]]; then
        pass "$(t "base de référence déjà présente (après des changements voulus : --baseline-update)" "baseline already present (after wanted changes: --baseline-update)")"
        return 0
    fi
    echo "  $(t "Création de la base de référence d'AIDE : tous les fichiers sont lus, cela peut prendre de 5 à 30 minutes..." \
        "Creating the AIDE baseline: every file is read, this can take 5 to 30 minutes...")"
    if have aideinit; then
        run aideinit -y -f >/dev/null 2>&1 || true
    elif have aide; then
        run aide --init -c "$(aide_config_file)" >/dev/null 2>&1 || true
        [[ -f "$AIDE_DB_DIR/aide.db.new" ]] && mv -f -- "$AIDE_DB_DIR/aide.db.new" "$AIDE_DB_DIR/aide.db"
    fi
    if [[ -f "$AIDE_DB_DIR/aide.db" || -f "$AIDE_DB_DIR/aide.db.gz" ]]; then
        pass "$(t "base de référence créée" "baseline created") ($AIDE_DB_DIR)"
    else
        fail "$(t "la base de référence n'a pas été créée : lancer aideinit à la main pour voir l'erreur" "the baseline was not created: run aideinit by hand to see the error")"
    fi
}

# aide_accept: the current files become the new baseline (aide --update, then aide.db.new replaces aide.db; the old one is kept as aide.db.previous).
aide_accept() {
    title "AIDE : $(t "nouvelle base de référence" "new baseline")"
    if ! is_root; then fail "$(t "il faut root" "root is needed")"; return 0; fi
    if ! have aide; then fail "$(t "AIDE n'est pas installé : system-hardening.sh --update" "AIDE is not installed: system-hardening.sh --update")"; return 0; fi
    echo "  $(t "Lecture de tous les fichiers (quelques minutes)..." "Reading every file (a few minutes)...")"
    run aide --update -c "$(aide_config_file)" >/dev/null 2>&1 || true            # non-zero when differences were found: expected here
    local new=""
    for new in "$AIDE_DB_DIR/aide.db.new" "$AIDE_DB_DIR/aide.db.new.gz"; do [[ -f "$new" ]] && break; new=""; done
    if [[ -z "$new" ]]; then fail "$(t "aide --update n'a pas produit de nouvelle base" "aide --update produced no new database")"; return 0; fi
    local target="$AIDE_DB_DIR/aide.db${new##*aide.db.new}"
    [[ -f "$target" ]] && cp -p -- "$target" "$target.previous"
    mv -f -- "$new" "$target"
    pass "$(t "nouvelle base de référence en place (l'ancienne :" "new baseline in place (the old one:") $target.previous)"
}

# ------------------------------------------------------------------------------------------------------------------------
# 4. Daily summary by e-mail (--notify) and its timer
# ------------------------------------------------------------------------------------------------------------------------
mail_ready() {
    [[ -r "$MAIL_CONF" ]] || return 1
    grep -qE '^[[:space:]]*MAIL_HOST=.+' "$MAIL_CONF" && grep -qE '^[[:space:]]*MAIL_TO=.+' "$MAIL_CONF"
}

notify_service_content() {
    cat <<EOF
# Written by system-hardening.sh (rlq-admin-tools): daily summary of the system hardening, sent by e-mail when something needs attention.
[Unit]
Description=system-hardening.sh daily summary (security updates, reboot, AIDE, audit)
After=network-online.target

[Service]
Type=oneshot
Environment=NO_COLOR=1
ExecStart=$SCRIPT_DIR/$SCRIPT_FILE --notify
EOF
}

notify_timer_content() {
    cat <<EOF
# Written by system-hardening.sh (rlq-admin-tools)
[Unit]
Description=system-hardening.sh daily summary

[Timer]
OnCalendar=*-*-* $NOTIFY_TIME:00
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF
}

notify_check() {
    title "4. $(t "Sommaire quotidien par courriel" "Daily summary by e-mail")"
    if (( DO_NOTIFY_TIMER == 0 )); then skip "$(t "désactivé (NOTIFY=no)" "disabled (NOTIFY=no)")"; return 0; fi
    if mail_ready; then pass "$(t "courriel de la suite configuré" "mail of the suite configured") ($MAIL_CONF)"
    else warn "$(t "courriel de la suite non configuré : nginx-hardening.sh --update --mail-setup (sinon le sommaire n'est qu'affiché)" "mail of the suite not configured: nginx-hardening.sh --update --mail-setup (otherwise the summary is only printed)")"; fi
    if [[ -f "$NOTIFY_TIMER" ]] && [[ "$(cat -- "$NOTIFY_TIMER")" == "$(notify_timer_content)" ]] && [[ -f "$NOTIFY_SERVICE" ]] && [[ "$(cat -- "$NOTIFY_SERVICE")" == "$(notify_service_content)" ]]; then
        pass "$(t "minuteur system-hardening-notify.timer installé" "timer system-hardening-notify.timer installed") ($NOTIFY_TIME)"
    elif [[ -f "$NOTIFY_TIMER" ]]; then
        warn "$(t "minuteur à mettre à jour (heure ou emplacement du programme changé)" "timer to update (time or program location changed)") : system-hardening.sh --update"
    else
        fail "$(t "minuteur absent" "timer missing") ($NOTIFY_TIMER) : system-hardening.sh --update"
    fi
}

notify_apply() {
    title "4. $(t "Sommaire quotidien par courriel" "Daily summary by e-mail")"
    if (( DO_NOTIFY_TIMER == 0 )); then skip "$(t "désactivé (NOTIFY=no)" "disabled (NOTIFY=no)")"; return 0; fi
    local changed=0
    write_if_changed "$NOTIFY_SERVICE" "$(notify_service_content)" 644 && changed=1
    write_if_changed "$NOTIFY_TIMER" "$(notify_timer_content)" 644 && changed=1
    if have systemctl && systemd_running; then
        if (( changed == 1 )); then run systemctl daemon-reload >/dev/null 2>&1 || true; fi
        if run systemctl enable --now system-hardening-notify.timer >/dev/null 2>&1; then
            pass "$(t "minuteur actif : tous les jours vers" "timer enabled: every day around") $NOTIFY_TIME"
        else
            fail "$(t "impossible d'activer system-hardening-notify.timer" "cannot enable system-hardening-notify.timer")"
        fi
    fi
    mail_ready || warn "$(t "courriel de la suite non configuré : nginx-hardening.sh --update --mail-setup" "mail of the suite not configured: nginx-hardening.sh --update --mail-setup")"
}

# notify: the summary of the last 24 hours; mailed when something needs attention (or always with NOTIFY_ALWAYS=yes).
notify() {
    local body="" attention=0 line why result pending counts alert_counts upgraded
    add() { body+="$1"$'\n'; }
    add "$(hostname) : $OS_NAME : $(describe_machine)"
    add "$(t "Sommaire du" "Summary of") $(date '+%Y-%m-%d %H:%M') ($SCRIPT_FILE $SCRIPT_VERSION)"
    add ""
    if (( DO_UU == 1 )); then
        upgraded="$(uu_upgraded_since_yesterday)"
        if [[ -n "$upgraded" ]]; then add "[INFO] $(t "correctifs de sécurité installés :" "security updates installed:") $upgraded"; attention=1; fi
        pending="$(pending_security)"
        if [[ -n "$pending" && "$pending" != 0 ]]; then add "[ATTN] $pending $(t "correctif(s) de sécurité en attente" "security update(s) pending")"; fi
        if ! pkg_installed unattended-upgrades || [[ ! -f "$UU_FILE" ]]; then add "[FAIL] $(t "mises à jour automatiques non configurées : system-hardening.sh --update" "automatic updates not configured: system-hardening.sh --update")"; attention=1; fi
    fi
    why="$(reboot_pending)"
    if [[ -n "$why" ]]; then add "[ATTN] $(t "redémarrage en attente :" "reboot pending:") $why"; attention=1; fi
    if (( DO_AIDE == 1 )); then
        result="$(aide_last_result)"
        case "$result" in
            *"|differences|"*) add "[ATTN] AIDE (${result%%|*}) : $(t "fichiers changés" "files changed") (${result##*|}) : $AIDE_LOG ; $(t "changements voulus :" "wanted changes:") system-hardening.sh --baseline-update"; attention=1 ;;
            *"|ok") add "[OK] AIDE (${result%%|*}) : $(t "aucune différence" "no difference")" ;;
            *) add "[INFO] AIDE : $(t "aucun résultat de vérification" "no check result")" ;;
        esac
    fi
    if (( DO_AUDIT == 1 )) && ! in_container && is_root; then
        alert_counts="$(audit_counts "$AUDIT_ALERT_KEYS")"
        counts="$(audit_counts)"
        if [[ -n "$alert_counts" ]]; then add "[ATTN] $(t "audit, changements sensibles depuis hier :" "audit, sensitive changes since yesterday:") $alert_counts : ausearch -k CLE -i --start yesterday"; attention=1
        elif [[ -n "$counts" ]]; then add "[INFO] $(t "audit, événements depuis hier :" "audit, events since yesterday:") $counts"; fi
    fi
    if (( attention == 0 )); then add "[OK] $(t "rien à signaler" "nothing to report")"; fi
    printf '%s' "$body"
    if (( attention == 0 && NOTIFY_ALWAYS == 0 )); then return 0; fi
    if ! mail_ready; then
        echo "[ATTN] $(t "courriel non envoyé : courriel de la suite non configuré" "mail not sent: mail of the suite not configured") ($MAIL_CONF)" >&2
        return 0
    fi
    local file
    file="$(mktemp)"
    printf '%s' "$body" > "$file"
    if (( attention == 1 )); then line="$(t "Durcissement" "Hardening") $(hostname) : $(t "à regarder" "to look at")"
    else line="$(t "Durcissement" "Hardening") $(hostname) : $(t "rien à signaler" "nothing to report")"; fi
    if run python3 "$SCRIPT_DIR/apps/_courriel.py" --send "$line" --body-file "$file" >/dev/null 2>&1; then
        echo "[OK] $(t "courriel envoyé" "mail sent")"
    else
        echo "[ATTN] $(t "échec de l'envoi du courriel : python3 apps/_courriel.py --test" "mail failed: python3 apps/_courriel.py --test")" >&2
    fi
    rm -f -- "$file"
}

# uu_upgraded_since_yesterday: packages that unattended-upgrades installed in the last 24 hours (its log).
uu_upgraded_since_yesterday() {
    [[ -r "$UU_LOG" ]] || return 0
    local since
    since="$(date -d '24 hours ago' '+%Y-%m-%d %H:%M' 2>/dev/null || date '+%Y-%m-%d')"
    awk -v since="$since" 'substr($0, 1, 16) >= since && /Packages that (will be|were) upgraded:/ {sub(/.*upgraded: */, ""); print}' "$UU_LOG" 2>/dev/null \
        | tr ' ' '\n' | sed '/^$/d' | sort -u | tr '\n' ' ' | sed 's/ $//' || true
}

# ------------------------------------------------------------------------------------------------------------------------
# Rollback
# ------------------------------------------------------------------------------------------------------------------------
rollback() {
    title "$(t "Retour arrière" "Rollback")"
    if ! is_root; then fail "$(t "il faut root" "root is needed")"; return 0; fi
    local f removed=0
    if have systemctl && systemd_running && [[ -f "$NOTIFY_TIMER" ]]; then run systemctl disable --now system-hardening-notify.timer >/dev/null 2>&1 || true; fi
    if aide_checksums_restore; then pass "$(t "ligne Checksums d'origine remise :" "original Checksums line restored:") $AIDE_MAIN_CONF"; removed=1; fi
    for f in "$UU_FILE" "$AUDIT_FILE" "$AIDE_FILE" "$NOTIFY_TIMER" "$NOTIFY_SERVICE"; do
        if [[ -f "$f" ]]; then rm -f -- "$f"; pass "$(t "retiré :" "removed:") $f"; removed=1; fi
    done
    if (( removed == 0 )); then info "$(t "rien à retirer : aucun fichier de system-hardening.sh" "nothing to remove: no file of system-hardening.sh")"; return 0; fi
    if have systemctl && systemd_running; then run systemctl daemon-reload >/dev/null 2>&1 || true; fi
    if have augenrules && ! in_container; then run augenrules --load >/dev/null 2>&1 || true; fi
    if have update-aide.conf; then run update-aide.conf >/dev/null 2>&1 || true; fi
    info "$(t "les paquets (unattended-upgrades, auditd, aide) et la base d'AIDE restent en place ; les retirer : apt purge aide auditd" \
        "the packages (unattended-upgrades, auditd, aide) and the AIDE database stay; to remove them: apt purge aide auditd")"
}

# ------------------------------------------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------------------------------------------
config_lire "$SCRIPT_NAME" "$@"
if [[ -n "${CFG_EXPLICITE:-}" && ! -r "$CFG_EXPLICITE" ]]; then
    echo "$(t "fichier de configuration introuvable ou illisible : " "configuration file not found or unreadable: ")$CFG_EXPLICITE" >&2
    exit 2
fi
choose_language "$@"
load_settings

if declare -F rapport_si_demande >/dev/null; then
    rapport_si_demande "$SCRIPT_DIR/$SCRIPT_FILE" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi

# Menu --menu: apps/_menu.sh (dialog if installed, otherwise text). Entries: TAG|FR|EN|CONFIRMATION.
if [[ -r "$SCRIPT_DIR/apps/_menu.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_menu.sh"
fi
# shellcheck disable=SC2034  # read by apps/_menu.sh
MENU_ENTREES=(
    "|Vérifier (ne modifie rien)|Check (changes nothing)|0"
    "--update|Appliquer le durcissement|Apply the hardening|1"
    "--notify|Sommaire quotidien maintenant|Daily summary now|0"
    "--baseline-update|Accepter les changements de fichiers (AIDE)|Accept the file changes (AIDE)|1"
    "--rollback|Retirer les fichiers du durcissement|Remove the hardening files|1"
)
if declare -F menu_si_demande >/dev/null; then menu_si_demande "$SCRIPT_DIR/$SCRIPT_FILE" "$@"; fi

MODE="check"; DO_CHANGELOG=0; DO_HELP=0; DO_VERSION=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --baseline-update) MODE="baseline-update"; shift ;;
        --changelog) DO_CHANGELOG=1; shift ;;
        --check) MODE="check"; shift ;;
        -c|--config)
            if [[ $# -lt 2 ]]; then { t "option -c : fichier attendu" "option -c: file expected"; echo; } >&2; exit 2; fi
            shift 2 ;;                                  # read before (apps/_i18n.sh)
        --config=*) shift ;;
        -h|--help) DO_HELP=1; shift ;;
        --lang)
            if [[ $# -lt 2 ]]; then { t "option --lang : fr ou en attendu" "option --lang: fr or en expected"; echo; } >&2; exit 2; fi
            shift 2 ;;                                  # read before (choose_language)
        --lang=*) shift ;;
        --menu) shift ;;                                # handled before (apps/_menu.sh)
        --notify) MODE="notify"; shift ;;
        --report-err) shift ;;                          # read before (apps/_rapport.sh)
        --rollback) MODE="rollback"; shift ;;
        --update) MODE="update"; shift ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --version) DO_VERSION=1; shift ;;
        *)
            echo "$(t "Option inconnue : " "Unknown option: ")$1" >&2
            usage >&2
            exit 2 ;;
    esac
done

if (( DO_VERSION == 1 )); then echo "$SCRIPT_FILE version $SCRIPT_VERSION"; exit 0; fi
if (( DO_HELP == 1 )); then usage; exit 0; fi
if (( DO_CHANGELOG == 1 )); then show_changelog || exit 1; exit 0; fi

detect_system
if [[ "$MODE" == notify ]]; then
    notify
    exit 0
fi
show_config
echo "$(t "Système :" "System:") ${OS_NAME:-$(t "inconnu" "unknown")} · $(describe_machine) · $(t "mode" "mode") $MODE$(is_root || echo " · $(t "sans root" "without root")")"
if (( SUPPORTED == 0 )); then
    echo "  ${C_YELLOW}[ATTN]${C_RESET} $(t "système non prévu (Debian 12 et plus, Ubuntu 20.04 et plus, Proxmox VE 9) : vérification seulement" \
        "system not supported (Debian 12 and later, Ubuntu 20.04 and later, Proxmox VE 9): check only")"
    if [[ "$MODE" != check ]]; then exit 1; fi
fi

case "$MODE" in
    update)
        if ! is_root; then echo "${C_RED}$(t "ERREUR : --update demande root (sudo)." "ERROR: --update needs root (sudo).")${C_RESET}" >&2; exit 1; fi
        uu_apply; audit_apply; aide_apply; notify_apply ;;
    rollback) rollback ;;
    baseline-update) aide_accept ;;
    *) uu_check; audit_check; aide_check; notify_check ;;
esac

echo
if (( N_FAIL > 0 )); then
    echo "$(t "Bilan :" "Result:") ${C_RED}$N_FAIL $(t "échec(s)" "failure(s)")${C_RESET}, $N_WARN $(t "à regarder" "to look at"), $N_OK OK$( [[ "$MODE" == check ]] && echo " : system-hardening.sh --update $(t "pour corriger" "to fix")")"
    exit 1
fi
echo "$(t "Bilan :" "Result:") ${C_GREEN}$(t "aucun échec" "no failure")${C_RESET}, $N_WARN $(t "à regarder" "to look at"), $N_OK OK"
exit 0
