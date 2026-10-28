# Contexte du projet - à lire EN PREMIER dans une nouvelle discussion

Instantané du 2026-10-02. Il remplace le recours à l'historique d'une longue discussion. **La référence reste le code** (archives
`nginx-tools.zip`, `nginx-tools-tests.zip`, `nginx-odoo-config.zip`) **et le rapport `--report-err`** du programme concerné : en cas de désaccord,
ils ont raison et ce fichier est périmé.

## 1. Démarrer une discussion (et économiser des jetons) - Vérifier d'abord quelles archives sont les plus récentes : `zip-versions.py ~/Téléchargements` (section « ARCHIVES À
  JOINDRE »).
- Joindre `nginx-tools.<version>.zip` et `nginx-tools-tests.<version>.zip` (et `nginx-odoo-config.<version>.zip` si la configuration nginx est concernée - voir la section 10 : ne JAMAIS l'envoyer seul), écrire « lis
  doc/CONTEXTE.md », puis coller le **rapport `--report-err`** du programme concerné - pas la sortie complète.
- Un thème par discussion, dans le même projet (la mémoire du projet est partagée). Regrouper plusieurs demandes dans un message.
- Suite complète (`nginx-tools-tests/run-all.sh`) avant chaque déploiement ; des tests ciblés suffisent entre deux. Ne coller d'une sortie de
  `run-all.sh` que les lignes `[ÉCHEC]` et `FAIL`.

## 2. Les serveurs (à confirmer : ce que l'utilisateur a dit, pas ce qui a été mesuré)

| Serveur | Rôle |
|---|---|
| Odoo PROD (hôte `odoo18`, `www.rencontres-linux.quebec`) | Odoo 18 CE (ERPLibre, `erplibre.service`) dans un conteneur LXC Proxmox, nginx devant ; 13 workers |
| Odoo DEV (`odoo-dev.rencontres-linux.quebec`) | même pile, restreint par IP (`deny all` hors liste de l'équipe) ; les refus « access forbidden by rule » y sont NORMAUX |
| BigBlueButton PROD (`bbb3.services-conseils-linux.org`) | BBB (2.7 d'après l'utilisateur), Ubuntu 20.04 -> **Python 3.8** ; TLS terminé par **HAProxy** ; Greenlight |
| BigBlueButton DEV (`bbb30.dev.services-conseils-linux.org`) | BBB 3.0 ; mêmes règles |

Adresses propres à l'installation : **hors des archives** (publiables sur GitHub sans données personnelles), dans `/etc/default`, lues par `apps/_listes.py` et `apps/_listes.sh` :
`nginx-tools-white-list.conf` (LISTE BLANCHE : adresses de confiance, jamais bannies, accès à DEV et LAB ; lue seulement dans /etc/default) et `nginx-tools-ip-location.conf` (LIEUX : un
nom pour une plage - `# Université  [partagée] [protégée]` ; aucun accès ; lu aussi dans `~/.nginx-tools-ip-location.conf`). nginx en reçoit deux fichiers GÉNÉRÉS par `nginx-hardening.sh` (étape 12) :
`snippets/team-ips-geo.conf` et `snippets/team-ips-allow.conf` (liste blanche seulement) - ne jamais les modifier à la main. Les adresses de la liste blanche et des lieux `[protégée]` ne sont
jamais bannies (fail2ban `ignoreip`, liste CrowdSec, `nginx-log-audit.sh`). `nginx-hardening.sh --update` crée ou migre ces fichiers (l'ancienne `apps/team-ips.list` est copiée puis renommée `.migre`).

## 3. Conventions de l'utilisateur (à respecter pour TOUT programme) - **Version** `MAJEUR.MINEUR.AAAAMMJJ.HHMMSS` : MINEUR +0.1 à CHAQUE changement demandé, MAJEUR seulement sur demande ou rupture de
  compatibilité ; date et heure locale (America/New_York) de la modification. `__version__` / `SCRIPT_VERSION` ; `--version` dynamique.
- **Journal** `CHANGELOG.md` à la racine du dépôt : une section `## <programme>` par programme (chemin depuis la racine pour les modules `apps/`), version la plus récente EN PREMIER : titre, motif,
  détail, bugs corrigés (symptôme, diagnostic, correction), garde-fous, vérifications, action requise. `--changelog` : numéros de
  version en couleur (seulement dans un terminal), tube fermé proprement. En-tête du programme : une ligne par version.
- **Tout en français** (commentaires, messages, journal) sauf les noms de programmes et d'options. **Options de l'aide par ordre
  alphabétique** (nom long, sans les tirets) ; un test le vérifie.
- **Configuration** : lire `/etc/default/<programme>.conf`, PUIS `~/.<programme>.conf` s'il existe (extension `.conf`, jamais `.cfg` : un ancien fichier personnel en `.cfg` est renommé
  automatiquement par apps/_config.py `migrer_ancien` et apps/_i18n.sh `config_migrer_ancien`, 2026-10-20) (le dernier l'emporte), PUIS la ligne de
  commande (prioritaire) ; `--config` = ce fichier seul, qui doit exister. **Toujours afficher** quels fichiers sont lus, avec un
  sommaire d'une ou deux lignes des options importantes. Créer une configuration par défaut au premier lancement.
  Seuls `odoo-backup.sh` et `app-health-check.py` ont une configuration ; `nginx-hardening.conf` dans `/etc/default` est un fichier d'ÉTAT.
- **`--report-err`** dans chaque programme : rapport à copier-coller en fin d'exécution (programme, version, commande, serveur, système,
  durée, code de sortie, contexte, versions de toute la suite, échecs, avertissements, recommandations) ; mots de passe masqués ;
  désactive couleurs et questions interactives. C'est ce que l'utilisateur colle dans la discussion.
- **Pas de commande à taper dans une recommandation** : le programme fait lui-même les vérifications (nginx -T, enquête,
  essai réel d'une URL, robots.txt...) et propose les corrections en fin d'exécution, avec confirmation (`--apply --yes` : sans question).
  L'assistant n'a AUCUN accès aux serveurs : ce qu'il peut faire lui-même, c'est analyser les archives jointes et le rapport.
- **Noms des archives** : nom du programme PUIS version SANS la date (MAJEUR.MINEUR), ex. `nginx-tools.1.1.zip`,
  `nginx-tools-tests.1.61.zip` (comme `rlq_survey_report.18.0.1.90.0.zip`) ; le répertoire de premier niveau, lui, SANS version
  (`nginx-tools/`, `nginx-tools-tests/`, `nginx-odoo/`) - jamais un nom générique comme `tests.zip`, qui écraserait le `tests/` d'autres
  programmes. Version de l'archive `nginx-tools` : `doc/nginx-tools.version` (complète, avec la date ; MINEUR +0.1 à chaque livraison) ;
  `nginx-tools-tests` : version de `run-all.sh` ; `nginx-odoo-config` : fichier `VERSION` à la racine de `nginx-odoo/` (MINEUR +0.1 à chaque modification de la configuration, copié à l'identique dans `nginx-tools-tests/nginx-odoo/`).
  `zip-versions.py` vérifie que le nom et le contenu concordent sur MAJEUR.MINEUR.
- **`--verbose` est transmis à TOUS les programmes qu'un programme lance** (et à leurs composants `apps/`) : chacun affiche alors ses propres
  commandes externes. Tout nouveau lancement d'un programme de la suite par un autre doit ajouter `--verbose` quand il est actif.
- **Un programme long dit ce qu'il fait** : une ligne par étape avec le temps écoulé (un journal lu à la fois, une IP examinée à la fois),
  sur la sortie d'erreur, dans un terminal ou avec `--verbose` - jamais dans un tube ni une tâche planifiée. Pas de lecture inutile.
- **Les tests sont étiquetés par environnement** : chaque `test_*.py` porte `ENVIRONNEMENT = "commun" | "odoo" | "bbb"` ; `run-all.sh`
  détecte le serveur (ou `--app NOM`) et n'exécute que les modules communs et ceux de SON environnement (`--all-environments` : tous ;
  `--list` : voir sans exécuter). Un nouveau module de test DOIT porter son étiquette (un test le vérifie).
- **La PREMIÈRE ligne de toute exécution - même `--help`, `--changelog`, une option inconnue - est « NOM vVERSION »** (`--version` n'affiche que la version, une seule
  ligne). Bash : après le hook `--report-err` (qui relance le programme : sinon deux en-têtes). Programmes seulement : les composants `apps/` sont internes, leur sortie est
  lue par d'autres programmes. Sortie de DONNÉES redirigeable (`nginx-log-audit.sh --export-bans`) et flux (`app-log-live.py`) : l'en-tête va sur la sortie d'erreur.
  Un test (`EnTeteDeVersion`) le vérifie pour les dix programmes.
- **`geoip-bin` est RECOMMANDÉ, pas facultatif** : sans lui, `app-log-live.py` cherche le pays de chaque adresse sur Internet (rdap.org). `nginx-hardening.sh` (étape 14) le vérifie et
  l'installe avec `--update` (avec `geoip-database`) ; `web-monitor.py` le recommande et propose l'installation ; le programme vérifie d'abord que le paquet existe dans les dépôts
  (`apt-cache policy`) : sur une distribution récente (Debian 13...) il peut manquer.
- **Aucune donnée personnelle dans les archives** (objectif : publier `nginx-tools` et ses tests sur GitHub ; la configuration nginx reste privée) : adresses, noms, lieux vivent dans
  `/etc/default/nginx-tools-*.conf` (noms avec des TIRETS partout), jamais dans le code ni dans `apps/`. `doc/nginx-tools-*.conf.example` : modèles livrés. Les profils `apps/odoo.conf`
  et `apps/bbb.conf` restent livrés (rien de personnel) ; leurs surcharges facultatives iront dans `/etc/default/nginx-tools-odoo.conf` et `nginx-tools-bbb.conf` (phase C, à faire).
  Reste à faire (phase D) : remplacer les adresses, noms de domaine et noms d'hôtes réels dans les tests, la documentation et les journaux ; test de publication (liste de termes
  personnels HORS dépôt) ; garder `CONTEXTE.md` hors du dépôt ; nettoyer AVANT le premier commit (l'historique Git garde tout).
- **Cache permanent des adresses** (`apps/_cache_ip.py`, SQLite, `/var/lib/nginx-tools/ip-cache.sqlite`, droits 600) : nom DNS (30 j ; « aucun nom » 3 j), propriétaire du bloc et pays (90 j) ; un ÉCHEC de recherche n'est
  JAMAIS mémorisé ; purge des adresses non revues depuis 180 jours (vie privée : une adresse IP est un renseignement personnel) ; `--no-cache`, `NGINX_TOOLS_IP_CACHE=off|chemin`. Les tests le désactivent (`off`).
- **« ISP » est un mot à ne plus employer** : l'information est le PROPRIÉTAIRE du bloc d'adresses d'après RDAP (« Nom (org) » = organisation enregistrée ; « NOM (réseau) » = nom technique du réseau). Pas forcément un fournisseur d'accès.
- **Courriels non envoyés** (`app-log-check.py`, sommaire et section [5]) : 452 « Maximum number of messages per session » (-> `mail.session.batch.size` plus petit), 503 « Multiple MAIL commands » (cascade du 452), 550 « not allowed to send emails as »
  (-> serveur sortant avec « Filtre De », `mail.default.from`, `mail.catchall.domain`). Le programme DIAGNOSTIQUE (lecture seule) et ne modifie jamais Odoo : une écriture directe en SQL ne vide pas le cache des paramètres d'Odoo.
- **odoo-mail-retry.py** : liste des courriels en « Échec d'envoi » (TITRE, date, destinataires masqués, cause transitoire / PERMANENTE) puis menu de renvoi [t] [l] [c] [N] ; « renvoyer » = remettre l'état à « En attente »
- **odoo-warmup.py** (1.0) : préchauffe le cache d'Odoo après un redémarrage (pages publiques + assets ; administration avec un utilisateur dédié et une clé d'API en fichier 0600 : client web, menus, get_views des modèles de MODELS, répétés en parallèle pour toucher plusieurs workers). `--systemd-install --service UNITE` : fichier .d avec ExecStartPost=-+systemd-run --no-block (n'allonge pas le démarrage d'Odoo). Configuration /etc/default/odoo-warmup.conf puis ~/.odoo-warmup.conf.
  (comme « Réessayer »), Odoo envoie par sa tâche planifiée ; seule écriture du projet dans la base Odoo, gardée par `state = 'exception'` et consignée dans `/var/lib/nginx-tools/mail-retry.log`.
- **Schéma Odoo** : `mail.mail` hérite de `mail.message` (`_inherits`) : le SUJET est dans `mail_message.subject`, pas dans `mail_mail` (erreur corrigée en 1.3 de `_odoo_db.py` ; un simulateur de test ne peut pas la voir : vérifier
  les noms de colonnes contre le vrai schéma).
- **app-log-live.py, affichage** : nom (qui remplace l'adresse) sur AU MOINS 42 caractères (1.10), jamais tronqué ; premier champ (logger) des lignes SANS adresse sur 42 ; VIDÉO INVERSE : URL suspect (sans couleur), URL en 5xx (rouge) ou 4xx (jaune),
  adresse de la liste blanche (blanc) ou des lieux (gris). `rendre()` retourne `(nom, parties, brut, categorie)`. Les motifs suspects sont dans `SUSPECT_RE` (même esprit que `SENSITIVE_RE` de nginx-log-audit.sh : pas de source commune, à garder cohérents).
- **app-log-live.py 1.7** : suspect en vidéo inverse MAGENTA ; `[banni : fail2ban|CrowdSec]` (fail2ban-client + ipsets `crowdsec-blocklist-v4/-v6`, « nomatch » = exception, relus toutes les 60 s) ; `--slow` (5 s) ; `--only`
  (répétable) et `--suspect` ; résumé de la session à Ctrl-C ou `--summary`. Les tests simulent fail2ban-client et ipset (jamais les vrais).
- **Fichier de configuration créé au premier démarrage** (apps/_config.py `creer_par_defaut`, apps/_i18n.sh `config_creer_defaut`, odoo-mail-retry via _config) : copie de `doc/PROGRAMME.conf.example` (toutes les options en commentaire + options de la ligne de commande seulement) dans `/etc/default/PROGRAMME.conf` (root) ou `~/.PROGRAMME.conf` ; rien avec `--help/--version/--changelog/-c` ni `NGINX_TOOLS_CONFIG_CREER=0` (tests) ; app-health-check.py garde son `--create-config`, odoo-backup.sh son propre fichier.
- **app-log-live.py 1.28, tableau de bord à 9 niveaux** : `--level N` / `LEVEL=` (1 = verdict, 5 = l'essentiel, 9 = tout, défaut) ; touches 1 à 9 à la volée, niveau gardé pour Ctrl-G/Ctrl-T/résumé final ; les problèmes restent visibles dès le niveau 1.
- **app-log-live.py 1.11, tableau de bord** : nom sur 45 caractères par défaut (`--dns-max [N]` : largeur sans couper, 20 sans valeur ; `--dns-max-truncate [N]` : coupe à N avec « ... », 32 sans valeur) ; pays AVANT l'adresse
  (`CA 11.191.124.32`, colonne de 18) ; GET aligné (« GET  » avec 2 espaces, websocket `longpolling` compensé, date ISO redondante retirée) ; légende des chiffres après le code HTTP, couleurs si SQL >= 300 / taille >= 1 Mo ;
  **Ctrl-G** = tableau de bord (santé [OK] [ATTN] [FAIL] avec détail, CPU / mémoire / E-S, cache des adresses, langues EN FR ES, top 10 URLs, erreurs d'Odoo), **Ctrl-T** = changements depuis le dernier affichage, `--no-keys` ;
  `--health MIN` = alerte automatique seulement s'il y a un problème ; **journal quotidien** avec couleurs (`less -R`) dans `/var/log/app-log-live/` (root) ou `~/.local/state/app-log-live/` (droits 600, 30 jours,
  `--log-dir`, `--log-keep-days`, `--no-log-file`, `APP_LOG_LIVE_LOG_DIR=off`) ; adresse d'un lieu : « Personne | Lieu » ; pays aussi pour l'équipe ; présence en colonnes avec date. Les tests mettent `APP_LOG_LIVE_LOG_DIR=off`.
  Tests : les listes (`/etc/default/nginx-tools-*.conf`) sont isolées ; `run-all.sh` signale les fichiers RÉSIDUELS d'une ancienne archive (`apps/team-ips.list`...) : extraire chaque archive dans un dossier vide.
- **app-log-live.py 1.8, présentation compacte** : pas de « : » après le programme (lignes structurées d'Odoo) ni après le logger ; colonne d'adresse SANS crochets ni virgule, pays AVANT l'adresse « CA 11.191.124.32 » (18 caractères depuis la 1.10, `--hide-ip` : 2) ; « - » retiré après l'adresse
  (identité RFC 1413 et utilisateur HTTP, toujours « - » dans Odoo ; gardé si un vrai utilisateur) ; nom et logger sur 42 caractères (1.10) ; un espace de plus après GET / PUT pour aligner les URL sur POST. Adresses citées dans un message et lignes BBB : crochets conservés (« nom [CA adresse] »).
- **Requêtes de navigateurs sur des fichiers absents** (`/apple-touch-icon.png`, `/apple-touch-icon-precomposed.png`, `/favicon.ico`) : demandées automatiquement par Safari / iOS / Android pour l'icône d'écran d'accueil ; sans
  conséquence de sécurité ; chaque 404 coûte une page Odoo complète (~0,3 s). FAIT (nginx-odoo-config 1.2) : `location` de `_odoo-common.conf` qui réécrit EN INTERNE vers `/web/image/website/1/app_icon/180x180` ; à tester sur DEV (`nginx -t`, `curl -sI`) avant PROD.
- **Couleurs en vidéo inverse** : ne jamais compter sur `7;9x` (inverse d'un gris/noir du thème : noir sur noir chez Étienne). Fond ET texte explicites (liste blanche `107;30`, lieux `48;5;245;30` ou `47;30`).
- Vocabulaire : jamais « sondage » (dire « tentative d'accès », « recherche de fichiers sensibles »).
- Sortie en couleur : `[OK]` vert, `[SKIP]` et `[ATTN]` jaunes, `[FAIL]`/`[ERR...]` rouges - SEULEMENT dans un terminal.

## 4. Les programmes (versions au 2026-10-02)

| Programme | Version | Rôle |
|---|---|---|
| `nginx-hardening.sh` | 2.30.20261011.181500 | Installation et audit du serveur en 16 étapes (nginx, pare-feu, Odoo, fail2ban, HSTS, rétention des journaux, adresses de l'équipe, courriel, geoip-bin, byobu, appels d'Odoo vers son nom public) ; `--check` (défaut) ou `--update` |
| `nginx-log-audit.sh` | 2.30.20261011.172500 | Audit des journaux nginx (progression affichée) : robots, refus, attaques, enquête sur une IP (avec son fournisseur d'accès, RDAP), bannissements (`--ban`, `--unban-check`, `--export-bans`...) |
| `sync-crowdsec-blocklist.sh` | 1.20.20261010.215000 | Liste communautaire CrowdSec -> deux ipsets bloqués au pare-feu (cron) ; adresses de l'équipe jamais bloquées |
| `odoo-backup.sh` | 1.12.20261010.215000 | Sauvegarde et restauration d'Odoo au format natif (.zip importable par la page d'Odoo, ou .tar.xz), rétention, copie `REMOTE`, plusieurs heures par jour |
| `odoo-update-module.sh` | 1.0.20261014.110643 | Met à jour les modules `rlq_*` (service arrêté, `-u ... --stop-after-init --no-http --workers=0 --max-cron-threads=0` avec délai maximal) puis redémarre Odoo par systemd, avec contrôle du journal, du service et du port ; `--dry-run`, `--backup` |
| `app-health-check.py` | 2.19.20261010.215000 | Vérification de santé nginx + application (sonde `/web/health`, pages, TLS, fichiers sensibles refusés, courriel : `--check-email-dns`, `--test-email`) |
| `app-log-check.py` | 2.15.20261010.215000 | Analyse du journal systemd d'Odoo (attaques de protocole, traces Python, bruit connu dont les refus de droits par utilisateur) ; `--by-hour` : problèmes par heure et par jour, pages en erreur, diagnostic de « Session expired » |
| `web-monitor.py` | 2.49.20261011.144500 | Orchestrateur : passage horaire (timer), alertes, `--summary` (trafic, blocages, connexions, recommandations VÉRIFIÉES par le programme), `--apply` (corrections faites par le programme, avec confirmation), `--list-users`, bannissements |
| `zip-versions.py` | 1.7.20261010.215000 | Versions contenues dans les archives (sans extraction), les nôtres et celles de tout autre programme (manifeste, CHANGELOG...) ; cohérence archive de tests <-> programme ; archive la plus récente de chaque type, à joindre ; `--installed` : comparaison avec le serveur |
| `app-log-live.py` | 1.96.20261022.083937 | Journal d'Odoo en TEMPS RÉEL (`journalctl -f`, 222 lignes) : pays de l'IP, 127.0.0.1 = le programme, rappel des lignes d'un visiteur devenu connu, heure locale ISO sans doublons, chaque IP remplacée par la personne déjà connectée, l'équipe, le nom DNS ou l'ISP (adresse gardée entre crochets), présence (connexion, déconnexion, inactivité), couleurs (HTTP, erreurs, connexions), `--min` ; `--no-isp` : aucune requête extérieure |
| `nginx-tools-tests/run-all.sh` | 1.105.20261011.211500 | Validation complète : présence, syntaxe, ShellCheck, ruff, tests de l'environnement du serveur (Odoo ou BBB) sous chaque awk, configuration déployée (Odoo), contrôles du serveur réel (lecture seule) |
| `odoo-chat-post.py` (NOUVEAU) | 1.0.20261015.085700 | Canaux et fils d'alertes dans Odoo (Discuss) avec premier message, `--post` pour y publier ; catalogue `doc/odoo-chat-post.catalogue.json` |
| `odoo-mail-retry.py` (NOUVEAU) | 1.2.20261010.215000 | Liste des courriels d'Odoo non envoyés (titre, date, destinataires masqués, cause) et renvoi (menu ou --resend --yes) |
| `host-perf-audit.py` (NOUVEAU, 2026-10-16) | 1.0 | À lancer sur l'HÔTE Proxmox : ce qui limite les performances (processeur, mémoire, disques, PSI, ZFS, réseau, invités LXC/VM par cgroup) sur `--duration` (60 s à 24 h), verdict, « des disques SSD sont-ils justifiés ? », réglages (`--apply` : compression / atime ZFS, zfs_arc_max, swappiness) ; `--csv` |

Composants partagés dans `apps/` : `_profile.sh` / `_profile.py` (profil d'application `odoo.conf` / `bbb.conf`, détection automatique),
`_rapport.sh` / `_rapport.py` (`--report-err`, version 1.9.20261008.120306), `_bbb.py` (état de BigBlueButton avant / après, version 1.1.20261002.073514), `_reseau.py` (propriétaire du bloc d'adresses d'une IP, RDAP puis whois, avec cache, version 1.1.20261007.171721), `_i18n.py` (langue d'affichage et traduction par fragments, catalogues PO `lang/PROGRAMME.XX.po`, contexte commun des programmes Python, version 1.4.20261011.144500), `_config.py` (fichiers de configuration KEY=VALUE des programmes Python, version 1.0.20261010.211030), `_i18n.sh` (langue et fichier de configuration des programmes bash, version 1.1.20261011.144500), `_traduire.py` (traduit la sortie d'un programme bash, version 1.2.20261011.144500), `_odoo_db.py` (utilisateurs, modules, paramètres mail.*, courriels, inscriptions aux événements et aux sondages d'une base Odoo, LECTURE SEULE forcée, version 1.7.20261009.230224), `_listes.py` / `_listes.sh` (LISTE BLANCHE et LIEUX hors des archives, lecteur commun, version 1.0.20261007.093208), `_cache_ip.py` (cache permanent des adresses, SQLite, version 1.0.20261007.171721), `team-ips.list`. Documentation : `doc/courriel-securise.md` + `doc/courriel/` (Postfix en envoi seulement, relais ou envoi direct, OpenDKIM, modèles SPF / DKIM / DMARC / TLS-RPT / MTA-STS), `doc/email-setup.md` (relais SMTP,
DNS : MX, SPF, DKIM, DMARC), `doc/app-health-check.conf.example`, `doc/bbb-upgrade.md` (mise à jour de BBB sans perdre le durcissement). - **2026-10-16 (nginx-tools 1.122)** : `web-monitor.py` 2.65 - section ACTIVITÉ SUSPECTE D'UTILISATEURS CONNECTÉS (score d'indices : rafale, outils, accès refusés par Odoo, formulaires en masse, URL malveillantes, courriel jetable, nouveau compte...), `--suspect-users`, `--investigate-user`, `--ban-odoo-user` / `--unban-odoo-user` (compte ARCHIVÉ par SQL gardé + adresses propres au compte bannies), `--watch-odoo-user` ; registre `/var/lib/nginx-tools/odoo-users.tsv` (`apps/_odoo_users.py`) lu par `nginx-log-audit.sh` 2.37 (adresses d'un compte banni plus « légitimes ») et `app-log-live.py` (marques). Recherches Internet (StopForumSpam, Gravatar, DuckDuckGo : `apps/_email_check.py`) SEULEMENT avec accord ou `--internet` ; `NGINX_TOOLS_INTERNET=off`. `app-log-live.py` 1.82 : latence (touche P, Ctrl-G niveau 4/6/8 : PSI du cgroup du conteneur, % disque, SQL vs Python, par heure ; verdict SSD) via `apps/_sysperf.py`. `odoo-mail-retry.py` 1.10 : adresses invalides des inscriptions (`--invalid-emails`, `--fix --yes`). Largeur d'affichage des caractères chinois (web-monitor `--table`, app-log-live). Module `rlq_survey_report` 18.0.1.109.0 : menu Événements > Courriels invalides (correction + renvoi), correction automatique de la ponctuation à l'inscription.
- **2026-10-16 (nginx-tools 1.123)** : `host-perf-audit.py` 1.1 (cœurs lus dans le /proc/stat mesuré) ; `docs/build_docs.py` 1.1 -> module `rlq_tools_docs` 18.0.1.2.0 (pages web de tous les programmes, dont host-perf-audit) ; tests `run-all.sh` 1.182 : les anciens `lang/PROG.en.po` des programmes écrits en anglais sont des fichiers résiduels (proposés à la suppression). Module `rlq_survey_report` 18.0.1.110.0 : guide `/rlq_survey_report/aide` § 13 « Adresses courriel invalides ».
- **2026-10-16 (nginx-tools 1.124)** : `app-log-live.py` 1.83 - `--truncate [N]` (clé TRUNCATE ; lignes coupées à 2 x $COLUMNS à l'écran, journal entier), comptes SSH avec leur nombre de sessions (processus sshd + who), groupes RLQ* sur 4 / 2 colonnes ; nombres colorés APRÈS traduction (plus d'anglais dans le résumé français) ; `rlq_tools_docs` 18.0.1.3.0.
- **2026-10-16 (nginx-tools 1.125)** : copyright « Services-Conseils Linux Inc. » partout (programmes, modules, doc). Ctrl+C : `timeout --foreground` dans tous les programmes bash (sans lui, Ctrl+C restait sans effet jusqu'à la fin du délai : cause du problème de `nginx-log-audit.sh` lancé par `app-log-live.py`), `run_interruptible` / `ctrl_c_child` (apps/_i18n.sh 1.11), `foreground_child` (apps/_i18n.py 1.16). `app-log-live.py` 1.84 : touche I par événement -> billet -> sondage DU billet (`_odoo_db.registrations_by_ticket`), courriels envoyés nommés (`mail_detail`). `odoo-update-module.sh` 1.11 : site calme (WAIT_QUIET 15 min, BUSY_VISITORS 3), copie des modules, contrôle du journal après le démarrage, retour arrière. `web-monitor.py` 2.66 : pages lues / écrites, Mo reçus / envoyés (`rl=$request_length`, nginx-odoo-config 1.11). `rlq_survey_report` 18.0.1.111.0, `rlq_tools_docs` 18.0.1.4.0.
- **2026-10-17 (nginx-tools 1.126)** : `web-monitor.py` 2.67 - `--list-users --table` compact (aucune espace dans les cellules, titres coupés sur 2 lignes, min. 4), champs Odoo (événements, sondages, téléphone, pays, ville, groupes, étiquettes : `_odoo_db.user_profiles` 1.16), couleurs, `--table-fields`, `--group`, `--csv` (« ; », BOM, virgule décimale), `--repeat-header`, `--stats`. « Mo envoyés » = « ? » tant que nginx-odoo-config 1.11 (rl=$request_length) n'est pas déployé et nginx rechargé. Langue : `LANGUAGE` de GNU lu, origine affichée dans la ligne Options (`apps/_i18n.py` 1.17, `_i18n.sh` 1.12, `_traduire.py` 1.4).
- **2026-10-17 (nginx-tools 1.127)** : `web-monitor.py` 2.68 (plantage de --table avec bans.tsv), `app-log-live.py` 1.85 (groupes « NOM = N »), `apps/_i18n.sh` 1.13 (second Ctrl+C pendant la confirmation), tests 1.186 : la suite ne touche JAMAIS le dossier des programmes (fichiers résiduels seulement signalés).
- **2026-10-17 (nginx-tools 1.128)** : `web-monitor.py` 2.69 - colonne « IP vue » (`ipseen`, `--sort seen`), titre de la colonne triée en cyan, étiquettes hors du tableau par défaut, clés CSV / GROUP / INTERNET ; les clés du fichier ne lancent jamais `--list-users` (seulement la ligne de commande).
- **2026-10-19 (nginx-tools 1.129 à 1.131)** : `web-monitor.py` 2.70 (une ligne sur 5 soulignée, colonnes « Compte créé », « Pays IP » RDAP/whois, « VPN ») et 2.71 (clés des options jamais traduites : « browsers », pas « navigateurs » ; noms français acceptés). 1.131 : `app-log-live.py` 1.86 - `--diagnose` / touche D : versions de la configuration nginx et leurs dates (nginx-odoo/VERSION, journal daté du README.md, fichiers déployés comparés, dernier rechargement) ; `apps/_config.py` 1.7 et `apps/_i18n.sh` 1.14 - un fichier de /etc/default sans AUCUNE option active est remis au modèle actuel au lancement suivant (jamais s'il a une ligne CLÉ=valeur ; `NGINX_TOOLS_CONFIG_MAJ_AUTO=0`) ; **copyright** : « Copyright (C) 2026 Services-Conseils Linux Inc. » et « Copyright (C) 2026 Rencontres Linux au Québec contributors » (AGPL-3.0-or-later) dans tous les programmes Python et bash, AUCUN dans les fichiers de configuration (modèles libres) ; `doc/` = fichiers utilisés par les programmes (journaux, modèles .conf.example, nginx-tools.version, notes), `docs/` = manuel en/fr et build_docs.py (`rlq_tools_docs` 18.0.1.7.0).
- **2026-10-19 (nginx-tools 1.129 à 1.131)** : `web-monitor.py` 2.70 (une ligne sur 5 soulignée, colonnes « Compte créé », « Pays IP » RDAP/whois, « VPN ») et 2.71 (clés des options jamais traduites : « browsers », pas « navigateurs » ; noms français acceptés). 1.131 : `app-log-live.py` 1.86 - `--diagnose` / touche D : versions de la configuration nginx et leurs dates (nginx-odoo/VERSION, journal daté du README.md, fichiers déployés comparés, dernier rechargement) ; `apps/_config.py` 1.7 et `apps/_i18n.sh` 1.14 - un fichier de /etc/default sans AUCUNE option active est remis au modèle actuel au lancement suivant (jamais s'il a une ligne CLÉ=valeur ; `NGINX_TOOLS_CONFIG_MAJ_AUTO=0`) ; **copyright** : « Copyright (C) 2026 Services-Conseils Linux » et « Copyright (C) 2026 Rencontres Linux au Québec contributors » (AGPL-3.0-or-later) dans tous les programmes Python et bash, AUCUN dans les fichiers de configuration (modèles libres) ; `doc/` = fichiers utilisés par les programmes (journaux, modèles .conf.example, nginx-tools.version, notes), `docs/` = manuel en/fr et build_docs.py (`rlq_tools_docs` 18.0.1.7.0).
- **2026-10-20 (nginx-tools 1.133)** : `app-log-live.py` 1.88 - une ligne du journal sur 5 soulignée ; `--truncate` par défaut (`--no-truncate`) : ligne plus large que `$COLUMNS - 10` -> « début ... deux derniers mots » (menus et rapports jamais coupés) ; `--anonymize` par défaut et enfin appliqué à l'écran (`--no-anonymize` ; le journal quotidien garde tout) ; courriel envoyé nommé même après sa suppression par Odoo (auto_delete : `apps/_odoo_db.py` 1.19 relit le mail.message par Message-Id) ; « -2026- » surligné. `apps/_anonymiser.py` 1.2 : courriels masqués « b****ge@... » remplacés en entier, `fixed_width`.
- **2026-10-20 (nginx-tools 1.134, nginx-tools-tests 1.188)** : la suite de tests est dans le dépôt Git (`nginx-tools-tests/`), SANS données personnelles (noms, courriels, IP de personnes remplacés : adresses publiques fictives dans les blocs du DoD `11.x`, documentation RFC 5737 sinon) et SANS la configuration nginx (privée : `NGINX_ODOO_DIR`, ou `nginx-tools-tests/nginx-odoo/` de l'archive) ni `tools/` ; statistiques à la fin de `run-all.sh` (`stats_runner.py` : durée, CPU, mémoire, disque, tests par programme et par nature unitaire / fonctionnel / interactif / conformité) ; données d'exemple FR/EN (`donnees_exemples.py`) et tests d'alignement (`test_alignement.py`) ; `apps/_i18n.sh` 1.15 `pad_cols` (printf de bash compte des octets) ; `app-log-live.py` 1.89 : `--truncate` / `--anonymize` par défaut seulement dans un terminal ; `web-monitor.py` 2.74.

## 5. Déploiement (par serveur)

```bash
cd /root/scripts && unzip -o nginx-tools.<MAJEUR.MINEUR>.zip && cp -r nginx-tools/* . && rm -rf nginx-tools
# Odoo seulement - dans CET ordre (les fichiers inclus doivent exister avant la configuration qui les inclut ; team-ips-geo.conf et team-ips-allow.conf sont inclus par leur nom exact, et l'include ÉCHOUE sans fichier : lancer nginx-hardening.sh --update avant tout nginx -t / rechargement) :
unzip -o nginx-odoo-config.<MAJEUR.MINEUR>.zip
cp nginx-odoo/snippets/securite-commune.conf /etc/nginx/snippets/      # team-ips-*.conf : GÉNÉRÉS par nginx-hardening.sh, jamais livrés
mkdir -p /etc/nginx/fail2ban && cp nginx-odoo/fail2ban/* /etc/nginx/fail2ban/
cp nginx-odoo/conf.d/odoo-global.conf /etc/nginx/conf.d/ ; cp nginx-odoo/snippets/odoo/env-*.conf /etc/nginx/snippets/odoo/
nginx -t && systemctl reload nginx
./nginx-hardening.sh --update        # jails, ignoreip, adresses de l'équipe, courriel, rétention...
unzip -o nginx-tools-tests.<MAJEUR.MINEUR>.zip && nginx-tools-tests/run-all.sh
```
Ancienne suite dans `tests/` (avant le 2026-10-01) : `run-all.sh` la signale `[ATTN]` avec nos fichiers qui s'y trouvent ; ne retirer
que ceux-là (le dossier `tests/` peut contenir les tests d'autres programmes).
Sur BigBlueButton : `nginx-tools.zip` et `nginx-tools-tests.zip` suffisent, puis `./nginx-hardening.sh --update` et UNE réunion de test (caméra, micro,
partage d'écran : la suite ne peut pas tester WebRTC).

## 6. Validation - `nginx-tools-tests/run-all.sh`

Étapes : présence des fichiers - syntaxe (`bash -n`, `py_compile`) - ShellCheck - ruff - suite de tests sous chaque awk (mawk, gawk,
busybox si présent), **limitée à l'environnement du serveur** (modules `commun` + `odoo` OU `bbb`) - configuration déployée comparée à
`nginx-tools-tests/nginx-odoo/` (Odoo seulement) - contrôles du serveur RÉEL en lecture seule, hors verdict (BBB : `apps/_bbb.py --summary` ;
Odoo : `app-health-check.py --target local`). Un test en échec est relancé seul : échec confirmé
(bloquant) ou `[INSTABLE]` (détail dans `nginx-tools-tests/last-instable.log`). Sentinelles : aucun répertoire temporaire oublié, **aucun fichier de
configuration réel modifié** (`/etc/default`, `~`). Les tests redirigent TOUS les chemins système vers un dossier temporaire et
n'atteignent aucune commande système sensible (`ufw`, `iptables`, `nginx`, `systemctl`..., simulées). `/proc` est isolé pour TOUT le processus
de test (`helpers.py`), et le vrai instantané BBB (`/var/lib/nginx-tools/bbb-state.json`) est surveillé par la sentinelle.

## 7. Pièges connus (chacun a déjà coûté un cycle) - **Python 3.8** sur BBB PROD : pas de `str.removesuffix`, etc. (un test refuse les fonctions postérieures).
- **ShellCheck** : la version de développement (0.11) est PLUS récente que celle de Debian/Ubuntu et ne signale pas « A && B || C »
  (SC2015) - un test cherche ce motif lui-même. Jamais d'apostrophe dans `${x:+...}` entre guillemets (casse l'analyse de bash).
- `systemctl is-active` AFFICHE l'état ET renvoie un code non nul : ne pas écrire `$(... || echo inconnu)`.
- Un test qui appelle une fonction de migration SANS rediriger `/etc/default` écrit dans le vrai (sentinelle de `run-all.sh`) ; isoler `HOME`.
- Les tests ne doivent pas dépendre de l'environnement (longueur du PID, awk, ordre) : analyser les en-têtes avec un analyseur, pas une regex.
- `--config` introuvable = erreur ; ne jamais ignorer en silence un fichier demandé (valeurs par défaut sans `REMOTE` = pas de copie hors du serveur).
- Un timer ne doit pas contenir de chemin de configuration en dur (sauf `--config` explicite) ; `web-monitor.py` alerte si un timer vise un fichier absent.
- `http-response` de HAProxy ne s'applique pas à ses propres redirections : `http-after-response` (HSTS sur BBB).
- Ne jamais lire le répertoire courant pour une configuration (résultat différent à la main et sous systemd). - **Un test qui charge un programme DANS le processus de test** (`importlib`, appel direct de `recommandations()`...) n'utilise PAS `self.env` :
  il lit le vrai `os.environ`, `/proc`, etc. Toute dépendance à la machine se corrige au niveau du processus (`helpers.py`), pas dans `self.env`.
  Vérifier avec un faux `/proc` contenant des processus nginx (un test avait échoué seulement sur un serveur où nginx tourne).
- **Jamais de suite de tests ancienne contre des programmes récents** (ni l'inverse) : la 1.52 lancée contre les nouveaux programmes avait écrit
  le vrai instantané BBB. Déployer les deux archives ensemble ; retirer les anciens `run-all.sh` et `test_*.py` de la racine des programmes.
- Adresses de documentation (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`) : « privées » pour Python (`ipaddress`) - utiliser d'autres adresses publiques dans les tests.
- Un `cut -c` d'octets coupe un caractère accentué en deux (sortie invalide) : couper avec Python. - **Une recommandation doit dire la VRAIE cause** : `web-monitor.py` évalue lui-même les `location ~` de `nginx -T` sur chaque chemin qui traverse nginx
  (« règle manquante » != « bloc server mal inclus ») ; un conseil générique qui envoie chercher au mauvais endroit a déjà coûté un cycle (wp-admin).
- `app-log-live.py` : Odoo n'enregistre pas la fin d'une session (« connecté » = connecté, non déconnecté, actif depuis moins de `--idle` minutes) ;
  l'heure d'un événement vient de la ligne du journal, jamais du fuseau de la machine. - **Les invites Python chargent `readline`** (`web-monitor.py`, `app-health-check.py`) : sans lui, `input()` affiche « ^H » avec un terminal dont le retour arrière envoie ^H.
  Un nouveau programme qui pose une question fait pareil (les invites bash utilisent `read -e`).
- **`app-log-live.py` : une recherche lente ne doit jamais retenir une recherche rapide.** Voie rapide (ce serveur, personne, équipe) sans appel extérieur ;
  threads séparés pour le DNS, le fournisseur d'accès et le pays. Les noms de personnes ne dépendent que de PostgreSQL (lecture seule, en cache).
- Les tests n'utilisent JAMAIS les vrais fichiers de `/etc/default` : `helpers.py` isole `NGINX_TOOLS_WHITE_LIST` et `NGINX_TOOLS_IP_LOCATION` ; un test écrit SA liste (`self.liste_blanche()`, `self.lieux()`, adresses FICTIVES `LISTE_EXEMPLE`). - « Session expired » (INFO, `odoo.http`) : requête d'un client dont la session n'est plus valide ; HTTP 200 (le refus est dans la réponse JSON-RPC). Un flot
  de milliers de lignes vient d'UN onglet resté ouvert, pas d'un défaut du serveur : `app-log-check.py --by-hour` le dit (un client ou plusieurs, lien avec
  les redémarrages). Ne pas masquer le message avant d'avoir identifié le client. - **Les refus de nginx sont dans `blocked-probes.log`, pas dans les journaux du site** (nos règles de refus y écrivent à la place) : toute enquête ou preuve sur une adresse
  bannie par le jail `nginx-blocked-probes` doit le lire (`urls_refusees`, section « Requêtes REFUSÉES par nginx »). Sans cela : « aucune requête » pour une adresse bannie.
- Deux adresses d'un même compte = un compte sur deux postes, pas « plusieurs clients » (`app-log-check.py --by-hour` raisonne par compte). Odoo CE autorise plusieurs sessions
  simultanées par compte : si une connexion sur un poste invalide l'autre, chercher un module (le rapport les liste) - ne pas conclure sans les rafales corrélées.

## 8. Décisions à ne pas défaire - BBB : règles de sécurité dans un fichier À NOUS (`/etc/bigbluebutton/nginx/zz-nginx-hardening-security.nginx`), aucun fichier géré par BBB
  modifié ; **pas de capteur catch-all** (HAProxy reçoit le port 443) ; être indexé n'est pas souhaitable (refus 403 à Googlebot : voulu).
- Les refus de nginx sont journalisés À PART (`blocked-probes.log`) et bannis par la jail `nginx-blocked-probes` (5 refus en 10 min -> 24 h).
- CrowdSec : chargement par `ipset swap` (jamais d'ensemble vide ou partiel), nginx non rechargé.
- Sauvegarde : pg_dump `--no-owner` texte + `manifest.json` + `filestore/` (format d'Odoo) ; jamais d'écrasement à la restauration ;
  `KEEP_RECENT_DAYS` garde tout sur N jours (sinon plusieurs sauvegardes par jour s'effaceraient) ; seuil d'alerte = écart maximal + 2 h.
- Un bloc qui ne fait que rediriger inclut `securite-commune.conf` et redirige dans `location /` (jamais `return` au niveau du
  server : il passerait avant les règles). Une redirection (3xx, petite page) de nginx à une URL malveillante est un rejet pour
  `web-monitor.py`.
- Adresses `$remote_addr` dans les journaux (jamais `X-Forwarded-For`, falsifiable) ; journal des sites au format `combined_host`.

## 9. État connu et tâches en attente - À CONFIRMER sur les serveurs - **Sauvegarde** : configurer `REMOTE` dans `/etc/default/odoo-backup.conf`, faire `--test-restore` puis une restauration réelle en DEV, installer
  le timer (`--install-timer`) ; vérifier qu'un ancien timer ne vise pas un fichier absent (`--status`).
- Courriel des alertes : relais SMTP + DNS (`app-health-check.py --check-email-dns`, `--test-email`) ; timer `web-monitor.py --install-timer`.
- PROD Odoo : `--limit-memory-hard=0` dans `run.sh` (valeurs proposées par `nginx-hardening.sh --check`, étape 6) ; `list_db = False` ;
  HSTS `max-age` à remonter (31536000) sur les noms qui redirigent ; bug `web_editor` AccessDenied (correctif en amont).
- BBB : mise à jour de BBB selon `doc/bbb-upgrade.md` (`--update` avant ET après : sections AVANT / APRÈS, instantané
  `/var/lib/nginx-tools/bbb-state.json`) ; `nginx-hardening.sh --update` sur les deux serveurs, fail2ban démarré (`systemctl enable --now fail2ban`), `robots.txt` (`Disallow: /`) à
  vérifier, secret de l'API à renouveler (`bbb-conf --setsecret`), adresse dominante des refus 403 à enquêter.
- SSH réservé à Tailscale (interface `tailscale0` + quatre adresses exactes, pas `100.64.0.0/10`) : recommandé, pas appliqué.
- L'adresse du cellulaire de Étienne change : la mettre à jour dans `/etc/default/nginx-tools-white-list.conf` (puis `nginx-hardening.sh --update`).

## 10. Régénérer `nginx-odoo-config.zip` (dans une autre discussion)

La configuration nginx **n'est pas autonome** : ses règles vivent aussi dans `nginx-tools.zip` et `nginx-tools-tests.zip`. Joindre les TROIS archives et
écrire « lis doc/CONTEXTE.md » ; il n'y a volontairement pas de second `CONTEXTE.md` dans `nginx-odoo-config.zip` (deux copies divergent), seulement
un renvoi dans son `README.md`.

Contenu : `conf.d/` (`odoo-global.conf`, `bot_blocker.conf`) - `sites-available/` (`00-catchall-default`, `10` prod, `20` dev, `30` lab) - `snippets/odoo/` (`_odoo-common.conf`, `env-{prod,dev,lab}.conf`, `hsts.conf`, fichiers `*.name.conf` et `*.ssl.conf`) - `snippets/securite-commune.conf` - `fail2ban/` (jails `nginx-catchall`, `nginx-blocked-probes`, `odoo-auth` en
modèle) - `maintenance/index.html` - `README.md` (journal DATÉ, sans numéro de version : ajouter une ligne à chaque modification).

À chaque modification, TOUT ce qui suit doit rester cohérent (chaque point est vérifié par un test ou par `run-all.sh`) :

1. **Copie testée identique** (VERSION comprise) : `nginx-odoo/` et `nginx-tools-tests/nginx-odoo/` (lue par `test_config_nginx` et par l'étape 5 de `run-all.sh`) ; `diff -rq nginx-odoo
   nginx-tools-tests/nginx-odoo` doit être vide. Reconstruire `nginx-odoo-config.zip` ET `nginx-tools-tests.zip`.
2. **`team-ips-geo.conf` et `team-ips-allow.conf` ne sont PAS livrés** : GÉNÉRÉS sur chaque serveur par `generer_equipe` de `nginx-hardening.sh` à partir de la liste blanche
   (`/etc/default/nginx-tools-white-list.conf`) ; la configuration les inclut par leur NOM EXACT (`team-ips-geo.conf`, `team-ips-allow.conf` ; un joker `team-ips-geo*.conf` a fait échouer `nginx -t` sur odoo-dev même avec les fichiers présents), et un fichier absent fait ÉCHOUER `nginx -t` : `--update` crée toujours les deux fichiers (vides au besoin), jamais de `rm`
   (test : `SourceUniqueEquipe`). Aucune adresse de l'équipe en dur ailleurs ; les adresses propres à un environnement (localhost, IP publique du serveur DEV) restent dans son `env-*.conf`.
3. **Filtre et jail `nginx-blocked-probes`** : recopiés OCTET POUR OCTET dans `nginx-hardening.sh` (fonctions `filtre_blocked_probes` et
   `jail_blocked_probes`, utilisées sur BBB où cette configuration n'est pas déployée). Modifier les deux ensemble (test : `RefusJournalises`).
4. **`securite-commune.conf`** journalise ses 8 refus dans `/var/log/nginx/blocked-probes.log` au format `combined_host` (jamais `access_log off`) ;
   ce format est défini dans `odoo-global.conf` et utilisé par les journaux des trois sites.
5. **Déploiement** : d'abord les fichiers inclus (`securite-commune.conf`...), puis `odoo-global.conf` et `env-*.conf`, puis `nginx -t && systemctl reload nginx`,
   puis `nginx-hardening.sh --update` (section 5 pour les commandes). Un `nginx -t` en échec ne doit jamais être suivi d'un rechargement.
6. **Version** : chaque modification de la configuration monte le MINEUR de `VERSION` (1.0 -> 1.1...) dans LES DEUX arbres, ajoute une ligne datée au journal du
   `README.md`, et l'archive se livre sous `nginx-odoo-config.<MAJEUR.MINEUR>.zip`. Les expressions régulières qui contiennent une accolade (`{2}`) sont
   ENTRE GUILLEMETS (nginx refuse sinon la configuration : `nginx -t` échoue). Toute règle de refus nouvelle a un test de comportement
   (`test_config_nginx.py`, classe `RegleWordPress` : chemins refusés ET vraies routes d'Odoo jamais refusées).

## Langue d'affichage et fichiers de configuration (tous les programmes)

* **Tous les programmes sont bilingues** (français = langue du code ; anglais ; toute autre langue = un fichier `lang/PROGRAMME.XX.po`, format PO standard, voir `lang/README.md`). Choix : `--lang` > `NGINX_TOOLS_LANG` (impose la langue à tous les outils ; les programmes qui ANALYSENT la sortie d'un autre y mettent `fr`) > variable du programme (`WEB_MONITOR_LANG`, `NGINX_LOG_AUDIT_LANG`...) > clé `LANGUAGE` du fichier de configuration (`auto` = suivre l'environnement) > `LC_ALL` > `LC_MESSAGES` > `LANG` > français si rien n'est défini.
* **Programmes Python** : `apps/_i18n.py` (`demarrer`) ; **programmes bash** : `apps/_i18n.sh` (`i18n_relancer` tout au début) relance le programme derrière `apps/_traduire.py`, qui traduit la sortie ligne par ligne (en français : aucun processus de plus). Les messages du code restent en français ; un message sans traduction reste en français (jamais d'erreur).
* **Anonymisation (`--anonymize`)** : `apps/_anonymiser.py` remplace IP, courriels, identifiants (`--login`, `login=`, `user=`, `email=`) et jetons / mots de passe / cookies dans ce qui est affiché par des PSEUDONYMES STABLES (HMAC-SHA256 d'un sel secret par machine : `IP-4f2a9c`, `usager-9c1e03@anonyme.invalid`, `ID-3b7d11`, `***`). Tous les analyseurs d'arguments acceptent l'option (ajoutée par `apps/_i18n.py` ; `web-monitor.py` par sa propre classe) ; le programme est relancé derrière le filtre de `apps/_traduire.py` (Python : `--anonymiser-seul` ; bash : `i18n_relancer`, qui retire l'option des arguments), donc les programmes lancés par lui sont filtrés aussi. Clé `ANONYMIZE` (fichier commun ou du programme, terminal seulement), variable `NGINX_TOOLS_ANONYMIZE` (1 : oui, y compris cron ; 0 : non), `NGINX_TOOLS_ANON_ACTIF` posée derrière le filtre. Échoue fermé. `apps/_anonymiser.py --pseudonyme VALEUR` donne le pseudonyme d'une valeur connue.
* **Fichiers de configuration** (règle commune) : `/etc/default/PROGRAMME.conf` PUIS `~/.PROGRAMME.conf` (le dernier l'emporte), ligne de commande prioritaire, `-c/--config FICHIER` = ce fichier SEUL. Au départ : « Configuration lue : ... » et « Options : ... ». Clés = options importantes (+ `LANGUAGE`) ; exemples dans `doc/PROGRAMME.conf.example`. `/etc/default/nginx-hardening.conf` sert aussi de fichier d'état (lignes `SETUP_*`) : les autres lignes sont conservées.
* Tests : `test_i18n.py` (catalogue complet de chaque programme, mécanisme, configuration), `i18n_tools.py` / `i18n_tools_sh.py` (extraction des messages). - **Ctrl+C demande TOUJOURS confirmation** (« Interrompre le programme ? [o/N] ») dans les programmes Python (`apps/_i18n.py` `installer_confirmation_ctrl_c`, via `demarrer()` ; `web-monitor.py` l'appelle lui-même) et bash (`apps/_i18n.sh` `ctrl_c_installer`, via `i18n_relancer`). Oui / second Ctrl+C = arrêt ; non = reprise. Sans effet hors terminal ; `NGINX_TOOLS_CTRL_C=0` la désactive. Le terminal envoie aussi le signal aux commandes en cours (même groupe) : limite connue. `run-all.sh` isole la passe de tests (`setsid`). Tests : `test_ctrl_c.py`. - **limit_conn par cookie `visitor_uuid`** (nginx-odoo-config 1.7, `odoo_visiteur_v2`, 8 connexions simultanées, 429) et **section [11] de nginx-log-audit.sh 2.29** : requêtes dynamiques en parallèle depuis une même adresse (conflits d'écriture `website_visitor` d'Odoo). Le journal nginx ne contient pas le cookie : l'indice est « même adresse, même seconde » AVEC erreurs 5xx/429 ; lieux connus (université) jamais signalés ; information seulement. La limite nginx compte par COOKIE, jamais par adresse (des inscriptions ou sondages simultanés derrière une même adresse ne se gênent pas). Option `--parallel-threshold`. - **Odoo 17** (nginx-odoo-config 1.10, nginx-hardening.sh 2.46, app-log-live 1.56) : `odoo17.rencontres-linux.quebec`, sites `40-`/`50-`/`60-` (PROD/DEV/LAB, un seul actif par serveur), ports 8069/8072, upstreams `odoo17`/`odoo17_chat` ; les outils ignorent tout upstream `odoo<chiffre>*` (jamais corrigé par --update). Certificat à émettre (certbot webroot) avant d'activer.
- **Réseaux partagés** (nginx-odoo-config 1.9, nginx-hardening.sh 2.30 étape 12b) : les lieux `[partagée]` de `nginx-tools-ip-location.conf` sont écrits dans `shared-ips-geo.conf` ($is_shared_ip) et ont leurs zones `odoo_general_partage_v2` (90 req/s, rafale 180) et `odoo_login_partage_v2` (25/min, rafale 25) ; les zones ordinaires ne visent que les autres adresses. Marquer aussi `[protégée]` pour que fail2ban ignore la plage. Déploiement : nginx-hardening.sh --update AVANT la nouvelle configuration nginx (include sans fichier = nginx -t refuse). - **Configuration d'Odoo (nginx-hardening 2.32)** : `--odoo-conf-paths` / `ODOO_CONF_PATHS` (candidats : /etc/odoo/odoo-linux_meetup.conf, /opt/odoo/erplibre/config.conf, /home/utilisateur/git/erplibre/config.conf, /etc/odoo/*.conf). Une configuration trouvée => application « Odoo », ports http/gevent (ufw/iptables), logfile (jail odoo-auth, étape 11b, app-log-live). Priorité des ports : option explicite > configuration > 8069/8072 > 10000/10002 historiques. app-log-check.py et web-monitor.py ne lisent encore que le journal systemd. - **nginx-hardening 2.34** : étape 0b fuseau horaire (`--timezone`, défaut America/Montreal, demandé la première fois, mémorisé dans `TIMEZONE=`), 0c création des dossiers `proxy_cache_path`, 11b création de `/etc/logrotate.d/odoo`. **app-log-live 1.35** : messages d'Odoo (non-requêtes) alignés sur la colonne du GET/POST ; Ctrl-G/Ctrl-T affichent « depuis ... pendant ... ». - **Lot 2026-10-12 (nuit)** : app-log-live 1.36 (`--not-found`, `--disk-min`), nginx-log-audit 2.32 (site `lab`, `--ban` installe iptables-persistent), nginx-hardening 2.35 (règles iptables enregistrées, page de maintenance depuis /etc/nginx/maintenance).
