# nginx-hardening.sh - audit et installation du serveur

Audite (par défaut) ou installe/répare (`--update`) la base du serveur en étapes numérotées. Rien n'est modifié sans `--update` ; chaque fichier modifié est d'abord sauvegardé. Fonctionne pour le profil Odoo et le profil BigBlueButton (`--app odoo|bbb`, détecté sinon ; l'audit dit « sans objet » là où une étape ne convient pas à l'application).

```bash
./nginx-hardening.sh --check --app odoo          # audit en lecture seule
./nginx-hardening.sh --update                    # appliquer (root ; pose quelques questions la première fois)
./nginx-hardening.sh --update --rename-to nouveau.example.org   # changement de nom DNS + nouveau certificat Let's Encrypt
```

## Étapes

| Étape | Sujet |
|---|---|
| 0 | programmes requis (`ss`, `curl`, `logrotate`, `fail2ban`, `iptables-persistent`) |
| 0a | nginx avant les changements (`nginx -t`, service) |
| 0b | fuseau horaire (`--timezone`) |
| 0c | répertoires de cache nginx (`proxy_cache_path`) |
| 0d | courriel des programmes : `msmtp`, relais SMTP demandé une fois, mot de passe demandé à part et jamais en option (`--mail-*`) |
| 0e | changement de nom DNS dans nginx et Let's Encrypt (`--rename-from/--rename-to`) |
| 1 | répertoire ACME `/var/www/letsencrypt` |
| 2 | journal du « catch-all » (capteur des requêtes vers un nom d'hôte inconnu) |
| 3 | page de maintenance |
| 4 | interface d'écoute d'Odoo et amonts nginx : le port de l'amont doit être celui d'Odoo ; vérifie l'amont websocket (discussion en direct), `proxy_http_version`, `proxy_read_timeout` ; les amonts d'une autre version d'Odoo ne sont ni vérifiés ni modifiés |
| 5 | pare-feu : ports HTTP/gevent d'Odoo bloqués depuis l'extérieur |
| 6 | suggestion de limite mémoire (`--workers` x RAM disponible) |
| 7 | audit de l'unité systemd d'Odoo et de `run.sh` |
| 8 | audit d'`odoo.conf` (`list_db`, `admin_passwd`, mode proxy, limites...) |
| 9 | jails fail2ban : capteur catch-all, `odoo-auth` (échecs de connexion lus dans le journal d'Odoo), `nginx-blocked-probes` (5 refus nginx en 10 minutes -> bannissement de 24 h) |
| 10 | HSTS réellement envoyé par chaque nom HTTPS (lu dans `nginx -T`) |
| 11 | rétention des journaux (`--log-retention-months`, 1 à 24, défaut 3) |
| 12 | listes d'adresses -> fragments nginx (`team-ips-geo.conf`, `team-ips-allow.conf`, `shared-ips-geo.conf`) ; nginx est rechargé si les fragments sont plus récents que la configuration chargée |
| 13 | courriel d'alerte : relais, MX, SPF, DMARC, DKIM |
| 14 | `geoip-bin` / `geoip-database` pour le pays en local |
| 15 | bip d'`app-log-live.py --chime` dans byobu/tmux |

## Notes pour les administrateurs

* **Fichier d'état.** `/etc/default/nginx-hardening.conf` est un fichier d'*état* écrit par le programme (réponses données, marqueurs générés) : ne pas le modifier à la main.
* **Jamais de `return` au niveau du `server`** dans un bloc qui ne fait que rediriger : mettre la redirection dans `location /` et inclure `snippets/securite-commune.conf`, sinon la redirection passe avant les règles de refus.
* **Adresses des clients** : `$remote_addr`, jamais `X-Forwarded-For`. Les journaux des sites utilisent le format `combined_host` ; les refus de nginx vont dans `/var/log/nginx/blocked-probes.log` pour que la jail `nginx-blocked-probes` de fail2ban les lise.
* **BigBlueButton.** Les règles de sécurité vont dans un seul fichier à nous (`/etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx`) ; aucun fichier géré par BBB n'est modifié. HAProxy y termine le TLS : HSTS utilise donc `http-after-response`. Il n'y a volontairement pas de capteur catch-all sur BBB. Voir `doc/bbb-upgrade.md` pour mettre BBB à jour sans perdre le durcissement (`--update` avant et après).
* **Droits.** `--check` fonctionne en utilisateur ordinaire avec un tableau incomplet ; `--update` est refusé aussitôt sans root, avant de prendre le verrou.

## Options
{{HELP}}
