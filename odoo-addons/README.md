# Odoo modules shipped with rlq-admin-tools / Modules Odoo livrés avec rlq-admin-tools

## rlq_preload_statics

**EN** - Server-wide module (never installed in a database). The main process of Odoo lists the `static/` folders of every module of
`addons_path` once, before it starts its workers; every worker, the replaced ones included, inherits the list. Without it, each worker
builds the list the first time it serves a static file (about 10 s with ERPLibre). Enabled by `nginx-hardening.sh --update --odoo-preload-statics`
(adds this folder to `addons_path` and the module to `server_wide_modules`), then a restart of Odoo.

**FR** - Module « server-wide » (jamais installé dans une base). Le processus principal d'Odoo dresse une seule fois la liste des dossiers
`static/` de tous les modules d'`addons_path`, avant de démarrer ses workers ; chaque worker, y compris ceux qui sont remplacés, en hérite.
Sans lui, chaque worker la dresse au premier fichier statique qu'il sert (environ 10 s avec ERPLibre). Activé par
`nginx-hardening.sh --update --odoo-preload-statics` (ajoute ce dossier à `addons_path` et le module à `server_wide_modules`), puis un
redémarrage d'Odoo.
