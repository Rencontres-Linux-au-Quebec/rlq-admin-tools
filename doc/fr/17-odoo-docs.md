# odoo-docs.py — publier cette documentation dans Odoo

Écrit la documentation (`docs/en`, `docs/fr`) **dans Odoo lui-même**, par l'API externe (XML-RPC avec une clé d'API), afin qu'elle reste à jour avec les programmes : chaque page contient le vrai `--help` de son programme. Deux cibles, choisies avec `--target` :

| Cible | Où | Prérequis |
|---|---|---|
| `wiki` | pages du module OCA **document_page** (dépôt *OCA/knowledge*) : catégorie racine → *English* / *Français* → une page par document | `document_page` installé |
| `website` | pages du site web `/docs/<langue>/<page>` (vue QWeb + `website.page`) | `website` installé |

```bash
odoo-docs.py --check --target wiki          # valider seulement : rien n'est publié
odoo-docs.py --target wiki --dry-run        # montrer ce qui serait créé / mis à jour
odoo-docs.py --target wiki                  # publier (idempotent : à relancer à chaque version)
odoo-docs.py --target website               # même contenu en pages du site web
```

## Validation avant d'écrire (wiki)

Le programme refuse d'écrire sans avoir vérifié que `document_page` est **installé et fonctionne** : module à l'état `installed` (version affichée) ; modèles `document.page` et `document.page.history` ; champs `name`, `type`, `parent_id`, `content` (modifiable) ; droits `create` / `write` / `unlink` du compte ; puis un **essai réel** sur une catégorie et une page temporaires (création, modification, relecture, nombre de versions d'historique, suppression — supprimées même en cas d'échec). `--dry-run` saute l'essai d'écriture.

## Configuration

`/etc/default/odoo-docs.conf`, puis `~/.odoo-docs.conf` (clés `API_KEY`, `DB`, `DOCS_DIR`, `LANGUAGE`, `LOGIN`, `ROOT`, `TARGET`, `URL` ; modèle : `doc/odoo-docs.conf.example`). La clé API (`chmod 600`) peut aussi venir de `ODOO_API_KEY`. Les mises à jour sont idempotentes : une page est trouvée par nom et parent, et réécrite seulement si son contenu a changé (résumé de révision `odoo-docs.py <version>`).

## Options
{{HELP}}
