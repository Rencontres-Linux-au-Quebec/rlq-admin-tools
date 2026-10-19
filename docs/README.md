# Documentation sources / Sources de la documentation

Bilingual administrator documentation of the suite. `en/` and `fr/` hold the same pages (same file names); `{{HELP}}` is replaced by each program's real `--help`, so the option lists cannot go stale.

```bash
python3 docs/build_docs.py --check            # validate (needs python3-markdown)
python3 docs/build_docs.py --out /tmp/docs    # Markdown in /tmp/docs/build/<lang>/, Odoo module in /tmp/docs/rlq_tools_docs/
```

## Publishing on an Odoo website (Odoo 18 Community, module `website`)

Odoo's *Knowledge* app is Enterprise-only; on Community the documentation is published as **website pages**:

1. Build, zip the generated `rlq_tools_docs/` folder and unpack it into an addons path (or use `odoo-update-module.sh --zip … --module rlq_tools_docs`).
2. Install it once (Apps → Update Apps List → *nginx-tools documentation*). Pages appear at `/docs/en/<page>` and `/docs/fr/<page>`; `/docs/en` and `/docs/fr` redirect to the first page.
3. To refresh after a release: rebuild and update the module (`odoo-update-module.sh --module rlq_tools_docs`). **Edits made in the website editor are overwritten by an update** — change the Markdown sources instead.

The Markdown files themselves are the GitHub documentation.
