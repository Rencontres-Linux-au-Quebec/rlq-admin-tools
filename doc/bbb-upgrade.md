# Mettre à jour BigBlueButton sans perdre le durcissement nginx

Ce qui nous appartient sur un serveur BBB, et pourquoi une mise à jour ne l'écrase pas :

| Fichier | Rôle | Écrasé par une mise à jour de BBB ? |
|---|---|---|
| `/etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx` | règles de sécurité (fichiers cachés, PHP, WordPress... refusés en 404) | **Non** : aucun paquet ne le possède (vérifié par `dpkg -S` à chaque passage) ; BBB inclut `*.nginx` de ce dossier |
| `/etc/fail2ban/jail.d/nginx-blocked-probes.conf`, `filter.d/nginx-blocked-probes.conf`, `jail.d/zz-nginx-hardening-ignoreip.local` | bannissement des scanners | Non (fail2ban n'est pas un paquet de BBB) |
| `/etc/logrotate.d/nginx` | 3 mois de journaux | Fichier du paquet nginx : en cas de nouvelle version, dpkg garde la nôtre par défaut - vérifié au passage suivant |
| HSTS dans `/etc/haproxy/haproxy.cfg` (`http-after-response`) | ajouté À LA MAIN (conseil de l'étape 10) | **Peut-être** : `bbb-install.sh` peut régénérer ce fichier - détecté et signalé `[FAIL] HSTS retiré` |

Aucun fichier géré par BBB n'est modifié par nos outils.

## Procédure (2.7 et 3.0)

1. **Avant** : `./nginx-hardening.sh --update` - à la fin, l'état de BBB (versions, empreinte de sa configuration et de la
   nôtre) est enregistré dans `/var/lib/nginx-tools/bbb-state.json` : c'est la référence. Une réunion de test si le dernier
   passage remonte à loin.
2. **Mise à jour de BBB**, dans la même série : `apt update && apt upgrade` (ou `bbb-install.sh` avec les MÊMES arguments
   qu'à l'installation, par ex. `-v focal-270` pour 2.7, `-v jammy-300` pour 3.0). Passer de 2.7 à 3.0 change de version
   d'Ubuntu (20.04 -> 22.04) : c'est une nouvelle installation, pas une mise à jour sur place.
3. **Après** : `./nginx-hardening.sh --update`. - Section **AVANT ce passage** : ce que la mise à jour a changé - version de BBB, paquets, Greenlight, fichiers de
     configuration de BBB modifiés, et surtout si l'un des NÔTRES a disparu ou si le HSTS de HAProxy a été retiré. - Les étapes réappliquent nos règles si besoin (`nginx -t` avant tout rechargement ; ancienne version restaurée sinon). - Section **APRÈS ce passage** : compatibilité - nos règles chargées par nginx (`nginx -T`), `nginx -t`, l'API de BBB
     (`/bigbluebutton/api` -> 200 SUCCESS), le client HTML5 et l'accueil joignables (pas un 404 de nos règles), HSTS,
     `bbb-conf --check` ; puis le nouvel état est enregistré.
4. **Une réunion de test** : caméra, micro, partage d'écran (WebRTC : aucun outil ne peut le vérifier à notre place).
5. `web-monitor.py --summary` montre en permanence la même section ; si BBB a changé depuis le dernier `--update`, il le
   recommande et propose de le lancer.

## Si quelque chose ne fonctionne plus

Pour savoir si nos règles sont en cause : déplacer `zz-nginx-hardening-security.nginx` hors du dossier, `nginx -t && systemctl
reload nginx`, refaire l'essai ; le remettre ensuite (`nginx-hardening.sh --update`). Joindre le rapport
`nginx-hardening.sh --update --report-err` à la discussion.

## Instantané « ignoré »

Si `--update` annonce « Instantané ... ignoré : il décrit d'autres emplacements de fichiers », c'est un instantané écrit par une exécution de test ou une
ancienne installation : il est sans valeur et sera remplacé par ce `--update`. Rien à effacer à la main.
