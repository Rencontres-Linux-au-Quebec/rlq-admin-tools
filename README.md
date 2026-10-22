Copyright (C) 2026 Services-Conseils Linux Inc.
Copyright (C) 2026 Rencontres Linux au Québec contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

The configuration templates (`doc/*.conf.example`, `apps/*.conf`) carry no copyright notice: copy and adapt them freely.

## Folders / Dossiers

* `CHANGELOG.md` — the change log, one section per program (`--changelog` shows the program's own section).
* `doc/` — `doc/en/` and `doc/fr/`: manual, configuration templates (`*.conf.example`, copied to `/etc/default`), `build_docs.py`; `doc/` also holds `nginx-tools.version` and maintainers' notes.
  Utilisé **par les programmes** : `CHANGELOG.md` (journal, `--changelog`), `doc/en/` et `doc/fr/` (modèles de configuration `*.conf.example`, copiés dans `/etc/default`, manuel, `build_docs.py`).
* `doc/en/` and `doc/fr/` — the administrator **manual** (Markdown, `build_docs.py` → GitHub pages and the Odoo module `rlq_tools_docs`); no program reads it.
  Le **manuel** de l'administrateur (Markdown `en/` et `fr/`, `build_docs.py` → pages GitHub et module Odoo `rlq_tools_docs`) ; aucun programme ne le lit.
