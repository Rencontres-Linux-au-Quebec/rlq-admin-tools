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
# nginx-hardening.sh - idempotent initial installation: directories (ACME, catch-all log, maintenance page), and firewall (blocks direct external access to Odoo's HTTP/gevent ports, which would bypass ALL
# nginx rules if left open). Safe to rerun several times: each step checks the current state before
# acting, nothing is duplicated. NO DANGER BY DEFAULT: without an explicit --update, it ONLY checks, never changes
# anything. NEVER modifies odoo.conf itself (only a diagnostic and a recommendation): this file has a
# format and comments specific to each installation, too risky to edit blindly.
# format and comments specific to each installation, too risky to edit blindly.
#
# Usage : nginx-hardening.sh [--update] [--check] [--odoo-http-port PORT] [--odoo-gevent-port PORT]
#                              [--odoo-service NOM] [--odoo-conf CHEMIN] [--odoo-conf-paths LISTE] [--timezone ZONE] [--workers N] [-v|--verbose] [--version]
#                              [--changelog]
#   - (no option)          : CHECK ONLY - changes NOTHING, same behavior as --check. This is the
#                            default behavior since 1.7 (before: applied the changes by
#                            default, which posed a real risk of accidental system changes).
#   - --check              : same as no option - kept for explicit compatibility. This is the mode
#                            qu'utilisent nginx-log-audit.sh et app-health-check.py pour avertir si le setup
#                            initial installation was never done.
#   - --update             : actually runs the installation steps (directories + firewall), writes the
#                            state file. Requires root. This is the former default behavior.
#   - --odoo-http-port     : Odoo's main HTTP port to check (default: http_port/xmlrpc_port of the Odoo
#                            configuration found, otherwise 8069 if the key is absent, otherwise 10000 if no configuration).
#   - --odoo-gevent-port   : gevent/longpolling port (default: gevent_port/longpolling_port of the configuration, otherwise
#                            8072; 10002 if no configuration). These ports drive ufw/iptables (step 5).
#   - --odoo-service NAME  : Odoo systemd unit to audit (steps 6-7). Without this option: auto-detection
#                            among "erplibre.service" and "erplibre_erplibre.service" (same logic as
#                            app-log-check.py).
#   - --odoo-conf PATH     : Odoo configuration file to read (ports, logfile, workers, limits). Without this option:
#                            first existing file of --odoo-conf-paths. If one is found, the server application is
#                            recognized as Odoo and the log (logfile, otherwise systemd journal) is located. Read-only.
#   - --odoo-conf-paths L  : candidate paths (space separated, * patterns allowed). Default: /etc/odoo/odoo-linux_meetup.conf
#                            /opt/odoo/erplibre/config.conf /home/utilisateur/git/erplibre/config.conf /etc/odoo/*.conf.
#                            ODOO_CONF_PATHS key of /etc/default/nginx-hardening.conf or ~/.nginx-hardening.conf.
#   - --timezone ZONE      : server time zone (step 0b; default America/Montreal, asked at the first --update, stored in TIMEZONE;
#                            "none": change nothing).
#   - --mail-host/--mail-port/--mail-security/--mail-user/--mail-from/--mail-to, --mail-setup : mail of the Python and Bash programs (step 0d);
#                            asked ONCE with --update; the password is asked without echo and kept in a separate file (0600).
#   - --log-retention-months N : duree de conservation des journaux visee par l'etape 11 (1 a 24 mois, defaut : 3).
#                            nginx and fail2ban: "rotate" raised to cover at least N months (never lowered).
#                            Journal systemd : MaxRetentionSec=Nmonth ; une valeur deja fixee n'est modifiee que si
#                            l'option est donnee ET qu'elle se trouve dans le fichier de ce script (sinon : signalee).
#   - --workers N          : number of Odoo workers, if not found in odoo.conf (e.g. set on the command
#                            line in run.sh rather than in the config file).
#   - -v/--verbose         : shows each system command run (ss, ufw, iptables, systemctl, nginx -T,
#                            curl, cp, chown, fail2ban-client...), prefixed with "+".
#   - --version            : affiche la version et quitte.
#   - --changelog          : affiche CHANGELOG.md (couleur si terminal).
#
# Must be run as root for --update (chown, firewall, /var/www, /var/log/nginx). Without --update
# (check only, default behavior), no privilege required.

set -euo pipefail
# PATH completed (2.x): under cron, PATH is limited to /usr/bin:/bin - ipset, iptables, nft, fail2ban-client, nginx
# (in /usr/sbin, /sbin) were then not found. Added AT THE END: never hide a command already found.
for _d in /usr/local/sbin /usr/sbin /sbin; do [[ -n "${NGINX_TOOLS_TESTS:-}" ]] && break; case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac; done
# (During the test suite, NGINX_TOOLS_TESTS disables this addition: /usr/sbin/ufw & co would otherwise stay reachable.)
export PATH

# grep_q: equivalent of "grep -q" WITHOUT the SIGPIPE race. "cmd | grep -q pattern" under "set -o pipefail" can
# repondre FAUX alors que le motif est present : grep -q s'arrete a la premiere correspondance et ferme le tube ; si
# cmd still writing, it receives SIGPIPE and pipefail propagates this failure (race observed in test on "ipset list -n").
# grep sans -q lit toute l'entree : l'ecrivain n'est jamais interrompu.
grep_q() { grep "$@" >/dev/null; }

# shellcheck disable=SC2154  # "ec" is set INSIDE the trap text (ec=$?), at execution: shellcheck
#                              ne peut pas le voir, le texte etant entre apostrophes (faux positif).
trap 'ec=$?; echo "" >&2; echo "*** ARRÊT INATTENDU DU SCRIPT (code $ec) À LA LIGNE $LINENO ***" >&2; echo "*** Commande fautive : $BASH_COMMAND" >&2' ERR

# run : execute une commande en l'affichant d'abord si -v/--verbose. Affichage via le descripteur 3 (copie du
# stderr d'origine) : plusieurs appels masquent leur propre stderr ("2>/dev/null"), ce qui ferait disparaitre la
# ligne "+ commande" si elle etait ecrite sur stderr. Fonctionne aussi a l'interieur des $(...).
exec 3>&2
VERBOSE=0
run() {
    if [[ "$VERBOSE" == "1" ]]; then
        printf '+ %s\n' "$*" >&3
    fi
    "$@"
}

readonly SCRIPT_VERSION="2.60.20261028.170500"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}" .sh)"; readonly SCRIPT_NAME
# Display language (en or fr): --lang, NGINX_HARDENING_LANG, LANGUAGE of the configuration file, LC_ALL / LANG - apps/_i18n.sh translates the output (nothing changes in French).
if [[ -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_i18n.sh"
    i18n_relancer nginx-hardening NGINX_HARDENING_LANG "$0" "$@"
fi
# Changelog dans le sous-repertoire doc/ ; repli sur l'ancien emplacement (a cote du programme) tant que
# l'installation n'a pas ete reorganisee.
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
readonly CHANGELOG_FILE

# Section of this program in CHANGELOG.md (from its "## <file name>" heading to the next "## " heading).
changelog_section() {
    awk -v cle="${BASH_SOURCE[0]##*/}" '/^## /{dans=($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE"
}
# migrer_chemin OLD NEW: renaming of the programs in 2.0 - renames a file or directory from the old name
# s'il existe et que le nouveau n'existe PAS encore (jamais d'ecrasement) ; silencieux si rien a faire ou si les
# droits manquent (le programme continue avec le nouveau chemin).
migrer_chemin() {
    local ancien="$1" nouveau="$2"
    if [[ -e "$ancien" && ! -e "$nouveau" ]]; then
        mkdir -p "$(dirname "$nouveau")" 2>/dev/null || true
        if mv "$ancien" "$nouveau" 2>/dev/null; then
            echo "Migration (renommage des programmes, version 2.0) : $ancien → $nouveau" >&2
        fi
    fi
    return 0
}
migrer_chemin "/etc/default/setup-nginx-odoo.conf" "/etc/default/${SCRIPT_NAME}.conf"
readonly STATE_FILE="${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/${SCRIPT_NAME}.conf"

: "${LC_ALL:=C.UTF-8}"
export LC_ALL

if [[ -t 1 || -n "${REPORT_ERR_COULEUR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_RESET=""
fi

CHECK_ONLY=1
# Backups (2.59): one archive (NGINX_HARDENING_ARCHIVE_DIR, separate from the per-file .bak copies) of the nginx and fail2ban configuration before each --update (--rollback restores it).
ARCHIVE_DIR="${NGINX_HARDENING_ARCHIVE_DIR:-/var/backups/nginx-hardening/archives}"
BACKUP_KEEP="${NGINX_HARDENING_BACKUP_KEEP:-20}"
read -r -a BACKUP_ROOTS <<< "${NGINX_HARDENING_BACKUP_ROOTS:-/etc/nginx /etc/fail2ban}"
ROLLBACK=0
ROLLBACK_BACKUP=""
ROLLBACK_YES=0
DISABLE_URI_LIST=()     # --disable-uri CHEMIN (repeatable): refused with 404 in the Odoo site, every language
ENABLE_URI_LIST=()      # --enable-uri CHEMIN (repeatable): the refusal is removed
ODOO_HTTP_PORT=""      # empty: read from the Odoo configuration ("configuration" step), otherwise 10000 / 10002
ODOO_GEVENT_PORT=""
ODOO_CONF_PATHS="${ODOO_CONF_PATHS:-}"
ODOO_SERVICE=""
TIMEZONE=""            # empty: default below (asked the first time); "none": change nothing
TIMEZONE_DEFAUT="America/Montreal"
MAIL_HOST=""; MAIL_PORT=""; MAIL_SECURITY=""; MAIL_USER=""; MAIL_FROM=""; MAIL_TO=""   # programs' mail (step 0d): empty = read from the common file, otherwise asked
MAIL_SETUP=0           # --mail-setup: ask the mail configuration again even if it exists
RENAME_FROM=""; RENAME_TO=""   # --rename-from / --rename-to: public DNS name change (step 0e); empty: nothing to do
APP_FORCE=""
ODOO_CONF=""
ODOO_WORKERS_OVERRIDE=""
# Initialized here: set by steps specific to Odoo (4 and 9), but read by the final summary - same
# for BigBlueButton, for which these steps are "not applicable" (otherwise: "unbound variable" at the end of execution).
PORT_EXPOSED=0
NEED_FAIL2BAN_RESTART=0
F2B_INSTALLED_JAILS=()
LOG_RETENTION_MONTHS=3
RETENTION_EXPLICITE=0
# Configuration file (/etc/default/nginx-hardening.conf THEN ~/.nginx-hardening.conf; -c/--config FILE: this file only): default values of the options.
# /etc/default/nginx-hardening.conf ALSO serves as the state file (SETUP_* lines, rewritten by --update): the other lines are kept there.
if declare -F config_lire >/dev/null; then
    config_lire nginx-hardening "$@"
    config_defaut APP_FORCE APP --app texte
    config_defaut LOG_RETENTION_MONTHS LOG_RETENTION_MONTHS --log-retention-months nombre
    config_defaut MAIL_FROM MAIL_FROM --mail-from texte
    config_defaut MAIL_HOST MAIL_HOST --mail-host texte
    config_defaut MAIL_PORT MAIL_PORT --mail-port nombre
    config_defaut MAIL_SECURITY MAIL_SECURITY --mail-security texte
    config_defaut MAIL_SETUP MAIL_SETUP --mail-setup booleen
    config_defaut MAIL_TO MAIL_TO --mail-to texte
    config_defaut MAIL_USER MAIL_USER --mail-user texte
    config_defaut ODOO_CONF ODOO_CONF --odoo-conf texte
    config_defaut ODOO_CONF_PATHS ODOO_CONF_PATHS --odoo-conf-paths texte
    config_defaut ODOO_GEVENT_PORT ODOO_GEVENT_PORT --odoo-gevent-port nombre
    config_defaut ODOO_HTTP_PORT ODOO_HTTP_PORT --odoo-http-port nombre
    config_defaut ODOO_SERVICE ODOO_SERVICE --odoo-service texte
    config_defaut RENAME_FROM RENAME_FROM --rename-from texte
    config_defaut RENAME_TO RENAME_TO --rename-to texte
    config_defaut TIMEZONE TIMEZONE --timezone texte
    config_defaut VERBOSE VERBOSE --verbose booleen
    config_defaut ODOO_WORKERS_OVERRIDE WORKERS --workers nombre
fi

export ODOO_CONF_PATHS   # read by apps/_odoo_conf.sh (empty: ODOO_CONF_PATHS lines of the configuration files, then default list)

# --report-err: error report to copy-paste at the end of execution (program, version, server, failures...) - apps/_rapport.sh
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_rapport.sh"
    rapport_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi
# First line of EVERY execution, even with --help: the name and version of the program (--version displays it itself).
case " $* " in *" --version "*) ;; *) echo "nginx-hardening.sh v$SCRIPT_VERSION" ;; esac
if declare -F config_afficher >/dev/null; then
    case " $* " in *" --version "*|*" --changelog "*) ;; *) config_afficher ;; esac
fi
# Address lists (white list and places): /etc/default/nginx-tools-*.conf, never shipped in the archives - common reader apps/_listes.sh.
# shellcheck source=/dev/null
[[ -r "$SCRIPT_DIR/apps/_listes.sh" ]] && . "$SCRIPT_DIR/apps/_listes.sh"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        --check) CHECK_ONLY=1; shift ;;   # behavior by default now - kept for explicit compatibility
        --update) CHECK_ONLY=0; shift ;;  # applique reellement les changements (anciennement le defaut)
        --backup) ROLLBACK_BACKUP="${2:-}"; shift 2 ;;
        --rollback) ROLLBACK=1; shift ;;
        --disable-uri) DISABLE_URI_LIST+=("${2:-}"); shift 2 ;;
        --enable-uri) ENABLE_URI_LIST+=("${2:-}"); shift 2 ;;
        --yes) ROLLBACK_YES=1; shift ;;
        --app) APP_FORCE="${2:-}"; shift 2 ;;
        --app=*) APP_FORCE="${1#--app=}"; shift ;;
        --mail-from) MAIL_FROM="${2:-}"; shift 2 ;;
        --mail-host) MAIL_HOST="${2:-}"; shift 2 ;;
        --mail-port) MAIL_PORT="${2:-}"; shift 2 ;;
        --mail-security) MAIL_SECURITY="${2:-}"; shift 2 ;;
        --mail-setup) MAIL_SETUP=1; shift ;;
        --mail-to) MAIL_TO="${2:-}"; shift 2 ;;
        --mail-user) MAIL_USER="${2:-}"; shift 2 ;;
        --odoo-http-port) ODOO_HTTP_PORT="${2:-}"; shift 2 ;;
        --odoo-gevent-port) ODOO_GEVENT_PORT="${2:-}"; shift 2 ;;
        --odoo-service) ODOO_SERVICE="${2:-}"; shift 2 ;;
        --rename-from) RENAME_FROM="${2:-}"; shift 2 ;;
        --rename-to) RENAME_TO="${2:-}"; shift 2 ;;
        --timezone) TIMEZONE="${2:-}"; shift 2 ;;
        --odoo-conf) ODOO_CONF="${2:-}"; shift 2 ;;
        --odoo-conf-paths) ODOO_CONF_PATHS="${2:-}"; shift 2 ;;
        --workers) ODOO_WORKERS_OVERRIDE="${2:-}"; shift 2 ;;
        --log-retention-months) LOG_RETENTION_MONTHS="${2:-}"; RETENTION_EXPLICITE=1; shift 2 ;;
        --version)
            echo "nginx-hardening.sh v$SCRIPT_VERSION"
            exit 0
            ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then
                echo "Changelog introuvable : $CHANGELOG_FILE" >&2
                exit 1
            fi
            if [[ -t 1 ]]; then
                changelog_section | sed -E "s/^(### [0-9]+\.[0-9]+\.[0-9]{8}\.[0-9]{6}.*)$/$(printf '\x1b[1;36m')\1$(printf '\x1b[0m')/" | (trap '' PIPE; less -R 2>/dev/null || cat) || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            else
                changelog_section || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            fi
            exit 0
            ;;
        -h|--help)
            cat <<'AIDE'
Usage : nginx-hardening.sh [OPTION]...
Setup initial et audit du serveur (nginx, pare-feu, Odoo, fail2ban, journaux, courriel). Par défaut (sans --update) :
vérification seule, rien n'est modifié.

Options (par ordre alphabétique) :
  --anonymize                  anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE
  --app NAME                   application derrière nginx (profil apps/NAME.conf : odoo, bbb…) ; détectée par défaut
  --backup NAME                avec --rollback : sauvegarde à restaurer (défaut : la plus récente ; liste : ls /var/backups/nginx-hardening/archives)
  --changelog                  affiche le journal des modifications
  --check                      vérification seule (comportement par défaut)
  -c, --config FILE            fichier de configuration à lire SEUL (défaut : /etc/default/nginx-hardening.conf puis ~/.nginx-hardening.conf)
  --disable-uri CHEMIN         refuse (404) ce chemin dans le site Odoo, toutes les langues (ex. /shop) : fichier snippets/uri-desactivees.conf ; répétable
  --enable-uri CHEMIN          rétablit un chemin refusé par --disable-uri ; répétable
  -h, --help                   affiche cette aide et quitte
  --lang LANG                  langue d'affichage : en ou fr (défaut : selon LC_ALL / LC_MESSAGES / LANG)
  --log-retention-months N     durée de conservation des journaux visée par l'étape 11 (1 à 24 mois, défaut : 3)
  --mail-from ADDRESS          expéditeur des courriels de la suite (défaut : l'identifiant du relais)
  --mail-host HOST             relais SMTP des courriels des programmes Python et Bash (étape 0d ; demandé la première fois avec --update)
  --mail-port PORT             port du relais SMTP (défaut : 587)
  --mail-security MODE         chiffrement : starttls (défaut), ssl ou none
  --mail-setup                 redemander la configuration du courriel (avec --update)
  --mail-to ADDRESS            destinataire des courriels de la suite (alertes, rapports)
  --mail-user NAME             identifiant du relais SMTP (le mot de passe est demandé, jamais passé en option)
  --odoo-conf FILE            configuration d'Odoo (défaut : premier fichier trouvé parmi --odoo-conf-paths)
  --odoo-conf-paths LIST       chemins (espaces ; motifs * permis) où chercher la configuration d'Odoo (défaut : /etc/odoo/odoo-linux_meetup.conf
                               /opt/odoo/erplibre/config.conf /home/utilisateur/git/erplibre/config.conf /etc/odoo/*.conf…)
  --odoo-gevent-port PORT      port gevent (websocket) d'Odoo à vérifier (défaut : celui de la configuration d'Odoo)
  --odoo-http-port PORT        port HTTP d'Odoo à vérifier (défaut : celui de la configuration d'Odoo)
  --odoo-service NAME         unité systemd d'Odoo (défaut : détectée)
  --rename-from NAME           ancien nom DNS public à remplacer dans nginx (étape 0e ; avec --rename-to et --update)
  --rename-to NAME             nouveau nom DNS public : nginx et certificat Let's Encrypt sont refaits pour ce nom (sans --rename-from, l'ancien nom est cherché dans nginx)
  --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
                               échecs, avertissements) ; désactive couleurs et questions interactives
  --rollback                   restaure la sauvegarde la plus récente (ou --backup NAME) de la configuration nginx et fail2ban, après confirmation
  --timezone ZONE              fuseau horaire du serveur (défaut : America/Montreal, demandé la première fois ; none = ne pas toucher)
  --update                     installer ou mettre à jour ce qui manque (sauvegarde des fichiers modifiés)
  -v, --verbose                affiche chaque commande lancée
  --version                    affiche la version et quitte
  --workers N                  nombre de workers pour la suggestion de limites mémoire (étape 6)
  --yes                        avec --rollback : restaurer sans question
AIDE
            exit 0
            ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*) shift ;;
        --lang) shift 2 ;;                     # handled earlier (apps/_i18n.sh: i18n_relancer)
        --lang=*) shift ;;
        --report-err) shift ;;                 # handled earlier (apps/_rapport.sh); accepted here with --help, --version...
        *) echo "Argument inconnu: $1" >&2; exit 1 ;;
    esac
done

# --disable-uri / --enable-uri: a path only (starts with /, letters, digits, _ . / -); "/" alone would refuse the whole site.
for u in ${DISABLE_URI_LIST[@]+"${DISABLE_URI_LIST[@]}"} ${ENABLE_URI_LIST[@]+"${ENABLE_URI_LIST[@]}"}; do
    if [[ ! "$u" =~ ^/[A-Za-z0-9_./-]+$ ]] || [[ "$u" == *..* ]]; then
        echo "ERREUR: chemin invalide « $u » : il commence par / et ne contient que lettres, chiffres, _ . / - (ex. /shop)." >&2
        exit 1
    fi
done

# Lock (flock): only one MODIFYING execution at a time - cron, systemd timer and manual launch may
# cross. Wait in seconds (0: immediate abort). Directory: NGINX_TOOLS_LOCK_DIR (tests), otherwise /run/lock, otherwise
# /tmp. A nested call of the same script (e.g. --import-bans which runs --ban) reuses the lock already held.
prendre_verrou() {
    local attente="$1" nom="$2" var ok dir="${NGINX_TOOLS_LOCK_DIR:-/run/lock}"
    var="VERROU_TENU_${nom//-/_}"
    [[ -n "${!var:-}" ]] && return 0
    command -v flock >/dev/null 2>&1 || return 0
    [[ -d "$dir" && -w "$dir" ]] || dir="${TMPDIR:-/tmp}"
    VERROU_FICHIER="$dir/$nom.lock"
    exec 9>>"$VERROU_FICHIER" || return 0
    if (( attente > 0 )); then flock -w "$attente" 9 && ok=1 || ok=0; else flock -n 9 && ok=1 || ok=0; fi
    if (( ! ok )); then
        echo "ERREUR: une autre exécution de $nom est en cours (verrou $VERROU_FICHIER) — abandon." >&2
        exit 75
    fi
    export "$var=1"
}
if [[ "$CHECK_ONLY" != "1" && "$EUID" -ne 0 ]]; then        # root checked BEFORE the lock (1.102: the refusal is the first thing done)
    echo "ERREUR: ce script doit être exécuté en root (sudo) pour --update." >&2
    exit 1
fi
# --update only (--check changes nothing): wait for NGINX_TOOLS_LOCK_WAIT seconds at most (60 by default).
if [[ "$CHECK_ONLY" != "1" ]]; then
    prendre_verrou "${NGINX_TOOLS_LOCK_WAIT:-60}" nginx-hardening
fi

echo "=============================================================="
if [[ "$CHECK_ONLY" == "1" ]]; then
    echo " VÉRIFICATION DU SETUP INITIAL (rien n'est modifié — relancer avec --update pour appliquer)"
else
    echo " INSTALLATION / MISE À JOUR DU SETUP INITIAL (--update)"
fi
echo "=============================================================="
echo

# Each step leads to one of these three outcomes, counted at the end for the exit code and the summary.
PASS=0
FAIL=0
WARN=0

# --- Application derriere nginx : profil apps/<nom>.conf, detecte ou force (--app=NOM, ou variable APP_PROFILE) ------
APPS_DIR="$SCRIPT_DIR/apps"
if [[ -r "$APPS_DIR/_profile.sh" ]]; then
    # shellcheck source=/dev/null  # bibliotheque apps/_profile.sh, livree a cote du programme
    . "$APPS_DIR/_profile.sh"
    charger_profil_app "$APPS_DIR" "$APP_FORCE" || exit 1
else
    APP_NAME="odoo"; APP_LABEL="Odoo"; ODOO_SPECIFIC_STEPS="yes"; HARDENING_CONFIG="nginx-odoo"; TLS_TERMINATION="nginx"
    APP_DETECTION="par défaut (dossier apps/ absent à côté du programme)"
fi
echo "Application : $APP_LABEL ($APP_DETECTION)"
echo

# --- Odoo configuration: file found (--odoo-conf, otherwise first existing candidate: --odoo-conf-paths), ports and log ---
# Les ports HTTP et gevent viennent de la configuration (http_port / xmlrpc_port, gevent_port / longpolling_port) : le pare-feu
# (steps 4 and 5) therefore target the REAL ports of this server. An explicit option (--odoo-http-port...) always wins.
ODOO_PORTS_SOURCE="défaut historique (aucune configuration d'Odoo trouvée)"
ODOO_LOGFILE=""
ODOO_CONF_UNITES=""
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
    if [[ -r "$APPS_DIR/_odoo_conf.sh" ]] && ! declare -F odoo_conf_trouver >/dev/null; then
        # shellcheck source=/dev/null  # bibliotheque apps/_odoo_conf.sh, livree a cote du programme
        . "$APPS_DIR/_odoo_conf.sh"
    fi
    if [[ -z "$ODOO_CONF" ]] && declare -F odoo_conf_trouver >/dev/null; then
        ODOO_CONF=$(odoo_conf_trouver) || ODOO_CONF=""
    fi
    if [[ -n "$ODOO_CONF" && -r "$ODOO_CONF" ]] && declare -F odoo_conf_charger >/dev/null; then
        odoo_conf_charger "$ODOO_CONF"
        ODOO_LOGFILE="$ODOO_CONF_LOGFILE"
        ODOO_PORTS_SOURCE="lus dans $ODOO_CONF"
        [[ -n "$ODOO_HTTP_PORT" ]] || ODOO_HTTP_PORT="$ODOO_CONF_HTTP_PORT"
        [[ -n "$ODOO_GEVENT_PORT" ]] || ODOO_GEVENT_PORT="$ODOO_CONF_GEVENT_PORT"
        echo "Configuration d'Odoo : $ODOO_CONF"
        echo "  Ports : HTTP $ODOO_HTTP_PORT, gevent $ODOO_GEVENT_PORT ($ODOO_PORTS_SOURCE)"
        if [[ -z "$(odoo_conf_valeur "$ODOO_CONF" http_port)$(odoo_conf_valeur "$ODOO_CONF" xmlrpc_port)" ]]; then
            echo "  [!] http_port absent de la configuration : port par défaut d'Odoo (8069) retenu. Si Odoo est lancé avec --http-port en ligne de commande, précisez --odoo-http-port."
        fi
        if [[ -n "$ODOO_LOGFILE" ]]; then
            echo "  Journal d'Odoo : fichier $ODOO_LOGFILE (logfile)"
        else
            echo "  Journal d'Odoo : journal systemd (pas de logfile dans la configuration)"
        fi
        echo
    fi
fi
[[ -n "$ODOO_HTTP_PORT" ]] || ODOO_HTTP_PORT=10000
[[ -n "$ODOO_GEVENT_PORT" ]] || ODOO_GEVENT_PORT=10002

# sans_objet RAISON : etape ignoree pour cette application (affiche, jamais compte comme echec ni avertissement).
sans_objet() { echo "  [--]   Sans objet pour $APP_LABEL : $1"; }

# Team addresses -> nginx (step 12): included files GENERATED from the WHITE LIST (/etc/default/nginx-tools-white-list.conf, apps/_listes.sh).
# $1 = geo (table $is_trusted_ip: "ADDRESS 1; ") or allow (allow lists: "allow ADDRESS; "). Invalid entries:
# noted in EQUIPE_INVALIDES (never written to nginx, which would otherwise refuse its whole configuration).
EQUIPE_INVALIDES=""
generer_equipe() {
    local type="$1" adr lib n
    EQUIPE_INVALIDES=""
    echo "# GÉNÉRÉ par nginx-hardening.sh à partir de la liste blanche (/etc/default/nginx-tools-white-list.conf) — NE PAS MODIFIER À LA MAIN."
    echo "# Pour ajouter ou retirer une adresse : modifier la liste blanche, puis nginx-hardening.sh --update."
    while IFS=$'\037' read -r adr lib _ n; do
        [[ -z "$adr" ]] && continue
        if ! listes_adresse_valide "$adr"; then
            EQUIPE_INVALIDES="$EQUIPE_INVALIDES ligne $n : « $adr »;"
            continue
        fi
        if [[ "$type" == "geo" ]]; then
            printf '%-18s 1;   # %s\n' "$adr" "${lib:-équipe}"
        else
            printf 'allow %-18s # %s\n' "$adr;" "${lib:-équipe}"
        fi
    done < <(listes_blanche)
}

# generer_partages: content of shared-ips-geo.conf (nginx $is_shared_ip table): addresses of the places marked [shared] (university...); wider rate-limit zones.
generer_partages() {
    local adr lib
    echo "# GÉNÉRÉ par nginx-hardening.sh à partir des lieux [partagée] (/etc/default/nginx-tools-ip-location.conf) — NE PAS MODIFIER À LA MAIN."
    echo "# Adresses derrière lesquelles plusieurs personnes travaillent : limites de débit plus larges (odoo-global.conf, zones *_partage)."
    while IFS=$'\037' read -r adr lib _ _; do
        [[ -z "$adr" ]] && continue
        printf '%-18s 1;   # %s\n' "$adr" "${lib:-réseau partagé}"
    done < <(listes_lieux | listes_valides | awk -F'\037' '$3 ~ /partagee/ && !vu[$1]++')
}

# fragments_generes_assurer: the THREE generated fragments (team-ips-geo.conf, team-ips-allow.conf, shared-ips-geo.conf) are included by their exact name in
# odoo-global.conf and env-*.conf: it is enough that ONE is missing for nginx -t to refuse the WHOLE configuration - including during step 12, which writes the
# first two and tests nginx before step 12b has written the third (real case: nginx stopped, white list erased by the restore).
# --update, Odoo only: each MISSING fragment is created empty (one comment line, valid in a geo block and among allow lines); an existing file
# is never touched; steps 12 and 12b fill them afterward. Displays one line per file created; returns 0 if it created at least one.
fragments_generes_assurer() {
    local snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}" f cree=1
    [[ "$CHECK_ONLY" == "1" || "$APP_NAME" != "odoo" ]] && return 1
    for f in team-ips-geo.conf team-ips-allow.conf shared-ips-geo.conf uri-desactivees.conf; do
        [[ -e "$snip/$f" ]] && continue
        if mkdir -p "$snip" 2>/dev/null && printf '%s\n' "# vide — créé par nginx-hardening.sh --update (nginx refuse un include sans fichier) ; rempli aux étapes 12 et 12b" > "$snip/$f" 2>/dev/null; then
            chmod 644 "$snip/$f" 2>/dev/null || true
            echo "        $snip/$f était absent : créé vide pour que nginx -t réussisse (rempli par son étape : 12, 12b ou 12c)."
            cree=0
        fi
    done
    return "$cree"
}

# nginx_appliquer: applies a configuration that nginx -t has just accepted. Active service: reload; STOPPED service (configuration
# invalid at startup, manual stop...): start - a "systemctl reload" fails on a stopped service and the site stayed offline.
# Returns 0 if nginx runs with the new configuration. NGINX_APPLIQUE = "reloaded" or "started" (for the message).
NGINX_APPLIQUE=""
nginx_appliquer() {
    if run systemctl is-active --quiet nginx 2>/dev/null; then
        NGINX_APPLIQUE="rechargé"
        run systemctl reload nginx >/dev/null 2>&1
    else
        NGINX_APPLIQUE="démarré (il était arrêté)"
        run systemctl start nginx >/dev/null 2>&1
    fi
}

# creer_modele DESTINATION MODELE: creates the file (mode 644) from doc/MODELE shipped with the programs, otherwise a minimal header.
creer_modele() {
    local dest="$1" modele="$SCRIPT_DIR/doc/$2"
    mkdir -p "$(dirname "$dest")" 2>/dev/null || return 1
    if [[ -r "$modele" ]]; then cp "$modele" "$dest" 2>/dev/null || return 1
    else printf '# %s — voir doc/%s\n' "$(basename "$dest")" "$2" > "$dest" 2>/dev/null || return 1; fi
    chmod 644 "$dest"
}

# migrer_listes: the white list and the places live in /etc/default (outside the archives, publishable without personal data).
# --update: migrates the old list apps/team-ips.list (copied, then renamed .migre) or creates a template; existing files: never modified.
migrer_listes() {
    local blanche="${NGINX_TOOLS_WHITE_LIST:-$LISTES_BLANCHE_DEFAUT}" lieux="${NGINX_TOOLS_IP_LOCATION:-$LISTES_LIEUX_DEFAUT}"
    local ancien="$SCRIPT_DIR/apps/team-ips.list"
    if [[ -f "$blanche" ]]; then
        pass "Liste blanche : $blanche ($(listes_blanche | listes_valides | grep -c . || true) adresse(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        if [[ -f "$ancien" ]]; then warn "Liste blanche : ANCIEN emplacement $ancien — --update la migre vers $blanche."
        else warn "Liste blanche absente ($blanche) — --update crée un modèle à remplir (sans elle, aucune adresse n'a accès à la gestion des bases de DEV ni à LAB)."; fi
    elif [[ -f "$ancien" ]]; then
        if cp "$ancien" "$blanche" 2>/dev/null && chmod 644 "$blanche" && mv "$ancien" "$ancien.migre"; then
            pass "Liste blanche migrée : $ancien -> $blanche (l'ancien fichier est renommé .migre : il peut être supprimé)."
        else warn "Migration de $ancien vers $blanche impossible (droits ?) : la copier à la main."; fi
    elif creer_modele "$blanche" nginx-tools-white-list.conf.example; then
        warn "Liste blanche créée VIDE ($blanche) : y mettre les adresses de confiance (équipe), puis relancer --update."
    else
        warn "Liste blanche : impossible de créer $blanche (droits ?)."
    fi
    if [[ -f "$lieux" ]]; then
        pass "Lieux : $lieux ($(listes_lieux | listes_valides | grep -c . || true) plage(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Lieux : aucun fichier ($lieux) — facultatif ; --update crée un modèle (université, bureau : nom d'une plage, affiché par app-log-live.py)."
    elif creer_modele "$lieux" nginx-tools-ip-location.conf.example; then
        pass "Lieux : modèle créé ($lieux) : y décrire vos plages partagées (université…) — facultatif."
    fi
    while IFS= read -r probleme; do [[ -n "$probleme" ]] && warn "Listes : $probleme"; done < <(python3 "$SCRIPT_DIR/apps/_listes.py" --resume 2>/dev/null | sed -n 's/^  ATTENTION //p')
}

# Hardening of BigBlueButton (step 9): file OURS in /etc/bigbluebutton/nginx/ (included by BBB in its block
# server, never overwritten by its updates). Refuses ONLY URLs that BBB never serves; no location of
# BBB is modified (HTML5 client, API, WebRTC: proxy_buffering, timeouts and protocol upgrades intact).
generer_regles_bbb() {
    cat <<'EOF'
# GÉNÉRÉ par nginx-hardening.sh — NE PAS MODIFIER À LA MAIN (relancer nginx-hardening.sh --update).
# Règles de sécurité pour BigBlueButton : URL que BBB ne sert jamais (fichiers cachés, scripts PHP/CGI, WordPress…),
# refusées en 404 par nginx et journalisées dans blocked-probes.log (jail fail2ban nginx-blocked-probes).
location ~ /\.(?!well-known/) {
    access_log /var/log/nginx/blocked-probes.log;
    return 404;
}
location ~* \.(php[0-9]?|phtml|asp|aspx|jsp|cgi|env|bak|swp)$ {
    access_log /var/log/nginx/blocked-probes.log;
    return 404;
}
location ~* ^/(wp-admin|wp-login|wp-content|wp-includes|xmlrpc\.php|phpmyadmin|pma|cgi-bin|vendor/phpunit) {
    access_log /var/log/nginx/blocked-probes.log;
    return 404;
}
EOF
}
# Filtre et jail de nginx-blocked-probes : copie EXACTE (octet pour octet) de nginx-odoo/fail2ban/nginx-blocked-probes.
# {filter,jail}.conf, so that tests/run-all.sh (step 5, cmp) does not report a difference on a BBB server, where these
# files are not deployed and must be written here. A test checks identity with the shipped files.
filtre_blocked_probes() {
    cat <<'EOF'
# Filtre fail2ban : refus des règles de sécurité de nginx (securite-commune.conf : fichiers sensibles, .php, cadriciels,
# objets connectés, wp-*, graphql…), journalisés à part dans blocked-probes.log. Chaque ligne de ce journal est un
# refus CERTAIN : toute ligne compte (format combined_host, adresse en tête de ligne).
[Definition]
failregex = ^<HOST> - \S+ \[
ignoreregex =
EOF
}
jail_blocked_probes() {
    cat <<'EOF'
# Jail : un client qui accumule les refus des règles de sécurité (scanner de fichiers sensibles, de failles connues)
# est banni. Ces refus étaient invisibles de fail2ban (access_log off) jusqu'au journal dédié blocked-probes.log.
[nginx-blocked-probes]
enabled  = true
port     = http,https
filter   = nginx-blocked-probes
logpath  = /var/log/nginx/blocked-probes.log
maxretry = 5
findtime = 600
bantime  = 86400
action   = iptables-multiport[name=nginx-blocked-probes, port="http,https", protocol=tcp]
EOF
}
durcir_bbb() {
    local dir="${NGINX_HARDENING_BBB_NGINX_DIR:-/etc/bigbluebutton/nginx}" fichier contenu ancien="" tmp
    fichier="$dir/zz-nginx-hardening-security.nginx"
    contenu=$(generer_regles_bbb)
    if ! command -v nginx >/dev/null 2>&1; then
        warn "nginx introuvable — règles de sécurité BBB non vérifiées."
    elif ! run nginx -T 2>/dev/null | grep_q 'include /etc/bigbluebutton/nginx/\*\.nginx'; then
        warn "La configuration nginx de BBB n'inclut pas /etc/bigbluebutton/nginx/*.nginx — règles de sécurité non installées (à examiner)."
    elif [[ -f "$fichier" && "$(cat "$fichier")" == "$contenu" ]]; then
        pass "Règles de sécurité BBB à jour ($fichier)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Règles de sécurité BBB $([[ -f "$fichier" ]] && echo différentes || echo absentes) — --update les installera ($fichier : fichiers cachés, PHP/CGI, WordPress refusés en 404)."
    else
        [[ -f "$fichier" ]] && ancien=$(cat "$fichier")
        mkdir -p "$dir"; tmp=$(mktemp "$dir/.zz-nginx-hardening.XXXXXX")
        printf '%s\n' "$contenu" > "$tmp" && chmod 644 "$tmp" && mv -f "$tmp" "$fichier"
        if run nginx -t >/dev/null 2>&1; then
            nginx_appliquer || true
            pass "Règles de sécurité BBB installées ($fichier) ; nginx -t réussi, nginx rechargé."
        else
            if [[ -n "$ancien" ]]; then printf '%s\n' "$ancien" > "$fichier"; else rm -f "$fichier"; fi
            fail "nginx -t refuse les règles de sécurité BBB — ancienne version restaurée, nginx NON rechargé (nginx -t pour le détail)."
        fi
    fi
    # Jail nginx-blocked-probes (files written here: the nginx-odoo configuration is not deployed on BBB).
    if command -v fail2ban-client >/dev/null 2>&1; then
        if [[ -f /etc/fail2ban/jail.d/nginx-blocked-probes.conf && -f /etc/fail2ban/filter.d/nginx-blocked-probes.conf ]]; then
            pass "Jail nginx-blocked-probes : fichiers présents."
            F2B_INSTALLED_JAILS+=(nginx-blocked-probes)
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            warn "Jail nginx-blocked-probes absente — --update l'installera (bannit les clients qui accumulent les refus)."
        else
            mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d
            filtre_blocked_probes > /etc/fail2ban/filter.d/nginx-blocked-probes.conf
            jail_blocked_probes > /etc/fail2ban/jail.d/nginx-blocked-probes.conf
            [[ -e /var/log/nginx/blocked-probes.log ]] || { touch /var/log/nginx/blocked-probes.log; chown --reference=/var/log/nginx /var/log/nginx/blocked-probes.log 2>/dev/null || true; }
            pass "Jail nginx-blocked-probes installée (5 refus en 10 min → banni 24 h)."
            NEED_FAIL2BAN_RESTART=1
            F2B_INSTALLED_JAILS+=(nginx-blocked-probes)
        fi
    fi
}

# Defined here, with the utility functions: called by step 9 for Odoo AND for BigBlueButton.
verifier_ignoreip() {
    # --- 9c) ignoreip: team addresses (nginx $is_trusted_ip table AND white list + [protected] places of /etc/default/nginx-tools-*.conf) never banned by fail2ban. The lists
    # "allow" of nginx and "ignoreip" of fail2ban are INDEPENDENT: an address added to one is not added to
    # the other. Correction (--update) in a separate file, read last (jail.d/*.local), which TAKES OVER the addresses
    # already ignored: never a change to jail.local.
    f2b_equipe=$({ run nginx -T 2>/dev/null | awk '/^[[:space:]]*geo[[:space:]].*\$is_trusted_ip[[:space:]]*\{/ { dans = 1; next }
        dans && /^[[:space:]]*\}/ { dans = 0 } dans && $2 ~ /^1;/ && $1 != "127.0.0.1" && $1 != "::1" { print $1 }'; listes_ne_pas_bannir ; } | sort -u) || f2b_equipe=""
    f2b_jails=$(run fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr ',' ' ') || f2b_jails=""
    if [[ -n "$f2b_equipe" && -n "${f2b_jails// /}" ]]; then
        f2b_manquants=(); f2b_connues=""
        for j in $f2b_jails; do
            # VALID addresses only: IPv4 (possibly a range), IPv6 with at least two colons - never a piece of
            # text ("ignored:" would give "ed:"), which would make the fail2ban configuration unreadable.
            f2b_ign=$(run fail2ban-client get "$j" ignoreip 2>/dev/null | grep -oE '[0-9a-fA-F:.]+(/[0-9]+)?' \
                      | grep -xE '[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?|[0-9a-fA-F]*:[0-9a-fA-F]*:[0-9a-fA-F:]*(/[0-9]{1,3})?' || true)
            f2b_connues="$f2b_connues $f2b_ign"
            for ip in $f2b_equipe; do
                grep -qxF "$ip" <<< "$f2b_ign" || f2b_manquants+=("$j:$ip")
            done
        done
        if (( ${#f2b_manquants[@]} == 0 )); then
            pass "fail2ban : les $(wc -w <<< "$f2b_equipe") adresses de l'équipe (table \$is_trusted_ip de nginx) sont ignorées par toutes les jails."
        else
            f2b_ips=$(printf '%s\n' "${f2b_manquants[@]}" | cut -d: -f2- | sort -u | tr '\n' ' ')
            f2b_js=$(printf '%s\n' "${f2b_manquants[@]}" | cut -d: -f1 | sort -u | tr '\n' ' ')
            if [[ "$CHECK_ONLY" == "1" ]]; then
                warn "fail2ban : adresses de l'équipe NON ignorées (jails : ${f2b_js% }) : ${f2b_ips% } — --update les ajoutera (jail.d/zz-nginx-hardening-ignoreip.local)."
            else
                f2b_liste=$(tr ' ' '\n' <<< "127.0.0.1/8 ::1 $f2b_connues $f2b_equipe" | grep . | awk '!vu[$0]++' | tr '\n' ' ')
                mkdir -p /etc/fail2ban/jail.d 2>/dev/null || true
                printf '%s\n' "# Généré par nginx-hardening.sh : adresses de l'équipe (table \$is_trusted_ip de nginx) jamais bannies," \
                    "# plus les adresses déjà ignorées. Lu en dernier (jail.d/*.local) : complète jail.local sans le modifier." \
                    "[DEFAULT]" "ignoreip = ${f2b_liste% }" > /etc/fail2ban/jail.d/zz-nginx-hardening-ignoreip.local
                NEED_FAIL2BAN_RESTART=1
                pass "fail2ban : ignoreip complété (${f2b_ips% }) dans /etc/fail2ban/jail.d/zz-nginx-hardening-ignoreip.local — une jail qui définit son propre ignoreip reste à compléter à la main."
            fi
        fi
    fi
}

pass() { echo "  ${C_GREEN}[OK]${C_RESET}   $1"; PASS=$((PASS+1)); }
fail() { echo "  ${C_RED}[FAIL]${C_RESET} $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ${C_YELLOW}[ATTN]${C_RESET} $1"; WARN=$((WARN+1)); }
# 2.54: not as root (--check by default), iptables, ufw, fail2ban-client and nginx -t refuse to answer: the point is "unverified" (ATTN), never "absent" (FAIL).
sans_root_verif() { warn "$1 : non vérifié sans root (relancer avec sudo $0 --check)"; }

# --- BigBlueButton: state BEFORE / AFTER this pass (apps/_bbb.py) ---
# Versions (packages, Greenlight), fingerprint of BBB's configuration files and ours, compared to the snapshot
# of the last --update: a BBB update done in the meantime appears BEFORE; AFTER, the compatibility of our rules
# with BBB is checked (nginx -t, rules loaded, API and HTML5 client reachable, HAProxy HSTS, bbb-conf --check).
bbb_etat() {
    local ligne verb=()
    if [[ "$VERBOSE" == "1" ]]; then verb=(--verbose); fi          # --verbose is passed to the programs called
    while IFS= read -r ligne; do
        case "$ligne" in
            "[OK] "*)   pass "${ligne#\[OK\] }" ;;
            "[ATTN] "*) warn "${ligne#\[ATTN\] }" ;;
            "[FAIL] "*) fail "${ligne#\[FAIL\] }" ;;
            *)          echo "  $ligne" ;;
        esac
    done < <(timeout --foreground 400 python3 "$APPS_DIR/_bbb.py" ${verb[@]+"${verb[@]}"} "$@" 2>&1 || true)
}
# --- Sauvegardes (2.59) : une archive de la configuration nginx et fail2ban avant chaque --update ; --rollback la restaure ---
# Archive : $ARCHIVE_DIR/AAAAMMJJ-HHMMSS-MMM-ETIQUETTE.tar.gz, avec un fichier .txt (version, date, racines). Les BACKUP_KEEP plus
# récentes sont gardées. Non couverts : règles iptables, paquets installés, odoo.conf (jamais modifié par ce programme).
sauvegarde_elaguer() {    # keeps the BACKUP_KEEP most recent archives
    local f i=0
    local -a liste=()
    mapfile -t liste < <(find "$ARCHIVE_DIR" -maxdepth 1 -name '*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2- || true)
    for f in "${liste[@]}"; do
        i=$((i+1))
        if (( i > BACKUP_KEEP )); then rm -f "$f" "$f.txt"; fi
    done
}
sauvegarde_creer() {     # $1 label: prints the archive path; returns 1 if it could not be made
    local etiquette="$1" nom chemin racine
    local -a racines=()
    for racine in "${BACKUP_ROOTS[@]}"; do
        if [[ -e "$racine" ]]; then racines+=("${racine#/}"); fi
    done
    (( ${#racines[@]} > 0 )) || return 1
    mkdir -p "$ARCHIVE_DIR" || return 1
    chmod 700 "$ARCHIVE_DIR" || return 1
    nom="$(date +%Y%m%d-%H%M%S-%3N)-$etiquette"
    chemin="$ARCHIVE_DIR/$nom.tar.gz"
    if ! tar -czf "$chemin" -C / "${racines[@]}" 2>/dev/null; then rm -f "$chemin"; return 1; fi
    {
        echo "nginx-hardening.sh v$SCRIPT_VERSION"
        echo "date : $(date '+%Y-%m-%d %H:%M:%S %Z')"
        echo "etiquette : $etiquette"
        echo "racines : ${racines[*]}"
    } > "$chemin.txt"
    chmod 600 "$chemin" "$chemin.txt"
    sauvegarde_elaguer
    echo "$chemin"
}
archive_extraire() {     # $1 archive, $2 empty directory: extracts the archive there
    tar -xzf "$1" -C "$2"
}
archive_appliquer() {    # $1 extracted directory: puts every root of the archive back in place; nginx -t must pass, else nothing stays changed
    local tmp="$1" racine rel stamp
    local -a deplace=()
    stamp=$(date +%Y%m%d-%H%M%S-%3N)
    annuler() {
        for racine in "${deplace[@]}"; do
            rm -rf "$racine"
            mv "$racine.rollback-old-$stamp" "$racine"
        done
    }
    for racine in "${BACKUP_ROOTS[@]}"; do
        rel="${racine#/}"
        [[ -e "$tmp/$rel" ]] || continue
        if [[ -e "$racine" ]]; then
            if ! mv "$racine" "$racine.rollback-old-$stamp"; then annuler; return 1; fi
            deplace+=("$racine")
        fi
        mkdir -p "$(dirname "$racine")"
        if ! cp -a "$tmp/$rel" "$racine"; then annuler; return 1; fi
    done
    if command -v nginx >/dev/null 2>&1 && ! nginx -t >/dev/null 2>&1; then
        annuler
        return 1
    fi
    for racine in "${deplace[@]}"; do rm -rf "$racine.rollback-old-$stamp"; done
    return 0
}
rollback_executer() {    # --rollback: restores an archive (the newest by default, or --backup NAME), after confirmation
    local archive="" tmp="" rep="" avant="" racine
    if [[ "$EUID" -ne 0 ]]; then echo "ERREUR: --rollback nécessite root (sudo)." >&2; exit 1; fi
    if [[ -n "$ROLLBACK_BACKUP" ]]; then
        if [[ "$ROLLBACK_BACKUP" == */* ]]; then echo "ERREUR: --backup prend un nom, pas un chemin." >&2; exit 1; fi
        archive="$ARCHIVE_DIR/$ROLLBACK_BACKUP"
        [[ -f "$archive" ]] || archive="$ARCHIVE_DIR/$ROLLBACK_BACKUP.tar.gz"
    else
        archive=$(find "$ARCHIVE_DIR" -maxdepth 1 -name '*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n 1 | cut -d' ' -f2- || true)
    fi
    if [[ -z "$archive" || ! -f "$archive" ]]; then
        echo "Aucune sauvegarde trouvée dans $ARCHIVE_DIR (--backup NAME pour une autre)." >&2
        exit 1
    fi
    echo "--- Restauration de la sauvegarde : $archive ---"
    if [[ -r "$archive.txt" ]]; then sed 's/^/  /' "$archive.txt"; fi
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/nh-rollback.XXXXXX")
    if ! archive_extraire "$archive" "$tmp"; then rm -rf "$tmp"; echo "ERREUR: archive illisible : $archive" >&2; exit 1; fi
    echo "  Différences avec l'état actuel (30 premières lignes) :"
    for racine in "${BACKUP_ROOTS[@]}"; do
        if [[ -e "$tmp/${racine#/}" ]]; then diff -rq "$tmp/${racine#/}" "$racine" 2>/dev/null || true; fi
    done | head -n 30 | sed 's/^/      /' || true
    if [[ "$ROLLBACK_YES" != "1" ]]; then
        if [[ -t 0 ]]; then read -r -p "  Restaurer cette sauvegarde ? L'état actuel est sauvegardé d'abord. [o/N] " rep || rep=""
        else echo "Pas de terminal : rien restauré (ajouter --yes pour confirmer sans question)." >&2; rm -rf "$tmp"; exit 1; fi
        if [[ ! "$rep" =~ ^[oOyY]$ ]]; then echo "Annulé : rien restauré."; rm -rf "$tmp"; exit 0; fi
    fi
    if ! avant=$(sauvegarde_creer avant-rollback); then
        rm -rf "$tmp"; fail "Sauvegarde préalable impossible : rien restauré."; exit 1
    fi
    echo "  État actuel sauvegardé : $avant"
    if archive_appliquer "$tmp"; then
        rm -rf "$tmp"
        if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then systemctl reload nginx || true; fi
        if command -v fail2ban-client >/dev/null 2>&1; then fail2ban-client reload >/dev/null 2>&1 || true; fi
        pass "Sauvegarde restaurée (nginx -t réussit). Retour arrière : --rollback --backup $(basename "$avant" .tar.gz)"
        warn "Non restaurés : règles iptables, paquets installés, odoo.conf."
        exit 0
    fi
    rm -rf "$tmp"
    fail "Restauration annulée : nginx -t refuse la sauvegarde ou une copie a échoué ; l'état actuel est conservé."
    exit 1
}

# --- Sauvegarde avant --update ou restauration (--rollback) ---
if [[ "$ROLLBACK" == "1" ]]; then
    rollback_executer
fi
if [[ "$CHECK_ONLY" == "0" ]]; then
    echo "--- Sauvegarde de la configuration avant modification ---"
    if ! SAUVEGARDE_UPDATE=$(sauvegarde_creer update); then
        fail "Sauvegarde impossible dans $ARCHIVE_DIR : aucune modification faite."
        exit 1
    fi
    pass "Sauvegarde : $SAUVEGARDE_UPDATE (restauration : --rollback)"
    echo
fi

BBB_ETAT=0
if [[ "$APP_NAME" == "bbb" && -r "$APPS_DIR/_bbb.py" ]] && command -v python3 >/dev/null 2>&1; then
    BBB_ETAT=1
    echo "--- BigBlueButton AVANT ce passage : versions et configuration, changements depuis le dernier --update ---"
    bbb_etat --before
    echo
fi

# --- 0) Required programs: installed by --update if missing (apt) ---
# paquet_installer COMMAND PACKAGE: COMMAND absent => check only: warns; --update: apt-get install, then rechecks.
paquet_installer() {
    local cmd="$1" paquet="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd présent (paquet $paquet)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "$cmd absent (paquet $paquet) — relancer avec --update pour l'installer."
    elif ! command -v apt-get >/dev/null 2>&1; then
        warn "$cmd absent et apt-get introuvable — installez le paquet $paquet avec le gestionnaire de paquets de cette distribution."
    elif DEBIAN_FRONTEND=noninteractive run apt-get install -y "$paquet" >/dev/null 2>&1 && command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd installé (paquet $paquet)."
    else
        fail "installation du paquet $paquet en échec — lancer « apt-get install $paquet » et lire l'erreur."
    fi
}
echo "--- 0) Programmes requis (ss, curl, logrotate, fail2ban) ---"
paquet_installer ss iproute2
paquet_installer curl curl
paquet_installer logrotate logrotate
paquet_installer fail2ban-client fail2ban
echo

# --- 0a) nginx BEFORE my changes: "nginx -t" and the service state, with help to fix ---
# A problem already present (certificate not found, cache directory absent, unknown directive, port in use...) is reported HERE, with the file and the lines involved, and
# the steps to follow, so that a refusal of nginx later is not attributed to this script's changes. Nothing is changed by this step.
nginx_aide() {      # nginx_aide MESSAGE: advice from the "nginx -t" message (one line per recognized cause)
    local m="$1" fic lig
    if grep -Eqi 'cannot load certificate|BIO_new_file|SSL_CTX_use_(PrivateKey|certificate)' <<<"$m"; then
        echo "        Que faire : un certificat ou une clé est introuvable ou illisible. Si le nom DNS a changé : $0 --update --rename-to NOUVEAU_NOM (refait nginx et le certificat) ; sinon « certbot certificates » puis « certbot renew »."
    fi
    if grep -Eqi 'open\(\) .* failed \(2: No such file|No such file or directory' <<<"$m"; then
        if grep -Eq '(team-ips-(geo|allow)|shared-ips-geo)\.conf' <<<"$m"; then
            echo "        Que faire : ce fragment est GÉNÉRÉ par ce script depuis /etc/default/nginx-tools-*.conf : $0 --update le crée (vide au besoin), régénère les adresses et recharge (ou démarre) nginx."
        else
            echo "        Que faire : un fichier ou un dossier mentionné par nginx n'existe pas (cache, journal, include). Les dossiers de cache sont créés par $0 --update (étape 0c) ; sinon créer le fichier ou retirer la ligne."
        fi
    fi
    if grep -Eqi 'unknown directive|unknown "' <<<"$m"; then
        echo "        Que faire : directive inconnue de cette installation de nginx : module absent (ex. GeoIP : apt install libnginx-mod-http-geoip) ou faute de frappe dans la ligne indiquée."
    fi
    if grep -Eqi 'Address already in use|bind\(\)' <<<"$m"; then
        echo "        Que faire : un port est déjà pris par un autre programme : ss -ltnp | grep ':80\|:443' (un autre nginx, Apache, Docker…), l'arrêter ou changer le port."
    fi
    if grep -Eqi 'host not found in upstream' <<<"$m"; then
        echo "        Que faire : le nom d'un serveur amont (upstream/proxy_pass) ne se résout pas : mettre 127.0.0.1 ou corriger le nom."
    fi
    if grep -Eqi 'duplicate|conflicting|already bound|is already defined' <<<"$m"; then
        echo "        Que faire : définition en double (upstream, zone, location ou serveur par défaut) : garder une seule définition ; grep -rn le nom dans /etc/nginx/."
    fi
    if grep -Eqi 'hash_bucket_size|hash_max_size' <<<"$m"; then
        echo "        Que faire : augmenter server_names_hash_bucket_size (64 puis 128) dans nginx.conf, bloc http."
    fi
    fic=$(grep -Eo 'in /[^ :]+:[0-9]+' <<<"$m" | head -n 1 | sed 's/^in //') || fic=""
    if [[ -n "$fic" ]]; then
        lig="${fic##*:}"; fic="${fic%:*}"
        if [[ -r "$fic" ]]; then
            echo "        Lignes en cause ($fic, ligne $lig) :"
            sed -n "$((lig > 2 ? lig - 2 : 1)),$((lig + 2))p" "$fic" 2>/dev/null | sed 's/^/          | /'
        fi
    fi
}
echo "--- 0a) nginx avant les changements (nginx -t, service) ---"
if ! command -v nginx >/dev/null 2>&1; then
    warn "nginx absent (commande introuvable) : le reste du setup ne peut pas vérifier ni recharger nginx."
else
    # --update: the fragments GENERATED by this script (steps 12 and 12b) are not an "already present problem": if missing, they are created empty BEFORE the test.
    fragments_generes_assurer && pass "Fragments générés absents créés vides (remplis aux étapes 12 et 12b) : nginx -t peut tester le reste de la configuration."
    nx_code=0; nx_sortie=$(run nginx -t 2>&1) || nx_code=$?
    nx_actif=$(systemctl is-active nginx 2>/dev/null) || nx_actif="inconnu"
    if (( nx_code == 0 )); then
        pass "nginx -t : la configuration est valide avant les changements de ce script."
    elif [[ "$EUID" -ne 0 ]] && grep -Eqi 'Permission denied|Operation not permitted|must be root' <<<"$nx_sortie"; then
        sans_root_verif "nginx -t (configuration)"
    else
        fail "nginx -t REFUSE la configuration AVANT tout changement de ce script (problème déjà présent, à corriger) :"
        printf '%s\n' "$nx_sortie" | head -n 8 | sed 's/^/        nginx -t : /'
        nginx_aide "$nx_sortie"
        echo "        Après correction : nginx -t && systemctl reload nginx, puis relancer ce script. Les étapes qui modifient nginx restaurent leurs fichiers si nginx -t refuse, mais ne réparent pas ce problème."
    fi
    if [[ "$nx_actif" != "active" ]]; then
        warn "Le service nginx n'est pas actif (état : $nx_actif) : systemctl status nginx --no-pager ; journalctl -u nginx -n 30 --no-pager$( (( nx_code == 0 )) && { [[ "$CHECK_ONLY" == "1" ]] && echo " ; --update le démarre si nginx -t réussit" || echo " ; il sera démarré par la première étape qui applique la configuration (nginx -t d'abord)"; } )."
    fi
fi

# --- 0b) Server time zone (default: America/Montreal; --timezone, TIMEZONE; "none": change nothing) ---
# The first time (TIMEZONE absent from all the configuration files), --update asks in a terminal; the answer is kept in /etc/default/nginx-hardening.conf
# (TIMEZONE=... line). Without a terminal: the default is applied.
echo "--- 0b) Fuseau horaire ---"
TIMEZONE_A_ENREGISTRER=""
if [[ "$TIMEZONE" == "none" ]]; then
    sans_objet "fuseau horaire laissé tel quel (TIMEZONE=none)"
elif ! command -v timedatectl >/dev/null 2>&1; then
    warn "timedatectl introuvable — fuseau horaire non vérifié (souhaité : ${TIMEZONE:-$TIMEZONE_DEFAUT})."
else
    tz_voulu="${TIMEZONE:-$TIMEZONE_DEFAUT}"
    tz_actuel=$(run timedatectl show -p Timezone --value 2>/dev/null) || tz_actuel=""
    if [[ ! -e "${NGINX_HARDENING_ZONEINFO:-/usr/share/zoneinfo}/$tz_voulu" ]]; then
        warn "Fuseau horaire « $tz_voulu » inconnu de ce système (/usr/share/zoneinfo) — précisez --timezone ZONE (liste : timedatectl list-timezones)."
    elif [[ "$tz_actuel" == "$tz_voulu" ]]; then
        pass "Fuseau horaire : $tz_actuel."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Fuseau horaire : $tz_actuel (souhaité : $tz_voulu) — relancer avec --update pour le régler."
    else
        reponse="o"
        if [[ -z "$TIMEZONE" && -t 0 && -t 2 ]]; then
            read -r -p "  Régler le fuseau horaire du serveur à $tz_voulu (actuel : ${tz_actuel:-inconnu}) ? [O/n/autre zone] " reponse || reponse="o"
            case "$reponse" in
                ""|[oOyY]*) reponse="o" ;;
                [nN]*) reponse="n" ;;
                *) tz_voulu="$reponse"; reponse="o" ;;
            esac
        fi
        if [[ "$reponse" == "n" ]]; then
            TIMEZONE_A_ENREGISTRER="none"
            pass "Fuseau horaire laissé à $tz_actuel (choix mémorisé : TIMEZONE=none)."
        elif run timedatectl set-timezone "$tz_voulu" >/dev/null 2>&1; then
            [[ -z "$TIMEZONE" ]] && TIMEZONE_A_ENREGISTRER="$tz_voulu"
            pass "Fuseau horaire réglé à $tz_voulu (avant : ${tz_actuel:-inconnu})."
        else
            warn "Réglage du fuseau horaire à $tz_voulu en échec — lancer « timedatectl set-timezone $tz_voulu » et lire l'erreur."
        fi
    fi
fi
echo

# --- 0c) nginx cache directories (proxy_cache_path): nginx refuses to start if the directory does not exist ---
echo "--- 0c) Dossiers de cache nginx (proxy_cache_path) ---"
if ! command -v nginx >/dev/null 2>&1; then
    sans_objet "nginx absent"
else
    cache_dossiers=$(grep -rhE '^[[:space:]]*proxy_cache_path[[:space:]]+/' /etc/nginx 2>/dev/null | sed -E 's/^[[:space:]]*proxy_cache_path[[:space:]]+([^[:space:];]+).*/\1/' | sort -u) || cache_dossiers=""
    cache_proprio=$(grep -hE '^[[:space:]]*user[[:space:]]+[a-z_-]+' /etc/nginx/nginx.conf 2>/dev/null | head -1 | awk '{gsub(/;/,"",$2); print $2}') || cache_proprio=""
    cache_proprio="${cache_proprio:-www-data}"
    if [[ -z "$cache_dossiers" ]]; then
        pass "Aucun proxy_cache_path dans la configuration nginx."
    fi
    while IFS= read -r cache_dir; do
        [[ -n "$cache_dir" ]] || continue
        if [[ -d "$cache_dir" ]]; then
            pass "$cache_dir existe déjà."
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "$cache_dir n'existe pas : nginx -t refuse la configuration (relancer avec --update pour le créer)."
        elif run install -d -m 0750 -o "$cache_proprio" -g "$cache_proprio" "$cache_dir" 2>/dev/null; then
            pass "$cache_dir créé (propriétaire $cache_proprio)."
        else
            fail "Impossible de créer $cache_dir (propriétaire $cache_proprio) — à faire à la main : install -d -o $cache_proprio -g $cache_proprio $cache_dir"
        fi
    done <<< "$cache_dossiers"
fi
echo

# --- 0d) Courriel des programmes Python et Bash : relais SMTP, logiciels (msmtp), configuration commune --------------------------
# The parameters (host, port, encryption, login, sender, recipient) are kept in /etc/default/nginx-tools-mail.conf; the PASSWORD
# is in /etc/default/nginx-tools-mail.pass (mode 0600, root), never in the configuration file, never displayed, never in an email or a report.
# The Python programs use apps/_courriel.py; Bash (sendmail, mail) goes through msmtp, configured in /etc/msmtprc from the same file.
echo "--- 0d) Courriel des programmes (relais SMTP, msmtp, configuration commune) ---"
MAIL_CONF="${NGINX_TOOLS_MAIL_CONF:-/etc/default/nginx-tools-mail.conf}"
MAIL_PASS="${NGINX_TOOLS_MAIL_PASSWORD_FILE:-/etc/default/nginx-tools-mail.pass}"
MSMTPRC="${NGINX_TOOLS_MSMTPRC:-/etc/msmtprc}"
mail_valeur() { if [[ -r "$MAIL_CONF" ]]; then sed -nE "s/^$1=\"?([^\"]*)\"?[[:space:]]*(#.*)?$/\1/p" "$MAIL_CONF" | tail -1; fi; return 0; }
# Software: msmtp (sending), sendmail (msmtp-mta, unless another mail server is already installed), mail (bsd-mailx).
paquet_installer msmtp msmtp
if [[ -x /usr/sbin/sendmail || -x /usr/lib/sendmail ]] || command -v sendmail >/dev/null 2>&1; then
    pass "sendmail présent (commande sendmail des programmes Bash)."
elif [[ "$CHECK_ONLY" == "1" ]]; then
    warn "sendmail absent (paquet msmtp-mta) — relancer avec --update pour l'installer."
elif DEBIAN_FRONTEND=noninteractive run apt-get install -y msmtp-mta >/dev/null 2>&1; then
    pass "msmtp-mta installé (commande sendmail)."
else
    fail "installation du paquet msmtp-mta en échec — lancer « apt-get install msmtp-mta » et lire l'erreur."
fi
paquet_installer mail bsd-mailx
# Valeurs : option ou fichier de configuration du setup, sinon fichier commun existant, sinon (avec --update, dans un terminal) on demande.
for mail_cle in HOST PORT SECURITY USER FROM TO; do
    mail_var="MAIL_$mail_cle"
    [[ -n "${!mail_var}" ]] || printf -v "$mail_var" '%s' "$(mail_valeur "$mail_var")"
done
mail_deja=0; [[ -n "$MAIL_HOST" && -r "$MAIL_PASS" ]] && mail_deja=1
mail_demander() {      # mail_demander VARIABLE "question" [default]: sets the answer (or the default); without a terminal, keeps the value
    local nom="$1" question="$2" defaut="${3:-}" reponse=""
    [[ -n "${!nom}" ]] && return 0
    if mail_terminal; then
        read -r -p "  $question${defaut:+ [$defaut]} : " reponse || reponse=""
    fi
    printf -v "$nom" '%s' "${reponse:-$defaut}"
}
mail_terminal() { [[ -t 0 && -t 2 ]]; }       # questions asked on the terminal (standard input and error): also works with "| tee journal" (redirected output)
mail_valide() { [[ "$1" != *[\"\$\`\\]* && "$1" != *$'\n'* ]]; }
mail_non=0      # "no" answer (default) to the question: the SMTP setup is skipped for this run
if [[ "$CHECK_ONLY" != "1" ]] && ! (( mail_deja && ! MAIL_SETUP )) && (( ! MAIL_SETUP )) && [[ -z "$MAIL_HOST" && -z "${NGINX_TOOLS_MAIL_PASSWORD:-}" ]] && mail_terminal; then
    read -r -p "  Faire le setup du courriel (relais SMTP) maintenant ? [o/N] : " mail_rep || mail_rep=""
    case "${mail_rep,,}" in o|oui|y|yes) ;; *) mail_non=1 ;; esac
fi
if [[ "$CHECK_ONLY" == "1" ]]; then
    if (( mail_deja )); then
        pass "Courriel configuré : $MAIL_HOST:${MAIL_PORT:-587} (${MAIL_SECURITY:-starttls}), expéditeur ${MAIL_FROM:-$MAIL_USER}, destinataire ${MAIL_TO:-non défini}."
    else
        warn "Courriel non configuré ($MAIL_CONF et $MAIL_PASS) — relancer avec --update dans un terminal : le relais SMTP et le mot de passe sont demandés une fois."
    fi
elif (( mail_deja && ! MAIL_SETUP )); then
    pass "Courriel déjà configuré : $MAIL_HOST:${MAIL_PORT:-587} (--mail-setup pour le redemander)."
elif (( mail_non )); then
    warn "Courriel : setup reporté (réponse non) — relancer avec --update et répondre o, ou avec --mail-setup."
else
    if mail_terminal; then
        echo "  Configuration du courriel des programmes (demandée une seule fois) : Entrée garde la valeur entre crochets."
        echo "  Les réponses vont dans $MAIL_CONF (sans mot de passe) ; le mot de passe va seul dans $MAIL_PASS (mode 0600, jamais affiché)."
    else
        echo "  Aucun terminal pour poser les questions du courriel (entrée non interactive) : relancer dans un terminal, ou passer --mail-host et --mail-user (mot de passe : variable NGINX_TOOLS_MAIL_PASSWORD)."
    fi
    mail_demander MAIL_HOST "Serveur SMTP (relais)" ""
    mail_demander MAIL_PORT "Port" "587"
    mail_demander MAIL_SECURITY "Chiffrement (starttls, ssl ou none)" "starttls"
    mail_demander MAIL_USER "Nom d'utilisateur" ""
    mail_demander MAIL_FROM "Adresse d'expéditeur" "$MAIL_USER"
    mail_demander MAIL_TO "Adresse de destination des courriels de la suite" "$MAIL_FROM"
    mail_mdp="${NGINX_TOOLS_MAIL_PASSWORD:-}"
    if [[ -z "$mail_mdp" && -n "$MAIL_HOST" ]] && mail_terminal; then
        read -r -s -p "  Mot de passe de $MAIL_USER (aucun écho, gardé dans $MAIL_PASS en mode 0600) : " mail_mdp || mail_mdp=""
        echo
    fi
    if [[ -z "$MAIL_HOST" || -z "$MAIL_USER" ]]; then
        warn "Courriel non configuré : serveur SMTP ou identifiant manquant — relancer avec --update dans un terminal (ou --mail-host et --mail-user)."
    elif [[ -z "$mail_mdp" && ! -r "$MAIL_PASS" ]]; then
        warn "Courriel non configuré : mot de passe manquant — relancer avec --update dans un terminal (ou variable NGINX_TOOLS_MAIL_PASSWORD)."
    elif ! [[ "$MAIL_PORT" =~ ^[0-9]+$ ]] || [[ ! "$MAIL_SECURITY" =~ ^(starttls|ssl|none)$ ]]; then
        fail "Courriel : port numérique et chiffrement starttls, ssl ou none attendus (reçus : « $MAIL_PORT », « $MAIL_SECURITY »)."
    elif ! mail_valide "$MAIL_HOST$MAIL_USER$MAIL_FROM$MAIL_TO" || ! mail_valide "$mail_mdp"; then
        fail "Courriel : guillemets, \$, accent grave, barre oblique inverse et retour à la ligne refusés dans les réponses (fichiers de configuration)."
    else
        mkdir -p "$(dirname "$MAIL_CONF")" 2>/dev/null || true
        mail_tmp=$(umask 077; mktemp "$MAIL_CONF.XXXXXX") || mail_tmp=""
        if [[ -z "$mail_tmp" ]]; then
            fail "Courriel : écriture impossible dans $(dirname "$MAIL_CONF")."
        else
            {
                echo "# Généré par nginx-hardening.sh (étape 0d) — courriel des programmes Python et Bash. AUCUN mot de passe ici : il est dans $MAIL_PASS."
                echo "MAIL_HOST=\"$MAIL_HOST\""
                echo "MAIL_PORT=\"$MAIL_PORT\""
                echo "MAIL_SECURITY=\"$MAIL_SECURITY\""
                echo "MAIL_USER=\"$MAIL_USER\""
                echo "MAIL_FROM=\"$MAIL_FROM\""
                echo "MAIL_TO=\"$MAIL_TO\""
                echo "MAIL_PASSWORD_FILE=\"$MAIL_PASS\""
                echo "# Pièce jointe plus grosse que cette taille (Mo) : remplacée par un lien (copie dans MAIL_LINK_DIR ; MAIL_LINK_URL = adresse publique de ce dossier)."
                echo "MAIL_ATTACH_MAX_MB=\"$(mail_valeur MAIL_ATTACH_MAX_MB || true)\""
                echo "MAIL_LINK_DIR=\"$(mail_valeur MAIL_LINK_DIR || true)\""
                echo "MAIL_LINK_URL=\"$(mail_valeur MAIL_LINK_URL || true)\""
                echo "MAIL_LINK_DAYS=\"$(mail_valeur MAIL_LINK_DAYS || true)\""
            } > "$mail_tmp"
            sed -i -E 's/^MAIL_ATTACH_MAX_MB=""$/MAIL_ATTACH_MAX_MB="100"/; s/^MAIL_LINK_DIR=""$/MAIL_LINK_DIR="\/var\/lib\/nginx-tools\/pieces-jointes"/; s/^MAIL_LINK_DAYS=""$/MAIL_LINK_DAYS="30"/' "$mail_tmp"
            chmod 0644 "$mail_tmp" && mv "$mail_tmp" "$MAIL_CONF"          # sans secret : lisible par les programmes
            if [[ -n "$mail_mdp" ]]; then
                mail_tmp=$(umask 077; mktemp "$MAIL_PASS.XXXXXX")
                printf '%s\n' "$mail_mdp" > "$mail_tmp"
                chmod 0600 "$mail_tmp" && mv "$mail_tmp" "$MAIL_PASS"
            fi
            chmod 0600 "$MAIL_PASS" 2>/dev/null || true
            pass "Courriel configuré : $MAIL_CONF (sans mot de passe) et $MAIL_PASS (mode 0600)."
            # msmtp (sendmail and mail of the Bash programs): /etc/msmtprc, unless it exists and was not created here.
            if [[ -e "$MSMTPRC" ]] && ! grep -q "nginx-hardening.sh" "$MSMTPRC" 2>/dev/null; then
                warn "$MSMTPRC existe et n'a pas été créé par ce programme — laissé tel quel (copie de la configuration à y reporter : hôte $MAIL_HOST, port $MAIL_PORT, utilisateur $MAIL_USER)."
            else
                case "$MAIL_SECURITY" in
                    ssl) mail_tls="tls on
tls_starttls off" ;;
                    none) mail_tls="tls off" ;;
                    *) mail_tls="tls on
tls_starttls on" ;;
                esac
                mail_tmp=$(umask 077; mktemp "$MSMTPRC.XXXXXX")
                {
                    echo "# Généré par nginx-hardening.sh (étape 0d) — sans mot de passe : lu dans $MAIL_PASS."
                    echo "defaults"
                    echo "auth on"
                    echo "$mail_tls"
                    echo "tls_trust_file /etc/ssl/certs/ca-certificates.crt"
                    echo "account default"
                    echo "host $MAIL_HOST"
                    echo "port $MAIL_PORT"
                    echo "from ${MAIL_FROM:-$MAIL_USER}"
                    echo "user $MAIL_USER"
                    echo "passwordeval cat $MAIL_PASS"
                    echo "set_from_header on"
                } > "$mail_tmp"
                chmod 0644 "$mail_tmp" && mv "$mail_tmp" "$MSMTPRC"
                pass "$MSMTPRC écrit (commandes sendmail et mail des programmes Bash)."
            fi
            if mail_terminal; then
                read -r -p "  Envoyer un courriel de test à $MAIL_TO maintenant ? [O/n] " mail_rep || mail_rep="n"
                case "$mail_rep" in
                    [nN]*) ;;
                    *)  if mail_sortie=$(timeout --foreground 60 python3 "$SCRIPT_DIR/apps/_courriel.py" --test 2>&1); then pass "Courriel de test envoyé à $MAIL_TO."
                        else fail "Courriel de test refusé : $mail_sortie"; fi ;;
                esac
            else
                echo "  Courriel de test : python3 $SCRIPT_DIR/apps/_courriel.py --test"
            fi
        fi
    fi
fi
echo "  Entrées DNS exactes à créer (SPF, DMARC, DKIM) : étape 13 ci-dessous ; guide : doc/courriel-securise.md."
echo

# --- 0e) Changement de nom DNS public (ex. odoo-lab.exemple.org -> odoo.exemple.org) : nginx et certificat Let's Encrypt -------------
# --rename-from OLD --rename-to NEW. Without --update: report of what would be changed. With --update: backup of the nginx files touched, names replaced
# (server_name, redirects...), certificate for the new name obtained with certbot (webroot /var/www/letsencrypt) if it does not exist, certificate paths replaced,
# "nginx -t" then reload; if nginx refuses, everything is restored. Odoo (web.base.url, dbfilter) and DNS are never modified: reminders displayed.
echo "--- 0e) Changement de nom DNS (nginx et Let's Encrypt) ---"
renom_valide() { [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]]; }
renom_fichiers() {      # real files (no duplicate) of nginx that mention the old name (whole name, not a subdomain)
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f reel vus=" "
    for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do
        [[ -f "$f" ]] || continue
        reel=$(readlink -f "$f" 2>/dev/null) || reel="$f"
        [[ "$vus" == *" $reel "* ]] && continue
        vus+="$reel "
        grep -Eq "(^|[^A-Za-z0-9._-])${RENAME_FROM//./\\.}([^A-Za-z0-9._-]|\$)" "$reel" && echo "$reel"
    done
    return 0
}
renom_candidats() {     # noms de domaine complets des directives server_name de nginx (sans doublon, sans le nouveau nom) : les anciens noms possibles
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f mot
    for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do
        [[ -f "$f" ]] || continue
        sed -n -E 's/^[[:space:]]*server_name[[:space:]]+([^;]*);.*/\1/p' "$f" 2>/dev/null
    done | tr -s ' \t' '\n' | while IFS= read -r mot; do
        renom_valide "$mot" && [[ "$mot" != "$RENAME_TO" ]] && echo "$mot"
    done | sort -u
    return 0
}
# Only the NEW name is given: the old one is searched in nginx server_name entries (one name of the same domain: kept; several: asked in a terminal).
if [[ -z "$RENAME_FROM" && -n "$RENAME_TO" ]] && renom_valide "$RENAME_TO"; then
    mapfile -t rn_cands < <(renom_candidats)
    rn_domaine="${RENAME_TO#*.}"; rn_memes=()
    for rn_c in "${rn_cands[@]}"; do [[ "${rn_c#*.}" == "$rn_domaine" ]] && rn_memes+=("$rn_c"); done
    (( ${#rn_memes[@]} > 0 )) && rn_cands=("${rn_memes[@]}")
    if (( ${#rn_cands[@]} == 1 )); then
        RENAME_FROM="${rn_cands[0]}"
        echo "  Ancien nom (--rename-from non donné) : $RENAME_FROM, seul nom de domaine trouvé dans les server_name de nginx."
    elif (( ${#rn_cands[@]} > 1 )); then
        echo "  Noms trouvés dans les server_name de nginx : ${rn_cands[*]}"
        if [[ "$CHECK_ONLY" != "1" ]] && mail_terminal; then
            read -r -p "  Ancien nom à remplacer par $RENAME_TO : " RENAME_FROM || RENAME_FROM=""
        fi
        [[ -n "$RENAME_FROM" ]] || warn "Plusieurs anciens noms possibles : préciser lequel avec --rename-from NOM."
    else
        warn "Aucun nom de domaine trouvé dans les server_name de nginx : préciser l'ancien nom avec --rename-from NOM."
    fi
fi
if [[ -z "$RENAME_FROM" && -z "$RENAME_TO" ]]; then
    echo "  [--]   Aucun changement de nom demandé (--rename-from ANCIEN --rename-to NOUVEAU, avec --update pour l'appliquer)."
elif ! renom_valide "$RENAME_FROM" || ! renom_valide "$RENAME_TO"; then
    if [[ -z "$RENAME_FROM" ]]; then
        fail "Changement de nom : l'ancien nom est introuvable ou ambigu — relancer avec --rename-from ANCIEN --rename-to $RENAME_TO."
    else
        fail "Changement de nom : deux noms de domaine complets sont attendus (reçus : « $RENAME_FROM » et « $RENAME_TO »)."
    fi
elif [[ "$RENAME_FROM" == "$RENAME_TO" ]]; then
    fail "Changement de nom : l'ancien et le nouveau nom sont identiques ($RENAME_TO)."
else
    rn_le="${NGINX_HARDENING_LETSENCRYPT_DIR:-/etc/letsencrypt}"
    rn_cert="$rn_le/live/$RENAME_TO/fullchain.pem"
    rn_ancien_re="${RENAME_FROM//./\\.}"
    rn_limite='(^|[^A-Za-z0-9._-])'"$rn_ancien_re"'([^A-Za-z0-9._-]|$)'
    mapfile -t rn_fichiers < <(renom_fichiers)
    rn_cert_ok=0
    if [[ -r "$rn_cert" ]]; then
        rn_cert_ok=1
        if command -v openssl >/dev/null 2>&1 && ! openssl x509 -in "$rn_cert" -noout -checkhost "$RENAME_TO" 2>/dev/null | grep -q "does match"; then rn_cert_ok=0; fi
    fi
    rn_dns=$(getent hosts "$RENAME_TO" 2>/dev/null | awk 'NR==1{print $1}') || rn_dns=""
    if (( ${#rn_fichiers[@]} == 0 )); then
        warn "Changement de nom : aucun fichier nginx (sites-enabled/, conf.d/) ne mentionne $RENAME_FROM — rien à remplacer."
    else
        echo "  Fichiers nginx qui mentionnent $RENAME_FROM : ${rn_fichiers[*]}"
    fi
    if (( rn_cert_ok )); then
        pass "Certificat de $RENAME_TO déjà présent et valide pour ce nom ($rn_cert)."
    elif [[ -z "$rn_dns" ]]; then
        warn "Le nom $RENAME_TO n'existe pas encore dans le DNS : Let's Encrypt refusera le certificat. Créer chez le fournisseur du domaine un enregistrement A (et AAAA si IPv6) $RENAME_TO vers l'adresse IP de CE serveur, attendre la propagation, puis relancer."
    else
        echo "  Le nom $RENAME_TO pointe vers $rn_dns : vérifier que c'est bien l'adresse IP de CE serveur (sinon Let's Encrypt échouera)."
    fi
    if [[ "$CHECK_ONLY" == "1" ]]; then
        if (( ${#rn_fichiers[@]} > 0 )); then
            warn "Changement de nom $RENAME_FROM → $RENAME_TO à faire : relancer avec --update (sauvegarde, remplacement dans nginx, certificat de $RENAME_TO réutilisé s'il existe, sinon demandé à Let's Encrypt, nginx -t, rechargement)."
        fi
    elif (( ${#rn_fichiers[@]} > 0 )); then
        rn_sauv="${NGINX_HARDENING_BACKUP_DIR:-/var/backups/nginx-hardening}"
        mkdir -p "$rn_sauv" 2>/dev/null || true
        rn_stamp=$(date +%Y%m%d-%H%M%S); rn_copies=(); rn_ok=1
        for rn_f in "${rn_fichiers[@]}"; do
            rn_c="$rn_sauv/$(basename "$rn_f").$rn_stamp.bak"
            if cp -p "$rn_f" "$rn_c" 2>/dev/null; then rn_copies+=("$rn_c"); else rn_ok=0; fail "Changement de nom : copie de sauvegarde de $rn_f impossible — rien n'est modifié."; break; fi
        done
        renom_restaurer() { local i; for i in "${!rn_fichiers[@]}"; do cp -p "${rn_copies[$i]}" "${rn_fichiers[$i]}" 2>/dev/null || true; done; }
        if (( rn_ok )); then
            # Phase 1: the name (server_name, redirects...); certificate paths (letsencrypt/live|archive/OLD) stay as they are for now.
            for rn_f in "${rn_fichiers[@]}"; do
                sed -i -E "\#letsencrypt/(live|archive)/${rn_ancien_re}([^A-Za-z0-9._-]|\$)#!{s#${rn_limite}#\1${RENAME_TO}\2#g;s#${rn_limite}#\1${RENAME_TO}\2#g}" "$rn_f"
            done
            if ! run nginx -t >/dev/null 2>&1; then
                renom_restaurer
                fail "Changement de nom : nginx -t refuse la nouvelle configuration — anciennes versions restaurées, nginx NON rechargé. Sauvegardes : $rn_sauv"
                rn_ok=0
            else
                nginx_appliquer || true
                pass "nginx : $RENAME_FROM remplacé par $RENAME_TO dans ${#rn_fichiers[@]} fichier(s) ; nginx -t réussi, nginx rechargé. Sauvegardes : $rn_sauv"
            fi
        fi
        if (( rn_ok && ! rn_cert_ok )); then
            paquet_installer certbot certbot
            if command -v certbot >/dev/null 2>&1; then
                rn_args=(certonly --webroot -w /var/www/letsencrypt -d "$RENAME_TO" --cert-name "$RENAME_TO" --non-interactive --agree-tos)
                if [[ -n "$MAIL_TO" ]]; then rn_args+=(-m "$MAIL_TO"); else rn_args+=(--register-unsafely-without-email); fi
                if rn_sortie=$(run certbot "${rn_args[@]}" 2>&1) && [[ -r "$rn_cert" ]]; then
                    rn_cert_ok=1
                    pass "Certificat Let's Encrypt obtenu pour $RENAME_TO ($rn_cert)."
                else
                    fail "certbot n'a pas pu obtenir le certificat de $RENAME_TO (le nom doit pointer vers CE serveur, port 80 ouvert, nginx servant /.well-known/acme-challenge/ depuis /var/www/letsencrypt) :"
                    printf '%s\n' "$rn_sortie" | tail -n 8 | sed 's/^/         /'
                fi
            fi
        fi
        if (( rn_ok && rn_cert_ok )); then
            # Phase 2: the certificate paths switch to that of the new name.
            for rn_f in "${rn_fichiers[@]}"; do
                sed -i "s#letsencrypt/live/${rn_ancien_re}/#letsencrypt/live/${RENAME_TO}/#g" "$rn_f"
            done
            if ! run nginx -t >/dev/null 2>&1; then
                renom_restaurer
                fail "Changement de nom : nginx -t refuse les chemins du nouveau certificat — anciennes versions restaurées, nginx NON rechargé."
            else
                nginx_appliquer || true
                pass "nginx : certificat de $RENAME_TO en service ; nginx -t réussi, nginx rechargé."
            fi
        elif (( rn_ok )); then
            warn "Les chemins du certificat de $RENAME_FROM sont gardés tant que $RENAME_TO n'a pas de certificat : les navigateurs refuseront $RENAME_TO. Corriger la cause ci-dessus puis relancer la même commande."
        fi
    fi
    # What the program never modifies: precise reminders.
    echo "  À faire à la main pour $RENAME_TO :"
    echo "    - DNS : enregistrement A (et AAAA) $RENAME_TO vers l'adresse IP de ce serveur ; retirer $RENAME_FROM du DNS seulement quand plus personne ne l'utilise."
    echo "    - Odoo : Paramètres → Technique → Paramètres système → web.base.url = https://$RENAME_TO (et freeze.url si présent)."
    if [[ -n "${ODOO_CONF:-}" && -r "$ODOO_CONF" ]] && grep -Eq "$rn_limite" "$ODOO_CONF" 2>/dev/null; then
        warn "$ODOO_CONF mentionne encore $RENAME_FROM (dbfilter ? ligne : $(grep -En "$rn_limite" "$ODOO_CONF" | head -n 1 | cut -c1-80)) — à adapter, puis redémarrer Odoo."
    fi
    rn_defaut=$(grep -lE "$rn_limite" "/etc/default/"* 2>/dev/null | tr '\n' ' ') || rn_defaut=""
    [[ -z "$rn_defaut" ]] || warn "Fichiers de /etc/default qui mentionnent encore $RENAME_FROM : $rn_defaut— à adapter (programmes de surveillance, courriel…)."
    echo "    - Anciens certificat et configuration : « certbot certificates » puis « certbot delete --cert-name $RENAME_FROM » quand $RENAME_FROM n'est plus servi."
    echo "    - HSTS : les navigateurs qui ont visité $RENAME_FROM continueront d'exiger HTTPS pour lui ; garder $RENAME_FROM avec un certificat valide et une redirection 301 vers $RENAME_TO."
    echo "    - Vérification : app-log-live.py --diagnose --diagnose-host $RENAME_TO (certificat vu comme un navigateur)."
fi
echo

# --- 0f) Configuration nginx generique (dossier nginx/ du depot, a cote de ce script) ---------------------------------------
# 2.56: the generic files (bots, rate limits, common security rules, fail2ban) are installed in /etc/nginx/ with the SAME layout as the site
# package. The set depends on the application detected by apps/_profile.sh (APP_NAME): odoo = the full set; bbb = the bot map only (BBB's
# own rules stay with durcir_bbb). For each file: identical => nothing; missing => created; different (edited by hand, or an older
# version) => a dated backup is kept, the diff is shown, then the replacement. Nothing changes without a confirmation (--update),
# and with --check only the plan is shown. Then nginx -t: if it fails, every file changed by this step is restored from its backup.
GEN_SRC="$SCRIPT_DIR/nginx"
GEN_DEST="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}"
gen_fichiers_app() {
    case "$APP_NAME" in
        odoo) echo "conf.d/bot_blocker.conf conf.d/odoo-global.conf snippets/securite-commune.conf snippets/odoo/_odoo-common.conf snippets/odoo/hsts.conf fail2ban/nginx-catchall.filter.conf fail2ban/nginx-catchall.jail.conf fail2ban/nginx-blocked-probes.filter.conf fail2ban/nginx-blocked-probes.jail.conf fail2ban/odoo-auth.filter.conf" ;;
        bbb)  echo "conf.d/bot_blocker.conf" ;;
        *)    echo "" ;;
    esac
}
echo "--- 0f) Configuration nginx générique (dépôt : $GEN_SRC) ---"
GEN_LISTE=$(gen_fichiers_app)
if [[ -z "$GEN_LISTE" ]]; then
    sans_objet "configuration nginx générique (application non reconnue : $APP_NAME)"
elif [[ ! -d "$GEN_SRC" ]]; then
    warn "Dossier nginx/ absent à côté du programme ($GEN_SRC) : configuration générique non installée."
else
    GEN_VERSION=$(cat "$GEN_SRC/VERSION" 2>/dev/null || true)
    echo "  Version livrée : ${GEN_VERSION:-inconnue} ; destination : $GEN_DEST"
    GEN_PLAN=()
    for rel in $GEN_LISTE; do
        src="$GEN_SRC/$rel"; dst="$GEN_DEST/$rel"
        if [[ ! -r "$src" ]]; then warn "$rel absent du dépôt : ignoré."; continue; fi
        if [[ ! -e "$dst" ]]; then GEN_PLAN+=("creer $rel")
        elif cmp -s "$src" "$dst"; then :
        else GEN_PLAN+=("remplacer $rel"); fi
    done
    if [[ "$APP_NAME" == "odoo" && ! -e "$GEN_DEST/snippets/robots-disallow.conf" ]]; then
        GEN_PLAN+=("creer snippets/robots-disallow.conf (vide : fichier propre au site, à remplir par le zip du site)")
    fi
    if (( ${#GEN_PLAN[@]} == 0 )); then
        pass "Configuration nginx générique à jour (tous les fichiers sont identiques au dépôt)."
    else
        echo "  Changements prévus :"
        for ligne in "${GEN_PLAN[@]}"; do echo "    - $ligne"; done
        for ligne in "${GEN_PLAN[@]}"; do
            case "$ligne" in remplacer\ *) rel="${ligne#remplacer }"
                echo "  Différences pour $rel (les 25 premières lignes) :"
                diff -u "$GEN_DEST/$rel" "$GEN_SRC/$rel" 2>/dev/null | sed -n '3,27p' | sed 's/^/      /' || true ;; esac
        done
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "Configuration nginx générique : ${#GEN_PLAN[@]} changement(s) en attente (relancer avec --update pour les appliquer après confirmation)."
        else
            GEN_REP=""
            if [[ -t 0 ]]; then read -r -p "  Appliquer ces ${#GEN_PLAN[@]} changement(s) à la configuration nginx générique ? [o/N] " GEN_REP || GEN_REP=""
            else warn "Pas de terminal : configuration nginx générique non modifiée (lancer --update dans un terminal pour confirmer)."; fi
            if [[ "$GEN_REP" =~ ^[oOyY]$ ]]; then
                GEN_TS=$(date +%Y%m%d-%H%M%S); GEN_FAITS=()
                for ligne in "${GEN_PLAN[@]}"; do
                    rel="${ligne#* }"; rel="${rel%% (*}"; src="$GEN_SRC/$rel"; dst="$GEN_DEST/$rel"
                    case "$ligne" in
                        remplacer\ *) cp -p "$dst" "$dst.before-generic-$GEN_TS" && GEN_FAITS+=("remplacer:$rel") ;;
                        creer\ *)     GEN_FAITS+=("creer:$rel") ;;
                    esac
                    mkdir -p "$(dirname "$dst")" 2>/dev/null || true
                    if [[ "$rel" == snippets/robots-disallow.conf ]]; then
                        printf '%s\n' "# vide — créé par nginx-hardening.sh --update ; à remplir par le zip de configuration du site" > "$dst"
                    else
                        cp "$src" "$dst"
                    fi
                    chmod 644 "$dst" 2>/dev/null || true
                done
                fragments_generes_assurer || true
                if nginx -t >/dev/null 2>&1; then
                    pass "Configuration nginx générique installée (${#GEN_FAITS[@]} fichier(s)) ; nginx -t réussit."
                    nginx_appliquer
                    echo "  nginx : $NGINX_APPLIQUE"
                else
                    fail "nginx -t refuse la configuration générique : retour à l'état précédent."
                    for item in "${GEN_FAITS[@]}"; do
                        rel="${item#*:}"; dst="$GEN_DEST/$rel"
                        if [[ "$item" == remplacer:* ]]; then mv -f "$dst.before-generic-$GEN_TS" "$dst"
                        else rm -f "$dst"; fi
                    done
                    nginx -t 2>&1 | tail -n 3 | sed 's/^/      /' || true
                fi
            else
                warn "Configuration nginx générique : aucun changement appliqué (refusé ou sans réponse)."
            fi
        fi
    fi
fi
echo

# --- 1) Directory for ACME challenges (Let's Encrypt) ---
echo "--- 1) Répertoire ACME (/var/www/letsencrypt) ---"
if [[ -n "${HARDENING_CONFIG:-}" ]]; then
if [[ -d /var/www/letsencrypt ]]; then
    pass "/var/www/letsencrypt existe déjà."
elif [[ "$CHECK_ONLY" == "1" ]]; then
    fail "/var/www/letsencrypt n'existe pas (relancer avec --update pour le créer)."
else
    if run mkdir -p /var/www/letsencrypt 2>/dev/null; then
        pass "/var/www/letsencrypt créé."
    else
        warn "Impossible de créer /var/www/letsencrypt (permissions ? /var/www absent ou non accessible ?) — à faire manuellement si nécessaire."
    fi
fi
echo

# --- 2) Dedicated log for the catch-all sensor ---
else
    sans_objet "pas de configuration de durcissement nginx livrée pour cette application (répertoire ACME de la configuration nginx-odoo)"
fi
echo "--- 2) Journal catch-all (/var/log/nginx/odoo-catchall-444.log) ---"
if [[ -n "${HARDENING_CONFIG:-}" ]]; then
CATCHALL_LOG=/var/log/nginx/odoo-catchall-444.log
if [[ -f "$CATCHALL_LOG" ]]; then
    owner=$(stat -c '%U:%G' "$CATCHALL_LOG" 2>/dev/null) || owner="?"
    if [[ "$owner" == "www-data:adm" ]]; then
        pass "$CATCHALL_LOG existe déjà, propriétaire correct (www-data:adm)."
    else
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "$CATCHALL_LOG existe mais son propriétaire est '$owner' (attendu www-data:adm)."
        elif run chown www-data:adm "$CATCHALL_LOG" 2>/dev/null; then
            pass "$CATCHALL_LOG : propriétaire corrigé (www-data:adm)."
        else
            warn "$CATCHALL_LOG : impossible de définir le propriétaire www-data:adm (utilisateur ou groupe absent sur ce système ?) — à corriger manuellement si nécessaire."
        fi
    fi
elif [[ "$CHECK_ONLY" == "1" ]]; then
    fail "$CATCHALL_LOG n'existe pas (relancer avec --update pour le créer)."
else
    CATCHALL_LOG_DIR=$(dirname "$CATCHALL_LOG")
    if [[ ! -d "$CATCHALL_LOG_DIR" ]]; then
        fail "$CATCHALL_LOG_DIR n'existe pas — nginx est-il installé ? (le paquet nginx crée normalement ce répertoire). Impossible de créer le journal catch-all tant que ce répertoire n'existe pas."
    else
        run touch "$CATCHALL_LOG"
        if run chown www-data:adm "$CATCHALL_LOG" 2>/dev/null; then
            pass "$CATCHALL_LOG créé, propriétaire www-data:adm."
        else
            warn "$CATCHALL_LOG créé mais impossible de définir le propriétaire www-data:adm (utilisateur ou groupe absent sur ce système ?) — à corriger manuellement si nécessaire."
        fi
    fi
fi
echo

# --- 3) Page de maintenance -------------------------------------------------------------------------------------
else
    sans_objet "pas de capteur catch-all dans sa configuration nginx"
fi
echo "--- 3) Page de maintenance (/var/www/maintenance/index.html) ---"
if [[ -n "${HARDENING_CONFIG:-}" ]]; then
MAINT_DIR=/var/www/maintenance
MAINT_FILE="$MAINT_DIR/index.html"
MAINT_SOURCE="$SCRIPT_DIR/maintenance/index.html"
for maint_cand in "$SCRIPT_DIR/maintenance/index.html" /etc/nginx/maintenance/index.html /root/scripts/maintenance/index.html; do      # next to the program, then the deployed nginx configuration
    if [[ -r "$maint_cand" ]]; then MAINT_SOURCE="$maint_cand"; break; fi
done
if [[ -f "$MAINT_FILE" ]]; then
    pass "$MAINT_FILE existe déjà."
elif [[ "$CHECK_ONLY" == "1" ]]; then
    fail "$MAINT_FILE n'existe pas — nginx affichera l'erreur brute d'Odoo plutôt que la page de maintenance."
else
    if [[ ! -r "$MAINT_SOURCE" ]]; then
        warn "Fichier source introuvable ($MAINT_SOURCE) — impossible de copier automatiquement. Copiez-le vous-même vers $MAINT_FILE."
    else
        if run mkdir -p "$MAINT_DIR" 2>/dev/null && run cp "$MAINT_SOURCE" "$MAINT_FILE" 2>/dev/null; then
            pass "$MAINT_FILE installé depuis $MAINT_SOURCE."
        else
            warn "Impossible de créer $MAINT_DIR ou d'y copier $MAINT_SOURCE (permissions ? /var/www absent ou non accessible ?) — à faire manuellement si nécessaire."
        fi
    fi
fi
echo

PORT_EXPOSED=0
NEED_FAIL2BAN_RESTART=0
# iptables_rendre_persistant: without a persistence package, the rules disappear at reboot - --update installs iptables-persistent and saves.
iptables_rendre_persistant() {
    if command -v netfilter-persistent >/dev/null 2>&1; then
        if run netfilter-persistent save >/dev/null 2>&1; then
            for ipt_f in /etc/iptables/rules.v4 /etc/iptables/rules.v6 /etc/iptables/ipsets; do         # fail2ban chains: recreated by it at startup (never restored twice)
                if [[ -f "$ipt_f" ]] && grep -q 'f2b-' "$ipt_f" 2>/dev/null; then run sed -i '/f2b-/d' "$ipt_f"; fi
            done
            pass "iptables : règles enregistrées (netfilter-persistent) — elles survivent à un redémarrage."
        else
            warn "iptables : « netfilter-persistent save » en échec — les règles sont en mémoire seulement."
        fi
    elif command -v apt-get >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive run apt-get install -y iptables-persistent >/dev/null 2>&1 && command -v netfilter-persistent >/dev/null 2>&1; then
        run netfilter-persistent save >/dev/null 2>&1 || true
        for ipt_f in /etc/iptables/rules.v4 /etc/iptables/rules.v6 /etc/iptables/ipsets; do
            if [[ -f "$ipt_f" ]] && grep -q 'f2b-' "$ipt_f" 2>/dev/null; then run sed -i '/f2b-/d' "$ipt_f"; fi
        done
        pass "iptables-persistent installé et règles enregistrées — elles survivent à un redémarrage."
    else
        warn "iptables : règle ajoutée en mémoire seulement — installez iptables-persistent (ou équivalent) pour qu'elle survive à un redémarrage."
    fi
}

# --- 4) Odoo listening interface (diagnostic only - never automatic editing of odoo.conf) ---
else
    sans_objet "pas de page de maintenance de la configuration nginx-odoo"
fi
echo "--- 4) Interface d'écoute d'Odoo (diagnostic — ports $ODOO_HTTP_PORT et $ODOO_GEVENT_PORT) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if ! command -v ss >/dev/null 2>&1; then
    warn "Commande 'ss' introuvable — impossible de vérifier l'interface d'écoute d'Odoo automatiquement."
else
    for port in "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT"; do
        binding=$(run ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $4}' | head -1) || true
        if [[ -z "$binding" ]]; then
            warn "Rien n'écoute sur le port $port actuellement (Odoo est-il démarré ?) — impossible de vérifier."
        elif [[ "$binding" == 127.0.0.1:* || "$binding" == \[::1\]:* ]]; then
            pass "Port $port : écoute sur $binding (local seulement — correct)."
        else
            fail "Port $port : écoute sur $binding (accessible depuis l'EXTÉRIEUR) — voir la recommandation ci-dessous."
            PORT_EXPOSED=1
        fi
    done
fi

# nginx upstreams: the "upstream" ports must be Odoo's (http_port / gevent_port of the Odoo configuration).
# Otherwise nginx does not reach Odoo and answers the maintenance page (502/503/504) while Odoo runs very well.
amonts_nginx_lister() {
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f reel vus=" "
    for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do
        [[ -f "$f" ]] || continue
        reel=$(readlink -f "$f" 2>/dev/null) || reel="$f"
        [[ "$vus" == *" $reel "* ]] && continue
        vus+="$reel "
        awk -v fic="$f" -v reel="$reel" '
            /^[[:space:]]*#/ { next }
            /^[[:space:]]*upstream[[:space:]]+[^[:space:]{]+/ { nom = $2; sub(/\{.*/, "", nom); dans = 1 }
            dans && match($0, /server[[:space:]]+[^[:space:];]+/) {
                srv = substr($0, RSTART, RLENGTH); sub(/^server[[:space:]]+/, "", srv)
                print fic "\t" reel "\t" FNR "\t" nom "\t" srv
            }
            dans && /\}/ { dans = 0 }
        ' "$f"
    done
}
amonts_n=0
amonts_ko=0
while IFS=$'\t' read -r am_fic am_reel am_ligne am_nom am_srv; do
    [[ -n "$am_srv" ]] || continue
    am_hote="${am_srv%:*}"; am_port="${am_srv##*:}"
    [[ "$am_hote" == "$am_srv" ]] && continue                        # no port (unix socket, group name...)
    [[ "$am_port" =~ ^[0-9]+$ ]] || continue
    case "$am_hote" in 127.0.0.1|localhost|"[::1]") ;; *) continue ;; esac
    case "$am_nom" in
        odoo[0-9]*)                                                  # autre version d'Odoo (ex. odoo17, odoo17_chat) : ports propres, jamais ceux de cette instance
            echo "  [--]   nginx : l'amont « $am_nom » ($am_fic:$am_ligne) est celui d'une autre version d'Odoo (port $am_port) : non vérifié, non modifié."
            continue ;;
        *chat*|*longpoll*|*gevent*|*websocket*) am_attendu="$ODOO_GEVENT_PORT"; am_genre="gevent" ;;
        odoo*) am_attendu="$ODOO_HTTP_PORT"; am_genre="HTTP" ;;
        *) continue ;;
    esac
    amonts_n=$((amonts_n + 1))
    if [[ "$am_port" == "$am_attendu" ]]; then
        pass "nginx : l'amont « $am_nom » ($am_fic:$am_ligne) vise le port $am_port, qui est celui d'Odoo ($am_genre)."
        continue
    fi
    amonts_ko=$((amonts_ko + 1))
    if [[ "$CHECK_ONLY" == "1" ]]; then
        fail "nginx : l'amont « $am_nom » ($am_fic:$am_ligne) vise le port $am_port, mais Odoo ($am_genre) est configuré sur $am_attendu ($ODOO_PORTS_SOURCE) — page de maintenance probable. Relancer avec --update pour corriger la configuration nginx."
        continue
    fi
    am_sauv="${NGINX_HARDENING_BACKUP_DIR:-/var/backups/nginx-hardening}"
    mkdir -p "$am_sauv" 2>/dev/null || true
    am_copie="$am_sauv/$(basename "$am_reel").$(date +%Y%m%d-%H%M%S).bak"      # hors de sites-enabled : nginx chargerait la copie
    cp -p "$am_reel" "$am_copie" 2>/dev/null || { fail "nginx : copie de sauvegarde de $am_reel impossible — fichier non modifié."; continue; }
    sed -i -E "${am_ligne}s/(server[[:space:]]+[^;[:space:]]*:)${am_port}([[:space:];])/\1${am_attendu}\2/" "$am_reel"
    if run nginx -t >/dev/null 2>&1; then
        nginx_appliquer || true
        pass "nginx : l'amont « $am_nom » ($am_fic:$am_ligne) passe du port $am_port à $am_attendu (Odoo, $am_genre) ; nginx -t réussi, nginx rechargé. Sauvegarde : $am_copie"
    else
        cp -p "$am_copie" "$am_reel" 2>/dev/null || true
        fail "nginx : le port $am_attendu de l'amont « $am_nom » est refusé par nginx -t — ancienne version restaurée ($am_fic), nginx NON rechargé."
    fi
done < <(amonts_nginx_lister)
if (( amonts_n == 0 )); then
    echo "  [--]   nginx : aucun amont « odoo » sur 127.0.0.1 trouvé dans sites-enabled/ ni conf.d/ (vérification des ports ignorée)."
fi

# Odoo websocket (real-time discussions): without the right "location /websocket" in nginx, messages do not arrive live (or with a long delay) for
# connected people. Checks: the /websocket route to the gevent port, HTTP 1.1, the Upgrade and Connection headers, the read timeout (Odoo sends a ping every 40
# to 55 s; the nginx default is 60 s) and the nginx connection count. Reads nginx.conf with its "include" (or sites-enabled/ and conf.d/ otherwise).
WS_DELAI_MIN=120        # secondes : en dessous, la marge sur les pings d'Odoo est trop mince
WS_DELAI_REGLE=300      # seconds: value set by --update
ws_lire_fichier() {
    local f="$1" prof="${2:-0}" n=0 ligne motif g
    [[ -f "$f" ]] || return 0
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        n=$((n + 1))
        ligne="${ligne//$'\t'/ }"
        if [[ "$ligne" =~ ^[[:space:]]*include[[:space:]]+([^\;]+)\; ]] && (( prof < 5 )); then
            motif="${BASH_REMATCH[1]}"
            [[ "$motif" == /* ]] || motif="$ws_racine/$motif"
            if [[ "$motif" == /etc/nginx/* && "$ws_racine" != /etc/nginx ]]; then motif="$ws_racine/${motif#/etc/nginx/}"; fi      # dossier nginx de remplacement (tests)
            for g in $motif; do                                  # deliberately unprotected glob
                if [[ -f "$g" ]]; then ws_lire_fichier "$g" $((prof + 1)); fi
            done
        else
            printf '%s:%s\t%s\n' "$f" "$n" "$ligne"
        fi
    done < "$f"
    return 0
}
ws_config_aplatie() {
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f
    ws_racine="$dir"
    if [[ -f "$dir/nginx.conf" ]]; then
        ws_lire_fichier "$dir/nginx.conf" 0
    else
        printf 'x:0\thttp {\n'
        for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do ws_lire_fichier "$f" 0; done
        printf 'x:0\t}\n'
    fi
    return 0
}
ws_analyser() {   # $1 Odoo HTTP port, $2 gevent port: lines (separated by \037) "G|H", path, file:line, timeout, file:line of the timeout, HTTP version, Upgrade, Connection, indentation, own timeout
    awk -F'\t' -v HTTP="$1" -v GEVENT="$2" -v q="'" '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    function unquote(s) { gsub("^[\"" q "]|[\"" q "]$", "", s); return s }
    function secondes(v,   n, u) {
        n = v + 0; u = v; gsub(/[0-9.]/, "", u)
        if (u == "m") return n * 60
        if (u == "h") return n * 3600
        if (u == "ms") return n / 1000
        if (u == "d") return n * 86400
        return n
    }
    function statement(s, c, tag,   w, nw, k, x, hu, hc, hv2, tov, ttag, tprop, trouve) {
        s = trim(s)
        if (c == ";") {
            if (s == "" || d < 1) return
            nw = split(s, w, /[ ]+/)
            if (w[1] == "proxy_pass") { pp[d] = w[2]; ppt[d] = tag; match(raw, /^[ ]*/); ind[d] = substr(raw, 1, RLENGTH) }
            else if (w[1] == "proxy_set_header") { ph[d]++; if (tolower(w[2]) == "upgrade") up[d] = 1; if (tolower(w[2]) == "connection") cn[d] = unquote(w[3]) }
            else if (w[1] == "proxy_read_timeout") { to[d] = secondes(unquote(w[2])); tt[d] = tag }
            else if (w[1] == "proxy_http_version") hv[d] = w[2]
            else if (w[1] == "set" && substr(w[2], 1, 1) == "$") sv[fid[d], w[2]] = unquote(w[3])
            else if (w[1] == "worker_connections") wc = w[2]
            else if (w[1] == "server" && typ[d] == "upstream" && !(upn[d] in ups)) { x = w[2]; sub(/.*:/, "", x); ups[upn[d]] = x }
            return
        }
        if (c == "{") {
            d++; fid[d] = ++fidn; typ[d] = "autre"; pp[d] = ""; ppt[d] = ""; ph[d] = 0; up[d] = 0; cn[d] = ""; to[d] = ""; tt[d] = ""; hv[d] = ""; ind[d] = ""; chemin[d] = ""
            nw = split(s, w, /[ ]+/)
            if (w[1] == "location") { typ[d] = "location"; chemin[d] = trim(substr(s, 9)) }
            else if (w[1] == "upstream") { typ[d] = "upstream"; upn[d] = w[2] }
            else if (w[1] == "server" || w[1] == "http") typ[d] = w[1]
            return
        }
        if (d < 1) return
        if (typ[d] == "location" && pp[d] != "") {
            t = pp[d]                                  # "proxy_pass http://$odoo_backend_chat;": the variable comes from a "set" of the server (or of the http block)
            while (match(t, /\$[A-Za-z_0-9]+/)) {
                nom = substr(t, RSTART, RLENGTH); val = ""
                for (k = d; k >= 1; k--) if ((fid[k], nom) in sv) { val = sv[fid[k], nom]; break }
                if (val == "") break
                t = substr(t, 1, RSTART - 1) val substr(t, RSTART + RLENGTH)
            }
            n++; R_chemin[n] = chemin[d]; R_pp[n] = t; R_ppt[n] = ppt[d]; R_ind[n] = ind[d]
            hu = 0; hc = ""; hv2 = ""; tov = ""; ttag = ""; trouve = 0; tprop = 0
            for (k = d; k >= 1; k--) {              # headers are inherited only if this location (or the closest level) defines none
                if (!trouve && ph[k] > 0) { hu = up[k]; hc = cn[k]; trouve = 1 }
                if (hv2 == "" && hv[k] != "") hv2 = hv[k]
                if (tov == "" && to[k] != "") { tov = to[k]; ttag = tt[k]; tprop = (k == d) }
            }
            R_up[n] = hu; R_cn[n] = hc; R_hv[n] = (hv2 == "" ? "1.0" : hv2); R_to[n] = (tov == "" ? 60 : tov); R_tt[n] = ttag; R_tprop[n] = tprop
        }
        d--
    }
    {
        tag = $1; raw = $2; line = $2
        sub(/#.*/, "", line)
        if (trim(line) == "") next
        while (match(line, /[;{}]/)) {                 # RSTART est lu AVANT l appel : statement() utilise aussi match()
            pos = RSTART; c = substr(line, pos, 1); instr = substr(line, 1, pos - 1); line = substr(line, pos + 1)
            statement(instr, c, tag)
        }
    }
    END {
        for (i = 1; i <= n; i++) {
            t = R_pp[i]; sub(/^https?:\/\//, "", t); sub(/\/.*/, "", t); port = ""
            if (t ~ /^(127\.0\.0\.1|localhost|\[::1\]):[0-9]+$/) { port = t; sub(/.*:/, "", port) }
            else if (t in ups) port = ups[t]
            classe = (port == GEVENT) ? "G" : ((port == HTTP && R_chemin[i] ~ /websocket|longpolling/) ? "H" : "")
            if (classe == "" && t ~ /\$/ && R_chemin[i] ~ /websocket|longpolling/) classe = "U"        # variable the script cannot resolve
            if (classe != "") printf "%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s\n", classe, R_chemin[i], R_ppt[i], (classe == "U" ? t : R_to[i]), R_tt[i], R_hv[i], R_up[i], R_cn[i], R_ind[i], R_tprop[i]
        }
        if (wc != "") printf "W\037%s\n", wc
    }'
}
ws_n=0; ws_http=0; ws_inconnu=0; ws_fixes=""; ws_sep=$'\037'; ws_fail0=$FAIL
if [[ -d "${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" ]]; then
    ws_donnees=$(ws_config_aplatie | ws_analyser "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT") || ws_donnees=""
    while IFS=$'\037' read -r ws_k ws_chem ws_tag ws_to ws_tt ws_hv ws_up ws_cn ws_ind ws_tprop; do
        case "$ws_k" in
            W)
                if [[ "$ws_chem" =~ ^[0-9]+$ ]] && (( ws_chem < 1024 )); then
                    warn "nginx : worker_connections = $ws_chem — chaque websocket occupe 2 connexions (le navigateur et Odoo) ; avec une centaine de personnes connectées à la discussion (souvent 2 appareils chacune), prévoir au moins 2048."
                fi
                ;;
            U)
                ws_inconnu=$((ws_inconnu + 1))
                echo "  [--]   nginx : le location « $ws_chem » ($ws_tag) envoie vers une variable que ce script ne sait pas résoudre ($ws_to) — vérification de ce websocket ignorée."
                ;;
            H)
                ws_http=$((ws_http + 1))
                fail "nginx : le location « $ws_chem » ($ws_tag) vise le port HTTP d'Odoo ($ODOO_HTTP_PORT) au lieu du port gevent ($ODOO_GEVENT_PORT) — les messages de la discussion n'arrivent pas en temps réel (Odoo avec workers : seul le processus gevent sert le websocket)."
                ;;
            G)
                ws_n=$((ws_n + 1))
                ws_ok=1
                                if [[ "$ws_hv" != "1.1" ]]; then
                    ws_ok=0
                    if [[ "$CHECK_ONLY" == "1" ]]; then
                        fail "nginx : le location « $ws_chem » ($ws_tag) n'a pas « proxy_http_version 1.1; » (défaut de nginx : 1.0) — les websockets échouent et les messages n'arrivent plus en direct. Relancer avec --update pour l'ajouter."
                    else
                        ws_fixes+="V${ws_sep}${ws_tag}${ws_sep}${ws_chem}${ws_sep}${ws_ind}${ws_sep}${ws_tt}${ws_sep}${ws_to}${ws_sep}${ws_tprop}"$'\n'
                    fi
                fi
                if [[ "$ws_up" != "1" ]]; then
                    ws_ok=0
                    fail "nginx : le location « $ws_chem » ($ws_tag) n'envoie pas « proxy_set_header Upgrade \$http_upgrade; » — le websocket ne s'établit pas. À ajouter à la main (voir le modèle ci-dessous : ajouter une directive proxy_set_header à un location retire celles du niveau supérieur)."
                fi
                if [[ "${ws_cn,,}" != "upgrade" && "$ws_cn" != "\$connection_upgrade" ]]; then
                    ws_ok=0
                    fail "nginx : le location « $ws_chem » ($ws_tag) n'envoie pas « proxy_set_header Connection \"upgrade\"; » (ni \$connection_upgrade) — le websocket ne s'établit pas. À ajouter à la main (voir le modèle ci-dessous)."
                fi
                if (( ${ws_to%.*} < WS_DELAI_MIN )); then
                    ws_ok=0
                    if [[ "$CHECK_ONLY" == "1" ]]; then
                        warn "nginx : le location « $ws_chem » ($ws_tag) coupe un websocket muet après ${ws_to%.*} s (proxy_read_timeout, défaut 60 s) ; Odoo envoie un ping toutes les 40 à 55 s : marge trop mince, les coupures répétées retardent les messages. Relancer avec --update pour passer à ${WS_DELAI_REGLE} s."
                    else
                        ws_fixes+="T${ws_sep}${ws_tag}${ws_sep}${ws_chem}${ws_sep}${ws_ind}${ws_sep}${ws_tt}${ws_sep}${ws_to}${ws_sep}${ws_tprop}"$'\n'
                    fi
                fi
                (( ws_ok == 1 )) && pass "nginx : le location « $ws_chem » ($ws_tag) vise le port gevent $ODOO_GEVENT_PORT, HTTP 1.1, en-têtes Upgrade et Connection, délai de lecture ${ws_to%.*} s — websocket (discussions en temps réel) bien configuré."
                ;;
        esac
    done <<< "$ws_donnees"
    # Corrections of --update (no effect on header inheritance): proxy_http_version 1.1 and proxy_read_timeout
    if [[ -n "$ws_fixes" ]]; then
        ws_sauv="${NGINX_HARDENING_BACKUP_DIR:-/var/backups/nginx-hardening}"
        mkdir -p "$ws_sauv" 2>/dev/null || true
        while IFS=$'\037' read -r ws_type ws_tag ws_chem ws_ind ws_tt ws_to ws_tprop; do
            [[ -n "$ws_type" ]] || continue
            ws_fic="${ws_tag%:*}"; ws_lig="${ws_tag##*:}"
            ws_reel=$(readlink -f "$ws_fic" 2>/dev/null) || ws_reel="$ws_fic"
            ws_copie="$ws_sauv/$(basename "$ws_reel").$(date +%Y%m%d-%H%M%S).bak"
            cp -p "$ws_reel" "$ws_copie" 2>/dev/null || { fail "nginx : copie de sauvegarde de $ws_reel impossible — fichier non modifié."; continue; }
            if [[ "$ws_type" == "V" ]]; then
                sed -i "${ws_lig}a\\
${ws_ind}proxy_http_version 1.1;" "$ws_reel"
                ws_quoi="« proxy_http_version 1.1; » ajouté"
            elif [[ "$ws_tprop" == "1" && -n "$ws_tt" && "${ws_tt%:*}" == "$ws_fic" ]]; then
                ws_lt="${ws_tt##*:}"
                sed -i -E "${ws_lt}s/(proxy_read_timeout[[:space:]]+)[^;]+;/\1${WS_DELAI_REGLE}s;/" "$ws_reel"
                ws_quoi="proxy_read_timeout modifié : ${ws_to%.*} s → ${WS_DELAI_REGLE} s"
            else
                sed -i "${ws_lig}a\\
${ws_ind}proxy_read_timeout ${WS_DELAI_REGLE}s;" "$ws_reel"
                ws_quoi="« proxy_read_timeout ${WS_DELAI_REGLE}s; » ajouté (défaut : 60 s)"
            fi
            if run nginx -t >/dev/null 2>&1; then
                nginx_appliquer || true
                pass "nginx : location « $ws_chem » ($ws_fic) : $ws_quoi ; nginx -t réussi, nginx rechargé. Sauvegarde : $ws_copie"
            else
                cp -p "$ws_copie" "$ws_reel" 2>/dev/null || true
                fail "nginx : la modification du location « $ws_chem » ($ws_fic) est refusée par nginx -t — ancienne version restaurée, nginx NON rechargé."
            fi
        done < <(printf '%s' "$ws_fixes" | tac)
    fi
    if (( ws_n == 0 && ws_http == 0 && ws_inconnu == 0 )); then
        if (( amonts_n > 0 )); then
            fail "nginx : aucun location vers le port gevent d'Odoo ($ODOO_GEVENT_PORT) — le websocket (discussions en temps réel) ne peut pas fonctionner."
        else
            echo "  [--]   nginx : aucun location /websocket vers Odoo trouvé (vérification du websocket ignorée)."
        fi
    fi
    if (( FAIL > ws_fail0 )) 2>/dev/null; then
        cat <<EOM
  Modèle de location pour le websocket d'Odoo (à placer AVANT « location / ») :
        location /websocket {
            proxy_pass http://127.0.0.1:$ODOO_GEVENT_PORT;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host \$host;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_read_timeout ${WS_DELAI_REGLE}s;
        }
EOM
    fi
fi
echo

# --- 5) Firewall: block direct external access to Odoo ports ---
# Defense in depth: even if Odoo is fixed to listen only locally (step 4), an explicit firewall
# also protects if this setting is accidentally changed one day. Detects ufw first (more readable/portable
# sur Debian), sinon retombe sur iptables direct.
else
    sans_objet "ports du serveur d'application Odoo"
fi
echo "--- 5) Pare-feu (ports $ODOO_HTTP_PORT et $ODOO_GEVENT_PORT bloqués depuis l'extérieur) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if command -v ufw >/dev/null 2>&1; then
    for port in "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT"; do
        if run ufw status 2>/dev/null | grep_q -E "^${port}/tcp[[:space:]]+DENY"; then
            pass "ufw : règle DENY déjà présente pour le port $port/tcp."
        elif [[ "$CHECK_ONLY" == "1" && "$EUID" -ne 0 ]]; then
            sans_root_verif "ufw : règle DENY du port $port/tcp"
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "ufw : aucune règle DENY pour le port $port/tcp (relancer avec --update pour l'ajouter)."
        else
            run ufw deny "$port"/tcp >/dev/null
            pass "ufw : règle DENY ajoutée pour le port $port/tcp."
        fi
    done
elif command -v iptables >/dev/null 2>&1; then
    for port in "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT"; do
        if run iptables -C INPUT -p tcp --dport "$port" ! -s 127.0.0.1 -j DROP 2>/dev/null; then
            pass "iptables : règle DROP déjà présente pour le port $port/tcp (sauf depuis 127.0.0.1)."
        elif [[ "$CHECK_ONLY" == "1" && "$EUID" -ne 0 ]]; then
            sans_root_verif "iptables : règle DROP du port $port/tcp"
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "iptables : aucune règle DROP pour le port $port/tcp (relancer avec --update pour l'ajouter)."
        else
            run iptables -I INPUT -p tcp --dport "$port" ! -s 127.0.0.1 -j DROP
            pass "iptables : règle DROP ajoutée pour le port $port/tcp (sauf depuis 127.0.0.1)."
            iptables_rendre_persistant
        fi
    done
    if ! command -v netfilter-persistent >/dev/null 2>&1; then          # rules already set but never saved: lost at the next reboot
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "iptables : netfilter-persistent absent — les règles disparaîtront au redémarrage (relancer avec --update pour installer iptables-persistent)."
        else
            iptables_rendre_persistant
        fi
    fi
else
    warn "Ni ufw ni iptables trouvés — impossible de vérifier/ajouter les règles de pare-feu automatiquement."
fi
echo

# --- Resolution of the Odoo service (steps 6-8): same auto-detection logic as app-log-check.py ---
odoo_service="$ODOO_SERVICE"
if [[ -z "$odoo_service" ]]; then
    for candidate in $ODOO_CONF_UNITES erplibre.service erplibre_erplibre.service; do
        if run systemctl list-unit-files "$candidate" --no-legend 2>/dev/null | grep_q "$candidate"; then
            odoo_service="$candidate"
            break
        fi
    done
fi

# --- Resolution of odoo.conf: done above (--odoo-conf, otherwise first candidate of --odoo-conf-paths). Display fallback only.
if [[ -z "$ODOO_CONF" ]]; then
    ODOO_CONF="/etc/odoo/odoo.conf"  # repli pour affichage, meme si rien n'a ete trouve
fi

# --- Resolution of the real startup script (run.sh) via the systemd unit - used by steps 6 AND 7.
# "systemctl cat" fusionne les eventuels drop-ins (sinon un reglage ajoute via override serait invisible). Fait
# UNE SEULE FOIS ici : un flag --limit-memory-hard passe en ligne de commande dans run.sh a PRIORITE sur la
# value of odoo.conf (standard Odoo rule: CLI > config file) - step 6 must know it so as not to
# signaler a tort une valeur de odoo.conf qu'Odoo n'utilise jamais reellement en pratique.
run_script=""
run_script_prod_lines=""
run_direct=0
if [[ -n "$odoo_service" ]]; then
    unit_content=$(run systemctl cat "$odoo_service" 2>/dev/null) || true
    if [[ -n "$unit_content" ]]; then
        exec_start=$(printf '%s' "$unit_content" | grep -E "^ExecStart=" | tail -1 | sed -E 's/^ExecStart=//') || true
        run_script=$(printf '%s' "$exec_start" | awk '{print $1}') || true
        if [[ -n "$run_script" && -r "$run_script" ]] && ! grep -Iq . "$run_script" 2>/dev/null; then
            # ExecStart directly launches a program (venv python...) and not a run.sh script: Odoo's options are on the ExecStart line itself
            run_direct=1
            run_script_prod_lines="$exec_start"
        elif [[ -n "$run_script" && -r "$run_script" ]]; then
            # Exclut la ligne du mode test (--log-level=test, branche ODOO_MODE_TEST) ET les lignes commentees
            # (ex. une ancienne invocation "python3 ./odoo/odoo-bin ..." laissee en commentaire pour reference,
            # avec ses propres valeurs --limit-memory-*, parfois tres differentes de celles reellement actives) de
            # TOUTES les verifications basees sur run.sh. Sans l'exclusion des commentaires, "tail -1" sur un grep
            # multi-lignes prend le DERNIER "--limit-memory-hard=" trouve dans le fichier, meme s'il est mort dans
            # a comment lower down than the real production line - real bug observed: a commented line
            # contenant --limit-memory-hard=10737418240 (10240 Mo) etait prise pour la valeur active, faussant
            # entierement le diagnostic de l'etape 6 malgre une vraie ligne de production correcte juste au-dessus.
            run_script_prod_lines=$(grep -v -- "--log-level=test" "$run_script" | grep -vE '^\s*#') || true
        fi
    fi
fi

# --- 6) Suggested calculation of Odoo memory limits (workers x RAM really available) ---
# Never applied automatically (odoo.conf or run.sh are never modified) - only displays the calculation and a
# comparaison avec la valeur actuelle si elle est trouvable, pour eviter de deviner un chiffre a l'aveugle (voir
# l'incident evite : un chiffre choisi sans connaitre le nombre de workers reel aurait pu causer un OOM en PROD).
else
    sans_objet "ports du serveur d'application Odoo (pare-feu de BBB : ufw, géré par son installateur)"
fi
U_MEM="Mo"; [[ "${NGINX_TOOLS_I18N_LANGUE:-fr}" != "fr" ]] && U_MEM="MB"       # memory unit displayed (MB in French)
echo "--- 6) Suggestion de limites mémoire Odoo (workers × RAM disponible) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if [[ -z "$odoo_service" ]]; then
    warn "Aucun service Odoo connu trouvé (db_user de la configuration, erplibre.service / erplibre_erplibre.service) — précisez --odoo-service NOM pour activer ce calcul."
else
    workers="$ODOO_WORKERS_OVERRIDE"
    if [[ -z "$workers" && -r "$ODOO_CONF" ]]; then
        workers=$(grep -E "^\s*workers\s*=" "$ODOO_CONF" 2>/dev/null | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]') || true
    fi
    if [[ -z "$workers" ]]; then
        cores=$(nproc 2>/dev/null) || cores=0
        if [[ "$cores" -gt 0 ]]; then
            workers=$(( cores * 2 + 1 ))
            warn "Nombre de workers introuvable dans $ODOO_CONF — utilise la formule officielle Odoo ((cœurs × 2) + 1 = $workers) à titre indicatif. Précisez --workers N pour une valeur exacte si elle est définie ailleurs (ex. run.sh)."
        fi
    fi

    total_ram_kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null) || true
    total_ram_mb=$(( ${total_ram_kb:-0} / 1024 ))

    if [[ -z "$workers" || "$workers" -eq 0 || "$total_ram_mb" -eq 0 ]]; then
        warn "Données insuffisantes (workers ou RAM totale introuvable) — calcul impossible."
    else
        used_mb=$(run free -m 2>/dev/null | awk '/^Mem:/{print $3}') || used_mb=0
        odoo_used_mb=0
        mem_current=$(run systemctl show "$odoo_service" -p MemoryCurrent --value 2>/dev/null) || true
        if [[ "$mem_current" =~ ^[0-9]+$ ]]; then
            odoo_used_mb=$(( mem_current / 1024 / 1024 ))
        fi
        non_odoo_mb=$(( used_mb - odoo_used_mb ))
        (( non_odoo_mb < 0 )) && non_odoo_mb=0
        safety_margin_mb=512
        available_for_odoo_mb=$(( total_ram_mb - non_odoo_mb - safety_margin_mb ))
        (( available_for_odoo_mb < 0 )) && available_for_odoo_mb=0
        safe_hard_mb=$(( available_for_odoo_mb / workers ))
        safe_soft_mb=$(( safe_hard_mb * 85 / 100 ))

        echo "  Service Odoo               : $odoo_service"
        echo "  Workers                     : $workers"
        echo "  RAM totale                  : ${total_ram_mb} $U_MEM"
        echo "  Utilisé hors Odoo (estimé)  : ${non_odoo_mb} $U_MEM (PostgreSQL, OS, nginx, etc. — via free -m moins"
        echo "                                l'usage actuel du cgroup d'Odoo, MemoryCurrent)"
        echo "  Disponible pour Odoo        : ${available_for_odoo_mb} $U_MEM"
        echo
        echo "  Suggestion (par worker — à valider par un test réel en DEV avant PROD) :"
        printf "    --limit-memory-soft=%d   (%d $U_MEM)\n" $(( safe_soft_mb * 1024 * 1024 )) "$safe_soft_mb"
        printf "    --limit-memory-hard=%d   (%d $U_MEM)\n" $(( safe_hard_mb * 1024 * 1024 )) "$safe_hard_mb"
        echo "  Pire cas (tous les workers à la limite dure en même temps) : $(( safe_hard_mb * workers )) $U_MEM"

        if [[ -r "$ODOO_CONF" ]] || [[ -n "$run_script_prod_lines" ]]; then
            # Priorite : un --limit-memory-hard=N en ligne de commande dans run.sh (branche production) l'emporte
            # ALWAYS the value of odoo.conf, Odoo side - so we look for it here first.
            current_hard=""
            current_hard_source=""
            if [[ -n "$run_script_prod_lines" ]]; then
                current_hard=$(printf '%s' "$run_script_prod_lines" | grep -oE -- '--limit-memory-hard=[0-9]+' | tail -1 | sed -E 's/.*=//') || true
                [[ -n "$current_hard" ]] && current_hard_source="$run_script (ligne de commande, priorité sur odoo.conf)"
            fi
            if [[ -z "$current_hard" && -r "$ODOO_CONF" ]]; then
                current_hard=$(grep -E "^\s*limit_memory_hard\s*=" "$ODOO_CONF" 2>/dev/null | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]') || true
                [[ -n "$current_hard" ]] && current_hard_source="$ODOO_CONF"
            fi
            if [[ "$current_hard" =~ ^[0-9]+$ ]]; then
                current_hard_mb=$(( current_hard / 1024 / 1024 ))
                worst_case_current_mb=$(( current_hard_mb * workers ))
                if (( current_hard == 0 )); then
                    fail "limit_memory_hard actuel = 0 (illimité) — source : $current_hard_source — aucune protection contre l'épuisement mémoire."
                elif (( worst_case_current_mb > total_ram_mb )); then
                    fail "limit_memory_hard actuel (${current_hard_mb} $U_MEM, source : $current_hard_source) × $workers workers = ${worst_case_current_mb} $U_MEM > RAM totale (${total_ram_mb} $U_MEM) — risque réel d'épuisement mémoire si plusieurs workers culminent en même temps."
                else
                    pass "limit_memory_hard actuel (${current_hard_mb} $U_MEM, source : $current_hard_source) cohérent avec la RAM disponible."
                fi
            else
                echo "  (limit_memory_hard non trouvé dans $ODOO_CONF ni dans la ligne de production de run.sh)"
            fi
        fi
    fi
fi
echo

# --- 7) Audit of the Odoo service (systemd unit + startup script) - diagnostic only, never editing ---
else
    sans_objet "limites mémoire des workers Odoo"
fi
echo "--- 7) Audit du service Odoo (unité systemd + run.sh) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if [[ -z "$odoo_service" ]]; then
    warn "Service Odoo non déterminé — audit ignoré (voir étape 6)."
elif [[ -z "$unit_content" ]]; then
    warn "Impossible de lire l'unité $odoo_service (systemctl cat)."
else
    if printf '%s' "$unit_content" | grep_q "^Wants=.*network-online.target"; then
        pass "Wants=network-online.target présent."
    else
        warn "Wants=network-online.target absent — After= seul ne garantit pas que le réseau soit prêt avant le démarrage d'Odoo."
    fi

    if printf '%s' "$unit_content" | grep_q -E "^StartLimitIntervalSec=|^StartLimitBurst="; then
        pass "Limite anti-boucle-de-redémarrage (StartLimitIntervalSec/Burst) configurée."
    else
        warn "Aucune limite anti-boucle-de-redémarrage — Restart=always peut retenter indéfiniment si le service plante en boucle, sans jamais passer en état 'failed' pour alerter."
    fi

    if printf '%s' "$unit_content" | grep_q "^NoNewPrivileges=true"; then
        pass "NoNewPrivileges=true présent."
    else
        warn "NoNewPrivileges=true absent — durcissement simple et sans risque connu à ajouter."
    fi

    if printf '%s' "$unit_content" | grep_q "^PIDFile=" && printf '%s' "$unit_content" | grep_q "^Type=simple"; then
        warn "PIDFile= présent avec Type=simple — sans effet réel (PIDFile n'est utile qu'avec Type=forking), nettoyage possible."
    fi

    # run_script / run_script_prod_lines deja resolus plus haut (partages avec l'etape 6), l'exclusion de
    # --log-level=test y est deja appliquee.
    if [[ "$run_direct" == "1" ]]; then
        pass "ExecStart lance directement $run_script (pas de script run.sh) : les options d'Odoo sont lues sur cette ligne de commande."
        if printf '%s' "$run_script_prod_lines" | grep_q -E -- "--limit-memory-hard=0\b"; then
            fail "ExecStart contient --limit-memory-hard=0 (illimité) — voir l'étape 6 pour une valeur suggérée."
        fi
    elif [[ -n "$run_script" && -n "$run_script_prod_lines" ]]; then
        if printf '%s' "$run_script_prod_lines" | grep_q -E "^\s*exec\s+.*odoo_bin\.sh"; then
            pass "$run_script utilise 'exec' avant de lancer odoo_bin.sh — suivi de PID le plus propre possible."
        else
            warn "$run_script n'utilise pas 'exec' avant odoo_bin.sh — sans danger avec KillMode=control-group (le défaut, qui envoie SIGTERM à tout le groupe de processus), mais 'exec' reste plus propre."
        fi

        if printf '%s' "$run_script_prod_lines" | grep_q 'ORIGIN_CONFIG_PATH=CONFIG_PATH'; then
            warn "$run_script contient 'ORIGIN_CONFIG_PATH=CONFIG_PATH' (sans \$) — coquille cosmétique, le message d'erreur affichera le mauvais texte si la config est introuvable."
        fi

        if printf '%s' "$run_script_prod_lines" | grep_q -E -- "--limit-memory-hard=0\b"; then
            fail "$run_script contient encore --limit-memory-hard=0 (illimité) sur la ligne de production — voir l'étape 6 pour une valeur suggérée."
        fi
    else
        warn "Impossible de lire le script de démarrage réel (${run_script:-introuvable}) pour vérifier exec/coquilles connues."
    fi
fi
echo

# --- 8) Audit of odoo.conf (additional security points, outside the port management already covered) ---
else
    sans_objet "unité systemd et run.sh d'Odoo"
fi
echo "--- 8) Audit odoo.conf ($ODOO_CONF) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if [[ ! -r "$ODOO_CONF" ]]; then
    warn "$ODOO_CONF introuvable ou illisible — précisez --odoo-conf CHEMIN si ce n'est pas le bon fichier."
else
    proxy_mode=$(grep -E "^\s*proxy_mode\s*=" "$ODOO_CONF" | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]') || true
    if [[ "$proxy_mode" == "true" || "$proxy_mode" == "1" ]]; then
        pass "proxy_mode activé — Odoo fait confiance aux en-têtes X-Forwarded-* de nginx (IP client réelle, HTTPS détecté correctement)."
    else
        fail "proxy_mode absent ou non activé dans $ODOO_CONF — derrière nginx, Odoo verrait 127.0.0.1 comme IP de TOUTES les requêtes dans ses propres journaux, et pourrait mal détecter HTTPS."
    fi

    list_db=$(grep -E "^\s*list_db\s*=" "$ODOO_CONF" | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]') || true
    # Ce que la regle nginx reserve aux IP autorisees (location allow/deny des env-*.conf) : depuis la config livree
    # le 2026-09-25, TOUTES les routes /web/database/* ; avant, seulement manager et selector (+ /xmlrpc/(2/)db).
    # /jsonrpc (service "db", method "list") remains out of nginx's reach in all cases: it is the general
    # entry point of the API, impossible to filter without breaking integrations - only list_db = False closes it.
    db_rule_all=0
    if command -v nginx >/dev/null 2>&1 && run nginx -T 2>/dev/null | grep_q -F 'web/database/.*|xmlrpc'; then
        db_rule_all=1
    fi
    if [[ "$list_db" == "false" || "$list_db" == "0" ]]; then
        pass "list_db désactivé — la liste des bases n'est renvoyée par AUCUNE route, pas même /jsonrpc (service « db », méthode « list »), que nginx ne peut pas filtrer. (Effet voulu : le gestionnaire de bases d'Odoo est aussi désactivé, y compris pour les IP autorisées.)"
    else
        warn "list_db absent ou actif dans $ODOO_CONF (actif par défaut dans Odoo) : la liste des bases peut être demandée."
        if [[ "$db_rule_all" == "1" ]]; then
            echo "         Réservées par nginx aux IP autorisées (allow) : toutes les routes /web/database/* (manager, selector, list,"
            echo "         backup, drop, restore, duplicate, create, change_password), /xmlrpc/db et /xmlrpc/2/db."
        else
            echo "         Réservées par nginx aux IP autorisées (allow) : /web/database/manager, /web/database/selector, /xmlrpc/db"
            echo "         et /xmlrpc/2/db SEULEMENT. /web/database/list (liste des bases en JSON) reste joignable par TOUS :"
            echo "         déployez la dernière config nginx (règle des env-*.conf étendue à toutes les routes /web/database/*)."
        fi
        echo "         Joignable par TOUS malgré nginx : /jsonrpc (service « db », méthode « list ») — point d'entrée général de"
        echo "         l'API, impossible à filtrer sans casser les intégrations ; seul list_db = False le ferme."
        echo "         Quoi faire : en PROD, list_db = False dans $ODOO_CONF puis redémarrer Odoo (le gestionnaire de bases est"
        echo "         alors désactivé pour tous : le réactiver le temps d'une opération). Sur une DEV entièrement restreinte par"
        echo "         IP (deny all dans env-dev.conf), acceptable tel quel : aucune de ces routes n'y est joignable d'Internet."
    fi

    admin_passwd=$(grep -E "^\s*admin_passwd\s*=" "$ODOO_CONF" | tail -1 | sed -E 's/^[^=]*=\s*//') || true
    if [[ -z "$admin_passwd" ]]; then
        warn "admin_passwd vide ou absent dans $ODOO_CONF — vérifiez manuellement (jamais affiché ici par précaution)."
    elif [[ "$admin_passwd" == "admin" || "$admin_passwd" == "password" || ${#admin_passwd} -lt 8 ]]; then
        fail "admin_passwd semble faible (valeur courante ou trop courte) — protège /web/database/manager, même restreint par IP. À vérifier manuellement."
    else
        pass "admin_passwd défini et de longueur raisonnable (valeur elle-même jamais affichée)."
    fi
fi
echo


# --- 9) fail2ban jails: catch-all sensor (nginx) and Odoo login failures (Odoo log) ---
# nginx-catchall : le capteur catch-all (odoo-catchall-444.log) est invisible des jails existants (leur glob
# "*access*.log" never finds it. odoo-auth: a wrong password answers 200, so invisible to any nginx
# jail - only Odoo's log ("Login failed ... from IP") makes it possible to detect brute force. NEW files and
# autonomes sous filter.d/ et jail.d/, jamais de modification de jail.local. Sources cherchees dans /etc/nginx/fail2ban
# (deploiement documente dans le README) puis a cote de ce script.
else
    sans_objet "odoo.conf"
fi
echo "--- 9) Jails fail2ban (capteur catch-all, échecs de connexion Odoo) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
F2B_SRC_DIR=""
for f2b_cand in /etc/nginx/fail2ban "$SCRIPT_DIR/fail2ban"; do
    if [[ -r "$f2b_cand/nginx-catchall.filter.conf" ]]; then F2B_SRC_DIR="$f2b_cand"; break; fi
done
F2B_INSTALLED_JAILS=()
if ! command -v fail2ban-client >/dev/null 2>&1; then
    warn "fail2ban-client introuvable — fail2ban n'est peut-être pas installé, étape ignorée."
else
    # --- 9a) jails with files copied as they are: nginx-catchall (catch-all sensor), nginx-blocked-probes (refusals
    # of the security rules, dedicated log blocked-probes.log) ---
    installer_jail_copie() {
        local nom="$1" pourquoi="$2" filtre="/etc/fail2ban/filter.d/$1.conf" jail="/etc/fail2ban/jail.d/$1.conf"
        if [[ -f "$filtre" && -f "$jail" ]]; then
            pass "Jail $nom : fichiers présents ($jail)."
            F2B_INSTALLED_JAILS+=("$nom")
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "Jail $nom absent — $pourquoi (relancer avec --update pour l'installer)."
        elif [[ -z "$F2B_SRC_DIR" || ! -r "$F2B_SRC_DIR/$nom.jail.conf" ]]; then
            warn "Fichiers source de $nom introuvables (cherché dans /etc/nginx/fail2ban/ et $SCRIPT_DIR/fail2ban/) — copiez le dossier fail2ban/ du zip vers /etc/nginx/fail2ban/."
        else
            mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d 2>/dev/null || true
            if run cp "$F2B_SRC_DIR/$nom.filter.conf" "$filtre" 2>/dev/null && run cp "$F2B_SRC_DIR/$nom.jail.conf" "$jail" 2>/dev/null; then
                pass "Jail $nom installé ($jail, depuis $F2B_SRC_DIR)."
                NEED_FAIL2BAN_RESTART=1
                F2B_INSTALLED_JAILS+=("$nom")
            else
                warn "Impossible de copier les fichiers du jail $nom (permissions ?) — à faire manuellement."
            fi
        fi
    }
    installer_jail_copie nginx-catchall "le capteur catch-all reste invisible de fail2ban"
    installer_jail_copie nginx-blocked-probes "les refus des règles de sécurité (blocked-probes.log) ne sont jamais sanctionnés"
    # The log must exist for fail2ban to load the jail (nginx creates it at the first refused request).
    if [[ "$CHECK_ONLY" != "1" && ! -e /var/log/nginx/blocked-probes.log ]] && [[ " ${F2B_INSTALLED_JAILS[*]} " == *" nginx-blocked-probes "* ]]; then
        if touch /var/log/nginx/blocked-probes.log 2>/dev/null; then
            chown --reference=/var/log/nginx /var/log/nginx/blocked-probes.log 2>/dev/null || true
        fi
    fi

    # --- 9b) odoo-auth (jail GENERE pour ce serveur a partir du modele) ---
    AUTH_FILTER_DST="/etc/fail2ban/filter.d/odoo-auth.conf"
    AUTH_JAIL_DST="/etc/fail2ban/jail.d/odoo-auth.conf"
    if [[ -z "$odoo_service" && -z "$ODOO_LOGFILE" ]]; then
        warn "Jail odoo-auth : service Odoo non déterminé (voir étape 6) — impossible de générer le jail (--odoo-service NOM)."
    elif [[ -z "$F2B_SRC_DIR" || ! -r "$F2B_SRC_DIR/odoo-auth.filter.conf" || ! -r "$F2B_SRC_DIR/odoo-auth.jail.conf.template" ]]; then
        if [[ -f "$AUTH_JAIL_DST" ]]; then
            pass "Jail odoo-auth : fichiers présents ($AUTH_JAIL_DST) — modèle introuvable, contenu non revérifié."
            F2B_INSTALLED_JAILS+=(odoo-auth)
        else
            warn "Jail odoo-auth : modèle introuvable (odoo-auth.*.conf dans /etc/nginx/fail2ban/) — déployez le dossier fail2ban/ du zip."
        fi
    else
        # Odoo log: possible namespace (LogNamespace, see log isolation) - fail2ban's systemd backend
        # ne lit que le journal par defaut, sauf si on lui donne le repertoire du namespace.
        auth_ns=$(run systemctl show -p LogNamespace --value "$odoo_service" 2>/dev/null) || auth_ns=""
        if [[ -n "$auth_ns" ]]; then
            auth_backend="systemd[journalpath=/var/log/journal/$(cat /etc/machine-id 2>/dev/null).$auth_ns]"
        else
            auth_backend="systemd"
        fi
        # IP a ne jamais bannir : boucle locale, adresses de ce serveur, et la liste blanche nginx (source unique des
        # trusted IP - team): an administrator's password error must not cut them off from the site.
        auth_ignore="127.0.0.1/8 ::1"
        for a in $(hostname -I 2>/dev/null) $(run nginx -T 2>/dev/null | grep -oE 'allow [0-9a-fA-F:./]+;' | awk '{print $2}' | tr -d ';' | sort -u); do
            case "$a" in 127.*|::1) continue ;; esac        # deja couvertes par 127.0.0.1/8 et ::1
            case " $auth_ignore " in *" $a "*) ;; *) auth_ignore="$auth_ignore $a" ;; esac
        done
        auth_generated=$(sed -e "s#@ODOO_UNIT@#$odoo_service#" -e "s#@BACKEND@#$auth_backend#" -e "s#@IGNOREIP@#$auth_ignore#" \
                              -e '/^# MODÈLE — ne pas copier tel quel/,/jail\.d\/odoo-auth\.conf\.$/c\# GÉNÉRÉ par nginx-hardening.sh --update pour ce serveur — ne pas éditer à la main (sera régénéré).' \
                              "$F2B_SRC_DIR/odoo-auth.jail.conf.template")
        if [[ -n "$ODOO_LOGFILE" ]]; then
            # Odoo writes to a FILE (logfile of its configuration): fail2ban reads it directly, not the systemd journal.
            auth_generated=$(printf '%s\n' "$auth_generated" | sed -e "s#^backend .*#backend      = auto#" -e "s#^journalmatch .*#logpath      = $ODOO_LOGFILE\nlogtimezone  = UTC#")
            auth_backend="auto, logpath $ODOO_LOGFILE"
        fi
        auth_state="absent"
        if [[ -f "$AUTH_JAIL_DST" && -f "$AUTH_FILTER_DST" ]]; then
            if [[ "$(cat "$AUTH_JAIL_DST")" == "$auth_generated" ]] && cmp -s "$F2B_SRC_DIR/odoo-auth.filter.conf" "$AUTH_FILTER_DST"; then
                auth_state="à jour"
            else
                auth_state="différent"
            fi
        fi
        case "$auth_state" in
            "à jour")
                pass "Jail odoo-auth à jour (service $odoo_service, backend $auth_backend, $(wc -w <<< "$auth_ignore") IP jamais bannies)."
                F2B_INSTALLED_JAILS+=(odoo-auth) ;;
            *)
                if [[ "$CHECK_ONLY" == "1" ]]; then
                    if [[ "$auth_state" == "absent" ]]; then
                        fail "Jail odoo-auth absent — la force brute sur la page de connexion d'Odoo n'est détectée par rien (relancer avec --update)."
                    else
                        warn "Jail odoo-auth différent de ce qui serait généré aujourd'hui (service, liste blanche nginx ou filtre modifiés) — relancer avec --update pour le régénérer."
                        F2B_INSTALLED_JAILS+=(odoo-auth)
                    fi
                else
                    mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d 2>/dev/null || true
                    migrer_chemin "$AUTH_JAIL_DST.avant-setup" "$AUTH_JAIL_DST.before-setup"
                    [[ -f "$AUTH_JAIL_DST" ]] && run cp -p "$AUTH_JAIL_DST" "$AUTH_JAIL_DST.before-setup" 2>/dev/null
                    if run cp "$F2B_SRC_DIR/odoo-auth.filter.conf" "$AUTH_FILTER_DST" 2>/dev/null && printf '%s\n' "$auth_generated" > "$AUTH_JAIL_DST"; then
                        if [[ "$auth_state" == "absent" ]]; then auth_verbe="installé"; else auth_verbe="régénéré"; fi
                        pass "Jail odoo-auth $auth_verbe (service $odoo_service, backend $auth_backend, IP jamais bannies : $auth_ignore)."
                        NEED_FAIL2BAN_RESTART=1
                        F2B_INSTALLED_JAILS+=(odoo-auth)
                    else
                        warn "Impossible d'écrire le jail odoo-auth (permissions ?)."
                    fi
                fi ;;
        esac
    fi

    # --- 9c) Jails reellement CHARGES par fail2ban (des fichiers presents ne suffisent pas : erreur de syntaxe,
    # fail2ban pas recharge depuis l'installation, journal introuvable...). Apres --update, verifie en fin de script,
    # une fois fail2ban recharge.
    verifier_ignoreip

    if [[ "$NEED_FAIL2BAN_RESTART" == "0" ]]; then
        for j in "${F2B_INSTALLED_JAILS[@]}"; do
            if run fail2ban-client status "$j" >/dev/null 2>&1; then
                pass "Jail $j chargé et actif dans fail2ban."
            elif [[ "$EUID" -ne 0 ]]; then
                sans_root_verif "Jail $j (fail2ban-client status)"
            else
                fail "Jail $j : fichiers présents mais jail NON chargé par fail2ban — voir « fail2ban-client reload » puis « journalctl -u fail2ban -n 30 » (erreur de syntaxe, journal introuvable ?)."
            fi
        done
    fi
fi
echo

# --- 9b) Jail nginx-sqli defined by hand on the server (jail.local): logpath must also read blocked-probes.log ---
# 2.59: the refusals of the nginx rules are written to blocked-probes.log. The jail nginx-sqli read only the access logs, so an
# injection refused by nginx was never counted. The jail is NOT copied from the repository (its filter is local to the server):
# only its logpath line changes. Same rules as 0f: the difference is shown, nothing changes without confirmation (--update),
# a dated backup is kept, fail2ban is reloaded, and the jail's file list is checked; if that fails, the backup is restored.
F2B_SQLI_JAIL="nginx-sqli"
F2B_SQLI_LOG="/var/log/nginx/blocked-probes.log"
f2b_jail_fichier() {      # $1 jail: file that defines [$1] (jail.local, jail.d/*.conf, jail.conf); prints it, returns 1 if none
    local f
    for f in /etc/fail2ban/jail.local /etc/fail2ban/jail.d/*.conf /etc/fail2ban/jail.conf; do
        [[ -r "$f" ]] || continue
        if awk -v j="$1" '$0 ~ "^[[:space:]]*\\[" j "\\][[:space:]]*$" { found = 1 } END { exit !found }' "$f"; then
            echo "$f"; return 0
        fi
    done
    return 1
}
f2b_section_contient() {  # $1 file, $2 jail, $3 log: 0 if the logpath of [$2] already reads $3
    awk -v j="$2" -v journal="$3" '
        /^[[:space:]]*\[/ { dans = ($0 ~ "^[[:space:]]*\\[" j "\\][[:space:]]*$") }
        dans && index($0, journal) { ok = 1 }
        END { exit !ok }' "$1"
}
f2b_logpath_ajouter() {   # $1 file, $2 jail, $3 log: the file with $3 added after the first logpath line of [$2] (stdout)
    awk -v j="$2" -v journal="$3" '
        /^[[:space:]]*\[/ { dans = ($0 ~ "^[[:space:]]*\\[" j "\\][[:space:]]*$") }
        { print }
        dans && !fait && /^[[:space:]]*logpath[[:space:]]*=/ { print "           " journal; fait = 1 }' "$1"
}
echo "--- 9b) Jail $F2B_SQLI_JAIL : journaux lus (blocked-probes.log) ---"
if [[ "$APP_NAME" != "odoo" ]]; then
    sans_objet "jail $F2B_SQLI_JAIL (Odoo seulement)"
elif ! command -v fail2ban-client >/dev/null 2>&1; then
    sans_objet "jail $F2B_SQLI_JAIL (fail2ban absent)"
elif ! F2B_SQLI_FICHIER=$(f2b_jail_fichier "$F2B_SQLI_JAIL"); then
    sans_objet "jail $F2B_SQLI_JAIL non définie sur ce serveur"
elif [[ ! -e "$F2B_SQLI_LOG" ]]; then
    warn "$F2B_SQLI_LOG absent : nginx le crée au premier refus de ses règles ; relancer ensuite."
elif f2b_section_contient "$F2B_SQLI_FICHIER" "$F2B_SQLI_JAIL" "$F2B_SQLI_LOG"; then
    pass "Jail $F2B_SQLI_JAIL : $F2B_SQLI_LOG déjà lu ($F2B_SQLI_FICHIER)."
else
    F2B_TMP=$(mktemp "${TMPDIR:-/tmp}/f2b-logpath.XXXXXX")
    f2b_logpath_ajouter "$F2B_SQLI_FICHIER" "$F2B_SQLI_JAIL" "$F2B_SQLI_LOG" > "$F2B_TMP"
    if cmp -s "$F2B_SQLI_FICHIER" "$F2B_TMP"; then
        warn "Jail $F2B_SQLI_JAIL : aucune ligne logpath dans $F2B_SQLI_FICHIER : ajouter $F2B_SQLI_LOG à la main."
    else
        echo "  Changement prévu pour $F2B_SQLI_FICHIER (jail $F2B_SQLI_JAIL, lecture de $F2B_SQLI_LOG) :"
        diff -u "$F2B_SQLI_FICHIER" "$F2B_TMP" | sed -n '3,20p' | sed 's/^/      /' || true
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "Jail $F2B_SQLI_JAIL : journal $F2B_SQLI_LOG non lu (relancer avec --update pour l'ajouter après confirmation)."
        else
            F2B_REP=""
            if [[ -t 0 ]]; then read -r -p "  Appliquer ce changement à $F2B_SQLI_FICHIER et recharger fail2ban ? [o/N] " F2B_REP || F2B_REP=""
            else warn "Pas de terminal : jail $F2B_SQLI_JAIL non modifiée (lancer --update dans un terminal pour confirmer)."; fi
            if [[ "$F2B_REP" =~ ^[oOyY]$ ]]; then
                F2B_BAK="$F2B_SQLI_FICHIER.before-logpath-$(date +%Y%m%d-%H%M%S)"
                cp -p "$F2B_SQLI_FICHIER" "$F2B_BAK"
                cat "$F2B_TMP" > "$F2B_SQLI_FICHIER"
                if fail2ban-client reload >/dev/null 2>&1 && fail2ban-client status "$F2B_SQLI_JAIL" 2>/dev/null | grep_q "$F2B_SQLI_LOG"; then
                    pass "Jail $F2B_SQLI_JAIL : $F2B_SQLI_LOG ajouté ; sauvegarde : $F2B_BAK."
                else
                    cp -p "$F2B_BAK" "$F2B_SQLI_FICHIER"
                    fail2ban-client reload >/dev/null 2>&1 || true
                    fail "Jail $F2B_SQLI_JAIL : fail2ban n'a pas pris le changement : retour à $F2B_SQLI_FICHIER d'origine (sauvegarde : $F2B_BAK)."
                fi
            else
                warn "Jail $F2B_SQLI_JAIL : aucun changement appliqué (refusé ou sans réponse)."
            fi
        fi
    fi
    rm -f "$F2B_TMP"
fi
echo

# --- 10) HSTS reellement envoye par chaque nom public servi en HTTPS ------------------------------------------------
# Test EMPIRIQUE : pour chaque nom declare par une directive server_name dans la config active, une vraie requete
# HTTPS est faite en local (curl --resolve NOM:443:127.0.0.1, donc avec le bon SNI) et l'en-tete
# Strict-Transport-Security est cherche dans la reponse. Remplace l'analyse statique des versions 1.10 a 1.13, qui
# wrongly assumed that "nginx -T" expands the include() directives: it does NOT - it displays each file
# separement, l'un apres l'autre. Un bloc server dont le server_name ou le HSTS vient d'un fichier inclus (cas de
# TOUS les vhosts de ce projet : snippets/odoo/*.name.conf et _odoo-common.conf) etait donc juge a tort sans nom
# ou sans HSTS. Le test empirique voit exactement ce qu'un navigateur recevrait, include() et heritage compris.
# Diagnostic seulement, jamais d'edition de la config.
else
    sans_objet "jails du capteur catch-all et des connexions Odoo (capteur : HAProxy aiguille le port 443 de BBB)"
    durcir_bbb
    # Team addresses ignored by fail2ban: also applies to BigBlueButton (sshd jail in particular).
    if command -v fail2ban-client >/dev/null 2>&1; then verifier_ignoreip; fi
fi
echo "--- 10) HSTS réellement envoyé par chaque nom servi en HTTPS ---"
if ! command -v nginx >/dev/null 2>&1; then
    warn "nginx introuvable — étape ignorée."
elif ! command -v curl >/dev/null 2>&1; then
    warn "curl introuvable — impossible de tester HSTS réellement (apt install curl)."
else
    nginx_dump=$(run nginx -T 2>/dev/null) || true
    # Noms declares dans TOUS les fichiers affiches par nginx -T (y compris les snippets inclus), hors commentaires,
    # hors "_" (capteur catch-all : ferme la connexion en 444 sans jamais servir de contenu, HSTS sans objet) et hors
    # noms generiques ou expressions regulieres (commencant par ~ ou contenant *), non testables tels quels.
    # Commentaire retire d'abord (tout ce qui suit un #), puis chaque occurrence de server_name est lue, meme sur une
    # ligne compacte du type "server { listen 80; server_name a b; }".
    hsts_names=$(printf '%s\n' "$nginx_dump" | awk '
        { line = $0; c = index(line, "#"); if (c > 0) line = substr(line, 1, c - 1)
          while ((p = index(line, "server_name")) > 0) {
              before = (p > 1) ? substr(line, p - 1, 1) : " "
              line = substr(line, p + 11)
              if (before !~ /[[:space:];{]/ || line !~ /^[[:space:]]/) continue
              e = index(line, ";"); part = (e > 0) ? substr(line, 1, e - 1) : line
              n = split(part, names, /[[:space:]]+/)
              for (i = 1; i <= n; i++) if (names[i] != "" && names[i] != "_" && names[i] !~ /^~/ && names[i] !~ /\*/) print names[i]
          } }' | sort -u) || true
    if [[ -z "$hsts_names" ]]; then
        warn "Aucun server_name testable trouvé dans \"nginx -T\" — nginx est-il installé et configuré ?"
    else
        browser_ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        while IFS= read -r hname; do
            [[ -z "$hname" ]] && continue
            hdrs=$(run curl -sk -o /dev/null -D - --max-time 8 -A "$browser_ua" \
                   --resolve "$hname:443:127.0.0.1" "https://$hname/" 2>/dev/null) || hdrs=""
            if [[ -z "$hdrs" ]]; then
                # Pas de reponse HTTPS pour ce nom : typiquement un nom declare uniquement dans un bloc port 80, qui
                # retombe en HTTPS sur le capteur catch-all (connexion fermee sans reponse, 444). Pas un defaut HSTS.
                echo "  [INFO] $hname : aucune réponse HTTPS en local (nom servi seulement en HTTP, ou certificat/bloc 443 absent) — HSTS non applicable."
                continue
            fi
            hcode=$(printf '%s\n' "$hdrs" | awk 'NR==1{print $2}') || true
            hsts_val=$(printf '%s\n' "$hdrs" | tr -d '\r' | awk 'tolower($0) ~ /^strict-transport-security:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }') || true
            if [[ -n "$hsts_val" ]]; then
                max_age=$(printf '%s' "$hsts_val" | grep -oE 'max-age=[0-9]+' | cut -d= -f2) || true
                if [[ -n "$max_age" ]] && (( max_age < 86400 )); then
                    pass "HSTS présent — $hname (HTTP $hcode, max-age=${max_age}s : encore court — normal après un déploiement initial, à remonter à 31536000 après quelques jours sans problème)"
                else
                    pass "HSTS présent — $hname (HTTP $hcode, ${hsts_val})"
                fi
            else
                # Redirect to the SAME name (e.g. "/" -> "/b" of BBB): the arrival page is checked too. If it
                # carries HSTS, the browser records it: warning (header to add to the redirects too).
                hsts_arrivee=""; chemin_arrivee=""
                if [[ "$hcode" =~ ^30[1278]$ ]]; then
                    loc=$(printf '%s\n' "$hdrs" | tr -d '\r' | awk 'tolower($0) ~ /^location:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }') || loc=""
                    case "$loc" in
                        /*) chemin_arrivee="$loc" ;;
                        "https://$hname"|"https://$hname/"*) chemin_arrivee="/${loc#https://"$hname"/}" ;;
                    esac
                    if [[ -n "$chemin_arrivee" ]]; then
                        hsts_arrivee=$(run curl -sk -o /dev/null -D - --max-time 8 -A "$browser_ua" --resolve "$hname:443:127.0.0.1" \
                            "https://$hname$chemin_arrivee" 2>/dev/null | tr -d '\r' \
                            | awk 'tolower($0) ~ /^strict-transport-security:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }') || hsts_arrivee=""
                    fi
                fi
                if [[ -n "$hsts_arrivee" ]]; then
                    # HSTS is recorded by the browser on the final HTTPS response: a redirect that does not carry it
                    # (BBB: "/" -> Greenlight) has no consequence as long as the arrival page sends it. Compliant.
                    pass "HSTS présent — $hname (la redirection HTTP $hcode n'en porte pas, mais la page d'arrivée $chemin_arrivee l'envoie : $hsts_arrivee ; le navigateur l'enregistre)"
                else
                    if [[ "${TLS_TERMINATION:-nginx}" == "haproxy" ]]; then
                        conseil="dans /etc/haproxy/haproxy.cfg, section « frontend » du 443, ajoutez « http-after-response set-header Strict-Transport-Security \"max-age=300; includeSubDomains\" » (HAProxy 2.2 et suivants ; contrairement à http-response, s'applique AUSSI aux redirections produites par HAProxy), puis haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy ; max-age à remonter à 31536000 après quelques jours sans problème. Attention : bbb-install peut régénérer ce fichier lors d'une mise à jour."
                    else
                        conseil="dans le fichier sites-available/ du bloc server 443 qui sert ce nom, ajoutez « include /etc/nginx/snippets/odoo/hsts.conf; » au niveau server (un bloc de redirection), ou vérifiez qu'il inclut bien _odoo-common.conf (un bloc qui sert Odoo) ; add_header … always pour qu'il s'applique aussi aux redirections et erreurs ; puis nginx -t && systemctl reload nginx. Pour trouver le fichier : grep -rln \"$hname\" /etc/nginx/"
                    fi
                    # (complement built separately: an apostrophe in "${x:+...}" between quotes breaks bash parsing)
                    precision=""; if [[ -n "$chemin_arrivee" ]]; then precision=", et sur la page d'arrivée $chemin_arrivee"; fi
                    fail "HSTS ABSENT — $hname (HTTP $hcode$precision). Quoi faire : $conseil"
                fi
            fi
        done <<< "$hsts_names"
    fi
fi
echo

if ! [[ "$LOG_RETENTION_MONTHS" =~ ^[0-9]+$ ]] || (( LOG_RETENTION_MONTHS < 1 || LOG_RETENTION_MONTHS > 24 )); then
    echo "ERREUR: --log-retention-months attend un nombre de mois entre 1 et 24 (reçu : $LOG_RETENTION_MONTHS)." >&2
    exit 1
fi
echo "--- 11) Rétention des journaux (cible : $LOG_RETENTION_MONTHS mois) ---"
# Rotation de nginx et de fail2ban (/etc/logrotate.d/) et duree de conservation du journal systemd. Debian garde par
# default 14 days of nginx logs (daily rotation, "rotate 14"): insufficient for reports over 30 days
# and more (web-monitor.py --summary). --update adjusts "rotate" according to the frequency (daily: 92, weekly:
# 14, mensuelle : 4), apres une copie de sauvegarde (.before-nginx-hardening), valide la syntaxe (logrotate -d) et
# restaure la copie en cas d'erreur. Journal systemd : MaxRetentionSec=Nmonth (garde au plus N mois).
RETENTION_CIBLE=$(( (LOG_RETENTION_MONTHS * 61 + 1) / 2 ))   # months of 30.5 days: 3 -> 92, 6 -> 183, 12 -> 366
LOGROTATE_DIR="${NGINX_HARDENING_LOGROTATE_DIR:-/etc/logrotate.d}"
for lr_nom in nginx fail2ban; do
    lr_f="$LOGROTATE_DIR/$lr_nom"
    if [[ ! -r "$lr_f" ]]; then
        warn "$lr_f absent ou illisible — rotation de $lr_nom non vérifiable."
        continue
    fi
    lr_freq=$(grep -oE '^[[:space:]]*(daily|weekly|monthly)\b' "$lr_f" | head -1 | tr -d '[:space:]') || true
    [[ -z "$lr_freq" ]] && lr_freq="weekly"
    lr_n=$(grep -oE '^[[:space:]]*rotate[[:space:]]+[0-9]+' "$lr_f" | head -1 | awk '{print $2}') || true
    [[ -z "$lr_n" ]] && lr_n=4
    case "$lr_freq" in daily) lr_m=1; lr_fr="quotidienne" ;; weekly) lr_m=7; lr_fr="hebdomadaire" ;; *) lr_m=30; lr_fr="mensuelle" ;; esac
    lr_jours=$((lr_n * lr_m))
    # Rotation actually performed? On Ubuntu, /var/log belongs to the syslog group, which can write there: logrotate
    # then REFUSES to rotate the logs of this directory without a "su" directive ("parent directory has insecure
    # permissions") - the log therefore did not rotate at all, whatever "rotate".
    lr_err=""
    if command -v logrotate >/dev/null 2>&1; then
        lr_err=$(run logrotate -d "$lr_f" 2>&1 | grep -m1 -iE '^error:' || true)
    fi
    lr_su=0
    if [[ "$lr_err" == *"insecure permissions"* ]] && ! grep_q -E '^[[:space:]]*su[[:space:]]' "$lr_f"; then lr_su=1; fi
    if (( lr_jours >= RETENTION_CIBLE && lr_su == 0 )); then
        pass "$lr_nom : rotation $lr_fr, $lr_n conservés ≈ $lr_jours jours ($lr_f)"
        continue
    fi
    lr_cible=$(( (RETENTION_CIBLE + lr_m - 1) / lr_m ))
    (( lr_jours >= RETENTION_CIBLE )) && lr_cible=$lr_n
    if [[ "$CHECK_ONLY" == "1" ]]; then
        (( lr_su )) && warn "$lr_nom : NE TOURNE PAS — logrotate refuse ($lr_err) ; --update ajoutera la directive « su » à $lr_f."
        (( lr_jours < RETENTION_CIBLE )) && warn "$lr_nom : ≈ $lr_jours jours seulement (rotation $lr_fr, rotate $lr_n) — --update passera à « rotate $lr_cible » (≈ $LOG_RETENTION_MONTHS mois)."
        continue
    fi
    migrer_chemin "$lr_f.avant-nginx-hardening" "$lr_f.before-nginx-hardening"      # nom anglais (2.1)
    [[ -e "$lr_f.before-nginx-hardening" ]] || cp -p "$lr_f" "$lr_f.before-nginx-hardening"
    lr_fait=()
    if (( lr_cible != lr_n )); then
        sed -i -E "0,/^([[:space:]]*)rotate[[:space:]]+[0-9]+/s//\1rotate $lr_cible/" "$lr_f"
        lr_fait+=("« rotate $lr_n » → « rotate $lr_cible » (≈ $LOG_RETENTION_MONTHS mois)")
    fi
    if (( lr_su )); then
        # su <owner> <group> of the log itself (fallback: root adm, the Debian/Ubuntu usage for /var/log).
        lr_journal=$(awk '/^[[:space:]]*\// { print $1; exit }' "$lr_f")
        lr_proprio=""
        for lr_j in $lr_journal; do [[ -e "$lr_j" ]] && lr_proprio=$(stat -c '%U %G' "$lr_j" 2>/dev/null) && break; done
        lr_proprio=${lr_proprio:-root adm}
        sed -i -E "0,/\{[[:space:]]*$/s//{\n    su $lr_proprio/" "$lr_f"
        lr_fait+=("directive « su $lr_proprio » ajoutée (le journal ne tournait pas : $lr_err)")
    fi
    if (( lr_cible != lr_n )) && ! grep_q -E "^[[:space:]]*rotate[[:space:]]+$lr_cible\b" "$lr_f"; then
        warn "$lr_nom : aucune ligne « rotate » modifiable dans $lr_f — ajoutez « rotate $lr_cible » à la main."
    elif command -v logrotate >/dev/null 2>&1 && lr_err2=$(run logrotate -d "$lr_f" 2>&1 | grep -m1 -iE '^error:') && [[ -n "$lr_err2" ]]; then
        cp -p "$lr_f.before-nginx-hardening" "$lr_f"
        fail "$lr_nom : $lr_f refusé par logrotate après modification ($lr_err2) — copie d'origine restaurée."
    else
        lr_msg=$(IFS=';'; echo "${lr_fait[*]}")
        pass "$lr_nom : ${lr_msg//;/ ; } dans $lr_f (copie : $lr_f.before-nginx-hardening)"
    fi
done
# Journal systemd : celui de l'application si elle journalise dans un namespace isole (LogNamespace), sinon le general.
jr_ns=""
if [[ "$APP_NAME" == "odoo" ]]; then
    for jr_svc in $ODOO_CONF_UNITES ${DETECT_UNITS:-erplibre.service erplibre_erplibre.service odoo.service}; do
        if systemctl list-unit-files "$jr_svc" --no-legend 2>/dev/null | awk '{print $1}' | grep_q -xF "$jr_svc"; then
            jr_ns=$(systemctl show -p LogNamespace --value "$jr_svc" 2>/dev/null) || jr_ns=""
            break
        fi
    done
fi
JOURNALD_DIR="${NGINX_HARDENING_JOURNALD_DIR:-/etc/systemd}"
if [[ -n "$jr_ns" ]]; then
    jr_f="$JOURNALD_DIR/journald@$jr_ns.conf"; jr_unit="systemd-journald@$jr_ns"
else
    jr_f="$JOURNALD_DIR/journald.conf.d/90-nginx-hardening-retention.conf"; jr_unit="systemd-journald"
fi
# Value read into a variable: grep returns 2 if journald.conf is absent EVEN when it finds the line elsewhere -
# with pipefail, "grep ... | grep_q ." then concluded "no fixed duration" and ADDED a second line.
jr_actuel=$(grep -rhsE '^[[:space:]]*MaxRetentionSec=' "$JOURNALD_DIR/journald.conf" "$JOURNALD_DIR/journald.conf.d/" \
            ${jr_ns:+"$jr_f"} 2>/dev/null | tail -1 | tr -d '[:space:]') || true
if [[ -n "$jr_actuel" ]]; then
    if [[ "$RETENTION_EXPLICITE" != "1" || "$jr_actuel" == "MaxRetentionSec=${LOG_RETENTION_MONTHS}month" ]]; then
        pass "Journal systemd${jr_ns:+ (namespace $jr_ns)} : durée de conservation déjà fixée ($jr_actuel)"
    elif ! grep -qsE '^[[:space:]]*MaxRetentionSec=' "$jr_f"; then
        warn "Journal systemd : $jr_actuel est fixé hors de $jr_f — à remplacer à la main par MaxRetentionSec=${LOG_RETENTION_MONTHS}month."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Journal systemd${jr_ns:+ (namespace $jr_ns)} : $jr_actuel — --update passera à MaxRetentionSec=${LOG_RETENTION_MONTHS}month dans $jr_f."
    else
        sed -i -E "s/^[[:space:]]*MaxRetentionSec=.*/MaxRetentionSec=${LOG_RETENTION_MONTHS}month/" "$jr_f"
        if systemctl restart "$jr_unit" >/dev/null 2>&1; then
            pass "Journal systemd${jr_ns:+ (namespace $jr_ns)} : $jr_actuel → MaxRetentionSec=${LOG_RETENTION_MONTHS}month dans $jr_f, $jr_unit redémarré."
        else
            warn "Journal systemd : MaxRetentionSec=${LOG_RETENTION_MONTHS}month écrit dans $jr_f, mais redémarrage de $jr_unit impossible — à faire à la main."
        fi
    fi
elif [[ "$CHECK_ONLY" == "1" ]]; then
    warn "Journal systemd${jr_ns:+ (namespace $jr_ns)} : aucune durée fixée (limité seulement par la taille) — --update ajoutera MaxRetentionSec=${LOG_RETENTION_MONTHS}month dans $jr_f."
else
    mkdir -p "$(dirname "$jr_f")"
    if [[ -f "$jr_f" ]] && grep_q -E '^\[Journal\]' "$jr_f"; then
        sed -i -E "/^\\[Journal\\]/a MaxRetentionSec=${LOG_RETENTION_MONTHS}month" "$jr_f"
    else
        printf '# Ajouté par nginx-hardening.sh : conservation des journaux (%s mois au plus).\n[Journal]\nMaxRetentionSec=%smonth\n' \
            "$LOG_RETENTION_MONTHS" "$LOG_RETENTION_MONTHS" >> "$jr_f"
    fi
    if run systemctl restart "$jr_unit" >/dev/null 2>&1; then
        pass "Journal systemd${jr_ns:+ (namespace $jr_ns)} : MaxRetentionSec=${LOG_RETENTION_MONTHS}month ajouté dans $jr_f, $jr_unit redémarré."
    else
        warn "Journal systemd : MaxRetentionSec=${LOG_RETENTION_MONTHS}month ajouté dans $jr_f, mais redémarrage de $jr_unit impossible — à faire à la main."
    fi
fi
echo

# nginx_plus_ancien_que FILE...: 0 if nginx runs with a configuration OLDER than one of these files (modified after the last load:
# it must be reloaded), 1 if the loaded configuration is up to date, 2 if it cannot be known (nginx stopped, ps absent). nginx does not say which
# configuration it loaded: at each reload it starts NEW worker processes, whose age (the youngest) is the age of the
# configuration. NGINX_HARDENING_WORKER_AGE (secondes) remplace cette mesure (essais).
nginx_plus_ancien_que() {
    local age_config="${NGINX_HARDENING_WORKER_AGE:-}" maitre f modif maintenant plus_recent=""
    if [[ -z "$age_config" ]]; then
        command -v ps >/dev/null 2>&1 || return 2
        maitre=$(head -n 1 "${NGINX_HARDENING_NGINX_PID:-/run/nginx.pid}" 2>/dev/null)
        [[ "$maitre" =~ ^[0-9]+$ ]] || return 2
        age_config=$(ps -o etimes= --ppid "$maitre" 2>/dev/null | tr -d ' ' | grep -E '^[0-9]+$' | sort -n | head -1)
    fi
    [[ "$age_config" =~ ^[0-9]+$ ]] || return 2
    maintenant=$(date +%s)
    for f in "$@"; do
        [[ -f "$f" ]] || continue
        modif=$(stat -c %Y "$f" 2>/dev/null) || continue
        (( maintenant - modif + 1 < age_config )) && plus_recent="$f"      # file modified AFTER the workers started (tolerance: 1 s)
    done
    [[ -n "$plus_recent" ]]
}

# --- 11b) Odoo log in FILE (logfile of its configuration): must be rotated (logrotate), otherwise it grows endlessly ---
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" && -n "$ODOO_LOGFILE" ]]; then
    echo "--- 11b) Journal d'Odoo en fichier ($ODOO_LOGFILE) ---"
    if [[ ! -e "$ODOO_LOGFILE" ]]; then
        warn "Le fichier $ODOO_LOGFILE (logfile de la configuration d'Odoo) n'existe pas encore — Odoo n'a pas démarré, ou le dossier n'est pas accessible en écriture."
    elif grep -rqsF -e "$ODOO_LOGFILE" -e "$(dirname "$ODOO_LOGFILE")/" /etc/logrotate.d /etc/logrotate.conf 2>/dev/null; then
        pass "Rotation : $ODOO_LOGFILE est couvert par logrotate."
    else
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "Aucune règle logrotate ne mentionne $ODOO_LOGFILE : il grossira sans fin — --update crée $LOGROTATE_DIR/odoo (weekly, rotate 13, compress, copytruncate, missingok, notifempty)."
        else
            lr_odoo="$LOGROTATE_DIR/odoo"                              # 2.51: directory of NGINX_HARDENING_LOGROTATE_DIR (was hard-coded /etc/logrotate.d)
            [[ -e "$lr_odoo" ]] && lr_odoo="$LOGROTATE_DIR/odoo-nginx-hardening"       # an "odoo" file already exists (other content): never overwritten
            lr_su=""
            lr_proprio=$(stat -c '%U %G' "$ODOO_LOGFILE" 2>/dev/null) || lr_proprio=""
            [[ -n "$lr_proprio" && "$lr_proprio" != "root root" ]] && lr_su="    su $lr_proprio"$'\n'
            if printf '%s\n' "# Généré par nginx-hardening.sh : rotation du journal d'Odoo (logfile de sa configuration)." \
                    "$ODOO_LOGFILE {" "    weekly" "    rotate 13" "    compress" "    delaycompress" "    copytruncate" "    missingok" "    notifempty" \
                    "${lr_su%$'\n'}" "}" | grep -v '^$' > "$lr_odoo" 2>/dev/null; then
                if lr_err3=$(run logrotate -d "$lr_odoo" 2>&1 | grep -m1 -iE '^error:') && [[ -n "$lr_err3" ]]; then
                    warn "$lr_odoo créé mais logrotate -d signale : $lr_err3"
                else
                    pass "$lr_odoo créé : $ODOO_LOGFILE tourné chaque semaine, 13 copies compressées conservées (≈ 3 mois)."
                fi
            else
                warn "Impossible de créer $lr_odoo — à faire à la main (weekly, rotate 13, compress, copytruncate, missingok, notifempty)."
            fi
        fi
    fi
    echo "  Note : app-log-live.py lit ce fichier ; app-log-check.py et web-monitor.py ne lisent que le journal systemd d'Odoo (ils ne verront pas ses lignes)."
    echo
fi

# --- 12) Team addresses in nginx (files GENERATED from apps/team-ips.list) ---
# A single list to maintain: the $is_trusted_ip table and the allow lists include team-ips-geo.conf and
# team-ips-allow.conf. Atomic write (temporary file in the same directory, then mv), nginx -t BEFORE any
# reload; on refusal, the old version is restored and nginx is not reloaded.
echo "--- 12) Listes d'adresses : liste blanche et lieux (/etc/default/nginx-tools-*.conf) → nginx ---"
migrer_listes
listes_resume >&2
if [[ "$APP_NAME" != "odoo" ]]; then
    sans_objet "fichiers team-ips-*.conf de la configuration nginx-odoo (les listes restent lues par les outils)"
elif [[ -z "$(listes_fichier_blanche)" ]]; then
    # nginx REFUSES a wildcard include without any matching file ([emerg] open() ... No such file):
    # so we make sure both files exist (at least empty, as a comment) even without a white list.
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    if [[ "$CHECK_ONLY" != "1" ]]; then
        for eq_type in geo allow; do
            if [[ ! -e "$snip/team-ips-$eq_type.conf" ]]; then
                mkdir -p "$snip" && printf '%s\n' "# vide — liste blanche introuvable (nginx refuse un include sans fichier)" > "$snip/team-ips-$eq_type.conf" && chmod 644 "$snip/team-ips-$eq_type.conf" \
                    && echo "        $snip/team-ips-$eq_type.conf créé (vide) pour que nginx -t réussisse."
            fi
        done
    fi
    warn "Liste blanche introuvable : aucune adresse n'est générée dans team-ips-*.conf (la gestion des bases de DEV et tout LAB resteraient fermés à tous) — remplir /etc/default/nginx-tools-white-list.conf puis relancer --update."
else
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    generer_equipe geo >/dev/null
    if [[ -n "$EQUIPE_INVALIDES" ]]; then
        fail "liste blanche : entrée(s) invalide(s) —${EQUIPE_INVALIDES%;} — rien n'est écrit dans nginx tant qu'elles ne sont pas corrigées."
    else
        eq_change=0; declare -A eq_ancien=()
        for eq_type in geo allow; do
            eq_dst="$snip/team-ips-$eq_type.conf"
            eq_nouveau=$(generer_equipe "$eq_type")
            if [[ -f "$eq_dst" ]] && [[ "$(cat "$eq_dst")" == "$eq_nouveau" ]]; then
                pass "$eq_dst à jour ($(grep -c '^[^#]' "$eq_dst") adresse(s))."
            elif [[ "$CHECK_ONLY" == "1" ]]; then
                warn "$eq_dst $([[ -f "$eq_dst" ]] && echo "différent de la liste blanche" || echo "absent") — --update le régénérera."
            else
                [[ -f "$eq_dst" ]] && eq_ancien[$eq_type]=$(cat "$eq_dst")
                mkdir -p "$snip"
                eq_tmp=$(mktemp "$snip/.team-ips-$eq_type.XXXXXX")
                printf '%s\n' "$eq_nouveau" > "$eq_tmp" && chmod 644 "$eq_tmp" && mv -f "$eq_tmp" "$eq_dst"
                eq_change=1
            fi
        done
        if (( eq_change )); then
            fragments_generes_assurer || true        # shared-ips-geo.conf (step 12b) must exist BEFORE this nginx -t, otherwise team addresses would be restored for nothing
            if eq_erreur=$(run nginx -t 2>&1); then
                if nginx_appliquer; then
                    pass "Adresses de l'équipe régénérées depuis la liste blanche ; nginx -t réussi, nginx $NGINX_APPLIQUE."
                else
                    warn "Adresses de l'équipe régénérées et nginx -t réussi, mais nginx n'a pas pu être $NGINX_APPLIQUE — systemctl status nginx --no-pager ; journalctl -u nginx -n 30 --no-pager."
                fi
            else
                for eq_type in geo allow; do
                    # Never rm: a wildcard include without file makes nginx -t fail. Without an old version: valid empty file.
                    if [[ -n "${eq_ancien[$eq_type]+x}" ]]; then printf '%s\n' "${eq_ancien[$eq_type]}" > "$snip/team-ips-$eq_type.conf"
                    else printf '%s\n' "# vide — restauré après refus de nginx -t" > "$snip/team-ips-$eq_type.conf"; fi
                done
                fail "nginx -t refuse la configuration avec les adresses régénérées — ancienne version restaurée, nginx NON rechargé (nginx -t pour le détail)."
                # nginx's own message, then the proof: does nginx -t ALSO refuse the previous version? Then the addresses are not to blame: the configuration was already invalid.
                printf '%s\n' "$eq_erreur" | head -8 | sed 's/^/        nginx -t : /'
                echo "        Fichiers présents (dossier $snip) :"
                { ls -ld "$snip" "$snip"/team-ips-* 2>&1 || true; } | sed 's/^/          /'
                if ! eq_avant=$(run nginx -t 2>&1); then
                    echo "        nginx -t refuse AUSSI la version d'avant : la configuration nginx est DÉJÀ invalide, indépendamment des adresses de l'équipe."
                    echo "        Corriger d'abord la cause ci-dessus (souvent un fichier de nginx-odoo-config.zip déployé à moitié : include ou variable absente)."
                    [[ "$eq_avant" != "$eq_erreur" ]] && printf '%s\n' "$eq_avant" | head -8 | sed 's/^/        nginx -t (version d'"'"'avant) : /'
                fi
            fi
        fi
        if (( ! eq_change )); then
            # Files already up to date, but has nginx LOADED them? (real case: address added, file regenerated, nginx never reloaded -> 403 for the new address)
            nginx_plus_ancien_que "$snip/team-ips-geo.conf" "$snip/team-ips-allow.conf" && eq_a_charger=1 || eq_a_charger=0
            if (( eq_a_charger )); then
                if [[ "$CHECK_ONLY" == "1" ]]; then
                    warn "Les fichiers team-ips-*.conf sont plus récents que la configuration chargée par nginx : les adresses récentes sont refusées (403) tant que nginx n'est pas rechargé — --update le recharge (ou systemctl reload nginx)."
                elif eq_erreur=$(run nginx -t 2>&1); then
                    if nginx_appliquer; then
                        pass "nginx $NGINX_APPLIQUE : team-ips-*.conf étaient plus récents que la configuration chargée."
                    else
                        warn "team-ips-*.conf plus récents que la configuration chargée, nginx -t réussi, mais nginx n'a pas pu être $NGINX_APPLIQUE — systemctl status nginx --no-pager ; journalctl -u nginx -n 30 --no-pager."
                    fi
                else
                    fail "team-ips-*.conf plus récents que la configuration chargée, mais nginx -t refuse la configuration — nginx NON rechargé."
                    printf '%s\n' "$eq_erreur" | head -8 | sed 's/^/        nginx -t : /'
                fi
            fi
        fi
        if command -v nginx >/dev/null 2>&1 && ! run nginx -T 2>/dev/null | grep_q 'team-ips-allow'; then
            warn "La configuration nginx active n'inclut pas encore team-ips-*.conf — déployer nginx-odoo-config.zip (odoo-global.conf, env-*.conf)."
        fi
    fi
fi
# --- 12b) Shared networks (places [shared]) -> shared-ips-geo.conf: wider rate limits for a room behind ONE address ---
if [[ "$APP_NAME" == "odoo" ]]; then
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    part_dst="$snip/shared-ips-geo.conf"
    part_nouveau=$(generer_partages)
    part_n=$(printf '%s\n' "$part_nouveau" | grep -c '^[^#]' || true)
    if [[ -f "$part_dst" ]] && [[ "$(cat "$part_dst")" == "$part_nouveau" ]]; then
        pass "$part_dst à jour ($part_n réseau(x) partagé(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "$part_dst $([[ -f "$part_dst" ]] && echo "différent des lieux [partagée]" || echo "absent") — --update le régénérera (nginx refuse l'include de odoo-global.conf sans ce fichier)."
    else
        part_ancien=""; [[ -f "$part_dst" ]] && part_ancien=$(cat "$part_dst")
        mkdir -p "$snip"
        part_tmp=$(mktemp "$snip/.shared-ips-geo.XXXXXX")
        printf '%s\n' "$part_nouveau" > "$part_tmp" && chmod 644 "$part_tmp" && mv -f "$part_tmp" "$part_dst"
        if part_erreur=$(run nginx -t 2>&1); then
            if nginx_appliquer; then
                pass "Réseaux partagés régénérés ($part_n) dans $part_dst ; nginx -t réussi, nginx $NGINX_APPLIQUE."
            else
                warn "Réseaux partagés régénérés ($part_n) et nginx -t réussi, mais nginx n'a pas pu être $NGINX_APPLIQUE — systemctl status nginx --no-pager ; journalctl -u nginx -n 30 --no-pager."
            fi
        else
            if [[ -n "$part_ancien" ]]; then printf '%s\n' "$part_ancien" > "$part_dst"; else printf '%s\n' "# vide — restauré après refus de nginx -t" > "$part_dst"; fi
            fail "nginx -t refuse la configuration avec les réseaux partagés régénérés — ancienne version restaurée, nginx NON rechargé."
            printf '%s\n' "$part_erreur" | head -8 | sed 's/^/        nginx -t : /'
        fi
    fi
fi
echo

# --- 12c) URI refusées (--disable-uri / --enable-uri) -> uri-desactivees.conf, inclus au début de securite-commune.conf ---
# La liste vit DANS le fichier (lignes « # uri : CHEMIN ») : un --update sans option la conserve.
# Une requête vers ce chemin (toutes langues : /shop, /es/shop, /en_CA/shop...) reçoit 404 avant le site.
if [[ "$APP_NAME" == "odoo" ]]; then
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    uri_dst="$snip/uri-desactivees.conf"
    declare -A uri_liste=()
    if [[ -f "$uri_dst" ]]; then
        while IFS= read -r ligne; do
            [[ "$ligne" == "# uri : "* ]] && uri_liste["${ligne#"# uri : "}"]=1
        done < "$uri_dst"
    fi
    if (( ${#DISABLE_URI_LIST[@]} > 0 )); then
        for u in "${DISABLE_URI_LIST[@]}"; do uri_liste["$u"]=1; done
    fi
    if (( ${#ENABLE_URI_LIST[@]} > 0 )); then
        for u in "${ENABLE_URI_LIST[@]}"; do unset "uri_liste[$u]"; done
    fi
    uri_nouveau="# Généré par nginx-hardening.sh (--disable-uri / --enable-uri) : ne pas éditer à la main."$'\n'
    if (( ${#uri_liste[@]} == 0 )); then
        uri_nouveau+="# Aucune URI refusée."$'\n'
    else
        mapfile -t uri_triees < <(printf '%s\n' "${!uri_liste[@]}" | sort)
        for u in "${uri_triees[@]}"; do uri_nouveau+="# uri : $u"$'\n'; done
        for u in "${uri_triees[@]}"; do
            motif="^(/[A-Za-z_-]+)?${u//./\\.}(/|\$)"
            uri_nouveau+="location ~ $motif { return 404; }"$'\n'
        done
    fi
    uri_n=${#uri_liste[@]}
    if [[ -f "$uri_dst" ]] && [[ "$(cat "$uri_dst")" == "$uri_nouveau" ]]; then
        pass "$uri_dst à jour ($uri_n URI refusée(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "$uri_dst $([[ -f "$uri_dst" ]] && echo "différent de la liste demandée" || echo "absent") — --update l'écrira ($uri_n URI refusée(s))."
    else
        uri_ancien=""; [[ -f "$uri_dst" ]] && uri_ancien=$(cat "$uri_dst")
        mkdir -p "$snip"
        uri_tmp=$(mktemp "$snip/.uri-desactivees.XXXXXX")
        printf '%s' "$uri_nouveau" > "$uri_tmp" && chmod 644 "$uri_tmp" && mv -f "$uri_tmp" "$uri_dst"
        if uri_erreur=$(run nginx -t 2>&1); then
            if nginx_appliquer; then
                pass "URI refusées ($uri_n) dans $uri_dst ; nginx -t réussi, nginx $NGINX_APPLIQUE."
            else
                warn "URI refusées ($uri_n) et nginx -t réussi, mais nginx n'a pas pu être $NGINX_APPLIQUE — systemctl status nginx --no-pager ; journalctl -u nginx -n 30 --no-pager."
            fi
        else
            if [[ -n "$uri_ancien" ]]; then printf '%s\n' "$uri_ancien" > "$uri_dst"; else printf '%s\n' "# vide — restauré après refus de nginx -t" > "$uri_dst"; fi
            fail "nginx -t refuse la configuration avec les URI refusées — ancienne version restaurée, nginx NON rechargé."
            printf '%s\n' "$uri_erreur" | head -8 | sed 's/^/        nginx -t : /'
        fi
    fi
fi
echo

# --- 13) Courriel des alertes : relais SMTP et DNS (MX, SPF, DMARC, DKIM) ---------------------------------------------
# Delegated to app-health-check.py --check-email-dns (same configuration as sending alerts): each line
# [OK]/[ATTN]/[FAIL] is counted here; the detail lines (DNS records to add) are displayed as they are.
# Diagnostic only: nothing is changed (DNS is set at the domain provider). Guide: doc/email-setup.md.
echo "--- 13) Courriel des alertes (relais SMTP, MX, SPF, DMARC, DKIM) ---"
if [[ ! -r "$SCRIPT_DIR/app-health-check.py" ]]; then
    warn "app-health-check.py introuvable à côté de ce script — vérification du courriel impossible."
else
    courriel_n=0; courriel_brut=""
    while IFS= read -r ligne_courriel; do
        case "$ligne_courriel" in
            "[OK] "*)   pass "${ligne_courriel#\[OK\] }"; courriel_n=$((courriel_n + 1)) ;;
            "[ATTN] "*) warn "${ligne_courriel#\[ATTN\] }"; courriel_n=$((courriel_n + 1)) ;;
            "[FAIL] "*) fail "${ligne_courriel#\[FAIL\] }"; courriel_n=$((courriel_n + 1)) ;;
            "       "*) echo "  $ligne_courriel" ;;                         # detail: DNS record to add
            *)          courriel_brut="${courriel_brut:-$ligne_courriel}" ;;
        esac
    done < <(NGINX_TOOLS_LANG=fr timeout --foreground 120 python3 "$SCRIPT_DIR/app-health-check.py" --check-email-dns 2>&1 || true)
    # No recognized result (program too old, error): never "all is in order" without verification.
    if (( courriel_n == 0 )); then
        warn "vérification du courriel impossible : app-health-check.py n'a produit aucun résultat reconnu${courriel_brut:+ (« ${courriel_brut:0:140} »)}."
    fi
    echo "  Envoi réel d'un courriel de test : $SCRIPT_DIR/app-health-check.py --test-email"
fi
echo

# --- 14) Pays des adresses IP : base locale (geoip-bin) ------------------------------------------------------------
# RECOMMENDED for all servers, not optional: without it, app-log-live.py looks up the country of EACH address on the Internet (rdap.org) -
# slow (one request per address) and dependent on an external service. With it: local reading, instant, without sending anything.
echo "--- 14) Pays des adresses IP : geoip-bin (base locale) ---"
if command -v geoiplookup >/dev/null 2>&1; then
    if geoiplookup 8.8.8.8 2>/dev/null | grep -qE 'Country Edition: [A-Z]{2},'; then
        pass "geoip-bin installé et sa base répond : le pays des adresses IP est lu localement (aucune requête Internet)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "geoip-bin est installé mais sa base de pays est introuvable (paquet geoip-database absent ?) : le pays est cherché sur Internet. --update installe geoip-database."
    elif run apt-get install -y geoip-database >/dev/null 2>&1; then
        pass "geoip-database installé : le pays des adresses IP est lu localement."
    else
        warn "installation de geoip-database en échec : lancer « apt-get install geoip-database » et lire l'erreur."
    fi
else
    geoip_candidat=$(apt-cache policy geoip-bin 2>/dev/null | awk '/Candidate:/ { print $2 }') || geoip_candidat=""
    if [[ -z "$geoip_candidat" || "$geoip_candidat" == "(none)" ]]; then
        warn "geoip-bin est introuvable dans les dépôts de cette distribution (apt-cache policy) : le pays de chaque adresse est cherché sur Internet (rdap.org)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "geoip-bin absent — RECOMMANDÉ (pas facultatif) : sans lui le pays de chaque adresse est cherché sur Internet. --update l'installe (apt-get install geoip-bin geoip-database)."
    elif run apt-get install -y geoip-bin geoip-database >/dev/null 2>&1; then
        pass "geoip-bin et geoip-database installés : le pays des adresses IP est lu localement (aucune requête Internet)."
    else
        warn "installation de geoip-bin en échec : lancer « apt-get install geoip-bin geoip-database » et lire l'erreur."
    fi
fi
echo

# --- 15) Bip d'app-log-live.py (--chime) dans byobu / tmux ---------------------------------------------------------
# byobu relies on tmux: by default tmux may swallow the bell (bell-action none, visual-bell on). We say WHICH configuration to change; nothing is changed.
if command -v byobu >/dev/null 2>&1 || command -v tmux >/dev/null 2>&1; then
    echo "--- 15) Bip d'app-log-live.py (--chime) dans byobu / tmux ---"
    bip_manque=()
    if command -v tmux >/dev/null 2>&1; then
        [[ "$(tmux show-options -gv bell-action 2>/dev/null)" == "any" ]] || bip_manque+=("set -g bell-action any")
        [[ "$(tmux show-options -gv visual-bell 2>/dev/null)" == "off" ]] || bip_manque+=("set -g visual-bell off")
        [[ "$(tmux show-options -gv allow-passthrough 2>/dev/null)" == "on" ]] || bip_manque+=("set -g allow-passthrough on")
    else
        bip_manque=("set -g bell-action any" "set -g visual-bell off" "set -g allow-passthrough on")
    fi
    if (( ${#bip_manque[@]} == 0 )); then
        pass "byobu/tmux laisse passer le bip (bell-action any, visual-bell off, allow-passthrough on)."
    else
        echo "  [INFO] byobu/tmux peut avaler le bip de « app-log-live.py --chime ». Pour l'entendre, ajouter ces lignes à la configuration PERSONNELLE de byobu"
        echo "         (fichier ~/.byobu/.tmux.conf, à créer au besoin ; pas de fichier système à toucher), puis recharger (touche F5 de byobu, ou « tmux source-file ~/.byobu/.tmux.conf ») :"
        printf '           %s\n' "${bip_manque[@]}"
        echo "         Essai immédiat, sans fichier (perdu à la fermeture de tmux) : tmux set -g bell-action any ; tmux set -g visual-bell off ; tmux set -g allow-passthrough on (tmux 3.3+)."
        echo "         Hors byobu/tmux, rien à changer. Le terminal (client SSH) doit aussi avoir le son actif pour la cloche."
    fi
    echo
fi

# --- 16) Odoo calls to its own public name (User-Agent "python-requests") ---
# Odoo (mass_mailing, theme preview...) calls its public name with python-requests: if nginx takes it for a robot (403), the pages that use it break.
# On refait, DEPUIS le serveur et SANS --resolve (donc par l'adresse publique, comme Odoo), la commande de diagnostic : curl -sI -A python-requests/2.31 https://NOM/mass_mailing_themes
if [[ "$APP_NAME" == "odoo" ]] && command -v nginx >/dev/null 2>&1 && command -v curl >/dev/null 2>&1 && [[ -n "${hsts_names:-}" ]]; then
    echo "--- 16) Appels d'Odoo vers son propre nom public (User-Agent python-requests, page /mass_mailing_themes) ---"
    ua_ctrl="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    n16=0
    while IFS= read -r hname; do
        [[ -z "$hname" ]] && continue
        c_py=$(run curl -sk -I -o /dev/null -w '%{http_code}' --max-time 8 -A "python-requests/2.31" "https://$hname/mass_mailing_themes" 2>/dev/null) || c_py=""
        [[ "$c_py" =~ ^[0-9]{3}$ && "$c_py" != "000" ]] || { echo "  [INFO] $hname : pas de réponse depuis ce serveur (nom non joignable d'ici) — non testé."; continue; }
        c_nav=$(run curl -sk -I -o /dev/null -w '%{http_code}' --max-time 8 -A "$ua_ctrl" "https://$hname/mass_mailing_themes" 2>/dev/null) || c_nav=""
        n16=$((n16 + 1))
        if [[ "$c_py" == "403" && "$c_nav" != "403" ]]; then
            fail "$hname : HTTP 403 pour python-requests mais HTTP ${c_nav:-?} pour un navigateur — le filtre anti-robots bloque les appels d'Odoo vers lui-même (mass_mailing, aperçu des thèmes, rapports). Quoi faire : déployer nginx-odoo-config 1.5 ou plus récent (snippets/securite-commune.conf : exemption de l'adresse du serveur), nginx -t && systemctl reload nginx, puis relancer ce script. Si le serveur est derrière un NAT, l'adresse publique n'est pas celle de l'interface : ajoutez-la à la liste blanche (/etc/default/nginx-tools-white-list.conf)."
        elif [[ "$c_py" == "403" ]]; then
            warn "$hname : HTTP 403 aussi pour un navigateur sur /mass_mailing_themes — ce n'est pas le filtre anti-robots (autre règle : liste blanche, page protégée, module mass_mailing non installé…). À examiner : nginx-log-audit.sh --evidence <adresse du serveur>."
        else
            pass "$hname : python-requests passe (HTTP $c_py ; navigateur HTTP ${c_nav:-?}) — les appels d'Odoo vers son nom public ne sont pas bloqués."
        fi
    done <<< "$hsts_names"
    (( n16 > 0 )) || echo "  [INFO] Aucun nom joignable depuis ce serveur : test impossible ici (refaire à la main : curl -sI -A python-requests/2.31 https://NOM/mass_mailing_themes)."
    echo
fi

if (( BBB_ETAT )); then
    echo "--- BigBlueButton APRÈS ce passage : compatibilité avec nos règles, changements faits par ce passage ---"
    if [[ "$CHECK_ONLY" == "1" ]]; then bbb_etat --after; else bbb_etat --after --save; fi
    echo
fi

echo "=============================================================="
if (( FAIL > 0 )); then
    echo "${C_RED}RÉSUMÉ : $PASS OK, $WARN avertissement(s), $FAIL échec(s).${C_RESET}"
elif (( WARN > 0 )); then
    echo "${C_YELLOW}RÉSUMÉ : $PASS OK, $WARN avertissement(s), aucun échec.${C_RESET}"
else
    echo "${C_GREEN}RÉSUMÉ : tout est en ordre ($PASS vérifications).${C_RESET}"
fi
echo "=============================================================="

if [[ "$CHECK_ONLY" != "1" ]]; then
    # The state file is also the configuration file: the user's lines (LANGUAGE, options...) are kept, only the SETUP_* lines are replaced.
    conserve=""
    mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true
    if [[ -r "$STATE_FILE" ]]; then
        conserve="$(grep -vE '^(SETUP_(VERSION|DATE|LAST_RESULT_(PASS|WARN|FAIL))=|# Généré par nginx-hardening\.sh)' "$STATE_FILE" || true)"
    fi
    {
        echo "# Généré par nginx-hardening.sh — les lignes SETUP_* sont réécrites à chaque --update ; les autres lignes (options, LANGUAGE) sont conservées."
        echo "SETUP_VERSION=$SCRIPT_VERSION"
        echo "SETUP_DATE=$(date '+%Y-%m-%d %H:%M:%S %Z')"
        echo "SETUP_LAST_RESULT_PASS=$PASS"
        echo "SETUP_LAST_RESULT_WARN=$WARN"
        echo "SETUP_LAST_RESULT_FAIL=$FAIL"
        if [[ -n "$TIMEZONE_A_ENREGISTRER" ]]; then
            conserve="$(printf '%s\n' "$conserve" | grep -vE '^TIMEZONE=' || true)"
            echo "TIMEZONE=$TIMEZONE_A_ENREGISTRER"
        fi
        [[ -n "$conserve" ]] && printf '%s\n' "$conserve"
    } > "$STATE_FILE"
    echo
    echo "État écrit dans $STATE_FILE."
fi

if (( PORT_EXPOSED > 0 )); then
    echo
    echo "Recommandation pour un port encore ouvert à l'extérieur (étape 4) : ajoutez dans odoo.conf —"
    echo "    [options]"
    echo "    http_interface = 127.0.0.1"
    echo "— puis redémarrez Odoo (pas un simple reload) et relancez ce script pour confirmer."
fi

if (( NEED_FAIL2BAN_RESTART > 0 )); then
    echo
    # "fail2ban-client reload" plutot que "systemctl reload fail2ban" : fonctionne meme si l'unite systemd de
    # fail2ban n'implemente pas ExecReload, et fail2ban-client est deja confirme present a ce stade (etape 9).
    # Contrairement a un redemarrage d'Odoo (jamais automatique dans ce script, interruption reelle du service),
    # a fail2ban reload is fast and has no impact on web traffic - safe to do automatically here.
    if run fail2ban-client reload >/dev/null 2>&1; then
        echo "Jails fail2ban installés ou régénérés : fail2ban rechargé (fail2ban-client reload)."
        sleep 2
        for j in "${F2B_INSTALLED_JAILS[@]}"; do
            if run fail2ban-client status "$j" >/dev/null 2>&1; then
                echo "    Jail $j : chargé et actif."
            else
                echo "    ${C_RED}Jail $j : NON chargé — voir « journalctl -u fail2ban -n 30 » (erreur de syntaxe, journal introuvable ?).${C_RESET}"
            fi
        done
        if [[ " ${F2B_INSTALLED_JAILS[*]} " == *" odoo-auth "* ]]; then
            echo "    Vérification ponctuelle (une fois) : fail2ban voit-il les échecs de connexion dans le VRAI journal d'Odoo ?"
            echo "    1) Depuis un navigateur, se connecter au site avec un MAUVAIS mot de passe (une fois suffit) ;"
            echo "    2) lancer :"
            # Test on TEXT (reliable): "fail2ban-regex ... systemd-journal" can read 0 lines even when the journal is full (observed on DEV); the filter, however, is checked on an excerpt of the journal.
            jopt=""; if [[ -n "${auth_ns:-}" ]]; then jopt=" --namespace=$auth_ns"; fi
            if [[ -n "$ODOO_LOGFILE" && -r "$ODOO_LOGFILE" ]]; then
                jtest="$ODOO_LOGFILE"                                    # journal d'Odoo en fichier : lu tel quel
            else
                jtest=/tmp/odoo-journal.txt
                echo "      journalctl -u $odoo_service$jopt --since \"10 min ago\" --no-pager > /tmp/odoo-journal.txt"
            fi
            echo "      fail2ban-regex $jtest /etc/fail2ban/filter.d/odoo-auth.conf"
            echo "    3) Attendu : « Lines: … N matched » avec N ≥ 1 (les lignes « missed » sont normales : tout le reste du journal d'Odoo)."
            echo "       0 matched : « grep -c 'Login failed' $jtest » = 0 → Odoo n'a pas écrit l'échec (mot de passe pas encore essayé, ou niveau de journal d'Odoo au-dessus de INFO) ;"
            echo "       sinon, vérifier que la ligne se termine par l'adresse (« … from 203.0.113.9 »). Adresse 127.0.0.1 partout : proxy_mode inactif (étape 8) — fail2ban bannirait nginx lui-même."
            echo "    4) La jail elle-même : « fail2ban-client status odoo-auth » (Total failed ≥ 1 après l'essai). ATTENTION : une adresse de la liste blanche de l'équipe est IGNORÉE par fail2ban"
            echo "       (ignoreip) : depuis votre poste d'équipe, « Total failed » reste à 0, c'est NORMAL. Pour voir la jail compter, essayer depuis une adresse hors liste (cellulaire, autre réseau)."
        fi
    else
        # Most frequent cause: fail2ban is not started (no socket); otherwise, configuration error.
        # "systemctl is-active" DISPLAYS the state AND returns a non-zero code if it is not active: read into a variable.
        f2b_etat=""; command -v systemctl >/dev/null 2>&1 && { f2b_etat=$(systemctl is-active fail2ban 2>/dev/null) || true; }
        if [[ -n "$f2b_etat" && "$f2b_etat" != "active" ]]; then
            echo "${C_RED}Jails fail2ban installés, mais fail2ban n'est PAS démarré ($f2b_etat) : aucune jail n'est active.${C_RESET}"
            echo "    Démarrer et activer au démarrage : systemctl enable --now fail2ban"
            echo "    Puis vérifier                    : fail2ban-client status"
        else
            echo "${C_RED}Jails fail2ban installés, mais le rechargement a échoué.${C_RESET}"
            f2b_test=$(run fail2ban-client -t 2>&1 | grep -iE 'error|erreur|fail|not found|No such|unable' | head -5) || f2b_test=""
            [[ -n "$f2b_test" ]] && printf '    %s\n' "Test de la configuration (fail2ban-client -t) :" && printf '      %s\n' "$f2b_test"
            echo "    Détail : journalctl -u fail2ban -n 30 ; puis fail2ban-client reload"
        fi
    fi
fi

exit $(( FAIL > 0 ? 1 : 0 ))
