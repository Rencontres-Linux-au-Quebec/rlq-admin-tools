# Changelog

Version numbers follow `MAJOR.MINOR.YYYYMMDD.HHMMSS` (local time of the change).
Each program has its own section; the most recent version comes first.
Earlier history was archived outside this repository when this file was created.

## app-health-check.py

### 2.26.20261020.211944

- Current version. Earlier history archived outside the repository.

## app-log-check.py

### 2.24.20261022.012000

- Title: Settings key: BY_HOUR.
- Reason: Reason: the report mode --by-hour is a setting that can stay in the file; --last remains a one-shot window and stays on the command line.
- Changes:
  - SCHEMA_CONFIG: new key BY_HOUR (--by-hour).
  - doc/en and doc/fr app-log-check.conf.example: BY_HOUR added.
  - --init and --last remain command-line only (actions / one-shot filter).
- Bugs fixed:
  None in this change.
- Guard rails and edge cases:
  - Absent or empty BY_HOUR keeps the report default.
- Checks:
  - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 2.23.20261020.211944

- Current version. Earlier history archived outside the repository.

## app-log-live.py

### 1.95.20261022.012000

- Title: Settings keys: SUMMARY, and UNDERLINE documented in the default files.
- Reason: Reason: the owner wants every changeable setting available in the configuration file, and default files that list every variable (commented). UNDERLINE was missing from default files created before the key existed.
- Changes:
  - SCHEMA_CONFIG: new key SUMMARY (--summary: session summary at the end of a --no-follow run).
  - doc/en and doc/fr app-log-live.conf.example: SUMMARY added. UNDERLINE was already in the code and in both examples (verified).
  - Action-only options stay on the command line: --diagnose, --diagnose-host, --modules, --modules-latest, --no-follow, --rate-limit, --record-test-log, --keep-ip (hidden legacy option).
- Bugs fixed:
  - Symptom: UNDERLINE absent from /etc/default/app-log-live.conf. Diagnosis: the file was created before the key existed, and an existing file is never completed automatically. Fix: add the line by hand (see Action required).
- Guard rails and edge cases:
  - A key that is absent or empty keeps the default (UNDERLINE=5, SUMMARY off).
  - Command-line options still take precedence over the file.
- Checks:
  - py_compile and ruff on the program; test_cles_modeles (every schema key is present in both examples).
- Action required: Add `UNDERLINE=5` and `SUMMARY=non` to /etc/default/app-log-live.conf if you want them written in the file (new installs get them automatically).

### 1.94.20261021.095843

- Current version. Earlier history archived outside the repository.

## host-perf-audit.py

### 1.4.20261020.211944

- Current version. Earlier history archived outside the repository.

## odoo-chat-post.py

### 1.9.20261022.012000

- Title: Settings keys: BOT_LOGIN and CATALOG.
- Reason: Reason: every setting in the command line gets a key; actions remain on the command line.
- Changes:
  - SCHEMA_CONFIG: new keys BOT_LOGIN (--bot-login) and CATALOG (--catalog).
  - doc/en and doc/fr odoo-chat-post.conf.example: both added.
  - Command-line only (actions or per-run inputs): --bot-config, --create, --create-bot, --dry-run, --list, --message, --post, --renew-key.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases:
  - An empty CATALOG= line is ignored (the shipped catalogue is used).
- Checks:
  - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.8.20261020.211944

- Current version. Earlier history archived outside the repository.

## odoo-docs.py

### 1.4.20261020.211944

- Current version. Earlier history archived outside the repository.

## odoo-mail-retry.py

### 1.15.20261022.012000

- Title: The common file now reaches LOG_KEEP_DAYS and ANONYMIZE.
- Reason: Reason: same as odoo-warmup.py: the common-file filter discarded LOG_KEEP_DAYS and ANONYMIZE.
- Changes:
  - read_config(): the common file accepts LOG_KEEP_DAYS and ANONYMIZE; both are exported to the environment (environment wins).
- Bugs fixed:
  - Symptom: ANONYMIZE in app-default.conf ignored. Diagnosis and fix as in odoo-warmup.py.
- Guard rails and edge cases:
  - Invalid ANONYMIZE value reported and ignored.
- Checks:
  - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.14.20261020.211944

- Current version. Earlier history archived outside the repository.

## odoo-warmup.py

### 1.10.20261022.012000

- Title: The common file now reaches LOG_KEEP_DAYS and ANONYMIZE.
- Reason: Reason: app-default.conf defines five common keys (apps/_config.py CLES_COMMUNES), but this program read only LANGUAGE, VERBOSE and DEBUG_LEVEL from it.
- Changes:
  - read_config(): the common file accepts LOG_KEEP_DAYS and ANONYMIZE.
  - LOG_KEEP_DAYS and ANONYMIZE are exported as NGINX_TOOLS_LOG_KEEP_DAYS and NGINX_TOOLS_ANONYMIZE (only if not already set in the environment).
  - Comment updated to list the five keys.
- Bugs fixed:
  - Symptom: ANONYMIZE=yes in app-default.conf had no effect on odoo-warmup. Diagnosis: the common-file filter discarded every key except three. Fix: accept the two keys.
- Guard rails and edge cases:
  - An environment variable already set wins over the file.
  - An invalid ANONYMIZE value is reported and ignored.
- Checks:
  - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.9.20261020.211944

- Current version. Earlier history archived outside the repository.

## web-monitor.py

### 2.76.20261020.211944

- Current version. Earlier history archived outside the repository.

## zip-versions.py

### 1.15.20261020.211944

- Current version. Earlier history archived outside the repository.

## odoo-backup.sh

### 1.20.20261022.012000

- Title: Comment corrected for the common file (no behaviour change).
- Reason: Reason: the comment said only VERBOSE and DEBUG_LEVEL are read from app-default.conf. LANGUAGE and ANONYMIZE are in fact read through apps/_i18n.sh, and LOG_KEEP_DAYS does not apply to this program.
- Changes:
  - Comment only (line ~256).
- Bugs fixed:
  None: the behaviour was checked and is correct.
- Guard rails and edge cases:
  - No code change.
- Checks:
  - shellcheck, bash -n.
- Action required: None.

### 1.19.20261020.211944

- Current version. Earlier history archived outside the repository.

## odoo-update-module.sh

### 1.14.20261020.211944

- Current version. Earlier history archived outside the repository.

## nginx-hardening.sh

### 2.53.20261021.130912

- Current version. Earlier history archived outside the repository.

## nginx-log-audit.sh

### 2.42.20261020.211944

- Current version. Earlier history archived outside the repository.

## sync-crowdsec-blocklist.sh

### 1.26.20261020.211944

- Current version. Earlier history archived outside the repository.

## apps/_anonymiser.py

### 1.3.20261020.203430

- Current version. Earlier history archived outside the repository.

## apps/_bbb.py

### 1.3.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_cache_ip.py

### 1.2.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_config.py

### 1.8.20261020.211944

- Current version. Earlier history archived outside the repository.

## apps/_connexions.py

### 1.1.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_courriel.py

### 1.3.20261020.211944

- Current version. Earlier history archived outside the repository.

## apps/_email_check.py

### 1.2.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_i18n.py

### 1.18.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_limites.py

### 1.1.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_listes.py

### 1.3.20261020.211944

- Current version. Earlier history archived outside the repository.

## apps/_odoo_conf.py

### 1.3.20261020.211944

- Current version. Earlier history archived outside the repository.

## apps/_odoo_db.py

### 1.19.20261020.103939

- Current version. Earlier history archived outside the repository.

## apps/_odoo_users.py

### 1.2.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_rapport.py

### 1.12.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_record.py

### 1.0.20261020.230008

- Current version. Earlier history archived outside the repository.

## apps/_reseau.py

### 1.3.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_sysperf.py

### 1.2.20261019.150215

- Current version. Earlier history archived outside the repository.

## run-all.sh

### 1.194.20261021.130912

- Current version. Earlier history archived outside the repository.

## apps/_traduire.py

### 1.5.20261019.150215

- Current version. Earlier history archived outside the repository.
