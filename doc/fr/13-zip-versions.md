# zip-versions.py — versions contenues dans les archives livrées

Lit des archives `.zip` **sans les extraire** et rapporte les versions des programmes, de la configuration et des modules Odoo qu'elles contiennent (`__version__`, `SCRIPT_VERSION`, `VERSION`, manifestes de modules, journaux), désigne **l'archive la plus récente de chaque type**, et vérifie que le *nom* et le *contenu* d'une archive concordent sur MAJEUR.MINEUR (ex. `nginx-tools.1.111.zip` ↔ `doc/nginx-tools.version` ; archive de tests ↔ `run-all.sh`).

```bash
zip-versions.py ~/Téléchargements             # section « ARCHIVES À JOINDRE »
zip-versions.py --installed /root/scripts --nginx-dir /etc/nginx   # comparer avec ce qui est installé
```

Nom des archives : nom du programme, puis `MAJEUR.MINEUR` sans la date (`nginx-tools.1.111.zip`, `nginx-tools-tests.1.170.zip`, `rlq_survey_report.18.0.1.107.0.zip`) ; le dossier de premier niveau n'a **aucune version** (`nginx-tools/`). Un nom générique comme `tests.zip` écraserait le dossier `tests/` d'autres programmes.

## Options
{{HELP}}
