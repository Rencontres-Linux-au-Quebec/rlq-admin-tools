#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# sync-crowdsec-blocklist.sh — importe la liste communautaire de CrowdSec (CAPI) dans deux ipsets dedies (IPv4 et
# IPv6) + une regle iptables/ip6tables DROP chacun, sans faire tourner l'agent CrowdSec complet. Pense pour un
# lancement periodique (cron) : telecharge la liste (jusqu'a ~3000 IP), la charge par lots dans un ipset temporaire
# puis l'echange ATOMIQUEMENT avec l'ipset actif (ipset swap : jamais de fenetre avec un ensemble vide ou partiel),
# s'assure que les regles DROP existent (ajoutees une seule fois), et sauvegarde l'etat pour qu'il survive a un
# redemarrage.
#
# Pourquoi un ipset plutot que fail2ban-client banip par IP : fail2ban insere une regle iptables par IP, inadapte a
# ~3000 IP (lent a appliquer ET a faire correspondre au trafic). Un ipset reste rapide quel que soit son contenu, et
# une seule regle suffit.
#
# Savoir quelles IP ont REELLEMENT ete bloquees (--blocked) : les ipsets sont crees avec l'option "counters", qui
# compte paquets/octets PAR ENTREE a chaque correspondance de la regle DROP. Pas de journalisation noyau (LOG), peu
# fiable dans un conteneur LXC non privilegie. Comme chaque synchronisation remplace l'ipset (compteurs remis a
# zero), les compteurs sont cumules juste avant chaque echange dans un fichier d'etat local — l'historique survit
# donc aux synchronisations, y compris pour une IP retiree entre-temps de la liste communautaire.
#
# Source par defaut : "all.txt" du projet communautaire Y3ll0w/CrowdSec-CAPI-Decisions (republie la liste CAPI de
# CrowdSec, ~toutes les 2h, sans compte CrowdSec). Projet tiers, pas un service officiel de CrowdSec.
#
# HISTORIQUE DE VERSION (resume — voir sync-crowdsec-blocklist.changelog.txt pour le detail complet) :
#   1.24.20261019.150215 — New copyright: Services-Conseils Linux and Rencontres Linux au Québec contributors (AGPL-3.0-or-later).
#   1.23.20261016.173838 — Copyright holder: Services-Linux Conseils Inc
#   1.22.20261015.143436 — --anonymize : affichage anonymisé (pseudonymes stables).
#   1.21.20261012.103600 — Fichier de configuration créé au premier démarrage (toutes les options en commentaire) ; modèle doc/sync-crowdsec-blocklist.conf.example complété.
#   1.20.20261010.215000 — Affichage francais ou anglais (--lang) ; fichier de configuration (LANGUAGE et options) et -c/--config.
#   1.19.20261008.120306 — Couleurs conservees avec --report-err.
#   1.18.20261007.093208 — Adresses protegees : liste blanche et lieux [protegee] (apps/_listes.sh).
#   1.17.20261002.214327 — Premiere ligne de TOUTE execution (meme --help) : nom et version.
#   1.16.20260930.163902 — Option --report-err : rapport d'erreurs a copier-coller en fin d'execution.
#   1.15.20260930.081347 — Motif « A && B || C » remplace par un « if » (derniere_reussite).
#   1.14.20260929.195459 — Aide : options par ordre alphabetique.
#   1.13.20260929.134422 — Verrou flock contre les executions concurrentes.
#   1.12.20260929.123856 — IP protegees : liste unique apps/team-ips.list, en plus des « allow » de nginx (vaut pour BBB).
#   1.11.20260928.211633 — PATH non complete pendant la suite de tests (NGINX_TOOLS_TESTS).
#   1.10.20260928.091309 — PATH complete (cron) ; passage date ; vrai message d'ipset et diagnostic adapte, verifie avant
#                          le telechargement ; suivi des echecs consecutifs (--status) ; cron complete (PATH).
#   1.9.20260927.202645 — Changelog dans le sous-repertoire doc/ (repli sur l'ancien emplacement).
#   1.8.20260927.200712 — Fichiers d'etat et copie de sauvegarde en anglais (migration automatique).
#   1.7.20260927.145909 — Reference mise a jour : nginx-log-audit.sh (ancien chk-nginx-logs.sh).
#   1.6.20260926.125259 — ShellCheck 0.11.0 : aucun signalement, a tous les niveaux (constantes affectees puis
#                          declarees readonly, faux positifs documentes), variable morte was_exec retiree. --changelog : interruption d'un
#                          tube (ex. « | head ») geree proprement, au lieu d'un faux « ARRET INATTENDU (code 141) ».
#   1.5.20260926.085236 — Revue de type shellcheck : « rm -rf "${STATE_DIR:?}" » (SC2115) dans --uninstall —
#                          s'arrete au lieu de viser la racine si la variable etait un jour vide.
#   1.4.20260926.075558 — IP protegees JAMAIS bloquees (liste blanche nginx, adresses du serveur, fichier .allow),
#                          meme si la liste communautaire les contient exactement ou via une plage : entrees
#                          « nomatch » dans les ipsets ; reseaux prives ecartes. Course SIGPIPE de « | grep -q »
#                          corrigee (grep_q) — elle pouvait empecher la remise de la regle au demarrage de ufw.
#   1.3.20260924.213315 — Options --ufw-hook / --ufw-hook-remove : integration optionnelle a ufw via son point
#                          d'extension officiel /etc/ufw/after.init (bloc delimite, sauvegarde, retrait exact) —
#                          ipsets et regles restaures a chaque demarrage de ufw, sans attendre le cron.
#   1.2.20260924.203547 — Avertissement si la liste n'a pas change depuis --stale-days jours (defaut 3) : sortie,
#                          --status et journal systeme (logger) — signe d'un depot source plus alimente.
#   1.1.20260924.192259 — Installation automatique des paquets manquants (ipset, iptables, curl, ipset-persistent,
#                          iptables-persistent — ces deux derniers JAMAIS si ufw est installe, car apt supprimerait
#                          ufw) ; sauvegarde persistante apres chaque changement (netfilter-persistent save, chaines
#                          fail2ban retirees de la sauvegarde) ; --verbose ; indicateur de progression ; --blocked
#                          (IP reellement bloquees, compteurs par IP cumules) ; --cron-hours ; synchronisation sautee
#                          si la liste n'a pas change ; repli sur la derniere liste en cache si le telechargement
#                          echoue apres un redemarrage. Correctif : --status annoncait a tort ne pas exiger root.
#   1.0.20260924.162902 — Version initiale.
#
# Usage : sync-crowdsec-blocklist.sh [--dry-run] [--status] [--blocked [--top N]] [--source URL] [--install-cron
#                                    [--cron-hours N]] [--uninstall] [--min-ips N] [-v|--verbose] [--version]
#                                    [--changelog]
#   - (aucune option) : installe au besoin les paquets manquants, telecharge la liste, met a jour les ipsets
#                        (remplacement atomique), s'assure que les regles existent, sauvegarde l'etat. Root requis.
#   - --dry-run       : telecharge et analyse la liste sans rien installer ni modifier. Aucun privilege requis.
#   - --status        : etat actuel (ipsets, nombre d'entrees, regles, persistance, cron). Root requis (la lecture
#                        d'un ipset exige CAP_NET_ADMIN).
#   - --blocked       : IP de la liste qui ont REELLEMENT tente de se connecter et ont ete bloquees, triees par
#                        nombre de paquets, avec premiere/derniere detection. Root requis.
#   - --top N         : avec --blocked, nombre de lignes affichees (defaut : 50 ; 0 = toutes).
#   - --source URL    : remplace l'URL de la liste (texte brut, une IP ou un CIDR par ligne).
#   - --install-cron  : cree /etc/cron.d/sync-crowdsec-blocklist (fichier neuf et autonome) : une synchronisation
#                        toutes les --cron-hours heures, plus une au demarrage (@reboot). Root requis.
#   - --cron-hours N  : intervalle du cron, en heures (1 a 24, defaut : 1 — voir le changelog 1.1 pour le choix).
#   - --uninstall     : retire regles, ipsets, cron et cache, puis resauvegarde l'etat persistant pour que rien ne
#                        soit restaure au prochain demarrage. Ne desinstalle AUCUN paquet. Root requis.
#   - --stale-days N  : avertit (sortie, --status et journal systeme via logger) si la liste n'a pas change depuis N
#                        jours ou plus (defaut : 3 ; la source se met a jour environ toutes les 2 h). Une liste figee
#                        signale presque surement un depot source qui n'est plus alimente.
#   - --ufw-hook      : (serveurs avec ufw, optionnel) insere dans /etc/ufw/after.init — point d'extension officiel
#                        de ufw, execute juste apres l'initialisation de ses regles — un bloc delimite par des
#                        marqueurs qui restaure ipsets (depuis la liste en cache, sans reseau) et regles DROP a chaque
#                        demarrage de ufw : au boot, et apres un rechargement qui vide les chaines (MANAGE_BUILTINS=yes).
#                        Copie de sauvegarde faite une fois ; ne peut jamais faire echouer ufw. Seule modification d'un
#                        fichier existant de tout ce projet — d'ou une option explicite, jamais automatique. Root requis.
#   - --ufw-hook-remove : retire exactement ce bloc et remet le fichier dans son etat d'execution d'origine.
#   - --min-ips N     : minimum d'IP valides attendues avant d'accepter une mise a jour (defaut : 50) — protege
#                        contre un telechargement rate silencieusement qui debannirait tout le monde.
#   - -v/--verbose    : affiche chaque commande systeme executee (apt, ipset, iptables, curl...).
#   - --version       : affiche la version et quitte.
#   - --changelog     : affiche sync-crowdsec-blocklist.changelog.txt (couleur si terminal).

set -euo pipefail
# PATH complété (2.x) : sous cron, PATH se limite à /usr/bin:/bin — ipset, iptables, nft, fail2ban-client, nginx
# (dans /usr/sbin, /sbin) étaient alors introuvables. Ajoutés À LA FIN : ne masquent jamais une commande déjà trouvée.
for _d in /usr/local/sbin /usr/sbin /sbin; do [[ -n "${NGINX_TOOLS_TESTS:-}" ]] && break; case ":$PATH:" in *":$_d:"*) ;; *) PATH="$PATH:$_d" ;; esac; done
# (Pendant la suite de tests, NGINX_TOOLS_TESTS désactive cet ajout : /usr/sbin/ufw & co resteraient sinon joignables.)
export PATH

# grep_q : equivalent de « grep -q » SANS la course SIGPIPE. « cmd | grep -q motif » sous « set -o pipefail » peut
# repondre FAUX alors que le motif est present : grep -q s'arrete a la premiere correspondance et ferme le tube ; si
# cmd ecrit encore, il recoit SIGPIPE et pipefail propage cet echec (course observee en test sur « ipset list -n »).
# grep sans -q lit toute l'entree : l'ecrivain n'est jamais interrompu.
grep_q() { grep "$@" >/dev/null; }

# shellcheck disable=SC2154  # « ec » est affectee DANS le texte du trap (ec=$?), a l'execution : shellcheck
#                              ne peut pas le voir, le texte etant entre apostrophes (faux positif).
trap 'ec=$?; echo "" >&2; echo "*** ARRÊT INATTENDU DU SCRIPT (code $ec) À LA LIGNE $LINENO ***" >&2; echo "*** Commande fautive : $BASH_COMMAND" >&2' ERR

readonly SCRIPT_VERSION="1.24.20261019.150215"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}" .sh)"; readonly SCRIPT_NAME
# Changelog dans le sous-repertoire doc/ ; repli sur l'ancien emplacement (a cote du programme) tant que
# l'installation n'a pas ete reorganisee.
CHANGELOG_FILE="$SCRIPT_DIR/doc/${SCRIPT_NAME}.changelog.txt"
if [[ ! -r "$CHANGELOG_FILE" && -r "$SCRIPT_DIR/${SCRIPT_NAME}.changelog.txt" ]]; then CHANGELOG_FILE="$SCRIPT_DIR/${SCRIPT_NAME}.changelog.txt"; fi
readonly CHANGELOG_FILE
# Langue d'affichage (en ou fr) : --lang, SYNC_CROWDSEC_BLOCKLIST_LANG, LANGUAGE du fichier de configuration, LC_ALL / LANG — apps/_i18n.sh traduit la sortie (rien ne change en français).
if [[ -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_i18n.sh"
    i18n_relancer "$SCRIPT_NAME" SYNC_CROWDSEC_BLOCKLIST_LANG "$0" "$@"
fi

readonly IPSET_V4="crowdsec-blocklist-v4"
readonly IPSET_V6="crowdsec-blocklist-v6"
readonly SOURCE_URL_DEFAULT="https://raw.githubusercontent.com/Y3ll0w/CrowdSec-CAPI-Decisions/main/all.txt"
readonly STATE_DIR="${SYNC_CROWDSEC_STATE_DIR:-/var/lib/sync-crowdsec-blocklist}"
readonly CACHE_LIST="$STATE_DIR/last-list.txt"
readonly CACHE_SHA="$STATE_DIR/last-list.sha256"
readonly BLOCKED_DB="$STATE_DIR/blocked-ips.tsv"
readonly LAST_SYNC_FILE="$STATE_DIR/last-sync"
readonly FAILURE_FILE="$STATE_DIR/last-failure"   # échecs consécutifs en cours (effacé à la première réussite)
readonly LAST_CHANGE_FILE="$STATE_DIR/last-list-change"   # epoch du dernier changement REEL de la liste
readonly CRON_FILE="${SYNC_CROWDSEC_CRON_FILE:-/etc/cron.d/sync-crowdsec-blocklist}"
readonly CHUNK_SIZE=250
readonly ALLOW_FILE="${SYNC_CROWDSEC_ALLOW_FILE:-/etc/default/sync-crowdsec-blocklist.allow}"
readonly PUBLIC_IP_CACHE="$STATE_DIR/public-ip"
readonly PRIVATE_V4_RE='^(0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)'
readonly PRIVATE_V6_RE='^(::1(/|$)|[fF][eE]80:|[fF][cCdD][0-9a-fA-F]{0,2}:)'
readonly UFW_AFTER_INIT="${SYNC_CROWDSEC_UFW_AFTER_INIT:-/etc/ufw/after.init}"
# Noms de fichiers d'etat en anglais (1.8) : les anciens noms sont renommes au premier lancement, jamais d'ecrasement.
migrer_chemin() {
    if [[ -e "$1" && ! -e "$2" ]] && mv "$1" "$2" 2>/dev/null; then
        echo "Migration (noms de fichiers en anglais) : $1 → $2" >&2
    fi
    return 0
}
for _migr in "derniere-liste.txt:last-list.txt" "derniere-liste.sha256:last-list.sha256" "ip-bloquees.tsv:blocked-ips.tsv" \
             "derniere-synchro:last-sync" "dernier-changement-liste:last-list-change" "ip-publique:public-ip"; do  # _migr
    migrer_chemin "$STATE_DIR/${_migr%%:*}" "$STATE_DIR/${_migr##*:}"
done
migrer_chemin "${UFW_AFTER_INIT}.avant-sync-crowdsec" "${UFW_AFTER_INIT}.before-sync-crowdsec"
readonly UFW_HOOK_BEGIN="# BEGIN sync-crowdsec-blocklist (ajouté par sync-crowdsec-blocklist.sh --ufw-hook ; retirer avec --ufw-hook-remove)"
readonly UFW_HOOK_END="# END sync-crowdsec-blocklist"
readonly UFW_HOOK_STATE="$STATE_DIR/ufw-after-init-etait-executable"   # "oui" / "non" : etat d'origine, restaure au retrait

DO_DRY_RUN=0
DO_STATUS=0
DO_BLOCKED=0
DO_INSTALL_CRON=0
DO_UNINSTALL=0
DO_UFW_HOOK=0
DO_UFW_HOOK_REMOVE=0
DO_UFW_START=0
VERBOSE=0
SOURCE_URL="$SOURCE_URL_DEFAULT"
MIN_IPS=50
TOP_N=50
CRON_HOURS=1
STALE_DAYS=3

# --report-err : rapport d'erreurs à copier-coller en fin d'exécution (programme, version, serveur, échecs…) — apps/_rapport.sh
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_rapport.sh"
    rapport_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi
# Première ligne de TOUTE exécution, même avec --help : le nom et la version du programme (--version l'affiche lui-même).
case " $* " in *" --version "*) ;; *) echo "sync-crowdsec-blocklist.sh v$SCRIPT_VERSION" ;; esac
# Listes d'adresses (liste blanche, lieux protégés) : /etc/default/nginx-tools-*.conf — lecteur commun apps/_listes.sh.
# shellcheck source=/dev/null
[[ -r "$SCRIPT_DIR/apps/_listes.sh" ]] && . "$SCRIPT_DIR/apps/_listes.sh"
# Configuration (/etc/default/sync-crowdsec-blocklist.conf, puis ~/.sync-crowdsec-blocklist.cfg ; -c/--config : ce fichier SEUL) : valeurs par défaut des options, la ligne de commande l'emporte.
# Clés : CRON_HOURS, LANGUAGE, MIN_IPS, SOURCE, STALE_DAYS, TOP, VERBOSE.
if declare -F config_lire >/dev/null; then
    config_lire "$SCRIPT_NAME" "$@"
    config_defaut CRON_HOURS CRON_HOURS --cron-hours nombre
    config_defaut MIN_IPS MIN_IPS --min-ips nombre
    config_defaut SOURCE_URL SOURCE --source texte
    config_defaut STALE_DAYS STALE_DAYS --stale-days nombre
    config_defaut TOP_N TOP --top nombre
    config_defaut VERBOSE VERBOSE --verbose booleen
    case " $* " in *" --version "*|*" --help "*|*" -h "*) ;; *) config_afficher ;; esac
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DO_DRY_RUN=1; shift ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*|--lang=*) shift ;;
        --lang) shift 2 ;;
        --status) DO_STATUS=1; shift ;;
        --blocked) DO_BLOCKED=1; shift ;;
        --top) TOP_N="${2:-}"; shift 2 ;;
        --source) SOURCE_URL="${2:-}"; shift 2 ;;
        --install-cron) DO_INSTALL_CRON=1; shift ;;
        --cron-hours) CRON_HOURS="${2:-}"; shift 2 ;;
        --stale-days) STALE_DAYS="${2:-}"; shift 2 ;;
        --ufw-hook) DO_UFW_HOOK=1; shift ;;
        --ufw-hook-remove) DO_UFW_HOOK_REMOVE=1; shift ;;
        --ufw-start) DO_UFW_START=1; shift ;;   # interne : appele par /etc/ufw/after.init
        --uninstall) DO_UNINSTALL=1; shift ;;
        --min-ips) MIN_IPS="${2:-}"; shift 2 ;;
        -v|--verbose) VERBOSE=1; shift ;;
        --version) echo "sync-crowdsec-blocklist.sh version $SCRIPT_VERSION"; exit 0 ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then
                echo "Changelog introuvable : $CHANGELOG_FILE" >&2
                exit 1
            fi
            if [[ -t 1 ]]; then
                # Numeros de version en cyan gras ; SIGPIPE (ex. "| head") laisse terminer proprement par defaut.
                sed -E $'s/([0-9]+\\.[0-9]+\\.[0-9]{8}\\.[0-9]{6})/\\x1b[1;36m\\1\\x1b[0m/' "$CHANGELOG_FILE" || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            else
                cat "$CHANGELOG_FILE" || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            fi
            exit 0
            ;;
        -h|--help)
            cat <<'AIDE'
Usage : sync-crowdsec-blocklist.sh [OPTION]...
Importe la liste communautaire de CrowdSec dans deux ipsets (IPv4, IPv6) bloqués au pare-feu.

Options (par ordre alphabétique) :
  --anonymize                  anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE
  --blocked                    IP de la liste effectivement bloquées (compteurs du pare-feu)
  --changelog                  affiche le journal des modifications
  -c, --config FILE            fichier de configuration à lire SEUL (sinon : /etc/default/sync-crowdsec-blocklist.conf, puis ~/.sync-crowdsec-blocklist.cfg ;
                               clés : CRON_HOURS, LANGUAGE, MIN_IPS, SOURCE, STALE_DAYS, TOP, VERBOSE)
  --cron-hours N               avec --install-cron : intervalle en heures
  --dry-run                    télécharger et analyser la liste, sans rien modifier
  -h, --help                   affiche cette aide et quitte
  --install-cron               synchronisation automatique (fichier cron)
  --lang LANG                  langue d'affichage : en ou fr (défaut : selon LC_ALL / LC_MESSAGES / LANG)
  --min-ips N                  taille minimale acceptée de la liste (protection contre une liste tronquée)
  --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
                               échecs, avertissements) ; désactive couleurs et questions interactives
  --source URL                 autre source de la liste
  --stale-days N               âge au-delà duquel la liste est signalée périmée
  --status                     état : dernière synchronisation, échec en cours, taille, IP protégées
  --top N                      avec --blocked : nombre d'IP affichées
  --ufw-hook                   installer le crochet ufw (règles réinsérées à chaque rechargement d'ufw)
  --ufw-hook-remove            retirer le crochet ufw
  --ufw-start                  (interne) appelé par le crochet ufw
  --uninstall                  retirer cron, règles et ipsets
  -v, --verbose                affiche chaque commande lancée
  --version                    affiche la version et quitte
AIDE
            exit 0
            ;;
        --report-err) shift ;;                 # traité avant (apps/_rapport.sh) ; accepté ici avec --help, --version…
        *) echo "Argument inconnu: $1" >&2; exit 1 ;;
    esac
done

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
# Synchronisation (cron) : abandon immédiat si une autre tourne. Sans verrou : --status (lecture) et --ufw-hook
# (appelé par ufw à chaque rechargement : ne doit jamais être empêché de réinsérer ses règles).
if [[ "$DO_STATUS" != "1" && "$DO_UFW_HOOK" != "1" ]]; then
    prendre_verrou 0 sync-crowdsec-blocklist
fi

for pair in "MIN_IPS:--min-ips" "TOP_N:--top" "CRON_HOURS:--cron-hours" "STALE_DAYS:--stale-days"; do
    var="${pair%%:*}"; opt="${pair##*:}"
    if ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
        echo "ERREUR: $opt attend un entier positif (reçu: '${!var}')" >&2
        exit 1
    fi
done
if (( CRON_HOURS < 1 || CRON_HOURS > 24 )); then
    echo "ERREUR: --cron-hours attend une valeur entre 1 et 24 (reçu: $CRON_HOURS)" >&2
    exit 1
fi

if [[ -t 1 || -n "${REPORT_ERR_COULEUR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_CYAN=$'\x1b[1;36m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_CYAN=""; C_RESET=""
fi

# --- Utilitaires ----------------------------------------------------------------------------------------------------
# run : execute une commande en l'affichant d'abord si --verbose. L'affichage passe par le descripteur 3, copie du
# stderr ORIGINAL faite ici une seule fois : beaucoup d'appels redirigent leur propre stderr vers /dev/null pour
# masquer le bruit des outils (ex. "run ipset create ... 2>/dev/null") — ecrire la ligne "+ commande" sur stderr la
# ferait disparaitre avec ce bruit, exactement pour les commandes les plus importantes a voir.
exec 3>&2
run() {
    if [[ "$VERBOSE" == "1" ]]; then
        echo "${C_CYAN}+ $*${C_RESET}" >&3
    fi
    "$@"
}

vlog() { if [[ "$VERBOSE" == "1" ]]; then echo "${C_CYAN}+ $*${C_RESET}" >&3; fi; }

step() { echo "${C_CYAN}[$1/$2]${C_RESET} $3"; }

require_root() {
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERREUR: $1 nécessite root (sudo).${2:+ $2}" >&2
        exit 1
    fi
}

# Barre de progression sur une seule ligne (retour chariot) — seulement si la sortie est un terminal : dans un
# journal de cron, des centaines de "\r" rendraient le fichier illisible.
progress() {
    [[ -t 1 ]] || return 0
    local cur="$1" total="$2" pct filled bar
    if (( total > 0 )); then pct=$(( cur * 100 / total )); else pct=100; fi
    filled=$(( pct * 30 / 100 ))
    bar=$(printf '%*s' "$filled" '' | tr ' ' '#')
    printf '\r      [%-30s] %3d%% (%d/%d)' "$bar" "$pct" "$cur" "$total"
    if (( cur >= total )); then echo; fi
}

ufw_installed() {
    dpkg-query -W -f='${Status}' ufw 2>/dev/null | grep_q "install ok installed"
}

pkg_installed() {
    dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep_q "install ok installed"
}

set_exists() {
    ipset list -n 2>/dev/null | grep_q -xF "$1"
}

rule_exists() {
    local tool="$1" set_name="$2"
    command -v "$tool" >/dev/null 2>&1 && "$tool" -C INPUT -m set --match-set "$set_name" src -j DROP 2>/dev/null
}

# Compteurs actuels d'un ipset (seulement les entrees avec au moins un paquet), format : ip<TAB>paquets<TAB>octets.
# Une ligne de membre avec l'option counters ressemble a : "1.2.3.4 packets 12 bytes 720".
read_counters() {
    local set_name="$1"
    set_exists "$set_name" || return 0
    ipset list "$set_name" 2>/dev/null | awk '
        /^Members:/ { m = 1; next }
        m && $2 == "packets" && $3 > 0 { print $1 "\t" $3 "\t" $5 }
    ' || true
}

# Cumule les compteurs actuels (v4 + v6) dans la base locale, juste avant un echange d'ipset qui les remettra a
# zero. Format de la base : ip<TAB>paquets<TAB>octets<TAB>premiere_detection<TAB>derniere_detection. Les dates sont
# celles de la SYNCHRONISATION qui a constate l'augmentation : un compteur ipset ne donne pas l'heure exacte de
# chaque paquet, seulement "au moins un paquet depuis la synchronisation precedente".
accumulate_counters() {
    local now current tmp
    now=$(date '+%Y-%m-%d %H:%M')
    current=$( { read_counters "$IPSET_V4"; read_counters "$IPSET_V6"; } ) || true
    [[ -z "$current" ]] && return 0
    mkdir -p "$STATE_DIR"
    touch "$BLOCKED_DB"
    tmp="$BLOCKED_DB.tmp.$$"
    printf '%s\n' "$current" | awk -F'\t' -v OFS='\t' -v now="$now" '
        FNR == NR { cp[$1] = $2; cb[$1] = $3; next }
        { ip = $1; p = $2; b = $3; first = $4; last = $5
          if (ip in cp) { p += cp[ip]; b += cb[ip]; last = now; delete cp[ip] }
          print ip, p, b, first, last }
        END { for (ip in cp) print ip, cp[ip], cb[ip], now, now }
    ' - "$BLOCKED_DB" > "$tmp"
    mv "$tmp" "$BLOCKED_DB"
}

# Sauvegarde persistante (survie au redemarrage) via netfilter-persistent, si disponible et sans ufw. Retire
# ensuite de la sauvegarde tout ce qui appartient a fail2ban (chaines et ipsets "f2b-*") : fail2ban les recree
# lui-meme a son demarrage, et les restaurer en plus depuis la sauvegarde produirait des doublons ou des erreurs
# "chain already exists" au boot.
save_persistent() {
    if ufw_installed; then
        if ufw_hook_installed; then
            echo "      ufw installé : pas de netfilter-persistent (conflit) — le crochet ufw (--ufw-hook) restaure ipsets"
            echo "      et règles à chaque démarrage de ufw, depuis la dernière liste en cache."
        else
            echo "      ufw installé : pas de netfilter-persistent (conflit) — l'entrée @reboot du cron (--install-cron)"
            echo "      recrée ipsets et règles ~60 s après le démarrage. Plus tôt et plus fiable : --ufw-hook."
        fi
        return 0
    fi
    if ! command -v netfilter-persistent >/dev/null 2>&1; then
        echo "      ${C_YELLOW}netfilter-persistent introuvable — état NON sauvegardé pour le redémarrage.${C_RESET}"
        return 0
    fi
    if run netfilter-persistent save >/dev/null 2>&1; then
        local f
        for f in /etc/iptables/rules.v4 /etc/iptables/rules.v6 /etc/iptables/ipsets; do
            if [[ -f "$f" ]] && grep -q 'f2b-' "$f" 2>/dev/null; then
                run sed -i '/f2b-/d' "$f"
            fi
        done
        echo "      ${C_GREEN}État sauvegardé (netfilter-persistent save, chaînes fail2ban exclues de la sauvegarde).${C_RESET}"
    else
        echo "      ${C_YELLOW}Échec de netfilter-persistent save — état NON sauvegardé pour le redémarrage.${C_RESET}"
    fi
}

# --- Diagnostic d'ipset et suivi des echecs consecutifs --------------------------------------------------------------
LAST_ERROR=""
# Message d'ipset -> cause probable et remede (au lieu d'accuser LXC dans tous les cas, comme jusqu'a la 1.9).
diagnostic_ipset() {
    local err="$1"
    if ! command -v ipset >/dev/null 2>&1; then
        echo "commande ipset introuvable (PATH : $PATH) — paquet ipset absent ?"
    elif [[ "$err" == *"Operation not permitted"* || "$err" == *"Permission denied"* ]]; then
        echo "droits insuffisants pour ipset ($err) — conteneur LXC non privilégié : autoriser ipset dans le conteneur"
        echo "(Proxmox : conteneur privilégié, ou nesting/keyctl selon la version) ; sur l'hôte : lsmod | grep ip_set"
    elif [[ "$err" == *"not supported"* || "$err" == *"Kernel error"* || "$err" == *"Can't open"* || "$err" == *"Protocol"* ]]; then
        echo "module noyau ip_set non disponible ($err) — dans un conteneur LXC, le charger sur l'HÔTE Proxmox :"
        echo "modprobe ip_set ip_set_hash_net xt_set, et l'ajouter à /etc/modules-load.d/ sur l'hôte (permanent)"
    else
        echo "ipset a répondu : ${err:-aucun message}"
    fi
}
echec() {             # message d'erreur fatal, retenu pour le suivi des échecs
    LAST_ERROR=$(printf '%s' "$1" | head -1)
    printf '%s\n' "$1" | sed "s/^/${C_RED}ERREUR: /; s/\$/${C_RESET}/" >&2
}
derniere_reussite() { if [[ -r "$LAST_SYNC_FILE" ]]; then cat "$LAST_SYNC_FILE"; else echo "inconnue"; fi; }
# Fin d'une synchronisation (piege EXIT) : echec -> compteur et date du premier echec ; reussite -> suivi efface.
fin_synchro() {
    local rc="$1" since="" count=0
    [[ "$DO_DRY_RUN" == "1" || "$EUID" -ne 0 ]] && return 0
    if (( rc == 0 )); then
        rm -f "$FAILURE_FILE"
        return 0
    fi
    if [[ -r "$FAILURE_FILE" ]]; then
        since=$(sed -n 's/^since=//p' "$FAILURE_FILE"); count=$(sed -n 's/^count=//p' "$FAILURE_FILE")
    fi
    since=${since:-$(date '+%Y-%m-%d %H:%M')}; count=$(( ${count:-0} + 1 ))
    mkdir -p "$STATE_DIR"
    printf 'since=%s\ncount=%s\nlast=%s\nmessage=%s\n' "$since" "$count" "$(date '+%Y-%m-%d %H:%M')" \
        "${LAST_ERROR:-arrêt avec le code $rc}" > "$FAILURE_FILE" 2>/dev/null || true
    echo "${C_RED}ÉCHEC n° $count consécutif, depuis le $since — dernière synchronisation réussie : $(derniere_reussite)${C_RESET}" >&2
}

# Installation des paquets manquants. apt-get --no-remove : si l'installation devait retirer un paquet (ex. ufw a
# cause d'un conflit), apt abandonne au lieu de supprimer quoi que ce soit — garde-fou en plus de la verification
# explicite de ufw ci-dessous.
ensure_packages() {
    local missing=()
    command -v curl >/dev/null 2>&1 || missing+=(curl)
    command -v ipset >/dev/null 2>&1 || missing+=(ipset)
    command -v iptables >/dev/null 2>&1 || missing+=(iptables)
    if ufw_installed; then
        echo "      ufw est installé : ipset-persistent/iptables-persistent volontairement NON installés (apt"
        echo "      supprimerait ufw pour résoudre un conflit de paquets)."
    else
        pkg_installed iptables-persistent || missing+=(iptables-persistent)
        pkg_installed ipset-persistent || missing+=(ipset-persistent)
    fi
    if [[ ${#missing[@]} -eq 0 ]]; then
        echo "      Tous les paquets requis sont déjà installés."
        return 0
    fi
    echo "      Installation : ${missing[*]}"
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "${C_RED}ERREUR: apt-get introuvable — installez vous-même : ${missing[*]}${C_RESET}" >&2
        exit 1
    fi
    # Sans ces reponses pre-remplies, iptables-persistent pose deux questions interactives a l'installation
    # ("sauvegarder les regles actuelles ?"), qui bloqueraient indefiniment une execution par cron. Non : la
    # sauvegarde est faite plus loin par ce script, apres nettoyage des chaines fail2ban.
    if command -v debconf-set-selections >/dev/null 2>&1; then
        printf '%s\n' "iptables-persistent iptables-persistent/autosave_v4 boolean false" \
                      "iptables-persistent iptables-persistent/autosave_v6 boolean false" | run debconf-set-selections
    fi
    run apt-get update -qq >/dev/null 2>&1 || echo "      ${C_YELLOW}apt-get update a échoué — tentative d'installation quand même.${C_RESET}"
    if ! run env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends --no-remove "${missing[@]}" >/dev/null 2>&1; then
        echo "${C_RED}ERREUR: échec de l'installation de : ${missing[*]} (relancez avec --verbose, ou installez-les vous-même).${C_RESET}" >&2
        exit 1
    fi
    echo "      ${C_GREEN}Installé : ${missing[*]}${C_RESET}"
}

# Charge un fichier (une entree par ligne) dans un ipset par lots de CHUNK_SIZE via "ipset restore" (un seul
# processus par lot au lieu d'un "ipset add" par IP — des dizaines de fois plus rapide pour ~3000 entrees).
# Met a jour la barre de progression partagee (LOADED/TOTAL_TO_LOAD).
load_into_set() {
    local file="$1" set_name="$2" batch count
    [[ -s "$file" ]] || return 0
    count=0
    batch=""
    while IFS= read -r entry; do
        [[ -z "$entry" ]] && continue
        batch+="add $set_name $entry"$'\n'
        count=$((count + 1))
        if (( count % CHUNK_SIZE == 0 )); then
            vlog "ipset restore -exist  (lot de $CHUNK_SIZE entrées vers $set_name)"
            printf '%s' "$batch" | ipset restore -exist 2>/dev/null || true
            batch=""
            LOADED=$((LOADED + CHUNK_SIZE))
            progress "$LOADED" "$TOTAL_TO_LOAD"
        fi
    done < "$file"
    if [[ -n "$batch" ]]; then
        local rest=$(( count % CHUNK_SIZE ))
        vlog "ipset restore -exist  (lot de $rest entrées vers $set_name)"
        printf '%s' "$batch" | ipset restore -exist 2>/dev/null || true
        LOADED=$((LOADED + rest))
        progress "$LOADED" "$TOTAL_TO_LOAD"
    fi
}

# Remplace le contenu de l'ipset actif par celui d'un ipset temporaire, atomiquement. Si l'echange echoue (ex. ipset
# actif cree par la version 1.0 SANS l'option counters, incompatible), bascule sur un remplacement complet : retrait
# de la regle, destruction de l'ancien ipset, renommage du temporaire, remise de la regle — une fenetre de quelques
# millisecondes sans protection, une seule fois lors de cette migration.
swap_or_replace() {
    local tmp_set="$1" set_name="$2" tool="$3"
    if run ipset swap "$tmp_set" "$set_name" 2>/dev/null; then
        run ipset destroy "$tmp_set"
        return 0
    fi
    echo "      ${C_YELLOW}Échange impossible pour $set_name (ipset incompatible, probablement créé sans compteurs) — remplacement complet.${C_RESET}"
    if rule_exists "$tool" "$set_name"; then
        run "$tool" -D INPUT -m set --match-set "$set_name" src -j DROP
    fi
    run ipset destroy "$set_name"
    run ipset rename "$tmp_set" "$set_name"
}

# Age (en jours entiers) depuis le dernier changement REEL de la liste, ou vide si inconnu.
list_age_days() {
    [[ -r "$LAST_CHANGE_FILE" ]] || return 0
    local since now
    since=$(cat "$LAST_CHANGE_FILE" 2>/dev/null) || return 0
    [[ "$since" =~ ^[0-9]+$ ]] || return 0
    now=$(date +%s)
    echo $(( (now - since) / 86400 ))
}

# Avertit si la liste n'a pas change depuis plus de STALE_DAYS jours : la source se met a jour environ toutes les
# 2 h, donc une liste figee depuis plusieurs jours signifie presque surement que le depot tiers qui la republie
# n'est plus alimente (projet abandonne, compte suspendu, changement de format). Les ipsets resteraient alors
# charges avec une liste de plus en plus perimee, SANS aucune erreur visible — d'ou cet avertissement, repris dans
# le journal systeme (logger) pour ne pas rester enfoui dans le fichier de journal du cron.
warn_if_stale() {
    local age
    age=$(list_age_days)
    [[ -n "$age" ]] || return 0
    (( age >= STALE_DAYS )) || return 0
    local since_h
    since_h=$(date -d "@$(cat "$LAST_CHANGE_FILE")" '+%Y-%m-%d %H:%M' 2>/dev/null) || since_h="?"
    echo "${C_YELLOW}ATTENTION : la liste n'a pas changé depuis $age jour(s) (dernier changement : $since_h), alors que${C_RESET}"
    echo "${C_YELLOW}la source se met normalement à jour environ toutes les 2 h. Le dépôt qui la republie n'est probablement${C_RESET}"
    echo "${C_YELLOW}plus alimenté — vérifiez ses derniers commits : https://github.com/Y3ll0w/CrowdSec-CAPI-Decisions/commits/main${C_RESET}"
    echo "${C_YELLOW}Les ipsets restent chargés avec cette liste de plus en plus périmée (aucune IP retirée ni ajoutée).${C_RESET}"
    echo "${C_YELLOW}Solutions : une autre source (--source URL), ou le vrai agent CrowdSec. Seuil réglable : --stale-days N.${C_RESET}"
    # Journal systeme seulement lors d'une synchronisation (le cron), pas a chaque consultation de --status.
    if [[ "${1:-}" != "sans-journal" ]] && command -v logger >/dev/null 2>&1; then
        run logger -t sync-crowdsec-blocklist -p user.warning \
            "Liste CrowdSec inchangee depuis $age jour(s) (depuis $since_h) : source probablement plus alimentee ($SOURCE_URL)" || true
    fi
}

# --- IP protegees : JAMAIS bloquees, meme si la liste communautaire les contient -----------------------------------
# Risque couvert : une IP de l'equipe (souvent une connexion residentielle dynamique, reattribuee) ou du serveur
# lui-meme presente dans la liste communautaire — le serveur se couperait de ses administrateurs ou de ses propres
# outils. Source unique, comme pour nginx-log-audit.sh : les IP des regles « allow » de la config nginx active, les
# adresses du serveur (hostname -I + IP publique), et un fichier optionnel ALLOW_FILE (une IP ou un CIDR par ligne,
# # pour les commentaires). Les reseaux prives et de boucle locale sont ecartes de la liste des le depart.
collect_protected_ips() {
    local out="" ip pub
    if command -v nginx >/dev/null 2>&1; then
        out+=$(run nginx -T 2>/dev/null | grep -oE 'allow [0-9a-fA-F:./]+;' | awk '{print $2}' | tr -d ';')$'\n' || true
        # Liste blanche et lieux [protégée] (/etc/default/nginx-tools-*.conf, apps/_listes.sh) : protégés même sans liste « allow » nginx (BBB).
        out+=$(listes_ne_pas_bannir)$'\n' || true
    fi
    out+=$(hostname -I 2>/dev/null | tr ' ' '\n')$'\n' || true
    pub=$(cat "$PUBLIC_IP_CACHE" 2>/dev/null) || pub=""
    if [[ -z "$pub" ]] && command -v curl >/dev/null 2>&1; then
        pub=$(run curl -s --max-time 3 https://icanhazip.com 2>/dev/null | tr -d '[:space:]') || pub=""
        if [[ "$pub" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ || "$pub" =~ ^[0-9a-fA-F:]+:[0-9a-fA-F:]*$ ]]; then
            mkdir -p "$STATE_DIR"; echo "$pub" > "$PUBLIC_IP_CACHE"
        else
            pub=""
        fi
    fi
    out+="$pub"$'\n'
    if [[ -r "$ALLOW_FILE" ]]; then
        out+=$(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$ALLOW_FILE")$'\n'
    fi
    # Seulement les adresses publiques valides (les privees sont de toute facon ecartees de la liste).
    printf '%s\n' "$out" | grep -E '^([0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?|[0-9a-fA-F:]+:[0-9a-fA-F:]*(/[0-9]{1,3})?)$' \
        | grep -vE "$PRIVATE_V4_RE" | grep -vE "$PRIVATE_V6_RE" | sort -u || true
}

# Ajoute chaque IP protegee en « nomatch » dans les ipsets indiques : dans un ipset hash:net, une entree plus precise
# marquee nomatch l'emporte sur une plage plus large qui la contient — une IP protegee n'est donc jamais bloquee, que
# la liste la contienne exactement ou via une plage (CIDR). Affiche un avertissement pour chaque IP protegee qui
# figurait dans la liste. $1/$2 = ipsets IPv4/IPv6 ; $3 = « silencieux » pour --ufw-start.
apply_protected() {
    local set4="$1" set6="$2" quiet="${3:-}" ip set n=0 hits=0
    PROTECTED_LIST=$(collect_protected_ips) || PROTECTED_LIST=""
    while IFS= read -r ip; do
        [[ -z "$ip" ]] && continue
        if [[ "$ip" == *:* ]]; then set="$set6"; else set="$set4"; fi
        if [[ "$ip" != */* ]] && ipset test "$set" "$ip" >/dev/null 2>&1; then
            hits=$((hits + 1))
            [[ -z "$quiet" ]] && echo "      ${C_YELLOW}ATTENTION : $ip (IP protégée) figurait dans la liste communautaire — exclue, jamais bloquée.${C_RESET}"
        fi
        # del puis add : un simple « add -exist » ne garantit pas la mise a jour du drapeau nomatch d'une entree
        # deja presente (IP protegee listee exactement).
        ipset del "$set" "$ip" >/dev/null 2>&1 || true
        run ipset add "$set" "$ip" nomatch -exist >/dev/null 2>&1 || true
        n=$((n + 1))
    done <<< "$PROTECTED_LIST"
    [[ -z "$quiet" ]] && echo "      $n IP protégée(s) (liste blanche nginx, adresses du serveur, $ALLOW_FILE) : jamais bloquée(s)$([[ $hits -gt 0 ]] && echo " — dont $hits présente(s) dans la liste communautaire")."
    return 0
}

# --- Integration ufw (optionnelle) ---------------------------------------------------------------------------------
# ufw execute /etc/ufw/after.init (s'il est executable) juste APRES avoir mis en place ses propres regles, a son
# demarrage — donc au boot et, avec MANAGE_BUILTINS=yes, a chaque rechargement qui vide les chaines de base. C'est le
# point d'extension officiel prevu par ufw pour les ipsets (voir « man ufw-framework »). --ufw-hook y insere un bloc
# delimite par des marqueurs, qui appelle ce script en mode --ufw-start : rechargement des ipsets depuis la derniere
# liste en cache (aucun reseau, aucun apt — ufw demarre tot au boot) et remise des regles DROP en tete de INPUT.
# Seul le bloc entre les marqueurs est ajoute ou retire ; le reste du fichier n'est jamais modifie.

ufw_hook_installed() {
    [[ -f "$UFW_AFTER_INIT" ]] && grep -qxF "$UFW_HOOK_BEGIN" "$UFW_AFTER_INIT" 2>/dev/null
}

# Retire le bloc entre les marqueurs (inclus) d'un fichier, sans toucher au reste.
strip_ufw_block() {
    awk -v b="$UFW_HOOK_BEGIN" -v e="$UFW_HOOK_END" '
        $0 == b { skip = 1; next }
        skip && $0 == e { skip = 0; next }
        !skip { print }' "$1"
}

install_ufw_hook() {
    local script_path tmp
    script_path="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
    mkdir -p "$STATE_DIR" "$(dirname "$UFW_AFTER_INIT")"
    if [[ ! -f "$UFW_AFTER_INIT" ]]; then
        # Fichier absent (installation atypique) : on cree un after.init minimal, avec la meme structure que celui
        # fourni par ufw.
        # shellcheck disable=SC2016  # contenu ecrit dans after.init : « $1 » doit y rester litteral
        printf '%s\n' '#!/bin/sh' '# after.init : si exécutable, appelé par ufw-init. Voir « man ufw-framework ».' \
            'case "$1" in' 'start|stop|status|flush-all) ;;' '*) echo "Usage: after.init {start|stop|flush-all|status}" ;;' 'esac' \
            > "$UFW_AFTER_INIT"
        echo "non" > "$UFW_HOOK_STATE"
        echo "      $UFW_AFTER_INIT absent — fichier minimal créé."
    else
        # Etat d'origine memorise UNE SEULE FOIS (une reinstallation ne doit pas l'ecraser par « oui »).
        if [[ ! -f "$UFW_HOOK_STATE" ]]; then
            if [[ -x "$UFW_AFTER_INIT" ]]; then echo "oui" > "$UFW_HOOK_STATE"; else echo "non" > "$UFW_HOOK_STATE"; fi
        fi
        if [[ ! -f "${UFW_AFTER_INIT}.before-sync-crowdsec" ]]; then
            run cp -p "$UFW_AFTER_INIT" "${UFW_AFTER_INIT}.before-sync-crowdsec"
            echo "      Copie de sauvegarde : ${UFW_AFTER_INIT}.before-sync-crowdsec"
        fi
    fi
    tmp="$(mktemp)"
    # Bloc insere juste apres la premiere ligne (#!) : il s'execute avant le reste, ne gere que « start », et se
    # termine toujours avec succes (« || true ») — meme sous « set -e » (present dans le after.init d'Ubuntu), il ne
    # peut jamais faire echouer le demarrage de ufw, y compris si ce script a ete deplace ou supprime depuis.
    strip_ufw_block "$UFW_AFTER_INIT" | awk -v b="$UFW_HOOK_BEGIN" -v e="$UFW_HOOK_END" -v s="$script_path" '
        NR == 1 && /^#!/ { print; ins = 1 }
        function block() {
            print b
            print "case \"$1\" in"
            print "    start) [ -x \"" s "\" ] && \"" s "\" --ufw-start >/dev/null 2>&1 || true ;;"
            print "esac"
            print e
        }
        NR == 1 && ins { block(); next }
        NR == 1 && !ins { block() }
        { print }' > "$tmp"
    run cp "$tmp" "$UFW_AFTER_INIT"
    rm -f "$tmp"
    run chmod 755 "$UFW_AFTER_INIT"
    echo "      ${C_GREEN}Crochet installé dans $UFW_AFTER_INIT${C_RESET} (appelle : $script_path --ufw-start)."
}

remove_ufw_hook() {
    local tmp
    if ! ufw_hook_installed; then
        echo "      Aucun crochet sync-crowdsec-blocklist dans $UFW_AFTER_INIT — rien à retirer."
        return 0
    fi
    tmp="$(mktemp)"
    strip_ufw_block "$UFW_AFTER_INIT" > "$tmp"
    run cp "$tmp" "$UFW_AFTER_INIT"
    rm -f "$tmp"
    if [[ "$(cat "$UFW_HOOK_STATE" 2>/dev/null)" == "non" ]]; then
        run chmod a-x "$UFW_AFTER_INIT"
        echo "      $UFW_AFTER_INIT remis non exécutable (son état d'origine)."
    fi
    rm -f "$UFW_HOOK_STATE"
    echo "      ${C_GREEN}Crochet retiré de $UFW_AFTER_INIT${C_RESET} (reste du fichier inchangé)."
}

# Mode --ufw-start (appele par after.init) : silencieux, rapide, sans reseau, ne doit JAMAIS echouer.
ufw_start_restore() {
    command -v ipset >/dev/null 2>&1 || exit 0
    if ! { set_exists "$IPSET_V4" && set_exists "$IPSET_V6"; }; then
        [[ -s "$CACHE_LIST" ]] || exit 0
        local t4 t6
        t4="$(mktemp)"; t6="$(mktemp)"
        grep -E '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(/[0-9]{1,2})?$' "$CACHE_LIST" > "$t4" || true
        grep -E '^[0-9a-fA-F:]+:[0-9a-fA-F:]*(/[0-9]{1,3})?$' "$CACHE_LIST" > "$t6" || true
        ipset create "$IPSET_V4" hash:net family inet counters -exist 2>/dev/null || true
        ipset create "$IPSET_V6" hash:net family inet6 counters -exist 2>/dev/null || true
        LOADED=0; TOTAL_TO_LOAD=0
        load_into_set "$t4" "$IPSET_V4" >/dev/null 2>&1 || true
        load_into_set "$t6" "$IPSET_V6" >/dev/null 2>&1 || true
        apply_protected "$IPSET_V4" "$IPSET_V6" silencieux >/dev/null 2>&1 || true
        rm -f "$t4" "$t6"
    fi
    local pair tool set_name
    for pair in "iptables:$IPSET_V4" "ip6tables:$IPSET_V6"; do
        IFS=: read -r tool set_name <<< "$pair"
        if command -v "$tool" >/dev/null 2>&1 && set_exists "$set_name" && ! rule_exists "$tool" "$set_name"; then
            "$tool" -I INPUT -m set --match-set "$set_name" src -j DROP 2>/dev/null || true
        fi
    done
    if command -v logger >/dev/null 2>&1; then
        logger -t sync-crowdsec-blocklist "Démarrage de ufw : ipsets et règles CrowdSec restaurés (liste en cache)" 2>/dev/null || true
    fi
    exit 0
}

if [[ "$DO_UFW_START" == "1" ]]; then
    trap - ERR
    set +e
    [[ "$EUID" -eq 0 ]] || exit 0
    ufw_start_restore
fi

date '+%Y-%m-%d %H:%M:%S %Z'

# --- --ufw-hook / --ufw-hook-remove -------------------------------------------------------------------------------------
if [[ "$DO_UFW_HOOK" == "1" || "$DO_UFW_HOOK_REMOVE" == "1" ]]; then
    require_root "--ufw-hook / --ufw-hook-remove"
    echo "=============================================================="
    echo " INTÉGRATION UFW (/etc/ufw/after.init)"
    echo "=============================================================="
    if [[ "$DO_UFW_HOOK_REMOVE" == "1" ]]; then
        remove_ufw_hook
        exit 0
    fi
    if ! ufw_installed; then
        echo "${C_YELLOW}ufw n'est pas installé — crochet inutile (netfilter-persistent assure déjà la persistance).${C_RESET}"
        exit 0
    fi
    if [[ ! -s "$CACHE_LIST" ]]; then
        echo "${C_YELLOW}Aucune liste en cache : lancez d'abord une synchronisation (sans option), sinon le crochet${C_RESET}"
        echo "${C_YELLOW}n'aurait rien à restaurer au démarrage de ufw. Le crochet est quand même installé.${C_RESET}"
    fi
    install_ufw_hook
    echo "      Effet : au démarrage de ufw (boot, et rechargements qui vident les chaînes si MANAGE_BUILTINS=yes),"
    echo "      les ipsets sont restaurés depuis la liste en cache et les règles remises en tête de INPUT."
    echo "      Tester sans redémarrer : ufw reload && $0 --status"
    exit 0
fi

# --- --status ---------------------------------------------------------------------------------------------------------
if [[ "$DO_STATUS" == "1" ]]; then
    require_root "--status"
    echo "=============================================================="
    echo " ÉTAT ACTUEL"
    echo "=============================================================="
    if ! command -v ipset >/dev/null 2>&1; then
        echo "${C_YELLOW}ipset n'est pas installé — lancez ce script sans option pour l'installer.${C_RESET}"
        exit 0
    fi
    for set_name in "$IPSET_V4" "$IPSET_V6"; do
        if set_exists "$set_name"; then
            count=$(ipset list "$set_name" 2>/dev/null | awk '/^Members:/{m=1;next} m && NF{n++} END{print n+0}') || count=0
            echo "Ipset $set_name : ${C_GREEN}présent${C_RESET}, $count entrée(s)"
        else
            echo "Ipset $set_name : ${C_YELLOW}absent${C_RESET}"
        fi
    done
    for pair in "iptables:$IPSET_V4:IPv4" "ip6tables:$IPSET_V6:IPv6"; do
        IFS=: read -r tool set_name fam <<< "$pair"
        if rule_exists "$tool" "$set_name"; then
            echo "Règle $tool ($fam) : ${C_GREEN}présente${C_RESET}"
        else
            echo "Règle $tool ($fam) : ${C_YELLOW}absente${C_RESET}"
        fi
    done
    if ufw_installed; then
        echo "Persistance : via l'entrée @reboot du cron (ufw installé, netfilter-persistent volontairement absent)"
    elif command -v netfilter-persistent >/dev/null 2>&1; then
        echo "Persistance : ${C_GREEN}netfilter-persistent présent${C_RESET}"
    else
        echo "Persistance : ${C_YELLOW}aucune${C_RESET} (relancez sans option pour installer ipset-persistent)"
    fi
    if ufw_installed; then
        if ufw_hook_installed; then
            echo "Crochet ufw : ${C_GREEN}installé${C_RESET} ($UFW_AFTER_INIT)"
        else
            echo "Crochet ufw : ${C_YELLOW}absent${C_RESET} (--ufw-hook : restauration au démarrage de ufw, sans attendre le cron)"
        fi
    fi
    if [[ -f "$CRON_FILE" ]]; then
        echo "Cron : ${C_GREEN}installé${C_RESET} ($CRON_FILE)"
    else
        echo "Cron : ${C_YELLOW}absent${C_RESET} (--install-cron)"
    fi
    [[ -r "$LAST_SYNC_FILE" ]] && echo "Dernière synchronisation : $(cat "$LAST_SYNC_FILE")"
    if [[ -r "$FAILURE_FILE" ]]; then
        echo "${C_RED}ÉCHEC EN COURS : $(sed -n 's/^count=//p' "$FAILURE_FILE") tentative(s) consécutive(s) depuis le $(sed -n 's/^since=//p' "$FAILURE_FILE") (dernière : $(sed -n 's/^last=//p' "$FAILURE_FILE"))${C_RESET}"
        echo "${C_RED}  $(sed -n 's/^message=//p' "$FAILURE_FILE")${C_RESET}"
        echo "  Détail : tail -n 40 /var/log/sync-crowdsec-blocklist.log"
    fi
    prot=$(collect_protected_ips) || prot=""
    echo "IP protégées (jamais bloquées) : $(printf '%s\n' "$prot" | grep -c . || true) — $(printf '%s\n' "$prot" | paste -sd' ' -)"
    age=$(list_age_days)
    if [[ -n "$age" ]]; then
        if (( age >= STALE_DAYS )); then
            echo "Âge de la liste : ${C_YELLOW}inchangée depuis $age jour(s)${C_RESET} (seuil d'alerte : $STALE_DAYS)"
            warn_if_stale sans-journal
        else
            echo "Âge de la liste : dernier changement il y a $age jour(s) (seuil d'alerte : $STALE_DAYS)"
        fi
    fi
    exit 0
fi

# --- --blocked : IP reellement bloquees, cumul historique + compteurs depuis la derniere synchronisation --------------
if [[ "$DO_BLOCKED" == "1" ]]; then
    require_root "--blocked"
    echo "=============================================================="
    echo " IP RÉELLEMENT BLOQUÉES PAR LA LISTE CROWDSEC"
    echo "=============================================================="
    if ! command -v ipset >/dev/null 2>&1; then
        echo "${C_YELLOW}ipset n'est pas installé — rien à afficher.${C_RESET}"
        exit 0
    fi
    last_sync="(inconnue)"
    [[ -r "$LAST_SYNC_FILE" ]] && last_sync=$(cat "$LAST_SYNC_FILE")
    current=$( { read_counters "$IPSET_V4"; read_counters "$IPSET_V6"; } ) || true
    history=""
    [[ -r "$BLOCKED_DB" ]] && history=$(cat "$BLOCKED_DB")
    if [[ -z "$current" && -z "$history" ]]; then
        echo "${C_GREEN}Aucune IP de la liste n'a encore tenté de se connecter à ce serveur (ou les ipsets viennent d'être créés).${C_RESET}"
        exit 0
    fi
    # Fusion : historique cumule (jusqu'a la derniere synchro) + compteurs courants (depuis la derniere synchro).
    merged=$(awk -F'\t' -v OFS='\t' -v recent="depuis la synchro du $last_sync" '
        FNR == NR { if ($1 == "") next; p[$1] = $2; b[$1] = $3; f[$1] = $4; l[$1] = $5; next }
        { if ($1 == "") next
          if ($1 in p) { p[$1] += $2; b[$1] += $3 } else { p[$1] = $2; b[$1] = $3; f[$1] = recent }
          l[$1] = recent }
        END { for (ip in p) print p[ip], b[ip], ip, f[ip], l[ip] }
    ' <(printf '%s\n' "$history") <(printf '%s\n' "$current") | sort -t$'\t' -k1,1 -rn) || true
    n_total=$(printf '%s\n' "$merged" | grep -c . || true)
    echo "$n_total IP distincte(s) bloquée(s) à ce jour. Dernière synchronisation : $last_sync"
    echo
    printf '%-40s %10s %12s  %-38s %s\n' "IP" "PAQUETS" "OCTETS" "PREMIÈRE DÉTECTION" "DERNIÈRE DÉTECTION"
    if [[ "$TOP_N" -gt 0 ]]; then
        shown=$(printf '%s\n' "$merged" | head -n "$TOP_N") || true
    else
        shown="$merged"
    fi
    printf '%s\n' "$shown" | awk -F'\t' '{ printf "%-40s %10s %12s  %-38s %s\n", $3, $1, $2, $4, $5 }'
    if [[ "$TOP_N" -gt 0 && "$n_total" -gt "$TOP_N" ]]; then
        echo "(… $((n_total - TOP_N)) autre(s) — --top 0 pour tout afficher)"
    fi
    echo
    echo "Note : les dates sont celles de la synchronisation qui a constaté l'activité (un compteur ipset ne"
    echo "donne pas l'heure exacte de chaque paquet). Une IP bloquée n'atteint jamais nginx : elle n'apparaît"
    echo "donc dans AUCUN journal nginx — ce rapport est la seule trace de ces blocages."
    exit 0
fi

# --- --uninstall ------------------------------------------------------------------------------------------------------
if [[ "$DO_UNINSTALL" == "1" ]]; then
    require_root "--uninstall"
    echo "=============================================================="
    echo " DÉSINSTALLATION"
    echo "=============================================================="
    for pair in "iptables:$IPSET_V4" "ip6tables:$IPSET_V6"; do
        IFS=: read -r tool set_name <<< "$pair"
        while rule_exists "$tool" "$set_name"; do
            run "$tool" -D INPUT -m set --match-set "$set_name" src -j DROP || break
            echo "Règle $tool retirée ($set_name)."
        done
    done
    if command -v ipset >/dev/null 2>&1; then
        for set_name in "$IPSET_V4" "$IPSET_V6"; do
            if set_exists "$set_name"; then
                if run ipset destroy "$set_name" 2>/dev/null; then
                    echo "Ipset $set_name détruit."
                else
                    echo "${C_YELLOW}Impossible de détruire $set_name (encore référencé par une autre règle ?).${C_RESET}"
                fi
            fi
        done
    fi
    if ufw_hook_installed; then
        remove_ufw_hook
    fi
    if [[ -f "$CRON_FILE" ]]; then
        run rm -f "$CRON_FILE"
        echo "$CRON_FILE retiré."
    fi
    if [[ -d "$STATE_DIR" ]]; then
        run rm -rf "${STATE_DIR:?}"
        echo "$STATE_DIR (cache + historique des IP bloquées) retiré."
    fi
    # Sans cette resauvegarde, la sauvegarde persistante contiendrait encore les ipsets et regles retires, qui
    # reviendraient au prochain demarrage.
    save_persistent
    echo "Aucun paquet n'a été désinstallé (ipset, iptables-persistent, ipset-persistent restent en place)."
    exit 0
fi

# --- --install-cron ---------------------------------------------------------------------------------------------------
if [[ "$DO_INSTALL_CRON" == "1" ]]; then
    require_root "--install-cron"
    REAL_SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
    if (( CRON_HOURS == 1 )); then hour_field="*"; else hour_field="*/$CRON_HOURS"; fi
    {
        echo "# Généré par sync-crowdsec-blocklist.sh --install-cron — ne pas éditer à la main."
        echo "# PATH explicite : celui de cron (/usr/bin:/bin) ne contient ni ipset ni iptables (dans /usr/sbin)."
        echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        echo "# Synchronisation toutes les $CRON_HOURS heure(s), minute 17 (évite l'heure pile, où tout le monde tape la même source)."
        echo "17 $hour_field * * * root $REAL_SCRIPT_PATH >>/var/log/sync-crowdsec-blocklist.log 2>&1"
        echo "# Au démarrage : recrée ipsets et règles (depuis la dernière liste en cache si le réseau n'est pas encore prêt)."
        echo "@reboot root sleep 60 && $REAL_SCRIPT_PATH >>/var/log/sync-crowdsec-blocklist.log 2>&1"
    } > "$CRON_FILE"
    chmod 644 "$CRON_FILE"
    echo "Cron installé : $CRON_FILE (toutes les $CRON_HOURS heure(s) + au démarrage ; sortie dans /var/log/sync-crowdsec-blocklist.log)."
    exit 0
fi

# --- Synchronisation (mode normal ou --dry-run) --------------------------------------------------------------------------
if [[ "$DO_DRY_RUN" == "1" ]]; then
    TOTAL_STEPS=2
else
    require_root "La synchronisation" "Utilisez --dry-run pour tester sans privilège."
    TOTAL_STEPS=6
fi

echo "=============================================================="
if [[ "$DO_DRY_RUN" == "1" ]]; then
    echo " SYNCHRONISATION DE LA LISTE CROWDSEC (--dry-run : rien n'est modifié)"
else
    echo " SYNCHRONISATION DE LA LISTE CROWDSEC"
fi
echo "=============================================================="

STEP=0
if [[ "$DO_DRY_RUN" != "1" ]]; then
    trap 'fin_synchro $?' EXIT
    # Fichier cron d'une version anterieure (sans PATH) : complete sur place, une fois.
    if [[ -f "$CRON_FILE" ]] && ! grep_q '^PATH=' "$CRON_FILE"; then
        sed -i '1a # PATH explicite : celui de cron (/usr/bin:/bin) ne contient ni ipset ni iptables (dans /usr/sbin).\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' "$CRON_FILE"
        echo "      ${C_YELLOW}$CRON_FILE complété : PATH explicite (cause des échecs sous cron).${C_RESET}"
    fi
    STEP=$((STEP + 1)); step "$STEP" "$TOTAL_STEPS" "Vérification des paquets requis"
    ensure_packages
    # ipset utilisable ? Verifie AVANT de telecharger la liste (40 000 entrees) : un echec s'annonce tout de suite.
    if ! err_ipset=$(run ipset list -n 2>&1); then
        echec "$(printf 'ipset inutilisable : %s' "$(diagnostic_ipset "$err_ipset")")"
        exit 1
    fi
fi

STEP=$((STEP + 1)); step "$STEP" "$TOTAL_STEPS" "Téléchargement de $SOURCE_URL"
TMP_DOWNLOAD="$(mktemp)"
rc_fin=0
trap 'rc_fin=$?; rm -f "$TMP_DOWNLOAD" "${TMP_DOWNLOAD}.v4" "${TMP_DOWNLOAD}.v6"; fin_synchro "$rc_fin"' EXIT
download_ok=0
if [[ -t 1 && "$VERBOSE" != "1" ]]; then
    curl_display=(--progress-bar)
else
    curl_display=(-sS)
fi
if run curl -f "${curl_display[@]}" --max-time 60 "$SOURCE_URL" -o "$TMP_DOWNLOAD"; then
    download_ok=1
fi

USING_CACHE=0
if [[ "$download_ok" != "1" ]]; then
    # Repli sur la derniere liste connue UNIQUEMENT si les ipsets sont absents (cas typique : redemarrage, reseau
    # pas encore pret). Si les ipsets existent deja, ils contiennent deja cette liste — rien de mieux a faire que
    # les garder tels quels.
    if [[ "$DO_DRY_RUN" != "1" && -s "$CACHE_LIST" ]] && ! { set_exists "$IPSET_V4" && set_exists "$IPSET_V6"; }; then
        echo "      ${C_YELLOW}Téléchargement impossible — ipsets absents, restauration depuis la dernière liste en cache.${C_RESET}"
        cp "$CACHE_LIST" "$TMP_DOWNLOAD"
        USING_CACHE=1
    else
        echo "${C_RED}ERREUR: échec du téléchargement depuis $SOURCE_URL — ipsets actuels conservés tels quels.${C_RESET}" >&2
        exit 1
    fi
fi

STEP=$((STEP + 1)); step "$STEP" "$TOTAL_STEPS" "Analyse de la liste"
grep -E '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(/[0-9]{1,2})?$' "$TMP_DOWNLOAD" | grep -vE "$PRIVATE_V4_RE" > "${TMP_DOWNLOAD}.v4" || true
grep -E '^[0-9a-fA-F:]+:[0-9a-fA-F:]*(/[0-9]{1,3})?$' "$TMP_DOWNLOAD" | grep -vE "$PRIVATE_V6_RE" > "${TMP_DOWNLOAD}.v6" || true
count_v4=$(grep -c . "${TMP_DOWNLOAD}.v4" 2>/dev/null) || count_v4=0
count_v6=$(grep -c . "${TMP_DOWNLOAD}.v6" 2>/dev/null) || count_v6=0
total=$((count_v4 + count_v6))
echo "      $total entrée(s) valide(s) ($count_v4 IPv4, $count_v6 IPv6)."

if (( total < MIN_IPS )); then
    echo "${C_RED}ERREUR: seulement $total entrée(s) valide(s), en dessous du minimum attendu ($MIN_IPS — voir --min-ips).${C_RESET}" >&2
    echo "${C_RED}Symptôme typique d'un téléchargement raté silencieusement — mise à jour ANNULÉE pour ne pas${C_RESET}" >&2
    echo "${C_RED}débannir tout le monde par erreur. Aucun ipset n'a été modifié.${C_RESET}" >&2
    exit 1
fi

if [[ "$DO_DRY_RUN" == "1" ]]; then
    echo
    echo "Exemples (5 premières entrées de chaque famille) :"
    echo "  IPv4 :"; head -5 "${TMP_DOWNLOAD}.v4" | sed 's/^/    - /'
    echo "  IPv6 :"; head -5 "${TMP_DOWNLOAD}.v6" | sed 's/^/    - /'
    exit 0
fi

PROTECTED_FOR_SHA=$(collect_protected_ips) || PROTECTED_FOR_SHA=""
new_sha=$( { cat "$TMP_DOWNLOAD"; echo "#ip-protegees"; printf '%s\n' "$PROTECTED_FOR_SHA"; } | sha256sum | awk '{print $1}')
old_sha=""
[[ -r "$CACHE_SHA" ]] && old_sha=$(cat "$CACHE_SHA")
changed=0

STEP=$((STEP + 1)); step "$STEP" "$TOTAL_STEPS" "Mise à jour des ipsets"
if [[ "$USING_CACHE" != "1" && -n "$old_sha" && "$new_sha" == "$old_sha" ]] && set_exists "$IPSET_V4" && set_exists "$IPSET_V6"; then
    echo "      Liste identique à la précédente synchronisation — ipsets inchangés (compteurs conservés)."
    # Mise a jour depuis la version 1.1 : pas encore de date de dernier changement connue — on part de maintenant.
    [[ -r "$LAST_CHANGE_FILE" ]] || date +%s > "$LAST_CHANGE_FILE"
    warn_if_stale
else
    # Echec de creation typique dans un conteneur LXC non privilegie : le module noyau ip_set n'est pas charge sur
    # l'hote (un conteneur ne peut pas charger de module lui-meme).
    err_ipset=""
    if ! err_ipset=$(run ipset create "$IPSET_V4" hash:net family inet counters -exist 2>&1) \
       || ! err_ipset=$(run ipset create "$IPSET_V6" hash:net family inet6 counters -exist 2>&1); then
        # -exist echoue aussi si l'ipset existe avec des options differentes (version 1.0, sans compteurs) : ce cas
        # est gere plus bas par swap_or_replace — on ne s'arrete que si l'ipset n'existe vraiment pas.
        if ! set_exists "$IPSET_V4" || ! set_exists "$IPSET_V6"; then
            echec "$(printf 'impossible de créer les ipsets : %s' "$(diagnostic_ipset "$err_ipset")")"
            exit 1
        fi
    fi
    TMP_SET_V4="${IPSET_V4}-tmp"
    TMP_SET_V6="${IPSET_V6}-tmp"
    for s in "$TMP_SET_V4" "$TMP_SET_V6"; do
        set_exists "$s" && run ipset destroy "$s"
    done
    run ipset create "$TMP_SET_V4" hash:net family inet counters
    run ipset create "$TMP_SET_V6" hash:net family inet6 counters

    LOADED=0
    TOTAL_TO_LOAD=$total
    load_into_set "${TMP_DOWNLOAD}.v4" "$TMP_SET_V4"
    load_into_set "${TMP_DOWNLOAD}.v6" "$TMP_SET_V6"
    apply_protected "$TMP_SET_V4" "$TMP_SET_V6"

    # Cumul des compteurs de l'ipset actif AVANT l'echange (qui les remet a zero).
    accumulate_counters
    swap_or_replace "$TMP_SET_V4" "$IPSET_V4" iptables
    swap_or_replace "$TMP_SET_V6" "$IPSET_V6" ip6tables
    changed=1

    mkdir -p "$STATE_DIR"
    if [[ "$USING_CACHE" != "1" ]]; then
        cp "$TMP_DOWNLOAD" "$CACHE_LIST"
        if [[ "$new_sha" != "$old_sha" ]]; then
            date +%s > "$LAST_CHANGE_FILE"
        fi
        echo "$new_sha" > "$CACHE_SHA"
    fi
    echo "      ${C_GREEN}Ipsets à jour : $IPSET_V4 ($count_v4), $IPSET_V6 ($count_v6).${C_RESET}"
fi

STEP=$((STEP + 1)); step "$STEP" "$TOTAL_STEPS" "Règles iptables/ip6tables"
for pair in "iptables:$IPSET_V4:IPv4" "ip6tables:$IPSET_V6:IPv6"; do
    IFS=: read -r tool set_name fam <<< "$pair"
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "      ${C_YELLOW}$tool introuvable — règle $fam non appliquée.${C_RESET}"
    elif rule_exists "$tool" "$set_name"; then
        echo "      Règle $tool ($fam) déjà présente."
    else
        run "$tool" -I INPUT -m set --match-set "$set_name" src -j DROP
        echo "      ${C_GREEN}Règle $tool ($fam) ajoutée.${C_RESET}"
        changed=1
    fi
done

STEP=$((STEP + 1)); step "$STEP" "$TOTAL_STEPS" "Sauvegarde pour le redémarrage"
if [[ "$changed" == "1" ]]; then
    save_persistent
else
    echo "      Rien n'a changé — sauvegarde inutile."
fi

mkdir -p "$STATE_DIR"
date '+%Y-%m-%d %H:%M' > "$LAST_SYNC_FILE"
echo
echo "${C_GREEN}Synchronisation terminée.${C_RESET} Voir les IP réellement bloquées : $0 --blocked"
