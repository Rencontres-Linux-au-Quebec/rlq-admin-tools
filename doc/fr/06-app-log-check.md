# app-log-check.py - analyse du journal d'Odoo

Lit le journal systemd du service Odoo (détecté parmi `erplibre.service`, `erplibre_erplibre.service` ; ou `--service` ; `--namespace` si l'unité utilise `LogNamespace=`) et classe ce qu'il trouve en sections numérotées : attaques de protocole, traces Python regroupées par signature [2], autres erreurs [3], bruit connu, diagnostics [5], courriels non envoyés.

Par défaut il analyse ce qui est nouveau depuis la dernière exécution ; `--init` prend tout l'historique disponible ; `--last HEURES` limite la fenêtre.

```bash
app-log-check.py                        # nouveautés depuis la dernière exécution
app-log-check.py --errors-only --full-trace
app-log-check.py --by-hour --days 7 --top 15   # problèmes par heure et par jour ; n'utilise ni ne déplace la position sauvegardée
```

## Lire `--by-hour`

Il rapporte erreurs, pages d'erreur et « Session expired » avec leurs pointes. Un flot de milliers de lignes « Session expired » vient généralement d'**un onglet resté ouvert**, pas d'un défaut du serveur : le rapport dit si un client ou plusieurs sont en cause et si les pointes coïncident avec des redémarrages. Deux adresses pour un même compte signifient un compte sur deux postes, pas « plusieurs clients » ; Odoo CE permet plusieurs sessions simultanées par compte : si une connexion sur un poste en invalide une autre, chercher un module.

## Courriels non envoyés

Causes typiques diagnostiquées (lecture seule ; Odoo n'est jamais modifié) : 452 « Maximum number of messages per session » (réduire `mail.session.batch.size`), 503 « Multiple MAIL commands » (cascade du 452), expéditeur rejeté (serveur sortant avec *Filtre De*, `mail.default.from`, `mail.catchall.domain`). Utiliser `odoo-mail-retry.py` pour les renvoyer.

## Options
{{HELP}}
