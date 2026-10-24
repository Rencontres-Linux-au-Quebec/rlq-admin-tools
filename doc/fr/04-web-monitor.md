# web-monitor.py - orchestrateur, sommaires et corrections en une question

Lance les outils de la suite selon un horaire, **n'alerte que s'il faut agir**, et fournit un sommaire numéroté du trafic et de la sécurité. C'est le programme par lequel commencer sur un nouveau serveur et celui à mettre sur une minuterie.

```bash
web-monitor.py --install-timer --interval-hours 1   # minuterie systemd, un passage par heure
web-monitor.py --status                             # état de la minuterie, dernier passage, dernière alerte
web-monitor.py --summary --days 7                   # trafic, blocages et attaques, erreurs, requêtes par nom DNS, faits saillants, couverture des journaux
web-monitor.py --apply                              # fait les corrections recommandées, une question par correction
web-monitor.py --apply --yes                        # idem, sans questions
web-monitor.py --list-users --table --sort last --reverse   # identifiants Odoo (ou participants BBB) avec leur trafic
web-monitor.py --unban-check                        # réévalue les bannissements manuels
```

## Ce que fait un passage

1. Lance `nginx-log-audit.sh`, `app-health-check.py`, `app-log-check.py` et vérifie bannissements, minuteries et courriel.
2. Décide si quelque chose demande de l'attention ; si oui, envoie l'alerte par courriel (relais configuré par `nginx-hardening.sh`, étape 0d) et mémorise les IP recommandées.
3. Dans un terminal, propose de bannir les adresses recommandées (`--no-prompt` pour l'éviter) et d'ouvrir le rapport complet dans `less` (`--no-pager`).

`--dry-run` montre la décision sans envoyer de courriel ni déplacer les positions de lecture ; avec `--save-recommended` il mémorise quand même les IP recommandées (utilisé par la touche `b` d'`app-log-live.py`).

## Les recommandations sont vérifiées

Une recommandation donne la **vraie cause** : le programme évalue lui-même les blocs `location ~` de `nginx -T` pour chaque chemin qui traverse nginx (« règle manquante » != « bloc server qui n'inclut pas le fragment »). Les corrections disponibles par `--apply` comprennent bannissements, rechargement de nginx, `nginx-hardening.sh --update` et réparation de minuterie. Une minuterie qui vise un fichier de configuration inexistant est signalée.

## Un utilisateur connecté n'est pas digne de confiance d'office

Le sommaire a une section **ACTIVITÉ SUSPECTE D'UTILISATEURS CONNECTÉS** : chaque compte qui s'est connecté reçoit un score fait d'indices qui ont chacun une explication innocente - seule leur somme mérite l'attention.

| Indice | Points |
|---|---|
| URL malveillantes demandées (fichiers sensibles, injections, PHP...) | 3 |
| rafale de pages (15 pages distinctes ou plus en 10 s), outil de script dans le User-Agent, accès refusés par Odoo pour son UID, formulaires soumis en masse, adresse partagée par plusieurs comptes portail, adresse bannie, courriel jetable | 2 chacun |
| connexions échouées, réinitialisations du mot de passe, 6 adresses ou plus, beaucoup d'erreurs 4xx, nouveau compte (première connexion depuis moins de 7 jours), domaine du courriel mal écrit | 1 chacun |

2 à 3 = *à surveiller*, 4 et plus = *suspect*. Les comptes surveillés sont toujours listés.

```bash
web-monitor.py --suspect-users                      # les comptes de la section, puis : enquêter [N] / [a] tous
web-monitor.py --investigate-user user@example.org  # un compte : fiche Odoo, TOUTES ses adresses IP, activité, courriel, Internet
web-monitor.py --watch-odoo-user user@example.org   # toujours listé, marqué [surveillé] dans app-log-live.py
web-monitor.py --ban-odoo-user user@example.org     # enquête, puis confirmation
web-monitor.py --unban-odoo-user user@example.org   # compte rétabli, adresses débannies
```

**Enquête.** Le compte dans Odoo (création, fournisseur OAuth, connexions, inscriptions, messages, sondages), chaque adresse IP utilisée (examinée par `nginx-log-audit.sh --investigate`, avec les autres comptes vus sur cette adresse), son activité sur tout l'historique conservé, son adresse courriel (syntaxe, faute de frappe, domaine jetable, serveur de courriel du domaine) et - seulement après un oui, ou avec `--internet` - Internet : StopForumSpam (signalements de spam du courriel et des adresses), Gravatar, une recherche Web de l'adresse exacte. Ces recherches envoient l'adresse à des tiers ; `NGINX_TOOLS_INTERNET=off` les désactive.

**Bannissement.** Le compte Odoo est **archivé** (plus de connexion, les sessions ouvertes se terminent, le courriel ne peut plus servir à créer un compte) et les adresses utilisées par *aucun autre compte* sont bannies au pare-feu (`nginx-log-audit.sh --ban`). Les comptes internes, l'administrateur et l'utilisateur public ne sont jamais archivés - dans le programme et dans le SQL lui-même. Tout est consigné dans `/var/lib/nginx-tools/odoo-users.tsv` (`apps/_odoo_users.py`), que `--unban-odoo-user` utilise pour annuler et qui dit à `nginx-log-audit.sh` que les adresses d'un compte banni ne sont plus « un utilisateur légitime ».

## Notes

* Une redirection (3xx, petite page) de nginx vers une URL malveillante est un **rejet** pour le moniteur.
* `--list-users` sur Odoo lit PostgreSQL (root) ; « Odoo n'enregistre pas la fin d'une session », donc *connecté* signifie « connecté, non déconnecté, actif depuis peu de minutes ».

* `--list-users --table` montre aussi, par compte, les **pages lues**, les **pages écrites** (formulaires et enregistrements envoyés - pas les lectures du client web d'Odoo), les **Mo reçus** (ce que nginx a transmis) et les **Mo envoyés** (taille de ses requêtes ; il faut `rl=$request_length` à la fin du format `combined_host`, nginx-odoo-config 1.11 - `?` sinon). `--sort written|received|sent`.
* `--list-users --table` est un tableau **compact** : aucune espace autour des cellules, chaque colonne aussi étroite que son contenu (titres coupés, au moins 4 caractères, sur deux lignes s'ils ont deux mots). Champs : `num,uid,ip,ipseen,ipcountry,vpn,name,login,created,first,last,logins,minutes,type,events,surveys,phone,country,city,groups,tags,systems,browsers,read,written,received,sent,email` - les choisir et les ordonner avec `--table-fields` (`all` = tous ; par défaut tous sauf `tags` et `email`). **IP vue** : l'adresse du compte qui a fait la requête la plus récente dans les journaux nginx, même sans nouvelle connexion (`--sort seen`). **Pays IP** : pays du propriétaire de chaque bloc d'adresses d'après RDAP / whois (le registre, pas une géolocalisation ; en jaune s'il diffère du pays du contact Odoo). **VPN** : le propriétaire du bloc est un VPN connu, Tor, un relais (iCloud Private Relay, Cloudflare WARP) ou un hébergeur (centre de données) - une déduction d'après le nom du propriétaire, pas une preuve (`--sort vpn`) ; chaque adresse est cherchée une fois sur Internet (rdap.org, sinon whois), puis servie par le cache des adresses pendant 90 jours (`NGINX_TOOLS_INTERNET=off` : le cache seulement). **Compte créé** : date de création du compte Odoo, en cyan s'il a moins de 7 jours (`--sort created`). Une ligne sur 5 est soulignée. Le titre de la colonne triée est en cyan. Chaque réglage a sa clé dans le fichier de configuration (`TABLE_FIELDS`, `SORT`, `STATS`, `GROUP`, `CSV`...) ; les actions (`--apply`, `--ban-*`, `--list-users`) restent sur la ligne de commande. Événements = inscriptions non annulées, sondages = sondages complétés ; groupes = ceux créés dans Odoo ou par un module `rlq_*`. Dans un terminal : dernière connexion d'aujourd'hui en vert, compte créé aujourd'hui en cyan, les comptes les plus actifs en jaune.
* `--group NOM` (membres d'un groupe Odoo, accents ignorés), `--csv FICHIER` (toutes les valeurs, jamais coupées ; séparateur `;`, virgule décimale en français : Excel l'ouvre directement), `--repeat-header` (titres aussi en bas), `--stats` (membres par groupe et par étiquette, interne / portail, pays, domaines de courriel, systèmes, navigateurs, les 10 comptes les plus actifs).

## Options
{{HELP}}
