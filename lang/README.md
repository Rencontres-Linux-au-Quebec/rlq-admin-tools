# Traductions (dossier lang/)

Les programmes sont écrits en français ; l'affichage existe aussi en anglais, et **toute autre langue s'ajoute en ajoutant un fichier** - sans toucher au code.

## Format

Un catalogue par programme et par langue, au format **PO** (le format standard de gettext, lisible par Poedit, Weblate, Crowdin, les éditeurs de texte...) :

```
lang/PROGRAMME.XX.po        PROGRAMME = nom du programme sans extension (web-monitor, nginx-log-audit...), XX = code de langue (en, es, de...)
lang/_config.XX.po          messages communs à tous les programmes (fichier de configuration)
lang/_bbb.XX.po, _listes, _profile, _rapport, _i18n   messages des bibliothèques partagées
```

Chaque entrée :

```
msgid "Aucune connexion"        <- le fragment français tel qu'il est dans le code (ne pas le modifier)
msgstr "No connection"          <- la traduction ; vide = non traduit (le français reste affiché, jamais d'erreur)
```

* Les `msgid` sont des **morceaux de phrases** (le code assemble des phrases avec des variables) : garder les espaces de début et de fin, et l'ordre des morceaux.
* `msgstr` identique au `msgid` = valable dans les deux langues (nom propre, commande, expression régulière...).
* Les entrées marquées `#, fuzzy` sont ignorées.

## Programmes écrits en anglais (migration en cours)

Un programme dont le code est déjà en anglais est signalé par l'en-tête `"Source-Language: en\n"` dans `lang/PROGRAMME.fr.po` : les `msgid` sont alors les textes **anglais** du code et les `msgstr` leur traduction **française** (le fichier `PROGRAMME.en.po` n'existe plus). Les autres langues s'ajoutent de la même façon. Premier programme migré : `zip-versions.py`.

## Ajouter une langue

1. Copier `PROGRAMME.en.po` en `PROGRAMME.es.po` (par exemple), changer `"Language: en\n"` en `"Language: es\n"` et traduire les `msgstr`.
2. C'est tout : `--lang es`, la variable `PROGRAMME_LANG=es`, `LANGUAGE=es` dans `/etc/default/PROGRAMME.conf` ou les variables `LC_ALL` / `LANG` (`es_MX.UTF-8`...) l'utilisent.

## Vérifier

`python3 -m unittest test_i18n` (suite de tests) contrôle que chaque message du code a une entrée dans le catalogue anglais, que les traductions ne contiennent pas de français et que les en-têtes sont corrects.
