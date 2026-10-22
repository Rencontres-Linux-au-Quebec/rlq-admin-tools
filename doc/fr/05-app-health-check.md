# app-health-check.py — santé de nginx + application

Sonde la pile web et affiche `[OK]`, `[ATTN]`, `[FAIL]` par contrôle : l'URL de santé de l'application (`/web/health` pour Odoo), les pages clés, TLS, les fichiers sensibles qui doivent être refusés, et le chemin du courriel d'alerte (`--check-email-dns`, `--test-email`).

`--target` est obligatoire : `local` (depuis le serveur, par 127.0.0.1 et le nginx local) ou `external` (par le nom public).

```bash
app-health-check.py --target local
app-health-check.py --target external --report-err
app-health-check.py --check-email-dns            # relais SMTP, MX, SPF, DMARC, DKIM — affiche les enregistrements à ajouter
app-health-check.py --test-email                 # contrôles DNS, puis envoi réel d'un courriel d'essai
app-health-check.py --create-config              # détecte les valeurs de ce serveur et écrit /etc/default/app-health-check.conf
```

## Configuration

`--create-config [CHEMIN]` détecte les valeurs (application, ports, noms) et écrit le fichier par défaut (`--force` remplace un fichier existant après en avoir fait une copie de sauvegarde). Clés : `APP`, `LANGUAGE`, `TARGET`, `VERBOSE`. Le comportement propre à l'application vient du profil `apps/odoo.conf` / `apps/bbb.conf` (modifiable dans `/etc/default/nginx-tools-odoo.conf` / `-bbb.conf`).

## Options
{{HELP}}
