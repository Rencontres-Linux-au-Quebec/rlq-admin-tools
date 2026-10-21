# app-health-check.py — health of nginx + application

Probes the web stack and reports `[OK]`, `[ATTN]`, `[FAIL]` per check: the application's health URL (`/web/health` for Odoo), key pages, TLS, sensitive files that must be refused, and the e-mail path for alerts (`--check-email-dns`, `--test-email`).

`--target` is required: `local` (from the server, through 127.0.0.1 and the local nginx) or `external` (through the public name).

```bash
app-health-check.py --target local
app-health-check.py --target external --report-err
app-health-check.py --check-email-dns            # SMTP relay, MX, SPF, DMARC, DKIM — prints the records to add
app-health-check.py --test-email                 # DNS checks, then really sends a test e-mail
app-health-check.py --create-config              # detect values on this server and write /etc/default/app-health-check.conf
```

## Configuration

`--create-config [PATH]` detects values (application, ports, names) and writes the default file (`--force` replaces an existing one after making a backup copy). Keys: `APP`, `LANGUAGE`, `TARGET`, `VERBOSE`. Application-specific behavior comes from the profile `apps/odoo.conf` / `apps/bbb.conf` (overridable in `/etc/default/nginx-tools-odoo.conf` / `-bbb.conf`).

## Options
{{HELP}}
