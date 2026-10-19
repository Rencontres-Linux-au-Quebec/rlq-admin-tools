# host-perf-audit.py — ce qui limite les performances d'un hôte Proxmox

À lancer **sur l'hôte Proxmox** (dans un conteneur, les vrais disques ne sont pas visibles). Il mesure pendant une durée choisie — d'une minute à une journée entière — puis donne un verdict par ressource, la réponse à « des disques SSD sont-ils justifiés ? » et les réglages à changer.

```bash
host-perf-audit.py                                  # une minute, un échantillon toutes les 5 s
host-perf-audit.py --duration 4h                    # les heures chargées : un échantillon toutes les 60 s
host-perf-audit.py --duration 24h --csv /root/perf.csv   # une journée entière, chaque échantillon dans un fichier pour tableur
host-perf-audit.py --apply                          # rapport, puis les réglages sans risque un par un
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
