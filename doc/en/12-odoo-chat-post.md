# odoo-chat-post.py - Discuss alert channels and a restricted bot

Creates, through Odoo's external API (XML-RPC with an API key - no PostgreSQL access), the **channels and threads** of the team's alerts in Discuss, each with a first message explaining its purpose, and publishes alerts into them. The catalog is a JSON file (`doc/odoo-chat-post.catalogue.json`): security, e-mails, backups, updates, event day, plus one set of threads per event (`--event JPOL26` -> `JPOL26-Inscriptions`, `JPOL26-Sondages`).

```bash
odoo-chat-post.py --list                                         # catalog: present or absent
odoo-chat-post.py --create --dry-run --suggested                 # preview
odoo-chat-post.py --create --members you@example.org,tux-bot     # RESTRICTED: only these accounts see/are members
odoo-chat-post.py --post "Odoo-Erreurs/HTTP 5xx" --message "5xx burst at 14:02"
echo "text" | odoo-chat-post.py --post "Odoo-Erreurs/HTTP 5xx" --message -
```

* `--create` only creates what is missing; it never modifies an existing channel.
* Access: by default the group `base.group_user` (all internal users); `--members` makes it restricted to listed logins and **creates a restricted group** "Team alerts (odoo-chat-post)".

## The bot account

`--create-bot` creates an internal user with **no right other than writing in those channels**. On the first run it also creates its API key (one year if Odoo allows it, else 7 days) and writes `LOGIN` / `API_KEY` to `/etc/default/odoo-chat-post.conf` (mode 600, previous version backed up; repeat `--bot-config` for other programs' files). `--renew-key` issues a new key (the old one stays valid until it expires). Odoo cannot create API keys through the external API, so the program signs in with a web session and replays the "API key" wizard - if your Odoo version differs, create the key by hand in *Preferences -> Account security* and put it in the file.

## Options
{{HELP}}
