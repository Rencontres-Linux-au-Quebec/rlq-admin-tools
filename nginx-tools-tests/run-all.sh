#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# Ce fichier fait partie de la configuration nginx de Rencontres Linux Quebec. Logiciel libre : vous pouvez le
# redistribuer et/ou le modifier selon les termes de la GNU Affero General Public License publiee par la Free
# Software Foundation, soit la version 3 de la licence, soit (a votre choix) toute version ulterieure.
# Texte complet : https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# run-all.sh - single launcher of the validation, to run BEFORE each deployment. One command, one verdict:
#   0) presence des programmes et du dossier apps/ (installation incomplete signalee, avec la commande a lancer) ;
#   1) syntaxe de tous les programmes (bash -n, python3 -m py_compile) ;
#   2) ShellCheck sur tous les scripts Bash (0 signalement attendu : les exceptions voulues sont documentees par des
#      directives dans le code) ;
#   3) ruff sur le Python, s'il est installe (equivalent de ShellCheck pour Python) ;
#   4) the test suite (unittest, included in Python), ONCE PER AVAILABLE AWK (mawk, gawk, BusyBox) - gawk and
#      mawk do not interpret awk programs the same way ("awk -v" bug of nginx-log-audit.sh 1.24, invisible
#      sous mawk) ;
#   5) configuration deployee (/etc/nginx, /etc/fail2ban) comparee a la version testee (nginx-tools-tests/nginx-odoo/), pour
#      information : les differences sont signalees sans entrer dans le verdict (serveurs Odoo seulement) ;
#   6) controles du serveur REEL, en lecture seule, propres a son environnement (BigBlueButton : apps/_bbb.py ; Odoo :
#      app-health-check.py --target local), pour information : ils n'entrent pas dans le verdict.
# L'ENVIRONNEMENT (Odoo ou BigBlueButton) est detecte au depart (apps/_profile.py, ou --app NOM) : chaque module de test porte
# a label ENVIRONNEMENT = "commun" | "odoo" | "bbb" and only the common modules and those of THIS environment
# tournent. Serveur non reconnu (poste de developpement) ou --all-environments : tous les modules.
# Outils cherches dans le PATH, puis dans nginx-tools-tests/tools/ (executables statiques deposes la, ex. shellcheck, gawk, ruff).
# Ce qui n'a PAS pu etre verifie (outil absent, tests exigeant root ou un terminal) est dit explicitement dans le verdict.
# A la fin, STATISTIQUES (stats_runner.py) : duree totale et par passe, CPU, memoire, disque, programmes lances, et par programme le nombre de tests
# unitaires, fonctionnels, interactifs et de conformite (nature MESUREE pendant chaque test), desactives et en echec, et les tests les plus lents.
#
#
# Usage : nginx-tools-tests/run-all.sh [-v|--verbose] [--version] [--changelog]
#   Code de sortie : 0 = tout ce qui a ete execute a reussi ; 1 = au moins un echec.

set -euo pipefail

# shellcheck disable=SC2154  # "ec" is set INSIDE the trap text (ec=$?), at run time (false positive).
trap 'ec=$?; echo "*** ARRÊT INATTENDU DE run-all.sh (code $ec) À LA LIGNE $LINENO : $BASH_COMMAND" >&2' ERR
# Ctrl+C: apps/_i18n.sh asks for confirmation ("Interrompre le programme ? [o/N]"); if yes, run_all_nettoyer stops the test pass (its own process group) before exiting.
JOB_PID=""
# shellcheck disable=SC2317,SC2329  # called indirectly: CTRL_C_NETTOYAGE (apps/_i18n.sh) and the TERM trap
run_all_nettoyer() {
    if [[ -n "$JOB_PID" ]]; then kill -TERM -- "-$JOB_PID" 2>/dev/null || true; fi
    echo >&2; echo "Interrompu (Ctrl+C) : arrêt de run-all.sh." >&2
}
# shellcheck disable=SC2034  # lue par apps/_i18n.sh
CTRL_C_NETTOYAGE=run_all_nettoyer
trap 'run_all_nettoyer; exit 143' TERM

readonly SCRIPT_VERSION="1.197.20261026.114649"
RUN_ALL_DEBUT=$(date +%s)
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly TESTS_DIR
PROG_DIR="${TEST_SCRIPTS_DIR:-$(dirname "$TESTS_DIR")}"; readonly PROG_DIR
# Journal : section de ce programme dans CHANGELOG.md (a la racine du depot).
CHANGELOG_FILE="$TESTS_DIR/../CHANGELOG.md"
readonly CHANGELOG_FILE

# Section of this program in CHANGELOG.md (from its "## <file name>" heading to the next "## " heading).
changelog_section() {
    awk -v cle="${BASH_SOURCE[0]##*/}" '/^## /{dans=($0 == "## " cle); if (dans) print; next} dans' "$CHANGELOG_FILE"
}
VERBOSE=0; APP_FORCE=""; TOUS_ENVIRONNEMENTS=0; LISTE_SEULE=0; INSTALLER_MANQUANTS=0

# Display language (en or fr): --lang, RUN_ALL_LANG, LANGUAGE of the configuration file, LC_ALL / LANG - apps/_i18n.sh translates the output (nothing changes in French).
if [[ -r "$PROG_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped with the programs
    . "$PROG_DIR/apps/_i18n.sh"
    i18n_relancer run-all RUN_ALL_LANG "$0" "$@"
    # The programs launched by the suite (and whose output is parsed) stay in French: only the output of run-all.sh is translated.
    [[ -n "${NGINX_TOOLS_I18N:-}" ]] && export NGINX_TOOLS_LANG=fr
    # Configuration file (/etc/default/run-all.conf THEN ~/.run-all.conf; -c/--config FILE: this file ONLY): default values of the options.
    # shellcheck disable=SC2034  # lue par apps/_i18n.sh (config_creer_defaut)
    CFG_DOSSIER_DOC="$TESTS_DIR/doc"; config_lire run-all "$@"        # first start: creates the configuration file (template: doc/run-all.conf.example)
    export NGINX_TOOLS_CONFIG_CREER=0                                  # the tested programs themselves never create a file in the real /etc/default
    config_defaut TOUS_ENVIRONNEMENTS ALL_ENVIRONMENTS --all-environments booleen
    config_defaut APP_FORCE APP --app texte
    config_defaut INSTALLER_MANQUANTS INSTALL_MISSING --install-missing booleen
    config_defaut VERBOSE VERBOSE --verbose booleen
fi

# --report-err: error report to copy and paste at the end of the run (program, version, server, failures...) - apps/_rapport.sh
if [[ -r "$PROG_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # library shipped next to the program
    . "$PROG_DIR/apps/_rapport.sh"
    rapport_si_demande "$TESTS_DIR/run-all.sh" "$SCRIPT_VERSION" "$PROG_DIR" "$@"
fi
# First line of EVERY run, even with --help: the name and version of the program (--version displays it itself).
case " $* " in *" --version "*) ;; *) echo "run-all.sh v$SCRIPT_VERSION" ;; esac
if declare -F config_afficher >/dev/null; then
    case " $* " in *" --version "*|*" --changelog "*) ;; *) config_afficher ;; esac
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        --all-environments) TOUS_ENVIRONNEMENTS=1; shift ;;
        --app) APP_FORCE="${2:-}"; [[ -n "$APP_FORCE" ]] || { echo "--app attend un nom (odoo, bbb…)" >&2; exit 1; }; shift 2 ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*|--lang=*) shift ;;
        --lang) shift 2 ;;
        --install-missing) INSTALLER_MANQUANTS=1; shift ;;
        --list) LISTE_SEULE=1; shift ;;
        --version) echo "run-all.sh version $SCRIPT_VERSION"; exit 0 ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then echo "Changelog introuvable : $CHANGELOG_FILE" >&2; exit 1; fi
            if [[ -t 1 ]]; then
                changelog_section | sed -E $'s/([0-9]+\\.[0-9]+\\.[0-9]{8}\\.[0-9]{6})/\\x1b[1;36m\\1\\x1b[0m/' || true  # lecteur ferme plus tot : SIGPIPE attendu
            else
                changelog_section || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            fi
            exit 0 ;;
        -h|--help)
            cat <<'AIDE'
Usage : nginx-tools-tests/run-all.sh [OPTION]...
Suite de validation : présence des programmes, syntaxe, ShellCheck, ruff, tests (un passage par awk), configuration.

Options (par ordre alphabétique) :
  --all-environments           exécuter les tests de TOUS les environnements (Odoo et BigBlueButton), quel que soit le serveur
  --app NAME                   environnement à tester : odoo, bbb… (profil apps/NAME.conf ; défaut : détecté sur ce serveur)
  --changelog                  affiche le journal des modifications
  -c, --config FILE            fichier de configuration à lire SEUL (défaut : /etc/default/run-all.conf puis ~/.run-all.conf)
  -h, --help                   affiche cette aide et quitte
  --install-missing            installer les logiciels de validation absents (ShellCheck par apt-get, ruff par apt-get ou pip) ; il faut être root
  --lang LANG                  langue d'affichage : en ou fr (défaut : selon LC_ALL / LC_MESSAGES / LANG)
  --list                       affiche l'environnement détecté et les modules de test retenus, sans rien exécuter
  --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
                               échecs, avertissements) ; désactive couleurs et questions interactives
  -v, --verbose                détail de chaque vérification
  --version                    affiche la version et quitte
AIDE
            exit 0
            ;;
        --report-err) shift ;;                 # handled before (apps/_rapport.sh); accepted here with --help, --version...
        *) echo "Argument inconnu : $1" >&2; exit 1 ;;
    esac
done

if [[ -t 1 ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_CYAN=$'\x1b[1;36m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_CYAN=""; C_RESET=""
fi
[[ -d "$TESTS_DIR/tools" ]] && export PATH="$TESTS_DIR/tools:$PATH"

# --install-missing: ShellCheck and ruff missing are installed (apt-get, otherwise pip for ruff); without this option, steps 2 and 3 are only skipped.
installer_manquants() {
    local cmd="$1" paquet="$2" pip_paquet="${3:-}"
    command -v "$cmd" >/dev/null 2>&1 && return 0
    if (( EUID != 0 )); then echo "  $cmd absent : --install-missing demande les droits root (sudo)." >&2; return 0; fi
    if command -v apt-get >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y "$paquet" >/dev/null 2>&1 && command -v "$cmd" >/dev/null 2>&1; then
        echo "  $cmd installé (paquet $paquet)."
    elif [[ -n "$pip_paquet" ]] && command -v pip3 >/dev/null 2>&1 && pip3 install --break-system-packages "$pip_paquet" >/dev/null 2>&1; then
        echo "  $cmd installé (pip $pip_paquet)."
    else
        echo "  Installation de $cmd en échec : apt-get install $paquet${pip_paquet:+ (ou pip3 install $pip_paquet)} et lire l'erreur." >&2
    fi
    return 0
}
if (( INSTALLER_MANQUANTS )); then
    installer_manquants shellcheck shellcheck
    installer_manquants ruff ruff ruff
fi

ECHECS=0
NON_VERIFIE=()
ok()   { echo "  ${C_GREEN}[OK]${C_RESET}    $1"; }
ko()   { echo "  ${C_RED}[ÉCHEC]${C_RESET} $1"; ECHECS=$((ECHECS + 1)); }
skip() { echo "  ${C_YELLOW}[IGNORÉ]${C_RESET} $1"; NON_VERIFIE+=("$1"); }
titre() { echo; echo "${C_CYAN}=== $1 ===${C_RESET}"; }
detail() { if [[ "$VERBOSE" == "1" ]]; then sed 's/^/      /'; else cat >/dev/null; fi; }

cd "$PROG_DIR"

# --- Environnement de CE serveur : Odoo ou BigBlueButton (profil apps/<nom>.conf, detecte ou force par --app) -------------
# ENV_APP vide = serveur non reconnu (poste de developpement, aucune ou plusieurs applications) : tous les modules tournent.
ENV_APP=""; ENV_LABEL=""; ENV_ORIGINE=""
if [[ -n "$APP_FORCE" ]]; then
    ENV_APP="$APP_FORCE"; ENV_LABEL="$APP_FORCE"; ENV_ORIGINE="forcé (--app)"
    if [[ ! -f "$PROG_DIR/apps/$APP_FORCE.conf" ]]; then
        profils=()
        for f in "$PROG_DIR"/apps/*.conf; do [[ -f "$f" ]] && profils+=("$(basename "$f" .conf)"); done
        echo "ERREUR : profil d'application inconnu : $APP_FORCE (profils : ${profils[*]:-aucun})" >&2
        exit 1
    fi
    ENV_LABEL=$(sed -n 's/^APP_LABEL="\(.*\)"/\1/p' "$PROG_DIR/apps/$APP_FORCE.conf" | head -1)
elif [[ -r "$PROG_DIR/apps/_profile.py" ]] && command -v python3 >/dev/null 2>&1; then
    detecte=$(cd "$PROG_DIR/apps" && python3 -c "import _profile; p = _profile.charger_profil_app('.', None); print(p['APP_NAME'] + '|' + p['APP_LABEL'])" 2>/dev/null) || detecte=""
    if [[ -n "$detecte" ]]; then ENV_APP=${detecte%%|*}; ENV_LABEL=${detecte#*|}; ENV_ORIGINE="détecté automatiquement"; fi
fi
if (( TOUS_ENVIRONNEMENTS )); then ENV_ORIGINE="${ENV_ORIGINE:+$ENV_ORIGINE ; }tous les environnements demandés (--all-environments)"; fi

# Test modules: the ENVIRONNEMENT = "..." label of each one (commun, odoo, bbb) decides whether it runs on this server.
MODULES=(); MODULES_ECARTES=(); ECARTES_ENV=""
for f in "$TESTS_DIR"/test_*.py; do
    m=$(basename "$f" .py)
    etiquette=$(sed -n 's/^ENVIRONNEMENT = "\([a-z0-9_-]*\)".*/\1/p' "$f" | head -1)
    etiquette=${etiquette:-commun}
    if [[ "$etiquette" == "commun" || -z "$ENV_APP" || "$etiquette" == "$ENV_APP" ]] || (( TOUS_ENVIRONNEMENTS )); then
        MODULES+=("$m")
    else
        MODULES_ECARTES+=("$m"); ECARTES_ENV="$etiquette"
    fi
done
if (( LISTE_SEULE )); then
    echo "Environnement : ${ENV_LABEL:-non reconnu (tous les modules sont retenus)}${ENV_APP:+ ($ENV_APP)}${ENV_ORIGINE:+ — $ENV_ORIGINE}"
    echo "Modules retenus (${#MODULES[@]}) : ${MODULES[*]}"
    echo "Modules écartés (${#MODULES_ECARTES[@]}) : ${MODULES_ECARTES[*]:-aucun}"
    exit 0
fi
mapfile -t BASH_PROGS < <(ls ./*.sh ./apps/*.sh 2>/dev/null; echo "$TESTS_DIR/run-all.sh")
mapfile -t PY_PROGS < <(ls ./*.py ./apps/*.py 2>/dev/null)
echo "Programmes : $PROG_DIR"
echo "Environnement : ${ENV_LABEL:-non reconnu}${ENV_APP:+ ($ENV_APP)}${ENV_ORIGINE:+ — $ENV_ORIGINE}"
if (( ${#MODULES_ECARTES[@]} > 0 )); then
    echo "  Tests propres à un autre environnement (${ECARTES_ENV}) non exécutés ici : ${MODULES_ECARTES[*]} — --all-environments pour tout exécuter"
fi

titre "0) Programmes présents dans $PROG_DIR"
# Installation incomplete (programmes absents) : le dire clairement ici, plutot que des sections vides et des dizaines
# de tests desactives un par un. Cas typique : nginx-tools.zip extrait (dossier nginx-tools/) sans l'etape de copie.
MANQUANTS=0
for attendu in nginx-hardening.sh nginx-log-audit.sh sync-crowdsec-blocklist.sh odoo-backup.sh odoo-update-module.sh app-health-check.py app-log-check.py \
               web-monitor.py zip-versions.py app-log-live.py odoo-mail-retry.py odoo-chat-post.py odoo-warmup.py host-perf-audit.py apps/_profile.sh apps/_profile.py apps/_rapport.sh apps/_rapport.py apps/_bbb.py \
               apps/_reseau.py apps/_odoo_db.py apps/_listes.py apps/_listes.sh apps/_cache_ip.py apps/_courriel.py apps/_email_check.py apps/_odoo_users.py apps/_sysperf.py apps/_i18n.py apps/_i18n.sh apps/_config.py apps/_traduire.py apps/config-entete.txt apps/odoo.conf apps/bbb.conf; do
    if [[ -f "$attendu" ]]; then
        [[ "$VERBOSE" == "1" ]] && ok "$attendu"
    else
        ko "$attendu absent"; MANQUANTS=$((MANQUANTS + 1))
    fi
done
if (( MANQUANTS == 0 )); then
    ok "tous les programmes et le dossier apps/ sont présents"
else
    if [[ -f nginx-tools/nginx-log-audit.sh ]]; then
        echo "      ${C_YELLOW}L'archive a été extraite dans $PROG_DIR/nginx-tools/ sans être copiée à sa place :${C_RESET}"
        echo "      cd $PROG_DIR && cp -r nginx-tools/* . && rm -rf nginx-tools"
    else
        echo "      ${C_YELLOW}Déployer l'archive : cd $PROG_DIR && unzip -o nginx-tools.<version>.zip && cp -r nginx-tools/* . && rm -rf nginx-tools${C_RESET}"
    fi
fi
# Old copy of THIS suite in tests/ (before 1.56: name shared with the tests of other programs, which
# overwrote each other): reported with the list of our files found there, never deleted here - the folder
# may contain the tests of other programs, sometimes under the same names (README.md, helpers.py...).
if [[ "$(basename "$TESTS_DIR")" != "tests" && -f tests/test_web_monitor.py && -f tests/run-all.sh ]]; then
    ancienne=$(sed -n 's/^readonly SCRIPT_VERSION="\(.*\)"/\1/p' tests/run-all.sh | head -1)
    communs=()
    for f in "$TESTS_DIR"/*; do
        if [[ "$(basename "$f")" != __pycache__ && -e "tests/$(basename "$f")" ]]; then communs+=("$(basename "$f")"); fi
    done
    echo "  ${C_YELLOW}[ATTN]${C_RESET}  ancienne copie de cette suite dans $PROG_DIR/tests/ (run-all.sh ${ancienne:-?}) : la suite est"
    echo "          maintenant dans $(basename "$TESTS_DIR")/ — à retirer de tests/ (${#communs[@]} nom(s) en commun : ${communs[*]:0:8}…)"
fi

# RESIDUAL files of old versions: an archive extracted over an old folder removes nothing from it. These files (personal address lists,
# generated on each server) are no longer shipped; their presence makes tests fail (test_locks, test_multi_app, test_listes)
# for a reason that is not a defect of the code. Reported with the exact command, never deleted here.
RESIDUELS=()
for f in "$PROG_DIR/apps/team-ips.list" "$TESTS_DIR/nginx-odoo/snippets/team-ips-geo.conf" "$TESTS_DIR/nginx-odoo/snippets/team-ips-allow.conf" \
         "$PROG_DIR/nginx-odoo/snippets/team-ips-geo.conf" "$PROG_DIR/nginx-odoo/snippets/team-ips-allow.conf"; do
    [[ -f "$f" ]] && RESIDUELS+=("$f")
done
# 1.182: old catalogue lang/PROGRAM.en.po of a program that moved to English code (its lang/PROGRAM.fr.po declares Source-Language en): cp -r does not
# erase it, and it skews the translations (French text in the English display) and test_i18n.
# General rule: a catalogue in the program's SOURCE language (declared by the Source-Language header of its French catalogue) is residual.
for f in "$PROG_DIR"/lang/*.po; do
    lg=${f%.po}; lg=${lg##*.}; base=${f%."$lg".po}
    [[ -f "$f" && "$lg" != fr && -f "$base.fr.po" ]] && grep -q "^\"Source-Language: $lg" "$base.fr.po" && RESIDUELS+=("$f")
done
# 1.186: the test suite NEVER modifies the programs' folder (it only proposed, but that was outside its folder): residual files
# are reported, with the command to remove them, and the tests continue (old lang/PROG.en.po are no longer read: apps/_i18n.py 1.15).
if (( ${#RESIDUELS[@]} > 0 )); then
    echo "  ${C_YELLOW}[ATTN]${C_RESET}  fichier(s) résiduel(s) d'une ancienne version (plus livrés, lus par aucun programme) :"
    printf '          %s\n' "${RESIDUELS[@]}"
    echo "          Ils peuvent être retirés sans risque : rm -f ${RESIDUELS[*]}"
    echo "          (un lang/PROG.en.po date de l'époque où PROG était écrit en français ; PROG est écrit en anglais et lit lang/PROG.fr.po ; aucun autre programme ne le lit)"
fi

titre "1) Syntaxe"
for f in "${BASH_PROGS[@]}"; do
    if out=$(bash -n "$f" 2>&1); then ok "bash -n $(basename "$f")"; else ko "bash -n $(basename "$f") : $out"; fi
done
for f in "${PY_PROGS[@]}"; do
    if out=$(python3 -m py_compile "$f" 2>&1); then ok "py_compile $(basename "$f")"; else ko "py_compile $(basename "$f") : $out"; fi
done

titre "2) ShellCheck"
if command -v shellcheck >/dev/null 2>&1; then
    for f in "${BASH_PROGS[@]}"; do
        out=$(shellcheck -f gcc "$f" 2>&1) || true
        if [[ -z "$out" ]]; then ok "shellcheck $(basename "$f") : 0 signalement"
        else ko "shellcheck $(basename "$f") : $(printf '%s\n' "$out" | grep -c .) signalement(s)"; printf '%s\n' "$out" | sed 's/^/      /'; fi
    done
else
    skip "ShellCheck non installé (relancer avec --install-missing, ou apt install shellcheck, ou exécutable statique dans nginx-tools-tests/tools/)"
fi

titre "3) ruff (analyse du Python)"
if command -v ruff >/dev/null 2>&1; then
    # E9/F: syntax errors and real defects (undefined names, unused imports or variables...) - not the style.
    if out=$(ruff check --select E9,F --target-version py38 --no-cache --output-format concise "${PY_PROGS[@]}" "$TESTS_DIR"/*.py 2>&1); then ok "ruff : aucun défaut"
    else ko "ruff : défauts trouvés"; printf '%s\n' "$out" | sed 's/^/      /'; fi
else
    skip "ruff non installé (relancer avec --install-missing, ou pipx install ruff, ou exécutable statique dans nginx-tools-tests/tools/)"
fi

titre "4) Suite de tests (une fois par awk disponible) — ${#MODULES[@]} module(s) : commun${ENV_APP:+ + $ENV_APP}"
TMP_AVANT=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'test-rlq-*' 2>/dev/null | sort) || true
# Sentinel: the suite must NEVER create or modify a REAL configuration file (/etc/default, ~). Fingerprint before/after:
# on a server these files legitimately exist - only a change DURING the suite is a fault.
# Legacy personal names (rule before 1.191: personal files ended with .cfg; the programs rename them .conf): a test must never rename a real one.
ANCIENS_NOMS=("${HOME:-/root}/.app-health-check.cfg" "${HOME:-/root}/.odoo-backup.cfg" "${HOME:-/root}/.app-default.cfg")    # legacy names
empreinte_configs() {
    local f
    for f in /etc/default/app-health-check.conf /etc/default/odoo-backup.conf /etc/default/nginx-hardening.conf \
             /etc/default/sanity-check-odoo.conf "${HOME:-/root}/.app-health-check.conf" "${HOME:-/root}/.odoo-backup.conf" \
             ${ANCIENS_NOMS[@]+"${ANCIENS_NOMS[@]}"} \
             /var/lib/nginx-tools/bbb-state.json /var/lib/nginx-tools/bbb-state.json.before \
             /etc/default/nginx-tools-mail.conf /etc/default/nginx-tools-mail.pass /etc/msmtprc \
             /etc/default/nginx-tools-white-list.conf /etc/default/nginx-tools-ip-location.conf /var/lib/nginx-tools/ip-cache.sqlite \
             /var/lib/nginx-tools/odoo-users.tsv; do
        # 1.190: file unreadable without root (mode 600): size and modification date (stat), which also change if a test writes it
        if [[ -r "$f" ]]; then sha256sum "$f"; elif [[ -e "$f" ]]; then echo "illisible $(stat -c '%s %Y' "$f" 2>/dev/null)  $f"; else echo "absent  $f"; fi
    done
}
CONFIGS_AVANT=$(empreinte_configs)
MARQUE_SYSTEME=$(mktemp)                                         # 1.190: any file of /etc or /var/backups modified AFTER this point is examined at the end
AWKS=()
for a in mawk gawk original-awk; do command -v "$a" >/dev/null 2>&1 && AWKS+=("$(command -v "$a")"); done
BB_WRAP=""
if command -v busybox >/dev/null 2>&1 && busybox awk 'BEGIN{}' 2>/dev/null; then
    BB_WRAP="$(mktemp -d)/awk-busybox"; printf '#!/bin/sh\nexec busybox awk "$@"\n' > "$BB_WRAP"; chmod +x "$BB_WRAP"; AWKS+=("$BB_WRAP")
fi
[[ ${#AWKS[@]} -eq 0 ]] && AWKS+=("$(command -v awk)")
STATS_DIR=$(mktemp -d); STATS_FICHIERS=()                    # 1.188: statistics of each pass (stats_runner.py), displayed at the end
LANCEUR=(python3 -W ignore -m unittest)                         # fallback without stats_runner.py (old suite): same tests, without statistics
for a in "${AWKS[@]}"; do
    rc=0
    nom=$(basename "$a"); nom=${nom#awk-}
    if [[ -r "$TESTS_DIR/stats_runner.py" ]]; then
        STATS_FICHIERS+=("$STATS_DIR/passe-${#STATS_FICHIERS[@]}-$nom.json")
        LANCEUR=(python3 -W ignore "$TESTS_DIR/stats_runner.py" --run "${STATS_FICHIERS[-1]}")
    fi
    # The pass runs in ITS OWN session (setsid): the terminal's Ctrl+C does not reach it, run-all's confirmation decides (no -> the pass continues, without a false test).
    sortie_passe=$(mktemp)
    (cd "$TESTS_DIR" && TEST_AWK="$a" TEST_SCRIPTS_DIR="$PROG_DIR" exec setsid "${LANCEUR[@]}" "${MODULES[@]}" -v >"$sortie_passe" 2>&1) &
    JOB_PID=$!
    while :; do
        wait "$JOB_PID" && rc=0 || rc=$?
        kill -0 "$JOB_PID" 2>/dev/null || break              # "wait" interrupted by the Ctrl+C question: the pass is still running, we wait for it again
    done
    JOB_PID=""
    res=$(cat "$sortie_passe"); rm -f "$sortie_passe"
    bilan=$(printf '%s\n' "$res" | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' ')
    if [[ $rc -eq 0 ]]; then ok "tests sous $nom : $bilan"; printf '%s\n' "$res" | detail
    else
        # Each failing test is rerun ALONE: confirmed failure (blocking), or UNSTABLE test - it passes only alone
        # (dependency on order or timing): reported, with its complete message kept in last-instable.log.
        confirmes=(); instables=()
        while IFS= read -r id; do
            [[ -z "$id" ]] && continue
            if (cd "$TESTS_DIR" && TEST_AWK="$a" TEST_SCRIPTS_DIR="$PROG_DIR" python3 -W ignore -m unittest "$id" >/dev/null 2>&1); then
                instables+=("$id")
            else
                confirmes+=("$id")
            fi
        done < <(printf '%s\n' "$res" | sed -nE 's/^(FAIL|ERROR): ([A-Za-z0-9_]+) \(([A-Za-z0-9_.]+)\).*/\2 \3/p' \
                 | awk '{ id = $2; if (id !~ ("\\." $1 "$")) id = id "." $1; print id }' | sort -u)
        if (( ${#confirmes[@]} > 0 || ${#instables[@]} == 0 )); then
            ko "tests sous $nom : $bilan"
            # 1.190: sed reads ALL the input (no "head"): otherwise grep receives SIGPIPE and "set -o pipefail" + the ERR trap stopped run-all.sh
            printf '%s\n' "$res" | grep -E '^(FAIL|ERROR):|AssertionError|Error:' | sed -n '1,40s/^/      /p'
        else
            ok "tests sous $nom : tous réussis une fois relancés seuls"
        fi
        if (( ${#instables[@]} > 0 )); then
            {
                echo "=== $(date '+%Y-%m-%d %H:%M:%S') — run-all.sh v$SCRIPT_VERSION — awk : $nom — $(hostname)"
                for id in "${instables[@]}"; do
                    printf '%s\n' "$res" | awk -v t="${id##*.}" '/^(FAIL|ERROR): / { garde = index($0, t) > 0 } /^-{10,}$/ && garde && vu++ { garde = 0 } garde'
                done
            } >> "$TESTS_DIR/last-instable.log"
            for id in "${instables[@]}"; do
                echo "  ${C_YELLOW}[INSTABLE]${C_RESET} $id : a échoué dans la suite, réussi seul — détail : $TESTS_DIR/last-instable.log"
            done
        fi
    fi
    # Disabled tests: the real REASON, given by each test (-v: "... skipped 'reason'"), once per reason.
    if [[ "$a" == "${AWKS[0]}" ]]; then
        while IFS= read -r ligne; do
            [[ -z "$ligne" ]] && continue
            skip "$ligne"
        done < <(printf '%s\n' "$res" | grep -oE "skipped '[^']*'" | sed -E "s/^skipped '(.*)'$/\1/" | sort | uniq -c \
                 | sed -E 's/^ *([0-9]+) (.*)$/\1 test(s) désactivé(s) : \2/')
    fi
done
[[ -n "$BB_WRAP" ]] && rm -rf "$(dirname "$BB_WRAP")"
# Filet de securite : repertoires temporaires des tests restes dans /tmp (test interrompu, processus tue...). Seuls
# those CREATED DURING THIS PASS are deleted - never those of another running pass or of another user.
TMP_APRES=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'test-rlq-*' 2>/dev/null | sort) || true
RESTES=$(comm -13 <(printf '%s\n' "$TMP_AVANT") <(printf '%s\n' "$TMP_APRES") | grep . || true)
CONFIGS_APRES=$(empreinte_configs)
# 1.190: SYSTEM files modified during the suite. A test must NEVER write outside its folder: a file that names a test folder
# (/tmp/test-rlq-...) comes from a test = failure; the others (a service of the machine may have written during that time) = for information.
ECRITS_PAR_TESTS=(); ECRITS_AUTRES=()
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if grep -qs 'test-rlq-' "$f"; then ECRITS_PAR_TESTS+=("$f"); else ECRITS_AUTRES+=("$f"); fi
done < <(find /etc /var/backups -xdev -type f -newer "$MARQUE_SYSTEME" 2>/dev/null | sort)
rm -f "$MARQUE_SYSTEME"
if (( ${#ECRITS_PAR_TESTS[@]} > 0 )); then
    ko "la suite de tests a ÉCRIT ${#ECRITS_PAR_TESTS[@]} fichier(s) du système (ils nomment un dossier de test) — à supprimer :"
    printf '      %s\n' "${ECRITS_PAR_TESTS[@]}"
fi
if (( ${#ECRITS_AUTRES[@]} > 0 )); then
    echo "  [INFO]  ${#ECRITS_AUTRES[@]} fichier(s) de /etc ou /var/backups modifié(s) pendant la suite, sans lien avec un test (un service de la machine) : ${ECRITS_AUTRES[*]:0:5}"
fi
if [[ "$CONFIGS_AVANT" != "$CONFIGS_APRES" ]]; then
    ko "la suite de tests a MODIFIÉ un fichier de configuration réel (elle doit tout rediriger vers un dossier temporaire) :"
    diff <(printf '%s\n' "$CONFIGS_AVANT") <(printf '%s\n' "$CONFIGS_APRES") | grep '^[<>]' | sed 's/^/      /' || true
    echo "      Cause la plus probable : un programme réel (ex. nginx-hardening.sh --update) lancé PENDANT la suite, dans un autre terminal. Aucun test n'écrit ces fichiers (vérifié avec strace) : relancer la suite sans rien d'autre."
fi
if [[ -n "$RESTES" ]]; then
    n_restes=$(printf '%s\n' "$RESTES" | grep -c .)
    while IFS= read -r r; do rm -rf "${r:?}"; done <<< "$RESTES"
    echo "  ${C_YELLOW}[NETTOYÉ]${C_RESET} $n_restes répertoire(s) temporaire(s) de test laissé(s) dans /tmp — supprimé(s)"
fi
for requis in mawk gawk; do
    command -v "$requis" >/dev/null 2>&1 || skip "$requis absent : les différences d'interprétation awk ne sont pas couvertes (apt install $requis)"
done

titre "5) Configuration déployée comparée à la version testée (nginx-tools-tests/nginx-odoo/)"
# Derive de deploiement : fichiers de /etc/nginx et /etc/fail2ban differents de la configuration testee. Signale
# seulement (une difference peut etre voulue, ex. liste d'IP de l'equipe) : n'entre pas dans le verdict.
REF="${NGINX_ODOO_DIR:-$TESTS_DIR/nginx-odoo}"                   # 1.188: private configuration, outside the Git repository (local copy)
if [[ -n "$ENV_APP" && "$ENV_APP" != "odoo" ]]; then
    echo "  [INFO]  sans objet pour $ENV_LABEL : cette configuration nginx est celle des serveurs Odoo"
elif [[ ! -d /etc/nginx ]]; then
    echo "  [INFO]  pas de /etc/nginx sur cette machine — comparaison sans objet"
elif [[ ! -d "$REF" ]]; then
    echo "  [INFO]  $REF absent — comparaison impossible"
else
    n_id=0; n_abs=0; n_diff=0
    while IFS='|' read -r src dst; do
        [[ -f "$src" ]] || continue
        if [[ ! -e "$dst" ]]; then n_abs=$((n_abs + 1)); continue; fi
        if cmp -s "$src" "$dst"; then n_id=$((n_id + 1))
        else n_diff=$((n_diff + 1)); echo "  ${C_YELLOW}[ATTN]${C_RESET}  différent de la version testée : $dst"; fi
    done < <(
        cd "$REF" && find conf.d snippets sites-available -type f -name '*.conf' 2>/dev/null | sed "s#.*#$REF/&|/etc/nginx/&#"
        for f in "$REF"/fail2ban/*.filter.conf; do [[ -f "$f" ]] && echo "$f|/etc/fail2ban/filter.d/$(basename "$f" .filter.conf).conf"; done
        [[ -f "$REF/fail2ban/nginx-catchall.jail.conf" ]] && echo "$REF/fail2ban/nginx-catchall.jail.conf|/etc/fail2ban/jail.d/nginx-catchall.conf"
        [[ -f "$REF/maintenance/index.html" ]] && echo "$REF/maintenance/index.html|/var/www/maintenance/index.html"
    )
    echo "  [INFO]  $n_id fichier(s) identique(s), $n_diff différent(s), $n_abs absent(s) de ce serveur (normal pour ceux d'un autre environnement)"
    (( n_diff > 0 )) && echo "          Voir une différence : diff <fichier testé> <fichier déployé> ; déployer : voir nginx-tools-tests/nginx-odoo/README.md"
fi

titre "6) Contrôles du serveur réel, en lecture seule (${ENV_LABEL:-environnement non reconnu})"
# Checks SPECIFIC to the environment, done on THIS server (steps 1 to 4 test the code with simulated commands).
# For information: the state of a server is not a defect of the code, so nothing here enters the verdict.
controle_reel() {          # controle_reel LABEL COMMAND...: [OK]/[ATTN]/[FAIL] lines of the output, in a summary
    local libelle="$1" sortie n_fail n_attn; shift
    sortie=$(timeout --foreground 300 "$@" 2>&1) || true
    n_fail=$(printf '%s\n' "$sortie" | grep -cE '^\s*(\x1b\[[0-9;]*m)?\[(FAIL|ÉCHEC)\]' || true)
    n_attn=$(printf '%s\n' "$sortie" | grep -cE '^\s*(\x1b\[[0-9;]*m)?\[ATTN\]' || true)
    echo "  [INFO]  $libelle : $n_fail échec(s), $n_attn avertissement(s) sur ce serveur"
    printf '%s\n' "$sortie" | grep -E '^\s*(\x1b\[[0-9;]*m)?\[(FAIL|ÉCHEC|ATTN)\]' | sed -n '1,8s/^/          /p'
}
case "$ENV_APP" in
    bbb)
        if [[ -r apps/_bbb.py ]]; then
            controle_reel "BigBlueButton : versions, nos règles chargées, API, client HTML5, HSTS (apps/_bbb.py --summary)" \
                python3 apps/_bbb.py --summary
        else
            echo "  [INFO]  apps/_bbb.py absent : contrôles de BigBlueButton impossibles"
        fi ;;
    odoo)
        if [[ -r app-health-check.py ]]; then
            controle_reel "Odoo : nginx et application (app-health-check.py --target local)" \
                python3 app-health-check.py --target local --app odoo
        else
            echo "  [INFO]  app-health-check.py absent : contrôles d'Odoo impossibles"
        fi ;;
    *) echo "  [INFO]  environnement non reconnu : aucun contrôle de serveur réel (--app NOM pour en choisir un)" ;;
esac

# 1.188: statistics (duration, resources, number of tests per program and per kind) - the table is written IN THE DISPLAY LANGUAGE by
# stats_runner.py (widths computed after translation: columns aligned in French as in English)
if (( ${#STATS_FICHIERS[@]} > 0 )); then
    python3 "$TESTS_DIR/stats_runner.py" --total "$(( $(date +%s) - RUN_ALL_DEBUT ))" --report "${STATS_FICHIERS[@]}" || true
fi
[[ -n "${STATS_DIR:-}" ]] && rm -rf "$STATS_DIR"
echo
echo "=============================================================="
if (( ECHECS > 0 )); then
    echo "${C_RED} VERDICT : $ECHECS ÉCHEC(S) — ne pas déployer.${C_RESET}"
elif (( ${#NON_VERIFIE[@]} > 0 )); then
    echo "${C_YELLOW} VERDICT : tout ce qui a été exécuté réussit — mais ${#NON_VERIFIE[@]} point(s) NON vérifié(s) (voir [IGNORÉ]).${C_RESET}"
else
    echo "${C_GREEN} VERDICT : TOUT PASSE — validation complète.${C_RESET}"
fi
echo "=============================================================="
# explicit "exit": a final "(( ECHECS == 0 ))" false triggered the ERR trap (false "UNEXPECTED STOP").
if (( ECHECS > 0 )); then exit 1; fi
exit 0
