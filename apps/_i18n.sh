# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _i18n.sh - display language (fr / en...) and configuration file of the bash programs (common library, sourced, apps/).
#
#
# Usage, at the very start of the program (after SCRIPT_DIR and SCRIPT_NAME):
#   . "$SCRIPT_DIR/apps/_i18n.sh"; i18n_relancer "$SCRIPT_NAME" NOM_DU_PROGRAMME_LANG "$0" "$@"
#   config_lire "$SCRIPT_NAME" "$@"                         # /etc/default/PROGRAMME.conf PUIS ~/.PROGRAMME.conf ; -c / --config FICHIER : ce fichier SEUL
#   config_defaut MIN_IPS MIN_IPS --min-ips nombre          # file value = default value of the variable (the command line replaces it afterwards)
#   config_afficher                                         # "Configuration lue : ..." and "Options : ..." (program messages)
# Language: --lang, NGINX_TOOLS_LANG, the program's variable, LANGUAGE of the configuration file, LC_ALL / LC_MESSAGES / LANG (see apps/_i18n.py). In French
# (cas courant) rien ne change : aucun processus de plus. Dans une autre langue, apps/_traduire.py lance le programme et traduit sa sortie ligne par ligne.
# shellcheck shell=bash

# pad_cols TEXT WIDTH: TEXT followed by spaces up to WIDTH COLUMNS (1.15). Bash's "printf '%-20s'" counts BYTES: "Premiere" (9 bytes, 8 columns)
# shifted the next column by one step per accented letter. Characters are counted in UTF-8 whatever the caller's locale (cron: LANG=C).
pad_cols() {
    local LC_ALL=C.UTF-8 texte="$1" n
    n=$(( $2 - ${#texte} ))
    (( n > 0 )) || n=0
    printf '%s%*s' "$texte" "$n" ""
}

_I18N_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# i18n_relancer PROGRAM LANGUAGE_VARIABLE SCRIPT ARGUMENTS...: relaunches the program behind the translator if the language is not French. No effect (return 0) if the
# program is already behind the translator, if nothing indicates another language, or if python3 / apps/_traduire.py are missing.
i18n_relancer() {
    _i18n_relancer "$@" || return $?
    ctrl_c_installer                                    # reached only if the program is not relaunched behind the translator (which itself asks no question)
    return 0
}

# _i18n_anonymize_configure PROGRAMME : vrai si un fichier de configuration (commun ou du programme) contient ANONYMIZE=yes ET que la sortie est un terminal (jamais pour un tube ni
# cron: see apps/_anonymiser.py); NGINX_TOOLS_ANONYMIZE=0 prevents it.
_i18n_anonymize_configure() {
    local f valeur
    [[ -t 1 && "${NGINX_TOOLS_ANONYMIZE:-}" != "0" ]] || return 1
    for f in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$1.conf" "${HOME:-/root}/.app-default.conf" "${HOME:-/root}/.$1.conf" \
             "${HOME:-/root}/.app-default.cfg" "${HOME:-/root}/.$1.cfg"; do          # 1.16: legacy personal names too (renamed later by config_lire)
        [[ -r "$f" ]] || continue
        valeur=$(grep -iE '^[[:space:]]*ANONYMIZE[[:space:]]*=' "$f" | tail -n 1 | cut -d= -f2- | tr -d "\"' \t" | tr '[:upper:]' '[:lower:]')
        case "$valeur" in 1|oui|yes|true|on|vrai) return 0 ;; esac
    done
    return 1
}

_i18n_relancer() {
    local programme="$1" variable="$2" script="$3" a signal="" valeur
    shift 3
    [[ -n "${NGINX_TOOLS_I18N:-}" ]] && return 0
    [[ -r "$_I18N_DIR/_traduire.py" ]] && command -v python3 >/dev/null 2>&1 || return 0
    for a in "$@"; do
        case "$a" in --lang|--lang=*|-c|--config|--config=*) signal=1 ;; esac
        case "$a" in --anon|--anony|--anonym|--anonymi|--anonymiz|--anonymize) signal=1 ;; esac          # --anonymize: output filter (apps/_anonymiser.py), set by apps/_traduire.py
    done
    [[ -z "$signal" && -n "${NGINX_TOOLS_ANONYMIZE:-}" && "${NGINX_TOOLS_ANONYMIZE}" != "0" ]] && signal=1
    [[ -z "$signal" ]] && _i18n_anonymize_configure "$programme" && signal=1
    if [[ -z "$signal" ]]; then
        valeur="${NGINX_TOOLS_LANG:-${!variable:-}}"
        case "$valeur" in
            fr|fr_*|fr.*|FR|FR_*) return 0 ;;
            "") ;;
            *) signal=1 ;;
        esac
    fi
    if [[ -z "$signal" ]]; then
        if [[ -f "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$programme.conf" || -f "${HOME:-/root}/.$programme.conf" || -f "${HOME:-/root}/.$programme.cfg" ]]; then signal=1
        elif [[ -n "${LANGUAGE:-}${LC_ALL:-}${LC_MESSAGES:-}${LANG:-}" ]]; then signal=1; fi
    fi
    [[ -n "$signal" ]] || return 0
    exec python3 "$_I18N_DIR/_traduire.py" "$programme" "$variable" -- bash "$script" "$@"
}

# --- Ctrl+C : toujours une confirmation avant de quitter ---------------------------------------------------------------------------------------------------------
# ctrl_c_installer: installs the INT trap "Interrompre le programme ? [o/N]" (program prompt). Yes (o, oui, y, yes), end of file or second Ctrl+C -> stop (code 130) after the function
# named by CTRL_C_NETTOYAGE (if it exists); other answer -> resume. No effect outside a terminal (cron, pipe, tests) and if NGINX_TOOLS_CTRL_C=0.
# Limit: the terminal's Ctrl+C also goes to the running commands (same process group): a short command interrupted during the question stops
# anyway; the script itself resumes after the answer. CTRL_C_NETTOYAGE also serves to stop what the script launched in the background.
CTRL_C_NETTOYAGE=""
CTRL_C_PID=""                       # 1.11: command started by run_interruptible, stopped (TERM) when the interruption is confirmed
_ctrl_c_en_cours=0
ctrl_c_installer() {
    [[ "${NGINX_TOOLS_CTRL_C:-}" == "0" ]] && return 0
    [[ -t 0 && -t 2 ]] || return 0
    trap '_ctrl_c_demande' INT
    return 0
}

_ctrl_c_demande() {
    local rep=""
    if (( _ctrl_c_en_cours )); then _ctrl_c_arret; fi             # second Ctrl+C during the question: confirmed
    _ctrl_c_en_cours=1
    printf '\r\n%s' "Interrompre le programme ? [o/N] " >&2
    # NOT "read -e": during a question already asked by "read -e", the answer was mixed into the current line ("n" + "t" = "nt"). Terminal put back in line mode
    # (echo, kernel erase) for the duration of the answer, then in the previous state (the one the interrupted readline waits for).
    local etat_tty=""
    etat_tty=$(stty -g 2>/dev/null </dev/tty) || etat_tty=""
    [[ -n "$etat_tty" ]] && stty icanon echo echoe isig icrnl 2>/dev/null </dev/tty
    # 1.13: the answer is read in a subshell where Ctrl+C has its normal effect: bash does not rerun an INT trap already running, so a second Ctrl+C
    # during this question (after a Ctrl+C received during a "read -e") stayed without effect ("^C^C^C"). Interrupted subshell or end of file: yes.
    # This shell ignores Ctrl+C for the duration of the question (otherwise bash, receiving the same signal during its trap: "trap_handler: bad signal 2", abort).
    trap '' INT
    rep=$(trap - INT; IFS= read -r r </dev/tty 2>/dev/null || read -r r || exit 130; printf '%s' "$r") || rep=o
    trap '_ctrl_c_demande' INT
    [[ -n "$etat_tty" ]] && stty "$etat_tty" 2>/dev/null </dev/tty
    _ctrl_c_en_cours=0
    case "${rep,,}" in
        o|oui|y|yes) _ctrl_c_arret ;;
    esac
    printf '%s\n' "  Reprise." >&2
}

_ctrl_c_arret() {
    trap '' INT
    if [[ -n "$CTRL_C_PID" ]]; then kill -TERM "$CTRL_C_PID" 2>/dev/null || true; fi
    if [[ -n "$CTRL_C_NETTOYAGE" ]] && declare -F "$CTRL_C_NETTOYAGE" >/dev/null 2>&1; then "$CTRL_C_NETTOYAGE"; fi
    exit 130
}

# run_interruptible CMD... (1.11): runs a LONG command so that Ctrl+C is answered AT ONCE. In the foreground, bash runs the INT trap only when the command ends
# (30 min for a module update, 60 s for a "timeout journalctl"): Ctrl+C seemed dead. Here the command runs in the background (SIGINT ignored for it: the
# terminal's Ctrl+C is not for it) and bash waits with "wait", which the trap interrupts: the question comes immediately; "no" goes back to waiting,
# "yes" stops the command (TERM) then the program. Redirections of the call apply to the command; its code is returned. Not for a command that reads the keyboard.
run_interruptible() {
    local pid rc=0 rc2
    "$@" &
    pid=$!
    CTRL_C_PID=$pid
    while :; do
        wait "$pid" && rc=0 || rc=$?
        kill -0 "$pid" 2>/dev/null || break        # finished (otherwise: wait interrupted by the Ctrl+C question, answer "no")
    done
    if (( rc > 128 )); then                        # ended while the question was asked: its real code, if bash still has it
        wait "$pid" 2>/dev/null && rc2=0 || rc2=$?
        (( rc2 == 127 )) || rc=$rc2
    fi
    CTRL_C_PID=""
    return "$rc"
}

# ctrl_c_child CMD... (1.11): runs a program that owns the terminal (questions, its own Ctrl+C confirmation). The terminal's Ctrl+C reaches both programs (same
# process group): without this, this program asked "Interrupt?" again once the child had answered. Here this program says nothing while the child runs
# (a trap that does nothing, NOT an ignored signal, which the child would inherit). Its code is returned.
ctrl_c_child() {
    local rc=0
    trap ':' INT
    "$@" || rc=$?
    trap - INT
    ctrl_c_installer
    return "$rc"
}

# --- Configuration file: read line by line, NEVER executed (no "source"); keys in capitals, optional quotes, # = comment ----------------------------------------
declare -gA CFG=()
CFG_FICHIERS=()
CFG_EXPLICITE=""
CFG_PROGRAMME=""
CFG_OPTIONS=()
CFG_PROBLEMES=()
CFG_FRANCAIS=()         # values in French (oui, non...) still read; config_afficher asks for them to be written in English

# config_migrer_ancien CHEMIN.conf (1.16) : personal file to READ, in CFG_A_LIRE. The rule is now ~/.PROGRAMME.conf; the legacy name ~/.PROGRAMME.cfg is handled here:
#   * legacy file only: RENAMED to CHEMIN.conf (same owner, rights, content), one notice on stderr; rename impossible: the legacy file is read as is (notice);
#   * both files: CHEMIN.conf is read, the legacy file is IGNORED (never merged nor deleted: its settings may differ), one notice per run.
# NGINX_TOOLS_CONFIG_MIGRER=0: no rename (the legacy file is still read when alone). Same rule and same messages as apps/_config.py (migrer_ancien).
CFG_A_LIRE=""
config_migrer_ancien() {
    local chemin="$1" ancien erreur
    CFG_A_LIRE="$chemin"
    [[ "$chemin" == *.conf ]] || return 0
    ancien="${chemin%.conf}.cfg"
    [[ -e "$ancien" || -L "$ancien" ]] || return 0
    if [[ -e "$chemin" || -L "$chemin" ]]; then
        if _config_signaler "$ancien"; then
            printf '%s\n' "Configuration : ancien fichier $ancien IGNORÉ ($chemin existe et l'emporte) — reporter ses réglages dans $chemin, puis le supprimer" >&2
        fi
        return 0
    fi
    if [[ "${NGINX_TOOLS_CONFIG_MIGRER:-}" == "0" ]]; then CFG_A_LIRE="$ancien"; return 0; fi
    erreur=$(mv -n -- "$ancien" "$chemin" 2>&1) || true
    if [[ -e "$chemin" && ! -e "$ancien" && ! -L "$ancien" ]]; then
        _config_signaler "$ancien" || true
        printf '%s\n' "Configuration : ancien fichier $ancien renommé en $chemin (les fichiers personnels se terminent maintenant par .conf)" >&2
    else
        CFG_A_LIRE="$ancien"
        if _config_signaler "$ancien"; then
            printf '%s\n' "Configuration : impossible de renommer $ancien (${erreur##*: }) — l'ancien fichier est lu tel quel au lieu de $chemin" >&2
        fi
    fi
    return 0
}

# _config_signaler FILE: true (0) the first time a legacy file is reported in this run - variable NGINX_TOOLS_CONFIG_SIGNALES, shared with apps/_config.py and
# inherited by the programs this one starts (one notice per file and per run).
_config_signaler() {
    case ":${NGINX_TOOLS_CONFIG_SIGNALES:-}:" in *":$1:"*) return 1 ;; esac
    export NGINX_TOOLS_CONFIG_SIGNALES="${NGINX_TOOLS_CONFIG_SIGNALES:+$NGINX_TOOLS_CONFIG_SIGNALES:}$1"
    return 0
}

# config_creer_defaut PROGRAM ARGUMENTS...: first start - if NO file of the rule exists, creates the system one (/etc/default/PROGRAM.conf, root) or, without
# rights, the personal file (~/.PROGRAM.conf): copy of doc/en/PROGRAM.conf.example (CFG_DOSSIER_DOC designates the doc/ folder, otherwise the program's) whose options are all in
# comment. Nothing is created with -c/--config, --help / --version / --changelog, if NGINX_TOOLS_CONFIG_CREER=0 or if the template is missing. Path created: CFG_CREE.
CFG_CREE=""
config_creer_defaut() {
    local programme="$1" a ligne modele chemin mode systeme perso; shift
    CFG_CREE=""
    [[ "${NGINX_TOOLS_CONFIG_CREER:-}" == "0" ]] && return 0
    for a in "$@"; do
        case "$a" in -h|--help|--version|--changelog|-c|--config|--config=*) return 0 ;; esac
    done
    config_migrer_ancien "${HOME:-/root}/.app-default.conf"                                                       # 1.16: legacy ~/.NAME.cfg renamed BEFORE any creation
    config_creer_fichier app-default "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "$CFG_A_LIRE"       # le fichier commun d'abord (1.5)
    config_migrer_ancien "${HOME:-/root}/.$programme.conf"
    config_creer_fichier "$programme" "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$programme.conf" "$CFG_A_LIRE"
    return 0
}

# config_creer_fichier NAME SYSTEM PERSONAL: creates the first of the two files that can be, from doc/NAME.conf.example, if none exists; CFG_CREE receives the path created
# (only for the program's file: the "Configuration lue" line does not mention the common file).
config_creer_fichier() {
    local programme="$1" systeme="$2" perso="$3" a ligne modele chemin mode
    if [[ -e "$systeme" || -e "$perso" ]]; then
        for chemin in "$systeme" "$perso"; do [[ -f "$chemin" ]] && config_rafraichir "$programme" "$chemin"; done
        return 0
    fi
    modele="${CFG_DOSSIER_DOC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/doc}/${CFG_LANGUE_MODELE:-en}/$programme.conf.example"
    [[ -r "$modele" ]] || return 0
    for chemin in "$systeme" "$perso"; do
        [[ -d "$(dirname "$chemin")" && -w "$(dirname "$chemin")" ]] || continue
        mode=644; [[ "$chemin" == "$perso" ]] && mode=600
        if ( set -o noclobber
             umask 077
             {
                 while IFS= read -r ligne; do
                     ligne="${ligne//\{DATE\}/$(date +%F\ %H:%M)}"; printf '%s\n' "${ligne//\{NOM\}/$programme}"
                 done < "$(dirname "${BASH_SOURCE[0]}")/config-entete.txt"
                 cat "$modele"
             } > "$chemin" ) 2>/dev/null; then
            chmod "$mode" "$chemin" 2>/dev/null
            if [[ "$programme" != app-default ]]; then CFG_CREE="$chemin"; export NGINX_TOOLS_CONFIG_CREE="$chemin"; fi       # environment variable: the line stays true after i18n_relancer
            return 0
        fi
    done
    return 0
}

# config_rafraichir NAME FILE (1.14): an EXISTING file in which no option is active (all comments = never modified) is rewritten from the template
# doc/NAME.conf.example when the latter has changed; a file with at least one KEY=VALUE line is NEVER touched. Temporary file in the same folder, same rights and
# owner, then rename. NGINX_TOOLS_CONFIG_MAJ_AUTO=0: never. The path is added to NGINX_TOOLS_CONFIG_MAJ ("Configuration lue" line).
config_rafraichir() {
    local programme="$1" chemin="$2" modele temporaire ligne premiere=1
    [[ "${NGINX_TOOLS_CONFIG_MAJ_AUTO:-}" == "0" ]] && return 0
    modele="${CFG_DOSSIER_DOC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/doc}/${CFG_LANGUE_MODELE:-en}/$programme.conf.example"
    [[ -r "$modele" && -r "$chemin" && -w "$chemin" && -w "$(dirname "$chemin")" ]] || return 0
    grep -qE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' "$chemin" && return 0          # an active option: file modified by the user
    tail -c "$(wc -c < "$modele")" "$chemin" 2>/dev/null | cmp -s - "$modele" && return 0       # already at the current template
    temporaire="$(mktemp "$(dirname "$chemin")/.$(basename "$chemin").XXXXXX" 2>/dev/null)" || return 0
    {
        while IFS= read -r ligne; do
            if (( premiere )); then
                ligne="# Fichier mis à jour automatiquement le {DATE} par {NOM} : aucune option n’y était active, il suit le modèle actuel."; premiere=0
            fi
            ligne="${ligne//\{DATE\}/$(date +%F\ %H:%M)}"; printf '%s\n' "${ligne//\{NOM\}/$programme}"
        done < "$(dirname "${BASH_SOURCE[0]}")/config-entete.txt"
        cat "$modele"
    } > "$temporaire" 2>/dev/null || { rm -f "$temporaire"; return 0; }
    chmod --reference="$chemin" "$temporaire" 2>/dev/null
    chown --reference="$chemin" "$temporaire" 2>/dev/null
    if mv -f "$temporaire" "$chemin" 2>/dev/null; then
        export NGINX_TOOLS_CONFIG_MAJ="${NGINX_TOOLS_CONFIG_MAJ:+$NGINX_TOOLS_CONFIG_MAJ:}$chemin"
    else
        rm -f "$temporaire"
    fi
    return 0
}

# config_lire PROGRAM ARGUMENTS...: fills CFG ({KEY: value}) and CFG_FICHIERS; a -c FILE / --config FILE / --config=FILE in the arguments: this file ONLY.
config_lire() {
    local programme="$1" i f c ligne cle valeur; shift
    CFG=(); CFG_FICHIERS=(); CFG_EXPLICITE=""; CFG_PROGRAMME="$programme"; CFG_OPTIONS=(); CFG_PROBLEMES=(); CFG_FRANCAIS=()
    local args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do
        case "${args[i]}" in
            --config=*) CFG_EXPLICITE="${args[i]#--config=}" ;;
            -c|--config) CFG_EXPLICITE="${args[i+1]:-}" ;;
        esac
    done
    local fichiers=() communs=()
    if [[ -n "$CFG_EXPLICITE" ]]; then
        fichiers=("$CFG_EXPLICITE")
    else
        config_creer_defaut "$programme" "${args[@]}"
        # COMMON file for all the programs (app-default.conf): read first, only LANGUAGE, VERBOSE, DEBUG_LEVEL, LOG_KEEP_DAYS and ANONYMIZE; the program's one wins.
        config_migrer_ancien "${HOME:-/root}/.app-default.conf"          # 1.16: ~/.NAME.conf (a legacy ~/.NAME.cfg is renamed; the name to read is in CFG_A_LIRE)
        for f in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "$CFG_A_LIRE"; do
            [[ -f "$f" ]] && communs+=("$f")
        done
        config_migrer_ancien "${HOME:-/root}/.$programme.conf"
        for f in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$programme.conf" "$CFG_A_LIRE"; do
            [[ -f "$f" ]] && fichiers+=("$f")
        done
    fi
    local commun=0
    for f in ${communs[@]+"${communs[@]}"} ${fichiers[@]+"${fichiers[@]}"}; do
        [[ -r "$f" ]] || continue
        CFG_FICHIERS+=("$f")
        commun=0; for c in ${communs[@]+"${communs[@]}"}; do [[ "$c" == "$f" ]] && commun=1; done
        while IFS= read -r ligne || [[ -n "$ligne" ]]; do
            ligne="${ligne#"${ligne%%[![:space:]]*}"}"
            [[ -z "$ligne" || "$ligne" == "#"* || "$ligne" != *=* ]] && continue
            cle="${ligne%%=*}"; valeur="${ligne#*=}"
            cle="${cle//[[:space:]]/}"; cle="${cle^^}"
            if (( commun )); then case "$cle" in LANGUAGE|VERBOSE|DEBUG_LEVEL|LOG_KEEP_DAYS|ANONYMIZE) ;; *) continue ;; esac; fi
            valeur="${valeur#"${valeur%%[![:space:]]*}"}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"
            if [[ "${valeur:0:1}" == '"' || "${valeur:0:1}" == "'" ]] && [[ "${valeur: -1}" == "${valeur:0:1}" && ${#valeur} -ge 2 ]]; then
                valeur="${valeur:1:${#valeur}-2}"
            elif [[ "$valeur" == *" #"* ]]; then
                valeur="${valeur%% #*}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"
            fi
            [[ "$cle" =~ ^[A-Z][A-Z0-9_]*$ ]] && CFG["$cle"]="$valeur"
        done < "$f"
    done
    # DEBUG_LEVEL >= 1 means VERBOSE=yes (unless VERBOSE is written in a file); the level is exported in NGINX_TOOLS_DEBUG_LEVEL.
    if [[ "${CFG[DEBUG_LEVEL]:-}" =~ ^[0-9]+$ ]] && (( CFG[DEBUG_LEVEL] >= 1 )); then
        [[ -n "${CFG[VERBOSE]:-}" ]] || CFG[VERBOSE]="yes"
        export NGINX_TOOLS_DEBUG_LEVEL="${CFG[DEBUG_LEVEL]}"
    fi
    # LOG_KEEP_DAYS (common or program file): days of retention of the logs specific to the programs, exported for those they launch.
    [[ "${CFG[LOG_KEEP_DAYS]:-}" =~ ^[0-9]+$ ]] && export NGINX_TOOLS_LOG_KEEP_DAYS="${CFG[LOG_KEEP_DAYS]}"
    return 0
}

# config_defaut VARIABLE KEY OPTION [TYPE]: if the file defines KEY, VARIABLE takes that value (default value: the command line replaces it afterwards).
# TYPE: text (default), number (positive or zero integer) or boolean (yes/no, true/false, 1/0 -> 1 or 0). Invalid value: reported by config_afficher, ignored.
# English values only: an old oui / non / vrai / faux is still read, and config_afficher asks for it to be written in English.
config_defaut() {
    local variable="$1" cle="$2" option="$3" type="${4:-texte}" valeur="${CFG[$2]:-}"
    [[ -n "$valeur" ]] || return 0
    local anglais=""
    case "${valeur,,}" in
        oui) anglais=yes ;; non) anglais=no ;; vrai) anglais=true ;; faux) anglais=false ;; aucun|aucune) anglais=none ;;
    esac
    [[ -n "$anglais" ]] && CFG_FRANCAIS+=("$cle=$valeur → $anglais")
    case "$type" in
        nombre)
            if [[ "$valeur" =~ ^[0-9]+$ ]]; then printf -v "$variable" '%s' "$valeur"; CFG_OPTIONS+=("$option $valeur")
            else CFG_PROBLEMES+=("$cle=$valeur (entier attendu)"); fi ;;
        booleen)
            case "${valeur,,}" in
                1|true|yes|oui|on|vrai) printf -v "$variable" '%s' 1; CFG_OPTIONS+=("$option yes") ;;
                0|false|no|non|off|faux) printf -v "$variable" '%s' 0; CFG_OPTIONS+=("$option no") ;;
                *) CFG_PROBLEMES+=("$cle=$valeur (yes ou no attendu)") ;;
            esac ;;
        *) printf -v "$variable" '%s' "$valeur"; CFG_OPTIONS+=("$option $valeur") ;;
    esac
    return 0
}

# config_date_modif FILE: LOCAL date and time of last modification (YYYY-MM-DD HH:MM), "?" if unreadable.
config_date_modif() { date -r "$1" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '?'; }

# config_afficher: two starting lines - WHICH configuration file(s) were read, then the important options that result from them (language included).
config_afficher() {
    local lus="" f opts p
    [[ -n "${NGINX_TOOLS_CONFIG_VUE:-}" ]] && return 0      # already displayed by the calling program (or by a previous call): no repetition in the parsed outputs
    export NGINX_TOOLS_CONFIG_VUE=1
    if [[ -n "$CFG_EXPLICITE" ]]; then
        lus="Configuration lue : $(cd "$(dirname "$CFG_EXPLICITE")" 2>/dev/null && pwd)/$(basename "$CFG_EXPLICITE") (modifié le $(config_date_modif "$CFG_EXPLICITE")) (demandé par -c/--config : aucun autre fichier n'est lu)"
    elif (( ${#CFG_FICHIERS[@]} == 0 )); then
        lus="Configuration : aucun fichier (cherchés : ${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$CFG_PROGRAMME.conf, ${HOME:-/root}/.$CFG_PROGRAMME.conf) — valeurs par défaut"
    else
        for f in "${CFG_FICHIERS[@]}"; do lus+="${lus:+, puis }$f (modifié le $(config_date_modif "$f"))"; done
        lus="Configuration lue : $lus"
        (( ${#CFG_FICHIERS[@]} > 1 )) && lus+=" (le dernier l'emporte)"
        for f in "${CFG_FICHIERS[@]}"; do [[ "$f" == "${NGINX_TOOLS_CONFIG_CREE:-}" ]] && CFG_CREE="$f"; done
        [[ -n "$CFG_CREE" ]] && lus+=" (fichier créé à l'instant : toutes les options y sont en commentaire, valeurs par défaut)"
        if [[ -z "$CFG_CREE" && -n "${NGINX_TOOLS_CONFIG_MAJ:-}" ]]; then         # 1.14: files reset to the current template (config_rafraichir)
            local maj="" m
            for f in "${CFG_FICHIERS[@]}"; do
                IFS=: read -ra m <<< "$NGINX_TOOLS_CONFIG_MAJ"
                [[ " ${m[*]} " == *" $f "* ]] && maj+="${maj:+, }$(basename "$f")"
            done
            [[ -n "$maj" ]] && lus+=" ($maj mis à jour à l'instant d'après le nouveau modèle : aucune option n'y était active)"
        fi
    fi
    echo "$lus"
    opts="--lang ${NGINX_TOOLS_I18N_LANGUE:-fr}${NGINX_TOOLS_I18N_ORIGINE:+ ($NGINX_TOOLS_I18N_ORIGINE)}"
    for p in "${CFG_OPTIONS[@]}"; do opts+=" · $p"; done
    echo "  Options : $opts (ligne de commande prioritaire)"
    for p in "${CFG_PROBLEMES[@]}"; do echo "  ATTENTION : valeur de configuration ignorée : $p" >&2; done
    for p in "${CFG_FRANCAIS[@]}"; do echo "  ATTENTION : valeur en français, écrire l'anglais dans le fichier de configuration : $p" >&2; done
    return 0
}
