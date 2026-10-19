# nginx-log-audit.sh — rapport des journaux nginx, enquêtes, bannissements

Lit les journaux d'accès nginx (journal du site `dev`, `lab` ou `prod` ; défaut : le profil détecté) et produit un rapport numéroté : robots, refus, attaques, recherche de fichiers sensibles, rafales, requêtes parallèles, identités de robots changeantes, puis propose de bannir les fautifs. Il garde une position de lecture : chaque exécution analyse **ce qui est nouveau** (`--init` relit le fichier actif, `--init-all` tout l'historique avec les rotations).

```bash
nginx-log-audit.sh prod                    # rapport, puis proposition de bannissements
nginx-log-audit.sh prod --last 24 --no-prompt
nginx-log-audit.sh --investigate 203.0.113.7   # enquête sur tout l'historique + propriétaire du bloc (RDAP)
nginx-log-audit.sh --evidence 203.0.113.7      # preuves pour/contre un bannissement, lecture seule
sudo nginx-log-audit.sh --ban 203.0.113.7      # preuves affichées, confirmation demandée (--yes pour l'éviter)
nginx-log-audit.sh --export-bans > bans.txt ; nginx-log-audit.sh --import-bans bans.txt
nginx-log-audit.sh --stats --details       # statistiques : codes, IP, agents utilisateurs, appareils
```

## Comment un bannissement est décidé

Les indices sont comptés par adresse : recherche de chemins sensibles, rafales de pages (`--page-burst` : pages distinctes en 10 s), requêtes dynamiques parallèles dans la même seconde (`--parallel-threshold`, section 11), nombreuses identités de robot depuis une adresse (`--ua-rotation-threshold`). Un bannissement est *suggéré* à partir de `--ban-threshold` indices (défaut 3). Les adresses de la liste blanche ou des lieux `[protégée]` ne sont jamais proposées. Les bannissements manuels sont réévalués par `--unban-check` (la levée est suggérée si elle n'est plus justifiée).

Les refus produits par nos règles nginx sont journalisés dans `blocked-probes.log`, pas dans les journaux des sites ; les enquêtes et les preuves le lisent aussi (« Requêtes REFUSÉES par nginx »), sinon une adresse bannie semblerait n'avoir fait aucune requête.

## Options
{{HELP}}
