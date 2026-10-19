#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026  Services-Linux Conseils Inc <Martial@Bigras.ca> <Martial.Bigras@Services-Conseils-Linux.com>
#
# Ce fichier fait partie de la configuration nginx de Rencontres Linux Quebec. Logiciel libre : vous pouvez le
# redistribuer et/ou le modifier selon les termes de la GNU Affero General Public License publiee par la Free
# Software Foundation, soit la version 3 de la licence, soit (a votre choix) toute version ulterieure.
# Texte complet : https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# nginx-hardening.sh — installation initiale idempotente : répertoires (ACME, journal catch-all, page de
# maintenance), et pare-feu (bloque l'accès externe direct aux ports HTTP/gevent d'Odoo, qui contournerait TOUTES
# les règles nginx si laissé ouvert). Sûr à relancer plusieurs fois — chaque étape vérifie l'état actuel avant
# d'agir, rien n'est dupliqué. SANS DANGER PAR DÉFAUT : sans --update explicite, ne fait QUE vérifier, ne modifie
# jamais rien. Ne modifie JAMAIS odoo.conf lui-même (juste un diagnostic + une recommandation) : ce fichier a un
# format et des commentaires propres à chaque installation, trop risqué à éditer à l'aveugle.
#
# HISTORIQUE DE VERSION (résumé — voir nginx-hardening.changelog.txt pour le détail complet de chaque version) :
#   2.49.20261016.173838 — Ctrl+C works during the e-mail and BBB checks (timeout --foreground)
#   2.48.20261015.143436 — --anonymize : affichage anonymisé (pseudonymes stables).
#   2.47.20261015.080630 — Le refus sans root (--update) précède le verrou.
#   2.46.20261013.205851 — Étape 4 : les amonts d'une autre version d'Odoo (odoo17, odoo17_chat) ne sont ni vérifiés ni modifiés.
#   2.45.20261013.203700 — Websocket : la variable de proxy_pass ($odoo_backend_chat) est résolue ; lecture des blocs corrigée.
#   2.44.20261013.195358 — Étape 4 : vérification du websocket d'Odoo (discussions en temps réel) et correction de proxy_http_version / proxy_read_timeout.
#   2.43.20261013.163324 — Nouvelle étape 0a : nginx -t et état du service AVANT les changements, avec aide pour corriger.
#   2.42.20261013.161254 — Étape 0e : --rename-to seul, l'ancien nom est trouvé dans les server_name de nginx.
#   2.41.20261013.153600 — Étape 0d : question « faire le setup du courriel maintenant ? [o/N] » (non par défaut).
#   2.40.20261013.150500 — Étape 0d : les questions du courriel sont posées même si la sortie est redirigée ; introduction et message clair sans terminal.
#   2.39.20261013.123500 — Étape 0e : changement de nom DNS (nginx et certificat Let's Encrypt) ; options --rename-from et --rename-to.
#   2.38.20261013.103000 — Étape 0d : courriel des programmes (msmtp, relais SMTP demandé une fois, mot de passe à part) ; options --mail-*.
#   2.37.20261013.100000 — Étape 4 : le port des amonts nginx doit être celui d'Odoo ; --update le corrige.
#   2.36.20261013.091500 — « Quoi faire » traduit en anglais (HSTS).
#   2.35.20261012.231200 — iptables-persistent installé si les règles ne sont pas enregistrées ; page de maintenance cherchée dans /etc/nginx/maintenance ; unités de mémoire et textes anglais.
#   2.34.20261012.220800 — Fuseau horaire (--timezone, America/Montreal), dossier de cache nginx, rotation du journal d'Odoo (logrotate), ExecStart direct, sortie anglaise complète.
#   2.33.20261012.213000 — Étape 0 : installe les programmes manquants (ss, curl, logrotate, fail2ban ; iptables-persistent) ; service Odoo déduit de db_user.
#   2.32.20261012.195500 — Configuration d'Odoo détectée (--odoo-conf-paths) : application reconnue comme Odoo, ports du pare-feu et journal (logfile) lus dans la configuration ; étape 11b.
#   2.31.20261012.103600 — Fichier de configuration créé au premier démarrage (toutes les options en commentaire) ; modèle doc/nginx-hardening.conf.example complété.
#   2.30.20261011.181500 — Étape 12b : shared-ips-geo.conf généré depuis les lieux [partagée] (limites de débit plus larges pour une salle derrière une adresse).
#   2.29.20261011.144500 — ShellCheck SC2002 (cat inutile) corrigé ; Ctrl+C : confirmation avant de quitter (apps/_i18n.sh).
#   2.28.20261011.133251 — Étape 12 : recharge nginx si team-ips-*.conf sont plus récents que la configuration chargée (adresse ajoutée mais refusée en 403).
#   2.27.20261010.215000 — Affichage francais ou anglais (--lang) ; fichier de configuration (LANGUAGE et options, lignes SETUP_* conservees) et -c/--config.
#   2.26.20261009.170830 — Verification d'odoo-auth : test sur TEXTE (journalctl puis fail2ban-regex) ; adresse de l'equipe ignoree par la jail.
#   2.25.20261009.150500 — Etape 16 : curl -A python-requests/2.31 vers le nom public (/mass_mailing_themes) ; 403 = le filtre anti-robots bloque Odoo lui-meme.
#   2.24.20261009.104326 — Etape 15 : quelle configuration de byobu/tmux changer pour le bip de app-log-live.py --chime.
#   2.23.20261008.120306 — Couleurs conservees avec --report-err ; fichiers team-ips-* listes si nginx -t refuse.
#   2.22.20261008.112757 — Etape 12 : team-ips-geo.conf et team-ips-allow.conf EXISTENT toujours (nginx refuse un include a joker sans fichier) ; jamais de rm.
#   2.21.20261008.113500 — Etape 12 : si nginx -t refuse, affiche son message et dit si la configuration etait DEJA invalide avant les adresses.
#   2.20.20261007.093208 — Listes en /etc/default : migration de apps/team-ips.list, modeles, generation nginx, ignoreip (liste blanche + lieux proteges).
#   2.19.20261002.214327 — Etape 14 : geoip-bin (recommande, installe par --update) ; Premiere ligne de TOUTE execution (meme --help) : nom et version.
#   2.18.20261002.073514 — --verbose transmis a apps/_bbb.py ; section BigBlueButton protegee des instantanes d'autres emplacements.
#   1.0.20260922.081216 — Version initiale : répertoires (letsencrypt, catch-all log, maintenance), pare-feu
#                          (ufw ou iptables selon disponibilité) pour les ports 10000/10002, diagnostic de
#                          l'interface d'écoute d'Odoo (ss), fichier d'état pour --check.
#   1.1.20260922.194104 — Fichier d'état déplacé vers /etc/default/rlq-nginx-odoo-setup.conf (convention Debian
#                          standard pour ce type de fichier), au lieu de /etc/ directement.
#   1.2.20260922.195656 — Trois nouvelles étapes (diagnostic seulement, jamais d'édition automatique) :
#                          (6) calcule des limites limit_memory_soft/hard suggérées à partir du nombre de workers
#                          réel et de la RAM réellement disponible (via MemoryCurrent du cgroup Odoo, pas une
#                          estimation à l'aveugle), et compare à la valeur actuellement configurée si trouvable ;
#                          (7) audite l'unité systemd d'Odoo et son script de démarrage (Wants=network-online,
#                          limite anti-boucle-de-redémarrage, NoNewPrivileges, exec avant le binaire réel,
#                          coquilles connues) ; (8) audite odoo.conf (proxy_mode, list_db, admin_passwd faible).
#                          Nouvelles options --odoo-service, --odoo-conf, --workers.
#   1.3.20260922.222513 — --odoo-conf auto-détecte maintenant /opt/odoo/erplibre/config.conf (PROD) puis
#                          /home/mathben/git/erplibre/config.conf (DEV) avant le repli générique
#                          /etc/odoo/odoo.conf. La vérification de --limit-memory-hard=0 dans run.sh ignore
#                          maintenant la ligne du mode test (--log-level=test) : ces runs sont courts et ponctuels
#                          (--stop-after-init), une limite illimitée y est normale, pas un vrai problème.
#   1.4.20260922.225003 — Correctif critique : deux affectations dans l'étape 7 (extraction d'ExecStart=) n'avaient
#                          pas de "|| true" — si l'unité systemd n'avait pas d'ExecStart= trouvable tel quel (ex.
#                          format inattendu), le script s'arrêtait net AVANT d'écrire le fichier d'état, sans que
#                          la cause soit évidente. L'exclusion de la ligne --log-level=test s'applique maintenant
#                          à TOUTES les vérifications de run.sh (exec, coquille ORIGIN_CONFIG_PATH, limite
#                          mémoire), pas seulement la dernière. L'étape 7 utilise "systemctl cat" plutôt que lire
#                          directement le fichier d'unité, pour inclure les éventuels drop-ins (sinon un réglage
#                          ajouté via override, ex. NoNewPrivileges, était signalé à tort comme absent). La
#                          recommandation finale sur http_interface ne s'affiche plus que si un port est
#                          réellement exposé (étape 4) — elle apparaissait à tort pour n'importe quel échec.
#   1.5.20260922.225452 — Correctif critique : les étapes 1-3 (répertoires ACME/maintenance, journal catch-all)
#                          plantaient tout le script si un répertoire parent attendu (ex. /var/log/nginx) n'existe
#                          pas — un cas réel si nginx n'est pas encore installé, ou installé ailleurs. Chaque
#                          mkdir/touch/cp/chown est maintenant vérifié explicitement, avec un message d'erreur
#                          clair (FAIL ou ATTN selon la gravité) plutôt qu'un arrêt brutal via le trap ERR.
#   1.6.20260922.230500 — Le fichier d'état est maintenant nommé d'après le nom réel du script (basename sans
#                          .sh) plutôt qu'un nom fixe "rlq-nginx-odoo-setup.conf" — devient
#                          /etc/default/nginx-hardening.conf tel que livré. Le changelog est résolu de la même
#                          façon.
#   1.7.20260922.232142 — CHANGEMENT DE COMPORTEMENT PAR DÉFAUT : sans option, le script fait maintenant une
#                          VÉRIFICATION SEULE (comme --check) — plus sûr par défaut. Nouvelle option --update
#                          pour appliquer réellement les changements (l'ancien comportement par défaut). --check
#                          reste accepté (no-op désormais, gardé pour compatibilité explicite et pour les appels
#                          existants de nginx-log-audit.sh/app-health-check.py). Root n'est requis que pour
#                          --update.
#   1.8.20260923.075125 — Correctif : l'étape 6 (limites mémoire) ne regardait QUE odoo.conf pour la valeur
#                          actuelle de limit_memory_hard, ignorant qu'un --limit-memory-hard en ligne de commande
#                          dans run.sh (priorité Odoo standard : CLI > fichier de config) rend la valeur
#                          d'odoo.conf inutilisée en pratique. L'étape 6 vérifie maintenant d'abord la ligne de
#                          production de run.sh (même exclusion de --log-level=test que l'étape 7, partagée via
#                          une résolution commune faite une seule fois désormais) avant de se rabattre sur
#                          odoo.conf, et indique clairement la source retenue dans son message. Messages internes
#                          "relancer sans --check" (devenus faux depuis la 1.7) corrigés vers "--update".
#   1.9.20260923.155021 — Nouvelle étape 9 : installe un jail fail2ban dédié au capteur catch-all
#                          (odoo-catchall-444.log), invisible de tous les jails existants (leur glob
#                          "*access*.log" ne matche jamais ce nom de fichier). Crée deux fichiers NEUFS et
#                          autonomes (filter.d/nginx-catchall.conf, jail.d/nginx-catchall.conf) — jamais de
#                          modification de jail.local ou d'un fichier existant. Fichiers source livrés dans
#                          fail2ban/ à côté de ce script.
#   1.10.20260924.063613 — Nouvelle étape 10 : audit HSTS via "nginx -T" (config active fusionnée, tous les
#                          include() developpes) sur CHAQUE bloc server en écoute 443, pas seulement les vhosts
#                          servant du contenu — regression test direct du bug HSTS absent sur le bloc non-canonique
#                          de PROD, corrigé dans les fichiers de config nginx livrés séparément. Diagnostic
#                          seulement, jamais d'édition automatique d'un fichier de config existant.
#   1.11.20260924.083650 — L'étape 9 (jail fail2ban catch-all) recharge maintenant fail2ban automatiquement
#                          ("fail2ban-client reload") après une installation réussie en --update, plutôt que de
#                          se contenter d'un rappel affiché — contrairement à un redémarrage d'Odoo (jamais
#                          automatique, interruption réelle), un reload fail2ban est rapide et sans impact sur
#                          le trafic web.
#   1.12.20260924.085519 — Deux correctifs suite a un rapport reel : (1) l'etape 6 prenait parfois la valeur
#                          --limit-memory-hard d'une LIGNE COMMENTEE plus bas dans run.sh (ex. une vieille
#                          invocation laissee en reference) plutot que la vraie ligne de production active — les
#                          lignes commencant par # sont maintenant exclues de toutes les verifications basees sur
#                          run.sh, en plus de la ligne --log-level=test deja exclue. (2) L'etape 10 (HSTS) signalait
#                          a tort le capteur catch-all interne (server_name "_", qui ferme la connexion en 444 sans
#                          jamais servir de contenu — HSTS n'a pas de sens ici) : desormais jamais signale. Un bloc
#                          443 sans AUCUN server_name (probablement le site par defaut Debian encore actif) est
#                          maintenant distingue clairement, avec suggestion de le desactiver plutot que de lui
#                          ajouter HSTS.
#   1.13.20260924.113852 — Correctif suite a un rapport reel : le message de l'etape 10 nommait
#                          /etc/nginx/sites-enabled/default comme cause probable du bloc 443 sans server_name,
#                          alors que ce fichier n'existe pas chez l'utilisateur (seuls 00-catchall-default.conf et
#                          le vhost de l'instance sont actifs) — message rendu neutre, invite a verifier soi-meme
#                          via "nginx -T" plutot que de presumer une cause non confirmee. Etape 9 (jail fail2ban) :
#                          cherche maintenant les fichiers source a DEUX emplacements (/etc/nginx/fail2ban/ en
#                          premier, puis a cote du script) — le README ne documentait jusqu'ici aucun emplacement
#                          precis pour le dossier fail2ban/ du zip, et l'utilisateur l'avait logiquement place sous
#                          /etc/nginx/ comme le reste du zip, ce que le script ne cherchait pas. README mis a jour
#                          pour documenter explicitement cet emplacement.
#   1.14.20260924.203547 — Etape 10 refaite en test EMPIRIQUE (curl HTTPS local par nom, avec SNI) : les versions
#                          1.10 a 1.13 supposaient a tort que "nginx -T" developpe les include() — il affiche en
#                          realite chaque fichier separement, d'ou de faux [FAIL]/[ATTN] sur des vhosts dont le
#                          server_name et le HSTS viennent de snippets inclus. Nouvelle option -v/--verbose.
#   1.15.20260925.162700 — Message list_db (etape 8) corrige : il affirmait a tort que la liste des bases etait deja
#                          protegee par nginx. Il liste maintenant les URL reservees aux IP autorisees et celles qui
#                          restent publiques (/web/database/list si l'ancienne regle nginx est active, /jsonrpc dans
#                          tous les cas), avec la marche a suivre (list_db = False en PROD).
#   1.16.20260926.075558 — Etape 9 : nouveau jail fail2ban odoo-auth (echecs de connexion lus dans le journal d'Odoo),
#                          GENERE pour ce serveur (service, namespace de journal, liste blanche nginx en ignoreip) ;
#                          verification que chaque jail est reellement CHARGE par fail2ban. Course SIGPIPE de
#                          « | grep -q » corrigee (grep_q), dont « nginx -T | grep -q » (sortie volumineuse).
#   1.17.20260926.125259 — ShellCheck 0.11.0 : aucun signalement, a tous les niveaux (constantes affectees puis
#                          declarees readonly, faux positifs documentes). --changelog : interruption d'un
#                          tube (ex. « | head ») geree proprement, au lieu d'un faux « ARRET INATTENDU (code 141) ».
#   1.18.20260926.132132 — Jail odoo-auth genere : paragraphe « MODELE » du modele retire EN ENTIER (une phrase
#                          orpheline restait) ; 127.0.0.1 plus repetee dans ignoreip. Defauts trouves par la suite de tests.
#   1.19.20260926.211237 — SC2015 (A && B || C) reecrit en if/then dans le message du jail odoo-auth (ShellCheck de Debian).
#   1.20.20260926.223504 — Commande fail2ban-regex affichee corrigee : journalmatch par l'option -m (entre crochets, elle
#                          faisait planter fail2ban-regex).
#   1.21.20260926.230736 — Verification fail2ban-regex expliquee (but, marche a suivre, lecture du resultat) ; lignes
#                          reconnues affichees avec leur IP (--print-all-matched).
#   2.0.20260927.145909 — Renomme (ancien nom : setup-nginx-odoo.sh) ; profils d'application (--app) ; etapes propres a
#                          Odoo « sans objet » pour BBB ; conseil HSTS pour HAProxy ; etape 11 : retention des journaux (3 mois).
#   2.1.20260927.200712 — Copies de sauvegarde en anglais : .before-nginx-hardening, .before-setup (migration automatique).
#   2.2.20260927.202645 — Changelog dans le sous-repertoire doc/ (repli sur l'ancien emplacement).
#   2.2.20260928.091309 — PATH complete au demarrage (lancement par cron : /usr/sbin et /sbin manquants).
#   2.3.20260928.103708 — Nouvelle option --log-retention-months N (etape 11) ; lecture fiable de MaxRetentionSec.
#   2.4.20260928.211633 — PATH non complete pendant la suite de tests (NGINX_TOOLS_TESTS).
#   2.5.20260928.212833 — Etape 11 : directive « su » ajoutee quand logrotate refuse (/var/log inscriptible par syslog) ;
#                          variables des etapes Odoo initialisees (plantage final sur BigBlueButton).
#   2.6.20260929.083206 — Etape 9 : jail nginx-blocked-probes (refus des regles, journal dedie) ; verification et
#                          completion de l'ignoreip de fail2ban avec les adresses de l'equipe (table $is_trusted_ip).
#   2.7.20260929.123856 — ignoreip : adresses de nginx ET de la liste unique apps/team-ips.list ; verifie aussi pour BigBlueButton.
#   2.8.20260929.134422 — Etape 12 : adresses de l'equipe generees dans nginx depuis apps/team-ips.list (ecriture atomique,
#                          nginx -t, restauration) ; verrou flock pour --update.
#   2.9.20260929.145745 — Etape 13 : courriel des alertes (relais SMTP, MX, SPF, DMARC, DKIM) via app-health-check.py.
#   2.10.20260929.151644 — Etape 9 pour BigBlueButton : regles de securite (/etc/bigbluebutton/nginx/zz-*.nginx) et jail
#                          nginx-blocked-probes, sans toucher aux fichiers geres par BBB.
#   2.11.20260929.185720 — Etape 13 jamais silencieuse ; cause d'un rechargement de fail2ban en echec (service arrete, erreur de
#                          configuration) ; etat de systemctl lu correctement.
#   2.12.20260929.195459 — Aide : options par ordre alphabetique.
#   2.13.20260929.235632 — Etape 10 : redirection vers le meme nom suivie (HSTS de la page d'arrivee) ; conseil HAProxy
#                          « http-after-response » (s'applique aussi a ses redirections).
#   2.14.20260930.081347 — Motif « A && B || C » remplace par un « if » (ShellCheck de Debian/Ubuntu : SC2015).
#   2.15.20260930.084200 — Filtre et jail ecrits sur BBB identiques aux fichiers livres (octet pour octet) ; HSTS : page
#                          d'arrivee conforme.
#   2.17.20261001.143624 — BigBlueButton : etat AVANT / APRES le passage (versions, configuration de BBB et la notre,
#                          compatibilite, instantane) — apps/_bbb.py ; doc/bbb-upgrade.md.
#   2.16.20260930.163902 — Option --report-err : rapport d'erreurs a copier-coller en fin d'execution.
# Usage : nginx-hardening.sh [--update] [--check] [--odoo-http-port PORT] [--odoo-gevent-port PORT]
#                              [--odoo-service NOM] [--odoo-conf CHEMIN] [--odoo-conf-paths LISTE] [--timezone ZONE] [--workers N] [-v|--verbose] [--version]
#                              [--changelog]
#   - (aucune option)      : VÉRIFICATION SEULE — ne modifie RIEN, même comportement que --check. C'est le
#                            comportement par défaut depuis la 1.7 (avant : appliquait les changements par
#                            défaut, ce qui posait un vrai risque de modification accidentelle du système).
#   - --check              : identique à l'absence d'option — gardé pour compatibilité explicite. C'est ce mode
#                            qu'utilisent nginx-log-audit.sh et app-health-check.py pour avertir si le setup
#                            initial n'a jamais été fait.
#   - --update             : exécute réellement les étapes d'installation (répertoires + pare-feu), écrit le
#                            fichier d'état. Nécessite root. C'est l'ancien comportement par défaut.
#   - --odoo-http-port     : port HTTP principal d'Odoo à vérifier (défaut : http_port/xmlrpc_port de la configuration
#                            d'Odoo trouvée, sinon 8069 si la clé est absente, sinon 10000 si aucune configuration).
#   - --odoo-gevent-port   : port gevent/longpolling (défaut : gevent_port/longpolling_port de la configuration, sinon
#                            8072 ; 10002 si aucune configuration). Ces ports pilotent ufw/iptables (étape 5).
#   - --odoo-service NOM   : unité systemd d'Odoo à ausculter (étapes 6-7). Sans cette option : auto-détection
#                            parmi "erplibre.service" et "erplibre_erplibre.service" (même logique que
#                            app-log-check.py).
#   - --odoo-conf CHEMIN   : fichier de configuration d'Odoo à lire (ports, logfile, workers, limites). Sans cette option :
#                            premier fichier existant de --odoo-conf-paths. Si un est trouvé, l'application du serveur est
#                            reconnue comme Odoo et le journal (logfile, sinon journal systemd) est repéré. Lecture seule.
#   - --odoo-conf-paths L  : chemins candidats (séparés par des espaces, motifs * permis). Défaut : /etc/odoo/odoo-linux_meetup.conf
#                            /opt/odoo/erplibre/config.conf /home/mathben/git/erplibre/config.conf /etc/odoo/*.conf.
#                            Clé ODOO_CONF_PATHS de /etc/default/nginx-hardening.conf ou ~/.nginx-hardening.cfg.
#   - --timezone ZONE      : fuseau horaire du serveur (étape 0b ; défaut America/Montreal, demandé au premier --update, mémorisé dans TIMEZONE ;
#                            « none » : ne rien changer).
#   - --mail-host/--mail-port/--mail-security/--mail-user/--mail-from/--mail-to, --mail-setup : courriel des programmes Python et Bash (étape 0d) ;
#                            demandé UNE fois avec --update ; le mot de passe est demandé sans écho et gardé dans un fichier à part (0600).
#   - --log-retention-months N : duree de conservation des journaux visee par l'etape 11 (1 a 24 mois, defaut : 3).
#                            nginx et fail2ban : « rotate » releve pour couvrir au moins N mois (jamais abaisse).
#                            Journal systemd : MaxRetentionSec=Nmonth ; une valeur deja fixee n'est modifiee que si
#                            l'option est donnee ET qu'elle se trouve dans le fichier de ce script (sinon : signalee).
#   - --workers N          : nombre de workers Odoo, si introuvable dans odoo.conf (ex. défini en ligne de
#                            commande dans run.sh plutôt que dans le fichier de config).
#   - -v/--verbose         : affiche chaque commande système exécutée (ss, ufw, iptables, systemctl, nginx -T,
#                            curl, cp, chown, fail2ban-client...), préfixée de « + ».
#   - --version            : affiche la version et quitte.
#   - --changelog          : affiche nginx-hardening.changelog.txt (couleur si terminal).
#
# Doit être exécuté en root pour --update (chown, pare-feu, /var/www, /var/log/nginx). Sans --update
# (vérification seule, comportement par défaut), aucun privilège requis.

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

# run : execute une commande en l'affichant d'abord si -v/--verbose. Affichage via le descripteur 3 (copie du
# stderr d'origine) : plusieurs appels masquent leur propre stderr ("2>/dev/null"), ce qui ferait disparaitre la
# ligne "+ commande" si elle etait ecrite sur stderr. Fonctionne aussi a l'interieur des $(...).
exec 3>&2
VERBOSE=0
run() {
    if [[ "$VERBOSE" == "1" ]]; then
        printf '+ %s\n' "$*" >&3
    fi
    "$@"
}

readonly SCRIPT_VERSION="2.49.20261016.173838"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly SCRIPT_DIR
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}" .sh)"; readonly SCRIPT_NAME
# Langue d'affichage (en ou fr) : --lang, NGINX_HARDENING_LANG, LANGUAGE du fichier de configuration, LC_ALL / LANG — apps/_i18n.sh traduit la sortie (rien ne change en français).
if [[ -r "$SCRIPT_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_i18n.sh"
    i18n_relancer nginx-hardening NGINX_HARDENING_LANG "$0" "$@"
fi
# Changelog dans le sous-repertoire doc/ ; repli sur l'ancien emplacement (a cote du programme) tant que
# l'installation n'a pas ete reorganisee.
CHANGELOG_FILE="$SCRIPT_DIR/doc/${SCRIPT_NAME}.changelog.txt"
if [[ ! -r "$CHANGELOG_FILE" && -r "$SCRIPT_DIR/${SCRIPT_NAME}.changelog.txt" ]]; then CHANGELOG_FILE="$SCRIPT_DIR/${SCRIPT_NAME}.changelog.txt"; fi
readonly CHANGELOG_FILE
# migrer_chemin ANCIEN NOUVEAU : renommage des programmes en 2.0 — renomme un fichier ou repertoire de l'ancien nom
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
migrer_chemin "/etc/default/setup-nginx-odoo.conf" "/etc/default/${SCRIPT_NAME}.conf"
readonly STATE_FILE="${NGINX_TOOLS_ETC_DEFAULT:-/etc/default}/${SCRIPT_NAME}.conf"

: "${LC_ALL:=C.UTF-8}"
export LC_ALL

if [[ -t 1 || -n "${REPORT_ERR_COULEUR:-}" ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_RESET=""
fi

CHECK_ONLY=1
ODOO_HTTP_PORT=""      # vide : lu dans la configuration d'Odoo (étape « configuration »), sinon 10000 / 10002
ODOO_GEVENT_PORT=""
ODOO_CONF_PATHS="${ODOO_CONF_PATHS:-}"
ODOO_SERVICE=""
TIMEZONE=""            # vide : défaut ci-dessous (demandé la première fois) ; « none » : ne rien changer
TIMEZONE_DEFAUT="America/Montreal"
MAIL_HOST=""; MAIL_PORT=""; MAIL_SECURITY=""; MAIL_USER=""; MAIL_FROM=""; MAIL_TO=""   # courriel des programmes (étape 0d) : vide = lu dans le fichier commun, sinon demandé
MAIL_SETUP=0           # --mail-setup : redemander la configuration du courriel même si elle existe
RENAME_FROM=""; RENAME_TO=""   # --rename-from / --rename-to : changement de nom DNS public (étape 0e) ; vide : rien à faire
APP_FORCE=""
ODOO_CONF=""
ODOO_WORKERS_OVERRIDE=""
# Initialisées ici : affectées par des étapes propres à Odoo (4 et 9), mais lues par le récapitulatif final — même
# pour BigBlueButton, dont ces étapes sont « sans objet » (sinon : « unbound variable » en fin d'exécution).
PORT_EXPOSED=0
NEED_FAIL2BAN_RESTART=0
F2B_INSTALLED_JAILS=()
LOG_RETENTION_MONTHS=3
RETENTION_EXPLICITE=0
# Fichier de configuration (/etc/default/nginx-hardening.conf PUIS ~/.nginx-hardening.cfg ; -c/--config FICHIER : ce fichier seul) : valeurs par défaut des options.
# /etc/default/nginx-hardening.conf sert AUSSI de fichier d'état (lignes SETUP_*, réécrites par --update) : les autres lignes y sont conservées.
if declare -F config_lire >/dev/null; then
    config_lire nginx-hardening "$@"
    config_defaut APP_FORCE APP --app texte
    config_defaut LOG_RETENTION_MONTHS LOG_RETENTION_MONTHS --log-retention-months nombre
    config_defaut MAIL_FROM MAIL_FROM --mail-from texte
    config_defaut MAIL_HOST MAIL_HOST --mail-host texte
    config_defaut MAIL_PORT MAIL_PORT --mail-port nombre
    config_defaut MAIL_SECURITY MAIL_SECURITY --mail-security texte
    config_defaut MAIL_SETUP MAIL_SETUP --mail-setup booleen
    config_defaut MAIL_TO MAIL_TO --mail-to texte
    config_defaut MAIL_USER MAIL_USER --mail-user texte
    config_defaut ODOO_CONF ODOO_CONF --odoo-conf texte
    config_defaut ODOO_CONF_PATHS ODOO_CONF_PATHS --odoo-conf-paths texte
    config_defaut ODOO_GEVENT_PORT ODOO_GEVENT_PORT --odoo-gevent-port nombre
    config_defaut ODOO_HTTP_PORT ODOO_HTTP_PORT --odoo-http-port nombre
    config_defaut ODOO_SERVICE ODOO_SERVICE --odoo-service texte
    config_defaut RENAME_FROM RENAME_FROM --rename-from texte
    config_defaut RENAME_TO RENAME_TO --rename-to texte
    config_defaut TIMEZONE TIMEZONE --timezone texte
    config_defaut VERBOSE VERBOSE --verbose booleen
    config_defaut ODOO_WORKERS_OVERRIDE WORKERS --workers nombre
fi

export ODOO_CONF_PATHS   # lu par apps/_odoo_conf.sh (vide : lignes ODOO_CONF_PATHS des fichiers de configuration, puis liste par défaut)

# --report-err : rapport d'erreurs à copier-coller en fin d'exécution (programme, version, serveur, échecs…) — apps/_rapport.sh
if [[ -r "$SCRIPT_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$SCRIPT_DIR/apps/_rapport.sh"
    rapport_si_demande "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$SCRIPT_VERSION" "$SCRIPT_DIR" "$@"
fi
# Première ligne de TOUTE exécution, même avec --help : le nom et la version du programme (--version l'affiche lui-même).
case " $* " in *" --version "*) ;; *) echo "nginx-hardening.sh v$SCRIPT_VERSION" ;; esac
if declare -F config_afficher >/dev/null; then
    case " $* " in *" --version "*|*" --changelog "*) ;; *) config_afficher ;; esac
fi
# Listes d'adresses (liste blanche et lieux) : /etc/default/nginx-tools-*.conf, jamais livrées dans les archives — lecteur commun apps/_listes.sh.
# shellcheck source=/dev/null
[[ -r "$SCRIPT_DIR/apps/_listes.sh" ]] && . "$SCRIPT_DIR/apps/_listes.sh"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        --check) CHECK_ONLY=1; shift ;;   # comportement par defaut desormais — garde pour compatibilite explicite
        --update) CHECK_ONLY=0; shift ;;  # applique reellement les changements (anciennement le defaut)
        --app) APP_FORCE="${2:-}"; shift 2 ;;
        --app=*) APP_FORCE="${1#--app=}"; shift ;;
        --mail-from) MAIL_FROM="${2:-}"; shift 2 ;;
        --mail-host) MAIL_HOST="${2:-}"; shift 2 ;;
        --mail-port) MAIL_PORT="${2:-}"; shift 2 ;;
        --mail-security) MAIL_SECURITY="${2:-}"; shift 2 ;;
        --mail-setup) MAIL_SETUP=1; shift ;;
        --mail-to) MAIL_TO="${2:-}"; shift 2 ;;
        --mail-user) MAIL_USER="${2:-}"; shift 2 ;;
        --odoo-http-port) ODOO_HTTP_PORT="${2:-}"; shift 2 ;;
        --odoo-gevent-port) ODOO_GEVENT_PORT="${2:-}"; shift 2 ;;
        --odoo-service) ODOO_SERVICE="${2:-}"; shift 2 ;;
        --rename-from) RENAME_FROM="${2:-}"; shift 2 ;;
        --rename-to) RENAME_TO="${2:-}"; shift 2 ;;
        --timezone) TIMEZONE="${2:-}"; shift 2 ;;
        --odoo-conf) ODOO_CONF="${2:-}"; shift 2 ;;
        --odoo-conf-paths) ODOO_CONF_PATHS="${2:-}"; shift 2 ;;
        --workers) ODOO_WORKERS_OVERRIDE="${2:-}"; shift 2 ;;
        --log-retention-months) LOG_RETENTION_MONTHS="${2:-}"; RETENTION_EXPLICITE=1; shift 2 ;;
        --version)
            echo "nginx-hardening.sh v$SCRIPT_VERSION"
            exit 0
            ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then
                echo "Changelog introuvable : $CHANGELOG_FILE" >&2
                exit 1
            fi
            if [[ -t 1 ]]; then
                sed -E "s/^(## [0-9]+\.[0-9]+\.[0-9]{8}\.[0-9]{6}.*)$/$(printf '\x1b[1;36m')\1$(printf '\x1b[0m')/" "$CHANGELOG_FILE" | (trap '' PIPE; less -R 2>/dev/null || cat) || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            else
                cat "$CHANGELOG_FILE" || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            fi
            exit 0
            ;;
        -h|--help)
            cat <<'AIDE'
Usage : nginx-hardening.sh [OPTION]...
Setup initial et audit du serveur (nginx, pare-feu, Odoo, fail2ban, journaux, courriel). Par défaut (sans --update) :
vérification seule, rien n'est modifié.

Options (par ordre alphabétique) :
  --anonymize                  anonymise ce qui est affiché (adresses IP, courriels, identifiants, jetons) par des pseudonymes stables ; clé ANONYMIZE
  --app NAME                   application derrière nginx (profil apps/NAME.conf : odoo, bbb…) ; détectée par défaut
  --changelog                  affiche le journal des modifications
  --check                      vérification seule (comportement par défaut)
  -c, --config FILE            fichier de configuration à lire SEUL (défaut : /etc/default/nginx-hardening.conf puis ~/.nginx-hardening.cfg)
  -h, --help                   affiche cette aide et quitte
  --lang LANG                  langue d'affichage : en ou fr (défaut : selon LC_ALL / LC_MESSAGES / LANG)
  --log-retention-months N     durée de conservation des journaux visée par l'étape 11 (1 à 24 mois, défaut : 3)
  --mail-from ADDRESS          expéditeur des courriels de la suite (défaut : l'identifiant du relais)
  --mail-host HOST             relais SMTP des courriels des programmes Python et Bash (étape 0d ; demandé la première fois avec --update)
  --mail-port PORT             port du relais SMTP (défaut : 587)
  --mail-security MODE         chiffrement : starttls (défaut), ssl ou none
  --mail-setup                 redemander la configuration du courriel (avec --update)
  --mail-to ADDRESS            destinataire des courriels de la suite (alertes, rapports)
  --mail-user NAME             identifiant du relais SMTP (le mot de passe est demandé, jamais passé en option)
  --odoo-conf FILE            configuration d'Odoo (défaut : premier fichier trouvé parmi --odoo-conf-paths)
  --odoo-conf-paths LIST       chemins (espaces ; motifs * permis) où chercher la configuration d'Odoo (défaut : /etc/odoo/odoo-linux_meetup.conf
                               /opt/odoo/erplibre/config.conf /home/mathben/git/erplibre/config.conf /etc/odoo/*.conf…)
  --odoo-gevent-port PORT      port gevent (websocket) d'Odoo à vérifier (défaut : celui de la configuration d'Odoo)
  --odoo-http-port PORT        port HTTP d'Odoo à vérifier (défaut : celui de la configuration d'Odoo)
  --odoo-service NAME         unité systemd d'Odoo (défaut : détectée)
  --rename-from NAME           ancien nom DNS public à remplacer dans nginx (étape 0e ; avec --rename-to et --update)
  --rename-to NAME             nouveau nom DNS public : nginx et certificat Let's Encrypt sont refaits pour ce nom (sans --rename-from, l'ancien nom est cherché dans nginx)
  --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
                               échecs, avertissements) ; désactive couleurs et questions interactives
  --timezone ZONE              fuseau horaire du serveur (défaut : America/Montreal, demandé la première fois ; none = ne pas toucher)
  --update                     installer ou mettre à jour ce qui manque (sauvegarde des fichiers modifiés)
  -v, --verbose                affiche chaque commande lancée
  --version                    affiche la version et quitte
  --workers N                  nombre de workers pour la suggestion de limites mémoire (étape 6)
AIDE
            exit 0
            ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*) shift ;;
        --lang) shift 2 ;;                     # traité avant (apps/_i18n.sh : i18n_relancer)
        --lang=*) shift ;;
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
if [[ "$CHECK_ONLY" != "1" && "$EUID" -ne 0 ]]; then        # root vérifié AVANT le verrou (1.102 : le refus est la première chose faite)
    echo "ERREUR: ce script doit être exécuté en root (sudo) pour --update." >&2
    exit 1
fi
# --update seulement (--check ne modifie rien) : attente de NGINX_TOOLS_LOCK_WAIT secondes au plus (60 par défaut).
if [[ "$CHECK_ONLY" != "1" ]]; then
    prendre_verrou "${NGINX_TOOLS_LOCK_WAIT:-60}" nginx-hardening
fi

echo "=============================================================="
if [[ "$CHECK_ONLY" == "1" ]]; then
    echo " VÉRIFICATION DU SETUP INITIAL (rien n'est modifié — relancer avec --update pour appliquer)"
else
    echo " INSTALLATION / MISE À JOUR DU SETUP INITIAL (--update)"
fi
echo "=============================================================="
echo

# Chaque étape mène à l'une de ces trois issues, comptées à la fin pour le code de sortie et le résumé.
PASS=0
FAIL=0
WARN=0

# --- Application derriere nginx : profil apps/<nom>.conf, detecte ou force (--app=NOM, ou variable APP_PROFILE) ------
APPS_DIR="$SCRIPT_DIR/apps"
if [[ -r "$APPS_DIR/_profile.sh" ]]; then
    # shellcheck source=/dev/null  # bibliotheque apps/_profile.sh, livree a cote du programme
    . "$APPS_DIR/_profile.sh"
    charger_profil_app "$APPS_DIR" "$APP_FORCE" || exit 1
else
    APP_NAME="odoo"; APP_LABEL="Odoo"; ODOO_SPECIFIC_STEPS="yes"; HARDENING_CONFIG="nginx-odoo"; TLS_TERMINATION="nginx"
    APP_DETECTION="par défaut (dossier apps/ absent à côté du programme)"
fi
echo "Application : $APP_LABEL ($APP_DETECTION)"
echo

# --- Configuration d'Odoo : fichier trouvé (--odoo-conf, sinon premier candidat existant : --odoo-conf-paths), ports et journal ---
# Les ports HTTP et gevent viennent de la configuration (http_port / xmlrpc_port, gevent_port / longpolling_port) : le pare-feu
# (étapes 4 et 5) vise donc les VRAIS ports de ce serveur. Une option explicite (--odoo-http-port…) l'emporte toujours.
ODOO_PORTS_SOURCE="défaut historique (aucune configuration d'Odoo trouvée)"
ODOO_LOGFILE=""
ODOO_CONF_UNITES=""
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
    if [[ -r "$APPS_DIR/_odoo_conf.sh" ]] && ! declare -F odoo_conf_trouver >/dev/null; then
        # shellcheck source=/dev/null  # bibliotheque apps/_odoo_conf.sh, livree a cote du programme
        . "$APPS_DIR/_odoo_conf.sh"
    fi
    if [[ -z "$ODOO_CONF" ]] && declare -F odoo_conf_trouver >/dev/null; then
        ODOO_CONF=$(odoo_conf_trouver) || ODOO_CONF=""
    fi
    if [[ -n "$ODOO_CONF" && -r "$ODOO_CONF" ]] && declare -F odoo_conf_charger >/dev/null; then
        odoo_conf_charger "$ODOO_CONF"
        ODOO_LOGFILE="$ODOO_CONF_LOGFILE"
        ODOO_PORTS_SOURCE="lus dans $ODOO_CONF"
        [[ -n "$ODOO_HTTP_PORT" ]] || ODOO_HTTP_PORT="$ODOO_CONF_HTTP_PORT"
        [[ -n "$ODOO_GEVENT_PORT" ]] || ODOO_GEVENT_PORT="$ODOO_CONF_GEVENT_PORT"
        echo "Configuration d'Odoo : $ODOO_CONF"
        echo "  Ports : HTTP $ODOO_HTTP_PORT, gevent $ODOO_GEVENT_PORT ($ODOO_PORTS_SOURCE)"
        if [[ -z "$(odoo_conf_valeur "$ODOO_CONF" http_port)$(odoo_conf_valeur "$ODOO_CONF" xmlrpc_port)" ]]; then
            echo "  [!] http_port absent de la configuration : port par défaut d'Odoo (8069) retenu. Si Odoo est lancé avec --http-port en ligne de commande, précisez --odoo-http-port."
        fi
        if [[ -n "$ODOO_LOGFILE" ]]; then
            echo "  Journal d'Odoo : fichier $ODOO_LOGFILE (logfile)"
        else
            echo "  Journal d'Odoo : journal systemd (pas de logfile dans la configuration)"
        fi
        echo
    fi
fi
[[ -n "$ODOO_HTTP_PORT" ]] || ODOO_HTTP_PORT=10000
[[ -n "$ODOO_GEVENT_PORT" ]] || ODOO_GEVENT_PORT=10002

# sans_objet RAISON : etape ignoree pour cette application (affiche, jamais compte comme echec ni avertissement).
sans_objet() { echo "  [--]   Sans objet pour $APP_LABEL : $1"; }

# Adresses de l'équipe → nginx (étape 12) : fichiers inclus GÉNÉRÉS depuis la LISTE BLANCHE (/etc/default/nginx-tools-white-list.conf, apps/_listes.sh).
# $1 = geo (table $is_trusted_ip : « ADRESSE 1; ») ou allow (listes allow : « allow ADRESSE; »). Entrées invalides :
# notées dans EQUIPE_INVALIDES (jamais écrites dans nginx, qui refuserait sinon toute sa configuration).
EQUIPE_INVALIDES=""
generer_equipe() {
    local type="$1" adr lib n
    EQUIPE_INVALIDES=""
    echo "# GÉNÉRÉ par nginx-hardening.sh à partir de la liste blanche (/etc/default/nginx-tools-white-list.conf) — NE PAS MODIFIER À LA MAIN."
    echo "# Pour ajouter ou retirer une adresse : modifier la liste blanche, puis nginx-hardening.sh --update."
    while IFS=$'\037' read -r adr lib _ n; do
        [[ -z "$adr" ]] && continue
        if ! listes_adresse_valide "$adr"; then
            EQUIPE_INVALIDES="$EQUIPE_INVALIDES ligne $n : « $adr »;"
            continue
        fi
        if [[ "$type" == "geo" ]]; then
            printf '%-18s 1;   # %s\n' "$adr" "${lib:-équipe}"
        else
            printf 'allow %-18s # %s\n' "$adr;" "${lib:-équipe}"
        fi
    done < <(listes_blanche)
}

# generer_partages : contenu de shared-ips-geo.conf (table $is_shared_ip de nginx) : les adresses des lieux marqués [partagée] (université…) ; zones de limitation plus larges.
generer_partages() {
    local adr lib
    echo "# GÉNÉRÉ par nginx-hardening.sh à partir des lieux [partagée] (/etc/default/nginx-tools-ip-location.conf) — NE PAS MODIFIER À LA MAIN."
    echo "# Adresses derrière lesquelles plusieurs personnes travaillent : limites de débit plus larges (odoo-global.conf, zones *_partage)."
    while IFS=$'\037' read -r adr lib _ _; do
        [[ -z "$adr" ]] && continue
        printf '%-18s 1;   # %s\n' "$adr" "${lib:-réseau partagé}"
    done < <(listes_lieux | listes_valides | awk -F'\037' '$3 ~ /partagee/ && !vu[$1]++')
}

# creer_modele DESTINATION MODELE : crée le fichier (droits 644) depuis doc/MODELE livré avec les programmes, à défaut un en-tête minimal.
creer_modele() {
    local dest="$1" modele="$SCRIPT_DIR/doc/$2"
    mkdir -p "$(dirname "$dest")" 2>/dev/null || return 1
    if [[ -r "$modele" ]]; then cp "$modele" "$dest" 2>/dev/null || return 1
    else printf '# %s — voir doc/%s\n' "$(basename "$dest")" "$2" > "$dest" 2>/dev/null || return 1; fi
    chmod 644 "$dest"
}

# migrer_listes : la liste blanche et les lieux vivent dans /etc/default (hors des archives, publiables sans données personnelles).
# --update : migre l'ancienne liste apps/team-ips.list (copiée, puis renommée .migre) ou crée un modèle ; fichiers présents : jamais modifiés.
migrer_listes() {
    local blanche="${NGINX_TOOLS_WHITE_LIST:-$LISTES_BLANCHE_DEFAUT}" lieux="${NGINX_TOOLS_IP_LOCATION:-$LISTES_LIEUX_DEFAUT}"
    local ancien="$SCRIPT_DIR/apps/team-ips.list"
    if [[ -f "$blanche" ]]; then
        pass "Liste blanche : $blanche ($(listes_blanche | listes_valides | grep -c . || true) adresse(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        if [[ -f "$ancien" ]]; then warn "Liste blanche : ANCIEN emplacement $ancien — --update la migre vers $blanche."
        else warn "Liste blanche absente ($blanche) — --update crée un modèle à remplir (sans elle, aucune adresse n'a accès à la gestion des bases de DEV ni à LAB)."; fi
    elif [[ -f "$ancien" ]]; then
        if cp "$ancien" "$blanche" 2>/dev/null && chmod 644 "$blanche" && mv "$ancien" "$ancien.migre"; then
            pass "Liste blanche migrée : $ancien -> $blanche (l'ancien fichier est renommé .migre : il peut être supprimé)."
        else warn "Migration de $ancien vers $blanche impossible (droits ?) : la copier à la main."; fi
    elif creer_modele "$blanche" nginx-tools-white-list.conf.example; then
        warn "Liste blanche créée VIDE ($blanche) : y mettre les adresses de confiance (équipe), puis relancer --update."
    else
        warn "Liste blanche : impossible de créer $blanche (droits ?)."
    fi
    if [[ -f "$lieux" ]]; then
        pass "Lieux : $lieux ($(listes_lieux | listes_valides | grep -c . || true) plage(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Lieux : aucun fichier ($lieux) — facultatif ; --update crée un modèle (université, bureau : nom d'une plage, affiché par app-log-live.py)."
    elif creer_modele "$lieux" nginx-tools-ip-location.conf.example; then
        pass "Lieux : modèle créé ($lieux) : y décrire vos plages partagées (université…) — facultatif."
    fi
    while IFS= read -r probleme; do [[ -n "$probleme" ]] && warn "Listes : $probleme"; done < <(python3 "$SCRIPT_DIR/apps/_listes.py" --resume 2>/dev/null | sed -n 's/^  ATTENTION //p')
}

# Durcissement de BigBlueButton (étape 9) : fichier À NOUS dans /etc/bigbluebutton/nginx/ (inclus par BBB dans son bloc
# server, jamais écrasé par ses mises à jour). Refuse UNIQUEMENT des URL que BBB ne sert jamais ; aucun emplacement de
# BBB n'est modifié (client HTML5, API, WebRTC : proxy_buffering, délais et mises à niveau de protocole intacts).
generer_regles_bbb() {
    cat <<'EOF'
# GÉNÉRÉ par nginx-hardening.sh — NE PAS MODIFIER À LA MAIN (relancer nginx-hardening.sh --update).
# Règles de sécurité pour BigBlueButton : URL que BBB ne sert jamais (fichiers cachés, scripts PHP/CGI, WordPress…),
# refusées en 404 par nginx et journalisées dans blocked-probes.log (jail fail2ban nginx-blocked-probes).
location ~ /\.(?!well-known/) {
    access_log /var/log/nginx/blocked-probes.log;
    return 404;
}
location ~* \.(php[0-9]?|phtml|asp|aspx|jsp|cgi|env|bak|swp)$ {
    access_log /var/log/nginx/blocked-probes.log;
    return 404;
}
location ~* ^/(wp-admin|wp-login|wp-content|wp-includes|xmlrpc\.php|phpmyadmin|pma|cgi-bin|vendor/phpunit) {
    access_log /var/log/nginx/blocked-probes.log;
    return 404;
}
EOF
}
# Filtre et jail de nginx-blocked-probes : copie EXACTE (octet pour octet) de nginx-odoo/fail2ban/nginx-blocked-probes.
# {filter,jail}.conf, pour que tests/run-all.sh (étape 5, cmp) ne signale pas de différence sur un serveur BBB, où ces
# fichiers ne sont pas déployés et doivent être écrits ici. Un test vérifie l'identité avec les fichiers livrés.
filtre_blocked_probes() {
    cat <<'EOF'
# Filtre fail2ban : refus des règles de sécurité de nginx (securite-commune.conf : fichiers sensibles, .php, cadriciels,
# objets connectés, wp-*, graphql…), journalisés à part dans blocked-probes.log. Chaque ligne de ce journal est un
# refus CERTAIN : toute ligne compte (format combined_host, adresse en tête de ligne).
[Definition]
failregex = ^<HOST> - \S+ \[
ignoreregex =
EOF
}
jail_blocked_probes() {
    cat <<'EOF'
# Jail : un client qui accumule les refus des règles de sécurité (scanner de fichiers sensibles, de failles connues)
# est banni. Ces refus étaient invisibles de fail2ban (access_log off) jusqu'au journal dédié blocked-probes.log.
[nginx-blocked-probes]
enabled  = true
port     = http,https
filter   = nginx-blocked-probes
logpath  = /var/log/nginx/blocked-probes.log
maxretry = 5
findtime = 600
bantime  = 86400
action   = iptables-multiport[name=nginx-blocked-probes, port="http,https", protocol=tcp]
EOF
}
durcir_bbb() {
    local dir="${NGINX_HARDENING_BBB_NGINX_DIR:-/etc/bigbluebutton/nginx}" fichier contenu ancien="" tmp
    fichier="$dir/zz-nginx-hardening-security.nginx"
    contenu=$(generer_regles_bbb)
    if ! command -v nginx >/dev/null 2>&1; then
        warn "nginx introuvable — règles de sécurité BBB non vérifiées."
    elif ! run nginx -T 2>/dev/null | grep_q 'include /etc/bigbluebutton/nginx/\*\.nginx'; then
        warn "La configuration nginx de BBB n'inclut pas /etc/bigbluebutton/nginx/*.nginx — règles de sécurité non installées (à examiner)."
    elif [[ -f "$fichier" && "$(cat "$fichier")" == "$contenu" ]]; then
        pass "Règles de sécurité BBB à jour ($fichier)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Règles de sécurité BBB $([[ -f "$fichier" ]] && echo différentes || echo absentes) — --update les installera ($fichier : fichiers cachés, PHP/CGI, WordPress refusés en 404)."
    else
        [[ -f "$fichier" ]] && ancien=$(cat "$fichier")
        mkdir -p "$dir"; tmp=$(mktemp "$dir/.zz-nginx-hardening.XXXXXX")
        printf '%s\n' "$contenu" > "$tmp" && chmod 644 "$tmp" && mv -f "$tmp" "$fichier"
        if run nginx -t >/dev/null 2>&1; then
            run systemctl reload nginx >/dev/null 2>&1 || true
            pass "Règles de sécurité BBB installées ($fichier) ; nginx -t réussi, nginx rechargé."
        else
            if [[ -n "$ancien" ]]; then printf '%s\n' "$ancien" > "$fichier"; else rm -f "$fichier"; fi
            fail "nginx -t refuse les règles de sécurité BBB — ancienne version restaurée, nginx NON rechargé (nginx -t pour le détail)."
        fi
    fi
    # Jail nginx-blocked-probes (fichiers écrits ici : la configuration nginx-odoo n'est pas déployée sur BBB).
    if command -v fail2ban-client >/dev/null 2>&1; then
        if [[ -f /etc/fail2ban/jail.d/nginx-blocked-probes.conf && -f /etc/fail2ban/filter.d/nginx-blocked-probes.conf ]]; then
            pass "Jail nginx-blocked-probes : fichiers présents."
            F2B_INSTALLED_JAILS+=(nginx-blocked-probes)
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            warn "Jail nginx-blocked-probes absente — --update l'installera (bannit les clients qui accumulent les refus)."
        else
            mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d
            filtre_blocked_probes > /etc/fail2ban/filter.d/nginx-blocked-probes.conf
            jail_blocked_probes > /etc/fail2ban/jail.d/nginx-blocked-probes.conf
            [[ -e /var/log/nginx/blocked-probes.log ]] || { touch /var/log/nginx/blocked-probes.log; chown --reference=/var/log/nginx /var/log/nginx/blocked-probes.log 2>/dev/null || true; }
            pass "Jail nginx-blocked-probes installée (5 refus en 10 min → banni 24 h)."
            NEED_FAIL2BAN_RESTART=1
            F2B_INSTALLED_JAILS+=(nginx-blocked-probes)
        fi
    fi
}

# Définie ici, avec les fonctions utilitaires : appelée par l'étape 9 pour Odoo ET pour BigBlueButton.
verifier_ignoreip() {
    # --- 9c) ignoreip : adresses de l'équipe (table $is_trusted_ip de nginx ET liste blanche + lieux [protégée] de /etc/default/nginx-tools-*.conf) jamais bannies par fail2ban. Les listes
    # « allow » de nginx et « ignoreip » de fail2ban sont INDÉPENDANTES : une adresse ajoutée à l'une ne l'est pas à
    # l'autre. Correction (--update) dans un fichier à part, lu en dernier (jail.d/*.local), qui REPREND les adresses
    # déjà ignorées : jamais de modification de jail.local.
    f2b_equipe=$({ run nginx -T 2>/dev/null | awk '/^[[:space:]]*geo[[:space:]].*\$is_trusted_ip[[:space:]]*\{/ { dans = 1; next }
        dans && /^[[:space:]]*\}/ { dans = 0 } dans && $2 ~ /^1;/ && $1 != "127.0.0.1" && $1 != "::1" { print $1 }'; listes_ne_pas_bannir ; } | sort -u) || f2b_equipe=""
    f2b_jails=$(run fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr ',' ' ') || f2b_jails=""
    if [[ -n "$f2b_equipe" && -n "${f2b_jails// /}" ]]; then
        f2b_manquants=(); f2b_connues=""
        for j in $f2b_jails; do
            # Adresses VALIDES seulement : IPv4 (plage éventuelle), IPv6 à deux deux-points au moins — jamais un morceau de
            # texte (« ignored: » donnerait « ed: »), qui rendrait la configuration de fail2ban illisible.
            f2b_ign=$(run fail2ban-client get "$j" ignoreip 2>/dev/null | grep -oE '[0-9a-fA-F:.]+(/[0-9]+)?' \
                      | grep -xE '[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?|[0-9a-fA-F]*:[0-9a-fA-F]*:[0-9a-fA-F:]*(/[0-9]{1,3})?' || true)
            f2b_connues="$f2b_connues $f2b_ign"
            for ip in $f2b_equipe; do
                grep -qxF "$ip" <<< "$f2b_ign" || f2b_manquants+=("$j:$ip")
            done
        done
        if (( ${#f2b_manquants[@]} == 0 )); then
            pass "fail2ban : les $(wc -w <<< "$f2b_equipe") adresses de l'équipe (table \$is_trusted_ip de nginx) sont ignorées par toutes les jails."
        else
            f2b_ips=$(printf '%s\n' "${f2b_manquants[@]}" | cut -d: -f2- | sort -u | tr '\n' ' ')
            f2b_js=$(printf '%s\n' "${f2b_manquants[@]}" | cut -d: -f1 | sort -u | tr '\n' ' ')
            if [[ "$CHECK_ONLY" == "1" ]]; then
                warn "fail2ban : adresses de l'équipe NON ignorées (jails : ${f2b_js% }) : ${f2b_ips% } — --update les ajoutera (jail.d/zz-nginx-hardening-ignoreip.local)."
            else
                f2b_liste=$(tr ' ' '\n' <<< "127.0.0.1/8 ::1 $f2b_connues $f2b_equipe" | grep . | awk '!vu[$0]++' | tr '\n' ' ')
                mkdir -p /etc/fail2ban/jail.d 2>/dev/null || true
                printf '%s\n' "# Généré par nginx-hardening.sh : adresses de l'équipe (table \$is_trusted_ip de nginx) jamais bannies," \
                    "# plus les adresses déjà ignorées. Lu en dernier (jail.d/*.local) : complète jail.local sans le modifier." \
                    "[DEFAULT]" "ignoreip = ${f2b_liste% }" > /etc/fail2ban/jail.d/zz-nginx-hardening-ignoreip.local
                NEED_FAIL2BAN_RESTART=1
                pass "fail2ban : ignoreip complété (${f2b_ips% }) dans /etc/fail2ban/jail.d/zz-nginx-hardening-ignoreip.local — une jail qui définit son propre ignoreip reste à compléter à la main."
            fi
        fi
    fi
}

pass() { echo "  ${C_GREEN}[OK]${C_RESET}   $1"; PASS=$((PASS+1)); }
fail() { echo "  ${C_RED}[FAIL]${C_RESET} $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ${C_YELLOW}[ATTN]${C_RESET} $1"; WARN=$((WARN+1)); }

# --- BigBlueButton : état AVANT / APRÈS ce passage (apps/_bbb.py) --------------------------------------------------
# Versions (paquets, Greenlight), empreinte des fichiers de configuration de BBB et des nôtres, comparées à l'instantané
# du dernier --update : une mise à jour de BBB faite entre-temps apparaît AVANT ; APRÈS, la compatibilité de nos règles
# avec BBB est vérifiée (nginx -t, règles chargées, API et client HTML5 joignables, HSTS de HAProxy, bbb-conf --check).
bbb_etat() {
    local ligne verb=()
    if [[ "$VERBOSE" == "1" ]]; then verb=(--verbose); fi          # --verbose est passé aux programmes appelés
    while IFS= read -r ligne; do
        case "$ligne" in
            "[OK] "*)   pass "${ligne#\[OK\] }" ;;
            "[ATTN] "*) warn "${ligne#\[ATTN\] }" ;;
            "[FAIL] "*) fail "${ligne#\[FAIL\] }" ;;
            *)          echo "  $ligne" ;;
        esac
    done < <(timeout --foreground 400 python3 "$APPS_DIR/_bbb.py" ${verb[@]+"${verb[@]}"} "$@" 2>&1 || true)
}
BBB_ETAT=0
if [[ "$APP_NAME" == "bbb" && -r "$APPS_DIR/_bbb.py" ]] && command -v python3 >/dev/null 2>&1; then
    BBB_ETAT=1
    echo "--- BigBlueButton AVANT ce passage : versions et configuration, changements depuis le dernier --update ---"
    bbb_etat --before
    echo
fi

# --- 0) Programmes requis : installés par --update s'ils manquent (apt) ----------------------------------------------
# paquet_installer COMMANDE PAQUET : COMMANDE absente => vérification seule : avertit ; --update : apt-get install, puis revérifie.
paquet_installer() {
    local cmd="$1" paquet="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd présent (paquet $paquet)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "$cmd absent (paquet $paquet) — relancer avec --update pour l'installer."
    elif ! command -v apt-get >/dev/null 2>&1; then
        warn "$cmd absent et apt-get introuvable — installez le paquet $paquet avec le gestionnaire de paquets de cette distribution."
    elif DEBIAN_FRONTEND=noninteractive run apt-get install -y "$paquet" >/dev/null 2>&1 && command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd installé (paquet $paquet)."
    else
        fail "installation du paquet $paquet en échec — lancer « apt-get install $paquet » et lire l'erreur."
    fi
}
echo "--- 0) Programmes requis (ss, curl, logrotate, fail2ban) ---"
paquet_installer ss iproute2
paquet_installer curl curl
paquet_installer logrotate logrotate
paquet_installer fail2ban-client fail2ban
echo

# --- 0a) nginx AVANT mes changements : « nginx -t » et l'état du service, avec de l'aide pour corriger ------------------------------
# Un problème déjà présent (certificat introuvable, dossier de cache absent, directive inconnue, port occupé…) est signalé ICI, avec le fichier et les lignes en cause et
# la marche à suivre, pour qu'un refus de nginx plus loin ne soit pas attribué aux changements de ce script. Rien n'est modifié par cette étape.
nginx_aide() {      # nginx_aide MESSAGE : conseils d'après le message de « nginx -t » (une ligne par cause reconnue)
    local m="$1" fic lig
    if grep -Eqi 'cannot load certificate|BIO_new_file|SSL_CTX_use_(PrivateKey|certificate)' <<<"$m"; then
        echo "        Que faire : un certificat ou une clé est introuvable ou illisible. Si le nom DNS a changé : $0 --update --rename-to NOUVEAU_NOM (refait nginx et le certificat) ; sinon « certbot certificates » puis « certbot renew »."
    fi
    if grep -Eqi 'open\(\) .* failed \(2: No such file|No such file or directory' <<<"$m"; then
        echo "        Que faire : un fichier ou un dossier mentionné par nginx n'existe pas (cache, journal, include). Les dossiers de cache sont créés par $0 --update (étape 0c) ; sinon créer le fichier ou retirer la ligne."
    fi
    if grep -Eqi 'unknown directive|unknown "' <<<"$m"; then
        echo "        Que faire : directive inconnue de cette installation de nginx : module absent (ex. GeoIP : apt install libnginx-mod-http-geoip) ou faute de frappe dans la ligne indiquée."
    fi
    if grep -Eqi 'Address already in use|bind\(\)' <<<"$m"; then
        echo "        Que faire : un port est déjà pris par un autre programme : ss -ltnp | grep ':80\|:443' (un autre nginx, Apache, Docker…), l'arrêter ou changer le port."
    fi
    if grep -Eqi 'host not found in upstream' <<<"$m"; then
        echo "        Que faire : le nom d'un serveur amont (upstream/proxy_pass) ne se résout pas : mettre 127.0.0.1 ou corriger le nom."
    fi
    if grep -Eqi 'duplicate|conflicting|already bound|is already defined' <<<"$m"; then
        echo "        Que faire : définition en double (upstream, zone, location ou serveur par défaut) : garder une seule définition ; grep -rn le nom dans /etc/nginx/."
    fi
    if grep -Eqi 'hash_bucket_size|hash_max_size' <<<"$m"; then
        echo "        Que faire : augmenter server_names_hash_bucket_size (64 puis 128) dans nginx.conf, bloc http."
    fi
    fic=$(grep -Eo 'in /[^ :]+:[0-9]+' <<<"$m" | head -n 1 | sed 's/^in //') || fic=""
    if [[ -n "$fic" ]]; then
        lig="${fic##*:}"; fic="${fic%:*}"
        if [[ -r "$fic" ]]; then
            echo "        Lignes en cause ($fic, ligne $lig) :"
            sed -n "$((lig > 2 ? lig - 2 : 1)),$((lig + 2))p" "$fic" 2>/dev/null | sed 's/^/          | /'
        fi
    fi
}
echo "--- 0a) nginx avant les changements (nginx -t, service) ---"
if ! command -v nginx >/dev/null 2>&1; then
    warn "nginx absent (commande introuvable) : le reste du setup ne peut pas vérifier ni recharger nginx."
else
    nx_code=0; nx_sortie=$(run nginx -t 2>&1) || nx_code=$?
    nx_actif=$(systemctl is-active nginx 2>/dev/null) || nx_actif="inconnu"
    if (( nx_code == 0 )); then
        pass "nginx -t : la configuration est valide avant les changements de ce script."
    else
        fail "nginx -t REFUSE la configuration AVANT tout changement de ce script (problème déjà présent, à corriger) :"
        printf '%s\n' "$nx_sortie" | head -n 8 | sed 's/^/        nginx -t : /'
        nginx_aide "$nx_sortie"
        echo "        Après correction : nginx -t && systemctl reload nginx, puis relancer ce script. Les étapes qui modifient nginx restaurent leurs fichiers si nginx -t refuse, mais ne réparent pas ce problème."
    fi
    if [[ "$nx_actif" != "active" ]]; then
        warn "Le service nginx n'est pas actif (état : $nx_actif) : systemctl status nginx --no-pager ; journalctl -u nginx -n 30 --no-pager$( (( nx_code == 0 )) && echo " ; après vérification : systemctl start nginx" )."
    fi
fi

# --- 0b) Fuseau horaire du serveur (défaut : America/Montreal ; --timezone, TIMEZONE ; « none » : ne rien changer) -----------------
# La première fois (TIMEZONE absent de tous les fichiers de configuration), --update demande dans un terminal ; la réponse est gardée dans /etc/default/nginx-hardening.conf
# (ligne TIMEZONE=…). Sans terminal : le défaut est appliqué.
echo "--- 0b) Fuseau horaire ---"
TIMEZONE_A_ENREGISTRER=""
if [[ "$TIMEZONE" == "none" ]]; then
    sans_objet "fuseau horaire laissé tel quel (TIMEZONE=none)"
elif ! command -v timedatectl >/dev/null 2>&1; then
    warn "timedatectl introuvable — fuseau horaire non vérifié (souhaité : ${TIMEZONE:-$TIMEZONE_DEFAUT})."
else
    tz_voulu="${TIMEZONE:-$TIMEZONE_DEFAUT}"
    tz_actuel=$(run timedatectl show -p Timezone --value 2>/dev/null) || tz_actuel=""
    if [[ ! -e "${NGINX_HARDENING_ZONEINFO:-/usr/share/zoneinfo}/$tz_voulu" ]]; then
        warn "Fuseau horaire « $tz_voulu » inconnu de ce système (/usr/share/zoneinfo) — précisez --timezone ZONE (liste : timedatectl list-timezones)."
    elif [[ "$tz_actuel" == "$tz_voulu" ]]; then
        pass "Fuseau horaire : $tz_actuel."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Fuseau horaire : $tz_actuel (souhaité : $tz_voulu) — relancer avec --update pour le régler."
    else
        reponse="o"
        if [[ -z "$TIMEZONE" && -t 0 && -t 2 ]]; then
            read -r -p "  Régler le fuseau horaire du serveur à $tz_voulu (actuel : ${tz_actuel:-inconnu}) ? [O/n/autre zone] " reponse || reponse="o"
            case "$reponse" in
                ""|[oOyY]*) reponse="o" ;;
                [nN]*) reponse="n" ;;
                *) tz_voulu="$reponse"; reponse="o" ;;
            esac
        fi
        if [[ "$reponse" == "n" ]]; then
            TIMEZONE_A_ENREGISTRER="none"
            pass "Fuseau horaire laissé à $tz_actuel (choix mémorisé : TIMEZONE=none)."
        elif run timedatectl set-timezone "$tz_voulu" >/dev/null 2>&1; then
            [[ -z "$TIMEZONE" ]] && TIMEZONE_A_ENREGISTRER="$tz_voulu"
            pass "Fuseau horaire réglé à $tz_voulu (avant : ${tz_actuel:-inconnu})."
        else
            warn "Réglage du fuseau horaire à $tz_voulu en échec — lancer « timedatectl set-timezone $tz_voulu » et lire l'erreur."
        fi
    fi
fi
echo

# --- 0c) Dossiers de cache nginx (proxy_cache_path) : nginx refuse de démarrer si le dossier n'existe pas --------------------------
echo "--- 0c) Dossiers de cache nginx (proxy_cache_path) ---"
if ! command -v nginx >/dev/null 2>&1; then
    sans_objet "nginx absent"
else
    cache_dossiers=$(grep -rhE '^[[:space:]]*proxy_cache_path[[:space:]]+/' /etc/nginx 2>/dev/null | sed -E 's/^[[:space:]]*proxy_cache_path[[:space:]]+([^[:space:];]+).*/\1/' | sort -u) || cache_dossiers=""
    cache_proprio=$(grep -hE '^[[:space:]]*user[[:space:]]+[a-z_-]+' /etc/nginx/nginx.conf 2>/dev/null | head -1 | awk '{gsub(/;/,"",$2); print $2}') || cache_proprio=""
    cache_proprio="${cache_proprio:-www-data}"
    if [[ -z "$cache_dossiers" ]]; then
        pass "Aucun proxy_cache_path dans la configuration nginx."
    fi
    while IFS= read -r cache_dir; do
        [[ -n "$cache_dir" ]] || continue
        if [[ -d "$cache_dir" ]]; then
            pass "$cache_dir existe déjà."
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "$cache_dir n'existe pas : nginx -t refuse la configuration (relancer avec --update pour le créer)."
        elif run install -d -m 0750 -o "$cache_proprio" -g "$cache_proprio" "$cache_dir" 2>/dev/null; then
            pass "$cache_dir créé (propriétaire $cache_proprio)."
        else
            fail "Impossible de créer $cache_dir (propriétaire $cache_proprio) — à faire à la main : install -d -o $cache_proprio -g $cache_proprio $cache_dir"
        fi
    done <<< "$cache_dossiers"
fi
echo

# --- 0d) Courriel des programmes Python et Bash : relais SMTP, logiciels (msmtp), configuration commune --------------------------
# Les paramètres (hôte, port, chiffrement, identifiant, expéditeur, destinataire) sont gardés dans /etc/default/nginx-tools-mail.conf ; le MOT DE PASSE
# est dans /etc/default/nginx-tools-mail.pass (mode 0600, root), jamais dans le fichier de configuration, jamais affiché, jamais dans un courriel ni un rapport.
# Les programmes Python utilisent apps/_courriel.py ; Bash (sendmail, mail) passe par msmtp, configuré dans /etc/msmtprc à partir du même fichier.
echo "--- 0d) Courriel des programmes (relais SMTP, msmtp, configuration commune) ---"
MAIL_CONF="${NGINX_TOOLS_MAIL_CONF:-/etc/default/nginx-tools-mail.conf}"
MAIL_PASS="${NGINX_TOOLS_MAIL_PASSWORD_FILE:-/etc/default/nginx-tools-mail.pass}"
MSMTPRC="${NGINX_TOOLS_MSMTPRC:-/etc/msmtprc}"
mail_valeur() { if [[ -r "$MAIL_CONF" ]]; then sed -nE "s/^$1=\"?([^\"]*)\"?[[:space:]]*(#.*)?$/\1/p" "$MAIL_CONF" | tail -1; fi; return 0; }
# Logiciels : msmtp (envoi), sendmail (msmtp-mta, sauf si un autre serveur de courriel est déjà installé), mail (bsd-mailx).
paquet_installer msmtp msmtp
if [[ -x /usr/sbin/sendmail || -x /usr/lib/sendmail ]] || command -v sendmail >/dev/null 2>&1; then
    pass "sendmail présent (commande sendmail des programmes Bash)."
elif [[ "$CHECK_ONLY" == "1" ]]; then
    warn "sendmail absent (paquet msmtp-mta) — relancer avec --update pour l'installer."
elif DEBIAN_FRONTEND=noninteractive run apt-get install -y msmtp-mta >/dev/null 2>&1; then
    pass "msmtp-mta installé (commande sendmail)."
else
    fail "installation du paquet msmtp-mta en échec — lancer « apt-get install msmtp-mta » et lire l'erreur."
fi
paquet_installer mail bsd-mailx
# Valeurs : option ou fichier de configuration du setup, sinon fichier commun existant, sinon (avec --update, dans un terminal) on demande.
for mail_cle in HOST PORT SECURITY USER FROM TO; do
    mail_var="MAIL_$mail_cle"
    [[ -n "${!mail_var}" ]] || printf -v "$mail_var" '%s' "$(mail_valeur "$mail_var")"
done
mail_deja=0; [[ -n "$MAIL_HOST" && -r "$MAIL_PASS" ]] && mail_deja=1
mail_demander() {      # mail_demander VARIABLE "question" [défaut] : affecte la réponse (ou le défaut) ; sans terminal, garde la valeur
    local nom="$1" question="$2" defaut="${3:-}" reponse=""
    [[ -n "${!nom}" ]] && return 0
    if mail_terminal; then
        read -r -p "  $question${defaut:+ [$defaut]} : " reponse || reponse=""
    fi
    printf -v "$nom" '%s' "${reponse:-$defaut}"
}
mail_terminal() { [[ -t 0 && -t 2 ]]; }       # questions posées sur le terminal (entrée et erreur standard) : fonctionne aussi avec « | tee journal » (sortie redirigée)
mail_valide() { [[ "$1" != *[\"\$\`\\]* && "$1" != *$'\n'* ]]; }
mail_non=0      # réponse « non » (défaut) à la question : le setup SMTP est sauté pour ce passage
if [[ "$CHECK_ONLY" != "1" ]] && ! (( mail_deja && ! MAIL_SETUP )) && (( ! MAIL_SETUP )) && [[ -z "$MAIL_HOST" && -z "${NGINX_TOOLS_MAIL_PASSWORD:-}" ]] && mail_terminal; then
    read -r -p "  Faire le setup du courriel (relais SMTP) maintenant ? [o/N] : " mail_rep || mail_rep=""
    case "${mail_rep,,}" in o|oui|y|yes) ;; *) mail_non=1 ;; esac
fi
if [[ "$CHECK_ONLY" == "1" ]]; then
    if (( mail_deja )); then
        pass "Courriel configuré : $MAIL_HOST:${MAIL_PORT:-587} (${MAIL_SECURITY:-starttls}), expéditeur ${MAIL_FROM:-$MAIL_USER}, destinataire ${MAIL_TO:-non défini}."
    else
        warn "Courriel non configuré ($MAIL_CONF et $MAIL_PASS) — relancer avec --update dans un terminal : le relais SMTP et le mot de passe sont demandés une fois."
    fi
elif (( mail_deja && ! MAIL_SETUP )); then
    pass "Courriel déjà configuré : $MAIL_HOST:${MAIL_PORT:-587} (--mail-setup pour le redemander)."
elif (( mail_non )); then
    warn "Courriel : setup reporté (réponse non) — relancer avec --update et répondre o, ou avec --mail-setup."
else
    if mail_terminal; then
        echo "  Configuration du courriel des programmes (demandée une seule fois) : Entrée garde la valeur entre crochets."
        echo "  Les réponses vont dans $MAIL_CONF (sans mot de passe) ; le mot de passe va seul dans $MAIL_PASS (mode 0600, jamais affiché)."
    else
        echo "  Aucun terminal pour poser les questions du courriel (entrée non interactive) : relancer dans un terminal, ou passer --mail-host et --mail-user (mot de passe : variable NGINX_TOOLS_MAIL_PASSWORD)."
    fi
    mail_demander MAIL_HOST "Serveur SMTP (relais)" ""
    mail_demander MAIL_PORT "Port" "587"
    mail_demander MAIL_SECURITY "Chiffrement (starttls, ssl ou none)" "starttls"
    mail_demander MAIL_USER "Nom d'utilisateur" ""
    mail_demander MAIL_FROM "Adresse d'expéditeur" "$MAIL_USER"
    mail_demander MAIL_TO "Adresse de destination des courriels de la suite" "$MAIL_FROM"
    mail_mdp="${NGINX_TOOLS_MAIL_PASSWORD:-}"
    if [[ -z "$mail_mdp" && -n "$MAIL_HOST" ]] && mail_terminal; then
        read -r -s -p "  Mot de passe de $MAIL_USER (aucun écho, gardé dans $MAIL_PASS en mode 0600) : " mail_mdp || mail_mdp=""
        echo
    fi
    if [[ -z "$MAIL_HOST" || -z "$MAIL_USER" ]]; then
        warn "Courriel non configuré : serveur SMTP ou identifiant manquant — relancer avec --update dans un terminal (ou --mail-host et --mail-user)."
    elif [[ -z "$mail_mdp" && ! -r "$MAIL_PASS" ]]; then
        warn "Courriel non configuré : mot de passe manquant — relancer avec --update dans un terminal (ou variable NGINX_TOOLS_MAIL_PASSWORD)."
    elif ! [[ "$MAIL_PORT" =~ ^[0-9]+$ ]] || [[ ! "$MAIL_SECURITY" =~ ^(starttls|ssl|none)$ ]]; then
        fail "Courriel : port numérique et chiffrement starttls, ssl ou none attendus (reçus : « $MAIL_PORT », « $MAIL_SECURITY »)."
    elif ! mail_valide "$MAIL_HOST$MAIL_USER$MAIL_FROM$MAIL_TO" || ! mail_valide "$mail_mdp"; then
        fail "Courriel : guillemets, \$, accent grave, barre oblique inverse et retour à la ligne refusés dans les réponses (fichiers de configuration)."
    else
        mkdir -p "$(dirname "$MAIL_CONF")" 2>/dev/null || true
        mail_tmp=$(umask 077; mktemp "$MAIL_CONF.XXXXXX") || mail_tmp=""
        if [[ -z "$mail_tmp" ]]; then
            fail "Courriel : écriture impossible dans $(dirname "$MAIL_CONF")."
        else
            {
                echo "# Généré par nginx-hardening.sh (étape 0d) — courriel des programmes Python et Bash. AUCUN mot de passe ici : il est dans $MAIL_PASS."
                echo "MAIL_HOST=\"$MAIL_HOST\""
                echo "MAIL_PORT=\"$MAIL_PORT\""
                echo "MAIL_SECURITY=\"$MAIL_SECURITY\""
                echo "MAIL_USER=\"$MAIL_USER\""
                echo "MAIL_FROM=\"$MAIL_FROM\""
                echo "MAIL_TO=\"$MAIL_TO\""
                echo "MAIL_PASSWORD_FILE=\"$MAIL_PASS\""
                echo "# Pièce jointe plus grosse que cette taille (Mo) : remplacée par un lien (copie dans MAIL_LINK_DIR ; MAIL_LINK_URL = adresse publique de ce dossier)."
                echo "MAIL_ATTACH_MAX_MB=\"$(mail_valeur MAIL_ATTACH_MAX_MB || true)\""
                echo "MAIL_LINK_DIR=\"$(mail_valeur MAIL_LINK_DIR || true)\""
                echo "MAIL_LINK_URL=\"$(mail_valeur MAIL_LINK_URL || true)\""
                echo "MAIL_LINK_DAYS=\"$(mail_valeur MAIL_LINK_DAYS || true)\""
            } > "$mail_tmp"
            sed -i -E 's/^MAIL_ATTACH_MAX_MB=""$/MAIL_ATTACH_MAX_MB="100"/; s/^MAIL_LINK_DIR=""$/MAIL_LINK_DIR="\/var\/lib\/nginx-tools\/pieces-jointes"/; s/^MAIL_LINK_DAYS=""$/MAIL_LINK_DAYS="30"/' "$mail_tmp"
            chmod 0644 "$mail_tmp" && mv "$mail_tmp" "$MAIL_CONF"          # sans secret : lisible par les programmes
            if [[ -n "$mail_mdp" ]]; then
                mail_tmp=$(umask 077; mktemp "$MAIL_PASS.XXXXXX")
                printf '%s\n' "$mail_mdp" > "$mail_tmp"
                chmod 0600 "$mail_tmp" && mv "$mail_tmp" "$MAIL_PASS"
            fi
            chmod 0600 "$MAIL_PASS" 2>/dev/null || true
            pass "Courriel configuré : $MAIL_CONF (sans mot de passe) et $MAIL_PASS (mode 0600)."
            # msmtp (sendmail et mail des programmes Bash) : /etc/msmtprc, sauf s'il existe et n'a pas été créé ici.
            if [[ -e "$MSMTPRC" ]] && ! grep -q "nginx-hardening.sh" "$MSMTPRC" 2>/dev/null; then
                warn "$MSMTPRC existe et n'a pas été créé par ce programme — laissé tel quel (copie de la configuration à y reporter : hôte $MAIL_HOST, port $MAIL_PORT, utilisateur $MAIL_USER)."
            else
                case "$MAIL_SECURITY" in
                    ssl) mail_tls="tls on
tls_starttls off" ;;
                    none) mail_tls="tls off" ;;
                    *) mail_tls="tls on
tls_starttls on" ;;
                esac
                mail_tmp=$(umask 077; mktemp "$MSMTPRC.XXXXXX")
                {
                    echo "# Généré par nginx-hardening.sh (étape 0d) — sans mot de passe : lu dans $MAIL_PASS."
                    echo "defaults"
                    echo "auth on"
                    echo "$mail_tls"
                    echo "tls_trust_file /etc/ssl/certs/ca-certificates.crt"
                    echo "account default"
                    echo "host $MAIL_HOST"
                    echo "port $MAIL_PORT"
                    echo "from ${MAIL_FROM:-$MAIL_USER}"
                    echo "user $MAIL_USER"
                    echo "passwordeval cat $MAIL_PASS"
                    echo "set_from_header on"
                } > "$mail_tmp"
                chmod 0644 "$mail_tmp" && mv "$mail_tmp" "$MSMTPRC"
                pass "$MSMTPRC écrit (commandes sendmail et mail des programmes Bash)."
            fi
            if mail_terminal; then
                read -r -p "  Envoyer un courriel de test à $MAIL_TO maintenant ? [O/n] " mail_rep || mail_rep="n"
                case "$mail_rep" in
                    [nN]*) ;;
                    *)  if mail_sortie=$(timeout --foreground 60 python3 "$SCRIPT_DIR/apps/_courriel.py" --test 2>&1); then pass "Courriel de test envoyé à $MAIL_TO."
                        else fail "Courriel de test refusé : $mail_sortie"; fi ;;
                esac
            else
                echo "  Courriel de test : python3 $SCRIPT_DIR/apps/_courriel.py --test"
            fi
        fi
    fi
fi
echo "  Entrées DNS exactes à créer (SPF, DMARC, DKIM) : étape 13 ci-dessous ; guide : doc/courriel-securise.md."
echo

# --- 0e) Changement de nom DNS public (ex. odoo-lab.exemple.org -> odoo.exemple.org) : nginx et certificat Let's Encrypt -------------
# --rename-from ANCIEN --rename-to NOUVEAU. Sans --update : rapport de ce qui serait changé. Avec --update : sauvegarde des fichiers nginx touchés, noms remplacés
# (server_name, redirections…), certificat du nouveau nom obtenu avec certbot (webroot /var/www/letsencrypt) s'il n'existe pas, chemins du certificat remplacés,
# « nginx -t » puis rechargement ; en cas de refus de nginx, tout est restauré. Odoo (web.base.url, dbfilter) et le DNS ne sont jamais modifiés : rappels affichés.
echo "--- 0e) Changement de nom DNS (nginx et Let's Encrypt) ---"
renom_valide() { [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]]; }
renom_fichiers() {      # fichiers réels (sans doublon) de nginx qui mentionnent l'ancien nom (nom entier, pas un sous-domaine)
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f reel vus=" "
    for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do
        [[ -f "$f" ]] || continue
        reel=$(readlink -f "$f" 2>/dev/null) || reel="$f"
        [[ "$vus" == *" $reel "* ]] && continue
        vus+="$reel "
        grep -Eq "(^|[^A-Za-z0-9._-])${RENAME_FROM//./\\.}([^A-Za-z0-9._-]|\$)" "$reel" && echo "$reel"
    done
    return 0
}
renom_candidats() {     # noms de domaine complets des directives server_name de nginx (sans doublon, sans le nouveau nom) : les anciens noms possibles
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f mot
    for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do
        [[ -f "$f" ]] || continue
        sed -n -E 's/^[[:space:]]*server_name[[:space:]]+([^;]*);.*/\1/p' "$f" 2>/dev/null
    done | tr -s ' \t' '\n' | while IFS= read -r mot; do
        renom_valide "$mot" && [[ "$mot" != "$RENAME_TO" ]] && echo "$mot"
    done | sort -u
    return 0
}
# Seul le NOUVEAU nom est donné : l'ancien est cherché dans les server_name de nginx (un seul nom du même domaine : retenu ; plusieurs : demandé dans un terminal).
if [[ -z "$RENAME_FROM" && -n "$RENAME_TO" ]] && renom_valide "$RENAME_TO"; then
    mapfile -t rn_cands < <(renom_candidats)
    rn_domaine="${RENAME_TO#*.}"; rn_memes=()
    for rn_c in "${rn_cands[@]}"; do [[ "${rn_c#*.}" == "$rn_domaine" ]] && rn_memes+=("$rn_c"); done
    (( ${#rn_memes[@]} > 0 )) && rn_cands=("${rn_memes[@]}")
    if (( ${#rn_cands[@]} == 1 )); then
        RENAME_FROM="${rn_cands[0]}"
        echo "  Ancien nom (--rename-from non donné) : $RENAME_FROM, seul nom de domaine trouvé dans les server_name de nginx."
    elif (( ${#rn_cands[@]} > 1 )); then
        echo "  Noms trouvés dans les server_name de nginx : ${rn_cands[*]}"
        if [[ "$CHECK_ONLY" != "1" ]] && mail_terminal; then
            read -r -p "  Ancien nom à remplacer par $RENAME_TO : " RENAME_FROM || RENAME_FROM=""
        fi
        [[ -n "$RENAME_FROM" ]] || warn "Plusieurs anciens noms possibles : préciser lequel avec --rename-from NOM."
    else
        warn "Aucun nom de domaine trouvé dans les server_name de nginx : préciser l'ancien nom avec --rename-from NOM."
    fi
fi
if [[ -z "$RENAME_FROM" && -z "$RENAME_TO" ]]; then
    echo "  [--]   Aucun changement de nom demandé (--rename-from ANCIEN --rename-to NOUVEAU, avec --update pour l'appliquer)."
elif ! renom_valide "$RENAME_FROM" || ! renom_valide "$RENAME_TO"; then
    if [[ -z "$RENAME_FROM" ]]; then
        fail "Changement de nom : l'ancien nom est introuvable ou ambigu — relancer avec --rename-from ANCIEN --rename-to $RENAME_TO."
    else
        fail "Changement de nom : deux noms de domaine complets sont attendus (reçus : « $RENAME_FROM » et « $RENAME_TO »)."
    fi
elif [[ "$RENAME_FROM" == "$RENAME_TO" ]]; then
    fail "Changement de nom : l'ancien et le nouveau nom sont identiques ($RENAME_TO)."
else
    rn_le="${NGINX_HARDENING_LETSENCRYPT_DIR:-/etc/letsencrypt}"
    rn_cert="$rn_le/live/$RENAME_TO/fullchain.pem"
    rn_ancien_re="${RENAME_FROM//./\\.}"
    rn_limite='(^|[^A-Za-z0-9._-])'"$rn_ancien_re"'([^A-Za-z0-9._-]|$)'
    mapfile -t rn_fichiers < <(renom_fichiers)
    rn_cert_ok=0
    if [[ -r "$rn_cert" ]]; then
        rn_cert_ok=1
        if command -v openssl >/dev/null 2>&1 && ! openssl x509 -in "$rn_cert" -noout -checkhost "$RENAME_TO" 2>/dev/null | grep -q "does match"; then rn_cert_ok=0; fi
    fi
    rn_dns=$(getent hosts "$RENAME_TO" 2>/dev/null | awk 'NR==1{print $1}') || rn_dns=""
    if (( ${#rn_fichiers[@]} == 0 )); then
        warn "Changement de nom : aucun fichier nginx (sites-enabled/, conf.d/) ne mentionne $RENAME_FROM — rien à remplacer."
    else
        echo "  Fichiers nginx qui mentionnent $RENAME_FROM : ${rn_fichiers[*]}"
    fi
    if (( rn_cert_ok )); then
        pass "Certificat de $RENAME_TO déjà présent et valide pour ce nom ($rn_cert)."
    elif [[ -z "$rn_dns" ]]; then
        warn "Le nom $RENAME_TO n'existe pas encore dans le DNS : Let's Encrypt refusera le certificat. Créer chez le fournisseur du domaine un enregistrement A (et AAAA si IPv6) $RENAME_TO vers l'adresse IP de CE serveur, attendre la propagation, puis relancer."
    else
        echo "  Le nom $RENAME_TO pointe vers $rn_dns : vérifier que c'est bien l'adresse IP de CE serveur (sinon Let's Encrypt échouera)."
    fi
    if [[ "$CHECK_ONLY" == "1" ]]; then
        if (( ${#rn_fichiers[@]} > 0 )); then
            warn "Changement de nom $RENAME_FROM → $RENAME_TO à faire : relancer avec --update (sauvegarde, remplacement dans nginx, certificat de $RENAME_TO réutilisé s'il existe, sinon demandé à Let's Encrypt, nginx -t, rechargement)."
        fi
    elif (( ${#rn_fichiers[@]} > 0 )); then
        rn_sauv="${NGINX_HARDENING_BACKUP_DIR:-/var/backups/nginx-hardening}"
        mkdir -p "$rn_sauv" 2>/dev/null || true
        rn_stamp=$(date +%Y%m%d-%H%M%S); rn_copies=(); rn_ok=1
        for rn_f in "${rn_fichiers[@]}"; do
            rn_c="$rn_sauv/$(basename "$rn_f").$rn_stamp.bak"
            if cp -p "$rn_f" "$rn_c" 2>/dev/null; then rn_copies+=("$rn_c"); else rn_ok=0; fail "Changement de nom : copie de sauvegarde de $rn_f impossible — rien n'est modifié."; break; fi
        done
        renom_restaurer() { local i; for i in "${!rn_fichiers[@]}"; do cp -p "${rn_copies[$i]}" "${rn_fichiers[$i]}" 2>/dev/null || true; done; }
        if (( rn_ok )); then
            # Phase 1 : le nom (server_name, redirections…) ; les chemins du certificat (letsencrypt/live|archive/ANCIEN) restent tels quels pour l'instant.
            for rn_f in "${rn_fichiers[@]}"; do
                sed -i -E "\#letsencrypt/(live|archive)/${rn_ancien_re}([^A-Za-z0-9._-]|\$)#!{s#${rn_limite}#\1${RENAME_TO}\2#g;s#${rn_limite}#\1${RENAME_TO}\2#g}" "$rn_f"
            done
            if ! run nginx -t >/dev/null 2>&1; then
                renom_restaurer
                fail "Changement de nom : nginx -t refuse la nouvelle configuration — anciennes versions restaurées, nginx NON rechargé. Sauvegardes : $rn_sauv"
                rn_ok=0
            else
                run systemctl reload nginx >/dev/null 2>&1 || true
                pass "nginx : $RENAME_FROM remplacé par $RENAME_TO dans ${#rn_fichiers[@]} fichier(s) ; nginx -t réussi, nginx rechargé. Sauvegardes : $rn_sauv"
            fi
        fi
        if (( rn_ok && ! rn_cert_ok )); then
            paquet_installer certbot certbot
            if command -v certbot >/dev/null 2>&1; then
                rn_args=(certonly --webroot -w /var/www/letsencrypt -d "$RENAME_TO" --cert-name "$RENAME_TO" --non-interactive --agree-tos)
                if [[ -n "$MAIL_TO" ]]; then rn_args+=(-m "$MAIL_TO"); else rn_args+=(--register-unsafely-without-email); fi
                if rn_sortie=$(run certbot "${rn_args[@]}" 2>&1) && [[ -r "$rn_cert" ]]; then
                    rn_cert_ok=1
                    pass "Certificat Let's Encrypt obtenu pour $RENAME_TO ($rn_cert)."
                else
                    fail "certbot n'a pas pu obtenir le certificat de $RENAME_TO (le nom doit pointer vers CE serveur, port 80 ouvert, nginx servant /.well-known/acme-challenge/ depuis /var/www/letsencrypt) :"
                    printf '%s\n' "$rn_sortie" | tail -n 8 | sed 's/^/         /'
                fi
            fi
        fi
        if (( rn_ok && rn_cert_ok )); then
            # Phase 2 : les chemins du certificat passent à celui du nouveau nom.
            for rn_f in "${rn_fichiers[@]}"; do
                sed -i "s#letsencrypt/live/${rn_ancien_re}/#letsencrypt/live/${RENAME_TO}/#g" "$rn_f"
            done
            if ! run nginx -t >/dev/null 2>&1; then
                renom_restaurer
                fail "Changement de nom : nginx -t refuse les chemins du nouveau certificat — anciennes versions restaurées, nginx NON rechargé."
            else
                run systemctl reload nginx >/dev/null 2>&1 || true
                pass "nginx : certificat de $RENAME_TO en service ; nginx -t réussi, nginx rechargé."
            fi
        elif (( rn_ok )); then
            warn "Les chemins du certificat de $RENAME_FROM sont gardés tant que $RENAME_TO n'a pas de certificat : les navigateurs refuseront $RENAME_TO. Corriger la cause ci-dessus puis relancer la même commande."
        fi
    fi
    # Ce que le programme ne modifie jamais : rappels précis.
    echo "  À faire à la main pour $RENAME_TO :"
    echo "    - DNS : enregistrement A (et AAAA) $RENAME_TO vers l'adresse IP de ce serveur ; retirer $RENAME_FROM du DNS seulement quand plus personne ne l'utilise."
    echo "    - Odoo : Paramètres → Technique → Paramètres système → web.base.url = https://$RENAME_TO (et freeze.url si présent)."
    if [[ -n "${ODOO_CONF:-}" && -r "$ODOO_CONF" ]] && grep -Eq "$rn_limite" "$ODOO_CONF" 2>/dev/null; then
        warn "$ODOO_CONF mentionne encore $RENAME_FROM (dbfilter ? ligne : $(grep -En "$rn_limite" "$ODOO_CONF" | head -n 1 | cut -c1-80)) — à adapter, puis redémarrer Odoo."
    fi
    rn_defaut=$(grep -lE "$rn_limite" "/etc/default/"* 2>/dev/null | tr '\n' ' ') || rn_defaut=""
    [[ -z "$rn_defaut" ]] || warn "Fichiers de /etc/default qui mentionnent encore $RENAME_FROM : $rn_defaut— à adapter (programmes de surveillance, courriel…)."
    echo "    - Anciens certificat et configuration : « certbot certificates » puis « certbot delete --cert-name $RENAME_FROM » quand $RENAME_FROM n'est plus servi."
    echo "    - HSTS : les navigateurs qui ont visité $RENAME_FROM continueront d'exiger HTTPS pour lui ; garder $RENAME_FROM avec un certificat valide et une redirection 301 vers $RENAME_TO."
    echo "    - Vérification : app-log-live.py --diagnose --diagnose-host $RENAME_TO (certificat vu comme un navigateur)."
fi
echo

# --- 1) Répertoire pour les défis ACME (Let's Encrypt) -----------------------------------------------------------
echo "--- 1) Répertoire ACME (/var/www/letsencrypt) ---"
if [[ -n "${HARDENING_CONFIG:-}" ]]; then
if [[ -d /var/www/letsencrypt ]]; then
    pass "/var/www/letsencrypt existe déjà."
elif [[ "$CHECK_ONLY" == "1" ]]; then
    fail "/var/www/letsencrypt n'existe pas (relancer avec --update pour le créer)."
else
    if run mkdir -p /var/www/letsencrypt 2>/dev/null; then
        pass "/var/www/letsencrypt créé."
    else
        warn "Impossible de créer /var/www/letsencrypt (permissions ? /var/www absent ou non accessible ?) — à faire manuellement si nécessaire."
    fi
fi
echo

# --- 2) Journal dédié au capteur catch-all -------------------------------------------------------------------
else
    sans_objet "pas de configuration de durcissement nginx livrée pour cette application (répertoire ACME de la configuration nginx-odoo)"
fi
echo "--- 2) Journal catch-all (/var/log/nginx/odoo-catchall-444.log) ---"
if [[ -n "${HARDENING_CONFIG:-}" ]]; then
CATCHALL_LOG=/var/log/nginx/odoo-catchall-444.log
if [[ -f "$CATCHALL_LOG" ]]; then
    owner=$(stat -c '%U:%G' "$CATCHALL_LOG" 2>/dev/null) || owner="?"
    if [[ "$owner" == "www-data:adm" ]]; then
        pass "$CATCHALL_LOG existe déjà, propriétaire correct (www-data:adm)."
    else
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "$CATCHALL_LOG existe mais son propriétaire est '$owner' (attendu www-data:adm)."
        elif run chown www-data:adm "$CATCHALL_LOG" 2>/dev/null; then
            pass "$CATCHALL_LOG : propriétaire corrigé (www-data:adm)."
        else
            warn "$CATCHALL_LOG : impossible de définir le propriétaire www-data:adm (utilisateur ou groupe absent sur ce système ?) — à corriger manuellement si nécessaire."
        fi
    fi
elif [[ "$CHECK_ONLY" == "1" ]]; then
    fail "$CATCHALL_LOG n'existe pas (relancer avec --update pour le créer)."
else
    CATCHALL_LOG_DIR=$(dirname "$CATCHALL_LOG")
    if [[ ! -d "$CATCHALL_LOG_DIR" ]]; then
        fail "$CATCHALL_LOG_DIR n'existe pas — nginx est-il installé ? (le paquet nginx crée normalement ce répertoire). Impossible de créer le journal catch-all tant que ce répertoire n'existe pas."
    else
        run touch "$CATCHALL_LOG"
        if run chown www-data:adm "$CATCHALL_LOG" 2>/dev/null; then
            pass "$CATCHALL_LOG créé, propriétaire www-data:adm."
        else
            warn "$CATCHALL_LOG créé mais impossible de définir le propriétaire www-data:adm (utilisateur ou groupe absent sur ce système ?) — à corriger manuellement si nécessaire."
        fi
    fi
fi
echo

# --- 3) Page de maintenance -------------------------------------------------------------------------------------
else
    sans_objet "pas de capteur catch-all dans sa configuration nginx"
fi
echo "--- 3) Page de maintenance (/var/www/maintenance/index.html) ---"
if [[ -n "${HARDENING_CONFIG:-}" ]]; then
MAINT_DIR=/var/www/maintenance
MAINT_FILE="$MAINT_DIR/index.html"
MAINT_SOURCE="$SCRIPT_DIR/maintenance/index.html"
for maint_cand in "$SCRIPT_DIR/maintenance/index.html" /etc/nginx/maintenance/index.html /root/scripts/maintenance/index.html; do      # à côté du programme, puis la configuration nginx déployée
    if [[ -r "$maint_cand" ]]; then MAINT_SOURCE="$maint_cand"; break; fi
done
if [[ -f "$MAINT_FILE" ]]; then
    pass "$MAINT_FILE existe déjà."
elif [[ "$CHECK_ONLY" == "1" ]]; then
    fail "$MAINT_FILE n'existe pas — nginx affichera l'erreur brute d'Odoo plutôt que la page de maintenance."
else
    if [[ ! -r "$MAINT_SOURCE" ]]; then
        warn "Fichier source introuvable ($MAINT_SOURCE) — impossible de copier automatiquement. Copiez-le vous-même vers $MAINT_FILE."
    else
        if run mkdir -p "$MAINT_DIR" 2>/dev/null && run cp "$MAINT_SOURCE" "$MAINT_FILE" 2>/dev/null; then
            pass "$MAINT_FILE installé depuis $MAINT_SOURCE."
        else
            warn "Impossible de créer $MAINT_DIR ou d'y copier $MAINT_SOURCE (permissions ? /var/www absent ou non accessible ?) — à faire manuellement si nécessaire."
        fi
    fi
fi
echo

PORT_EXPOSED=0
NEED_FAIL2BAN_RESTART=0
# iptables_rendre_persistant : sans paquet de persistance, les règles disparaissent au redémarrage — --update installe iptables-persistent et enregistre.
iptables_rendre_persistant() {
    if command -v netfilter-persistent >/dev/null 2>&1; then
        if run netfilter-persistent save >/dev/null 2>&1; then
            for ipt_f in /etc/iptables/rules.v4 /etc/iptables/rules.v6 /etc/iptables/ipsets; do         # chaînes de fail2ban : recréées par lui au démarrage (jamais restaurées en double)
                if [[ -f "$ipt_f" ]] && grep -q 'f2b-' "$ipt_f" 2>/dev/null; then run sed -i '/f2b-/d' "$ipt_f"; fi
            done
            pass "iptables : règles enregistrées (netfilter-persistent) — elles survivent à un redémarrage."
        else
            warn "iptables : « netfilter-persistent save » en échec — les règles sont en mémoire seulement."
        fi
    elif command -v apt-get >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive run apt-get install -y iptables-persistent >/dev/null 2>&1 && command -v netfilter-persistent >/dev/null 2>&1; then
        run netfilter-persistent save >/dev/null 2>&1 || true
        for ipt_f in /etc/iptables/rules.v4 /etc/iptables/rules.v6 /etc/iptables/ipsets; do
            if [[ -f "$ipt_f" ]] && grep -q 'f2b-' "$ipt_f" 2>/dev/null; then run sed -i '/f2b-/d' "$ipt_f"; fi
        done
        pass "iptables-persistent installé et règles enregistrées — elles survivent à un redémarrage."
    else
        warn "iptables : règle ajoutée en mémoire seulement — installez iptables-persistent (ou équivalent) pour qu'elle survive à un redémarrage."
    fi
}

# --- 4) Interface d'écoute d'Odoo (diagnostic seulement — jamais d'édition automatique d'odoo.conf) --------------
else
    sans_objet "pas de page de maintenance de la configuration nginx-odoo"
fi
echo "--- 4) Interface d'écoute d'Odoo (diagnostic — ports $ODOO_HTTP_PORT et $ODOO_GEVENT_PORT) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if ! command -v ss >/dev/null 2>&1; then
    warn "Commande 'ss' introuvable — impossible de vérifier l'interface d'écoute d'Odoo automatiquement."
else
    for port in "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT"; do
        binding=$(run ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $4}' | head -1) || true
        if [[ -z "$binding" ]]; then
            warn "Rien n'écoute sur le port $port actuellement (Odoo est-il démarré ?) — impossible de vérifier."
        elif [[ "$binding" == 127.0.0.1:* || "$binding" == \[::1\]:* ]]; then
            pass "Port $port : écoute sur $binding (local seulement — correct)."
        else
            fail "Port $port : écoute sur $binding (accessible depuis l'EXTÉRIEUR) — voir la recommandation ci-dessous."
            PORT_EXPOSED=1
        fi
    done
fi

# Amonts nginx : les ports des « upstream » doivent être ceux d'Odoo (http_port / gevent_port de la configuration d'Odoo).
# Sinon nginx n'atteint pas Odoo et répond la page de maintenance (502/503/504) alors qu'Odoo tourne très bien.
amonts_nginx_lister() {
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f reel vus=" "
    for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do
        [[ -f "$f" ]] || continue
        reel=$(readlink -f "$f" 2>/dev/null) || reel="$f"
        [[ "$vus" == *" $reel "* ]] && continue
        vus+="$reel "
        awk -v fic="$f" -v reel="$reel" '
            /^[[:space:]]*#/ { next }
            /^[[:space:]]*upstream[[:space:]]+[^[:space:]{]+/ { nom = $2; sub(/\{.*/, "", nom); dans = 1 }
            dans && match($0, /server[[:space:]]+[^[:space:];]+/) {
                srv = substr($0, RSTART, RLENGTH); sub(/^server[[:space:]]+/, "", srv)
                print fic "\t" reel "\t" FNR "\t" nom "\t" srv
            }
            dans && /\}/ { dans = 0 }
        ' "$f"
    done
}
amonts_n=0
amonts_ko=0
while IFS=$'\t' read -r am_fic am_reel am_ligne am_nom am_srv; do
    [[ -n "$am_srv" ]] || continue
    am_hote="${am_srv%:*}"; am_port="${am_srv##*:}"
    [[ "$am_hote" == "$am_srv" ]] && continue                        # pas de port (socket unix, nom de groupe…)
    [[ "$am_port" =~ ^[0-9]+$ ]] || continue
    case "$am_hote" in 127.0.0.1|localhost|"[::1]") ;; *) continue ;; esac
    case "$am_nom" in
        odoo[0-9]*)                                                  # autre version d'Odoo (ex. odoo17, odoo17_chat) : ports propres, jamais ceux de cette instance
            echo "  [--]   nginx : l'amont « $am_nom » ($am_fic:$am_ligne) est celui d'une autre version d'Odoo (port $am_port) : non vérifié, non modifié."
            continue ;;
        *chat*|*longpoll*|*gevent*|*websocket*) am_attendu="$ODOO_GEVENT_PORT"; am_genre="gevent" ;;
        odoo*) am_attendu="$ODOO_HTTP_PORT"; am_genre="HTTP" ;;
        *) continue ;;
    esac
    amonts_n=$((amonts_n + 1))
    if [[ "$am_port" == "$am_attendu" ]]; then
        pass "nginx : l'amont « $am_nom » ($am_fic:$am_ligne) vise le port $am_port, qui est celui d'Odoo ($am_genre)."
        continue
    fi
    amonts_ko=$((amonts_ko + 1))
    if [[ "$CHECK_ONLY" == "1" ]]; then
        fail "nginx : l'amont « $am_nom » ($am_fic:$am_ligne) vise le port $am_port, mais Odoo ($am_genre) est configuré sur $am_attendu ($ODOO_PORTS_SOURCE) — page de maintenance probable. Relancer avec --update pour corriger la configuration nginx."
        continue
    fi
    am_sauv="${NGINX_HARDENING_BACKUP_DIR:-/var/backups/nginx-hardening}"
    mkdir -p "$am_sauv" 2>/dev/null || true
    am_copie="$am_sauv/$(basename "$am_reel").$(date +%Y%m%d-%H%M%S).bak"      # hors de sites-enabled : nginx chargerait la copie
    cp -p "$am_reel" "$am_copie" 2>/dev/null || { fail "nginx : copie de sauvegarde de $am_reel impossible — fichier non modifié."; continue; }
    sed -i -E "${am_ligne}s/(server[[:space:]]+[^;[:space:]]*:)${am_port}([[:space:];])/\1${am_attendu}\2/" "$am_reel"
    if run nginx -t >/dev/null 2>&1; then
        run systemctl reload nginx >/dev/null 2>&1 || true
        pass "nginx : l'amont « $am_nom » ($am_fic:$am_ligne) passe du port $am_port à $am_attendu (Odoo, $am_genre) ; nginx -t réussi, nginx rechargé. Sauvegarde : $am_copie"
    else
        cp -p "$am_copie" "$am_reel" 2>/dev/null || true
        fail "nginx : le port $am_attendu de l'amont « $am_nom » est refusé par nginx -t — ancienne version restaurée ($am_fic), nginx NON rechargé."
    fi
done < <(amonts_nginx_lister)
if (( amonts_n == 0 )); then
    echo "  [--]   nginx : aucun amont « odoo » sur 127.0.0.1 trouvé dans sites-enabled/ ni conf.d/ (vérification des ports ignorée)."
fi

# Websocket d'Odoo (discussions en temps réel) : sans le bon « location /websocket » dans nginx, les messages n'arrivent pas en direct (ou avec un long retard) chez les
# personnes connectées. Vérifie : la route /websocket vers le port gevent, HTTP 1.1, les en-têtes Upgrade et Connection, le délai de lecture (Odoo envoie un ping toutes les 40
# à 55 s ; le défaut de nginx est 60 s) et le nombre de connexions de nginx. Lit nginx.conf avec ses « include » (ou sites-enabled/ et conf.d/ à défaut).
WS_DELAI_MIN=120        # secondes : en dessous, la marge sur les pings d'Odoo est trop mince
WS_DELAI_REGLE=300      # secondes : valeur posée par --update
ws_lire_fichier() {
    local f="$1" prof="${2:-0}" n=0 ligne motif g
    [[ -f "$f" ]] || return 0
    while IFS= read -r ligne || [[ -n "$ligne" ]]; do
        n=$((n + 1))
        ligne="${ligne//$'\t'/ }"
        if [[ "$ligne" =~ ^[[:space:]]*include[[:space:]]+([^\;]+)\; ]] && (( prof < 5 )); then
            motif="${BASH_REMATCH[1]}"
            [[ "$motif" == /* ]] || motif="$ws_racine/$motif"
            if [[ "$motif" == /etc/nginx/* && "$ws_racine" != /etc/nginx ]]; then motif="$ws_racine/${motif#/etc/nginx/}"; fi      # dossier nginx de remplacement (tests)
            for g in $motif; do                                  # glob volontairement non protégé
                if [[ -f "$g" ]]; then ws_lire_fichier "$g" $((prof + 1)); fi
            done
        else
            printf '%s:%s\t%s\n' "$f" "$n" "$ligne"
        fi
    done < "$f"
    return 0
}
ws_config_aplatie() {
    local dir="${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" f
    ws_racine="$dir"
    if [[ -f "$dir/nginx.conf" ]]; then
        ws_lire_fichier "$dir/nginx.conf" 0
    else
        printf 'x:0\thttp {\n'
        for f in "$dir"/sites-enabled/* "$dir"/conf.d/*.conf; do ws_lire_fichier "$f" 0; done
        printf 'x:0\t}\n'
    fi
    return 0
}
ws_analyser() {   # $1 port HTTP d'Odoo, $2 port gevent : lignes (séparées par \037) « G|H », chemin, fichier:ligne, délai, fichier:ligne du délai, version HTTP, Upgrade, Connection, indentation, délai propre
    awk -F'\t' -v HTTP="$1" -v GEVENT="$2" -v q="'" '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    function unquote(s) { gsub("^[\"" q "]|[\"" q "]$", "", s); return s }
    function secondes(v,   n, u) {
        n = v + 0; u = v; gsub(/[0-9.]/, "", u)
        if (u == "m") return n * 60
        if (u == "h") return n * 3600
        if (u == "ms") return n / 1000
        if (u == "d") return n * 86400
        return n
    }
    function statement(s, c, tag,   w, nw, k, x, hu, hc, hv2, tov, ttag, tprop, trouve) {
        s = trim(s)
        if (c == ";") {
            if (s == "" || d < 1) return
            nw = split(s, w, /[ ]+/)
            if (w[1] == "proxy_pass") { pp[d] = w[2]; ppt[d] = tag; match(raw, /^[ ]*/); ind[d] = substr(raw, 1, RLENGTH) }
            else if (w[1] == "proxy_set_header") { ph[d]++; if (tolower(w[2]) == "upgrade") up[d] = 1; if (tolower(w[2]) == "connection") cn[d] = unquote(w[3]) }
            else if (w[1] == "proxy_read_timeout") { to[d] = secondes(unquote(w[2])); tt[d] = tag }
            else if (w[1] == "proxy_http_version") hv[d] = w[2]
            else if (w[1] == "set" && substr(w[2], 1, 1) == "$") sv[fid[d], w[2]] = unquote(w[3])
            else if (w[1] == "worker_connections") wc = w[2]
            else if (w[1] == "server" && typ[d] == "upstream" && !(upn[d] in ups)) { x = w[2]; sub(/.*:/, "", x); ups[upn[d]] = x }
            return
        }
        if (c == "{") {
            d++; fid[d] = ++fidn; typ[d] = "autre"; pp[d] = ""; ppt[d] = ""; ph[d] = 0; up[d] = 0; cn[d] = ""; to[d] = ""; tt[d] = ""; hv[d] = ""; ind[d] = ""; chemin[d] = ""
            nw = split(s, w, /[ ]+/)
            if (w[1] == "location") { typ[d] = "location"; chemin[d] = trim(substr(s, 9)) }
            else if (w[1] == "upstream") { typ[d] = "upstream"; upn[d] = w[2] }
            else if (w[1] == "server" || w[1] == "http") typ[d] = w[1]
            return
        }
        if (d < 1) return
        if (typ[d] == "location" && pp[d] != "") {
            t = pp[d]                                  # « proxy_pass http://$odoo_backend_chat; » : la variable vient d un « set » du serveur (ou du http)
            while (match(t, /\$[A-Za-z_0-9]+/)) {
                nom = substr(t, RSTART, RLENGTH); val = ""
                for (k = d; k >= 1; k--) if ((fid[k], nom) in sv) { val = sv[fid[k], nom]; break }
                if (val == "") break
                t = substr(t, 1, RSTART - 1) val substr(t, RSTART + RLENGTH)
            }
            n++; R_chemin[n] = chemin[d]; R_pp[n] = t; R_ppt[n] = ppt[d]; R_ind[n] = ind[d]
            hu = 0; hc = ""; hv2 = ""; tov = ""; ttag = ""; trouve = 0; tprop = 0
            for (k = d; k >= 1; k--) {              # les en-têtes ne sont hérités que si ce location (ou le niveau le plus proche) n en définit aucun
                if (!trouve && ph[k] > 0) { hu = up[k]; hc = cn[k]; trouve = 1 }
                if (hv2 == "" && hv[k] != "") hv2 = hv[k]
                if (tov == "" && to[k] != "") { tov = to[k]; ttag = tt[k]; tprop = (k == d) }
            }
            R_up[n] = hu; R_cn[n] = hc; R_hv[n] = (hv2 == "" ? "1.0" : hv2); R_to[n] = (tov == "" ? 60 : tov); R_tt[n] = ttag; R_tprop[n] = tprop
        }
        d--
    }
    {
        tag = $1; raw = $2; line = $2
        sub(/#.*/, "", line)
        if (trim(line) == "") next
        while (match(line, /[;{}]/)) {                 # RSTART est lu AVANT l appel : statement() utilise aussi match()
            pos = RSTART; c = substr(line, pos, 1); instr = substr(line, 1, pos - 1); line = substr(line, pos + 1)
            statement(instr, c, tag)
        }
    }
    END {
        for (i = 1; i <= n; i++) {
            t = R_pp[i]; sub(/^https?:\/\//, "", t); sub(/\/.*/, "", t); port = ""
            if (t ~ /^(127\.0\.0\.1|localhost|\[::1\]):[0-9]+$/) { port = t; sub(/.*:/, "", port) }
            else if (t in ups) port = ups[t]
            classe = (port == GEVENT) ? "G" : ((port == HTTP && R_chemin[i] ~ /websocket|longpolling/) ? "H" : "")
            if (classe == "" && t ~ /\$/ && R_chemin[i] ~ /websocket|longpolling/) classe = "U"        # variable que le script ne sait pas résoudre
            if (classe != "") printf "%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s\n", classe, R_chemin[i], R_ppt[i], (classe == "U" ? t : R_to[i]), R_tt[i], R_hv[i], R_up[i], R_cn[i], R_ind[i], R_tprop[i]
        }
        if (wc != "") printf "W\037%s\n", wc
    }'
}
ws_n=0; ws_http=0; ws_inconnu=0; ws_fixes=""; ws_sep=$'\037'; ws_fail0=$FAIL
if [[ -d "${NGINX_HARDENING_NGINX_DIR:-/etc/nginx}" ]]; then
    ws_donnees=$(ws_config_aplatie | ws_analyser "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT") || ws_donnees=""
    while IFS=$'\037' read -r ws_k ws_chem ws_tag ws_to ws_tt ws_hv ws_up ws_cn ws_ind ws_tprop; do
        case "$ws_k" in
            W)
                if [[ "$ws_chem" =~ ^[0-9]+$ ]] && (( ws_chem < 1024 )); then
                    warn "nginx : worker_connections = $ws_chem — chaque websocket occupe 2 connexions (le navigateur et Odoo) ; avec une centaine de personnes connectées à la discussion (souvent 2 appareils chacune), prévoir au moins 2048."
                fi
                ;;
            U)
                ws_inconnu=$((ws_inconnu + 1))
                echo "  [--]   nginx : le location « $ws_chem » ($ws_tag) envoie vers une variable que ce script ne sait pas résoudre ($ws_to) — vérification de ce websocket ignorée."
                ;;
            H)
                ws_http=$((ws_http + 1))
                fail "nginx : le location « $ws_chem » ($ws_tag) vise le port HTTP d'Odoo ($ODOO_HTTP_PORT) au lieu du port gevent ($ODOO_GEVENT_PORT) — les messages de la discussion n'arrivent pas en temps réel (Odoo avec workers : seul le processus gevent sert le websocket)."
                ;;
            G)
                ws_n=$((ws_n + 1))
                ws_ok=1
                                if [[ "$ws_hv" != "1.1" ]]; then
                    ws_ok=0
                    if [[ "$CHECK_ONLY" == "1" ]]; then
                        fail "nginx : le location « $ws_chem » ($ws_tag) n'a pas « proxy_http_version 1.1; » (défaut de nginx : 1.0) — les websockets échouent et les messages n'arrivent plus en direct. Relancer avec --update pour l'ajouter."
                    else
                        ws_fixes+="V${ws_sep}${ws_tag}${ws_sep}${ws_chem}${ws_sep}${ws_ind}${ws_sep}${ws_tt}${ws_sep}${ws_to}${ws_sep}${ws_tprop}"$'\n'
                    fi
                fi
                if [[ "$ws_up" != "1" ]]; then
                    ws_ok=0
                    fail "nginx : le location « $ws_chem » ($ws_tag) n'envoie pas « proxy_set_header Upgrade \$http_upgrade; » — le websocket ne s'établit pas. À ajouter à la main (voir le modèle ci-dessous : ajouter une directive proxy_set_header à un location retire celles du niveau supérieur)."
                fi
                if [[ "${ws_cn,,}" != "upgrade" && "$ws_cn" != "\$connection_upgrade" ]]; then
                    ws_ok=0
                    fail "nginx : le location « $ws_chem » ($ws_tag) n'envoie pas « proxy_set_header Connection \"upgrade\"; » (ni \$connection_upgrade) — le websocket ne s'établit pas. À ajouter à la main (voir le modèle ci-dessous)."
                fi
                if (( ${ws_to%.*} < WS_DELAI_MIN )); then
                    ws_ok=0
                    if [[ "$CHECK_ONLY" == "1" ]]; then
                        warn "nginx : le location « $ws_chem » ($ws_tag) coupe un websocket muet après ${ws_to%.*} s (proxy_read_timeout, défaut 60 s) ; Odoo envoie un ping toutes les 40 à 55 s : marge trop mince, les coupures répétées retardent les messages. Relancer avec --update pour passer à ${WS_DELAI_REGLE} s."
                    else
                        ws_fixes+="T${ws_sep}${ws_tag}${ws_sep}${ws_chem}${ws_sep}${ws_ind}${ws_sep}${ws_tt}${ws_sep}${ws_to}${ws_sep}${ws_tprop}"$'\n'
                    fi
                fi
                (( ws_ok == 1 )) && pass "nginx : le location « $ws_chem » ($ws_tag) vise le port gevent $ODOO_GEVENT_PORT, HTTP 1.1, en-têtes Upgrade et Connection, délai de lecture ${ws_to%.*} s — websocket (discussions en temps réel) bien configuré."
                ;;
        esac
    done <<< "$ws_donnees"
    # Corrections de --update (sans effet sur l'héritage des en-têtes) : proxy_http_version 1.1 et proxy_read_timeout
    if [[ -n "$ws_fixes" ]]; then
        ws_sauv="${NGINX_HARDENING_BACKUP_DIR:-/var/backups/nginx-hardening}"
        mkdir -p "$ws_sauv" 2>/dev/null || true
        while IFS=$'\037' read -r ws_type ws_tag ws_chem ws_ind ws_tt ws_to ws_tprop; do
            [[ -n "$ws_type" ]] || continue
            ws_fic="${ws_tag%:*}"; ws_lig="${ws_tag##*:}"
            ws_reel=$(readlink -f "$ws_fic" 2>/dev/null) || ws_reel="$ws_fic"
            ws_copie="$ws_sauv/$(basename "$ws_reel").$(date +%Y%m%d-%H%M%S).bak"
            cp -p "$ws_reel" "$ws_copie" 2>/dev/null || { fail "nginx : copie de sauvegarde de $ws_reel impossible — fichier non modifié."; continue; }
            if [[ "$ws_type" == "V" ]]; then
                sed -i "${ws_lig}a\\
${ws_ind}proxy_http_version 1.1;" "$ws_reel"
                ws_quoi="« proxy_http_version 1.1; » ajouté"
            elif [[ "$ws_tprop" == "1" && -n "$ws_tt" && "${ws_tt%:*}" == "$ws_fic" ]]; then
                ws_lt="${ws_tt##*:}"
                sed -i -E "${ws_lt}s/(proxy_read_timeout[[:space:]]+)[^;]+;/\1${WS_DELAI_REGLE}s;/" "$ws_reel"
                ws_quoi="proxy_read_timeout modifié : ${ws_to%.*} s → ${WS_DELAI_REGLE} s"
            else
                sed -i "${ws_lig}a\\
${ws_ind}proxy_read_timeout ${WS_DELAI_REGLE}s;" "$ws_reel"
                ws_quoi="« proxy_read_timeout ${WS_DELAI_REGLE}s; » ajouté (défaut : 60 s)"
            fi
            if run nginx -t >/dev/null 2>&1; then
                run systemctl reload nginx >/dev/null 2>&1 || true
                pass "nginx : location « $ws_chem » ($ws_fic) : $ws_quoi ; nginx -t réussi, nginx rechargé. Sauvegarde : $ws_copie"
            else
                cp -p "$ws_copie" "$ws_reel" 2>/dev/null || true
                fail "nginx : la modification du location « $ws_chem » ($ws_fic) est refusée par nginx -t — ancienne version restaurée, nginx NON rechargé."
            fi
        done < <(printf '%s' "$ws_fixes" | tac)
    fi
    if (( ws_n == 0 && ws_http == 0 && ws_inconnu == 0 )); then
        if (( amonts_n > 0 )); then
            fail "nginx : aucun location vers le port gevent d'Odoo ($ODOO_GEVENT_PORT) — le websocket (discussions en temps réel) ne peut pas fonctionner."
        else
            echo "  [--]   nginx : aucun location /websocket vers Odoo trouvé (vérification du websocket ignorée)."
        fi
    fi
    if (( FAIL > ws_fail0 )) 2>/dev/null; then
        cat <<EOM
  Modèle de location pour le websocket d'Odoo (à placer AVANT « location / ») :
        location /websocket {
            proxy_pass http://127.0.0.1:$ODOO_GEVENT_PORT;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host \$host;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_read_timeout ${WS_DELAI_REGLE}s;
        }
EOM
    fi
fi
echo

# --- 5) Pare-feu : bloquer l'accès externe direct aux ports Odoo -------------------------------------------------
# Défense en profondeur : même si Odoo est corrigé pour n'écouter qu'en local (etape 4), un pare-feu explicite
# protège aussi si ce réglage est un jour accidentellement changé. Détecte ufw en priorité (plus lisible/portable
# sur Debian), sinon retombe sur iptables direct.
else
    sans_objet "ports du serveur d'application Odoo"
fi
echo "--- 5) Pare-feu (ports $ODOO_HTTP_PORT et $ODOO_GEVENT_PORT bloqués depuis l'extérieur) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if command -v ufw >/dev/null 2>&1; then
    for port in "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT"; do
        if run ufw status 2>/dev/null | grep_q -E "^${port}/tcp[[:space:]]+DENY"; then
            pass "ufw : règle DENY déjà présente pour le port $port/tcp."
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "ufw : aucune règle DENY pour le port $port/tcp (relancer avec --update pour l'ajouter)."
        else
            run ufw deny "$port"/tcp >/dev/null
            pass "ufw : règle DENY ajoutée pour le port $port/tcp."
        fi
    done
elif command -v iptables >/dev/null 2>&1; then
    for port in "$ODOO_HTTP_PORT" "$ODOO_GEVENT_PORT"; do
        if run iptables -C INPUT -p tcp --dport "$port" ! -s 127.0.0.1 -j DROP 2>/dev/null; then
            pass "iptables : règle DROP déjà présente pour le port $port/tcp (sauf depuis 127.0.0.1)."
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "iptables : aucune règle DROP pour le port $port/tcp (relancer avec --update pour l'ajouter)."
        else
            run iptables -I INPUT -p tcp --dport "$port" ! -s 127.0.0.1 -j DROP
            pass "iptables : règle DROP ajoutée pour le port $port/tcp (sauf depuis 127.0.0.1)."
            iptables_rendre_persistant
        fi
    done
    if ! command -v netfilter-persistent >/dev/null 2>&1; then          # règles déjà posées mais jamais enregistrées : perdues au prochain redémarrage
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "iptables : netfilter-persistent absent — les règles disparaîtront au redémarrage (relancer avec --update pour installer iptables-persistent)."
        else
            iptables_rendre_persistant
        fi
    fi
else
    warn "Ni ufw ni iptables trouvés — impossible de vérifier/ajouter les règles de pare-feu automatiquement."
fi
echo

# --- Résolution du service Odoo (étapes 6-8) : même logique d'auto-détection que app-log-check.py ----------------
odoo_service="$ODOO_SERVICE"
if [[ -z "$odoo_service" ]]; then
    for candidate in $ODOO_CONF_UNITES erplibre.service erplibre_erplibre.service; do
        if run systemctl list-unit-files "$candidate" --no-legend 2>/dev/null | grep_q "$candidate"; then
            odoo_service="$candidate"
            break
        fi
    done
fi

# --- Résolution de odoo.conf : faite plus haut (--odoo-conf, sinon premier candidat de --odoo-conf-paths). Repli d'affichage seulement.
if [[ -z "$ODOO_CONF" ]]; then
    ODOO_CONF="/etc/odoo/odoo.conf"  # repli pour affichage, meme si rien n'a ete trouve
fi

# --- Résolution du script de démarrage réel (run.sh) via l'unité systemd — utilisée par les étapes 6 ET 7.
# "systemctl cat" fusionne les eventuels drop-ins (sinon un reglage ajoute via override serait invisible). Fait
# UNE SEULE FOIS ici : un flag --limit-memory-hard passe en ligne de commande dans run.sh a PRIORITE sur la
# valeur de odoo.conf (regle Odoo standard : CLI > fichier de config) — l'etape 6 doit le savoir pour ne pas
# signaler a tort une valeur de odoo.conf qu'Odoo n'utilise jamais reellement en pratique.
run_script=""
run_script_prod_lines=""
run_direct=0
if [[ -n "$odoo_service" ]]; then
    unit_content=$(run systemctl cat "$odoo_service" 2>/dev/null) || true
    if [[ -n "$unit_content" ]]; then
        exec_start=$(printf '%s' "$unit_content" | grep -E "^ExecStart=" | tail -1 | sed -E 's/^ExecStart=//') || true
        run_script=$(printf '%s' "$exec_start" | awk '{print $1}') || true
        if [[ -n "$run_script" && -r "$run_script" ]] && ! grep -Iq . "$run_script" 2>/dev/null; then
            # ExecStart lance directement un programme (python du venv…) et non un script run.sh : les options d'Odoo sont sur la ligne ExecStart elle-même
            run_direct=1
            run_script_prod_lines="$exec_start"
        elif [[ -n "$run_script" && -r "$run_script" ]]; then
            # Exclut la ligne du mode test (--log-level=test, branche ODOO_MODE_TEST) ET les lignes commentees
            # (ex. une ancienne invocation "python3 ./odoo/odoo-bin ..." laissee en commentaire pour reference,
            # avec ses propres valeurs --limit-memory-*, parfois tres differentes de celles reellement actives) de
            # TOUTES les verifications basees sur run.sh. Sans l'exclusion des commentaires, "tail -1" sur un grep
            # multi-lignes prend le DERNIER "--limit-memory-hard=" trouve dans le fichier, meme s'il est mort dans
            # un commentaire plus bas que la vraie ligne de production — bug reel observe : une ligne commentee
            # contenant --limit-memory-hard=10737418240 (10240 Mo) etait prise pour la valeur active, faussant
            # entierement le diagnostic de l'etape 6 malgre une vraie ligne de production correcte juste au-dessus.
            run_script_prod_lines=$(grep -v -- "--log-level=test" "$run_script" | grep -vE '^\s*#') || true
        fi
    fi
fi

# --- 6) Calcul suggéré des limites mémoire Odoo (workers x RAM réellement disponible) -----------------------------
# Jamais applique automatiquement (odoo.conf ou run.sh ne sont jamais modifies) — affiche juste le calcul et une
# comparaison avec la valeur actuelle si elle est trouvable, pour eviter de deviner un chiffre a l'aveugle (voir
# l'incident evite : un chiffre choisi sans connaitre le nombre de workers reel aurait pu causer un OOM en PROD).
else
    sans_objet "ports du serveur d'application Odoo (pare-feu de BBB : ufw, géré par son installateur)"
fi
U_MEM="Mo"; [[ "${NGINX_TOOLS_I18N_LANGUE:-fr}" != "fr" ]] && U_MEM="MB"       # unité de mémoire affichée (Mo en français)
echo "--- 6) Suggestion de limites mémoire Odoo (workers × RAM disponible) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if [[ -z "$odoo_service" ]]; then
    warn "Aucun service Odoo connu trouvé (db_user de la configuration, erplibre.service / erplibre_erplibre.service) — précisez --odoo-service NOM pour activer ce calcul."
else
    workers="$ODOO_WORKERS_OVERRIDE"
    if [[ -z "$workers" && -r "$ODOO_CONF" ]]; then
        workers=$(grep -E "^\s*workers\s*=" "$ODOO_CONF" 2>/dev/null | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]') || true
    fi
    if [[ -z "$workers" ]]; then
        cores=$(nproc 2>/dev/null) || cores=0
        if [[ "$cores" -gt 0 ]]; then
            workers=$(( cores * 2 + 1 ))
            warn "Nombre de workers introuvable dans $ODOO_CONF — utilise la formule officielle Odoo ((cœurs × 2) + 1 = $workers) à titre indicatif. Précisez --workers N pour une valeur exacte si elle est définie ailleurs (ex. run.sh)."
        fi
    fi

    total_ram_kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null) || true
    total_ram_mb=$(( ${total_ram_kb:-0} / 1024 ))

    if [[ -z "$workers" || "$workers" -eq 0 || "$total_ram_mb" -eq 0 ]]; then
        warn "Données insuffisantes (workers ou RAM totale introuvable) — calcul impossible."
    else
        used_mb=$(run free -m 2>/dev/null | awk '/^Mem:/{print $3}') || used_mb=0
        odoo_used_mb=0
        mem_current=$(run systemctl show "$odoo_service" -p MemoryCurrent --value 2>/dev/null) || true
        if [[ "$mem_current" =~ ^[0-9]+$ ]]; then
            odoo_used_mb=$(( mem_current / 1024 / 1024 ))
        fi
        non_odoo_mb=$(( used_mb - odoo_used_mb ))
        (( non_odoo_mb < 0 )) && non_odoo_mb=0
        safety_margin_mb=512
        available_for_odoo_mb=$(( total_ram_mb - non_odoo_mb - safety_margin_mb ))
        (( available_for_odoo_mb < 0 )) && available_for_odoo_mb=0
        safe_hard_mb=$(( available_for_odoo_mb / workers ))
        safe_soft_mb=$(( safe_hard_mb * 85 / 100 ))

        echo "  Service Odoo               : $odoo_service"
        echo "  Workers                     : $workers"
        echo "  RAM totale                  : ${total_ram_mb} $U_MEM"
        echo "  Utilisé hors Odoo (estimé)  : ${non_odoo_mb} $U_MEM (PostgreSQL, OS, nginx, etc. — via free -m moins"
        echo "                                l'usage actuel du cgroup d'Odoo, MemoryCurrent)"
        echo "  Disponible pour Odoo        : ${available_for_odoo_mb} $U_MEM"
        echo
        echo "  Suggestion (par worker — à valider par un test réel en DEV avant PROD) :"
        printf "    --limit-memory-soft=%d   (%d $U_MEM)\n" $(( safe_soft_mb * 1024 * 1024 )) "$safe_soft_mb"
        printf "    --limit-memory-hard=%d   (%d $U_MEM)\n" $(( safe_hard_mb * 1024 * 1024 )) "$safe_hard_mb"
        echo "  Pire cas (tous les workers à la limite dure en même temps) : $(( safe_hard_mb * workers )) $U_MEM"

        if [[ -r "$ODOO_CONF" ]] || [[ -n "$run_script_prod_lines" ]]; then
            # Priorite : un --limit-memory-hard=N en ligne de commande dans run.sh (branche production) l'emporte
            # TOUJOURS sur la valeur de odoo.conf, cote Odoo — donc on le cherche d'abord ici.
            current_hard=""
            current_hard_source=""
            if [[ -n "$run_script_prod_lines" ]]; then
                current_hard=$(printf '%s' "$run_script_prod_lines" | grep -oE -- '--limit-memory-hard=[0-9]+' | tail -1 | sed -E 's/.*=//') || true
                [[ -n "$current_hard" ]] && current_hard_source="$run_script (ligne de commande, priorité sur odoo.conf)"
            fi
            if [[ -z "$current_hard" && -r "$ODOO_CONF" ]]; then
                current_hard=$(grep -E "^\s*limit_memory_hard\s*=" "$ODOO_CONF" 2>/dev/null | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]') || true
                [[ -n "$current_hard" ]] && current_hard_source="$ODOO_CONF"
            fi
            if [[ "$current_hard" =~ ^[0-9]+$ ]]; then
                current_hard_mb=$(( current_hard / 1024 / 1024 ))
                worst_case_current_mb=$(( current_hard_mb * workers ))
                if (( current_hard == 0 )); then
                    fail "limit_memory_hard actuel = 0 (illimité) — source : $current_hard_source — aucune protection contre l'épuisement mémoire."
                elif (( worst_case_current_mb > total_ram_mb )); then
                    fail "limit_memory_hard actuel (${current_hard_mb} $U_MEM, source : $current_hard_source) × $workers workers = ${worst_case_current_mb} $U_MEM > RAM totale (${total_ram_mb} $U_MEM) — risque réel d'épuisement mémoire si plusieurs workers culminent en même temps."
                else
                    pass "limit_memory_hard actuel (${current_hard_mb} $U_MEM, source : $current_hard_source) cohérent avec la RAM disponible."
                fi
            else
                echo "  (limit_memory_hard non trouvé dans $ODOO_CONF ni dans la ligne de production de run.sh)"
            fi
        fi
    fi
fi
echo

# --- 7) Audit du service Odoo (unité systemd + script de démarrage) — diagnostic seulement, jamais d'édition -----
else
    sans_objet "limites mémoire des workers Odoo"
fi
echo "--- 7) Audit du service Odoo (unité systemd + run.sh) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if [[ -z "$odoo_service" ]]; then
    warn "Service Odoo non déterminé — audit ignoré (voir étape 6)."
elif [[ -z "$unit_content" ]]; then
    warn "Impossible de lire l'unité $odoo_service (systemctl cat)."
else
    if printf '%s' "$unit_content" | grep_q "^Wants=.*network-online.target"; then
        pass "Wants=network-online.target présent."
    else
        warn "Wants=network-online.target absent — After= seul ne garantit pas que le réseau soit prêt avant le démarrage d'Odoo."
    fi

    if printf '%s' "$unit_content" | grep_q -E "^StartLimitIntervalSec=|^StartLimitBurst="; then
        pass "Limite anti-boucle-de-redémarrage (StartLimitIntervalSec/Burst) configurée."
    else
        warn "Aucune limite anti-boucle-de-redémarrage — Restart=always peut retenter indéfiniment si le service plante en boucle, sans jamais passer en état 'failed' pour alerter."
    fi

    if printf '%s' "$unit_content" | grep_q "^NoNewPrivileges=true"; then
        pass "NoNewPrivileges=true présent."
    else
        warn "NoNewPrivileges=true absent — durcissement simple et sans risque connu à ajouter."
    fi

    if printf '%s' "$unit_content" | grep_q "^PIDFile=" && printf '%s' "$unit_content" | grep_q "^Type=simple"; then
        warn "PIDFile= présent avec Type=simple — sans effet réel (PIDFile n'est utile qu'avec Type=forking), nettoyage possible."
    fi

    # run_script / run_script_prod_lines deja resolus plus haut (partages avec l'etape 6), l'exclusion de
    # --log-level=test y est deja appliquee.
    if [[ "$run_direct" == "1" ]]; then
        pass "ExecStart lance directement $run_script (pas de script run.sh) : les options d'Odoo sont lues sur cette ligne de commande."
        if printf '%s' "$run_script_prod_lines" | grep_q -E -- "--limit-memory-hard=0\b"; then
            fail "ExecStart contient --limit-memory-hard=0 (illimité) — voir l'étape 6 pour une valeur suggérée."
        fi
    elif [[ -n "$run_script" && -n "$run_script_prod_lines" ]]; then
        if printf '%s' "$run_script_prod_lines" | grep_q -E "^\s*exec\s+.*odoo_bin\.sh"; then
            pass "$run_script utilise 'exec' avant de lancer odoo_bin.sh — suivi de PID le plus propre possible."
        else
            warn "$run_script n'utilise pas 'exec' avant odoo_bin.sh — sans danger avec KillMode=control-group (le défaut, qui envoie SIGTERM à tout le groupe de processus), mais 'exec' reste plus propre."
        fi

        if printf '%s' "$run_script_prod_lines" | grep_q 'ORIGIN_CONFIG_PATH=CONFIG_PATH'; then
            warn "$run_script contient 'ORIGIN_CONFIG_PATH=CONFIG_PATH' (sans \$) — coquille cosmétique, le message d'erreur affichera le mauvais texte si la config est introuvable."
        fi

        if printf '%s' "$run_script_prod_lines" | grep_q -E -- "--limit-memory-hard=0\b"; then
            fail "$run_script contient encore --limit-memory-hard=0 (illimité) sur la ligne de production — voir l'étape 6 pour une valeur suggérée."
        fi
    else
        warn "Impossible de lire le script de démarrage réel (${run_script:-introuvable}) pour vérifier exec/coquilles connues."
    fi
fi
echo

# --- 8) Audit odoo.conf (points de sécurité additionnels, hors gestion des ports déjà couverte) -------------------
else
    sans_objet "unité systemd et run.sh d'Odoo"
fi
echo "--- 8) Audit odoo.conf ($ODOO_CONF) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
if [[ ! -r "$ODOO_CONF" ]]; then
    warn "$ODOO_CONF introuvable ou illisible — précisez --odoo-conf CHEMIN si ce n'est pas le bon fichier."
else
    proxy_mode=$(grep -E "^\s*proxy_mode\s*=" "$ODOO_CONF" | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]') || true
    if [[ "$proxy_mode" == "true" || "$proxy_mode" == "1" ]]; then
        pass "proxy_mode activé — Odoo fait confiance aux en-têtes X-Forwarded-* de nginx (IP client réelle, HTTPS détecté correctement)."
    else
        fail "proxy_mode absent ou non activé dans $ODOO_CONF — derrière nginx, Odoo verrait 127.0.0.1 comme IP de TOUTES les requêtes dans ses propres journaux, et pourrait mal détecter HTTPS."
    fi

    list_db=$(grep -E "^\s*list_db\s*=" "$ODOO_CONF" | tail -1 | sed -E 's/^[^=]*=\s*//' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]') || true
    # Ce que la regle nginx reserve aux IP autorisees (location allow/deny des env-*.conf) : depuis la config livree
    # le 2026-09-25, TOUTES les routes /web/database/* ; avant, seulement manager et selector (+ /xmlrpc/(2/)db).
    # /jsonrpc (service « db », methode « list ») reste hors de portee de nginx dans tous les cas : c'est le point
    # d'entree general de l'API, impossible a filtrer sans casser les integrations — seul list_db = False le ferme.
    db_rule_all=0
    if command -v nginx >/dev/null 2>&1 && run nginx -T 2>/dev/null | grep_q -F 'web/database/.*|xmlrpc'; then
        db_rule_all=1
    fi
    if [[ "$list_db" == "false" || "$list_db" == "0" ]]; then
        pass "list_db désactivé — la liste des bases n'est renvoyée par AUCUNE route, pas même /jsonrpc (service « db », méthode « list »), que nginx ne peut pas filtrer. (Effet voulu : le gestionnaire de bases d'Odoo est aussi désactivé, y compris pour les IP autorisées.)"
    else
        warn "list_db absent ou actif dans $ODOO_CONF (actif par défaut dans Odoo) : la liste des bases peut être demandée."
        if [[ "$db_rule_all" == "1" ]]; then
            echo "         Réservées par nginx aux IP autorisées (allow) : toutes les routes /web/database/* (manager, selector, list,"
            echo "         backup, drop, restore, duplicate, create, change_password), /xmlrpc/db et /xmlrpc/2/db."
        else
            echo "         Réservées par nginx aux IP autorisées (allow) : /web/database/manager, /web/database/selector, /xmlrpc/db"
            echo "         et /xmlrpc/2/db SEULEMENT. /web/database/list (liste des bases en JSON) reste joignable par TOUS :"
            echo "         déployez la dernière config nginx (règle des env-*.conf étendue à toutes les routes /web/database/*)."
        fi
        echo "         Joignable par TOUS malgré nginx : /jsonrpc (service « db », méthode « list ») — point d'entrée général de"
        echo "         l'API, impossible à filtrer sans casser les intégrations ; seul list_db = False le ferme."
        echo "         Quoi faire : en PROD, list_db = False dans $ODOO_CONF puis redémarrer Odoo (le gestionnaire de bases est"
        echo "         alors désactivé pour tous : le réactiver le temps d'une opération). Sur une DEV entièrement restreinte par"
        echo "         IP (deny all dans env-dev.conf), acceptable tel quel : aucune de ces routes n'y est joignable d'Internet."
    fi

    admin_passwd=$(grep -E "^\s*admin_passwd\s*=" "$ODOO_CONF" | tail -1 | sed -E 's/^[^=]*=\s*//') || true
    if [[ -z "$admin_passwd" ]]; then
        warn "admin_passwd vide ou absent dans $ODOO_CONF — vérifiez manuellement (jamais affiché ici par précaution)."
    elif [[ "$admin_passwd" == "admin" || "$admin_passwd" == "password" || ${#admin_passwd} -lt 8 ]]; then
        fail "admin_passwd semble faible (valeur courante ou trop courte) — protège /web/database/manager, même restreint par IP. À vérifier manuellement."
    else
        pass "admin_passwd défini et de longueur raisonnable (valeur elle-même jamais affichée)."
    fi
fi
echo


# --- 9) Jails fail2ban : capteur catch-all (nginx) et échecs de connexion Odoo (journal d'Odoo) --------------------
# nginx-catchall : le capteur catch-all (odoo-catchall-444.log) est invisible des jails existants (leur glob
# « *access*.log » ne le trouve jamais). odoo-auth : un mauvais mot de passe repond 200, donc invisible pour tout jail
# nginx — seul le journal d'Odoo (« Login failed … from IP ») permet de detecter la force brute. Fichiers NEUFS et
# autonomes sous filter.d/ et jail.d/, jamais de modification de jail.local. Sources cherchees dans /etc/nginx/fail2ban
# (deploiement documente dans le README) puis a cote de ce script.
else
    sans_objet "odoo.conf"
fi
echo "--- 9) Jails fail2ban (capteur catch-all, échecs de connexion Odoo) ---"
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" ]]; then
F2B_SRC_DIR=""
for f2b_cand in /etc/nginx/fail2ban "$SCRIPT_DIR/fail2ban"; do
    if [[ -r "$f2b_cand/nginx-catchall.filter.conf" ]]; then F2B_SRC_DIR="$f2b_cand"; break; fi
done
F2B_INSTALLED_JAILS=()
if ! command -v fail2ban-client >/dev/null 2>&1; then
    warn "fail2ban-client introuvable — fail2ban n'est peut-être pas installé, étape ignorée."
else
    # --- 9a) jails aux fichiers copiés tels quels : nginx-catchall (capteur catch-all), nginx-blocked-probes (refus
    # des règles de sécurité, journal dédié blocked-probes.log) ---
    installer_jail_copie() {
        local nom="$1" pourquoi="$2" filtre="/etc/fail2ban/filter.d/$1.conf" jail="/etc/fail2ban/jail.d/$1.conf"
        if [[ -f "$filtre" && -f "$jail" ]]; then
            pass "Jail $nom : fichiers présents ($jail)."
            F2B_INSTALLED_JAILS+=("$nom")
        elif [[ "$CHECK_ONLY" == "1" ]]; then
            fail "Jail $nom absent — $pourquoi (relancer avec --update pour l'installer)."
        elif [[ -z "$F2B_SRC_DIR" || ! -r "$F2B_SRC_DIR/$nom.jail.conf" ]]; then
            warn "Fichiers source de $nom introuvables (cherché dans /etc/nginx/fail2ban/ et $SCRIPT_DIR/fail2ban/) — copiez le dossier fail2ban/ du zip vers /etc/nginx/fail2ban/."
        else
            mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d 2>/dev/null || true
            if run cp "$F2B_SRC_DIR/$nom.filter.conf" "$filtre" 2>/dev/null && run cp "$F2B_SRC_DIR/$nom.jail.conf" "$jail" 2>/dev/null; then
                pass "Jail $nom installé ($jail, depuis $F2B_SRC_DIR)."
                NEED_FAIL2BAN_RESTART=1
                F2B_INSTALLED_JAILS+=("$nom")
            else
                warn "Impossible de copier les fichiers du jail $nom (permissions ?) — à faire manuellement."
            fi
        fi
    }
    installer_jail_copie nginx-catchall "le capteur catch-all reste invisible de fail2ban"
    installer_jail_copie nginx-blocked-probes "les refus des règles de sécurité (blocked-probes.log) ne sont jamais sanctionnés"
    # Le journal doit exister pour que fail2ban charge la jail (nginx le crée à la première requête refusée).
    if [[ "$CHECK_ONLY" != "1" && ! -e /var/log/nginx/blocked-probes.log ]] && [[ " ${F2B_INSTALLED_JAILS[*]} " == *" nginx-blocked-probes "* ]]; then
        if touch /var/log/nginx/blocked-probes.log 2>/dev/null; then
            chown --reference=/var/log/nginx /var/log/nginx/blocked-probes.log 2>/dev/null || true
        fi
    fi

    # --- 9b) odoo-auth (jail GENERE pour ce serveur a partir du modele) ---
    AUTH_FILTER_DST="/etc/fail2ban/filter.d/odoo-auth.conf"
    AUTH_JAIL_DST="/etc/fail2ban/jail.d/odoo-auth.conf"
    if [[ -z "$odoo_service" && -z "$ODOO_LOGFILE" ]]; then
        warn "Jail odoo-auth : service Odoo non déterminé (voir étape 6) — impossible de générer le jail (--odoo-service NOM)."
    elif [[ -z "$F2B_SRC_DIR" || ! -r "$F2B_SRC_DIR/odoo-auth.filter.conf" || ! -r "$F2B_SRC_DIR/odoo-auth.jail.conf.template" ]]; then
        if [[ -f "$AUTH_JAIL_DST" ]]; then
            pass "Jail odoo-auth : fichiers présents ($AUTH_JAIL_DST) — modèle introuvable, contenu non revérifié."
            F2B_INSTALLED_JAILS+=(odoo-auth)
        else
            warn "Jail odoo-auth : modèle introuvable (odoo-auth.*.conf dans /etc/nginx/fail2ban/) — déployez le dossier fail2ban/ du zip."
        fi
    else
        # Journal d'Odoo : namespace eventuel (LogNamespace, cf. isolation du journal) — le backend systemd de fail2ban
        # ne lit que le journal par defaut, sauf si on lui donne le repertoire du namespace.
        auth_ns=$(run systemctl show -p LogNamespace --value "$odoo_service" 2>/dev/null) || auth_ns=""
        if [[ -n "$auth_ns" ]]; then
            auth_backend="systemd[journalpath=/var/log/journal/$(cat /etc/machine-id 2>/dev/null).$auth_ns]"
        else
            auth_backend="systemd"
        fi
        # IP a ne jamais bannir : boucle locale, adresses de ce serveur, et la liste blanche nginx (source unique des
        # IP de confiance — equipe) : une erreur de mot de passe d'un administrateur ne doit pas le couper du site.
        auth_ignore="127.0.0.1/8 ::1"
        for a in $(hostname -I 2>/dev/null) $(run nginx -T 2>/dev/null | grep -oE 'allow [0-9a-fA-F:./]+;' | awk '{print $2}' | tr -d ';' | sort -u); do
            case "$a" in 127.*|::1) continue ;; esac        # deja couvertes par 127.0.0.1/8 et ::1
            case " $auth_ignore " in *" $a "*) ;; *) auth_ignore="$auth_ignore $a" ;; esac
        done
        auth_generated=$(sed -e "s#@ODOO_UNIT@#$odoo_service#" -e "s#@BACKEND@#$auth_backend#" -e "s#@IGNOREIP@#$auth_ignore#" \
                              -e '/^# MODÈLE — ne pas copier tel quel/,/jail\.d\/odoo-auth\.conf\.$/c\# GÉNÉRÉ par nginx-hardening.sh --update pour ce serveur — ne pas éditer à la main (sera régénéré).' \
                              "$F2B_SRC_DIR/odoo-auth.jail.conf.template")
        if [[ -n "$ODOO_LOGFILE" ]]; then
            # Odoo écrit dans un FICHIER (logfile de sa configuration) : fail2ban le lit directement, pas le journal systemd.
            auth_generated=$(printf '%s\n' "$auth_generated" | sed -e "s#^backend .*#backend      = auto#" -e "s#^journalmatch .*#logpath      = $ODOO_LOGFILE\nlogtimezone  = UTC#")
            auth_backend="auto, logpath $ODOO_LOGFILE"
        fi
        auth_state="absent"
        if [[ -f "$AUTH_JAIL_DST" && -f "$AUTH_FILTER_DST" ]]; then
            if [[ "$(cat "$AUTH_JAIL_DST")" == "$auth_generated" ]] && cmp -s "$F2B_SRC_DIR/odoo-auth.filter.conf" "$AUTH_FILTER_DST"; then
                auth_state="à jour"
            else
                auth_state="différent"
            fi
        fi
        case "$auth_state" in
            "à jour")
                pass "Jail odoo-auth à jour (service $odoo_service, backend $auth_backend, $(wc -w <<< "$auth_ignore") IP jamais bannies)."
                F2B_INSTALLED_JAILS+=(odoo-auth) ;;
            *)
                if [[ "$CHECK_ONLY" == "1" ]]; then
                    if [[ "$auth_state" == "absent" ]]; then
                        fail "Jail odoo-auth absent — la force brute sur la page de connexion d'Odoo n'est détectée par rien (relancer avec --update)."
                    else
                        warn "Jail odoo-auth différent de ce qui serait généré aujourd'hui (service, liste blanche nginx ou filtre modifiés) — relancer avec --update pour le régénérer."
                        F2B_INSTALLED_JAILS+=(odoo-auth)
                    fi
                else
                    mkdir -p /etc/fail2ban/filter.d /etc/fail2ban/jail.d 2>/dev/null || true
                    migrer_chemin "$AUTH_JAIL_DST.avant-setup" "$AUTH_JAIL_DST.before-setup"
                    [[ -f "$AUTH_JAIL_DST" ]] && run cp -p "$AUTH_JAIL_DST" "$AUTH_JAIL_DST.before-setup" 2>/dev/null
                    if run cp "$F2B_SRC_DIR/odoo-auth.filter.conf" "$AUTH_FILTER_DST" 2>/dev/null && printf '%s\n' "$auth_generated" > "$AUTH_JAIL_DST"; then
                        if [[ "$auth_state" == "absent" ]]; then auth_verbe="installé"; else auth_verbe="régénéré"; fi
                        pass "Jail odoo-auth $auth_verbe (service $odoo_service, backend $auth_backend, IP jamais bannies : $auth_ignore)."
                        NEED_FAIL2BAN_RESTART=1
                        F2B_INSTALLED_JAILS+=(odoo-auth)
                    else
                        warn "Impossible d'écrire le jail odoo-auth (permissions ?)."
                    fi
                fi ;;
        esac
    fi

    # --- 9c) Jails reellement CHARGES par fail2ban (des fichiers presents ne suffisent pas : erreur de syntaxe,
    # fail2ban pas recharge depuis l'installation, journal introuvable...). Apres --update, verifie en fin de script,
    # une fois fail2ban recharge.
    verifier_ignoreip

    if [[ "$NEED_FAIL2BAN_RESTART" == "0" ]]; then
        for j in "${F2B_INSTALLED_JAILS[@]}"; do
            if run fail2ban-client status "$j" >/dev/null 2>&1; then
                pass "Jail $j chargé et actif dans fail2ban."
            else
                fail "Jail $j : fichiers présents mais jail NON chargé par fail2ban — voir « fail2ban-client reload » puis « journalctl -u fail2ban -n 30 » (erreur de syntaxe, journal introuvable ?)."
            fi
        done
    fi
fi
echo

# --- 10) HSTS reellement envoye par chaque nom public servi en HTTPS ------------------------------------------------
# Test EMPIRIQUE : pour chaque nom declare par une directive server_name dans la config active, une vraie requete
# HTTPS est faite en local (curl --resolve NOM:443:127.0.0.1, donc avec le bon SNI) et l'en-tete
# Strict-Transport-Security est cherche dans la reponse. Remplace l'analyse statique des versions 1.10 a 1.13, qui
# supposait a tort que "nginx -T" developpe les include() : il ne le fait PAS — il affiche chaque fichier
# separement, l'un apres l'autre. Un bloc server dont le server_name ou le HSTS vient d'un fichier inclus (cas de
# TOUS les vhosts de ce projet : snippets/odoo/*.name.conf et _odoo-common.conf) etait donc juge a tort sans nom
# ou sans HSTS. Le test empirique voit exactement ce qu'un navigateur recevrait, include() et heritage compris.
# Diagnostic seulement, jamais d'edition de la config.
else
    sans_objet "jails du capteur catch-all et des connexions Odoo (capteur : HAProxy aiguille le port 443 de BBB)"
    durcir_bbb
    # Adresses de l'équipe ignorées par fail2ban : vaut aussi pour BigBlueButton (jail sshd notamment).
    if command -v fail2ban-client >/dev/null 2>&1; then verifier_ignoreip; fi
fi
echo "--- 10) HSTS réellement envoyé par chaque nom servi en HTTPS ---"
if ! command -v nginx >/dev/null 2>&1; then
    warn "nginx introuvable — étape ignorée."
elif ! command -v curl >/dev/null 2>&1; then
    warn "curl introuvable — impossible de tester HSTS réellement (apt install curl)."
else
    nginx_dump=$(run nginx -T 2>/dev/null) || true
    # Noms declares dans TOUS les fichiers affiches par nginx -T (y compris les snippets inclus), hors commentaires,
    # hors "_" (capteur catch-all : ferme la connexion en 444 sans jamais servir de contenu, HSTS sans objet) et hors
    # noms generiques ou expressions regulieres (commencant par ~ ou contenant *), non testables tels quels.
    # Commentaire retire d'abord (tout ce qui suit un #), puis chaque occurrence de server_name est lue, meme sur une
    # ligne compacte du type "server { listen 80; server_name a b; }".
    hsts_names=$(printf '%s\n' "$nginx_dump" | awk '
        { line = $0; c = index(line, "#"); if (c > 0) line = substr(line, 1, c - 1)
          while ((p = index(line, "server_name")) > 0) {
              before = (p > 1) ? substr(line, p - 1, 1) : " "
              line = substr(line, p + 11)
              if (before !~ /[[:space:];{]/ || line !~ /^[[:space:]]/) continue
              e = index(line, ";"); part = (e > 0) ? substr(line, 1, e - 1) : line
              n = split(part, names, /[[:space:]]+/)
              for (i = 1; i <= n; i++) if (names[i] != "" && names[i] != "_" && names[i] !~ /^~/ && names[i] !~ /\*/) print names[i]
          } }' | sort -u) || true
    if [[ -z "$hsts_names" ]]; then
        warn "Aucun server_name testable trouvé dans \"nginx -T\" — nginx est-il installé et configuré ?"
    else
        browser_ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        while IFS= read -r hname; do
            [[ -z "$hname" ]] && continue
            hdrs=$(run curl -sk -o /dev/null -D - --max-time 8 -A "$browser_ua" \
                   --resolve "$hname:443:127.0.0.1" "https://$hname/" 2>/dev/null) || hdrs=""
            if [[ -z "$hdrs" ]]; then
                # Pas de reponse HTTPS pour ce nom : typiquement un nom declare uniquement dans un bloc port 80, qui
                # retombe en HTTPS sur le capteur catch-all (connexion fermee sans reponse, 444). Pas un defaut HSTS.
                echo "  [INFO] $hname : aucune réponse HTTPS en local (nom servi seulement en HTTP, ou certificat/bloc 443 absent) — HSTS non applicable."
                continue
            fi
            hcode=$(printf '%s\n' "$hdrs" | awk 'NR==1{print $2}') || true
            hsts_val=$(printf '%s\n' "$hdrs" | tr -d '\r' | awk 'tolower($0) ~ /^strict-transport-security:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }') || true
            if [[ -n "$hsts_val" ]]; then
                max_age=$(printf '%s' "$hsts_val" | grep -oE 'max-age=[0-9]+' | cut -d= -f2) || true
                if [[ -n "$max_age" ]] && (( max_age < 86400 )); then
                    pass "HSTS présent — $hname (HTTP $hcode, max-age=${max_age}s : encore court — normal après un déploiement initial, à remonter à 31536000 après quelques jours sans problème)"
                else
                    pass "HSTS présent — $hname (HTTP $hcode, ${hsts_val})"
                fi
            else
                # Redirection vers le MÊME nom (ex. « / » → « /b » de BBB) : la page d'arrivée est vérifiée aussi. Si elle
                # porte HSTS, le navigateur l'enregistre : avertissement (en-tête à ajouter aussi aux redirections).
                hsts_arrivee=""; chemin_arrivee=""
                if [[ "$hcode" =~ ^30[1278]$ ]]; then
                    loc=$(printf '%s\n' "$hdrs" | tr -d '\r' | awk 'tolower($0) ~ /^location:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }') || loc=""
                    case "$loc" in
                        /*) chemin_arrivee="$loc" ;;
                        "https://$hname"|"https://$hname/"*) chemin_arrivee="/${loc#https://"$hname"/}" ;;
                    esac
                    if [[ -n "$chemin_arrivee" ]]; then
                        hsts_arrivee=$(run curl -sk -o /dev/null -D - --max-time 8 -A "$browser_ua" --resolve "$hname:443:127.0.0.1" \
                            "https://$hname$chemin_arrivee" 2>/dev/null | tr -d '\r' \
                            | awk 'tolower($0) ~ /^strict-transport-security:/ { sub(/^[^:]*:[[:space:]]*/, ""); print; exit }') || hsts_arrivee=""
                    fi
                fi
                if [[ -n "$hsts_arrivee" ]]; then
                    # HSTS est enregistré par le navigateur sur la réponse HTTPS finale : une redirection qui n'en porte pas
                    # (BBB : « / » → Greenlight) est sans conséquence dès que la page d'arrivée l'envoie. Conforme.
                    pass "HSTS présent — $hname (la redirection HTTP $hcode n'en porte pas, mais la page d'arrivée $chemin_arrivee l'envoie : $hsts_arrivee ; le navigateur l'enregistre)"
                else
                    if [[ "${TLS_TERMINATION:-nginx}" == "haproxy" ]]; then
                        conseil="dans /etc/haproxy/haproxy.cfg, section « frontend » du 443, ajoutez « http-after-response set-header Strict-Transport-Security \"max-age=300; includeSubDomains\" » (HAProxy 2.2 et suivants ; contrairement à http-response, s'applique AUSSI aux redirections produites par HAProxy), puis haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy ; max-age à remonter à 31536000 après quelques jours sans problème. Attention : bbb-install peut régénérer ce fichier lors d'une mise à jour."
                    else
                        conseil="dans le fichier sites-available/ du bloc server 443 qui sert ce nom, ajoutez « include /etc/nginx/snippets/odoo/hsts.conf; » au niveau server (un bloc de redirection), ou vérifiez qu'il inclut bien _odoo-common.conf (un bloc qui sert Odoo) ; add_header … always pour qu'il s'applique aussi aux redirections et erreurs ; puis nginx -t && systemctl reload nginx. Pour trouver le fichier : grep -rln \"$hname\" /etc/nginx/"
                    fi
                    # (complément construit à part : une apostrophe dans « ${x:+…} » entre guillemets casse l'analyse de bash)
                    precision=""; if [[ -n "$chemin_arrivee" ]]; then precision=", et sur la page d'arrivée $chemin_arrivee"; fi
                    fail "HSTS ABSENT — $hname (HTTP $hcode$precision). Quoi faire : $conseil"
                fi
            fi
        done <<< "$hsts_names"
    fi
fi
echo

if ! [[ "$LOG_RETENTION_MONTHS" =~ ^[0-9]+$ ]] || (( LOG_RETENTION_MONTHS < 1 || LOG_RETENTION_MONTHS > 24 )); then
    echo "ERREUR: --log-retention-months attend un nombre de mois entre 1 et 24 (reçu : $LOG_RETENTION_MONTHS)." >&2
    exit 1
fi
echo "--- 11) Rétention des journaux (cible : $LOG_RETENTION_MONTHS mois) ---"
# Rotation de nginx et de fail2ban (/etc/logrotate.d/) et duree de conservation du journal systemd. Debian garde par
# defaut 14 jours de journaux nginx (rotation quotidienne, « rotate 14 ») : insuffisant pour les bilans sur 30 jours
# et plus (web-monitor.py --summary). --update ajuste « rotate » selon la frequence (quotidienne : 92, hebdomadaire :
# 14, mensuelle : 4), apres une copie de sauvegarde (.before-nginx-hardening), valide la syntaxe (logrotate -d) et
# restaure la copie en cas d'erreur. Journal systemd : MaxRetentionSec=Nmonth (garde au plus N mois).
RETENTION_CIBLE=$(( (LOG_RETENTION_MONTHS * 61 + 1) / 2 ))   # mois de 30,5 jours : 3 → 92, 6 → 183, 12 → 366
LOGROTATE_DIR="${NGINX_HARDENING_LOGROTATE_DIR:-/etc/logrotate.d}"
for lr_nom in nginx fail2ban; do
    lr_f="$LOGROTATE_DIR/$lr_nom"
    if [[ ! -r "$lr_f" ]]; then
        warn "$lr_f absent ou illisible — rotation de $lr_nom non vérifiable."
        continue
    fi
    lr_freq=$(grep -oE '^[[:space:]]*(daily|weekly|monthly)\b' "$lr_f" | head -1 | tr -d '[:space:]') || true
    [[ -z "$lr_freq" ]] && lr_freq="weekly"
    lr_n=$(grep -oE '^[[:space:]]*rotate[[:space:]]+[0-9]+' "$lr_f" | head -1 | awk '{print $2}') || true
    [[ -z "$lr_n" ]] && lr_n=4
    case "$lr_freq" in daily) lr_m=1; lr_fr="quotidienne" ;; weekly) lr_m=7; lr_fr="hebdomadaire" ;; *) lr_m=30; lr_fr="mensuelle" ;; esac
    lr_jours=$((lr_n * lr_m))
    # Rotation réellement effectuée ? Sous Ubuntu, /var/log appartient au groupe syslog, qui peut y écrire : logrotate
    # REFUSE alors de faire tourner les journaux de ce dossier sans directive « su » (« parent directory has insecure
    # permissions ») — le journal ne tournait donc pas du tout, quel que soit « rotate ».
    lr_err=""
    if command -v logrotate >/dev/null 2>&1; then
        lr_err=$(run logrotate -d "$lr_f" 2>&1 | grep -m1 -iE '^error:' || true)
    fi
    lr_su=0
    if [[ "$lr_err" == *"insecure permissions"* ]] && ! grep_q -E '^[[:space:]]*su[[:space:]]' "$lr_f"; then lr_su=1; fi
    if (( lr_jours >= RETENTION_CIBLE && lr_su == 0 )); then
        pass "$lr_nom : rotation $lr_fr, $lr_n conservés ≈ $lr_jours jours ($lr_f)"
        continue
    fi
    lr_cible=$(( (RETENTION_CIBLE + lr_m - 1) / lr_m ))
    (( lr_jours >= RETENTION_CIBLE )) && lr_cible=$lr_n
    if [[ "$CHECK_ONLY" == "1" ]]; then
        (( lr_su )) && warn "$lr_nom : NE TOURNE PAS — logrotate refuse ($lr_err) ; --update ajoutera la directive « su » à $lr_f."
        (( lr_jours < RETENTION_CIBLE )) && warn "$lr_nom : ≈ $lr_jours jours seulement (rotation $lr_fr, rotate $lr_n) — --update passera à « rotate $lr_cible » (≈ $LOG_RETENTION_MONTHS mois)."
        continue
    fi
    migrer_chemin "$lr_f.avant-nginx-hardening" "$lr_f.before-nginx-hardening"      # nom anglais (2.1)
    [[ -e "$lr_f.before-nginx-hardening" ]] || cp -p "$lr_f" "$lr_f.before-nginx-hardening"
    lr_fait=()
    if (( lr_cible != lr_n )); then
        sed -i -E "0,/^([[:space:]]*)rotate[[:space:]]+[0-9]+/s//\1rotate $lr_cible/" "$lr_f"
        lr_fait+=("« rotate $lr_n » → « rotate $lr_cible » (≈ $LOG_RETENTION_MONTHS mois)")
    fi
    if (( lr_su )); then
        # su <propriétaire> <groupe> du journal lui-même (repli : root adm, l'usage Debian/Ubuntu pour /var/log).
        lr_journal=$(awk '/^[[:space:]]*\// { print $1; exit }' "$lr_f")
        lr_proprio=""
        for lr_j in $lr_journal; do [[ -e "$lr_j" ]] && lr_proprio=$(stat -c '%U %G' "$lr_j" 2>/dev/null) && break; done
        lr_proprio=${lr_proprio:-root adm}
        sed -i -E "0,/\{[[:space:]]*$/s//{\n    su $lr_proprio/" "$lr_f"
        lr_fait+=("directive « su $lr_proprio » ajoutée (le journal ne tournait pas : $lr_err)")
    fi
    if (( lr_cible != lr_n )) && ! grep_q -E "^[[:space:]]*rotate[[:space:]]+$lr_cible\b" "$lr_f"; then
        warn "$lr_nom : aucune ligne « rotate » modifiable dans $lr_f — ajoutez « rotate $lr_cible » à la main."
    elif command -v logrotate >/dev/null 2>&1 && lr_err2=$(run logrotate -d "$lr_f" 2>&1 | grep -m1 -iE '^error:') && [[ -n "$lr_err2" ]]; then
        cp -p "$lr_f.before-nginx-hardening" "$lr_f"
        fail "$lr_nom : $lr_f refusé par logrotate après modification ($lr_err2) — copie d'origine restaurée."
    else
        lr_msg=$(IFS=';'; echo "${lr_fait[*]}")
        pass "$lr_nom : ${lr_msg//;/ ; } dans $lr_f (copie : $lr_f.before-nginx-hardening)"
    fi
done
# Journal systemd : celui de l'application si elle journalise dans un namespace isole (LogNamespace), sinon le general.
jr_ns=""
if [[ "$APP_NAME" == "odoo" ]]; then
    for jr_svc in $ODOO_CONF_UNITES ${DETECT_UNITS:-erplibre.service erplibre_erplibre.service odoo.service}; do
        if systemctl list-unit-files "$jr_svc" --no-legend 2>/dev/null | awk '{print $1}' | grep_q -xF "$jr_svc"; then
            jr_ns=$(systemctl show -p LogNamespace --value "$jr_svc" 2>/dev/null) || jr_ns=""
            break
        fi
    done
fi
JOURNALD_DIR="${NGINX_HARDENING_JOURNALD_DIR:-/etc/systemd}"
if [[ -n "$jr_ns" ]]; then
    jr_f="$JOURNALD_DIR/journald@$jr_ns.conf"; jr_unit="systemd-journald@$jr_ns"
else
    jr_f="$JOURNALD_DIR/journald.conf.d/90-nginx-hardening-retention.conf"; jr_unit="systemd-journald"
fi
# Valeur lue dans une variable : grep renvoie 2 si journald.conf est absent MEME quand il trouve la ligne ailleurs —
# avec pipefail, « grep … | grep_q . » concluait alors « aucune durée fixée » et AJOUTAIT une seconde ligne.
jr_actuel=$(grep -rhsE '^[[:space:]]*MaxRetentionSec=' "$JOURNALD_DIR/journald.conf" "$JOURNALD_DIR/journald.conf.d/" \
            ${jr_ns:+"$jr_f"} 2>/dev/null | tail -1 | tr -d '[:space:]') || true
if [[ -n "$jr_actuel" ]]; then
    if [[ "$RETENTION_EXPLICITE" != "1" || "$jr_actuel" == "MaxRetentionSec=${LOG_RETENTION_MONTHS}month" ]]; then
        pass "Journal systemd${jr_ns:+ (namespace $jr_ns)} : durée de conservation déjà fixée ($jr_actuel)"
    elif ! grep -qsE '^[[:space:]]*MaxRetentionSec=' "$jr_f"; then
        warn "Journal systemd : $jr_actuel est fixé hors de $jr_f — à remplacer à la main par MaxRetentionSec=${LOG_RETENTION_MONTHS}month."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "Journal systemd${jr_ns:+ (namespace $jr_ns)} : $jr_actuel — --update passera à MaxRetentionSec=${LOG_RETENTION_MONTHS}month dans $jr_f."
    else
        sed -i -E "s/^[[:space:]]*MaxRetentionSec=.*/MaxRetentionSec=${LOG_RETENTION_MONTHS}month/" "$jr_f"
        if systemctl restart "$jr_unit" >/dev/null 2>&1; then
            pass "Journal systemd${jr_ns:+ (namespace $jr_ns)} : $jr_actuel → MaxRetentionSec=${LOG_RETENTION_MONTHS}month dans $jr_f, $jr_unit redémarré."
        else
            warn "Journal systemd : MaxRetentionSec=${LOG_RETENTION_MONTHS}month écrit dans $jr_f, mais redémarrage de $jr_unit impossible — à faire à la main."
        fi
    fi
elif [[ "$CHECK_ONLY" == "1" ]]; then
    warn "Journal systemd${jr_ns:+ (namespace $jr_ns)} : aucune durée fixée (limité seulement par la taille) — --update ajoutera MaxRetentionSec=${LOG_RETENTION_MONTHS}month dans $jr_f."
else
    mkdir -p "$(dirname "$jr_f")"
    if [[ -f "$jr_f" ]] && grep_q -E '^\[Journal\]' "$jr_f"; then
        sed -i -E "/^\\[Journal\\]/a MaxRetentionSec=${LOG_RETENTION_MONTHS}month" "$jr_f"
    else
        printf '# Ajouté par nginx-hardening.sh : conservation des journaux (%s mois au plus).\n[Journal]\nMaxRetentionSec=%smonth\n' \
            "$LOG_RETENTION_MONTHS" "$LOG_RETENTION_MONTHS" >> "$jr_f"
    fi
    if run systemctl restart "$jr_unit" >/dev/null 2>&1; then
        pass "Journal systemd${jr_ns:+ (namespace $jr_ns)} : MaxRetentionSec=${LOG_RETENTION_MONTHS}month ajouté dans $jr_f, $jr_unit redémarré."
    else
        warn "Journal systemd : MaxRetentionSec=${LOG_RETENTION_MONTHS}month ajouté dans $jr_f, mais redémarrage de $jr_unit impossible — à faire à la main."
    fi
fi
echo

# nginx_plus_ancien_que FICHIER… : 0 si nginx tourne avec une configuration PLUS ANCIENNE qu'un de ces fichiers (modifié après le dernier chargement :
# il faut recharger), 1 si la configuration chargée est à jour, 2 si on ne peut pas le savoir (nginx arrêté, ps absent). nginx ne dit pas quelle
# configuration il a chargée : à chaque rechargement il démarre de NOUVEAUX processus de travail, dont l'âge (le plus jeune) est l'âge de la
# configuration. NGINX_HARDENING_WORKER_AGE (secondes) remplace cette mesure (essais).
nginx_plus_ancien_que() {
    local age_config="${NGINX_HARDENING_WORKER_AGE:-}" maitre f modif maintenant plus_recent=""
    if [[ -z "$age_config" ]]; then
        command -v ps >/dev/null 2>&1 || return 2
        maitre=$(head -n 1 "${NGINX_HARDENING_NGINX_PID:-/run/nginx.pid}" 2>/dev/null)
        [[ "$maitre" =~ ^[0-9]+$ ]] || return 2
        age_config=$(ps -o etimes= --ppid "$maitre" 2>/dev/null | tr -d ' ' | grep -E '^[0-9]+$' | sort -n | head -1)
    fi
    [[ "$age_config" =~ ^[0-9]+$ ]] || return 2
    maintenant=$(date +%s)
    for f in "$@"; do
        [[ -f "$f" ]] || continue
        modif=$(stat -c %Y "$f" 2>/dev/null) || continue
        (( maintenant - modif + 1 < age_config )) && plus_recent="$f"      # fichier modifié APRÈS le démarrage des travailleurs (tolérance : 1 s)
    done
    [[ -n "$plus_recent" ]]
}

# --- 11b) Journal d'Odoo en FICHIER (logfile de sa configuration) : doit être tourné (logrotate), sinon il grossit sans fin -----------
if [[ "${ODOO_SPECIFIC_STEPS:-yes}" == "yes" && -n "$ODOO_LOGFILE" ]]; then
    echo "--- 11b) Journal d'Odoo en fichier ($ODOO_LOGFILE) ---"
    if [[ ! -e "$ODOO_LOGFILE" ]]; then
        warn "Le fichier $ODOO_LOGFILE (logfile de la configuration d'Odoo) n'existe pas encore — Odoo n'a pas démarré, ou le dossier n'est pas accessible en écriture."
    elif grep -rqsF -e "$ODOO_LOGFILE" -e "$(dirname "$ODOO_LOGFILE")/" /etc/logrotate.d /etc/logrotate.conf 2>/dev/null; then
        pass "Rotation : $ODOO_LOGFILE est couvert par logrotate."
    else
        if [[ "$CHECK_ONLY" == "1" ]]; then
            warn "Aucune règle logrotate ne mentionne $ODOO_LOGFILE : il grossira sans fin — --update crée /etc/logrotate.d/odoo (weekly, rotate 13, compress, copytruncate, missingok, notifempty)."
        else
            lr_odoo=/etc/logrotate.d/odoo
            [[ -e "$lr_odoo" ]] && lr_odoo=/etc/logrotate.d/odoo-nginx-hardening       # un fichier « odoo » existe déjà (autre contenu) : jamais écrasé
            lr_su=""
            lr_proprio=$(stat -c '%U %G' "$ODOO_LOGFILE" 2>/dev/null) || lr_proprio=""
            [[ -n "$lr_proprio" && "$lr_proprio" != "root root" ]] && lr_su="    su $lr_proprio"$'\n'
            if printf '%s\n' "# Généré par nginx-hardening.sh : rotation du journal d'Odoo (logfile de sa configuration)." \
                    "$ODOO_LOGFILE {" "    weekly" "    rotate 13" "    compress" "    delaycompress" "    copytruncate" "    missingok" "    notifempty" \
                    "${lr_su%$'\n'}" "}" | grep -v '^$' > "$lr_odoo" 2>/dev/null; then
                if lr_err3=$(run logrotate -d "$lr_odoo" 2>&1 | grep -m1 -iE '^error:') && [[ -n "$lr_err3" ]]; then
                    warn "$lr_odoo créé mais logrotate -d signale : $lr_err3"
                else
                    pass "$lr_odoo créé : $ODOO_LOGFILE tourné chaque semaine, 13 copies compressées conservées (≈ 3 mois)."
                fi
            else
                warn "Impossible de créer $lr_odoo — à faire à la main (weekly, rotate 13, compress, copytruncate, missingok, notifempty)."
            fi
        fi
    fi
    echo "  Note : app-log-live.py lit ce fichier ; app-log-check.py et web-monitor.py ne lisent que le journal systemd d'Odoo (ils ne verront pas ses lignes)."
    echo
fi

# --- 12) Adresses de l'équipe dans nginx (fichiers GÉNÉRÉS depuis apps/team-ips.list) ------------------------------
# Une seule liste à tenir : la table $is_trusted_ip et les listes allow incluent team-ips-geo.conf et
# team-ips-allow.conf. Écriture atomique (fichier temporaire dans le même dossier, puis mv), nginx -t AVANT tout
# rechargement ; en cas de refus, l'ancienne version est restaurée et nginx n'est pas rechargé.
echo "--- 12) Listes d'adresses : liste blanche et lieux (/etc/default/nginx-tools-*.conf) → nginx ---"
migrer_listes
listes_resume >&2
if [[ "$APP_NAME" != "odoo" ]]; then
    sans_objet "fichiers team-ips-*.conf de la configuration nginx-odoo (les listes restent lues par les outils)"
elif [[ -z "$(listes_fichier_blanche)" ]]; then
    # nginx REFUSE un include à joker sans aucun fichier correspondant ([emerg] open() ... No such file) :
    # on s'assure donc que les deux fichiers existent (au moins vides, en commentaire) même sans liste blanche.
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    if [[ "$CHECK_ONLY" != "1" ]]; then
        for eq_type in geo allow; do
            if [[ ! -e "$snip/team-ips-$eq_type.conf" ]]; then
                mkdir -p "$snip" && printf '%s\n' "# vide — liste blanche introuvable (nginx refuse un include sans fichier)" > "$snip/team-ips-$eq_type.conf" && chmod 644 "$snip/team-ips-$eq_type.conf" \
                    && echo "        $snip/team-ips-$eq_type.conf créé (vide) pour que nginx -t réussisse."
            fi
        done
    fi
    warn "Liste blanche introuvable : aucune adresse n'est générée dans team-ips-*.conf (la gestion des bases de DEV et tout LAB resteraient fermés à tous) — remplir /etc/default/nginx-tools-white-list.conf puis relancer --update."
else
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    generer_equipe geo >/dev/null
    if [[ -n "$EQUIPE_INVALIDES" ]]; then
        fail "liste blanche : entrée(s) invalide(s) —${EQUIPE_INVALIDES%;} — rien n'est écrit dans nginx tant qu'elles ne sont pas corrigées."
    else
        eq_change=0; declare -A eq_ancien=()
        for eq_type in geo allow; do
            eq_dst="$snip/team-ips-$eq_type.conf"
            eq_nouveau=$(generer_equipe "$eq_type")
            if [[ -f "$eq_dst" ]] && [[ "$(cat "$eq_dst")" == "$eq_nouveau" ]]; then
                pass "$eq_dst à jour ($(grep -c '^[^#]' "$eq_dst") adresse(s))."
            elif [[ "$CHECK_ONLY" == "1" ]]; then
                warn "$eq_dst $([[ -f "$eq_dst" ]] && echo "différent de la liste blanche" || echo "absent") — --update le régénérera."
            else
                [[ -f "$eq_dst" ]] && eq_ancien[$eq_type]=$(cat "$eq_dst")
                mkdir -p "$snip"
                eq_tmp=$(mktemp "$snip/.team-ips-$eq_type.XXXXXX")
                printf '%s\n' "$eq_nouveau" > "$eq_tmp" && chmod 644 "$eq_tmp" && mv -f "$eq_tmp" "$eq_dst"
                eq_change=1
            fi
        done
        if (( eq_change )); then
            if eq_erreur=$(run nginx -t 2>&1); then
                if run systemctl reload nginx >/dev/null 2>&1; then
                    pass "Adresses de l'équipe régénérées depuis la liste blanche ; nginx -t réussi, nginx rechargé."
                else
                    warn "Adresses de l'équipe régénérées et nginx -t réussi, mais rechargement impossible — systemctl reload nginx à la main."
                fi
            else
                for eq_type in geo allow; do
                    # Jamais de rm : un include à joker sans fichier fait échouer nginx -t. Sans ancienne version : fichier vide valide.
                    if [[ -n "${eq_ancien[$eq_type]+x}" ]]; then printf '%s\n' "${eq_ancien[$eq_type]}" > "$snip/team-ips-$eq_type.conf"
                    else printf '%s\n' "# vide — restauré après refus de nginx -t" > "$snip/team-ips-$eq_type.conf"; fi
                done
                fail "nginx -t refuse la configuration avec les adresses régénérées — ancienne version restaurée, nginx NON rechargé (nginx -t pour le détail)."
                # Le message de nginx lui-même, puis la preuve : nginx -t refuse-t-il AUSSI la version d'avant ? Alors les adresses ne sont pas en cause : la configuration était déjà invalide.
                printf '%s\n' "$eq_erreur" | head -8 | sed 's/^/        nginx -t : /'
                echo "        Fichiers présents (dossier $snip) :"
                { ls -ld "$snip" "$snip"/team-ips-* 2>&1 || true; } | sed 's/^/          /'
                if ! eq_avant=$(run nginx -t 2>&1); then
                    echo "        nginx -t refuse AUSSI la version d'avant : la configuration nginx est DÉJÀ invalide, indépendamment des adresses de l'équipe."
                    echo "        Corriger d'abord la cause ci-dessus (souvent un fichier de nginx-odoo-config.zip déployé à moitié : include ou variable absente)."
                    [[ "$eq_avant" != "$eq_erreur" ]] && printf '%s\n' "$eq_avant" | head -8 | sed 's/^/        nginx -t (version d'"'"'avant) : /'
                fi
            fi
        fi
        if (( ! eq_change )); then
            # Fichiers déjà à jour, mais nginx les a-t-il CHARGÉS ? (cas réel : adresse ajoutée, fichier régénéré, nginx jamais rechargé -> 403 pour la nouvelle adresse)
            nginx_plus_ancien_que "$snip/team-ips-geo.conf" "$snip/team-ips-allow.conf" && eq_a_charger=1 || eq_a_charger=0
            if (( eq_a_charger )); then
                if [[ "$CHECK_ONLY" == "1" ]]; then
                    warn "Les fichiers team-ips-*.conf sont plus récents que la configuration chargée par nginx : les adresses récentes sont refusées (403) tant que nginx n'est pas rechargé — --update le recharge (ou systemctl reload nginx)."
                elif eq_erreur=$(run nginx -t 2>&1); then
                    if run systemctl reload nginx >/dev/null 2>&1; then
                        pass "nginx rechargé : team-ips-*.conf étaient plus récents que la configuration chargée."
                    else
                        warn "team-ips-*.conf plus récents que la configuration chargée, nginx -t réussi, mais rechargement impossible — systemctl reload nginx à la main."
                    fi
                else
                    fail "team-ips-*.conf plus récents que la configuration chargée, mais nginx -t refuse la configuration — nginx NON rechargé."
                    printf '%s\n' "$eq_erreur" | head -8 | sed 's/^/        nginx -t : /'
                fi
            fi
        fi
        if command -v nginx >/dev/null 2>&1 && ! run nginx -T 2>/dev/null | grep_q 'team-ips-allow'; then
            warn "La configuration nginx active n'inclut pas encore team-ips-*.conf — déployer nginx-odoo-config.zip (odoo-global.conf, env-*.conf)."
        fi
    fi
fi
# --- 12b) Réseaux partagés (lieux [partagée]) → shared-ips-geo.conf : limites de débit plus larges pour une salle derrière UNE adresse ---------------------------------
if [[ "$APP_NAME" == "odoo" ]]; then
    snip="${NGINX_HARDENING_SNIPPETS_DIR:-/etc/nginx/snippets}"
    part_dst="$snip/shared-ips-geo.conf"
    part_nouveau=$(generer_partages)
    part_n=$(printf '%s\n' "$part_nouveau" | grep -c '^[^#]' || true)
    if [[ -f "$part_dst" ]] && [[ "$(cat "$part_dst")" == "$part_nouveau" ]]; then
        pass "$part_dst à jour ($part_n réseau(x) partagé(s))."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "$part_dst $([[ -f "$part_dst" ]] && echo "différent des lieux [partagée]" || echo "absent") — --update le régénérera (nginx refuse l'include de odoo-global.conf sans ce fichier)."
    else
        part_ancien=""; [[ -f "$part_dst" ]] && part_ancien=$(cat "$part_dst")
        mkdir -p "$snip"
        part_tmp=$(mktemp "$snip/.shared-ips-geo.XXXXXX")
        printf '%s\n' "$part_nouveau" > "$part_tmp" && chmod 644 "$part_tmp" && mv -f "$part_tmp" "$part_dst"
        if part_erreur=$(run nginx -t 2>&1); then
            if run systemctl reload nginx >/dev/null 2>&1; then
                pass "Réseaux partagés régénérés ($part_n) dans $part_dst ; nginx -t réussi, nginx rechargé."
            else
                warn "Réseaux partagés régénérés ($part_n) et nginx -t réussi, mais rechargement impossible — systemctl reload nginx à la main."
            fi
        else
            if [[ -n "$part_ancien" ]]; then printf '%s\n' "$part_ancien" > "$part_dst"; else printf '%s\n' "# vide — restauré après refus de nginx -t" > "$part_dst"; fi
            fail "nginx -t refuse la configuration avec les réseaux partagés régénérés — ancienne version restaurée, nginx NON rechargé."
            printf '%s\n' "$part_erreur" | head -8 | sed 's/^/        nginx -t : /'
        fi
    fi
fi
echo

# --- 13) Courriel des alertes : relais SMTP et DNS (MX, SPF, DMARC, DKIM) ---------------------------------------------
# Délégué à app-health-check.py --check-email-dns (même configuration que l'envoi des alertes) : chaque ligne
# [OK]/[ATTN]/[FAIL] est comptée ici ; les lignes de détail (enregistrements DNS à ajouter) sont affichées telles quelles.
# Diagnostic seulement : rien n'est modifié (le DNS se règle chez le fournisseur du domaine). Guide : doc/email-setup.md.
echo "--- 13) Courriel des alertes (relais SMTP, MX, SPF, DMARC, DKIM) ---"
if [[ ! -r "$SCRIPT_DIR/app-health-check.py" ]]; then
    warn "app-health-check.py introuvable à côté de ce script — vérification du courriel impossible."
else
    courriel_n=0; courriel_brut=""
    while IFS= read -r ligne_courriel; do
        case "$ligne_courriel" in
            "[OK] "*)   pass "${ligne_courriel#\[OK\] }"; courriel_n=$((courriel_n + 1)) ;;
            "[ATTN] "*) warn "${ligne_courriel#\[ATTN\] }"; courriel_n=$((courriel_n + 1)) ;;
            "[FAIL] "*) fail "${ligne_courriel#\[FAIL\] }"; courriel_n=$((courriel_n + 1)) ;;
            "       "*) echo "  $ligne_courriel" ;;                         # détail : enregistrement DNS à ajouter
            *)          courriel_brut="${courriel_brut:-$ligne_courriel}" ;;
        esac
    done < <(NGINX_TOOLS_LANG=fr timeout --foreground 120 python3 "$SCRIPT_DIR/app-health-check.py" --check-email-dns 2>&1 || true)
    # Aucun résultat reconnu (programme trop ancien, erreur) : jamais « tout est en ordre » sans vérification.
    if (( courriel_n == 0 )); then
        warn "vérification du courriel impossible : app-health-check.py n'a produit aucun résultat reconnu${courriel_brut:+ (« ${courriel_brut:0:140} »)}."
    fi
    echo "  Envoi réel d'un courriel de test : $SCRIPT_DIR/app-health-check.py --test-email"
fi
echo

# --- 14) Pays des adresses IP : base locale (geoip-bin) ------------------------------------------------------------
# RECOMMANDÉ pour tous les serveurs, pas facultatif : sans lui, app-log-live.py cherche le pays de CHAQUE adresse sur Internet (rdap.org) —
# lent (une requête par adresse) et dépendant d'un service extérieur. Avec lui : lecture locale, instantanée, sans rien envoyer.
echo "--- 14) Pays des adresses IP : geoip-bin (base locale) ---"
if command -v geoiplookup >/dev/null 2>&1; then
    if geoiplookup 8.8.8.8 2>/dev/null | grep -qE 'Country Edition: [A-Z]{2},'; then
        pass "geoip-bin installé et sa base répond : le pays des adresses IP est lu localement (aucune requête Internet)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "geoip-bin est installé mais sa base de pays est introuvable (paquet geoip-database absent ?) : le pays est cherché sur Internet. --update installe geoip-database."
    elif run apt-get install -y geoip-database >/dev/null 2>&1; then
        pass "geoip-database installé : le pays des adresses IP est lu localement."
    else
        warn "installation de geoip-database en échec : lancer « apt-get install geoip-database » et lire l'erreur."
    fi
else
    geoip_candidat=$(apt-cache policy geoip-bin 2>/dev/null | awk '/Candidate:/ { print $2 }') || geoip_candidat=""
    if [[ -z "$geoip_candidat" || "$geoip_candidat" == "(none)" ]]; then
        warn "geoip-bin est introuvable dans les dépôts de cette distribution (apt-cache policy) : le pays de chaque adresse est cherché sur Internet (rdap.org)."
    elif [[ "$CHECK_ONLY" == "1" ]]; then
        warn "geoip-bin absent — RECOMMANDÉ (pas facultatif) : sans lui le pays de chaque adresse est cherché sur Internet. --update l'installe (apt-get install geoip-bin geoip-database)."
    elif run apt-get install -y geoip-bin geoip-database >/dev/null 2>&1; then
        pass "geoip-bin et geoip-database installés : le pays des adresses IP est lu localement (aucune requête Internet)."
    else
        warn "installation de geoip-bin en échec : lancer « apt-get install geoip-bin geoip-database » et lire l'erreur."
    fi
fi
echo

# --- 15) Bip d'app-log-live.py (--chime) dans byobu / tmux ---------------------------------------------------------
# byobu s'appuie sur tmux : par défaut tmux peut avaler le bip (bell-action none, visual-bell on). On dit QUELLE configuration changer ; rien n'est modifié.
if command -v byobu >/dev/null 2>&1 || command -v tmux >/dev/null 2>&1; then
    echo "--- 15) Bip d'app-log-live.py (--chime) dans byobu / tmux ---"
    bip_manque=()
    if command -v tmux >/dev/null 2>&1; then
        [[ "$(tmux show-options -gv bell-action 2>/dev/null)" == "any" ]] || bip_manque+=("set -g bell-action any")
        [[ "$(tmux show-options -gv visual-bell 2>/dev/null)" == "off" ]] || bip_manque+=("set -g visual-bell off")
        [[ "$(tmux show-options -gv allow-passthrough 2>/dev/null)" == "on" ]] || bip_manque+=("set -g allow-passthrough on")
    else
        bip_manque=("set -g bell-action any" "set -g visual-bell off" "set -g allow-passthrough on")
    fi
    if (( ${#bip_manque[@]} == 0 )); then
        pass "byobu/tmux laisse passer le bip (bell-action any, visual-bell off, allow-passthrough on)."
    else
        echo "  [INFO] byobu/tmux peut avaler le bip de « app-log-live.py --chime ». Pour l'entendre, ajouter ces lignes à la configuration PERSONNELLE de byobu"
        echo "         (fichier ~/.byobu/.tmux.conf, à créer au besoin ; pas de fichier système à toucher), puis recharger (touche F5 de byobu, ou « tmux source-file ~/.byobu/.tmux.conf ») :"
        printf '           %s\n' "${bip_manque[@]}"
        echo "         Essai immédiat, sans fichier (perdu à la fermeture de tmux) : tmux set -g bell-action any ; tmux set -g visual-bell off ; tmux set -g allow-passthrough on (tmux 3.3+)."
        echo "         Hors byobu/tmux, rien à changer. Le terminal (client SSH) doit aussi avoir le son actif pour la cloche."
    fi
    echo
fi

# --- 16) Appels d'Odoo vers son propre nom public (User-Agent « python-requests ») ----------------------------------
# Odoo (mass_mailing, aperçu des thèmes…) appelle son nom public avec python-requests : si nginx le prend pour un robot (403), les pages qui s'en servent cassent.
# On refait, DEPUIS le serveur et SANS --resolve (donc par l'adresse publique, comme Odoo), la commande de diagnostic : curl -sI -A python-requests/2.31 https://NOM/mass_mailing_themes
if [[ "$APP_NAME" == "odoo" ]] && command -v nginx >/dev/null 2>&1 && command -v curl >/dev/null 2>&1 && [[ -n "${hsts_names:-}" ]]; then
    echo "--- 16) Appels d'Odoo vers son propre nom public (User-Agent python-requests, page /mass_mailing_themes) ---"
    ua_ctrl="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    n16=0
    while IFS= read -r hname; do
        [[ -z "$hname" ]] && continue
        c_py=$(run curl -sk -I -o /dev/null -w '%{http_code}' --max-time 8 -A "python-requests/2.31" "https://$hname/mass_mailing_themes" 2>/dev/null) || c_py=""
        [[ "$c_py" =~ ^[0-9]{3}$ && "$c_py" != "000" ]] || { echo "  [INFO] $hname : pas de réponse depuis ce serveur (nom non joignable d'ici) — non testé."; continue; }
        c_nav=$(run curl -sk -I -o /dev/null -w '%{http_code}' --max-time 8 -A "$ua_ctrl" "https://$hname/mass_mailing_themes" 2>/dev/null) || c_nav=""
        n16=$((n16 + 1))
        if [[ "$c_py" == "403" && "$c_nav" != "403" ]]; then
            fail "$hname : HTTP 403 pour python-requests mais HTTP ${c_nav:-?} pour un navigateur — le filtre anti-robots bloque les appels d'Odoo vers lui-même (mass_mailing, aperçu des thèmes, rapports). Quoi faire : déployer nginx-odoo-config 1.5 ou plus récent (snippets/securite-commune.conf : exemption de l'adresse du serveur), nginx -t && systemctl reload nginx, puis relancer ce script. Si le serveur est derrière un NAT, l'adresse publique n'est pas celle de l'interface : ajoutez-la à la liste blanche (/etc/default/nginx-tools-white-list.conf)."
        elif [[ "$c_py" == "403" ]]; then
            warn "$hname : HTTP 403 aussi pour un navigateur sur /mass_mailing_themes — ce n'est pas le filtre anti-robots (autre règle : liste blanche, page protégée, module mass_mailing non installé…). À examiner : nginx-log-audit.sh --evidence <adresse du serveur>."
        else
            pass "$hname : python-requests passe (HTTP $c_py ; navigateur HTTP ${c_nav:-?}) — les appels d'Odoo vers son nom public ne sont pas bloqués."
        fi
    done <<< "$hsts_names"
    (( n16 > 0 )) || echo "  [INFO] Aucun nom joignable depuis ce serveur : test impossible ici (refaire à la main : curl -sI -A python-requests/2.31 https://NOM/mass_mailing_themes)."
    echo
fi

if (( BBB_ETAT )); then
    echo "--- BigBlueButton APRÈS ce passage : compatibilité avec nos règles, changements faits par ce passage ---"
    if [[ "$CHECK_ONLY" == "1" ]]; then bbb_etat --after; else bbb_etat --after --save; fi
    echo
fi

echo "=============================================================="
if (( FAIL > 0 )); then
    echo "${C_RED}RÉSUMÉ : $PASS OK, $WARN avertissement(s), $FAIL échec(s).${C_RESET}"
elif (( WARN > 0 )); then
    echo "${C_YELLOW}RÉSUMÉ : $PASS OK, $WARN avertissement(s), aucun échec.${C_RESET}"
else
    echo "${C_GREEN}RÉSUMÉ : tout est en ordre ($PASS vérifications).${C_RESET}"
fi
echo "=============================================================="

if [[ "$CHECK_ONLY" != "1" ]]; then
    # Le fichier d'état est aussi le fichier de configuration : les lignes de l'utilisateur (LANGUAGE, options…) sont conservées, seules les lignes SETUP_* sont remplacées.
    conserve=""
    mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true
    if [[ -r "$STATE_FILE" ]]; then
        conserve="$(grep -vE '^(SETUP_(VERSION|DATE|LAST_RESULT_(PASS|WARN|FAIL))=|# Généré par nginx-hardening\.sh)' "$STATE_FILE" || true)"
    fi
    {
        echo "# Généré par nginx-hardening.sh — les lignes SETUP_* sont réécrites à chaque --update ; les autres lignes (options, LANGUAGE) sont conservées."
        echo "SETUP_VERSION=$SCRIPT_VERSION"
        echo "SETUP_DATE=$(date '+%Y-%m-%d %H:%M:%S %Z')"
        echo "SETUP_LAST_RESULT_PASS=$PASS"
        echo "SETUP_LAST_RESULT_WARN=$WARN"
        echo "SETUP_LAST_RESULT_FAIL=$FAIL"
        if [[ -n "$TIMEZONE_A_ENREGISTRER" ]]; then
            conserve="$(printf '%s\n' "$conserve" | grep -vE '^TIMEZONE=' || true)"
            echo "TIMEZONE=$TIMEZONE_A_ENREGISTRER"
        fi
        [[ -n "$conserve" ]] && printf '%s\n' "$conserve"
    } > "$STATE_FILE"
    echo
    echo "État écrit dans $STATE_FILE."
fi

if (( PORT_EXPOSED > 0 )); then
    echo
    echo "Recommandation pour un port encore ouvert à l'extérieur (étape 4) : ajoutez dans odoo.conf —"
    echo "    [options]"
    echo "    http_interface = 127.0.0.1"
    echo "— puis redémarrez Odoo (pas un simple reload) et relancez ce script pour confirmer."
fi

if (( NEED_FAIL2BAN_RESTART > 0 )); then
    echo
    # "fail2ban-client reload" plutot que "systemctl reload fail2ban" : fonctionne meme si l'unite systemd de
    # fail2ban n'implemente pas ExecReload, et fail2ban-client est deja confirme present a ce stade (etape 9).
    # Contrairement a un redemarrage d'Odoo (jamais automatique dans ce script, interruption reelle du service),
    # un reload de fail2ban est rapide et sans impact sur le trafic web — sans risque a faire automatiquement ici.
    if run fail2ban-client reload >/dev/null 2>&1; then
        echo "Jails fail2ban installés ou régénérés : fail2ban rechargé (fail2ban-client reload)."
        sleep 2
        for j in "${F2B_INSTALLED_JAILS[@]}"; do
            if run fail2ban-client status "$j" >/dev/null 2>&1; then
                echo "    Jail $j : chargé et actif."
            else
                echo "    ${C_RED}Jail $j : NON chargé — voir « journalctl -u fail2ban -n 30 » (erreur de syntaxe, journal introuvable ?).${C_RESET}"
            fi
        done
        if [[ " ${F2B_INSTALLED_JAILS[*]} " == *" odoo-auth "* ]]; then
            echo "    Vérification ponctuelle (une fois) : fail2ban voit-il les échecs de connexion dans le VRAI journal d'Odoo ?"
            echo "    1) Depuis un navigateur, se connecter au site avec un MAUVAIS mot de passe (une fois suffit) ;"
            echo "    2) lancer :"
            # Test sur TEXTE (fiable) : « fail2ban-regex … systemd-journal » peut lire 0 ligne même quand le journal est plein (constaté sur DEV) ; le filtre, lui, est vérifié sur un extrait du journal.
            jopt=""; if [[ -n "${auth_ns:-}" ]]; then jopt=" --namespace=$auth_ns"; fi
            if [[ -n "$ODOO_LOGFILE" && -r "$ODOO_LOGFILE" ]]; then
                jtest="$ODOO_LOGFILE"                                    # journal d'Odoo en fichier : lu tel quel
            else
                jtest=/tmp/odoo-journal.txt
                echo "      journalctl -u $odoo_service$jopt --since \"10 min ago\" --no-pager > /tmp/odoo-journal.txt"
            fi
            echo "      fail2ban-regex $jtest /etc/fail2ban/filter.d/odoo-auth.conf"
            echo "    3) Attendu : « Lines: … N matched » avec N ≥ 1 (les lignes « missed » sont normales : tout le reste du journal d'Odoo)."
            echo "       0 matched : « grep -c 'Login failed' $jtest » = 0 → Odoo n'a pas écrit l'échec (mot de passe pas encore essayé, ou niveau de journal d'Odoo au-dessus de INFO) ;"
            echo "       sinon, vérifier que la ligne se termine par l'adresse (« … from 203.0.113.9 »). Adresse 127.0.0.1 partout : proxy_mode inactif (étape 8) — fail2ban bannirait nginx lui-même."
            echo "    4) La jail elle-même : « fail2ban-client status odoo-auth » (Total failed ≥ 1 après l'essai). ATTENTION : une adresse de la liste blanche de l'équipe est IGNORÉE par fail2ban"
            echo "       (ignoreip) : depuis votre poste d'équipe, « Total failed » reste à 0, c'est NORMAL. Pour voir la jail compter, essayer depuis une adresse hors liste (cellulaire, autre réseau)."
        fi
    else
        # Cause la plus fréquente : fail2ban n'est pas démarré (aucun socket) ; sinon, erreur de configuration.
        # « systemctl is-active » AFFICHE l'état ET renvoie un code non nul s'il n'est pas actif : lu dans une variable.
        f2b_etat=""; command -v systemctl >/dev/null 2>&1 && { f2b_etat=$(systemctl is-active fail2ban 2>/dev/null) || true; }
        if [[ -n "$f2b_etat" && "$f2b_etat" != "active" ]]; then
            echo "${C_RED}Jails fail2ban installés, mais fail2ban n'est PAS démarré ($f2b_etat) : aucune jail n'est active.${C_RESET}"
            echo "    Démarrer et activer au démarrage : systemctl enable --now fail2ban"
            echo "    Puis vérifier                    : fail2ban-client status"
        else
            echo "${C_RED}Jails fail2ban installés, mais le rechargement a échoué.${C_RESET}"
            f2b_test=$(run fail2ban-client -t 2>&1 | grep -iE 'error|erreur|fail|not found|No such|unable' | head -5) || f2b_test=""
            [[ -n "$f2b_test" ]] && printf '    %s\n' "Test de la configuration (fail2ban-client -t) :" && printf '      %s\n' "$f2b_test"
            echo "    Détail : journalctl -u fail2ban -n 30 ; puis fail2ban-client reload"
        fi
    fi
fi

exit $(( FAIL > 0 ? 1 : 0 ))
