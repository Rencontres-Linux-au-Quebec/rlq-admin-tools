# odoo-docs.py — publish this documentation inside Odoo

Writes the documentation (`docs/en`, `docs/fr`) **into Odoo itself**, through the external API (XML-RPC with an API key), so it stays up to date with the programs: each page embeds the real `--help` of its program. Two targets, chosen with `--target`:

| Target | Where | Needs |
|---|---|---|
| `wiki` | pages of the OCA module **document_page** (repository *OCA/knowledge*): root category → *English* / *Français* → one page per document | `document_page` installed |
| `website` | website pages `/docs/<lang>/<page>` (QWeb view + `website.page`) | `website` installed |

```bash
odoo-docs.py --check --target wiki          # validate only: nothing published
odoo-docs.py --target wiki --dry-run        # show what would be created / updated
odoo-docs.py --target wiki                  # publish (idempotent: re-run at each release)
odoo-docs.py --target website               # same content as website pages
```

## Validation before writing (wiki)

The program refuses to write unless it has verified that `document_page` is **installed and works**: module state `installed` (version shown); models `document.page` and `document.page.history`; fields `name`, `type`, `parent_id`, `content` (writable); `create` / `write` / `unlink` rights of the account; then a **real round trip** on a temporary category and page (create, edit, read back, history count, delete — deleted even on failure). `--dry-run` skips the write test.

## Configuration

`/etc/default/odoo-docs.conf`, then `~/.odoo-docs.cfg` (keys `API_KEY`, `DB`, `DOCS_DIR`, `LANGUAGE`, `LOGIN`, `ROOT`, `TARGET`, `URL`; model: `doc/odoo-docs.conf.example`). The API key (`chmod 600`) may also come from `ODOO_API_KEY`. Updates are idempotent: a page is found by name and parent and rewritten only when its content changed (revision summary `odoo-docs.py <version>`).

## Options
{{HELP}}
