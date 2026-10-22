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

## Options
{{HELP}}
