# shellcheck shell=bash
# ========================================================================================================================
# Copyright (C) 2026  Services-Conseils Linux
# Licence : GNU Affero General Public License, version 3 ou ultérieure — https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _listes.sh — lecteur commun (bash) de la LISTE BLANCHE et des LIEUX : même fichiers et même syntaxe que apps/_listes.py (voir son en-tête).
#   /etc/default/nginx-tools-white-list.conf (seulement /etc/default), /etc/default/nginx-tools-ip-location.conf puis ~/.nginx-tools-ip-location.cfg.
# À sourcer (". apps/_listes.sh") ; ne fait rien tout seul.
#
# HISTORIQUE DE VERSION (resume — voir doc/_listes.changelog.txt pour le detail complet) :
#   1.0.20261007.093208 — Premiere version : liste blanche et lieux, lecteur commun (remplace les analyseurs de team-ips.list).

LISTES_BLANCHE_DEFAUT="/etc/default/nginx-tools-white-list.conf"
LISTES_LIEUX_DEFAUT="/etc/default/nginx-tools-ip-location.conf"
LISTES_SEP=$'\037'             # séparateur des champs de listes_lire (jamais une tabulation : read la fusionne quand un champ est vide)

# listes_fichier_blanche : chemin de la liste blanche LUE — le nouveau fichier ; à défaut, l'ancienne liste apps/team-ips.list
# (transition, seulement sans surcharge d'environnement) ; rien si aucun n'existe.
listes_fichier_blanche() {
    local nouveau="${NGINX_TOOLS_WHITE_LIST:-$LISTES_BLANCHE_DEFAUT}" ancien="${SCRIPT_DIR:-.}/apps/team-ips.list"
    if [[ -f "$nouveau" ]]; then printf '%s\n' "$nouveau"
    elif [[ -z "${NGINX_TOOLS_WHITE_LIST:-}" && -f "$ancien" ]]; then printf '%s\n' "$ancien"
    fi
}

# listes_fichiers_lieux : chemins des fichiers de lieux existants (un seul si NGINX_TOOLS_IP_LOCATION est défini), un par ligne.
listes_fichiers_lieux() {
    local f
    if [[ -n "${NGINX_TOOLS_IP_LOCATION:-}" ]]; then
        [[ -f "$NGINX_TOOLS_IP_LOCATION" ]] && printf '%s\n' "$NGINX_TOOLS_IP_LOCATION"
    else
        for f in "$LISTES_LIEUX_DEFAUT" "$HOME/.nginx-tools-ip-location.cfg"; do [[ -f "$f" ]] && printf '%s\n' "$f"; done
    fi
    return 0
}

# listes_lire FICHIER : une ligne par entrée, « ADRESSE LIBELLÉ OPTIONS NUMÉRO-DE-LIGNE » séparés par le caractère 037 (octal : jamais une tabulation, que read fusionnerait quand un champ est vide) (options : partagee, protegee,
# separées par des virgules ; « inconnue:xxx » pour une option inconnue). L'adresse n'est PAS validée ici (voir listes_adresse_valide).
listes_lire() {
    local fichier="$1" ligne adr com opts reste opt lib n=0
    [[ -r "$fichier" ]] || return 0
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        n=$((n + 1)); ligne=${ligne%$'\r'}
        [[ "$ligne" =~ ^[[:space:]]*(#|$) ]] && continue
        adr=${ligne%%#*}; read -r adr _ <<< "$adr"
        com=""; if [[ "$ligne" == *"#"* ]]; then com=${ligne#*#}; fi
        opts=""; reste=$com
        while [[ "$reste" =~ \[([^]]*)\] ]]; do
            opt=${BASH_REMATCH[1],,}; opt=${opt//é/e}; opt=${opt## }; opt=${opt%% }
            case "$opt" in
                partagee|protegee) opts+="${opts:+,}$opt" ;;
                *) opts+="${opts:+,}inconnue:$opt" ;;
            esac
            reste=${reste/"${BASH_REMATCH[0]}"/}
        done
        lib=${reste#"${reste%%[![:space:]]*}"}; lib=${lib%"${lib##*[![:space:]]}"}
        printf '%s\037%s\037%s\037%s\n' "$adr" "$lib" "$opts" "$n"
    done < "$fichier"
    return 0
}

# listes_adresse_valide ADRESSE : adresse ou plage IPv4/IPv6 de forme correcte (jamais écrite dans nginx sinon : il refuserait toute sa configuration).
listes_adresse_valide() {
    [[ "$1" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?$ || "$1" =~ ^[0-9a-fA-F]*:[0-9a-fA-F]*:[0-9a-fA-F:]*(/[0-9]{1,3})?$ ]]
}

# listes_valides : filtre (entrée standard -> sortie standard) : ne garde que les entrées dont l'adresse est de forme correcte.
listes_valides() {
    local ligne adr
    while IFS= read -r ligne; do
        adr=${ligne%%$'\037'*}
        if listes_adresse_valide "$adr"; then printf '%s\n' "$ligne"; fi
    done
    return 0
}

# listes_blanche : entrées de la liste blanche (format de listes_lire).
listes_blanche() {
    local f
    f=$(listes_fichier_blanche)
    [[ -n "$f" ]] && listes_lire "$f"
    return 0
}

# listes_lieux : entrées de tous les fichiers de lieux (format de listes_lire).
listes_lieux() {
    local f
    while IFS= read -r f; do [[ -n "$f" ]] && listes_lire "$f"; done < <(listes_fichiers_lieux)
    return 0
}

# listes_ne_pas_bannir : adresses à ne JAMAIS bannir (liste blanche + lieux [protégée]), une par ligne, sans doublon, adresses valides seulement.
listes_ne_pas_bannir() {
    { listes_blanche | listes_valides | cut -d "$LISTES_SEP" -f1
      listes_lieux | listes_valides | awk -F'\037' '$3 ~ /protegee/ { print $1 }'
    } | awk 'NF && !vu[$0]++'
}

# listes_resume : la ligne « Listes : … » (fichiers lus et nombre d'adresses valides), pour la sortie d'erreur des programmes.
listes_resume() {
    local fb nb nl lieux a b
    fb=$(listes_fichier_blanche); lieux=$(listes_fichiers_lieux | paste -sd, - | sed 's/,/, /g')
    nb=$(listes_blanche | listes_valides | grep -c . || true); nl=$(listes_lieux | listes_valides | grep -c . || true)
    if [[ -n "$fb" ]]; then
        a="liste blanche $fb ($nb adresse(s))"
        if [[ "$fb" == */apps/team-ips.list ]]; then a+=" — ANCIEN emplacement, à migrer : nginx-hardening.sh --update"; fi
    else a="liste blanche : aucun fichier"; fi
    if [[ -n "$lieux" ]]; then b="lieux $lieux ($nl plage(s))"; else b="lieux : aucun fichier"; fi
    printf 'Listes : %s ; %s\n' "$a" "$b"
}
