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
* `S`/`I` dernières inscriptions aux sondages / événements (30 jours), `E` détail des erreurs, `D` diagnostic du site (pourquoi la page de maintenance s'affiche), `G` membres de chaque groupe `RLQ*`, `b` bannir les adresses recommandées.
* `--hide-addons` (touche `q`) : cache les lignes INFO des modules d'Odoo (`odoo.addons.*` : tâches planifiées, websocket, fetchmail...). Jamais cachées : les erreurs (WARNING, ERROR, CRITICAL, traces), les courriels envoyés (`mail_mail`, `ir_mail_server`, « successfully sent ») et les fichiers générés (`ir_actions_report`, PDF...). Appuyer de nouveau sur `q` affiche le nombre de lignes cachées.

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

Toutes les 30 secondes, un échantillonneur léger lit les compteurs du noyau (aucune commande) : processeur, temps d'attente (PSI) du disque / du processeur / de la mémoire - le cgroup *du conteneur lui-même* dans un conteneur LXC - , et le % d'occupation des disques et l'attente par opération. Chaque requête Odoo (temps SQL + temps Python de sa ligne de journal) est classée dans l'heure où elle a eu lieu, « disque occupé » ou « disque calme ». Appuyer sur **P** (ou Ctrl-G au niveau 6 et plus) après quelques heures : le verdict dit si les disques ralentissent les requêtes (SSD justifiés), seulement par moments (démarrages, sauvegardes), ou pas du tout (SATA suffisant), avec le tableau par heure au niveau 8. Dans un conteneur, les compteurs des disques peuvent être partiels : lancer `host-perf-audit.py` sur l'hôte Proxmox pour les vrais disques.

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

## Options
{{HELP}}
