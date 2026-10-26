# Changelog

Version numbers follow `MAJOR.MINOR.YYYYMMDD.HHMMSS` (local time of the change).
Each program has its own section; the most recent version comes first.
Earlier history was archived outside this repository when this file was created.

## app-health-check.py

### 2.29.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 48 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: app-health-check.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


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
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes:
  - show_config_read(): yes / no in every language (was oui / non in French).
  - doc/en and doc/fr app-health-check.conf.example: keys sorted alphabetically inside each section (the sections are kept because this template holds real example values); the one-line comment that described LANGUAGE, TARGET, APP and VERBOSE split into one comment per key.
- Bugs fixed:
  None.
- Guard rails and edge cases: - No key added or removed; example values unchanged.
- Checks: - py_compile; test_cles_modeles.
- Action required: None.

### 2.26.20261020.211944 - Current version. Earlier history archived outside the repository.

## app-log-check.py

### 2.25.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 22 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: app-log-check.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 2.24.20261022.012000 - Title: Settings key: BY_HOUR.
- Reason: Reason: the report mode --by-hour is a setting that can stay in the file; --last remains a one-shot window and stays on the command line.
- Changes: - SCHEMA_CONFIG: new key BY_HOUR (--by-hour). - doc/en and doc/fr app-log-check.conf.example: BY_HOUR added. - --init and --last remain command-line only (actions / one-shot filter).
- Bugs fixed:
  None in this change.
- Guard rails and edge cases: - Absent or empty BY_HOUR keeps the report default.
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 2.23.20261020.211944 - Current version. Earlier history archived outside the repository.

## app-log-live.py

### 1.110.20261025.172827 - "Who is connected now" shown from level 5

- Title: The list of connected users is shown from dashboard level 5 (Ctrl-G and Ctrl-T), not at every level.
- Reason: Request from the maintainer: the connected users must appear when the level is 5 or more, not only at level 9.
- Changes:
  - app-log-live.py, summary(): the `people` lines are added when level >= 5 (both return paths). Before this version (1.109), they were added at every level.
  - app-log-live.py, table_rows(): comment updated.
  - Version: __version__ 1.110.20261025.172827.
  - Files: app-log-live.py, CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - Levels 1 to 4: connected users are hidden (as before 1.109). Levels 5 to 8: shown without the "Program efficiency" block. Level 9: everything, as before.
  - Detection unchanged (ssh_sessions(), Odoo presence).
- Checks:
  - python3 -I -m py_compile app-log-live.py: OK.
  - app-log-live.py --version: 1.110.20261025.172827.
  - logged_in_lines() with a fake "who" in PATH: "Connected over SSH: 1 (martial ×1)".
  - Not run: the full test suite test_app_log_live.py (to be run with the testeur agent before the pull request is merged).
- Action required: none.

### 1.109.20261025.162831 - "Who is connected now" shown with Ctrl-T at every level

- Title: The list of connected users is shown by Ctrl-T (and Ctrl-G) whatever the dashboard level.
- Reason: Report from the maintainer: Ctrl-T did not show the connected users, although the command "who" lists them on the server.
- Changes:
  - app-log-live.py, table_rows(): the block "Who is connected now" (Odoo presence and SSH sessions, from logged_in_lines()) is built apart and passed to summary() as the new argument `people`.
  - app-log-live.py, summary(): new argument `people=()`; its lines are added at every level, before the "Program efficiency" block. Before, the whole "extras" block (connected users, program efficiency, Odoo network connections) was shown only at level 9.
  - "Program efficiency" and "Odoo network connections" keep their level 9 display.
  - Version: __version__ 1.109.20261025.162831.
  - Files: app-log-live.py, CHANGELOG.md.
- Bugs fixed:
  - Symptom: Ctrl-T shows the requests of the period but no "Who is connected now" section, while "who" lists an open SSH session.
  - Diagnosis: the connected-users block was part of the extras, and the extras are added to the summary only when the dashboard level is 9. Any lower level (keys 1 to 8, or LEVEL=1 to 8 in /etc/default/app-log-live.conf or ~/.app-log-live.conf) hides it.
  - Fix: the block is no longer gated by the level.
- Safeguards and edge cases:
  - No change to the detection: ssh_sessions() still reads "who" and keeps only the lines with an origin address; the Odoo presence is unchanged.
  - The new argument has a default (empty tuple): every other caller of summary() behaves as before.
  - When there is no request in the lines shown, the connected users are still displayed.
- Checks:
  - python3 -I -m py_compile app-log-live.py: OK.
  - app-log-live.py --version: 1.109.20261025.162831.
  - With a fake "who" in PATH (one SSH session from a remote address), logged_in_lines() returns the expected "Connected over SSH: 1 (martial ×1)" line.
  - Not run: the full test suite nginx-tools-tests/test_app_log_live.py (too long in this session; network and DNS dependent). To be run before the pull request is merged.
- Action required: none. To check on the server: press Ctrl-T; the "Who is connected now" section must list the same SSH sessions as "who".

### 1.108.20261025.150359 - Country next to each name in "Requests by name (DNS column)"

- Title: The country of the address is shown next to each name in the summary.
- Reason: The maintainer asked to add the country of the IP address to the "Requêtes par nom (colonne DNS)" rows.
- Changes:
  - app-log-live.py, summary(): the country most frequent among the addresses of a name is shown in brackets after the name, for example
    "name [CA] x12"; nothing is shown when the country is unknown.
  - Files: app-log-live.py, CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases: a name shared by several countries shows the most frequent one; addresses without a known country are left out.
- Checks: py_compile; test suite test_app_log_live.py: the same 23 failures and 1 error as before the change (environment-dependent tests: DNS,
  geoiplookup, terminal); no new failure.
- Action required: none.

### 1.107.20261025.115115 - IP address hidden by default; underlined lines at 80 percent of the terminal width

- Title: IP address hidden by default (HIDE_IP=yes); underlined lines stop at 80 percent of the terminal width (COLUMNS).
- Reason: The IP address in brackets is hidden by default now (it was shown unless --hide-ip was given). The underlined lines (--underline) ran to the end of the terminal line; the request is to stop them at 80 percent of the width.
- Changes:
  - HIDE_IP: the default is now yes (set_defaults(hide_ip=True) before the configuration file is applied, so HIDE_IP=no in the file still shows the address).
  - New option --show-ip (same destination as --hide-ip; shows the address). --hide-ip keeps working.
  - Underlined lines: UNDERLINE_RATIO = 0.8 of the terminal width (terminal_columns(), that is COLUMNS). With the REC marker, the underline still stops before "REC".
  - Help text of --underline: "up to 80 percent of the screen width" (no percent sign: argparse reads it as a format).
  - doc/en and doc/fr app-log-live.conf.example: HIDE_IP=yes in the commented example.
  - lang/app-log-live.fr.po: new and updated messages (--hide-ip, --show-ip, --underline), so the French help text does not fall back to word substitution.
  - Version: __version__ 1.107.20261025.115115.
  - Files: app-log-live.py, lang/app-log-live.fr.po, doc/en/app-log-live.conf.example, doc/fr/app-log-live.conf.example, CHANGELOG.md.
- Bugs fixed:
  - Symptom: the help text of --underline ended with "%" in the French catalogue and --help crashed (TypeError: %d format).
  - Diagnosis: argparse formats help strings with the % operator; any percent sign in a help text must be written as %%, or avoided.
  - Fix: the percent sign is replaced by the words "percent" (English) and "pour cent" (French).
- Safeguards and edge cases:
  - Config file priority kept: set_defaults runs before I18N.defauts(), so HIDE_IP in /etc/default or ~/.app-log-live.conf still wins over the new default; command-line options still win over the file.
  - Underline with --no-underline or --underline 0: unchanged (no underline).
  - Width unknown: terminal_columns() falls back to 100 columns (80 underlined).
- Checks:
  - python3 -I -m py_compile app-log-live.py: OK.
  - app-log-live.py --version: 1.107.20261025.115115.
  - app-log-live.py --help: runs (English and French help), --show-ip shown in the options list.
  - Underline width check: 100 columns gives an underline of 80 columns.
  - Not run: nginx-tools-tests/run-all.sh (to be run before the pull request is merged).
- Action required: none. Note: the HIDE_IP default changes what is shown; use --show-ip or HIDE_IP=no to see the addresses again.

### 1.106.20261025.113933 - Summary: site default language read from Odoo (root only)

- Title: Summary: the « without prefix » pages show the site's default language, read from Odoo (root only).
- Reason: The summary showed "sans préfixe" for the pages without a language prefix, and this was read as "not French". The default language of the site is the only one without a prefix, so the program should read it from Odoo instead of guessing. The program runs as root in the current setup; without root, the database cannot be read.
- Changes:
  - site_default_language(): reads the default language once per session, only when running as root (via apps/_odoo_db.py langue_defaut()). Not queried again at each refresh.
  - language_label(): in the summary "Pages by language", the "without prefix" bucket shows the default language, for example "sans préfixe (fr_CA = langue par défaut du site)". Without root or without database access, the label says why the language is unknown.
  - Translations (lang/app-log-live.fr.po): "sans préfixe" reverts to its plain text; new messages for the default language and the two unknown cases.
  - Version: __version__ 1.106.20261025.113933.
  - Files: app-log-live.py, apps/_odoo_db.py, lang/app-log-live.fr.po, CHANGELOG.md.
- Bugs fixed:
  - Symptom: "sans préfixe 46 %" could be read as "not French" for a French site.
  - Diagnosis: the label did not say which language is the default; the program never read it from Odoo.
  - Fix: the default language is read from Odoo and shown in the label.
- Safeguards and edge cases:
  - Read only as root (os.geteuid() == 0). Non-root: no database query, the label says the language is not read.
  - Read-only: the query goes through _requete(), which forces a read-only PostgreSQL transaction.
  - Database unreachable as root: the label says "base inaccessible", not "root requis".
  - If the site has several websites, the first one (lowest id) is used; if there is no website, the first active language is used.
  - The language is read from the database; the count of pages is still based on the URL prefix.
- Checks:
  - python3 -I -m py_compile on app-log-live.py and apps/_odoo_db.py: OK.
  - app-log-live.py --version: 1.106.20261025.113933. _odoo_db.py --version: 1.22.20261025.113933.
  - Without a database (sandbox): site_default_language() returns None, labels correct in the three cases (unknown, unreachable, known).
  - Not tested against a real Odoo database. Test suite nginx-tools-tests/run-all.sh: not run.
- Action required: none. Verify the displayed language on the server (as root): it should match Website > Configuration > Languages in Odoo.

### 1.105.20261025.113234 - Summary: reason of each address to ban, clear label for pages without prefix

- Title: Summary: reason of each address to ban, clear label for pages without prefix.
- Reason: The summary showed "Suspicious requests: none" and, just below, "Addresses to ban: 2" with no reason. The two addresses were not suspicious requests: they were probe sweeps (5 or more DIFFERENT pages not found, 404), which the "Suspicious requests" line does not count. The label "sans préfixe" for "Pages by language" was read as "not French", although it is the default language of the site (French here, without prefix in the URL).
- Changes:
  - Summary, "Addresses to ban" line: each address now shows its reason (same wording as the b key), for example "7 different pages not found (404): probe sweep" or "3 suspicious request(s)". Stats.ban_reason() was already used by the b key; it is now also used by the summary.
  - lang/app-log-live.fr.po: msgstr of "without prefix" becomes "sans préfixe (langue par défaut du site)". The English text and the code key ("without prefix") are unchanged.
  - Version: __version__ 1.105.20261025.113234.
  - Files: app-log-live.py, lang/app-log-live.fr.po, CHANGELOG.md.
- Bugs fixed:
  - Symptom: "Suspicious requests: none" followed by "Addresses to ban: 2" looks contradictory.
  - Diagnosis: to_ban() also lists addresses with 5 or more different 404 pages (probe sweep). The summary line counted only the suspicious URLs.
  - Fix: the reason is displayed next to each address. No change to the detection rules.
  - Symptom: "FR 0 %" in the summary of the language pages.
  - Diagnosis: the French pages have no URL prefix (language_of returns "without prefix"), so French is counted under "sans préfixe", not under "FR".
  - Fix: the label now says that this is the default language of the site. The count itself is not changed.
- Safeguards and edge cases:
  - The language is still inferred from the URL prefix. The label does not claim the page is French: it says "default language of the site", which is true only if the site's default language is French (to confirm in Odoo: Website > Configuration > Languages).
  - Addresses already banned, of the whitelist, of a place, of a known person or of this server stay excluded (to_ban() unchanged).
- Checks:
  - python3 -I -m py_compile app-log-live.py: OK.
  - python3 app-log-live.py --version: 1.105.20261025.113234.
  - Test suite nginx-tools-tests/run-all.sh: not run in this change (to be run before the pull request is merged).
- Action required: confirm in Odoo that the default language of the website is French.

### 1.104.20261023.210301 - Title: Requests by name (DNS column) in the summary, Ctrl-T included.
- Reason: request: in the summary (key Ctrl-T, and the summary at the end of a session), show the number of requests for each name of the DNS column, only for the names that could be identified. The bare IP addresses must not appear in this count.
- Changes:
  - Stats: new counter `by_name` (identified name -> requests). It is listed in COUNTERS, so the snapshot and the difference of Ctrl-T (since()) handle it like the other counters.
  - Stats.ajouter(): a request is counted under its name when its address has one (the name of the column: DNS name, person, team, server, organization or network). An address without a name is never counted under its own address.
  - Stats.summary(), level 5 (with the most active addresses): « Requests by name (DNS column): N identified, M by address only », then the 10 most requested names, then « +K name(s) not shown » when there are more.
  - Header comment: description of the session summary.
  - lang/app-log-live.fr.po: the four new messages are translated.
  - nginx-tools-tests/test_app_log_live.py: test_requetes_par_nom_dns_seulement_identifies_et_difference_ctrl_t.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases:
  - The names are counted as they are displayed in the column: a name cut by --dns-max-truncate is counted under its cut form, so two long names with the same beginning are counted together.
  - The total of identified and unidentified requests stays exact even when the list of names is cut at 10 lines.
  - The screen anonymisation (A key, --anonymize) applies to these names like to the rest of the screen; the daily journal keeps the real names.
- Checks:
  - py_compile of app-log-live.py; test_requetes_par_nom_dns_seulement_identifies_et_difference_ctrl_t; test_i18n, test_conventions and test_cles_modeles.
  - test_app_log_live: the two menu tests (test_menu_des_touches_et_options_a_la_volee, test_menu_exclure_groupe_bip_et_rapport) fail the same way on the main branch (keys sent to the pseudo-terminal too fast for the machine load); see the pull request.
- Action required: none. The new lines appear in the summary after the update.
### 1.104.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 67 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: app-log-live.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.103.20261022.215046 - Title: RLQ* groups show their identifier and category, so homonyms can be told apart.
- Reason: request: the G key and the end summary listed « RLQ22-Visiteur = 0 » three times without any way to tell the three groups apart. Odoo allows several groups with the same name.
- Changes:
  - apps/_odoo_db.py, groupes_rlq(): the query also reads res_groups.id and the name of the category (ir_module_category). Each group is returned with `id` and `categorie`; the list is sorted by name, then by id. The grouping is still per group id, so homonyms are no longer merged.
  - apps/_odoo_db.py, nom_traduit(): new helper, the translated-name reading moved out of groupes_rlq() (fr_CA, then fr_FR, then en_US, then the first value).
  - app-log-live.py, rlq_group_label(): new helper; a group is written « RLQ22-Visiteur #12 [Événements] = 70 ». The « #id » and the « [category] » parts appear only when the data provides them, so callers that only pass a name and a count get the previous output.
  - app-log-live.py, rlq_group_columns(): uses rlq_group_label() for each cell.
  - nginx-tools-tests/test_app_log_live.py: test_groupes_rlq_homonymes_distingues_par_identifiant_et_categorie.
- Bugs fixed:
  - Symptom: three lines « RLQ22-Visiteur = 0 / 70 / 0 » and two « RLQ22-Commanditaire » lines, impossible to attribute.
  - Diagnosis: the query already grouped by group id, so these were distinct res_groups records sharing the same displayed name; the program printed only the name.
  - Correction: the identifier and the category are read and displayed next to the name.
- Guard rails and edge cases:
  - Read-only: the query is unchanged apart from the two added columns and the join on the category; the prefix is still checked by regex before use.
  - A group without category is shown without brackets; a name that is not valid JSON is kept as it is.
  - Column width is measured on the displayed text, so the longer labels reduce the number of columns on a narrow terminal (as before).
- Checks:
  - py_compile of app-log-live.py and apps/_odoo_db.py; --version.
  - Unit tests of the RLQ* groups (test_groupes_rlq_*), alignment tests and test_conventions.
- Action required: None. To see the identifiers, press G in the menu or read the end summary (Ctrl-C) after updating.

### 1.102.20261022.154430 - Title: U key (menu) for UNDERLINE; saved by the C key.
- Reason: request: add an option U for UNDERLINE in the menu that asks for a number, and make sure it is saved with the C key.
- Changes: - MENU_KEYS: U = underline; the menu lists « U --underline N » (current value, 0 = none) in alphabetical order. - Key handler underline: asks for N (0 to 1000; Enter = 10, the default), applies it at once to the output (output.underline) and to options["underline"]. - config_values(): UNDERLINE is written by the C key (only when changed since startup, like the other settings). - main(): options["underline"] is set from the value in use at startup (command line, or UNDERLINE of the configuration file). - C key help: UNDERLINE added to the list of savable settings. - --underline help: « U key of the menu; UNDERLINE of the configuration file ». - Header comment, lang/app-log-live.fr.po and doc/en and doc/fr 07-app-log-live.md updated.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases: - 0 means no underlined line, as on the command line; a non-number is refused with the usual message and nothing changes. - Only what changed since startup is written by C; an unchanged value is not written. - The value is kept in memory only until C is pressed (or the program ends).
- Checks: - py_compile; --version.
- Action required: None.

### 1.101.20261022.154316 - Title: F key (steps line) works without a recording in progress.
- Reason: request: the F key should not be available only after R; it must show the steps without requiring a recording to be started first.
- Changes: - show_steps_line(): shows the steps of the recording in progress, otherwise the steps of the LAST recording (kept until the next R), otherwise the hint « Steps: no recording yet (R starts one, then N a step) ». The line of the last recording is prefixed « Last recording - ». - record["last"]: the recording stopped last, set by record_stop(). - F key (steps_line): no longer refuses with « Start a recording (R) »; turning it on shows the line at once. - Menu: the F entry says the steps are those of the recording (or of the last one) and that it works without R. - lang/app-log-live.fr.po: new and changed messages translated; obsolete messages removed. - doc/en and doc/fr 07-app-log-live.md: the F key paragraph.
- Bugs fixed: - Symptom: pressing F without a recording only printed « Start a recording (R) to see the steps on one line », so the key looked unavailable. - Diagnosis: the line was drawn only from the recording in progress (record["r"]); no recording meant nothing to draw. - Correction: the steps are read from the recording in progress or from the last one; the refusal message is gone.
- Guard rails and edge cases: - A recording in progress takes precedence over the last one. - No recording at all: a hint, never an empty line; a text wider than the terminal is cut as before. - Screen only: nothing is written to the journal or to the archive. - The steps of the last recording are kept in memory only, until the next R; a new recording replaces them.
- Checks: - py_compile.
- Action required: None.

### 1.100.20261022.133552 - Title: Runs without root (sudo -n for the advanced commands); PostgreSQL mandatory for the R recording; system context in the archive; menu options in alphabetical order.
- Reason: request: the program must run with a non-root account and use sudo before the advanced functions; the recording must keep the database samples (writes, locks), so PostgreSQL is mandatory; the archive must record whether the program ran as root, the operating system and the tools (psql 18.6 was not recorded); the menu options sorted alphabetically.
- Changes: - privileged() and lancer_root(): fail2ban-client and ipset run as they are when root, through « sudo -n » otherwise (never asks for a password). - R recording refused with an explicit message without psql, without an Odoo database, or without PostgreSQL access through « sudo -n -u postgres ». - Archive: context/system.txt (root or not, sudo, operating system, kernel, Python and tool versions; no user name); db/writes-BASE.log (writes per activity table at each sample). - Journal of the service recorded through sudo -n when not root. - Menu (? key): options sorted alphabetically by option name. - Files: app-log-live.py; doc/en and doc/fr 07-app-log-live.md and app-log-live.conf.example (sudo and PostgreSQL requirements); apps/_record.py 1.2; apps/_odoo_db.py 1.20; apps/_connexions.py 1.2; nginx-tools-tests/fixtures/app-log-live-record-exemple-tests-en-dev.tar.xz (anonymized recording with the context reported by the operator).
- Bugs fixed: - Symptom: psql and runuser were called only as root; with a non-root account there were no database samples and no context in the archive. - Diagnosis: runuser needs root. - Correction: sudo -n -u postgres for an account that is not root; the advanced commands go through sudo -n.
- Guard rails and edge cases: - Without sudo and without root, the commands fail as before, and the messages say so. - The recording never starts blind: without the database samples it is refused.
- Checks: py_compile; --version; test_app_log_live; test_record; test_i18n; test_conventions; test_cles_modeles; test_config_defaut. Non-root run on a temporary account with a limited sudoers rule: --version, --help, and --app odoo --no-follow reach the service check and print the limited-rights message; sudo -n -u postgres psql and sudo -n journalctl work. A full recording could not be run in the test environment (no Odoo service).
- Action required: to use the recording and the advanced functions without root, allow without password for the account: « sudo -n -u postgres psql », « fail2ban-client », « ipset », « journalctl ». The PostgreSQL client (postgresql-client) must be installed.

### 1.99.20261022.122804 - Title: Steps line (F key, --steps-line) and a 60-minute maximum for test recordings.
- Reason: During a test recording the steps (N key) are marked one by one, but nothing shows at a glance what the user is doing. The request: all the steps on one white reverse-video line, toggled on or off. Also, a recording must stop by itself when someone forgets to press R: the limit is now 60 minutes at most.
- Changes: - F key (menu, with the current state) and option --steps-line / STEPS_LINE (yes / no in the configuration file): all the steps of the recording on ONE line, white reverse video (style 30;107, black text on white background, both explicit). Each step: number, state ([OK] ended, - open) and description cut at 24 columns. Shown when turned on, and at each step start or end. - steps_line_text() (new): if the full line does not fit the terminal width, the descriptions are left out and the last step is shown in full. - show_steps_line() (new): screen only, anonymized like the stream (never in the daily journal, never in the archive). - --record-max / RECORD_MAX: default 60 minutes (was 30); the value must be greater than 0 and at most 60 (RECORD_MAX_LIMIT). The help text and the menu are updated. - Files: app-log-live.py; lang/app-log-live.fr.po (6 new messages, help fragment updated); doc/en and doc/fr 07-app-log-live.md; doc/en and doc/fr app-log-live.conf.example (STEPS_LINE, RECORD_MAX=60); doc/nginx-tools.version.
- Bugs fixed: - None (new option; change of a limit).
- Guard rails and edge cases: - Without a recording, F only changes the state and says that a recording is needed; the line is then empty of steps and nothing is written. - The line is cut to the terminal width (no wrap, no broken layout); it is rewritten on each step, so an older copy stays in the scrollback (the stream scrolls). - 0 is refused for --record-max / RECORD_MAX: a recording always has a limit. A value above 60 is refused too, so the limit cannot be bypassed from the command line or the configuration file. - --record-test-log (automatic recording without the keyboard) keeps its own limit (at most 1440 minutes).
- Checks: - py_compile; --version, --help (French and English texts), --record-max 0 and 61 refused. - test_app_log_live: new test test_199_steps_line_touche_F_et_limite_d_enregistrement_60_minutes; test_i18n (catalogue of the French messages), test_conventions, test_cles_modeles, test_config_commune, test_config_defaut, test_record, test_reglages_bannis_limites: OK.
- Action required: If /etc/default/app-log-live.conf or ~/.app-log-live.conf contains RECORD_MAX=0 or a value above 60, change it to 60 or less: otherwise the program stops at startup with a message. To see the steps on one line, add STEPS_LINE=yes or press F during a recording.

### 1.98.20261022.110306 - Title: New defaults (MIN=yes, UNDERLINE=10, -2026- highlighted), option values in English only, configuration template sorted.
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - MIN_DEFAULT = True (new constant): --min is on by default; new option --no-min (shows everything: database, « werkzeug », fetchmail lines); MIN=no in the configuration file does the same. - UNDERLINE_DEFAULT = 10 (was 5): one log line out of 10 underlined by default and for UNDERLINE=yes / --underline without N; --help text updated. - HIGHLIGHT: the default list already held -2026- (HIGHLIGHT_DEFAULT); the template now shows it (#HIGHLIGHT=...,ouvertes,-2026-) and explains that a word ending with a dash is a word, not a removal. - Menu (? key): option states shown as yes / no in every language (was oui / non in French) - the same words as in the configuration file. - doc/en and doc/fr app-log-live.conf.example: keys in alphabetical order in one « Options » section (LANGUAGE and ANONYMIZE included), yes / no values, #MIN=yes, #UNDERLINE=10. - doc/en and doc/fr 07-app-log-live.md: underline every 10 lines, --min by default, English values. - lang/app-log-live.fr.po: --min, --no-min and --underline help texts. - nginx-tools-tests/test_app_log_live.py: the tests written for the full display pass --no-min (run_cmd / run_pty wrappers); the default-underline test uses 11 lines (10th underlined); menu test expects yes; new test test_valeurs_par_defaut_198_min_underline_highlight_et_valeurs_en_anglais.
- Bugs fixed:
  None (change of defaults).
- Guard rails and edge cases: - --no-min, MIN=no (or the old MIN=non, still read) bring back the full display; --min stays accepted. - Old French values (oui, non, aucun) in UNDERLINE / TRUNCATE / booleans are still read with the same meaning; the configuration banner asks to write the English value. - « -2026- » is not taken as « remove 2026 » by the +word / -word syntax (modify_highlight already excluded words ending with a dash). - /etc/default/app-log-live.conf with no active line is refreshed to the new sorted template at the next run (apps/_config.py rafraichir); a file with active lines is never rewritten.
- Checks: - test_app_log_live, test_cles_modeles (new sorting / English-values test), test_config_commune, test_config_defaut, test_i18n: OK. - py_compile.
- Action required: In /etc/default/app-log-live.conf (or ~/.app-log-live.conf), replace any oui / non by yes / no (the program prints the lines to change). Remove an active MIN=no or UNDERLINE=5 line if you want the new defaults.

### 1.97.20261022.100559 - Title: --hide-addons (key q): hide the INFO noise of the Odoo modules.
- Reason: The live stream is flooded by INFO lines of the Odoo modules (cron jobs, websocket, fetchmail...) that hide the lines that matter. The request: hide them, except when there is an error or when an e-mail is sent or a file (PDF...) is generated.
- Changes: - Option --hide-addons (new), key q on the fly (menu, with the current state), configuration key HIDE_ADDONS (yes/no) in doc/en and doc/fr app-log-live.conf.example. - Lines whose logger starts with odoo.addons. and whose level is INFO or DEBUG are discarded, unless ADDONS_KEEP_RE matches (successfully sent, mail_mail, ir_mail_server, mail delivery, smtp, ir_actions_report, pdf, report generated, attachments .pdf/.xlsx/.docx/.csv/.zip). - Line.discard_addons() (new); the same rule is applied to the lines of the reminder shown again after a sign-in. - Command-line summary line (--hide-addons in the list of active filters of the test recording). - Files: app-log-live.py; lang/app-log-live.fr.po (3 new fragments); doc/en and doc/fr 07-app-log-live.md and app-log-live.conf.example; nginx-tools-tests/test_app_log_live.py (new test).
- Bugs fixed:
  None (new option).
- Guard rails and edge cases: - Errors are never hidden: WARNING, ERROR, CRITICAL and any trace (Line.err()), even from odoo.addons.*. - Lines of nginx / werkzeug requests and lines outside odoo.addons.* are never hidden. - Pressing q again shows how many lines were hidden so far. - Without the option, nothing changes (the test checks the complete output). - --min keeps its own rule; the two options combine.
- Checks: - test_app_log_live: new test test_hide_addons_cache_le_bruit_des_modules_sauf_erreurs_courriels_et_pdf (option, key set from configuration file, errors / e-mails / PDF kept); test_min_sans_base... still passes. - py_compile; ruff shows no new warning.
- Action required: To hide the noise by default, add HIDE_ADDONS=oui to /etc/default/app-log-live.conf (or ~/.app-log-live.conf). Otherwise: none.

### 1.96.20261022.083937 - Title: N key: steps of a test (start and end, with a description; steps.txt in the archive).
- Reason: The first archive of the test plan (2026-10-21) could only be read by timestamps: nothing marked where each action of the test started and ended. Each action is now marked by hand during the R recording, with a description, and listed in the archive.
- Changes: - Key N (only while a recording runs): N asks for a description and starts a step; N again ends the open step. The step shows on screen (cyan START / END line), in stream-all.log ([step]) and in records.log. - Archive: steps.txt (new): number, start, end, duration, description. README.txt gives the number of steps. - Help menu (? or h): a line for N. Key line at startup: "N step while recording". - Files: app-log-live.py; apps/_record.py 1.1; lang/app-log-live.fr.po (French); doc/en and doc/fr 07-app-log-live.md; nginx-tools-tests/test_record.py. - Merged with main (1.95 settings keys SUMMARY/UNDERLINE): this change takes 1.96 to avoid a version clash.
- Bugs fixed:
  None (new function).
- Guard rails and edge cases: - N outside a recording starts nothing; a message says to press R first. - Ctrl-C at the description prompt cancels: no step is started. - A step still open when the recording stops is closed then ("recording stopped" in records.log and steps.txt); pressing N for a new step closes the open one first. - The description has its spaces collapsed, is cut at 200 characters and is masked like every other line (addresses, e-mails, tokens); empty = "(no description)". - Numbering restarts at 1 for each recording.
- Checks: - test_record.py: new test (START / END lines in records.log, steps.txt, README count, step closed at the stop). - py_compile and ruff on apps/_record.py, app-log-live.py and test_record.py.
- Action required: None.

### 1.95.20261022.012000 - Title: Settings keys: SUMMARY, and UNDERLINE documented in the default files.
- Reason: Reason: the owner wants every changeable setting available in the configuration file, and default files that list every variable (commented). UNDERLINE was missing from default files created before the key existed.
- Changes: - SCHEMA_CONFIG: new key SUMMARY (--summary: session summary at the end of a --no-follow run). - doc/en and doc/fr app-log-live.conf.example: SUMMARY added. UNDERLINE was already in the code and in both examples (verified). - Action-only options stay on the command line: --diagnose, --diagnose-host, --modules, --modules-latest, --no-follow, --rate-limit, --record-test-log, --keep-ip (hidden legacy option).
- Bugs fixed: - Symptom: UNDERLINE absent from /etc/default/app-log-live.conf. Diagnosis: the file was created before the key existed, and an existing file is never completed automatically. Fix: add the line by hand (see Action required).
- Guard rails and edge cases: - A key that is absent or empty keeps the default (UNDERLINE=5, SUMMARY off). - Command-line options still take precedence over the file.
- Checks: - py_compile and ruff on the program; test_cles_modeles (every schema key is present in both examples).
- Action required: Add `UNDERLINE=5` and `SUMMARY=non` to /etc/default/app-log-live.conf if you want them written in the file (new installs get them automatically).

### 1.94.20261021.095843 - Current version. Earlier history archived outside the repository.

## host-perf-audit.py

### 1.5.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 8 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: host-perf-audit.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.4.20261020.211944 - Current version. Earlier history archived outside the repository.

## odoo-chat-post.py

### 1.10.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 10 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: odoo-chat-post.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.9.20261022.012000 - Title: Settings keys: BOT_LOGIN and CATALOG.
- Reason: Reason: every setting in the command line gets a key; actions remain on the command line.
- Changes: - SCHEMA_CONFIG: new keys BOT_LOGIN (--bot-login) and CATALOG (--catalog). - doc/en and doc/fr odoo-chat-post.conf.example: both added. - Command-line only (actions or per-run inputs): --bot-config, --create, --create-bot, --dry-run, --list, --message, --post, --renew-key.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases: - An empty CATALOG= line is ignored (the shipped catalogue is used).
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.8.20261020.211944 - Current version. Earlier history archived outside the repository.

## odoo-docs.py

### 1.5.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 7 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: odoo-docs.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.4.20261020.211944 - Current version. Earlier history archived outside the repository.

## odoo-mail-retry.py

### 1.16.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 11 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: odoo-mail-retry.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.15.20261022.012000 - Title: The common file now reaches LOG_KEEP_DAYS and ANONYMIZE.
- Reason: Reason: same as odoo-warmup.py: the common-file filter discarded LOG_KEEP_DAYS and ANONYMIZE.
- Changes: - read_config(): the common file accepts LOG_KEEP_DAYS and ANONYMIZE; both are exported to the environment (environment wins).
- Bugs fixed: - Symptom: ANONYMIZE in app-default.conf ignored. Diagnosis and fix as in odoo-warmup.py.
- Guard rails and edge cases: - Invalid ANONYMIZE value reported and ignored.
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.14.20261020.211944 - Current version. Earlier history archived outside the repository.

## odoo-warmup.py

### 1.26.20261025.215544 - Odoo ports read from the Odoo service, without the configuration file

- Title: When no configuration file can be read, the HTTP and gevent ports come from the command line of the Odoo processes and from ExecStart of their systemd unit.
- Reason: The account running the warm-up cannot read the Odoo configuration file; the Odoo service (systemctl) gives the ports and the configuration path without reading that file.
- Changes:
  - ports_de_ligne_de_commande(): --http-port, --gevent-port and -c/--config read in a command line.
  - commandes_odoo(): command lines of the Odoo Python processes (/proc) and ExecStart of their units (systemctl show, no root).
  - ports_du_service(): ports and configuration path from these command lines.
  - odoo_conf_ports(): used when no configuration file is found; the configuration file is read only if it is readable and no port was found in the command lines.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py.
- Bugs fixed:
  - Symptom: as a normal user, no port is detected because the configuration file is not readable.
  - Diagnosis: the program needed the file to read the ports, although the service carries them.
  - Correction: the ports are read from the service first.
- Safeguards and edge cases:
  - If the service gives no port and the file is not readable, the detection works as before (listening sockets, then 8069).
  - systemctl missing or failing: ignored.
- Checks:
  - py_compile; test suite test_odoo_warmup (16 tests, with a fake /proc and a fake systemctl). Not tested on a real systemd host.
- Action required: none, but check on the server: systemctl show -p ExecStart --value <unit> must show --http-port or -c; send the output if the detection still fails.

### 1.25.20261025.214951 - Non-root account: unreadable configuration reported, detection probe 10 s

- Title: When the Odoo configuration file cannot be read by the account, the warm-up says so and tells how to set URL; the detection probe waits 10 s.
- Reason: Run as a normal user, the warm-up found no port: the probe of 10000 timed out after 3 s (HTTP 0 in 3.02 s) and the configuration file was not read, so the message gave no reason.
- Changes:
  - config_illisibles(): configuration files matching the candidate patterns that exist but are not readable by this account.
  - detect_odoo_url(): when no port is detected, warns about these files and prints how to set URL (or ~/.odoo-warmup.conf).
  - PROBE_TIMEOUT: 3 s to 10 s.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: as a normal user, "No single Odoo port detected, default http://127.0.0.1:8069" and Odoo never answers on 8069.
  - Diagnosis: the detection does not read a configuration file it cannot open (silent OSError); the probe of 10000 was cut at 3 s.
  - Correction: explicit warning, longer probe timeout.
- Safeguards and edge cases:
  - A file the account can read is used as before; no change for root.
  - A configuration file in a home directory that the account cannot enter is not seen by glob: the hint about URL still applies.
- Checks:
  - py_compile; test suite test_odoo_warmup (15 tests).
- Action required: as a normal user, set URL=http://127.0.0.1:10000 in /etc/default/odoo-warmup.conf (or ~/.odoo-warmup.conf), or ask for read access to the configuration file.

### 1.24.20261025.212138 - Odoo unit found from its running process for --systemd-install

- Title: Without --service, --systemd-install and --systemd-remove use the systemd unit that runs the Odoo Python process, not odoo.service.
- Reason: The default unit odoo.service does not exist on the server; the Odoo service has another name (see systemctl status of the Odoo process).
- Changes:
  - odoo_units(): reads /proc/PID/cgroup of each Python process whose command line mentions odoo and keeps the NAME.service of that process (no root needed).
  - Order for the unit: --service, then SERVICE of the configuration, then the unit found in the process, then odoo.service (with a warning).
  - Several Odoo units found: error, asking for --service UNIT (nothing is written).
  - --service help text updated.
  - Files: odoo-warmup.py, nginx-tools-tests/test_odoo_warmup.py.
- Bugs fixed:
  - Symptom: --systemd-install without --service writes odoo.service.d/odoo-warmup.conf for a unit that does not exist, so the warm-up never runs after a start.
  - Diagnosis: DEFAULT_SERVICE was used as soon as no --service or SERVICE was given, without looking at the running Odoo.
  - Correction: the unit is read from the running process.
- Safeguards and edge cases:
  - No Odoo process running: odoo.service is used and a warning says so.
  - Two or more Odoo units: nothing is written.
  - A normal run (no --systemd-*) does not change.
- Checks:
  - py_compile; test suite test_odoo_warmup (new test with a fake /proc tree).
- Action required: run --systemd-install again without --service (or with --service NAME.service) so the drop-in is written for the right unit; remove the wrong drop-in /etc/systemd/system/odoo.service.d/odoo-warmup.conf if it was created.

### 1.23.20261025.211244 - Odoo configuration file found when its path has a * pattern

- Title: The Odoo configuration file is found through the default patterns (for example /home/*/git/erplibre/config.conf), so its http_port and gevent_port are used.
- Reason: The configuration file was not found in the real run, so the gevent port 10002 was not excluded and was probed as an HTTP instance. That probe returned HTTP 500 on the Odoo side, at the start of every run.
- Changes:
  - odoo_conf_ports(): uses trouver() of apps/_odoo_conf.py, which expands the * patterns; before, the patterns were tested literally with os.path.isfile().
  - apps/_odoo_conf.py (shared module, version 1.5.20261025.211244): _reglage() accepts spaces around the "=" of ODOO_CONF_PATHS in nginx-hardening.conf; the key is escaped.
  - Files: odoo-warmup.py, apps/_odoo_conf.py.
- Bugs fixed:
  - Symptom: the first request of a run is a probe to http://127.0.0.1:10002/web/login, answered with HTTP 500 by Odoo, although config.conf says gevent_port = 10002.
  - Diagnosis: chemins_candidats() returns the default patterns as plain text; os.path.isfile("/home/*/git/erplibre/config.conf") is always False, so no configuration file was read and no port was excluded.
  - Correction: trouver() develops the patterns, as the other programs do.
- Safeguards and edge cases:
  - Without a configuration file, the behaviour is unchanged (candidates from the listening sockets, then 8069).
  - Workaround until this version: HOST=odoo-dev.rencontres-linux.quebec in /etc/default/odoo-warmup.conf skips the detection entirely.
- Checks:
  - py_compile of both files; test suite test_odoo_warmup and test_odoo_conf (to run).
- Action required: none.

### 1.22.20261025.210356 - Odoo found by the owner of its processes, without root

- Title: The Odoo ports are those listened to by the account that runs an Odoo Python process; works without root.
- Reason: Without root, ss does not show the process of another account, so the Python process was not seen and the detection fell back to 8069. The owner (UID) of each listening socket is shown without root (ss -e: uid:N; netstat: User column).
- Changes:
  - odoo_uids(): UIDs of the processes whose command line contains python and odoo (read in /proc).
  - odoo_ports_listening(): listening TCP sockets owned by one of these UIDs (ss -ltnHe, then netstat -tlen).
  - Client(timeout=...): optional timeout; detection probes use PROBE_TIMEOUT (3 s), so a port that is not HTTP does not block for 120 s.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: "No single Odoo port detected, default http://127.0.0.1:8069" when run without root.
  - Diagnosis: the Python process of Odoo was not visible without root in ss -ltnp.
  - Correction: owner UID instead of process name.
- Safeguards and edge cases:
  - No Odoo process visible: no candidate from the processes; the configuration file and the default port still apply.
  - Each candidate must still answer 200 with "odoo" on /web/login.
- Checks:
  - py_compile; test suite test_odoo_warmup; parsing of ss and netstat samples (10002 and 10000 found, UID 0 ignored).
- Action required: none.

### 1.21.20261025.202416 - Request trace for diagnosis (ODOO_WARMUP_TRACE)

- Title: With the environment variable ODOO_WARMUP_TRACE set, each request of the warm-up is written to stderr with its URL, HTTP code and duration.
- Reason: The 500 error in the Odoo log could not be reproduced by replaying the requests one by one; the exact sequence of the real run is needed.
- Changes:
  - Client.request_() wraps the former request_() (renamed _request()); the trace is printed only when ODOO_WARMUP_TRACE is set.
  - Files: odoo-warmup.py.
- Bugs fixed: none (diagnosis aid).
- Safeguards and edge cases:
  - Without the variable, the output and the behaviour are unchanged.
- Checks:
  - py_compile; test suite test_odoo_warmup.
- Action required: none. To diagnose: ODOO_WARMUP_TRACE=1 odoo-warmup.py 2>&1 | tee /tmp/trace.txt, then send the TRACE lines and the matching Odoo log lines.

### 1.20.20261025.194640 - Site name read from the nginx configuration

- Title: Without HOST, the warm-up finds the site name in the nginx configuration and goes through nginx.
- Reason: The warm-up went directly to Odoo when HOST was not set, which produced the REQUEST_URI error at each start. The nginx configuration differs from one server to another, so the name is read from the files, not hard-coded.
- Changes:
  - nginx_names_for_port(PORT): reads NGINX_DIR/nginx.conf and sites-enabled/* (includes followed, comments removed), finds the upstream blocks that point to 127.0.0.1:PORT and the server blocks whose proxy_pass reaches them (directly or through set $variable), and returns their server_name (without _).
  - via_nginx(HOST): probes /web/login over HTTPS with the site name (certificate checked).
  - main(): HOST set -> nginx first, direct detection otherwise. HOST not set -> direct detection, then the site name from nginx when exactly one name reaches the Odoo port, then nginx.
  - Several names reach the port: nothing is chosen; the message asks for HOST.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: KeyError REQUEST_URI at each warm-up run while the visitors (through nginx) get no such error.
  - Diagnosis: HOST was missing from the configuration, so the warm-up bypassed nginx.
  - Correction: automatic site name from the nginx configuration.
- Safeguards and edge cases:
  - Reading the configuration needs no root (NGINX_DIR files are readable).
  - Absent or unreadable nginx files: no name, direct connection as before.
  - Two names reaching the port: no choice.
  - Include depth limited to 5.
- Checks:
  - py_compile; test suite test_odoo_warmup; a copy of the server's configuration (upstream odoo -> 127.0.0.1:10000, set $odoo_backend odoo, include of the name file): 10000 gives odoo-dev.rencontres-linux.quebec, 9999 gives nothing; a second vhost to 10000 gives two names.
- Action required: none if the configuration is as expected. If the warm-up says several names, set HOST in /etc/default/odoo-warmup.conf.

### 1.19.20261025.192521 - Default wait of 20 seconds instead of 120

- Title: The default --wait (and key WAIT) is 20 seconds.
- Reason: Requested. Odoo is normally up well before 120 seconds; a shorter default fails sooner when the service is really stopped.
- Changes:
  - DEFAULT_WAIT: 120 -> 20. REQUEST_TIMEOUT (120 s per request) is unchanged.
  - doc/fr and doc/en odoo-warmup.conf.example: #WAIT=20.
  - Files: odoo-warmup.py, doc/fr/odoo-warmup.conf.example, doc/en/odoo-warmup.conf.example.
- Bugs fixed: none.
- Safeguards and edge cases:
  - A slow start longer than 20 seconds: use --wait 120 or WAIT=120 in the configuration file.
- Checks:
  - py_compile; test suite test_odoo_warmup.
- Action required: none, unless Odoo needs more than 20 seconds to answer after a restart; then set WAIT=120.

### 1.18.20261025.192316 - Warm-up through nginx, as the visitors do, when HOST is set

- Title: With the key HOST, the warm-up goes through nginx (HTTPS on this machine), and directly to Odoo only if nginx does not answer.
- Reason: The warm-up asked Odoo directly on its port, without nginx. Odoo then gets no REQUEST_URI, and the first render of /en_CA/web/login fails with KeyError REQUEST_URI at each start. Visitors go through nginx and do not see this error.
- Changes:
  - New key HOST (site name, in /etc/default/odoo-warmup.conf or ~/.odoo-warmup.conf). Used only when URL and --url are not set.
  - _NginxConnection / _NginxHandler: the TCP connection goes to 127.0.0.1:443 (NGINX_ADDRESS); the TLS name (SNI), the Host header and the certificate check use HOST, as a browser does. The system proxy is not used.
  - main(): with HOST, nginx is probed on /web/login; if it answers 200, 302 or 303, the warm-up uses https://HOST; otherwise direct detection (1.14 to 1.15) applies.
  - Files: odoo-warmup.py, lang/odoo-warmup.fr.po (keys list in the help and in the messages).
- Bugs fixed:
  - Symptom: a KeyError REQUEST_URI in the Odoo log at each warm-up run, never for visitors.
  - Diagnosis: the warm-up bypassed nginx; the visitors' path through nginx does not raise it (200 on the same page via nginx, HTTP/HTTPS on the local address).
  - Correction: the warm-up uses the same path as the visitors when HOST is set.
- Safeguards and edge cases:
  - The certificate is checked for HOST: a wrong name or an invalid certificate makes nginx count as not answering, and the direct path is used.
  - Without HOST, behaviour is unchanged.
- Checks:
  - py_compile; test suite test_odoo_warmup; local TLS server with a self-signed certificate for odoo-dev.test: the right name answers 200 and the Host header is received; a wrong name gives no answer (0).
- Action required: add HOST=odoo-dev.rencontres-linux.quebec to /etc/default/odoo-warmup.conf (or ~/.odoo-warmup.conf), then run the warm-up. Check that the Odoo log no longer shows KeyError REQUEST_URI.

### 1.17.20261025.191509 - Up to four tries for a public page answering 5xx

- Title: A public page answering 5xx is requested up to four times, one second apart.
- Reason: After a restart, Odoo runs several processes and each builds its template cache at its first render. One retry (version 1.16) could still reach a process that was not ready yet. The log showed a 500, then a 200 one second later on the same page.
- Changes:
  - load_page(): up to PUBLIC_ATTEMPTS (4) tries, RETRY_PAUSE (1 second) between them; the last answer is recorded.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: a 500 in the Odoo log at each start, even with 1.16.
  - Diagnosis: a single retry does not guarantee to reach a warm process; the log showed several processes loading the registry.
  - Correction: several tries.
- Safeguards and edge cases:
  - Only 5xx answers are retried; a 404 (optional page) is not.
  - A page still answering 5xx after four tries is recorded as a failure.
  - Calling /web/login first was considered and not kept: it answers 303 and does not render the layout.
- Checks:
  - py_compile; test suite test_odoo_warmup; scripted client: 500, 500, 200 is recorded as 200 after 3 calls; five times 500 is recorded as 500 after 4 calls.
- Action required: none. The 500 may still appear in the Odoo log at a cold start; the warm-up reports it as success if a later try answers 200.

### 1.16.20261025.185140 - One retry for a public page answering 5xx

- Title: A public page answering 5xx is requested once more after one second.
- Reason: On the development server, the first request for a language-prefixed page (/en_CA/web/login) fails with a 500 (KeyError REQUEST_URI while Odoo builds its template cache), and the next request for the same page succeeds. The warm-up triggered this error at every run, and the error filled the Odoo log.
- Changes:
  - load_page(): a 5xx answer is requested once more after RETRY_PAUSE (1 second); the second answer is the one recorded.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: a 500 in the Odoo log for each warm-up run, although the warm-up reported 0 failure.
  - Diagnosis: first render of the page fails while the template cache is built; the warm-up is the first client to request these pages.
  - Correction: one retry. The cache is then built by the warm-up, not by the first visitor.
- Safeguards and edge cases:
  - Only 5xx answers are retried; a 404 (optional page) is not.
  - A page failing twice is still recorded as a failure.
- Checks:
  - py_compile; test suite test_odoo_warmup; scripted client: 500 then 200 is recorded as 200 after 2 calls; 500 twice is recorded as 500.
- Action required: none. The Odoo log may still show one 500 per language variant on a cold start; the root cause (REQUEST_URI absent on the direct port) is to be checked on the server.

### 1.15.20261025.175745 - The gevent port is not an Odoo instance

- Title: The gevent (long polling) port of the Odoo configuration file is never taken for a second instance.
- Reason: Odoo uses two ports: http_port (the web site, 10000 on the server) and gevent_port (long polling, 10002). Both listen, so the detection saw two instances and stopped.
- Changes:
  - odoo_conf_ports() replaces odoo_ports_from_conf(): returns the HTTP port and the gevent port of the configuration file.
  - The gevent port is removed from the listening-port candidates and is never probed as an HTTP instance.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: "several Odoo instances answer on ports [10000, 10002]" on a single Odoo instance.
  - Diagnosis: the gevent port was a candidate like the HTTP port.
  - Correction: exclusion of the gevent port.
- Safeguards and edge cases:
  - Without a configuration file, the gevent port is unknown; it is then only accepted if it answers 200 with "odoo" on /web/login.
- Checks:
  - py_compile; test suite test_odoo_warmup; a configuration with http_port 10000 and gevent_port 10002 gives 10000 only.
- Action required: none if the configuration file is found. Otherwise set URL in /etc/default/odoo-warmup.conf.

### 1.14.20261025.175011 - Automatic detection only when a single Odoo instance answers

- Title: Automatic detection only when exactly one Odoo instance answers; the program never needs root.
- Reason: Several Odoo instances can run on one server (for example ports 10002 and 10000). Choosing one of them silently is wrong. The program must also run as a normal user.
- Changes:
  - An Odoo instance is recognised by /web/login answering 200 with "odoo" in the page, not only by a listening port.
  - Exactly one Odoo instance: it is used and shown. Several: detection stops with an error and asks for --url or URL. None answering: the single candidate (Odoo may be starting), else 127.0.0.1:8069.
  - Priority unchanged: --url, then URL in the configuration file, then detection.
  - Root: not needed. Only --systemd-install and --systemd-remove write systemd files and need root.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: a warning about several Odoo ports did not stop the run; the first port was used.
  - Diagnosis: the detection chose the first answering port.
  - Correction: refusal when several instances answer.
- Safeguards and edge cases:
  - Without root, process command lines may be unreadable: the Odoo page check still applies.
  - A listening Python process that is not Odoo (no "odoo" on its login page) is ignored.
- Checks:
  - py_compile of odoo-warmup.py; test suite test_odoo_warmup; fake Odoo servers on 10002 and 10000: refusal, then detection of 10002 alone.
- Action required: if the server has several instances, set URL in /etc/default/odoo-warmup.conf (or give --url).

### 1.13.20261025.174351 - Port detection with netstat, and warning when several Odoo ports answer

- Title: Port detection also works where ss is missing (netstat), and several answering Odoo ports are reported.
- Reason: On the production server (Debian-like, netstat installed, ss absent) the detection found nothing, so the default 8069 was used. Odoo listens on 10002 and 10000 (python3). Also, when several Odoo ports answer, the first one was used silently.
- Changes:
  - Listening sockets: ss -ltnpH first, then netstat -tlnp when ss is missing or empty (function _listening_lines()).
  - Several answering ports: the first one is still used, but a WARNING line lists all of them and asks for --url or URL.
  - Files: odoo-warmup.py.
- Bugs fixed:
  - Symptom: "No Odoo port detected, default http://127.0.0.1:8069" although python3 processes listen on 10002 and 10000.
  - Diagnosis: the program only knew the ss command; netstat output was not read.
  - Correction: netstat fallback and parser checked on the netstat output of the server.
- Safeguards and edge cases:
  - Without root, a process command line can be unreadable: the process name (python) is then accepted.
  - Neither ss nor netstat available: no candidate from the processes; configuration file and default port still apply.
- Checks:
  - py_compile of odoo-warmup.py; parser run on the netstat output of the server (ports 10002 and 10000 found).
- Action required: none. If the warning appears on the server, choose the port with --url or URL in /etc/default/odoo-warmup.conf.

### 1.12.20261025.172228 - Automatic detection of the Odoo port

- Title: Automatic detection of the Odoo HTTP port when --url and URL are not set.
- Reason: The default address 127.0.0.1:8069 was used even when Odoo listens on another port (for example 10002 on the development server), so the warm-up waited for an address that does not answer.
- Changes:
  - New functions odoo_ports_from_conf() (HTTP port of the first Odoo configuration file found, through apps/_odoo_conf.py), odoo_ports_listening() (TCP ports of the Python processes whose command line mentions odoo, through ss) and detect_odoo_url() (probe of each candidate on /web/login).
  - Order of the candidates: configuration file, then listening Odoo processes. The first one answering 200, 302 or 303 is used.
  - Priority unchanged: --url on the command line, then URL in the configuration file, then detection, then http://127.0.0.1:8069.
  - The detected address is shown on the screen, in French and English.
  - Files: odoo-warmup.py (version, detection functions, --url help text), lang/odoo-warmup.fr.po (French text of the new messages and of the --url help).
- Bugs fixed:
  - Symptom: with a port other than 8069 and no explicit URL, the warm-up stopped with "Odoo does not answer at http://127.0.0.1:8069".
  - Diagnosis: the default URL was fixed in the code; nothing looked at the port Odoo really uses.
  - Correction: detection described above.
- Safeguards and edge cases:
  - Without root, the command line of other users' processes cannot be read: the process name (python) is then accepted.
  - ss missing or failing: no candidate from the listening processes, the configuration file and the default port still apply.
  - No candidate answering: the first candidate is used, so the wait loop reports the real port.
- Checks:
  - py_compile of odoo-warmup.py.
  - Test suite nginx-tools-tests/test_odoo_warmup.py (see the result in the pull request).
- Action required: none.

### 1.11.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 5 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: odoo-warmup.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.10.20261022.012000 - Title: The common file now reaches LOG_KEEP_DAYS and ANONYMIZE.
- Reason: Reason: app-default.conf defines five common keys (apps/_config.py CLES_COMMUNES), but this program read only LANGUAGE, VERBOSE and DEBUG_LEVEL from it.
- Changes: - read_config(): the common file accepts LOG_KEEP_DAYS and ANONYMIZE. - LOG_KEEP_DAYS and ANONYMIZE are exported as NGINX_TOOLS_LOG_KEEP_DAYS and NGINX_TOOLS_ANONYMIZE (only if not already set in the environment). - Comment updated to list the five keys.
- Bugs fixed: - Symptom: ANONYMIZE=yes in app-default.conf had no effect on odoo-warmup. Diagnosis: the common-file filter discarded every key except three. Fix: accept the two keys.
- Guard rails and edge cases: - An environment variable already set wins over the file. - An invalid ANONYMIZE value is reported and ignored.
- Checks: - py_compile, ruff, test_cles_modeles.
- Action required: None.

### 1.9.20261020.211944 - Current version. Earlier history archived outside the repository.

## web-monitor.py

### 2.79.20261025.153031 - Test of the ban question no longer depends on its spacing

- Title: Three tests waited for the French text "[N] aucune" to answer the ban question; the terminal shows "[N]  aucune" (two spaces), so they timed out.
- Reason: The test suite failed on this server (two of them, then three with the same cause); the program itself was correct.
- Changes:
  - nginx-tools-tests/test_web_monitor.py: the three waits now look for "[N]", the marker of the question, whatever the spacing or the translation.
  - Files: nginx-tools-tests/test_web_monitor.py, web-monitor.py (version only), CHANGELOG.md.
- Bugs fixed: test only, no program change. Diagnosis: the prompt was displayed correctly; only the expected text was wrong.
- Safeguards and edge cases: the answers sent are unchanged (o, Enter, c); the program's behaviour is untouched.
- Checks: test_web_monitor (85 tests, OK); ruff E9/F on the program: clean.
- Action required: none.

### 2.78.20261023.210301 - Title: Requests per DNS name (Host) for each period in --summary.
- Reason: request: --summary gives the figures for today, D-1, D-2, 7 days and 30 days, but the names requested (Host, the DNS column) were only given for the whole 30 days. The number of requests per name over several days is needed.
- Changes:
  - collect_summary(): facts["hotes_periodes"]: for each Host name, the number of site requests in each of the five periods (the same windows as the funnel). A line without a Host field is counted under the empty name. The requests of this server's own programs are excluded, as before.
  - show_summary(): new table after the firewall lines, « REQUESTS BY DNS NAME (Host), SITE LOGS », with the same columns and the same asterisk for the partial periods as the funnel. The 15 most requested names are shown (sorted by the 30-day figure, then by today), the others are summed in one line « N other name(s) », and the lines without a Host field in « (no Host field: older log lines) ».
  - A name longer than the label column is cut with "...".
  - lang/web-monitor.fr.po: the three new messages are translated.
  - nginx-tools-tests/test_web_monitor.py: test Bilan.test_requetes_par_nom_dns_par_periode.
- Bugs fixed:
  None in this change.
- Guard rails and edge cases:
  - Only the site logs (nginx access logs) are counted, like the existing line « Names requested (Host) ». The catch-all sensor and blocked-probes.log are not counted per name.
  - The numbers of the new table are aligned in the same columns as the funnel (the first alignment test of --summary checks it).
  - A period without any request shows 0; the figures of the rows add up to the « Requests on the site » line, except for the names cut into « other name(s) », which are summed.
- Checks:
  - py_compile of web-monitor.py; manual run of --summary on synthetic nginx logs (today, yesterday, five days ago, lines without host=, one request from this server), in English and in French.
  - test_requetes_par_nom_dns_par_periode, test_sommaire_chiffres_alignes_a_droite_avec_les_pourcentages_a_part, test_i18n, test_conventions and test_cles_modeles.
  - test_web_monitor: the two Surveillance tests (test_fin_de_passage_c_passe_par_l_enquete_de_ban, test_fin_de_passage_o_bannit_toutes_n_aucune) fail the same way on the main branch; not related to this change.
- Action required: none. The table appears in the next --summary run.
### 2.78.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 40 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: web-monitor.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 2.77.20261022.110306 - Title: Option values in English only in the configuration summary; template sorted.
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - Configuration summary line: boolean options shown as yes / no in every language (was oui / non in French). - doc/en and doc/fr web-monitor.conf.example: keys in alphabetical order, yes / no values.
- Bugs fixed:
  None.
- Guard rails and edge cases: - Old oui / non values are still read (apps/_config.py) with a warning.
- Checks: - py_compile; test_cles_modeles.
- Action required: None.

### 2.76.20261020.211944 - Current version. Earlier history archived outside the repository.

## zip-versions.py

### 1.16.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 10 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: zip-versions.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.15.20261020.211944 - Current version. Earlier history archived outside the repository.

## odoo-backup.sh

### 1.21.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 61 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: odoo-backup.sh.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Help texts and generated configuration templates are not translated (they are displayed, or compared with shipped files, by the tests): their French text is kept on purpose.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.20.20261022.012000 - Title: Comment corrected for the common file (no behaviour change).
- Reason: Reason: the comment said only VERBOSE and DEBUG_LEVEL are read from app-default.conf. LANGUAGE and ANONYMIZE are in fact read through apps/_i18n.sh, and LOG_KEEP_DAYS does not apply to this program.
- Changes: - Comment only (line ~256).
- Bugs fixed:
  None: the behaviour was checked and is correct.
- Guard rails and edge cases: - No code change.
- Checks: - shellcheck, bash -n.
- Action required: None.

### 1.19.20261020.211944 - Current version. Earlier history archived outside the repository.

## odoo-update-module.sh

### 1.20.20261025.150359 - Logged-in users count only if active in the last 15 minutes

- Title: A logged-in user keeps the site "busy" only if active in the last CONNECTED_WINDOW minutes (15 by default).
- Reason: The maintainer asked that a logged-in user is considered present only while active during the last 15 minutes, because a session can
  stay valid for much longer without activity.
- Changes:
  - odoo-update-module.sh: new key CONNECTED_WINDOW (default 15); visiteurs_connectes uses it instead of VISITOR_WINDOW.
  - doc/en and doc/fr: odoo-update-module.conf.example and 09-odoo-update-module.md list the key.
  - lang/odoo-update-module.en.po: translation of the help line.
  - Files: odoo-update-module.sh, doc/en/odoo-update-module.conf.example, doc/fr/odoo-update-module.conf.example,
    doc/en/09-odoo-update-module.md, doc/fr/09-odoo-update-module.md, lang/odoo-update-module.en.po, CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases: if the PostgreSQL table cannot be read, the logged-in delays still apply (unknown state).
- Checks: bash -n; shellcheck not re-run for this change (no new construct); test_odoo_update_module.py (39 tests, OK); test_i18n.py (32 tests, OK).
- Action required: none.

### 1.19.20261025.130618 - ShellCheck clean: unused variables removed

- Title: ShellCheck warnings on the start-up and wait changes fixed (no behaviour change).
- Reason: The maintainer pointed out that ShellCheck was available to check the program; the check reported three warnings (SC2034) on code added
  in 1.17 and 1.18.
- Changes:
  - odoo-update-module.sh: CLI_WAIT removed (the fixed delay is WAIT_QUIET, non-empty when given); unused local var removed from demander_attentes;
    FORCE_BUSY kept for compatibility, with a ShellCheck directive above the option loop.
  - Files: odoo-update-module.sh, CHANGELOG.md.
- Bugs fixed: none (no behaviour change).
- Safeguards and edge cases: --wait-quiet still fixes the delay for every profile; the question about the maximal waits is still skipped when WAIT_QUIET is set.
- Checks: shellcheck -x odoo-update-module.sh (ShellCheck 0.11.0, from the project archive): clean; bash -n; test_odoo_update_module.py (39 tests, OK).
- Action required: none.

### 1.18.20261025.125933 - Maximum waits by profile: logged-in users 60/3 min, anonymous visitors 30/2 min

- Title: Maximum wait depends on who is on the site (logged-in users or anonymous visitors) and on the activity level.
- Reason: The maintainer asked that a logged-in user who is active on the website allows at most 60 minutes of waiting (3 minutes when the
  activity is low), and that when only anonymous visitors are present, who can change little, the maximum is 30 minutes (2 minutes when the
  activity is low). Confirmed definitions: a logged-in user is a website_visitor row with partner_id set and last_connection_datetime within the
  VISITOR_WINDOW; low activity is fewer than LOW_REQUESTS (10) requests, robots excluded, in the same window.
- Changes:
  - odoo-update-module.sh: new functions visiteurs_connectes (PostgreSQL, table website_visitor), requetes_recentes (nginx logs),
    attente_maximale (sets ATTENTE_MAX and ATTENTE_PROFIL, checked at every poll). The 2 maxima and their low-activity values are read from the
    configuration files (WAIT_CONNECTED, WAIT_CONNECTED_LOW, WAIT_ANONYMOUS, WAIT_ANONYMOUS_LOW) and LOW_REQUESTS.
  - WAIT_QUIET is now empty by default: a value given (configuration or --wait-quiet) fixes the delay for every profile.
  - Start-up questions and the 5-minute prompt now ask the two maxima (logged-in, anonymous) unless WAIT_QUIET is fixed.
  - The busy messages show the current maximum and its profile.
  - doc/en and doc/fr: odoo-update-module.conf.example and 09-odoo-update-module.md list the new keys.
  - lang/odoo-update-module.en.po: translations of the new messages; obsolete entries removed.
  - nginx-tools-tests/test_odoo_update_module.py: expectation updated for the new wording.
  - Files: odoo-update-module.sh, doc/en/odoo-update-module.conf.example, doc/fr/odoo-update-module.conf.example,
    doc/en/09-odoo-update-module.md, doc/fr/09-odoo-update-module.md, lang/odoo-update-module.en.po,
    nginx-tools-tests/test_odoo_update_module.py, CHANGELOG.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - If the PostgreSQL table cannot be read, the logged-in delays apply (users are never cut short by an unknown state).
  - If the nginx logs cannot be read, the request count is unknown and the normal activity delay applies.
  - Writes still block the update at the end of the wait, whatever the profile.
- Checks:
  - bash -n; --help shows the new keys; test_odoo_update_module.py (39 tests); test_i18n.py (32 tests); test_docs.py; test_config_defaut.py
    (the only failure is app-log-live.py --show-ip, not related to this change).
- Action required: confirm that the reading of "activité faible" (fewer than 10 requests in the window) and of the logged-in user (website_visitor)
  matches what you want; check that the Odoo version of this server has website_visitor.last_connection_datetime.

### 1.17.20261025.124729 - Start-up questions (threshold, window, wait); reads allowed, writes never; 5-minute settings prompt

- Title: Start-up questions and periodic settings prompt; a write always blocks the update, reads alone do not.
- Reason: The maintainer asked that the threshold, the counting window and the wait time be asked when the script starts (defaults taken from the
  configuration files, after 10 seconds without an answer), that the busy message show the time, that the wording "visiteurs actifs" be used, and
  that every 5 minutes during the wait the script asks whether to change the settings (10 seconds to answer). The update must never run while the
  database or the website is being written to, but may run when there are only reads.
- Changes:
  - odoo-update-module.sh: new functions peut_demander, question_reponse, lire_nombre, demander_parametres_demarrage (asked before the checks),
    changer_parametres (asked every ODOO_UPDATE_MODULE_ASK_EVERY seconds, default 300, during the wait).
  - wait_for_quiet_site: prints "[HH:MM:SS] site occupé :" at each check; at the end of the wait, a write blocks the update (cancelled, nothing
    stopped), reads alone let it go ahead with a warning.
  - site_reasons: each reason is tagged W (write or unreadable value, always blocks) or R (active visitors only, reads). Messages now say
    "visiteurs actifs".
  - active_visitors: takes the window in seconds (default 300).
  - New option --visitor-window MIN and configuration key VISITOR_WINDOW (default 5). The three questions are skipped for the values given on the
    command line.
  - --force-busy: kept for compatibility; it no longer overrides a write (it had no effect on reads, which were already allowed).
  - lang/odoo-update-module.en.po: English translations of the new and changed messages and help lines; obsolete entries removed.
  - nginx-tools-tests/test_odoo_update_module.py: assertions updated (new wording; a write stays blocked with --force-busy).
  - Files: odoo-update-module.sh, lang/odoo-update-module.en.po, nginx-tools-tests/test_odoo_update_module.py, CHANGELOG.md.
- Bugs fixed: none. Behaviour change: with --force-busy, a site with writes is no longer updated after the wait (it was before).
- Safeguards and edge cases:
  - Unreadable nginx logs or PostgreSQL state are treated as writes (never update blind).
  - Without a terminal (cron, timer, pipe), no question is asked: the configured values are used and the script says so.
  - A refused (non-numeric or too small) answer keeps the default value and shows a warning.
  - --dry-run still shows the checks; the questions are asked only on an interactive terminal.
- Checks:
  - bash -n on odoo-update-module.sh; --help lists --visitor-window; non-interactive --dry-run prints the default values.
  - nginx-tools-tests: test_odoo_update_module.py (39 tests, OK), test_i18n.py (32 tests, OK), test_conventions.py.
  - Not run: the full run-all.sh suite (exceeded the time limit in this session).
- Action required: review the behaviour change for --force-busy above; check the English messages on a server running in English.

### 1.16.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 66 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: odoo-update-module.sh.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Help texts and generated configuration templates are not translated (they are displayed, or compared with shipped files, by the tests): their French text is kept on purpose.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.15.20261022.133552 - Title: Activity guard: no module update while the site writes; 60-minute wait; the update is cancelled unless --force-busy; new --check-activity.
- Reason: request: update the modules only when the site is idle. A single visitor can write (survey answer, chat message, registration, contact form), and the former guard, which counted visitors only, let such an update through.
- Changes: - Guard (site_reasons, wait_for_quiet_site): the site is busy while one of these holds: active visitors (BUSY_VISITORS threshold); write requests in the nginx logs during the last ACTIVITY_WINDOW seconds (POST, PUT, PATCH, DELETE, except the known read-only requests of Odoo); open PostgreSQL sessions on the database; write locks on ir_cron; writes in the activity tables (counters of pg_stat_user_tables, sampled twice ACTIVITY_SAMPLE seconds apart). - WAIT_QUIET default: 60 minutes (was 15). 0 = a single check. - At the end of the wait the update is CANCELLED (exit 3, nothing stopped) instead of going ahead. --force-busy (FORCE_BUSY=yes) runs it anyway. - New option --check-activity: state of the site now, changes nothing; exit 0 = quiet, 3 = busy. - PostgreSQL commands run through runuser when the program runs as root, through « sudo -n -u postgres » otherwise (no root needed). - The regular expressions of the nginx logs accept several spaces between columns. - Test hooks: ODOO_UPDATE_MODULE_NOW (clock), ODOO_UPDATE_MODULE_PG_AS (command used in place of sudo), ODOO_UPDATE_MODULE_SAMPLE, ODOO_UPDATE_MODULE_WINDOW. - Calm-site messages state the threshold instead of claiming "no active visitor" when one visitor is below it. - Files: odoo-update-module.sh; lang/odoo-update-module.en.po; doc/en and doc/fr odoo-update-module.conf.example and 09-odoo-update-module.md; nginx-tools-tests/test_odoo_update_module.py; nginx-tools-tests/fixtures/ (anonymized recording used by the tests).
- Bugs fixed: - Symptom: after WAIT_QUIET minutes with visitors still active, the update went ahead ("mise à jour quand même"), even during writes. - Diagnosis: the wait looked at visitors only, and the end of the wait forced the update. - Correction: the guard looks at all the activity above; the update is cancelled unless --force-busy.
- Guard rails and edge cases: - Unreadable nginx logs, or unreadable PostgreSQL (psql missing, sudo refused): counted as BUSY, never a blind update. - Read-only POST requests of Odoo (lists, views, reads, bus) are not writes; any other POST counts as a write.
- Checks: test_odoo_update_module (guard tests replayed on the anonymized recording: busy, calm, cancelled without --force-busy, forced with it, unreadable database counted as busy); test_i18n; test_conventions; test_cles_modeles; test_config_defaut; test_config_commune.
- Action required: if your configuration keeps WAIT_QUIET=15, it still waits 15 minutes; the new default is 60. The account that runs the update, when it is not root, needs « sudo -n -u postgres psql » without password (sudoers), otherwise the update is cancelled with a message.

### 1.14.20261020.211944 - Current version. Earlier history archived outside the repository.

## nginx-hardening.sh

### 2.55.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 227 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: nginx-hardening.sh.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Help texts and generated configuration templates are not translated (they are displayed, or compared with shipped files, by the tests): their French text is kept on purpose.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


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

### 2.45.20261025.155703 - Summary of IPs to unban after --unban-check

- Title: summary of the IPs to lift at the end of --unban-check when there are more than 5.
- Reason: on a server with many manual bans, the per-IP report scrolls far above the final tally, and the IPs recommended for lifting are hard to find again. The request was to list them after the command, only when there are more than 5.
- Changes:
  - --unban-check: each IP whose lifting is recommended (verdict "lever") or done (verdict "levé") is recorded during the loop.
  - After the BILAN line, if more than 5 IPs are recorded (constant UNBAN_SUMMARY_MIN=5), a bilingual summary lists each IP with its status (lifting recommended / lifting done). Nothing is printed for 5 IPs or fewer.
  - No new option and no new configuration key (the threshold is a fixed constant, not a setting).
  - Documentation: doc/en/02-nginx-log-audit.md and doc/fr/02-nginx-log-audit.md.
  - Files: nginx-log-audit.sh, CHANGELOG.md, doc/en/02-nginx-log-audit.md, doc/fr/02-nginx-log-audit.md.
- Bugs fixed: none.
- Safeguards and edge cases:
  - The summary is only printed by --unban-check; other actions and the exit code are unchanged.
  - An empty recommendation list never reaches the summary loop (guarded by the count check, safe with set -u).
  - Each lift still asks for confirmation one IP at a time; the summary does not lift anything.
  - Output uses no em dash or other typographic symbols in the new lines.
- Checks:
  - bash -n on nginx-log-audit.sh; shellcheck 0.11.0 with -S warning: no new warnings.
  - Isolated test of the summary block with 6 IPs (summary shown, with mixed statuses) and 5 IPs (nothing shown).
- Action required: none.


### 2.44.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 228 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: nginx-log-audit.sh.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Help texts and generated configuration templates are not translated (they are displayed, or compared with shipped files, by the tests): their French text is kept on purpose.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


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

### 1.27.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 55 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: sync-crowdsec-blocklist.sh.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Help texts and generated configuration templates are not translated (they are displayed, or compared with shipped files, by the tests): their French text is kept on purpose.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.26.20261020.211944 - Current version. Earlier history archived outside the repository.

## apps/_anonymiser.py

### 1.4.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 11 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_anonymiser.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.3.20261020.203430 - Current version. Earlier history archived outside the repository.

## apps/_bbb.py

### 1.4.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 9 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_bbb.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.3.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_cache_ip.py

### 1.3.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 11 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_cache_ip.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.2.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_config.py

### 1.10.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 13 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_config.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.9.20261022.110306 - Title: English-only values: French values detected; DEBUG_LEVEL gives VERBOSE=yes.
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - FRANCAIS (new map oui/non/vrai/faux/aucun -> yes/no/true/false/none) and valeurs_francaises(cfg) (new): list of « KEY=oui -> yes » for the configuration banner. - lire(): DEBUG_LEVEL >= 1 now sets VERBOSE=yes (was oui). - All templates doc/en and doc/fr *.conf.example (read by creer_par_defaut / rafraichir): options in alphabetical order (one « Options » section; inside each section for app-health-check and nginx-tools-mail, which hold real values), boolean values yes / no, « booléens : yes / no » in the header. No key added or removed (check: no line lost apart from the old section titles).
- Bugs fixed:
  None.
- Guard rails and edge cases: - Old French values keep their meaning (OUI / NON lists unchanged): nothing breaks on a server whose file still says oui. - Files in /etc/default without an active line follow the new sorted template at the next run; files with active lines are never rewritten.
- Checks: - test_config_commune, test_config_defaut, test_cles_modeles (new test test_modeles_en_ordre_alphabetique_et_valeurs_en_anglais).
- Action required: None.

### 1.8.20261020.211944 - Current version. Earlier history archived outside the repository.

## apps/_connexions.py

### 1.3.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 4 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_connexions.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.2.20261022.133552 - Title: PostgreSQL query of the connections through sudo -n when the account is not root.
- Changes: POSTGRES_RUN (see apps/_odoo_db.py 1.20).
- Action required: none.

### 1.1.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_courriel.py

### 1.4.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 3 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_courriel.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.3.20261020.211944 - Current version. Earlier history archived outside the repository.

## apps/_email_check.py

### 1.3.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 6 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_email_check.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.2.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_i18n.py

### 1.20.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 23 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_i18n.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.19.20261022.110306 - Title: Option values in English only; warning for French values (Python and Bash).
- Reason: Request: add MIN=yes, UNDERLINE=10 and -2026- in HIGHLIGHT to the default settings of /etc/default/app-log-live.conf; arguments in English only (oui -> yes, non -> no); options of the default configuration files in /etc/default in alphabetical order.
- Changes: - oui_non(): always yes / no (summary « Options : ... »). - afficher_configuration(): after the ignored values, one warning per French value (« valeur en français, écrire l'anglais dans le fichier de configuration : MIN=oui -> yes »); lang/_i18n.en.po translated. - apps/_i18n.sh: config_defaut collects French values in CFG_FRANCAIS (new array) and config_afficher prints the same warning; booleans shown as yes / no; « yes ou no attendu » for an invalid value; DEBUG_LEVEL gives VERBOSE=yes; lang/_config.en.po updated.
- Bugs fixed:
  None.
- Guard rails and edge cases: - The French value is still applied (same meaning): only a warning, never an ignored setting. - CFG_FRANCAIS is reset with the other arrays at each config_lire.
- Checks: - test_i18n (catalogues, Bash configuration), test_config_commune.
- Action required: None.

### 1.18.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_limites.py

### 1.2.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 4 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_limites.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.1.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_listes.py

### 1.4.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 9 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_listes.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.3.20261020.211944 - Current version. Earlier history archived outside the repository.

## apps/_odoo_conf.py

### 1.4.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 2 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_odoo_conf.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.3.20261020.211944 - Current version. Earlier history archived outside the repository.

## apps/_odoo_db.py

### 1.22.20261025.113933 - New read-only function langue_defaut() (default language of the website)

- Title: New read-only function langue_defaut(base): default language of the website, read from Odoo.
- Reason: Needed by app-log-live.py to show the default language of the site in the summary (see its 1.106).
- Changes:
  - langue_defaut(base, delai=20): code of the default language (e.g. "fr_CA") from website.default_lang_id joined to res_lang; fallback: first active language. Root only (os.geteuid() == 0), otherwise None.
  - Files: apps/_odoo_db.py.
- Bugs fixed: none.
- Safeguards and edge cases: read-only query through _requete() (transaction forced read-only by PostgreSQL); None if the table or the column is missing.
- Checks: python3 -I -m py_compile; --version; without a database, returns None.
- Action required: none.

### 1.21.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 13 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_odoo_db.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.20.20261022.133552 - Title: PostgreSQL queries run as the postgres user through sudo -n when the account is not root.
- Changes: POSTGRES_RUN (runuser when root, « sudo -n -u postgres » otherwise) replaces the runuser prefix of the six queries.
- Action required: none beyond the sudoers rules of app-log-live.py 1.100.

### 1.19.20261020.103939 - Current version. Earlier history archived outside the repository.

## apps/_odoo_users.py

### 1.3.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 3 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_odoo_users.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.2.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_rapport.py

### 1.13.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 12 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_rapport.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.12.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_record.py

### 1.3.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 6 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_record.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.2.20261022.133552 - Title: PostgreSQL samples mandatory; context/system.txt; writes per table; sudo -n for the journal of the service.
- Changes: start() refuses the recording without psql, without a database, or without PostgreSQL access; context/system.txt (uid, sudo, operating system, kernel, Python, tool versions, no user name); db/writes-BASE.log (write counters per activity table at each sample); privileged() for the journal of the service.
- Files: apps/_record.py; nginx-tools-tests/test_record.py.
- Action required: none beyond the sudoers rules of app-log-live.py 1.100.

### 1.1.20261022.083937 - Title: Steps of the test (N key of app-log-live.py): steps.txt.
- Reason: The N key of app-log-live.py marks the start and the end of each action of a test; the archive must hold them, with their times, to match the log lines.
- Changes: - Recorder.step_start(description) / step_end(reason): step numbers, times, descriptions; the open step is closed before a new one starts. - records.log and stream-all.log: "STEP n START hh:mm:ss - description" and "STEP n END hh:mm:ss - duration s - description". - steps.txt (new, bilingual header) in the archive, and "Steps" line in README.txt. - stop(): a step still open is closed with reason "recording stopped".
- Bugs fixed:
  None.
- Guard rails and edge cases: - step_start returns None when no recording runs or when it is stopping (no crash, nothing written). - Description masked with the same mask() as the lines; spaces collapsed; 200 characters maximum.
- Checks: - test_record.py: test_etapes_debut_fin_dans_records_log_et_steps_txt.
- Action required: None.

### 1.0.20261020.230008 - Current version. Earlier history archived outside the repository.

## apps/_reseau.py

### 1.4.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 7 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_reseau.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.3.20261019.150215 - Current version. Earlier history archived outside the repository.

## apps/_sysperf.py

### 1.3.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 4 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_sysperf.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.2.20261019.150215 - Current version. Earlier history archived outside the repository.

## run-all.sh

### 1.196.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 55 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: nginx-tools-tests/run-all.sh.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Help texts and generated configuration templates are not translated (they are displayed, or compared with shipped files, by the tests): their French text is kept on purpose.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.195.20261022.083937 - Title: test_record: steps of the test (N key of app-log-live.py).
- Reason: New test of the step markers (N key) of the test recording.
- Changes: - nginx-tools-tests/test_record.py: archive() accepts etapes; new test_etapes_debut_fin_dans_records_log_et_steps_txt. - Merged with main (1.194): this change takes 1.195; nginx-tools 1.142.
- Bugs fixed:
  None.
- Guard rails and edge cases: - The step still open at the stop is checked (closed with "recording stopped").
- Checks: - run-all.sh on the modules test_record and test_conventions.
- Action required: None.

### 1.194.20261021.130912 - Current version. Earlier history archived outside the repository.

## apps/_traduire.py

### 1.6.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 12 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Shared module used by several programs: the translated comments do not change any behavior. Files: apps/_traduire.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.


### 1.5.20261019.150215 - Current version. Earlier history archived outside the repository.

## doc/build_docs.py

### 1.7.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 3 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: doc/build_docs.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.

## nginx-tools-tests/stats_runner.py

### 1.1.20261022.231529 - Code comments translated to English

- Title: Code comments translated to English (repository convention).
- Reason: Commit messages and code comments written in French with accents were displayed badly in the GitHub logs (UTF-8 display). The repository conventions require English code comments; user-visible text stays bilingual (French and English).
- Changes:
  - Comments only: 4 comment lines translated from French to English. No code, string, docstring or option was changed.
  - Copyright line written "Quebec" (no accent), for the same reason.
  - Files: nginx-tools-tests/stats_runner.py.
- Bugs fixed: none (translation only).
- Safeguards and edge cases:
  - Only comment text changed: the non-comment lines of the file are identical to the previous version (checked with git diff).
  - Docstrings and user-visible strings keep their current (bilingual) text.
- Checks:
  - Syntax check (bash -n or python py_compile) and a diff check showing that only comments changed.
  - Test suite nginx-tools-tests/run-all.sh (result given in the pull request).
- Action required: none.

