#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# odoo-update-module.sh — met à jour des modules Odoo (par défaut ceux de Rencontres Linux Québec : rlq_*) puis redémarre Odoo par systemd.
#
# Déroulement : (1) détection du service systemd, de son compte, de son dossier, de la base et de la configuration d'Odoo ; (2) modules
# trouvés dans les addons_path ; (3) sauvegarde facultative de la base (--backup) ; (4) attente d'un site CALME (au plus --wait-quiet minutes,
# 15 par défaut : moins de --busy-visitors visiteurs actifs dans les journaux de nginx) ; (5) copie des modules d'avant (.tar.gz) ; (6) service
# ARRÊTÉ (aucun second Odoo sur la base, aucun conflit de port) ; (7) archive décompressée (--zip) ; (8) mise à jour par « odoo -d BASE -u MODULES
# --stop-after-init --no-http --workers=0 --max-cron-threads=0 » sous le compte du service, avec un délai maximal (--timeout) qui tue le processus
# s'il ne se termine pas — Ctrl+C y répond tout de suite ; (9) journal de la mise à jour contrôlé (ERROR / CRITICAL) ; (10) service DÉMARRÉ par
# systemd, état et port vérifiés ; (11) préchauffage ; (12) journal d'Odoo contrôlé depuis le démarrage. Après une erreur (8 à 12) : RETOUR ARRIÈRE
# (modules d'avant remis, nouvelle mise à jour, redémarrage ; question sur un terminal, automatique sinon ; --no-rollback pour l'empêcher). Le site
# ne reste jamais arrêté ; le code de sortie dit alors 1. Un Odoo lancé à la main sur la même base est refusé (--force pour passer outre).
#
# Usage : odoo-update-module.sh [OPTION]...   (sans option : mettre à jour les modules rlq_* de la base du service, puis redémarrer)
#
# Options (par ordre alphabétique) :
#   --addons-dir DIR             dossier où décompresser l'archive .zip des modules (souvent un dossier d'addons) ; défaut : ADDONS_DIR, sinon le dossier de
#                                addons_path qui contient déjà ces modules
#   --anonymize                  anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE
#   --backup                     sauvegarder la base avant (odoo-backup.sh --db BASE) ; échec = abandon, rien n'est arrêté
#   --busy-visitors N            site occupé à partir de N visiteurs actifs (requête dans les 5 dernières minutes, robots exclus) ; défaut : BUSY_VISITORS, soit 3
#   --changelog                  affiche le journal des modifications
#   -c, --config FILE            ce fichier de configuration SEUL (défaut : /etc/default/odoo-update-module.conf, puis
#                                ~/.odoo-update-module.conf s'il existe ; la ligne de commande est prioritaire)
#   --db NAME                    base à mettre à jour (défaut : « -d » de la commande du service, sinon db_name d'Odoo)
#   --dry-run                    montrer ce qui serait fait (service, base, modules, commandes), sans rien arrêter ni écrire
#   --force                      continuer malgré un Odoo lancé à la main (il est alors ignoré, pas arrêté)
#   -h, --help                   affiche cette aide et quitte
#   --lang LANG                  langue d'affichage : en ou fr (défaut : LANGUAGE du fichier de configuration, sinon LC_ALL / LC_MESSAGES / LANG)
#   --module PATTERN             module à mettre à jour ; motif accepté (« rlq_* »), option répétable (défaut : MODULES, soit rlq_*)
#   --no-rollback                jamais de retour arrière automatique (clé ROLLBACK=non) ; sinon, après des erreurs (mise à jour, démarrage, journal du service),
#                                les modules sont remis dans leur version d'avant (copie prise avant la décompression), mis à jour de nouveau, et Odoo redémarré
#   --no-warmup                  ne pas préchauffer le cache d'Odoo après le redémarrage (clé WARMUP=non) ; sinon odoo-warmup.py charge les pages publiques,
#                                les derniers événements et sondages, les écrans d'administration (réglages : /etc/default/odoo-warmup.conf)
#   --odoo-conf FILE             configuration d'Odoo (défaut : ODOO_CONF, sinon config.conf du dossier du service, sinon emplacements connus)
#   --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
#                                échecs, avertissements) ; désactive couleurs et questions interactives
#   --service NAME               service systemd d'Odoo (défaut : SERVICE, sinon détection automatique : erplibre* ou odoo*)
#   --timeout SECONDS            durée maximale de la mise à jour (défaut : TIMEOUT, soit 1800)
#   --user NAME                  compte sous lequel la mise à jour s'exécute (défaut : User= du service)
#   -v, --verbose                afficher chaque commande externe exécutée (systemctl, runuser, odoo, ss)
#   --version                    affiche la version et quitte
#   --wait-quiet MIN             attendre au plus MIN minutes que le site soit calme avant d'arrêter Odoo (défaut : WAIT_QUIET, soit 15 ; 0 = ne pas attendre) ;
#                                au bout du délai, la mise à jour se fait quand même
#   --zip FILE                   archive .zip des modules à décompresser avant la mise à jour (fichier, ou dossier : la plus récente) ; défaut : ZIP, sinon la plus
#                                récente « MODULE*.zip » du dossier courant ; « non » : ne rien décompresser
#
# Configuration (/etc/default/odoo-update-module.conf, créée au premier lancement, PUIS ~/.odoo-update-module.conf s'il existe ; lue sans être
# exécutée ; la ligne de commande l'emporte sur les fichiers) :
#   ADDONS_DIR=                   dossier de décompression de l'archive .zip (vide : celui de addons_path qui contient déjà les modules)
#   BACKUP=non                    sauvegarder avant (oui / non)
#   BUSY_VISITORS=3               site occupé à partir de ce nombre de visiteurs actifs (5 dernières minutes, robots exclus)
#   COMMAND=                      commande d'Odoo (vide : ./odoo_bin.sh du dossier du service, sinon odoo-bin)
#   DATABASE=                     base (vide : « -d » du service, sinon db_name d'Odoo)
#   LANGUAGE=auto                 langue d'affichage : en, fr ou auto (suivre LC_ALL / LANG)
#   MODULES=rlq_*                 modules à mettre à jour, séparés par des espaces (motifs acceptés)
#   MODULES_BACKUP_DIR=/var/backups/odoo-update-module   copies des modules AVANT la mise à jour (.tar.gz, les 10 dernières gardées) : base du retour arrière
#   ODOO_CONF=                    configuration d'Odoo (vide : config.conf du dossier du service, sinon emplacements connus)
#   ODOO_DIR=                     dossier d'Odoo (vide : WorkingDirectory= du service)
#   ROLLBACK=oui                  retour arrière des modules après des erreurs (oui / non) ; question sur un terminal, automatique sinon
#   RUN_USER=                     compte de la mise à jour (vide : User= du service)
#   SERVICE=                      service systemd d'Odoo (vide : détection automatique parmi erplibre* et odoo*, sinon erplibre_erplibre.service)
#   ZIP=                          archive .zip des modules (fichier ou dossier ; vide : « MODULE*.zip » le plus récent du dossier courant ; non : aucune)
#   WARMUP=oui                    préchauffer le cache d'Odoo après le redémarrage (odoo-warmup.py) ; non = comme --no-warmup
#   TIMEOUT=1800                  durée maximale de la mise à jour, en secondes
#   WAIT=90                       attente maximale du démarrage (service actif, puis port à l'écoute), en secondes
#   WAIT_QUIET=15                 attente maximale d'un site calme avant l'arrêt d'Odoo, en minutes (0 = ne pas attendre)
#
# HISTORIQUE (résumé ; détail : doc/odoo-update-module.changelog.txt)
#   1.14.20261020.211944 — Personal configuration file ~/.odoo-update-module.conf (not .cfg); a legacy one with .cfg is renamed automatically.
#   1.13.20261020.112434 — Header fields padded in columns (pad_cols): an accented label no longer shifts its value.
#   1.12.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.11.20261016.173838 — Quiet site before stopping Odoo, copy of the modules, check after the start, automatic rollback, Ctrl+C at once
#   1.10.20261015.170611 — ShellCheck : variable locale « c » inutilisée retirée de trouver_conf (SC2034).
#   1.9.20261015.143436 — --anonymize : affichage anonymisé (pseudonymes stables).
#   1.8.20261015.092124 — ShellCheck : 5 signalements corrigés (C_BLUE inutilisé, boucle à un élément, motif développé, apostrophes voulues).
#   1.7.20261015.080630 — Journaux de mise à jour gardés LOG_KEEP_DAYS jours (180) en plus des 10 plus récents.
#   1.6.20261014.214019 — Version du manifeste de l'archive affichée dès l'en-tête.
#   1.5.20261014.203136 — Détection automatique du service d'Odoo (erplibre* ou odoo*).
#   1.4.20261014.190654 — Archive .zip décompressée (--zip, --addons-dir) ; versions des modules avant / après.
#   1.3.20261014.175821 — Fichier commun app-default.conf ; clé VERBOSE.
#   1.2.20261014.174013 — Préchauffage du cache d'Odoo (odoo-warmup.py) après le redémarrage ; --no-warmup.
#   1.1.20261014.161550 — Sortie plus lisible : en-tête compact, étapes numérotées, ✔ ✖ ⚠ en couleur, détails en gris.
#   1.0.20261014.110643 — Première version : arrêt du service, mise à jour des modules rlq_* qui se termine vraiment (--stop-after-init, délai maximal), contrôle du journal, redémarrage par systemd.
# ========================================================================================================================

set -euo pipefail
for _d in /usr/local/sbin /usr/sbin /sbin; do [[ -n "${NGINX_TOOLS_TESTS:-}" ]] && break; case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac; done
export PATH

readonly SCRIPT_VERSION="1.14.20261020.211944"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}" .sh)"; readonly SCRIPT_NAME
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"; readonly SCRIPT_PATH
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
readonly CHANGELOG_FILE

# Section of this program in CHANGELOG.md (from its "## <file name>" heading to the next "## " heading).
changelog_section() {
    awk -v cle="${BASH_SOURCE[0]##*/}" '/^## /{dans=($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE"
}
# Langue d'affichage (en ou fr) : --lang, ODOO_UPDATE_MODULE_LANG, LANGUAGE du fichier de configuration, LC_ALL / LANG — apps/_i18n.sh traduit la sortie.
if [[ -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_i18n.sh"
    i18n_relancer "$SCRIPT_NAME" ODOO_UPDATE_MODULE_LANG "$0" "$@"
fi
# 1.11: without apps/_i18n.sh, plain execution (no Ctrl+C question).
declare -F pad_cols >/dev/null || pad_cols() { printf '%-*s' "$2" "$1"; }     # 1.13 : sans apps/_i18n.sh, remplissage en octets (comme avant)
declare -F run_interruptible >/dev/null || run_interruptible() { "$@"; }
declare -F ctrl_c_child >/dev/null || ctrl_c_child() { "$@"; }
# Bibliothèque commune : configuration d'Odoo (ports, db_name…).
if [[ -r "$SCRIPT_DIR/apps/_odoo_conf.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_odoo_conf.sh"
fi

if [[ -t 1 || -n "${REPORT_ERR_COULEUR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_RESET=$'\x1b[0m'
    C_CYAN=$'\x1b[1;36m'; C_BOLD=$'\x1b[1m'; C_DIM=$'\x1b[90m'
else C_RED=""; C_YELLOW=""; C_GREEN=""; C_RESET=""; C_CYAN=""; C_BOLD=""; C_DIM=""; fi

# --- Options -----------------------------------------------------------------------------------------------------------
SERVICE=""; SERVICE_DETECTE=0; MODULES_MOTIFS="rlq_*"; ONLY_DB=""; ODOO_CONF_OPT=""; ODOO_DIR=""; RUN_USER=""; COMMAND=""
TIMEOUT=1800; WAIT=90; DO_BACKUP=0; DO_DRY_RUN=0; DO_FORCE=0; DO_WARMUP=1; VERBOSE=0; CLI_MODULES=0; ADDONS_DIR=""; ZIP_ARG=""
WAIT_QUIET=15; BUSY_VISITORS=3; DO_ROLLBACK=1                                           # 1.11: quiet site before stopping Odoo; rollback of the modules after errors
NGINX_LOG_DIR="${ODOO_UPDATE_MODULE_NGINX_DIR:-/var/log/nginx}"
MODULES_BACKUP_DIR="${ODOO_UPDATE_MODULE_BACKUP_DIR:-/var/backups/odoo-update-module}"
LOG_DIR="${ODOO_UPDATE_MODULE_LOG_DIR:-/var/log/odoo-update-module}"
# --report-err : rapport d'erreurs à copier-coller en fin d'exécution — apps/_rapport.sh
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_rapport.sh"
    rapport_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi
# Première ligne de TOUTE exécution, même avec --help : le nom et la version du programme (--version l'affiche lui-même).
case " $* " in *" --version "*) ;; *) echo "odoo-update-module.sh v$SCRIPT_VERSION" ;; esac
# Configuration (/etc/default/odoo-update-module.conf, puis ~/.odoo-update-module.conf ; -c/--config : ce fichier SEUL) : valeurs par défaut des options, la ligne de commande l'emporte.
if declare -F config_lire >/dev/null; then
    config_lire "$SCRIPT_NAME" "$@"
    config_defaut ADDONS_DIR ADDONS_DIR --addons-dir texte
    config_defaut DO_BACKUP BACKUP --backup booleen
    config_defaut BUSY_VISITORS BUSY_VISITORS --busy-visitors nombre
    config_defaut MODULES_BACKUP_DIR MODULES_BACKUP_DIR MODULES_BACKUP_DIR texte
    config_defaut DO_ROLLBACK ROLLBACK --no-rollback booleen
    config_defaut WAIT_QUIET WAIT_QUIET --wait-quiet nombre
    config_defaut COMMAND COMMAND COMMAND texte
    config_defaut ONLY_DB DATABASE --db texte
    config_defaut MODULES_MOTIFS MODULES --module texte
    config_defaut ODOO_CONF_OPT ODOO_CONF --odoo-conf texte
    config_defaut ODOO_DIR ODOO_DIR ODOO_DIR texte
    config_defaut RUN_USER RUN_USER --user texte
    config_defaut SERVICE SERVICE --service texte
    config_defaut TIMEOUT TIMEOUT --timeout nombre
    config_defaut WAIT WAIT WAIT nombre
    config_defaut DO_WARMUP WARMUP --no-warmup booleen
    config_defaut VERBOSE VERBOSE --verbose booleen
    config_defaut ZIP_ARG ZIP --zip texte
    case " $* " in *" --version "*|*" --help "*|*" -h "*) ;; *) config_afficher ;; esac
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --addons-dir) ADDONS_DIR="${2:-}"; shift 2 ;;
        --backup) DO_BACKUP=1; shift ;;
        --busy-visitors) BUSY_VISITORS="${2:-}"; shift 2 ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then
                echo "Changelog introuvable : $CHANGELOG_FILE" >&2
                exit 1
            fi
            if [[ -t 1 ]]; then
                # Numeros de version en cyan gras ; SIGPIPE (ex. "| head") laisse terminer proprement par defaut.
                changelog_section | sed -E $'s/([0-9]+\\.[0-9]+\\.[0-9]{8}\\.[0-9]{6})/\\x1b[1;36m\\1\\x1b[0m/' || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu
            else
                changelog_section || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu
            fi
            exit 0
            ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*|--lang=*) shift ;;
        --db) ONLY_DB="${2:-}"; shift 2 ;;
        --dry-run) DO_DRY_RUN=1; shift ;;
        --force) DO_FORCE=1; shift ;;
        -h|--help) sed -n '/^# Usage :/,/^# HISTORIQUE/p' "$SCRIPT_PATH" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        --lang) shift 2 ;;                     # lu avant (apps/_i18n.sh)
        --module)
            if (( CLI_MODULES == 0 )); then MODULES_MOTIFS=""; CLI_MODULES=1; fi
            MODULES_MOTIFS+="${MODULES_MOTIFS:+ }${2:-}"; shift 2 ;;
        --no-rollback) DO_ROLLBACK=0; shift ;;
        --no-warmup) DO_WARMUP=0; shift ;;
        --odoo-conf) ODOO_CONF_OPT="${2:-}"; shift 2 ;;
        --report-err) shift ;;                 # traité avant (apps/_rapport.sh) ; accepté ici avec --help, --version…
        --service) SERVICE="${2:-}"; shift 2 ;;
        --timeout) TIMEOUT="${2:-}"; shift 2 ;;
        --user) RUN_USER="${2:-}"; shift 2 ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --version) echo "odoo-update-module.sh version $SCRIPT_VERSION"; exit 0 ;;
        --wait-quiet) WAIT_QUIET="${2:-}"; shift 2 ;;
        --zip) ZIP_ARG="${2:-}"; shift 2 ;;
        *) echo "Argument inconnu: $1 (voir --help)" >&2; exit 1 ;;
    esac
done

# --- Outils -------------------------------------------------------------------------------------------------------------
# Présentation : peu de texte, de la couleur pour guider l'œil — vert = réussi, jaune = attention, rouge = échec, cyan = étape, gris = détail secondaire.
ok()   { echo "  ${C_GREEN}✔${C_RESET} $*"; }
attn() { echo "  ${C_YELLOW}⚠ [ATTN]${C_RESET} ${C_YELLOW}$*${C_RESET}"; }
ko()   { echo "  ${C_RED}✖ [FAIL]${C_RESET} ${C_RED}$*${C_RESET}"; }
sim()  { echo "  ${C_DIM}(simulation)${C_RESET} $*"; }
detail() { echo "    ${C_DIM}$*${C_RESET}"; }
en_retrait() { local l; while IFS= read -r l; do printf '        %s%s%s\n' "$1" "$l" "$C_RESET"; done; }       # lignes lues sur l'entrée, en retrait, dans la couleur donnée
champ() { printf '  %s%s%s %s\n' "$C_DIM" "$(pad_cols "$1" 13)" "$C_RESET" "$2"; }         # champ "Base :" "valeur" ; 1.13 : largeur en colonnes (étiquette accentuée)
ETAPE=0; ETAPES=0
etape() { ETAPE=$((ETAPE + 1)); echo; echo "${C_CYAN}▶ [${ETAPE}/${ETAPES}] $*${C_RESET}"; }
exec 3>&2
trace() {       # --verbose : la commande externe exacte, avant son exécution (sur la sortie d'erreur)
    if [[ "$VERBOSE" == "1" ]]; then printf '+ %s\n' "$*" >&3; fi
    return 0
}
sc() { trace systemctl "$@"; systemctl "$@"; }

# Détection automatique du service d'Odoo (--service ou SERVICE l'emportent) : unités « erplibre* » ou « odoo* »
# (en production : erplibre ou odoo), hors unités auxiliaires (warmup, backup, update, mail, retry...). Actif préféré.
deviner_service() {
    local liste candidats actifs
    trace systemctl list-units --type=service --all --no-legend --plain
    liste="$(systemctl list-units --type=service --all --no-legend --plain 2>/dev/null || true)"
    candidats="$(awk '{ n=$1; sub(/^[^A-Za-z0-9]+/, "", n) } n ~ /^(erplibre|odoo)[A-Za-z0-9@_.:-]*\.service$/ && n !~ /(warmup|backup|update|mail|retry|run|monitor|watch|survey|log|check)/ { print n, $3 }' <<< "$liste" | sort -u)"
    actifs="$(awk '$2 == "active" { print $1 }' <<< "$candidats")"
    if [[ -n "$actifs" ]]; then candidats="$actifs"; else candidats="$(awk '{ print $1 }' <<< "$candidats")"; fi
    if [[ -z "$candidats" ]]; then SERVICE="erplibre_erplibre.service"; return 0; fi
    if (( $(wc -l <<< "$candidats") > 1 )); then
        echo "ERREUR: plusieurs services Odoo possibles ($(tr '\n' ' ' <<< "$candidats")) : précisez --service ou SERVICE dans la configuration." >&2
        exit 1
    fi
    SERVICE="$candidats"; SERVICE_DETECTE=1
}
[[ -n "$SERVICE" ]] || deviner_service

[[ "$TIMEOUT" =~ ^[0-9]+$ && "$TIMEOUT" -ge 1 ]] || { echo "ERREUR: --timeout attend un nombre de secondes (reçu : « $TIMEOUT »)." >&2; exit 1; }
[[ "$WAIT" =~ ^[0-9]+$ ]] || { echo "ERREUR: WAIT attend un nombre de secondes (reçu : « $WAIT »)." >&2; exit 1; }
[[ "$SERVICE" =~ ^[A-Za-z0-9@_.:-]+$ ]] || { echo "ERREUR: nom de service invalide : « $SERVICE »." >&2; exit 1; }
[[ "$SERVICE" == *.* ]] || SERVICE="$SERVICE.service"

# Verrou (flock) : une seule mise à jour à la fois (timer, cron et lancement manuel peuvent se croiser).
prendre_verrou() {
    local dir="${NGINX_TOOLS_LOCK_DIR:-/run/lock}" ok
    command -v flock >/dev/null 2>&1 || return 0
    [[ -d "$dir" && -w "$dir" ]] || dir="${TMPDIR:-/tmp}"
    exec 9>>"$dir/odoo-update-module.lock" || return 0
    flock -n 9 && ok=1 || ok=0
    if (( ! ok )); then
        echo "ERREUR: une autre exécution de odoo-update-module est en cours (verrou $dir/odoo-update-module.lock) — abandon." >&2
        exit 75
    fi
}

# --- Détection : service, compte, dossier, base, configuration, modules -----------------------------------------------------
propriete() { systemctl show -p "$1" --value -- "$SERVICE" 2>/dev/null || true; }   # propriété du service (vide si absente)

detecter_service() {
    local charge exec_start argv
    charge=$(propriete LoadState)
    if [[ "$charge" == "not-found" || -z "$charge" ]]; then
        ko "service « $SERVICE » introuvable (systemctl) — voir --service ou SERVICE dans la configuration"
        exit 1
    fi
    [[ -n "$RUN_USER" ]] || RUN_USER=$(propriete User)
    [[ -n "$ODOO_DIR" ]] || ODOO_DIR=$(propriete WorkingDirectory)
    exec_start=$(propriete ExecStart)
    argv=$(sed -n 's/.*argv\[\]=\([^;]*\);.*/\1/p' <<< "$exec_start" | head -1)
    [[ -n "$ODOO_DIR" && "$ODOO_DIR" != "!"* ]] || ODOO_DIR=""
    if [[ -z "$ODOO_DIR" && -n "$argv" ]]; then ODOO_DIR=$(dirname "${argv%% *}"); fi
    if [[ -z "$ONLY_DB" && "$argv" =~ (^|[[:space:]])(-d|--database)[[:space:]=]+([^[:space:]]+) ]]; then
        BASE_DU_SERVICE="${BASH_REMATCH[3]}"
    fi
}

trouver_conf() {
    if [[ -n "$ODOO_CONF_OPT" ]]; then
        [[ -r "$ODOO_CONF_OPT" ]] || { ko "configuration d'Odoo illisible : $ODOO_CONF_OPT"; exit 1; }
        ODOO_CONF_UTILISEE="$ODOO_CONF_OPT"; return 0
    fi
    if [[ -n "$ODOO_DIR" && -r "$ODOO_DIR/config.conf" ]]; then ODOO_CONF_UTILISEE="$ODOO_DIR/config.conf"; return 0; fi
    if declare -F odoo_conf_trouver >/dev/null; then ODOO_CONF_UTILISEE=$(odoo_conf_trouver) || ODOO_CONF_UTILISEE=""; fi
    [[ -n "$ODOO_CONF_UTILISEE" ]] || { ko "configuration d'Odoo introuvable (voir --odoo-conf ou ODOO_CONF)"; exit 1; }
}

trouver_base() {
    local v
    DB="$ONLY_DB"
    [[ -n "$DB" ]] || DB="${BASE_DU_SERVICE:-}"
    if [[ -z "$DB" ]]; then
        v=$(odoo_conf_valeur "$ODOO_CONF_UTILISEE" db_name 2>/dev/null || true)
        if [[ -n "$v" && "$v" != "False" && "$v" != *","* ]]; then DB="$v"; fi
    fi
    [[ -n "$DB" ]] || { ko "base introuvable : ni --db, ni « -d » dans la commande du service, ni db_name dans la configuration d'Odoo"; exit 1; }
    [[ "$DB" =~ ^[A-Za-z0-9_.-]+$ ]] || { ko "nom de base invalide : « $DB »"; exit 1; }
}

# Archive .zip des modules : --zip / ZIP (fichier, ou dossier : la plus récente), sinon la plus récente « MOTIF*.zip » du dossier COURANT ; aucune : rien à décompresser.
# Un zip trouvé sans l'avoir demandé n'est qu'une commodité ; un zip DEMANDÉ et introuvable est une erreur.
ZIP_FICHIER=""; ZIP_MODULES=(); ZIP_VERSIONS=(); DESTINATION=""
zip_inspecter() {   # zip_inspecter FICHIER : « module<TAB>version du manifeste » par module de l'archive ; code 3 si un chemin sort du dossier de destination
    python3 - "$1" <<'PYEOF'
import ast, posixpath, sys, zipfile
try:
    z = zipfile.ZipFile(sys.argv[1])
    modules = {}
    for n in z.namelist():
        p = posixpath.normpath(n)
        if n.startswith("/") or p == ".." or p.startswith("../"):
            sys.exit(3)
        parts = p.split("/")
        if len(parts) == 2 and parts[1] == "__manifest__.py":
            try:
                version = str(ast.literal_eval(z.read(n).decode("utf-8", "replace")).get("version", "?"))
            except (ValueError, SyntaxError):
                version = "?"
            modules[parts[0]] = version
except (OSError, zipfile.BadZipFile):
    sys.exit(4)
for nom in sorted(modules):
    print(nom + "\t" + modules[nom])
PYEOF
}

trouver_zip() {
    local source motif cand="" f
    local -a MOTIFS=()
    read -ra MOTIFS <<< "$MODULES_MOTIFS"                      # sans développement des « * » par le shell dans le dossier courant
    source="$ZIP_ARG"
    case "${source,,}" in non|no|none|off) return 0 ;; esac
    if [[ -n "$source" && -f "$source" ]]; then cand="$source"
    else
        local dossier="${source:-$PWD}"
        if [[ -n "$source" && ! -d "$source" ]]; then ko "archive introuvable : « $source » (--zip ou ZIP)"; exit 1; fi
        for motif in "${MOTIFS[@]}"; do
            # shellcheck disable=SC2012,SC2086,SC2231  # noms de fichiers simples ; motif développé voulu
            f=$(ls -1t "$dossier"/$motif*.zip 2>/dev/null | head -n 1 || true)
            if [[ -n "$f" && ( -z "$cand" || "$f" -nt "$cand" ) ]]; then cand="$f"; fi
        done
        if [[ -z "$cand" ]]; then
            [[ -z "$source" ]] || { ko "aucune archive « ${MODULES_MOTIFS// /, }*.zip » dans $source"; exit 1; }
            return 0
        fi
    fi
    ZIP_FICHIER=$(cd "$(dirname "$cand")" && pwd)/$(basename "$cand")
    local sortie ligne code=0
    sortie=$(zip_inspecter "$ZIP_FICHIER") || code=$?
    if (( code == 3 )); then ko "archive refusée : $ZIP_FICHIER contient un chemin qui sort du dossier de destination (/ ou ..)"; exit 1; fi
    if (( code != 0 )); then ko "archive illisible (zip invalide ?) : $ZIP_FICHIER"; exit 1; fi
    [[ -n "$sortie" ]] || { ko "archive sans module : aucun dossier avec __manifest__.py à la racine de $ZIP_FICHIER"; exit 1; }
    while IFS= read -r ligne; do ZIP_MODULES+=("${ligne%%$'\t'*}"); ZIP_VERSIONS+=("${ligne#*$'\t'}"); done <<< "$sortie"
}

# Dossier de décompression : --addons-dir / ADDONS_DIR ; sinon le dossier d'addons_path qui contient déjà un de ces modules ; sinon erreur (jamais deviné au hasard).
trouver_destination() {
    local liste chemin m
    local -a dossiers=()
    [[ -n "$ZIP_FICHIER" ]] || return 0
    if [[ -n "$ADDONS_DIR" ]]; then
        [[ "$ADDONS_DIR" == /* ]] || ADDONS_DIR="${ODOO_DIR:-.}/$ADDONS_DIR"
        [[ -d "$ADDONS_DIR" ]] || { ko "dossier de décompression introuvable : $ADDONS_DIR (--addons-dir ou ADDONS_DIR)"; exit 1; }
        DESTINATION=$(cd "$ADDONS_DIR" && pwd); return 0
    fi
    liste=$(odoo_conf_valeur "$ODOO_CONF_UTILISEE" addons_path 2>/dev/null || true)
    IFS=',' read -ra dossiers <<< "$liste"
    for chemin in ${dossiers[@]+"${dossiers[@]}"}; do
        chemin="${chemin#"${chemin%%[![:space:]]*}"}"; chemin="${chemin%"${chemin##*[![:space:]]}"}"
        [[ -n "$chemin" ]] || continue
        [[ "$chemin" == /* ]] || chemin="$ODOO_DIR/$chemin"
        for m in "${ZIP_MODULES[@]}"; do
            if [[ -d "$chemin/$m" ]]; then DESTINATION=$(cd "$chemin" && pwd); return 0; fi
        done
    done
    ko "dossier de décompression introuvable : aucun dossier de addons_path ne contient déjà ${ZIP_MODULES[*]} — préciser --addons-dir (ou ADDONS_DIR)"
    exit 1
}

decompresser() {
    local i
    etape "Décompression de $(basename "$ZIP_FICHIER")"
    for i in "${!ZIP_MODULES[@]}"; do champ "${ZIP_MODULES[$i]}" "${C_CYAN}${ZIP_VERSIONS[$i]}${C_RESET} ${C_DIM}(manifeste de l'archive)${C_RESET}"; done
    if (( DO_DRY_RUN )); then sim "décompression de $ZIP_FICHIER vers $DESTINATION (propriétaire : celui du dossier)"; return 0; fi
    trace python3 - "$ZIP_FICHIER" "$DESTINATION"
    if python3 - "$ZIP_FICHIER" "$DESTINATION" <<'PYEOF'
import os, sys, zipfile
z = zipfile.ZipFile(sys.argv[1]); dest = os.path.realpath(sys.argv[2])
st = os.stat(dest)
for info in z.infolist():
    cible = os.path.realpath(os.path.join(dest, info.filename))
    if not (cible == dest or cible.startswith(dest + os.sep)):
        sys.exit(3)
z.extractall(dest)
if os.geteuid() == 0:                                   # les fichiers appartiennent à celui du dossier (le compte d'Odoo), pas à root
    for info in z.infolist():
        p = os.path.join(dest, info.filename)
        try:
            os.chown(p, st.st_uid, st.st_gid)
        except OSError:
            pass
PYEOF
    then ok "$(basename "$ZIP_FICHIER") décompressé dans ${C_BOLD}$DESTINATION${C_RESET} (${#ZIP_MODULES[@]} module(s), fichiers existants remplacés)"
    else ko "décompression de $ZIP_FICHIER dans $DESTINATION impossible (droits ? espace disque ?)"; return 1; fi
}

# Versions des modules installés, avant / après (lecture seule dans PostgreSQL, apps/_odoo_db.py --modules) : les modules mis à jour + les 10 modifiés le plus récemment.
VERS_AVANT=""
versions_lire() { python3 "$SCRIPT_DIR/apps/_odoo_db.py" --modules "$DB" 2>/dev/null || true; }
afficher_versions() {
    local apres
    apres=$(versions_lire)
    if [[ -z "$apres" || -z "$VERS_AVANT" ]]; then detail "versions des modules illisibles (PostgreSQL : root requis ?)"; return 0; fi
    AVANT="$VERS_AVANT" APRES="$apres" MIS_A_JOUR="${MODULES_TROUVES[*]}" BASE="$DB" CB="$C_BOLD" CC="$C_CYAN" CD="$C_DIM" CG="$C_GREEN" CY="$C_YELLOW" CR="$C_RESET" python3 - <<'PYEOF'
import datetime, os
e = os.environ
def lire(texte):
    res = {}
    for l in texte.splitlines():
        c = l.split("\t")
        if len(c) >= 4:
            res[c[0]] = {"etat": c[1], "version": c[2], "maj": c[3]}
    return res
avant, apres = lire(e["AVANT"]), lire(e["APRES"])
def locale(t):
    try:
        return datetime.datetime.strptime(t[:16], "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return t
mis = e["MIS_A_JOUR"].split()
installes = {n: m for n, m in apres.items() if m["etat"] in ("installed", "to upgrade", "to remove")}
recents = sorted((n for n, m in installes.items() if m["maj"]), key=lambda n: (installes[n]["maj"], n), reverse=True)[:10]
noms = sorted(set(recents) | {n for n in mis if n in apres}, key=lambda n: (apres[n]["maj"], n), reverse=True)
va, vb = avant.get("base", {}).get("version", "?"), apres.get("base", {}).get("version", "?")
print(f"  {e['CD']}Versions des modules installés (base {e['BASE']}) — Odoo {e['CR']}{e['CC']}{vb}{e['CR']}" + (f"{e['CD']} (avant : {va}){e['CR']}" if va != vb else ""))
largeur = max((len(n) for n in noms), default=0)
for n in noms:
    a, b = avant.get(n, {}).get("version"), apres[n]["version"]
    if a is None:
        couleur, mot, texte = e["CC"], "nouveau", f"{b or '?'}"
    elif a != b:
        couleur, mot, texte = e["CG"], "mis à jour", f"{a or '?'} → {b or '?'}"
    elif n in mis:
        couleur, mot, texte = e["CD"], "inchangé", f"{b or '?'}"
    else:
        couleur, mot, texte = e["CD"], "", f"{b or '?'}"
    print(f"      {e['CB']}{n.ljust(largeur)}{e['CR']}  {texte.ljust(34)} {couleur}{(f"({mot})" if mot else "").ljust(13)}{e['CR']} {e['CD']}{locale(apres[n]['maj'])}{e['CR']}")
PYEOF
}

# Modules : motifs (« rlq_* ») développés dans les addons_path de la configuration d'Odoo ; seuls les dossiers qui ont un __manifest__.py comptent.
trouver_modules() {
    local liste chemin motif d nom
    local -a dossiers=() MOTIFS=()
    read -ra MOTIFS <<< "$MODULES_MOTIFS"                      # sans développement des « * » par le shell dans le dossier courant
    MODULES_TROUVES=()
    liste=$(odoo_conf_valeur "$ODOO_CONF_UTILISEE" addons_path 2>/dev/null || true)
    IFS=',' read -ra dossiers <<< "$liste"
    for motif in "${MOTIFS[@]}"; do
        [[ "$motif" =~ ^[a-z0-9_*?]+$ ]] || { ko "motif de module invalide : « $motif » (lettres minuscules, chiffres, _ * ?)"; exit 1; }
        for chemin in ${dossiers[@]+"${dossiers[@]}"}; do
            chemin="${chemin#"${chemin%%[![:space:]]*}"}"; chemin="${chemin%"${chemin##*[![:space:]]}"}"
            [[ -n "$chemin" ]] || continue
            [[ "$chemin" == /* ]] || chemin="$ODOO_DIR/$chemin"
            # shellcheck disable=SC2231  # développement du motif voulu
            for d in $chemin/$motif; do
                [[ -f "$d/__manifest__.py" ]] || continue
                nom=$(basename "$d")
                case " ${MODULES_TROUVES[*]-} " in *" $nom "*) ;; *) MODULES_TROUVES+=("$nom") ;; esac
            done
        done
    done
    for nom in ${ZIP_MODULES[@]+"${ZIP_MODULES[@]}"}; do          # les modules de l'archive sont mis à jour aussi (même s'ils ne sont pas encore sur le disque)
        case " ${MODULES_TROUVES[*]-} " in *" $nom "*) ;; *) MODULES_TROUVES+=("$nom") ;; esac
    done
    if (( ${#MODULES_TROUVES[@]} == 0 )); then
        ko "aucun module trouvé pour « $MODULES_MOTIFS » dans addons_path de $ODOO_CONF_UTILISEE"
        exit 1
    fi
}

commande_odoo() {
    if [[ -n "$COMMAND" ]]; then CMD_ODOO="$COMMAND"
    elif [[ -n "$ODOO_DIR" && -x "$ODOO_DIR/odoo_bin.sh" ]]; then CMD_ODOO="./odoo_bin.sh"
    elif command -v odoo-bin >/dev/null 2>&1; then CMD_ODOO="odoo-bin"
    else ko "commande d'Odoo introuvable : ./odoo_bin.sh absent de « ${ODOO_DIR:-?} » et odoo-bin absent du PATH (voir COMMAND)"; exit 1; fi
}

# Odoo lancé à la main (hors systemd) : même Odoo qui ne s'arrête pas, mêmes ports, même base.
odoo_a_la_main() {
    pgrep -af 'odoo[-_]bin' 2>/dev/null | grep -v "odoo-update-module" || true
}

# Appelé APRÈS l'arrêt du service (sinon l'Odoo du service lui-même serait vu) ; refus : le service est remis dans l'état où on l'a trouvé.
verifier_odoo_a_la_main() {
    local autres
    if (( DO_DRY_RUN )); then sim "vérification qu'aucun Odoo ne tourne hors systemd (après l'arrêt du service)"; return 0; fi
    autres=$(odoo_a_la_main)
    [[ -n "$autres" ]] || return 0
    ko "un Odoo tourne HORS systemd (lancé à la main ?) — même base, mêmes ports :"
    cut -c1-200 <<< "$autres" | en_retrait "$C_YELLOW"
    if (( DO_FORCE )); then attn "--force : on continue ; ce processus n'est ni arrêté ni contrôlé"; return 0; fi
    echo "  Arrêtez-le (Ctrl+C dans son terminal, ou kill PID), puis relancez ; --force pour passer outre." >&2
    if (( ETAIT_ACTIF )); then sc start "$SERVICE" || true; attn "service $SERVICE redémarré : il était actif avant"; fi
    exit 1
}

# --- Étapes -------------------------------------------------------------------------------------------------------------------
sauvegarder() {
    local prog="$SCRIPT_DIR/odoo-backup.sh"
    [[ -x "$prog" || -r "$prog" ]] || { ko "odoo-backup.sh introuvable à côté de ce programme"; return 1; }
    etape "Sauvegarde de la base $DB"
    if (( DO_DRY_RUN )); then sim "bash $prog --db $DB"; return 0; fi
    trace bash "$prog" --db "$DB"
    if ctrl_c_child bash "$prog" --db "$DB"; then ok "sauvegarde de $DB terminée"; else ko "sauvegarde de $DB en échec — rien n'a été arrêté"; return 1; fi
}

arreter() {
    etape "Arrêt du service"
    if (( DO_DRY_RUN )); then sim "systemctl stop $SERVICE"; return 0; fi
    sc stop "$SERVICE" || true
    if [[ "$(sc is-active "$SERVICE" 2>/dev/null || true)" == "active" ]]; then
        ko "le service $SERVICE est toujours actif après « systemctl stop »"
        return 1
    fi
    ok "service $SERVICE arrêté"
}

preparer_journal() {
    local dir="$LOG_DIR"
    if (( DO_DRY_RUN )); then JOURNAL="$dir/update-$DB-AAAAMMJJ-HHMMSS.log"; return 0; fi
    if ! mkdir -p "$dir" 2>/dev/null || [[ ! -w "$dir" ]]; then dir="${TMPDIR:-/tmp}"; fi
    JOURNAL="$dir/update-$DB-$(date +%Y%m%d-%H%M%S).log"
    DOSSIER_JOURNAUX="$dir"
}
purger_journaux() {   # garde les 10 plus récents ET tout ce qui a moins de LOG_KEEP_DAYS jours (fichier commun, défaut 180 ; 0 = ne rien effacer)
    local f jours="${NGINX_TOOLS_LOG_KEEP_DAYS:-180}"
    [[ "$jours" =~ ^[0-9]+$ ]] || jours=180
    (( jours == 0 )) && return 0
    # shellcheck disable=SC2012  # noms produits par ce programme : aucun caractère étrange
    ls -1t "$DOSSIER_JOURNAUX"/update-*.log 2>/dev/null | tail -n +11 | while IFS= read -r f; do
        [[ -n "$(find "$f" -mtime "-$jours" 2>/dev/null)" ]] || rm -f -- "$f"
    done
}

mettre_a_jour() {
    local liste code=0 secondes debut
    etape "Mise à jour des modules dans la base $DB"
    liste=$(IFS=,; echo "${MODULES_TROUVES[*]}")
    local -a odoo=("$CMD_ODOO" -c "$ODOO_CONF_UTILISEE" -d "$DB" -u "$liste"
                   --stop-after-init --no-http --workers=0 --max-cron-threads=0
                   --limit-time-real="$TIMEOUT" --limit-time-cpu="$TIMEOUT" --limit-memory-hard=0 --log-level=info)
    # shellcheck disable=SC2016  # les apostrophes sont voulues : bash -c reçoit le script tel quel
    local -a lancer=(timeout --kill-after=30 "$TIMEOUT" bash -c 'cd "$1" && shift && exec "$@"' _ "${ODOO_DIR:-.}" "${odoo[@]}")
    if [[ -n "$RUN_USER" && "$(id -un)" != "$RUN_USER" ]]; then
        local maison
        maison=$(getent passwd "$RUN_USER" | cut -d: -f6 || true)      # runuser -u garde HOME=/root : data_dir d'Odoo irait au mauvais endroit
        # shellcheck disable=SC2016  # idem
        lancer=(timeout --kill-after=30 "$TIMEOUT" runuser -u "$RUN_USER" -- env "HOME=${maison:-/nonexistent}" bash -c 'cd "$1" && shift && exec "$@"' _ "${ODOO_DIR:-.}" "${odoo[@]}")
    fi
    if (( DO_DRY_RUN )); then sim "$(printf '%q ' "${lancer[@]}")> $JOURNAL"; return 0; fi
    echo "  ${C_DIM}${#MODULES_TROUVES[@]} module(s), compte ${RUN_USER:-$(id -un)}, délai maximal ${TIMEOUT} s — en cours…${C_RESET}"
    detail "journal : $JOURNAL"
    trace "${lancer[@]}"
    debut=$SECONDS
    run_interruptible "${lancer[@]}" > "$JOURNAL" 2>&1 < /dev/null || code=$?        # 1.11: Ctrl+C answered at once (not after up to TIMEOUT s)
    secondes=$((SECONDS - debut))
    if (( code == 124 || code == 137 )); then
        ko "la mise à jour ne s'est pas terminée en ${TIMEOUT} s : processus tué (code $code)"
        return 1
    elif (( code != 0 )); then
        ko "la mise à jour d'Odoo s'est terminée avec le code $code (voir $JOURNAL)"
        tail -n 15 "$JOURNAL" | en_retrait "$C_DIM"
        return 1
    fi
    ok "Odoo s'est arrêté de lui-même après ${secondes} s (code 0)"
    controler_journal
}

controler_journal() {
    local erreurs critiques
    erreurs=$(grep -cE ' (ERROR|CRITICAL) ' "$JOURNAL" || true)
    critiques=$(grep -cE ' CRITICAL ' "$JOURNAL" || true)
    if (( erreurs > 0 )); then
        ko "${erreurs} ligne(s) ERROR/CRITICAL dans le journal de la mise à jour (${critiques} CRITICAL) — premières :"
        grep -E ' (ERROR|CRITICAL) ' "$JOURNAL" | head -n 10 | cut -c1-300 | en_retrait "$C_RED"
        return 1
    fi
    ok "journal de la mise à jour sans ERROR ni CRITICAL ${C_DIM}($(grep -c . "$JOURNAL") lignes)${C_RESET}"
}

port_ecoute() {   # port_ecoute PORT : 0 si un programme écoute sur ce port
    ss -ltn "sport = :$1" 2>/dev/null | grep -q ":$1\b"
}

demarrer() {
    local port="${ODOO_CONF_HTTP_PORT:-8069}" debut=$SECONDS
    etape "Redémarrage du service"
    if (( DO_DRY_RUN )); then sim "systemctl start $SERVICE (puis vérification : service actif, port $port à l'écoute, ${WAIT} s au plus)"; return 0; fi
    if ! sc start "$SERVICE"; then ko "« systemctl start $SERVICE » a échoué (journalctl -u $SERVICE -n 50)"; return 1; fi
    while (( SECONDS - debut <= WAIT )); do
        if [[ "$(sc is-active "$SERVICE" 2>/dev/null || true)" == "active" ]] && port_ecoute "$port"; then
            ok "service $SERVICE actif, port $port à l'écoute (après $((SECONDS - debut)) s)"
            return 0
        fi
        sleep 2
    done
    if [[ "$(sc is-active "$SERVICE" 2>/dev/null || true)" != "active" ]]; then ko "le service $SERVICE n'est pas actif après ${WAIT} s (journalctl -u $SERVICE -n 50)"
    else ko "le service $SERVICE est actif mais rien n'écoute sur le port $port après ${WAIT} s"; fi
    return 1
}

# Préchauffage du cache (odoo-warmup.py) après le redémarrage : pages publiques, derniers événements et sondages, écrans d'administration. Jamais un échec de la mise à jour :
# un problème de préchauffage est un avertissement. Sa sortie détaillée va dans un fichier ; ici, un résumé.
prechauffer() {
    local prog="$SCRIPT_DIR/odoo-warmup.py" port="${ODOO_CONF_HTTP_PORT:-8069}" log code=0 resume lignes
    etape "Préchauffage du cache"
    log="${JOURNAL%.log}-prechauffage.log"
    if (( DO_DRY_RUN )); then sim "python3 $prog --url http://127.0.0.1:$port --db $DB --wait 60 --lang fr > $log"; return 0; fi
    if [[ ! -r "$prog" ]] || ! command -v python3 >/dev/null 2>&1; then
        attn "odoo-warmup.py (ou python3) introuvable : cache non préchauffé — les premiers visiteurs attendront la construction des pages"
        return 0
    fi
    trace python3 "$prog" --url "http://127.0.0.1:$port" --db "$DB" --wait 60 --lang fr
    echo "  ${C_DIM}pages publiques, derniers événements et sondages, administration — en cours…${C_RESET}"
    NGINX_TOOLS_CONFIG_VUE=1 timeout --foreground --kill-after=10 600 python3 "$prog" --url "http://127.0.0.1:$port" --db "$DB" --wait 60 --lang fr > "$log" 2>&1 < /dev/null || code=$?
    resume=$(grep -E '^Pr.chauffage termin' "$log" | tail -n 1 || true)
    if [[ -z "$resume" ]]; then
        attn "préchauffage interrompu (code $code) : voir $log"
        tail -n 5 "$log" | en_retrait "$C_DIM"
        return 0
    fi
    lignes=$(grep -cE '^  \[(OK|.CHEC)' "$log" || true)
    if grep -q '.CHEC ' "$log"; then
        attn "préchauffage terminé avec des échecs (${lignes} appel(s)) :"
        grep -E '^  \[.CHEC' "$log" | head -n 5 | cut -c1-160 | en_retrait "$C_YELLOW"
    else
        ok "cache préchauffé en ${resume#* en }"
    fi
    if grep -q 'administration non pr.chauff.e' "$log"; then
        detail "administration non préchauffée : LOGIN et KEY_FILE à définir dans /etc/default/odoo-warmup.conf (derniers événements et sondages, écrans d'administration)"
    fi
    detail "détail : $log"
    return 0
}


# --- 1.11 : site calme, copie des modules, contrôle après le démarrage, retour arrière ---------------------------------------------
# active_visitors : nombre d'adresses qui ont fait une requête dans les 5 dernières minutes (journaux d'accès de nginx, fin de chaque fichier seulement ;
# robots, outils et ce serveur exclus) ; « ? » si aucun journal n'est lisible.
active_visitors() {
    python3 - "$NGINX_LOG_DIR" <<'PYEOF'
import datetime, glob, os, re, sys
LINE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "[^"]*" \d{3} \S+ "[^"]*" "([^"]*)"')
ROBOT = re.compile(r"bot|crawl|spider|slurp|curl|wget|python|go-http|monitor|uptime|preview", re.I)
now = datetime.datetime.now(datetime.timezone.utc)
seen, readable = set(), False
for path in glob.glob(os.path.join(sys.argv[1], "*access*.log")):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2_000_000))
            data = f.read().decode("utf-8", "replace")
        readable = True
    except OSError:
        continue
    for line in data.splitlines():
        m = LINE.match(line)
        if not m or ROBOT.search(m.group(3)) or m.group(1) in ("127.0.0.1", "::1"):
            continue
        try:
            t = datetime.datetime.strptime(m.group(2), "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            continue
        if (now - t).total_seconds() <= 300:
            seen.add(m.group(1))
print(len(seen) if readable else "?")
PYEOF
}

wait_for_quiet_site() {
    local n debut=$SECONDS poll="${ODOO_UPDATE_MODULE_QUIET_POLL:-30}"
    (( WAIT_QUIET > 0 )) || return 0
    etape "Attente d'un site calme (au plus ${WAIT_QUIET} min, occupé à partir de ${BUSY_VISITORS} visiteur(s) actif(s))"
    while :; do
        n=$(active_visitors 2>/dev/null || echo "?")
        if [[ "$n" == "?" ]]; then attn "journaux d'accès de nginx illisibles dans $NGINX_LOG_DIR : affluence inconnue, pas d'attente"; return 0; fi
        if (( DO_DRY_RUN )); then sim "maintenant : $n visiteur(s) actif(s) dans les 5 dernières minutes — $( (( n < BUSY_VISITORS )) && echo "site calme, pas d'attente" || echo "site occupé : attente d'au plus ${WAIT_QUIET} min" )"; return 0; fi
        if (( n < BUSY_VISITORS )); then ok "site calme : $n visiteur(s) actif(s) dans les 5 dernières minutes"; return 0; fi
        if (( SECONDS - debut >= WAIT_QUIET * 60 )); then
            attn "toujours $n visiteur(s) actif(s) après ${WAIT_QUIET} min : mise à jour quand même"
            return 0
        fi
        echo "  ${C_YELLOW}site occupé : $n visiteur(s) actif(s) dans les 5 dernières minutes${C_RESET} ${C_DIM}— nouvel essai dans ${poll} s (Ctrl+C pour arrêter)${C_RESET}"
        sleep "$poll"
    done
}

# Dossier de chaque module (avant la décompression) : premier dossier de addons_path qui le contient.
declare -A MODULE_DIRS=()
find_module_dirs() {
    local liste chemin nom
    local -a dossiers=()
    liste=$(odoo_conf_valeur "$ODOO_CONF_UTILISEE" addons_path 2>/dev/null || true)
    IFS=',' read -ra dossiers <<< "$liste"
    for nom in "${MODULES_TROUVES[@]}"; do
        for chemin in ${dossiers[@]+"${dossiers[@]}"}; do
            chemin="${chemin#"${chemin%%[![:space:]]*}"}"; chemin="${chemin%"${chemin##*[![:space:]]}"}"
            [[ -n "$chemin" ]] || continue
            [[ "$chemin" == /* ]] || chemin="$ODOO_DIR/$chemin"
            if [[ -f "$chemin/$nom/__manifest__.py" ]]; then MODULE_DIRS[$nom]=$(cd "$chemin/$nom" && pwd); break; fi
        done
    done
}

MODULES_BACKUP=""; CODE_REPLACED=0
backup_modules() {
    local stamp nom f
    local -a chemins=()
    etape "Copie des modules avant la mise à jour (base du retour arrière)"
    for nom in "${MODULES_TROUVES[@]}"; do [[ -n "${MODULE_DIRS[$nom]:-}" ]] && chemins+=("${MODULE_DIRS[$nom]}"); done
    if (( ${#chemins[@]} == 0 )); then detail "aucun module déjà présent sur le disque : rien à copier (nouveaux modules)"; return 0; fi
    stamp=$(date +%Y%m%d-%H%M%S)
    if (( DO_DRY_RUN )); then sim "tar -czPf $MODULES_BACKUP_DIR/modules-$DB-$stamp.tar.gz ${chemins[*]}"; return 0; fi
    if ! mkdir -p "$MODULES_BACKUP_DIR" 2>/dev/null || [[ ! -w "$MODULES_BACKUP_DIR" ]]; then
        ko "dossier des copies inaccessible : $MODULES_BACKUP_DIR (MODULES_BACKUP_DIR) — rien n'a été arrêté"
        return 1
    fi
    chmod 700 "$MODULES_BACKUP_DIR" 2>/dev/null || true
    MODULES_BACKUP="$MODULES_BACKUP_DIR/modules-$DB-$stamp.tar.gz"
    trace tar -czPf "$MODULES_BACKUP" "${chemins[@]}"
    if ! tar -czPf "$MODULES_BACKUP" "${chemins[@]}" 2>/dev/null; then
        rm -f -- "$MODULES_BACKUP"; MODULES_BACKUP=""
        ko "copie des modules impossible (espace disque ?) — rien n'a été arrêté"
        return 1
    fi
    printf '%s\n' "${chemins[@]}" > "${MODULES_BACKUP%.tar.gz}.list"
    ok "${#chemins[@]} module(s) copié(s) : ${C_BOLD}$MODULES_BACKUP${C_RESET} ${C_DIM}($(du -h "$MODULES_BACKUP" | cut -f1))${C_RESET}"
    # shellcheck disable=SC2012  # noms produits par ce programme
    ls -1t "$MODULES_BACKUP_DIR"/modules-*.tar.gz 2>/dev/null | tail -n +11 | while IFS= read -r f; do rm -f -- "$f" "${f%.tar.gz}.list"; done
}

restore_modules() {
    local d
    [[ -n "$MODULES_BACKUP" && -r "$MODULES_BACKUP" ]] || { ko "aucune copie des modules : retour arrière impossible"; return 1; }
    while IFS= read -r d; do
        [[ -n "$d" && "$d" == /* && "$d" != "/" ]] || continue
        trace rm -rf -- "$d"
        rm -rf -- "$d"
    done < "${MODULES_BACKUP%.tar.gz}.list"
    trace tar -xzPf "$MODULES_BACKUP"
    if tar -xzPf "$MODULES_BACKUP" 2>/dev/null; then ok "modules remis dans leur version d'avant (copie $(basename "$MODULES_BACKUP"))"
    else ko "restauration de $MODULES_BACKUP impossible"; return 1; fi
}

# Erreurs d'Odoo depuis le démarrage : journal du service (systemd) et fichier « logfile » de la configuration d'Odoo (heures UTC).
DEMARRAGE_EPOCH=0
check_after_start() {
    local erreurs="" fichier depuis_utc n
    etape "Contrôle du journal d'Odoo depuis le démarrage"
    if (( DO_DRY_RUN )); then sim "journalctl -u $SERVICE --since @DÉMARRAGE : lignes ERROR / CRITICAL (et le fichier logfile d'Odoo)"; return 0; fi
    if (( ! DO_WARMUP )); then sleep "${ODOO_UPDATE_MODULE_SETTLE:-15}"; fi        # sans préchauffage : quelques secondes de vraies requêtes
    if command -v journalctl >/dev/null 2>&1; then
        erreurs=$(journalctl -u "$SERVICE" --since "@$DEMARRAGE_EPOCH" -o cat --no-pager 2>/dev/null | grep -E ' (ERROR|CRITICAL) ' || true)
    fi
    fichier=$(odoo_conf_valeur "$ODOO_CONF_UTILISEE" logfile 2>/dev/null || true)
    [[ -n "$fichier" && "$fichier" != /* ]] && fichier="$ODOO_DIR/$fichier"
    if [[ -n "$fichier" && "${fichier,,}" != */false && -r "$fichier" ]]; then
        depuis_utc=$(date -u -d "@$DEMARRAGE_EPOCH" '+%Y-%m-%d %H:%M:%S')
        erreurs+=$'\n'$(tail -n 20000 "$fichier" | awk -v d="$depuis_utc" 'substr($0, 1, 19) >= d && / (ERROR|CRITICAL) /' || true)
    fi
    erreurs=$(grep -v '^$' <<< "$erreurs" || true)
    if [[ -z "$erreurs" ]]; then ok "aucune erreur (ERROR / CRITICAL) dans le journal d'Odoo depuis le démarrage"; return 0; fi
    n=$(grep -c . <<< "$erreurs")
    ko "${n} ligne(s) ERROR/CRITICAL dans le journal d'Odoo depuis le démarrage — premières :"
    head -n 8 <<< "$erreurs" | cut -c1-300 | en_retrait "$C_RED"
    return 1
}

# Retour arrière : arrêt, modules d'avant remis en place, nouvelle mise à jour (la base suit le code d'avant), redémarrage, contrôle. Question sur un terminal
# (Entrée = oui), automatique sinon (cron, systemd) ; jamais avec --no-rollback (ROLLBACK=non) ni si ce programme n'a pas remplacé le code (pas d'archive).
rollback() {
    local rep=""
    if (( DO_DRY_RUN )); then sim "en cas d'erreur : retour arrière des modules (copie d'avant, nouvelle mise à jour, redémarrage)"; return 1; fi
    if (( ! DO_ROLLBACK )); then attn "retour arrière désactivé (--no-rollback / ROLLBACK=non) : copie d'avant disponible : ${MODULES_BACKUP:-aucune}"; return 1; fi
    if (( ! CODE_REPLACED )); then attn "pas de retour arrière : ce programme n'a pas remplacé le code des modules (pas d'archive .zip) ; copie : ${MODULES_BACKUP:-aucune}"; return 1; fi
    if [[ -z "$MODULES_BACKUP" ]]; then attn "pas de retour arrière : aucune copie des modules d'avant (nouveaux modules seulement)"; return 1; fi
    echo
    if [[ -t 0 && -t 1 ]]; then
        read -r -p "  Retour arrière vers les versions d'avant (copie $(basename "$MODULES_BACKUP")) ? [O/n] " rep || rep=""
        case "${rep,,}" in n|non|no) attn "pas de retour arrière : copie d'avant disponible : $MODULES_BACKUP (tar -xzPf, puis mise à jour)"; return 1 ;; esac
    fi
    ETAPE=0; ETAPES=5; if (( DO_WARMUP )); then ETAPES=6; fi
    echo "${C_BOLD}${C_YELLOW}Retour arrière des modules${C_RESET}"
    arreter || return 1
    etape "Remise en place des modules d'avant"
    restore_modules || { demarrer || true; return 1; }
    JOURNAL="${JOURNAL%.log}-retour-arriere.log"
    mettre_a_jour || { demarrer || true; ko "la mise à jour avec les modules d'avant a échoué aussi : voir $JOURNAL"; return 1; }
    demarrer || return 1
    DEMARRAGE_EPOCH=$(date +%s)
    if (( DO_WARMUP )); then prechauffer; fi
    check_after_start || { ko "erreurs aussi après le retour arrière"; return 1; }
    ok "${C_BOLD}retour arrière réussi${C_RESET} : modules d'avant en service"
    return 0
}

# Ctrl+C confirmé pendant le traitement : le service est remis en route s'il était actif (le site ne reste jamais arrêté).
interrupted_cleanup() {
    if (( ETAIT_ACTIF )) && [[ "$(sc is-active "$SERVICE" 2>/dev/null || true)" != "active" ]]; then
        echo "  Interruption : redémarrage du service $SERVICE (il était actif)…" >&2
        sc start "$SERVICE" >/dev/null 2>&1 || true
    fi
}
# shellcheck disable=SC2034  # lue par apps/_i18n.sh (_ctrl_c_arret)
CTRL_C_NETTOYAGE=interrupted_cleanup

# --- Principal ----------------------------------------------------------------------------------------------------------------
BASE_DU_SERVICE=""; ODOO_CONF_UTILISEE=""; DB=""; CMD_ODOO=""; JOURNAL=""; DOSSIER_JOURNAUX=""
declare -a MODULES_TROUVES=()
if (( ! DO_DRY_RUN )) && [[ "$EUID" -ne 0 && -z "${NGINX_TOOLS_TESTS:-}" ]]; then
    echo "ERREUR: root requis (systemctl stop/start, mise à jour sous le compte du service) — ou --dry-run pour simuler." >&2
    exit 1
fi
if (( ! DO_DRY_RUN )); then prendre_verrou; fi
echo "${C_BOLD}Mise à jour des modules Odoo${C_RESET}  ${C_DIM}$(date '+%Y-%m-%d %H:%M:%S %Z')${C_RESET}"
detecter_service
trouver_conf
if declare -F odoo_conf_charger >/dev/null; then odoo_conf_charger "$ODOO_CONF_UTILISEE" 2>/dev/null || true; fi
trouver_base
trouver_zip
trouver_destination
trouver_modules
commande_odoo
echo
champ "Service :" "${C_BOLD}$SERVICE${C_RESET}$( (( SERVICE_DETECTE )) && printf ' (détecté)' )"
champ "Base :" "${C_BOLD}${C_YELLOW}$DB${C_RESET}"
champ "Modules :" "${C_CYAN}${MODULES_TROUVES[*]}${C_RESET}"
if [[ -n "$ZIP_FICHIER" ]]; then champ "Archive :" "${C_BOLD}$ZIP_FICHIER${C_RESET} ${C_DIM}→ $DESTINATION${C_RESET}"
    for i in "${!ZIP_MODULES[@]}"; do champ "  ${ZIP_MODULES[$i]}" "version ${C_BOLD}${C_CYAN}${ZIP_VERSIONS[$i]}${C_RESET} ${C_DIM}(manifeste de l'archive)${C_RESET}"; done
fi
champ "Compte :" "${C_DIM}${RUN_USER:-$(id -un)}${C_RESET}"
champ "Dossier :" "${C_DIM}${ODOO_DIR:-?}${C_RESET}"
champ "Config Odoo :" "${C_DIM}$ODOO_CONF_UTILISEE${C_RESET}"
if (( DO_DRY_RUN )); then echo "  ${C_YELLOW}Mode simulation : rien n'est arrêté, écrit ni démarré.${C_RESET}"; fi
ETAPES=5; if (( DO_WARMUP )); then ETAPES=6; fi; if (( DO_BACKUP )); then ETAPES=$((ETAPES + 1)); fi
if [[ -n "$ZIP_FICHIER" ]]; then ETAPES=$((ETAPES + 1)); fi
if (( WAIT_QUIET > 0 )); then ETAPES=$((ETAPES + 1)); fi

echecs=0
find_module_dirs
if (( DO_BACKUP )); then sauvegarder || exit 1; fi
wait_for_quiet_site                                           # 1.11: Odoo s'arrête quand le site est calme (au plus WAIT_QUIET min d'attente)
backup_modules || exit 1                                      # 1.11: copie des modules d'avant : base du retour arrière
VERS_AVANT=$(versions_lire)                                   # versions avant la mise à jour (lecture seule)
ZIP_ECHEC=0; ETAIT_ACTIF=0
if [[ "$(sc is-active "$SERVICE" 2>/dev/null || true)" == "active" ]]; then ETAIT_ACTIF=1; fi
arreter || exit 1
verifier_odoo_a_la_main
if [[ -n "$ZIP_FICHIER" ]]; then
    CODE_REPLACED=1                                          # même une décompression interrompue a pu remplacer des fichiers
    decompresser || { echecs=$((echecs + 1)); ZIP_ECHEC=1; }
fi
preparer_journal
if (( ZIP_ECHEC )); then
    ko "mise à jour des modules annulée : l'archive n'a pas été décompressée"
    if [[ -n "$MODULES_BACKUP" ]]; then restore_modules || true; fi           # fichiers à moitié remplacés : remis comme avant (la base n'a pas changé)
    if (( ETAIT_ACTIF )); then sc start "$SERVICE" >/dev/null 2>&1 || true; fi
    exit 1
fi
mettre_a_jour || echecs=$((echecs + 1))
if (( DO_DRY_RUN )); then sim "versions des modules installés avant / après la mise à jour (PostgreSQL, lecture seule)"; else afficher_versions; fi
(( DO_DRY_RUN )) || purger_journaux
if demarrer; then
    DEMARRAGE_EPOCH=$(date +%s)
    if (( DO_WARMUP )); then prechauffer; fi
    check_after_start || echecs=$((echecs + 1))
else
    echecs=$((echecs + 1))
fi
if (( echecs > 0 )); then
    echo
    ko "mise à jour terminée avec ${echecs} échec(s)"
    if rollback; then
        echo
        ko "mise à jour ANNULÉE : les modules d'avant sont en service (journal de l'échec : $JOURNAL)"
    fi
    exit 1
fi
if (( DO_DRY_RUN )); then rollback || true; fi
echo
if (( DO_DRY_RUN )); then echo "${C_BOLD}Simulation terminée.${C_RESET}"; else echo "${C_GREEN}✔ ${C_BOLD}mise à jour terminée${C_RESET} : ${C_CYAN}${MODULES_TROUVES[*]}${C_RESET}"; fi
