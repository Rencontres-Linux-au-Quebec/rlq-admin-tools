# system-hardening.sh - correctifs de sécurité, audit et intégrité des fichiers du système

Durcissement du système d'exploitation lui-même, où qu'il tourne : un **hôte Proxmox VE 9** (Debian 13), une **machine virtuelle** (Ubuntu 20.04 et plus, Debian 12 et plus) ou un **conteneur LXC** (Debian 12 et plus). Comme `nginx-hardening.sh`, il **vérifie seulement** par défaut ; `--update` applique.

```bash
system-hardening.sh                  # vérification seulement, ne modifie rien
sudo system-hardening.sh --update    # applique (paquets, configuration, règles, référence d'AIDE, minuteur quotidien)
sudo system-hardening.sh --baseline-update   # après des changements voulus (mises à jour, nouveaux modules Odoo) : nouvelle référence d'AIDE
system-hardening.sh --notify         # le sommaire quotidien, maintenant
sudo system-hardening.sh --rollback  # retire les fichiers écrits par --update (les paquets restent)
```

## Ce qu'il met en place

1. **unattended-upgrades** : les correctifs de sécurité de la distribution sont appliqués chaque jour (Debian Security, sécurité et ESM d'Ubuntu). Les listes de `50unattended-upgrades` sont d'abord vidées : rien d'autre n'est mis à jour tout seul. **Pas de redémarrage automatique** par défaut (`AUTOMATIC_REBOOT=no`) : le redémarrage coupe Odoo et les conférences BigBlueButton ; le programme signale quand un redémarrage est en attente (`/var/run/reboot-required`, ou un noyau plus récent installé que celui en marche). Sur un hôte Proxmox, seuls les correctifs de sécurité de Debian passent : les paquets de Proxmox se mettent à jour à la main (`apt full-upgrade`).
2. **auditd** (pas dans un conteneur LXC, voir plus bas) : règles étiquetées `rlq-*` - `rlq-sudo` (sudoers), `rlq-sudo-exec` (chaque `sudo` lancé par un vrai utilisateur), `rlq-ssh-keys` (`.ssh` de root et de chaque utilisateur), `rlq-sshd`, `rlq-cron`, `rlq-identity` (passwd, shadow, group), `rlq-pam`, `rlq-preload` (`/etc/ld.so.preload`), `rlq-systemd` (services), `rlq-apt` (sources des paquets). Plutôt que tout `/etc` (des milliers de changements sans gravité), ce sont les parties sensibles qui sont surveillées ; AIDE couvre l'intégrité de tout `/etc`. Pour lire les événements : `ausearch -k rlq-ssh-keys -i`.
3. **AIDE** : intégrité des fichiers. Les dossiers qui changent sans arrêt sont exclus (journaux, caches, PostgreSQL, Docker, enregistrements de BigBlueButton, filestore d'Odoo et `data_dir` de chaque configuration d'Odoo trouvée, stockage de Proxmox et `/etc/pve`) ; `AIDE_EXCLUDE` en ajoute d'autres. La base de référence est créée une fois (5 à 30 minutes), puis vérifiée chaque jour par la distribution (`dailyaidecheck.timer` ou `/etc/cron.daily/aide`).
4. **Sommaire quotidien par courriel** : `system-hardening-notify.timer` lance `--notify` chaque jour (`NOTIFY_TIME`, 07:30 par défaut). Le courriel passe par les réglages de courriel de la suite (`/etc/default/nginx-tools-mail.conf`, configurés par `nginx-hardening.sh --update --mail-setup`) : aucun serveur de courriel local n'est nécessaire. Un courriel n'est envoyé que s'il y a quelque chose à voir (correctifs installés, redémarrage en attente, différences d'AIDE, événements d'audit sensibles), ou chaque jour avec `NOTIFY_ALWAYS=yes`.

## Conteneurs LXC et hôte Proxmox

L'audit du noyau ne peut pas tourner dans un conteneur LXC non privilégié : le noyau appartient à l'hôte. Dans un conteneur, le programme met en place unattended-upgrades, AIDE et le sommaire quotidien, et indique que l'audit se fait sur l'hôte. Sur l'**hôte Proxmox**, `--update` écrit aussi des surveillances pour les fichiers sensibles de chaque conteneur **en marche** (vus dans `/var/lib/lxc/ID/rootfs`) : sudoers, `.ssh`, cron, passwd, shadow, sshd. Après le redémarrage d'un conteneur, relancer `--update` sur l'hôte pour que les surveillances suivent son nouveau montage (`AUDIT_WATCH_CONTAINERS=no` pour laisser les conteneurs de côté).

## Fichiers écrits

Seulement des fichiers qui lui sont propres, retirés par `--rollback` : `/etc/apt/apt.conf.d/52rlq-unattended-upgrades`, `/etc/audit/rules.d/60-rlq-hardening.rules`, `/etc/aide/aide.conf.d/99_rlq_exclusions`, `/etc/systemd/system/system-hardening-notify.service` et `.timer`. Aucun fichier de la distribution n'est modifié. Les paquets (`unattended-upgrades`, `auditd`, `aide`) et la base d'AIDE restent après `--rollback`.

## Options
{{HELP}}
