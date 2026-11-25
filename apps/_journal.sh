# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Library (sourced by nginx-hardening.sh): journal of the files the tools install, so that the base configuration can be
# put back (--revert-base). One line per file, tab-separated: ACTION, FILE, BACKUP COPY ("-" if none), DATE.
#   ACTION : creer (file created by the tools: removed on revert) or remplacer (file replaced: the copy is put back).
# Safeguards: only files under the roots in NGINX_TOOLS_JOURNAL_ROOTS are recorded or restored; a created file is
# removed only by its own journal line.
# shellcheck shell=bash

JOURNAL_FICHIER="${NGINX_TOOLS_JOURNAL:-/var/lib/nginx-tools/installed-files.tsv}"
JOURNAL_RACINES="${NGINX_TOOLS_JOURNAL_ROOTS:-/etc/nginx /etc/fail2ban /etc/logrotate.d /etc/systemd}"

journal_sous_racine_autorisee() {       # $1 file : 0 if it is under one of the allowed roots
    local chemin="$1" racine
    for racine in $JOURNAL_RACINES; do
        case "$chemin" in "$racine"/*) return 0 ;; esac
    done
    return 1
}

journal_ajouter() {                      # $1 creer|remplacer, $2 file, $3 backup copy ("" if none): 1 if refused
    local action="$1" fichier="$2" copie="${3:-}"
    [[ "$action" == creer || "$action" == remplacer ]] || return 1
    journal_sous_racine_autorisee "$fichier" || return 1
    [[ -n "$copie" ]] || copie="-"
    mkdir -p "$(dirname "$JOURNAL_FICHIER")" 2>/dev/null || return 1
    printf '%s\t%s\t%s\t%s\n' "$action" "$fichier" "$copie" "$(date +%Y%m%d-%H%M%S)" >> "$JOURNAL_FICHIER" || return 1
}

journal_preparer() {                     # $1 file about to be created or replaced: copies it first, then records it; 1 if refused or failed
    local fichier="$1" action=creer copie=""
    journal_sous_racine_autorisee "$fichier" || return 1
    if [[ -e "$fichier" ]]; then
        action=remplacer
        copie="$fichier.before-revert-$(date +%Y%m%d-%H%M%S)"
        cp -p -- "$fichier" "$copie" || return 1
    fi
    journal_ajouter "$action" "$fichier" "$copie"
}

journal_restaurer() {                    # [--dry-run] : puts back the files, newest entry first; lines on stdout; 1 if an error
    local dry="${1:-}" action fichier copie date rc=0 i
    local -a lignes=()
    if [[ ! -r "$JOURNAL_FICHIER" ]]; then
        echo "aucun journal ($JOURNAL_FICHIER) : rien à restaurer"
        return 0
    fi
    mapfile -t lignes < "$JOURNAL_FICHIER"
    for (( i=${#lignes[@]}-1; i>=0; i-- )); do
        IFS=$'\t' read -r action fichier copie date <<< "${lignes[$i]}"
        if ! journal_sous_racine_autorisee "$fichier"; then
            echo "refusé (hors des racines autorisées) : $fichier"; rc=1; continue
        fi
        case "$action" in
            creer)
                if [[ -n "$dry" ]]; then
                    echo "retirer $fichier"
                elif [[ -e "$fichier" ]]; then
                    if rm -f -- "$fichier"; then echo "retiré $fichier"; else echo "échec : retrait de $fichier"; rc=1; fi
                else
                    echo "déjà absent : $fichier"
                fi ;;
            remplacer)
                if [[ ! -e "$copie" ]]; then
                    echo "copie absente, non restauré : $fichier (attendu : $copie)"; rc=1
                elif [[ -n "$dry" ]]; then
                    echo "restaurer $copie vers $fichier"
                elif cp -p -- "$copie" "$fichier"; then
                    echo "restauré $fichier"
                else
                    echo "échec : restauration de $fichier"; rc=1
                fi ;;
            *)
                echo "ligne de journal inconnue ignorée : $action"; rc=1 ;;
        esac
    done
    return $rc
}

journal_archiver() {                     # after a successful revert: the journal is kept under another name, never deleted
    [[ -e "$JOURNAL_FICHIER" ]] || return 0
    mv -- "$JOURNAL_FICHIER" "$JOURNAL_FICHIER.reverted-$(date +%Y%m%d-%H%M%S)"
}
