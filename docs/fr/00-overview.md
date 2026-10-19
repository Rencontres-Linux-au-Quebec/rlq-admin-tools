# Vue d'ensemble et concepts

*nginx-tools* est une suite de programmes en ligne de commande pour installer, auditer, surveiller et entretenir un serveur **nginx + Odoo** (et, avec le même moteur, un serveur **BigBlueButton**). Elle s'adresse aux administrateurs qui connaissent Linux (systemd, nginx, PostgreSQL, pare-feu) et Odoo (Community 18, installations de type ERPLibre).

## Les programmes

| Programme | Langage | Rôle | Root requis |
|---|---|---|---|
| `nginx-hardening.sh` | bash | audit/installation du serveur en 16 étapes : nginx, pare-feu, limites d'Odoo, fail2ban, HSTS, rétention des journaux, relais courriel | `--update` seulement |
| `nginx-log-audit.sh` | bash | rapport des journaux nginx : robots, refus, attaques, enquête sur une IP, bannissements | pour bannir |
| `sync-crowdsec-blocklist.sh` | bash | importe la liste communautaire CrowdSec dans deux ipsets du pare-feu | oui |
| `web-monitor.py` | python | orchestrateur : passage horaire, alertes, sommaires, `--apply` (une question par correction) | pour les corrections |
| `app-health-check.py` | python | santé de nginx + application (sondes, TLS, fichiers sensibles, DNS du courriel) | en partie |
| `app-log-check.py` | python | analyse du journal systemd d'Odoo (attaques de protocole, traces Python, bruit) | en partie |
| `app-log-live.py` | python | journal d'Odoo en temps réel avec noms, pays, bannissements et tableau de bord | en partie |
| `odoo-backup.sh` | bash | sauvegarde/restauration au format natif d'Odoo, rétention, copie distante, minuterie systemd | oui |
| `odoo-update-module.sh` | bash | met à jour des modules Odoo (`rlq_*` par défaut) service arrêté, redémarre et préchauffe | oui |
| `odoo-warmup.py` | python | préchauffe les caches d'Odoo après un redémarrage | non |
| `odoo-mail-retry.py` | python | liste et renvoie les courriels d'Odoo en état *exception* | oui |
| `odoo-chat-post.py` | python | crée les canaux/fils d'alerte Discuss, un compte robot restreint, et y publie des alertes | non |
| `odoo-docs.py` | python | publie cette documentation dans Odoo (wiki OCA `document_page` ou pages du site web) | non |
| `zip-versions.py` | python | versions contenues dans les archives livrées, comparaison avec l'installation | non |
| `host-perf-audit.py` | python | sur un hôte Proxmox (ou tout serveur Linux) : ce qui limite les performances — processeur, mémoire, disques, ZFS, réseau, invités — et si des disques SSD sont justifiés | pour un rapport complet |

Les composants partagés sont dans `apps/` (détection du profil, générateur de rapport, i18n, anonymiseur, RDAP/whois, cache d'IP, courriel…). Ils sont internes : ne pas les lancer directement, sauf `apps/_anonymiser.py` (un filtre).

## Prérequis

* Système de type Debian/Ubuntu avec systemd. BigBlueButton 2.7 sur Ubuntu 20.04 impose **Python 3.8** : le code évite les syntaxes plus récentes.
* `python3`, `bash`, `gawk` ou `mawk` ; recommandés : `geoip-bin` + `geoip-database` (pays des adresses en local), `fail2ban`, `ufw` ou `iptables`/`ipset`, `curl`.
* L'accès à PostgreSQL est en lecture seule via `runuser -u postgres -- psql` (c'est pourquoi tout ce qui touche la base d'Odoo exige root).

## Installation

```bash
cd /root/scripts
unzip -o nginx-tools.<VERSION>.zip && cp -r nginx-tools/* . && rm -rf nginx-tools
./nginx-hardening.sh --check          # audit, ne change rien
./nginx-hardening.sh --update         # installe/répare ce qui manque (sauvegarde les fichiers modifiés)
unzip -o nginx-tools-tests.<VERSION>.zip && nginx-tools-tests/run-all.sh
```

Déployez toujours l'archive des programmes et celle des tests **ensemble** (même MAJEUR.MINEUR). `zip-versions.py` vérifie la concordance des noms et du contenu.

## Conventions communes à tous les programmes

**Première ligne.** Chaque exécution affiche d'abord `NOM vVERSION` (même `--help`). Les programmes qui produisent des données ou un flux l'écrivent sur la sortie d'erreur.

**Versions.** `MAJEUR.MINEUR.AAAAMMJJ.HHMMSS` (heure locale). `--version` l'affiche ; `--changelog` montre `doc/NOM.changelog.txt`, la plus récente d'abord, numéros de version en couleur dans un terminal seulement.

**Configuration en couches.** `/etc/default/NOM.conf` est lu d'abord, puis `~/.NOM.cfg` s'il existe (le dernier l'emporte), puis la ligne de commande (prioritaire). `-c/--config FICHIER` lit ce fichier **seul** et il doit exister. Les fichiers sont *analysés, jamais exécutés* ; seules les clés connues sont retenues. Au démarrage, chaque programme affiche les fichiers lus, avec leur date de modification et un sommaire d'une ligne des options importantes. Un fichier par défaut est créé au premier lancement à partir de `doc/NOM.conf.example`. Les clés communes (`ANONYMIZE`, `LOG_KEEP_DAYS`, langue…) sont dans `/etc/default/app-default.conf`.

**Langue.** Les programmes parlent anglais et français (autre langue : ajouter `lang/NOM.XX.po`, voir *Tests, traduction et contribution*). Priorité : `--lang` > `NGINX_TOOLS_LANG` > la variable du programme (`WEB_MONITOR_LANG`…) > `LANGUAGE=` du fichier > l'environnement comme gettext : `LANGUAGE` de GNU (`fr_CA:fr:en`, sans effet sous la locale `C`), puis `LC_ALL`, `LC_MESSAGES`, `LANG` — la première définie l'emporte : un `LC_ALL` oublié masque `LANG`. La ligne *Options* du démarrage dit quel réglage a décidé : `--lang en (LC_ALL=C.UTF-8 ; LANG=fr_CA.UTF-8 ignorée(s))`.

**Options en ordre alphabétique.** L'aide liste les options par ordre alphabétique ; un test le vérifie.

**`--report-err`.** Affiche en fin d'exécution un rapport à copier-coller : programme, version, commande, serveur, système, durée, code de sortie, versions de toute la suite, échecs, avertissements, recommandations. Les secrets sont masqués ; couleurs et questions sont désactivées. C'est la façon préférée de signaler un problème.

**Lecture seule par défaut.** Les programmes qui modifient le système le disent, demandent confirmation et sauvegardent les fichiers qu'ils modifient. `--yes` supprime les questions quand c'est pertinent.

**`--verbose`** est transmis à tous les programmes qu'un programme lance : chaque commande externe devient visible.

**Progression.** Un programme long affiche une ligne par étape avec le temps écoulé, sur la sortie d'erreur, seulement dans un terminal ou avec `--verbose` (jamais dans un tube ni une tâche planifiée).

**Avis de droits.** Un programme de lecture lancé sans root affiche « Droits limités (pas root) : … » et dit ce qui sera incomplet (le taire : `NGINX_TOOLS_AVIS_ROOT=0`). Voir *Qui doit être root*.

## Sortie anonymisée (`--anonymize`)

Tout programme accepte `--anonymize` (ou `ANONYMIZE=1`, `NGINX_TOOLS_ANONYMIZE=1`). Les adresses IP deviennent `IP-4f2a9c`, les courriels `usager-9c1e03@anonyme.invalid`, les identifiants `ID-3b7d11`, les jetons/mots de passe/témoins `***`. Les pseudonymes sont **stables** (HMAC-SHA256 avec un sel secret propre à la machine, dans `/etc/default/nginx-tools-anon.salt` ou `~/.nginx-tools-anon.salt`, droits 600) : un même visiteur garde son pseudonyme d'un rapport à l'autre, ce qui permet de partager des extraits sans danger. Boucle locale, masques et numéros de version restent intacts. Le filtre **échoue fermé** : s'il est demandé mais introuvable, le programme s'arrête au lieu d'afficher des données en clair. `apps/_anonymiser.py --pseudonyme VALEUR` indique le pseudonyme d'une valeur connue. Limite : seuls les motifs reconnus sont masqués (un nom de personne écrit en texte libre ne l'est pas).

## Listes d'adresses de confiance

Les adresses propres à une installation vivent **hors du code**, dans `/etc/default` :

* `nginx-tools-white-list.conf` — adresses de confiance : jamais bannies, accès aux sites de développement/laboratoire.
* `nginx-tools-ip-location.conf` — lieux nommés (`# Université [partagée] [protégée]`), aucun accès accordé.

`nginx-hardening.sh --update` génère les fragments nginx à partir de ces fichiers (`team-ips-geo.conf`, `team-ips-allow.conf`) ; ne jamais les modifier à la main.

## Données conservées par la suite

* `/var/lib/nginx-tools/ip-cache.sqlite` (droits 600) : nom DNS (30 jours), propriétaire du bloc et pays (90 jours) ; un échec de recherche n'est jamais mémorisé ; les adresses non revues depuis 180 jours sont purgées (une adresse IP est un renseignement personnel). `--no-cache`, `NGINX_TOOLS_IP_CACHE=off|chemin`.
* Les journaux propres aux programmes (`app-log-live`, `web-monitor`, `odoo-update-module`) sont gardés `LOG_KEEP_DAYS` jours (180 par défaut, 0 = jamais effacés).
