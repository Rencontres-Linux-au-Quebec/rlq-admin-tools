# app-log-live.py — journal d'Odoo en temps réel et tableau de bord

Suit le journal d'Odoo (`journalctl -f`) et réécrit chaque ligne pour les humains : **qui** (l'utilisateur Odoo derrière une adresse, d'après PostgreSQL, mis en cache), **où** (pays), et si l'adresse est l'équipe, un lieu nommé, le serveur lui-même (`127.0.0.1` = ce programme) ou **bannie** (`[banni : fail2ban|CrowdSec]`). Les requêtes suspectes sont en vidéo inverse ; les requêtes lentes (`--slow`, 5 s) et les erreurs peuvent sonner (`--chime`).

```bash
app-log-live.py                     # suivre, avec l'historique récent
app-log-live.py --level 5 --health 30      # tableau de bord niveau 5 ; alerte de santé aux 30 min si quelque chose ne va pas
app-log-live.py --accentuate-group "Équipe"  # contacts d'une étiquette Odoo en blanc gras sur bleu
app-log-live.py --modules-startup          # tableau des modules personnalisés installés au démarrage
app-log-live.py --summary --no-follow      # affiche le résumé et quitte
```

## Touches (`?` pour le menu)

* `Ctrl-G` tableau de bord (santé, ressources, cache des adresses, langues, top 10 des URL, erreurs d'Odoo) ; `1`–`9` choisissent son niveau ; `Ctrl-T` seulement ce qui a changé depuis le dernier affichage ; `Ctrl-C` arrêt et résumé de la session (qui inclut le nombre de membres de chaque groupe `RLQ*`).
* Réglages changés à la volée : `a` groupe accentué, `c` bip, `d`/`t` largeur de la colonne des noms, `e` exclure des IP, `H` période de santé, `i` cacher l'IP, `l` surligner des mots, `m` minimum, `M` tableau des modules installés avec tri, `L` derniers modules, `n` seulement les introuvables, `o` seulement les lignes contenant un texte, `r` rapport d'erreurs à copier-coller, `s` seulement les suspectes, `T` rapport périodique, `v` verbeux, `w` surveiller des URL, `C` sauvegarder les réglages changés dans le fichier de configuration.
* `S`/`I` dernières inscriptions aux sondages / événements (30 jours), `E` détail des erreurs, `D` diagnostic du site (pourquoi la page de maintenance s'affiche), `G` membres de chaque groupe `RLQ*`, `b` bannir les adresses recommandées.

## Latence : est-ce le disque ?

Toutes les 30 secondes, un échantillonneur léger lit les compteurs du noyau (aucune commande) : processeur, temps d'attente (PSI) du disque / du processeur / de la mémoire — le cgroup *du conteneur lui-même* dans un conteneur LXC —, et le % d'occupation des disques et l'attente par opération. Chaque requête Odoo (temps SQL + temps Python de sa ligne de journal) est classée dans l'heure où elle a eu lieu, « disque occupé » ou « disque calme ». Appuyer sur **P** (ou Ctrl-G au niveau 6 et plus) après quelques heures : le verdict dit si les disques ralentissent les requêtes (SSD justifiés), seulement par moments (démarrages, sauvegardes), ou pas du tout (SATA suffisant), avec le tableau par heure au niveau 8. Dans un conteneur, les compteurs des disques peuvent être partiels : lancer `host-perf-audit.py` sur l'hôte Proxmox pour les vrais disques.

## Règles de conception à connaître

* Une recherche lente ne retient jamais une recherche rapide : la voie rapide (ce serveur, une personne connue, l'équipe) ne fait aucun appel extérieur ; DNS, propriétaire et pays tournent dans des threads séparés. Les noms de personnes ne dépendent que de PostgreSQL (lecture seule, en cache).
* Odoo n'enregistre pas la fin d'une session : « connecté » signifie actif depuis moins de `--idle` minutes.
* L'heure d'un événement vient de la ligne du journal, jamais du fuseau horaire de la machine.
* Les journaux quotidiens en couleur vont dans `/var/log/app-log-live/` (root) ou `~/.local/state/app-log-live/` (droits 600, 30 jours ; `--log-dir`, `--log-keep-days`, `--no-log-file`).
* `--truncate` coupe chaque ligne affichée à 2 × la largeur du terminal (`$COLUMNS`), ou à N colonnes avec `--truncate N`, terminée par « … » : une ligne prend au plus deux lignes à l'écran. Le journal quotidien garde les lignes entières.
* « Qui est connecté maintenant » donne le nom de chaque compte SSH avec son nombre de sessions (`ana ×2, root ×1`, sftp compris) ; les groupes RLQ* s'affichent sur 4, 2 ou 1 colonne(s) selon la largeur du terminal.
* Touche **I** : inscriptions regroupées par événement, puis par billet, avec **le sondage de chaque billet** (comptes : confirmées, non terminées, sans sondage) ; une réponse à un autre sondage (celui de l'an dernier, un essai, un autre billet) est signalée, jamais comptée.
* Un courriel envoyé montre son destinataire et son sujet : « Courriel no 7573 envoyé à Ana Tremblay (a***n@…) — « sujet » — inscription … ».
* **Ctrl+C** pendant un programme lancé depuis le menu (nginx-log-audit.sh, web-monitor.py…) : une seule question, tout de suite.

## Options
{{HELP}}
