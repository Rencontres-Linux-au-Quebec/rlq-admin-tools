Copyright (C) 2026 Services-Conseils Linux Inc.
Copyright (C) 2026 Rencontres Linux au Québec contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

The configuration templates (`doc/*.conf.example`, `apps/*.conf`) carry no copyright notice: copy and adapt them freely.

## Folders / Dossiers

* `doc/` — used **by the programs**: change logs (`--changelog`), configuration templates (`*.conf.example`, copied to `/etc/default`), `nginx-tools.version`, maintainers' notes.
  Utilisé **par les programmes** : journaux (`--changelog`), modèles de configuration (`*.conf.example`, copiés dans `/etc/default`), `nginx-tools.version`, notes des responsables.
* `docs/` — the administrator **manual** (Markdown `en/` and `fr/`, `build_docs.py` → GitHub pages and the Odoo module `rlq_tools_docs`); no program reads it.
  Le **manuel** de l'administrateur (Markdown `en/` et `fr/`, `build_docs.py` → pages GitHub et module Odoo `rlq_tools_docs`) ; aucun programme ne le lit.
