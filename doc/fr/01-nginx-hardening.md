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
| 4 | interface d'écoute d'Odoo et amonts nginx : le port de l'amont doit être celui d'Odoo ; vérifie l'amont websocket (discussion en direct), `proxy_http_version`, `proxy_read_timeout` ; les amonts d'une autre version d'Odoo ne sont ni vérifiés ni modifiés ; 2.89 : sur un serveur Odoo, `--update` règle `worker_connections` de nginx à 2048 (`WORKER_CONNECTIONS`, bloc `events` de nginx.conf : chaque websocket de la discussion occupe 2 connexions) et ajoute `worker_rlimit_nofile` s'il manque ; copie avant, `nginx -t`, rechargement sans couper personne; 2.91 : vérifie ce que nginx écrit sur le disque : tampons des réponses (`proxy_buffers`, 1 Mo conseillé), fichiers temporaires et cache en mémoire (`/dev/shm`), cache des images d'Odoo (`/web/image` : seulement celles qu'Odoo déclare publiques) |
| 5 | pare-feu : ports HTTP/gevent d'Odoo bloqués depuis l'extérieur |
| 6 | suggestion de limite mémoire : la RAM disponible (au moins 15 % gardés pour PostgreSQL et le système, 10 % de marge) partagée entre les workers, les tâches planifiées (`max_cron_threads`, `--cron-threads`) et le processus gevent (2.82). 2.85 : Odoo compare ses limites à la mémoire **virtuelle** ; la limite suggérée est la part de RAM plus la mémoire virtuelle sans RAM mesurée sur les workers (environ 400 Mo), et `limit_memory_soft` ne descend jamais sous 1024 Mo ni sous 1,5 × un worker au repos (sinon moins de workers sont suggérés). Une limite actuelle sous un worker au repos est un échec : les workers sont recyclés dès leur démarrage, en boucle. 2.86 : contrôle des limites du processus gevent de la discussion en direct (`limit_memory_soft_gevent` 2147483648, `limit_memory_hard_gevent` 2684354560 conseillés : sans elles il prend la limite des workers et redémarre quand beaucoup de monde discute, ce qui coupe toutes les discussions) ; quand la RAM est juste, la quantité de mémoire à ajouter pour garder les workers à 1536 Mo (limite dure), et une alerte si moins de 15 % de la mémoire est disponible. Même calcul que le risque de mémoire d'app-log-live.py |
| 7 | audit de l'unité systemd d'Odoo et de `run.sh` |
| 8 | audit d'`odoo.conf` (`list_db`, `admin_passwd`, mode proxy, limites...) ; 2.87 : le fichier lu comme Odoo le lit (`apps/_odoo_conf_check.py`) : un commentaire après une valeur (`limit_memory_soft_gevent = 2147483648 # 2048 Mo`) reste DANS la valeur et Odoo ne démarre plus ; aussi clé donnée deux fois, valeur du mauvais type, clés inconnues d'Odoo et lecture par l'Odoo du serveur. Vérification seule : `python3 apps/_odoo_conf_check.py /opt/odoo/erplibre/config.conf` |
| 9 | jails fail2ban : capteur catch-all, `odoo-auth` (échecs de connexion lus dans le journal d'Odoo), `nginx-blocked-probes` (5 refus nginx en 10 minutes -> bannissement de 24 h) |
| 10 | HSTS réellement envoyé par chaque nom HTTPS (lu dans `nginx -T`) |
| 11 | rétention des journaux (`--log-retention-months`, 1 à 24, défaut 3) ; journal systemd persistant (`JOURNAL_PERSISTENT`, 2.83) : les raisons d'un arrêt d'Odoo survivent à un redémarrage |
| 12 | listes d'adresses -> fragments nginx (`team-ips-geo.conf`, `team-ips-allow.conf`, `shared-ips-geo.conf`) ; nginx est rechargé si les fragments sont plus récents que la configuration chargée |
| 13 | courriel d'alerte : relais, MX, SPF, DMARC, DKIM |
| 14 | `geoip-bin` / `geoip-database` pour le pays en local |
| 15 | bip d'`app-log-live.py --chime` dans byobu/tmux |
| 16 | appels d'Odoo vers son propre nom public (User-Agent python-requests) |
| 17 | PostgreSQL (2.83, `PG_LOGGING`, `PG_SLOW_MS`) : requêtes de plus de 2 s, verrous attendus, autovacuum et fichiers temporaires écrits dans le journal de PostgreSQL (fichier `conf.d/90-nginx-hardening-logging.conf`, rechargé sans redémarrage ; le texte des requêtes lentes y figure) ; `shared_buffers` resté à 128 Mo est signalé; 2.91 (`PG_TUNING`) : mémoire et points de contrôle montés selon la mémoire du serveur pour moins d'accès au disque (`shared_buffers` RAM/10, 4 Go au plus ; `effective_cache_size` RAM/2 ; `work_mem` ; `maintenance_work_mem` ; `checkpoint_timeout` 15 min ; `max_wal_size` 4 Go ; `wal_compression`) dans `conf.d/91-nginx-hardening-memory.conf` ; une valeur n'est que montée ; `shared_buffers` demande un redémarrage de PostgreSQL (question dans un terminal) |

## Notes pour les administrateurs

* **Fichier d'état.** `/etc/default/nginx-hardening.conf` est un fichier d'*état* écrit par le programme (réponses données, marqueurs générés) : ne pas le modifier à la main.
* **Jamais de `return` au niveau du `server`** dans un bloc qui ne fait que rediriger : mettre la redirection dans `location /` et inclure `snippets/securite-commune.conf`, sinon la redirection passe avant les règles de refus.
* **Adresses des clients** : `$remote_addr`, jamais `X-Forwarded-For`. Les journaux des sites utilisent le format `combined_host` ; les refus de nginx vont dans `/var/log/nginx/blocked-probes.log` pour que la jail `nginx-blocked-probes` de fail2ban les lise.
* **BigBlueButton.** Les règles de sécurité vont dans un seul fichier à nous (`/etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx`) ; aucun fichier géré par BBB n'est modifié. HAProxy y termine le TLS : HSTS utilise donc `http-after-response`. Il n'y a volontairement pas de capteur catch-all sur BBB. Voir `doc/bbb-upgrade.md` pour mettre BBB à jour sans perdre le durcissement (`--update` avant et après).
* **Droits.** `--check` fonctionne en utilisateur ordinaire avec un tableau incomplet ; `--update` est refusé aussitôt sans root, avant de prendre le verrou.

## Options
{{HELP}}
