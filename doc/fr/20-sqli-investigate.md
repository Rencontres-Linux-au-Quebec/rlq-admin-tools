# sqli-investigate.py - enquête sur les injections SQL (lecture seule)

Relit les journaux d'accès nginx (fichiers courants, rotations et `.gz`), le journal de fail2ban et, avec `--odoo-log`, le journal d'Odoo.
Chaque requête dont l'URL **décodée** contient une tentative d'injection SQL est classée par famille : `union` (UNION SELECT), `error`
(EXTRACTVALUE, UPDATEXML, CONCAT(0x7e...)), `order-by` (ORDER BY n), `boolean` (' AND 1=1, ') AND ('...), `time` (SLEEP, BENCHMARK), `schema`
(information_schema, LOAD_FILE, INTO OUTFILE).

```bash
sqli-investigate.py                              # enquête avec les chemins par défaut
sqli-investigate.py --odoo-log /chemin/odoo.log  # ajoute les erreurs Odoo à 60 s de chaque tentative
sqli-investigate.py --jail nginx-sqli --top 10   # prison à examiner, dix adresses dans le résumé
sqli-investigate.py --report-err                 # rapport à copier-coller en cas de problème
```

## Ce qui est écrit

Seulement dans `--output` (dossier en mode 700, fichiers en mode 600), par défaut `/var/lib/sqli-investigate/AAAAMMJJ-HHMMSS` (le programme doit alors tourner en root) :

* `sqli-requests.tsv` : chaque tentative (heure, adresse, méthode, code HTTP, taille, famille, référent, agent, URL décodée, fichier lu).
* `sqli-summary.txt` : adresses les plus actives, réponses, agents, bannissements et réponses reçues après chaque bannissement.
* `sqli-bans.txt` : événements de la prison et état donné par `fail2ban-client status`.

## Ce que le programme ne fait pas

* Il ne bannit, ne débanit, ne redémarre rien et ne modifie aucune configuration.
* Une réponse 200 ne prouve **pas** l'absence d'injection : seules les requêtes SQL exécutées dans PostgreSQL le prouvent.
* La famille `boolean` est heuristique : relire `sqli-requests.tsv` avant de conclure.

## Configuration

`/etc/default/sqli-investigate.conf` puis `~/.sqli-investigate.conf` (le dernier lu gagne ; la ligne de commande prime). Exemple : `doc/fr/sqli-investigate.conf.example`.
Clés : `ACCESS_LOG`, `FAIL2BAN_LOG`, `JAIL`, `LANGUAGE`, `NO_LOOKUP`, `ODOO_LOG`, `OUTPUT`, `TOP`.

## Pourquoi pas collect-all-advise.sh

`collect-all-advise.sh` anonymise par défaut, ne lit que les détails des codes 4xx, ne relit pas la prison fail2ban et ne voit pas les
requêtes SQL elles-mêmes. Ce programme répond aux questions de l'enquête : qui a tenté quoi, quand, avec quelle réponse, et ce qui s'est passé
après le bannissement.
