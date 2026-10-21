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
# odoo-backup.sh — sauvegarde et restauration de la base PostgreSQL et du filestore d'Odoo, au FORMAT D'ODOO.
#
# Chaque sauvegarde est une archive au format natif d'Odoo (celui de la page du gestionnaire de bases) : dump.sql
# (pg_dump --no-owner, texte), manifest.json (version d'Odoo, de PostgreSQL, modules installés) et filestore/.
# --format zip (défaut) : importable tel quel par la page /web/database/manager d'Odoo ; --format tar.xz : même
# contenu, mieux compressé. Vérifications : fin de dump.sql présente, archive relue, empreinte SHA-256 (.sha256).
# Écriture dans un fichier .partial renommé seulement si tout a réussi ; espace disque vérifié AVANT ; rétention
# quotidienne / hebdomadaire / mensuelle ; copie rsync facultative (ex. vers Proxmox par Tailscale). --restore restaure
# une archive .zip ou .tar.xz sur ce serveur. L'état (dernière réussite, dernier échec) est lu par web-monitor.py.
#
# Usage : odoo-backup.sh [OPTION]...   (sans option : sauvegarder toutes les bases configurées ou détectées)
#
# Options (par ordre alphabétique) :
#   --anonymize                  anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE
#   --changelog                  affiche le journal des modifications
#   -c, --config FILE            ce fichier de configuration SEUL (défaut : /etc/default/odoo-backup.conf, puis
#                                ~/.odoo-backup.conf s'il existe ; la ligne de commande est prioritaire)
#   --db NAME                    une seule base (avec --restore : nom de la base créée)
#   --dest DIR                   autre dossier des sauvegardes (DEST= dans la configuration)
#   --dry-run                    montrer ce qui serait fait, sans rien écrire
#   --format zip|tar.xz          format de l'archive (défaut : zip, importable par la page d'Odoo)
#   -h, --help                   affiche cette aide et quitte
#   --install-timer              sauvegardes automatiques aux heures TIMER_TIME (systemd), une ou plusieurs fois par jour
#   --lang LANG                  langue d'affichage : en ou fr (défaut : LANGUAGE du fichier de configuration, sinon LC_ALL / LC_MESSAGES / LANG)
#   --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
#                                échecs, avertissements) ; désactive couleurs et questions interactives
#   --restore FILE               restaurer une archive .zip ou .tar.xz (jamais d'écrasement : base ou filestore
#                                existant = refus)
#   --status                     sauvegardes présentes, âge de la dernière, timer, copie hors du serveur
#   --test-restore               restaurer la dernière sauvegarde dans une base temporaire, contrôler, supprimer
#   --times "HH:MM ..."          heures des sauvegardes automatiques, une ou plusieurs par jour (ex. --times "09:00 16:00 23:00" ;
#                                défaut : TIMER_TIME du fichier) — à utiliser avec --install-timer
#   --uninstall-timer            retirer la sauvegarde automatique
#   -v, --verbose                afficher chaque commande externe exécutée (psql, pg_dump, tar, rsync, systemctl)
#   --version                    affiche la version et quitte
#
# Configuration (/etc/default/odoo-backup.conf, créée au premier lancement, PUIS ~/.odoo-backup.conf s'il existe ; lue sans être
# exécutée : seules les clés ci-dessous sont retenues ; --dest, --format et --db l'emportent sur les fichiers) :
#   DEST=/var/backups/odoo        dossier des sauvegardes (droits 700)
#   FORMAT=zip                    zip (importable par la page d'Odoo) ou tar.xz
#   DATABASES=                    bases à sauvegarder, séparées par des espaces (vide : db_name d'Odoo, sinon toutes)
#   ODOO_CONF=                    configuration d'Odoo (vide : emplacements connus d'ERPLibre)
#   LANGUAGE=auto                 langue d'affichage : en, fr ou auto (suivre LC_ALL / LANG)
#   FILESTORE_DIR=                dossier contenant les filestores (vide : data_dir d'Odoo, puis emplacements connus)
#   PG_USER=postgres              compte système utilisé pour pg_dump (vide : l'utilisateur courant)
#   KEEP_RECENT_DAYS=2            garder TOUTES les sauvegardes des N derniers jours (utile avec plusieurs sauvegardes par jour)
#   KEEP_DAILY=7 KEEP_WEEKLY=4 KEEP_MONTHLY=6   rétention : ensuite la dernière de chaque jour, semaine ISO, mois
#   REMOTE=                       copie rsync facultative, ex. root@serveur-de-sauvegarde.exemple:/srv/sauvegardes/odoo
#   TIMER_TIME=02:30              heure(s) de la sauvegarde automatique : une ou plusieurs HH:MM (ex. TIMER_TIME=09:00 16:00 23:00)
#
# HISTORIQUE (résumé ; détail : doc/odoo-backup.changelog.txt)
#   1.19.20261020.211944 — Personal configuration file ~/.odoo-backup.conf (not .cfg); a legacy layer with .cfg is renamed automatically.
#   1.18.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.17.20261016.173838 — Ctrl+C answered at once during pg_dump, tar and rsync
#   1.16.20261015.143436 — --anonymize : affichage anonymisé (pseudonymes stables).
#   1.15.20261015.073057 — Date de modification des fichiers de configuration lus.
#   1.14.20261014.175821 — Fichier commun app-default.conf (VERBOSE, DEBUG_LEVEL).
#   1.13.20261012.103600 — Fichier de configuration créé au premier démarrage (toutes les options en commentaire) ; modèle doc/odoo-backup.conf.example complété.
#   1.12.20261010.215000 — Affichage francais ou anglais (--lang, LANGUAGE du fichier de configuration) ; -c, synonyme de --config ; aide en anglais pour les arguments.
#   1.11.20261008.120306 — Couleurs conservees avec --report-err.
#   1.10.20261002.214327 — Premiere ligne de TOUTE execution (meme --help) : nom et version.
#   1.9.20261002.073514 — Option --verbose : chaque commande externe (psql, pg_dump, tar, rsync, systemctl) est affichee.
#   1.8.20260930.163902 — Option --report-err : rapport d'erreurs a copier-coller en fin d'execution.
#   1.7.20260930.132809 — Plusieurs sauvegardes par jour (TIMER_TIME a plusieurs heures, --times) ; KEEP_RECENT_DAYS ; seuil d'alerte
#                          calcule d'apres les heures.
#   1.6.20260930.123230 — Configuration en couches (/etc/default puis ~), ligne de commande prioritaire, fichiers lus affiches ;
#                          ancien fichier renomme AVANT toute operation sur le timer ; timer vers un fichier absent signale.
#   1.5.20260930.093133 — Configuration dans /etc/default/odoo-backup.conf (creee au premier lancement) ; ancien emplacement lu en repli
#                          avec avertissement ; --config introuvable = erreur ; timer sans chemin en dur.
#   1.4.20260930.081347 — Motif « A && B || C » remplace par un « if » (ShellCheck SC2015).
#   1.3.20260929.195459 — Aide : options par ordre alphabetique.
#   1.2.20260929.185720 — --status : etat du timer lu correctement (systemctl is-active).
#   1.1.20260929.180340 — Format d'Odoo (dump.sql, manifest.json, filestore/) en .zip ou .tar.xz ; --restore.
#   1.0.20260929.150745 — Première version : pg_dump vérifié, filestore, SHA256SUMS, rétention, rsync, --test-restore, timer.
# ========================================================================================================================

set -euo pipefail
# PATH complété (2.x) : sous cron, PATH se limite à /usr/bin:/bin — ipset, iptables, nft, fail2ban-client, nginx
# (dans /usr/sbin, /sbin) étaient alors introuvables. Ajoutés À LA FIN : ne masquent jamais une commande déjà trouvée.
for _d in /usr/local/sbin /usr/sbin /sbin; do [[ -n "${NGINX_TOOLS_TESTS:-}" ]] && break; case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac; done
# (Pendant la suite de tests, NGINX_TOOLS_TESTS désactive cet ajout : /usr/sbin/ufw & co resteraient sinon joignables.)
export PATH

readonly SCRIPT_VERSION="1.19.20261020.211944"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}" .sh)"; readonly SCRIPT_NAME
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"; readonly SCRIPT_PATH
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
readonly CHANGELOG_FILE

# Section of this program in CHANGELOG.md (from its "## <file name>" heading to the next "## " heading).
changelog_section() {
    awk -v cle="${BASH_SOURCE[0]##*/}" '/^## /{dans=($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE"
}
# Langue d'affichage (en ou fr) : --lang, ODOO_BACKUP_LANG, LANGUAGE du fichier de configuration, LC_ALL / LANG — apps/_i18n.sh traduit la sortie (rien ne change en français).
if [[ -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_i18n.sh"
    i18n_relancer "$SCRIPT_NAME" ODOO_BACKUP_LANG "$0" "$@"
fi
declare -F run_interruptible >/dev/null || run_interruptible() { "$@"; }     # sans apps/_i18n.sh : exécution simple
readonly STATE_DIR="${ODOO_BACKUP_STATE_DIR:-/var/lib/odoo-backup}"
readonly SYSTEMD_DIR="${ODOO_BACKUP_SYSTEMD_DIR:-/etc/systemd/system}"

if [[ -t 1 || -n "${REPORT_ERR_COULEUR:-}" ]]; then C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_RESET=$'\x1b[0m'
else C_RED=""; C_YELLOW=""; C_GREEN=""; C_RESET=""; fi

# --- Options -----------------------------------------------------------------------------------------------------------
# Règle des fichiers de configuration (tous les programmes) : lire /etc/default/odoo-backup.conf, PUIS ~/.odoo-backup.conf s'il
# existe (le dernier l'emporte), PUIS la ligne de commande (prioritaire sur les fichiers). --config FICHIER (ou la variable
# ODOO_BACKUP_CONFIG) : ce fichier SEUL, qui DOIT exister. Les fichiers lus sont toujours affichés.
readonly CONFIG_DEFAUT="${ODOO_BACKUP_DEFAULT_DIR:-/etc/default}/odoo-backup.conf"
CONFIG_PERSO="${HOME:-/root}/.odoo-backup.conf"
readonly CONFIG_ANCIEN="${HOME:-/root}/.odoo-backup.cfg"      # legacy personal name (rule before 1.19: personal files ended with .cfg)
CONFIG_FILE="${ODOO_BACKUP_CONFIG:-}"; CONFIG_EXPLICITE=0; CLI_OPTIONS=""
if [[ -n "$CONFIG_FILE" ]]; then CONFIG_EXPLICITE=1; fi
RESTORE_FILE=""; OPT_TIMES=""; OPT_FORMAT=""; ONLY_DB=""; DO_DRY_RUN=0; DO_STATUS=0; DO_TEST_RESTORE=0; DO_INSTALL_TIMER=0; DO_UNINSTALL_TIMER=0; OPT_DEST=""; VERBOSE=0
# --report-err : rapport d'erreurs à copier-coller en fin d'exécution (programme, version, serveur, échecs…) — apps/_rapport.sh
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_rapport.sh"
    rapport_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi
# Première ligne de TOUTE exécution, même avec --help : le nom et la version du programme (--version l'affiche lui-même).
case " $* " in *" --version "*) ;; *) echo "odoo-backup.sh v$SCRIPT_VERSION" ;; esac

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--config) CONFIG_FILE="${2:-}"; CONFIG_EXPLICITE=1; shift 2 ;;
        --lang) shift 2 ;;                     # lu avant (apps/_i18n.sh)
        --lang=*) shift ;;
        --db) ONLY_DB="${2:-}"; CLI_OPTIONS+=" --db ${2:-}"; shift 2 ;;
        --dest) OPT_DEST="${2:-}"; CLI_OPTIONS+=" --dest ${2:-}"; shift 2 ;;
        --format) OPT_FORMAT="${2:-}"; CLI_OPTIONS+=" --format ${2:-}"; shift 2 ;;
        --restore) RESTORE_FILE="${2:-}"; shift 2 ;;
        --times) OPT_TIMES="${2:-}"; CLI_OPTIONS+=" --times \"${2:-}\""; shift 2 ;;
        --dry-run) DO_DRY_RUN=1; shift ;;
        --status) DO_STATUS=1; shift ;;
        --test-restore) DO_TEST_RESTORE=1; shift ;;
        --install-timer) DO_INSTALL_TIMER=1; shift ;;
        --uninstall-timer) DO_UNINSTALL_TIMER=1; shift ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --version) echo "odoo-backup.sh version $SCRIPT_VERSION"; exit 0 ;;
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
        -h|--help) sed -n '/^# Usage :/,/^# HISTORIQUE/p' "$SCRIPT_PATH" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        --report-err) shift ;;                 # traité avant (apps/_rapport.sh) ; accepté ici avec --help, --version…
        *) echo "Argument inconnu: $1 (voir --help)" >&2; exit 1 ;;
    esac
done

# --- Configuration : migration et création (actions qui ÉCRIVENT, en root, sans --config) ---------------------------------
# Action qui écrit : sauvegarde, restauration, timer. Jamais : --status, --dry-run, --test-restore, --uninstall-timer.
ACTION_ECRIT=1
if [[ "$DO_STATUS" == "1" || "$DO_DRY_RUN" == "1" || "$DO_TEST_RESTORE" == "1" || "$DO_UNINSTALL_TIMER" == "1" ]]; then ACTION_ECRIT=0; fi
if [[ -n "$RESTORE_FILE" ]]; then ACTION_ECRIT=0; fi

# Le service systemd peut contenir l'ancien chemin de configuration en dur (--config, avant la 1.5) : retiré IMMÉDIATEMENT après
# le renommage, sans arrêter le timer, pour qu'il ne pointe jamais vers un fichier absent (il retrouve seul /etc/default).
retirer_chemin_du_service() {
    local ancien="$1" unite="$SYSTEMD_DIR/odoo-backup.service" contenu
    [[ -f "$unite" ]] || return 0
    contenu=$(cat "$unite")
    [[ "$contenu" == *" --config $ancien"* ]] || return 0
    printf '%s\n' "${contenu//" --config $ancien"/}" > "$unite.tmp" && mv -f "$unite.tmp" "$unite"
    systemctl daemon-reload >/dev/null 2>&1 || true
    echo "Timer : chemin de l'ancien fichier retiré du service (il retrouve seul $CONFIG_DEFAUT) ; le timer n'a PAS été arrêté." >&2
}

# Ancien fichier de configuration (avant la 1.5 : ~/.odoo-backup.cfg, seule configuration) → /etc/default : RENOMMÉ d'abord,
# service corrigé ensuite, AVANT toute opération sur le timer (--install-timer l'arrête puis le relance après). Seulement si
# /etc/default/odoo-backup.conf n'existe pas : un fichier personnel à côté d'un fichier système est une couche voulue (1.19 : l'ancien nom
# ~/.odoo-backup.cfg devient alors ~/.odoo-backup.conf, voir migrer_ancien_nom).
migrer_config_perso() {
    [[ "$EUID" -eq 0 && ! -e "$CONFIG_DEFAUT" && -f "$CONFIG_ANCIEN" && ! -e "$CONFIG_PERSO" ]] || return 0
    mkdir -p "$(dirname "$CONFIG_DEFAUT")" 2>/dev/null || return 0
    mv -- "$CONFIG_ANCIEN" "$CONFIG_DEFAUT" || return 0
    chmod 600 "$CONFIG_DEFAUT" 2>/dev/null || true
    echo "Migration : configuration renommée $CONFIG_ANCIEN → $CONFIG_DEFAUT" >&2
    retirer_chemin_du_service "$CONFIG_ANCIEN"
}

# 1.19 — personal file ~/.odoo-backup.conf (common rule): a legacy ~/.odoo-backup.cfg kept as a LAYER (a system file exists) is renamed to it
# (apps/_i18n.sh config_migrer_ancien: same notices as every program); the service (old path in its --config) is corrected at once, like above.
# Both files: the .conf is read, the .cfg is reported and ignored. Rename impossible: the legacy file is read as is.
migrer_ancien_nom() {
    [[ -e "$CONFIG_ANCIEN" || -L "$CONFIG_ANCIEN" ]] || return 0
    if declare -F config_migrer_ancien >/dev/null; then
        config_migrer_ancien "$CONFIG_PERSO"
        CONFIG_PERSO="$CFG_A_LIRE"
    elif [[ ! -e "$CONFIG_PERSO" ]] && mv -n -- "$CONFIG_ANCIEN" "$CONFIG_PERSO" 2>/dev/null && [[ ! -e "$CONFIG_ANCIEN" ]]; then
        echo "Configuration : ancien fichier $CONFIG_ANCIEN renommé en $CONFIG_PERSO (les fichiers personnels se terminent maintenant par .conf)" >&2
    elif [[ ! -e "$CONFIG_PERSO" ]]; then
        CONFIG_PERSO="$CONFIG_ANCIEN"
    fi
    if [[ "$CONFIG_PERSO" != "$CONFIG_ANCIEN" && ! -e "$CONFIG_ANCIEN" && "$EUID" -eq 0 ]]; then retirer_chemin_du_service "$CONFIG_ANCIEN"; fi
    return 0
}

# Création au premier lancement (comme app-health-check.py) : modèle commenté dans /etc/default, droits 600.
creer_config_defaut() {
    [[ "$EUID" -eq 0 && ! -e "$CONFIG_DEFAUT" ]] || return 0
    mkdir -p "$(dirname "$CONFIG_DEFAUT")" 2>/dev/null || return 0
    cat > "$CONFIG_DEFAUT" <<'EOF' || return 0
# Configuration de odoo-backup.sh — créée automatiquement au premier lancement. Lue sans être exécutée : seules les clés
# ci-dessous sont retenues (les lignes commencent par # : valeurs par défaut). Enlever le # pour changer une valeur.
# Ordre de lecture : ce fichier, PUIS ~/.odoo-backup.conf s'il existe (prioritaire), PUIS la ligne de commande (--dest,
# --format, --db), prioritaire sur les fichiers.
#
# Copie hors du serveur (rsync), ex. vers un autre serveur par Tailscale : INDISPENSABLE — une sauvegarde sur le même
# serveur ne protège ni d'une panne du serveur ni d'un rançongiciel.
#REMOTE=root@serveur-de-sauvegarde.exemple:/srv/sauvegardes/odoo
#
#DEST=/var/backups/odoo            # dossier des sauvegardes (droits 700)
#FORMAT=zip                        # zip (importable par la page d'Odoo) ou tar.xz
#DATABASES=                        # vide : db_name d'Odoo, sinon toutes les bases
#ODOO_CONF=                        # vide : emplacements connus d'ERPLibre
#LANGUAGE=auto                     # langue d'affichage : en, fr ou auto (suivre LC_ALL / LANG)
#FILESTORE_DIR=                    # vide : data_dir d'Odoo, puis emplacements connus
#PG_USER=postgres                  # compte système de pg_dump (vide : l'utilisateur courant)
#KEEP_RECENT_DAYS=2               # garder TOUTES les sauvegardes des N derniers jours (plusieurs par jour)
#KEEP_DAILY=7                      # ensuite : la dernière de chaque jour pendant N jours,
#KEEP_WEEKLY=4                     #           la dernière de chaque semaine pendant N semaines,
#KEEP_MONTHLY=6                    #           la dernière de chaque mois pendant N mois
#TIMER_TIME=02:30                  # heure(s) de la sauvegarde automatique, une ou plusieurs : TIMER_TIME=09:00 16:00 23:00
EOF
    chmod 600 "$CONFIG_DEFAUT" 2>/dev/null || true
    echo "Configuration créée : $CONFIG_DEFAUT (modèle commenté ; à compléter, surtout REMOTE : copie hors du serveur)." >&2
}
if (( ACTION_ECRIT && ! CONFIG_EXPLICITE )); then migrer_config_perso; creer_config_defaut; fi
if (( ! CONFIG_EXPLICITE )); then migrer_ancien_nom; fi

# --- Configuration : fichiers lus, dans l'ordre (le dernier l'emporte) ------------------------------------------------------
FICHIERS_CONFIG=()
if (( CONFIG_EXPLICITE )); then
    # Un fichier demandé et introuvable n'est JAMAIS ignoré : les valeurs par défaut (sans REMOTE : plus de copie hors du
    # serveur) s'appliqueraient en silence.
    [[ -e "$CONFIG_FILE" ]] || { echo "ERREUR: configuration introuvable : $CONFIG_FILE" >&2; exit 1; }
    FICHIERS_CONFIG=("$CONFIG_FILE")
else
    if [[ -e "$CONFIG_DEFAUT" ]]; then FICHIERS_CONFIG+=("$CONFIG_DEFAUT"); fi
    if [[ -e "$CONFIG_PERSO" ]]; then FICHIERS_CONFIG+=("$CONFIG_PERSO"); fi
    CONFIG_FILE="$CONFIG_DEFAUT"
fi
for fichier_config in ${FICHIERS_CONFIG[@]+"${FICHIERS_CONFIG[@]}"}; do
    if [[ ! -r "$fichier_config" ]]; then echo "ERREUR: configuration illisible (droits) : $fichier_config" >&2; exit 1; fi
done

# --- Configuration : lue ligne à ligne, JAMAIS exécutée (pas de « source ») ; clés inconnues ignorées ---------------
DEST=/var/backups/odoo; FORMAT=zip; DATABASES=""; ODOO_CONF=""; FILESTORE_DIR=""; PG_USER=postgres
KEEP_RECENT_DAYS=2; KEEP_DAILY=7; KEEP_WEEKLY=4; KEEP_MONTHLY=6; REMOTE=""; TIMER_TIME=02:30
for fichier_config in ${FICHIERS_CONFIG[@]+"${FICHIERS_CONFIG[@]}"}; do
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        [[ "$ligne" =~ ^[[:space:]]*(DEST|FORMAT|DATABASES|ODOO_CONF|FILESTORE_DIR|PG_USER|KEEP_RECENT_DAYS|KEEP_DAILY|KEEP_WEEKLY|KEEP_MONTHLY|REMOTE|TIMER_TIME)=(.*)$ ]] || continue
        valeur="${BASH_REMATCH[2]%%#*}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"; valeur="${valeur#\"}"; valeur="${valeur%\"}"
        printf -v "${BASH_REMATCH[1]}" '%s' "$valeur"
    done < "$fichier_config"
done
# Fichier COMMUN à tous les programmes (app-default.conf, puis ~/.app-default.conf) : seulement VERBOSE et DEBUG_LEVEL ; la clé du fichier du programme l'emporte.
if (( ! CONFIG_EXPLICITE )); then
    commun_perso="${HOME:-/root}/.app-default.conf"
    if declare -F config_migrer_ancien >/dev/null; then config_migrer_ancien "$commun_perso"; commun_perso="$CFG_A_LIRE"; fi     # 1.19: legacy ~/.app-default.cfg renamed
    for fichier_commun in "${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/app-default.conf" "$commun_perso"; do
        [[ -r "$fichier_commun" ]] || continue
        while IFS= read -r ligne || [[ -n "$ligne" ]]; do
            [[ "$ligne" =~ ^[[:space:]]*(VERBOSE|DEBUG_LEVEL)=(.*)$ ]] || continue
            valeur="${BASH_REMATCH[2]%%#*}"; valeur="${valeur%"${valeur##*[![:space:]]}"}"; valeur="${valeur#\"}"; valeur="${valeur%\"}"
            case "${BASH_REMATCH[1]}:${valeur,,}" in
                VERBOSE:1|VERBOSE:true|VERBOSE:yes|VERBOSE:oui|VERBOSE:on) VERBOSE=1 ;;
                DEBUG_LEVEL:[1-9]*) VERBOSE=1; export NGINX_TOOLS_DEBUG_LEVEL="${valeur}" ;;
            esac
        done < "$fichier_commun"
    done
fi
[[ -n "$OPT_DEST" ]] && DEST="$OPT_DEST"
[[ -n "$OPT_FORMAT" ]] && FORMAT="$OPT_FORMAT"
[[ -n "$OPT_TIMES" ]] && TIMER_TIME="$OPT_TIMES"
[[ "$FORMAT" == "zip" || "$FORMAT" == "tar.xz" ]] || { echo "ERREUR: format « $FORMAT » inconnu (zip ou tar.xz)." >&2; exit 1; }
for n in KEEP_RECENT_DAYS KEEP_DAILY KEEP_WEEKLY KEEP_MONTHLY; do
    [[ "${!n}" =~ ^[0-9]+$ ]] || { echo "ERREUR: $n doit être un entier (reçu : « ${!n} »)." >&2; exit 1; }
done
# Heures des sauvegardes : une ou plusieurs HH:MM (espaces ou virgules) ; « 9:00 » devient « 09:00 » ; triées, sans doublon.
normaliser_heures() {
    local h mot
    local -a mots=() res=()
    read -ra mots <<< "${1//,/ }"
    for mot in ${mots[@]+"${mots[@]}"}; do
        [[ "$mot" =~ ^([0-9]{1,2}):([0-5][0-9])$ ]] || return 1
        h=$((10#${BASH_REMATCH[1]}))
        if (( h > 23 )); then return 1; fi
        res+=("$(printf '%02d:%s' "$h" "${BASH_REMATCH[2]}")")
    done
    if (( ${#res[@]} == 0 )); then return 1; fi
    printf '%s\n' "${res[@]}" | sort -u | tr '\n' ' ' | sed 's/ $//'
}
TIMER_TIME_BRUT="$TIMER_TIME"
TIMER_TIME=$(normaliser_heures "$TIMER_TIME_BRUT") || { echo "ERREUR: TIMER_TIME attend une ou plusieurs heures HH:MM, ex. « 09:00 16:00 23:00 » (reçu : « $TIMER_TIME_BRUT »)." >&2; exit 1; }
read -ra HEURES <<< "$TIMER_TIME"
# Écart maximal entre deux sauvegardes consécutives (cyclique, en heures) + 2 h de marge : au-delà, la dernière sauvegarde est
# trop ancienne (une seule par jour : 24 + 2 = 26 h, comme avant ; 09:00 16:00 23:00 : 10 + 2 = 12 h).
calculer_seuil_heures() {
    local prec="" premier="" h m ecart max=0
    for h in "${HEURES[@]}"; do
        m=$((10#${h%%:*} * 60 + 10#${h##*:}))
        if [[ -z "$premier" ]]; then premier=$m; else ecart=$((m - prec)); if (( ecart > max )); then max=$ecart; fi; fi
        prec=$m
    done
    ecart=$((premier + 1440 - prec)); if (( ecart > max )); then max=$ecart; fi    # du dernier au premier, le lendemain
    echo $(( (max + 59) / 60 + 2 ))
}
SEUIL_HEURES=$(calculer_seuil_heures)

# Quels fichiers sont lus, et les options importantes : deux lignes (l'affichage ne dépend jamais de la couleur).
afficher_configuration() {
    local lus="" f bases_txt copie_txt cli_txt=""
    if (( CONFIG_EXPLICITE )); then
        lus="$CONFIG_FILE (modifié le $(date -r "$CONFIG_FILE" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '?')) (demandé par --config : ni /etc/default ni ~ ne sont lus)"
    elif (( ${#FICHIERS_CONFIG[@]} == 0 )); then
        lus="aucune (valeurs par défaut) — créée au premier lancement : $CONFIG_DEFAUT"
    else
        for f in "${FICHIERS_CONFIG[@]}"; do lus+="${lus:+, puis }$f (modifié le $(date -r "$f" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '?'))"; done
        if (( ${#FICHIERS_CONFIG[@]} > 1 )); then lus+=" (le dernier l'emporte)"; fi
    fi
    if [[ -n "$ONLY_DB" ]]; then bases_txt="$ONLY_DB"
    elif [[ -n "$DATABASES" ]]; then bases_txt="$DATABASES"
    else bases_txt="automatique (db_name d'Odoo)"; fi
    if [[ -n "$REMOTE" ]]; then copie_txt="$REMOTE"; else copie_txt="${C_YELLOW}AUCUNE${C_RESET}"; fi
    if [[ -n "$CLI_OPTIONS" ]]; then cli_txt=" · ligne de commande (prioritaire) :$CLI_OPTIONS"; fi
    echo "  Configuration lue : $lus"
    echo "  Options : --lang ${NGINX_TOOLS_I18N_LANGUE:-fr} · sauvegardes dans $DEST ($FORMAT) aux heures : ${TIMER_TIME// /, } · bases : $bases_txt · copie hors du serveur : $copie_txt · rétention : tout sur $KEEP_RECENT_DAYS j, puis $KEEP_DAILY j / $KEEP_WEEKLY sem. / $KEEP_MONTHLY mois$cli_txt"
}

# Verrou (flock) : une seule exécution MODIFIANTE à la fois — cron, timer systemd et lancement manuel peuvent se
# croiser. Attente en secondes (0 : abandon immédiat). Dossier : NGINX_TOOLS_LOCK_DIR (tests), sinon /run/lock, sinon
# /tmp. Un appel imbriqué du même script (ex. --import-bans qui lance --ban) réutilise le verrou déjà tenu.
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
if [[ "$DO_STATUS" != "1" && "$DO_DRY_RUN" != "1" ]]; then prendre_verrou 0 odoo-backup; fi
# grep_q : equivalent de « grep -q » SANS la course SIGPIPE sous « set -o pipefail » (lit toute l'entree).
grep_q() { grep "$@" > /dev/null; }

# --- Outils -------------------------------------------------------------------------------------------------------------
ok()   { echo "  ${C_GREEN}[OK]${C_RESET}   $*"; }
attn() { echo "  ${C_YELLOW}[ATTN]${C_RESET} $*"; }
ko()   { echo "  ${C_RED}[FAIL]${C_RESET} $*"; }
octets() { numfmt --to=iec --suffix=o "${1:-0}" 2>/dev/null | sed -E 's/^([0-9.,]+)([KMGTP]?)o$/\1 \2o/' || echo "${1:-0} o"; }
# Commandes PostgreSQL sous le compte PG_USER (root : runuser) ; sinon l'utilisateur courant.
exec 3>&2
trace() {       # --verbose : la commande externe exacte, avant son exécution (sur la sortie d'erreur)
    if [[ "$VERBOSE" == "1" ]]; then printf '+ %s\n' "$*" >&3; fi
    return 0
}
pg() {
    if [[ -n "$PG_USER" && "$EUID" -eq 0 && "$(id -un)" != "$PG_USER" ]]; then
        trace runuser -u "$PG_USER" -- "$@"
        runuser -u "$PG_USER" -- "$@"
    else
        trace "$@"
        "$@"
    fi
}

conf_odoo() {
    local c
    for c in "$ODOO_CONF" /opt/odoo/erplibre/config.conf /home/utilisateur/git/erplibre/config.conf /etc/odoo/odoo.conf; do
        [[ -n "$c" && -r "$c" ]] && { echo "$c"; return 0; }
    done
    return 0
}
valeur_odoo() {       # valeur_odoo CLÉ : clé de la section [options] de la configuration d'Odoo (vide si absente)
    local c; c=$(conf_odoo); [[ -z "$c" ]] && return 0
    awk -F'=' -v k="$1" '/^\[/ { dans = ($0 ~ /^\[options\]/) } dans && $1 ~ "^[ \t]*" k "[ \t]*$" { v = $2; sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v); print v; exit }' "$c"
}
bases() {
    if [[ -n "$ONLY_DB" ]]; then echo "$ONLY_DB"; return 0; fi
    if [[ -n "$DATABASES" ]]; then tr ' ' '\n' <<< "$DATABASES" | grep .; return 0; fi
    local nom; nom=$(valeur_odoo db_name)
    if [[ -n "$nom" && "$nom" != "False" && "$nom" != *","* ]]; then echo "$nom"; return 0; fi
    pg psql -Atc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1" 2>/dev/null || true
}
filestore_de() {       # dossier du filestore de la base $1 (vide si introuvable)
    local db="$1" d dd
    dd=$(valeur_odoo data_dir)
    for d in "${FILESTORE_DIR:+$FILESTORE_DIR/$db}" "${dd:+$dd/filestore/$db}" "/opt/odoo/.local/share/Odoo/filestore/$db" \
             "/var/lib/odoo/filestore/$db" "/var/lib/odoo/.local/share/Odoo/filestore/$db" "$HOME/.local/share/Odoo/filestore/$db"; do
        [[ -n "$d" && -d "$d" ]] && { echo "$d"; return 0; }
    done
    return 0
}
noter() {             # noter success|failure MESSAGE : état lu par web-monitor.py et --status
    [[ "$DO_DRY_RUN" == "1" ]] && return 0
    mkdir -p "$STATE_DIR" 2>/dev/null || return 0
    printf '%s\t%s\t%s\n' "$(date +%s)" "$(date '+%Y-%m-%d %H:%M')" "$2" > "$STATE_DIR/last-$1" 2>/dev/null || true
    # Âge maximal toléré de la dernière sauvegarde (selon les heures configurées) : lu par web-monitor.py
    if [[ "$1" == "success" ]]; then echo "$SEUIL_HEURES" > "$STATE_DIR/max-age-hours" 2>/dev/null || true; fi
}

# --- Sauvegarde d'une base, au format d'Odoo ---------------------------------------------------------------------------
# Motif des archives : BASE_AAAA-MM-JJ_HHMMSS.zip|.tar.xz (+ .sha256). Contenu identique à la sauvegarde de la page
# d'Odoo (odoo/service/db.py : dump_db) : dump.sql, manifest.json (dump_db_manifest), filestore/.
MOTIF_ARCHIVE='_([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6})\.(zip|tar\.xz)$'
manifest_json() {      # manifest_json BASE FICHIER : manifest.json d'Odoo (version, PostgreSQL, modules installés)
    local db="$1" sortie="$2" base_v pgv modules
    base_v=$(pg psql -Atc "SELECT latest_version FROM ir_module_module WHERE name = 'base'" -d "$db" 2>/dev/null) || base_v=""
    pgv=$(pg psql -Atc "SHOW server_version" -d "$db" 2>/dev/null) || pgv=""
    modules=$(pg psql -Atc "SELECT name || '=' || coalesce(latest_version, '') FROM ir_module_module WHERE state = 'installed' ORDER BY name" -d "$db" 2>/dev/null) || modules=""
    DB="$db" BASE_V="$base_v" PGV="$pgv" MODULES="$modules" python3 - "$sortie" <<'PY'
import json, os, re, sys
base = os.environ["BASE_V"].strip()
major = ".".join(base.split(".")[:2]) if base else ""
m = re.match(r"(\d+)\.(\d+)", major)
pg = re.match(r"(\d+)(?:\.(\d+))?", os.environ["PGV"].strip() or "0")
modules = dict(l.split("=", 1) for l in os.environ["MODULES"].splitlines() if "=" in l)
json.dump({"odoo_dump": "1", "db_name": os.environ["DB"], "version": major, "major_version": major,
           "version_info": [int(m.group(1)), int(m.group(2)), 0, "final", 0, ""] if m else [],
           "pg_version": f"{pg.group(1)}.{pg.group(2) or 0}", "modules": modules}, open(sys.argv[1], "w"), indent=4)
PY
}
archiver() {           # archiver FORMAT SORTIE DOSSIER_TEMP FILESTORE : dump.sql + manifest.json + filestore/
    local fmt="$1" sortie="$2" tmp="$3" fs="$4"
    if [[ "$fmt" == "zip" ]]; then
        trace python3 - "$sortie" "$tmp" "$fs"
        python3 - "$sortie" "$tmp" "$fs" <<'PY'
import os, sys, zipfile
sortie, tmp, fs = sys.argv[1:4]
with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
    z.write(os.path.join(tmp, "dump.sql"), "dump.sql")
    z.write(os.path.join(tmp, "manifest.json"), "manifest.json")
    if fs and os.path.isdir(fs):
        for racine, dossiers, fichiers in os.walk(fs):
            dossiers.sort()
            for f in sorted(fichiers):
                chemin = os.path.join(racine, f)
                z.write(chemin, os.path.join("filestore", os.path.relpath(chemin, fs)))
with zipfile.ZipFile(sortie) as z:                  # relecture complète (CRC de chaque fichier)
    noms = set(z.namelist())
    if z.testzip() is not None or not {"dump.sql", "manifest.json"} <= noms:
        sys.exit("archive ZIP illisible ou incomplète")
PY
    else
        if [[ -n "$fs" ]]; then
            trace tar -cJf "$sortie" -C "$tmp" dump.sql manifest.json -C "$(dirname "$fs")" "$(basename "$fs")"
            XZ_OPT="${XZ_OPT:--6 -T0}" run_interruptible tar -cJf "$sortie" -C "$tmp" dump.sql manifest.json \
                -C "$(dirname "$fs")" --transform "s,^$(basename "$fs"),filestore," "$(basename "$fs")"
        else
            trace tar -cJf "$sortie" -C "$tmp" dump.sql manifest.json
            XZ_OPT="${XZ_OPT:--6 -T0}" run_interruptible tar -cJf "$sortie" -C "$tmp" dump.sql manifest.json
        fi
        tar -tJf "$sortie" | grep_q -x 'dump.sql' || { echo "archive tar.xz illisible ou incomplète" >&2; return 1; }
    fi
}
sauvegarder() {
    local db="$1" ts fs tmp nom final besoin libre taille_db taille_fs=0 nb_fichiers=0
    ts=$(date '+%Y-%m-%d_%H%M%S'); nom="${db}_${ts}.${FORMAT}"; final="$DEST/$db/$nom"
    fs=$(filestore_de "$db")
    taille_db=$(pg psql -Atc "SELECT pg_database_size('$db')" 2>/dev/null) || taille_db=0
    [[ "$taille_db" =~ ^[0-9]+$ ]] || taille_db=0
    if [[ -n "$fs" ]]; then taille_fs=$(du -sb "$fs" 2>/dev/null | cut -f1) || taille_fs=0; nb_fichiers=$(find "$fs" -type f | wc -l); fi
    echo "Base $db — base $(octets "$taille_db"), filestore ${fs:-INTROUVABLE} ($(octets "$taille_fs"), $nb_fichiers fichier(s)) — format $FORMAT"
    if [[ "$DO_DRY_RUN" == "1" ]]; then
        echo "  (--dry-run) écrirait $final (dump.sql, manifest.json, filestore/) et $final.sha256"
        return 0
    fi
    mkdir -p "$DEST/$db"; chmod 700 "$DEST" "$DEST/$db" 2>/dev/null || true
    besoin=$(( (2 * taille_db + taille_fs) * 12 / 10 ))          # dump.sql temporaire + archive
    libre=$(df -B1 --output=avail "$DEST" 2>/dev/null | tail -1 | tr -d ' ') || libre=0
    if [[ "$libre" =~ ^[0-9]+$ ]] && (( libre > 0 && besoin > libre )); then
        ko "espace insuffisant dans $DEST : $(octets "$libre") libres, $(octets "$besoin") nécessaires — sauvegarde de $db ANNULÉE."
        return 1
    fi
    tmp=$(mktemp -d "$DEST/$db/.partial-XXXXXX"); chmod 700 "$tmp"
    if ! run_interruptible pg pg_dump --no-owner -d "$db" > "$tmp/dump.sql" 2> "$tmp/errors.txt"; then      # 1.x: Ctrl+C answered at once, « no » lets the dump finish
        ko "pg_dump de $db en échec : $(head -c 300 "$tmp/errors.txt")"; rm -rf "$tmp"; return 1
    fi
    if ! tail -c 4096 "$tmp/dump.sql" | grep_q 'PostgreSQL database dump complete'; then
        ko "dump de $db incomplet (marque de fin de pg_dump absente) — sauvegarde rejetée."; rm -rf "$tmp"; return 1
    fi
    if ! manifest_json "$db" "$tmp/manifest.json" 2>> "$tmp/errors.txt"; then
        ko "manifest.json de $db impossible à produire : $(tail -c 300 "$tmp/errors.txt")"; rm -rf "$tmp"; return 1
    fi
    if ! archiver "$FORMAT" "$tmp/$nom" "$tmp" "$fs" 2>> "$tmp/errors.txt"; then
        ko "archive de $db en échec : $(tail -c 300 "$tmp/errors.txt")"; rm -rf "$tmp"; return 1
    fi
    (cd "$tmp" && sha256sum -- "$nom" > "$nom.sha256")
    mv "$tmp/$nom" "$final" && mv "$tmp/$nom.sha256" "$final.sha256"
    rm -rf "$tmp"
    local total; total=$(stat -c %s "$final")
    if [[ -n "$fs" ]]; then ok "$db : $final ($(octets "$total") ; dump, manifest et filestore vérifiés)"
    else attn "$db : $final ($(octets "$total")) — FILESTORE INTROUVABLE : pièces jointes non sauvegardées (FILESTORE_DIR)"; fi
    noter success "$db $final $total"
    if [[ -n "$REMOTE" ]]; then
        trace rsync -a --partial --mkpath "$final" "$final.sha256" "$REMOTE/$db/"
        if run_interruptible rsync -a --partial --mkpath "$final" "$final.sha256" "$REMOTE/$db/" 2>/tmp/odoo-backup-rsync.$$; then
            ok "copie hors du serveur : $REMOTE/$db/$nom"
        else
            attn "copie vers $REMOTE en échec ($(head -c 200 /tmp/odoo-backup-rsync.$$)) — la sauvegarde locale reste valable."
            noter failure "copie rsync vers $REMOTE en échec"
        fi
        rm -f /tmp/odoo-backup-rsync.$$
    fi
    retention "$db"
}

# --- Rétention : la plus récente de chaque jour (KEEP_DAILY jours), semaine ISO (KEEP_WEEKLY), mois (KEEP_MONTHLY) ---
retention() {          # rétention INDÉPENDANTE par format : une sauvegarde manuelle en tar.xz n'efface pas le zip du jour
    local db="$1" fmt f d j s m garder nj ns nm recent=""
    find "$DEST/$db" -maxdepth 1 -name '.partial-*' -mmin +1440 -exec rm -rf {} + 2>/dev/null || true
    # KEEP_RECENT_DAYS : TOUTES les sauvegardes des N derniers jours (aujourd'hui compris) — sans cela, avec plusieurs
    # sauvegardes par jour, seule la dernière de chaque jour serait gardée et les précédentes effacées aussitôt.
    if (( KEEP_RECENT_DAYS > 0 )); then recent=$(date -d "-$((KEEP_RECENT_DAYS - 1)) days" +%Y-%m-%d); fi
    for fmt in zip tar.xz; do
        local -A vu_j=() vu_s=() vu_m=()
        nj=0; ns=0; nm=0
        while IFS=$'\t' read -r d f; do
            [[ "$f" == *".$fmt" ]] || continue
            j=${d:0:10}; m=${d:0:7}; s=$(date -d "$j" +%G-%V 2>/dev/null) || s="$j"; garder=0
            if [[ -z "${vu_j[$j]:-}" ]]; then vu_j[$j]=1; nj=$((nj + 1)); (( nj <= KEEP_DAILY )) && garder=1; fi
            if [[ -z "${vu_s[$s]:-}" ]]; then vu_s[$s]=1; ns=$((ns + 1)); (( ns <= KEEP_WEEKLY )) && garder=1; fi
            if [[ -z "${vu_m[$m]:-}" ]]; then vu_m[$m]=1; nm=$((nm + 1)); (( nm <= KEEP_MONTHLY )) && garder=1; fi
            if [[ -n "$recent" && ! "$j" < "$recent" ]]; then garder=1; fi
            if (( ! garder )); then rm -f "${DEST:?}/$db/$f" "${DEST:?}/$db/$f.sha256"; echo "  rétention : $f supprimée"; fi
        done < <(archives "$db")
        unset vu_j vu_s vu_m
    done
}
archives() {           # archives BASE : « date<TAB>fichier », la plus récente d'abord (seuls les noms au format du programme)
    find "$DEST/$1" -mindepth 1 -maxdepth 1 -type f -printf '%f\n' 2>/dev/null \
        | sed -nE "s/^(.+)${MOTIF_ARCHIVE}/\\2\t&/p" | sort -r
}

# --- --status -----------------------------------------------------------------------------------------------------------
afficher_statut() {
    local db rc=0 dernier age n
    echo "$(hostname) — sauvegardes dans $DEST (format $FORMAT)"
    afficher_configuration
    if [[ -f "$SYSTEMD_DIR/odoo-backup.service" ]]; then
        local script_timer cfg_timer
        script_timer=$(sed -n 's/^ExecStart=\([^ ]*\).*/\1/p' "$SYSTEMD_DIR/odoo-backup.service")
        cfg_timer=$(sed -n 's/^ExecStart=.* --config \([^ ]*\).*/\1/p' "$SYSTEMD_DIR/odoo-backup.service")
        if [[ -n "$script_timer" && ! -e "$script_timer" ]]; then
            ko "le timer lance $script_timer, qui N'EXISTE PAS — la sauvegarde automatique échoue : $SCRIPT_PATH --install-timer"; rc=1
        fi
        if [[ -n "$cfg_timer" && ! -e "$cfg_timer" ]]; then
            ko "le timer lit --config $cfg_timer, qui N'EXISTE PAS — chaque sauvegarde automatique échoue (avant la 1.5 elle s'exécutait sans REMOTE, en silence) : $SCRIPT_PATH --install-timer"; rc=1
        elif [[ -n "$cfg_timer" ]]; then
            attn "le timer lit seulement --config $cfg_timer, pas la configuration par défaut — relancer : $SCRIPT_PATH --install-timer"
        fi
    fi
    for db in $(bases); do
        dernier=$(archives "$db" | head -1 | cut -f2) || dernier=""
        if [[ -z "$dernier" ]]; then ko "$db : AUCUNE sauvegarde"; rc=1; continue; fi
        age=$(( ($(date +%s) - $(stat -c %Y "$DEST/$db/$dernier")) / 3600 ))
        n=$(archives "$db" | wc -l)
        if (( age > SEUIL_HEURES )); then ko "$db : dernière sauvegarde il y a $age h ($dernier ; seuil $SEUIL_HEURES h pour les heures $TIMER_TIME) — $n conservée(s)"; rc=1
        else ok "$db : dernière sauvegarde il y a $age h ($dernier, $(octets "$(stat -c %s "$DEST/$db/$dernier")")) — $n conservée(s), $(octets "$(du -sb "$DEST/$db" | cut -f1)") au total"; fi
    done
    [[ -r "$STATE_DIR/last-failure" ]] && attn "dernier échec : $(cut -f2- "$STATE_DIR/last-failure" | tr '\t' ' ')"
    if [[ -f "$SYSTEMD_DIR/odoo-backup.timer" ]]; then
        local etat_timer; etat_timer=$(systemctl is-active odoo-backup.timer 2>/dev/null) || true
        local heures_timer; heures_timer=$(sed -n 's/^OnCalendar=\*-\*-\* //p' "$SYSTEMD_DIR/odoo-backup.timer" | sort -u | tr '\n' ' ' | sed 's/ $//')
        echo "  Timer : ${etat_timer:-inconnu}, chaque jour à ${heures_timer// /, }"
        if [[ "$heures_timer" != "$TIMER_TIME" ]]; then
            attn "le timer installé (${heures_timer// /, }) ne correspond pas aux heures configurées (${TIMER_TIME// /, }) — relancer : $SCRIPT_PATH --install-timer"
        fi
    else
        attn "Timer : NON INSTALLÉ — sauvegarde automatique : odoo-backup.sh --install-timer"
    fi
    if [[ -n "$REMOTE" ]]; then echo "  Copie hors du serveur : $REMOTE"
    else attn "Copie hors du serveur : aucune (REMOTE) — une sauvegarde sur le même serveur ne protège pas d'une perte du serveur"; fi
    return "$rc"
}

# --- Restauration d'une archive .zip ou .tar.xz (format d'Odoo) ------------------------------------------------------
# Jamais d'écrasement : base existante ou filestore non vide = refus. Chemins dangereux (absolus, « .. ») = refus. Les
# objets sont créés sous le compte PostgreSQL d'Odoo (db_user : SET ROLE), comme lors d'une restauration par Odoo.
restaurer() {          # restaurer ARCHIVE [BASE_CIBLE] [DOSSIER_FILESTORE_CIBLE] [essai] → 0 si restaurée
    local archive="$1" cible="${2:-}" fs_cible="${3:-}" essai="${4:-}" tmp role proprio erreurs nb
    [[ -r "$archive" ]] || { ko "archive introuvable : $archive"; return 1; }
    case "$archive" in *.zip|*.tar.xz) ;; *) ko "format non reconnu (attendu : .zip ou .tar.xz) : $archive"; return 1 ;; esac
    if [[ -r "$archive.sha256" ]] && ! (cd "$(dirname "$archive")" && sha256sum -c --quiet "$(basename "$archive").sha256"); then
        ko "empreinte SHA-256 incorrecte : archive altérée ($archive)"; return 1
    fi
    tmp=$(mktemp -d "${TMPDIR:-/var/tmp}/odoo-restore-XXXXXX"); chmod 700 "$tmp"
    if [[ "$archive" == *.zip ]]; then
        python3 - "$archive" "$tmp" <<'PY' || { rm -rf "$tmp"; ko "archive ZIP refusée ou illisible : $archive"; return 1; }
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    for m in z.infolist():
        if m.filename.startswith("/") or ".." in m.filename.replace("\\", "/").split("/"):
            sys.exit(f"chemin dangereux dans l'archive : {m.filename}")
    if z.testzip() is not None:
        sys.exit("archive corrompue")
    z.extractall(sys.argv[2])
PY
    else
        if tar -tJf "$archive" 2>/dev/null | grep_q -E '(^/|(^|/)\.\.(/|$))'; then
            rm -rf "$tmp"; ko "archive tar.xz refusée : chemin dangereux (absolu ou « .. »)"; return 1
        fi
        tar -xJf "$archive" -C "$tmp" --no-same-owner || { rm -rf "$tmp"; ko "archive tar.xz illisible : $archive"; return 1; }
    fi
    [[ -r "$tmp/dump.sql" ]] || { rm -rf "$tmp"; ko "dump.sql absent de l'archive : ce n'est pas une sauvegarde d'Odoo"; return 1; }
    [[ -n "$cible" ]] || cible=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("db_name",""))' "$tmp/manifest.json" 2>/dev/null) || cible=""
    [[ "$cible" =~ ^[A-Za-z0-9_.-]+$ ]] || { rm -rf "$tmp"; ko "nom de base cible invalide ou absent (« $cible ») : préciser --db NOM"; return 1; }
    if [[ -r "$tmp/manifest.json" && -z "$essai" ]]; then
        echo "  Manifest : $(python3 - "$tmp/manifest.json" 2>/dev/null <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print("base d'origine {}, Odoo {}, PostgreSQL {}, {} module(s)".format(
    m.get("db_name"), m.get("version"), m.get("pg_version"), len(m.get("modules", {}))))
PY
)"
    fi
    if [[ -n "$(pg psql -Atc "SELECT 1 FROM pg_database WHERE datname = '$cible'" 2>/dev/null)" ]]; then
        rm -rf "$tmp"; ko "la base $cible existe déjà — jamais d'écrasement : choisir --db AUTRE_NOM (ou dropdb $cible d'abord)"; return 1
    fi
    if [[ -z "$fs_cible" ]]; then
        local parent; parent=$(dirname "$(filestore_de "$(bases | head -1)")" 2>/dev/null)
        [[ -n "$FILESTORE_DIR" ]] && parent="$FILESTORE_DIR"
        [[ -z "$parent" || "$parent" == "." ]] && { local dd; dd=$(valeur_odoo data_dir); [[ -n "$dd" ]] && parent="$dd/filestore"; }
        [[ -n "$parent" && "$parent" != "." ]] && fs_cible="$parent/$cible"
    fi
    if [[ -d "$tmp/filestore" && -n "$fs_cible" && -d "$fs_cible" && -n "$(ls -A "$fs_cible" 2>/dev/null)" ]]; then
        rm -rf "$tmp"; ko "le filestore $fs_cible existe déjà et n'est pas vide — jamais d'écrasement"; return 1
    fi
    role=$(valeur_odoo db_user); [[ "$role" == "False" ]] && role=""
    [[ -z "$essai" ]] && echo "  Restauration dans la base $cible${role:+ (propriétaire : $role)}…"
    if ! pg createdb ${role:+--owner "$role"} "$cible"; then rm -rf "$tmp"; ko "createdb $cible impossible"; return 1; fi
    chmod 755 "$tmp"; chmod 644 "$tmp/dump.sql"                    # lisible par le compte PostgreSQL
    pg psql -q -d "$cible" ${role:+-c "SET ROLE \"$role\""} -f "$tmp/dump.sql" > /dev/null 2> "$tmp/errors.txt" || true
    # Erreurs sans conséquence (comme lors d'une restauration par Odoo) : commentaire d'une extension créée par
    # le superutilisateur. Toute autre erreur est signalée.
    erreurs=$(grep -E 'ERROR:' "$tmp/errors.txt" | grep -vc 'must be owner of extension') || erreurs=0
    nb=$(pg psql -Atc "SELECT count(*) FROM ir_module_module WHERE state = 'installed'" -d "$cible" 2>/dev/null) || nb=""
    if [[ ! "$nb" =~ ^[0-9]+$ || "$nb" -eq 0 ]]; then
        pg dropdb --if-exists "$cible" >/dev/null 2>&1 || true
        ko "restauration de $cible en ÉCHEC : $(grep -m3 'ERROR:' "$tmp/errors.txt" | tr '\n' ' ')"; rm -rf "$tmp"; return 1
    fi
    local n_fs=0
    if [[ -d "$tmp/filestore" && -n "$fs_cible" ]]; then
        mkdir -p "$fs_cible" && cp -a "$tmp/filestore/." "$fs_cible/"
        proprio=$(stat -c '%U:%G' "$(dirname "$fs_cible")" 2>/dev/null) || proprio=""
        if [[ -n "$proprio" && "$EUID" -eq 0 ]]; then chown -R "$proprio" "$fs_cible" 2>/dev/null || true; fi
        n_fs=$(find "$fs_cible" -type f | wc -l)
    elif [[ -d "$tmp/filestore" ]]; then
        attn "dossier des filestores introuvable (FILESTORE_DIR, data_dir d'Odoo) : filestore NON restauré"
    fi
    rm -rf "$tmp"
    ok "base $cible restaurée — $nb module(s) installé(s), $n_fs fichier(s) de filestore${fs_cible:+ ($fs_cible)}$( (( erreurs > 0 )) && echo " ; $erreurs erreur(s) SQL à examiner")"
    if [[ -z "$essai" ]]; then
        echo "  Copie d'une base de production : avant de démarrer Odoo dessus, la NEUTRALISER (courriels sortants, tâches"
        echo "  planifiées, connecteurs) : odoo-bin neutralize -c <configuration> -d $cible (Odoo 16 et suivants)."
    fi
}

# --- --test-restore : la dernière sauvegarde est-elle RÉELLEMENT restaurable ? --------------------------------------
test_restauration() {
    local db dernier essai rc=0 fs_essai
    for db in $(bases); do
        dernier=$(archives "$db" | head -1 | cut -f2) || dernier=""
        if [[ -z "$dernier" ]]; then ko "$db : aucune sauvegarde à restaurer"; rc=1; continue; fi
        essai="${db}_restore_test_$$"; fs_essai=$(mktemp -d "${TMPDIR:-/var/tmp}/odoo-restore-test-XXXXXX")
        echo "Essai de restauration de $dernier dans la base temporaire $essai…"
        restaurer "$DEST/$db/$dernier" "$essai" "$fs_essai/$essai" essai || rc=1
        pg dropdb --if-exists "$essai" >/dev/null 2>&1 || attn "base temporaire $essai à supprimer à la main (dropdb $essai)"
        rm -rf "$fs_essai"
    done
    return "$rc"
}

# --- Timer systemd ------------------------------------------------------------------------------------------------------
installer_timer() {
    [[ "$EUID" -eq 0 ]] || { echo "ERREUR: root requis pour --install-timer." >&2; exit 1; }
    # Chemin de configuration dans le timer SEULEMENT s'il a été demandé (--config) : sinon le programme retrouve seul son
    # fichier (/etc/default), et déplacer ce fichier ne casse plus le timer.
    local CONFIG_ARG="" LIGNES_CALENDRIER="" h
    if (( CONFIG_EXPLICITE )); then CONFIG_ARG=" --config $CONFIG_FILE"; fi
    for h in "${HEURES[@]}"; do LIGNES_CALENDRIER+="${LIGNES_CALENDRIER:+$'\n'}OnCalendar=*-*-* $h"; done   # une ligne par heure
    cat > "$SYSTEMD_DIR/odoo-backup.service" <<EOF
[Unit]
Description=Sauvegarde de la base et du filestore d'Odoo (odoo-backup.sh)
After=postgresql.service

[Service]
Type=oneshot
ExecStart=$SCRIPT_PATH$CONFIG_ARG
Nice=10
IOSchedulingClass=idle
EOF
    cat > "$SYSTEMD_DIR/odoo-backup.timer" <<EOF
[Unit]
Description=Sauvegarde quotidienne d'Odoo

[Timer]
$LIGNES_CALENDRIER
Persistent=true
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
EOF
    # Le fichier de configuration a déjà été renommé (migration, plus haut) : le timer n'est arrêté qu'ENSUITE. « restart » =
    # arrêt puis démarrage, pour que la nouvelle définition (service, heure) s'applique à un timer déjà actif.
    trace systemctl daemon-reload; systemctl daemon-reload
    trace systemctl enable odoo-backup.timer; systemctl enable odoo-backup.timer
    trace systemctl restart odoo-backup.timer; systemctl restart odoo-backup.timer
    echo "Timer installé (arrêté puis relancé) : ${#HEURES[@]} sauvegarde(s) par jour, à ${TIMER_TIME// /, } (rattrapées au démarrage si le serveur était éteint). État : odoo-backup.sh --status"
}
desinstaller_timer() {
    [[ "$EUID" -eq 0 ]] || { echo "ERREUR: root requis pour --uninstall-timer." >&2; exit 1; }
    systemctl disable --now odoo-backup.timer 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/odoo-backup.timer" "$SYSTEMD_DIR/odoo-backup.service"
    systemctl daemon-reload 2>/dev/null || true
    echo "Timer retiré (les sauvegardes existantes sont conservées dans $DEST)."
}

# --- Principal ----------------------------------------------------------------------------------------------------------
if [[ "$DO_STATUS" == "1" ]]; then afficher_statut; exit $?; fi
if [[ "$DO_INSTALL_TIMER" == "1" ]]; then afficher_configuration; installer_timer; exit 0; fi
if [[ "$DO_UNINSTALL_TIMER" == "1" ]]; then desinstaller_timer; exit 0; fi
if [[ "$DO_TEST_RESTORE" == "1" ]]; then afficher_configuration; test_restauration; exit $?; fi
if [[ -n "$RESTORE_FILE" ]]; then afficher_configuration; restaurer "$RESTORE_FILE" "$ONLY_DB"; exit $?; fi
if [[ "$DO_DRY_RUN" != "1" && "$EUID" -ne 0 && -n "$PG_USER" && "$(id -un)" != "$PG_USER" ]]; then
    echo "ERREUR: root requis (pg_dump sous le compte $PG_USER)." >&2
    exit 1
fi
echo "$(date '+%Y-%m-%d %H:%M:%S %Z') — destination : $DEST"
afficher_configuration
mapfile -t LISTE < <(bases)
if (( ${#LISTE[@]} == 0 )); then
    ko "aucune base trouvée (DATABASES, db_name d'Odoo ou PostgreSQL injoignable)"
    noter failure "aucune base trouvée"
    exit 1
fi
echecs=0
for db in "${LISTE[@]}"; do
    sauvegarder "$db" || { echecs=$((echecs + 1)); noter failure "sauvegarde de $db en échec"; }
done
(( echecs == 0 )) || exit 1
