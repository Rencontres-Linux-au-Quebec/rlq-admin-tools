# odoo-warmup.py - préchauffer les caches d'Odoo après un redémarrage

Après un redémarrage, les premiers visiteurs paient la compilation des assets, le chargement des registres et le rendu des pages. Ce programme demande, dans l'ordre : les pages publiques (dans chaque langue du site), les pages liées, les assets, puis - avec un identifiant d'administration - le client web, les menus, les `get_views` des principaux modèles, et les pages publiques des derniers événements et sondages. Les appels d'administration sont répétés en parallèle (`--repeat`) parce qu'un Odoo à plusieurs workers ne préchauffe qu'un processus par requête.

```bash
odoo-warmup.py                              # préchauffe http://127.0.0.1:8069 (contourne nginx)
odoo-warmup.py --wait 300 --latest 5 --links 6 --site-languages fr,en
odoo-warmup.py --systemd-install --service erplibre.service   # exécuté après chaque démarrage de l'unité
odoo-warmup.py --systemd-remove
```

## Préchauffage de l'administration

Créer un utilisateur Odoo dédié et une clé d'API dans un fichier de droits 0600 ; renseigner `LOGIN`, `KEY_FILE`, `DB` dans `/etc/default/odoo-warmup.conf`. Sans eux, seules les pages publiques sont préchauffées. Chemins publics supplémentaires : un par ligne dans `/etc/default/odoo-warmup-pages.conf` (créé au premier lancement).

## Plusieurs workers

Odoo compile les gabarits QWeb d'une page dans chaque worker, la première fois que ce worker la montre. Les pages chargées sont donc redemandées par plusieurs files en parallèle, chacune avec sa propre session (`WORKER_LANES`, `--worker-lanes`). Par défaut, il y a une file pour deux workers : les autres workers restent libres pour les visiteurs qui arrivent pendant le préchauffage. `0` désactive cette étape.

Les fichiers statiques sont demandés directement à Odoo. Avec le module serveur `rlq_preload_statics` (dépôt rlq-odoo-addons), le processus maître d'Odoo dresse la liste des dossiers static avant de lancer les workers : chaque fichier n'est alors demandé qu'une fois, pour vérifier. Sans ce module, chaque fichier est demandé deux fois par worker.

Chaque préchauffage est noté dans `/var/lib/odoo-warmup/runs` : `app-log-live.py` nomme ses requêtes « odoo-warmup.py » et les résume en une ligne (`--warmup-lines` pour les voir une par une).

## Options
{{HELP}}
