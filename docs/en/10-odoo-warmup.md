# odoo-warmup.py — warm Odoo's caches after a restart

After a restart the first visitors pay for compiling assets, loading registries and rendering pages. This program requests, in order: public pages (in each site language), linked pages, assets, then — with an administration login — the web client, menus, `get_views` of the main models, and the public pages of the latest events and surveys. Calls to the administration API are repeated in parallel (`--repeat`) because an Odoo with several workers warms one process per request.

```bash
odoo-warmup.py                              # warm http://127.0.0.1:8069 (bypasses nginx)
odoo-warmup.py --wait 300 --latest 5 --links 6 --site-languages fr,en
odoo-warmup.py --systemd-install --service erplibre.service   # run after every start of the unit
odoo-warmup.py --systemd-remove
```

## Administration warm-up

Create a dedicated Odoo user and an API key stored in a file with mode 0600; set `LOGIN`, `KEY_FILE`, `DB` in `/etc/default/odoo-warmup.conf`. Without them only public pages are warmed. Extra public paths: one per line in `/etc/default/odoo-warmup-pages.conf` (created at first run).

## Options
{{HELP}}
