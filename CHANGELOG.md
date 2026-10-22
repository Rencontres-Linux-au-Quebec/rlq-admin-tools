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

### 1.97.20261022.100559

- Title: --hide-addons (key q): hide the INFO noise of the Odoo modules.
- Reason: The live stream is flooded by INFO lines of the Odoo modules (cron jobs, websocket, fetchmail…) that hide the lines that matter. The request: hide them, except when there is an error or when an e-mail is sent or a file (PDF…) is generated.
- Changes:
  - Option --hide-addons (new), key q on the fly (menu, with the current state), configuration key HIDE_ADDONS (yes/no) in doc/en and doc/fr app-log-live.conf.example.
  - Lines whose logger starts with odoo.addons. and whose level is INFO or DEBUG are discarded, unless ADDONS_KEEP_RE matches (successfully sent, mail_mail, ir_mail_server, mail delivery, smtp, ir_actions_report, pdf, report generated, attachments .pdf/.xlsx/.docx/.csv/.zip).
  - Line.discard_addons() (new); the same rule is applied to the lines of the reminder shown again after a sign-in.
  - Command-line summary line (--hide-addons in the list of active filters of the test recording).
  - Files: app-log-live.py; lang/app-log-live.fr.po (3 new fragments); doc/en and doc/fr 07-app-log-live.md and app-log-live.conf.example; nginx-tools-tests/test_app_log_live.py (new test).
- Bugs fixed:
  None (new option).
- Guard rails and edge cases:
  - Errors are never hidden: WARNING, ERROR, CRITICAL and any trace (Line.err()), even from odoo.addons.*.
  - Lines of nginx / werkzeug requests and lines outside odoo.addons.* are never hidden.
  - Pressing q again shows how many lines were hidden so far.
  - Without the option, nothing changes (the test checks the complete output).
  - --min keeps its own rule; the two options combine.
- Checks:
  - test_app_log_live: new test test_hide_addons_cache_le_bruit_des_modules_sauf_erreurs_courriels_et_pdf (option, key set from configuration file, errors / e-mails / PDF kept); test_min_sans_base... still passes.
  - py_compile; ruff shows no new warning.
- Action required: To hide the noise by default, add HIDE_ADDONS=oui to /etc/default/app-log-live.conf (or ~/.app-log-live.conf). Otherwise: none.

### 1.96.20261022.083937

- Title: N key: steps of a test (start and end, with a description; steps.txt in the archive).
- Reason: The first archive of the test plan (2026-10-21) could only be read by timestamps: nothing marked where each action of the test started and ended. Each action is now marked by hand during the R recording, with a description, and listed in the archive.
- Changes:
  - Key N (only while a recording runs): N asks for a description and starts a step; N again ends the open step. The step shows on screen (cyan START / END line), in stream-all.log ([step]) and in records.log.
  - Archive: steps.txt (new): number, start, end, duration, description. README.txt gives the number of steps.
  - Help menu (? or h): a line for N. Key line at startup: "N step while recording".
  - Files: app-log-live.py; apps/_record.py 1.1; lang/app-log-live.fr.po (French); doc/en and doc/fr 07-app-log-live.md; nginx-tools-tests/test_record.py.
  - Merged with main (1.95 settings keys SUMMARY/UNDERLINE): this change takes 1.96 to avoid a version clash.
- Bugs fixed:
  None (new function).
- Guard rails and edge cases:
  - N outside a recording starts nothing; a message says to press R first.
  - Ctrl-C at the description prompt cancels: no step is started.
  - A step still open when the recording stops is closed then ("recording stopped" in records.log and steps.txt); pressing N for a new step closes the open one first.
  - The description has its spaces collapsed, is cut at 200 characters and is masked like every other line (addresses, e-mails, tokens); empty = "(no description)".
  - Numbering restarts at 1 for each recording.
- Checks:
  - test_record.py: new test (START / END lines in records.log, steps.txt, README count, step closed at the stop).
  - py_compile and ruff on apps/_record.py, app-log-live.py and test_record.py.
- Action required: None.

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

### 1.1.20261022.083937

- Title: Steps of the test (N key of app-log-live.py): steps.txt.
- Reason: The N key of app-log-live.py marks the start and the end of each action of a test; the archive must hold them, with their times, to match the log lines.
- Changes:
  - Recorder.step_start(description) / step_end(reason): step numbers, times, descriptions; the open step is closed before a new one starts.
  - records.log and stream-all.log: "STEP n START hh:mm:ss — description" and "STEP n END hh:mm:ss — duration s — description".
  - steps.txt (new, bilingual header) in the archive, and "Steps" line in README.txt.
  - stop(): a step still open is closed with reason "recording stopped".
- Bugs fixed:
  None.
- Guard rails and edge cases:
  - step_start returns None when no recording runs or when it is stopping (no crash, nothing written).
  - Description masked with the same mask() as the lines; spaces collapsed; 200 characters maximum.
- Checks:
  - test_record.py: test_etapes_debut_fin_dans_records_log_et_steps_txt.
- Action required: None.

### 1.0.20261020.230008

- Current version. Earlier history archived outside the repository.

## apps/_reseau.py

### 1.3.20261019.150215

- Current version. Earlier history archived outside the repository.

## apps/_sysperf.py

### 1.2.20261019.150215

- Current version. Earlier history archived outside the repository.

## run-all.sh

### 1.195.20261022.083937

- Title: test_record: steps of the test (N key of app-log-live.py).
- Reason: New test of the step markers (N key) of the test recording.
- Changes:
  - nginx-tools-tests/test_record.py: archive() accepts etapes; new test_etapes_debut_fin_dans_records_log_et_steps_txt.
  - Merged with main (1.194): this change takes 1.195; nginx-tools 1.142.
- Bugs fixed:
  None.
- Guard rails and edge cases:
  - The step still open at the stop is checked (closed with "recording stopped").
- Checks:
  - run-all.sh on the modules test_record and test_conventions.
- Action required: None.

### 1.194.20261021.130912

- Current version. Earlier history archived outside the repository.

## apps/_traduire.py

### 1.5.20261019.150215

- Current version. Earlier history archived outside the repository.
