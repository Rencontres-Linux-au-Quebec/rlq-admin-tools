# Changelog

Version numbers follow `MAJOR.MINOR.YYYYMMDD.HHMMSS` (local time of the change).
Each program has its own section; the most recent version comes first.
Earlier history was archived outside this repository when this file was created.

## app-health-check.py

### 2.28.20261022.171858

- Title: Configuration file present but unreadable without root is reported, not treated as missing.
- Reason: Without root, `/etc/default/app-health-check.conf` (mode 600, owner root) was found, could not be read, and its settings were silently lost. The e-mail check then reported "not configured".
- Changes:
  - `resolve_config_paths()`: an existing file that is not readable is listed as a warning "exists but is NOT readable by this user (run with sudo)"; it is not used.
  - If the only file found is unreadable, the program stops with exit code 2 and "configuration not readable without root" instead of creating a new configuration.
  - Files: app-health-check.py, nginx-tools-tests/test_app_health_check.py (test_fichier_illisible_sans_root_signale_et_non_pris_pour_absent, skipped as root).
- Bugs fixed:
  - Symptom: "e-mail not configured (SMTP_HOST and NOTIFY_EMAIL_TO empty)" as a normal user, while the file defined both.
  - Diagnosis: the file was present but unreadable; the empty values came from the missing read, not from the file.
  - Fix: see Changes above.
- Safeguards and edge cases:
  - An explicit `-c/--config` path is unchanged.
  - As root, the file is read as before.
- Checks:
  - test_app_health_check as an ordinary user and as root; test_conventions.
- Action required: none. Run `sudo app-health-check.py --target local` to read the configuration on the server.

### 2.27.20261022.110306

- Title: Option values in English only in the configuration summary; template sorted.
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui → yes, non → no); options of the default configuration files in /etc/default in alphabetical order.
- Changes:
  - show_config_read(): yes / no in every language (was oui / non in French).
  - doc/en and doc/fr app-health-check.conf.example: keys sorted alphabetically inside each section (the sections are kept because this template holds real example values); the one-line comment that described LANGUAGE, TARGET, APP and VERBOSE split into one comment per key.
- Bugs fixed:
  None.
- Guard rails and edge cases: - No key added or removed; example values unchanged.
- Checks: - py_compile; test_cles_modeles.
- Action required: None.

### 2.26.20261020.211944

## app-log-check.py

### 2.24.20261022.012000
- Reason: Reason: the report mode --by-hour is a setting that can stay in the file; --last remains a one-shot window and stays on the command line.
- Changes: - SCHEMA_CONFIG: new key BY_HOUR (--by-hour). - doc/en and doc/fr app-log-check.conf.example: BY_HOUR added. - --init and --last remain command-line only (actions / one-shot filter).
- Bugs fixed:
  None in this change.
- Guard rails and edge cases: - Absent or empty BY_HOUR keeps the report default.
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 2.23.20261020.211944

## app-log-live.py

### 1.102.20261022.154430
- Reason: request: add an option U for UNDERLINE in the menu that asks for a number, and make sure it is saved with the C key.
- Changes: - MENU_KEYS: U = underline; the menu lists « U --underline N » (current value, 0 = none) in alphabetical order. - Key handler underline: asks for N (0 to 1000; Enter = 10, the default), applies it at once to the output (output.underline) and to options["underline"]. - config_values(): UNDERLINE is written by the C key (only when changed since startup, like the other settings). - main(): options["underline"] is set from the value in use at startup (command line, or UNDERLINE of the configuration file). - C key help: UNDERLINE added to the list of savable settings. - --underline help: « U key of the menu; UNDERLINE of the configuration file ». - Header comment, lang/app-log-live.fr.po and doc/en and doc/fr 07-app-log-live.md updated.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases: - 0 means no underlined line, as on the command line; a non-number is refused with the usual message and nothing changes. - Only what changed since startup is written by C; an unchanged value is not written. - The value is kept in memory only until C is pressed (or the program ends).
- Checks: - py_compile; --version.
- Action required: None.

### 1.101.20261022.154316
- Reason: request: the F key should not be available only after R; it must show the steps without requiring a recording to be started first.
- Changes: - show_steps_line(): shows the steps of the recording in progress, otherwise the steps of the LAST recording (kept until the next R), otherwise the hint « Steps: no recording yet (R starts one, then N a step) ». The line of the last recording is prefixed « Last recording - ». - record["last"]: the recording stopped last, set by record_stop(). - F key (steps_line): no longer refuses with « Start a recording (R) »; turning it on shows the line at once. - Menu: the F entry says the steps are those of the recording (or of the last one) and that it works without R. - lang/app-log-live.fr.po: new and changed messages translated; obsolete messages removed. - doc/en and doc/fr 07-app-log-live.md: the F key paragraph.
- Bugs fixed: - Symptom: pressing F without a recording only printed « Start a recording (R) to see the steps on one line », so the key looked unavailable. - Diagnosis: the line was drawn only from the recording in progress (record["r"]); no recording meant nothing to draw. - Correction: the steps are read from the recording in progress or from the last one; the refusal message is gone.
- Guard rails and edge cases: - A recording in progress takes precedence over the last one. - No recording at all: a hint, never an empty line; a text wider than the terminal is cut as before. - Screen only: nothing is written to the journal or to the archive. - The steps of the last recording are kept in memory only, until the next R; a new recording replaces them.
- Checks: - py_compile.
- Action required: None.

### 1.100.20261022.133552
- Reason: request: the program must run with a non-root account and use sudo before the advanced functions; the recording must keep the database samples (writes, locks), so PostgreSQL is mandatory; the archive must record whether the program ran as root, the operating system and the tools (psql 18.6 was not recorded); the menu options sorted alphabetically.
- Changes: - privileged() and lancer_root(): fail2ban-client and ipset run as they are when root, through « sudo -n » otherwise (never asks for a password). - R recording refused with an explicit message without psql, without an Odoo database, or without PostgreSQL access through « sudo -n -u postgres ». - Archive: context/system.txt (root or not, sudo, operating system, kernel, Python and tool versions; no user name); db/writes-BASE.log (writes per activity table at each sample). - Journal of the service recorded through sudo -n when not root. - Menu (? key): options sorted alphabetically by option name. - Files: app-log-live.py; doc/en and doc/fr 07-app-log-live.md and app-log-live.conf.example (sudo and PostgreSQL requirements); apps/_record.py 1.2; apps/_odoo_db.py 1.20; apps/_connexions.py 1.2; nginx-tools-tests/fixtures/app-log-live-record-exemple-tests-en-dev.tar.xz (anonymized recording with the context reported by the operator).
- Bugs fixed: - Symptom: psql and runuser were called only as root; with a non-root account there were no database samples and no context in the archive. - Diagnosis: runuser needs root. - Correction: sudo -n -u postgres for an account that is not root; the advanced commands go through sudo -n.
- Guard rails and edge cases: - Without sudo and without root, the commands fail as before, and the messages say so. - The recording never starts blind: without the database samples it is refused.
- Checks: py_compile; --version; test_app_log_live; test_record; test_i18n; test_conventions; test_cles_modeles; test_config_defaut. Non-root run on a temporary account with a limited sudoers rule: --version, --help, and --app odoo --no-follow reach the service check and print the limited-rights message; sudo -n -u postgres psql and sudo -n journalctl work. A full recording could not be run in the test environment (no Odoo service).
- Action required: to use the recording and the advanced functions without root, allow without password for the account: « sudo -n -u postgres psql », « fail2ban-client », « ipset », « journalctl ». The PostgreSQL client (postgresql-client) must be installed.

### 1.99.20261022.122804
- Reason: During a test recording the steps (N key) are marked one by one, but nothing shows at a glance what the user is doing. The request: all the steps on one white reverse-video line, toggled on or off. Also, a recording must stop by itself when someone forgets to press R: the limit is now 60 minutes at most.
- Changes: - F key (menu, with the current state) and option --steps-line / STEPS_LINE (yes / no in the configuration file): all the steps of the recording on ONE line, white reverse video (style 30;107, black text on white background, both explicit). Each step: number, state ([OK] ended, - open) and description cut at 24 columns. Shown when turned on, and at each step start or end. - steps_line_text() (new): if the full line does not fit the terminal width, the descriptions are left out and the last step is shown in full. - show_steps_line() (new): screen only, anonymized like the stream (never in the daily journal, never in the archive). - --record-max / RECORD_MAX: default 60 minutes (was 30); the value must be greater than 0 and at most 60 (RECORD_MAX_LIMIT). The help text and the menu are updated. - Files: app-log-live.py; lang/app-log-live.fr.po (6 new messages, help fragment updated); doc/en and doc/fr 07-app-log-live.md; doc/en and doc/fr app-log-live.conf.example (STEPS_LINE, RECORD_MAX=60); doc/nginx-tools.version.
- Bugs fixed: - None (new option; change of a limit).
- Guard rails and edge cases: - Without a recording, F only changes the state and says that a recording is needed; the line is then empty of steps and nothing is written. - The line is cut to the terminal width (no wrap, no broken layout); it is rewritten on each step, so an older copy stays in the scrollback (the stream scrolls). - 0 is refused for --record-max / RECORD_MAX: a recording always has a limit. A value above 60 is refused too, so the limit cannot be bypassed from the command line or the configuration file. - --record-test-log (automatic recording without the keyboard) keeps its own limit (at most 1440 minutes).
- Checks: - py_compile; --version, --help (French and English texts), --record-max 0 and 61 refused. - test_app_log_live: new test test_199_steps_line_touche_F_et_limite_d_enregistrement_60_minutes; test_i18n (catalogue of the French messages), test_conventions, test_cles_modeles, test_config_commune, test_config_defaut, test_record, test_reglages_bannis_limites: OK.
- Action required: If /etc/default/app-log-live.conf or ~/.app-log-live.conf contains RECORD_MAX=0 or a value above 60, change it to 60 or less: otherwise the program stops at startup with a message. To see the steps on one line, add STEPS_LINE=yes or press F during a recording.

### 1.98.20261022.110306
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - MIN_DEFAULT = True (new constant): --min is on by default; new option --no-min (shows everything: database, « werkzeug », fetchmail lines); MIN=no in the configuration file does the same. - UNDERLINE_DEFAULT = 10 (was 5): one log line out of 10 underlined by default and for UNDERLINE=yes / --underline without N; --help text updated. - HIGHLIGHT: the default list already held -2026- (HIGHLIGHT_DEFAULT); the template now shows it (#HIGHLIGHT=...,ouvertes,-2026-) and explains that a word ending with a dash is a word, not a removal. - Menu (? key): option states shown as yes / no in every language (was oui / non in French) - the same words as in the configuration file. - doc/en and doc/fr app-log-live.conf.example: keys in alphabetical order in one « Options » section (LANGUAGE and ANONYMIZE included), yes / no values, #MIN=yes, #UNDERLINE=10. - doc/en and doc/fr 07-app-log-live.md: underline every 10 lines, --min by default, English values. - lang/app-log-live.fr.po: --min, --no-min and --underline help texts. - nginx-tools-tests/test_app_log_live.py: the tests written for the full display pass --no-min (run_cmd / run_pty wrappers); the default-underline test uses 11 lines (10th underlined); menu test expects yes; new test test_valeurs_par_defaut_198_min_underline_highlight_et_valeurs_en_anglais.
- Bugs fixed:
  None (change of defaults).
- Guard rails and edge cases: - --no-min, MIN=no (or the old MIN=non, still read) bring back the full display; --min stays accepted. - Old French values (oui, non, aucun) in UNDERLINE / TRUNCATE / booleans are still read with the same meaning; the configuration banner asks to write the English value. - « -2026- » is not taken as « remove 2026 » by the +word / -word syntax (modify_highlight already excluded words ending with a dash). - /etc/default/app-log-live.conf with no active line is refreshed to the new sorted template at the next run (apps/_config.py rafraichir); a file with active lines is never rewritten.
- Checks: - test_app_log_live, test_cles_modeles (new sorting / English-values test), test_config_commune, test_config_defaut, test_i18n: OK. - py_compile.
- Action required: In /etc/default/app-log-live.conf (or ~/.app-log-live.conf), replace any oui / non by yes / no (the program prints the lines to change). Remove an active MIN=no or UNDERLINE=5 line if you want the new defaults.

### 1.97.20261022.100559
- Reason: The live stream is flooded by INFO lines of the Odoo modules (cron jobs, websocket, fetchmail...) that hide the lines that matter. The request: hide them, except when there is an error or when an e-mail is sent or a file (PDF...) is generated.
- Changes: - Option --hide-addons (new), key q on the fly (menu, with the current state), configuration key HIDE_ADDONS (yes/no) in doc/en and doc/fr app-log-live.conf.example. - Lines whose logger starts with odoo.addons. and whose level is INFO or DEBUG are discarded, unless ADDONS_KEEP_RE matches (successfully sent, mail_mail, ir_mail_server, mail delivery, smtp, ir_actions_report, pdf, report generated, attachments .pdf/.xlsx/.docx/.csv/.zip). - Line.discard_addons() (new); the same rule is applied to the lines of the reminder shown again after a sign-in. - Command-line summary line (--hide-addons in the list of active filters of the test recording). - Files: app-log-live.py; lang/app-log-live.fr.po (3 new fragments); doc/en and doc/fr 07-app-log-live.md and app-log-live.conf.example; nginx-tools-tests/test_app_log_live.py (new test).
- Bugs fixed:
  None (new option).
- Guard rails and edge cases: - Errors are never hidden: WARNING, ERROR, CRITICAL and any trace (Line.err()), even from odoo.addons.*. - Lines of nginx / werkzeug requests and lines outside odoo.addons.* are never hidden. - Pressing q again shows how many lines were hidden so far. - Without the option, nothing changes (the test checks the complete output). - --min keeps its own rule; the two options combine.
- Checks: - test_app_log_live: new test test_hide_addons_cache_le_bruit_des_modules_sauf_erreurs_courriels_et_pdf (option, key set from configuration file, errors / e-mails / PDF kept); test_min_sans_base... still passes. - py_compile; ruff shows no new warning.
- Action required: To hide the noise by default, add HIDE_ADDONS=oui to /etc/default/app-log-live.conf (or ~/.app-log-live.conf). Otherwise: none.

### 1.96.20261022.083937
- Reason: The first archive of the test plan (2026-10-21) could only be read by timestamps: nothing marked where each action of the test started and ended. Each action is now marked by hand during the R recording, with a description, and listed in the archive.
- Changes: - Key N (only while a recording runs): N asks for a description and starts a step; N again ends the open step. The step shows on screen (cyan START / END line), in stream-all.log ([step]) and in records.log. - Archive: steps.txt (new): number, start, end, duration, description. README.txt gives the number of steps. - Help menu (? or h): a line for N. Key line at startup: "N step while recording". - Files: app-log-live.py; apps/_record.py 1.1; lang/app-log-live.fr.po (French); doc/en and doc/fr 07-app-log-live.md; nginx-tools-tests/test_record.py. - Merged with main (1.95 settings keys SUMMARY/UNDERLINE): this change takes 1.96 to avoid a version clash.
- Bugs fixed:
  None (new function).
- Guard rails and edge cases: - N outside a recording starts nothing; a message says to press R first. - Ctrl-C at the description prompt cancels: no step is started. - A step still open when the recording stops is closed then ("recording stopped" in records.log and steps.txt); pressing N for a new step closes the open one first. - The description has its spaces collapsed, is cut at 200 characters and is masked like every other line (addresses, e-mails, tokens); empty = "(no description)". - Numbering restarts at 1 for each recording.
- Checks: - test_record.py: new test (START / END lines in records.log, steps.txt, README count, step closed at the stop). - py_compile and ruff on apps/_record.py, app-log-live.py and test_record.py.
- Action required: None.

### 1.95.20261022.012000
- Reason: Reason: the owner wants every changeable setting available in the configuration file, and default files that list every variable (commented). UNDERLINE was missing from default files created before the key existed.
- Changes: - SCHEMA_CONFIG: new key SUMMARY (--summary: session summary at the end of a --no-follow run). - doc/en and doc/fr app-log-live.conf.example: SUMMARY added. UNDERLINE was already in the code and in both examples (verified). - Action-only options stay on the command line: --diagnose, --diagnose-host, --modules, --modules-latest, --no-follow, --rate-limit, --record-test-log, --keep-ip (hidden legacy option).
- Bugs fixed: - Symptom: UNDERLINE absent from /etc/default/app-log-live.conf. Diagnosis: the file was created before the key existed, and an existing file is never completed automatically. Fix: add the line by hand (see Action required).
- Guard rails and edge cases: - A key that is absent or empty keeps the default (UNDERLINE=5, SUMMARY off). - Command-line options still take precedence over the file.
- Checks: - py_compile and ruff on the program; test_cles_modeles (every schema key is present in both examples).
- Action required: Add `UNDERLINE=5` and `SUMMARY=non` to /etc/default/app-log-live.conf if you want them written in the file (new installs get them automatically).

### 1.94.20261021.095843

## host-perf-audit.py

### 1.4.20261020.211944

## odoo-chat-post.py

### 1.9.20261022.012000
- Reason: Reason: every setting in the command line gets a key; actions remain on the command line.
- Changes: - SCHEMA_CONFIG: new keys BOT_LOGIN (--bot-login) and CATALOG (--catalog). - doc/en and doc/fr odoo-chat-post.conf.example: both added. - Command-line only (actions or per-run inputs): --bot-config, --create, --create-bot, --dry-run, --list, --message, --post, --renew-key.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases: - An empty CATALOG= line is ignored (the shipped catalogue is used).
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.8.20261020.211944

## odoo-docs.py

### 1.4.20261020.211944

## odoo-mail-retry.py

### 1.15.20261022.012000
- Reason: Reason: same as odoo-warmup.py: the common-file filter discarded LOG_KEEP_DAYS and ANONYMIZE.
- Changes: - read_config(): the common file accepts LOG_KEEP_DAYS and ANONYMIZE; both are exported to the environment (environment wins).
- Bugs fixed: - Symptom: ANONYMIZE in app-default.conf ignored. Diagnosis and fix as in odoo-warmup.py.
- Guard rails and edge cases: - Invalid ANONYMIZE value reported and ignored.
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.14.20261020.211944

## odoo-warmup.py

### 1.10.20261022.012000
- Reason: Reason: app-default.conf defines five common keys (apps/_config.py CLES_COMMUNES), but this program read only LANGUAGE, VERBOSE and DEBUG_LEVEL from it.
- Changes: - read_config(): the common file accepts LOG_KEEP_DAYS and ANONYMIZE. - LOG_KEEP_DAYS and ANONYMIZE are exported as NGINX_TOOLS_LOG_KEEP_DAYS and NGINX_TOOLS_ANONYMIZE (only if not already set in the environment). - Comment updated to list the five keys.
- Bugs fixed: - Symptom: ANONYMIZE=yes in app-default.conf had no effect on odoo-warmup. Diagnosis: the common-file filter discarded every key except three. Fix: accept the two keys.
- Guard rails and edge cases: - An environment variable already set wins over the file. - An invalid ANONYMIZE value is reported and ignored.
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.9.20261020.211944

## web-monitor.py

### 2.77.20261022.110306
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - Configuration summary line: boolean options shown as yes / no in every language (was oui / non in French). - doc/en and doc/fr web-monitor.conf.example: keys in alphabetical order, yes / no values.
- Bugs fixed:
  None.
- Guard rails and edge cases: - Old oui / non values are still read (apps/_config.py) with a warning.
- Checks: - py_compile; test_cles_modeles.
- Action required: None.

### 2.76.20261020.211944

## zip-versions.py

### 1.15.20261020.211944

## odoo-backup.sh

### 1.20.20261022.012000
- Reason: Reason: the comment said only VERBOSE and DEBUG_LEVEL are read from app-default.conf. LANGUAGE and ANONYMIZE are in fact read through apps/_i18n.sh, and LOG_KEEP_DAYS does not apply to this program.
- Changes: - Comment only (line ~256).
- Bugs fixed:
  None: the behaviour was checked and is correct.
- Guard rails and edge cases: - No code change.
- Checks: - shellcheck, bash -n.
- Action required: None.

### 1.19.20261020.211944

## odoo-update-module.sh

### 1.15.20261022.133552
- Reason: request: update the modules only when the site is idle. A single visitor can write (survey answer, chat message, registration, contact form), and the former guard, which counted visitors only, let such an update through.
- Changes: - Guard (site_reasons, wait_for_quiet_site): the site is busy while one of these holds: active visitors (BUSY_VISITORS threshold); write requests in the nginx logs during the last ACTIVITY_WINDOW seconds (POST, PUT, PATCH, DELETE, except the known read-only requests of Odoo); open PostgreSQL sessions on the database; write locks on ir_cron; writes in the activity tables (counters of pg_stat_user_tables, sampled twice ACTIVITY_SAMPLE seconds apart). - WAIT_QUIET default: 60 minutes (was 15). 0 = a single check. - At the end of the wait the update is CANCELLED (exit 3, nothing stopped) instead of going ahead. --force-busy (FORCE_BUSY=yes) runs it anyway. - New option --check-activity: state of the site now, changes nothing; exit 0 = quiet, 3 = busy. - PostgreSQL commands run through runuser when the program runs as root, through « sudo -n -u postgres » otherwise (no root needed). - The regular expressions of the nginx logs accept several spaces between columns. - Test hooks: ODOO_UPDATE_MODULE_NOW (clock), ODOO_UPDATE_MODULE_PG_AS (command used in place of sudo), ODOO_UPDATE_MODULE_SAMPLE, ODOO_UPDATE_MODULE_WINDOW. - Calm-site messages state the threshold instead of claiming "no active visitor" when one visitor is below it. - Files: odoo-update-module.sh; lang/odoo-update-module.en.po; doc/en and doc/fr odoo-update-module.conf.example and 09-odoo-update-module.md; nginx-tools-tests/test_odoo_update_module.py; nginx-tools-tests/fixtures/ (anonymized recording used by the tests).
- Bugs fixed: - Symptom: after WAIT_QUIET minutes with visitors still active, the update went ahead ("mise à jour quand même"), even during writes. - Diagnosis: the wait looked at visitors only, and the end of the wait forced the update. - Correction: the guard looks at all the activity above; the update is cancelled unless --force-busy.
- Guard rails and edge cases: - Unreadable nginx logs, or unreadable PostgreSQL (psql missing, sudo refused): counted as BUSY, never a blind update. - Read-only POST requests of Odoo (lists, views, reads, bus) are not writes; any other POST counts as a write.
- Checks: test_odoo_update_module (guard tests replayed on the anonymized recording: busy, calm, cancelled without --force-busy, forced with it, unreadable database counted as busy); test_i18n; test_conventions; test_cles_modeles; test_config_defaut; test_config_commune.
- Action required: if your configuration keeps WAIT_QUIET=15, it still waits 15 minutes; the new default is 60. The account that runs the update, when it is not root, needs « sudo -n -u postgres psql » without password (sudoers), otherwise the update is cancelled with a message.

### 1.14.20261020.211944

## nginx-hardening.sh

### 2.54.20261022.171858

- Title: Run the initial-setup check without root: unverifiable points are warnings, not failures.
- Reason: Running `nginx-hardening.sh --check` (the default mode) as an ordinary user reported false failures: `iptables -C`, `ufw status`, `fail2ban-client status` and `nginx -t` need root, so their refusal was read as "rule absent" or "configuration refused". The test suite and the read-only real-server checks (run-all.sh, section 6) therefore could not run without root.
- Changes:
  - `sans_root_verif()`: when not root in check mode, a check that needs root is reported as `[ATTN]` "not checked without root (run again with sudo ...)", never `[FAIL]`.
  - Step 0a: `nginx -t` refused with "Permission denied" / "Operation not permitted" / "must be root" without root is a warning.
  - Step 5: the iptables and ufw rule checks are warnings without root.
  - Step 9: the fail2ban jail status checks are warnings without root.
  - Files: nginx-hardening.sh, lang/nginx-hardening.en.po (4 new fragments), nginx-tools-tests/test_nginx_hardening.py (test_hors_root_nginx_t_et_iptables_non_verifies_sans_echec).
- Bugs fixed:
  - Symptom: `nginx-hardening.sh --check` run as a normal user reported "nginx -t REFUSE", "iptables : aucune règle DROP" for ports 10000 and 10002, and "Jail ... NON chargé" for three jails, although `--update` as root showed everything correct.
  - Diagnosis: the default check mode does not require root, but these commands do. Their permission error was read as a missing rule or a refused configuration.
  - Fix: see Changes above.
- Safeguards and edge cases:
  - As root, the checks are unchanged.
  - Only `--check` is affected: `--update` still requires root.
  - A real refusal of nginx (certificate, directive, port) still fails as root or without root, unless the message is a permission error.
- Checks:
  - test_nginx_hardening, test_app_health_check, test_web_monitor run as an ordinary user (147 tests, 18 skipped because they require root) and as root.
  - test_i18n and test_conventions.
- Action required: none for the program. To validate the real server state, run `sudo nginx-hardening.sh --check` (or `--update`, which then shows everything as before).

### 2.53.20261021.130912

- Current version. Earlier history archived outside the repository.

## nginx-log-audit.sh

### 2.43.20261022.162206

- **Titre** : option `--unban-low-score` — lister les IP bannies dont le score est sous le seuil et proposer de les débannir.
- **Motif** : `--unban-check` ne voit que les bannissements manuels (pare-feu) ; une IP bannie automatiquement par fail2ban (jail `nginx-blocked-probes`) n'apparaissait nulle part, et il n'existait aucun moyen de repérer en une fois les bannissements dont le score est sous le seuil.
- **Détail des modifications** :
  - nouvelle option `--unban-low-score` (root requis) : collecte les IP bannies de tous les jails fail2ban (`fail2ban-client status`) et des bannissements manuels (`list_manual_bans`) ;
  - calcule le score de chaque IP en relançant `--investigate IP --no-prompt` (même calcul, lecture seule) ;
  - affiche un tableau IP / score / origine, puis la liste des IP dont le score est strictement inférieur à `BAN_THRESHOLD` (3 par défaut) ;
  - pour chacune, demande « Débannir … ? [o/N] » ; `--yes` lève sans question ; sans terminal interactif, rien n'est levé (liste seule) ;
  - levée : `fail2ban-client set <jail> unbanip IP` pour les bannissements fail2ban, `--unban IP --yes` (journalisé dans `bans.tsv`) pour les bannissements manuels ;
  - aide (`--help`) : option ajoutée à sa place alphabétique, après `--unban-check` ; en-tête du programme mis à jour.
- **Bugs corrigés** : aucun.
- **Garde-fous et cas limites** :
  - une IP dont le score n'est pas lisible (sortie de `--investigate` sans ligne « Score ») est affichée avec « ? » et n'est jamais proposée ;
  - une IP protégée (liste blanche, adresses du serveur, réseaux privés) est signalée et n'est jamais levée ici ;
  - la levée fail2ban n'est pas journalisée dans `bans.tsv` (le journal ne couvre que les bannissements manuels) ;
  - l'option ne pose jamais de bannissement.
- **Vérifications** : `bash -n` ; `--version` et `--help` (option présente, ordre alphabétique) ; `python3 -m unittest test_nginx_log_audit` : 41 tests OK. La levée réelle dans un jail fail2ban n'a pas été testée (aucun fail2ban dans l'environnement de développement).
- **Action requise** : aucune, sauf pour lancer `sudo ./nginx-log-audit.sh --unban-low-score` sur le serveur et valider chaque levée.

### 2.42.20261020.211944

- Current version. Earlier history archived outside the repository.

## sync-crowdsec-blocklist.sh

### 1.26.20261020.211944

## apps/_anonymiser.py

### 1.3.20261020.203430

## apps/_bbb.py

### 1.3.20261019.150215

## apps/_cache_ip.py

### 1.2.20261019.150215

## apps/_config.py

### 1.9.20261022.110306
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - FRANCAIS (new map oui/non/vrai/faux/aucun -> yes/no/true/false/none) and valeurs_francaises(cfg) (new): list of « KEY=oui -> yes » for the configuration banner. - lire(): DEBUG_LEVEL >= 1 now sets VERBOSE=yes (was oui). - All templates doc/en and doc/fr *.conf.example (read by creer_par_defaut / rafraichir): options in alphabetical order (one « Options » section; inside each section for app-health-check and nginx-tools-mail, which hold real values), boolean values yes / no, « booléens : yes / no » in the header. No key added or removed (check: no line lost apart from the old section titles).
- Bugs fixed:
  None.
- Guard rails and edge cases: - Old French values keep their meaning (OUI / NON lists unchanged): nothing breaks on a server whose file still says oui. - Files in /etc/default without an active line follow the new sorted template at the next run; files with active lines are never rewritten.
- Checks: - test_config_commune, test_config_defaut, test_cles_modeles (new test test_modeles_en_ordre_alphabetique_et_valeurs_en_anglais).
- Action required: None.

### 1.8.20261020.211944

## apps/_connexions.py

### 1.2.20261022.133552
- Changes: POSTGRES_RUN (see apps/_odoo_db.py 1.20).
- Action required: none.

### 1.1.20261019.150215

## apps/_courriel.py

### 1.3.20261020.211944

## apps/_email_check.py

### 1.2.20261019.150215

## apps/_i18n.py

### 1.19.20261022.110306
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - oui_non(): always yes / no (summary « Options : ... »). - afficher_configuration(): after the ignored values, one warning per French value (« valeur en français, écrire l'anglais dans le fichier de configuration : MIN=oui -> yes »); lang/_i18n.en.po translated. - apps/_i18n.sh: config_defaut collects French values in CFG_FRANCAIS (new array) and config_afficher prints the same warning; booleans shown as yes / no; « yes ou no attendu » for an invalid value; DEBUG_LEVEL gives VERBOSE=yes; lang/_config.en.po updated.
- Bugs fixed:
  None.
- Guard rails and edge cases: - The French value is still applied (same meaning): only a warning, never an ignored setting. - CFG_FRANCAIS is reset with the other arrays at each config_lire.
- Checks: - test_i18n (catalogues, Bash configuration), test_config_commune.
- Action required: None.

### 1.18.20261019.150215

## apps/_limites.py

### 1.1.20261019.150215

## apps/_listes.py

### 1.3.20261020.211944

## apps/_odoo_conf.py

### 1.3.20261020.211944

## apps/_odoo_db.py

### 1.20.20261022.133552
- Changes: POSTGRES_RUN (runuser when root, « sudo -n -u postgres » otherwise) replaces the runuser prefix of the six queries.
- Action required: none beyond the sudoers rules of app-log-live.py 1.100.

### 1.19.20261020.103939

## apps/_odoo_users.py

### 1.2.20261019.150215

## apps/_rapport.py

### 1.12.20261019.150215

## apps/_record.py

### 1.2.20261022.133552
- Changes: start() refuses the recording without psql, without a database, or without PostgreSQL access; context/system.txt (uid, sudo, operating system, kernel, Python, tool versions, no user name); db/writes-BASE.log (write counters per activity table at each sample); privileged() for the journal of the service.
- Files: apps/_record.py; nginx-tools-tests/test_record.py.
- Action required: none beyond the sudoers rules of app-log-live.py 1.100.

### 1.1.20261022.083937
- Reason: The N key of app-log-live.py marks the start and the end of each action of a test; the archive must hold them, with their times, to match the log lines.
- Changes: - Recorder.step_start(description) / step_end(reason): step numbers, times, descriptions; the open step is closed before a new one starts. - records.log and stream-all.log: "STEP n START hh:mm:ss - description" and "STEP n END hh:mm:ss - duration s - description". - steps.txt (new, bilingual header) in the archive, and "Steps" line in README.txt. - stop(): a step still open is closed with reason "recording stopped".
- Bugs fixed:
  None.
- Guard rails and edge cases: - step_start returns None when no recording runs or when it is stopping (no crash, nothing written). - Description masked with the same mask() as the lines; spaces collapsed; 200 characters maximum.
- Checks: - test_record.py: test_etapes_debut_fin_dans_records_log_et_steps_txt.
- Action required: None.

### 1.0.20261020.230008

## apps/_reseau.py

### 1.3.20261019.150215

## apps/_sysperf.py

### 1.2.20261019.150215

## run-all.sh

### 1.195.20261022.083937
- Reason: New test of the step markers (N key) of the test recording.
- Changes: - nginx-tools-tests/test_record.py: archive() accepts etapes; new test_etapes_debut_fin_dans_records_log_et_steps_txt. - Merged with main (1.194): this change takes 1.195; nginx-tools 1.142.
- Bugs fixed:
  None.
- Guard rails and edge cases: - The step still open at the stop is checked (closed with "recording stopped").
- Checks: - run-all.sh on the modules test_record and test_conventions.
- Action required: None.

### 1.194.20261021.130912

## apps/_traduire.py

### 1.5.20261019.150215
