# nginx-log-audit.sh - rapport des journaux nginx, enquêtes, bannissements

Lit les journaux d'accès nginx (journal du site `dev`, `lab` ou `prod` ; défaut : le profil détecté) et produit un rapport numéroté : robots, refus, attaques, recherche de fichiers sensibles, rafales, requêtes parallèles, identités de robots changeantes, puis propose de bannir les fautifs. Il garde une position de lecture : chaque exécution analyse **ce qui est nouveau** (`--init` relit le fichier actif, `--init-all` tout l'historique avec les rotations).

```bash
nginx-log-audit.sh prod                    # rapport, puis proposition de bannissements
nginx-log-audit.sh prod --last 24 --no-prompt
nginx-log-audit.sh --investigate 203.0.113.7   # enquête sur tout l'historique + propriétaire du bloc (RDAP)
nginx-log-audit.sh --evidence 203.0.113.7      # preuves pour/contre un bannissement, lecture seule
sudo nginx-log-audit.sh --ban 203.0.113.7      # preuves affichées, justification et confirmation demandées (--yes pour l'éviter)
sudo nginx-log-audit.sh --ban 203.0.113.7 --yes --reason "scanner .env"   # justification donnée d'avance
sudo nginx-log-audit.sh --ban-history          # journal des bannissements manuels : date, heure, justification, origine
nginx-log-audit.sh --export-bans > bans.txt ; nginx-log-audit.sh --import-bans bans.txt
nginx-log-audit.sh --stats --details       # statistiques : codes, IP, agents utilisateurs, appareils
```

## Comment un bannissement est décidé

Les indices sont comptés par adresse : recherche de chemins sensibles, rafales de pages (`--page-burst` : pages distinctes en 10 s), requêtes dynamiques parallèles dans la même seconde (`--parallel-threshold`, section 11), nombreuses identités de robot depuis une adresse (`--ua-rotation-threshold`). Un bannissement est *suggéré* à partir de `--ban-threshold` indices (défaut 3). Les adresses de la liste blanche ou des lieux `[protégée]` ne sont jamais proposées. Les bannissements manuels sont réévalués par `--unban-check` (la levée est suggérée si elle n'est plus justifiée). Lorsque plus de 5 IP sont à lever, un sommaire de ces IP est affiché après le bilan.

## Quand et pourquoi une adresse a été bannie

Chaque `--ban` et `--unban` enregistre dans `~/.local/state/nginx-log-audit/bans.tsv` la date, l'heure, la **justification** et l'origine (compte et programme : ligne de commande, `web-monitor.py`, `app-log-live.py`, question du rapport...). La justification est demandée au clavier (proposition modifiable : les preuves) ; `--reason TEXTE` la donne d'avance ; avec `--yes` sans `--reason`, elle est notée « automatique ». Pour justifier après coup un bannissement plus ancien : `--ban IP --reason "..."` (la date du bannissement ne change pas).

`--unban IP` lève **tous** les bannissements de l'adresse, sans autre commande à lancer : la règle manuelle du pare-feu, chaque jail fail2ban qui la tient (trouvé par le programme) et la liste CrowdSec (l'adresse est retirée de l'ipset et ajoutée à `/etc/default/sync-crowdsec-blocklist.allow`, sinon la prochaine synchronisation la rebloquerait). Il affiche d'abord ce qu'il a trouvé, demande une confirmation et une justification, puis note une seule levée dans le journal avec les sources levées. Un jail peut la bannir de nouveau si elle recommence. `--unban-check` et `--unban-expired`, qui jugent le bannissement manuel, ne lèvent que celui-là.

`--investigate IP` commence par la section **Bannissements** : état actuel (règle du pare-feu, jails fail2ban avec début et fin, liste CrowdSec) et historique chronologique (journal des bannissements manuels et `fail2ban.log` avec ses rotations), puis, pour chaque jail en cause, sa raison et ce que l'adresse a fait (pages refusées de `blocked-probes.log`, requêtes au capteur catch-all...). Une adresse bloquée seulement par fail2ban ou par la liste CrowdSec n'apparaît pas dans `--unban-check`, qui ne traite que les bannissements manuels.

L'indice **serveur loué** est coché quand le DNS inverse désigne un hébergeur (AWS, OVH, Hetzner...) ; avec `--investigate`, il l'est aussi quand le **propriétaire du bloc d'adresses** (RDAP) en est un, même si le DNS inverse ne le montre pas (exemple : Vultr derrière un nom quelconque). La liste des **comptes Odoo actifs** pendant les requêtes n'est cherchée que si l'adresse a demandé une page de session (connexion, back-office, compte client, discussion) : Odoo ne note pas l'adresse IP des sessions, et pour un robot qui ne lit que des pages publiques cette coïncidence d'horaire désignerait des membres à tort. Les connexions trouvées dans le journal d'Odoo pour l'adresse elle-même restent toujours affichées.

Les refus produits par nos règles nginx sont journalisés dans `blocked-probes.log`, pas dans les journaux des sites ; les enquêtes et les preuves le lisent aussi (« Requêtes REFUSÉES par nginx »), sinon une adresse bannie semblerait n'avoir fait aucune requête.

`--unban-low-score` (2.81) enquête (comme `--investigate`) sur chaque adresse dont `--unban-check` recommande la levée, **avant** de la lever : le verdict et les raisons s'affichent, et une adresse n'est levée que si l'enquête dit « LEVER LE BANNISSEMENT » (sinon elle reste bannie, même avec `--yes`, avec un message qui renvoie à `--investigate`).

## Verdict et recommandation de `--investigate`

`--investigate` se termine par **ANALYSE ET RECOMMANDATION** : il relit l'enquête comme le ferait une personne et donne un seul verdict, ses raisons et la commande à lancer.

| Verdict | Quand |
|---|---|
| NE PAS BANNIR / LEVER LE BANNISSEMENT | adresse protégée (liste blanche, lieu protégé), moteur de recherche vérifié, compte Odoo connecté, nœud d'un CDN |
| BANNIR / GARDER LE BANNISSEMENT | signe fort (fichiers sensibles, erreurs en masse, faux moteur, capteur catch-all) ou score au seuil avec un signe d'hostilité ; la durée selon la provenance est indiquée |
| LAISSER À FAIL2BAN | signe fort, mais score sous le seuil : un bannissement au pare-feu demanderait une exception |
| REFUSER LE ROBOT PAR SON NOM | aucun signe d'hostilité, mais le robot se nomme dans son User-Agent (« CareerScout/1.0 », « webzio (+https://...) ») absent de `bot_blocker.conf` : le refuser par son nom suit le robot quand il change d'adresse |
| LEVER LE BANNISSEMENT | adresse bannie sans signe d'hostilité : fail2ban rattrape seul une nouvelle rafale |
| AUCUNE ACTION | rien à signaler |

S'y ajoutent des notes : nom déjà refusé dans `bot_blocker.conf`, nature probable des requêtes (offres d'emploi, flux RSS, formulaires), **type d'adresse** (VPN, sortie Tor, relais, hébergeur, d'après le propriétaire du bloc et la liste officielle des sorties Tor, mise en cache un jour), adresse de fournisseur d'accès, bannissements fail2ban et CrowdSec en cours. Le pays n'est pas un critère : c'est celui du serveur, pas de la personne. Quand l'organisation RDAP ne dit rien (« Admin »), le nom du réseau est affiché à sa place.

Plusieurs adresses d'un coup : `nginx-log-audit.sh --investigate 203.0.113.7 198.51.100.4` (ou `203.0.113.7,198.51.100.4`). Chaque adresse est enquêtée à tour de rôle, puis une **synthèse** donne le verdict de chacune et les commandes à lancer (`--ban`, `--unban`), qui vérifient de nouveau et demandent confirmation.

## Revue quotidienne des bannissements manuels (`--unban-check`)

`--unban-check` (lancé en root) réévalue chaque bannissement manuel avec les règles actuelles et propose de lever ceux qui ne sont plus justifiés. Ses verdicts :

- **justifié** : au moins un signe fort (fichiers sensibles, erreurs en masse, faux moteur de recherche, capteur catch-all) ou des refus répétés dans `blocked-probes.log` : on le garde ;
- **à vérifier** : une seule rafale de pages, sans signe fort : un navigateur ou un outil de surveillance peut faire cela. Ce verdict ne lève RIEN ; lisez les requêtes et décidez ;
- **incohérente** : l'adresse a changé pendant l'enquête : aucun verdict, relancer `--investigate` ;
- **sans trace** : plus aucune requête dans les journaux : l'historique des bannissements (jails fail2ban, journal des bannissements) est affiché.

Après la liste, la section **AUTRES POINTS À RE-VÉRIFIER** lance des contrôles en lecture seule et affiche la commande de chacun : adresses de l'équipe parmi les bannissements, jails fail2ban, adresses refusées par nginx qui ont aussi reçu des pages normales (faux positif possible), journaux utilisés, et les commandes à lancer à la main pour chaque adresse à vérifier. Ses sections 1 à 5 peuvent être copiées telles quelles pour une relecture.

Section **6** (2.80) : le programme lance lui-même `--investigate` pour chaque adresse de la section 5 (20 au plus, variable `UNBAN_CHECK_INVESTIGATIONS`) et n'affiche que son bloc **ANALYSE ET RECOMMANDATION** (verdict, raisons, commande), puis une synthèse et les commandes `--ban` ou `--unban` à lancer. Le rapport complet d'une adresse : la commande de la section 5.

Pour le lancer chaque matin, en root :

```
0 7 * * * root /root/scripts/nginx-log-audit.sh prod --unban-check --no-prompt
```

## Durée des bannissements (échéance)

Un bannissement au pare-feu n'est plus permanent : une adresse change de main avec le temps (une instance de nuage passe à un autre client, une ligne d'abonné à un autre abonné). Sa durée dépend de la **provenance** de l'adresse, décidée au bannissement :

| Provenance | Reconnue par | Clé (option) | Défaut |
|---|---|---|---|
| hébergeur, nuage | DNS inverse (AWS, OVH, Vultr...) ou propriétaire du bloc (RDAP) | `BAN_DAYS_HOSTING` (`--ban-days-hosting`) | 365 jours |
| fournisseur d'accès | DNS inverse d'une ligne d'abonné (dsl, cable, pool, dyn..., ou l'adresse écrite dans le nom) | `BAN_DAYS_ISP` (`--ban-days-isp`) | 90 jours |
| inconnue | aucun des deux | `BAN_DAYS_OTHER` (`--ban-days-other`) | 365 jours |

`0` = sans expiration. `--ban IP --ban-days N` fixe la durée de ce bannissement seulement, quelle que soit la provenance. L'échéance et la provenance sont écrites dans `bans.tsv` (colonnes 6 et 7) et affichées par `--investigate` et `--ban-history`.

`--unban-expired` (root) affiche chaque bannissement manuel avec sa date, son échéance et la décision, puis demande une seule confirmation (`--yes` : aucune) et lève ceux dont l'échéance est passée, par `--unban` (journal et règles persistantes mis à jour). Un bannissement enregistré avant la version 2.73 reçoit une échéance calculée depuis sa date de bannissement, écrite une fois dans le journal. Une règle absente du journal (posée à la main) n'a pas de date connue : elle reste en place ; `--ban IP --reason TEXTE` lui fixe une échéance à partir d'aujourd'hui.

`--ban` et `--unban-expired` écrivent `/etc/cron.d/nginx-log-audit-expiry`, qui lance `--unban-expired --yes` chaque jour à 4 h 23 (journal : `/var/log/nginx-log-audit-expiry.log`).

## Options
{{HELP}}
