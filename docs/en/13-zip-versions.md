# zip-versions.py — versions inside release archives

Reads `.zip` archives **without extracting them** and reports the versions of the programs, configuration and Odoo modules they hold (`__version__`, `SCRIPT_VERSION`, `VERSION`, module manifests, changelogs), designates the **most recent archive of each type**, and checks that an archive's *name* and *content* agree on MAJOR.MINOR (e.g. `nginx-tools.1.111.zip` ↔ `doc/nginx-tools.version`; test archive ↔ `run-all.sh`).

```bash
zip-versions.py ~/Downloads                   # section “ARCHIVES TO ATTACH”
zip-versions.py --installed /root/scripts --nginx-dir /etc/nginx   # compare with what is installed
```

Archive naming: program name, then `MAJOR.MINOR` without the date (`nginx-tools.1.111.zip`, `nginx-tools-tests.1.170.zip`, `rlq_survey_report.18.0.1.107.0.zip`); the top-level folder inside has **no version** (`nginx-tools/`). A generic name such as `tests.zip` would overwrite other programs' `tests/` folder.

## Options
{{HELP}}
