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

`--investigate IP` commence par la section **Bannissements** : état actuel (règle du pare-feu, jails fail2ban avec début et fin, liste CrowdSec) et historique chronologique (journal des bannissements manuels et `fail2ban.log` avec ses rotations), puis, pour chaque jail en cause, sa raison et ce que l'adresse a fait (pages refusées de `blocked-probes.log`, requêtes au capteur catch-all...). Une adresse bloquée seulement par fail2ban ou par la liste CrowdSec n'apparaît pas dans `--unban-check`, qui ne traite que les bannissements manuels.

Les refus produits par nos règles nginx sont journalisés dans `blocked-probes.log`, pas dans les journaux des sites ; les enquêtes et les preuves le lisent aussi (« Requêtes REFUSÉES par nginx »), sinon une adresse bannie semblerait n'avoir fait aucune requête.

## Revue quotidienne des bannissements manuels (`--unban-check`)

`--unban-check` (lancé en root) réévalue chaque bannissement manuel avec les règles actuelles et propose de lever ceux qui ne sont plus justifiés. Ses verdicts :

- **justifié** : au moins un signe fort (fichiers sensibles, erreurs en masse, faux moteur de recherche, capteur catch-all) ou des refus répétés dans `blocked-probes.log` : on le garde ;
- **à vérifier** : une seule rafale de pages, sans signe fort : un navigateur ou un outil de surveillance peut faire cela. Ce verdict ne lève RIEN ; lisez les requêtes et décidez ;
- **incohérente** : l'adresse a changé pendant l'enquête : aucun verdict, relancer `--investigate` ;
- **sans trace** : plus aucune requête dans les journaux : l'historique des bannissements (jails fail2ban, journal des bannissements) est affiché.

Après la liste, la section **AUTRES POINTS À RE-VÉRIFIER** lance des contrôles en lecture seule et affiche la commande de chacun : adresses de l'équipe parmi les bannissements, jails fail2ban, adresses refusées par nginx qui ont aussi reçu des pages normales (faux positif possible), journaux utilisés, et les commandes à lancer à la main pour chaque adresse à vérifier. Ses sections 1 à 5 peuvent être copiées telles quelles pour une relecture.

Pour le lancer chaque matin, en root :

```
0 7 * * * root /root/scripts/nginx-log-audit.sh prod --unban-check --no-prompt
```

## Options
{{HELP}}
