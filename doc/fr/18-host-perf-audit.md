# host-perf-audit.py - ce qui limite les performances d'un hôte Proxmox

À lancer **sur l'hôte Proxmox** (dans un conteneur, les vrais disques ne sont pas visibles). Il mesure pendant une durée choisie - d'une minute à une journée entière - puis donne un verdict par ressource, la réponse à « des disques SSD sont-ils justifiés ? » et les réglages à changer.

```bash
host-perf-audit.py                                  # une minute, un échantillon toutes les 5 s
host-perf-audit.py --duration 4h                    # les heures chargées : un échantillon toutes les 60 s
host-perf-audit.py --duration 24h --csv /root/perf.csv   # une journée entière, chaque échantillon dans un fichier pour tableur
host-perf-audit.py --apply                          # rapport, puis les réglages sans risque un par un
host-perf-audit.py --export-ai                      # rapport, puis rapport et état brut de l'hôte dans un fichier Markdown à envoyer pour vérification
```

## Ce qui est mesuré

* **Processeur** : % d'occupation, iowait, steal (temps pris par un autre hyperviseur), charge, et le temps d'attente d'un cœur (PSI *cpu*).
* **Mémoire** : mémoire disponible, swap, temps d'attente de la mémoire (PSI *memory* : récupération, swap), taille, maximum et taux de réussite de l'ARC de ZFS.
* **Disques** : pour chaque disque (HDD, SSD ou NVMe, modèle) : % du temps occupé, opérations et Mo par seconde, attente par lecture et par écriture (95e centile), et le temps d'attente de tout l'hôte pour les disques (PSI *io* : *some* = au moins une tâche a attendu, *full* = toutes). Santé SMART quand `smartctl` est installé.
* **ZFS** : pour chaque pool, % utilisé, fragmentation, état, scrub / resilver en cours, périphériques special / log / cache, `ashift`, attentes moyennes depuis l'importation du pool (écritures synchrones comprises) ; propriétés des datasets (compression, atime, sync, recordsize).
* **Réseau** : reçu / envoyé par interface, erreurs et pertes.
* **Invités** : pour chaque conteneur et VM en marche (cgroup v2, nommés d'après `/etc/pve`) : processeur, mémoire, débit disque et temps d'attente du disque *à l'intérieur* de l'invité.

Le programme est léger par conception : un échantillon lit quelques petits fichiers de `/proc` et `/sys` (aucune commande), le programme baisse sa propre priorité (nice 10, classe d'E-S « idle »), les quelques commandes (`zpool`, `zfs`, `pveversion`, `smartctl`) ne tournent qu'une fois, et le rapport indique le temps processeur que la mesure a coûté. **Ctrl-C** pendant la mesure l'arrête et donne quand même le rapport sur les échantillons déjà pris.

## Des disques SSD sont-ils justifiés ?

* **Oui** quand les HDD sont un goulot mesuré : des tâches attendent le disque une bonne partie du temps, ou un disque est occupé plus de 85 % du temps (95e centile) avec des opérations lentes. Le rapport donne d'abord les étapes moins chères : un ARC plus grand si la RAM le permet, un SSD *special* en miroir (métadonnées et petits blocs), un SSD *log* (SLOG) pour les écritures synchrones comme les validations de PostgreSQL, puis des SSD pour le pool de l'invité le plus actif.
* **Pas encore** quand les disques ne ralentissent qu'aux pointes : mesurer sur une journée entière, sauvegardes comprises.
* **Non** quand les disques ne sont pas une limite : la lenteur des premiers chargements après un redémarrage vient du cache froid, pas du type de disque.

## Réglages

Chaque suggestion a une priorité (HAUTE / MOYENNE / FAIBLE). Avec `--apply`, celles qui sont **sans risque et réversibles** sont proposées une par une (`--yes` : sans question) : `compression=lz4` et `atime=off` d'un dataset ZFS, `zfs_arc_max` (maintenant, dans `/etc/modprobe.d/` et l'initramfs), `vm.swappiness` (maintenant et dans `/etc/sysctl.d/`). Les conseils matériels et les options des disques des VM (bus, `iothread`, cache, type de CPU) sont expliqués, jamais modifiés : ils demandent une décision et un redémarrage de la VM.

## Options
{{HELP}}

## Espace, sauvegardes et export (1.10)

* **Espace des pools** : espace libre, instantanés, plus gros datasets, et ce qui est placé directement dans un dataset parent (par exemple `/var/lib/vz/dump`).
* **Disque d'un conteneur presque plein** : nommé avec son point de montage et la commande `pct resize`.
* **Sauvegardes (vzdump)** : nombre, taille, rétention, tâches planifiées et heures des sauvegardes des 3 derniers jours, à comparer avec les heures lentes des sites.
* **`--export-ai`** : écrit le rapport et l'état brut de l'hôte dans `/var/lib/host-perf-audit/export-ai-HÔTE-DATE.md` (mode 600, mots de passe masqués). Clé `EXPORT_AI` dans la configuration.

## Santé, intérieur des invités et alertes (1.12)

```bash
host-perf-audit.py --health --inside            # vérification en quelques secondes, sans mesure
host-perf-audit.py --install-timer              # la même chaque heure, avec une alerte par courriel quand il y a du nouveau
```

* **`--health`** : compteurs SMART de chaque disque comparés à l'exécution précédente (secteurs réalloués, en attente, non corrigibles), état et erreurs des pools ZFS, RAID, messages du noyau, espace, sauvegardes. Code de sortie 0, 1 (à surveiller) ou 2 (problème).
* **`--inside`** : regarde dans chaque invité, en lecture seule : `pct exec` pour un conteneur, l'agent invité QEMU pour une VM (`qm set ID --agent enabled=1`, `qemu-guest-agent` dans la VM, puis arrêt et démarrage de la VM). Conteneurs Docker qui redémarrent en boucle, services en échec, journal qui déborde, disques pleins, processus qui écrivent le plus. Aucun répertoire partagé n'est nécessaire.
* **`--notify`** : journal système et courriel (réglages SMTP d'`app-health-check.py`, sinon courrier local à root), seulement quand il y a du nouveau, rappel après 24 heures.
* **Commandes à lancer** : chaque rapport finit par les commandes à copier, coller, et dont la sortie est à envoyer.

## Configuration des conteneurs et des VM (1.13)

Au démarrage, le programme vérifie la configuration de chaque invité (`/etc/pve`, lecture seule) et annonce les **enjeux majeurs** : point de montage d'un conteneur absent des sauvegardes (`backup=1`), disque en `cache=unsafe`, invité sans `onboot`, invité hors de toute tâche de sauvegarde, mémoire promise au-delà de la machine. La liste complète (à améliorer, remarques) est à la fin du rapport, avec les commandes `pct set` / `qm set` à copier.

Depuis la 1.14, chaque invité en ordre a sa ligne `[OK]` avec ce qui a été vérifié, et les instantanés de plus de 60 jours sont listés avec la place que leur suppression libère (calculée par `zfs destroy -n`, sans rien détruire) et les commandes `pct delsnapshot` / `qm delsnapshot`.

## Commandes lancées par le programme (1.15)

À la fin du rapport et de `--health`, chaque commande est marquée **`[lecture]`** (le programme la lance lui-même et montre sa sortie dans la section « COLLECTÉ ») ou **`[modif.]`** (elle modifie quelque chose : le programme la propose une à une et ne la lance qu'après « y », en root, dans un terminal). `--no-collect` liste seulement les commandes. Les sauvegardes placées dans un sous-dossier que Proxmox ne voit pas (sa rétention ne s'y applique jamais) sont signalées, avec la liste des fichiers à supprimer au-delà de `keep-last` et la place libérée.

## Commande dans les invités (1.17)

```bash
host-perf-audit.py --guest-run --guests 101,104,105,433
```

Lance `/opt/rlq-admin-tools/nginx-hardening.sh --update` (ou `--guest-command`) dans chaque invité, l'un après l'autre, après avoir vérifié que le programme y existe et après une confirmation (`--yes` : sans question). Les sorties sont gardées dans `/var/lib/host-perf-audit/guest-runs/DATE/`, avec un `report.md` à envoyer pour analyse. Clés `GUESTS` et `GUEST_COMMAND` dans la configuration. Sans terminal dans l'invité, `nginx-hardening.sh --update` n'applique pas les étapes qui demandent une confirmation (0f, configuration nginx générique ; 9b bis, filtre nginx-sqli) : `--guest-command "/opt/rlq-admin-tools/nginx-hardening.sh --update --yes"` les applique (sauvegarde, puis retour en arrière si `nginx -t` ou fail2ban refusent).

## Copie de la suite dans les invités (1.18)

```bash
host-perf-audit.py --guest-sync --guest-run --guests 101,104,105,433
```

Copie le dossier de la suite de l'hôte (celui de ce programme, ou `--sync-source`) dans `/opt/rlq-admin-tools` de chaque invité, après confirmation. L'ancienne copie reste en `/opt/rlq-admin-tools.previous`. Un invité qui porte le dossier source lui-même n'est jamais remplacé. Avec `--guest-run`, la commande est lancée ensuite ; le rapport s'appelle `report-HÔTE-DATE.md`.

Depuis la 1.20, la copie vers une VM affiche sa progression en %, et `--sync-git all|containers|none` (clé `SYNC_GIT`) choisit où le dossier `.git` est copié : par défaut dans les conteneurs seulement, car une VM reçoit la copie en morceaux par son agent.
