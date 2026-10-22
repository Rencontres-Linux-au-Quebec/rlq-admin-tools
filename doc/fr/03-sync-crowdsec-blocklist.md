# sync-crowdsec-blocklist.sh — liste communautaire CrowdSec au pare-feu

Télécharge la liste communautaire de CrowdSec et la charge dans **deux ipsets** (`crowdsec-blocklist-v4`, `-v6`) rejetés par le pare-feu (règles iptables ou crochet `ufw`). L'agent CrowdSec n'est pas nécessaire.

* **Chargement atomique** par `ipset swap` : l'ensemble n'est jamais vide ni partiel ; nginx n'est pas rechargé.
* **Protection contre une liste tronquée** : `--min-ips` refuse une liste plus petite que prévu ; l'ensemble précédent reste en place.
* **Les adresses de confiance ne sont jamais bloquées** (liste blanche, lieux `[protégée]`).
* Lancement par cron (`--install-cron --cron-hours N`) et survie à `ufw reload` avec `--ufw-hook`.

```bash
sync-crowdsec-blocklist.sh --dry-run          # télécharge et analyse, ne change rien
sync-crowdsec-blocklist.sh                    # synchroniser maintenant
sync-crowdsec-blocklist.sh --install-cron --cron-hours 6 --ufw-hook
sync-crowdsec-blocklist.sh --status           # dernière synchronisation, échec en cours, taille, IP protégées
sync-crowdsec-blocklist.sh --blocked --top 20 # adresses réellement rejetées (compteurs du pare-feu)
sync-crowdsec-blocklist.sh --uninstall        # retire cron, règles et ipsets
```

`app-log-live.py` marque les adresses présentes dans ces ensembles `[banni : CrowdSec]` (une entrée `nomatch` est une exception).

## Options
{{HELP}}
