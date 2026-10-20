# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _i18n.sh — langue d'affichage (fr / en…) et fichier de configuration des programmes bash (bibliothèque commune sourcée, apps/).
#
# HISTORIQUE DE VERSION (résumé — voir doc/_i18n.sh.changelog.txt pour le détail complet) :
#   1.14.20261019.150215 — config_rafraichir: configuration files with no active option rewritten from the current template; new copyright.
#   1.13.20261017.200717 — Ctrl+C: a second Ctrl+C during the « Interrupt? » question stops the program (it was ignored after a Ctrl+C in a question).
#   1.12.20261017.105442 — Language: LANGUAGE (GNU) also starts the translator; « Options : --lang xx (origine) » for the bash programs.
#   1.11.20261016.173838 — run_interruptible (Ctrl+C answered at once during a long command) and ctrl_c_child (the child program asks, not both); stop of the running command on « yes ».
#   1.10.20261015.172851 — ShellCheck : tr 'A-Z' 'a-z' remplacé par les classes [:upper:] / [:lower:] (SC2018, SC2019).
#   1.9.20261015.143436 — --anonymize, NGINX_TOOLS_ANONYMIZE et ANONYMIZE du fichier de configuration : le programme est relancé derrière le filtre d'apps/_traduire.py.
#   1.8.20261015.092124 — ShellCheck SC2004 : (( CFG[DEBUG_LEVEL] >= 1 )) sans $.
#   1.7.20261015.080630 — LOG_KEEP_DAYS du fichier commun exporté (NGINX_TOOLS_LOG_KEEP_DAYS).
#   1.6.20261015.073057 — config_date_modif : date de modification des fichiers de configuration lus (heure locale).
#   1.5.20261015.065821 — Le fichier commun app-default.conf est créé s'il n'existe pas (config_creer_defaut).
#   1.4.20261014.175821 — Fichier commun app-default.conf lu avant celui du programme (LANGUAGE, VERBOSE, DEBUG_LEVEL).
#   1.3.20261014.154520 — Ctrl+C pendant une question : la réponse est lue hors readline (plus de « nt » mêlé à la ligne en cours).
#   1.2.20261012.103600 — config_creer_defaut : crée le fichier de configuration par défaut au premier démarrage (toutes les options en commentaire).
#   1.1.20261011.144500 — Ctrl+C : ctrl_c_installer (confirmation « Interrompre le programme ? [o/N] »), appelée par i18n_relancer ; CTRL_C_NETTOYAGE.
#   1.0.20261010.221500 — Création : i18n_relancer (traduction de la sortie par apps/_traduire.py), config_lire / config_defaut / config_afficher (règle commune des fichiers de configuration).
#
# Utilisation, tout au début du programme (après SCRIPT_DIR et SCRIPT_NAME) :
#   . "$SCRIPT_DIR/apps/_i18n.sh"; i18n_relancer "$SCRIPT_NAME" NOM_DU_PROGRAMME_LANG "$0" "$@"
#   config_lire "$SCRIPT_NAME" "$@"                         # /etc/default/PROGRAMME.conf PUIS ~/.PROGRAMME.cfg ; -c / --config FICHIER : ce fichier SEUL
#   config_defaut MIN_IPS MIN_IPS --min-ips nombre          # valeur du fichier = valeur par défaut de la variable (la ligne de commande la remplace ensuite)
#   config_afficher                                         # « Configuration lue : … » et « Options : … »
# Langue : --lang, NGINX_TOOLS_LANG, la variable du programme, LANGUAGE du fichier de configuration, LC_ALL / LC_MESSAGES / LANG (voir apps/_i18n.py). En français
# (cas courant) rien ne change : aucun processus de plus. Dans une autre langue, apps/_traduire.py lance le programme et traduit sa sortie ligne par ligne.
# shellcheck shell=bash

_I18N_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# i18n_relancer PROGRAMME VARIABLE_LANGUE SCRIPT ARGUMENTS… : relance le programme derrière le traducteur si la langue n'est pas le français. Sans effet (retour 0) si le
# programme est déjà derrière le traducteur, si rien n'indique une autre langue, ou si python3 / apps/_traduire.py manquent.
i18n_relancer() {
    _i18n_relancer "$@" || return $?
    ctrl_c_installer                                    # atteint seulement si le programme n'est pas relancé derrière le traducteur (qui, lui, ne pose aucune question)
    return 0
}

# _i18n_anonymize_configure PROGRAMME : vrai si un fichier de configuration (commun ou du programme) contient ANONYMIZE=oui ET que la sortie est un terminal (jamais pour un tube ni
# cron : voir apps/_anonymiser.py) ; NGINX_TOOLS_ANONYMIZE=0 l'empêche.
_i18n_anonymize_configure() {
    local f valeur
    [[ -t 1 && "${NGINX_TOOLS_ANONYMIZE:-}" != "0" ]] || return 1
    for f in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$1.conf" "${HOME:-/root}/.app-default.cfg" "${HOME:-/root}/.$1.cfg"; do
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
        case "$a" in --anon|--anony|--anonym|--anonymi|--anonymiz|--anonymize) signal=1 ;; esac          # --anonymize : filtre de sortie (apps/_anonymiser.py), posé par apps/_traduire.py
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
        if [[ -f "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$programme.conf" || -f "${HOME:-/root}/.$programme.cfg" ]]; then signal=1
        elif [[ -n "${LANGUAGE:-}${LC_ALL:-}${LC_MESSAGES:-}${LANG:-}" ]]; then signal=1; fi
    fi
    [[ -n "$signal" ]] || return 0
    exec python3 "$_I18N_DIR/_traduire.py" "$programme" "$variable" -- bash "$script" "$@"
}

# --- Ctrl+C : toujours une confirmation avant de quitter ---------------------------------------------------------------------------------------------------------
# ctrl_c_installer : installe le piège INT « Interrompre le programme ? [o/N] ». Oui (o, oui, y, yes), fin de fichier ou second Ctrl+C -> arrêt (code 130) après la fonction
# de nettoyage nommée par CTRL_C_NETTOYAGE (si elle existe) ; autre réponse -> reprise. Sans effet hors terminal (cron, tube, tests) et si NGINX_TOOLS_CTRL_C=0.
# Limite : le Ctrl+C du terminal part aussi aux commandes en cours (même groupe de processus) : une commande courte interrompue pendant la question s'arrête
# quand même ; le script, lui, reprend après la réponse. CTRL_C_NETTOYAGE sert aussi à arrêter ce que le script a lancé en arrière-plan.
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
    if (( _ctrl_c_en_cours )); then _ctrl_c_arret; fi             # second Ctrl+C pendant la question : confirmé
    _ctrl_c_en_cours=1
    printf '\r\n%s' "Interrompre le programme ? [o/N] " >&2
    # PAS « read -e » : pendant une question déjà posée par « read -e », la réponse se mêlait à la ligne en cours (« n » + « t » = « nt »). Terminal remis en mode ligne
    # (écho, retour arrière du noyau) le temps de la réponse, puis dans l'état d'avant (celui que le readline interrompu attend).
    local etat_tty=""
    etat_tty=$(stty -g 2>/dev/null </dev/tty) || etat_tty=""
    [[ -n "$etat_tty" ]] && stty icanon echo echoe isig icrnl 2>/dev/null </dev/tty
    # 1.13 : la réponse est lue dans un sous-shell où Ctrl+C a son effet normal : bash ne relance pas un piège INT déjà en cours, si bien qu'un second Ctrl+C
    # pendant cette question (après un Ctrl+C reçu pendant un « read -e ») restait sans effet (« ^C^C^C »). Sous-shell interrompu ou fin de fichier : oui.
    # Ce shell-ci ignore Ctrl+C le temps de la question (sinon bash, recevant le même signal pendant son piège : « trap_handler: bad signal 2 », abandon).
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

# run_interruptible CMD… (1.11) : runs a LONG command so that Ctrl+C is answered AT ONCE. In the foreground, bash runs the INT trap only when the command ends
# (30 min for a module update, 60 s for a « timeout journalctl »): Ctrl+C seemed dead. Here the command runs in the background (SIGINT ignored for it: the
# terminal's Ctrl+C is not for it) and bash waits with « wait », which the trap interrupts: the question comes immediately; « no » goes back to waiting,
# « yes » stops the command (TERM) then the program. Redirections of the call apply to the command; its code is returned. Not for a command that reads the keyboard.
run_interruptible() {
    local pid rc=0 rc2
    "$@" &
    pid=$!
    CTRL_C_PID=$pid
    while :; do
        wait "$pid" && rc=0 || rc=$?
        kill -0 "$pid" 2>/dev/null || break        # finished (otherwise: wait interrupted by the Ctrl+C question, answer « no »)
    done
    if (( rc > 128 )); then                        # ended while the question was asked: its real code, if bash still has it
        wait "$pid" 2>/dev/null && rc2=0 || rc2=$?
        (( rc2 == 127 )) || rc=$rc2
    fi
    CTRL_C_PID=""
    return "$rc"
}

# ctrl_c_child CMD… (1.11) : runs a program that owns the terminal (questions, its own Ctrl+C confirmation). The terminal's Ctrl+C reaches both programs (same
# process group): without this, this program asked « Interrupt? » again once the child had answered. Here this program says nothing while the child runs
# (a trap that does nothing, NOT an ignored signal, which the child would inherit). Its code is returned.
ctrl_c_child() {
    local rc=0
    trap ':' INT
    "$@" || rc=$?
    trap - INT
    ctrl_c_installer
    return "$rc"
}

# --- Fichier de configuration : lu ligne à ligne, JAMAIS exécuté (pas de « source ») ; clés en majuscules, guillemets facultatifs, # = commentaire -------------------
declare -gA CFG=()
CFG_FICHIERS=()
CFG_EXPLICITE=""
CFG_PROGRAMME=""
CFG_OPTIONS=()
CFG_PROBLEMES=()

# config_creer_defaut PROGRAMME ARGUMENTS… : premier démarrage — si AUCUN fichier de la règle n'existe, crée celui du système (/etc/default/PROGRAMME.conf, root) ou, sans les
# droits, le fichier personnel (~/.PROGRAMME.cfg) : copie de doc/PROGRAMME.conf.example (CFG_DOSSIER_DOC, sinon le dossier doc/ du programme) dont toutes les options sont en
# commentaire. Rien n'est créé avec -c/--config, --help / --version / --changelog, si NGINX_TOOLS_CONFIG_CREER=0 ou si le modèle est absent. Chemin créé : CFG_CREE.
CFG_CREE=""
config_creer_defaut() {
    local programme="$1" a ligne modele chemin mode systeme perso; shift
    CFG_CREE=""
    [[ "${NGINX_TOOLS_CONFIG_CREER:-}" == "0" ]] && return 0
    for a in "$@"; do
        case "$a" in -h|--help|--version|--changelog|-c|--config|--config=*) return 0 ;; esac
    done
    config_creer_fichier app-default "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "${HOME:-/root}/.app-default.cfg"       # le fichier commun d'abord (1.5)
    config_creer_fichier "$programme" "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$programme.conf" "${HOME:-/root}/.$programme.cfg"
    return 0
}

# config_creer_fichier NOM SYSTEME PERSO : crée le premier des deux fichiers qui peut l'être, à partir de doc/NOM.conf.example, si aucun n'existe ; CFG_CREE reçoit le chemin créé
# (seulement pour le fichier du programme : la ligne « Configuration lue » ne parle pas du fichier commun).
config_creer_fichier() {
    local programme="$1" systeme="$2" perso="$3" a ligne modele chemin mode
    if [[ -e "$systeme" || -e "$perso" ]]; then
        for chemin in "$systeme" "$perso"; do [[ -f "$chemin" ]] && config_rafraichir "$programme" "$chemin"; done
        return 0
    fi
    modele="${CFG_DOSSIER_DOC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/doc}/$programme.conf.example"
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
            if [[ "$programme" != app-default ]]; then CFG_CREE="$chemin"; export NGINX_TOOLS_CONFIG_CREE="$chemin"; fi       # variable d'environnement : la ligne reste vraie après i18n_relancer
            return 0
        fi
    done
    return 0
}

# config_rafraichir NOM FICHIER (1.14) : un fichier EXISTANT dont aucune option n'est active (tout en commentaire = jamais modifié) est réécrit à partir du modèle
# doc/NOM.conf.example quand celui-ci a changé ; un fichier avec au moins une ligne CLÉ=VALEUR n'est JAMAIS touché. Fichier temporaire du même dossier, mêmes droits et
# propriétaire, puis renommage. NGINX_TOOLS_CONFIG_MAJ_AUTO=0 : jamais. Le chemin est ajouté à NGINX_TOOLS_CONFIG_MAJ (ligne « Configuration lue »).
config_rafraichir() {
    local programme="$1" chemin="$2" modele temporaire ligne premiere=1
    [[ "${NGINX_TOOLS_CONFIG_MAJ_AUTO:-}" == "0" ]] && return 0
    modele="${CFG_DOSSIER_DOC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/doc}/$programme.conf.example"
    [[ -r "$modele" && -r "$chemin" && -w "$chemin" && -w "$(dirname "$chemin")" ]] || return 0
    grep -qE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' "$chemin" && return 0          # une option active : fichier modifié par l'utilisateur
    tail -c "$(wc -c < "$modele")" "$chemin" 2>/dev/null | cmp -s - "$modele" && return 0       # déjà au modèle actuel
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

# config_lire PROGRAMME ARGUMENTS… : remplit CFG ({CLÉ: valeur}) et CFG_FICHIERS ; un -c FICHIER / --config FICHIER / --config=FICHIER des arguments : ce fichier SEUL.
config_lire() {
    local programme="$1" i f c ligne cle valeur; shift
    CFG=(); CFG_FICHIERS=(); CFG_EXPLICITE=""; CFG_PROGRAMME="$programme"; CFG_OPTIONS=(); CFG_PROBLEMES=()
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
        # Fichier COMMUN à tous les programmes (app-default.conf) : lu d'abord, seulement LANGUAGE, VERBOSE et DEBUG_LEVEL ; celui du programme l'emporte.
        for f in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "${HOME:-/root}/.app-default.cfg"; do
            [[ -f "$f" ]] && communs+=("$f")
        done
        for f in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$programme.conf" "${HOME:-/root}/.$programme.cfg"; do
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
    # DEBUG_LEVEL >= 1 vaut VERBOSE=oui (sauf VERBOSE écrit dans un fichier) ; le niveau est exporté dans NGINX_TOOLS_DEBUG_LEVEL.
    if [[ "${CFG[DEBUG_LEVEL]:-}" =~ ^[0-9]+$ ]] && (( CFG[DEBUG_LEVEL] >= 1 )); then
        [[ -n "${CFG[VERBOSE]:-}" ]] || CFG[VERBOSE]="oui"
        export NGINX_TOOLS_DEBUG_LEVEL="${CFG[DEBUG_LEVEL]}"
    fi
    # LOG_KEEP_DAYS (fichier commun ou du programme) : jours de conservation des journaux propres aux programmes, exporté pour ceux qu'ils lancent.
    [[ "${CFG[LOG_KEEP_DAYS]:-}" =~ ^[0-9]+$ ]] && export NGINX_TOOLS_LOG_KEEP_DAYS="${CFG[LOG_KEEP_DAYS]}"
    return 0
}

# config_defaut VARIABLE CLÉ OPTION [TYPE] : si le fichier définit CLÉ, VARIABLE prend cette valeur (valeur par défaut : la ligne de commande la remplace ensuite).
# TYPE : texte (défaut), nombre (entier positif ou nul) ou booléen (oui/non, true/false, 1/0 -> 1 ou 0). Valeur invalide : signalée par config_afficher, ignorée.
config_defaut() {
    local variable="$1" cle="$2" option="$3" type="${4:-texte}" valeur="${CFG[$2]:-}"
    [[ -n "$valeur" ]] || return 0
    case "$type" in
        nombre)
            if [[ "$valeur" =~ ^[0-9]+$ ]]; then printf -v "$variable" '%s' "$valeur"; CFG_OPTIONS+=("$option $valeur")
            else CFG_PROBLEMES+=("$cle=$valeur (entier attendu)"); fi ;;
        booleen)
            case "${valeur,,}" in
                1|true|yes|oui|on|vrai) printf -v "$variable" '%s' 1; CFG_OPTIONS+=("$option oui") ;;
                0|false|no|non|off|faux) printf -v "$variable" '%s' 0; CFG_OPTIONS+=("$option non") ;;
                *) CFG_PROBLEMES+=("$cle=$valeur (oui ou non attendu)") ;;
            esac ;;
        *) printf -v "$variable" '%s' "$valeur"; CFG_OPTIONS+=("$option $valeur") ;;
    esac
    return 0
}

# config_date_modif FICHIER : date et heure LOCALES de dernière modification (AAAA-MM-JJ HH:MM), « ? » si illisible.
config_date_modif() { date -r "$1" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '?'; }

# config_afficher : deux lignes de départ — QUEL(S) fichier(s) de configuration ont été lus, puis les options importantes qui en résultent (langue comprise).
config_afficher() {
    local lus="" f opts p
    [[ -n "${NGINX_TOOLS_CONFIG_VUE:-}" ]] && return 0      # déjà affichée par le programme appelant (ou par un appel précédent) : pas de répétition dans les sorties analysées
    export NGINX_TOOLS_CONFIG_VUE=1
    if [[ -n "$CFG_EXPLICITE" ]]; then
        lus="Configuration lue : $(cd "$(dirname "$CFG_EXPLICITE")" 2>/dev/null && pwd)/$(basename "$CFG_EXPLICITE") (modifié le $(config_date_modif "$CFG_EXPLICITE")) (demandé par -c/--config : aucun autre fichier n'est lu)"
    elif (( ${#CFG_FICHIERS[@]} == 0 )); then
        lus="Configuration : aucun fichier (cherchés : ${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/$CFG_PROGRAMME.conf, ${HOME:-/root}/.$CFG_PROGRAMME.cfg) — valeurs par défaut"
    else
        for f in "${CFG_FICHIERS[@]}"; do lus+="${lus:+, puis }$f (modifié le $(config_date_modif "$f"))"; done
        lus="Configuration lue : $lus"
        (( ${#CFG_FICHIERS[@]} > 1 )) && lus+=" (le dernier l'emporte)"
        for f in "${CFG_FICHIERS[@]}"; do [[ "$f" == "${NGINX_TOOLS_CONFIG_CREE:-}" ]] && CFG_CREE="$f"; done
        [[ -n "$CFG_CREE" ]] && lus+=" (fichier créé à l'instant : toutes les options y sont en commentaire, valeurs par défaut)"
        if [[ -z "$CFG_CREE" && -n "${NGINX_TOOLS_CONFIG_MAJ:-}" ]]; then         # 1.14 : fichiers remis au modèle actuel (config_rafraichir)
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
    return 0
}
