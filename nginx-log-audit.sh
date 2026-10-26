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
# nginx-log-audit.sh - quick audit of nginx blocks (bad-bot, method, traversal, 429, 5xx, upstream errors,
# catch-all) + statistiques de type goaccess + verification cible d'une IP.
#
#
# Usage : nginx-log-audit.sh [dev|lab|prod] [-v|--verbose] [--ip ADRESSE] [--init] [--init-all] [--stats] [--last HEURES]
#                            [--details] [--fail2ban] [--ban IP [--yes] [--reason TEXT]] [--unban IP] [--ban-history] [--investigate IP] [--evidence IP]
#                            [--unban-check] [--unban-low-score] [--ban-threshold N] [--page-burst N] [--parallel-threshold N] [--no-prompt] [--version]
#                            [--changelog]
#   - [dev|lab|prod]  : optional, auto-detected from the files present in /var/log/nginx/.
#   - -v/--verbose    : affiche aussi la commande shell exacte utilisee pour chaque verification.
#   - --ip ADDRESS    : dedicated section that searches this precise IP in the logs (complete file, not the delta).
#   - --init          : reaffiche TOUT l'historique du fichier (ignore la position memorisee), puis remet la
#                        up-to-date position - the following calls become incremental again from now on.
#   - --init-all      : comme --init, mais fusionne D'ABORD tous les fichiers de log connus pour l'environnement
#                        chosen - active + rotations (.1, .2...) + compressed (.gz), decompressed on the fly -
#                        avant d'analyser l'ensemble comme un seul historique complet. Combinable avec --last
#                        to restrict this complete history to a recent time window (useful for
#                        confirmer si quelque chose de vu il y a des semaines se reproduit encore aujourd'hui).
#                        May take several seconds depending on the volume of compressed files present.
#   - --last HOURS    : restricts ALL the sections (including --stats) to the entries of the last HOURS hours,
#                        peu importe l'historique du fichier ou la position memorisee. Ne touche jamais la
#                        normal incremental position - a call without --last restarts exactly where it was.
#   - --stats         : ajoute des statistiques generales sur le fichier complet (type goaccess), avec un accent
#                        on requests that would have been blocked (403/404/405/429/444) - useful to restart
#                        d'une vue d'ensemble plutot que ligne par ligne. Chaque ligne affiche aussi son % du total.
#   - --details       : with --stats, adds under each blocked path the responsible IPs (top 3).
#   - --fail2ban      : lists the IPs currently banned by fail2ban (all jails), with their reverse DNS - useful
#                        pour reperer un faux positif (ex. un vrai moteur de recherche banni par erreur). Affiche
#                        aussi les IP de la liste communautaire CrowdSec qui ont reellement ete bloquees (compteurs
#                        de sync-crowdsec-blocklist.sh --blocked ; 15 premieres, toutes avec --details ; root requis).
#   - --ban IP        : manual ban via firewall (ufw if present, otherwise iptables - same logic as
#                        nginx-hardening.sh). Requires root. Displays the number of known occurrences of this IP
#                        before asking for confirmation (skipped with --yes, useful in a script). Deliberately
#                        independent of the existing fail2ban jails: none of them watches the catch-all sensor,
#                        which is typically the justification for a manual ban by volume. Idempotent
#                        (never duplicates a rule already present).
#   - --unban IP      : removes a ban set by --ban (ufw or iptables). Asks for confirmation like
#                        --ban (skipped with --yes). No effect on a fail2ban ban - use
#                        "fail2ban-client set <jail> unbanip IP" for those.
#   - --yes           : saute la confirmation interactive de --ban ET --unban.
#   - --reason TEXT   : justification for --ban / --unban, recorded with the date and time in bans.tsv (2.40). Without --reason :
#                        asked at the keyboard (editable proposal: the evidence), automatic with --yes.
#   - --ban-history   : log of manual bans and lifts (date, time, IP, justification, origin), read-only.
#   - --investigate IP : enquete complete sur une IP dans TOUT l'historique disponible (journal actif, rotations et
#                        .gz) : preuves une par une, commandes equivalentes, score, puis proposition de bannissement
#                        avec confirmation. La section [10] du rapport normal fait la meme enquete, automatiquement,
#                        sur les IP les plus suspectes de la fenetre analysee (5 au maximum).
#                        Indices (1 point chacun) : rafale de pages distinctes en 10 s (assets exclus) ; outil de
#                        script declare (python-httpx, curl...) ; double identite (outil de script ET navigateur, ou
#                        plusieurs organisations de robots) ; recherche de fichiers sensibles (3+) ; taux d'erreurs
#                        eleve ; DNS inverse d'un hebergeur (AWS, OVH, Hetzner...) ; faux moteur de recherche (se dit
#                        Googlebot/Bingbot mais la double verification DNS echoue). Jamais proposes : l'equipe, les
#                        moteurs de recherche verifies, les IP deja bannies ou deja dans la liste CrowdSec, et les IP
#                        protegees : boucle locale, adresses du serveur (dont son IP publique, memorisee par le
#                        report), private networks (--ban refuses them), IPs of nginx "allow" rules (--ban warns).
#   - --unban-check   : re-evaluates each MANUAL ban in place (iptables "-s IP -j DROP", ufw "deny from";
#                        pas les bannissements temporaires de fail2ban) avec la logique ACTUELLE, sur tout l'historique
#                        (journal du site ET capteur catch-all, rotations et .gz compris) : URL demandees, indices,
#                        date of the ban if known, then verdict - lifting recommended (no sign of hostility, IP
#                        protegee, moteur verifie), bannissement justifie, ou aucune trace (decision manuelle). Propose
#                        la levee avec confirmation (terminal + root), sinon affiche la commande. Root requis.
#   - --export-bans [FICHIER] : exporte les bannissements MANUELS en place (IP, date du bannissement, serveur
#                        d'origine), vers FICHIER ou la sortie standard. Root requis.
#   - --import-bans FICHIER|- : bannit sur CE serveur les IP d'un export (- : entree standard). Apercu classe avant
#                        toute action (a bannir, deja bannies, protegees ICI, invalides), puis une confirmation (--yes
#                        pour un usage scripte). Les IP protegees sur ce serveur ne sont jamais importees. Root requis.
#                        Entre deux serveurs : ssh AUTRE nginx-log-audit.sh --export-bans | nginx-log-audit.sh --import-bans -
#   - --ban-threshold N : nombre d'indices a partir duquel le bannissement est propose (defaut : 3).
#                        ET au moins un signe d'HOSTILITE (rafale, fichiers sensibles, erreurs en masse, faux moteur) : les signes
#                        d'automatisation seuls (outil de script, double identite, hebergeur) decrivent un robot, souvent
#                        harmless - never a sufficient reason to ban. Each investigation displays the requested URLs.
#   - --page-burst N  : pages distinctes en 10 s a partir desquelles la rafale compte comme indice (defaut : 8).
#   - --parallel-threshold N : requetes dynamiques d'une meme IP dans la meme seconde a partir desquelles la section [11] les signale (defaut : 5).
#   - --no-prompt     : n'affiche que les recommandations, sans jamais poser de question (automatique hors terminal,
#                        ex. cron). La confirmation exige aussi root.
#   - --ua-rotation-threshold N : threshold of section [9] - minimum number of DIFFERENT bot families
#                        (Google, OpenAI, Meta...) declared by the same IP to report it. Default: 2. Browser
#                        User-Agents are ignored (a company or university NAT legitimately shows many of them);
#                        legitimately many); only an IP claiming several bot organizations at
#                        once is reported - no organization operates the bots of another.
#   - --unban-low-score : liste les IP BANNIES (fail2ban et pare-feu manuel) dont le score est SOUS le seuil de
#                        proposal (BAN_THRESHOLD, 3 by default), score recalculated like --investigate; asks for
#                        each one whether it can be unbanned (--yes: without question; without terminal: list only).
#   - --version       : affiche la version et quitte.
#   - --changelog     : affiche CHANGELOG.md (numeros de version en couleur si terminal).
#
# Sections du rapport standard :
#   [1] 403 (bad bot)              - frequency per User-Agent. Almost always expected noise (bot_blocker.conf).
#   [2] 405 (refused method)       - should be empty in normal use.
#   [3] 444 in the NAMED LOG (not the catch-all) - ambiguous cases: a real domain matched, but still an internal 400.
#   [4] 404 from the traversal rule (%2e%2e, ../, ..\) - isolates these 404s from Odoo's normal 404s.
#   [5] 429 (rate limiting) per IP - a trusted IP here deserves a check against $is_trusted_ip.
#   [6] 5xx (server errors) - a real 500/502/503/504 on the Odoo side, not an nginx block. Never ignore.
#   [7] Upstream errors (error.log) - "connect() failed" = Odoo (or its gevent worker) unreachable.
#   [8] default_server sensor (catch-all) - volume + top IPs. Expected scan noise in large volume.
#
# Important reminder: rules 4 to 11 of securite-commune.conf (hidden files, extensions, frameworks, IoT,
# xmlrpc, CMS/diagnostics, JSON secrets, graphql/api) use "access_log off;" - their blocks never appear
# in the access log, by design. This script (including --stats) therefore cannot see anything from THOSE rules.
# ========================================================================================================================

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

# Safety net: if "set -e" interrupts the script on a command that fails somewhere (for example a
# badly protected "sort | head" pipeline that we would have missed), this trap announces it clearly BEFORE bash exits
# silently - rather than letting the report stop dead with no visible explanation on screen.
# shellcheck disable=SC2154  # "ec" is set INSIDE the trap text (ec=$?), at execution: shellcheck
#                              ne peut pas le voir, le texte etant entre apostrophes (faux positif).
trap 'ec=$?; echo "" >&2; echo "*** ARRÊT INATTENDU DU SCRIPT (code $ec) À LA LIGNE $LINENO ***" >&2; echo "*** Commande fautive : $BASH_COMMAND" >&2; echo "*** Si le rapport ci-dessus semble incomplet (ex. sections Top 10 absentes), c'\''est probablement la cause." >&2' ERR

readonly SCRIPT_VERSION="2.45.20261026.114649"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
# Chemin de ce programme (relances --investigate, --ban, --unban) : defini ICI, avant le bloc --ban qui l'utilise.
SELF_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
# Display language (en or fr): --lang, NGINX_LOG_AUDIT_LANG, LANGUAGE of the configuration file, LC_ALL / LANG - apps/_i18n.sh translates the output (nothing changes in French).
if [[ -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_i18n.sh"
    i18n_relancer nginx-log-audit NGINX_LOG_AUDIT_LANG "$0" "$@"
fi
# Changelog dans le sous-repertoire doc/ ; repli sur l'ancien emplacement (a cote du programme) tant que
# l'installation n'a pas ete reorganisee.
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
readonly CHANGELOG_FILE

# Section of this program in CHANGELOG.md (from its "## <file name>" heading to the next "## " heading).
changelog_section() {
    awk -v cle="${BASH_SOURCE[0]##*/}" '/^## /{dans=($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE"
}

# Forces a UTF-8 locale if none is already defined (cron and some minimal services often run
# without LANG/LC_ALL, which can degrade the display of accented characters) - never replaces a locale
# already defined by the user/system, only the case where it is absent.
: "${LC_ALL:=C.UTF-8}"
export LC_ALL

VERBOSE=0
TARGET_IP=""
ENV=""
DO_INIT=0
DO_STATS=0
DO_DETAILS=0
DO_FAIL2BAN=0
DO_INIT_ALL=0
LAST_HOURS=""
BAN_IP=""
UNBAN_IP=""
BAN_REASON=""
DO_BAN_HISTORY=0
DO_UNBAN_CHECK=0
DO_UNBAN_LOW_SCORE=0
# Set by investigate_and_propose: ENQUETE_INCOHERENTE=1 when the address changed during the investigation (no verdict then);
# SIGNE_FORT=1 when a strong sign of hostility was found (sensitive files, errors, fake search engine, catch-all).
ENQUETE_INCOHERENTE=0
SIGNE_FORT=0
REVOIR_IPS=()                  # --unban-check: addresses whose ban must be checked by hand (section 5 of the review)
EXPORT_BANS=""
IMPORT_BANS=""
INV_MODE=""
CATCHALL_MERGED=""
ASSUME_YES=0
INVESTIGATE_IP=""
EVIDENCE_IP=""
APP_FORCE=""
NO_PROMPT=0
BAN_THRESHOLD=3
PAGE_BURST=8
PARALLEL_THRESHOLD=5
UA_ROTATION_THRESHOLD=2

# --report-err: error report to copy-paste at the end of execution (program, version, server, failures...) - apps/_rapport.sh
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$SCRIPT_DIR/apps/_rapport.sh"
    rapport_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi
# First line of EVERY execution, even with --help: the name and version of the program (--version displays it itself).
# --export-bans writes a LIST of addresses meant to be redirected into a file then re-imported: the version goes to the error output.
case " $* " in *" --version "*) ;; *" --export-bans "*) echo "nginx-log-audit.sh v$SCRIPT_VERSION" >&2 ;; *) echo "nginx-log-audit.sh v$SCRIPT_VERSION" ;; esac
# Configuration (/etc/default/nginx-log-audit.conf, then ~/.nginx-log-audit.conf; -c/--config: this file ONLY): default values of the options, the command line wins.
# Keys: APP, BAN_THRESHOLD, LANGUAGE, NO_PROMPT, PAGE_BURST, PARALLEL_THRESHOLD, UA_ROTATION_THRESHOLD, VERBOSE.
if declare -F config_lire >/dev/null; then
    config_lire nginx-log-audit "$@"
    config_defaut APP_FORCE APP --app texte
    config_defaut BAN_THRESHOLD BAN_THRESHOLD --ban-threshold nombre
    config_defaut NO_PROMPT NO_PROMPT --no-prompt booleen
    config_defaut PAGE_BURST PAGE_BURST --page-burst nombre
    config_defaut PARALLEL_THRESHOLD PARALLEL_THRESHOLD --parallel-threshold nombre
    config_defaut UA_ROTATION_THRESHOLD UA_ROTATION_THRESHOLD --ua-rotation-threshold nombre
    config_defaut VERBOSE VERBOSE --verbose booleen
    case " $* " in *" --version "*|*" --help "*|*" -h "*|*" --changelog "*) ;; *" --export-bans "*) config_afficher >&2 ;; *) config_afficher ;; esac
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        dev|lab|prod) ENV="$1"; shift ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --ip) TARGET_IP="${2:-}"; shift 2 ;;
        --init) DO_INIT=1; shift ;;
        --stats) DO_STATS=1; shift ;;
        --last) LAST_HOURS="${2:-}"; shift 2 ;;
        --details) DO_DETAILS=1; shift ;;
        --fail2ban) DO_FAIL2BAN=1; shift ;;
        --init-all) DO_INIT_ALL=1; shift ;;
        --ban) BAN_IP="${2:-}"; shift 2 ;;
        --unban) UNBAN_IP="${2:-}"; shift 2 ;;
        --reason) BAN_REASON="${2:-}"; shift 2 ;;
        --reason=*) BAN_REASON="${1#--reason=}"; shift ;;
        --ban-history) DO_BAN_HISTORY=1; shift ;;
        --yes) ASSUME_YES=1; shift ;;
        --ua-rotation-threshold) UA_ROTATION_THRESHOLD="${2:-}"; shift 2 ;;
        --investigate) INVESTIGATE_IP="${2:-}"; shift 2 ;;
        --evidence) EVIDENCE_IP="${2:-}"; shift 2 ;;
        --unban-check) DO_UNBAN_CHECK=1; shift ;;
        --unban-low-score) DO_UNBAN_LOW_SCORE=1; shift ;;
        --export-bans) if [[ -n "${2:-}" && "${2:0:2}" != "--" ]]; then EXPORT_BANS="$2"; shift 2; else EXPORT_BANS="-"; shift; fi ;;
        --import-bans) IMPORT_BANS="${2:-}"; shift 2 ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*|--lang=*) shift ;;
        --lang) shift 2 ;;
        --app) APP_FORCE="${2:-}"; shift 2 ;;
        --app=*) APP_FORCE="${1#--app=}"; shift ;;
        --no-prompt) NO_PROMPT=1; shift ;;
        --ban-threshold) BAN_THRESHOLD="${2:-}"; shift 2 ;;
        --page-burst) PAGE_BURST="${2:-}"; shift 2 ;;
        --parallel-threshold) PARALLEL_THRESHOLD="${2:-}"; shift 2 ;;
        --version) echo "nginx-log-audit.sh version $SCRIPT_VERSION"; exit 0 ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then
                echo "Changelog introuvable : $CHANGELOG_FILE" >&2
                exit 1
            fi
            if [[ -t 1 ]]; then
                # Version numbers (X.Y.AAAAMMDD.HHMMSS) in bold cyan - standard ANSI colors, adapt to
                # theme clair/sombre du terminal plutot que d'imposer une couleur fixe potentiellement illisible.
                changelog_section | sed -E $'s/([0-9]+\\.[0-9]+\\.[0-9]{8}\\.[0-9]{6})/\\x1b[1;36m\\1\\x1b[0m/' 2>/dev/null || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            else
                changelog_section 2>/dev/null || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            fi
            # "|| true": without it, the script's ERR trap took the SIGPIPE of a reader closed earlier (e.g.

            # "--changelog | head") for a failure and displayed "UNEXPECTED STOP (code 141)".
            exit 0
            ;;
        -h|--help)
            cat <<'AIDE'
Usage : nginx-log-audit.sh [dev|lab|prod] [OPTION]...
Rapport des journaux nginx : robots, refus, attaques, enquêtes sur les IP suspectes, bannissements.

Arguments :
  dev | lab | prod             environnement (journal du site) ; défaut : celui du profil détecté

Options (par ordre alphabétique) :
  --anonymize                  anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE
  --app NAME                   application derrière nginx (profil apps/NAME.conf : odoo, bbb…) ; détectée par défaut
  --ban IP                     bannir IP au pare-feu (preuves affichées, justification et confirmation demandées)
  --ban-history                journal des bannissements et levées manuels : date, heure, justification, origine (lecture seule)
  --ban-threshold N            nombre d'indices à partir duquel le bannissement est proposé (défaut : 3)
  --changelog                  affiche le journal des modifications
  -c, --config FILE            fichier de configuration à lire SEUL (sinon : /etc/default/nginx-log-audit.conf, puis ~/.nginx-log-audit.conf ;
                               clés : APP, BAN_THRESHOLD, LANGUAGE, NO_PROMPT, PAGE_BURST, PARALLEL_THRESHOLD, UA_ROTATION_THRESHOLD, VERBOSE)
  --details                    avec --stats : détail de chaque indicateur
  --evidence IP                preuves pour ou contre le bannissement d'une IP et verdict, sans rien demander ni bannir (lecture seule)
  --export-bans [FILE]         exporter les bannissements manuels (sortie standard par défaut)
  --fail2ban                   état des jails et historique des bannissements de fail2ban
  -h, --help                   affiche cette aide et quitte
  --import-bans FILE|-         importer des bannissements (- : entrée standard) ; aperçu, puis confirmation
  --init                       analyser tout le fichier actif (et non seulement le nouveau depuis le dernier passage)
  --init-all                   analyser tout l'historique, rotations comprises
  --investigate IP             enquête complète sur une IP (tout l'historique), avec le propriétaire de son bloc d'adresses (RDAP)
  --ip ADDRESS                 limiter le rapport à une adresse
  --lang LANG                  langue d'affichage : en ou fr (défaut : selon LC_ALL / LC_MESSAGES / LANG)
  --last HOURS                 limiter toutes les sections aux HOURS dernières heures
  --no-prompt                  ne pas proposer de bannir en fin de rapport
  --page-burst N               pages distinctes en 10 s à partir desquelles l'indice « rafale » est retenu
  --parallel-threshold N        requêtes dynamiques d'une même IP dans la même seconde à partir desquelles la section [11] les signale (défaut : 5)
  --reason TEXT                avec --ban ou --unban : justification enregistrée dans le journal des bannissements
  --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
                               échecs, avertissements) ; désactive couleurs et questions interactives
  --stats                      statistiques du trafic (codes, IP, User-Agents, appareils des visiteurs)
  --ua-rotation-threshold N    identités de robots différentes pour l'indice « double identité »
  --unban IP                   lever un bannissement manuel (justification demandée)
  --unban-check                réévaluer chaque bannissement manuel (levée proposée si injustifié)
  --unban-low-score            lister les IP bannies dont le score est sous le seuil et proposer de les débannir
  -v, --verbose                affiche chaque commande lancée
  --version                    affiche la version et quitte
  --yes                        avec --ban ou --unban : sans question (justification : --reason, sinon automatique)
AIDE
            exit 0
            ;;
        --report-err) shift ;;                 # handled earlier (apps/_rapport.sh); accepted here with --help, --version...
        *) echo "Argument inconnu: $1" >&2; exit 1 ;;
    esac
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
# Lecture seule (--stats, --investigate, --evidence, --export-bans, --ban-history) : sans verrou ; sinon (rapport, positions, --ban, --unban,
# --unban-check, --import-bans): wait for NGINX_TOOLS_LOCK_WAIT seconds at most (120 by default).
if [[ "$DO_STATS" != "1" && -z "$INVESTIGATE_IP" && -z "$EVIDENCE_IP" && -z "$EXPORT_BANS" && "$DO_BAN_HISTORY" != "1" ]]; then
    prendre_verrou "${NGINX_TOOLS_LOCK_WAIT:-120}" nginx-log-audit
fi

if [[ -n "$LAST_HOURS" ]] && ! [[ "$LAST_HOURS" =~ ^[0-9]+$ ]]; then
    echo "ERREUR: --last attend un nombre d'heures entier positif (reçu: '$LAST_HOURS')" >&2
    exit 1
fi

for pair in "BAN_THRESHOLD:--ban-threshold" "PAGE_BURST:--page-burst" "PARALLEL_THRESHOLD:--parallel-threshold"; do
    var="${pair%%:*}"; opt="${pair##*:}"
    if ! [[ "${!var}" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERREUR: $opt attend un entier >= 1 (reçu: '${!var}')" >&2
        exit 1
    fi
done
if [[ -n "$INVESTIGATE_IP" ]] && ! [[ "$INVESTIGATE_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$INVESTIGATE_IP" =~ ^[0-9a-fA-F:]+:[0-9a-fA-F:]*$ ]]; then
    echo "ERREUR: --investigate attend une adresse IP (reçu: '$INVESTIGATE_IP')" >&2
    exit 1
fi

if ! [[ "$UA_ROTATION_THRESHOLD" =~ ^[0-9]+$ ]] || [[ "$UA_ROTATION_THRESHOLD" -lt 2 ]]; then
    echo "ERREUR: --ua-rotation-threshold attend un entier >= 2 (reçu: '$UA_ROTATION_THRESHOLD')" >&2
    exit 1
fi

# --- Couleur conditionnelle : jamais si la sortie n'est pas un terminal (fichier, mail, pipe) -------------------
if [[ -t 1 || -n "${REPORT_ERR_COULEUR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_RESET=$'\x1b[0m'; C_BOLD=$'\x1b[1m'
    C_MAL=$'\x1b[1;35m'     # magenta : elements malveillants (URL sensibles, codes de blocage ou d'erreur, IP a bannir)
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_RESET=""; C_MAL=""; C_BOLD=""
fi

log() { if [[ "$VERBOSE" == "1" ]]; then echo ">>> $*" >&2; fi; }

# run : execute une commande systeme en l'annoncant d'abord si -v/--verbose. Affichage via le descripteur 3 (copie
# du stderr d'origine) : ces appels masquent souvent leur propre stderr ("2>/dev/null"), ce qui ferait disparaitre
# l'annonce avec. Fonctionne aussi a l'interieur des $(...).
exec 3>&2
run() {
    if [[ "$VERBOSE" == "1" ]]; then echo ">>> $*" >&3; fi
    "$@"
}

# progress: what the program does, ONE LINE PER STEP with the elapsed time, on the error output - in a terminal or
# with --verbose; nothing in a pipe nor a scheduled task (reports stay clean). Log reads (one per
# file), DNS and whois lookups (one per address): we see that it moves forward and where, instead of a program that seems frozen.
PROGRES_ACTIF=0
if [[ "$VERBOSE" == "1" || -t 2 ]]; then PROGRES_ACTIF=1; fi
progres() {
    if (( PROGRES_ACTIF )); then printf '[%4d s] %s\n' "$SECONDS" "$*" >&3; fi
    return 0
}
progres_detail() {      # comme progres, mais SEULEMENT avec --details (lecture de chaque fichier de rotation)
    if [[ "$DO_DETAILS" == "1" ]]; then progres "$@"; fi
    return 0
}
taille_lisible() {      # taille_lisible FILE: "4 MB" (or "812 KB"), "?" if unreadable
    local o
    o=$(stat -c %s -- "$1" 2>/dev/null) || { echo "?"; return 0; }
    if (( o >= 1048576 )); then echo "$(( o / 1048576 )) Mo"; else echo "$(( (o + 1023) / 1024 )) Ko"; fi
}

# highlight: colors in magenta, in the log excerpts, what is MALICIOUS - sensitive file paths
# (.env, .git/, wp-login...) and blocking or error HTTP codes (403, 404, 429, 444, 5xx) - so that they stand out.
# Sans effet quand la sortie est redirigee (C_MAL vide). Lit l'entree standard.
surligner() {
    if [[ -z "${C_MAL:-}" ]]; then cat; return 0; fi
    # (sed: no "\|" inside a class; ERE alternation; & = matched text)
    sed -E -u "s#(/?\\.env[^ \"]*|/?\\.git/[^ \"]*|/wp-[^ \"]*|/?wp-login[^ \"]*|/?xmlrpc\\.php|/?phpmyadmin[^ \"]*|/?\\.aws/[^ \"]*|/?\\.ssh/[^ \"]*|/config\\.(php|json|yml)|/server-status)#${C_MAL}&${C_RESET}#g; s#(\" |^| |[0-9]x)(4(03|04|29|44)|5[0-9][0-9])([ ,]|$)#\\1${C_MAL}\\2${C_RESET}\\4#g"
}

# demander_oui QUESTION: returns 0 if the answer is yes (o, O, oui), 1 otherwise - "no" by default, Enter alone,
# Ctrl-D ou Ctrl-C. Dans un terminal : lecture par readline (read -e), qui comprend la touche d'effacement que le
# terminal sends ^H or ^? (many SSH clients send ^H, which the simple read displayed as "^H" without erasing),
# les fleches, Debut/Fin ; les touches non gerees (Page precedente...) sont ignorees au lieu d'inserer des caracteres.
# The reading takes place in a SUB-SHELL: Ctrl-C stops it (default signal), the main script - whose trap
# ":" does nothing - continues; DEMANDER_INTERROMPU is then 1. (An INT trap on a "read" in the shell
# principal ne suffit pas : bash 5.2 execute le piege puis REPREND l'attente.) Hors terminal (reponse par un tube,
# e.g. "printf 'o\n' | ... --ban IP"): simple read.
DEMANDER_INTERROMPU=0
demander_oui() {
    local question="$1" reply="" tmp rc=0
    DEMANDER_INTERROMPU=0
    if [[ -t 0 ]]; then
        tmp=$(mktemp)
        trap ':' INT
        ( trap - INT; read -e -r -p "$question" r && printf '%s' "$r" > "$tmp" ) || rc=$?
        trap - INT; ctrl_c_installer        # remet la confirmation de Ctrl+C
        reply=$(cat "$tmp" 2>/dev/null) || reply=""
        rm -f "$tmp"
        if (( rc == 130 )); then DEMANDER_INTERROMPU=1; echo; fi
    else
        read -r -p "$question" reply || reply=""
    fi
    case "$reply" in o|O|oui|Oui|OUI) return 0 ;; *) return 1 ;; esac
}

# --- Firewall: ufw only if it is ACTIVE (installed but inactive, "ufw deny" records the rule without
# l'appliquer : le bannissement serait sans effet) ; sauvegarde persistante apres chaque changement ----------------
ufw_active() {
    command -v ufw >/dev/null 2>&1 && run ufw status 2>/dev/null | grep_q '^Status: active'
}

# Rend les regles iptables permanentes (survie au redemarrage). Avec ufw actif : rien a faire, ufw enregistre
# itself its rules. Otherwise, netfilter-persistent if it is installed - then removal from the backup of everything
# belonging to fail2ban (chains and ipsets "f2b-*"): fail2ban recreates them at its startup, and restoring them in addition
# produirait des doublons ou des erreurs au boot (meme traitement que sync-crowdsec-blocklist.sh).
persist_firewall() {
    if ufw_active; then
        echo "${C_GREEN}Règle permanente : ufw enregistre lui-même ses règles (survit au redémarrage).${C_RESET}"
        return 0
    fi
    if command -v netfilter-persistent >/dev/null 2>&1; then
        if run netfilter-persistent save >/dev/null 2>&1; then
            local f
            for f in /etc/iptables/rules.v4 /etc/iptables/rules.v6 /etc/iptables/ipsets; do
                if [[ -f "$f" ]] && grep -q 'f2b-' "$f" 2>/dev/null; then
                    run sed -i '/f2b-/d' "$f"
                fi
            done
            echo "${C_GREEN}Règles sauvegardées (netfilter-persistent save, chaînes fail2ban exclues) : survivront au redémarrage.${C_RESET}"
        else
            echo "${C_YELLOW}Échec de netfilter-persistent save — règle en mémoire seulement jusqu'au prochain redémarrage.${C_RESET}"
        fi
        return 0
    fi
    if ! command -v ufw >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1 && [[ "$(id -u)" == "0" ]]; then
        # Neither ufw nor a backup tool: the firewall is iptables alone, whose rules disappear at reboot - we install what keeps them (iptables-persistent removes nothing
        # without ufw; with ufw installed, apt would remove it, hence the exclusion above).
        echo "${C_YELLOW}Aucun outil de sauvegarde des règles : installation de iptables-persistent et ipset-persistent…${C_RESET}"
        if DEBIAN_FRONTEND=noninteractive run apt-get install -y iptables-persistent ipset-persistent >/dev/null 2>&1 && command -v netfilter-persistent >/dev/null 2>&1; then
            persist_firewall
            return 0
        fi
        echo "${C_RED}Installation de iptables-persistent en échec — lancer « apt-get install iptables-persistent ipset-persistent » et lire l'erreur.${C_RESET}"
    fi
    echo "${C_YELLOW}Règle en mémoire seulement : aucun outil de sauvegarde installé (netfilter-persistent absent).${C_RESET}"
    if command -v ufw >/dev/null 2>&1; then
        echo "${C_YELLOW}ufw est installé (inactif) : NE PAS installer iptables-persistent, apt supprimerait ufw.${C_RESET}"
    else
        echo "${C_YELLOW}Pour la rendre permanente : apt install iptables-persistent ipset-persistent, puis relancer ce${C_RESET}"
        echo "${C_YELLOW}bannissement (ou lancer sync-crowdsec-blocklist.sh, qui installe et configure ces paquets).${C_RESET}"
    fi
}

# --- IP protegees : jamais proposees au bannissement (sections [9]/[10], --investigate), --ban refuse ou avertit ---
# Address lists: WHITE LIST (team) and PLACES (/etc/default/nginx-tools-*.conf, outside the archives) - common reader apps/_listes.sh.
# No address is written in this program: without a white list, no address is protected by this list (the protections of the server
# itself, of the private network and of nginx "allow" rules remain active).
# shellcheck source=/dev/null
[[ -r "$SCRIPT_DIR/apps/_listes.sh" ]] && . "$SCRIPT_DIR/apps/_listes.sh"
TEAM_IPS=$(listes_blanche | listes_valides | cut -d "$LISTES_SEP" -f1 | tr '\n' ' ') || TEAM_IPS=""
LIEUX_LIGNES=$(listes_lieux | listes_valides) || LIEUX_LIGNES=""
listes_resume >&2
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
[[ -z "${NGINX_LOG_AUDIT_STATE_DIR:-}" ]] && migrer_chemin "$HOME/.local/state/chk-nginx-logs" "$HOME/.local/state/nginx-log-audit"
# Noms de fichiers d'etat en anglais (2.2) : bannissements.tsv -> bans.tsv, ip-publique -> public-ip.
ETAT_MIGR="${NGINX_LOG_AUDIT_STATE_DIR:-$HOME/.local/state/nginx-log-audit}"
migrer_chemin "$ETAT_MIGR/bannissements.tsv" "$ETAT_MIGR/bans.tsv"
migrer_chemin "$ETAT_MIGR/ip-publique" "$ETAT_MIGR/public-ip"
PUBLIC_IP_CACHE="${NGINX_LOG_AUDIT_STATE_DIR:-$HOME/.local/state/nginx-log-audit}/public-ip"
# Journal des bannissements et levees manuels : --unban-check, --investigate et --ban-history affichent la date, l'heure et la
# justification. Colonnes (TAB) : date heure | evenement (banni / leve) | IP | justification | origine (compte et programme).
# Les 3 premieres colonnes ne changent jamais : web-monitor.py --summary et --list-users les lisent. 4e colonne : avant la 2.40,
# seulement l'origine d'un import (BAN_NOTE) ; une ligne plus ancienne n'a que 3 colonnes (justification inconnue).
BAN_LOG="${NGINX_LOG_AUDIT_STATE_DIR:-$HOME/.local/state/nginx-log-audit}/bans.tsv"
# Une seule ligne, sans TAB ni retour de ligne ni code de controle (le fichier est lu colonne par colonne), 300 caracteres au plus.
nettoyer_texte() {
    local t
    t=$(printf '%s' "$1" | tr '\t\r\n' '   ' | tr -d '\000-\010\013\014\016-\037\177' | sed -E 's/  +/ /g; s/^ //; s/ $//')
    printf '%s' "${t:0:300}"            # in characters (UTF-8 locale), never in the middle of an accented letter
}
# Qui a demande l'action : le compte (sudo compris) et le programme appelant avec son option principale (web-monitor.py
# --ban-recommended, app-log-live.py, nginx-log-audit.sh --unban-check or the report...), otherwise "command line". Walks up
# the parent processes (/proc, 8 levels at most) skipping the wrappers of THIS call (sudo, timeout, bash... whose line contains
# already --ban or --unban of this program). Never an error.
origine_appel() {
    local qui="${SUDO_USER:-${USER:-$(id -un 2>/dev/null || echo root)}}" pid="$PPID" niveau mot prog="" opt="" meme
    local -a args
    for (( niveau = 0; niveau < 8 && pid > 1; niveau++ )); do
        [[ -r "/proc/$pid/cmdline" ]] || break
        mapfile -d '' -t args < "/proc/$pid/cmdline" 2>/dev/null || break       # one argument per element (NUL separated)
        prog=""; opt=""; meme=0
        for mot in "${args[@]}"; do
            [[ "$mot" == *[[:space:]]* ]] && continue                           # e.g. "bash -c 'script...'": not a program name
            case "$mot" in
                *web-monitor.py|*app-log-live.py|*app-log-check.py|*nginx-log-audit.sh|*nginx-hardening.sh) [[ -z "$prog" ]] && prog=$(basename "$mot") ;;
                --ban|--unban) [[ "$prog" == nginx-log-audit.sh ]] && meme=1 ;;
                --*) [[ -n "$prog" && -z "$opt" ]] && opt="${mot%%=*}" ;;
            esac
        done
        if [[ -n "$prog" && "$meme" == "0" ]]; then
            [[ "$prog" == nginx-log-audit.sh && -z "$opt" ]] && opt="(rapport)"
            printf '%s via %s%s' "$qui" "$prog" "${opt:+ $opt}"
            return 0
        fi
        pid=$(awk '/^PPid:/ { print $2 }' "/proc/$pid/status" 2>/dev/null) || break
        [[ -n "$pid" ]] || break
    done
    printf '%s via ligne de commande' "$qui"
}
note_ban() {
    mkdir -p "$(dirname "$BAN_LOG")" 2>/dev/null || return 0
    local raison
    raison=$(nettoyer_texte "${BAN_NOTE:+$BAN_NOTE${BAN_REASON:+ — }}${BAN_REASON}")
    printf '%s\t%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M')" "$1" "$2" "${raison:--}" "$(nettoyer_texte "$(origine_appel)")" >> "$BAN_LOG" 2>/dev/null || true
}
# Address ALREADY banned: a justification given (at the keyboard or --reason, not the automatic one) is added to the log by an event
# "justifies" (the ban date does not change) - this is how a ban prior to 2.40 is justified after the fact.
ajouter_justification() {
    [[ -z "$BAN_REASON" || "$BAN_REASON" == automatique* ]] && return 0
    note_ban justifie "$1"
    echo "Justification ajoutée au bannissement existant ($(date '+%Y-%m-%d %H:%M')) : $BAN_REASON"
}
# demander_texte QUESTION [DEFAULT]: one line at the keyboard (DEFAULT proposed, editable); Ctrl+C = DEFAULT; without terminal: DEFAULT.
demander_texte() {
    local question="$1" defaut="${2:-}" tmp rc=0 reponse=""
    if [[ ! -t 0 ]]; then printf '%s' "$defaut"; return 0; fi
    tmp=$(mktemp)
    trap ':' INT
    ( trap - INT; read -e -r -i "$defaut" -p "$question" r && printf '%s' "$r" > "$tmp" ) </dev/tty >/dev/tty 2>&1 || rc=$?
    trap - INT; declare -F ctrl_c_installer >/dev/null && ctrl_c_installer
    reponse=$(cat "$tmp" 2>/dev/null) || reponse=""
    rm -f "$tmp"
    if (( rc != 0 )); then reponse="$defaut"; echo >/dev/tty; fi
    printf '%s' "$reponse"
}
# Raison d'un bannissement par un jail fail2ban (ceux de nginx-hardening.sh et les jails courants), pour --investigate.
raison_jail() {
    case "$1" in
        nginx-blocked-probes) echo "requêtes REFUSÉES par nginx (fichiers sensibles, failles, outils d'attaque) — blocked-probes.log" ;;
        nginx-catchall)       echo "accès par adresse IP brute ou domaine inconnu (capteur catch-all) — typique d'un scanner" ;;
        odoo-auth)            echo "échecs de connexion à Odoo (mot de passe) répétés" ;;
        sshd|ssh)             echo "échecs de connexion SSH répétés" ;;
        recidive)             echo "bannie à répétition par d'autres jails (récidive)" ;;
        nginx-limit-req)      echo "trop de requêtes (limite de débit de nginx dépassée)" ;;
        nginx-http-auth)      echo "échecs d'authentification HTTP de nginx" ;;
        nginx-botsearch)      echo "recherche de pages d'administration ou de failles (robot)" ;;
        nginx-bad-request)    echo "requêtes HTTP malformées" ;;
        *)                    echo "règle du jail $1 (filtre /etc/fail2ban/filter.d/$1.conf)" ;;
    esac
}
ALLOWED_IPS_CACHE=""
ALLOWED_IPS_LOADED=0
# Displays the reason and returns 0 if the IP is protected; returns 1 otherwise. Second line displayed: "refused" (the
# server itself or an internal network: --ban refuses) or "warning" (team, nginx white list: --ban
# demande confirmation avec un avertissement explicite).
# Bannissements MANUELS en place (--ban, ou regle equivalente posee a la main) : regles directes de la chaine INPUT
# "-s IP -j DROP" (nor the fail2ban chains, temporary, nor the port rules of nginx-hardening.sh, nor the ipset
# CrowdSec), and ufw "deny from" rules if it is active.
list_manual_bans() {
    {
        if command -v iptables >/dev/null 2>&1; then
            run iptables -S INPUT 2>/dev/null | sed -nE 's#^-A INPUT -s ([0-9.]+)(/32)? -j DROP$#\1#p' || true
        fi
        if command -v ip6tables >/dev/null 2>&1; then
            run ip6tables -S INPUT 2>/dev/null | sed -nE 's#^-A INPUT -s ([0-9a-fA-F:]+)(/128)? -j DROP$#\1#p' || true
        fi
        if ufw_active; then
            run ufw status 2>/dev/null | awk '/DENY/ {print $NF}' | grep -E '^[0-9a-fA-F:.]+$' || true
        fi
    } | sort -u
}

# Preuves rassemblees pour une IP avant un bannissement (2.5) : identite DNS (PTR, confirmation, scanners declares),
# historique fail2ban (fail2ban.log et rotations), requetes au capteur catch-all et au site (rotations comprises), journal
# system for jails other than nginx (sshd, odoo-auth), then "for / against" summary and verdict. All the sources:
# une IP bannie par la jail nginx-catchall n'apparait QUE dans le journal du capteur, jamais dans celui du site.
PREUVES_SITE=0
# Fichiers du plus ancien au plus recent (rotations d'abord), pour des exemples et des dates dans l'ordre chronologique.
lire_chrono() {
    local f
    # shellcheck disable=SC2012  # noms de fichiers de journaux maitrises (pas d'espaces) : ls -tr suffit
    ls -1tr -- "$@" 2>/dev/null | while IFS= read -r f; do
        if [[ -r "$f" ]]; then progres_detail "  lecture de $(basename "$f") ($(taille_lisible "$f"))"; zcat -f -- "$f"; fi
    done 2>/dev/null || true
}

# urls_refusees IP [N]: the pages requested by IP and REFUSED by nginx, according to blocked-probes.log - the log read by the jail
# nginx-blocked-probes: it is that one, and not the site logs, that contains what got the address banned (our refusal rules
# write there instead of the site log). One line per page, most frequent first: "<count><TAB><page> (<code>)".
urls_refusees() {
    local ip="$1" n="${2:-5}" ipre
    ipre=$(printf '%s' "$ip" | sed 's/[.]/\\./g')
    compgen -G "/var/log/nginx/blocked-probes.log*" >/dev/null || return 0
    lire_chrono /var/log/nginx/blocked-probes.log* | { grep -E "^$ipre " || true; } \
        | awk '{ u = $7; sub(/\?.*/, "", u); c[u " (" $9 ")"]++ } END { for (k in c) printf "%d\t%s\n", c[k], k }' \
        | sort -t"$(printf '\t')" -k1,1nr -k2,2 | awk -v n="$n" 'NR <= n'
}
preuves_ip() {
    local ip="$1" ipre out rc ptr="" dns="" f
    local -a pour=() contre=() faible=()
    ipre=$(printf '%s' "$ip" | sed 's/[.]/\\./g')
    echo "${C_BOLD}PREUVES RASSEMBLÉES POUR $ip${C_RESET}"
    # --- 1) Identite ---
    echo
    echo "  Identité (DNS inverse)"
    # Meme interrogation que l'enquete (host IP), avec dig puis getent en repli : une seule reponse DNS partout.
    if command -v host >/dev/null 2>&1; then
        out=$(timeout --foreground 5 host "$ip" 2>&1) && rc=0 || rc=$?
        if (( rc == 124 )) || printf '%s' "$out" | grep_q -Ei 'timed out|no servers'; then dns="délai"
        else ptr=$(printf '%s\n' "$out" | { grep -m1 -oE 'pointer [^ ]+' || true; } | awk '{print $2}' | sed 's/\.$//'); fi
    elif command -v dig >/dev/null 2>&1; then
        out=$(timeout --foreground 5 dig +short +time=2 +tries=1 -x "$ip" 2>&1) && rc=0 || rc=$?
        if (( rc == 124 )) || printf '%s' "$out" | grep_q -Ei 'timed out|no servers'; then dns="délai"
        else ptr=$(printf '%s\n' "$out" | { grep -m1 -E '^[A-Za-z0-9._-]+\.$' || true; } | sed 's/\.$//'); fi
    elif command -v getent >/dev/null 2>&1; then
        out=$(timeout --foreground 5 getent hosts "$ip") && rc=0 || rc=$?
        if (( rc == 124 )); then dns="délai"; else ptr=$(printf '%s\n' "$out" | awk 'NF > 1 { print $2; exit }'); fi
    else
        dns="outil"
    fi
    if [[ "$dns" == "délai" ]]; then
        echo "    PTR : non vérifiable — délai dépassé (5 s) : le serveur DNS ne répond pas. La décision repose sur les"
        echo "          autres preuves ci-dessous."
    elif [[ "$dns" == "outil" ]]; then
        echo "    PTR : non vérifiable — aucun outil DNS (dig, host, getent) ; installer : apt install bind9-dnsutils"
    elif [[ -z "$ptr" ]]; then
        echo "    PTR : ${C_MAL}aucun${C_RESET} — pas de nom inverse déclaré : fréquent pour les serveurs loués et les machines"
        echo "          compromises ; rare pour un fournisseur d'accès grand public ou un moteur de recherche."
        faible+=("aucun nom inverse (PTR) : ni fournisseur d'accès grand public ni moteur de recherche identifiable")
    else
        local retour
        retour=$(timeout --foreground 5 getent ahosts "$ptr" 2>/dev/null | awk '{print $1}' | sort -u) || retour=""
        if printf '%s\n' "$retour" | grep_q -xF "$ip"; then
            echo "    PTR : $ptr (confirmé : ce nom renvoie bien vers $ip)"
        else
            echo "    PTR : $ptr (${C_YELLOW}NON confirmé${C_RESET} : ce nom ne renvoie pas vers $ip — nom possiblement usurpé)"
        fi
        if printf '%s' "$ptr" | grep_q -Ei 'censys|shodan|internet-measurement|binaryedge|stretchoid|shadowserver|onyphe|criminalip|leakix|recyber|internettl|alphastrike|scanner|scan\.'; then
            echo "          ${C_MAL}Scanner Internet déclaré${C_RESET} : balaie tout Internet (ports, HTTP) pour des études ou des"
            echo "          moteurs de recherche de failles. Le bannir est sans effet négatif pour le site."
            pour+=("scanner Internet déclaré ($ptr)")
        elif printf '%s\n' "$retour" | grep_q -xF "$ip" && printf '%s' "$ptr" | grep_q -Ei 'googlebot\.com|google\.com|search\.msn\.com|crawl\.yahoo\.net|applebot\.apple\.com|yandex\.(ru|com|net)|baidu\.(com|jp)|duckduckgo\.com|petalsearch\.com|qwant\.com'; then
            contre+=("moteur de recherche AUTHENTIQUE ($ptr, confirmé) : le bannir retire le site de ses résultats")
        fi
    fi
    # --- Place (list of places): a shared or protected address is an argument AGAINST the ban ---
    local lieu_info lieu_lib lieu_opts lieu_plage
    lieu_info=$(lieu_de_ip "$ip")
    if [[ -n "$lieu_info" ]]; then
        IFS=$'\037' read -r lieu_lib lieu_opts lieu_plage <<< "$lieu_info"
        echo
        echo "  Lieu (/etc/default/nginx-tools-ip-location.conf)"
        echo "    $lieu_lib (plage $lieu_plage)${lieu_opts:+ — options : ${lieu_opts//,/, }}"
        if [[ "$lieu_opts" == *partagee* ]]; then contre+=("adresse PARTAGÉE ($lieu_lib) : la bannir bloquerait toutes les personnes de ce lieu"); fi
        if [[ "$lieu_opts" == *protegee* ]]; then contre+=("lieu PROTÉGÉ ($lieu_lib) : à ne bannir que pour une raison grave"); fi
    fi
    # --- Compte Odoo ---
    charger_logins
    local l_odoo
    l_odoo=$(logins_odoo "$ip")
    if [[ -n "$l_odoo" ]]; then
        echo
        echo "  Connexions à Odoo (journal, 100 jours)"
        printf '%s\n' "$l_odoo" | sed 's/^/    /'
        contre+=("connectée à Odoo avec un compte ($(printf '%s\n' "$l_odoo" | head -1 | cut -d' ' -f1)) : un bénévole ou un membre, pas un attaquant anonyme")
    fi
    # --- 2) Historique fail2ban ---
    echo
    echo "  Historique fail2ban (fail2ban.log et ses rotations)"
    local hist jails="" total_bans=0
    progres "Preuves pour $ip : historique fail2ban (fail2ban.log et ses rotations)"
    hist=$(lire_chrono "${FAIL2BAN_LOG_FILE:-/var/log/fail2ban.log}"* \
           | { grep -E "\] (Ban|Found) $ipre( |$)" || true; } | awk '
        { if (match($0, /\[[^]]+\] (Ban|Found) /)) {
              s = substr($0, RSTART, RLENGTH); j = s; sub(/^\[/, "", j); sub(/\].*/, "", j); J[j] = 1
              if (s ~ /Ban $/) { b[j]++; if (!((j, $1) in vu)) { vu[j, $1] = 1; jours[j] = jours[j] (jours[j] ? ", " : "") $1 } }
              else fo[j]++ } }
        END { for (j in J) printf "%s\t%d\t%d\t%s\n", j, b[j] + 0, fo[j] + 0, jours[j] }')
    if [[ -z "$hist" ]]; then
        echo "    aucun bannissement ni détection dans les journaux de fail2ban conservés"
    else
        local jail nb nf dates
        while IFS=$'\t' read -r jail nb nf dates; do
            dates=$(printf '%s' "$dates" | tr ',' '\n' | sed 's/^ *//' | sort -u | paste -sd ',' | sed 's/,/, /g')
            echo "    Jail ${C_MAL}$jail${C_RESET} : $nb bannissement(s) temporaire(s)${dates:+ les $dates}, $nf détection(s)"
            total_bans=$((total_bans + nb)); jails="$jails${jails:+, }$jail"
            [[ "$jail" == nginx-* ]] || JAILS_HORS_NGINX+=("$jail")
        done <<< "$hist"
        if (( total_bans >= 2 )); then
            pour+=("récidive : $total_bans bannissements temporaires par fail2ban ($jails) — revient après chaque levée")
        elif (( total_bans == 1 )); then
            pour+=("déjà bannie une fois par fail2ban ($jails)")
        fi
    fi
    # --- 3) nginx : capteur catch-all et site ---
    echo
    echo "  Requêtes reçues par nginx (journaux et rotations)"
    local ca n_ca=0 jours_ca site n_site=0 n_sens=0 n_ok=0
    progres "Preuves pour $ip : journaux du capteur catch-all"
    ca=$(lire_chrono /var/log/nginx/*catchall*.log* | { grep -E "^$ipre " || true; })
    [[ -n "$ca" ]] && n_ca=$(printf '%s\n' "$ca" | wc -l)
    if (( n_ca > 0 )); then
        jours_ca=$(printf '%s\n' "$ca" | grep -oE '\[[0-9]{2}/[A-Za-z]{3}/[0-9]{4}' | tr -d '[' | awk '!vu[$0]++' | paste -sd' ' | sed 's/ /, /g') || jours_ca=""
        echo "    Capteur catch-all : ${C_MAL}$n_ca requête(s)${C_RESET} (jours : $jours_ca) — adresse IP brute ou domaine inconnu :"
        echo "      aucun visiteur légitime ne passe par là (il arrive par le nom du site). Exemples :"
        printf '%s\n' "$ca" | tail -n 3 | cut -c1-150 | sed 's/^/        /'
        pour+=("$n_ca requête(s) au capteur catch-all (IP brute ou domaine inconnu), sur $(printf '%s' "$jours_ca" | awk -F', ' '{print NF}') jour(s)")
    else
        echo "    Capteur catch-all : aucune requête"
    fi
    local -a fichiers_site=()
    for f in /var/log/nginx/*access.log*; do case "$f" in *catchall*) ;; *) [[ -e "$f" ]] && fichiers_site+=("$f") ;; esac; done
    site=""
    progres "Preuves pour $ip : journaux du site (${#fichiers_site[@]} fichier(s) et leurs rotations, un à la fois)"
    (( ${#fichiers_site[@]} > 0 )) && site=$(lire_chrono "${fichiers_site[@]}" | { grep -E "^$ipre " || true; })
    if [[ -n "$site" ]]; then
        n_site=$(printf '%s\n' "$site" | wc -l)
        n_sens=$(printf '%s\n' "$site" | awk '$7 ~ /\.env|\.git\/|\/wp-|wp-login|\.php|cgi-bin|\.\.\/|%2e%2e|\.(bak|old|sql|swp)$/' | wc -l)
        n_ok=$(printf '%s\n' "$site" | awk '$6 == "\"GET" && $9 ~ /^2/ && $7 !~ /\.env|\.git\/|\/wp-|\.php|cgi-bin|\.\.\//' | wc -l)
        echo "    Site : $n_site requête(s), dont ${C_MAL}$n_sens tentative(s)${C_RESET} d'accès à des fichiers sensibles ou à des failles et $n_ok page(s) servie(s)"
        (( n_sens > 0 )) && pour+=("$n_sens tentative(s) d'accès à des fichiers sensibles ou à des failles sur le site")
        (( n_ok > 0 )) && contre+=("$n_ok page(s) du site servie(s) avec succès : l'enquête ci-dessous dit s'il s'agit d'un robot légitime")
    else
        echo "    Site : aucune requête (les requêtes REFUSÉES par nginx ne sont pas dans ces journaux : voir ci-dessous)"
    fi
    PREUVES_SITE=$n_site
    # --- 3b) Requests REFUSED by nginx: blocked-probes.log, what the nginx-blocked-probes jail reads ---
    local refus n_refus=0 jours_refus
    progres "Preuves pour $ip : requêtes refusées par nginx (blocked-probes.log)"
    refus=$(lire_chrono /var/log/nginx/blocked-probes.log* 2>/dev/null | { grep -E "^$ipre " || true; })
    [[ -n "$refus" ]] && n_refus=$(printf '%s\n' "$refus" | wc -l)
    if (( n_refus > 0 )); then
        jours_refus=$(printf '%s\n' "$refus" | grep -oE '\[[0-9]{2}/[A-Za-z]{3}/[0-9]{4}' | tr -d '[' | awk '!vu[$0]++' | paste -sd' ' | sed 's/ /, /g') || jours_refus=""
        echo "    Requêtes REFUSÉES par nginx : ${C_MAL}$n_refus requête(s)${C_RESET} (jours : $jours_refus) — c'est ce que voit le jail nginx-blocked-probes."
        echo "      Pages demandées (fichiers sensibles, failles, outils d'attaque) :"
        urls_refusees "$ip" 8 | awk -F'\t' '{ printf "        %5d  %s\n", $1, $2 }'
        pour+=("$n_refus requête(s) refusée(s) par nginx (fichiers sensibles, failles, outils d'attaque), sur $(printf '%s' "$jours_refus" | awk -F', ' '{print NF}') jour(s)")
    else
        echo "    Requêtes refusées par nginx (blocked-probes.log) : aucune dans les journaux conservés"
    fi
    # --- 4) System log (jails other than nginx: sshd, odoo-auth...) ---
    if (( ${#JAILS_HORS_NGINX[@]} > 0 )) && command -v journalctl >/dev/null 2>&1; then
        echo
        echo "  Journal système (jails hors nginx : ${JAILS_HORS_NGINX[*]})"
        local jn n_jn=0
        progres "Preuves pour $ip : journal systemd (100 jours, jusqu'à 30 s)"
        jn=$(timeout --foreground 30 journalctl -q --no-pager -o short-iso --since "-100 days" -g "$ipre" 2>/dev/null) || jn=""
        [[ -n "$jn" ]] && n_jn=$(printf '%s\n' "$jn" | wc -l)
        if (( n_jn > 0 )); then
            echo "    ${C_MAL}$n_jn ligne(s)${C_RESET} mentionnent $ip. Exemples :"
            printf '%s\n' "$jn" | tail -n 3 | cut -c1-150 | sed 's/^/        /'
            pour+=("$n_jn ligne(s) du journal système (${JAILS_HORS_NGINX[*]} : tentatives de connexion)")
        else
            echo "    aucune ligne (journal peut-être plus court que l'historique de fail2ban)"
        fi
    fi
    # --- 5) Synthese ---
    echo
    echo "  Synthèse"
    local r
    if (( ${#pour[@]} > 0 )); then
        echo "    Pour le bannissement :"
        for r in "${pour[@]}"; do echo "      + $r"; done
    fi
    if (( ${#faible[@]} > 0 )); then
        echo "    Indice faible (jamais suffisant seul) :"
        for r in "${faible[@]}"; do echo "      · $r"; done
    fi
    if (( ${#contre[@]} > 0 )); then
        echo "    Contre :"
        for r in "${contre[@]}"; do echo "      ${C_YELLOW}− $r${C_RESET}"; done
    fi
    # Justification proposal for --ban (2.40): the "for" evidence, on one line.
    PREUVES_RESUME=""
    if (( ${#pour[@]} > 0 )); then PREUVES_RESUME=$(printf '%s ; ' "${pour[@]}"); PREUVES_RESUME="${PREUVES_RESUME% ; }"; fi
    if (( ${#pour[@]} == 0 && ${#contre[@]} > 0 )); then
        echo "    ${C_RED}Verdict : ne pas bannir${C_RESET} — aucune preuve contre cette IP, et des éléments plaident en sa faveur."
    elif (( ${#pour[@]} == 0 )); then
        echo "    ${C_YELLOW}Aucune preuve dans les journaux conservés : ne pas bannir sans raison connue par ailleurs.${C_RESET}"
    elif (( ${#contre[@]} == 0 )); then
        echo "    ${C_GREEN}Verdict : bannissement justifié${C_RESET} (aucune raison contraire trouvée)."
    else
        echo "    ${C_YELLOW}Verdict : à examiner${C_RESET} — des éléments plaident contre (voir aussi l'enquête ci-dessous)."
    fi
    echo
}
JAILS_HORS_NGINX=()
PREUVES_RESUME=""
PROP_RAISON=""

# --- Bans of an IP (2.40): CURRENT state (firewall, fail2ban, CrowdSec list) and CHRONOLOGICAL HISTORY (ban log)
# bannissements manuels bans.tsv, fail2ban.log et rotations) avec la date, l'heure et la justification de chaque bannissement.
# Used by --investigate (even without any request to the site: an address banned by nginx-blocked-probes appears only in
# blocked-probes.log) et par --unban-check. $2 : indentation.
afficher_bannissements() {
    local ip="$1" ind="${2:-  }" ipre trouve=0 j quand n=0 d=""
    local -a jails_actuels=() jails_hist=()
    ipre=$(printf '%s' "$ip" | sed 's/[.]/\\./g')
    progres "Bannissements de $ip : pare-feu, fail2ban, liste CrowdSec, journal des bannissements manuels"
    echo "${ind}${C_BOLD}Bannissements de $ip${C_RESET} (quand, et pourquoi)"
    # --- 1) Current state ---
    echo "${ind}  État actuel :"
    if [[ "$EUID" -ne 0 ]]; then
        echo "${ind}    non lisible sans root (pare-feu, fail2ban, ipset) : relancer avec sudo"
    else
        local pf=""
        if [[ "$ip" == *:* ]]; then
            command -v ip6tables >/dev/null 2>&1 && run ip6tables -C INPUT -s "$ip" -j DROP 2>/dev/null && pf="règle ip6tables « DROP »"
        else
            command -v iptables >/dev/null 2>&1 && run iptables -C INPUT -s "$ip" -j DROP 2>/dev/null && pf="règle iptables « DROP »"
        fi
        if [[ -z "$pf" ]] && ufw_active && run ufw status 2>/dev/null | awk '/DENY/ {print $NF}' | grep_q -xF -- "$ip"; then pf="règle ufw « deny from »"; fi
        if [[ -n "$pf" ]]; then
            trouve=1
            echo "${ind}    Pare-feu : ${C_MAL}BANNIE${C_RESET} — $pf (bannissement manuel, sans expiration ; levée : nginx-log-audit.sh --unban $ip)"
        else
            echo "${ind}    Pare-feu : pas de bannissement manuel"
        fi
        if command -v fail2ban-client >/dev/null 2>&1 && run fail2ban-client ping >/dev/null 2>&1; then
            for j in $(run fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr ',' ' '); do
                if run fail2ban-client status "$j" 2>/dev/null | sed -n 's/.*Banned IP list:[[:space:]]*//p' | tr ' ' '\n' | grep_q -xF -- "$ip"; then
                    jails_actuels+=("$j")
                    # fail2ban 0.11+: "IP  YYYY-MM-DD HH:MM:SS + duration = YYYY-MM-DD HH:MM:SS" (start and end of the ban)
                    quand=$(run fail2ban-client get "$j" banip --with-time 2>/dev/null | awk -v ip="$ip" '$1 == ip { $1 = ""; sub(/^[ \t]+/, ""); print; exit }') || quand=""
                    echo "${ind}    fail2ban : ${C_MAL}BANNIE${C_RESET} par le jail ${C_MAL}$j${C_RESET} — $(raison_jail "$j")"
                    if [[ -n "$quand" ]]; then echo "${ind}      début + durée = fin : $quand"; fi
                fi
            done
            if (( ${#jails_actuels[@]} == 0 )); then echo "${ind}    fail2ban : pas bannie actuellement"; else trouve=1; fi
        else
            echo "${ind}    fail2ban : non installé ou arrêté"
        fi
        local s cs=""
        if command -v ipset >/dev/null 2>&1; then
            for s in crowdsec-blocklist-v4 crowdsec-blocklist-v6; do
                run ipset test "$s" "$ip" >/dev/null 2>&1 && cs="$s"
            done
        fi
        if [[ -n "$cs" ]]; then
            trouve=1
            local maj liste="${SYNC_CROWDSEC_STATE_DIR:-/var/lib/sync-crowdsec-blocklist}/last-list.txt"
            maj=$(date -r "$liste" '+%Y-%m-%d %H:%M' 2>/dev/null) || maj=""
            echo "${ind}    Liste CrowdSec : ${C_MAL}BLOQUÉE${C_RESET} (ipset $cs) — adresse signalée comme agressive par d'autres serveurs du réseau"
            echo "${ind}      CrowdSec (liste communautaire, sync-crowdsec-blocklist.sh) : aucune justification locale${maj:+ ; liste mise à jour le $maj}"
        else
            echo "${ind}    Liste CrowdSec : absente"
        fi
    fi
    # --- 2) History: one line per event, from oldest to newest ---
    local hist="" f2b
    if [[ -r "$BAN_LOG" ]]; then
        hist=$(awk -F'\t' -v ip="$ip" '$3 == ip {
                   ev = ($2 == "banni") ? "BANNIE au pare-feu" : (($2 == "leve") ? "bannissement LEVÉ" : (($2 == "justifie") ? "justification ajoutée" : $2))
                   r = (NF >= 4 && $4 != "" && $4 != "-") ? "justification : " $4 : "justification : non enregistrée (avant la version 2.40)"
                   printf "%s\t%s — %s%s\n", $1, ev, r, (NF >= 5 && $5 != "") ? " — par " $5 : "" }' "$BAN_LOG" 2>/dev/null) || hist=""
    fi
    f2b=$(lire_chrono "${FAIL2BAN_LOG_FILE:-/var/log/fail2ban.log}"* | { grep -E "\] (Restore Ban|Ban|Unban) $ipre( |$)" || true; } | awk '
            { if (match($0, /\[[^]]+\] (Restore Ban|Ban|Unban) /)) {
                  s = substr($0, RSTART, RLENGTH); j = s; sub(/^\[/, "", j); sub(/\].*/, "", j)
                  a = s; sub(/^\[[^]]+\] /, "", a); sub(/ $/, "", a)
                  t = (a == "Unban") ? "fail2ban : bannissement levé par le jail " j " (fin de la durée, ou levée manuelle)" : ((a == "Ban") ? "fail2ban : BANNIE par le jail " j : "fail2ban : bannissement rétabli au redémarrage (jail " j ")")
                  printf "%s %s\t%s\t%s\n", $1, substr($2, 1, 8), t, j } }')
    if [[ -n "$f2b" ]]; then
        mapfile -t jails_hist < <(printf '%s\n' "$f2b" | awk -F'\t' '$2 ~ /BANNIE/ { print $3 }' | sort -u)
        f2b=$(printf '%s\n' "$f2b" | cut -f1,2)
        hist="$hist${hist:+$'\n'}$f2b"
    fi
    echo "${ind}  Historique (heure locale, du plus ancien au plus récent) :"
    if [[ -z "$hist" ]]; then
        echo "${ind}    aucun événement dans le journal des bannissements manuels ni dans les journaux de fail2ban conservés"
    else
        trouve=1
        n=$(printf '%s\n' "$hist" | grep -c .)
        (( n > 30 )) && echo "${ind}    ($((n - 30)) événement(s) plus ancien(s) non affiché(s))"
        printf '%s\n' "$hist" | sort -s -t"$(printf '\t')" -k1,1 | tail -n 30 | awk -F'\t' -v ind="$ind" -v m="$C_MAL" -v r="$C_RESET" '
            { t = $2; if (t ~ /BANNIE/) t = m t r; printf "%s    %-19s  %s\n", ind, $1, t }'
    fi
    # --- 3) Detailed reason of each fail2ban jail involved: what the address did ---
    local -A vus=()
    for j in "${jails_actuels[@]}" "${jails_hist[@]}"; do
        [[ -z "$j" || -n "${vus[$j]:-}" ]] && continue
        vus[$j]=1
        echo "${ind}  Pourquoi le jail $j l'a bannie : $(raison_jail "$j")"
        local found
        found=$(lire_chrono "${FAIL2BAN_LOG_FILE:-/var/log/fail2ban.log}"* | { grep -E "\[$j\] Found $ipre( |$)" || true; } \
                | awk '{ n++; if (!p) p = $1 " " substr($2, 1, 8); d = $1 " " substr($2, 1, 8) } END { if (n) printf "%d\t%s\t%s\n", n, p, d }')
        if [[ -n "$found" ]]; then
            IFS=$'\t' read -r n quand d <<< "$found"
            echo "${ind}    $n détection(s) par fail2ban (première : $quand, dernière : $d)"
        fi
        case "$j" in
            nginx-blocked-probes)
                local pages
                pages=$(urls_refusees "$ip" 8)
                if [[ -n "$pages" ]]; then
                    echo "${ind}    Pages demandées et refusées par nginx (blocked-probes.log) :"
                    printf '%s\n' "$pages" | awk -F'\t' -v ind="$ind" '{ printf "%s      %5d  %s\n", ind, $1, $2 }' | surligner
                else
                    echo "${ind}    (blocked-probes.log ne contient plus ces requêtes : journal tourné depuis)"
                fi ;;
            nginx-catchall)
                local ca
                ca=$(lire_chrono /var/log/nginx/*catchall*.log* | { grep -E "^$ipre " || true; } | tail -n 3 | cut -c1-150)
                if [[ -n "$ca" ]]; then echo "${ind}    Dernières requêtes au capteur catch-all :"; printf '%s\n' "$ca" | sed "s/^/${ind}      /"; fi ;;
            *)
                echo "${ind}    Détail : journalctl -g '$ipre' --since -100days   (journal du service surveillé par ce jail)" ;;
        esac
    done
    if (( trouve == 0 )); then
        echo "${ind}  ${C_GREEN}Aucun bannissement trouvé${C_RESET} sur ce serveur : ni pare-feu, ni fail2ban (journaux conservés), ni liste CrowdSec,"
        echo "${ind}  ni journal des bannissements manuels ($BAN_LOG). Si elle est signalée bannie ailleurs, vérifier sur l'autre serveur."
    fi
    echo
}

# SUCCESSFUL logins to Odoo (2.10), read ONCE per execution in the systemd journal (100 days): Odoo writes
# "Login successful for db:BASE login:ACCOUNT from IP". An IP that logged in with an account (volunteer, member)
# is never proposed for banning. load_logins is called outside the sub-shell (global cache); logins_odoo filters.
LOGINS_CHARGES=0
LOGINS_TABLE=""
charger_logins() {
    (( LOGINS_CHARGES )) && return 0
    LOGINS_CHARGES=1
    local unites=() u
    for u in ${SERVICES:-erplibre.service erplibre_erplibre.service odoo.service}; do
        [[ "$u" == postgresql* ]] || unites+=(-u "$u")
    done
    command -v journalctl >/dev/null 2>&1 || return 0
    progres "Lecture du journal systemd d'Odoo : connexions des 100 derniers jours (jusqu'à 60 s)"
    LOGINS_TABLE=$(timeout --foreground 60 journalctl "${unites[@]}" -q --no-pager -o short-iso --since "-100 days" \
                   -g "Login successful for" 2>/dev/null \
                   | sed -nE 's/^([0-9T:-]+).* login:([^ ]+) from ([0-9a-fA-F:.]+).*/\3 \2 \1/p') || LOGINS_TABLE=""
    # 2.37 : comptes BANNIS par web-monitor.py --ban-odoo-user (registre apps/_odoo_users.py) : leurs connexions ne font plus d'une adresse
    # "a legitimate user" (otherwise --unban-check would propose lifting the ban of their addresses).
    local registre="${NGINX_TOOLS_ODOO_USERS:-/var/lib/nginx-tools/odoo-users.tsv}" bannis
    if [[ -n "$LOGINS_TABLE" && "$registre" != off && -r "$registre" ]]; then
        bannis=$(awk -F'\t' '$2 == "banned" { b[$5] = 1 } $2 == "unbanned" { delete b[$5] } END { for (l in b) print l }' "$registre" 2>/dev/null) || bannis=""
        if [[ -n "$bannis" ]]; then
            LOGINS_TABLE=$(printf '%s\n' "$LOGINS_TABLE" | awk 'NR == FNR { b[$0] = 1; next } !($2 in b)' <(printf '%s\n' "$bannis") -) || true
        fi
    fi
}
# comptes_surveilles : comptes Odoo SOUS SURVEILLANCE (web-monitor.py --watch-odoo-user), un par ligne.
comptes_surveilles() {
    local registre="${NGINX_TOOLS_ODOO_USERS:-/var/lib/nginx-tools/odoo-users.tsv}"
    [[ "$registre" != off && -r "$registre" ]] || return 0
    awk -F'\t' '$2 == "watched" { w[$5] = 1 } $2 == "unwatched" { delete w[$5] } END { for (l in w) print l }' "$registre" 2>/dev/null || true
}
logins_odoo() {       # "account (N login(s), last YYYY-MM-DDTHH:MM)" for each account logged in from the IP
    [[ -z "$LOGINS_TABLE" ]] && return 0
    printf '%s\n' "$LOGINS_TABLE" | awk -v ip="$1" '$1 == ip { n[$2]++; d[$2] = $3 }
        END { for (l in n) printf "%s (%d connexion(s), dernière %s)\n", l, n[l], substr(d[l], 1, 16) }'
}

# ip_dans IP ENTRY: true if ENTRY is the IP address itself, or an IPv4 range (a.b.c.d/n) that contains it.
ip_dans() {
    local ip="$1" e="$2" net bits a b c d x y
    [[ "$e" == */* ]] || { [[ "$e" == "$ip" ]]; return; }
    net=${e%/*}; bits=${e#*/}
    [[ "$ip" =~ ^[0-9]+(\.[0-9]+){3}$ && "$net" =~ ^[0-9]+(\.[0-9]+){3}$ && "$bits" =~ ^[0-9]+$ ]] || return 1
    (( bits >= 0 && bits <= 32 )) || return 1
    IFS=. read -r a b c d <<< "$ip"; x=$(( (a << 24) | (b << 16) | (c << 8) | d ))
    IFS=. read -r a b c d <<< "$net"; y=$(( (a << 24) | (b << 16) | (c << 8) | d ))
    (( bits == 0 || (x >> (32 - bits)) == (y >> (32 - bits)) ))
}

# lieu_de_ip IP: "LABEL<TAB>OPTIONS<TAB>RANGE" of the most precise place (longest prefix) that contains the address; nothing otherwise.
lieu_de_ip() {
    local ip="$1" adr lib opts _n best="" best_bits=-1 bits
    while IFS=$'\037' read -r adr lib opts _n; do
        [[ -z "$adr" ]] && continue
        if ip_dans "$ip" "$adr"; then
            bits=32; if [[ "$adr" == */* ]]; then bits=${adr#*/}; fi
            if (( bits >= best_bits )); then best_bits=$bits; best=$(printf '%s\037%s\037%s' "$lib" "$opts" "$adr"); fi
        fi
    done <<< "$LIEUX_LIGNES"
    if [[ -n "$best" ]]; then printf '%s\n' "$best"; fi
    return 0
}

protected_ip_reason() {
    local ip="$1" a lieu lib opts plage
    case "$ip" in
        127.*|::1) printf '%s\n%s\n' "adresse de boucle locale : le serveur lui-même (app-health-check.py --target local, tests curl)" refus; return 0 ;;
        10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*|[fF][cCdD]*:*|[fF][eE]80:*) printf '%s\n%s\n' "réseau privé : trafic interne, jamais une attaque venue d'Internet" refus; return 0 ;;
    esac
    for a in $(hostname -I 2>/dev/null) $(cat "$PUBLIC_IP_CACHE" 2>/dev/null); do
        if [[ "$a" == "$ip" ]]; then
            printf '%s\n%s\n' "adresse de CE serveur (ex. app-health-check.py --target external, qui teste aussi le blocage des robots)" refus; return 0
        fi
    done
    for a in $TEAM_IPS; do
        if ip_dans "$ip" "$a"; then printf '%s\n%s\n' "IP de l'équipe$([[ "$a" == */* ]] && echo " (plage $a)")" avertissement; return 0; fi
    done
    lieu=$(lieu_de_ip "$ip")
    if [[ -n "$lieu" ]]; then
        IFS=$'\037' read -r lib opts plage <<< "$lieu"
        if [[ "$opts" == *protegee* ]]; then printf '%s\n%s\n' "lieu protégé : $lib (plage $plage)" avertissement; return 0; fi
    fi
    if [[ "$ALLOWED_IPS_LOADED" == "0" ]]; then
        ALLOWED_IPS_LOADED=1
        if command -v nginx >/dev/null 2>&1; then
            ALLOWED_IPS_CACHE=$(run nginx -T 2>/dev/null | grep -oE 'allow [0-9a-fA-F:./]+;' | awk '{print $2}' | tr -d ';' | sort -u) || true
        fi
    fi
    for a in $ALLOWED_IPS_CACHE; do                        # adresses exactes et plages (ex. cellulaire, adresse dynamique)
        if ip_dans "$ip" "$a"; then
            printf '%s\n%s\n' "IP présente dans une règle « allow » de la config nginx active (liste blanche$([[ "$a" == */* ]] && echo ", plage $a"))" avertissement; return 0
        fi
    done
    return 1
}

# Fusionne un fichier de log et toutes ses rotations (actif + .N + .N.gz) dans $2, decompressant les .gz a la
# volee. Affiche sur stdout la liste des fichiers effectivement traites (un par ligne), pour affichage par
# the caller - the merge itself is silent. Used by --init-all to analyze the WHOLE history
# disponible d'un coup, pas seulement le fichier actif.
merge_all_rotations() {
    local base="$1" out="$2" dir base_name f gz
    dir=$(dirname "$base")
    base_name=$(basename "$base")
    shopt -s nullglob
    local raw_files=("$dir/$base_name" "$dir/$base_name".[0-9]* "$dir/$base_name".[0-9]*.gz)
    shopt -u nullglob
    local files=()
    if [[ ${#raw_files[@]} -gt 0 ]]; then
        mapfile -t files < <(printf '%s\n' "${raw_files[@]}" | sort -u)
    fi
    : > "$out"
    local n_f=0 total_f=${#files[@]}
    for f in "${files[@]}"; do
        [[ -f "$f" ]] || continue
        n_f=$((n_f + 1))
        gz=""; if [[ "$f" == *.gz ]]; then gz=", compressé"; fi
        progres "Lecture du journal $n_f/$total_f : $(basename "$f") ($(taille_lisible "$f")$gz)"
        if [[ "$f" == *.gz ]]; then
            zcat "$f" >> "$out" 2>/dev/null || true
        else
            cat "$f" >> "$out" 2>/dev/null || true
        fi
        printf '%s\n' "$f"
    done
}

# --- Rough validation of IPv4/IPv6, shared by --ban and --unban ---
looks_like_ip() {
    local ip="$1"
    [[ "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]] && return 0
    [[ "$ip" == *:* && "$ip" =~ ^[0-9a-fA-F:]+$ ]] && return 0
    return 1
}

# --- --evidence IP: the evidence and verdict of --ban, WITHOUT question nor ban (read-only; used by app-log-live.py) ---
if [[ -n "$EVIDENCE_IP" ]]; then
    if ! looks_like_ip "$EVIDENCE_IP"; then
        echo "ERREUR: '$EVIDENCE_IP' ne ressemble pas à une adresse IP valide." >&2
        exit 1
    fi
    if prot=$(protected_ip_reason "$EVIDENCE_IP"); then
        echo "Adresse protégée : $(printf '%s\n' "$prot" | head -1) — jamais proposée au bannissement."
        exit 0
    fi
    preuves_ip "$EVIDENCE_IP"
    exit 0
fi

# --- --ban-history: log of manual bans and lifts (2.40): date, time, IP, justification, origin ---
if [[ "$DO_BAN_HISTORY" == "1" ]]; then
    echo "=============================================================="
    echo " JOURNAL DES BANNISSEMENTS MANUELS ($BAN_LOG)"
    echo "=============================================================="
    if [[ ! -s "$BAN_LOG" ]]; then
        echo "Aucun bannissement manuel enregistré (journal absent ou vide)."
        [[ "$EUID" -ne 0 ]] && echo "Le journal est dans le dossier du compte qui bannit (root) : relancer avec sudo."
        exit 0
    fi
    echo "Du plus ancien au plus récent (heure locale) — bannissements de fail2ban et liste CrowdSec : nginx-log-audit.sh --investigate IP"
    echo
    awk -F'\t' -v m="$C_MAL" -v g="$C_GREEN" -v r="$C_RESET" -v b="$C_BOLD" '
        BEGIN { printf "%s%-16s  %-8s  %-15s  %s%s\n", b, "Date", "Action", "IP", "Justification — origine", r }
        NF >= 3 {
            if ($2 == "banni") { a = m "banni" r "   " } else if ($2 == "leve") { a = g "levé" r "    " } else if ($2 == "justifie") { a = "justifié" } else { a = sprintf("%-8s", $2) }
            j = (NF >= 4 && $4 != "" && $4 != "-") ? $4 : "(non enregistrée : avant la version 2.40)"
            printf "%-16s  %s  %-15s  %s%s\n", $1, a, $3, j, (NF >= 5 && $5 != "") ? " — " $5 : "" }' "$BAN_LOG"
    exit 0
fi

# --- --ban IP : bannissement manuel via pare-feu (ufw ou iptables, meme logique que nginx-hardening.sh) ---------
# Choix delibere de NE PAS passer par les jails fail2ban existants : aucun d'eux ne surveille le capteur
# catch-all (d'ou vient typiquement la justification d'un bannissement manuel par volume), et injecter une IP
# dans le cycle de vie d'un jail dont le filtre ne l'a pas elle-meme detectee rendrait son expiration
# imprevisible. Le pare-feu direct est simple, universel, et sa duree est entierement sous votre controle.
if [[ -n "$BAN_IP" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: --ban nécessite root (sudo)." >&2
        exit 1
    fi
    if ! looks_like_ip "$BAN_IP"; then
        echo "ERREUR: '$BAN_IP' ne ressemble pas à une adresse IP valide." >&2
        exit 1
    fi

    echo "=============================================================="
    echo " BANNISSEMENT MANUEL : $BAN_IP"
    echo "=============================================================="
    BAN_PROTECTED_WARNING=""
    if prot=$(protected_ip_reason "$BAN_IP"); then
        prot_reason=$(printf '%s\n' "$prot" | head -1); prot_kind=$(printf '%s\n' "$prot" | tail -1)
        if [[ "$prot_kind" == "refus" ]]; then
            echo "${C_RED}REFUSÉ : $BAN_IP — $prot_reason.${C_RESET}" >&2
            echo "${C_RED}Ce trafic vient du serveur lui-même ou d'un réseau interne, jamais d'Internet : ce script ne la bannit jamais.${C_RESET}" >&2
            exit 1
        fi
        BAN_PROTECTED_WARNING="$prot_reason"
    fi

    echo
    # Preuves de TOUTES les sources avant la confirmation (demande interactive seulement : avec --yes, l'appel vient
    # of a question that already presented the IPs - and the DNS queries would slow down a group ban).
    [[ "$ASSUME_YES" != "1" ]] && preuves_ip "$BAN_IP"
    if [[ -n "$BAN_PROTECTED_WARNING" ]]; then
        echo "${C_RED}ATTENTION : $BAN_IP — $BAN_PROTECTED_WARNING. La bannir est très probablement une erreur.${C_RESET}"
    fi
    # Raisonnement AVANT la confirmation (demande interactive seulement : avec --yes, l'appel vient d'une question du
    # rapport ou de --unban-check, qui ont deja affiche l'enquete) : enquete complete sur tout l'historique, avec la
    # current logic - requested URLs, clues, signs of hostility, verdict.
    if [[ "$ASSUME_YES" != "1" ]]; then
        echo "Enquête détaillée sur les requêtes au site (même logique que --investigate) :"
        echo
        enquete=$(bash "$SELF_PATH" --investigate "$BAN_IP" --no-prompt ${APP_FORCE:+--app "$APP_FORCE"} 2>&1 \
                  | sed -n '/▶/,$p' | grep -v '^=====') || enquete=""
        if (( PREUVES_SITE == 0 )); then
            echo "  (aucune requête au site : l'enquête détaillée porte sur les journaux du site — les preuves ci-dessus"
            echo "   couvrent le capteur catch-all, fail2ban et le journal système)"
            echo
        elif [[ -n "$enquete" ]]; then
            printf '%s\n' "$enquete"
            if printf '%s\n' "$enquete" | grep_q "Signes d'hostilité : 0"; then
                echo "${C_YELLOW}ATTENTION : aucun signe d'hostilité (rafale, fichiers sensibles, erreurs en masse, faux moteur, catch-all) —${C_RESET}"
                echo "${C_YELLOW}bannir $BAN_IP n'est probablement pas justifié, sauf raison connue hors de ces journaux.${C_RESET}"
                echo
            fi
        else
            echo "  (enquête indisponible : aucune requête de $BAN_IP dans l'historique des journaux)"
            echo
        fi
    fi
    echo "Ceci va bloquer TOUT le trafic depuis $BAN_IP au niveau du pare-feu (toutes routes, tous ports gérés"
    echo "par ce pare-feu), immédiatement et indéfiniment — jusqu'à un --unban explicite ou un redémarrage si la"
    echo "règle n'est pas rendue persistante. Un vrai visiteur derrière cette IP (rare mais possible si l'IP a"
    echo "changé de main entre-temps) serait bloqué exactement pareil qu'un attaquant."

    if [[ "$ASSUME_YES" != "1" ]]; then
        echo
        if ! demander_oui "Confirmer le bannissement de $BAN_IP ? [o/N] "; then echo "Annulé."; exit 0; fi
    fi
    # Justification (2.40), recorded with the date and time in the ban log (--investigate, --unban-check and
    # --ban-history l'affichent) : au clavier (proposition modifiable : --reason, sinon les preuves), --reason avec --yes, sinon automatique.
    if [[ "$ASSUME_YES" != "1" ]]; then
        echo
        echo "Justification du bannissement (enregistrée avec la date et l'heure ; Entrée accepte la proposition) :"
        BAN_REASON=$(demander_texte "> " "${BAN_REASON:-${PREUVES_RESUME:+preuves : $PREUVES_RESUME}}")
    fi
    BAN_REASON=$(nettoyer_texte "$BAN_REASON")
    [[ -z "$BAN_REASON" ]] && BAN_REASON="automatique : aucune justification fournie"

    if ufw_active; then
        if run ufw status 2>/dev/null | grep_q -F "$BAN_IP"; then
            echo "${C_YELLOW}Déjà présent dans une règle ufw pour $BAN_IP — rien à faire.${C_RESET}"
            ajouter_justification "$BAN_IP"
        else
            run ufw deny from "$BAN_IP" >/dev/null
            echo "${C_GREEN}Règle ufw ajoutée : deny from $BAN_IP${C_RESET}"
            note_ban banni "$BAN_IP"
            echo "Justification enregistrée ($(date '+%Y-%m-%d %H:%M')) : $BAN_REASON"
            persist_firewall
        fi
    elif command -v iptables >/dev/null 2>&1; then
        if run iptables -C INPUT -s "$BAN_IP" -j DROP 2>/dev/null; then
            echo "${C_YELLOW}Déjà présent dans iptables pour $BAN_IP — règle inchangée.${C_RESET}"
            ajouter_justification "$BAN_IP"
            # Sauvegarde quand meme : c'est le moyen de rendre permanent un bannissement pose AVANT l'installation de
            # netfilter-persistent (le conseil affiche en fin de persist_firewall est de relancer --ban).
            persist_firewall
        else
            run iptables -I INPUT -s "$BAN_IP" -j DROP
            echo "${C_GREEN}Règle iptables ajoutée : DROP depuis $BAN_IP${C_RESET}"
            note_ban banni "$BAN_IP"
            echo "Justification enregistrée ($(date '+%Y-%m-%d %H:%M')) : $BAN_REASON"
            persist_firewall
        fi
    else
        echo "ERREUR: ni ufw ni iptables trouvés — bannissement impossible." >&2
        exit 1
    fi
    exit 0
fi

# --- --unban IP: lifts a manual ban set by --ban (ufw or iptables) ---
if [[ -n "$UNBAN_IP" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: --unban nécessite root (sudo)." >&2
        exit 1
    fi
    if ! looks_like_ip "$UNBAN_IP"; then
        echo "ERREUR: '$UNBAN_IP' ne ressemble pas à une adresse IP valide." >&2
        exit 1
    fi

    echo "=============================================================="
    echo " LEVÉE DE BANNISSEMENT MANUEL : $UNBAN_IP"
    echo "=============================================================="

    already_banned=0
    if command -v ufw >/dev/null 2>&1 && run ufw status 2>/dev/null | grep_q -F "$UNBAN_IP"; then
        already_banned=1
    fi
    if command -v iptables >/dev/null 2>&1 && run iptables -C INPUT -s "$UNBAN_IP" -j DROP 2>/dev/null; then
        already_banned=1
    fi
    if [[ "$already_banned" == "0" ]]; then
        echo "${C_YELLOW}Aucune règle de bannissement manuel (ufw/iptables) trouvée pour $UNBAN_IP — rien à lever.${C_RESET}"
        echo "(Si cette IP a été bannie par fail2ban plutôt que par --ban, utilisez :"
        echo " fail2ban-client set <jail> unbanip $UNBAN_IP)"
        exit 0
    fi

    echo "Ceci va retirer le blocage pare-feu pour $UNBAN_IP — le trafic de cette IP redeviendra possible"
    echo "immédiatement. Ne faites ça que si vous êtes sûr que ce bannissement était une erreur (IP mal notée,"
    echo "IP réattribuée à un usage légitime depuis) — sinon l'IP reste bloquée jusqu'à expiration naturelle ou"
    echo "un futur --unban."

    if [[ "$ASSUME_YES" != "1" ]]; then
        echo
        if ! demander_oui "Confirmer la levée du bannissement de $UNBAN_IP ? [o/N] "; then echo "Annulé."; exit 0; fi
        echo
        echo "Justification de la levée (enregistrée avec la date et l'heure ; Entrée accepte la proposition) :"
        BAN_REASON=$(demander_texte "> " "$BAN_REASON")
    fi
    BAN_REASON=$(nettoyer_texte "$BAN_REASON")
    [[ -z "$BAN_REASON" ]] && BAN_REASON="automatique : aucune justification fournie"

    removed=0
    if command -v ufw >/dev/null 2>&1 && run ufw status 2>/dev/null | grep_q -F "$UNBAN_IP"; then
        run ufw delete deny from "$UNBAN_IP" >/dev/null 2>&1 && { echo "${C_GREEN}Règle ufw retirée pour $UNBAN_IP.${C_RESET}"; removed=1; }
    fi
    if command -v iptables >/dev/null 2>&1; then
        attempts=0
        while run iptables -C INPUT -s "$UNBAN_IP" -j DROP 2>/dev/null; do
            if run iptables -D INPUT -s "$UNBAN_IP" -j DROP 2>/dev/null; then
                echo "${C_GREEN}Règle iptables retirée pour $UNBAN_IP.${C_RESET}"
                removed=1
            else
                echo "${C_RED}Échec lors du retrait de la règle iptables pour $UNBAN_IP.${C_RESET}" >&2
                break
            fi
            attempts=$((attempts + 1))
            if (( attempts >= 20 )); then
                echo "${C_YELLOW}Arrêt de sécurité après 20 tentatives (répétitions inattendues).${C_RESET}" >&2
                break
            fi
        done
    fi
    if [[ "$removed" -eq 0 ]]; then
        echo "${C_RED}Une règle avait été détectée pour $UNBAN_IP mais son retrait a échoué — vérifiez manuellement.${C_RESET}" >&2
    else
        note_ban leve "$UNBAN_IP"
        echo "Justification enregistrée ($(date '+%Y-%m-%d %H:%M')) : $BAN_REASON"
        # Sans resauvegarde, l'ancienne sauvegarde persistante contiendrait encore la regle retiree : l'IP
        # redeviendrait bannie au prochain redemarrage.
        persist_firewall
    fi
    exit 0
fi

# --- --export-bans [FICHIER] : bannissements MANUELS en place, pour les importer sur un autre serveur ------------------
# Format: lines "IP<TAB>ban date<TAB>origin server", preceded by a comment header.
# Without file (or "-"): standard output, for a direct pipe between servers:
#   ssh autre-serveur nginx-log-audit.sh --export-bans | nginx-log-audit.sh --import-bans -
if [[ -n "$EXPORT_BANS" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: --export-bans nécessite root (lecture des règles du pare-feu)." >&2
        exit 1
    fi
    mapfile -t EXP < <(list_manual_bans)
    {
        echo "# nginx-tools — bannissements manuels exportés de $(hostname) le $(date '+%Y-%m-%d %H:%M %Z') (${#EXP[@]} IP)"
        echo "# Import : nginx-log-audit.sh --import-bans FICHIER   (IP<TAB>date du bannissement<TAB>serveur d'origine)"
        for ip in "${EXP[@]}"; do
            quand=$(awk -F'\t' -v ip="$ip" '$3 == ip && $2 == "banni" { d = $1 } END { print d }' "$BAN_LOG" 2>/dev/null) || quand=""
            printf '%s\t%s\t%s\n' "$ip" "${quand:-inconnue}" "$(hostname)"
        done
    } > "$( [[ "$EXPORT_BANS" == "-" ]] && echo /dev/stdout || echo "$EXPORT_BANS")"
    [[ "$EXPORT_BANS" != "-" ]] && echo "${#EXP[@]} bannissement(s) manuel(s) exporté(s) dans $EXPORT_BANS" >&2
    exit 0
fi

# --- --import-bans FICHIER|- : bannit sur CE serveur les IP d'un export --------------------------------------------------
# Apercu classe AVANT toute action (a bannir, deja bannies, protegees ici, invalides), puis UNE confirmation (--yes pour
# un usage scripte). Jamais importees : les IP protegees sur CE serveur (ses adresses, reseaux prives, equipe, liste
# local nginx white list) - they may differ from those of the origin server.
if [[ -n "$IMPORT_BANS" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: --import-bans nécessite root (pare-feu)." >&2
        exit 1
    fi
    if [[ "$IMPORT_BANS" != "-" && ! -r "$IMPORT_BANS" ]]; then
        echo "ERREUR: fichier d'import illisible : $IMPORT_BANS" >&2
        exit 1
    fi
    if [[ "$IMPORT_BANS" == "-" ]]; then
        CONTENU=$(cat)
        # La confirmation se lit au clavier : l'entree standard (le tube) est epuisee. Ouverture testee d'abord dans un
        # sub-shell: without a control terminal (cron, ssh without -t), an "exec < /dev/tty" that fails ENDS the script.
        if [[ "$ASSUME_YES" != "1" ]] && (exec < /dev/tty) 2>/dev/null; then exec < /dev/tty; fi
    else
        CONTENU=$(cat "$IMPORT_BANS")
    fi
    mapfile -t DEJA < <(list_manual_bans)
    A_BANNIR=(); n_deja=0; n_prot=0; n_inval=0; ORIGINE=""
    echo "=============================================================="
    echo " IMPORT DE BANNISSEMENTS${IMPORT_BANS:+ ($([[ "$IMPORT_BANS" == "-" ]] && echo "entrée standard" || echo "$IMPORT_BANS"))}"
    echo "=============================================================="
    while IFS=$'\t' read -r ip quand origine _; do
        ip="${ip%%[[:space:]]*}"
        [[ -z "$ip" || "$ip" == \#* ]] && continue
        [[ -n "${origine:-}" && -z "$ORIGINE" ]] && ORIGINE="$origine"
        if ! [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$ip" =~ ^[0-9a-fA-F:]+:[0-9a-fA-F:]*$ ]]; then
            echo "  ${C_YELLOW}[invalide]${C_RESET} $ip"; n_inval=$((n_inval + 1)); continue
        fi
        if prot=$(protected_ip_reason "$ip"); then
            echo "  ${C_GREEN}[protégée ici]${C_RESET} $ip — $(printf '%s\n' "$prot" | head -1) : jamais importée"; n_prot=$((n_prot + 1)); continue
        fi
        if printf '%s\n' "${DEJA[@]}" | grep_q -xF "$ip"; then
            n_deja=$((n_deja + 1)); continue
        fi
        case " ${A_BANNIR[*]} " in *" $ip "*) continue ;; esac            # doublon dans le fichier
        A_BANNIR+=("$ip")
        echo "  ${C_MAL}[à bannir]${C_RESET} $ip  (banni ${quand:-date inconnue}${origine:+ sur $origine})"
    done <<< "$CONTENU"
    echo
    echo "  ${#A_BANNIR[@]} à bannir, $n_deja déjà bannie(s) ici, $n_prot protégée(s) ici (ignorées), $n_inval invalide(s)."
    if (( ${#A_BANNIR[@]} == 0 )); then
        echo "  Rien à faire."
        exit 0
    fi
    if [[ "$ASSUME_YES" != "1" ]]; then
        echo
        if ! demander_oui "Bannir ces ${#A_BANNIR[@]} IP sur $(hostname) (blocage au pare-feu, réversible par --unban) ? [o/N] "; then
            echo "Annulé."; exit 0
        fi
    fi
    n_ok=0
    for ip in "${A_BANNIR[@]}"; do
        if BAN_NOTE="importé${ORIGINE:+ de $ORIGINE}" bash "$SELF_PATH" --ban "$ip" --yes >/dev/null 2>&1; then
            n_ok=$((n_ok + 1))
        else
            echo "  ${C_RED}ÉCHEC du bannissement de $ip${C_RESET} (relancer : nginx-log-audit.sh --ban $ip)"
        fi
    done
    echo "  ${C_GREEN}$n_ok IP bannie(s) sur $(hostname).${C_RESET}"
    exit 0
fi


# --- Light check of the initial setup (directories, firewall) if nginx-hardening.sh is present next to it ---
# Silent if all is in order, so as not to clutter a normal report - displays something only if
# a step is missing. If nginx-hardening.sh is not deployed next to this script, ignored without error.
SETUP_SCRIPT="$SCRIPT_DIR/nginx-hardening.sh"
if [[ -x "$SETUP_SCRIPT" ]]; then
    SETUP_CHECK_OUT=$(env -u NGINX_TOOLS_I18N "$SETUP_SCRIPT" --check --lang "${NGINX_TOOLS_I18N_LANGUE:-fr}" 2>/dev/null) || true
    if printf '%s\n' "$SETUP_CHECK_OUT" | grep_q '\[FAIL\]'; then
        echo
        echo "${C_YELLOW}ATTENTION : le setup initial semble incomplet — étapes en échec :${C_RESET}"
        printf '%s\n' "$SETUP_CHECK_OUT" | grep '\[FAIL\]'
        echo "${C_YELLOW}Voir : nginx-hardening.sh --check (ou --update pour corriger).${C_RESET}"
        echo
    fi
fi

# --- Application derriere nginx : profil apps/<nom>.conf, detecte ou force (--app=NOM, ou variable APP_PROFILE) ------
APPS_DIR="$SCRIPT_DIR/apps"
if [[ -r "$APPS_DIR/_profile.sh" ]]; then
    # shellcheck source=/dev/null  # bibliotheque apps/_profile.sh, livree a cote du programme
    . "$APPS_DIR/_profile.sh"
    charger_profil_app "$APPS_DIR" "$APP_FORCE" || exit 1
else
    APP_NAME="odoo"; APP_LABEL="Odoo"; ACCESS_LOGS="*-access.log"; ERROR_LOGS="*-error.log"
    CATCHALL_LOG="odoo-catchall-444.log"; APP_DETECTION="par défaut (dossier apps/ absent à côté du programme)"
fi
PROFIL_CATCHALL="$CATCHALL_LOG"          # nom de fichier du profil (le chemin complet est calcule plus bas)
log "Application : $APP_LABEL ($APP_DETECTION)"

# --- Auto-detection of the environment (Odoo: prod/dev according to the logs present) if not specified as argument ---
if [[ "$APP_NAME" != "odoo" ]]; then
    ENV="$APP_NAME"
elif [[ -z "$ENV" ]]; then
    TROUVES=()
    for env_candidat in prod dev lab; do
        [[ -r "/var/log/nginx/rencontres_linux_quebec_${env_candidat}-access.log" ]] && TROUVES+=("$env_candidat")
    done
    if (( ${#TROUVES[@]} == 1 )); then
        ENV="${TROUVES[0]}"
    elif (( ${#TROUVES[@]} > 1 )); then
        echo "ERREUR: plusieurs jeux de logs (${TROUVES[*]}) sont présents sur ce serveur — précisez explicitement" >&2
        echo "        '$0 ${TROUVES[0]}' ou '$0 ${TROUVES[1]}', l'auto-détection ne peut pas choisir pour vous." >&2
        exit 1
    else
        echo "ERREUR: aucun fichier /var/log/nginx/rencontres_linux_quebec_{prod,dev,lab}-access.log trouvé." >&2
        exit 1
    fi
    log "Environnement auto-detecte : $ENV (fichier trouvé dans /var/log/nginx/)"
fi

if [[ "$APP_NAME" == "odoo" ]]; then
    ACCESS_LOG="/var/log/nginx/rencontres_linux_quebec_${ENV}-access.log"
    ERROR_LOG="/var/log/nginx/rencontres_linux_quebec_${ENV}-error.log"
else
    # Autres applications : journaux du profil (premier motif ; ex. BBB : bigbluebutton.access.log, error.log).
    ACCESS_LOG="/var/log/nginx/${ACCESS_LOGS%% *}"
    ERROR_LOG="/var/log/nginx/${ERROR_LOGS%% *}"
fi
# Capteur catch-all : seulement si le profil en declare un (configuration nginx-odoo) ; vide sinon (ex. BBB).
if [[ -n "$PROFIL_CATCHALL" ]]; then CATCHALL_LOG="/var/log/nginx/$PROFIL_CATCHALL"; else CATCHALL_LOG=""; fi
STATE_DIR="${NGINX_LOG_AUDIT_STATE_DIR:-$HOME/.local/state/nginx-log-audit}"
mkdir -p "$STATE_DIR"

if [[ ! -r "$ACCESS_LOG" ]]; then
    echo "ERREUR: impossible de lire $ACCESS_LOG" >&2
    exit 1
fi

# --- --init-all : remplace les 3 logs (access/error/catchall) par la fusion de TOUTES leurs rotations connues
# (active + .N + .N.gz, decompressed on the fly) - the rest of the script then processes this merge exactly like
# le fichier actif normal, sans distinction. Force le comportement "fichier complet" (comme --init) : la position
# incrementale normale n'a pas de sens contre un fichier temporaire regenere a chaque appel.
ORIG_ACCESS_LOG="$ACCESS_LOG"
INIT_ALL_TMP_FILES=()
if [[ "$DO_INIT_ALL" == "1" ]]; then
    echo "--init-all : fusion de tous les fichiers de log disponibles (actifs + tournés + compressés) —"
    echo "peut prendre quelques secondes selon le volume d'historique présent sur ce serveur."
    echo

    MERGED_ACCESS="$STATE_DIR/.init-all-access.$$"
    mapfile -t ACCESS_FILES_USED < <(merge_all_rotations "$ACCESS_LOG" "$MERGED_ACCESS")
    INIT_ALL_TMP_FILES+=("$MERGED_ACCESS")
    if [[ ${#ACCESS_FILES_USED[@]} -eq 0 ]]; then
        echo "ERREUR: aucun fichier access log trouvé pour $ENV (même pas le fichier actif attendu)." >&2
        exit 1
    fi
    echo "Access log — ${#ACCESS_FILES_USED[@]} fichier(s) fusionné(s) :"
    printf '  - %s\n' "${ACCESS_FILES_USED[@]}"
    ACCESS_LOG="$MERGED_ACCESS"

    if [[ -r "$ERROR_LOG" || -r "$ERROR_LOG.1" ]]; then
        MERGED_ERROR="$STATE_DIR/.init-all-error.$$"
        mapfile -t ERROR_FILES_USED < <(merge_all_rotations "$ERROR_LOG" "$MERGED_ERROR")
        INIT_ALL_TMP_FILES+=("$MERGED_ERROR")
        if [[ ${#ERROR_FILES_USED[@]} -gt 0 ]]; then
            echo "Error log — ${#ERROR_FILES_USED[@]} fichier(s) fusionné(s) :"
            printf '  - %s\n' "${ERROR_FILES_USED[@]}"
            ERROR_LOG="$MERGED_ERROR"
        fi
    fi

    if [[ -r "$CATCHALL_LOG" || -r "$CATCHALL_LOG.1" ]]; then
        MERGED_CATCHALL="$STATE_DIR/.init-all-catchall.$$"
        mapfile -t CATCHALL_FILES_USED < <(merge_all_rotations "$CATCHALL_LOG" "$MERGED_CATCHALL")
        INIT_ALL_TMP_FILES+=("$MERGED_CATCHALL")
        if [[ ${#CATCHALL_FILES_USED[@]} -gt 0 ]]; then
            echo "Catch-all log — ${#CATCHALL_FILES_USED[@]} fichier(s) fusionné(s) :"
            printf '  - %s\n' "${CATCHALL_FILES_USED[@]}"
            CATCHALL_LOG="$MERGED_CATCHALL"
        fi
    fi
    echo

    trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
    DO_INIT=1
fi

# --- Enquete sur les IP suspectes (section [10] et --investigate) -----------------------------------------------
# Rassemble automatiquement les preuves qu'on collectait a la main (rafale, outil de script, double identite, DNS
# inverse d'hebergeur, faux moteur de recherche, fichiers sensibles, erreurs), les affiche une par une avec la commande
# equivalente, puis PROPOSE le bannissement (confirmation obligatoire, jamais automatique).
# Relance ce programme pour --ban ou --unban (questions de la section [10], des recidivistes et de --unban-check) :
# ALWAYS through "bash", so as not to depend on the file's execute permission (launched with "bash nginx-log-audit.sh"
# on a non-executable file, the direct call failed - "Permission denied" swallowed by the display filter -
# et l'echec arretait tout le rapport). En cas d'echec, la sortie complete est affichee.
relancer_action() {
    local out rc=0
    out=$(bash "$SELF_PATH" "$@" 2>&1) || rc=$?
    if (( rc == 0 )); then
        printf '%s\n' "$out" | sed -n '/Règle\|Déjà\|REFUSÉ\|Justification\|sauvegard\|mémoire\|permanente/p' | sed 's/^/      /'
    else
        echo "      ${C_RED}ÉCHEC de « $* » (code $rc) — sortie complète :${C_RESET}"
        printf '%s\n' "$out" | sed 's/^/        /'
    fi
    return 0
}
# Exclus du compte des pages (rafale) : fichiers statiques, et appels internes qu'une page DEJA ouverte fait d'elle-meme
# (Odoo back office: /web/dataset, /mail, /bus... - dozens per page, without the user changing page).
STATIC_RE='^/web/(assets|image|static|content|binary|dataset|action|webclient|bundle)/|/static/|/websocket|/longpolling|^/(mail|discuss|bus|html_editor|web_editor|hr_attendance|partner_autocomplete|calendar)/|^/website/(translations|snippet)|^/web/(manifest.webmanifest|service-worker.js)|\.(js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|map)(\?|$)'
# Sensitive on an Odoo site ONLY: /wp, /wordpress, xmlrpc.php... are normal pages under WordPress (same rule as apps/_profile.py cms():
# NGINX_TOOLS_CMS, /etc/default/nginx-tools-cms.conf "CMS=odoo|wordpress|auto", then a wp-config.php under /var/www, /srv, /usr/share/nginx or /opt).
cms_wordpress() {
    local choix="${NGINX_TOOLS_CMS:-}" fichier="${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/nginx-tools-cms.conf" base
    choix="${choix,,}"
    if [[ "$choix" != odoo && "$choix" != wordpress && -r "$fichier" ]]; then
        choix=$(sed -n 's/^[[:space:]]*CMS[[:space:]]*=[[:space:]]*["'"'"']\{0,1\}\([A-Za-z]*\).*/\1/p' "$fichier" | tail -1)
        choix="${choix,,}"
    fi
    [[ "$choix" == wordpress ]] && return 0
    [[ "$choix" == odoo ]] && return 1
    for base in /var/www /srv /usr/share/nginx /opt; do
        [[ -d "${APP_DETECT_ROOT:-}$base" ]] && [[ -n "$(find "${APP_DETECT_ROOT:-}$base" -maxdepth 4 -name wp-config.php -print -quit 2>/dev/null)" ]] && return 0
    done
    return 1
}
SENSITIVE_BASE='\.env|\.git/|phpmyadmin|\.aws/|\.ssh/|\.(bak|old|sql|swp)(\?|$)|/config\.(php|json|yml)|/server-status|/\.well-known/security|/_ignition|/debug/default'
SENSITIVE_WP='/wp-|wp-login|xmlrpc\.php|/wp(/|\?|$)|/wordpress(/|\?|$)'
SENSITIVE_CMS_BBB='/administrator(/|$)|/joomla|/drupal|/sites/default|/typo3|/magento|/prestashop|/bitrix|/umbraco|/ghost/|/user/login|/node/[0-9]+|/components/com_|/index\.php|\.(asp|aspx|jsp|cgi|php)(\?|$)|/admin/login|/wp-json|/typo3conf'
if [[ "$APP_NAME" == "bbb" ]]; then SENSITIVE_RE="$SENSITIVE_BASE|$SENSITIVE_WP|$SENSITIVE_CMS_BBB"      # BigBlueButton hosts no CMS: anything that falls under it is sensitive
elif cms_wordpress; then SENSITIVE_RE="$SENSITIVE_BASE"; else SENSITIVE_RE="$SENSITIVE_BASE|$SENSITIVE_WP"; fi
CLOUD_PTR_RE='ip-[0-9]{1,3}-[0-9]{1,3}-[0-9]{1,3}\.(eu|net|us)$|amazonaws\.com|googleusercontent\.com|compute\.|cloudapp\.|azure|ovh\.(net|com|ca)|hetzner|your-server\.de|digitalocean|linode|akamai|vultr|contabo|scaleway|oraclecloud|aliyun|alibaba|tencent|leaseweb|m247|choopa|hwclouds|kimsufi|hostinger|ionos'

# Field separator: ASCII character 31 (\037), NOT the tab - with IFS=$'\t', "read" merges the
# tabulations consecutives (la tabulation est un espace pour lui) et un champ vide ferait glisser tous les suivants.
# Une ligne par IP retenue : score_preliminaire, ip, total, max_pages_10s, fenetre, n_script, n_navigateur,
# n_familles, familles, n_erreurs, n_sensibles, codes, user-agents, exemples_sensibles. only_ip = ne traiter qu'elle.
scan_ips() {
    local file="$1" only_ip="${2:-}" min_prelim="${3:-2}"
    # Expressions regulieres passees par l'ENVIRONNEMENT, pas par -v : awk interprete les barres obliques inverses
    # of a -v value (gawk turns "\." into "." with a warning, silently widening the pattern).
    STATIC_RE="$STATIC_RE" SENSITIVE_RE="$SENSITIVE_RE" \
    awk -F'"' -v only="$only_ip" -v minp="$min_prelim" -v pb="$PAGE_BURST" '
    function family(ua,   l, t) {
        l = tolower(ua); gsub(/\+?https?:\/\/[^ ;)]*/, "", l)
        if (l ~ /googlebot|googleother|google-inspectiontool|google-extended|adsbot-google|mediapartners-google|storebot-google|apis-google/) return "Google"
        if (l ~ /gptbot|chatgpt-user|oai-searchbot/) return "OpenAI"
        if (l ~ /meta-externalagent|facebookexternalhit|facebookbot|meta-externalfetcher/) return "Meta"
        if (l ~ /bingbot|bingpreview|adidxbot|msnbot/) return "Microsoft"
        if (l ~ /perplexitybot|perplexity-user/) return "Perplexity"
        if (l ~ /claudebot|claude-user|claude-searchbot/) return "Anthropic"
        if (l ~ /applebot/) return "Apple"
        if (l ~ /yandex[a-z]*bot/) return "Yandex"
        if (match(l, /[a-z0-9_.-]*(bot|crawler|spider)[a-z0-9_-]*/)) { t = substr(l, RSTART, RLENGTH); if (t != "bot" && t != "bots" && t != "robot" && t != "robots") return t }
        return ""
    }
    function is_script(l) {
        return (l ~ /^(curl|wget|python-requests|python-httpx|python-urllib|go-http-client|aiohttp|scrapy|okhttp|libwww-perl|node-fetch|axios|java\/|php\/|ruby|httpclient|apache-httpclient)/ || l ~ /(^| )python\/[0-9]/)
    }
    BEGIN { static_re = ENVIRON["STATIC_RE"]; sens_re = ENVIRON["SENSITIVE_RE"] }
    {
        split($1, a, " "); ip = a[1]
        if (only != "" && ip != only) next
        if (!match($1, /\[[^]]+\]/)) next
        t = substr($1, RSTART + 1, RLENGTH - 2); bucket = substr(t, 1, 19)
        split($2, r, " "); path = r[2]
        split($3, st, " "); code = st[1]
        ua = $6; l = tolower(ua)
        total[ip]++; sc[ip SUBSEP code]++; uac[ip SUBSEP ua]++; urlc[ip SUBSEP substr(path, 1, 100)]++
        if (path !~ static_re) {
            k = ip SUBSEP bucket SUBSEP path
            if (!(k in seenp)) { seenp[k] = 1; kb = ip SUBSEP bucket; pc[kb]++
                if (pc[kb] > maxp[ip]) { maxp[ip] = pc[kb]; maxb[ip] = bucket } }
        }
        f = family(ua)
        if (is_script(l)) nscript[ip]++
        else if (f == "" && l ~ /mozilla\/5\.0/) nbrowser[ip]++
        if (f != "" && index("|" fams[ip] "|", "|" f "|") == 0) { fams[ip] = (fams[ip] == "" ? f : fams[ip] "|" f); nf[ip]++ }
        if (code ~ /^[45]/) nerr[ip]++
        if (path ~ sens_re) { nprobe[ip]++; if (nprobe[ip] <= 3) probes[ip] = probes[ip] (probes[ip] == "" ? "" : ", ") path }
    }
    END {
        for (k in sc)  { split(k, p, SUBSEP); codes[p[1]] = codes[p[1]] (codes[p[1]] == "" ? "" : ", ") sc[k] "x" p[2] }
        for (k in uac) { split(k, p, SUBSEP); uas[p[1]] = uas[p[1]] "\001" uac[k] "x " p[2] }
        for (k in urlc) { split(k, p, SUBSEP); urls[p[1]] = urls[p[1]] "\001" urlc[k] "x " p[2] }
        for (ip in total) {
            s = 0
            if (maxp[ip] >= pb) s++
            if (nscript[ip] > 0) s++
            if ((nscript[ip] > 0 && nbrowser[ip] > 0) || nf[ip] >= 2) s++
            if (nprobe[ip] >= 3) s++
            if (nerr[ip] >= 20 && nerr[ip] * 2 >= total[ip]) s++
            if (only == "" && s < minp) continue
            printf "%d\037%s\037%d\037%d\037%s\037%d\037%d\037%d\037%s\037%d\037%d\037%s\037%s\037%s\037%s\n", s, ip, total[ip], maxp[ip] + 0, maxb[ip],
                nscript[ip] + 0, nbrowser[ip] + 0, nf[ip] + 0, fams[ip], nerr[ip] + 0, nprobe[ip] + 0, codes[ip], uas[ip], probes[ip], urls[ip]
        }
    }' "$file" | sort -t$'\037' -k1,1nr -k3,3nr
}

ip_already_blocked() {
    local ip="$1"
    if command -v iptables >/dev/null 2>&1 && iptables -C INPUT -s "$ip" -j DROP 2>/dev/null; then echo "déjà banni (iptables)"; return 0; fi
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep_q -F "$ip"; then echo "déjà banni (ufw)"; return 0; fi
    if command -v ipset >/dev/null 2>&1; then
        local s
        for s in crowdsec-blocklist-v4 crowdsec-blocklist-v6; do
            if ipset test "$s" "$ip" >/dev/null 2>&1; then echo "déjà bloqué (liste CrowdSec)"; return 0; fi
        done
    fi
    return 1
}

# Affiche l'enquete complete d'une IP (preuves + commandes equivalentes), calcule le score final, puis propose le
# bannissement. $1 = ligne produite par scan_ips ; $2 = fichier analyse (pour les commandes equivalentes affichees).
# --- Owner of the address block of an IP (--investigate) ---
# apps/_reseau.py (shared with app-log-live.py): RDAP via https://rdap.org (which redirects to the right registry),
# otherwise the whois command. Only the investigated address is sent, and only with --investigate.
infos_reseau() {
    local ip="$1" ligne="" org net plage pays abus registre source
    if [[ -r "$APPS_DIR/_reseau.py" ]] && command -v python3 >/dev/null 2>&1; then
        if [[ "$VERBOSE" == "1" ]]; then     # --verbose is passed to the component: its commands (curl, whois) are displayed
            ligne=$(run python3 "$APPS_DIR/_reseau.py" --verbose --raw "$ip" 2>&3) || ligne=""
        else
            ligne=$(run python3 "$APPS_DIR/_reseau.py" --raw "$ip" 2>/dev/null) || ligne=""
        fi
    fi
    if [[ -z "$ligne" ]]; then
        echo "      Propriétaire du bloc d'adresses : inconnu (ni rdap.org joignable par curl/wget, ni commande whois)"
        return 0
    fi
    IFS=$'\037' read -r org net plage pays abus registre source <<< "$ligne"
    local genre="nom du réseau"
    if [[ -n "$org" ]]; then genre="organisation"; fi
    echo "      Propriétaire du bloc d'adresses : ${C_YELLOW}${org:-$net}${C_RESET} ($genre ; pas forcément un fournisseur d'accès)${pays:+ — pays $pays}"
    echo "        réseau ${net:-?}${plage:+ ($plage)} — source $source${registre:+ ($registre)}"
    if [[ -n "$abus" ]]; then echo "        signalement d'abus : $abus"; fi
}

investigate_and_propose() {
    local rec="$1" src="$2" scope="${3:-dans la fenêtre analysée}"
    local ip total maxp maxb urls hostile=0 n_url nscript nbrowser nf fams nerr nprobe codes uas probes
    IFS=$'\037' read -r _ ip total maxp maxb nscript nbrowser nf fams nerr nprobe codes uas probes urls <<< "$rec"
    # The address investigated is remembered: every check below must still work on it (see the coherence check before the
    # DNS lines at the end of this function).
    local ip_depart="$ip"
    ENQUETE_INCOHERENTE=0
    SIGNE_FORT=0
    local etapes="DNS inverse, connexions Odoo, capteur catch-all"
    if [[ -n "$INVESTIGATE_IP" ]]; then etapes="$etapes, propriétaire du bloc d'adresses"; fi
    progres "Enquête sur $ip : $etapes"
    local score=0 ok="${C_RED}[✓]${C_RESET}" no="[ ]" verified_engine=0 ptr fwd engines
    local -a motifs=()                 # clues retained: justification proposed if the ban is accepted (2.40)
    echo
    echo "  ▶ ${C_YELLOW}$ip${C_RESET} — $total requête(s) $scope"
    if [[ -n "$INVESTIGATE_IP" ]]; then infos_reseau "$ip"; fi
    echo "      Codes HTTP : $codes" | surligner
    echo "      User-Agents :"
    # Rapport normal : les 5 plus frequents (+ le nombre de ceux masques) ; --investigate : tous.
    local n_ua ua_max=5
    [[ -n "$INVESTIGATE_IP" ]] && ua_max=100000
    { printf '%s\n' "$uas" | tr '\001' '\n' | sed '/^$/d' | sort -t x -k1,1nr | head -n "$ua_max" | sed 's/^/        /'; } || true
    n_ua=$(printf '%s\n' "$uas" | tr '\001' '\n' | grep -c . || true)
    if (( n_ua > ua_max )); then echo "        (+$((n_ua - ua_max)) autre(s) User-Agent(s) — tous visibles avec : nginx-log-audit.sh --investigate $ip)"; fi
    # requested URLs: what the IP really did, to judge at a glance (e.g. "3x /events": nothing hostile).
    echo "      URL demandées :"
    { printf '%s\n' "$urls" | tr '\001' '\n' | sed '/^$/d' | sort -t x -k1,1nr | head -n "$ua_max" | sed 's/^/        /' | surligner; } || true
    n_url=$(printf '%s\n' "$urls" | tr '\001' '\n' | grep -c . || true)
    if (( n_url > ua_max )); then echo "        (+$((n_url - ua_max)) autre(s) URL — toutes visibles avec : nginx-log-audit.sh --investigate $ip)"; fi

    echo
    echo "      Indices :"
    if (( maxp >= PAGE_BURST )); then score=$((score+1)); hostile=$((hostile+1)); motifs+=("rafale de $maxp pages en 10 s"); echo "      $ok Rafale : $maxp pages distinctes en 10 s ($maxb""x) — un humain lit une page à la fois (assets exclus du compte)"
    else echo "      $no Rafale : au plus $maxp page(s) distincte(s) en 10 s (seuil : $PAGE_BURST)"; fi
    if (( nscript > 0 )); then score=$((score+1)); motifs+=("outil de script ($nscript requête(s))"); echo "      $ok Outil de script déclaré : $nscript requête(s) (bibliothèque HTTP, pas un navigateur)"
    else echo "      $no Outil de script : aucun"; fi
    if (( nscript > 0 && nbrowser > 0 )); then score=$((score+1)); motifs+=("double identité"); echo "      $ok Double identité : outil de script ET User-Agent de navigateur depuis la même IP (client automatisé qui change d'identité)"
    elif (( nf >= 2 )); then score=$((score+1)); motifs+=("double identité ($nf organisations de robots)"); echo "      $ok Double identité : se réclame de $nf organisations de robots (${fams//|/, })"
    else echo "      $no Double identité : non"; fi
    if (( nprobe >= 3 )); then score=$((score+1)); hostile=$((hostile+1)); SIGNE_FORT=1; motifs+=("$nprobe tentative(s) d'accès à des fichiers sensibles (ex. $probes)"); echo "      $ok Recherche de fichiers sensibles : $nprobe requête(s) (ex. $probes)"
    else echo "      $no Recherche de fichiers sensibles : ${nprobe} requête(s)"; fi
    if (( nerr >= 20 && nerr * 2 >= total )); then score=$((score+1)); hostile=$((hostile+1)); SIGNE_FORT=1; motifs+=("$nerr erreurs sur $total requêtes"); echo "      $ok Taux d'erreurs élevé : $nerr/$total (4xx/5xx/444)"
    else echo "      $no Taux d'erreurs : $nerr/$total"; fi

    ptr=$(run timeout --foreground 3 host "$ip" 2>/dev/null | awk '/pointer/{print $NF}' | sed 's/\.$//' | head -1) || true
    if [[ -z "$ptr" ]]; then
        ptr=$(run timeout --foreground 3 getent hosts "$ip" 2>/dev/null | awk '{print $2}' | head -1) || true
    fi
    if [[ -n "$ptr" ]] && printf '%s' "$ptr" | grep_q -iE "$CLOUD_PTR_RE" && ! printf '%s' "$ptr" | grep_q -i 'gae\.googleusercontent'; then
        score=$((score+1)); motifs+=("serveur loué ($ptr)"); echo "      $ok Serveur loué chez un hébergeur : $ptr (DNS inverse) — pas une connexion d'internaute"
    else
        echo "      $no Serveur loué : ${ptr:-aucun DNS inverse}"
    fi
    # Moteur de recherche annonce : double verification DNS (inverse PUIS directe, qui doit redonner la meme IP).
    if [[ "$fams" =~ (^|\|)(Google|Microsoft|Apple|Yandex)(\||$) ]]; then
        if [[ -n "$ptr" ]] && printf '%s' "$ptr" | grep_q -iE '(googlebot|google)\.com$|search\.msn\.com$|applebot\.apple\.com$|yandex\.(ru|net|com)$'; then
            fwd=$(run timeout --foreground 3 getent ahosts "$ptr" 2>/dev/null | awk '{print $1}' | sort -u) || true
            if printf '%s\n' "$fwd" | grep_q -xF "$ip"; then verified_engine=1; fi
        fi
        if [[ "$verified_engine" == "1" ]]; then
            echo "      ${C_GREEN}[=]${C_RESET} Moteur de recherche VÉRIFIÉ ($ptr ↔ $ip) — jamais proposé au bannissement"
        else
            engines=$(printf '%s\n' "${fams//|/$'\n'}" | grep -xE 'Google|Microsoft|Apple|Yandex' | paste -sd, - | sed 's/,/, /g') || true
            score=$((score+1)); hostile=$((hostile+1)); SIGNE_FORT=1; motifs+=("faux moteur de recherche ($engines)"); echo "      $ok Faux moteur de recherche : se dit robot de ${engines} mais la double vérification DNS (inverse puis directe) échoue"
        fi
    fi
    # Capteur catch-all (enquetes sur tout l'historique : --investigate, --unban-check) : une IP qui frappe le serveur
    # by its raw address or an unknown domain is almost always a scanner - a sign of hostility.
    if [[ -n "$CATCHALL_MERGED" && -s "$CATCHALL_MERGED" ]]; then
        local n_ca
        n_ca=$(awk -v ip="$ip" '$1 == ip' "$CATCHALL_MERGED" | grep -c . || true)
        if (( n_ca > 0 )); then
            hostile=$((hostile+1)); SIGNE_FORT=1; motifs+=("$n_ca tentative(s) au capteur catch-all")
            echo "      $ok Capteur catch-all : $n_ca tentative(s) par IP brute ou domaine inconnu (typique d'un scanner)"
        else
            echo "      $no Capteur catch-all : aucune tentative"
        fi
    fi
    echo
    # Indications (outside the score): session open in the back office, URL repeated in a loop.
    local n_bo top_n top_u logins=""
    n_bo=$(printf '%s\n' "$urls" | tr '\001' '\n' | awk '$2 ~ /^\/(web\/(dataset|action|webclient)|mail\/|discuss\/|bus\/)/ { s += $1 } END { print s + 0 }')
    read -r top_n top_u < <(printf '%s\n' "$urls" | tr '\001' '\n' | sed '/^$/d' | sort -t x -k1,1nr | head -1 | sed 's/x / /') || true
    top_n=${top_n:-0}
    charger_logins
    logins=$(logins_odoo "$ip")
    if [[ -n "$logins" ]]; then
        echo "      ${C_GREEN}[i] Connectée à Odoo avec un compte (journal, 100 jours) :${C_RESET}"
        printf '%s\n' "$logins" | sed 's/^/            /'
    fi
    if (( n_bo >= 20 )); then
        echo "      ${C_GREEN}[i] Session ouverte dans le back-office : $n_bo appel(s) internes (/web/dataset, /mail…) — un utilisateur"
        echo "          CONNECTÉ, pas un robot anonyme : vérifier de qui il s'agit avant tout bannissement.${C_RESET}"
    fi
    if (( total > 0 && top_n >= 100 && top_n * 2 >= total )); then
        echo "      ${C_YELLOW}[i] Répétition : $(( top_n * 100 / total )) % des requêtes sur une seule URL ($top_n x $top_u) —"
        echo "          plutôt une boucle d'un module ou d'un onglet resté ouvert qu'une attaque ; voir la console du navigateur${C_RESET}"
        echo "          ${C_YELLOW}de cet utilisateur (outils de développement, onglet Réseau).${C_RESET}"
    fi

    # Coherence check: the address must be the one that was investigated. A change would mean that the evidence and the
    # verdict below concern another address: no verdict then, and the lines "to verify" use the address that was asked for.
    if [[ "$ip" != "$ip_depart" ]]; then
        ENQUETE_INCOHERENTE=1
        echo "      ${C_RED}[FAIL] Enquête incohérente : l'adresse a changé pendant l'analyse ($ip_depart -> $ip). Aucun verdict : à relancer.${C_RESET}"
        ip="$ip_depart"
    fi
    echo "      Pour vérifier soi-même :"
    echo "        host $ip"
    echo "        grep -F \"$ip \" $src | awk -F'\"' '{print \$6}' | sort | uniq -c"
    echo

    local blocked prot
    if [[ "$INV_MODE" == "unban-check" ]]; then
        if [[ -n "$logins" ]]; then
            # Banned WHILE it logged in to Odoo with an account: ban to lift (volunteer, member).
            echo "      ${C_YELLOW}⚠ Cette IP bannie s'est connectée à Odoo avec un compte ($(printf '%s\n' "$logins" | head -1 | cut -d' ' -f1)) :${C_RESET}"
            echo "      ${C_YELLOW}  un utilisateur légitime — bannissement à lever.${C_RESET}"
            decide_unban "$ip" 0 0 "$verified_engine"
        else
            decide_unban "$ip" "$hostile" "$score" "$verified_engine"
        fi
        return 0
    fi
    if prot=$(protected_ip_reason "$ip"); then
        echo "      ${C_GREEN}→ Score $score/7 — IP protégée ($(printf '%s\n' "$prot" | head -1)) : jamais proposée au bannissement.${C_RESET}"
        return 0
    fi
    if [[ -n "$logins" ]]; then
        local compte surveille
        compte=$(printf '%s\n' "$logins" | head -1 | cut -d' ' -f1)
        surveille=$(comptes_surveilles | grep -xF -- "$compte" || true)
        if [[ -n "$surveille" ]]; then
            echo "      ${C_YELLOW}→ Score $score/7 — connectée à Odoo avec le compte $compte, SOUS SURVEILLANCE : jamais bannie automatiquement ;${C_RESET}"
            echo "      ${C_YELLOW}  enquête sur le compte et toutes ses adresses : web-monitor.py --investigate-user $compte${C_RESET}"
        else
            echo "      ${C_GREEN}→ Score $score/7 — connectée à Odoo avec le compte $compte : un compte n'est pas une preuve de bonne foi,${C_RESET}"
            echo "      ${C_GREEN}  mais l'adresse n'est jamais proposée au bannissement ; activité du compte : web-monitor.py --investigate-user $compte${C_RESET}"
        fi
        return 0
    fi
    if [[ "$verified_engine" == "1" ]]; then
        echo "      → Score $score/7 — moteur vérifié, aucune action."
        return 0
    fi
    if blocked=$(ip_already_blocked "$ip"); then
        echo "      → Score $score/7 — $blocked, aucune action nécessaire."
        return 0
    fi
    # Two families of clues: AUTOMATION (script tool, double identity, rented server) - a robot, often
    # legitimate or harmless (search robot, monitoring, aggregator) - and HOSTILITY (burst = abuse of
    # ressources, fichiers sensibles, erreurs en masse, faux moteur). Faux positif reel en PROD : 11.68.110.86, 3/7 avec
    # seulement des signes d'automatisation pour 3 visites de /events. Proposition de bannissement : seuil atteint ET
    # au moins un signe d'hostilite.
    echo "      Signes d'hostilité : $hostile (rafale, fichiers sensibles, erreurs, faux moteur, catch-all) ; d'automatisation : $((score - hostile)) (script, double identité, hébergeur)"
    if (( score < BAN_THRESHOLD )); then
        echo "      → Score $score/7 (seuil de proposition : $BAN_THRESHOLD) — à surveiller, pas de bannissement proposé."
        return 0
    fi
    if (( hostile == 0 )); then
        echo "      ${C_GREEN}→ Score $score/7 — signes d'AUTOMATISATION seulement, aucun signe d'hostilité : robot probablement${C_RESET}"
        echo "      ${C_GREEN}  inoffensif (vérifier les URL demandées ci-dessus), pas de bannissement proposé.${C_RESET}"
        return 0
    fi
    echo "      ${C_MAL}→ Score $score/7 : bannissement recommandé.${C_RESET}"
    PROP_RAISON="enquête $(date '+%Y-%m-%d %H:%M') : score $score/7, $hostile signe(s) d'hostilité — $(printf '%s ; ' "${motifs[@]}")"
    PROP_RAISON="${PROP_RAISON% ; }"
    confirm_and_ban "$ip"
}

# Propose le bannissement permanent d'une IP (terminal + root, confirmation obligatoire ; Ctrl-C = non) ; hors
# terminal, --no-prompt ou sans root : affiche seulement la commande. Utilisee par la section [10] et par --fail2ban.
confirm_and_ban() {
    local ip="$1"
    if [[ "$NO_PROMPT" != "1" && -t 0 && -t 1 && "$EUID" -eq 0 ]]; then
        echo
        echo "      Conséquence : TOUT le trafic de $ip sera bloqué au pare-feu, immédiatement et jusqu'à un --unban"
        echo "      (un vrai visiteur derrière cette IP serait bloqué aussi)."
        echo "      Réversible : nginx-log-audit.sh --unban $ip"
        echo
        # Ctrl-C = "no" and the report continues (see demander_oui): a stop here would lose these lines, the position of
        # lecture du journal etant deja enregistree a ce stade.
        if demander_oui "      Bannir $ip maintenant ? [o/N] "; then
            local justif
            echo "      Justification (enregistrée avec la date et l'heure ; Entrée accepte la proposition) :"
            justif=$(demander_texte "      > " "${PROP_RAISON:-}")
            echo
            relancer_action --ban "$ip" --yes --reason "${justif:-${PROP_RAISON:-}}"
        elif [[ "$DEMANDER_INTERROMPU" == "1" ]]; then
            echo "      (Ctrl-C : non banni, le rapport continue — plus tard : nginx-log-audit.sh --investigate $ip)"
        else
            echo "      Non banni."
        fi
        echo
    else
        echo "      Pour bannir (avec confirmation) : nginx-log-audit.sh --ban $ip"
    fi
}

# --- --unban-check : reevaluation d'un bannissement manuel avec la logique actuelle ---------------------------------
UNBAN_VERDICT=""
decide_unban() {
    local ip="$1" hostile="$2" score="$3" verified="$4" prot raison=""
    if [[ "$ENQUETE_INCOHERENTE" == "1" ]]; then
        UNBAN_VERDICT="incoherente"
        echo "      ${C_YELLOW}→ Aucun verdict : enquête incohérente, à relancer (nginx-log-audit.sh --investigate $ip).${C_RESET}"
        return 0
    fi
    if prot=$(protected_ip_reason "$ip"); then
        raison="IP protégée ($(printf '%s\n' "$prot" | head -1)) : bannie par erreur"
    elif [[ "$verified" == "1" ]]; then
        raison="moteur de recherche VÉRIFIÉ : le bannir le retire de l'indexation du site"
    elif (( hostile == 0 )); then
        raison="aucun signe d'hostilité (score $score/7, automatisation seulement) — voir les URL demandées"
    fi
    # A single sign of hostility that is only a burst of pages (no strong sign) is not enough to keep a ban: a browser or a
    # monitoring tool can load many pages in 10 seconds. The reader decides.
    if [[ -z "$raison" && "$hostile" == "1" && "$SIGNE_FORT" != "1" ]]; then
        UNBAN_VERDICT="verifier"
        echo "      ${C_YELLOW}→ À VÉRIFIER : un seul signe d'hostilité, une rafale de pages, sans signe fort (fichiers sensibles,"
        echo "        erreurs, faux moteur, capteur catch-all). Gardez-le seulement si vous reconnaissez cet outil.${C_RESET}"
        return 0
    fi
    if [[ -z "$raison" ]]; then
        UNBAN_VERDICT="garder"
        echo "      ${C_RED}→ Bannissement JUSTIFIÉ : $hostile signe(s) d'hostilité — le garder.${C_RESET}"
        return 0
    fi
    UNBAN_VERDICT="lever"
    echo "      ${C_GREEN}→ Levée RECOMMANDÉE : $raison.${C_RESET}"
    echo "        (Gardez-le si vous l'aviez banni pour une raison connue qui n'apparaît pas dans ces journaux.)"
    if [[ "$NO_PROMPT" != "1" && -t 0 && -t 1 && "$EUID" -eq 0 ]]; then
        if demander_oui "      Lever le bannissement de $ip maintenant ? [o/N] "; then
            relancer_action --unban "$ip" --yes --reason "réévaluation (--unban-check) : $raison"
            UNBAN_VERDICT="levé"
        elif [[ "$DEMANDER_INTERROMPU" == "1" ]]; then
            echo "      (Ctrl-C : bannissement conservé, la réévaluation continue)"
        else
            echo "      Bannissement conservé."
        fi
    else
        echo "      Pour lever (avec confirmation) : nginx-log-audit.sh --unban $ip"
    fi
}

# --- --unban-low-score : IP bannies (fail2ban ou pare-feu manuel) dont le score est SOUS le seuil de proposition ---------
# The score is recalculated like --investigate (read-only). An IP whose score is not readable is never proposed.
if [[ "$DO_UNBAN_LOW_SCORE" == "1" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: --unban-low-score nécessite root (sudo)." >&2
        exit 1
    fi
    echo "=============================================================="
    echo " IP BANNIES SOUS LE SEUIL DE PROPOSITION (score < $BAN_THRESHOLD/7)"
    echo "=============================================================="
    declare -A BAN_SOURCE=()
    declare -A SCORE_OF=()
    declare -a LOW_IPS=()
    if command -v fail2ban-client >/dev/null 2>&1 && run fail2ban-client ping >/dev/null 2>&1; then
        for j in $(run fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr ',' ' '); do
            for b in $(run fail2ban-client status "$j" 2>/dev/null | sed -n 's/.*Banned IP list:[[:space:]]*//p'); do
                BAN_SOURCE["$b"]="fail2ban:$j"
            done
        done
    fi
    mapfile -t MANUAL_BANS < <(list_manual_bans)
    for m in "${MANUAL_BANS[@]}"; do
        [[ -n "$m" && -z "${BAN_SOURCE[$m]:-}" ]] && BAN_SOURCE["$m"]="pare-feu"
    done
    if (( ${#BAN_SOURCE[@]} == 0 )); then
        echo "${C_GREEN}Aucune IP bannie (fail2ban ni bannissement manuel).${C_RESET}"
        exit 0
    fi
    echo "${#BAN_SOURCE[@]} IP bannie(s) : calcul du score de chacune (lecture seule)…"
    for ip in $(printf '%s\n' "${!BAN_SOURCE[@]}" | sort); do
        sc=$(bash "$SELF_PATH" --investigate "$ip" --no-prompt ${APP_FORCE:+--app "$APP_FORCE"} 2>/dev/null \
             | grep -o -m1 'Score [0-9]/7' | grep -o '[0-9]' || true)
        SCORE_OF["$ip"]="${sc:-?}"
        if [[ "$sc" =~ ^[0-9]+$ ]] && (( sc < BAN_THRESHOLD )); then
            LOW_IPS+=("$ip")
        fi
    done
    echo
    printf '  %-40s %-10s %s\n' "IP" "Score" "Banni par"
    for ip in $(printf '%s\n' "${!BAN_SOURCE[@]}" | sort); do
        printf '  %-40s %-10s %s\n' "$ip" "${SCORE_OF[$ip]}/7" "${BAN_SOURCE[$ip]}"
    done
    echo
    if (( ${#LOW_IPS[@]} == 0 )); then
        echo "${C_GREEN}Aucune IP bannie n'a un score sous $BAN_THRESHOLD/7.${C_RESET}"
        exit 0
    fi
    echo "${C_YELLOW}${#LOW_IPS[@]} IP bannie(s) sous le seuil de $BAN_THRESHOLD/7 : ${LOW_IPS[*]}${C_RESET}"
    interactif=0
    [[ "$NO_PROMPT" != "1" && -t 0 && -t 1 ]] && interactif=1
    for ip in "${LOW_IPS[@]}"; do
        src="${BAN_SOURCE[$ip]}"; sc="${SCORE_OF[$ip]}"
        if prot=$(protected_ip_reason "$ip"); then
            echo "  $ip : IP protégée ($(printf '%s\n' "$prot" | head -1)) — jamais levée par ce programme."
            continue
        fi
        ok=0
        if [[ "$ASSUME_YES" == "1" ]]; then
            ok=1
        elif (( interactif )); then
            if demander_oui "Débannir $ip (score $sc/7, banni par $src) ? [o/N] "; then ok=1; fi
        else
            echo "  $ip : non levée (aucun terminal interactif ; relancer avec --yes pour la lever sans question)."
            continue
        fi
        if (( ok )); then
            case "$src" in
                fail2ban:*)
                    jail="${src#fail2ban:}"
                    if run fail2ban-client set "$jail" unbanip "$ip" >/dev/null 2>&1; then
                        echo "  ${C_GREEN}✓ $ip levée (jail $jail).${C_RESET}"
                    else
                        echo "  ${C_RED}✗ échec de la levée de $ip dans le jail $jail.${C_RESET}"
                    fi
                    ;;
                *)
                    relancer_action --unban "$ip" --yes --reason "score $sc/7 sous le seuil (--unban-low-score)" || true
                    ;;
            esac
        fi
    done
    exit 0
fi

# --- --investigate IP : enquete complete sur TOUT l'historique disponible (actif + rotations + .gz) ------------------
if [[ -n "$INVESTIGATE_IP" ]]; then
    echo "=============================================================="
    echo " ENQUÊTE SUR $INVESTIGATE_IP (tout l'historique : $ENV, rotations et .gz compris)"
    echo "=============================================================="
    echo
    # 2.40: first WHEN and WHY the address was banned (firewall, fail2ban, CrowdSec) - even without any request to the site.
    afficher_bannissements "$INVESTIGATE_IP" "  "
    INV_SRC="$STATE_DIR/.investigate.$$"
    INIT_ALL_TMP_FILES+=("$INV_SRC")
    trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
    merge_all_rotations "${ORIG_ACCESS_LOG:-$ACCESS_LOG}" "$INV_SRC" > /dev/null
    CATCHALL_MERGED="$STATE_DIR/.investigate-catchall.$$"
    INIT_ALL_TMP_FILES+=("$CATCHALL_MERGED")
    [[ -n "$CATCHALL_LOG" ]] && { merge_all_rotations "$CATCHALL_LOG" "$CATCHALL_MERGED" > /dev/null 2>&1 || true; }
    INV_REC=$(scan_ips "$INV_SRC" "$INVESTIGATE_IP") || true
    if [[ -z "$INV_REC" ]]; then
        echo "Aucune requête de $INVESTIGATE_IP dans l'historique disponible du site ($ENV) : les requêtes refusées par nginx et"
        echo "celles du capteur catch-all n'y sont pas — voir « Bannissements » ci-dessus, ou : nginx-log-audit.sh --evidence $INVESTIGATE_IP"
        exit 0
    fi
    investigate_and_propose "$INV_REC" "$(dirname "${ORIG_ACCESS_LOG:-$ACCESS_LOG}")/$(basename "${ORIG_ACCESS_LOG:-$ACCESS_LOG}")*  (zgrep pour les .gz)" "dans tout l'historique disponible"
    exit 0
fi

# --- --unban-check : other points to re-check every day (read-only; this program runs them and shows the commands) ------
# Each check prints [OK], [ATTN] or [FAIL] and the command that shows the same thing by hand. The section can be copied
# as it is and sent for a review. Arguments: the manual bans examined (may be empty).
revue_controles() {
    local -a bans=("$@")
    local ip jails j n_att=0 acces_glob croise x nb
    local -a fichiers_acces=()
    acces_glob="$(dirname "${ORIG_ACCESS_LOG:-$ACCESS_LOG}")/$(basename "${ORIG_ACCESS_LOG:-$ACCESS_LOG}")*"
    echo
    echo "=============================================================="
    echo " AUTRES POINTS À RE-VÉRIFIER (contrôles lancés par ce programme, lecture seule)"
    echo "=============================================================="
    # 1) Team and protected addresses among the manual bans: a ban on one of them is an error to correct at once.
    echo "${C_BOLD}1) Adresses de l'équipe et lieux protégés parmi les bannissements manuels${C_RESET}"
    echo "   Commande : iptables -S INPUT | grep -- '-j DROP'"
    for ip in "${bans[@]}"; do
        if protected_ip_reason "$ip" >/dev/null 2>&1; then
            n_att=$((n_att + 1))
            echo "   ${C_RED}[ATTN]${C_RESET} $ip est bannie alors qu'elle est protégée : $(protected_ip_reason "$ip" | head -n 1)"
        fi
    done
    if (( n_att == 0 )); then echo "   ${C_GREEN}[OK]${C_RESET} aucune adresse protégée parmi les ${#bans[@]} bannissement(s) manuel(s)"; fi
    # 2) fail2ban: the jails that ban automatically (refusals, failed logins, catch-all)
    echo
    echo "${C_BOLD}2) Jails fail2ban${C_RESET}"
    echo "   Commande : fail2ban-client status"
    jails=""
    if command -v fail2ban-client >/dev/null 2>&1; then
        jails=$(run fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr -d ' ' | tr ',' ' ') || jails=""
    fi
    if [[ -n "$jails" ]]; then
        echo "   ${C_GREEN}[OK]${C_RESET} jails actives : $jails"
        for j in $jails; do
            nb=$(run fail2ban-client status "$j" 2>/dev/null | sed -n 's/.*Currently banned:[[:space:]]*//p') || nb=""
            echo "   [i] $j : ${nb:-?} IP bannie(s) en ce moment (commande : fail2ban-client status $j)"
        done
    else
        echo "   ${C_RED}[FAIL]${C_RESET} fail2ban inaccessible ou sans jail : les bannissements automatiques ne sont pas appliqués"
    fi
    # 3) Addresses refused by nginx AND served normal pages (200): a visitor who got a refusal (rule 6 or 9 of
    #    securite-commune.conf, for example) is a false positive to fix, not a scanner.
    echo
    echo "${C_BOLD}3) Adresses refusées par nginx et servies normalement (200) : faux positif possible${C_RESET}"
    echo "   Commande : grep -F \"IP \" /var/log/nginx/blocked-probes.log"
    if compgen -G "/var/log/nginx/blocked-probes.log*" >/dev/null && compgen -G "$acces_glob" >/dev/null; then
        mapfile -t fichiers_acces < <(compgen -G "$acces_glob")
        croise=$(comm -12 <(lire_chrono "${fichiers_acces[@]}" 2>/dev/null | awk '$9 == 200 { print $1 }' | sort -u) \
                          <(lire_chrono /var/log/nginx/blocked-probes.log* 2>/dev/null | awk '{ print $1 }' | sort -u) | head -n 10) || croise=""
        if [[ -n "$croise" ]]; then
            echo "   ${C_RED}[ATTN]${C_RESET} ces adresses ont reçu des refus ET des pages 200 (10 maximum) :"
            while IFS= read -r x; do
                [[ -z "$x" ]] && continue
                echo "       $x : $(urls_refusees "$x" 2 | awk -F'\t' '{ printf "%sx %s ; ", $1, $2 }')"
            done <<< "$croise"
        else
            echo "   ${C_GREEN}[OK]${C_RESET} aucune adresse refusée n'a reçu de page 200"
        fi
    else
        echo "   [i] journal blocked-probes.log ou journal d'accès absent : rien à comparer"
    fi
    # 4) Logs used by the checks above (fail2ban history and refusals), readable?
    echo
    echo "${C_BOLD}4) Journaux utilisés par ces contrôles${C_RESET}"
    echo "   Commande : ls -l /var/log/fail2ban.log* /var/log/nginx/blocked-probes.log*"
    if compgen -G "${FAIL2BAN_LOG_FILE:-/var/log/fail2ban.log}*" >/dev/null; then
        echo "   ${C_GREEN}[OK]${C_RESET} historique fail2ban présent (rotations comprises)"
    else
        echo "   ${C_RED}[ATTN]${C_RESET} historique fail2ban introuvable : l'origine des anciens bannissements ne peut plus être vérifiée"
    fi
    if compgen -G "/var/log/nginx/blocked-probes.log*" >/dev/null; then
        echo "   ${C_GREEN}[OK]${C_RESET} journal blocked-probes.log présent"
    else
        echo "   ${C_YELLOW}[ATTN]${C_RESET} blocked-probes.log absent : les refus des règles 4 à 11 ne sont pas journalisés"
    fi
    # 5) Bans to look at by hand, with the commands to run (paste their output for a review).
    echo
    echo "${C_BOLD}5) Bannissements à vérifier à la main (commandes à lancer)${C_RESET}"
    if (( ${#REVOIR_IPS[@]} == 0 )); then
        echo "   ${C_GREEN}[OK]${C_RESET} aucun bannissement à revoir"
    else
        for ip in "${REVOIR_IPS[@]}"; do
            echo "   ${C_YELLOW}$ip${C_RESET}"
            echo "       nginx-log-audit.sh --investigate $ip --no-prompt"
            echo "       grep -h -F \"$ip\" ${FAIL2BAN_LOG_FILE:-/var/log/fail2ban.log}*"
        done
    fi
    echo
    echo "   Pour une relecture : copiez les sections 1 à 5 de ce rapport."
}

# --- --unban-check : reevalue chaque bannissement manuel avec la logique ACTUELLE, sur tout l'historique --------------
if [[ "$DO_UNBAN_CHECK" == "1" ]]; then
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: --unban-check nécessite root (lecture des règles du pare-feu)." >&2
        exit 1
    fi
    echo "=============================================================="
    echo " RÉÉVALUATION DES BANNISSEMENTS MANUELS ($ENV — tout l'historique, rotations et .gz compris)"
    echo "=============================================================="
    mapfile -t BANS < <(list_manual_bans)
    if (( ${#BANS[@]} == 0 )); then
        echo "${C_GREEN}Aucun bannissement manuel en place (iptables INPUT « -s IP -j DROP », ufw « deny from »).${C_RESET}"
        revue_controles
        exit 0
    fi
    echo "${#BANS[@]} bannissement(s) manuel(s) à réévaluer avec la logique actuelle (bannissement justifié seulement"
    echo "s'il y a au moins un signe d'HOSTILITÉ : rafale, fichiers sensibles, erreurs en masse, faux moteur, capteur catch-all)."
    INV_SRC="$STATE_DIR/.unban-check.$$"
    CATCHALL_MERGED="$STATE_DIR/.unban-check-catchall.$$"
    INIT_ALL_TMP_FILES+=("$INV_SRC" "$CATCHALL_MERGED")
    trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
    merge_all_rotations "${ORIG_ACCESS_LOG:-$ACCESS_LOG}" "$INV_SRC" > /dev/null
    [[ -n "$CATCHALL_LOG" ]] && { merge_all_rotations "$CATCHALL_LOG" "$CATCHALL_MERGED" > /dev/null 2>&1 || true; }
    INV_MODE="unban-check"
    n_lever=0; n_garder=0; n_trace=0; n_leve=0; n_verif=0; n_incoh=0; i=0
    REVOIR_IPS=()
    for bip in "${BANS[@]}"; do
        i=$((i + 1))
        IFS=$'\t' read -r quand justif origine < <(awk -F'\t' -v ip="$bip" '$3 == ip && $2 == "banni" { d = $1; r = (NF >= 4) ? $4 : ""; o = (NF >= 5) ? $5 : "" }
                                                     $3 == ip && $2 == "justifie" && NF >= 4 { r = $4 " (ajoutée le " $1 ")" }
                                                     END { printf "%s\t%s\t%s\n", d, r, o }' "$BAN_LOG" 2>/dev/null) || { quand=""; justif=""; origine=""; }
        echo
        # (No "${quand:-...}" here: when the variable is set, this form returns it ITSELF - date doubled.)
        if [[ -n "$quand" ]]; then quand="le $quand"; else quand="(date inconnue : bannissement antérieur à la 1.34, ou posé à la main)"; fi
        echo "--- [$i/${#BANS[@]}] $bip — banni $quand${origine:+ par $origine}"
        if [[ -n "$justif" && "$justif" != "-" ]]; then echo "    Justification : $justif"
        else echo "    Justification : non enregistrée (bannissement antérieur à la 2.40) ; pour l'ajouter : nginx-log-audit.sh --ban $bip --reason \"…\""; fi
        UNBAN_VERDICT=""
        rec=$(scan_ips "$INV_SRC" "$bip") || true
        if [[ -n "$rec" ]]; then
            investigate_and_propose "$rec" "$(dirname "$ORIG_ACCESS_LOG")/$(basename "$ORIG_ACCESS_LOG")*" "dans tout l'historique disponible"
        else
            n_ca=$(awk -v ip="$bip" '$1 == ip' "$CATCHALL_MERGED" 2>/dev/null | grep -c . || true)
            if (( n_ca > 0 )); then
                echo "  ▶ ${C_YELLOW}$bip${C_RESET} — aucune requête sur le site, mais $n_ca tentative(s) sur le capteur catch-all"
                echo "      URL tentées :"
                { awk -F'"' -v ip="$bip" '{ split($1, a, " ") } a[1] == ip { split($2, r, " "); print substr(r[2], 1, 100) }' "$CATCHALL_MERGED" \
                    | sort | uniq -c | sort -rn | head -n 8 | sed -E 's/^ *([0-9]+) /\1x /; s/^/        /'; } || true
                UNBAN_VERDICT="garder"
                echo "      ${C_RED}→ Bannissement JUSTIFIÉ : scanner (accès par IP brute ou domaine inconnu) — le garder.${C_RESET}"
            elif refus=$(urls_refusees "$bip" 3) && [[ -n "$refus" ]]; then
                # Refused requests (blocked-probes.log) are certain evidence: they are what the nginx-blocked-probes jail counts.
                echo "  ▶ ${C_YELLOW}$bip${C_RESET} — aucune requête sur le site, mais requêtes REFUSÉES par nginx (blocked-probes.log) :"
                echo "      URL refusées :"
                awk -F'\t' '{ printf "        %sx %s\n", $1, $2 }' <<< "$refus"
                UNBAN_VERDICT="garder"
                echo "      ${C_RED}→ Bannissement JUSTIFIÉ : requêtes répétées refusées par les règles de sécurité — le garder.${C_RESET}"
            else
                # No evidence left in the logs: show the ban history (fail2ban jails, ban log) instead of a bare "no trace".
                UNBAN_VERDICT="trace"
                echo "      Aucune requête de $bip dans les journaux du site, du capteur catch-all ni de blocked-probes.log."
                afficher_bannissements "$bip" "      "
                echo "      Réévaluation impossible : décision manuelle (--unban $bip pour lever)."
            fi
        fi
        case "$UNBAN_VERDICT" in
            lever) n_lever=$((n_lever + 1)) ;; levé) n_lever=$((n_lever + 1)); n_leve=$((n_leve + 1)) ;;
            garder) n_garder=$((n_garder + 1)) ;;
            verifier) n_verif=$((n_verif + 1)); REVOIR_IPS+=("$bip") ;;
            incoherente) n_incoh=$((n_incoh + 1)); REVOIR_IPS+=("$bip") ;;
            *) n_trace=$((n_trace + 1)); REVOIR_IPS+=("$bip") ;;
        esac
    done
    echo
    echo "=============================================================="
    echo " BILAN : ${#BANS[@]} bannissement(s) — $n_garder justifié(s), $n_lever levée(s) recommandée(s)$([[ $n_leve -gt 0 ]] && echo " (dont $n_leve effectuée(s))"), $n_trace sans trace, $n_verif à vérifier, $n_incoh incohérente(s)"
    echo "=============================================================="
    revue_controles "${BANS[@]}"
    exit 0
fi

# --- Public IP and operating system, for the report header ---
# Short timeout (3s): must never block the script for long if the server has no outbound access or if the
# IP detection service is unavailable.
log "curl -s --max-time 3 https://icanhazip.com"
PUBLIC_IP=$(run curl -s --max-time 3 https://icanhazip.com 2>/dev/null | tr -d '[:space:]') || true
# Validation de forme (IPv4 ou IPv6 grossier) : curl peut renvoyer une page d'erreur non vide (proxy, portail
# captive portal, network restriction) rather than a real connection error - a non-empty text is not necessarily an IP.
if [[ "$PUBLIC_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$PUBLIC_IP" =~ ^[0-9a-fA-F:]+$ ]]; then
    # Memorisee pour protected_ip_reason (y compris lors d'un --ban ulterieur, qui ne refait pas cette requete).
    echo "$PUBLIC_IP" > "$STATE_DIR/public-ip" 2>/dev/null || true
fi
# Requetes de NOS programmes (2.7) : boucle locale, adresses de ce serveur (dont l'IP publique), User-Agent marque
# "app-health-check/". Excluded from the report sections and from --stats: these are voluntary tests (traversal test,
# curl User-Agent, database manager...), not visitors nor attacks. The ERROR log is not
# pas filtre : si l'application tombe, les erreurs provoquees par le test de sante sont justement le signal utile.
NOS_IPS="127.0.0.1 ::1 $(hostname -I 2>/dev/null || true)"
[[ "$PUBLIC_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$PUBLIC_IP" =~ ^[0-9a-fA-F:]+$ ]] && NOS_IPS="$NOS_IPS $PUBLIC_IP"
NOS_PROGRAMMES_RE="^($(tr ' ' '\n' <<< "$NOS_IPS" | grep . | sort -u | sed 's/[.]/\\./g' | paste -sd'|')) |app-health-check/"
filtrer_nos_programmes() { grep -vE "$NOS_PROGRAMMES_RE" || true; }
compter_nos_programmes() { grep -cE "$NOS_PROGRAMMES_RE" || true; }
if ! [[ "$PUBLIC_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$PUBLIC_IP" =~ ^[0-9a-fA-F:]+$ ]]; then
    PUBLIC_IP="indisponible (pas d'accès sortant, ou réponse inattendue du service de détection)"
fi

if [[ -r /etc/os-release ]]; then
    # shellcheck source=/dev/null  # fichier systeme lu a l'execution, pas un fichier du projet
OS_NAME=$(. /etc/os-release && echo "$PRETTY_NAME") || true
    [[ -z "$OS_NAME" ]] && OS_NAME="$(uname -sr)"
else
    OS_NAME="$(uname -sr)"
fi

# --- Date of the last execution (before updating it to the current date/time) ---
LASTRUN_FILE="$STATE_DIR/${ENV}-lastrun"
LASTRUN_PREVIOUS="jamais executee avant"
[[ -f "$LASTRUN_FILE" ]] && LASTRUN_PREVIOUS=$(cat "$LASTRUN_FILE")
date '+%Y-%m-%d %H:%M:%S %Z' > "$LASTRUN_FILE"

# Displays the lines added to $1 since the last call (position kept in $2), UNLESS --init is active:
# in that case, the whole file is displayed (last_pos forced to 0), and the position is still updated at the
# end - the following calls become incremental normally again.
new_lines() {
    local file="$1" state_file="$2" total_lines last_pos
    total_lines=$(wc -l < "$file")
    last_pos=0
    if [[ "$DO_INIT" != "1" && -f "$state_file" ]]; then
        last_pos=$(cat "$state_file")
    fi
    (( last_pos > total_lines )) && last_pos=0
    if (( total_lines > last_pos )); then
        tail -n "+$((last_pos + 1))" "$file"
    fi
    echo "$total_lines" > "$state_file"
}

# Returns only the lines of $1 whose nginx timestamp falls within the last $2 hours. Does
# NEVER touch the incremental position files (STATE_DIR/*.pos): --last is a one-off query on a
# time window, independent of the "new since the last call" tracking. Uses mawk (not gawk) + "date -f -"
# to convert all the dates in ONE PASS (fast even on tens of thousands of lines), rather than
# a call to "date" per line (too slow). A line whose date cannot be extracted (very rare, corrupted
# log) gets epoch 0 (1970) - it is therefore silently excluded from any recent window rather than
# faire echouer le script.
filter_last_hours() {
    local file="$1" hours="$2" cutoff dates_tmp epochs_tmp
    cutoff=$(date -d "-${hours} hours" +%s)
    dates_tmp="$STATE_DIR/.tmp_dates.$$"
    epochs_tmp="$STATE_DIR/.tmp_epochs.$$"
    awk '
    {
        line = $0
        if (match(line, /\[[0-9]{2}\/[A-Za-z]{3}\/[0-9]{4}:[0-9]{2}:[0-9]{2}:[0-9]{2} [+-][0-9]{4}\]/)) {
            datestr = substr(line, RSTART+1, RLENGTH-2)
            split(datestr, a, "/")
            day=a[1]; mon=a[2]; rest=a[3]
            split(rest, b, ":")
            year=b[1]; hh=b[2]; mi=b[3]
            split(b[4], c, " ")
            ss=c[1]; tz=c[2]
            printf "%s %s %s %s:%s:%s %s\n", day, mon, year, hh, mi, ss, tz
        } else {
            print "1 Jan 1970 00:00:00 +0000"
        }
    }' "$file" > "$dates_tmp"
    date -f "$dates_tmp" +%s 2>/dev/null > "$epochs_tmp"
    paste -d'\t' "$epochs_tmp" "$file" | awk -F'\t' -v c="$cutoff" '$1+0 >= c {sub($1"\t","",$0); print}'
    rm -f "$dates_tmp" "$epochs_tmp"
}

echo "=============================================================="
echo " Rapport nginx — $ENV — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo " IP publique de ce serveur : $PUBLIC_IP"
echo " Système d'exploitation    : $OS_NAME"
if [[ -n "$LAST_HOURS" ]]; then
    echo " (--last ${LAST_HOURS}h actif : uniquement les entrées des $LAST_HOURS dernières heures, TOUTES sections)"
elif [[ "$DO_INIT" == "1" ]]; then
    echo " (--init actif : historique COMPLET du fichier, pas seulement le delta)"
else
    echo " (lignes nouvelles depuis la dernière exécution seulement)"
fi
echo " Dernière exécution : $LASTRUN_PREVIOUS"
echo "=============================================================="

log "Fichier access log : $ACCESS_LOG"
if [[ -n "$LAST_HOURS" ]]; then
    log "filter_last_hours \"$ACCESS_LOG\" $LAST_HOURS"
    ACCESS_NEW=$(filter_last_hours "$ACCESS_LOG" "$LAST_HOURS")
    # --stats must read this same filtered subset, not the complete file: written to a temporary file
    # pour que les commandes awk/grep de --stats (qui prennent un CHEMIN de fichier, pas une variable) le lisent.
    STATS_SOURCE_FILE="$STATE_DIR/.stats_source.$$"
    printf '%s\n' "$ACCESS_NEW" > "$STATS_SOURCE_FILE"
    INIT_ALL_TMP_FILES+=("$STATS_SOURCE_FILE")
    trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
else
    ACCESS_NEW=$(new_lines "$ACCESS_LOG" "$STATE_DIR/${ENV}-access.pos")
    STATS_SOURCE_FILE="$ACCESS_LOG"
fi
N_NOS_PROGRAMMES=$(printf '%s\n' "$ACCESS_NEW" | compter_nos_programmes)
ACCESS_NEW=$(printf '%s\n' "$ACCESS_NEW" | filtrer_nos_programmes)
if (( N_NOS_PROGRAMMES > 0 )); then
    echo
    echo "($N_NOS_PROGRAMMES requête(s) de nos propres programmes exclues de ce rapport : boucle locale, adresses de ce"
    echo " serveur, User-Agent app-health-check — tests volontaires, pas des visiteurs ni des attaques.)"
fi

echo
progres "Section [1] : 403 (bad bot) par User-Agent, fréquence"
echo "--- [1] 403 (bad bot) par User-Agent, fréquence ---"
# shellcheck disable=SC2016  # affiche la commande awk TELLE QUELLE : ses $ ne doivent pas etre remplaces
log 'awk -F"\"" '"'"'$3 ~ /^ 403 /{print $6}'"'"' | sort | uniq -c | sort -rn'
R1=$(printf '%s\n' "$ACCESS_NEW" | awk -F'"' '$3 ~ /^ 403 /{print $6}' | sort | uniq -c | sort -rn)
if [[ -z "$R1" ]]; then echo "${C_GREEN}RIEN${C_RESET}"; else echo "$R1"; fi

echo
progres "Section [2] : 405 (méthode HTTP refusee)"
echo "--- [2] 405 (méthode HTTP refusee) ---"
log 'grep '"'"'" 405 '"'"''
R2=$(printf '%s\n' "$ACCESS_NEW" | grep '" 405 ' || true)
if [[ -z "$R2" ]]; then echo "${C_GREEN}RIEN${C_RESET}"; else printf '%s\n' "$R2" | surligner; fi

echo
progres "Section [3] : 444 dans le log nommé (pas le catch-all)"
echo "--- [3] 444 dans le log nommé (pas le catch-all) ---"
log 'grep '"'"'" 444 '"'"''
R3=$(printf '%s\n' "$ACCESS_NEW" | grep '" 444 ' || true)
if [[ -z "$R3" ]]; then echo "${C_GREEN}RIEN${C_RESET}"; else printf '%s\n' "$R3" | surligner; fi

echo
progres "Section [4] : 404 correspondant a la règle de traversee (%2e%2e, ../, ..\\)"
echo "--- [4] 404 correspondant a la règle de traversee (%2e%2e, ../, ..\\) ---"
log 'grep -E "\"(GET|POST|HEAD) [^\"]*(%2e%2e|\.\./|\.\.\\\\)"'
R4=$(printf '%s\n' "$ACCESS_NEW" | grep -E '"(GET|POST|HEAD) [^"]*(%2e%2e|\.\./|\.\.\\\\)' || true)
if [[ -z "$R4" ]]; then echo "${C_GREEN}RIEN${C_RESET}"; else printf '%s\n' "$R4" | surligner; fi

echo
progres "Section [5] : 429 (limitation de debit) par IP, fréquence"
echo "--- [5] 429 (limitation de debit) par IP, fréquence ---"
# shellcheck disable=SC2016  # affiche la commande awk TELLE QUELLE : ses $ ne doivent pas etre remplaces
log 'awk -F"\"" '"'"'$3 ~ /^ 429 /{print $1}'"'"' | awk '"'"'{print $1}'"'"' | sort | uniq -c | sort -rn'
R5=$(printf '%s\n' "$ACCESS_NEW" | awk -F'"' '$3 ~ /^ 429 /{print $1}' | awk '{print $1}' | sort | uniq -c | sort -rn)
if [[ -z "$R5" ]]; then
    echo "${C_GREEN}RIEN${C_RESET}"
else
    echo "${C_YELLOW}$R5${C_RESET}"
    echo "Note : vérifier si une de ces IP devrait figurer dans \$is_trusted_ip (conf.d/odoo-global.conf) — un usage"
    echo "       normal et intensif du backend Odoo par un compte connu peut declencher cette limite par erreur."
fi

echo
progres "Section [6] : 5xx (erreurs serveur — probablement Odoo, pas nginx)"
echo "--- [6] 5xx (erreurs serveur — probablement Odoo, pas nginx) ---"
log 'grep -E "\" 5[0-9]{2} "'
R6=$(printf '%s\n' "$ACCESS_NEW" | grep -E '" 5[0-9]{2} ' || true)
if [[ -z "$R6" ]]; then echo "${C_GREEN}RIEN${C_RESET}"; else printf '%s\n' "$R6" | surligner; fi

echo
progres "Section [7] : Erreurs upstream (error.log)"
echo "--- [7] Erreurs upstream (error.log) ---"
UPSTREAM_DOWN=""
if [[ -r "$ERROR_LOG" ]]; then
    log "tail incrémental sur $ERROR_LOG, recherche de 'connect() failed'"
    ERROR_NEW=$(new_lines "$ERROR_LOG" "$STATE_DIR/${ENV}-error.pos")
    UPSTREAM_DOWN=$(printf '%s\n' "$ERROR_NEW" | grep "connect() failed" || true)
    if [[ -n "$UPSTREAM_DOWN" ]]; then
        echo "${C_RED}ATTENTION — upstream injoignable (Odoo ou son worker gevent down au moment de la requête) :${C_RESET}"
        echo "${C_RED}$UPSTREAM_DOWN${C_RESET}"
    fi
    OTHER_ALL=$(printf '%s\n' "$ERROR_NEW" | grep -v "connect() failed" || true)
    # Refusals WANTED by the configuration: "access forbidden by rule" (deny: site restricted by IP, e.g. DEV) and
    # "limiting requests" (rate limiting, counted in [429]) - summarized below, NOT listed as errors.
    REFUS_REGLE=$(printf '%s\n' "$OTHER_ALL" | grep "access forbidden by rule" || true)
    LIMITES_DEBIT=$(printf '%s\n' "$OTHER_ALL" | grep "limiting requests" || true)
    OTHER_ERRORS=$(printf '%s\n' "$OTHER_ALL" | grep -v -e "access forbidden by rule" -e "limiting requests" || true)
    OTHER_COUNT=$(printf '%s\n' "$OTHER_ERRORS" | grep -c . || true)
    if [[ -z "$UPSTREAM_DOWN" && "$OTHER_COUNT" -eq 0 ]]; then
        echo "${C_GREEN}RIEN${C_RESET}"
    elif [[ "$OTHER_COUNT" -gt 0 ]]; then
        echo "${C_YELLOW}$OTHER_ERRORS${C_RESET}"
    fi
    N_REFUS_REGLE=$(printf '%s\n' "$REFUS_REGLE" | grep -c . || true)
    if (( N_REFUS_REGLE > 0 )); then
        CLIENTS_REFUSES=$(printf '%s\n' "$REFUS_REGLE" | sed -n 's/.*client: \([^,]*\),.*/\1/p' | sort | uniq -c | sort -rn | head -3 \
            | awk '{ a[NR] = $2 " (" $1 ")" } END { for (i = 1; i <= NR; i++) printf "%s%s", a[i], (i < NR ? ", " : "") }')
        echo "  ${N_REFUS_REGLE} refus par règle d'accès (access forbidden by rule) — attendu : accès restreint par IP ; clients les plus actifs : ${CLIENTS_REFUSES}"
    fi
    N_LIMITES_DEBIT=$(printf '%s\n' "$LIMITES_DEBIT" | grep -c . || true)
    if (( N_LIMITES_DEBIT > 0 )); then
        echo "  ${N_LIMITES_DEBIT} requête(s) freinée(s) par la limitation de débit (voir [429])"
    fi
else
    echo "ATTENTION: $ERROR_LOG introuvable ou illisible."
fi

echo
progres "Section [8] : Capteur default_server (catch-all, tous domaines confondus)"
echo "--- [8] Capteur default_server (catch-all, tous domaines confondus) ---"
if [[ -r "$CATCHALL_LOG" ]]; then
    log "tail incrémental sur $CATCHALL_LOG"
    CATCHALL_NEW=$(new_lines "$CATCHALL_LOG" "$STATE_DIR/catchall.pos" | filtrer_nos_programmes)
    COUNT=$(printf '%s\n' "$CATCHALL_NEW" | grep -c . || true)
    echo "$COUNT nouvelle(s) tentative(s) depuis le dernier passage."
    if (( COUNT > 0 )); then
        echo "Top 5 IP :"
        printf '%s\n' "$CATCHALL_NEW" | awk '{print $1}' | sort | uniq -c | sort -rn | head -5 \
            | awk -v m="$C_MAL" -v r="$C_RESET" '{ printf "%8s %s%s%s\n", $1, m, $2, r }' || true
    fi
else
    if [[ -z "$CATCHALL_LOG" ]]; then
        echo "Sans objet : pas de capteur catch-all dans la configuration de $APP_LABEL."
    else
        echo "ATTENTION: $CATCHALL_LOG introuvable ou illisible — capteur peut-être pas encore deploye sur ce serveur."
    fi
fi
echo

# --- [9] IP presenting ITSELF as SEVERAL robots of different organizations (probable identity spoofing) ---
# Only the User-Agents that declare themselves robots (Googlebot, GPTBot, SemrushBot...) count, grouped by family
# (organisation) : Googlebot, Googlebot-Image et GoogleOther forment UNE famille (Google), GPTBot, ChatGPT-User et
# OAI-SearchBot another (OpenAI), etc. An IP claiming to belong to several families at once has no
# legitimate explanation: no organization operates the robots of another - original case of this section, 11.55.161.77
# (Googlebot, GPTBot, ChatGPT-User, PerplexityBot from the same GCP VM, to look for sensitive files).
# BROWSER User-Agents are deliberately ignored: behind a NAT (company, university, mobile
# operator), dozens of devices with different OSes and browsers share a single IP - a variety of
# browsers is therefore NOT a signal (defect of version 1.20-1.21, which counted all the User-Agents).
progres "Section [9] : IP se présentant comme ${UA_ROTATION_THRESHOLD}+ robots d'organisations différentes"
echo "--- [9] IP se présentant comme ${UA_ROTATION_THRESHOLD}+ robots d'organisations différentes ---"
log "awk : familles de robots déclarées par IP (User-Agents de navigateurs ignorés), seuil ${UA_ROTATION_THRESHOLD}"
UA_ROTATION_SUMMARY=$(printf '%s\n' "$ACCESS_NEW" | awk -F'"' -v thresh="$UA_ROTATION_THRESHOLD" '
function family(ua,   l, t) {
    l = tolower(ua)
    gsub(/\+?https?:\/\/[^ ;)]*/, "", l)          # documentation URL ("+http://.../bot.html"): never a robot name
    if (l ~ /googlebot|googleother|google-inspectiontool|google-extended|adsbot-google|mediapartners-google|storebot-google|apis-google/) return "Google"
    if (l ~ /gptbot|chatgpt-user|oai-searchbot/) return "OpenAI"
    if (l ~ /meta-externalagent|facebookexternalhit|facebookbot|meta-externalfetcher/) return "Meta"
    if (l ~ /bingbot|bingpreview|adidxbot|msnbot/) return "Microsoft"
    if (l ~ /perplexitybot|perplexity-user/) return "Perplexity"
    if (l ~ /claudebot|claude-user|claude-searchbot/) return "Anthropic"
    if (l ~ /applebot/) return "Apple"
    if (l ~ /yandex[a-z]*bot|yandex\.com\/bots/) return "Yandex"
    if (match(l, /[a-z0-9_.-]*(bot|crawler|spider)[a-z0-9_-]*/)) {
        t = substr(l, RSTART, RLENGTH)
        if (t == "bot" || t == "bots" || t == "robot" || t == "robots") return ""
        return t                                    # robot inconnu : son propre nom sert de famille
    }
    return ""                                       # browser (or tool without a robot name): ignored
}
{
    split($1, ipf, " "); ip = ipf[1]; ua = $6
    total[ip]++
    f = family(ua)
    if (f == "") next
    if (index("|" fams[ip] "|", "|" f "|") == 0) { fams[ip] = (fams[ip] == "" ? f : fams[ip] "|" f); nf[ip]++ }
    if (!((ip SUBSEP ua) in seen)) { seen[ip SUBSEP ua] = 1; uas[ip] = uas[ip] "\001" ua }
}
END { for (ip in nf) if (nf[ip] >= thresh) print nf[ip] "\t" ip "\t" total[ip] "\t" fams[ip] "\t" uas[ip] }
' | sort -t$'\t' -k1,1 -rn) || true

if [[ -z "$UA_ROTATION_SUMMARY" ]]; then
    echo "${C_GREEN}RIEN${C_RESET}"
else
    n9=0
    while IFS=$'\t' read -r nb_fam rot_ip nb_total fam_list ua_blob; do
        [[ -z "$rot_ip" ]] && continue
        # IP protegees exclues : le serveur lui-meme (app-health-check.py --target external teste justement le
        # blocking of several robots - SERanking, Ahrefs, Geedo - from the public IP), private networks, team,
        # liste blanche nginx.
        protected_ip_reason "$rot_ip" >/dev/null && continue
        n9=$((n9 + 1))
        echo "${C_YELLOW}  $rot_ip : se présente comme $nb_fam robots d'organisations différentes (${fam_list//|/, }) sur $nb_total requête(s) — usurpation d'identité probable${C_RESET}"
        printf '%s\n' "$ua_blob" | tr '\001' '\n' | sed '/^$/d; s/^/      - /'
    done <<< "$UA_ROTATION_SUMMARY"
    if (( n9 == 0 )); then
        echo "${C_GREEN}RIEN${C_RESET} (seules des IP protégées — serveur lui-même, équipe, liste blanche — correspondaient)"
    else
        echo "  Vérifier une IP : nginx-log-audit.sh --investigate ADRESSE ; la bannir : nginx-log-audit.sh --ban ADRESSE"
    fi
fi
echo

# --- [10] Automatic investigation of suspicious IPs, with ban proposal ---
progres "Section [10] : Enquête sur les IP suspectes (proposition de bannissement à partir de $BAN_THRESHOLD indices)"
echo "--- [10] Enquête sur les IP suspectes (proposition de bannissement à partir de $BAN_THRESHOLD indices) ---"
SUSPECT_SRC="$STATE_DIR/.suspects.$$"
printf '%s\n' "$ACCESS_NEW" > "$SUSPECT_SRC"
INIT_ALL_TMP_FILES+=("$SUSPECT_SRC")
trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
log "scan_ips (rafales, outils de script, doubles identités, fichiers sensibles, erreurs) sur la fenêtre analysée"
progres "Section [10] : recherche des IP suspectes dans $(printf '%s\n' "$ACCESS_NEW" | grep -c . || true) ligne(s) (rafales, outils de script, fichiers sensibles, erreurs)"
SUSPECTS=$(scan_ips "$SUSPECT_SRC" "" "$((BAN_THRESHOLD > 1 ? BAN_THRESHOLD - 1 : 1))") || true
n_shown=0
if [[ -n "$SUSPECTS" ]]; then
    # Liste lue sur le descripteur 4 : l'entree standard reste celle du terminal, pour la confirmation.
    while IFS= read -r rec <&4; do
        [[ -z "$rec" ]] && continue
        rip=$(printf '%s' "$rec" | cut -d$'\037' -f2)
        # IP protegees (serveur lui-meme, reseau prive, equipe, liste blanche nginx) : jamais examinees ici.
        protected_ip_reason "$rip" >/dev/null && continue
        investigate_and_propose "$rec" "$ORIG_ACCESS_LOG"
        n_shown=$((n_shown + 1))
        (( n_shown >= 5 )) && { echo; echo "  (5 IP examinées au maximum par rapport — les suivantes au prochain passage)"; break; }
    done 4<<< "$SUSPECTS"
fi
(( n_shown == 0 )) && echo "${C_GREEN}RIEN${C_RESET}"
echo

# --- [11] Dynamic requests IN PARALLEL from the same address (probably the same visitor cookie) ---
# Original case: Odoo records the website visitor (website_visitor) on each page; several simultaneous requests carrying the SAME cookie fight over
# the same database row ("could not serialize access...", "bad query ... INSERT" in Odoo's log, 5xx response after 5 attempts). The nginx log does not contain
# the cookie: the observable clue is "at least N dynamic requests from the same address within the same second" (static files, images and /websocket excluded),
# AND accompanied by 5xx / 429 errors (without errors, it is normal use: several people behind the same address - university - who register or answer a poll at
# the same time trigger NOTHING). The addresses of a known place (nginx-tools-ip-location.conf: university, office...) are ignored. INFORMATIVE section: it proposes and performs no ban.
progres "Section [11] : requêtes dynamiques en parallèle (${PARALLEL_THRESHOLD}+ par seconde et par adresse)"
echo "--- [11] Requêtes dynamiques en parallèle depuis une même adresse (même cookie probable) ---"
PARALLELES=$(printf '%s\n' "$ACCESS_NEW" | awk -F'"' -v th="$PARALLEL_THRESHOLD" '
{
    if (!match($1, /\[[^]]*\]/)) next
    t = substr($1, RSTART + 1, RLENGTH - 2); sub(/ .*/, "", t)
    split($2, r, " "); u = r[2]; sub(/\?.*/, "", u)
    if (u ~ /^\/(static|web\/static|web\/assets|web\/image|web\/content|websocket|longpolling|favicon|robots)/) next
    if (u ~ /\.(js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|map|mp4)$/) next
    split($1, ipf, " "); ip = ipf[1]
    split($3, st, " "); k = ip SUBSEP t
    n[k]++
    if (st[1] ~ /^5/ || st[1] == "429") e[k]++
}
END {
    for (k in n) {
        if (n[k] < th) continue
        split(k, kk, SUBSEP); ip = kk[1]
        sec[ip]++; if (n[k] > mx[ip]) mx[ip] = n[k]; er[ip] += e[k]
    }
    for (ip in sec) if (er[ip] > 0) print sec[ip] "\t" ip "\t" mx[ip] "\t" er[ip] + 0
}' | sort -t$'\t' -k1,1 -rn | head -10) || true
n11=0
if [[ -n "$PARALLELES" ]]; then
    while IFS=$'\t' read -r nb_sec par_ip par_max par_err; do
        [[ -z "$par_ip" ]] && continue
        protected_ip_reason "$par_ip" >/dev/null && continue
        [[ -n "$(lieu_de_ip "$par_ip")" ]] && continue                    # known place (shared network): never reported
        n11=$((n11 + 1))
        echo "${C_YELLOW}  $par_ip : $nb_sec seconde(s) avec ${PARALLEL_THRESHOLD}+ requêtes dynamiques simultanées (jusqu'à $par_max), dont $par_err en erreur 5xx/429 — même cookie de visiteur probable${C_RESET}"
    done <<< "$PARALLELES"
fi
if (( n11 == 0 )); then
    echo "${C_GREEN}RIEN${C_RESET}"
else
    echo "  Effet : conflits d'écriture sur website_visitor dans Odoo (« bad query » / « could not serialize »). nginx-odoo-config 1.7 limite les connexions simultanées par cookie (limit_conn odoo_visiteur → 429) ;"
    echo "  Information seulement (aucun bannissement proposé) ; vérifier l'adresse : nginx-log-audit.sh --investigate ADRESSE"
fi
echo

# --- Optional section: targeted search for a precise IP (rereads the complete logs, not just the delta) ---
if [[ -n "$TARGET_IP" ]]; then
    echo
    echo "=============================================================="
    echo " IP CIBLEE : $TARGET_IP"
    echo "=============================================================="
    log "grep -F '$TARGET_IP ' \"$ACCESS_LOG\" | awk status | sort | uniq -c"
    IP_HITS=$(grep -F "$TARGET_IP " "$ACCESS_LOG" | awk -F'"' '{print $3}' | awk '{print $1}' | sort | uniq -c | sort -rn || true)
    if [[ -z "$IP_HITS" ]]; then
        echo "Aucune requête de cette IP dans $ACCESS_LOG."
    else
        echo "Répartition des statuts HTTP pour cette IP :"
        echo "$IP_HITS"
    fi
    if [[ -r "$CATCHALL_LOG" ]] && grep -qF "$TARGET_IP " "$CATCHALL_LOG"; then
        echo "${C_YELLOW}ATTENTION : cette IP apparaît aussi dans le capteur default_server (Host non reconnu ou IP nue) :${C_RESET}"
        grep -F "$TARGET_IP " "$CATCHALL_LOG" | tail -5
    fi
    if grep -rq -- "$TARGET_IP" /etc/nginx/conf.d/odoo-global.conf 2>/dev/null; then
        echo "Info : cette IP apparaît dans conf.d/odoo-global.conf (probablement \$is_trusted_ip ou une liste similaire)."
    fi
fi

# --- Section optionnelle : statistiques generales type goaccess (fichier complet, pas le delta) -----------------
if [[ "$DO_STATS" == "1" ]]; then

    # Description courte, en francais, des codes HTTP les plus frequemment rencontres dans ces logs. Un code
    # absent from this list (rare) simply displays "(undocumented)" rather than making the script fail.
    declare -A HTTP_DESC=(
        [101]="Changement de protocole (upgrade — ex. passage en websocket)"
        [200]="OK"
        [301]="Redirection permanente"
        [302]="Redirection temporaire"
        [303]="Redirection (voir ailleurs, POST->GET)"
        [304]="Non modifie (cache navigateur)"
        [400]="Requête invalide (souvent : HTTP en clair sur le port HTTPS)"
        [401]="Non authentifie"
        [403]="Interdit (bloqué par une règle nginx, ex. bad-bot)"
        [404]="Introuvable"
        [405]="Méthode HTTP non autorisée"
        [429]="Trop de requêtes (limitation de debit)"
        [444]="Connexion fermee sans réponse (nginx, capteur/anti-scan)"
        [499]="Client ferme la connexion avant la réponse"
        [500]="Erreur interne du serveur (côté Odoo)"
        [502]="Mauvaise passerelle (upstream injoignable ou en erreur)"
        [503]="Service indisponible"
        [504]="Delai d'attente upstream depasse"
    )
    describe_status() { echo "${HTTP_DESC[$1]:-(non documenté)}"; }

    # Ajoute une colonne pourcentage a une liste "  N libelle" (sortie de "sort | uniq -c | sort -rn"), relative
    # au total passe en $1. Format de sortie : "  N (P%) libelle".
    with_pct() {
        local total="$1"
        awk -v total="$total" '{
            count = $1; $1 = "";
            pct = (total > 0) ? sprintf("%5.1f%%", (count / total) * 100) : "  0.0%";
            printf "%6d (%s)%s\n", count, pct, $0
        }'
    }

    echo
    echo "=============================================================="
    echo " STATISTIQUES — $STATS_SOURCE_FILE"
    if [[ -n "$LAST_HOURS" ]]; then
        echo " Fenêtre : dernières ${LAST_HOURS}h seulement (--last), pas le fichier complet."
    else
        echo " ATTENTION : couvre TOUT l'historique du fichier, y compris les entrées antérieures à un correctif"
        echo " récent. Un chemin qui apparaît ici comme 'bloqué' peut très bien ne plus l'être depuis — vérifiez la"
        echo " date des lignes concernées, ou relancez avec --last pour restreindre à une fenêtre récente."
    fi
    echo "=============================================================="

    STATS_FILTRE="$STATE_DIR/.stats_filtre.$$"
    INIT_ALL_TMP_FILES+=("$STATS_FILTRE")
    trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
    N_NOS_STATS=$(compter_nos_programmes < "$STATS_SOURCE_FILE")
    filtrer_nos_programmes < "$STATS_SOURCE_FILE" > "$STATS_FILTRE"
    STATS_SOURCE_FILE="$STATS_FILTRE"
    TOTAL=$(wc -l < "$STATS_SOURCE_FILE")
    echo "Requêtes totales : $TOTAL  ($N_NOS_STATS de nos propres programmes exclues : boucle locale, ce serveur, app-health-check)"

    echo
    echo "--- Répartition par statut HTTP ---"
    # shellcheck disable=SC2016  # affiche la commande awk TELLE QUELLE : ses $ ne doivent pas etre remplaces
    log 'awk -F"\"" '"'"'{print $3}'"'"' | awk '"'"'{print $1}'"'"' | sort | uniq -c | sort -rn'
    while read -r count code; do
        printf "%6d (%5.1f%%) %s — %s\n" "$count" "$(awk -v c="$count" -v t="$TOTAL" 'BEGIN{print (t>0)?(c/t)*100:0}')" "$code" "$(describe_status "$code")"
    done < <(awk -F'"' '{print $3}' "$STATS_SOURCE_FILE" | awk '{print $1}' | sort | uniq -c | sort -rn)

    BLOCKED=$(awk -F'"' '$3 ~ /^ (403|404|405|429|444) /' "$STATS_SOURCE_FILE" | grep -c . || true)
    PCT="0"
    if (( TOTAL > 0 )); then
        PCT=$(awk -v b="$BLOCKED" -v t="$TOTAL" 'BEGIN{printf "%.1f", (b/t)*100}')
    fi
    echo
    echo "--- Requêtes bloquées (403/404/405/429/444) : $BLOCKED / $TOTAL (${PCT}%) ---"
    echo "Attention : 403/405/429/444 sont de vrais blocages nginx. Un 404 dans ce total est presque toujours"
    echo "Odoo qui répond normalement \"introuvable\" (route inexistante, mauvaise méthode) — pas un blocage nginx."
    echo "Relancez avec --details pour voir le statut exact par IP et lever le doute au cas par cas."
    echo "Top 15 chemins bloqués (méthode + chemin), % relatif au total de requêtes bloquées :"
    BLOCKED_TOP=$(awk -F'"' '$3 ~ /^ (403|404|405|429|444) /{print $2}' "$STATS_SOURCE_FILE" | sort | uniq -c | sort -rn | head -15) || true
    printf '%s\n' "$BLOCKED_TOP" | with_pct "$BLOCKED" || true

    if [[ "$DO_DETAILS" == "1" && -n "$BLOCKED_TOP" ]]; then
        echo
        echo "--- Détail par IP (statut + User-Agent) de chaque chemin bloqué ci-dessus (--details, top 3) ---"
        echo "    Rappel : 403/405/429/444 sont de vrais blocages nginx. Un 404 est presque toujours Odoo qui"
        echo "    répond normalement \"introuvable\" (route inexistante ou mauvaise méthode) — PAS un blocage nginx."
        while IFS= read -r topline; do
            req=$(printf '%s\n' "$topline" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]*//')
            echo "  $req :"
            grep -F "\"$req\"" "$STATS_SOURCE_FILE" | awk -F'"' '$3 ~ /^ (403|404|405|429|444) /{
                    split($3, st, " "); split($1, ipf, " ")
                    print ipf[1]" ("st[1]")  "$6
                }' | sort | uniq -c | sort -rn | head -3 | sed 's/^/      /' || true
        done < <(printf '%s\n' "$BLOCKED_TOP")
    fi

    echo
    echo "--- Top 10 chemins demandés (tous statuts confondus), % relatif au total ---"
    awk -F'"' '{print $2}' "$STATS_SOURCE_FILE" | sort | uniq -c | sort -rn | head -10 | with_pct "$TOTAL" || true

    # IPs present in an "allow" rule of the active nginx configuration (nginx -T) - informative only: says whether the
    # IP is already whitelisted somewhere (e.g. /web/database/manager), not whether THIS precise request benefited.
    # Requires nginx -T to be executable by the current user; otherwise, the annotation is ignored.
    ALLOWED_IPS=""
    if command -v nginx >/dev/null 2>&1; then
        log "nginx -T | grep -oE 'allow [0-9a-fA-F:.]+;'"
        ALLOWED_IPS=$(nginx -T 2>/dev/null | grep -oE 'allow [0-9a-fA-F:.]+;' | awk '{print $2}' | tr -d ';' | sort -u || true)
    fi

    echo
    echo "--- Top 10 IP (tous statuts confondus), % relatif au total ---"
    if [[ -n "$ALLOWED_IPS" ]]; then
        echo "(*) = IP présente dans au moins une règle 'allow' de la config nginx active (nginx -T)"
        while read -r count ip; do
            pct=$(awk -v c="$count" -v t="$TOTAL" 'BEGIN{print (t>0)?(c/t)*100:0}')
            marque=""
            grep -qxF "$ip" <<< "$ALLOWED_IPS" && marque=" (*)"
            printf "%6d (%5.1f%%) %s%s\n" "$count" "$pct" "$ip" "$marque"
        done < <(awk '{print $1}' "$STATS_SOURCE_FILE" | sort | uniq -c | sort -rn | head -10) || true
    else
        echo "(nginx -T indisponible ou aucune règle 'allow' trouvée — annotation ignorée)"
        awk '{print $1}' "$STATS_SOURCE_FILE" | sort | uniq -c | sort -rn | head -10 | with_pct "$TOTAL" || true
    fi

    echo
    echo "--- Appareils des visiteurs (humains probables) ---"
    echo "    Visiteur = IP + navigateur ayant vu une page ET chargé les CSS/JS (les robots lisent le HTML sans les"
    echo "    charger) ; robots, outils, User-Agent vide et équipe (liste blanche nginx) exclus. Un iPad récent se"
    echo "    présente comme un Mac : il compte comme ordinateur."
    awk -F'"' -v blanche="$(tr '\n' ' ' <<< "$ALLOWED_IPS")" '
        BEGIN { n = split(blanche, b, " "); for (i = 1; i <= n; i++) exclu[b[i]] = 1 }
        {
            split($1, a, " "); ip = a[1]; ua = $6; split($2, r, " "); url = r[2]; split($3, s, " "); code = s[1]
            if (r[1] != "GET" || ua == "" || ua == "-" || (ip in exclu)) next
            if (ua ~ /[Bb]ot|[Cc]rawler|[Ss]pider|curl|[Ww]get|python-|[Gg]o-http|okhttp|[Jj]ava|[Ss]crapy|[Hh]eadless|zgrab|masscan|nmap|nuclei|sqlmap|nikto|libwww|aiohttp|poc-suite/) next
            cle = ip "|" ua
            if (url ~ /^\/web\/(assets|static|image|content|binary)\/|\/static\/|\.(js|css)(\?|$)/) { if (code ~ /^[23]/) assets[cle] = 1; next }
            if (code ~ /^2/ && url !~ /\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|map)(\?|$)/) {
                if (ua ~ /iPad|Tablet|Kindle|Silk|PlayBook/ || (ua ~ /Android/ && ua !~ /Mobile/)) f = "Tablette"
                else if (ua ~ /Mobile|iPhone|iPod|Android|Windows Phone|Opera Mini|BlackBerry/) f = "Cellulaire"
                else f = "Ordinateur"
                fam[cle] = f
            }
        }
        END {
            for (c in fam) if (c in assets) { t[fam[c]]++; tot++ }
            if (!tot) { print "  aucun visiteur humain identifiable"; exit }
            split("Ordinateur Cellulaire Tablette", o, " ")
            for (i = 1; i <= 3; i++) printf "  %-11s %6d (%5.1f%%)\n", o[i], t[o[i]], 100 * t[o[i]] / tot
            printf "  %-11s %6d visiteur(s) humain(s) probable(s)\n", "Total", tot
        }' "$STATS_SOURCE_FILE"

    echo
    echo "--- Top 10 User-Agents, % relatif au total ---"
    UA_TOP=$(awk -F'"' '{print $6}' "$STATS_SOURCE_FILE" | sort | uniq -c | sort -rn | head -10) || true
    printf '%s\n' "$UA_TOP" | with_pct "$TOTAL" || true

    if [[ "$DO_DETAILS" == "1" && -n "$UA_TOP" ]]; then
        echo
        echo "--- Détail par IP de chaque User-Agent ci-dessus (--details, top 3 IP par UA) ---"
        while IFS= read -r topline; do
            ua=$(printf '%s\n' "$topline" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]*//')
            echo "  $ua :"
            grep -F "\"$ua\"" "$STATS_SOURCE_FILE" | awk '{print $1}' \
                | sort | uniq -c | sort -rn | head -3 | sed 's/^/      /' || true
        done < <(printf '%s\n' "$UA_TOP")
    fi

    # Approximate breakdown of VISITOR operating systems (not the server's), deduced from the
    # User-Agent par correspondance de motifs simples. Approximatif par nature : un bot peut usurper n'importe
    # quel UA, et certains navigateurs omettent l'OS. A prendre comme tendance, pas comme mesure exacte.
    echo
    echo "--- Répartition des systèmes d'exploitation visiteurs (approximatif, déduit du User-Agent) ---"
    # A single awk pass produces "OS<TAB>UA" for each line - avoids a fork per line for the detail (--details
    # devrait rester utilisable sur des dizaines de milliers de lignes sans devenir trop lent).
    OS_UA_PAIRS="$STATE_DIR/.os_ua_pairs.$$"
    awk -F'"' '{
        ua = $6
        if (ua ~ /Windows/) os = "Windows"
        else if (ua ~ /Android/) os = "Android"
        else if (ua ~ /iPhone|iPad|iOS/) os = "iOS"
        else if (ua ~ /Mac OS X|Macintosh/) os = "macOS"
        else if (ua ~ /Linux/) os = "Linux"
        else os = "Autre/non identifié"
        print os "\t" ua
    }' "$STATS_SOURCE_FILE" > "$OS_UA_PAIRS"

    OS_TOP=$(cut -f1 "$OS_UA_PAIRS" | sort | uniq -c | sort -rn)
    printf '%s\n' "$OS_TOP" | with_pct "$TOTAL" || true

    if [[ "$DO_DETAILS" == "1" && -n "$OS_TOP" ]]; then
        echo
        echo "--- Détail par User-Agent de chaque OS ci-dessus (--details, top 3 UA par OS) ---"
        while IFS= read -r topline; do
            os=$(printf '%s\n' "$topline" | sed -E 's/^[[:space:]]*[0-9]+[[:space:]]*//')
            echo "  $os :"
            awk -F'\t' -v os="$os" '$1 == os {print $2}' "$OS_UA_PAIRS" \
                | sort | uniq -c | sort -rn | head -3 | sed 's/^/      /' || true
        done < <(printf '%s\n' "$OS_TOP")
    fi
    rm -f "$OS_UA_PAIRS"

    echo
    echo "Rappel : ceci ne couvre QUE ce qui apparaît dans l'access log. Les règles 4 à 11 de securite-commune.conf"
    echo "(access_log off;) restent invisibles ici, quel que soit leur volume réel."
fi

# --- Section optionnelle : IP actuellement bannies par fail2ban, avec DNS inverse (reperer un faux positif) -----
if [[ "$DO_FAIL2BAN" == "1" ]]; then
    echo
    echo "=============================================================="
    echo " VÉRIFICATION FAIL2BAN"
    echo "=============================================================="
    if ! command -v fail2ban-client >/dev/null 2>&1; then
        echo "fail2ban-client introuvable — fail2ban n'est peut-être pas installe, ou pas dans le PATH de cet utilisateur."
    else
        declare -A RECIDIVISTS=()
        declare -A FICHIER_FUSIONNE=()
        RECIDIVIST_ORDER=()
        log "fail2ban-client status"
        JAIL_LIST=$(run fail2ban-client status 2>/dev/null | grep "Jail list:" | sed 's/.*Jail list:[[:space:]]*//' | tr ',' '\n' | sed 's/^ *//;s/ *$//') || true
        if [[ -z "$JAIL_LIST" ]]; then
            echo "Aucun jail trouvé (fail2ban tourne-t-il avec les droits nécessaires pour cet utilisateur ?)"
        fi
        while IFS= read -r jail; do
            [[ -z "$jail" ]] && continue
            log "fail2ban-client status $jail"
            BANNED=$(run fail2ban-client status "$jail" 2>/dev/null | grep "Banned IP list:" | sed 's/.*Banned IP list:[[:space:]]*//') || true
            # Le jail peut surveiller PLUSIEURS fichiers (ex. le fichier actuel + un ancien fichier herite d'avant
            # a reorganization) - recover them so that the --details sample searches everywhere fail2ban could have
            # cherche lui-meme, pas seulement dans $ACCESS_LOG. Sans ca, une IP bannie a cause d'une ligne dans un
            # AUTRE fichier surveille semble n'avoir "rien fait" quand on ne regarde que $ACCESS_LOG.
            JAIL_FILES=$(run fail2ban-client status "$jail" 2>/dev/null | grep "File list:" | sed 's/.*File list:[[:space:]]*//') || true
            echo
            echo "--- Jail: $jail ---"
            if [[ -z "$BANNED" ]]; then
                echo "  ${C_GREEN}Aucune IP actuellement bannie.${C_RESET}"
                continue                      # nothing to examine: no log is read for this jail (2.20)
            fi
            # Chaque fichier surveille par le jail est etendu a ses PROPRES rotations connues (.N, .N.gz,
            # decompressed on the fly) - without this, an IP whose faulty activity is in a portion already
            # tournee/compressee du meme fichier semblait n'avoir "rien fait". Chaque fichier n'est lu qu'UNE FOIS par
            # passage, meme surveille par plusieurs jails (FICHIER_FUSIONNE) ; toujours fait (pas seulement avec
            # --details) : la detection des recidivistes a besoin de plusieurs jours d'historique.
            JAIL_MERGED="$STATE_DIR/.fail2ban_${jail}_merged.$$"
            : > "$JAIL_MERGED"
            INIT_ALL_TMP_FILES+=("$JAIL_MERGED")
            read -ra ips_bannies <<< "$BANNED"; read -ra fichiers_jail <<< "$JAIL_FILES"
            n_banned=${#ips_bannies[@]}
            progres "Jail $jail : $n_banned IP bannie(s) ; lecture des journaux surveillés (${#fichiers_jail[@]} fichier(s) et leurs rotations)"
            for jf in $JAIL_FILES; do
                [[ -n "$jf" ]] || continue
                if [[ -z "${FICHIER_FUSIONNE[$jf]:-}" ]]; then
                    FICHIER_FUSIONNE[$jf]="$STATE_DIR/.fail2ban_file_${#FICHIER_FUSIONNE[@]}.$$"
                    INIT_ALL_TMP_FILES+=("${FICHIER_FUSIONNE[$jf]}")
                    merge_all_rotations "$jf" "${FICHIER_FUSIONNE[$jf]}" > /dev/null
                else
                    progres "Journal $(basename "$jf") déjà lu pour un autre jail : réutilisé"
                fi
                cat "${FICHIER_FUSIONNE[$jf]}" >> "$JAIL_MERGED" 2>/dev/null || true
            done
            trap 'rm -f "${INIT_ALL_TMP_FILES[@]}"' EXIT
            n_ip=0
            for ip in $BANNED; do
                n_ip=$((n_ip + 1))
                progres "Jail $jail — IP $n_ip/$n_banned : $ip (DNS inverse, whois, requêtes dans les journaux)"
                rdns=""
                days="" n_days=0
                if command -v host >/dev/null 2>&1; then
                    rdns=$(run timeout --foreground 3 host "$ip" 2>/dev/null | awk '/pointer/{print $NF}' | sed 's/\.$//' | head -1) || true
                elif command -v getent >/dev/null 2>&1; then
                    rdns=$(run timeout --foreground 3 getent hosts "$ip" 2>/dev/null | awk '{print $2}' | head -1) || true
                fi
                [[ -z "$rdns" ]] && rdns="(pas de PTR, ou outil DNS indisponible/timeout)"

                # Organization owning the IP (whois): the format varies enormously depending on the registry
                # (ARIN/RIPE/APNIC/etc.), donc on prend la premiere ligne correspondant a un des champs les plus
                # courants plutot que de tenter un parsing exhaustif.
                whois_org=""
                if command -v whois >/dev/null 2>&1; then
                    log "whois $ip"
                    whois_org=$(timeout --foreground 5 whois "$ip" 2>/dev/null \
                        | grep -iE '^(orgname|org-name|netname|descr|owner|org):' \
                        | head -1 | sed -E 's/^[^:]+:[[:space:]]*//') || true
                fi
                [[ -z "$whois_org" ]] && whois_org="(whois indisponible ou sans réponse utile)"

                marque=""
                # WARNING: "*.googleusercontent.com" (generic) is NOT a reliable sign of Googlebot - it is
                # le DNS inverse standard de N'IMPORTE QUELLE VM Google Cloud louee, legitime ou malveillante.
                # Seul "*.gae.googleusercontent.com" (App Engine, fetchers google declenches par un utilisateur)
                # est documente par Google comme fiable ; le vrai Googlebot utilise exclusivement .googlebot.com
                # ou .google.com. Erreur corrigee ici suite a un vrai faux positif observe (scanner de secrets
                # tournant sur une VM GCP louee, signale a tort comme "ressemble a un moteur de recherche").
                if printf '%s' "$rdns" | grep_q -iE '\.googlebot\.com$|\.google\.com$|\.gae\.googleusercontent\.com$|\.search\.msn\.com$|\.msnbot\.com$'; then
                    marque="  ${C_YELLOW}<-- ressemble à un vrai moteur de recherche : VERIFIER avant de laisser ce bannissement se prolonger${C_RESET}"
                fi
                printf "  %-16s %-45s %s%s\n" "$ip" "$rdns" "$whois_org" "$marque"

                # --details: searches ALL the requests of this IP in ALL the files this jail watches
                # (JAIL_FILES), not only $ACCESS_LOG. Displays the TOTAL COUNT and the breakdown by status
                # before a sample: a fail2ban ban is triggered by a RATE (e.g. maxretry=10 in
                # findtime=60s), so 3-5 example lines are not enough to judge whether the threshold was really
                # reached - see the total count for that, the sample only illustrates the content.
                log "grep -F '$ip ' \"$JAIL_MERGED\" (fichiers du jail + leurs rotations)"
                all_lines=$(grep -F "$ip " "$JAIL_MERGED" 2>/dev/null) || true

                # Recidive : activite sur plusieurs JOURS distincts. Les bannissements fail2ban sont temporaires
                # (bantime) : un attaquant qui revient apres chaque expiration merite un bannissement permanent.
                if [[ -n "$all_lines" ]]; then
                    days=$(printf '%s\n' "$all_lines" | grep -oE '\[[0-9]{2}/[A-Za-z]{3}/[0-9]{4}' | tr -d '[' \
                           | sort -u | sort -t/ -k3,3n -k2,2M -k1,1n) || true
                    n_days=$(printf '%s\n' "$days" | grep -c . || true)
                    if (( n_days >= 2 )) && ! protected_ip_reason "$ip" >/dev/null; then
                        if already=$(ip_already_blocked "$ip"); then
                            echo "      Récidiviste (actif sur $n_days jours) — $already."
                        else
                            day_list=$( { printf '%s\n' "$days" | head -5 | sed -E 's#/[0-9]{4}$##' | paste -sd, - | sed 's/,/, /g'; } || true)
                            (( n_days > 5 )) && day_list="$day_list…"
                            echo "      ${C_RED}⚠ Récidiviste : actif sur $n_days jours distincts ($day_list) — revient malgré les bannissements${C_RESET}"
                            echo "      ${C_RED}  temporaires de fail2ban : bannissement permanent recommandé (récapitulatif en fin de section).${C_RESET}"
                            if [[ -z "${RECIDIVISTS[$ip]:-}" ]]; then
                                RECIDIVISTS[$ip]="$n_days jours ($day_list), jail $jail"
                                demandees=$(urls_refusees "$ip" 3 | awk -F'\t' '{ printf "%s%s ×%d", (NR > 1 ? ", " : ""), $2, $1 }')
                                if [[ -n "$demandees" ]]; then RECIDIVISTS[$ip]+=", a demandé : $demandees"; fi
                                RECIDIVIST_ORDER+=("$ip")
                            fi
                        fi
                    fi
                fi

                if [[ "$DO_DETAILS" == "1" ]]; then
                    if [[ -n "$all_lines" ]]; then
                        total=$(printf '%s\n' "$all_lines" | grep -c .)
                        echo "      $total requête(s) au total pour cette IP (fichiers surveillés + rotations connues) — répartition par statut :"
                        printf '%s\n' "$all_lines" | awk -F'"' '{print $3}' | awk '{print $1}' | sort | uniq -c | sort -rn | sed 's/^/        /' || true
                        echo "      Échantillon (5 premières) :"
                        # Protege contre SIGPIPE : une IP tres active (ex. 770 requetes, > 64 Ko) remplit le tube,
                        # "head" stops after 5 lines and printf receives SIGPIPE - under pipefail, this stopped everything
                        # le script (code 141), exactement le bug corrige en 1.3, ici dans du code ajoute ensuite.
                        { printf '%s\n' "$all_lines" | head -5 | sed 's/^/        /'; } || true
                    else
                        echo "      (aucune requête de cette IP trouvée, même en incluant les rotations/compressés connus —"
                        echo "       l'activité fautive est peut-être dans un fichier plus ancien déjà supprimé par la rotation)"
                    fi
                fi
            done
        done <<< "$JAIL_LIST"

        if (( ${#RECIDIVIST_ORDER[@]} > 0 )); then
            echo
            echo "--- ${C_RED}Bannissement PERMANENT recommandé : ${#RECIDIVIST_ORDER[@]} IP récidiviste(s)${C_RESET} ---"
            echo "  Ces IP reviennent sur plusieurs jours : chaque bannissement fail2ban expire (bantime), puis elles"
            echo "  recommencent. Un bannissement permanent (--ban) les bloque définitivement au pare-feu."
            for rip in "${RECIDIVIST_ORDER[@]}"; do
                echo
                echo "  ▶ ${C_YELLOW}$rip${C_RESET} — ${RECIDIVISTS[$rip]}"
                PROP_RAISON="récidiviste fail2ban ($(date '+%Y-%m-%d %H:%M')) : ${RECIDIVISTS[$rip]}"
                confirm_and_ban "$rip"
            done
        fi
    fi
    echo
    echo "Rappel : le DNS inverse ET le whois peuvent mentir (n'importe qui peut configurer un PTR, et whois ne"
    echo "reflète que le propriétaire du BLOC d'IP, pas qui l'utilise réellement) — ce sont des indices, pas une"
    echo "preuve absolue. Pour Googlebot/Bingbot, la seule vérification fiable est le DNS inverse SUIVI d'une"
    echo "resolution DNS normale (forward) de ce nom, qui doit redonner la même IP."

    # --- Liste communautaire CrowdSec (sync-crowdsec-blocklist.sh) -----------------------------------------------
    # Ces IP sont bloquees par le NOYAU (ipset + regle DROP) avant meme d'atteindre nginx : elles n'apparaissent
    # donc dans AUCUN journal nginx, et fail2ban ne les voit jamais. Les compteurs par IP (paquets, octets,
    # first/last detection) are kept by sync-crowdsec-blocklist.sh - we reuse its --blocked output
    # plutot que de dupliquer sa logique de cumul (meme principe que nginx-hardening.sh --check plus haut).
    echo
    echo "=============================================================="
    echo " LISTE COMMUNAUTAIRE CROWDSEC (IP bloquées avant nginx)"
    echo "=============================================================="
    CROWDSEC_SCRIPT=""
    if [[ -x "$SCRIPT_DIR/sync-crowdsec-blocklist.sh" ]]; then
        CROWDSEC_SCRIPT="$SCRIPT_DIR/sync-crowdsec-blocklist.sh"
    elif command -v sync-crowdsec-blocklist.sh >/dev/null 2>&1; then
        CROWDSEC_SCRIPT="$(command -v sync-crowdsec-blocklist.sh)"
    fi
    if [[ -z "$CROWDSEC_SCRIPT" ]]; then
        echo "sync-crowdsec-blocklist.sh introuvable (ni à côté de ce script, ni dans le PATH) — section ignorée."
    elif [[ "$EUID" -ne 0 ]]; then
        echo "${C_YELLOW}Lecture des compteurs ipset impossible sans root — relancez avec sudo pour cette section.${C_RESET}"
    else
        # 20 au maximum, meme avec --details : la liste complete peut compter des milliers d'IP (1772 observees en
        # PROD). Liste complete : sync-crowdsec-blocklist.sh --blocked --top 0.
        CS_TOP=20
        # Sortie de --blocked sans son en-tete (4 premieres lignes : version + bandeau) : ce rapport a deja le sien.
        CS_OUT=$(NGINX_TOOLS_LANG=fr run "$CROWDSEC_SCRIPT" --blocked --top "$CS_TOP" 2>&1) || true
        if [[ -z "$CS_OUT" ]]; then
            echo "${C_YELLOW}Aucune sortie de $CROWDSEC_SCRIPT --blocked.${C_RESET}"
        else
            printf '%s\n' "$CS_OUT" | tail -n +5 | sed "s#--top 0 pour tout afficher#liste complète : $CROWDSEC_SCRIPT --blocked --top 0#"
        fi
    fi
fi

echo
echo "=============================================================="
if [[ -z "$R2$R3$R4$R6$UPSTREAM_DOWN" ]]; then
    echo "${C_GREEN} RÉSUMÉ : rien de suspect dans [2]/[3]/[4]/[6]/[7]. Relire [1], [5] et [8] pour du bruit habituel.${C_RESET}"
else
    echo "${C_RED} RÉSUMÉ : au moins une section contient du nouveau — a relire ci-dessus.${C_RESET}"
fi
echo "=============================================================="
