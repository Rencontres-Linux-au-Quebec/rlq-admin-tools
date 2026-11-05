# app-log-live.py - journal d'Odoo en temps réel et tableau de bord

Suit le journal d'Odoo (`journalctl -f`) et réécrit chaque ligne pour les humains : **qui** (l'utilisateur Odoo derrière une adresse, d'après PostgreSQL, mis en cache), **où** (pays), et si l'adresse est l'équipe, un lieu nommé, le serveur lui-même (`127.0.0.1` = ce programme) ou **bannie** (`[banni : fail2ban|CrowdSec]`). Les requêtes suspectes sont en vidéo inverse ; les requêtes lentes (`--slow`, 5 s) et les erreurs peuvent sonner (`--chime`).

```bash
app-log-live.py                     # suivre, avec l'historique récent
app-log-live.py --level 5 --health 30      # tableau de bord niveau 5 ; alerte de santé aux 30 min si quelque chose ne va pas
app-log-live.py --accentuate-group "Équipe"  # contacts d'une étiquette Odoo en blanc gras sur bleu
app-log-live.py --modules-startup          # tableau des modules personnalisés installés au démarrage
app-log-live.py --summary --no-follow      # affiche le résumé et quitte
```

## Touches (`?` pour le menu)

* `Ctrl-G` tableau de bord (santé, ressources, cache des adresses, langues, top 10 des URL, erreurs d'Odoo) ; `1`-`9` choisissent son niveau ; `Ctrl-T` seulement ce qui a changé depuis le dernier affichage (le sommaire compte les requêtes par nom de la colonne DNS, sans les adresses non identifiées) ; `Ctrl-C` arrêt et résumé de la session (qui inclut le nombre de membres de chaque groupe `RLQ*`).
* Réglages changés à la volée : `a` groupe accentué, `c` bip, `d`/`t` largeur de la colonne des noms, `e` exclure des IP, `H` période de santé, `i` cacher l'IP, `q` cacher les lignes des modules d'Odoo (`--hide-addons`), `l` surligner des mots, `m` minimum, `M` tableau des modules installés avec tri, `L` derniers modules, `n` seulement les introuvables, `o` seulement les lignes contenant un texte, `r` rapport d'erreurs à copier-coller, `s` seulement les suspectes, `T` rapport périodique, `v` verbeux, `w` surveiller des URL, `C` sauvegarder les réglages changés dans le fichier de configuration.
* `z` (1.163) analyse des problèmes soulevés, avec les causes probables et les solutions recommandées : voir la section « Analyse des problèmes soulevés » plus bas.
* `S`/`I` dernières inscriptions aux sondages / événements (30 jours), `E` détail des erreurs, `D` diagnostic du site (pourquoi la page de maintenance s'affiche), `G` membres de chaque groupe `RLQ*`, `b` bannir les adresses recommandées (1.155 : seulement celles que `nginx-log-audit.sh --investigate` recommande lui aussi : chaque adresse est d'abord vérifiée par ce programme, celui qui bannit ; les autres sont listées avec son verdict).
* `--hide-addons` (touche `q`) : cache les lignes INFO des modules d'Odoo (`odoo.addons.*` : tâches planifiées, websocket, fetchmail...), et celles de `odoo.models.unlink` (enregistrements supprimés) et `odoo.modules.registry` (invalidations de cache). Jamais cachées : les erreurs (WARNING, ERROR, CRITICAL, traces), les courriels envoyés (`mail_mail`, `ir_mail_server`, « successfully sent ») et les fichiers générés (`ir_actions_report`, PDF...). Appuyer de nouveau sur `q` affiche le nombre de lignes cachées.

## Analyse des problèmes soulevés (touche z, 1.163)

Appuyer sur **z** dans le flux en direct : le programme analyse ce que le tableau de bord a compté depuis son démarrage et affiche, pour chaque problème, les preuves, la cause probable et quoi faire. Plus besoin de copier les journaux pour les faire expliquer.

1. **Détails lus dans les journaux**, seulement pour les problèmes soulevés : la trace d'Odoo qui suit chaque message ERROR / CRITICAL (le fichier journal d'Odoo, sinon le journal systemd quelques secondes autour de son heure : exception, module du dernier appel) et, pour les URL qui répondent 4xx, les codes, les référents (la page qui contient le lien mort) et les User-Agents des journaux d'accès de nginx.
2. **Règles** (apps/_advisor.py) : erreurs 5xx (Odoo n'a pas répondu, ou une exception dans un module), 404 sur des pages de sitemap.xml (vraie page disparue, lien tronqué, ou fausse alerte d'un code de langue seul que le site n'offre pas), 404 répétés hors du sitemap (produit dépublié, lien interne mort), `sitemap.xml` refusé ou absent, messages d'Odoo connus (source maps `.map`, « called ignoring args », invité du clavardage expiré, « Exception during request handling » expliquée par sa trace), échecs de mise à jour simultanée, courriels en échec (codes SMTP 452, 503, 550), requêtes lentes (SQL, Python ou cache froid), adresses à bannir (touche `b` : la liste blanche et le score de nginx-log-audit.sh décident, les relais CDN ne sont jamais proposés), formulaires de compte, latence mesurée sur trop peu de requêtes.
3. **Amélioration continue** : chaque analyse est gardée dans `advisor-history.json` (dossier d'état du programme : `APP_LOG_LIVE_STATE_DIR`, sinon `/var/lib/app-log-live`, sinon `~/.cache/app-log-live` ; mode 600 ; 200 analyses et 90 jours au plus). Chaque problème porte une étiquette **[nouveau]**, **[récurrent : N analyses de suite]**, **[revenu]** ou **[rien de nouveau depuis la dernière analyse]** ; les problèmes disparus sont listés comme **réglés**, et les problèmes vus le plus souvent arrivent en tête de « à corriger en premier ».

Gravité : ✖ problème, ⚠ à regarder, ℹ information. Rien n'est modifié sur le serveur : les journaux sont seulement lus, et le seul fichier écrit est l'historique.

1.164 : dans la comparaison avec sitemap.xml (santé, `--log-chk-sitemap`), un premier segment de deux lettres n'est retiré comme préfixe de langue que s'il est un code ISO 639-1 (`/fr`, `/es`, `/fr_CA`...). Avant, `/ev` (un `/event` tronqué) était comparé comme la page d'accueil et compté comme un 404 « dans sitemap.xml ».

### Sur plusieurs semaines : --advise (1.165)

```
sudo app-log-live.py --advise          # les 14 derniers jours
sudo app-log-live.py --advise 30       # les 30 derniers jours
sudo app-log-live.py --advise --since 2026-10-01 --until 2026-10-31
```

La même analyse que la touche z, sans le flux en direct : les journaux de la période sont lus sans être affichés (cela peut prendre quelques minutes pour plusieurs semaines), puis l'analyse est affichée. Les journaux d'accès de nginx déjà tournés pendant la période (`.1`, `.2.gz`...) sont lus pour les référents. Chaque exécution est gardée dans `advisor-history-advise.json` (séparé de l'historique de la touche z, dont les périodes ne sont pas comparables) : deux exécutions à une semaine d'écart disent ce qui est nouveau, récurrent ou réglé. Avec `--summary`, le résumé de la session suit. 1.166 : la période est lue environ 15 fois plus vite (20 000 lignes en 8 s au lieu de plus de 2 minutes sur la machine de test) et avec la priorité la plus basse (nice 19, classe disque « idle »), pour que l'analyse ne ralentisse jamais Odoo : les lignes sont comptées sans être mises en forme ni traduites, et les noms (DNS, RDAP, pays) sont cherchés à la fin, seulement pour les adresses que l'analyse affiche. Sans sudo, le journal systemd et `/var/lib/app-log-live` peuvent être illisibles.

1.168 : pendant la lecture de la période, la sortie d'erreur montre la progression : la part de la période déjà lue, la date atteinte, les lignes lues par seconde et le temps restant (une ligne réécrite sur place dans un terminal, une ligne toutes les 30 s sinon), puis chaque étape de l'analyse (noms des adresses, traces d'Odoo, journaux de nginx, journal du service, base de données, réponse du site, règles) avec le temps écoulé depuis le début.

### Détails vérifiés et corrections (1.167)

Pour chaque problème, l'analyse vérifie maintenant les faits elle-même au lieu de seulement renvoyer vers un outil (lecture seule) :

* **Requêtes lentes** : les workers et les limites d'`odoo.conf` (`workers`, `max_cron_threads`, `limit_time_cpu`, `limit_time_real`, `limit_memory_*`), les processeurs et la mémoire de la machine (ceux du conteneur), comparés au guide de déploiement d'Odoo ((2 x CPU) + 1 workers au plus, environ 325 Mo chacun) ; les heures les plus chargées ; les requêtes arrivées dans les 10 minutes après un démarrage d'Odoo (cache froid).
* **Odoo injoignable depuis nginx** : les lignes du journal d'erreurs de nginx ne sont plus comptées comme erreurs d'Odoo ni comme courriels en échec ; elles sont regroupées et comparées aux démarrages et arrêts du service (son journal) et à son état actuel.
* **Exceptions d'Odoo** : l'exception de chaque occurrence (pas seulement de la dernière), le module du dernier appel ; causes connues (clé VAPID des notifications, droits d'accès, enregistrements supprimés, mémoire, délais...).
* **Erreurs 5xx** : regroupées par page, avec la trace écrite à la même seconde et les adresses ; un scanneur de vulnérabilités (guillemets, parenthèses, « zqzz ») est reconnu.
* **Courriels en échec** : la base de données décide (état de la file de courriels, causes, serveurs sortants) : un nombre du journal que la base ne confirme pas est affiché comme information.
* **404** : la réponse du site maintenant, l'événement ou le produit du numéro de l'adresse (publié, archivé, supprimé), la page web et une page semblable, une redirection déjà définie ; les référents du site lui-même (avec ou sans www) sont reconnus.
* **Formulaires de compte** : formulaires vraiment envoyés (POST) ou seulement affichés (GET), inscription libre ou sur invitation, comptes portail créés dans la période.

Avec **`--apply`** (avec `--advise`, dans un terminal), les corrections sont proposées une à une après l'analyse, une question chacune : bannir les adresses avec `nginx-log-audit.sh --ban` (il examine chaque adresse, vérifie la liste blanche et son score, et demande sa propre confirmation), ouvrir `odoo-mail-retry.py` pour les courriels en échec (il les liste et demande avant de les renvoyer), préchauffer Odoo avec `odoo-warmup.py` après un redémarrage. Rien n'est fait sans un « oui », et `odoo.conf` n'est jamais modifié.

## Tableau de bord : ce que change 1.169

* Avec `--log-merge`, la ligne de nginx et la ligne d'Odoo d'une même requête forment une seule ligne ; les temps d'Odoo de cette ligne (requêtes SQL, temps SQL, temps Python) sont maintenant comptés : avant, les requêtes lentes, la latence et le maximum de requêtes SQL du tableau de bord ne voyaient que les lignes d'Odoo restées sans partenaire nginx (67 requêtes mesurées pour 2 603 vues).
* Les requêtes lentes des 10 minutes après le démarrage d'Odoo (cache froid) sont affichées mais ne comptent pas dans la santé ; les sondes de ce serveur (`app-health-check.py`) sont nommées comme telles : elles ont mesuré la lenteur, elles ne l'ont pas causée. L'état du serveur « à cet instant » n'explique des requêtes lentes que si elles datent de moins de 5 minutes.
* « Odoo injoignable depuis nginx » compte les interruptions (erreurs à moins de 5 minutes d'écart) : une courte interruption (un redémarrage) est « à regarder », plusieurs, ou une de plus de 15 minutes, sont un « problème », avec l'heure de démarrage d'Odoo.
* « Surveillance automatique (web-monitor.py) : dernier passage il y a N h » quand le dernier passage date de plus de 48 heures : son minuteur est arrêté ou en échec.
* Comptes sans marque de pluriel : « requêtes : 4 · adresses : 1 ».

## Enregistrer un test (touche R)

Pour analyser un test du site (un sondage abandonné, une inscription, une proposition de présentation...) sans le bruit :

1. Appuyer sur **R** dans le direct : une étiquette est demandée (par exemple `sondage-abandonne`, Entrée = aucune).
2. Faire le test. Pendant l'enregistrement, **REC** s'affiche en rouge à la colonne `$COLUMNS - 4` de chaque ligne.
3. Appuyer de nouveau sur **R** : l'enregistrement s'arrête et l'archive `.tar.xz` est créée en arrière-plan. Son chemin s'affiche sur la ligne « Archive à envoyer pour analyse ».

Pendant l'enregistrement, **N** marque les étapes du test : N demande une description et démarre une étape, N de nouveau la termine (par exemple « inscription », puis « sondage abandonné »). Les étapes (début, fin, durée, description) sont listées dans `steps.txt` de l'archive et dans `records.log`. Une étape encore ouverte à l'arrêt est fermée à ce moment-là.

L'archive contient : `README.txt` (heures locales et UTC, sources absentes), `records.log` (les lignes du test, sans robots, fichiers statiques, websockets ni sondes locales), `stream-all.log` (toutes les lignes, avec leur catégorie), `raw/` (extraits complets de nginx, Odoo, fail2ban et du journal systemd pendant la fenêtre), `network/` (connexions des ports web et d'Odoo), `db/` (activité PostgreSQL, verrous sur `ir_cron`, instantanés des tables de sondages, inscriptions, courriels et pages), `context/` (réglages du service et d'Odoo sans secret, modules).

Adresses IP, courriels, noms connus et jetons sont remplacés par des pseudonymes stables avant l'écriture. La base n'est lue qu'en lecture seule.

**Prérequis de l'enregistrement (1.100)** : le client `psql` (paquet `postgresql-client`) et un accès à la base Odoo sont obligatoires ; sans eux, l'enregistrement est refusé avec un message (les échantillons PostgreSQL montrent les écritures et les verrous). Le programme peut tourner sans root : PostgreSQL est alors interrogé par `sudo -n -u postgres`, et les commandes avancées (fail2ban-client, ipset, journalctl) par `sudo -n`. Ces règles sudo doivent être autorisées sans mot de passe pour le compte qui lance le programme. L'archive contient aussi le contexte système (root ou non, système d'exploitation, versions des outils).

Sans clavier : `--record-test-log MIN` enregistre MIN minutes à partir du démarrage, écrit l'archive puis quitte. `--record-max MIN` (clé `RECORD_MAX`, 60 par défaut et au maximum ; 0 refusé) arrête un enregistrement de lui-même. `--steps-line` (touche F) affiche toutes les étapes de l'enregistrement sur une ligne blanche, mise à jour à chaque étape (écran seulement).

## Latence : est-ce le disque ?

Toutes les 30 secondes, un échantillonneur léger lit les compteurs du noyau (aucune commande) : processeur, temps d'attente (PSI) du disque / du processeur / de la mémoire - le cgroup *du conteneur lui-même* dans un conteneur LXC - , et le % d'occupation des disques et l'attente par opération. Chaque requête Odoo (temps SQL + temps Python de sa ligne de journal) est classée dans l'heure où elle a eu lieu, « disque occupé » ou « disque calme ». Appuyer sur **Y** (ou Ctrl-G au niveau 6 et plus) après quelques heures : le verdict dit si les disques ralentissent les requêtes (SSD justifiés), seulement par moments (démarrages, sauvegardes), ou pas du tout (SATA suffisant), avec le tableau par heure au niveau 8. Dans un conteneur, les compteurs des disques peuvent être partiels : lancer `host-perf-audit.py` sur l'hôte Proxmox pour les vrais disques.

## Règles de conception à connaître

* Une recherche lente ne retient jamais une recherche rapide : la voie rapide (ce serveur, une personne connue, l'équipe) ne fait aucun appel extérieur ; DNS, propriétaire et pays tournent dans des threads séparés. Les noms de personnes ne dépendent que de PostgreSQL (lecture seule, en cache).
* Odoo n'enregistre pas la fin d'une session : « connecté » signifie actif depuis moins de `--idle` minutes.
* L'heure d'un événement vient de la ligne du journal, jamais du fuseau horaire de la machine.
* Les journaux quotidiens en couleur vont dans `/var/log/app-log-live/` (root) ou `~/.local/state/app-log-live/` (droits 600, 30 jours ; `--log-dir`, `--log-keep-days`, `--no-log-file`).
* Par défaut dans un terminal, une ligne du journal plus large que `$COLUMNS - 10` colonnes (`--truncate N` : N colonnes) est raccourcie en « début ... deux derniers mots » : la fin d'une URL longue (et une étiquette `[banned: ...]`) reste visible ; `--no-truncate` affiche les lignes entières. Les menus et rapports ne sont jamais coupés ; le journal quotidien garde les lignes entières.
* Une ligne du journal sur 10 est soulignée, pour suivre une ligne d'un bout à l'autre d'un écran large (`--underline N`, `UNDERLINE=N` ; `--no-underline` : aucune). La touche `U` du menu demande le nombre N ; `C` enregistre la valeur dans le fichier de configuration, comme les autres réglages.
* `--min` est actif par défaut : sans nom de base, sans « werkzeug », sans les lignes de fetchmail sauf erreur (`--no-min` ou `MIN=no` : tout).
* Les valeurs de configuration s'écrivent en anglais seulement : `yes` / `no` (`oui` / `non` sont encore lus, avec un avertissement demandant de les remplacer).
* Par défaut dans un terminal, les adresses IP et les courriels sont affichés en pseudonymes stables (`IP-4f2a9c`, `usager-9c1e03@anonyme.invalid`) ; `--no-anonymize` affiche les vraies valeurs. Les noms des personnes restent ; le journal quotidien garde tout. Un tube ou un programme qui lit la sortie reçoit toujours les vraies lignes, entières.
* Un courriel envoyé est affiché « Courriel no N envoyé à NOM - « sujet » », même quand Odoo l'a supprimé juste après l'envoi (auto_delete).
* « Qui est connecté maintenant » donne le nom de chaque compte SSH avec son nombre de sessions (`ana x2, root x1`, sftp compris) ; les groupes RLQ* s'affichent sur 4, 2 ou 1 colonne(s) selon la largeur du terminal.
* Touche **I** : inscriptions regroupées par événement, puis par billet, avec **le sondage de chaque billet** (comptes : confirmées, non terminées, sans sondage) ; une réponse à un autre sondage (celui de l'an dernier, un essai, un autre billet) est signalée, jamais comptée.
* Un courriel envoyé montre son destinataire et son sujet : « Courriel no 7573 envoyé à Ana Tremblay (a***n@...) - « sujet » - inscription ... ».
* **Ctrl+C** pendant un programme lancé depuis le menu (nginx-log-audit.sh, web-monitor.py...) : une seule question, tout de suite.

## Période, journalctl et filtres par pays (1.112)

* `-S` / `--since TEMPS` et `-U` / `--until TEMPS` : `YYYY-MM-DD [HH:MM[:SS]] [Z ou +HH:MM]`, `HH:MM[:SS]` (aujourd'hui), `today`, `yesterday`, `now`, `@EPOCH`, ou relatif (`-2h`, `'-30 min'`, `'0.5 day'`, `'3 days ago'`). Heure locale, ou UTC avec `--utc`. Une date seule couvre toute la journée (`--until` s'arrête au début du jour suivant). En direct, `--until` arrête le programme à ce moment.
* `--utc` : heures des lignes et heures données sans fuseau en UTC.
* `-n` / `--lines N` : alias de `--lines`, comme dans journalctl. `--no-hostname` : sans le nom de l'hôte.
* `-g` / `--grep REGEX` : seulement les lignes dont le message correspond. Insensible à la casse, sauf si REGEX contient une majuscule (comme journalctl).
* `--country CC,CC` : seulement les lignes dont la première adresse (le client) est dans ces pays. `--exclude-country CC,CC` : cache ces pays. Codes à deux lettres, répétables. Une adresse de pays inconnu est cachée par `--country` et gardée par `--exclude-country`.
* `--days` accepte les fractions : `--days 0.1` = 2,4 heures d'historique des connexions.
* `-f` et `--no-pager` sont acceptés pour compatibilité avec journalctl (sans effet).

Exemples :

```bash
app-log-live.py -S '-2h' --utc -n 500          # deux dernières heures, en UTC
app-log-live.py -S yesterday -U today -g erreur  # hier seulement, lignes contenant « erreur »
app-log-live.py --exclude-country US,CN         # cache les adresses de ces pays
app-log-live.py --days 0.1 --no-follow          # historique des connexions des 2,4 dernières heures
```

## Barre d'état, rafraîchissement et impression (1.113)

* **Barre d'état** (vidéo inverse), après toutes les N lignes affichées (`--status-every N`, 100 par défaut ; 0 = jamais) : tentatives d'injection SQL, réponses 4xx et 5xx, adresses bannies vues, requêtes lentes (durée >= `--slow`) et la plus lente. Les compteurs sont cumulés depuis le dernier rapport détaillé : **Ctrl-T** ou **g** les remettent à zéro. Couleur : blanc = rien à signaler ; vert = un peu (4xx, quelques requêtes lentes) ; jaune = à regarder (injection SQL, 5xx, adresse bannie, plusieurs requêtes lentes) ; rouge = enquêter maintenant (injections répétées, beaucoup de 5xx ou de requêtes lentes). 1.125 : chaque chiffre a sa propre couleur (vert, jaune ou rouge) selon sa criticité, par exemple 5xx : 0 vert, 1 à 4 jaune, 5 et plus rouge. La barre est aussi affichée une fois après l'historique, au démarrage (sauf avec `--status-every 0`). 1.154 : la ligne des libellés des colonnes (HEURE, PROG, NIV, PA BLOC-IP, HTTP, STA...) est réaffichée juste après chaque barre d'état, alignée sur la dernière ligne de requête ; « PA BLOC-IP » se place au-dessus du code du pays et du nom (ou de l'adresse), avec ou sans `--min`.
* **f** (rafraîchir) : les dernières lignes du tampon sont réaffichées avec les options courantes (adresses, DNS, noms, surlignage, `--only`...). Elles ne sont pas recomptées ni réécrites dans le journal quotidien.
* **P** (imprimer) : les dernières lignes du tampon (`--buffer N`, 200 par défaut ; 0 = aucun) sont écrites dans un fichier, couleurs conservées (`less -R fichier`). Le programme demande le nombre de lignes et le nom du fichier. Le fichier est créé en mode 600 : il contient des adresses et des noms.
* **Y** : rapport de latence (anciennement la touche P).

## Journaux nginx dans le même flux (1.116)

Les journaux d'accès et d'erreurs du site (`ACCESS_LOGS` et `ERROR_LOGS` du profil de l'application, dans `/var/log/nginx`) sont lus
avec le journal de l'application. Leurs lignes ont le même préfixe et les mêmes colonnes que les lignes Odoo (date et heure
locales, hôte, programme `http`, niveau, pays et adresse, nom). Ils sont masqués par défaut sur un serveur Odoo.

- `--log-nginx` (ou `LOG_NGINX=yes` dans le fichier de configuration) les affiche dès le départ.
- `--log-merge` (1.123) : la ligne nginx et la ligne Odoo de la MÊME requête (même URL et même statut, à 5 secondes près) s'affichent en UNE seule ligne, avec les requêtes SQL et les temps d'Odoo. Depuis la 1.153, un 304 de nginx (il a répondu lui-même à la requête conditionnelle du navigateur) se fusionne avec un 200 d'Odoo, et un 499 de nginx (client parti avant la réponse) avec n'importe quel statut d'Odoo ; la ligne fusionnée garde le statut de nginx, celui qu'a reçu le navigateur. Demande `--log-nginx` ; une ligne nginx qui attend encore sa ligne Odoo après 8 secondes est affichée seule. Clé de configuration : `LOG_MERGE`.
- `--status-header` (1.123, 1.125) : l'heure reste au début de chaque ligne ; la date (sans l'heure) et le nom de l'hôte s'affichent au début de la barre d'état (date et hôte de la dernière ligne). Clé de configuration : `STATUS_HEADER`.
- `--config-merge` (1.125) : réécrit le fichier de configuration lu (celui donné avec `-c FICHIER`, sinon le dernier lu) à partir de la NOUVELLE configuration par défaut (exemple de la langue courante), en gardant les valeurs réglées dans l'ancien fichier. L'ancien fichier est d'abord copié en `FICHIER.bak-AAAAMMJJ-HHMMSS` (heure locale). Les clés inconnues du programme sont signalées et écartées. Le programme se termine ensuite.
- Affichage (1.123) : le niveau s'écrit en 4 caractères (`ERR`, `WARN`, `CRIT`, `DBUG`, `INFO`), le protocole en `H1.1`, et une ligne raccourcie est marquée par `…`. 1.124 : la barre d'état donne les réponses 4xx et 5xx par code (403, 404, 500...).
- La touche `x` les affiche ou les masque à chaud, à partir de la ligne suivante (le menu `?` indique s'ils sont affichés). Les lignes
  masquées ne sont ni comptées ni recherchées. Les lignes lues pendant qu'ils étaient masqués ne sont pas affichées après coup.

```
app-log-live.py --log-nginx                      # en direct : Odoo et nginx ensemble
app-log-live.py --log-nginx --no-follow -S '-1h' # la dernière heure des deux, puis arrêt
app-log-live.py --log-nginx -g ' 404 '           # les réponses 404 de nginx et d'Odoo
```

- Le message de départ nomme les fichiers nginx lus, et indique s'ils sont affichés.
- `-S`, `-U` et `-g` s'appliquent aussi aux lignes nginx (les lignes de l'application sont déjà filtrées par journalctl).
- Un journal nginx silencieux ne retient pas les lignes d'Odoo : il est attendu `APP_LOG_MERGE_WAIT` secondes (2 par défaut),
  puis il n'est plus attendu tant qu'il ne parle pas.
- La fusion est faite par `apps/_logs_merge.py`, qui peut aussi être lancé seul (`--help`, `--version`).
- BigBlueButton : ses lignes nginx étaient déjà affichées et le restent.

## Options
* **1.114 - détail de la barre d'état** : la barre nomme aussi les trois adresses qui ont le plus de lignes problématiques (`IP principales`), seulement lorsque les adresses sont affichées (`--show-ip`, ou la touche **H**) ; sinon elle indique qu'elles sont masquées. La première fois que la barre passe au rouge, un bip et une ligne rouge **ALERTE** sont affichés ; l'alerte n'est redonnée qu'après **Ctrl-T** ou **g**.
* **1.114 - fichier de configuration** : `BUFFER=` (`--buffer`) et `STATUS_EVERY=` (`--status-every`) se règlent dans `/etc/default/app-log-live.conf` ou `~/.app-log-live.conf`. La ligne de commande reste prioritaire.

* **1.156 - colonne du système** : le User-Agent donne `AND`, `IOS`, `WIN`, `LIN` ou `MAC` ; sans système, le programme qui fait la requête : `CUR` (curl), `PYT` (Python), `WGT` (wget), `GOL` (Go), `JAV` (Java), `PHP`, `NOD` (Node.js), `RUB` (Ruby), `PER` (Perl) ; `OTH` pour tout autre User-Agent.

* **1.157 - formulaires de compte** : une requête à `/web/reset_password` ou `/web/signup` (avec ou sans préfixe de langue) s'affiche en **vidéo inverse rouge**. Le résumé (Ctrl-G, Ctrl-T, Ctrl-C) ajoute la ligne « Formulaires de compte » : nombre de requêtes par adresse (cinq premières) et par page. Un robot qui suit les liens de la page de connexion les lit sans rien soumettre ; ce repère sert à voir une adresse qui les demande en rafale.

* **1.158 - seulement les erreurs** : `--errors-only` (`ERRORS_ONLY`) ou la touche `X` (bascule) n'affiche que les erreurs et les requêtes suspectes : code HTTP 400 et plus, requête suspecte, WARNING / ERROR / CRITICAL d'Odoo, traces, connexions échouées. Les transactions normales (2xx, 3xx, INFO) sont cachées. Au démarrage (au moins 3000 lignes d'historique lues) et à chaque activation par `X`, les **100 dernières erreurs** s'affichent d'abord. Le résumé ne compte que ce qui est affiché.

* **1.159 - robots** : la colonne du système affiche `BOT` (magenta) pour un robot qui se nomme dans son User-Agent (Googlebot, Amazonbot, SemrushBot, NVIDIABOT, facebookexternalhit...), vérifié avant le système ; les programmes `CUR`, `PYT`, `WGT`, `GOL`, `JAV`, `PHP`, `NOD`, `RUB`, `PER` s'affichent en **jaune gras** (outil de script). Un **403 produit par un robot refusé** (liste de `bot_blocker.conf`, `[BOT]`) n'est pas critique : l'URL s'affiche en jaune, sans vidéo inverse ; une requête à un fichier sensible garde sa vidéo inverse.

* **1.160 - démarrage et antislash** : les lignes de démarrage (journaux nginx, service Odoo, historique des connexions, avertissement PostgreSQL des modules, légendes des couleurs, adresses bannies, écran, journal quotidien) sont dans la touche `?` et plus à l'écran ; la ligne « Informations de démarrage : appuyez sur ? » est retirée. Une requête avec un antislash (`register%5C` chez nginx, `register\\` chez Odoo) est vue comme la même requête et fusionne en une seule ligne.

* **1.161 - thèmes** : `--theme N` (0 à 4) ou `THEME` dans la configuration : toutes les couleurs sont remplacées par les plus proches qui se lisent sur le fond choisi (voir `00-overview.md`).

{{HELP}}

* **1.162 - touche Entrée et utilisateurs connectés** : en attente de nouvelles lignes, **Entrée** affiche la barre d'état avec la date et l'heure de l'action (sans la légende, sans remise à zéro des compteurs). La barre compte les sessions SSH comme les rapports (processus sshd et `who` ensemble : elle restait à 0 quand `who` ne donnait pas d'adresse d'origine) et ajoute « connectés (who) N (comptes) ».
